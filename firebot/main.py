"""Firebot entry point.

Run modes:
  python -m firebot.main            # loop forever (default; for the always-on container)
  python -m firebot.main --once     # single pass then exit (cron / testing)
  python -m firebot.main --once --dry-run   # fetch + log what WOULD post, post nothing
  python -m firebot.main --test     # post a single sample embed to verify the webhook
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import datetime
from functools import partial

from . import __version__
from .cluster import cluster_hotspots
from .config import Config
from .discord import (
    build_firms_cluster_embed,
    build_nifc_embed,
    build_nifc_update_embed,
    post_embeds,
    post_test,
)
from .geo import bbox_from_center_half_extent, haversine_miles, incident_footprint_radius_miles
from .maps import static_map_url
from .sources.firms import query_firms
from .sources.inciweb import InciWebIndex, incident_info_url
from .sources.nifc import query_nifc

log = logging.getLogger("firebot")


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def _incident_changes(inc, meta: dict, cfg: Config) -> list[str]:
    """Return human-readable change lines if a known incident changed enough to re-post."""
    lines: list[str] = []
    base_acres = meta.get("acres")
    base_contained = meta.get("contained")
    was_out = bool(meta.get("out", False))

    # Significant growth (since the last alert's baseline).
    if cfg.update_on_growth and inc.acres is not None:
        if base_acres is None:
            # First time we have a size at all — alert if it's already meaningful.
            if inc.acres >= cfg.update_acres_abs:
                lines.append(f"Size: now {inc.acres:,.0f} acres")
        else:
            grew_abs = inc.acres - base_acres
            grew_pct = (grew_abs / base_acres * 100) if base_acres > 0 else 0.0
            big_pct_growth = (
                base_acres > 0
                and grew_pct >= cfg.update_acres_pct
                and grew_abs >= cfg.update_acres_pct_floor
            )
            if grew_abs >= cfg.update_acres_abs or big_pct_growth:
                lines.append(f"Size: {base_acres:,.0f} → {inc.acres:,.0f} acres (+{grew_abs:,.0f})")

    # Containment change in either direction.
    if cfg.update_on_containment and inc.percent_contained is not None:
        base = base_contained if base_contained is not None else 0.0
        if abs(inc.percent_contained - base) >= cfg.update_containment_delta:
            lines.append(f"Contained: {base:.0f}% → {inc.percent_contained:.0f}%")

    # Out / contained transition (one-time).
    if cfg.update_on_out and inc.out_or_contained and not was_out:
        lines.append("Fire reported out / contained")

    return lines


def _relevant(cfg: Config, lat: float, lon: float) -> bool:
    """True if the point is within the true great-circle relevance radius (or filter off)."""
    if cfg.relevance_radius_miles <= 0:
        return True
    return haversine_miles(cfg.center_lat, cfg.center_lon, lat, lon) <= cfg.relevance_radius_miles


def _should_alert_new(inc, meta: dict | None, cfg: Config, now: datetime) -> bool:
    """Whether a not-yet-alerted incident is significant enough for its first alert.

    ``meta`` is the stored "pending" baseline (acres + seen_ts) if we've seen this fire
    before but held off, else None. A fire alerts once it reaches ``new_alert_min_acres``,
    or when it grows at least ``new_alert_acres_per_day`` (and ``new_alert_growth_floor``
    acres absolute) since we first saw it.
    """
    if inc.acres is None:
        return False
    if inc.acres >= cfg.new_alert_min_acres:
        return True
    if meta is not None:
        base = meta.get("acres")
        base_ts = meta.get("seen_ts")
        if base is not None and base_ts:
            try:
                since = datetime.fromisoformat(base_ts)
            except ValueError:
                since = None
            if since is not None:
                elapsed_days = (now - since).total_seconds() / 86400.0
                grew = inc.acres - base
                if (
                    elapsed_days > 0
                    and grew >= cfg.new_alert_growth_floor
                    and grew / elapsed_days >= cfg.new_alert_acres_per_day
                ):
                    return True
    return False


def _cluster_alertable(cluster, cfg: Config) -> bool:
    """A hotspot cluster alerts if it has enough detections or one hot enough pixel."""
    if cluster.count >= cfg.firms_min_cluster_detections:
        return True
    mf = cluster.max_frp
    return mf is not None and mf >= cfg.firms_single_detection_min_frp


def _suppress_radius_miles(inc, cfg: Config) -> float:
    """Effective hotspot-suppression radius around an incident, scaled to its footprint."""
    footprint = incident_footprint_radius_miles(inc.acres)
    return max(cfg.firms_suppress_near_incident_miles, footprint + cfg.firms_suppress_buffer_miles)


def _collect_new_items(cfg: Config, state) -> tuple[list, list, list]:
    """Fetch sources; return (new_incidents, updated_incidents, new_clusters).

    ``updated_incidents`` is a list of (incident, change_lines) for known incidents
    that changed enough to warrant a follow-up alert. ``new_clusters`` groups nearby
    FIRMS detections into one fire each. State is not mutated here.
    """
    bbox = bbox_from_center_half_extent(cfg.center_lat, cfg.center_lon, cfg.square_half_miles)
    log.info(
        "Area: square %.0f mi around (%.4f, %.4f) -> bbox %s",
        cfg.square_half_miles, cfg.center_lat, cfg.center_lon, bbox.as_envelope(),
    )

    incidents = []
    if cfg.enable_nifc:
        try:
            incidents = query_nifc(bbox, cfg.nifc_incident_type_list())
            log.info("NIFC: %d incident(s) in area", len(incidents))
        except Exception as exc:  # one source failing must not kill the run
            log.error("NIFC query failed: %s", exc)

    hotspots = []
    if cfg.enable_firms:
        if not cfg.firms_map_key:
            log.warning("FIRMS enabled but FIRMS_MAP_KEY not set; skipping FIRMS.")
        else:
            try:
                hotspots = query_firms(
                    bbox,
                    cfg.firms_map_key,
                    cfg.firms_source,
                    cfg.firms_day_range,
                    viirs_min_confidence=cfg.firms_viirs_min_confidence,
                    min_confidence_pct=cfg.firms_min_confidence_pct,
                    frp_min=cfg.firms_frp_min,
                )
                log.info("FIRMS: %d hotspot(s) after filters", len(hotspots))
            except Exception as exc:
                log.error("FIRMS query failed: %s", exc)

    # Trim the square's corners to a true relevance radius so distant fires don't leak in.
    incidents = [i for i in incidents if _relevant(cfg, i.lat, i.lon)]
    hotspots = [h for h in hotspots if _relevant(cfg, h.lat, h.lon)]

    # Classify NIFC incidents: alert-worthy new fires, silently-tracked "pending" fires
    # (too small to alert yet), and updates to already-alerted ones.
    now = datetime.now()
    new_incidents = []
    updated_incidents = []
    pending_incidents = []
    for inc in incidents:
        meta = state.get(f"nifc:{inc.key}")
        if meta is None or not meta.get("alerted", True):
            if _should_alert_new(inc, meta, cfg, now):
                new_incidents.append(inc)
            else:
                pending_incidents.append(inc)  # track/refresh baseline, no alert
        elif cfg.enable_incident_updates:
            changes = _incident_changes(inc, meta, cfg)
            if changes:
                updated_incidents.append((inc, changes))

    # New FIRMS hotspots, suppressing those that coincide with a known incident.
    # Collapse duplicate detections that share a dedupe key WITHIN this run (adjacent
    # VIIRS pixels round to the same key); keep the highest-FRP one as representative.
    # Suppression radius scales to each fire's own footprint (a large fire's perimeter
    # sits well beyond its reported center point).
    new_hotspots = []
    seen_keys: set[str] = set()
    supp_on = cfg.firms_suppress_near_incident_miles > 0
    for hs in sorted(hotspots, key=lambda h: (h.frp or 0.0), reverse=True):
        if state.has(f"firms:{hs.key}") or hs.key in seen_keys:
            continue
        if supp_on and any(
            haversine_miles(hs.lat, hs.lon, inc.lat, inc.lon) <= _suppress_radius_miles(inc, cfg)
            for inc in incidents
        ):
            log.debug("Suppressing hotspot %s near a known incident", hs.key)
            continue
        seen_keys.add(hs.key)
        new_hotspots.append(hs)

    # Group nearby detections into one fire each, so a big multi-pixel fire = one alert,
    # then drop clusters too weak to be worth alerting (lone low-FRP pixels).
    clusters = cluster_hotspots(new_hotspots, cfg.firms_cluster_miles)
    new_clusters = [c for c in clusters if _cluster_alertable(c, cfg)]
    if hotspots:
        log.info(
            "FIRMS: %d new detection(s) -> %d cluster(s), %d alertable",
            len(new_hotspots), len(clusters), len(new_clusters),
        )

    return new_incidents, updated_incidents, new_clusters, pending_incidents


def _record_incident(state, inc) -> None:
    """Store/refresh an alerted incident's update baseline."""
    state.add(
        f"nifc:{inc.key}",
        "nifc",
        alerted=True,
        acres=inc.acres,
        contained=inc.percent_contained,
        out=inc.out_or_contained,
    )


def _record_pending(state, pending) -> None:
    """Record a first-seen sub-threshold incident so its growth can be measured later.

    Only the first sighting sets the baseline (acres + timestamp); later sightings keep
    the original baseline so growth accumulates rather than resetting each run.
    """
    for inc in pending:
        if state.get(f"nifc:{inc.key}") is None:
            state.add(
                f"nifc:{inc.key}",
                "nifc",
                alerted=False,
                acres=inc.acres,
                seen_ts=datetime.now().isoformat(),
            )


def run_once(cfg: Config, state, *, dry_run: bool) -> int:
    new_incidents, updated_incidents, new_clusters, pending_incidents = _collect_new_items(cfg, state)
    total = len(new_incidents) + len(updated_incidents) + len(new_clusters)

    if total == 0:
        # Persist pending baselines even when there's nothing to alert on, so a slow
        # fire's growth is measured against its first sighting on future runs.
        if not dry_run and pending_incidents:
            _record_pending(state, pending_incidents)
            state.prune(cfg.state_retention_days)
            state.save()
            log.info("Tracked %d sub-threshold fire(s); nothing to alert.", len(pending_incidents))
        else:
            log.info("No new fires or updates to report.")
        return 0

    log.info(
        "New: %d incident(s), %d update(s), %d fire cluster(s)",
        len(new_incidents), len(updated_incidents), len(new_clusters),
    )

    z = cfg.map_link_zoom
    # Fetch the InciWeb feed once so incident titles can link to a real incident page.
    iw = InciWebIndex.fetch() if (new_incidents or updated_incidents) else None

    def _iurl(inc):
        return incident_info_url(iw, inc.name, inc.state)

    clat, clon, clabel = cfg.center_lat, cfg.center_lon, cfg.center_label
    # Static minimap closures (returns None when no provider/key is configured, so
    # builders simply omit the embed image). Red pin for NIFC, orange for FIRMS.
    _smap = partial(
        static_map_url,
        provider=cfg.static_map_provider,
        key=cfg.static_map_key,
        zoom=cfg.static_map_zoom,
        size=(cfg.static_map_width, cfg.static_map_height),
        style=cfg.static_map_style,
    )
    nifc_map = partial(_smap, color="d7263d")   # COLOR_WILDFIRE red
    firms_map = partial(_smap, color="ff7a00")  # COLOR_HOTSPOT orange

    embeds = [build_nifc_embed(i, z, _iurl(i), clat, clon, clabel, static_map=nifc_map) for i in new_incidents]
    embeds += [
        build_nifc_update_embed(inc, changes, z, _iurl(inc), clat, clon, clabel, static_map=nifc_map)
        for inc, changes in updated_incidents
    ]
    embeds += [
        build_firms_cluster_embed(c, z, clat, clon, clabel, static_map=firms_map)
        for c in new_clusters
    ]

    if dry_run:
        for inc in new_incidents:
            log.info("[dry-run] NEW NIFC %s (%s) %.4f,%.4f", inc.name, inc.type_category, inc.lat, inc.lon)
        for inc, changes in updated_incidents:
            log.info("[dry-run] UPDATE NIFC %s: %s", inc.name, "; ".join(changes))
        for c in new_clusters:
            r = c.representative
            log.info("[dry-run] FIRMS fire: %d detection(s), max FRP=%s, rep %.4f,%.4f",
                     c.count, c.max_frp, r.lat, r.lon)
        log.info("[dry-run] would post %d embed(s); state NOT updated", len(embeds))
        return total

    post_embeds(cfg.discord_webhook_url, embeds)
    # Only record state after a successful post so failures get retried next run.
    for inc in new_incidents:
        _record_incident(state, inc)  # promotes pending -> alerted
    for inc, _changes in updated_incidents:
        _record_incident(state, inc)  # reset baseline to current values
    _record_pending(state, pending_incidents)  # track any still-sub-threshold fires
    for c in new_clusters:
        for key in c.member_keys:  # record every pixel so the fire isn't re-alerted
            state.add(f"firms:{key}", "firms")
    state.prune(cfg.state_retention_days)
    state.save()
    log.info("Posted %d embed(s) and saved state.", len(embeds))
    return total


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Firebot — Discord wildfire alerts")
    parser.add_argument("--once", action="store_true", help="run a single pass then exit")
    parser.add_argument("--loop", action="store_true", help="run forever (default)")
    parser.add_argument("--dry-run", action="store_true", help="log what would post; post nothing; don't update state")
    parser.add_argument("--test", action="store_true", help="post a single test embed and exit")
    args = parser.parse_args(argv)

    _setup_logging()
    log.info("Firebot v%s starting", __version__)
    cfg = Config()

    if args.test:
        cfg.require_webhook()
        post_test(cfg.discord_webhook_url)
        log.info("Test embed posted.")
        return 0

    if not args.dry_run:
        cfg.require_webhook()

    # Import here so State picks up the configured path.
    from .state import State

    if args.once:
        state = State.load(cfg.state_path)
        run_once(cfg, state, dry_run=args.dry_run)
        return 0

    # Default: loop.
    interval = max(cfg.poll_interval_min, 1) * 60
    log.info("Looping every %d min. State at %s", cfg.poll_interval_min, cfg.state_path)
    while True:
        state = State.load(cfg.state_path)
        try:
            run_once(cfg, state, dry_run=args.dry_run)
        except Exception as exc:
            log.exception("run_once failed: %s", exc)
        time.sleep(interval)


if __name__ == "__main__":
    raise SystemExit(main())

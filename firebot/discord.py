"""Discord delivery via webhook (no bot token, no gateway connection).

A webhook post is just an HTTP POST returning 204. We send rich embeds and respect
Discord's limit of 10 embeds per message.
"""

from __future__ import annotations

import time

from .cluster import Cluster
from .geo import offset_description
from .http import session
from .maps import airnow_map_url, firms_map_url
from .sources.firms import satellite_name
from .sources.nifc import Incident

# Colors (decimal)
COLOR_WILDFIRE = 0xD7263D   # red
COLOR_PRESCRIBED = 0xE6A700  # amber (RX/prescribed)
COLOR_HOTSPOT = 0xFF7A00    # orange
COLOR_UPDATE = 0xF59E0B     # amber (growth/containment update)
COLOR_CONTAINED = 0x2ECC71  # green (out / contained)
COLOR_TEST = 0x5865F2       # blurple

MAX_EMBEDS_PER_MESSAGE = 10


def _fmt_dt(dt) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "unknown"


def build_nifc_embed(
    inc: Incident,
    zoom: int = 9,
    incident_url: str | None = None,
    center_lat: float | None = None,
    center_lon: float | None = None,
    center_label: str = "",
    *,
    static_map=None,
) -> dict:
    is_rx = inc.type_category.upper() == "RX"
    title = ("🔥 " if not is_rx else "🪵 ") + inc.name
    map_url = airnow_map_url(inc.lat, inc.lon, zoom)
    fields = []
    if inc.acres is not None:
        fields.append({"name": "Size", "value": f"{inc.acres:,.0f} acres", "inline": True})
    if inc.percent_contained is not None:
        fields.append({"name": "Contained", "value": f"{inc.percent_contained:.0f}%", "inline": True})
    if inc.type_category:
        fields.append({"name": "Type", "value": inc.type_category, "inline": True})
    loc = ", ".join(p for p in [inc.county, inc.state] if p)
    if loc:
        fields.append({"name": "Location", "value": loc, "inline": True})
    if center_lat is not None and center_lon is not None and center_label:
        fields.append({"name": "Distance",
                       "value": offset_description(center_lat, center_lon, inc.lat, inc.lon, center_label),
                       "inline": True})
    if inc.cause:
        fields.append({"name": "Cause", "value": inc.cause, "inline": True})
    fields.append({"name": "Discovered", "value": _fmt_dt(inc.discovered), "inline": True})
    embed = {
        "title": title[:256],
        "url": incident_url or map_url,  # title -> incident page
        "color": COLOR_PRESCRIBED if is_rx else COLOR_WILDFIRE,
        # coordinates -> map
        "description": f"📍 [{inc.lat:.4f}, {inc.lon:.4f}]({map_url}) · NIFC incident · 🗺️ AirNow Fire & Smoke map",
        "fields": fields,
        "footer": {"text": "Source: NIFC WFIGS"},
    }
    if static_map is not None:
        img = static_map(inc.lat, inc.lon)
        if img:
            embed["image"] = {"url": img}
    return embed


def build_nifc_update_embed(
    inc: Incident,
    change_lines: list[str],
    zoom: int = 9,
    incident_url: str | None = None,
    center_lat: float | None = None,
    center_lon: float | None = None,
    center_label: str = "",
    *,
    static_map=None,
) -> dict:
    """Embed for a change to an already-reported incident."""
    out = inc.out_or_contained
    title = ("✅ " if out else "📈 ") + f"{inc.name} — update"
    map_url = airnow_map_url(inc.lat, inc.lon, zoom)
    fields = []
    if inc.acres is not None:
        fields.append({"name": "Size", "value": f"{inc.acres:,.0f} acres", "inline": True})
    if inc.percent_contained is not None:
        fields.append({"name": "Contained", "value": f"{inc.percent_contained:.0f}%", "inline": True})
    loc = ", ".join(p for p in [inc.county, inc.state] if p)
    if loc:
        fields.append({"name": "Location", "value": loc, "inline": True})
    if center_lat is not None and center_lon is not None and center_label:
        fields.append({"name": "Distance",
                       "value": offset_description(center_lat, center_lon, inc.lat, inc.lon, center_label),
                       "inline": True})
    desc = "\n".join(f"• {line}" for line in change_lines) or "Updated"
    desc += f"\n📍 [{inc.lat:.4f}, {inc.lon:.4f}]({map_url}) · 🗺️ AirNow Fire & Smoke map"
    embed = {
        "title": title[:256],
        "url": incident_url or map_url,  # title -> incident page
        "color": COLOR_CONTAINED if out else COLOR_UPDATE,
        "description": desc,
        "fields": fields,
        "footer": {"text": "Source: NIFC WFIGS · update"},
    }
    if static_map is not None:
        img = static_map(inc.lat, inc.lon)
        if img:
            embed["image"] = {"url": img}
    return embed


_VIIRS_CONF_LABELS = {"l": "low", "n": "nominal", "h": "high"}


def build_firms_cluster_embed(
    cluster: Cluster,
    zoom: int = 9,
    center_lat: float | None = None,
    center_lon: float | None = None,
    center_label: str = "",
    *,
    static_map=None,
) -> dict:
    """One embed per clustered fire (a group of nearby detections)."""
    rep = cluster.representative
    map_url = firms_map_url(rep.lat, rep.lon, zoom)
    conf = _VIIRS_CONF_LABELS.get(str(rep.confidence).strip().lower(), str(rep.confidence) or "n/a")

    fields = [{"name": "Satellite", "value": satellite_name(rep.satellite), "inline": True}]
    if cluster.max_frp is not None:
        fields.append({"name": "Max FRP", "value": f"{cluster.max_frp:.1f} MW", "inline": True})
    if cluster.count > 1:
        fields.append({"name": "Detections", "value": str(cluster.count), "inline": True})
        if cluster.span_miles >= 1:
            fields.append({"name": "Extent", "value": f"~{cluster.span_miles:.0f} mi across", "inline": True})
    else:
        fields.append({"name": "Confidence", "value": conf, "inline": True})
    if center_lat is not None and center_lon is not None and center_label:
        fields.append({"name": "Distance",
                       "value": offset_description(center_lat, center_lon, rep.lat, rep.lon, center_label),
                       "inline": True})
    fields.append({"name": "Detected", "value": _fmt_dt(cluster.latest_acq), "inline": True})

    if cluster.count > 1:
        headline = f"🛰️ Satellite fire ({cluster.count} detections)"
    else:
        headline = "🛰️ Satellite fire hotspot"

    embed = {
        "title": headline[:256],
        "url": map_url,
        "color": COLOR_HOTSPOT,
        "description": f"📍 [{rep.lat:.4f}, {rep.lon:.4f}]({map_url}) · unconfirmed detection · 🗺️ NASA FIRMS map",
        "fields": fields,
        "footer": {"text": "Source: NASA FIRMS"},
    }
    if static_map is not None:
        img = static_map(rep.lat, rep.lon)
        if img:
            embed["image"] = {"url": img}
    return embed


def _retry_after_seconds(resp) -> float:
    """Discord's 429 body is JSON with retry_after, but be safe about non-JSON bodies."""
    try:
        return float(resp.json().get("retry_after", 1))
    except (ValueError, AttributeError, TypeError):
        return 1.0


def post_embeds(webhook_url: str, embeds: list[dict], *, timeout: int = 30) -> None:
    """Post embeds in batches of <=10. Raises on non-2xx.

    POSTs go through the shared session for connection pooling only — no automatic
    retries (a retried POST whose first attempt landed would double-post); the single
    explicit 429 retry below is the only re-send.
    """
    for i in range(0, len(embeds), MAX_EMBEDS_PER_MESSAGE):
        batch = embeds[i : i + MAX_EMBEDS_PER_MESSAGE]
        resp = session.post(webhook_url, json={"embeds": batch}, timeout=timeout)
        # 429 = rate limited; honor retry_after then retry once.
        if resp.status_code == 429:
            time.sleep(_retry_after_seconds(resp) + 0.5)
            resp = session.post(webhook_url, json={"embeds": batch}, timeout=timeout)
        resp.raise_for_status()
        if i + MAX_EMBEDS_PER_MESSAGE < len(embeds):
            time.sleep(1.0)  # be gentle between messages


def post_test(webhook_url: str) -> None:
    embed = {
        "title": "✅ Firebot is connected",
        "color": COLOR_TEST,
        "description": "This is a test message. Fire alerts will look similar to this.",
        "footer": {"text": "Firebot"},
    }
    post_embeds(webhook_url, [embed])

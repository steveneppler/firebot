"""Environment-driven configuration.

All values have sensible defaults except the secrets (Discord webhook URL and the
NASA FIRMS map key). Load these from the process environment so the same image can
be configured per-deployment in Coolify.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return float(raw)


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


def _get_str(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    # --- Secrets / delivery ---
    discord_webhook_url: str = field(default_factory=lambda: _get_str("DISCORD_WEBHOOK_URL"))
    firms_map_key: str = field(default_factory=lambda: _get_str("FIRMS_MAP_KEY"))

    # --- Area: a square centered on the given point, extending SQUARE_HALF_MILES
    #     from the center to each edge. Grand Junction, CO by default. ---
    center_lat: float = field(default_factory=lambda: _get_float("CENTER_LAT", 39.0639))
    center_lon: float = field(default_factory=lambda: _get_float("CENTER_LON", -108.5506))
    square_half_miles: float = field(default_factory=lambda: _get_float("SQUARE_HALF_MILES", 100.0))
    # Additional true great-circle radius filter (miles) applied on top of the query
    # box, so the box corners don't leak in distant fires. 0 disables (pure square).
    # Default covers Grand Junction's surrounding communities out to Ouray/Telluride.
    relevance_radius_miles: float = field(default_factory=lambda: _get_float("RELEVANCE_RADIUS_MILES", 100.0))
    # Place name used in "X mi <direction> of <label>" descriptions.
    center_label: str = field(default_factory=lambda: _get_str("CENTER_LABEL", "Grand Junction"))

    # --- Scheduling ---
    poll_interval_min: int = field(default_factory=lambda: _get_int("POLL_INTERVAL_MIN", 30))

    # --- Map links (zoom level used in the AirNow / FIRMS deep-links) ---
    map_link_zoom: int = field(default_factory=lambda: _get_int("MAP_LINK_ZOOM", 9))

    # --- Static minimap image embedded in each alert (optional) ---
    # Provider: "none" (default; no image, unchanged behavior) or "mapbox".
    static_map_provider: str = field(default_factory=lambda: _get_str("STATIC_MAP_PROVIDER", "none"))
    # Token/key for the provider (a Mapbox public access token). Not needed for "none".
    static_map_key: str = field(default_factory=lambda: _get_str("STATIC_MAP_KEY"))
    static_map_zoom: int = field(default_factory=lambda: _get_int("STATIC_MAP_ZOOM", 11))
    static_map_width: int = field(default_factory=lambda: _get_int("STATIC_MAP_WIDTH", 600))
    static_map_height: int = field(default_factory=lambda: _get_int("STATIC_MAP_HEIGHT", 360))
    # Optional basemap style override (blank = satellite-streets default for Mapbox).
    static_map_style: str = field(default_factory=lambda: _get_str("STATIC_MAP_STYLE"))

    # --- Sources toggle ---
    enable_nifc: bool = field(default_factory=lambda: _get_bool("ENABLE_NIFC", True))
    enable_firms: bool = field(default_factory=lambda: _get_bool("ENABLE_FIRMS", True))

    # --- NIFC options ---
    # Comma-separated IncidentTypeCategory values to include. "WF" = wildfire,
    # "RX" = prescribed burn, "CX" = complex. Default: wildfires only.
    nifc_incident_types: str = field(default_factory=lambda: _get_str("NIFC_INCIDENT_TYPES", "WF"))

    # --- New-fire alert gate (relevance) ---
    # A newly seen incident only alerts once it is a large fire OR is growing fast.
    # Smaller fires are tracked silently ("pending") so growth can be measured.
    # Alert immediately when the fire reaches this size (acres).
    new_alert_min_acres: float = field(default_factory=lambda: _get_float("NEW_ALERT_MIN_ACRES", 100.0))
    # ...or when a pending fire grows at least this many acres/day since first seen,
    new_alert_acres_per_day: float = field(default_factory=lambda: _get_float("NEW_ALERT_ACRES_PER_DAY", 50.0))
    # provided it has also grown at least this many acres in absolute terms.
    new_alert_growth_floor: float = field(default_factory=lambda: _get_float("NEW_ALERT_GROWTH_FLOOR", 20.0))

    # --- Incident update alerts (re-post when a known incident changes) ---
    enable_incident_updates: bool = field(default_factory=lambda: _get_bool("ENABLE_INCIDENT_UPDATES", True))
    update_on_growth: bool = field(default_factory=lambda: _get_bool("UPDATE_ON_GROWTH", True))
    update_on_containment: bool = field(default_factory=lambda: _get_bool("UPDATE_ON_CONTAINMENT", True))
    update_on_out: bool = field(default_factory=lambda: _get_bool("UPDATE_ON_OUT", True))
    # Growth fires when acreage rises by >= this percent OR >= this many acres
    # (since the last alert). Moderate defaults.
    update_acres_pct: float = field(default_factory=lambda: _get_float("UPDATE_ACRES_PCT", 25.0))
    update_acres_abs: float = field(default_factory=lambda: _get_float("UPDATE_ACRES_ABS", 100.0))
    # Percent-growth alerts also require at least this many acres of absolute growth,
    # so a tiny fire (e.g. 2 -> 4 acres = +100%) doesn't spam updates.
    update_acres_pct_floor: float = field(default_factory=lambda: _get_float("UPDATE_ACRES_PCT_FLOOR", 10.0))
    # Containment fires when % contained moves by >= this many points since the last alert.
    update_containment_delta: float = field(default_factory=lambda: _get_float("UPDATE_CONTAINMENT_DELTA", 20.0))

    # --- FIRMS options ---
    firms_source: str = field(default_factory=lambda: _get_str("FIRMS_SOURCE", "VIIRS_NOAA20_NRT"))
    firms_day_range: int = field(default_factory=lambda: _get_int("FIRMS_DAY_RANGE", 1))
    # VIIRS confidence is low/nominal/high; keep detections at this level or above.
    # (A 300-mile box in summer can return >1000 hotspots, so "high" is the sane default.)
    firms_viirs_min_confidence: str = field(default_factory=lambda: _get_str("FIRMS_VIIRS_MIN_CONFIDENCE", "high"))
    # MODIS confidence is 0-100.
    firms_min_confidence_pct: int = field(default_factory=lambda: _get_int("FIRMS_MIN_CONFIDENCE_PCT", 0))
    # Drop detections below this fire radiative power (MW) to cut ag/industrial noise.
    firms_frp_min: float = field(default_factory=lambda: _get_float("FIRMS_FRP_MIN", 20.0))
    # Group detections within this many miles of each other into ONE fire alert.
    # 0 disables clustering (one alert per detection).
    firms_cluster_miles: float = field(default_factory=lambda: _get_float("FIRMS_CLUSTER_MILES", 3.0))
    # A hotspot cluster only alerts if it has at least this many detections...
    firms_min_cluster_detections: int = field(default_factory=lambda: _get_int("FIRMS_MIN_CLUSTER_DETECTIONS", 2))
    # ...or a single detection at least this hot (MW). Cuts lone weak-pixel noise.
    firms_single_detection_min_frp: float = field(
        default_factory=lambda: _get_float("FIRMS_SINGLE_DETECTION_MIN_FRP", 50.0)
    )
    # Suppress a hotspot if it is within this many miles of a known NIFC incident
    # (it is almost certainly the same fire). 0 disables suppression. The effective
    # radius is scaled up to a large fire's own footprint plus the buffer below.
    firms_suppress_near_incident_miles: float = field(
        default_factory=lambda: _get_float("FIRMS_SUPPRESS_NEAR_INCIDENT_MILES", 5.0)
    )
    # Extra margin added beyond a fire's estimated footprint radius when suppressing.
    firms_suppress_buffer_miles: float = field(
        default_factory=lambda: _get_float("FIRMS_SUPPRESS_BUFFER_MILES", 2.0)
    )

    # --- State ---
    state_path: str = field(default_factory=lambda: _get_str("STATE_PATH", "/data/state.json"))
    # Drop remembered hotspot keys older than this many days so state.json stays small.
    state_retention_days: int = field(default_factory=lambda: _get_int("STATE_RETENTION_DAYS", 7))

    def nifc_incident_type_list(self) -> list[str]:
        return [t.strip().upper() for t in self.nifc_incident_types.split(",") if t.strip()]

    def require_webhook(self) -> None:
        if not self.discord_webhook_url:
            raise SystemExit("DISCORD_WEBHOOK_URL is not set. See .env.example.")

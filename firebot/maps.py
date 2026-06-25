"""Build deep-links to external maps, centered on a fire's location.

Smart per-source: NIFC named incidents link to the AirNow Fire & Smoke Map (fire +
smoke / air quality), FIRMS satellite hotspots link to the NASA FIRMS Fire Map (the
raw thermal detections). Zoom is configurable via MAP_LINK_ZOOM.
"""

from __future__ import annotations

DEFAULT_ZOOM = 9

# Static "minimap" image embedded inside alerts (see static_map_url).
DEFAULT_STATIC_SIZE = (600, 360)  # renders well in a Discord embed
DEFAULT_STATIC_ZOOM = 11          # tighter than the deep-link zoom; a minimap wants context


def firms_map_url(lat: float, lon: float, zoom: int = DEFAULT_ZOOM) -> str:
    """NASA FIRMS Fire Map. Hash format: #d:<range>;@<lon>,<lat>,<zoom>z"""
    return f"https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@{lon:.4f},{lat:.4f},{zoom}z"


def airnow_map_url(lat: float, lon: float, zoom: int = DEFAULT_ZOOM) -> str:
    """AirNow Fire & Smoke Map. Hash format: #<zoom>/<lat>/<lon>"""
    return f"https://fire.airnow.gov/#{zoom}/{lat:.4f}/{lon:.4f}"


def google_maps_url(lat: float, lon: float) -> str:
    return f"https://www.google.com/maps/search/?api=1&query={lat},{lon}"


def _mapbox_static_url(
    lat: float,
    lon: float,
    zoom: int,
    w: int,
    h: int,
    token: str,
    style: str = "satellite-streets-v12",
    color: str = "d7263d",
) -> str:
    """Mapbox Static Images API: a satellite minimap with a pin at (lat, lon).

    Note Mapbox uses lon,lat order. The @2x suffix requests a retina (crisp) image.
    """
    marker = f"pin-l+{color}({lon:.5f},{lat:.5f})"
    return (
        f"https://api.mapbox.com/styles/v1/mapbox/{style}/static/"
        f"{marker}/{lon:.5f},{lat:.5f},{zoom}/{w}x{h}@2x"
        f"?access_token={token}"
    )


def static_map_url(
    lat: float,
    lon: float,
    *,
    provider: str = "none",
    key: str = "",
    zoom: int = DEFAULT_STATIC_ZOOM,
    size: tuple[int, int] = DEFAULT_STATIC_SIZE,
    style: str = "",
    color: str = "d7263d",
) -> str | None:
    """A public, directly-fetchable static map image URL with a marker at (lat, lon).

    Returns None when no usable provider is configured (caller omits the embed image),
    so a missing key or provider="none" fails soft to today's text-only behavior.
    """
    p = (provider or "none").strip().lower()
    if p in ("", "none", "off"):
        return None
    if p == "mapbox":
        if not key:
            return None
        w, h = size
        return _mapbox_static_url(lat, lon, zoom, w, h, key, style or "satellite-streets-v12", color)
    return None

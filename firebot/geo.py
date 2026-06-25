"""Geometry helpers.

The alert area is a square (bounding box). ``bbox_from_center_half_extent`` turns a
center point + half-extent (miles) into a ``BBox``. ``haversine_miles`` is used only
for the optional "hotspot near an existing incident" suppression and for tests — it is
NOT used to trim the square into a circle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EARTH_RADIUS_MILES = 3958.7613
MILES_PER_DEG_LAT = 69.0  # close enough for bbox sizing


@dataclass(frozen=True)
class BBox:
    west: float
    south: float
    east: float
    north: float

    def as_envelope(self) -> str:
        """ArcGIS/FIRMS order: west,south,east,north."""
        return f"{self.west},{self.south},{self.east},{self.north}"

    def contains(self, lat: float, lon: float) -> bool:
        return self.south <= lat <= self.north and self.west <= lon <= self.east


def bbox_from_center_half_extent(lat: float, lon: float, half_miles: float) -> BBox:
    """Square centered on (lat, lon) extending ``half_miles`` to each edge."""
    dlat = half_miles / MILES_PER_DEG_LAT
    miles_per_deg_lon = MILES_PER_DEG_LAT * math.cos(math.radians(lat))
    # Guard against division by ~0 near the poles.
    dlon = half_miles / miles_per_deg_lon if miles_per_deg_lon > 1e-6 else 180.0
    return BBox(
        west=lon - dlon,
        south=max(lat - dlat, -90.0),
        east=lon + dlon,
        north=min(lat + dlat, 90.0),
    )


def haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in miles between two lat/lon points."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


_COMPASS_16 = [
    "N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
    "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW",
]


def initial_bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing in degrees (0-360) from point 1 toward point 2."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def compass_point(bearing: float) -> str:
    """Bearing in degrees -> 16-point compass label (N, NNE, NE, ...)."""
    return _COMPASS_16[int((bearing % 360 + 11.25) % 360 // 22.5)]


def offset_description(center_lat: float, center_lon: float, lat: float, lon: float, label: str) -> str:
    """e.g. '142 mi NW of Grand Junction' (distance + direction FROM center TO point)."""
    dist = haversine_miles(center_lat, center_lon, lat, lon)
    point = compass_point(initial_bearing(center_lat, center_lon, lat, lon))
    if dist < 1:
        return f"at {label}"
    return f"{dist:.0f} mi {point} of {label}"

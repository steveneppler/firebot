"""Spatial clustering of FIRMS hotspots into fires.

A single large fire is detected as many adjacent VIIRS pixels. Rounding-based dedupe
only collapses pixels in the same ~0.7mi cell, so a big fire still yields many alerts.
This groups detections that are within ``radius_miles`` of each other (transitively, via
union-find) into one ``Cluster`` so we post one alert per fire.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from .geo import MILES_PER_DEG_LAT, haversine_miles
from .sources.firms import Hotspot


@dataclass
class Cluster:
    members: list[Hotspot]

    @cached_property
    def representative(self) -> Hotspot:
        """Hottest detection — used for the map link and headline location."""
        return max(self.members, key=lambda h: (h.frp or 0.0))

    @property
    def count(self) -> int:
        return len(self.members)

    @property
    def max_frp(self) -> float | None:
        frps = [h.frp for h in self.members if h.frp is not None]
        return max(frps) if frps else None

    @property
    def total_frp(self) -> float | None:
        frps = [h.frp for h in self.members if h.frp is not None]
        return sum(frps) if frps else None

    @property
    def latest_acq(self):
        dts = [h.acq_dt for h in self.members if h.acq_dt is not None]
        return max(dts) if dts else None

    @property
    def span_miles(self) -> float:
        """Rough fire extent: max distance between the representative and any member."""
        r = self.representative
        return max((haversine_miles(r.lat, r.lon, m.lat, m.lon) for m in self.members), default=0.0)

    @property
    def member_keys(self) -> list[str]:
        return [m.key for m in self.members]


def cluster_hotspots(hotspots: list[Hotspot], radius_miles: float) -> list[Cluster]:
    """Group hotspots within ``radius_miles`` of each other (connected components).

    radius_miles <= 0 disables clustering (every hotspot is its own cluster).
    """
    n = len(hotspots)
    if n == 0:
        return []
    if radius_miles <= 0:
        return [Cluster([h]) for h in hotspots]

    # Sort by latitude so the pairwise scan can stop early: once a candidate's
    # latitude gap alone exceeds the radius, every later candidate is too far too.
    # Grouping is unaffected (connected components don't depend on visit order).
    order = sorted(range(n), key=lambda i: hotspots[i].lat)
    max_dlat_deg = radius_miles / MILES_PER_DEG_LAT

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for a in range(n):
        i = order[a]
        for b in range(a + 1, n):
            j = order[b]
            if hotspots[j].lat - hotspots[i].lat > max_dlat_deg:
                break
            if haversine_miles(hotspots[i].lat, hotspots[i].lon, hotspots[j].lat, hotspots[j].lon) <= radius_miles:
                union(i, j)

    groups: dict[int, list[Hotspot]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(hotspots[i])
    return [Cluster(members=g) for g in groups.values()]

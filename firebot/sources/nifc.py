"""NIFC WFIGS — Wildland Fire Incident Locations (official named incidents).

Public, token-free ArcGIS REST FeatureServer. Returns confirmed incidents with name,
size, containment, cause, discovery time and location. We query with a bounding-box
envelope so the server only returns points inside our square.

Docs / dataset: https://data-nifc.opendata.arcgis.com/  (Wildland Fire Incident Locations)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from ..geo import BBox

NIFC_URL = (
    "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
    "WFIGS_Incident_Locations_Current/FeatureServer/0/query"
)

# Fields we read back (keeps payloads small and avoids invalid-field errors).
_OUT_FIELDS = ",".join([
    "IrwinID",
    "UniqueFireIdentifier",
    "IncidentName",
    "IncidentTypeCategory",
    "IncidentSize",
    "DiscoveryAcres",
    "PercentContained",
    "FireCause",
    "FireDiscoveryDateTime",
    "FireOutDateTime",
    "ContainmentDateTime",
    "POOState",
    "POOCounty",
    "GACC",
])


@dataclass
class Incident:
    key: str            # stable dedupe key (IrwinID or UniqueFireIdentifier)
    name: str
    type_category: str  # WF, RX, CX, ...
    lat: float
    lon: float
    acres: float | None
    percent_contained: float | None
    cause: str | None
    discovered: datetime | None
    state: str | None
    county: str | None
    out_or_contained: bool = False


def _epoch_ms_to_dt(value) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (ValueError, TypeError, OSError):
        return None


def _to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (ValueError, TypeError):
        return None


def query_nifc(bbox: BBox, incident_types: list[str], *, timeout: int = 30) -> list[Incident]:
    """Fetch incidents inside ``bbox``, filtered to the given IncidentTypeCategory values."""
    where = "1=1"
    if incident_types:
        quoted = ",".join(f"'{t}'" for t in incident_types)
        where = f"IncidentTypeCategory IN ({quoted})"

    params = {
        "where": where,
        "geometry": bbox.as_envelope(),
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": _OUT_FIELDS,
        "returnGeometry": "true",
        "f": "json",
    }
    resp = requests.get(NIFC_URL, params=params, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if "error" in data:
        raise RuntimeError(f"NIFC query error: {data['error']}")

    incidents: list[Incident] = []
    for feat in data.get("features", []):
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry") or {}
        lat = geom.get("y")
        lon = geom.get("x")
        if lat is None or lon is None:
            continue
        key = (attrs.get("IrwinID") or attrs.get("UniqueFireIdentifier") or "").strip()
        if not key:
            # No stable id -> fall back to name+coords so we still dedupe.
            key = f"{attrs.get('IncidentName','?')}|{round(lat,3)}|{round(lon,3)}"
        acres = _to_float(attrs.get("IncidentSize"))
        if acres is None:
            acres = _to_float(attrs.get("DiscoveryAcres"))
        pct = _to_float(attrs.get("PercentContained"))
        out_or_contained = bool(
            attrs.get("FireOutDateTime")
            or attrs.get("ContainmentDateTime")
            or (pct is not None and pct >= 100)
        )
        incidents.append(
            Incident(
                key=key,
                name=(attrs.get("IncidentName") or "Unnamed incident").strip(),
                type_category=(attrs.get("IncidentTypeCategory") or "").strip(),
                lat=float(lat),
                lon=float(lon),
                acres=acres,
                percent_contained=pct,
                cause=(attrs.get("FireCause") or None),
                discovered=_epoch_ms_to_dt(attrs.get("FireDiscoveryDateTime")),
                state=(attrs.get("POOState") or None),
                county=(attrs.get("POOCounty") or None),
                out_or_contained=out_or_contained,
            )
        )
    return incidents

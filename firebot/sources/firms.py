"""NASA FIRMS — Area API (satellite-detected thermal hotspots).

Near-real-time active-fire detections (VIIRS/MODIS). Earliest warning and covers
remote areas, but noisy (ag/prescribed burns, industrial heat). We apply confidence
and FRP filters to cut the noise.

Endpoint:
  https://firms.modaps.eosdis.nasa.gov/api/area/csv/{MAP_KEY}/{SOURCE}/{west,south,east,north}/{DAY_RANGE}
Free MAP_KEY: https://firms.modaps.eosdis.nasa.gov/api/map_key/
Limit: 5000 transactions / 10 min.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime, timezone

from ..geo import BBox
from ..http import get

FIRMS_BASE = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"

# VIIRS reports confidence as low/nominal/high; MODIS as 0-100.
_VIIRS_CONF_RANK = {"l": 0, "n": 1, "h": 2}
_VIIRS_CONF_LEVEL = {"low": 0, "nominal": 1, "high": 2}

# FIRMS satellite codes -> readable names.
_SATELLITE_NAMES = {
    "N": "Suomi NPP", "NPP": "Suomi NPP",
    "1": "NOAA-20", "N20": "NOAA-20",
    "2": "NOAA-21", "N21": "NOAA-21",
    "T": "Terra (MODIS)", "A": "Aqua (MODIS)",
}


def satellite_name(code: str) -> str:
    """Translate a FIRMS satellite code (e.g. 'N') to a readable name (e.g. 'Suomi NPP')."""
    code = (code or "").strip()
    return _SATELLITE_NAMES.get(code.upper(), code or "unknown")


@dataclass
class Hotspot:
    key: str
    lat: float
    lon: float
    acq_dt: datetime | None
    confidence: str       # raw value as reported (l/n/h or 0-100)
    frp: float | None     # fire radiative power (MW)
    satellite: str
    daynight: str


def _parse_acq(date_str: str, time_str: str) -> datetime | None:
    # acq_date = YYYY-MM-DD, acq_time = HHMM (UTC)
    if not date_str:
        return None
    try:
        t = (time_str or "0").zfill(4)
        return datetime.strptime(f"{date_str} {t}", "%Y-%m-%d %H%M").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _confidence_ok(raw: str, *, viirs_min_rank: int, min_pct: int) -> bool:
    raw = (raw or "").strip().lower()
    if raw in _VIIRS_CONF_RANK:  # VIIRS l/n/h
        return _VIIRS_CONF_RANK[raw] >= viirs_min_rank
    try:  # MODIS numeric 0-100
        return float(raw) >= min_pct
    except ValueError:
        return True  # unknown format: don't drop


def query_firms(
    bbox: BBox,
    map_key: str,
    source: str,
    day_range: int,
    *,
    viirs_min_confidence: str = "nominal",
    min_confidence_pct: int = 0,
    frp_min: float = 0.0,
    timeout: int = 30,
) -> list[Hotspot]:
    """Fetch hotspots in ``bbox`` and apply noise filters."""
    viirs_min_rank = _VIIRS_CONF_LEVEL.get(viirs_min_confidence.strip().lower(), 1)
    if not map_key:
        raise RuntimeError("FIRMS_MAP_KEY is not set; cannot query FIRMS.")

    url = f"{FIRMS_BASE}/{map_key}/{source}/{bbox.as_envelope()}/{day_range}"
    resp = get(url, timeout=timeout)
    resp.raise_for_status()
    text = resp.text.strip()

    # FIRMS returns a plain-text error (not CSV) for bad keys / invalid params.
    if not text or text.lower().startswith(("invalid", "error")) or "," not in text.splitlines()[0]:
        raise RuntimeError(f"FIRMS returned an unexpected response: {text[:200]!r}")

    hotspots: list[Hotspot] = []
    for row in csv.DictReader(io.StringIO(text)):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
        except (KeyError, ValueError):
            continue

        confidence = row.get("confidence", "")
        if not _confidence_ok(confidence, viirs_min_rank=viirs_min_rank, min_pct=min_confidence_pct):
            continue

        frp = None
        try:
            frp = float(row["frp"]) if row.get("frp") not in (None, "") else None
        except ValueError:
            frp = None
        if frp_min > 0 and (frp is None or frp < frp_min):
            continue

        acq_date = row.get("acq_date", "")
        acq_time = row.get("acq_time", "")
        # Round coords so repeat detections of the same pixel across a day collapse to one alert.
        key = f"{round(lat, 2)}|{round(lon, 2)}|{acq_date}"
        hotspots.append(
            Hotspot(
                key=key,
                lat=lat,
                lon=lon,
                acq_dt=_parse_acq(acq_date, acq_time),
                confidence=confidence,
                frp=frp,
                satellite=row.get("satellite", ""),
                daynight=row.get("daynight", ""),
            )
        )
    return hotspots

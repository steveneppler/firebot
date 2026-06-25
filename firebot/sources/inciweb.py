"""InciWeb incident-page lookup.

InciWeb (https://inciweb.wildfire.gov) is the official incident information system,
but only larger/active fires get a page, and the page slug uses InciWeb's own unit
codes that aren't derivable from IRWIN data. So we fetch InciWeb's RSS feed once per
run and match our incidents by normalized name (+ state to disambiguate). When a fire
has no InciWeb page, ``incident_info_url`` falls back to a Google web search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus

import requests

RSS_URL = "https://inciweb.wildfire.gov/incidents/rss.xml"

_STATE_NAME_TO_ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR",
    "California": "CA", "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID",
    "Illinois": "IL", "Indiana": "IN", "Iowa": "IA", "Kansas": "KS",
    "Kentucky": "KY", "Louisiana": "LA", "Maine": "ME", "Maryland": "MD",
    "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN", "Mississippi": "MS",
    "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK",
    "Oregon": "OR", "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC",
    "South Dakota": "SD", "Tennessee": "TN", "Texas": "TX", "Utah": "UT",
    "Vermont": "VT", "Virginia": "VA", "Washington": "WA", "West Virginia": "WV",
    "Wisconsin": "WI", "Wyoming": "WY",
}
_ABBR_TO_STATE_NAME = {v: k for k, v in _STATE_NAME_TO_ABBR.items()}


def _norm_name(name: str) -> str:
    """Normalize an incident name for matching: drop trailing 'Fire', lowercase."""
    return re.sub(r"\s+fire$", "", (name or "").strip(), flags=re.I).lower()


def _norm_rss_title(title: str) -> str:
    """RSS titles look like 'NMGNF Bear Fire' — drop the leading unit code + trailing 'Fire'."""
    toks = (title or "").strip().split()
    if toks and re.fullmatch(r"[A-Z]{2,6}", toks[0]):
        toks = toks[1:]
    return _norm_name(" ".join(toks))


def _state_abbr(poo_state: str | None) -> str:
    """Our POOState is like 'US-CO' -> 'CO'."""
    if not poo_state:
        return ""
    return poo_state.strip().split("-")[-1].upper()


@dataclass
class _Entry:
    name_norm: str
    state_abbr: str
    url: str


def _parse_rss(xml: str) -> list[_Entry]:
    entries: list[_Entry] = []
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        t = re.search(r"<title>(.*?)</title>", block, re.S)
        l = re.search(r"<link>(.*?)</link>", block, re.S)
        d = re.search(r"<description>(.*?)</description>", block, re.S)
        if not (t and l):
            continue
        state_abbr = ""
        if d:
            sm = re.search(r"State:\s*([A-Za-z .]+?)\s*(?:---|<|$)", d.group(1))
            if sm:
                state_abbr = _STATE_NAME_TO_ABBR.get(sm.group(1).strip().title(), "")
        url = l.group(1).strip().replace("http://", "https://")
        entries.append(_Entry(_norm_rss_title(t.group(1)), state_abbr, url))
    return entries


class InciWebIndex:
    def __init__(self, entries: list[_Entry]):
        self.entries = entries

    @classmethod
    def fetch(cls, *, timeout: int = 30) -> "InciWebIndex":
        try:
            resp = requests.get(RSS_URL, timeout=timeout)
            resp.raise_for_status()
            return cls(_parse_rss(resp.text))
        except Exception:
            return cls([])  # network/parse failure -> everything falls back to web search

    def find(self, name: str, state_abbr: str) -> str | None:
        n = _norm_name(name)
        matches = [e for e in self.entries if e.name_norm == n]
        if not matches:
            return None
        if state_abbr:
            in_state = [e for e in matches if e.state_abbr == state_abbr]
            if in_state:
                return in_state[0].url
        # Only trust a stateless match when it's unambiguous (avoid wrong-fire links).
        return matches[0].url if len(matches) == 1 else None


def web_search_url(name: str, state_abbr: str = "") -> str:
    q = f'"{name} Fire"'
    full = _ABBR_TO_STATE_NAME.get(state_abbr)
    if full:
        q += f" {full}"
    q += " wildfire"
    return "https://www.google.com/search?q=" + quote_plus(q)


def incident_info_url(index: InciWebIndex | None, name: str, poo_state: str | None) -> str:
    """InciWeb page if the fire has one, else a Google search for the fire."""
    abbr = _state_abbr(poo_state)
    if index is not None:
        url = index.find(name, abbr)
        if url:
            return url
    return web_search_url(name, abbr)

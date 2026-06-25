"""Tests for run-collection logic (within-run hotspot dedupe + suppression)."""

import unittest
from unittest import mock

from firebot import main
from firebot.config import Config
from firebot.sources.firms import Hotspot
from firebot.sources.nifc import Incident
from firebot.state import State


def hs(lat, lon, frp, date="2026-06-23"):
    key = f"{round(lat, 2)}|{round(lon, 2)}|{date}"
    return Hotspot(key=key, lat=lat, lon=lon, acq_dt=None, confidence="h",
                   frp=frp, satellite="N", daynight="D")


def cfg():
    c = Config(discord_webhook_url="x", firms_map_key="x")
    c.enable_nifc = False
    c.firms_suppress_near_incident_miles = 0
    return c


class CollectTests(unittest.TestCase):
    def test_within_run_dedupe_keeps_highest_frp(self):
        hotspots = [
            hs(39.101, -108.601, 10),   # same key as next
            hs(39.104, -108.604, 99),   # -> 39.1|-108.6 (highest FRP, kept)
            hs(40.000, -107.000, 30),   # distinct key, ~88 mi away -> separate cluster
        ]
        with mock.patch.object(main, "query_firms", return_value=hotspots), \
             mock.patch.object(main, "query_nifc", return_value=[]):
            _new, _upd, clusters = main._collect_new_items(cfg(), State(":mem:"))
        self.assertEqual(len(clusters), 2)
        rep = next(c.representative for c in clusters
                   if c.representative.key == "39.1|-108.6|2026-06-23")
        self.assertEqual(rep.frp, 99)

    def test_nearby_detections_form_one_cluster(self):
        # A blob: three detections all within a couple miles -> one fire alert.
        hotspots = [hs(39.10, -108.60, 50), hs(39.11, -108.61, 80), hs(39.12, -108.60, 30)]
        with mock.patch.object(main, "query_firms", return_value=hotspots), \
             mock.patch.object(main, "query_nifc", return_value=[]):
            _new, _upd, clusters = main._collect_new_items(cfg(), State(":mem:"))
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].count, 3)
        self.assertEqual(clusters[0].representative.frp, 80)  # hottest is representative

    def test_suppress_near_incident(self):
        c = cfg()
        c.firms_suppress_near_incident_miles = 5
        incident = Incident(key="i", name="X", type_category="WF", lat=39.10, lon=-108.60,
                            acres=10, percent_contained=0, cause=None, discovered=None,
                            state="US-CO", county="Mesa")
        hotspots = [hs(39.101, -108.601, 50), hs(45.0, -110.0, 50)]  # first is ~near incident
        with mock.patch.object(main, "query_firms", return_value=hotspots), \
             mock.patch.object(main, "query_nifc", return_value=[incident]):
            c.enable_nifc = True
            _new, _upd, clusters = main._collect_new_items(c, State(":mem:"))
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].representative.lat, 45.0)  # near-incident hotspot suppressed


if __name__ == "__main__":
    unittest.main()

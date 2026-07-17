"""Tests for run-collection logic (within-run hotspot dedupe + suppression,
relevance radius filtering, and the new-fire size/growth gate)."""

import unittest
from unittest import mock

from firebot import main
from firebot.config import Config
from firebot.sources.firms import Hotspot
from firebot.sources.nifc import Incident
from firebot.state import State

GJ_LAT, GJ_LON = 39.0639, -108.5506


def hs(lat, lon, frp, date="2026-06-23"):
    key = f"{round(lat, 2)}|{round(lon, 2)}|{date}"
    return Hotspot(key=key, lat=lat, lon=lon, acq_dt=None, confidence="h",
                   frp=frp, satellite="N", daynight="D")


def incident(lat, lon, acres, key="i"):
    return Incident(key=key, name="X", type_category="WF", lat=lat, lon=lon,
                    acres=acres, percent_contained=0, cause=None, discovered=None,
                    state="US-CO", county="Mesa")


def cfg():
    c = Config(discord_webhook_url="x", firms_map_key="x")
    c.enable_nifc = False
    c.firms_suppress_near_incident_miles = 0
    # These tests predate relevance/cluster gating; disable both so they stay focused
    # on dedupe/clustering/suppression rather than the new filters.
    c.relevance_radius_miles = 0
    c.firms_min_cluster_detections = 1
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
            _new, _upd, clusters, _pend = main._collect_new_items(cfg(), State(":mem:"))
        self.assertEqual(len(clusters), 2)
        rep = next(c.representative for c in clusters
                   if c.representative.key == "39.1|-108.6|2026-06-23")
        self.assertEqual(rep.frp, 99)

    def test_nearby_detections_form_one_cluster(self):
        # A blob: three detections all within a couple miles -> one fire alert.
        hotspots = [hs(39.10, -108.60, 50), hs(39.11, -108.61, 80), hs(39.12, -108.60, 30)]
        with mock.patch.object(main, "query_firms", return_value=hotspots), \
             mock.patch.object(main, "query_nifc", return_value=[]):
            _new, _upd, clusters, _pend = main._collect_new_items(cfg(), State(":mem:"))
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].count, 3)
        self.assertEqual(clusters[0].representative.frp, 80)  # hottest is representative

    def test_suppress_near_incident(self):
        c = cfg()
        c.firms_suppress_near_incident_miles = 5
        inc = incident(39.10, -108.60, 10)
        hotspots = [hs(39.101, -108.601, 50), hs(39.90, -108.60, 50)]  # first ~near incident
        with mock.patch.object(main, "query_firms", return_value=hotspots), \
             mock.patch.object(main, "query_nifc", return_value=[inc]):
            c.enable_nifc = True
            _new, _upd, clusters, _pend = main._collect_new_items(c, State(":mem:"))
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].representative.lat, 39.90)  # near-incident hotspot suppressed

    def test_large_fire_suppresses_hotspots_beyond_base_radius(self):
        # A 50k-acre fire's footprint (~5 mi) + buffer suppresses a hotspot ~6 mi out
        # that the fixed 5-mi radius would have missed.
        c = cfg()
        c.firms_suppress_near_incident_miles = 5
        inc = incident(GJ_LAT, GJ_LON, 50_000)
        far = hs(GJ_LAT + 0.087, GJ_LON, 50)  # ~6 mi north of the incident center
        with mock.patch.object(main, "query_firms", return_value=[far]), \
             mock.patch.object(main, "query_nifc", return_value=[inc]):
            c.enable_nifc = True
            _new, _upd, clusters, _pend = main._collect_new_items(c, State(":mem:"))
        self.assertEqual(clusters, [])

    def test_weak_single_hotspot_gated_out(self):
        c = cfg()
        c.firms_min_cluster_detections = 2  # re-enable the single-pixel gate
        weak = hs(39.10, -108.60, 25)  # lone 25 MW pixel < 50 MW single-detection floor
        with mock.patch.object(main, "query_firms", return_value=[weak]), \
             mock.patch.object(main, "query_nifc", return_value=[]):
            _new, _upd, clusters, _pend = main._collect_new_items(c, State(":mem:"))
        self.assertEqual(clusters, [])

    def test_far_incident_excluded_by_relevance(self):
        c = cfg()
        c.enable_nifc = True
        c.relevance_radius_miles = 100
        near = incident(GJ_LAT, GJ_LON, 500, key="near")
        far = incident(39.7392, -104.9903, 500, key="far")  # Denver ~196 mi
        with mock.patch.object(main, "query_firms", return_value=[]), \
             mock.patch.object(main, "query_nifc", return_value=[near, far]):
            new, _upd, _clusters, _pend = main._collect_new_items(c, State(":mem:"))
        self.assertEqual([i.key for i in new], ["near"])

    def test_small_new_fire_is_pending_not_alerted(self):
        c = cfg()
        c.enable_nifc = True
        small = incident(GJ_LAT, GJ_LON, 10, key="small")
        with mock.patch.object(main, "query_firms", return_value=[]), \
             mock.patch.object(main, "query_nifc", return_value=[small]):
            new, _upd, _clusters, pending = main._collect_new_items(c, State(":mem:"))
        self.assertEqual(new, [])
        self.assertEqual([i.key for i in pending], ["small"])


if __name__ == "__main__":
    unittest.main()

"""Tests for relevance/size gating: new-fire alert gate, hotspot cluster gate,
radius relevance filter, and size-scaled incident suppression radius."""

import unittest
from datetime import datetime, timedelta

from firebot.cluster import Cluster
from firebot.config import Config
from firebot.main import (
    _cluster_alertable,
    _record_pending,
    _relevant,
    _should_alert_new,
    _suppress_radius_miles,
)
from firebot.sources.firms import Hotspot
from firebot.sources.nifc import Incident
from firebot.state import State

GJ_LAT, GJ_LON = 39.0639, -108.5506


def cfg():
    return Config(discord_webhook_url="x", firms_map_key="x")


def inc(acres=None, lat=GJ_LAT, lon=GJ_LON):
    return Incident(
        key="X", name="Test", type_category="WF", lat=lat, lon=lon,
        acres=acres, percent_contained=None, cause=None, discovered=None,
        state="US-CO", county="Mesa", out_or_contained=False,
    )


def hs(lat, lon, frp):
    return Hotspot(key=f"{lat}|{lon}|d", lat=lat, lon=lon, acq_dt=None,
                   confidence="h", frp=frp, satellite="N", daynight="D")


class RelevanceRadiusTests(unittest.TestCase):
    def test_point_at_center_is_relevant(self):
        self.assertTrue(_relevant(cfg(), GJ_LAT, GJ_LON))

    def test_far_point_excluded(self):
        # ~196 mi away (Denver) is outside a 100 mi radius.
        self.assertFalse(_relevant(cfg(), 39.7392, -104.9903))

    def test_ouray_included(self):
        # Ouray, CO ~90 mi south -> inside 100 mi.
        self.assertTrue(_relevant(cfg(), 38.0228, -107.6714))

    def test_radius_zero_disables_filter(self):
        c = cfg()
        c.relevance_radius_miles = 0
        self.assertTrue(_relevant(c, 39.7392, -104.9903))


class NewFireGateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()
        self.now = datetime(2026, 7, 16, 12, 0, 0)

    def test_large_fire_alerts_on_first_sight(self):
        self.assertTrue(_should_alert_new(inc(acres=150), None, self.cfg, self.now))

    def test_small_fire_does_not_alert_on_first_sight(self):
        self.assertFalse(_should_alert_new(inc(acres=10), None, self.cfg, self.now))

    def test_unknown_size_does_not_alert(self):
        self.assertFalse(_should_alert_new(inc(acres=None), None, self.cfg, self.now))

    def test_pending_fire_growing_fast_alerts(self):
        # Seen 12h ago at 10 acres, now 60 -> +50 acres in 0.5 day = 100 ac/day.
        meta = {"acres": 10.0, "seen_ts": (self.now - timedelta(hours=12)).isoformat()}
        self.assertTrue(_should_alert_new(inc(acres=60), meta, self.cfg, self.now))

    def test_pending_fire_growing_slowly_stays_silent(self):
        # Seen 2 days ago at 10 acres, now 40 -> +30 acres over 2 days = 15 ac/day.
        meta = {"acres": 10.0, "seen_ts": (self.now - timedelta(days=2)).isoformat()}
        self.assertFalse(_should_alert_new(inc(acres=40), meta, self.cfg, self.now))

    def test_pending_fast_rate_but_below_growth_floor_stays_silent(self):
        # Seen 10 min ago at 5 acres, now 18 -> +13 acres, huge rate but < 20-acre floor.
        meta = {"acres": 5.0, "seen_ts": (self.now - timedelta(minutes=10)).isoformat()}
        self.assertFalse(_should_alert_new(inc(acres=18), meta, self.cfg, self.now))

    def test_pending_fire_reaching_min_acres_alerts(self):
        meta = {"acres": 10.0, "seen_ts": (self.now - timedelta(days=5)).isoformat()}
        self.assertTrue(_should_alert_new(inc(acres=120), meta, self.cfg, self.now))

    def test_growth_gate_survives_non_string_seen_ts(self):
        # A corrupt state file may hold a non-string seen_ts; fromisoformat raises
        # TypeError there, which must not crash collection.
        meta = {"acres": 10.0, "seen_ts": 12345}
        self.assertFalse(_should_alert_new(inc(acres=40), meta, self.cfg, self.now))


class PendingBaselineTests(unittest.TestCase):
    def test_baseline_established_when_acreage_becomes_known(self):
        st = State(":mem:")
        # First sighting: acreage unknown -> pending with no usable baseline.
        _record_pending(st, [inc(acres=None)])
        self.assertIsNone(st.get("nifc:X")["acres"])
        # Once a real acreage is known, the baseline (acres + seen_ts) is established.
        _record_pending(st, [inc(acres=50)])
        meta = st.get("nifc:X")
        self.assertEqual(meta["acres"], 50)
        self.assertIn("seen_ts", meta)

    def test_known_baseline_not_overwritten(self):
        st = State(":mem:")
        _record_pending(st, [inc(acres=10)])
        first_ts = st.get("nifc:X")["seen_ts"]
        _record_pending(st, [inc(acres=30)])  # grew, but baseline must stay fixed
        meta = st.get("nifc:X")
        self.assertEqual(meta["acres"], 10)
        self.assertEqual(meta["seen_ts"], first_ts)


class HotspotClusterGateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()

    def test_multi_detection_cluster_alerts(self):
        c = Cluster([hs(39.1, -108.6, 25), hs(39.11, -108.61, 30)])
        self.assertTrue(_cluster_alertable(c, self.cfg))

    def test_single_weak_detection_suppressed(self):
        c = Cluster([hs(39.1, -108.6, 25)])  # 1 pixel, 25 MW < 50
        self.assertFalse(_cluster_alertable(c, self.cfg))

    def test_single_hot_detection_alerts(self):
        c = Cluster([hs(39.1, -108.6, 80)])  # 1 pixel but 80 MW >= 50
        self.assertTrue(_cluster_alertable(c, self.cfg))


class SuppressRadiusTests(unittest.TestCase):
    def setUp(self):
        self.cfg = cfg()

    def test_small_or_unknown_fire_uses_floor(self):
        self.assertEqual(_suppress_radius_miles(inc(acres=None), self.cfg), 5.0)
        self.assertEqual(_suppress_radius_miles(inc(acres=10), self.cfg), 5.0)

    def test_large_fire_scales_beyond_floor(self):
        # 50k acres -> ~5 mi footprint + 2 mi buffer = ~7 mi, above the 5 mi floor.
        r = _suppress_radius_miles(inc(acres=50_000), self.cfg)
        self.assertTrue(6.5 <= r <= 7.5, f"got {r:.2f}")


if __name__ == "__main__":
    unittest.main()

"""Tests for incident update-alert change detection."""

import unittest

from firebot.config import Config
from firebot.main import _incident_changes
from firebot.sources.nifc import Incident


def make_incident(acres=None, contained=None, out=False):
    return Incident(
        key="X", name="Test", type_category="WF", lat=39.0, lon=-108.0,
        acres=acres, percent_contained=contained, cause=None, discovered=None,
        state="US-CO", county="Mesa", out_or_contained=out,
    )


def moderate_cfg():
    # Defaults are the "moderate" thresholds: +25% / +100 acres, +/-20 contain pts.
    return Config(discord_webhook_url="x", firms_map_key="x")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = moderate_cfg()

    def test_no_change_no_alert(self):
        meta = {"acres": 500.0, "contained": 30.0, "out": False}
        inc = make_incident(acres=510.0, contained=35.0)  # +2%, +5 pts: below thresholds
        self.assertEqual(_incident_changes(inc, meta, self.cfg), [])

    def test_growth_by_percent(self):
        meta = {"acres": 400.0, "contained": 0.0, "out": False}
        inc = make_incident(acres=520.0, contained=0.0)  # +30%
        lines = _incident_changes(inc, meta, self.cfg)
        self.assertTrue(any("Size" in l for l in lines))

    def test_growth_by_absolute_acres(self):
        meta = {"acres": 5000.0, "contained": 0.0, "out": False}
        inc = make_incident(acres=5150.0, contained=0.0)  # +3% but +150 acres
        lines = _incident_changes(inc, meta, self.cfg)
        self.assertTrue(any("Size" in l for l in lines))

    def test_tiny_fire_percent_growth_suppressed(self):
        # 2 -> 4 acres is +100% but only +2 acres: below the pct floor (10), no alert.
        meta = {"acres": 2.0, "contained": 0.0, "out": False}
        inc = make_incident(acres=4.0, contained=0.0)
        self.assertEqual(_incident_changes(inc, meta, self.cfg), [])

    def test_containment_change(self):
        meta = {"acres": 1000.0, "contained": 10.0, "out": False}
        inc = make_incident(acres=1000.0, contained=40.0)  # +30 pts
        lines = _incident_changes(inc, meta, self.cfg)
        self.assertTrue(any("Contained" in l for l in lines))

    def test_out_transition_once(self):
        meta = {"acres": 1000.0, "contained": 90.0, "out": False}
        inc = make_incident(acres=1000.0, contained=100.0, out=True)
        lines = _incident_changes(inc, meta, self.cfg)
        self.assertTrue(any("out" in l.lower() for l in lines))
        # Once recorded as out, no repeat.
        meta_out = {"acres": 1000.0, "contained": 100.0, "out": True}
        self.assertFalse(any("out" in l.lower() for l in _incident_changes(inc, meta_out, self.cfg)))

    def test_first_size_report(self):
        meta = {"acres": None, "contained": None, "out": False}
        inc = make_incident(acres=250.0)  # first known size, above 100-acre floor
        lines = _incident_changes(inc, meta, self.cfg)
        self.assertTrue(any("Size" in l for l in lines))

    def test_disabled_updates_via_toggle(self):
        cfg = moderate_cfg()
        cfg.update_on_growth = False
        meta = {"acres": 400.0, "contained": 0.0, "out": False}
        inc = make_incident(acres=800.0, contained=0.0)  # +100% but growth disabled
        self.assertEqual(_incident_changes(inc, meta, cfg), [])


if __name__ == "__main__":
    unittest.main()

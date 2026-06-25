"""Tests for embed field construction (distance, links)."""

import unittest

from firebot.cluster import Cluster
from firebot.discord import build_firms_cluster_embed, build_nifc_embed, build_nifc_update_embed
from firebot.sources.firms import Hotspot
from firebot.sources.nifc import Incident

GJ_LAT, GJ_LON = 39.0639, -108.5506


def incident(lat=39.7392, lon=-104.9903):  # ~Denver
    return Incident(key="k", name="Test Fire", type_category="WF", lat=lat, lon=lon,
                    acres=1000, percent_contained=20, cause="Lightning", discovered=None,
                    state="US-CO", county="Mesa")


def _field(embed, name):
    return next((f["value"] for f in embed["fields"] if f["name"] == name), None)


class DiscordTests(unittest.TestCase):
    def test_nifc_has_distance_when_center_given(self):
        e = build_nifc_embed(incident(), 9, "http://x", GJ_LAT, GJ_LON, "Grand Junction")
        self.assertRegex(_field(e, "Distance"), r"^\d+ mi [NSEW]+ of Grand Junction$")

    def test_nifc_omits_distance_without_center(self):
        e = build_nifc_embed(incident(), 9, "http://x")
        self.assertIsNone(_field(e, "Distance"))

    def test_nifc_update_has_distance(self):
        e = build_nifc_update_embed(incident(), ["Size: 1 → 2"], 9, "http://x",
                                    GJ_LAT, GJ_LON, "Grand Junction")
        self.assertRegex(_field(e, "Distance"), r"of Grand Junction$")

    def test_title_links_to_incident_page(self):
        e = build_nifc_embed(incident(), 9, "https://inciweb.example/x")
        self.assertEqual(e["url"], "https://inciweb.example/x")

    def test_firms_distance_in_body_not_title(self):
        hs = Hotspot(key="k", lat=39.7392, lon=-104.9903, acq_dt=None, confidence="h",
                     frp=120.0, satellite="N", daynight="D")
        e = build_firms_cluster_embed(Cluster([hs]), 9, GJ_LAT, GJ_LON, "Grand Junction")
        # Distance is a field, and the title no longer contains the offset text.
        self.assertRegex(_field(e, "Distance"), r"of Grand Junction$")
        self.assertNotIn("of Grand Junction", e["title"])


if __name__ == "__main__":
    unittest.main()

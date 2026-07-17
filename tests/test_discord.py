"""Tests for embed field construction (distance, links) and webhook delivery."""

import unittest
from unittest import mock

import firebot.discord as discord
from firebot.cluster import Cluster
from firebot.discord import (
    _retry_after_seconds,
    build_firms_cluster_embed,
    build_nifc_embed,
    build_nifc_update_embed,
    post_embeds,
)
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


class FakeResp:
    def __init__(self, status_code=204, body=None):
        self.status_code = status_code
        self._body = body

    def json(self):
        if self._body is None:
            raise ValueError("no JSON")
        return self._body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class PostEmbedsTests(unittest.TestCase):
    def test_retry_after_parses_discord_body(self):
        self.assertEqual(_retry_after_seconds(FakeResp(429, {"retry_after": 2.5})), 2.5)

    def test_retry_after_survives_non_json_429(self):
        # A proxy can return an HTML 429; the fallback wait must not raise.
        self.assertEqual(_retry_after_seconds(FakeResp(429)), 1.0)

    def test_429_is_retried_once(self):
        responses = [FakeResp(429, {"retry_after": 0}), FakeResp(204)]
        with mock.patch.object(discord.session, "post", side_effect=responses) as post, \
             mock.patch.object(discord.time, "sleep"):
            post_embeds("https://hook.example", [{"title": "x"}])
        self.assertEqual(post.call_count, 2)


if __name__ == "__main__":
    unittest.main()

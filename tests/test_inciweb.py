"""Tests for InciWeb feed parsing, matching, and web-search fallback."""

import unittest

from firebot.sources.inciweb import InciWebIndex, _parse_rss, incident_info_url, web_search_url

SAMPLE_RSS = """<?xml version="1.0"?>
<rss version="2.0"><channel>
<item>
  <title>NMGNF Bear Fire</title>
  <link>http://inciweb.wildfire.gov/incident-information/nmgnf-bear-fire</link>
  <description>Last updated: 2026-06-23 --- State: New Mexico --- Coordinates:</description>
</item>
<item>
  <title>AZTNF Bear Fire</title>
  <link>http://inciweb.wildfire.gov/incident-information/aztnf-bear-fire</link>
  <description>State: Arizona ---</description>
</item>
<item>
  <title>COGJD South Fork Fire</title>
  <link>http://inciweb.wildfire.gov/incident-information/cogjd-south-fork-fire</link>
  <description>State: Colorado ---</description>
</item>
</channel></rss>"""


class InciWebTests(unittest.TestCase):
    def setUp(self):
        self.index = InciWebIndex(_parse_rss(SAMPLE_RSS))

    def test_parse_count_and_https(self):
        self.assertEqual(len(self.index.entries), 3)
        self.assertTrue(all(e.url.startswith("https://") for e in self.index.entries))

    def test_match_by_name_and_state_disambiguates(self):
        # Two "Bear" fires -> state picks the right one.
        self.assertEqual(self.index.find("Bear", "NM"),
                         "https://inciweb.wildfire.gov/incident-information/nmgnf-bear-fire")
        self.assertEqual(self.index.find("Bear", "AZ"),
                         "https://inciweb.wildfire.gov/incident-information/aztnf-bear-fire")

    def test_ambiguous_without_state_returns_none(self):
        # "Bear" matches two entries and no state given -> refuse to guess.
        self.assertIsNone(self.index.find("Bear", ""))

    def test_unique_match(self):
        self.assertEqual(self.index.find("South Fork", "CO"),
                         "https://inciweb.wildfire.gov/incident-information/cogjd-south-fork-fire")

    def test_no_match_returns_none(self):
        self.assertIsNone(self.index.find("Rapid Creek", "CO"))

    def test_incident_info_url_falls_back_to_web_search(self):
        url = incident_info_url(self.index, "Rapid Creek", "US-CO")
        self.assertIn("google.com/search", url)
        self.assertIn("Colorado", url)

    def test_incident_info_url_uses_inciweb_when_matched(self):
        url = incident_info_url(self.index, "South Fork", "US-CO")
        self.assertIn("inciweb.wildfire.gov/incident-information", url)

    def test_web_search_url_encodes_query(self):
        url = web_search_url("Rapid Creek", "CO")
        self.assertTrue(url.startswith("https://www.google.com/search?q="))
        self.assertIn("wildfire", url)


if __name__ == "__main__":
    unittest.main()

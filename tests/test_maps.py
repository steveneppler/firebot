"""Tests for map deep-link builders."""

import unittest

from firebot.maps import airnow_map_url, firms_map_url, google_maps_url

LAT, LON = 39.0639, -108.5506


class MapsTests(unittest.TestCase):
    def test_firms_format(self):
        url = firms_map_url(LAT, LON, zoom=9)
        # #d:24hrs;@<lon>,<lat>,<zoom>z
        self.assertEqual(url, "https://firms.modaps.eosdis.nasa.gov/map/#d:24hrs;@-108.5506,39.0639,9z")

    def test_airnow_format(self):
        url = airnow_map_url(LAT, LON, zoom=9)
        # #<zoom>/<lat>/<lon>
        self.assertEqual(url, "https://fire.airnow.gov/#9/39.0639/-108.5506")

    def test_zoom_is_applied(self):
        self.assertIn("#12/", airnow_map_url(LAT, LON, zoom=12))
        self.assertIn(",12z", firms_map_url(LAT, LON, zoom=12))

    def test_google_still_available(self):
        self.assertIn("google.com/maps", google_maps_url(LAT, LON))


if __name__ == "__main__":
    unittest.main()

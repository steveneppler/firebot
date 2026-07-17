"""Geo sanity checks. Run: python -m pytest  (or python -m unittest)."""

import math
import unittest

from firebot.geo import (
    bbox_from_center_half_extent,
    compass_point,
    haversine_miles,
    incident_footprint_radius_miles,
    initial_bearing,
    offset_description,
)

GJ_LAT, GJ_LON = 39.0639, -108.5506


class GeoTests(unittest.TestCase):
    def test_haversine_known_distance(self):
        # Grand Junction -> Denver is ~196 miles great-circle (~250 mi by road).
        d = haversine_miles(GJ_LAT, GJ_LON, 39.7392, -104.9903)
        self.assertTrue(188 <= d <= 205, f"got {d:.1f} mi")

    def test_bbox_edges_are_half_extent_from_center(self):
        half = 300.0
        bb = bbox_from_center_half_extent(GJ_LAT, GJ_LON, half)
        # North/south edges along the center meridian.
        north = haversine_miles(GJ_LAT, GJ_LON, bb.north, GJ_LON)
        south = haversine_miles(GJ_LAT, GJ_LON, bb.south, GJ_LON)
        # East/west edges along the center parallel.
        east = haversine_miles(GJ_LAT, GJ_LON, GJ_LAT, bb.east)
        west = haversine_miles(GJ_LAT, GJ_LON, GJ_LAT, bb.west)
        for name, val in [("north", north), ("south", south), ("east", east), ("west", west)]:
            self.assertTrue(abs(val - half) <= 15, f"{name} edge {val:.1f} mi off from {half}")

    def test_bbox_scales_with_half_extent(self):
        small = bbox_from_center_half_extent(GJ_LAT, GJ_LON, 100)
        big = bbox_from_center_half_extent(GJ_LAT, GJ_LON, 300)
        self.assertLess(big.south, small.south)
        self.assertGreater(big.north, small.north)
        self.assertLess(big.west, small.west)
        self.assertGreater(big.east, small.east)

    def test_contains(self):
        bb = bbox_from_center_half_extent(GJ_LAT, GJ_LON, 300)
        self.assertTrue(bb.contains(GJ_LAT, GJ_LON))
        self.assertFalse(bb.contains(GJ_LAT + 90, GJ_LON))

    def test_compass_cardinals(self):
        self.assertEqual(compass_point(0), "N")
        self.assertEqual(compass_point(90), "E")
        self.assertEqual(compass_point(180), "S")
        self.assertEqual(compass_point(270), "W")
        self.assertEqual(compass_point(359), "N")  # wraps

    def test_bearing_due_north_and_east(self):
        self.assertEqual(compass_point(initial_bearing(GJ_LAT, GJ_LON, GJ_LAT + 1, GJ_LON)), "N")
        self.assertEqual(compass_point(initial_bearing(GJ_LAT, GJ_LON, GJ_LAT, GJ_LON + 1)), "E")

    def test_offset_description(self):
        # Denver is roughly east-northeast of Grand Junction, ~196 mi.
        desc = offset_description(GJ_LAT, GJ_LON, 39.7392, -104.9903, "Grand Junction")
        self.assertRegex(desc, r"^\d+ mi (E|ENE|NE) of Grand Junction$")

    def test_offset_zero_distance(self):
        self.assertEqual(offset_description(GJ_LAT, GJ_LON, GJ_LAT, GJ_LON, "GJ"), "at GJ")

    def test_footprint_radius_none_or_zero_is_zero(self):
        self.assertEqual(incident_footprint_radius_miles(None), 0.0)
        self.assertEqual(incident_footprint_radius_miles(0), 0.0)

    def test_footprint_radius_scales_with_acreage(self):
        # Circle-equivalent radius: 1 sq mi = 640 acres -> radius ~0.564 mi.
        r640 = incident_footprint_radius_miles(640)
        self.assertAlmostEqual(r640, math.sqrt(1 / math.pi), places=2)
        # A 50,000-acre fire is ~5 miles in radius.
        r50k = incident_footprint_radius_miles(50_000)
        self.assertTrue(4.5 <= r50k <= 5.5, f"got {r50k:.2f} mi")
        # Monotonic: bigger fire -> bigger footprint.
        self.assertGreater(incident_footprint_radius_miles(100_000), r50k)


if __name__ == "__main__":
    unittest.main()

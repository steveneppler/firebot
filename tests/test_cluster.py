"""Tests for FIRMS hotspot clustering."""

import unittest

from firebot.cluster import cluster_hotspots
from firebot.sources.firms import Hotspot


def hs(lat, lon, frp):
    return Hotspot(key=f"{lat}|{lon}|d", lat=lat, lon=lon, acq_dt=None,
                   confidence="h", frp=frp, satellite="N", daynight="D")


class ClusterTests(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(cluster_hotspots([], 3.0), [])

    def test_blob_merges(self):
        # Three points within ~1-2 mi -> one cluster.
        pts = [hs(39.10, -108.60, 50), hs(39.11, -108.61, 90), hs(39.115, -108.605, 20)]
        clusters = cluster_hotspots(pts, 3.0)
        self.assertEqual(len(clusters), 1)
        c = clusters[0]
        self.assertEqual(c.count, 3)
        self.assertEqual(c.max_frp, 90)
        self.assertEqual(c.total_frp, 160)
        self.assertEqual(c.representative.frp, 90)

    def test_distant_points_separate(self):
        pts = [hs(39.10, -108.60, 50), hs(41.50, -105.50, 50)]  # hundreds of mi apart
        self.assertEqual(len(cluster_hotspots(pts, 3.0)), 2)

    def test_transitive_chaining(self):
        # A-B within radius, B-C within radius, A-C just over -> still ONE cluster (chained).
        pts = [hs(39.000, -108.000, 10), hs(39.030, -108.000, 10), hs(39.060, -108.000, 10)]
        # each ~2 mi apart; radius 3 chains all three
        self.assertEqual(len(cluster_hotspots(pts, 3.0)), 1)

    def test_radius_zero_disables(self):
        pts = [hs(39.10, -108.60, 50), hs(39.101, -108.601, 50)]
        self.assertEqual(len(cluster_hotspots(pts, 0)), 2)

    def test_span_miles(self):
        pts = [hs(39.00, -108.00, 100), hs(39.03, -108.00, 10)]  # ~2 mi apart
        c = cluster_hotspots(pts, 5.0)[0]
        self.assertTrue(1.5 <= c.span_miles <= 2.6, f"span {c.span_miles}")

    def test_unsorted_input_chains_across_latitude(self):
        # Input deliberately NOT sorted by latitude; the middle point chains the
        # outer two, so the lat-sorted early-break scan must still find one cluster.
        pts = [hs(39.060, -108.000, 10), hs(39.000, -108.000, 10), hs(39.030, -108.000, 10)]
        clusters = cluster_hotspots(pts, 3.0)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].count, 3)

    def test_latitude_gap_beyond_radius_splits(self):
        # Same longitude, ~7 mi of latitude apart -> beyond a 3 mi radius.
        pts = [hs(39.00, -108.00, 10), hs(39.10, -108.00, 10)]
        self.assertEqual(len(cluster_hotspots(pts, 3.0)), 2)

    def test_representative_is_cached(self):
        c = cluster_hotspots([hs(39.10, -108.60, 50), hs(39.11, -108.61, 90)], 3.0)[0]
        self.assertIs(c.representative, c.representative)


if __name__ == "__main__":
    unittest.main()

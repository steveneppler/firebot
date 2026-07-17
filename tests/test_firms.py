"""Tests for FIRMS CSV parsing and noise filters."""

import unittest
from unittest import mock

import firebot.sources.firms as f
from firebot.geo import bbox_from_center_half_extent

CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
39.10,-108.60,330,0.4,0.4,2026-06-23,0912,N,VIIRS,h,2.0NRT,290,55.0,D
39.20,-108.40,320,0.4,0.4,2026-06-23,0912,N,VIIRS,n,2.0NRT,285,55.0,D
39.30,-108.20,300,0.4,0.4,2026-06-23,0912,N,VIIRS,l,2.0NRT,280,55.0,N
39.40,-108.10,360,0.4,0.4,2026-06-23,0912,N,VIIRS,h,2.0NRT,300,5.0,D"""


class FakeResp:
    status_code = 200
    text = CSV

    def raise_for_status(self):
        pass


class FirmsTests(unittest.TestCase):
    def setUp(self):
        self.bbox = bbox_from_center_half_extent(39.0639, -108.5506, 300)

    def _query(self, **kw):
        with mock.patch.object(f, "get", return_value=FakeResp()):
            return f.query_firms(self.bbox, "KEY", "VIIRS_SNPP_NRT", 1, **kw)

    def test_high_confidence_only(self):
        # rows: h(55), n(55), l(55), h(5). high-only -> the two 'h' rows.
        hs = self._query(viirs_min_confidence="high", frp_min=0)
        self.assertEqual(len(hs), 2)
        self.assertTrue(all(h.confidence == "h" for h in hs))

    def test_nominal_keeps_n_and_h(self):
        hs = self._query(viirs_min_confidence="nominal", frp_min=0)
        self.assertEqual(len(hs), 3)  # h, n, h (drops the 'l')

    def test_frp_min(self):
        # high-conf + FRP>=20 -> only the h/55 row (the h/5 row is dropped).
        hs = self._query(viirs_min_confidence="high", frp_min=20)
        self.assertEqual(len(hs), 1)
        self.assertAlmostEqual(hs[0].frp, 55.0)

    def test_recommended_combo(self):
        # The configured default combo for this project.
        hs = self._query(viirs_min_confidence="high", frp_min=20)
        self.assertEqual(len(hs), 1)

    def test_dedupe_key_shape(self):
        hs = self._query(viirs_min_confidence="high", frp_min=0)
        self.assertRegex(hs[0].key, r"^-?\d+\.\d+\|-?\d+\.\d+\|\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()

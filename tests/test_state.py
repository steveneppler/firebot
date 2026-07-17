"""Tests for state pruning: alerted incidents are kept, pending ones expire."""

import unittest
from datetime import date, timedelta

from firebot.state import State


def old_iso(days):
    return (date.today() - timedelta(days=days)).isoformat()


class PruneTests(unittest.TestCase):
    def setUp(self):
        self.st = State(":mem:")

    def test_alerted_incident_kept_indefinitely(self):
        self.st.seen["nifc:a"] = {"first_seen": old_iso(60), "kind": "nifc", "alerted": True}
        self.st.prune(7)
        self.assertIn("nifc:a", self.st.seen)

    def test_legacy_incident_without_flag_kept(self):
        # Entries written before the pending feature have no "alerted" key.
        self.st.seen["nifc:legacy"] = {"first_seen": old_iso(60), "kind": "nifc"}
        self.st.prune(7)
        self.assertIn("nifc:legacy", self.st.seen)

    def test_old_pending_incident_pruned(self):
        self.st.seen["nifc:p"] = {"first_seen": old_iso(10), "kind": "nifc", "alerted": False}
        self.st.prune(7)
        self.assertNotIn("nifc:p", self.st.seen)

    def test_recent_pending_incident_kept(self):
        self.st.seen["nifc:p"] = {"first_seen": old_iso(1), "kind": "nifc", "alerted": False}
        self.st.prune(7)
        self.assertIn("nifc:p", self.st.seen)

    def test_prune_survives_malformed_timestamp(self):
        # A hand-edited/corrupt state file may carry a non-string first_seen; pruning
        # must not crash (fromisoformat raises TypeError, not ValueError, on null/number).
        self.st.seen["firms:bad"] = {"first_seen": None, "kind": "firms"}
        self.st.seen["nifc:bad"] = {"first_seen": 12345, "kind": "nifc", "alerted": False}
        self.st.prune(7)  # should not raise
        # Treated as just-seen -> kept rather than dropped.
        self.assertIn("firms:bad", self.st.seen)
        self.assertIn("nifc:bad", self.st.seen)


if __name__ == "__main__":
    unittest.main()

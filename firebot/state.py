"""Persistent dedupe state.

state.json maps a stable alert key -> ISO date it was first seen. We keep keys around
so we never re-post the same fire, and prune old hotspot keys to keep the file small.
NIFC incident keys are retained indefinitely (an incident can stay active for weeks).
"""

from __future__ import annotations

import json
import os
from datetime import date, datetime, timedelta, timezone


class State:
    def __init__(self, path: str):
        self.path = path
        # key -> {"first_seen": "YYYY-MM-DD", "kind": "nifc"|"firms"}
        self.seen: dict[str, dict] = {}

    @classmethod
    def load(cls, path: str) -> "State":
        st = cls(path)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
                if isinstance(data, dict) and isinstance(data.get("seen"), dict):
                    st.seen = data["seen"]
            except (json.JSONDecodeError, OSError):
                # Corrupt/unreadable state should not crash the run; start fresh.
                st.seen = {}
        return st

    def has(self, key: str) -> bool:
        return key in self.seen

    def get(self, key: str) -> dict | None:
        return self.seen.get(key)

    def add(self, key: str, kind: str, **fields) -> None:
        meta = {"first_seen": date.today().isoformat(), "kind": kind}
        meta.update(fields)
        self.seen[key] = meta

    def update_meta(self, key: str, **fields) -> None:
        """Merge fields into an existing entry (used to reset the update baseline)."""
        if key in self.seen:
            self.seen[key].update(fields)

    def prune(self, retention_days: int) -> None:
        """Drop transient keys older than retention_days.

        Alerted NIFC incidents are kept indefinitely (they can stay active for weeks).
        FIRMS hotspots and *pending* (never-alerted) NIFC incidents are transient and
        expire once older than the cutoff, so small fires that never grow don't pile up.
        """
        cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
        kept: dict[str, dict] = {}
        for key, meta in self.seen.items():
            is_firms = meta.get("kind") == "firms"
            is_pending = meta.get("kind") == "nifc" and not meta.get("alerted", True)
            if is_firms or is_pending:
                try:
                    seen_dt = datetime.fromisoformat(meta.get("first_seen", ""))
                except (ValueError, TypeError):
                    # Missing/malformed timestamp (e.g. null in a hand-edited state
                    # file) -> treat as just-seen so a bad value can't crash pruning.
                    seen_dt = datetime.now(timezone.utc)
                if seen_dt.tzinfo is None:
                    seen_dt = seen_dt.astimezone()  # first_seen is a naive local date
                if seen_dt < cutoff:
                    continue
            kept[key] = meta
        self.seen = kept

    def save(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"seen": self.seen}, fh, indent=2)
        os.replace(tmp, self.path)  # atomic write

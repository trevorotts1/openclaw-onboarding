"""Persistent intake ledger with an exclusive-create claim.

Implements design/webhook-design.md Section 3.2. One file per job. The atomic
claim uses exclusive create (O_CREAT | O_EXCL): the filesystem is the lock, which
also settles races between two concurrent deliveries of the same submission.
Exactly one delivery claims the job; the other reads the existing file and answers
as a duplicate.

In production this ledger lives at
~/.openclaw/state/podcast-engine/intake-ledger/<job_key>.json (durable state, never
/tmp). The oracle takes an explicit base_dir so tests write into a throwaway
directory and never touch a real box.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

# The state enum is the client dashboard's status vocabulary plus the queue states
# (Section 3.2), so the dashboard reads this ledger with no separate data entry.
STATES = {
    "received", "needs_input", "researching", "writing", "qc", "art", "audio",
    "publishing", "enrolling", "complete", "queued_credit_out", "aged_out",
    "failed", "test",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, base_dir):
        self.base_dir = str(base_dir)
        os.makedirs(self.base_dir, exist_ok=True)

    def path_for(self, job_key: str) -> str:
        return os.path.join(self.base_dir, job_key + ".json")

    def payload_path_for(self, job_key: str) -> str:
        return os.path.join(self.base_dir, job_key + ".payload.json")

    def count(self) -> int:
        return len([n for n in os.listdir(self.base_dir) if n.endswith(".json")
                    and not n.endswith(".payload.json")])

    def read(self, job_key: str):
        path = self.path_for(job_key)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)

    def _write(self, job_key: str, record: dict) -> None:
        # atomic replace on update so a crash never leaves a torn record
        tmp = self.path_for(job_key) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
        os.replace(tmp, self.path_for(job_key))

    def claim(self, job_key: str, canonical: dict, state: str = "received"):
        """Atomically claim a job. Return the new record, or None if already claimed.

        Uses O_CREAT | O_EXCL so a second concurrent delivery of the same submission
        cannot create a second record; it gets None and must duplicate-ack.
        """
        if state not in STATES:
            raise ValueError("illegal ledger state: " + str(state))
        record = {
            "job_key": job_key,
            "state": state,
            "received_at": _now(),
            "updated_at": _now(),
            "attempts": {"delivery_count": 1, "qc_failures": 0},
            "contact_id": canonical.get("contact_id"),
            "location_id": canonical.get("location_id"),
            "podcast_id": canonical.get("podcast_id"),
            "mode": canonical.get("mode"),
            "style": canonical.get("style"),
            "canonical_payload_path": os.path.basename(self.payload_path_for(job_key)),
            "flow_id": job_key,
            "podbean_permalink": None,
            "notes": [],
        }
        try:
            fd = os.open(self.path_for(job_key), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            return None
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(record, handle, indent=2, sort_keys=True)
        # persist the canonical payload beside the record (pointer-based flow trigger)
        with open(self.payload_path_for(job_key), "w", encoding="utf-8") as handle:
            json.dump(canonical, handle, indent=2, sort_keys=True)
        return record

    def touch_duplicate(self, job_key: str) -> dict:
        """Increment delivery_count and touch updated_at; change nothing else."""
        record = self.read(job_key)
        if record is None:
            raise KeyError("no ledger record for " + job_key)
        record["attempts"]["delivery_count"] = record["attempts"].get("delivery_count", 1) + 1
        record["updated_at"] = _now()
        self._write(job_key, record)
        return record

    def set_state(self, job_key: str, state: str) -> dict:
        if state not in STATES:
            raise ValueError("illegal ledger state: " + str(state))
        record = self.read(job_key)
        if record is None:
            raise KeyError("no ledger record for " + job_key)
        record["state"] = state
        record["updated_at"] = _now()
        self._write(job_key, record)
        return record

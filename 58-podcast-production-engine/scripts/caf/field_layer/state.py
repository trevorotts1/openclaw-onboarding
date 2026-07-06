#!/usr/bin/env python3
"""
Per-client Convert and Flow state file access (design Section 8).

The state file at <state-dir>/ghl-state.json is shared memory for the whole
data plane: folders, workflow ids, rate counters, and the field-key to
field-id map. This module owns ONLY the field-layer sections (field_map and
book_teaser_field_present) and performs read-modify-write so sibling slices
(media folders, workflow enrollment, rate budgeting, credential gate) keep
their sections intact.

No secret material is ever written here (design Section 8). The field layer
never writes the PIT, only field ids and presence flags.
"""
from __future__ import annotations

import json
import os
import tempfile
from typing import Any

from . import constants


class GhlState:
    def __init__(self, state_dir: str | None = None) -> None:
        self.state_dir = state_dir or constants.default_state_dir()
        self.path = os.path.join(self.state_dir, constants.STATE_FILE_NAME)

    # -- load / save ------------------------------------------------------
    def load(self) -> dict[str, Any]:
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else {}
        except (FileNotFoundError, ValueError, OSError):
            return {}

    def _atomic_write(self, data: dict[str, Any]) -> None:
        os.makedirs(self.state_dir, exist_ok=True)
        # Read-modify-write on a fresh load so a concurrent sibling section
        # update is not clobbered by a stale in-memory copy.
        fd, tmp_path = tempfile.mkstemp(dir=self.state_dir, prefix=".ghl-state-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, sort_keys=True)
                handle.write("\n")
            os.replace(tmp_path, self.path)
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def _update_sections(self, sections: dict[str, Any]) -> dict[str, Any]:
        data = self.load()
        data.update(sections)
        self._atomic_write(data)
        return data

    # -- read-side helpers ------------------------------------------------
    def get_location_id(self) -> str | None:
        value = self.load().get("location_id")
        return value if isinstance(value, str) else None

    def get_field_map(self) -> dict[str, str]:
        field_map = self.load().get("field_map")
        if isinstance(field_map, dict):
            return {k: v for k, v in field_map.items() if isinstance(v, str)}
        return {}

    def book_teaser_present(self) -> bool:
        return bool(self.load().get("book_teaser_field_present", False))

    def gate_is_fresh(self, max_age_seconds: int) -> bool:
        """True when a prior credential gate pass is recorded and recent.
        The field layer does not run the gate (a separate slice owns it); it
        only reads freshness to decide whether cached ids may be trusted."""
        import datetime

        gate = self.load().get("gate")
        if not isinstance(gate, dict):
            return False
        stamp = gate.get("last_pass")
        if not isinstance(stamp, str):
            return False
        try:
            when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except ValueError:
            return False
        now = datetime.datetime.now(datetime.timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=datetime.timezone.utc)
        return (now - when).total_seconds() <= max_age_seconds

    # -- write-side helpers (field-layer owned sections only) ------------
    def save_field_map(
        self,
        field_map: dict[str, str],
        book_teaser_present: bool,
        location_id: str | None = None,
    ) -> None:
        sections: dict[str, Any] = {
            "field_map": dict(field_map),
            "book_teaser_field_present": bool(book_teaser_present),
        }
        # Only set location_id if the file does not already carry one; the
        # credential gate is the authoritative writer of location_id.
        if location_id and not self.get_location_id():
            sections["location_id"] = location_id
        self._update_sections(sections)

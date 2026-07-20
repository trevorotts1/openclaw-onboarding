#!/usr/bin/env python3
"""
tests/unit/ledger-reconciler-idempotent-write.test.py
─────────────────────────────────────────────────────────────────────────────
Proves shared-utils/ledger_reconciler_core.py's split write behavior
(re-unified 2026-07-19 from the operator-box fork):

  1. `_write_idempotent` freezes the target byte-for-byte when ONLY volatile
     lines (Generated timestamp, HEAD shas, journal count) changed — so the
     committed scratch copy produces NO noise commit/push on a no-change pass.
  2. `_write_idempotent` DOES rewrite when substantive content changes
     (e.g. an integrity alarm appears or clears).
  3. `render_recovery_state(..., idempotent=False)` (the default, used for
     the operator-box local copy) ALWAYS rewrites with the fresh `Generated`
     timestamp — the liveness heartbeat. The pre-fix deployed fork froze the
     local copy too, making a healthy reconciler indistinguishable from a
     dead one (the 2026-07-16..19 outage's visibility hole).

FAIL-FIRST: on the pre-fix canonical module (no `_write_idempotent`,
`render_recovery_state` without the `idempotent` kwarg), Test 1/2 raise
AttributeError and Test 3 raises TypeError.

Run:
    python3 tests/unit/ledger-reconciler-idempotent-write.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir()

_spec = importlib.util.spec_from_file_location(
    "ledger_reconciler_core", _SHARED_UTILS / "ledger_reconciler_core.py"
)
assert _spec is not None
mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(mod)  # type: ignore


def _truth(generated_at, onb_sha, with_alarm):
    alarms = []
    if with_alarm:
        alarms.append({
            "unit": "U53", "repo": "openclaw-onboarding",
            "branch": "skill6-v2/U53", "tip": "1afb5690deadbeef",
            "ledger_status": "verified", "kind": "unmerged",
            "reason": "fixture",
        })
    return {
        "generated_at": generated_at,
        "onb_main_sha": onb_sha,
        "cc_main_sha": "c" * 40,
        "onb_units": {},
        "cc_units": {},
        "cinematic": {"exists": False},
        "cinematic_local_clone": {"clone_exists": False},
        "merge_queue": {"tickets_ready": [], "done": [], "lock_held": False},
        "journal_hits": [],
        "ledger_edit_allowed": True,
        "units_gap_filled": "",
        "failclosed_alarms": alarms,
    }


class TestIdempotentWrite(unittest.TestCase):
    def test_volatile_only_change_freezes_file(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "recovery-state.md"
            mod.render_recovery_state(
                _truth("2026-07-19T00:00:00Z", "a" * 40, False), "", out, idempotent=True
            )
            first = out.read_text()
            self.assertIn("2026-07-19T00:00:00Z", first)
            # Second pass: only volatile lines differ (new timestamp, new sha).
            mod.render_recovery_state(
                _truth("2026-07-19T00:10:00Z", "b" * 40, False), "", out, idempotent=True
            )
            self.assertEqual(
                out.read_text(), first,
                "volatile-only change must leave the committed copy byte-identical",
            )

    def test_substantive_change_rewrites(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "recovery-state.md"
            mod.render_recovery_state(
                _truth("2026-07-19T00:00:00Z", "a" * 40, False), "", out, idempotent=True
            )
            # Alarm appears: substantive — must rewrite (fresh timestamp too).
            mod.render_recovery_state(
                _truth("2026-07-19T00:10:00Z", "b" * 40, True), "", out, idempotent=True
            )
            second = out.read_text()
            self.assertIn("2026-07-19T00:10:00Z", second)
            self.assertIn("U53", second)

    def test_local_copy_always_fresh(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "recovery-state.md"
            mod.render_recovery_state(
                _truth("2026-07-19T00:00:00Z", "a" * 40, False), "", out
            )
            # Volatile-only change, NON-idempotent default: must still rewrite
            # with the fresh timestamp (liveness heartbeat).
            mod.render_recovery_state(
                _truth("2026-07-19T00:10:00Z", "a" * 40, False), "", out
            )
            self.assertIn(
                "2026-07-19T00:10:00Z", out.read_text(),
                "local copy must always carry the current pass's Generated timestamp",
            )

    def test_neutralize_preserves_line_positions(self):
        text = "Generated: X\nreal content\n"
        neutral = mod._neutralize_volatile(text)
        self.assertEqual(len(neutral.split("\n")), len(text.split("\n")))
        self.assertIn("real content", neutral)


# ─── Cross-ship downgrade (the resolved-U108 shape) ─────────────────────────
# A both-tagged row, status verified, NO own-named branch in the repo -- but
# the row's own text cites a carrier branch. If git proves the carrier merged
# into this repo's main, the finding must downgrade to informational
# "cross-shipped-leg-verified" (no more 10-minutely hard alarm on documented,
# human-reviewed, merged work). If the cited carrier is NOT provably merged,
# the hard "missing-leg" alarm must stand unchanged (fail-closed).

_XSHIP_LEDGER = (
    "| unit | description | label | status | evidence | timestamp |\n"
    "|---|---|---|---|---|---|\n"
    "| U108 | [E5-3] (both, P1) opt-out warning | [fix] corrected | verified | "
    "CC-side work was done, filed under U110's branch by design: part of "
    "`skill6-v2/U110`'s own branch, merged. No `skill6-v2/U108` CC branch exists. "
    "| 2026-07-17T01:15:00-04:00 |\n"
)


def _units_truth_with(branch, merged):
    return {
        branch: {
            "branch": branch,
            "tip": "d" * 40,
            "is_ancestor_of_main": merged,
            "merge_sha": ("e" * 40) if merged else None,
            "tag": "v6.0.55" if merged else None,
        }
    }


class TestCrossShipDowngrade(unittest.TestCase):
    def test_cited_carrier_merged_downgrades_to_informational(self):
        alarms = mod.detect_failclosed_mismatches(
            "blackceo-command-center",
            _units_truth_with("skill6-v2/U110", merged=True),
            _XSHIP_LEDGER,
        )
        u108 = [a for a in alarms if a["unit"] == "U108"]
        self.assertEqual(len(u108), 1)
        self.assertEqual(u108[0]["kind"], "cross-shipped-leg-verified")
        self.assertIn("cross-shipped-leg-verified", mod.INFORMATIONAL_ALARM_KINDS)

    def test_cited_carrier_unmerged_keeps_hard_alarm(self):
        alarms = mod.detect_failclosed_mismatches(
            "blackceo-command-center",
            _units_truth_with("skill6-v2/U110", merged=False),
            _XSHIP_LEDGER,
        )
        # The unmerged U110 branch itself has no verified row here, so the
        # only finding must be U108's -- and it must stay HARD.
        u108 = [a for a in alarms if a["unit"] == "U108"]
        self.assertEqual(len(u108), 1)
        self.assertEqual(u108[0]["kind"], "missing-leg")

    def test_own_branch_citation_never_counts_as_carrier(self):
        carriers = mod.find_verified_cross_ship_carriers(
            "no `skill6-v2/U108` branch exists",
            "U108",
            _units_truth_with("skill6-v2/U108", merged=True),
        )
        self.assertEqual(carriers, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)

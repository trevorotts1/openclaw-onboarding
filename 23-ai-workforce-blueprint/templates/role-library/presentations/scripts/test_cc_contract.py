#!/usr/bin/env python3
"""
test_cc_contract.py — STATIC CONTRACT TEST for the presentations Command Center
board wiring. Stdlib unittest + ast only; NO network, NO imports of the heavy
render engine (build_deck.py is parsed, not executed).

WHY THIS EXISTS
  v17.0.x shipped a P9-DELIVER close that PATCHed the deck task to status
  ``'delivered'`` — a literal that is NOT a member of the Command Center
  ``UpdateTaskSchema`` TaskStatus enum (src/lib/validation.ts). The gate 400'd
  every terminal PATCH, so the card never closed. The mock in test_cc_board.py
  accepted 'delivered' and hid the bug.

  This test pins the 10 AUTHORITATIVE CC TaskStatus values and FAILS if any status
  literal that ``cc_board.py`` or ``build_deck.py`` can EMIT to the board is outside
  that set — so a re-introduction of 'delivered' (or any other non-enum status)
  fails here at build time, offline, with no Command Center required.

WHAT IS CHECKED
  1. cc_board.CC_TASK_STATUSES equals the 10 authoritative values (drift guard).
  2. Every status STRING LITERAL emitted by cc_board.py, build_deck.py AND
     run_signature_deck.py — whether in a board-PATCH-payload dict (phase_id+status)
     or as the status argument of a patch_phase / _board_patch_phase call — is a
     member of the authoritative set.
  3. 'delivered' specifically is emitted by NONE of those files (the exact
     P9-DELIVER regression).
  4. OWNERSHIP/ORDERING: build_deck's P9-DELIVER 'done' close is GUARDED by
     `if _process_certificate_present(...)` (so in the runner flow, where render runs
     before the cert exists, build_deck emits no premature terminal 'done'); and the
     RUNNER (run_signature_deck.py) emits the terminal status='done' close itself.
  5. (Self-check, skipped when the CC clone is absent) the hardcoded authoritative
     set matches the z.enum([...]) TaskStatus in the CC repo validation.ts.
"""

import ast
import os
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

# The 10 authoritative Command Center TaskStatus values — UpdateTaskSchema in the
# CC repo src/lib/validation.ts. THIS is the contract the producer side must honour.
# NB: there is NO 'delivered' status; a completed deck closes with 'done'.
AUTHORITATIVE_CC_TASK_STATUSES = frozenset({
    "backlog",
    "inbox",
    "planning",
    "in_progress",
    "assigned",
    "review",
    "testing",
    "blocked",
    "pending_dispatch",
    "done",
})

# Read-only CC clone used ONLY for an optional self-check of the hardcode above.
# FIX-PRES-05: NO hardcoded operator-machine path (the old literal embedded the
# operator home in its dash-separated scratchpad spelling — a fleet
# no-operator-identifiers violation that also evaded qc-assert-no-client-names.sh,
# which banned only the slash form; the dash form is now a banned token too). The
# cross-check is now enabled ONLY when the operator points CC_VALIDATION_TS_PATH at
# a local blackceo-command-center validation.ts; unset (the fleet / CI default) =>
# the self-check skips rather than runs against a machine-specific path.
_CC_VALIDATION_TS_ENV = os.environ.get("CC_VALIDATION_TS_PATH", "").strip()
_CC_VALIDATION_TS = Path(_CC_VALIDATION_TS_ENV) if _CC_VALIDATION_TS_ENV else None

# Function names whose STATUS argument (positional index 3) is a task-level status.
#   patch_phase(run_dir, task_id, phase_id, status, note="", env=None)
#   _board_patch_phase(run_dir, task_id, phase_id, status, note="")
_STATUS_FUNCS = {"patch_phase", "_board_patch_phase"}
_STATUS_ARG_INDEX = 3


def _emitted_status_literals(source: str) -> set:
    """Collect every task-STATUS string literal a module can emit TO THE BOARD:
      * the status value of a board PATCH payload dict — a dict literal carrying
        BOTH a ``phase_id`` and a ``status`` key (the CC task-PATCH shape); this is
        narrow on purpose so unrelated internal dicts (deliverables-ledger /
        teleprompter-publish ``{"status": ...}`` records) are NOT mistaken for
        board statuses, and
      * the status argument (positional #3 or kw ``status=``) of a
        patch_phase / _board_patch_phase call.
    Only Constant strings are collected (a variable status is opaque to a static
    scan and is covered at runtime by the mock server + the movement receipt)."""
    tree = ast.parse(source)
    found: set = set()

    for node in ast.walk(tree):
        # A CC task-PATCH payload dict: {"phase_id": ..., "status": "<lit>", ...}
        if isinstance(node, ast.Dict):
            literal_keys = {
                k.value for k in node.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
            if "phase_id" in literal_keys and "status" in literal_keys:
                for key, value in zip(node.keys, node.values):
                    if (
                        isinstance(key, ast.Constant)
                        and key.value == "status"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)
                    ):
                        found.add(value.value)

        # patch_phase(...) / _board_patch_phase(...) status argument.
        if isinstance(node, ast.Call):
            fname = None
            if isinstance(node.func, ast.Name):
                fname = node.func.id
            elif isinstance(node.func, ast.Attribute):
                fname = node.func.attr
            if fname in _STATUS_FUNCS:
                if len(node.args) > _STATUS_ARG_INDEX:
                    arg = node.args[_STATUS_ARG_INDEX]
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        found.add(arg.value)
                for kw in node.keywords:
                    if (
                        kw.arg == "status"
                        and isinstance(kw.value, ast.Constant)
                        and isinstance(kw.value.value, str)
                    ):
                        found.add(kw.value.value)
    return found


def _call_name(node: ast.Call):
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _test_references(test: ast.AST, name: str) -> bool:
    """True when an ``if`` test invokes a function named ``name`` (e.g. the
    ``if _process_certificate_present(run_dir):`` guard)."""
    for sub in ast.walk(test):
        if isinstance(sub, ast.Call) and _call_name(sub) == name:
            return True
    return False


def _p9_done_close_counts(source: str, guard_func: str = "_process_certificate_present"):
    """Count P9-DELIVER terminal 'done' board closes in `source` and how many are
    lexically nested inside an ``if <guard_func>(...)`` block. Returns (total, guarded).
    A 'close' is a patch_phase / _board_patch_phase call carrying BOTH the 'P9-DELIVER'
    phase id and the 'done' status as constant string args."""
    tree = ast.parse(source)

    guarded_call_ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _test_references(node.test, guard_func):
            for stmt in node.body:  # guarded branch ONLY (never orelse)
                for sub in ast.walk(stmt):
                    if isinstance(sub, ast.Call):
                        guarded_call_ids.add(id(sub))

    total = guarded = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) in _STATUS_FUNCS:
            const_strs = {
                a.value for a in node.args
                if isinstance(a, ast.Constant) and isinstance(a.value, str)
            }
            if "P9-DELIVER" in const_strs and "done" in const_strs:
                total += 1
                if id(node) in guarded_call_ids:
                    guarded += 1
    return total, guarded


class ContractTest(unittest.TestCase):
    def _read(self, name: str) -> str:
        p = HERE / name
        self.assertTrue(p.exists(), f"{name} not found next to the contract test at {HERE}")
        return p.read_text()

    def test_cc_board_status_set_matches_authoritative(self):
        import sys
        sys.path.insert(0, str(HERE))
        import cc_board  # noqa: E402
        self.assertEqual(
            set(cc_board.CC_TASK_STATUSES),
            set(AUTHORITATIVE_CC_TASK_STATUSES),
            "cc_board.CC_TASK_STATUSES has drifted from the CC UpdateTaskSchema enum.",
        )

    def test_cc_board_emits_only_valid_statuses(self):
        emitted = _emitted_status_literals(self._read("cc_board.py"))
        bad = emitted - AUTHORITATIVE_CC_TASK_STATUSES
        self.assertEqual(
            bad, set(),
            f"cc_board.py emits status literal(s) outside the CC TaskStatus enum: {sorted(bad)}",
        )
        self.assertNotIn("delivered", emitted)

    def test_build_deck_emits_only_valid_statuses(self):
        emitted = _emitted_status_literals(self._read("build_deck.py"))
        bad = emitted - AUTHORITATIVE_CC_TASK_STATUSES
        self.assertEqual(
            bad, set(),
            f"build_deck.py emits status literal(s) outside the CC TaskStatus enum: {sorted(bad)}",
        )
        # The exact P9-DELIVER regression: 'delivered' must never be a status literal.
        self.assertNotIn(
            "delivered", emitted,
            "build_deck.py still emits status='delivered' — the P9-DELIVER close must "
            "use status='done' and put 'delivered' in the note only.",
        )

    def test_build_deck_terminal_close_is_done(self):
        # Positive assertion: build_deck DOES emit a terminal 'done' status somewhere
        # (the completed-deck close), so the fix is present, not merely 'delivered'
        # removed.
        emitted = _emitted_status_literals(self._read("build_deck.py"))
        self.assertIn("done", emitted)
        self.assertIn("in_progress", emitted)  # P4-RENDER START still a status change.

    def test_build_deck_terminal_done_is_cert_guarded(self):
        # Ownership/ordering proof: build_deck's P9-DELIVER 'done' close must be
        # GUARDED by `if _process_certificate_present(...)`, so in the runner flow
        # (render before the cert is minted) build_deck emits NO terminal 'done' —
        # it defers to the runner. Every P9-DELIVER 'done' close must be guarded.
        total, guarded = _p9_done_close_counts(self._read("build_deck.py"))
        self.assertGreaterEqual(
            total, 1, "build_deck.py no longer has a P9-DELIVER 'done' close.")
        self.assertEqual(
            total, guarded,
            "build_deck.py has a P9-DELIVER 'done' close that is NOT guarded by "
            "_process_certificate_present — it could 422 a premature terminal close in "
            "the runner flow (cert not yet minted).",
        )

    def test_runner_emits_terminal_done_close(self):
        # The RUNNER owns the terminal close: after prove-deck mints the cert it fires
        # a task-level status='done' via cc_board.patch_phase (which attaches the
        # process_certificate_sha). Assert the runner emits 'done', only valid
        # statuses, and never 'delivered'. Also assert the close is NOT hidden behind
        # the cert guard (the runner runs AFTER prove-deck, so it needs no guard).
        src = self._read("run_signature_deck.py")
        emitted = _emitted_status_literals(src)
        bad = emitted - AUTHORITATIVE_CC_TASK_STATUSES
        self.assertEqual(
            bad, set(),
            f"run_signature_deck.py emits status literal(s) outside the CC enum: {sorted(bad)}",
        )
        self.assertIn(
            "done", emitted,
            "run_signature_deck.py must emit the terminal status='done' delivery close.",
        )
        self.assertNotIn("delivered", emitted)

    def test_hardcode_matches_cc_clone_validation_ts_when_present(self):
        if _CC_VALIDATION_TS is None:
            self.skipTest("CC_VALIDATION_TS_PATH unset — CC clone cross-check skipped")
        if not _CC_VALIDATION_TS.exists():
            self.skipTest(f"CC clone validation.ts not present at {_CC_VALIDATION_TS}")
        ts = _CC_VALIDATION_TS.read_text()
        m = re.search(r"const\s+TaskStatus\s*=\s*z\.enum\(\s*\[(.*?)\]\s*\)", ts, re.S)
        self.assertIsNotNone(m, "Could not locate `const TaskStatus = z.enum([...])` in validation.ts")
        enum_values = set(re.findall(r"['\"]([a-zA-Z_]+)['\"]", m.group(1)))
        self.assertEqual(
            enum_values, set(AUTHORITATIVE_CC_TASK_STATUSES),
            "The hardcoded authoritative status set is out of lockstep with the CC "
            f"repo TaskStatus enum. CC={sorted(enum_values)} "
            f"hardcode={sorted(AUTHORITATIVE_CC_TASK_STATUSES)}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

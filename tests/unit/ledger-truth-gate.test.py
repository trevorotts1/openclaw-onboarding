#!/usr/bin/env python3
"""
tests/unit/ledger-truth-gate.test.py
─────────────────────────────────────────────────────────────────────────────
Proves the ZERO_LEG_OVERRIDES / classify_ledger_row() fix in
scripts/ledger-truth-gate.py: `ledgers/skill58-podbean-proxy-2026-07-16.md`'s
U2/U4/U5/U8 rows are each a live n8n/data-table claim with NO repository leg
at all (confirmed by that ledger's own CONCURRENCY MAP table, which names
ONLY U12/U14/U15/U16/U17/U21 as carrying a repo leg) -- before this fix, ANY
`verified`/`done` claim added to that file, true or false, was routed to the
NOT-ENFORCED / human-review-required path unconditionally (the exemption
list PR #633 added never had a way to convert to a PASS, even for a claim
independently confirmed true), which is why PR #637 -- which flips exactly
these 4 units to `verified` on real, independently-confirmed-true live
n8n-execution evidence -- fails this gate every time despite nothing being
false.

WHAT EACH TEST CLASS PROVES:
  ClassifyLedgerRowRouting        -- pure, offline unit tests of the router
                                     itself, including a direct mutation
                                     proof (empty ZERO_LEG_OVERRIDES reverts
                                     U2 to not_enforced).
  PodbeanZeroLegEndToEnd          -- real git-repo + real subprocess
                                     invocation of the SHIPPED gate script:
                                     (a) U2/U4/U5/U8 alone -> clean PASS;
                                     (b) U2/U4/U5/U8 PLUS an unreviewed unit
                                         (U12) flipped in the SAME commit ->
                                         the reviewed 4 still print PASS WITH
                                         DISCLAIMER, but U12 alone still
                                         blocks the whole gate -- proving the
                                         fix is surgical, not a blanket
                                         exemption of the file;
                                     (c) an INTEGRATION-level mutation proof:
                                         the exact scenario-(a) diff, re-run
                                         through a copy of the script with
                                         ZERO_LEG_OVERRIDES reverted to `{}`,
                                         fails again -- exactly PR #637's
                                         real failure;
                                     (d) a stub `unit-status.sh` proves
                                         neither bucket ever shells out to
                                         the tool (which is the ENTIRE point
                                         -- invoking it risks the real
                                         U2/U4/U5/U8 cross-file numbering
                                         collision with the kanban ledger's
                                         own, unrelated U2/U4/U5/U8 rows).
  FalseClaimStillRejectedElsewhere -- the property this fix must NOT weaken:
                                     a genuinely FALSE `verified` claim for a
                                     real, git-checkable unit (proper leg
                                     tag, NOT in an UNPARSEABLE_LEDGER_FILES
                                     member) is still mechanically caught as
                                     NOT-DONE by unit_status_core.py, which
                                     this fix never touches. Fully offline --
                                     the fabricated unit's own-named branch
                                     is real but provably unmerged, so no
                                     CI/network check-run lookup ever fires.

Run:
    python3 tests/unit/ledger-truth-gate.test.py
"""
from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_GATE_SCRIPT = _REPO_ROOT / "scripts" / "ledger-truth-gate.py"
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _GATE_SCRIPT.is_file()
assert _SHARED_UTILS.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


gate = _load("ledger_truth_gate", _GATE_SCRIPT)
usc = _load("unit_status_core", _SHARED_UTILS / "unit_status_core.py")

PODBEAN_FILE = "skill58-podbean-proxy-2026-07-16.md"
KANBAN_FILE = "skill6-blended-persona-kanban-v2-2026-07-13.md"


def _git(cwd, *args, check=True):
    r = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git -C {cwd} {' '.join(args)} failed: {r.stderr}")
    return r.stdout.strip()


# --------------------------------------------------------------------------
# Section 1: pure-function routing tests (no I/O)
# --------------------------------------------------------------------------

class ClassifyLedgerRowRouting(unittest.TestCase):
    """classify_ledger_row() is a pure function -- these tests never touch
    git or the filesystem. They prove the router is SURGICAL: only the 4
    reviewed units get trusted; every other unit id in the same
    unparseable file (including ones this repo's own concurrency map names
    as carrying a REAL repo leg) keeps the original, unconditional
    not_enforced failure."""

    def test_reviewed_units_get_zero_leg_override(self):
        for unit_id in ("U2", "U4", "U5", "U8"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(
                    gate.classify_ledger_row(PODBEAN_FILE, unit_id),
                    "zero_leg_override",
                )

    def test_repo_leg_units_in_same_file_stay_not_enforced(self):
        # U12/U14/U15/U16/U17/U21 carry a REAL repo leg per this ledger's own
        # CONCURRENCY MAP table -- blanket-trusting them the way U2/U4/U5/U8
        # are trusted would be the exact security regression the fix must
        # avoid, so none of them may appear on the allowlist.
        for unit_id in ("U12", "U14", "U15", "U16", "U17", "U21"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, unit_id), "not_enforced")
                self.assertNotIn(
                    unit_id, gate.ZERO_LEG_OVERRIDES.get(PODBEAN_FILE, frozenset()),
                )

    def test_unlisted_or_future_unit_defaults_to_not_enforced(self):
        # A fail-closed default: a unit nobody has reviewed yet must NOT be
        # trusted just because it lives in an already-partly-trusted file.
        for unit_id in ("U1", "U3", "U6", "U9999"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, unit_id), "not_enforced")

    def test_other_ledgers_fully_enforced_unaffected(self):
        self.assertEqual(gate.classify_ledger_row(KANBAN_FILE, "U2"), "enforce")
        self.assertEqual(gate.classify_ledger_row(KANBAN_FILE, "U9999"), "enforce")

    def test_mutation_proof_reverting_override_breaks_it(self):
        """FAIL-FIRST/PASS-AFTER: simulate the pre-fix state (an empty
        ZERO_LEG_OVERRIDES -- UNPARSEABLE_LEDGER_FILES membership alone,
        which existed before this fix and is unchanged by it, is NOT
        sufficient by itself) and confirm U2 reverts to not_enforced, then
        restore it and confirm the fix is back in effect. This is the
        direct proof that "does reverting your fix make the test fail
        again" is TRUE."""
        saved = gate.ZERO_LEG_OVERRIDES
        try:
            gate.ZERO_LEG_OVERRIDES = {}
            self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, "U2"), "not_enforced")
        finally:
            gate.ZERO_LEG_OVERRIDES = saved
        self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, "U2"), "zero_leg_override")


# --------------------------------------------------------------------------
# Section 2: real git repo + real subprocess invocation of the shipped script
# --------------------------------------------------------------------------

# If zero_leg_override or not_enforced routing ever regresses into calling
# the real tool, this stub makes that failure LOUD (UNKNOWN + a sentinel
# log) instead of silently working by accident -- it must never be invoked
# by either bucket in these tests.
_STUB_UNIT_STATUS_SH = """#!/usr/bin/env bash
echo "$@" >> "$(cd "$(dirname "$0")" && pwd)/.unit-status-invoked.log"
echo '{"unit": "STUB", "verdict": "UNKNOWN", "reason": "unit-status.sh stub invoked -- routing bug, this bucket must never shell out to the tool"}'
exit 3
"""


def _podbean_fixture_text(u2, u4, u5, u8, u12):
    return textwrap.dedent(f"""\
        # SKILL 58 PODBEAN SERVER-SIDE PUBLISH — LEDGER — FIXTURE

        **Row format:** `id | desc | [Model xN] label | status | evidence | timestamp`
        **Status vocabulary:** `pending` / `in_progress` / `verified` / `blocked`
        **`verified` is a GIT state (repo legs) or a LIVE-API state (n8n legs: fresh
        API re-read). Never prose. Never a subagent's claim.**

        ## CONCURRENCY MAP (one writer per n8n WORKFLOW; different workflows run in PARALLEL)

        | Lock target | Units | Note |
        |---|---|---|
        | Repo `openclaw-onboarding` | U12 (repo leg) | ONE merge-writer, serial |

        ## UNIT ROWS

        | id | desc | [Model xN] label | status | evidence | timestamp |
        |---|---|---|---|---|---|
        | U2 | fixture data-table seed | — | {u2} | fixture LIVE-PROVEN evidence U2 | 2026-07-18T00:00:00Z |
        | U4 | fixture webhook header-auth flip | — | {u4} | fixture LIVE-PROVEN evidence U4 | 2026-07-18T00:00:00Z |
        | U5 | fixture roster/identity gate | — | {u5} | fixture LIVE-PROVEN evidence U5 | 2026-07-18T00:00:00Z |
        | U8 | fixture idempotency via data-table | — | {u8} | fixture LIVE-PROVEN evidence U8 | 2026-07-18T00:00:00Z |
        | U12 | fixture HYBRID repo-leg unit (NOT reviewed/allowlisted) | — | {u12} | fixture evidence U12 | 2026-07-18T00:00:00Z |
        """)


class PodbeanZeroLegEndToEnd(unittest.TestCase):
    """Runs the ACTUAL scripts/ledger-truth-gate.py as a subprocess against
    a throwaway, self-contained git repo -- not just the pure function."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ledger-truth-gate-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = Path(self.tmp) / "repo"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _git(self.repo, "config", "user.email", "test@example.invalid")
        _git(self.repo, "config", "user.name", "Test")

        stub = self.repo / "unit-status.sh"
        stub.write_text(_STUB_UNIT_STATUS_SH)
        stub.chmod(0o755)

        self.ledgers_dir = self.repo / "ledgers"
        self.ledgers_dir.mkdir()
        (self.ledgers_dir / PODBEAN_FILE).write_text(
            _podbean_fixture_text("pending", "pending", "pending", "pending", "pending")
        )
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base: all pending")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")

        self.cc_dir = Path(self.tmp) / "cc-dummy"
        self.cc_dir.mkdir()
        self.head_sha = None

    def _commit_fixture(self, u2, u4, u5, u8, u12, message):
        (self.ledgers_dir / PODBEAN_FILE).write_text(_podbean_fixture_text(u2, u4, u5, u8, u12))
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", message)
        self.head_sha = _git(self.repo, "rev-parse", "HEAD")

    def _run_gate(self, script_path=None):
        script_path = script_path or _GATE_SCRIPT
        assert self.head_sha, "call _commit_fixture() first"
        return subprocess.run(
            [sys.executable, str(script_path),
             "--base", self.base_sha, "--head", self.head_sha, "--cc-dir", str(self.cc_dir)],
            cwd=self.repo, capture_output=True, text=True, timeout=60,
        )

    def _invoked_log_text(self):
        p = self.repo / ".unit-status-invoked.log"
        return p.read_text() if p.is_file() else None

    def test_reviewed_units_pass_cleanly(self):
        self._commit_fixture("verified", "verified", "verified", "verified", "pending",
                              "flip U2/U4/U5/U8 to verified")
        r = self._run_gate()
        self.assertEqual(r.returncode, 0, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        for unit_id in ("U2", "U4", "U5", "U8"):
            self.assertIn(f"PASS WITH DISCLAIMER (reviewed zero-leg override): {unit_id}", r.stdout)
        self.assertIn("GATE RESULT: PASS.", r.stdout)
        self.assertIsNone(
            self._invoked_log_text(),
            "unit-status.sh stub was invoked -- routing bug: zero_leg_override must never shell "
            "out to the tool (that is exactly the collision-risk path this fix avoids)",
        )

    def test_unreviewed_unit_in_same_file_still_blocks(self):
        # U2/U4/U5/U8 genuinely verified AND U12 (never reviewed, never
        # allowlisted) ALSO flipped to verified in the SAME commit/file --
        # proves the fix is surgical: the reviewed 4 still pass, but U12's
        # claim -- true or false, the gate cannot mechanically tell for this
        # file's row shape -- still blocks the whole check for a human,
        # exactly as before this fix existed.
        self._commit_fixture("verified", "verified", "verified", "verified", "verified",
                              "flip U2/U4/U5/U8/U12 to verified")
        r = self._run_gate()
        self.assertEqual(r.returncode, 1, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        for unit_id in ("U2", "U4", "U5", "U8"):
            self.assertIn(f"PASS WITH DISCLAIMER (reviewed zero-leg override): {unit_id}", r.stdout)
        self.assertIn("NOT ENFORCED -- HUMAN REVIEW REQUIRED: U12", r.stdout)
        self.assertIn("GATE RESULT: FAIL", r.stdout)
        self.assertIsNone(self._invoked_log_text())

    def test_mutation_proof_reverting_fix_fails_scenario_again(self):
        """FAIL-FIRST/PASS-AFTER at the INTEGRATION level (not just the pure
        function): run the exact same base/head diff that passes cleanly
        today through a copy of the gate script with ZERO_LEG_OVERRIDES
        reverted to empty -- must go back to FAIL, exactly reproducing
        PR #637's real, live failure. Proves the PASS in
        test_reviewed_units_pass_cleanly is actually caused by this fix."""
        self._commit_fixture("verified", "verified", "verified", "verified", "pending",
                              "flip U2/U4/U5/U8 to verified")

        src = _GATE_SCRIPT.read_text()
        needle = 'ZERO_LEG_OVERRIDES = {\n    "skill58-podbean-proxy-2026-07-16.md": frozenset({"U2", "U4", "U5", "U8"}),\n}'
        self.assertIn(
            needle, src,
            "ZERO_LEG_OVERRIDES's literal shape changed -- update this mutation proof's `needle` to "
            "match scripts/ledger-truth-gate.py's current source before trusting this test",
        )
        pre_fix_src = src.replace(needle, "ZERO_LEG_OVERRIDES = {}")
        pre_fix_script = Path(self.tmp) / "pre-fix-ledger-truth-gate.py"
        pre_fix_script.write_text(pre_fix_src)

        r = self._run_gate(script_path=pre_fix_script)
        self.assertEqual(
            r.returncode, 1,
            msg="reverting the fix should make this exact scenario FAIL again (PR #637's real "
                f"failure) -- got:\nstdout:\n{r.stdout}\nstderr:\n{r.stderr}",
        )
        self.assertIn("NOT ENFORCED -- HUMAN REVIEW REQUIRED: U2", r.stdout)


# --------------------------------------------------------------------------
# Section 3: the property this fix must NOT weaken
# --------------------------------------------------------------------------

class FalseClaimStillRejectedElsewhere(unittest.TestCase):
    """A genuinely FALSE `verified` claim for a real, git-checkable unit
    (proper `(ONB, P#)` leg tag, in a ledger file NOT in
    UNPARSEABLE_LEDGER_FILES) must still be mechanically caught as NOT-DONE.
    This exercises unit_status_core.py directly -- the module this fix never
    touches -- as a regression pin proving the core git-truth property is
    intact. Fully offline: the fabricated unit's own-named branch is real
    but provably UNMERGED, so resolve_leg() returns method="own-branch-
    unmerged" and _leg_head_sha() yields no sha to CI-check (see that
    function's docstring) -- no network call is ever made."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ledger-truth-gate-falseclaim-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.onb = Path(self.tmp) / "onb"
        self.onb.mkdir()
        _git(self.onb, "init", "-q", "-b", "main")
        _git(self.onb, "config", "user.email", "test@example.invalid")
        _git(self.onb, "config", "user.name", "Test")

        ledgers = self.onb / "ledgers"
        ledgers.mkdir()
        self.ledger_path = ledgers / "fixture-kanban-style.md"
        self.ledger_path.write_text(
            "| id | desc | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            "| U9001 | (ONB, P0) fabricated fixture unit -- branch exists but is UNMERGED | "
            "[Test x1] fabricated | verified | FALSE CLAIM, fixture-only | 2026-07-18T00:00:00Z |\n"
        )
        (self.onb / "README.md").write_text("fixture repo\n")
        _git(self.onb, "add", "-A")
        _git(self.onb, "commit", "-q", "-m", "main tip")
        main_sha = _git(self.onb, "rev-parse", "HEAD")

        # A REAL branch for this unit id exists -- but is never merged into
        # main. This is what a false "verified" claim looks like when the
        # unit IS mechanically checkable: real, positive evidence of
        # non-completion, not mere silence.
        _git(self.onb, "checkout", "-q", "-b", "skill6-v2/U9001")
        (self.onb / "unmerged-work.txt").write_text("work that never landed\n")
        _git(self.onb, "add", "-A")
        _git(self.onb, "commit", "-q", "-m", "unmerged work for U9001")
        branch_sha = _git(self.onb, "rev-parse", "HEAD")
        _git(self.onb, "checkout", "-q", "main")

        # Fabricate the remote-tracking refs unit_status_core.py reads
        # (`git branch -r`) directly -- no real remote, no network.
        _git(self.onb, "update-ref", "refs/remotes/origin/main", main_sha)
        _git(self.onb, "update-ref", "refs/remotes/origin/skill6-v2/U9001", branch_sha)

    def test_false_claim_with_unmerged_branch_is_not_done(self):
        result = usc.resolve_unit(
            "U9001", onb_dir=str(self.onb), cc_dir=str(self.onb),
            ledger_paths=[str(self.ledger_path)], skip_ci=True,
        )
        self.assertEqual(result["verdict"], "NOT-DONE", msg=result)
        self.assertIs(result["legs"]["onb"]["satisfied"], False)
        self.assertEqual(result["legs"]["onb"]["method"], "own-branch-unmerged")


if __name__ == "__main__":
    unittest.main(verbosity=2)

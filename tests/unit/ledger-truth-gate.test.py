#!/usr/bin/env python3
"""
tests/unit/ledger-truth-gate.test.py
─────────────────────────────────────────────────────────────────────────────
Proves TWO fixes in scripts/ledger-truth-gate.py, layered on top of each
other:

  (1, PR #633/#637, still true) ZERO_LEG_OVERRIDES / classify_ledger_row():
  `ledgers/skill58-podbean-proxy-2026-07-16.md`'s U2/U4/U5/U8 rows are each
  a live n8n/data-table claim with NO repository leg at all (confirmed by
  that ledger's own CONCURRENCY MAP table). A `verified` claim for one of
  these 4 is trusted from the ledger's own status cell -- unit-status.sh is
  never invoked for it at all, since there is no repo leg to check in
  principle.

  (2, 2026-07-19, THIS fix) --ledger SCOPING: before this fix, every OTHER
  unit id in that same file -- including the REAL repo-leg units U12/U14/
  U15/U16/U17/U21 -- was routed to an unconditional "not_enforced" failure,
  forever, even once PR #646 landed real leg-requirement tags on every row
  in the file (proving unit_status_core.py CAN now correctly classify and
  resolve them). The reason for the bypass was a real, empirically-confirmed
  cross-campaign U-numbering collision: unit-status.sh's DEFAULT multi-
  ledger search (no --ledger given) always checks the kanban ledger FIRST,
  so a Skill-58 unit id that also exists in the kanban ledger (U12/U14/U21
  do) would silently resolve against the KANBAN ledger's unrelated row
  instead. THIS fix closes that gap the right way: run_unit_status() now
  passes an explicit `--ledger <path>` scoped to the EXACT file a
  candidate's diff came from whenever that file has a proven collision risk
  (scoped_ledger_for()) -- so find_ledger_row() can never resolve the wrong
  campaign's row. classify_ledger_row() no longer needs a third
  "not_enforced" bucket: only the ZERO_LEG_OVERRIDES allowlist above skips
  the tool now; every other row, in every ledger, gets a REAL, git-derived
  verdict -- while a genuinely false claim (real-looking leg tag, a cited
  SHA that does not exist) is still mechanically rejected, never silently
  passed. This was CI's real, reproduced red check on
  trevorotts1/openclaw-onboarding main after PR #646 landed real leg tags on
  12 already-`verified` S58 rows (U1/U3/U6/U9/U10/U11/U12/U13/U14/U15/U16/
  U17) and the old bypass re-flagged every one of them as NOT ENFORCED.

WHAT EACH TEST CLASS PROVES:
  ClassifyLedgerRowRouting          -- pure, offline unit tests of
                                        classify_ledger_row(): only the
                                        ZERO_LEG_OVERRIDES allowlist skips
                                        the tool now; a repo-leg unit like
                                        U12/U14-U17 can never land on it
                                        (mutation proof included).
  ScopedLedgerForRouting            -- pure, offline unit tests of
                                        scoped_ledger_for(): only a single
                                        UNPARSEABLE_LEDGER_FILES member gets
                                        scoped; every other ledger keeps the
                                        tool's default multi-ledger search,
                                        unchanged from before this fix.
  PodbeanZeroLegEndToEnd            -- real git-repo + real subprocess
                                        invocation of the SHIPPED gate
                                        script against a throwaway fixture
                                        repo with a stub unit-status.sh:
                                        (a) U2/U4/U5/U8 alone -> clean PASS,
                                            stub never invoked (fast path);
                                        (b) U2/U4/U5/U8 PLUS an unreviewed
                                            unit (U12) flipped in the SAME
                                            commit -> the reviewed 4 still
                                            print PASS WITH DISCLAIMER via
                                            the fast path, but U12 now gets
                                            REAL (stub-simulated) enforcement
                                            -- WITH an explicit --ledger
                                            argument -- and still blocks the
                                            whole gate, proving the fix is
                                            surgical, not a blanket
                                            exemption of the file;
                                        (c) an INTEGRATION-level mutation
                                            proof: the exact scenario-(a)
                                            diff, re-run through a copy of
                                            the script with ZERO_LEG_OVERRIDES
                                            reverted to `{}`, fails again
                                            (now via real, stub-simulated
                                            UNKNOWN verdicts, since the fast
                                            path no longer exists to fall
                                            back on).
  S58RealDiffEndToEnd               -- the REAL PR #646 diff against the
                                        REAL trevorotts1/openclaw-onboarding
                                        history: (a) proves the 12
                                        legitimately-tagged S58 rows now
                                        pass the gate honestly, quoting the
                                        real PASS lines; (b) a FAIL-FIRST/
                                        PASS-AFTER mutation proof using the
                                        LITERAL pre-fix script blob (`git
                                        show <ci-red-sha>:scripts/
                                        ledger-truth-gate.py`, not a
                                        synthetic patch) re-run against the
                                        identical diff -- reproduces the
                                        real CI failure again.
  FabricatedS58RowRejectedByGate    -- a FABRICATED `verified` row (a
                                        real-looking `(ONB, P1)` tag, citing
                                        a SHA that does not exist anywhere)
                                        appended to a real, throwaway clone
                                        of the actual repo and run through
                                        the shipped, --ledger-scoped gate --
                                        still mechanically REJECTED. Proves
                                        --ledger scoping changes WHICH file
                                        is searched, never WHETHER a claim
                                        is independently re-derived from
                                        git truth.
  FalseClaimStillRejectedElsewhere   -- the property this fix must NOT
                                        weaken: a genuinely FALSE `verified`
                                        claim for a real, git-checkable unit
                                        (proper leg tag, NOT in an
                                        UNPARSEABLE_LEDGER_FILES member) is
                                        still mechanically caught as
                                        NOT-DONE by unit_status_core.py,
                                        which this fix never touches. Fully
                                        offline -- the fabricated unit's
                                        own-named branch is real but
                                        provably unmerged, so no CI/network
                                        check-run lookup ever fires.

Run:
    python3 tests/unit/ledger-truth-gate.test.py

Env overrides (skip auto-clone, point at an existing checkout -- e.g. a
local merged tree instead of a fresh clone from origin):
    UNIT_STATUS_TEST_ONB_DIR, UNIT_STATUS_TEST_CC_DIR
"""
from __future__ import annotations

import importlib.util
import os
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
    git or the filesystem. PRE-2026-07-19-FIX: every unit id in an
    UNPARSEABLE_LEDGER_FILES member NOT on ZERO_LEG_OVERRIDES routed to
    "not_enforced" -- an unconditional failure, even for a row that was
    genuinely true and (after PR #646's leg tags) mechanically checkable.
    THIS FIX: run_unit_status() now passes unit-status.sh an explicit
    --ledger scoped to the exact file a candidate's diff came from (see
    ScopedLedgerForRouting below), which eliminates the cross-campaign
    collision the "not_enforced" bypass existed to avoid -- so
    classify_ledger_row() no longer needs a third bucket: only the
    hand-reviewed zero-leg allowlist skips the tool; everything else,
    including every repo-leg unit in the same file, now gets "enforce" and
    a REAL git-derived verdict (see S58RealDiffEndToEnd for the end-to-end
    proof this is both correct AND still catches a fabricated claim). These
    tests prove the router is still SURGICAL in the one way that still
    matters: the allowlist (and ONLY the allowlist) skips the tool, and a
    repo-leg unit like U12/U14-U17 can NEVER land on it."""

    def test_reviewed_units_get_zero_leg_override(self):
        for unit_id in ("U2", "U4", "U5", "U8"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(
                    gate.classify_ledger_row(PODBEAN_FILE, unit_id),
                    "zero_leg_override",
                )

    def test_repo_leg_units_in_same_file_now_get_real_enforcement(self):
        # U12/U14/U15/U16/U17/U21 carry a REAL repo leg per this ledger's own
        # CONCURRENCY MAP table -- blanket-trusting them the way U2/U4/U5/U8
        # are trusted would be the exact security regression this fix must
        # avoid, so none of them may EVER appear on the allowlist; they must
        # instead route to "enforce" (real, --ledger-scoped git verification).
        for unit_id in ("U12", "U14", "U15", "U16", "U17", "U21"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, unit_id), "enforce")
                self.assertNotIn(
                    unit_id, gate.ZERO_LEG_OVERRIDES.get(PODBEAN_FILE, frozenset()),
                    f"REGRESSION: {unit_id} carries a REAL repo leg per the podbean ledger's own "
                    f"CONCURRENCY MAP table -- it must NEVER be added to ZERO_LEG_OVERRIDES.",
                )

    def test_unlisted_or_future_unit_also_gets_real_enforcement(self):
        # A unit nobody has reviewed onto the allowlist yet must still be
        # mechanically checked -- never trusted just because it lives in an
        # already-partly-trusted file, and (after this fix) never
        # permanently blocked either, now that the tool can actually check
        # it via a correctly-scoped --ledger.
        for unit_id in ("U1", "U3", "U6", "U9999"):
            with self.subTest(unit_id=unit_id):
                self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, unit_id), "enforce")

    def test_other_ledgers_fully_enforced_unaffected(self):
        self.assertEqual(gate.classify_ledger_row(KANBAN_FILE, "U2"), "enforce")
        self.assertEqual(gate.classify_ledger_row(KANBAN_FILE, "U9999"), "enforce")

    def test_mutation_proof_reverting_override_breaks_it(self):
        """FAIL-FIRST/PASS-AFTER: simulate emptying ZERO_LEG_OVERRIDES and
        confirm U2 reverts from the never-invoke-the-tool fast path
        ("zero_leg_override") to the real-enforcement path ("enforce"),
        then restore it and confirm the fast path is back in effect. This
        is the direct proof that ZERO_LEG_OVERRIDES -- not
        UNPARSEABLE_LEDGER_FILES membership, and not this fix's --ledger
        scoping -- is the one thing still governing this specific bucket."""
        saved = gate.ZERO_LEG_OVERRIDES
        try:
            gate.ZERO_LEG_OVERRIDES = {}
            self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, "U2"), "enforce")
        finally:
            gate.ZERO_LEG_OVERRIDES = saved
        self.assertEqual(gate.classify_ledger_row(PODBEAN_FILE, "U2"), "zero_leg_override")


class ScopedLedgerForRouting(unittest.TestCase):
    """scoped_ledger_for() is also a pure function -- the OTHER half of this
    fix (classify_ledger_row() decides WHETHER to enforce a row; this
    decides WHICH --ledger to scope unit-status.sh to when it does)."""

    def test_single_unparseable_ledger_file_is_scoped(self):
        self.assertEqual(
            gate.scoped_ledger_for({f"ledgers/{PODBEAN_FILE}"}),
            f"ledgers/{PODBEAN_FILE}",
        )

    def test_single_ordinary_ledger_file_is_not_scoped(self):
        # The kanban ledger (and any future non-cross-campaign ledger) keeps
        # the tool's default multi-ledger search, completely unchanged from
        # before this fix -- scoping only ever applies to the one collision
        # case it exists to fix.
        self.assertIsNone(gate.scoped_ledger_for({f"ledgers/{KANBAN_FILE}"}))

    def test_multiple_distinct_paths_are_never_scoped(self):
        # A unit id whose changed rows span more than one ledger file in a
        # single diff is not this fix's problem to silently resolve --
        # falls back to the tool's ordinary default search, exactly as
        # before this fix existed.
        self.assertIsNone(
            gate.scoped_ledger_for({f"ledgers/{PODBEAN_FILE}", f"ledgers/{KANBAN_FILE}"})
        )

    def test_empty_set_is_never_scoped(self):
        self.assertIsNone(gate.scoped_ledger_for(set()))


# --------------------------------------------------------------------------
# Section 2: real git repo + real subprocess invocation of the shipped script
# --------------------------------------------------------------------------

# If zero_leg_override routing ever regresses into calling the real tool,
# this stub makes that failure LOUD (UNKNOWN + a sentinel log) instead of
# silently working by accident -- it must never be invoked for a
# zero_leg_override row. It DOES get invoked for "enforce" rows now (that is
# this fix's whole point) -- test_unreviewed_unit_in_same_file_still_blocks
# below asserts it is invoked WITH an explicit --ledger argument, standing
# in for unit-status.sh returning a verdict it could not confirm.
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
        # proves the fix is surgical: the reviewed 4 still pass via the
        # never-invoke-the-tool fast path, but U12's claim now gets REAL
        # enforcement (the stub simulates unit-status.sh being unable to
        # confirm it) -- still blocks the whole gate for a human, same
        # overall outcome as before this fix, but now for the RIGHT reason
        # (a real verdict, not an unconditional bypass).
        self._commit_fixture("verified", "verified", "verified", "verified", "verified",
                              "flip U2/U4/U5/U8/U12 to verified")
        r = self._run_gate()
        self.assertEqual(r.returncode, 1, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        for unit_id in ("U2", "U4", "U5", "U8"):
            self.assertIn(f"PASS WITH DISCLAIMER (reviewed zero-leg override): {unit_id}", r.stdout)
        self.assertIn("unit U12: verdict=UNKNOWN", r.stdout)
        self.assertIn("GATE RESULT: FAIL", r.stdout)

        invoked = self._invoked_log_text()
        self.assertIsNotNone(
            invoked,
            "unit-status.sh stub was NEVER invoked -- routing regression: U12 (not on "
            "ZERO_LEG_OVERRIDES) must now go through real, --ledger-scoped enforcement.",
        )
        tokens = invoked.split()
        self.assertIn("U12", tokens)
        self.assertIn("--ledger", tokens)
        self.assertIn(f"ledgers/{PODBEAN_FILE}", tokens,
                       "the --ledger argument must be scoped to the exact file U12's row lives in "
                       "-- this is the actual fix for the cross-campaign collision.")
        for unit_id in ("U2", "U4", "U5", "U8"):
            self.assertNotIn(unit_id, tokens,
                              f"{unit_id} is on ZERO_LEG_OVERRIDES -- must never reach unit-status.sh")

    def test_mutation_proof_reverting_fix_fails_scenario_again(self):
        """FAIL-FIRST/PASS-AFTER at the INTEGRATION level (not just the pure
        function): run the exact same base/head diff that passes cleanly
        today through a copy of the gate script with ZERO_LEG_OVERRIDES
        reverted to empty -- must go back to FAIL. With the allowlist
        emptied, U2/U4/U5/U8 all fall through to "enforce" too (this fix's
        classify_ledger_row() has no "not_enforced" bucket to fall back on
        anymore) -- the stub (standing in for a tool that could not verify
        them) returns UNKNOWN for each, so the gate correctly fails again.
        Proves ZERO_LEG_OVERRIDES is still the one thing making
        test_reviewed_units_pass_cleanly pass without invoking the tool at
        all -- exactly reproducing PR #637's original real failure, now
        surfaced via a real (stub-simulated) UNKNOWN verdict instead of the
        retired "not_enforced" notice."""
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
            msg="emptying ZERO_LEG_OVERRIDES should make this exact scenario FAIL again -- got:\n"
                f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}",
        )
        self.assertIn("unit U2", r.stdout)
        self.assertIn("verdict=UNKNOWN", r.stdout)
        self.assertIn("GATE RESULT: FAIL", r.stdout)


# --------------------------------------------------------------------------
# Section 2b: end-to-end against the REAL trevorotts1/openclaw-onboarding
# history -- proves the shipped fix on the REAL PR #646 diff that was
# CI-red before it, and that a fabricated claim in the SAME real,
# --ledger-scoped file is still mechanically rejected. Network + gh auth
# required for S58RealDiffEndToEnd (the real gate script always runs
# unit-status.sh's check-run lookup -- there is no --skip-ci passthrough in
# ledger-truth-gate.py by design, see its own module docstring: "no
# --skip-ci: catching stamps that ignore failing checks is the entire
# point"). FabricatedS58RowRejectedByGate needs network only to clone/fetch
# -- the fabricated row never resolves a checkable head sha, so no `gh api`
# call is ever made for it.
# --------------------------------------------------------------------------

def _clone_or_reuse(url, envvar, cache_name):
    """Same contract as tests/unit/unit-status-historical.test.py's helper
    of the same name (not imported from it -- each test file in this repo
    is self-contained): the env var lets a caller point at an existing
    local checkout -- e.g. the merged tree this fix's own PR branch lives
    on -- instead of a fresh clone from origin."""
    override = os.environ.get(envvar)
    if override:
        assert Path(override).is_dir(), f"{envvar}={override} does not exist"
        subprocess.run(["git", "-C", override, "fetch", "-q", "origin", "main"], check=False)
        return override
    cache_root = Path(os.environ.get("UNIT_STATUS_TEST_CACHE", tempfile.gettempdir())) / "openclaw-git-truth-tools-tests"
    cache_root.mkdir(parents=True, exist_ok=True)
    dest = cache_root / cache_name
    if (dest / ".git").is_dir():
        subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin", "main"], check=False)
    else:
        subprocess.run(["git", "clone", "-q", url, str(dest)], check=True)
    return str(dest)


class S58RealDiffEndToEnd(unittest.TestCase):
    """Runs the SHIPPED scripts/ledger-truth-gate.py (this fix) against the
    REAL diff PR #646 introduced on trevorotts1/openclaw-onboarding's actual
    history -- the exact diff that was CI-red on main before this fix (this
    fix's own repro: base=c040c514 = main tip before PR #646's push,
    head=3fdec236 = PR #646's merge commit, the commit CI ran the red check
    against). Both are real, immutable commits already in history.

    PROVES (a) the task requirement: 'the 12 legitimately-tagged S58 rows
    now pass the gate honestly' -- 5 via real git verification (U12/U14/
    U15/U16/U17) and 7 via the tool's own zero-leg trust mode (U1/U3/U6/
    U9/U10/U11/U13, genuinely computed by unit_status_core.py, NOT the
    hand-maintained ZERO_LEG_OVERRIDES allowlist, which only ever covers
    U2/U4/U5/U8); and (b) a FAIL-FIRST/PASS-AFTER mutation proof against
    the REAL pre-fix script content (not a synthetic patch -- the literal
    scripts/ledger-truth-gate.py blob that was actually on main at the
    CI-red commit), proving the PASS in (a) is genuinely caused by this
    fix, not an artifact of the diff or the test harness."""

    BASE_SHA = "c040c514ee307887c65f3db131dd0f8a08fba274"
    HEAD_SHA = "3fdec236567d25a56a20af29b98d7f4351d62ef8"

    @classmethod
    def setUpClass(cls):
        cls.onb_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/openclaw-onboarding.git",
            "UNIT_STATUS_TEST_ONB_DIR", "openclaw-onboarding",
        )
        cls.cc_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/blackceo-command-center.git",
            "UNIT_STATUS_TEST_CC_DIR", "blackceo-command-center",
        )
        for sha in (cls.BASE_SHA, cls.HEAD_SHA):
            r = subprocess.run(["git", "-C", cls.onb_dir, "cat-file", "-e", sha],
                                capture_output=True, text=True)
            assert r.returncode == 0, (
                f"PRECONDITION FAILED: {sha} not found in {cls.onb_dir} -- clone is missing history "
                f"this fix's own repro depends on (shallow clone? wrong remote?)."
            )

    def _run_real_gate(self, script_path=None):
        script_path = script_path or _GATE_SCRIPT
        return subprocess.run(
            [sys.executable, str(script_path),
             "--base", self.BASE_SHA, "--head", self.HEAD_SHA, "--cc-dir", self.cc_dir],
            cwd=self.onb_dir, capture_output=True, text=True, timeout=180,
        )

    def test_pr646_diff_passes_cleanly_with_shipped_fix(self):
        r = self._run_real_gate()
        self.assertEqual(r.returncode, 0, msg=f"stdout:\n{r.stdout}\nstderr:\n{r.stderr}")
        self.assertIn("PASS (git-verified DONE): U12, U14, U15, U16, U17", r.stdout)
        for unit_id in ("U1", "U3", "U6", "U9", "U10", "U11", "U13"):
            self.assertIn(
                f"PASS WITH DISCLAIMER: {unit_id} -- this unit has no repository leg", r.stdout,
                f"{unit_id} should resolve via the tool's own zero-leg trust mode, computed fresh "
                f"(not the hand-maintained ZERO_LEG_OVERRIDES allowlist, which only covers U2/U4/U5/U8)",
            )
        for unit_id in ("U2", "U4", "U5", "U8"):
            self.assertIn(f"PASS WITH DISCLAIMER (reviewed zero-leg override): {unit_id}", r.stdout)
        self.assertIn("GATE RESULT: PASS.", r.stdout)
        self.assertNotIn("NOT ENFORCED", r.stdout)

    def test_mutation_proof_real_pre_fix_script_reproduces_the_ci_failure(self):
        """The literal pre-fix scripts/ledger-truth-gate.py content, as it
        actually existed on origin/main at the CI-red commit (HEAD_SHA
        itself) -- not a synthetic patch. Reverting to this exact file and
        re-running the identical diff must reproduce the real CI failure
        this fix closes."""
        r = subprocess.run(
            ["git", "-C", self.onb_dir, "show", f"{self.HEAD_SHA}:scripts/ledger-truth-gate.py"],
            capture_output=True, text=True,
        )
        self.assertEqual(r.returncode, 0, msg=f"stderr:\n{r.stderr}")
        pre_fix_src = r.stdout
        self.assertNotIn(
            "scoped_ledger_for", pre_fix_src,
            "PRECONDITION FAILED: the real pre-fix blob at the CI-red commit already contains this "
            "fix's own marker -- either the commit sha is wrong or the fix already existed there.",
        )
        with tempfile.TemporaryDirectory() as td:
            pre_fix_script = Path(td) / "pre-fix-ledger-truth-gate.py"
            pre_fix_script.write_text(pre_fix_src)
            r2 = self._run_real_gate(script_path=pre_fix_script)
        self.assertEqual(
            r2.returncode, 1,
            msg="the real pre-fix script must reproduce the real CI failure on this diff -- got:\n"
                f"stdout:\n{r2.stdout}\nstderr:\n{r2.stderr}",
        )
        self.assertIn("GATE RESULT: FAIL", r2.stdout)
        self.assertIn("NOT ENFORCED -- HUMAN REVIEW REQUIRED: U12", r2.stdout)


class FabricatedS58RowRejectedByGate(unittest.TestCase):
    """PROVES the second half of the task's mutation-proof requirement: a
    FABRICATED 'verified' row -- a real-looking repo-leg tag ('(ONB, P1)',
    the exact shape U14/U15/U16/U17 use), landed on a REAL clone of
    trevorotts1/openclaw-onboarding (so git ancestry is genuinely checked,
    not a synthetic stand-in), citing a SHA that does not exist anywhere in
    the real repo -- is still REJECTED by the shipped, --ledger-scoped
    gate, exactly like a genuine false stamp would be. This is the property
    the fix must NOT weaken: --ledger scoping only changes WHICH file
    find_ledger_row() searches, never WHETHER a claim is independently
    re-derived from git truth."""

    @classmethod
    def setUpClass(cls):
        cls.real_onb_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/openclaw-onboarding.git",
            "UNIT_STATUS_TEST_ONB_DIR", "openclaw-onboarding",
        )
        cls.cc_dir = _clone_or_reuse(
            "https://github.com/trevorotts1/blackceo-command-center.git",
            "UNIT_STATUS_TEST_CC_DIR", "blackceo-command-center",
        )

    def setUp(self):
        # A local-only, throwaway clone of the REAL repo -- so this test's
        # fabricated commit can never touch the shared checkout other tests
        # in this run also use, and never reaches the network/origin.
        self.tmp = tempfile.mkdtemp(prefix="ledger-truth-gate-fabricated-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.repo = Path(self.tmp) / "repo"
        subprocess.run(["git", "clone", "-q", self.real_onb_dir, str(self.repo)], check=True)
        _git(self.repo, "config", "user.email", "test@example.invalid")
        _git(self.repo, "config", "user.name", "Test")
        _git(self.repo, "checkout", "-q", "main")
        self.base_sha = _git(self.repo, "rev-parse", "HEAD")

        ledger_file = self.repo / "ledgers" / PODBEAN_FILE
        assert ledger_file.is_file(), "real S58 ledger not found in the cloned repo -- history drifted?"
        fabricated_row = (
            "| U999305 | (ONB, P1) FABRICATED fixture row for the ledger-truth-gate mutation-proof "
            "test -- must never resolve DONE | [Test x1] fabricated | verified | FABRICATED-EVIDENCE, "
            "never real: merge commit `deadbeef01deadbeef01deadbeef01deadbeef01` merged into "
            "`origin/main`, entirely fake, this SHA does not exist anywhere in the real repo. | "
            "2026-01-01T00:00:00Z |\n"
        )
        with ledger_file.open("a") as f:
            f.write(fabricated_row)
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "test: fabricated verified row, must be rejected")
        self.head_sha = _git(self.repo, "rev-parse", "HEAD")

    def test_fabricated_row_with_nonexistent_sha_is_rejected(self):
        r = subprocess.run(
            [sys.executable, str(_GATE_SCRIPT),
             "--base", self.base_sha, "--head", self.head_sha, "--cc-dir", self.cc_dir],
            cwd=self.repo, capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(
            r.returncode, 1,
            msg=f"a fabricated verified claim must FAIL the gate -- got:\nstdout:\n{r.stdout}\n"
                f"stderr:\n{r.stderr}",
        )
        self.assertNotIn("PASS WITH DISCLAIMER (reviewed zero-leg override): U999305", r.stdout)
        self.assertNotIn("PASS (git-verified DONE): U999305", r.stdout)
        self.assertIn("unit U999305", r.stdout)
        self.assertNotIn("unit U999305: verdict=DONE", r.stdout)
        self.assertIn("GATE RESULT: FAIL", r.stdout)


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

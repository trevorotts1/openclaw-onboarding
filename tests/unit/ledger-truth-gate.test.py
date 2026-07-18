#!/usr/bin/env python3
"""
tests/unit/ledger-truth-gate.test.py
─────────────────────────────────────────────────────────────────────────────
Proves scripts/ledger-truth-gate.py's fix for the cross-campaign unit-id
collision that used to force `ledgers/skill58-podbean-proxy-2026-07-16.md`
onto UNPARSEABLE_LEDGER_FILES (an always-fail, human-review-required path,
even for genuinely true rows -- see that file's own module docstring).

THE BUG THIS FILE PROVES WAS REAL (not hypothetical): `unit-status.sh <id>`
(no `--ledger` filter) searches every ledgers/*.md file -- kanban ledger
first, then the rest alphabetically -- and `find_ledger_row()` returns the
FIRST row matching the id. The kanban ledger's OWN U2/U4/U5/U8 rows (real,
already-verified, git-checkable units) collide with the podbean ledger's
OWN U2/U4/U5/U8 rows (real, live-n8n-verified, zero-repo-leg units) -- two
totally unrelated campaigns sharing bare `U<n>` numbering. An unscoped
lookup for "U2" silently returns the WRONG file's row.

THE FIX (both parts, proven separately below):
  1. `run_unit_status()` now always passes `--ledger <the exact file a
     candidate row was diffed out of>`, scoping every check to that one
     file. This makes the collision structurally unreachable from the
     gate's call site, for ANY ledger, not just the podbean one.
  2. `ledgers/skill58-podbean-proxy-2026-07-16.md` now opens its zero-leg
     rows' `desc` column with a `(live, P#)` tag (the same grammar as the
     kanban ledger's own `(doc, P#)` zero-leg rows) so the tool's leg-tag
     parser can read them at all, instead of returning `mode=unknown`.

With both fixes in place, `skill58-podbean-proxy-2026-07-16.md` was removed
from UNPARSEABLE_LEDGER_FILES -- proven below, plus proof the removal does
NOT create a hole: a genuinely FALSE verified/done claim, in the very same
diff as a genuinely true zero-leg claim, is still independently and
correctly rejected as NOT-DONE.

All tests here are OFFLINE / no network: real on-disk ledger files are read
directly for the collision-precondition and row-format tests; the
end-to-end gate test builds a fully local, throwaway git repo (no remote,
no `gh api` calls reachable -- the fixture's units are either zero-leg
(skips CI/network entirely) or a repo leg resolved via plain local `git`
ref/ancestor plumbing).

Run:
    python3 tests/unit/ledger-truth-gate.test.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SCRIPTS = _REPO_ROOT / "scripts"
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
_LEDGERS = _REPO_ROOT / "ledgers"
assert _SCRIPTS.is_dir() and _SHARED_UTILS.is_dir() and _LEDGERS.is_dir()

sys.path.insert(0, str(_SHARED_UTILS))
sys.path.insert(0, str(_SCRIPTS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore
    return mod


usc = _load("unit_status_core", _SHARED_UTILS / "unit_status_core.py")
gate = _load("ledger_truth_gate", _SCRIPTS / "ledger-truth-gate.py")

KANBAN_LEDGER = _LEDGERS / "skill6-blended-persona-kanban-v2-2026-07-13.md"
PODBEAN_LEDGER = _LEDGERS / "skill58-podbean-proxy-2026-07-16.md"
assert KANBAN_LEDGER.is_file() and PODBEAN_LEDGER.is_file()


class CollisionIsRealAndScopingFixesIt(unittest.TestCase):
    """Offline, against the REAL, on-disk ledgers -- the collision this class
    proves is live in this repo's actual history, not a synthesized case."""

    COLLIDING_IDS = ["U2", "U4", "U5", "U8"]

    def test_precondition_kanban_and_podbean_both_have_these_bare_ids(self):
        """PRECONDITION: both ledgers must actually carry a row for each id,
        or the collision this class exists to prove is meaningless."""
        for uid in self.COLLIDING_IDS:
            _, kanban_row = usc.find_ledger_row([str(KANBAN_LEDGER)], uid)
            _, podbean_row = usc.find_ledger_row([str(PODBEAN_LEDGER)], uid)
            self.assertIsNotNone(kanban_row, f"PRECONDITION FAILED: kanban ledger has no {uid} row anymore.")
            self.assertIsNotNone(podbean_row, f"PRECONDITION FAILED: podbean ledger has no {uid} row anymore.")
            self.assertNotEqual(
                kanban_row, podbean_row,
                f"PRECONDITION FAILED: {uid}'s row text is now IDENTICAL in both ledgers -- "
                f"the collision (two DIFFERENT units sharing one id) no longer exists; this "
                f"test class needs re-deriving against whatever real collision replaced it.",
            )

    def test_unscoped_lookup_silently_returns_the_wrong_file(self):
        """FAIL-FIRST PROOF the bug was real: unit-status.sh's own default
        ledger search order is kanban-first (see unit-status.sh's LEDGER_ARGS
        default block), so an unscoped find_ledger_row() over both files
        must return the KANBAN row for every colliding id -- even though the
        podbean ledger has its own, unrelated row for that same id. This is
        exactly the silent wrong-unit-judged risk the gate used to guard
        against only by blanket-failing the whole file."""
        for uid in self.COLLIDING_IDS:
            path, _ = usc.find_ledger_row([str(KANBAN_LEDGER), str(PODBEAN_LEDGER)], uid)
            self.assertEqual(
                path, str(KANBAN_LEDGER),
                f"{uid}: expected the unscoped, kanban-first search to reproduce the collision "
                f"(kanban's row wins) -- got {path}. If upstream ledger discovery order changed, "
                f"this precondition needs updating.",
            )

    def test_scoped_lookup_reads_the_correct_podbean_row(self):
        """THE FIX's effect at the lookup layer: scoping ledger_paths to just
        the podbean file makes find_ledger_row() return the RIGHT row for
        every colliding id, regardless of what the kanban ledger also calls
        that id."""
        for uid in self.COLLIDING_IDS:
            path, row = usc.find_ledger_row([str(PODBEAN_LEDGER)], uid)
            self.assertEqual(path, str(PODBEAN_LEDGER))
            self.assertIn(f"| {uid} |", row)

    def test_run_unit_status_always_passes_a_scoped_ledger_flag(self):
        """MUTATION PROOF at the call-construction layer: run_unit_status()
        must build a command that includes `--ledger <the exact path it was
        given>`. FAILS on a reverted copy of the function (the pre-fix
        signature took no ledger_path argument and never emitted --ledger at
        all, so `--ledger` would be entirely absent from the captured argv)."""
        captured = {}

        def fake_run(cmd, capture_output, text, timeout):
            captured["cmd"] = cmd
            class R:
                returncode = 0
                stdout = '{"unit": "U2", "verdict": "DONE"}'
                stderr = ""
            return R()

        orig = gate.subprocess.run
        gate.subprocess.run = fake_run
        try:
            gate.run_unit_status("U2", "/fake-cc-dir", str(PODBEAN_LEDGER))
        finally:
            gate.subprocess.run = orig

        cmd = captured["cmd"]
        self.assertIn("--ledger", cmd, f"REGRESSION: no --ledger flag in the invoked command: {cmd}")
        idx = cmd.index("--ledger")
        self.assertEqual(
            cmd[idx + 1], str(PODBEAN_LEDGER),
            f"REGRESSION: --ledger must be followed by the exact path run_unit_status() was given, "
            f"got {cmd[idx + 1]!r}",
        )
        self.assertEqual(
            cmd[:4], ["./unit-status.sh", "U2", "--cc-dir", "/fake-cc-dir"],
            f"unexpected command shape: {cmd}",
        )


class PodbeanRowsNowZeroLegParseable(unittest.TestCase):
    """Offline, against the REAL, on-disk podbean ledger: proves the row-
    format half of the fix -- U2/U4/U5/U8's desc columns now open with a
    `(live, P#)` tag the tool recognizes as zero-leg, instead of falling
    into `mode=unknown` (which can never pass the gate mechanically no
    matter how true the underlying claim is)."""

    UNITS = ["U2", "U4", "U5", "U8"]

    def test_real_rows_resolve_zero_leg(self):
        for uid in self.UNITS:
            _, row_text = usc.find_ledger_row([str(PODBEAN_LEDGER)], uid)
            cells = [c.strip() for c in row_text.strip().strip("|").split("|")]
            desc = cells[1]
            legs, mode, note = usc.resolve_required_legs(desc)
            self.assertEqual(mode, "zero-leg", f"{uid}: expected zero-leg, got {mode!r} ({note}) for desc={desc!r}")
            self.assertEqual(legs, set())

    def test_fail_first_without_the_tag_the_same_rows_were_unknown(self):
        """Reproduce the PRE-FIX text inline (same content, tag stripped) and
        confirm it resolves 'unknown', not 'zero-leg' -- proving the `(live,
        P#)` prefix is what actually changed the classification, not some
        other incidental difference."""
        for uid in self.UNITS:
            _, row_text = usc.find_ledger_row([str(PODBEAN_LEDGER)], uid)
            cells = [c.strip() for c in row_text.strip().strip("|").split("|")]
            desc = cells[1]
            self.assertTrue(desc.startswith("(live, P1) "), f"{uid}: expected the (live, P1) prefix, got {desc!r}")
            pre_fix_desc = desc[len("(live, P1) "):]
            legs, mode, note = usc.resolve_required_legs(pre_fix_desc)
            self.assertEqual(
                mode, "unknown",
                f"{uid}: PRECONDITION FAILED -- the untagged text no longer resolves 'unknown' "
                f"(got {mode!r}); the mutation proof is meaningless without a real pre-fix FAIL case.",
            )


class UnparseableLedgerFilesNoLongerNeedsPodbean(unittest.TestCase):
    def test_podbean_file_removed_from_the_exemption_list(self):
        self.assertNotIn(
            "skill58-podbean-proxy-2026-07-16.md", gate.UNPARSEABLE_LEDGER_FILES,
            "REGRESSION: the podbean ledger is back on the blanket NOT-ENFORCED exemption list -- "
            "it should now be handled by scoped lookup + a real zero-leg tag instead.",
        )


class EndToEndGateFixture(unittest.TestCase):
    """Builds a fully local, throwaway git repo (no network, no remote) with
    TWO ledger files that share a bare unit id across unrelated campaigns --
    the exact shape of the real kanban/podbean collision -- and runs the
    REAL scripts/ledger-truth-gate.py (as a subprocess, exercising the whole
    diff -> candidate -> scoped-check -> verdict pipeline end to end) against
    a single diff that flips BOTH files' same-numbered row to `verified` at
    once. Proves, in one gate run:
      (a) the genuinely TRUE, zero-leg claim (podbean-shaped) passes cleanly
          (PASS WITH DISCLAIMER), scoped correctly to its own file;
      (b) the genuinely FALSE claim (kanban-shaped, citing a real but
          UNMERGED branch) is still independently caught as NOT-DONE, in
          the SAME diff, under the SAME colliding id -- proving the fix does
          not blanket-pass everything in a scoped file, only what the git/
          live evidence actually backs.
    """

    UID = "U500002"  # deliberately not a real unit id in either real ledger

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls._tmp.name)

        (cls.repo / "scripts").mkdir()
        (cls.repo / "shared-utils").mkdir()
        (cls.repo / "ledgers").mkdir()
        cls._copy(_SCRIPTS / "ledger-truth-gate.py", cls.repo / "scripts" / "ledger-truth-gate.py")
        cls._copy(_REPO_ROOT / "unit-status.sh", cls.repo / "unit-status.sh")
        (cls.repo / "unit-status.sh").chmod(0o755)
        cls._copy(_SHARED_UTILS / "unit_status_core.py", cls.repo / "shared-utils" / "unit_status_core.py")
        cls._copy(_SHARED_UTILS / "ledger_reconciler_core.py", cls.repo / "shared-utils" / "ledger_reconciler_core.py")

        cls.kanban_fixture = cls.repo / "ledgers" / "campaign-a-kanban-fixture.md"
        cls.podbean_fixture = cls.repo / "ledgers" / "campaign-b-podbean-fixture.md"
        cls.kanban_fixture.write_text(
            "# CAMPAIGN A KANBAN-SHAPED FIXTURE LEDGER\n\n"
            "| id | desc | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            f"| {cls.UID} | (ONB, P1) Campaign-A's own {cls.UID} -- a git-leg unit, unrelated to "
            f"Campaign B's same-numbered unit | [test] build {cls.UID} | pending | not started | "
            "2026-01-01T00:00:00Z |\n"
        )
        cls.podbean_fixture.write_text(
            "# CAMPAIGN B PODBEAN-SHAPED FIXTURE LEDGER\n\n"
            "| id | desc | label | status | evidence | timestamp |\n"
            "|---|---|---|---|---|---|\n"
            f"| {cls.UID} | (live, P1) Campaign-B's own {cls.UID} -- a live n8n-API unit, unrelated "
            f"to Campaign A's same-numbered unit | [test] build {cls.UID} | pending | not started | "
            "2026-01-01T00:00:00Z |\n"
        )

        cls._git(["init", "-q"])
        cls._git(["config", "user.email", "test@example.com"])
        cls._git(["config", "user.name", "Test Fixture"])
        cls._git(["add", "-A"])
        cls._git(["commit", "-q", "-m", "base: both campaigns pending"])
        cls.base_sha = cls._git(["rev-parse", "HEAD"]).strip()

        # An UNMERGED "feature branch" commit for campaign-A's unit -- never
        # lands on the base->head line. This is the real, present evidence
        # that campaign-A's row is a FALSE verified/done claim.
        cls._git(["checkout", "-q", "-b", "feature-branch", cls.base_sha])
        (cls.repo / "feature-file.txt").write_text("unmerged feature work\n")
        cls._git(["add", "-A"])
        cls._git(["commit", "-q", "-m", "feature: unmerged"])
        cls.feature_sha = cls._git(["rev-parse", "HEAD"]).strip()

        # Back on main line at base: the HEAD commit flips BOTH fixtures'
        # same-numbered row pending -> verified, in ONE diff.
        cls._git(["checkout", "-q", "-B", "main", cls.base_sha])
        cls.kanban_fixture.write_text(
            cls.kanban_fixture.read_text().replace(
                "| pending | not started | 2026-01-01T00:00:00Z |",
                "| verified | FALSE CLAIM: no real merge backs this row -- planted by the test fixture "
                "| 2026-01-02T00:00:00Z |",
            )
        )
        cls.podbean_fixture.write_text(
            cls.podbean_fixture.read_text().replace(
                "| pending | not started | 2026-01-01T00:00:00Z |",
                "| verified | LIVE-PROVEN (fixture): genuine live n8n evidence, no repo leg exists for "
                "this unit | 2026-01-02T00:00:00Z |",
            )
        )
        cls._git(["add", "-A"])
        cls._git(["commit", "-q", "-m", "head: both campaigns flip to verified in the SAME diff"])
        cls.head_sha = cls._git(["rev-parse", "HEAD"]).strip()

        # Fake remote refs -- no real remote/network needed, just refs under
        # refs/remotes/origin/* for the ancestor/branch-discovery plumbing.
        cls._git(["update-ref", "refs/remotes/origin/main", cls.head_sha])
        cls._git(["update-ref", "refs/remotes/origin/skill6-v2/" + cls.UID, cls.feature_sha])

        cls.cc_dir = Path(tempfile.mkdtemp())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    @classmethod
    def _copy(cls, src, dst):
        dst.write_bytes(src.read_bytes())

    @classmethod
    def _git(cls, args):
        r = subprocess.run(["git"] + args, cwd=cls.repo, capture_output=True, text=True)
        assert r.returncode == 0, f"git {args} failed: {r.stderr}"
        return r.stdout

    def _run_gate(self):
        r = subprocess.run(
            [sys.executable, "scripts/ledger-truth-gate.py",
             "--base", self.base_sha, "--head", self.head_sha, "--cc-dir", str(self.cc_dir)],
            cwd=self.repo, capture_output=True, text=True,
        )
        return r

    def test_two_files_same_id_one_true_one_false_both_correctly_judged(self):
        r = self._run_gate()
        out = r.stdout

        self.assertIn(
            f"PASS WITH DISCLAIMER: {self.UID}", out,
            f"REGRESSION: the genuinely true, zero-leg podbean-shaped claim must pass cleanly.\n{out}",
        )
        self.assertIn(
            f"unit {self.UID} (ledgers/campaign-a-kanban-fixture.md): NOT-DONE", out,
            f"REGRESSION: the genuinely FALSE, unmerged-branch kanban-shaped claim must still be "
            f"rejected, in the very same diff, under the same colliding id.\n{out}",
        )
        self.assertEqual(
            r.returncode, 1,
            f"the overall gate must still FAIL (a real false stamp is present) even though the "
            f"colliding true claim passed -- got exit {r.returncode}.\n{out}",
        )

    def test_why_the_fix_is_needed_unscoped_cli_call_reads_the_wrong_file(self):
        """Demonstrates, via the REAL bash CLI (not just the Python function),
        exactly why scoped lookup was necessary: calling `./unit-status.sh
        <id>` the OLD way -- no `--ledger` at all, the general-purpose,
        multi-ledger default every OTHER (human, interactive) caller still
        gets -- resolves this id to campaign-A's row (alphabetically first
        among this fixture's two files, same effect as kanban-vs-podbean in
        the real repo), never reaching campaign-B's real, true claim. This
        directly justifies why `run_unit_status()` (tested above) must never
        make this same bare, unscoped call -- unit-status.sh's own default
        behavior is deliberately left unchanged for interactive use (a human
        who wants a specific file must pass --ledger by hand); the fix lives
        entirely in what the GATE passes, not in the tool's own default."""
        r = subprocess.run(
            ["./unit-status.sh", self.UID, "--cc-dir", str(self.cc_dir), "--json"],
            cwd=self.repo, capture_output=True, text=True,
        )
        import json
        result = json.loads(r.stdout)
        # Compare resolved (realpath) paths -- macOS's /tmp -> /private/tmp
        # symlink means the bash/python tool chain and this test's own
        # tempfile.TemporaryDirectory() can report the SAME file under two
        # textually-different-but-identical absolute paths; that's a macOS
        # path-canonicalization detail, not the thing this test proves.
        self.assertEqual(
            Path(result.get("ledger_row_path")).resolve(), self.kanban_fixture.resolve(),
            "PRECONDITION FAILED: an unscoped call was expected to reproduce the collision "
            "(campaign-A's row wins alphabetically) -- if unit-status.sh's own default ledger "
            "discovery order changed, this proof needs re-deriving.\n"
            f"Unscoped lookup actually resolved: {result.get('ledger_row_path')}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

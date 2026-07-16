#!/usr/bin/env python3
"""
scripts/tests/u93-rename-shims.test.py
─────────────────────────────────────────────────────────────────────────────
U93 (X/U-X3) — proves the two rename+shim pairs the unit owns
(32-command-center-setup/scripts/heartbeat-canary-probe.py ->
heartbeat-embedding-probe.py; scripts/loop-protection-canary.sh ->
loop-protection-first-proof.sh) actually behave identically via the OLD
(shim) path and the NEW path, and that the docs-language CI guard (U92) sees
zero unexplained new occurrences of the retired term in this unit's own diff.

Hermetic: every fixture (the SQLite DB, the git repo used for the guard
live-fire check) is built in a disposable tempdir. Never touches a live box,
never touches the real ~/.openclaw tree.

Run:
    python3 scripts/tests/u93-rename-shims.test.py
"""
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Wall-clock-derived tokens in the probe's stdout that are EXPECTED to differ
# between two back-to-back invocations even against the identical fixture DB
# (a fresh secrets.token_hex(8) row id per run; embedding_age_days computed
# from "now minus the fixture's insert timestamp", which ticks between the
# old-path and new-path subprocess calls). Masking these — and ONLY these —
# before comparing is what makes the parity check a real behavioral proof
# rather than a flaky clock race: every other byte of output (status,
# counts, coverage, recall ratio, dark_reason) must still match exactly.
_ROW_ID_RE = re.compile(r"id=[0-9a-f]{16}")
_AGE_DAYS_RE = re.compile(r"(embedding_age_days:\s+)[0-9.eE+-]+")


def _normalize(stdout: str) -> str:
    out = _ROW_ID_RE.sub("id=<ID>", stdout)
    out = _AGE_DAYS_RE.sub(r"\1<AGE>", out)
    return out

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent

_HEARTBEAT_NEW = _REPO_ROOT / "32-command-center-setup" / "scripts" / "heartbeat-embedding-probe.py"
_HEARTBEAT_OLD_SHIM = _REPO_ROOT / "32-command-center-setup" / "scripts" / "heartbeat-canary-probe.py"
_LOOP_NEW = _REPO_ROOT / "scripts" / "loop-protection-first-proof.sh"
_LOOP_OLD_SHIM = _REPO_ROOT / "scripts" / "loop-protection-canary.sh"
_ALLOWLIST = _REPO_ROOT / "scripts" / "docs-language-allowlist.json"
_GUARD = _REPO_ROOT / "scripts" / "check-docs-language.py"


def _make_fixture_db(tmp_path: Path, *, sops: int, embedded: int, personas: int) -> Path:
    """A minimal, hermetic mission-control.db with just enough shape for the
    probe's row-count reads (sops / sop_embeddings / persona_index)."""
    db_path = tmp_path / "mission-control.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE sops (
          id TEXT PRIMARY KEY, name TEXT, task_keywords TEXT, description TEXT
        );
        CREATE TABLE sop_embeddings (
          sop_id TEXT PRIMARY KEY, updated_at TEXT
        );
        CREATE TABLE persona_index (id TEXT PRIMARY KEY);
        """
    )
    for i in range(sops):
        conn.execute(
            "INSERT INTO sops (id, name, task_keywords, description) VALUES (?, ?, ?, ?)",
            (f"sop_{i}", f"SOP {i}", "onboard", "how to onboard a new hire"),
        )
    for i in range(embedded):
        conn.execute(
            "INSERT INTO sop_embeddings (sop_id, updated_at) VALUES (?, datetime('now'))",
            (f"sop_{i}",),
        )
    for i in range(personas):
        conn.execute("INSERT INTO persona_index (id) VALUES (?)", (f"p_{i}",))
    conn.commit()
    conn.close()
    return db_path


class TestBothFilesExistAndAreExecutable(unittest.TestCase):
    def test_new_paths_exist_and_are_executable(self):
        for p in (_HEARTBEAT_NEW, _LOOP_NEW):
            self.assertTrue(p.is_file(), f"{p} missing")
            self.assertTrue(os.access(p, os.X_OK), f"{p} not executable")

    def test_old_paths_exist_as_executable_shims(self):
        for p in (_HEARTBEAT_OLD_SHIM, _LOOP_OLD_SHIM):
            self.assertTrue(p.is_file(), f"{p} missing — the D20 one-release shim is required")
            self.assertTrue(os.access(p, os.X_OK), f"{p} not executable")

    def test_shims_are_much_smaller_than_the_real_scripts(self):
        """A non-hollow-suite guard: the shim files must be THIN delegates,
        not a second copy of the real logic (which would silently fork
        behavior the moment one side is edited and the other isn't)."""
        self.assertLess(_HEARTBEAT_OLD_SHIM.stat().st_size, _HEARTBEAT_NEW.stat().st_size / 3)
        self.assertLess(_LOOP_OLD_SHIM.stat().st_size, _LOOP_NEW.stat().st_size / 3)


class TestHeartbeatProbeShimParity(unittest.TestCase):
    """The exact --db-pointed, --dry-run invocation must produce
    byte-identical stdout and the same exit code via the old (shim) path and
    the new path, against the SAME fixture DB."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, script: Path, db_path: Path, *, box_id="u93-test-box") -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(script), "--db", str(db_path), "--dry-run", "--box-id", box_id],
            capture_output=True, text=True, timeout=30,
        )

    def test_healthy_box_identical_via_old_and_new_path(self):
        db = _make_fixture_db(self.tmp_path, sops=10, embedded=10, personas=5)
        new_res = self._run(_HEARTBEAT_NEW, db)
        old_res = self._run(_HEARTBEAT_OLD_SHIM, db)
        self.assertEqual(new_res.returncode, 0, new_res.stdout + new_res.stderr)
        self.assertEqual(old_res.returncode, new_res.returncode)
        self.assertEqual(
            _normalize(old_res.stdout), _normalize(new_res.stdout),
            "shim stdout diverged from the new path (beyond the expected clock/row-id jitter)",
        )
        self.assertIn("healthy", new_res.stdout)

    def test_dark_box_identical_via_old_and_new_path(self):
        """sops loaded, zero embeddings -> dark (exit 2) on BOTH paths."""
        db = _make_fixture_db(self.tmp_path, sops=25, embedded=0, personas=5)
        new_res = self._run(_HEARTBEAT_NEW, db)
        old_res = self._run(_HEARTBEAT_OLD_SHIM, db)
        self.assertEqual(new_res.returncode, 2, new_res.stdout + new_res.stderr)
        self.assertEqual(old_res.returncode, 2)
        self.assertEqual(_normalize(old_res.stdout), _normalize(new_res.stdout))
        self.assertIn("dark", new_res.stdout)

    def test_shim_forwards_argv_correctly_bad_flag_same_usage_error(self):
        """A malformed invocation must fail identically via both paths (argv
        forwarding proof, not just the happy path)."""
        new_res = subprocess.run(
            [sys.executable, str(_HEARTBEAT_NEW), "--no-such-flag"],
            capture_output=True, text=True, timeout=15,
        )
        old_res = subprocess.run(
            [sys.executable, str(_HEARTBEAT_OLD_SHIM), "--no-such-flag"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(old_res.returncode, new_res.returncode)
        self.assertNotEqual(new_res.returncode, 0)


class TestLoopProtectionShimParity(unittest.TestCase):
    """--self-test is itself a hermetic, sandboxed offline drill (uses a
    mktemp state dir internally) — both paths must produce byte-identical
    output. Covered end-to-end already by scripts/test-loop-protection-wiring.sh
    W7/W10; re-proven here at the unit level so this test file alone is
    sufficient evidence without requiring the wiring script."""

    def test_self_test_output_identical_via_old_and_new_path(self):
        new_res = subprocess.run(
            ["bash", str(_LOOP_NEW), "--self-test"],
            capture_output=True, text=True, timeout=60,
        )
        old_res = subprocess.run(
            ["bash", str(_LOOP_OLD_SHIM), "--self-test"],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(new_res.returncode, 0, new_res.stdout + new_res.stderr)
        self.assertEqual(old_res.returncode, 0, old_res.stdout + old_res.stderr)
        self.assertEqual(old_res.stdout, new_res.stdout)


class TestOldShimBreaksLoudlyIfTargetGoesMissing(unittest.TestCase):
    """Fail-closed proof: if the new script is ever deleted while the old
    shim survives (a partial-revert or partial-fleet-sync scenario), BOTH
    shims must error loudly (non-zero exit, message naming the missing
    target) instead of silently no-op'ing."""

    def test_python_shim_errors_when_target_missing(self):
        with tempfile.TemporaryDirectory() as td:
            shim_copy = Path(td) / "heartbeat-canary-probe.py"
            shutil.copy2(_HEARTBEAT_OLD_SHIM, shim_copy)
            os.chmod(shim_copy, 0o755)
            # deliberately do NOT copy heartbeat-embedding-probe.py alongside it
            res = subprocess.run(
                [sys.executable, str(shim_copy), "--dry-run"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("not found", res.stderr)

    def test_bash_shim_errors_when_target_missing(self):
        with tempfile.TemporaryDirectory() as td:
            shim_copy = Path(td) / "loop-protection-canary.sh"
            shutil.copy2(_LOOP_OLD_SHIM, shim_copy)
            os.chmod(shim_copy, 0o755)
            res = subprocess.run(
                ["bash", str(shim_copy), "--self-test"],
                capture_output=True, text=True, timeout=15,
            )
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("not found", res.stdout + res.stderr)


class TestDocsLanguageAllowlistShrunk(unittest.TestCase):
    """Structural proof (never a substring grep) that the U93-owned allowlist
    entries were removed and the U30-owned ones were left alone — the D20
    dependency note's "guard allowlist shrinks in the same PR" requirement."""

    def setUp(self):
        self.data = json.loads(_ALLOWLIST.read_text(encoding="utf-8"))
        self.paths = {e["path"] for e in self.data["legacy_filenames"]["entries"]}

    def test_u93_owned_entries_removed(self):
        self.assertNotIn("32-command-center-setup/scripts/heartbeat-canary-probe.py", self.paths)
        self.assertNotIn("scripts/loop-protection-canary.sh", self.paths)

    def test_u30_owned_entries_untouched(self):
        """U93 must not disturb U30's entries — but it must NOT pin them as an
        exact set either. U30/B-U16 owns those four rows and removes them when
        it lands its own rename; the two units ride independent branches and
        either order is legal. An assertEqual against the full U30 set encodes
        a merge-order assumption, not a U93 invariant, and goes red the moment
        U30 lands first (proven: it did, 2026-07-16) even though U93 is
        correct. The real invariant is directional and order-free: every path
        still listed is one of U30's, so U93 neither removed one of U30's rows
        early nor added a row of its own."""
        u30_owned = {
            "06-ghl-install-pages/scripts/run-selector-canary.sh",
            "06-ghl-install-pages/tests/test_ghl_selector_canary.py",
            "06-ghl-install-pages/tests/test_iframe_survival_canary.py",
            "06-ghl-install-pages/tools/ghl_selector_canary.py",
        }
        self.assertTrue(
            self.paths <= u30_owned,
            f"allowlist carries entries U93 does not expect: {sorted(self.paths - u30_owned)}",
        )
        # Whatever survives must still be attributed to U30, never re-owned.
        for entry in self.data["legacy_filenames"]["entries"]:
            self.assertEqual(entry["owner"], "U30", f"unexpected owner on {entry['path']}")


class TestDocsLanguageGuardLiveFireOnRealDiff(unittest.TestCase):
    """The actual CI guard (U92), run for real against THIS unit's live diff
    on disk vs the merge-base — not a synthetic fixture repo. If any of the
    doc-prose edits in this unit reintroduced an unexplained occurrence of
    the retired term (e.g. by citing the now-unlisted old filenames), this
    fails loudly and names the exact file:line."""

    def setUp(self):
        # Skip cleanly (not a false pass) when this checkout has no git
        # history to diff against — e.g. a tarball extraction in some CI
        # sandbox — rather than mis-reporting a guard failure that isn't one.
        if not (_REPO_ROOT / ".git").exists():
            self.skipTest("no .git directory in this checkout — nothing to diff")
        base_ref = os.environ.get("U93_TEST_BASE_REF", "origin/main")
        check = subprocess.run(
            ["git", "rev-parse", "--verify", "-q", base_ref],
            cwd=_REPO_ROOT, capture_output=True, text=True,
        )
        if check.returncode != 0:
            self.skipTest(f"base ref {base_ref!r} not resolvable in this checkout")
        self.base_ref = base_ref

    def test_guard_passes_on_the_real_working_tree_diff(self):
        res = subprocess.run(
            [sys.executable, str(_GUARD), "--base-ref", self.base_ref, "--repo-root", str(_REPO_ROOT)],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(
            res.returncode, 0,
            f"docs-language guard found unexplained occurrences in this unit's diff:\n{res.stdout}\n{res.stderr}",
        )


if __name__ == "__main__":
    unittest.main()

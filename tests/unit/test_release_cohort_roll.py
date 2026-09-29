#!/usr/bin/env python3
"""JGT102: scripts/roll-release-cohort.py rolls release-cohort.json's
onb_version/cc_version to match /version and cc-compat.json's pinnedTag,
and scripts/bump-version.sh calls it on every bump (and reports drift under
--check).

release-cohort.json (spec 14.8/17.4) is the tested onb_version/cc_version
pair that shared-utils/decision_engine_train/train.py's
check_release_cohort()/promote() gate JEV promotion on. Nothing rolled it on
a version bump, so it went stale every release (caught by
tests/unit/test_release_cohort_manifest.py::test_instance_versions_match_live_repo_contracts).
This suite proves the roll script and its bump-version.sh wiring, offline,
against a throwaway temp repo tree — never the real clone.

It FAILS on origin/main because scripts/roll-release-cohort.py does not
exist there yet.

Run: python3 -m pytest tests/unit/test_release_cohort_roll.py -q
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "roll-release-cohort.py"
_BUMP = _REPO_ROOT / "scripts" / "bump-version.sh"

_STALE_ONB_SHA = "a" * 40
_STALE_CC_SHA = "b" * 40


def _run(*args, **kwargs):
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        capture_output=True, text=True, timeout=15, **kwargs)


def _make_repo(tmp_path, cohort_extra=None):
    """A minimal temp repo tree: version v9.9.9, pinnedTag v1.2.3, a stale
    release-cohort.json. Mirrors the real repo's own layout just enough for
    the roll script to read from and write to."""
    (tmp_path / "version").write_text("v9.9.9\n", encoding="utf-8")
    (tmp_path / "cc-compat.json").write_text(
        json.dumps({"commandCenter": {"pinnedTag": "v1.2.3"}}),
        encoding="utf-8")
    cohort = {
        "onb_sha": _STALE_ONB_SHA,
        "cc_sha": _STALE_CC_SHA,
        "onb_version": "v9.0.0",
        "cc_version": "v1.0.0",
        "contract": "1.1.0",
        "notes": "pre-existing note that must survive the roll untouched",
    }
    if cohort_extra:
        cohort.update(cohort_extra)
    (tmp_path / "release-cohort.json").write_text(
        json.dumps(cohort, indent=2) + "\n", encoding="utf-8")
    return cohort


class ScriptExists(unittest.TestCase):
    def test_script_exists(self):
        self.assertTrue(_SCRIPT.is_file(),
                        "scripts/roll-release-cohort.py is missing")


class Roll(unittest.TestCase):
    def test_check_reports_stale_then_roll_fixes_it(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)

            # --check BEFORE the roll: stale, exit 1, writes nothing.
            before = _run("--repo-root", str(tmp_path), "--check")
            self.assertEqual(before.returncode, 1, before.stderr)
            on_disk_before = json.loads(
                (tmp_path / "release-cohort.json").read_text())
            self.assertEqual(on_disk_before["onb_version"], "v9.0.0")

            # The actual roll (no SHAs given — they are release-time only).
            rolled = _run("--repo-root", str(tmp_path))
            self.assertEqual(rolled.returncode, 0, rolled.stderr)

            on_disk = json.loads(
                (tmp_path / "release-cohort.json").read_text())
            self.assertEqual(on_disk["onb_version"], "v9.9.9")
            self.assertEqual(on_disk["cc_version"], "v1.2.3")
            # SHAs untouched when not supplied.
            self.assertEqual(on_disk["onb_sha"], _STALE_ONB_SHA)
            self.assertEqual(on_disk["cc_sha"], _STALE_CC_SHA)
            # Other keys kept, including their value.
            self.assertEqual(on_disk["contract"], "1.1.0")
            self.assertEqual(
                on_disk["notes"],
                "pre-existing note that must survive the roll untouched")
            # Key order preserved.
            self.assertEqual(list(on_disk.keys()), list(on_disk_before.keys()))
            # Written with a trailing newline, 2-space indent.
            raw = (tmp_path / "release-cohort.json").read_text()
            self.assertTrue(raw.endswith("\n"))
            self.assertIn('\n  "onb_version"', raw)

            # --check AFTER the roll: current, exit 0.
            after = _run("--repo-root", str(tmp_path), "--check")
            self.assertEqual(after.returncode, 0, after.stderr)

    def test_sha_flags_roll_the_shas_too(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            new_onb_sha = "c" * 40
            new_cc_sha = "d" * 40
            result = _run(
                "--repo-root", str(tmp_path),
                "--onb-sha", new_onb_sha, "--cc-sha", new_cc_sha)
            self.assertEqual(result.returncode, 0, result.stderr)
            on_disk = json.loads(
                (tmp_path / "release-cohort.json").read_text())
            self.assertEqual(on_disk["onb_sha"], new_onb_sha)
            self.assertEqual(on_disk["cc_sha"], new_cc_sha)

    def test_second_roll_is_a_noop(self):
        """Rolling an already-current cohort changes nothing and exits 0."""
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            _run("--repo-root", str(tmp_path))
            before = (tmp_path / "release-cohort.json").read_text()
            again = _run("--repo-root", str(tmp_path))
            self.assertEqual(again.returncode, 0, again.stderr)
            after = (tmp_path / "release-cohort.json").read_text()
            self.assertEqual(before, after)


class BadInput(unittest.TestCase):
    def test_bad_cc_sha_gives_rc_2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            result = _run(
                "--repo-root", str(tmp_path), "--cc-sha", "not-a-real-sha")
            self.assertEqual(result.returncode, 2, result.stdout)
            # Never wrote on a bad input.
            on_disk = json.loads(
                (tmp_path / "release-cohort.json").read_text())
            self.assertEqual(on_disk["cc_version"], "v1.0.0")

    def test_bad_onb_sha_gives_rc_2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            result = _run(
                "--repo-root", str(tmp_path),
                "--onb-sha", "TOOSHORT")
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_uppercase_sha_rejected(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            result = _run(
                "--repo-root", str(tmp_path), "--cc-sha", "A" * 40)
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_missing_repo_root_gives_rc_2(self):
        result = _run("--repo-root", "/nonexistent/definitely-not-a-dir")
        self.assertEqual(result.returncode, 2, result.stdout)

    def test_missing_version_file_gives_rc_2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            (tmp_path / "cc-compat.json").write_text(
                json.dumps({"commandCenter": {"pinnedTag": "v1.2.3"}}),
                encoding="utf-8")
            result = _run("--repo-root", str(tmp_path))
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_missing_pinned_tag_gives_rc_2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            (tmp_path / "version").write_text("v9.9.9\n", encoding="utf-8")
            (tmp_path / "cc-compat.json").write_text(
                json.dumps({"commandCenter": {}}), encoding="utf-8")
            result = _run("--repo-root", str(tmp_path))
            self.assertEqual(result.returncode, 2, result.stdout)

    def test_missing_cohort_file_gives_rc_2(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            (tmp_path / "version").write_text("v9.9.9\n", encoding="utf-8")
            (tmp_path / "cc-compat.json").write_text(
                json.dumps({"commandCenter": {"pinnedTag": "v1.2.3"}}),
                encoding="utf-8")
            result = _run("--repo-root", str(tmp_path))
            self.assertEqual(result.returncode, 2, result.stdout)


class BumpVersionWiring(unittest.TestCase):
    """Wiring guard: bump-version.sh must actually call the roll script,
    both on a real bump and under --check, next to the pinnedTag-derived
    README token step. This is what makes cohort drift impossible to
    reintroduce silently."""

    def test_bump_version_invokes_roll_release_cohort(self):
        self.assertTrue(_BUMP.is_file(), "scripts/bump-version.sh is missing")
        src = _BUMP.read_text(encoding="utf-8")
        self.assertIn("roll-release-cohort.py", src,
                     "bump-version.sh never references roll-release-cohort.py")
        self.assertIn('"$SCRIPT_DIR/roll-release-cohort.py" --repo-root "$REPO_ROOT"',
                     src,
                     "bump-version.sh does not call roll-release-cohort.py "
                     "with --repo-root \"$REPO_ROOT\"")

    def test_bump_version_check_mode_also_calls_it(self):
        src = _BUMP.read_text(encoding="utf-8")
        check_block_start = src.index('"${1:-}" = "--check"')
        check_block = src[check_block_start:check_block_start + 1500]
        self.assertIn("roll-release-cohort.py", check_block,
                     "--check mode does not invoke roll-release-cohort.py")
        self.assertIn("--check", check_block[check_block.index("roll-release-cohort.py"):],
                     "--check mode must pass --check through to the roll script")

    def test_bump_version_does_not_touch_owned_marker_files(self):
        """This unit does NOT change BUMP_CHECKED_MARKERS or
        version-markers.json — the cohort tracks two sources, like the
        DIRECT-TO-AGENT CC token, and is deliberately kept out of that set."""
        src = _BUMP.read_text(encoding="utf-8")
        self.assertIn("BUMP_CHECKED_MARKERS=10", src)


if __name__ == "__main__":
    unittest.main()

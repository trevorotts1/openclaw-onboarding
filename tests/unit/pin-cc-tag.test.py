#!/usr/bin/env python3
"""Unit test: scripts/pin-cc-tag.py moves the CC pin in BOTH files in lockstep.

The Command Center pin lives in two files that must never disagree:
cc-compat.json commandCenter.pinnedTag (read by shared-utils/cc_compat.py for
fleet-refresh + the skill-32 installer) and release-cohort.json cc_version
(the tested pair decision-engine promotion gates on). Nothing else wrote
pinnedTag, so a hand edit of either file could silently leave the pair split.

This suite proves, offline, against throwaway temp repos (never the real
clone, no network, no model calls):

  * a bump moves pinnedTag AND cc_version to the same new tag in one run,
    preserving every other key, key order, and the trailing newline;
  * every refusal (bad tag shape, tag < minVersion, missing input, invalid
    cc-compat.json) exits 2 and writes NOTHING in either file;
  * --check reports agreement (exit 0) or drift (exit 1) without writing;
  * MUTATION PROOF (anti-vacuity, both directions): with the second write
    faulted in a throwaway copy, the first file is rolled back — the pair is
    never left split; and with the agreement comparison forced true in a copy,
    a genuine drift stops being reported — so the real rc=1 above is the
    comparison doing the work, not an accident.

Run: python3 tests/unit/pin-cc-tag.test.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SCRIPT = _REPO_ROOT / "scripts" / "pin-cc-tag.py"
_COMPAT_LIB = _REPO_ROOT / "shared-utils" / "cc_compat.py"

_OLD = "v1.2.3"
_NEW = "v1.4.2"
_MIN = "v1.0.0"


def _run(*args, script=None):
    return subprocess.run(
        [sys.executable, str(script or _SCRIPT), *args],
        capture_output=True, text=True, timeout=15)


def _make_repo(tmp_path: Path, pinned=_OLD, cc_version=_OLD, min_version=_MIN) -> None:
    """A minimal temp repo tree the script can read and write: a valid
    cc-compat.json, a release-cohort.json carrying extra keys that must
    survive a bump, and the real shared-utils/cc_compat.py it imports."""
    (tmp_path / "shared-utils").mkdir()
    shutil.copy2(_COMPAT_LIB, tmp_path / "shared-utils" / "cc_compat.py")
    (tmp_path / "cc-compat.json").write_text(json.dumps({
        "schemaVersion": 1,
        "onboardingVersion": "v9.9.9",
        "commandCenter": {"minVersion": min_version, "maxVersion": None,
                          "repo": "trevorotts1/blackceo-command-center",
                          "pinnedTag": pinned},
    }, indent=2) + "\n", encoding="utf-8")
    (tmp_path / "release-cohort.json").write_text(json.dumps({
        "onb_sha": "a" * 40,
        "cc_sha": "b" * 40,
        "onb_version": "v9.9.9",
        "cc_version": cc_version,
        "contract": "1.1.0",
        "notes": "pre-existing note that must survive the bump untouched",
    }, indent=2) + "\n", encoding="utf-8")


def _pins(tmp_path: Path):
    compat = json.loads((tmp_path / "cc-compat.json").read_text(encoding="utf-8"))
    cohort = json.loads((tmp_path / "release-cohort.json").read_text(encoding="utf-8"))
    return compat["commandCenter"]["pinnedTag"], cohort["cc_version"]


class ScriptExists(unittest.TestCase):
    def test_script_and_lib_exist(self):
        self.assertTrue(_SCRIPT.is_file(), "scripts/pin-cc-tag.py is missing")
        self.assertTrue(_COMPAT_LIB.is_file(), "shared-utils/cc_compat.py is missing")


class CheckMode(unittest.TestCase):
    def test_check_reports_agreement_without_writing(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            before = (tmp_path / "cc-compat.json").read_text()
            r = _run("--repo-root", str(tmp_path), "--check")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn(_OLD, r.stdout)
            self.assertEqual((tmp_path / "cc-compat.json").read_text(), before)

    def test_check_reports_drift(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path, cc_version="v1.9.9")  # the two files disagree
            r = _run("--repo-root", str(tmp_path), "--check")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertIn("DRIFT", r.stdout)
            # Drift is reported, never silently "fixed" by --check.
            self.assertEqual(_pins(tmp_path), (_OLD, "v1.9.9"))

    def test_check_rejects_a_tag_argument(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            r = _run("--repo-root", str(tmp_path), "--check", _NEW)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual(_pins(tmp_path), (_OLD, _OLD))

    def test_check_mode_cannot_pass_vacuously(self):
        """MUTATION PROOF: force the agreement comparison true in a throwaway
        copy and the drift report disappears — the real rc=1 above is the
        comparison working, not an accident of the fixture."""
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path, cc_version="v1.9.9")
            script = tmp_path / "pin-cc-tag.py"
            src = _SCRIPT.read_text(encoding="utf-8")
            old = "if pinned == cur_cc:"
            self.assertEqual(src.count(old), 1, "fixture stale: agreement comparison not found")
            script.write_text(src.replace(old, "if True:"), encoding="utf-8")
            r = _run("--repo-root", str(tmp_path), "--check", script=script)
            self.assertEqual(r.returncode, 0,
                             "mutated copy should stop reporting drift; test fixture is stale")


class Bump(unittest.TestCase):
    def test_bump_moves_both_files_to_the_same_tag(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            keys_before = list(json.loads((tmp_path / "release-cohort.json").read_text()).keys())

            r = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(_pins(tmp_path), (_NEW, _NEW))

            # Everything else survives: values, key order, trailing newline.
            cohort = json.loads((tmp_path / "release-cohort.json").read_text())
            self.assertEqual(list(cohort.keys()), keys_before)
            self.assertEqual(cohort["onb_version"], "v9.9.9")
            self.assertEqual(cohort["onb_sha"], "a" * 40)
            self.assertEqual(cohort["notes"],
                             "pre-existing note that must survive the bump untouched")
            self.assertEqual(cohort["contract"], "1.1.0")
            raw = (tmp_path / "release-cohort.json").read_text()
            self.assertTrue(raw.endswith("\n"))
            self.assertIn('\n  "cc_version"', raw)

    def test_second_bump_is_a_byte_identical_noop(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            _run("--repo-root", str(tmp_path), _NEW)
            before = ((tmp_path / "cc-compat.json").read_bytes(),
                      (tmp_path / "release-cohort.json").read_bytes())
            again = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(again.returncode, 0, again.stderr)
            self.assertIn("nothing to do", again.stdout)
            after = ((tmp_path / "cc-compat.json").read_bytes(),
                     (tmp_path / "release-cohort.json").read_bytes())
            self.assertEqual(before, after)

    def test_bump_from_drift_heals_the_pair(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path, cc_version="v1.9.9")
            r = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(_pins(tmp_path), (_NEW, _NEW))

    def test_no_temp_files_left_behind(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            _run("--repo-root", str(tmp_path), _NEW)
            leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [], f"atomic-write temp files left: {leftovers}")


class Refusals(unittest.TestCase):
    """Every refusal exits 2 and leaves BOTH files exactly as they were."""

    def _assert_refused(self, tmp_path, args):
        before = ((tmp_path / "cc-compat.json").read_bytes(),
                  (tmp_path / "release-cohort.json").read_bytes())
        r = _run("--repo-root", str(tmp_path), *args)
        self.assertEqual(r.returncode, 2, f"args={args} stdout={r.stdout} stderr={r.stderr}")
        after = ((tmp_path / "cc-compat.json").read_bytes(),
                 (tmp_path / "release-cohort.json").read_bytes())
        self.assertEqual(before, after, f"a refused run (args={args}) wrote to disk")

    def test_bad_tag_shapes(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            for bad in ("7.6.91", "v7.6", "v7.6.91.1", "latest", "vX.Y.Z", ""):
                if bad == "":
                    continue  # no-tag case is covered below
                self._assert_refused(tmp_path, [bad])
            self._assert_refused(tmp_path, [])  # no tag at all

    def test_tag_below_min_version_refused(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path, min_version="v9.0.0")
            self._assert_refused(tmp_path, ["v1.4.2"])

    def test_missing_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            (tmp_path / "release-cohort.json").unlink()
            compat_before = (tmp_path / "cc-compat.json").read_bytes()
            r = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual((tmp_path / "cc-compat.json").read_bytes(), compat_before)
            self.assertFalse((tmp_path / "release-cohort.json").exists(),
                             "a refused run recreated the missing file")
        r = _run("--repo-root", "/nonexistent/definitely-not-a-dir", _NEW)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)

    def test_invalid_cc_compat_exits_2_not_traceback(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            # pinnedTag below minVersion: load_cc_compat() raises ValueError.
            (tmp_path / "cc-compat.json").write_text(json.dumps({
                "schemaVersion": 1, "onboardingVersion": "v9.9.9",
                "commandCenter": {"minVersion": "v9.0.0", "pinnedTag": "v1.0.0"},
            }), encoding="utf-8")
            before = (tmp_path / "release-cohort.json").read_bytes()
            r = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual((tmp_path / "release-cohort.json").read_bytes(), before)

    def test_missing_pinned_tag_refused(self):
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            (tmp_path / "cc-compat.json").write_text(json.dumps({
                "schemaVersion": 1, "onboardingVersion": "v9.9.9",
                "commandCenter": {"minVersion": _MIN, "pinnedTag": None},
            }), encoding="utf-8")
            before = (tmp_path / "release-cohort.json").read_bytes()
            r = _run("--repo-root", str(tmp_path), _NEW)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertEqual((tmp_path / "release-cohort.json").read_bytes(), before)


class Rollback(unittest.TestCase):
    def test_second_write_failure_rolls_the_first_back(self):
        """MUTATION PROOF: fault the second write in a throwaway copy. The
        first file must be rolled back so the pair still agrees — the
        never-split guarantee, proved rather than assumed."""
        with tempfile.TemporaryDirectory() as d:
            tmp_path = Path(d)
            _make_repo(tmp_path)
            script = tmp_path / "pin-cc-tag.py"
            src = _SCRIPT.read_text(encoding="utf-8")
            old = "_write_atomic(cohort_path, new_cohort)"
            self.assertEqual(src.count(old), 1, "fixture stale: cohort write call not found")
            script.write_text(
                src.replace(old, 'raise RuntimeError("injected cohort write failure")'),
                encoding="utf-8")

            r = _run("--repo-root", str(tmp_path), _NEW, script=script)
            self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
            self.assertIn("rolled back", r.stderr)
            # The pair still agrees, on the OLD value, in both files.
            self.assertEqual(_pins(tmp_path), (_OLD, _OLD))
            leftovers = [p.name for p in tmp_path.iterdir() if p.name.startswith(".")]
            self.assertEqual(leftovers, [], f"atomic-write temp files left: {leftovers}")


if __name__ == "__main__":
    unittest.main()

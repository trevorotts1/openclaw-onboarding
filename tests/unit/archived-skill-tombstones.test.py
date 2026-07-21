#!/usr/bin/env python3
"""Unit tests for the archived-skill tombstones (T2-12).

T2-12: `33-department-heads-ARCHIVED/SKILL.md` opened as an active installer for
seventeen permanent department heads with no archive banner and no successor, and
`34-intelligent-staffing-ARCHIVED/SKILL.md` still declared that it extends Skill
23 and depends on Skill 33. The cluster addendum added
`13-google-workspace-setup-ARCHIVED`, whose text defers work to a skill number and
a script that do not exist. An operator who opens any of the three sees a live
installer; following it reintroduces a superseded model into a live workforce.

The state each archived folder is supposed to be in is declared in
`docs/archived-skill-tombstones.json`, not inferred. These tests enforce it, in
both directions:

  * a tombstoned folder that loses its banner, its successor, or its installer's
    refusal turns this suite RED;
  * a folder still declared pending must say why, so "not yet done" is visible
    rather than silently skipped;
  * a NEW archived folder that nobody declared turns this suite RED, so the next
    archive cannot slip in as a live installer.

Run:
    python3 tests/unit/archived-skill-tombstones.test.py
    or: pytest tests/unit/archived-skill-tombstones.test.py
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_MANIFEST_PATH = _REPO_ROOT / "docs" / "archived-skill-tombstones.json"
assert _MANIFEST_PATH.is_file(), f"manifest not found at {_MANIFEST_PATH}"

_MANIFEST = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
_BANNER = _MANIFEST["banner_prefix"]
_ENTRIES = _MANIFEST["archived"]

_FENCE_RE = re.compile(r"^\s*```", re.MULTILINE)


def _archived_dirs_on_disk():
    return sorted(
        name for name in os.listdir(_REPO_ROOT)
        if name.endswith("-ARCHIVED") and (_REPO_ROOT / name).is_dir()
    )


def _tombstoned():
    return sorted(k for k, v in _ENTRIES.items() if v.get("tombstoned") is True)


class TestManifestCoversReality(unittest.TestCase):
    def test_every_archived_directory_is_declared(self):
        on_disk = set(_archived_dirs_on_disk())
        declared = set(_ENTRIES)
        self.assertEqual(
            on_disk - declared, set(),
            "archived folder(s) on disk with no entry in "
            "docs/archived-skill-tombstones.json — declare them tombstoned or pending",
        )

    def test_no_declared_directory_is_missing_from_disk(self):
        on_disk = set(_archived_dirs_on_disk())
        declared = set(_ENTRIES)
        self.assertEqual(
            declared - on_disk, set(),
            "manifest declares archived folder(s) that do not exist — remove the stale entries",
        )

    def test_pending_entries_state_a_reason(self):
        for name, entry in sorted(_ENTRIES.items()):
            if entry.get("tombstoned") is True:
                continue
            with self.subTest(archived=name):
                self.assertTrue(
                    (entry.get("pending") or "").strip(),
                    f"{name} is not tombstoned and gives no reason — an outstanding "
                    f"archive must be visible, never a silent skip",
                )

    def test_the_three_t2_12_folders_are_declared_tombstoned(self):
        for name in (
            "33-department-heads-ARCHIVED",
            "34-intelligent-staffing-ARCHIVED",
            "13-google-workspace-setup-ARCHIVED",
        ):
            with self.subTest(archived=name):
                self.assertTrue(
                    _ENTRIES.get(name, {}).get("tombstoned") is True,
                    f"{name} must stay tombstoned (T2-12)",
                )


class TestTombstonedFoldersAreTombstones(unittest.TestCase):
    def test_skill_md_carries_the_banner(self):
        for name in _tombstoned():
            with self.subTest(archived=name):
                text = (_REPO_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertTrue(
                    text.lstrip().startswith(_BANNER),
                    f"{name}/SKILL.md does not open with the tombstone banner "
                    f"{_BANNER!r} — it reads as a live skill",
                )

    def test_skill_md_names_its_successor(self):
        for name in _tombstoned():
            with self.subTest(archived=name):
                successor = _ENTRIES[name]["successor"]
                text = (_REPO_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(
                    successor, text,
                    f"{name}/SKILL.md does not name its successor {successor}",
                )

    def test_skill_md_states_it_must_not_be_run(self):
        for name in _tombstoned():
            with self.subTest(archived=name):
                text = (_REPO_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("Do not run its installer", text)

    def test_skill_md_has_no_runnable_procedure(self):
        """A tombstone carries no code fences: nothing in it can be executed."""
        for name in _tombstoned():
            with self.subTest(archived=name):
                text = (_REPO_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIsNone(
                    _FENCE_RE.search(text),
                    f"{name}/SKILL.md still contains a runnable code block",
                )

    def test_install_md_carries_the_banner(self):
        for name in _tombstoned():
            install_md = _REPO_ROOT / name / "INSTALL.md"
            if not install_md.is_file():
                continue
            with self.subTest(archived=name):
                text = install_md.read_text(encoding="utf-8")
                self.assertTrue(
                    text.lstrip().startswith("# ARCHIVED — DO NOT RUN"),
                    f"{name}/INSTALL.md still reads as an installation guide",
                )


class TestArchivedInstallersRefuseToRun(unittest.TestCase):
    """The sharpest check here: the installer is executed and must fail."""

    def _run_installer(self, path: Path):
        with tempfile.TemporaryDirectory() as fake_home:
            env = dict(os.environ)
            env["HOME"] = fake_home
            return subprocess.run(
                ["bash", str(path)],
                capture_output=True, text=True, timeout=60,
                cwd=str(path.parent), env=env, stdin=subprocess.DEVNULL,
            )

    def test_each_tombstoned_installer_exits_non_zero(self):
        ran_at_least_one = False
        for name in _tombstoned():
            installer = _REPO_ROOT / name / "install.sh"
            if not installer.is_file():
                continue
            ran_at_least_one = True
            with self.subTest(archived=name):
                proc = self._run_installer(installer)
                self.assertNotEqual(
                    proc.returncode, 0,
                    f"{name}/install.sh ran to success — an archived installer must refuse",
                )
                combined = proc.stdout + proc.stderr
                self.assertIn("REFUSED", combined,
                              f"{name}/install.sh failed without saying it refused")
                self.assertIn(_ENTRIES[name]["successor"], combined,
                              f"{name}/install.sh refused without naming its successor")
        self.assertTrue(
            ran_at_least_one,
            "no tombstoned archived folder ships an install.sh — this check exercised nothing",
        )

    def test_installer_writes_nothing(self):
        """A refusal must not touch the box on its way out."""
        for name in _tombstoned():
            installer = _REPO_ROOT / name / "install.sh"
            if not installer.is_file():
                continue
            with self.subTest(archived=name):
                with tempfile.TemporaryDirectory() as fake_home:
                    env = dict(os.environ)
                    env["HOME"] = fake_home
                    subprocess.run(
                        ["bash", str(installer)],
                        capture_output=True, text=True, timeout=60,
                        cwd=str(installer.parent), env=env, stdin=subprocess.DEVNULL,
                    )
                    self.assertEqual(
                        os.listdir(fake_home), [],
                        f"{name}/install.sh wrote into HOME before refusing",
                    )


class TestTheCheckCanGoRed(unittest.TestCase):
    """Directed negative cases: prove each rule catches the defect it names."""

    def test_a_live_installer_body_fails_the_banner_rule(self):
        live_body = "# Skill 99: Something\n\n## What This Skill Does\n\nInstalls things.\n"
        self.assertFalse(live_body.lstrip().startswith(_BANNER))

    def test_a_body_with_a_code_fence_fails_the_no_procedure_rule(self):
        with_fence = f"{_BANNER} — Skill 99\n\n```bash\nbash install.sh\n```\n"
        self.assertIsNotNone(_FENCE_RE.search(with_fence))

    def test_a_zero_exit_installer_fails_the_refusal_rule(self):
        with tempfile.TemporaryDirectory() as td:
            stub = Path(td) / "install.sh"
            stub.write_text("#!/usr/bin/env bash\nexit 0\n", encoding="utf-8")
            proc = subprocess.run(["bash", str(stub)], capture_output=True,
                                  text=True, timeout=60, stdin=subprocess.DEVNULL)
        self.assertEqual(proc.returncode, 0,
                         "control: a permissive installer exits zero, which the rule rejects")


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""The shared pydeps contract: where jsonschema lives when pip refuses the interpreter, and how every importer finds it.

A client Mac (Homebrew Python 3.14, PEP 668 "externally managed") refused plain and --user pip, and
--break-system-packages is forbidden. `pip install --target <root>/pydeps/py<X.Y>/` works, so the package
lives there and every Python file that imports jsonschema puts that folder on sys.path itself. The 999 setup
agent and the Command Center use the same names, so they are pinned here.

Hermetic: stub packages in temp dirs, subprocesses with a scrubbed environment, no pip, no network.
Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import pydeps  # noqa: E402


def _layout() -> tuple:
    """(repo root, folder holding the skills, in the 999 repo?). The same file runs in both repos, byte for byte.

    onboarding: <repo>/83-black-friday-launcher; the skills are the repo's top-level NN-name folders.
    999:        <repo>/.claude/skills/black-friday-launcher; the skills are real folders there (the NN-name entries
                are symlinks the walk does not follow), while shared-utils and the installers sit at the repo root.
    Anywhere else (an installed copy) the walk stays on the skills folder and the canonical-file skip applies.
    """
    skills = SKILL_ROOT.parent
    repo = skills.parent.parent
    if skills.name == "skills" and skills.parent.name == ".claude" and (repo / "shared-utils").is_dir():
        return repo, skills, True
    return skills, skills, False


REPO_ROOT, SKILLS_DIR, IN_999 = _layout()
TAG = "py%d.%d" % sys.version_info[:2]
CANONICAL_FILE = next(
    (f for f in (SKILLS_DIR / d / "scripts" / "validate_checkout.py" for d in ("signature-order-form", "79-signature-order-form"))
     if f.is_file()),
    SKILLS_DIR / "79-signature-order-form" / "scripts" / "validate_checkout.py")
BLOCK = re.compile(r"# PYDEPS-ACTIVATION:BEGIN.*?# PYDEPS-ACTIVATION:END\n", re.S)
IMPORT = re.compile(r"^\s*(?:import jsonschema\b|from jsonschema\b)", re.M)
# Shell scripts whose own Python probe puts the pydeps folder first carry no inline block: the onboarding shell library
# (oc_pydeps_lookup feeds its probe) and the 999 installer (its probe inserts the folder it installs into). Each must
# still show that marker before its first jsonschema import, so the exemption cannot outlive the thing it relies on.
SELF_ACTIVATING = {"lib-onboarding-state.sh": "oc_pydeps_lookup", "setup-macos.sh": "sys.path.insert(0, sys.argv[2])"}
# The 999 repo ships only the nine-router variant of Skill 72, which has no jsonschema importer.
SKILL_72_IMPORTERS = {"motion_contracts.py", "powerpoint_package.py", "review_rubric.py", "vsl_mobile.py", "vsl_handoff.py"}
SKIP_DIRS = {".git", "__pycache__", "node_modules", "tests", "fixtures", "QUALITY-CONTROL", "evidence", "ledgers"}


def clean_env(tmp: str, **extra: str) -> dict:
    env = {"PATH": os.environ.get("PATH", ""), "HOME": tmp, **extra}
    return env


def stub_package(folder: Path, marker: str = "stub") -> None:
    (folder / "jsonschema").mkdir(parents=True)
    (folder / "jsonschema" / "__init__.py").write_text(f"MARKER = {marker!r}\n", encoding="utf-8")


def import_after(snippet: str, env: dict) -> subprocess.CompletedProcess:
    code = snippet + "\nimport jsonschema; print(jsonschema.MARKER, jsonschema.__file__)"
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)


class PydepsFolders(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def env(self, **extra: str):
        scrubbed = {k: v for k, v in os.environ.items() if k not in ("OC_PYDEPS_DIR", "OPENCLAW_ROOT")}
        return mock.patch.dict(os.environ, {**scrubbed, "HOME": str(self.tmp), **extra}, clear=True)

    def test_the_folder_is_root_pydeps_python_version(self):
        with self.env(OPENCLAW_ROOT=str(self.tmp / "oc")):
            self.assertEqual(pydeps.install_dir(), self.tmp / "oc" / "pydeps" / TAG)

    def test_the_override_is_used_as_is_and_wins(self):
        with self.env(OPENCLAW_ROOT=str(self.tmp / "oc"), OC_PYDEPS_DIR=str(self.tmp / "exact")):
            self.assertEqual(pydeps.install_dir(), self.tmp / "exact")

    def test_without_a_root_it_falls_back_to_data_openclaw_then_home(self):
        with self.env():
            expected = (Path("/data/.openclaw") if Path("/data/.openclaw").is_dir()
                        else self.tmp / ".openclaw") / "pydeps" / TAG
            self.assertEqual(pydeps.install_dir(), expected)

    def test_lookup_returns_only_existing_folders_and_includes_the_999_one(self):
        root_folder = self.tmp / "oc" / "pydeps" / TAG
        nine_folder = self.tmp / ".claude" / "pydeps" / TAG
        with self.env(OPENCLAW_ROOT=str(self.tmp / "oc")):
            self.assertEqual(pydeps.lookup_dirs(), [])
            root_folder.mkdir(parents=True)
            nine_folder.mkdir(parents=True)
            self.assertEqual(pydeps.lookup_dirs(), [root_folder, nine_folder])
        with self.env(OPENCLAW_ROOT=str(self.tmp / "oc"), OC_PYDEPS_DIR=str(self.tmp / "exact")):
            self.assertEqual(pydeps.lookup_dirs(), [])  # the override replaces the others, and it does not exist
            (self.tmp / "exact").mkdir()
            self.assertEqual(pydeps.lookup_dirs(), [self.tmp / "exact"])

    def test_activate_prepends_once(self):
        folder = self.tmp / "oc" / "pydeps" / TAG
        folder.mkdir(parents=True)
        saved = list(sys.path)
        self.addCleanup(lambda: sys.path.__setitem__(slice(None), saved))
        with self.env(OPENCLAW_ROOT=str(self.tmp / "oc")):
            self.assertEqual(pydeps.activate(), [str(folder)])
            self.assertEqual(sys.path[0], str(folder))
            self.assertEqual(pydeps.activate(), [])  # idempotent


class ActivationSnippet(unittest.TestCase):
    """The block that sits before `import jsonschema` in every importer."""

    @classmethod
    def setUpClass(cls) -> None:
        if not CANONICAL_FILE.is_file():
            raise unittest.SkipTest("Skill 79 is not beside this skill (vendored copy)")
        cls.block = BLOCK.search(CANONICAL_FILE.read_text(encoding="utf-8")).group(0)

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name).resolve()

    def run_block(self, **extra: str) -> subprocess.CompletedProcess:
        return import_after(self.block, clean_env(str(self.tmp), **extra))

    def test_the_root_folder_is_found_and_wins_over_any_installed_copy(self):
        stub_package(self.tmp / "oc" / "pydeps" / TAG)
        run = self.run_block(OPENCLAW_ROOT=str(self.tmp / "oc"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("stub "), run.stdout)

    def test_the_override_folder_is_found(self):
        stub_package(self.tmp / "exact")
        run = self.run_block(OC_PYDEPS_DIR=str(self.tmp / "exact"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("stub "), run.stdout)

    def test_the_999_home_claude_folder_is_found(self):
        stub_package(self.tmp / ".claude" / "pydeps" / TAG)
        run = self.run_block(OPENCLAW_ROOT=str(self.tmp / "empty"))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("stub "), run.stdout)

    def test_a_folder_for_another_python_version_is_never_loaded(self):  # wheels are built per ABI
        stub_package(self.tmp / "oc" / "pydeps" / "py2.0")
        run = self.run_block(OPENCLAW_ROOT=str(self.tmp / "oc"))
        self.assertNotEqual(run.returncode, 0)
        self.assertNotIn("stub", run.stdout)


class LauncherPreflightSeesTheFolder(unittest.TestCase):
    """dependencies.py (the preflight) imports the package only after launcher_core/__init__ activated the folder."""

    def test_the_preflight_module_finds_a_target_install_without_any_path_help(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name).resolve() / "exact"  # OC_PYDEPS_DIR is the folder itself: no py<X.Y> is appended
        stub_package(folder)
        code = "from launcher_core import dependencies\nimport jsonschema; print(jsonschema.MARKER, jsonschema.__file__)"
        run = subprocess.run([sys.executable, "-c", code], cwd=str(SKILL_ROOT), capture_output=True, text=True,
                             env=clean_env(tmp.name, OC_PYDEPS_DIR=str(folder)))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertTrue(run.stdout.startswith("stub "), run.stdout)
        self.assertIn(str(folder), run.stdout)


class EveryImporterIsActivated(unittest.TestCase):
    def test_every_non_test_file_that_imports_jsonschema_carries_the_identical_block_first(self):
        if not CANONICAL_FILE.is_file():
            self.skipTest("Skill 79 is not beside this skill (vendored copy)")
        canonical = BLOCK.search(CANONICAL_FILE.read_text(encoding="utf-8")).group(0)
        importers = []
        for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for name in filenames:
                if name.endswith((".py", ".sh")) and not (name.startswith("test_") or name.endswith("_test.py")):
                    path = Path(dirpath) / name
                    text = path.read_text(encoding="utf-8", errors="replace")
                    if IMPORT.search(text):
                        importers.append((path, text))
        names = {p.name for p, _ in importers}
        # Skill 72 (motion-video-plus) is covered like every other importer in onboarding: no carve-out.
        expected = {"validate_checkout.py", "events.py", "normalizer.py", "processor.py", "stage_gate.py",
                    "verify.py", "verify.sh"} | (set() if IN_999 else SKILL_72_IMPORTERS)
        self.assertTrue(expected <= names, sorted(expected - names))
        if not IN_999:
            self.assertTrue(any("72-motion-video-plus" in str(p.relative_to(REPO_ROOT)) and p.name == "verify.sh"
                                for p, _ in importers), "Skill 72's verify.sh is not among the guarded importers")
        for path, text in importers:
            rel = path.relative_to(REPO_ROOT)
            marker = SELF_ACTIVATING.get(path.name)
            if marker:
                self.assertIn(marker, text[:IMPORT.search(text).start()],
                              f"{rel}: its own probe must put the pydeps folder first ({marker})")
                continue
            found = BLOCK.search(text)
            self.assertIsNotNone(found, f"{rel} imports jsonschema without the PYDEPS-ACTIVATION block")
            self.assertEqual(found.group(0), canonical, f"{rel}: the block differs from the canonical one")
            self.assertLess(found.start(), IMPORT.search(text).start(), f"{rel}: the block must come first")

    def test_the_detector_notices_a_missing_block(self):  # control: the guard is not always green
        text = "import json\nimport jsonschema\n"
        self.assertIsNotNone(IMPORT.search(text))
        self.assertIsNone(BLOCK.search(text))


if __name__ == "__main__":
    unittest.main()

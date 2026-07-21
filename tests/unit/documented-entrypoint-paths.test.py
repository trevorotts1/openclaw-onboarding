#!/usr/bin/env python3
"""Unit tests for docs/tools/check_documented_entrypoints.py — the T2-07 guard.

T2-07: three skills documented a runnable entry point at a path that does not
exist (`bash add-role.sh`, `bash sync-extensions.sh`, `bash
add-persona-from-source.sh`). Each script ships under the skill's own scripts/
directory, so an agent following the documented line gets "No such file or
directory" and the role, the converge or the persona never happens.

These tests prove BOTH directions:

  * the checker goes RED on a real defect — a synthetic skill that documents a
    script the tree does not contain is reported unresolved, with its file and
    line, and the process exits non-zero;
  * the checker stays GREEN on correct state — the same skill with the script
    present passes, and THIS repository passes;
  * the checker does not invent work — runtime paths (~/…, /…, $VAR/…) and
    documentation placeholders are out of scope and never reported.

Run:
    python3 tests/unit/documented-entrypoint-paths.test.py
    or: pytest tests/unit/documented-entrypoint-paths.test.py
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_CHECKER = _REPO_ROOT / "docs" / "tools" / "check_documented_entrypoints.py"
assert _CHECKER.is_file(), f"checker not found at {_CHECKER}"

_spec = importlib.util.spec_from_file_location("check_documented_entrypoints", _CHECKER)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_documented_entrypoints"] = _mod
_spec.loader.exec_module(_mod)


def _fixture_repo(tmp: Path, skill_md_body: str, ship_script: bool) -> Path:
    """Build a minimal repo-shaped tree with one numbered skill directory."""
    skill = tmp / "77-fixture-skill"
    (skill / "scripts").mkdir(parents=True)
    (skill / "SKILL.md").write_text(skill_md_body, encoding="utf-8")
    if ship_script:
        (skill / "scripts" / "do-the-thing.sh").write_text("#!/usr/bin/env bash\nexit 0\n",
                                                           encoding="utf-8")
    return tmp


_DOCUMENTS_MISSING_PATH = textwrap.dedent(
    """\
    # Fixture skill

    ```bash
    bash do-the-thing.sh --flag value
    ```
    """
)

_DOCUMENTS_SHIPPED_PATH = textwrap.dedent(
    """\
    # Fixture skill

    ```bash
    bash 77-fixture-skill/scripts/do-the-thing.sh --flag value
    ```
    """
)

_DOCUMENTS_RUNTIME_AND_PLACEHOLDER_PATHS = textwrap.dedent(
    """\
    # Fixture skill

    ```bash
    bash ~/.openclaw/skills/77-fixture-skill/scripts/do-the-thing.sh
    bash /usr/local/bin/somebody-elses-tool.sh
    bash $SKILL_DIR/scripts/do-the-thing.sh
    bash <skill-dir>/scripts/do-the-thing.sh
    ```
    """
)


class TestCheckerGoesRedOnARealDefect(unittest.TestCase):
    def test_missing_script_is_reported_with_file_and_line(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _fixture_repo(Path(td), _DOCUMENTS_MISSING_PATH, ship_script=False)
            misses = _mod.unresolved(str(repo))
        self.assertEqual(len(misses), 1, f"expected exactly one unresolved, got {misses}")
        rel_md, lineno, arg = misses[0]
        self.assertEqual(rel_md, "77-fixture-skill/SKILL.md")
        self.assertEqual(lineno, 4)
        self.assertEqual(arg, "do-the-thing.sh")

    def test_missing_script_exits_non_zero(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _fixture_repo(Path(td), _DOCUMENTS_MISSING_PATH, ship_script=False)
            proc = subprocess.run(
                [sys.executable, str(_CHECKER), "--repo-root", str(repo)],
                capture_output=True, text=True, timeout=60,
            )
        self.assertNotEqual(proc.returncode, 0, f"checker passed a real defect:\n{proc.stdout}")
        self.assertIn("UNRESOLVED", proc.stdout)
        self.assertIn("do-the-thing.sh", proc.stdout)

    def test_documenting_the_script_but_deleting_it_turns_red(self):
        """The fix is the document naming a path that EXISTS — not the wording.
        A correctly-worded path whose file is gone must still fail."""
        with tempfile.TemporaryDirectory() as td:
            repo = _fixture_repo(Path(td), _DOCUMENTS_SHIPPED_PATH, ship_script=True)
            (repo / "77-fixture-skill" / "scripts" / "do-the-thing.sh").unlink()
            misses = _mod.unresolved(str(repo))
        self.assertEqual(len(misses), 1, f"expected exactly one unresolved, got {misses}")


class TestCheckerStaysGreenOnCorrectState(unittest.TestCase):
    def test_shipped_path_passes(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _fixture_repo(Path(td), _DOCUMENTS_SHIPPED_PATH, ship_script=True)
            proc = subprocess.run(
                [sys.executable, str(_CHECKER), "--repo-root", str(repo)],
                capture_output=True, text=True, timeout=60,
            )
        self.assertEqual(proc.returncode, 0, f"correct state failed:\n{proc.stdout}\n{proc.stderr}")

    def test_runtime_and_placeholder_paths_are_out_of_scope(self):
        with tempfile.TemporaryDirectory() as td:
            repo = _fixture_repo(
                Path(td), _DOCUMENTS_RUNTIME_AND_PLACEHOLDER_PATHS, ship_script=False
            )
            misses = _mod.unresolved(str(repo))
        self.assertEqual(misses, [], "runtime/placeholder paths must not be reported")

    def test_this_repository_passes(self):
        """The T2-07 fix itself: every documented entry point in this repo resolves."""
        misses = _mod.unresolved(str(_REPO_ROOT))
        self.assertEqual(
            misses, [],
            "documented entry points that do not resolve:\n"
            + "\n".join(f"  {m[0]}:{m[1]} -> {m[2]}" for m in misses),
        )

    def test_the_three_repaired_lines_now_name_shipped_scripts(self):
        """Directly pins the three T2-07 sites, so reverting any one turns this red."""
        for skill, script in (
            ("23-ai-workforce-blueprint", "scripts/add-role.sh"),
            ("32-command-center-setup", "scripts/sync-extensions.sh"),
            ("22-book-to-persona-coaching-leadership-system",
             "scripts/add-persona-from-source.sh"),
        ):
            with self.subTest(skill=skill):
                self.assertTrue(
                    (_REPO_ROOT / skill / script).is_file(),
                    f"{skill}/{script} is not shipped",
                )
                documented = [
                    arg for rel_md, _, _, arg in _mod.documented_entrypoints(str(_REPO_ROOT))
                    if rel_md.startswith(skill + "/")
                ]
                self.assertIn(
                    f"{skill}/{script}", documented,
                    f"{skill}/SKILL.md no longer documents the shipped path {script}",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""Version, CLI and module-name parity for Skill 83.

Three drifts shipped already:

1. the version was bumped in skill-version.txt and SKILL.md but not in
   skill.json, registration.json or launcher_core/constants.py;
2. three CLI subcommands existed in launcher_core/cli.py but were never
   documented in SKILL.md's Entry block;
3. a test module shared a stem with a module in a sibling skill's scripts
   directory that routes/substrate.py puts on sys.path, so unittest discovery
   resolved that stem to the sibling and aborted verify.sh.

All three are cheap to check and expensive to notice late, so all three are
pinned here.

Stdlib only: python3 -m unittest.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
REPO_ROOT = SKILL_ROOT.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core.constants import SKILL_VERSION  # noqa: E402


def _frontmatter_version(text: str) -> str:
    match = re.search(r"^version:\s*(\S+)\s*$", text, re.MULTILINE)
    if match is None:
        raise AssertionError("SKILL.md has no version: frontmatter line")
    return match.group(1)


class VersionParity(unittest.TestCase):
    """Every version record for one skill names one version."""

    def test_all_version_records_agree(self) -> None:
        stamped = (SKILL_ROOT / "skill-version.txt").read_text(encoding="utf-8").strip()
        documented = _frontmatter_version(
            (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8"))
        skill_json = json.loads(
            (SKILL_ROOT / "skill.json").read_text(encoding="utf-8"))
        registration = json.loads(
            (SKILL_ROOT / "registration.json").read_text(encoding="utf-8"))

        self.assertEqual(stamped, documented, "skill-version.txt vs SKILL.md")
        self.assertEqual(stamped, skill_json["version"], "skill-version.txt vs skill.json")
        self.assertEqual(stamped, registration["skill"]["version"],
                         "skill-version.txt vs registration.json")
        self.assertEqual(stamped, SKILL_VERSION,
                         "skill-version.txt vs launcher_core/constants.py")


class CliDocumentationParity(unittest.TestCase):
    """Every shipped subcommand is named in SKILL.md, and vice versa."""

    @staticmethod
    def _shipped() -> set:
        source = (SKILL_ROOT / "launcher_core" / "cli.py").read_text(encoding="utf-8")
        return set(re.findall(r'add_parser\(\s*"([a-z_]+)"', source))

    @staticmethod
    def _documented() -> set:
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        return set(re.findall(r"launcher_core\.cli\s+([a-z_]+)", text))

    def test_every_subcommand_is_documented(self) -> None:
        shipped, documented = self._shipped(), self._documented()
        self.assertTrue(shipped, "no subcommands parsed from cli.py")
        self.assertEqual(set(), shipped - documented,
                         f"cli.py ships subcommands SKILL.md never documents: "
                         f"{sorted(shipped - documented)}")

    def test_every_documented_subcommand_ships(self) -> None:
        shipped, documented = self._shipped(), self._documented()
        self.assertEqual(set(), documented - shipped,
                         f"SKILL.md documents subcommands cli.py does not ship: "
                         f"{sorted(documented - shipped)}")


class TestModuleNameParity(unittest.TestCase):
    """No test module stem is claimed by a sibling skill's scripts directory.

    routes/substrate.py binds sibling skill modules by file path and those
    modules put their own directories on sys.path, so a stem collision is not
    theoretical: unittest discovery imports by stem and aborts when the stem
    resolves to the sibling file. This checks the whole collision surface,
    not just the one pair (tests/test_launch_plan) that broke verify.sh once.

    ponytail: this pins the collision after the fact; the durable fix is for
    substrate.load to restore sys.path after binding (it must then also warm
    each loader's call-time sibling imports). Add that when the next collision
    appears, not before.
    """

    def test_no_stem_collision_with_sibling_script_modules(self) -> None:
        ours = {p.stem for p in (SKILL_ROOT / "tests").glob("*.py")}
        theirs: dict[str, Path] = {}
        for scripts in sorted(REPO_ROOT.glob("[0-9][0-9]-*/scripts")):
            for module in scripts.glob("*.py"):
                theirs.setdefault(module.stem, module)
        shared = sorted(ours & set(theirs))
        self.assertEqual([], shared,
                         "test module stems colliding with sibling modules "
                         f"on the substrate import path: "
                         f"{[(s, str(theirs[s].relative_to(REPO_ROOT))) for s in shared]}")


if __name__ == "__main__":
    unittest.main()

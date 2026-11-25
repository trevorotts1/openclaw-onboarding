#!/usr/bin/env python3
"""SWB-570: the validators that read shared-utils find it through every documented layout.

Found on a client box: a second, older skill copy under ~/.claude/skills has no sibling
shared-utils, so validate_annotation_leak.py (which imports build_production_request.py) and
validate_mockup_slots.py died with FileNotFoundError on
~/.claude/skills/shared-utils/signature_launch/... while the installed tree under
~/.openclaw/skills passed. Both now try: the sibling of the skill folder as resolved, the sibling
as spelled (a symlinked skill folder), OPENCLAW_SKILLS_DIR, ~/.openclaw/skills, /data/.openclaw/skills,
and refuse by naming every place they looked.
"""
import os
import shutil
import site
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT.parent / "shared-utils"
NEEDED = ("signature_launch/design_intelligence.py", "signature_launch/design/image_slots.py")


def install_shared(dest):
    for rel in NEEDED:
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SHARED / rel, target)


def skill_copy(parent):
    """A skill folder with its own scripts and the other folders linked back to the repo."""
    skill = parent / "blackceo-signature-page"
    skill.mkdir(parents=True)
    shutil.copytree(ROOT / "scripts", skill / "scripts", ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("references", "assets"):
        if (ROOT / name).exists():
            (skill / name).symlink_to(ROOT / name)
    return skill


PROBE = (
    "import sys; sys.dont_write_bytecode = True; sys.path.insert(0, sys.argv[1]); "
    "import validate_mockup_slots as m; p = m.image_slots_path(); "
    "assert p.is_file(), p; print('SLOTS', p); "
    "import build_production_request as b; print('DI', b.di.__file__)"
)


def probe(skill, home, extra_env=None):
    env = {k: v for k, v in os.environ.items() if k != "OPENCLAW_SKILLS_DIR"}
    env.update(HOME=str(home), PYTHONDONTWRITEBYTECODE="1", PYTHONUSERBASE=site.getuserbase())
    env.update(extra_env or {})
    return subprocess.run([sys.executable, "-c", PROBE, str(skill / "scripts")], cwd=str(skill), env=env,
                          capture_output=True, text=True, timeout=120)


class SharedUtilsFallback(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="swb570-")).resolve()
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = self.tmp / "home"
        self.home.mkdir()

    def test_old_claude_copy_falls_back_to_the_installed_openclaw_shared_utils(self):
        skill = skill_copy(self.tmp / "home" / ".claude" / "skills")
        self.assertFalse((skill.parent / "shared-utils").exists())
        install_shared(self.home / ".openclaw" / "skills" / "shared-utils")
        done = probe(skill, self.home)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(self.home / ".openclaw" / "skills" / "shared-utils"), done.stdout)

    def test_skill_folder_symlinked_into_a_tree_without_shared_utils(self):
        real = skill_copy(self.tmp / "real")          # no sibling shared-utils beside the real folder
        link_parent = self.tmp / "linked"
        link_parent.mkdir()
        (link_parent / "blackceo-signature-page").symlink_to(real)
        install_shared(link_parent / "shared-utils")  # only the symlink's own parent has it
        done = probe(link_parent / "blackceo-signature-page", self.home)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(link_parent / "shared-utils"), done.stdout)

    def test_sibling_shared_utils_still_wins_over_the_installed_one(self):
        skill = skill_copy(self.tmp / "tree")
        install_shared(skill.parent / "shared-utils")
        install_shared(self.home / ".openclaw" / "skills" / "shared-utils")
        done = probe(skill, self.home)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(skill.parent / "shared-utils"), done.stdout)
        self.assertNotIn(str(self.home), done.stdout)

    def test_openclaw_skills_dir_environment_variable_is_honoured(self):
        skill = skill_copy(self.tmp / "tree")
        install_shared(self.tmp / "elsewhere" / "shared-utils")
        done = probe(skill, self.home, {"OPENCLAW_SKILLS_DIR": str(self.tmp / "elsewhere")})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn(str(self.tmp / "elsewhere" / "shared-utils"), done.stdout)

    def test_nowhere_to_be_found_refuses_naming_the_places_looked(self):
        skill = skill_copy(self.tmp / "tree")
        done = probe(skill, self.home)
        self.assertNotEqual(done.returncode, 0)
        # validate_mockup_slots falls back to the sibling path (so the failure names it);
        # the slots probe asserts is_file(), the builder names every layout it tried.
        self.assertIn("shared-utils", done.stderr)
        builder = subprocess.run(
            [sys.executable, "-c", "import sys; sys.path.insert(0, sys.argv[1]); import build_production_request",
             str(skill / "scripts")],
            cwd=str(skill), env={**os.environ, "HOME": str(self.home), "PYTHONDONTWRITEBYTECODE": "1",
                 "PYTHONUSERBASE": site.getuserbase()},
            capture_output=True, text=True, timeout=120)
        self.assertNotEqual(builder.returncode, 0)
        self.assertIn("design_intelligence.py not found in any shared-utils layout", builder.stderr)
        self.assertIn(str(self.home / ".openclaw" / "skills" / "shared-utils"), builder.stderr)


if __name__ == "__main__":
    unittest.main()

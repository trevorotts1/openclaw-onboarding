"""Skill 84 wiring check: the blueprint may only name code that exists.

Run: python3 -I 84-purple-billboard-blueprint/tests/test_blueprint_wiring.py
Standard library only. Works in the repository and on a box, because every
path is resolved against the skills root (the folder holding the numbered
skill folders and shared-utils/).
"""
import json
import re
import unittest
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ROOT = SKILL.parent  # skills root
REFS = SKILL / "references"

# Files whose backticked repo paths must exist.
CHECKED = [SKILL / "SKILL.md", REFS / "wiring-map.md", REFS / "safety-boundaries.md"] + sorted(
    (REFS / "playbook").glob("0[67]-*.md")
)

# A backticked token counts as a path to verify when it starts with a numbered
# skill folder, shared-utils/, or this skill's own references/ spec/ playbook/.
ROOTED = re.compile(r"^(\d\d-[a-z0-9-]+|shared-utils)/[\w./-]+$")
SKILL_REL = re.compile(r"^(references|spec|playbook)/[\w./-]+$")

PLAYBOOK = [
    "01-main-playbook.md", "02-strategy-guide.md", "03-ai-sop-and-rules-checklist.md",
    "04-swipe-pack.md", "05-conversation-ai-build-plan.md", "06-dm-door-and-agreed-flow.md",
    "07-posting-routes-approvals-and-30-day-plan.md", "08-examples.md", "09-realtor-examples.md",
]
SPEC = ["SPEC.md", "CLIENT-EXPERIENCE.md", "DEPLOYMENT.md", "DATA-CONTRACTS.md", "DECISIONS.md"]


def _paths(text):
    for tok in re.findall(r"`([^`\n]+)`", text):
        first = tok.split()[0].rstrip(",.;:)")
        if any(c in first for c in "<>*{}$~"):
            continue
        if ROOTED.match(first):
            yield ROOT / first
        elif SKILL_REL.match(first):
            yield (SKILL / first) if first.startswith("references/") else (REFS / first)


def _frontmatter(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.S)
    assert m, "SKILL.md has no frontmatter"
    return m.group(1)


class BlueprintWiring(unittest.TestCase):
    def test_versions_agree(self):
        fm = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        ver = re.search(r"^version:\s*(\S+)\s*$", fm, re.M).group(1)
        self.assertEqual(ver, (SKILL / "skill-version.txt").read_text(encoding="utf-8").strip())

    def test_name_matches_folder(self):
        fm = _frontmatter((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        name = re.search(r"^name:\s*(\S+)\s*$", fm, re.M).group(1)
        self.assertEqual(SKILL.name, "84-" + name)
        self.assertRegex(fm, r"(?m)^description:")

    def test_every_named_path_exists(self):
        missing = []
        n = 0
        for f in CHECKED:
            for p in _paths(f.read_text(encoding="utf-8")):
                n += 1
                if not p.exists():
                    missing.append("%s -> %s" % (f.name, p.relative_to(ROOT) if ROOT in p.parents else p))
        self.assertGreater(n, 40, "path scan found suspiciously few paths: the scanner is broken")
        self.assertEqual(missing, [], "named paths that do not exist")

    def test_scanner_discriminates(self):
        bad = list(_paths("`38-conversational-ai-system/tools/no_such_module.py`"))
        self.assertEqual(len(bad), 1)
        self.assertFalse(bad[0].exists())

    def test_references_present(self):
        for n in PLAYBOOK:
            self.assertTrue((REFS / "playbook" / n).is_file(), n)
        for n in SPEC:
            self.assertTrue((REFS / "spec" / n).is_file(), n)

    def test_boundaries_stay_in_skill_md(self):
        t = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        for needle in ("outbound_gate.py", "pb_send.py", "written authorization", "unproved"):
            self.assertIn(needle, t)

    def test_no_operator_paths(self):
        needles = ["/Us" + "ers/", "/Vol" + "umes/", "/pri" + "vate/tmp"]
        hits = []
        for f in SKILL.rglob("*"):
            if f.is_file() and f.suffix in {".md", ".json", ".txt", ".py"}:
                t = f.read_text(encoding="utf-8", errors="replace")
                hits += [str(f.relative_to(SKILL)) for n in needles if n in t]
        self.assertEqual(hits, [])

    def test_map_entry_matches_repo_map(self):
        mp = ROOT / "23-ai-workforce-blueprint" / "skill-department-map.json"
        if not mp.is_file():
            self.skipTest("skill-department-map.json is repository-only")
        entry = json.loads((SKILL / "repo-integration" / "skill-department-map-entry.json").read_text(encoding="utf-8"))
        mapped = [s for s in json.loads(mp.read_text(encoding="utf-8"))["skills"] if s["skill"] == "84"]
        self.assertEqual(mapped, [entry])


if __name__ == "__main__":
    unittest.main(verbosity=2)

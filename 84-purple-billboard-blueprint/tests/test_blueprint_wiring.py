"""Skill 84 wiring check: the blueprint may only name code that exists.

Run: python3 -I 84-purple-billboard-blueprint/tests/test_blueprint_wiring.py
Checks every named path exists and every function, class and command-line
subcommand named beside a module is defined in it (read with ast, nothing is
imported or run). CI runs this as an explicit step of .github/workflows/qc-static.yml.
Standard library only. Works in the repository and on a box, because every
path is resolved against the skills root (the folder holding the numbered
skill folders and shared-utils/).
"""
import ast
import json
import re
import tempfile
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


# Symbols. A backticked .py path may be followed by a parenthesised list of
# names ("`mod.py` (`Class`: `method`, `func`)"), and its own token may carry a
# command-line subcommand ("`mod.py admit --x`" or "`mod.py {a,b}`"). Each such
# name must be defined in THAT module. Names that appear elsewhere in a row
# (status labels, constants quoted for context) are not claims about a module.
TOKEN = re.compile(r"`([^`\n]+)`")
AFTER = re.compile(r"\s*\(([^()\n]*)\)")
NAME = re.compile(r"^\.?[A-Za-z_]\w*(\.[A-Za-z_]\w*)*$")
SUBCMD = re.compile(r"^[a-z][a-z0-9-]*$")


def _claims(text):
    """Yield (module path relative to the skills root, name, kind) for each claim."""
    for m in TOKEN.finditer(text):
        words = m.group(1).split()
        mod = words[0].rstrip(",.;:)")
        if not (ROOTED.match(mod) and mod.endswith(".py")):
            continue
        if len(words) > 1:
            w = words[1]
            if w.startswith("{") and w.endswith("}"):
                for s in w[1:-1].split(","):
                    yield mod, s, "sub"
            elif SUBCMD.match(w):
                yield mod, w, "sub"
        group = AFTER.match(text, m.end())
        if group:
            for name in TOKEN.findall(group.group(1)):
                if NAME.match(name):
                    yield mod, name, "name"


def _defined(path):
    """(top-level and nested def/class/constant names, {class: member names}, argparse subcommands)."""
    names, members, subs = set(), {}, set()
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        if isinstance(node, ast.ClassDef):
            members[node.name] = {
                c.name for c in node.body if isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            } | {
                t.id for c in node.body if isinstance(c, ast.Assign) for t in c.targets if isinstance(t, ast.Name)
            }
        if isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_parser"
                and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
            subs.add(node.args[0].value)
    return names, members, subs


def _undefined(path, claims):
    """Names in `claims` [(name, kind)] that `path` does not define."""
    names, members, subs = _defined(path)
    out = []
    for name, kind in claims:
        if kind == "sub":
            ok = name in subs
        elif name.startswith("."):
            ok = name[1:] in names
        elif "." in name:
            # ponytail: one level, "Class.member"; deeper chains are not claimed in the docs.
            owner, _, member = name.partition(".")
            ok = member in members.get(owner, ())
        else:
            ok = name in names or name in subs  # "admit, then reply" in prose names subcommands
        if not ok:
            out.append(name)
    return out


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

    def test_every_named_symbol_is_defined(self):
        by_module = {}
        for f in CHECKED:
            for mod, name, kind in _claims(f.read_text(encoding="utf-8")):
                by_module.setdefault((f.name, mod), set()).add((name, kind))
        total = sum(len(v) for v in by_module.values())
        self.assertGreater(total, 100, "symbol scan found suspiciously few names: the scanner is broken")
        bad = []
        for (fname, mod), claims in sorted(by_module.items()):
            path = ROOT / mod
            if not path.is_file():
                continue  # test_every_named_path_exists reports the missing file
            bad += ["%s -> %s: %s" % (fname, mod, n) for n in _undefined(path, sorted(claims))]
        self.assertEqual(bad, [], "named functions, classes or subcommands that the module does not define")

    def test_symbol_scanner_discriminates(self):
        src = (
            "import argparse\n"
            "K = 1\n"
            "def gamma(): pass\n"
            "class Alpha:\n"
            "    def beta(self): pass\n"
            "def main():\n"
            "    argparse.ArgumentParser().add_subparsers().add_parser('delta')\n"
        )
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "m.py"
            p.write_text(src, encoding="utf-8")
            ok = [("Alpha", "name"), ("Alpha.beta", "name"), (".beta", "name"), ("gamma", "name"),
                  ("K", "name"), ("delta", "sub"), ("delta", "name")]
            self.assertEqual(_undefined(p, ok), [])
            nope = [("Beta", "name"), ("Alpha.gamma", "name"), (".nope", "name"), ("gamma_renamed", "name"),
                    ("gamma", "sub"), ("delta2", "sub")]
            self.assertEqual(_undefined(p, nope), [n for n, _ in nope])
        claims = list(_claims("`38-x/tools/m.py` (`A.b`, `c`) then `38-x/tools/m.py run --k` and `38-x/tools/m.py {p,q}` and `x.json` (`z`)"))
        self.assertIn(("38-x/tools/m.py", "A.b", "name"), claims)
        self.assertIn(("38-x/tools/m.py", "run", "sub"), claims)
        self.assertIn(("38-x/tools/m.py", "q", "sub"), claims)
        self.assertNotIn("z", [n for _, n, _ in claims])

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

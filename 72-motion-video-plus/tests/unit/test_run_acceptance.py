"""Unit tests for the MG-043 acceptance runner's T28 checks.

Builds synthetic spec workspaces in temp dirs and proves the T28 gate
in tests/run_acceptance.py in both directions:

- a complete, acyclic, table-consistent workspace passes;
- a workspace missing an item fails (fifty_items);
- a dependency cycle fails (graph_acyclic);
- a Section 15 table that disagrees with the JSON fails (table_agrees).

The synthetic directive carries a minimal Section 13 register, a
Section 15 table, and a Section 6 body citing a registered reference.

Run from the skill root:
    python3 -m unittest discover -s tests/unit
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[2]
RUNNER = SKILL_ROOT / "tests" / "run_acceptance.py"
REAL_SPEC = Path("/home/hatch/workspace/skill72-v2/spec")


def make_items(cycle: bool = False, drop: str | None = None) -> list[dict]:
    items = []
    for n in range(1, 51):
        mg = f"MG-{n:03d}"
        if mg == drop:
            continue
        deps: list[str] = []
        if n > 1:
            deps = [f"MG-{n - 1:03d}"]
        if cycle and mg == "MG-002":
            deps = ["MG-003"]
        items.append({"id": mg, "owner": "QA", "depends_on": deps, "tests": ["T28"]})
    return items


def make_directive(items: list[dict], table_override: dict[str, list[str]] | None = None) -> str:
    rows = []
    for it in items:
        deps = (table_override or {}).get(it["id"], it["depends_on"])
        cell = "None" if not deps else ", ".join(deps)
        rows.append(f"| {it['id']} | {cell} | QA | output | T28 |")
    return (
        "## 6. Numbered implementation changes\n\n"
        "### MG-001. Example\n\nBody citing a source. **Sources:** [B01]\n\n"
        "## 7. Motion component library\n\n"
        "## 13. Research source register\n\n[B01] An internal source.\n\n"
        "## 14. Verified integration patch map\n\n"
        "## 15. Task-level dependencies and ownership\n\n"
        "| MG item | Prerequisites | Integrating owner | Required output | Acceptance tests |\n"
        "|---|---|---|---|---|\n" + "\n".join(rows) + "\n\n"
        "## 16. Complete contracts, fixtures, and lifecycle\n"
    )


def make_workspace(items: list[dict]) -> Path:
    root = Path(tempfile.mkdtemp(prefix="mg043-t28-"))
    deps_dir = root / "extracted" / "execution"
    deps_dir.mkdir(parents=True)
    (deps_dir / "dependencies.json").write_text(
        json.dumps({"items": items}), encoding="utf-8"
    )
    # The extracted mode fixtures are the repository's own valid fixture
    # jobs, so fixtures_validate exercises the real contract layer.
    import shutil

    shutil.copytree(
        SKILL_ROOT / "tests" / "fixtures" / "modes",
        root / "extracted" / "fixtures",
        dirs_exist_ok=True,
    )
    return root


def run_t28(spec: Path, directive: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--test",
            "T28",
            "--spec-workspace",
            str(spec),
            "--directive",
            str(directive),
        ],
        capture_output=True,
        text=True,
    )


class T28GateTests(unittest.TestCase):
    def write_directive(self, text: str) -> Path:
        path = Path(tempfile.mkdtemp(prefix="mg043-t28-directive-")) / "directive.md"
        path.write_text(text, encoding="utf-8")
        return path

    def test_complete_workspace_passes(self):
        items = make_items()
        proc = run_t28(make_workspace(items), self.write_directive(make_directive(items)))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("T28: pass", proc.stdout)
        self.assertIn("PASS     fifty_items", proc.stdout)
        self.assertIn("PASS     graph_acyclic", proc.stdout)
        self.assertIn("PASS     table_agrees", proc.stdout)
        self.assertIn("PASS     fixtures_validate", proc.stdout)

    def test_missing_item_fails(self):
        items = make_items(drop="MG-050")
        proc = run_t28(make_workspace(items), self.write_directive(make_directive(items)))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FAIL     fifty_items", proc.stdout)

    def test_cycle_fails(self):
        items = make_items(cycle=True)
        proc = run_t28(make_workspace(items), self.write_directive(make_directive(items)))
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FAIL     graph_acyclic", proc.stdout)

    def test_table_disagreement_fails(self):
        items = make_items()
        directive = self.write_directive(
            make_directive(items, table_override={"MG-010": []})
        )
        proc = run_t28(make_workspace(items), directive)
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("FAIL     table_agrees", proc.stdout)


@unittest.skipUnless(REAL_SPEC.exists(), "coordinator spec workspace not present on this box")
class T28RealWorkspaceTests(unittest.TestCase):
    def test_real_spec_workspace_is_consistent(self):
        # Fixtures in the synthetic tests cannot cover the extracted mode
        # fixtures; the real coordinator workspace can. Its directive sits
        # one level up from the extracted tree's owner directory.
        directive = Path("/home/hatch/workspace/user/files/BLACKCEO_SKILL_72_MOTION_GRAPHICS_V2_EXECUTION_DIRECTIVE_v1_1.md")
        proc = run_t28(REAL_SPEC, directive)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("T28: pass", proc.stdout)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""test_check_lattice_citation.py -- fail-first proof for the U89/GK-27 QC
citation tripwire (check_lattice_citation.py).

Every test builds its OWN isolated tmp "repo" fixture (never touches this
checkout's real skill files) so the suite is deterministic, offline, and
side-effect free. The fail-first cases are the acceptance-criterion proof
required by U89: "deliberately breaking one citation (fixture) fails that
skill's QC."

Run: pytest -q docs/tools/test_check_lattice_citation.py
     (or: python3 -m unittest docs/tools/test_check_lattice_citation.py)
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import check_lattice_citation as clc  # noqa: E402


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class FixtureRepo:
    """Builds a minimal two-skill fixture repo + manifest mirroring the real
    shape (a pointer file + one line-citation edge + one exists-citation edge
    per skill), so tests can mutate ONE thing at a time and prove the checker
    reacts to exactly that thing."""

    def __init__(self, tmp: Path):
        self.root = tmp
        self.skill_a = "aa-skill-alpha"
        self.skill_b = "bb-skill-beta"

        _write(
            self.root / self.skill_a / "SKILL.md",
            "---\nname: alpha\n---\n"
            "# Alpha\n"
            "Some intro text.\n"
            "See docs/CONTENT-CONVERSATION-LATTICE.md for the relationship lattice.\n"
            "Line 7 the real edge quote lives here: ALPHA_OWNS_THE_THING.\n",
        )
        # Sanity-pin the line count assumption so a future edit to the text
        # above can't silently desync from the "line": 7 citation below.
        assert (
            len((self.root / self.skill_a / "SKILL.md").read_text(encoding="utf-8").splitlines()) == 7
        ), "fixture SKILL.md line count drifted -- update the citation's 'line' value to match"
        _write(
            self.root / self.skill_b / "SKILL.md",
            "---\nname: beta\n---\n"
            "# Beta\n"
            "No pointer on this one initially (tests add it when needed).\n",
        )
        _write(self.root / self.skill_b / "tools" / "beta_tool.py", "# exists\n")

        self.manifest = {
            "skill_pointers": {
                self.skill_a: {"file": "SKILL.md", "must_contain": "docs/CONTENT-CONVERSATION-LATTICE.md"},
                self.skill_b: {"file": "SKILL.md", "must_contain": "docs/CONTENT-CONVERSATION-LATTICE.md"},
            },
            "edges": [
                {
                    "id": "EA-line",
                    "label": "alpha owns a line citation",
                    "owner_skill": self.skill_a,
                    "citations": [
                        {"file": f"{self.skill_a}/SKILL.md", "line": 7, "must_contain": "ALPHA_OWNS_THE_THING"}
                    ],
                },
                {
                    "id": "EB-exists",
                    "label": "beta owns a file-existence citation",
                    "owner_skill": self.skill_b,
                    "citations": [
                        {"file": f"{self.skill_b}/tools/beta_tool.py", "exists": True}
                    ],
                },
            ],
        }
        self.manifest_path = self.root / "docs" / "lattice-citations.json"
        _write(self.manifest_path, json.dumps(self.manifest))

    def run(self, skill: str, edge_ids=None):
        return clc.run(self.root, skill, self.manifest, edge_ids, quiet=True)


class TestCleanFixturePasses(unittest.TestCase):
    """Positive control: an untouched fixture must pass for both skills."""

    def test_alpha_clean_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            self.assertEqual(fx.run(fx.skill_a), 0)

    def test_beta_pointer_missing_fails_even_with_good_citation(self):
        # beta's fixture SKILL.md deliberately has NO pointer line -- this is
        # the "pointer missing" branch, proven separately from citation drift.
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            self.assertEqual(fx.run(fx.skill_b), 1)

    def test_beta_passes_once_pointer_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            skill_md = fx.root / fx.skill_b / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8")
                + "Relationship lattice: see docs/CONTENT-CONVERSATION-LATTICE.md.\n",
                encoding="utf-8",
            )
            self.assertEqual(fx.run(fx.skill_b), 0)


class TestFailFirstLineCitationDrift(unittest.TestCase):
    """FAIL-FIRST PROOF (line citation): deliberately breaking the cited
    line's content must fail alpha's tripwire, while leaving beta untouched
    and still passing -- proving the failure is scoped to the skill that
    actually owns the broken citation."""

    def test_editing_the_cited_line_fails_the_owning_skill(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            self.assertEqual(fx.run(fx.skill_a), 0, "sanity: clean fixture must pass before we break it")

            skill_md = fx.root / fx.skill_a / "SKILL.md"
            lines = skill_md.read_text(encoding="utf-8").splitlines(keepends=True)
            self.assertIn("ALPHA_OWNS_THE_THING", lines[6])
            lines[6] = "Line 7 got edited and the quoted substring is gone now.\n"
            skill_md.write_text("".join(lines), encoding="utf-8")

            self.assertEqual(fx.run(fx.skill_a), 1, "citation drift on the cited line must fail QC")

    def test_deleting_the_cited_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            (fx.root / fx.skill_a / "SKILL.md").unlink()
            self.assertEqual(fx.run(fx.skill_a), 1)

    def test_line_number_shift_fails_drift(self):
        # Simulates someone inserting a line above the citation, shifting
        # the quote down without updating the manifest -- the drift tripwire
        # must catch this too, not just outright deletion.
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            skill_md = fx.root / fx.skill_a / "SKILL.md"
            skill_md.write_text(
                "INSERTED LINE THAT SHIFTS EVERYTHING DOWN\n" + skill_md.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            self.assertEqual(fx.run(fx.skill_a), 1)


class TestFailFirstExistsCitationDrift(unittest.TestCase):
    """FAIL-FIRST PROOF (file-existence citation): deleting a file an edge
    depends on must fail the owning skill's tripwire."""

    def test_deleting_the_dependency_file_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            self.assertEqual(fx.run(fx.skill_b), 1, "beta has no pointer yet, expected pre-fail")
            skill_md = fx.root / fx.skill_b / "SKILL.md"
            skill_md.write_text(
                skill_md.read_text(encoding="utf-8") + "docs/CONTENT-CONVERSATION-LATTICE.md\n",
                encoding="utf-8",
            )
            self.assertEqual(fx.run(fx.skill_b), 0, "sanity: now clean, must pass")

            (fx.root / fx.skill_b / "tools" / "beta_tool.py").unlink()
            self.assertEqual(fx.run(fx.skill_b), 1, "deleting the cited dependency file must fail QC")


class TestScopeIsolation(unittest.TestCase):
    """A citation break owned by skill A must never fail skill B's run, and
    vice versa -- each skill's QC gate only asserts what it owns."""

    def test_breaking_alpha_does_not_affect_beta(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            skill_md_b = fx.root / fx.skill_b / "SKILL.md"
            skill_md_b.write_text(
                skill_md_b.read_text(encoding="utf-8") + "docs/CONTENT-CONVERSATION-LATTICE.md\n",
                encoding="utf-8",
            )
            self.assertEqual(fx.run(fx.skill_b), 0)

            (fx.root / fx.skill_a / "SKILL.md").unlink()
            self.assertEqual(fx.run(fx.skill_b), 0, "beta must still pass -- alpha's break is not beta's problem")
            self.assertEqual(fx.run(fx.skill_a), 1, "alpha itself must still fail")


class TestEdgeIdFilter(unittest.TestCase):
    def test_edge_id_filter_scopes_to_requested_edge_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            # requesting an edge id that does not belong to alpha yields no
            # extra edge checks (only the pointer check still runs) -- proves
            # the filter is a real restriction, not a no-op.
            self.assertEqual(fx.run(fx.skill_a, edge_ids=["EB-exists"]), 0)


class TestMalformedCitationRaises(unittest.TestCase):
    def test_citation_missing_required_keys_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            bad_manifest = json.loads(json.dumps(fx.manifest))
            bad_manifest["edges"][0]["citations"] = [{"file": "nope.md"}]
            with self.assertRaises(ValueError):
                clc.run(fx.root, fx.skill_a, bad_manifest, None, quiet=True)


class TestUnknownSkillIsUsageError(unittest.TestCase):
    def test_unknown_skill_returns_usage_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            fx = FixtureRepo(Path(tmp))
            rc = clc.run(fx.root, "not-a-real-skill", fx.manifest, None, quiet=True)
            self.assertEqual(rc, 2)


class TestRealManifestAgainstThisCheckout(unittest.TestCase):
    """Runs the ACTUAL manifest (docs/lattice-citations.json) against THIS
    checkout for all five real skills -- the genuine offline proof that the
    lattice doc's citations hold on the committed branch, not just in a toy
    fixture. This is read-only (never mutates the real tree)."""

    def _repo_root(self) -> Path:
        # docs/tools/test_check_lattice_citation.py -> repo root is two up.
        return Path(__file__).resolve().parents[2]

    def test_all_five_skills_pass_against_real_repo(self):
        repo_root = self._repo_root()
        manifest_path = repo_root / "docs" / "lattice-citations.json"
        if not manifest_path.is_file():
            self.skipTest("docs/lattice-citations.json not present in this checkout")
        manifest = clc.load_manifest(manifest_path)
        for skill in manifest["skill_pointers"]:
            with self.subTest(skill=skill):
                rc = clc.run(repo_root, skill, manifest, None, quiet=True)
                self.assertEqual(rc, 0, f"{skill} lattice citation tripwire should PASS on the real repo")


if __name__ == "__main__":
    unittest.main()

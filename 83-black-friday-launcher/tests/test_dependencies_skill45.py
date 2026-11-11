"""Skill 45 is a dependency of a client package, and three of its SOPs are read receipts (issues 7, 34).

Skill 45's graphics_ghl_push.py is the only route that hosts a package's images on the GHL media
library, and the design library is what styles the pages. Neither was in dependencies.json, so the
preflight was green on a box where a client package could never be hosted. Now:

  * `tree-45-design-intelligence-library` and `script-45-graphics-ghl-push` are assemble-mode rows
    that apply to a CLIENT package (`"when": "not_test_only"`); a practice package stays buildable;
  * SOP-DIU-602, 607 and 610 are `sop` rows with read receipts, like SOP-GIP-02 and 03, so `assemble`
    refuses when a receipt is absent, stale or names another SOP.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_ROOT))

from launcher_core import cli, dependencies  # noqa: E402

SKILL_45_ROWS = ("tree-45-design-intelligence-library", "script-45-graphics-ghl-push")
DIU_SOP_ROWS = {"sop-diu-602-generation-receipts": "SOP-DIU-602",
                "sop-diu-607-named-styles": "SOP-DIU-607",
                "sop-diu-610-rights-manifest": "SOP-DIU-610"}


def entries() -> dict:
    return {e["id"]: e for e in dependencies.load_manifest()["entries"]}


class Skill45Rows(unittest.TestCase):
    def test_the_two_rows_are_assemble_rows_for_a_client_package(self):
        for row_id in SKILL_45_ROWS:
            row = entries()[row_id]
            self.assertEqual(row["class"], "selected_conditional", row_id)
            self.assertEqual(row["modes"], ["assemble"], row_id)
            self.assertEqual(row["when"], "not_test_only", row_id)
            self.assertIs(row["required"], False, row_id)
        self.assertEqual(entries()["script-45-graphics-ghl-push"]["ref"],
                         "45-design-intelligence-library/scripts/graphics_ghl_push.py")

    def test_the_tree_row_carries_a_version_floor_the_shipped_skill_meets(self):
        row = entries()["tree-45-design-intelligence-library"]
        self.assertTrue(row.get("min_version"), "every skill_tree row names a floor")
        tree = SKILL_ROOT.parent / row["ref"]
        self.assertIsNone(dependencies._version_floor(row, tree))

    def test_the_hosting_route_the_launcher_calls_is_the_row(self):
        from launcher_core import graphics_hooks
        self.assertEqual(graphics_hooks.PUSH_REF, entries()["script-45-graphics-ghl-push"]["ref"])

    def test_assemble_lists_both_rows_and_both_resolve_in_this_repository(self):
        report = dependencies.check(mode="assemble")
        by_id = {e["id"]: e for e in report["entries"]}
        for row_id in SKILL_45_ROWS:
            self.assertEqual(by_id[row_id]["status"], "present", by_id[row_id]["evidence"])
            self.assertTrue(by_id[row_id]["selected"], row_id)

    def test_a_box_without_skill_45_is_refused_for_a_client_package_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            client = dependencies.check(Path(tmp), "assemble", test_only=False)
            practice = dependencies.check(Path(tmp), "assemble", test_only=True)
            unknown = dependencies.check(Path(tmp), "assemble")
        for report in (client, unknown):  # unknown is never a pass
            by_id = {e["id"]: e for e in report["entries"]}
            for row_id in SKILL_45_ROWS:
                self.assertEqual(by_id[row_id]["status"], "missing", row_id)
                self.assertTrue(by_id[row_id]["blocking"], row_id)
                self.assertIn(row_id, report["blockers"])
        by_id = {e["id"]: e for e in practice["entries"]}
        for row_id in SKILL_45_ROWS:
            self.assertEqual(by_id[row_id]["status"], "missing", row_id)  # still reported
            self.assertFalse(by_id[row_id]["selected"], row_id)
            self.assertFalse(by_id[row_id]["blocking"], row_id)
            self.assertNotIn(row_id, practice["blockers"])

    def test_require_refuses_a_client_package_by_row_name(self):
        def check_only(root=None, install=None, mode=None):  # never pip-installs in a test
            return dependencies.check(root, mode)
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(dependencies, "ensure_runtime_packages", side_effect=check_only):
            with self.assertRaises(dependencies.DependencyError) as ctx:
                dependencies.require(Path(tmp), "assemble", test_only=False)
        self.assertIn("tree-45-design-intelligence-library", str(ctx.exception))
        self.assertIn("script-45-graphics-ghl-push", str(ctx.exception))

    def test_cli_assemble_tells_the_preflight_whether_the_package_is_a_practice_one(self):
        seen = []

        class Stop(Exception):
            pass

        def record(**kwargs):
            seen.append(kwargs)
            raise Stop

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(dependencies, "require", side_effect=record):
            for intake, want in (({"test_only": False}, False), ({"test_only": True}, True), ({}, True)):
                path = Path(tmp) / "intake.json"
                path.write_text(json.dumps(intake), encoding="utf-8")
                args = mock.Mock(intake=str(path))
                with self.assertRaises(Stop):
                    cli.cmd_assemble(args)
                self.assertEqual(seen[-1], {"mode": "assemble", "test_only": want}, intake)


class DiuSopReceipts(unittest.TestCase):
    def test_three_diu_sops_are_sop_rows_with_receipts(self):
        for row_id, name in DIU_SOP_ROWS.items():
            row = entries()[row_id]
            self.assertEqual(row["kind"], "sop", row_id)
            self.assertEqual(row["modes"], ["assemble"], row_id)
            self.assertEqual(row["receipt"], f"receipts/sop-read/{name}.json", row_id)
            self.assertTrue(row["ref"].endswith(f"/{name}.md"), row_id)

    def test_every_receipt_matches_its_sop_and_says_it_was_read_in_full(self):
        for row_id, name in DIU_SOP_ROWS.items():
            row = entries()[row_id]
            receipt = json.loads((SKILL_ROOT / row["receipt"]).read_text(encoding="utf-8"))
            sop = SKILL_ROOT.parent / row["ref"]
            self.assertEqual(receipt["sop"], row["ref"])
            self.assertEqual(receipt["sha256"], hashlib.sha256(sop.read_bytes()).hexdigest(), f"{name} changed")
            self.assertIs(receipt["read_in_full"], True)
            result = dependencies._present(row, dependencies._repo_root())
            self.assertEqual(result["status"], "present", result["evidence"])

    def test_the_declared_read_list_in_skill_md_names_them(self):
        text = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for name in DIU_SOP_ROWS.values():
            self.assertIn(f"sops/{name}.md", text)

    def test_the_metadata_pointers_were_restamped_with_the_new_rows(self):
        manifest = dependencies.load_manifest()
        for name in ("registration.json", "skill.json"):
            spine = json.loads((SKILL_ROOT / name).read_text(encoding="utf-8"))["depends_on"]
            self.assertEqual(spine["manifest_entry_count"], len(manifest["entries"]), name)
            self.assertEqual(spine["requirements_digest"], dependencies.requirements_digest(manifest), name)
        self.assertEqual(dependencies.metadata_spine(manifest)["findings"], [])


if __name__ == "__main__":
    unittest.main()

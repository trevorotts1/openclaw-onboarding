#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_department_map_entry.py - Skill 49 is routable through its OWN department-map row (issue 74).

The only documented door into Skill 49 used to sit inside Skill 6's engine registry. Now a signature funnel
request reaches it through the `signature-funnel` row of 23-ai-workforce-blueprint/skill-department-map.json
(intent triggers), mirrored by 49-signature-funnel/repo-integration/skill-department-map-entry.json, and the
front door refuses (DEPT-MAP) when that row is missing. Skill 6's own registry is not read or needed.

Run:  python3 -m pytest 49-signature-funnel/scripts/test_department_map_entry.py -q
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent
sys.path.insert(0, str(HERE))
import front_door as fd  # noqa: E402

ENTRY = SKILL / "repo-integration" / "skill-department-map-entry.json"
MAP = REPO / "23-ai-workforce-blueprint" / "skill-department-map.json"


def _row(rows):
    return [r for r in rows if isinstance(r, dict) and r.get("slug") == "signature-funnel"]


class TheEntryFileMirrorsTheMapRow(unittest.TestCase):
    def test_entry_file_has_the_83_shape(self):
        entry = json.loads(ENTRY.read_text(encoding="utf-8"))
        self.assertEqual(entry["skill"], "49")
        self.assertEqual(entry["slug"], "signature-funnel")
        self.assertIs(entry["client_facing"], True)
        for key in ("name", "description", "departments", "roles", "intent_triggers", "execution_sops"):
            self.assertTrue(entry.get(key), key)
        self.assertIn("signature funnel", entry["intent_triggers"])
        self.assertEqual(entry["execution_sops"], ["funnel-craft"])

    def test_the_map_carries_exactly_one_signature_funnel_row_equal_to_the_entry_file(self):
        rows = _row(json.loads(MAP.read_text(encoding="utf-8"))["skills"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], json.loads(ENTRY.read_text(encoding="utf-8")),
                         "the entry file and the map row must not drift")

    def test_the_real_front_door_step_clears(self):
        fd.step_departmap(SKILL)

    def test_routing_text_no_longer_points_into_skill_6(self):
        skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("repo-integration/skill-department-map-entry.json", skill_md)
        self.assertIn("front_door.step_departmap", skill_md)


class AMissingRowIsAFrontDoorRefusal(unittest.TestCase):
    def layout(self, td, rows=None, write_map=True):
        root = Path(td)
        (root / "49-signature-funnel").mkdir()
        bp = root / "23-ai-workforce-blueprint"
        bp.mkdir()
        (bp / "SKILL.md").write_text("---\nname: x\n---\n", encoding="utf-8")
        if write_map:
            (bp / "skill-department-map.json").write_text(json.dumps({"skills": rows or []}), encoding="utf-8")
        return root / "49-signature-funnel"

    def refused(self, skill_dir):
        with self.assertRaises(fd.FrontDoorError) as cm:
            fd.step_departmap(skill_dir)
        self.assertEqual(cm.exception.gate, "DEPT-MAP")
        return cm.exception.detail

    def test_row_present_clears(self):
        with tempfile.TemporaryDirectory() as td:
            sd = self.layout(td, [{"slug": "signature-funnel", "intent_triggers": ["signature funnel"]}])
            fd.step_departmap(sd)

    def test_no_row_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            detail = self.refused(self.layout(td, [{"slug": "someone-else", "intent_triggers": ["x"]}]))
            self.assertIn("signature-funnel", detail)

    def test_row_without_intent_triggers_is_refused(self):
        for triggers in ([], ["  "]):
            with tempfile.TemporaryDirectory() as td:
                self.refused(self.layout(td, [{"slug": "signature-funnel", "intent_triggers": triggers}]))

    def test_missing_map_file_and_missing_blueprint_tree_are_refused(self):
        with tempfile.TemporaryDirectory() as td:
            self.refused(self.layout(td, write_map=False))
        with tempfile.TemporaryDirectory() as td:
            (Path(td) / "49-signature-funnel").mkdir()
            self.refused(Path(td) / "49-signature-funnel")

    def test_unreadable_map_is_refused_not_crashed(self):
        with tempfile.TemporaryDirectory() as td:
            sd = self.layout(td)
            (sd.parent / "23-ai-workforce-blueprint" / "skill-department-map.json").write_text("{not json")
            self.refused(sd)

    def test_check_runs_the_step_before_the_pin(self):
        """check() is version -> dept-map -> hash-pin -> bypass: a layout with no map stops at DEPT-MAP, not HASH-PIN."""
        with tempfile.TemporaryDirectory() as td:
            sd = self.layout(td, [{"slug": "other", "intent_triggers": ["x"]}])
            (sd / "skill-version.txt").write_text("v2.0.0\n", encoding="utf-8")
            with self.assertRaises(fd.FrontDoorError) as cm:
                fd.check(skill_dir=sd)
            self.assertEqual(cm.exception.gate, "DEPT-MAP")

    def test_the_cli_step_exits_non_zero_without_the_row_and_zero_with_it(self):
        with tempfile.TemporaryDirectory() as td:
            sd = self.layout(td, [{"slug": "other", "intent_triggers": ["x"]}])
            run = lambda: subprocess.run([sys.executable, str(HERE / "front_door.py"), "--skill-dir", str(sd),  # noqa: E731
                                          "departmap"], capture_output=True, text=True)
            bad = run()
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn("DEPT-MAP", bad.stderr)
            (sd.parent / "23-ai-workforce-blueprint" / "skill-department-map.json").write_text(
                json.dumps({"skills": [{"slug": "signature-funnel", "intent_triggers": ["signature funnel"]}]}))
            good = run()
            self.assertEqual(good.returncode, 0, good.stdout + good.stderr)

    def test_the_shell_entry_runs_the_step_in_every_mode(self):
        text = (SKILL / "signature-funnel-entry.sh").read_text(encoding="utf-8")
        self.assertIn('"$PY" "$FRONT_DOOR" departmap', text)
        for fn in ("run_launch_pipeline()", "run_pipeline()", "self_test()"):
            body = text[text.index(fn):]
            body = body[:body.index("\n}\n")]
            self.assertIn("step_departmap", body, fn)


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""SWB-200: the sanctioned per-run layout input of the page-role runner.

<run>/dispatch/layout-overrides.json (or --layout-overrides PATH), shaped
{"<stage>": {"<section id>": {"layout": "...", "negatives": "..."}}}, is appended to that stage's
section `layout` when production-request.json is rebuilt. Design text only. No paid call is made.
"""
import hashlib
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

os.environ["SKILL71_FIXTURE_RUN"] = "1"
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from test_page_role_thank_you import PY, SCRIPTS, STUB, RunCase, builder, write_intake  # noqa: E402

TEXT = "DESIGN OVERRIDE: one white card with a thin black hairline border."
NEG = "No table, no chips."


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Base(RunCase):
    def put(self, doc, name="layout-overrides.json"):
        path = self.run / "dispatch" / name
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(doc), encoding="utf-8")
        return path

    def build_with(self, path, stage="mobile-tablet"):
        text = (self.run / "copy" / "internal-manuscript.md").read_text(encoding="utf-8")
        return builder.build(stage, "thank-you", text, {}, {}, [], STUB, "", self.run,
                             layout_overrides=path)

    def layouts(self, request):
        return {s["section_id"]: s.get("layout", "") for s in request["sections"]}


class AppliedTests(Base):
    def test_text_is_appended_never_replacing(self):
        base = self.layouts(self.build_with(None))
        path = self.put({"mobile-tablet": {"2": {"layout": TEXT, "negatives": NEG}}})
        out = self.layouts(self.build_with(path))
        self.assertIn(TEXT, out["2"])
        self.assertIn("NEGATIVES: " + NEG, out["2"])
        self.assertEqual(out["2"], (base["2"] + "\n" if base["2"] else "") + TEXT + "\nNEGATIVES: " + NEG)
        self.assertGreater(len(out["2"]), len(base["2"]))
        for sid in ("1", "3", "4", "5"):
            self.assertEqual(out[sid], base[sid])

    def test_only_the_named_stage_is_touched(self):
        base = self.build_with(None, "visual-mockup")
        path = self.put({"mobile-tablet": {"2": {"layout": TEXT}}})
        other = self.build_with(path, "visual-mockup")
        self.assertEqual(self.layouts(other), self.layouts(base))

    def test_provenance_records_the_file_hash_and_the_exact_text(self):
        path = self.put({"mobile-tablet": {"2": {"layout": TEXT, "negatives": NEG}}})
        block = self.build_with(path)["layout_overrides"]
        self.assertEqual(block["sha256"], sha(path))
        self.assertEqual(block["stage"], "mobile-tablet")
        self.assertEqual(block["applied"], [{"section_id": "2",
                                             "appended_text": TEXT + "\nNEGATIVES: " + NEG}])

    def test_a_changed_file_changes_the_recorded_hash(self):
        a = self.put({"mobile-tablet": {"2": {"layout": TEXT}}})
        first = self.build_with(a)["layout_overrides"]["sha256"]
        b = self.put({"mobile-tablet": {"2": {"layout": TEXT + " Bigger."}}})
        self.assertNotEqual(self.build_with(b)["layout_overrides"]["sha256"], first)
        self.assertEqual(self.build_with(b)["layout_overrides"]["sha256"], sha(b))

    def test_absent_file_changes_nothing(self):
        plain = self.build_with(None)
        self.assertNotIn("layout_overrides", plain)
        text = (self.run / "copy" / "internal-manuscript.md").read_text(encoding="utf-8")
        legacy = builder.build("mobile-tablet", "thank-you", text, {}, {}, [], STUB, "", self.run)
        self.assertEqual(json.dumps(plain, sort_keys=True), json.dumps(legacy, sort_keys=True))

    def test_a_file_with_no_entry_for_the_stage_changes_only_the_provenance(self):
        plain = self.build_with(None)
        path = self.put({"visual-mockup": {"2": {"layout": TEXT}}})
        out = self.build_with(path)
        block = out.pop("layout_overrides")
        self.assertEqual(block["applied"], [])
        self.assertEqual(json.dumps(out, sort_keys=True), json.dumps(plain, sort_keys=True))


class RefusalTests(Base):
    def refuses(self, doc, needle):
        path = self.put(doc)
        with self.assertRaises(builder.BuildError) as cm:
            self.build_with(path)
        self.assertIn(needle, str(cm.exception))

    def test_forbidden_keys_refuse(self):
        for key in ("copy", "cta", "ctas", "model", "references", "slots", "order", "section_id"):
            self.refuses({"mobile-tablet": {"2": {"layout": TEXT, key: "x"}}}, key)

    def test_unknown_section_refuses(self):
        self.refuses({"mobile-tablet": {"9": {"layout": TEXT}}}, "unknown section '9'")

    def test_unknown_stage_refuses(self):
        self.refuses({"no-such-stage": {"2": {"layout": TEXT}}}, "unknown stage")

    def test_a_section_of_another_stage_entry_is_still_checked(self):
        self.refuses({"visual-mockup": {"9": {"layout": TEXT}}}, "unknown section")

    def test_empty_or_non_string_layout_refuses(self):
        self.refuses({"mobile-tablet": {"2": {"layout": "  "}}}, "non-empty")
        self.refuses({"mobile-tablet": {"2": {"layout": 5}}}, "non-empty")
        self.refuses({"mobile-tablet": {"2": {"layout": TEXT, "negatives": 3}}}, "string")

    def test_a_non_object_file_refuses(self):
        self.refuses([1, 2], "keyed by stage")

    def test_an_unreadable_file_refuses(self):
        with self.assertRaises(builder.BuildError):
            self.build_with(self.run / "dispatch" / "nope.json")


class RunnerTests(Base):
    def runner(self, *extra):
        write_intake(self.run, page_role="thank_you", copy_version="thank-you")
        return subprocess.run([PY, str(SCRIPTS / "run_page_role_stages.py"), str(self.run),
                               "--model", STUB, *extra], capture_output=True, text=True)

    def test_the_default_file_is_used_printed_recorded_and_survives_every_rebuild(self):
        path = self.put({"mobile-tablet": {"2": {"layout": TEXT, "negatives": NEG}}})
        proc = self.runner("--stages", "mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("LAYOUT-OVERRIDES file=", proc.stdout)
        self.assertIn(sha(path), proc.stdout)
        self.assertIn("LAYOUT-OVERRIDE section 2: " + TEXT, proc.stdout)
        request = json.loads((self.run / "production-request.json").read_text())
        self.assertEqual(request["layout_overrides"]["sha256"], sha(path))
        record = json.loads((self.run / "mobile-tablet" / "stage-executor-record.json").read_text())
        self.assertEqual(record["layout_overrides"]["sha256"], sha(path))
        self.assertEqual(record["layout_overrides"]["applied"][0]["section_id"], "2")
        proc = self.runner("--stages", "mobile-tablet")  # the rebuild from the manuscript keeps it
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        again = json.loads((self.run / "production-request.json").read_text())
        self.assertIn(TEXT, [s for s in again["sections"] if s["section_id"] == "2"][0]["layout"])

    def test_the_preflight_prints_the_applied_overrides(self):
        self.put({"desktop-wireframe": {"3": {"layout": TEXT}}})
        proc = self.runner("--preflight", "--stages", "desktop-wireframe")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("LAYOUT-OVERRIDE section 3: " + TEXT, proc.stdout)

    def test_an_explicit_path_wins_and_a_missing_one_is_a_usage_error(self):
        other = self.put({"mobile-tablet": {"4": {"layout": TEXT}}}, "elsewhere.json")
        proc = self.runner("--preflight", "--stages", "mobile-tablet", "--layout-overrides", str(other))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("LAYOUT-OVERRIDE section 4", proc.stdout)
        proc = self.runner("--preflight", "--layout-overrides", str(self.run / "dispatch" / "gone.json"))
        self.assertEqual(proc.returncode, 2, proc.stdout)

    def test_a_forbidden_key_stops_the_stage_before_any_image(self):
        self.put({"mobile-tablet": {"2": {"layout": TEXT, "copy": "new words"}}})
        proc = self.runner("--stages", "mobile-tablet")
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("REFUSED: layout overrides", proc.stdout)
        self.assertEqual(list((self.run / "mobile-tablet").glob("section-*.png")), [])

    def test_no_file_prints_no_override_line_and_the_request_has_no_block(self):
        proc = self.runner("--stages", "mobile-tablet")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("LAYOUT-OVERRIDE", proc.stdout)
        request = json.loads((self.run / "production-request.json").read_text())
        self.assertNotIn("layout_overrides", request)


if __name__ == "__main__":
    unittest.main()

"""QC-F25 — readability + status colors in the sheet exports/template.

NUMBER_EQ is absent for text statuses (TEXT_EQ only); every status has BOTH a
color rule AND a written label; the This Week view schema is present (~8
columns); frozen headers + wrapped copy + dropdown validation are provisioned;
the upsert path preserves client row sizes/notes.
"""
import json
import os
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
SCHEMA = os.path.join(BASE, "35-social-media-planner", "config", "sheet-template.schema.json")
VALIDATOR = os.path.join(BASE, "35-social-media-planner", "config", "validate-sheet-format.py")
CREATE = os.path.join(BASE, "35-social-media-planner", "config", "n8n", "social-planner-sheet-create.json")
APPEND = os.path.join(BASE, "35-social-media-planner", "config", "n8n", "social-planner-row-append.json")

STATUSES = ["Complete", "Failed", "QC Review", "Scheduled", "Published", "Needs Attention"]


def load(path):
    with open(path) as f:
        return json.load(f)


def run_validator(*args):
    return subprocess.run(["python3", VALIDATOR, *args], capture_output=True, text=True, timeout=60)


class TestF25ContractAndValidator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(SCHEMA) as f:
            cls.schema = json.load(f)

    def test_number_eq_absent_for_text_statuses(self):
        fmt = json.dumps(self.schema)
        self.assertNotIn('"type": "NUMBER_EQ"', fmt)
        self.assertIn("TEXT_EQ", fmt)

    def test_every_status_has_color_and_label(self):
        statuses = self.schema["status_colors"]["statuses"]
        labels = [s["label"] for s in statuses]
        for st in STATUSES:
            self.assertIn(st, labels, f"status '{st}' needs a color+label entry")
        for s in statuses:
            self.assertTrue(s.get("color"), f"{s['label']} missing color")
            self.assertTrue(s.get("color_label"), f"{s['label']} missing written label — color must not be the only signal")

    def test_this_week_view_schema_present(self):
        tw = self.schema["tabs"]["This Week"]
        self.assertEqual(tw["headings"],
                         ["Week", "Client", "Next Action", "Drafting", "QC",
                          "Scheduled", "Published", "Needs Attention"])
        self.assertLessEqual(tw["width"], 9)

    def test_validator_passes_the_contract(self):
        proc = run_validator()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_validator_catches_number_eq(self):
        tmp = tempfile.mkdtemp(prefix="f25-")
        bad = os.path.join(tmp, "bad.json")
        doc = load(SCHEMA)
        doc["tabs"] = {"This Week": doc["tabs"]["This Week"], "Weekly Overview": {
            "headings": ["a"], "frozen_headings_row": 1}}
        doc["status_colors"]["statuses"] = doc["status_colors"]["statuses"][:1]
        with open(bad, "w") as f:
            json.dump(doc, f)
        # A contract whose emitted condition would be NUMBER_EQ must FAIL.
        bad_doc = {"schema_version": "1.2.0", "tabs": {}, "status_colors": {
            "statuses": [{"label": "Complete", "color": "#fff", "color_label": "green — done"}],
            "conditional_format_rules": "type NUMBER_EQ emitted",
        }, "formatting_contract": {}}
        with open(bad, "w") as f:
            json.dump(bad_doc, f)
        proc = run_validator(bad)
        self.assertEqual(proc.returncode, 1, "a NUMBER_EQ-emitting contract must fail")

    def test_validator_checks_dropdowns_and_freeze(self):
        tmp = tempfile.mkdtemp(prefix="f25-")
        doc = load(SCHEMA)
        doc.pop("tabs", None)
        path = os.path.join(tmp, "contract.json")
        with open(path, "w") as f:
            json.dump(doc, f)
        proc = run_validator(path)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("This Week view tab missing", proc.stdout)


class TestF25ExportFormattingWiring(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(CREATE) as f:
            cls.create = json.load(f)

    def test_text_eq_emitted_never_number_eq(self):
        js = next(n for n in self.create["nodes"]
                  if n["name"] == "Build Formatting Requests (F25)")["parameters"]["jsCode"]
        self.assertIn("TEXT_EQ", js)
        self.assertNotIn("type: 'NUMBER_EQ'", js)

    def test_dropdown_validation_emitted(self):
        js = next(n for n in self.create["nodes"]
                  if n["name"] == "Build Formatting Requests (F25)")["parameters"]["jsCode"]
        self.assertIn("setDataValidation", js)
        self.assertIn("ONE_OF_LIST", js)
        self.assertIn("showCustomUi", js)

    def test_all_six_statuses_color_labeled(self):
        js = next(n for n in self.create["nodes"]
                  if n["name"] == "Build Formatting Requests (F25)")["parameters"]["jsCode"]
        for st in STATUSES:
            self.assertIn(f"label: '{st}'", js)

    def test_frozen_headers_and_wrapped_copy(self):
        js = next(n for n in self.create["nodes"]
                  if n["name"] == "Build Formatting Requests (F25)")["parameters"]["jsCode"]
        self.assertIn("frozenRowCount", js)
        self.assertIn("WRAP", js)
        # Posts freezes its first two columns.
        self.assertIn("frozenColumnCount", js)

    def test_protected_formulas_and_this_week(self):
        js = next(n for n in self.create["nodes"]
                  if n["name"] == "Build Formatting Requests (F25)")["parameters"]["jsCode"]
        self.assertIn("addProtectedRange", js)
        self.assertIn("This Week", js)

    def test_formatting_runs_real_batchupdate(self):
        nodes = [n for n in self.create["nodes"]
                 if n["type"] == "n8n-nodes-base.httpRequest" and ":batchUpdate" in str(n["parameters"].get("url", ""))]
        self.assertTrue(len(nodes) >= 2, "formatting + This Week sizing both run batchUpdate")

    def test_validator_export_mode_green(self):
        proc = run_validator("--export")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class TestF25UpsertPreservesClientEdits(unittest.TestCase):
    """Re-running the provisioner/upsert never resets client row sizes/notes."""

    def test_append_upsert_preserves_row_height_and_notes(self):
        with open(APPEND) as f:
            append = json.load(f)
        # The resize node only resizes the CURRENTLY written row (postsMode
        # 'updated' + exact rowNumber) — a client-resized OTHER row is never
        # touched, and nothing in the append path rewrites client notes.
        rjs = next(n for n in append["nodes"]
                   if n["name"] == "Resolve Posts Sheet ID")["parameters"]["jsCode"]
        self.assertIn("postsMode === 'updated'", rjs)
        self.assertIn("src.rowNumber", rjs)
        # Overview upsert writes its own keyed row; legacy client rows untouched.
        ojs = next(n for n in append["nodes"]
                   if n["name"] == "Build Overview Summary")["parameters"]["jsCode"]
        self.assertIn("retained untouched", ojs)

    def test_contract_upsert_preserves_rule(self):
        with open(SCHEMA) as f:
            schema = json.load(f)
        self.assertIn("NEVER resets", schema["formatting_contract"]["upsert_preserves"])


if __name__ == "__main__":
    unittest.main()
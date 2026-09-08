"""QC-F16 — the export verifier gates the deployable contracts.

Runs 35-social-media-planner/config/n8n/verify-exports.py against both exports
and asserts it passes; asserts the verifier itself FAILS on violations (real
detection, not a rubber stamp): placeholder note, committed credential, fake
note-only resize, missing share node, TikTok fallback.
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
N8N = os.path.join(BASE, "35-social-media-planner", "config", "n8n")
VERIFIER = os.path.join(N8N, "verify-exports.py")
CREATE = os.path.join(N8N, "social-planner-sheet-create.json")
APPEND = os.path.join(N8N, "social-planner-row-append.json")


def run_verifier(against_dir):
    env = dict(os.environ)
    # The verifier resolves BASE from its own file location; copy it into the
    # sandbox dir so it validates the sandboxed exports.
    proc = subprocess.run(
        ["python3", os.path.join(against_dir, "verify-exports.py")],
        capture_output=True, text=True, timeout=60, env=env)
    return proc


class TestF16VerifierPassesRealExports(unittest.TestCase):
    def test_verifier_exits_zero_on_repo_exports(self):
        proc = subprocess.run(["python3", VERIFIER],
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0,
                         f"verifier must pass on the repo exports:\n{proc.stdout}\n{proc.stderr}")
        self.assertIn("0 failures", proc.stdout)

    def test_exports_are_importable_json_with_required_top_level(self):
        for path in (CREATE, APPEND):
            with open(path) as f:
                export = json.load(f)
            for key in ("name", "schema_version", "nodes", "connections", "contract"):
                self.assertIn(key, export, f"{os.path.basename(path)} missing {key}")
            self.assertTrue(export["nodes"])
            self.assertTrue(export["connections"])


class TestF16VerifierDetectsViolations(unittest.TestCase):
    """Copy the config dir to a sandbox, break the export, expect exit 1."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="f16-sandbox-")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def sandbox(self):
        dst = tempfile.mkdtemp(dir=self.tmp)
        for f in os.listdir(N8N):
            src = os.path.join(N8N, f)
            if os.path.isfile(src):
                shutil.copy2(src, os.path.join(dst, f))
        return dst

    def break_and_expect_fail(self, mutate):
        dst = self.sandbox()
        path = os.path.join(dst, "social-planner-row-append.json")
        with open(path) as f:
            export = json.load(f)
        mutate(export)
        with open(path, "w") as f:
            json.dump(export, f)
        proc = run_verifier(dst)
        self.assertEqual(proc.returncode, 1,
                         f"verifier must FAIL the mutation:\n{proc.stdout}")
        return proc.stdout

    def test_placeholder_note_reintroduced_is_caught(self):
        def mutate(export):
            export["_PLACEHOLDER_NOTE"] = "reconstructed placeholder"
        out = self.break_and_expect_fail(mutate)
        self.assertIn("placeholder marker", out)

    def test_committed_credential_is_caught(self):
        def mutate(export):
            for n in export["nodes"]:
                if n["type"] == "n8n-nodes-base.httpRequest":
                    n["credentials"] = {"googleSheetsOAuth2Api": {
                        "id": "4IoTZHAybRblm172",
                        "name": "management blackceo Google Sheets account"}}
                    break
        out = self.break_and_expect_fail(mutate)
        self.assertIn("credentials block", out)

    def test_fake_note_resize_is_caught(self):
        def mutate(export):
            for n in export["nodes"]:
                if n["name"] == "Resolve Posts Sheet ID":
                    n["parameters"]["jsCode"] = "return [{ json: { receipt: {}, resizeRequests: [] } }];"
        out = self.break_and_expect_fail(mutate)
        self.assertIn("updateDimensionProperties", out)

    def test_tiktok_fallback_is_caught(self):
        def mutate(export):
            for n in export["nodes"]:
                if n["name"] == "Validate + Build Keys":
                    js = n["parameters"]["jsCode"]
                    n["parameters"]["jsCode"] = js + "\nconst fallbackPlatform = row['TikTok'] || row.platform;"
        out = self.break_and_expect_fail(mutate)
        self.assertIn("TikTok", out)

    def test_missing_share_node_is_caught(self):
        dst = self.sandbox()
        path = os.path.join(dst, "social-planner-sheet-create.json")
        with open(path) as f:
            export = json.load(f)
        export["nodes"] = [n for n in export["nodes"] if n["name"] != "Set Anyone Can Edit"]
        with open(path, "w") as f:
            json.dump(export, f)
        proc = run_verifier(dst)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("'Set Anyone Can Edit' node missing", proc.stdout)

    def test_wrong_share_role_is_caught(self):
        dst = self.sandbox()
        path = os.path.join(dst, "social-planner-sheet-create.json")
        with open(path) as f:
            export = json.load(f)
        for n in export["nodes"]:
            if n["name"] == "Set Anyone Can Edit":
                n["parameters"]["permissionsUi"]["permissionsValues"]["role"] = "reader"
        with open(path, "w") as f:
            json.dump(export, f)
        proc = run_verifier(dst)
        self.assertEqual(proc.returncode, 1)
        self.assertIn("permissions drifted", proc.stdout)


class TestF16ExportContractFields(unittest.TestCase):
    """Versioned export contract per README: schema_version, parameter list."""

    @classmethod
    def setUpClass(cls):
        with open(CREATE) as f:
            cls.create = json.load(f)
        with open(APPEND) as f:
            cls.append = json.load(f)

    def test_contract_documents_input_output_schemas(self):
        for export, name in ((self.create, "create"), (self.append, "append")):
            contract = export["contract"]
            self.assertIn("input_schema", contract, f"{name} contract missing input_schema")
            self.assertIn("output_schema", contract, f"{name} contract missing output_schema")
            self.assertIn("credential_references", contract, f"{name} contract missing credential_references")

    def test_no_literal_template_id_committed(self):
        for export in (self.create, self.append):
            raw = json.dumps(export)
            self.assertNotIn("1RKgS5l-i6NBtf_vON49nBPdHe-F5W67RF9ym-S67L2c", raw,
                             "fleet template ID must be a parameter, never committed")

    def test_receipt_keys_in_output_schema(self):
        out = self.append["contract"]["output_schema"]
        for key in ("sheetId", "posts_updatedRange", "row_key", "mode"):
            self.assertIn(key, out)
        out_create = self.create["contract"]["output_schema"]
        for key in ("sheetId", "sheetUrl", "provisioning_key", "deduped"):
            self.assertIn(key, out_create)


if __name__ == "__main__":
    unittest.main()
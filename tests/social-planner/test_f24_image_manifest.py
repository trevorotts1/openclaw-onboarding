"""QC-F24 — asset manifest + trusted IMAGE formulas in the row-append export.

The manifest is persisted (upserted on asset_key); =IMAGE("https://…",1)
formulas are generated ONLY for validated URLs and land ONLY in the Images
tab's designated preview column (RAW everywhere else — F26 rule); invalid URLs
refuse into a visible repair state; sizing requests carry the 220px preview
column + row sizing per the SPEC build contract.
"""
import json
import os
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
N8N = os.path.join(BASE, "35-social-media-planner", "config", "n8n")
APPEND = os.path.join(N8N, "social-planner-row-append.json")

RUNNER = r"""
// Executes the Build Asset Manifest (F24) code node with a webhook body.
const fs = require('fs');
const [exportPath, stateJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === 'Build Asset Manifest (F24)').parameters.jsCode;
const state = JSON.parse(stateJson);  // {body, receipt}
const $input = { first: () => ({ json: state }) };
const $ = (name) => ({ first: () => ({ json: name.includes('Receipt') ? { json: state.receipt } : state }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""

RESIZE_RUNNER = r"""
// Executes the Resolve Posts Sheet ID code node with a metadata readback.
const fs = require('fs');
const [exportPath, stateJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === 'Resolve Posts Sheet ID').parameters.jsCode;
const state = JSON.parse(stateJson);
globalThis.__prior = state.prior || {};
globalThis.__input = { sheets: state.sheets || [] };
const $input = { first: () => ({ json: globalThis.__input }) };
const $ = (name) => ({ first: () => ({ json: globalThis.__prior[name] || {} }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""

CDN = "https://assets.cdn.filesafe.space/loc-abc/media/img-1.png"


def load_export():
    with open(APPEND) as f:
        return json.load(f)


def run_manifest(body, receipt):
    tmp = tempfile.mkdtemp(prefix="f24-")
    runner = os.path.join(tmp, "runner.js")
    with open(runner, "w") as f:
        f.write(RUNNER)
    state = {"body": body, "receipt": receipt}
    proc = subprocess.run(["node", runner, APPEND, json.dumps(state)],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip().splitlines()[-1])


def base_body(**kw):
    body = {"sheetId": "sh-1", "schema_version": "1.1.0", "company_id": "co-1",
            "cycle_id": "2026-W37", "content_revision": "r1", "account_id": "ig-1",
            "platform": "instagram", "account_name": "Acme IG", "format": "image",
            "scheduled_local": "2026-09-08 09:00", "scheduled_utc": "2026-09-08T13:00Z",
            "state": "scheduled", "qc_state": "approved",
            "preview_url": "https://assets.cdn.filesafe.space/loc-abc/media/img-1.png"}
    body.update(kw)
    return body


RECEIPT = {"success": True, "sheetId": "sh-1", "posts_updatedRange": "Posts!A2:N2",
           "overview_updatedRange": "Weekly Overview!A2:U2", "row_key": "k",
           "overview_key": "OV::k", "mode": "appended", "schema_version": "1.1.0"}


class TestF24AssetManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = load_export()

    def manifest_body(self, **asset):
        asset_def = {"content_id": "2026-W37::r1", "asset_id": "a-1", "kind": "image",
                     "preview_url": CDN, "original_url": CDN,
                     "ratio": "4:5", "width": 1080, "height": 1350,
                     "alt_text": "Acme product flat lay"}
        asset_def.update(asset)
        return base_body(asset=asset_def)

    def test_manifest_persisted_with_fields(self):
        out = run_manifest(self.manifest_body(), RECEIPT)
        m = out["assetManifest"]
        self.assertIsNotNone(m)
        header = m["header"]
        for field in ("asset_key", "content_id", "asset_id", "company_id", "ratio",
                      "width", "height", "alt_text", "qc_state", "preview_url",
                      "original_url"):
            self.assertIn(field, header)
        values = dict(zip(header, m["values"]))
        self.assertEqual(values["content_id"], "2026-W37::r1")
        self.assertEqual(values["ratio"], "4:5")
        self.assertEqual(values["alt_text"], "Acme product flat lay")
        self.assertEqual(values["width"], "1080")
        self.assertTrue(values["asset_key"].startswith("ASSET::"))

    def test_trusted_formula_only_for_validated_urls(self):
        out = run_manifest(self.manifest_body(), RECEIPT)
        self.assertEqual(out["imagesFormula"], f'=IMAGE("{CDN}", 1)')

    def test_formula_cells_only_in_designated_column(self):
        # The formula write targets ONLY the Images preview column P; all other
        # manifest writes are RAW (valueInputOption=RAW).
        raw = json.dumps(self.export)
        formula_nodes = [n for n in self.export["nodes"]
                         if n["name"] == "Write Trusted IMAGE Formula (F24)"]
        self.assertEqual(len(formula_nodes), 1)
        node = formula_nodes[0]
        self.assertIn("Images!P", node["parameters"]["url"])
        self.assertIn("USER_ENTERED", node["parameters"]["url"])
        # Everything else writing to the Images tab uses RAW.
        for n in self.export["nodes"]:
            url = str(n["parameters"].get("url", ""))
            if "values/Images" in url.lower() and "P" not in url.split("/values/")[-1].split("?")[0][:1]:
                if "Update Asset" in n["name"] or "Append Asset" in n["name"]:
                    self.assertIn("valueInputOption=RAW", url, n["name"])

    def test_invalid_url_refused_into_repair_state(self):
        cases = {
            "http://assets.example.com/x.png": "asset_url_not_https",
            'https://assets.cdn.filesafe.space/a"b.png': "asset_url_unsafe_chars",
            "https://drive.google.com/file/d/1abc/view": "asset_url_not_fetchable",
            "": "asset_missing_url",
        }
        for url, state in cases.items():
            # The asset URL is the one under test; the body-level fallback is
            # neutralized by not setting preview_url on the body.
            body = self.manifest_body()
            body.pop("preview_url", None)
            body["asset"]["preview_url"] = url
            out = run_manifest(body, RECEIPT)
            self.assertIsNotNone(out["assetRepair"], url)
            self.assertEqual(out["assetRepair"]["repair_state"], state)
            self.assertTrue(out["assetRepair"]["repair_required"])
            self.assertIsNone(out["assetManifest"], "nothing is written for an invalid URL")
            self.assertIsNone(out["imagesFormula"])

    def test_raw_urls_never_become_formulas(self):
        # The manifest row values carry the URL as a RAW value; the formula is a
        # separate Images-tab cell (P), never in the Posts values.
        out = run_manifest(self.manifest_body(), RECEIPT)
        header = out["assetManifest"]["header"]
        values = out["assetManifest"]["values"]
        self.assertEqual(values[header.index("preview_url")], CDN)
        self.assertNotIn("=IMAGE", json.dumps(values))

    def test_sizing_requests_present_in_export(self):
        rjs = next(n for n in self.export["nodes"]
                   if n["name"] == "Resolve Posts Sheet ID")["parameters"]["jsCode"]
        self.assertIn("updateDimensionProperties", rjs)
        self.assertIn("220", rjs)  # Images preview column 220px per SPEC
        self.assertIn("275", rjs)  # 4:5 row height per SPEC gallery contract
        self.assertIn("'Images'", rjs)
        # The resize runs as a real batchUpdate call.
        resize = next(n for n in self.export["nodes"]
                      if n["name"] == "Resize Columns + Row (batchUpdate)")
        self.assertIn(":batchUpdate", resize["parameters"]["url"])

    def test_asset_upsert_never_duplicates(self):
        # The manifest readback targets column A (asset_key) and upserts the
        # exact row when present.
        self.assertIn("values/Images!A2:A",
                      json.dumps([n["parameters"].get("url") for n in self.export["nodes"]]))
        fjs = next(n for n in self.export["nodes"]
                   if n["name"] == "Find Asset Row (F24)")["parameters"]["jsCode"]
        self.assertIn("rowNumber", fjs)
        self.assertIn("+ 2", fjs)


if __name__ == "__main__":
    unittest.main()
"""QC-F23 — normalized Posts schema in the row-append export.

Two accounts on one platform + X + Google Business Profile + an unfamiliar
platform label each get distinct keyed rows; the mapping contains NO
generic->TikTok fallback; Weekly Overview stays a summary derived from Posts
rows with legacy rows retained and an explicit overview key; schema is
versioned.
"""
import json
import os
import re
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
N8N = os.path.join(BASE, "35-social-media-planner", "config", "n8n")
APPEND = os.path.join(N8N, "social-planner-row-append.json")
CREATE = os.path.join(N8N, "social-planner-sheet-create.json")
README = os.path.join(N8N, "README.md")
INSTALL = os.path.join(BASE, "35-social-media-planner", "INSTALL.md")

SCHEMA_VERSION = "1.1.0"
POSTS_HEADER = ["row_key", "company_id", "cycle_id", "content_revision", "account_id",
                "platform", "account_name", "format", "scheduled_local", "scheduled_utc",
                "state", "qc_state", "preview_url", "remote_url"]

RUNNER = r"""
// Executes the exported Validate + Build Keys code with a fake webhook body and
// returns the built rowKey + postsValues so the test can assert keyed rows.
const fs = require('fs');
const [exportPath, bodyJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === 'Validate + Build Keys').parameters.jsCode;
const $input = { first: () => ({ json: { body: JSON.parse(bodyJson) } }) };
const $ = () => ({ first: () => ({ json: {} }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""

OVERVIEW_RUNNER = r"""
// Executes the exported Build Overview Summary code against a Posts readback.
const fs = require('fs');
const [exportPath, stateJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === 'Build Overview Summary').parameters.jsCode;
const state = JSON.parse(stateJson);  // {values: ovRows, prior...}
globalThis.__input = state.input || {};
for (const [k, v] of Object.entries(state.prior || {})) globalThis['__node_' + k] = v;
const $input = { first: () => ({ json: globalThis.__input }) };
const $ = (name) => ({ first: () => ({ json: globalThis['__node_' + name] || {} }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""


def load_export():
    with open(APPEND) as f:
        return json.load(f)


class TestF23PostsSchemaStatic(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.export = load_export()

    def test_schema_versioned(self):
        self.assertEqual(self.export["schema_version"], SCHEMA_VERSION)
        contract = self.export["contract"]
        self.assertEqual(contract["schema_version"], SCHEMA_VERSION)
        self.assertEqual(contract["posts_schema"], POSTS_HEADER)

    def test_posts_row_key_definition(self):
        self.assertEqual(self.export["contract"]["posts_row_key"],
                         "cycle_id::content_revision::account_id (upsert, never duplicate-append)")

    def test_no_generic_to_tiktok_fallback_in_mapping(self):
        for n in self.export["nodes"]:
            if n["type"] == "n8n-nodes-base.code":
                js = n["parameters"]["jsCode"]
                self.assertNotRegex(js, r"row\['TikTok'\]\s*\|\|",
                                    "mapping must not fall back into the TikTok column")
                self.assertNotRegex(js, r"row\.tiktok\s*\|\|",
                                    "mapping must not fall back into the TikTok column")
                self.assertNotRegex(js, r"row\.platform\s*\|\|[^=]*['\"]TikTok['\"]",
                                    "generic platform value must never land in TikTok")
        self.assertNotIn("'TikTok'] ||", json.dumps(
            [n["parameters"].get("jsCode", "") for n in self.export["nodes"]]))

    def test_overview_is_summary_not_source_of_truth(self):
        contract = self.export["contract"]["overview_summary"]
        self.assertIn("summary", contract.lower())
        self.assertIn("retained", contract.lower())

    def test_live_build_row_fallback_not_carried_into_export(self):
        # The LIVE workflow's Build Row Values had `row['TikTok'] || row.tiktok || row.platform`.
        # The export is the deployable contract: none of its code may contain that chain.
        for n in self.export["nodes"]:
            if n["type"] == "n8n-nodes-base.code":
                self.assertNotIn("row.platform ||", n["parameters"].get("jsCode", ""))

    def test_readme_documents_posts_columns(self):
        with open(README) as f:
            readme = f.read()
        for col in POSTS_HEADER:
            self.assertIn(f"`{col}`", readme, f"README Posts table missing {col}")
        self.assertIn("no generic", readme.lower())
        self.assertIn("schema_version", readme)

    def test_install_documents_posts_contract(self):
        with open(INSTALL) as f:
            install = f.read()
        self.assertIn("4f-bis", install)
        self.assertIn("row_key", install)
        self.assertIn("no generic-platform fallback", install)


class TestF23KeyedRowsSimulation(unittest.TestCase):
    """Runs the exported mapping JS per destination account via node."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="f23-")
        cls.runner = os.path.join(cls.tmp, "runner.js")
        with open(cls.runner, "w") as f:
            f.write(RUNNER)
        cls.ov_runner = os.path.join(cls.tmp, "ov_runner.js")
        with open(cls.ov_runner, "w") as f:
            f.write(OVERVIEW_RUNNER)

    def map_row(self, body):
        proc = subprocess.run(
            ["node", self.runner, APPEND, json.dumps(body)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def base_body(self, **kw):
        body = {"sheetId": "sh-1", "schema_version": SCHEMA_VERSION,
                "company_id": "co-1", "cycle_id": "2026-W37",
                "content_revision": "r1", "account_id": "acc-x",
                "platform": "facebook", "account_name": "Acme FB",
                "format": "image", "scheduled_local": "2026-09-08 09:00",
                "scheduled_utc": "2026-09-08T13:00Z", "state": "scheduled",
                "qc_state": "approved"}
        body.update(kw)
        return body

    def test_two_accounts_same_platform_get_distinct_keyed_rows(self):
        a = self.map_row(self.base_body(account_id="fb-1", account_name="Acme Main FB"))
        b = self.map_row(self.base_body(account_id="fb-2", account_name="Acme Secondary FB"))
        self.assertNotEqual(a["rowKey"], b["rowKey"])
        self.assertEqual(a["postsValues"][5], "facebook")   # F platform, verbatim
        self.assertEqual(b["postsValues"][5], "facebook")
        self.assertEqual(a["postsValues"][6], "Acme Main FB")
        self.assertEqual(b["postsValues"][6], "Acme Secondary FB")
        self.assertEqual(a["postsValues"][0], a["rowKey"])  # A row_key

    def test_x_and_gbp_and_unfamiliar_labels_get_own_rows(self):
        x = self.map_row(self.base_body(account_id="x-1", platform="X",
                                        account_name="Acme X", format="text"))
        gbp = self.map_row(self.base_body(account_id="gbp-1", platform="Google Business Profile",
                                          account_name="Acme GBP", format="update"))
        weird = self.map_row(self.base_body(account_id="w-1", platform="Threads-Longform",
                                            account_name="Acme Alt", format="text"))
        keys = {x["rowKey"], gbp["rowKey"], weird["rowKey"]}
        self.assertEqual(len(keys), 3, "every destination gets its own keyed row")
        self.assertEqual(x["postsValues"][5], "X")
        self.assertEqual(gbp["postsValues"][5], "Google Business Profile")
        self.assertEqual(weird["postsValues"][5], "Threads-Longform")
        # No TikTok redirection anywhere: the platform column carries the input verbatim.
        for values in (x["postsValues"], gbp["postsValues"], weird["postsValues"]):
            self.assertNotEqual(values[5], "TikTok")

    def test_generic_platform_string_never_becomes_tiktok(self):
        generic = self.map_row(self.base_body(account_id="g-1", platform="newsletter_cross",
                                              account_name="Cross-post", format="text"))
        self.assertEqual(generic["postsValues"][5], "newsletter_cross",
                         "generic platform string must pass through verbatim")

    def test_new_revision_of_same_account_is_its_own_row(self):
        r1 = self.map_row(self.base_body(account_id="fb-1", content_revision="r1"))
        r2 = self.map_row(self.base_body(account_id="fb-1", content_revision="r2"))
        self.assertNotEqual(r1["rowKey"], r2["rowKey"])
        self.assertEqual(r1["rowKey"], "2026-W37::r1::fb-1")
        self.assertEqual(r2["rowKey"], "2026-W37::r2::fb-1")

    def test_posts_header_exported_for_tab_creation(self):
        result = self.map_row(self.base_body(account_id="fb-1"))
        self.assertEqual(result["postsHeader"], POSTS_HEADER)


class TestF23OverviewSummaryDerivation(unittest.TestCase):
    """Weekly Overview rows derive from Posts rows; legacy rows retained."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="f23-ov-")
        cls.runner = os.path.join(cls.tmp, "ov_runner.js")
        with open(cls.runner, "w") as f:
            f.write(OVERVIEW_RUNNER)

    def build_overview(self, posts_rows, ov_rows, body):
        state = {
            "input": {"values": ov_rows},
            "prior": {
                "Find Posts Row": {
                    "allRows": posts_rows,
                    "postsValues": posts_rows[0] if posts_rows else [],
                    "sheetId": "sh-1",
                    "body": body,
                },
                "Normalize Posts Write": {
                    "postsUpdatedRange": "Posts!A1:N1",
                    "postsMode": "appended",
                },
            },
        }
        proc = subprocess.run(
            ["node", self.runner, APPEND, json.dumps(state)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def body(self, **kw):
        base = {"sheetId": "sh-1", "company_id": "co-1", "cycle_id": "2026-W37",
                "content_revision": "r1", "account_id": "x-1", "platform": "X",
                "account_name": "Acme X", "format": "text",
                "scheduled_local": "2026-09-08 09:00", "scheduled_utc": "2026-09-08T13:00Z",
                "state": "scheduled", "qc_state": "approved", "theme": "Launch week"}
        base.update(kw)
        return base

    def test_x_only_cycle_leaves_tiktok_column_empty(self):
        posts_row = ["2026-W37::r1::x-1", "co-1", "2026-W37", "r1", "x-1",
                     "X", "Acme X", "text", "2026-09-08 09:00", "2026-09-08T13:00Z",
                     "scheduled", "approved", "", ""]
        result = self.build_overview([posts_row], [], self.body())
        values = result["ovValues"]
        self.assertEqual(values[10], "", "TikTok column must stay empty for an X-only cycle")

    def test_overview_row_has_technical_key_in_column_u(self):
        posts_row = ["2026-W37::r1::x-1", "co-1", "2026-W37", "r1", "x-1",
                     "X", "Acme X", "text", "2026-09-08 09:00", "2026-09-08T13:00Z",
                     "scheduled", "approved", "", ""]
        result = self.build_overview([posts_row], [], self.body())
        self.assertEqual(result["ovValues"][20], "OV::2026-W37::r1")
        self.assertFalse(result["ovExisting"])

    def test_legacy_overview_rows_retained_and_new_summary_upserts_own_key(self):
        legacy = ["2026-W30", "Old theme", "", "Old content", "", "",
                  "done", "", "", "", "", "", "", "", "", "", "", "2026-08-17", "published", "legacy note", ""]
        posts_row = ["2026-W37::r1::x-1", "co-1", "2026-W37", "r1", "x-1",
                     "X", "Acme X", "text", "2026-09-08 09:00", "2026-09-08T13:00Z",
                     "scheduled", "approved", "", ""]
        result = self.build_overview([posts_row], [legacy], self.body())
        self.assertFalse(result["ovExisting"],
                         "legacy row without the key must not be matched/overwritten")
        self.assertEqual(result["ovValues"][20], "OV::2026-W37::r1")
        # Legacy row is untouched: the upsert targets a NEW appended row.
        self.assertEqual(result["ovRowNumber"], None)

    def test_existing_summary_row_with_same_key_is_upserted_in_place(self):
        posts_row = ["2026-W37::r1::x-1", "co-1", "2026-W37", "r1", "x-1",
                     "X", "Acme X", "text", "2026-09-08 09:00", "2026-09-08T13:00Z",
                     "published", "approved", "", ""]
        existing_summary = ["2026-W37", "Launch week", "", "Launch", "", "",
                            "", "", "", "", "", "", "", "", "", "", "scheduled", "2026-09-08 09:00", "scheduled", "", "OV::2026-W37::r1"]
        result = self.build_overview([posts_row], [existing_summary], self.body(state="published"))
        self.assertTrue(result["ovExisting"])
        self.assertEqual(result["ovRowNumber"], 2, "upsert targets exactly the keyed row")


if __name__ == "__main__":
    unittest.main()
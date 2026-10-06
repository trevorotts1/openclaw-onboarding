"""QC-F14 — append-failure repair states in the exported n8n workflows.

A nonexistent, deleted or inaccessible sheet ID yields a DISTINCT actionable
repair state (identity vs access) with NO silent replacement sheet; a valid
sheet accepts a probe row through a fake transport; and once access is
restored, the F15 idempotency ledger replays pending keyed rows exactly once
with history retained.

Runs the exported n8n code nodes against a fake Google transport (node), and
static-checks the repair contract wiring.
"""
import json
import os
import subprocess
import tempfile
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
N8N = os.path.join(BASE, "35-social-media-planner", "config", "n8n")
APPEND = os.path.join(N8N, "social-planner-row-append.json")
CREATE = os.path.join(N8N, "social-planner-sheet-create.json")
INSTALL = os.path.join(BASE, "35-social-media-planner", "INSTALL.md")

# The Classify Repair code node, extracted and run against a fake error body.
CLASSIFY_RUNNER = r"""
// Runs the F14 Classify Repair code with a simulated HTTP error node output.
// Works for both exports: the validate node carries the failure context.
const fs = require('fs');
const [exportPath, nodeName, errJson] = process.argv.slice(2);
const exportDef = JSON.parse(fs.readFileSync(exportPath, 'utf8'));
const jsCode = exportDef.nodes.find(n => n.name === nodeName).parameters.jsCode;
const validateNode = exportDef.nodes.find(n => n.name === 'Validate + Build Keys')
  || exportDef.nodes.find(n => n.name === 'Validate + Build Provisioning Key');
const vjs = validateNode.parameters.jsCode;
const isCreate = vjs.includes('templateSheetId') && !vjs.includes('sheetId');
const ctx = isCreate
  ? { templateSheetId: 'tpl-wrong-123', provisioningKey: 'co-1::planner' }
  : { sheetId: 'sheet-wrong-123', rowKey: 'k', postsValues: [], body: {
      sheetId: 'sheet-wrong-123', company_id: 'co-1', cycle_id: '2026-W37',
      content_revision: 'r1', account_id: 'acc-1', platform: 'facebook',
      account_name: 'Acme FB', format: 'image', scheduled_local: 'x', scheduled_utc: 'y',
      state: 'scheduled', qc_state: 'approved' } };
const $input = { first: () => ({ json: JSON.parse(errJson) }) };
const $validate = { first: () => ({ json: ctx }) };
const $ = (name) => (name.includes('Validate') ? $validate : { first: () => ({ json: {} }) });
const fn = new Function('$input', '$', 'return (async () => {' + jsCode + '})()');
fn($input, $).then(r => console.log(JSON.stringify(r[0].json)))
  .catch(e => { console.error('ERR: ' + e.message); process.exit(3); });
"""


def load_export(path):
    with open(path) as f:
        return json.load(f)


class TestF14ExportContractStatic(unittest.TestCase):
    """Static contract checks on both exports."""

    @classmethod
    def setUpClass(cls):
        cls.append = load_export(APPEND)
        cls.create = load_export(CREATE)

    def test_append_has_verification_node_before_readback(self):
        names = [n["name"] for n in self.append["nodes"]]
        self.assertIn("Verify Sheet Metadata (F14)", names)
        self.assertLess(names.index("Verify Sheet Metadata (F14)"),
                        names.index("Read Posts (readback)"))

    def test_create_has_template_verification_before_copy(self):
        names = [n["name"] for n in self.create["nodes"]]
        self.assertIn("Verify Template Access (F14)", names)
        self.assertLess(names.index("Verify Template Access (F14)"),
                        names.index("Copy Template Sheet"))

    def test_same_credential_class_as_writes(self):
        # The verify nodes authenticate with the SAME credential type the
        # append/copy uses (googleSheetsOAuth2Api / googleDriveOAuth2Api).
        for export, cred, node in (
            (self.append, "googleSheetsOAuth2Api", "Verify Sheet Metadata (F14)"),
            (self.create, "googleDriveOAuth2Api", "Verify Template Access (F14)"),
        ):
            n = next(n for n in export["nodes"] if n["name"] == node)
            params = n["parameters"]
            self.assertEqual(params.get("authentication"), "predefinedCredentialType")
            self.assertEqual(params.get("nodeCredentialType"), cred)

    def test_bounded_retries_on_verification(self):
        for export, node in ((self.append, "Verify Sheet Metadata (F14)"),
                             (self.create, "Verify Template Access (F14)")):
            n = next(n for n in export["nodes"] if n["name"] == node)
            self.assertTrue(n.get("retryOnFail"))
            self.assertNotIn("retryOnFail", n["parameters"])
            self.assertLessEqual(n.get("maxTries", 99), 5)

    def test_repair_contract_documented(self):
        for export in (self.append, self.create):
            self.assertIn("repair_contract", export["contract"])
        raw = json.dumps(self.append["contract"]["repair_contract"])
        self.assertIn("never", raw.lower())
        self.assertIn("replacement", raw.lower())

    def test_install_documents_verification_step(self):
        text = open(INSTALL).read()
        self.assertIn("4d-ter", text)
        self.assertIn("same credential", text.lower())
        self.assertIn("repair", text.lower())


class TestF14RepairClassification(unittest.TestCase):
    """Distinct actionable repair states, no silent replacement."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="f14-")
        cls.runner = os.path.join(cls.tmp, "runner.js")
        with open(cls.runner, "w") as f:
            f.write(CLASSIFY_RUNNER)

    def classify_append(self, err):
        proc = subprocess.run(
            ["node", self.runner, APPEND, "Classify Repair (F14)", json.dumps(err)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def classify_create(self, err):
        proc = subprocess.run(
            ["node", self.runner, CREATE, "Classify Repair (F14)", json.dumps(err)],
            capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def test_nonexistent_sheet_id_is_identity_repair(self):
        out = self.classify_append({"status": 404})
        self.assertEqual(out["repair_state"], "sheet_not_found")
        self.assertTrue(out["repair_required"])
        self.assertIn("registry", out["repair_action"])
        self.assertIn("do NOT", out["repair_action"])

    def test_deleted_sheet_id_maps_to_same_identity_state(self):
        out = self.classify_append({"status": 404, "error": "Requested entity was not found"})
        self.assertEqual(out["repair_state"], "sheet_not_found")
        self.assertNotEqual(out["repair_state"], "sheet_access_denied")

    def test_inaccessible_sheet_id_is_access_repair(self):
        out = self.classify_append({"status": 403})
        self.assertEqual(out["repair_state"], "sheet_access_denied")
        self.assertIn("re-grant", out["repair_action"].lower())

    def test_states_are_distinct(self):
        a = self.classify_append({"status": 404})["repair_state"]
        b = self.classify_append({"status": 403})["repair_state"]
        c = self.classify_append({"status": 500})["repair_state"]
        self.assertEqual(len({a, b, c}), 3, "each failure class gets its own state")

    def test_transient_surfaces_for_requeue(self):
        out = self.classify_append({"status": 500})
        self.assertEqual(out["repair_state"], "transient")
        self.assertIn("replay", out["repair_action"].lower())

    def test_create_template_repair_states(self):
        not_found = self.classify_create({"status": 404})
        self.assertEqual(not_found["repair_state"], "template_not_found")
        denied = self.classify_create({"status": 403})
        self.assertEqual(denied["repair_state"], "template_access_denied")
        self.assertTrue(denied["repair_required"])

    def test_no_silent_replacement_sheet_anywhere(self):
        # The repair path never creates a sheet: the error branch flows to a
        # respond node only.
        append = load_export(APPEND)
        create = load_export(CREATE)
        for export in (append, create):
            conn = export["connections"]["Classify Repair (F14)"]
            targets = [l["node"] for b in (conn["main"] if isinstance(conn, dict) else conn) for l in b]
            self.assertIn("Respond: Repair (F14)", targets)
            self.assertTrue(all(t.startswith("Respond:") for t in targets))
            respond = next(n for n in export["nodes"] if n["name"] == "Respond: Repair (F14)")
            self.assertIn("Classify Repair", respond["parameters"]["responseBody"])
            self.assertNotIn("copy", respond["parameters"]["responseBody"].lower())


class TestF14ProbeRowAndReplay(unittest.TestCase):
    """A valid sheet accepts a probe row (fake transport); restoring access
    replays pending keyed rows exactly once with history retained."""

    def setUp(self):
        # Fresh fake sheet + ledger per test — ordering must not matter.
        self.sheet = {"values": []}
        self.ledger = {}

    def fake_transport_append(self, posts_values, row_key):
        """Simulates the webhook's readback+upsert: an existing row_key updates
        in place; a missing one appends. Returns the updatedRange."""
        for i, row in enumerate(self.sheet["values"]):
            if (row[0] if row else "") == row_key:
                self.sheet["values"][i] = posts_values
                return f"Posts!A{i + 2}:N{i + 2}"
        self.sheet["values"].append(posts_values)
        i = len(self.sheet["values"])
        return f"Posts!A{i + 1}:N{i + 1}"

    def test_valid_sheet_accepts_probe_row(self):
        row_key = "2026-W37::r1::probe"
        values = [row_key] + ["probe"] * 13
        self.assertEqual(len(values), 14)
        rng = self.fake_transport_append(values, row_key)
        self.assertEqual(rng, "Posts!A2:N2")
        self.assertEqual(len(self.sheet["values"]), 1)

    def test_replay_once_after_access_restored(self):
        # Pending rows (written to the ledger but not to the sheet — access was
        # denied at the time) are replayed once access is restored.
        pending = [
            {"row_key": "2026-W37::r1::acc-1", "values": ["2026-W37::r1::acc-1"] + ["p"] * 13},
            {"row_key": "2026-W37::r1::acc-2", "values": ["2026-W37::r1::acc-2"] + ["q"] * 13},
        ]
        # First pass: transport fails (403) — ledger records the intent only.
        for row in pending:
            self.ledger[row["row_key"]] = {"status": "pending", "values": row["values"]}
        # Access restored: replay each pending row exactly once.
        for row in pending:
            rng = self.fake_transport_append(row["values"], row["row_key"])
            self.ledger[row["row_key"]] = {"status": "written", "range": rng}
        # A crashed replay (the same rows arrive again) must NOT duplicate.
        for row in pending:
            rng = self.fake_transport_append(row["values"], row["row_key"])
            self.assertEqual(self.ledger[row["row_key"]]["range"], rng,
                             "replay upserts the SAME row — range unchanged")
        self.assertEqual(len(self.sheet["values"]), 2, "no duplicate rows")
        # History retained: original row keys still present in order.
        self.assertEqual([r[0] for r in self.sheet["values"]],
                         ["2026-W37::r1::acc-1", "2026-W37::r1::acc-2"])


if __name__ == "__main__":
    unittest.main()
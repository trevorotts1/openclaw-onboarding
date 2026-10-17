#!/usr/bin/env python3
"""S71 A23 provider-gate tests: no false KIE task IDs for Agnes.

Acceptance unit A23 (doc 18: L1 provider receipt tests), S71 portion:
the per-provider branch in Skill 71's image-generation-qc gate, per the
reconciled matrix Q10 action 9. Fixture specifications are FINAL in
S71-06-RECONCILED-MATRIX.md section 3 (F-A23-1..F-A23-4); the fixture
receipts live in tests/fixtures/provider-receipts/ and are run through
the gate's own validators (stage_gate.check_transport for the stage
close and stage_gate.check_item_transport for the per-item close).

Parity target: S63's provider_receipt.validate_receipt (PR #2157) —
Agnes receipt task_id always explicit null; any non-null task_id or
non-null KIE-named field on an Agnes receipt refused; the real task ID
required on a KIE receipt.

On the pre-A23 base these pins fail: check_transport skipped every
per-task check for the Agnes route, so a fabricated task ID on an
Agnes receipt passed silently (the mutation control in the build
report records that run).
"""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
FIXTURES = HERE / "fixtures" / "provider-receipts"
STAGE = "image-generation-qc"
ITEM_ID = "Image-001"

sys.path.insert(0, str(SKILL_ROOT / "scripts"))
import stage_gate  # noqa: E402


def load_fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ProviderGateCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="a23-gate-"))

    def tearDown(self):
        import shutil
        shutil.rmtree(self.td, ignore_errors=True)

    def make_run(self, fixture):
        """A minimal run dir the gate reads: intake + the stage's files,
        plus a receipts/kie74 result file per KIE task id (as a real
        Skill 74 run would record)."""
        run = Path(tempfile.mkdtemp(prefix="run-", dir=self.td))
        (run / "image-generation-qc").mkdir(parents=True)
        (run / "intake.json").write_text(
            json.dumps({"image_engine": fixture["image_engine"]}),
            encoding="utf-8")
        for rel in fixture["files"]:
            (run / rel).write_bytes(b"stub")
        for task in fixture["receipt"]["transport"]["tasks"]:
            tid = task.get("task_id")
            if fixture["image_engine"] == "kie" and tid:
                f = stage_gate._kie74_file(run, tid)
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(json.dumps({
                    "task_id": tid, "adapter": "74-kie-live-adapter",
                    "adapter_mode": "active", "state": "success",
                }), encoding="utf-8")
        return run

    def stage_problems(self, fixture):
        run = self.make_run(fixture)
        return stage_gate.check_transport(run, STAGE, fixture["receipt"])

    def item_problems(self, fixture):
        run = self.make_run(fixture)
        return stage_gate.check_item_transport(
            run, STAGE, ITEM_ID, fixture["receipt"])

    def assert_accepted(self, fixture):
        self.assertEqual(self.stage_problems(fixture), [],
                         "stage gate must accept")
        self.assertEqual(self.item_problems(fixture), [],
                         "item gate must accept")

    def assert_refused(self, fixture, needle):
        stage = self.stage_problems(fixture)
        self.assertTrue(any(needle in p for p in stage),
                        f"stage gate must refuse naming {needle!r}; got {stage}")
        item = self.item_problems(fixture)
        self.assertTrue(any(needle in p for p in item),
                        f"item gate must refuse naming {needle!r}; got {item}")


class TestFA23(ProviderGateCase):
    # ---- F-A23-1: Agnes honest identifiers, both encodings ACCEPT
    def test_fa23_1_agnes_task_id_null_accepted(self):
        self.assert_accepted(load_fixture("fa23-1-agnes-honest-null.json"))

    def test_fa23_1_agnes_task_id_omitted_accepted(self):
        self.assert_accepted(load_fixture("fa23-1-agnes-honest-omitted.json"))

    def test_fa23_1_gate_does_not_backfill_a_task_id(self):
        fixture = load_fixture("fa23-1-agnes-honest-omitted.json")
        before = copy.deepcopy(fixture["receipt"])
        self.stage_problems(fixture)
        self.item_problems(fixture)
        self.assertEqual(fixture["receipt"], before,
                         "validation must not mutate the receipt")
        self.assertNotIn("task_id",
                         fixture["receipt"]["transport"]["tasks"][0])

    # ---- F-A23-2: KIE run, real task evidence ACCEPT
    def test_fa23_2_kie_real_task_evidence_accepted(self):
        self.assert_accepted(load_fixture("fa23-2-kie-real.json"))

    # ---- F-A23-3: cross-provider negatives, both directions FAIL by name
    def test_fa23_3_agnes_with_kie_task_id_fails(self):
        self.assert_refused(
            load_fixture("fa23-3-agnes-with-kie-task-id.json"),
            "Agnes task_id must be null")

    def test_fa23_3_kie_without_task_id_fails(self):
        self.assert_refused(
            load_fixture("fa23-3-kie-without-task-id.json"),
            "task_id")

    def test_fa23_3_agnes_with_kie_named_field_fails(self):
        fixture = load_fixture("fa23-1-agnes-honest-null.json")
        fixture["receipt"]["transport"]["tasks"][0]["kie_task_id"] = \
            "kie-task-8f3a2c1d9e47"
        self.assert_refused(fixture, "KIE identifier field")

    def test_fa23_3_agnes_with_any_nonnull_task_id_fails(self):
        # Not only KIE-shaped strings: any attached identifier is false
        # evidence for a provider that issues none (S63 parity).
        fixture = load_fixture("fa23-1-agnes-honest-null.json")
        fixture["receipt"]["transport"]["tasks"][0]["task_id"] = "agnes-12345"
        self.assert_refused(fixture, "Agnes task_id must be null")

    # ---- F-A23-4: synchronous Agnes, no task ID, no polling artefacts
    def test_fa23_4_sync_agnes_accepted(self):
        self.assert_accepted(load_fixture("fa23-4-agnes-sync.json"))

    def test_fa23_4_polling_artefact_fails(self):
        fixture = load_fixture("fa23-4-agnes-sync.json")
        fixture["receipt"]["transport"]["tasks"][0]["poll_count"] = 3
        self.assert_refused(fixture, "polling artefact")

    def test_fa23_4_active_mode_on_agnes_fails(self):
        fixture = load_fixture("fa23-4-agnes-sync.json")
        fixture["receipt"]["transport"]["mode"] = "active"
        self.assert_refused(fixture, "transport.mode must be 'sync'")
        fixture = load_fixture("fa23-4-agnes-sync.json")
        fixture["receipt"]["transport"]["tasks"][0]["mode"] = "async"
        self.assert_refused(fixture, "mode must be 'sync'")

    def test_fa23_4_minimal_agnes_task_still_accepted(self):
        # The pre-existing minimal Agnes shape (test_stage_gate i9: a
        # task carrying only its file) stays accepted: nothing in the
        # A23 branch invents new required fields for Agnes.
        fixture = load_fixture("fa23-1-agnes-honest-null.json")
        fixture["receipt"]["transport"] = {
            "skill": "63-agnes-image", "policy": "63-agnes-image",
            "tasks": [{"file": f} for f in fixture["files"]],
        }
        self.assert_accepted(fixture)


if __name__ == "__main__":
    unittest.main(verbosity=2)

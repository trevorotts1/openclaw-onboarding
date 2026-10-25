"""Read-only closure from actual decisions; a cache never creates an approval.

Uses the real intake, artifact handlers, Store, recap and Go writers. No
provider, actual media, client transport or source-run cache is produced.
"""
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(CORE), str(CORE / "intake_preflight")]
from intake_preflight import factory
import production_process as process
from test_factory_method_agnes import make_run
from test_production_process import write_json


def stamps(run):
    return {str(path.relative_to(run)): (path.stat().st_mtime_ns, path.read_bytes())
            for path in Path(run).rglob("*") if path.is_file()}


class CompletionApprovalProjection(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="completion-approval-projection-")
        self.addCleanup(self.tmp.cleanup)
        self.run = make_run(Path(self.tmp.name), None, agnes="no")
        # An empty typed array is explicit non-delivery, never an approval.
        write_json(self.run / "delivery" / "receipts.json", [])

    def inspect(self):
        before = stamps(self.run)
        result = process.inspect_completion_approvals(self.run)
        self.assertEqual(stamps(self.run), before)
        return result

    def test_current_modern_and_verifiable_legacy_decisions_need_no_aggregate_cache(self):
        cache = self.run / "control" / "approvals.json"
        self.assertFalse(cache.exists())
        modern = self.inspect()
        self.assertTrue(modern["ok"], modern)
        self.assertEqual(modern["authority"], "intake-session")
        self.assertEqual(modern["checks"]["creative-strategy"]["proof_kind"],
                         "internal-stage-and-current-script-package")
        ledger = self.run / "control" / "intake-session.json"
        ledger.rename(ledger.with_name("retained-client-ledger.json"))
        legacy = self.inspect()
        self.assertTrue(legacy["ok"], legacy)
        self.assertEqual(legacy["authority"], "legacy-artifact-decisions")
        self.assertFalse(cache.exists())

    def test_approved_cache_cannot_replace_missing_actual_script_decisions_or_history(self):
        cache = {s: {"state": "approved"} for s in factory.CANONICAL_STAGES}
        write_json(self.run / "control" / "approvals.json", cache)
        approval = self.run / "creative" / "script-approval.json"
        approval.rename(approval.with_name("retained-script-approval.json"))
        result = self.inspect()
        self.assertFalse(result["ok"], result)
        self.assertEqual(result["reason_code"], "PRODUCTION_SCRIPT_APPROVAL_MISSING")
        bare = Path(self.tmp.name) / "bare-cache"
        write_json(bare / "control" / "approvals.json", cache)
        self.assertFalse(process.inspect_completion_approvals(bare)["ok"])

    def test_changed_artifacts_pick_go_context_and_foreign_decisions_stay_refused(self):
        script = self.run / "creative" / "script.json"
        still = next((self.run / "storyboard").glob("s*.png"))
        pick = self.run / "song-choices" / "pick.json"
        go = self.run / "control" / "production-go.json"
        record = self.run / "creative" / "script-approval.json"
        cases = ((script, "script"), (still, "still"), (pick, "pick"), (go, "go"),
                 (record, "context"), (record, "foreign"))
        for path, kind in cases:
            with self.subTest(kind=kind):
                original = path.read_bytes()
                try:
                    if kind == "still":
                        path.write_bytes(original + b" changed")
                    else:
                        doc = json.loads(original)
                        if kind == "script":
                            doc["story"][0][1].append("A changed ending")
                        elif kind in ("pick", "go"):
                            doc["sha256" if kind == "pick" else "recap_digest"] = "0" * 64
                        else:
                            for event in doc["approvals"]:
                                if kind == "context":
                                    event.pop("source_ref", None)
                                else:
                                    event["run_id"] = "another-run"
                        write_json(path, doc)
                    refused = self.inspect()
                    self.assertFalse(refused["ok"], refused)
                finally:
                    path.write_bytes(original)

    def test_existing_cache_can_only_veto_verified_proofs(self):
        self.assertTrue(self.inspect()["ok"])
        cache_path = self.run / "control" / "approvals.json"
        for cache in ({"script-lyrics": {"state": "pending"}},
                      {"storyboard": {"state": "revoked"}}, [],
                      {"creative-strategy": {"state": "approved", "plan_revision": 1}}):
            with self.subTest(cache=cache):
                write_json(self.run / "control" / "plan-revision.json", {"revision": 2})
                write_json(cache_path, cache)
                self.assertFalse(self.inspect()["ok"])

    def test_legal_completion_history_is_required(self):
        import state_store
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            changed = store.con.execute("DELETE FROM events WHERE run_id=? AND stage=?",
                                        (self.run.name, "creative-strategy"))
            self.assertGreater(changed.rowcount, 0)
            store.con.commit()
        refused = self.inspect()
        self.assertFalse(refused["ok"])
        self.assertEqual(refused["reason_code"], "PRODUCTION_COMPLETION_HISTORY_UNVERIFIED")

    def test_final_qc_artifact_and_delivery_checks_remain_independent(self):
        import qc_gate
        from storyboard_director.test_registry_advancement import qc_record
        record = qc_record(self.run.name)
        record["stage"] = "final-qc"
        verdict = qc_gate.evaluate(self.run.name, "final-qc", [record],
                                   {record["check_id"]: "different-build-worker"}, ["continuity"])
        self.assertEqual(verdict["gate"], "PASS", verdict)
        write_json(self.run / "final-qc" / "record.json",
                   {"gate": verdict["gate"], "producer": factory.STAGE_REGISTRY["final-qc"]["qc_producer"],
                    "evaluation": verdict})
        states = {s: "COMPLETE" for s in factory.CANONICAL_STAGES}
        before = stamps(self.run)
        evidence = factory._collect_completion_evidence(self.run, states)
        self.assertTrue(evidence["approvals_current"], evidence["approval_projection"])
        self.assertTrue(evidence["final_qc_independent_pass"])
        self.assertFalse(evidence["delivery_receipts_ok"])
        self.assertEqual(stamps(self.run), before)
        for receipts in ([{"destination": "origin", "status": "failed"}],
                         [{"destination": "origin", "status": "delivered"}] * 2):
            write_json(self.run / "delivery" / "receipts.json", receipts)
            evidence = factory._collect_completion_evidence(self.run, states)
            self.assertTrue(evidence["approvals_current"])
            self.assertFalse(evidence["delivery_receipts_ok"])
            self.assertFalse(factory._decide_completion(evidence)[0])
        write_json(self.run / "final-qc" / "record.json", {"gate": "FAIL", "producer": "same-build-worker"})
        evidence = factory._collect_completion_evidence(self.run, states)
        self.assertFalse(evidence["final_qc_independent_pass"])
        artifact = self.run / "assembly" / "timeline.json"
        artifact.rename(artifact.with_name("retained-timeline.json"))
        evidence = factory._collect_completion_evidence(self.run, states)
        self.assertFalse(evidence["artifacts_present"])
        self.assertIn("assembly/timeline.json", evidence["missing_artifacts"])
        self.assertFalse(factory._decide_completion(evidence)[0])


if __name__ == "__main__":
    unittest.main()

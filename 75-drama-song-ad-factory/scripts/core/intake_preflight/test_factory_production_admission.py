"""Factory CLI production admission, using real intake/Store/approval protocols.

No provider, model, media or client-send calls. Dependency availability alone
is mocked for paid-stage dependency checks; client/stage authority is real.
"""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
from intake_preflight import factory
import state_store
from kie_dispatch import model_lock
from test_production_process import (confirmed_run, complete_stage, approve_script,
                                    write_json, run_hashes)


class FactoryProductionAdmission(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="factory-production-admission-")
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run"

    def cli(self, *args):
        out = io.StringIO()
        with redirect_stdout(out):
            code = factory.main(list(args))
        return code, json.loads(out.getvalue())

    def preflight(self, *extra):
        return self.cli("preflight", "--storage-dir", self.tmp.name, *extra)

    def paid_dependencies(self):
        return patch.object(factory._preflight, "check_requirement",
                            return_value={"ok": True, "detail": "offline dependency availability"})

    def ready_for_music(self, **preferences):
        confirmed_run(self.run, **preferences)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)
        return approve_script(self.run)

    def forged_store(self):
        (self.run / "control").mkdir(parents=True)
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.init_run(self.run.name, factory._stages())
        model_lock.lock_run_model(self.run / "control" / "state.sqlite3", self.run.name, "minimax-h3/*")
        write_json(self.run / "control" / "authorization.json",
                   {"scope": "campaign", "expires_unix": 9999999999})
        write_json(self.run / "control" / "card-receipt.json",
                   {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                                "length": 120, "video_model": "MiniMax H3"}, "who": "client", "at": 1})

    def test_diagnostics_do_not_need_intake_and_never_admit_production(self):
        code, result = self.preflight("--mode", "diagnostic")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["reason_code"], "preflight-pass-diagnostic")
        self.assertEqual(result["data"]["readiness"], "diagnostic-only")
        self.assertFalse(result["data"]["production_admitted"])
        self.assertFalse(self.run.exists())

    def test_confirmed_planning_and_first_research_need_no_future_approval_or_auth_file(self):
        rid = confirmed_run(self.run)
        code, result = self.preflight("--run-dir", str(self.run))
        self.assertEqual(code, 0, result)
        self.assertEqual(result["reason_code"], "preflight-pass-planning")
        self.assertEqual(result["run_id"], rid)
        self.assertEqual(result["data"]["readiness"], "planning-only")
        self.assertFalse(result["data"]["production_admitted"])
        code, result = self.preflight("--run-dir", str(self.run), "--stage", "research")
        self.assertEqual(code, 0, result)
        self.assertEqual(result["data"]["checks"]["production_process"]["stage"], "research")
        code, nxt = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, nxt)
        self.assertEqual(nxt["data"]["stage"], "research")
        self.assertTrue(nxt["data"]["production_admitted"])
        self.assertEqual(nxt["data"]["production_process"]["authority"], "intake-session")
        self.assertFalse((self.run / "control" / "authorization.json").exists())
        self.assertFalse((self.run / "creative" / "script-approval.json").exists())

    def test_preflight_names_actual_stage_and_explicit_run_id_not_a_generated_label(self):
        rid = confirmed_run(self.run)
        with self.paid_dependencies():
            code, wrong = self.preflight("--run-dir", str(self.run), "--stage", "research", "--run-id", "another-run")
            self.assertEqual(code, 2)
            self.assertFalse(wrong["data"]["production_admitted"])
            code, blocked = self.preflight("--run-dir", str(self.run), "--stage", "music")
        self.assertEqual(code, 2)
        self.assertEqual(blocked["reason_code"], "PRODUCTION_PREDECESSOR_INCOMPLETE")
        self.assertEqual(blocked["run_id"], rid)
        self.assertEqual(blocked["data"]["checks"]["production_process"]["predecessor"], "research")

    def test_forged_manual_store_and_json_never_reach_music_runner_or_next_command(self):
        self.forged_store()
        before = run_hashes(self.run)
        with patch.object(factory, "music_stage", side_effect=AssertionError("paid/lifecycle runner trap")) as trap:
            code, blocked = self.cli("music", "--run-dir", str(self.run), "--owner", "fixture-worker", "--action", "start")
        self.assertEqual(code, 2)
        self.assertEqual(blocked["reason_code"], "PRODUCTION_INTAKE_AUTHORITY_MISSING")
        trap.assert_not_called()
        code, nxt = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 2)
        self.assertIsNone(nxt["data"]["command"])
        code, event = self.cli("event", "--run-dir", str(self.run), "--event", "restart")
        self.assertEqual(code, 2)
        self.assertIsNone(event["data"]["command"])
        self.assertEqual(run_hashes(self.run), before)

    def test_continuation_queue_cannot_publish_an_unapproved_music_command(self):
        confirmed_run(self.run)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)
        code, blocked = self.cli("event", "--run-dir", str(self.run), "--event", "restart")
        self.assertEqual(code, 2)
        self.assertEqual(blocked["reason_code"], "PRODUCTION_SCRIPT_MISSING")
        self.assertIsNone(blocked["data"]["command"])
        queued = factory.drain_continuation(self.run)
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["verdict"], "waiting")
        self.assertIsNone(queued[0]["entrypoint"])
        self.assertFalse(queued[0]["production_admitted"])

    def test_real_whole_script_approval_allows_music_but_revised_artifact_stops_it(self):
        doc = self.ready_for_music()
        with self.paid_dependencies():
            code, admitted = self.preflight("--run-dir", str(self.run), "--stage", "music")
        self.assertEqual(code, 0, admitted)
        proof = admitted["data"]["checks"]["production_process"]["approved_script"]
        self.assertTrue(proof["script_sha256"])
        code, nxt = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, nxt)
        self.assertEqual(nxt["data"]["production_process"]["stage"], "music")
        doc["story"][0][1].append("A changed ending")
        write_json(self.run / "creative" / "script.json", doc)
        with patch.object(factory, "music_stage", side_effect=AssertionError("paid/lifecycle runner trap")) as trap:
            code, blocked = self.cli("music", "--run-dir", str(self.run), "--owner", "fixture-worker", "--action", "start")
        self.assertEqual(code, 2)
        trap.assert_not_called()
        self.assertEqual(blocked["reason_code"], "PRODUCTION_SCRIPT_APPROVAL_UNVERIFIED")

    def test_existing_music_wait_resume_is_cost_free_and_keeps_lease_checks(self):
        self.ready_for_music()
        code, started = self.cli("music", "--run-dir", str(self.run), "--owner", "fixture-worker", "--action", "start")
        self.assertEqual(code, 0, started)
        code, waiting = self.cli("music", "--run-dir", str(self.run), "--owner", "fixture-worker", "--action", "wait-provider")
        self.assertEqual(code, 0, waiting)
        code, resumed = self.cli("music", "--run-dir", str(self.run), "--owner", "fixture-worker", "--action", "start")
        self.assertEqual(code, 0, resumed)
        self.assertEqual(resumed["reason_code"], "music-resumed")
        self.assertFalse(resumed["data"]["production_admitted"])
        code, rejected = self.cli("music", "--run-dir", str(self.run), "--owner", "foreign-worker", "--action", "resume")
        self.assertEqual(code, 4, rejected)
        self.assertEqual(rejected["reason_code"], "NOT_OWNER")

    def test_supported_legacy_package_events_resume_without_reconstructing_old_answers(self):
        self.ready_for_music()
        ledger = self.run / "control" / "intake-session.json"
        ledger.rename(self.run / "control" / "retained-legacy-test-ledger.json")
        before = (self.run / "card-answers.json").read_bytes()
        code, nxt = self.cli("next", "--run-dir", str(self.run))
        self.assertEqual(code, 0, nxt)
        self.assertEqual(nxt["data"]["stage"], "music")
        self.assertEqual(nxt["data"]["production_process"]["authority"], "legacy-artifact-decisions")
        self.assertEqual((self.run / "card-answers.json").read_bytes(), before)
        self.assertFalse(ledger.exists())

    def test_storyboard_decision_is_required_after_keyframes_not_before_them(self):
        self.ready_for_music(song=False)
        for stage in ("music", "continuity-bible", "storyboard"):
            complete_stage(self.run, stage)
        with self.paid_dependencies():
            code, images = self.preflight("--run-dir", str(self.run), "--stage", "image-keyframes")
        self.assertEqual(code, 0, images)
        complete_stage(self.run, "image-keyframes")
        with self.paid_dependencies():
            code, video = self.preflight("--run-dir", str(self.run), "--stage", "video-generation")
        self.assertEqual(code, 2)
        self.assertFalse(video["data"]["production_admitted"])


if __name__ == "__main__":
    unittest.main()

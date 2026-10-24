"""Offline dispatch admission regressions: no real transport or paid work."""
from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CORE))
D = importlib.import_module("kie_dispatch.kie_dispatch")
import spend_ledger as ledger
from audio_c3 import lipsync_producer as producer
from lip_sync.lip_gate import picture_gate as picture

MODEL = "gpt-image-2-5-sunburst-text-to-image"
CARD = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                    "length": 120, "video_model": "MiniMax H3 768P"},
        "who": "owner", "at": "2026-10-24T00:00:00Z"}


class ProcessGateTest(unittest.TestCase):
    def setUp(self):
        # Keep pure cap measurements, but suppress their unrelated optional
        # local adapter audit. No subprocess/network path may run in this suite.
        audit = patch.object(D._PL, "_TRAIL_DONE", True)
        audit.start()
        self.addCleanup(audit.stop)
        self.temp = tempfile.TemporaryDirectory(prefix="s75-dispatch-process-")
        self.run = Path(self.temp.name) / "run"
        (self.run / "control").mkdir(parents=True)
        self.request = {"model": MODEL, "input": {"prompt": "p" * 200},
                        "run_dir": str(self.run), "card_receipt": copy.deepcopy(CARD)}
        self.kwargs = dict(model=MODEL, request=self.request,
                           save_dir=str(self.run / "images"),
                           ledger_db=str(self.run / "spend.sqlite3"),
                           run_id="run", logical_key="image/1", attempt_id="",
                           estimated_cost=10, prompt="p" * 200, stage="image-keyframes",
                           adapter_path=str(Path(__file__).resolve()))

    def tearDown(self):
        self.temp.cleanup()

    def assert_zero_spend_refusal(self, expected=None, **overrides):
        args = dict(self.kwargs, **overrides)
        with patch.object(D.L, "plan") as plan, patch.object(D.L, "reserve") as reserve, \
                patch.object(D, "make_runner") as real, patch.object(D.subprocess, "run") as transport:
            env = D.dispatch(**args)
        self.assertEqual(env["outcome"], "rejected", env)
        if expected:
            self.assertEqual(env["reason_code"], expected, env)
        self.assertFalse(env["evidence"]["production_admitted"], env)
        self.assertFalse(env["evidence"]["accepted_production"], env)
        self.assertFalse(env["evidence"]["generated"], env)
        plan.assert_not_called()
        reserve.assert_not_called()
        real.assert_not_called()
        self.assertEqual(transport.call_count, 0)
        return env

    def test_manual_authorization_and_four_pick_receipt_cannot_authorize(self):
        (self.run / "control" / "card-receipt.json").write_text(json.dumps(CARD))
        (self.run / "control" / "authorization.json").write_text(json.dumps({
            "approved": True, "campaign_digest": "0" * 64,
            "expires_at": "2099-01-01T00:00:00Z", "approved_by": "owner"}))
        before = {p.name: p.read_bytes() for p in (self.run / "control").iterdir()}
        self.assert_zero_spend_refusal("PRODUCTION_STATE_UNVERIFIED")
        self.assertEqual(before, {p.name: p.read_bytes() for p in (self.run / "control").iterdir()})
        self.assertFalse((self.run / "spend.sqlite3").exists())

    def test_manual_store_initialization_cannot_replace_intake_provenance(self):
        import state_store
        from batch_mode.batch import STAGES
        from kie_dispatch import model_lock
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.init_run("run", [stage for stage, _ in STAGES])
        model_lock.lock_run_model(self.run / "control" / "state.sqlite3", "run", "minimax-h3/*")
        self.assert_zero_spend_refusal("PRODUCTION_INTAKE_AUTHORITY_MISSING")

    def ready_for_music(self, **preferences):
        from test_production_process import confirmed_run, complete_stage, approve_script
        confirmed_run(self.run, **preferences)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)
        return approve_script(self.run)

    def music_arguments(self, lyrics):
        request = {"model": D._R.KIE_MUSIC_TASK_MODEL,
                   "callBackUrl": "https://example.invalid/offline-callback",
                   "run_dir": str(self.run), "card_receipt": copy.deepcopy(CARD),
                   "input": {"model": "V6", "custom_mode": True, "instrumental": False,
                             "title": "A new chapter", "lyrics": lyrics,
                             "style": "Soul Ballad", "negative_tags": "distortion", "duration": 120}}
        return dict(self.kwargs, model=request["model"], request=request, stage="music")

    def test_confirmed_intake_cannot_skip_predecessors_before_paid_dispatch(self):
        from test_production_process import confirmed_run
        confirmed_run(self.run, song=False)
        self.assert_zero_spend_refusal("PRODUCTION_PREDECESSOR_INCOMPLETE")

    def test_valid_governed_music_reaches_only_the_trapped_ledger_boundary(self):
        doc = self.ready_for_music()
        arguments = self.music_arguments(doc["lyrics"])
        with patch.object(D.L, "plan", return_value={"outcome": "parked", "reason_code": "OFFLINE_ADMISSION_TRAP"}) as plan, \
                patch.object(D.L, "reserve") as reserve, patch.object(D.subprocess, "run") as transport, \
                patch.object(D._LG, "kie_request") as governor:
            env = D.dispatch(**arguments)
        self.assertEqual(env["reason_code"], "OFFLINE_ADMISSION_TRAP", env)
        self.assertTrue(env["evidence"]["production_admitted"], env)
        self.assertFalse(env["evidence"]["accepted_production"], env)
        self.assertEqual(env["evidence"]["process_admission"]["authority"], "intake-session")
        plan.assert_called_once()
        reserve.assert_not_called()
        self.assertEqual(transport.call_count, 0)
        governor.assert_not_called()

    def test_valid_early_reference_images_use_continuity_stage(self):
        from test_production_process import complete_stage
        self.ready_for_music(song=False)
        complete_stage(self.run, "music")
        with patch.object(D.L, "plan", return_value={"outcome": "parked", "reason_code": "OFFLINE_REFERENCE_TRAP"}) as plan, \
                patch.object(D.L, "reserve") as reserve, patch.object(D.subprocess, "run") as transport:
            env = D.dispatch(**dict(self.kwargs, stage="continuity-bible"))
        self.assertEqual(env["reason_code"], "OFFLINE_REFERENCE_TRAP", env)
        self.assertTrue(env["evidence"]["production_admitted"], env)
        self.assertEqual(env["evidence"]["process_admission"]["stage"], "continuity-bible")
        plan.assert_called_once()
        reserve.assert_not_called()
        self.assertEqual(transport.call_count, 0)

    def test_request_override_cannot_approve_different_provider_lyrics(self):
        self.ready_for_music()
        arguments = self.music_arguments("These are different, unapproved words.")
        arguments["request"]["script_approval"] = {
            "required": True, "status": "approved", "approved_by": "forged-client",
            "lyrics_sha": D._SA.lyrics_sha(arguments["request"]["input"]["lyrics"])}
        self.assert_zero_spend_refusal("PRODUCTION_APPROVAL_SCOPE_MISMATCH", **arguments)

    def ready_for_video(self):
        from test_production_process import complete_stage, approve_storyboard
        doc = self.ready_for_music(song=False)
        for stage in ("music", "continuity-bible", "storyboard", "image-keyframes"):
            complete_stage(self.run, stage)
        approve_storyboard(self.run)
        return doc

    def test_separation_and_picture_repair_use_video_context_without_relabeling_music(self):
        doc = self.ready_for_video()
        for model, kind, inp in (
                ("ai-music-api/separate-vocals", "lipsync-vocal-separation",
                 {"audio_url": "https://example.invalid/selected-song", "type": "separate_vocal", "stem_name": "Lead Vocal"}),
                (MODEL, "lipsync-picture-regeneration", {"prompt": "p" * 200})):
            request = dict(self.request, model=model, input=inp, request_kind=kind,
                           production_stage="video-generation")
            with patch.object(D.L, "plan", return_value={"outcome": "parked", "reason_code": "OFFLINE_REPAIR_TRAP"}) as plan, \
                    patch.object(D.L, "reserve") as reserve, patch.object(D.subprocess, "run") as transport:
                env = D.dispatch(**dict(self.kwargs, model=model, request=request, stage="video-generation"))
            self.assertEqual(env["reason_code"], "OFFLINE_REPAIR_TRAP", env)
            self.assertTrue(env["evidence"]["production_admitted"], env)
            plan.assert_called_once()
            reserve.assert_not_called()
            self.assertEqual(transport.call_count, 0)
        self.assert_zero_spend_refusal("PRODUCTION_STAGE_MISMATCH",
                                      **dict(self.music_arguments(doc["lyrics"]), stage="video-generation"))

    def test_producer_callers_require_and_preserve_actual_stage_context(self):
        from audio_c3 import lipsync_producer as producer
        from lip_sync.lip_gate import picture_gate as picture
        source = self.run / "source.bin"
        source.write_bytes(b"synthetic local source")
        request = {"run_id": "run", "source_path": str(source),
                   "source_sha256": producer._sha(source), "output_dir": str(self.run)}
        uploads = []
        real = producer.skill74_runner(self.run, lambda p: uploads.append(p), {}, lambda r: {})
        with self.assertRaises(ValueError) as caught:
            real(request)
        self.assertEqual(caught.exception.code, "LIPSYNC_PRODUCTION_STAGE_REQUIRED")
        self.assertEqual(uploads, [])
        for stage in ("video-generation", "qc-retakes"):
            out = self.run / stage
            out.mkdir()
            captured = []
            def fake_dispatch(**kw):
                captured.append(kw)
                return {"outcome": "ok", "evidence": {}}
            runner = producer.skill74_runner(self.run, lambda p: "https://example.invalid/source",
                                             {"stage": stage}, lambda result: {}, dispatch_fn=fake_dispatch)
            with patch.object(producer, "_approval_context", return_value=copy.deepcopy(CARD)):
                runner(dict(request, output_dir=str(out)))
            self.assertEqual(captured[0]["stage"], stage)
            self.assertEqual(captured[0]["request"]["production_stage"], stage)
            regenerate = picture.make_regenerate(source, save_dir=str(out), ledger_db=self.kwargs["ledger_db"],
                                                 run_id="run", logical_key="face/1", estimated_cost=1,
                                                 card_receipt=CARD, uploader=lambda p: "https://example.invalid/image",
                                                 production_stage=stage)
            with patch.object(picture, "_dispatch", return_value=D), \
                    patch.object(D, "dispatch", return_value={"outcome": "ok", "evidence": {"saved_paths": [str(out / "fake.png")]}}) as dispatch:
                regenerate(str(source), "a proposed prompt")
            self.assertEqual(dispatch.call_args.kwargs["stage"], stage)
            self.assertEqual(dispatch.call_args.kwargs["request"]["production_stage"], stage)
        regenerate = picture.make_regenerate(source, save_dir=str(self.run), ledger_db=self.kwargs["ledger_db"],
                                             run_id="run", logical_key="face/1", estimated_cost=1,
                                             card_receipt=CARD, uploader=lambda p: uploads.append(p))
        with self.assertRaisesRegex(picture.RegenerationFailed, "PRODUCTION_STAGE_REQUIRED"):
            regenerate(str(source), "draft prompt")
        self.assertEqual(uploads, [])

    def test_current_storyboard_allows_a_bound_subset_and_rejects_substitution(self):
        from test_production_process import complete_stage, approve_storyboard
        self.ready_for_music(song=False)
        for stage in ("music", "continuity-bible", "storyboard", "image-keyframes"):
            complete_stage(self.run, stage)
        approve_storyboard(self.run)
        gate = json.loads((self.run / "storyboard" / "gate.json").read_text())
        request = dict(self.request, model="minimax-h3/image-to-video",
                       storyboard={"shots": gate["shots"][:1], "review": gate["review"]})
        arguments = dict(model=request["model"], request=request, stage="video-generation",
                         run_id="run", ledger_db=self.kwargs["ledger_db"], save_dir=self.kwargs["save_dir"])
        with patch.object(D.L, "plan") as plan, patch.object(D.subprocess, "run") as transport:
            admitted = D.production_process_admission(**arguments)
            self.assertTrue(admitted["ok"], admitted)
            request["storyboard"]["shots"][0]["visual_objective"] = "Unapproved substituted scene"
            refused = D.production_process_admission(**arguments)
        self.assertEqual(refused["reason_code"], "PRODUCTION_APPROVAL_SCOPE_MISMATCH", refused)
        plan.assert_not_called()
        self.assertEqual(transport.call_count, 0)

    def test_real_runner_rechecks_current_artifact_authority_at_submit(self):
        doc = self.ready_for_music()
        arguments = self.music_arguments(doc["lyrics"])
        request = arguments.pop("request")
        context_arguments = {k: arguments[k] for k in
                             ("model", "save_dir", "ledger_db", "run_id", "stage", "adapter_path")}
        self.assertTrue(D.production_process_admission(request=request, **context_arguments)["ok"])
        req_path = self.run / "request.json"
        req_path.write_text(json.dumps(request))
        live = D.make_runner(process_context={"arguments": context_arguments,
                                              "request_digest": D.L.digest_request(request)})
        script_path = self.run / "creative" / "script.json"
        changed = json.loads(script_path.read_text())
        changed["lyrics"] = "Changed after admission"
        script_path.write_text(json.dumps(changed))
        with patch.object(D.subprocess, "run") as transport, patch.object(D._LG, "kie_request") as governor:
            with self.assertRaisesRegex(D.DispatchError, "SCRIPT_NOT_APPROVED|PRODUCTION_"):
                live([str(Path(__file__)), "submit", "--request", str(req_path)])
        self.assertEqual(transport.call_count, 0)
        governor.assert_not_called()

    def test_injecting_real_runner_does_not_skip_production_admission(self):
        live = D.make_runner()
        self.assert_zero_spend_refusal("PRODUCTION_STATE_UNVERIFIED", runner=live)

    def test_provider_payload_cannot_name_a_different_model(self):
        req = dict(self.request, model="another-image-model")
        self.assert_zero_spend_refusal("PRODUCTION_MODEL_MISMATCH", request=req)

    def test_output_and_ledger_cannot_cross_run_scope(self):
        self.assert_zero_spend_refusal("PRODUCTION_RUN_SCOPE_MISMATCH",
                                      save_dir=str(Path(self.temp.name) / "other-run"))
        self.assert_zero_spend_refusal("PRODUCTION_RUN_SCOPE_MISMATCH",
                                      ledger_db=str(Path(self.temp.name) / "other-ledger.sqlite3"))

    def test_paid_media_cannot_label_itself_research(self):
        self.assert_zero_spend_refusal("PRODUCTION_STAGE_MISMATCH", stage="research")

    def test_ambiguous_images_require_their_actual_stage(self):
        self.assert_zero_spend_refusal("PRODUCTION_STAGE_REQUIRED", stage="kie")

    def test_missing_shared_authority_fails_closed(self):
        with patch.dict(sys.modules, {"production_process": None}):
            self.assert_zero_spend_refusal("PRODUCTION_AUTHORITY_UNREADABLE")

    def test_offline_draft_preparation_has_no_spend_or_acceptance(self):
        draft = copy.deepcopy(self.request)
        draft["input"]["prompt"] = "A proposed fictional dramatic opening."
        before = json.dumps(draft, sort_keys=True)
        with patch.object(D.L, "plan") as plan, patch.object(D.subprocess, "run") as transport:
            receipt = D.production_process_admission(
                model=MODEL, request=draft, save_dir=self.kwargs["save_dir"],
                ledger_db=self.kwargs["ledger_db"], run_id="run")
        self.assertFalse(receipt["ok"])
        self.assertEqual(json.dumps(draft, sort_keys=True), before)
        plan.assert_not_called()
        self.assertEqual(transport.call_count, 0)

    def test_real_runner_without_governed_context_cannot_submit_even_wrapped(self):
        live = D.make_runner()
        with patch.object(D.subprocess, "run") as transport, patch.object(D._LG, "kie_request") as governor:
            with self.assertRaisesRegex(D.DispatchError, "PRODUCTION_CONTEXT_REQUIRED"):
                live([str(Path(__file__)), "submit", "--request", "unused.json"])
            rc, _doc, raw = D._call(lambda argv: live(argv), str(Path(__file__)),
                                   ["submit", "--request", "unused.json"])
        self.assertEqual(rc, -1)
        self.assertIn("PRODUCTION_CONTEXT_REQUIRED", raw)
        self.assertEqual(transport.call_count, 0)
        governor.assert_not_called()

    def test_real_runner_rejects_payload_change_before_transport(self):
        req_path = self.run / "request.json"
        req_path.write_text(json.dumps(dict(self.request, changed=True)))
        live = D.make_runner(process_context={"request_digest": D.L.digest_request(self.request),
                                              "arguments": {}})
        with patch.object(D.subprocess, "run") as transport, patch.object(D._LG, "kie_request") as governor:
            with self.assertRaisesRegex(D.DispatchError, "PRODUCTION_REQUEST_CHANGED"):
                live([str(Path(__file__)), "submit", "--request", str(req_path)])
        self.assertEqual(transport.call_count, 0)
        governor.assert_not_called()

    def test_injected_simulation_never_becomes_production_evidence(self):
        ledger.init_run(self.kwargs["ledger_db"], "run", 1000)
        commands = []
        def fake(argv):
            command = argv[1]
            commands.append(command)
            return {"health": (0, {"adapter_mode": "active"}),
                    "preflight": (0, {"state": "validated", "data": {"ok": True}}),
                    "prompt-budget": (0, {"state": "success", "data": {"status": "OK", "exit_code": 0}}),
                    "submit": (0, {"state": "queued", "task_id": "offline-1"}),
                    "wait": (0, {"state": "success", "task_id": "offline-1", "credits_consumed": 10}),
                    "save": (0, {"state": "success", "saved_paths": [str(self.run / "fake.png")]})}[command]
        with patch.object(D.subprocess, "run") as transport, patch.object(D, "make_runner") as live:
            env = D.dispatch(**self.kwargs, runner=fake)
        self.assertEqual(env["outcome"], "ok", env)
        self.assertIn("submit", commands)
        self.assertEqual(env["evidence"]["execution_mode"], "offline")
        self.assertFalse(env["evidence"]["production_admitted"])
        self.assertFalse(env["evidence"]["accepted_production"])
        self.assertEqual(transport.call_count, 0)
        live.assert_not_called()


if __name__ == "__main__":
    unittest.main()

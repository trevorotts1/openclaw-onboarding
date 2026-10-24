"""Offline regressions for the concrete manual-receipt/stage bypasses.

TemporaryDirectory respects TMPDIR; no fixed /tmp path, provider or media call.
The fixture uses the real full card and existing Store/approval event writers.
"""
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

CORE = Path(__file__).resolve().parent
sys.path.insert(0, str(CORE))
import production_process as process
import state_store
from choice_card.intake_card import intake_card as card
from choice_card.intake_card import intake_session as session
from intake_preflight import preflight
from script_approval import script_approval as approval


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def confirmed_run(run, *, script=True, song=True, storyboard=True):
    """Actual full catalog, one renderer-bound raw client reply per turn."""
    run = Path(run)
    replies = {"offer": "New Chapter Coaching", "link": "https://example.com/coaching",
               "audience": "successful founders 45–60 building a new chapter",
               "character": "Christine, a lawyer on New Year's Eve",
               "photos": "Generate the photos", "models": "deepseek-chain builds, opus-chain checks",
               "length": "2 minutes", "spend": "$25",
               "script": "1" if script else "2", "song": "1" if song else "2",
               "storyboard": "1" if storyboard else "2"}
    turn = session.process([], run_dir=run, purpose_flow=False, runtime="claude-nine")
    for _ in range(30):
        qid = turn.get("question_id")
        if qid == "recap":
            raw = "yes"
        else:
            raw = replies.get(qid, "1")
        turn = session.process([raw], run_dir=run, purpose_flow=False, runtime="claude-nine",
                               question_id=qid, question_digest=turn.get("question_digest"),
                               source="client", source_ref="offline-owner-fixture:" + str(qid))
        if turn.get("done"):
            return turn["run_id"]
        if turn.get("outcome") not in ("ok", None):
            raise AssertionError(turn)
    raise AssertionError("full intake did not reach its explicit confirmation: %r" % turn)


def complete_stage(run, stage):
    """Use existing legal Store transitions; synthetic artifacts are local only."""
    run = Path(run)
    _, registry = process._graph()
    for rel in registry[stage].get("required_artifacts", []):
        path = run / rel
        if not path.exists():
            write_json(path, {"fixture": stage})
    with state_store.Store(run / "control" / "state.sqlite3") as store:
        store.transition(run.name, stage, "READY", "fixture-worker")
        store.claim(run.name, stage, "fixture-worker")
        store.transition(run.name, stage, "COMPLETE", "fixture-worker")


def approve_script(run):
    """Exercise existing revision-bound whole-package presentation/reply APIs."""
    run = Path(run)
    doc = {"title": "A new chapter", "story": [["Act 1", ["Christine watches the clock."]]],
           "sheet": [{"tag": "Verse", "lines": ["I choose my new chapter today"]}],
           "lyrics": "I choose my new chapter today"}
    write_json(run / "creative" / "script.json", doc)
    context = {"run_id": run.name, "conversation_id": "offline-owner-conversation",
               "approved_by": "fixture-client", "reply_to_message_id": "fixture-script-presented"}
    approval.request_approval(run, doc["title"], doc["story"], doc["sheet"], doc["lyrics"],
                              maker="fixture-builder", context=context, message_id="fixture-script-presented")
    approval.mark_sent(run)
    rec = approval.record_for(run)
    context.update(source="client", source_ref="fixture-owner-approval",
                   presentation_ask_id=next(a["ask_id"] for a in rec["asks"] if a["state"] == "open"))
    result = approval.handle_reply(run, "I approve both", doc["title"], doc["story"], doc["sheet"], doc["lyrics"],
                                   lambda reply, story, sheet: (story, sheet, doc["lyrics"]),
                                   lambda story, sheet: [], context=context)
    if result.get("status") != "approved":
        raise AssertionError(result)
    return doc


def approve_storyboard(run):
    """Use the existing whole-package presentation and GO handler, no media."""
    from storyboard_director import approval_runner
    run = Path(run)
    shots, contracts, stills = [], {}, {}
    for n in range(1, 4):
        sid = "s%d" % n
        shots.append({"shot_id": sid, "song_start": (n - 1) * 8.0, "song_end": n * 8.0,
                      "lyric_line_ids": ["l%d" % n], "story_stage": "new-chapter",
                      "visual_objective": "Christine chooses next step %d" % n,
                      "character_ids": ["christine"], "wardrobe_ids": ["suit"],
                      "location_id": "office", "product_visibility": "featured" if n == 2 else "none",
                      "camera_direction": "close-up direction %d" % n, "reference_assets": [],
                      "image_model_capability_request": {}, "video_model_capability_request": {},
                      "continuity_constraints": [], "negative_constraints": [], "cost_estimate": 10,
                      "qc_requirements": ["speaker-visibility"], "status": "planned"})
        contracts[sid] = {"lyric_text": "line %d" % n,
                          "viewer_understanding": "she chooses her next step %d" % n,
                          "character_action": "Christine takes step %d" % n, "visible_emotion": "hope"}
        still = run / "storyboard" / (sid + ".png")
        still.parent.mkdir(parents=True, exist_ok=True)
        still.write_bytes(b"synthetic local still %d" % n)
        stills[sid] = str(still)
    for name, data in (("shot-list.json", {"shots": shots}), ("contracts.json", contracts), ("stills.json", stills)):
        write_json(run / "storyboard" / name, data)
    # The full card writer already elected approval. Exercise the actual
    # presentation, WAITING_APPROVAL transition and client GO reply.
    pending = approval_runner.run(str(run), lambda message, images: None)
    if pending["action"] != "waiting":
        raise AssertionError(pending)
    result = approval_runner.run(str(run), lambda message, images: None, reply="GO")
    if result["action"] != "approved":
        raise AssertionError(result)
    return shots


def run_hashes(run):
    return {str(p.relative_to(run)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path(run).rglob("*") if p.is_file()}


class ProductionProcessTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="s75-production-provenance-")
        self.addCleanup(self.temp.cleanup)
        self.run = Path(self.temp.name) / "run"

    def ready_for_music(self, **preferences):
        confirmed_run(self.run, **preferences)
        for stage in ("research", "creative-strategy", "script-lyrics"):
            complete_stage(self.run, stage)

    def test_full_confirmed_intake_allows_unpaid_research_without_future_approval(self):
        rid = confirmed_run(self.run)
        before = run_hashes(self.run)
        admitted = process.admit_production(self.run, "research", run_id=rid)
        self.assertTrue(admitted["ok"], admitted)
        self.assertEqual(admitted["current_state"], "NOT_STARTED")
        self.assertEqual(admitted["authority"], "intake-session")
        self.assertFalse((self.run / "creative" / "script-approval.json").exists())
        self.assertEqual(run_hashes(self.run), before)

    def test_manual_authorization_and_four_picks_are_never_authority(self):
        self.run.mkdir()
        write_json(self.run / "control" / "authorization.json",
                   {"scope": "campaign", "summary_digest": "manual", "expires_unix": 9999999999})
        write_json(self.run / "control" / "card-receipt.json",
                   {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                                "length": 120, "video_model": "MiniMax H3"},
                    "who": "client", "when": "2026-10-24T00:00:00Z"})
        before = run_hashes(self.run)
        r = process.admit_production(self.run, "music")
        self.assertFalse(r["ok"])
        self.assertEqual(run_hashes(self.run), before)
        self.assertFalse((self.run / "control" / "state.sqlite3").exists())

    def test_manual_store_initialization_does_not_prove_intake_or_stage_completion(self):
        from kie_dispatch import model_lock
        (self.run / "control").mkdir(parents=True)
        order, _ = process._graph()
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.init_run(self.run.name, order)
        model_lock.lock_run_model(self.run / "control" / "state.sqlite3", self.run.name, "minimax-h3/*")
        r = process.admit_production(self.run, "music")
        self.assertFalse(r["ok"])
        self.assertEqual(r["reason_code"], "PRODUCTION_INTAKE_AUTHORITY_MISSING")

    def test_wrong_predecessor_stage_and_wrong_run_are_rejected(self):
        confirmed_run(self.run)
        r = process.admit_production(self.run, "music")
        self.assertEqual(r["reason_code"], "PRODUCTION_PREDECESSOR_INCOMPLETE")
        self.assertEqual(r["predecessor"], "research")
        self.assertFalse(process.admit_production(self.run, "research", run_id="another-run")["ok"])
        self.assertEqual(process.admit_production(self.run, "kie")["reason_code"], "PRODUCTION_STAGE_UNKNOWN")

    def test_live_wal_parked_state_is_seen_without_writing_source_sidecars(self):
        confirmed_run(self.run)
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.transition(self.run.name, "research", "READY", "fixture-worker")
            store.transition(self.run.name, "research", "PARKED", "fixture-worker", reason="owner paused")
            before = run_hashes(self.run)
            r = process.admit_production(self.run, "research")
            self.assertEqual(r["reason_code"], "PRODUCTION_STAGE_NOT_RUNNABLE")
            self.assertEqual(r["current_state"], "PARKED")
            self.assertEqual(run_hashes(self.run), before)

    def test_live_wal_model_lock_must_match_exact_confirmed_provider_choice(self):
        confirmed_run(self.run)
        state = json.loads((self.run / "control" / "intake-session.json").read_text())
        expected_model = state["model_lock"]["model"]
        self.assertEqual(expected_model, "minimax-h3/*")
        def stamps():
            return {str(p.relative_to(self.run)): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                    for p in self.run.rglob("*") if p.is_file()}
        with state_store.Store(self.run / "control" / "state.sqlite3") as store:
            store.transition(self.run.name, "research", "READY", "fixture-worker")
            before = stamps()
            matching = process.inspect_intake(self.run)
            self.assertTrue(matching["ok"], matching)
            self.assertEqual(matching["video_model_lock"], expected_model)
            self.assertTrue(process.admit_production(self.run, "research")["ok"])
            self.assertEqual(stamps(), before)
            store.con.execute("UPDATE video_model_lock SET model=? WHERE run_id=?",
                              ("bytedance/seedance-2-5", self.run.name))
            store.con.commit()
            # The old immutable projection still sees the checkpointed H3
            # lock. The production inspector must validate the live WAL lock.
            self.assertTrue(session.completion_status(self.run)["done"])
            before = stamps()
            changed = process.inspect_intake(self.run)
            self.assertFalse(changed["ok"], changed)
            self.assertEqual(changed["reason_code"], "PRODUCTION_VIDEO_MODEL_LOCK_MISMATCH")
            self.assertEqual(changed["video_model_lock"], "bytedance/seedance-2-5")
            self.assertEqual(process.admit_production(self.run, "research")["reason_code"],
                             "PRODUCTION_VIDEO_MODEL_LOCK_MISMATCH")
            self.assertEqual(stamps(), before)

    def test_direct_database_completion_without_transition_is_not_accepted(self):
        confirmed_run(self.run)
        db = self.run / "control" / "state.sqlite3"
        with closing(sqlite3.connect(db)) as con:
            con.execute("UPDATE stages SET state='COMPLETE' WHERE stage='research'")
            con.commit()
        r = process.admit_production(self.run, "creative-strategy")
        self.assertEqual(r["reason_code"], "PRODUCTION_PREDECESSOR_INCOMPLETE")

    def test_mutated_saved_answer_and_assistant_confirmation_do_not_become_client_intent(self):
        confirmed_run(self.run)
        answers = self.run / "card-answers.json"
        doc = json.loads(answers.read_text())
        audience = next(row for row in doc["answers"] if row["id"] == "audience")
        audience["text"] = audience["value"] = "founders 48–58"
        write_json(answers, doc)
        r = process.inspect_intake(self.run)
        self.assertEqual(r["reason_code"], "PRODUCTION_ANSWER_HANDOFF_MISMATCH")
        ledger_path = self.run / "control" / "intake-session.json"
        ledger = json.loads(ledger_path.read_text())
        ledger["confirmation"]["source"] = "assistant"
        write_json(ledger_path, ledger)
        self.assertFalse(process.inspect_intake(self.run)["ok"])

    def test_preferences_or_manual_approval_status_do_not_approve_unseen_script(self):
        self.ready_for_music()
        r = process.admit_production(self.run, "music")
        self.assertEqual(r["reason_code"], "PRODUCTION_SCRIPT_MISSING")
        doc = approve_script(self.run)
        path = self.run / "creative" / "script-approval.json"
        write_json(path, {"required": True, "status": "approved", "approved_by": "client",
                          "lyrics_sha": approval.lyrics_sha(doc["lyrics"])})
        r = process.admit_production(self.run, "music")
        self.assertEqual(r["reason_code"], "PRODUCTION_SCRIPT_APPROVAL_UNVERIFIED")

    def test_governed_whole_script_approval_allows_music_and_changes_invalidate_scope(self):
        self.ready_for_music()
        doc = approve_script(self.run)
        before = run_hashes(self.run)
        admitted = process.admit_production(self.run, "music")
        self.assertTrue(admitted["ok"], admitted)
        self.assertEqual(admitted["approved_script"]["lyrics_sha256"], approval.lyrics_sha(doc["lyrics"]))
        self.assertEqual(run_hashes(self.run), before)
        doc["story"][0][1].append("Changed whole-story ending")
        write_json(self.run / "creative" / "script.json", doc)
        r = process.admit_production(self.run, "music")
        self.assertEqual(r["reason_code"], "PRODUCTION_SCRIPT_APPROVAL_UNVERIFIED")

    def test_existing_legacy_event_authority_remains_supported_without_rewriting_answers(self):
        self.ready_for_music()
        approve_script(self.run)
        # This is the older supported event-authority path; surviving raw
        # source records are never inferred or generated by the checker.
        (self.run / "control" / "intake-session.json").unlink()
        before = run_hashes(self.run)
        r = process.admit_production(self.run, "music")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["authority"], "legacy-artifact-decisions")
        self.assertEqual(run_hashes(self.run), before)

    def test_offline_dispatch_success_cannot_prove_a_predecessor(self):
        confirmed_run(self.run)
        complete_stage(self.run, "research")
        write_json(self.run / "research" / "receipt.json",
                   {"outcome": "ok", "reason_code": "KIE_DISPATCH_OK", "execution_mode": "offline", "production_admitted": False})
        result = process.admit_production(self.run, "creative-strategy")
        self.assertEqual(result["reason_code"], "PRODUCTION_PREDECESSOR_OFFLINE_ONLY")

    def test_foreign_approval_run_cannot_be_reused(self):
        self.ready_for_music()
        approve_script(self.run)
        path = self.run / "creative" / "script-approval.json"
        rec = json.loads(path.read_text())
        rec["run"]["run_id"] = "foreign-run"
        write_json(path, rec)
        self.assertEqual(process.admit_production(self.run, "music")["reason_code"], "PRODUCTION_APPROVAL_SCOPE_MISMATCH")

    def test_changing_song_preference_file_cannot_remove_elected_artifact_gate(self):
        self.ready_for_music()
        approve_script(self.run)
        complete_stage(self.run, "music")
        write_json(self.run / "song-choices" / "state.json", {"required": False})
        r = process.admit_production(self.run, "continuity-bible")
        self.assertEqual(r["reason_code"], "PRODUCTION_SONG_PREFERENCE_MISMATCH")

    def test_storyboard_approval_is_checked_at_video_not_image_keyframe_stage(self):
        self.ready_for_music(song=False)
        approve_script(self.run)
        for stage in ("music", "continuity-bible", "storyboard"):
            complete_stage(self.run, stage)
        images = process.admit_production(self.run, "image-keyframes")
        self.assertTrue(images["ok"], images)
        complete_stage(self.run, "image-keyframes")
        write_json(self.run / "storyboard" / "approval.json", {"state": "approved", "who": "client", "at": 1})
        video = process.admit_production(self.run, "video-generation")
        self.assertEqual(video["reason_code"], "PRODUCTION_STORYBOARD_APPROVAL_UNVERIFIED")

    def test_current_whole_storyboard_gate_is_preserved_and_changed_gate_or_still_refuses(self):
        self.ready_for_music(song=False)
        approve_script(self.run)
        for stage in ("music", "continuity-bible", "storyboard", "image-keyframes"):
            complete_stage(self.run, stage)
        approve_storyboard(self.run)
        result = process.admit_production(self.run, "video-generation")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["approved_storyboard"]["shot_ids"], ["s1", "s2", "s3"])
        gate_path = self.run / "storyboard" / "gate.json"
        original = gate_path.read_bytes()
        gate = json.loads(original)
        gate["shots"][0]["visual_objective"] = "Unapproved substituted scene"
        write_json(gate_path, gate)
        self.assertEqual(process.admit_production(self.run, "video-generation")["reason_code"], "PRODUCTION_STORYBOARD_SCOPE_MISMATCH")
        gate_path.write_bytes(original)
        (self.run / "storyboard" / "s1.png").write_bytes(b"changed still")
        self.assertEqual(process.admit_production(self.run, "video-generation")["reason_code"], "PRODUCTION_STORYBOARD_APPROVAL_UNVERIFIED")

    def test_planning_uses_reduced_dependencies_but_still_requires_governed_intake(self):
        confirmed_run(self.run)
        payload = {"storage_dir": self.temp.name, "run_dir": str(self.run), "env": {}}
        with patch.object(preflight, "check_requirement", return_value={"ok": True, "detail": "offline dependency probe"}):
            planned = preflight.check(payload)
            self.assertEqual(planned["reason_code"], "preflight-pass-planning")
            self.assertEqual(planned["checks"]["mode"], "planning")
            self.assertTrue(planned["checks"]["card_recorded"])
            self.assertFalse(planned["checks"]["generating"])
            self.assertEqual({r["id"] for r in planned["checks"]["requirements"]},
                             {"platform-arch", "python-interpreter", "storage-capacity", "temp-capacity"})
            payload["stage"] = "research"
            self.assertEqual(preflight.check(payload)["reason_code"], "preflight-pass")
            (self.run / "control" / "intake-session.json").unlink()
            blocked = preflight.check(payload)
            self.assertFalse(blocked["production_admitted"])
            self.assertEqual(blocked["reason_code"], "PRODUCTION_LEGACY_AUTHORITY_UNVERIFIED")
            payload["mode"] = "diagnostic"
            diagnostic = preflight.check(payload)
            self.assertEqual(diagnostic["reason_code"], "preflight-pass-diagnostic")
            self.assertFalse(diagnostic["production_admitted"])

    def test_preflight_bare_files_are_dependencies_only_and_confirmed_run_is_planning_only(self):
        receipt = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad", "length": 120,
                               "video_model": "MiniMax H3"}, "who": "client", "at": "2026-10-24T00:00:00Z"}
        payload = {"storage_dir": self.temp.name, "mode": "quick", "card_receipt": receipt,
                   "auth": {"scope": "campaign"}, "summary_digest": "manual"}
        patches = (patch.object(preflight, "derive_requirements", return_value=[{"id": "fixture", "kind": "tool", "severity": "hard",
                    "manifest_id": "fixture", "manifest_severity": "hard", "why": "offline test"}]),
                   patch.object(preflight, "check_requirement", return_value={"ok": True, "detail": "offline check"}))
        with patches[0], patches[1]:
            r = preflight.check(payload)
            self.assertEqual(r["reason_code"], "preflight-pass-dependencies")
            self.assertFalse(r["production_admitted"])
            confirmed_run(self.run)
            payload["run_dir"] = str(self.run)
            payload.pop("auth")
            r = preflight.check(payload)
            self.assertEqual(r["reason_code"], "preflight-pass-planning")
            self.assertFalse(r["production_admitted"])
            payload["stage"] = "music"
            r = preflight.check(payload)
            self.assertEqual(r["reason_code"], "PRODUCTION_PREDECESSOR_INCOMPLETE")
            self.assertFalse(r["production_admitted"])


if __name__ == "__main__":
    unittest.main()

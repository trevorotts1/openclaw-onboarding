#!/usr/bin/env python3
"""UL-003 regression: the eight launch answers survive intake -> session -> plan.

Free: no network, no model, no paid call, no live send. Every value is synthetic.
Run: python3 shared-utils/signature_launch/tests/test_session_contract.py
"""
import hashlib
import importlib
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
REPO = PKG.parents[1]
CONTRACT = PKG / "session_contract.json"
FIXTURE = PKG / "fixtures/session_contract.complete_plan.json"
ANSWERS = REPO / "shared-utils/client_intake/fixtures"

sys.path.insert(0, str(REPO / "shared-utils/client_intake"))
sys.path.insert(0, str(REPO / "49-signature-funnel/scripts"))
import engine as e  # noqa: E402

li = importlib.import_module("launch_intake")

ANSWERS_FILE = "answers.elevation.json"
FIXED = dict(tenant_id="tenant-l01", location_id="loc-l01", launch_id="elevation-2026-11",
             client_identity_ref="client:l01-fixture", brand_ref="brand:l01-fixture",
             brand_hash="0" * 64, test_only=True)
SESSION_ID = "l01fixture001"


def doc(name=ANSWERS_FILE):
    return json.loads((ANSWERS / name).read_text(encoding="utf-8"))


def session_from(answers=None, session_id=SESSION_ID):
    s = li.new_session(**FIXED)
    s["session_id"] = session_id
    li.ingest_answers(s, answers or doc())
    return s


def canonical(plan):
    return json.dumps(plan, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(plan):
    return hashlib.sha256(canonical(plan)).hexdigest()


def approval_for(session, **over):
    a = {"schema_version": "1.0", "approval_id": "APPR-L01",
         "subject_type": "launch_plan_build", "subject_hash": session["plan_hash"],
         "owner_identity_ref": session["client_identity_ref"],
         "source_message_ref": "msg-l01", "recorded_at": li._now(),
         "scope": ["launch_plan_build"], "revoked": False,
         "verification_class": "recorded_consent_not_cryptographically_sealed"}
    a.update(over)
    return a


class TypedAdapters(unittest.TestCase):
    """A realistic transcript recorded through the real engine, never hand-built."""

    def transcript(self):
        d = e.new_doc("launch")
        for qid, value in (
                ("launch_calendar", "Doors open 3 Nov 2026 9:00 a.m. New York, launch at noon, "
                                    "doors close 10 Nov 2026 11:59 p.m."),
                ("channels", "Email only"),
                ("conversation_ai", "No, not this launch"),
                ("access_delivery", "Yes, send access after purchase"),
                ("payment_plans", "Paid in full"),
                ("sender_name", "Elevation Coaching Co"),
                ("reply_to_email", "hello@elevationcoaching.com"),
                ("a2p_ready", "No, not yet")):
            r = e.record(d, qid, value)
            self.assertTrue(r.get("ok"), (qid, r))
        return d

    def test_all_eight_answers_are_typed_and_keep_provenance(self):
        typed = e.launch_answers(self.transcript())
        self.assertEqual(typed["launch.channels"]["value"], ["email"])
        self.assertIs(typed["launch.conversation_ai"]["value"], False)
        self.assertIs(typed["launch.access_delivery"]["value"], True)
        self.assertIs(typed["launch.payment_plans"]["value"], False)
        self.assertIs(typed["launch.a2p_ready"]["value"], False)
        self.assertEqual(typed["launch.sender_name"]["value"], "Elevation Coaching Co")
        self.assertEqual(typed["launch.reply_to_email"]["value"], "hello@elevationcoaching.com")
        self.assertEqual(typed["launch.doors_open_at"]["value"], "2026-11-03T09:00:00-05:00")
        self.assertEqual(typed["launch.launch_at"]["value"], "2026-11-03T12:00:00-05:00")
        self.assertEqual(typed["launch.doors_close_at"]["value"], "2026-11-10T23:59:00-05:00")
        self.assertEqual(typed["launch.timezone"]["value"], "America/New_York")
        for key, entry in typed.items():
            self.assertEqual(entry["state"], "provided", key)
            self.assertEqual(entry["provenance"]["raw"] is not None, True, key)
            self.assertEqual(entry["source_ref"].split(":", 1)[0], "answers-file", key)

    def test_no_string_answer_is_ever_truthy(self):
        d = e.new_doc("launch")
        e.record(d, "a2p_ready", "No, not yet")
        self.assertIs(e.launch_answers(d)["launch.a2p_ready"]["value"], False)
        e.record(d, "conversation_ai", "No, not this launch")
        self.assertIs(e.launch_answers(d)["launch.conversation_ai"]["value"], False)

    def test_email_only_and_no_ai_stay_false(self):
        typed = e.launch_answers(self.transcript())
        self.assertNotIn("text", typed["launch.channels"]["value"])
        self.assertIs(typed["launch.conversation_ai"]["value"], False)

    def test_unknown_and_recommended_states_survive(self):
        d = e.new_doc("launch")
        e.record(d, "a2p_ready", "I'm not sure")       # help
        e.record(d, "a2p_ready", "not sure")           # safe default, flagged
        entry = e.launch_answers(d)["launch.a2p_ready"]
        self.assertEqual(entry["state"], "recommended_unapproved")
        self.assertIs(entry["value"], False)
        d2 = e.new_doc("launch")
        e.record(d2, "sender_name", "I'm not sure")
        e.record(d2, "sender_name", "no idea")         # never defaultable -> unknown
        self.assertEqual(e.launch_answers(d2)["launch.sender_name"],
                         {"value": None, "state": "unknown",
                          "source_ref": "answers-file:sender_name",
                          "provenance": {"question_id": "sender_name", "raw": None,
                                         "answer_status": "unknown", "answer_source": "client"}})

    def test_a_partial_calendar_never_invents_a_date(self):
        parsed = e.parse_launch_calendar("Doors open 3 Nov 2026 9:00 a.m. New York, launch at noon")
        self.assertEqual(parsed["doors_close_at"], None)
        self.assertEqual(parsed["launch_at"], "2026-11-03T12:00:00-05:00")


def collected_transcript():
    """A realistic client conversation through the real engine, saved and reloaded —
    no hand-edited answers file."""
    d = e.new_doc("launch", harness="claude-nine")
    for qid, value in (
            ("interview_mode", "I know what I want"), ("business_name", "Bright Path Studio"),
            ("offer_name", "The Path"),
            ("offer_description", "A six week program for new coaches who want their first clients."),
            ("audience", "New coaches; career changers"),
            ("offer_transformation", "They land their first three clients."),
            ("pains", "no clients; no offer; no confidence"),
            ("deliverables", "6 sessions; worksheets"),
            ("funnel_shape", "One offer"), ("price", "$497"), ("billing", "All at once"),
            ("bump", "No add-on"), ("upsell_1", "No thanks"),
            ("brand_colors", "primary #0A7E8C, background #FFFFFF"),
            ("page_set", "only the main page and checkout"),
            ("location", "Yes, my existing account"),
            ("launch_calendar", "Doors open 3 Nov 2026 9:00 a.m. New York, launch at noon, "
                                "doors close 10 Nov 2026 11:59 p.m."),
            ("channels", "Email only"), ("conversation_ai", "No, not this launch"),
            ("access_delivery", "Yes, send access after purchase"),
            ("payment_plans", "Paid in full"), ("sender_name", "Bright Path Studio"),
            ("reply_to_email", "hello@brightpath.example"), ("a2p_ready", "No, not yet")):
        assert e.record(d, qid, value).get("ok"), (qid, value)
    e.finalize(d)
    return d


class RealTranscript(unittest.TestCase):
    def test_collect_save_load_plan_keeps_every_answer_typed(self):
        import tempfile
        d = collected_transcript()
        with tempfile.TemporaryDirectory() as td:
            answers_path = Path(td) / "answers.json"
            e.save(d, answers_path)
            reloaded = e.load(answers_path)
            brand = Path(td) / "brand.json"
            brand.write_text('{"brand_id": "synthetic", "palette": {"primary": "#0A7E8C"}}')
            s = li.new_session(tenant_id="t", location_id="l", launch_id="bright-path-2026-11",
                               client_identity_ref="client:1", test_only=True)
            li.ingest_answers(s, reloaded, brand)
            session_path = Path(td) / "session.json"
            li.save_session(s, session_path)
            s = li.load_session(session_path)
            out = li.assemble_plan(s)
        self.assertIn(out["state"], ("awaiting_plan_approval", "recommendation_ready"), out)
        self.assertEqual(s["launch_plan_missing"], [])
        plan = s["launch_plan"]
        self.assertIs(plan["a2p_ready"], False)          # "No, not yet" never truthy
        self.assertEqual(plan["text_sets"], [])          # email-only plans no texts
        self.assertEqual(plan["conversation_ai"], {"requested": False, "mode": "none"})
        self.assertIs(plan["launch_answers"]["launch.access_delivery"]["value"], True)
        self.assertIs(plan["launch_answers"]["launch.payment_plans"]["value"], False)
        self.assertEqual(plan["launch_answers"]["launch.channels"]["value"], ["email"])
        self.assertEqual(plan["launch_answers"]["launch.reply_to_email"]["value"],
                         "hello@brightpath.example")
        self.assertEqual(plan["launch_calendar"]["doors_close_at"], "2026-11-10T23:59:00-05:00")


class EndToEnd(unittest.TestCase):
    def test_all_eight_answers_reach_the_assembled_plan(self):
        s = session_from()
        for key in li.LAUNCH_ANSWER_KEYS:
            self.assertIn(key, s["answers"], key)
            self.assertTrue(s["answers"][key].get("provenance"), key)
        out = li.assemble_plan(s)
        self.assertIn(out["state"], ("awaiting_plan_approval", "recommendation_ready"), out)
        self.assertEqual(s["launch_plan_missing"], [])
        plan = s["launch_plan"]
        self.assertEqual(plan["launch_calendar"]["timezone"], "America/New_York")
        self.assertEqual(plan["launch_calendar"]["launch_at"], "2026-11-03T12:00:00-05:00")
        self.assertIs(plan["a2p_ready"], False)
        self.assertEqual(plan["conversation_ai"], {"requested": False, "mode": "none"})
        self.assertIs(plan["offer"]["payment_plans"], False)
        self.assertEqual(plan["text_sets"], [])
        self.assertEqual(set(plan["launch_answers"]), set(li.LAUNCH_ANSWER_KEYS))
        self.assertEqual(plan["launch_answers"]["launch.sender_name"]["value"], "Elevation Coaching Co")

    def test_complete_plan_digest_fixture_for_l06(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["schema"], "signature-launch-session-contract.fixture/v1")
        self.assertEqual(fixture["plan_digest"]["value"], digest(fixture["launch_plan"]))
        rebuilt = session_from()
        li.assemble_plan(rebuilt)
        self.assertEqual(rebuilt["launch_plan"], fixture["launch_plan"],
                         "the published fixture is exactly what the pipeline builds")
        self.assertEqual(digest(rebuilt["launch_plan"]), fixture["plan_digest"]["value"])

    def test_a_requested_bot_without_a_mode_is_named_not_invented(self):
        s = session_from(doc("answers.7fig.json"))
        s["launch_id"] = "seven-figure-2026-11"
        li.assemble_plan(s)
        missing = " ".join(s["launch_plan_missing"])
        self.assertIn("Conversation AI", missing)
        self.assertIsNone(s["launch_plan"])

    def test_contract_names_every_answer_and_the_invalidation_cases(self):
        c = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(c["schema"], "signature-launch-session-contract/v1")
        ids = {a["id"] for a in c["launch_answers"]}
        self.assertEqual(ids, {"launch_calendar", "channels", "conversation_ai", "access_delivery",
                               "payment_plans", "sender_name", "reply_to_email", "a2p_ready"})
        cases = {x["id"] for x in c["approval"]["invalidation_cases"]}
        self.assertTrue({"answer_changed_after_approval", "revision_requested",
                         "plan_hash_mismatch", "approval_revoked", "session_not_awaiting_approval"} <= cases)
        self.assertEqual(c["fixture"]["path"], "shared-utils/signature_launch/fixtures/session_contract.complete_plan.json")


class ApprovalInvalidation(unittest.TestCase):
    def ready(self):
        s = session_from()
        li.assemble_plan(s)
        if s["state"] == "recommendation_ready":
            li.present_plan(s)
        return s

    def test_collecting_session_refuses_with_an_actionable_message(self):
        s = session_from()
        with self.assertRaisesRegex(li.IntakeError, "assemble_plan"):
            li.approve(s, approval_for(s), worker_identity_ref="worker-9")

    def test_changed_answer_after_approval_invalidates_it(self):
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        self.assertEqual(s["state"], "approved")
        li.answer(s, "a1_offer", "A new offer, same client")
        self.assertEqual(s["state"], "collecting")
        self.assertIsNone(s["approval"])
        self.assertIsNone(s["plan_hash"])
        self.assertEqual(s["history"][-2]["event"], "answer")
        self.assertEqual(s["history"][-1]["event"], "approval_invalidated")
        with self.assertRaisesRegex(li.IntakeError, "assemble_plan"):
            li.approve(s, approval_for(s), worker_identity_ref="worker-9")

    def test_reassembling_an_approved_plan_requires_a_revision(self):
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        with self.assertRaisesRegex(li.IntakeError, "request_revision"):
            li.assemble_plan(s)

    def test_building_session_refuses_answer_changes(self):
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        li.begin_build(s)
        with self.assertRaisesRegex(li.IntakeError, "request_revision"):
            li.answer(s, "a1_offer", "x")

    def test_revoked_approval_and_stale_hash_are_refused(self):
        s = self.ready()
        with self.assertRaisesRegex(Exception, "revoked"):
            li.approve(s, approval_for(s, revoked=True), worker_identity_ref="worker-9")
        with self.assertRaisesRegex(Exception, "subject_hash"):
            li.approve(s, approval_for(s, subject_hash="0" * 64), worker_identity_ref="worker-9")

    def test_reingesting_the_answers_file_after_approval_invalidates_it(self):
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        li.ingest_answers(s, doc())
        self.assertEqual(s["state"], "collecting")
        self.assertIsNone(s["approval"])

    def test_ingesting_into_a_building_session_is_refused(self):
        # A fact that changes during building must go through
        # request_revision(); the ledger must not silently drift under a
        # spent approval.
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        li.begin_build(s)
        before = dict(s["answers"]["launch.sender_name"])
        with self.assertRaisesRegex(li.IntakeError, "request_revision"):
            li.ingest_answers(s, doc())
        self.assertEqual(s["state"], "building")
        self.assertIsNotNone(s["approval"])
        self.assertEqual(s["plan"]["plan_approval_ref"], "APPR-L01")
        self.assertEqual(s["answers"]["launch.sender_name"], before)

    def test_invalidation_clears_the_full_plan_artifacts(self):
        # A stale launch_plan with a stale launch_answers block must never
        # read as approved after the approval is spent.
        s = self.ready()
        self.assertIsNotNone(s["launch_plan"])
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        self.assertIsNotNone(s["approved_launch_plan_digest"])
        li.answer(s, "a1_offer", "A new offer, same client")
        self.assertEqual(s["state"], "collecting")
        self.assertIsNone(s["launch_plan"])
        self.assertEqual(s["launch_plan_missing"], [])
        self.assertIsNone(s["approved_launch_plan"])
        self.assertIsNone(s["approved_launch_plan_digest"])

    def test_approval_pins_the_full_plan_digest(self):
        # The approval binds the page-plan hash through the gate AND pins the
        # full-plan digest the Skill 50 consumer verifies against the fixture.
        s = self.ready()
        li.approve(s, approval_for(s), worker_identity_ref="worker-9")
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(s["approved_launch_plan"], fixture["launch_plan"])
        self.assertEqual(s["approved_launch_plan_digest"],
                         fixture["plan_digest"]["value"])
        self.assertEqual(li.full_plan_digest(s["launch_plan"]),
                         s["approved_launch_plan_digest"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

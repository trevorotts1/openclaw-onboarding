#!/usr/bin/env python3
"""test_motion_intake_election.py -- Item 34 (FIX-PLAN) R5 acceptance for the
motion graphics intake election (R1): T2 and T3 in full, T12 hosted-path
parity, and the three-state election fixture proof.

WHAT THIS PINS
--------------
Motion is the FOURTH upsell election, wired exactly like its three siblings
(sales_checkout, vsl_page, email_sequences):
  * want_motion_graphics (upsell order 7.8, required, block_gate, default
    "no": opt-in, asked every run) and motion_graphics_declined_reason
    (order 7.81, conditional on a "no", stored VERBATIM as the waiver's
    client_request_quote, no default, empty re-asked), defined in
    intake/upsell-questions.json and mirrored in
    intake/deck-intake-questions.json (subfields riding the growth_assets
    and decline_context turns; alias rows at orders 20.04 and 22.08);
  * the fourth waiver_field_mapping entry, motion_graphics, in both banks;
  * the hosted path: the pair lands in pre_presentation_capture through
    intake/interview-app/bridge/intake_writer.py (T12) and projects
    identically through presentation_job/resolve_intake.py from the
    nested, flat, and both ledger shapes;
  * the seam: a decline with the client's verbatim reason is the recorded
    motion_graphics waiver (T2); a decline WITHOUT a reason is recorded
    NOWHERE as a waiver (T3, pinned at the definition, writer, projection,
    and seam layers; the chat driver's --complete refusal itself is a
    parent-verification integration step, per build/B34-TESTPLAN.md).

COPY RULE PINNED HERE: the client-facing question must NOT promise the
pieces play inside PowerPoint (landed doctrine: PowerPoint playback is
UNVERIFIED). It promises the pieces are embedded in the deck file with
the designed slide as their still.

Unit-level, house style: flat file in tests/, SCRIPTS on sys.path, direct
function calls, no network, no spend, no media dependency (this file must
never skip). The mg036 suite covers the engine YES side
(test_election_default_no_and_capture_yes); this file is the missing
decline side plus the wiring.

ASSEMBLY-PREP UNION (recorded in build/B34-ITEM34.md): this file is the
staging lineage's suite, merged with the assertions the contribution
lineage's same-named suite carried that this one lacked (the generated
UI question set's conditional_on/storeOn for the reason, and the direct
writer-mirror pins). Everything else in the contribution suite was
already covered here, in several places more strictly.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(HERE))  # sibling test-module imports (house style)

import pytest  # noqa: E402

import build_deck  # noqa: E402
from presentation_job import defers  # noqa: E402
from presentation_job import motion as pm  # noqa: E402
from presentation_job import resolve_intake  # noqa: E402

PRESENTATIONS = SCRIPTS.parent
UPSELL_BANK = PRESENTATIONS / "intake" / "upsell-questions.json"
DECK_BANK = PRESENTATIONS / "intake" / "deck-intake-questions.json"
APP = PRESENTATIONS / "intake" / "interview-app"
CONTRACT_JSON = APP / "schema" / "intake_fields.json"

#: The verbatim waiver quote used across this file (and the exclusion
#: sibling): mixed case and punctuation on purpose -- any strip, lower,
#: or summarize mutation breaks byte equality.
REASON = "No thanks, our brand team handles ALL motion in-house."
VSL_REASON = "We don't have a video."

NESTED_DECLINE = {
    "pre_presentation_capture": {
        "WANT_MOTION_GRAPHICS": "no",
        "MOTION_GRAPHICS_DECLINED_REASON": REASON,
    },
    "waivers": [{"rule": "motion_graphics", "client_request_quote": REASON}],
}
WAIVER_ONLY_DECLINE = {
    "waivers": [{"rule": "motion_graphics", "client_request_quote": REASON}],
}
BARE_DECLINE = {"pre_presentation_capture": {"WANT_MOTION_GRAPHICS": "no"}}
BLANK_REASON = {
    "pre_presentation_capture": {
        "WANT_MOTION_GRAPHICS": "no",
        "MOTION_GRAPHICS_DECLINED_REASON": "   ",
    },
}


def _writer():
    bridge = str(APP / "bridge")
    if bridge not in sys.path:
        sys.path.insert(0, bridge)
    import intake_writer  # noqa: PLC0415

    return intake_writer


def _hosted_answers(**overrides):
    """An otherwise complete hosted answers map (the PRES-006 complete
    set plus every election answered)."""
    answers = {
        "presentation_type": "from_scratch",
        "offer_name": "The Momentum Method",
        "named_methodology": "The Three-Move Pipeline",
        "transformation_promise": "stuck -> closing",
        "time_to_result": "8 weeks",
        "audience": "women entrepreneurs, 35-55",
        "cta_action": "book a call",
        "tone": "Inspirational",
        "final_price": "$497",
        "speech_speed_preference": "default",
        "want_sales_checkout": "yes",
        "want_vsl_page": "no",
        "vsl_page_declined_reason": VSL_REASON,
        "want_email_sequences": "no",
        "email_sequences_declined_reason": "We run our own email list.",
        "want_motion_graphics": "yes",
    }
    answers.update(overrides)
    return answers


def _still_run(tmp_path: Path, intake: dict) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run_dir / "working" / "copy" / "intake.json").write_text(
        json.dumps(intake), encoding="utf-8")
    slides = [{"slide": 1, "scene": "scene-1",
               "copy": ["Northwind Co", "A still opening slide"]}]
    (run_dir / "working" / "copy" / "slides.json").write_text(
        json.dumps({"slides": slides}), encoding="utf-8")
    return run_dir


def _slides_of(run_dir: Path):
    obj = json.loads(
        (run_dir / "working" / "copy" / "slides.json").read_text(
            encoding="utf-8"))
    return obj["slides"] if isinstance(obj, dict) else obj


# ===========================================================================
# Definition shape (T3 arm 1; also T12 assertion 6, payload lockstep)
# ===========================================================================

class TestMotionQuestionDefinitions:
    @classmethod
    def setup_class(cls):
        cls.upsell = json.loads(UPSELL_BANK.read_text(encoding="utf-8"))
        cls.deck = json.loads(DECK_BANK.read_text(encoding="utf-8"))
        cls.uq = {q["id"]: q for q in cls.upsell["questions"]}
        cls.dq = {q["id"]: q for q in cls.deck["questions"]}

    def test_upsell_toggle_shape(self):
        q = self.uq["want_motion_graphics"]
        assert q["order"] == 7.8
        assert q["storeOn"] == "WANT_MOTION_GRAPHICS"
        assert q["required"] is True
        assert q["block_gate"] is True
        assert q["default"] == "no"
        assert q["allowed_values"] == ["yes", "no"]

    def test_upsell_reason_shape(self):
        q = self.uq["motion_graphics_declined_reason"]
        assert q["order"] == 7.81
        assert q["storeOn"] == "MOTION_GRAPHICS_DECLINED_REASON"
        assert q["required"] is True
        assert q["block_gate"] is True
        assert q["conditional_on"] == {"id": "want_motion_graphics",
                                       "equals": "no"}
        assert "default" not in q  # no default, no fallback: empty re-asked

    def test_upsell_store_target_and_waiver_mapping(self):
        assert self.upsell["storeTarget"]["WANT_MOTION_GRAPHICS"] == \
            "pre_presentation_capture.WANT_MOTION_GRAPHICS"
        assert self.upsell["storeTarget"][
            "MOTION_GRAPHICS_DECLINED_REASON"] == \
            "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON"
        assert self.upsell["waiver_field_mapping"]["motion_graphics"] == {
            "toggle": "want_motion_graphics",
            "reason": "motion_graphics_declined_reason"}

    def test_upsell_order_lockstep_no_collision(self):
        orders = sorted(q["order"] for q in self.upsell["questions"])
        assert orders == [7.6, 7.61, 7.7, 7.71, 7.8, 7.81, 7.9, 7.91]

    def test_question_copy_never_promises_powerpoint_playback(self):
        # R1's binding copy correction: landed doctrine holds PowerPoint
        # playback UNVERIFIED; the question may promise only that the
        # pieces are embedded in the deck file with the designed slide
        # as their still.
        for bank in (self.upsell, self.deck):
            for q in bank["questions"]:
                if q["id"] != "want_motion_graphics":
                    continue
                text = (q.get("prompt", "") + " " + q.get("help", ""))
                assert "play inside PowerPoint" not in text
                assert "plays inside PowerPoint" not in text
                assert "embedded in the deck file" in text

    def test_deck_bank_store_target_and_waiver_mapping(self):
        assert self.deck["storeTarget"]["WANT_MOTION_GRAPHICS"] == \
            "pre_presentation_capture.WANT_MOTION_GRAPHICS"
        assert self.deck["storeTarget"][
            "MOTION_GRAPHICS_DECLINED_REASON"] == \
            "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON"
        assert self.deck["waiver_field_mapping"]["motion_graphics"] == {
            "toggle": "want_motion_graphics",
            "reason": "motion_graphics_declined_reason"}

    def test_deck_bank_subfields_ride_the_existing_turns(self):
        # FIX 30 pattern (the email precedent): no new turn; the pair
        # rides growth_assets (order 20) and decline_context (order 22).
        growth = self.dq["growth_assets"]
        assert growth["subfields"]["want_motion_graphics"] == {
            "storeOn": "WANT_MOTION_GRAPHICS", "boolish": True,
            "default": "no"}
        decline = self.dq["decline_context"]
        sub = decline["subfields"]["motion_graphics_declined_reason"]
        assert sub["storeOn"] == "MOTION_GRAPHICS_DECLINED_REASON"
        assert sub["conditional_on"] == {"id": "want_motion_graphics",
                                         "equals": "no"}
        # The merged interview still has exactly 23 turns.
        merged = [q for q in self.deck["questions"]
                  if q.get("kind") == "merged"]
        assert len(merged) == 23

    def test_deck_bank_alias_rows(self):
        toggle = self.dq["want_motion_graphics"]
        assert toggle["order"] == 20.04
        assert toggle["alias"] is True
        assert toggle["storeOn"] == "WANT_MOTION_GRAPHICS"
        assert toggle["required"] is True and toggle["block_gate"] is True
        assert toggle["default"] == "no"
        reason = self.dq["motion_graphics_declined_reason"]
        assert reason["order"] == 22.08
        assert reason["alias"] is True
        assert reason["storeOn"] == "MOTION_GRAPHICS_DECLINED_REASON"
        assert reason["conditional_on"] == {"id": "want_motion_graphics",
                                            "equals": "no"}
        assert "default" not in reason

    def test_fields_contract_rows(self):
        contract = json.loads(CONTRACT_JSON.read_text(encoding="utf-8"))
        fields = {f["id"]: f for f in contract["fields"]}
        assert fields["want_motion_graphics"]["canonical_path"] == \
            "pre_presentation_capture.WANT_MOTION_GRAPHICS"
        reason = fields["motion_graphics_declined_reason"]
        assert reason["canonical_path"] == \
            "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON"
        # The generated projection drops conditional_on for EVERY field
        # (the email pair's row proves it); the condition lives in the
        # .js source of truth, asserted there.
        js = (APP / "schema" / "intake_fields.js").read_text(
            encoding="utf-8")
        assert 'conditional_on: { id: "want_motion_graphics", ' \
               'equals: "no" }' in js
        assert "pre_presentation_capture.WANT_MOTION_GRAPHICS" in \
            contract["required_fields"]
        # The generated UI question set (pages/questions.json) DOES
        # carry the condition and the canonical storeOn for the
        # reason (merged at assembly prep from the contribution
        # lineage's suite, which pinned the generated set directly).
        questions = json.loads(
            (APP / "pages" / "questions.json").read_text(
                encoding="utf-8"))
        qlist = questions["questions"] if isinstance(
            questions, dict) else questions
        q = next(q for q in qlist
                 if q["id"] == "motion_graphics_declined_reason")
        assert q["conditional_on"] == {
            "id": "want_motion_graphics", "equals": "no"}
        assert q["storeOn"] == \
            "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON"
        # The conditional reason is NOT a flat-required field (the email
        # precedent's discipline): completeness for it is enforced by
        # the interview definitions and the fail-closed consumers.
        assert "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON" \
            not in contract["required_fields"]

    def test_writer_mirror_carries_the_pair(self):
        # Merged at assembly prep from the contribution lineage's
        # suite: the writer's own maps are pinned directly, not only
        # through behavior (the PRES-006 pin binds the canonical maps
        # to the generated projection; ID_TO_FIELD and
        # PRE_CAPTURE_FIELDS are the flat-answers routing half).
        iw = _writer()
        assert iw.ID_TO_FIELD["want_motion_graphics"] == \
            "WANT_MOTION_GRAPHICS"
        assert iw.ID_TO_FIELD["motion_graphics_declined_reason"] == \
            "MOTION_GRAPHICS_DECLINED_REASON"
        assert "WANT_MOTION_GRAPHICS" in iw.PRE_CAPTURE_FIELDS
        assert "MOTION_GRAPHICS_DECLINED_REASON" in \
            iw.PRE_CAPTURE_FIELDS
        assert iw.CANONICAL_FIELD_PATHS["want_motion_graphics"] == \
            "pre_presentation_capture.WANT_MOTION_GRAPHICS"
        assert iw.CANONICAL_FIELD_PATHS[
            "motion_graphics_declined_reason"] == \
            "pre_presentation_capture.MOTION_GRAPHICS_DECLINED_REASON"
        assert "pre_presentation_capture.WANT_MOTION_GRAPHICS" in \
            iw.REQUIRED_CANONICAL_FIELDS


# ===========================================================================
# T2 -- decline with verbatim reason, recorded as the motion_graphics waiver
# ===========================================================================

class TestMotionDeclineWithReason:
    def test_resolve_value_reads_the_capture_toggle(self):
        assert defers.resolve_intake_value(
            NESTED_DECLINE, "want_motion_graphics") == "no"

    def test_election_from_capture_is_a_recorded_decline(self):
        out = pm.election_for_run(Path("."), intake=NESTED_DECLINE)
        assert out == {"elected": False, "value": "no",
                       "source": "intake_capture"}

    def test_election_from_waiver_only_is_the_waiver(self):
        # The recorded waiver ALONE is the decline (defers resolution
        # step 4): this is the arm that proves the decline is recorded
        # AS the motion_graphics waiver, not merely as a toggle value.
        out = pm.election_for_run(Path("."), intake=WAIVER_ONLY_DECLINE)
        assert out == {"elected": False, "value": "no", "source": "waiver"}

    def test_waiver_quote_and_capture_reason_are_the_same_bytes(self):
        assert NESTED_DECLINE["waivers"][0]["client_request_quote"] == \
            REASON
        assert NESTED_DECLINE["pre_presentation_capture"][
            "MOTION_GRAPHICS_DECLINED_REASON"] == REASON

    def test_plan_on_declined_still_run_plans_nothing(self, tmp_path):
        run_dir = _still_run(tmp_path, NESTED_DECLINE)
        record, motion_media = build_deck.plan_motion_media(
            run_dir, _slides_of(run_dir))
        assert motion_media == {}
        assert record["election"] == {
            "field": "want_motion_graphics", "value": "no",
            "elected": False, "source": "intake_capture"}
        assert record["slides"] == []
        on_disk = json.loads(
            (run_dir / "working" / "checkpoints" / "motion.json")
            .read_text(encoding="utf-8"))
        assert on_disk["election"] == record["election"]
        manifest = json.loads(
            (run_dir / "working" / "checkpoints"
             / "slide_media_manifest.json").read_text(encoding="utf-8"))
        assert manifest["slides"] == []

    def test_declared_media_on_declined_run_degrades_not_elected(
            self, tmp_path):
        from test_mg036_motion_integration import media_block

        run_dir = _still_run(tmp_path, NESTED_DECLINE)
        slides = _slides_of(run_dir)
        slides[0]["media"] = media_block(1)
        record, motion_media = build_deck.plan_motion_media(
            run_dir, slides)
        assert motion_media == {}
        entry = record["slides"][0]
        assert entry["status"] == "degraded"
        assert entry["reason_code"] == pm.MOTION_NOT_ELECTED
        assert "_embed" not in entry


# ===========================================================================
# T3 -- decline without reason blocks completion (definition, writer,
# projection, and seam layers; the driver --complete refusal itself is a
# parent-verification integration step, per build/B34-TESTPLAN.md)
# ===========================================================================

class TestMotionDeclineWithoutReason:
    def test_writer_never_fabricates_a_reason(self):
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(want_motion_graphics="no")},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "no"
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in pre
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in \
            intake.get("deck_brief", {})
        # The writer never authors a waiver.
        assert "waivers" not in intake

    def test_projection_of_missing_or_blank_reason_is_missing(self):
        # A MISSING reason projects as missing: nothing downstream can
        # mistake it for a recorded waiver.
        assert resolve_intake._resolve_upsell_capture(
            {}, BARE_DECLINE) == {"WANT_MOTION_GRAPHICS": "no"}
        # A BLANK (whitespace-only) reason projects verbatim, exactly
        # like the VSL pair's blank reason (parity, verified against
        # the sibling): the projection is a carrier, not a judge. The
        # fail-closed judgment lives at the waiver seam (asserted in
        # test_reasonless_decline_is_never_a_waiver_at_the_seam: a
        # blank capture reason never becomes a waiver record).
        blank_vsl = {"pre_presentation_capture": {
            "WANT_VSL_PAGE": "no", "VSL_PAGE_DECLINED_REASON": "   "}}
        assert resolve_intake._resolve_upsell_capture(
            {}, BLANK_REASON) == {
                "WANT_MOTION_GRAPHICS": "no",
                "MOTION_GRAPHICS_DECLINED_REASON": "   "}
        assert resolve_intake._resolve_upsell_capture(
            {}, blank_vsl) == {
                "WANT_VSL_PAGE": "no",
                "VSL_PAGE_DECLINED_REASON": "   "}

    def test_reasonless_decline_is_never_a_waiver_at_the_seam(self):
        out = pm.election_for_run(Path("."), intake=BARE_DECLINE)
        assert out["source"] == "intake_capture"  # answered, not waived
        assert "motion_graphics" not in defers._waiver_rules(BARE_DECLINE)
        assert "motion_graphics" not in defers._waiver_rules(BLANK_REASON)


# ===========================================================================
# T12 -- hosted-path parity (writer landing + projection parity)
# ===========================================================================

class TestMotionHostedParity:
    def test_writer_landing_no_with_reason_byte_for_byte(self):
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(
                want_motion_graphics="no",
                motion_graphics_declined_reason=REASON)},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "no"
        assert pre["MOTION_GRAPHICS_DECLINED_REASON"] == REASON
        assert "WANT_MOTION_GRAPHICS" not in intake.get("deck_brief", {})
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in \
            intake.get("deck_brief", {})

    def test_writer_landing_yes_carries_no_reason(self):
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(want_motion_graphics="yes")},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "yes"
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in pre

    def test_projection_nested_shape_matches_vsl_pair(self):
        intake = {"pre_presentation_capture": {
            "WANT_MOTION_GRAPHICS": "no",
            "MOTION_GRAPHICS_DECLINED_REASON": REASON,
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": VSL_REASON}}
        out = resolve_intake._resolve_upsell_capture({}, intake)
        assert out == {
            "WANT_MOTION_GRAPHICS": "no",
            "MOTION_GRAPHICS_DECLINED_REASON": REASON,
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": VSL_REASON}

    def test_projection_flat_shape_is_identical(self):
        flat = {"WANT_MOTION_GRAPHICS": "no",
                "MOTION_GRAPHICS_DECLINED_REASON": REASON,
                "WANT_VSL_PAGE": "no",
                "VSL_PAGE_DECLINED_REASON": VSL_REASON}
        nested = {"pre_presentation_capture": dict(flat)}
        assert resolve_intake._resolve_upsell_capture({}, flat) == \
            resolve_intake._resolve_upsell_capture({}, nested)

    def test_projection_both_ledger_dialects(self):
        entries_a = {
            "want_motion_graphics": {"value": "no"},
            "motion_graphics_declined_reason": {"value": REASON},
            "want_vsl_page": {"value": "no"},
            "vsl_page_declined_reason": {"value": VSL_REASON}}
        entries_b = {
            key: {"answer": val["value"], "normalized": val["value"]}
            for key, val in entries_a.items()}
        expected = {
            "WANT_MOTION_GRAPHICS": "no",
            "MOTION_GRAPHICS_DECLINED_REASON": REASON,
            "WANT_VSL_PAGE": "no",
            "VSL_PAGE_DECLINED_REASON": VSL_REASON}
        assert resolve_intake._resolve_upsell_capture(
            entries_a, {}) == expected
        assert resolve_intake._resolve_upsell_capture(
            entries_b, {}) == expected

    def test_writer_completeness_names_the_missing_toggle(self, tmp_path):
        iw = _writer()
        answers = _hosted_answers()
        del answers["want_motion_graphics"]
        intake = iw.assemble_intake({"answers": answers}, run_id="RUNTEST")
        with pytest.raises(iw.IntakeIncompleteError) as excinfo:
            iw.write_intake_file(tmp_path / "run", intake)
        assert "pre_presentation_capture.WANT_MOTION_GRAPHICS" in \
            str(excinfo.value)


# ===========================================================================
# The three-state election fixture proof (B34-TESTPLAN Section 7)
# ===========================================================================

class TestThreeStateElectionProof:
    def test_state_1_yes(self, tmp_path):
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(want_motion_graphics="yes")},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "yes"
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in pre
        assert "waivers" not in intake

        chat = {"pre_presentation_capture": {"WANT_MOTION_GRAPHICS": "yes"}}
        assert resolve_intake._resolve_upsell_capture({}, chat) == \
            {"WANT_MOTION_GRAPHICS": "yes"}
        assert resolve_intake._resolve_upsell_capture(
            {}, {"WANT_MOTION_GRAPHICS": "yes"}) == \
            {"WANT_MOTION_GRAPHICS": "yes"}
        assert resolve_intake._resolve_upsell_capture(
            {"want_motion_graphics": {"value": "yes"}}, {}) == \
            {"WANT_MOTION_GRAPHICS": "yes"}

        assert defers.resolve_intake_value(
            chat, "want_motion_graphics") == "yes"
        assert pm.election_for_run(Path("."), intake=chat) == {
            "elected": True, "value": "yes", "source": "intake_capture"}
        assert "motion_graphics" not in defers._waiver_rules(chat)

        run_dir = _still_run(tmp_path, chat)
        record, _media = build_deck.plan_motion_media(
            run_dir, _slides_of(run_dir))
        assert record["election"] == {
            "field": "want_motion_graphics", "value": "yes",
            "elected": True, "source": "intake_capture"}
        assert record["slides"] == []

    def test_state_2_no_with_verbatim_reason(self, tmp_path):
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(
                want_motion_graphics="no",
                motion_graphics_declined_reason=REASON)},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "no"
        assert pre["MOTION_GRAPHICS_DECLINED_REASON"] == REASON

        expected = {"WANT_MOTION_GRAPHICS": "no",
                    "MOTION_GRAPHICS_DECLINED_REASON": REASON}
        assert resolve_intake._resolve_upsell_capture(
            {}, NESTED_DECLINE) == expected
        flat = {"WANT_MOTION_GRAPHICS": "no",
                "MOTION_GRAPHICS_DECLINED_REASON": REASON}
        assert resolve_intake._resolve_upsell_capture({}, flat) == expected
        entries_a = {"want_motion_graphics": {"value": "no"},
                     "motion_graphics_declined_reason": {"value": REASON}}
        entries_b = {
            key: {"answer": val["value"], "normalized": val["value"]}
            for key, val in entries_a.items()}
        assert resolve_intake._resolve_upsell_capture(
            entries_a, {}) == expected
        assert resolve_intake._resolve_upsell_capture(
            entries_b, {}) == expected

        assert defers.resolve_intake_value(
            NESTED_DECLINE, "want_motion_graphics") == "no"
        assert pm.election_for_run(Path("."), intake=NESTED_DECLINE) == {
            "elected": False, "value": "no", "source": "intake_capture"}
        assert pm.election_for_run(
            Path("."), intake=WAIVER_ONLY_DECLINE)["source"] == "waiver"
        rules = defers._waiver_rules(NESTED_DECLINE)
        assert "motion_graphics" in rules

        run_dir = _still_run(tmp_path, NESTED_DECLINE)
        record, motion_media = build_deck.plan_motion_media(
            run_dir, _slides_of(run_dir))
        assert motion_media == {}
        assert record["election"]["elected"] is False
        assert record["slides"] == []

    def test_state_3_no_without_reason_is_blocked_not_waived(self):
        # Definition layer: TestMotionQuestionDefinitions above (the
        # block_gate + conditional_on + no-default shape that blocks
        # --complete). Writer, projection, and seam layers:
        iw = _writer()
        intake = iw.assemble_intake(
            {"answers": _hosted_answers(want_motion_graphics="no")},
            run_id="RUNTEST")
        pre = intake["pre_presentation_capture"]
        assert pre["WANT_MOTION_GRAPHICS"] == "no"
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in pre
        assert "MOTION_GRAPHICS_DECLINED_REASON" not in \
            intake.get("deck_brief", {})
        assert "waivers" not in intake

        assert resolve_intake._resolve_upsell_capture(
            {}, BARE_DECLINE) == {"WANT_MOTION_GRAPHICS": "no"}
        # Blank projects verbatim (VSL parity) but is never a waiver:
        # the seam asserts that below and in the T3 class.
        out = pm.election_for_run(Path("."), intake=BARE_DECLINE)
        assert out["source"] == "intake_capture"
        assert "motion_graphics" not in defers._waiver_rules(BARE_DECLINE)
        assert "motion_graphics" not in defers._waiver_rules(BLANK_REASON)

    def test_default_no_is_not_a_waiver(self):
        # Default, capture, and waiver are three different records of
        # "no"; only the waiver is a client decline with a reason.
        assert pm.election_for_run(Path("."), intake={}) == {
            "elected": False, "value": "no", "source": "default"}

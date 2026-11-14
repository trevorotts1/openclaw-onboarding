"""PD-013 -- a short interview: pace first, models out of the client's way.

Acceptance rows A1 to A5 from 01-BUILD-SPEC.md, section PD-013:

A1  a simulated QUICK from-scratch pitch deck that accepts defaults is asked
    14 or fewer questions including `defaults_review`.
A2  the first three ids asked are presentation_type, pitch_included,
    standard_mode.
A3  none of workhorse_model, reasoning_model, qc_model, thinking_mode,
    run_mode, deepseek_variant, openrouter_model is asked unless
    build_settings_choice was answered "customize".
A4  IN-DEPTH still reaches every field.
A5  every existing bank test still passes (the suite run, quoted in the
    build report).

The QUICK walk drives the real deck-intake-driver.py through --next/--answer,
never a reimplementation of it.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
DEPT = SCRIPTS.parent
INTAKE = DEPT / "intake"
DRIVER = SCRIPTS / "deck-intake-driver.py"
BANK = INTAKE / "deck-intake-questions.json"
TEMPLATES = SCRIPTS / "conversation_templates.json"

sys.path.insert(0, str(INTAKE))
import question_sequence as qs  # noqa: E402

MODEL_IDS = sorted(qs.MODEL_CHOICE_FIELDS)


def _schema():
    return json.loads(BANK.read_text(encoding="utf-8"))


def _questions(schema=None):
    return qs.atomic_questions(schema or _schema())


# ---------------------------------------------------------------------------
# the walk -- the real driver, one answer per turn
# ---------------------------------------------------------------------------
class Walk:
    def __init__(self, tmp_path):
        self.run = tmp_path / "run"
        self.run.mkdir(parents=True)
        self.env = dict(os.environ)
        self.env.update(
            PRESENTATION_RESOURCE_PROFILE_DIR=str(tmp_path / "profile"),
            PRESENTATION_CAPACITY_CONFIG_DIR=str(tmp_path / "profile"),
            PRESENTATION_PROVIDER_PROBES="0",
            PRESENTATION_MODEL_FRESHNESS="0")
        self.ids = []

    def call(self, *args):
        proc = subprocess.run(
            [sys.executable, str(DRIVER), "--run-dir", str(self.run), *args],
            env=self.env, capture_output=True, text=True, timeout=90)
        return proc, (json.loads(proc.stdout) if proc.stdout.strip() else {})

    def reply(self, q):
        """A deterministic answer for one emitted question."""
        if q.get("question_id") == "defaults_review":
            return "good"
        if q.get("allowed_values"):
            return str(q["allowed_values"][0])
        if q.get("default") is not None:
            return str(q["default"])
        if q.get("kind") == "integer":
            return "30"
        return "sample answer"

    def walk(self, presentation_type="from_scratch", pitch="yes",
             mode="QUICK", build_settings=None, stop_after=None,
             stop_before=None):
        _, q = self.call("--next")
        guard = 0
        while q.get("question_id"):
            guard += 1
            assert guard < 200, f"walk did not terminate: {self.ids}"
            qid = q["question_id"]
            self.ids.append(qid)
            if stop_after and len(self.ids) >= stop_after:
                return self.ids
            if stop_before and qid == stop_before:
                return self.ids
            if qid == "presentation_type":
                text = presentation_type
            elif qid == "pitch_included":
                text = pitch
            elif qid == "standard_mode":
                text = mode
            elif qid == "build_settings_choice" and build_settings:
                text = build_settings
            else:
                text = self.reply(q)
            args = ["--answer", qid, text]
            if qid == "defaults_review":
                args += ["--owner-msg-id", "walk-1"]
            proc, q = self.call(*args)
            assert proc.returncode == 0, f"{qid}: {proc.stdout}{proc.stderr}"
            assert "error" not in q, f"{qid}: {q.get('error')}"
            if q.get("status") == "complete":
                break
        return self.ids

    def ledger(self):
        return json.loads(
            (self.run / "working/interview/intake_ledger.json").read_text())["entries"]


# ---------------------------------------------------------------------------
# the bank's own contract
# ---------------------------------------------------------------------------
def test_every_answer_field_declares_its_depth():
    schema = _schema()
    declared = {}
    for row in schema["questions"]:
        for field, ann in (row.get("subfields") or {}).items():
            if ann.get("derived"):
                continue
            assert "depth" in ann, f"{field} has no depth"
            declared[field] = ann["depth"]
    assert {f for f, d in declared.items() if d == "both"} == set(qs.BOTH_DEPTH)
    assert all(d in ("both", "in-depth") for d in declared.values())
    # the projected question carries the bank's depth, unchanged
    for q in _questions(schema):
        assert qs.depth_of(q) == declared[q["answer_field"]]


def test_the_both_set_is_the_spec_list():
    both = set(qs.BOTH_DEPTH)
    for field in ("presentation_type", "pitch_included", "signature_source",
                  "extracted_substance", "recipient_name", "audience",
                  "representation_mix", "grounded_content", "goal",
                  "cta_action", "transformation_promise", "duration_min",
                  "deadline", "standard_mode", "offer_name", "offer_stack",
                  "final_price", "price_mode", "proof_assets",
                  "delivery_destinations", "want_teleprompter",
                  "want_speech_script", "want_audio_deliverable",
                  "want_ghl_upload", "want_sales_checkout"):
        assert field in both, field
    assert len(both) == 25


def test_session_budget_is_measured_and_not_typed():
    schema = _schema()
    measured = qs.measure_budget(schema)
    assert schema["session_budget"]["max_turns"] == measured["max_turns"]
    assert schema["session_budget"]["quick_max_turns"] == measured["quick_max_turns"]
    # the IN-DEPTH ceiling is the projected sequence: no skipped field
    assert measured["max_turns"] == len(_questions(schema))


def test_the_pace_question_is_asked_third_and_says_the_approved_words():
    by_id = {q["id"]: q for q in _questions()}
    assert by_id["standard_mode"]["order"] == 0.6
    prompt = by_id["standard_mode"]["prompt"]
    assert prompt.startswith("Do you want the QUICK version")
    assert "about 12 questions" in prompt
    assert "about 30 questions" in prompt
    assert prompt.endswith("You can switch any time.")
    assert prompt.count("?") == 1


# ---------------------------------------------------------------------------
# A2 -- the first three ids
# ---------------------------------------------------------------------------
def test_a2_the_first_three_ids_are_type_pitch_and_pace(tmp_path):
    ids = Walk(tmp_path).walk(stop_after=3)
    assert ids == ["presentation_type", "pitch_included", "standard_mode"]


# ---------------------------------------------------------------------------
# A1 -- the QUICK count
# ---------------------------------------------------------------------------
def test_a1_quick_from_scratch_deck_asks_at_most_fourteen(tmp_path):
    """A from-scratch deck with no pitch: 14 questions including the review."""
    walk = Walk(tmp_path)
    ids = walk.walk(pitch="no")
    print("A1 ids:", ids)
    assert ids[-1] == "defaults_review"
    assert len(ids) <= 14, ids
    proc, done = walk.call("--complete")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert done["status"] == "complete"


def test_a1_quick_pitch_deck_is_measured(tmp_path):
    """A from-scratch PITCH deck: nineteen questions including the review.

    The spec's A1 ceiling is 14. Under the spec's own 25-field "both" set a
    deck that carries a pitch cannot reach it: offer_name, offer_stack,
    price_mode, final_price and proof_assets are both-depth fields with no
    bank default, so a QUICK interview must ask them. 14 + 5 = 19. This test
    pins the real number so the gap is visible and cannot drift silently.
    """
    ids = Walk(tmp_path).walk(pitch="yes")
    print("A1 pitch ids:", ids)
    assert ids[-1] == "defaults_review"
    assert len(ids) == 19, ids
    assert {"offer_name", "offer_stack", "price_mode", "final_price",
            "proof_assets"} <= set(ids)


# ---------------------------------------------------------------------------
# A3 -- the model questions stay shut
# ---------------------------------------------------------------------------
def test_a3_quick_never_asks_a_model_question(tmp_path):
    ids = Walk(tmp_path).walk(pitch="yes")
    assert not (set(MODEL_IDS) & set(ids)), ids
    assert "build_settings_choice" not in ids  # answered by its own default


def test_a3_model_questions_open_only_on_customize():
    questions = {q["id"]: q for q in _questions()}
    quick_ok = {"standard_mode": "QUICK", "build_settings_choice": "ok"}
    quick_custom = {"standard_mode": "QUICK", "build_settings_choice": "customize"}
    depth_ok = {"standard_mode": "IN-DEPTH", "build_settings_choice": "ok"}
    depth_custom = {"standard_mode": "IN-DEPTH", "build_settings_choice": "customize"}
    for qid in MODEL_IDS:
        assert qs.quick_skip(questions[qid], quick_ok)[0] is True
        assert qs.quick_skip(questions[qid], depth_ok)[0] is False  # depth says ask
        assert qs.quick_skip(questions[qid], depth_custom)[0] is False
        assert qs.quick_skip(questions[qid], quick_custom)[0] is False
    # the ask_if gate is what actually holds them shut in IN-DEPTH
    for qid in MODEL_IDS:
        assert questions[qid]["ask_if"] == {
            "question_id": "build_settings_choice", "equals": "customize"}


def test_a3_the_plan_tier_keeps_its_own_rule():
    questions = {q["id"]: q for q in _questions()}
    quick_ok = {"standard_mode": "QUICK", "build_settings_choice": "ok"}
    assert qs.quick_skip(questions["provider_plan"], quick_ok)[0] is False


# ---------------------------------------------------------------------------
# A4 -- IN-DEPTH still reaches every field
# ---------------------------------------------------------------------------
def test_a4_in_depth_skips_nothing_on_depth():
    depth = {"standard_mode": "IN-DEPTH", "build_settings_choice": "customize"}
    skipped = [q["id"] for q in _questions() if qs.quick_skip(q, depth)[0]]
    assert skipped == [], skipped


def test_a4_in_depth_walk_reaches_every_non_model_field(tmp_path):
    walk = Walk(tmp_path)
    ids = walk.walk(mode="IN-DEPTH")          # build_settings defaults to "ok"
    assert "defaults_review" not in ids        # the review is a QUICK turn
    fields = {q["id"] for q in _questions()}
    missed = fields - set(ids) - set(MODEL_IDS)
    # conditional rows are legitimately skipped for this fixture
    conditional = {"extracted_substance", "recipient_name", "signature_source",
                   "event_price", "price_anchor", "vip_price", "vip_spots",
                   "audience_composition_note", "target_feeling",
                   "time_to_result", "primary_objection", "hook_seed", "tone",
                   "client_notes", "named_methodology", "want_audio_demo",
                   "speech_speed_preference"}
    conditional |= {f for f in fields if f.endswith("_declined_reason")}
    assert missed <= conditional, sorted(missed - conditional)


# ---------------------------------------------------------------------------
# A1's review turn and the acceptance stamp PD-004b reads
# ---------------------------------------------------------------------------
def test_defaults_review_lists_the_assumed_values_and_stamps_the_acceptance(tmp_path):
    walk = Walk(tmp_path)
    ids = walk.walk(pitch="no")
    assert ids[-1] == "defaults_review"
    entries = walk.ledger()
    defaulted = {k for k, v in entries.items()
                 if isinstance(v, dict) and v.get("defaulted")}
    assert defaulted, "no defaulted entries recorded"
    assert entries["defaults_review"]["accepted"] is True
    stamped = {k for k in defaulted
               if entries[k].get("default_accepted_msg_id") == "walk-1"}
    assert stamped == defaulted, sorted(defaulted - stamped)


def test_defaults_review_refuses_an_acceptance_with_no_owner_message_id(tmp_path):
    other = Walk(tmp_path)
    other.walk(pitch="no", stop_before="defaults_review")
    proc, out = other.call("--answer", "defaults_review", "good")
    assert proc.returncode != 0
    assert "owner-msg-id" in out.get("error", "")
    entries = other.ledger()
    assert "default_accepted_msg_id" not in json.dumps(entries)


# ---------------------------------------------------------------------------
# the front-door qualification
# ---------------------------------------------------------------------------
def test_frontdoor_asks_one_qualification_question_and_keeps_the_old_wording():
    front = json.loads(TEMPLATES.read_text(encoding="utf-8"))["frontdoor"]
    assert front["qualification"] == [
        "You are here to have a presentation built, and it is OK for me to "
        "message you here about it — is that right?"]
    legacy = front["qualification_legacy"]
    assert len(legacy) >= 2
    assert any("you are here because you would like a presentation" in s
               for s in legacy)
    assert any("is it all right for us to keep this conversation going" in s
               for s in legacy)

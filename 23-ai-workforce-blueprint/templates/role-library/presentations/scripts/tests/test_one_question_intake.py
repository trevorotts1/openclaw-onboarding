"""One actual decision per turn, including resumed and hosted interviews."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
DEPT = SCRIPTS.parent
ROOT = DEPT.parents[3]
APP = DEPT / "intake/interview-app"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


DRIVER = load("atomic_driver", SCRIPTS / "deck-intake-driver.py")
BUILDER = load("atomic_payload", APP / "payload/build_questions_payload.py")
SCANNER = load("atomic_scanner", ROOT / "51-signature-presentation/scripts/intake_trace_check.py")


@pytest.fixture
def interview(tmp_path):
    env = dict(os.environ)
    env.update(PRESENTATION_RESOURCE_PROFILE_DIR=str(tmp_path / "profile"),
               PRESENTATION_CAPACITY_CONFIG_DIR=str(tmp_path / "profile"),
               PRESENTATION_PROVIDER_PROBES="0", PRESENTATION_MODEL_FRESHNESS="0")
    run = tmp_path / "run"
    run.mkdir()

    def call(*args, entry=SCRIPTS / "deck-intake-driver.py", ok=True):
        result = subprocess.run([sys.executable, str(entry), "--run-dir", str(run), *args],
                                env=env, capture_output=True, text=True, timeout=20)
        if ok:
            assert result.returncode == 0, result.stdout + result.stderr
        return result, json.loads(result.stdout)

    return run, call


def ledger(run):
    return json.loads((run / "working/interview/intake_ledger.json").read_text())["entries"]


def test_every_asked_field_has_its_own_prompt_even_with_old_rollback_flag(monkeypatch):
    schema = DRIVER.load_question_schema()
    monkeypatch.setenv("PRESENTATION_INTAKE_V2", "0")
    questions = DRIVER.get_questions(schema)
    assert len(questions) == schema["session_budget"]["max_turns"]
    assert len({q["id"] for q in questions}) == len(questions)
    fields = {k for q in schema["questions"] for k, a in (q.get("subfields") or {}).items()
              if not a.get("derived")}
    assert {q["answer_field"] for q in questions} == fields
    for q in questions:
        assert q["kind"] != "merged"
        assert list(q["subfields"]) == [q["answer_field"]]
        assert q["prompt"].count("?") <= 1


@pytest.mark.parametrize("entry", [SCRIPTS / "deck-intake-driver.py", ROOT / "23-ai-workforce-blueprint/scripts/deck-intake-driver.py"])
def test_type_and_pitch_are_separate_questions(interview, entry):
    run, call = interview
    _, first = call("--next", entry=entry)
    assert first["question_id"] == "presentation_type"
    _, second = call("--answer", "presentation_type", "from_scratch", entry=entry)
    assert second["question_id"] == "pitch_included"
    assert "pitch_included" not in ledger(run)
    _, third = call("--answer", "pitch_included", "no", entry=entry)
    # PD-013: the pace question is asked third, right after the deck type and
    # the pitch decision, so the client picks QUICK before anything optional.
    assert third["question_id"] == "standard_mode"
    assert ledger(run)["pitch_included"]["value"] is False
    _, same = call("--next", entry=entry)
    assert same["question_id"] == third["question_id"]
    _, fourth = call("--answer", "standard_mode", "IN-DEPTH", entry=entry)
    assert fourth["question_id"] == "audience"


def test_individual_answers_do_not_invent_sibling_answers(interview):
    run, call = interview
    call("--answer", "audience", "New business owners")
    entries = ledger(run)
    assert entries["AUDIENCE"]["value"] == "New business owners"
    assert "representation_mix" not in entries
    assert "audience_composition_note" not in entries
    call("--answer", "want_motion_graphics", "no")
    assert "want_email_sequences" not in ledger(run)
    # PD-014: declining an opt-in that DEFAULTS to "no" is not a waiver, so
    # this reason is optional and never blocks the gate. An empty reply is
    # accepted and stores only the bank's own "no note." sentinel -- a blank
    # never becomes an invented reason written on the client's behalf.
    call("--answer", "motion_graphics_declined_reason", "")
    assert ledger(run)["MOTION_GRAPHICS_DECLINED_REASON"]["value"] == "no note."
    reason = "Our own team handles ALL motion."
    call("--answer", "motion_graphics_declined_reason", reason)
    assert ledger(run)["MOTION_GRAPHICS_DECLINED_REASON"]["value"] == reason


def test_existing_merged_session_resumes_with_only_missing_fields(interview):
    run, call = interview
    call("--answer", "deck_type_source", "presentation_type: content_personal; pitch_included: no; extracted_substance: Build trust")
    _, next_q = call("--next")
    # PD-013: the pace question sits at 0.6, ahead of every field question.
    assert next_q["question_id"] == "standard_mode"
    _, after_pace = call("--answer", "standard_mode", "IN-DEPTH")
    assert after_pace["question_id"] == "recipient_name"
    call("--answer", "recipient_name", "Jordan")
    assert ledger(run)["extracted_substance"]["value"] == "Build trust"
    assert ledger(run)["RECIPIENT_NAME"]["value"] == "Jordan"


def test_derivations_and_consent_remain_typed(interview):
    run, call = interview
    call("--answer", "duration_min", "45 minutes")
    assert ledger(run)["DURATION_MIN"]["value"] == 45
    assert ledger(run)["SLIDE_COUNT"]["value"] == "36"
    call("--answer", "event_price", "free")
    assert ledger(run)["ACCESS_FREE"]["value"] is True
    call("--answer", "style_pick_auto", "no")
    assert ledger(run)["STYLE_PICK_AUTO"]["value"] is False
    for key in ("want_teleprompter", "want_speech_script", "want_audio_deliverable"):
        call("--answer", key, "no")
    assert ledger(run)["DELIVERABLE_SET"]["value"] == "deck-only"


def test_blank_optional_reply_preserves_an_existing_run_mode(interview):
    run, call = interview
    call("--answer", "run_mode", "ultra")
    call("--answer", "run_mode", "")
    assert ledger(run)["RUN_MODE"]["value"] == "ultra"


def test_conditionals_are_individual_and_still_apply():
    by_id = {q["id"]: q for q in DRIVER.get_questions(DRIVER.load_question_schema())}
    for values, expected in [({"presentation_type": "from_scratch"}, False),
                             ({"presentation_type": "content_personal"}, True)]:
        assert DRIVER.should_ask(by_id["recipient_name"], values)[0] is expected
    assert not DRIVER.should_ask(by_id["vip_price"], {"vip_tier": False})[0]
    assert DRIVER.should_ask(by_id["vip_price"], {"vip_tier": True})[0]
    assert not DRIVER.should_ask(by_id["motion_graphics_declined_reason"], {"want_motion_graphics": "yes"})[0]
    assert DRIVER.should_ask(by_id["motion_graphics_declined_reason"], {"want_motion_graphics": "no"})[0]


def test_hosted_embedded_and_signature_prompts_are_single_questions():
    specs, _, targets = BUILDER.load_specs(ROOT)
    payload = BUILDER.build_curated_payload("atomic", specs, BUILDER.DEFAULT_CURATED, targets)
    embedded = json.loads((APP / "pages/questions.json").read_text())
    signature = BUILDER.build_signature_payload("atomic", BUILDER.load_signature_spec(ROOT))
    for source in (payload, embedded, signature):
        for q in source["questions"]:
            assert q["prompt"].count("?") <= 1, q
            assert q["kind"] != "merged"
            assert "subfields" not in q
    assert (APP / "pages/index.html").read_bytes() == (APP / "deployed-r2/public/index.html").read_bytes()


def test_custom_hosted_question_list_cannot_request_a_merged_parent():
    specs, _, targets = BUILDER.load_specs(ROOT)
    with pytest.raises(ValueError, match="one answer field"):
        BUILDER.build_curated_payload("atomic", specs, ["goal_cta_feeling"], targets)


def test_scanner_rejects_compound_bank_prompts_and_accepts_atomic_questions():
    schema = DRIVER.load_question_schema()
    bank = SCANNER.load_bank_questions()
    opener = [{"role": "assistant", "text": "QUICK or IN-DEPTH?"},
              {"role": "owner", "text": "quick"}]
    for q in schema["questions"]:
        captures = [a for a in (q.get("subfields") or {}).values() if not a.get("derived")]
        if len(captures) > 1:
            result = SCANNER.scan_transcript(opener + [{"role": "assistant", "text": q["prompt"]}], bank)
            assert not result["pass"], q["id"]
            assert any(v["reason"] == "COMPOUND-BANK-PROMPT" for v in result["violations"])
    for q in DRIVER.get_questions(schema):
        result = SCANNER.scan_transcript(opener + [{"role": "assistant", "text": q["prompt"]}], bank)
        assert result["pass"], (q["id"], result)

    prompt = DRIVER.get_questions(schema)[0]["prompt"]
    assert not SCANNER.scan_transcript(opener + [
        {"role": "assistant", "text": prompt + " Which date works?"}], bank)["pass"]
    assert not SCANNER.scan_transcript(opener + [
        {"role": "assistant", "text": prompt},
        {"role": "assistant", "text": "What is the purpose of this presentation?"}], bank)["pass"]


def test_real_cli_walk_completes_and_proves_a_single_question_transcript(interview):
    run, call = interview
    values = {"presentation_type": "from_scratch", "pitch_included": "yes",
              "duration_min": "45", "provider_plan": "use conservative default",
              "standard_mode": "QUICK", "run_mode": "standard",
              "event_price": "free", "price_mode": "straight", "final_price": "$97",
              "vip_tier": "no", "style_pick_auto": "no"}
    seen = []
    _, q = call("--next")
    for _ in range(80):
        if q.get("status") == "complete":
            break
        qid = q["question_id"]
        assert qid not in seen, (qid, seen)
        seen.append(qid)
        assert q["prompt"].count("?") <= 1
        if qid == "defaults_review":
            # PD-013: a QUICK interview ends with ONE review turn listing the
            # defaults. Accept it the same way the branch's own PD-013 walk
            # does (an acceptance needs the client's message id); the guard
            # still proves no FIELD question is ever asked twice.
            _, q = call("--answer", qid, "good", "--owner-msg-id", "walk-1")
            continue
        if qid in values:
            answer = values[qid]
        elif qid.startswith("want_") or qid == "dark_ok" or qid == "logo_on_slides":
            answer = "no"
        elif qid in ("workhorse_model", "reasoning_model", "qc_model", "thinking_mode", "deepseek_variant", "openrouter_model", "ollama_plan"):
            answer = ""
        elif q.get("allowed_values"):
            answer = q["allowed_values"][0]
        else:
            answer = "Client supplied " + qid
        _, q = call("--answer", qid, answer)
    assert q["status"] == "complete", q
    _, complete = call("--complete")
    assert complete["status"] == "complete"
    trace = json.loads((run / "working/interview/intake_transcript.json").read_text())
    bank = SCANNER.load_bank_questions()
    assert SCANNER.scan_transcript(trace["turns"], bank)["pass"]
    entries = ledger(run)
    for field in ("AUDIENCE", "GOAL", "CTA_ACTION", "DURATION_MIN"):
        assert entries[field]["validated"] is True
    # PD-013: a QUICK interview asks only what it truly needs. Everything the
    # bank already answers is recorded as a DEFAULT -- visible in the review
    # turn's list and stamped by the client's acceptance -- never silently
    # dropped and never asked one question at a time.
    assert entries["WANT_MOTION_GRAPHICS"]["defaulted"] is True
    assert entries["WANT_MOTION_GRAPHICS"]["default_accepted_msg_id"] == "walk-1"
    assert entries["defaults_review"]["accepted"] is True
    # ... and an in-depth field with no bank default is left unrecorded
    # rather than invented (PD-014: no "why not?" for a default-no opt-in).
    assert "MOTION_GRAPHICS_DECLINED_REASON" not in entries

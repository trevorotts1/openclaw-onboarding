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
        # PD-004b: a test may flip the intake-provenance switch on the real
        # process by setting it in os.environ (the driver reads it per run).
        call_env = dict(env)
        if "PRESENTATION_INTAKE_PROVENANCE" in os.environ:
            call_env["PRESENTATION_INTAKE_PROVENANCE"] = \
                os.environ["PRESENTATION_INTAKE_PROVENANCE"]
        result = subprocess.run([sys.executable, str(entry), "--run-dir", str(run), *args],
                                env=call_env, capture_output=True, text=True, timeout=20)
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
    assert third["question_id"] == "audience"
    assert ledger(run)["pitch_included"]["value"] is False
    _, same = call("--next", entry=entry)
    assert same["question_id"] == third["question_id"]


def test_individual_answers_do_not_invent_sibling_answers(interview):
    run, call = interview
    call("--answer", "audience", "New business owners")
    entries = ledger(run)
    assert entries["AUDIENCE"]["value"] == "New business owners"
    assert "representation_mix" not in entries
    assert "audience_composition_note" not in entries
    call("--answer", "want_motion_graphics", "no")
    assert "want_email_sequences" not in ledger(run)
    # PD-901: declining an opt-in that defaults to "no" is not a waiver, so
    # this reason is optional -- a blank answer is accepted. It must never
    # invent a reason: the bank's documented "no note" sentinel is the only
    # value a blank may leave behind.
    accepted, _ = call("--answer", "motion_graphics_declined_reason", "", ok=False)
    assert accepted.returncode == 0
    assert ledger(run).get("MOTION_GRAPHICS_DECLINED_REASON", {}).get("value", "") in ("", "no note.")
    reason = "Our own team handles ALL motion."
    call("--answer", "motion_graphics_declined_reason", reason)
    assert ledger(run)["MOTION_GRAPHICS_DECLINED_REASON"]["value"] == reason


def test_existing_merged_session_resumes_with_only_missing_fields(interview):
    run, call = interview
    call("--answer", "deck_type_source", "presentation_type: content_personal; pitch_included: no; extracted_substance: Build trust")
    _, next_q = call("--next")
    assert next_q["question_id"] == "recipient_name"
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


WALK_VALUES = {"presentation_type": "from_scratch", "pitch_included": "yes",
               "duration_min": "45", "provider_plan": "use conservative default",
               "standard_mode": "QUICK", "run_mode": "standard",
               "event_price": "free", "price_mode": "straight", "final_price": "$97",
               "vip_tier": "no", "style_pick_auto": "no"}


def _walk_to_complete(call, values):
    """Answer the live turn gate until every question is answered; return the
    last (complete) question payload."""
    seen = []
    _, q = call("--next")
    for _ in range(80):
        if q.get("status") == "complete":
            break
        qid = q["question_id"]
        assert qid not in seen, (qid, seen)
        seen.append(qid)
        assert q["prompt"].count("?") <= 1
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
    return q


def test_real_cli_walk_completes_and_proves_a_single_question_transcript(interview, monkeypatch):
    # PD-004c: enforce is now the default, and this walk records no client
    # message ids -- it exercises the walk, so it asks for warn explicitly.
    monkeypatch.setenv("PRESENTATION_INTAKE_PROVENANCE", "warn")
    run, call = interview
    _walk_to_complete(call, WALK_VALUES)
    _, complete = call("--complete")
    assert complete["status"] == "complete"
    trace = json.loads((run / "working/interview/intake_transcript.json").read_text())
    bank = SCANNER.load_bank_questions()
    assert SCANNER.scan_transcript(trace["turns"], bank)["pass"]
    entries = ledger(run)
    for field in ("AUDIENCE", "GOAL", "CTA_ACTION", "DURATION_MIN", "WANT_MOTION_GRAPHICS", "MOTION_GRAPHICS_DECLINED_REASON"):
        assert entries[field]["validated"] is True

def test_complete_under_enforce_refuses_an_interview_with_no_message_ids(interview, monkeypatch):
    """PD-004b: the same real walk, under ENFORCE, cannot complete -- none of
    its answers names the client message it came from."""
    monkeypatch.setenv("PRESENTATION_INTAKE_PROVENANCE", "enforce")
    run, call = interview
    _walk_to_complete(call, WALK_VALUES)
    result, payload = call("--complete", ok=False)
    assert result.returncode == 6, result.stdout + result.stderr
    assert payload["status"] == "unproven", result.stdout
    assert payload["mode"] == "enforce", result.stdout
    assert payload["unproven_questions"], result.stdout
    assert json.loads((run / "working/interview/intake_ledger.json").read_text()).get("complete") is not True

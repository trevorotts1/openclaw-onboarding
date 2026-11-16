"""END008 — the operator contract carries the complete answer/provenance set.

The merged units PD-013 (QUICK defaults review), PD-004b (provenance proof) and
PD-913 (turn gate) make a minimal operator contract unable to complete under
``enforce``. The standards-preserving answer is a COMPLETE contract: every turn
is answered explicitly, or a QUICK default is accepted through the client's real
inbound message. This file pins both the compatible positive path and the
refusals that must stay refusals.

Positive path: a QUICK contract that answers every turn explicitly records every
scalar answer as ``source: operator-contract`` with the receipt digest; no
default is recorded, so no ``defaults_review`` turn exists.

Negative controls (the important half):
  * a missing turn is refused and ``intake.json`` is never written;
  * omitted defaults with no signed acceptance are refused;
  * a named acceptance that is not already the client's inbound message is
    refused, and the bridge never writes that evidence itself;
  * a tampered receipt still exits 6.
"""
import importlib.util
import json
import os
import pathlib
import subprocess
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
PRESENTATIONS = HERE.parent.parent.parent
DRIVER = PRESENTATIONS / "scripts" / "deck-intake-driver.py"
BRIDGE = APP / "bridge" / "intake_bridge.py"

spec = importlib.util.spec_from_file_location("end008_bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(bridge)

RECEIPT_HMAC = "end008-test-receipt-hmac"
TASK_ID = "d4e05a2f-f83b-4e87-aabe-d5e31c43867b"
EXECUTION_ID = "b4cc51f0-0abf-420a-bed2-9cfbb8650e83"
CHAT_ID = "end008-requester"

# Every turn a QUICK run asks, answered explicitly so PD-013 records no default
# and therefore emits no defaults_review turn. Values are non-commercial facts
# from the authenticated informational-demo contract, not invented claims.
COMPLETE_ANSWERS = {
    "audience_recipient_cast": (
        "recipient_name: Internal team demonstration; "
        "audience: Internal team demonstration; "
        "audience_composition_note: Internal team demonstration; "
        "representation_mix: Internal team demonstration"),
    "deadline_and_notes": (
        "deadline: Internal team demonstration; "
        "client_notes: Internal team demonstration"),
    "goal_cta_feeling": (
        "goal: Internal team demonstration; "
        "cta_action: Internal team demonstration; "
        "target_feeling: Internal team demonstration"),
    "grounding_and_method": (
        "grounded_content: Internal team demonstration; "
        "named_methodology: Internal team demonstration"),
    "interview_depth": "standard_mode: QUICK",
    "pitch_included": "no",
    "promise_objection_timing": (
        "transformation_promise: Internal team demonstration; "
        "primary_objection: Internal team demonstration; "
        "time_to_result: Internal team demonstration"),
    "standard_mode": "QUICK",
    "style_and_brand": (
        "style_source: create-new; style_prefs: fresh clean-white; "
        "brand_primary: Internal team demonstration; dark_ok: False; "
        "style_pick_auto: yes"),
    "visual_mix": "visual_mix: mix",
    "logo_placement": "logo_on_slides: False",
}

# The three turns PD-013 defaults when they are absent. Used by the default
# acceptance/refusal controls.
DEFAULTABLE_TURNS = ("style_and_brand", "visual_mix", "logo_placement")


def contract(*, answers=None, acceptance=None):
    value = {
        "version": 1, "source": "operator-delegated",
        "task_id": TASK_ID, "execution_id": EXECUTION_ID,
        "title": "Internal workflow demonstration",
        "presentation_type": "from_scratch", "run_mode": "standard",
        "workhorse_model": "deepseek-flash@deepseek-direct",
        "slide_count": 8, "pitch_included": False,
        "want_teleprompter": "yes", "want_speech_script": "yes",
        "want_audio_deliverable": "yes", "want_audio_demo": True,
        "want_ghl_upload": "yes", "want_sales_checkout": "no",
        "want_vsl_page": "no",
        "deliverable_set": "PPTX, PDF",
        "delivery_destinations": ["PPTX", "PDF"],
        "interview_depth": "quick",
        "answers": dict(COMPLETE_ANSWERS if answers is None else answers),
    }
    if acceptance is not None:
        value["default_acceptance"] = acceptance
    return value


def _run_env(monkeypatch):
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHAT_ID", CHAT_ID)
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHANNEL", "operator-delegated")
    monkeypatch.setenv("PRESENTATION_INTAKE_PROVENANCE", "enforce")


def _run_dir(tmp_path, name="run"):
    return tmp_path / name


def _write_inbound(rd, *, msg_id="msg-1", chat_id=CHAT_ID, text="good"):
    path = pathlib.Path(rd) / "working" / "interview" / "inbound_messages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"msg_id": msg_id, "chat_id": chat_id,
                                "text": text, "received_at": "2026-11-15T00:00:00Z"}) + "\n",
                    encoding="utf-8")
    return path


def _ledger(rd):
    path = pathlib.Path(rd) / "working" / "interview" / "intake_ledger.json"
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _entries(rd):
    return _ledger(rd)["entries"]


def test_positive_complete_contract_completes_and_every_answer_is_operator_contract(
        tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = _run_dir(tmp_path)
    report = bridge.drive_operator_contract(contract(), rd, driver_path=DRIVER,
                                            launch=False, receipt_hmac=RECEIPT_HMAC)
    assert report["driver_complete"] is True
    receipt = rd / "working" / "interview" / "operator_contract.json"
    receipt_sha = bridge.hashlib.sha256(receipt.read_bytes()).hexdigest()
    entries = _entries(rd)
    defaulted = [k for k, v in entries.items()
                 if isinstance(v, dict) and v.get("defaulted")]
    assert not defaulted, f"a complete contract must record no defaults: {defaulted}"
    assert "defaults_review" not in entries
    scalars = {k: v for k, v in entries.items()
               if isinstance(v, dict) and not v.get("skipped")
               and not isinstance(v.get("value"), (dict, list))}
    assert scalars, "the run recorded no scalar answers"
    for key, entry in scalars.items():
        assert entry.get("source") == "operator-contract", (key, entry)
        assert entry.get("contract_sha256") == receipt_sha, (key, entry)
    # The complete path needs no client acceptance message, so the bridge must
    # not have written one.
    assert not (rd / "working" / "interview" / "inbound_messages.jsonl").exists()


def test_negative_missing_required_turn_is_refused_and_writes_no_intake(
        tmp_path, monkeypatch):
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    answers.pop("goal_cta_feeling")
    rd = _run_dir(tmp_path)
    with pytest.raises(RuntimeError) as refused:
        bridge.drive_operator_contract(contract(answers=answers), rd,
                                       driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    message = str(refused.value)
    assert "incomplete" in message, message
    assert "missing turns" in message, message
    assert _ledger(rd).get("status") != "complete"
    assert not _ledger(rd).get("complete")


def test_negative_omitted_defaults_without_acceptance_are_refused(
        tmp_path, monkeypatch):
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    rd = _run_dir(tmp_path)
    with pytest.raises(RuntimeError) as refused:
        bridge.drive_operator_contract(contract(answers=answers), rd,
                                       driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    message = str(refused.value)
    assert "default_acceptance" in message, message
    assert "fabricate" in message, message
    assert _ledger(rd).get("status") != "complete"
    assert not (rd / "working" / "interview" / "inbound_messages.jsonl").exists()


def test_negative_named_acceptance_without_inbound_evidence_is_refused(
        tmp_path, monkeypatch):
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    acceptance = {"msg_id": "msg-1", "chat_id": CHAT_ID, "text": "good"}
    rd = _run_dir(tmp_path)
    with pytest.raises(ValueError) as refused:
        bridge.drive_operator_contract(contract(answers=answers, acceptance=acceptance),
                                       rd, driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    assert "not present in this run's inbound evidence" in str(refused.value)
    assert not (rd / "working" / "interview" / "inbound_messages.jsonl").exists()


def test_negative_acceptance_text_mismatch_is_refused(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    rd = _run_dir(tmp_path)
    path = _write_inbound(rd, text="change the price instead")
    before = path.read_bytes()
    acceptance = {"msg_id": "msg-1", "chat_id": CHAT_ID, "text": "good"}
    with pytest.raises(ValueError) as refused:
        bridge.drive_operator_contract(contract(answers=answers, acceptance=acceptance),
                                       rd, driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    assert "text does not match" in str(refused.value)
    assert path.read_bytes() == before, "the bridge must never rewrite inbound evidence"


def test_negative_acceptance_chat_mismatch_is_refused(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    rd = _run_dir(tmp_path)
    path = _write_inbound(rd, chat_id="intruder")
    before = path.read_bytes()
    acceptance = {"msg_id": "msg-1", "chat_id": CHAT_ID, "text": "good"}
    with pytest.raises(ValueError) as refused:
        bridge.drive_operator_contract(contract(answers=answers, acceptance=acceptance),
                                       rd, driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    assert "chat does not match" in str(refused.value)
    assert path.read_bytes() == before, "the bridge must never rewrite inbound evidence"


def test_positive_quick_defaults_complete_through_the_real_acceptance_message(
        tmp_path, monkeypatch):
    """#3774: one real acceptance proves every default AND completes the run.

    The review row reuses the acceptance id PD-004b already credits to the
    defaulted rows; the bridge marks only that action row `derived` so the
    reuse rule does not refuse it. Every defaulted answer keeps the real id.
    """
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    rd = _run_dir(tmp_path)
    path = _write_inbound(rd, text="good")
    before = path.read_bytes()
    acceptance = {"msg_id": "msg-1", "chat_id": CHAT_ID, "text": "good"}
    report = bridge.drive_operator_contract(contract(answers=answers, acceptance=acceptance),
                                            rd, driver_path=DRIVER, launch=False,
                                            receipt_hmac=RECEIPT_HMAC)
    assert report["driver_complete"] is True
    assert path.read_bytes() == before, "the bridge must never rewrite inbound evidence"
    entries = _entries(rd)
    defaulted = {k: v for k, v in entries.items()
                 if isinstance(v, dict) and v.get("defaulted")}
    assert defaulted, "the QUICK contract must have recorded defaults"
    for key, entry in defaulted.items():
        assert entry.get("default_accepted_msg_id") == "msg-1", (key, entry)
        assert entry.get("source") != "derived", (key, entry)
    review = entries["defaults_review"]
    assert review["accepted"] is True and review["owner_msg_id"] == "msg-1"
    assert review["source"] == "derived"


def test_negative_invalid_interview_depth_is_refused_before_any_write(
        tmp_path, monkeypatch):
    _run_env(monkeypatch)
    value = contract()
    value["interview_depth"] = "sideways"
    rd = _run_dir(tmp_path)
    with pytest.raises(ValueError, match="interview_depth must be quick or in_depth"):
        bridge.drive_operator_contract(value, rd, driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
    assert not rd.exists()


def test_positive_contract_answer_wins_over_a_synthesized_value(tmp_path, monkeypatch):
    """A supplied canonical answer is never overwritten by a synthesized one."""
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    answers["core_deliverables"] = "deliverable_set: operator chose workbook only"
    rd = _run_dir(tmp_path)
    bridge.drive_operator_contract(contract(answers=answers), rd, driver_path=DRIVER,
                                   launch=False, receipt_hmac=RECEIPT_HMAC)
    assert "operator chose workbook only" in str(_entries(rd)["core_deliverables"]["value"])


def test_negative_acceptance_with_matching_evidence_is_never_fabricated(
        tmp_path, monkeypatch):
    """The bridge hands the real id to the driver; it never writes the evidence.

    With the merged PD-013/PD-004b driver, the single acceptance message proves
    both the defaults and the review record, and the driver's reuse rule refuses
    the review record that reuses it unless the bridge marks that action row
    `derived` (#3774). This test pins the bridge's honest half: no evidence
    written, the real id passed, and any refusal is the driver's own.
    """
    _run_env(monkeypatch)
    answers = dict(COMPLETE_ANSWERS)
    for turn in DEFAULTABLE_TURNS:
        answers.pop(turn)
    rd = _run_dir(tmp_path)
    path = _write_inbound(rd, text="good")
    before = path.read_bytes()
    acceptance = {"msg_id": "msg-1", "chat_id": CHAT_ID, "text": "good"}
    try:
        bridge.drive_operator_contract(contract(answers=answers, acceptance=acceptance),
                                       rd, driver_path=DRIVER, launch=False,
                                       receipt_hmac=RECEIPT_HMAC)
        completed = True
    except RuntimeError as exc:
        completed = False
        assert "already used by" in str(exc), str(exc)
    assert path.read_bytes() == before, "the bridge must never rewrite inbound evidence"
    entries = _entries(rd)
    if completed:
        for key, entry in entries.items():
            if isinstance(entry, dict) and entry.get("defaulted"):
                assert entry.get("default_accepted_msg_id") == "msg-1", (key, entry)


def test_negative_tampered_receipt_still_exits_six(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = _run_dir(tmp_path)
    real_run = bridge.subprocess.run

    def tampering(argv, *args, **kwargs):
        if isinstance(argv, list) and "--complete" in argv:
            receipt = rd / "working" / "interview" / "operator_contract.json"
            raw = receipt.read_bytes()
            receipt.write_bytes(raw[:-1] + (b" " if raw[-1:] != b" " else b"\n"))
        return real_run(argv, *args, **kwargs)

    monkeypatch.setattr(bridge.subprocess, "run", tampering)
    with pytest.raises(RuntimeError) as refused:
        bridge.drive_operator_contract(contract(), rd, driver_path=DRIVER,
                                       launch=False, receipt_hmac=RECEIPT_HMAC)
    assert "driver completion refused" in str(refused.value)
    proc = real_run([sys.executable, str(DRIVER), "--run-dir", str(rd), "--complete"],
                    capture_output=True, text=True, check=False)
    assert proc.returncode == 6, f"rc={proc.returncode} out={proc.stdout[-400:]}"
    payload = json.loads(proc.stdout)
    assert "the operator contract receipt no longer matches this answer" in " ".join(
        payload["findings"])

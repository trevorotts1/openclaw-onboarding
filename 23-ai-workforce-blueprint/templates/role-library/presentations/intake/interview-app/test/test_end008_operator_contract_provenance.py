"""END008 — the operator contract transports a COMPLETE answer set and its
real default provenance through the actual sender/consumer schema.

Authority:

  * PD-013  `default_accepted_msg_id` is stamped on every defaulted entry from
            the owner message that accepted the review turn.
  * PD-004b third provenance class: `--operator-contract` proves answers the
            signed contract carries; a name alone is never proof.
  * PD-107  A2: with the proof set to `enforce`, an operator-contract run
            completes; A3: one changed receipt byte exits 6.

The bridge never invents a pace answer, a client answer, or an acceptance.
The positive rows therefore supply (a) the PD-013 pace decision on the
contract and (b) either a complete canonical answer set or a real inbound
message that the channel recorded. The negative rows prove each missing or
false provenance is refused.
"""
import importlib.util
import json
import pathlib
import sys

import pytest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
PRESENTATIONS = HERE.parent.parent.parent
BRIDGE = APP / "bridge" / "intake_bridge.py"
DRIVER = PRESENTATIONS / "scripts" / "deck-intake-driver.py"

spec = importlib.util.spec_from_file_location("end008_bridge", BRIDGE)
bridge = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(bridge)

CHAT = "operator-test-route"
RECEIPT = "end008-test-receipt"

# The QUICK interview asks every both-depth field with no bank default. These
# are explicit operator answers (operator-contract provenance), so a complete
# contract produces ZERO synthesized defaults and needs no acceptance message.
COMPLETE_QUICK_ANSWERS = {
    "audience": "general informational audience learning how to use the Presentation Department",
    "transformation_promise": "No commercial transformation promise",
    "cta_action": "Request or use the Presentation Department",
    "tone": "teacher",
    "representation_mix": "no people",
    "grounded_content": "no named method",
    "goal": "Explain the Presentation Department",
    "deadline": "no deadline",
    "style_source": "create-new",
    "style_prefs": "fresh clean-white",
    "dark_ok": "yes",
    "visual_mix": "mix",
    "logo_on_slides": "yes",
}

# The same contract minus the style/visual fields, so the driver records them
# as QUICK defaults (10 rows) that a real acceptance message must prove.
DEFAULTING_QUICK_ANSWERS = {
    key: value for key, value in COMPLETE_QUICK_ANSWERS.items()
    if key not in ("style_source", "style_prefs", "dark_ok", "visual_mix", "logo_on_slides")
}


def _contract(answers, *, depth="quick", acceptance=True):
    value = {
        "version": 1, "source": "operator-delegated",
        "task_id": "d4e05a2f-f83b-4e87-aabe-d5e31c43867b",
        "execution_id": "b4cc51f0-0abf-420a-bed2-9cfbb8650e83",
        "title": "How the Presentation Department Works",
        "presentation_type": "from_scratch", "run_mode": "ultra",
        "workhorse_model": "deepseek-flash@deepseek-direct",
        "slide_count": 8, "pitch_included": False,
        "want_teleprompter": "yes", "want_speech_script": "yes",
        "want_audio_deliverable": "yes", "want_audio_demo": True,
        "want_ghl_upload": "yes", "want_sales_checkout": "yes", "want_vsl_page": "yes",
        "deliverable_set": "PPTX, PDF, presenter guide, workbook, fillable workbook, infographic",
        "delivery_destinations": ["PPTX", "PDF", "presenter guide", "workbook",
                                  "fillable workbook", "infographic"],
        "answers": dict(answers),
    }
    if depth is not None:
        value["interview_depth"] = depth
    if acceptance:
        value["default_acceptance"] = {
            "msg_id": "tg-msg-9001", "chat_id": CHAT, "text": "good"}
    return value


def _write_channel_evidence(rd, *, chat=CHAT, text="good"):
    """The channel that received the client's message records it first."""
    path = rd / "working" / "interview" / "inbound_messages.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "msg_id": "tg-msg-9001", "chat_id": chat, "text": text,
        "received_at": "2026-11-15T00:00:00Z"}) + "\n", encoding="utf-8")


def _ledger(rd):
    return json.loads((rd / "working" / "interview" / "intake_ledger.json").read_text())


def _run_env(monkeypatch):
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHAT_ID", CHAT)
    monkeypatch.setenv("PRESENTATION_REQUESTER_CHANNEL", "operator-delegated")
    monkeypatch.setenv("PRESENTATION_INTAKE_PROVENANCE", "enforce")


def test_complete_canonical_contract_completes_under_enforce(tmp_path, monkeypatch):
    """Full canonical answers ride the contract; zero defaults, no acceptance."""
    _run_env(monkeypatch)
    rd = tmp_path / "complete"
    report = bridge.drive_operator_contract(
        _contract(COMPLETE_QUICK_ANSWERS, acceptance=False), rd,
        driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)
    assert report["driver_complete"] is True
    entries = _ledger(rd)["entries"]
    defaulted = [k for k, v in entries.items() if isinstance(v, dict) and v.get("defaulted")]
    assert defaulted == [], "a complete contract must not synthesize defaults"
    # Every canonical answer the contract supplied is proven by the receipt.
    receipt = rd / "working" / "interview" / "operator_contract.json"
    import hashlib
    sha = hashlib.sha256(receipt.read_bytes()).hexdigest()
    for qid in ("representation_mix", "goal", "deadline", "grounded_content"):
        assert entries[qid]["source"] == "operator-contract"
        assert entries[qid]["contract_sha256"] == sha


def test_quick_defaults_are_proven_by_the_real_acceptance_message(tmp_path, monkeypatch):
    """PD-013 + PD-004b: the defaulted rows carry default_accepted_msg_id."""
    _run_env(monkeypatch)
    rd = tmp_path / "defaults-ok"
    rd.mkdir(parents=True)
    _write_channel_evidence(rd)
    report = bridge.drive_operator_contract(
        _contract(DEFAULTING_QUICK_ANSWERS), rd,
        driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)
    assert report["driver_complete"] is True
    entries = _ledger(rd)["entries"]
    defaulted = [(k, v) for k, v in entries.items() if isinstance(v, dict) and v.get("defaulted")]
    assert defaulted, "the QUICK contract must have recorded defaults"
    assert all(v.get("default_accepted_msg_id") == "tg-msg-9001" for _k, v in defaulted)


def test_defaults_without_evidence_are_refused(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = tmp_path / "defaults-no-evidence"
    rd.mkdir(parents=True)
    with pytest.raises(ValueError, match="not present in this run's inbound evidence"):
        bridge.drive_operator_contract(
            _contract(DEFAULTING_QUICK_ANSWERS), rd,
            driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)


def test_defaults_with_a_different_chat_are_refused(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = tmp_path / "defaults-wrong-chat"
    rd.mkdir(parents=True)
    _write_channel_evidence(rd, chat="intruder")
    with pytest.raises(ValueError, match="chat does not match"):
        bridge.drive_operator_contract(
            _contract(DEFAULTING_QUICK_ANSWERS), rd,
            driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)


def test_defaults_with_a_different_text_are_refused(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = tmp_path / "defaults-wrong-text"
    rd.mkdir(parents=True)
    _write_channel_evidence(rd, text="change the colors")
    with pytest.raises(ValueError, match="text does not match"):
        bridge.drive_operator_contract(
            _contract(DEFAULTING_QUICK_ANSWERS), rd,
            driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)


def test_defaults_with_no_acceptance_contract_are_refused(tmp_path, monkeypatch):
    """Evidence exists, but the signed contract never accepted any default."""
    _run_env(monkeypatch)
    rd = tmp_path / "defaults-no-acceptance"
    rd.mkdir(parents=True)
    _write_channel_evidence(rd)
    with pytest.raises(RuntimeError, match="refusing to fabricate"):
        bridge.drive_operator_contract(
            _contract(DEFAULTING_QUICK_ANSWERS, acceptance=False), rd,
            driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)


def test_invalid_interview_depth_is_refused_before_any_write(tmp_path, monkeypatch):
    _run_env(monkeypatch)
    rd = tmp_path / "bad-depth"
    with pytest.raises(ValueError, match="interview_depth must be quick or in_depth"):
        bridge.drive_operator_contract(
            _contract(COMPLETE_QUICK_ANSWERS, depth="sideways"), rd,
            driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)
    assert not rd.exists()


def test_contract_answer_wins_over_a_synthesized_value(tmp_path, monkeypatch):
    """A supplied canonical answer is never overwritten by a synthesized one."""
    _run_env(monkeypatch)
    answers = dict(COMPLETE_QUICK_ANSWERS)
    answers["core_deliverables"] = "deliverable_set: operator chose workbook only"
    rd = tmp_path / "override"
    bridge.drive_operator_contract(
        _contract(answers, acceptance=False), rd,
        driver_path=DRIVER, launch=False, receipt_hmac=RECEIPT)
    entries = _ledger(rd)["entries"]
    assert "operator chose workbook only" in str(entries["core_deliverables"]["value"])

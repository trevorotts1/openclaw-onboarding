#!/usr/bin/env python3
"""PD-004c -- the interview proof refuses by default (warn is opt-in).

Acceptance rows A1 and A2 of unit PD-004c (01-BUILD-SPEC.md, lane FL02), plus
the fail-closed rule PD-004b's review left with this unit: a deployment that
does not carry intake_provenance.py must REFUSE, never warn and continue.

Driven at the subprocess level against the REAL deck-intake-driver.py; no
renderer, no network, no live service, no paid call.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
DRIVER = SCRIPTS / "deck-intake-driver.py"

LEDGER = Path("working") / "interview" / "intake_ledger.json"
FINDINGS = Path("working") / "interview" / "provenance_findings.json"
RECEIPT = Path("working") / "interview" / "operator_contract.json"
INBOUND = Path("working") / "interview" / "inbound_messages.jsonl"

#: AUTH004 synthetic secret. Test-only; the real operator secret is never
#: read, printed, or needed. The driver reads WEBHOOK_SECRET exactly as the
#: bridge does, so the fixture supplies this one value for both sign+verify.
_SYNTHETIC_SECRET = "auth004-synthetic-test-secret-only"
REQUESTER_CHAT = "111"


def _canonical_bytes(contract: dict) -> bytes:
    return json.dumps(contract, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def _sign(contract: dict) -> str:
    return hmac.new(_SYNTHETIC_SECRET.encode("utf-8"),
                    _canonical_bytes(contract), hashlib.sha256).hexdigest()


def _contract(*, acceptance=None) -> dict:
    """A minimal dict the bridge verifier accepts. Not a full production
    contract; the driver only checks HMAC + default_acceptance presence."""
    c = {"task_id": "auth004-task", "execution_id": "auth004-exec",
         "title": "Auth004 fixture"}
    if acceptance is not None:
        c["default_acceptance"] = acceptance
    return c


def _write_signed_receipt(run_dir: Path, contract: dict | None = None,
                            *, hmac_value: str | None = None) -> dict:
    """Write working/interview/operator_contract.json as a signed envelope."""
    contract = contract if contract is not None else _contract()
    envelope = {"receipt_version": 1, "contract": contract,
                "receipt_hmac": _sign(contract) if hmac_value is None else hmac_value}
    receipt = run_dir / RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps(envelope), encoding="utf-8")
    return envelope


def _write_inbound(run_dir: Path, *, msg_id: str = "msg-1",
                     chat_id: str = REQUESTER_CHAT, text: str = "good") -> None:
    path = run_dir / INBOUND
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"msg_id": msg_id, "chat_id": chat_id,
                                "text": text, "received_at": "2026-11-15T00:00:00+00:00"}) + "\n",
                    encoding="utf-8")

EIGHT = {
    "audience": "New business owners",
    "goal": "Book paid calls",
    "cta_action": "Book a call",
    "transformation_promise": "From invisible to booked",
    "primary_objection": "No time",
    "tone": "Warm and direct",
    "deadline": "December 15",
    "recipient_name": "Jordan",
}
BASE = {"presentation_type": "from_scratch"}
ALL = {**BASE, **EIGHT, "resource_plan": "use conservative default"}

# A box that does not carry the proof module: the import must fail.
_NO_MODULE = textwrap.dedent('''
    import runpy, sys

    class _Block:
        def find_spec(self, name, path=None, target=None):
            if name == "intake_provenance" or name.startswith("intake_provenance."):
                raise ModuleNotFoundError(f"No module named {name!r}")
            return None

    sys.meta_path.insert(0, _Block())
    driver, run_dir = sys.argv[1:3]
    sys.argv = [driver, "--run-dir", run_dir] + sys.argv[3:]
    runpy.run_path(driver, run_name="__main__")
''')


def _env(tmp_path: Path, mode: str | None) -> dict:
    env = dict(os.environ)
    env.update({
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
        "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-004c-test-key-material",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-004c-test-1",
        "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
        "PRESENTATION_REQUESTER_CHAT_ID": "111",
        "PRESENTATION_REQUESTER_CHANNEL": "telegram",
    })
    if mode is None:
        env.pop("PRESENTATION_INTAKE_PROVENANCE", None)
    else:
        env["PRESENTATION_INTAKE_PROVENANCE"] = mode
    # AUTH004: the verifier reads WEBHOOK_SECRET exactly as intake_bridge
    # does. Tests supply only the synthetic value above. Never a live secret.
    env["WEBHOOK_SECRET"] = _SYNTHETIC_SECRET
    return env


@pytest.fixture
def run(tmp_path):
    # A locked BYOK provider, so the model-plan turns can be answered without
    # inventing a provider the client never configured. Test data only.
    profile_dir = tmp_path / "profile"
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "resource_profile.json").write_text(json.dumps({
        ".schema_version": 1,
        "profile_version": "20160101T000000Z-pd004c",
        "updated_at": "2016-01-01T00:00:00+00:00",
        "created_at": "2016-01-01T00:00:00+00:00",
        "providers": {"deepseek-direct": {
            "provider": "deepseek-direct", "plan_tier": None,
            "concurrency_ceiling": "UNBOUNDED", "ceiling_source": "declared",
            "consented": True, "wired_models": ["deepseek-flash", "deepseek-pro"],
            "detected": True, "plan_known": True, "locked": True}},
        "creative_prefs": {}, "consent": {"add_models": True},
    }), encoding="utf-8")

    def build(mode=None, without_module=False):
        run_dir = tmp_path / f"run-{mode}-{without_module}"
        run_dir.mkdir()
        wrapper = tmp_path / f"driver-{mode}-{without_module}.py"
        if without_module:
            wrapper.write_text(_NO_MODULE, encoding="utf-8")
            command = [sys.executable, str(wrapper), str(DRIVER), str(run_dir)]
        else:
            command = [sys.executable, str(DRIVER), "--run-dir", str(run_dir)]
        env = _env(tmp_path, mode)

        def call(*args):
            return subprocess.run(command + list(args), capture_output=True,
                                  text=True, timeout=180, env=env)

        return run_dir, call

    return build


#: PD-913 makes `--complete` refuse while any turn the interview still owes is
#: unanswered, so a fixture that stops after nine answers never reaches the
#: provenance gate this file is about. These are the remaining required turns,
#: with a value the bank accepts for each. They are fixture data, not claims
#: under test: the rows here judge the provenance gate, never the answers.
_WALK_VALUES = {
    "pitch_included": "no",
    "audience_composition_note": "A room of new business owners",
    "representation_mix": "no people",
    "grounded_content": "The owner's own words in this interview",
    "target_feeling": "Ready to book",
    "primary_objection": "No time",
    "hook_seed": "Invisible to booked in one call",
    "duration_min": "30",
    "deadline": "December 15",
    "standard_mode": "QUICK",
    "workhorse_model": "deepseek-flash@deepseek-direct",
    "reasoning_model": "deepseek-pro@deepseek-direct",
    "qc_model": "deepseek-pro@deepseek-direct",
    "thinking_mode": "high",
    "run_mode": "ultra",
    "deepseek_variant": "flash",
    "openrouter_model": "openrouter/auto",
    "ollama_plan": "$20/month",
    "style_source": "auto",
    "style_prefs": "clean and direct",
    "dark_ok": "no",
    "style_pick_auto": "yes",
    "visual_mix": "mix",
    "logo_on_slides": "no",
    "want_teleprompter": "yes",
    "want_speech_script": "yes",
    "want_audio_deliverable": "yes",
    "delivery_destinations": "PPTX, PDF, presenter guide",
    "want_ghl_upload": "yes",
    "want_sales_checkout": "yes",
    "want_vsl_page": "yes",
    "want_email_sequences": "yes",
    "want_motion_graphics": "yes",
    "want_audio_demo": "yes",
    "speech_speed_preference": "default",
    #: PD-013's QUICK review turn: the client accepts the whole defaults list.
    #: Fixture data, not a claim under test -- the rows judge the provenance
    #: gate, never the answer text.
    "defaults_review": "good",
}

def _walk(call, *, operator_contract: bool = False) -> None:
    """Answer whatever the turn gate asks next until the interview is done.

    PD-013: the QUICK ``defaults_review`` turn only clears on a plain
    acceptance, and PD-004b refuses an acceptance that names no client
    message. Non-operator-contract walks therefore accept with a real
    ``--owner-msg-id`` (the message id is test data, never a claim under
    test); operator-contract walks accept on the signed receipt path.
    """
    extra = ["--operator-contract"] if operator_contract else []
    for _ in range(80):
        step = call("--next")
        assert step.returncode == 0, step.stdout + step.stderr
        asked = _payload(step)
        if asked.get("status") == "complete":
            return
        qid = asked.get("question_id")
        assert qid, asked
        text = _WALK_VALUES.get(qid, "A plain answer to this question")
        # PD-013 defaults_review needs an owner id or the contract path --
        # extra already carries --operator-contract when requested.
        review_extra = extra + (["--owner-msg-id", "defaults-review-1"]
                                if not operator_contract and qid == "defaults_review" else [])
        out = call("--answer", qid, text, *review_extra)
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
    raise AssertionError("the interview turn gate never reported complete")

def _answer_all(call, *, operator_contract: bool = False) -> None:
    extra = ["--operator-contract"] if operator_contract else []
    for qid, text in ALL.items():
        out = call("--answer", qid, text, *extra)
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
    _walk(call, operator_contract=operator_contract)


def _payload(result) -> dict:
    return json.loads(result.stdout)


def _ledger(run_dir: Path) -> dict:
    return json.loads((run_dir / LEDGER).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# A1 -- the variable UNSET: eight answers with no message ids refuse, naming
#       all eight, and the ledger is not marked complete
# ---------------------------------------------------------------------------
def test_a1_unset_default_refuses_and_names_all_eight(run):
    run_dir, call = run(mode=None)
    _answer_all(call)

    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert payload["status"] == "unproven", payload
    assert payload["mode"] == "enforce", payload
    assert set(EIGHT) <= set(payload["unproven_questions"]), payload
    assert len(set(payload["unproven_questions"])) >= 8, payload
    assert _ledger(run_dir).get("complete") is not True
    assert (run_dir / FINDINGS).is_file()


# ---------------------------------------------------------------------------
# A2 -- the explicit opt-out: warn reports the findings and does not block
# ---------------------------------------------------------------------------
def test_a2_warn_refuses_nothing_and_prints_findings(run):
    run_dir, call = run(mode="warn")
    _answer_all(call)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _payload(out)["status"] == "complete", out.stdout
    assert "INTAKE-PROVENANCE" in out.stderr, out.stderr
    findings = json.loads((run_dir / FINDINGS).read_text(encoding="utf-8"))
    assert findings["status"] == "unproven", findings
    assert findings["mode"] == "warn", findings


# ---------------------------------------------------------------------------
# The flip must not refuse everything: operator-contract answers still pass
# with the variable unset (the new default). AUTH004: the receipt is a real
# signed envelope (HMAC over canonical(contract) with the synthetic secret),
# never a nonempty string. The walk records QUICK defaults, so its signed
# contract carries the default_acceptance that names a real inbound message
# (a signature alone cannot approve the defaults).
# ---------------------------------------------------------------------------
def test_operator_contract_answers_still_complete_under_the_default(run):
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": REQUESTER_CHAT, "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    _write_inbound(run_dir, msg_id="msg-1", chat_id=REQUESTER_CHAT, text="good")

    for qid, text in ALL.items():
        out = call("--answer", qid, text, "--operator-contract")
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
    _walk(call, operator_contract=True)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _ledger(run_dir).get("complete") is True


# ---------------------------------------------------------------------------
# AUTH004 positives and negatives. Every negative must refuse WITHOUT
# marking complete and WITHOUT stamping a proven contract class. No CLI
# flag can bypass the verification; a complete contract needs no defaults
# review (PD-107), so the defaults review only appears when defaults exist.
# ---------------------------------------------------------------------------
def test_auth004_pos_signed_contract_with_defaults_acceptance_stamps(run):
    """POS: valid HMAC + default_acceptance matching real inbound evidence."""
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": REQUESTER_CHAT, "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    _write_inbound(run_dir, msg_id="msg-1", chat_id=REQUESTER_CHAT, text="good")
    # Seed two defaulted entries exactly as the QC004TRUST probe did.
    ledger = {"entries": {
        "goal": {"value": "Book paid calls", "validated": False,
                 "defaulted": True, "source": "default",
                 "answered_at": "2026-11-15T00:00:00+00:00",
                 "normalized": "Book paid calls", "answer": "Book paid calls"},
        "tone": {"value": "Warm and direct", "validated": False,
                 "defaulted": True, "source": "default",
                 "answered_at": "2026-11-15T00:00:00+00:00",
                 "normalized": "Warm and direct", "answer": "Warm and direct"}},
        "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 0, out.stdout + out.stderr
    entries = _ledger(run_dir)["entries"]
    assert entries["goal"]["source"] == "operator-contract"
    assert entries["goal"]["contract_sha256"]


def test_auth004_neg_bogus_hmac_refuses_without_stamp(run):
    """NEG: nonempty bogus HMAC used to prove. Now must refuse."""
    run_dir, call = run(mode=None)
    _write_signed_receipt(run_dir, hmac_value="TOTALLY-BOGUS-HMAC-0000")
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "signature is invalid" in out.stdout
    entries = _ledger(run_dir)["entries"]
    assert entries["goal"].get("source") == "default"


def test_auth004_neg_valid_hmac_without_acceptance_refuses_defaults(run):
    """NEG: valid signature alone does not prove client accepted defaults."""
    run_dir, call = run(mode=None)
    _write_signed_receipt(run_dir, _contract())  # no default_acceptance
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "default_acceptance" in out.stdout


def test_auth004_neg_acceptance_wrong_chat_refuses(run):
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": "999-other", "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    _write_inbound(run_dir, msg_id="msg-1", chat_id=REQUESTER_CHAT, text="good")
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "inbound" in out.stdout


def test_auth004_neg_acceptance_wrong_text_refuses(run):
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": REQUESTER_CHAT, "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    _write_inbound(run_dir, msg_id="msg-1", chat_id=REQUESTER_CHAT,
                   text="change the price instead")
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "inbound" in out.stdout


def test_auth004_neg_acceptance_missing_inbound_refuses(run):
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": REQUESTER_CHAT, "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    # no inbound file written
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "inbound" in out.stdout


def test_auth004_neg_tamper_after_stamp_refuses_complete(run):
    """Tamper after a valid stamp must still exit 6 at --complete."""
    run_dir, call = run(mode=None)
    acceptance = {"msg_id": "msg-1", "chat_id": REQUESTER_CHAT, "text": "good"}
    _write_signed_receipt(run_dir, _contract(acceptance=acceptance))
    _write_inbound(run_dir, msg_id="msg-1", chat_id=REQUESTER_CHAT, text="good")
    for qid, text in ALL.items():
        out = call("--answer", qid, text, "--operator-contract")
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
    _walk(call, operator_contract=True)
    receipt = run_dir / RECEIPT
    receipt.write_text(receipt.read_text(encoding="utf-8") + " ", encoding="utf-8")
    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr


def test_auth004_neg_no_key_refuses(run):
    """NEG: no verifier key fails closed, never falls back to allow."""
    run_dir, call = run(mode=None)
    _write_signed_receipt(run_dir)
    # Remove the key for this subprocess call only.
    import copy
    # Rebuild a caller without WEBHOOK_SECRET by invoking the driver directly.
    env = dict(os.environ)
    env.pop("WEBHOOK_SECRET", None)
    env.update({"PRESENTATION_RESOURCE_PROFILE_DIR": str(run_dir.parent / "profile"),
                "PRESENTATION_CAPACITY_CONFIG_DIR": str(run_dir.parent / "profile"),
                "PRESENTATION_PROVIDER_PROBES": "0",
                "PRESENTATION_MODEL_FRESHNESS": "0",
                "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
                "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-004c-test-key-material",
                "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-004c-test-1",
                "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
                "PRESENTATION_REQUESTER_CHAT_ID": REQUESTER_CHAT,
                "PRESENTATION_REQUESTER_CHANNEL": "telegram"})
    # Seed ledger requester so --next/--complete do not confuse modes.
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    import sys as _sys
    out = subprocess.run([_sys.executable, str(DRIVER), "--run-dir", str(run_dir),
                          "--answer", "defaults_review", "good", "--operator-contract"],
                         capture_output=True, text=True, timeout=180, env=env)
    assert out.returncode == 1, out.stdout + out.stderr
    assert "unsigned" in out.stdout or "HMAC does not verify" in out.stdout


def test_auth004_neg_no_hmac_refuses(run):
    run_dir, call = run(mode=None)
    receipt = run_dir / RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({"contract": {"task_id": "x"}}), encoding="utf-8")
    out = call("--answer", "presentation_type", "from_scratch", "--operator-contract")
    assert out.returncode == 1, out.stdout + out.stderr


def test_auth004_neg_bare_acceptance_refuses(run):
    run_dir, call = run(mode=None)
    _write_signed_receipt(run_dir)
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "forged approval" in out.stdout


def test_auth004_neg_both_flags_refuses(run):
    run_dir, call = run(mode=None)
    _write_signed_receipt(run_dir)
    ledger = {"entries": {"goal": {"value": "Book paid calls", "validated": False,
                                    "defaulted": True, "source": "default",
                                    "answered_at": "2026-11-15T00:00:00+00:00",
                                    "normalized": "Book paid calls",
                                    "answer": "Book paid calls"}},
              "requester": {"chat_id": REQUESTER_CHAT}}
    (run_dir / LEDGER).parent.mkdir(parents=True, exist_ok=True)
    (run_dir / LEDGER).write_text(json.dumps(ledger), encoding="utf-8")
    out = call("--answer", "defaults_review", "good", "--operator-contract",
               "--owner-msg-id", "any-id")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "give one, not both" in out.stdout


# ---------------------------------------------------------------------------
# Fail closed: a box without intake_provenance.py refuses with a named reason
# (PD-004b's forward risk; the module's default is now enforce)
# ---------------------------------------------------------------------------
def test_missing_proof_module_refuses_with_a_named_reason(run):
    run_dir, call = run(mode=None, without_module=True)
    _answer_all(call)
    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert payload["status"] == "unproven", payload
    assert payload["mode"] == "enforce", payload
    assert "intake_provenance.py is missing" in payload["error"], payload
    assert _ledger(run_dir).get("complete") is not True


def test_missing_proof_module_still_honours_the_explicit_warn_opt_out(run):
    run_dir, call = run(mode="warn", without_module=True)
    _answer_all(call)
    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert "intake_provenance.py is missing" in out.stderr, out.stderr

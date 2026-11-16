#!/usr/bin/env python3
"""PD-004c -- the interview proof refuses by default (warn is opt-in).

Acceptance rows A1 and A2 of unit PD-004c (01-BUILD-SPEC.md, lane FL02), plus
the fail-closed rule PD-004b's review left with this unit: a deployment that
does not carry intake_provenance.py must REFUSE, never warn and continue.

Driven at the subprocess level against the REAL deck-intake-driver.py; no
renderer, no network, no live service, no paid call.
"""
from __future__ import annotations

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
# with the variable unset (the new default)
# ---------------------------------------------------------------------------
def test_operator_contract_answers_still_complete_under_the_default(run):
    run_dir, call = run(mode=None)
    receipt = run_dir / RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "receipt_hmac": "hmac-of-the-signed-contract",
        "contract": "the operator contract as received",
    }), encoding="utf-8")

    for qid, text in ALL.items():
        out = call("--answer", qid, text, "--operator-contract")
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
    _walk(call, operator_contract=True)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _ledger(run_dir).get("complete") is True


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

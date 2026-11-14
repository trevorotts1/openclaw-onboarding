#!/usr/bin/env python3
"""PD-004b -- every interview answer is tied to a real client message.

Acceptance rows A1-A8 of unit PD-004b (01-BUILD-SPEC.md, lane FL02). Driven at
the subprocess level against the REAL deck-intake-driver.py and the REAL
intake_provenance.py; no renderer, no network, no live service, no paid call.

The resolver itself is PD-004a (`presentation_job.approvals.
resolve_owner_message`, lane FL34) -- ACCEPTED on its own branch, not yet on
this one. The wrapper below registers that ONE function in `sys.modules` so the
driver's own import site is exercised unchanged; it implements the accepted
contract (an id in `working/interview/inbound_messages.jsonl` resolves to its
row, else None). Same harness shape as PD-015's tests.

A1-A5 and A7 run with PRESENTATION_INTAKE_PROVENANCE=enforce (the variable this
unit's switch shipped as `warn`; PD-004c flipped the default to enforce). A6
sets it to `warn` explicitly.
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
PROOF = SCRIPTS / "intake_provenance.py"

REQUESTER_CHAT = "111"
LEDGER = Path("working") / "interview" / "intake_ledger.json"
INBOUND = Path("working") / "interview" / "inbound_messages.jsonl"
FINDINGS = Path("working") / "interview" / "provenance_findings.json"
RECEIPT = Path("working") / "interview" / "operator_contract.json"

# Eight standard text answers (A1's "eight standard answers").
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
ALL = {**BASE, **EIGHT}

_WRAPPER = textwrap.dedent('''
    import json, runpy, sys, types
    from pathlib import Path

    scripts_dir, run_dir, driver = sys.argv[1:4]
    sys.path.insert(0, scripts_dir)
    import presentation_job

    mod = types.ModuleType("presentation_job.approvals")

    def resolve_owner_message(owner_msg_id, run_dir=None):
        path = Path(run_dir or ".") / "working" / "interview" / "inbound_messages.jsonl"
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return None
        for line in lines:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict) or str(obj.get("msg_id") or "") != str(owner_msg_id):
                continue
            text = obj.get("text")
            if not isinstance(text, str) or not text.strip():
                return None
            return {"msg_id": str(obj["msg_id"]),
                    "chat_id": str(obj.get("chat_id") or ""),
                    "text": text,
                    "received_at": str(obj.get("received_at") or "")}
        return None

    mod.resolve_owner_message = resolve_owner_message
    sys.modules["presentation_job.approvals"] = mod
    presentation_job.approvals = mod
    sys.argv = [driver, "--run-dir", run_dir] + sys.argv[4:]
    runpy.run_path(driver, run_name="__main__")
''')


def _env(tmp_path: Path, mode: str = "enforce") -> dict:
    env = dict(os.environ)
    env.update({
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
        "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-004b-test-key-material",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-004b-test-1",
        "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
        "PRESENTATION_REQUESTER_CHAT_ID": REQUESTER_CHAT,
        "PRESENTATION_REQUESTER_CHANNEL": "telegram",
    })
    if mode is None:
        env.pop("PRESENTATION_INTAKE_PROVENANCE", None)
    else:
        env["PRESENTATION_INTAKE_PROVENANCE"] = mode
    return env


@pytest.fixture
def run(tmp_path):
    def build(mode="enforce"):
        run_dir = tmp_path / f"run-{mode}"
        run_dir.mkdir()
        wrapper = tmp_path / f"driver-{mode}.py"
        wrapper.write_text(_WRAPPER, encoding="utf-8")
        env = _env(tmp_path, mode)

        def call(*args):
            return subprocess.run(
                [sys.executable, str(wrapper), str(SCRIPTS), str(run_dir),
                 str(DRIVER), *args],
                capture_output=True, text=True, timeout=180, env=env)

        return run_dir, call

    return build


def _inbound(run_dir: Path, rows) -> None:
    path = run_dir / INBOUND
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def _row(msg_id: str, text: str, chat_id: str = REQUESTER_CHAT) -> dict:
    return {"msg_id": msg_id, "chat_id": chat_id, "text": text,
            "received_at": "2026-11-12T15:04:05+00:00"}


def _answer_all(call, answers: dict, ids: dict | None = None) -> None:
    for qid, text in {**BASE, **answers}.items():
        extra = (["--owner-msg-id", ids[qid]] if ids and ids.get(qid) else [])
        out = call("--answer", qid, text, *extra)
        assert out.returncode == 0, (qid, out.stdout + out.stderr)


def _ledger(run_dir: Path) -> dict:
    return json.loads((run_dir / LEDGER).read_text(encoding="utf-8"))


def _payload(result) -> dict:
    return json.loads(result.stdout)


# ---------------------------------------------------------------------------
# A1 -- eight answers with NO message ids refuse to complete, naming all eight
# ---------------------------------------------------------------------------
def test_a1_no_message_ids_exits_6_listing_all_eight(run):
    run_dir, call = run()
    _answer_all(call, EIGHT)

    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert payload["status"] == "unproven", payload
    assert payload["mode"] == "enforce", payload
    named = set(payload["unproven_questions"])
    assert set(EIGHT) <= named, (named, payload)
    assert len(named) >= 8, payload
    assert _ledger(run_dir).get("complete") is not True
    assert (run_dir / FINDINGS).is_file()


# ---------------------------------------------------------------------------
# A2 -- the same answers with ids whose text matches complete cleanly
# ---------------------------------------------------------------------------
def test_a2_matching_message_ids_exit_0(run):
    run_dir, call = run()
    ids = {qid: f"msg-{qid}" for qid in ALL}
    _inbound(run_dir, [_row(ids[q], t) for q, t in ALL.items()])
    _answer_all(call, EIGHT, ids)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _ledger(run_dir).get("complete") is True
    entry = _ledger(run_dir)["entries"]["audience"]
    assert entry["owner_msg_id"] == ids["audience"], entry


# ---------------------------------------------------------------------------
# A3 -- an id from a DIFFERENT chat refuses and names that question
# ---------------------------------------------------------------------------
def test_a3_other_chat_message_exits_6_naming_the_question(run):
    run_dir, call = run()
    ids = {qid: f"msg-{qid}" for qid in ALL}
    rows = [_row(ids[q], t) for q, t in ALL.items()]
    rows = [(_row(ids["audience"], BASE["presentation_type"], chat_id="999")
             if r["msg_id"] == ids["audience"] else r) for r in rows]
    _inbound(run_dir, rows)
    _answer_all(call, EIGHT, ids)

    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert "audience" in payload["unproven_questions"], payload
    assert any("different chat" in f for f in payload["findings"]), payload


# ---------------------------------------------------------------------------
# A4 -- one message id reused for two answers refuses
# ---------------------------------------------------------------------------
def test_a4_reused_message_id_exits_6(run):
    run_dir, call = run()
    ids = {qid: f"msg-{qid}" for qid in ALL}
    ids["goal"] = ids["audience"]                     # the same client message
    rows = [_row(ids[q], t) for q, t in ALL.items() if q != "goal"]
    _inbound(run_dir, rows)
    answers = dict(EIGHT)
    answers["goal"] = answers["audience"]             # same text, same message
    _answer_all(call, answers, ids)

    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert "goal" in payload["unproven_questions"], payload
    assert any("already used" in f for f in payload["findings"]), payload


# ---------------------------------------------------------------------------
# A5 -- --sig-record refuses a record file that carries no provenance
# ---------------------------------------------------------------------------
def test_a5_sig_record_without_provenance_exits_6(run, tmp_path):
    run_dir, call = run()
    record = {"q1": "a", "q2": "b", "q3": "c", "q4": "d",
              "q5": "e", "q6": "f", "q7": "g", "q8": "h",
              "signature_frame": "vault"}
    file_path = tmp_path / "record.json"
    file_path.write_text(json.dumps(record), encoding="utf-8")

    out = call("--signature", "--sig-record", str(file_path))
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert payload["status"] == "unproven", payload
    assert payload["door"] == "--sig-record", payload
    assert payload["problems"], payload
    assert not (run_dir / "working" / "copy" / "sp_intake.json").exists()


# ---------------------------------------------------------------------------
# A6 -- with the variable set to `warn` (PD-004c's opt-out) the proof reports
#       but never blocks, and --complete still exits 0 with findings on stderr
# ---------------------------------------------------------------------------
def test_a6_warn_mode_reports_and_does_not_block(run):
    run_dir, call = run(mode="warn")
    _answer_all(call, EIGHT)

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr
    assert _payload(out)["status"] == "complete", out.stdout
    assert "INTAKE-PROVENANCE" in out.stderr, out.stderr
    findings = json.loads((run_dir / FINDINGS).read_text(encoding="utf-8"))
    assert findings["status"] == "unproven", findings
    assert findings["mode"] == "warn", findings


# ---------------------------------------------------------------------------
# A7 -- a stored value that differs from the message by one word refuses
# ---------------------------------------------------------------------------
def test_a7_one_word_mismatch_exits_6(run):
    run_dir, call = run()
    ids = {qid: f"msg-{qid}" for qid in ALL}
    rows = [_row(ids[q], t) for q, t in ALL.items()]
    rows = [(_row(ids["goal"], "Book paid demos")
             if r["msg_id"] == ids["goal"] else r) for r in rows]
    _inbound(run_dir, rows)
    _answer_all(call, EIGHT, ids)

    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert "goal" in payload["unproven_questions"], payload


# ---------------------------------------------------------------------------
# A8 -- operator-contract answers pass under enforce; one changed byte of the
#       receipt refuses them
# ---------------------------------------------------------------------------
def test_a8_operator_contract_passes_until_the_receipt_changes(run):
    run_dir, call = run()
    receipt = run_dir / RECEIPT
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(json.dumps({
        "receipt_hmac": "hmac-of-the-signed-contract",
        "contract": "the operator contract as received",
    }), encoding="utf-8")

    for qid, text in {**BASE, **EIGHT}.items():
        out = call("--answer", qid, text, "--operator-contract")
        assert out.returncode == 0, (qid, out.stdout + out.stderr)
        assert _ledger(run_dir)["entries"][qid]["source"] == "operator-contract", out.stdout

    out = call("--complete")
    assert out.returncode == 0, out.stdout + out.stderr

    receipt.write_text(receipt.read_text(encoding="utf-8").replace(
        "operator contract", "operator contracT"), encoding="utf-8")
    out = call("--complete")
    assert out.returncode == 6, out.stdout + out.stderr
    payload = _payload(out)
    assert set(EIGHT) <= set(payload["unproven_questions"]), payload


def test_proof_module_is_standalone_and_documents_the_switch():
    source = PROOF.read_text(encoding="utf-8")
    assert "PRESENTATION_INTAKE_PROVENANCE" in source
    assert 'DEFAULT_MODE = "enforce"' in source
    assert "PD-004c" in source

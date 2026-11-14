#!/usr/bin/env python3
"""PD-015 -- a typed client answer is recorded as directly confirmed.

Acceptance rows A1-A3 of unit PD-015 (01-BUILD-SPEC.md, lane FL02). Driven at
the subprocess level against the REAL deck-intake-driver.py; no renderer, no
network, no live service, no paid call. Every case runs in a temporary run
folder.

The proof itself belongs to PD-004a (`presentation_job.approvals.
resolve_owner_message`, lane FL34), which is ACCEPTED on its own branch and
not yet on this one. So the tests pre-register that ONE function in
`sys.modules` through a wrapper -- the driver's own import site is exercised
unchanged, and the stub implements the accepted contract: an id present in
`working/interview/inbound_messages.jsonl` resolves to its row, else None.
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

QIDS = ("q1", "q2", "q3", "q4", "q5", "q6", "q7", "q8")
LEDGER = Path("working") / "interview" / "intake_ledger.json"
SP_INTAKE = Path("working") / "copy" / "sp_intake.json"
INBOUND = Path("working") / "interview" / "inbound_messages.jsonl"
REQUESTER_CHAT = "111"

# The accepted PD-004a contract, registered for the driver's own import:
# `from presentation_job.approvals import resolve_owner_message`.
_WRAPPER = textwrap.dedent('''
    import json, runpy, sys, types
    from pathlib import Path

    scripts_dir, run_dir, driver = sys.argv[1:4]
    sys.path.insert(0, scripts_dir)
    import presentation_job  # the real package, so every other import works

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
            if not isinstance(obj, dict):
                continue
            if str(obj.get("msg_id") or "") != str(owner_msg_id):
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

def _env(tmp_path: Path) -> dict:
    env = dict(os.environ)
    env.update({
        "PRESENTATION_RESOURCE_PROFILE_DIR": str(tmp_path / "profile"),
        "PRESENTATION_CAPACITY_CONFIG_DIR": str(tmp_path / "profile"),
        "PRESENTATION_PROVIDER_PROBES": "0",
        "PRESENTATION_MODEL_FRESHNESS": "0",
        "PRESENTATION_SP_TURN_LEDGER_KEYS_FILE": "",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY": "pd-015-test-key-material",
        "PRESENTATION_SP_TURN_LEDGER_CURRENT_KEY_ID": "pd-015-test-1",
        "PRESENTATION_SP_TURN_LEDGER_ROTATION_STARTED_AT": "2026-01-01T00:00:00+00:00",
        # The proof requires the message to come from THIS run's requester.
        "PRESENTATION_REQUESTER_CHAT_ID": REQUESTER_CHAT,
        "PRESENTATION_REQUESTER_CHANNEL": "telegram",
    })
    return env

@pytest.fixture
def sig(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    wrapper = tmp_path / "driver_with_resolver.py"
    wrapper.write_text(_WRAPPER, encoding="utf-8")
    env = _env(tmp_path)

    def call(*args):
        return subprocess.run(
            [sys.executable, str(wrapper), str(SCRIPTS), str(run), str(DRIVER),
             *args],
            capture_output=True, text=True, timeout=180, env=env)

    return run, call

def _inbound(run: Path, rows) -> None:
    path = run / INBOUND
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows),
                    encoding="utf-8")

def _row(msg_id: str, text: str, chat_id: str = REQUESTER_CHAT) -> dict:
    return {"msg_id": msg_id, "chat_id": chat_id, "text": text,
            "received_at": "2026-11-12T15:04:05+00:00"}

def _ledger(run: Path) -> dict:
    return json.loads((run / LEDGER).read_text(encoding="utf-8"))

# ---------------------------------------------------------------------------
# A1 -- a PROVEN id makes the answer direct; a full run completes with ZERO
#       --sig-confirm calls
# ---------------------------------------------------------------------------
def test_a1_proven_id_is_direct_and_full_run_completes(sig):
    run, call = sig
    texts = {"sp_mode": "QUICK"}
    texts.update({qid: f"Client answer {n}" for n, qid in enumerate(QIDS, 1)})
    texts["signature_frame"] = "vault"
    _inbound(run, [_row(f"msg-{k}", v) for k, v in texts.items()])

    for qid, text in texts.items():
        out = call("--signature", "--sig-answer", qid, text,
                   "--owner-msg-id", f"msg-{qid}")
        assert out.returncode == 0, out.stdout + out.stderr

    entries = _ledger(run)["sp_entries"]
    q1 = entries["q1"]
    assert q1["confirmed_by_client"] is True, q1
    assert q1["confirmation"] == "direct", q1
    assert q1["owner_msg_id"] == "msg-q1", q1

    payload = json.loads(out.stdout)          # the frame answer finalizes
    assert payload["status"] == "complete", out.stdout + out.stderr
    assert payload["unconfirmed_answers"] == [], out.stdout
    assert payload["agent_authored_answers"] == [], out.stdout
    assert payload["prover"] == "passed", out.stdout
    assert (run / SP_INTAKE).is_file()
    assert _ledger(run).get("status") == "complete"
    record = json.loads((run / SP_INTAKE).read_text(encoding="utf-8"))
    for qid in QIDS:
        prov = record["answer_provenance"][qid]
        assert prov["confirmation"] == "direct", prov
        assert prov["confirmed_by_client"] is True, prov

# ---------------------------------------------------------------------------
# A2 -- an id whose text differs is a hard error: exit 1, nothing stored
# ---------------------------------------------------------------------------
def test_a2_text_mismatch_exits_1_and_stores_nothing(sig):
    run, call = sig
    call("--signature", "--sig-answer", "sp_mode", "QUICK")
    _inbound(run, [_row("msg-q1", "Something the client never typed")])

    out = call("--signature", "--sig-answer", "q1", "Client answer 1",
               "--owner-msg-id", "msg-q1")
    assert out.returncode == 1, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert payload["status"] == "error", out.stdout
    assert payload["owner_msg_id"] == "msg-q1", out.stdout
    assert "q1" not in _ledger(run).get("sp_entries", {}), _ledger(run)

# ---------------------------------------------------------------------------
# A3 -- no id: unchanged, the answer stays unconfirmed
# ---------------------------------------------------------------------------
def test_a3_no_id_stays_unconfirmed(sig):
    run, call = sig
    call("--signature", "--sig-answer", "sp_mode", "QUICK")
    out = call("--signature", "--sig-answer", "q1", "Client answer 1")
    assert out.returncode == 0, out.stdout + out.stderr
    entry = _ledger(run)["sp_entries"]["q1"]
    assert entry["confirmed_by_client"] is False, entry
    assert entry["confirmation"] is None, entry
    assert "owner_msg_id" not in entry, entry

"""Offline proofs for the pb_send chokepoint (review C1).

Run either way:
    python3 -I test_pb_send.py
    pytest -q test_pb_send.py

Proves:
  1. The SAME provider message id admitted twice gives exactly one admission
     and the second call exits 3.
  2. A suppressed (global-stop) contact produces ZERO sender calls.
  3. A human-fenced contact produces ZERO transport calls.

Every proof drives the real CLI (``pb_send.main``), the real DurableStore, the
real consent/handoff gates and the real JournalTransport — no fakes.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(HERE)
SKILL = os.path.dirname(TOOLS)  # 38-conversational-ai-system
REPO = os.path.dirname(SKILL)
for path in (TOOLS, os.path.join(REPO, "shared-utils", "handoff")):
    if path not in sys.path:
        sys.path.insert(0, path)

import pb_send  # noqa: E402
import tenant_identity  # noqa: E402
import consent_gate  # noqa: E402

TENANT = "loc_pb_send_proof"
INBOUND = "msg_inbound_proof_1"


def _workspace():
    d = tempfile.mkdtemp(prefix="pb-send-proof-")
    return {
        "dir": d,
        "outbox": os.path.join(d, "outbox.sqlite"),
        "identity": os.path.join(d, "identity.sqlite"),
        "journal": os.path.join(d, "journal.jsonl"),
    }


def _bind(ws):
    identity = tenant_identity.TenantIdentity(ws["identity"])
    identity.register_tenant(TENANT, "proof")
    return identity.bind(TENANT, [("phone", "+15550000001", True)])


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = pb_send.main(argv)
    return rc, buf.getvalue()


def _admit(ws, contact):
    return _run(["admit", "--outbox", ws["outbox"], "--tenant", TENANT,
                 "--message-id", INBOUND, "--contact", contact])


def _reply(ws, contact):
    return _run(["reply", "--outbox", ws["outbox"], "--tenant", TENANT,
                 "--contact", contact, "--channel", "sms",
                 "--text", "Your gift is ready.", "--inbound-message-id", INBOUND,
                 "--identity-db", ws["identity"], "--transport", "journal",
                 "--journal", ws["journal"], "--approval-ref", "proof"])


def _sends(ws):
    if not os.path.exists(ws["journal"]):
        return 0
    with open(ws["journal"], encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def test_duplicate_admit_is_one_admission_and_exit_3():
    ws = _workspace()
    contact = _bind(ws)
    first, _ = _admit(ws, contact)
    second, out = _admit(ws, contact)
    assert first == 0, first
    assert second == 3, (second, out)
    assert json.loads(out)["admitted"] is False
    conn = sqlite3.connect(ws["outbox"])
    rows = conn.execute("SELECT COUNT(*) FROM inbox_events").fetchone()[0]
    conn.close()
    assert rows == 1, rows


def test_suppressed_contact_makes_zero_sender_calls():
    ws = _workspace()
    contact = _bind(ws)
    store = consent_gate.ConsentStore(
        tenant_identity.TenantIdentity(ws["identity"]))
    store.global_stop(TENANT, contact, reason="person said stop", actor="proof")
    _admit(ws, contact)
    rc, out = _reply(ws, contact)
    assert rc == 4, (rc, out)
    assert "SUPPRESSED" in out, out
    assert _sends(ws) == 0, "a suppressed contact must reach no transport"


def test_human_fence_makes_zero_transport_calls():
    ws = _workspace()
    contact = _bind(ws)
    store = consent_gate.ConsentStore(
        tenant_identity.TenantIdentity(ws["identity"]))
    store.human_takeover(TENANT, contact, actor="trevor", reason="proof")
    _admit(ws, contact)
    rc, out = _reply(ws, contact)
    assert rc == 4, (rc, out)
    assert _sends(ws) == 0, "a human-fenced contact must reach no transport"


def _main():
    checks = [test_duplicate_admit_is_one_admission_and_exit_3,
              test_suppressed_contact_makes_zero_sender_calls,
              test_human_fence_makes_zero_transport_calls]
    for check in checks:
        check()
        print("PASS", check.__name__)
    print("RESULT: PASS 3/3")
    return 0


if __name__ == "__main__":
    sys.exit(_main())

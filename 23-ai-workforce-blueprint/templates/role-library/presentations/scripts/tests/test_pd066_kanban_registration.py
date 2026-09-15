#!/usr/bin/env python3
"""PD-TEST-066 — the Presentations engine's Kanban registration with the
Command Center: the credential the engine must SEND, and the duplicate it must
never create.

WHAT WAS BROKEN (measured live, run
pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4):

    [cc_board/presentations] ingest POST non-OK (HTTP 401): {'error': 'Unauthorized'}
    ... six times, then "run continues ungrouped"

`cc_board.ingest_deck_task()` WAS reached — so `COMMAND_CENTER_URL` was in the
engine's process env, because otherwise `board_config()` returns None and the
log reads "CC board disabled (no-op)". But `MC_API_TOKEN` / `WEBHOOK_SECRET`
were NOT. `_request()` attaches `Authorization` only when `cfg["token"]` is
truthy and `x-webhook-signature` only when `cfg["secret"]` is truthy, so the
request went out with NEITHER header. The Command Center middleware
(src/middleware.ts:653-656) rejects a bearer-less request to a webhook route
with 401 'missing-header' BEFORE the route's own signature check
(src/app/api/tasks/ingest/route.ts:385-391) is ever reached — which is why the
CC logged ZERO "[INGEST] Invalid signature attempt" lines.

The credentials were never wrong. They were never SENT. Both secrets match
between the engine's sanctioned store (~/.openclaw/.env) and the Command
Center's .env.local (sha256 prefix 8960f9 for the token, 075f33 for the
secret), and the CC's own runtime proves both are configured: an unset
MC_API_TOKEN yields 503 'mc-api-token-unset' and an unset WEBHOOK_SECRET yields
503 'webhook-secret-unset' — the engine received a 401, so both are set.

ROOT CAUSE: `presentation_job` had no entry-point env-store load. Only the two
launchd shells (presentation-intake-poll.sh, presentation-watchdog.sh) and
`intake_bridge._load_operator_launch_environment()` loaded the store. An engine
launched DIRECTLY — as this one was, from an operator/agent shell whose env
carries COMMAND_CENTER_URL but not the secrets — inherited a credential-less
environment and silently degraded to "ungrouped".

THE FIX under test: `presentation_job.env_store.load_into_process()`, called
first thing in `presentation_job.__main__.main()`. It is the in-process twin of
`--emit-shell` and obeys the SAME precedence rule (a non-blank value already in
the process env wins and is never re-assigned), so it cannot overwrite an
operator's one-invocation override.

The stub board below enforces the Command Center's TWO real gates IN ORDER, and
dedupes on `idempotency_key` through a key shaped exactly like the live
`task_request_keys` table's PRIMARY KEY(company_id, source, operation_id). That
is what lets this suite prove ONE legitimate registration and NO duplicate.

NOTE ON test_a: the patch deliberately does NOT change cc_board's control flow,
so the credential-less path still posts unsigned and still takes a 401. test_a
pins that shape — it is the live defect, and it doubles as the guard that the
fix was made in the ENV PROVISIONING, never by weakening or bypassing a gate.

Hermetic: no live network, no real credential. Stdlib + pytest-compatible.
Run:  python3 scripts/tests/test_pd066_kanban_registration.py
"""
from __future__ import annotations

import hashlib
import hmac
import http.server
import json
import re
import sys
import tempfile
import threading
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import cc_board  # noqa: E402
from presentation_job.env_store import load_into_process  # noqa: E402

TOKEN = "tok-pd066-test-only"          # test values, never a client credential
SECRET = "sec-pd066-test-only"
COMPANY = "blackceo"


# ---------------------------------------------------------------------------
# The stub Command Center. Both gates, in the real order.
# ---------------------------------------------------------------------------
class _StubBoard(http.server.BaseHTTPRequestHandler):
    requests: list = []          # every request seen, for assertions
    cards: dict = {}             # (company, source, operation_id) -> task_id
    _seq = [0]

    def do_POST(self):  # noqa: N802
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        rec = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "signature": self.headers.get("x-webhook-signature"),
            "raw": raw,
            "status": None,
        }
        _StubBoard.requests.append(rec)

        # GATE 1 — middleware bearer (src/middleware.ts:653-660). The response
        # body is the bare 'Unauthorized' the middleware deliberately keeps, so
        # no reject reason is disclosed to the caller.
        auth = self.headers.get("Authorization") or ""
        if not auth.startswith("Bearer ") or auth[7:] != TOKEN:
            rec["status"] = 401
            return self._send(401, {"error": "Unauthorized"})

        # GATE 2 — route HMAC over the RAW body
        # (src/lib/webhook-signature.ts:60-65). Recomputed here over the exact
        # bytes received, which is what proves the engine signs the bytes it
        # actually sends (no re-serialization mismatch).
        expected = hmac.new(SECRET.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        got = self.headers.get("x-webhook-signature")
        if not got or not hmac.compare_digest(got, expected):
            rec["status"] = 401
            return self._send(401, {"error": "Unauthorized"})

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            rec["status"] = 400
            return self._send(400, {"error": "Invalid JSON body"})

        # Idempotency, shaped like task_request_keys
        # PRIMARY KEY(company_id, source, operation_id).
        key = (COMPANY, payload.get("source") or "", payload["idempotency_key"])
        if key in _StubBoard.cards:
            rec["status"] = 200
            return self._send(200, {"task_id": _StubBoard.cards[key], "deduped": True})

        _StubBoard._seq[0] += 1
        task_id = "card-%04d" % _StubBoard._seq[0]
        _StubBoard.cards[key] = task_id
        rec["status"] = 200
        return self._send(200, {"task_id": task_id, "deduped": False})

    def _send(self, code, obj):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):
        pass


class Stub:
    def __enter__(self):
        _StubBoard.requests = []
        _StubBoard.cards = {}
        _StubBoard._seq = [0]
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _StubBoard)
        self.url = "http://127.0.0.1:%d" % self.srv.server_address[1]
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *exc):
        self.srv.shutdown()
        self.srv.server_close()
        return False


def _run_dir() -> Path:
    """A scratch run dir. Deliberately has NO state.json, so cc_board's
    _dispatch_engine_if_idle() returns immediately and never spawns anything."""
    rd = Path(tempfile.mkdtemp(prefix="pd066_run_"))
    (rd / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    return rd


def _store_file() -> Path:
    d = Path(tempfile.mkdtemp(prefix="pd066_store_"))
    p = d / ".env"
    p.write_text(
        "PRESENTATION_NOTIFY_CMD=/bin/echo pd066\n"
        "MC_API_TOKEN=%s\n"
        "WEBHOOK_SECRET=%s\n" % (TOKEN, SECRET)
    )
    return p


def _manifest(rd: Path) -> dict:
    p = rd / "working" / "checkpoints" / "process_manifest.json"
    return json.loads(p.read_text()) if p.is_file() else {}


def _ingest(env, rd):
    return cc_board.ingest_deck_task(
        rd, "pres-operator-1d269693", "Presentation pj_4996d", "desc",
        env=env, run_id="1d269693-ff54-4b1f-b45a-61dc7d8ca4d4",
    )


# ---------------------------------------------------------------------------
# A — the live defect: an enabled board with no credentials posts UNSIGNED and
#     is rejected 401 at the middleware bearer gate.
# ---------------------------------------------------------------------------
def test_a_credential_less_engine_sends_no_auth_headers_and_is_rejected_401():
    with Stub() as stub:
        # The operator/agent shell env: base URL present, credentials absent.
        env = {"COMMAND_CENTER_URL": stub.url}
        rd = _run_dir()
        task_id = _ingest(env, rd)

        assert task_id is None, "an unauthorised ingest must not register: %r" % (task_id,)
        assert len(_StubBoard.requests) == 1, _StubBoard.requests
        rec = _StubBoard.requests[0]
        assert rec["path"] == "/api/tasks/ingest", rec["path"]
        assert rec["status"] == 401, rec
        assert rec["authorization"] is None, (
            "PD-066: engine must be shown sending NO Authorization header, got %r"
            % (rec["authorization"],))
        assert rec["signature"] is None, (
            "PD-066: engine must be shown sending NO x-webhook-signature, got %r"
            % (rec["signature"],))
        assert _StubBoard.cards == {}, "a rejected ingest must create no card"

        m = _manifest(rd)
        assert m.get("cc_register_attempted") is True, m
        assert "cc_task_id" not in m, (
            "a 401 must never stamp a task id: %r" % (m.get("cc_task_id"),))


# ---------------------------------------------------------------------------
# B — GREEN: after the entry-point store load, ONE legitimate registration.
# ---------------------------------------------------------------------------
def test_b_entry_store_load_yields_one_accepted_registration():
    with Stub() as stub:
        env = {"COMMAND_CENTER_URL": stub.url}
        assert "MC_API_TOKEN" not in env and "WEBHOOK_SECRET" not in env

        rep = load_into_process(environ=env, paths=[_store_file()])
        assert "MC_API_TOKEN" in env and "WEBHOOK_SECRET" in env, (
            "the entry-point load must supply BOTH credentials: %r" % (rep,))
        assert rep.get("loaded_into_process") is True, rep
        # The report is the ONLY reporting surface -- and it carries no value.
        assert TOKEN not in json.dumps(rep) and SECRET not in json.dumps(rep), (
            "the redacted report must never carry a secret value")

        rd = _run_dir()
        task_id = _ingest(env, rd)

        assert task_id == "card-0001", task_id
        rec = _StubBoard.requests[0]
        assert rec["status"] == 200, rec
        assert rec["authorization"] == "Bearer %s" % TOKEN, rec["authorization"]
        assert re.fullmatch(r"[0-9a-f]{64}", rec["signature"] or ""), rec["signature"]
        assert len(_StubBoard.cards) == 1, _StubBoard.cards

        m = _manifest(rd)
        assert m.get("cc_task_id") == task_id, m
        assert m.get("cc_register_attempted") is True, m


# ---------------------------------------------------------------------------
# C — no duplicate: the same run registering again reuses the SAME card.
# ---------------------------------------------------------------------------
def test_c_repeat_registration_is_idempotent_no_duplicate_card():
    with Stub() as stub:
        env = {"COMMAND_CENTER_URL": stub.url}
        load_into_process(environ=env, paths=[_store_file()])

        rd = _run_dir()
        ids = [_ingest(env, rd) for _ in range(3)]  # initial + retry + resume

        assert ids == ["card-0001"] * 3, ids
        assert len(_StubBoard.requests) == 3, len(_StubBoard.requests)
        assert len(_StubBoard.cards) == 1, (
            "exactly one card must exist for one run: %r" % (_StubBoard.cards,))
        assert [r["status"] for r in _StubBoard.requests] == [200, 200, 200], (
            [r["status"] for r in _StubBoard.requests])


# ---------------------------------------------------------------------------
# D — precedence: a one-invocation operator override is never overwritten.
# ---------------------------------------------------------------------------
def test_d_process_env_wins_over_store():
    with Stub() as stub:
        env = {"COMMAND_CENTER_URL": stub.url,
               "MC_API_TOKEN": TOKEN,
               "WEBHOOK_SECRET": "operator-override-not-the-store-value"}
        rep = load_into_process(environ=env, paths=[_store_file()])
        assert env["WEBHOOK_SECRET"] == "operator-override-not-the-store-value"
        assert "WEBHOOK_SECRET" in rep["already_in_process_env"], rep


# ---------------------------------------------------------------------------
# E — the wiring itself: main() loads the store before it does anything else.
# ---------------------------------------------------------------------------
def test_e_main_loads_entry_store():
    src = (SCRIPTS / "presentation_job" / "__main__.py").read_text()
    body = src.split("def main(", 1)[1]
    call = body.index("load_into_process()")
    assert call < body.index("build_parser()"), (
        "main() must load the env store BEFORE parsing args / doing work")


# ---------------------------------------------------------------------------
def _main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS  %s" % t.__name__)
        except AssertionError as exc:
            failed += 1
            print("FAIL  %s\n        %s" % (t.__name__, exc))
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("ERROR %s: %s: %s" % (t.__name__, type(exc).__name__, exc))
    print("\n%d/%d passed" % (len(tests) - failed, len(tests)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_main())

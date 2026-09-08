"""test_f12_board_outbox.py — F12 acceptance (ONB half).

"A board outage does not lose completed artifacts, and replay creates one
consistent card with truthful status." Plus truthful task ownership: Skill 35's
runner now creates tasks via the canonical /api/tasks/ingest with company +
department binding and fallback_ok (verified by payload-contract test here).

Coverage (board outbox in 57-social-media-in-a-box/scripts/mc_board.py):
  1. Outage → ingest failure parks the op in the run's board outbox (one line,
     deduped).
  2. Recovery → replay_outbox re-POSTs once; the server fixture dedupes on the
     stable idempotency_key so exactly ONE card exists; the outbox drains.
  3. Status-write outage parks the move; replay re-reads the card first and
     never double-moves or regresses a card that advanced during the outage.
  4. A 4xx is a permanent fault — never parked, never replayed.
  5. run-publishing-cycle.sh create-payload contract: canonical ingest fields
     (source, source_ref, idempotency_key, department_slug, fallback_ok,
     optional company_id) and NO bare /api/tasks POST for task creation.

Run: python3 -m unittest tests.social_planner.test_f12_board_outbox -v
(via discover: python3 -m unittest discover -s tests/social-planner -p 'test_f*.py')
"""

import hashlib
import hmac
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

_ONB_ROOT = Path(__file__).resolve().parents[2]
_MC_BOARD = _ONB_ROOT / "57-social-media-in-a-box" / "scripts" / "mc_board.py"
_RUNNER = _ONB_ROOT / "35-social-media-planner" / "scripts" / "run-publishing-cycle.sh"


def _load_mc_board():
    spec = importlib.util.spec_from_file_location("f12_mc_board", _MC_BOARD)
    mod = importlib.util.module_from_spec(spec)
    # dataclasses.py resolves annotation modules via sys.modules[cls.__module__]
    # — the module must be registered BEFORE exec on Python 3.14.
    sys.modules["f12_mc_board"] = mod
    spec.loader.exec_module(mod)
    return mod


class _FakeBoard:
    """Records attempted side effects; configurable outage windows.

    Network fakes record attempted side effects (QC fixture contract) — never
    touch the network. Dedupe happens SERVER-side on idempotency_key; this
    fixture mirrors that contract so the test proves the replay collapses to
    one card because of the shared key, not client memory."""

    def __init__(self, outage=False):
        self.outage = outage
        self.ingest_calls = []
        self.cards = {}           # idempotency_key -> task_id (server dedupe)
        self.status_moves = []    # (task_id, from, to)
        self.statuses = {}        # task_id -> current status
        self._seq = 0

    def _respond(self):
        class R:
            def __init__(self, code, body):
                self.code, self.body = code, body

            def read(self):
                return json.dumps(self.body).encode()

            def getcode(self):
                return self.code

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return R

    # --- urllib surface used by mc_board._request ---
    def urlopen(self, req, timeout=None):  # noqa: ARG002 — parity signature
        if self.outage:
            raise urllib.error.URLError("connection refused (simulated outage)")
        url = req.full_url
        body = req.data or b""
        if url.endswith("/api/tasks/ingest"):
            payload = json.loads(body or b"{}")
            self.ingest_calls.append(payload)
            key = payload.get("idempotency_key") or ""
            if key and key in self.cards:
                resp = {"ok": True, "deduped": True, "task_id": self.cards[key]}
            else:
                self._seq += 1
                tid = f"task-{self._seq}"
                self.cards[key] = tid
                self.statuses[tid] = "backlog"
                resp = {"ok": True, "deduped": False, "task_id": tid}
            return self._respond()(200, resp)
        # status write: /api/tasks/{id}
        tid = url.rstrip("/").rsplit("/", 1)[-1]
        payload = json.loads(body or b"{}")
        target = payload.get("status")
        if target and self.statuses.get(tid) != target:
            self.status_moves.append((tid, self.statuses.get(tid), target))
            self.statuses[tid] = target
        return self._respond()(200, {"ok": True, "status": self.statuses.get(tid)})


class TestF12BoardOutbox(unittest.TestCase):
    def setUp(self):
        self.mc = _load_mc_board()
        self.tmp = tempfile.TemporaryDirectory()
        self.run_dir = Path(self.tmp.name) / "run-1"
        (self.run_dir / "working" / "checkpoints").mkdir(parents=True)
        self.env = {
            "COMMAND_CENTER_URL": "http://board.test",
            "CC_API_TOKEN": "tok",
            "WEBHOOK_SECRET": "sec",
        }

    def tearDown(self):
        self.tmp.cleanup()

    def _patch_request(self, fake):
        real_urlopen = __import__("urllib.request", fromlist=["urlopen"]).urlopen
        urllib.request.urlopen = fake.urlopen
        self.addCleanup(lambda: setattr(urllib.request, "urlopen", real_urlopen))
        return fake

    # ------------------------------------------------------------------
    # 1+2. Outage → outbox → replay → ONE card
    # ------------------------------------------------------------------
    def test_outage_parks_ingest_then_replay_creates_exactly_one_card(self):
        fake = _FakeBoard(outage=True)
        self._patch_request(fake)

        tid = self.mc.card_open(str(self.run_dir), slug="skill-57", title="F12 run",
                                department="marketing", source="test",
                                env=dict(self.env))
        self.assertIsNone(tid, "outage must fail-soft (None), never raise")
        ops = self.mc._outbox_read(str(self.run_dir))
        self.assertEqual(len(ops), 1, "exactly one parked op for one failed ingest")

        # A repeated failure of the SAME write collapses (deduped on op_id).
        self.mc.card_open(str(self.run_dir), slug="skill-57", title="F12 run",
                          department="marketing", source="test", env=dict(self.env))
        self.assertEqual(len(self.mc._outbox_read(str(self.run_dir))), 1,
                         "repeated outage must not grow the outbox")

        # RECOVERY: the board comes back. Replay once.
        recovered = _FakeBoard(outage=False)
        self._patch_request(recovered)
        report = self.mc.replay_outbox(str(self.run_dir), env=dict(self.env))
        self.assertEqual(report["replayed"], 1)
        self.assertEqual(report["remaining"], 0)
        self.assertEqual(len(recovered.ingest_calls), 1,
                         "replay re-POSTs exactly once")
        self.assertEqual(len(recovered.cards), 1, "server dedupe ⇒ ONE card")
        # Receipt backfilled with the real task id.
        receipt = self.mc._read_receipt(str(self.run_dir))
        self.assertEqual(receipt.get("mc_task_id"), recovered.cards[recovered.ingest_calls[0]["idempotency_key"]])

        # A second replay pass is a no-op (idempotent recovery).
        report2 = self.mc.replay_outbox(str(self.run_dir), env=dict(self.env))
        self.assertEqual(report2["replayed"], 0)
        self.assertEqual(len(recovered.ingest_calls), 1)

    # ------------------------------------------------------------------
    # 3. Status-write outage: replay never double-moves or regresses
    # ------------------------------------------------------------------
    def test_status_outage_replay_is_truthful(self):
        # Park a status move during an outage.
        fake = _FakeBoard(outage=True)
        self._patch_request(fake)
        ok = self.mc.card_advance(str(self.run_dir), "task-9", phase_id="run",
                                  status="in_progress", note="run started",
                                  env=dict(self.env))
        self.assertFalse(ok)
        self.assertEqual(len(self.mc._outbox_read(str(self.run_dir))), 1)

        # Recovery — but the card ALREADY reached review during the outage
        # (someone else advanced it). Truthful replay must NOT regress it.
        recovered = _FakeBoard(outage=False)
        self._patch_request(recovered)
        recovered.statuses["task-9"] = "review"
        report = self.mc.replay_outbox(str(self.run_dir), env=dict(self.env))
        self.assertEqual(report["removed"], 1, "op resolved without a write")
        self.assertEqual(recovered.status_moves, [],
                         "no move issued — replay never regresses a card that advanced")

        # And the normal case: card still at backlog ⇒ the parked in_progress
        # move IS re-issued, once.
        run2 = Path(self.tmp.name) / "run-2"
        (run2 / "working" / "checkpoints").mkdir(parents=True)
        fake2 = _FakeBoard(outage=True)
        self._patch_request(fake2)
        self.mc.card_advance(str(run2), "task-10", phase_id="run", status="in_progress",
                             env=dict(self.env))
        rec2 = _FakeBoard(outage=False)
        self._patch_request(rec2)
        rec2.statuses["task-10"] = "backlog"
        report2 = self.mc.replay_outbox(str(run2), env=dict(self.env))
        self.assertEqual(report2["removed"], 1)
        self.assertEqual(rec2.status_moves, [("task-10", "backlog", "in_progress")],
                         "parked move replayed exactly once, in order")

    # ------------------------------------------------------------------
    # 4. 4xx is permanent — never parked
    # ------------------------------------------------------------------
    def test_4xx_not_parked(self):
        class BadRequest(_FakeBoard):
            def urlopen(self, req, timeout=None):  # noqa: ARG002
                raise urllib.error.HTTPError(req.full_url, 400, "bad request",
                                             None, None)

        self._patch_request(BadRequest())
        tid = self.mc.card_open(str(self.run_dir), slug="s", title="t",
                                department="marketing", env=dict(self.env))
        self.assertIsNone(tid)
        self.assertEqual(self.mc._outbox_read(str(self.run_dir)), [],
                         "a 4xx caller fault must not enter the outbox (replay can never succeed)")

    # ------------------------------------------------------------------
    # 5. Truthful ownership: canonical ingest payload contract
    # ------------------------------------------------------------------
    def test_skill35_runner_uses_canonical_ingest_with_binding(self):
        self.assertTrue(_RUNNER.exists(), "runner script must exist")
        src = _RUNNER.read_text()
        # Canonical front door, not the generic task POST, for CREATION.
        self.assertIn('cc_call_ingest', src, "runner must create via cc_call_ingest")
        self.assertIn('"/api/tasks/ingest"', src)
        self.assertNotRegex(src, r'cc_call POST /api/tasks ',
                            "bare generic task POST must no longer be the creation path")
        # Company + capability binding + fallback + idempotency fields.
        self.assertIn('"department_slug": "social-media"', src)
        self.assertIn('"fallback_ok": True', src)
        self.assertIn('"idempotency_key"', src)
        self.assertIn('SKILL35_COMPANY_ID', src, "verified company binding from env")
        self.assertIn('"company_id"', src)

    # ------------------------------------------------------------------
    # 6. D-F12-01: signed-ingest HMAC parity — fast path must equal
    # HMAC(secret, rawBody), the construction CC verifyWebhookSignature
    # (and mc_board._sign) uses. Regression: the old fast path signed
    # HMAC(body-as-key, empty-message) and CC 401d every signed ingest.
    # ------------------------------------------------------------------
    def test_ingest_hmac_fast_path_matches_secret_keyed_signature(self):
        self.assertTrue(_RUNNER.exists(), "runner script must exist")
        src = _RUNNER.read_text()
        secret = "qc-parity-secret"
        body = '{"title":"qc-parity-body"}'
        fast = subprocess.run(
            ["bash", "-c",
             "printf '%s' \"$0\" | CC_WEBHOOK_SECRET=\"$1\" python3 -c "
             "\"import hashlib,hmac,os,sys; print(hmac.new("
             "os.environ['CC_WEBHOOK_SECRET'].encode('utf-8'), "
             "sys.stdin.buffer.read(), hashlib.sha256).hexdigest())\"",
             body, secret],
            capture_output=True, text=True)
        self.assertEqual(fast.returncode, 0, fast.stderr)
        expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"),
                            hashlib.sha256).hexdigest()
        self.assertEqual(fast.stdout.strip(), expected,
                         "shell fast path must be HMAC(secret, body)")
        # The runner's embedded fast path must use the secret as the key
        # (not the body) over the body bytes (not an empty message).
        self.assertIn("os.environ['CC_WEBHOOK_SECRET']", src)
        self.assertIn("sys.stdin.buffer.read(), hashlib.sha256", src)
        self.assertNotIn("hmac.new(sys.stdin.buffer.read(), b''", src,
                         "old body-as-key construction must be gone")


if __name__ == "__main__":
    unittest.main()
#!/usr/bin/env python3
"""
test_cc_board.py — hermetic tests for the presentations producer-side Command
Center board caller (cc_board.py). Stdlib unittest only; NO live network — every
HTTP call is intercepted so the suite is deterministic and offline.

Covers the contract that matters:
  * FAIL-SOFT: no COMMAND_CENTER_URL => clean no-op (None / False), never raises.
  * cc_register_attempted=True is stamped BEFORE any HTTP call (fail-soft discipline).
  * AUTH PARITY: Bearer CC_API_TOKEN + x-webhook-signature = HMAC-SHA256(
    WEBHOOK_SECRET, EXACT rawBody) hex — recomputed the way the route handler
    verifies it.
  * REQUEST CONTRACT: POST /api/tasks/ingest body shape; PATCH /api/tasks/{id} shape;
    POST /api/tasks/{id}/activities body shape.
  * STATUS ENFORCEMENT: the fake server MIRRORS the CC UpdateTaskSchema — a PATCH
    whose status is not one of the 10 authoritative TaskStatus values is REJECTED
    with HTTP 400, exactly as the live gate does. (The retired 'delivered' literal
    is rejected; the mock previously accepted it and hid the P9-DELIVER 400 bug.)
  * FAIL-SOFT on transport errors (URLError / HTTPError / timeout) => None/False,
    but cc_register_attempted=True is always stamped.
  * stamp_task_id merges cc_task_id into process_manifest.json without clobbering.
"""

import hashlib
import hmac
import io
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cc_board  # noqa: E402

# The 10 authoritative Command Center TaskStatus values (UpdateTaskSchema in the CC
# repo src/lib/validation.ts). The fake server below rejects a PATCH status outside
# this set with HTTP 400, mirroring the live Zod gate.
VALID_CC_STATUSES = frozenset({
    "backlog", "inbox", "planning", "in_progress", "assigned",
    "review", "testing", "blocked", "pending_dispatch", "done",
})


# ---------------------------------------------------------------------------
# A fake HTTP layer: records the last request and returns a scripted response.
# ---------------------------------------------------------------------------
class _FakeResp:
    def __init__(self, status, payload):
        self._status = status
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def getcode(self):
        return self._status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _Recorder:
    """Stand-in for urllib.request.urlopen. Captures requests and replays a queue
    of (status, payload) responses; a response may be an Exception to raise."""

    def __init__(self):
        self.requests = []
        self.responses = []

    def queue(self, status, payload):
        self.responses.append((status, payload))

    def queue_raise(self, exc):
        self.responses.append(exc)

    def __call__(self, req, timeout=None):
        body_str = req.data.decode("utf-8") if req.data else ""
        self.requests.append({
            "method": req.get_method(),
            "url": req.full_url,
            "headers": {k.lower(): v for k, v in req.header_items()},
            "body": body_str,
            "timeout": timeout,
        })
        # SERVER-SIDE STATUS ENFORCEMENT (mirror of CC UpdateTaskSchema): a task PATCH
        # carrying a status outside the 10 authoritative values is a 400 — the same
        # way the live Zod validator rejects it — so an unknown literal like the
        # retired 'delivered' can never masquerade as a successful advance.
        if req.get_method() == "PATCH" and "/api/tasks/" in req.full_url \
                and not req.full_url.endswith("/activities"):
            try:
                _status = json.loads(body_str).get("status") if body_str else None
            except (json.JSONDecodeError, ValueError):
                _status = None
            if _status is not None and _status not in VALID_CC_STATUSES:
                raise urllib.error.HTTPError(
                    req.full_url, 400, "Validation failed", {},
                    io.BytesIO(json.dumps({
                        "error": "Validation failed",
                        "details": [{"path": ["status"], "message":
                                     f"Invalid enum value. Received '{_status}'"}],
                    }).encode()))
        if not self.responses:
            raise AssertionError("no scripted response queued")
        nxt = self.responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        status, payload = nxt
        if status >= 400:
            raise urllib.error.HTTPError(
                req.full_url, status, "err", {}, io.BytesIO(json.dumps(payload).encode()))
        return _FakeResp(status, payload)


ENV = {
    "COMMAND_CENTER_URL": "https://cc.example.test/",
    "CC_API_TOKEN": "tok-abc",
    "WEBHOOK_SECRET": "shh-secret",
}

# The five per-phase QC reports the render engine writes to working/qc/*.json.
_QC_FILES = {
    "copy_qc_report.json": "Phase 1Q",
    "prompt_qc_report.json": "Phase Prompt-QC",
    "image_qc_report.json": "Phase Image-QC",
    "typography_qc_report.json": "Phase Typography-QC",
    "speech_qc_report.json": "Phase Speech-QC",
}


def _seed_qc_reports(run_dir, averages=None, passing=True, autofails=None):
    """Write the five governed QC reports under run_dir/working/qc/ using the engine's
    own field schema (gate / average / pass / triggered_autofails)."""
    averages = averages or {}
    autofails = autofails or {}
    qc = Path(run_dir) / "working" / "qc"
    qc.mkdir(parents=True, exist_ok=True)
    for fname, gate in _QC_FILES.items():
        (qc / fname).write_text(json.dumps({
            "gate": gate,
            "average": averages.get(fname, 9.0),
            "pass": passing,
            "triggered_autofails": autofails.get(fname, []),
        }))


class FailSoftTest(unittest.TestCase):
    def test_no_url_ingest_is_noop_but_stamps_attempted(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            result = cc_board.ingest_deck_task(rd, "deck-1", "My Deck", "desc", env={})
            self.assertIsNone(result)
            # cc_register_attempted must be stamped even when board disabled
            pm = rd / "working" / "checkpoints" / "process_manifest.json"
            self.assertTrue(pm.exists())
            self.assertTrue(json.loads(pm.read_text()).get("cc_register_attempted"))

    def test_no_url_patch_is_noop(self):
        self.assertFalse(cc_board.patch_phase(None, "task-1", "P0A-INTAKE", "done", env={}))

    def test_config_none_without_url(self):
        self.assertIsNone(cc_board.board_config({"CC_API_TOKEN": "x"}))

    def test_mission_control_url_fallback(self):
        cfg = cc_board.board_config({"MISSION_CONTROL_URL": "https://fallback.test"})
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["base_url"], "https://fallback.test")

    def test_command_center_url_takes_priority(self):
        cfg = cc_board.board_config({
            "COMMAND_CENTER_URL": "https://primary.test",
            "MISSION_CONTROL_URL": "https://secondary.test",
        })
        self.assertIsNotNone(cfg)
        self.assertEqual(cfg["base_url"], "https://primary.test")

    def test_cc_api_token_and_mc_api_token_aliases(self):
        cfg1 = cc_board.board_config({"COMMAND_CENTER_URL": "https://x.test", "CC_API_TOKEN": "t1"})
        cfg2 = cc_board.board_config({"COMMAND_CENTER_URL": "https://x.test", "MC_API_TOKEN": "t2"})
        self.assertEqual(cfg1["token"], "t1")
        self.assertEqual(cfg2["token"], "t2")


class AuthAndContractTest(unittest.TestCase):
    def setUp(self):
        self.rec = _Recorder()
        self._orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = self.rec

    def tearDown(self):
        cc_board.urllib.request.urlopen = self._orig

    def _verify_signature(self, request):
        body = request["body"].encode("utf-8")
        expected = hmac.new(b"shh-secret", body, hashlib.sha256).hexdigest()
        self.assertEqual(request["headers"]["x-webhook-signature"], expected)

    def test_ingest_contract_and_auth(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.rec.queue(201, {"ok": True, "task_id": "task-xyz", "deduped": False})
            task_id = cc_board.ingest_deck_task(
                rd, "deck-001", "My Deck", "A great deck", env=ENV)
            self.assertEqual(task_id, "task-xyz")
            req = self.rec.requests[-1]
            self.assertEqual(req["method"], "POST")
            self.assertEqual(req["url"], "https://cc.example.test/api/tasks/ingest")
            self.assertEqual(req["headers"]["authorization"], "Bearer tok-abc")
            self.assertEqual(req["headers"]["content-type"], "application/json")
            self._verify_signature(req)
            body = json.loads(req["body"])
            self.assertEqual(body["title"], "My Deck")
            self.assertEqual(body["source_ref"], "deck-001")
            self.assertEqual(body["department_slug"], "presentations")
            # cc_task_id and cc_register_attempted both stamped
            pm = json.loads((rd / "working" / "checkpoints" / "process_manifest.json").read_text())
            self.assertEqual(pm["cc_task_id"], "task-xyz")
            self.assertTrue(pm["cc_register_attempted"])

    def test_no_secret_means_no_signature_header(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.rec.queue(200, {"ok": True, "task_id": "t2", "deduped": True})
            env = {"COMMAND_CENTER_URL": "https://cc.example.test", "CC_API_TOKEN": "t"}
            cc_board.ingest_deck_task(rd, "d2", "S", "desc", env=env)
            req = self.rec.requests[-1]
            self.assertNotIn("x-webhook-signature", req["headers"])
            self.assertEqual(req["headers"]["authorization"], "Bearer t")

    def test_ingest_http_error_stamps_attempted(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.rec.queue(500, {"error": "boom"})
            result = cc_board.ingest_deck_task(rd, "d1", "S", "desc", env=ENV)
            self.assertIsNone(result)
            pm = json.loads((rd / "working" / "checkpoints" / "process_manifest.json").read_text())
            self.assertTrue(pm.get("cc_register_attempted"))
            self.assertNotIn("cc_task_id", pm)

    def test_ingest_urlerror_stamps_attempted(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.rec.queue_raise(urllib.error.URLError("conn refused"))
            result = cc_board.ingest_deck_task(rd, "d1", "S", "desc", env=ENV)
            self.assertIsNone(result)
            pm = json.loads((rd / "working" / "checkpoints" / "process_manifest.json").read_text())
            self.assertTrue(pm.get("cc_register_attempted"))

    def test_patch_phase_contract(self):
        self.rec.queue(200, {"task": {"status": "in_progress"}})
        ok = cc_board.patch_phase(None, "task-xyz", "P0A-INTAKE", "in_progress",
                                  note="Intake started", env=ENV)
        self.assertTrue(ok)
        req = self.rec.requests[-1]
        self.assertEqual(req["method"], "PATCH")
        self.assertEqual(req["url"], "https://cc.example.test/api/tasks/task-xyz")
        body = json.loads(req["body"])
        self.assertEqual(body["phase_id"], "P0A-INTAKE")
        self.assertEqual(body["status"], "in_progress")
        self.assertEqual(body["note"], "Intake started")

    def test_patch_phase_noop_without_config(self):
        ok = cc_board.patch_phase(None, "task-xyz", "P0A-INTAKE", "done", env={})
        self.assertFalse(ok)
        self.assertEqual(self.rec.requests, [])

    def test_patch_unknown_status_is_rejected(self):
        # REGRESSION for the P9-DELIVER bug: 'delivered' is NOT a CC TaskStatus, so
        # the server (mock, mirroring UpdateTaskSchema) rejects it with 400 and
        # patch_phase returns False. The request WAS attempted (proving the mock's
        # rejection — not a client shortcut — produced the False).
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            ok = cc_board.patch_phase(rd, "task-xyz", "P9-DELIVER", "delivered",
                                      note="bundle complete — deck delivered", env=ENV)
            self.assertFalse(ok)
            req = self.rec.requests[-1]
            self.assertEqual(req["method"], "PATCH")
            self.assertEqual(json.loads(req["body"])["status"], "delivered")
            # The failed advance is VISIBLE in the movement receipt (HTTP 400, not ok).
            receipt = json.loads(
                (rd / "working" / "checkpoints" / "cc-board.json").read_text())
            self.assertEqual(receipt["successful_advances"], 0)
            self.assertEqual(receipt["movements"][-1]["http_status"], 400)
            self.assertFalse(receipt["movements"][-1]["ok"])
            self.assertFalse(cc_board.assert_min_one_advance(rd))

    def test_terminal_done_attaches_process_certificate(self):
        # 'done' cert-attach mechanics are STILL supported (the CC-side promotion of a
        # reviewed deck, and reconcile replays, both PATCH 'done' with the cert). The
        # PRODUCER no longer self-closes 'done' (it stops at 'review', see below) — this
        # test pins that a 'done' PATCH attaches the minted PROCESS-CERTIFICATE sha.
        # 'done' is a valid status, so the mock accepts it (200), advance recorded OK.
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            cert_dir = rd / "delivery" / "mydeck-FINAL"
            cert_dir.mkdir(parents=True)
            (cert_dir / "PROCESS-CERTIFICATE.json").write_text(
                json.dumps({"certificate_sha": "abc123def456"}))
            self.rec.queue(200, {"task": {"status": "done"}})
            ok = cc_board.patch_phase(rd, "task-xyz", "P9-DELIVER", "done",
                                      note="bundle complete — deck delivered", env=ENV)
            self.assertTrue(ok)
            body = json.loads(self.rec.requests[-1]["body"])
            self.assertEqual(body["status"], "done")
            self.assertEqual(body["process_certificate_sha"], "abc123def456")
            self.assertIn("delivered", body["note"])
            self.assertTrue(cc_board.assert_min_one_advance(rd))

    def test_terminal_review_attaches_cert_and_qc_scores(self):
        # The PRODUCER close is status='review' (never a self-closed 'done'): it carries
        # the PROCESS-CERTIFICATE sha (ticket INTO review) AND the real per-gate QC
        # scores — both a human-readable summary in the note and a structured qc_scores
        # key. 'review' is a valid status, so the mock accepts it (200).
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            cert_dir = rd / "delivery" / "mydeck-FINAL"
            cert_dir.mkdir(parents=True)
            (cert_dir / "PROCESS-CERTIFICATE.json").write_text(
                json.dumps({"certificate_sha": "cafebabe0001"}))
            _seed_qc_reports(rd, averages={"image_qc_report.json": 8.7})
            self.rec.queue(200, {"task": {"status": "review"}})
            ok = cc_board.patch_phase(rd, "task-xyz", "P9-DELIVER", "review",
                                      note="bundle complete — deck delivered", env=ENV)
            self.assertTrue(ok)
            body = json.loads(self.rec.requests[-1]["body"])
            self.assertEqual(body["status"], "review")
            self.assertEqual(body["process_certificate_sha"], "cafebabe0001")
            # Structured scores present for a lenient CC server.
            self.assertEqual(body["qc_scores"]["gates_graded"], 5)
            self.assertTrue(body["qc_scores"]["overall_pass"])
            self.assertEqual(body["qc_scores"]["min_average"], 8.7)
            # Human/DA-readable summary folded into the (always-accepted) note.
            self.assertIn("QC", body["note"])
            self.assertIn("min=8.7", body["note"])
            self.assertTrue(cc_board.assert_min_one_advance(rd))

    def test_review_strict_server_strips_qc_scores_and_still_transitions(self):
        # DEFENSIVE FALLBACK: an unknown-key-strict CC server 422s the PATCH while the
        # optional qc_scores key is present. patch_phase must retry ONCE without it so
        # the status transition to 'review' still lands (the note keeps the summary).
        class _StrictRec:
            def __init__(self):
                self.requests = []

            def __call__(self, req, timeout=None):
                body = req.data.decode("utf-8") if req.data else ""
                self.requests.append(body)
                parsed = json.loads(body) if body else {}
                if "qc_scores" in parsed:
                    raise urllib.error.HTTPError(
                        req.full_url, 422, "Unrecognized key", {},
                        io.BytesIO(b'{"error":"Unrecognized key: qc_scores"}'))
                return _FakeResp(200, {"task": {"status": "review"}})

        strict = _StrictRec()
        orig = cc_board.urllib.request.urlopen
        cc_board.urllib.request.urlopen = strict
        try:
            with tempfile.TemporaryDirectory() as d:
                rd = Path(d)
                cert_dir = rd / "delivery" / "mydeck-FINAL"
                cert_dir.mkdir(parents=True)
                (cert_dir / "PROCESS-CERTIFICATE.json").write_text(
                    json.dumps({"certificate_sha": "deadbeef0002"}))
                _seed_qc_reports(rd)
                ok = cc_board.patch_phase(rd, "task-xyz", "P9-DELIVER", "review",
                                          note="bundle complete", env=ENV)
                self.assertTrue(ok, "review transition must survive the strict-server 422")
                # Two attempts: first WITH qc_scores (422), retry WITHOUT it (200).
                self.assertEqual(len(strict.requests), 2)
                self.assertIn("qc_scores", json.loads(strict.requests[0]))
                retry = json.loads(strict.requests[1])
                self.assertNotIn("qc_scores", retry)
                self.assertEqual(retry["status"], "review")
                self.assertEqual(retry["process_certificate_sha"], "deadbeef0002")
                self.assertIn("QC", retry["note"])  # summary still rode in on the note
                self.assertTrue(cc_board.assert_min_one_advance(rd))
        finally:
            cc_board.urllib.request.urlopen = orig

    def test_collect_qc_summary_reads_governed_reports(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            _seed_qc_reports(rd, averages={"copy_qc_report.json": 9.4,
                                           "prompt_qc_report.json": 8.6})
            summary = cc_board.collect_qc_summary(rd)
            self.assertEqual(summary["gates_graded"], 5)
            self.assertTrue(summary["overall_pass"])
            self.assertEqual(summary["min_average"], 8.6)
            self.assertEqual(summary["autofails_total"], 0)
            # An empty run dir yields a clean empty summary (never raises).
        with tempfile.TemporaryDirectory() as d2:
            empty = cc_board.collect_qc_summary(Path(d2))
            self.assertEqual(empty["gates_graded"], 0)
            self.assertFalse(empty["overall_pass"])
            self.assertIsNone(empty["min_average"])
        self.assertEqual(cc_board.collect_qc_summary(None)["gates_graded"], 0)

    def test_collect_qc_summary_flags_autofail_as_not_pass(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            _seed_qc_reports(rd, autofails={"image_qc_report.json": ["AF-I1"]})
            summary = cc_board.collect_qc_summary(rd)
            self.assertEqual(summary["autofails_total"], 1)
            self.assertFalse(summary["overall_pass"])

    def test_post_qc_activities_posts_one_per_gate_with_scores(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            _seed_qc_reports(rd, averages={"speech_qc_report.json": 8.8})
            for _ in range(5):
                self.rec.queue(201, {"id": "act", "activity_type": "updated"})
            posted = cc_board.post_qc_activities(rd, "task-xyz", env=ENV)
            self.assertEqual(posted, 5)
            # Each activity carries the structured scores key + a numeric tail.
            last = json.loads(self.rec.requests[-1]["body"])
            self.assertIn("scores", last)
            self.assertIn("avg=", last["message"])
            self.assertIn("autofails=", last["message"])

    def test_post_activity_uses_activities_endpoint(self):
        # Mid-run phase progress is an ACTIVITY (POST /activities), never a status
        # change — so it carries NO status field and cannot trip the cert done-gate.
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.rec.queue(201, {"id": "act-1", "activity_type": "updated"})
            ok = cc_board.post_activity(rd, "task-xyz", "P4-RENDER",
                                        "12 slides rendered", env=ENV)
            self.assertTrue(ok)
            req = self.rec.requests[-1]
            self.assertEqual(req["method"], "POST")
            self.assertEqual(req["url"],
                             "https://cc.example.test/api/tasks/task-xyz/activities")
            body = json.loads(req["body"])
            self.assertEqual(body["activity_type"], "updated")
            self.assertNotIn("status", body)
            self.assertIn("P4-RENDER", body["message"])
            self.assertIn("12 slides rendered", body["message"])
            self.assertTrue(cc_board.assert_min_one_advance(rd))


class StampTest(unittest.TestCase):
    def test_stamp_merges_without_clobber(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            pm = rd / "working" / "checkpoints" / "process_manifest.json"
            pm.parent.mkdir(parents=True)
            pm.write_text(json.dumps({
                "cc_register_attempted": True,
                "phase_attestations": [{"phase_id": "P0A-INTAKE"}]
            }))
            self.assertTrue(cc_board.stamp_task_id(rd, "task-xyz"))
            got = json.loads(pm.read_text())
            self.assertEqual(got["cc_task_id"], "task-xyz")
            # Original fields preserved
            self.assertTrue(got["cc_register_attempted"])
            self.assertIn("phase_attestations", got)

    def test_stamp_creates_manifest_when_absent(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            self.assertTrue(cc_board.stamp_task_id(rd, "task-1"))
            got = json.loads(
                (rd / "working" / "checkpoints" / "process_manifest.json").read_text())
            self.assertEqual(got["cc_task_id"], "task-1")

    def test_stamp_empty_id_is_noop(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(cc_board.stamp_task_id(Path(d), ""))


if __name__ == "__main__":
    unittest.main(verbosity=2)

#!/usr/bin/env python3
"""PD-085 gate: `resume` sends the company id with the session id.

The worker binds a session to the company that minted it and answers 403 to a
renew that omits or mismatches `company_id`. This test replaces `_http` with a
recorder — no network — and asserts on the body it is handed.

Run: python3 test/test_pd085_resume_company_id.py

Rows:
  A1  a record with a company_id -> body carries BOTH session_id and company_id
  A1b a record with no company_id -> rc 2, the exact message, and no request
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE.parent / "bridge"))

import intake_bridge as ib  # noqa: E402

MESSAGE = "session.json has no company_id; cannot resume"


def _run_resume(record: dict) -> tuple[int, list[dict], str]:
    """Drive cmd_resume with a recorder in `_http`; return (rc, calls, stderr)."""
    calls: list[dict] = []

    def recorder(method, url, *, token=None, body=None, timeout=20):
        calls.append({"method": method, "url": url, "token": token, "body": body})
        return 201, {"token": "new-token", "capability_url": "https://w/c/new-token",
                     "session_id": record.get("session_id")}

    saved = ib._http
    ib._http = recorder
    saved_env = os.environ.get("INTAKE_ADMIN_TOKEN")
    os.environ["INTAKE_ADMIN_TOKEN"] = "admin-tok"
    err = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as td:
            run_dir = pathlib.Path(td) / record.get("presentation_id", "pid")
            run_dir.mkdir()
            (run_dir / "session.json").write_text(json.dumps(record), encoding="utf-8")
            args = types.SimpleNamespace(
                worker_url="https://worker.example", presentation_id=record["presentation_id"],
                runs_dir=td)
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                rc = ib.cmd_resume(args)
    finally:
        ib._http = saved
        if saved_env is None:
            os.environ.pop("INTAKE_ADMIN_TOKEN", None)
        else:
            os.environ["INTAKE_ADMIN_TOKEN"] = saved_env
    return rc, calls, err.getvalue()


class ResumeCompanyId(unittest.TestCase):
    def test_a1_body_carries_session_and_company(self):
        rc, calls, err = _run_resume({
            "presentation_id": "pid-a1", "session_id": "sess-abc", "company_id": "acme",
            "token": "old-token"})
        self.assertEqual(rc, 0, err)
        self.assertEqual(len(calls), 1, "exactly one renew request")
        self.assertEqual(calls[0]["method"], "POST")
        self.assertTrue(calls[0]["url"].endswith("/api/sessions/renew"), calls[0]["url"])
        body = calls[0]["body"]
        self.assertIsInstance(body, dict)
        self.assertEqual(body.get("session_id"), "sess-abc", body)
        self.assertEqual(body.get("company_id"), "acme", body)
        self.assertEqual(set(body), {"session_id", "company_id"}, body)

    def test_a1b_no_company_exits_two_without_a_request(self):
        rc, calls, err = _run_resume({
            "presentation_id": "pid-a1b", "session_id": "sess-abc", "token": "old-token"})
        self.assertEqual(rc, 2, err)
        self.assertIn(MESSAGE, err)
        self.assertEqual(calls, [], "must not call the worker without a company id")


if __name__ == "__main__":
    unittest.main(verbosity=2)

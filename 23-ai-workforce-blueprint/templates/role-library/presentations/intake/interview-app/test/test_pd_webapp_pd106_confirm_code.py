#!/usr/bin/env python3
"""PD-106 gate: the confirmation code reaches the mint and the page sends it.

`new` gains `--confirm-code` (default off, so behaviour is unchanged) and
prints the minted code on its own line; the page carries it back to the worker
as the `x-confirm-code` header on every session call. No network: `_http` and
the payload builder are replaced.

Run: python3 test/test_pd_webapp_pd106_confirm_code.py

Rows:
  A1e  `new --confirm-code` -> mint body carries want_confirm_code=True and
       stdout has the code on its own line
  A1f  `new` with no flag -> want_confirm_code=False and no code line
  A1g  the page sends x-confirm-code, and the two page copies are byte-identical
"""
from __future__ import annotations

import contextlib
import filecmp
import io
import json
import os
import pathlib
import sys
import tempfile
import types
import unittest

HERE = pathlib.Path(__file__).resolve().parent
APP = HERE.parent
sys.path.insert(0, str(APP))
sys.path.insert(0, str(APP / "bridge"))

import intake_bridge as ib  # noqa: E402

PAYLOAD = {"question_set": "standard", "questions": [
    {"id": "offer_name", "order": 1, "prompt": "Your offer?", "kind": "text", "required": True},
]}


def _run_new(confirm_code: bool, code: str | None) -> tuple[int, list[dict], str]:
    calls: list[dict] = []

    def recorder(method, url, *, token=None, body=None, timeout=20):
        calls.append({"method": method, "url": url, "token": token, "body": body})
        resp = {"token": "t0k", "session_id": "sess-1", "capability_url": "https://w/c/t0k",
                "run_id": "RUN-1", "intake_session_id": "intake-1"}
        if code:
            resp["confirm_code"] = code
        return 201, resp

    saved_http = ib._http
    saved_builder = ib._build_questions_payload
    saved_env = os.environ.get("INTAKE_ADMIN_TOKEN")
    ib._http = recorder
    ib._build_questions_payload = lambda presentation_id: PAYLOAD  # no subprocess
    os.environ["INTAKE_ADMIN_TOKEN"] = "admin-tok"
    out = io.StringIO()
    try:
        with tempfile.TemporaryDirectory() as td:
            args = types.SimpleNamespace(
                worker_url="https://worker.example", company_id="acme",
                installation_id="install-test", title="PD-106 deck",
                recipient_chat_id=None, runs_dir=td, confirm_code=confirm_code)
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                rc = ib.cmd_new(args)
    finally:
        ib._http = saved_http
        ib._build_questions_payload = saved_builder
        if saved_env is None:
            os.environ.pop("INTAKE_ADMIN_TOKEN", None)
        else:
            os.environ["INTAKE_ADMIN_TOKEN"] = saved_env
    return rc, calls, out.getvalue()


class NewConfirmCode(unittest.TestCase):
    def test_a1e_flag_mints_a_code_and_prints_it_on_its_own_line(self):
        rc, calls, stdout = _run_new(True, "123456")
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 1, "exactly one mint request")
        body = calls[0]["body"]
        self.assertTrue(body.get("want_confirm_code"), body)
        lines = [ln for ln in stdout.splitlines() if ln.strip()]
        self.assertIn("confirm_code: 123456", lines, lines)

    def test_a1f_default_is_off_and_changes_nothing(self):
        rc, calls, stdout = _run_new(False, None)
        self.assertEqual(rc, 0)
        self.assertFalse(calls[0]["body"].get("want_confirm_code"))
        self.assertNotIn("confirm_code", stdout, "no code line when none was minted")

    def test_a1f2_cli_accepts_the_flag_and_defaults_to_off(self):
        # Through the real parser: absent -> False, present -> True.
        captured: list = []
        saved = ib.cmd_new
        ib.cmd_new = lambda args: (captured.append(args), 0)[1]
        base = ["new", "--worker-url", "https://w", "--company-id", "acme",
                "--installation-id", "install-test", "--title", "T"]
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(ib.main(base), 0)
                self.assertFalse(captured[-1].confirm_code, "default must be off")
                self.assertEqual(ib.main(base + ["--confirm-code"]), 0)
                self.assertTrue(captured[-1].confirm_code)
        finally:
            ib.cmd_new = saved


class PageSendsCode(unittest.TestCase):
    def test_a1g_page_sends_the_header_and_copies_are_identical(self):
        page = (APP / "pages" / "index.html").read_text(encoding="utf-8")
        self.assertIn('x-confirm-code', page, "the page must send the code as a header")
        api_at = page.index("function apiJson(")
        self.assertLess(page.index('"x-confirm-code"'), api_at + 1200,
                        "the header belongs in apiJson so every session call carries it")
        self.assertTrue(filecmp.cmp(APP / "pages" / "index.html",
                                    APP / "deployed-r2" / "public" / "index.html",
                                    shallow=False), "page copies must stay byte-identical")


if __name__ == "__main__":
    unittest.main(verbosity=2)

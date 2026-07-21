#!/usr/bin/env python3
"""Regression suite for the live-verification browser session (T2-01).

`ghl_builder.render_check` drives the headless browser through
`ghl_builder.browser_cmd`, and `browser_cmd` calls
`browser_manager.assert_session_active` — it REFUSES outside an active
`browser_manager.browser_session()`. Nothing on the live verification path
acquired one; the builder modules open their own sessions for the BUILD phase
and those are closed by the time the separate verification step runs.

Measured on untouched `origin/main`, one live page:

    http = None
    PASS = False
    render_errors = ["render_check exception: RuntimeError: REFUSE (singleton
                     gateway): ghl_builder.browser_cmd emitted outside an active
                     browser_session() ..."]

— a verdict reached with no navigation attempted, on the ONLY production
acceptance path for live page verification. `render_check`'s own docstring
claimed the caller acquired the session.

These tests use a CONTROLLED FAKE TRANSPORT: `ghl_builder.subprocess.run` is
replaced with a recorder that returns a scripted rendered DOM. Nothing real is
launched, and the fixture is produced by the test, never by the code under test.

Both directions are proven:
  * the live path now reaches an actual navigation carrying the preview URL, and
    the singleton refusal never appears;
  * the guard it satisfies is still live — calling `render_check` outside the
    bracket still refuses, so the fix is the session, not a weakened guard;
  * `verify_all` holds ONE session for the whole loop, not one per page.

Run:
    python3 tests/unit/ghl-verify-live-browser-session.test.py
    or: pytest tests/unit/ghl-verify-live-browser-session.test.py
"""
from __future__ import annotations

import os
import subprocess as _real_subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_TOOLS = _REPO_ROOT / "06-ghl-install-pages" / "tools"
assert _TOOLS.is_dir(), f"skill 06 tools not found at {_TOOLS}"
sys.path.insert(0, str(_TOOLS))

os.environ.setdefault("AGENT_BROWSER_HEADED", "false")

import browser_manager  # noqa: E402
import ghl_builder  # noqa: E402
import ghl_verify  # noqa: E402

MARKER = "MARKER-T201-CHECK"
# render_check requires visible_text_len >= ghl_builder.MIN_RENDERED_TEXT (400)
# before it will report ok=True, so the scripted DOM carries real body copy
# rather than a stub. Built from a repeated sentence so the length is obvious
# and the assertion below pins it against the module's own constant.
_PARA = (
    "This paragraph carries real visible body copy so the rendered page clears "
    "the minimum rendered-text floor that render_check enforces on every page "
    "before it will report a pass. "
)
RENDERED_DOM = (
    "<html><body><h1>A headline that is long enough to be real content</h1>"
    + "".join(f"<p>{_PARA}</p>" for _ in range(4))
    + f"<p>{MARKER}</p></body></html>"
)


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


class _Transport:
    """Records every agent-browser argv and answers it deterministically."""

    def __init__(self, nav_status: int = 200):
        self.calls: list[list[str]] = []
        self.nav_status = nav_status

    def run(self, argv, **kwargs):
        self.calls.append(list(argv))
        verb = ""
        for i, tok in enumerate(argv):
            if tok in ("open", "get", "screenshot", "console"):
                verb = tok
                break
        if verb == "open":
            return _FakeCompleted(0, f"navigated status: {self.nav_status}\n")
        if verb == "get":
            return _FakeCompleted(0, RENDERED_DOM)
        if verb == "screenshot":
            return _FakeCompleted(0, "")
        if verb == "console":
            return _FakeCompleted(0, "")
        return _FakeCompleted(0, "")

    def navigated_urls(self):
        urls = []
        for argv in self.calls:
            if "open" in argv:
                idx = argv.index("open")
                if idx + 1 < len(argv):
                    urls.append(argv[idx + 1])
        return urls


class _Harness:
    """Installs the fake transport and neutralises the binary version pin.

    The version pin asserts the LOCAL agent-browser matches 0.27.0. That is a
    property of the box, not of the defect under test, so it is stubbed — and
    stubbed only here, never in the shipped path."""

    def __enter__(self):
        self.transport = _Transport()
        # render_check does a function-local `import subprocess`, so the name is
        # resolved on the module object at call time — patching the module's
        # attribute is what reaches it.
        self._real_run = _real_subprocess.run
        self._real_pin = browser_manager.assert_agent_browser_version
        self._real_shot = ghl_builder.png_blank_report
        _real_subprocess.run = self.transport.run
        browser_manager.assert_agent_browser_version = lambda *a, **k: None
        # A screenshot is never taken through the fake transport, so the pixel
        # inspector would report an unreadable file. Report "not determinable",
        # which render_check already treats as non-fatal.
        ghl_builder.png_blank_report = lambda *a, **k: {
            "blank": False, "determinable": False, "reason": "faked_transport"
        }
        return self.transport

    def __exit__(self, *exc):
        _real_subprocess.run = self._real_run
        browser_manager.assert_agent_browser_version = self._real_pin
        ghl_builder.png_blank_report = self._real_shot
        return False


def _page(step="probe", url="https://example.com/preview/abc"):
    return {"step": step, "page_id": f"pid-{step}", "preview_url": url, "marker": MARKER}


def _singleton_refusals(record):
    return [e for e in (record.get("render_errors") or []) if "singleton gateway" in e]


class TestLiveVerificationAcquiresASession(unittest.TestCase):
    def test_verify_page_live_no_longer_refuses_on_the_singleton_gateway(self):
        with _Harness() as transport, tempfile.TemporaryDirectory() as rd:
            rec = ghl_verify.verify_page(_page(), run_dir=rd, live=True)
        self.assertEqual(
            _singleton_refusals(rec), [],
            "the live path still refuses on the singleton gateway — no navigation happened",
        )
        self.assertEqual(
            transport.navigated_urls(), ["https://example.com/preview/abc"],
            "the live path did not navigate to the preview url",
        )

    def test_verify_page_live_reports_a_real_http_status(self):
        with _Harness() as transport, tempfile.TemporaryDirectory() as rd:
            rec = ghl_verify.verify_page(_page(), run_dir=rd, live=True)
        self.assertEqual(rec["http"], 200, f"render_errors={rec['render_errors']}")
        self.assertTrue(rec["marker_in_rendered_dom"])
        self.assertTrue(rec["PASS"], f"render_errors={rec['render_errors']}")
        self.assertGreaterEqual(len(transport.calls), 4, "the four-step render sequence did not run")

    def test_verify_all_live_verifies_every_page(self):
        pages = [_page("one", "https://example.com/preview/one"),
                 _page("two", "https://example.com/preview/two")]
        with _Harness() as transport, tempfile.TemporaryDirectory() as rd:
            out = ghl_verify.verify_all(rd, pages, live=True, run_id="t201", version="test")
        for rec in out["raw"]:
            self.assertEqual(_singleton_refusals(rec), [], f"step {rec['step']} refused")
            self.assertEqual(rec["http"], 200, f"step {rec['step']}: {rec['render_errors']}")
        self.assertEqual(
            transport.navigated_urls(),
            ["https://example.com/preview/one", "https://example.com/preview/two"],
        )
        self.assertEqual(out["trust"], "LIVE")

    def test_verify_all_holds_ONE_session_for_the_whole_loop(self):
        """Not one per page: the session name is stable and the loop runs inside it."""
        seen = []
        pages = [_page("one"), _page("two"), _page("three")]
        real_render = ghl_builder.render_check

        def spy(*a, **k):
            seen.append((browser_manager.session_active(),
                         browser_manager._ACTIVE_SESSION_NAME))
            return real_render(*a, **k)

        with _Harness(), tempfile.TemporaryDirectory() as rd:
            ghl_builder.render_check = spy
            ghl_verify.render_check_spy_installed = True
            try:
                ghl_verify.verify_all(rd, pages, live=True, run_id="t201", version="test")
            finally:
                ghl_builder.render_check = real_render
        self.assertTrue(seen, "render_check was never reached")
        self.assertTrue(all(active for active, _ in seen),
                        "a page rendered outside an active session")
        names = {name for _, name in seen}
        self.assertEqual(len(names), 1, f"more than one session across the loop: {names}")


class TestTheGuardIsStillLive(unittest.TestCase):
    """The fix must be the session, never a weakened guard."""

    def test_render_check_outside_the_bracket_still_refuses(self):
        with _Harness(), tempfile.TemporaryDirectory() as rd:
            self.assertFalse(browser_manager.session_active())
            res = ghl_builder.render_check(
                "https://example.com/preview/abc", MARKER, run_dir=rd, step="bare", timeout=5,
            )
        errs = [e for e in (res.get("render_errors") or []) if "singleton gateway" in e]
        self.assertTrue(
            errs,
            "browser_cmd no longer refuses outside a session — the guard was weakened, "
            "which is not the fix this item asked for",
        )
        self.assertIsNone(res.get("http"))

    def test_browser_cmd_refuses_outside_and_succeeds_inside(self):
        with self.assertRaises(RuntimeError):
            ghl_builder.browser_cmd("open", "https://example.com")
        with browser_manager.browser_session("guard-probe"):
            self.assertIn("open", ghl_builder.browser_cmd("open", "https://example.com"))


class TestMockModeTakesNoSession(unittest.TestCase):
    def test_mock_mode_does_not_open_a_browser_session(self):
        seen = []

        def fetcher(url, marker):
            seen.append((browser_manager.session_active(), url))
            return {"ok": True, "http": 200, "marker_found": True,
                    "render_errors": [], "dom_bytes": 1234, "visible_text_len": 200}

        with tempfile.TemporaryDirectory() as rd:
            out = ghl_verify.verify_all(rd, [_page("m1")], live=False, fetcher=fetcher,
                                        run_id="t201", version="test")
        self.assertTrue(seen, "the mock fetcher was never called")
        self.assertFalse(any(active for active, _ in seen),
                         "mock mode opened a browser session it never uses")
        self.assertEqual(out["trust"], "MOCK")


if __name__ == "__main__":
    unittest.main(verbosity=2)

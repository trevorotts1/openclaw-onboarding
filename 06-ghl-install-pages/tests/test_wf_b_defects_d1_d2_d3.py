"""WF-B defects D1/D2/D3 — regression locks for the shipped Playwright lane.

D1  _RealPlaywrightHandle must not pass ``devtools=`` to
    playwright's launch_persistent_context (no such kwarg -> TypeError, the
    lane cannot launch), while headless=True stays a LITERAL at the launch
    site (the D6 static headless-guard audit keys off it) and the D6/P3
    refusal chain stays intact.
D2  the bridge-seeded page is the single source of truth: the seed receipt
    hands back the exact page object that was seeded, so callers navigate THAT
    page instead of opening a second one (a second page reads as
    user_not_logged_in despite a successful mint).
D3  PLAYWRIGHT_SEED_JS writes cookie `a` (and the token cookies) RAW — no
    encodeURIComponent — exactly like tools/inject-ghl-auth.sh and the SPA's
    own setter; percent-escaping turns + / = into %2B %2F %3D and atob throws.

Offline only: no real browser is launched. D1 inspects the source text and
exercises the launch call through a recording double; D3 evaluates the
generated JS's cookie-write semantics against a tiny Python model.
"""
from __future__ import annotations

import ast
import base64
import json
import re
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import browser_manager as bm  # noqa: E402
import ghl_auth as ga  # noqa: E402

_BM_SRC = (_TOOLS_DIR / "browser_manager.py").read_text(encoding="utf-8")

# Synthetic (fake) credential shapes — never real values. This apiKey's base64
# encoding contains '+', '/' AND '=' trailing padding, which is exactly the
# alphabet encodeURIComponent mangles (D3).
FAKE_API_KEY = "+JRR2K?pO~Pq"
FAKE_API_KEY_B64 = ("eyJhcGlLZXkiOiIrSlJSMks/cE9+UHEiLCJ1c2VySWQiOiJ1MSIsImNvbXBh"
                    "bnlJZCI6ImMxIn0=")


# ── D1 ──────────────────────────────────────────────────────────────────────

class RecordingContext:
    """Stands in for playwright's BrowserContext: records the kwargs the launch
    call receives and never spawns anything."""

    def __init__(self, recorder, kwargs):
        self.recorder = recorder
        self.kwargs = kwargs
        self.pages = []

    def close(self):
        pass


class RecordingChromium:
    def __init__(self, recorder):
        self.recorder = recorder

    def launch_persistent_context(self, profile_dir, **kwargs):
        # Real playwright raises TypeError on an unknown kwarg; assert the real
        # signature contract here so the double cannot silently accept devtools.
        allowed = {"headless", "args", "channel", "executable_path",
                   "ignore_https_errors", "locale", "timezone_id",
                   "user_agent", "viewport", "permissions"}
        unexpected = set(kwargs) - allowed
        if unexpected:
            raise TypeError(
                f"unexpected keyword argument {sorted(unexpected)[0]!r}")
        self.recorder.append({"profile_dir": profile_dir, "kwargs": kwargs})
        return RecordingContext(self.recorder, kwargs)


class RecordingPlaywright:
    def __init__(self, recorder):
        self.chromium = RecordingChromium(recorder)

    def stop(self):
        pass


class TestD1LaunchKwargs:
    def test_launch_persistent_context_omits_devtools(self, monkeypatch):
        """The real handle factory must launch with no devtools kwarg. Before
        the fix this raised TypeError and the lane could not start."""
        recorder = []
        import playwright.sync_api as pw_sync  # noqa: F401 - import contract

        monkeypatch.setattr(
            pw_sync, "sync_playwright",
            lambda: type("P", (), {"start": lambda self: RecordingPlaywright(recorder)})())
        handle = bm._RealPlaywrightHandle("/tmp/defect-d1-profile",
                                          bm.pw_launch_options({}))
        assert len(recorder) == 1
        kwargs = recorder[0]["kwargs"]
        assert "devtools" not in kwargs
        assert kwargs["headless"] is True
        handle.close()

    def test_launch_site_keeps_literal_headless_true(self):
        """D6 static audit requires the literal at the launch call."""
        site = _BM_SRC.split("class _RealPlaywrightHandle")[1]
        # the whole call expression: from the open paren to the line that is
        # just a closing paren (comments inside it are stripped below)
        call = site.split("launch_persistent_context(", 1)[1]
        call = call.split("\n        )", 1)[0]
        code = "\n".join(line.split("#", 1)[0] for line in call.splitlines())
        assert "headless=True" in code.replace(" ", "")
        assert "devtools" not in code

    def test_refusal_chain_still_rejects_devtools_and_headed(self):
        for overrides in ({"devtools": True}, {"headless": False}):
            with pytest.raises(bm.PWLaunchRefused):
                bm.pw_launch_options({}, overrides)
        # inherited headed config is refused by the D6 headless_guard
        with pytest.raises(RuntimeError, match="headless guard"):
            bm.pw_launch_options({"AGENT_BROWSER_HEADED": "true"}, {})

    def test_launch_options_verify_request_shape_not_kwarg(self):
        opts = bm.pw_launch_options({}, {"devtools": False, "headless": True})
        assert opts["headless"] is True
        assert "devtools" not in opts


# ── D2 ──────────────────────────────────────────────────────────────────────

class _Page:
    def __init__(self, recorder, identity):
        self.recorder = recorder
        self.identity = identity

    def evaluate(self, js, arg=None):
        self.recorder.append({"page": self, "js": js, "seed": arg})
        return self.identity


class _Context:
    def __init__(self, pages=(), identity=None):
        self.recorder = []
        self.pages = list(pages)
        self._identity = identity if identity is not None else {}

    def new_page(self):
        page = _Page(self.recorder, self._identity)
        self.pages.append(page)
        return page


def _minimal_seed():
    return {
        "indexeddb": {"database": "firebaseLocalStorageDb",
                      "store": "firebaseLocalStorage",
                      "keyPath": "fbase_key",
                      "entry": {"fbase_key": "k", "value": {
                          "uid": "u-fake", "emailVerified": False,
                          "isAnonymous": False, "providerData": [],
                          "stsTokenManager": {"refreshToken": "r", "accessToken": "a",
                                              "expirationTime": 0}}}},
        "login_current": {"method": "GET", "url": "https://example.invalid/",
                          "headers": {"token-id": "t"},
                          "response_to_cookies": {}},
        "cookies": {"a_name": "a", "a_shape": ["apiKey", "userId", "companyId"],
                    "token_map": {}, "attrs": {"path": "/", "maxAge": 31536000}},
    }


class TestD2SeededPageIsSourceOfTruth:
    def test_receipt_page_is_the_page_that_carries_the_seed(self):
        """The page the bridge seeded must be the page callers are directed to
        navigate — with a pre-existing pages[0] it must NOT be a new page."""
        first = _Page([], {"userId": "u1", "companyId": "c1", "locationId": "L1"})
        ctx = _Context(pages=[first])
        receipt = ga.bridge_seed_into_context(
            ctx, _minimal_seed(),
            identity_fetcher=lambda _c: {"userId": "u1", "companyId": "c1",
                                         "locationId": "L1"})
        assert receipt["ok"] is True
        assert receipt.page is first                      # the seeded page
        assert len(ctx.pages) == 1                        # no second page opened
        assert "page" not in receipt                      # never a serialized key
        json.dumps(receipt)                               # still JSON-safe

    def test_default_in_page_path_records_the_same_page(self):
        ctx = _Context()
        receipt = ga.bridge_seed_into_context(ctx, _minimal_seed())
        assert receipt.page is ctx.pages[0]
        assert ctx.recorder[-1]["page"] is receipt.page
        assert ctx.recorder[-1]["js"] == ga.PLAYWRIGHT_SEED_JS

    def test_expired_receipt_still_names_the_seeded_page(self):
        ctx = _Context()
        receipt = ga.bridge_seed_into_context(
            ctx, _minimal_seed(), identity_fetcher=lambda _c: {})
        assert receipt["state"] == "SESSION_EXPIRED"
        assert receipt.page is ctx.pages[0]

    def test_resolve_page_contract_documented(self):
        doc = ga._resolve_page.__doc__ or ""
        assert "SINGLE SOURCE OF TRUTH" in doc


# ── D3 ──────────────────────────────────────────────────────────────────────

_COOKIE_A_WRITE = re.compile(r"document\.cookie\s*=\s*ck\.a_name\s*\+\s*'='\s*\+\s*(.+?)\s*\+\s*attrs")


class TestD3SeedWritesRawCookies:
    def test_cookie_a_write_has_no_encodeuri(self):
        assert "encodeURIComponent" not in ga.PLAYWRIGHT_SEED_JS
        match = _COOKIE_A_WRITE.search(ga.PLAYWRIGHT_SEED_JS)
        assert match, "cookie `a` write not found in PLAYWRIGHT_SEED_JS"
        assert match.group(1) == "btoa(JSON.stringify(aObj))"

    def test_injector_ground_truth_also_writes_raw(self):
        """The proven injector is the contract: it writes btoa output raw."""
        injector = (_TOOLS_DIR / "inject-ghl-auth.sh").read_text(encoding="utf-8")
        assert "encodeURIComponent" not in injector
        assert "setCookie(ckA.a_name, btoa(JSON.stringify(aObj)))" in injector

    def test_base64_alphabet_survives_atob_roundtrip(self):
        """The synthetic key's base64 carries + / and = — the characters
        percent-escaping destroyed. Raw cookie value must atob back to the
        identical JSON object."""
        obj = {"apiKey": FAKE_API_KEY, "userId": "u1", "companyId": "c1"}
        raw = base64.b64encode(
            json.dumps(obj, separators=(",", ":")).encode()).decode()
        assert raw == FAKE_API_KEY_B64
        assert "+" in raw and "/" in raw and raw.endswith("=")
        # What the OLD seed produced, and why the SPA's raw getter died on it:
        escaped = raw.replace("+", "%2B").replace("/", "%2F").replace("=", "%3D")
        assert escaped != raw
        with pytest.raises(Exception):
            base64.b64decode(escaped, validate=True)  # atob semantics: throws
        # What the CORRECTED seed produces:
        assert json.loads(base64.b64decode(raw).decode()) == obj

    def test_token_cookie_writes_carry_no_encoding(self):
        """D3 intent: the token cookie value goes in RAW (the SPA atob()s it).
        D5 kept this — the value moved into `val` so the login/current `token`
        alias can feed custom-firebase-token; the write still carries no
        escaping. Assert the INTENT (raw write, no encoder), not the spelling."""
        tmpl = ga.PLAYWRIGHT_SEED_JS
        loop = tmpl.split("for (const [field, name] of Object.entries(ck.token_map))")[1]
        body = loop.split("}", 1)[0]
        assert "encodeURIComponent" not in body
        assert "document.cookie = name + '=' + val + attrs" in body
        assert "const val = i[field]" in body

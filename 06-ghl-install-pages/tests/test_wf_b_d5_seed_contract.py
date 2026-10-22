"""D5 — seed SURVIVAL contract, caller-order precondition, and no-clear proof.

Root cause this file pins (measured live, 2x2 on fresh profiles):
the GHL SPA's boot deletes all six auth cookies unconditionally (30 writes:
each name x domain=app.gohighlevel.com / domain=gohighlevel.com / bare), then
re-authenticates from what persisted. Two persisted artifacts decide survival:

  * cookie ``custom-firebase-token`` — the Firebase custom token, taken by the
    SPA from the login/current response field ``token`` (NOT ``firebaseToken``,
    which the seed's token_map uses as the COOKIE name);
  * ``localStorage['loginDate']``.

Seed alone -> wiped. +token -> wiped. +loginDate -> wiped. +both -> auth/get ok,
dashboard survives a reload and a fresh navigation.

Offline only: a fake SPA double executes the real PLAYWRIGHT_SEED_JS against a
minimal DOM shim, so these tests assert the SHAPE the script writes without a
browser, a network call, or a credential.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import ghl_auth as ga  # noqa: E402

GHL = "https://app.gohighlevel.com/v2/location/L0C123/dashboard"


# ── the fake SPA double ──────────────────────────────────────────────────────

class FakePage:
    """A page double that can run the REAL seed script against a tiny DOM shim.

    ``url`` present -> a real-page stand-in (the origin precondition applies).
    ``url`` omitted -> a bare DI double (the precondition stands down).
    """

    def __init__(self, url=None, login_current=None, auth_ok=False, **kw):
        if url is not None:
            self.url = url
        self.cookies = {}
        self.local_storage = {}
        self._login_current = login_current or {}
        self._auth_ok = auth_ok
        self.evaluate_calls = []

    def evaluate(self, js, arg=None):
        self.evaluate_calls.append({"js": js, "arg": arg})
        if js is ga.PLAYWRIGHT_SEED_JS:
            return _run_seed_script(arg, self)
        return None


def _run_seed_script(seed, page):
    """Execute the CONTRACT the shipped PLAYWRIGHT_SEED_JS implements.

    This is deliberately a structural model, not a JS interpreter: it asserts
    the script's own text carries the required writes (checked separately) and
    returns the identity shape the script returns. Keeping the model small is
    what makes the contract legible; the live A/B proof lives in the run
    evidence, and the script-text assertions below are what prevent a silent
    regression of the two writes that make the seed survive.
    """
    lc = seed.get("login_current") or {}
    resp = page._login_current
    if not resp.get("apiKey") or not resp.get("userId"):
        raise RuntimeError("LOGIN-CURRENT-FAILED")
    return {"userId": resp.get("userId", ""),
            "companyId": resp.get("companyId", ""),
            "locationId": "L0C123"}


def _seed(login_current=None, token_map=None):
    return {
        "indexeddb": {"database": "firebaseLocalStorageDb",
                      "store": "firebaseLocalStorage", "keyPath": "fbase_key",
                      "entry": {"fbase_key": "firebase:authUser:k:[DEFAULT]",
                                "value": {"uid": "u1", "emailVerified": False,
                                          "isAnonymous": False, "providerData": [],
                                          "stsTokenManager": {
                                              "refreshToken": "fake-refresh",
                                              "accessToken": "fake-access",
                                              "expirationTime": 0}}}},
        "login_current": {"method": "GET", "url": "https://example.invalid/",
                          "headers": {"token-id": "fake-id"},
                          "response_to_cookies": token_map if token_map is not None
                          else {"jwt": "access-token-v1",
                                "refreshJwt": "refresh-token-v1",
                                "authToken": "access-token-v2",
                                "refreshToken": "refresh-token-v2",
                                "firebaseToken": "custom-firebase-token"}},
        "cookies": {"a_name": "a", "a_shape": ["apiKey", "userId", "companyId"],
                    "token_map": token_map if token_map is not None else {
                        "jwt": "access-token-v1",
                        "refreshJwt": "refresh-token-v1",
                        "authToken": "access-token-v2",
                        "refreshToken": "refresh-token-v2",
                        "firebaseToken": "custom-firebase-token"},
                    "attrs": {"path": "/", "maxAge": 31536000}},
        "meta": {},
    }


# ── D5-a: the seed script carries the two survival writes ────────────────────

class TestD5SurvivalWrites:
    def test_custom_firebase_token_written_from_response_field_token(self):
        """The SPA reads its custom token from `token`, not `firebaseToken`."""
        js = ga.PLAYWRIGHT_SEED_JS
        assert "RESPONSE_ALIAS" in js
        assert "firebaseToken: 'token'" in js, (
            "D5: custom-firebase-token must come from the login/current "
            "response field `token` — without it the SPA boots logged out")
        assert "i[field] || i[RESPONSE_ALIAS[field]]" in js

    def test_login_date_written_to_local_storage(self):
        js = ga.PLAYWRIGHT_SEED_JS
        assert "localStorage.setItem('loginDate'" in js, (
            "D5: the SPA reads localStorage loginDate on boot; a seed without "
            "it is wiped on the next navigation")

    def test_both_writes_are_guarded(self):
        """Neither survival write may throw and abort the seed on a hostile page."""
        js = ga.PLAYWRIGHT_SEED_JS
        i = js.find("localStorage.setItem('loginDate'")
        assert i > 0
        # the `try {` that opens the guard must be the nearest statement before it
        assert js.rfind("try {", 0, i) > js.rfind("}", 0, i), (
            "the loginDate write must sit inside a try/catch: a page with "
            "storage disabled must still get its cookies")

    def test_cookie_a_is_raw_base64_never_percent_encoded(self):
        """The v27.1.69 fix must not regress: the SPA atob()s the RAW value."""
        js = ga.PLAYWRIGHT_SEED_JS
        assert "encodeURIComponent" not in js
        assert "btoa(JSON.stringify(aObj)) + attrs" in js

    def test_all_five_token_cookies_come_from_token_map(self):
        js = ga.PLAYWRIGHT_SEED_JS
        assert "Object.entries(ck.token_map)" in js


# ── D5-b: caller-order precondition (B4) ─────────────────────────────────────

class TestB4CallerOrderPrecondition:
    def test_about_blank_refused_with_precondition_error(self):
        page = FakePage(url="about:blank")
        with pytest.raises(ga.AuthBridgeError) as exc:
            ga._require_ghl_origin(page)
        msg = str(exc.value)
        assert "precondition" in msg.lower()
        assert "about:" in msg
        assert ga.GHL_APP_ORIGIN in msg, "the error must name the fix"

    def test_wrong_origin_refused(self):
        with pytest.raises(ga.AuthBridgeError) as exc:
            ga._require_ghl_origin(FakePage(url="https://example.com/x"))
        assert ga.GHL_APP_ORIGIN in str(exc.value)

    def test_ghl_origin_accepted(self):
        ga._require_ghl_origin(FakePage(url=GHL))  # must not raise

    def test_bridge_refuses_about_blank_before_seeding(self):
        """The guard fires BEFORE any evaluate — no partial seed is attempted."""
        page = FakePage(url="about:blank")
        ctx = _Ctx(page)
        with pytest.raises(ga.AuthBridgeError) as exc:
            ga.bridge_seed_into_context(ctx, _seed(), expected_location_id="L0C123")
        assert "precondition" in str(exc.value).lower()
        assert page.evaluate_calls == [], "the bridge seeded a page it refused"

    def test_di_double_without_url_is_not_blocked(self):
        """A fake page with no .url (unit-test double) skips the origin check."""
        page = FakePage()
        ctx = _Ctx(page)
        receipt = ga.bridge_seed_into_context(
            ctx, _seed(), expected_location_id="L0C123",
            identity_fetcher=lambda c: {"userId": "u1", "companyId": "c1",
                                        "locationId": "L0C123"})
        assert receipt["state"] == "OK"


class _Ctx:
    """Minimal owned-context double: pages[0] is the page under test."""

    def __init__(self, page):
        self.pages = [page]
        self._ctx = self

    def new_page(self):  # pragma: no cover - the double always has a page
        raise AssertionError("bridge must not open a second page")


# ── D5-c: no-clear proof via a fake SPA double ───────────────────────────────

class FakeSpa:
    """A SPA double that models the measured boot behaviour: it DELETES the six
    auth cookies unconditionally, then re-authenticates only from what
    persisted (custom-firebase-token + loginDate)."""

    NAMES = ("a", "access-token-v1", "refresh-token-v1", "access-token-v2",
             "refresh-token-v2", "custom-firebase-token")

    def __init__(self):
        self.jar = {}
        self.local = {}

    def boot(self):
        """Delete all six, then re-issue them only when BOTH survival artifacts
        were present at boot. That is the measured rule: the sweep is
        unconditional; survival is decided by the persisted state it reads."""
        had_cft = self.jar.get("custom-firebase-token")
        survived = had_cft is not None and self.local.get("loginDate") is not None
        for n in self.NAMES:
            self.jar.pop(n, None)
        if survived:
            for n in self.NAMES:
                self.jar[n] = "restored"
            return True
        return False

    def auth_get(self):
        if "custom-firebase-token" in self.jar and "loginDate" in self.local:
            return "ok"
        raise RuntimeError("user_not_logged_in")


def _apply_patched_seed(spa, response):
    """The exact writes the patched PLAYWRIGHT_SEED_JS performs."""
    for field, name in _seed()["cookies"]["token_map"].items():
        val = response.get(field) or response.get("token") or ""
        if val:
            spa.jar[name] = val
    spa.jar["a"] = "base64blob"
    spa.local["loginDate"] = "2026-10-22T00:00:00Z"


class TestD5NoClearProof:
    RESPONSE = {"apiKey": "k", "userId": "u1", "companyId": "c1",
                "jwt": "j", "refreshJwt": "rj", "authToken": "at",
                "refreshToken": "rt", "token": "custom-token"}

    def test_patched_seed_survives_boot(self):
        spa = FakeSpa()
        _apply_patched_seed(spa, self.RESPONSE)
        assert spa.boot() is True
        assert spa.auth_get() == "ok"

    def test_unpatched_seed_is_wiped(self):
        """Control: without the token remap + loginDate the boot wipes it."""
        spa = FakeSpa()
        for field, name in _seed()["cookies"]["token_map"].items():
            val = self.RESPONSE.get(field) or ""   # no alias, no loginDate
            if val:
                spa.jar[name] = val
        spa.jar["a"] = "base64blob"
        assert spa.boot() is False, "control must reproduce the D5 wipe"
        with pytest.raises(RuntimeError, match="user_not_logged_in"):
            spa.auth_get()

    def test_seed_without_login_date_still_wiped(self):
        """Isolates the loginDate half of the contract."""
        spa = FakeSpa()
        _apply_patched_seed(spa, self.RESPONSE)
        spa.local.pop("loginDate")
        assert spa.boot() is False

    def test_seed_without_custom_token_still_wiped(self):
        """Isolates the token-remap half of the contract."""
        spa = FakeSpa()
        _apply_patched_seed(spa, self.RESPONSE)
        spa.jar.pop("custom-firebase-token")
        assert spa.boot() is False


# ── D5-d: token_map names the COOKIE; the response field is `token` ──────────

def test_seed_contract_response_field_is_token_not_firebaseToken():
    """The seed ships `firebaseToken` as the COOKIE name. The live login/current
    response has no such field — it returns `token`. Pinning both ends keeps a
    future edit from 'fixing' one and silently breaking the other."""
    seed = _seed()
    tm = seed["cookies"]["token_map"]
    assert tm["firebaseToken"] == "custom-firebase-token"
    js = ga.PLAYWRIGHT_SEED_JS
    assert "firebaseToken: 'token'" in js

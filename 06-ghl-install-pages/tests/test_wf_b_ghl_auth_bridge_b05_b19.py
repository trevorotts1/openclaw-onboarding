"""WF-B (Skill 06 v3.0 P4) — GHL auth bridge, tests B05 + B19.

Per plan §14.2:
  B05  token missing / expired / wrong tenant — stop or ONE permitted re-seed,
       no login popups, no leaks
  B19  auth/PII never reaches a trace, prompt, log, or git — redaction holds

Offline synthetic fixtures ONLY: the mint step is a DI ``seed_runner`` stub and
the in-page identity read is a DI ``identity_fetcher`` stub. No live GHL calls,
no live writes, no network. Secrets here are synthetic shapes, never real
credentials.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

import browser_manager as bm  # noqa: E402
import ghl_auth as ga  # noqa: E402

# Synthetic (fake) credential shapes — never real values.
FAKE_REFRESH = "AgNt" + "r3fr3sh" * 6          # >= 20 chars, not placeholder-shaped
FAKE_PIT = "AgNt" + "l0c4t10n" * 6
FAKE_ID_TOKEN = "eyJhbGciOi" + "FAKEIDTOKEN" * 5
FAKE_REFRESH_2 = "AgNt" + "r3fr3shB" * 6


def _seed_payload(id_token=FAKE_ID_TOKEN, refresh=FAKE_REFRESH_2):
    return {
        "indexeddb": {
            "database": "firebaseLocalStorageDb",
            "store": "firebaseLocalStorage",
            "keyPath": "fbase_key",
            "entry": {
                "fbase_key": "firebase:authUser:x:[DEFAULT]",
                "value": {
                    "uid": "u-fake",
                    "emailVerified": False,
                    "isAnonymous": False,
                    "providerData": [],
                    "stsTokenManager": {
                        "refreshToken": refresh,
                        "accessToken": id_token,
                        "expirationTime": 0,
                    },
                },
            },
        },
        "login_current": {"method": "GET", "url": "https://example.invalid/",
                          "headers": {"token-id": id_token},
                          "response_to_cookies": {}},
        "cookies": {"a_name": "a", "a_shape": ["apiKey", "userId", "companyId"],
                    "token_map": {}, "attrs": {"path": "/", "maxAge": 31536000}},
    }


def _seed_runner_factory(calls, exit_code=0, payload=None):
    def _runner(session, out, env):
        calls.append({"session": session, "out": out})
        if exit_code == 0:
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_text(
                json.dumps(payload or _seed_payload()), encoding="utf-8")
        return exit_code
    return _runner


class FakePage:
    def __init__(self, recorder, identity):
        self.recorder = recorder
        self.identity = identity

    def evaluate(self, js, arg=None):
        self.recorder.append({"js": js, "seed": arg})
        return self.identity


class FakeContext:
    """Owned Playwright context stand-in. Records every call — B05 asserts no
    login popup / no navigation to a login form ever happens through the
    bridge."""

    def __init__(self, identity=None):
        self.calls = []
        self._identity = identity if identity is not None else {}
        self.pages = []

    def new_page(self):
        page = FakePage(self.calls, self._identity)
        self.pages.append(page)
        return page


# ── B05 ─────────────────────────────────────────────────────────────────────

class TestB05AuthFailures:
    def test_token_missing_stops_no_login_popup(self, tmp_path):
        ctx = FakeContext()
        calls = []
        with pytest.raises(ga.AuthBridgeError, match="no usable refresh token"):
            ga.mint_and_bridge(
                ctx, "wf-b-b05", str(tmp_path / "seed.json"), env={},
                expected_location_id="L1",
                seed_runner=_seed_runner_factory(calls))
        # nothing was minted, no page was touched, no login popup/page opened
        assert calls == []
        assert ctx.calls == []

    def test_expired_auth_one_reseed_then_success(self, tmp_path):
        ctx = FakeContext()
        identities = [{}, {"userId": "u1", "companyId": "c1", "locationId": "L1"}]
        calls = []

        def fetcher(_ctx):
            return identities.pop(0) if identities else identities

        receipt = ga.mint_and_bridge(
            ctx, "wf-b-b05e", str(tmp_path / "seed.json"),
            env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
            expected_location_id="L1",
            seed_runner=_seed_runner_factory(calls),
            identity_fetcher=fetcher)
        assert receipt["ok"] is True
        assert receipt["reseed_count"] == 1          # exactly ONE re-seed
        assert len(calls) == 2                       # initial mint + one re-mint
        assert receipt["identity"]["locationId"] == "L1"

    def test_expired_auth_still_expired_stops_after_one_reseed(self, tmp_path):
        ctx = FakeContext()
        calls = []
        with pytest.raises(ga.AuthBridgeError, match="re-seed"):
            ga.mint_and_bridge(
                ctx, "wf-b-b05x", str(tmp_path / "seed.json"),
                env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
                expected_location_id="L1",
                seed_runner=_seed_runner_factory(calls),
                identity_fetcher=lambda _c: {})      # always the login bounce
        assert len(calls) == 2                       # never a third mint

    def test_wrong_tenant_terminal_no_reseed(self, tmp_path):
        ctx = FakeContext()
        calls = []
        with pytest.raises(ga.AuthBridgeError, match="wrong tenant"):
            ga.mint_and_bridge(
                ctx, "wf-b-b05w", str(tmp_path / "seed.json"),
                env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
                expected_location_id="L1",
                seed_runner=_seed_runner_factory(calls),
                identity_fetcher=lambda _c: {
                    "userId": "u1", "companyId": "c1", "locationId": "OTHER"})
        assert len(calls) == 1                       # terminal — no re-seed
        assert ctx.calls == []                       # fetcher used, no popup

    def test_revoked_token_stops_with_redacted_message(self, tmp_path):
        ctx = FakeContext()
        calls = []
        with pytest.raises(ga.AuthBridgeError) as excinfo:
            ga.mint_and_bridge(
                ctx, "wf-b-b05r", str(tmp_path / "seed.json"),
                env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
                expected_location_id="L1",
                seed_runner=_seed_runner_factory(calls, exit_code=3))
        assert len(calls) == 1
        assert FAKE_REFRESH not in str(excinfo.value)  # B19: value never leaks

    def test_night_mode_blocks_tier2_fallback(self, tmp_path):
        already = "ghl_auth_fallback" in sys.modules
        res = ga.run("wf-b-b05n", str(tmp_path / "seed.json"),
                     env={"GHL_NIGHT_MODE": "1"},
                     seed_runner=lambda s, o, e: 2)
        assert res.tier == ga.TIER3
        assert res.exit_code == 7
        assert res.fallback_entries == 0
        # the fallback is never IMPORTED by this run (it was not loaded before)
        assert ("ghl_auth_fallback" in sys.modules) is already
        assert "Night mode" in res.client_message

    def test_refresh_and_pit_never_substituted(self):
        # happy path: two DIFFERENT credentials, each from its own alias chain
        ga.assert_credentials_not_substituted(
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", "GOHIGHLEVEL_API_KEY in store",
            refresh_value=FAKE_REFRESH, pit_value=FAKE_PIT)
        # substitution by alias source
        with pytest.raises(ga.AuthBridgeError, match="substituted"):
            ga.assert_credentials_not_substituted(
                "GOHIGHLEVEL_API_KEY in store", "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
        # substitution by identical value
        with pytest.raises(ga.AuthBridgeError, match="SAME value"):
            ga.assert_credentials_not_substituted(
                "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", "GOHIGHLEVEL_API_KEY",
                refresh_value=FAKE_PIT, pit_value=FAKE_PIT)

    def test_validate_location_identity_contract(self):
        assert ga.validate_location_identity(
            {"userId": "u", "companyId": "c", "locationId": "L1"},
            expected_location_id="L1")["locationId"] == "L1"
        with pytest.raises(ga.AuthBridgeError):
            ga.validate_location_identity({}, expected_location_id="L1")
        with pytest.raises(ga.AuthBridgeError, match="could NOT be confirmed"):
            ga.validate_location_identity(
                {"userId": "u", "companyId": "c"},
                expected_location_id="L1")  # no location, no company expectation
        assert ga.validate_location_identity(
            {"userId": "u", "companyId": "c1"},
            expected_location_id="L1",
            expected_company_id="c1")["companyId"] == "c1"


# ── B19 ─────────────────────────────────────────────────────────────────────

class TestB19Redaction:
    def test_redact_secrets_masks_values_keeps_names(self):
        text = f"mint failed for GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN={FAKE_REFRESH} (retry)"
        out = ga.redact_secrets(text, [FAKE_REFRESH])
        assert FAKE_REFRESH not in out
        assert ga.TOKEN_REDACTED in out
        assert "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN" in out  # name survives

    def test_bridge_receipt_carries_no_token_or_cookie(self, tmp_path):
        ctx = FakeContext()
        receipt = ga.mint_and_bridge(
            ctx, "wf-b-b19", str(tmp_path / "seed.json"),
            env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
            expected_location_id="L1",
            seed_runner=_seed_runner_factory([]),
            identity_fetcher=lambda _c: {
                "userId": "u1", "companyId": "c1", "locationId": "L1"})
        blob = json.dumps(receipt)
        for secret in (FAKE_REFRESH, FAKE_REFRESH_2, FAKE_ID_TOKEN):
            assert secret not in blob

    def test_seed_rides_evaluate_argument_not_loggable_literal(self, tmp_path):
        ctx = FakeContext(identity={"userId": "u1", "companyId": "c1",
                                    "locationId": "L1"})
        ga.mint_and_bridge(
            ctx, "wf-b-b19b", str(tmp_path / "seed.json"),
            env={"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": FAKE_REFRESH},
            expected_location_id="L1",
            seed_runner=_seed_runner_factory([]),
            identity_fetcher=None)   # default in-page path (fake page records)
        assert len(ctx.calls) == 1
        js, seed = ctx.calls[0]["js"], ctx.calls[0]["seed"]
        assert js == ga.PLAYWRIGHT_SEED_JS
        # the token rides as the evaluate ARGUMENT (structured), never as a
        # string literal inside the script text
        assert FAKE_ID_TOKEN not in js
        assert seed["indexeddb"]["entry"]["value"]["stsTokenManager"][
            "accessToken"] == FAKE_ID_TOKEN

    def test_trace_recording_refused_on_authed_lane(self):
        with pytest.raises(bm.PWLaunchRefused):
            bm.pw_launch_options({}, {"record_har_path": "/tmp/auth.har"})
        with pytest.raises(bm.PWLaunchRefused):
            bm.pw_launch_options({}, {"record_video_dir": "/tmp/vid"})

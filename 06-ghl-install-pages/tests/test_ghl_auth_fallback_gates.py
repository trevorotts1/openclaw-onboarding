"""Tests for the Tier-2 gate gauntlet + lockout safety (ghl_auth_fallback.py).

Covers DONE checks 3 (each gate A/B/C/D failing -> Tier 3 with the correct
plain-language instruction, non-zero exit, ZERO login attempts), 4 (no-real-
account-lockout: GATE B runs before any login; bounded attempts + backoff;
lockout/captcha hard-stop), and 9 (authorization recorded).

MOCKS ONLY — no real GHL, no real Gmail, no browser, no network. Zero lockout
risk: every "login" is a scripted in-memory mock.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_auth_fallback as fb  # noqa: E402
from mocks.mock_ghl import MockBrowserEngine, build_driver  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe, ghl_code_message  # noqa: E402
from mocks.mock_secret_store import MockSecretStore, fully_provisioned_store  # noqa: E402


def _good_gmail(addr="agent@example.test"):
    # live_code: the 2FA email "arrives" fresh (post-t0) when the mailbox is read
    # during login — deterministic, no real Gmail, no timing flake.
    client = MockGmailClient(profile_address=addr, messages=[], live_code="123456")
    return build_probe(client, addr)


class TestGateGauntlet:
    def test_gate_a_authorization_missing_refuses(self):
        """DONE 9: no recorded authorization -> Tier 3, exit!=0, ZERO login."""
        store = fully_provisioned_store(**{fb.AUTHORIZED_KEY: ""})
        driver = build_driver()
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert res.exit_code != 0
        assert "AUTHORIZE" in res.client_message
        assert driver.engine.password_filled == 0, "no login attempt when gate A fails"

    def test_gate_a_authorization_present_passes(self):
        """DONE 9: with the authorization record, gate A passes."""
        store = fully_provisioned_store()
        assert fb.gate_a_authorization(store).ok is True

    def test_gate_b_gmail_not_proven_refuses(self):
        """GATE B: wrong-account Gmail -> NOT-PROVEN -> Tier 3, ZERO login."""
        store = fully_provisioned_store()
        wrong = MockGmailClient(profile_address="someone-else@example.test",
                                messages=[ghl_code_message(msg_id="m1", code="999999")])
        probe = build_probe(wrong, "agent@example.test")
        driver = build_driver()
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert res.tier == fb.TIER3
        assert res.exit_code != 0
        assert "Gmail" in res.client_message
        assert driver.engine.password_filled == 0

    def test_gate_c_totp_hint_refuses(self):
        """GATE C: GHL_2FA_METHOD hint = totp -> Tier 3, ZERO login."""
        store = fully_provisioned_store(**{fb.TWOFA_METHOD_KEY: "totp"})
        driver = build_driver()
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert res.exit_code != 0
        assert "email" in res.client_message.lower()
        assert driver.engine.password_filled == 0

    def test_gate_d_creds_missing_refuses(self):
        """GATE D: no agency password -> Tier 3, ZERO login."""
        store = fully_provisioned_store(**{fb.AGENCY_PASSWORD_KEYS[0]: ""})
        driver = build_driver()
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert res.exit_code != 0
        assert "GHL_AGENCY_EMAIL" in res.client_message or "GHL_AGENCY_PASSWORD" in res.client_message
        assert driver.engine.password_filled == 0

    def test_gates_short_circuit_in_order(self):
        """check_all_gates returns the FIRST failing gate (A before B before C/D)."""
        store = fully_provisioned_store(**{fb.AUTHORIZED_KEY: "", fb.AGENCY_PASSWORD_KEYS[0]: ""})
        gate = fb.check_all_gates(store, _good_gmail())
        assert gate.ok is False
        assert gate.gate == "A", "gate A must short-circuit before gate D"


class TestLockoutSafety:
    def test_gate_b_runs_before_any_login(self):
        """DONE 4: GATE B (Gmail proof) runs BEFORE any login — if Gmail is not
        proven, the driver is never asked to fill a password."""
        store = fully_provisioned_store()
        wrong = MockGmailClient(profile_address="nope@example.test", messages=[])
        probe = build_probe(wrong, "agent@example.test")
        driver = build_driver()
        fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert driver.engine.email_filled == 0
        assert driver.engine.password_filled == 0
        assert "navigate" not in driver.engine.call_log

    def test_wrong_password_bounded_to_max_attempts(self, monkeypatch):
        """DONE 4: a failed login (no positive liveness) stops at
        MAX_LOGIN_ATTEMPTS with backoff — never unbounded."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)  # no real sleep
        store = fully_provisioned_store()
        # liveness=False simulates a wrong password / failed login each attempt.
        driver = build_driver(liveness=False)
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert res.exit_code != 0
        # Exactly MAX_LOGIN_ATTEMPTS navigations (one per attempt), no more.
        assert driver.engine.attempt_count == fb.MAX_LOGIN_ATTEMPTS
        assert fb.MAX_LOGIN_ATTEMPTS <= 3

    def test_lockout_signal_hard_stops(self, monkeypatch):
        """DONE 4: a lockout signal hard-stops to Tier 3 (no further attempts)."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        driver = build_driver(lockout_on_attempt=1)
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert "blocked" in res.client_message.lower() or "wait" in res.client_message.lower()
        # Hard stop on the FIRST attempt — never burns all attempts.
        assert driver.engine.attempt_count == 1

    def test_captcha_signal_hard_stops(self, monkeypatch):
        """DONE 4: a captcha signal hard-stops to Tier 3."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        driver = build_driver(captcha=True)
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert driver.engine.attempt_count == 1

    def test_totp_only_dom_aborts_to_tier3(self, monkeypatch):
        """GATE C DOM-authoritative: only TOTP offered -> Tier 3, single attempt."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()  # hint says email, but DOM offers only TOTP
        driver = build_driver(only_totp=True, offers_email_2fa=False)
        res = fb.run_tier2("s", "/tmp/x", store, _good_gmail(), driver)
        assert res.tier == fb.TIER3
        assert "email" in res.client_message.lower()


class TestStaleCodeRefused:
    def test_stale_code_not_submitted(self, monkeypatch):
        """No fresh post-t0 code -> NoFreshCodeError per attempt -> Tier 3; the
        driver never submits a stale code."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        # Only a STALE code (15 minutes old, before t0 + past expiry).
        stale = MockGmailClient(
            profile_address="agent@example.test",
            messages=[ghl_code_message(msg_id="old", code="111111", age_ms=15 * 60 * 1000)],
        )
        probe = build_probe(stale, "agent@example.test")
        # Keep await_code fast.
        probe.await_code.__func__.__defaults__  # touch to ensure attr exists
        driver = build_driver()

        # Shrink the await window so the test is fast.
        orig = probe.await_code

        def _fast(**kw):
            kw.setdefault("max_wait", 0.0)
            kw.setdefault("poll", 0.0)
            return orig(since_ns=kw["since_ns"], patterns=kw["patterns"],
                        max_wait=0.0, poll=0.0)

        probe.await_code = _fast  # type: ignore[assignment]
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert res.tier == fb.TIER3
        assert "submit" not in driver.engine.call_log

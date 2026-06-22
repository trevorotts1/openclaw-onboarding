"""Tests for the Tier-2 happy path + self-heal-to-Tier-1 (ghl_auth_fallback.py +
ghl_auth.py orchestrator).

Covers DONE checks 5 (email-2FA happy path: log in, select email 2FA, read the
freshest post-t0 code, submit, positive liveness) and 6 (self-heal: a fresh
GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN is written to the mock client store, and an
immediate second orchestrator run uses Tier 1 with zero fallback entries).

MOCKS ONLY — no real GHL, no real Gmail, no browser, no network.
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

import ghl_auth  # noqa: E402
import ghl_auth_fallback as fb  # noqa: E402
from mocks.mock_ghl import build_driver, MockBrowserEngine  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe, ghl_code_message, now_ms  # noqa: E402
from mocks.mock_secret_store import fully_provisioned_store  # noqa: E402


class TestHappyPath:
    def test_email_2fa_happy_path(self, monkeypatch):
        """DONE 5: email-2FA happy path reaches Tier-2 success."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        gmail = MockGmailClient(
            profile_address="agent@example.test",
            messages=[], live_code="246802",
        )
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(offers_email_2fa=True, liveness=True, locations=[])

        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)

        assert res.ok is True
        assert res.tier == fb.TIER2, res.reason
        assert res.exit_code == 0
        # The flow drove the form: email + password + send-code + submit + liveness.
        log = driver.engine.call_log
        assert "fill_email" in log and "fill_password" in log
        assert "send_code" in log and "submit" in log
        assert driver.engine.fired_send_code_at_ns, "send-code must have fired (t0)"

    def test_freshest_post_t0_code_chosen(self):
        """DONE 5: await_code picks the NEWEST post-t0 code, not a stale one."""
        import time
        t0 = time.time_ns()
        # An older (pre-t0) code and a newer (post-t0) code both present.
        gmail = MockGmailClient(
            profile_address="agent@example.test",
            messages=[
                {"id": "old", "internalDate": now_ms() - 5000, "from": "no-reply@leadconnectorhq.com",
                 "subject": "Your login security code", "body": "Your verification code is 111111"},
                {"id": "new", "internalDate": now_ms() + 10, "from": "no-reply@leadconnectorhq.com",
                 "subject": "Your login security code", "body": "Your verification code is 222222"},
            ],
        )
        probe = build_probe(gmail, "agent@example.test")
        code = probe.await_code(since_ns=t0, patterns=fb.CODE_PATTERNS, max_wait=2.0, poll=0.1)
        assert code == "222222", "must pick the freshest post-t0 code"

    def test_multi_location_selects_configured(self, monkeypatch):
        """Multi-location: the configured GHL_LOCATION_ID is selected; success."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        loc = "abcd1234EFGH5678ijkl"  # fabricated 20-char location id
        store = fully_provisioned_store(**{fb.LOCATION_ID_KEY: loc})
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code="123123")
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(locations=[loc, "zzzz9999WXYZ0000abcd"])
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert res.ok is True and res.tier == fb.TIER2

    def test_multi_location_ambiguous_unconfigured_fails(self, monkeypatch):
        """Ambiguous + unconfigured location -> Tier 3."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()  # no GHL_LOCATION_ID
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code="123123")
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(locations=["abcd1234EFGH5678ijkl", "zzzz9999WXYZ0000abcd"])
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert res.tier == fb.TIER3
        assert "location" in res.client_message.lower()


class TestSelfHeal:
    def test_self_heal_writes_canonical_token(self, monkeypatch):
        """DONE 6: after Tier-2 success the canonical refresh-token key is written
        to the (mock) client store."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code="135790")
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[])

        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        assert res.ok is True and res.healed_token_written is True
        assert fb.REFRESH_TOKEN_KEY in store.written, "self-heal must write the canonical key"
        assert store.written[fb.REFRESH_TOKEN_KEY], "written token must be non-empty"

    def test_second_run_uses_tier1_after_heal(self, monkeypatch, tmp_path):
        """DONE 6: an immediate SECOND orchestrator run reads the healed token and
        uses Tier 1 with ZERO fallback entries."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        out = str(tmp_path / "seed.json")

        # First run: no token in env -> Tier 2 -> self-heal into the store.
        store = fully_provisioned_store()
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code="864209")
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[])

        first = ghl_auth.run(
            "sess", out, env={},  # no token -> straight to Tier 2 eval
            seed_runner=lambda s, o, e: 2,  # belt: even if checked, "no token"
            store=store, probe=probe, driver=driver,
        )
        assert first.tier == ghl_auth.TIER2, first.reason
        assert first.fallback_entries == 1
        healed = store.written[fb.REFRESH_TOKEN_KEY]
        assert healed

        # Second run: the healed token is now in the env (the client store).
        sys.modules.pop("ghl_auth_fallback", None)
        env2 = {ghl_auth.REFRESH_ENV_VARS[0]: healed}
        counter2 = ghl_auth.Counter()
        second = ghl_auth.run(
            "sess", out, env2,
            fallback_entry_counter=counter2,
            seed_runner=lambda s, o, e: 0,  # token present -> mint ok
        )
        assert second.tier == ghl_auth.TIER1
        assert second.fallback_entries == 0
        assert "ghl_auth_fallback" not in sys.modules, (
            "second run must NOT import the fallback (Tier 1 served it)"
        )

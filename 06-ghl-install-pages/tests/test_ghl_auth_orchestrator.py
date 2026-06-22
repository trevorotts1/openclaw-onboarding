"""Tests for the GHL auth ORCHESTRATOR (ghl_auth.py) — the 3-tier ladder.

Covers DONE checks 1 (Tier-1 routing), 2 (valid token uses Tier 1 with ZERO
fallback entries; fallback module never imported), and 7 (orchestrator secret
hygiene of its routing output).

MOCKS ONLY — no real GHL, no real Gmail, no browser, no network. Routing is
verified deterministically; the fallback module is detected via sys.modules and
the fallback-entry counter (which the orchestrator persists for a separate
verifier).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_auth  # noqa: E402
from mocks.mock_ghl import build_driver  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe  # noqa: E402
from mocks.mock_secret_store import fully_provisioned_store  # noqa: E402

_FAKE_TOKEN = "FAKEtokenFAKEtokenFAKEtoken0123456789abcd"


def _seed_runner_ok(session, out, env):
    """Stub seed runner: token present -> mint exits 0 (Tier 1 served)."""
    return 0


def _seed_runner_revoked(session, out, env):
    """Stub seed runner: token present but revoked -> exit 3 (fall to Tier 2)."""
    return 3


class TestTier1Primary:
    def test_valid_token_uses_tier1_no_fallback(self, tmp_path):
        """DONE 2: a valid token routes Tier 1, fallback_entries == 0, and the
        fallback module is NEVER imported."""
        sys.modules.pop("ghl_auth_fallback", None)
        out = str(tmp_path / "seed.json")
        env = {ghl_auth.REFRESH_ENV_VARS[0]: _FAKE_TOKEN}
        counter = ghl_auth.Counter()

        res = ghl_auth.run(
            "sess1", out, env,
            fallback_entry_counter=counter,
            seed_runner=_seed_runner_ok,
        )

        assert res.tier == ghl_auth.TIER1
        assert res.ok is True
        assert res.exit_code == 0
        assert res.fallback_entries == 0, "Tier 1 must record ZERO fallback entries"
        assert counter.value == 0
        # The fallback module must NOT have been imported on the Tier-1 path.
        assert "ghl_auth_fallback" not in sys.modules, (
            "fallback module was imported on a valid-token Tier-1 run"
        )

    def test_tier_side_file_records_raw_routing(self, tmp_path):
        """DONE 2/6 evidence: a separate verifier can read raw {tier,
        fallback_entries} from the side file the orchestrator writes."""
        out = str(tmp_path / "seed.json")
        env = {ghl_auth.REFRESH_ENV_VARS[0]: _FAKE_TOKEN}
        ghl_auth.run("sess1", out, env, seed_runner=_seed_runner_ok)

        side = tmp_path / "ghl-auth-tier.json"
        assert side.exists(), "orchestrator must persist the tier side file"
        data = json.loads(side.read_text())
        assert data["tier"] == ghl_auth.TIER1
        assert data["fallback_entries"] == 0
        # Side file is a routing record only — no secret.
        assert _FAKE_TOKEN not in side.read_text()

    def test_resolve_refresh_token_precedence(self):
        """Tier-1 token precedence matches seed-ghl-auth.py order."""
        env = {
            "CAF_FIREBASE_REFRESH_TOKEN": "alias-token",
            ghl_auth.REFRESH_ENV_VARS[0]: "canonical-token",
        }
        tok, name = ghl_auth.resolve_refresh_token(env)
        assert tok == "canonical-token"
        assert name == ghl_auth.REFRESH_ENV_VARS[0]
        # No token anywhere -> empty.
        assert ghl_auth.resolve_refresh_token({}) == ("", "")


class TestTier1FallThrough:
    def test_revoked_token_falls_to_tier2_and_self_heals(self, tmp_path):
        """DONE 2: a revoked token (mint exit 3) falls through to Tier 2; with a
        fully-provisioned mock store/probe/driver it self-heals to Tier 2."""
        sys.modules.pop("ghl_auth_fallback", None)
        out = str(tmp_path / "seed.json")
        env = {ghl_auth.REFRESH_ENV_VARS[0]: _FAKE_TOKEN}

        store = fully_provisioned_store()
        gmail = MockGmailClient(
            profile_address="agent@example.test",
            messages=[], live_code="123456",
        )
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(locations=[])  # single location

        counter = ghl_auth.Counter()
        res = ghl_auth.run(
            "sess1", out, env,
            fallback_entry_counter=counter,
            seed_runner=_seed_runner_revoked,
            store=store, probe=probe, driver=driver,
        )

        assert res.tier == ghl_auth.TIER2, res.reason
        assert res.ok is True
        assert res.fallback_entries == 1, "exactly one fallback entry on a fall-through"
        assert res.healed_token_written is True


class TestOrchestratorHasNoLoginCode:
    def test_orchestrator_source_has_no_password_read(self):
        """DONE 7: the orchestrator must contain NO login/password/2FA code (that
        lives only in the fallback + browser helper)."""
        src = (_TOOLS_DIR / "ghl_auth.py").read_text(encoding="utf-8")
        for banned in ("fill_password", "os.environ[\"GHL_AGENCY_PASSWORD\"",
                       "signInWith", "enter_otp", "handle_2fa"):
            assert banned not in src, f"orchestrator must not contain '{banned}'"

    def test_orchestrator_check_does_not_import_fallback(self, tmp_path):
        """--check reports a tier WITHOUT importing the fallback (no login touched)."""
        sys.modules.pop("ghl_auth_fallback", None)
        res = ghl_auth._check("s", str(tmp_path / "seed.json"),
                              {ghl_auth.REFRESH_ENV_VARS[0]: _FAKE_TOKEN})
        assert res.tier == ghl_auth.TIER1
        assert "ghl_auth_fallback" not in sys.modules

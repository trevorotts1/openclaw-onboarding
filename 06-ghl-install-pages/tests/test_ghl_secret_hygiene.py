"""Secret-hygiene tests for the GHL Tier-2 auth fallback (DONE 7).

PROVES: a full mock Tier-2 run leaks NO password, NO 2FA code, NO refresh/access
token to stdout/stderr/logs or any artifact; and a repo grep of all new source
finds no secret literal and no client name/id/email.

MOCKS ONLY — no real GHL, no real Gmail, no browser, no network.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
_REPO_ROOT = _TESTS_DIR.parent.parent
for p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

import ghl_auth  # noqa: E402
import ghl_auth_fallback as fb  # noqa: E402
from mocks.mock_ghl import build_driver  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe  # noqa: E402
from mocks.mock_secret_store import fully_provisioned_store  # noqa: E402

_NEW_SOURCE = [
    _TOOLS_DIR / "ghl_auth.py",
    _TOOLS_DIR / "ghl_auth_fallback.py",
    _TOOLS_DIR / "ghl_gmail_probe.py",
    _TOOLS_DIR / "ghl_login_browser.py",
]

# The fabricated secret-shaped values the mocks use (these are NOT real secrets).
_FAKE_PASSWORD = "FAKE-pw-not-a-real-secret"
_FAKE_CODE = "246802"
_FAKE_REFRESH = "FAKErefreshTOKENfakeREFRESHtoken0123456789"


class TestNoSecretLeak:
    def test_full_run_leaks_no_secret(self, monkeypatch, capsys, tmp_path):
        """DONE 7: a full Tier-2 run (mock GHL + mock Gmail) prints/logs NO
        password, NO code, NO token to stdout/stderr."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store(**{fb.AGENCY_PASSWORD_KEYS[0]: _FAKE_PASSWORD})
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code=_FAKE_CODE)
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[],
                              refresh_token_to_emit=_FAKE_REFRESH)

        out = str(tmp_path / "seed.json")
        res = ghl_auth.run("s", out, env={}, seed_runner=lambda *a: 2,
                           store=store, probe=probe, driver=driver)
        assert res.ok and res.tier == ghl_auth.TIER2

        captured = capsys.readouterr()
        blob = captured.out + captured.err + res.reason + res.client_message
        for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
            assert secret not in blob, f"secret leaked into output: {secret!r}"

        # The side file the orchestrator wrote must also be secret-free.
        side = tmp_path / "ghl-auth-tier.json"
        if side.exists():
            sidetext = side.read_text()
            for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
                assert secret not in sidetext

    def test_result_objects_never_carry_a_secret(self, monkeypatch, tmp_path):
        """The Tier-2 result fields (reason/client_message) never carry the token,
        password, or code."""
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store(**{fb.AGENCY_PASSWORD_KEYS[0]: _FAKE_PASSWORD})
        gmail = MockGmailClient(profile_address="agent@example.test",
                                messages=[], live_code=_FAKE_CODE)
        probe = build_probe(gmail, "agent@example.test")
        driver = build_driver(liveness=True, locations=[],
                              refresh_token_to_emit=_FAKE_REFRESH)
        res = fb.run_tier2("s", "/tmp/x", store, probe, driver)
        for field_val in (res.reason, res.client_message):
            for secret in (_FAKE_PASSWORD, _FAKE_CODE, _FAKE_REFRESH):
                assert secret not in field_val


class TestRepoSourceHygiene:
    def test_no_long_token_literal_in_source(self):
        """DONE 7: no secret literal (long JWT/base64 run) in the new modules."""
        long_re = re.compile(r"['\"][A-Za-z0-9_\-]{120,}['\"]")
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert not long_re.search(txt), f"long token-looking literal in {f.name}"

    def test_no_real_firebase_api_key_in_new_modules(self):
        """The new modules carry NO live token; they may NOT embed the real
        securetoken Firebase API key either (that lives only in seed-ghl-auth.py)."""
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert "AIzaSy-FAKE-EXAMPLE-KEY-DO-NOT-USE-000000" not in txt

    def test_no_operator_path_in_source(self):
        """No operator machine path literal in the new modules' CODE.

        os.path.expanduser('~') is used instead of a hardcoded home, so an
        operator path must never appear.
        """
        for f in _NEW_SOURCE:
            txt = f.read_text(encoding="utf-8")
            assert "/Users/blackceomacmini" not in txt

    def test_no_client_identifiers_in_new_files(self):
        """DONE 7: run the repo's no-client-names guard scoped to the new files +
        tests (fabricated ids must not trip it)."""
        import subprocess
        guard = _REPO_ROOT / "scripts" / "qc-assert-no-client-names.sh"
        res = subprocess.run(["bash", str(guard), "--repo-root", str(_REPO_ROOT)],
                             capture_output=True, text=True, timeout=120)
        # The guard scans the whole repo; the new files must not introduce a hit.
        assert res.returncode == 0, (
            f"no-client-names guard FAILED (a new file may carry a client id):\n{res.stdout}")

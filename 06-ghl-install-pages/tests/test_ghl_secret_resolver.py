"""S06-04 — the shared secret resolver (tools/ghl_secret_resolver.py) and its
wiring into ghl_auth.py, seed-ghl-auth.py, ghl_media.py, and
ghl_auth_fallback.SecretStore.

Hermetic: every store, secret file, and HOME lives under tmp_path; the
process env is scrubbed via monkeypatch where a test resolves the process
environment. NO real credential, NO network, NO live GHL/Gmail.
Fabricated values only.
"""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import capability_probe  # noqa: E402
import ghl_auth  # noqa: E402
import ghl_auth_fallback as fb  # noqa: E402
import ghl_media  # noqa: E402
import ghl_secret_resolver as resolver  # noqa: E402
from mocks.mock_ghl import build_driver  # noqa: E402
from mocks.mock_gmail import MockGmailClient, build_probe  # noqa: E402
from mocks.mock_secret_store import MockSecretStore, fully_provisioned_store  # noqa: E402

_TOKEN = "FAKEtokenFAKEtokenFAKEtoken0123456789abcd"     # 41 chars, real-shaped
_TOKEN2 = "OTHERtokenOTHERtokenOTHERtoken0123456789ab"  # second real-shaped value
_PIT = "pit-FAKEFAKEFAKEFAKEFAKEFAKEFAKEFAKE0123456789"
_LOC = "FIXTURE0LOCATION0000"
_PLACEHOLDER = "pit-abc123"  # the doc placeholder from the 2026-08-03 incident

_REFRESH_NAMES = (
    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN",
    "CAF_FIREBASE_REFRESH_TOKEN",
    "GHL_FIREBASE_REFRESH_TOKEN",
    "GHL_REFRESH_TOKEN_FILE",
)


def _write_file(path: Path, text: str, mode: int = 0o600) -> str:
    path.write_text(text, encoding="utf-8")
    os.chmod(path, mode)
    return str(path)


def _tmp_stores(tmp_path: Path, monkeypatch, *contents: str) -> list:
    """Point the resolver + ghl_media store lists at tmp files (call-time seam)."""
    paths = []
    for i, content in enumerate(contents):
        p = tmp_path / ("store" + str(i) + ".env")
        p.write_text(content, encoding="utf-8")
        paths.append(str(p))
    monkeypatch.setattr(resolver, "ENV_STORES", tuple(paths))
    monkeypatch.setattr(ghl_media, "_GHL_ENV_STORES", tuple(paths))
    return paths


def _scrub_refresh_env(monkeypatch) -> None:
    for name in _REFRESH_NAMES:
        monkeypatch.delenv(name, raising=False)


class TestFileIndirection:
    def test_file_happy_path_refresh(self, tmp_path):
        f = _write_file(tmp_path / "tok.txt", _TOKEN + "\n")
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: f}
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "GHL_REFRESH_TOKEN_FILE")

    def test_file_beats_env_and_stores(self, tmp_path, monkeypatch):
        f = _write_file(tmp_path / "tok.txt", _TOKEN)
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN2 + "\n")
        env = {
            ghl_auth.REFRESH_TOKEN_FILE_VAR: f,
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": _TOKEN2,
        }
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "GHL_REFRESH_TOKEN_FILE")

    def test_env_beats_stores(self, tmp_path, monkeypatch):
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN2 + "\n")
        env = {"CAF_FIREBASE_REFRESH_TOKEN": _TOKEN}
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "CAF_FIREBASE_REFRESH_TOKEN")

    def test_preferred_alias_in_later_store_beats_legacy_in_earlier(self, tmp_path, monkeypatch):
        _scrub_refresh_env(monkeypatch)
        _tmp_stores(
            tmp_path, monkeypatch,
            "GHL_FIREBASE_REFRESH_TOKEN=" + _TOKEN2 + "\n",
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n",
        )
        value, source = ghl_auth.resolve_refresh_token(None)
        assert value == _TOKEN
        assert source.startswith("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")

    def test_missing_file_is_precise(self, tmp_path):
        missing = str(tmp_path / "absent.txt")
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: missing}
        with pytest.raises(resolver.SecretFileError) as ei:
            ghl_auth.resolve_refresh_token(env)
        msg = str(ei.value)
        assert "GHL_REFRESH_TOKEN_FILE" in msg and missing in msg
        assert _TOKEN not in msg

    def test_empty_file_is_precise(self, tmp_path):
        f = _write_file(tmp_path / "empty.txt", "   \n")
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: f}
        with pytest.raises(resolver.SecretFileError) as ei:
            ghl_auth.resolve_refresh_token(env)
        assert "empty" in str(ei.value)

    def test_loose_permissions_refused(self, tmp_path):
        f = _write_file(tmp_path / "loose.txt", _TOKEN, mode=0o644)
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: f}
        with pytest.raises(resolver.SecretFileError) as ei:
            ghl_auth.resolve_refresh_token(env)
        msg = str(ei.value)
        assert "0o644" in msg and "GHL_REFRESH_TOKEN_FILE" in msg
        assert _TOKEN not in msg

    def test_placeholder_file_value_falls_through(self, tmp_path):
        f = _write_file(tmp_path / "ph.txt", _PLACEHOLDER + "\n")
        env = {
            ghl_auth.REFRESH_TOKEN_FILE_VAR: f,
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": _TOKEN,
        }
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
        env_only = {ghl_auth.REFRESH_TOKEN_FILE_VAR: f}
        assert ghl_auth.resolve_refresh_token(env_only) == ("", "")


class TestRefreshProcessResolution:
    def test_store_only_token_resolves_for_orchestrator(self, tmp_path, monkeypatch):
        _scrub_refresh_env(monkeypatch)
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n")
        value, source = ghl_auth.resolve_refresh_token(None)
        assert value == _TOKEN
        assert source.startswith("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")

    def test_explicit_mapping_is_hermetic(self, tmp_path, monkeypatch):
        # The unmodified-suite contract: an explicit mapping must NOT consult
        # the box's real stores (the Mini's real store holds a real token).
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n")
        assert ghl_auth.resolve_refresh_token({}) == ("", "")

    def test_env_placeholder_falls_through_to_store(self, tmp_path, monkeypatch):
        _scrub_refresh_env(monkeypatch)
        monkeypatch.setenv("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", _PLACEHOLDER)
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n")
        value, _source = ghl_auth.resolve_refresh_token(None)
        assert value == _TOKEN
        assert ghl_auth._resolve_refresh(None).placeholder_seen is True

    def test_all_placeholders_fail_loud_with_note(self, tmp_path, monkeypatch):
        _scrub_refresh_env(monkeypatch)
        monkeypatch.setenv("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN", _PLACEHOLDER)
        _tmp_stores(tmp_path, monkeypatch,
                    "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=your-token-here-xxxxxx\n")
        res = ghl_auth._check("s", str(tmp_path / "seed.json"), None)
        assert res.tier == ghl_auth.TIER2
        assert "PLACEHOLDER" in res.reason

    def test_broken_file_is_tier3_never_tier2(self, tmp_path):
        missing = str(tmp_path / "absent.txt")
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: missing}
        calls = []

        def stub_seed(session, out, env_arg):
            calls.append(1)
            return 0

        res = ghl_auth.run(
            "s", str(tmp_path / "seed.json"), env,
            seed_runner=stub_seed,
            store=fully_provisioned_store(),
            probe=build_probe(MockGmailClient(
                profile_address="agent@example.test", messages=[], live_code="246802"),
                "agent@example.test"),
            driver=build_driver(offers_email_2fa=True, liveness=True, locations=[]),
        )
        assert res.tier == ghl_auth.TIER3
        assert res.exit_code == 2
        assert res.fallback_entries == 0
        assert "GHL_REFRESH_TOKEN_FILE" in res.reason
        assert calls == [], "Tier 1 must not run with a broken _FILE indirection"


_SEED = str(_TOOLS_DIR / "seed-ghl-auth.py")


def _seed_check(tmp_path: Path, extra_env: dict, store_text: str = ""):
    home = tmp_path / "home"
    secrets_dir = home / ".openclaw" / "secrets"
    secrets_dir.mkdir(parents=True, exist_ok=True)
    if store_text:
        (secrets_dir / ".env").write_text(store_text, encoding="utf-8")
    env = {"PATH": os.environ.get("PATH", ""), "HOME": str(home)}
    env.update(extra_env)
    proc = subprocess.run(
        [sys.executable, _SEED, "--check"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    return proc


class TestSeedCheckSubprocess:
    def test_store_only_token_resolves(self, tmp_path):
        proc = _seed_check(tmp_path, {},
                           "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n")
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert doc["auth_path"] == "refresh-token"
        assert doc["env_var"].startswith("GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN")
        assert doc["len"] == len(_TOKEN)
        assert _TOKEN not in proc.stdout and _TOKEN not in proc.stderr

    def test_file_token_resolves(self, tmp_path):
        f = _write_file(tmp_path / "tok.txt", _TOKEN + "\n")
        proc = _seed_check(tmp_path, {"GHL_REFRESH_TOKEN_FILE": f})
        assert proc.returncode == 0, proc.stderr
        doc = json.loads(proc.stdout)
        assert doc["env_var"] == "GHL_REFRESH_TOKEN_FILE"
        assert _TOKEN not in proc.stdout and _TOKEN not in proc.stderr

    def test_all_placeholders_exit2_with_note(self, tmp_path):
        proc = _seed_check(
            tmp_path,
            {"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": _PLACEHOLDER},
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=your-token-here-xxxxxx\n",
        )
        assert proc.returncode == 2
        assert "PLACEHOLDER" in proc.stderr
        assert _PLACEHOLDER not in proc.stderr

    def test_broken_file_exit2_precise(self, tmp_path):
        missing = str(tmp_path / "absent.txt")
        proc = _seed_check(tmp_path, {"GHL_REFRESH_TOKEN_FILE": missing})
        assert proc.returncode == 2
        assert "GHL_REFRESH_TOKEN_FILE" in proc.stderr and missing in proc.stderr

    def test_loose_file_exit2_refused(self, tmp_path):
        f = _write_file(tmp_path / "loose.txt", _TOKEN, mode=0o644)
        proc = _seed_check(tmp_path, {"GHL_REFRESH_TOKEN_FILE": f})
        assert proc.returncode == 2
        assert "0o644" in proc.stderr
        assert _TOKEN not in proc.stderr and _TOKEN not in proc.stdout


class TestSecretStoreFileRead:
    def _store_path(self, tmp_path: Path, text: str) -> str:
        p = tmp_path / "secrets.env"
        p.write_text(text, encoding="utf-8")
        return str(p)

    def test_reads_store_file_when_env_empty(self, tmp_path):
        path = self._store_path(
            tmp_path,
            "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN + "\n"
            "GHL_AGENCY_EMAIL=agent@example.test\n",
        )
        store = fb.SecretStore({}, secrets_path=path)
        assert store.read_secret(fb.REFRESH_TOKEN_KEY) == _TOKEN
        assert store.email == "agent@example.test"

    def test_env_wins_over_file(self, tmp_path):
        path = self._store_path(
            tmp_path, "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=" + _TOKEN2 + "\n")
        store = fb.SecretStore({fb.REFRESH_TOKEN_KEY: _TOKEN}, secrets_path=path)
        assert store.read_secret(fb.REFRESH_TOKEN_KEY) == _TOKEN

    def test_write_then_fresh_store_reads_back(self, tmp_path):
        # The read/write asymmetry regression: self-heal writes the store;
        # a FRESH process (new SecretStore, empty env) must read it back.
        path = str(tmp_path / "secrets.env")
        writer = fb.SecretStore({}, secrets_path=path)
        assert writer.write_secret(fb.REFRESH_TOKEN_KEY, _TOKEN) is True
        assert stat.S_IMODE(os.stat(path).st_mode) == 0o600
        fresh = fb.SecretStore({}, secrets_path=path)
        assert fresh.read_secret(fb.REFRESH_TOKEN_KEY) == _TOKEN

    def test_mock_location_id_canonical_first(self):
        both = MockSecretStore(**{
            fb.LOCATION_ID_KEY_CANONICAL: "canonical-location-id",
            fb.LOCATION_ID_KEY: "legacy-location-id",
        })
        assert both.location_id == "canonical-location-id"
        legacy_only = MockSecretStore(**{fb.LOCATION_ID_KEY: "legacy-location-id"})
        assert legacy_only.location_id == "legacy-location-id"


class TestMediaFileIndirection:
    def test_pit_file_resolves(self, tmp_path, monkeypatch):
        _tmp_stores(tmp_path, monkeypatch)
        f = _write_file(tmp_path / "pit.txt", _PIT + "\n")
        env = {"GHL_LOCATION_PIT_FILE": f}
        assert ghl_media.resolve_location_pit(env) == _PIT

    def test_location_id_file_resolves(self, tmp_path, monkeypatch):
        _tmp_stores(tmp_path, monkeypatch)
        f = _write_file(tmp_path / "loc.txt", _LOC + "\n")
        env = {"GHL_LOCATION_ID_FILE": f}
        assert ghl_media.resolve_location_id(env) == _LOC

    def test_pit_broken_file_raises_precise(self, tmp_path, monkeypatch):
        _tmp_stores(tmp_path, monkeypatch)
        missing = str(tmp_path / "absent.txt")
        env = {"GHL_LOCATION_PIT_FILE": missing}
        with pytest.raises(RuntimeError) as ei:
            ghl_media.resolve_location_pit(env)
        assert "GHL_LOCATION_PIT_FILE" in str(ei.value)
        assert _PIT not in str(ei.value)


class TestProbeParity:
    """Q6 pinned semantics: the probe reports ENV-PRESENCE against its
    SKILL.md-declared chains only. These tests pin the labeled disagreement
    so it can never become silent drift: the orchestrator resolves sources
    the probe does not claim to see (CAF alias, stores, *_FILE), and the
    probe sees one name the orchestrator does not use (bare
    FIREBASE_REFRESH_TOKEN)."""

    def test_canonical_env_both_see_it(self):
        env = {"GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": _TOKEN}
        assert capability_probe._secret_bool(env, capability_probe.FIREBASE_TOKEN_ALIASES) is True
        assert ghl_auth.resolve_refresh_token(env)[0] == _TOKEN

    def test_caf_only_probe_blind_orchestrator_resolves(self):
        env = {"CAF_FIREBASE_REFRESH_TOKEN": _TOKEN}
        assert capability_probe._secret_bool(env, capability_probe.FIREBASE_TOKEN_ALIASES) is False
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "CAF_FIREBASE_REFRESH_TOKEN")

    def test_bare_firebase_name_probe_sees_orchestrator_does_not(self):
        env = {"FIREBASE_REFRESH_TOKEN": _TOKEN}
        assert capability_probe._secret_bool(env, capability_probe.FIREBASE_TOKEN_ALIASES) is True
        assert ghl_auth.resolve_refresh_token(env) == ("", "")

    def test_file_only_probe_blind_orchestrator_resolves(self, tmp_path):
        f = _write_file(tmp_path / "tok.txt", _TOKEN)
        env = {"GHL_REFRESH_TOKEN_FILE": f}
        assert capability_probe._secret_bool(env, capability_probe.FIREBASE_TOKEN_ALIASES) is False
        assert ghl_auth.resolve_refresh_token(env) == (_TOKEN, "GHL_REFRESH_TOKEN_FILE")


class TestD1StarImport:
    def test_every_export_resolves(self):
        ns: dict = {}
        exec("from ghl_media import *", ns)
        for name in ghl_media.__all__:
            assert hasattr(ghl_media, name), name
        assert "PROMPT_CHAR_FLOOR" not in ghl_media.__all__


class TestNoSecretLeak:
    def test_file_token_appears_in_no_artifact(self, tmp_path):
        f = _write_file(tmp_path / "tok.txt", _TOKEN)
        env = {ghl_auth.REFRESH_TOKEN_FILE_VAR: f}
        out = tmp_path / "seed.json"

        def stub_seed(session, out_path, env_arg):
            return 0

        res = ghl_auth.run("s", str(out), env, seed_runner=stub_seed)
        assert res.tier == ghl_auth.TIER1 and res.ok is True
        side = (tmp_path / "ghl-auth-tier.json").read_text(encoding="utf-8")
        assert _TOKEN not in side
        assert _TOKEN not in res.reason and _TOKEN not in res.client_message
        check = ghl_auth._check("s", str(out), env)
        assert "GHL_REFRESH_TOKEN_FILE" in check.reason
        assert _TOKEN not in check.reason

    def test_tier2_healed_token_only_in_store_written(self, tmp_path, monkeypatch):
        monkeypatch.setattr(fb, "backoff", lambda attempt: None)
        store = fully_provisioned_store()
        probe = build_probe(MockGmailClient(
            profile_address="agent@example.test", messages=[], live_code="246802"),
            "agent@example.test")
        driver = build_driver(offers_email_2fa=True, liveness=True, locations=[])
        out = tmp_path / "seed.json"
        res = ghl_auth.run("s", str(out), {}, store=store, probe=probe, driver=driver)
        assert res.tier == ghl_auth.TIER2 and res.ok is True
        healed = store.written.get(fb.REFRESH_TOKEN_KEY, "")
        assert healed, "self-heal must persist a fresh token to the store"
        side = (tmp_path / "ghl-auth-tier.json").read_text(encoding="utf-8")
        assert healed not in side
        assert healed not in res.reason and healed not in res.client_message

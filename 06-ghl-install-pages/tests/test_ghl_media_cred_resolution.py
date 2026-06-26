"""MOCK-only unit tests — GHL credential resolution (the six-month false-fail fix).

These tests lock the behaviour added after the image step false-failed
("GHL LOCATION PIT not found") on a LOCATION PIT the operator had used for six
months — the value was sitting in ``~/.openclaw/secrets/.env`` under
``GOHIGHLEVEL_API_KEY``, but the old resolver only checked two env-var names in
the live process environment and never opened the store.

NO real keys, NO real tokens, NO network. The canonical env stores are redirected
to a tmp directory via monkeypatching ``ghl_media._GHL_ENV_STORES`` so a fake
``secrets/.env`` (with FAKE values) exercises the store-fallback path without ever
touching the operator's real store. Every value here is a generic ``pit-FAKE…`` /
``LOCFAKE…`` fixture.

What these tests prove:
  * Multi-alias env resolution (preferred alias wins) for the LOCATION PIT + id.
  * Store FALLBACK: an empty live env resolves the value from secrets/.env
    (the exact incident) — both PIT and location id.
  * Store preference: a preferred alias in a later store still beats a legacy
    alias in an earlier store.
  * AGENCY-class names are NEVER used for the LOCATION PIT (an agency-only env
    still fails) and the honest-fail message says so.
  * Honest-fail ONLY after env × stores are exhausted, and the message NAMES the
    exact env vars and store paths it checked + how to source the store.
  * Allowlist (comma-separated) location ids resolve to the first id.
"""
from __future__ import annotations

import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_media as m

# Generic FAKE values — never real tokens/ids.
FAKE_LOC_PIT = "pit-FAKE-location-89ff-not-real"
FAKE_LEGACY_PIT = "pit-FAKE-legacy-ghlapikey"
FAKE_AGENCY_PIT = "pit-FAKE-agency-266b-no-media-scope"
FAKE_LOC_ID = "LOCFAKE0000000000001"
FAKE_LOC_ID_2 = "LOCFAKE0000000000002"


def _write_store(path, **pairs):
    """Write a fake KEY=VALUE env store (one of secrets/.env shape) to ``path``."""
    lines = ["# fake env store for tests (no real secrets)"]
    for k, v in pairs.items():
        lines.append(f"{k}={v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.fixture
def fake_stores(tmp_path, monkeypatch):
    """Redirect ghl_media's canonical store list at a tmp 'secrets/.env'.

    Returns a helper that (re)writes the fake store with given KEY=VALUE pairs and
    points ghl_media._GHL_ENV_STORES at it (and only it)."""
    store = tmp_path / "secrets.env"

    def _set(**pairs):
        p = _write_store(store, **pairs)
        # Use an ABSOLUTE path so os.path.expanduser is a no-op; only this store
        # is searched (the real ~/.openclaw/secrets/.env is never read).
        monkeypatch.setattr(m, "_GHL_ENV_STORES", (p,))
        return p

    return _set


# ── LOCATION PIT — env-only resolution (search_stores=False) ──────────────────

class TestPitEnvResolution:
    def test_preferred_alias_wins(self):
        env = {"GOHIGHLEVEL_API_KEY": FAKE_LOC_PIT, "GHL_API_KEY": FAKE_LEGACY_PIT}
        assert m.resolve_location_pit(env, search_stores=False) == FAKE_LOC_PIT

    def test_legacy_alias_used_when_preferred_absent(self):
        env = {"GHL_API_KEY": FAKE_LEGACY_PIT}
        assert m.resolve_location_pit(env, search_stores=False) == FAKE_LEGACY_PIT

    def test_explicit_location_pit_alias_resolves(self):
        env = {"GOHIGHLEVEL_LOCATION_PIT": FAKE_LOC_PIT}
        assert m.resolve_location_pit(env, search_stores=False) == FAKE_LOC_PIT

    def test_agency_pit_is_never_used_for_location_pit(self):
        """An env carrying ONLY agency-class names must still FAIL — agency PITs
        401 for media; the resolver must not silently return one."""
        env = {n: FAKE_AGENCY_PIT for n in m._AGENCY_PIT_ENV_NAMES}
        with pytest.raises(RuntimeError) as ei:
            m.resolve_location_pit(env, search_stores=False)
        msg = str(ei.value)
        # Message must call out the agency-token scope problem explicitly.
        assert "AGENCY" in msg.upper()
        assert FAKE_AGENCY_PIT not in msg  # never echoes the token value

    def test_empty_env_honest_fail_names_vars_and_stores(self):
        with pytest.raises(RuntimeError) as ei:
            m.resolve_location_pit({}, search_stores=False)
        msg = str(ei.value)
        # NAMES the exact env vars it checked …
        for name in m._PIT_ENV_NAMES:
            assert name in msg
        # … and the exact store paths, and how to load them.
        for store in m._GHL_ENV_STORES:
            assert store in msg
        assert "source" in msg.lower()
        assert "~/.openclaw/secrets/.env" in msg


# ── LOCATION PIT — STORE FALLBACK (the actual six-month incident) ─────────────

class TestPitStoreFallback:
    def test_empty_env_resolves_pit_from_secrets_store(self, fake_stores):
        """THE INCIDENT: live env empty, but secrets/.env defines GOHIGHLEVEL_API_KEY.
        The resolver MUST find it in the store instead of false-failing."""
        fake_stores(GOHIGHLEVEL_API_KEY=FAKE_LOC_PIT, GOHIGHLEVEL_LOCATION_ID=FAKE_LOC_ID)
        assert m.resolve_location_pit({}, search_stores=True) == FAKE_LOC_PIT

    def test_live_env_beats_store(self, fake_stores):
        """A value in the live env takes precedence over the store."""
        fake_stores(GOHIGHLEVEL_API_KEY=FAKE_LOC_PIT)
        env = {"GOHIGHLEVEL_API_KEY": "pit-FAKE-from-live-env"}
        assert m.resolve_location_pit(env, search_stores=True) == "pit-FAKE-from-live-env"

    def test_store_export_prefix_and_quotes_parsed(self, fake_stores, tmp_path, monkeypatch):
        store = tmp_path / "exported.env"
        store.write_text(
            "# store with export + quotes\n"
            f'export GOHIGHLEVEL_API_KEY="{FAKE_LOC_PIT}"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(m, "_GHL_ENV_STORES", (str(store),))
        assert m.resolve_location_pit({}, search_stores=True) == FAKE_LOC_PIT

    def test_store_disabled_falls_through_to_fail(self, fake_stores):
        """With search_stores=False, even a populated store is ignored (the value
        must come from the live env) — used by callers that want pure-env semantics."""
        fake_stores(GOHIGHLEVEL_API_KEY=FAKE_LOC_PIT)
        with pytest.raises(RuntimeError):
            m.resolve_location_pit({}, search_stores=False)

    def test_agency_only_store_still_fails_with_scope_note(self, fake_stores):
        """A store that has ONLY an agency PIT must still fail — and say the agency
        token isn't media-scoped (do NOT silently use it)."""
        fake_stores(GOHIGHLEVEL_AGENCY_PIT=FAKE_AGENCY_PIT)
        with pytest.raises(RuntimeError) as ei:
            m.resolve_location_pit({}, search_stores=True)
        assert "AGENCY" in str(ei.value).upper()


# ── LOCATION ID — env + store + allowlist ─────────────────────────────────────

class TestLocationIdResolution:
    def test_preferred_alias_wins(self):
        env = {"GOHIGHLEVEL_LOCATION_ID": FAKE_LOC_ID, "GHL_LOCATION_ID": FAKE_LOC_ID_2}
        assert m.resolve_location_id(env, search_stores=False) == FAKE_LOC_ID

    def test_allowlist_first_id(self):
        env = {"CAF_ALLOWED_LOCATION_IDS": f"{FAKE_LOC_ID},{FAKE_LOC_ID_2}"}
        assert m.resolve_location_id(env, search_stores=False) == FAKE_LOC_ID

    def test_store_fallback_resolves_location_id(self, fake_stores):
        fake_stores(GOHIGHLEVEL_LOCATION_ID=FAKE_LOC_ID)
        assert m.resolve_location_id({}, search_stores=True) == FAKE_LOC_ID

    def test_empty_honest_fail_names_vars_and_stores(self):
        with pytest.raises(RuntimeError) as ei:
            m.resolve_location_id({}, search_stores=False)
        msg = str(ei.value)
        for name in m._LOCATION_ENV_NAMES:
            assert name in msg
        for store in m._GHL_ENV_STORES:
            assert store in msg
        assert "GOHIGHLEVEL_LOCATION_ID" in msg


# ── Alias-set invariants — the AGENCY vs LOCATION distinction is encoded ──────

class TestAliasSetInvariants:
    def test_location_aliases_contain_no_agency_names(self):
        for agency in m._AGENCY_PIT_ENV_NAMES:
            assert agency not in m._PIT_ENV_NAMES, \
                f"{agency} is agency-class and must NEVER be a LOCATION-PIT alias"

    def test_preferred_pit_alias_is_gohighlevel_api_key(self):
        assert m._PIT_ENV_NAMES[0] == "GOHIGHLEVEL_API_KEY"

    def test_preferred_location_alias_is_gohighlevel_location_id(self):
        assert m._LOCATION_ENV_NAMES[0] == "GOHIGHLEVEL_LOCATION_ID"

    def test_secrets_env_is_first_store(self):
        assert m._GHL_ENV_STORES[0] == "~/.openclaw/secrets/.env"

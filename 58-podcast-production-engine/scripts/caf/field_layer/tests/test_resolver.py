#!/usr/bin/env python3
"""Resolver tests: ENV-CHECK-BEFORE-FAIL, isolation, ordering. Hermetic: the
file, openclaw.json, auth-profiles, shared-resolver, and sweep scanners are all
patched to empty so only the controlled process environment is in play."""
from __future__ import annotations

import pytest

from field_layer import constants, resolver


@pytest.fixture
def clean_env(monkeypatch):
    # Remove every alias so the box's real environment cannot leak in.
    for key in (*constants.LOCATION_PIT_ALIASES, *constants.LOCATION_ID_ALIASES,
                *constants.FORBIDDEN_PIT_ALIASES):
        monkeypatch.delenv(key, raising=False)
    # Silence every non-process-env store.
    monkeypatch.setattr(resolver, "_parse_env_file", lambda path: {})
    monkeypatch.setattr(resolver, "_openclaw_json_stores",
                        lambda: [("openclaw.json:env.vars", {}), ("openclaw.json:env.root", {})])
    monkeypatch.setattr(resolver, "_auth_profiles_store", lambda: {})
    monkeypatch.setattr(resolver, "_shared_resolver_lookup", lambda alias: None)
    monkeypatch.setattr(resolver, "_path_only_sweep", lambda: [])
    return monkeypatch


def test_canonical_alias_resolves_from_live_env(clean_env):
    clean_env.setenv("GOHIGHLEVEL_API_KEY", "pit-abc1234567")
    clean_env.setenv("GHL_LOCATION_ID", "loc-1")
    res = resolver.resolve_credentials()
    assert res.pit_found is True
    assert res.pit_alias == "GOHIGHLEVEL_API_KEY"
    assert res.pit_store == "live-process-env"
    assert res.prefix_ok is True
    assert res.pit_length == len("pit-abc1234567")
    assert res.location_found is True and res.location_id == "loc-1"
    # No token value ever leaves via the public dict.
    assert "pit-abc1234567" not in str(res.to_public_dict())


def test_convertflow_branded_alias_resolves(clean_env):
    clean_env.setenv("CONVERTFLOW_API_KEY", "pit-brandedvalue1")
    res = resolver.resolve_credentials()
    assert res.pit_found is True
    assert res.pit_alias == "CONVERTFLOW_API_KEY"


def test_agency_pit_is_never_resolved(clean_env):
    # Only the forbidden agency alias is present.
    clean_env.setenv("GOHIGHLEVEL_AGENCY_PIT", "pit-agencytoken1")
    res = resolver.resolve_credentials()
    assert res.pit_found is False
    assert res.pit_alias is None


def test_canonical_wins_over_legacy_alias(clean_env):
    clean_env.setenv("GHL_API_KEY", "pit-legacyvalue1")
    clean_env.setenv("GOHIGHLEVEL_API_KEY", "pit-canonicalv1")
    res = resolver.resolve_credentials()
    assert res.pit_alias == "GOHIGHLEVEL_API_KEY"


def test_payload_location_mismatch_flags_isolation(clean_env):
    clean_env.setenv("GOHIGHLEVEL_API_KEY", "pit-abc1234567")
    clean_env.setenv("GHL_LOCATION_ID", "loc-1")
    res = resolver.resolve_credentials(payload_location_id="loc-2")
    assert res.payload_location_mismatch is True


def test_missing_everywhere_is_a_valid_missing_verdict(clean_env):
    res = resolver.resolve_credentials()
    assert res.pit_found is False
    assert res.prefix_ok is False
    # The audit records that every alias was checked in every store.
    checked_aliases = {row["alias"] for row in res.audit}
    for alias in constants.LOCATION_PIT_ALIASES:
        assert alias in checked_aliases


def test_non_pit_prefix_flags_prefix_not_ok(clean_env):
    clean_env.setenv("GOHIGHLEVEL_API_KEY", "not-a-pit-token")
    res = resolver.resolve_credentials()
    assert res.pit_found is True
    assert res.prefix_ok is False

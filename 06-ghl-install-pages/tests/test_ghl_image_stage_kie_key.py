"""MOCK-only tests: ghl_image_stage resolves the KIE key through the shared
secret-name canon (shared-utils/secret_names.json), not its own bare-name list.

No real keys, no network. Every value is a generic FAKE fixture.
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_image_stage as st

FAKE_KEY = "FAKEkie0000000000000000000000001"  # 32 chars, not placeholder-shaped


def _canon_kie_family() -> list[str]:
    path = os.path.join(_TOOLS_DIR, "..", "..", "shared-utils", "secret_names.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["canonical_names"]["KIE_API_KEY"]


@pytest.fixture
def no_stores(monkeypatch, tmp_path):
    monkeypatch.setattr(st, "_KIE_ENV_STORES", (str(tmp_path / "absent.env"),))


def test_names_come_from_the_shared_canon():
    assert list(st._KIE_KEY_ENV_NAMES) == _canon_kie_family()


def test_every_canon_alias_resolves_from_env(no_stores):
    for name in _canon_kie_family():
        assert st._resolve_kie_api_key({name: FAKE_KEY}) == FAKE_KEY, name


def test_alias_resolves_from_store(monkeypatch, tmp_path):
    alias = _canon_kie_family()[1]
    store = tmp_path / ".env"
    store.write_text(f"# fake\n{alias}={FAKE_KEY}\n", encoding="utf-8")
    monkeypatch.setattr(st, "_KIE_ENV_STORES", (str(store),))
    assert st._resolve_kie_api_key({}) == FAKE_KEY


def test_placeholder_is_rejected_and_fails_honestly(no_stores):
    with pytest.raises(st.ImagePipelineError) as ei:
        st._resolve_kie_api_key({"KIE_API_KEY": "PASTE_REAL_TOKEN_HERE"})
    assert ei.value.honest_fail is True
    assert "PASTE_REAL_TOKEN_HERE" not in str(ei.value)  # never echo a value


def test_absent_error_names_aliases_and_says_client_own_key(no_stores):
    with pytest.raises(st.ImagePipelineError) as ei:
        st._resolve_kie_api_key({})
    msg = str(ei.value)
    assert "client's" in msg and "operator's own" not in msg
    for name in _canon_kie_family():
        assert name in msg

"""MOCK-only unit tests — ghl_media folder-per-funnel discipline (transcript §3).

NO network of any kind: ``create_media_folder``'s HTTP is mocked via the
injectable ``opener``. Covers the transcript media-storage rule (ONE clearly-named
folder per funnel/website + per-page subfolders, never browser-routed) and the
fail-soft name-prefix fallback when the GHL plan has no folder endpoint.

No real client/operator names, ids, emails, or location-ids appear — all values
are generic / parameterised fakes.
"""
from __future__ import annotations

import io
import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import ghl_media as m


# ── fakes ────────────────────────────────────────────────────────────────────
class _Resp:
    def __init__(self, code: int, body: dict):
        self._code = code
        self._raw = json.dumps(body).encode("utf-8")

    def getcode(self):
        return self._code

    def read(self):
        return self._raw


def _folder_opener(captured: list):
    """Returns a fresh folderId per call; records the POST bodies for assertions."""
    counter = {"n": 0}

    def _open(req, timeout):
        counter["n"] += 1
        captured.append(json.loads(req.data.decode("utf-8")))
        return _Resp(201, {"folderId": f"fld-{counter['n']}"})

    return _open


# ── pure planner ─────────────────────────────────────────────────────────────
def test_plan_one_folder_with_per_page_subfolders():
    plan = m.funnel_media_folder_plan("ZHC test", ["Opt-in", "Sales", "Thank You"])
    assert plan["folder"] == "ZHC test"
    assert plan["subfolders"] == ["Opt-in", "Sales", "Thank You"]


def test_plan_dedupes_and_drops_blanks_case_insensitive():
    plan = m.funnel_media_folder_plan("ZHC test", ["Home", "home", "", "  ", "About"])
    assert plan["subfolders"] == ["Home", "About"]


def test_plan_requires_funnel_name():
    with pytest.raises(ValueError):
        m.funnel_media_folder_plan("")


# ── side-effecting ensure (folders mode) ─────────────────────────────────────
def test_ensure_creates_funnel_folder_then_nested_subfolders():
    captured: list = []
    out = m.ensure_funnel_media_folders(
        "ZHC test", "loc-123", "pit-xyz",
        page_names=["Opt-in", "Sales"],
        opener=_folder_opener(captured),
    )
    assert out["mode"] == "folders"
    assert out["browser_routed"] is False           # transcript: NO browser control
    assert out["funnel"]["folderId"] == "fld-1"
    # 1 funnel folder + 2 page subfolders = 3 POSTs
    assert len(captured) == 3
    # the funnel folder is created at root (no parentId)
    assert "parentId" not in captured[0]
    # each subfolder nests under the funnel folder id
    assert captured[1]["parentId"] == "fld-1"
    assert captured[2]["parentId"] == "fld-1"
    assert out["pages"]["Opt-in"]["folderId"] == "fld-2"
    assert out["pages"]["Sales"]["folderId"] == "fld-3"


def test_ensure_no_pages_creates_only_the_funnel_folder():
    captured: list = []
    out = m.ensure_funnel_media_folders(
        "ZHC site", "loc-123", "pit-xyz", opener=_folder_opener(captured)
    )
    assert out["mode"] == "folders"
    assert out["pages"] == {}
    assert len(captured) == 1


# ── fail-soft to name-prefix when the folder endpoint is unavailable ─────────
def test_ensure_falls_back_to_name_prefix_on_runtime_error():
    def _broken(req, timeout):
        raise RuntimeError("folder endpoint unavailable on this plan")

    out = m.ensure_funnel_media_folders(
        "ZHC test", "loc-123", "pit-xyz",
        page_names=["Opt-in"], opener=_broken,
    )
    assert out["mode"] == "name-prefix"
    assert out["browser_routed"] is False
    assert out["funnel"]["name_prefix"].endswith("__")
    assert "ZHC-test" in out["funnel"]["name_prefix"]
    assert out["pages"]["Opt-in"]["name_prefix"].endswith("__")


def test_ensure_subfolder_failure_is_non_fatal():
    """Funnel folder succeeds, a subfolder POST fails → that page name-prefixes,
    the funnel folder is retained (organization is not lost)."""
    state = {"n": 0}

    def _flaky(req, timeout):
        state["n"] += 1
        if state["n"] == 1:
            return _Resp(201, {"folderId": "fld-root"})
        raise RuntimeError("subfolder create rejected")

    out = m.ensure_funnel_media_folders(
        "ZHC test", "loc-123", "pit-xyz",
        page_names=["Sales"], opener=_flaky,
    )
    assert out["mode"] == "folders"
    assert out["funnel"]["folderId"] == "fld-root"
    assert out["pages"]["Sales"]["name_prefix"].endswith("__")


def test_ensure_requires_creds():
    with pytest.raises(ValueError):
        m.ensure_funnel_media_folders("ZHC test", "", "pit")
    with pytest.raises(ValueError):
        m.ensure_funnel_media_folders("ZHC test", "loc", "")

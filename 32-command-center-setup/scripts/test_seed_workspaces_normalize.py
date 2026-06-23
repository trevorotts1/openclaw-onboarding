"""Regression test for the seed-workspaces.py departments normalizer.

Guards the fix for the `sync-extensions.sh --converge` Step-4 crash:
`'str' object has no attribute 'get'` raised when departments.json contained
string entries instead of dicts. The normalizer must accept all three real-world
shapes (list-of-dicts, list-of-strings, dict-of-dicts) and emit list-of-dicts
with an `id` and a derived `name` on every entry.
"""
import importlib.util
import os

import pytest

_SW = os.path.join(os.path.dirname(os.path.abspath(__file__)), "seed-workspaces.py")
_spec = importlib.util.spec_from_file_location("seed_workspaces", _SW)
_sw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sw)
normalize = _sw._normalize_departments


def test_list_of_dicts_passthrough():
    out = normalize([{"id": "marketing", "name": "Marketing", "emoji": "📢"}])
    assert out[0]["id"] == "marketing"
    assert out[0]["name"] == "Marketing"


def test_list_of_strings_is_the_crash_shape():
    # This is the exact payload that raised 'str' object has no attribute 'get'.
    out = normalize(["marketing", "sales", "personal-assistant", "dept-finance"])
    assert all(isinstance(d, dict) for d in out)
    assert out[0] == {"id": "marketing", "name": "Marketing"}
    assert out[2] == {"id": "personal-assistant", "name": "Personal Assistant"}
    assert out[3] == {"id": "dept-finance", "name": "Finance"}
    # The crashing access now works on every entry.
    for d in out:
        assert d.get("id")


def test_dict_of_dicts_shape():
    out = normalize({"marketing": {"name": "Marketing"}, "sales": {"emoji": "💰"}})
    by_id = {d["id"]: d for d in out}
    assert by_id["marketing"]["name"] == "Marketing"
    assert by_id["sales"]["name"] == "Sales"  # derived from slug


def test_dict_missing_name_derives_title_case():
    out = normalize([{"id": "strategy-innovation"}])
    assert out[0]["name"] == "Strategy Innovation"


def test_dict_with_slug_key_only():
    out = normalize([{"slug": "operations"}])
    assert out[0]["id"] == "operations"
    assert out[0]["name"] == "Operations"


def test_none_and_non_list_return_safely():
    assert normalize(None) is None
    assert normalize(42) is None


def test_seed_loop_does_not_crash_on_bare_strings(monkeypatch, tmp_path):
    # Build a throwaway sqlite db with the minimal schema seed() touches, then
    # prove seed() runs end-to-end on a bare-string department list.
    import sqlite3
    db = tmp_path / "mc.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE companies (id TEXT PRIMARY KEY, name TEXT, slug TEXT, industry TEXT, config TEXT);
        CREATE TABLE workspaces (id TEXT PRIMARY KEY, name TEXT, slug TEXT UNIQUE,
            description TEXT, icon TEXT, company_id TEXT);
        """
    )
    conn.commit()
    conn.close()
    company_info = {
        "name": "Test Co", "slug": "test-co", "industry": "",
        "brand_primary": "#000", "brand_accent": "#fff", "brand_text": "#111",
    }
    # The crash shape: a list of bare strings.
    _sw.seed(str(db), ["marketing", "sales", "operations"], company_info)
    conn = sqlite3.connect(db)
    rows = {r[0] for r in conn.execute("SELECT id FROM workspaces").fetchall()}
    conn.close()
    assert {"marketing", "sales", "operations"} <= rows

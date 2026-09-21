"""Regression test for the seed-workspaces.py departments normalizer.

Guards the fix for the `sync-extensions.sh --converge` Step-4 crash:
`'str' object has no attribute 'get'` raised when departments.json contained
string entries instead of dicts. The normalizer must accept all four real-world
shapes (list-of-dicts, list-of-strings, dict-of-dicts, and an object WRAPPING the
list under "departments") and emit list-of-dicts with an `id` and a derived
`name` on every entry.

It also guards the second defect: the old dict branch folded EVERY key of a
wrapped/envelope payload in as a department id, which seeded bogus workspaces
named "Company", "Total Departments", "Total Roles" and "Departments" onto a live
client board. An object that carries no department list must now FAIL LOUDLY —
naming the path and the top-level type — never quietly become departments.
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


def test_none_returns_safely():
    # None means "nothing was loaded" — not malformed. Still a quiet None.
    assert normalize(None) is None


def test_scalar_payload_fails_loudly():
    # A bare scalar at the top level of departments.json is a malformed file,
    # not an empty one. It must name the path and the top-level type, never
    # return a quiet None that a caller reads as "no departments".
    with pytest.raises(_sw.MalformedDepartmentsError) as exc:
        normalize(42, path="/box/zero-human-company/acme/departments.json")
    assert "int" in str(exc.value)
    assert "/box/zero-human-company/acme/departments.json" in str(exc.value)


# ─── The wrapped-object (envelope) shape ─────────────────────────────────────
# A client Mac carried
#   {"company": ..., "total_departments": 34, "total_roles": 416,
#    "departments": [...]}
# The old dict branch folded EVERY key in as a department id, so the board got
# four bogus workspaces named "Company", "Total Departments", "Total Roles" and
# "Departments". These guard that it can never happen again.

_REAL_DEPTS = [
    {"id": "dept-ceo", "slug": "ceo", "name": "CEO"},
    {"id": "dept-marketing", "slug": "marketing", "name": "Marketing"},
]
_BOGUS_NAMES = {"Company", "Total Departments", "Total Roles", "Departments"}


def test_envelope_with_departments_list_is_unwrapped():
    out = normalize({
        "company": "Acme Industries",
        "total_departments": 2,
        "total_roles": 18,
        "departments": _REAL_DEPTS,
    })
    assert [d["id"] for d in out] == ["dept-ceo", "dept-marketing"]
    assert _BOGUS_NAMES.isdisjoint({d["name"] for d in out})


def test_retire_script_provenance_shape_is_unwrapped():
    # retire-confirmed-decline.sh writes {removedWithProvenance, departments};
    # build-workforce.py preserves that dict shape on later builds.
    out = normalize({
        "removedWithProvenance": [{"slug": "legal", "retiredAt": "2026-08-07"}],
        "departments": _REAL_DEPTS,
    })
    assert [d["slug"] for d in out] == ["ceo", "marketing"]
    assert "Removed With Provenance" not in {d["name"] for d in out}


def test_envelope_without_departments_key_fails_loudly():
    with pytest.raises(_sw.MalformedDepartmentsError) as exc:
        normalize(
            {"company": "Acme", "total_departments": 34, "total_roles": 416},
            path="/box/zero-human-company/acme/departments.json",
        )
    msg = str(exc.value)
    assert "/box/zero-human-company/acme/departments.json" in msg
    assert "dict" in msg
    assert "'company'" in msg  # the offending keys are named for the operator


def test_departments_key_holding_a_slug_keyed_map_is_folded():
    # The shape the client Mac actually carries: the envelope's "departments"
    # key holds an OBJECT keyed by slug, not a list. 34 real departments used
    # to read as a hard refusal here.
    out = normalize({
        "company": "Acme Industries",
        "total_departments": 2,
        "total_roles": 18,
        "departments": {
            "account-management-dept": {"name": "Account Management"},
            "audio-dept": {"name": "Audio"},
        },
    }, path="/box/zero-human-company/acme/departments.json")
    assert [d["id"] for d in out] == ["account-management-dept", "audio-dept"]
    assert [d["slug"] for d in out] == ["account-management-dept", "audio-dept"]
    assert [d["name"] for d in out] == ["Account Management", "Audio"]


def test_folded_entry_keeps_its_own_id_and_slug():
    out = normalize({"departments": {"acct": {"id": "dept-account",
                                              "slug": "account",
                                              "name": "Account"}}})
    assert out[0]["id"] == "dept-account"
    assert out[0]["slug"] == "account"


def test_departments_key_holding_a_non_object_map_fails_loudly():
    # A scalar value is what separates a metadata envelope from a department
    # map. Refuse it rather than seeding a workspace named after a role count.
    for bad in ({"marketing": "not-an-object"}, {}, 42, "marketing"):
        with pytest.raises(_sw.MalformedDepartmentsError):
            normalize({"departments": bad}, path="/x/departments.json")


def test_client_envelope_metadata_never_becomes_a_workspace():
    # The lead regression, stated against the real file shape: folding the
    # "departments" map must not drag company / total_departments / total_roles
    # in as departments. These are the four bogus workspaces seen on the board.
    out = normalize({
        "company": "Acme", "total_departments": 34, "total_roles": 416,
        "departments": {"marketing-dept": {"name": "Marketing"}},
    })
    produced = {d.get("id") for d in out} | {d.get("name") for d in out}
    assert produced.isdisjoint(_BOGUS_NAMES)
    assert produced.isdisjoint({"company", "total_departments", "total_roles",
                                "departments"})
    assert produced == {"marketing-dept", "Marketing"}


def test_envelope_keys_never_become_department_names():
    # The exact regression: whatever happens, no normalizer output may carry a
    # department derived from an envelope's metadata key.
    for payload in (
        {"company": "Acme", "total_departments": 2, "total_roles": 18,
         "departments": _REAL_DEPTS},
        {"removedWithProvenance": [], "departments": _REAL_DEPTS},
    ):
        out = normalize(payload)
        produced = {d.get("id") for d in out} | {d.get("name") for d in out}
        assert produced.isdisjoint(_BOGUS_NAMES)
        assert produced.isdisjoint({"company", "total_departments", "total_roles",
                                    "departments", "removedWithProvenance"})


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


def test_seed_loop_never_writes_envelope_keys_as_workspaces(tmp_path):
    # End-to-end: the envelope shape that put "Company" / "Total Departments" /
    # "Total Roles" / "Departments" workspaces on a live client board must now
    # seed the REAL departments and nothing else.
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
    payload = {
        "company": "Test Co",
        "total_departments": 2,
        "total_roles": 18,
        "departments": [
            {"id": "dept-marketing", "slug": "marketing", "name": "Marketing"},
            {"id": "dept-legal", "slug": "legal", "name": "Legal"},
        ],
    }
    _sw.seed(str(db), normalize(payload), company_info)

    conn = sqlite3.connect(db)
    names = {r[0] for r in conn.execute("SELECT name FROM workspaces").fetchall()}
    conn.close()
    assert names == {"Marketing", "Legal"}, names
    assert _BOGUS_NAMES.isdisjoint(names)

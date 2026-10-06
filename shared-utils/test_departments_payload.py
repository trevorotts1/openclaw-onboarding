"""The ONE departments.json envelope normalizer's own unit tests.

`departments_payload._demo()` is the module's runnable self-check (it also runs
under `python3 shared-utils/departments_payload.py`). Running it here puts it in
CI alongside the reader-level regressions in
32-command-center-setup/scripts/test_seed_workspaces_normalize.py.
"""
import importlib.util
import os

import pytest

_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "departments_payload.py")
_spec = importlib.util.spec_from_file_location("departments_payload_under_test", _MOD)
dp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dp)


def test_module_self_check_passes(capsys):
    dp._demo()
    assert "all self-checks pass" in capsys.readouterr().out


def test_envelope_is_unwrapped_not_folded():
    depts = [{"id": "dept-sales", "slug": "sales", "name": "Sales"}]
    out = dp.normalize_departments({
        "company": "Acme", "total_departments": 1, "total_roles": 9,
        "departments": depts,
    })
    assert out == depts


def test_departments_key_holding_a_slug_keyed_map_is_folded():
    # The shape a real client Mac carries. Keys become id/slug, file order is
    # preserved, and the envelope's metadata keys are never folded in.
    out = dp.normalize_departments({
        "company": "Acme", "total_departments": 2, "total_roles": 18,
        "departments": {
            "account-management-dept": {"name": "Account Management"},
            "audio-dept": {"name": "Audio"},
        },
    })
    # No entry carries id/slug/folder, so the key is the only identity — minus
    # its "-dept" suffix. See test_entry_identity_beats_the_map_key for the
    # client artifact where the entry DOES name its folder.
    assert out == [
        {"name": "Account Management", "id": "account-management",
         "slug": "account-management"},
        {"name": "Audio", "id": "audio", "slug": "audio"},
    ]


def test_folded_entry_that_names_itself_keeps_its_own_identity():
    out = dp.normalize_departments(
        {"departments": {"acct": {"id": "dept-account", "slug": "account"}}})
    assert out == [{"id": "dept-account", "slug": "account"}]


@pytest.mark.parametrize("bad", [
    {"marketing": "not-an-object"},   # a scalar value marks a metadata envelope
    {},                               # the shipped empty default is [], never {}
    42,
    "marketing",
])
def test_departments_key_holding_a_non_department_map_is_refused(bad):
    with pytest.raises(dp.MalformedDepartmentsError) as exc:
        dp.normalize_departments({"departments": bad},
                                 path="/box/acme/departments.json")
    assert "/box/acme/departments.json" in str(exc.value)


# This module is MIRRORED rule for rule with blackceo-command-center's
# shared-utils/departments_payload.py (CC v7.6.30, 8828dec6e). The two repos
# read the SAME artifact off the SAME box, so the refusal an operator sees must
# read the same in both. These pin the two distinct messages; if either is
# reworded here without re-mirroring there, this fails.
def test_object_under_departments_key_gets_the_department_map_wording():
    with pytest.raises(dp.MalformedDepartmentsError) as exc:
        dp.normalize_departments({"departments": {"marketing": "yes"}},
                                 path="/box/acme/departments.json")
    assert str(exc.value) == (
        "departments.json: 'departments' key holds an object that is not a "
        "department map (it is empty, or a value is not an object); expected a "
        "list, or an object keyed by department slug whose values are all "
        "objects (path: /box/acme/departments.json)")


def test_non_object_under_departments_key_gets_the_short_wording():
    with pytest.raises(dp.MalformedDepartmentsError) as exc:
        dp.normalize_departments({"departments": 42},
                                 path="/box/acme/departments.json")
    assert str(exc.value) == (
        "departments.json: 'departments' key holds int, expected a list "
        "(path: /box/acme/departments.json)")


def test_metadata_only_object_is_refused_with_path_and_type():
    with pytest.raises(dp.MalformedDepartmentsError) as exc:
        dp.normalize_departments(
            {"company": "Acme", "total_departments": 34, "total_roles": 416},
            path="/box/zero-human-company/acme/departments.json")
    msg = str(exc.value)
    assert "/box/zero-human-company/acme/departments.json" in msg
    assert "dict with keys" in msg


def test_lenient_wrapper_never_raises_but_stays_loud(capsys):
    out = dp.departments_or_empty({"company": "Acme", "total_roles": 9},
                                  path="/x/departments.json")
    assert out == []
    assert "/x/departments.json" in capsys.readouterr().err


# ─── Entry identity beats the map key (mirrors CC v7.6.35) ──────────────────
# Precedence: id -> slug -> folder -> the map key. The key is used ONLY when
# the entry carries none of the three, and a slug taken FROM the key loses a
# trailing "-dept". An entry's own value is never rewritten.

def test_entry_identity_beats_the_map_key():
    # The real client artifact: keyed "<name>-dept", each entry naming its folder.
    out = dp.normalize_departments({
        "company": "Acme", "total_departments": 2, "total_roles": 34,
        "departments": {
            "account-management-dept": {"name": "Account Management",
                                        "folder": "account-management"},
            "audio-dept": {"name": "Audio", "folder": "audio"},
            # folder DELIBERATELY unequal to the key stem: where folder ==
            # key-minus-dept, folding on the key gives the same answer and an
            # id-only mutation passes. This one discriminates.
            "client-success-dept": {"name": "Client Success",
                                    "folder": "accounts"},
        },
    })
    assert [d["id"] for d in out] == ["account-management", "audio", "accounts"]
    assert [d["slug"] for d in out] == ["account-management", "audio", "accounts"]


@pytest.mark.parametrize("entry,want_id,want_slug", [
    ({"id": "dept-m", "slug": "mkt", "folder": "f"}, "dept-m", "mkt"),
    ({"slug": "mkt", "folder": "f"},                 "mkt",    "mkt"),
    ({"folder": "f"},                                "f",      "f"),
    ({"name": "M"},                                  "m",      "m"),
])
def test_fold_precedence_id_slug_folder_key(entry, want_id, want_slug):
    out = dp.normalize_departments({"departments": {"m-dept": entry}})
    assert out[0]["id"] == want_id
    assert out[0]["slug"] == want_slug


def test_dept_suffix_stripped_only_when_the_slug_came_from_the_key():
    # An entry's OWN value keeps its suffix; only a key-derived slug loses it.
    own = dp.normalize_departments({"departments": {"x": {"slug": "legal-dept"}}})
    assert own[0]["slug"] == "legal-dept"
    from_key = dp.normalize_departments({"departments": {"legal-dept": {"name": "L"}}})
    assert from_key[0]["slug"] == "legal"


def test_a_key_that_is_only_the_suffix_is_kept_whole():
    out = dp.normalize_departments({"departments": {"-dept": {"name": "Odd"}}})
    assert out[0]["id"] == "-dept"

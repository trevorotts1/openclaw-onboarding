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

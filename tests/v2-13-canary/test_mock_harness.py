#!/usr/bin/env python3
"""Mock harness checks: both scripted paths run, order rules hold, fallback only when needed.

Runs standalone (python3 test_mock_harness.py) and under pytest.
"""

from __future__ import annotations

import mock_harness as mh


def _spec() -> dict:
    return mh.load_spec()


def _shot() -> dict:
    return mh.load_fixture("shot_painful_moment.json")


def test_primary_path_dispatches_only_the_primary():
    result = mh.run_path(_spec(), _shot(), mh.PRIMARY_OK)
    assert result["dispatch_order"] == [mh.ROSTER[0]]
    assert result["attempts"] == [mh.ROSTER[0]]
    assert result["winner"] == mh.ROSTER[0]
    assert result["final_status"] == "succeeded"
    assert result["saved_file"]


def test_fallback_path_runs_primary_then_backup():
    result = mh.run_path(_spec(), _shot(), mh.FALLBACK)
    assert result["dispatch_order"] == [mh.ROSTER[0], mh.ROSTER[1]]
    assert result["attempts"] == [mh.ROSTER[0], mh.ROSTER[1]]
    assert result["winner"] == mh.ROSTER[1]
    assert result["final_status"] == "succeeded"
    assert result["saved_file"]


def test_both_fail_path_records_no_winner():
    result = mh.run_path(_spec(), _shot(), mh.BOTH_FAIL)
    assert result["dispatch_order"] == [mh.ROSTER[0], mh.ROSTER[1]]
    assert result["winner"] is None
    assert result["final_status"] == "failed"
    assert result["saved_file"] is None


def test_backup_never_runs_without_a_primary_attempt():
    client = mh.ScriptedKIE({mh.ROSTER[1]: [mh.load_fixture("infinitalk_backup_success.json")]})
    try:
        mh.verify_attempt_order([mh.ROSTER[1]])
        client.dispatch(mh.ROSTER[1], {"shot_id": _shot()["shot_id"]})
    except mh.SpecError:
        return
    raise AssertionError("a backup-only attempt was accepted")


def test_unknown_provider_is_refused():
    client = mh.ScriptedKIE({})
    try:
        client.dispatch("somebody/new-model", {"shot_id": _shot()["shot_id"]})
    except mh.SpecError:
        return
    raise AssertionError("an out-of-roster provider was dispatched")


def test_script_exhaustion_is_refused():
    client = mh.ScriptedKIE({mh.ROSTER[0]: []})
    try:
        client.dispatch(mh.ROSTER[0], {"shot_id": _shot()["shot_id"]})
    except mh.SpecError:
        return
    raise AssertionError("an exhausted script was dispatched")


def test_unknown_path_is_refused():
    try:
        mh.run_path(_spec(), _shot(), "paid_live")
    except mh.SpecError:
        return
    raise AssertionError("an unknown path was accepted")


def test_style_mismatch_is_refused():
    shot = dict(_shot())
    shot["style"] = "photoreal"
    try:
        mh.run_path(_spec(), shot, mh.PRIMARY_OK)
    except mh.SpecError:
        return
    raise AssertionError("a shot in the wrong look was accepted")


def test_ledger_refuses_a_nonzero_price():
    ledger = mh.Ledger()
    try:
        ledger.record_mock(mh.ROSTER[0], _shot()["shot_id"], price_usd=0.24)
    except mh.LiveCallRefused:
        return
    raise AssertionError("a nonzero price was recorded")


def test_every_fixture_response_is_marked_mock_and_unpaid():
    for name in (
        "kling_primary_success.json",
        "kling_primary_failure.json",
        "infinitalk_backup_success.json",
        "infinitalk_backup_failure.json",
    ):
        fixture = mh.load_fixture(name)
        assert fixture["mock"] is True, name
        assert fixture["paid"] is False, name
        assert fixture["model"] in mh.ROSTER, name


if __name__ == "__main__":
    failures = []
    names = [n for n in sorted(globals()) if n.startswith("test_")]
    for name in names:
        fn = globals()[name]
        if not callable(fn):
            continue
        try:
            fn()
            print(f"PASS {name}")
        except Exception as exc:  # noqa: BLE001 - report then fail
            failures.append(name)
            print(f"FAIL {name}: {exc}")
    print(f"total={len(names)} failed={len(failures)}")
    raise SystemExit(1 if failures else 0)

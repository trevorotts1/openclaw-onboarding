#!/usr/bin/env python3
"""Canary spec checks: roster order, closed provider set, shot bounds, zero spend.

Runs standalone (python3 test_canary_spec.py) and under pytest.
"""

from __future__ import annotations

import json
import pathlib
import re

import mock_harness as mh

HERE = pathlib.Path(__file__).resolve().parent

#: Every provider-shaped token allowed to appear in SPEC.md.
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]*/[A-Za-z0-9_-]+")


def _spec() -> dict:
    return mh.load_spec()


def test_spec_loads_and_validates():
    mh.validate_spec(_spec())


def test_primary_is_kling_first():
    spec = _spec()
    assert spec["providers"][0]["model"] == "kling/ai-avatar-standard"
    assert spec["providers"][0]["role"] == "primary"
    assert spec["providers"][0]["rank"] == 1


def test_backup_is_infinitalk_second():
    spec = _spec()
    assert spec["providers"][1]["model"] == "infinitalk/from-audio"
    assert spec["providers"][1]["role"] == "backup"
    assert spec["providers"][1]["rank"] == 2


def test_roster_is_closed_at_exactly_two_entries():
    spec = _spec()
    models = tuple(p["model"] for p in spec["providers"])
    assert models == mh.ROSTER
    assert len(models) == 2
    assert set(models) == set(mh.ROSTER)


def test_shot_count_is_one_or_two():
    shots = _spec()["shots"]
    assert shots["min"] == 1
    assert shots["max"] == 2
    assert 1 <= shots["count"] <= 2
    assert shots["same_keyframe"] is True
    assert shots["style"] == "cartoon"


def test_window_spends_nothing():
    spec = _spec()
    assert spec["mode"] == "mock"
    assert spec["spend"]["allowed"] is False
    assert float(spec["spend"]["ceiling_usd"]) == 0.0
    assert int(spec["spend"]["paid_calls"]) == 0
    assert spec["routing"]["through_skill"] == 74


def test_spec_md_agrees_with_json_and_carries_no_other_provider_token():
    spec = _spec()
    text = (HERE / "SPEC.md").read_text(encoding="utf-8")
    for provider in spec["providers"]:
        model = provider["model"]
        assert model in text, f"SPEC.md never names {model}"
    tokens = tuple(TOKEN_RE.findall(text))
    assert set(tokens) == set(mh.ROSTER), f"unexpected provider-shaped tokens: {tokens}"


def test_spec_json_is_the_only_roster_source():
    raw = (HERE / "canary_spec.json").read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert tuple(p["model"] for p in parsed["providers"]) == mh.ROSTER
    # a third provider cannot hide in the file as a bare token
    assert len(re.findall(r'"model"\s*:', raw)) == 2


def test_fixture_shot_matches_canary_style():
    shot = mh.load_fixture("shot_painful_moment.json")
    spec = _spec()
    assert shot["style"] == spec["shots"]["style"]
    assert shot["lip_sync_flag"] == "pain_peak"
    assert shot["keyframe"] and shot["isolated_line"]


def test_validate_spec_refuses_a_reversed_roster():
    spec = _spec()
    spec["providers"] = list(reversed(spec["providers"]))
    for p, rank in zip(spec["providers"], (1, 2)):
        p["rank"] = rank
    spec["providers"][0]["role"], spec["providers"][1]["role"] = "primary", "backup"
    try:
        mh.validate_spec(spec)
    except mh.SpecError:
        return
    raise AssertionError("a reversed roster was accepted")


def test_validate_spec_refuses_a_third_provider():
    spec = _spec()
    spec["providers"].append(
        {"rank": 3, "role": "tertiary", "model": "extra/model-not-in-roster"}
    )
    try:
        mh.validate_spec(spec)
    except mh.SpecError:
        return
    raise AssertionError("a third provider was accepted")


def test_validate_spec_refuses_out_of_range_shot_count():
    spec = _spec()
    for bad in (0, 3):
        spec["shots"]["count"] = bad
        try:
            mh.validate_spec(spec)
        except mh.SpecError:
            continue
        raise AssertionError(f"shots.count={bad} was accepted")
    spec["shots"]["count"] = 2


def test_validate_spec_refuses_a_spend_allowed_spec():
    spec = _spec()
    spec["spend"]["allowed"] = True
    try:
        mh.validate_spec(spec)
    except mh.SpecError:
        return
    raise AssertionError("spend.allowed=true was accepted")


def test_attempt_order_requires_primary_before_backup():
    mh.verify_attempt_order([mh.ROSTER[0]])
    mh.verify_attempt_order([mh.ROSTER[0], mh.ROSTER[1]])
    for bad in ([mh.ROSTER[1]], [mh.ROSTER[1], mh.ROSTER[0]], []):
        try:
            mh.verify_attempt_order(bad)
        except mh.SpecError:
            continue
        raise AssertionError(f"attempt order {bad!r} was accepted")


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except Exception as exc:  # noqa: BLE001 - report then fail
                failures.append(name)
                print(f"FAIL {name}: {exc}")
    print(f"total={len([n for n in globals() if n.startswith('test_')])} failed={len(failures)}")
    raise SystemExit(1 if failures else 0)

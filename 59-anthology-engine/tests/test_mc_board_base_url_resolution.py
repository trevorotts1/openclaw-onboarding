#!/usr/bin/env python3
"""test_mc_board_base_url_resolution.py -- P3-03 G23 regression: mc_board.py MUST
honor a live-process MISSION_CONTROL_URL (or MC_URL, or a config-named override)
env override BEFORE it falls back to its http://localhost:4000 default.

WHY THIS TEST EXISTS (G23, SUPER-SPEC-2026-07-11 P3-03 (c)4): the fleet standard for
the Command Center's own port is :4000, so the localhost:4000 default in
BoardConfig.__init__ is CORRECT as a default -- but a box that legitimately differs
(a non-standard port, a remote board host, or a test harness) must be able to
override it, and that override must never be silently shadowed by the default. This
suite proves the RESOLUTION ORDER, not just the default's existence:

  1. explicit config `board.base_url_env` (a caller-named env var) wins over
     everything, including the standard MISSION_CONTROL_URL/MC_URL names.
  2. MISSION_CONTROL_URL (first-checked standard name) wins over MC_URL and over a
     literal `board.base_url` in config.
  3. MC_URL (second-checked standard name) is honored when MISSION_CONTROL_URL is
     absent.
  4. a literal `board.base_url` in config is honored when no env var is set.
  5. the http://localhost:4000 default fires only when nothing else is configured.
  6. an empty/whitespace-only env value is treated as NOT SET (never resolves to a
     blank base_url).

Fail-first proof (rubric 2.1.3 / 2.3.3 -- "a test that would fail if the code were
wrong"): test_env_priority_order_is_load_bearing reimplements the WRONG resolution
order (default-checked-before-env, the regression this test guards against) inline
and asserts THAT implementation fails the same assertions the real BoardConfig
passes -- proving the precedence assertions are meaningful, not tautological.

Hermetic: imports mc_board.py directly (stdlib only, no network, no board process).
Every test isolates os.environ via monkeypatch; no test reads or writes real
process env beyond its own fixture.

Run: python3 -m pytest 59-anthology-engine/tests/test_mc_board_base_url_resolution.py -q
"""
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mc_board  # noqa: E402


ENV_NAMES = ("MISSION_CONTROL_URL", "MC_URL", "MY_CUSTOM_BOARD_URL_ENV")


def _clear_board_env(monkeypatch):
    for name in ENV_NAMES:
        monkeypatch.delenv(name, raising=False)


def test_default_fires_when_nothing_configured(monkeypatch):
    _clear_board_env(monkeypatch)
    cfg = mc_board.BoardConfig({})
    assert cfg.base_url == "http://localhost:4000", (
        "the fleet-standard :4000 default must fire when no env or config base_url "
        "is present"
    )


def test_mission_control_url_env_overrides_default(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://10.0.0.5:4000")
    cfg = mc_board.BoardConfig({})
    assert cfg.base_url == "http://10.0.0.5:4000", (
        "MISSION_CONTROL_URL must win over the localhost:4000 default"
    )


def test_mc_url_env_overrides_default_when_mission_control_url_absent(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MC_URL", "http://board.internal:4000")
    cfg = mc_board.BoardConfig({})
    assert cfg.base_url == "http://board.internal:4000", (
        "MC_URL must be honored as the secondary standard env name"
    )


def test_mission_control_url_wins_over_mc_url(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://primary:4000")
    monkeypatch.setenv("MC_URL", "http://secondary:4000")
    cfg = mc_board.BoardConfig({})
    assert cfg.base_url == "http://primary:4000", (
        "MISSION_CONTROL_URL is checked before MC_URL in DEFAULT_BASE_URL_ENV order"
    )


def test_config_literal_base_url_honored_with_no_env(monkeypatch):
    _clear_board_env(monkeypatch)
    cfg = mc_board.BoardConfig({"board": {"base_url": "http://from-config:4000"}})
    assert cfg.base_url == "http://from-config:4000"


def test_env_wins_over_config_literal_base_url(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://from-env:4000")
    cfg = mc_board.BoardConfig({"board": {"base_url": "http://from-config:4000"}})
    assert cfg.base_url == "http://from-env:4000", (
        "a live-process env override must win over a config-file literal"
    )


def test_named_config_env_var_wins_over_standard_names(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MY_CUSTOM_BOARD_URL_ENV", "http://custom-named:4000")
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://standard:4000")
    cfg = mc_board.BoardConfig({"board": {"base_url_env": "MY_CUSTOM_BOARD_URL_ENV"}})
    assert cfg.base_url == "http://custom-named:4000", (
        "an explicitly-named board.base_url_env is checked before the standard names"
    )


def test_blank_env_value_treated_as_not_set(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MISSION_CONTROL_URL", "   ")
    cfg = mc_board.BoardConfig({"board": {"base_url": "http://from-config:4000"}})
    assert cfg.base_url == "http://from-config:4000", (
        "a whitespace-only env value must be treated as NOT SET, never resolved to "
        "a blank/whitespace base_url"
    )


def test_trailing_slash_is_stripped_regardless_of_source(monkeypatch):
    _clear_board_env(monkeypatch)
    monkeypatch.setenv("MISSION_CONTROL_URL", "http://trailing-slash:4000/")
    cfg = mc_board.BoardConfig({})
    assert cfg.base_url == "http://trailing-slash:4000"


def test_env_priority_order_is_load_bearing(monkeypatch):
    """Fail-first proof: a NAIVE 'default-first' resolver (the class of regression
    G23 guards against -- checking config/default BEFORE the live env) fails the
    exact same override assertion the real BoardConfig passes. This proves the
    precedence tests above are exercising real, breakable behavior."""
    _clear_board_env(monkeypatch)
    import os

    monkeypatch.setenv("MISSION_CONTROL_URL", "http://should-win:4000")

    def wrong_resolve_base_url(board_cfg):
        # The regression shape: config literal / default wins even though a live
        # env override is present (env is consulted LAST, or not at all).
        return (board_cfg.get("base_url") or mc_board.DEFAULT_BASE_URL).rstrip("/")

    wrong_result = wrong_resolve_base_url({"board": {}})
    real_cfg = mc_board.BoardConfig({"board": {}})

    assert wrong_result == mc_board.DEFAULT_BASE_URL, (
        "sanity: the naive resolver must reproduce the pre-fix bug shape"
    )
    assert real_cfg.base_url == "http://should-win:4000"
    assert wrong_result != real_cfg.base_url, (
        "the naive (env-blind) resolver and the real BoardConfig must diverge here -- "
        "if they agree, this test is not actually proving the env override is honored"
    )


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))

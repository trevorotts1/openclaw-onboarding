#!/usr/bin/env python3
"""MOCK-only unit tests — capability_probe (Skill 06 adaptive lane probe).

These tests are MOCK-ONLY. There is NO live OpenClaw, NO agent-browser binary
required, NO network, NO real secrets.  All runners are in-process fakes that
return synthetic CompletedProcess-like objects; all env is a synthetic dict.

Coverage per the P0-6 + 9.7-4 task contract:
  (a) lane selection priority per the plan 9.6 REVISED table —
        * agent-browser-only box          -> selectedLane "agent_browser"
        * OC 2.0+ + plugin + playwright   -> managed lane available/eligible
        * nothing present                 -> selectedLane null + no-browser-lane
                                             blocker (fail-closed)
  (b) iframeDrag.available False when Playwright missing (fail-closed), True
      only on the AB+Playwright hybrid
  (c) secrets booleans correct from a fake env; NO secret VALUE ever appears
      in the serialized output JSON
  (d) `--selftest` subprocess exits 0 (offline, timeout 120)

Run:
    python3 -m pytest tests/test_capability_probe.py -v
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import capability_probe as cp

NOW = "2026-09-07T00:00:00Z"


# ── fake runner plumbing ──────────────────────────────────────────────────────

class _CP:
    """CompletedProcess stand-in (subprocess.run signature compatible)."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_runner(**scripted):
    """Build a runner from a {command-substring: _CP} map. Unmatched commands
    fail with rc=1 / empty output (binary absent). Keys are matched in the
    order given (dict ordering), substring against the joined argv."""
    rules = list(scripted.items())

    def runner(cmd, capture_output=False, text=False, timeout=None):
        joined = " ".join(cmd)
        for key, result in rules:
            if key in joined:
                return result
        return _CP(returncode=1, stdout="", stderr="")

    return runner


R_OK = _CP(returncode=0, stdout="", stderr="")


# Lane fixtures ---------------------------------------------------------------

def runner_ab_only():
    """agent-browser on PATH at 0.27.0; no OpenClaw, no Playwright."""
    return _fake_runner(
        **{
            "command -v": _CP(returncode=0, stdout="/usr/local/bin/agent-browser\n"),
            "--version": _CP(returncode=0, stdout="agent-browser 0.27.0\n"),
        }
    )


def runner_ab_plus_playwright():
    """agent-browser + importable Playwright (the 1b hybrid)."""
    return _fake_runner(
        **{
            "command -v": _CP(returncode=0, stdout="/usr/local/bin/agent-browser\n"),
            "--version": _CP(returncode=0, stdout="agent-browser 0.27.0\n"),
            "import playwright": _CP(returncode=0, stdout=""),
        }
    )


def runner_oc2_managed():
    """OpenClaw 2026.9.2 + browser plugin enabled + browser CLI works +
    Playwright importable; NO agent-browser."""
    return _fake_runner(
        **{
            "openclaw --version": _CP(returncode=0, stdout="OpenClaw 2026.9.2 (3928bad)\n"),
            "openclaw plugins list": _CP(
                returncode=0,
                stdout="@openclaw/browser-plugin 2.0.1 enabled\ncua-computer 0.21.0 enabled\n",
            ),
            "--browser-profile": _CP(returncode=0, stdout="profile openclaw ready\n"),
            "import playwright": _CP(returncode=0, stdout=""),
        }
    )


def runner_playwright_only():
    """Playwright importable; no agent-browser, no OpenClaw CLI."""
    return _fake_runner(
        **{
            "import playwright": _CP(returncode=0, stdout=""),
        }
    )


def runner_nothing():
    """Bare box: every command fails (binary absent)."""
    return _fake_runner(**{"__never__": _CP(returncode=1)})


# ── (a) lane selection priority per plan 9.6 REVISED table ────────────────────

@pytest.mark.parametrize("runner_factory,expected_lane", [
    (runner_ab_only, "agent_browser"),
    (runner_ab_plus_playwright, "agent_browser"),           # 1b = same lane
    (runner_oc2_managed, "openclaw_managed_browser"),
    (runner_playwright_only, "playwright_direct"),
    (runner_nothing, None),
])
def test_lane_selection_priority_9_6(runner_factory, expected_lane):
    res = cp.run_probe(runner=runner_factory(), env={}, now=NOW)
    assert res["selectedLane"] == expected_lane


def test_agent_browser_only_box_is_qc_passable():
    """Plan 2.2: agent-browser works -> full Skill 6 capability; no blockers,
    lane 1 selected, version reported."""
    res = cp.run_probe(runner=runner_ab_only(), env={}, now=NOW)
    assert res["selectedLane"] == "agent_browser"
    assert res["blockers"] == []
    assert res["lanes"]["agent_browser"]["available"] is True
    assert res["lanes"]["agent_browser"]["version"] == "0.27.0"
    assert res["lanes"]["agent_browser"]["path"] == "/usr/local/bin/agent-browser"
    # lane 2 must NOT be selected without OC 2.0 floor + plugin + cli
    assert res["fallbackChain"][0] == "agent_browser"
    assert "openclaw_managed_browser" not in res["fallbackChain"]
    assert res["fallbackChain"][-1] == "cua_last_resort"


def test_oc_2x_plugin_playwright_managed_lane_available():
    res = cp.run_probe(runner=runner_oc2_managed(), env={}, now=NOW)
    lane = res["lanes"]["openclaw_managed_browser"]
    assert lane["pluginEnabled"] is True
    assert lane["cliWorks"] is True
    assert lane["playwrightAvailable"] is True
    assert lane["profile"] == "openclaw"
    assert res["openclaw"]["is2xOrNewer"] is True
    assert res["openclaw"]["semver"] == [2026, 9, 2]
    # agent-browser absent -> lane 2 selected
    assert res["selectedLane"] == "openclaw_managed_browser"


def test_oc_pre_2x_managed_lane_not_eligible():
    """Plan 2.2: OpenClaw < 2026.8.1 must NOT get the managed lane even with
    plugin + cli; falls to playwright when importable, else fail-closed."""
    base = {
        "openclaw --version": _CP(returncode=0, stdout="OpenClaw 2026.7.9 (abc)\n"),
        "openclaw plugins list": _CP(
            returncode=0, stdout="@openclaw/browser-plugin 1.9.0 enabled\n"),
        "--browser-profile": R_OK,
        "import playwright": _CP(returncode=0, stdout=""),
    }
    res = cp.run_probe(runner=_fake_runner(**base), env={}, now=NOW)
    assert res["openclaw"]["is2xOrNewer"] is False
    assert res["selectedLane"] == "playwright_direct"
    assert any("2026.8.1" in w for w in res["warnings"])


def test_nothing_present_fails_closed_with_blocker():
    res = cp.run_probe(runner=runner_nothing(), env={}, now=NOW)
    assert res["selectedLane"] is None
    assert "no-browser-lane" in res["blockers"]


def test_existing_session_never_default_without_opt_in():
    """Plan 2.2: existing_session NEVER a silent default; only the explicit
    GHL_SKILL6_ALLOW_EXISTING_SESSION=1 opt-in can select lane 4."""
    # bare box + no opt-in -> still null (lane 4 gated)
    res = cp.run_probe(runner=runner_nothing(), env={}, now=NOW)
    assert res["selectedLane"] is None
    # bare box + opt-in -> lane 4 selected
    res = cp.run_probe(runner=runner_nothing(),
                       env={"GHL_SKILL6_ALLOW_EXISTING_SESSION": "1"}, now=NOW)
    assert res["selectedLane"] == "existing_session"
    # even WITH opt-in, CDP lanes still win the priority table
    res = cp.run_probe(runner=runner_ab_only(),
                       env={"GHL_SKILL6_ALLOW_EXISTING_SESSION": "1"}, now=NOW)
    assert res["selectedLane"] == "agent_browser"


# ── (b) iframeDrag fail-closed (plan 9.2 / 9.7-4) ─────────────────────────────

@pytest.mark.parametrize("runner_factory,ab,pw,expected", [
    (runner_ab_only, True, False, False),          # AB only -> drag STOP
    (runner_ab_plus_playwright, True, True, True),  # 1b hybrid -> drag OK
    (runner_nothing, False, False, False),
])
def test_iframe_drag_available_hybrid_only(runner_factory, ab, pw, expected):
    res = cp.run_probe(runner=runner_factory(), env={}, now=NOW)
    assert res["lanes"]["agent_browser"]["available"] is ab
    assert res["lanes"]["playwright_direct"]["available"] is pw
    assert res["iframeDrag"]["available"] is expected
    assert res["iframeDrag"]["requires"] == "playwright+cdp"
    assert res["iframeDrag"]["degradedWithout"] == "STOP on cross-origin tile/drag"


def test_iframe_drag_warning_when_ab_without_playwright():
    res = cp.run_probe(runner=runner_ab_only(), env={}, now=NOW)
    assert any("cross-origin" in w for w in res["warnings"])


# ── (c) secrets: booleans from env, values NEVER in output ────────────────────

_SECRET_ENVS = {
    "all-present": {
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "SEKRET-TOKEN",
        "GHL_API_KEY": "SEKRET-PIT",
        "GOHIGHLEVEL_LOCATION_ID": "SEKRET-LOC",
        "KIE_API_KEY": "SEKRET-KIE",
        "expected": {"firebaseRefreshToken": True, "locationPit": True,
                     "locationId": True, "kieApiKey": True},
    },
    "canonical-aliases": {
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "v1",
        "GOHIGHLEVEL_API_KEY": "v2",
        "GHL_LOCATION_ID": "v3",
        "expected": {"firebaseRefreshToken": True, "locationPit": True,
                     "locationId": True, "kieApiKey": False},
    },
    "secondary-aliases": {
        "GHL_FIREBASE_REFRESH_TOKEN": "v1",
        "GOHIGHLEVEL_LOCATION_PIT": "v4",
        "GHL_LOCATION_ID": "v5",
        "expected": {"firebaseRefreshToken": True, "locationPit": True,
                     "locationId": True, "kieApiKey": False},
    },
    "empty-values-are-false": {
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "",
        "GHL_API_KEY": "   ",
        "expected": {"firebaseRefreshToken": False, "locationPit": False,
                     "locationId": False, "kieApiKey": False},
    },
    "none-present": {
        "expected": {"firebaseRefreshToken": False, "locationPit": False,
                     "locationId": False, "kieApiKey": False},
    },
}


@pytest.mark.parametrize("case", sorted(_SECRET_ENVS.keys()))
def test_secrets_booleans_from_env(case):
    spec = _SECRET_ENVS[case]
    env = {k: v for k, v in spec.items() if k != "expected"}
    res = cp.run_probe(runner=runner_nothing(), env=env, now=NOW)
    assert res["secrets"] == spec["expected"]


def test_no_secret_values_in_output_json():
    secret_env = {
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "SUPERSEKRET-TOKEN-123",
        "GHL_API_KEY": "SUPERSEKRET-PIT-456",
        "GOHIGHLEVEL_LOCATION_ID": "SUPERSEKRET-LOC-789",
        "KIE_API_KEY": "SUPERSEKRET-KIE-000",
    }
    res = cp.run_probe(runner=runner_nothing(), env=secret_env, now=NOW)
    blob = json.dumps(res)
    for value in secret_env.values():
        assert value not in blob
    # also: the keys must be plain booleans
    assert all(isinstance(v, bool) for v in res["secrets"].values())


# ── output contract shape (plan 2.1 fields) ───────────────────────────────────

EXPECTED_TOP_KEYS = {
    "probedAt", "platform", "openclaw", "lanes", "secrets", "selectedLane",
    "fallbackChain", "optimizations", "iframeDrag", "blockers", "warnings",
}


def test_output_has_exact_plan_2_1_top_level_fields():
    res = cp.run_probe(runner=runner_ab_only(), env={}, now=NOW)
    assert set(res.keys()) == EXPECTED_TOP_KEYS
    assert set(res["lanes"].keys()) == {
        "agent_browser", "openclaw_managed_browser", "existing_session",
        "playwright_direct", "cua", "computer_peekaboo"}
    assert set(res["optimizations"].items()) == {
        ("preferHeadless", True), ("maxParallelTabs", 1),
        ("snapshotMode", "efficient"), ("iframeStrategy", "frame_scoped_snapshot")}


@pytest.mark.parametrize("version,expected", [
    ("OpenClaw 2026.9.2 (3928bad)", True),
    ("2026.8.1", True),
    ("2026.8.0", False),
    ("2026.7.9", False),
    ("2.0.0", False),           # literal 2.x tag is below the 2026.8.1 floor
    ("garbage", False),
])
def test_is_2x_or_newer_floor_2026_8_1(version, expected):
    semver = cp._semver(version)
    assert cp._is_2x_or_newer(cp._semver(version)) is expected
    if version == "garbage":
        assert semver is None


def test_every_probe_failure_is_non_fatal():
    """A runner that raises instead of returning must still yield a full doc
    with warnings, never an exception out of run_probe."""
    def exploding_runner(cmd, capture_output=False, text=False, timeout=None):
        raise RuntimeError("boom")

    res = cp.run_probe(runner=exploding_runner, env={}, now=NOW)
    assert res["selectedLane"] is None
    assert "no-browser-lane" in res["blockers"]
    assert res["warnings"], "expected warnings from the failed probes"


def exploding_runner_factory():
    def runner(cmd, capture_output=False, text=False, timeout=None):
        raise RuntimeError("boom")
    return runner


# ── (d) --selftest subprocess convention ──────────────────────────────────────

def test_selftest_subprocess_exit_zero():
    cp_path = os.path.join(_TOOLS_DIR, "capability_probe.py")
    proc = subprocess.run([sys.executable, cp_path, "--selftest"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "PASS" in proc.stdout


def test_cli_json_flag_stdout_only_no_file(tmp_path):
    """--json must print valid JSON and not write the default file."""
    cp_path = os.path.join(_TOOLS_DIR, "capability_probe.py")
    proc = subprocess.run([sys.executable, cp_path, "--json"],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert "selectedLane" in doc
    default_out = os.path.normpath(os.path.join(_TOOLS_DIR, "..", "working",
                                                "skill6-capability.json"))
    assert not os.path.exists(default_out)


def test_cli_out_writes_working_json(tmp_path):
    cp_path = os.path.join(_TOOLS_DIR, "capability_probe.py")
    out = tmp_path / "cap.json"
    proc = subprocess.run([sys.executable, cp_path, "--out", str(out)],
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(out.read_text())
    assert "selectedLane" in doc
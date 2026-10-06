# -*- coding: utf-8 -*-
"""Tests for tools/cua_last_resort_adapter.sh (P1-13 — CUA last-resort lane contract).

The adapter is a CONTRACT wrapper, not a driver: it gates and documents the
CUA/computer lane (plan 9.6 lane 5; 9.1 — absent from Skill 6 paths today).
It must never launch a browser and must never write a waiver receipt on any
refusal. All tests run offline against synthetic capability JSON files in
tmp_path via the CUA_CAPABILITY_PATH / CUA_WAIVER_RECEIPT_PATH overrides —
the real working/skill6-capability.json and working/cua-waiver-receipt.json
are never touched (this box legitimately reports cua available; tests must
not depend on live state).

Coverage:
  A. bash -n syntax clean.
  B. Selftest subprocess exit 0 (house convention, timeout=120).
  C. Gate matrix via check verb:
     C1 missing capability file  -> exit 2 + 'cua-unavailable' stderr token.
     C2 unavailable provider (none / unknown) -> exit 2.
     C3 ambiguous (unknown + plugin enabled)  -> exit 3 + 'cua-ambiguous' token.
     C4 available (provider cua, peekaboo)    -> exit 0 + 'cua available' stdout.
  D. request verb without GHL_SKILL6_ALLOW_CUA=1 -> exit 75 + NO receipt written.
  E. request verb with GHL_SKILL6_ALLOW_CUA=1 -> receipt written, valid JSON,
     contract fields {requestedAt, reason, providerSelected, lane,
     requiresVisionModel} present with lane='cua_last_resort' and
     requiresVisionModel is True.
  F. request verb on failing gate even WITH opt-in -> exit 2 + no receipt.
  G. note verb prints doctrine tokens (NEVER the default, VISION model,
     ephemeral, does NOT attach).
  H. No browser-launch tokens in executable (non-comment) script code.
"""

import json
import os
import re
import subprocess
import sys

import pytest

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
_SCRIPT = os.path.join(_TOOLS_DIR, "cua_last_resort_adapter.sh")


def _run_script(args, env=None, timeout=120):
    full_env = dict(os.environ)
    if env:
        full_env.update(env)
    return subprocess.run(
        ["bash", _SCRIPT] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=full_env,
    )


def _mkcap(path, plugin=True, driver=True, provider="cua"):
    """Synthetic capability receipt matching capability_probe.py _probe_cua schema."""
    receipt = {
        "probedAt": "2026-09-07T00:00:00Z",
        "platform": "mac",
        "lanes": {
            "cua": {
                "pluginEnabled": bool(plugin),
                "appPresent": bool(plugin),
                "driverPresent": bool(driver),
                "providerSelected": provider,
            }
        },
        "selectedLane": "agent_browser",
        "blockers": [],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2)
    return path


def _env_overrides(tmp_path):
    return {
        "CUA_CAPABILITY_PATH": os.path.join(str(tmp_path), "cap.json"),
        "CUA_WAIVER_RECEIPT_PATH": os.path.join(str(tmp_path), "waiver.json"),
    }


def _receipt_path(tmp_path):
    return os.path.join(str(tmp_path), "waiver.json")


# ---------------------------------------------------------------- A: syntax


def test_bash_n_syntax_clean():
    proc = subprocess.run(["bash", "-n", _SCRIPT], capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, f"bash -n failed: {proc.stderr}"


# ------------------------------------------------------------- B: selftest


def test_selftest_exit_zero_timeout_120():
    proc = _run_script(["--selftest"])
    assert proc.returncode == 0, f"selftest failed rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "PASS" in proc.stdout


# --------------------------------------------------------- C: gate matrix


@pytest.mark.parametrize(
    "plugin,driver,provider,expected_rc,expect_token",
    [
        # C2: unavailable provider (none) -> 2
        (False, False, "none", 2, "cua-unavailable"),
        # C2: plugin off entirely -> 2
        (False, True, "peekaboo", 2, "cua-unavailable"),
        # C2: plugin on but driver missing -> 2 (provider 'unknown' with plugin on
        # is C3, so use explicit none-shaped schema: driver false + provider cua
        # is unreachable in the real probe, but the gate treats it unavailable)
        (True, False, "cua", 2, "cua-unavailable"),
    ],
)
def test_gate_unavailable(tmp_path, plugin, driver, provider, expected_rc, expect_token):
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=plugin, driver=driver, provider=provider)
    proc = _run_script(["check"], env=overrides)
    assert proc.returncode == expected_rc, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert expect_token in proc.stderr


def test_gate_missing_capability_file_exit_2(tmp_path):
    # C1: point at a path that does not exist
    overrides = _env_overrides(tmp_path)
    proc = _run_script(["check"], env=overrides)
    assert proc.returncode == 2
    assert "cua-unavailable" in proc.stderr


def test_gate_ambiguous_exit_3(tmp_path):
    # C3: plugin enabled but providerSelected unknown -> 3
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=True, driver=False, provider="unknown")
    proc = _run_script(["check"], env=overrides)
    assert proc.returncode == 3, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "cua-ambiguous" in proc.stderr


@pytest.mark.parametrize("provider", ["cua", "peekaboo"])  # C4
def test_gate_available_exit_0(tmp_path, provider):
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=True, driver=True, provider=provider)
    proc = _run_script(["check"], env=overrides)
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "cua available" in proc.stdout


# --------------------------------------------- D: request without opt-in env


def test_request_without_optin_refused_75_no_receipt(tmp_path):
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=True, driver=True, provider="cua")
    # GHL_SKILL6_ALLOW_CUA deliberately absent from env
    proc = _run_script(["request", "test reason"], env=overrides)
    assert proc.returncode == 75, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "GHL_SKILL6_ALLOW_CUA" in proc.stderr
    assert not os.path.exists(_receipt_path(tmp_path)), "refusal must NOT write a waiver receipt"


# ------------------------------------------------ E: request with opt-in env


def test_request_with_optin_writes_valid_receipt(tmp_path):
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=True, driver=True, provider="cua")
    env = dict(overrides)
    env["GHL_SKILL6_ALLOW_CUA"] = "1"
    proc = _run_script(["request", "operator approved lane-5 trial"], env=env)
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert "CUA REQUESTED" in proc.stdout
    receipt_file = _receipt_path(tmp_path)
    assert os.path.exists(receipt_file), "gated request must write the waiver receipt"
    with open(receipt_file, "r", encoding="utf-8") as fh:
        receipt = json.load(fh)  # raises if not valid JSON
    for field in ("requestedAt", "reason", "providerSelected", "lane", "requiresVisionModel"):
        assert field in receipt, f"receipt missing contract field {field}"
    assert receipt["lane"] == "cua_last_resort"
    assert receipt["requiresVisionModel"] is True
    assert receipt["providerSelected"] == "cua"
    assert receipt["reason"] == "operator approved lane-5 trial"


# --------------------------------------- F: request with opt-in but bad gate


def test_request_with_optin_but_failing_gate_no_receipt(tmp_path):
    overrides = _env_overrides(tmp_path)
    _mkcap(overrides["CUA_CAPABILITY_PATH"], plugin=False, driver=False, provider="none")
    env = dict(overrides)
    env["GHL_SKILL6_ALLOW_CUA"] = "1"
    proc = _run_script(["request", "should not pass the gate"], env=env)
    assert proc.returncode == 2, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    assert not os.path.exists(_receipt_path(tmp_path)), "failed gate must NOT write a receipt"


# ------------------------------------------------------------- G: doctrine


def test_note_prints_doctrine_tokens():
    proc = _run_script(["note"])
    assert proc.returncode == 0, f"rc={proc.returncode}\n{proc.stdout}\n{proc.stderr}"
    blob = proc.stdout + proc.stderr
    for token in ("NEVER the default", "VISION model", "ephemeral", "does NOT attach"):
        assert token in blob, f"doctrine token missing: {token}"


# ----------------------------------------------- H: no browser tokens in code


def test_no_browser_launch_tokens_in_executable_code():
    with open(_SCRIPT, "r", encoding="utf-8") as fh:
        lines = fh.read().splitlines()
    # Strip comment lines, the self-declaring token-list loop itself, and heredoc
    # bodies (printed doctrine TEXT, not executable code — doctrine must be free
    # to NAME the CDP lanes it claims to have exhausted).
    in_heredoc = False
    kept = []
    for ln in lines:
        stripped = ln.strip()
        if not in_heredoc and "<<'CUA_DOCTRINE'" in ln:
            in_heredoc = True
            continue
        if in_heredoc:
            if stripped == "CUA_DOCTRINE":
                in_heredoc = False
            continue
        if stripped.startswith("#") or "for token in" in ln:
            continue
        kept.append(ln)
    code = "\n".join(kept)
    for token in ("agent-browser", "connect_over_cdp", "connect-over-cdp", "playwright"):
        assert token not in code, f"adapter executable code mentions browser lane token: {token}"
#!/usr/bin/env python3
"""Hermetic subprocess tests - scripts/check-openclaw-extension-version.sh.

S06-03 T-B: covers the lane-scoped preflight's human wording, the --json
contract (exactly 7 keys; a computed verdict - current, behind, missing,
unknown-currency - is exit 0; cannot-run is exit 2), and the cannot-run
boundaries. Every case builds its subprocess env FROM SCRATCH ({PATH,
HOME=<tmp>, OPENCLAW_HOME=<tmp>, plus per-case knobs}) so the real box's
Chrome / OpenClaw state can never leak in. The fake-chrome fixture
carries the extension at v2.3.0; the bundled manifest is written by the
test when a case needs one. No network; every subprocess gets
timeout=120 (house rule).

Run:
    python3 -m pytest tests/test_check_openclaw_extension_version.py -v
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
_SKILL_DIR = os.path.normpath(os.path.join(_HERE, ".."))
_SCRIPT = os.path.join(_SKILL_DIR, "scripts",
                       "check-openclaw-extension-version.sh")
_FIXTURE_CHROME = os.path.join(_HERE, "fixtures", "fake-chrome")
_STORE_URL = ("https://chromewebstore.google.com/detail/openclaw/"
              "kcdjddhmeafeomebliikmbpblkmkfoig")
_TIMEOUT = 120
_BASH = shutil.which("bash") or "/bin/bash"
_JSON_KEYS = {"installed", "version", "expectedVersion", "expectedSource",
              "current", "lane", "laneAvailable"}


def _base_env(tmp_path):
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "OPENCLAW_HOME": str(tmp_path / "openclaw"),
    }


def _run(env, *args):
    return subprocess.run(
        [_BASH, _SCRIPT] + list(args),
        env=env, capture_output=True, text=True, timeout=_TIMEOUT)


def _write_bundled_manifest(tmp_path, version="2.3.0"):
    ext_dir = tmp_path / "openclaw" / "browser" / "chrome-extension"
    ext_dir.mkdir(parents=True, exist_ok=True)
    (ext_dir / "manifest.json").write_text(
        json.dumps({"version": version}), encoding="utf-8")


# -- B1: human mode, installed and current --------------------------------

def test_b1_human_current(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "2.3.0"
    proc = _run(env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    first = proc.stdout.splitlines()[0]
    assert first == ("OK: OpenClaw Chrome extension v2.3.0 is installed "
                     "and current (expected v2.3.0).")


# -- B2: human mode, behind -> LANE 1 UNAVAILABLE, exit 2 ------------------

def test_b2_human_behind(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "9.9.9"
    proc = _run(env)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "LANE 1 UNAVAILABLE" in proc.stdout
    assert _STORE_URL in proc.stdout
    assert "no install run can start" not in proc.stdout
    assert not any(line.startswith("STOP:")
                   for line in proc.stdout.splitlines())


# -- B3: human mode, not installed -> LANE 1 UNAVAILABLE, exit 2 -----------

def test_b3_human_missing(tmp_path):
    empty = tmp_path / "empty-roots"
    empty.mkdir()
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = str(empty)
    _write_bundled_manifest(tmp_path)
    proc = _run(env)
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "LANE 1 UNAVAILABLE" in proc.stdout
    assert "NOT installed" in proc.stdout


# -- B4: human mode, currency unknown -> OK with warning, exit 0 -----------

def test_b4_human_unknown_currency(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    # no pin, and OPENCLAW_HOME (from _base_env) carries no bundled manifest
    proc = _run(env)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK (with warning)" in proc.stdout


# -- B5: --json, current ----------------------------------------------------

def test_b5_json_current(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "2.3.0"
    proc = _run(env, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert len(proc.stdout.strip().splitlines()) == 1  # one object only
    obj = json.loads(proc.stdout)
    assert set(obj.keys()) == _JSON_KEYS
    assert obj == {
        "installed": True,
        "version": "2.3.0",
        "expectedVersion": "2.3.0",
        "expectedSource": "operator-pin",
        "current": True,
        "lane": "openclaw-extension",
        "laneAvailable": True,
    }


# -- B6: --json, behind is a verdict (exit 0), not an error -----------------

def test_b6_json_behind(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "9.9.9"
    proc = _run(env, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    obj = json.loads(proc.stdout)
    assert set(obj.keys()) == _JSON_KEYS
    assert obj["installed"] is True
    assert obj["version"] == "2.3.0"
    assert obj["expectedVersion"] == "9.9.9"
    assert obj["current"] is False
    assert obj["laneAvailable"] is False


# -- B7: --json, missing; plus the not-installed + no-expected corner -------

def test_b7_json_missing(tmp_path):
    empty = tmp_path / "empty-roots"
    empty.mkdir()
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = str(empty)
    _write_bundled_manifest(tmp_path)
    proc = _run(env, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    obj = json.loads(proc.stdout)
    assert obj["installed"] is False
    assert obj["version"] is None
    assert obj["expectedVersion"] == "2.3.0"
    assert obj["expectedSource"] == "bundled-manifest"
    assert obj["current"] is False
    assert obj["laneAvailable"] is False


def test_b7_json_missing_no_expected_corner(tmp_path):
    """Not installed AND expectedVersion null: current is False, never
    "unknown" (the governing rule mirrors capability_probe.py). The roots
    dir EXISTS here, so a verdict is computable - unlike B9."""
    empty = tmp_path / "empty-roots"
    empty.mkdir()
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = str(empty)
    # no pin, no bundled manifest under OPENCLAW_HOME
    proc = _run(env, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    obj = json.loads(proc.stdout)
    assert obj["installed"] is False
    assert obj["expectedVersion"] is None
    assert obj["expectedSource"] == "unknown"
    assert obj["current"] is False
    assert obj["laneAvailable"] is False


# -- B8: --json, currency unknown -------------------------------------------

def test_b8_json_unknown_currency(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    proc = _run(env, "--json")
    assert proc.returncode == 0, proc.stdout + proc.stderr
    obj = json.loads(proc.stdout)
    assert obj["installed"] is True
    assert obj["current"] == "unknown"
    assert obj["expectedVersion"] is None
    assert obj["expectedSource"] == "unknown"
    assert obj["laneAvailable"] is True


# -- B9: --json cannot-run - no roots on disk AND no expected source --------

def test_b9_json_cannot_run_no_roots_no_source(tmp_path):
    env = _base_env(tmp_path)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = str(tmp_path / "does-not-exist")
    # HOME / OPENCLAW_HOME point at nonexistent tmp dirs, so the default
    # roots do not exist either, and there is no pin and no manifest.
    proc = _run(env, "--json")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert proc.stdout.strip() == ""  # no JSON object on stdout


# -- B10: --json cannot-run - python3 absent --------------------------------

def test_b10_json_cannot_run_no_python3(tmp_path):
    empty_bin = tmp_path / "empty-bin"
    empty_bin.mkdir()
    env = _base_env(tmp_path)
    env["PATH"] = str(empty_bin)
    env["GHL_SKILL6_CHROME_PROFILE_ROOTS"] = _FIXTURE_CHROME
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "2.3.0"
    proc = _run(env, "--json")
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert "python3" in proc.stderr


# -- B11: QC compatibility is pinned by B1/B2 --------------------------------
# qc-ghl-install-pages.sh calls the script with no args and reads only the
# exit code (warn-only). B1 (current -> 0) and B2 (behind -> 2) pin those
# codes, so the human-mode exit contract QC depends on cannot drift; no
# separate test is needed.

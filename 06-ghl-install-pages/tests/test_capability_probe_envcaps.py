#!/usr/bin/env python3
"""MOCK-only unit tests — capability_probe environment capabilities (S06-02).

Covers the Signature Launch spec 05 section 3 contract added to
capability_probe.py: the top-level `environmentCapabilities` record with
runtime/harness identity, OS/architecture, container detection, REAL
cgroup limit parsing (v2, v1, absent), persistent storage root, client /
location as references + booleans only, per-lane browser availability +
version, the Playwright launch+screenshot proof (launcher injected both
ways, plus the default runner path), the OpenClaw extension record with
honest "unknown" currentness, approved auth methods, declared API
operations, and per-section evidence timestamps.

Like test_capability_probe.py these are MOCK-ONLY: fake runners, synthetic
env dicts, and tmp_path cgroup trees. No live OpenClaw, no network, no
real secrets, and the real Playwright launch is never executed here (the
launcher is injected, or the fake runner answers the proof child).

Run:
    python3 -m pytest tests/test_capability_probe_envcaps.py -v
"""
from __future__ import annotations

import json
import os
import sys

_TOOLS_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "tools"))
if _TOOLS_DIR not in sys.path:
    sys.path.insert(0, _TOOLS_DIR)

import pytest

import capability_probe as cp

NOW = "2026-10-15T00:00:00Z"

FIXTURE_CHROME_ROOT = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "fixtures", "fake-chrome")


class _CP:
    """CompletedProcess stand-in (subprocess.run signature compatible)."""

    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _fake_runner(**scripted):
    rules = list(scripted.items())

    def runner(cmd, capture_output=False, text=False, timeout=None):
        joined = " ".join(cmd)
        for key, result in rules:
            if key in joined:
                return result
        return _CP(returncode=1, stdout="", stderr="")

    return runner


def runner_nothing():
    return _fake_runner(**{"__never__": _CP(returncode=1)})


def _proof_ok():
    return {"attempted": True, "launched": True, "screenshotTaken": True,
            "errorClass": None}


def _proof_failed():
    return {"attempted": True, "launched": False, "screenshotTaken": False,
            "errorClass": "browser-binary-missing"}


# ── cgroup limit parsing ──────────────────────────────────────────────────────

def _write(root, relpath, text):
    path = os.path.join(str(root), relpath)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text)


def test_cgroup_v2_limits_parsed(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "sys/fs/cgroup/cgroup.controllers", "cpuset cpu io memory\n")
    _write(root, "sys/fs/cgroup/memory.max", "1073741824\n")
    _write(root, "sys/fs/cgroup/cpu.max", "200000 100000\n")
    limits = cp._parse_cgroup_limits(sys_root=str(root))
    assert limits["source"] == "cgroup-v2"
    assert limits["memoryLimitBytes"] == 1073741824
    assert limits["cpuLimitCores"] == 2.0


def test_cgroup_v2_max_means_unbounded_or_unknown(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "sys/fs/cgroup/memory.max", "max\n")
    _write(root, "sys/fs/cgroup/cpu.max", "max 100000\n")
    limits = cp._parse_cgroup_limits(sys_root=str(root))
    assert limits["source"] == "cgroup-v2"
    assert limits["memoryLimitBytes"] == cp.UNBOUNDED_OR_UNKNOWN
    assert limits["cpuLimitCores"] == cp.UNBOUNDED_OR_UNKNOWN


def test_cgroup_v1_limits_parsed(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "sys/fs/cgroup/memory/memory.limit_in_bytes", "536870912\n")
    _write(root, "sys/fs/cgroup/cpu/cpu.cfs_quota_us", "50000\n")
    _write(root, "sys/fs/cgroup/cpu/cpu.cfs_period_us", "100000\n")
    limits = cp._parse_cgroup_limits(sys_root=str(root))
    assert limits["source"] == "cgroup-v1"
    assert limits["memoryLimitBytes"] == 536870912
    assert limits["cpuLimitCores"] == 0.5


def test_cgroup_v1_unlimited_sentinels(tmp_path):
    root = tmp_path / "sysroot"
    # kernel "no limit" sentinels: near-LONG_MAX memory, quota -1
    _write(root, "sys/fs/cgroup/memory/memory.limit_in_bytes",
           "9223372036854771712\n")
    _write(root, "sys/fs/cgroup/cpu/cpu.cfs_quota_us", "-1\n")
    _write(root, "sys/fs/cgroup/cpu/cpu.cfs_period_us", "100000\n")
    limits = cp._parse_cgroup_limits(sys_root=str(root))
    assert limits["source"] == "cgroup-v1"
    assert limits["memoryLimitBytes"] == cp.UNBOUNDED_OR_UNKNOWN
    assert limits["cpuLimitCores"] == cp.UNBOUNDED_OR_UNKNOWN


def test_cgroup_absent_files(tmp_path):
    limits = cp._parse_cgroup_limits(sys_root=str(tmp_path / "nope"))
    assert limits["source"] == "none"
    assert limits["memoryLimitBytes"] == cp.UNBOUNDED_OR_UNKNOWN
    assert limits["cpuLimitCores"] == cp.UNBOUNDED_OR_UNKNOWN


# ── container detection ───────────────────────────────────────────────────────

def test_container_detected_by_dockerenv(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, ".dockerenv", "")
    _write(root, "proc/1/cgroup", "0::/\n")
    det = cp._detect_container({}, sys_root=str(root))
    assert det["inContainer"] is True
    assert "/.dockerenv present" in det["markers"]


def test_container_detected_by_proc_cgroup(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "proc/1/cgroup",
           "11:memory:/docker/abc123\n0::/docker/abc123\n")
    det = cp._detect_container({}, sys_root=str(root))
    assert det["inContainer"] is True
    assert "proc-1-cgroup:docker" in det["markers"]


def test_container_not_detected_on_bare_tree(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "proc/1/cgroup", "0::/init.scope\n")
    det = cp._detect_container({}, sys_root=str(root))
    assert det["inContainer"] is False
    assert det["markers"] == []


def test_container_cgroup_version_v2_marker(tmp_path):
    root = tmp_path / "sysroot"
    _write(root, "sys/fs/cgroup/cgroup.controllers", "cpu memory\n")
    det = cp._detect_container({}, sys_root=str(root))
    assert det["cgroupVersion"] == "v2"


# ── environment-capabilities record shape ─────────────────────────────────────

REQUIRED_SECTIONS = {
    "runtime", "os", "container", "resourceLimits", "storage", "client",
    "location", "browsers", "playwrightProof", "extension", "authMethods",
    "apiOperations",
}


def test_envcaps_record_shape_and_timestamps(tmp_path):
    res = cp.run_probe(runner=runner_nothing(), env={}, now=NOW,
                       pw_launcher=_proof_ok, sys_root=str(tmp_path))
    assert "environmentCapabilities" in res
    envcaps = res["environmentCapabilities"]
    assert envcaps["schema"] == "skill6-environment-capabilities/1"
    assert REQUIRED_SECTIONS <= set(envcaps.keys())
    for section in REQUIRED_SECTIONS:
        assert envcaps[section]["evidenceAt"] == NOW, section
    # runtime/os facts are stated, harness honestly unknown with no markers
    assert envcaps["runtime"]["name"] == "unknown"
    assert envcaps["runtime"]["evidence"] == "none"
    assert envcaps["os"]["architecture"]
    assert envcaps["os"]["platform"] == res["platform"]
    # storage root is a real path string, limits honestly unbounded here
    assert isinstance(envcaps["storage"]["persistentRoot"], str)
    assert envcaps["resourceLimits"]["memoryLimitBytes"] == \
        cp.UNBOUNDED_OR_UNKNOWN
    # declared API operations are labeled, never dressed as live-proven
    assert envcaps["apiOperations"]["verification"] == \
        "declared-not-live-proven"
    assert envcaps["apiOperations"]["public"]
    assert envcaps["apiOperations"]["internal"]


def test_envcaps_harness_detection_from_env_markers():
    res = cp.run_probe(runner=runner_nothing(),
                       env={"CLAUDECODE": "1"}, now=NOW,
                       pw_launcher=_proof_failed)
    runtime = res["environmentCapabilities"]["runtime"]
    assert runtime["name"] == "claude-code"
    assert runtime["evidence"] == "env:CLAUDECODE"


def test_envcaps_secrets_are_booleans_and_references_only():
    secret_env = {
        "GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN": "SEKRET-TOKEN",
        "GHL_API_KEY": "SEKRET-PIT",
        "GOHIGHLEVEL_LOCATION_ID": "SEKRET-LOC",
        "GHL_SKILL6_CLIENT_SLUG": "SEKRET-CLIENT",
    }
    res = cp.run_probe(runner=runner_nothing(), env=secret_env, now=NOW,
                       pw_launcher=_proof_failed)
    envcaps = res["environmentCapabilities"]
    blob = json.dumps(envcaps)
    for value in secret_env.values():
        assert value not in blob
    # identity/location appear as env-var reference NAMES + booleans only
    assert envcaps["client"] == {
        "identityPresent": True,
        "identityReference": "GHL_SKILL6_CLIENT_SLUG",
        "evidenceAt": NOW,
    }
    assert envcaps["location"]["present"] is True
    assert envcaps["location"]["reference"] == "GOHIGHLEVEL_LOCATION_ID"
    assert envcaps["location"]["verified"] == "unknown"
    auth = envcaps["authMethods"]
    assert auth["firebaseRefreshToken"] == {"approved": True, "present": True}
    assert auth["locationPit"] == {"approved": True, "present": True}
    assert auth["gatedEmail2faBootstrap"]["approved"] is True
    assert auth["gatedEmail2faBootstrap"]["modulePresent"] is True


# ── extension currentness representation ──────────────────────────────────────

def test_envcaps_extension_unknown_currentness(tmp_path):
    """Extension present but expected version unknowable on this box:
    the LEGACY lane field keeps its historical boolean (presence counts
    as current), while the new record must read current: "unknown"."""
    home = tmp_path / "home"
    home.mkdir()
    env = {
        "GHL_SKILL6_CHROME_PROFILE_ROOTS": FIXTURE_CHROME_ROOT,
        "HOME": str(home),  # no bundled manifest under this HOME
    }
    res = cp.run_probe(runner=runner_nothing(), env=env, now=NOW,
                       pw_launcher=_proof_failed)
    legacy = res["lanes"]["openclaw_managed_browser"]["extension"]
    assert legacy["installed"] is True
    assert legacy["version"] == "2.3.0"
    assert legacy["expectedVersion"] is None
    assert legacy["current"] is True  # legacy behavior untouched
    ext = res["environmentCapabilities"]["extension"]
    assert ext["installed"] is True
    assert ext["installedVersion"] == "2.3.0"
    assert ext["expectedVersion"] is None
    assert ext["expectedSource"] == "unknown"
    assert ext["current"] == "unknown"
    assert ext["attached"] == "unknown"
    assert ext["connectionHealth"] == "unknown"


def test_envcaps_extension_current_with_expected(tmp_path):
    env = {
        "GHL_SKILL6_CHROME_PROFILE_ROOTS": FIXTURE_CHROME_ROOT,
        "SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION": "2.3.0",
        "HOME": str(tmp_path),
    }
    res = cp.run_probe(runner=runner_nothing(), env=env, now=NOW,
                       pw_launcher=_proof_failed)
    ext = res["environmentCapabilities"]["extension"]
    assert ext["current"] is True
    assert ext["expectedSource"] == \
        "env:SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"
    # behind reads False, never "unknown"
    env["SKILL6_OPENCLAW_EXTENSION_EXPECTED_VERSION"] = "9.9.9"
    res = cp.run_probe(runner=runner_nothing(), env=env, now=NOW,
                       pw_launcher=_proof_failed)
    assert res["environmentCapabilities"]["extension"]["current"] is False


# ── Playwright proof recording ────────────────────────────────────────────────

def test_playwright_proof_recorded_from_injected_launcher_success():
    res = cp.run_probe(runner=runner_nothing(), env={}, now=NOW,
                       pw_launcher=_proof_ok)
    assert res["environmentCapabilities"]["playwrightProof"] == {
        "attempted": True, "launched": True, "screenshotTaken": True,
        "errorClass": None, "evidenceAt": NOW,
    }


def test_playwright_proof_recorded_from_injected_launcher_failure():
    res = cp.run_probe(runner=runner_nothing(), env={}, now=NOW,
                       pw_launcher=_proof_failed)
    assert res["environmentCapabilities"]["playwrightProof"] == {
        "attempted": True, "launched": False, "screenshotTaken": False,
        "errorClass": "browser-binary-missing", "evidenceAt": NOW,
    }


def test_playwright_proof_default_path_missing_package():
    """Default launcher through a dead runner: attempted, not launched,
    classified playwright-missing (the import probe also failed)."""
    proof = cp._default_playwright_launcher(runner_nothing(),
                                            package_available=False)
    assert proof == {"attempted": True, "launched": False,
                     "screenshotTaken": False,
                     "errorClass": "playwright-missing"}


def test_playwright_proof_default_path_parses_child_verdict():
    verdict = json.dumps({"launched": True, "screenshotTaken": True,
                          "errorClass": None})
    runner = _fake_runner(**{"skill6-pw-proof": _CP(returncode=0,
                                                    stdout=verdict + "\n")})
    proof = cp._default_playwright_launcher(runner, package_available=True)
    assert proof["attempted"] is True
    assert proof["launched"] is True
    assert proof["screenshotTaken"] is True
    assert proof["errorClass"] is None


def test_playwright_proof_default_path_no_verdict_is_launch_failed():
    runner = _fake_runner(**{"__never__": _CP(returncode=1)})
    proof = cp._default_playwright_launcher(runner, package_available=True)
    assert proof["launched"] is False
    assert proof["errorClass"] == "launch-failed"

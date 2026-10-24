"""Small runnable check for `runtime_adapters.py` (unit W3C-U1).

Repo test style: load the module by path (shared-utils is not an installed
package) and exercise it directly. Offline only — no network, no browser
launch, no display required.

Run: python3 -m pytest shared-utils/browser/test_runtime_adapters.py -q
"""
import importlib.util
import os
import sys

import pytest

_MOD = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runtime_adapters.py")
_spec = importlib.util.spec_from_file_location("runtime_adapters_under_test", _MOD)
ra = importlib.util.module_from_spec(_spec)
# Python 3.14 dataclasses resolve KW_ONLY annotations via
# sys.modules[cls.__module__]; register before exec_module.
sys.modules[_spec.name] = ra
_spec.loader.exec_module(ra)


def test_detect_platform_shapes():
    info = ra.detect_platform()
    assert info.system in ("darwin", "linux", "windows", "other")
    assert info.arch in ("arm64", "x86_64", "other")
    assert info.is_mac == (info.system == "darwin")
    assert info.is_linux == (info.system == "linux")
    assert info.python.count(".") == 2


def test_dependency_probe_reports_without_raising():
    deps = ra.detect_dependencies(env={})
    assert set(deps) >= {"python", "playwright", "chromium", "node", "git"}
    assert deps["python"].found
    for st in deps.values():
        assert st.detail
    # assert_dependencies names every missing one
    with pytest.raises(ra.DependencyError) as exc:
        ra.assert_dependencies(deps, ["python", "definitely-missing-dep"])
    assert "definitely-missing-dep" in str(exc.value)


def test_no_mac_paths_on_linux():
    linux = ra.PlatformInfo("linux", "x86_64", "3.11.0", False, True, True)
    for bad in ("/Users/x", "/Volumes/usb/x", "/Applications/x", "/Library/x"):
        assert ra.looks_like_mac_path(bad)
        with pytest.raises(ra.PathPlatformError):
            ra.assert_paths_platform_safe([bad], linux)
    ra.assert_paths_platform_safe(["/tmp/ok", "/home/ok", "/data/ok"], linux)
    mac = ra.PlatformInfo("darwin", "arm64", "3.11.0", True, False, False)
    ra.assert_paths_platform_safe(["/Users/ok"], mac)  # legal on mac


def test_harness_paths_writable_and_prefixed(tmp_path, monkeypatch):
    monkeypatch.setenv("GHL_HARNESS_SCRATCH", str(tmp_path))
    hp = ra.harness_paths("W3C-U1", box_slug="mac-mini-m4")
    for d in (hp.base_dir, hp.scratch_dir, hp.profile_dir, hp.artifact_dir):
        assert d.is_dir()
        assert os.access(d, os.W_OK)
    assert hp.base_dir.name.startswith("mac-mini-m4-W3C-U1-")
    info = ra.detect_platform()
    if info.is_linux:
        assert not str(hp.base_dir).startswith(ra.MAC_ONLY_ROOTS)


def test_scratch_candidates_no_mac_default_on_linux():
    linux = ra.PlatformInfo("linux", "x86_64", "3.11.0", False, True, True)
    cands = ra.scratch_candidates("W3C-U1", linux, box_slug="box",
                                  env={"TMPDIR": "/tmp"})
    assert cands
    for c in cands:
        assert not ra.looks_like_mac_path(c)


def test_headless_always_required_and_display_never_relaxes_it(monkeypatch):
    assert ra.headless_required() is True
    linux = ra.PlatformInfo("linux", "x86_64", "3.11.0", False, True, True)
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    assert ra.display_state(linux, env={}) == ra.DisplayState.ABSENT
    assert ra.headless_required() is True  # absent display still headless
    monkeypatch.setenv("DISPLAY", ":0")
    assert ra.display_state(linux, env={"DISPLAY": ":0"}) == ra.DisplayState.PRESENT
    assert ra.headless_required() is True  # present display still headless


def test_redact_masks_secret_shapes():
    text = "sk-abcdef1234567890 Authorization: Bearer ghi987654321 api_key=zzzTOPSECRET"
    masked = ra.redact(text)
    assert "abcdef1234567890" not in masked
    assert "ghi987654321" not in masked
    assert "zzzTOPSECRET" not in masked
    assert ra.redact("plain text stays") == "plain text stays"


def test_self_check_passes():
    ra._self_check()

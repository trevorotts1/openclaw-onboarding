#!/usr/bin/env python3
"""MOCK-only tests — openclaw_browser_adapter.sh (Skill 06 Lane 2 adapter).

These tests are MOCK-ONLY. There is NO live OpenClaw, NO managed-browser
launch, NO network, NO secrets. Every subprocess test either restricts PATH to
/usr/bin:/bin (where the `openclaw` CLI does not exist) or installs a tiny
argv-echoing STUB `openclaw` on a scratch PATH. No verb ever reaches a real
browser; `--selftest` itself is browser-safe by construction (it runs only
against stripped PATHs and stubs).

Exit-code contract under test (documented in the adapter header):
  0   success
  64  usage error / openclaw CLI absent
  75  capability gate refusal (JSON missing/unreadable, python3 absent, or
      lanes.openclaw_managed_browser.cliWorks not true)

Coverage per the P1-12 / 9.7-6 task contract:
  (a) `--selftest` subprocess exits 0 (offline, timeout 120, no browser)
  (b) every verb against a PATH WITHOUT openclaw -> exit 64 + stderr names openclaw
      (CLI-absent refusal fires FIRST, before any capability work)
  (c) capability gate: cliWorks=false -> exit 75 + names cliWorks;
      missing JSON -> exit 75 + names the path (tmp capability JSON)
  (d) verb->CLI mapping through the stub: status/start/open/snapshot/click/
      type/frame-snapshot/stop all translate per Appendix A, snapshot always
      carries --interactive (+ --efficient preset by default), --frame
      SELECTOR passes through verbatim
  (e) usage errors: unknown verb / open without URL / type with one arg -> 64

Run:
    python3 -m pytest tests/test_openclaw_browser_adapter.py -v
"""
from __future__ import annotations

import os
import subprocess
import stat
import sys
import tempfile
from pathlib import Path

import pytest

_TOOLS_DIR = (Path(__file__).parent.parent / "tools").resolve()
_ADAPTER_SH = _TOOLS_DIR / "openclaw_browser_adapter.sh"

ALL_VERBS = ["status", "start", "open", "snapshot", "click", "type",
             "frame-snapshot", "stop"]

# PATH where the real openclaw CLI cannot exist (it lives in ~/.local/bin on
# the operator box; /usr/bin:/bin is the minimal system set).
_STRIpped_PATH = "/usr/bin:/bin"


def _read(p: Path) -> str:
    assert p.exists(), f"missing: {p}"
    return p.read_text(encoding="utf-8")


def _make_stub_dir(tmp_path: Path) -> Path:
    """Write a stub `openclaw` that echoes its argv one-per-line, exit 0."""
    stub_dir = tmp_path / "stubbin"
    stub_dir.mkdir(exist_ok=True)
    stub = stub_dir / "openclaw"
    stub.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do printf "%s\\n" "$a"; done\n'
        "exit 0\n",
        encoding="utf-8",
    )
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return stub_dir


def _cap_json(tmp_path: Path, cliworks: bool) -> Path:
    p = tmp_path / "capability.json"
    p.write_text(
        '{"lanes": {"openclaw_managed_browser": {"cliWorks": %s}}}\n'
        % ("true" if cliworks else "false"),
        encoding="utf-8",
    )
    return p


def _run_adapter(args, env_extra, timeout=120):
    env = dict(os.environ)
    env.pop("GHL_SKILL6_CAPABILITY_JSON", None)
    env.pop("GHL_SKILL6_SNAPSHOT_MODE", None)
    env.pop("OCB_PROFILE", None)
    env.pop("OCB_CALL_TIMEOUT", None)
    env.update(env_extra)
    return subprocess.run(
        ["bash", str(_ADAPTER_SH)] + list(args),
        capture_output=True, text=True, timeout=timeout, env=env,
    )


def _stub_env(tmp_path: Path) -> dict:
    return {
        "PATH": f"{_make_stub_dir(tmp_path)}:/usr/bin:/bin",
        "GHL_SKILL6_CAPABILITY_JSON": str(_cap_json(tmp_path, True)),
        "GHL_SKILL6_SNAPSHOT_MODE": "efficient",
    }


# ── (a) --selftest subprocess convention ─────────────────────────────────────

def test_selftest_subprocess_exit_zero():
    proc = subprocess.run(
        ["bash", str(_ADAPTER_SH), "--selftest"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"--selftest must exit 0 offline\nstdout:\n{proc.stdout}\n"
        f"stderr:\n{proc.stderr}"
    )
    assert "SELFTEST PASS" in proc.stdout


def test_selftest_runs_without_openclaw_on_path():
    """The selftest must pass with the openclaw CLI removed from PATH — proving
    no real binary or browser is ever needed (and none is launched)."""
    env = dict(os.environ)
    env["PATH"] = _STRIpped_PATH
    proc = subprocess.run(
        ["bash", str(_ADAPTER_SH), "--selftest"],
        capture_output=True, text=True, timeout=120, env=env,
    )
    assert proc.returncode == 0
    assert "SELFTEST PASS" in proc.stdout


# ── (b) CLI-absent refusal: exit 64, fires before anything else ──────────────

@pytest.mark.parametrize("verb", ALL_VERBS)
def test_verb_without_openclaw_cli_exits_64(tmp_path, verb):
    """Every verb against a PATH WITHOUT openclaw -> exit 64 + stderr names
    openclaw. Uses the box's own PATH restriction; the adapter must refuse
    before ever attempting a browser action."""
    env = {"PATH": _STRIpped_PATH}
    if verb == "open":
        args = [verb, "https://example.test/ghl"]
    elif verb == "type":
        args = [verb, "f1e12", "text"]
    else:
        args = [verb]
    proc = _run_adapter(args, env)
    assert proc.returncode == 64, (
        f"verb {verb} without openclaw on PATH: expected exit 64, got "
        f"{proc.returncode}\nstderr:\n{proc.stderr}"
    )
    assert "openclaw" in (proc.stderr + proc.stdout).lower()
    assert "REFUSE" in (proc.stderr + proc.stdout)


def test_cli_absent_refusal_mentions_primary_lane():
    """The refusal should point the caller at the agent-browser PRIMARY so a
    Lane-2 miss is actionable, not a dead end."""
    proc = _run_adapter(["status"], {"PATH": _STRIpped_PATH})
    combined = proc.stderr + proc.stdout
    assert "agent-browser" in combined or "browser_manager" in combined


# ── (c) capability gate ──────────────────────────────────────────────────────

def test_capability_gate_cliworks_false_exits_75(tmp_path):
    """cliWorks=false -> exit 75 + names the gate field (one documented code)."""
    stub_dir = _make_stub_dir(tmp_path)
    cap = _cap_json(tmp_path, cliworks=False)
    proc = _run_adapter(
        ["status"],
        {"PATH": f"{stub_dir}:/usr/bin:/bin",
         "GHL_SKILL6_CAPABILITY_JSON": str(cap)},
    )
    assert proc.returncode == 75, f"expected 75, got {proc.returncode}\n{proc.stderr}"
    assert "cliWorks" in (proc.stderr + proc.stdout)


def test_capability_gate_missing_json_exits_75(tmp_path):
    stub_dir = _make_stub_dir(tmp_path)
    proc = _run_adapter(
        ["status"],
        {"PATH": f"{stub_dir}:/usr/bin:/bin",
         "GHL_SKILL6_CAPABILITY_JSON": str(tmp_path / "absent.json")},
    )
    assert proc.returncode == 75
    combined = proc.stderr + proc.stdout
    assert "absent.json" in combined
    assert "capability" in combined.lower()


def test_capability_gate_cli_absent_beats_capability(tmp_path):
    """Ordering contract: with NO openclaw on PATH the adapter exits 64 (CLI
    gate) even though the capability JSON would also refuse (75) — the CLI
    check runs FIRST per the P1-12 contract."""
    cap = _cap_json(tmp_path, cliworks=True)
    proc = _run_adapter(
        ["status"],
        {"PATH": _STRIpped_PATH, "GHL_SKILL6_CAPABILITY_JSON": str(cap)},
    )
    assert proc.returncode == 64


# ── (d) verb->CLI mapping through the stub ───────────────────────────────────

def test_status_mapping(tmp_path):
    proc = _run_adapter(["status"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "--browser-profile" in out and "openclaw" in out
    assert "status" in out


def test_start_mapping(tmp_path):
    proc = _run_adapter(["start"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "start" in out


def test_open_mapping(tmp_path):
    url = "https://app.convertandflow.com/"
    proc = _run_adapter(["open", url], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "open" in out and url in out


def test_snapshot_mapping_defaults(tmp_path):
    """P1-12 snapshotDefaults: ALWAYS --interactive; --efficient preset on by
    default (GHL_SKILL6_SNAPSHOT_MODE=efficient)."""
    proc = _run_adapter(["snapshot"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "snapshot" in out
    assert "--interactive" in out, "snapshotDefaults: --interactive is mandatory"
    assert "--efficient" in out, "snapshotDefaults.mode: efficient preset expected"


def test_snapshot_efficient_mode_off(tmp_path):
    """A caller can drop the efficient preset via GHL_SKILL6_SNAPSHOT_MODE."""
    env = _stub_env(tmp_path)
    env["GHL_SKILL6_SNAPSHOT_MODE"] = "full"
    proc = _run_adapter(["snapshot"], env)
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "--interactive" in out
    assert "--efficient" not in out


def test_frame_snapshot_mapping(tmp_path):
    """frame-snapshot -> snapshot --interactive --frame SELECTOR, selector
    verbatim (plan Appendix A / 9.6: frame-scoped snapshots are Lane 2's point)."""
    sel = 'iframe[src*="form-builder-v2"]'
    proc = _run_adapter(["frame-snapshot", sel], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "snapshot" in out
    assert "--interactive" in out
    assert "--frame" in out
    assert sel in out


def test_click_mapping(tmp_path):
    proc = _run_adapter(["click", "f1e12"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "click" in out and "f1e12" in out


def test_type_mapping(tmp_path):
    proc = _run_adapter(["type", "f1e12", "hello world"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "type" in out
    assert "f1e12" in out and "hello world" in out


def test_stop_mapping(tmp_path):
    """stop -> `openclaw browser close` per the P1-12 contract (tab close is
    the Skill 6 teardown unit; the process-level `stop` is not mapped)."""
    proc = _run_adapter(["stop"], _stub_env(tmp_path))
    assert proc.returncode == 0
    out = (proc.stdout + proc.stderr).splitlines()
    assert "browser" in out and "close" in out


# ── (e) usage errors ─────────────────────────────────────────────────────────

def test_unknown_verb_exits_64():
    proc = _run_adapter(["frobnicate"], {"PATH": _STRIpped_PATH})
    assert proc.returncode == 64
    assert "unknown verb" in (proc.stderr + proc.stdout).lower()


def test_no_verb_prints_usage_exits_64():
    proc = _run_adapter([], {"PATH": _STRIpped_PATH})
    assert proc.returncode == 64


def test_open_without_url_exits_64(tmp_path):
    proc = _run_adapter(["open"], _stub_env(tmp_path))
    assert proc.returncode == 64
    assert "url" in (proc.stderr + proc.stdout).lower()


def test_type_missing_text_exits_64(tmp_path):
    proc = _run_adapter(["type", "f1e12"], _stub_env(tmp_path))
    assert proc.returncode == 64


def test_frame_snapshot_without_selector_exits_64(tmp_path):
    proc = _run_adapter(["frame-snapshot"], _stub_env(tmp_path))
    assert proc.returncode == 64
    assert "selector" in (proc.stderr + proc.stdout).lower()


def test_help_flag_exits_zero():
    proc = _run_adapter(["--help"], {"PATH": _STRIpped_PATH})
    assert proc.returncode == 0
    combined = proc.stdout + proc.stderr
    for verb in ALL_VERBS:
        assert verb in combined


# ── static: adapter never references a real browser launch in selftest ───────

def test_selftest_never_starts_a_browser_process():
    """Static guard: the selftest body must not invoke a real browser binary —
    only PATH-stripped subprocesses and the argv stub. The strings 'browser
    start' / 'browser open' legitimately appear in the selftest's PASS-message
    labels, so the guard targets actual invocation shapes: the CLI word at the
    START of a command, `agent-browser`, and `navigate`."""
    src = _read(_ADAPTER_SH)
    # Extract the selftest function body (up to the next top-level definition).
    start = src.index("selftest() {")
    body = src[start:]
    assert "agent-browser" not in body
    assert "navigate" not in body
    # No line may EXEC openclaw with a browser-verb as its first argument.
    for line in body.splitlines():
        stripped = line.strip()
        if stripped.startswith('"$OCB_BIN_NAME"') or stripped.startswith('"$OCB"'):
            assert not any(
                stripped.startswith(f'"{name}" {verb}')
                for name in ("$OCB_BIN_NAME", "$OCB")
                for verb in ("browser", "start", "open", "navigate", "click")
            ), f"selftest must not exec a browser verb: {stripped}"


def test_script_bash32_safe_static():
    """P1-12 portability: no mapfile, no associative arrays, no ${var,,}
    lowercasing — in CODE. (Doc-comment mentions of the banned constructs are
    fine and expected; strip comments before asserting.)"""
    src = _read(_ADAPTER_SH)
    code_lines = [
        ln for ln in src.splitlines()
        if ln.strip() and not ln.strip().startswith("#")
    ]
    code = "\n".join(code_lines)
    assert "mapfile" not in code
    assert "declare -A" not in code
    assert "declare -a" not in code
    assert ",," not in code
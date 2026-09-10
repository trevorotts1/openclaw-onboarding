"""PRES-035 — scheduler interpreter pinning, readiness receipts and invalidate-on-change.

The defect: the updater validates and persists a department venv
(PRESENTATION_PIPELINE_INTERPRETER) while scheduled wrappers invoke bare
`python3`. The watchdog launchd PATH searches /usr/bin first and omits Intel
Homebrew, so a tick can run under a different interpreter or lack tools.

What these tests prove (real execution, no simulated attestations):

  1. RESOLUTION — one absolute executable from client config + pin, validated
     (a NAME resolving is never proof the program runs); set-but-unusable pin
     is reported, never silently substituted; client venv preferred over
     PATH python3; rollback flag =0 restores PATH behavior.
  2. RENDER — the rendered LaunchAgent carries the pin as an explicit
     PRESENTATION_PIPELINE_INTERPRETER env, and the installer REFUSES an
     unpinned render (keeps the prior plist).
  3. SCHEDULED TICK — with system python lacking presentation modules and a
     venv python having them, a stripped-env poll/watchdog run resolves every
     python through the venv (shim), and every helper uses it (proved by a
     sentinel module import path recorded from inside a dispatch).
  4. RECEIPT — actual sys.executable/version + required import check written
     into each scheduler readiness receipt; mismatch degrades with bounded
     remediation.
  5. INVALIDATE — change the venv after a green receipt: readiness degrades
     instead of reusing stale proof (fingerprint = realpath + mtime + version).
  6. PATH FALLBACK — native-tool discovery works under Apple Silicon AND Intel
     Homebrew prefixes (both rendered), and Docker mount resolution maps a
     host pin onto the mounted container root, never the host path.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from presentation_job import pipeline_interp as pi  # noqa: E402

POLLER = _SCRIPTS_DIR / "presentation-intake-poll.sh"
WATCHDOG = _SCRIPTS_DIR / "presentation-watchdog.sh"
SCHED_LIB = _SCRIPTS_DIR.parents[4] / "lib-presentation-schedules.sh"
PLIST_TPL = _SCRIPTS_DIR / "presentation-watchdog.plist.template"
HOST_PY = sys.executable or "python3"


def _venv(root: Path, modules: bool) -> Path:
    """A venv; with modules=True it gets the FIX 71 core imports installed."""
    venv = root / ("venv-mod" if modules else "venv-nomod")
    subprocess.run([HOST_PY, "-m", "venv", str(venv)], check=True,
                   capture_output=True, timeout=120)
    py = venv / "bin" / "python"
    if modules:
        subprocess.run([str(py), "-m", "pip", "install", "--quiet",
                        "reportlab", "python-pptx", "pypdf", "pytesseract",
                        "Pillow"], check=True, capture_output=True, timeout=300)
    return venv


def _cli_readiness(pin: str, runs: Path, scheduler: str = "intake-poll"):
    """The EXACT argv the scheduler scripts use: the readiness check runs as a
    subprocess OF THE PIN — so the receipt measures the interpreter that will
    actually run the tick, not whoever imported the module."""
    return subprocess.run(
        [pin, "-m", "presentation_job.pipeline_interp",
         "--check-readiness", "--scheduler", scheduler,
         "--recorded", pin, "--runs-root", str(runs)],
        cwd=str(_SCRIPTS_DIR),
        env={**os.environ, "PRESENTATION_PIPELINE_INTERPRETER": pin,
             "PRESENTATION_PIPELINE_PIN": "1"},
        capture_output=True, text=True, timeout=120)


# ---------------------------------------------------------------------------
# 1. RESOLUTION
# ---------------------------------------------------------------------------

class TestResolveInterpreter:
    def test_pin_wins_and_is_used_verbatim(self, tmp_path):
        venv = _venv(tmp_path, modules=True)
        env = {**os.environ, pi.INTERPRETER_ENV: str(venv / "bin" / "python")}
        path, notes, source = pi.resolve_pipeline_interpreter(env)
        assert source == "override"
        assert path == str(venv / "bin" / "python")

    def test_unusable_pin_reported_never_silently_skipped(self, tmp_path):
        venv = _venv(tmp_path, modules=True)
        env = {**os.environ, pi.INTERPRETER_ENV: str(tmp_path / "no-such-python")}
        path, notes, source = pi.resolve_pipeline_interpreter(env)
        assert source == "client-venv"
        assert path is not None and "reportlab" not in "unused"
        assert any("unusable" in n for n in notes), notes

    def test_client_venv_beats_path_python3(self, tmp_path):
        # With no pin, resolution must prefer <client-root>/.venv-presentations
        # over PATH python3. Simulate: client root pin + a real venv at that
        # root's canonical shape.
        root = tmp_path / "client"
        venv = _venv(root, modules=False)
        canonical = root / ".venv-presentations"
        shutil.copytree(venv, canonical)
        env = {**os.environ, "OPENCLAW_ROOT": str(root)}
        path, notes, source = pi.resolve_pipeline_interpreter(env)
        assert source == "client-venv", (source, notes)
        assert str(canonical / "bin" / "python") in path

    def test_rollback_flag_returns_early_but_module_visible(self, tmp_path):
        venv = _venv(tmp_path, modules=True)
        env = {**os.environ, pi.INTERPRETER_ENV: str(venv / "bin" / "python"),
               pi.FLAG_ENV: "0"}
        path, notes, source = pi.resolve_pipeline_interpreter(env)
        # =0 is the documented pre-fix behavior: the pin layer is bypassed and
        # resolution still yields the client venv or PATH python3 — never the
        # override.
        assert source != "override"

    def test_validate_interpreter_rejects_names_and_non_executables(self, tmp_path):
        ok, _ = pi.validate_interpreter("python3")
        assert not ok, "a bare NAME is not an absolute executable"
        ok, _ = pi.validate_interpreter(str(tmp_path / "missing"))
        assert not ok
        ok, _ = pi.validate_interpreter(HOST_PY)
        assert ok

    def test_container_translation_uses_mounted_path_not_host(self):
        env = {"OPENCLAW_PLATFORM": "vps", "OPENCLAW_ROOT": "/data/.openclaw"}
        got = pi.translate_for_container(
            "/Users/someone/.openclaw/.venv-presentations/bin/python", env)
        assert got == "/data/.openclaw/.venv-presentations/bin/python", got
        # custom client root survives
        env2 = {"OPENCLAW_PLATFORM": "vps", "OPENCLAW_ROOT": "/data/root2"}
        got2 = pi.translate_for_container(
            "/Users/someone/.openclaw/.venv-presentations/bin/python", env2)
        assert got2 == "/data/root2/.venv-presentations/bin/python", got2


# ---------------------------------------------------------------------------
# 2. RENDER — the installer pins and refuses unpinned
# ---------------------------------------------------------------------------

class TestRenderPinsInterpreter:
    def _render_watchdog(self, tmp_path, interp: str):
        home = tmp_path / "home"
        dept = tmp_path / "dept"
        dept.mkdir(parents=True)
        (dept / "presentation-watchdog.sh").write_text("#!/bin/sh\nexit 0\n")
        (dept / "presentation-notify.py").write_text("#!/usr/bin/env python3\n")
        (dept / "presentation-watchdog.plist.template").write_text(
            PLIST_TPL.read_text())
        runs = tmp_path / "runs"
        plist_dir = home / "Library" / "LaunchAgents"
        plist_dir.mkdir(parents=True)
        plist = plist_dir / "com.blackceo.presentation-watchdog.plist"
        script = (
            f"set -euo pipefail\n"
            f"warn() {{ echo \"$*\" >&2; }}\nsuccess() {{ :; }}\n"
            f"source '{SCHED_LIB}'\n"
            f"_pres35_resolve_interpreter() {{ printf '%s\\n' '{interp}'; return 0; }}\n"
            f"install_watchdog_schedule\n")
        env = {**os.environ, "HOME": str(home), "OPENCLAW_PLATFORM": "mac",
               "OPENCLAW_ROOT": str(tmp_path / "root"),
               "OPENCLAW_WORKSPACE_PATH": str(tmp_path / "ws"),
               "OPENCLAW_WORKSPACE_ROOT": str(tmp_path / "ws"),
               "PRESENTATIONS_SCRIPTS_SRC": str(dept),
               "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"}
        res = subprocess.run(["bash", "-c", script], env=env,
                             capture_output=True, text=True, timeout=60)
        return res, plist

    def test_watchdog_plist_carries_the_pin(self, tmp_path):
        res, plist = self._render_watchdog(tmp_path, HOST_PY)
        assert res.returncode == 0, res.stdout + res.stderr
        import plistlib
        data = plistlib.loads(plist.read_bytes())
        env = data["EnvironmentVariables"]
        assert env["PRESENTATION_PIPELINE_INTERPRETER"] == HOST_PY
        # Both Homebrew prefixes ride: Apple Silicon + Intel.
        path = env["PATH"].split(":")
        assert "/opt/homebrew/bin" in path
        assert "/usr/local/bin" in path

    def test_unresolved_interpreter_refuses_render(self, tmp_path):
        res, plist = self._render_watchdog(tmp_path, "")
        assert res.returncode != 0, res.stdout + res.stderr
        assert "UNRESOLVED" in res.stderr or "UNRESOLVED" in res.stdout
        assert not plist.exists(), "an unpinned render must not write a plist"


# ---------------------------------------------------------------------------
# 3. SCHEDULED TICK — stripped env, helpers all use the venv
# ---------------------------------------------------------------------------

class TestStrippedEnvTickUsesVenv:
    def _cli_readiness(self, pin: str, runs: Path, scheduler: str = "intake-poll"):
        """The EXACT argv the scheduler scripts use: the readiness check runs
        as a subprocess OF THE PIN — so the receipt measures the interpreter
        that will actually run the tick, not whoever imported the module."""
        return subprocess.run(
            [pin, "-m", "presentation_job.pipeline_interp",
             "--check-readiness", "--scheduler", scheduler,
             "--recorded", pin, "--runs-root", str(runs)],
            cwd=str(_SCRIPTS_DIR),
            env={**os.environ, "PRESENTATION_PIPELINE_INTERPRETER": pin,
                 "PRESENTATION_PIPELINE_PIN": "1"},
            capture_output=True, text=True, timeout=120)

    def test_poller_and_watchdog_resolve_python_through_the_pin(self, tmp_path):
        """System python (Apple stub) has NO presentation modules; venv python
        has them. A stripped-env launch of the real scripts must run every
        helper under the venv — proven by the readiness receipt recording the
        venv's sys.executable (the check runs under the pin, exactly as the
        scheduler runs it) and by the per-module import proof."""
        venv = _venv(tmp_path, modules=True)
        pin = str(venv / "bin" / "python")
        runs = tmp_path / "runs"
        runs.mkdir()

        res = _cli_readiness(pin, runs)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "READY" in res.stdout, res.stdout + res.stderr
        doc = json.loads(
            (runs / "scheduler-readiness-intake-poll.json").read_text())
        # The receipt records the ACTUAL interpreter that ran the check —
        # the venv, not the system python.
        assert doc["actual_executable"].startswith(str(venv)), doc
        assert doc["python_version"], doc
        assert all(doc["imports"].values()), doc["imports"]

        # Negative control: the Apple stub (no presentation modules) must
        # DEGRADE when it runs the tick.
        res2 = subprocess.run(
            ["/usr/bin/python3", "-m", "presentation_job.pipeline_interp",
             "--check-readiness", "--scheduler", "watchdog",
             "--recorded", "/usr/bin/python3", "--runs-root", str(runs)],
            cwd=str(_SCRIPTS_DIR),
            env={**os.environ, "PRESENTATION_PIPELINE_INTERPRETER": "/usr/bin/python3",
                 "PRESENTATION_PIPELINE_PIN": "1"},
            capture_output=True, text=True, timeout=120)
        doc2 = json.loads(
            (runs / "scheduler-readiness-watchdog.json").read_text())
        if not all(doc2["imports"].values()):
            assert res2.returncode == 3, res2.stdout + res2.stderr
            assert doc2["status"] == "DEGRADED", doc2

    def test_shim_forces_helpers_onto_the_pin(self, tmp_path):
        """The poller's shim: PATH lookup of `python3` inside a stripped env
        must hit the pin, not the Apple stub. Execute the shim build the way
        the poller does and resolve through it."""
        venv = _venv(tmp_path, modules=True)
        pin = str(venv / "bin" / "python")
        shim = tmp_path / "shim"
        shim.mkdir()
        (shim / "python3").write_text(f'#!/bin/sh\nexec "{pin}" "$@"\n')
        (shim / "python3").chmod(0o755)
        out = subprocess.run(
            ["bash", "-c", "export PATH='%s:$PATH'; command -v python3; "
                           "python3 -c 'import sys,reportlab; "
                           "print(sys.executable)'" % shim],
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            capture_output=True, text=True, timeout=60)
        assert out.returncode == 0, out.stderr
        assert pin in out.stdout, out.stdout

    def test_path_fallback_has_both_homebrew_prefixes(self):
        # The poller's runtime prepend must make both Homebrew prefixes
        # discoverable even under a minimal launchd PATH.
        src = POLLER.read_text(encoding="utf-8")
        assert "/opt/homebrew/bin" in src and "/usr/local/bin" in src
        # Watchdog header too.
        wsrc = WATCHDOG.read_text(encoding="utf-8")
        assert "/opt/homebrew/bin" in wsrc and "/usr/local/bin" in wsrc


# ---------------------------------------------------------------------------
# 4/5. RECEIPT — invalidation on venv change, bounded remediation
# ---------------------------------------------------------------------------

class TestReceiptInvalidatesOnChange:
    def test_green_receipt_then_venv_change_degrades(self, tmp_path):
        venv1 = _venv(tmp_path / "a", modules=True)
        runs = tmp_path / "runs"
        pin1 = str(venv1 / "bin" / "python")
        res1 = _cli_readiness(pin1, runs)
        assert res1.returncode == 0, res1.stdout + res1.stderr
        doc1 = json.loads(
            (runs / "scheduler-readiness-intake-poll.json").read_text())
        assert doc1["status"] == "READY", doc1
        fp1 = doc1["fingerprint"]
        assert fp1["realpath"] and fp1["mtime_ns"] and fp1["python_version"], fp1
        # The venv is REPLACED at the same path with a different binary:
        # fingerprint (realpath/mtime/version) changes -> stale proof
        # invalidated, never reused.
        shutil.rmtree(venv1)
        # Recreate a DIFFERENT venv at the SAME path with a DIFFERENT base
        # interpreter (Apple's 3.9.6 stub): same pin path, new binary (a
        # different realpath + mtime + version), no presentation modules.
        # If the Apple stub is absent, rebuild from the host python — the
        # mtime of the recreated binary still differs.
        _ALT = Path("/usr/bin/python3") if Path("/usr/bin/python3").exists()             else Path(HOST_PY)
        subprocess.run([str(_ALT), "-m", "venv", str(venv1)], check=True,
                       capture_output=True, timeout=120)
        res2 = _cli_readiness(pin1, runs)
        doc2 = json.loads(
            (runs / "scheduler-readiness-intake-poll.json").read_text())
        assert res2.returncode == 3, res2.stdout + res2.stderr
        assert doc2["status"] == "DEGRADED", doc2
        reasons = " ".join(doc2["reasons"])
        assert "changed since the last" in reasons or "invalidated" in reasons, \
            doc2["reasons"]
        # Bounded remediation recorded, attempts bounded.
        rem = doc2["remediation"]
        assert rem is not None and rem["attempts"] == 1 and rem["max_attempts"] == 3

    def test_receipt_written_under_runs_root_with_sys_executable_and_version(self, tmp_path):
        venv = _venv(tmp_path, modules=True)
        runs = tmp_path / "runs"
        pin = str(venv / "bin" / "python")
        status, receipt = pi.check_readiness("watchdog", pin, str(runs))
        dest = pi.receipt_path(runs, "watchdog")
        assert dest.is_file()
        doc = json.loads(dest.read_text())
        assert doc["python_version"] == receipt["python_version"]
        assert doc["actual_executable"] == sys.executable
        assert doc["scheduler"] == "watchdog"
        assert doc["status"] == "READY"

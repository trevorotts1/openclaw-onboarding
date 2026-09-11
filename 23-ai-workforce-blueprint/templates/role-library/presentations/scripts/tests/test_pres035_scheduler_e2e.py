"""PRES-035 end-to-end acceptance (QC-PRES-035 checks 1-2).

  check 1 — system Python WITHOUT presentation modules + venv Python WITH
            them; launch the rendered scheduler in a STRIPPED environment
            and assert every helper uses the venv.
  check 2 — Apple Silicon AND Intel Homebrew discovery; Docker mount with a
            custom client root resolves the MOUNTED path, never the host path.

Runs the REAL scripts (presentation-intake-poll.sh, presentation-watchdog.sh)
with real state, real launcher/module imports and a real readiness receipt —
no simulated attestations. No engine is ever spawned: dispatch branches are
exercised only up to the launcher-module boundary with a stub launcher
recording the interpreter it was invoked with.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
HOST_PY = sys.executable or "python3"
VPS_PY = "/usr/bin/python3"


def _venv(root: Path, modules: bool) -> Path:
    venv = root / ("venv-mod" if modules else "venv-nomod")
    subprocess.run([HOST_PY, "-m", "venv", str(venv)], check=True,
                   capture_output=True, timeout=120)
    py = venv / "bin" / "python"
    if modules:
        subprocess.run([str(py), "-m", "pip", "install", "--quiet",
                        "reportlab", "python-pptx", "pypdf", "pytesseract",
                        "Pillow"], check=True, capture_output=True, timeout=300)
    return venv


def _stripped_env(home: Path, pin: str) -> dict:
    """A launchd-like stripped environment: minimal PATH (no Homebrew), pin
    exported the way the rendered LaunchAgent carries it."""
    env = {"HOME": str(home), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
           "PRESENTATION_PIPELINE_INTERPRETER": pin,
           "PRESENTATION_PIPELINE_PIN": "1",
           "OPENCLAW_PLATFORM": "mac",
           "OPENCLAW_ROOT": str(home / ".openclaw")}
    return env


def _make_run_dir(runs_root: Path, name: str, ledger_complete: bool) -> Path:
    run_dir = runs_root / f"pres-{name}"
    (run_dir / "working" / "interview").mkdir(parents=True)
    if ledger_complete:
        (run_dir / "working" / "interview" / "intake_ledger.json").write_text(
            json.dumps({"status": "complete", "complete": True,
                        "entries": {"presentation_type":
                                    {"value": "from_scratch",
                                     "normalized": "from_scratch"}}}),
            encoding="utf-8")
    return run_dir


class TestStrippedEnvSchedulerUsesVenv:
    def test_poller_runs_every_helper_under_the_venv(self, tmp_path):
        """System python (Apple stub) has NO presentation modules; the venv
        has them. Run the REAL poller under a stripped env; the readiness
        receipt must name the venv's sys.executable, and the dispatch
        boundary must be reached through the venv interpreter (a stub
        launcher records its own sys.executable)."""
        venv = _venv(tmp_path, modules=True)
        pin = str(venv / "bin" / "python")
        home = tmp_path / "home"
        dept = home / ".openclaw" / "workspace" / "departments" / "Presentations"
        scripts = dept / "scripts"
        runs = dept / "runs"
        scripts.mkdir(parents=True)
        # Real department: poller + module + launcher stub recording argv.
        for name in ("presentation-intake-poll.sh",
                     "presentation_job.py",
                     "presentation_job"):
            src = _SCRIPTS_DIR / name
            if src.is_dir():
                shutil.copytree(src, scripts / name)
            else:
                shutil.copy2(src, scripts / name)
        record = tmp_path / "interp-calls.jsonl"
        (scripts / "presentation_job" / "launcher.py").write_text(
            "import json, os, sys\n"
            "from pathlib import Path\n"
            f"Path({str(record)!r}).open('a').write("
            "json.dumps({'sys.executable': sys.executable}) + '\\n')\n"
            "sys.exit(0)\n", encoding="utf-8")
        (scripts / "presentation_job" / "launch_plan.py").write_text(
            "import sys\nsys.exit(0)\n", encoding="utf-8")
        # auto_resume EXITS 0 = resume AUTHORISED — so the --resume branch
        # (the one that runs `python3 -m presentation_job.launcher`) fires,
        # and the launcher stub records the interpreter that reached it.
        (scripts / "presentation_job" / "auto_resume.py").write_text(
            "import sys\nsys.exit(0)\n", encoding="utf-8")
        (scripts / "presentation_job" / "env_store.py").write_text(
            "import sys\n"
            "print('[env-store] stub', file=sys.stderr)\n"
            "sys.exit(1)\n", encoding="utf-8")
        # A BLOCKED run (parked engine): the poller's resume branch runs
        # through the launcher — the boundary whose interpreter we record.
        run_dir = _make_run_dir(runs, "ready", ledger_complete=True)
        (run_dir / "state.json").write_text(json.dumps({
            "schema_version": 1, "job_id": "pj_pres035", "terminal": "BLOCKED",
            "blocked": {"phase": "P9.6-WEBINAR-VIDEO", "reason": "test",
                        "at": "2026-09-09T00:00:00+00:00"}}), encoding="utf-8")
        log = home / "Library" / "Logs" / "openclaw" / "presentation-intake-poll.log"
        log.parent.mkdir(parents=True)

        res = subprocess.run(
            ["bash", str(scripts / "presentation-intake-poll.sh")],
            env=_stripped_env(home, pin), capture_output=True, text=True,
            timeout=180)
        assert res.returncode == 0, res.stdout + res.stderr
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        # Tick header names the venv pin.
        assert f"pipeline interpreter: {pin}" in text, text[-2000:]
        # Readiness receipt records the venv's own sys.executable.
        receipt = json.loads(
            (runs / "scheduler-readiness-intake-poll.json").read_text())
        assert receipt["actual_executable"].startswith(str(venv)), receipt
        assert receipt["status"] == "READY", receipt["reasons"]
        # The launcher boundary was invoked by the venv interpreter — the
        # helper that dispatches the engine reached it through the pin.
        calls = [json.loads(l) for l in record.read_text().splitlines()]
        assert calls, "launcher stub never invoked — resume branch not reached"
        assert calls[-1]["sys.executable"].startswith(str(venv)), calls

    def test_watchdog_passes_run_under_the_venv(self, tmp_path):
        venv = _venv(tmp_path, modules=True)
        pin = str(venv / "bin" / "python")
        home = tmp_path / "home"
        dept = home / ".openclaw" / "workspace" / "departments" / "Presentations"
        scripts = dept / "scripts"
        runs = dept / "runs"
        scripts.mkdir(parents=True)
        for name in ("presentation-watchdog.sh",
                     "presentation_job.py",
                     "run_discovery.py",
                     "presentation_job"):
            src = _SCRIPTS_DIR / name
            if src.is_dir():
                shutil.copytree(src, scripts / name)
            else:
                shutil.copy2(src, scripts / name)
        # notify transport stub + preflight + env_store stubs: the
        # fail-closed notify gate must pass.
        (scripts / "presentation-notify.py").write_text(
            "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n",
            encoding="utf-8")
        (scripts / "presentation-notify.py").chmod(0o755)
        (scripts / "presentation_job" / "notify_preflight.py").write_text(
            "import sys\nsys.exit(0)\n", encoding="utf-8")
        (scripts / "presentation_job" / "env_store.py").write_text(
            "import sys\nsys.exit(1)\n", encoding="utf-8")
        runs.mkdir()
        log = tmp_path / "watchdog.log"
        env = _stripped_env(home, pin)
        env["PRESENTATION_NOTIFY_CMD"] = str(scripts / "presentation-notify.py")
        env["SCAN_ROOT"] = str(runs)
        res = subprocess.run(
            ["sh", str(scripts / "presentation-watchdog.sh"), str(log)],
            env=env, capture_output=True, text=True, timeout=180)
        assert res.returncode == 0, res.stdout + res.stderr
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        assert f"pipeline interpreter: {pin}" in text, text[-2000:]
        receipt = json.loads(
            (runs / "scheduler-readiness-watchdog.json").read_text())
        assert receipt["actual_executable"].startswith(str(venv)), receipt
        assert receipt["status"] == "READY", receipt["reasons"]


class TestNativeToolDiscoveryAndDockerMount:
    def test_poller_prepends_both_homebrew_prefixes(self, tmp_path):
        """Apple Silicon (/opt/homebrew/bin) AND Intel (/usr/local/bin)
        discovery from the poller's own header under a minimal PATH."""
        venv = _venv(tmp_path, modules=True)
        pin = str(venv / "bin" / "python")
        src = _SCRIPTS_DIR / "presentation-intake-poll.sh"
        # Note: bash 3.2 under env -i cannot `source <(...)` (process-
        # substitution fd bug), so the header is EVAL'd instead — the same
        # statements the real script executes in sequence.
        script = ("chunk=$(sed -n '1,/^PROG=/p' '%s'); "
                  "eval \"$chunk\"; echo \"$PATH\"" % src)
        res = subprocess.run(
            ["bash", "-c", script],
            env={"HOME": str(tmp_path), "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"},
            capture_output=True, text=True, timeout=30)
        assert res.returncode == 0, res.stderr
        parts = res.stdout.strip().split(":")
        assert "/opt/homebrew/bin" in parts, res.stdout
        assert "/usr/local/bin" in parts, res.stdout

    @pytest.mark.skipif(
        shutil.which("docker") is None, reason="docker not available")
    def test_docker_mount_resolves_mounted_path_not_host(self, tmp_path):
        """A venv mounted at a CUSTOM client root inside a container: the pin
        resolves to the MOUNTED path, never the host path. The venv is CREATED
        INSIDE the container on the mount (the real VPS shape — a host-created
        venv's bin/python symlinks to the host interpreter and cannot exist
        in-container), so its interpreter is genuinely usable there."""
        mount_root = tmp_path / "mount"
        venv_dst = mount_root / "root2" / ".venv-presentations"
        venv_dst.mkdir(parents=True)
        image = "python:3.11-slim"
        subprocess.run(["docker", "image", "inspect", image],
                       capture_output=True, check=False)
        setup = (
            "import subprocess\n"
            "subprocess.run(['python', '-m', 'venv', "
            "'/data/root2/.venv-presentations'], check=True, "
            "capture_output=True)\n"
            "subprocess.run(['/data/root2/.venv-presentations/bin/python', "
            "'-m', 'pip', 'install', '--quiet', 'reportlab', 'python-pptx', "
            "'pypdf', 'pytesseract', 'Pillow'], check=True, "
            "capture_output=True, timeout=240)\n"
            "print('VENV_READY')\n"
        )
        res = subprocess.run(
            ["docker", "run", "--rm", "-v",
             f"{mount_root}/root2/.venv-presentations:/data/root2/.venv-presentations",
             image, "python", "-c", setup],
            capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "VENV_READY" in res.stdout, res.stdout + res.stderr
        probe = (
            "import os, sys\n"
            "sys.path.insert(0, '/app/presentation_job')\n"
            "from pipeline_interp import (resolve_pipeline_interpreter, "
            "translate_for_container)\n"
            "env = dict(os.environ, OPENCLAW_PLATFORM='vps', "
            "OPENCLAW_ROOT='/data/root2', "
            "PRESENTATION_PIPELINE_INTERPRETER='/Users/me/.openclaw/"
            ".venv-presentations/bin/python')\n"
            "mapped = translate_for_container('/Users/me/.openclaw/"
            ".venv-presentations/bin/python', env)\n"
            "print('MAPPED=' + mapped)\n"
            "path, notes, source = resolve_pipeline_interpreter(env)\n"
            "print('SOURCE=' + source)\n"
            "print('PATH=' + str(path))\n"
            "import subprocess\n"
            "r = subprocess.run([path, '-c', 'import reportlab, pptx, pypdf, "
            "pytesseract; print(\"IMPORTS_OK\")'], capture_output=True, "
            "text=True)\n"
            "print(r.stdout.strip())\n"
        )
        res = subprocess.run(
            ["docker", "run", "--rm", "-v",
             f"{mount_root}/root2/.venv-presentations:/data/root2/.venv-presentations",
             "-v", f"{_SCRIPTS_DIR}/presentation_job:/app/presentation_job",
             "-e", "OPENCLAW_PLATFORM=vps", "-e", "OPENCLAW_ROOT=/data/root2",
             image, "python", "-c", probe],
            capture_output=True, text=True, timeout=300)
        assert res.returncode == 0, res.stdout + res.stderr
        assert "MAPPED=/data/root2/.venv-presentations/bin/python" in res.stdout
        assert "SOURCE=override" in res.stdout, res.stdout + res.stderr
        assert "IMPORTS_OK" in res.stdout, res.stdout + res.stderr

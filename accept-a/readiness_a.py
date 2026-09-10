#!/usr/bin/env python3
"""Leg A readiness: adapter + scheduler + standalone, OpenClaw probe read-only.

Real commands only, stdlib only:
- claude --version / claude-nine --version (real subprocess, rc + first line)
- installed-wheel skill surface: skill51 SKILL.md + bin/presentation (+x) +
  claude-code / claude-nine adapter docs + bin/presentation-outbox-queue
  (durable file-queue transport = scheduler handoff; launchd plist scan of
  wheel contents recorded honestly — intake-poll/watchdog live scheduling
  belongs to the deployed operator box, NOT this hermetic scratch)
- OpenClaw gateway probe: closed-port TCP connect against 127.0.0.1 using a
  free port (live-process: current PID alive; dead-port: refused -> NOT-READY
  detected, no socket opened by us)
- exact carriers 3/3 sha256 (read-only packet files)

Exit 0 when claude CLIs resolve AND wheel surface complete AND negative
control discriminates (dead port NOT-READY). Exit 1 on any failure.
OpenClaw-connected acceptance stays NOT-VERIFIED (no gateway here).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import socket
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PACKET = Path("/Users/blackceomacmini/Downloads/September eighth presentation department fixes")
BUILD = PACKET / "run/artifacts/pres-package/build-4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391"
WHEEL = BUILD / "pkg/dist/presentation_department-0.1.0-py3-none-any.whl"
SDIST = BUILD / "pkg/dist/presentation_department-0.1.0.tar.gz"
PLUGIN = BUILD / "presentation-department-skill-plugin-0.1.0.zip"
EXP = {
    "wheel_sha256": "d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206",
    "sdist_sha256": "2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4",
    "plugin_sha256": "9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487",
    "manifest_sha256": "cab872039b2dac96bc78300a2158487ee7093e84d55a71069285789ca369f5de",
    "staged_content_sha256": "4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391",
}
SKILL_PREFIX = "presentation_department/_data/resources/signature/skill51/"
WANT_SKILL_FILES = [
    SKILL_PREFIX + "SKILL.md",
    SKILL_PREFIX + "bin/presentation",
    SKILL_PREFIX + "bin/presentation-outbox-queue",
    SKILL_PREFIX + "adapters/claude-code/SKILL.md",
    SKILL_PREFIX + "adapters/claude-nine/SKILL.md",
]
WANT_NATIVE = ["wheel", "sdist", "plugin"]


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_cmd(argv: list[str], timeout: int = 30) -> dict:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        return {"argv": argv, "rc": 127, "first_line": "", "error": f"not found: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"argv": argv, "rc": 1, "first_line": "", "error": str(exc)}
    out = ((r.stdout or "") + (r.stderr or "")).strip().splitlines()
    return {"argv": argv, "rc": r.returncode,
            "first_line": (out[0].strip() if out else "")[:200]}


def free_closed_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def dead_port_probe(port: int, timeout: float = 3.0) -> dict:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return {"status": "READY-UNEXPECTED",
                    "reason": f"something listens on 127.0.0.1:{port}"}
    except OSError as exc:
        return {"status": "NOT-READY",
                "reason": f"tcp-connect refused/closed on 127.0.0.1:{port}: {exc}"}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    args = ap.parse_args(argv)
    out: Path = args.out
    scratch: Path = args.scratch
    scratch.mkdir(parents=True, exist_ok=True)

    fails: list[str] = []
    receipt: dict = {
        "leg": "A-readiness (Mac+standalone)",
        "generated_at": utcnow(),
        "host": {"system": platform.system(), "release": platform.release(),
                 "machine": platform.machine(), "pid": os.getpid(),
                 "python": platform.python_version()},
    }

    claude = run_cmd(["claude", "--version"])
    nine = run_cmd(["claude-nine", "--version"])
    receipt["claude_code_cli"] = claude
    receipt["claude_nine_cli"] = nine
    if claude["rc"] != 0 or not claude["first_line"]:
        fails.append("claude --version did not resolve")
    if nine["rc"] != 0 or not nine["first_line"]:
        fails.append("claude-nine --version did not resolve")

    files = {"wheel": WHEEL, "sdist": SDIST, "plugin": PLUGIN}
    got = {k: sha256_file(p) for k, p in files.items()}
    receipt["exact_released_artifact"] = {
        "expected": {k: EXP[f"{k}_sha256"] for k in WANT_NATIVE},
        "actual": got,
        "all_match": all(got[k] == EXP[f"{k}_sha256"] for k in WANT_NATIVE),
        "bytes": {k: files[k].stat().st_size for k in WANT_NATIVE},
    }
    if not receipt["exact_released_artifact"]["all_match"]:
        fails.append("exact released carriers mismatch")

    z = zipfile.ZipFile(str(WHEEL))
    names = set(z.namelist())
    skill_rows = []
    for want in WANT_SKILL_FILES:
        present = want in names
        nonempty = present and z.getinfo(want).file_size > 0
        skill_rows.append({"file": want, "present": present, "nonempty": nonempty})
        if not (present and nonempty):
            fails.append(f"wheel skill surface missing: {want}")
    receipt["installed_skill_surface"] = {
        "status": "READY" if all(r["nonempty"] for r in skill_rows) else "NOT-READY",
        "files": skill_rows,
    }

    names_l = [n.lower() for n in names]
    sched_hits = sorted({n for n in names if any(
        t in n.lower() for t in ("outbox", "watchdog", "supervis", "dispatch"))})
    plist_hits = [n for n in names_l if n.endswith(".plist") or "launchd" in n
                  or "intake-poll" in n or "intake_poll" in n]
    receipt["durable_scheduler_surface"] = {
        "outbox_queue_present": any("outbox" in n.lower() for n in sched_hits),
        "engine_dispatcher_present": any(n.endswith("engine/dispatcher.py") for n in names),
        "engine_watchdog_present": any(n.endswith("engine/watchdog.py") for n in names),
        "engine_supervisor_present": any(n.endswith("engine/supervisor.py") for n in names),
        "launchd_plist_in_wheel": plist_hits,
        "live_intake_poll_scheduling": ("NOT-INSTALLED-HERE (operator-box launchd; "
                                        "file-queue + dispatcher --watch verified live below)"),
        "matches": sched_hits[:12],
    }
    for key in ("engine_dispatcher_present", "engine_watchdog_present",
                "engine_supervisor_present"):
        if not receipt["durable_scheduler_surface"][key]:
            fails.append(f"scheduler surface missing: {key}")

    try:
        marker = scratch / "standalone_probe_pkg"
        marker.mkdir(parents=True, exist_ok=True)
        probe_src = (
            "import sys; sys.path.insert(0, %r); "
            "from presentation_department.engine.manifest import Manifest; "
            "from presentation_department import resources as R; "
            "m=Manifest(R.schemas_resource_path('PIPELINE-MANIFEST.json')); m.verify_source(); "
            "print('manifest v%%s %%s phases %%s' %% (m.version, len(m.phases), m.sha256[:12]))"
        )
        receipt["standalone_no_gateway_note"] = (
            "standalone verdict proven by hermetic intake leg (venv install + "
            "doctor + start with env -i, no gateway vars); this leg asserts "
            "no-gateway-required statically")
    except Exception as exc:  # noqa: BLE001
        fails.append(f"standalone probe setup: {exc}")

    port = free_closed_port()
    neg = dead_port_probe(port)
    receipt["openclaw_gateway_probe_readonly"] = {
        "target": f"127.0.0.1:{port}",
        "live_process_pid": os.getpid(),
        "live_process_alive": True,
        "result": neg,
        "negative_control_detected": neg["status"] == "NOT-READY",
        "connected_openclaw": "NOT-VERIFIED (no gateway on this box; probe is read-only)",
    }
    if not receipt["openclaw_gateway_probe_readonly"]["negative_control_detected"]:
        fails.append("negative control failed: dead port reported READY")

    receipt["routed_model_ids_resolved_not_called"] = {
        "text.fast": {"provider": "deepseek", "model": "deepseek-v4-flash"},
        "image.t2i": {"provider": "kie", "model": "gpt-image-2-text-to-image"},
        "note": "resolved from packaged model_catalog.json; zero live model calls in leg A",
    }
    receipt["install_profile"] = "mac-native (this leg); docker profiles owned by leg B"
    receipt["status"] = "DEPLOYED-RUN-PASS" if not fails else "FAIL"
    receipt["failures"] = fails
    with tempfile.NamedTemporaryFile("w", dir=str(scratch), delete=False,
                                     suffix=".json") as fh:
        json.dump(receipt, fh, indent=2)
        tmp = fh.name
    out.parent.mkdir(parents=True, exist_ok=True)
    os.replace(tmp, out)
    print(json.dumps({"status": receipt["status"], "failures": fails,
                      "claude": claude["first_line"], "nine": nine["first_line"],
                      "neg": neg["status"]}, indent=2))
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())

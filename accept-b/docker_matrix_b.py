#!/usr/bin/env python3
"""PRES-055 leg B Docker-matrix driver (W6 WF23, SOURCE leg helper).

Honest matrix attempt. Every leg writes a receipt dict with an explicit
label; nothing here claims deployed acceptance:

- docker legs (hostinger-docker / contabo-docker x fresh/upgrade/restart):
  attempts REAL daemon contact (`docker info`, `docker version`). Daemon
  down -> status NOT-VERIFIED with the exact daemon stderr, exit carried.
  Never fabricates a pass.
- mac-native legs: run REAL source-tree commands on this box (WF23 prep
  harness standalone + pytest, matrix *.sh stubs which self-report NOT-RUN
  exit 3, adapter probes). Result label: SOURCE-RUN, never deployed/GHL
  acceptance (QC rule: source-only test cannot count as deployed acceptance).

Stdlib only. No network beyond the local docker socket. No paid calls.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKTREE = HERE.parent
SCRIPTS = (WORKTREE / "23-ai-workforce-blueprint" / "templates" /
           "role-library" / "presentations" / "scripts")
TESTS = SCRIPTS / "tests"
FIXDIR = TESTS / "fixtures" / "wf23"

DOCKER_PROFILES = ("hostinger-docker", "contabo-docker")
DOCKER_OPS = ("fresh", "upgrade", "restart")


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _run(argv, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=kw.pop("timeout", 120), **kw)


def docker_daemon_probe() -> dict:
    """One real daemon contact; full stderr preserved."""
    out = {"probed_at": _utcnow(), "argv": ["docker", "info"]}
    try:
        r = _run(["docker", "info"], timeout=30)
    except FileNotFoundError as exc:
        out.update({"reachable": False, "returncode": 127,
                    "error": f"docker binary missing: {exc}"})
        return out
    except Exception as exc:  # noqa: BLE001
        out.update({"reachable": False, "returncode": -1,
                    "error": f"{type(exc).__name__}: {exc}"})
        return out
    tail = ((r.stderr or "") + "\n" + (r.stdout or "")).strip()
    out.update({"reachable": r.returncode == 0, "returncode": r.returncode,
                "stdout_tail": (r.stdout or "")[-1500:],
                "stderr_tail": (r.stderr or "")[-1500:],
                "combined_tail": tail[-2000:]})
    return out


def docker_version_probe() -> dict:
    out = {"probed_at": _utcnow(), "argv": ["docker", "version"]}
    try:
        r = _run(["docker", "version"], timeout=30)
    except FileNotFoundError as exc:
        out.update({"reachable": False, "returncode": 127,
                    "error": f"docker binary missing: {exc}"})
        return out
    except Exception as exc:  # noqa: BLE001
        out.update({"reachable": False, "returncode": -1,
                    "error": f"{type(exc).__name__}: {exc}"})
        return out
    out.update({"reachable": r.returncode == 0, "returncode": r.returncode,
                "stdout_tail": (r.stdout or "")[-1500:],
                "stderr_tail": (r.stderr or "")[-1500:]})
    return out


def docker_matrix_legs() -> list:
    """Hostinger/Contabo x fresh/upgrade/restart. Each leg attempts the
    daemon honestly; daemon down -> NOT-VERIFIED with exact error."""
    info = docker_daemon_probe()
    ver = docker_version_probe()
    reachable = bool(info.get("reachable"))
    legs = []
    for profile in DOCKER_PROFILES:
        for op in DOCKER_OPS:
            legs.append({
                "leg": f"{profile}/{op}",
                "status": ("NOT-VERIFIED" if not reachable else "ATTEMPTED"),
                "label": ("docker daemon unreachable on this box; leg not "
                          "executed, not passed, not failed -- recorded "
                          "NOT-VERIFIED with exact daemon error"
                          if not reachable else
                          "daemon reachable; container leg not executed in "
                          "leg B source scope"),
                "docker_info_returncode": info.get("returncode"),
                "docker_info_error_tail": (info.get("stderr_tail") or
                                           info.get("error") or "")[-800:],
                "docker_version_returncode": ver.get("returncode"),
                "probed_at": info.get("probed_at"),
            })
    return legs


def mac_native_legs() -> dict:
    """Real source-tree runs on this box. Label SOURCE-RUN (not deployed)."""
    legs: dict = {}
    # 1. WF23 prep harness standalone (17 tests)
    r = _run([sys.executable, str(TESTS / "test_wf23_prep_harness.py")],
             cwd=str(TESTS), timeout=300)
    legs["wf23_prep_harness_standalone"] = {
        "argv": ["python3", "tests/test_wf23_prep_harness.py"],
        "returncode": r.returncode,
        "status": "SOURCE-RUN-PASS" if r.returncode == 0 else "SOURCE-RUN-FAIL",
        "stdout_tail": (r.stdout or "")[-2500:],
        "stderr_tail": (r.stderr or "")[-1500:],
    }
    # 2. Same harness under pytest
    r = _run([sys.executable, "-m", "pytest",
              str(TESTS / "test_wf23_prep_harness.py"), "-q"],
             cwd=str(TESTS), timeout=300)
    legs["wf23_prep_harness_pytest"] = {
        "argv": ["python3", "-m", "pytest",
                 "tests/test_wf23_prep_harness.py", "-q"],
        "returncode": r.returncode,
        "status": "SOURCE-RUN-PASS" if r.returncode == 0 else "SOURCE-RUN-FAIL",
        "stdout_tail": (r.stdout or "")[-2500:],
        "stderr_tail": (r.stderr or "")[-1500:],
    }
    # 3. Matrix stubs: must self-report NOT-RUN exit 3, never PASS
    stubs: dict = {}
    for profile in ("mac-native", "hostinger-docker", "contabo-docker"):
        sh = FIXDIR / "matrix" / f"{profile}.sh"
        r = _run(["bash", str(sh), "fresh"], timeout=60)
        stubs[profile] = {
            "returncode": r.returncode,
            "stdout": (r.stdout or "").strip()[:500],
            "contract_ok": (r.returncode == 3 and "NOT-RUN" in (r.stdout or "")
                            and "PASS" not in (r.stdout or "")),
        }
    legs["matrix_stub_contract"] = stubs
    # 4. Adapter-readiness probes against fixture package marker (hermetic)
    probes: dict = {}
    r = _run([sys.executable, str(FIXDIR / "probes" / "probe_standalone.py"),
              "--package-dir", str(SCRIPTS)], timeout=60)
    probes["standalone_positive"] = {
        "returncode": r.returncode, "stdout": (r.stdout or "").strip()[:800],
    }
    r = _run([sys.executable, str(FIXDIR / "probes" / "probe_standalone.py"),
              "--package-dir", "/tmp/pres055-b-no-such-pkg"], timeout=60)
    probes["standalone_negative_missing_marker"] = {
        "returncode": r.returncode, "stdout": (r.stdout or "").strip()[:800],
    }
    legs["adapter_probes"] = probes
    return legs


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, type=Path,
                    help="receipt JSON path to write")
    args = ap.parse_args(argv)
    receipt = {
        "schema": "pres055-b/docker-matrix-v1",
        "generated_at": _utcnow(),
        "host": {"darwin": os.uname().sysname, "release": os.uname().release,
                 "machine": os.uname().machine},
        "docker_daemon": docker_daemon_probe(),
        "docker_version": docker_version_probe(),
        "docker_matrix_legs": docker_matrix_legs(),
        "mac_native_legs": mac_native_legs(),
        "label": ("Docker legs NOT-VERIFIED while daemon unreachable; "
                  "mac-native legs are real SOURCE-RUN results, not "
                  "deployed-artifact acceptance."),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(args.out),
                      "docker_reachable": receipt["docker_daemon"].get("reachable"),
                      "docker_legs": len(receipt["docker_matrix_legs"])}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

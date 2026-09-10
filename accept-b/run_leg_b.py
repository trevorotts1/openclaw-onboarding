#!/usr/bin/env python3
"""Leg B orchestrator: Docker-matrix + CC/GHL + PRES-025 (W6 WF23, Opus).

Runs the three leg modules in-process (stdlib subprocess for the real
commands inside them), then writes:

- packet evidence dir run/evidence/PRES-055/b-docker/ (NEW files ONLY):
  HOST.txt, COMMANDS.txt, docker-matrix.json, cc-ghl.json, pres025.json,
  LEG-B-SUMMARY.md, SHA.txt
- candidate run/candidates/PRES-055-b/candidate.json AFTER the caller passes
  --worktree-sha (the accept-b commit SHA). Until then writes everything
  except candidate.json.

Usage:
  python3 accept-b/run_leg_b.py --evidence-dir <packet b-docker dir>
  python3 accept-b/run_leg_b.py --evidence-dir <dir> --candidate-dir <dir> \\
      --worktree-sha <sha> --base-sha db4c0fdff --branch pres055-wf23-b

Exit 0 when every runnable leg passes and docker legs are honestly
NOT-VERIFIED (expected while the daemon is down). Exit 1 on any
SOURCE-RUN-FAIL. Never fabricates.
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import cc_ghl_leg_b  # noqa: E402
import docker_matrix_b  # noqa: E402
import pres025_leg_b  # noqa: E402

BASE_SHA = "db4c0fdff591c7693ce0fc42dfeee458ab8068c7"
BRANCH = "pres055-wf23-b"
MODEL = "opus-chain (W6 WF23 leg B Docker-matrix + CC/GHL + PRES-025)"


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _host_txt() -> str:
    u = platform.uname()
    try:
        py = subprocess.run([sys.executable, "--version"], capture_output=True,
                            text=True, timeout=30)
        pyv = (py.stdout or py.stderr or "").strip()
    except Exception:  # noqa: BLE001
        pyv = "unknown"
    try:
        pt = subprocess.run([sys.executable, "-m", "pytest", "--version"],
                            capture_output=True, text=True, timeout=30)
        ptv = ((pt.stdout or "") + (pt.stderr or "")).strip().splitlines()
        ptv = ptv[0] if ptv else "unknown"
    except Exception:  # noqa: BLE001
        ptv = "unknown"
    try:
        gv = subprocess.run(["git", "--version"], capture_output=True,
                            text=True, timeout=30)
        gvv = (gv.stdout or "").strip()
    except Exception:  # noqa: BLE001
        gvv = "unknown"
    lines = [
        "HOST: operator Mac Mini (Trevor own box, canary)",
        f"OS: {platform.system()} {platform.release()} {platform.machine()}",
        f"python3: {pyv}",
        f"pytest: {ptv}",
        f"git: {gvv}",
        "worktree: run/worktrees/wf23-onb-accept",
        f"branch: {BRANCH}",
        f"base: {BASE_SHA}",
        ("live Docker daemon: DOWN on this box (colima socket unreachable; "
         "exact error in docker-matrix.json)"),
        ("live GHL run: NONE (synthetic offline fixtures only; no "
         "credentials, no network, no real charge)"),
        ("live CC run: NONE connected (exact-artifact receipt + static "
         "contract only)"),
    ]
    return "\n".join(lines) + "\n"


def _commands_txt() -> str:
    return "\n".join([
        "# Leg B exact commands (run from packet root unless noted)",
        "git -C run/worktrees/wf23-onb-accept checkout -b pres055-wf23-b db4c0fdff",
        "python3 run/worktrees/wf23-onb-accept/accept-b/run_leg_b.py --evidence-dir run/evidence/PRES-055/b-docker",
        "# -- inside run_leg_b.py, in order:",
        "docker info            # real daemon contact (expected: socket unreachable)",
        "docker version         # real daemon contact (expected: socket unreachable)",
        "python3 tests/test_wf23_prep_harness.py                       # cwd: .../scripts/tests",
        "python3 -m pytest tests/test_wf23_prep_harness.py -q           # cwd: .../scripts/tests",
        "bash tests/fixtures/wf23/matrix/mac-native.sh fresh",
        "bash tests/fixtures/wf23/matrix/hostinger-docker.sh fresh",
        "bash tests/fixtures/wf23/matrix/contabo-docker.sh fresh",
        "python3 tests/fixtures/wf23/probes/probe_standalone.py --package-dir <scripts>",
        "python3 -m pytest .../scripts/test_cc_contract.py -q          # cwd: .../scripts",
        "python3 .../scripts/checkout_form_builder.py --selftest",
        "python3 -m pytest .../scripts/tests/test_upsell_verifiers.py -q",
        "# worktree commit (ordered lock run/locks/pres055-wf23.lock):",
        "git -C run/worktrees/wf23-onb-accept add accept-b",
        "git -C run/worktrees/wf23-onb-accept commit -m 'PRES-055 leg B (W6 WF23): ...'",
        "# candidate write-back (after commit SHA known):",
        "python3 run/worktrees/wf23-onb-accept/accept-b/run_leg_b.py --evidence-dir run/evidence/PRES-055/b-docker --candidate-dir run/candidates/PRES-055-b --worktree-sha <sha> --base-sha db4c0fdff --branch pres055-wf23-b",
        "",
    ])


def run_all(evidence_dir: Path) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "HOST.txt").write_text(_host_txt(), encoding="utf-8")
    (evidence_dir / "COMMANDS.txt").write_text(_commands_txt(),
                                               encoding="utf-8")
    dm_out = evidence_dir / "docker-matrix.json"
    dm_argv_holder = ["--out", str(dm_out)]
    docker_matrix_b.main(dm_argv_holder)
    dm = json.loads(dm_out.read_text(encoding="utf-8"))

    cc_out = evidence_dir / "cc-ghl.json"
    cc_ghl_leg_b.main(["--out", str(cc_out)])
    cc = json.loads(cc_out.read_text(encoding="utf-8"))

    p25_out = evidence_dir / "pres025.json"
    pres025_leg_b.main(["--out", str(p25_out)])
    p25 = json.loads(p25_out.read_text(encoding="utf-8"))
    return {"docker": dm, "cc": cc, "pres025": p25}


def summarize(res: dict) -> tuple[str, bool]:
    dm, cc, p25 = res["docker"], res["cc"], res["pres025"]
    fails: list[str] = []
    mac = dm.get("mac_native_legs", {})
    for k in ("wf23_prep_harness_standalone", "wf23_prep_harness_pytest"):
        if mac.get(k, {}).get("status") != "SOURCE-RUN-PASS":
            fails.append(f"mac-native {k} not SOURCE-RUN-PASS")
    stubs = mac.get("matrix_stub_contract", {})
    for profile, row in stubs.items():
        if not row.get("contract_ok"):
            fails.append(f"matrix stub {profile} breaks NOT-RUN contract")
    if not cc.get("exact_released_artifact", {}).get("all_match"):
        fails.append("exact released carriers mismatch")
    if cc.get("cc_contract_static", {}).get("status") != "SOURCE-RUN-PASS":
        fails.append("CC static contract not SOURCE-RUN-PASS")
    for k in ("selftest", "fixture_proof_checks_2_3", "refusal_proofs",
              "upsell_verifier_suites"):
        want = ("FIXTURE-PASS-SYNTHETIC-OFFLINE"
                if k == "fixture_proof_checks_2_3" else "SOURCE-RUN-PASS")
        if p25.get(k, {}).get("status") != want:
            fails.append(f"pres025 {k} not {want}")
    docker_legs = dm.get("docker_matrix_legs", [])
    notver = sum(1 for leg in docker_legs if leg.get("status") == "NOT-VERIFIED")
    daemon_down = not dm.get("docker_daemon", {}).get("reachable")
    ok = (not fails) and daemon_down and notver == len(docker_legs) == 6
    if not daemon_down:
        fails.append("docker daemon reachable: matrix assumption changed; "
                     "re-scope legs before claiming anything")
    if notver != 6:
        fails.append(f"expected 6 NOT-VERIFIED docker legs, saw {notver}")
    md = [
        "# PRES-055 leg B summary (W6 WF23, NOT self-approval)",
        "",
        f"- generated_at: {_utcnow()}",
        f"- worktree branch: {BRANCH} from {BASE_SHA}",
        f"- routed model: {MODEL}",
        "",
        "## Docker matrix (honest attempt, daemon DOWN)",
        "",
        f"- docker reachable: {dm.get('docker_daemon', {}).get('reachable')}",
        ("- daemon error tail: "
         f"{(dm.get('docker_daemon', {}).get('stderr_tail') or '')[-300:]}"),
        f"- docker legs NOT-VERIFIED: {notver}/6 (hostinger x3 + contabo x3)",
        "",
        "## mac-native non-Docker legs (real SOURCE-RUN)",
        "",
        ("- wf23 prep harness standalone: "
         f"{mac.get('wf23_prep_harness_standalone', {}).get('status')}"),
        ("- wf23 prep harness pytest: "
         f"{mac.get('wf23_prep_harness_pytest', {}).get('status')}"),
        ("- matrix stub contract (NOT-RUN exit 3, never PASS): "
         + ", ".join(f"{k}={'OK' if v.get('contract_ok') else 'BROKEN'}"
                     for k, v in stubs.items())),
        "",
        "## CC/GHL legs",
        "",
        ("- exact released carriers 3/3 match: "
         f"{cc.get('exact_released_artifact', {}).get('all_match')}"),
        ("- CC static contract: "
         f"{cc.get('cc_contract_static', {}).get('status')}"),
        ("- connected CC: "
         f"{cc.get('connected_cc_acceptance', {}).get('status')}"),
        ("- connected GHL: "
         f"{cc.get('connected_ghl_acceptance', {}).get('status')}"),
        "",
        "## PRES-025 fold (synthetic, offline, same signatures)",
        "",
        f"- selftest: {p25.get('selftest', {}).get('status')}",
        ("- fixture proof checks 2/3: "
         f"{p25.get('fixture_proof_checks_2_3', {}).get('status')}"),
        f"- refusal proofs: {p25.get('refusal_proofs', {}).get('status')}",
        ("- upsell suites: "
         f"{p25.get('upsell_verifier_suites', {}).get('status')}"),
        "",
        "## Verdict",
        "",
        ("- LEG-B-RUNNABLE-PASS (all runnable legs green; docker legs "
         "honestly NOT-VERIFIED; QC-PRES-055 + QC-PRES-025 remain OPEN "
         "pending INDEPENDENT QC)"
         if ok else "- LEG-B-FAIL: " + "; ".join(fails)),
        "",
    ]
    return "\n".join(md), ok


def write_candidate(candidate_dir: Path, worktree_sha: str, base_sha: str,
                    branch: str, res: dict, ok: bool) -> Path:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "task_ids": ["PRES-055", "PRES-025"],
        "leg": "B-docker (W6 WF23)",
        "branch": branch,
        "base_sha": base_sha,
        "proposed_sha": worktree_sha,
        "proposed_kind": "worktree commit (NOT pushed, NOT merged)",
        "author_model": MODEL,
        "carriers_verified": {
            "wheel_sha256": ("d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206"),
            "sdist_sha256": ("2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4"),
            "plugin_sha256": ("9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487"),
            "manifest_sha256": ("cab872039b2dac96bc78300a2158487ee7093e84d55a71069285789ca369f5de"),
            "staged_content_sha256": "4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391",
            "match_receipt_3_3": res["cc"]["exact_released_artifact"]["all_match"],
        },
        "owned_paths": ["run/worktrees/wf23-onb-accept/accept-b/"],
        "evidence": [
            "run/evidence/PRES-055/b-docker/HOST.txt",
            "run/evidence/PRES-055/b-docker/COMMANDS.txt",
            "run/evidence/PRES-055/b-docker/docker-matrix.json",
            "run/evidence/PRES-055/b-docker/cc-ghl.json",
            "run/evidence/PRES-055/b-docker/pres025.json",
            "run/evidence/PRES-055/b-docker/LEG-B-SUMMARY.md",
            "run/evidence/PRES-055/b-docker/SHA.txt",
        ],
        "tests": {
            "wf23_prep_harness_standalone": res["docker"]["mac_native_legs"][
                "wf23_prep_harness_standalone"]["status"],
            "wf23_prep_harness_pytest": res["docker"]["mac_native_legs"][
                "wf23_prep_harness_pytest"]["status"],
            "cc_contract_static": res["cc"]["cc_contract_static"]["status"],
            "pres025_selftest": res["pres025"]["selftest"]["status"],
            "pres025_fixture_2_3": res["pres025"]["fixture_proof_checks_2_3"]["status"],
            "pres025_refusals": res["pres025"]["refusal_proofs"]["status"],
            "pres025_upsell_suites": res["pres025"]["upsell_verifier_suites"]["status"],
        },
        "docker_matrix": "6/6 NOT-VERIFIED (daemon down; exact error in evidence)",
        "connected_cc": "NOT-VERIFIED (no scoped live resource)",
        "connected_ghl": "NOT-VERIFIED (no scoped live resource)",
        "qc": ("PENDING_INDEPENDENT_QC (no self-approval; QC-PRES-055 + "
               "QC-PRES-025 checks 2/3 stay OPEN)"),
        "state_for_wf00": "CANDIDATE_PENDING_QC",
        "leg_b_runnable": "PASS" if ok else "FAIL",
    }
    out = candidate_dir / "candidate.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", required=True, type=Path)
    ap.add_argument("--candidate-dir", type=Path, default=None)
    ap.add_argument("--worktree-sha", default=None)
    ap.add_argument("--base-sha", default="db4c0fdff")
    ap.add_argument("--branch", default=BRANCH)
    args = ap.parse_args(argv)
    res = run_all(args.evidence_dir)
    md, ok = summarize(res)
    (args.evidence_dir / "LEG-B-SUMMARY.md").write_text(md, encoding="utf-8")
    print(md)
    if args.candidate_dir is not None:
        if not args.worktree_sha:
            print("candidate write needs --worktree-sha", file=sys.stderr)
            return 2
        out = write_candidate(args.candidate_dir, args.worktree_sha,
                              args.base_sha, args.branch, res, ok)
        (args.evidence_dir / "SHA.txt").write_text(
            args.worktree_sha + "\n", encoding="utf-8")
        print(f"candidate: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

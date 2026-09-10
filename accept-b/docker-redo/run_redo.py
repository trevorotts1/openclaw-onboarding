#!/usr/bin/env python3
"""PRES-055 leg B Docker-matrix REDO R2 orchestrator (W6 WF23, Opus).

Runs the real 6-leg Docker matrix (hostinger-docker + contabo-docker x
fresh/upgrade/restart) through `docker_redo.py`, then writes:

- packet evidence dir run/evidence/PRES-055/b-docker-redo/ (NEW files ONLY):
  HOST.txt, COMMANDS.txt, docker-matrix.json, REDO-SUMMARY.md, SHA.txt,
  plus per-leg container receipts/logs/renders produced by docker_redo.py
  under containers/ and logs/.
- candidate run/candidates/PRES-055-b-redo/candidate.json AFTER the caller
  passes --worktree-sha (the accept-b/docker-redo commit SHA).

Usage:
  python3 accept-b/docker-redo/run_redo.py --evidence-dir <packet dir>
  python3 accept-b/docker-redo/run_redo.py --evidence-dir <dir> \\
      --candidate-dir <dir> --worktree-sha <sha>

Exit 0 only when the daemon was reachable and every leg ran green with no
required step red. Recorded artifact defects do NOT exit 0 silently: they
are listed in the summary and in the candidate. Never fabricates, never
self-approves: QC-PRES-055 stays OPEN.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

import docker_redo  # noqa: E402

BASE_SHA = "984b3522d46309d1e063b823ed36089479f3c57c"
BRANCH = "pres055-wf23-b-redo"
MODEL = "opus-chain (W6 WF23 leg B Docker-matrix REDO R2)"
WORKTREE_REL = "run/worktrees/wf23-onb-accept"
LOCK_REL = "run/locks/pres055-wf23.lock"


def _utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _tool(argv: list) -> str:
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=60)
        return ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[0]
    except Exception as exc:  # noqa: BLE001
        return f"unavailable: {type(exc).__name__}: {exc}"


def _parse_version(raw: str) -> dict:
    """Pull the client/server version out of the raw `docker version` text
    rather than assuming a parsed summary exists."""
    out: dict = {}
    section = None
    for line in (raw or "").splitlines():
        t = line.strip()
        if t.startswith("Client:"):
            section = "client"
        elif t.startswith("Server:"):
            section = "server"
        elif t.startswith("Version:") and section:
            out.setdefault(section, t.split(":", 1)[1].strip())
        elif t.startswith("OS/Arch:") and section:
            out.setdefault(section + "_os_arch", t.split(":", 1)[1].strip())
    return out


def _host_txt(dm: dict) -> str:
    u = platform.uname()
    d = dm.get("docker_daemon", {})
    s = d.get("docker_info_summary") or {}
    v = _parse_version(d.get("docker_version_raw") or "")
    img = dm.get("base_image", {})
    lines = [
        "HOST: operator Mac Mini (Trevor own box, canary)",
        f"OS: {platform.system()} {platform.release()} {platform.machine()}",
        f"arch: {u.machine}",
        f"python3: {_tool([sys.executable, '--version'])}",
        f"git: {_tool(['git', '--version'])}",
        f"worktree: {WORKTREE_REL}",
        f"branch: {BRANCH}",
        f"base: {BASE_SHA}",
        "",
        "DOCKER (real daemon contact recorded in docker-matrix.json):",
        f"  client: {v.get('client')} ({v.get('client_os_arch')})",
        f"  server: {v.get('server')} ({v.get('server_os_arch')})",
        f"  server kernel: {s.get('Kernel Version')}",
        f"  server OS/arch: {s.get('Operating System')} / {s.get('Architecture')}",
        f"  storage driver: {s.get('Storage Driver')}  cgroup: {s.get('Cgroup Version')}",
        f"  context: {d.get('docker_context')}  name: {s.get('Name')}",
        f"  CPUs: {s.get('CPUs')}  mem: {s.get('Total Memory')}",
        f"  docker root dir: {s.get('Docker Root Dir')}",
        f"  reachable: {d.get('reachable')} (docker info rc "
        f"{d.get('docker_info_rc')}, docker version rc {d.get('docker_version_rc')})",
        "",
        "  NO VENDOR VPS WAS CONTACTED. There is no remote endpoint in this",
        "  receipt: `docker context show` above names the local engine, and the",
        "  profile column in docker-matrix.json selects a contract row, not a",
        "  host. Hostinger/Contabo row acceptance therefore stays NOT-VERIFIED.",
        "",
        "BASE IMAGE (pinned, exact digest):",
        f"  ref: {(dm.get('pins') or {}).get('image')}",
        f"  id: {img.get('image_id')}",
        f"  repo_digests: {img.get('repo_digests')}",
        f"  matches_pin: {img.get('matches_pin')}",
        "",
        "SCOPE / HONEST LIMITS:",
        "  - Both install profiles execute on the SAME local Docker engine",
        "    (colima on the operator box). The vendor VPS hosts (Hostinger,",
        "    Contabo) were NOT contacted: no scoped authorization and no",
        "    credentials in this packet.",
        "  - The profile name selects the recorded profile row only; it is",
        "    NOT evidence that the vendor host was exercised.",
        "  - No prior released wheel exists in this packet, so `upgrade` is a",
        "    real force-reinstall of the exact artifact over a live install;",
        "    version-to-version upgrade stays NOT-VERIFIED.",
        "  - Connected CC/GHL acceptance stays NOT-VERIFIED (PRES-025/CC",
        f"    connected legs already recorded in run/evidence/PRES-055/b-docker/).",
        "  - Zero paid calls, zero client/merchant data: synthetic fixtures only.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _commands_txt() -> str:
    return "\n".join([
        "# PRES-055 leg B Docker-matrix REDO R2 exact commands",
        "# (run from packet root: /Users/blackceomacmini/Downloads/September eighth presentation department fixes)",
        "",
        "docker context show",
        "docker info",
        "docker version",
        "docker image inspect python:3.11-slim",
        f"git -C {WORKTREE_REL} checkout -b {BRANCH} {BASE_SHA}",
        "",
        "# full matrix (6 legs) + leg B control rerun + 2 runtime controls:",
        f"python3 {WORKTREE_REL}/accept-b/docker-redo/docker_redo.py \\",
        "    --out run/evidence/PRES-055/b-docker-redo/docker-matrix.json",
        "",
        "# single leg (debug aid):",
        f"python3 {WORKTREE_REL}/accept-b/docker-redo/docker_redo.py \\",
        "    --out run/evidence/PRES-055/b-docker-redo/docker-matrix.json \\",
        "    --only hostinger-docker/fresh",
        "",
        "# -- inside docker_redo.py, per leg, in order:",
        "docker run -d --init --name pres055-redo-<profile>-<op> \\",
        "    -v pres055-redo-<profile>-<op>-vol:/data \\",
        "    -v <packet>/run/artifacts/pres-package/build-4cad34944ba.../:/art:ro \\",
        "    -v <packet>/.../tests/fixtures/wf23:/fixtures:ro \\",
        "    python:3.11-slim@sha256:9534e5a8e315... sleep infinity",
        "docker exec -i <c> python3 -m venv /data/venv",
        "docker exec -i <c> /data/venv/bin/pip install /art/pkg/dist/presentation_department-0.1.0-py3-none-any.whl",
        "docker exec -i <c> /data/venv/bin/python -m pip install Pillow python-pptx",
        "docker exec -i <c> /data/venv/bin/presentation init --workspace /data/ws ...",
        "docker exec -i <c> /data/venv/bin/presentation doctor --workspace /data/ws",
        "docker exec -i <c> /data/venv/bin/presentation start --workspace /data/ws ... --intake /data/intake.json --run-dir /data/ws/runs/<id>",
        "docker exec -i <c> /data/venv/bin/presentation status --run-dir <run-dir> --json",
        "docker exec -i <c> /data/venv/bin/python -   # engine: --resume --diagnose-only",
        "docker exec -i <c> /data/venv/bin/python -   # engine: --run --dry-run (CONTROL, expect parked rc 3)",
        "docker exec -i <c> /data/venv/bin/python -   # dispatcher --once",
        "docker exec -i <c> /data/venv/bin/python -   # watchdog --scan-root",
        "docker exec -i <c> /data/venv/bin/python -   # supervise --scan-root",
        "docker exec -i <c> /data/venv/bin/presentation verify --run-dir <run-dir>",
        "docker exec -i <c> /usr/bin/timeout 100 /data/venv/bin/presentation resume --run-dir <run-dir>   # expect rc 124 = RESUME-LOOP-ENTERED",
        "# reap the surviving dispatcher (bounded resume leaves one holding the lease):",
        "docker exec -i <c> /data/venv/bin/python -   # /proc scan, kills only cmdlines naming this run dir",
        "docker exec -i <c> /data/venv/bin/python -   # CONTROL: engine verb must no longer see rc 6 lease contention",
        "docker exec -i <c> /data/venv/bin/presentation status --run-dir <run-dir> --json   # post-resume control",
        "docker exec -i <c> /data/venv/bin/python -   # render: local synthetic PNG + PPTX into /data/render",
        "docker exec -i <c> /data/venv/bin/python -   # QC-1: PNG magic/dims/non-blank, independent read from disk",
        "docker exec -i <c> /data/venv/bin/python -   # QC-2: pptx zip integrity + slide count + <a:t> text presence",
        "# op=upgrade: pip install --force-reinstall --no-deps of the EXACT wheel over the live install",
        "# op=restart: docker restart <c>; container id stable; started_at changed; venv + state alive",
        "docker exec -i <c> /data/venv/bin/presentation export --run-dir <run-dir> --out /data/export",
        "docker cp <c>:/data/export/. run/evidence/PRES-055/b-docker-redo/containers/<profile>__<op>/export-out/",
        "docker cp <c>:/data/render/png/slide-01.png run/evidence/PRES-055/b-docker-redo/renders/<profile>__<op>-slide-01.png",
        "docker inspect <c>   # image/mounts/cmd receipts",
        "docker logs <c>",
        "docker rm -f <c> && docker volume rm pres055-redo-<profile>-<op>-vol",
        "",
        "# controls re-run from leg B, unchanged code path (READ-ONLY import):",
        "#   matrix stub contract (must self-report NOT-RUN exit 3, never PASS)",
        "#   adapter probes (standalone positive + missing-marker negative)",
        f"#   source: {WORKTREE_REL}/accept-b/docker_matrix_b.py (leg B module)",
        "",
        "# candidate write-back (after commit SHA known):",
        f"python3 {WORKTREE_REL}/accept-b/docker-redo/run_redo.py \\",
        "    --evidence-dir run/evidence/PRES-055/b-docker-redo \\",
        "    --candidate-dir run/candidates/PRES-055-b-redo --worktree-sha <sha>",
        "",
    ])


def summarize(dm: dict) -> tuple[str, bool]:
    legs = dm.get("docker_matrix_legs", [])
    daemon = dm.get("docker_daemon", {})
    reachable = bool(daemon.get("reachable"))
    fails: list[str] = []
    defect_rows: list[str] = []
    for leg in legs:
        name = leg.get("leg", "?")
        st = leg.get("status")
        if st == "NOT-VERIFIED":
            fails.append(f"{name}: NOT-VERIFIED ({leg.get('not_verified_reason')})")
        elif st == "DEPLOYED-RUN-FAIL":
            fails.append(f"{name}: DEPLOYED-RUN-FAIL {leg.get('failures')}")
        for d in leg.get("defects", []) or []:
            defect_rows.append(f"{name}: {d.get('id')} rc={d.get('observed_rc')} "
                               f"expected {d.get('expected_rc')}")
    ctl = dm.get("controls_leg_b_rerun", {})
    stubs = (ctl.get("matrix_stub_contract") or {})
    for profile, row in stubs.items():
        if not row.get("contract_ok"):
            fails.append(f"leg B stub contract {profile} BROKEN")
    # leg B's adapter_probes returns the two arms' rc+stdout (no `ok` key), so
    # the discrimination is asserted here explicitly: the standalone probe must
    # answer READY (rc 0) on the real package dir and NOT-READY (rc 2) on a
    # package dir with no marker. A control that answered the same on both arms
    # would mean the probe cannot discriminate at all.
    ap = ctl.get("adapter_probes") or {}
    if ap:
        pos, neg = (ap.get("standalone_positive") or {}), (
            ap.get("standalone_negative_missing_marker") or {})
        ap_ok = (pos.get("returncode") == 0 and "READY" in (pos.get("stdout") or "")
                 and "NOT-READY" not in (pos.get("stdout") or "")
                 and neg.get("returncode") == 2
                 and "NOT-READY" in (neg.get("stdout") or ""))
        ap["ok"] = ap_ok
        if not ap_ok:
            fails.append(f"leg B adapter probes did not discriminate: {ap}")
    pv = dm.get("runtime_control_python_version", {})
    if not pv.get("discriminates"):
        fails.append("python-version runtime control did not discriminate "
                     "(control broken, not the target)")
    rp = dm.get("runtime_control_pid1_reaping", {})
    if not rp.get("discriminates"):
        fails.append("pid-1 reaping runtime control did not discriminate "
                     "(control broken, not the target)")
    green = {"DEPLOYED-RUN-PASS", "DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS"}
    ran = [l.get("leg") for l in legs if l.get("status") in green]
    okay = (reachable and not fails and len(ran) == 6)

    pins = dm.get("pins", {})
    img = dm.get("base_image", {})
    md = [
        "# PRES-055 leg B Docker-matrix REDO R2 summary (W6 WF23, NOT self-approval)",
        "",
        f"- generated_at: {dm.get('generated_at') or _utcnow()}",
        f"- worktree branch: {BRANCH} from {BASE_SHA}",
        f"- routed model: {MODEL}",
        f"- docker daemon reachable: {reachable}",
        f"- base image digest matches pin: {img.get('matches_pin')} "
        f"({img.get('image_id')})",
        "",
        "## Docker matrix legs (real containers, live engine)",
        "",
    ]
    for leg in legs:
        md.append(f"- {leg.get('leg')}: **{leg.get('status')}** "
                  f"(steps {leg.get('steps_total')}, required-red "
                  f"{len(leg.get('steps_red_required') or [])}, control-red "
                  f"{len(leg.get('steps_red_control') or [])})")
    md += ["", "## Recorded artifact defects (never waived)", ""]
    md += ([f"- {r}" for r in defect_rows] or
           ["- none: the engine dry-run park control returned the expected rc 3 "
            "on the container runtime for every leg"])
    md += [
        "",
        "## Controls (re-run; a control that does not discriminate means the",
        "## instrument is broken, not the target)",
        "",
        f"- leg B matrix stub contract: "
        + ", ".join(f"{k}={'OK' if v.get('contract_ok') else 'BROKEN'}"
                    for k, v in stubs.items()),
        (f"- leg B adapter probes discriminate (standalone READY rc 0 vs "
         f"missing-marker NOT-READY rc 2): {ap.get('ok')}"),
        f"- python-version runtime control discriminates: {pv.get('discriminates')} "
        f"({pv.get('note') or 'Thread._stop shadowing on python <=3.12 vs 3.14'})",
        f"- pid-1 reaping runtime control discriminates: {rp.get('discriminates')} "
        f"({rp.get('question')})",
        "",
        "## Carriers (verified read-only against the pins)",
        "",
        f"- wheel sha256: {pins.get('wheel_sha256')}",
        f"- sdist sha256: {pins.get('sdist_sha256')}",
        f"- plugin sha256: {pins.get('plugin_sha256')}",
        f"- manifest v68 sha256: {pins.get('manifest_sha256')} (62 phases)",
        f"- staged content sha256: {pins.get('staged_content_sha256')}",
        "",
        "## Still NOT-VERIFIED (unchanged by this redo, never waived)",
        "",
        "- Hostinger / Contabo vendor hosts themselves were NOT contacted: both",
        "  profile rows ran as real containers on the local Docker engine only.",
        "- Version-to-version upgrade: no prior released wheel exists here, so",
        "  only a force-reinstall of the exact artifact over a live install ran.",
        "- Connected CC / connected GHL acceptance: not redone (PRES-025/CC",
        "  connected legs are recorded separately under",
        "  run/evidence/PRES-055/b-docker/ and were read-only here).",
        "- Canonical KIE render: zero paid calls; render is LOCAL-SYNTHETIC.",
        "",
        "## Verdict",
        "",
        f"- {dm.get('verdict')}",
        "",
    ]
    if fails:
        md += ["## Reds", ""] + [f"- {f}" for f in fails] + [""]
    md += [
        "No receipt here self-approves anything. QC-PRES-055 stays OPEN pending",
        "INDEPENDENT QC.",
        "",
        "## Provenance of these documents",
        "",
        "docker-matrix.json is written by the leg driver itself as the six legs",
        "run. HOST.txt / COMMANDS.txt / REDO-SUMMARY.md are DERIVED from that",
        "same receipt (no leg is re-run to regenerate them); with",
        "`--reuse-matrix` the receipt is left byte-identical unless a derived",
        "key actually changed.",
        "",
    ]
    return "\n".join(md), okay


def write_candidate(candidate_dir: Path, worktree_sha: str, dm: dict,
                    okay: bool) -> Path:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    legs = dm.get("docker_matrix_legs", [])
    green = {"DEPLOYED-RUN-PASS", "DEPLOYED-RUN-PASS-WITH-RECORDED-DEFECTS"}
    by_status: dict[str, list] = {}
    defects: list = []
    for leg in legs:
        by_status.setdefault(leg.get("status", "?"), []).append(leg.get("leg"))
        for d in leg.get("defects", []) or []:
            defects.append({"leg": leg.get("leg"), **d})
    pins = dm.get("pins", {})
    doc = {
        "task_ids": ["PRES-055"],
        "leg": "B-docker-redo (W6 WF23 Docker-matrix REDO R2)",
        "branch": BRANCH,
        "base_sha": BASE_SHA,
        "proposed_sha": worktree_sha,
        "proposed_kind": "worktree commit (NOT pushed, NOT merged, NOT released)",
        "author_model": MODEL,
        "ordered_lock": LOCK_REL,
        "carriers_verified": dict(pins),
        "owned_paths": [
            "run/worktrees/wf23-onb-accept/accept-b/docker-redo/",
            "run/evidence/PRES-055/b-docker-redo/",
            "run/candidates/PRES-055-b-redo/",
        ],
        "evidence": [
            "run/evidence/PRES-055/b-docker-redo/HOST.txt",
            "run/evidence/PRES-055/b-docker-redo/COMMANDS.txt",
            "run/evidence/PRES-055/b-docker-redo/docker-matrix.json",
            "run/evidence/PRES-055/b-docker-redo/REDO-SUMMARY.md",
            "run/evidence/PRES-055/b-docker-redo/SHA.txt",
            "run/evidence/PRES-055/b-docker-redo/containers/<profile>__<op>/logs/ "
            "(per-step argv + rc + expected + ok + stdout/stderr)",
            "run/evidence/PRES-055/b-docker-redo/containers/<profile>__<op>/leg.json "
            "(per-leg receipt: steps, controls, defects, state readback, cleanup)",
            "run/evidence/PRES-055/b-docker-redo/containers/<profile>__<op>/"
            "export-out/ (docker cp readback of the container export dir)",
            "run/evidence/PRES-055/b-docker-redo/containers/<profile>__<op>/renders/ "
            "(slide-01.png + deck.pptx copied out of the container)",
        ],
        "tests": {
            "docker_matrix_legs": {k: v for k, v in sorted(by_status.items())},
            "legs_ran_green": sum(len(v) for k, v in by_status.items() if k in green),
            "leg_b_stub_contract": "rerun in docker-matrix.json "
                                   "(controls_leg_b_rerun.matrix_stub_contract)",
            "leg_b_adapter_probes": "rerun in docker-matrix.json "
                                    "(controls_leg_b_rerun.adapter_probes)",
            "runtime_control_python_version": (
                "DISCRIMINATES" if (dm.get("runtime_control_python_version")
                                    or {}).get("discriminates")
                else "DOES-NOT-DISCRIMINATE (control broken, not the target)"),
            "runtime_control_pid1_reaping": dm.get(
                "runtime_control_pid1_reaping", {}).get("status"),
            "recorded_artifact_defects": defects,
        },
        "docker_matrix": (
            f"{sum(len(v) for k, v in by_status.items() if k in green)}/6 legs ran for "
            "real in containers on the live daemon against the exact released wheel; "
            f"statuses: {by_status}"),
        "connected_cc": "NOT-VERIFIED (not redone here; see run/evidence/PRES-055/b-docker/cc-ghl.json)",
        "connected_ghl": "NOT-VERIFIED (not redone here; see run/evidence/PRES-055/b-docker/cc-ghl.json)",
        "vendor_hosts": "NOT-VERIFIED (Hostinger/Contabo VPS not contacted; both "
                        "profiles ran on the local Docker engine only)",
        "version_to_version_upgrade": "NOT-VERIFIED (no prior released wheel in packet; "
                                       "force-reinstall of the exact artifact over a live "
                                       "install was exercised instead)",
        "qc": "PENDING_INDEPENDENT_QC (no self-approval; QC-PRES-055 stays OPEN)",
        "state_for_wf00": "CANDIDATE_PENDING_QC",
        "leg_b_redo_runnable": "PASS" if okay else "FAIL",
    }
    out = candidate_dir / "candidate.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", required=True, type=Path)
    ap.add_argument("--candidate-dir", type=Path, default=None)
    ap.add_argument("--worktree-sha", default=None)
    ap.add_argument("--keep-containers", action="store_true")
    ap.add_argument("--reuse-matrix", action="store_true",
                    help="write the candidate/SHA from the docker-matrix.json "
                         "already on disk instead of re-running the 6 legs "
                         "(rerunning would overwrite the receipt the candidate "
                         "describes); the matrix is never edited by this path")
    args = ap.parse_args(argv)
    ev: Path = args.evidence_dir
    ev.mkdir(parents=True, exist_ok=True)
    dm_out = ev / "docker-matrix.json"
    if args.reuse_matrix:
        if not dm_out.is_file():
            print(f"--reuse-matrix: no receipt at {dm_out}", file=sys.stderr)
            return 2
        rc = 0
        print(f"--reuse-matrix: using existing receipt {dm_out}")
    else:
        rc = docker_redo.main(["--out", str(dm_out)]
                              + (["--keep-containers"] if args.keep_containers else []))
    dm = json.loads(dm_out.read_text(encoding="utf-8"))
    (ev / "HOST.txt").write_text(_host_txt(dm), encoding="utf-8")
    (ev / "COMMANDS.txt").write_text(_commands_txt(), encoding="utf-8")
    md, okay = summarize(dm)
    # summarize() asserts the adapter-probe discrimination and stores the
    # derived `ok` back on the control dict; persist it so the evidence JSON
    # carries the verdict and not just the two raw arms. Under --reuse-matrix
    # the receipt is the artifact the candidate describes, so it is written
    # back ONLY if this derived key actually changed; otherwise it stays
    # byte-stable.
    new_dm = json.dumps(dm, indent=2)
    if args.reuse_matrix and new_dm == dm_out.read_text(encoding="utf-8"):
        print("--reuse-matrix: receipt unchanged, left as-is")
    else:
        dm_out.write_text(new_dm, encoding="utf-8")
    (ev / "REDO-SUMMARY.md").write_text(md, encoding="utf-8")
    print(md)
    if args.candidate_dir is not None:
        if not args.worktree_sha:
            print("candidate write needs --worktree-sha", file=sys.stderr)
            return 2
        c = write_candidate(args.candidate_dir, args.worktree_sha, dm, okay)
        (ev / "SHA.txt").write_text(
            args.worktree_sha + "\n"
            f"base: {BASE_SHA}\n"
            f"branch: {BRANCH}\n"
            f"worktree: {WORKTREE_REL}\n"
            f"ordered lock: {LOCK_REL}\n"
            "docker-matrix generated_at: " + str(dm.get("generated_at")) + "\n",
            encoding="utf-8")
        print(f"candidate: {c}")
    # rc from docker_redo is the leg verdict; a recorded defect is reported in
    # the summary/candidate and never silently returns a green exit.
    return 0 if (okay and rc == 0) else 1


if __name__ == "__main__":
    sys.exit(main())

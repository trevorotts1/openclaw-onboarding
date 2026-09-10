#!/usr/bin/env python3
"""Leg A orchestrator: Mac-native + standalone-no-gateway (W6 WF23, Opus).

Runs readiness + intake/resume + render/QC + delivery in-process, then writes:

- packet evidence dir run/evidence/PRES-055/a-mac/ (NEW files ONLY):
  HOST.txt, COMMANDS.txt, readiness.json, intake-resume.json, render-qc.json,
  delivery.json, INTAKE-COMMANDS.txt, LEG-A-SUMMARY.md, SHA.txt,
  renders/slide-01.png, renders/deck.pptx
- candidate run/candidates/PRES-055-a/candidate.json AFTER caller passes
  --worktree-sha (accept-a commit SHA). Until then everything except candidate.

Usage:
  python3 accept-a/run_leg_a.py --evidence-dir <packet a-mac dir> --scratch /tmp/leg-a-run
  python3 accept-a/run_leg_a.py --evidence-dir <dir> --scratch /tmp/leg-a-run \\
      --candidate-dir <dir> --worktree-sha <sha> --base-sha db4c0fdff --branch pres055-wf23-a

Exit 0 when all four legs DEPLOYED-RUN-PASS. Exit 1 else. Never fabricates.
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

import delivery_a  # noqa: E402
import intake_resume_a  # noqa: E402
import readiness_a  # noqa: E402
import render_qc_a  # noqa: E402

BASE_SHA = "db4c0fdff591c7693ce0fc42dfeee458ab8068c7"
BRANCH = "pres055-wf23-a"
MODEL = "opus-chain (W6 WF23 leg A Mac+standalone)"
COMPANY = "SYN-CO-ACME-01"
PRES = "SYN-PRES-ACME-DECK-01"


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
    lines = [
        "HOST: operator Mac Mini (Trevor own box, canary)",
        f"OS: {platform.system()} {platform.release()} {platform.machine()}",
        f"python3: {pyv}",
        "worktree: run/worktrees/wf23-onb-accept",
        f"branch: {BRANCH}",
        f"base: {BASE_SHA}",
        "install profile: mac-native (this leg; docker profiles owned by leg B)",
        "live GHL run: NONE (synthetic intake only; no credentials, no network)",
        "live CC run: NONE connected (local export only)",
        "canonical KIE render: NOT-RUN (no key, zero paid calls; LOCAL-SYNTHETIC-RENDER only)",
    ]
    return "\n".join(lines) + "\n"


def _commands_txt() -> str:
    return "\n".join([
        "# Leg A exact commands (run from packet root unless noted)",
        "git -C run/worktrees/wf23-onb-accept checkout -b pres055-wf23-a db4c0fdff",
        "python3 run/worktrees/wf23-onb-accept/accept-a/run_leg_a.py --evidence-dir run/evidence/PRES-055/a-mac --scratch /tmp/leg-a-run",
        "# -- inside run_leg_a.py, in order (all real, hermetic scratch OUTSIDE packet):",
        "claude --version",
        "claude-nine --version",
        "python3 -m venv /tmp/leg-a-run/venv",
        "/tmp/leg-a-run/venv/bin/python -m pip install <build>/pkg/dist/presentation_department-0.1.0-py3-none-any.whl",
        "presentation init/start/status/verify/export (console entry, env -i hermetic)",
        "engine --resume --diagnose-only / --run --dry-run / dispatcher --once / watchdog / supervise (compat shim)",
        "Pillow PNG render + python-pptx build (LOCAL-SYNTHETIC-RENDER) + QC-1/QC-2 independent passes",
        "bundle_gate.py --adhoc (fail-closed control) + dispatcher --once",
        "# worktree commit (ordered lock run/locks/pres055-wf23.lock):",
        "git -C run/worktrees/wf23-onb-accept add accept-a",
        "git -C run/worktrees/wf23-onb-accept commit -m 'PRES-055 leg A (W6 WF23): ...'",
        "# candidate write-back (after commit SHA known):",
        "python3 run/worktrees/wf23-onb-accept/accept-a/run_leg_a.py --evidence-dir run/evidence/PRES-055/a-mac --scratch /tmp/leg-a-run --candidate-dir run/candidates/PRES-055-a --worktree-sha <sha> --base-sha db4c0fdff --branch pres055-wf23-a",
        "",
    ])


def run_all(evidence_dir: Path, scratch: Path) -> dict:
    evidence_dir.mkdir(parents=True, exist_ok=True)
    scratch.mkdir(parents=True, exist_ok=True)
    (evidence_dir / "HOST.txt").write_text(_host_txt(), encoding="utf-8")
    (evidence_dir / "COMMANDS.txt").write_text(_commands_txt(), encoding="utf-8")
    r_scratch = scratch / "readiness"
    readiness_a.main(["--out", str(evidence_dir / "readiness.json"), "--scratch", str(r_scratch)])
    i_scratch = scratch / "intake"
    intake_resume_a.main(["--out", str(evidence_dir / "intake-resume.json"),
                          "--scratch", str(i_scratch),
                          "--cmd-log", str(evidence_dir / "INTAKE-COMMANDS.txt")])
    vpy = i_scratch / "venv" / "bin" / "python"
    vcli = i_scratch / "venv" / "bin" / "presentation"
    rundir = i_scratch / "ws leg-a" / "runs" / f"{COMPANY}-{PRES}"
    render_qc_a.main(["--out", str(evidence_dir / "render-qc.json"),
                      "--scratch", str(scratch / "render"),
                      "--venv-python", str(vpy), "--run-dir", str(rundir),
                      "--visual-dir", str(evidence_dir / "renders")])
    delivery_a.main(["--out", str(evidence_dir / "delivery.json"),
                     "--scratch", str(scratch / "delivery"),
                     "--venv-python", str(vpy), "--venv-cli", str(vcli),
                     "--run-dir", str(rundir),
                     "--delivery-dir", str(evidence_dir / "delivery")])
    docs = {}
    for name in ("readiness.json", "intake-resume.json", "render-qc.json", "delivery.json"):
        docs[name] = json.loads((evidence_dir / name).read_text(encoding="utf-8"))
    return docs


def summarize(res: dict) -> tuple[str, bool]:
    fails: list[str] = []
    for name, want in (("readiness.json", "DEPLOYED-RUN-PASS"),
                       ("intake-resume.json", "DEPLOYED-RUN-PASS"),
                       ("render-qc.json", "DEPLOYED-RUN-PASS"),
                       ("delivery.json", "DEPLOYED-RUN-PASS")):
        if res[name].get("status") != want:
            fails.append(f"{name} not {want}: {res[name].get('failures')}")
    ok = not fails
    r, i, q, d = (res["readiness.json"], res["intake-resume.json"],
                  res["render-qc.json"], res["delivery.json"])
    md = [
        "# PRES-055 leg A summary (W6 WF23, NOT self-approval)",
        "",
        f"- generated_at: {_utcnow()}",
        f"- worktree branch: {BRANCH} from {BASE_SHA}",
        f"- routed model: {MODEL}",
        "",
        "## Readiness (adapter + scheduler + standalone, gateway probe read-only)",
        "",
        f"- status: {r.get('status')}",
        f"- claude: {(r.get('claude_code_cli') or {}).get('first_line')}",
        f"- nine: {(r.get('claude_nine_cli') or {}).get('first_line')}",
        f"- carriers 3/3: {(r.get('exact_released_artifact') or {}).get('all_match')}",
        f"- negative control: {(r.get('openclaw_gateway_probe_readonly') or {}).get('result', {}).get('status')}",
        "",
        "## Intake + pause/resume (hermetic install, user-facing entry)",
        "",
        f"- status: {i.get('status')}",
        f"- job: {(i.get('run_identity') or {}).get('job_id')}",
        f"- manifest: v{(i.get('run_identity') or {}).get('manifest_version')}",
        f"- events: {i.get('event_count')}",
        f"- dry-run parked rc: {(i.get('engine_run_dry_run') or {}).get('rc')} (expected 3, AF-INTAKE-GATE honest)",
        f"- dispatcher/watchdog/supervise rc: {(i.get('dispatcher_once') or {}).get('rc')}/{(i.get('watchdog') or {}).get('rc')}/{(i.get('supervise') or {}).get('rc')}",
        "",
        "## Render + independent visual QC (LOCAL-SYNTHETIC-RENDER)",
        "",
        f"- status: {q.get('status')}",
        f"- pngs: {(q.get('render_outputs') or {}).get('png_count')}",
        f"- QC-1 PNG: {(q.get('qc1_png_independent') or {}).get('status')}",
        f"- QC-2 PPTX: {(q.get('qc2_pptx_independent') or {}).get('status')}",
        f"- bundle_gate --adhoc rc: {(q.get('bundle_gate_adhoc') or {}).get('rc')} (fail-closed control)",
        "- visual proof: renders/slide-01.png + renders/deck.pptx",
        "- canonical KIE render: NOT-RUN (no key, zero paid)",
        "",
        "## Delivery (synthetic clients, local export)",
        "",
        f"- status: {d.get('status')}",
        f"- job: {d.get('run_job_id')}",
        f"- export files: {(d.get('export_provenance') or {}).get('files')}",
        f"- connected GHL/CC: {d.get('connected_ghl_delivery')} / {d.get('connected_cc_delivery')}",
        "",
        "## Routed model IDs (resolved-not-called)",
        "",
        f"- {json.dumps(d.get('routed_model_ids_resolved_not_called', {}))}",
        "",
        "## Verdict",
        "",
        ("- LEG-A-RUNNABLE-PASS (all runnable legs green; connected CC/GHL + "
         "canonical KIE honestly NOT-VERIFIED/NOT-RUN; QC-PRES-055 stays OPEN "
         "pending INDEPENDENT QC)"
         if ok else "- LEG-A-FAIL: " + "; ".join(fails)),
        "",
    ]
    return "\n".join(md), ok


def write_candidate(candidate_dir: Path, worktree_sha: str, base_sha: str,
                    branch: str, res: dict, ok: bool) -> Path:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "task_ids": ["PRES-055"],
        "leg": "A-mac-standalone (W6 WF23)",
        "branch": branch,
        "base_sha": base_sha,
        "proposed_sha": worktree_sha,
        "proposed_kind": "worktree commit (NOT pushed, NOT merged)",
        "author_model": MODEL,
        "carriers_verified": {
            "wheel_sha256": "d02e50855a47e2672766970f7142940fc16311efc1891f3edd3fc131daa8e206",
            "sdist_sha256": "2d696d48c726321325fd87de9c5d3d7477e4023e635b30cce8ede114af9dc2a4",
            "plugin_sha256": "9f2843d0886165e3ed6038ee1d10d4017ebe078c1bf5f9c15cf9b17013b01487",
            "manifest_sha256": "cab872039b2dac96bc78300a2158487ee7093e84d55a71069285789ca369f5de",
            "staged_content_sha256": "4cad34944ba28dc4e8648ac137a17bfb9c53d2e63b3899301bc18d2a188e4391",
            "match_receipt_3_3": res["readiness.json"]["exact_released_artifact"]["all_match"],
        },
        "owned_paths": ["run/worktrees/wf23-onb-accept/accept-a/"],
        "evidence": [
            "run/evidence/PRES-055/a-mac/HOST.txt",
            "run/evidence/PRES-055/a-mac/COMMANDS.txt",
            "run/evidence/PRES-055/a-mac/readiness.json",
            "run/evidence/PRES-055/a-mac/intake-resume.json",
            "run/evidence/PRES-055/a-mac/render-qc.json",
            "run/evidence/PRES-055/a-mac/delivery.json",
            "run/evidence/PRES-055/a-mac/INTAKE-COMMANDS.txt",
            "run/evidence/PRES-055/a-mac/LEG-A-SUMMARY.md",
            "run/evidence/PRES-055/a-mac/SHA.txt",
            "run/evidence/PRES-055/a-mac/renders/slide-01.png",
            "run/evidence/PRES-055/a-mac/renders/deck.pptx",
        ],
        "tests": {
            "readiness": res["readiness.json"]["status"],
            "intake_resume": res["intake-resume.json"]["status"],
            "render_qc": res["render-qc.json"]["status"],
            "delivery": res["delivery.json"]["status"],
            "run_job_id": res["intake-resume.json"].get("run_identity", {}).get("job_id"),
        },
        "routed_model_ids": res["delivery.json"].get("routed_model_ids_resolved_not_called", {}),
        "canonical_kie_render": "NOT-RUN (no key, zero paid)",
        "connected_cc": "NOT-VERIFIED (no scoped live resource)",
        "connected_ghl": "NOT-VERIFIED (no scoped live resource)",
        "qc": "PENDING_INDEPENDENT_QC (no self-approval; QC-PRES-055 stays OPEN)",
        "state_for_wf00": "CANDIDATE_PENDING_QC",
        "leg_a_runnable": "PASS" if ok else "FAIL",
    }
    out = candidate_dir / "candidate.json"
    out.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--evidence-dir", required=True, type=Path)
    ap.add_argument("--scratch", required=True, type=Path)
    ap.add_argument("--candidate-dir", type=Path, default=None)
    ap.add_argument("--worktree-sha", default=None)
    ap.add_argument("--base-sha", default="db4c0fdff")
    ap.add_argument("--branch", default=BRANCH)
    args = ap.parse_args(argv)
    res = run_all(args.evidence_dir, args.scratch)
    md, ok = summarize(res)
    (args.evidence_dir / "LEG-A-SUMMARY.md").write_text(md, encoding="utf-8")
    print(md)
    if args.candidate_dir is not None:
        if not args.worktree_sha:
            print("candidate write needs --worktree-sha", file=sys.stderr)
            return 2
        out = write_candidate(args.candidate_dir, args.worktree_sha,
                              args.base_sha, args.branch, res, ok)
        (args.evidence_dir / "SHA.txt").write_text(args.worktree_sha + "\n", encoding="utf-8")
        print(f"candidate: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

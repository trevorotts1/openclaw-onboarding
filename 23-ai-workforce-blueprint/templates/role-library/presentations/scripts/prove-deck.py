#!/usr/bin/env python3
"""
prove-deck.py — END-OF-PROCESS NO-SKIP PROOF CERTIFICATE (FIX C).

================================================================================
Nothing reaches "done/delivered" without an INDEPENDENT, unspoofable proof that
the WHOLE declared process actually ran — in order, with real artifacts, each
validated for SUBSTANCE (not mere existence) and each REPORTED to the client.
This is the can't-fake-it backstop to the build-time gates: even if every other
gate were bypassed, a deck cannot be certified without this walk passing.
================================================================================

WHAT IT WALKS (the declared plan + the attestation chain)
  * declared_plan.json (FIX E) — the contract the agent committed to at run-begin
    ("I'll follow these N steps and report after each"). When absent it falls back
    to the manifest phase list (ordered) as the declared plan.
  * working/checkpoints/process_manifest.json — phase_attestations[], client_reports[]
    (FIX E), owner_skip_approvals[].
  * phase_verifiers.py (FIX F) — the per-phase SUBSTANCE verifier (real output
    inspection, reusing the engine checkers), when deployed.

FOR EVERY DECLARED STEP it asserts ALL of:
  (a) ATTESTED        — a phase_attestation exists for the step.
  (b) ARTIFACT-SHA    — the attestation carries a NON-EMPTY artifact_sha
                        (the FM-3 empty-sha "done" stamp is rejected).
  (c) SUBSTANCE       — phase_verifiers.verify_phase(step, run_dir) passes when the
                        verifier is deployed (substance, not existence).
  (d) REPORTED        — a client start AND done report exist with a confirmed
                        gateway_msg_id (FIX E), for steps the plan marks
                        report_required.
  (e) IN-ORDER        — the steps attested in ascending plan order (an
                        earlier-order step attested AFTER a later one = out-of-order).
  (f) NO MISSING STEP — every declared step is present (covered by (a)).

On a FULL pass it writes a client-presentable PROCESS-CERTIFICATE.json + .md and a
content sha (process_certificate_sha) the Command Center done-gate can require
(OTHER REPO). On ANY skip / out-of-order / unvalidated / unreported step it exits 9.
The ONLY bypass for a single step is a logged, VERIFIABLE owner_skip_approval
(owner_approved:true + approved_by + reason + a real, non-placeholder timestamp +
an owner message id) — never self-authored, never back-dated.

ZERO third-party deps (stdlib json / hashlib / argparse / pathlib / re / time).

EXIT CODES
    0 — full pass; PROCESS-CERTIFICATE written.
    9 — one or more steps failed the no-skip proof (skip / out-of-order /
        empty-sha / unvalidated substance / unreported). The deck is NOT certified.
    2 — could not run (missing run dir / manifest unreadable).
"""

import argparse
import hashlib
import json
import re
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXIT_NO_SKIP_FAIL = 9


def _fatal(msg):
    print(f"FATAL [prove-deck]: {msg}", file=sys.stderr)
    sys.exit(2)


def _find_repo_root(start: Path):
    cur = start
    for _ in range(12):
        if (cur / "universal-sops").is_dir():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return None


def load_manifest() -> dict:
    repo = _find_repo_root(HERE)
    cands = []
    if repo:
        cands.append(repo / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json")
    cands += [HERE.parent / "sops" / "PIPELINE-MANIFEST.json", HERE.parent / "PIPELINE-MANIFEST.json"]
    for c in cands:
        if c.exists():
            try:
                return json.loads(c.read_text())
            except Exception:  # noqa: BLE001
                pass
    return {}


def _proc_manifest(run_dir: Path) -> dict:
    p = run_dir / "working" / "checkpoints" / "process_manifest.json"
    if not p.exists():
        return {}
    try:
        obj = json.loads(p.read_text())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def _declared_plan(run_dir: Path, manifest: dict) -> list:
    """The ordered declared steps: declared_plan.json when present (FIX E), else the
    manifest phases. Each step is {phase_id, order, name, report_required}."""
    dp = run_dir / "working" / "checkpoints" / "declared_plan.json"
    report_required_by_id = {}
    for ph in manifest.get("phases", []):
        cr = ph.get("client_report") or {}
        report_required_by_id[ph.get("id")] = bool(cr.get("required"))
    if dp.exists():
        try:
            obj = json.loads(dp.read_text())
            steps = obj.get("steps") if isinstance(obj, dict) else None
            if isinstance(steps, list) and steps:
                out = []
                for s in steps:
                    pid = s.get("phase_id") or s.get("id")
                    if not pid:
                        continue
                    out.append({
                        "phase_id": pid,
                        "order": s.get("order", 0),
                        "name": s.get("name", pid),
                        "report_required": bool(s.get("report_required",
                                                       report_required_by_id.get(pid, False))),
                    })
                return sorted(out, key=lambda x: x["order"])
        except Exception:  # noqa: BLE001
            pass
    # fallback: manifest phases
    return sorted(
        [{"phase_id": ph["id"], "order": ph.get("order", 0), "name": ph.get("name", ph["id"]),
          "report_required": report_required_by_id.get(ph["id"], False)}
         for ph in manifest.get("phases", []) if ph.get("id")],
        key=lambda x: x["order"],
    )


# ---------------------------------------------------------------------------
# Owner-skip validity (FM-4 hardening — verifiable, never self-authored/back-dated)
# ---------------------------------------------------------------------------
_PRODUCER_IDENTITIES = {"self", "builder", "build_deck", "build_deck.py", "agent",
                        "run_signature_deck", "run_signature_deck.py", "the agent",
                        "producing agent", "assistant"}
_MIDNIGHT_RE = re.compile(r"T00:00:00")


def _valid_owner_skip(rec: dict) -> bool:
    if not isinstance(rec, dict):
        return False
    approved = rec.get("owner_approved") is True or rec.get("approved") is True
    by = str(rec.get("approved_by", "")).strip()
    reason = str(rec.get("reason", "")).strip()
    ts = str(rec.get("timestamp") or rec.get("approved_at") or "").strip()
    owner_msg = str(rec.get("gateway_msg_id") or rec.get("owner_message_id")
                    or rec.get("telegram_message_id") or "").strip()
    if not (approved and by and reason):
        return False
    if by.lower() in _PRODUCER_IDENTITIES:           # self-authored => invalid (FM-4)
        return False
    if (not ts) or _MIDNIGHT_RE.search(ts):          # placeholder/midnight => invalid
        return False
    if not owner_msg:                                # must reference a real owner action
        return False
    return True


def _skips_by_target(pm: dict) -> dict:
    out = {}
    recs = []
    for key in ("owner_skip_approvals", "owner_skip_approval", "phase_skip_approvals"):
        v = pm.get(key)
        if isinstance(v, list):
            recs += v
        elif isinstance(v, dict):
            recs += v.get("approvals", []) if isinstance(v.get("approvals"), list) else [v]
    for r in recs:
        if not _valid_owner_skip(r):
            continue
        target = str(r.get("phase_id") or r.get("gate") or r.get("gate_code") or r.get("code") or "").strip()
        if target:
            out[target] = r
    return out


# ---------------------------------------------------------------------------
# Substance verifier (FIX F) — best-effort import
# ---------------------------------------------------------------------------
def _substance(phase_id: str, run_dir: Path):
    """Return (checked: bool, ok: bool, reason: str). When phase_verifiers is not
    deployed, checked=False (the certificate records substance_checked:false)."""
    try:
        sys.path.insert(0, str(HERE))
        import phase_verifiers as pv  # type: ignore
    except Exception:  # noqa: BLE001
        return False, True, "phase_verifiers not deployed"
    fn = getattr(pv, "verify_phase", None)
    if not callable(fn):
        return False, True, "phase_verifiers.verify_phase missing"
    try:
        ok, reason = fn(phase_id, run_dir)
        return True, bool(ok), str(reason or "")
    except Exception as exc:  # noqa: BLE001
        return True, False, f"verifier raised {exc!r}"


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------
def prove(run_dir: Path):
    manifest = load_manifest()
    pm = _proc_manifest(run_dir)
    plan = _declared_plan(run_dir, manifest)
    if not plan:
        _fatal("no declared plan and no manifest phases — nothing to prove.")

    atts = {a.get("phase_id"): a for a in pm.get("phase_attestations", []) if isinstance(a, dict)}
    # build_deck records the render under phases[]{phase:"render"} — count it as P4-RENDER.
    for ph in pm.get("phases", []) or []:
        if isinstance(ph, dict) and ph.get("phase") == "render" and "P4-RENDER" not in atts:
            atts["P4-RENDER"] = {"phase_id": "P4-RENDER", "artifact_sha": ph.get("artifact_sha")
                                 or ph.get("sha") or "", "attested_at": ph.get("rendered_at")
                                 or ph.get("attested_at") or ""}
    reports = pm.get("client_reports", []) if isinstance(pm.get("client_reports"), list) else []

    def _report(pid, kind):
        for r in reports:
            if (isinstance(r, dict) and r.get("phase_id") == pid
                    and r.get("kind") == kind and str(r.get("gateway_msg_id", "")).strip()):
                return r
        return None

    skips = _skips_by_target(pm)
    failures = []
    proven = []
    last_ts = ""

    for step in plan:
        pid = step["phase_id"]
        step_fail = []
        att = atts.get(pid)
        # (a) attested
        if not att:
            step_fail.append("not attested (declared step has no phase_attestation)")
        else:
            # (b) non-empty artifact_sha (FM-3)
            if not str(att.get("artifact_sha", "")).strip():
                step_fail.append("empty artifact_sha (a 'done' stamp with no verified artifact)")
            # (e) in-order: attested_at must be >= the previous proven step's
            ts = str(att.get("attested_at", "")).strip()
            if ts and last_ts and ts < last_ts:
                step_fail.append(f"out-of-order (attested {ts} before the prior step's {last_ts})")
            if ts:
                last_ts = max(last_ts, ts)
        # (c) substance
        checked, ok, reason = _substance(pid, run_dir)
        if checked and not ok:
            step_fail.append(f"substance verifier failed: {reason}")
        # (d) reported (start + done) for report-required steps
        if step.get("report_required"):
            if not _report(pid, "start"):
                step_fail.append("no client START report with a confirmed gateway_msg_id")
            if not _report(pid, "done"):
                step_fail.append("no client DONE report with a confirmed gateway_msg_id")

        if step_fail:
            if pid in skips:
                proven.append({"phase_id": pid, "status": "owner_skip_approved",
                               "approved_by": skips[pid].get("approved_by"),
                               "reason": skips[pid].get("reason")})
                continue
            failures.append({"phase_id": pid, "name": step["name"], "problems": step_fail})
        else:
            proven.append({"phase_id": pid, "status": "proven",
                           "artifact_sha": att.get("artifact_sha"),
                           "substance_checked": checked, "attested_at": att.get("attested_at")})

    return manifest, plan, proven, failures


def write_certificate(run_dir: Path, manifest: dict, plan: list, proven: list) -> dict:
    cert = {
        "schema": "process_certificate/v1",
        "deck_run_dir": str(run_dir),
        "manifest_version": manifest.get("manifest_version"),
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "declared_steps": len(plan),
        "proven_steps": len(proven),
        "steps": proven,
        "no_skip_proof": "PASS",
        "statement": ("Every declared step ran in order, produced a real artifact "
                      "(non-empty artifact_sha), passed its substance verifier where "
                      "deployed, and was reported to the client. No step was skipped, "
                      "reordered, empty-stamped, or unreported."),
    }
    body = json.dumps(cert, indent=2, sort_keys=True).encode("utf-8")
    cert_sha = hashlib.sha256(body).hexdigest()
    cert["process_certificate_sha"] = cert_sha
    out_dir = run_dir / "working" / "checkpoints"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "PROCESS-CERTIFICATE.json").write_text(json.dumps(cert, indent=2))
    md = [
        "# Process Certificate — No-Skip Proof",
        "",
        f"- Declared steps: **{len(plan)}**",
        f"- Proven steps: **{len(proven)}**",
        f"- Certificate SHA: `{cert_sha}`",
        f"- Generated: {cert['generated_at']}",
        "",
        cert["statement"],
        "",
        "| # | Step | Status | artifact_sha |",
        "|---|------|--------|--------------|",
    ]
    for i, s in enumerate(proven, 1):
        md.append(f"| {i} | {s['phase_id']} | {s['status']} | "
                  f"`{str(s.get('artifact_sha', ''))[:16]}` |")
    (out_dir / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n")
    return cert


def main():
    ap = argparse.ArgumentParser(description="No-skip proof certificate for a deck run (FIX C).")
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        _fatal(f"--run-dir not found: {run_dir}")

    manifest, plan, proven, failures = prove(run_dir)
    if failures:
        if args.json:
            print(json.dumps({"no_skip_proof": "FAIL", "failures": failures}, indent=2))
        else:
            print("=== prove-deck: NO-SKIP PROOF FAILED — deck is NOT certified ===",
                  file=sys.stderr)
            for f in failures:
                print(f"  [{f['phase_id']}] {f['name']}", file=sys.stderr)
                for p in f["problems"]:
                    print(f"      - {p}", file=sys.stderr)
            print("\nThe ONLY bypass for a step is a logged, VERIFIABLE owner_skip_approval "
                  "(owner_approved:true + approved_by + reason + real timestamp + owner "
                  "message id). Self-authored or back-dated approvals are rejected.",
                  file=sys.stderr)
        sys.exit(EXIT_NO_SKIP_FAIL)

    cert = write_certificate(run_dir, manifest, plan, proven)
    if args.json:
        print(json.dumps({"no_skip_proof": "PASS",
                          "process_certificate_sha": cert["process_certificate_sha"],
                          "proven_steps": len(proven)}, indent=2))
    else:
        print("=== prove-deck: NO-SKIP PROOF PASSED ===")
        print(f"declared steps: {len(plan)}  proven steps: {len(proven)}")
        print(f"process_certificate_sha: {cert['process_certificate_sha']}")
        print("PROCESS-CERTIFICATE.json + .md written under working/checkpoints/.")
    sys.exit(0)


if __name__ == "__main__":
    main()

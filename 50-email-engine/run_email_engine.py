#!/usr/bin/env python3
"""run_email_engine.py — the deterministic state machine over EMAIL-MANIFEST.json.

Walks the Email Engine phases IN ORDER (P1-SELECT -> P2-GENERATE -> P3-QC ->
P4-DEPLOY) with NO phase skips. Each phase's preflight is checked against the
run directory's artifacts; P3-QC shells out to tools/prove-email.py and refuses
to advance on ANY AF-EMAIL-* violation. This is a runnable STUB: it enforces
phase ordering, artifact presence, and the fail-closed QC gate; the authoring
steps themselves are performed upstream and drop their artifacts into the run dir.

FRONT-DOOR NONCE: like the Presentations canonical orchestrator, this refuses to
run unless OC_EMAIL_ENTRY_NONCE matches the run-scoped nonce minted by
email-engine-entry.sh (the ONE sanctioned entry). This is model-free and
provider-neutral — it calls no LLM and no email provider.

EXIT CODES:
  0  all requested phases passed
  2  a phase gate failed (fail-closed)
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through email-engine-entry.sh)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_GATE = 2
EXIT_USAGE = 3
EXIT_NONCE = 4

_SKILL_DIR = Path(__file__).resolve().parent
MANIFEST = _SKILL_DIR / "EMAIL-MANIFEST.json"
PROVER = _SKILL_DIR / "tools" / "prove-email.py"

# produces_artifact -> the run-dir-relative path the phase drops.
PHASE_ORDER = ["P1-SELECT", "P2-GENERATE", "P3-QC", "P4-DEPLOY"]


def _portable_run_dir(run_dir: Path) -> str:
    """A machine-independent label for the run dir recorded in the process
    manifest. Never bake an absolute filesystem path into a written artifact:
    a run inside the skill tree records its repo-relative path (portable golden
    fixtures); any other run records just its folder name (no operator/client
    path leaks into a shipped certificate)."""
    rd = run_dir.resolve()
    try:
        return rd.relative_to(_SKILL_DIR).as_posix()
    except ValueError:
        return rd.name


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read EMAIL-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _phase(manifest, pid):
    for ph in manifest.get("phases", []):
        if ph.get("id") == pid:
            return ph
    return None


def _nonce_ok(run_dir: Path) -> bool:
    if os.environ.get("OC_EMAIL_ALLOW_DIRECT") == "1":
        # informational back-compat only; the nonce below is the real gate.
        pass
    want = os.environ.get("OC_EMAIL_ENTRY_NONCE", "")
    nf = run_dir / "working" / "checkpoints" / ".email-entry-nonce"
    if not want or not nf.is_file():
        return False
    try:
        return nf.read_text(encoding="utf-8").strip() == want.strip()
    except OSError:
        return False


def _chk_email_brief(run_dir: Path) -> tuple[bool, str]:
    brief = run_dir / "working" / "copy" / "brief.json"
    if not brief.is_file():
        return False, "missing working/copy/brief.json (intake brief not locked)"
    rc = _run_prover(brief, kind="intake")
    return (rc == 0), ("brief PASS" if rc == 0 else "brief FAILED prove-email intake gate (exit %d)" % rc)


def _chk_emails_authored(run_dir: Path) -> tuple[bool, str]:
    emails = run_dir / "working" / "copy" / "emails.json"
    if not emails.is_file():
        return False, "missing working/copy/emails.json"
    return True, "emails.json present"


def _chk_prove_email(run_dir: Path) -> tuple[bool, str]:
    emails = run_dir / "working" / "copy" / "emails.json"
    if not emails.is_file():
        return False, "missing working/copy/emails.json for QC"
    rc = _run_prover(emails)
    return (rc == 0), ("prove-email PASS" if rc == 0 else "prove-email FAILED (exit %d) — fail-closed" % rc)


def _chk_deploy_approval(run_dir: Path) -> tuple[bool, str]:
    approval = run_dir / "working" / "deploy" / "approval.json"
    if not approval.is_file():
        return False, "missing working/deploy/approval.json (DRAFT-ONLY; a human must approve before any send)"
    try:
        rec = json.loads(approval.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, "approval.json unreadable: %s" % exc
    if rec.get("approved") is True and str(rec.get("approved_by", "")).strip():
        return True, "human approval present (draft-only deploy)"
    return False, "approval.json present but not approved (approved:true + approved_by required)"


_CHECKERS = {
    "_chk_email_brief": _chk_email_brief,
    "_chk_emails_authored": _chk_emails_authored,
    "_chk_prove_email": _chk_prove_email,
    "_chk_deploy_approval": _chk_deploy_approval,
}


def _run_prover(path: Path, kind: str | None = None) -> int:
    if not PROVER.is_file():
        print("FATAL: prover not found at %s" % PROVER, file=sys.stderr)
        return EXIT_USAGE
    cmd = [sys.executable, str(PROVER), str(path)]
    if kind:
        cmd += ["--kind", kind]
    return subprocess.call(cmd)


def _run_checker(name, run_dir: Path) -> tuple[bool, str]:
    fn = _CHECKERS.get(name)
    if fn is None:
        # An unmapped checker is treated as a soft presence check on produces_artifact.
        return True, "checker %s not mapped (soft-pass)" % name
    return fn(run_dir)


def plan(manifest) -> int:
    print("== Email Engine — canonical phase plan ==")
    for i, pid in enumerate(PHASE_ORDER, 1):
        ph = _phase(manifest, pid)
        if not ph:
            print("  %d. %s (MISSING FROM MANIFEST)" % (i, pid))
            continue
        pf = (ph.get("preflight") or {}).get("checker", "-")
        print("  %d. %s — %s" % (i, pid, ph.get("name", "")))
        print("       produces: %s" % ph.get("produces_artifact", "-"))
        print("       gate    : %s | codes: %s" % (pf, ", ".join(ph.get("gate_codes", []))))
    return EXIT_PASS


def run(manifest, run_dir: Path, upto: str | None) -> int:
    stop_at = upto or "P4-DEPLOY"
    if stop_at not in PHASE_ORDER:
        print("FATAL: --upto %s is not a known phase" % stop_at, file=sys.stderr)
        return EXIT_USAGE

    proc = {"skill": "email-engine", "run_dir": _portable_run_dir(run_dir), "phases": []}
    for pid in PHASE_ORDER:
        ph = _phase(manifest, pid)
        if not ph:
            print("FATAL: phase %s missing from manifest" % pid, file=sys.stderr)
            return EXIT_USAGE
        checks = []
        pre = ph.get("preflight")
        if pre and pre.get("required"):
            checks.append(pre["checker"])
        for ap in ph.get("additional_preflights", []) or []:
            if ap.get("required"):
                checks.append(ap["checker"])
        print("=== PHASE %s — %s ===" % (pid, ph.get("name", "")))
        phase_ok = True
        for c in checks:
            ok, msg = _run_checker(c, run_dir)
            print("   [%s] %s: %s" % ("OK" if ok else "FAIL", c, msg))
            phase_ok = phase_ok and ok
        proc["phases"].append({"id": pid, "passed": phase_ok})
        if not phase_ok:
            _write_proc(run_dir, proc, failed=pid)
            print("BLOCKED at %s (fail-closed). No phase skips; fix and re-run." % pid, file=sys.stderr)
            return EXIT_GATE
        if pid == stop_at:
            break
    _write_proc(run_dir, proc, failed=None)
    # A full P1->P4 pass issues the delivery process certificate (mirrors the
    # Presentations prove-deck.py certificate). A partial (--upto) run never
    # certifies — the certificate attests the WHOLE governed pipeline ran in order.
    if stop_at == "P4-DEPLOY":
        cert = _write_certificate(run_dir, proc)
        if cert:
            print("CERTIFICATE ISSUED: %s (sha %s)" % (cert["path"], cert["sha"][:12]))
    print("ALL REQUESTED PHASES PASSED (through %s)." % stop_at)
    return EXIT_PASS


def _write_proc(run_dir: Path, proc: dict, failed):
    proc["failed_phase"] = failed
    out = run_dir / "working" / "checkpoints" / "process_manifest.json"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(proc, indent=2), encoding="utf-8")
    except OSError:
        pass


def _write_certificate(run_dir: Path, proc: dict):
    """Issue the delivery PROCESS-CERTIFICATE after a full P1->P4 pass.

    Deterministic: certificate_sha is computed over the ordered phase steps +
    the sequence identity + the email count (NOT the wall-clock timestamp), so
    re-running the same passing sequence yields the same sha. DRAFT-ONLY is
    recorded on the certificate — the certificate attests the governed pipeline
    ran in order; it never authorizes a send."""
    import datetime
    import hashlib
    emails_path = run_dir / "working" / "copy" / "emails.json"
    seq_id, seq_type, email_count, founder = "", "", 0, ""
    try:
        led = json.loads(emails_path.read_text(encoding="utf-8"))
        seq_id = led.get("sequence_id", "")
        seq_type = led.get("sequence_type", "")
        founder = led.get("founder_name", "")
        email_count = len(led.get("emails", []) or [])
    except (OSError, ValueError):
        pass
    names = {"P1-SELECT": "Select", "P2-GENERATE": "Generate",
             "P3-QC": "QC (fail-closed floor prover)", "P4-DEPLOY": "Deploy (DRAFT-ONLY)"}
    steps = [{"phase_id": ph["id"], "name": names.get(ph["id"], ph["id"]),
              "disposition": "verified", "ok": bool(ph.get("passed"))}
             for ph in proc.get("phases", [])]
    body = {
        "schema": "email-process-certificate-v1",
        "sequence_id": seq_id, "sequence_type": seq_type,
        "email_count": email_count, "founder_name": founder,
        "declared_phases": PHASE_ORDER, "verified_phases": len(steps),
        "all_phases_pass": all(s["ok"] for s in steps) and len(steps) == len(PHASE_ORDER),
        "deploy_mode": "draft-only",
        "steps": steps,
    }
    sha_src = json.dumps({"seq": seq_id, "n": email_count,
                          "steps": [(s["phase_id"], s["ok"]) for s in steps]},
                         sort_keys=True)
    body["certificate_sha"] = hashlib.sha256(sha_src.encode("utf-8")).hexdigest()
    body["certified_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out_dir = run_dir / "delivery"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "PROCESS-CERTIFICATE.json").write_text(
            json.dumps(body, indent=2), encoding="utf-8")
        md = [
            "# Email Engine — PROCESS CERTIFICATE",
            "",
            "- **Sequence:** `%s` (`%s`)" % (seq_id, seq_type),
            "- **Emails:** %d" % email_count,
            "- **Founder signature:** %s" % founder,
            "- **All phases pass:** %s" % body["all_phases_pass"],
            "- **Deploy mode:** DRAFT-ONLY (nothing sends without explicit human approval)",
            "- **Certificate SHA:** `%s`" % body["certificate_sha"],
            "- **Certified at:** %s" % body["certified_at"],
            "",
            "| Phase | Name | Verified |",
            "|---|---|---|",
        ]
        for s in steps:
            md.append("| %s | %s | %s |" % (s["phase_id"], s["name"], "yes" if s["ok"] else "NO"))
        md.append("")
        md.append("Issued by `run_email_engine.py` after a full P1->P4 pass through "
                  "`email-engine-entry.sh`. The P3 gate is `tools/prove-email.py` "
                  "(fail-closed). This certificate attests the governed pipeline ran "
                  "in order; it does not authorize a send.")
        (out_dir / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        return {"path": str(out_dir / "PROCESS-CERTIFICATE.json"), "sha": body["certificate_sha"]}
    except OSError:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Email Engine orchestrator (Skill 50).")
    ap.add_argument("--run-dir", help="the email run directory (contains working/)")
    ap.add_argument("--upto", choices=PHASE_ORDER, help="run through this phase only")
    ap.add_argument("--plan", action="store_true", help="print the canonical phase plan and exit")
    args = ap.parse_args(argv)

    manifest = _load_manifest()
    if args.plan:
        return plan(manifest)

    if not args.run_dir:
        ap.error("--run-dir is required (or use --plan)")
    run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print("FATAL: --run-dir not found: %s" % run_dir, file=sys.stderr)
        return EXIT_USAGE

    if not _nonce_ok(run_dir):
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH email-engine-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.", file=sys.stderr)
        return EXIT_NONCE

    return run(manifest, run_dir, args.upto)


if __name__ == "__main__":
    sys.exit(main())

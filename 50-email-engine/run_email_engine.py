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
CATALOG = _SKILL_DIR / "email-library" / "catalog-index.json"

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


def _canonical_ids():
    """Load the committed Superlibrary catalog and return {type: set(ids)}.
    Fail-closed: an unreadable/absent catalog yields empty sets, so every id then
    reads as non-canonical and the P1 selection gate BLOCKS — never a silent pass."""
    try:
        rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if isinstance(rows, dict):
        rows = rows.get("entries", [])
    by_type: dict[str, set] = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id") and r.get("type"):
            by_type.setdefault(r["type"], set()).add(r["id"])
    return by_type


def _email_match_violations(match: dict, brief: dict) -> list[tuple[str, str]]:
    """PURE P1-SELECT gate: the resolved selection (working/routing/email-match.json)
    must (a) resolve the brief to CANONICAL Superlibrary ids and (b) stay consistent
    with the brief it claims to route. Returns [(AF_CODE, message)]; [] == PASS.
    Fail-closed — this is the declared-required gate the manifest names."""
    ids = _canonical_ids()
    frameworks = ids.get("framework", set())
    objectives = ids.get("objective", set())
    personas = ids.get("persona-style", set())
    sequences = ids.get("sequence", set())
    buyertypes = ids.get("buyer-type", set())

    if not isinstance(match, dict):
        return [("AF-EMAIL-TYPE-MISMATCH", "email-match.json root is not a JSON object")]
    fails = []
    if match.get("skill") not in (None, "email-engine"):
        fails.append(("AF-EMAIL-TYPE-MISMATCH",
                      "email-match.json skill is %r, expected 'email-engine'" % match.get("skill")))
    resolved = match.get("resolved")
    if not isinstance(resolved, dict):
        return fails + [("AF-EMAIL-TYPE-MISMATCH",
                         "email-match.json carries no resolved{} selection object")]

    seq_id = resolved.get("sequence_id")
    obj_id = resolved.get("objective_id")
    bt_id = resolved.get("buyer_type_id")
    persona_id = resolved.get("persona_style_id")
    fw_ids = resolved.get("framework_ids") or []

    # --- canonical membership (the matched ids must be real library entries) ---
    if seq_id not in sequences:
        fails.append(("AF-EMAIL-TYPE-MISMATCH",
                      "resolved.sequence_id %r is not a canonical sequence id" % seq_id))
    if obj_id not in objectives:
        fails.append(("AF-EMAIL-OBJECTIVE-INVALID",
                      "resolved.objective_id %r is not a canonical objective id" % obj_id))
    if not isinstance(fw_ids, list) or not fw_ids:
        fails.append(("AF-EMAIL-FRAMEWORK-UNKNOWN",
                      "resolved.framework_ids is empty — no framework was selected"))
    else:
        for fid in fw_ids:
            if fid not in frameworks:
                fails.append(("AF-EMAIL-FRAMEWORK-UNKNOWN",
                              "resolved framework %r is not a canonical framework id" % fid))
    if persona_id not in (None, "") and persona_id not in personas:
        fails.append(("AF-EMAIL-PERSONA-INVALID",
                      "resolved.persona_style_id %r is not a canonical persona-style id" % persona_id))
    if bt_id not in (None, "", "all") and bt_id not in buyertypes:
        fails.append(("AF-EMAIL-BUYERTYPE-MAP",
                      "resolved.buyer_type_id %r is not a canonical buyer-type id" % bt_id))

    # --- consistency with the brief (the selection must resolve THIS brief) ---
    answers = brief.get("answers") if isinstance(brief, dict) else None
    if isinstance(answers, dict):
        b_obj = str(answers.get("objective", "")).strip()
        if b_obj and obj_id and obj_id != ("objective-" + b_obj):
            fails.append(("AF-EMAIL-TYPE-MISMATCH",
                          "resolved.objective_id %r does not match the brief objective %r"
                          % (obj_id, b_obj)))
        b_seq = str(answers.get("sequence_position", "")).strip()
        if b_seq and seq_id and seq_id != ("sequence-" + b_seq):
            fails.append(("AF-EMAIL-TYPE-MISMATCH",
                          "resolved.sequence_id %r does not match the brief sequence_position %r"
                          % (seq_id, b_seq)))
    return fails


def _chk_email_match(run_dir: Path) -> tuple[bool, str]:
    """P1-SELECT additional preflight (declared required in EMAIL-MANIFEST.json).
    Proves email_matcher resolved the brief to a canonical framework/buyer-type/
    objective/sequence and produced working/routing/email-match.json. Was a silent
    no-op before (unmapped -> soft-pass); now a real fail-closed gate."""
    match_path = run_dir / "working" / "routing" / "email-match.json"
    if not match_path.is_file():
        return False, ("AF-EMAIL-TYPE-MISMATCH: missing working/routing/email-match.json "
                       "(P1 selection not resolved — run email_matcher_cli.py and record the "
                       "resolved ids)")
    try:
        match = json.loads(match_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return False, "AF-EMAIL-TYPE-MISMATCH: email-match.json unreadable: %s" % exc
    brief = {}
    brief_path = run_dir / "working" / "copy" / "brief.json"
    if brief_path.is_file():
        try:
            brief = json.loads(brief_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            brief = {}
    fails = _email_match_violations(match, brief)
    if fails:
        return False, "; ".join("%s: %s" % (c, m) for c, m in fails)
    return True, "selection resolved to canonical Superlibrary entries (consistent with the brief)"


_CHECKERS = {
    "_chk_email_brief": _chk_email_brief,
    "_chk_email_match": _chk_email_match,
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
        # Fail-closed: a required checker named in the manifest but not mapped here is
        # a DISABLED gate, not a pass. The Email Engine's design law is enforcement,
        # not description — an unmapped gate BLOCKS (never a silent soft-pass, which
        # would let a manifest/checker-name drift disable a gate invisibly).
        return False, ("checker %s is not mapped — fail-closed (a required gate cannot "
                       "be a silent no-op)" % name)
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


def self_test() -> int:
    """Built-in gate self-test — proves the P1 selection gate (_chk_email_match)
    and the fail-closed unmapped-checker actually BITE. VALID golden fixture passes;
    each adversarial fixture trips its distinct AF code. No nonce/run needed."""
    import tempfile
    ok = True

    def _ck(label, cond):
        nonlocal ok
        cond = bool(cond)
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    ids = _canonical_ids()
    _ck("catalog canonical ids load (framework/objective/sequence non-empty)",
        ids.get("framework") and ids.get("objective") and ids.get("sequence"))

    golden_brief = {
        "kind": "intake", "skill": "email-engine",
        "answers": {"objective": "promotional", "sequence_position": "landing-page-10-promo"},
    }
    golden_match = {
        "skill": "email-engine",
        "resolved": {
            "sequence_id": "sequence-landing-page-10-promo",
            "objective_id": "objective-promotional",
            "buyer_type_id": "all",
            "framework_ids": ["framework-pastor-solutions", "framework-pas"],
            "persona_style_id": None,
        },
    }
    _ck("VALID golden match -> no violations",
        _email_match_violations(golden_match, golden_brief) == [])

    def _codes(mut):
        m = json.loads(json.dumps(golden_match))
        mut(m)
        return [c for c, _ in _email_match_violations(m, golden_brief)]

    _ck("VIOLATION framework-unknown -> AF-EMAIL-FRAMEWORK-UNKNOWN",
        "AF-EMAIL-FRAMEWORK-UNKNOWN" in _codes(
            lambda m: m["resolved"].__setitem__("framework_ids", ["framework-webinar"])))
    _ck("VIOLATION objective-invalid -> AF-EMAIL-OBJECTIVE-INVALID",
        "AF-EMAIL-OBJECTIVE-INVALID" in _codes(
            lambda m: m["resolved"].__setitem__("objective_id", "objective-newsletter")))
    _ck("VIOLATION persona-invalid -> AF-EMAIL-PERSONA-INVALID",
        "AF-EMAIL-PERSONA-INVALID" in _codes(
            lambda m: m["resolved"].__setitem__("persona_style_id", "persona-style-oprah")))
    _ck("VIOLATION brief-mismatch objective -> AF-EMAIL-TYPE-MISMATCH",
        "AF-EMAIL-TYPE-MISMATCH" in _codes(
            lambda m: m["resolved"].__setitem__("objective_id", "objective-upsell")))
    _ck("VIOLATION brief-mismatch sequence -> AF-EMAIL-TYPE-MISMATCH",
        "AF-EMAIL-TYPE-MISMATCH" in _codes(
            lambda m: m["resolved"].__setitem__("sequence_id", "sequence-high-ticket-appointment")))

    # unmapped checker must be fail-closed (was a silent soft-pass).
    with tempfile.TemporaryDirectory() as td:
        good, _ = _run_checker("_chk_does_not_exist", Path(td))
        _ck("unmapped checker -> fail-closed (not soft-pass)", good is False)

    # _chk_email_match end-to-end against a temp run dir.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td)
        (rd / "working" / "routing").mkdir(parents=True)
        (rd / "working" / "copy").mkdir(parents=True)
        good, _ = _chk_email_match(rd)
        _ck("_chk_email_match missing file -> FAIL", good is False)
        (rd / "working" / "copy" / "brief.json").write_text(json.dumps(golden_brief), encoding="utf-8")
        (rd / "working" / "routing" / "email-match.json").write_text(
            json.dumps(golden_match), encoding="utf-8")
        good, _ = _chk_email_match(rd)
        _ck("_chk_email_match golden -> PASS", good is True)
        (rd / "working" / "routing" / "email-match.json").write_text(json.dumps(
            {"skill": "email-engine", "resolved": {
                "sequence_id": "sequence-nope", "objective_id": "objective-promotional",
                "framework_ids": ["framework-pas"]}}), encoding="utf-8")
        good, _ = _chk_email_match(rd)
        _ck("_chk_email_match non-canonical sequence -> FAIL", good is False)

    print("== run_email_engine self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Email Engine orchestrator (Skill 50).")
    ap.add_argument("--run-dir", help="the email run directory (contains working/)")
    ap.add_argument("--upto", choices=PHASE_ORDER, help="run through this phase only")
    ap.add_argument("--plan", action="store_true", help="print the canonical phase plan and exit")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in gate self-tests (P1 selection + unmapped-checker) and exit")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

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

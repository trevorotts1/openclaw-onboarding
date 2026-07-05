#!/usr/bin/env python3
"""run_anthology.py — the deterministic state machine over ANTHOLOGY-MANIFEST.json.

Walks the Anthology Writer phases IN ORDER, one contributor at a time
(P0-INTAKE -> P1-FIDELITY -> P2-TONE-AUTHOR -> P3-TONE-QC -> P4-TITLE-LOCK ->
P5-CHAPTER-AUTHOR -> P6-CHAPTER-QC -> P7-DELIVER) with NO phase skips. Each
phase's preflight is checked against the run directory's artifacts; the QC phases
shell out to the fail-closed provers in scripts/ and refuse to advance on ANY
AF-AW-* violation. This is a runnable STUB: it enforces phase ordering, artifact
presence, and the fail-closed gates; the LLM authoring steps are performed
upstream on the CLIENT's own NON-Anthropic provider chain and drop their
artifacts (working/tone-doc.md, working/title.json, working/outline.md,
working/chapter.md, working/RUN-LEDGER.json) into the run dir.

FRONT-DOOR NONCE: like the sibling engines, this refuses to run unless
OC_ANTHOLOGY_ENTRY_NONCE matches the run-scoped nonce minted by anthology-entry.sh
(the ONE sanctioned entry). Model-free, provider-neutral: no LLM, no network.

A full P0->P6 pass issues the delivery PROCESS-CERTIFICATE (deterministic sha over
the ordered phase steps + contributor identity + MEASURED word counts, not the
wall clock). A partial (--upto) run never certifies.

EXIT CODES:
  0  all requested phases passed
  2  a phase gate failed (fail-closed)  [AF-AW-STAGE-SKIPPED / a prover AF]
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through anthology-entry.sh)
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
MANIFEST = _SKILL_DIR / "ANTHOLOGY-MANIFEST.json"
SCRIPTS = _SKILL_DIR / "scripts"
PROMPTS = _SKILL_DIR / "assets" / "prompts"

PHASE_ORDER = ["P0-INTAKE", "P1-FIDELITY", "P2-TONE-AUTHOR", "P3-TONE-QC",
               "P4-TITLE-LOCK", "P5-CHAPTER-AUTHOR", "P6-CHAPTER-QC", "P7-DELIVER"]


def _portable_run_dir(run_dir: Path) -> str:
    rd = run_dir.resolve()
    try:
        return rd.relative_to(_SKILL_DIR).as_posix()
    except ValueError:
        return rd.name


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read ANTHOLOGY-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _phase(manifest, pid):
    for ph in manifest.get("phases", []):
        if ph.get("id") == pid:
            return ph
    return None


def _nonce_ok(run_dir: Path) -> bool:
    want = os.environ.get("OC_ANTHOLOGY_ENTRY_NONCE", "")
    nf = run_dir / "working" / "checkpoints" / ".anthology-entry-nonce"
    if not want or not nf.is_file():
        return False
    try:
        return nf.read_text(encoding="utf-8").strip() == want.strip()
    except OSError:
        return False


def _run_prover(script: str, *args) -> int:
    p = SCRIPTS / script
    if not p.is_file():
        print("FATAL: prover not found at %s" % p, file=sys.stderr)
        return EXIT_USAGE
    return subprocess.call([sys.executable, str(p), *args])


def _run_prover_json(script: str, *args):
    """Run a prover in --json mode, capturing its machine-readable result while
    still echoing it for the operator. Returns (rc, parsed_or_none). Used so the
    QC phases can persist the prover verdict to the manifest-declared qc report
    path (produces_artifact) instead of leaving that artifact unwritten."""
    p = SCRIPTS / script
    if not p.is_file():
        print("FATAL: prover not found at %s" % p, file=sys.stderr)
        return EXIT_USAGE, None
    proc = subprocess.run([sys.executable, str(p), *args, "--json"],
                          capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except (ValueError, TypeError):
        parsed = {"prover": script, "raw": proc.stdout.strip(), "returncode": proc.returncode}
    return proc.returncode, parsed


def _write_qc_report(run_dir: Path, name: str, obj) -> None:
    """Persist a QC prover verdict to working/qc/<name> (the manifest's declared
    produces_artifact for the QC phases). Best-effort: a report-write failure
    must never mask the gate's own PASS/FAIL decision."""
    out = run_dir / "working" / "qc" / name
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    except OSError:
        pass


# ---- phase checkers ---------------------------------------------------------
def _chk_intake(run_dir: Path):
    f = run_dir / "working" / "intake.json"
    if not f.is_file():
        return False, "missing working/intake.json"
    rc = _run_prover("prove_aw_intake.py", str(f))
    return (rc == 0), ("intake PASS" if rc == 0 else "intake FAILED (exit %d)" % rc)


def _chk_fidelity(run_dir: Path):
    rc_f = _run_prover("prove_aw_fidelity.py", "--prompts-dir", str(PROMPTS),
                       "--manifest", str(MANIFEST))
    rc_t = _run_prover("verify_tone_core_sync.py")
    ok = (rc_f == 0 and rc_t == 0)
    return ok, ("prompt fidelity + tone-core sync PASS" if ok
                else "fidelity FAILED (prompts exit %d, tone-core exit %d)" % (rc_f, rc_t))


def _chk_tone_authored(run_dir: Path):
    f = run_dir / "working" / "tone-doc.md"
    return (f.is_file(), "tone-doc.md present" if f.is_file() else "missing working/tone-doc.md")


def _override_args(run_dir: Path):
    """The client-exact override channel wiring: pass the locked brief (intake)
    and, when present, the LOGGED overrides.json so an exact word target wins over
    the default band (recorded on the certificate). Absent overrides.json = the
    default SACRED bands (purely additive)."""
    args = []
    intake = run_dir / "working" / "intake.json"
    ov = run_dir / "working" / "overrides.json"
    if intake.is_file():
        args += ["--brief", str(intake)]
    if ov.is_file():
        args += ["--band-override", str(ov)]
    return args


def _chk_tone_qc(run_dir: Path):
    f = run_dir / "working" / "tone-doc.md"
    if not f.is_file():
        return False, "missing working/tone-doc.md for QC"
    rc, parsed = _run_prover_json("prove_aw_tone.py", str(f), *_override_args(run_dir))
    _write_qc_report(run_dir, "tone_qc_report.json", parsed)
    return (rc == 0), ("tone QC PASS" if rc == 0 else "tone QC FAILED (exit %d)" % rc)


def _chk_title_locked(run_dir: Path):
    f = run_dir / "working" / "title.json"
    if not f.is_file():
        return False, "missing working/title.json"
    try:
        obj = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False, "working/title.json unreadable/invalid"
    if not str(obj.get("title", "")).strip() or not str(obj.get("subtitle", "")).strip():
        return False, "title.json missing a non-empty title/subtitle (AF-AW-TITLE-MISSING)"
    return True, "title/subtitle locked"


def _chk_chapter_authored(run_dir: Path):
    outline = run_dir / "working" / "outline.md"
    chapter = run_dir / "working" / "chapter.md"
    if not outline.is_file():
        return False, "missing working/outline.md"
    if not chapter.is_file():
        return False, "missing working/chapter.md"
    return True, "outline.md + chapter.md present"


def _chk_chapter_qc(run_dir: Path):
    chapter = run_dir / "working" / "chapter.md"
    outline = run_dir / "working" / "outline.md"
    title = run_dir / "working" / "title.json"
    intake = run_dir / "working" / "intake.json"
    ledger = run_dir / "working" / "RUN-LEDGER.json"
    if not chapter.is_file():
        return False, "missing working/chapter.md for QC"
    # Model-sovereignty is FAIL-CLOSED at P6: a chapter cannot certify without the
    # run ledger that records the (NON-Anthropic) provenance it was authored on.
    # Was fail-OPEN (build-check ran only `if ledger.is_file()`), so a run with no
    # ledger sailed through the no-Anthropic gate unproven.
    if not ledger.is_file():
        _write_qc_report(run_dir, "chapter_qc_report.json",
                         {"prover": "run_anthology._chk_chapter_qc", "passed": False,
                          "violations": [{"code": "AF-AW-PROVENANCE-MISSING",
                                          "message": "working/RUN-LEDGER.json is required at "
                                          "P6-CHAPTER-QC (model provenance / no-Anthropic proof)"}]})
        return False, ("AF-AW-PROVENANCE-MISSING: working/RUN-LEDGER.json is required at "
                       "P6-CHAPTER-QC — a chapter cannot certify without its NON-Anthropic "
                       "model provenance")
    args_common = []
    if title.is_file():
        args_common += ["--title", str(title)]
    if intake.is_file():
        args_common += ["--intake", str(intake)]
    ov_args = _override_args(run_dir)
    report = {"prover": "run_anthology._chk_chapter_qc", "parts": {}}
    rc_ch, p_ch = _run_prover_json("prove_aw_chapter.py", str(chapter), "--mode", "chapter",
                                   *args_common, *ov_args)
    report["parts"]["chapter"] = p_ch
    rc_ol, p_ol = 0, None
    if outline.is_file():
        rc_ol, p_ol = _run_prover_json("prove_aw_chapter.py", str(outline), "--mode", "outline",
                                       *args_common)
        report["parts"]["outline"] = p_ol
    rc_bc, p_bc = _run_prover_json("aw_build_check.py", str(ledger))
    report["parts"]["build_check"] = p_bc
    ok = (rc_ch == 0 and rc_ol == 0 and rc_bc == 0)
    report["passed"] = ok
    _write_qc_report(run_dir, "chapter_qc_report.json", report)
    return ok, ("chapter QC PASS" if ok else
                "chapter QC FAILED (chapter exit %d, outline exit %d, build-check exit %d)"
                % (rc_ch, rc_ol, rc_bc))


def _chk_deliver(run_dir: Path):
    """P7 delivery gate — assemble the slug-labeled LOCAL bundle from the QC'd
    working copies and verify it byte-for-byte. Fail-closed: the artifacts that
    passed P3/P4/P6 (chapter + tone doc + outline + locked title) MUST be present
    (else AF-AW-STAGE-SKIPPED); a pre-existing delivery artifact that DISAGREES
    with its QC'd working source is refused (a swap-after-QC / planted deliverable,
    AF-AW-DELIVER-MISMATCH). The orchestrator is the SOLE writer of the bundle.
    Was an unconditional `return True` before — an evidence-free no-op that let P7
    pass (and certify) with no deliverable on disk (ported from Skill 55)."""
    import hashlib
    work = {
        "chapter.md": run_dir / "working" / "chapter.md",
        "tone-doc.md": run_dir / "working" / "tone-doc.md",
        "outline.md": run_dir / "working" / "outline.md",
        "title.json": run_dir / "working" / "title.json",
    }
    missing = [name for name, p in work.items() if not p.is_file()]
    if missing:
        return False, ("AF-AW-STAGE-SKIPPED: delivery requires the QC'd working copies; "
                       "missing working/%s" % ", working/".join(missing))
    intake = {}
    ipath = run_dir / "working" / "intake.json"
    if ipath.is_file():
        try:
            intake = json.loads(ipath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            intake = {}
    slug = _slug(intake)
    out_dir = run_dir / "delivery"
    labeled = {
        "chapter-%s.md" % slug: work["chapter.md"],
        "tone-doc-%s.md" % slug: work["tone-doc.md"],
        "outline-%s.md" % slug: work["outline.md"],
        "title-%s.json" % slug: work["title.json"],
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for label, src in labeled.items():
            src_bytes = src.read_bytes()
            dst = out_dir / label
            if dst.is_file() and dst.read_bytes() != src_bytes:
                return False, ("AF-AW-DELIVER-MISMATCH: delivery/%s disagrees with the QC'd "
                               "working copy (swap-after-QC / planted deliverable)" % label)
            dst.write_bytes(src_bytes)
            if hashlib.sha256(dst.read_bytes()).hexdigest() != hashlib.sha256(src_bytes).hexdigest():
                return False, ("AF-AW-DELIVER-MISMATCH: delivery/%s did not round-trip "
                               "byte-identical to the working copy" % label)
    except OSError as exc:
        return False, "AF-AW-STAGE-SKIPPED: could not assemble the delivery bundle: %s" % exc
    return True, ("labeled delivery bundle assembled + byte-verified against the QC'd working "
                  "copies (chapter/tone-doc/outline/title-%s); no n8n/Airtable/Drive/Slack/Gmail"
                  % slug)


_CHECKERS = {
    "_chk_intake": _chk_intake,
    "_chk_fidelity": _chk_fidelity,
    "_chk_tone_authored": _chk_tone_authored,
    "_chk_tone_qc": _chk_tone_qc,
    "_chk_title_locked": _chk_title_locked,
    "_chk_chapter_authored": _chk_chapter_authored,
    "_chk_chapter_qc": _chk_chapter_qc,
    "_chk_deliver": _chk_deliver,
}


def _run_checker(name, run_dir: Path):
    fn = _CHECKERS.get(name)
    if fn is None:
        # Fail-CLOSED: an unmapped required checker is a DISABLED gate, not a pass.
        # Enforcement, not description — a manifest/checker-name drift must BLOCK,
        # never silently soft-pass a required phase (ported from Skill 55).
        return False, ("checker %s is not mapped — fail-closed (a required gate cannot be a "
                       "silent no-op)" % name)
    return fn(run_dir)


def plan(manifest) -> int:
    print("== Anthology Writer — canonical phase plan ==")
    for i, pid in enumerate(PHASE_ORDER):
        ph = _phase(manifest, pid)
        if not ph:
            print("  %d. %s (MISSING FROM MANIFEST)" % (i, pid))
            continue
        pf = (ph.get("preflight") or {}).get("checker", "-")
        print("  %d. %s — %s" % (i, pid, ph.get("name", "")))
        print("       produces: %s" % ph.get("produces_artifact", "-"))
        print("       gate    : %s | codes: %s" % (pf, ", ".join(ph.get("gate_codes", []))))
    return EXIT_PASS


def run(manifest, run_dir: Path, upto) -> int:
    stop_at = upto or "P7-DELIVER"
    if stop_at not in PHASE_ORDER:
        print("FATAL: --upto %s is not a known phase" % stop_at, file=sys.stderr)
        return EXIT_USAGE

    proc = {"skill": "anthology-writer", "run_dir": _portable_run_dir(run_dir), "phases": []}
    for pid in PHASE_ORDER:
        ph = _phase(manifest, pid)
        if not ph:
            print("FATAL: phase %s missing from manifest" % pid, file=sys.stderr)
            return EXIT_USAGE
        pre = ph.get("preflight") or {}
        print("=== PHASE %s — %s ===" % (pid, ph.get("name", "")))
        phase_ok = True
        if pre.get("required"):
            ok, msg = _run_checker(pre["checker"], run_dir)
            print("   [%s] %s: %s" % ("OK" if ok else "FAIL", pre.get("checker"), msg))
            phase_ok = ok
        proc["phases"].append({"id": pid, "passed": phase_ok})
        if not phase_ok:
            _write_proc(run_dir, proc, failed=pid)
            print("BLOCKED at %s (fail-closed). No phase skips; fix and re-run." % pid,
                  file=sys.stderr)
            return EXIT_GATE
        if pid == stop_at:
            break
    _write_proc(run_dir, proc, failed=None)
    if stop_at == "P7-DELIVER":
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


def _measure(run_dir: Path):
    """Deterministic measured counts for the certificate (never self-reported)."""
    sys.path.insert(0, str(SCRIPTS))
    try:
        import _aw_common as c  # noqa: E402
    except Exception:
        return {"chapter_words": None, "tone_words": None}
    out = {"chapter_words": None, "tone_words": None}
    ch = run_dir / "working" / "chapter.md"
    tn = run_dir / "working" / "tone-doc.md"
    if ch.is_file():
        out["chapter_words"] = c.word_count(ch.read_text(encoding="utf-8"))
    if tn.is_file():
        out["tone_words"] = c.word_count(tn.read_text(encoding="utf-8"))
    return out


def _slug(intake: dict) -> str:
    import re
    base = "%s %s %s" % (intake.get("anthology_title", "anthology"),
                         intake.get("first_name", ""), intake.get("last_name", ""))
    slug = re.sub(r"[^a-z0-9]+", "-", base.strip().lower()).strip("-")
    return slug or "anthology"


def _load_client_override(run_dir: Path, intake: dict):
    """Resolve the LOGGED, brief-tied client-exact band override for the
    certificate (XC-12b). Returns None unless working/overrides.json is present
    AND passes the audited-channel check in _aw_common.resolve_band_override
    (recorded / approved / reasoned / tied to the locked brief). An unlogged
    override never reaches here — the QC provers already fail closed on it."""
    ov_path = run_dir / "working" / "overrides.json"
    if not ov_path.is_file():
        return None
    try:
        ov = json.loads(ov_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    sys.path.insert(0, str(SCRIPTS))
    try:
        import _aw_common as c  # noqa: E402
    except Exception:
        return None
    keys = ("chapter_word_min", "chapter_word_max", "tone_word_floor")
    status, _reason, applied = c.resolve_band_override(ov, intake, keys)
    if status != "applied":
        return None
    return {"source": ov.get("source"), "approved_by": ov.get("approved_by"),
            "reason": ov.get("reason"), "brief_ref": ov.get("brief_ref"),
            "applied_bands": applied}


def _write_certificate(run_dir: Path, proc: dict):
    """Issue the delivery PROCESS-CERTIFICATE after a full P0->P6 pass. All phases
    must have passed; otherwise AF-AW-PROCESS-INTEGRITY (no certificate).
    certificate_sha is computed over the ordered phase steps + the contributor
    identity + the MEASURED counts (not the wall clock), so re-running the same
    passing artifacts yields the same sha (idempotent)."""
    import datetime
    import hashlib
    intake = {}
    ipath = run_dir / "working" / "intake.json"
    if ipath.is_file():
        try:
            intake = json.loads(ipath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            intake = {}
    steps = [{"phase_id": ph["id"], "disposition": "verified", "ok": bool(ph.get("passed"))}
             for ph in proc.get("phases", [])]
    all_pass = all(s["ok"] for s in steps) and len(steps) == len(PHASE_ORDER)
    if not all_pass:
        print("AF-AW-PROCESS-INTEGRITY: refusing to certify — not a full P0->P6 pass.",
              file=sys.stderr)
        return None
    measured = _measure(run_dir)
    client_override = _load_client_override(run_dir, intake)
    contributor = ("%s %s" % (intake.get("first_name", ""), intake.get("last_name", ""))).strip()
    body = {
        "schema": "anthology-writer-process-certificate-v1",
        "anthology_title": intake.get("anthology_title", ""),
        "contributor": contributor,
        "slug": _slug(intake),
        "measured_chapter_words": measured["chapter_words"],
        "measured_tone_words": measured["tone_words"],
        "client_band_override": client_override,
        "declared_phases": PHASE_ORDER,
        "verified_phases": len(steps),
        "all_phases_pass": all_pass,
        "runtime": "local-only (no n8n / Airtable / Google Drive / Slack / Gmail); client's own NON-Anthropic providers",
        "steps": steps,
    }
    sha_fields = {
        "slug": body["slug"],
        "chapter_words": measured["chapter_words"],
        "tone_words": measured["tone_words"],
        "steps": [(s["phase_id"], s["ok"]) for s in steps],
    }
    # Bind an APPLIED client-exact override into the certificate sha (so a run
    # certified under an override reproduces a DIFFERENT sha than the default
    # band). No override => sha_fields unchanged => the default-band sha is stable.
    if client_override:
        sha_fields["client_band_override"] = client_override["applied_bands"]
    sha_src = json.dumps(sha_fields, sort_keys=True)
    body["certificate_sha"] = hashlib.sha256(sha_src.encode("utf-8")).hexdigest()
    body["certified_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out_dir = run_dir / "delivery"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "PROCESS-CERTIFICATE.json").write_text(
            json.dumps(body, indent=2), encoding="utf-8")
        md = [
            "# Anthology Writer — PROCESS CERTIFICATE",
            "",
            "- **Anthology:** %s" % body["anthology_title"],
            "- **Contributor:** %s (`%s`)" % (contributor, body["slug"]),
            "- **Measured chapter words:** %s (stripped; self-report ignored)" % measured["chapter_words"],
            "- **Measured tone-doc words:** %s (stripped)" % measured["tone_words"],
            "- **Client-exact band override:** %s" % (
                "applied — %s (by %s): %s" % (client_override["source"], client_override["approved_by"],
                                              client_override["applied_bands"])
                if client_override else "none (default SACRED bands)"),
            "- **All phases pass:** %s" % all_pass,
            "- **Runtime:** local-only; client's own NON-Anthropic providers",
            "- **Certificate SHA:** `%s`" % body["certificate_sha"],
            "- **Certified at:** %s" % body["certified_at"],
            "",
            "| Phase | Verified |",
            "|---|---|",
        ]
        for s in steps:
            md.append("| %s | %s |" % (s["phase_id"], "yes" if s["ok"] else "NO"))
        md.append("")
        md.append("Issued by `run_anthology.py` after a full P0->P6 pass through "
                  "`anthology-entry.sh`. QC gates are the fail-closed provers in "
                  "`scripts/`. No certificate = not done.")
        (out_dir / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        return {"path": str(out_dir / "PROCESS-CERTIFICATE.json"), "sha": body["certificate_sha"]}
    except OSError:
        return None


def self_test() -> int:
    """Built-in gate self-test — proves the P7 delivery gate (_chk_deliver) and the
    fail-closed unmapped-checker actually BITE (both were evidence-free no-ops
    before this fix). VALID fixture assembles + byte-verifies the labeled bundle;
    adversarial fixtures trip their AF codes. No nonce / run needed."""
    import tempfile
    ok = True

    def _ck(label, cond):
        nonlocal ok
        cond = bool(cond)
        ok = ok and cond
        print("  [%s] %s" % ("PASS" if cond else "MISS", label))

    # unmapped checker must be fail-closed (was a silent soft-pass).
    with tempfile.TemporaryDirectory() as td:
        good, _ = _run_checker("_chk_does_not_exist", Path(td))
        _ck("unmapped checker -> fail-closed (not soft-pass)", good is False)

    intake = {"anthology_title": "Unbroken Ground", "first_name": "Marcus", "last_name": "Bell",
              "chapter_premise": "x"}
    slug = _slug(intake)

    def _seed(rd: Path):
        (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        (rd / "working" / "chapter.md").write_text("# Chapter\nthe QC'd chapter body\n", encoding="utf-8")
        (rd / "working" / "tone-doc.md").write_text("# The Marcus Bell Tone\nbody\n", encoding="utf-8")
        (rd / "working" / "outline.md").write_text("# Outline\n- beat\n", encoding="utf-8")
        (rd / "working" / "title.json").write_text(
            json.dumps({"title": "Unbroken Ground", "subtitle": "Voices"}), encoding="utf-8")

    # missing working QC artifacts -> FAIL (no evidence-free pass).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver missing artifacts -> FAIL (AF-AW-STAGE-SKIPPED)",
            good is False and "AF-AW-STAGE-SKIPPED" in msg)

    # golden -> assembles + byte-verifies the labeled bundle.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd)
        good, _ = _chk_deliver(rd)
        _ck("_chk_deliver golden -> PASS", good is True)
        _ck("_chk_deliver assembled the labeled bundle",
            (rd / "delivery" / ("chapter-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("tone-doc-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("outline-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("title-%s.json" % slug)).is_file())

    # planted mismatch -> AF-AW-DELIVER-MISMATCH (swap-after-QC / stale deliverable).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd); (rd / "delivery").mkdir()
        (rd / "delivery" / ("chapter-%s.md" % slug)).write_text(
            "planted different bytes\n", encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver planted-mismatch -> FAIL (AF-AW-DELIVER-MISMATCH)",
            good is False and "AF-AW-DELIVER-MISMATCH" in msg)

    print("== run_anthology self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Anthology Writer orchestrator (Skill 54).")
    ap.add_argument("--run-dir", help="the anthology run directory (contains working/)")
    ap.add_argument("--upto", choices=PHASE_ORDER, help="run through this phase only")
    ap.add_argument("--plan", action="store_true", help="print the canonical phase plan and exit")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in gate self-tests (P7 delivery + unmapped-checker) and exit")
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
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH anthology-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.",
              file=sys.stderr)
        return EXIT_NONCE
    return run(manifest, run_dir, args.upto)


if __name__ == "__main__":
    sys.exit(main())

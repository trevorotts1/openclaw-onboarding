#!/usr/bin/env python3
"""run_product_bio.py — the deterministic state machine over PRODUCT-BIO-MANIFEST.json.

Walks the Product Bio phases IN ORDER (P0-INTAKE -> P1-FIDELITY -> P2-BIO-AUTHOR
-> P3-BIO-QC -> P4-HTML-AUTHOR -> P5-HTML-QC -> P6-DELIVER) with NO phase skips.
Each phase's preflight is checked against the run directory's artifacts; the QC
phases shell out to the fail-closed provers in scripts/ and refuse to advance on
ANY AF-PB-* violation. This is a runnable STUB: it enforces phase ordering,
artifact presence, and the fail-closed gates; the two LLM authoring steps (P2/P4)
are performed upstream on the CLIENT's own provider chain and drop their
artifacts (working/product-bio.md, working/product-bio.html) into the run dir.

FRONT-DOOR NONCE: like the Email/Presentations canonical orchestrators, this
refuses to run unless OC_PRODUCT_BIO_ENTRY_NONCE matches the run-scoped nonce
minted by product-bio-entry.sh (the ONE sanctioned entry). Model-free,
provider-neutral: it calls no LLM and no external service.

A full P0->P5 pass issues the delivery PROCESS-CERTIFICATE (deterministic sha
over the ordered phase steps + product identity + MEASURED word/close counts,
not the wall clock). A partial (--upto) run never certifies.

EXIT CODES:
  0  all requested phases passed
  2  a phase gate failed (fail-closed)  [AF-PB-STAGE-SKIPPED / a prover AF]
  3  usage / manifest error
  4  front-door nonce missing/mismatch (run through product-bio-entry.sh)
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
MANIFEST = _SKILL_DIR / "PRODUCT-BIO-MANIFEST.json"
SCRIPTS = _SKILL_DIR / "scripts"
PROMPTS = _SKILL_DIR / "assets" / "prompts"

PHASE_ORDER = ["P0-INTAKE", "P1-FIDELITY", "P2-BIO-AUTHOR", "P3-BIO-QC",
               "P4-HTML-AUTHOR", "P5-HTML-QC", "P6-DELIVER"]


def _portable_run_dir(run_dir: Path) -> str:
    """A machine-independent label for the run dir recorded in the certificate.
    Never bake an absolute filesystem path into a shipped artifact."""
    rd = run_dir.resolve()
    try:
        return rd.relative_to(_SKILL_DIR).as_posix()
    except ValueError:
        return rd.name


def _load_manifest():
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print("FATAL: cannot read PRODUCT-BIO-MANIFEST.json: %s" % exc, file=sys.stderr)
        sys.exit(EXIT_USAGE)


def _phase(manifest, pid):
    for ph in manifest.get("phases", []):
        if ph.get("id") == pid:
            return ph
    return None


def _nonce_ok(run_dir: Path) -> bool:
    want = os.environ.get("OC_PRODUCT_BIO_ENTRY_NONCE", "")
    nf = run_dir / "working" / "checkpoints" / ".product-bio-entry-nonce"
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


# ---- phase checkers ---------------------------------------------------------
def _chk_intake(run_dir: Path):
    f = run_dir / "working" / "intake.json"
    if not f.is_file():
        return False, "missing working/intake.json"
    rc = _run_prover("prove_pb_intake.py", str(f))
    return (rc == 0), ("intake PASS" if rc == 0 else "intake FAILED (exit %d)" % rc)


def _chk_fidelity(run_dir: Path):
    rc = _run_prover("prove_pb_fidelity.py", "--prompts-dir", str(PROMPTS))
    return (rc == 0), ("prompt fidelity PASS" if rc == 0 else "prompt fidelity FAILED (exit %d)" % rc)


def _chk_bio_authored(run_dir: Path):
    f = run_dir / "working" / "product-bio.md"
    return (f.is_file(), "product-bio.md present" if f.is_file() else "missing working/product-bio.md")


def _chk_bio_qc(run_dir: Path):
    bio = run_dir / "working" / "product-bio.md"
    if not bio.is_file():
        return False, "missing working/product-bio.md for QC"
    rc_w = _run_prover("prove_pb_wordcount.py", str(bio))
    rc_s = _run_prover("prove_pb_sections.py", str(bio))
    ok = (rc_w == 0 and rc_s == 0)
    return ok, ("bio QC PASS" if ok else "bio QC FAILED (wordcount exit %d, sections exit %d)" % (rc_w, rc_s))


def _chk_html_authored(run_dir: Path):
    f = run_dir / "working" / "product-bio.html"
    return (f.is_file(), "product-bio.html present" if f.is_file() else "missing working/product-bio.html")


def _chk_html_qc(run_dir: Path):
    html = run_dir / "working" / "product-bio.html"
    bio = run_dir / "working" / "product-bio.md"
    if not html.is_file():
        return False, "missing working/product-bio.html for QC"
    args = [str(html)]
    if bio.is_file():
        args += ["--source-bio", str(bio)]
    rc = _run_prover("prove_pb_html.py", *args)
    return (rc == 0), ("html QC PASS" if rc == 0 else "html QC FAILED (exit %d)" % rc)


def _chk_deliver(run_dir: Path):
    """P6 delivery gate — assemble the slug-labeled LOCAL bundle from the QC'd
    working copies and verify it byte-for-byte. Fail-closed: the bio + html that
    passed P3/P5 MUST be present (else AF-PB-STAGE-SKIPPED); a pre-existing
    delivery artifact that DISAGREES with the QC'd working copy is refused
    (a swap-after-QC / planted deliverable, AF-PB-DELIVER-MISMATCH). The
    orchestrator is the SOLE writer of the bundle. Was an unconditional
    `return True` before — an evidence-free no-op that let P6 pass (and certify)
    with no deliverable on disk."""
    import hashlib
    work = {
        "product-bio.md": run_dir / "working" / "product-bio.md",
        "product-bio.html": run_dir / "working" / "product-bio.html",
    }
    missing = [name for name, p in work.items() if not p.is_file()]
    if missing:
        return False, ("AF-PB-STAGE-SKIPPED: delivery requires the QC'd working copies; "
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
        "product-bio-%s.md" % slug: work["product-bio.md"],
        "product-bio-%s.html" % slug: work["product-bio.html"],
    }
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for label, src in labeled.items():
            src_bytes = src.read_bytes()
            dst = out_dir / label
            if dst.is_file() and dst.read_bytes() != src_bytes:
                return False, ("AF-PB-DELIVER-MISMATCH: delivery/%s disagrees with the QC'd "
                               "working copy (swap-after-QC / planted deliverable)" % label)
            dst.write_bytes(src_bytes)
            if hashlib.sha256(dst.read_bytes()).hexdigest() != hashlib.sha256(src_bytes).hexdigest():
                return False, ("AF-PB-DELIVER-MISMATCH: delivery/%s did not round-trip "
                               "byte-identical to the working copy" % label)
    except OSError as exc:
        return False, "AF-PB-STAGE-SKIPPED: could not assemble the delivery bundle: %s" % exc
    return True, ("labeled delivery bundle assembled + byte-verified against the QC'd "
                  "working copies (product-bio-%s.md/.html)" % slug)


_CHECKERS = {
    "_chk_intake": _chk_intake,
    "_chk_fidelity": _chk_fidelity,
    "_chk_bio_authored": _chk_bio_authored,
    "_chk_bio_qc": _chk_bio_qc,
    "_chk_html_authored": _chk_html_authored,
    "_chk_html_qc": _chk_html_qc,
    "_chk_deliver": _chk_deliver,
}


def _run_checker(name, run_dir: Path):
    fn = _CHECKERS.get(name)
    if fn is None:
        # Fail-closed: an unmapped required checker is a DISABLED gate, not a pass —
        # enforcement, not description. A manifest/checker-name drift must BLOCK,
        # never silently soft-pass a required phase.
        return False, ("checker %s is not mapped — fail-closed (a required gate cannot "
                       "be a silent no-op)" % name)
    return fn(run_dir)


def plan(manifest) -> int:
    print("== Product Bio — canonical phase plan ==")
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


def run(manifest, run_dir: Path, upto: str | None) -> int:
    stop_at = upto or "P6-DELIVER"
    if stop_at not in PHASE_ORDER:
        print("FATAL: --upto %s is not a known phase" % stop_at, file=sys.stderr)
        return EXIT_USAGE

    proc = {"skill": "product-bio", "run_dir": _portable_run_dir(run_dir), "phases": []}
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
    if stop_at == "P6-DELIVER":
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
        import _pb_common as c  # noqa: E402
    except Exception:
        return {"word_count": None, "closes": None}
    bio = run_dir / "working" / "product-bio.md"
    if not bio.is_file():
        return {"word_count": None, "closes": None}
    txt = bio.read_text(encoding="utf-8")
    return {"word_count": c.word_count(txt), "closes": len(c.closes_found(txt))}


def _slug(intake: dict) -> str:
    import re
    name = str(intake.get("product_name", "product")).strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", name).strip("-")
    return slug or "product"


def _write_certificate(run_dir: Path, proc: dict):
    """Issue the delivery PROCESS-CERTIFICATE after a full P0->P5 pass. All
    phases must have passed; otherwise AF-PB-PROCESS-INTEGRITY (no certificate).
    certificate_sha is computed over the ordered phase steps + the product
    identity + the MEASURED counts (not the wall-clock time), so re-running the
    same passing artifacts yields the same sha."""
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
        print("AF-PB-PROCESS-INTEGRITY: refusing to certify — not a full P0->P5 pass.",
              file=sys.stderr)
        return None
    measured = _measure(run_dir)
    body = {
        "schema": "product-bio-process-certificate-v1",
        "product_name": intake.get("product_name", ""),
        "product_slug": _slug(intake),
        "measured_word_count": measured["word_count"],
        "measured_signature_closes": measured["closes"],
        "declared_phases": PHASE_ORDER,
        "verified_phases": len(steps),
        "all_phases_pass": all_pass,
        "runtime": "local-only (no n8n / Google Drive / Slack / Gmail)",
        "steps": steps,
    }
    sha_src = json.dumps({
        "slug": body["product_slug"],
        "words": measured["word_count"],
        "closes": measured["closes"],
        "steps": [(s["phase_id"], s["ok"]) for s in steps],
    }, sort_keys=True)
    body["certificate_sha"] = hashlib.sha256(sha_src.encode("utf-8")).hexdigest()
    body["certified_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    out_dir = run_dir / "delivery"
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "PROCESS-CERTIFICATE.json").write_text(
            json.dumps(body, indent=2), encoding="utf-8")
        md = [
            "# Product Bio — PROCESS CERTIFICATE",
            "",
            "- **Product:** %s (`%s`)" % (body["product_name"], body["product_slug"]),
            "- **Measured word count:** %s (stripped; self-report ignored)" % measured["word_count"],
            "- **Measured signature closes:** %s / 24" % measured["closes"],
            "- **All phases pass:** %s" % all_pass,
            "- **Runtime:** local-only (no n8n / Google Drive / Slack / Gmail)",
            "- **Certificate SHA:** `%s`" % body["certificate_sha"],
            "- **Certified at:** %s" % body["certified_at"],
            "",
            "| Phase | Verified |",
            "|---|---|",
        ]
        for s in steps:
            md.append("| %s | %s |" % (s["phase_id"], "yes" if s["ok"] else "NO"))
        md.append("")
        md.append("Issued by `run_product_bio.py` after a full P0->P5 pass through "
                  "`product-bio-entry.sh`. QC gates are the fail-closed provers in "
                  "`scripts/`. No certificate = not done.")
        (out_dir / "PROCESS-CERTIFICATE.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        return {"path": str(out_dir / "PROCESS-CERTIFICATE.json"), "sha": body["certificate_sha"]}
    except OSError:
        return None


def self_test() -> int:
    """Built-in gate self-test — proves the P6 delivery gate (_chk_deliver) and the
    fail-closed unmapped-checker actually BITE. VALID fixture assembles + verifies
    the labeled bundle; adversarial fixtures trip their AF codes. No nonce/run needed."""
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

    intake = {"product_name": "AtlasFlow", "product_description": "x",
              "first_name": "A", "last_name": "B"}
    slug = _slug(intake)

    # missing working QC artifacts -> FAIL (no evidence-free pass).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        good, _ = _chk_deliver(rd)
        _ck("_chk_deliver missing bio/html -> FAIL", good is False)

    # golden -> assembles + byte-verifies the labeled bundle.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        (rd / "working" / "product-bio.md").write_text("# AtlasFlow\nQC'd bio body\n", encoding="utf-8")
        (rd / "working" / "product-bio.html").write_text(
            "<!DOCTYPE html>\n<h1>AtlasFlow</h1>\n</html>", encoding="utf-8")
        good, _ = _chk_deliver(rd)
        _ck("_chk_deliver golden -> PASS", good is True)
        _ck("_chk_deliver assembled the labeled bundle",
            (rd / "delivery" / ("product-bio-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("product-bio-%s.html" % slug)).is_file())

    # planted mismatch -> AF-PB-DELIVER-MISMATCH (swap-after-QC / stale deliverable).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir(); (rd / "delivery").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        (rd / "working" / "product-bio.md").write_text("# AtlasFlow\nthe real QC'd bio\n", encoding="utf-8")
        (rd / "working" / "product-bio.html").write_text(
            "<!DOCTYPE html>\n<h1>AtlasFlow</h1>\n</html>", encoding="utf-8")
        (rd / "delivery" / ("product-bio-%s.md" % slug)).write_text(
            "planted different bytes\n", encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver planted-mismatch -> FAIL (AF-PB-DELIVER-MISMATCH)",
            good is False and "AF-PB-DELIVER-MISMATCH" in msg)

    print("== run_product_bio self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Product Bio orchestrator (Skill 55).")
    ap.add_argument("--run-dir", help="the product-bio run directory (contains working/)")
    ap.add_argument("--upto", choices=PHASE_ORDER, help="run through this phase only")
    ap.add_argument("--plan", action="store_true", help="print the canonical phase plan and exit")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in gate self-tests (P6 delivery + unmapped-checker) and exit")
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
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH product-bio-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.",
              file=sys.stderr)
        return EXIT_NONCE
    return run(manifest, run_dir, args.upto)


if __name__ == "__main__":
    sys.exit(main())

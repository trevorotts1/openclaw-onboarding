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

# U059: the single durable per-participant run directory resolver lives in the
# sibling engine (59-anthology-engine). Both this orchestrator and every Skill 59
# stage dispatcher resolve the participant's working directory through the SAME
# function, so the gate artifacts this orchestrator checks (working/intake.json,
# working/avatar.md, working/tone-doc.md, ...) are exactly what the stages wrote.
_ANTHOLOGY_ENGINE_SCRIPTS = _SKILL_DIR.parent / "59-anthology-engine" / "scripts"
sys.path.insert(0, str(_ANTHOLOGY_ENGINE_SCRIPTS))
try:
    from anthology_run_dir import resolve_participant_run_dir  # noqa: E402
except Exception:  # pragma: no cover - resolver must resolve; fail loud at use site
    resolve_participant_run_dir = None

PHASE_ORDER = ["P0-INTAKE", "P0A-AVATAR", "P1-FIDELITY", "P2-TONE-AUTHOR", "P3-TONE-QC",
               "P4-TITLE-LOCK", "P5-CHAPTER-AUTHOR", "P6-CHAPTER-QC", "P7-DELIVER"]

# The failing (phase_id, note) captured at a gate failure so the fail-soft board
# seam (_mc_board_blocked, FIX-XC-06) can move the card to `blocked` with the AF
# code as the note. Mutated in place (no `global`) — read only by the board seam.
_LAST_BLOCK: dict = {}


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


def _chk_avatar(run_dir: Path):
    """P0A-AVATAR (pre-P1) — the Skill 52 avatar handoff gate. Fail-closed: the
    delegation to Skill 52 avatar-alchemist prompts 01..03 (referenced BY PATH,
    never copied) must have produced working/avatar.md, AND every referenced Skill
    52 prompt must resolve at its pinned path with a matching sha256, AND no Skill
    52 avatar prompt may be copied into this skill's tree. prove_aw_avatar.py
    decides the three AF-AW-AVATAR-* codes (a required, non-inert gate)."""
    f = run_dir / "working" / "avatar.md"
    if not f.is_file():
        return False, ("missing working/avatar.md (AF-AW-AVATAR-MISSING) — the Skill 52 avatar "
                       "handoff produced no dossier for the downstream authoring stages")
    try:
        empty = not f.read_text(encoding="utf-8").strip()
    except OSError:
        empty = True
    if empty:
        return False, ("working/avatar.md is empty/whitespace-only (AF-AW-AVATAR-MISSING) — the "
                       "Skill 52 avatar handoff produced no usable dossier")
    rc = _run_prover("prove_aw_avatar.py", str(f), "--manifest", str(MANIFEST))
    return (rc == 0), ("avatar handoff PASS (Skill 52 delegation intact, no copied IP)"
                       if rc == 0 else
                       "avatar handoff FAILED (exit %d) — see AF-AW-AVATAR-*" % rc)


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


def _blurb_defect(text: str):
    """Return a human reason string when the blurb is unfit to ship, else None. The
    blurb is a PROMISED deliverable (SKILL 'Delivery is local-only' names it in the
    bundle) — enforce it, don't just carry it (FIX-S36-55: it was never produced or
    gated). A present blurb must be finalized prose: non-empty stripped text, no
    unresolved placeholder, and more than a stub. MASTERDOC sets NO SACRED blurb word
    floor, so the >=20-word bar is only an anti-stub sanity minimum (never a
    floor-swap of a client-exact ask)."""
    import re
    stripped = (text or "").strip()
    if not stripped:
        return "working/blurb.md is empty (a finished back-cover blurb is required)"
    if re.search(r"\{\{.*?\}\}|\[\[.*?\]\]|<[A-Z][A-Z0-9_]{2,}>", text):
        return ("working/blurb.md carries an unresolved placeholder "
                "({{..}} / [[..]] / <ALLCAPS>) — the blurb is not finalized")
    words = len(re.findall(r"\S+", stripped))
    if words < 20:
        return ("working/blurb.md has only %d word(s) — too thin to be a finished blurb "
                "(anti-stub minimum 20; MASTERDOC sets no SACRED blurb floor)" % words)
    return None


def _chk_deliver(run_dir: Path):
    """P7 delivery gate — assemble the slug-labeled LOCAL bundle from the QC'd
    working copies and verify it byte-for-byte. Fail-closed: the artifacts that
    passed P3/P4/P6 (chapter + tone doc + outline + locked title) AND the promised
    blurb MUST be present (else AF-AW-STAGE-SKIPPED); a present-but-unfinished blurb
    fails closed (AF-AW-BLURB-MISSING, FIX-S36-55); a pre-existing delivery artifact
    that DISAGREES with its QC'd working source is refused (a swap-after-QC / planted
    deliverable, AF-AW-DELIVER-MISMATCH). The orchestrator is the SOLE writer of the
    bundle. Was an unconditional `return True` before — an evidence-free no-op that
    let P7 pass (and certify) with no deliverable on disk (ported from Skill 55)."""
    import hashlib
    work = {
        "chapter.md": run_dir / "working" / "chapter.md",
        "tone-doc.md": run_dir / "working" / "tone-doc.md",
        "outline.md": run_dir / "working" / "outline.md",
        "title.json": run_dir / "working" / "title.json",
        # FIX-S36-55: the blurb is a promised deliverable — required + gated here.
        "blurb.md": run_dir / "working" / "blurb.md",
    }
    missing = [name for name, p in work.items() if not p.is_file()]
    if missing:
        return False, ("AF-AW-STAGE-SKIPPED: delivery requires the QC'd working copies; "
                       "missing working/%s" % ", working/".join(missing))
    # BLURB gate (FIX-S36-55): a present blurb must be finished prose (not empty / a
    # stub / placeholder-bearing) before it can ship in the labeled bundle.
    b_defect = _blurb_defect(work["blurb.md"].read_text(encoding="utf-8"))
    if b_defect:
        return False, "AF-AW-BLURB-MISSING: %s" % b_defect
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
        "blurb-%s.md" % slug: work["blurb.md"],
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
                  "copies (chapter/tone-doc/outline/title/blurb-%s); no n8n/Airtable/Drive/Slack/Gmail"
                  % slug)


_CHECKERS = {
    "_chk_intake": _chk_intake,
    "_chk_avatar": _chk_avatar,
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
            _LAST_BLOCK.clear()
            _LAST_BLOCK.update({"phase_id": pid, "note": msg})
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
        # Assemble the labeled ~/Downloads bundle (chapter + tone doc + outline +
        # title + blurb + DELIVERY-NOTE + handoff + certificate). NON-FATAL: the run
        # is already certified and the run-dir delivery/ bundle already byte-verified
        # (FIX-S36-55 — the SKILL-promised ~/Downloads bundle is now actually written).
        _assemble_downloads_bundle(run_dir, cert, proc)
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


# ---------------------------------------------------------------------------
# Labeled LOCAL deliverable — the ~/Downloads bundle + DELIVERY-NOTE + handoff
# (FIX-S36-55). SKILL.md promises `~/Downloads/Anthology-<slug>-<MM-DD-YYYY>/`
# carrying the chapter, tone doc, outline, title, blurb, DELIVERY-NOTE.md,
# handoff.json, and the PROCESS-CERTIFICATE — before this fix only the run-dir
# certificate was written and that promise was unkept. State-path discipline (the
# Skill-23 lesson): the Downloads root is OVERRIDABLE via ANTHOLOGY_DELIVERY_ROOT
# so a test / verify run never writes into the operator's REAL ~/Downloads; it
# fails LOUDLY when neither the override nor $HOME resolves, never guessing a path.
# Mirrors Skill 55's run_product_bio._assemble_downloads_bundle.
# ---------------------------------------------------------------------------
_DELIVERY_ROOT_ENV = "ANTHOLOGY_DELIVERY_ROOT"
_BUNDLE_RECEIPT = ("working", "checkpoints", "delivery-bundle.json")


def _delivery_root(override=None):
    """Resolve the labeled-deliverable root. Precedence: explicit arg >
    ${ANTHOLOGY_DELIVERY_ROOT} > $HOME/Downloads. Returns None (the loud caller
    handles it) when nothing resolves — never a blind guess."""
    if override:
        return Path(override)
    env = os.environ.get(_DELIVERY_ROOT_ENV, "").strip()
    if env:
        return Path(env)
    home = os.environ.get("HOME") or os.path.expanduser("~")
    if home and home != "~":
        return Path(home) / "Downloads"
    return None


def _bundle_dir(root: Path, slug: str) -> Path:
    import datetime
    stamp = datetime.datetime.now().strftime("%m-%d-%Y")
    return root / ("Anthology-%s-%s" % (slug, stamp))


def _delivery_bundle_receipt(run_dir: Path) -> Path:
    return run_dir.joinpath(*_BUNDLE_RECEIPT)


def _assemble_downloads_bundle(run_dir: Path, cert, proc: dict, delivery_root=None):
    """Copy the byte-verified run-dir delivery/ artifacts into the labeled
    ~/Downloads bundle and write DELIVERY-NOTE.md + handoff.json alongside the
    certificate. Returns the receipt dict (also persisted to
    working/checkpoints/delivery-bundle.json) so the CC card can carry the delivery
    path + certificate sha. NON-FATAL: the run is already certified and the run-dir
    deliverable already byte-verified; a Downloads copy failure is logged LOUDLY and
    recorded (delivered:false) but never regresses the exit code."""
    import datetime
    intake = {}
    ipath = run_dir / "working" / "intake.json"
    if ipath.is_file():
        try:
            intake = json.loads(ipath.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            intake = {}
    slug = _slug(intake)
    src_dir = run_dir / "delivery"
    labeled = {
        "Chapter-%s.md" % slug: src_dir / ("chapter-%s.md" % slug),
        "Tone-Doc-%s.md" % slug: src_dir / ("tone-doc-%s.md" % slug),
        "Outline-%s.md" % slug: src_dir / ("outline-%s.md" % slug),
        "Title-%s.json" % slug: src_dir / ("title-%s.json" % slug),
        "Blurb-%s.md" % slug: src_dir / ("blurb-%s.md" % slug),
    }
    receipt = {"delivered": False, "slug": slug,
               "certificate_sha": (cert or {}).get("sha")}
    root = _delivery_root(delivery_root)
    if root is None:
        print("!! [anthology] cannot resolve a delivery root (no %s and no $HOME); the "
              "run-dir deliverable stands, but NO labeled ~/Downloads bundle was written."
              % _DELIVERY_ROOT_ENV, file=sys.stderr)
        _write_bundle_receipt(run_dir, receipt)
        return receipt
    bundle = _bundle_dir(root, slug)
    try:
        bundle.mkdir(parents=True, exist_ok=True)
        copied = []
        for label, src in labeled.items():
            if not src.is_file():
                raise OSError("byte-verified source missing: %s" % src)
            (bundle / label).write_bytes(src.read_bytes())
            copied.append(label)
        # PROCESS-CERTIFICATE.json/.md into the bundle (the client-facing proof).
        for cf in ("PROCESS-CERTIFICATE.json", "PROCESS-CERTIFICATE.md"):
            cp = src_dir / cf
            if cp.is_file():
                (bundle / cf).write_bytes(cp.read_bytes())
                copied.append(cf)
        note = _delivery_note(intake, slug, cert, proc, copied)
        (bundle / "DELIVERY-NOTE.md").write_text(note, encoding="utf-8")
        copied.append("DELIVERY-NOTE.md")
        handoff = _handoff(run_dir, intake, slug, cert, bundle, copied)
        (bundle / "handoff.json").write_text(
            json.dumps(handoff, indent=2), encoding="utf-8")
        copied.append("handoff.json")
        receipt.update({"delivered": True, "bundle_dir": str(bundle), "files": copied})
        print("LABELED DELIVERABLE: %s (%d files)" % (bundle, len(copied)))
    except OSError as exc:
        print("!! [anthology] labeled ~/Downloads bundle assembly FAILED (%s); the certified "
              "run-dir deliverable in delivery/ still stands." % exc, file=sys.stderr)
        receipt.update({"delivered": False, "bundle_dir": str(bundle), "error": str(exc)})
    _write_bundle_receipt(run_dir, receipt)
    return receipt


def _write_bundle_receipt(run_dir: Path, receipt: dict):
    out = _delivery_bundle_receipt(run_dir)
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    except OSError:
        pass


def _delivery_note(intake: dict, slug: str, cert, proc: dict, files) -> str:
    import datetime
    title = intake.get("anthology_title", slug)
    contributor = ("%s %s" % (intake.get("first_name", ""),
                              intake.get("last_name", ""))).strip()
    sha = (cert or {}).get("sha", "")
    lines = [
        "# Anthology Writer — DELIVERY NOTE",
        "",
        "- **Anthology:** %s (`%s`)" % (title, slug),
    ]
    if contributor:
        lines.append("- **Contributor:** %s" % contributor)
    lines += [
        "- **Certificate SHA:** `%s`" % sha,
        "- **Delivered (local):** %s" % datetime.datetime.now().strftime("%m-%d-%Y"),
        "- **Runtime:** local-only (no n8n / Airtable / Google Drive / Slack / Gmail).",
        "",
        "## What's in this bundle",
        "",
        "| File | Purpose |",
        "|---|---|",
        "| `Chapter-%s.md` | the finished 2,000-3,500-word chapter (QC'd) |" % slug,
        "| `Tone-Doc-%s.md` | the blended signature-voice tone doc (QC'd) |" % slug,
        "| `Outline-%s.md` | the approved chapter outline |" % slug,
        "| `Title-%s.json` | the locked title + subtitle |" % slug,
        "| `Blurb-%s.md` | the back-cover blurb |" % slug,
        "| `PROCESS-CERTIFICATE.json` / `.md` | the signed proof of a full P0->P6 pass |",
        "| `handoff.json` | machine-readable handoff (paths, measured counts, cert sha) |",
        "",
        "Everything is a LOCAL labeled deliverable. Any push to a channel is per-client "
        "config through the client's own OpenClaw gateway (never bypassed), client-silent "
        "by default.",
        "",
        "_No certificate = not done. This bundle carries one (`%s`)._" % (sha[:12] if sha else "—"),
        "",
    ]
    return "\n".join(lines)


def _handoff(run_dir: Path, intake: dict, slug: str, cert, bundle: Path, files) -> dict:
    import datetime
    measured = _measure(run_dir)
    return {
        "schema": "anthology-writer-handoff-v1",
        "skill": "anthology-writer",
        "skill_number": 54,
        "anthology_title": intake.get("anthology_title", ""),
        "slug": slug,
        "contributor": ("%s %s" % (intake.get("first_name", ""),
                                   intake.get("last_name", ""))).strip(),
        "bundle_dir": str(bundle),
        "files": files,
        "measured_chapter_words": measured.get("chapter_words"),
        "measured_tone_words": measured.get("tone_words"),
        "certificate_sha": (cert or {}).get("sha"),
        "certificate_path": (cert or {}).get("path"),
        "runtime": "local-only (no n8n / Airtable / Google Drive / Slack / Gmail)",
        "delivered_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }


def _deliver_card_note(run_dir) -> str:
    """The CC card's deliverable POINTER: the labeled-bundle path + certificate sha,
    read from the delivery-bundle receipt written at assembly time. Falls back to a
    plain note when the receipt is absent (the board is a view, never a gate)."""
    try:
        rec = json.loads(_delivery_bundle_receipt(Path(run_dir)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return "certified + delivered"
    sha = (rec.get("certificate_sha") or "")[:12]
    if rec.get("delivered") and rec.get("bundle_dir"):
        return "certified + delivered — bundle: %s · cert sha %s" % (rec["bundle_dir"], sha)
    return ("certified (run-dir deliverable); labeled ~/Downloads bundle NOT written · cert sha %s"
            % sha)


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

    # P0A-AVATAR wiring must be LIVE, not an inert manifest-only gate (SPEC 3.2/1):
    # the phase sits in PHASE_ORDER right after P0-INTAKE and before P1-FIDELITY, it
    # maps a real checker, and that checker fail-closes on a missing avatar dossier.
    _ck("P0A-AVATAR wired into PHASE_ORDER (after P0-INTAKE, before P1-FIDELITY)",
        "P0A-AVATAR" in PHASE_ORDER
        and PHASE_ORDER.index("P0A-AVATAR") == PHASE_ORDER.index("P0-INTAKE") + 1
        and PHASE_ORDER.index("P0A-AVATAR") < PHASE_ORDER.index("P1-FIDELITY"))
    _ck("_chk_avatar mapped in _CHECKERS", "_chk_avatar" in _CHECKERS)
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir()
        good, msg = _run_checker("_chk_avatar", rd)
        _ck("_chk_avatar fail-closes on a missing avatar dossier (AF-AW-AVATAR-MISSING)",
            good is False and "AF-AW-AVATAR-MISSING" in msg)

    intake = {"anthology_title": "Unbroken Ground", "first_name": "Marcus", "last_name": "Bell",
              "chapter_premise": "x"}
    slug = _slug(intake)

    _BLURB = ("An anthology chapter about losing the family auto-repair shop and the "
              "long work of separating a man's identity from the building he thought he "
              "was. A blue Igloo cooler, a padlock sent by certified mail, and what was "
              "rebuilt once there was nothing left to protect.")

    def _seed(rd: Path):
        (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        (rd / "working" / "chapter.md").write_text("# Chapter\nthe QC'd chapter body\n", encoding="utf-8")
        (rd / "working" / "tone-doc.md").write_text("# The Marcus Bell Tone\nbody\n", encoding="utf-8")
        (rd / "working" / "outline.md").write_text("# Outline\n- beat\n", encoding="utf-8")
        (rd / "working" / "title.json").write_text(
            json.dumps({"title": "Unbroken Ground", "subtitle": "Voices"}), encoding="utf-8")
        (rd / "working" / "blurb.md").write_text("# Blurb\n\n%s\n" % _BLURB, encoding="utf-8")

    # missing working QC artifacts -> FAIL (no evidence-free pass).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); (rd / "working").mkdir()
        (rd / "working" / "intake.json").write_text(json.dumps(intake), encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver missing artifacts -> FAIL (AF-AW-STAGE-SKIPPED)",
            good is False and "AF-AW-STAGE-SKIPPED" in msg)

    # golden -> assembles + byte-verifies the labeled bundle (incl. the blurb).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd)
        good, _ = _chk_deliver(rd)
        _ck("_chk_deliver golden -> PASS", good is True)
        _ck("_chk_deliver assembled the labeled bundle (incl. blurb)",
            (rd / "delivery" / ("chapter-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("tone-doc-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("outline-%s.md" % slug)).is_file()
            and (rd / "delivery" / ("title-%s.json" % slug)).is_file()
            and (rd / "delivery" / ("blurb-%s.md" % slug)).is_file())

    # FIX-S36-55: a MISSING blurb blocks P7 (AF-AW-STAGE-SKIPPED); a present-but-stub
    # blurb blocks it (AF-AW-BLURB-MISSING) — the blurb is now produced AND gated.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd)
        (rd / "working" / "blurb.md").unlink()
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver missing blurb -> FAIL (AF-AW-STAGE-SKIPPED)",
            good is False and "AF-AW-STAGE-SKIPPED" in msg and "blurb.md" in msg)
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd)
        (rd / "working" / "blurb.md").write_text("TODO", encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver stub blurb -> FAIL (AF-AW-BLURB-MISSING)",
            good is False and "AF-AW-BLURB-MISSING" in msg)

    # planted mismatch -> AF-AW-DELIVER-MISMATCH (swap-after-QC / stale deliverable).
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td); _seed(rd); (rd / "delivery").mkdir()
        (rd / "delivery" / ("chapter-%s.md" % slug)).write_text(
            "planted different bytes\n", encoding="utf-8")
        good, msg = _chk_deliver(rd)
        _ck("_chk_deliver planted-mismatch -> FAIL (AF-AW-DELIVER-MISMATCH)",
            good is False and "AF-AW-DELIVER-MISMATCH" in msg)

    # labeled ~/Downloads bundle (FIX-S36-55): assembled into an OVERRIDE root (never
    # the real ~/Downloads), carrying DELIVERY-NOTE.md + handoff.json + cert pointer.
    with tempfile.TemporaryDirectory() as td:
        rd = Path(td) / "run"; rd.mkdir(parents=True); _seed(rd)
        _chk_deliver(rd)  # assembles delivery/<...>-<slug> (byte-verified)
        dl_root = Path(td) / "downloads"
        cert = {"path": str(rd / "delivery" / "PROCESS-CERTIFICATE.json"), "sha": "a" * 64}
        rec = _assemble_downloads_bundle(rd, cert, {"phases": []}, delivery_root=dl_root)
        _ck("Downloads bundle assembled under the OVERRIDE root", rec.get("delivered") is True)
        bdir = Path(rec.get("bundle_dir", ""))
        _ck("bundle carries DELIVERY-NOTE.md", (bdir / "DELIVERY-NOTE.md").is_file())
        _ck("bundle carries handoff.json", (bdir / "handoff.json").is_file())
        _ck("bundle carries the labeled chapter + blurb",
            (bdir / ("Chapter-%s.md" % slug)).is_file()
            and (bdir / ("Blurb-%s.md" % slug)).is_file())
        try:
            ho = json.loads((bdir / "handoff.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ho = {}
        _ck("handoff.json records the certificate sha", ho.get("certificate_sha") == "a" * 64)
        _ck("card deliverable note points at the bundle + cert sha",
            bdir.as_posix() in _deliver_card_note(rd) and "aaaaaaaaaaaa" in _deliver_card_note(rd))
        real_home = os.environ.get("HOME", "")
        _ck("never touched a path outside the override root",
            not bdir.as_posix().startswith(real_home + "/Downloads") if real_home else True)

    print("== run_anthology self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return EXIT_PASS if ok else 1


# ---------------------------------------------------------------------------
# Command Center board card (FAIL-SOFT). FIX-S36-53: the Anthology Writer shipped
# ZERO Command Center wiring — no mc_board.py and main() never carded a run, so
# every anthology run was board-invisible. This mirrors Skill-55 (product-bio) and
# Skill-53 (book-writer) via the shared mc_board helper: land ONE mc-route card per
# run and advance it. A disabled board (no COMMAND_CENTER_URL) is a clean no-op; ANY
# failure is swallowed — the board is a VIEW, never a gate, and can never affect this
# orchestrator's exit code.
# ---------------------------------------------------------------------------
def _mc_board_begin(run_dir):
    try:
        sys.path.insert(0, str(_SKILL_DIR))
        import mc_board
        return mc_board.begin_run(
            run_dir, slug=run_dir.name,
            title="Anthology Writer — %s" % run_dir.name,
            # FIX-BK-DEPT-01 (SK2-01): "books" was never a real, seeded department
            # (no script anywhere in this repo creates one) — mc_board fails SOFT on
            # an unrecognized department_slug, so every Anthology Writer card was
            # silently dropped/misrouted. skill-department-map.json resolves skill 54
            # (and its sibling skill 53 Book Writer) to the real, mandatory,
            # always-seeded "marketing" department.
            department="marketing", persona="Anthology Writer", source="anthology-writer")
    except Exception as exc:  # noqa: BLE001 — board hookup must NEVER break the run.
        print("[mc_board] begin best-effort skip (%s)" % exc, file=sys.stderr)
        return None


def _mc_board_done(run_dir, task_id):
    try:
        sys.path.insert(0, str(_SKILL_DIR))
        import mc_board
        mc_board.complete_run(run_dir, task_id, note=_deliver_card_note(run_dir))
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] done best-effort skip (%s)" % exc, file=sys.stderr)


def _mc_board_blocked(run_dir, task_id):
    """FIX-XC-06: on a gate failure, move the card to `blocked` (never `done`) with
    the failing phase + AF code as the note, so a failed anthology run is VISIBLE on
    the board instead of stranding forever at in_progress. FAIL-SOFT."""
    try:
        sys.path.insert(0, str(_SKILL_DIR))
        import mc_board
        info = _LAST_BLOCK or {}
        mc_board.block_run(run_dir, task_id, phase_id=info.get("phase_id", ""),
                           note=info.get("note", "a fail-closed gate blocked the run"))
    except Exception as exc:  # noqa: BLE001
        print("[mc_board] blocked best-effort skip (%s)" % exc, file=sys.stderr)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Deterministic Anthology Writer orchestrator (Skill 54).")
    ap.add_argument("--run-dir", help="the anthology run directory (contains working/)")
    ap.add_argument("--participant-key", dest="participant_key", default=None,
                    help="resolve the run directory via the shared per-participant resolver "
                         "(anthology_run_dir.resolve_participant_run_dir) instead of --run-dir; "
                         "the SAME resolver every Skill 59 stage dispatcher uses (U059)")
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
    if not args.run_dir and not args.participant_key:
        ap.error("--run-dir or --participant-key is required (or use --plan)")
    if args.participant_key:
        # U059: resolve the gate-artifact directory through the SAME shared resolver
        # the Skill 59 stage dispatchers use, so this orchestrator checks exactly the
        # directory the stages wrote to (never an ad-hoc per-stage path).
        if resolve_participant_run_dir is None:
            print("FATAL: cannot import anthology_run_dir.resolve_participant_run_dir from "
                  "59-anthology-engine/scripts (U059 shared resolver).", file=sys.stderr)
            return EXIT_USAGE
        run_dir = resolve_participant_run_dir(args.participant_key)
    else:
        run_dir = Path(args.run_dir).resolve()
    if not run_dir.is_dir():
        print("FATAL: --run-dir not found: %s" % run_dir, file=sys.stderr)
        return EXIT_USAGE
    if not _nonce_ok(run_dir):
        print("FATAL: front-door nonce missing/mismatch. Run THROUGH anthology-entry.sh "
              "(the ONE sanctioned entry); do not call this orchestrator directly.",
              file=sys.stderr)
        return EXIT_NONCE
    _mc_task = _mc_board_begin(run_dir)
    rc = run(manifest, run_dir, args.upto)
    if rc == EXIT_PASS and not args.upto:
        _mc_board_done(run_dir, _mc_task)
    elif rc != EXIT_PASS:
        # A gate failure after the card was opened: mark it blocked so it never
        # strands invisibly at in_progress (FIX-XC-06). A partial `--upto` PASS is
        # neither done nor blocked (it legitimately stays in_progress).
        _mc_board_blocked(run_dir, _mc_task)
    return rc


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""stage_s8_deliver.py -- thin stage dispatcher for s8 (PACKAGE AND DELIVER).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S8 package and deliver (runs per deliverable as each stage completes AND as a full sweep
at participant completion): Google Doc, designed PDF at the 14-point floor, Convert and
Flow media upload, exact-key field writes by contact_id read back byte-for-byte, control
fields, per-gate pipeline-stage update, completion notice, signed certificate, card to review.

Persona (PRD Section 13): none (deterministic rendering and delivery; anthology-producer-orchestrator).

Exit codes (SPEC 3.4 row 6; house: 1 unexpected error):
  0  stage complete and persisted
  2  prover failure (counts a QC attempt)
  3  held (credits, lost callback, or a collaborator not yet wired)
  5  unresolved prompt slot (AF-AE-SLOT-UNRESOLVED)
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STAGE = "s8"
STAGE_NAME = "PACKAGE AND DELIVER"
KEY_ARG = "participant-key"
PERSONA = "none (deterministic rendering and delivery; anthology-producer-orchestrator)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S8.
WIRING = [
    ("scripts/drive_adapter.py", "create the Google Doc inside the participant Drive folder tree"),
    ("scripts/pdf_render.py", "render the designed PDF from the house template for this deliverable type"),
    ("scripts/guard-font-floor.py", "parse the RENDERED PDF; fail on any glyph below 14 point (AF-AE-FONT-FLOOR)"),
    ("scripts/caf_delivery.py", "Convert and Flow media upload; exact-key field writes by contact_id from config/field-map.json; byte-for-byte read-back; control fields"),
    ("scripts/anthology_state.py", "fire the per-gate Convert and Flow pipeline-stage update from the registry stage map (never hardcoded)"),
    ("scripts/nudge_send.py", "send the completion notice through the sanctioned template only"),
    ("scripts/mc_board.py", "at participant completion, the signed process certificate is recorded and the board card moves to review (never done; the QC scorer owns review to done)"),
]


KEY_DELIM = "::"

# ledger ARTIFACT_TYPES -> the Layer 1 working/*.md checkpoint that carries its
# content (54-anthology-writer/run_anthology.py). cover/anthology_manuscript have
# no single working file here: cover is image-only (delivered via Drive at S7),
# manuscript is S9's own compiled full text, passed via --doc-file/--pdf-file.
DELIVERABLE_WORKING_FILE = {
    "avatar": "avatar.md", "tone": "tone-doc.md", "titles": "title.json",
    "blurb": "blurb.md", "outline": "outline.md", "chapter": "chapter.md",
    "rewrite": "chapter.md",
}


def _run_dir_for(key, run_dir=None):
    """Resolve (and create) the run directory. S8 is always CALLED with an
    explicit --run-dir by its caller (S1-S7, S9 all thread their OWN run dir
    through so working/*.md stays the one shared per-participant directory); the
    stage-local default below only applies to a fully standalone invocation."""
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        d = SKILL_DIR / "state" / "runs" / STAGE / safe
    (d / "working").mkdir(parents=True, exist_ok=True)
    return d


def _run(argv, timeout=180):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return EX_HELD, None, "timed out (%ss): %s" % (timeout, " ".join(argv))
    except OSError as exc:
        return EX_ERR, None, "could not launch: %s" % exc
    out = (proc.stdout or "").strip()
    parsed = None
    if out:
        try:
            parsed = json.loads(out)
        except (ValueError, TypeError):
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def _step(i, rel, argv, timeout=180):
    sys.stderr.write("[stage_%s] %d/%d %s\n" % (STAGE, i + 1, len(WIRING), rel))
    rc, parsed, err = _run(argv, timeout=timeout)
    classified = classify_child_rc(rc)
    if classified != EX_OK:
        sys.stderr.write("[stage_%s] %s exited %d -> classified %d%s\n"
                         % (STAGE, rel, rc, classified,
                            (" :: %s" % err[-300:]) if err else ""))
    return classified, parsed


def _resolve(rel):
    # Skill-local collaborators (scripts/, config/, assets/, roles/, fixtures/)
    # resolve ONLY under this skill dir; cross-skill paths (e.g. the Skill 54
    # Layer 1 entry) resolve under the repo root. Strict, so a same-named
    # repo-root script can never masquerade as a skill collaborator.
    top = rel.split("/", 1)[0]
    base = SKILL_DIR if top in ("scripts", "config", "assets", "roles", "fixtures") else REPO_ROOT
    p = base / rel
    return p if p.exists() else None


def classify_child_rc(rc):
    """FIXED contract: map a collaborator exit code to this stage's exit code."""
    if rc == 0:
        return EX_OK
    if rc in (2, 4):
        return EX_PROVER
    if rc == 3:
        return EX_HELD
    if rc == 5:
        return EX_SLOT
    return EX_ERR


def plan():
    print("STAGE %s  %s" % (STAGE.upper(), STAGE_NAME))
    print("persona: %s" % PERSONA)
    print("Layer 1 authoring entry (Skill 54): %s" % LAYER1_ENTRY)
    print("ordered wiring contract:")
    for i, (rel, role) in enumerate(WIRING, 1):
        status = "resolved" if _resolve(rel) else "PENDING-WIRING"
        print("  %2d. [%-13s] %s" % (i, status, rel))
        print("        %s" % role)
    return EX_OK


def _doc_url_from_created(created):
    """Pull the live Google Doc link out of drive_adapter.deliver_doc()'s result.

    drive_adapter.py's create-doc path (deliver_doc) returns the shareable link
    under the key "doc_url" (its files_get webViewLink) and the file id under
    "doc_id" -- NOT a top-level webViewLink/link/id. Read the real key first; the
    legacy guesses stay only as harmless fallbacks so a future shape change never
    silently ships a None link in the completion email/SMS."""
    return (created.get("doc_url") or created.get("webViewLink")
            or created.get("link"))


def _invoke_wiring(key, run_dir=None, deliverable=None, final=False, gate_hint=None):
    """W4.0: the concrete argv chain per collaborator, in WIRING order (fixed).
    `deliverable` is the ledger ARTIFACT_TYPES value the caller just authored
    (S1-S7, S9 each pass their own --deliverable); this thin runner does not
    guess it. classify_child_rc's numeric contract is unchanged; every step
    short-circuits on anything but EX_OK."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD, None
    if not key or KEY_DELIM not in key:
        sys.stderr.write("[stage_%s] --%s must be a contact_id%santhology_id composite "
                         "key.\n" % (STAGE, KEY_ARG, KEY_DELIM))
        return EX_HELD, None
    if not deliverable:
        sys.stderr.write("[stage_%s] --deliverable is required (the ledger artifact_type "
                         "just authored by the calling stage).\n" % STAGE)
        return EX_HELD, None
    pkey = key
    contact_id, anthology_id = pkey.split(KEY_DELIM, 1)
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)

    # G10 rewrite preservation: a rewrite lands in its OWN pair (rewrite1/rewrite2),
    # never the base chapter pair, so the ORIGINAL (and any earlier rewrite) survives
    # in the producer's Convert and Flow view. The slot is the participant's
    # rewrite_count at delivery time -- incremented exactly once at the
    # s5_participant/request_rewrite gate BEFORE this stage runs (1 for the first
    # editors' rewrite, 2 for the second) -- read here from the sole ledger, never
    # guessed. A wrong slot would overwrite a preserved version, so an out-of-range
    # count is a hard refusal, not a fallback.
    rewrite_number = None
    if deliverable == "rewrite":
        _, part_rc, _ = _run([py, str(_resolve("scripts/anthology_state.py")), "--json",
                             "get-participant", "--participant-key", pkey])
        raw_count = (part_rc or {}).get("rewrite_count")
        try:
            rewrite_number = int(raw_count)
        except (TypeError, ValueError):
            rewrite_number = None
        if rewrite_number not in (1, 2):
            sys.stderr.write("[stage_%s] rewrite delivery needs a rewrite_count of 1 or 2 "
                             "(got %r); the s5 rewrite gate owns that increment. Refusing to "
                             "guess a preservation slot.\n" % (STAGE, raw_count))
            return EX_PROVER, None
        sys.stderr.write("[stage_%s] rewrite #%d -> preservation slot rewrite%d (base chapter "
                         "left intact)\n" % (STAGE, rewrite_number, rewrite_number))

    # deliverable_for_artifact_type() (drift #2's fix) is exercised BEFORE any
    # call into caf_delivery.py, per SESSION-LOG.md: import in-process (no
    # subprocess side effects; mirrors the sibling cross-check convention in
    # intake_router.py/mc_board.py). For a rewrite it routes by rewrite_number to
    # rewrite1/rewrite2 (G10); for every other type the static alias applies.
    sys.path.insert(0, str(SCRIPTS))
    import caf_delivery as _caf  # noqa: E402
    fm = _caf.FieldMap.load()
    try:
        caf_deliverable = fm.deliverable_for_artifact_type(deliverable, rewrite_number=rewrite_number)
    except _caf.DeliveryError as exc:
        sys.stderr.write("[stage_%s] %s\n" % (STAGE, exc))
        return EX_PROVER, None

    working_name = DELIVERABLE_WORKING_FILE.get(deliverable)
    content_file = (Path(rundir) / "working" / working_name) if working_name else None

    # 1. drive_adapter.py -- create the Google Doc inside the participant Drive
    #    folder tree.
    rel, _ = WIRING[0]
    _, participant, _ = _run([py, str(_resolve("scripts/anthology_state.py")), "--json",
                             "get-participant", "--participant-key", pkey])
    folder_id = (participant or {}).get("drive_folder_id")
    doc_url = None
    if folder_id and content_file and content_file.is_file():
        # The deliverable Google Doc is shared anyone-with-link EDIT (writer), NOT
        # view-only: Trevor's law (LOCKED #4) so the co-author edits their own Doc in
        # place and the engine pulls the edits back (confirm-then-pull, U7). The paired
        # premium PDF (rendered below) remains the view-only artifact.
        argv = [py, str(_resolve(rel)), "create-doc", "--name", "%s-%s" % (contact_id, deliverable),
                "--parent-folder-id", folder_id, "--text-file", str(content_file), "--share-edit"]
        rc, created = _step(0, rel, argv)
        if rc != EX_OK:
            return rc, None
        doc_url = _doc_url_from_created(created or {})
    else:
        sys.stderr.write("[stage_%s] 1/%d %s: skipped (no drive_folder_id yet, or no "
                         "working/%s content to package)\n" % (STAGE, len(WIRING), rel, working_name))

    # 2. pdf_render.py -- render the designed PDF from the house template.
    rel, _ = WIRING[1]
    pdf_path = Path(rundir) / "working" / ("%s.pdf" % deliverable)
    if content_file and content_file.is_file() and deliverable in (
            "avatar", "tone", "titles", "blurb", "outline", "chapter", "rewrite", "anthology_manuscript"):
        pdf_type = "chapter" if deliverable in ("rewrite",) else (
            "manuscript" if deliverable == "anthology_manuscript" else deliverable)
        rc, _ = _step(1, rel, [py, str(_resolve(rel)), "--type", pdf_type, "--in", str(content_file),
                              "--out", str(pdf_path), "--json"])
        if rc != EX_OK:
            return rc, None
    else:
        sys.stderr.write("[stage_%s] 2/%d %s: skipped (no source content to render)\n"
                         % (STAGE, len(WIRING), rel))
        pdf_path = None

    # 3. guard-font-floor.py -- parse the RENDERED PDF; fail below 14 point.
    rel, _ = WIRING[2]
    if pdf_path and pdf_path.is_file():
        rc, _ = _step(2, rel, [py, str(_resolve(rel)), str(pdf_path), "--json"])
        if rc != EX_OK:
            return rc, None
    else:
        sys.stderr.write("[stage_%s] 3/%d %s: skipped (no rendered PDF)\n"
                         % (STAGE, len(WIRING), rel))

    # 4. caf_delivery.py -- CAF media upload; exact-key field writes by
    #    contact_id from config/field-map.json; byte-for-byte read-back; control
    #    fields. Registry stage-map/pipeline (read-only; fail-soft if unbound
    #    on this box yet -- delivery still lands, only the pipeline-stage move
    #    is skipped, matching cmd_deliver's own conditional).
    rel, _ = WIRING[3]
    _, binding, _ = _run([py, str(_resolve("scripts/anthology_registry.py")),
                         "resolve", "--anthology-id", anthology_id, "--json"])
    binding = binding or {}
    argv = [py, str(_resolve(rel)), "deliver", "--contact-id", contact_id,
           "--anthology-id", anthology_id, "--participant-key", pkey,
           "--deliverable", caf_deliverable]
    if rewrite_number is not None:
        # Surface the rewrite counter into Convert and Flow's own control field so the
        # W8 release email can show "editors' rewrites used: N of 2" (read back like
        # every other write).
        argv += ["--rewrite-count", str(rewrite_number)]
    if doc_url:
        argv += ["--doc-url", doc_url]
    if pdf_path and pdf_path.is_file():
        argv += ["--pdf-file", str(pdf_path)]
    if binding.get("pipeline_id") and binding.get("caf_stage_map"):
        # The registry's caf_stage_map keys by ENGINE STAGE (s0..s9), not by
        # deliverable name, and this thin runner is not told which engine
        # stage_cursor it is being called from (S1-S7/S9 each dispatch their
        # OWN piece and only ever pass a --deliverable, never a --gate). A
        # per-gate opportunity move therefore only fires when the caller
        # supplies --gate explicitly (below); left unset otherwise is a
        # documented, honest gap: delivery + field writes still complete, byte-
        # for-byte read-back still runs, only the pipeline-stage move is
        # skipped for this call (stage_s9_assembly.py IS told its own gate and
        # passes one through).
        argv += ["--pipeline-id", binding["pipeline_id"],
                "--stage-map", json.dumps(binding["caf_stage_map"], ensure_ascii=False)]
        if gate_hint:
            argv += ["--gate", gate_hint]
    if final:
        argv += ["--final"]
    rc, delivered = _step(3, rel, argv)
    if rc != EX_OK:
        return rc, None
    delivered = delivered or {}

    # 5. anthology_state.py -- record the delivery outcome onto the ledger's own
    #    artifact row (the per-gate CAF pipeline-stage move itself is fired
    #    inside caf_delivery.py's own deliver call above, from the SAME registry
    #    stage map read in step 4; this is the ledger-side mirror of that CAF-side
    #    write, never hardcoded, always sourced from what was actually written).
    #    caf_delivery.py's own stdout carries only the persisted report PATH, not
    #    the field-write detail inline, so the ledger row records the Drive
    #    doc_url this dispatcher already holds; the CAF-hosted link and the
    #    per-field read-back proof live in that report file (referenced below)
    #    and in the CAF contact's own custom fields, the PRD Section 6 source
    #    of truth.
    rel, _ = WIRING[4]
    art_argv = [py, str(_resolve(rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", deliverable]
    if doc_url:
        art_argv += ["--doc-url", doc_url]
    rc, _ = _step(4, rel, art_argv)
    if rc != EX_OK:
        return rc, None

    # 6. nudge_send.py -- the completion notice through the sanctioned template
    #    only.
    rel, _ = WIRING[5]
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "send", "--template", "completion",
                          "--subject-key", pkey, "--deliverable-label", deliverable,
                          "--json"])
    if rc not in (EX_OK, EX_HELD):
        return rc, None

    # 7. mc_board.py -- at participant completion the signed process certificate
    #    is recorded and the card moves to review (never done).
    rel, _ = WIRING[6]
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc, None

    result = {"delivered": True, "type": deliverable, "doc_url": doc_url,
             "pdf_url": None, "report": delivered.get("report"),
             "certificate": delivered.get("certificate"),
             "caf_deliverable": caf_deliverable}
    if rewrite_number is not None:
        # G10: surface the rewrite counter + the preservation slot the rewrite landed
        # in (rewrite1/rewrite2), so the caller (S6) and the operator can see the count.
        result["rewrite_number"] = rewrite_number
        result["rewrite_slot"] = caf_deliverable
        result["rewrite_budget"] = _caf.FieldMap.REWRITE_BUDGET
        result["rewrites_remaining"] = max(0, _caf.FieldMap.REWRITE_BUDGET - rewrite_number)
    return EX_OK, result


def self_test():
    assert (EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT) == (0, 1, 2, 3, 5)
    assert classify_child_rc(0) == EX_OK
    assert classify_child_rc(2) == EX_PROVER
    assert classify_child_rc(4) == EX_PROVER
    assert classify_child_rc(3) == EX_HELD
    assert classify_child_rc(5) == EX_SLOT
    assert classify_child_rc(99) == EX_ERR
    assert isinstance(WIRING, list) and WIRING, "WIRING must be a non-empty ordered list"
    for rel, role in WIRING:
        assert isinstance(rel, str) and rel and isinstance(role, str) and role
    # doc-url resolution reads drive_adapter.deliver_doc()'s REAL return shape
    # (drive_adapter.py: keys "doc_url"/"doc_id", never top-level webViewLink/id).
    # The pre-fix expression guessed webViewLink/link/id -- none exist on that
    # dict -- so it shipped None; the helper must read the live "doc_url".
    _real = "https://docs.google.com/document/d/DOCID_x/edit"
    assert _doc_url_from_created({
        "ok": True, "action": "create-doc", "doc_id": "DOCID_x",
        "doc_url": _real, "view_shared": True, "permission_id": "p1",
        "verified": True}) == _real, "must read the live link from deliver_doc's doc_url"
    assert _doc_url_from_created({}) is None
    assert _doc_url_from_created({"webViewLink": _real}) == _real  # legacy fallback honored
    print("stage_%s self-test: OK (exit-code map + wiring contract coherent)" % STAGE)
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="thin dispatcher for stage %s (%s)" % (STAGE, STAGE_NAME))
    ap.add_argument("--%s" % KEY_ARG, dest="key", help="the %s to dispatch" % KEY_ARG)
    ap.add_argument("--run-dir", help="optional per-participant-per-stage run directory")
    ap.add_argument("--deliverable", help="the ledger artifact_type just authored "
                    "(avatar, tone, titles, blurb, outline, chapter, rewrite, cover, "
                    "anthology_manuscript); required to dispatch (S1-S7/S9 each pass "
                    "their own piece, never guessed here)")
    ap.add_argument("--gate", help="optional engine gate id for the per-gate CAF "
                    "pipeline-stage move (from the registry caf_stage_map)")
    ap.add_argument("--final", action="store_true",
                    help="emit the signed process certificate (full participant completion)")
    ap.add_argument("--json", action="store_true",
                    help="print the delivery result (doc_url, pdf_url, report ref) as JSON")
    ap.add_argument("--plan", action="store_true", help="print the wiring contract and exit")
    ap.add_argument("--self-test", action="store_true", help="verify the runner contract and exit")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return plan()
        if not args.key:
            ap.error("--%s is required to dispatch stage %s" % (KEY_ARG, STAGE))
        rc, result = _invoke_wiring(args.key, args.run_dir, args.deliverable, args.final, args.gate)
        if args.json and result is not None:
            print(json.dumps(result, ensure_ascii=False))
        return rc
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[stage_%s] unexpected error: %s\n" % (STAGE, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())

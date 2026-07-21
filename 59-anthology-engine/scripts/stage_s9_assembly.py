#!/usr/bin/env python3
"""stage_s9_assembly.py -- thin stage dispatcher for s9 (ANTHOLOGY ASSEMBLY).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S9 assembly (two producer decisions bracket it): the ready-to-assemble trigger (gate
s9_ready, all PRD 3.11 guards WRITER-enforced: own-producer auth, every participant
approved or explicitly excluded, at least min_chapters frozen approved chapters, typed
anthology-name confirmation, one-way) opens it; the final sign-off (gate s9_producer)
closes it. Fired from the Assembly card or the readiness nudge, both doors one endpoint.

Persona (PRD Section 13): anthology-producer-orchestrator speaking the Anthology Editor voice (ae-01 to ae-04), subordinate to producer inputs.

Exit codes (SPEC 3.4 row 6; house: 1 unexpected error):
  0  stage complete and persisted
  2  prover failure (counts a QC attempt)
  3  held (credits, lost callback, or a collaborator not yet wired)
  5  unresolved prompt slot (AF-AE-SLOT-UNRESOLVED)
"""
import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

STAGE = "s9"
STAGE_NAME = "ANTHOLOGY ASSEMBLY"
KEY_ARG = "anthology-id"
PERSONA = "anthology-producer-orchestrator speaking the Anthology Editor voice (ae-01 to ae-04), subordinate to producer inputs"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S9.
WIRING = [
    ("scripts/anthology_state.py", "assembly-readiness-report (the blocking list) then arm; the s9_ready trigger with every guard revalidated by the writer and --confirm-name (mismatch exits 5)"),
    ("scripts/mc_board.py", "mirror the dedicated Assembly card to the armed/ready state (the ready-to-assemble trigger surfaces as the card's review transition, SPEC 11.2); FAIL-SOFT, never blocks assembly"),
    ("scripts/model_router.py", "order curation (ae-01), editor introduction in the producer voice from producer inputs only (ae-02), front and back matter (ae-04), contributor bios from ledger identities (ae-03); LONGCTX tier when configured, else chunked on HEAVY-WRITER"),
    ("scripts/anthology_state.py", "assembly-set-order; compile from FROZEN approved chapter artifacts, sha256 byte identical per chapter"),
    ("scripts/qc-tier1-anthology.py", "assembly-scope Gate B (every chapter present exactly once, order matches curation, one continuous 14-point-floor PDF)"),
    ("scripts/stage_s8_deliver.py", "deliver the full manuscript Doc plus PDF and push the manuscript fields"),
    ("scripts/anthology_state.py", "record the s9_producer sign-off that closes the anthology; read the manuscript fields back"),
    ("scripts/mc_board.py", "mirror the Assembly card sign-off (assembly_state signed_off) onto the board; the engine never sets 'done' (the QC scorer owns review->done at >=8.5); FAIL-SOFT"),
]


def _run_dir_for(key, run_dir=None):
    """S9's OWN run dir. Deliberately NOT the per-participant directory the
    authoring stages share: this one is keyed by ANTHOLOGY id, and
    gate_engine.py::_s9_run_dir must keep resolving the identical
    <skill>/state/runs/s9/<safe_anthology_id> path that this runner reads."""
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        d = SKILL_DIR / "state" / "runs" / STAGE / safe
    (d / "working").mkdir(parents=True, exist_ok=True)
    return d


def participant_chapter_path(participant_key):
    """The frozen chapter's on-disk path inside the ONE canonical per-participant
    run directory the authoring stages (S1..S8) all share --
    <skill>/state/runs/participants/<safe_key>/working/chapter.md.

    This used to point at the stage-scoped state/runs/s5/<safe_key>/... . That
    path only existed while each stage resolved its OWN working directory, which
    is the same defect that stopped S2 from ever reaching tone authoring. It is a
    module-level function (not a closure) so the invariant "S9 reads exactly where
    S5/S6 wrote" is directly testable."""
    safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (participant_key or "unknown"))
    return SKILL_DIR / "state" / "runs" / "participants" / safe / "working" / "chapter.md"


def _load_request(run_dir):
    """Optional producer-supplied per-call context (producer_id, confirm_name for
    the s9_ready arm; signoff_confirm_name for the closing s9_producer sign-off)
    the dashboard/Assembly-card webhook drops at <run_dir>/request.json before
    dispatch -- the both-door trigger PRD 3.11 describes. Absent/unreadable ->
    {} (fail-soft; this call then only reports readiness, changing nothing)."""
    p = Path(run_dir) / "request.json"
    if not p.is_file():
        return {}
    try:
        loaded = json.loads(p.read_text(encoding="utf-8"))
        return loaded if isinstance(loaded, dict) else {}
    except (ValueError, OSError):
        return {}


def _confirmed_order(request, bundle):
    """The producer's CONFIRMED running order for a confirm_order pass. Prefer the
    order the board "Confirm the finalized set & order" action wrote into
    request.json (gate_engine._flag_runner_confirm_order stamps request['order']);
    fall back to the ledger's chapter_order, which the SOLE writer persisted in the
    'adjusted' state when that same action committed the order. Returns a list of
    participant_key strings (empty if neither source carries an order)."""
    order = request.get("order")
    if isinstance(order, list) and order:
        return [str(k) for k in order]
    raw = (bundle.get("anthology") or {}).get("chapter_order")
    if isinstance(raw, str) and raw.strip():
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if isinstance(raw, list) and raw:
        return [str(k) for k in raw]
    return []


def _run(argv, timeout=180, input_text=None):
    try:
        proc = subprocess.run(argv, input=input_text, capture_output=True,
                              text=True, timeout=timeout)
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


def _step(i, rel, argv, timeout=180, input_text=None):
    sys.stderr.write("[stage_%s] %d/%d %s\n" % (STAGE, i + 1, len(WIRING), rel))
    rc, parsed, err = _run(argv, timeout=timeout, input_text=input_text)
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


def _invoke_wiring(key, run_dir=None):
    """W4.0: the concrete argv chain per collaborator, in WIRING order (fixed).
    ENGINE-MANIFEST.json row 6 (drift #3): "the S9 assembly logic ships as the
    sibling helper scripts/stage_s9_assembly_logic.py ... imported by the
    stage_s9_assembly.py dispatcher rather than dispatched directly." So this
    thin runner does NOT reimplement the order-curation/compile/sha-verify
    machinery: it imports that module in-process (S9Assembly) and drives its
    high-level methods, which themselves shell anthology_state.py,
    qc-tier1-anthology.py, and model_router.py (WIRING[0]/[2]/[3]/[4], resolved
    via the sibling rather than a direct subprocess here -- the same "declared
    collaborator, fulfilled by an internal call" pattern already established for
    gate_engine.py wrapping nudge_send.py). This dispatcher directly drives only
    what S9Assembly does NOT own: mc_board.py (WIRING[1]/[7]) and
    stage_s8_deliver.py (WIRING[5]).

    S9 is bracketed by TWO producer decisions (module docstring); an optional
    <run_dir>/request.json supplies the context each decision needs (producer_id
    always; confirm_name to arm; producer_inputs/producer_display_name for the
    editor's voice, never fabricated; signoff_confirm_name to close). Without
    arm context this call only reports readiness (EX_OK, informational).
    classify_child_rc's numeric contract is unchanged; every step short-circuits
    on anything but EX_OK."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD
    logic_path = SCRIPTS / "stage_s9_assembly_logic.py"
    if not logic_path.exists():
        sys.stderr.write("[stage_%s] PENDING-WIRING: sibling module logic not yet present: "
                         "%s\n" % (STAGE, logic_path))
        return EX_HELD
    if not key:
        sys.stderr.write("[stage_%s] --%s is required.\n" % (STAGE, KEY_ARG))
        return EX_HELD
    anthology_id = key
    py = sys.executable or "python3"
    rundir = _run_dir_for(anthology_id, run_dir)
    request = _load_request(rundir)

    sys.path.insert(0, str(SCRIPTS))
    import stage_s9_assembly_logic as logic  # noqa: E402
    import anthology_state as ledger  # noqa: E402

    # stage_s9_assembly_logic._run_writer always passes an explicit --state-dir
    # (or --db); it has no "omit and let the child inherit its own default"
    # path the way a bare subprocess call does elsewhere in this dispatcher, so
    # this MUST be resolved the same way anthology_state.py resolves it itself
    # (else "--state-dir None" would silently point at the wrong store).
    resolved_state_dir = str(ledger.default_state_dir())

    def _chapter_source(participant_key):
        """Read a frozen chapter's body from the ONE canonical per-participant run
        dir that stage_s5_chapter.py and stage_s6_rewrite.py write into
        (state/runs/participants/<safe_key>/working/chapter.md). A live deployment
        may instead read the Drive-hosted doc via drive_adapter.py; this local read
        is the honest, real implementation available without a network call."""
        p = participant_chapter_path(participant_key)
        if not p.is_file():
            return b"", None
        data = p.read_bytes()
        return data, hashlib.sha256(data).hexdigest()

    eng = logic.S9Assembly(anthology_id, state_dir=resolved_state_dir, run_dir=str(rundir),
                          chapter_source=_chapter_source)

    # 1 (first half). anthology_state.py -- READ-ONLY assembly-readiness-report,
    #    via S9Assembly.readiness_report() (shells the sole writer itself).
    try:
        readiness = eng.readiness_report()
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] 1/%d %s: %s\n" % (STAGE, len(WIRING), WIRING[0][0], exc))
        return classify_child_rc(getattr(exc, "exit_code", logic.EX_ERR))

    producer_id = request.get("producer_id")
    confirm_name = request.get("confirm_name")
    if not (readiness.get("ready") and producer_id and confirm_name):
        sys.stderr.write("[stage_%s] readiness report only (ready=%s; arm needs a producer "
                         "confirm_name via request.json); nothing else to do this call.\n"
                         % (STAGE, readiness.get("ready")))
        return EX_OK

    # 1 (second half). the s9_ready ARM trigger (S9Assembly.fire_ready): every
    #    guard revalidated by the writer; --confirm-name mismatch exits 5.
    try:
        rc, _fire_report, _outcome = eng.fire_ready(
            producer_id, confirm_name, door=request.get("door", "dashboard"))
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] 1/%d %s: %s\n" % (STAGE, len(WIRING), WIRING[0][0], exc))
        return classify_child_rc(getattr(exc, "exit_code", logic.EX_ERR))
    classified = classify_child_rc(rc)
    if classified != EX_OK:
        return classified

    # 2. mc_board.py -- mirror the Assembly card to armed/ready (FAIL-SOFT).
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, [py, str(_resolve(rel)), "sync", "--subject-key", anthology_id, "--json"])
    if rc != EX_OK:
        return rc

    # helper read (not a separate WIRING slot): the frozen, approved chapters
    # and contributor identities this dispatcher must pass to S9Assembly
    # (curate_order/bios/editor_intro/front_back_matter/compile_manuscript all
    # need the ledger's own facts, never invented here).
    _, bundle, _ = _run([py, str(_resolve("scripts/anthology_state.py")), "--json",
                        "export-bundle", "--anthology-id", anthology_id])
    bundle = bundle or {}
    frozen = [a for a in bundle.get("artifacts", [])
             if a.get("type") == "chapter" and a.get("frozen")]
    frozen.sort(key=lambda a: a.get("participant_key", ""))
    chapters = [{"participant_key": a["participant_key"], "sha256": a.get("sha256")}
               for a in frozen]
    members_by_key = {m["participant_key"]: m for m in bundle.get("participants", [])}
    contributors = [{"participant_key": pk,
                     "first_name": members_by_key.get(pk, {}).get("first_name"),
                     "last_name": members_by_key.get(pk, {}).get("last_name")}
                    for pk in (a["participant_key"] for a in frozen)]
    producer = bundle.get("producer") or {}
    frozen_shas = {a["participant_key"]: a.get("sha256") for a in frozen if a.get("sha256")}

    # 3. model_router.py -- order curation (ae-01), editor introduction (ae-02),
    #    front/back matter (ae-04), contributor bios (ae-03), each via
    #    S9Assembly (LONGCTX when configured, else chunked HEAVY-WRITER; every
    #    call still funnels through model_router.py, the engine's sole model-
    #    call site). Never fabricates: a producer with no supplied voice inputs
    #    refuses the introduction rather than inventing one (AF-AE-S9-FABRICATION).
    rel, _ = WIRING[2]
    sys.stderr.write("[stage_%s] %d/%d %s\n" % (STAGE, 3, len(WIRING), rel))
    transitions = None
    finale = None
    confirm_order = bool(request.get("confirm_order"))
    try:
        if confirm_order:
            # U9(a)+(b): the producer has already CONFIRMED the finalized set & order
            # via the board "Confirm the finalized set & order" action. gate_engine's
            # confirm_order persisted THAT order through the SOLE writer
            # (assembly-set-order --state adjusted) AND stamped request['order']. This
            # pass therefore USES the confirmed order verbatim and MUST NOT re-curate:
            # curate_order re-persists via assembly-set-order --state proposed, an
            # ILLEGAL adjusted->proposed transition (anthology_state ASSEMBLY_EDGES has
            # no such edge) that would fail the pass before any transition or finale is
            # written -- and it would also discard the producer's CONFIRMED order in
            # favour of a freshly re-derived one. The legal adjusted->compiled edge is
            # taken later by compile_manuscript (WIRING[3]).
            order = _confirmed_order(request, bundle)
            if not order:
                raise logic.CurationInvalid(
                    "confirm_order pass carries no confirmed order (neither "
                    "request['order'] nor the ledger's chapter_order is set)")
            ok, detail = logic.validate_order_permutation(
                order, [c["participant_key"] for c in chapters])
            if not ok:
                raise logic.CurationInvalid(
                    "the producer's confirmed order is not a permutation of the "
                    "frozen approved set: %s" % detail)
            sys.stderr.write("[stage_%s] confirm_order pass: using the producer's CONFIRMED "
                             "order (%d chapter(s)); NOT re-curating (the sole writer already "
                             "persisted chapter_order in the 'adjusted' state).\n"
                             % (STAGE, len(order)))
        else:
            proposal = eng.curate_order(chapters)
            order = proposal["order"]
            # U9(c): the ordering + one-line-per-slot rationale the CC assembly cockpit
            # renders is on proposal["cockpit_view"]; persist it for the cockpit read
            # path (a durable file the dashboard loads; the ledger keeps chapter_order).
            try:
                (Path(rundir) / "working" / "order_proposal.json").write_text(
                    json.dumps(proposal.get("cockpit_view") or {}, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            except OSError as exc:
                sys.stderr.write("[stage_%s] non-fatal: could not persist the cockpit ordering "
                                 "view (%s); the ledger still holds chapter_order.\n" % (STAGE, exc))
        bios_out = eng.bios(contributors, order)
        bios_by_key = {b["participant_key"]: json.dumps(b, ensure_ascii=False)
                      for b in bios_out["bios"]}
        producer_inputs = request.get("producer_inputs")
        intro_markdown = ""
        front_matter = ""
        back_matter = ""
        # U9(a)+(b): the producer's "Confirm the finalized set & order" is the
        # trigger that authorizes the FINAL edition: the N-1 inter-chapter
        # transitions and the brand-new Grand Finale are written ONLY after the
        # set is finalized, approved, and ordered. Without that confirmation this
        # call still curates/compiles a working manuscript, but no transitions or
        # finale are inserted (final-edition-only, per the assembly directive).
        if confirm_order:
            chapters_meta = [{
                "participant_key": pk,
                "chapter_title": members_by_key.get(pk, {}).get("title_locked"),
                "first_name": members_by_key.get(pk, {}).get("first_name"),
                "last_name": members_by_key.get(pk, {}).get("last_name"),
                "one_line_summary": members_by_key.get(pk, {}).get("one_line_summary") or "",
            } for pk in order]
            transitions = eng.write_transitions(order, chapters_meta)
            finale = eng.write_finale(order, chapters_meta, producer.get("display_name"))
            sys.stderr.write("[stage_%s] final edition: %d inter-chapter transition(s) + "
                             "Grand Finale %r written (producer confirmed the set & order).\n"
                             % (STAGE, len(transitions), finale.get("finale_title")))
        if producer_inputs:
            intro_out = eng.editor_intro(producer_inputs, contributors,
                                         producer.get("display_name"), order)
            intro_markdown = intro_out["intro_markdown"]
            matter_out = eng.front_back_matter(
                producer_inputs, contributors, order, producer.get("display_name"),
                request.get("copyright_year") or datetime.date.today().year,
                subtitle=request.get("subtitle") or "")
            front_matter = matter_out["front_matter_markdown"]
            back_matter = matter_out["back_matter_markdown"]
        else:
            sys.stderr.write("[stage_%s] no producer_inputs in request.json; the editor's "
                             "introduction and front/back matter are skipped rather than "
                             "fabricated (AF-AE-S9-FABRICATION) -- the manuscript still "
                             "compiles from the frozen chapters and bios.\n" % STAGE)
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] %s\n" % (STAGE, exc))
        return classify_child_rc(getattr(exc, "exit_code", logic.EX_ERR))
    except Exception as exc:  # noqa: BLE001 -- model_router itself raises bare
        # exceptions (never an S9Error) for an unresolved model-map/credential
        # chain; that is a collaborator-not-yet-configured condition (held),
        # not an "unexpected" stage bug -- classify it as such rather than
        # falling through to main()'s bare EX_ERR handler.
        sys.stderr.write("[stage_%s] %d/%d %s: model_router dependency not ready: %s\n"
                         % (STAGE, 3, len(WIRING), rel, exc))
        return EX_HELD

    # 4. anthology_state.py -- compile from FROZEN approved chapter artifacts,
    #    sha256 byte-identical per chapter (S9Assembly.compile_manuscript, which
    #    itself calls assembly-advance --to compiled --verify-sha).
    rel, _ = WIRING[3]
    manuscript_path = Path(rundir) / "working" / "manuscript.md"
    try:
        compiled = eng.compile_manuscript(order, frozen_shas, front_matter, intro_markdown,
                                          bios_by_key, back_matter, transitions=transitions,
                                          finale=finale, out_path=manuscript_path)
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] %d/%d %s: %s\n" % (STAGE, 4, len(WIRING), rel, exc))
        return classify_child_rc(getattr(exc, "exit_code", logic.EX_ERR))

    # 5. qc-tier1-anthology.py -- assembly-scope Gate B (S9Assembly.assembly_gate_b).
    rel, _ = WIRING[4]
    gate = eng.assembly_gate_b(manuscript_path, order, contributors)
    if not gate["passed"]:
        sys.stderr.write("[stage_%s] %d/%d %s: assembly Gate B failed (rc=%s)\n"
                         % (STAGE, 5, len(WIRING), rel, gate["rc"]))
        return classify_child_rc(gate["rc"] or logic.EX_PROVER)

    # record the manuscript artifact row (S9Assembly.record_manuscript_artifact;
    # part of WIRING[3]'s "compile" role -- the sole writer records what step 4
    # just proved byte-identical).
    try:
        eng.record_manuscript_artifact(compiled["manuscript_sha256"], bios_out.get("model_used"))
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] non-fatal: manuscript artifact record did not persist "
                         "cleanly: %s\n" % (STAGE, exc))

    # 6. stage_s8_deliver.py -- deliver the full manuscript Doc + PDF, push the
    #    manuscript fields.
    rel, _ = WIRING[5]
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "--participant-key",
                          order[0] if order else anthology_id, "--run-dir", str(rundir),
                          "--deliverable", "anthology_manuscript", "--final", "--json"])
    if rc != EX_OK:
        return rc

    signoff_confirm = request.get("signoff_confirm_name")
    if not signoff_confirm:
        sys.stderr.write("[stage_%s] manuscript compiled and delivered; awaiting the producer's "
                         "separate s9_producer sign-off.\n" % STAGE)
        return EX_OK

    # 7. anthology_state.py -- record the s9_producer sign-off that closes the
    #    anthology (S9Assembly.sign_off).
    rel, _ = WIRING[6]
    try:
        rc, _signoff = eng.sign_off(producer_id, notes=request.get("signoff_notes"))
    except logic.S9Error as exc:
        sys.stderr.write("[stage_%s] %d/%d %s: %s\n" % (STAGE, 7, len(WIRING), rel, exc))
        return classify_child_rc(getattr(exc, "exit_code", logic.EX_ERR))
    classified = classify_child_rc(rc)
    if classified != EX_OK:
        return classified

    # 8. mc_board.py -- mirror the Assembly card sign-off (signed_off); the
    #    engine never sets 'done' (the QC scorer owns review->done at >=8.5).
    rel, _ = WIRING[7]
    rc, _ = _step(7, rel, [py, str(_resolve(rel)), "sync", "--subject-key", anthology_id, "--json"])
    if rc != EX_OK:
        return rc

    return EX_OK


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
    print("stage_%s self-test: OK (exit-code map + wiring contract coherent)" % STAGE)
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="thin dispatcher for stage %s (%s)" % (STAGE, STAGE_NAME))
    ap.add_argument("--%s" % KEY_ARG, dest="key", help="the %s to dispatch" % KEY_ARG)
    ap.add_argument("--run-dir", help="optional per-participant-per-stage run directory")
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
        return _invoke_wiring(args.key, args.run_dir)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[stage_%s] unexpected error: %s\n" % (STAGE, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())

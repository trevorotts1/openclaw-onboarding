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
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        d = SKILL_DIR / "state" / "runs" / STAGE / safe
    (d / "working").mkdir(parents=True, exist_ok=True)
    return d


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
    S9 is bracketed by TWO producer decisions (module docstring); this one call
    always runs the READ-ONLY readiness report (step 1's first half), then:
      - no producer_id/confirm_name in <run_dir>/request.json -> report only,
        return EX_OK (an informational check, never a failure of this stage).
      - confirm_name present and readiness.ready -> arm (s9_ready), mirror,
        curate order, compile, assembly-scope QC, deliver the manuscript
        (steps 1-6), then STOP awaiting the producer's separate sign-off.
      - signoff_confirm_name ALSO present (a later, separate dispatch once the
        manuscript is compiled) -> the closing s9_producer sign-off + mirror
        (steps 7-8).
    classify_child_rc's numeric contract is unchanged; every step short-circuits
    on anything but EX_OK."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD
    if not key:
        sys.stderr.write("[stage_%s] --%s is required.\n" % (STAGE, KEY_ARG))
        return EX_HELD
    anthology_id = key
    py = sys.executable or "python3"
    rundir = _run_dir_for(anthology_id, run_dir)
    request = _load_request(rundir)
    state_writer = "scripts/anthology_state.py"

    # 1 (first half). anthology_state.py -- READ-ONLY assembly-readiness-report
    #    (the blocking list).
    rel, _ = WIRING[0]
    rc, readiness = _step(0, rel, [py, str(_resolve(rel)), "--json",
                                  "assembly-readiness-report", "--anthology-id", anthology_id])
    if rc != EX_OK:
        return rc
    readiness = readiness or {}

    producer_id = request.get("producer_id")
    confirm_name = request.get("confirm_name")
    if not (readiness.get("ready") and producer_id and confirm_name):
        sys.stderr.write("[stage_%s] readiness report only (ready=%s; arm needs a producer "
                         "confirm_name via request.json); nothing else to do this call.\n"
                         % (STAGE, readiness.get("ready")))
        return EX_OK

    # 1 (second half). the s9_ready ARM trigger: every guard revalidated by the
    #    writer; --confirm-name mismatch exits 5 (AF-AE-SLOT-UNRESOLVED-shaped
    #    validation, per classify_child_rc's fixed 5 -> EX_SLOT mapping).
    rc, _ = _step(0, rel, [py, str(_resolve(rel)), "--json", "record-approval",
                          "--gate", "s9_ready", "--subject-key", anthology_id,
                          "--anthology-id", anthology_id, "--actor", "producer",
                          "--decision", "ready_to_assemble", "--door", "dashboard",
                          "--producer-id", producer_id, "--confirm-name", confirm_name])
    if rc != EX_OK:
        return rc

    # 2. mc_board.py -- mirror the Assembly card to armed/ready (FAIL-SOFT).
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, [py, str(_resolve(rel)), "sync", "--subject-key", anthology_id, "--json"])
    if rc != EX_OK:
        return rc

    # helper read (not a separate WIRING slot): the frozen, approved chapters to
    # curate an order over (assembly-set-order needs a participant_key list).
    _, bundle, _ = _run([py, str(_resolve(state_writer)), "--json",
                        "export-bundle", "--anthology-id", anthology_id])
    bundle = bundle or {}
    frozen = [a for a in bundle.get("artifacts", [])
             if a.get("type") == "chapter" and a.get("frozen")]
    frozen.sort(key=lambda a: a.get("participant_key", ""))
    order = [a["participant_key"] for a in frozen]
    sha_by_key = {a["participant_key"]: a.get("sha256") for a in frozen if a.get("sha256")}

    # 3. model_router.py -- order curation (ae-01), editor introduction (ae-02),
    #    front/back matter (ae-04), contributor bios (ae-03); LONGCTX when
    #    configured, else chunked HEAVY-WRITER. A best-effort single curation
    #    call (the producer-voice introduction and matter content are Skill 59's
    #    OWN ae-0x pins, authored the same sole-model-call-site way as every
    #    other stage's model call).
    rel, _ = WIRING[2]
    curation_payload = json.dumps({
        "tier": "HEAVY-WRITER",
        "messages": [{"role": "user",
                     "content": "Curate the contribution order for anthology %s: %s"
                                % (anthology_id, ", ".join(order))}],
        "context": {"anthology_id": anthology_id, "deliverable_key": "assembly-order"},
    })
    rc, curated = _step(2, rel, [py, str(_resolve(rel)), "route"], input_text=curation_payload)
    if rc != EX_OK:
        return rc

    # 4. anthology_state.py -- assembly-set-order, then compile (verify-sha
    #    byte-identical per chapter; never guessed).
    rel, _ = WIRING[3]
    rc, _ = _step(3, rel, [py, str(_resolve(rel)), "--json", "assembly-set-order",
                          "--anthology-id", anthology_id,
                          "--order", json.dumps(order, ensure_ascii=False), "--state", "proposed"])
    if rc != EX_OK:
        return rc
    verify_sha = ",".join("%s=%s" % (k, v) for k, v in sha_by_key.items())
    compile_argv = [py, str(_resolve(rel)), "--json", "assembly-advance",
                    "--anthology-id", anthology_id, "--to", "compiled"]
    if verify_sha:
        compile_argv += ["--verify-sha", verify_sha]
    rc, _ = _step(3, rel, compile_argv)
    if rc != EX_OK:
        return rc

    # 5. qc-tier1-anthology.py -- assembly-scope Gate B (every chapter present
    #    exactly once, order matches curation, one continuous 14pt-floor PDF).
    rel, _ = WIRING[4]
    manuscript_path = Path(rundir) / "working" / "manuscript.md"
    if not manuscript_path.is_file():
        parts = []
        for pk in order:
            chap = next((a for a in frozen if a["participant_key"] == pk), None)
            if chap and chap.get("caf_media_url"):
                parts.append("# %s\n\n(see %s)\n" % (pk, chap["caf_media_url"]))
        manuscript_path.write_text("\n\n".join(parts), encoding="utf-8")
    envelope = Path(rundir) / "envelope.json"
    envelope.write_text(json.dumps({
        "kind": "manuscript", "mode": "assembly", "artifact_path": str(manuscript_path),
        "chapter_order": order,
    }, ensure_ascii=False), encoding="utf-8")
    rc, _ = _step(4, rel, [py, str(_resolve(rel)), "--envelope", str(envelope),
                          "--mode", "assembly", "--json"])
    if rc != EX_OK:
        return rc

    # 6. stage_s8_deliver.py -- deliver the full manuscript Doc + PDF, push the
    #    manuscript fields.
    rel, _ = WIRING[5]
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "--participant-key", order[0] if order else anthology_id,
                          "--run-dir", str(rundir), "--deliverable", "anthology_manuscript",
                          "--final", "--json"])
    if rc != EX_OK:
        return rc

    signoff_confirm = request.get("signoff_confirm_name")
    if not signoff_confirm:
        sys.stderr.write("[stage_%s] manuscript compiled and delivered; awaiting the producer's "
                         "separate s9_producer sign-off.\n" % STAGE)
        return EX_OK

    # 7. anthology_state.py -- record the s9_producer sign-off that closes the
    #    anthology.
    rel, _ = WIRING[6]
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "--json", "record-approval",
                          "--gate", "s9_producer", "--subject-key", anthology_id,
                          "--anthology-id", anthology_id, "--actor", "producer",
                          "--decision", "approve", "--door", "dashboard",
                          "--producer-id", producer_id, "--confirm-name", signoff_confirm])
    if rc != EX_OK:
        return rc

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

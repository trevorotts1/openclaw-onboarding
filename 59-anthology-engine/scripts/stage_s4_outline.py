#!/usr/bin/env python3
"""stage_s4_outline.py -- thin stage dispatcher for s4 (BLURB AND OUTLINE).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S4 blurb and outline: Book Blurb then single-chapter Create Outline placing EVERY
personal story strategically. Producer gate, then participant outline approval on the
token page. NO manual outline re-upload exists anywhere.

Persona (PRD Section 13): anthology-chapter-author speaking the Blurb Copywriter (aw-07) and the Outline Architect (aw-08).

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

STAGE = "s4"
STAGE_NAME = "BLURB AND OUTLINE"
KEY_ARG = "participant-key"
PERSONA = "anthology-chapter-author speaking the Blurb Copywriter (aw-07) and the Outline Architect (aw-08)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S4.
WIRING = [
    ("scripts/anthology_state.py", "load the participant row (locked title/subtitle, tone, questions, chapter_about, personal_stories)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): Book Blurb pin aw-07 then Create Outline pin aw-08 (every personal story placed)"),
    ("scripts/qc-tier1-anthology.py", "story-placement prover (every story present) and the title-lock carry"),
    ("scripts/stage_s8_deliver.py", "deliver the Blurb and Outline Docs plus PDFs"),
    ("scripts/gate_engine.py", "open the s4_producer gate, then on approve the s4_participant outline-approval gate on the token page"),
    ("scripts/anthology_state.py", "record both approvals and advance to s5_chapter"),
    ("scripts/mc_board.py", "mirror the participant card to review across both s4_gate_producer and s4_gate_participant, then to in_progress once both approvals advance the cursor to s5_chapter (SPEC 11.2, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"


def _run_dir_for(key, run_dir=None):
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        # ONE canonical directory per participant, shared by EVERY authoring stage.
        # It used to be stage-scoped (state/runs/<STAGE>/<safe>), which meant S2 handed
        # 54-anthology-writer/anthology-entry.sh an EMPTY directory: run_anthology.py
        # walks its phases from P0-INTAKE every time and fails closed at the first phase
        # whose gate artifacts are absent, and those artifacts (working/intake.json,
        # working/avatar.md) were written by S1 into a DIFFERENT directory. Every stage
        # now resolves the same path, so later stages read back what earlier ones wrote.
        # NOTE: "participants" is a fixed literal, never a stage name, so this can never
        # collide with the anthology-level assembly dir at state/runs/s9/<anthology_id>
        # that gate_engine.py::_s9_run_dir must keep resolving identically.
        d = SKILL_DIR / "state" / "runs" / "participants" / safe
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


def _write_envelope(run_dir, kind, working_file, extra=None):
    working = Path(run_dir) / "working" / working_file
    env = {"kind": kind, "artifact_path": str(working)}
    if extra:
        env.update(extra)
    path = Path(run_dir) / ("envelope-%s.json" % kind)
    path.write_text(json.dumps(env, ensure_ascii=False), encoding="utf-8")
    return path


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
    Steps 1-5 (load -> author blurb+outline -> QC both -> deliver both -> open
    the producer gate) run synchronously here. Steps 6-7 (record BOTH the
    producer's and then the participant's approval, stamp the resulting cursor,
    mirror it) are the documented job of gate_engine.py's own "decide" endpoint
    invoked directly by the dashboard/token-page webhook on each actual approval
    -- not this authoring-time dispatch, which has no approval to record yet.
    classify_child_rc's numeric contract is unchanged; every executed step
    short-circuits on anything but EX_OK."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD
    if not key or KEY_DELIM not in key:
        sys.stderr.write("[stage_%s] --%s must be a contact_id%santhology_id composite "
                         "key.\n" % (STAGE, KEY_ARG, KEY_DELIM))
        return EX_HELD
    pkey = key
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)

    # 1. anthology_state.py -- load the participant row (locked title/subtitle,
    #    tone, questions, chapter_about, personal_stories).
    rel, _ = WIRING[0]
    rc, _ = _step(0, rel, [py, str(_resolve(rel)), "--json",
                          "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 2. 54-anthology-writer/anthology-entry.sh -- Layer 1 Book Blurb (aw-07) then
    #    Create Outline (aw-08, every personal story placed); Skill 54 does not
    #    declare a distinct blurb/outline phase id of its own -- both land inside
    #    its P1-FIDELITY window (avatar/tone/title fidelity carried forward, blurb
    #    and outline authored alongside) per ANTHOLOGY-MANIFEST.json's own phase
    #    ownership notes; writes working/blurb.md and working/outline.md.
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
                          "--upto", "P1-FIDELITY"])
    if rc != EX_OK:
        return rc

    # 3. qc-tier1-anthology.py -- story-placement prover + title-lock carry, over
    #    BOTH deliverables (blurb, then outline).
    rel, _ = WIRING[2]
    for kind, wf in (("blurb", "blurb.md"), ("outline", "outline.md")):
        envelope = _write_envelope(rundir, kind, wf)
        rc, _ = _step(2, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
        if rc != EX_OK:
            return rc

    # 4. stage_s8_deliver.py -- deliver the Blurb and Outline Docs + PDFs. --gate
    #    s4 moves the Convert and Flow opportunity to the mapped pipeline stage
    #    (Outline) from the registry caf_stage_map (never hardcoded); both
    #    deliverables in this stage share engine gate s4, so a second move is an
    #    idempotent re-move to the same stage; scope-denied stays HELD (exit 3),
    #    never fatal (B6 / SPEC 7.6).
    rel, _ = WIRING[3]
    for kind in ("blurb", "outline"):
        rc, delivered = _step(3, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                      "--run-dir", str(rundir), "--deliverable", kind,
                                      "--gate", "s4", "--json"])
        if rc != EX_OK:
            return rc
        delivered = delivered or {}
        if delivered.get("doc_url") or delivered.get("pdf_url"):
            art_argv = [py, str(_resolve(WIRING[0][0])), "--json", "record-artifact",
                       "--participant-key", pkey, "--type", kind]
            if delivered.get("doc_url"):
                art_argv += ["--doc-url", delivered["doc_url"]]
            if delivered.get("pdf_url"):
                art_argv += ["--pdf-url", delivered["pdf_url"]]
            art_rc, _p, _e = _run(art_argv)
            if classify_child_rc(art_rc) != EX_OK:
                sys.stderr.write("[stage_%s] non-fatal: %s artifact record did not persist "
                                 "cleanly (rc=%s); the doc/pdf still delivered.\n"
                                 % (STAGE, kind, art_rc))

    # 5. gate_engine.py -- open s4_producer (mints + fires ONE nudge internally);
    #    the s4_participant outline-approval gate opens on the producer's approve.
    rel, _ = WIRING[4]
    rc, _ = _step(4, rel, [py, str(_resolve(rel)), "open", "--subject-key", pkey, "--json"])
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
    ap.add_argument("--run-dir", help="optional per-participant run directory")
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

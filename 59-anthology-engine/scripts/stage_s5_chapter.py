#!/usr/bin/env python3
"""stage_s5_chapter.py -- thin stage dispatcher for s5 (CHAPTER).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S5 chapter: ONE complete chapter, 2,000 to 3,500 MEASURED stripped words, title locked,
every story placed. The FULL Gate B battery runs BEFORE the gate opens; the participant
never sees an ungated draft. Producer RELEASE gate (board door): s5_producer -- a
committed producer approve of the delivered chapter fires the anthology-release-chapter
tag through the gate-engine release bus (GATE_BY_CURSOR cursor s5_chapter), release-only
(no cursor move). Participant gate: Approve as-is OR Request rewrite with notes.

Persona (PRD Section 13): anthology-chapter-author speaking the Anthology Chapter Author (aw-09).

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

STAGE = "s5"
STAGE_NAME = "CHAPTER"
KEY_ARG = "participant-key"
PERSONA = "anthology-chapter-author speaking the Anthology Chapter Author (aw-09)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S5.
WIRING = [
    ("scripts/anthology_state.py", "load everything from the ledger (never re-asked)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): P5 Write Chapter pin aw-09 on the HEAVY-WRITER tier"),
    ("scripts/qc-tier1-anthology.py", "full Tier 1 set: band 2,000 to 3,500 measured, title lock, every story, no leakage, no placeholder"),
    ("scripts/judge_harness.py", "the Tier 2 ten-dimension rubric on the JUDGE tier (never the drafting tier)"),
    ("scripts/qc-strike-gate.py", "internal QC attempts counter (max 3); hold-and-alert on strike-out"),
    ("scripts/stage_s8_deliver.py", "deliver the Chapter Doc plus PDF; the card lands in review"),
    ("scripts/gate_engine.py", "producer chapter RELEASE gate (board door) s5_producer fires anthology-release-chapter on a committed producer approve; then open the s5_participant gate: exactly two actions on the token page"),
    ("scripts/anthology_state.py", "freeze the chapter on approve, or route to s6_rewrite on request_rewrite with the notes appended to chapter_updates"),
    ("scripts/mc_board.py", "mirror the participant card to in_progress as the decision advances the cursor to s7_cover (approve) or s6_rewrite (request_rewrite) -- both land in_progress (SPEC 11.2, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"
WORKING_FILE = "chapter.md"    # 54-anthology-writer/run_anthology.py working/chapter.md


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
    return classified, parsed, rc


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
    Steps 1-6 (load -> author -> Tier 1 -> Tier 2 -> strike-count -> deliver ->
    open the participant gate) run synchronously here. Steps 8-9 (freeze OR route
    to s6_rewrite, mirror the result) are the documented job of gate_engine.py's
    own "decide" endpoint on the participant's actual Approve/Request-rewrite
    action -- not this authoring-time dispatch. classify_child_rc's numeric
    contract is unchanged; every executed step short-circuits on anything but
    EX_OK, EXCEPT the QC battery, whose pass/fail outcome is deliberately routed
    THROUGH qc-strike-gate.py (never short-circuited directly on a bare Tier 1/2
    failure) so the retry-budget counter and the strike-out alert stay correct."""
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
    anthology_id = pkey.split(KEY_DELIM, 1)[1]
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)

    # 1. anthology_state.py -- load everything (never re-asked).
    rel, _ = WIRING[0]
    rc, _, _ = _step(0, rel, [py, str(_resolve(rel)), "--json",
                             "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 2. 54-anthology-writer/anthology-entry.sh -- Layer 1 P5 Write Chapter (aw-09)
    #    on the HEAVY-WRITER tier; writes working/chapter.md.
    rel, _ = WIRING[1]
    rc, _, _ = _step(1, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
                             "--upto", "P5-CHAPTER-AUTHOR"])
    if rc != EX_OK:
        return rc

    # 3. qc-tier1-anthology.py -- the full Tier 1 set (band, title lock, every
    #    story, no leakage, no placeholder).
    rel, _ = WIRING[2]
    chapter_path = Path(rundir) / "working" / WORKING_FILE
    envelope = Path(rundir) / "envelope.json"
    envelope.write_text(json.dumps({"kind": "chapter", "artifact_path": str(chapter_path)},
                                   ensure_ascii=False), encoding="utf-8")
    rc, _, tier1_rc = _step(2, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
    tier1_ok = (tier1_rc == 0)

    # 4. judge_harness.py -- the Tier 2 ten-dimension rubric on the JUDGE tier
    #    (never the drafting tier).
    rel, _ = WIRING[3]
    judge_envelope = Path(rundir) / "judge-envelope.json"
    judge_envelope.write_text(json.dumps({
        "kind": "chapter", "deliverable_path": str(chapter_path),
        "participant_key": pkey, "anthology_id": anthology_id,
    }, ensure_ascii=False), encoding="utf-8")
    rc, _, judge_rc = _step(3, rel, [py, str(_resolve(rel)), "judge",
                                    "--envelope", str(judge_envelope), "--json"])
    judge_ok = (judge_rc == 0)

    # 5. qc-strike-gate.py -- the internal QC attempts counter (max 3); the
    #    combined Tier 1 + Tier 2 outcome is ONE QC attempt for this deliverable.
    rel, _ = WIRING[4]
    qc_pass = tier1_ok and judge_ok
    strike_argv = [py, str(_resolve(rel)), "--json", "qc-attempt",
                  "--participant-key", pkey, "--deliverable", "chapter",
                  "--result", "pass" if qc_pass else "fail"]
    rc, _, strike_rc = _step(4, rel, strike_argv)
    if not qc_pass:
        sys.stderr.write("[stage_%s] chapter did not clear Gate B this attempt "
                         "(tier1_rc=%s judge_rc=%s); qc-strike-gate recorded the "
                         "attempt (rc=%s).\n" % (STAGE, tier1_rc, judge_rc, strike_rc))
        return EX_PROVER
    if rc != EX_OK:
        return rc

    # 6. stage_s8_deliver.py -- deliver the Chapter Doc + PDF; the card lands
    #    in review. --gate s5 moves the Convert and Flow opportunity to the mapped
    #    pipeline stage (Chapter) from the registry caf_stage_map (never
    #    hardcoded); a rewrite (S6) re-enters the s5 gate and maps to the SAME
    #    Chapter stage, so no separate move is needed there; scope-denied stays
    #    HELD (exit 3), never fatal (B6 / SPEC 7.6).
    rel, _ = WIRING[5]
    rc, delivered, _ = _step(5, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                     "--run-dir", str(rundir), "--deliverable", "chapter",
                                     "--gate", "s5", "--json"])
    if rc != EX_OK:
        return rc
    delivered = delivered or {}

    # 7. anthology_state.py -- record-artifact(chapter) from what stage_s8_deliver
    #    just delivered (part of "load everything ... never re-asked" -- the same
    #    sole writer already declared at WIRING[0]).
    art_argv = [py, str(_resolve(WIRING[0][0])), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "chapter"]
    if delivered.get("doc_url"):
        art_argv += ["--doc-url", delivered["doc_url"]]
    if delivered.get("pdf_url"):
        art_argv += ["--pdf-url", delivered["pdf_url"]]
    art_rc, _p, _e = _run(art_argv)
    if classify_child_rc(art_rc) != EX_OK:
        sys.stderr.write("[stage_%s] non-fatal: chapter artifact record did not persist "
                         "cleanly (rc=%s); the doc/pdf still delivered.\n" % (STAGE, art_rc))

    # 8. gate_engine.py -- open s5_participant: exactly two actions on the token
    #    page (Approve as-is / Request rewrite with notes).
    rel, _ = WIRING[6]
    rc, _, _ = _step(6, rel, [py, str(_resolve(rel)), "open", "--subject-key", pkey, "--json"])
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

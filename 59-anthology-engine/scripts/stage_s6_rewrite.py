#!/usr/bin/env python3
"""stage_s6_rewrite.py -- thin stage dispatcher for s6 (CHAPTER REWRITE).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S6 rewrite (optional, budget 2): the notes become chapter_updates; the Thornfield persona
rewrites INSIDE the band with the title lock held; the result RE-ENTERS the S5 gate. A
silent third rewrite is an illegal transition the writer refuses.

Persona (PRD Section 13): anthology-chapter-author speaking Dr. Margaret Thornfield, editorial revisionist (aw-10).

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

STAGE = "s6"
STAGE_NAME = "CHAPTER REWRITE"
KEY_ARG = "participant-key"
PERSONA = "anthology-chapter-author speaking Dr. Margaret Thornfield, editorial revisionist (aw-10)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S6.
WIRING = [
    ("scripts/anthology_state.py", "load the current chapter and chapter_updates; confirm rewrite_count < 2"),
    ("scripts/qc-strike-gate.py", "owns rewrite_count (max 2 with S5 gate re-entry); at budget the gate offers Approve as-is or producer escalation"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): the Thornfield rewrite pin aw-10 inside the 2,000 to 3,500 band, title lock held"),
    ("scripts/qc-tier1-anthology.py", "the same chapter Tier 1 provers over the rewritten draft"),
    ("scripts/judge_harness.py", "the Tier 2 rubric on the JUDGE tier"),
    ("scripts/anthology_state.py", "record the new chapter VERSION and RE-ENTER the s5_gate"),
    ("scripts/mc_board.py", "mirror the participant card to review as the rewrite RE-ENTERS the s5_gate cursor (SPEC 11.2, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"
WORKING_FILE = "chapter.md"    # 54-anthology-writer/run_anthology.py working/chapter.md


def _run_dir_for(key, run_dir=None):
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


def _invoke_wiring(key, run_dir=None):
    """W4.0: the concrete argv chain per collaborator, in WIRING order (fixed).
    Unlike S1-S5, S6 has no NEW gate to open: the rewrite RE-ENTERS the existing
    s5_gate (a cursor write, not a fresh mint+nudge), so every declared
    collaborator runs synchronously in this one call. classify_child_rc's
    numeric contract is unchanged; every step short-circuits on anything but
    EX_OK."""
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

    # 1. anthology_state.py -- load the current chapter and chapter_updates.
    rel, _ = WIRING[0]
    rc, _ = _step(0, rel, [py, str(_resolve(rel)), "--json",
                          "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 2. qc-strike-gate.py -- confirm rewrite_count < 2 (READ-ONLY budget report;
    #    exhausted -> exit 4 -> EX_PROVER, offering Approve-as-is/escalate).
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, [py, str(_resolve(rel)), "--json",
                          "rewrite-gate", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 3. 54-anthology-writer/anthology-entry.sh -- the Thornfield rewrite pin
    #    aw-10 inside the 2,000-3,500 band, title lock held; rewrites
    #    working/chapter.md in place (the run dir's chapter_updates carries the
    #    participant's notes forward from the ledger read in step 1).
    rel, _ = WIRING[2]
    rc, _ = _step(2, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
                          "--upto", "P5-CHAPTER-AUTHOR"])
    if rc != EX_OK:
        return rc

    # 4. qc-tier1-anthology.py -- the same chapter Tier 1 provers over the
    #    rewritten draft.
    rel, _ = WIRING[3]
    chapter_path = Path(rundir) / "working" / WORKING_FILE
    envelope = Path(rundir) / "envelope.json"
    envelope.write_text(json.dumps({"kind": "rewrite", "artifact_path": str(chapter_path)},
                                   ensure_ascii=False), encoding="utf-8")
    rc, _ = _step(3, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 5. judge_harness.py -- the Tier 2 rubric on the JUDGE tier.
    rel, _ = WIRING[4]
    judge_envelope = Path(rundir) / "judge-envelope.json"
    judge_envelope.write_text(json.dumps({
        "kind": "chapter", "deliverable_path": str(chapter_path),
        "participant_key": pkey, "anthology_id": anthology_id,
    }, ensure_ascii=False), encoding="utf-8")
    rc, _ = _step(4, rel, [py, str(_resolve(rel)), "judge",
                          "--envelope", str(judge_envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 6. anthology_state.py -- record the new chapter VERSION and RE-ENTER s5_gate.
    rel, _ = WIRING[5]
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "--json", "record-artifact",
                          "--participant-key", pkey, "--type", "rewrite"])
    if rc != EX_OK:
        return rc
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "--json", "advance-stage",
                          "--participant-key", pkey, "--to", "s5_gate"])
    if rc != EX_OK:
        return rc

    # 7. mc_board.py -- mirror the participant card to review as the rewrite
    #    RE-ENTERS s5_gate (W4.3); FAIL-SOFT.
    rel, _ = WIRING[6]
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
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

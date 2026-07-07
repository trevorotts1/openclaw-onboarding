#!/usr/bin/env python3
"""stage_s5_chapter.py -- thin stage dispatcher for s5 (CHAPTER).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S5 chapter: ONE complete chapter, 2,000 to 3,500 MEASURED stripped words, title locked,
every story placed. The FULL Gate B battery runs BEFORE the gate opens; the participant
never sees an ungated draft. Participant gate: Approve as-is OR Request rewrite with notes.

Persona (PRD Section 13): anthology-chapter-author speaking the Anthology Chapter Author (aw-09).

Exit codes (SPEC 3.4 row 6; house: 1 unexpected error):
  0  stage complete and persisted
  2  prover failure (counts a QC attempt)
  3  held (credits, lost callback, or a collaborator not yet wired)
  5  unresolved prompt slot (AF-AE-SLOT-UNRESOLVED)
"""
import argparse
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
    ("scripts/gate_engine.py", "open the s5_participant gate: exactly two actions on the token page"),
    ("scripts/anthology_state.py", "freeze the chapter on approve, or route to s6_rewrite on request_rewrite with the notes appended to chapter_updates"),
    ("scripts/mc_board.py", "mirror the participant card to in_progress as the decision advances the cursor to s7_cover (approve) or s6_rewrite (request_rewrite) -- both land in_progress (SPEC 11.2, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


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


def _invoke_wiring(key):
    """INTEGRATOR: replace this body with the concrete argv per collaborator.
    The ordering (WIRING), resolution (_resolve), and classification
    (classify_child_rc) contract above is FIXED and must not change."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD
    sys.stderr.write("[stage_%s] all collaborators resolved; the serial integrator wires the concrete\n"
                     "call sequence per the WIRING contract. Holding until wired.\n" % STAGE)
    return EX_HELD


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
        return _invoke_wiring(args.key)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[stage_%s] unexpected error: %s\n" % (STAGE, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())

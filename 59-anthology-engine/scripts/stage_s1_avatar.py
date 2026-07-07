#!/usr/bin/env python3
"""stage_s1_avatar.py -- thin stage dispatcher for s1 (AVATAR).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S1 avatar: the Skill 52 handoff (Avatar Questions 1 to 30, then 31 and 32 with the
auto-detected web search, then Rewrite Avatar Niche and Primary Goal, then Primary
Goal extraction on the LIGHT tier). Producer gate on the board review column.

Persona (PRD Section 13): anthology-chapter-author speaking the Avatar Profiler (Skill 52 aa-01 to aa-03).

Exit codes (SPEC 3.4 row 6; house: 1 unexpected error):
  0  stage complete and persisted
  2  prover failure (counts a QC attempt)
  3  held (credits, lost callback, or a collaborator not yet wired)
  5  unresolved prompt slot (AF-AE-SLOT-UNRESOLVED)
"""
import argparse
import sys
from pathlib import Path

STAGE = "s1"
STAGE_NAME = "AVATAR"
KEY_ARG = "participant-key"
PERSONA = "anthology-chapter-author speaking the Avatar Profiler (Skill 52 aa-01 to aa-03)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S1.
WIRING = [
    ("scripts/anthology_state.py", "load the participant row (ideal_avatar, niche, primary_goal, name)"),
    ("scripts/search_detect.py", "detect the client web-search tool for Avatar Questions 31 and 32 (prefer Perplexity; degrade plus one deduped flag)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): the avatar handoff pins aa-01 to aa-03 plus aw-12 primary-goal extraction, in a per-participant run dir"),
    ("scripts/guard-prompt-pins.py", "prove the composed pins match their sha256 (aa-01 to aa-03, aw-12); zero truncation"),
    ("scripts/qc-tier1-anthology.py", "Gate B Tier 1 checks 4 to 12"),
    ("scripts/stage_s8_deliver.py", "deliver the Avatar Doc plus PDF at S8 standards"),
    ("scripts/anthology_state.py", "record-artifact (avatar) and advance the cursor to s1_gate"),
    ("scripts/gate_engine.py", "open the s1_producer gate; nudge_send.py fires ONE gate-open nudge"),
    ("scripts/mc_board.py", "mirror the participant card to review at the s1_gate cursor (SPEC 11.2 stage_cursor projection, W4.3); FAIL-SOFT, never blocks the pipeline"),
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

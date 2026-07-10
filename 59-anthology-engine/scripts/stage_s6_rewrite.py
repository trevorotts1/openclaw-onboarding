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

# SPEC S6 participant rewrite budget (mirrors anthology_state.REWRITE_BUDGET and
# caf_delivery.FieldMap.REWRITE_BUDGET). The hard 'no 3rd rewrite' refusal is
# enforced at the s5 request_rewrite gate; this is used only to surface the count.
REWRITE_BUDGET = 2

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S6.
WIRING = [
    ("scripts/anthology_state.py", "load the current chapter and chapter_updates; read the rewrite_count (this rewrite's 1-based number, incremented once at the s5 request_rewrite gate)"),
    ("scripts/qc-strike-gate.py", "surface the rewrite budget (max 2, S5 gate re-entry): count 1 leaves one rewrite; count 2 is the final, budget-exhausting rewrite. The hard 'no 3rd rewrite' refusal is owned by anthology_state at request time, not here"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): the Thornfield rewrite pin aw-10 inside the 2,000 to 3,500 band, title lock held"),
    ("scripts/qc-tier1-anthology.py", "the same chapter Tier 1 provers over the rewritten draft"),
    ("scripts/judge_harness.py", "the Tier 2 rubric on the JUDGE tier"),
    ("scripts/stage_s8_deliver.py", "deliver the rewritten chapter into its OWN preservation pair (rewrite1 for the first rewrite, rewrite2 for the second) so the base chapter + any earlier rewrite stay INTACT (PRD Gap G10); byte-for-byte read-back"),
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
    # raw child rc is returned alongside the classified code so the rewrite-gate
    # step can tell a legal budget-exhausting rewrite (child exit 4) apart from a
    # real gate error (child exit 2/3), which classify_child_rc collapses together.
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
    Unlike S1-S5, S6 has no NEW gate to open: the rewrite RE-ENTERS the existing
    s5_gate (a cursor write, not a fresh mint+nudge). It DOES deliver: the
    rewritten chapter lands in its own preservation pair (rewrite1/rewrite2), never
    the base chapter pair, so the original survives (PRD Gap G10). classify_child_rc's
    numeric contract is unchanged; every step short-circuits on anything but EX_OK,
    EXCEPT the rewrite-gate, whose budget-exhausting exit 4 is a LEGAL final-rewrite
    state (see below)."""
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

    # 1. anthology_state.py -- load the current chapter and chapter_updates; read
    #    the rewrite_count (this rewrite's 1-based number).
    rel, _ = WIRING[0]
    rc, participant, _ = _step(0, rel, [py, str(_resolve(rel)), "--json",
                                       "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc
    rewrite_number = None
    try:
        rewrite_number = int((participant or {}).get("rewrite_count"))
    except (TypeError, ValueError):
        rewrite_number = None

    # 2. qc-strike-gate.py -- surface the rewrite budget. The increment is owned by
    #    anthology_state at the s5_participant/request_rewrite gate (the sole, hard
    #    'no 3rd rewrite' enforcer), so by the time S6 runs the count is already 1 or
    #    2. The gate reports budget REMAINING: exit 0 while a rewrite is still left
    #    (count 1), exit 4 (EX_EXHAUSTED) when THIS is the last one (count 2). BOTH
    #    are legal authoring states -- exit 4 here does NOT block the second rewrite;
    #    it only means no further rewrite may be requested after this. Only a real
    #    gate error (child exit 2 validation / 3 held) stops us.
    rel, _ = WIRING[1]
    rc, gate_dec, raw = _step(1, rel, [py, str(_resolve(rel)), "--json",
                                      "rewrite-gate", "--participant-key", pkey])
    if raw not in (0, 4):          # 0 = budget remains, 4 = final (budget-exhausting) rewrite
        return rc
    if rewrite_number is None:
        try:
            rewrite_number = int((gate_dec or {}).get("rewrite_count"))
        except (TypeError, ValueError):
            rewrite_number = None
    remaining = (gate_dec or {}).get("remaining")
    sys.stderr.write("[stage_%s] rewrite #%s of %s (rewrites remaining after this: %s); the "
                     "rewritten chapter will be preserved in slot rewrite%s.\n"
                     % (STAGE, rewrite_number, REWRITE_BUDGET, remaining, rewrite_number))

    # 3. 54-anthology-writer/anthology-entry.sh -- the Thornfield rewrite pin
    #    aw-10 inside the 2,000-3,500 band, title lock held; rewrites
    #    working/chapter.md in place (the run dir's chapter_updates carries the
    #    participant's notes forward from the ledger read in step 1).
    rel, _ = WIRING[2]
    rc, _, _ = _step(2, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
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
    rc, _, _ = _step(3, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 5. judge_harness.py -- the Tier 2 rubric on the JUDGE tier.
    rel, _ = WIRING[4]
    judge_envelope = Path(rundir) / "judge-envelope.json"
    judge_envelope.write_text(json.dumps({
        "kind": "chapter", "deliverable_path": str(chapter_path),
        "participant_key": pkey, "anthology_id": anthology_id,
    }, ensure_ascii=False), encoding="utf-8")
    rc, _, _ = _step(4, rel, [py, str(_resolve(rel)), "judge",
                             "--envelope", str(judge_envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 6. stage_s8_deliver.py -- deliver the rewrite into rewrite1/rewrite2 (G10).
    #    S8 re-reads the ledger rewrite_count itself and routes the slot; passing
    #    --deliverable rewrite (never rewrite1/rewrite2 directly) keeps the slot
    #    decision in one place and the base chapter pair untouched. The same rundir
    #    is threaded so working/chapter.md (the just-rewritten draft) is packaged.
    rel, _ = WIRING[5]
    rc, delivered, _ = _step(5, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                     "--run-dir", str(rundir), "--deliverable", "rewrite", "--json"])
    if rc != EX_OK:
        return rc
    delivered = delivered or {}
    if delivered.get("rewrite_slot"):
        sys.stderr.write("[stage_%s] rewrite delivered to %s (base chapter left intact).\n"
                         % (STAGE, delivered["rewrite_slot"]))

    # 7. anthology_state.py -- record the new chapter VERSION and RE-ENTER s5_gate.
    rel, _ = WIRING[6]
    art_argv = [py, str(_resolve(rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "rewrite"]
    if delivered.get("doc_url"):
        art_argv += ["--doc-url", delivered["doc_url"]]
    rc, _, _ = _step(6, rel, art_argv)
    if rc != EX_OK:
        return rc
    rc, _, _ = _step(6, rel, [py, str(_resolve(rel)), "--json", "advance-stage",
                             "--participant-key", pkey, "--to", "s5_gate"])
    if rc != EX_OK:
        return rc

    # 8. mc_board.py -- mirror the participant card to review as the rewrite
    #    RE-ENTERS s5_gate (W4.3); FAIL-SOFT.
    rel, _ = WIRING[7]
    rc, _, _ = _step(7, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
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

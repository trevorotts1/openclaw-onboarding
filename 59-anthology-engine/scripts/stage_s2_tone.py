#!/usr/bin/env python3
"""stage_s2_tone.py -- thin stage dispatcher for s2 (TONE).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S2 tone: Skill 54 P2 TONE using shared-utils/tone-writing-core byte identical (Write
Tone Style 1 to 4 then Write Blended Tone; 3,000 MEASURED words). Producer gate.

Persona (PRD Section 13): anthology-chapter-author speaking the Tone Analysts and Blender (tone core 04 to 08).

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

STAGE = "s2"
STAGE_NAME = "TONE"
KEY_ARG = "participant-key"
PERSONA = "anthology-chapter-author speaking the Tone Analysts and Blender (tone core 04 to 08)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S2.
WIRING = [
    ("scripts/anthology_state.py", "load the participant row (tone form: describe_tone plus four influences)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): P2 TONE on the shared tone core, byte identical, never forked"),
    ("54-anthology-writer/scripts/verify_tone_core_sync.py", "prove the baked tone stages are byte identical to shared-utils/tone-writing-core (AF-AW-TONE-DRIFT)"),
    ("scripts/qc-tier1-anthology.py", "tone floor of 3,000 measured stripped words plus the Tier 1 subset"),
    ("scripts/stage_s8_deliver.py", "deliver the Tone Doc plus PDF"),
    ("scripts/anthology_state.py", "record-artifact (tone) and advance to s2_gate"),
    ("scripts/gate_engine.py", "open the s2_producer gate; ONE nudge to the ledger-resolved recipient"),
    ("scripts/mc_board.py", "mirror the participant card to review at the s2_gate cursor (SPEC 11.2 stage_cursor projection, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"
WORKING_FILE = "tone-doc.md"    # 54-anthology-writer/run_anthology.py working/tone-doc.md


def _run_dir_for(key, run_dir=None):
    """Resolve (and create) this run's per-participant working directory
    -- the SAME directory 54-anthology-writer/anthology-entry.sh --run-dir targets,
    so its working/*.md checkpoints are exactly what this dispatcher reads back."""
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
    """Invoke one WIRING collaborator; return (rc, parsed_json_or_None, stderr_tail)."""
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
    """Run WIRING[i]'s collaborator; classify via the FIXED contract; log. The
    caller short-circuits on anything but EX_OK (rc==0)."""
    sys.stderr.write("[stage_%s] %d/%d %s\n" % (STAGE, i + 1, len(WIRING), rel))
    rc, parsed, err = _run(argv, timeout=timeout)
    classified = classify_child_rc(rc)
    if classified != EX_OK:
        sys.stderr.write("[stage_%s] %s exited %d -> classified %d%s\n"
                         % (STAGE, rel, rc, classified,
                            (" :: %s" % err[-300:]) if err else ""))
    return classified, parsed


def _write_envelope(run_dir, kind, extra=None):
    """Assemble the qc-tier1-anthology.py envelope from the Layer 1 working/*.md
    checkpoint. If Layer 1 has not produced it yet, the envelope still points at
    the intended path; qc-tier1-anthology.py then correctly reports the gap."""
    working = Path(run_dir) / "working" / WORKING_FILE
    env = {"kind": kind, "artifact_path": str(working)}
    if extra:
        env.update(extra)
    path = Path(run_dir) / "envelope.json"
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
    classify_child_rc's numeric contract is unchanged; every step short-circuits
    the stage on anything but EX_OK."""
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

    # 1. anthology_state.py -- load the participant row (tone form).
    rel, _ = WIRING[0]
    rc, _ = _step(0, rel, [py, str(_resolve(rel)), "--json",
                          "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 2. 54-anthology-writer/anthology-entry.sh -- Layer 1 P2 TONE on the shared
    #    tone core, byte identical, never forked; writes working/tone-doc.md.
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
                          "--upto", "P2-TONE-AUTHOR"])
    if rc != EX_OK:
        return rc

    # 3. verify_tone_core_sync.py -- the baked tone stages are byte-identical to
    #    shared-utils/tone-writing-core (AF-AW-TONE-DRIFT); no per-run args.
    rel, _ = WIRING[2]
    rc, _ = _step(2, rel, [py, str(_resolve(rel))])
    if rc != EX_OK:
        return rc

    # 4. qc-tier1-anthology.py -- 3,000 measured-word tone floor + Tier 1 subset.
    rel, _ = WIRING[3]
    envelope = _write_envelope(rundir, "tone")
    rc, _ = _step(3, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 5. stage_s8_deliver.py -- deliver the Tone Doc + PDF. --gate s2 moves the
    #    Convert and Flow opportunity to the mapped pipeline stage (Tone) from the
    #    registry caf_stage_map (never hardcoded); scope-denied stays HELD (exit
    #    3), never fatal (B6 / SPEC 7.6).
    rel, _ = WIRING[4]
    rc, delivered = _step(4, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                  "--run-dir", str(rundir), "--deliverable", "tone",
                                  "--gate", "s2", "--json"])
    if rc != EX_OK:
        return rc
    delivered = delivered or {}

    # 6. anthology_state.py -- record-artifact(tone), then advance to s2_gate.
    rel, _ = WIRING[5]
    art_argv = [py, str(_resolve(rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "tone"]
    if delivered.get("doc_url"):
        art_argv += ["--doc-url", delivered["doc_url"]]
    if delivered.get("pdf_url"):
        art_argv += ["--pdf-url", delivered["pdf_url"]]
    if delivered.get("custom_field_keys_written"):
        art_argv += ["--custom-field-keys-written",
                    json.dumps(delivered["custom_field_keys_written"], ensure_ascii=False)]
    rc, _ = _step(5, rel, art_argv)
    if rc != EX_OK:
        return rc
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "--json", "advance-stage",
                          "--participant-key", pkey, "--to", "s2_gate"])
    if rc != EX_OK:
        return rc

    # 7. gate_engine.py -- open s2_producer (mints + fires ONE nudge internally
    #    to the ledger-resolved recipient).
    rel, _ = WIRING[6]
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "open", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc

    # 8. mc_board.py -- mirror the participant card to review at s2_gate (W4.3).
    #    FAIL-SOFT (A1): this TERMINAL board mirror is a pure projection; a board
    #    outage or refusal here NEVER holds the stage (the substantive work is done
    #    and persisted, the cursor is advanced, the gate is open). The daily reconcile
    #    tick re-syncs any card the board missed. "A dark board never blocks the
    #    pipeline."
    rel, _ = WIRING[7]
    rc, _ = _step(7, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        sys.stderr.write("[stage_%s] board mirror non-OK (rc=%d); FAIL-SOFT, stage "
                         "complete; the daily reconcile tick re-syncs the card.\n"
                         % (STAGE, rc))

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

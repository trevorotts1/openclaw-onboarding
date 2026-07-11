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
import json
import subprocess
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


KEY_DELIM = "::"
WORKING_FILE = "avatar.md"     # 54-anthology-writer/run_anthology.py working/avatar.md


def _run_dir_for(key, run_dir=None):
    """Resolve (and create) this run's per-participant-per-stage working directory
    -- the SAME directory 54-anthology-writer/anthology-entry.sh --run-dir targets,
    so its working/*.md checkpoints are exactly what this dispatcher reads back."""
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        d = SKILL_DIR / "state" / "runs" / STAGE / safe
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


def _write_intake_bridge(run_dir, participant, anthology):
    """Skill 54's own P0-INTAKE gate (54-anthology-writer/scripts/prove_aw_intake.py,
    INTAKE_REQUIRED) needs working/intake.json carrying exactly anthology_title,
    first_name, last_name, chapter_premise. This is the one, bounded, mechanical
    field-shape translation from this engine's ledger rows into that shape (never
    authoring content; a straight field rename). Idempotent: only written if a
    non-degenerate copy is not already present, so a re-run never clobbers a
    producer-hand-edited intake.json."""
    path = Path(run_dir) / "working" / "intake.json"
    if path.is_file():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
            if all(str(existing.get(k, "")).strip() for k in
                  ("anthology_title", "first_name", "last_name", "chapter_premise")):
                return path
        except (ValueError, OSError):
            pass
    intake = {
        "anthology_title": anthology.get("name") or anthology.get("anthology_id") or "",
        "first_name": participant.get("first_name") or "",
        "last_name": participant.get("last_name") or "",
        "chapter_premise": participant.get("chapter_about") or "",
    }
    path.write_text(json.dumps(intake, ensure_ascii=False), encoding="utf-8")
    return path


def _write_envelope(run_dir, kind, extra=None):
    """Assemble the qc-tier1-anthology.py envelope from the Layer 1 working/*.md
    checkpoint for this stage's deliverable. If Layer 1 has not produced it yet
    (no live model chain configured), the envelope still points at the intended
    path; qc-tier1-anthology.py then correctly (and honestly) reports a gap rather
    than this dispatcher fabricating content it has no authority to write."""
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
    anthology_id = pkey.split(KEY_DELIM, 1)[1]
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)

    # 1. anthology_state.py -- load the participant row.
    rel, _ = WIRING[0]
    rc, parsed = _step(0, rel, [py, str(_resolve(rel)), "--json",
                               "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc

    # 2. search_detect.py -- detect/resolve the client web-search tool for Avatar
    #    Questions 31/32 (prefer Perplexity; degrade + one deduped flag). exit 3
    #    (no tool) is a documented degrade path, not a hard failure of this stage.
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, [py, str(_resolve(rel)), "resolve", "--anthology-id", anthology_id])
    if rc not in (EX_OK, EX_HELD):
        return rc

    # helper read (not a separate WIRING slot): the anthology row, for the
    # working/intake.json bridge below (anthology_title).
    _, anth, _ = _run([py, str(_resolve(WIRING[0][0])), "--json",
                      "get-anthology", "--anthology-id", anthology_id])
    _write_intake_bridge(rundir, parsed or {}, anth or {})

    # 3. 54-anthology-writer/anthology-entry.sh -- Layer 1 avatar handoff (aa-01 to
    #    aa-03, aw-12), through the P0A-AVATAR checkpoint only; writes working/avatar.md.
    #    Skill 54's own P0-INTAKE gate (prove_aw_intake.py) needs its OWN
    #    working/intake.json shape (anthology_title/first_name/last_name/
    #    chapter_premise); _write_intake_bridge above is the one, bounded,
    #    mechanical translation from this engine's ledger rows into that shape.
    rel, _ = WIRING[2]
    rc, _ = _step(2, rel, ["bash", str(_resolve(rel)), "--run-dir", str(rundir),
                          "--upto", "P0A-AVATAR"])
    if rc != EX_OK:
        return rc

    # 4. guard-prompt-pins.py -- prove the composed pins (aa-01..03, aw-12) are
    #    byte-exact and untruncated (whole-skill static prover; no per-run args).
    rel, _ = WIRING[3]
    rc, _ = _step(3, rel, [py, str(_resolve(rel)), "--json"])
    if rc != EX_OK:
        return rc

    # 5. qc-tier1-anthology.py -- Gate B Tier 1 checks 4-12 over working/avatar.md.
    rel, _ = WIRING[4]
    envelope = _write_envelope(rundir, "avatar")
    rc, _ = _step(4, rel, [py, str(_resolve(rel)), "--envelope", str(envelope), "--json"])
    if rc != EX_OK:
        return rc

    # 6. stage_s8_deliver.py -- deliver the Avatar Doc + PDF at S8 standards.
    #    --gate s1 threads THIS engine stage into S8 so the Convert and Flow
    #    opportunity moves to the mapped pipeline stage (Avatar) from the
    #    registry caf_stage_map (NEVER hardcoded); the move fires only where the
    #    anthology is bound to a pipeline, and a scope-denied opportunity write
    #    surfaces as a HELD (exit 3), never a fatal error (B6 / SPEC 7.6).
    rel, _ = WIRING[5]
    rc, delivered = _step(5, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                  "--run-dir", str(rundir), "--deliverable", "avatar",
                                  "--gate", "s1", "--json"])
    if rc != EX_OK:
        return rc
    delivered = delivered or {}

    # 7. anthology_state.py -- record-artifact(avatar), then advance to s1_gate.
    rel, _ = WIRING[6]
    art_argv = [py, str(_resolve(rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "avatar"]
    if delivered.get("doc_url"):
        art_argv += ["--doc-url", delivered["doc_url"]]
    if delivered.get("pdf_url"):
        art_argv += ["--pdf-url", delivered["pdf_url"]]
    if delivered.get("custom_field_keys_written"):
        art_argv += ["--custom-field-keys-written",
                    json.dumps(delivered["custom_field_keys_written"], ensure_ascii=False)]
    rc, _ = _step(6, rel, art_argv)
    if rc != EX_OK:
        return rc
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "--json", "advance-stage",
                          "--participant-key", pkey, "--to", "s1_gate"])
    if rc != EX_OK:
        return rc

    # 8. gate_engine.py -- open s1_producer (mints + fires ONE gate-open nudge
    #    through nudge_send.py internally).
    rel, _ = WIRING[7]
    rc, _ = _step(7, rel, [py, str(_resolve(rel)), "open", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc

    # 9. mc_board.py -- mirror the participant card to review at s1_gate (W4.3).
    #    FAIL-SOFT (A1): the board is a pure projection of the ledger, so a board
    #    outage or refusal on this TERMINAL mirror NEVER holds the stage -- the
    #    substantive work (authoring, QC, delivery, artifact, cursor advance, gate
    #    open + nudge) is already done and persisted. The daily reconcile tick
    #    (mc_board.py reconcile) re-syncs any card the board missed. "A dark board
    #    never blocks the pipeline."
    rel, _ = WIRING[8]
    rc, _ = _step(8, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
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

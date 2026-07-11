#!/usr/bin/env python3
"""stage_s0_intake.py -- thin stage dispatcher for S0 (INTAKE AND ROUTING).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S0 is normally entered by the gateway webhook (route /hooks/anthology-intake)
driving intake_router.py with the RAW payload; this runner exists so the stage
inventory is complete (SPEC 3.4) and to allow a manual or exceptions-queue replay
of S0. Deterministic; NO model call. Keys on contact_id, never email.

Persona (PRD Section 13): none (deterministic code, anthology-producer-orchestrator).

Exit codes (SPEC 3.4 row 6; house: 1 unexpected error):
  0  stage complete and persisted
  2  prover or guard refusal (route-secret / validation)
  3  held (a collaborator not yet wired)
  5  unresolved slot
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

STAGE = "s0"
STAGE_NAME = "INTAKE AND ROUTING"
KEY_ARG = "participant-key"
PERSONA = "none (deterministic code; anthology-producer-orchestrator owns the run)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S0.
# A1 ORDER LAW: the FAIL-SOFT board mirror (mc_board.py) is wired BEFORE the holdable
# drive-tree-provision step. Drive provisioning legitimately HOLDS (exit 3, e.g. until
# GOOGLE_IMPERSONATE_USER is set) and short-circuits the runner; if the card mirror sat
# after it, a held Drive would suppress the participant's board card entirely (5 ledger
# rows, 0 cards). Mirroring first -- and never propagating the mirror's exit code --
# guarantees the producer's Gate Panel always has a card, even while S0 holds at Drive.
WIRING = [
    ("scripts/intake_router.py", "deterministic S0: route-secret check, hidden-field validation, tenant check, dedup no-op, exceptions capture, under-2-second acknowledge, detached stage spawn"),
    ("scripts/anthology_state.py", "upsert-participant on the composite key contact_id::anthology_id, or confirm the cursor"),
    ("scripts/mc_board.py", "ingest ONE participant card to POST /api/tasks/ingest (HMAC + Bearer, fail-soft: a dark board never blocks the pipeline) -- mirrored BEFORE the holdable Drive step so a held/dark Drive never suppresses the card"),
    ("scripts/drive-tree-provision.py", "idempotent Producer/Anthology/Participant tree under the per-client BlackCEO-hosted Shared-Drive root (resolved per box from GOOGLE_DRIVE_ROOT_FOLDER), on first sight only"),
]


KEY_DELIM = "::"


def _run_dir_for(key, run_dir=None):
    """Resolve (and create) this run's per-participant-per-stage working directory
    -- the SAME directory 54-anthology-writer/anthology-entry.sh --run-dir targets,
    so its working/*.md checkpoints are exactly what a later stage reads back."""
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


def _spawn_next(py, next_script, key, run_dir):
    """Fire-and-forget the next stage, fully detached (mirrors intake_router.py's
    own spawn_stage_detached; never blocks this stage's own exit)."""
    target = SCRIPTS / next_script
    if not target.exists():
        sys.stderr.write("[stage_%s] next stage %s not present yet; the ledger cursor "
                         "holds it safely until it lands.\n" % (STAGE, next_script))
        return False
    argv = [py, str(target), "--participant-key", key, "--run-dir", str(run_dir)]
    logpath = Path(run_dir) / "stage-spawn.log"
    try:
        logf = open(logpath, "ab")
    except OSError:
        logf = subprocess.DEVNULL
    try:
        subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=logf, stderr=logf,
                         start_new_session=True, close_fds=True, cwd=str(SKILL_DIR))
        return True
    except Exception as exc:  # noqa: BLE001 - a spawn failure must not fail this stage
        sys.stderr.write("[stage_%s] next-stage spawn failed (non-fatal; the ledger "
                         "cursor holds it): %s\n" % (STAGE, exc))
        return False
    finally:
        if logf not in (subprocess.DEVNULL,):
            try:
                logf.close()
            except OSError:
                pass


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
    `key` is either a --participant-key (exceptions-replay) or a --payload file
    (the normal S0 path). classify_child_rc's numeric contract is unchanged; every
    step short-circuits the stage on anything but EX_OK."""
    pending = [rel for rel, _ in WIRING if _resolve(rel) is None]
    if pending:
        sys.stderr.write("[stage_%s] PENDING-WIRING: collaborator(s) not yet present: %s\n"
                         % (STAGE, ", ".join(pending)))
        sys.stderr.write("[stage_%s] held; the durable ledger keeps the cursor at zero cost.\n" % STAGE)
        return EX_HELD

    py = sys.executable or "python3"
    payload_file = key if (key and Path(key).is_file()) else None
    replay_key = None if payload_file else key

    # 1. intake_router.py -- the deterministic S0 route (route-secret, hidden-field
    #    validation, tenant check, dedup no-op, exceptions capture, the sole-writer
    #    upsert-participant, acknowledge). --no-spawn: THIS dispatcher (not
    #    intake_router) drives the rest of the WIRING chain below. intake_router.py
    #    has no bare-participant-key CLI surface (--replay re-submits the SAME
    #    --payload to reset its dedup claim); an exceptions-queue/manual replay by
    #    --participant-key alone means the participant already routed and this
    #    step has nothing to re-route -- it is a documented no-op in that path.
    rel, _ = WIRING[0]
    pkey = replay_key
    if payload_file:
        argv = [py, str(_resolve(rel)), "--no-spawn", "--json", "--payload", payload_file]
        rc, parsed = _step(0, rel, argv)
        if rc != EX_OK:
            return rc
        pkey = (parsed or {}).get("participant_key") or pkey
    else:
        sys.stderr.write("[stage_%s] 1/%d %s: skipped (no --payload; replaying an "
                         "already-routed --participant-key)\n" % (STAGE, len(WIRING), rel))
    if not pkey or KEY_DELIM not in pkey:
        sys.stderr.write("[stage_%s] no resolvable participant_key; held.\n" % STAGE)
        return EX_HELD
    contact_id, anthology_id = pkey.split(KEY_DELIM, 1)
    rundir = _run_dir_for(pkey, run_dir)

    # 2. anthology_state.py -- confirm the cursor. intake_router already performed
    #    the substantive upsert in step 1; this is an idempotent no-op confirm
    #    read via the sole writer's own upsert-participant contract.
    rel, _ = WIRING[1]
    argv = [py, str(_resolve(rel)), "--json", "upsert-participant",
            "--contact-id", contact_id, "--anthology-id", anthology_id]
    rc, _ = _step(1, rel, argv)
    if rc != EX_OK:
        return rc

    # 3. mc_board.py -- ingest ONE participant card (idempotent create/resolve).
    #    CARD-BEFORE-DRIVE (A1): mirrored BEFORE the holdable Drive step, and FULLY
    #    FAIL-SOFT -- the mirror's exit code is NEVER propagated into the stage
    #    short-circuit. mc_board is fail-soft by construction (every board outcome is
    #    exit 0); this guard additionally absorbs a mc_board wiring refusal (exit 2)
    #    or an unexpected error so the documented "a dark board never blocks the
    #    pipeline" contract holds at THIS call site too. The result: the producer's
    #    Gate Panel always has a card, even while S0 legitimately holds at Drive.
    rel, _ = WIRING[2]
    argv = [py, str(_resolve(rel)), "ensure", "--subject-key", pkey, "--json"]
    rc_board, _ = _step(2, rel, argv)
    if rc_board != EX_OK:
        sys.stderr.write("[stage_%s] board mirror non-OK (rc=%d); FAIL-SOFT, the card "
                         "reconciles on the daily tick; continuing (a dark board never "
                         "blocks the pipeline).\n" % (STAGE, rc_board))

    # helper read (not a separate WIRING slot): resolve the anthology's producer_id
    # so the Drive tree below carries a real level-1 folder identity.
    producer_id = anthology_id
    _, anth_parsed, _ = _run([py, str(_resolve(WIRING[1][0])), "--json",
                             "get-anthology", "--anthology-id", anthology_id])
    if anth_parsed and anth_parsed.get("producer_id"):
        producer_id = anth_parsed["producer_id"]

    # 4. drive-tree-provision.py -- idempotent Producer/Anthology/Participant tree,
    #    on first sight only (get-or-create is a no-op on a re-run). This is a HARD
    #    dependency (the tree must exist before authoring), so it DOES short-circuit;
    #    because the card was already mirrored above, a Drive hold leaves a visible
    #    review/blocked card on the board rather than an invisible participant.
    rel, _ = WIRING[3]
    argv = [py, str(_resolve(rel)), "provision", "--producer", producer_id,
            "--anthology", anthology_id, "--participant", contact_id, "--json"]
    rc, _ = _step(3, rel, argv)
    if rc != EX_OK:
        return rc

    # Housekeeping (SPEC 2.2 execution model: advance exactly one stage, persist,
    # stop): S0 is complete, so advance into S1 and hand off. The intake_router.py
    # module docstring names this exact hand-off ("the S0 stage runner ... runs
    # drive-tree-provision.py + mc_board.py and advances into S1").
    rel_state, _ = WIRING[1]
    argv = [py, str(_resolve(rel_state)), "--json", "advance-stage",
            "--participant-key", pkey, "--to", "s1_avatar"]
    rc_adv, _, err_adv = _run(argv)
    adv_class = classify_child_rc(rc_adv)
    if adv_class != EX_OK:
        sys.stderr.write("[stage_%s] advance-stage to s1_avatar failed (rc=%d): %s\n"
                         % (STAGE, rc_adv, err_adv[-300:] if err_adv else ""))
        return adv_class

    _spawn_next(py, "stage_s1_avatar.py", pkey, rundir)
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
    # A1 ORDER LAW: the fail-soft board mirror MUST be wired BEFORE the holdable
    # drive-tree-provision step, so a held/dark Drive can never suppress the card.
    _rels = [rel for rel, _ in WIRING]
    assert "scripts/mc_board.py" in _rels and "scripts/drive-tree-provision.py" in _rels, \
        "S0 must wire both the board mirror and drive-tree-provision"
    assert _rels.index("scripts/mc_board.py") < _rels.index("scripts/drive-tree-provision.py"), \
        "A1: mc_board.py (fail-soft card mirror) MUST precede drive-tree-provision.py (holdable)"
    print("stage_%s self-test: OK (exit-code map + wiring contract coherent; "
          "board mirror precedes the holdable Drive step)" % STAGE)
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="thin dispatcher for stage %s (%s)" % (STAGE, STAGE_NAME))
    ap.add_argument("--%s" % KEY_ARG, dest="key", help="the %s to dispatch (exceptions-replay)" % KEY_ARG)
    ap.add_argument("--payload", help="raw intake payload file (normal S0 path via intake_router.py)")
    ap.add_argument("--run-dir", help="optional per-participant-per-stage run directory")
    ap.add_argument("--plan", action="store_true", help="print the wiring contract and exit")
    ap.add_argument("--self-test", action="store_true", help="verify the runner contract and exit")
    args = ap.parse_args(argv)
    try:
        if args.self_test:
            return self_test()
        if args.plan:
            return plan()
        if not args.key and not args.payload:
            ap.error("stage %s needs --%s (replay) or --payload (normal intake)" % (STAGE, KEY_ARG))
        return _invoke_wiring(args.key or args.payload, args.run_dir)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[stage_%s] unexpected error: %s\n" % (STAGE, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())

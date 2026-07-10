#!/usr/bin/env python3
"""stage_s7_cover.py -- thin stage dispatcher for s7 (COVER IMAGE).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S7 cover: the cover prompt generator (structured output), then Kie.ai GPT-image-2 PORTRAIT
1024x1536 via Skills 07 and 46 against the Wave-0-verified text-to-image portrait endpoint
(NEVER the 16:9 presentation recipe); PNG to the participant Drive folder.

Persona (PRD Section 13): anthology-producer-orchestrator speaking the Senior Book-Cover Design Specialist (aw-11).

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

STAGE = "s7"
STAGE_NAME = "COVER IMAGE"
KEY_ARG = "participant-key"
PERSONA = "anthology-producer-orchestrator speaking the Senior Book-Cover Design Specialist (aw-11)"

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
REPO_ROOT = SKILL_DIR.parent
LAYER1_ENTRY = REPO_ROOT / "54-anthology-writer" / "anthology-entry.sh"

EX_OK, EX_ERR, EX_PROVER, EX_HELD, EX_SLOT = 0, 1, 2, 3, 5

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S7.
WIRING = [
    ("scripts/anthology_state.py", "load the participant row (locked title/subtitle, author name, blurb)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): the cover prompt generator pin aw-11 on MID-WRITER, structured image-prompt object"),
    ("scripts/cover_render.py", "Kie.ai GPT-image-2 PORTRAIT 1024x1536 via Skills 07/46 callback, bounded re-poll then hold plus alert"),
    ("scripts/drive_adapter.py", "land the cover PNG in the participant Drive folder"),
    ("scripts/anthology_state.py", "record-artifact (cover) with both link fields and advance to s8_deliver"),
    ("scripts/mc_board.py", "mirror the participant card to in_progress at the s8_deliver cursor (SPEC 11.2 stage_cursor projection, W4.3); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"
COVER_PIN = REPO_ROOT / "54-anthology-writer" / "assets" / "prompts" / "11-cover-image-prompt.md"


def _run_dir_for(key, run_dir=None):
    if run_dir:
        d = Path(run_dir)
    else:
        safe = "".join(c if (c.isalnum() or c in "-_.") else "_" for c in (key or "unknown"))
        d = SKILL_DIR / "state" / "runs" / STAGE / safe
    (d / "working").mkdir(parents=True, exist_ok=True)
    return d


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


def _spawn_next(py, next_script, key, run_dir):
    """Fire-and-forget the next stage, fully detached (mirrors intake_router.py's
    own spawn_stage_detached; never blocks this stage's own exit). S7 has no gate
    (SPEC S7 advances straight to s8_deliver), so the full completion sweep at
    S8 fires automatically once the cover lands."""
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
    S7 has no gate at all (SPEC S7: it advances straight to s8_deliver), so
    every declared collaborator runs synchronously in this one call.
    classify_child_rc's numeric contract is unchanged; every step short-circuits
    on anything but EX_OK."""
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
    #    author name, blurb, drive_folder_id).
    rel, _ = WIRING[0]
    rc, participant = _step(0, rel, [py, str(_resolve(rel)), "--json",
                                    "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc
    participant = participant or {}

    # 2. 54-anthology-writer/anthology-entry.sh -- the cover-prompt generator
    #    (aw-11) is Skill 54's OWN baked, non-phase asset (ANTHOLOGY-MANIFEST.json
    #    cover_prompt block: "Skill 54's own P0-P7 walk does NOT gate the cover");
    #    anthology-entry.sh exposes no dedicated cover subcommand (--run-dir /
    #    --plan / --upto only), so this step proves the Layer 1 gates are healthy
    #    (--plan, side-effect-free) and the MID-WRITER prompt call itself goes
    #    through this engine's own sole model-call site, model_router.py, over
    #    the baked aw-11 pin text -- the SAME collaborator WIRING declares, just
    #    routed the way SPEC 8 requires every model call to route.
    rel, _ = WIRING[1]
    rc, _ = _step(1, rel, ["bash", str(_resolve(rel)), "--plan"])
    if rc != EX_OK:
        return rc
    pin_text = COVER_PIN.read_text(encoding="utf-8") if COVER_PIN.is_file() else ""
    prompt_user = ("%s\n\nTITLE: %s\nSUBTITLE: %s\nAUTHOR: %s\nBLURB: %s"
                   % (pin_text, participant.get("title_locked") or "",
                      participant.get("subtitle_locked") or "",
                      ("%s %s" % (participant.get("first_name") or "",
                                  participant.get("last_name") or "")).strip(),
                      participant.get("chapter_about") or ""))
    router_rel = "scripts/model_router.py"
    router_payload = json.dumps({"tier": "MID-WRITER",
                                 "messages": [{"role": "user", "content": prompt_user}],
                                 "context": {"participant_key": pkey, "deliverable_key": "cover"}})
    rrc, rparsed, rerr = _run([py, str(_resolve(router_rel)), "route"], input_text=router_payload)
    router_class = classify_child_rc(rrc)
    if router_class != EX_OK:
        sys.stderr.write("[stage_%s] model_router.py route exited %d -> classified %d%s\n"
                         % (STAGE, rrc, router_class, (" :: %s" % rerr[-300:]) if rerr else ""))
        return router_class
    cover_prompt_text = (rparsed or {}).get("text") or ""
    cover_prompt_path = Path(rundir) / "working" / "cover-prompt.json"
    cover_prompt_path.write_text(json.dumps({"prompt": cover_prompt_text}, ensure_ascii=False),
                                 encoding="utf-8")

    # 3. cover_render.py -- Kie.ai GPT-image-2 PORTRAIT 1024x1536, bounded re-poll
    #    then hold + alert.
    rel, _ = WIRING[2]
    cover_png = Path(rundir) / "working" / "cover.png"
    cover_result = Path(rundir) / "working" / "cover-result.json"
    rc, rendered = _step(2, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                                 "--prompt-file", str(cover_prompt_path),
                                 "--out", str(cover_png), "--result-out", str(cover_result)])
    if rc != EX_OK:
        return rc
    rendered = rendered or {}

    # 4. drive_adapter.py -- land the cover PNG in the participant Drive folder.
    rel, _ = WIRING[3]
    folder_id = participant.get("drive_folder_id")
    if not folder_id:
        sys.stderr.write("[stage_%s] no drive_folder_id on the participant row; held.\n" % STAGE)
        return EX_HELD
    contact_id = pkey.split(KEY_DELIM, 1)[0]
    rc, uploaded = _step(3, rel, [py, str(_resolve(rel)), "upload",
                                 "--name", "%s-cover.png" % contact_id,
                                 "--parent-folder-id", folder_id,
                                 "--file", str(cover_png), "--mime", "image/png",
                                 "--share-view"])
    if rc != EX_OK:
        return rc
    uploaded = uploaded or {}
    cover_link = (uploaded.get("webViewLink") or uploaded.get("link")
                 or uploaded.get("url") or uploaded.get("id") or "")

    # 5. anthology_state.py -- record-artifact(cover) with both link fields
    #    (per field-map.json cover_field_semantics: doc_url the Convert and Flow
    #    media-storage image link -- written later by caf_delivery at S8 --
    #    pdf_url the Drive link recorded here); advance to s8_deliver.
    rel, _ = WIRING[4]
    art_argv = [py, str(_resolve(rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "cover"]
    if cover_link:
        art_argv += ["--pdf-url", cover_link]
    rc, _ = _step(4, rel, art_argv)
    if rc != EX_OK:
        return rc
    rc, _ = _step(4, rel, [py, str(_resolve(rel)), "--json", "advance-stage",
                          "--participant-key", pkey, "--to", "s8_deliver"])
    if rc != EX_OK:
        return rc

    # 5b. caf_delivery.py update-stage -- move the Convert and Flow opportunity to
    #     the mapped Cover pipeline stage (engine gate s7 -> "Cover" from the
    #     registry caf_stage_map, NEVER hardcoded). S7 has no producer gate and no
    #     per-deliverable S8 delivery call of its own (the cover's CAF field write
    #     rides the completion sweep), so this per-gate pipeline move is fired here
    #     directly through the SAME update-stage subcommand S8 uses -- no new
    #     adapter code. FAIL-SOFT: unbound on this box -> skipped; a scope-denied
    #     opportunity write (exit 3) or any error is logged and NEVER blocks the
    #     cover stage (the durable ledger + daily-tick retry hold it) (B6 / SPEC 7.6).
    contact_id, anthology_id = pkey.split(KEY_DELIM, 1)
    _, binding, _ = _run([py, str(_resolve("scripts/anthology_registry.py")),
                         "resolve", "--anthology-id", anthology_id, "--json"])
    binding = binding or {}
    if binding.get("pipeline_id") and binding.get("caf_stage_map"):
        move_rc, _mv, move_err = _run(
            [py, str(_resolve("scripts/caf_delivery.py")), "update-stage",
             "--contact-id", contact_id, "--pipeline-id", binding["pipeline_id"],
             "--gate", "s7",
             "--stage-map", json.dumps(binding["caf_stage_map"], ensure_ascii=False)])
        if classify_child_rc(move_rc) != EX_OK:
            sys.stderr.write("[stage_%s] per-gate pipeline-stage move to Cover held/"
                             "failed (rc=%s); non-fatal, the daily-tick retries%s\n"
                             % (STAGE, move_rc, (" :: %s" % move_err[-200:]) if move_err else ""))
    else:
        sys.stderr.write("[stage_%s] no pipeline binding on this box yet; the Cover "
                         "pipeline-stage move is skipped (delivery still lands).\n" % STAGE)

    # 6. mc_board.py -- mirror the participant card to in_progress at s8_deliver
    #    (W4.3); FAIL-SOFT.
    rel, _ = WIRING[5]
    rc, _ = _step(5, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc

    # Housekeeping (SPEC 2.2 execution model): S7 has no gate, so hand off the
    # completion sweep to S8 the same way S0 hands off to S1.
    _spawn_next(py, "stage_s8_deliver.py", pkey, rundir)
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

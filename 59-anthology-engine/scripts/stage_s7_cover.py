#!/usr/bin/env python3
"""stage_s7_cover.py -- thin stage dispatcher for s7 (COVER IMAGE).

WIRING CONTRACT (authored by W1.1; module logic authored by sibling units).
This is a THIN RUNNER: it validates inputs, resolves the ordered collaborators
below, and hands off. It implements NO module logic. The serial integrator wires
the concrete argv per collaborator into _invoke_wiring(); the resolution order and
the exit-code classification contract are FIXED here.

S7 cover (U8 / B8): the cover prompt generator (one structured BASE prompt), then FOUR
distinctly-styled portrait covers -- the config-pinned named styles in cover_render.COVER_STYLES
(exactly one strictly typography-driven) rendered on the SAME Kie.ai GPT-image-2 PORTRAIT
1024x1536 text-to-image endpoint (NEVER the 16:9 presentation recipe). Each style PNG is landed
in the participant Drive folder AND uploaded to Convert and Flow media storage; the four
anthology_cover_sample{1..4}_url fields are written (read-back). S7 then HOLDS: the producer
approves the SET (no down-select) and the client picks ONE style in the universal-review cover
dropdown. The producer's set-approval is the board-door s7_producer RELEASE gate -- a committed
producer approve fires the anthology-release-cover tag through the gate-engine release bus
(GATE_BY_CURSOR cursor s7_cover, release-only) while the cursor genuinely HOLDS at s7_cover for
the client pick; --apply-pick then advances to S8. The pick (--apply-pick --choice <style>) copies the chosen style's art into the
EXISTING cover image/drive fields and advances to S8 exactly as the single cover did before.

Two phases (both idempotent):
  * default (--participant-key)        -> render the SET, upload x4, write the 4 sample fields, HOLD
  * --apply-pick --choice <name|key>   -> stamp the chosen art into the cover fields, advance to S8

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

# Ordered collaborators: (path relative to skill or repo root, role). Per SPEC S7 + U8.
WIRING = [
    ("scripts/anthology_state.py", "load the participant row (locked title/subtitle, author name, blurb, drive folder)"),
    ("54-anthology-writer/anthology-entry.sh", "Layer 1 authoring core (Skill 54): the cover prompt generator pin aw-11 on MID-WRITER, one structured BASE image-prompt"),
    ("scripts/cover_render.py", "render the FOUR named cover styles (>=1 strictly typography-driven) on the SAME Kie.ai GPT-image-2 PORTRAIT endpoint; bounded re-poll then hold plus alert"),
    ("scripts/drive_adapter.py", "land each of the four style PNGs in the participant Drive folder"),
    ("scripts/caf_delivery.py", "upload each style PNG to Convert and Flow media storage; write the four anthology_cover_sample{1..4}_url fields (read-back); on the client pick, stamp the chosen art into the existing cover image/drive fields"),
    ("scripts/anthology_state.py", "on the client pick: record-artifact (cover) with both link fields and advance to s8_deliver"),
    ("scripts/mc_board.py", "mirror the participant card (cover SET ready for producer approval; then the s8_deliver cursor after the pick); FAIL-SOFT, never blocks the pipeline"),
]


KEY_DELIM = "::"
COVER_PIN = REPO_ROOT / "54-anthology-writer" / "assets" / "prompts" / "11-cover-image-prompt.md"
FIELD_MAP_PATH = SKILL_DIR / "config" / "field-map.json"
PICK_MANIFEST_CONTRACT = "anthology-engine-cover-pick-manifest"
COVER_SET_FILENAME = "cover-set.json"        # the Phase-A pick manifest (run-dir persisted)

# Sibling import (same convention caf_delivery.py / anthology_registry.py use): the
# four named cover styles + their prompt directives are config-pinned in cover_render.
sys.path.insert(0, str(SCRIPTS))
import cover_render  # noqa: E402  (sibling import after the path bootstrap above)


# --------------------------------------------------------------------------- #
# U8 pure helpers (network-free; self-tested). The FIELD KEYS live in field-map's
# cover_style_fields; the STYLE definitions (names/slots/directives) live in
# cover_render.COVER_STYLES. resolve_pick maps a client dropdown value to its
# rendered art in the Phase-A set manifest.
# --------------------------------------------------------------------------- #
def _load_cover_style_fields(field_map_path=FIELD_MAP_PATH):
    """Read config/field-map.json cover_style_fields; raise if absent/incomplete so a
    misprovisioned box HOLDS rather than silently mis-writing a cover field."""
    fm = json.loads(Path(field_map_path).read_text(encoding="utf-8"))
    csf = fm.get("cover_style_fields")
    tcf = (csf or {}).get("target_cover_fields") or {}
    if (not isinstance(csf, dict) or not csf.get("sample_url_fields")
            or not csf.get("choice_field") or not tcf.get("image") or not tcf.get("drive")):
        raise ValueError("field-map.json cover_style_fields is absent or incomplete (U8 provisioning missing)")
    return csf


def _sample_field_for_slot(csf, slot):
    key = (csf.get("sample_url_fields") or {}).get(str(slot))
    if not key:
        raise ValueError("no sample_url_field for slot %r in field-map cover_style_fields" % slot)
    return key


def build_pick_manifest(participant_key, render_set, links, csf):
    """Fold the cover_render set manifest (per-style out paths) + the uploaded links
    into the durable pick manifest S7 persists and Phase B reads. Pure."""
    styles = {}
    for e in (render_set.get("styles") or []):
        k = e["key"]
        lk = links.get(k) or {}
        styles[k] = {
            "name": e["name"], "slot": e.get("slot"),
            "sample_field": _sample_field_for_slot(csf, e["slot"]),
            "media_url": lk.get("media_url") or "",
            "drive_url": lk.get("drive_url") or "",
            "png": e.get("out_png"), "status": e.get("status"),
        }
    return {
        "contract": PICK_MANIFEST_CONTRACT, "schema_version": 1,
        "participant_key": participant_key,
        "choice_field": csf["choice_field"],
        "choice_options": list(cover_render.STYLE_NAMES),
        "target_cover_fields": dict(csf["target_cover_fields"]),
        "styles": styles,
    }


def resolve_pick(choice, pick_manifest, styles=None):
    """Map a client choice (a style NAME or KEY, case-insensitive) to its rendered
    entry. Returns (canonical_style_dict, style_entry). Raises ValueError on an
    empty/unknown choice or a chosen style whose art did not land."""
    styles = styles or cover_render.COVER_STYLES
    if not choice or not str(choice).strip():
        raise ValueError("empty cover choice")
    sel = str(choice).strip().lower()
    match = None
    for st in styles:
        if st["key"].lower() == sel or st["name"].lower() == sel:
            match = st
            break
    if not match:
        raise ValueError("choice %r matches none of the four named styles (%s)"
                         % (choice, ", ".join(s["name"] for s in styles)))
    entry = (pick_manifest.get("styles") or {}).get(match["key"])
    if not entry:
        raise ValueError("no rendered sample for chosen style %r in the set manifest" % match["name"])
    if not entry.get("media_url") and not entry.get("drive_url"):
        raise ValueError("chosen style %r has no landed art (media/drive url absent)" % match["name"])
    return match, entry


def _first_link(uploaded):
    """The hosted link from a drive_adapter upload result (webViewLink|link|url|id)."""
    u = uploaded or {}
    return u.get("webViewLink") or u.get("link") or u.get("url") or u.get("id") or ""


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


def _guard(key):
    """Shared preamble for both phases: every declared collaborator must resolve and
    the key must be a composite. Returns an exit code to short-circuit on, or None."""
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
    return None


def _invoke_wiring(key, run_dir=None):
    """PHASE A (render the SET). Renders the FOUR config-pinned named cover styles
    (>=1 strictly typography-driven) on the SAME Kie.ai GPT-image-2 portrait
    endpoint, lands each in Drive + Convert and Flow media storage, writes the four
    anthology_cover_sample{1..4}_url fields with byte-for-byte read-back, persists
    the durable pick manifest, and syncs the board. It then HOLDS at s7_cover for the
    producer set-approval + client pick -- it deliberately does NOT advance to s8 or
    spawn the next stage; the client pick (--apply-pick) does that. Every step
    short-circuits on anything but EX_OK (fixed classify_child_rc contract)."""
    g = _guard(key)
    if g is not None:
        return g
    pkey = key
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)
    working = Path(rundir) / "working"
    working.mkdir(parents=True, exist_ok=True)
    contact_id = pkey.split(KEY_DELIM, 1)[0]

    try:
        csf = _load_cover_style_fields()
    except (ValueError, OSError) as exc:
        sys.stderr.write("[stage_%s] cover-style field map unavailable: %s -> held.\n" % (STAGE, exc))
        return EX_HELD

    # 1. anthology_state.py -- load the participant row (locked title/subtitle,
    #    author name, blurb, drive_folder_id).
    rel, _ = WIRING[0]
    rc, participant = _step(0, rel, [py, str(_resolve(rel)), "--json",
                                    "get-participant", "--participant-key", pkey])
    if rc != EX_OK:
        return rc
    participant = participant or {}
    folder_id = participant.get("drive_folder_id")
    if not folder_id:
        sys.stderr.write("[stage_%s] no drive_folder_id on the participant row; held.\n" % STAGE)
        return EX_HELD

    # 2. 54-anthology-writer/anthology-entry.sh -- prove the Layer 1 gates are healthy
    #    (--plan, side-effect-free), then author the ONE aw-11 BASE cover prompt via
    #    this engine's sole model-call site, model_router.py (MID-WRITER). cover_render
    #    specializes that base prompt into each named style downstream.
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
    cover_prompt_path = working / "cover-prompt.json"
    cover_prompt_path.write_text(json.dumps({"prompt": cover_prompt_text}, ensure_ascii=False),
                                 encoding="utf-8")

    # 3. cover_render.py --style-set -- render the FOUR named styles (one PNG each),
    #    all portrait 2:3, bounded re-poll then hold + alert (overall HELD if any
    #    style could not land).
    rel, _ = WIRING[2]
    covers_dir = working / "covers"
    render_set_out = working / "cover-render-set.json"
    rc, _ = _step(2, rel, [py, str(_resolve(rel)), "--participant-key", pkey,
                          "--prompt-file", str(cover_prompt_path), "--style-set",
                          "--out-dir", str(covers_dir), "--result-out", str(render_set_out)])
    if rc != EX_OK:
        return rc
    try:
        render_set = json.loads(render_set_out.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write("[stage_%s] cover-set render manifest unreadable: %s -> held.\n" % (STAGE, exc))
        return EX_HELD
    entries = render_set.get("styles") or []
    if len(entries) != len(cover_render.COVER_STYLES):
        sys.stderr.write("[stage_%s] expected %d styled covers, got %d -> held.\n"
                         % (STAGE, len(cover_render.COVER_STYLES), len(entries)))
        return EX_HELD

    # 4 + 5. per style: land the PNG in Drive AND in Convert and Flow media storage.
    drive_rel, _ = WIRING[3]
    caf_rel, _ = WIRING[4]
    links = {}
    for e in entries:
        skey = e["key"]
        png = e.get("out_png")
        name = "%s-cover-%s.png" % (contact_id, skey)
        rc, uploaded = _step(3, drive_rel, [py, str(_resolve(drive_rel)), "upload",
                            "--name", name, "--parent-folder-id", folder_id,
                            "--file", png, "--mime", "image/png", "--share-view"])
        if rc != EX_OK:
            return rc
        drive_url = _first_link(uploaded)
        rc, media = _step(4, caf_rel, [py, str(_resolve(caf_rel)), "upload",
                                      "--file", png, "--name", name])
        if rc != EX_OK:
            return rc
        media_url = (media or {}).get("url") or ""
        links[skey] = {"media_url": media_url, "drive_url": drive_url}

    # 6. write the FOUR sample-url fields (the displayable media links) in ONE
    #    caf_delivery write-fields call -> single PUT + one byte-for-byte read-back.
    field_args = []
    for e in entries:
        field_args += ["--field", "%s=%s" % (_sample_field_for_slot(csf, e["slot"]),
                                             links[e["key"]]["media_url"])]
    rc, _ = _step(4, caf_rel, [py, str(_resolve(caf_rel)), "--field-map", str(FIELD_MAP_PATH),
                              "write-fields", "--contact-id", contact_id] + field_args)
    if rc != EX_OK:
        return rc

    # 7. persist the durable pick manifest (Phase B reads it to stamp the pick).
    pick_manifest = build_pick_manifest(pkey, render_set, links, csf)
    (working / COVER_SET_FILENAME).write_text(json.dumps(pick_manifest, indent=2), encoding="utf-8")

    # 8. mc_board.py -- mirror the participant card (the cover SET is ready for the
    #    producer to approve and send); FAIL-SOFT.
    rel, _ = WIRING[6]
    rc, _ = _step(6, rel, [py, str(_resolve(rel)), "sync", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc

    # HOLD at s7_cover: the producer approves the SET (no down-select) and the client
    # picks ONE style in the universal-review cover dropdown; --apply-pick advances S8.
    sys.stderr.write("[stage_%s] cover SET staged (4 styles rendered + uploaded to Drive/media + "
                     "sample fields written). HOLDING at s7_cover for producer set-approval + client "
                     "pick (re-invoke: stage_s7_cover.py --apply-pick --participant-key %s --choice <style>).\n"
                     % (STAGE, pkey))
    return EX_OK


def _invoke_apply_pick(key, choice, run_dir=None):
    """PHASE B (the client pick). Reads the Phase-A pick manifest, resolves the
    client's chosen style (a NAME or KEY from the universal-review dropdown), stamps
    its media + Drive links into the EXISTING cover image/drive fields (byte-for-byte
    read-back) plus the choice field, records the CHOSEN cover artifact with both link
    fields, advances s7_cover -> s8_deliver, and hands off the completion sweep to S8
    exactly as the single cover did. Idempotent: re-applying the same pick re-stamps
    the same values."""
    g = _guard(key)
    if g is not None:
        return g
    pkey = key
    py = sys.executable or "python3"
    rundir = _run_dir_for(pkey, run_dir)
    working = Path(rundir) / "working"
    contact_id = pkey.split(KEY_DELIM, 1)[0]

    # NOTE (U7 view-only cover, Trevor's LOCKED #4): the cover is a PNG IMAGE, not a
    # deliverable Google Doc. EDIT-share applies "for deliverable Docs" only; there is
    # nothing to pull back from an image and the co-author only picks a favorite, so
    # every rendered cover PNG stays anyone-with-link VIEW-only. That view-only upload
    # already happened in Phase A (_invoke_wiring uses drive_adapter upload --share-view);
    # Phase B only stamps the CHOSEN art's already-landed links (no re-upload).
    setp = working / COVER_SET_FILENAME
    if not setp.exists():
        sys.stderr.write("[stage_%s] no cover set manifest at %s; run the render-set phase first. Held.\n"
                         % (STAGE, setp))
        return EX_HELD
    try:
        pick_manifest = json.loads(setp.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        sys.stderr.write("[stage_%s] cover set manifest unreadable: %s -> held.\n" % (STAGE, exc))
        return EX_HELD
    try:
        match, entry = resolve_pick(choice, pick_manifest)
    except ValueError as exc:
        sys.stderr.write("[stage_%s] cover pick could not be resolved: %s. Held for a valid pick.\n"
                         % (STAGE, exc))
        return EX_HELD

    image_key = pick_manifest["target_cover_fields"]["image"]
    drive_key = pick_manifest["target_cover_fields"]["drive"]
    choice_field = pick_manifest["choice_field"]
    media_url = entry.get("media_url") or ""
    drive_url = entry.get("drive_url") or ""

    # 1. caf_delivery.py -- stamp the chosen art into the EXISTING cover fields and
    #    record the pick in the choice field (one PUT, byte-for-byte read-back).
    caf_rel, _ = WIRING[4]
    field_args = []
    if media_url:
        field_args += ["--field", "%s=%s" % (image_key, media_url)]
    if drive_url:
        field_args += ["--field", "%s=%s" % (drive_key, drive_url)]
    field_args += ["--field", "%s=%s" % (choice_field, match["name"])]
    rc, _ = _step(4, caf_rel, [py, str(_resolve(caf_rel)), "--field-map", str(FIELD_MAP_PATH),
                              "write-fields", "--contact-id", contact_id] + field_args)
    if rc != EX_OK:
        return rc

    # 2. anthology_state.py -- record-artifact(cover) with BOTH link fields (the
    #    CHOSEN art: doc_url/caf_media_url the media link, pdf_url the Drive link).
    state_rel, _ = WIRING[5]
    art_argv = [py, str(_resolve(state_rel)), "--json", "record-artifact",
               "--participant-key", pkey, "--type", "cover"]
    if media_url:
        art_argv += ["--doc-url", media_url, "--caf-media-url", media_url]
    if drive_url:
        art_argv += ["--pdf-url", drive_url]
    rc, _ = _step(5, state_rel, art_argv)
    if rc != EX_OK:
        return rc

    # 3. caf_delivery.py update-stage -- move the Convert and Flow opportunity to
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

    # 4. advance s7_cover -> s8_deliver.
    rc, _ = _step(5, state_rel, [py, str(_resolve(state_rel)), "--json", "advance-stage",
                                "--participant-key", pkey, "--to", "s8_deliver"])
    if rc != EX_OK:
        return rc

    # 5. mc_board.py -- mirror to the s8_deliver cursor; FAIL-SOFT.
    mc_rel, _ = WIRING[6]
    rc, _ = _step(6, mc_rel, [py, str(_resolve(mc_rel)), "sync", "--subject-key", pkey, "--json"])
    if rc != EX_OK:
        return rc

    # 6. hand off the completion sweep to S8 (as the single cover did at S0->S1).
    _spawn_next(py, "stage_s8_deliver.py", pkey, rundir)
    sys.stderr.write("[stage_%s] cover pick '%s' applied; chosen art stamped into the cover fields; "
                     "advanced to s8_deliver.\n" % (STAGE, match["name"]))
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
    # the WIRING order the phase code indexes into is fixed
    assert WIRING[2][0] == "scripts/cover_render.py"
    assert WIRING[3][0] == "scripts/drive_adapter.py"
    assert WIRING[4][0] == "scripts/caf_delivery.py"
    assert WIRING[6][0] == "scripts/mc_board.py"

    # --- U8: the four named styles come from cover_render; field-map carries keys --
    csf = _load_cover_style_fields()
    assert csf["choice_field"] == "contact.anthology_cover_choice"
    assert csf["target_cover_fields"]["image"] == "contact.anthology_cover_image_url"
    assert csf["target_cover_fields"]["drive"] == "contact.anthology_cover_drive_url"
    assert _sample_field_for_slot(csf, 1) == "contact.anthology_cover_sample1_url"
    assert _sample_field_for_slot(csf, "4") == "contact.anthology_cover_sample4_url"
    try:
        _sample_field_for_slot(csf, 9)
        assert False, "an out-of-range slot must raise"
    except ValueError:
        pass

    # build a pick manifest from a fake render-set + links, then resolve picks
    render_set = {"styles": [{"key": s["key"], "name": s["name"], "slot": s["slot"],
                              "out_png": "/x/cover-%s.png" % s["key"], "status": "rendered"}
                             for s in cover_render.COVER_STYLES]}
    links = {s["key"]: {"media_url": "https://media/%s" % s["key"],
                        "drive_url": "https://drive/%s" % s["key"]}
             for s in cover_render.COVER_STYLES}
    pm = build_pick_manifest("c1::a1", render_set, links, csf)
    assert len(pm["styles"]) == 4
    assert pm["choice_options"] == list(cover_render.STYLE_NAMES)
    assert pm["target_cover_fields"] == dict(csf["target_cover_fields"])
    for s in cover_render.COVER_STYLES:
        assert pm["styles"][s["key"]]["sample_field"] == _sample_field_for_slot(csf, s["slot"])

    # resolve by NAME and by KEY (case-insensitive)
    m, e = resolve_pick("Pure Type", pm)
    assert m["key"] == "pure_type" and e["media_url"] == "https://media/pure_type"
    m2, e2 = resolve_pick("bold_editorial", pm)
    assert m2["name"] == "Bold Editorial" and e2["drive_url"] == "https://drive/bold_editorial"
    m3, _ = resolve_pick("signature", pm)
    assert m3["typography_only"] is False
    # empty / unknown choice raises; a chosen style with no landed art raises
    for bad in ("", "   ", "Comic Sans", "watercolor"):
        try:
            resolve_pick(bad, pm)
            assert False, "bad choice %r must raise" % bad
        except ValueError:
            pass
    pm_missing = json.loads(json.dumps(pm))
    pm_missing["styles"]["fine_art"]["media_url"] = ""
    pm_missing["styles"]["fine_art"]["drive_url"] = ""
    try:
        resolve_pick("Fine Art", pm_missing)
        assert False, "a chosen style with no landed art must raise"
    except ValueError:
        pass

    print("stage_%s self-test: OK (exit-code map + wiring contract coherent; U8 style-field map, "
          "pick-manifest build, choice resolution by name/key, empty/unknown/no-art refusals)" % STAGE)
    return EX_OK


def main(argv=None):
    ap = argparse.ArgumentParser(description="thin dispatcher for stage %s (%s)" % (STAGE, STAGE_NAME))
    ap.add_argument("--%s" % KEY_ARG, dest="key", help="the %s to dispatch" % KEY_ARG)
    ap.add_argument("--run-dir", help="optional per-participant-per-stage run directory")
    ap.add_argument("--apply-pick", dest="apply_pick", action="store_true",
                    help="PHASE B: apply the client's cover pick (requires --choice) and advance to S8")
    ap.add_argument("--choice", help="the client's chosen cover style (a style NAME or KEY) for --apply-pick")
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
        if args.apply_pick:
            if not args.choice:
                ap.error("--apply-pick requires --choice <style name or key>")
            return _invoke_apply_pick(args.key, args.choice, args.run_dir)
        return _invoke_wiring(args.key, args.run_dir)
    except SystemExit:
        raise
    except Exception as exc:
        sys.stderr.write("[stage_%s] unexpected error: %s\n" % (STAGE, exc))
        return EX_ERR


if __name__ == "__main__":
    sys.exit(main())

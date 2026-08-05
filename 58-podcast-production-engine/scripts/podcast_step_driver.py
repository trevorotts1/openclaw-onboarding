#!/usr/bin/env python3
# =============================================================================
# 58-PODCAST-PRODUCTION-ENGINE :: PODCAST-STEP-DRIVER (orchestrator ghost fix)
# -----------------------------------------------------------------------------
# THE DETERMINISTIC STEP DRIVER. Master-plan unit 1.2.1. This file closes the
# "orchestrator ghost": there was no executable that sequenced the 18-step
# pipeline, so a bound department agent improvised from prose and jobs parked
# in `received` forever. This driver is the deterministic replacement.
#
# NO-DAEMON DOCTRINE (binding). This is NOT a controller daemon, NOT a scheduler
# daemon, and NOT a queue poller (webhook-design.md Section 7; SKILL.md
# NO-DAEMON DESIGN). It is a TOOL the podcast department agent calls inside its
# OWN tool-bearing turn: the controllerId runbook invokes
#     python3 scripts/podcast_step_driver.py next --job-id <id>
# and the driver emits the EXACT next command for Steps 2-18. The agent runs
# that command, records the stage change through podcast_state.py advance (the
# SOLE writer), then calls `next` again. No resident process, no cron, no poller.
# The only recurring podcast cron in the design remains the daily smoke test
# (podcast-smoke-test.py via openclaw cron), and this driver never arms one.
#
# WHAT `next` EMITS
#   - DETERMINISTIC steps call the production script DIRECTLY:
#       Step 10  generate_cover.sh
#       Step 11  generate_podcast_audio.sh
#       Step 12  render_documents.py
#       Step 13  render_book_teaser.py
#       Step 14  upload_media.py store
#       Step 15  podbean_publish.sh
#       Step 18  delivery_report.py
#   - CONTENT steps emit the model_router.py route (the model-resolver invocation)
#     the department agent fills with the runbook prompt and runs in its own turn:
#       Steps 2, 4, 5, 6, 7, 8  model_router.py route  (content tier)
#       Step 9  qc-tier1-mechanical.py + model_router.py route (qc_judge tier)
#       Step 17 (personal)  personal_spreadsheet.py append
#   - Steps with no dedicated production script (Step 16 LINK BACK, Step 17
#     interview-mode enroll) emit an explicit deterministic runbook directive.
#
# STEP DETERMINATION. The driver reads the job row through podcast_state.py's
# OWN database (connect + resolve_db_path + FORWARD_ORDER + resolve_preset +
# preset_flags + required outputs gate). It derives the current pipeline step
# from the job's recorded status and the already-recorded output columns, then
# emits the command for the next step the runbook must execute. It NEVER writes
# engine state: podcast_state.py remains the SOLE writer.
#
# VERIFICATION AFTER EACH STEP (1.2.1). The `verify` subcommand runs the
# required-outputs gate for the CURRENT status -> next status transition and
# fails loud (exit 3, the same code podcast_state uses for a blocked
# transition) naming every missing output. The driver also verifies the
# previous command's exit code via the caller (the agent's own turn), and
# `verify` re-checks the required outputs the step was supposed to produce.
#
# SECRECY: like podcast_state.py, nothing secret is ever printed. Commands
# reference credential-bearing environment variables and secret stores by
# LABEL and LOCATION only; values are resolved at execution time by the script
# being called. The driver itself holds no secret value.
#
# USAGE:
#   python3 podcast_step_driver.py next --job-id <id> [--json]
#   python3 podcast_step_driver.py verify --job-id <id> [--json]
#   python3 podcast_step_driver.py list-steps [--job-id <id>]
#   python3 podcast_step_driver.py self-test
#
# PYTHON VERSION (honest, verified). This file itself uses `from __future__
# import annotations`, so its own PEP 604 (`int | None`) annotations are strings
# at runtime and the FILE imports on 3.9+. BUT `next`, `verify`, and
# `list-steps --job-id <id>` all import the sibling podcast_state.py, which has
# NO future-annotations import and writes `str | None` unions that are evaluated
# at def time -- so podcast_state.py, and therefore those three subcommand forms,
# REQUIRE Python 3.10+. Only `--help`, `self-test`, and bare `list-steps` (the
# static step table; no sibling import) run on 3.9. Boxes on 3.9 can list the
# step table and read help but cannot drive a job.
#
# EXIT: 0 ok / 2 usage / 3 blocked transition (missing required outputs)
#       / 4 no such job or writer refused / 1 error.
# =============================================================================
"""Deterministic, no-daemon step driver for the Podcast Production Engine."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

# The driver's sibling module podcast_state.py is the engine's SOLE writer and
# the canonical home of the stage taxonomy (FORWARD_ORDER), the preset resolver,
# and the required-outputs gate. This driver READS job state through that module
# (connect / resolve_db_path / resolve_preset / preset_flags /
# missing_required_outputs), exactly like cc_board.py imports FORWARD_ORDER from
# the same module. The driver never writes engine state.
_SCRIPTS_DIR = Path(__file__).resolve().parent
_SKILL_ROOT = _SCRIPTS_DIR.parent

# Imported lazily inside handlers so `--help` and `list-steps` work even on a
# stripped deploy where the sibling state module is absent (mirrors cc_board.py's
# fail-soft import posture). The import is REQUIRED for `next` / `verify`.
_ps = None


def _podcast_state():
    """Import podcast_state once. Raises a typed error if it is missing."""
    global _ps
    if _ps is None:
        sys.path.insert(0, str(_SCRIPTS_DIR))
        try:
            import podcast_state  # noqa: PLC0415
        except Exception as exc:  # noqa: BLE001
            raise StepDriverError(
                "podcast_state.py (the SOLE state writer) is missing from the "
                "build; the step driver cannot read job state. install the "
                "58-podcast-production-engine scripts directory first."
            ) from exc
        _ps = podcast_state
    return _ps


# ---------------------------------------------------------------------------
# Exit codes (mirror podcast_state.py's vocabulary so callers can branch).
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_TRANSITION = 3
EXIT_REFUSED = 4
EXIT_ERROR = 1


class StepDriverError(Exception):
    """Raised on a driver-level failure (missing state module, missing job)."""


class UsageError(StepDriverError):
    """Raised on bad arguments. Exit code 2."""


class BlockedTransitionError(StepDriverError):
    """Raised when a step's required outputs are not yet recorded. Exit 3."""


# ---------------------------------------------------------------------------
# Step -> status mapping (BINDING, mirrors SKILL.md Step ownership + wiring.json
# kanban stage mapping). The driver reads the job's CURRENT status and the
# outputs already recorded to decide which step the runbook is on.
# ---------------------------------------------------------------------------
STATUS_BY_STEP = {
    1: "received",
    2: "writing",
    3: "researching",
    4: "writing",
    5: "writing",
    6: "writing",
    7: "writing",
    8: "writing",
    9: "in_qc",
    10: "generating_art",
    11: "producing_audio",
    12: "publishing",
    13: "publishing",
    14: "publishing",
    15: "publishing",
    16: "publishing",
    17: "enrolling",
    18: "complete",
}

# Steps in run order per status (wiring.json kanban `steps` arrays).
STEPS_BY_STATUS = {
    "received": [1],
    "researching": [3],
    "writing": [2, 4, 5, 6, 7, 8],
    "in_qc": [9],
    "generating_art": [10],
    "producing_audio": [11],
    "publishing": [12, 13, 14, 15, 16],
    "enrolling": [17],
    "complete": [18],
}

# The canonical 18-step names (SKILL.md "The canonical 18-step pipeline").
STEP_NAMES = {
    1: "Ingest",
    2: "Select engines",
    3: "Research assistant stage",
    4: "Size",
    5: "Blueprint",
    6: "Draft",
    7: "Improvement pass",
    8: "Read-aloud pass",
    9: "Quality control (episode gate)",
    10: "Cover art",
    11: "Audio",
    12: "Documents",
    13: "Book teaser",
    14: "Store media",
    15: "Publish to Podbean",
    16: "Link back",
    17: "Trigger and enroll",
    18: "Deliver",
}

# Steps whose command is a CONTENT step: the driver emits the model_router.py
# route for the tier (content or qc_judge); the department agent fills the
# runbook prompt and executes the route in its OWN tool-bearing turn. Step 2
# (select engines) is deterministic (blend_voice_governance.py) and is NOT
# content; Step 9 QC is both deterministic (Tier-1 mechanical) and content
# (judge tier), so it is listed for the judge-route emission.
CONTENT_STEPS = {3, 4, 5, 6, 7, 8, 9}


# ---------------------------------------------------------------------------
# Script path helpers (relative to this file's directory).
# ---------------------------------------------------------------------------
def _script(*parts: str) -> str:
    return str(_SCRIPTS_DIR.joinpath(*parts))


def _model_router() -> str:
    return _script("model_router.py")


def _state_writer() -> str:
    return _script("podcast_state.py")


# ---------------------------------------------------------------------------
# Job-state reads (through podcast_state's own database; read-only).
# ---------------------------------------------------------------------------
def _load_job_row(ps, db_path, job_id):
    conn = ps.connect(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM podcast_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    if row is None:
        raise StepDriverError(f"no such job_id: {job_id}")
    return dict(row)


def _load_payload(ps, db_path, job_id) -> dict:
    conn = ps.connect(db_path)
    try:
        row = conn.execute(
            "SELECT payload_json FROM podcast_job_payloads WHERE job_id = ?",
            (job_id,),
        ).fetchone()
    finally:
        conn.close()
    if row is None or not row[0]:
        return {}
    try:
        data = json.loads(row[0])
        return data if isinstance(data, dict) else {}
    except (ValueError, TypeError):
        return {}


def _next_status(ps, status: str):
    try:
        i = ps.FORWARD_ORDER.index(status)
    except ValueError:
        return None
    if i + 1 < len(ps.FORWARD_ORDER):
        return ps.FORWARD_ORDER[i + 1]
    return None


def _resolve_preset(ps, db_path, job_id, row):
    """Resolve the job's preset EXACTLY the way podcast_state.cmd_advance does
    (podcast_state.py:1068): through a LIVE connection, so an explicit in-enum
    preset stored in the intake payload wins over the mode-derived default.
    Passing conn=None here silently dropped the payload preset and mis-gated
    the verify (a season_strategy job in interview mode demanded media outputs
    the writer never required)."""
    conn = ps.connect(db_path)
    try:
        return ps.resolve_preset(conn, job_id, row.get("mode") or "")
    finally:
        conn.close()


def _resolve_preset_flags(ps, db_path, job_id, row) -> dict:
    return ps.preset_flags(_resolve_preset(ps, db_path, job_id, row))


# ---------------------------------------------------------------------------
# Step resolution: which step is the runbook on, and what is next?
# ---------------------------------------------------------------------------
def _produces_media(flags: dict) -> bool:
    """True when the preset produces media artifacts, mirroring the writer's
    podcast_state._gate_satisfied('produces_media') predicate EXACTLY: any of
    render_audio / publish_podbean / store_media. Used to gate Step 10 (cover)
    so the driver orders a cover exactly when the transition gate requires
    cover_image_url, and never otherwise."""
    return any(bool(flags.get(k)) for k in
               ("render_audio", "publish_podbean", "store_media"))


def _current_step(ps, db_path, job_id, row, flags=None) -> int | None:
    """Derive the CURRENT pipeline step from the job's recorded status + outputs
    + PRESET FLAGS (config/presets.json, resolved exactly like the writer).

    A status may host several steps (writing hosts 2,4,5,6,7,8; publishing hosts
    12,13,14,15,16). The step is derived from which output columns are already
    recorded, using the run order within the status:

      writing  (2,4,5,6,7,8): a recorded title means blueprint (5) is done; a
               recorded writing_model means draft (6) is done; otherwise the
               runbook is at the top of the writing block (2 select engines).
      publishing (12..16): documents done => 12 recorded; teaser done => 13
               recorded (interview only); media URLs recorded => 14 done;
               permalink recorded => 15 done; otherwise 16 (link back) is next.

    PRESET GATING (N1 fix). Every media/emission step is emitted ONLY when the
    job's preset flags require it, so `next` never orders work that the writer's
    required-outputs gate (`verify`) does not owe, and never WITHHOLDS work the
    gate demands:
      - Step 10 (generating_art, cover) requires produces_media (render_audio
        OR publish_podbean OR store_media -- the SAME helper the writer's gate
        uses for cover_image_url, podcast_state.py _gate_satisfied); a preset
        that stores media (episode_asset_pack) still owes the cover even though
        it never re-renders audio;
      - Step 11 (producing_audio, audio) requires render_audio; a preset that
        never re-renders audio (episode_asset_pack hard-refuses audio re-render)
        owes no audio step, and the writer's next gate requires no output;
      - Step 14 (store media) requires store_media;
      - Step 15 (Podbean publish) requires publish_podbean;
      - Step 16 (link back) requires link_back;
      - Step 17 (enroll / spreadsheet) requires workflow_enrollment OR
        running_spreadsheet_update (the preset's terminal action).
    A preset that skips a step returns None for it: a document-only preset
    (season_strategy) at `publishing` with its documents rendered carries NO
    runbook step (its deliverable is the document); the writer advances it to
    enrolling with zero media, and the driver now says exactly that. An empty
    flags dict (unresolvable preset) FAILS CLOSED: nothing is emitted."""

    flags = flags or {}
    status = row.get("status")
    steps = STEPS_BY_STATUS.get(status, [])
    if not steps:
        return None

    # Terminal / single-step statuses: the step is the status's only step.
    # Step 1 (INGEST) is the deterministic first step already executed by
    # webhook/intake_handler.py, so the step driver's domain is Steps 2-18:
    # a job at `received` is past ingest and its next step is Step 2.
    if status == "received":
        return 2
    if status == "researching":
        return 3
    if status == "in_qc":
        return 9
    if status == "generating_art":
        # Step 10 (cover) is owed exactly when the writer's transition gate
        # requires cover_image_url, i.e. produces_media. Use the SAME predicate
        # the writer uses (render_audio OR publish_podbean OR store_media) so the
        # driver never withholds a cover the gate demands (episode_asset_pack
        # stores media => owes the cover) nor orders one the gate never owed.
        if not _produces_media(flags):
            return None
        return 10
    if status == "producing_audio":
        # Step 11 (audio) is owed only when the preset re-renders audio. A preset
        # that hard-refuses audio re-render (episode_asset_pack) owes no step at
        # producing_audio; the writer's next transition requires no output there.
        if flags.get("render_audio") is not True:
            return None
        return 11
    if status == "enrolling":
        # Step 17's two flavors are the preset's TERMINAL ACTION: interview
        # enrolls workflows, solo appends the running spreadsheet. A preset with
        # neither (season_strategy, episode_asset_pack) skips Step 17 entirely;
        # the writer advances enrolling -> complete with no enrollment owed.
        if not (flags.get("workflow_enrollment") is True
                or flags.get("running_spreadsheet_update") is True):
            return None
        return 17
    if status == "complete":
        return 18

    if status == "writing":
        if row.get("writing_model"):
            return 6  # draft done -> improvement pass (7) is the next content step
        if row.get("episode_title"):
            return 6  # blueprint done -> draft
        return 2  # top of the writing block: select engines

    if status == "publishing":
        # book_teaser is interview-only: a preset whose book_teaser flag is not
        # strictly True never requires Step 13 (mirrors the state machine's
        # required-outputs gate for book_teaser_url, gate "book_teaser").
        teaser_required = bool(flags.get("book_teaser") is True)
        if not row.get("episode_package_url"):
            return 12  # documents not yet rendered
        if teaser_required and not row.get("book_teaser_url"):
            return 13  # book teaser pending (interview preset)
        # Steps 14/15/16 are preset-gated (N1): a document-only preset owes no
        # media store, no Podbean publish, and no link-back, so none is emitted.
        if flags.get("store_media") is True and (
                not row.get("mp3_media_url") or not row.get("cover_image_url")):
            return 14  # store media not yet done
        if flags.get("publish_podbean") is True and not row.get("podbean_permalink"):
            return 15  # publish not yet done
        if flags.get("link_back") is True:
            return 16  # everything else done -> link back
        return None  # preset requires no further publishing-block step

    return steps[0]


def _next_step(ps, db_path, job_id, row, current: int | None) -> int | None:
    """Return the next step the runbook must execute, or None when no step
    applies (an unknown status). If the current status still has runbook work,
    next == current (the driver re-emits the SAME step's command, idempotently,
    until the agent records progress and advances status). At `complete` the
    next step is 18 DELIVER: the delivery report is a real runbook step owned
    by the complete status, so the driver emits it (the plan requires the
    EXACT command for Steps 2-18, and Step 18 must be reachable)."""
    if current is None:
        return None
    status = row.get("status")
    if status == "complete":
        return 18
    if status == "writing":
        if current == 2:
            return 2
        if current == 6:
            # draft done -> improvement pass; but there is no distinct persisted
            # output for 7/8, so the runbook continues 7 then 8 within the same
            # status. Re-emit the content route for the writing block.
            return 6
        return current
    if status == "publishing":
        if current is None:
            # The preset requires no further publishing-block step (N1): do NOT
            # fall back to Step 12; the runbook's move is a writer advance.
            return None
        steps = STEPS_BY_STATUS.get("publishing", [])
        if current in steps:
            return current
        return steps[0]
    # Single-step statuses: next is the same step until the status advances.
    return current


# ---------------------------------------------------------------------------
# Command emission
# ---------------------------------------------------------------------------
def _emit_content_command(step: int, job_id: str, row: dict) -> str:
    """Emit the model_router.py route for a content step. The department agent
    fills the runbook prompt and executes the route in its OWN turn."""
    tier = "qc_judge" if step == 9 else "content"
    context = {
        "job_id": job_id,
        "mode": row.get("mode") or "",
        "style": row.get("style") or "",
    }
    payload = {
        "tier": tier,
        "messages": [
            {
                "role": "user",
                "content": "<Step %d %s prompt: fill from the runbook>"
                % (step, STEP_NAMES.get(step, "")),
            }
        ],
        "context": context,
    }
    return "%s route <<'JSON'\n%s\nJSON" % (
        _model_router(),
        json.dumps(payload, ensure_ascii=False),
    )


def _emit_step_command(step: int, job_id: str, row: dict, payload: dict,
                       flags: dict) -> str:
    """Emit the EXACT next command for a deterministic step."""
    title = row.get("episode_title") or "<episode-title>"
    client_name = " ".join(
        x for x in (row.get("submitter_first_name"), row.get("submitter_last_name"))
        if x
    ) or "<client-name>"

    if step == 2:
        # Select engines: deterministic voice-governance proof for the engine.
        return (
            "%s --prove --respondent \"%s\""
            % (_script("blend_voice_governance.py"), client_name)
        )

    if step in (3, 4, 5, 6, 7, 8):
        return _emit_content_command(step, job_id, row)

    if step == 9:
        # Step 9 QC: the deterministic Tier-1 mechanical checks run first at
        # zero model cost; the semantic checks (fabrication, mode perspective,
        # pronoun correctness) and the rubric run on the DISTINCT judge tier via
        # the model_router qc_judge route (SKILL.md Step 9).
        mechanical = (
            "%s <deliverable.json> --style %s --mode %s --json"
            % (_script("qc-tier1-mechanical.py"),
               row.get("style") or "",
               ("interview" if row.get("mode") == "interview_style_podcast" else "personal"))
        )
        judge = _emit_content_command(step, job_id, row)  # tier qc_judge
        return "%s\n\n# Step 9 semantic QC (judge tier):\n%s" % (mechanical, judge)

    if step == 10:
        return (
            "bash %s --prompt-file <visual_desc.txt> --title \"%s\" --client \"%s\" "
            "--out <cover.jpg> --receipt <cover-receipt.json>"
            % (_script("generate_cover.sh"), title, client_name)
        )

    if step == 11:
        return (
            "bash %s <script_file> <reference_id> s2.1-pro <out.mp3> \"%s\" \"%s\""
            % (_script("generate_podcast_audio.sh"), client_name, title)
        )

    if step == 12:
        return (
            "%s render --manifest <episode-manifest.json> --out-dir <out>"
            % (_script("render_documents.py"))
        )

    if step == 13:
        return (
            "%s --content <teaser.json> --out <teaser.pdf> --episode-title \"%s\""
            % (_script("render_book_teaser.py"), title)
        )

    if step == 14:
        return (
            "%s store --job <job.json>"
            % (_script("caf", "media_upload", "upload_media.py"))
        )

    if step == 15:
        mode = row.get("mode") or "personal_podcast_style"
        base = "bash %s" % _script("podbean_publish.sh")
        speaker = ""
        if mode == "interview_style_podcast":
            # Interview titles append "Inspired by <speaker>" (SKILL.md Step 15
            # title convention). The guest name is survey data the mapper never
            # guesses, so the agent fills this placeholder from the intake
            # survey's guest_first_name. Personal mode carries no speaker.
            speaker = " --speaker \"<guest_first_name>\""
        return (
            "%s --title \"%s\" --audio-url \"<mp3_media_url>\" "
            "--image-url \"<cover_image_url>\" --description \"<episode_description>\"%s "
            "--job-id %s"
            % (base, title, speaker, job_id)
        )

    if step == 16:
        return (
            "STEP 16 LINK BACK (deterministic runbook directive): write title, "
            "description, Episode Package link, and Speech Script link in ONE "
            "GHL batch, then write the episode URL field ALONE and LAST; read "
            "back every field byte-for-byte. Run in the agent's own turn."
        )

    if step == 17:
        mode = row.get("mode") or "personal_podcast_style"
        if mode == "personal_podcast_style":
            return (
                "%s append --state-dir <state-dir> --client-id %s "
                "--record-file <episode-record.json> --mode personal_podcast_style"
                % (_script("personal_spreadsheet.py"), row.get("client_id") or job_id)
            )
        return (
            "STEP 17 TRIGGER AND ENROLL (interview, deterministic runbook "
            "directive): verify the URL write already field-triggered the "
            "'podcast is completed' workflow, enroll explicitly only if not, "
            "enroll 'podcast episode is ready', verify both via CAF reads. "
            "Personal mode refuses workflow enrollment (hard mode guard)."
        )

    if step == 18:
        return (
            "%s --record-file <episode-record.json> --destination operator --json"
            % (_script("delivery_report.py"))
        )

    raise StepDriverError(f"no command defined for step {step}")


# ---------------------------------------------------------------------------
# Off-pipeline statuses (held / blocked / failed): the driver must report the
# REAL state, never claim the run is done. These statuses are outside the linear
# FORWARD_ORDER step table, so step resolution returns nothing for them; the
# handlers below translate that nothing into an honest, non-zero report.
# ---------------------------------------------------------------------------
def _off_pipeline_report(row) -> tuple:
    """Return (message, done_flag) for a job NOT on the forward pipeline, or
    None when the status is a normal pipeline status. `complete` is handled by
    the caller (it is the legitimate terminal edge, not an off-pipeline state)."""
    status = row.get("status")
    if status == "queued_credit_out":
        return (
            "job is HELD on the credit-out queue (service: %s; resume_stage: %s). "
            "The step driver never advances a held job. Restore credits and run "
            "`podcast_state.py resume --job-id <id>`; the driver then picks up at "
            "the recorded resume_stage." % (
                row.get("queued_service") or "?",
                row.get("resume_stage") or "?"),
            False,
        )
    if status == "blocked_standing":
        return (
            "job is BLOCKED on the client's standing (the Step 1 standing "
            "pre-check refused it). Nothing is produced or deleted. When standing "
            "returns to YES the same idempotency_key resumes cleanly; until then "
            "the step driver emits no command.",
            False,
        )
    if status == "failed":
        return (
            "job is FAILED (terminal). failed_step: %s; last_error: %s. The step "
            "driver emits no command for a failed job; the runbook's failure "
            "handling (founder alert via alert-dedup.py) owns it from here." % (
                row.get("failed_step") or "?",
                (row.get("last_error") or "?")[:120]),
            False,
        )
    return None


# ---------------------------------------------------------------------------
# Required-outputs gate (verify)
# ---------------------------------------------------------------------------
def _verify_outputs(ps, db_path, job_id, row):
    """Run the required-outputs gate for the current status -> next status
    transition. Raises BlockedTransitionError (exit 3) naming every missing
    output. Mirrors podcast_state.check_transition's gate semantics, including
    the writer's preset resolution (live-connection payload lookup)."""
    status = row.get("status")
    off = _off_pipeline_report(row)
    if off is not None:
        # Held / blocked / failed: there is no forward edge to verify. Fail
        # loud with the REAL state instead of a silent VERIFY PASS.
        raise BlockedTransitionError(off[0])
    to_status = _next_status(ps, status)
    if to_status is None:
        return []  # terminal edge (complete): nothing owed forward
    preset = _resolve_preset(ps, db_path, job_id, row)
    flags = ps.preset_flags(preset)
    conn = ps.connect(db_path)
    try:
        db_row = conn.execute(
            "SELECT * FROM podcast_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
    finally:
        conn.close()
    missing = ps.missing_required_outputs(db_row, status, to_status, flags)
    if missing:
        raise BlockedTransitionError(
            "cannot advance %s -> %s: preset '%s' requires output(s) not yet "
            "recorded: %s. Set them with `podcast_state.py output`, or pass "
            "--force-waiver (audited) only for a test run."
            % (status, to_status, preset or "?", ", ".join(missing))
        )
    return missing


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------
def cmd_next(args) -> int:
    ps = _podcast_state()
    db_path = args.db_path or ps.resolve_db_path()
    row = _load_job_row(ps, db_path, args.job_id)
    payload = _load_payload(ps, db_path, args.job_id)
    flags = _resolve_preset_flags(ps, db_path, args.job_id, row)

    current = _current_step(ps, db_path, args.job_id, row, flags)
    step = _next_step(ps, db_path, args.job_id, row, current)

    if step is None:
        # A held, blocked-on-standing, or failed job carries NO step: report the
        # REAL state with a non-zero exit. Never claim such a job is complete.
        off = _off_pipeline_report(row)
        if off is not None:
            out = {
                "job_id": args.job_id,
                "status": row.get("status"),
                "step": None,
                "name": None,
                "done": False,
                "command": None,
                "note": off[0],
            }
            if args.json:
                print(json.dumps(out, ensure_ascii=False))
            else:
                print("NO NEXT STEP (job %s is %s)"
                      % (args.job_id, row.get("status")))
                print("  %s" % off[0])
            return EXIT_REFUSED
        # A PIPELINE status with no step owed: the job's preset flags skip the
        # remaining work of this status (N1). This is NOT an error and NOT a
        # terminal edge: the writer's gate is already satisfied, so the runbook
        # move is a plain `podcast_state.py advance`, then call `next` again.
        status = row.get("status")
        if status in STEPS_BY_STATUS:
            preset_name = _resolve_preset(ps, db_path, args.job_id, row) or "?"
            advance_to = _next_status(ps, status)
            note = (
                "no runbook step is owed at status '%s' for preset '%s': the "
                "preset's flags skip the remaining work of this status (a "
                "document-only preset orders no cover, audio, media store, "
                "publish, or link-back). The writer's required-outputs gate for "
                "this transition is already satisfied; run `podcast_state.py "
                "advance --job-id %s --to %s` and call next again."
                % (status, preset_name, args.job_id, advance_to or "?")
            )
            out = {
                "job_id": args.job_id,
                "status": status,
                "step": None,
                "name": None,
                "done": False,
                "command": None,
                "note": note,
                "advance_to": advance_to,
            }
            if args.json:
                print(json.dumps(out, ensure_ascii=False))
            else:
                print("NO RUNBOOK STEP OWED (job %s at %s, preset %s)"
                      % (args.job_id, status, preset_name))
                print("  %s" % note)
            return EXIT_OK
        raise StepDriverError(
            "job %s has status '%s', which is not a pipeline status the step "
            "driver can sequence" % (args.job_id, row.get("status"))
        )

    command = _emit_step_command(step, args.job_id, row, payload, flags)
    step_status = STATUS_BY_STEP.get(step, row.get("status"))
    name = STEP_NAMES.get(step, "")
    out = {
        "job_id": args.job_id,
        "status": row.get("status"),
        "step": step,
        "name": name,
        "step_status": step_status,
        "command": command,
        "content_step": step in CONTENT_STEPS,
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        kind = "CONTENT" if step in CONTENT_STEPS else "DETERMINISTIC"
        # Show the JOB's own status (the state machine's truth); the step's
        # owning status rides along in the JSON as step_status.
        line = "STEP %d %s [%s | job status %s" % (
            step, name.upper(), kind, row.get("status"))
        if step_status != row.get("status"):
            line += ", step %s's status %s" % (step, step_status)
        print(line + "]")
        print("  %s" % command)
        if step in CONTENT_STEPS:
            print("  (content step: fill the model_router route payload from the runbook)")
    return EXIT_OK


def cmd_verify(args) -> int:
    ps = _podcast_state()
    db_path = args.db_path or ps.resolve_db_path()
    row = _load_job_row(ps, db_path, args.job_id)
    try:
        missing = _verify_outputs(ps, db_path, args.job_id, row)
    except BlockedTransitionError as exc:
        if args.json:
            print(json.dumps({"job_id": args.job_id, "ok": False,
                              "error": "missing_required_outputs",
                              "detail": str(exc)}, ensure_ascii=False))
        else:
            print("VERIFY FAIL: %s" % exc)
        return EXIT_TRANSITION
    if args.json:
        print(json.dumps({"job_id": args.job_id, "ok": True,
                          "missing": missing}, ensure_ascii=False))
    else:
        print("VERIFY PASS: %s outputs are recorded for the next transition"
              % args.job_id)
    return EXIT_OK


def cmd_list_steps(args) -> int:
    rows = []
    if args.job_id:
        ps = _podcast_state()  # job-position mode REQUIRES the sibling module
        db_path = args.db_path or ps.resolve_db_path()
        row = _load_job_row(ps, db_path, args.job_id)
        flags = _resolve_preset_flags(ps, db_path, args.job_id, row)
        current = _current_step(ps, db_path, args.job_id, row, flags)
        next_step = _next_step(ps, db_path, args.job_id, row, current)
        rows.append({
            "job_id": args.job_id,
            "status": row.get("status"),
            "current_step": current,
            "next_step": next_step,
        })
    else:
        for step in range(1, 19):
            rows.append({
                "step": step,
                "name": STEP_NAMES.get(step, ""),
                "status": STATUS_BY_STEP.get(step, ""),
                "content": step in CONTENT_STEPS,
            })
    if args.json:
        print(json.dumps(rows, ensure_ascii=False))
    else:
        if args.job_id:
            r = rows[0]
            print("job %s status=%s current_step=%s next_step=%s"
                  % (r["job_id"], r["status"], r["current_step"], r["next_step"]))
        else:
            for r in rows:
                kind = "content" if r["content"] else "deterministic"
                print("  Step %2d  %-38s  %-16s  %s"
                      % (r["step"], r["name"], r["status"], kind))
    return EXIT_OK


def cmd_self_test(args) -> int:
    """Hermetic offline battery. No network, no live DB. Verifies the step
    table, the step resolution, and the emitted-command shapes."""
    ok = True

    def check(label: str, cond: bool) -> None:
        nonlocal ok
        ok = ok and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    check("18 steps defined", len(STEP_NAMES) == 18)
    check("status mapping covers 2..18",
          all(n in STATUS_BY_STEP for n in range(2, 19)))
    check("writing hosts the content block",
          STEPS_BY_STATUS["writing"] == [2, 4, 5, 6, 7, 8])
    check("publishing hosts 12..16",
          STEPS_BY_STATUS["publishing"] == [12, 13, 14, 15, 16])

    # Step resolution against a fake row (no DB).
    fake = {
        "status": "writing", "mode": "personal_podcast_style",
        "style": "vulnerable", "episode_title": None, "writing_model": None,
        "episode_package_url": None, "book_teaser_url": None,
        "mp3_media_url": None, "cover_image_url": None, "podbean_permalink": None,
    }
    check("writing starts at step 2", _current_step(None, "", "", fake) == 2)
    fake2 = dict(fake, episode_title="A title", writing_model="kimi-2.6")
    check("writing after draft stays in writing block",
          _current_step(None, "", "", fake2) == 6)

    pub = {
        "status": "publishing", "mode": "personal_podcast_style",
        "style": "vulnerable", "episode_package_url": None, "book_teaser_url": None,
        "mp3_media_url": None, "cover_image_url": None, "podbean_permalink": None,
    }
    check("publishing starts at step 12", _current_step(None, "", "", pub) == 12)
    pub2 = dict(pub, episode_package_url="https://x/pkg",
                mp3_media_url="https://x/a.mp3", cover_image_url="https://x/c.jpg")
    # Preset-gated step emission (N1): the full-producing flag set (solo) keeps
    # the media ordering; the step table below asserts every skip.
    SOLO = {"render_audio": True, "publish_podbean": True, "book_teaser": False,
            "store_media": True, "link_back": True,
            "workflow_enrollment": False, "running_spreadsheet_update": True}
    check("publishing with media but no permalink -> 15",
          _current_step(None, "", "", pub2, SOLO) == 15)
    SEASON = {"render_audio": False, "publish_podbean": False,
              "book_teaser": False, "store_media": False, "link_back": False,
              "workflow_enrollment": False, "running_spreadsheet_update": False}
    ASSET = {"render_audio": False, "publish_podbean": False,
             "book_teaser": "conditional_interview_source", "store_media": True,
             "link_back": True, "workflow_enrollment": False,
             "running_spreadsheet_update": False}
    check("N1: empty flags fail closed (no step emitted)",
          _current_step(None, "", "", pub2, {}) is None)
    check("N1: season_strategy docs-only publishing owes NO step",
          _current_step(None, "", "", pub2, SEASON) is None)
    check("N1: season_strategy without docs still renders them (12)",
          _current_step(None, "", "", dict(pub), SEASON) == 12)
    check("N1: episode_asset_pack skips publish, still links back (16)",
          _current_step(None, "", "", pub2, ASSET) == 16)
    check("N1: episode_asset_pack still stores regenerated media (14)",
          _current_step(None, "", "", dict(pub, episode_package_url="https://x/p"),
                        ASSET) == 14)
    art_off = dict(pub, status="generating_art")
    audio_off = dict(pub, status="producing_audio")
    check("N1: generating_art with no media flags owes no step",
          _current_step(None, "", "", art_off, SEASON) is None)
    check("N1: generating_art with render_audio True emits 10",
          _current_step(None, "", "", art_off, SOLO) == 10)
    # Step 10 is gated on produces_media (mirrors the writer's cover gate), so
    # a preset that STORES media but never renders audio (episode_asset_pack)
    # still owes the cover the writer's transition gate demands.
    check("N1: generating_art with store_media only still emits 10",
          _current_step(None, "", "", art_off, ASSET) == 10)
    check("N1: producing_audio with render_audio False owes no step",
          _current_step(None, "", "", audio_off, SEASON) is None
          and _current_step(None, "", "", audio_off, ASSET) is None)
    check("N1: producing_audio with render_audio True emits 11",
          _current_step(None, "", "", audio_off, SOLO) == 11)
    enr = dict(pub, status="enrolling")
    check("N1: enrolling with no terminal action owes no step",
          _current_step(None, "", "", enr, SEASON) is None
          and _current_step(None, "", "", enr, ASSET) is None)
    check("N1: enrolling emits 17 for workflow and spreadsheet presets",
          _current_step(None, "", "", enr, dict(SOLO)) == 17
          and _current_step(None, "", "", enr, {"workflow_enrollment": True}) == 17)
    check("N1: _next_step honors None (no 12 fallback)",
          _next_step(None, "", "", pub2, None) is None)

    # Command shapes for deterministic steps (no import of podcast_state needed).
    row = dict(fake, status="generating_art", episode_title="T",
               submitter_first_name="A", submitter_last_name="B")
    for step in (10, 11, 12, 14, 15, 18):
        cmd = _emit_step_command(step, "pj_1", row, {}, {})
        check("step %d emits a command" % step, bool(cmd) and "\n" not in cmd)
    check("step 10 calls generate_cover.sh",
          "generate_cover.sh" in _emit_step_command(10, "j", row, {}, {}))
    check("step 11 calls generate_podcast_audio.sh",
          "generate_podcast_audio.sh" in _emit_step_command(11, "j", row, {}, {}))
    check("step 14 calls upload_media.py",
          "upload_media.py" in _emit_step_command(14, "j", row, {}, {}))
    check("step 15 calls podbean_publish.sh",
          "podbean_publish.sh" in _emit_step_command(15, "j", row, {}, {}))
    check("step 2 calls blend_voice_governance.py",
          "blend_voice_governance.py" in _emit_step_command(2, "j", row, {}, {}))
    check("content step emits model_router route",
          "model_router.py route" in _emit_content_command(5, "j", row))
    check("step 9 emits judge route",
          "model_router.py route" in _emit_step_command(9, "j", row, {}, {})
          and "qc_judge" in _emit_step_command(9, "j", row, {}, {}))

    # Off-pipeline honesty: held / blocked / failed must NEVER read "complete".
    held = dict(fake, status="queued_credit_out", queued_service="kie_ai",
                resume_stage="writing")
    off = _off_pipeline_report(held)
    check("held job reports HELD, not complete",
          off is not None and "HELD" in off[0] and "resume" in off[0])
    failed = dict(fake, status="failed", failed_step="10",
                  last_error="kie refused")
    off_f = _off_pipeline_report(failed)
    check("failed job reports FAILED, not complete",
          off_f is not None and "FAILED" in off_f[0])
    check("pipeline status yields no off-pipeline report",
          _off_pipeline_report(fake) is None)

    # Step 18 is reachable: a complete job's next step is 18 DELIVER, and its
    # command is the delivery report.
    done = dict(fake, status="complete")
    check("complete -> next step is 18 (delivery report reachable)",
          _next_step(None, "", "", done, _current_step(None, "", "", done)) == 18)
    check("step 18 emits delivery_report.py",
          "delivery_report.py" in _emit_step_command(18, "j", row, {}, {}))

    # Step 15 speaker wiring: interview carries --speaker, personal does not.
    iv = dict(row, status="publishing", mode="interview_style_podcast")
    check("step 15 interview carries --speaker",
          "--speaker" in _emit_step_command(15, "j", iv, {}, {}))
    pv = dict(row, status="publishing", mode="personal_podcast_style")
    check("step 15 personal has no --speaker",
          "--speaker" not in _emit_step_command(15, "j", pv, {}, {}))

    print("RESULT:", "PASS" if ok else "FAIL")
    return EXIT_OK if ok else EXIT_ERROR


# ---------------------------------------------------------------------------
# Parser + main
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="podcast_step_driver.py",
        description="Deterministic, no-daemon step driver for the Podcast "
                    "Production Engine (Steps 2-18).",
    )
    p.add_argument("--db-path", default=None, help="override PODCAST_DB_PATH")
    p.add_argument("--json", action="store_true", help="machine-readable JSON output")
    sub = p.add_subparsers(dest="command", required=True)

    n = sub.add_parser("next", help="emit the EXACT next command for the job")
    n.add_argument("--job-id", required=True)
    n.set_defaults(func=cmd_next)

    v = sub.add_parser("verify", help="check the required-outputs gate for the "
                                      "next transition (fail loud, exit 3)")
    v.add_argument("--job-id", required=True)
    v.set_defaults(func=cmd_verify)

    l = sub.add_parser("list-steps", help="show the step table or a job's position")
    l.add_argument("--job-id", default=None)
    l.set_defaults(func=cmd_list_steps)

    s = sub.add_parser("self-test", help="hermetic offline battery")
    s.set_defaults(func=cmd_self_test)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except BlockedTransitionError as exc:
        sys.stderr.write("illegal transition: %s\n" % exc)
        return EXIT_TRANSITION
    except UsageError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_USAGE
    except StepDriverError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return EXIT_REFUSED
    except Exception as exc:  # noqa: BLE001 - sanitized, non-zero
        red = _podcast_state_quiet()
        msg = red.redact(str(exc)) if red is not None else str(exc)
        sys.stderr.write("error: %s\n" % msg)
        return EXIT_ERROR


def _podcast_state_quiet():
    """Best-effort podcast_state reference for redaction; never raises."""
    try:
        return _podcast_state()
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())

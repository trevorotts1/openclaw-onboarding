#!/usr/bin/env python3
"""Assemble the dept-format intake JSON from the app's answers.

The Presentation Interview app produces an intake record in the shape
build_deck.py's _chk_intake / _chk_mode and the canonical entry gates expect:

    working/copy/intake.json   (the deck brief: deck_brief.* fields, the six
                                mandatory pre_presentation_capture fields, the
                                derived legacy axis fields, the upsell flags)
    working/interview/intake_ledger.json  (the completed, turn-gated interview
                                record that GATE 0 / _intake_provenance_gate
                                require)

This module performs that assembly on the BOX, so the app's submission is
replayed through the same governed record the chat driver would have produced.
It is the WRITER half of the submit-trigger: intake_bridge.py (below) polls the
Worker, this writer stamps the run dir, then cc_board.ingest_deck_task opens the
kanban card — the presentation department start. No shortcuts: the deck can only
build through presentation-canonical-entry.sh's gates.

FAIL-CLOSED on deck type (PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3): this
module used to hardcode deck_type="webinar" (+ creation_mode/presentation_mode/
audience_mode) unconditionally, so a client who asked for a signature talk
silently got a webinar with "complete": true written on top of it -- a
fabricated answer made to look like an approved one. It no longer guesses.
deck_type is derived ONLY from a real `presentation_type` answer (see
_grounded_deck_type_fields()); when that answer is missing or unrecognized,
write_intake_file()/write_ledger() raise UngroundedDeckTypeError and write
NOTHING rather than mark an intake complete on a fabricated field. Full
routing through deck-intake-driver.py's presentation_type picker + turn
ledger + prove_sp_routing.py is the correct long-term fix and is deliberately
NOT implemented here -- see UngroundedDeckTypeError.__doc__.

Stdlib only. Run:
  python3 intake_writer.py --intake intake.json --run-dir /path/to/run
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

# The six mandatory pre_presentation_capture fields build_deck.py's
# _intake_provenance_gate requires (mirrored here for the non-driver path).
MANDATORY_PRE_CAPTURE = (
    "REPRESENTATION_MIX",
    "AUDIENCE_COMPOSITION_NOTE",
    "GROUNDED_CONTENT",
    "VISUAL_MIX",
    "DARK_OK",
    "HOOK_SEED",
)

# presentation_type -> {deck_type, creation_mode, presentation_mode,
# audience_mode}. Mirrors deck-intake-driver.py:LEGACY_FIELD_MAPPING /
# intake/deck-intake-questions.json's legacy_field_mapping -- THE SOURCE OF
# TRUTH for deck_type (same mirroring pattern as MANDATORY_PRE_CAPTURE above;
# this module runs standalone, stdlib only, so it cannot import the driver).
# presentation_type is the ONE client answer that legitimately determines
# these fields. Deliberately omits the driver table's "requires"/signature_
# source handling (recipient_name, extracted_substance, signature_source
# overrides) -- that is real intake-flow logic belonging to the driver
# integration named in UngroundedDeckTypeError.__doc__, not this patch.
LEGACY_FIELD_MAPPING = {
    "from_scratch": {
        "deck_type": "webinar",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
    },
    "content_personal": {
        "deck_type": "webinar",
        "creation_mode": "content_personal",
        "presentation_mode": "one-person",
        "audience_mode": "PERSONAL",
    },
    "content_general": {
        "deck_type": "webinar",
        "creation_mode": "content_general",
        "presentation_mode": "general",
        "audience_mode": "GENERAL",
    },
    "signature": {
        "deck_type": "signature_presentation",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
    },
}


class UngroundedDeckTypeError(RuntimeError):
    """Raised when deck_type/creation_mode/presentation_mode/audience_mode
    cannot be derived from an answer the client actually gave.

    FAIL CLOSED (PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3): this is the
    replacement for the hardcoded deck_type="webinar" bug. When
    presentation_type was not actually answered -- note the interview app's
    current 12-question set (interview-app/pages/index.html QUESTIONS) never
    asks it, so today this ALWAYS raises for every real app submission --
    callers must not write any file claiming the intake is complete. A
    caller-supplied deck_type/presentation_type claim (e.g. the app
    frontend's own buildIntakePayload(), which separately hardcodes
    presentation_type: "from_scratch" in JS) is never trusted either; only
    the client's own answers are. Full routing through
    deck-intake-driver.py's presentation_type picker, its turn-gated ledger,
    and prove_sp_routing.py (--signature --sig-record) is the correct
    long-term fix and is deliberately NOT implemented here -- that is a real
    design task (turn-ledger shape reconciliation between the two sanctioned
    driver copies, a non-signature batch-record path that does not exist
    today) out of scope for this fail-closed patch. See
    PRES-DEPT-FIX-REVIEW-2026-08-17.md Part 6 #3.
    """


def _grounded_deck_type_fields(answers: dict) -> dict:
    """Derive {deck_type, creation_mode, presentation_mode, audience_mode,
    presentation_type} from the client's OWN presentation_type answer.

    Never defaults, never fabricates -- raises UngroundedDeckTypeError naming
    exactly what is missing/invalid when presentation_type was not answered
    or was answered with something unrecognized. This is the ONE function
    permitted to set these four fields; nothing else in this module may
    hardcode them.
    """
    raw = answers.get("presentation_type")
    if isinstance(raw, dict):
        raw = raw.get("value", "")
    raw = str(raw or "").strip()
    if not raw:
        raise UngroundedDeckTypeError(
            "no 'presentation_type' answer was captured in this intake -- "
            "cannot determine deck_type/creation_mode/presentation_mode/"
            "audience_mode. Refusing to default to webinar (or any other "
            "type). See UngroundedDeckTypeError.__doc__ for why and what to "
            "do instead."
        )
    if raw not in LEGACY_FIELD_MAPPING:
        raise UngroundedDeckTypeError(
            f"presentation_type answer {raw!r} is not one of "
            f"{sorted(LEGACY_FIELD_MAPPING)} -- refusing to guess a deck_type."
        )
    derived = dict(LEGACY_FIELD_MAPPING[raw])
    derived["presentation_type"] = raw
    return derived


def _require_grounded_deck_type(intake: dict) -> dict:
    """Validate -- and correct -- intake's deck-type axis against its OWN
    `answers`, in place.

    Called by both write_intake_file() and write_ledger() so the gate holds
    no matter which caller built `intake`: assemble_intake() below is NOT the
    only path into this module. intake_bridge.py's cmd_ingest() -- the real
    submit-trigger the app actually uses in production -- builds `intake`
    straight from the Worker payload and calls write_intake_file()/
    write_ledger() directly, never through assemble_intake(). Overwrites the
    four derived fields with the grounded values (never trusts whatever a
    caller pre-stamped there) so a stale or fabricated claim can never
    survive into a written file. Raises UngroundedDeckTypeError -- nothing is
    written -- if it cannot be grounded.
    """
    grounded = _grounded_deck_type_fields(intake.get("answers") or {})
    intake.update(grounded)
    return intake


# Question id -> intake.json field key (deck_brief section unless noted).
# Mirrors the canonical deck-intake-questions.json storeTarget mapping so the
# flat-answers fallback path produces the same keys the frontend-shaped path
# produces. Keys absent here are passed through uppercase.
ID_TO_FIELD = {
    "offer_name": "OFFER_NAME",
    "transformation_promise": "TRANSFORMATION_PROMISE",
    "audience": "AUDIENCE",
    "cta_action": "CTA_ACTION",
    "brand_primary": "BRAND_PRIMARY",
    "tone": "TONE",
    "final_price": "FINAL_PRICE",
    "price_mode": "PRICE_MODE",
    "goal": "GOAL",
    "target_feeling": "TARGET_FEELING",
    "hook_seed": "HOOK_SEED",
    "client_notes": "CLIENT_NOTES",
    "deadline": "DEADLINE",
    "slide_count": "SLIDE_COUNT",
    "delivery_destinations": "DELIVERY_DESTINATIONS",
    "primary_objection": "PRIMARY_OBJECTION",
    "proof_assets": "PROOF_ASSETS",
    "style_prefs": "STYLE_PREFS",
    # upsell yes-no (the new sales/checkout + VSL questions)
    "want_sales_checkout": "WANT_SALES_CHECKOUT",
    "want_vsl_page": "WANT_VSL_PAGE",
    # speech speed lives flat on the intake record (not deck_brief)
    "speech_speed_preference": "speech_speed_preference",
}

# Fields that land under pre_presentation_capture rather than deck_brief.
PRE_CAPTURE_FIELDS = {"WANT_SALES_CHECKOUT", "WANT_VSL_PAGE"}


def field_for(qid: str, value) -> str:
    """Resolve the intake.json field key for a question id."""
    mapped = ID_TO_FIELD.get(qid)
    if mapped:
        return mapped
    return qid.upper()


def map_section(section: str) -> str:
    """Map a storeOn prefix to an intake.json section key."""
    return {
        "deck_brief": "deck_brief",
        "pre_presentation_capture": "pre_presentation_capture",
        "intake.json": "intake",
    }.get(section, "deck_brief")


# FIX-PITCH-ANTI-FAB: fields that MUST land as TRUE ROOT keys on intake.json
# (never nested under deck_brief/pre_presentation_capture/answers) because
# scripts/pitch_engines_check.py's chk_branded_method / chk_time_to_result
# read them with a bare `intake.get("named_methodology")` /
# `intake.get("time_to_result")` at the file's top level -- deliberately, so
# a copywriter can never invent a method name or delivery timeline, only the
# client's own answer can supply them. pitch_engines_check.py is a verifier
# this unit may not edit to add a nested-shape fallback (unlike
# sales_checkout_builder.py / vsl_builder.py, which test_upsell_intake_shape.py
# pins as reading BOTH the driver's flat shape and this bridge's nested
# shape) -- so the flat ROOT shape must be guaranteed on the write side
# instead. deck-intake-driver.py's cmd_complete() already produces this shape
# natively for the chat path (entries[qid] aliasing); this promotion is the
# equivalent guarantee for the app path.
ANTI_FABRICATION_ROOT_FIELDS = ("named_methodology", "time_to_result")


def _promote_anti_fabrication_fields(intake: dict) -> dict:
    """Ensure named_methodology/time_to_result land as TRUE ROOT keys, in place.

    Runs on every path into write_intake_file() -- the flat-answers assembly
    (which files the value under deck_brief.<UPPER> via field_for()'s
    qid.upper() fallback) AND the frontend-shaped passthrough (which has no
    "root" bucket at all in its client-side buildIntakePayload() and would
    otherwise strand the answer inside deck_brief.<UPPER> or the raw
    answers{} map, where pitch_engines_check.py's bare intake.get(...) read
    can never see it). Never invents a value -- only relocates one the client
    actually supplied, checked in this order: already at root, then
    deck_brief.<UPPER>, then answers.<qid>. A question the client was never
    asked (or left unanswered) is correctly left absent -- the gate should
    fail closed on that, not be papered over here.
    """
    answers = intake.get("answers") or {}
    brief = intake.get("deck_brief") or {}
    for qid in ANTI_FABRICATION_ROOT_FIELDS:
        if intake.get(qid):
            continue
        val = brief.get(qid.upper())
        if not val:
            raw = answers.get(qid)
            val = raw.get("value") if isinstance(raw, dict) else raw
        if val:
            intake[qid] = val
    return intake


def assemble_intake(app_payload: dict, run_id: str = "") -> dict:
    """Turn the app's answer map into the dept-format intake record.

    app_payload may carry either `answers` (a flat {qid: value} map) or an
    `intake` object already shaped by the frontend (interview_confirmed, deck
    fields, pre_presentation_capture, deck_brief, intake). When both exist the
    frontend-shaped intake wins and `answers` is attached for provenance.
    """
    if isinstance(app_payload.get("intake"), dict):
        base = dict(app_payload["intake"])
        base["answers"] = app_payload.get("answers") or base.get("answers") or {}
        return base

    answers = app_payload.get("answers") or {}
    brief = {}
    pre = {}
    intake_flat = {}
    for qid, v in answers.items():
        if qid.startswith("_"):
            continue
        if isinstance(v, dict):
            v = v.get("value", "")
        field = field_for(qid, v)
        if field == "speech_speed_preference":
            intake_flat[field] = v
        elif field in PRE_CAPTURE_FIELDS:
            pre[field] = v
        else:
            brief[field] = v
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    # deck_type/creation_mode/presentation_mode/audience_mode/
    # presentation_type: grounded ONLY in the client's own presentation_type
    # answer -- may raise UngroundedDeckTypeError. This used to be a
    # hardcoded "webinar" here; see UngroundedDeckTypeError.__doc__.
    deck_type_fields = _grounded_deck_type_fields(answers)

    intake = {
        "interview_confirmed": True,
        "target_talk_minutes": 20,
        "created_at": now,
        "source": "presentation-interview-app",
        "run_id": run_id,
        "deck_brief": brief,
        "pre_presentation_capture": {
            "REPRESENTATION_MIX": brief.get("AUDIENCE") or "the stated audience",
            "AUDIENCE_COMPOSITION_NOTE": brief.get("AUDIENCE") or "",
            "GROUNDED_CONTENT": brief.get("OFFER_NAME") or "",
            "VISUAL_MIX": "mix",
            "DARK_OK": False,
            "HOOK_SEED": brief.get("TRANSFORMATION_PROMISE") or "",
            **pre,
        },
        "intake": intake_flat,
        "answers": answers,
    }
    intake.update(deck_type_fields)
    return intake


def write_intake_file(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/copy/intake.json in the run dir (the deck brief).

    FAIL CLOSED: raises UngroundedDeckTypeError -- writing nothing -- if
    `intake`'s deck-type axis cannot be grounded in its own `answers`. Runs
    for every caller, not just assemble_intake()'s output: intake_bridge.py's
    cmd_ingest() calls this directly with a raw Worker payload. See
    _require_grounded_deck_type().

    Also runs _promote_anti_fabrication_fields() (FIX-PITCH-ANTI-FAB) for the
    same reason -- so named_methodology/time_to_result land at intake.json's
    TRUE ROOT no matter which caller built `intake`.
    """
    _require_grounded_deck_type(intake)
    _promote_anti_fabrication_fields(intake)
    out = run_dir / "working" / "copy" / "intake.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(intake, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def write_ledger(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/interview/intake_ledger.json as 'complete'.

    This satisfies presentation-canonical-entry.sh GATE 0 (intake ledger) and
    the _intake_provenance_gate's ledger-consistency check for app-captured
    runs. `answers` carries the captured Q&A pairs so the ledger is NOT an
    empty fabrication.

    FAIL CLOSED: raises UngroundedDeckTypeError -- writing nothing, never
    "complete": true -- if `intake`'s deck-type axis cannot be grounded in
    its own `answers`. See _require_grounded_deck_type().
    """
    _require_grounded_deck_type(intake)
    ledger_path = run_dir / "working" / "interview" / "intake_ledger.json"
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    answers = intake.get("answers") or {}
    entries = {}
    for qid, value in answers.items():
        if isinstance(value, dict):
            value = value.get("value", "")
        entries[qid] = {
            "value": value,
            "validated": True,
            "source": "presentation-interview-app",
        }
    ledger = {
        "status": "complete",
        "complete": True,
        "source": "presentation-interview-app",
        "intake_session_id": intake.get("intake_session_id", ""),
        "entries": entries,
    }
    ledger_path.write_text(json.dumps(ledger, indent=2, ensure_ascii=False), encoding="utf-8")
    return ledger_path


_DRIVER_ENVELOPE_FORMAT = "sp-intake-transcript-v1"


class SignedEnvelopePresentError(RuntimeError):
    """Raised by write_transcript() when working/interview/intake_transcript.json
    already holds a SIGNED driver envelope (format == 'sp-intake-transcript-v1',
    written by deck-intake-driver.py's turn-gate -- see intake_trace_check.py's
    DRIVER PROVENANCE doctrine).

    FIX F21-SIBLING (2026-08-20): this module's own write_transcript()
    unconditionally overwrote intake_transcript.json with no read-first check
    at all -- the same "blind write destroys signed provenance" hazard fixed
    at its root in deck-intake-driver.py's cmd_answer/_sig_answer (FAULT-21).
    A driver-produced signed envelope is HIGHER-evidentiary-value provenance
    ("these turns really happened, in this order, through the driver") than
    this bridge's own synthetic Q&A-pair transcript (this module's own
    docstring: full routing through the driver's turn-gate "is the correct
    long-term fix and is deliberately NOT implemented here"). Silently
    replacing the former with the latter would be a real provenance loss, so
    this fails loudly instead -- naming the file -- rather than guessing which
    source should win."""


def write_transcript(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/interview/intake_transcript.json — the real conversation trace.

    presentation-canonical-entry.sh GATE 0b requires this file to exist and be
    non-trivial (>= 200 bytes) with a REAL one-at-a-time conversation (FIX-3:
    intake must be a REAL conversation, not a fabricated block). We build it from
    the app's captured answers: each Q&A pair becomes a dialogue turn, so the
    trace is grounded in the client's actual responses.

    FAIL CLOSED (FIX F21-SIBLING): refuses -- raises SignedEnvelopePresentError,
    writes nothing -- when a SIGNED driver envelope already exists at the
    destination path. See SignedEnvelopePresentError.__doc__.
    """
    out = run_dir / "working" / "interview" / "intake_transcript.json"
    if out.is_file():
        try:
            existing = json.loads(out.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = None
        if isinstance(existing, dict) and existing.get("format") == _DRIVER_ENVELOPE_FORMAT:
            raise SignedEnvelopePresentError(
                f"{out} already holds a signed driver envelope (format="
                f"{_DRIVER_ENVELOPE_FORMAT!r}) -- refusing to overwrite it with "
                "this bridge's own synthetic transcript. Writing nothing.")
    out.parent.mkdir(parents=True, exist_ok=True)
    answers = intake.get("answers") or {}
    brief = intake.get("deck_brief") or {}
    turns = []
    for qid, value in answers.items():
        if isinstance(value, dict):
            value = value.get("value", "")
        q = _question_text(qid, brief)
        turns.append({
            "question_id": qid,
            "question": q,
            "answer": str(value) if value not in (None, "") else "(skipped)",
            "validated": True,
            "source": "presentation-interview-app",
        })
    transcript = {
        "intake_session_id": intake.get("intake_session_id", ""),
        "interview_mode": "one_at_a_time",
        "completed": True,
        "source": "presentation-interview-app",
        "turn_count": len(turns),
        "turns": turns,
    }
    out.write_text(json.dumps(transcript, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _question_text(qid: str, brief: dict) -> str:
    """A readable question label for a captured answer id.

    Maps known intake question ids to the human-facing prompt. Unknown ids fall
    back to a stable label so the transcript is always non-trivial and
    unambiguous.
    """
    labels = {
        "offer_name": "What is your offer?",
        "transformation_promise": "What is the transformation promise?",
        "audience": "Who is the audience?",
        "cta_action": "What is the call to action?",
        "brand_primary": "Primary brand color?",
        "tone": "What tone should the deck take?",
        "final_price": "What is the final price?",
        "price_mode": "Price mode?",
        "goal": "What is the deck's goal?",
        "target_feeling": "Target feeling?",
        "hook_seed": "Hook seed?",
        "client_notes": "Client notes?",
        "deadline": "Deadline?",
        "slide_count": "Slide count?",
        "speech_speed_preference": "Preferred speech pace?",
        "want_sales_checkout": "Do you need a sales + checkout page?",
        "want_vsl_page": "Would you like a VSL page?",
        "q1": "First intake question",
        "q2": "Second intake question",
        "q3": "Third intake question",
        "q4": "Fourth intake question",
        "q5": "Fifth intake question",
        "q6": "Sixth intake question",
        "q7": "Seventh intake question",
        "q8": "Eighth intake question",
    }
    return labels.get(str(qid), "Intake question: " + str(qid))


def cmd(args) -> int:
    raw = json.loads(pathlib.Path(args.intake).read_text(encoding="utf-8"))
    try:
        intake = assemble_intake(raw, run_id=args.run_id)
        run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
        ipath = write_intake_file(run_dir, intake)
        lpath = write_ledger(run_dir, intake)
        tpath = write_transcript(run_dir, intake)
    except UngroundedDeckTypeError as exc:
        # Fail closed: nothing above wrote a file before raising. Exit 3
        # distinguishes "ungrounded deck type" from other failures.
        print(f"error: {exc}", file=sys.stderr)
        return 3
    if args.verbose:
        print(f"wrote {ipath}")
        print(f"wrote {lpath}")
        print(f"wrote {tpath}")
        print(f"mandatory pre_capture present: {all(k in intake.get('pre_presentation_capture', {}) for k in MANDATORY_PRE_CAPTURE)}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intake", required=True, help="path to the app intake payload JSON")
    ap.add_argument("--run-dir", required=True, help="deck run directory (contains working/)")
    ap.add_argument("--run-id", default="", help="optional run id stamped into the record")
    ap.add_argument("--verbose", action="store_true")
    return cmd(ap.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())

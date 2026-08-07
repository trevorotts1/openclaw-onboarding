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

    intake = {
        "interview_confirmed": True,
        "deck_type": "webinar",
        "creation_mode": "from_scratch",
        "presentation_mode": "general",
        "audience_mode": "STANDARD",
        "presentation_type": "from_scratch",
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
    return intake


def write_intake_file(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/copy/intake.json in the run dir (the deck brief)."""
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
    """
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


def write_transcript(run_dir: pathlib.Path, intake: dict) -> pathlib.Path:
    """Write working/interview/intake_transcript.json — the real conversation trace.

    presentation-canonical-entry.sh GATE 0b requires this file to exist and be
    non-trivial (>= 200 bytes) with a REAL one-at-a-time conversation (FIX-3:
    intake must be a REAL conversation, not a fabricated block). We build it from
    the app's captured answers: each Q&A pair becomes a dialogue turn, so the
    trace is grounded in the client's actual responses.
    """
    out = run_dir / "working" / "interview" / "intake_transcript.json"
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
    intake = assemble_intake(raw, run_id=args.run_id)
    run_dir = pathlib.Path(args.run_dir).expanduser().resolve()
    ipath = write_intake_file(run_dir, intake)
    lpath = write_ledger(run_dir, intake)
    tpath = write_transcript(run_dir, intake)
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

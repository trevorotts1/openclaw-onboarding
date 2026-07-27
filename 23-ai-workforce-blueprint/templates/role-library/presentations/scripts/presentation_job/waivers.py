from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gates import GATE_KEYS, NON_WAIVABLE_GATES, TRANSCRIPT_WAIVERS_ACCEPTED
from .state import _norm, _read_json

# ---------------------------------------------------------------------------
# Waivers. The only bypass, and it must not be self-issuable.
# ---------------------------------------------------------------------------
class WaiverError(Exception):
    pass


def load_waivers(run_dir: Path) -> List[Dict[str, Any]]:
    p = run_dir / "waivers.json"
    if not p.is_file():
        return []
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WaiverError(f"waivers.json is unreadable: {exc}")
    result = obj if isinstance(obj, list) else [obj]
    # Reject duplicate rules: one gate, one waiver.
    seen: set = set()
    for w in result:
        rule = w.get("rule")
        if rule in seen:
            raise WaiverError(f"two waivers name the same gate {rule!r}; one gate, one waiver")
        seen.add(rule)
    return result


def validate_waiver(w: Dict[str, Any], run_dir: Path) -> None:
    """
    A waiver must be traceable to the CLIENT, not to the agent that wants the skip.

    v1 of the plan required matching the quote against "the recorded conversation", which is not
    implementable for a Telegram-routed request (route-presentation.sh:101-107 sends five keys and
    no requester identity). So the accepted evidence is, in order of strength:
      1. intake_field  — a form field the client set (strongest; the form is the consent record)
      2. transcript    — a verbatim quote found in working/interview/intake_transcript.json,
                         which is written turn-by-turn by deck-intake-driver.py:1273-1298, a
                         DIFFERENT producer than the build being certified
    An empty, unquoted, or unsourced waiver is invalid. See the plan's D3 for the eight hardening
    changes still needed before a transcript quote is consent-grade.
    """
    rule = w.get("rule")
    if rule not in GATE_KEYS:
        raise WaiverError(f"waiver names {rule!r}, which is not a waivable gate. "
                          f"Waivable: {', '.join(GATE_KEYS)}. "
                          f"Never waivable: {', '.join(NON_WAIVABLE_GATES)}")
    # The NON_WAIVABLE_GATES branch below was removed as dead code because GATE_KEYS already
    # excludes the non-waivable set. The assertion at import time in gates.py guarantees that
    # a future edit adding ocr_readback to GATE_KEYS does not silently make it waivable.
    src = w.get("source")
    if src not in ("intake_field", "transcript"):
        raise WaiverError(f"waiver for {rule!r} has source={src!r}; must be "
                          "'intake_field' or 'transcript'")
    quote = (w.get("client_request_quote") or "").strip()
    if len(quote) < 3:
        raise WaiverError(f"waiver for {rule!r} carries no client_request_quote — "
                          "a waiver the agent wrote for itself is not a waiver")
    if not w.get("captured_at"):
        raise WaiverError(f"waiver for {rule!r} has no captured_at timestamp")

    if src == "intake_field":
        intake = _read_json(run_dir / "working" / "copy" / "intake.json") or {}
        field_name = w.get("intake_field")
        if not field_name or field_name not in intake:
            raise WaiverError(f"waiver for {rule!r} cites intake field {field_name!r}, "
                              "which is not present in intake.json")
        return

    # transcript source
    if not TRANSCRIPT_WAIVERS_ACCEPTED:
        raise WaiverError(
            f"waiver for {rule!r} cites source='transcript'. Transcript-sourced waivers are "
            "NOT YET ACCEPTED. The audit's D3 (:1016-1019) records that a Telegram-routed "
            "request sends five keys and no requester identity, and the ceo-chat transcript "
            "lives in the Command Center database — which violates the offline-authoritative "
            "rule (the engine cannot read it from the run dir). Until that identity gap closes, "
            "the only accepted waiver source is 'intake_field' — a form field the client set, "
            "where the form is the consent record. Use an intake field waiver instead, or set "
            "TRANSCRIPT_WAIVERS_ACCEPTED to True after the identity gap is closed.")

    tp = run_dir / "working" / "interview" / "intake_transcript.json"
    if not tp.is_file():
        raise WaiverError(f"waiver for {rule!r} cites the transcript, but "
                          "working/interview/intake_transcript.json does not exist. "
                          "An absent transcript is not proof of client consent.")
    try:
        turns = json.loads(tp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WaiverError(f"transcript unreadable: {exc}")
    owner_text = " ".join(
        (t.get("text") or "") for t in turns
        if isinstance(t, dict) and (t.get("role") or "").lower() in ("owner", "user", "client"))
    if _norm(quote) not in _norm(owner_text):
        raise WaiverError(
            f"waiver for {rule!r} quotes text that does not appear in any client turn of the "
            "recorded transcript. The quote must be the client's own words.")


def _waiver_schema_message() -> str:
    """Produce the standard schema reminder for rejected waivers."""
    return (
        "A valid waiver must match this schema:\n"
        '  {\n'
        '    "rule": "gate-key",\n'
        '    "source": "intake_field",\n'
        '    "client_request_quote": "the client\'s own words (min 3 chars)",\n'
        '    "intake_field": "field_name_in_intake.json",\n'
        '    "captured_at": "ISO-8601 timestamp",\n'
        '    "captured_from": "where the consent was recorded"\n'
        '  }\n'
        "Waivable gates: " + ", ".join(GATE_KEYS) + "\n"
        "Never waivable: " + ", ".join(NON_WAIVABLE_GATES) + "\n"
        "Resume after fixing waivers.json:\n"
        "  python3 presentation_job.py --close --run-dir <run_dir>"
    )


def print_waiver_error(exc: WaiverError, run_dir: Optional[Path] = None) -> None:
    """Print a readable waiver rejection to stderr and exit 9."""
    print("\n" + "=" * 72, file=sys.stderr)
    print("WAIVER REJECTED — the waiver is invalid and cannot authorise a gate skip.",
          file=sys.stderr)
    print(f"  reason: {exc}", file=sys.stderr)
    print(file=sys.stderr)
    print(_waiver_schema_message(), file=sys.stderr)
    print("=" * 72 + "\n", file=sys.stderr)

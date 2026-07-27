from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gates import GATE_KEYS, NON_WAIVABLE_GATES
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
    return obj if isinstance(obj, list) else [obj]



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
    if rule in NON_WAIVABLE_GATES:
        raise WaiverError(f"gate {rule!r} cannot be waived")
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




from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gates import GATE_KEYS, NON_WAIVABLE_GATES
from .state import _norm, _read_json

assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES)), "a non-waivable gate appears in GATE_KEYS"

TRANSCRIPT_WAIVERS_ACCEPTED: bool = False

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
    waivers = obj if isinstance(obj, list) else [obj]
    seen = set()
    for w in waivers:
        if not isinstance(w, dict):
            raise WaiverError(f"waivers.json: expected an object, got {type(w).__name__}: {w!r}")
        rule = w.get("rule")
        if rule in seen:
            raise WaiverError(f"two waivers name the same gate {rule!r}; one gate, one waiver")
        seen.add(rule)
    return waivers

def validate_waiver(w: Dict[str, Any], run_dir: Path) -> None:
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

    if not TRANSCRIPT_WAIVERS_ACCEPTED:
        raise WaiverError(
            f"waiver for {rule!r} is transcript-sourced, but TRANSCRIPT_WAIVERS_ACCEPTED "
            "is False. Transcript waivers are not yet consent-grade: the route script "
            "sends five keys and no requester identity, and the chat transcript lives in "
            "a database which breaks the offline-authoritative rule (audit D3:1016-1019). "
            "Set TRANSCRIPT_WAIVERS_ACCEPTED = True only after the identity gap closes "
            "and the transcript is in the run dir.")

    tp = run_dir / "working" / "interview" / "intake_transcript.json"
    if not tp.is_file():
        raise WaiverError(f"waiver for {rule!r} cites the transcript, but "
                          "working/interview/intake_transcript.json does not exist.")
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

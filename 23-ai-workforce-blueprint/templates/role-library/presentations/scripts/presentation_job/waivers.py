from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gates import GATE_KEYS, NON_WAIVABLE_GATES
from .state import _norm, _read_json

assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES)), "a non-waivable gate appears in GATE_KEYS"

# DECISION (self-issuable-waiver fix, see CHANGELOG [Unreleased]):
# The intake_field path below (src == "intake_field") now requires
# client_request_quote to be a genuine substring of the value already
# recorded at that key in intake.json. That closes the hole where any
# agent could write itself a waiver merely by naming a field that
# exists, with no check that the client ever said the quoted words.
#
# TRANSCRIPT_WAIVERS_ACCEPTED stays False. The substring match against
# recorded client turns further down in this file is correct and is not
# why the flag is off. It stays off because of two problems that are
# independent of quote verification and are NOT fixed by this change:
#   1. No requester identity: the route script that produces the
#      transcript sends five keys and no identity for who is speaking.
#   2. Storage: the transcript lives in a database, which breaks the
#      offline-authoritative rule (audit D3:1016-1019) that this job's
#      state must be reconstructable from the run directory alone.
# Flip this only after both are closed and the transcript file is
# written into the run dir -- not as a side effect of unrelated waiver
# work such as this fix.
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
        field_value = intake.get(field_name)
        if not isinstance(field_value, str):
            raise WaiverError(
                f"waiver for {rule!r} cites intake field {field_name!r}, but that field's "
                f"value is not text (got {type(field_value).__name__}), so the client's "
                "quote cannot be checked against it. A waivable intake field must hold the "
                "client's own written words.")
        if _norm(quote) not in _norm(field_value):
            raise WaiverError(
                f"waiver for {rule!r} quotes text that does not appear in intake field "
                f"{field_name!r}. Recorded value of {field_name!r} does not contain the "
                "quoted words -- the quote must be the client's own words as recorded in "
                "intake.json, not text the agent supplied.")
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
        loaded = json.loads(tp.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise WaiverError(f"transcript unreadable: {exc}")
    # FIX-3: the driver writes a SIGNED ENVELOPE ({"format": ..., "turns": [...]});
    # legacy bare-list transcripts are still accepted here (waivers read the text,
    # they do not gate conversation provenance — the P-SP-INTAKE-TRACE preflight does).
    if isinstance(loaded, dict) and isinstance(loaded.get("turns"), list):
        turns = loaded["turns"]
    elif isinstance(loaded, list):
        turns = loaded
    else:
        raise WaiverError(f"transcript at {tp} is neither a bare turn list nor a "
                          "driver envelope with a turns array.")
    owner_text = " ".join(
        (t.get("text") or "") for t in turns
        if isinstance(t, dict) and (t.get("role") or "").lower() in ("owner", "user", "client"))
    if _norm(quote) not in _norm(owner_text):
        raise WaiverError(
            f"waiver for {rule!r} quotes text that does not appear in any client turn of the "
            "recorded transcript. The quote must be the client's own words.")

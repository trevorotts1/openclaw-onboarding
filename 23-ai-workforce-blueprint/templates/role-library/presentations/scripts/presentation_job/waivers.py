from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from .gates import GATE_KEYS, NON_WAIVABLE_GATES
from .state import _norm, _read_json

# MASTER Part 8 Fix 32: an owner-skip approval claimed by a waiver record is
# verified through the shared approvals.verify() oracle (cc_board owner-message
# resolution), not taken on the strength of its own fields. Import is deferred
# into validate_waiver() so a bare-module import of waivers.py keeps working.

assert not (set(GATE_KEYS) & set(NON_WAIVABLE_GATES)), "a non-waivable gate appears in GATE_KEYS"

# PD-202: which intake fields may speak for which gate. Filled ONLY from
# questions in intake/deck-intake-questions.json (the question bank) that offer
# the client the choice to skip that deliverable, plus the verbatim-decline
# follow-up that captures the client's own words:
#
#   teleprompter -> "teleprompter_declined_reason"  (bank order 22.01)
#   script       -> "speech_script_declined_reason" (bank order 22.02)
#   ghl_upload   -> "ghl_upload_declined_reason"    (bank order 22.03)
#
# Each reason question is conditional_on the matching want_* toggle answering
# "no" (the toggles ride core_deliverables and delivery_and_ghl), so the value
# recorded there is the client's own reason for skipping that deliverable --
# exactly the fact a waiver for that gate has to prove.
#
# prompt_floor and qc have NO such question, so their lists are empty and they
# cannot be waived from an intake field at all. The bank's own
# waiver_field_mapping says so outright: "prompt_floor and qc are deliberately
# ABSENT -- a client cannot consent to a thinner prompt or a lower quality bar;
# those are craft floors, not options."
WAIVER_INTAKE_FIELDS: Dict[str, tuple] = {
    "script": ("speech_script_declined_reason",),
    "teleprompter": ("teleprompter_declined_reason",),
    "ghl_upload": ("ghl_upload_declined_reason",),
    "prompt_floor": (),
    "qc": (),
}
assert set(WAIVER_INTAKE_FIELDS) <= set(GATE_KEYS), (
    "WAIVER_INTAKE_FIELDS names a gate that is not in GATE_KEYS -- it could never be reached")
assert not (set(WAIVER_INTAKE_FIELDS) & set(NON_WAIVABLE_GATES)), (
    "a non-waivable gate carries intake fields")

# A client's request has to be a sentence about the gate, not a stray word:
# "the" is 3 characters and one word, and it is not a request about anything.
WAIVER_QUOTE_MIN_CHARS = 20
WAIVER_QUOTE_MIN_WORDS = 4


def _parses_as_datetime(value: Any) -> bool:
    """True when `value` is text the standard library reads as a date AND a time.

    A waiver's captured_at is the moment the client said the quoted words; a
    date with no time of day, or a string no parser recognizes, is not evidence
    of when anything was said. A trailing Z is accepted as UTC.
    """
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text or ":" not in text:  # no time of day -> not a date AND time
        return False
    if text[-1] in ("Z", "z"):
        text = text[:-1] + "+00:00"
    try:
        datetime.fromisoformat(text)
        return True
    except ValueError:
        return False


# DECISION (self-issuable-waiver fix, see CHANGELOG [Unreleased]; extended by
# PD-202, "a closing waiver must be a real request about that gate"):
# The intake_field path below (src == "intake_field") is a CONSENT record, not
# a note the agent can write for itself. Four checks, in this order:
#   1. client_request_quote is present, and once normalized
#      (_norm: lower-cased, whitespace-collapsed) it is at least
#      WAIVER_QUOTE_MIN_CHARS (20) characters AND at least
#      WAIVER_QUOTE_MIN_WORDS (4) words. A stray "the" is not a request.
#   2. captured_at parses as a date AND a time (_parses_as_datetime). An
#      unparseable stamp is not evidence of when the client said anything.
#   3. the cited intake_field is one the question bank offers for THAT gate
#      (WAIVER_INTAKE_FIELDS). A client can only decline what the interview
#      actually asked about, so a gate with no such question cannot be waived
#      from an intake field at all.
#   4. the quote is a genuine substring of the value recorded at that field
#      (case- and whitespace-insensitive), so the words really are the
#      client's own.
# Together these close the hole where any agent could write itself a waiver
# merely by naming a field that exists, with no check that the client ever
# said the quoted words about the thing being waived.
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

    # MASTER Part 8 Fix 32: a waiver that claims owner authority — an approved_by
    # name and no client-voice quote (the {approved_by:"Trevor", no
    # owner_msg_id} shape QC FIX 32 calls the forged record) — is an owner-skip
    # approval and MUST verify against the shared approvals oracle before
    # anything else about it is honored. Presence of "Trevor" in approved_by is
    # never proof. Fail-closed: a forged/unresolvable record raises
    # WaiverError with the AF-FORGED-APPROVAL reason; a record whose
    # owner_msg_id resolves to a real owner message (stub-oracle proof) passes.
    # Field mapping onto the approvals schema: the waiver's `rule` names the
    # gate, and its `captured_at` is the grant timestamp.
    claimed_owner = str(w.get("approved_by", "") or "").strip()
    if claimed_owner and not (w.get("client_request_quote") or "").strip():
        from .approvals import verify as _approvals_verify
        approval_record = dict(w, gate=rule, granted_at=w.get("captured_at"))
        try:
            _approvals_verify(approval_record, Path(run_dir))
        except Exception as exc:  # noqa: BLE001 — verify raises ApprovalError;
            # any other failure from the oracle path is still fail-closed.
            raise WaiverError(
                f"waiver for {rule!r} claims owner approval by {claimed_owner!r} "
                f"but could not be verified — {exc}") from exc
        # The owner_msg_id RESOLVED (stub-oracle proof / real board): this is a
        # genuine owner-authorized skip, honored without a client-voice quote —
        # the quote path below is for client-sourced waivers only (Fix 32 half B:
        # the verified-id record must be ACCEPTED, not fall through to the quote
        # check and fail).
        return

    src = w.get("source")
    if src not in ("intake_field", "transcript"):
        raise WaiverError(f"waiver for {rule!r} has source={src!r}; must be "
                          "'intake_field' or 'transcript'")
    quote = (w.get("client_request_quote") or "").strip()
    if not quote:
        raise WaiverError(f"waiver for {rule!r} carries no client_request_quote — "
                          "a waiver the agent wrote for itself is not a waiver")
    if not w.get("captured_at"):
        raise WaiverError(f"waiver for {rule!r} has no captured_at timestamp")
    if not _parses_as_datetime(w.get("captured_at")):
        raise WaiverError(
            f"waiver for {rule!r} has captured_at {w.get('captured_at')!r}, which is "
            "not a date and time (for example 2026-01-01T00:00:00Z). The stamp is the "
            "evidence of when the client said the quoted words; unparseable text is "
            "not evidence.")
    normalized = _norm(quote)
    words = normalized.split()
    if len(normalized) < WAIVER_QUOTE_MIN_CHARS or len(words) < WAIVER_QUOTE_MIN_WORDS:
        raise WaiverError(
            f"waiver for {rule!r} carries no client_request_quote long enough to be a "
            f"request about that gate: {len(normalized)} character(s), {len(words)} "
            f"word(s), and at least {WAIVER_QUOTE_MIN_CHARS} characters and "
            f"{WAIVER_QUOTE_MIN_WORDS} words are required. A stray word is not a "
            "request to close a gate.")

    if src == "intake_field":
        allowed = WAIVER_INTAKE_FIELDS.get(rule) or ()
        field_name = w.get("intake_field")
        if not allowed:
            raise WaiverError(
                f"waiver for {rule!r} cannot be waived from an intake field: the "
                "interview asks the client no question that declines it, so there is "
                "no client answer to quote. Gates a client can decline in the "
                "interview: "
                + ", ".join(sorted(g for g, fields in WAIVER_INTAKE_FIELDS.items() if fields))
                + ". This gate needs a real operator record, not a typed waiver.")
        if not field_name or str(field_name) not in allowed:
            raise WaiverError(
                f"waiver for {rule!r} cites intake field {field_name!r}, which is not "
                f"a field that can waive {rule!r}. A waiver for {rule!r} may cite only "
                "the field the client answered to decline it: "
                f"{', '.join(allowed)}. Naming some other field — or a field that "
                "merely exists in intake.json — is not a request about this gate.")
        intake = _read_json(run_dir / "working" / "copy" / "intake.json") or {}
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

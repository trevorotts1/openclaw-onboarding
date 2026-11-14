"""presentation_job.approvals — THE ONE owner-approval validator (FIX 32).

MASTER Part 8 Fix 32 — "No agent may mint an approval."

PROBLEM (from the September audit): an owner-skip approval written in Trevor's
name by the driver was consumed 27 times; three validators at three strictness
levels meant one file rejected what another honoured. WHAT: one validator,
owner message id required.

THE SCHEMA (one contract, every consumer):

    {
      "gate":         "<AF code or phase_id the approval waives>",  # required
      "approved_by":  "<who>"                                      # required, non-empty
      "owner_msg_id": "<id of the owner-authored CC message>",     # REQUIRED
      "reason":       ">= 8 chars",                                # required
      "granted_at":   "tz-aware ISO-8601, never T00:00:00"         # required
    }

`owner_msg_id` is REQUIRED on every approval. A record with only an
`owner_action` string (or no owner reference at all) is the exact self-forgery
vector the live E2E used — it is rejected here, everywhere, with
`AF-FORGED-APPROVAL`.

`verify(approval, run_dir)` resolves `owner_msg_id` through the authoritative
owner oracle — `cc_board` GET /api/tasks/{id}/messages/owner-ids (or the
gateway's owner oracle when the board is disabled) — and the id must RESOLVE to
a real owner-authored message. Presence of a string is never proof. An
unresolvable or UNDETERMINED oracle DENIES the approval: undetermined never
opens the gate.

Every consumer calls THIS module:

  * build_deck._owner_skip_evaluate        (build_deck preflight / gate battery)
  * canonical_render_guard.load_owner_skip_approvals
  * run_signature_deck.load_skip_approvals
  * phase_verifiers waiver path            (owner_skip_approval_authorizes)
  * presentation_job.waivers
  * prove-deck.py                          (_is_valid_skip_approval)

The QC FIX-32 proof: a hand-written `owner_skip_approval` with
`approved_by: "Trevor"` and NO `owner_msg_id` is rejected by all four call
paths with `AF-FORGED-APPROVAL`; the same record with a verified id is
accepted by all four (stub oracle).
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Shared constants — exact strings, do not rename.
# ---------------------------------------------------------------------------
AF_FORGED_APPROVAL = "AF-FORGED-APPROVAL"

# Mirror of run_signature_deck._SELF_GRANT_MARKERS / prove-deck
# _SELF_GRANT_MARKERS: the producing agent may never approve its own skip.
# PD-305 item (5): these match WHOLE WORDS. A substring test refused the honest
# "Herself Ordóñez" (contains "self") while letting a crafted "se lf" through;
# whole tokens refuse the marker and only the marker.
SELF_GRANT_MARKERS: Tuple[str, ...] = (
    "executive strategy", "via", "directive", "auto-approved",
    "self", "auto_approved", "producing", "builder",
)

REASON_MIN_CHARS = 8

#: Whole-token regex edges, shared by every "does this text name X" check
#: (the gate name in an owner message, the self-grant markers in approved_by).
_GATE_TOKEN_BEFORE = r"(?<![A-Za-z0-9_-])"
_GATE_TOKEN_AFTER = r"(?![A-Za-z0-9_-])"

#: PD-305 item (2): one owner message approves ONE gate. Every accepted
#: (owner_msg_id, gate) pair is recorded here; a second gate on the same id is
#: refused. Relative to the run dir, beside the other checkpoints.
APPROVALS_USED_REL = Path("working") / "checkpoints" / "approvals_used.json"
APPROVALS_USED_WRITE_FAILED = "approvals_used.write_failed"
APPROVALS_USED_REUSED = "approvals_used.reused_for_second_gate"

_ISO_TZ_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


class ApprovalError(Exception):
    """An owner approval is malformed, self-forged, or unverifiable.

    `str(exc)` always begins with the exact code `AF-FORGED-APPROVAL` for the
    forgery shapes (schema violations name the missing field inside the same
    prefixed message) so every consumer's failure output carries the code the
    QC battery matches on."""


# ---------------------------------------------------------------------------
# Message text — resolve an owner message id to the message the client sent.
# ---------------------------------------------------------------------------
# Why this exists: the owner-ids oracle above proves an id is REAL, but an
# approval also has to be checked against WHAT the owner wrote (PD-305). That
# needs the message text, and today's endpoint returns ids only.
RESOLVE_BOARD_HAS_NO_TEXT = "resolve.board_has_no_text"
RESOLVE_NO_TEXT_SOURCE = "resolve.no_text_source"

#: Where a channel bridge drops inbound owner messages, one JSON object per
#: line: {"msg_id", "chat_id", "text", "received_at"}. This module only READS
#: it; nothing in this repository writes it (the writer belongs to the OpenClaw
#: channel layer).
INBOUND_MESSAGES_REL = Path("working") / "interview" / "inbound_messages.jsonl"

#: The board text source. Nothing wires it until PD-305b (the Command Center
#: read endpoint that returns text) and PD-305 (the text-aware oracle) land;
#: while it is None the board can supply ids only, never text. A wired value is
#: a callable ``(owner_msg_id, run_dir) -> dict | None`` returning one message
#: row; setting it is how a caller or a test supplies a real board.
BOARD_TEXT_RESOLVER: Optional[Any] = None


def _log_reason(reason: str) -> None:
    """Log one resolver reason on stderr. Never fatal, never silent."""
    print(f"[approvals] {reason}", file=sys.stderr, flush=True)


def _self_grant_marker(approved_by: str) -> Optional[str]:
    """The first self-grant marker `approved_by` names as a WHOLE WORD, or None.

    PD-305 item (5): markers match whole words. `"executive strategy"` is a
    two-word phrase and still matches on word boundaries at both ends; `"via"`
    only matches the standalone word, so an honest surname or an address that
    merely contains those letters is never refused."""
    hay = str(approved_by or "")
    for marker in SELF_GRANT_MARKERS:
        pattern = _GATE_TOKEN_BEFORE + re.escape(marker) + _GATE_TOKEN_AFTER
        if re.search(pattern, hay, re.IGNORECASE) is not None:
            return marker
    return None


# ---------------------------------------------------------------------------
# approvals_used.json — one owner message approves ONE gate (PD-305 item 2).
# ---------------------------------------------------------------------------
# Why a file and not memory: the same message id reused on a second gate is a
# forgery shape that survives restarts, retries and a fresh engine process, so
# the record has to be on disk beside the other checkpoints. READ fail-closed:
# an unreadable ledger refuses the approval rather than silently forgetting
# what was already consumed.
def _approvals_used_path(run_dir: Path) -> Path:
    return Path(run_dir) / APPROVALS_USED_REL


def _read_approvals_used(run_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Read the used-approvals ledger. Returns {} when the run has none yet
    (first approval), a dict on success, and None when the file exists but
    cannot be read or parsed — None is UNDETERMINED and refuses the approval."""
    if run_dir is None:
        return {}
    path = _approvals_used_path(Path(run_dir))
    if not path.is_file():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        _log_reason(APPROVALS_USED_WRITE_FAILED)
        return None
    if not isinstance(obj, dict):
        _log_reason(APPROVALS_USED_WRITE_FAILED)
        return None
    uses = obj.get("uses")
    if uses is None:
        return {"uses": {}}
    if not isinstance(uses, dict):
        _log_reason(APPROVALS_USED_WRITE_FAILED)
        return None
    return {"uses": uses}


def _record_approval_used(run_dir: Optional[Path], owner_msg_id: str,
                          gate: str) -> bool:
    """Record `(owner_msg_id, gate)` as consumed. Returns False when the ledger
    cannot be written — the caller then REFUSES the approval, because an
    approval whose consumption cannot be recorded could be replayed forever."""
    if run_dir is None:
        return False
    path = _approvals_used_path(Path(run_dir))
    ledger = _read_approvals_used(run_dir)
    if ledger is None:
        return False
    uses = ledger.setdefault("uses", {})
    uses[str(owner_msg_id)] = str(gate)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(ledger, indent=2, sort_keys=True) + "\n",
                       encoding="utf-8")
        tmp.replace(path)
    except OSError:
        _log_reason(APPROVALS_USED_WRITE_FAILED)
        return False
    return True


def check_approval_not_reused(run_dir: Optional[Path], owner_msg_id: str,
                              gate: str) -> None:
    """Raise ApprovalError when `owner_msg_id` was already consumed for a
    DIFFERENT gate. Re-asserting the SAME gate is idempotent and allowed, so a
    retry of an already-accepted approval is not a forgery."""
    mid = str(owner_msg_id or "").strip()
    want = str(gate or "").strip()
    if not mid:
        return
    ledger = _read_approvals_used(run_dir)
    if ledger is None:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {want!r} references "
            f"owner_msg_id {mid!r}, but the used-approvals ledger for this run "
            f"cannot be read ({APPROVALS_USED_REL.as_posix()}). An approval whose "
            "consumption cannot be proven is not consumed — DENIED.")
    used_for = (ledger.get("uses") or {}).get(mid)
    if used_for is not None and str(used_for).strip() != want:
        _log_reason(APPROVALS_USED_REUSED)
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: owner_msg_id {mid!r} already approved gate "
            f"{str(used_for)!r}; it may not also approve {want!r}. One owner "
            "message approves one gate — reusing a message for a second gate is "
            "a forgery shape and is DENIED.")


def _message_row(obj: Any) -> Optional[Dict[str, Any]]:
    """Project one inbound-message object to the resolver's four-key row, or
    None when it is not a usable message. A row WITHOUT text is never returned:
    an id with no text proves nothing about what the owner approved."""
    if not isinstance(obj, dict):
        return None
    msg_id = str(obj.get("msg_id") or "").strip()
    text = obj.get("text")
    if not msg_id or not isinstance(text, str) or not text.strip():
        return None
    return {
        "msg_id": msg_id,
        "chat_id": str(obj.get("chat_id") or "").strip(),
        "text": text,
        "received_at": str(obj.get("received_at") or "").strip(),
    }


def _default_board_text_resolver(owner_msg_id: str,
                                 run_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Ask the CC board for this message's text through the SAME oracle route
    the authenticity check uses (PD-305 clause B). Returns a message row when
    the board supplies text for the id, else None.

    `cc_board.list_owner_message_ids` returns `{id: text}` once PD-305b's read
    endpoint is deployed, and a frozenset of ids when the board can only supply
    ids. An ids-only answer is UNDETERMINED here — an id is not text — so this
    returns None and the approval is refused by the caller."""
    task_id = resolve_cc_task_id(run_dir)
    if not task_id:
        return None
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import cc_board  # noqa: PLC0415
        resolved = cc_board.list_owner_message_ids(task_id, env=None)
    except Exception:  # noqa: BLE001 — an unreachable board is "no text here"
        return None
    if not isinstance(resolved, dict):
        return None
    text = resolved.get(owner_msg_id)
    if not isinstance(text, str) or not text.strip():
        return None
    return {"msg_id": owner_msg_id, "chat_id": "", "text": text,
            "received_at": ""}


def _board_row(owner_msg_id: str, run_dir: Optional[Path],
               resolved: Any = None) -> Optional[Dict[str, Any]]:
    """This message's text from the board. None when the board is unwired, has
    no text for the id, or fails — the caller continues to the next source.
    Never raises.

    `resolved` is an oracle answer the caller already fetched (PD-305 clause B
    keeps ONE request per approval): a `{id: text}` mapping carries text, a
    frozenset is the ids-only answer and therefore no text. Without it, the
    wired resolver — or the default board resolver — is asked."""
    if resolved is not None and not isinstance(resolved, dict):
        # ids-only oracle answer: an id is not text, so there is nothing here.
        _log_reason(RESOLVE_BOARD_HAS_NO_TEXT)
        return None
    if isinstance(resolved, dict):
        text = resolved.get(owner_msg_id)
        if not isinstance(text, str) or not text.strip():
            _log_reason(RESOLVE_BOARD_HAS_NO_TEXT)
            return None
        return {"msg_id": owner_msg_id, "chat_id": "", "text": text,
                "received_at": ""}
    resolver = BOARD_TEXT_RESOLVER or _default_board_text_resolver
    try:
        row = _message_row(resolver(owner_msg_id, run_dir))
    except Exception:  # noqa: BLE001 — a board failure is "no text here"
        row = None
    # ponytail: id match keeps a confused board from attaching another
    # message's text; full provenance pinning arrives with PD-305b.
    if row is not None and row["msg_id"] == owner_msg_id:
        return row
    _log_reason(RESOLVE_BOARD_HAS_NO_TEXT)
    return None


def _file_row(owner_msg_id: str, run_dir: Optional[Path]) -> Optional[Dict[str, Any]]:
    """Look the id up in <RUN_DIR>/working/interview/inbound_messages.jsonl.
    Malformed lines are skipped, never fatal. Never writes the file."""
    if run_dir is None:
        return None
    path = Path(run_dir) / INBOUND_MESSAGES_REL
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                row = _message_row(obj)
                if row is not None and row["msg_id"] == owner_msg_id:
                    return row
    except OSError:  # absent file is an expected state, not an error
        return None
    return None


def resolve_owner_message(owner_msg_id: str,
                          run_dir: Optional[Path] = None,
                          *, resolved: Any = None) -> Optional[Dict[str, Any]]:
    """Resolve `owner_msg_id` to the message the client really sent.

    Returns ``{"msg_id", "chat_id", "text", "received_at"}`` for a real inbound
    owner message, else None. Sources, in order:

      1. the board, when it can return message TEXT for the run's task (it
         arrives with PD-305b and PD-305; until then it logs
         `resolve.board_has_no_text` and supplies nothing);
      2. ``<RUN_DIR>/working/interview/inbound_messages.jsonl``, when a channel
         bridge has written it.

    Never writes the fixture file, never returns a row without text, and logs
    `resolve.no_text_source` with a None return when neither source can supply
    text. The chat id is returned as it really is — a message from another chat
    is reported, not filtered; the caller decides what that means."""
    mid = str(owner_msg_id or "").strip()
    if not mid:
        _log_reason(RESOLVE_NO_TEXT_SOURCE)
        return None
    row = _board_row(mid, run_dir, resolved)
    if row is not None:
        return row
    row = _file_row(mid, run_dir)
    if row is not None:
        return row
    _log_reason(RESOLVE_NO_TEXT_SOURCE)
    return None


# ---------------------------------------------------------------------------
# PD-305 — the owner message must NAME the gate it approves.
# ---------------------------------------------------------------------------
# An id proves a message EXISTS. Only the message text proves WHAT the owner
# approved, so a consumer that acts on an approval for a named gate also
# requires that gate's name in the message. Both refusals below carry the
# AF-FORGED-APPROVAL code every consumer matches on, but say different things:
# "the id is real and its text could not be read" (the ids-only oracle shape
# that used to pass) is never reported as "the text approves something else".


def text_names_gate(text: str, gate: str) -> bool:
    """True when `text` contains `gate` as one whole, case-insensitive token.
    Hyphens stay inside the token, so 'P4-COPY' matches its own name and never
    a longer identifier that merely contains it."""
    want = str(gate or "").strip()
    if not want:
        return False
    pattern = _GATE_TOKEN_BEFORE + re.escape(want) + _GATE_TOKEN_AFTER
    return re.search(pattern, str(text or ""), re.IGNORECASE) is not None


def verify_with_gate_text(approval: Any, run_dir: Optional[Path] = None,
                          *, gate: str = "") -> Dict[str, Any]:
    """`verify()` plus PD-305: the owner message's TEXT must name the gate.

    Returns the verified approval. Raises ApprovalError (AF-FORGED-APPROVAL)
    when the id does not verify, when no text can be read for it (ids-only
    oracle / no inbound message log — the exact shape ids-only acceptance used
    to let through), or when the text does not name the gate. `gate` overrides
    the record's own gate for callers whose record carries the gate elsewhere.
    """
    approval = verify(approval, run_dir)
    want = str(gate or approval.get("gate") or approval.get("af_code")
               or approval.get("phase_id") or "").strip()
    owner_msg_id = str(approval.get("owner_msg_id") or "").strip()
    # One board answer per approval: when no resolver is wired, the oracle's own
    # reply is reused as the text source (it carries `{id: text}` once PD-305b's
    # endpoint is live, and a frozenset — no text — until then).
    resolved = None if BOARD_TEXT_RESOLVER is not None else \
        _cc_board_oracle(Path(run_dir) if run_dir is not None else None)
    row = resolve_owner_message(owner_msg_id, run_dir, resolved=resolved)
    if row is None:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {want!r} references "
            f"owner_msg_id {owner_msg_id!r}, which resolves to a real message "
            "but whose TEXT could not be read (ids-only oracle / no inbound "
            "message log). An id proves a message exists, never what the owner "
            "approved — DENIED.")
    if not text_names_gate(row.get("text") or "", want):
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: owner message {owner_msg_id!r} does not name "
            f"gate {want!r} (text={str(row.get('text'))[:80]!r}). The message "
            "must contain the gate name to be an approval for that gate — DENIED.")
    # PD-305 item (2): one owner message approves ONE gate, and the pairing is
    # recorded so a restart cannot forget what was already consumed.
    check_approval_not_reused(run_dir, owner_msg_id, want)
    if not _record_approval_used(run_dir, owner_msg_id, want):
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {want!r} on owner_msg_id "
            f"{owner_msg_id!r} is authentic, but its consumption could not be "
            f"recorded in {APPROVALS_USED_REL.as_posix()} — an approval whose "
            "consumption cannot be proven could be replayed forever, so it is "
            "DENIED.")
    return approval


# ---------------------------------------------------------------------------
# Schema validation (pure — no oracle, no I/O).
# ---------------------------------------------------------------------------
def _parse_granted_at(ts: str) -> Optional[datetime]:
    """Parse an ISO-8601 timestamp. Returns None for anything that is not a
    real, tz-aware datetime — rejects placeholders ('t', 'now', 'asap'),
    naive timestamps (no timezone), and midnight-exactly T00:00:00 (an
    automated/fabricated token). Accepts a trailing 'Z'."""
    s = (ts or "").strip()
    if not s:
        return None
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    if "T00:00:00" in s:
        return None  # midnight placeholder — a fabricated approval token
    if not _ISO_TZ_RE.search(s):
        return None  # no timezone designator — not a verifiable timestamp
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.tzinfo.utcoffset(dt) is None:
        return None
    return dt


def validate_schema(approval: Any, *, require_msg_id: bool = True) -> Dict[str, Any]:
    """Validate one approval record against the Fix 32 schema. Returns the
    record (as a dict) when it is well-formed; raises ApprovalError when not.
    Pure — no oracle call, no filesystem I/O."""
    if not isinstance(approval, dict):
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: an owner approval must be a JSON object, "
            f"got {type(approval).__name__}.")
    gate = str(approval.get("gate") or approval.get("af_code")
               or approval.get("phase_id") or "").strip()
    if not gate:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval record has no gate — an approval "
            "that names nothing authorizes nothing.")
    approved_by = str(approval.get("approved_by") or "").strip()
    if not approved_by:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} has an empty "
            "approved_by — a nameless approval is not an owner decision.")
    marker = _self_grant_marker(approved_by)
    if marker:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} names "
            f"approved_by {approved_by!r}, which contains the self-grant marker "
            f"{marker!r} — a producing agent may not approve its own skip.")
    reason = str(approval.get("reason") or "").strip()
    if len(reason) < REASON_MIN_CHARS:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} carries no real "
            f"justification (reason is {len(reason)} chars; {REASON_MIN_CHARS} "
            "required) — a placeholder token is not an owner decision.")
    if _parse_granted_at(str(approval.get("granted_at")
                             or approval.get("approved_at")
                             or approval.get("timestamp") or "")) is None:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} has no verifiable "
            "granted_at — the timestamp must be a real, timezone-aware ISO-8601 "
            "datetime and never the midnight placeholder T00:00:00.")
    owner_msg_id = str(approval.get("owner_msg_id") or "").strip()
    owner_action = str(approval.get("owner_action") or "").strip()
    if not owner_msg_id:
        if require_msg_id:
            raise ApprovalError(
                f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} (approved_by "
                f"{approved_by!r}) has NO owner_msg_id (owner_action={owner_action!r}). "
                "Every owner approval must carry a non-empty owner_msg_id that "
                "resolves to a real owner-authored message in Command Center "
                "task_activities — an owner_action string alone is never proof of "
                "an owner decision, and an approval without a resolvable message "
                "id is self-forged and DENIED.")
        return approval
    return approval


# ---------------------------------------------------------------------------
# The oracle — resolve owner_msg_id to a REAL owner-authored message.
# ---------------------------------------------------------------------------
def _resolve_owner_msg_ids_for_run(run_dir: Optional[Path]) -> Optional[frozenset]:
    """Compat alias (same oracle under the name run_signature_deck delegates to):
    resolve the run's CC task to its real owner-authored message ids via
    cc_board. Frozenset on success; None when UNDETERMINED — None NEVER opens
    the gate."""
    return _cc_board_oracle(Path(run_dir) if run_dir is not None else None)


def _gateway_owner_oracle(owner_msg_id: str) -> Optional[bool]:
    """Fallback oracle when the CC board is disabled: ask the OpenClaw gateway
    whether `owner_msg_id` is a real owner-authored message. Returns
    True/False on a definitive answer, None when undetermined (gateway
    unreachable, or the message could not be proven either way). Never
    raises."""
    gateway = (os.environ.get("OPENCLAW_GATEWAY_URL")
               or os.environ.get("GATEWAY_URL") or "").strip().rstrip("/")
    if not gateway:
        return None
    try:  # stdlib only — this module must import everywhere build_deck does
        import urllib.request
        from urllib import error as _err
        token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "").strip()
        url = gateway.rstrip("/") + "/tools/message/lookup?id=" \
            + urllib.parse.quote(str(owner_msg_id), safe="")
        req = urllib.request.Request(url)
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.getcode() != 200:
                return None
            import json as _json
            data = _json.loads(resp.read().decode("utf-8", "replace"))
        if isinstance(data, dict):
            # PD-305 item (4): only `is_owner: true` is proof. The old `role`
            # branch accepted "owner"/"user"/"client" as a string — a field the
            # message's own writer can set. A gateway that answers with a role
            # and no is_owner flag is UNDETERMINED, never an approval.
            if "is_owner" in data:
                return data.get("is_owner") is True
        return None
    except _err.HTTPError:
        return False  # a definitive "no such message" from the gateway
    except Exception:  # noqa: BLE001 — any transport failure is UNDETERMINED
        return None


#: PD-305 item (3): the engine's own state file, written by the run itself, is
#: the FIRST source of the CC task id. The manifest is the compatibility path.
STATE_JSON = Path("state.json")
TASK_ID_DISAGREEMENT = "task_id.sources_disagree"


def resolve_cc_task_id(run_dir: Optional[Path]) -> str:
    """The CC task id this run really belongs to, or "" when unknown.

    PD-305 item (3): `state.json` `board.task_id` is read FIRST — it is the
    engine's own live record — and `process_manifest.json` `cc_task_id` is used
    only when the two AGREE (or when only the manifest has a value, which is
    every run written before this change). When both are present and disagree,
    the task id is UNDETERMINED: approving against the wrong task's messages is
    exactly the confusion this ordering exists to prevent, so it fails closed
    rather than picking a side.
    """
    return _task_id_sources(run_dir)[0]


def _task_id_sources(run_dir: Optional[Path]) -> Tuple[str, bool]:
    """(task_id, disagreed). `task_id` is "" when unknown; `disagreed` is True
    only when BOTH files named a task and the two names differ, so a caller can
    tell "no task recorded anywhere" from "two files contradict each other"."""
    state_tid = ""
    manifest_tid = ""
    if run_dir is not None:
        root = Path(run_dir)
        try:
            state_path = root / STATE_JSON
            if state_path.is_file():
                obj = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    board = obj.get("board")
                    if isinstance(board, dict):
                        state_tid = str(board.get("task_id") or "").strip()
        except Exception:  # noqa: BLE001 — an unreadable state.json is no answer
            state_tid = ""
        try:
            pm = root / "working" / "checkpoints" / "process_manifest.json"
            if pm.is_file():
                obj = json.loads(pm.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    manifest_tid = str(obj.get("cc_task_id") or "").strip()
        except Exception:  # noqa: BLE001 — an unreadable manifest is no answer
            manifest_tid = ""
    if state_tid and manifest_tid and state_tid != manifest_tid:
        _log_reason(TASK_ID_DISAGREEMENT)
        return "", True
    return state_tid or manifest_tid, False


def _cc_board_oracle(run_dir: Optional[Path]) -> Optional[frozenset]:
    """Resolve the run's real owner message ids via cc_board. Returns a
    frozenset on success, None when the board is disabled/unreachable/unknown
    (UNDETERMINED). Never raises."""
    task_id, disagreed = _task_id_sources(run_dir)
    if disagreed:
        # Two files named different tasks. Falling through to the manifest-only
        # helper below would silently pick one of them, which is the exact
        # confusion item (3) exists to prevent.
        return None
    try:
        import sys as _sys
        _sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        import cc_board  # noqa: PLC0415
        if task_id:
            return cc_board.list_owner_message_ids(task_id, env=None)
        if run_dir is not None:
            return cc_board.owner_message_ids_match(Path(run_dir), "", env=None)
        return None
    except Exception:  # noqa: BLE001 — fail-closed: any oracle failure is DENIED
        return None


def verify(approval: Any, run_dir: Optional[Path] = None) -> Dict[str, Any]:
    """THE single authenticity check (Fix 32).

    Validates the schema, then resolves `owner_msg_id` through the
    authoritative owner oracle — cc_board's owner-ids endpoint for the run's
    cc_task_id, falling back to the gateway's owner oracle when the board is
    disabled. The id must RESOLVE to a real owner-authored message.

    Returns the validated approval dict. Raises ApprovalError (message
    prefixed `AF-FORGED-APPROVAL`) on any forgery shape, and on UNDETERMINED —
    a skip that cannot be proven authentic never opens the gate."""
    approval = validate_schema(approval)
    gate = str(approval.get("gate") or approval.get("af_code")
               or approval.get("phase_id") or "").strip()
    owner_msg_id = str(approval.get("owner_msg_id") or "").strip()
    if not owner_msg_id:  # unreachable while require_msg_id=True; kept for clarity
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} has NO owner_msg_id.")

    real_ids = _cc_board_oracle(Path(run_dir) if run_dir is not None else None)
    if real_ids is not None:
        if owner_msg_id in real_ids:
            return approval
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} references "
            f"owner_msg_id {owner_msg_id!r}, which does not resolve to a real "
            "owner-authored message in Command Center task_activities. Presence "
            "of a string is never proof of an owner message.")

    # Board disabled/unreachable — fall back to the gateway owner oracle.
    gw = _gateway_owner_oracle(owner_msg_id)
    if gw is True:
        return approval
    if gw is False:
        raise ApprovalError(
            f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} references "
            f"owner_msg_id {owner_msg_id!r}, which the owner oracle proves is "
            "not a real owner-authored message.")

    raise ApprovalError(
        f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} references "
        f"owner_msg_id {owner_msg_id!r}, but the owner oracle is UNDETERMINED "
        "(board unreachable / no cc_task_id / gateway did not prove the id). "
        "A skip that cannot be proven authentic is DENIED — undetermined never "
        "opens the gate.")


# ---------------------------------------------------------------------------
# Record-set readers — the shape every consumer loads from disk.
# ---------------------------------------------------------------------------
def read_records(run_dir: Path,
                 key: str = "owner_skip_approval") -> List[Dict[str, Any]]:
    """Read every raw owner approval record a run declares, tolerant of a
    single object or a list, under `owner_skip_approval` /
    `owner_skip_approvals` in process_manifest.json (the run's own attestation
    ledger — every record read from it is treated as UNVERIFIED until
    `verify` proves it). Returns only dict records. Never raises."""
    pm = Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"
    if not pm.is_file():
        return []
    try:
        obj = json.loads(pm.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — an unreadable manifest authorizes nothing
        return []
    if not isinstance(obj, dict):
        return []
    raw = obj.get(key, obj.get(key + "s", [])) if key else []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [r for r in raw if isinstance(r, dict)]


def verify_owner_skip_approvals(run_dir: Path, gate: str) -> Optional[Dict[str, Any]]:
    """Return the FIRST approval naming `gate` that verifies against the
    oracle, or None. Every record that names the gate but FAILS verification
    raises ApprovalError (fail-closed — a forged attempt is never quietly
    ignored, it aborts the consuming gate with AF-FORGED-APPROVAL). Records
    that never name this gate produce no verdict (the quiet common case)."""
    want = str(gate or "").strip().upper()
    for rec in read_records(run_dir):
        named = str(rec.get("gate") or rec.get("af_code")
                    or rec.get("phase_id") or "").strip().upper()
        if named != want:
            continue
        return verify(rec, Path(run_dir))
    return None


def split_verified(records: List[Any], run_dir: Optional[Path] = None) -> \
        Tuple[Dict[str, Dict[str, Any]], List[str]]:
    """Bulk form for loaders: validate every record's schema, then verify the
    well-formed ones against the oracle. Returns ({gate: verified_record},
    [rejection messages — every message names AF-FORGED-APPROVAL]). A record
    that names a gate but fails schema or oracle verification lands in the
    rejection list; only fully-verified records land in the index. Consumers
    that treat any rejection as fatal pass the list to their raise path."""
    verified: Dict[str, Dict[str, Any]] = {}
    rejections: List[str] = []
    ids_cache: Optional[frozenset] = None
    ids_resolved = False

    def _ids() -> Optional[frozenset]:
        nonlocal ids_cache, ids_resolved
        if not ids_resolved:
            ids_cache = _cc_board_oracle(Path(run_dir) if run_dir is not None else None)
            ids_resolved = True
        return ids_cache

    for rec in records:
        if not isinstance(rec, dict):
            continue
        gate = str(rec.get("gate") or rec.get("af_code")
                   or rec.get("phase_id") or "").strip()
        try:
            validate_schema(rec)
        except ApprovalError as exc:
            rejections.append(str(exc))
            continue
        owner_msg_id = str(rec.get("owner_msg_id") or "").strip()
        real_ids = _ids()
        if real_ids is not None:
            if owner_msg_id in real_ids:
                verified[gate] = rec
            else:
                rejections.append(
                    f"{AF_FORGED_APPROVAL}: approval for gate {gate!r} references "
                    f"owner_msg_id {owner_msg_id!r}, which does not resolve to a "
                    "real owner-authored message in Command Center "
                    "task_activities.")
            continue
        try:
            verified[gate] = verify(rec, Path(run_dir) if run_dir is not None else None)
        except ApprovalError as exc:
            rejections.append(str(exc))
    return verified, rejections

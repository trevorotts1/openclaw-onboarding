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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Shared constants — exact strings, do not rename.
# ---------------------------------------------------------------------------
AF_FORGED_APPROVAL = "AF-FORGED-APPROVAL"

# Mirror of run_signature_deck._SELF_GRANT_MARKERS / prove-deck
# _SELF_GRANT_MARKERS: the producing agent may never approve its own skip.
SELF_GRANT_MARKERS: Tuple[str, ...] = (
    "executive strategy", "via ", "directive", "auto-approved",
    "self", "auto_approved", "producing", "builder",
)

REASON_MIN_CHARS = 8

_ISO_TZ_RE = re.compile(r"(?:Z|[+-]\d{2}:?\d{2})$")


class ApprovalError(Exception):
    """An owner approval is malformed, self-forged, or unverifiable.

    `str(exc)` always begins with the exact code `AF-FORGED-APPROVAL` for the
    forgery shapes (schema violations name the missing field inside the same
    prefixed message) so every consumer's failure output carries the code the
    QC battery matches on."""


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
    marker = next((m for m in SELF_GRANT_MARKERS if m in approved_by.lower()), None)
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
            if "is_owner" in data:
                return data.get("is_owner") is True
            if "role" in data:
                return str(data.get("role") or "").lower() in ("owner", "user", "client")
        return None
    except _err.HTTPError:
        return False  # a definitive "no such message" from the gateway
    except Exception:  # noqa: BLE001 — any transport failure is UNDETERMINED
        return None


def _cc_board_oracle(run_dir: Optional[Path]) -> Optional[frozenset]:
    """Resolve the run's real owner message ids via cc_board. Returns a
    frozenset on success, None when the board is disabled/unreachable/unknown
    (UNDETERMINED). Never raises."""
    task_id = ""
    if run_dir is not None:
        try:
            pm = Path(run_dir) / "working" / "checkpoints" / "process_manifest.json"
            if pm.is_file():
                obj = json.loads(pm.read_text(encoding="utf-8"))
                if isinstance(obj, dict):
                    task_id = str(obj.get("cc_task_id") or "").strip()
        except Exception:  # noqa: BLE001 — an unreadable manifest is undetermined
            task_id = ""
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

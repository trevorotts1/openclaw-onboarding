#!/usr/bin/env python3
"""intake_provenance.py -- prove every client-owed interview answer came from
a message the client actually sent.

PD-004b (finding PD-004; third class PD-107). The driver used to record a
standard answer as {"value", "validated": True, "source": ...} with no link to
anything the client sent, so an agent could answer its own interview and every
gate still passed.

Three provenance classes are accepted for one answer:

  1 owner message    -- `owner_msg_id` resolves through PD-004a's
                        `presentation_job.approvals.resolve_owner_message` to a
                        real inbound message whose `chat_id` is this run's
                        requester and whose text (whitespace-collapsed,
                        case-folded) matches the stored value. A defaulted
                        answer instead carries `default_accepted_msg_id`, the
                        message in which the client accepted the default.
  2 operator contract -- `source: "operator-contract"` plus the SHA-256 of
                        `working/interview/operator_contract.json` recorded at
                        answer time (`contract_sha256`). Accepted only while the
                        receipt file still hashes to that exact value.
  3 reuse            -- `source` in preference-reuse / plan-lock must name the
                        earlier run (`reused_from_run`).

Exempt: deterministic derivations (`source: "derived"`), skipped answers, and
turn envelopes (a non-scalar `value` is a container of other answers, never an
answer of its own). An answer marked `origin: "agent_authored"` is never proof
of anything the client said.

ROLLOUT SWITCH -- `PRESENTATION_INTAKE_PROVENANCE`:

  warn                print the findings to stderr, write
                      `working/interview/provenance_findings.json`, do NOT
                      block. Opt-in only, for a deployment that cannot yet
                      prove what a client sent.
  enforce  (default)  refuse: the caller exits 6 with the unproven question ids
                      and does not record completion. This is the shipped
                      default: an unproven answer is never accepted.

PD-004c (decision D-40) flipped DEFAULT_MODE to "enforce".

Stdlib only. No network. Read-only apart from the findings file.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

MODE_ENV = "PRESENTATION_INTAKE_PROVENANCE"
DEFAULT_MODE = "enforce"  # PD-004c (D-40): warn is opt-in; unproven is refused.
MODE_WARN = "warn"
MODE_ENFORCE = "enforce"

FINDINGS_REL = Path("working") / "interview" / "provenance_findings.json"
RECEIPT_REL = Path("working") / "interview" / "operator_contract.json"

EXEMPT_SOURCES = {"derived"}
REUSE_SOURCES = {"preference-reuse", "plan-lock"}
CONTRACT_SOURCE = "operator-contract"
RESERVED_KEYS = {"answers", "answer_provenance"}

YES = {"yes", "y", "true", "yeah", "yep", "sure", "ok", "okay"}
NO = {"no", "n", "false", "nope", "no thanks", "no thank you"}


def provenance_mode() -> str:
    """'enforce' (default) or 'warn'; an unrecognised value stays 'enforce'."""
    raw = str(os.environ.get(MODE_ENV) or "").strip().lower()
    return MODE_WARN if raw == MODE_WARN else DEFAULT_MODE


def norm(text: Any) -> str:
    return " ".join(str(text if text is not None else "").split()).strip().casefold()


def matches(stored: Any, message_text: Any) -> bool:
    s, m = norm(stored), norm(message_text)
    if s == m:
        return True
    if s in ("yes", "true") and m in YES:
        return True
    if s in ("no", "false") and m in NO:
        return True
    return False


def receipt_sha256(run_dir: Path) -> Optional[str]:
    """SHA-256 of the operator-contract receipt file, or None when absent."""
    path = Path(run_dir) / RECEIPT_REL
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def contract_receipt_ok(run_dir: Path) -> bool:
    """The receipt exists AND carries the bridge's `receipt_hmac`."""
    path = Path(run_dir) / RECEIPT_REL
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(obj, dict) and bool(str(obj.get("receipt_hmac") or "").strip())


def _resolve(run_dir: Path, msg_id: str) -> Optional[Dict[str, Any]]:
    """PD-004a's resolver; an absent or failing resolver proves nothing."""
    try:
        from presentation_job.approvals import resolve_owner_message  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return None
    try:
        row = resolve_owner_message(str(msg_id), Path(run_dir))
    except Exception:  # noqa: BLE001
        return None
    return row if isinstance(row, dict) else None


def _label(aliases: Iterable[str], key: str, question_ids: Set[str]) -> str:
    """One stable name per answer: its question id when the ledger's own key
    is the store name (`AUDIENCE` -> `audience`)."""
    by_case = {q.casefold(): q for q in question_ids}
    ordered_keys = sorted(set(aliases) | {key})
    for alias in ordered_keys:
        if alias in question_ids:
            return alias
    for alias in ordered_keys:
        if alias.casefold() in by_case:
            return by_case[alias.casefold()]
    for alias in ordered_keys:
        if alias.islower():
            return alias
    return ordered_keys[0]


def ordered(ledger: Optional[Dict[str, Any]], question_ids: Set[str]) -> Dict[str, Any]:
    """Project a ledger's answers onto stable question-id names.

    One answer can sit under several keys (the question id, its store name) and
    an older copy can survive a later structured write; every copy that folds
    to the same name is ONE answer.
    """
    ledger = ledger if isinstance(ledger, dict) else {}
    out: Dict[str, Any] = {}
    seen: Set[str] = set()
    groups = (("standard", ledger.get("entries") or {}),
              ("signature", ledger.get("sp_entries") or {}))
    for group, entries in groups:
        if not isinstance(entries, dict):
            continue
        aliases: Dict[int, List[str]] = {}
        for key, value in entries.items():
            if isinstance(value, dict) and key not in RESERVED_KEYS:
                aliases.setdefault(id(value), []).append(str(key))
        for key in entries:
            value = entries[key]
            if not isinstance(value, dict) or str(key) in RESERVED_KEYS:
                continue
            name = _label(aliases.get(id(value), []), str(key), question_ids)
            if isinstance(value.get("value"), (dict, list)):
                continue  # turn envelope, not an answer
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            out[name] = value
    return out


def evaluate(run_dir: Path, ledger: Optional[Dict[str, Any]], *,
             requester_chat: str = "",
             question_ids=None) -> Dict[str, Any]:
    """Return {"status", "proven_answers", "unproven_questions", "findings"}."""
    run_dir = Path(run_dir)
    requester = str(requester_chat or "").strip()
    qids = {str(q) for q in (question_ids or ()) if str(q)}
    receipt = receipt_sha256(run_dir)

    findings: List[str] = []
    unproven: List[str] = []
    proven = 0
    used: Dict[str, str] = {}

    def fail(group: str, name: str, reason: str) -> None:
        if name not in unproven:
            unproven.append(name)
        findings.append(f"{group} {name}: {reason}")

    def check(group: str, name: str, entry: Dict[str, Any], value: Any) -> None:
        nonlocal proven
        source = str(entry.get("source") or "")
        if source in EXEMPT_SOURCES or entry.get("skipped"):
            return
        if isinstance(value, (dict, list)):
            return  # turn envelope, not an answer
        if source in REUSE_SOURCES:
            if not str(entry.get("reused_from_run") or "").strip():
                fail(group, name, "reused answer does not name the run it came from")
            return
        if entry.get("origin") == "agent_authored":
            fail(group, name, "the answer was written by the agent, not the client")
            return
        stored_contract = str(entry.get("contract_sha256") or "")
        if source == CONTRACT_SOURCE or stored_contract:
            if not stored_contract or not receipt or stored_contract != receipt:
                fail(group, name,
                     "the operator contract receipt no longer matches this answer")
            else:
                proven += 1
            return
        defaulted = bool(entry.get("defaulted"))
        msg_id = str((entry.get("default_accepted_msg_id") if defaulted else None)
                     or entry.get("owner_msg_id") or "").strip()
        if not msg_id:
            fail(group, name, "no client message id on the answer")
            return
        row = _resolve(run_dir, msg_id)
        if row is None:
            fail(group, name,
                 f"message {msg_id} cannot be resolved to a message the client sent")
            return
        if not requester:
            fail(group, name, "the run has no requester chat id to compare against")
            return
        if str(row.get("chat_id") or "").strip() != requester:
            fail(group, name,
                 f"message {msg_id} came from a different chat than the requester")
            return
        same_message = bool(entry.get("from_same_message"))
        # One client message may carry several labelled values, so a record
        # that is a FRAGMENT of it may share its id; a record whose value is
        # the whole message cannot back a second answer.
        fragment = same_message and norm(value) and norm(value) != norm(row.get("text"))
        if not defaulted and not matches(value, row.get("text")):
            if not (fragment and norm(value) in norm(row.get("text"))):
                fail(group, name,
                     f"the answer is not what the client sent in message {msg_id}")
                return
        if msg_id in used and not (fragment or defaulted):
            fail(group, name,
                 f"message {msg_id} is already used by {used[msg_id]}")
            return
        used.setdefault(msg_id, name)
        proven += 1

    answers = ordered(ledger, qids)
    for name, entry in answers.items():
        check("answer", name, entry, entry.get("value"))

    # A batch record stores its provenance beside the flat answers.
    sp = (ledger or {}).get("sp_entries") if isinstance(ledger, dict) else None
    block = sp.get("answer_provenance") if isinstance(sp, dict) else None
    if isinstance(block, dict):
        seen = set()
        for qid in sorted(block):
            blk = block[qid]
            if not isinstance(blk, dict) or id(blk) in seen:
                continue
            seen.add(id(blk))
            check("answer_provenance", str(qid), blk, blk.get("client_text"))

    return {
        "status": "unproven" if unproven else "proven",
        "proven_answers": proven,
        "unproven_questions": unproven,
        "findings": findings,
    }


def apply(run_dir: Path, ledger: Optional[Dict[str, Any]], *,
          requester_chat: str = "", question_ids=None,
          door: str = "intake") -> int:
    """Run the proof at a completion door. Returns 0 to continue, 6 to refuse.

    In `enforce` the refusal JSON is the ONLY thing written to stdout, so the
    caller returns immediately and its own success payload never follows.
    """
    result = evaluate(run_dir, ledger, requester_chat=requester_chat,
                      question_ids=question_ids)
    mode = provenance_mode()
    if result["status"] == "proven":
        return 0

    payload = {
        "status": "unproven",
        "door": door,
        "mode": mode,
        "proven_answers": result["proven_answers"],
        "unproven_questions": result["unproven_questions"],
        "findings": result["findings"],
    }
    try:
        path = Path(run_dir) / FINDINGS_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        print(f"  WARN  [INTAKE-PROVENANCE] findings not written: {exc}",
              file=sys.stderr)

    if mode == MODE_ENFORCE:
        payload["message"] = (
            "Every interview answer must be traceable to a message the client "
            "sent. Nothing was completed; re-record the named answers with "
            "--owner-msg-id (or --operator-contract) and run again.")
        print(json.dumps(payload, indent=2))
        return 6

    print(f"  WARN  [INTAKE-PROVENANCE] {len(result['unproven_questions'])} "
          f"answer(s) cannot be traced to a client message (mode=warn, not "
          f"blocking; findings at {FINDINGS_REL}):", file=sys.stderr)
    for line in result["findings"]:
        print(f"  WARN  [INTAKE-PROVENANCE] {line}", file=sys.stderr)
    return 0

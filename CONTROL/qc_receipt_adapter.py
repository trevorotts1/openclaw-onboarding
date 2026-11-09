#!/usr/bin/env python3
"""S75-T35: immediate unit QC and durable exact-head receipts.

Fail-closed adapter. A receipt confirms the unit ONLY when all of these hold:

  1. it carries a STRUCTURED claim (a dict with the contract fields), not
     captured console output;
  2. its recorded `head_tested` is a full 40-hex SHA EQUAL to the candidate
     head (an abbreviated or different head is not this candidate);
  3. its approver differs from the author on identity AND lineage, and for a
     repair receipt the verifier differs from the repair author on both. The
     adapter enforces this; it never trusts a brief that asserts independence.

Everything else lands on QC_UNCONFIRMED with a named reason code.

Durability: `commit_verdict` evaluates, then writes the receipt, then the
ledger transition, each via atomic replace + fsync, and only then returns an
acknowledgement. EVERY rejection is durable: a record that does not belong to
this ledger (wrong head, abbreviated head, foreign unit) is written into the
ledger's `rejections` list and acknowledged, never raised past. The only error
that escapes is DurabilityError, when a write itself fails, and then no
acknowledgement is returned.

Ledger transitions are idempotent: the same verdict for the same unit at the
same head twice leaves the ledger byte-identical. A DIFFERENT verdict for the
same unit at the same head is a conflict, not a duplicate: the first verdict is
never overwritten, the unit becomes QC_CONFLICT, and a distinct third authority
is required. That authority has exactly one route: the `adjudication` event
(ADJUDICATION_POLICY), which writes a resolution record and never mutates the
first verdict.

Outcome is derived, never believed: `apply_verdict` / `apply_event` re-derive
what a record means from its own claim fields and reason code. A record that
asserts `result: QC_CONFIRMED` while carrying a refusal code cannot confirm.
"""

from __future__ import annotations

import json
import os
import re
import tempfile

QC_CONFIRMED = "QC_CONFIRMED"
QC_UNCONFIRMED = "QC_UNCONFIRMED"
QC_CONFLICT = "QC_CONFLICT"

CONFIRMABLE_VERDICTS = ("PASS",)

REQUIRED_CLAIM_FIELDS = (
    "unit",
    "head_tested",
    "verdict",
    "author",
    "approver",
    "checks",
)

SUPPORTED_EVENTS = ("verdict", "repair_request", "lease_renewal", "adjudication")

ADJUDICATION_POLICY = (
    "the one route out of QC_CONFLICT: a separately authorised 'adjudication' "
    "event whose adjudicator differs on identity AND lineage from every party "
    "already recorded in the conflict, and whose authorisation is not the "
    "adjudicator's own identity. It writes a resolution record and never "
    "mutates the first verdict. Repeats are no-ops, and the first resolution "
    "wins"
)

CONFLICT_POLICY = (
    "same unit+head with a different verdict is a CONFLICT: first verdict is "
    "retained, unit becomes QC_CONFLICT, no verdict field is overwritten, and "
    "a distinct third authority is required to resolve it"
)

REASON_STRUCTURE = "unstructured_stdout"
REASON_MISSING_CLAIM = "missing_structured_claim"
REASON_HEAD_NOT_FULL_SHA = "head_not_full_sha"
REASON_HEAD_MISMATCH = "wrong_head"
REASON_VERDICT_NOT_CONFIRMABLE = "verdict_not_confirmable"
REASON_SELF_APPROVED = "self_approved"
REASON_REPAIR_AUTHOR_DEPENDENT = "repair_author_not_independent"
REASON_NO_CHECKS = "no_checks_recorded"
REASON_IDENTITY_MISSING = "identity_or_lineage_missing"
REASON_WRONG_UNIT = "wrong_unit"

REJECTION_CODES = (
    REASON_STRUCTURE,
    REASON_MISSING_CLAIM,
    REASON_HEAD_NOT_FULL_SHA,
    REASON_HEAD_MISMATCH,
    REASON_VERDICT_NOT_CONFIRMABLE,
    REASON_SELF_APPROVED,
    REASON_REPAIR_AUTHOR_DEPENDENT,
    REASON_NO_CHECKS,
    REASON_IDENTITY_MISSING,
    REASON_WRONG_UNIT,
)

_HEX40 = re.compile(r"^[0-9a-f]{40}$")


class UnsupportedEvent(ValueError):
    """An event type this adapter does not support. Never silently ignored."""

class RefusedRecord(ValueError):
    """A record or event this adapter refuses on its own gates.

    A ValueError subclass so existing callers keep working, but never a bare
    ValueError: a refusal names itself. A refusal that concerns a RECEIPT is
    never raised at all -- it lands in the ledger's `rejections` list and is
    acknowledged. What raises here is a malformed input or an adjudication
    that fails its own gates, and both leave the state untouched.
    """


class DurabilityError(RuntimeError):
    """A durable write failed. No acknowledgement is ever returned for it."""


def _pair_ok(value):
    """An author/approver block: non-empty identity and lineage strings."""
    return (
        isinstance(value, dict)
        and isinstance(value.get("identity"), str)
        and value["identity"].strip() != ""
        and isinstance(value.get("lineage"), str)
        and value["lineage"].strip() != ""
    )


def _norm(value):
    """Identity comparison form: trim and case-fold.

    Both halves of a party comparison use this. An author cannot become
    independent by changing model, session or workflow label -- nor by
    rewriting 'builder-lane-7' as 'Builder-Lane-7' (QC-AND-REPAIR.md:11).
    """
    return value.strip().casefold()

def _same_party(a, b):
    """Same person, or same model lineage: not an independent check."""
    return _norm(a["identity"]) == _norm(b["identity"]) or (
        _norm(a["lineage"]) == _norm(b["lineage"])
    )


def _unconfirmed(code, detail, **extra):
    out = {
        "result": QC_UNCONFIRMED,
        "code": code,
        "reason": detail,
        "unit": extra.get("unit"),
        "head_tested": extra.get("head_tested"),
    }
    return out


def evaluate_receipt(receipt, candidate_head, kind="qc"):
    """Evaluate one receipt against one candidate head. Never raises on input.

    `receipt` may be the structured claim (dict), or the captured console
    output that a careless lane forwards instead (str/bytes). The latter can
    never confirm.
    """
    if isinstance(receipt, (str, bytes)):
        return _unconfirmed(
            REASON_STRUCTURE,
            "captured console output carries no structured claim; stdout is not a receipt",
        )

    if not isinstance(receipt, dict):
        return _unconfirmed(
            REASON_STRUCTURE, "receipt is not a structured claim object"
        )

    missing = [f for f in REQUIRED_CLAIM_FIELDS if f not in receipt]
    if missing:
        return _unconfirmed(
            REASON_MISSING_CLAIM,
            "structured claim missing required fields: " + ", ".join(missing),
            unit=receipt.get("unit"),
            head_tested=receipt.get("head_tested"),
        )

    unit = receipt.get("unit")
    head = receipt.get("head_tested")

    if not isinstance(head, str) or not _HEX40.match(head.strip().lower()):
        return _unconfirmed(
            REASON_HEAD_NOT_FULL_SHA,
            "head_tested is not a full 40-hex commit SHA",
            unit=unit,
            head_tested=head,
        )

    cand = (candidate_head or "").strip().lower()
    if not _HEX40.match(cand):
        return _unconfirmed(
            REASON_HEAD_NOT_FULL_SHA,
            "candidate head is not a full 40-hex commit SHA",
            unit=unit,
            head_tested=head,
        )

    if head.strip().lower() != cand:
        return _unconfirmed(
            REASON_HEAD_MISMATCH,
            "receipt head_tested %s is not candidate head %s" % (head, cand),
            unit=unit,
            head_tested=head.strip().lower(),
        )

    verdict = receipt.get("verdict")
    if verdict not in CONFIRMABLE_VERDICTS:
        return _unconfirmed(
            REASON_VERDICT_NOT_CONFIRMABLE,
            "verdict %r is not a confirmable verdict %r" % (verdict, CONFIRMABLE_VERDICTS),
            unit=unit,
            head_tested=cand,
        )

    author, approver = receipt.get("author"), receipt.get("approver")
    if not (_pair_ok(author) and _pair_ok(approver)):
        return _unconfirmed(
            REASON_IDENTITY_MISSING,
            "author and approver must each carry a non-empty identity and lineage",
            unit=unit,
            head_tested=cand,
        )

    if _same_party(author, approver):
        return _unconfirmed(
            REASON_SELF_APPROVED,
            "approver %s/%s is the author: a receipt may not approve itself"
            % (approver["identity"], approver["lineage"]),
            unit=unit,
            head_tested=cand,
        )

    if kind == "repair" or receipt.get("kind") == "repair":
        repair_author = receipt.get("repair_author")
        if not _pair_ok(repair_author):
            return _unconfirmed(
                REASON_REPAIR_AUTHOR_DEPENDENT,
                "repair receipt must name the repair_author it is verifying",
                unit=unit,
                head_tested=cand,
            )
        if _same_party(repair_author, approver):
            return _unconfirmed(
                REASON_REPAIR_AUTHOR_DEPENDENT,
                "verifier %s/%s is the repair author"
                % (approver["identity"], approver["lineage"]),
                unit=unit,
                head_tested=cand,
            )

    checks = receipt.get("checks")
    if not isinstance(checks, list) or not checks:
        return _unconfirmed(
            REASON_NO_CHECKS,
            "no focused checks recorded",
            unit=unit,
            head_tested=cand,
        )

    return {
        "result": QC_CONFIRMED,
        "code": "confirmed",
        "reason": "structured claim, exact head, independent approver",
        "unit": unit,
        "head_tested": cand,
        "verdict": verdict,
        "author": {"identity": author["identity"], "lineage": author["lineage"]},
        "approver": {"identity": approver["identity"], "lineage": approver["lineage"]},
        "checks": checks,
    }


def build_state(unit, head_tested):
    return {
        "unit": unit,
        "head_tested": head_tested,
        "status": QC_UNCONFIRMED,
        "verdict": None,
        "entries": [],
        "rejections": [],
        "conflict": None,
        "resolution": None,
    }


def _party_key(value):
    """Case-folded identity of one party; None when the party is absent."""
    if _pair_ok(value):
        return (_norm(value["identity"]), _norm(value["lineage"]))
    return None

def _claim_key(record):
    """What a record CLAIMS, identity-free. `reason` text is not part of it."""
    return (record.get("result"), record.get("code"), record.get("head_tested"))

def _entry_key(record):
    """Who recorded it, and what.

    `reason` text is deliberately NOT part of a record's identity: formatting
    drift in a message must never become a CONFLICT that demotes a unit. The
    author and approver ARE part of it, so a second genuinely distinct approver
    is recorded as its own row instead of being dropped as a duplicate.
    """
    return _claim_key(record) + (
        _party_key(record.get("author")),
        _party_key(record.get("approver")),
    )

def _resolution_key(record):
    """Identity of an adjudication: who, under whose authority, ruling what."""
    adjudicator = record.get("adjudicator")
    return (
        record.get("result"),
        record.get("code"),
        record.get("head_tested"),
        _party_key(adjudicator),
        record.get("authorisation"),
    )

def _parties_of(entry):
    """The named parties of one recorded row, for third-authority checks."""
    out = []
    for role in ("author", "approver"):
        party = entry.get(role)
        if _pair_ok(party):
            out.append(
                {"role": role, "identity": party["identity"], "lineage": party["lineage"]}
            )
    return out

def _merge_parties(*groups):
    """One list of recorded parties, deduplicated on the case-folded identity."""
    out = []
    for group in groups:
        for party in group or []:
            if _pair_ok(party) and not any(
                _same_party(party, seen) for seen in out
            ):
                out.append(party)
    return out

_ENTRY_FIELDS = (
    "result",
    "code",
    "reason",
    "unit",
    "head_tested",
    "verdict",
    "author",
    "approver",
    "checks",
    "kind",
    "repair_author",
)

def _entry_from(record, derived):
    """Ledger row: the record's own evidence, with the DERIVED outcome on top."""
    entry = {k: v for k, v in record.items() if k in _ENTRY_FIELDS}
    entry.update(derived)
    return entry

def _derive(record, state_head):
    """Derive what a record means. Its self-declared result/code are never used.

    A full claim (every required field present) is re-evaluated from scratch
    against this ledger's head. A record carrying a named rejection code is
    that rejection. Nothing else can confirm: a record that claims 'confirmed'
    without a claim to re-evaluate is missing_structured_claim.
    """
    if all(field in record for field in REQUIRED_CLAIM_FIELDS):
        claim = {
            k: v for k, v in record.items() if k not in ("result", "code", "reason")
        }
        return evaluate_receipt(claim, state_head, kind=claim.get("kind") or "qc")
    code = record.get("code")
    if code in REJECTION_CODES:
        return {
            "result": QC_UNCONFIRMED,
            "code": code,
            "reason": record.get("reason"),
            "unit": record.get("unit"),
            "head_tested": record.get("head_tested"),
        }
    return {
        "result": QC_UNCONFIRMED,
        "code": REASON_MISSING_CLAIM,
        "reason": (
            "record carries no claim to re-evaluate and no named rejection "
            "code; only a re-evaluated claim can confirm"
        ),
        "unit": record.get("unit"),
        "head_tested": record.get("head_tested"),
    }

def _reject(state, record, derived, forced_code, detail):
    """Durable rejection: recorded in state['rejections'], never raised past."""
    code = derived.get("code")
    if code not in REJECTION_CODES:
        code = forced_code
    entry = {
        "result": QC_UNCONFIRMED,
        "code": code,
        "reason": detail,
        "unit": record.get("unit"),
        "head_tested": record.get("head_tested"),
        "claimed": {"result": record.get("result"), "code": record.get("code")},
    }
    rejections = list(state.get("rejections", []))
    if any(_entry_key(e) == _entry_key(entry) for e in rejections):
        return "duplicate", state
    new = dict(state)
    new["rejections"] = rejections + [entry]
    return "rejected", new


def apply_verdict(state, record):
    """Apply one evaluated verdict to a ledger state. Returns (outcome, state).

    outcome is "applied", "duplicate", "conflict" or "rejected". A duplicate
    returns the SAME state object, unmodified, so a second identical verdict
    cannot double-count, duplicate a row or append an entry. A rejected record
    is one that does not belong to this ledger (wrong head, abbreviated head,
    foreign unit): it is recorded in `rejections` and acknowledged, never
    raised past.

    The outcome a record carries is DERIVED here (_derive), never believed.
    """
    if not isinstance(state, dict) or not isinstance(record, dict):
        raise RefusedRecord("state and record must be objects")

    state_head = state.get("head_tested")
    derived = _derive(record, state_head)

    if record.get("unit") not in (None, state.get("unit")):
        return _reject(
            state,
            record,
            derived,
            REASON_WRONG_UNIT,
            "record unit %r does not belong to this ledger state"
            % (record.get("unit"),),
        )
    head = record.get("head_tested") or state_head
    if head != state_head:
        return _reject(
            state,
            record,
            derived,
            REASON_HEAD_MISMATCH,
            "record head %s does not belong to this ledger state" % (head,),
        )

    entry = _entry_from(record, derived)
    key = _entry_key(entry)
    if any(_entry_key(e) == key for e in state.get("entries", [])):
        return "duplicate", state

    conflict = state.get("conflict")
    if conflict is not None:
        results = [list(r) for r in conflict.get("results", [])]
        if list(key) in results:
            return "duplicate", state
        new = dict(state)
        new["conflict"] = dict(conflict)
        new["conflict"]["results"] = results + [list(key)]
        new["conflict"]["parties"] = _merge_parties(
            conflict.get("parties"), _parties_of(entry)
        )
        return "conflict", new

    first = state.get("verdict")
    if state.get("status") in (QC_CONFIRMED, QC_UNCONFIRMED) and first:
        if _claim_key(first) != _claim_key(entry):
            new = dict(state)
            new["status"] = QC_CONFLICT
            new["conflict"] = {
                "policy": CONFLICT_POLICY,
                "required_resolution": "distinct third authority",
                "results": [list(key)],
                "parties": _merge_parties(_parties_of(first), _parties_of(entry)),
            }
            return "conflict", new

    new = dict(state)
    new["entries"] = list(state.get("entries", [])) + [entry]
    if new.get("verdict") is None:
        new["verdict"] = dict(entry)
        new["status"] = entry["result"]
    return "applied", new


def apply_event(state, event):
    """Supported-event gate. Unknown event types are refused, never ignored."""
    if not isinstance(event, dict):
        raise UnsupportedEvent("event must be an object")
    name = event.get("type")
    if name not in SUPPORTED_EVENTS:
        raise UnsupportedEvent(
            "unsupported event type %r; supported: %s"
            % (name, ", ".join(SUPPORTED_EVENTS))
        )
    if name == "verdict":
        return apply_verdict(state, event.get("verdict"))
    if name == "adjudication":
        return _apply_adjudication(state, event)
    if name == "repair_request":
        target = event.get("unit")
        if target != state.get("unit"):
            raise RefusedRecord("repair_request for a different unit")
        if any(e.get("result") == QC_CONFIRMED for e in state.get("entries", [])):
            return "duplicate", state
        new = dict(state)
        new["entries"] = list(state.get("entries", [])) + [{"result": "REPAIR_REQUESTED"}]
        return "applied", new
    # lease_renewal: records a heartbeat only; it never moves a verdict.
    new = dict(state)
    new["entries"] = list(state.get("entries", [])) + [
        {"result": "LEASE_RENEWED", "generation": event.get("generation")}
    ]
    return "applied", new


def _apply_adjudication(state, event):
    """The one route out of QC_CONFLICT. See ADJUDICATION_POLICY.

    A third identity AND lineage, distinct from every party already recorded,
    acting under a separate authorisation, writes a resolution record. The
    first verdict is never touched. Repeats of the same resolution are no-ops;
    once one resolution is recorded, the first resolution wins and a different
    one is refused with nothing written.
    """
    adjudicator = event.get("adjudicator")
    if not _pair_ok(adjudicator):
        raise RefusedRecord(
            "adjudication must name an adjudicator with identity and lineage"
        )
    authorisation = event.get("authorisation")
    if not isinstance(authorisation, str) or authorisation.strip() == "":
        raise RefusedRecord("adjudication must carry its separate authorisation")
    if _norm(authorisation) == _norm(adjudicator["identity"]):
        raise RefusedRecord(
            "adjudication authorisation is the adjudicator's own identity: "
            "that is not a separate authority"
        )
    resolution = event.get("resolution")
    if not isinstance(resolution, dict) or resolution.get("result") not in (
        QC_CONFIRMED,
        QC_UNCONFIRMED,
    ):
        raise RefusedRecord(
            "adjudication resolution must name QC_CONFIRMED or QC_UNCONFIRMED"
        )
    conflict = state.get("conflict")
    if conflict is None:
        raise RefusedRecord("no conflict recorded: there is nothing to adjudicate")

    recorded = _merge_parties(
        _parties_of(state.get("verdict") or {}),
        conflict.get("parties"),
        *(_parties_of(e) for e in state.get("entries") or []),
    )
    for party in recorded:
        if _same_party(adjudicator, party):
            raise RefusedRecord(
                "adjudicator %s/%s is already recorded as %s: the resolution "
                "needs a third identity AND lineage"
                % (adjudicator["identity"], adjudicator["lineage"], party.get("role"))
            )

    record = {
        "result": resolution["result"],
        "code": "adjudicated",
        "reason": resolution.get("reason"),
        "unit": state.get("unit"),
        "head_tested": state.get("head_tested"),
        "adjudicator": {
            "identity": adjudicator["identity"],
            "lineage": adjudicator["lineage"],
        },
        "authorisation": authorisation.strip(),
        "resolution": resolution,
        "parties_checked": recorded,
        "policy": ADJUDICATION_POLICY,
    }
    existing = state.get("resolution")
    if existing is not None:
        if _resolution_key(existing) == _resolution_key(record):
            return "duplicate", state
        raise RefusedRecord(
            "a resolution is already recorded and it is not overwritten: "
            "the first resolution wins"
        )

    new = dict(state)
    new["resolution"] = record
    new["status"] = record["result"]
    return "applied", new

def _atomic_write_json(path, payload):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".qc-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
            fh.write("\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        dfd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def load_state(path, unit, head_tested):
    if not os.path.exists(path):
        return build_state(unit, head_tested)
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _ledger_view(outcome, state):
    """The ledger's own answer, embedded in the receipt.

    Both files are written from this one view in the same commit, so a receipt
    can never name an approver the ledger does not name: the recorded verdict,
    every recorded entry and every recorded rejection travel with it.
    """
    approvers = []
    for e in state.get("entries", []):
        party = e.get("approver")
        if _pair_ok(party):
            approvers.append(
                {"identity": party["identity"], "lineage": party["lineage"]}
            )
    return {
        "outcome": outcome,
        "status": state.get("status"),
        "verdict": state.get("verdict"),
        "approvers": approvers,
        "entries": state.get("entries", []),
        "rejections": state.get("rejections", []),
        "conflict": state.get("conflict"),
        "resolution": state.get("resolution"),
    }

def _ack_row(state, outcome, record):
    """The ledger row this commit actually recorded, for the acknowledgement."""
    if outcome == "rejected":
        rows = state.get("rejections") or []
    elif outcome == "applied":
        rows = state.get("entries") or []
    else:
        rows = []
    return rows[-1] if rows else record

def commit_verdict(
    receipt,
    candidate_head,
    receipt_path,
    ledger_path,
    kind="qc",
    generation=1,
):
    """Durably record the receipt, then the ledger transition, then acknowledge.

    The acknowledgement is constructed only after both files are on disk, and
    one is returned for EVERY outcome, rejections included: a rejection is a
    recorded, acknowledged fact, never an exception thrown past the ledger. The
    only failure that raises is DurabilityError, when a write itself fails, and
    then no acknowledgement is returned at all.
    """
    record = evaluate_receipt(receipt, candidate_head, kind=kind)
    unit = record.get("unit") or (receipt.get("unit") if isinstance(receipt, dict) else None)
    head = (candidate_head or "").strip().lower()

    state = load_state(ledger_path, unit, head)
    outcome, new_state = apply_event(state, {"type": "verdict", "verdict": record})
    view = _ledger_view(outcome, new_state)

    durable_receipt = {
        "schema": "s75.qc-receipt/1",
        "unit": unit,
        "head_tested": head,
        "generation": generation,
        "kind": kind,
        "evaluation": record,
        "claim": receipt if isinstance(receipt, (dict, str)) else None,
        "ledger": view,
    }

    try:
        _atomic_write_json(receipt_path, durable_receipt)
        _atomic_write_json(ledger_path, new_state)
    except OSError as exc:
        raise DurabilityError("durable write failed: %s" % exc) from exc

    row = _ack_row(new_state, outcome, record)
    return {
        "acknowledged": True,
        "durable": True,
        "outcome": outcome,
        "result": row.get("result"),
        "code": row.get("code"),
        "unit": unit,
        "head_tested": head,
        "receipt_path": os.path.abspath(receipt_path),
        "ledger_path": os.path.abspath(ledger_path),
        "ledger_status": new_state["status"],
        "recorded_approvers": view["approvers"],
    }

def commit_adjudication(
    event,
    resolution_path,
    ledger_path,
    generation=1,
):
    """Durably record one adjudication of a QC_CONFLICT ledger. See ADJUDICATION_POLICY.

    Same durability contract as commit_verdict: the resolution record and the
    ledger transition are both on disk before the acknowledgement exists, a
    repeat is a no-op, and only DurabilityError escapes.
    """
    if not os.path.exists(ledger_path):
        raise RefusedRecord(
            "no ledger at %s: there is nothing to adjudicate" % (ledger_path,)
        )
    state = load_state(ledger_path, None, None)
    outcome, new_state = apply_event(state, event)
    view = _ledger_view(outcome, new_state)

    durable_resolution = {
        "schema": "s75.qc-adjudication/1",
        "unit": new_state.get("unit"),
        "head_tested": new_state.get("head_tested"),
        "generation": generation,
        "event": event,
        "ledger": view,
    }

    try:
        _atomic_write_json(resolution_path, durable_resolution)
        _atomic_write_json(ledger_path, new_state)
    except OSError as exc:
        raise DurabilityError("durable write failed: %s" % exc) from exc

    return {
        "acknowledged": True,
        "durable": True,
        "outcome": outcome,
        "result": new_state.get("resolution", {}).get("result"),
        "code": new_state.get("resolution", {}).get("code"),
        "unit": new_state.get("unit"),
        "head_tested": new_state.get("head_tested"),
        "resolution_path": os.path.abspath(resolution_path),
        "ledger_path": os.path.abspath(ledger_path),
        "ledger_status": new_state["status"],
    }

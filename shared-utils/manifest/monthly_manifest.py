#!/usr/bin/env python3
"""Joined monthly approval manifest: one client approval, exact placement terms.

DATA-CONTRACTS section 10 / DEC-02: one coordinated client approval covers a
joined 30-day campaign of exact placements, and a mutation invalidates that
placement only.

This module owns the approval *lifecycle* the shared contract layer does not:

  approve()            join a DRAFT campaign into one approved revision
  amend()              change one placement's approved terms; invalidates that
                       placement only, so unrelated approved placements continue
  reapprove()          put one amended placement back to APPROVED
  next_cycle()         open the next 30-day cycle as a fresh DRAFT revision
  check_revision()     version enforcement: a new approval advances, never
                       repeats or rolls back
  validate()           the accepted approval contract, nothing re-implemented
  terms_errors()       every bound term present and informative, schedule inside
                       the joined window

Dispatch binding is NOT re-implemented here. The accepted T-08 guard
(38-conversational-ai-system/tools/pb_contracts.py: approval_errors, reached by
`pb_contracts.py dispatch`) already compares every approved placement field
against the outgoing action and refuses with the field named. This module feeds
that guard and never writes a second copy of it; the field list is imported from
it, so a term added upstream is enforced here without an edit.

Every function copies the document and returns (new_doc, errors); on any error
the original document comes back unchanged, so a caller persists only a clean
result. stdlib only.

  from monthly_manifest import approve, amend, reapprove, next_cycle
  doc, errs = approve(doc, "client-owner-1", "2026-10-20T18:00:00Z", "rev-3", "rev-2")
"""
from __future__ import annotations

import copy
import os
import re
import sys
from datetime import timedelta
from pathlib import Path

VERSION = "1.0.0"

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
_TOOLS_CANDIDATES = [
    os.environ.get("PB_CONTRACTS_TOOLS"),
    str(_REPO_ROOT / "38-conversational-ai-system" / "tools"),
]
for _candidate in _TOOLS_CANDIDATES:
    if _candidate and (Path(_candidate) / "pb_contracts.py").is_file():
        sys.path.insert(0, _candidate)
        break
else:
    raise RuntimeError(
        "pb_contracts.py not found; looked in %r. Set PB_CONTRACTS_TOOLS to the "
        "38-conversational-ai-system/tools directory." % (_TOOLS_CANDIDATES,)
    )

import pb_contracts as contracts  # noqa: E402

# The terms one client approval covers: placement identity plus the section 3
# placement fields, read from the accepted guard rather than copied.
APPROVAL_TERMS = ("account_id", "account_binding_revision") + tuple(contracts.PLACEMENT_BOUND_FIELDS)

SIGNED_STATUSES = ("APPROVED", "PARTIAL_INVALIDATED")
JOINED_WINDOW_DAYS = 30

_TRAILING_COUNTER = re.compile(r"(\d+)\s*$")


# --------------------------------------------------------------------------
# small shared predicates
# --------------------------------------------------------------------------


def _missing(value):
    """True when a value carries no information: absent, or blank when trimmed.

    ``contracts.normalise_evidence_id`` trims whitespace and format marks and
    returns None for a blank string, so a zero width space in an approved CTA is
    absent here just as it is in the dispatch gate. Non-strings pass through and
    the schema layer names their type.
    """
    if value is None:
        return True
    if isinstance(value, str):
        return contracts.normalise_evidence_id(value) is None
    return False


def _counter(revision):
    match = _TRAILING_COUNTER.search(revision) if isinstance(revision, str) else None
    return int(match.group(1)) if match else None


def _stamp_errors(value, name):
    if _missing(value):
        return ["$.%s: a real timestamp is required" % name]
    try:
        contracts.parse_ts(value, name)
    except contracts.UsageError as exc:
        return [str(exc)]
    return []


def _cas_errors(doc, expected_revision):
    if expected_revision != doc.get("revision"):
        return [
            "$.revision: expected %r but the manifest is at %r"
            % (expected_revision, doc.get("revision"))
        ]
    return []


def _placement(doc, placement_id):
    for placement in doc.get("placements") or []:
        if placement.get("placement_id") == placement_id:
            return placement
    return None


def _refuse(doc, errs):
    return copy.deepcopy(doc), errs


def _checked(doc, new):
    """Hand back the built document only if it still satisfies the contract."""
    errs = contracts.check_document("approval", new)
    if errs:
        return _refuse(doc, ["approval manifest: " + err for err in errs])
    return new, []


def _day(value, name):
    return contracts.parse_ts(value + "T00:00:00Z", name)


def _term_errors(placement, path):
    errs = []
    for field in APPROVAL_TERMS:
        value = placement.get(field)
        if isinstance(value, list):
            if any(_missing(item) for item in value):
                errs.append("%s.%s: a blank entry is not an approved term" % (path, field))
        elif _missing(value):
            errs.append("%s.%s: an approved term must be present" % (path, field))
    return errs


# --------------------------------------------------------------------------
# contract checks
# --------------------------------------------------------------------------


def validate(doc):
    """The accepted approval contract: schema plus DATA-CONTRACTS section 10."""
    return contracts.check_document("approval", doc)


def check_revision(previous, revision):
    """Version enforcement: a new approval advances its revision.

    Equal revisions never re-approve the same campaign. When both revisions end
    in a counter, the counter must move forward. A revision with no trailing
    counter is opaque: a differing value advances.
    ponytail: opaque revisions are ordered by inequality only. Put an explicit
    revision scheme in approval-manifest.schema.json if total ordering is
    required across publishers.
    """
    if _missing(revision):
        return ["$.revision: an approval revision must be present"]
    if revision == previous:
        return ["$.revision: %r is already the current revision; an approval must advance it" % (revision,)]
    before, after = _counter(previous), _counter(revision)
    if before is None or after is None:
        return []
    if after == before:
        return ["$.revision: %r does not advance %r" % (revision, previous)]
    if after < before:
        return ["$.revision: %r rolls back %r" % (revision, previous)]
    return []


def terms_errors(doc):
    """Every bound term on every placement is present, informative and in window."""
    errs = []
    window = doc.get("campaign_window") or {}
    starts = ends = None
    try:
        starts = _day(window.get("starts_on", ""), "campaign_window.starts_on")
        ends = _day(window.get("ends_on", ""), "campaign_window.ends_on") + timedelta(days=1)
    except (contracts.UsageError, TypeError):
        starts = ends = None  # the contract names the malformed window itself
    for placement in doc.get("placements") or []:
        placement_id = placement.get("placement_id")
        path = "$.placements[%s]" % (placement_id,)
        errs.extend(_term_errors(placement, path))
        slot = placement.get("scheduled_at")
        if starts is not None and not _missing(slot):
            try:
                when = contracts.parse_ts(slot, "placements[%s].scheduled_at" % (placement_id,))
            except contracts.UsageError:
                continue  # named by the contract
            if not (starts <= when < ends):
                errs.append(
                    "%s.scheduled_at: %r is outside the joined campaign window %s..%s"
                    % (path, slot, window.get("starts_on"), window.get("ends_on"))
                )
    return errs


def _window_errors(doc, starts_on, ends_on):
    errs = []
    try:
        starts = _day(starts_on, "campaign_window.starts_on")
        ends = _day(ends_on, "campaign_window.ends_on")
    except (contracts.UsageError, TypeError) as exc:
        return [str(exc)]
    span = (ends - starts).days + 1
    if span != JOINED_WINDOW_DAYS:
        errs.append(
            "$.campaign_window: a joined campaign spans %d days, got %d"
            % (JOINED_WINDOW_DAYS, span)
        )
    previous = (doc.get("campaign_window") or {}).get("ends_on")
    if previous:
        try:
            if starts <= _day(previous, "previous campaign_window.ends_on"):
                errs.append(
                    "$.campaign_window: %s starts on or before the previous cycle's last day %s"
                    % (starts_on, previous)
                )
        except contracts.UsageError:
            pass  # the current window is the contract's to name
    return errs


# --------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------


def approve(doc, approver, approved_at, revision, expected_revision):
    """Join a DRAFT campaign into one approved revision covering every placement."""
    errs = []
    if doc.get("status") != "DRAFT":
        errs.append("$.status: only a DRAFT is joined into an approval")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(check_revision(doc.get("revision"), revision))
    if _missing(approver):
        errs.append("$.approved_by: an approval names its approver")
    errs.extend(_stamp_errors(approved_at, "approved_at"))

    placements = doc.get("placements") or []
    if not placements:
        errs.append("$.placements: a joined monthly approval binds at least one placement")
    for placement in placements:
        state = placement.get("approval_status")
        if state != "DRAFT":
            errs.append(
                "$.placements[%s]: approval is %r; re-approve that placement on its own"
                % (placement.get("placement_id"), state)
            )
    errs.extend(terms_errors(doc))
    if errs:
        return _refuse(doc, errs)

    new = copy.deepcopy(doc)
    new["revision"] = revision
    new["status"] = "APPROVED"
    new["approved_by"] = approver
    new["approved_at"] = approved_at
    for placement in new["placements"]:
        placement["approval_status"] = "APPROVED"
        placement["invalidated_at"] = None
        placement["invalidated_reason"] = None
    return _checked(doc, new)


def amend(doc, placement_id, changes, reason, at, expected_revision):
    """Change one approved placement and invalidate that placement only.

    The manifest revision is deliberately left alone. It is the campaign
    approval version shared by every placement; moving it would turn one
    placement's amendment into a stale-approval block on every unrelated
    placement, which section 10 and this task's acceptance both forbid. The
    changed placement stops dispatching because its approval_status is
    INVALIDATED and because its new terms no longer match any queued action.
    """
    errs = []
    if doc.get("status") not in SIGNED_STATUSES:
        errs.append("$.status: only an approved manifest has approved terms to amend")
    errs.extend(_cas_errors(doc, expected_revision))
    placement = _placement(doc, placement_id)
    if placement is None:
        errs.append("$.placements: %r is not in the manifest" % (placement_id,))
    if not changes:
        errs.append("$.placements[%s]: an amendment changes at least one approved term" % (placement_id,))
    unknown = sorted(set(changes) - set(APPROVAL_TERMS))
    if unknown:
        errs.append(
            "$.placements[%s]: %s is not an approved term"
            % (placement_id, ",".join(unknown))
        )
    if _missing(reason):
        errs.append(
            "$.placements[%s].invalidated_reason: an invalidation names its reason" % (placement_id,)
        )
    errs.extend(_stamp_errors(at, "placements[%s].invalidated_at" % (placement_id,)))
    if placement is not None:
        if placement.get("approval_status") != "APPROVED":
            errs.append(
                "$.placements[%s]: approval is %r, not an approved placement to amend"
                % (placement_id, placement.get("approval_status"))
            )
        if not unknown and all(placement.get(field) == value for field, value in changes.items()):
            errs.append(
                "$.placements[%s]: the amendment changes nothing, so the placement stays approved"
                % (placement_id,)
            )
    if errs:
        return _refuse(doc, errs)

    new = copy.deepcopy(doc)
    target = _placement(new, placement_id)
    for field, value in changes.items():
        target[field] = copy.deepcopy(value)
    target["approval_status"] = "INVALIDATED"
    target["invalidated_at"] = at
    target["invalidated_reason"] = reason
    new["status"] = "PARTIAL_INVALIDATED"
    errs = terms_errors({"campaign_window": new.get("campaign_window"), "placements": [target]})
    if errs:
        return _refuse(doc, errs)
    return _checked(doc, new)


def reapprove(doc, placement_id, approver, at, expected_revision):
    """Put one amended placement back to APPROVED without disturbing the others."""
    errs = []
    if doc.get("status") != "PARTIAL_INVALIDATED":
        errs.append("$.status: only a partially invalidated manifest has a placement to re-approve")
    errs.extend(_cas_errors(doc, expected_revision))
    placement = _placement(doc, placement_id)
    if placement is None:
        errs.append("$.placements: %r is not in the manifest" % (placement_id,))
    elif placement.get("approval_status") != "INVALIDATED":
        errs.append(
            "$.placements[%s]: approval is %r, not an invalidated placement"
            % (placement_id, placement.get("approval_status"))
        )
    if _missing(approver):
        errs.append("$.approved_by: a re-approval names its approver")
    errs.extend(_stamp_errors(at, "approved_at"))
    if placement is not None:
        errs.extend(
            terms_errors({"campaign_window": doc.get("campaign_window"), "placements": [placement]})
        )
    if errs:
        return _refuse(doc, errs)

    new = copy.deepcopy(doc)
    target = _placement(new, placement_id)
    target["approval_status"] = "APPROVED"
    target["invalidated_at"] = None
    target["invalidated_reason"] = None
    # approved_by/approved_at carry the latest approval event on the manifest.
    new["approved_by"] = approver
    new["approved_at"] = at
    if all(p.get("approval_status") == "APPROVED" for p in new["placements"]):
        new["status"] = "APPROVED"
    return _checked(doc, new)


def next_cycle(doc, campaign_cycle_id, starts_on, ends_on, revision, expected_revision):
    """Open the next 30-day cycle as a fresh DRAFT at a new approval revision."""
    errs = []
    if doc.get("status") not in SIGNED_STATUSES:
        errs.append("$.status: a new cycle follows a signed campaign")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(check_revision(doc.get("revision"), revision))
    if _missing(campaign_cycle_id):
        errs.append("$.campaign_cycle_id: a new cycle names itself")
    elif campaign_cycle_id == doc.get("campaign_cycle_id"):
        errs.append("$.campaign_cycle_id: %r is the current cycle" % (campaign_cycle_id,))
    errs.extend(_window_errors(doc, starts_on, ends_on))
    if errs:
        return _refuse(doc, errs)

    new = copy.deepcopy(doc)
    new["campaign_cycle_id"] = campaign_cycle_id
    new["campaign_window"] = {"starts_on": starts_on, "ends_on": ends_on}
    new["revision"] = revision
    new["status"] = "DRAFT"
    new["approved_by"] = None
    new["approved_at"] = None
    for placement in new["placements"]:
        placement["approval_status"] = "DRAFT"
        placement["invalidated_at"] = None
        placement["invalidated_reason"] = None
    return _checked(doc, new)

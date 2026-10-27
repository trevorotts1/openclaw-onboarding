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
  check_revision()     version enforcement: a new approval advances its
                       revision, never repeating it and never rolling back
                       (see that function for exactly what "rolling back"
                       can be proven to mean)
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
result. That holds for a malformed document too: manifests are loaded from
files, so a wrong-shaped document or field is refused with the field named and
never raised at the caller. stdlib only.

  from monthly_manifest import approve, amend, reapprove, next_cycle
  doc, errs = approve(doc, "client-owner-1", "2026-10-20T18:00:00Z", "rev-3", "rev-2")
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import sys
from datetime import timedelta
from pathlib import Path

VERSION = "1.0.2"

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

_NUMBER_RUN = re.compile(r"\d+")


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


def _number_run(revision):
    """The revision's own digits, in order, as ints.

    A revision scheme is whatever its publisher writes: a counter (``rev-3``),
    a date (``2026-12-01``), a semantic version (``v2.0``). What is comparable
    across those is the run of numbers inside the revision, compared position by
    position. The run is read from the whole revision, never out of a trailing
    word, so ``rev-2-final`` is the counter 2 however the tag ends.
    """
    if not isinstance(revision, str):
        return ()
    return tuple(int(part) for part in _NUMBER_RUN.findall(revision))


def _placements(doc):
    """Only placement objects are iterated; anything else is the contract's to name.

    ``doc["placements"]`` is read from a file, so a caller can arrive with a
    string, a map or a list holding a null. Those shapes are refused below; this
    predicate keeps the loops from turning one into an AttributeError.
    """
    value = doc.get("placements")
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _placements_errors(doc):
    value = doc.get("placements")
    if value is None:
        return []  # absent placements are the schema's to name, and approve() requires one
    if isinstance(value, list) and all(isinstance(item, dict) for item in value):
        return []
    return ["$.placements: must be a list of placement objects"]


def _document_errors(doc):
    if not isinstance(doc, dict):
        return ["$: an approval manifest must be a JSON object, got %s" % type(doc).__name__]
    return []


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
    for placement in _placements(doc):
        if placement.get("placement_id") == placement_id:
            return placement
    return None


def _refuse(doc, errs):
    return copy.deepcopy(doc), errs


def _checked(doc, new):
    """Hand back the built document only if it still satisfies the contract."""
    errs = validate(new)
    if errs:
        return _refuse(doc, ["approval manifest: " + err for err in errs])
    return new, []


def _day(value, name):
    """A YYYY-MM-DD day as UTC midnight. A non-string is named, never raised."""
    if isinstance(value, str):
        value = value + "T00:00:00Z"
    return contracts.parse_ts(value, name)


def _window(doc):
    """The joined window as (first day, last day), or the errors naming why not.

    ``campaign_window`` is read from a file like the rest of the manifest, so a
    string, a number, a list or an unreadable day is refused with the field
    named, never raised. The accepted contract raises on an unreadable day
    rather than naming it, so the window is read here before the contract sees
    it.
    """
    window = doc.get("campaign_window")
    if not isinstance(window, dict):
        return None, [
            "$.campaign_window: must be an object holding starts_on and ends_on, got %s"
            % type(window).__name__
        ]
    try:
        return (
            _day(window.get("starts_on"), "campaign_window.starts_on"),
            _day(window.get("ends_on"), "campaign_window.ends_on"),
        ), []
    except contracts.UsageError as exc:
        return None, [str(exc)]


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
    """The accepted approval contract: schema plus DATA-CONTRACTS section 10.

    The contract raises UsageError on a well-typed but unreadable window day;
    that is a refusal with the field named, so it is returned, not raised.
    """
    try:
        return contracts.check_document("approval", doc)
    except contracts.UsageError as exc:
        return [str(exc)]


def check_revision(previous, revision):
    """Version enforcement: a new approval advances its revision.

    Every revision that carries numbers is ordered by its number run, compared
    position by position and numerically: ``2026-12-01`` advances
    ``2026-11-01``, ``v2.0`` advances ``v1.0``, and ``rev-2-final`` or
    ``rev-2-approval`` is a rollback of ``rev-3`` whatever word trails the
    number. A number is never read out of a trailing word, so no suffix
    heuristic can hide a rollback. A revision with no digits at all is opaque
    and advances by inequality, as promised: any differing value is a new
    approval, and only a repeat is refused.

    Two revisions that cannot be ordered against each other — one numbered, one
    not — are refused rather than guessed at. This function promises a revision
    never rolls back, so an order it cannot prove is not an advance.

    ponytail: opaque revisions are ordered by inequality only, and a scheme
    change is refused rather than interpreted. Put an explicit revision scheme
    in approval-manifest.schema.json if total ordering is required across
    publishers.
    """
    if _missing(revision):
        return ["$.revision: an approval revision must be present"]
    if not isinstance(revision, str):
        return ["$.revision: an approval revision must be a string, got %s" % type(revision).__name__]
    if revision == previous:
        return ["$.revision: %r is already the current revision; an approval must advance it" % (revision,)]
    before, after = _number_run(previous), _number_run(revision)
    if not before and not after:
        return []  # opaque revisions: a differing value advances
    if not before or not after:
        return [
            "$.revision: %r does not advance %r; the two revisions cannot be ordered"
            % (revision, previous)
        ]
    if after == before:
        return ["$.revision: %r does not advance %r" % (revision, previous)]
    if after < before:
        return ["$.revision: %r rolls back %r" % (revision, previous)]
    return []


def terms_errors(doc):
    """Every bound term on every placement is present, informative and in window.

    A schedule cannot be proven inside a window that cannot be read, so a
    wrong-shaped document, window or placement list is an error here too.
    """
    errs = _document_errors(doc)
    if errs:
        return errs
    window, errs = _window(doc)
    errs.extend(_placements_errors(doc))
    if window is not None:
        starts, ends = window[0], window[1] + timedelta(days=1)
    for placement in _placements(doc):
        placement_id = placement.get("placement_id")
        path = "$.placements[%s]" % (placement_id,)
        errs.extend(_term_errors(placement, path))
        slot = placement.get("scheduled_at")
        if window is not None and not _missing(slot):
            try:
                when = contracts.parse_ts(slot, "placements[%s].scheduled_at" % (placement_id,))
            except contracts.UsageError:
                continue  # named by the contract
            if not (starts <= when < ends):
                errs.append(
                    "%s.scheduled_at: %r is outside the joined campaign window %s..%s"
                    % (path, slot, doc["campaign_window"]["starts_on"], doc["campaign_window"]["ends_on"])
                )
    return errs


def _window_errors(doc, starts_on, ends_on):
    errs = []
    try:
        starts = _day(starts_on, "campaign_window.starts_on")
        ends = _day(ends_on, "campaign_window.ends_on")
    except contracts.UsageError as exc:
        return [str(exc)]
    except TypeError:
        return ["$.campaign_window: starts_on and ends_on must be ISO dates"]
    span = (ends - starts).days + 1
    if span != JOINED_WINDOW_DAYS:
        errs.append(
            "$.campaign_window: a joined campaign spans %d days, got %d"
            % (JOINED_WINDOW_DAYS, span)
        )
    # No overlap with the cycle being closed. An unreadable previous window
    # cannot prove that, so it is refused rather than skipped.
    previous, window_errs = _window(doc)
    if previous is None:
        return errs + window_errs
    if starts <= previous[1]:
        errs.append(
            "$.campaign_window: %s starts on or before the previous cycle's last day %s"
            % (starts_on, doc["campaign_window"]["ends_on"])
        )
    return errs


# --------------------------------------------------------------------------
# lifecycle
# --------------------------------------------------------------------------


def approve(doc, approver, approved_at, revision, expected_revision):
    """Join a DRAFT campaign into one approved revision covering every placement."""
    errs = _document_errors(doc)
    if errs:
        return _refuse(doc, errs)
    if doc.get("status") != "DRAFT":
        errs.append("$.status: only a DRAFT is joined into an approval")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(check_revision(doc.get("revision"), revision))
    if _missing(approver):
        errs.append("$.approved_by: an approval names its approver")
    errs.extend(_stamp_errors(approved_at, "approved_at"))

    shape = _placements_errors(doc)  # named by terms_errors below
    placements = _placements(doc)
    if not placements and not shape:
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
    for placement in _placements(new):
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
    errs = _document_errors(doc)
    if errs:
        return _refuse(doc, errs)
    if doc.get("status") not in SIGNED_STATUSES:
        errs.append("$.status: only an approved manifest has approved terms to amend")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(_placements_errors(doc))
    placement = _placement(doc, placement_id)
    if placement is None:
        errs.append("$.placements: %r is not in the manifest" % (placement_id,))
    if not isinstance(changes, dict):
        errs.append(
            "$.placements[%s]: an amendment is a map of approved term to its new value"
            % (placement_id,)
        )
    elif not changes:
        errs.append("$.placements[%s]: an amendment changes at least one approved term" % (placement_id,))
    unknown = sorted(set(changes) - set(APPROVAL_TERMS)) if isinstance(changes, dict) else []
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
        if isinstance(changes, dict) and not unknown and all(
            placement.get(field) == value for field, value in changes.items()
        ):
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
    errs = _document_errors(doc)
    if errs:
        return _refuse(doc, errs)
    if doc.get("status") != "PARTIAL_INVALIDATED":
        errs.append("$.status: only a partially invalidated manifest has a placement to re-approve")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(_placements_errors(doc))
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


def check_manifest(doc, placements=None, expected_revision=None, advance_from=None):
    """Publishing gate: the manifest is APPROVED and every named placement is too.

    This is the ONE call the publishing cycle makes before a Purple placement
    goes out (review C3 step 7). It never re-implements the approval contract:
    `validate` is the accepted schema check, `check_revision` is the accepted
    version enforcement, and `terms_errors` is the accepted term/window check.

    ``placements`` narrows the check to named placements (a per-placement
    publish); omitted, EVERY placement in the manifest must be APPROVED.
    ``advance_from`` proves the manifest's revision advanced past a known
    previous revision. Returns a list of refusals; empty means publishable.
    """
    if not isinstance(doc, dict):
        return ["$: an approval manifest must be a JSON object, got %s" % type(doc).__name__]
    errs = validate(doc)
    if errs:
        return errs
    errs.extend(terms_errors(doc))
    status = doc.get("status")
    if status not in SIGNED_STATUSES:
        errs.append("$.status: %r is not an approved manifest" % (status,))
    if expected_revision is not None and doc.get("revision") != expected_revision:
        errs.append(
            "$.revision: expected %r but the manifest is at %r"
            % (expected_revision, doc.get("revision"))
        )
    if advance_from is not None:
        errs.extend(check_revision(advance_from, doc.get("revision")))
    wanted = list(placements or [])
    if wanted:
        for placement_id in wanted:
            placement = _placement(doc, placement_id)
            if placement is None:
                errs.append("$.placements: %r is not in the manifest" % (placement_id,))
                continue
            state = placement.get("approval_status")
            if state != "APPROVED":
                errs.append(
                    "$.placements[%s]: approval is %r; publication requires APPROVED"
                    % (placement_id, state)
                )
    else:
        for placement in _placements(doc):
            state = placement.get("approval_status")
            if state != "APPROVED":
                errs.append(
                    "$.placements[%s]: approval is %r; publication requires APPROVED"
                    % (placement.get("placement_id"), state)
                )
    return errs


def main(argv=None):
    """`check` — the command-line publishing gate (review C3 step 7).

    Exit codes: 0 publishable, 2 unreadable input or usage, 3 refused.
    """
    parser = argparse.ArgumentParser(
        prog="monthly_manifest.py",
        description="Joined monthly approval manifest",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="refuse unless the manifest is approved for publication")
    check.add_argument("--manifest", required=True, help="path to the approval manifest JSON")
    check.add_argument(
        "--placement",
        action="append",
        default=[],
        help="placement_id to check (repeatable); omitted checks every placement",
    )
    check.add_argument("--expected-revision", default=None, help="require this exact revision")
    check.add_argument(
        "--advance-from",
        default=None,
        help="require the manifest revision to advance past this previous revision",
    )
    args = parser.parse_args(argv)

    try:
        with open(args.manifest, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as exc:
        print(json.dumps({"ok": False, "error": "unreadable manifest: %s" % exc}))
        return 2

    errs = check_manifest(
        doc,
        placements=args.placement,
        expected_revision=args.expected_revision,
        advance_from=args.advance_from,
    )
    if errs:
        print(json.dumps({"ok": False, "manifest": args.manifest, "errors": errs}, indent=2))
        return 3
    print(
        json.dumps(
            {
                "ok": True,
                "manifest": args.manifest,
                "revision": doc.get("revision"),
                "placements": args.placement
                or [p.get("placement_id") for p in _placements(doc)],
            },
            indent=2,
        )
    )
    return 0


def next_cycle(doc, campaign_cycle_id, starts_on, ends_on, revision, expected_revision):
    """Open the next 30-day cycle as a fresh DRAFT at a new approval revision."""
    errs = _document_errors(doc)
    if errs:
        return _refuse(doc, errs)
    if doc.get("status") not in SIGNED_STATUSES:
        errs.append("$.status: a new cycle follows a signed campaign")
    errs.extend(_cas_errors(doc, expected_revision))
    errs.extend(check_revision(doc.get("revision"), revision))
    errs.extend(_placements_errors(doc))
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
    for placement in _placements(new):
        placement["approval_status"] = "DRAFT"
        placement["invalidated_at"] = None
        placement["invalidated_reason"] = None
    return _checked(doc, new)


if __name__ == "__main__":
    sys.exit(main())

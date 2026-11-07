#!/usr/bin/env python3
"""revision.py -- one proposal-acceptance transition and one revision reconciliation.

WHY THIS IS ONE FILE
--------------------
Skill 49 (signature funnel) and Skill 83 (Black Friday launcher) both keep an answer
ledger and both build offers and a compiled route from it. Two rules must be the same
code in both or the two skills drift:

  1. ACCEPTING AN AI PROPOSAL is one transition: the approval record is named, the
     prior state and provenance are kept, and nothing is accepted anonymously.
  2. A REVISION THAT DISABLES UPSALE 1 (U1) reconsiders the saved DOWNSALE 1 (D1) and
     UPSELL 2 (U2) answers and offers. The route compiler refuses a graph where U1 is
     disabled and D1/U2 are enabled, and the page/email/automation planners derive their
     units from the enabled offers, so a stale dependent offer is a stale page, a stale
     follow-up email and a stale route node all at once. Reconciliation removes them
     here, by name, and records why.

ANSWER PROVENANCE IS NEVER FLATTENED
------------------------------------
Every answer keeps one of five kinds, before and after either transition:

  confirmed_fact                supplied or verified by the client/clerk
  ai_proposal                   recommended_unapproved / suggested / default_to_confirm
  user_selected_recommendation  the client picked our proposal (accepted, palette-help,
                                feel-words)
  generated_asset               a produced artifact (an asset reference, not a statement)
  unresolved_capability         unknown, or a capability the record cannot carry

PROVENANCE VOCABULARIES BOTH SKILLS USE
--------------------------------------
Skill 49's session ledger stores ``state`` with the launch-intake states
(provided / verified_existing / recommended_unapproved / approved_recommendation /
unknown / not_applicable). The shared client intake (answers.schema.json) stores
``status`` with provided / suggested / default_to_confirm / unknown. This module reads
either and writes back only the key the entry already has, so neither skill is forced
into the other's vocabulary.

If the answers file has no accepted state, acceptance is RECORDED on the entry
(``accepted``: approval ref, plan hash, time, prior state and provenance) instead of
being written as ``provided``: a suggestion that only reached the plan through an
approval must never read as a fact the client supplied.

Stdlib only. No network, no model, no file writes: callers own their ledgers.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

PROVENANCE_KINDS = ("confirmed_fact", "ai_proposal", "user_selected_recommendation",
                    "generated_asset", "unresolved_capability")

CONFIRMED_STATES = ("provided", "verified_existing", "approved_recommendation")
PROPOSAL_STATES = ("recommended_unapproved", "suggested", "default_to_confirm")
UNRESOLVED_STATES = ("unknown",)
NOT_APPLICABLE = "not_applicable"

# The only accepted state this module may WRITE. The shared answers file has no accepted
# state, so an answers-file entry keeps its status and carries `accepted` instead (see the
# module docstring: a proposal is never relabelled as a supplied fact).
ACCEPTED_STATE = {"recommended_unapproved": "approved_recommendation"}

# Which offers depend on which. Disabling U1 removes D1 and U2 (the route law: "U1 disabled
# REQUIRES D1 and U2 disabled"), and the same table is the whole dependency graph walk.
DEPENDENT_SLOTS = {"upsell_1": ("downsell_1", "upsell_2")}
EXTRAS_KEYS = ("upsell_1", "downsell_1", "upsell_2")
_ACCEPTANCE_REFS = ("approval_id", "approval_ref", "ref", "id")
_ACCEPTANCE_BINDS = ("plan_hash", "subject_hash", "hash")
_SLOTS = ("upsell_1", "downsell_1", "upsell_2")


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _value_of(entry: Any) -> Any:
    return entry.get("value") if isinstance(entry, dict) else None


def state_of(entry: Any) -> Optional[str]:
    """The entry's own state word: Skill 49 stores ``state``, the answers file ``status``."""
    if not isinstance(entry, dict):
        return None
    return entry.get("state") or entry.get("status")


def _write_state(entry: Dict[str, Any], state: str) -> None:
    """Write back into the key the entry already uses, so no consumer sees a foreign word."""
    entry["state" if "state" in entry else "status"] = state


def provenance_kind(entry: Any) -> str:
    """One of PROVENANCE_KINDS for an answer entry, from its own words only."""
    if not isinstance(entry, dict):
        return "unresolved_capability"
    state = state_of(entry)
    value = _value_of(entry)
    source = str(entry.get("source") or "")
    if isinstance(entry.get("accepted"), dict) and entry["accepted"].get("approval_ref"):
        return "user_selected_recommendation"
    if isinstance(value, dict) and (value.get("generated") is True
                                    or value.get("asset_ref") or value.get("generated_asset_ref")):
        return "generated_asset"
    if state in UNRESOLVED_STATES or (state is None and value is None):
        return "unresolved_capability"
    if state in PROPOSAL_STATES:
        return "ai_proposal"
    if source.startswith("palette-help") or source in ("feel-words", "recommended-option"):
        return "user_selected_recommendation"
    return "confirmed_fact"


# ---------------------------------------------------------------------------
# 1. The one proposal-acceptance transition.
# ---------------------------------------------------------------------------
def acceptance_ref(acceptance: Any) -> Tuple[str, Dict[str, str]]:
    """(approval ref, the hashes it binds) or ValueError. Never an anonymous acceptance."""
    if not isinstance(acceptance, Mapping):
        raise ValueError("acceptance must be the approval record that accepted these proposals")
    ref = next((acceptance.get(k) for k in _ACCEPTANCE_REFS
                if isinstance(acceptance.get(k), str) and acceptance[k].strip()), None)
    if ref is None:
        raise ValueError("the acceptance record names no approval id; a proposal is never accepted anonymously")
    if acceptance.get("revoked") is True:
        raise ValueError("the acceptance record is revoked; the proposals stay proposals")
    binds = {k: acceptance[k] for k in _ACCEPTANCE_BINDS
             if isinstance(acceptance.get(k), str) and acceptance[k].strip()}
    return ref.strip(), binds


def accept_proposals(ledger: Optional[Mapping[str, Any]], acceptance: Mapping[str, Any], *,
                     accepted_at: Optional[str] = None) -> Dict[str, Any]:
    """The ONE proposal-acceptance transition, shared by Skill 49 and Skill 83.

    Every proposal entry gains an ``accepted`` block naming the approval that accepted it,
    the prior state and the prior provenance kind. Skill 49's launch-intake state advances
    to ``approved_recommendation`` (its own accepted state); an answers-file entry keeps its
    status, because that format has no accepted state and a suggestion must never be
    relabelled as a supplied fact.

    Returns {"approval_ref", "accepted": [...], "untouched": [keys]}. Confirmed facts,
    generated assets, not_applicable decisions and unknowns are untouched by construction.
    """
    ref, binds = acceptance_ref(acceptance)
    at = accepted_at or _now()
    accepted: List[Dict[str, Any]] = []
    untouched: List[str] = []
    for key, entry in (ledger or {}).items():
        state = state_of(entry)
        if state not in PROPOSAL_STATES:
            untouched.append(key)
            continue
        kind = provenance_kind(entry)
        new_state = ACCEPTED_STATE.get(state)
        if new_state is not None:
            _write_state(entry, new_state)
        entry["accepted"] = {"approval_ref": ref, "at": at, "from_state": state,
                             "from_provenance": kind, **binds}
        accepted.append({"key": key, "from_state": state, "to_state": new_state or state,
                         "provenance": kind})
    return {"approval_ref": ref, "accepted": accepted, "untouched": untouched}


# ---------------------------------------------------------------------------
# 2. The one revision reconciliation.
# ---------------------------------------------------------------------------
def disabled_slots(*, extras: Optional[Mapping[str, Any]] = None,
                   offers: Optional[Iterable[Any]] = None) -> List[str]:
    """The slots this revision has disabled.

    A launcher extras answer says it outright (``False``). A payload that carries offers but
    no extras expresses the same thing by absence: no offer with that role. Unknown is never
    read as disabled -- with neither signal the slot is left alone.
    """
    out: List[str] = []
    carried = offers is not None
    roles = {(o.get("role") or o.get("slot")) for o in (offers or ()) if isinstance(o, Mapping)}
    for slot in _SLOTS:
        if extras is not None and extras.get(slot) is False:
            out.append(slot)
        elif carried and slot not in roles:
            out.append(slot)
    return out


def reconcile_launch(ledger: Optional[Dict[str, Any]], *, revision: int,
                     offers: Optional[Iterable[Dict[str, Any]]] = None,
                     extras: Optional[Dict[str, Any]] = None,
                     answer_prefix: str = "",
                     extras_key: Optional[str] = None,
                     disabled: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Reconcile one revision's dependent offers, answers and extras. Mutates in place.

    ``ledger``   answers keyed by field; Skill 49 uses ``offers.<slot>`` (answer_prefix
                 "offers."), the answers file uses the bare slot names.
    ``extras``   the launcher's {upsell_1, downsell_1, upsell_2} flags, when it has them.
    ``offers``   the offers built or supplied this revision; dependent ones are REMOVED
                 from the list the caller passed.

    Returns the report. ``dependent_slots`` are the offers/routes that must not survive;
    ``reconciled_answers`` keeps every prior state, provenance kind and value of the answer
    it replaced; ``kept_answers`` names everything else, which is the proof that unrelated
    brand, calendar and context answers were not touched.
    """
    ledger = ledger if ledger is not None else {}
    offs = list(offers or ())
    report: Dict[str, Any] = {
        "revision": revision, "disabled": [], "dependent_slots": [],
        "reconciled_answers": [], "removed_offers": [], "kept_answers": [],
        "client_notices": [],
    }
    report["disabled"] = (list(disabled) if disabled is not None
                          else disabled_slots(extras=extras, offers=offs if offers is not None else None))
    if not report["disabled"]:
        report["kept_answers"] = list(ledger)
        return report
    dependents: List[str] = []
    for slot in report["disabled"]:
        for dependent in DEPENDENT_SLOTS.get(slot, ()):
            if dependent not in dependents:
                dependents.append(dependent)
    report["dependent_slots"] = dependents
    if not dependents:
        report["kept_answers"] = list(ledger)
        return report

    reason = (f"revision {revision} disables "
              + " and ".join(report["disabled"])
              + f", so {', '.join(dependents)} cannot be offered, routed or planned")

    for slot in dependents:
        key = f"{answer_prefix}{slot}"
        entry = ledger.get(key)
        prior_state = state_of(entry)
        if isinstance(entry, dict) and prior_state != NOT_APPLICABLE:
            kind = provenance_kind(entry)
            prior_value = entry.get("value")
            prior_source = entry.get("source")
            existed = True
        else:
            kind = None
            prior_value = None
            prior_source = None
            existed = isinstance(entry, dict)
        if existed:
            note = {"revision": revision, "rule": "upsell_1_disabled",
                    "disabled": list(report["disabled"]), "reason": reason,
                    "from_state": prior_state, "from_provenance": kind,
                    "previous_value": prior_value, "previous_source": prior_source}
            if isinstance(entry.get("reconciled"), dict):
                note["previous_reconciled"] = entry["reconciled"]
            entry["reconciled"] = note
            _write_state(entry, NOT_APPLICABLE)
            entry["value"] = None
            report["reconciled_answers"].append(
                {"key": key, "slot": slot, "from_state": prior_state,
                 "from_provenance": kind, "previous_value": prior_value})
            if kind == "confirmed_fact":
                report["client_notices"].append(
                    f"{slot} was supplied by the client before this revision; "
                    f"{reason}. Tell the client it has been removed and why; do not rebuild it silently.")
        for offer in [o for o in offs if isinstance(o, dict) and (o.get("role") or o.get("slot")) == slot]:
            report["removed_offers"].append({"slot": slot, "offer_id": offer.get("offer_id"),
                                             "display_name": offer.get("display_name") or offer.get("name")})
            offs.remove(offer)
        if extras is not None and slot in extras:
            extras[slot] = False

    if extras_key and isinstance(ledger.get(extras_key), dict):
        entry = ledger[extras_key]
        entry.setdefault("reconciled", {"revision": revision, "rule": "upsell_1_disabled",
                                        "reason": reason, "disabled": list(report["disabled"]),
                                        "cleared": list(dependents)})

    touched = {row["key"] for row in report["reconciled_answers"]}
    report["kept_answers"] = [k for k in ledger if k not in touched]
    report["offers"] = offs  # the surviving list, in order
    return report

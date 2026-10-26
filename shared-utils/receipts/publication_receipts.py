#!/usr/bin/env python3
"""publication_receipts.py - ordered post/reveal receipts and partial resume.

Task PBB-119 / T-25. Contract basis: Purple-Billboard SPEC.md "Publish then
ordered comments over minutes, not an invented one-minute absolute" and
"Verify actual post/comment receipts and resume only missing approved pieces";
DATA-CONTRACTS.md sections 2, 3, 4 and 10.

This module adds the three things no accepted upstream module owns:

  TRUE RECEIPTS   A publication counts only when the provider's own object id
                  was persisted through the fenced outbox. A claim, a local id
                  echoed back, a comment receipt with no parent post, or an
                  unsupported status never counts.
  APPROVED ORDER  Publication follows the approved manifest placement order and,
                  inside a placement, the post before its comments. The approved
                  binding itself is pb_contracts.approval_errors - not a second
                  copy of it.
  PARTIAL RESUME  Resume returns the missing approved pieces only, in order, and
                  never re-issues a receipted item or a possibly-sent effect.

There is deliberately NO minimum gap between the post and its comments. The
taught sequence is a post and ordered comments a few seconds apart; a strict
under-one-minute rule is an invention, and `reveal_timing_errors` refuses only a
comment that precedes its post.

Import:

    import sys
    from pathlib import Path
    sys.path.insert(0, "<repo>/shared-utils/receipts")
    from publication_receipts import resume_plan

Python 3 standard library only. Reuses 38-conversational-ai-system/tools/
pb_contracts.py (approval binding, id normaliser, status set) and
durable_store.py (fenced receipts, action state).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

REPO_ROOT = Path(__file__).resolve().parents[2]
SKILL38_TOOLS = REPO_ROOT / "38-conversational-ai-system" / "tools"
if str(SKILL38_TOOLS) not in sys.path:
    sys.path.insert(0, str(SKILL38_TOOLS))

import pb_contracts as contracts  # noqa: E402

# Purpose -> the provider object kind that proves it happened.
PURPOSE_KIND = {
    "SCHEDULED_POST": "post",
    "REVEAL_COMMENT": "comment",
    "BONUS_COMMENT": "comment",
}
# Inside one placement: the post first, then its comments in approved order.
ORDER_RANK = {"SCHEDULED_POST": 0, "REVEAL_COMMENT": 1, "BONUS_COMMENT": 2}
# Receipt kinds durable_store persists, strongest publication evidence first.
PERSISTED_RECEIPT_KINDS = ("dispatch", "ack", "completion")
# A receipted provider object exists only for these statuses.
PUBLISHED_STATUSES = ("accepted", "sent", "delivered")
# Fields whose value a locally generated "receipt" could echo back at us.
LOCAL_ID_FIELDS = ("action_id", "logical_intent_key", "idempotency_key")
# Durable states in which the same action may be dispatched again: known
# nonexecution (not_requested/queued/failed). Everything else is either already
# receipted, suppressed by policy, or a possibly-sent effect awaiting reconcile.
RESUMABLE_STATES = frozenset({"not_requested", "queued", "failed"})

# Publication evidence is a subset of the contract's receipt statuses; if the
# contract narrows, this import fails loudly instead of drifting.
assert set(PUBLISHED_STATUSES) <= set(contracts.RECEIPT_STATUSES), (
    "published statuses must remain contract receipt statuses"
)


class ReceiptError(ValueError):
    """Malformed plan input. Fail closed: nothing is published."""


def _blank(value: Any) -> bool:
    """True when a value carries no identifier. Reuses the T-08d normaliser."""
    return contracts.normalise_evidence_id(value) is None


def _same_id(a: Any, b: Any) -> bool:
    """Identity, not spelling: both sides through the T-08d normaliser."""
    return contracts.normalise_evidence_id(a) == contracts.normalise_evidence_id(b)


def _plan_item(item: Any) -> Mapping[str, Any]:
    if not isinstance(item, Mapping):
        raise ReceiptError(
            "$.items: a plan item must be an object, got %s" % (type(item).__name__,)
        )
    return item


def _provider_id_errors(item: Mapping[str, Any], field: str, value: Any) -> List[str]:
    """A non-blank provider id must be a string and not a local id echoed back."""
    if not isinstance(value, str):
        return ["$.%s: must be a string, got %r" % (field, type(value).__name__)]
    for local_field in LOCAL_ID_FIELDS:
        local = item.get(local_field)
        if isinstance(local, str) and local and _same_id(value, local):
            return [
                "$.%s: %r echoes the local %s, not a provider object"
                % (field, value, local_field)
            ]
    return []


def item_kind(purpose: Any) -> str:
    kind = PURPOSE_KIND.get(purpose) if isinstance(purpose, str) else None
    if kind is None:
        raise ReceiptError(
            "$.purpose: %r has no post/comment receipt kind (expected one of %s)"
            % (purpose, sorted(PURPOSE_KIND))
        )
    return kind


def item_key(item: Mapping[str, Any]) -> str:
    key = _plan_item(item).get("logical_intent_key")
    if _blank(key) or not isinstance(key, str):
        raise ReceiptError("$.logical_intent_key: a plan item needs its logical intent key")
    return key


def validate_provider_receipt(
    item: Mapping[str, Any],
    receipt: Any,
    expected_parent: Optional[str] = None,
) -> List[str]:
    """Errors for a receipt that is not the provider's own post/comment object.

    A clean return means: the provider named its own object, the object kind
    matches the purpose, the status is a published status, and a comment names
    the post it was published under.
    """
    try:
        purpose = _plan_item(item).get("purpose")
        kind = item_kind(purpose)
    except ReceiptError as exc:
        return [str(exc)]
    if not isinstance(receipt, Mapping):
        return ["$: a provider receipt must be an object"]

    errs: List[str] = []
    if _blank(receipt.get("provider")):
        errs.append("$.provider: a true receipt names the provider that returned it")

    # Every id compare below is by identity, not spelling: the normaliser strips
    # the padding a locally generated "receipt" would decorate an echo with, and
    # the padding a real provider id may carry.
    object_id = receipt.get("provider_object_id")
    if _blank(object_id):
        errs.append("$.provider_object_id: a true receipt carries the provider's own object id")
    else:
        errs.extend(_provider_id_errors(item, "provider_object_id", object_id))

    got = receipt.get("kind")
    if got != kind:
        errs.append("$.kind: a %s receipt is a %s object, got %r" % (purpose, kind, got))

    status = receipt.get("supported_status")
    if status not in PUBLISHED_STATUSES:
        errs.append(
            "$.supported_status: %r is not publication evidence (expected one of %s)"
            % (status, list(PUBLISHED_STATUSES))
        )

    if kind == "comment":
        parent = receipt.get("parent_provider_object_id")
        if _blank(parent):
            errs.append(
                "$.parent_provider_object_id: a comment receipt names the post it was published under"
            )
            return errs
        parent_errs = _provider_id_errors(item, "parent_provider_object_id", parent)
        errs.extend(parent_errs)
        if not parent_errs and expected_parent is not None and not _same_id(parent, expected_parent):
            errs.append(
                "$.parent_provider_object_id: %r is not the receipted post %r"
                % (parent, expected_parent)
            )
    return errs


def true_receipt(
    store: Any,
    item: Mapping[str, Any],
    expected_parent: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """The persisted provider receipt for an item, or None.

    Only receipts written through the fenced outbox count. An unpersisted claim,
    or a persisted receipt that fails validate_provider_receipt, returns None -
    the item stays missing rather than being silently marked published.
    """
    key = _plan_item(item).get("logical_intent_key")
    if _blank(key) or not isinstance(key, str):
        return None
    row = store.action_by_intent(key)
    if row is None:
        return None
    receipts = store.receipts(row["action_id"])
    for kind in PERSISTED_RECEIPT_KINDS:
        record = receipts.get(kind)
        if record is None:
            continue
        payload = record.get("payload") or {}
        if not validate_provider_receipt(item, payload, expected_parent=expected_parent):
            return dict(payload)
    return None


def approved_order(
    manifest: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    manifest_path: str,
) -> Dict[str, Any]:
    """Validate plan items and return them in approved publication order.

    Placement binding is delegated to pb_contracts.approval_errors (the accepted
    T-23 guard). This function owns only what that guard does not: the sequence
    inside a placement, duplicate keys, and an unknown placement id.
    """
    manifest_errs = contracts.check_document("approval", manifest)
    if manifest_errs:
        raise ReceiptError("approval manifest: " + "; ".join(manifest_errs))
    if manifest["status"] not in {"APPROVED", "PARTIAL_INVALIDATED"}:
        raise ReceiptError("$.status: manifest is %r, nothing may be published" % (manifest["status"],))
    if manifest.get("campaign_window") is None:
        raise ReceiptError("$.campaign_window: a plan needs the approved campaign window")
    try:
        items = list(items)
    except TypeError:
        raise ReceiptError(
            "$.items: a plan is a list of items, got %s" % (type(items).__name__,)
        ) from None

    placement_index = {p["placement_id"]: i for i, p in enumerate(manifest["placements"])}
    entries: List[Dict[str, Any]] = []
    seen = set()
    problems: List[str] = []
    for position, item in enumerate(items):
        key = item_key(item)
        if key in seen:
            raise ReceiptError("$.items: duplicate item %r" % (key,))
        seen.add(key)
        if item.get("scope") != "public_placement":
            raise ReceiptError(
                "$.items[%d].scope: %r is not a public placement"
                % (position, item.get("scope"))
            )
        purpose = item.get("purpose")
        rank = ORDER_RANK.get(purpose) if isinstance(purpose, str) else None
        if rank is None:
            raise ReceiptError(
                "$.items[%d].purpose: %r is not a published post/comment purpose"
                % (position, purpose)
            )
        placement_id = item.get("placement_id")
        index = placement_index.get(placement_id) if isinstance(placement_id, str) else None
        if index is None:
            raise ReceiptError(
                "$.items[%d].placement_id: %r is not in the approved manifest"
                % (position, placement_id)
            )
        entries.append(
            {
                "item": item,
                "key": key,
                "position": position,
                "placement_id": placement_id,
                "placement_index": index,
                "rank": rank,
                "errors": contracts.approval_errors(item, manifest_path),
            }
        )

    by_placement: Dict[str, List[Dict[str, Any]]] = {}
    for entry in entries:
        by_placement.setdefault(entry["placement_id"], []).append(entry)
    for placement_id, group in by_placement.items():
        posts = [e for e in group if e["rank"] == ORDER_RANK["SCHEDULED_POST"]]
        if len(posts) > 1:
            problems.append(
                "$.order: placement %r has more than one scheduled post" % (placement_id,)
            )
        if not posts:
            problems.append(
                "$.order: placement %r has comments but no scheduled post" % (placement_id,)
            )

    # The canonical sequence inside a placement is the post, then the comments
    # in the approved content order the caller listed them in. Input order
    # across placements is irrelevant: the manifest owns that.
    entries.sort(key=lambda e: (e["placement_index"], e["rank"], e["position"]))
    return {"order": entries, "errors": problems}


def _resume_block_reason(row: Optional[Mapping[str, Any]]) -> Optional[str]:
    """Why the same action may not be dispatched again, or None if it may."""
    if row is None:
        return "NOT_ADMITTED"
    state = row.get("state")
    if state in RESUMABLE_STATES:
        return None
    if state == "unknown":
        return "STATE_UNKNOWN"
    if state in {"dispatched", "acknowledged", "completed"}:
        return "EFFECT_WITHOUT_TRUE_RECEIPT"
    if state == "canceled":
        return "CANCELED"
    if state == "suppressed":
        return "SUPPRESSED"
    if state == "quarantined":
        return "QUARANTINED"
    return "STATE_%s" % str(state).upper()


def resume_plan(
    store: Any,
    manifest: Mapping[str, Any],
    items: Sequence[Mapping[str, Any]],
    manifest_path: str,
) -> Dict[str, Any]:
    """Resume the missing approved pieces only, in approved order.

    Returns:
      ok               no structural order errors
      resume           items to publish in this pass, approved order
      blocked          missing items that must not be published now, with reason
      already_received items with a true provider receipt
      unapproved       items the approved manifest does not currently bind
      errors           structural problems (post-after-comment, 2 posts, ...)

    A comment whose post is missing is blocked, not resume: the post's provider
    id does not exist until it is published, so the next pass resumes it.
    """
    ordered = approved_order(manifest, items, manifest_path)
    resume: List[str] = []
    blocked: List[Dict[str, str]] = []
    received: List[str] = []
    unapproved: List[Dict[str, Any]] = []
    post_object_id: Dict[str, str] = {}

    for entry in ordered["order"]:
        item = entry["item"]
        key = entry["key"]
        if entry["errors"]:
            unapproved.append({"item": key, "errors": list(entry["errors"])})
            continue

        is_post = entry["rank"] == ORDER_RANK["SCHEDULED_POST"]
        if not is_post and entry["placement_id"] not in post_object_id:
            # No receipted post => the comment's parent cannot be verified, and a
            # comment with an unverified parent is never published or resumed.
            blocked.append({"item": key, "reason": "PARENT_POST_NOT_RECEIPTED"})
            continue

        expected_parent = None if is_post else post_object_id[entry["placement_id"]]
        receipt = true_receipt(store, item, expected_parent=expected_parent)
        if receipt is not None:
            received.append(key)
            if is_post:
                post_object_id[entry["placement_id"]] = receipt["provider_object_id"]
            continue

        row = store.action_by_intent(key)
        reason = _resume_block_reason(row)
        if reason is None and store.unresolved_attempt(row["action_id"]) is not None:
            # An open attempt is a send already in flight: it may or may not have
            # reached the provider, so re-issuing it could double-post. Reconcile
            # it first; the next pass either finds a receipt or blocks it.
            reason = "ATTEMPT_IN_FLIGHT"
        if reason is not None:
            blocked.append({"item": key, "reason": reason})
            continue
        resume.append(key)

    return {
        "ok": not ordered["errors"],
        "order": [e["key"] for e in ordered["order"]],
        "resume": resume,
        "blocked": blocked,
        "already_received": received,
        "unapproved": unapproved,
        "errors": ordered["errors"],
    }


def _timestamp(receipt: Mapping[str, Any]) -> float:
    """A finite numeric provider timestamp; a bool or NaN is not a time."""
    value = receipt["recorded_at"]
    if isinstance(value, bool):
        raise TypeError("a bool is not a timestamp")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError("a timestamp is finite")
    return value


def reveal_timing_errors(
    post_receipt: Optional[Mapping[str, Any]],
    comment_receipt: Mapping[str, Any],
) -> List[str]:
    """Refuse only a comment that precedes its post.

    There is no minimum gap. The provider timestamps are numeric seconds. A
    gap of zero or five seconds is legitimate: the class teaches ordered
    comments a few seconds apart, and a strict under-one-minute rule is not in
    the source material.

    ponytail: end-state only, the ceiling is a clock-skew pair from two provider
    hosts. If providers report local wall-clock strings, normalise to epoch at
    the adapter; do not add a tolerance here.
    """
    if post_receipt is None:
        return ["PARENT_POST_NOT_RECEIPTED"]
    try:
        post_at = _timestamp(post_receipt)
        comment_at = _timestamp(comment_receipt)
    except (KeyError, TypeError, ValueError):
        return ["$.recorded_at: both receipts need a numeric provider timestamp"]
    if comment_at < post_at:
        return ["COMMENT_PRECEDES_POST"]
    return []

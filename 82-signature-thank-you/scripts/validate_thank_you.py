"""Structured no-pitch validator for Skill 82 order views (S82-01/S82-03).

Replaces the legacy Skill 49 token blacklist in LAUNCH mode. Purchased
names, amounts, totals, order numbers and billing schedules are allowed
and required. What fails is a NEW pitch:

- a displayed item with no verified provenance in the snapshot, or with
  an amount/name that differs from the verified line;
- an item or recommendation for a product that was not purchased;
- any CTA outside the allowed classification set, any CTA that
  initiates a new charge, or any CTA referencing an unpurchased offer
  or an entitlement that is not a paid purchased entitlement;
- a view whose order reference / order number / journey does not match
  the verified snapshot (another buyer's order never validates);
- event provenance that disagrees with the verified lines: the
  snapshot's event_ids manifest, or the view's copied provenance list,
  over- or under-claiming events (observation O-01);
- an upsell_2 display with no paid upsell_1/downsell_1 qualifying it;
- purchase authority claimed from a query string (e.g. vip=true);
- a pending/failed/refunded purchase presented as confirmed
  ("You are all set");
- raw payment credential fields anywhere in the view.

Stdlib only. Returns a list of error strings; empty means pass.
Also runs validate_entitlements and merges its errors.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thank_you_resolver import (  # noqa: E402
    FORBIDDEN_KEYS,
    deduplicate_line_items,
    event_provenance_problem,
    ResolverError,
)
from validate_entitlements import validate_entitlements  # noqa: E402

ALLOWED_CTA_CLASSIFICATIONS = {
    "access",
    "download",
    "manage_purchase",
    "support",
    "schedule_included_service",
    "noncommercial_next_step",
}

QUERY_AUTHORITY_KEYS = {"vip", "entitlement", "entitlements", "offer",
                        "offer_id", "tier", "plan", "access"}


def _walk(obj, path="$"):
    if isinstance(obj, dict):
        for key, value in obj.items():
            yield path, key, value
            yield from _walk(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _walk(value, f"{path}[{i}]")


def validate_thank_you(view, snapshot, fulfillment_map=None):
    errors = []
    if not isinstance(view, dict):
        return ["view must be an object"]
    if not isinstance(snapshot, dict):
        return ["snapshot must be an object"]

    # --- forbidden credential fields anywhere in the view ---------------
    for path, key, _value in _walk(view):
        if str(key).lower() in FORBIDDEN_KEYS:
            errors.append(
                f"forbidden_field: raw payment credential field '{key}' at {path}"
            )

    # --- query-string authority claims -----------------------------------
    for path, key, value in _walk(view):
        if key in ("query_params", "query_string_claims") and isinstance(value, dict):
            bad = sorted(k for k in value if str(k).lower() in QUERY_AUTHORITY_KEYS)
            if bad:
                errors.append(
                    f"query_string_authority: view carries authority claims "
                    f"from query parameters {bad} at {path}"
                )
        if key == "source" and value == "query_string":
            errors.append(f"query_string_authority: claim sourced from query string at {path}")
        if key == "authority_source" and value not in (None, "verified_normalized_purchase_snapshot"):
            errors.append(
                f"unverified_authority_source: {value!r} at {path}; only the "
                "verified purchase snapshot is authority"
            )

    # --- identity must match the verified snapshot -----------------------
    for key in ("tenant_id", "location_id", "launch_id", "revision"):
        if view.get(key) != snapshot.get(key):
            errors.append(
                f"identity_mismatch: view {key}={view.get(key)!r} != "
                f"snapshot {snapshot.get(key)!r}"
            )
    # --- order identity must be the snapshot's order (repair D-03) -------
    # The displayed order number is required actual data; a view pointing
    # at another buyer's order must never validate.
    if view.get("order_ref") != snapshot.get("native_order_ref"):
        errors.append(
            f"order_ref_mismatch: view order_ref={view.get('order_ref')!r} "
            f"!= verified native order {snapshot.get('native_order_ref')!r}"
        )
    if view.get("order_number") != snapshot.get("native_order_ref"):
        errors.append(
            f"order_number_mismatch: view order_number="
            f"{view.get('order_number')!r} != verified native order "
            f"{snapshot.get('native_order_ref')!r}"
        )
    if view.get("journey_id") != snapshot.get("journey_id"):
        errors.append(
            f"journey_mismatch: view journey_id={view.get('journey_id')!r} "
            f"!= snapshot journey {snapshot.get('journey_id')!r}"
        )
    if (view.get("provenance") or {}).get("source") != "verified_normalized_purchase_snapshot":
        errors.append("provenance_missing: view was not built from a verified purchase snapshot")

    # --- displayed items: provenance + purchased-set truth ---------------
    try:
        lines = deduplicate_line_items(snapshot.get("line_items") or [])
    except ResolverError as exc:
        return errors + [f"snapshot_unusable: {exc}"]
    # --- event provenance consistency (observation O-01) ------------------
    # The snapshot's event_ids manifest must exactly match the event_id
    # values on its deduplicated line items, and the view's copied
    # provenance list must match the verified lines — provenance may
    # neither over- nor under-claim events.
    problem = event_provenance_problem(snapshot, lines)
    if problem is not None:
        errors.append(problem)
    verified_event_ids = {line["event_id"] for line in lines}
    claimed_event_ids = (view.get("provenance") or {}).get("event_ids")
    if not isinstance(claimed_event_ids, list) or set(claimed_event_ids) != verified_event_ids:
        errors.append(
            "event_id_mismatch: view provenance event_ids "
            f"{claimed_event_ids!r} != verified line item event_ids "
            f"{sorted(verified_event_ids)}"
        )
    verified_by_ref = {line["native_line_ref"]: line for line in lines}
    purchased_offers = {line["offer_id"] for line in lines}
    paid_entitlements = {
        ent for line in lines if line["payment_status"] == "succeeded"
        for ent in line["entitlement_ids"]
    }

    # --- U2 qualification (repair D-02) ------------------------------------
    # Mirror of the resolver rule: upsell_2 is displayable only when a
    # PAID upsell_1 or downsell_1 purchase in the same journey qualifies it.
    all_slots = {line["slot"] for line in lines}
    paid_slots = {line["slot"] for line in lines
                  if line["payment_status"] == "succeeded"}
    if "upsell_2" in all_slots:
        if not ({"upsell_1", "downsell_1"} & all_slots):
            errors.append(
                "u2_without_qualification: upsell_2 is displayed but "
                "neither upsell_1 nor downsell_1 was purchased in this "
                "journey; U2 requires a successful U1 or D1 purchase first"
            )
        elif not ({"upsell_1", "downsell_1"} & paid_slots):
            errors.append(
                "u2_without_qualification: upsell_2 is displayed but no "
                "PAID upsell_1 or downsell_1 purchase qualifies it in "
                "this journey"
            )

    displayed_refs = []
    for item in view.get("items") or []:
        ref = item.get("native_line_ref")
        displayed_refs.append(ref)
        line = verified_by_ref.get(ref)
        if line is None:
            errors.append(
                "unprovenanced_item: displayed item "
                f"{item.get('offer_id')!r} (line {ref!r}) has no verified "
                "line in the purchase snapshot"
            )
            continue
        if item.get("offer_id") != line["offer_id"]:
            errors.append(f"provenance_mismatch: line {ref} is offer {line['offer_id']!r}, displayed as {item.get('offer_id')!r}")
        if item.get("amount_minor") != line["amount_minor"]:
            errors.append(
                f"amount_mismatch: {line['offer_id']} displayed amount "
                f"{item.get('amount_minor')!r} != verified {line['amount_minor']}"
            )
        if item.get("display_name") != line["display_name"]:
            errors.append(
                f"name_mismatch: {line['offer_id']} displayed name "
                f"{item.get('display_name')!r} != verified {line['display_name']!r}"
            )
    if sorted(displayed_refs) != sorted(verified_by_ref):
        errors.append(
            "item_set_mismatch: displayed lines "
            f"{sorted(r for r in displayed_refs if r)} != verified purchased "
            f"lines {sorted(verified_by_ref)}"
        )

    # --- totals ------------------------------------------------------------
    paid_total = sum(l["amount_minor"] for l in lines if l["payment_status"] == "succeeded")
    totals = view.get("totals") or {}
    if totals.get("paid_total_minor") != paid_total:
        errors.append(
            f"total_mismatch: view paid_total_minor={totals.get('paid_total_minor')!r} "
            f"!= verified paid total {paid_total}"
        )

    # --- recommendations: any entry is a pitch -----------------------------
    for rec in view.get("recommendations") or []:
        offer = rec.get("offer_id") if isinstance(rec, dict) else rec
        errors.append(
            f"new_offer_pitch: recommendation of {offer!r} on the final "
            "thank-you page is a new pitch, purchased or not"
        )

    # --- CTAs: classification, no new charge, purchased refs only ----------
    for cta in view.get("ctas") or []:
        classification = cta.get("classification")
        if classification not in ALLOWED_CTA_CLASSIFICATIONS:
            errors.append(
                f"unclassified_cta: {classification!r} is not an allowed "
                "thank-you CTA classification (new-offer CTAs are prohibited)"
            )
        if cta.get("initiates_new_charge"):
            errors.append(
                f"new_charge_cta: CTA {cta.get('label')!r} initiates a new "
                "charge on the final thank-you page"
            )
        ref_offer = cta.get("offer_id")
        if ref_offer is not None and ref_offer not in purchased_offers:
            errors.append(
                f"unpurchased_cta_target: CTA {cta.get('label')!r} references "
                f"unpurchased offer {ref_offer!r}"
            )
        # Repair D-01: a CTA's entitlement target is checked too, not
        # just its offer. An access-classified CTA pointing at an
        # unpurchased entitlement is a hidden premium-access/pitch path
        # even when offer_id is null.
        ref_entitlement = cta.get("entitlement_id")
        if ref_entitlement is not None:
            if ref_entitlement not in paid_entitlements:
                errors.append(
                    f"unpurchased_cta_target: CTA {cta.get('label')!r} "
                    f"references entitlement {ref_entitlement!r}, which is "
                    "not an entitlement of a paid purchased item"
                )
            elif ref_offer is not None:
                owner_offers = {
                    line["offer_id"] for line in lines
                    if ref_entitlement in line["entitlement_ids"]
                }
                if ref_offer not in owner_offers:
                    errors.append(
                        f"cta_target_mismatch: CTA {cta.get('label')!r} "
                        f"pairs offer {ref_offer!r} with entitlement "
                        f"{ref_entitlement!r}, which belongs to "
                        f"{sorted(owner_offers)}, not to that offer"
                    )

    # --- honest confirmation status -----------------------------------------
    confirmation = view.get("confirmation") or {}
    unresolved = [i for i in view.get("items") or []
                  if i.get("display_status") in ("pending", "requires_customer_action",
                                                 "failed", "unknown",
                                                 "refunded", "partially_refunded")]
    if unresolved and confirmation.get("all_set"):
        errors.append(
            "false_confirmation: 'all set' confirmation while items are "
            f"unresolved: {[i.get('offer_id') for i in unresolved]}"
        )
    if unresolved and "all set" in str(confirmation.get("headline", "")).lower():
        errors.append(
            "false_confirmation: headline claims 'all set' while items are "
            f"unresolved: {[i.get('offer_id') for i in unresolved]}"
        )

    # --- entitlement equality (exact purchased set) -------------------------
    errors.extend(validate_entitlements(view, snapshot, fulfillment_map))
    return errors


def _load(path):
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True)
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--fulfillment")
    args = parser.parse_args(argv)
    fulfillment = _load(args.fulfillment) if args.fulfillment else None
    errors = validate_thank_you(_load(args.view), _load(args.snapshot), fulfillment)
    for err in errors:
        print(f"FAIL: {err}")
    if errors:
        return 1
    print("PASS: no pitch; every displayed item has verified provenance")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Validate entitlement equality for a Skill 82 order view (S82-03).

The displayed entitlement set must equal the verified purchased
entitlement set EXACTLY:

- item entitlements: entitlements shown on displayed items == entitlements
  on the deduplicated verified snapshot line items. An unpurchased item
  sneaking into the display (e.g. U1 shown on a D1 path) fails here, as
  does a purchased item silently dropped from the display.
- access entitlements: entitlements with access blocks must be a subset
  of the paid items' entitlements; when the S44 fulfillment map is
  supplied, they must equal exactly the paid + granted entitlements.
- CTA entitlement targets: a CTA carrying an entitlement_id is making an
  access claim; that entitlement must belong to a paid item (repair D-01).
- U2 qualification: an upsell_2 slot is legitimate only with a paid
  upsell_1 or downsell_1 in the same journey (repair D-02).

Stdlib only. Returns a list of error strings; empty means pass.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from thank_you_resolver import deduplicate_line_items, ResolverError  # noqa: E402

PAID = "paid"


def validate_entitlements(view, snapshot, fulfillment_map=None):
    errors = []
    if not isinstance(view, dict) or not isinstance(snapshot, dict):
        return ["view and snapshot must be objects"]

    try:
        lines = deduplicate_line_items(snapshot.get("line_items") or [])
    except ResolverError as exc:
        return [f"snapshot_unusable: {exc}"]

    # --- U2 qualification (repair D-02) ------------------------------------
    all_slots = {line["slot"] for line in lines}
    paid_slots = {line["slot"] for line in lines
                  if line["payment_status"] == "succeeded"}
    if "upsell_2" in all_slots:
        if not ({"upsell_1", "downsell_1"} & all_slots):
            errors.append(
                "u2_without_qualification: upsell_2 is present but neither "
                "upsell_1 nor downsell_1 was purchased in this journey; "
                "U2 requires a successful U1 or D1 purchase first"
            )
        elif not ({"upsell_1", "downsell_1"} & paid_slots):
            errors.append(
                "u2_without_qualification: upsell_2 is present but no "
                "PAID upsell_1 or downsell_1 purchase qualifies it in "
                "this journey"
            )

    verified_item_entitlements = set()
    paid_entitlements = set()
    for line in lines:
        verified_item_entitlements.update(line["entitlement_ids"])
        if line["payment_status"] == "succeeded":
            paid_entitlements.update(line["entitlement_ids"])

    displayed_item_entitlements = set()
    for item in view.get("items") or []:
        displayed_item_entitlements.update(item.get("entitlement_ids") or [])

    if displayed_item_entitlements != verified_item_entitlements:
        extra = sorted(displayed_item_entitlements - verified_item_entitlements)
        missing = sorted(verified_item_entitlements - displayed_item_entitlements)
        if extra:
            errors.append(
                f"unpurchased_entitlement_displayed: {extra} are displayed "
                "but are not in the verified purchased set"
            )
        if missing:
            errors.append(
                f"purchased_entitlement_missing: {missing} were purchased "
                "and verified but are not displayed"
            )

    access_entitlements = {
        block.get("entitlement_id") for block in view.get("access_blocks") or []
    }
    leaked = sorted(access_entitlements - paid_entitlements)
    if leaked:
        errors.append(
            f"access_without_paid_purchase: access blocks exist for {leaked}, "
            "which are not entitlements of a paid item"
        )

    if fulfillment_map is not None:
        expected_access = {
            e for e in paid_entitlements
            if (fulfillment_map.get(e) or {}).get("state") == "granted"
        }
        if access_entitlements != expected_access:
            errors.append(
                "access_entitlement_mismatch: access blocks "
                f"{sorted(access_entitlements)} != paid+granted "
                f"entitlements {sorted(expected_access)}"
            )

    # --- CTA entitlement targets (repair D-01) ------------------------------
    # A CTA that carries an entitlement reference makes an access claim;
    # the entitlement must belong to a PAID purchased item.
    for cta in view.get("ctas") or []:
        ref_entitlement = cta.get("entitlement_id")
        if ref_entitlement is not None and ref_entitlement not in paid_entitlements:
            errors.append(
                f"unpurchased_cta_target: CTA {cta.get('label')!r} references "
                f"entitlement {ref_entitlement!r}, which is not an "
                "entitlement of a paid purchased item"
            )
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
    errors = validate_entitlements(_load(args.view), _load(args.snapshot), fulfillment)
    for err in errors:
        print(f"FAIL: {err}")
    if errors:
        return 1
    print("PASS: displayed entitlement set equals the verified purchased set")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

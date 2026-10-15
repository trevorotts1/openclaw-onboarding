"""Build the S82 confirmation-shown observation record (S82-08).

Fulfillment is owned by S44 and begins on the purchase event, not on a
page visit. The thank-you page therefore emits NO onboarding send of its
own. What it may record is a single, idempotent observation —
"confirmation_shown" — so the page and the S44 event worker can
deduplicate onboarding: whichever side records the send first wins, and
a page refresh records the same observation again instead of a second
send.

The dedupe key is deterministic:

    sha256("<tenant_id>|<location_id>|<launch_id>|<order_ref>|"
           "<entitlement_version>")

`entitlement_version` identifies the entitlement state the buyer was
shown. It is taken from the view's explicit `entitlement_version` field
when S44 supplies one; otherwise it is derived deterministically from
the view's entitlement state (sorted entitlement_id + fulfillment
state pairs) so a refresh of the same state yields the same version,
and any entitlement change yields a new one.

The record carries NO PII: no email, no buyer name, no card data — only
tenant/location/launch identity, the opaque order reference, entitlement
IDs (product identifiers, not personal data), and the confirmation
status. Stdlib only; deterministic: no clock, no randomness.
"""

import hashlib
import json
import os
import sys

RECORD_TYPE = "confirmation_shown"


def entitlement_version_for(view):
    """Return the entitlement version a view was rendered from."""
    explicit = view.get("entitlement_version")
    if explicit not in (None, ""):
        return str(explicit)
    pairs = []
    seen = set()
    for block in view.get("access_blocks") or []:
        pair = (block.get("entitlement_id"),
                block.get("fulfillment_state") or "granted")
        if pair[0] and pair not in seen:
            seen.add(pair)
            pairs.append(pair)
    if not pairs:
        for item in view.get("items") or []:
            for entitlement_id in item.get("entitlement_ids") or []:
                pair = (entitlement_id, item.get("display_status") or "")
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
    canonical = json.dumps(sorted(pairs), separators=(",", ":"))
    return "derived-sha256:" + hashlib.sha256(
        canonical.encode("utf-8")).hexdigest()


def dedupe_key_for(tenant_id, location_id, launch_id, order_ref,
                   entitlement_version):
    material = "|".join([str(tenant_id), str(location_id),
                         str(launch_id), str(order_ref),
                         str(entitlement_version)])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_confirmation_observation(view):
    """Build the confirmation_shown observation record from a view.

    Pure: the same view always produces the same record, so a page
    refresh is idempotent and can never trigger a duplicate send.
    """
    if not isinstance(view, dict):
        raise ValueError("view must be an order-view object")
    for key in ("tenant_id", "location_id", "launch_id", "order_ref"):
        if view.get(key) in (None, ""):
            raise ValueError(f"view is missing required field {key!r}")
    version = entitlement_version_for(view)
    entitlement_ids = sorted({
        *(e for item in view.get("items") or []
          for e in (item.get("entitlement_ids") or [])),
        *(b["entitlement_id"] for b in view.get("access_blocks") or []
          if b.get("entitlement_id")),
    })
    return {
        "record_type": RECORD_TYPE,
        "dedupe_key": dedupe_key_for(view["tenant_id"],
                                     view["location_id"],
                                     view["launch_id"],
                                     view["order_ref"],
                                     version),
        "tenant_id": view["tenant_id"],
        "location_id": view["location_id"],
        "launch_id": view["launch_id"],
        "order_ref": view["order_ref"],
        "entitlement_version": version,
        "entitlement_ids": entitlement_ids,
        "confirmation_status": (view.get("confirmation") or {}).get("status"),
        "observed_via": "thank_you_page_render",
        "emits_send": False,
        "test_only": bool(view.get("test_only", False)),
    }


def _load(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main(argv=None):
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--view", required=True)
    args = parser.parse_args(argv)
    record = build_confirmation_observation(_load(args.view))
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

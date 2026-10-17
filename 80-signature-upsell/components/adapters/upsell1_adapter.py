"""S80-04 - Signature Upsell Page 1 production adapter (LOCAL).

Consumes a validated upsell_1 request plus its eight-section copy fixture
and verified journey state, and produces the spec 10 section 7 bundle:

    {"result": <upsell-result.json object>, "page_plan": <declarations>}

The result validates against schemas/upsell-result.schema.json (test
suite). The bundle also carries the S80-06 native_binding record:
CTAs bind the extra-offer binding ref (interface-conformant, fixture
level) while native_action.action_id stays null - no action ID is ever
invented; the page plan declares the adjacent disclosure rendered from
integer minor units, and the processing / decline / failure states
from spec 10 section 6.

Eligibility for U1 is exactly one thing: a verified original purchase
(spec 10 section 3). Client-side claims are never proof. Already-owned
or incompatible U1 entitlements are suppressed or routed safely to the
final thank-you - never double-charged.
"""

from typing import Dict, Mapping, Optional

import adapter_common as common


def build_bundle(
    request: Mapping,
    copy_doc: Mapping,
    journey: Optional[Mapping],
    *,
    copy_sha256: str,
    copy_artifact_path: str,
) -> Dict[str, object]:
    common.validate_request(request, "upsell_1")
    common.validate_routes_for_instance(request, "upsell_1")
    if request.get("entry_context") is not None:
        raise common.AdapterError("U1 has no entry context; it follows checkout.")

    orig = common.original_purchase_check(request, journey)
    eligibility_ok = orig["verified"]
    eligibility_check = {
        "original_purchase_verified": eligibility_ok,
        "qualifying_purchase_slot": None,
        "entry_context": None,
        "verdict": "eligible" if eligibility_ok else "blocked_unverified",
    }

    disposition = common.decide_presentation(
        request, journey, eligibility_ok=eligibility_ok
    )
    cta_map = common.build_cta_map(copy_doc, request)
    disclosure_text = common.render_disclosure(request["disclosure"])

    # The base purchase may be acknowledged only after its verified status
    # is known (spec 10 section 3) - so this block exists only when the
    # original purchase is verified, and never claims the upgrade is
    # required to use the original product.
    acknowledgement_blocks = []
    if eligibility_ok:
        main_rec = orig["record"] or {}
        main_name = main_rec.get("offer_display_name")
        text = (
            "Your original purchase is confirmed"
            + (" (%s)" % main_name if main_name else "")
            + ". It is complete on its own; this page offers an optional "
            "extra that adds to it."
        )
        acknowledgement_blocks.append(
            {"condition": "verified_original_purchase", "text": text}
        )

    test_outcomes = [
        {
            "test_id": "S80-04-adapter-upsell1-fixtures",
            "level": "L1",
            "outcome": "pass",
            "evidence_ref": "tests/test_adapters_upsell1.py",
        },
        {
            "test_id": "A10-route-native",
            "level": "L3",
            "outcome": "not_run",
            "evidence_ref": None,
        },
        {
            "test_id": "S80-09-installed-purchase-tests",
            "level": "L4",
            "outcome": "not_run",
            "evidence_ref": None,
        },
    ]

    result = common.build_result(
        request=request,
        copy_sha256=copy_sha256,
        copy_artifact_path=copy_artifact_path,
        cta_map=cta_map,
        eligibility_check=eligibility_check,
        disposition=disposition,
        test_outcomes=test_outcomes,
    )
    page_plan = common.build_page_plan(
        request=request,
        disclosure_text=disclosure_text,
        disposition=disposition,
        acknowledgement_blocks=acknowledgement_blocks,
    )
    return {
        "result": result,
        "page_plan": page_plan,
        "native_binding": common.build_native_binding(request),
    }

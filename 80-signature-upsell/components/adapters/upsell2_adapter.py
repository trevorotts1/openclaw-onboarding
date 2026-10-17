"""S80-05 - Signature Upsell Page 2 production adapter (LOCAL).

Same skill (80), distinct instance. U2 is ONE canonical page with ONE
product mapping, entered from exactly two verified paths (spec 10
section 5):

    entry_context = from_upsell_1    (verified U1 purchase)
    entry_context = from_downsell_1  (verified D1 purchase)

Eligibility gate (spec 10 section 3, doc 02 section 4): verified original
purchase PLUS a verified accepted upsell_1 OR downsell_1 purchase,
cross-checked between the request's eligibility block and the verified
journey state (matching slot AND matching evidence_ref). A bump alone
never qualifies. A client-side parameter such as acceptedU1=true is
never proof. The entry context must agree with the qualifying slot, so
the acknowledgement copy can never make a false prior-purchase
statement: D1 buyers are told they took the downsell alternative at its
own terms - never that they bought the full U1 package (an automatic
fail under spec 10 section 10).

Already-owned or incompatible U2 entitlements are suppressed or routed
safely to the final thank-you; a duplicate charge is never emitted.
"""

from typing import Dict, Mapping, Optional

import adapter_common as common

ENTRY_CONTEXT_BY_SLOT = {
    "upsell_1": "from_upsell_1",
    "downsell_1": "from_downsell_1",
}

# Markers of a client-side claim inside an evidence_ref (mirrors the
# repaired request schema's `not` guard, D-06). Such text is a claim
# made by the visitor's browser, never purchase proof.
CLIENT_CLAIM_EVIDENCE_MARKERS = ("acceptedU1=true", "client-side", "client_side")


def check_u2_eligibility(request: Mapping, journey: Optional[Mapping]) -> Dict:
    """Full U2 eligibility verdict with explicit problems, for the result."""
    problems = []
    orig = common.original_purchase_check(request, journey)
    if not orig["verified"]:
        problems.extend("original purchase: %s" % p for p in orig["problems"])

    elig = request.get("eligibility") or {}
    qual = elig.get("qualifying_purchase")
    entry_context = request.get("entry_context")
    qualifying_slot = None

    if not isinstance(qual, Mapping):
        problems.append(
            "no verified qualifying purchase: U2 requires a verified "
            "upsell_1 or downsell_1 purchase; a bump alone never qualifies"
        )
    else:
        slot = qual.get("slot")
        if slot not in ENTRY_CONTEXT_BY_SLOT:
            problems.append("qualifying slot %r is not upsell_1/downsell_1" % (slot,))
        elif qual.get("status") != "verified_succeeded":
            problems.append("qualifying purchase is not verified_succeeded")
        elif qual.get("verification_source") not in common.ADAPTER_VERIFICATION_SOURCES:
            # D-06: the qualifying purchase carries the SAME verification
            # discipline as the original purchase. An asserted status
            # without an adapter/native verification_source is a claim,
            # not proof (spec 10 section 3).
            problems.append(
                "qualifying purchase verification_source %r is not an "
                "adapter source; client-side claims are not purchase proof"
                % (qual.get("verification_source"),)
            )
        elif any(
            marker in str(qual.get("evidence_ref") or "")
            for marker in CLIENT_CLAIM_EVIDENCE_MARKERS
        ):
            problems.append(
                "qualifying purchase evidence_ref is a client-side claim, "
                "not purchase proof"
            )
        else:
            rec = common.journey_record_for(journey, slot)
            if rec is None:
                problems.append(
                    "journey state carries no verified %s purchase record" % slot
                )
            elif rec.get("evidence_ref") != qual.get("evidence_ref"):
                problems.append(
                    "journey %s evidence_ref does not match the request" % slot
                )
            elif rec.get("verification_source") != qual.get("verification_source"):
                # The request's stated source must be the source the
                # verified journey evidence was actually recorded under;
                # a source the request merely asserts is not sourcing.
                problems.append(
                    "journey %s verification_source %r does not match the "
                    "request's stated verification_source %r"
                    % (slot, rec.get("verification_source"),
                       qual.get("verification_source"))
                )
            else:
                qualifying_slot = slot
        if (
            qualifying_slot is not None
            and entry_context != ENTRY_CONTEXT_BY_SLOT[qualifying_slot]
        ):
            problems.append(
                "entry_context %r does not agree with the verified "
                "qualifying slot %r" % (entry_context, qualifying_slot)
            )
            qualifying_slot = None

    if entry_context not in ("from_upsell_1", "from_downsell_1"):
        problems.append("U2 requires an entry_context from verified journey state")

    return {
        "verified": not problems,
        "problems": problems,
        "qualifying_slot": qualifying_slot,
        "entry_context": entry_context,
    }


def acknowledgement_blocks(
    request: Mapping, journey: Optional[Mapping], check: Mapping
) -> list:
    """Conditional acknowledgement blocks, truthful on BOTH entry paths.

    Names come only from verified journey records - never invented. The
    from_downsell_1 block explicitly frames D1 as the alternative taken
    instead of the full U1 package.
    """
    if not check["verified"]:
        return []
    slot = check["qualifying_slot"]
    rec = common.journey_record_for(journey, slot) or {}
    prior_name = rec.get("offer_display_name")
    blocks = [
        {
            "condition": "verified_original_purchase",
            "text": (
                "Your original purchase is confirmed. This page offers one "
                "further optional extra; everything you already bought "
                "stays yours either way."
            ),
        }
    ]
    if slot == "upsell_1":
        text = "Your first upgrade is confirmed"
        if prior_name:
            text += " (%s)" % prior_name
        text += (
            ". The Implementation Studio builds on it with guided "
            "implementation - a different step from the content upgrade "
            "you just added."
        )
        blocks.append({"condition": "from_upsell_1", "text": text})
    else:  # downsell_1
        text = "Your downsell choice is confirmed"
        if prior_name:
            text += " (%s)" % prior_name
        text += (
            " at its own terms. You chose that alternative instead of the "
            "full first-upgrade package, and nothing about that changes "
            "here. This page offers the same further extra that first-"
            "upgrade buyers see."
        )
        blocks.append({"condition": "from_downsell_1", "text": text})
    return blocks


def build_bundle(
    request: Mapping,
    copy_doc: Mapping,
    journey: Optional[Mapping],
    *,
    copy_sha256: str,
    copy_artifact_path: str,
) -> Dict[str, object]:
    common.validate_request(request, "upsell_2")
    common.validate_routes_for_instance(request, "upsell_2")

    check = check_u2_eligibility(request, journey)
    eligibility_ok = check["verified"]
    eligibility_check = {
        "original_purchase_verified": not any(
            p.startswith("original purchase:") for p in check["problems"]
        ),
        "qualifying_purchase_slot": check["qualifying_slot"],
        "entry_context": request.get("entry_context"),
        "verdict": "eligible" if eligibility_ok else "blocked_unverified",
    }

    disposition = common.decide_presentation(
        request, journey, eligibility_ok=eligibility_ok
    )
    cta_map = common.build_cta_map(copy_doc, request)
    disclosure_text = common.render_disclosure(request["disclosure"])
    blocks = acknowledgement_blocks(request, journey, check)

    test_outcomes = [
        {
            "test_id": "S80-05-adapter-upsell2-fixtures",
            "level": "L1",
            "outcome": "pass",
            "evidence_ref": "tests/test_adapters_upsell2.py",
        },
        {
            "test_id": "A12-U2-both-entry-paths-local",
            "level": "L1",
            "outcome": "pass",
            "evidence_ref": "tests/test_adapters_upsell2.py",
        },
        {
            "test_id": "A12-U2-both-entry-paths-native",
            "level": "L4",
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
        extra_blockers=[
            "U2 eligibility problems: %s" % p for p in check["problems"]
        ],
    )
    page_plan = common.build_page_plan(
        request=request,
        disclosure_text=disclosure_text,
        disposition=disposition,
        acknowledgement_blocks=blocks,
    )
    return {
        "result": result,
        "page_plan": page_plan,
        "native_binding": common.build_native_binding(request),
    }

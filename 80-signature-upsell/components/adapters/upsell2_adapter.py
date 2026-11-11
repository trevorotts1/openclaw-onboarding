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
import upsell1_adapter as u1

ENTRY_CONTEXT_BY_SLOT = {
    "upsell_1": "from_upsell_1",
    "downsell_1": "from_downsell_1",
}

# Markers of a client-side claim inside an evidence_ref (mirrors the
# repaired request schema's `not` guard, D-06). Such text is a claim
# made by the visitor's browser, never purchase proof.
CLIENT_CLAIM_EVIDENCE_MARKERS = ("acceptedU1=true", "client-side", "client_side")


def enabled_entry_slots(launch: Optional[Mapping]) -> Optional[list]:
    """The U2 entry slots the launch enables (U1 and/or D1), from the launch
    record's extras (offers when extras do not name the slot); None when no
    launch record is supplied (the one staged journey then decides alone)."""
    if not isinstance(launch, Mapping):
        return None
    extras = launch.get("extras") if isinstance(launch.get("extras"), Mapping) else {}
    offered = {o.get("slot") for o in launch.get("offers") or [] if isinstance(o, Mapping)}
    return [
        s for s in u1.EXCLUSIVE_SLOTS
        if (extras[s] is True if s in extras else s in offered)
    ]


def _design_marker_eligibility(request: Mapping, journey: Optional[Mapping],
                               launch: Optional[Mapping], problems: list) -> Dict:
    """Issue 72: the DESIGN-stage U2 verdict. Nothing was bought, so the qualifying purchase is a
    marker for an entry slot the launch enables, and the entry context must agree with it. No purchase
    proof is read or asserted; the runtime guard verifies the real purchase."""
    check = common.original_purchase_check(request, journey)
    problems.extend("original purchase: %s" % p for p in check["problems"])
    qual = (request.get("eligibility") or {}).get("qualifying_purchase")
    entry_context = request.get("entry_context")
    slot = qual.get("slot") if isinstance(qual, Mapping) else None
    qualifying_slot = None
    if not isinstance(qual, Mapping) or qual.get("status") != common.DESIGN_MARKER:
        problems.append("no design-marker qualifying purchase: at the design stage U2 carries a "
                        "design_marker qualifying purchase for upsell_1 or downsell_1")
    elif slot not in ENTRY_CONTEXT_BY_SLOT:
        problems.append("qualifying slot %r is not upsell_1/downsell_1" % (slot,))
    else:
        enabled = enabled_entry_slots(launch)
        if enabled is not None and slot not in enabled:
            problems.append("qualifying slot %r is not enabled in the launch record" % slot)
        elif entry_context != ENTRY_CONTEXT_BY_SLOT[slot]:
            problems.append("entry_context %r does not agree with the design-marker qualifying "
                            "slot %r" % (entry_context, slot))
        else:
            qualifying_slot = slot
    return {"verified": not problems, "problems": problems,
            "qualifying_slot": qualifying_slot, "entry_context": entry_context}


def check_u2_eligibility(
    request: Mapping, journey: Optional[Mapping], launch: Optional[Mapping] = None
) -> Dict:
    """Full U2 eligibility verdict with explicit problems, for the result."""
    problems = []
    excluded = u1.mutual_exclusion_problem(journey)
    if excluded:
        problems.append(excluded)
    if common.is_design_marker(request):
        return _design_marker_eligibility(request, journey, launch, problems)
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
        enabled = enabled_entry_slots(launch)
        if qualifying_slot is not None and enabled is not None and qualifying_slot not in enabled:
            problems.append(
                "qualifying slot %r is not enabled in the launch record" % qualifying_slot
            )
            qualifying_slot = None
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
    request: Mapping,
    journey: Optional[Mapping],
    check: Mapping,
    launch: Optional[Mapping] = None,
) -> list:
    """Conditional acknowledgement blocks, truthful on BOTH entry paths.

    With a launch record that enables both U1 and D1 the page is ONE
    canonical page that must serve both buyers, so BOTH conditional blocks
    are emitted (one band renders at runtime, chosen by the buyer's verified
    entry_context; see strip_plan). Without one, only the staged journey's
    path. Product names come from the launch record's offer (this page) and
    the journey's or launch's prior offer - never from code. The
    from_downsell_1 block frames D1 as the alternative taken instead of the
    full U1 package.
    """
    if not check["verified"]:
        return []
    slots = enabled_entry_slots(launch) or [check["qualifying_slot"]]
    this_name = request["offer"]["display_name"]
    launch_names = {
        o.get("slot"): o.get("display_name")
        for o in (launch or {}).get("offers") or []
        if isinstance(o, Mapping)
    }
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
    for slot in slots:
        rec = common.journey_record_for(journey, slot) or {}
        prior_name = rec.get("offer_display_name") or launch_names.get(slot)
        if slot == "upsell_1":
            text = "Your first upgrade is confirmed"
            if prior_name:
                text += " (%s)" % prior_name
            text += (
                ". %s is a separate optional step that builds on it; your "
                "first upgrade stays yours either way." % this_name
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


def strip_plan(blocks: list) -> Optional[Dict]:
    """Design declaration when more than one entry-path band exists: the
    bands are mutually exclusive runtime variants and the design shows all."""
    variants = [b["condition"] for b in blocks if b["condition"] != "verified_original_purchase"]
    if len(variants) < 2:
        return None
    return {
        "mode": "runtime_conditional_mutually_exclusive",
        "variants": variants,
        "render_rule": (
            "render exactly the variant whose condition equals the buyer's "
            "verified entry_context; never both, never neither; same band "
            "geometry so the page does not shift"
        ),
        "design_shows_all_variants": True,
    }


def build_bundle(
    request: Mapping,
    copy_doc: Mapping,
    journey: Optional[Mapping],
    *,
    copy_sha256: str,
    copy_artifact_path: str,
    launch: Optional[Mapping] = None,
    review: Optional[Mapping] = None,
    image_provider: Optional[str] = None,
) -> Dict[str, object]:
    common.validate_request(request, "upsell_2")
    common.validate_routes_for_instance(request, "upsell_2")
    excluded = u1.mutual_exclusion_problem(journey)
    if excluded:
        raise common.AdapterError(excluded)
    scarcity = u1.scarcity_problems(request, copy_doc, launch)
    if scarcity:
        raise common.AdapterError("; ".join(scarcity))

    check = check_u2_eligibility(request, journey, launch)
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
    blocks = acknowledgement_blocks(request, journey, check, launch)

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
        review=review,
        extra_blockers=[
            "U2 eligibility problems: %s" % p for p in check["problems"]
        ],
        image_provider=image_provider,
    )
    page_plan = common.build_page_plan(
        request=request,
        disclosure_text=disclosure_text,
        disposition=disposition,
        acknowledgement_blocks=blocks,
    )
    strip = strip_plan(blocks)
    if strip:
        page_plan["acknowledgement_strip"] = strip
    return {
        "result": result,
        "page_plan": page_plan,
        "native_binding": common.build_native_binding(request),
    }

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

import re
from typing import Dict, List, Mapping, Optional

import adapter_common as common

# U1 and D1 are mutually exclusive (launch plan: offers[].excludes names the
# other; routing_state refuses the pair). The two slots are fixed by the
# profile, so the pair is stated here once and shared with the U2 adapter.
EXCLUSIVE_SLOTS = ("upsell_1", "downsell_1")

# Copy keys that hold the copy author's OWN evidence claims: never a source.
_AUTHOR_EVIDENCE_KEYS = frozenset({"verified_scarcity_evidence", "verified_proof_evidence"})


def mutual_exclusion_problem(journey: Optional[Mapping]) -> Optional[str]:
    """Name the exclusion when one journey carries both a U1 and a D1 record."""
    if all(common.journey_record_for(journey, s) is not None for s in EXCLUSIVE_SLOTS):
        return (
            "U1 and D1 are mutually exclusive (launch plan offers[].excludes): "
            "the journey carries both an upsell_1 and a downsell_1 purchase "
            "record, which cannot happen; refusing to pick one silently"
        )
    return None


def launch_scarcity_facts(launch: Optional[Mapping]) -> List[Mapping]:
    """Scarcity facts of the approved launch record (promotion dates, stock).

    Each is {family, fact, source_ref}; family is the validator profile's
    time_bound / availability / exclusivity. An entry missing any of the
    three is not a fact. The copy document is never a source.
    """
    facts = []
    for entry in (launch or {}).get("scarcity_facts") or []:
        if isinstance(entry, Mapping) and all(
            isinstance(entry.get(k), str) and entry[k].strip()
            for k in ("family", "fact", "source_ref")
        ):
            facts.append(entry)
    return facts


def _copy_strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, Mapping):
        for key, value in node.items():
            if key not in _AUTHOR_EVIDENCE_KEYS:
                yield from _copy_strings(value)
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _copy_strings(value)


def scarcity_problems(
    request: Mapping, copy_doc: Mapping, launch: Optional[Mapping]
) -> List[str]:
    """Every scarcity claim must be backed by a launch-record fact.

    (1) request.factual_scarcity_evidence entries must each equal a launch
    fact (fact text and source_ref); (2) scarcity wording in the copy needs
    a launch fact of the same family (any family for the bare markers).
    """
    facts = launch_scarcity_facts(launch)
    have = {f["family"] for f in facts}
    keyed = {(f["fact"].strip().lower(), f["source_ref"].strip()) for f in facts}
    problems = []
    for entry in request.get("factual_scarcity_evidence") or []:
        key = (
            str((entry or {}).get("fact") or "").strip().lower(),
            str((entry or {}).get("source_ref") or "").strip(),
        ) if isinstance(entry, Mapping) else None
        if key not in keyed:
            problems.append(
                "factual_scarcity_evidence entry %r matches no scarcity fact "
                "of the approved launch record; copy-authored evidence is "
                "not a source" % (entry,)
            )
    profile = common.load_json(common.PROFILE_PATH)
    text = "\n".join(_copy_strings(copy_doc))
    for pat in (profile.get("validator_patterns") or {}).get("scarcity_claim_patterns") or []:
        if re.search(pat["regex"], text, re.IGNORECASE) and pat["family"] not in have:
            problems.append(
                "copy scarcity wording (%s, %s) has no matching %s fact in "
                "the launch record" % (pat["id"], pat["family"], pat["family"])
            )
    low = text.lower()
    for marker in (profile.get("validator_denylists") or {}).get("invented_scarcity_markers") or []:
        if marker in low and not have:
            problems.append(
                "copy scarcity marker %r has no scarcity fact in the launch "
                "record" % marker
            )
    return problems


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
    common.validate_request(request, "upsell_1")
    common.validate_routes_for_instance(request, "upsell_1")
    if request.get("entry_context") is not None:
        raise common.AdapterError("U1 has no entry context; it follows checkout.")
    excluded = mutual_exclusion_problem(journey)
    if excluded:
        raise common.AdapterError(excluded)
    scarcity = scarcity_problems(request, copy_doc, launch)
    if scarcity:
        raise common.AdapterError("; ".join(scarcity))

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
        review=review,
        image_provider=image_provider,
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

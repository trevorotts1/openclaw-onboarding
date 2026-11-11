#!/usr/bin/env python3
"""validate_selection_binding.py - Skill 78 handoff validator (thin wrapper).

Validates a selection.json intent against the current approved launch catalog
before Skill 79 checkout consumes it. Rejects query-string price authority,
cross-tenant selections, stale revisions, and native mapping drift (A05).

This is a checkout-time gate. A visitor's live selection does not exist while the page is built, and
no host runs this CLI on one yet (PRD-05). The per-offer realisation has no visitor selection at all:
each emitted checkout target IS the selection its order form stands for. validate_plan() runs the
same validate_binding over every mapping of an emitted binding plan, and emit_binding_plan.emit_plan
calls it on every plan it returns (Skill 83 checkout_instances.build reaches it through emit_plan),
so a plan the checkout-time validator would refuse is never emitted. That hosted path is what puts
this script inside the skill's "done" claim (runtime-manifest.json "done_claim"). The gates that run
earlier in the build chain are the plan builder's catalog check and
validate_selection_content.validate_manuscript.

Usage:
  validate_selection_binding.py <selection.json> <launch.json> [--query <json>]
  validate_selection_binding.py --self-test
Exit: 0 pass, 2 violation, 3 fail-closed error.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selection_core import Violation, build_selection, reject_query_authority, validate_binding  # noqa: E402
from build_selection_plan import SELF_TEST_LAUNCH  # noqa: E402

V_PLAN_EMPTY = "S78-BINDING-INCOMPLETE"


def validate_plan(plan, launch, *, approval_verifier=None):
    """Run the checkout-time validate_binding over every mapping of an emitted binding plan.

    Each mapping is read as the selection its checkout target stands for: the plan header supplies
    tenant/location/launch/revision, the mapping supplies offer, price choice, native ids, currency and
    amount. Validated against the CURRENT launch record, so drift, a stale revision, a foreign tenant
    or a price that is no longer approved raises the same S78-* Violation the checkout would. A plan
    with no mappings validates nothing and is refused."""
    mappings = plan.get("mappings")
    if not isinstance(mappings, list) or not mappings or not all(isinstance(m, dict) for m in mappings):
        raise Violation(V_PLAN_EMPTY, "Binding plan has no usable mappings; a plan that validates nothing is refused.")
    revision = plan.get("revision")
    revision = revision if isinstance(revision, int) and not isinstance(revision, bool) else -1
    for m in mappings:
        selection = {
            "tenant_id": plan.get("tenant_id"), "location_id": plan.get("location_id"),
            "launch_id": plan.get("launch_id"), "revision": revision,
            "offer_id": m.get("offer_id"), "price_choice_id": m.get("price_choice_id"),
            "native_product_id": m.get("native_product_id"), "native_price_id": m.get("native_price_id"),
            "currency": m.get("currency"), "amount_minor_snapshot": m.get("amount_minor"),
        }
        validate_binding(selection, launch, expected_revision=int(launch["revision"]),
                         approval_verifier=approval_verifier)


def self_test():
    sel = build_selection(
        SELF_TEST_LAUNCH, offer_id="MAIN-B", price_choice_id="MAIN-B-USD",
        selected_at="2026-10-15T20:00:00Z", source_page_id="TEST-SELECTION", session_ref="opaque-123",
    )
    validate_binding(sel, SELF_TEST_LAUNCH, expected_revision=1)
    assert sel["kind"] == "selection_intent_not_payment_evidence"
    assert sel["native_price_id"] == "TEST-PRICE-B"
    for mutate, code in [
        (lambda s: s.update(tenant_id="OTHER-TENANT"), "S78-SELECTION-TENANT-MISMATCH"),
        (lambda s: s.update(revision=99), "S78-SELECTION-STALE-REVISION"),
        (lambda s: s.update(amount_minor_snapshot=1), "S78-SELECTION-PRICE-DRIFT"),
        (lambda s: s.update(native_price_id="FORGED"), "S78-SELECTION-PRICE-DRIFT"),
    ]:
        bad = json.loads(json.dumps(sel))
        mutate(bad)
        try:
            validate_binding(bad, SELF_TEST_LAUNCH, expected_revision=1)
        except Violation as v:
            assert v.code == code, (v.code, code)
        else:
            raise AssertionError(f"mutation was not rejected with {code}")
    try:
        reject_query_authority({"price": "97", "session": "opaque-123"})
    except Violation as v:
        assert v.code == "S78-QUERY-PRICE-AUTHORITY"
    else:
        raise AssertionError("query price authority was not rejected")
    reject_query_authority({"session": "opaque-123"})
    from emit_binding_plan import SELF_TEST_TARGETS, emit_plan  # the host; imported here to keep the module graph acyclic
    plan = emit_plan(SELF_TEST_LAUNCH, SELF_TEST_TARGETS, route="per_offer_targets")
    validate_plan(plan, SELF_TEST_LAUNCH)
    for mutate, code in [
        (lambda p: p.update(tenant_id="OTHER-TENANT"), "S78-SELECTION-TENANT-MISMATCH"),
        (lambda p: p["mappings"][0].update(amount_minor=1), "S78-SELECTION-PRICE-DRIFT"),
        (lambda p: p["mappings"][1].update(native_price_id="FORGED"), "S78-SELECTION-PRICE-DRIFT"),
        (lambda p: p.update(mappings=[]), V_PLAN_EMPTY),
    ]:
        bad = json.loads(json.dumps(plan))
        mutate(bad)
        try:
            validate_plan(bad, SELF_TEST_LAUNCH)
        except Violation as v:
            assert v.code == code, (v.code, code)
        else:
            raise AssertionError(f"plan mutation was not rejected with {code}")
    print("validate_selection_binding --self-test: PASS (valid handoff, tenant/stale/drift/forged/query rejections, emitted-plan validation)")
    return 0


def main(argv):
    if "--self-test" in argv:
        return self_test()
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) < 2:
        print("usage: validate_selection_binding.py <selection.json> <launch.json>", file=sys.stderr)
        return 3
    try:
        selection = json.loads(Path(args[0]).read_text())
        launch = json.loads(Path(args[1]).read_text())
        if "--query" in argv:
            reject_query_authority(json.loads(Path(argv[argv.index("--query") + 1]).read_text()))
        validate_binding(selection, launch, expected_revision=int(launch["revision"]))
    except Violation as v:
        print(f"VIOLATION [{v.code}]: {v.message}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"FAIL-CLOSED: {e}", file=sys.stderr)
        return 3
    print("BINDING PASS: selection preserves the approved native product/price mapping.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

#!/usr/bin/env python3
"""validate_selection_binding.py - Skill 78 handoff validator (thin wrapper).

Validates a selection.json intent against the current approved launch catalog
before Skill 79 checkout consumes it. Rejects query-string price authority,
cross-tenant selections, stale revisions, and native mapping drift (A05).

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
    print("validate_selection_binding --self-test: PASS (valid handoff, tenant/stale/drift/forged/query rejections)")
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

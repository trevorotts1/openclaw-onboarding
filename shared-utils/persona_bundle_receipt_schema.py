#!/usr/bin/env python3
"""persona_bundle_receipt_schema.py — B-U8/U22 bundle-receipt SCHEMA CHECK.

WHY THIS EXISTS
----------------
B-U1/U15's ``persona_bundle_ladder.py`` ALWAYS writes ``routing/persona-bundle-
receipt.json``; B-U5/U19's FAB-QC D4 v2 reads it to decide whether to ground
persona voice against the blend or fall back to the legacy template-token
path. Nothing, until now, proved the receipt's SHAPE stays intact — a future
edit to the ladder that silently drops a key, widens an enum, or lets
``hold``/``degradation`` both fire on the same receipt would only surface as
a confusing FAB-QC misfire downstream, never as a named regression at the
source. This module is that named check.

stdlib-only, deterministic, no network, no third-party ``jsonschema``
dependency (the four ``allOf`` cross-field rules in
``persona-bundle-receipt.schema.json`` are hand-implemented below rather than
run through a generic schema engine, matching this repo's stdlib-only
convention — see ``persona_crosswalk.py``'s own docstring).

Used by:
  - ``scripts/guard-fab-qc-gate.sh`` (B-U8/U22): asserts the schema file
    exists, the validator imports, and a REAL receipt written by the ladder's
    own self-test validates clean.
  - ``tests/unit/persona-bundle-ladder.test.py`` (B-U8/U22): every ladder
    rung's produced receipt is validated against this schema, not just
    hand-checked field-by-field.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA_PATH = os.path.join(_HERE, "persona-bundle-receipt.schema.json")

REQUIRED_KEYS = (
    "task_id", "source", "bundle_sha", "voice_persona_id", "topic_persona_id",
    "task_personas", "confirm_state", "degradation", "hold", "generated_at",
)
SOURCE_ENUM = ("threaded", "cc", "local", "absent")
CONFIRM_STATE_ENUM = ("confirmed", "pending", "n/a")


def load_schema(path: str = DEFAULT_SCHEMA_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _type_ok(value, expected) -> bool:
    types = expected if isinstance(expected, list) else [expected]
    for t in types:
        if t == "null" and value is None:
            return True
        if t == "string" and isinstance(value, str):
            return True
        if t == "boolean" and isinstance(value, bool):
            return True
        if t == "array" and isinstance(value, list):
            return True
        if t == "object" and isinstance(value, dict):
            return True
    return False


def validate_receipt(receipt: dict, schema: dict | None = None) -> tuple[bool, list[str]]:
    """Validate ``receipt`` against the persona-bundle-receipt schema.

    Returns ``(ok, errors)``. ``errors`` is empty iff ``ok`` is True. Never
    raises on a malformed receipt (a validator that itself crashes on bad
    input is a fail-closed hole, not a guard) — a non-dict receipt is simply
    reported as one clear error.
    """
    if schema is None:
        schema = load_schema()
    errors: list[str] = []

    if not isinstance(receipt, dict):
        return False, [f"receipt is not an object (got {type(receipt).__name__})"]

    props = schema.get("properties", {})
    for key in schema.get("required", REQUIRED_KEYS):
        if key not in receipt:
            errors.append(f"missing required key: {key!r}")

    for key, value in receipt.items():
        spec = props.get(key)
        if spec is None:
            continue  # additionalProperties: true — unknown keys are allowed
        expected_type = spec.get("type")
        if expected_type is not None and not _type_ok(value, expected_type):
            errors.append(f"{key!r}: expected type {expected_type}, got {type(value).__name__} ({value!r})")
        enum = spec.get("enum")
        if enum is not None and value not in enum:
            errors.append(f"{key!r}: value {value!r} not in allowed set {enum}")

    # ── cross-field rules (the schema's allOf block, hand-implemented) ──────
    source = receipt.get("source")
    confirm_state = receipt.get("confirm_state")
    hold = receipt.get("hold")
    degradation = receipt.get("degradation")

    if source == "absent":
        if confirm_state != "n/a":
            errors.append("source='absent' requires confirm_state='n/a'")
        if hold is not False:
            errors.append("source='absent' requires hold=false")

    if hold is True and confirm_state != "pending":
        errors.append("hold=true requires confirm_state='pending'")

    if degradation is not None and confirm_state != "pending":
        errors.append("a non-null degradation requires confirm_state='pending'")

    if hold is True and degradation is not None:
        errors.append("hold and degradation must never both fire on the same receipt (mutually exclusive)")

    return (len(errors) == 0), errors


def main(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Validate a persona-bundle-acquisition receipt against the B-U8/U22 schema.")
    ap.add_argument("receipt_path", nargs="?",
                     help="path to a persona-bundle-receipt.json (or an evidence root's routing/ dir)")
    ap.add_argument("--schema", default=DEFAULT_SCHEMA_PATH)
    ap.add_argument("--self-test", action="store_true",
                     help="run the built-in valid/invalid fixture self-test (no file args needed)")
    a = ap.parse_args(argv)

    if a.self_test:
        return _self_test()

    if not a.receipt_path:
        ap.error("receipt_path is required unless --self-test is given")
        return 2

    path = a.receipt_path
    if os.path.isdir(path):
        cand = os.path.join(path, "routing", "persona-bundle-receipt.json")
        path = cand if os.path.isfile(cand) else os.path.join(path, "persona-bundle-receipt.json")

    try:
        with open(path, encoding="utf-8") as f:
            receipt = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"✗ cannot read/parse {path}: {exc}")
        return 1

    schema = load_schema(a.schema)
    ok, errors = validate_receipt(receipt, schema)
    if ok:
        print(f"✓ {path} — schema OK ({len(REQUIRED_KEYS)} required keys present, all constraints satisfied)")
        return 0
    print(f"✗ {path} — schema INVALID:")
    for e in errors:
        print(f"    - {e}")
    return 1


def _self_test() -> int:
    ok_all = True

    def check(label, cond):
        nonlocal ok_all
        ok_all = ok_all and bool(cond)
        print("  [%s] %s" % ("PASS" if cond else "FAIL", label))

    schema = load_schema()

    valid_confirmed = {
        "task_id": "t1", "source": "threaded", "bundle_sha": "abc123",
        "voice_persona_id": "hormozi-100m-offers", "topic_persona_id": "miller-storybrand",
        "task_personas": [{"seq": 1, "persona_id": "hormozi-100m-offers"}],
        "confirm_state": "confirmed", "degradation": None, "hold": False,
        "generated_at": "2026-07-15T00:00:00Z",
    }
    ok, errs = validate_receipt(valid_confirmed, schema)
    check("valid confirmed receipt validates clean", ok and not errs)

    valid_absent = {
        "task_id": "t3", "source": "absent", "bundle_sha": None,
        "voice_persona_id": None, "topic_persona_id": None, "task_personas": [],
        "confirm_state": "n/a", "degradation": None, "hold": False,
        "generated_at": "2026-07-15T00:00:00Z",
    }
    ok, errs = validate_receipt(valid_absent, schema)
    check("valid absent receipt validates clean", ok and not errs)

    valid_hold = dict(valid_confirmed, confirm_state="pending", hold=True, degradation=None)
    ok, errs = validate_receipt(valid_hold, schema)
    check("valid pending+hold receipt validates clean", ok and not errs)

    valid_degrade = dict(valid_confirmed, confirm_state="pending", hold=False,
                          degradation="audience-unconfirmed-standalone: degraded to house voice")
    ok, errs = validate_receipt(valid_degrade, schema)
    check("valid pending+degradation receipt validates clean", ok and not errs)

    missing_key = dict(valid_confirmed)
    del missing_key["hold"]
    ok, errs = validate_receipt(missing_key, schema)
    check("missing required key 'hold' is rejected", (not ok) and any("hold" in e for e in errs))

    bad_source = dict(valid_confirmed, source="magic")
    ok, errs = validate_receipt(bad_source, schema)
    check("non-enum source value is rejected", (not ok) and any("source" in e for e in errs))

    bad_absent_pairing = dict(valid_absent, confirm_state="confirmed")
    ok, errs = validate_receipt(bad_absent_pairing, schema)
    check("source=absent with confirm_state!=n/a is rejected", (not ok) and any("absent" in e for e in errs))

    hold_and_degrade = dict(valid_confirmed, confirm_state="pending", hold=True,
                             degradation="both firing is a defect")
    ok, errs = validate_receipt(hold_and_degrade, schema)
    check("hold=true AND degradation both set is rejected (mutually exclusive)",
          (not ok) and any("mutually exclusive" in e for e in errs))

    hold_without_pending = dict(valid_confirmed, confirm_state="confirmed", hold=True)
    ok, errs = validate_receipt(hold_without_pending, schema)
    check("hold=true with confirm_state!=pending is rejected", (not ok) and any("hold=true" in e for e in errs))

    wrong_type = dict(valid_confirmed, task_personas="not-a-list")
    ok, errs = validate_receipt(wrong_type, schema)
    check("task_personas as a non-array is rejected", (not ok) and any("task_personas" in e for e in errs))

    ok, errs = validate_receipt("not a dict", schema)
    check("a non-dict receipt is rejected without raising", not ok and len(errs) == 1)

    print("== persona_bundle_receipt_schema self-test: %s ==" % ("ALL PASSED" if ok_all else "FAILED"))
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

#!/usr/bin/env python3
"""validate_launch_plan.py — U-CONTRACT launch-plan validator (stdlib only).

WHY THIS EXISTS
---------------
Skill 49 and Skill 83 will hand one launch plan to a swarm of independent
lanes (email, text, automations, Conversation AI, Command Center). Nothing
else proves those lanes and the planner agree on the same shape. This module
validates a plan JSON against ``launch-plan.schema.json`` and then enforces the
cross-field rules a generic schema engine cannot express:

  * unit ids are unique across pages, email_sequences, text_sets, automations
  * every ``waits_for`` id resolves to a unit in the same plan, never itself
  * the ``waits_for`` graph is acyclic (a cycle would stall the swarm forever)
  * doors_close_at is after doors_open_at
  * conversation_ai.requested == false  =>  mode == "none" (and vice versa)
  * failed_payment automations exist only when offer.payment_plans is true
  * conversation_ai_reply automations exist only when AI is requested
  * at most 5 promotional text sets (spec 3.2)

The schema walker implements exactly the draft-07 keyword set this contract
uses (local ``#/definitions/...`` $ref only). An unimplemented keyword fails
loudly instead of silently passing, matching this repo's stdlib-only
convention (see shared-utils/persona_bundle_receipt_schema.py).

USAGE
-----
    python3 shared-utils/signature_launch_contract/validate_launch_plan.py \
        shared-utils/signature_launch_contract/fixtures/*.json

    python3 shared-utils/signature_launch_contract/validate_launch_plan.py --self-test

Exit 0 = every plan valid; 1 = errors printed one per line; 2 = usage/IO.
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCHEMA_PATH = HERE / "launch-plan.schema.json"
FIXTURE_DIR = HERE / "fixtures"

KNOWN_KEYWORDS = {
    "$schema", "$id", "title", "description", "definitions",
    "$ref", "type", "enum", "const", "required", "properties",
    "additionalProperties", "items", "minItems", "maxItems",
    "uniqueItems", "minLength", "maxLength", "pattern", "minimum",
    "maximum", "format",
}
ANNOTATION_KEYWORDS = {"$schema", "$id", "title", "description", "definitions"}

_UNIT_ARRAYS = ("pages", "email_sequences", "text_sets", "automations")
_FAILED_PAYMENT_FAMILY = "failed_payment"
_AI_FAMILY = "conversation_ai_reply"
_PROMOTIONAL_CAP = 5


def load_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _is_type(value, expected: str) -> bool:
    if expected == "null":
        return value is None
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    raise ValueError("unsupported schema type: %s" % expected)


def _resolve_ref(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError("only local $ref supported, got %r" % ref)
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def _validate_node(value, schema: dict, root: dict, path: str, errors: list) -> None:
    if not isinstance(schema, dict):
        return
    unknown = set(schema) - KNOWN_KEYWORDS
    if unknown:
        raise ValueError("%s: unimplemented schema keyword(s): %s" % (path or "$", sorted(unknown)))

    if "$ref" in schema:
        _validate_node(value, _resolve_ref(root, schema["$ref"]), root, path, errors)
        return

    where = path or "$"

    if "type" in schema:
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(_is_type(value, item) for item in types):
            errors.append("%s: expected type %s, got %s" % (where, types, type(value).__name__))
            return

    if "enum" in schema and value not in schema["enum"]:
        errors.append("%s: %r not in %s" % (where, value, schema["enum"]))

    if "const" in schema and value != schema["const"]:
        errors.append("%s: expected %r, got %r" % (where, schema["const"], value))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append("%s: shorter than %d characters" % (where, schema["minLength"]))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append("%s: longer than %d characters" % (where, schema["maxLength"]))
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append("%s: %r does not match %s" % (where, value, schema["pattern"]))
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                errors.append("%s: %r is not an ISO-8601 date-time" % (where, value))

    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append("%s: %r below minimum %r" % (where, value, schema["minimum"]))
        if "maximum" in schema and value > schema["maximum"]:
            errors.append("%s: %r above maximum %r" % (where, value, schema["maximum"]))

    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append("%s: missing required key %r" % (where, key))
        properties = schema.get("properties", {})
        for key, child in value.items():
            child_path = "%s.%s" % (where, key)
            if key in properties:
                _validate_node(child, properties[key], root, child_path, errors)
            elif schema.get("additionalProperties", True) is False:
                errors.append("%s: unexpected key" % child_path)

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            errors.append("%s: fewer than %d items" % (where, schema["minItems"]))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            errors.append("%s: more than %d items" % (where, schema["maxItems"]))
        if schema.get("uniqueItems") and len(value) != len({json.dumps(item, sort_keys=True) for item in value}):
            errors.append("%s: items are not unique" % where)
        if "items" in schema:
            for index, item in enumerate(value):
                _validate_node(item, schema["items"], root, "%s[%d]" % (where, index), errors)


def _collect_units(plan: dict) -> dict:
    units = {}
    for array in _UNIT_ARRAYS:
        for index, unit in enumerate(plan.get(array, [])):
            if isinstance(unit, dict) and isinstance(unit.get("id"), str):
                units.setdefault(unit["id"], []).append("%s[%d]" % (array, index))
    return units


def _check_cycles(units: dict, graph: dict, errors: list) -> None:
    state = {}

    def visit(node: str, trail: list) -> None:
        if state.get(node) == "done":
            return
        if state.get(node) == "open":
            errors.append("waits_for cycle: %s" % " -> ".join(trail + [node]))
            return
        state[node] = "open"
        for dependency in graph.get(node, []):
            visit(dependency, trail + [node])
        state[node] = "done"

    for node in sorted(graph):
        visit(node, [])


def validate_plan(plan: dict, schema: dict) -> list:
    errors: list = []
    _validate_node(plan, schema, schema, "", errors)
    if errors:
        return errors  # shape is broken; cross-field rules would crash or mislead

    units = _collect_units(plan)
    for unit_id, locations in units.items():
        if len(locations) > 1:
            errors.append("id %r is used by more than one unit: %s" % (unit_id, ", ".join(locations)))

    graph = {}
    for unit_id, locations in units.items():
        unit = None
        for location in locations:
            array, index = location.split("[")
            unit = plan[array][int(index.rstrip("]"))]
            break
        waits_for = unit.get("waits_for", [])
        for dependency in waits_for:
            if dependency == unit_id:
                errors.append("%s: waits_for itself" % unit_id)
            elif dependency not in units:
                errors.append("%s: waits_for unknown unit %r" % (unit_id, dependency))
        graph[unit_id] = [item for item in waits_for if item in units]
    _check_cycles(units, graph, errors)

    calendar = plan["launch_calendar"]
    try:
        opened = datetime.fromisoformat(calendar["doors_open_at"].replace("Z", "+00:00"))
        closed = datetime.fromisoformat(calendar["doors_close_at"].replace("Z", "+00:00"))
        if closed <= opened:
            errors.append("launch_calendar: doors_close_at must be after doors_open_at")
    except ValueError:
        pass  # already reported by the schema walker

    ai = plan["conversation_ai"]
    if ai["requested"] and ai["mode"] == "none":
        errors.append("conversation_ai: requested=true requires a mode other than 'none'")
    if not ai["requested"] and ai["mode"] != "none":
        errors.append("conversation_ai: requested=false requires mode='none'")

    payment_plans = plan["offer"]["payment_plans"]
    for automation in plan.get("automations", []):
        if automation.get("family") == _FAILED_PAYMENT_FAMILY and not payment_plans:
            errors.append("%s: failed_payment automation requires offer.payment_plans=true" % automation.get("id"))
        if automation.get("family") == _AI_FAMILY and not ai["requested"]:
            errors.append("%s: conversation_ai_reply automation requires conversation_ai.requested=true" % automation.get("id"))

    promotional = [item.get("id") for item in plan.get("text_sets", []) if item.get("promotional")]
    if len(promotional) > _PROMOTIONAL_CAP:
        errors.append("text_sets: %d promotional sets exceeds the cap of %d (%s)"
                      % (len(promotional), _PROMOTIONAL_CAP, ", ".join(promotional)))

    return errors


def validate_file(path: Path, schema: dict) -> list:
    plan = load_json(path)
    return ["%s: %s" % (path.name, error) for error in validate_plan(plan, schema)]


def _self_test(schema: dict) -> list:
    """Prove the validator rejects a broken plan, not just accepts good ones."""
    fixture = load_json(FIXTURE_DIR / "elevation.json")
    failures = []

    mutated = json.loads(json.dumps(fixture))
    mutated["automations"][0]["waits_for"] = ["does_not_exist"]
    if not any("unknown unit" in error for error in validate_plan(mutated, schema)):
        failures.append("self-test: dangling waits_for was accepted")

    mutated = json.loads(json.dumps(fixture))
    mutated["pages"][0]["waits_for"] = [mutated["pages"][1]["id"]]
    mutated["pages"][1]["waits_for"] = [mutated["pages"][0]["id"]]
    if not any("cycle" in error for error in validate_plan(mutated, schema)):
        failures.append("self-test: waits_for cycle was accepted")

    mutated = json.loads(json.dumps(fixture))
    mutated["conversation_ai"] = {"requested": True, "mode": "none"}
    if not any("conversation_ai" in error for error in validate_plan(mutated, schema)):
        failures.append("self-test: requested=true with mode=none was accepted")

    mutated = load_json(FIXTURE_DIR / "multi-option.json")
    mutated["text_sets"][0]["opt_out_keyword"] = "STOP2"
    if not validate_plan(mutated, schema):
        failures.append("self-test: a broken text_set was accepted")

    return failures


def main(argv: list) -> int:
    try:
        schema = load_json(SCHEMA_PATH)
    except (OSError, ValueError) as error:
        print("cannot load %s: %s" % (SCHEMA_PATH, error), file=sys.stderr)
        return 2

    if not argv:
        fixtures = sorted(FIXTURE_DIR.glob("*.json"))
        argv = [str(path) for path in fixtures]

    if argv == ["--self-test"]:
        failures = _self_test(schema)
        for failure in failures:
            print(failure, file=sys.stderr)
        print("self-test: %s" % ("PASS" if not failures else "FAIL (%d)" % len(failures)))
        return 0 if not failures else 1

    failed = 0
    for name in argv:
        path = Path(name)
        try:
            errors = validate_file(path, schema)
        except (OSError, ValueError) as error:
            print("%s: cannot read: %s" % (path, error), file=sys.stderr)
            failed += 1
            continue
        if errors:
            failed += 1
            for error in errors:
                print("FAIL " + error, file=sys.stderr)
        else:
            print("PASS %s" % path.name)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

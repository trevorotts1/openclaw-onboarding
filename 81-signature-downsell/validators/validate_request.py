"""Skill 81 downsell request validator (stdlib only, fail-closed).

schemas/downsell-request.schema.json is the D1 page-request contract
(spec 11 section 3; it extends the packet page-request for role
downsell_1). The only pre-existing check on it,
tests/test_request_schema_fixture.py, silently skips when the
third-party jsonschema package is not installed, so on a machine
without that package the contract had no enforcement at all. This
module evaluates the packaged schema with the standard library only,
so the request contract is enforceable anywhere Python runs.

A validator returns a list of violation codes; empty list means pass.
Validators never raise on malformed input: malformed input is a
violation. The evaluator implements the JSON Schema (Draft 2020-12)
keywords the request schema uses (type, const, enum, minLength,
maxLength, minimum, maximum, required, properties, additionalProperties,
items, minItems, maxItems, minProperties, maxProperties). Any other
validation keyword found in the schema fails closed with
D1-REQUEST-UNSUPPORTED-SCHEMA-CONSTRAINT-<KEYWORD> instead of being
silently ignored, so a future schema edit can never quietly widen what
passes here. Annotation keywords (title, description, $schema, and
their kin) carry no validation semantics in the spec and are the only
keywords read and ignored, by design.

Nothing here calls GHL, charges anything, or proves anything about a
live launch; it checks the request object only.
"""
import json
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parents[1] / \
    "schemas" / "downsell-request.schema.json"

# Validation keywords this evaluator implements. Anything with
# validation semantics that is not listed here (pattern, format,
# $ref, allOf/anyOf/oneOf/not, exclusiveMinimum, multipleOf,
# uniqueItems, and the rest) is reported as an unsupported
# constraint rather than skipped: fail closed, never silently widen.
_SUPPORTED_KEYWORDS = {
    "type", "const", "enum",
    "minLength", "maxLength", "minimum", "maximum",
    "required", "properties", "additionalProperties",
    "items", "minItems", "maxItems", "minProperties", "maxProperties",
}

# Annotation keywords: defined by the spec to carry no validation
# semantics, so ignoring them cannot change a verdict.
_ANNOTATION_KEYWORDS = {
    "$schema", "$id", "$anchor", "$dynamicAnchor", "$vocabulary",
    "$comment", "$defs", "definitions", "title", "description",
    "default", "examples", "example", "readOnly", "writeOnly",
    "deprecated", "contentEncoding", "contentMediaType", "contentSchema",
}


def _sanitize(text):
    """A schema keyword or field name as a violation-code segment."""
    return "".join(ch if ch.isalnum() else "_" for ch in str(text)).upper()


def _label(path):
    return "_".join(_sanitize(segment) for segment in path)


def _code(path, suffix):
    label = _label(path)
    return f"D1-REQUEST-{label}-{suffix}" if label else f"D1-REQUEST-{suffix}"


def _json_equal(a, b):
    """JSON Schema equality: numbers compare mathematically, but a
    boolean is never equal to a number (Python's True == 1 must not
    leak into contract checks); containers compare recursively."""
    if isinstance(a, bool) or isinstance(b, bool):
        return isinstance(a, bool) and isinstance(b, bool) and a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and \
            all(_json_equal(a[key], b[key]) for key in a)
    if isinstance(a, list):
        return len(a) == len(b) and \
            all(_json_equal(x, y) for x, y in zip(a, b))
    return a == b


def _is_type(value, name):
    """JSON Schema type test, or None for a type name the spec does
    not define (a schema defect, which the caller fails closed)."""
    if name == "null":
        return value is None
    if name == "boolean":
        return isinstance(value, bool)
    if name == "integer":
        if isinstance(value, bool):
            return False
        if isinstance(value, int):
            return True
        # JSON Schema counts a number with zero fractional part as an
        # integer; a parsed 1.0 is the integer 1.
        return isinstance(value, float) and value.is_integer()
    if name == "number":
        return isinstance(value, (int, float)) \
            and not isinstance(value, bool)
    if name == "string":
        return isinstance(value, str)
    if name == "array":
        return isinstance(value, list)
    if name == "object":
        return isinstance(value, dict)
    return None


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _check(value, schema, path, violations, unsupported):
    """Evaluate one (sub)schema against one value, appending violation
    codes and collecting unsupported schema keywords. Keyword checks
    apply only to values of the kind they govern (minLength to
    strings, minimum to numbers, required/properties to objects),
    exactly as the spec defines them; the type check reports the
    values of the wrong kind."""
    if not isinstance(schema, dict):
        unsupported.add("subschema-not-an-object")
        return
    for keyword in schema:
        if keyword not in _SUPPORTED_KEYWORDS \
                and keyword not in _ANNOTATION_KEYWORDS:
            unsupported.add(keyword)

    type_decl = schema.get("type")
    if type_decl is not None:
        names = type_decl if isinstance(type_decl, list) else [type_decl]
        results = [_is_type(value, name) for name in names]
        if any(result is None for result in results):
            unsupported.add("type")
        elif not any(results):
            violations.append(_code(path, "WRONG-TYPE"))

    if "const" in schema and not _json_equal(value, schema["const"]):
        violations.append(_code(path, "CONST-MISMATCH"))
    if "enum" in schema and not any(
            _json_equal(value, option) for option in schema["enum"]):
        violations.append(_code(path, "NOT-IN-ENUM"))

    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            violations.append(_code(path, "TOO-SHORT"))
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            violations.append(_code(path, "TOO-LONG"))

    if _is_number(value):
        if "minimum" in schema and value < schema["minimum"]:
            violations.append(_code(path, "BELOW-MINIMUM"))
        if "maximum" in schema and value > schema["maximum"]:
            violations.append(_code(path, "ABOVE-MAXIMUM"))

    if isinstance(value, dict):
        for field in schema.get("required") or []:
            if field not in value:
                if path:
                    violations.append(
                        f"D1-REQUEST-{_label(path)}-"
                        f"MISSING-{_label([field])}")
                else:
                    violations.append(
                        f"D1-REQUEST-MISSING-{_label([field])}")
        properties = schema.get("properties") or {}
        for field, subschema in properties.items():
            if field in value:
                _check(value[field], subschema, path + [field],
                       violations, unsupported)
        if "additionalProperties" in schema:
            rule = schema["additionalProperties"]
            extras = sorted(f for f in value if f not in properties)
            if rule is False:
                for field in extras:
                    if path:
                        violations.append(
                            f"D1-REQUEST-{_label(path)}-"
                            f"UNEXPECTED-PROPERTY-{_label([field])}")
                    else:
                        violations.append(
                            "D1-REQUEST-UNEXPECTED-PROPERTY-"
                            f"{_label([field])}")
            elif isinstance(rule, dict):
                for field in extras:
                    _check(value[field], rule, path + [field],
                           violations, unsupported)
            elif rule is not True:
                unsupported.add("additionalProperties")
        if "minProperties" in schema \
                and len(value) < schema["minProperties"]:
            violations.append(_code(path, "TOO-FEW-PROPERTIES"))
        if "maxProperties" in schema \
                and len(value) > schema["maxProperties"]:
            violations.append(_code(path, "TOO-MANY-PROPERTIES"))

    if isinstance(value, list):
        if "minItems" in schema and len(value) < schema["minItems"]:
            violations.append(_code(path, "TOO-FEW-ITEMS"))
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            violations.append(_code(path, "TOO-MANY-ITEMS"))
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                _check(item, item_schema, path + [str(index)],
                       violations, unsupported)


_SCHEMA_CACHE = None


def _packaged_schema():
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is None:
        _SCHEMA_CACHE = json.loads(SCHEMA_PATH.read_text())
    return _SCHEMA_CACHE


def validate_request(request, schema=None):
    """Request: a parsed downsell page-request object. Schema: an
    optional parsed schema; defaults to the packaged
    schemas/downsell-request.schema.json. Returns a list of violation
    codes; empty list means the request satisfies the schema."""
    if not isinstance(request, dict):
        return ["D1-REQUEST-MALFORMED-INPUT"]
    if schema is None:
        try:
            schema = _packaged_schema()
        except (OSError, ValueError):
            return ["D1-REQUEST-SCHEMA-UNAVAILABLE"]
    if not isinstance(schema, dict):
        return ["D1-REQUEST-SCHEMA-UNAVAILABLE"]
    violations = []
    unsupported = set()
    _check(request, schema, [], violations, unsupported)
    for keyword in sorted(unsupported):
        violations.append(
            f"D1-REQUEST-UNSUPPORTED-SCHEMA-CONSTRAINT-{_sanitize(keyword)}")
    return violations

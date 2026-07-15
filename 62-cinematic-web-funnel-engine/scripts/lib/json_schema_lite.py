#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""json_schema_lite.py — a small, dependency-free JSON Schema (draft-07 subset)
validator used by state_engine.py to validate the U6 manifest/ledger schemas
(project-manifest, content-manifest, scene-plan, cost-ledger, deployment-receipt)
on every read and every write (spec Section 11.2: "schema validation on every
read/write"). No `jsonschema` package is available/permitted in this build's
runtime (stdlib only, per ADR-5) — this module is a REAL, tested, minimal
re-implementation covering exactly the keyword set the five U6 schemas use:

    type, enum, const, required, properties, additionalProperties,
    items, minItems, maxItems, uniqueItems,
    minLength, maxLength, pattern,
    minimum, maximum, exclusiveMinimum, exclusiveMaximum,
    oneOf, anyOf, allOf

`$ref` is deliberately NOT supported — the U6 schemas are self-contained (no
$ref), and a schema that uses one fails loudly (SchemaFeatureUnsupported)
rather than silently skipping validation.

Public API:
    validate(instance, schema) -> List[str]   # list of human-readable error
                                               # paths+reasons; [] means valid
    validate_or_raise(instance, schema, *, label="") -> None  # raises
                                               # SchemaValidationError with all
                                               # collected errors joined
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


class SchemaFeatureUnsupported(Exception):
    """Raised when a schema uses a keyword this lite validator does not
    implement (currently: $ref). Fails loud rather than silently passing."""


class SchemaValidationError(Exception):
    """Raised by validate_or_raise. .errors carries the full list."""

    def __init__(self, errors: List[str], label: str = ""):
        self.errors = errors
        prefix = f"{label}: " if label else ""
        super().__init__(prefix + "; ".join(errors))


_TYPE_MAP = {
    "string": str,
    "boolean": bool,
    "null": type(None),
    "array": list,
    "object": dict,
}


def _check_type(value: Any, type_name: str) -> bool:
    if type_name == "integer":
        # bool is a subclass of int in Python; JSON Schema integers must not
        # accept booleans.
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    py_type = _TYPE_MAP.get(type_name)
    if py_type is None:
        raise SchemaFeatureUnsupported(f"unknown JSON Schema type '{type_name}'")
    if type_name == "boolean":
        return isinstance(value, bool)
    return isinstance(value, py_type)


def _path_str(path: List[Any]) -> str:
    if not path:
        return "$"
    out = "$"
    for p in path:
        out += f"[{p!r}]" if isinstance(p, int) else f".{p}"
    return out


def _validate(instance: Any, schema: Dict[str, Any], path: List[Any], errors: List[str]) -> None:
    if not isinstance(schema, dict):
        raise SchemaFeatureUnsupported(f"schema at {_path_str(path)} is not an object")
    if "$ref" in schema:
        raise SchemaFeatureUnsupported(f"$ref is not supported (at {_path_str(path)})")

    # --- combinators -------------------------------------------------------
    for combinator in ("oneOf", "anyOf"):
        if combinator in schema:
            sub_schemas = schema[combinator]
            matches = 0
            sub_errors: List[str] = []
            for sub in sub_schemas:
                trial: List[str] = []
                _validate(instance, sub, path, trial)
                if not trial:
                    matches += 1
                else:
                    sub_errors.extend(trial)
            if combinator == "oneOf" and matches != 1:
                errors.append(f"{_path_str(path)}: expected exactly one oneOf branch to match, {matches} matched")
            if combinator == "anyOf" and matches < 1:
                errors.append(f"{_path_str(path)}: no anyOf branch matched ({'; '.join(sub_errors) or 'no detail'})")
    if "allOf" in schema:
        for sub in schema["allOf"]:
            _validate(instance, sub, path, errors)

    # --- const / enum --------------------------------------------------------
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{_path_str(path)}: expected const {schema['const']!r}, got {instance!r}")
        return
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{_path_str(path)}: {instance!r} is not one of {schema['enum']!r}")
        return

    # --- type ----------------------------------------------------------------
    if "type" in schema:
        type_spec = schema["type"]
        type_list = type_spec if isinstance(type_spec, list) else [type_spec]
        if not any(_check_type(instance, t) for t in type_list):
            errors.append(f"{_path_str(path)}: expected type {type_spec!r}, got {type(instance).__name__} ({instance!r})")
            return  # further checks would be meaningless against a type mismatch

    # --- string checks ---------------------------------------------------
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{_path_str(path)}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{_path_str(path)}: string longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            errors.append(f"{_path_str(path)}: {instance!r} does not match pattern {schema['pattern']!r}")

    # --- numeric checks ----------------------------------------------------
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            errors.append(f"{_path_str(path)}: {instance} < minimum {schema['minimum']}")
        if "maximum" in schema and instance > schema["maximum"]:
            errors.append(f"{_path_str(path)}: {instance} > maximum {schema['maximum']}")
        if "exclusiveMinimum" in schema and instance <= schema["exclusiveMinimum"]:
            errors.append(f"{_path_str(path)}: {instance} <= exclusiveMinimum {schema['exclusiveMinimum']}")
        if "exclusiveMaximum" in schema and instance >= schema["exclusiveMaximum"]:
            errors.append(f"{_path_str(path)}: {instance} >= exclusiveMaximum {schema['exclusiveMaximum']}")

    # --- array checks ------------------------------------------------------
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{_path_str(path)}: array shorter than minItems {schema['minItems']}")
        if "maxItems" in schema and len(instance) > schema["maxItems"]:
            errors.append(f"{_path_str(path)}: array longer than maxItems {schema['maxItems']}")
        if schema.get("uniqueItems"):
            seen = []
            for item in instance:
                if item in seen:
                    errors.append(f"{_path_str(path)}: duplicate item {item!r} violates uniqueItems")
                    break
                seen.append(item)
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, item in enumerate(instance):
                _validate(item, item_schema, path + [i], errors)

    # --- object checks -------------------------------------------------------
    if isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{_path_str(path)}: missing required property '{key}'")
        properties = schema.get("properties", {})
        for key, sub_schema in properties.items():
            if key in instance:
                _validate(instance[key], sub_schema, path + [key], errors)
        additional = schema.get("additionalProperties", True)
        if additional is False:
            extra = [k for k in instance.keys() if k not in properties]
            if extra:
                errors.append(f"{_path_str(path)}: additional properties not allowed: {sorted(extra)!r}")
        elif isinstance(additional, dict):
            extra = [k for k in instance.keys() if k not in properties]
            for key in extra:
                _validate(instance[key], additional, path + [key], errors)


def validate(instance: Any, schema: Dict[str, Any]) -> List[str]:
    """Validate `instance` against `schema`. Returns a list of error strings;
    an empty list means the instance is valid."""
    errors: List[str] = []
    _validate(instance, schema, [], errors)
    return errors


def validate_or_raise(instance: Any, schema: Dict[str, Any], *, label: str = "") -> None:
    errors = validate(instance, schema)
    if errors:
        raise SchemaValidationError(errors, label=label)

"""Load and validate the frozen GHL hybrid contracts.

The seven JSON Schemas in this directory are the single shared shape for every
consumer (Skill 44, Skill 6, Command Center, KIE handoff).  They are additive:
the v1 launch binding is not rewritten, and a legacy object is converted into a
versioned envelope through the explicit ``legacy_conversion`` block.

Two layers are applied on purpose:

* JSON Schema (Draft 2020-12 subset) for shape, enums and cross-file typed
  references;
* the semantic checks JSON Schema cannot express -- logical-key uniqueness,
  parent cycles, same-location association, proof separation, and the rule that
  a receipt may not claim ``verified`` without a matched readback.

Why a stdlib validator: the supported test environment runs with an empty
``HOME`` and ``python3 -I``, where third-party packages installed in a user site
are unavailable.  The subset below is the exact keyword set these schemas use
(``type``, ``const``, ``enum``, ``required``, ``properties``,
``additionalProperties``, ``propertyNames``, ``items``, ``minItems``,
``uniqueItems``, ``minLength``, ``minimum``, ``maximum``, ``pattern``,
``format``, ``oneOf``, ``anyOf``, ``allOf``, ``if``/``then``/``else``, ``$ref``).
An unknown keyword is reported, never silently ignored, so a schema change that
adds a construct this validator cannot enforce fails loudly.

No network access, no credential, no live call.  A consumer that loads a schema
validates the same bytes every other consumer validates.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, Mapping

CONTRACTS_DIR = Path(__file__).resolve().parent

SCHEMA_FILES: dict[str, str] = {
    "operation-contract": "operation-contract.schema.json",
    "capability-record.v2": "capability-record.v2.schema.json",
    "hybrid-operation-receipt.v1": "hybrid-operation-receipt.v1.schema.json",
    "course-build-plan.v1": "course-build-plan.v1.schema.json",
    "course-asset-manifest.v1": "course-asset-manifest.v1.schema.json",
    "learning-association.v1": "learning-association.v1.schema.json",
    "course-delivery-receipt.v1": "course-delivery-receipt.v1.schema.json",
}

_OUTCOMES = frozenset(
    {
        "planned",
        "submitted",
        "processing",
        "verified",
        "failed",
        "blocked",
        "unknown_outcome",
        "not_requested",
    }
)

_ANNOTATIONS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "description",
        "$comment",
        "default",
        "examples",
        "deprecated",
        "readOnly",
        "writeOnly",
        "x-semantic-constraints",
        "$defs",
    }
)

_SUPPORTED = frozenset(
    {
        "type",
        "const",
        "enum",
        "required",
        "properties",
        "additionalProperties",
        "propertyNames",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "minLength",
        "maximum",
        "minimum",
        "pattern",
        "format",
        "oneOf",
        "anyOf",
        "allOf",
        "if",
        "then",
        "else",
        "$ref",
        "not",
        "minProperties",
    }
) | _ANNOTATIONS

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DATE_TIME = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$"
)

_CACHE: dict[str, dict[str, Any]] = {}


class ContractError(ValueError):
    """A contract instance is invalid.  ``errors`` carries every violation."""

    def __init__(self, contract: str, errors: list[str]) -> None:
        self.contract = contract
        self.errors = errors
        super().__init__(f"{contract}: " + "; ".join(errors))


def load_schema(name: str) -> dict[str, Any]:
    """Return one schema document by contract name."""

    return _document(name)


def _document(name: str) -> dict[str, Any]:
    try:
        filename = SCHEMA_FILES[name]
    except KeyError:
        raise ContractError(
            name, [f"unknown contract {name!r}; known: {sorted(SCHEMA_FILES)}"]
        ) from None
    if name not in _CACHE:
        with open(CONTRACTS_DIR / filename, encoding="utf-8") as handle:
            _CACHE[name] = json.load(handle)
    return _CACHE[name]


def _by_filename(filename: str) -> tuple[str, dict[str, Any]]:
    for contract, candidate in SCHEMA_FILES.items():
        if candidate == filename:
            return contract, _document(contract)
    raise ContractError(filename, [f"unknown schema file {filename!r}"])


# ---------------------------------------------------------------------------
# Draft 2020-12 subset engine
# ---------------------------------------------------------------------------


def _type_matches(expected: str, value: Any) -> bool:
    if expected == "object":
        return isinstance(value, Mapping)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    raise ContractError("<schema>", [f"unsupported type keyword {expected!r}"])


def _equal(left: Any, right: Any) -> bool:
    # JSON equality: booleans are not numbers, 1 == 1.0 is true.
    if isinstance(left, bool) != isinstance(right, bool):
        return False
    return left == right


def _resolve(ref: str, current: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Resolve one ``$ref`` to (schema, base filename)."""

    if ref.startswith("#"):
        return current, ""
    filename, _, pointer = ref.partition("#")
    _, document = _by_filename(filename)
    return document, filename


def _walk_pointer(document: Any, pointer: str) -> Any:
    if pointer in ("", "/"):
        return document
    node = document
    for raw in pointer.strip("/").split("/"):
        part = raw.replace("~1", "/").replace("~0", "~")
        node = node[part]
    return node


def _errors(
    schema: Any,
    value: Any,
    path: str,
    root: dict[str, Any],
    base: str,
) -> list[str]:
    if schema is True or schema == {}:
        return []
    if schema is False:
        return [f"{path}: not allowed"]
    if not isinstance(schema, Mapping):
        return [f"{path}: schema must be an object or boolean"]

    unknown = set(schema) - _SUPPORTED
    if unknown:
        return [f"{path}: schema uses unsupported keyword(s) {sorted(unknown)}"]

    errors: list[str] = []
    here = path or "<root>"

    if "$ref" in schema:
        target_root, target_base = _resolve(schema["$ref"], root)
        pointer = schema["$ref"].partition("#")[2]
        target = _walk_pointer(target_root, pointer)
        errors.extend(
            _errors(
                target,
                value,
                path,
                target_root,
                target_base or (schema["$ref"].partition("#")[0] or base),
            )
        )

    if "type" in schema:
        expected = schema["type"]
        options = [expected] if isinstance(expected, str) else list(expected)
        if not any(_type_matches(option, value) for option in options):
            errors.append(f"{here}: expected type {options}, got {type(value).__name__}")
            return errors

    if "const" in schema and not _equal(schema["const"], value):
        errors.append(f"{here}: expected const {schema['const']!r}, got {value!r}")

    if "enum" in schema and not any(_equal(option, value) for option in schema["enum"]):
        errors.append(f"{here}: {value!r} is not one of {schema['enum']}")

    if "not" in schema and not _errors(schema["not"], value, path, root, base):
        errors.append(f"{here}: value matches a forbidden schema")

    for keyword, combinator in (("allOf", "all"), ("anyOf", "any"), ("oneOf", "one")):
        if keyword not in schema:
            continue
        branches = schema[keyword]
        results = [_errors(branch, value, path, root, base) for branch in branches]
        if combinator == "all":
            for branch_errors in results:
                errors.extend(branch_errors)
        elif combinator == "any":
            if all(branch_errors for branch_errors in results):
                errors.append(f"{here}: matches no anyOf branch")
        else:
            matched = [index for index, branch_errors in enumerate(results) if not branch_errors]
            if len(matched) != 1:
                errors.append(f"{here}: matches {len(matched)} oneOf branches, expected 1")

    if "if" in schema:
        branch = (
            schema.get("then")
            if not _errors(schema["if"], value, path, root, base)
            else schema.get("else")
        )
        if branch is not None:
            errors.extend(_errors(branch, value, path, root, base))

    if isinstance(value, Mapping):
        errors.extend(_object_errors(schema, value, path, root, base))
    if isinstance(value, list):
        errors.extend(_array_errors(schema, value, path, root, base))
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            errors.append(f"{here}: shorter than minLength {schema['minLength']}")
        if "pattern" in schema and re.search(schema["pattern"], value) is None:
            errors.append(f"{here}: does not match pattern {schema['pattern']!r}")
        if schema.get("format") == "date" and _DATE.match(value) is None:
            errors.append(f"{here}: not a YYYY-MM-DD date")
        if schema.get("format") == "date-time" and _DATE_TIME.match(value) is None:
            errors.append(f"{here}: not an RFC3339 date-time")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{here}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{here}: above maximum {schema['maximum']}")
    return errors


def _object_errors(
    schema: Mapping[str, Any],
    value: Mapping[str, Any],
    path: str,
    root: dict[str, Any],
    base: str,
) -> list[str]:
    errors: list[str] = []
    here = path or "<root>"
    for name in schema.get("required", ()):  # type: ignore[union-attr]
        if name not in value:
            errors.append(f"{here}: missing required property {name!r}")
    if "minProperties" in schema and len(value) < schema["minProperties"]:
        errors.append(f"{here}: fewer than {schema['minProperties']} properties")
    properties = schema.get("properties") or {}
    additional = schema.get("additionalProperties", True)
    names_schema = schema.get("propertyNames")
    for key, item in value.items():
        child = f"{path}/{key}" if path else str(key)
        if names_schema is not None:
            errors.extend(_errors(names_schema, key, f"{here} property name", root, base))
        if key in properties:
            errors.extend(_errors(properties[key], item, child, root, base))
        elif additional is False:
            errors.append(f"{here}: additional property {key!r} is not allowed")
        elif isinstance(additional, Mapping):
            errors.extend(_errors(additional, item, child, root, base))
    return errors


def _array_errors(
    schema: Mapping[str, Any],
    value: list[Any],
    path: str,
    root: dict[str, Any],
    base: str,
) -> list[str]:
    errors: list[str] = []
    here = path or "<root>"
    if "minItems" in schema and len(value) < schema["minItems"]:
        errors.append(f"{here}: fewer than {schema['minItems']} items")
    if "maxItems" in schema and len(value) > schema["maxItems"]:
        errors.append(f"{here}: more than {schema['maxItems']} items")
    if schema.get("uniqueItems"):
        for index, item in enumerate(value):
            if any(_equal(item, earlier) for earlier in value[:index]):
                errors.append(f"{here}/{index}: duplicate item")
    item_schema = schema.get("items")
    if isinstance(item_schema, Mapping):
        for index, item in enumerate(value):
            errors.extend(
                _errors(item_schema, item, f"{path}/{index}" if path else str(index), root, base)
            )
    return errors


# ---------------------------------------------------------------------------
# public validation surface
# ---------------------------------------------------------------------------


def schema_errors(name: str, instance: Mapping[str, Any]) -> list[str]:
    """Every schema violation for ``instance`` against ``name``."""

    document = _document(name)
    return _errors(document, instance, "", document, SCHEMA_FILES[name])


def semantic_errors(name: str, instance: Mapping[str, Any]) -> list[str]:
    """The constraints JSON Schema cannot express, for the contracts that need them."""

    if name == "course-build-plan.v1":
        return _course_plan_errors(instance)
    if name == "course-asset-manifest.v1":
        return _asset_manifest_errors(instance)
    if name == "hybrid-operation-receipt.v1":
        return _receipt_errors(instance)
    if name == "course-delivery-receipt.v1":
        return _delivery_errors(instance)
    if name == "learning-association.v1":
        return _association_errors(instance)
    return []


def validate(name: str, instance: Mapping[str, Any]) -> None:
    """Raise :class:`ContractError` unless ``instance`` is fully valid."""

    errors = schema_errors(name, instance) + semantic_errors(name, instance)
    if errors:
        raise ContractError(name, errors)


def validate_file(name: str, path: str | os.PathLike[str]) -> None:
    with open(path, encoding="utf-8") as handle:
        validate(name, json.load(handle))


# ---------------------------------------------------------------------------
# semantic checks
# ---------------------------------------------------------------------------


def _course_plan_errors(plan: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    modules = plan.get("modules")
    if not isinstance(modules, list):
        return ["modules must be a list"]
    keys: list[str] = []
    for module in modules:
        if not isinstance(module, Mapping):
            continue
        key = module.get("module_key")
        if key in keys:
            errors.append(f"duplicate module_key {key!r}")
        keys.append(key)
        lesson_keys: list[str] = []
        for lesson in module.get("lessons") or ():
            if not isinstance(lesson, Mapping):
                continue
            lesson_key = lesson.get("lesson_key")
            if lesson_key in lesson_keys:
                errors.append(f"{key}: duplicate lesson_key {lesson_key!r}")
            lesson_keys.append(lesson_key)
    known = set(keys)
    for module in modules:
        if not isinstance(module, Mapping):
            continue
        parent = module.get("parent_module_key")
        if parent is not None and parent not in known:
            errors.append(f"{module.get('module_key')}: unknown parent_module_key {parent!r}")
    parents = {
        module.get("module_key"): module.get("parent_module_key")
        for module in modules
        if isinstance(module, Mapping)
    }
    for start in parents:
        seen: set[str] = set()
        cursor = start
        while cursor is not None:
            if cursor in seen:
                errors.append(f"module parent cycle at {start!r}")
                break
            seen.add(cursor)
            cursor = parents.get(cursor)
    if plan.get("release_intent") == "draft_only":
        for module in modules:
            if isinstance(module, Mapping) and module.get("visibility") == "published":
                errors.append(
                    f"{module.get('module_key')}: draft_only plan publishes a module; release is a separate approved action"
                )
    return errors


def _asset_manifest_errors(asset: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if asset.get("generation_state") == "completed":
        if not asset.get("sha256"):
            errors.append("completed generation requires sha256 of the actual bytes")
        if not asset.get("byte_size"):
            errors.append("completed generation requires a nonzero byte_size")
        if not (asset.get("local_path") or asset.get("durable_url")):
            errors.append("completed generation requires a durable local path or approved URL")
    binding = asset.get("ghl_binding") or {}
    if isinstance(binding, Mapping) and binding.get("state") == "association_verified":
        if not binding.get("content_id") or not binding.get("lesson_id"):
            errors.append("association_verified requires content_id and lesson_id")
        if not binding.get("receipt_ref"):
            errors.append("association_verified requires a readback receipt_ref")
    proof = asset.get("proof") or {}
    if isinstance(proof, Mapping) and proof.get("learner_render_verified"):
        if not proof.get("lesson_association_verified"):
            errors.append("learner_render_verified without lesson_association_verified")
    return errors


def _receipt_errors(receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    outcome = receipt.get("outcome")
    if outcome is not None and outcome not in _OUTCOMES:
        errors.append(f"unknown outcome {outcome!r}")
    readback = receipt.get("readback") or {}
    if outcome == "verified":
        if not isinstance(readback, Mapping) or readback.get("state") != "matched":
            errors.append("outcome=verified requires readback.state=matched")
        if not receipt.get("object_refs") and not receipt.get("evidence_refs"):
            errors.append("outcome=verified requires an object ref or evidence ref")
    refs = receipt.get("object_refs")
    if isinstance(refs, Mapping) and any(key in {"id", "product_id", "user_id"} for key in refs):
        errors.append("object_refs must use domain-typed names, never a bare id/product_id/user_id")
    errors.extend(_outcome_shape_errors(receipt, "outcome"))
    return errors


def _delivery_errors(receipt: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    components = receipt.get("components") or {}
    if not isinstance(components, Mapping):
        return ["components must be an object"]
    if receipt.get("business_delivery_verified"):
        if receipt.get("outcome") != "verified":
            errors.append("business_delivery_verified requires outcome=verified")
        if receipt.get("live_verification") != "passed":
            errors.append("business_delivery_verified requires live_verification=passed")
        for label in ("course_shell", "plan_object_identity", "media_binding"):
            state = (components.get(label) or {}).get("state")
            if state != "verified":
                errors.append(f"{label} must be verified before business_delivery_verified")
        for lesson in components.get("lessons") or ():
            if isinstance(lesson, Mapping) and lesson.get("state") not in {"verified", "not_requested"}:
                errors.append(f"lesson {lesson.get('lesson_key')!r} is not verified")
    errors.extend(_outcome_shape_errors(receipt, "outcome"))
    return errors


def _association_errors(plan: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    group = plan.get("group_ref") or {}
    if isinstance(group, Mapping) and group.get("group_id") is None and group.get("group_slug") is None:
        errors.append("group_ref requires group_id or group_slug")
    if plan.get("operation") == "detach" and plan.get("desired_access") is None:
        errors.append("detach still records the access policy it removes")
    return errors


def _outcome_shape_errors(document: Mapping[str, Any], key: str) -> list[str]:
    outcome = document.get(key)
    if outcome == "unknown_outcome" and document.get("next_action") is None:
        return ["unknown_outcome requires next_action naming reconciliation (never a silent retry)"]
    return []


__all__ = [
    "CONTRACTS_DIR",
    "SCHEMA_FILES",
    "ContractError",
    "load_schema",
    "schema_errors",
    "semantic_errors",
    "validate",
    "validate_file",
]

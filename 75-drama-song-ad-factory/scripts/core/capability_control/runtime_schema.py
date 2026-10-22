"""Runtime-schema validation for the S75-W04-U2 capability configuration.

The schema is the snapshot at fixtures/runtime-schema.snapshot.json, derived
from the installed runtime surfaces. A proposal is validated as the ENTIRE
resulting configuration (merged document), never as a loose diff: an unknown
or mistyped key is rejected before activation, exactly as finding D30
requires. Compiled runtime bundles are never edited and are refused as write
targets.
"""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class SchemaError:
    path: str
    message: str

    def as_dict(self) -> Dict[str, str]:
        return {"path": self.path, "message": self.message}


@dataclass
class RuntimeSchema:
    schema_id: str
    root: Dict[str, Any]

    @classmethod
    def load(cls, snapshot: Dict[str, Any]) -> "RuntimeSchema":
        return cls(schema_id=snapshot["schema_id"], root=snapshot["root"])

    # ---- validation -------------------------------------------------
    def validate(self, doc: Any) -> List[SchemaError]:
        errors: List[SchemaError] = []
        self._check(doc, self.root, "$", errors)
        return errors

    def _check(self, value: Any, spec: Dict[str, Any], path: str, errors: List[SchemaError]) -> None:
        t = spec.get("type")
        ok = {
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
            "string": isinstance(value, str),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
        }.get(t, True)
        if not ok:
            errors.append(SchemaError(path, "expected type %s, got %s" % (t, type(value).__name__)))
            return
        if "enum" in spec and value not in spec["enum"]:
            errors.append(SchemaError(path, "value %r not in enum %r" % (value, spec["enum"])))
        if t == "string" and "minLength" in spec and len(value) < spec["minLength"]:
            errors.append(SchemaError(path, "string shorter than minLength %d" % spec["minLength"]))
        if t == "object":
            props = spec.get("properties", {})
            for req in spec.get("required", []):
                if req not in value:
                    errors.append(SchemaError(path, "missing required key %r" % req))
            if spec.get("additionalProperties") is False:
                for key in value:
                    if key not in props:
                        errors.append(SchemaError("%s.%s" % (path, key), "unknown key (ad hoc keys break the runtime schema)"))
            for key, sub in props.items():
                if key in value:
                    self._check(value[key], sub, "%s.%s" % (path, key), errors)
        if t == "array" and "items" in spec:
            for i, item in enumerate(value):
                self._check(item, spec["items"], "%s[%d]" % (path, i), errors)


@dataclass
class OwnedMerge:
    """Deep-merge a proposal onto the live configuration on owned sections only.

    Anything outside `owned_sections` must survive byte-for-byte: unrelated
    department models, credentials, aliases, heartbeat policies and user
    preferences are never touched by a capability change.
    """

    owned_sections: List[str]

    def merge(self, base: Dict[str, Any], proposal: Dict[str, Any]) -> Dict[str, Any]:
        for key in proposal:
            if key not in self.owned_sections:
                raise ValueError("proposal touches unowned section %r" % key)
        merged = copy.deepcopy(base)
        for key, value in proposal.items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key] = self._deep(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged

    @staticmethod
    def _deep(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        out = copy.deepcopy(base)
        for key, value in overlay.items():
            if isinstance(value, dict) and isinstance(out.get(key), dict):
                out[key] = OwnedMerge._deep(out[key], value)
            else:
                out[key] = copy.deepcopy(value)
        return out


VENDOR_BUNDLE_MARKERS = (".next-cli-build", "node_modules", "/app/.next", ".webpack")


def assert_writable_target(path: str, cache_paths: List[str]) -> None:
    """Refuse compiled runtime bundles and cache files as configuration targets.

    Capabilities are never handwritten into a cache; caches change only through
    their refresh path with provenance. Vendor bundles are never edited.
    """
    real = os.path.realpath(path)
    for marker in VENDOR_BUNDLE_MARKERS:
        if marker in real:
            raise PermissionError("refusing to write compiled runtime bundle: %s" % real)
    if real.endswith((".js", ".cjs", ".mjs")):
        raise PermissionError("refusing to write a code artifact as configuration: %s" % real)
    for cache in cache_paths:
        if real == os.path.realpath(cache):
            raise PermissionError(
                "refusing to handwrite capabilities into cache %s; use its refresh path" % real
            )

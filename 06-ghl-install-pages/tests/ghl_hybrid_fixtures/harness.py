"""Deterministic fixture harness for the WF22 cross-lane integration tests.

Design rules (Document 2 section 8.5, Document 1 sections 17 and 33):
  * No network, no browser, no owner notification, no GoHighLevel write.
  * A missing upstream artifact is reported as pending/not-run, never invented.
  * A schema validates only the fields this fixture pack declares; it never
    guesses a field the contract does not state.
  * A live canary result can never be upgraded to PASS from an offline test.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, Iterable, List

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))
CONTRACTS_DIR = os.path.join(FIXTURES_DIR, "contracts")
SCENARIOS_DIR = os.path.join(FIXTURES_DIR, "scenarios")
TOOLS_DIR = os.path.dirname(os.path.dirname(FIXTURES_DIR))  # 06-ghl-install-pages/tools

# Evidence labels mandated by Document 1 section 33 (IG-RELEASE-02) and
# Document 2 section 7.3: an offline pass, a live canary and a functional
# verification are three different claims and are never collapsed.
EVIDENCE_LABELS = ("OFFLINE_PASS", "OFFLINE_FAIL", "LIVE_PASS", "LIVE_FAIL",
                   "NOT_RUN", "PENDING", "NOT_REQUESTED")


class FixtureSchemaError(AssertionError):
    """A fixture does not satisfy its declared contract shape."""


def load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_scenario(name: str) -> Dict[str, Any]:
    filename = name if name.endswith(".json") else name + ".json"
    return load_json(os.path.join(SCENARIOS_DIR, filename))


def scenario_names() -> List[str]:
    return sorted(fn for fn in os.listdir(SCENARIOS_DIR) if fn.endswith(".json"))


def load_schema(name: str) -> Dict[str, Any]:
    filename = name if name.endswith(".json") else name + ".json"
    return load_json(os.path.join(CONTRACTS_DIR, filename))


def load_manifest() -> Dict[str, Any]:
    return load_json(os.path.join(CONTRACTS_DIR, "contract-manifest.json"))


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def manifest_file_hashes(contracts_dir: str = CONTRACTS_DIR) -> Dict[str, str]:
    manifest = load_json(os.path.join(contracts_dir, "contract-manifest.json"))
    return dict(manifest["files"])


def actual_file_hashes(contracts_dir: str = CONTRACTS_DIR) -> Dict[str, str]:
    return {
        fn: sha256_file(os.path.join(contracts_dir, fn))
        for fn in sorted(os.listdir(contracts_dir))
        if fn.endswith(".schema.json")
    }


def contract_set_digest(contracts_dir: str = CONTRACTS_DIR) -> str:
    """Stable digest over the declarative files: name + bytes, sorted by name.

    The manifest itself is excluded (a file cannot hash itself); the digest is
    the cross-repository identity the parity test compares.
    """
    h = hashlib.sha256()
    for fn in sorted(os.listdir(contracts_dir)):
        if not fn.endswith(".json") or fn == "contract-manifest.json":
            continue
        h.update(fn.encode("utf-8"))
        h.update(b"\0")
        with open(os.path.join(contracts_dir, fn), "rb") as fh:
            h.update(fh.read())
        h.update(b"\0")
    return h.hexdigest()


def checkpoint_record_path(run_root: str, checkpoint_id: str) -> str:
    return os.path.join(run_root, "contracts", checkpoint_id + ".json")


def checkpoint_state(run_root: str, checkpoint_id: str) -> str:
    """'recorded' when the orchestrator published the checkpoint record, else
    'pending'. Never treats an absent record as a pass."""
    return "recorded" if os.path.isfile(checkpoint_record_path(run_root, checkpoint_id)) else "pending"


def authoritative_contracts_dir(repo_root: str) -> str:
    return os.path.join(repo_root, "shared-utils", "ghl", "contracts")


# ---------------------------------------------------------------------------
# Minimal JSON-Schema subset validator (draft 2020-12 keywords this pack uses)
# ---------------------------------------------------------------------------

_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def validate(instance: Any, schema: Dict[str, Any], path: str = "$") -> None:
    """Validate the declared subset. Unknown keywords are rejected raw so a
    schema this harness cannot enforce can never masquerade as enforced."""
    supported = {"$schema", "$id", "title", "version", "description", "type", "required",
                 "properties", "additionalProperties", "items", "enum", "const", "pattern"}
    unknown = set(schema) - supported
    if unknown:
        raise FixtureSchemaError(f"{path}: schema uses unsupported keywords {sorted(unknown)}")

    declared_type = schema.get("type")
    if declared_type is not None:
        names = declared_type if isinstance(declared_type, list) else [declared_type]
        if not any(_TYPE_CHECKS.get(n, lambda v: False)(instance) for n in names):
            raise FixtureSchemaError(f"{path}: expected type {declared_type}, got {type(instance).__name__}")

    if "const" in schema and instance != schema["const"]:
        raise FixtureSchemaError(f"{path}: expected const {schema['const']!r}, got {instance!r}")

    if "enum" in schema and instance not in schema["enum"]:
        raise FixtureSchemaError(f"{path}: {instance!r} not in enum {schema['enum']!r}")

    if "pattern" in schema and isinstance(instance, str):
        import re
        if re.search(schema["pattern"], instance) is None:
            raise FixtureSchemaError(f"{path}: {instance!r} does not match {schema['pattern']!r}")

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in instance]
        if missing:
            raise FixtureSchemaError(f"{path}: missing required properties {missing}")
        properties = schema.get("properties", {})
        for key, value in instance.items():
            if key in properties:
                validate(value, properties[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                raise FixtureSchemaError(f"{path}: unexpected property {key!r}")

    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            validate(item, schema["items"], f"{path}[{index}]")


def validate_named(instance: Any, schema_name: str) -> None:
    validate(instance, load_schema(schema_name))


def iter_receipts(scenario: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
    return scenario.get("operation_receipts", [])


def classify_evidence(offline: str, live_canary: str, functional: str) -> Dict[str, str]:
    """IG-RELEASE-02: offline, live-canary and functional evidence are labelled
    independently. A live canary that did not run can never be reported PASS."""
    for label in (offline, live_canary, functional):
        if label not in ("PASS", "FAIL", "NOT_RUN", "PENDING", "NOT_REQUESTED"):
            raise ValueError(f"invalid evidence label {label!r}")
    if live_canary == "NOT_RUN" and functional == "PASS":
        raise ValueError("functional verification cannot pass while live canary is NOT_RUN")
    return {
        "offline_tests": "OFFLINE_PASS" if offline == "PASS" else ("OFFLINE_FAIL" if offline == "FAIL" else offline),
        "live_canary": live_canary,
        "functional_verification": functional,
        "claim_upgraded": "false",
    }


def checkpoint_entry(implemented: List[str], tests: List[Dict[str, Any]],
                     acceptance_ids: List[str]) -> Dict[str, Any]:
    """Document 2 section 7.3 shape with the not-run rule enforced: a test that
    did not run carries no exit_code."""
    for entry in tests:
        if entry.get("result") == "not_run" and "exit_code" in entry:
            raise ValueError("a not_run test must not carry an exit_code")
    return {
        "implemented": list(implemented),
        "tests": list(tests),
        "acceptance_ids": list(acceptance_ids),
    }


# ---------------------------------------------------------------------------
# Real Skill 6 receipts store (no GHL I/O)
# ---------------------------------------------------------------------------

def receipts_module():
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    import ghl_receipts  # noqa: E402
    return ghl_receipts


def write_object_receipts(evidence_root: str, receipts: Iterable[Dict[str, Any]]) -> List[str]:
    """Persist scenario object receipts through the real F6 store, so the
    scenario is reduced by production code, not by this harness."""
    mod = receipts_module()
    paths = []
    for spec in receipts:
        receipt = mod.make_receipt(
            spec["object_type"], spec["slug"], spec["action"],
            response_id=spec.get("response_id"),
            request_shape={"object_type": spec["object_type"], "slug": spec["slug"]},
            verify=spec.get("verify"),
            expected_location_id=spec.get("expected_location_id"),
            observed_location_id=spec.get("observed_location_id"),
            run_id=spec.get("run_id"),
        )
        paths.append(mod.write_receipt(evidence_root, receipt))
    return paths

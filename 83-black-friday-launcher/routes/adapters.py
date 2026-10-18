"""Adapter wiring for the Launcher: real entry points, real paths.

Every adapter below is the substrate's own module, invoked at its real
repository path. Nothing is copied, forked or reimplemented. When the
received contract names an entry point the tree does not have, the mismatch
is recorded in CONTRACT_DISCREPANCIES; no shim is created.

Checkout is intentionally NOT a dispatch adapter (CR-S49-003): the order
form is the native Convert and Flow surface installed by Skill 06, and the
bump is a component on that surface, never a route node.
"""
from __future__ import annotations

import inspect
import re
import shlex
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import substrate

PLACEHOLDER_PATTERNS = (re.compile(r"/path/to(?:/|$)"), re.compile(r"<[^>]+>"))


class PlaceholderRefused(ValueError):
    """A /path/to or <...> placeholder reached executable configuration."""


class AdapterError(ValueError):
    """A role has no dispatch adapter, or its real entry point is absent."""


def _refuse_placeholder(label: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise PlaceholderRefused(f"{label}: empty value")
    for pattern in PLACEHOLDER_PATTERNS:
        if pattern.search(value):
            raise PlaceholderRefused(
                f"{label}: {value!r} is a placeholder, not a bound path")


def _require_file(label: str, value: str | Path) -> Path:
    _refuse_placeholder(label, str(value))
    path = Path(value)
    if not path.is_file():
        raise AdapterError(f"{label}: no file at {path}")
    return path


# ---------------------------------------------------------------------------
# Real entry points. `dispatch` marks the six roles dispatch may execute.
# ---------------------------------------------------------------------------
ADAPTERS: Dict[str, Dict[str, Any]] = {
    "landing": {
        "dispatch": True,
        "skill": 71,
        "module": "49-signature-funnel/scripts/landing_bridge.py",
        "entry": "bridge",
        "timeout_s": 1800,
        "note": ("Skill 71 has no landing_bridge module of its own; the "
                 "dispatch adapter is S49's bridge, which calls S71's real "
                 "launch_context.prepare_import via write_intake.py and "
                 "page_result.build_and_write via write_page_result.py."),
    },
    "product_selection": {
        "dispatch": True,
        "skill": 78,
        "module": "78-signature-product-selection/scripts/build_selection_plan.py",
        "entry": "build_plan",
        "second_module": "78-signature-product-selection/scripts/emit_page_result.py",
        "second_entry": "emit",
        "timeout_s": 1800,
        "note": "native S78 chain: build_plan, then emit_page_result.emit",
    },
    "upsell_1": {
        "dispatch": True,
        "skill": 80,
        "module": "49-signature-funnel/scripts/upsell_wrapper.py",
        "entry": "main",
        "consumer_module": "80-signature-upsell/components/adapters/produce.py",
        "consumer_entry": "main",
        "timeout_s": 1800,
        "note": "one wrapper invocation per instance, --slot upsell_1",
    },
    "upsell_2": {
        "dispatch": True,
        "skill": 80,
        "module": "49-signature-funnel/scripts/upsell_wrapper.py",
        "entry": "main",
        "consumer_module": "80-signature-upsell/components/adapters/produce.py",
        "consumer_entry": "main",
        "timeout_s": 1800,
        "note": "same canonical U2 page, --slot upsell_2",
    },
    "downsell_1": {
        "dispatch": True,
        "skill": 81,
        "module": "49-signature-funnel/scripts/downsell_wrapper.py",
        "entry": "main",
        "validator_modules": (
            "81-signature-downsell/validators/validate_request.py",
            "81-signature-downsell/validators/validate_downsell.py",
        ),
        "timeout_s": 1800,
        "note": ("Skill 81 ships no executable consumer; S49's wrapper is the "
                 "runtime composition and loads the pinned S81 validators "
                 "from --skill81-root."),
    },
    "thank_you": {
        "dispatch": True,
        "skill": 82,
        "module": "49-signature-funnel/scripts/translate_thank_you_result.py",
        "entry": "main",
        "consumer_modules": (
            "82-signature-thank-you/scripts/run_manifest.py",
            "82-signature-thank-you/scripts/thank_you_resolver.py",
        ),
        "timeout_s": 600,
        "note": "translates the S82 result + companion run manifest",
    },
}

# Surfaces that are deliberately not dispatch adapters.
NATIVE_SURFACES: Dict[str, Dict[str, Any]] = {
    "checkout": {
        "skill": 79,
        "surface": "native Convert and Flow order form installed by Skill 06",
        "route_node": True,
        "dispatch_adapter": False,
        "contract": "79-signature-order-form/references/checkout.schema.json",
        "validator_module": "79-signature-order-form/scripts/validate_checkout.py",
        "validator_entry": "validate_request",
        "reason": "CR-S49-003: checkout is native platform controls, never a "
                  "custom HTML block and never a dispatch adapter.",
    },
    "bump": {
        "skill": 79,
        "surface": "checkout component",
        "route_node": False,
        "dispatch_adapter": False,
        "reason": "The bump is a COMPONENT on checkout, never a route node.",
    },
}

# Contract-vs-tree differences. Recorded, never papered over.
CONTRACT_DISCREPANCIES: List[Dict[str, str]] = [
    {
        "id": "D-01",
        "contract": "S71 landing bridge module and entry point in "
                    "71-blackceo-signature-page",
        "observed": "No landing_bridge.py exists in the S71 tree. The S71 "
                    "entry points are launch_context.prepare_import (used by "
                    "write_intake.py --launch-context) and "
                    "page_result.build_and_write (used by write_page_result.py). "
                    "The dispatch adapter is 49-signature-funnel/scripts/"
                    "landing_bridge.py, which invokes both.",
        "resolution": "Wired to the real S49 bridge and recorded here; no S71 "
                      "bridge shim was created.",
    },
    {
        "id": "D-02",
        "contract": "downsell_1 wrapper in Skill 81",
        "observed": "Skill 81 ships validators and libraries only, no "
                    "executable consumer. 49-signature-funnel/scripts/"
                    "downsell_wrapper.py is the runtime wrapper and loads the "
                    "pinned S81 validators from --skill81-root.",
        "resolution": "Wired to the real S49 wrapper plus the real S81 "
                      "validators; no 81 CLI shim was created.",
    },
    {
        "id": "D-03",
        "contract": "product_selection adapter command in "
                    "launch-adapters.example.json",
        "observed": "The example embeds the approved launch record path as the "
                    "literal string \"<per-launch: approved launch record "
                    "JSON>\" inside a bash -c command.",
        "resolution": "build_dispatch_config refuses every <...> placeholder "
                      "and binds the caller's real launch record path.",
    },
    {
        "id": "D-04",
        "contract": "upsell adapter entries in launch-adapters.example.json",
        "observed": "The example omits --route-graph; the wrapper then defaults "
                    "to route-graph.json beside the dispatch request.",
        "resolution": "The launcher config passes --route-graph "
                      "{work_dir}/route-graph.json explicitly, matching the "
                      "graph dispatch stages. Not a signature mismatch.",
    },
    {
        "id": "D-05",
        "contract": "checkout as one of the page roles",
        "observed": "launch-adapters.example.json has no checkout entry by "
                    "design; Skill 06 installs the native S79 form.",
        "resolution": "Recorded as an intentional non-adapter. A dispatch "
                      "request for checkout fails closed by name.",
    },
    {
        "id": "D-06",
        "contract": "executable adapter configuration",
        "observed": "launch-adapters.example.json contains /path/to entries and "
                    "a <dispatch run session id> placeholder, including the "
                    "thank_you --author-session.",
        "resolution": "The launcher builder requires real paths and a real "
                      "author session id; it refuses placeholders rather than "
                      "shipping them as executable configuration.",
    },
]

# Signatures the received contract and the shipped wrappers fix. Entries are
# checked against the real imported functions; a difference is recorded in the
# report, never synthesized around.
EXPECTED_SIGNATURES = (
    ("landing_bridge.bridge", "49-signature-funnel/scripts/landing_bridge.py",
     None, "bridge",
     ("request_path", "result_path", "work_dir", "config_path")),
    ("s71_launch_context.prepare_import",
     "71-blackceo-signature-page/scripts/launch_context.py", None,
     "prepare_import",
     ("skill_root", "run_dir", "request_path", "launch_path", "graph_path",
      "consent_path", "brand_file")),
    ("s71_page_result.build_and_write",
     "71-blackceo-signature-page/scripts/page_result.py", None,
     "build_and_write", ("run_dir",)),
    ("s78_build_selection_plan.build_plan",
     "78-signature-product-selection/scripts/build_selection_plan.py", None,
     "build_plan", ("launch", "recommendation", "production")),
    ("s78_emit_page_result.emit",
     "78-signature-product-selection/scripts/emit_page_result.py", None,
     "emit",
     ("plan", "author_session", "request_id", "page_id", "input_hash",
      "request", "artifact_paths", "status", "test_only", "reviewer_session",
      "native_bindings_ref", "blockers")),
    ("s79_validate_checkout.validate_request",
     "79-signature-order-form/scripts/validate_checkout.py", None,
     "validate_request", ("request", "now")),
    ("s80_produce.main",
     "80-signature-upsell/components/adapters/produce.py",
     "80-signature-upsell/components/adapters", "main", ("argv",)),
    ("upsell_wrapper.main",
     "49-signature-funnel/scripts/upsell_wrapper.py", None, "main", ("argv",)),
    ("downsell_wrapper.main",
     "49-signature-funnel/scripts/downsell_wrapper.py", None, "main", ("argv",)),
    ("s81_validate_request.validate_request",
     "81-signature-downsell/validators/validate_request.py", None,
     "validate_request", ("request", "schema")),
    ("s81_validate_downsell.check_entry_guard",
     "81-signature-downsell/validators/validate_downsell.py", None,
     "check_entry_guard", ("state",)),
    ("s82_run_manifest.build_run_manifest",
     "82-signature-thank-you/scripts/run_manifest.py",
     "82-signature-thank-you/scripts", "build_run_manifest",
     ("view", "snapshot", "fulfillment_map", "independent_review",
      "envelope_ref", "snapshot_ref", "map_ref", "result_ref")),
    ("s82_thank_you_resolver.resolve_order_view",
     "82-signature-thank-you/scripts/thank_you_resolver.py", None,
     "resolve_order_view",
     ("snapshot", "fulfillment_map", "expected_identity", "request_context",
      "entitlement_version")),
    ("translate_thank_you_result.main",
     "49-signature-funnel/scripts/translate_thank_you_result.py", None,
     "main", ("argv",)),
)


def contract_report() -> List[Dict[str, Any]]:
    """Inspect each real entry point. A mismatch is reported, never hidden."""
    report: List[Dict[str, Any]] = []
    for name, rel_path, sibling, function_name, expected in EXPECTED_SIGNATURES:
        entry = {"entry": name, "module": rel_path, "function": function_name,
                 "expected": list(expected)}
        try:
            module = substrate.load(
                rel_path, "launcher_check_" + re.sub(r"\W", "_", name), sibling)
        except Exception as exc:  # import failure is a recorded discrepancy
            entry.update({"ok": False, "actual": [], "error": str(exc)})
            report.append(entry)
            continue
        function = getattr(module, function_name, None)
        if not callable(function):
            entry.update({"ok": False, "actual": [],
                          "error": f"{function_name} is absent"})
            report.append(entry)
            continue
        actual = [parameter.name
                  for parameter in inspect.signature(function).parameters.values()]
        entry["actual"] = actual
        entry["ok"] = actual[:len(expected)] == list(expected)
        report.append(entry)
    return report


def signature_discrepancies() -> List[Dict[str, Any]]:
    return [entry for entry in contract_report() if not entry["ok"]]


def adapter_for(role: str) -> Dict[str, Any]:
    if role in NATIVE_SURFACES:
        raise AdapterError(
            f"{role!r} is a native surface, not a dispatch adapter: "
            f"{NATIVE_SURFACES[role]['reason']}")
    if role not in ADAPTERS:
        raise AdapterError(f"unknown page role {role!r}")
    return ADAPTERS[role]


def _python() -> str:
    return sys.executable or "python3"


def build_dispatch_config(*, work_dir: str | Path,
                          launch_record: str | Path,
                          bridge_config: str | Path,
                          author_session: str,
                          copy: Dict[str, str | Path],
                          journey: Dict[str, str | Path],
                          enrichment: Dict[str, str | Path],
                          skill80_root: str | Path | None = None,
                          skill81_root: str | Path | None = None,
                          python: Optional[str] = None) -> Dict[str, Any]:
    """Bind the real adapter commands for one launch. Fails closed.

    No /path/to entry, no <...> token and no missing file may be emitted as
    executable configuration. checkout is not configurable by design.
    """
    work = Path(work_dir)
    if not work.is_dir():
        raise AdapterError(f"work_dir: no directory at {work}")
    launch_path = _require_file("launch_record", launch_record)
    bridge_path = _require_file("bridge_config", bridge_config)
    _refuse_placeholder("author_session", author_session)
    python = python or _python()
    _refuse_placeholder("python", python)
    root49 = substrate.source("49-signature-funnel/scripts")
    root71 = substrate.source("71-blackceo-signature-page")
    root78 = substrate.source("78-signature-product-selection/scripts")
    root80 = Path(skill80_root) if skill80_root else substrate.source(
        "80-signature-upsell")
    root81 = Path(skill81_root) if skill81_root else substrate.source(
        "81-signature-downsell")
    for label, root in (("skill80_root", root80), ("skill81_root", root81)):
        if not root.is_dir():
            raise AdapterError(f"{label}: no directory at {root}")

    copy_files = {role: _require_file(f"copy.{role}", path)
                  for role, path in copy.items()}
    journey_files = {role: _require_file(f"journey.{role}", path)
                     for role, path in journey.items()}
    enrichment_files = {role: _require_file(f"enrichment.{role}", path)
                        for role, path in enrichment.items()}
    for role in ("upsell_1", "upsell_2", "downsell_1"):
        for label, mapping in (("copy", copy_files), ("journey", journey_files),
                               ("enrichment", enrichment_files)):
            if role not in mapping:
                raise AdapterError(f"{label}.{role}: missing per-launch input")

    def quote(value: Any) -> str:
        return shlex.quote(str(value))

    adapters: Dict[str, Dict[str, Any]] = {
        "landing": {
            "command": [python, str(root49 / "landing_bridge.py"),
                        "--request", "{request}",
                        "--result", "{result}",
                        "--work-dir", "{work_dir}",
                        "--bridge-config", str(bridge_path)],
            "timeout_s": ADAPTERS["landing"]["timeout_s"],
        },
        "product_selection": {
            "command": [
                "bash", "-c",
                f"{quote(python)} {quote(root78 / 'build_selection_plan.py')} "
                f"{quote(launch_path)} > {quote(work / 'selection-plan.json')} "
                f"&& {quote(python)} {quote(root78 / 'emit_page_result.py')} "
                f"{quote(work / 'selection-plan.json')} "
                f"--output \"{{result}}\" --author-session s49-native-selection "
                f"--request \"{{request}}\"",
            ],
            "timeout_s": ADAPTERS["product_selection"]["timeout_s"],
        },
        "thank_you": {
            "command": [python, str(root49 / "translate_thank_you_result.py"),
                        "{request}", "{result}", "{work_dir}",
                        "--author-session", author_session],
            "timeout_s": ADAPTERS["thank_you"]["timeout_s"],
        },
    }
    for role in ("upsell_1", "upsell_2"):
        adapters[role] = {
            "command": [python, str(root49 / "upsell_wrapper.py"),
                        "--slot", role,
                        "--request", "{request}",
                        "--result", "{result}",
                        "--launch", str(launch_path),
                        "--route-graph", "{work_dir}/route-graph.json",
                        "--copy", str(copy_files[role]),
                        "--journey", str(journey_files[role]),
                        "--enrichment", str(enrichment_files[role]),
                        "--produce", str(root80 / "components" / "adapters"
                                         / "produce.py")],
            "timeout_s": ADAPTERS[role]["timeout_s"],
        }
    adapters["downsell_1"] = {
        "command": [python, str(root49 / "downsell_wrapper.py"),
                    "--request", "{request}",
                    "--result", "{result}",
                    "--launch", str(launch_path),
                    "--route-graph", "{work_dir}/route-graph.json",
                    "--copy", str(copy_files["downsell_1"]),
                    "--journey", str(journey_files["downsell_1"]),
                    "--enrichment", str(enrichment_files["downsell_1"]),
                    "--skill81-root", str(root81)],
        "timeout_s": ADAPTERS["downsell_1"]["timeout_s"],
    }
    for role, spec in adapters.items():
        for part in spec["command"]:
            _refuse_placeholder(f"adapters.{role}.command", str(part))
    if "checkout" in adapters:
        raise AdapterError("checkout must never be a dispatch adapter")
    return {"adapters": adapters}

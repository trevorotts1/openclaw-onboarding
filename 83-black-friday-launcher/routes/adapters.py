"""Adapter wiring for the Launcher: real entry points, real paths.

Every adapter below is the substrate's own module, invoked at its real
repository path. Nothing is copied, forked or reimplemented. When the
received contract names an entry point the tree does not have, the mismatch
is recorded in CONTRACT_DISCREPANCIES; no shim is created.

Checkout is intentionally NOT a dispatch adapter FOR THE FORM (CR-S49-003): the
order form is the native Convert and Flow surface installed by Skill 06, and the
bump is a component on that surface, never a route node. The checkout PAGE's
design (desktop and mobile wireframes and mockups) does have a design-only
adapter, 49-signature-funnel/scripts/checkout_wrapper.py, wired through
build_dispatch_config(checkout_design=...); it never builds or binds the form.
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
        "image_module": "78-signature-product-selection/scripts/run_image_stages.py",
        "image_entry": "main",
        "timeout_s": 1800,
        "note": ("native S78 chain: build_plan, then run_image_stages.main (the order "
                 "page's wireframes and mockups through Skill 71's shared image "
                 "service; required, never skipped), then "
                 "emit_page_result.emit"),
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
        "design_adapter": True,
        "design_module": "49-signature-funnel/scripts/checkout_wrapper.py",
        "design_entry": "main",
        "design_timeout_s": 1800,
        "contract": "79-signature-order-form/references/checkout.schema.json",
        "validator_module": "79-signature-order-form/scripts/validate_checkout.py",
        "validator_entry": "validate_request",
        "reason": "CR-S49-003: checkout is native platform controls, never a "
                  "custom HTML block and never a dispatch adapter for the form "
                  "(only its design stages have one: design_adapter).",
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
        "observed": "launch-adapters.example.json carries a checkout entry that "
                    "is design-only (checkout_wrapper.py); Skill 06 still "
                    "installs the native S79 form.",
        "resolution": "The form stays an intentional non-adapter. Checkout is "
                      "wired only as the design-only adapter via "
                      "build_dispatch_config(checkout_design=...); without it a "
                      "dispatch request for checkout fails closed by name.",
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
    ("s78_run_image_stages.main",
     "78-signature-product-selection/scripts/run_image_stages.py", None,
     "main", ("argv",)),
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


# The shared image inputs (contract C3) every page follows: one style, one owner, one cap. A role's
# wrapper receives each value through whichever flag it declares, so every role is bound to the same
# brand file, owner, spend cap and design style, and none can be drawn under a different one.
IMAGE_PLAN_FLAGS = (
    ("--skill71-root", "skill71_root"),
    ("--brand-file", "brand_file"),
    ("--brand-owner", "brand_owner"),
    ("--image-cap", "image_cap"),
    ("--design-style", "design_style"),
)
IMAGE_INPUTS_FLAG = "--image-inputs"


def _declares(script: Path, flag: str) -> bool:
    """True when the wrapper's own parser declares this flag (so passing it cannot break it).

    A flag named only in a string (landing_bridge.py and upsell_wrapper.py pass --brand-file on to
    Skill 71) is not declared: the wrapper would refuse it as an unrecognized argument."""
    try:
        text = script.read_text(encoding="utf-8")
    except OSError:
        return False
    return re.search(r"add_argument\(\s*[\"']" + re.escape(flag) + r"[\"']", text) is not None


def image_flags(script: Path, command: List[str], plan: Dict[str, Any],
                inputs_path: Path, root71: Path) -> List[str]:
    """The shared image-plan flags this wrapper declares and its command does not already carry."""
    values = dict(plan, skill71_root=str(root71))
    extra: List[str] = []
    for flag, key in IMAGE_PLAN_FLAGS:
        if flag in command or not _declares(script, flag) or values.get(key) in (None, ""):
            continue
        extra += [flag, str(values[key])]
    if IMAGE_INPUTS_FLAG not in command and _declares(script, IMAGE_INPUTS_FLAG):
        extra += [IMAGE_INPUTS_FLAG, str(inputs_path)]
    return extra


def image_wiring(config: Dict[str, Any]) -> Dict[str, List[str]]:
    """Which shared image flags each configured role actually carries (for the delivery report)."""
    wanted = [flag for flag, _ in IMAGE_PLAN_FLAGS] + [IMAGE_INPUTS_FLAG]
    return {role: [f for f in wanted if f in spec["command"]]
            for role, spec in config["adapters"].items()}


def build_dispatch_config(*, work_dir: str | Path,
                          launch_record: str | Path,
                          bridge_config: str | Path,
                          author_session: str,
                          copy: Dict[str, str | Path],
                          journey: Dict[str, str | Path],
                          enrichment: Dict[str, str | Path],
                          image_inputs: str | Path,
                          order_page_inputs: str | Path | None = None,
                          skill80_root: str | Path | None = None,
                          skill81_root: str | Path | None = None,
                          image_provider: str = "stub",
                          allow_paid: bool = False,
                          python: Optional[str] = None,
                          checkout_design: Optional[Dict[str, Any]] = None,
                          image_plan: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Bind the real adapter commands for one launch. Fails closed.

    No /path/to entry, no <...> token and no missing file may be emitted as
    executable configuration. The native checkout form is not configurable by
    design; checkout_design (manuscript, brand_file, brand_owner, image_cap and
    optionally design_style) wires only the checkout page's design stages.

    image_inputs (required) is the per-launch inputs file for the order page's
    wireframes and mockups (78 run_image_stages.py --inputs). Every funnel that
    has a product_selection page gets all of its pages, so the order page's
    image step is never optional: a missing, empty or "none" value is refused
    the same way a missing launch_record is. The product_selection command
    makes the images before it writes the page result and never passes
    --allow-paid.

    image_plan (the resolved C3 inputs: design_style, brand_file, brand_owner, image_cap, ...) binds
    every role to the same style, owner, cap and Skill 71 root through the flags each wrapper declares;
    see image_flags and image_wiring.
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

    if image_inputs is None or str(image_inputs).strip().lower() in ("", "none"):
        raise AdapterError(
            "image_inputs: required; a funnel with an order page gets its "
            "wireframes and mockups, so the image step cannot be skipped")
    images_path = _require_file("image_inputs", image_inputs)
    # Skill 78 reads its own shape of the same values (route_graph, provider, test_run); Skill 49's
    # wrappers refuse any key outside contract C3, so the two readers get two files.
    order_inputs_path = _require_file("order_page_inputs", order_page_inputs or image_inputs)
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
                        "--bridge-config", str(bridge_path),
                        "--landing-pages", "{landing_pages}"],
            "timeout_s": ADAPTERS["landing"]["timeout_s"],
        },
        "product_selection": {
            "command": [
                "bash", "-c",
                f"{quote(python)} {quote(root78 / 'build_selection_plan.py')} "
                f"{quote(launch_path)} > {quote(work / 'selection-plan.json')} "
                f"&& {quote(python)} {quote(root78 / 'run_image_stages.py')} "
                f"--plan {quote(work / 'selection-plan.json')} "
                f"--request \"{{request}}\" "
                f"--run-dir {quote(work / 'order-page-images')} "
                f"--launch-record {quote(launch_path)} "
                f"--inputs {quote(order_inputs_path)} "
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
                                         / "produce.py"),
                        # wireframes and mockups through Skill 71's page-type runner;
                        # stub is free, kie spends money and needs allow_paid
                        "--bridge-config", str(bridge_path),
                        "--image-provider", image_provider,
                        *(["--allow-paid"] if allow_paid else [])],
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
    if checkout_design is not None:
        surface = NATIVE_SURFACES["checkout"]
        manuscript = _require_file("checkout_design.manuscript", checkout_design["manuscript"])
        brand_file = _require_file("checkout_design.brand_file", checkout_design["brand_file"])
        command = [python, str(substrate.source(surface["design_module"])),
                   "--request", "{request}", "--result", "{result}",
                   "--manuscript", str(manuscript),
                   "--design-prose", "{work_dir}/design-prose-checkout.json",
                   "--launch", str(launch_path),
                   "--route-graph", "{work_dir}/route-graph.json",
                   "--brand-file", str(brand_file),
                   "--brand-owner", str(checkout_design["brand_owner"]),
                   "--image-cap", str(checkout_design["image_cap"]),
                   "--run-dir", "{work_dir}/checkout-run",
                   "--skill71-root", str(root71)]
        if checkout_design.get("design_style"):
            command += ["--design-style", str(checkout_design["design_style"])]
        adapters["checkout"] = {"command": command, "timeout_s": surface["design_timeout_s"]}
    if image_plan is not None:
        scripts = {"landing": "landing_bridge.py", "upsell_1": "upsell_wrapper.py",
                   "upsell_2": "upsell_wrapper.py", "downsell_1": "downsell_wrapper.py",
                   "thank_you": "translate_thank_you_result.py", "checkout": "checkout_wrapper.py"}
        for role, name in scripts.items():
            if role in adapters:
                adapters[role]["command"] += image_flags(
                    root49 / name, adapters[role]["command"], image_plan, images_path, root71)
        # the downsell wrapper draws its own pages, so it carries the provider the others already do
        down = adapters["downsell_1"]["command"]
        if "--image-provider" not in down and _declares(root49 / "downsell_wrapper.py", "--image-provider"):
            down += ["--image-provider", image_provider]
            if allow_paid and "--allow-paid" not in down:
                down.append("--allow-paid")
    for role, spec in adapters.items():
        for part in spec["command"]:
            _refuse_placeholder(f"adapters.{role}.command", str(part))
    design_module = Path(NATIVE_SURFACES["checkout"]["design_module"]).name
    if "checkout" in adapters and not any(design_module in str(p) for p in adapters["checkout"]["command"]):
        raise AdapterError("checkout may only be the design-only adapter; the native form is never "
                           "a dispatch adapter")
    return {"adapters": adapters}

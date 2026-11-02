"""Native Convert and Flow checkout mapping, bound to the Skill 79 contract.

Checkout is the native order form installed by Skill 06 (CR-S49-003). It is a
route node and it is NEVER a dispatch adapter. There is no checkout adapter in
this module and none may be added.

What this module does: it reads the real Skill 79 checkout contract, maps the
launch's own verified facts onto that contract's field names, and calls the real
Skill 79 cross-field validator as a live binding probe. Anything the launch does
not supply stays explicitly unknown. Nothing is defaulted into a field the
contract calls commercial.

`checkout_mode` is `combined_single_offer` for every journey: one simple offer is one
order form, and several mains (`multiple_options`, `folded_levels`) are one native
combined_single_offer order form per main price choice (`checkout_instances`).
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .constants import (
    CHECKOUT_CONTRACT_REF,
    CHECKOUT_SKILL_SLUG,
    CHECKOUT_VALIDATOR_REF,
    REPO_ROOT,
    skill_path,
)

MODE_BY_JOURNEY = {
    "single_simple": "combined_single_offer",
    # several mains (multiple_options, folded_levels): one native combined_single_offer
    # order form per main price choice (DECISIONS-NEEDED[4]); see checkout_instances.
    "multiple_options": "combined_single_offer",
    "folded_levels": "combined_single_offer",
}

# A field is "supplied" only when the launch actually carries it.
SUPPLIED_FIELDS = (
    "approved_plan_hash",
    "tenant_id",
    "location_id",
    "launch_id",
    "launch_revision",
    "launch_plan_approval_ref",
    "brand_ref",
    "brand_revision",
    "checkout_mode",
    "main_offer_id",
    "main_price",
    "bump",
    "test_only",
)

# Operational, non-commercial: a single-quantity digital order. Recorded as a
# default with a reason so no commercial fact rides along with it.
OPERATIONAL_DEFAULTS = {
    "quantity": (1, "single-quantity order form; not a commercial fact"),
}


# Facts that only the Skill 06 read-back can supply (CHK-16): merged from that
# record alone, never defaulted. Intake owns terms_ref, consent_ref and bump copy.
READBACK_FACTS = ("native_capability_evidence_ref", "fulfillment_mapping_ref",
                  "failed_pending_requirements")
BUMP_READBACK = ("component_id", "component_version", "quantity_policy",
                 "fulfillment_rule_ref")
BUMP_UNRESOLVABLE = ("component_id", "component_version", "applicable_main_offer_ids",
                     "entitlement_ids", "headline", "benefit_explanation",
                     "quantity_policy", "fulfillment_rule_ref")
# Bookkeeping that annotates a record but is not a contract field: the S79
# request schemas set additionalProperties false, so none of it may reach a probe.
BOOKKEEPING_KEYS = ("unknown", "unresolved")


class CheckoutMappingError(Exception):
    """The Skill 79 contract cannot be read or bound."""


def _repo_ref(path: Path) -> str:
    """A path's repository-relative spelling, whichever convention resolved it."""
    try:
        return str(Path(path).relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def contract_path() -> Path:
    return skill_path(CHECKOUT_SKILL_SLUG, CHECKOUT_CONTRACT_REF)


def validator_path() -> Path:
    return skill_path(CHECKOUT_SKILL_SLUG, CHECKOUT_VALIDATOR_REF)


def contract_ref() -> str:
    return _repo_ref(contract_path())


def validator_ref() -> str:
    return _repo_ref(validator_path())


def load_contract() -> Dict[str, Any]:
    path = contract_path()
    if not path.is_file():
        raise CheckoutMappingError(f"Skill 79 contract not found at {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CheckoutMappingError(f"Skill 79 contract unreadable ({exc})") from exc


def required_fields(contract: Dict[str, Any]) -> List[str]:
    request = (contract.get("$defs") or {}).get("checkout_request") or {}
    created = request.get("required")
    if not isinstance(created, list) or not created:
        raise CheckoutMappingError("checkout_request declares no required fields")
    return list(created)


def checkout_modes(contract: Dict[str, Any]) -> List[str]:
    request = (contract.get("$defs") or {}).get("checkout_request") or {}
    mode = (request.get("properties") or {}).get("checkout_mode") or {}
    enum = mode.get("enum")
    if not isinstance(enum, list) or not enum:
        raise CheckoutMappingError("checkout_mode declares no enum")
    return list(enum)


def _load_validator():
    path = validator_path()
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("launcher_s79_validate_checkout", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _main_offers(intake: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [o for o in intake["offers"] if o["role"] == "main"]


def _price_choice(offer: Dict[str, Any], intake: Dict[str, Any],
                  readback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """One price choice. Native ids and the exponent come only from the intake's
    checkout block or the read-back; a fact nobody holds is named, never invented."""
    block = offer.get("checkout") or {}
    price = offer["price"]
    # The read-back keys native ids by the Skill 49 price_choice_id (<offer_id>-<currency>);
    # the bare offer id is accepted too.
    ids = (readback or {}).get("native") or {}
    native = ids.get(f"{offer['offer_id']}-{price['currency']}") or ids.get(offer["offer_id"]) or {}
    choice: Dict[str, Any] = {
        "price_choice_id": offer["offer_id"],
        "amount_minor": price["amount_minor"],
        "currency": price["currency"],
        # The S79 price_choice types these as string-or-null: null is the
        # contract's own way to say "no native mapping supplied".
        "native_product_id": native.get("native_product_id", block.get("native_product_id")),
        "native_price_id": native.get("native_price_id", block.get("native_price_id")),
    }
    if block.get("billing_type"):
        choice["billing_type"] = block["billing_type"]
    exponent = native.get("currency_exponent")
    if isinstance(exponent, int) and not isinstance(exponent, bool):
        choice["currency_exponent"] = exponent
    if intake.get("test_only"):
        choice["approval_status"] = "test_only"
    unknown = [n for n in ("currency_exponent", "billing_type", "approval_status")
               if n not in choice]
    if unknown:  # an annotation, never part of the probe request (contract_request)
        choice["unknown"] = unknown
    return choice


def instances_module():
    """The per-offer checkout realisation (one native checkout per main price
    choice), or None when this tree does not carry it."""
    name = f"{__package__}.checkout_instances"
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as exc:
        if exc.name == name:
            return None
        raise


def _bump_config(bump: Dict[str, Any], mains: List[Dict[str, Any]], intake: Dict[str, Any],
                 readback: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    price = _price_choice(bump, intake, readback)
    config: Dict[str, Any] = {
        "offer_id": bump["offer_id"],
        "price": price,
        "default_selected": False,
        "enabled": True,
    }
    for key in ("native_product_id", "native_price_id"):
        if price.get(key):
            config[key] = price[key]
    block = bump.get("checkout") or {}
    for key in ("headline", "benefit_explanation"):
        if block.get(key):
            config[key] = block[key]
    if bump.get("delivery") and len(mains) == 1:  # the validated intake carries the commercial block
        config["applicable_main_offer_ids"] = [mains[0]["offer_id"]]
        config["entitlement_ids"] = [bump["offer_id"].lower()]
    rb_bump = (readback or {}).get("bump") or {}
    for key in BUMP_READBACK:
        if key in rb_bump:
            config[key] = rb_bump[key]
    unresolved = [n for n in BUMP_UNRESOLVABLE if n not in config]
    if unresolved:  # an annotation, never part of the probe request
        config["unresolved"] = unresolved
    return config


def order_form_mapping(intake: Dict[str, Any], graph: Dict[str, Any],
                       readback: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Map verified launch facts onto the real Skill 79 checkout contract.

    ``readback`` is the Skill 06 read-back record (native ids, capability and
    fulfillment refs, bump component facts). It is recorded in the mapping so
    the mapping can be re-derived from its inputs.
    """
    contract = load_contract()
    required = required_fields(contract)
    modes = checkout_modes(contract)
    journey = intake["journey_mode"]
    mode = MODE_BY_JOURNEY.get(journey)
    mains = _main_offers(intake)
    route_roles = [n["role"] for n in graph.get("nodes", [])]
    rb = readback or {}

    supplied: Dict[str, Any] = {
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "launch_revision": intake["revision"],
        "launch_plan_approval_ref": intake["approval"]["ref"],
        "approved_plan_hash": intake["approval"]["hash"],
        "brand_ref": intake["brand"]["ref"],
        "brand_revision": intake["brand"]["hash"],
        "test_only": bool(intake.get("test_only")),
    }
    if mode is not None:
        supplied["checkout_mode"] = mode
    terms = intake.get("checkout_terms") or {}
    for name in ("terms_ref", "consent_ref"):
        if terms.get(name):
            supplied[name] = terms[name]
    for name in READBACK_FACTS:
        if name in rb:
            supplied[name] = rb[name]
    if len(mains) == 1:
        main = mains[0]
        supplied["main_offer_id"] = main["offer_id"]
        supplied["main_price"] = _price_choice(main, intake, readback)
        if main.get("delivery"):  # the validated intake carries the commercial block
            supplied["successful_payment_next_route"] = main["delivery"]["destination"]
            supplied["main_entitlement_ids"] = [main["offer_id"].lower()]
            supplied["previously_purchased_entitlement_ids"] = []
            if mode == "combined_single_offer":
                supplied["selection_ref"] = None
    bump = next((o for o in intake["offers"] if o["role"] == "bump"), None)
    # The contract allows an explicit null when there is no bump.
    supplied["bump"] = None if bump is None else _bump_config(bump, mains, intake, readback)
    for name, (value, _reason) in OPERATIONAL_DEFAULTS.items():
        supplied.setdefault(name, value)

    unknown = sorted({f for f in required if f not in supplied})

    notes: List[str] = []
    if mode is None:
        notes.append(
            f"journey_mode {journey!r} has {len(mains)} distinct main offers and no "
            "selection page; the Skill 79 contract's two modes "
            f"{modes!r} express neither, so checkout_mode stays unknown")
    if any(f not in ADMINISTRABLE for f in unknown):
        notes.append(
            "unknown fields are launch facts nobody supplied; they are never "
            "defaulted and never zero")

    blockers = [] if mode else [
        f"AF-LAUNCH-CHECKOUT-MODE: journey_mode {journey!r} has no Skill 79 "
        f"checkout_mode; delivery is blocked until the contract names one"]
    if mode == "post_selection" and not supplied.get("selection_ref"):
        blockers.append(
            "AF-LAUNCH-CHECKOUT-SELECTION: post_selection checkout has no selection_ref, "
            "so the buyer's pick is bound to no price; delivery is blocked")

    mapping = {
        "surface": "native Convert and Flow order form installed by Skill 06",
        "contract": contract_ref(),
        "contract_title": contract.get("title"),
        "contract_schema_version": ((contract.get("properties") or {})
                                    .get("schema_version") or {}).get("const"),
        "contract_sha256": hashlib.sha256(contract_path().read_bytes()).hexdigest(),
        "contract_modes": modes,
        "dispatch_adapter": False,
        "route_node": "checkout" if "checkout" in route_roles else None,
        "realisation": "single_request",
        "checkout_mode": mode,
        "checkout_mode_state": "resolved" if mode else "contract_gap",
        "main_offers": [{"offer_id": o["offer_id"],
                         "price": _price_choice(o, intake, readback)} for o in mains],
        "supplied": supplied,
        "unknown": unknown,
        "operational_defaults": {k: {"value": v, "reason": reason}
                                 for k, (v, reason) in OPERATIONAL_DEFAULTS.items()},
        "readback": readback,
        "notes": notes,
    }
    instances = instances_module() if len(mains) > 1 else None
    if instances is not None:
        # One native combined_single_offer order form per main price choice. The
        # top-level probe below only proves the contract binding; the instance
        # replay is the delivery verdict for this realisation.
        rec = instances.record(intake, graph, readback=readback)
        mapping.update({
            "realisation": "per_offer_instances",
            "instances": rec["instances"],
            "binding_plan": rec["binding_plan"],
            "checkout_mode": "combined_single_offer",
            "checkout_mode_state": "resolved",
        })
        blockers = list(rec["violations"])
    # An unresolved mode is a withheld delivery, not a recorded pass.
    # check_rules/checkout.py enforces it; recording it here means a consumer of
    # the mapping sees the block without re-deriving it.
    mapping["delivery_blocked"] = bool(blockers)
    mapping["delivery_blockers"] = blockers
    mapping["validator"] = _probe_validator(mapping, supplied)

    # A rejected probe means required facts are still missing. The record says so
    # in words a client can read; check_rules/checkout.py only lets an offline
    # design-only package pass when this label is present and true.
    missing = missing_facts(contract_request(supplied))
    rejected = (mapping["validator"].get("probe") or {}).get("result") == "rejected"
    if mapping["realisation"] == "per_offer_instances":
        missing = sorted({m for i in mapping["instances"] for m in i.get("missing") or []})
        rejected = bool(blockers)
    mapping["missing_facts"] = missing if rejected else []
    mapping["checkout_incomplete_label"] = (
        f"checkout incomplete: {len(missing)} required checkout fact(s) are not supplied "
        f"({', '.join(missing)}); this package is design-only and cannot take an order"
        if rejected else None)
    return mapping


# Fields a caller can fill; listed only so the notes stay truthful.
ADMINISTRABLE = set(SUPPLIED_FIELDS) | set(OPERATIONAL_DEFAULTS)


def contract_request(supplied: Dict[str, Any],
                     defaults: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """The inner checkout_request envelope, built from contract fields only.

    Document-level fields (schema_version) and this module's own bookkeeping
    (``unknown`` / ``unresolved``) are not contract fields, and the S79 schemas set
    additionalProperties false: carrying one makes every probe a shape rejection
    instead of evidence about the launch's missing facts (CHK-03).
    """
    props = ((load_contract().get("$defs") or {}).get("checkout_request") or {}).get("properties") or {}
    request = {k: v for k, v in dict(supplied or {}).items() if k in props}
    for name, entry in (defaults or {}).items():
        if isinstance(entry, dict) and "value" in entry:
            request[name] = entry["value"]

    def clean(block: Any) -> Any:
        return ({k: v for k, v in block.items() if k not in BOOKKEEPING_KEYS}
                if isinstance(block, dict) else block)

    for name in ("main_price", "bump"):
        if isinstance(request.get(name), dict):
            request[name] = clean(request[name])
    if isinstance(request.get("bump"), dict) and isinstance(request["bump"].get("price"), dict):
        request["bump"]["price"] = clean(request["bump"]["price"])
    return request


def missing_facts(request: Dict[str, Any]) -> List[str]:
    """Required contract facts a request does not carry, named by field."""
    contract = load_contract()
    defs = contract.get("$defs") or {}
    out = [f for f in required_fields(contract) if f not in request]
    if request.get("checkout_mode") == "post_selection" and not request.get("selection_ref"):
        out.append("selection_ref")
    for name, ref in (("main_price", "price_choice"), ("bump", "bump_config")):
        block = request.get(name)
        if isinstance(block, dict):
            out += [f"{name}.{k}" for k in (defs.get(ref) or {}).get("required", []) if k not in block]
    return sorted(set(out))


def replay(request: Dict[str, Any]) -> Tuple[str, str]:
    """Run a request through the real S79 validator: ("accepted"|"rejected"|"unavailable", detail)."""
    try:
        module = _load_validator()
    except Exception as exc:  # import failure is a recorded fact
        return "unavailable", f"{exc} (interpreter {sys.executable})"
    if module is None or not callable(getattr(module, "validate_request", None)):
        return "unavailable", f"validate_request is absent (interpreter {sys.executable})"
    try:
        module.validate_request(request)
    except Exception as exc:  # the contract's own typed validation error
        return "rejected", str(exc)
    return "accepted", ""


def _probe_validator(mapping: Dict[str, Any],
                     supplied: Dict[str, Any]) -> Dict[str, Any]:
    """Call the real Skill 79 validator. The binding is proved, not assumed.

    The validator loads in this process, so it runs under ``sys.executable`` and
    nothing else. Every record names that interpreter: a missing dependency of
    jsonschema (``No module named 'attrs'``) is otherwise unattributable on a
    machine with more than one Python (Big Fleet Roll error log, row 23).
    """
    interpreter = sys.executable
    defaults = {k: {"value": v} for k, (v, _reason) in OPERATIONAL_DEFAULTS.items()}
    state, detail = replay(contract_request(supplied, defaults))
    if state == "unavailable":
        return {"module": validator_ref(), "state": "unavailable",
                "error": detail.rsplit(" (interpreter", 1)[0], "interpreter": interpreter}
    probe: Dict[str, Any] = {"module": validator_ref(), "state": "bound",
                             "interpreter": interpreter}
    if state == "accepted":
        probe["probe"] = {"result": "accepted"}
    else:
        probe["probe"] = {
            "result": "rejected",
            "error": detail,
            "meaning": ("the Skill 79 contract is bound and names the facts this "
                        "launch still does not supply; a rejected probe is "
                        "recorded, never a substituted value"),
        }
    return probe

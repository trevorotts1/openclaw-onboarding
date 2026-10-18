"""Native Convert and Flow checkout mapping, bound to the Skill 79 contract.

Checkout is the native order form installed by Skill 06 (CR-S49-003). It is a
route node and it is NEVER a dispatch adapter. There is no checkout adapter in
this module and none may be added.

What this module does: it reads the real Skill 79 checkout contract, maps the
launch's own verified facts onto that contract's field names, and calls the real
Skill 79 cross-field validator as a live binding probe. Anything the launch does
not supply stays explicitly unknown. Nothing is defaulted into a field the
contract calls commercial.

`checkout_mode` is resolved only where the Skill 79 contract has a mode for the
launch shape (`post_selection` after a Product Selection page,
`combined_single_offer` for one simple offer). `folded_levels` has three main
offers and no selection page, and the S79 contract expresses neither; that is
recorded as a contract gap rather than invented into a mode.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from .constants import CHECKOUT_CONTRACT, CHECKOUT_VALIDATOR

MODE_BY_JOURNEY = {
    "single_simple": "combined_single_offer",
    "multiple_options": "post_selection",
    # folded_levels: three distinct mains folded into the signature page and no
    # selection page. The S79 contract has exactly two modes and neither says
    # this. Recorded as a gap; never guessed.
    "folded_levels": None,
}

# A field is "supplied" only when the launch actually carries it.
SUPPLIED_FIELDS = (
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


class CheckoutMappingError(Exception):
    """The Skill 79 contract cannot be read or bound."""


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def contract_path() -> Path:
    return _repo_root() / CHECKOUT_CONTRACT


def validator_path() -> Path:
    return _repo_root() / CHECKOUT_VALIDATOR


def load_contract() -> Dict[str, Any]:
    path = contract_path()
    if not path.is_file():
        raise CheckoutMappingError(f"Skill 79 contract not found at {CHECKOUT_CONTRACT}")
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


def _price_choice(offer: Dict[str, Any], intake: Dict[str, Any]) -> Dict[str, Any]:
    price = offer["price"]
    choice: Dict[str, Any] = {
        "price_choice_id": offer["offer_id"],
        "amount_minor": price["amount_minor"],
        "currency": price["currency"],
        # The S79 price_choice types these as string-or-null: null is the
        # contract's own way to say "no native mapping supplied".
        "native_product_id": None,
        "native_price_id": None,
        "unknown": ["currency_exponent", "billing_type", "approval_status"],
    }
    if intake.get("test_only"):
        choice["approval_status"] = "test_only"
        choice["unknown"] = [name for name in choice["unknown"]
                             if name != "approval_status"]
    return choice


def order_form_mapping(intake: Dict[str, Any], graph: Dict[str, Any]) -> Dict[str, Any]:
    """Map verified launch facts onto the real Skill 79 checkout contract."""
    contract = load_contract()
    required = required_fields(contract)
    modes = checkout_modes(contract)
    journey = intake["journey_mode"]
    mode = MODE_BY_JOURNEY.get(journey)
    mains = _main_offers(intake)
    route_roles = [n["role"] for n in graph.get("nodes", [])]

    supplied: Dict[str, Any] = {
        "tenant_id": intake["tenant_id"],
        "location_id": intake["location_id"],
        "launch_id": intake["launch_id"],
        "launch_revision": intake["revision"],
        "launch_plan_approval_ref": intake["approval"]["ref"],
        "brand_ref": intake["brand"]["ref"],
        "brand_revision": intake["brand"]["hash"],
        "test_only": bool(intake.get("test_only")),
    }
    if mode is not None:
        supplied["checkout_mode"] = mode
    if len(mains) == 1:
        supplied["main_offer_id"] = mains[0]["offer_id"]
        supplied["main_price"] = _price_choice(mains[0], intake)
    bump = next((o for o in intake["offers"] if o["role"] == "bump"), None)
    if bump is not None:
        supplied["bump"] = {
            "offer_id": bump["offer_id"],
            "price": _price_choice(bump, intake),
            "default_selected": False,
            "enabled": True,
            # Everything else the bump_config requires is not in hand.
            "unresolved": [
                "component_id", "component_version", "applicable_main_offer_ids",
                "entitlement_ids", "headline", "benefit_explanation",
                "quantity_policy", "fulfillment_rule_ref",
            ],
        }
    else:
        supplied["bump"] = None  # the contract allows an explicit null

    unknown = [f for f in required if f not in supplied]
    unknown += [f for f in OPERATIONAL_DEFAULTS if f not in supplied]

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

    mapping = {
        "surface": "native Convert and Flow order form installed by Skill 06",
        "contract": CHECKOUT_CONTRACT,
        "contract_title": contract.get("title"),
        "contract_schema_version": ((contract.get("properties") or {})
                                    .get("schema_version") or {}).get("const"),
        "contract_sha256": hashlib.sha256(contract_path().read_bytes()).hexdigest(),
        "contract_modes": modes,
        "dispatch_adapter": False,
        "route_node": "checkout" if "checkout" in route_roles else None,
        "checkout_mode": mode,
        "checkout_mode_state": "resolved" if mode else "contract_gap",
        "main_offers": [{"offer_id": o["offer_id"],
                         "price": _price_choice(o, intake)} for o in mains],
        "supplied": supplied,
        "unknown": sorted(unknown),
        "operational_defaults": {k: {"value": v, "reason": reason}
                                 for k, (v, reason) in OPERATIONAL_DEFAULTS.items()},
        "notes": notes,
    }
    mapping["validator"] = _probe_validator(mapping, supplied)
    return mapping


# Fields a caller can fill; listed only so the notes stay truthful.
ADMINISTRABLE = set(SUPPLIED_FIELDS) | set(OPERATIONAL_DEFAULTS)


def _probe_validator(mapping: Dict[str, Any],
                     supplied: Dict[str, Any]) -> Dict[str, Any]:
    """Call the real Skill 79 validator. The binding is proved, not assumed."""
    module = None
    try:
        module = _load_validator()
    except Exception as exc:  # import failure is a recorded fact
        return {"module": CHECKOUT_VALIDATOR, "state": "unavailable",
                "error": str(exc)}
    if module is None or not callable(getattr(module, "validate_request", None)):
        return {"module": CHECKOUT_VALIDATOR, "state": "unavailable",
                "error": "validate_request is absent"}
    request = {"schema_version": mapping.get("contract_schema_version")}
    request.update(supplied)
    for name, (value, _reason) in OPERATIONAL_DEFAULTS.items():
        request[name] = value
    probe: Dict[str, Any] = {"module": CHECKOUT_VALIDATOR, "state": "bound"}
    try:
        module.validate_request(request)
        probe["probe"] = {"result": "accepted"}
    except Exception as exc:  # the contract's own typed validation error
        probe["probe"] = {
            "result": "rejected",
            "error": str(exc),
            "meaning": ("the Skill 79 contract is bound and names the facts this "
                        "launch still does not supply; a rejected probe is "
                        "recorded, never a substituted value"),
        }
    return probe

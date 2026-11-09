"""Checkout rule for check_package (the check_rules seam).

One function, ``violations(manifest, root, skill_root)``, returns every checkout
violation as a named ``AF-LAUNCH-CHECKOUT-*`` string; an empty list passes.

CHK-02  a resolved mode must carry the facts its mode needs
CHK-04  a rejected Skill 79 probe is a blocker, never a pass
CHK-08  the manifest checkout record is compared with checkout-mapping.json and
        re-derived from intake.json + route-graph.json, so an edited and resealed
        record fails
PRD-05  multiple_options cannot reach delivery without native price ids
CHK-12  per-offer realisations are judged by their instance replay
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .. import checkout as checkout_module

# Environment, not evidence: another interpreter or jsonschema wording changes these.
_VOLATILE_VALIDATOR_KEYS = ("interpreter",)
_VOLATILE_PROBE_KEYS = ("error", "meaning")


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def mode_violations(checkout: Dict[str, Any]) -> List[str]:
    """CHK-02: 'resolved' is earned by the mode's required facts, not by the mode name."""
    mode, supplied = checkout.get("checkout_mode"), checkout.get("supplied") or {}
    if mode == "post_selection":
        if not _nonblank(supplied.get("selection_ref")) and not checkout.get("binding_plan"):
            return ["AF-LAUNCH-CHECKOUT-SELECTION: post_selection checkout carries no "
                    "selection_ref and no per-option binding, so the checkout cannot know which "
                    "package the buyer picked or what to charge"]
    elif mode == "combined_single_offer":
        absent = [n for n in ("main_offer_id", "main_price") if not supplied.get(n)]
        if absent:
            return [f"AF-LAUNCH-CHECKOUT-OFFER: combined_single_offer checkout carries no "
                    f"{' and no '.join(absent)}, so there is nothing to charge"]
    return []


def incomplete_violations(manifest: Dict[str, Any], checkout: Dict[str, Any]) -> List[str]:
    """CHK-04: replay the request through the real validator; never trust the recorded probe."""
    request = checkout_module.contract_request(checkout.get("supplied"),
                                               checkout.get("operational_defaults"))
    verdict, detail = checkout_module.replay(request)
    if verdict != "rejected":  # an unavailable validator is named by checks.py
        return []
    missing = checkout_module.missing_facts(request)
    listing = ", ".join(missing) or detail
    if manifest.get("test_only") is True:
        # Offline design-only: allowed, but never silently. The label must be on the record
        # and must name exactly the facts the contract still lacks.
        if _nonblank(checkout.get("checkout_incomplete_label")) \
                and checkout.get("missing_facts") == missing:
            return []
        return [f"AF-LAUNCH-CHECKOUT-INCOMPLETE: the Skill 79 probe rejects this checkout and "
                f"the package carries no checkout_incomplete label naming what is missing: {listing}"]
    return [f"AF-LAUNCH-CHECKOUT-INCOMPLETE: the Skill 79 contract rejects this checkout, so "
            f"delivery is blocked until it supplies: {listing}"]


def _norm(record: Any) -> Any:
    return json.loads(json.dumps(record, sort_keys=True))


def _comparable(record: Dict[str, Any]) -> Dict[str, Any]:
    out = _norm(record)
    validator = out.get("validator")
    if isinstance(validator, dict):
        for key in _VOLATILE_VALIDATOR_KEYS:
            validator.pop(key, None)
        for key in _VOLATILE_PROBE_KEYS:
            (validator.get("probe") or {}).pop(key, None)
    return out


def _differing(a: Dict[str, Any], b: Dict[str, Any]) -> str:
    return ", ".join(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))


def _load(root: Path, path: Any) -> Any:
    target = (root / str(path)).resolve() if path else None
    if target is None or not target.is_file() or not target.is_relative_to(root.resolve()):
        return None  # a missing or unhashed file is already named by check_package
    return json.loads(target.read_text(encoding="utf-8"))


def record_violations(manifest: Dict[str, Any], root: Path) -> List[str]:
    """CHK-08: the manifest's checkout record must equal the mapping file and re-derive from intake."""
    checkout = manifest.get("checkout") or {}
    recorded = _comparable({k: v for k, v in checkout.items()
                            if k not in ("mapping_path", "mapping_sha256")})
    fails: List[str] = []
    try:
        filed = _load(root, checkout.get("mapping_path"))
        if filed is not None and _comparable(filed) != recorded:
            fails.append(
                f"AF-LAUNCH-CHECKOUT-RECORD: the manifest checkout record differs from "
                f"{checkout.get('mapping_path')} in: {_differing(_comparable(filed), recorded)}")
        intake = _load(root, (manifest.get("intake") or {}).get("path"))
        graph = _load(root, (manifest.get("route_graph") or {}).get("path"))
        if intake is None or graph is None:
            return fails
        derived = _comparable(checkout_module.order_form_mapping(
            intake, graph, readback=checkout.get("readback")))
    except Exception as exc:  # a record that cannot be re-derived is not a pass
        return fails + [f"AF-LAUNCH-CHECKOUT-RECORD: the checkout record could not be "
                        f"re-derived from intake.json ({type(exc).__name__}: {exc})"]
    if derived != recorded:
        fails.append("AF-LAUNCH-CHECKOUT-RECORD: the manifest checkout record is not what "
                     f"intake.json and route-graph.json derive; it differs in: "
                     f"{_differing(derived, recorded)}")
    return fails


def native_id_violations(manifest: Dict[str, Any]) -> List[str]:
    """PRD-05: a live multiple_options checkout needs Skill 44 read-back ids on every main price."""
    if manifest.get("journey_mode") != "multiple_options" or manifest.get("test_only") is not False:
        return []
    mains = (manifest.get("checkout") or {}).get("main_offers") or []
    if not mains:
        return ["AF-LAUNCH-CHECKOUT-NATIVE-IDS: multiple_options checkout lists no main offers"]
    return [f"AF-LAUNCH-CHECKOUT-NATIVE-IDS: main offer {entry.get('offer_id')} has no {field}; "
            "multiple_options cannot reach delivery without Skill 44 read-back ids"
            for entry in mains for field in ("native_product_id", "native_price_id")
            if not _nonblank((entry.get("price") or {}).get(field))]


def instance_violations(checkout: Dict[str, Any]) -> List[str]:
    """CHK-12: one request per main price choice, each replayed through the real S79 validator."""
    instances = checkout_module.instances_module()
    if instances is None:
        return ["AF-LAUNCH-CHECKOUT-INSTANCES: the checkout is recorded as per-offer instances "
                "but the module that replays them is not installed"]
    return list(instances.replay_violations(checkout))


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    checkout = manifest.get("checkout") or {}
    if checkout.get("realisation") == "per_offer_instances":
        # The top-level probe has no main_offer_id by design; the instance replay is the verdict.
        fails = instance_violations(checkout)
    else:
        fails = mode_violations(checkout) + incomplete_violations(manifest, checkout)
    return fails + record_violations(manifest, Path(root)) + native_id_violations(manifest)

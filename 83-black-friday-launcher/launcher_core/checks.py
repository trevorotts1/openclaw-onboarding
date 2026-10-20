"""Executable package completeness checks.

Each check returns a list of violations; an empty list is a pass. A check never
asserts a proof class it did not measure, and never repairs anything.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any, Dict, List

from . import launch_plan as launch_plan_module
from . import page_designs
from .constants import (PLACEHOLDER_TOKENS, ROUTE_ROLES, SCHEMA_VERSION,
                        repo_root_for)


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_placeholder_path(value: Any) -> bool:
    """True when a bound path is placeholder-shaped rather than a real binding."""
    if not isinstance(value, str) or not value.strip():
        return True
    lowered = value.strip().lower()
    return any(token in lowered for token in PLACEHOLDER_TOKENS)


def _resolve(root: Path, relative: Any) -> Path:
    return (root / str(relative)).resolve()


def _decided_requirement_violations(manifest: Dict[str, Any], root: Path,
                                    skill_root: Path) -> List[str]:
    """The owner decisions LAUNCH-02b implemented, each checked by name."""
    fails: List[str] = []
    # Cross-tree refs are recorded repository-relative. ``skill_root.parent`` is
    # the repository root only in the onboarding layout; in a deployed tree the
    # skill sits under .claude/skills, so the root must be discovered, or the
    # recorded path is re-based under .claude/skills/.claude/skills and fails.
    repo_root = repo_root_for(skill_root)

    # 4. Verified offer facts only: nothing commercial may be defaulted.
    facts = manifest.get("offer_facts")
    if not isinstance(facts, list) or not facts:
        fails.append("AF-LAUNCH-OFFER-FACTS: the manifest carries no offer facts")
    else:
        for fact in facts:
            label = fact.get("offer_id") or "<unnamed offer>"
            price = fact.get("price") or {}
            if price.get("provenance") != "supplied":
                fails.append(f"AF-LAUNCH-OFFER-DEFAULTED: {label} price provenance "
                             f"is {price.get('provenance')!r}, not 'supplied'")
            amount = price.get("amount_minor")
            if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
                fails.append(f"AF-LAUNCH-OFFER-PRICE: {label} price is {amount!r}; "
                             "unknown is never zero")
            level = fact.get("level") or {}
            if level.get("provenance") not in ("supplied", "unknown"):
                fails.append(f"AF-LAUNCH-OFFER-DEFAULTED: {label} level provenance "
                             f"is {level.get('provenance')!r}; supply it or mark it unknown")
            entitlement = fact.get("entitlement") or {}
            if entitlement.get("provenance") != "attested":
                fails.append(f"AF-LAUNCH-OFFER-DEFAULTED: {label} entitlement "
                             f"provenance is {entitlement.get('provenance')!r}")

    # 1. Entitlement: attested, qualified, and nothing billed or created.
    entitlement = manifest.get("entitlement") or {}
    if entitlement.get("qualifies") is not True:
        fails.append("AF-LAUNCH-ENTITLEMENT-NOT-QUALIFIED: the package carries "
                     "no qualified entitlement attestation")
    if entitlement.get("billing") != "none":
        fails.append("AF-LAUNCH-ENTITLEMENT-BILLING: the build may not bill")
    declaration = entitlement.get("declaration") or {}
    path, digest = declaration.get("path"), declaration.get("sha256")
    target = skill_root / str(path)
    if not path or not target.is_file():
        fails.append(f"AF-LAUNCH-ENTITLEMENT-DECLARATION: {path!r} does not resolve")
    elif _sha256_file(target) != digest:
        fails.append("AF-LAUNCH-ENTITLEMENT-DECLARATION: the carried declaration "
                     "does not match the digest the package recorded")

    # 2. Council: recorded, and structurally incapable of blocking.
    council = manifest.get("council") or {}
    if not council.get("step"):
        fails.append("AF-LAUNCH-COUNCIL: no Council planning step is recorded")
    if council.get("blocks_build") is not False:
        fails.append("AF-LAUNCH-COUNCIL: blocks_build must be false; advice never blocks")
    if council.get("is_permission") is not False:
        fails.append("AF-LAUNCH-COUNCIL: is_permission must be false; advice is never permission")
    if council.get("status") not in ("ready_no_advice", "advice_returned", "not_ready"):
        fails.append(f"AF-LAUNCH-COUNCIL: unknown status {council.get('status')!r}")
    advice_path = council.get("advice_path")
    if not advice_path or not (root / str(advice_path)).is_file():
        fails.append(f"AF-LAUNCH-COUNCIL: advice record {advice_path!r} is missing")
    elif _sha256_file(root / str(advice_path)) != council.get("advice_sha256"):
        fails.append("AF-LAUNCH-COUNCIL: the advice record does not match its digest")

    # 3. Checkout: native, contract-bound, never a dispatch adapter.
    checkout = manifest.get("checkout") or {}
    if checkout.get("dispatch_adapter") is not False:
        fails.append("AF-LAUNCH-CHECKOUT: checkout must never be a dispatch adapter")
    contract = checkout.get("contract")
    contract_target = repo_root / str(contract)
    if not contract or not contract_target.is_file():
        fails.append(f"AF-LAUNCH-CHECKOUT: contract {contract!r} does not resolve")
    elif _sha256_file(contract_target) != checkout.get("contract_sha256"):
        fails.append("AF-LAUNCH-CHECKOUT: the Skill 79 contract does not match its digest")
    if checkout.get("checkout_mode_state") not in ("resolved", "contract_gap"):
        fails.append(f"AF-LAUNCH-CHECKOUT: unknown mode state "
                     f"{checkout.get('checkout_mode_state')!r}")
    validator = (checkout.get("validator") or {})
    validator_state = validator.get("state")
    if validator_state == "bound":
        pass
    elif validator_state == "unavailable" and importlib.util.find_spec(
            "jsonschema") is None:
        # Recorded, not hidden: the S79 validator needs jsonschema, and the
        # dependency package lists it as a 999 blocker.
        pass
    else:
        fails.append(f"AF-LAUNCH-CHECKOUT-VALIDATOR: the Skill 79 validator is "
                     f"{validator_state!r}: {validator.get('error', '')}")
    mapping_path = checkout.get("mapping_path")
    if not mapping_path or not (root / str(mapping_path)).is_file():
        fails.append(f"AF-LAUNCH-CHECKOUT: mapping {mapping_path!r} is missing")
    elif _sha256_file(root / str(mapping_path)) != checkout.get("mapping_sha256"):
        fails.append("AF-LAUNCH-CHECKOUT: the mapping does not match its digest")

    # 6. Cross-sales: present as an offer relationship, teaching never invented.
    cross_sales = manifest.get("cross_sales") or {}
    if cross_sales.get("route_node") is not False:
        fails.append("AF-LAUNCH-CROSS-SALES: cross-sales must never be a route node")
    if (cross_sales.get("teaching") or {}).get("state") != "pending":
        fails.append("AF-LAUNCH-CROSS-SALES: the teaching source is not in hand and "
                     "must be recorded as pending")
    thank_you = next((p for p in (manifest.get("pieces") or [])
                      if p.get("role") == "thank_you"), None)
    if thank_you is None:
        fails.append("AF-LAUNCH-CROSS-SALES: the package carries no thank_you piece "
                     "to surface the relationships on")

    # Cross-tree contract bindings resolve against the repository root.
    for name, ref in (manifest.get("dependencies") or {}).items():
        path, digest = (ref or {}).get("path"), (ref or {}).get("sha256")
        if not path:
            fails.append(f"AF-LAUNCH-DEPENDENCY: {name} names no path")
            continue
        target = repo_root / str(path)
        if not target.is_file():
            fails.append(f"AF-LAUNCH-DEPENDENCY: {name}={path!r} does not resolve")
        elif digest is not None and _sha256_file(target) != digest:
            fails.append(f"AF-LAUNCH-DEPENDENCY: {name}={path!r} does not match its digest")
    return fails


def _launch_plan_violations(manifest: Dict[str, Any], root: Path) -> List[str]:
    """The shared launch plan: calendar law and every planned unit actually delivered."""
    record = manifest.get("launch_plan")
    if record is None:
        return []  # a page-only package predates the shared launch plan
    fails: List[str] = []
    plan_ref = record.get("plan") or {}
    plan_path = plan_ref.get("path")
    target = _resolve(root, plan_path) if plan_path else None
    plan: Dict[str, Any] | None = None
    if not plan_path or target is None or not target.is_file():
        fails.append(f"AF-LAUNCH-PKG-PLAN-MISSING: launch plan {plan_path!r} does not resolve")
    elif _sha256_file(target) != plan_ref.get("sha256"):
        fails.append("AF-LAUNCH-PKG-PLAN-HASH: the launch plan does not match its digest")
    else:
        try:
            plan = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fails.append(f"AF-LAUNCH-PKG-PLAN-MISSING: unreadable launch plan ({exc})")

    if plan is None:
        return fails

    calendar_ref = record.get("calendar") or {}
    calendar_path = calendar_ref.get("path")
    calendar_target = _resolve(root, calendar_path) if calendar_path else None
    if not calendar_path or calendar_target is None or not calendar_target.is_file():
        fails.append(f"AF-LAUNCH-PKG-PLAN-CALENDAR: calendar {calendar_path!r} does not resolve")
    elif _sha256_file(calendar_target) != calendar_ref.get("sha256"):
        fails.append("AF-LAUNCH-PKG-PLAN-CALENDAR: the calendar does not match its digest")
    else:
        try:
            carried = json.loads(calendar_target.read_text(encoding="utf-8"))
            expected = launch_plan_module.black_friday_calendar(plan)
        except (OSError, ValueError) as exc:
            fails.append(f"AF-LAUNCH-PKG-PLAN-CALENDAR: unreadable calendar ({exc})")
        except launch_plan_module.LaunchPlanError as exc:
            fails.append(f"{exc.code}: {exc.detail}")
        else:
            if carried != expected:
                fails.append("AF-LAUNCH-PKG-PLAN-CALENDAR: the carried Black Friday calendar "
                             "is not the plan's calendar")

    completeness = record.get("completeness") or {}
    delivered = {u.get("id"): {"state": u.get("state")}
                 for u in (completeness.get("units") or []) if isinstance(u, dict)}
    try:
        recomputed = launch_plan_module.completeness(plan, delivered)
    except launch_plan_module.LaunchPlanError as exc:
        fails.append(f"{exc.code}: {exc.detail}")
        return fails
    if recomputed["missing"]:
        fails.append("AF-LAUNCH-PKG-PLAN-MISSING: planned item(s) not delivered: "
                     + ", ".join(recomputed["missing"]))
    if completeness.get("planned") != recomputed["planned"]:
        fails.append("AF-LAUNCH-PKG-PLAN-MISSING: the recorded planned units are not "
                     "the plan's units")
    if completeness.get("complete") is not True or completeness.get("percentage") != 100:
        fails.append("AF-LAUNCH-PKG-PLAN-MISSING: the package is not 100% complete")
    if completeness.get("percentage") != recomputed["percentage"]:
        fails.append("AF-LAUNCH-PKG-PLAN-MISSING: the recorded percentage does not match "
                     "the delivered units")
    return fails


def check_package(manifest_path: Path, root: Path,
                  skill_root: Path | None = None,
                  require_designs: bool | None = None) -> List[str]:
    """All package-completeness violations. Empty list means the package holds.

    AF-LAUNCH-PAGE-DESIGNS runs when the package was assembled as a designs-required delivery
    (manifest.designs_required) or when require_designs is True; require_designs=False skips it.
    """
    manifest_path = Path(manifest_path)
    root = Path(root).resolve()
    skill_root = Path(skill_root).resolve() if skill_root else Path(__file__).resolve().parent.parent
    fails: List[str] = []

    try:
        manifest: Dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"AF-LAUNCH-PKG-MANIFEST: unreadable manifest ({exc})"]

    if manifest.get("schema_version") != SCHEMA_VERSION:
        fails.append(f"AF-LAUNCH-PKG-MANIFEST: schema_version is {manifest.get('schema_version')!r}")
    if not manifest.get("test_only"):
        fails.append("AF-LAUNCH-PKG-MANIFEST: test_only must be true for an offline build")

    # Required pieces: every enabled route role, exactly once.
    pieces = manifest.get("pieces") or []
    # A page is its role plus its instance: downsell_1 and downsell_2 are two pages of one role.
    roles = [p.get("role") for p in pieces if not p.get("role_instance")]
    for role in ROUTE_ROLES:
        if role in ("landing", "checkout", "thank_you"):
            if roles.count(role) != 1:
                fails.append(f"AF-LAUNCH-PKG-MISSING-ROLE: {role} appears {roles.count(role)} times")
    for piece in pieces:
        if piece.get("role") not in ROUTE_ROLES:
            fails.append(f"AF-LAUNCH-PKG-MANIFEST: unknown piece role {piece.get('role')!r}")
    slots = [(p.get("role"), p.get("role_instance")) for p in pieces]
    if len(set(slots)) != len(slots):
        fails.append("AF-LAUNCH-PKG-MANIFEST: a route role is delivered more than once")

    for ref_name in ("intake", "route_graph"):
        ref = manifest.get(ref_name) or {}
        path = ref.get("path")
        if not path:
            fails.append(f"AF-LAUNCH-PKG-MANIFEST: {ref_name}.path missing")
            continue
        target = _resolve(root, path)
        if not target.is_file():
            fails.append(f"AF-LAUNCH-PKG-PATH-UNRESOLVED: {ref_name} path {path!r} does not resolve")
            continue
        if _sha256_file(target) != ref.get("sha256"):
            fails.append(f"AF-LAUNCH-PKG-HASH: {ref_name} hash does not match {path!r}")

    # Config bindings: must exist, must be real, never placeholder-shaped.
    for name, value in (manifest.get("bindings") or {}).items():
        if is_placeholder_path(value):
            fails.append(f"AF-LAUNCH-PKG-PLACEHOLDER: binding {name}={value!r} is placeholder-shaped")
            continue
        if not (skill_root / str(value)).exists():
            fails.append(f"AF-LAUNCH-PKG-PATH-UNRESOLVED: binding {name}={value!r} does not resolve")

    # Artifacts: present, non-placeholder, hash-matching.
    for piece in pieces:
        role = piece.get("role")
        artifacts = piece.get("artifacts") or []
        if not artifacts:
            fails.append(f"AF-LAUNCH-PKG-MISSING: {role} delivered no artifact")
        if piece.get("status") == "blocked":
            fails.append(f"AF-LAUNCH-PKG-BLOCKED: {role} is blocked")
        for art in artifacts:
            path, digest = art.get("path"), art.get("sha256")
            if is_placeholder_path(path):
                fails.append(f"AF-LAUNCH-PKG-PLACEHOLDER: {role} artifact path {path!r} is placeholder-shaped")
                continue
            target = _resolve(root, path)
            if not target.is_file():
                fails.append(f"AF-LAUNCH-PKG-ARTIFACT-MISSING: {role} artifact {path!r} does not resolve")
                continue
            actual = _sha256_file(target)
            if actual != digest:
                fails.append(f"AF-LAUNCH-PKG-HASH: {role} artifact {path!r} sha256 {actual} != {digest}")

    # Every page ships its full set of labeled desktop and mobile wireframes and mockups.
    needed = manifest.get("designs_required") is True if require_designs is None else require_designs
    if needed:
        fails.extend(page_designs.design_violations(manifest, root))

    # Decided-requirement records: every commercial fact is supplied or unknown,
    # the entitlement is attested, Council advice never blocks, checkout is native.
    fails.extend(_decided_requirement_violations(manifest, root, skill_root))

    # Shared launch plan: the Black Friday calendar and every planned unit delivered.
    fails.extend(_launch_plan_violations(manifest, root))

    # Receipt: present and self-consistent.
    receipt_path = root / "receipt.json"
    if not receipt_path.is_file():
        fails.append("AF-LAUNCH-PKG-RECEIPT: receipt.json is missing")
    else:
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            fails.append(f"AF-LAUNCH-PKG-RECEIPT: unreadable receipt ({exc})")
        else:
            if receipt.get("manifest", {}).get("sha256") != _sha256_file(manifest_path):
                fails.append("AF-LAUNCH-PKG-RECEIPT: receipt does not seal this manifest")
            if receipt.get("live_effects") != "none":
                fails.append("AF-LAUNCH-PKG-RECEIPT: receipt claims live effects in an offline build")
            state = (receipt.get("receipt_evidence") or {}).get("state")
            if state not in ("verified", "absent"):
                fails.append(f"AF-LAUNCH-PKG-RECEIPT: Skill 49 receipt store state {state!r}")
            if manifest.get("launch_plan") is not None:
                receipt_plan = receipt.get("launch_plan") or {}
                manifest_plan = manifest.get("launch_plan") or {}
                for name in ("plan", "calendar"):
                    sealed = (receipt_plan.get(name) or {}).get("sha256")
                    carried = (manifest_plan.get(name) or {}).get("sha256")
                    if not sealed or sealed != carried:
                        fails.append(f"AF-LAUNCH-PKG-PLAN-RECEIPT: receipt does not seal "
                                     f"the launch {name}")
                receipt_completeness = receipt_plan.get("completeness") or {}
                if receipt_completeness.get("missing") != [] or \
                        receipt_completeness.get("complete") is not True:
                    fails.append("AF-LAUNCH-PKG-PLAN-MISSING: the receipt records an "
                                 "incomplete launch")
                if receipt_completeness.get("percentage") != 100:
                    fails.append("AF-LAUNCH-PKG-PLAN-MISSING: the receipt's launch "
                                 "percentage is not 100")

    return fails

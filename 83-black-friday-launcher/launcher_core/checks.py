"""Executable package completeness checks.

Each check returns a list of violations; an empty list is a pass. A check never
asserts a proof class it did not measure, and never repairs anything.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

from . import launch_plan as launch_plan_module
from . import page_designs
from .package import (PROOF_BY_STATUS, PROOF_KEYS, RECEIPT_SCHEMA_VERSION,
                      RECEIPT_TYPE)
from .constants import (CHECKOUT_SKILL_SLUG, CHECKOUT_VALIDATOR_REF,
                        PLACEHOLDER_TOKENS, ROUTE_ROLES, SCHEMA_VERSION,
                        repo_root_for, skill_path)

_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")

# The typed per-unit receipt: every row is bound to the launch identity, the
# approved plan hash, the request it answers, its own artifacts and the lane
# that validated it. Proof classes are separate booleans so a draft can never
# be read as a live verification.
RECEIPT_UNIT_KEYS = ("unit_id", "unit_type", "tenant_id", "location_id", "launch_id",
                     "revision", "approved_plan_hash", "request", "artifacts",
                     "lane_validation", "proof", "status")
RECEIPT_PROOF_KEYS = PROOF_KEYS
RECEIPT_UNIT_TYPES = ("page", "email", "text", "automation", "conversation_ai")
DRAFT_UNIT_TYPES = ("email", "text", "automation")
IDENTITY_KEYS = ("tenant_id", "location_id", "launch_id", "revision")


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


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def checkout_mode_violations(checkout: Dict[str, Any]) -> List[str]:
    """Production delivery requires a resolved Skill 79 checkout mode.

    ``folded_levels`` has no mode in the Skill 79 contract, so its mapping
    records ``checkout_mode=None`` with ``checkout_mode_state="contract_gap"``.
    That is a blocker, never a pass: a package whose order form has no mode has
    no deliverable checkout, and "builds green offline" is not a deployable
    three-level checkout. The contract is not invented here — the mode stays
    unresolved until Skill 79 names one.
    """
    mode = checkout.get("checkout_mode")
    state = checkout.get("checkout_mode_state")
    if state == "resolved" and _nonempty_str(mode):
        return []
    if state == "contract_gap":
        return [f"AF-LAUNCH-CHECKOUT-MODE: checkout_mode is {mode!r} "
                f"(state {state!r}); the Skill 79 contract names no mode for this "
                "launch shape, so production delivery is blocked until it resolves"]
    return [f"AF-LAUNCH-CHECKOUT-MODE: checkout_mode is {mode!r} "
            f"(state {state!r}) is not a resolved mode; production delivery is "
            "blocked until a resolved, non-empty checkout_mode is recorded"]


def _load_checkout_validator():
    """The real Skill 79 cross-field validator, or None when it is not installed."""
    path = skill_path(CHECKOUT_SKILL_SLUG, CHECKOUT_VALIDATOR_REF)
    if not path.is_file():
        return None
    spec = importlib.util.spec_from_file_location("launcher_s79_validate_checkout", path)
    if spec is None or spec.loader is None:
        return None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SHAPE_MARKERS = ("Additional properties are not allowed", "was unexpected",
                  "is not of type", "is not one of", "is not a", "is too short",
                  "is too long", "does not match", "is less than", "is greater than")


def _replay_checkout(request: Dict[str, Any]) -> Tuple[str, str]:
    """Re-run the canonical checkout request through the real S79 validator.

    Returns ``("accepted" | "rejected" | "shape" | "unavailable", detail)``.
    ``rejected`` means the envelope is well formed and the launch is missing
    required facts; ``shape`` means the envelope itself is malformed — which is
    the producer's defect and must be named, not masked as a missing fact.
    """
    try:
        module = _load_checkout_validator()
    except Exception as exc:  # import failure is a recorded fact
        return "unavailable", f"{exc} (replay interpreter {sys.executable})"
    if module is None or not callable(getattr(module, "validate_request", None)):
        return "unavailable", f"validate_request is absent (replay interpreter {sys.executable})"
    try:
        module.validate_request(request)
    except Exception as exc:  # the contract's own typed validation error
        message = str(exc)
        if any(marker in message for marker in _SHAPE_MARKERS):
            return "shape", message
        return "rejected", message
    return "accepted", ""


def _checkout_probe_violations(checkout: Dict[str, Any],
                               validator: Dict[str, Any]) -> List[str]:
    """The consumer side of the L05 probe: a recorded verdict must be earned.

    The probe is only evidence when its request is the canonical request. This
    replay rebuilds that request from the manifest's own ``supplied`` record
    (no document-level field smuggled into the inner envelope), so an
    accepted/rejected verdict that the contract does not reproduce fails.
    """
    probe = validator.get("probe") or {}
    result = probe.get("result")
    if result not in ("accepted", "rejected"):
        return [f"AF-LAUNCH-CHECKOUT-VALIDATOR: the S79 probe recorded no verdict "
                f"({result!r}); a binding is proved, never assumed"]
    request = dict(checkout.get("supplied") or {})
    defaults = checkout.get("operational_defaults") or {}
    for name, entry in defaults.items():
        if isinstance(entry, dict) and "value" in entry:
            request[name] = entry["value"]
    if "schema_version" in request:
        return ["AF-LAUNCH-CHECKOUT-VALIDATOR: schema_version is a document-level field; "
                "the inner checkout_request envelope must not carry it"]
    outcome, detail = _replay_checkout(request)
    if outcome == "unavailable":
        # The probe's "bound" verdict is only earned by replay. A validator that
        # cannot load now leaves the binding unproved, so the build fails: an
        # interpreter without jsonschema must never print PASS.
        return [f"AF-LAUNCH-CHECKOUT-VALIDATOR: the S79 validator is unavailable "
                f"at replay time ({detail}); the probe was recorded under "
                f"{validator.get('interpreter') or 'an unrecorded interpreter'}"]
    if outcome == "shape":
        return [f"AF-LAUNCH-CHECKOUT-VALIDATOR: the S79 request envelope is malformed "
                f"({detail})"]
    if outcome == "accepted" and result != "accepted":
        return ["AF-LAUNCH-CHECKOUT-VALIDATOR: the canonical request validates, but the "
                "probe recorded 'rejected' — the verdict is not the contract's"]
    if outcome == "rejected" and result != "rejected":
        return ["AF-LAUNCH-CHECKOUT-VALIDATOR: the canonical request still lacks required "
                "facts, but the probe recorded 'accepted'"]
    probe_error = str(probe.get("error") or "")
    if result == "rejected" and any(marker in probe_error for marker in _SHAPE_MARKERS) \
            and outcome == "accepted":
        return [f"AF-LAUNCH-CHECKOUT-VALIDATOR: the probe rejected a malformed envelope "
                f"({probe_error})"]
    return []


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
    fails.extend(checkout_mode_violations(checkout))
    validator = (checkout.get("validator") or {})
    validator_state = validator.get("state")
    if validator_state == "bound":
        fails.extend(_checkout_probe_violations(checkout, validator))
    else:
        # An unbound validator is a verification failure, never a recorded
        # exception: jsonschema is the Launcher's own runtime requirement
        # (requirements.txt), so the interpreter that runs this check must be
        # able to load the Skill 79 validator.
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
            if target.stat().st_size == 0:
                # A zero-byte artifact is never delivered proof: it exists, it says nothing.
                fails.append(f"AF-LAUNCH-PKG-ARTIFACT-EMPTY: {role} artifact {path!r} is zero bytes")
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

    # Receipt: typed, bound to this launch and revalidated against its artifacts.
    fails.extend(_receipt_violations(manifest, manifest_path, root))

    return fails


def _artifact_violations(label: str, artifacts: Any, root: Path) -> List[str]:
    """Every artifact must exist, be non-empty and match its declared hash and size."""
    fails: List[str] = []
    if not isinstance(artifacts, list) or not artifacts:
        return [f"AF-LAUNCH-PKG-RECEIPT-ARTIFACT: {label} delivered no artifact to prove"]
    for index, art in enumerate(artifacts):
        if not isinstance(art, dict):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-ARTIFACT: {label} artifacts[{index}] is not an object")
            continue
        path, digest, size = art.get("path"), art.get("sha256"), art.get("size")
        if not _nonempty_str(path):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-ARTIFACT: {label} artifacts[{index}].path is missing")
            continue
        if not isinstance(digest, str) or not _SHA256_RE.match(digest):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-ARTIFACT: {label} artifacts[{index}].sha256 "
                         f"is not 64 lowercase hex")
            continue
        target = _resolve(root, path)
        if Path(path).is_absolute() or not target.is_relative_to(root):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-ARTIFACT: {label} artifact {path!r} escapes the run")
            continue
        if not target.is_file():
            fails.append(f"AF-LAUNCH-PKG-ARTIFACT-MISSING: {label} artifact {path!r} does not resolve")
            continue
        actual_size = target.stat().st_size
        if actual_size == 0:
            fails.append(f"AF-LAUNCH-PKG-ARTIFACT-EMPTY: {label} artifact {path!r} is zero bytes")
            continue
        if _sha256_file(target) != digest:
            fails.append(f"AF-LAUNCH-PKG-HASH: {label} artifact {path!r} does not match its hash")
            continue
        if not isinstance(size, int) or isinstance(size, bool) or size != actual_size:
            fails.append(f"AF-LAUNCH-PKG-ARTIFACT-SIZE: {label} artifact {path!r} is "
                         f"{actual_size} bytes, receipt says {size!r}")
    return fails


def _unit_receipt_violations(row: Any, index: int, manifest: Dict[str, Any],
                             approved: Any, plan_sha: Any, root: Path,
                             live_effects: Any) -> List[str]:
    """One typed per-unit receipt: identity, request echo, artifacts, lane, proof."""
    label = f"unit[{index}]"
    if not isinstance(row, dict):
        return [f"AF-LAUNCH-PKG-RECEIPT-UNITS: {label} is not an object"]
    missing = [key for key in RECEIPT_UNIT_KEYS if key not in row]
    if missing:
        return [f"AF-LAUNCH-PKG-RECEIPT-UNITS: {label} lacks {', '.join(missing)}"]
    unit_id = row.get("unit_id")
    label = f"unit {unit_id!r}"
    fails: List[str] = []
    for key in IDENTITY_KEYS:
        if row.get(key) != manifest.get(key):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-BINDING: {label} {key} {row.get(key)!r} "
                         f"is not the manifest's {manifest.get(key)!r}")
    if not approved or row.get("approved_plan_hash") != approved:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-BINDING: {label} is not bound to the "
                     f"approved plan hash")
    if row.get("unit_type") not in RECEIPT_UNIT_TYPES:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-UNITS: {label} has unknown unit_type "
                     f"{row.get('unit_type')!r}")

    request = row.get("request")
    if not isinstance(request, dict):
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-REQUEST: {label} carries no request echo")
    else:
        echo = request.get("plan_sha256")
        if plan_sha is not None:
            if not _nonempty_str(echo):
                fails.append(f"AF-LAUNCH-PKG-RECEIPT-REQUEST: {label} carries no plan echo")
            elif echo != plan_sha:
                fails.append(f"AF-LAUNCH-PKG-RECEIPT-REQUEST: {label} echoes plan "
                             f"{echo!r}, not the sealed plan")
        elif not _nonempty_str(echo) and not (
                _nonempty_str(request.get("request_id"))
                and _nonempty_str(request.get("input_hash"))):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-REQUEST: {label} carries no request echo")
        if row.get("unit_type") == "page" and row.get("delivery") != "declared":
            for key in ("request_id", "input_hash"):
                if not _nonempty_str(request.get(key)):
                    fails.append(f"AF-LAUNCH-PKG-RECEIPT-REQUEST: {label} carries no "
                                 f"{key} echo for the page request")

    fails.extend(_artifact_violations(label, row.get("artifacts"), root))

    lane = row.get("lane_validation")
    if not isinstance(lane, dict) or not _nonempty_str(lane.get("lane")) \
            or not _nonempty_str(lane.get("contract")) or lane.get("state") != "passed":
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-LANE: {label} carries no passed lane validation")

    proof = row.get("proof")
    if not isinstance(proof, dict) or any(key not in proof for key in RECEIPT_PROOF_KEYS):
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-PROOF: {label} does not carry "
                     f"{', '.join(RECEIPT_PROOF_KEYS)}")
    elif not all(isinstance(proof[key], bool) for key in RECEIPT_PROOF_KEYS):
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-PROOF: {label} proof classes must be booleans")
    else:
        expected = PROOF_BY_STATUS.get(row.get("status"))
        if expected is None:
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-PROOF: {label} has unknown status "
                         f"{row.get('status')!r}")
        elif tuple(proof[key] for key in RECEIPT_PROOF_KEYS) != expected:
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-PROOF: {label} claims "
                         f"{tuple(proof[key] for key in RECEIPT_PROOF_KEYS)}, "
                         f"status {row.get('status')!r} proves {expected}")
        if proof.get("live_verified") is True and live_effects == "none":
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-LIVE: {label} claims live verification "
                         f"in a package with no live effects")

    if row.get("unit_type") in DRAFT_UNIT_TYPES and row.get("draft_only") is not True:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-DRAFT: {label} is {row.get('unit_type')} but "
                     f"is not recorded draft_only")
    return fails


def _receipt_violations(manifest: Dict[str, Any], manifest_path: Path,
                        root: Path) -> List[str]:
    """Revalidate the receipt and every typed per-unit receipt against the artifacts."""
    receipt_path = root / "receipt.json"
    if not receipt_path.is_file():
        return ["AF-LAUNCH-PKG-RECEIPT: receipt.json is missing"]
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"AF-LAUNCH-PKG-RECEIPT: unreadable receipt ({exc})"]
    if not isinstance(receipt, dict):
        return ["AF-LAUNCH-PKG-RECEIPT: the receipt must be an object"]

    fails: List[str] = []
    if (receipt.get("manifest") or {}).get("sha256") != _sha256_file(manifest_path):
        fails.append("AF-LAUNCH-PKG-RECEIPT: receipt does not seal this manifest")
    if receipt.get("live_effects") != "none":
        fails.append("AF-LAUNCH-PKG-RECEIPT: receipt claims live effects in an offline build")
    evidence = receipt.get("receipt_evidence") or {}
    if evidence.get("state") not in ("verified", "absent"):
        fails.append(f"AF-LAUNCH-PKG-RECEIPT: Skill 49 receipt store state "
                     f"{evidence.get('state')!r}")

    if receipt.get("schema_version") != RECEIPT_SCHEMA_VERSION:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-SCHEMA: receipt schema_version is "
                     f"{receipt.get('schema_version')!r}, not {RECEIPT_SCHEMA_VERSION!r}")
    if receipt.get("receipt_type") != RECEIPT_TYPE:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT-SCHEMA: receipt_type is "
                     f"{receipt.get('receipt_type')!r}, not {RECEIPT_TYPE!r}")

    for key in IDENTITY_KEYS:
        if receipt.get(key) != manifest.get(key):
            fails.append(f"AF-LAUNCH-PKG-RECEIPT-BINDING: receipt {key} "
                         f"{receipt.get(key)!r} is not the manifest's {manifest.get(key)!r}")
    approved = receipt.get("approved_plan_hash")
    if not isinstance(approved, str) or not _SHA256_RE.match(approved):
        fails.append("AF-LAUNCH-PKG-RECEIPT-BINDING: approved_plan_hash is not a sha256")
    elif approved != manifest.get("approved_plan_hash"):
        fails.append("AF-LAUNCH-PKG-RECEIPT-BINDING: approved_plan_hash is not the "
                     "manifest's approved plan hash")

    lanes = receipt.get("lane_validations")
    if not isinstance(lanes, list) or not lanes:
        fails.append("AF-LAUNCH-PKG-RECEIPT-LANE: the receipt records no lane validations")
    else:
        l04 = [lane for lane in lanes if isinstance(lane, dict) and lane.get("lane") == "L04"]
        if not l04 or l04[0].get("state") != "passed":
            fails.append("AF-LAUNCH-PKG-RECEIPT-LANE: the L04 package validation is not "
                         "recorded as passed")
        for lane in lanes:
            if not isinstance(lane, dict) or lane.get("state") not in (
                    "passed", "recorded", "not_applicable"):
                fails.append(f"AF-LAUNCH-PKG-RECEIPT-LANE: lane validation {lane!r} has "
                             f"no recognized state")

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

    manifest_plan = manifest.get("launch_plan") or {}
    plan_sha = (manifest_plan.get("plan") or {}).get("sha256")
    plan_ref_path = (manifest_plan.get("plan") or {}).get("path")
    units = receipt.get("units")
    if not isinstance(units, list) or not units:
        fails.append("AF-LAUNCH-PKG-RECEIPT-UNITS: the receipt carries no typed "
                     "per-unit receipts")
        return fails

    seen: List[str] = []
    plan_artifact = _resolve(root, plan_ref_path) if plan_ref_path else None
    for index, row in enumerate(units):
        fails.extend(_unit_receipt_violations(row, index, manifest, approved, plan_sha,
                                              root, receipt.get("live_effects")))
        if isinstance(row, dict) and _nonempty_str(row.get("unit_id")):
            if row["unit_id"] in seen:
                fails.append(f"AF-LAUNCH-PKG-RECEIPT-UNITS: unit {row['unit_id']!r} carries "
                             f"more than one receipt")
            seen.append(row["unit_id"])
            if plan_artifact is not None:
                for art in row.get("artifacts") or []:
                    if not isinstance(art, dict):
                        continue
                    try:
                        target = _resolve(root, art.get("path"))
                    except (TypeError, ValueError):
                        continue
                    if target == plan_artifact:
                        fails.append(
                            "AF-LAUNCH-PKG-RECEIPT-ARTIFACT: "
                            f"unit {row['unit_id']!r} points at the sealed launch plan; "
                            "planning evidence stays PLANNED and is never delivery proof")
                        break
            if row.get("unit_type") in ("email", "text", "automation", "conversation_ai"):
                lane = (row.get("lane_validation") or {}).get("lane")
                if lane == "L04":
                    fails.append(
                        "AF-LAUNCH-PKG-RECEIPT-LANE: "
                        f"unit {row['unit_id']!r} is validated by L04 itself; a lane the "
                        "launcher does not own must validate its own delivery")

    if manifest_plan and plan_sha:
        plan_ref = manifest_plan.get("plan") or {}
        target = _resolve(root, plan_ref.get("path")) if plan_ref.get("path") else None
        if target is None or not target.is_file():
            fails.append("AF-LAUNCH-PKG-RECEIPT-UNITS: the sealed launch plan does not resolve")
        else:
            try:
                planned = {unit["id"] for unit in launch_plan_module.planned_units(
                    json.loads(target.read_text(encoding="utf-8")))}
            except (OSError, ValueError, launch_plan_module.LaunchPlanError) as exc:
                fails.append(f"AF-LAUNCH-PKG-RECEIPT-UNITS: the plan cannot be re-expanded "
                             f"({exc})")
            else:
                for unit_id in sorted(planned - set(seen)):
                    fails.append(f"AF-LAUNCH-PKG-RECEIPT-UNITS: planned unit {unit_id!r} "
                                 f"carries no typed receipt")
                for unit_id in sorted(set(seen) - planned):
                    fails.append(f"AF-LAUNCH-PKG-RECEIPT-UNITS: receipt unit {unit_id!r} "
                                 f"is not in the sealed plan")
    return fails


def verify_package_receipt(run_dir: Path, skill_root: Path | None = None) -> Dict[str, Any]:
    """Reopen a finished run and revalidate the same receipt/artifact contract.

    Recovery entry point (L03's progress reader, L12's producers): a unit is
    ``verified`` only when its artifacts exist, are non-empty and hash-match the
    receipt. File existence alone is never evidence, so no row is ever promoted
    to done by presence.
    """
    run_dir = Path(run_dir).resolve()
    receipt_path = run_dir / "receipt.json"
    manifest_path = run_dir / "package-manifest.json"
    report: Dict[str, Any] = {
        "state": "absent",
        "receipt": str(receipt_path),
        "manifest": str(manifest_path),
        "violations": [],
        "artifacts_checked": 0,
        "units": {},
    }
    if not receipt_path.is_file():
        report["violations"].append("AF-LAUNCH-PKG-RECEIPT: receipt.json is missing")
        return report
    report["state"] = "failed"
    if not manifest_path.is_file():
        report["violations"].append("AF-LAUNCH-PKG-MANIFEST: package-manifest.json is missing")
        return report

    fails = check_package(manifest_path, run_dir, skill_root=skill_root)
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        fails.append(f"AF-LAUNCH-PKG-RECEIPT: unreadable receipt ({exc})")
        report["violations"] = fails
        return report

    checked = 0
    units: Dict[str, str] = {}
    for row in receipt.get("units") or []:
        if not isinstance(row, dict) or not _nonempty_str(row.get("unit_id")):
            continue
        unit_fails: List[str] = []
        for art in row.get("artifacts") or []:
            path = (art or {}).get("path") if isinstance(art, dict) else None
            target = _resolve(run_dir, path) if _nonempty_str(path) else None
            checked += 1
            if target is None or not target.is_file():
                unit_fails.append(f"{row['unit_id']}: artifact {path!r} is missing")
                continue
            actual_size = target.stat().st_size
            if actual_size == 0:
                unit_fails.append(f"{row['unit_id']}: artifact {path!r} is zero bytes")
                continue
            if _sha256_file(target) != (art or {}).get("sha256"):
                unit_fails.append(f"{row['unit_id']}: artifact {path!r} does not match its hash")
                continue
            if (art or {}).get("size") != actual_size:
                unit_fails.append(f"{row['unit_id']}: artifact {path!r} size drifted")
        units[row["unit_id"]] = "failed" if unit_fails else "verified"
        fails.extend(unit_fails)

    report["artifacts_checked"] = checked
    report["violations"] = fails
    report["units"] = units
    if not fails and units and all(state == "verified" for state in units.values()):
        report["state"] = "verified"
    return report

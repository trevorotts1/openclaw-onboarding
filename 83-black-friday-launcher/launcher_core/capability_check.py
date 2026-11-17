"""F22: check the real current capabilities early, and FAIL CLOSED.

Before expensive design work and before anyone is told the launch is ready, this module
asks whether the selected journey, billing type, native checkout family, output
destination, installed runtime, and (when selected) the conversational/workflow
surfaces actually exist and map onto this launch. A capability that cannot be PROVEN
is never treated as satisfied:

  * ``proven``      the real contract/validator/file/probe answered for this launch;
  * ``unproven``    the check ran and could not prove it (missing fact, missing file,
                    validator unavailable, contradicting observation);
  * ``not_required`` the approved feature set did not select it.

``required`` is derived from the approved feature set, not from whatever happens to be
installed: a live sale needs its billing type and the native checkout validator; a
requested Conversation AI needs Skill 38's contract, Skill 29's runtime connection and
exactly one responder; a workflow build needs a real authorization mode. Any required
capability that is not proven blocks — the caller refuses, by name.

folded_levels is reported from the actual per-offer instance computation already
implemented in both repositories; the obsolete "no checkout mode" claim is not
reintroduced.

Stdlib only. No network, no model, no secret. Deterministic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import checkout as checkout_module
from .constants import (
    REPO_ROOT,
    SkillResolutionError,
    resolve_skill_dir,
    skill_path,
)

RECORD_TYPE = "launcher.capability-check.v1"
RECORD_REL = "capability-check.json"

# Every capability this launch can depend on.
CAPABILITIES = (
    "journey_mapping",
    "billing_type",
    "native_checkout_family",
    "output_destination",
    "installed_runtime",
    "conversational_workflows",
    "workflow_authorization",
)

# Capabilities proved from the files in this tree: a design-only run can prove them.
LOCAL_CAPABILITIES = ("output_destination", "installed_runtime", "journey_mapping")

# Skill 36's authorization modes. OAuth is the documented official MCP path; the location
# PIT is the REST path. A PIT sent to an MCP endpoint is an UNVERIFIED compatibility mode.
AUTH_MODE_OFFICIAL_MCP_OAUTH = "official_mcp_oauth"
AUTH_MODE_PIT_REST = "pit_rest"
AUTH_MODES_ALLOWED = (AUTH_MODE_OFFICIAL_MCP_OAUTH, AUTH_MODE_PIT_REST)
AUTH_MODE_COMMUNITY_MCP = "community_mcp"
AUTH_MODE_OFFICIAL_MCP_PIT = "official_mcp_pit"

# The declared support Skill 38 requires of Skill 29, and Skill 41's twelve points.
SKILL29_SUPPORT = ("05", "10", "19")
TWELVE_POINTS = 12

# Files that must exist for the installed runtime to be the one this launch needs.
RUNTIME_REFS = (
    ("signature-funnel", "structure/page_types.json"),
    ("signature-funnel", "scripts/page_set.py"),
    ("blackceo-signature-page", "scripts/stage_gate.py"),
    ("signature-order-form", "references/checkout.schema.json"),
    ("signature-order-form", "scripts/validate_checkout.py"),
    ("signature-thank-you", "scripts/validate_thank_you.py"),
)
CONVERSATIONAL_REFS = (
    ("conversational-ai-system", "launch/interactive-owner-contract.md"),
    ("conversational-ai-system", "tools/playbook_engine.py"),
    ("conversational-ai-system", "scripts/qc-trinity-registry.sh"),
)

SELLING_ROLES = ("main", "bump", "upsell_1", "downsell_1", "upsell_2")
WRITE_TARGETS = ("local_only", "approved_test_location")


class CapabilityError(Exception):
    """A required capability could not be proved. Carries a stable code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _row(state: str, required: bool, evidence: Any, detail: str,
         client_message: str = "", next_step: str = "") -> Dict[str, Any]:
    return {"state": state, "required": required, "evidence": evidence, "detail": detail,
            "client_message": client_message, "next_step": next_step}


def _proof_journey(normalized: Mapping[str, Any],
                   route: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """The real Skill 79 mapping: mode resolution plus the per-offer instance record.

    One main offer is proven by running the real mapping probe (the Skill 79 contract is
    loaded and the launch's own fields are bound). Several main offers are proven by the
    per-offer instance realisation itself (``checkout_instances``: one native
    ``combined_single_offer`` order form per price choice — the implemented folded_levels
    mapping in both repositories), never by the obsolete "no checkout mode" claim. The
    instance BUILD runs inside the pinned dispatch path, so this probe proves the
    realisation is installed and maps the journey, not that a paid form was placed.
    """
    graph = route if isinstance(route, Mapping) else {"nodes": []}
    journey = normalized.get("journey_mode")
    mains = [o for o in normalized.get("offers") or [] if o.get("role") == "main"]
    mode = checkout_module.MODE_BY_JOURNEY.get(journey)
    try:
        contract = checkout_module.load_contract()
        modes = checkout_module.checkout_modes(contract)
        contract_sha = __import__("hashlib").sha256(
            checkout_module.contract_path().read_bytes()).hexdigest()
    except Exception as exc:  # noqa: BLE001 — an unreadable contract is unproven
        return _row("unproven", True, {"error": type(exc).__name__},
                    f"the Skill 79 checkout contract cannot be read ({type(exc).__name__}: {exc})",
                    "The native checkout contract is not installed on this machine.",
                    "Install the checkout skill, then retry.")
    if mode is None:
        return _row("unproven", True, {"journey_mode": journey, "modes": list(modes)},
                    f"journey_mode {journey!r} resolves to no Skill 79 checkout mode",
                    "The checkout for this offer shape is not mapped yet.",
                    "Use a single offer, or wait for the contract to name this shape.")
    if mode not in modes:
        return _row("unproven", True, {"checkout_mode": mode, "contract_modes": list(modes)},
                    f"the resolved mode {mode!r} is not one the contract declares",
                    "The native order form family does not declare this mapping.",
                    "Re-check the checkout contract version.")
    if len(mains) > 1:
        module = checkout_module.instances_module()
        if module is None:
            return _row("unproven", True,
                        {"checkout_mode": mode, "mains": len(mains),
                         "instances_module": None},
                        f"{len(mains)} main offers need one native order form per price choice, "
                        "and launcher_core/checkout_instances.py is not installed",
                        "The several-price order form is not proven for this launch.",
                        "Restore the per-offer checkout instances before building.")
        realisation = getattr(module, "MODE", None)
        missing = [name for name in ("build", "record")
                   if not callable(getattr(module, name, None))]
        if realisation != mode or missing:
            return _row("unproven", True,
                        {"checkout_mode": mode, "instances_mode": realisation,
                         "missing": missing},
                        f"the per-offer instance module is {realisation!r} and lacks {missing}; "
                        f"it must realise {mode!r}",
                        "The several-price order form is not proven for this launch.",
                        "Restore the per-offer checkout instances before building.")
        return _row("proven", True,
                    {"checkout_mode": mode, "realisation": "per_offer_instances",
                     "instances_module": "launcher_core/checkout_instances.py",
                     "contract": checkout_module.contract_ref(),
                     "contract_sha256": contract_sha, "modes": list(modes),
                     "mains": len(mains)},
                    f"journey_mode {journey!r} maps to {mode!r} through per-offer checkout "
                    f"instances ({len(mains)} main price choices)")
    try:
        mapping = checkout_module.order_form_mapping(dict(normalized), dict(graph))
    except Exception as exc:  # noqa: BLE001 — a failed probe is unproven, never a pass
        return _row("unproven", True, {"error": type(exc).__name__},
                    f"the Skill 79 mapping refused to run ({type(exc).__name__}: {exc})",
                    "The checkout mapping could not be read for this launch.",
                    "Check the native checkout contract is installed, then retry.")
    if mapping.get("checkout_mode") is None:
        return _row("unproven", True,
                    {"checkout_mode": None, "mode_state": mapping.get("checkout_mode_state")},
                    f"journey_mode {journey!r} resolved to no checkout mode in the mapping",
                    "The checkout for this offer shape is not mapped yet.",
                    "Use a single offer, or wait for the contract to name this shape.")
    return _row("proven", True,
                {"checkout_mode": mapping.get("checkout_mode"),
                 "realisation": mapping.get("realisation"),
                 "mode_state": mapping.get("checkout_mode_state"),
                 "contract": mapping.get("contract"),
                 "contract_sha256": mapping.get("contract_sha256")},
                f"journey_mode {journey!r} maps to {mapping.get('checkout_mode')!r} "
                f"({mapping.get('realisation')})")


def _proof_billing(normalized: Mapping[str, Any]) -> Dict[str, Any]:
    """Every selling offer's billing type, from the answers-bound canonical price."""
    missing: List[str] = []
    seen: Dict[str, str] = {}
    for offer in normalized.get("offers") or []:
        if offer.get("role") not in SELLING_ROLES:
            continue
        canon = (offer.get("canonical") or {}).get("prices") or [{}]
        value = canon[0].get("billing_type") if isinstance(canon[0], Mapping) else None
        if not _nonempty(value):
            value = (offer.get("checkout") or {}).get("billing_type")
        if _nonempty(value):
            seen[str(offer.get("offer_id"))] = str(value)
        else:
            missing.append(str(offer.get("offer_id")))
    if missing:
        return _row("unproven", False, {"missing": missing, "billing_types": seen},
                    f"offer(s) {missing} record no billing type, so the native order form's "
                    "billing cannot be proved",
                    "Some prices have no confirmed billing type.",
                    "Confirm how each of those prices is billed (one payment, weekly, monthly, quarterly or yearly) in the client's answers.")
    return _row("proven", False, {"billing_types": seen},
                f"billing type recorded for every selling offer: {seen}")


def _proof_checkout_family(mapping_row: Dict[str, Any]) -> Dict[str, Any]:
    """The bound Skill 79 validator is what proves the native checkout family."""
    evidence = mapping_row.get("evidence") or {}
    if mapping_row.get("state") != "proven":
        return _row("unproven", False, evidence,
                    "the checkout family cannot be proved without a resolved mapping",
                    "The order form family is not proved for this launch.",
                    "Resolve the checkout mapping first.")
    probe = _validator_state()
    if probe["state"] != "bound":
        return _row("unproven", False, probe,
                    f"the Skill 79 checkout validator is {probe['state']}: {probe['detail']}",
                    "The native order form's own validator is not available on this machine.",
                    "Install the runtime requirement, then retry (no pages were built).")
    return _row("proven", False, {"validator": probe, **evidence},
                f"the native checkout family is bound to the real Skill 79 validator "
                f"({probe['path']})")


def _validator_state() -> Dict[str, Any]:
    """Load and call the real Skill 79 validator exactly as ``checkout.replay`` does."""
    try:
        module = checkout_module._load_validator()
    except Exception as exc:  # noqa: BLE001 — recorded, never a pass
        return {"state": "unavailable", "detail": f"{type(exc).__name__}: {exc}",
                "path": str(checkout_module.validator_path())}
    if module is None or not callable(getattr(module, "validate_request", None)):
        return {"state": "unavailable",
                "detail": "validate_request is absent from the Skill 79 validator",
                "path": str(checkout_module.validator_path())}
    try:
        contract = checkout_module.load_contract()
        required = checkout_module.required_fields(contract)
        modes = checkout_module.checkout_modes(contract)
    except Exception as exc:  # noqa: BLE001
        return {"state": "unavailable", "detail": f"{type(exc).__name__}: {exc}",
                "path": str(checkout_module.contract_path())}
    return {"state": "bound", "detail": "loaded",
            "path": str(checkout_module.validator_path()),
            "contract_sha256": __import__("hashlib").sha256(
                checkout_module.contract_path().read_bytes()).hexdigest(),
            "required_fields": len(required), "modes": list(modes)}


def _proof_output_destination(normalized: Mapping[str, Any],
                              observed: Mapping[str, Any]) -> Dict[str, Any]:
    """Where the pages go: the location identity and the approved write target."""
    location = normalized.get("location_id")
    target = normalized.get("allowed_write_target")
    problems: List[str] = []
    if not _nonempty(location):
        problems.append("location_id is empty")
    if target not in WRITE_TARGETS:
        problems.append(f"allowed_write_target {target!r} is not one of {list(WRITE_TARGETS)}")
    declared = observed.get("output_destination")
    if isinstance(declared, Mapping):
        other = declared.get("location_id")
        if _nonempty(other) and other != location:
            problems.append(
                f"the observed output destination is location {other!r}, not this launch's "
                f"{location!r} (a cross-location write is refused)")
    if problems:
        return _row("unproven", True, {"location_id": location, "write_target": target},
                    "; ".join(problems),
                    "The place these pages are meant to go is not proven for this launch.",
                    "Confirm the destination location and approve the write target.")
    return _row("proven", True,
                {"location_id": location, "write_target": target,
                 "observed": declared if isinstance(declared, Mapping) else None},
                f"output destination {location!r} with write target {target!r}")


def _proof_runtime() -> Dict[str, Any]:
    """The installed runtime: every required skill tree and file resolves on THIS box."""
    found: Dict[str, str] = {}
    missing: List[str] = []
    for slug, rel in RUNTIME_REFS:
        try:
            path = skill_path(slug, rel)
        except SkillResolutionError as exc:
            missing.append(f"{slug}/{rel}: {exc}")
            continue
        if not Path(path).is_file():
            missing.append(f"{slug}/{rel}: not a file at {path}")
            continue
        found[f"{slug}/{rel}"] = str(path)
    if missing:
        return _row("unproven", True, {"missing": missing, "found": sorted(found)},
                    "the installed runtime is incomplete: " + "; ".join(missing),
                    "This machine is missing part of the launch runtime.",
                    "Reinstall the launch skills so every required file resolves.")
    return _row("proven", True, {"found": sorted(found)},
                f"every required runtime file resolves ({len(found)} files)")


def _ref_exists(slug: str, rel: str) -> Optional[str]:
    try:
        path = skill_path(slug, rel)
    except SkillResolutionError:
        return None
    return str(path) if Path(path).is_file() else None


def _proof_conversational(normalized: Mapping[str, Any], required: bool,
                          observed: Mapping[str, Any]) -> Dict[str, Any]:
    """Skill 38's real contract + Skill 29's runtime + exactly one responder.

    Conditional on the approved feature set: a page-only launch is never asked for it.
    Skill 41's generated prompt is a build INPUT — it is recorded as such and never as a
    live workflow; a workflow built from it must carry its twelve-point post-build
    verification and dependency readback.
    """
    missing = [f"{slug}/{rel}" for slug, rel in CONVERSATIONAL_REFS
               if _ref_exists(slug, rel) is None]
    responders = observed.get("responders")
    support = observed.get("skill29_support")
    connected = observed.get("ghl_runtime_connected")
    problems: List[str] = []
    if missing:
        problems.append(f"Skill 38 contract file(s) missing: {missing}")
    if not isinstance(responders, list) or len(responders) != 1:
        problems.append(
            "the responder set is not exactly one (Skill 38's single-responder rule); "
            f"observed {responders!r}")
    if connected is not True:
        problems.append("Skill 29's runtime GHL connection is not observed (PIT/location connection)")
    if not (isinstance(support, list) and set(SKILL29_SUPPORT) <= {str(s) for s in support}):
        problems.append(
            f"Skill 29's declared support {list(SKILL29_SUPPORT)} is not recorded and no "
            "compatible harness adapter is demonstrated")
    workflow = observed.get("workflow_build")
    if isinstance(workflow, Mapping):
        source_kind = workflow.get("source_kind")
        if source_kind == "skill41_prompt":
            problems.append(
                "a Skill 41 generated prompt is a build INPUT, not a live workflow: it may not "
                "be reported as a running workflow")
        points = workflow.get("post_build_verification_points")
        if points != TWELVE_POINTS:
            problems.append(
                f"the twelve-point post-build verification is {points!r}, not {TWELVE_POINTS}")
        if workflow.get("dependency_readback") is not True:
            problems.append("dependency creation/readback is not recorded for the build")
    if problems:
        return _row("unproven", required,
                    {"missing_files": missing, "responders": responders,
                     "connected": connected, "support": support},
                    "; ".join(problems),
                    "The conversational AI is requested, but its runtime, its single responder "
                    "or its build contract is not proven.",
                    "Connect Skill 29, install Skill 38's contract, and name one responder.")
    return _row("proven", required,
                {"files": [f"{s}/{r}" for s, r in CONVERSATIONAL_REFS],
                 "responders": responders, "support": support},
                "Skill 38 contract present, Skill 29 runtime connected, exactly one responder")


def _proof_workflow_auth(required: bool, observed: Mapping[str, Any]) -> Dict[str, Any]:
    """Skill 36's OAuth vs PIT distinction, applied to the OBSERVED capability set.

    The retired community MCP is never a route; a PIT sent to an official MCP endpoint is
    an unverified compatibility mode, never an equal auth path; a shared rate limit never
    authorizes switching transport to evade it; a diagram label is never publication
    authority.
    """
    mode = observed.get("auth_mode")
    problems: List[str] = []
    if mode == AUTH_MODE_COMMUNITY_MCP:
        problems.append(
            "the retired community MCP is not a route: it must stay off (no openclaw MCP "
            "entry, no unit, no listener on 127.0.0.1:8765)")
    elif mode == AUTH_MODE_OFFICIAL_MCP_PIT:
        problems.append(
            "a PIT bearer sent to an official MCP endpoint is an UNVERIFIED compatibility "
            "mode, not an equivalent auth path")
    elif mode not in AUTH_MODES_ALLOWED:
        problems.append(
            f"auth mode {mode!r} is not one of {list(AUTH_MODES_ALLOWED)}; an unobserved auth "
            "path cannot build or publish a workflow")
    if observed.get("transport_switching") is True:
        problems.append(
            "transport switching to evade a shared rate limit is refused: a shared limit does "
            "not authorize another transport")
    authority = observed.get("publication_authority")
    if authority is not None and (not _nonempty(authority) or authority == "diagram_label"):
        problems.append(
            f"publication authority {authority!r} is not a recorded authority: a diagram label "
            "is not permission to publish")
    if problems:
        return _row("unproven", required, {"auth_mode": mode,
                                           "transport_switching": observed.get("transport_switching"),
                                           "publication_authority": authority},
                    "; ".join(problems),
                    "The workflow/authorization surface is not proven for this account.",
                    "Connect the account through a supported authorization mode.")
    return _row("proven", required, {"auth_mode": mode,
                                     "publication_authority": authority},
                f"authorization mode {mode!r} is supported and observed")


def _plan_requests_conversation(plan: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(plan, Mapping):
        return False
    conversation = plan.get("conversation_ai")
    return isinstance(conversation, Mapping) and conversation.get("requested") is True


def _conversation_selected(plan: Optional[Mapping[str, Any]],
                           observed: Mapping[str, Any]) -> bool:
    """F22 item 10: required when the conversational surface is being BUILT/CONNECTED.

    A plan that requests Conversation AI records the client's selection; the runtime,
    the single responder and the playbook contract become a required capability when the
    surface is actually being built/connected in this run (the caller observes the
    responder set / build), or when a live/installed readiness is claimed. Otherwise it
    is recorded unproven-not-required, never silently satisfied.
    """
    observed_build = (isinstance(observed.get("conversational_build"), Mapping)
                      or "responders" in observed
                      or isinstance(observed.get("workflow_build"), Mapping)
                      and observed.get("workflow_build", {}).get("conversational") is True)
    if observed_build:
        return True
    return _plan_requests_conversation(plan) and observed.get("readiness") in (
        "installed", "published", "live")


def _plan_has_workflows(plan: Optional[Mapping[str, Any]]) -> bool:
    if not isinstance(plan, Mapping):
        return False
    automations = plan.get("automations")
    return isinstance(automations, list) and bool(automations)


def _workflow_selected(normalized: Mapping[str, Any], plan: Optional[Mapping[str, Any]],
                       observed: Mapping[str, Any]) -> bool:
    """F22 item 11: required only when a workflow is BUILT/observed in this run.

    A plan that merely PLANS automations hands them to Skill 44's build step; that step
    observes the account's authorization mode. Requiring an observed auth mode at
    assembly of an offline plan would refuse work whose authorization is not this
    step's to hold, so the requirement follows the actual build, or a live/installed
    readiness claim.
    """
    if isinstance(observed.get("workflow_build"), Mapping):
        return True
    if observed.get("readiness") in ("installed", "published", "live"):
        return _plan_has_workflows(plan) or normalized.get("test_only") is False
    return False


def required_capabilities(normalized: Mapping[str, Any],
                          plan: Optional[Mapping[str, Any]] = None,
                          observed: Optional[Mapping[str, Any]] = None,
                          require: Sequence[str] = ()) -> List[str]:
    """The capabilities THIS approved feature set needs. Absence never means required.

    ``require`` is the calling boundary's own selection: the dispatch bridge requires the
    journey mapping because it is about to build from it; assembly requires the live set.
    """
    observed = observed or {}
    live = normalized.get("test_only") is False
    required = list(LOCAL_CAPABILITIES)
    required += [name for name in require if name in CAPABILITIES]
    if live or observed.get("readiness") in ("installed", "published", "live"):
        required += ["billing_type", "native_checkout_family"]
    if _conversation_selected(plan, observed):
        required.append("conversational_workflows")
    if _workflow_selected(normalized, plan, observed):
        required.append("workflow_authorization")
    return [name for name in CAPABILITIES if name in set(required)]


def run(normalized: Mapping[str, Any], *,
        route: Optional[Mapping[str, Any]] = None,
        plan: Optional[Mapping[str, Any]] = None,
        observed: Optional[Mapping[str, Any]] = None,
        require: Sequence[str] = ()) -> Dict[str, Any]:
    """Run every capability check and return the record (deterministic, no timestamps)."""
    observed = dict(observed or {})
    required = required_capabilities(normalized, plan, observed, require)
    journey = _proof_journey(normalized, route)
    journey["required"] = "journey_mapping" in required
    rows: Dict[str, Dict[str, Any]] = {
        "journey_mapping": journey,
        "billing_type": _proof_billing(normalized),
        "native_checkout_family": _proof_checkout_family(journey),
        "output_destination": _proof_output_destination(normalized, observed),
        "installed_runtime": _proof_runtime(),
        "conversational_workflows": _proof_conversational(
            normalized, "conversational_workflows" in required, observed),
        "workflow_authorization": _proof_workflow_auth(
            "workflow_authorization" in required, observed),
    }
    for name, row in rows.items():
        row["required"] = name in required
        if name not in required and row["state"] != "proven":
            row["state"] = "not_required"
    blocked = [name for name in required if rows[name]["state"] != "proven"]
    record = {
        "record_type": RECORD_TYPE,
        "launch_id": normalized.get("launch_id"),
        "tenant_id": normalized.get("tenant_id"),
        "location_id": normalized.get("location_id"),
        "revision": normalized.get("revision"),
        "test_only": bool(normalized.get("test_only", True)),
        "required": required,
        "capabilities": rows,
        "blocked": blocked,
        "state": "blocked" if blocked else ("design_only" if
                                            normalized.get("test_only") is not False else "ready"),
        "client_blockers": [rows[name]["client_message"] for name in blocked],
        "next_steps": [rows[name]["next_step"] for name in blocked],
        "operator_diagnostics": [f"{name}: {rows[name]['detail']}" for name in blocked],
    }
    return record


def blockers(normalized: Mapping[str, Any], *, route: Optional[Mapping[str, Any]] = None,
             plan: Optional[Mapping[str, Any]] = None,
             observed: Optional[Mapping[str, Any]] = None) -> List[str]:
    """Required capabilities that could not be proved, as named refusals."""
    record = run(normalized, route=route, plan=plan, observed=observed)
    return [f"AF-LAUNCH-CAPABILITY: {name}: {record['capabilities'][name]['detail']}"
            for name in record["blocked"]]


def assert_ready(record: Mapping[str, Any]) -> Mapping[str, Any]:
    """Fail closed: return the record only when every REQUIRED capability is proven."""
    blocked = list(record.get("blocked") or [])
    if blocked:
        detail = "; ".join(f"{name}: {(record.get('capabilities') or {}).get(name, {}).get('detail', '')}"
                           for name in blocked)
        raise CapabilityError("AF-LAUNCH-CAPABILITY", detail)
    return record

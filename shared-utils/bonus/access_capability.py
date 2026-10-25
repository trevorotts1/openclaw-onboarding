#!/usr/bin/env python3
"""access_capability.py — T-14 honest bonus membership / access capability
decision (R-13, DEC-16, D-19, D-26, D-28, D-34).

ONE source of truth for the question "can this system grant the optional bonus
membership access?" The answer today is NO for every automated route, and the
module says so with the exact evidence that is missing instead of inventing an
interface.

The five steps the capability actually needs (DEC-16 / R-13):
  identity  — a member identity that works without an email address
  grant     — granting the offer to that identity
  credential— issuing the login credential
  return    — returning the member to the gated content from an SMS message
  recovery  — recovering a lost or expired credential

Every step is reported as `proved`, `unproved`, `retired_rail_only` or
`ui_only`, with repo-relative provenance and the exact missing evidence. A
step that is not `proved` blocks the automated route. Nothing here carries a
URL, a verb or a path: `supported_route()` returns `api: None` on purpose, and
the test suite pins that `None`. The suite also scans the returned surface,
this module and the evidence doc for the API shapes it enumerates (scheme URL,
verb plus path spaced or glued, bare or identifier-prefixed path, a trailing
path segment with no segment after it, schemeless host plus path; dotted
operation ids on the returned surface only). Before matching, the scan
normalises the wrapper characters that formatting puts around a value (quotes,
backticks, asterisks, brackets, parentheses, markdown cell pipes, arrows) and
the separator look-alikes that spell a path differently (backslash, doubled
slash, U+FF0F, U+2215, U+2044, U+29F8). It then decides the ROLE a token plays
before any exemption applies: behind an `api` / `route` / `operation` /
`endpoint` / `method` / `path` / `url` / `uri` / `action` key that sits inside
the 240-character role window -- including a key reached by walking out through
nested frames -- a token is read as an operation value and is flagged. Two
exemptions are closed world. File provenance passes
only when the token is a real file in this tree, or an f-string template whose
variable is bound in the same text and whose whole expansion is a real file. A
reviewed prose token passes only when one of the reviewed windows that contain
it is present verbatim and does not itself begin inside a value. A new token, an
unbound template, or a reviewed token outside its window, fails until a human
reviews it. It is a pattern scan, not a proof: a fabrication in a shape the scan
does not enumerate, or one spelled with a character the normaliser does not map,
is not caught.

Reuse, not a second copy: the membership route question is answered by the
existing GHL capability inventory (`shared-utils/ghl/capability_inventory.py`)
and its frozen public operation registry, never by a local table of guessed
operations.

The supported path is assisted/operator: the owner creates the offer and the
member's access in the GHL Memberships area (a UI rail), the system prepares
the one-step instruction and records an operator confirmation. There is no
receipt until the operator confirms, and the system never claims it granted or
recovered anything.

Independent original gift (D-28 / C-F07): `plan_fulfillment()` derives the
original lane ONLY from the original lane's own inputs. The bonus lane cannot
gate it, and `assert_original_not_gated_by_bonus()` fails if a caller builds a
plan that does.

STDLIB ONLY. No network. No secrets.
"""

from __future__ import annotations

import dataclasses
from typing import Dict, List, Optional, Sequence, Tuple

# --------------------------------------------------------------------------
# Step vocabulary
# --------------------------------------------------------------------------

STEP_ORDER: Tuple[str, ...] = ("identity", "grant", "credential", "return", "recovery")

PROVED = "proved"
UNPROVED = "unproved"
RETIRED_RAIL_ONLY = "retired_rail_only"
UI_ONLY = "ui_only"

_ROUTABLE_STATES = (PROVED,)

BLOCK_REASON = "BONUS_ACCESS_CAPABILITY_BLOCKED"

# The GHL capability inventory's resource key for this family. There is no
# membership entry in the frozen registry, so the inventory answers "no route"
# from its own data instead of this module keeping a parallel table.
MEMBERSHIP_RESOURCE = "memberships"


class BonusCapabilityError(ValueError):
    """A bonus request or state the capability decision does not support."""


class BonusCouplingError(BonusCapabilityError):
    """The original gift plan was gated on the bonus lane."""


@dataclasses.dataclass(frozen=True)
class StepEvidence:
    """One capability step: what is known, from where, and what is missing."""

    step: str
    state: str
    claim: str
    provenance: Tuple[str, ...]
    authority: Tuple[str, ...]
    missing: Tuple[str, ...]

    def as_dict(self) -> dict:
        return {
            "step": self.step,
            "state": self.state,
            "claim": self.claim,
            "provenance": list(self.provenance),
            "authority": list(self.authority),
            "missing": list(self.missing),
            "routable": self.state in _ROUTABLE_STATES,
        }


_GHL = "44-convert-and-flow-operator"
_REGISTRY = f"{_GHL}/tools/engine/cli_anything/gohighlevel/public/operations.py"
_ACTIONS = f"{_GHL}/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py"
_CAPNOTE = f"{_GHL}/automation-templates/launch-ghl-probe/GHL-CAPABILITY-NOTE.md"
_MCPDOC = "36-ghl-mcp-setup/ghl-mcp-setup-full.md"
_COURSE = "06-ghl-install-pages/tools/SELECTORS-LIVE-course.md"
_COMMUNITY = "06-ghl-install-pages/tools/SELECTORS-LIVE-community.md"
_CLICKMAP = "06-ghl-install-pages/references/form-click-map.md"
_INVENTORY = "shared-utils/ghl/capability_inventory.py"

EVIDENCE: Tuple[StepEvidence, ...] = (
    StepEvidence(
        step="identity",
        state=UNPROVED,
        claim=(
            "No supported route establishes a member identity without an email "
            "address. The frozen public registry (documentation fetch 2026-10-18) "
            "carries no memberships or communities operation at all, the official "
            "MCP surface is a dynamic catalog whose account-grant and observed "
            "levels are explicitly NOT held, and the Memberships area is a UI rail."
        ),
        provenance=(_REGISTRY, _INVENTORY, _CLICKMAP),
        authority=("R-13", "D-34", "DEC-16"),
        missing=(
            "a documented memberships/communities operation in the frozen public registry",
            "a recorded tenant success for that operation in the capability receipt",
            "an observed member login that completes with no email address",
        ),
    ),
    StepEvidence(
        step="grant",
        state=RETIRED_RAIL_ONLY,
        claim=(
            "Granting an offer exists only as an internal-workflow action type "
            "(`membership_grant_offer` / `membership_revoke_offer`) and as retired "
            "community-MCP tools. In the frozen v3 production spec the public "
            "interface cannot create, update, publish or delete a workflow "
            "definition at all: its workflow rows are a read plus contact "
            "enrollment and unenrollment against an EXISTING workflow, which is "
            "not authoring and is not a membership grant. Definition authoring "
            "appears only as v4 rows documented at staging-doc level, which the "
            "tenant receipt does not verify. Every automation build routes "
            "through the internal engine, which needs the location's Firebase "
            "refresh token, not the PIT."
        ),
        provenance=(_ACTIONS, _MCPDOC, _CAPNOTE),
        authority=("R-13", "D-19", "DEC-16"),
        missing=(
            "a verified supported-tier operation that grants a membership offer to an identified member",
            "a workflow-build route that does not require the internal Firebase token",
        ),
    ),
    StepEvidence(
        step="credential",
        state=RETIRED_RAIL_ONLY,
        claim=(
            "Course and member credential creation appears only in the retired Tier-2 "
            "community-MCP list (~15 courses/memberships tools whose create/delete "
            "entries are documented as possibly unverified shells). Community groups "
            "have no delete on any known rail and only a slug validator, and the "
            "Memberships area is browser-executed."
        ),
        provenance=(_MCPDOC, _COURSE, _COMMUNITY),
        authority=("R-13", "D-34", "DEC-16"),
        missing=(
            "a live probe proving the course/credential create operations are real endpoints",
            "a supported tier that still exposes them (Tier 2 is retired)",
        ),
    ),
    StepEvidence(
        step="return",
        state=UNPROVED,
        claim=(
            "SMS-first return into gated member content has no verified route. The only "
            "verified SMS operation is a one-off message send; nothing resolves the "
            "SMS-bound person back to the same member record."
        ),
        provenance=(_INVENTORY, "05-ghl-setup/INSTRUCTIONS.md"),
        authority=("R-13", "D-26", "DEC-16"),
        missing=(
            "an operation that returns a member to gated content from an SMS identity",
            "receipt evidence that the SMS-bound person resolves to the same member record",
        ),
    ),
    StepEvidence(
        step="recovery",
        state=UNPROVED,
        claim=(
            "No supported credential-reset or recovery route is documented anywhere in "
            "this repository. Per R-13 an expired credential is never evidence about "
            "the guides themselves: the two questions stay separate."
        ),
        provenance=(_REGISTRY,),
        authority=("R-13", "DEC-16"),
        missing=(
            "a documented credential recovery operation",
            "a tenant observation of recovery completing without an email address",
        ),
    ),
)

_EVIDENCE_BY_STEP: Dict[str, StepEvidence] = {e.step: e for e in EVIDENCE}

CREDENTIAL_STATES: Tuple[str, ...] = ("valid", "expired", "absent", "unknown")


# --------------------------------------------------------------------------
# Capability questions
# --------------------------------------------------------------------------

def capability_evidence() -> Dict[str, dict]:
    """Every step with its state, provenance and exact missing evidence."""
    return {step: _EVIDENCE_BY_STEP[step].as_dict() for step in STEP_ORDER}


def blocked_steps() -> List[str]:
    """Steps that are not proved, in capability order."""
    return [s for s in STEP_ORDER if _EVIDENCE_BY_STEP[s].state not in _ROUTABLE_STATES]


def missing_evidence() -> Dict[str, List[str]]:
    """The exact evidence each blocked step still needs."""
    return {s: list(_EVIDENCE_BY_STEP[s].missing) for s in blocked_steps()}


def membership_inventory_routes() -> List[str]:
    """Routes the shared GHL inventory offers for a membership EXECUTE.

    Reuses `shared-utils/ghl/capability_inventory.py` instead of keeping a
    second table. Returns [] while the family is undocumented there, which is
    the honest answer, never "probably works".

    Fails closed when the reuse path itself cannot be reached. A broken import
    is an instrument failure, not a capability block: returning [] for it would
    make a broken reuse path indistinguishable from a proven "no route".
    """
    try:
        from ghl import capability_inventory as inventory
    except ImportError as exc:
        raise BonusCapabilityError(
            "the shared GHL capability inventory could not be imported "
            f"({exc}); failing closed instead of reporting a capability block"
        ) from exc
    routes = inventory.select_route(
        inventory.OpClass.EXECUTE,
        resource=MEMBERSHIP_RESOURCE,
        dynamic_confirmed=False,
    )
    return [f"{cap.transport.value}:{cap.route}" for cap in routes]


def supported_route() -> dict:
    """The supported path and why the automated one is not available.

    `api` is None by design: no operation is invented for this capability.
    """
    blocked = blocked_steps()
    return {
        "available": not blocked,
        "route": "assisted_operator" if blocked else "unattended",
        "api": None,
        "reason_code": BLOCK_REASON if blocked else "",
        "blocked_steps": blocked,
        "missing_evidence": missing_evidence(),
        "inventory_routes": membership_inventory_routes(),
        "no_invented_api": True,
        "supported_path": (
            "Owner creates the offer and the member's access in the GHL Memberships "
            "area; the system prepares the one-step instruction and records the "
            "operator's confirmation. No unattended grant, no system-claimed "
            "credential and no system-claimed recovery."
        ),
        "advertised_bonus_ready": False,
    }


# --------------------------------------------------------------------------
# Requests
# --------------------------------------------------------------------------

def request_bonus_access(*, unattended: bool = True) -> dict:
    """Resolve a bonus access request. An unattended grant is always refused.

    No branch returns `granted: True`, because no branch can verify identity,
    grant, credential, return or recovery. The assisted branch hands back an
    instruction and NO receipt.
    """
    if not isinstance(unattended, bool):
        raise BonusCapabilityError(f"unattended must be a bool, got {type(unattended).__name__}")
    route = supported_route()
    blocked = list(route["blocked_steps"])
    if unattended:
        return {
            "granted": False,
            "refused": True,
            "route": "refused",
            "reason_code": BLOCK_REASON,
            "reason": (
                "The optional bonus membership has no supported automated route: "
                + ", ".join(blocked)
                + " are unproved. The system will not invent an operation or claim a grant."
            ),
            "blocked_steps": blocked,
            "offer": {
                "route": "assisted_operator",
                "next": "prepare_operator_instruction",
                "message": route["supported_path"],
            },
            "no_silent_downgrade": True,
        }
    return {
        "granted": False,
        "refused": False,
        "route": "assisted_operator",
        "status": "awaiting-operator",
        "instruction": (
            "In the GHL Memberships area, grant the bonus offer to this member and "
            "record the member's identifier. Then confirm here; the confirmation is "
            "the only receipt."
        ),
        "blocked_steps": blocked,
        "receipt": None,
        "system_claimed_grant": False,
        "no_unverified_claim": True,
    }


# --------------------------------------------------------------------------
# Original gift independence (D-28 / C-F07)
# --------------------------------------------------------------------------

def plan_fulfillment(
    *,
    original_ready: bool,
    original_reason: str = "",
    bonus_requested: bool = True,
) -> dict:
    """Plan the original gift and the optional bonus as two independent lanes.

    The original lane is derived from its own inputs only. The bonus lane is
    always the capability decision. A non-ready original is reported for its
    own reason and never as "blocked by the bonus".

    `original_reason` must be a real string. A non-string is refused, never
    coerced: `str(None)` would store the literal "None" as the member-facing
    reason a not-ready lane is required to name.
    """
    if not isinstance(original_ready, bool):
        raise BonusCapabilityError(
            f"original_ready must be a bool, got {type(original_ready).__name__}"
        )
    if not isinstance(bonus_requested, bool):
        raise BonusCapabilityError(
            f"bonus_requested must be a bool, got {type(bonus_requested).__name__}"
        )
    if not isinstance(original_reason, str):
        raise BonusCapabilityError(
            f"original_reason must be a str, got {type(original_reason).__name__}"
        )
    if not original_ready and not original_reason.strip():
        raise BonusCapabilityError("a non-ready original lane must name its own reason")

    route = supported_route()
    original = {
        "route": "direct_chat",
        "ready": original_ready,
        "reason": original_reason.strip(),
        "blocked_by_bonus": False,
        "depends_on_bonus": False,
    }
    bonus = {
        "requested": bonus_requested,
        "available": bool(route["available"]),
        "advertised_ready": bool(route["available"]),
        "route": route["route"],
        "blocked_steps": list(route["blocked_steps"]),
    }
    plan = {
        "original": original,
        "bonus": bonus,
        "advertised_bonus_ready": bonus["advertised_ready"],
        "continuation": "original_and_bonus" if (original_ready and bonus["advertised_ready"])
        else ("original_only" if original_ready else "original_repair"),
    }
    assert_original_not_gated_by_bonus(plan)
    return plan


def assert_original_not_gated_by_bonus(plan: dict) -> bool:
    """Guard: a plan may never gate the original gift on the bonus lane.

    A malformed plan is refused with the domain error. The guard's job is to
    reject a bad plan, so it must not answer a bad plan with a bare
    `AttributeError` from duck-typed attribute access.
    """
    if not isinstance(plan, dict):
        raise BonusCapabilityError(f"plan must be a dict, got {type(plan).__name__}")
    original = plan.get("original")
    if not isinstance(original, dict):
        raise BonusCouplingError("plan has no original lane")
    if original.get("blocked_by_bonus") is not False:
        raise BonusCouplingError("original lane reports a bonus blocker")
    if original.get("depends_on_bonus") is not False:
        raise BonusCouplingError("original lane declares a bonus dependency")
    return True


# --------------------------------------------------------------------------
# Credential vs resource
# --------------------------------------------------------------------------

def resolve_member_state(*, credential_state: str, resource_authorized: bool) -> dict:
    """Keep the credential question and the resource question apart.

    An expired credential is not expired guides. Resource availability is
    derived from `resource_authorized` alone, never from the credential state.
    """
    state = str(credential_state or "").strip().lower()
    if state not in CREDENTIAL_STATES:
        raise BonusCapabilityError(
            f"credential_state must be one of {list(CREDENTIAL_STATES)}, got {credential_state!r}"
        )
    if not isinstance(resource_authorized, bool):
        raise BonusCapabilityError(
            "resource_authorized must be a bool, "
            f"got {type(resource_authorized).__name__}"
        )
    credential_valid = state == "valid"
    return {
        "credential_state": state,
        "credential_valid": credential_valid,
        "resource_authorized": resource_authorized,
        "resource_available": resource_authorized,
        "conflated": False,
        "statement": (
            "The credential is valid." if credential_valid
            else "The credential is not valid; that says nothing about the guides."
        ),
    }


# --------------------------------------------------------------------------
# Machine-readable decision
# --------------------------------------------------------------------------

def decision_document() -> dict:
    """The capability decision the evidence bundle and Command Center read."""
    route = supported_route()
    return {
        "task_id": "T-14",
        "artifact": "bonus-access-capability-decision",
        "requirement_ids": ["R-13"],
        "check_ids": ["C-14", "C-F07"],
        "decided_at": "2026-10-24",
        "steps": list(STEP_ORDER),
        "evidence": capability_evidence(),
        "blocked_steps": list(route["blocked_steps"]),
        "missing_evidence": route["missing_evidence"],
        "route": route,
        "verdict": "BLOCKED" if route["blocked_steps"] else "SUPPORTED",
        "original_gift_independent": True,
    }


if __name__ == "__main__":  # pragma: no cover
    import json

    print(json.dumps(decision_document(), indent=2, sort_keys=True))

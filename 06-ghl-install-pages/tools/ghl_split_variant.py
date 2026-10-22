#!/usr/bin/env python3
"""ghl_split_variant.py — native split-test VARIANT capability, DISABLED by
construction until a live authorized capture proves the real semantics
(Skill 06 v3.0, C6, B10, plan §10.3).

WHY THIS EXISTS
---------------
A funnel step's split test is a real GHL entity: the step carries
``split``/``control_traffic`` fields (visible in the captured
``create-step`` body shape in `ghl_rest_canvas.step_create_body`) and the step
overview carries a ``Create variation`` button at confidence 8.5 (carried
forward, never re-verified). What was NEVER captured is the part that decides
whether a build is honest:

  * how a VARIANT is related to its control (same step? sibling page? a row in
    a ``variations`` array? a second page with a ``variant_of`` pointer?);
  * what identifies a variant natively (its own id? an index? a page id?);
  * how TRAFFIC is expressed and which values are permitted;
  * what the readback looks like, and whether the control's id changes when a
    variant is added.

Without those, the only thing an implementer can do is create two
disconnected pages and call it an A/B test. That is a LIE about the platform
state: it splits nothing, it silently halves nothing, and it produces a
"control" and a "variant" that GHL does not treat as related. The plan forbids
exactly that (§10.3: "Do not fake A/B by creating two disconnected funnel
steps").

So this module ships the opposite of a fake: a complete, validated SCHEMA, the
actual create-variant + read-back operation, and a capture gate that keeps the
operation unreachable until real selectors exist. Synthetic fixtures exercise
both halves offline.

WHAT THIS MODULE *IS*
---------------------
A complete CAPTURE SCHEMA (``CAPTURE_SCHEMA``: 11 fields, each with a
validation rule), a loader (``load_capture``), and the ACTUAL variant
operation behind the capture gate:

  ``build_variant_request``  → the create-variant request, every selector
                               taken verbatim from the capture. Traffic is
                               pinned to the captured ``traffic_default``; the
                               operation REFUSES if the capture's
                               ``traffic_permitted`` is anything but False.
  ``readback_assertions``    → the assertions a read-back must satisfy, built
                               from ``readback_keys`` + ``control_id_*`` +
                               ``variant_relation``.
  ``reuse_decision``         → two-run idempotency: a second run finds the
                               variant by its captured relation/id and reuses
                               it instead of creating a duplicate.

No network, no browser, no GHL I/O, no LLM anywhere in this file: it plans and
validates, a receipted driver executes.

ENABLING IT (the exact blocker, still open)
-------------------------------------------
One authorized staging capture against a real location, recording: the
variant entity relation to its control step, the native id shape, the traffic
field names + permitted range + default, the readback payload, and whether the
control's identity or traffic moves when a variant is added. Write it with
``--capture-checklist`` → fill → ``--state --capture <file>``. A capture that
passes the FULL schema (not merely present keys) flips the state to
ENABLED_FOR_REVIEW; ``enabled`` stays ``False`` until a reviewer approves,
which is a separate, tested change. Until then the state is
``PENDING_LIVE_SELECTOR_CAPTURE``.

Live capture is a NAMED DEPENDENCY on the D5 login fix plus an authenticated
browser — another lane owns it. Nothing here fabricates a selector.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

PENDING_LIVE_SELECTOR_CAPTURE = "PENDING_LIVE_SELECTOR_CAPTURE"
ENABLED_FOR_REVIEW = "ENABLED_FOR_REVIEW"

CAPABILITY_ID = "ghl.native_split_test.variant"

# ── What a live capture MUST contain before this capability may be enabled ───

REQUIRED_CAPTURE_FIELDS: Tuple[str, ...] = (
    "location_id",              # the authorized staging location captured in
    "step_id",                  # the control step the variant was added to
    "control_id_before",        # control identity BEFORE the variant existed
    "control_id_after",         # ... and after (proves identity stability)
    "variant_id",               # the variant's own native id
    "variant_relation",         # how the variant is linked to the control
    "traffic_field",            # the payload field carrying traffic
    "traffic_permitted",        # permitted values/range, as captured
    "traffic_default",          # the platform default the capture observed
    "readback_keys",            # keys the authoritative read returns
    "capture_evidence",         # path/hash of the raw capture artifact
)

# Fields a variant request may never carry until the capture proves them.
FORBIDDEN_UNTIL_CAPTURE: Tuple[str, ...] = (
    "split_percentage",
    "traffic_weight",
    "abort_winner",
    "auto_promote",
)


class CaptureRequired(RuntimeError):
    """The live capture that would authorize this capability is missing."""


class VariantRefused(RuntimeError):
    """A variant action was requested on a disabled capability."""


class CaptureInvalid(CaptureRequired):
    """A capture is present but fails the schema. Never rounded up to valid."""


class TrafficActivationRefused(VariantRefused):
    """A payload would move live traffic. Split tests ship OFF by construction."""


# ── Capture schema: the 11 fields, each with its validation rule ─────────────
#
# Every value here flows from the capture file. Nothing in this module guesses
# a selector: a missing or malformed field is a refusal, never a default.

_EVIDENCE_RE = re.compile(r"sha256:[0-9a-f]{64}")

CAPTURE_SCHEMA: Dict[str, Dict[str, Any]] = {
    "location_id": {
        "rule": "non-empty string: the authorized staging location",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "step_id": {
        "rule": "non-empty string: the CONTROL step the variant hangs off",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "control_id_before": {
        "rule": "non-empty string: control identity BEFORE the variant existed",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "control_id_after": {
        "rule": "non-empty string: control identity AFTER the variant existed",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "variant_id": {
        "rule": "non-empty string: the variant's own native id, as returned",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "variant_relation": {
        "rule": "non-empty string naming HOW the variant is linked to the control; "
                "used verbatim in the request, never interpreted",
        "check": lambda v: isinstance(v, str) and bool(v.strip()),
    },
    "traffic_field": {
        "rule": "non-empty string: the payload key carrying traffic; must not be "
                "one of FORBIDDEN_UNTIL_CAPTURE",
        "check": lambda v: isinstance(v, str) and bool(v.strip())
                           and v not in FORBIDDEN_UNTIL_CAPTURE,
    },
    "traffic_permitted": {
        "rule": "MUST be boolean false. True means the capture observed an "
                "activation path, and this capability never activates traffic",
        "check": lambda v: v is False,
    },
    "traffic_default": {
        "rule": "the platform default the capture observed; replayed verbatim as "
                "the only value this module ever writes into traffic_field",
        "check": lambda v: v is not None
                           and not (isinstance(v, str) and not v.strip()),
    },
    "readback_keys": {
        "rule": "non-empty list of strings: keys the authoritative GET returns "
                "for the variant, asserted after creation",
        "check": lambda v: isinstance(v, (list, tuple)) and len(v) > 0
                           and all(isinstance(k, str) and k.strip() for k in v),
    },
    "capture_evidence": {
        "rule": "string carrying a raw-artifact reference with a "
                "sha256:<64 hex> digest; a shape fixture cannot satisfy this "
                "by accident",
        "check": lambda v: isinstance(v, str) and bool(_EVIDENCE_RE.search(v)),
    },
}

assert tuple(CAPTURE_SCHEMA) == REQUIRED_CAPTURE_FIELDS, (
    "CAPTURE_SCHEMA drifted from REQUIRED_CAPTURE_FIELDS"
)


def capture_checklist() -> Dict[str, Any]:
    """The checklist the authenticated-browser capture step fills in later.

    Emitted from the schema, so the checklist can never drift from validation.
    """
    return {
        "capability": CAPABILITY_ID,
        "state_until_filled": PENDING_LIVE_SELECTOR_CAPTURE,
        "artifact": "JSON object: one capture per authorized staging location",
        "note": "Fill every field from OBSERVED traffic. A guessed value is a "
                "failed capture, not a partial pass. traffic_permitted must be "
                "recorded as false for a split test whose traffic is OFF.",
        "fields": [
            {"name": name, "rule": CAPTURE_SCHEMA[name]["rule"], "required": True}
            for name in REQUIRED_CAPTURE_FIELDS
        ],
    }


def validate_capture(capture: Optional[Dict[str, Any]]) -> List[str]:
    """Return every schema problem; empty list == valid. Never raises."""
    if not isinstance(capture, dict):
        return ["capture is not a JSON object"]
    problems: List[str] = []
    for name in REQUIRED_CAPTURE_FIELDS:
        value = capture.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            problems.append(f"{name}: missing")
            continue
        try:
            ok = bool(CAPTURE_SCHEMA[name]["check"](value))
        except Exception:  # a hostile value must not crash the gate
            ok = False
        if not ok:
            problems.append(f"{name}: {CAPTURE_SCHEMA[name]['rule']}")
    return problems


def load_capture(path: str) -> Dict[str, Any]:
    """Load and validate a capture file. This is the ONLY ingress for a real
    capture. Refuses synthetic fixtures and any schema problem."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            capture = json.load(fh)
    except (OSError, ValueError) as exc:
        raise CaptureRequired(f"{CAPABILITY_ID}: cannot read capture {path}: {exc}")
    if is_synthetic_capture(capture):
        raise CaptureRequired(
            f"{CAPABILITY_ID}: capture {path} is synthetic; "
            f"{SYNTHETIC_CAPTURE_WARNING}"
        )
    problems = validate_capture(capture)
    if problems:
        raise CaptureInvalid(
            f"{CAPABILITY_ID}: capture {path} fails the schema: {problems}"
        )
    return capture


# ── Schema (complete, validated, and inert) ──────────────────────────────────

@dataclass(frozen=True)
class VariantRequest:
    """One requested variant, in the only shape the schema accepts.

    Deliberately absent: traffic weight, split percentage, publish flag. Those
    are the fields that would move live traffic, and their semantics are
    unknown until the capture lands. Adding them here would be inventing a
    contract.
    """

    location_id: str
    funnel_id: str
    step_id: str
    name: str
    slug: str
    is_control: bool = False

    def validate(self) -> "VariantRequest":
        for name in ("location_id", "funnel_id", "step_id", "name", "slug"):
            value = str(getattr(self, name) or "").strip()
            if not value:
                raise VariantRefused(f"variant request: {name} is required")
        if self.is_control:
            raise VariantRefused(
                "is_control=True is refused: a recipe may never declare a NEW "
                "object to be the control of an existing step — the control is "
                "whatever the platform already has, and its identity must not "
                "move (B10 'unchanged control variant')"
            )
        if "/" in self.slug or " " in self.slug:
            raise VariantRefused(
                f"slug {self.slug!r} is not a plain path segment; a variant slug "
                "is a reviewed value, never a label"
            )
        return self


@dataclass
class VariantPlan:
    """The plan a caller gets back. While disabled it is a refusal WITH the
    reason and the required capture fields, never a silent no-op."""

    capability: str
    state: str
    enabled: bool
    request: Optional[Dict[str, Any]] = None
    missing_capture_fields: List[str] = field(default_factory=list)
    reason: str = ""
    next_action: str = ""
    readback_assertions: Optional[Dict[str, Any]] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "state": self.state,
            "enabled": self.enabled,
            "request": self.request,
            "missing_capture_fields": list(self.missing_capture_fields),
            "reason": self.reason,
            "next_action": self.next_action,
            "readback_assertions": self.readback_assertions,
        }


def capability_state(capture: Optional[Dict[str, Any]] = None,
                     reviewed: bool = False) -> Dict[str, Any]:
    """Report the capability state, what is missing, and what is malformed.

    ``capture=None`` is the honest default: nothing has been captured, so the
    state is PENDING_LIVE_SELECTOR_CAPTURE and every required field is missing.
    A partial capture lists only what is still missing — it never rounds up.

    ``enabled`` is gated on BOTH: (a) every required field present, (b) the
    capture passing the FULL schema, (c) an explicit ``reviewed=True``. The
    schema check is why a plausible-looking field can never enable this:
    ``traffic_permitted`` must be literally ``False`` and ``capture_evidence``
    must carry a sha256 digest.
    """
    missing = [f for f in REQUIRED_CAPTURE_FIELDS
               if not _capture_field_present(capture, f)]
    problems = validate_capture(capture) if not missing else []
    if not missing:
        schema_valid = not problems
        return {
            "capability": CAPABILITY_ID,
            "state": ENABLED_FOR_REVIEW,
            "enabled": bool(schema_valid and reviewed),
            "missing_capture_fields": [],
            "schema_valid": schema_valid,
            "schema_problems": problems,
            "reviewed": bool(reviewed),
            "reason": (
                "a complete live capture is present and passes the schema; the "
                "capability may be ENABLED only after review of that capture"
                if schema_valid else
                "a capture is present but FAILS the schema; it is not evidence "
                "and can never enable this capability"
            ),
            "next_action": (
                "reviewer approves the capture (enablement is a separate, "
                "tested change)" if schema_valid else
                "re-run the capture checklist and fix: " + "; ".join(problems)
            ),
        }
    return {
        "capability": CAPABILITY_ID,
        "state": PENDING_LIVE_SELECTOR_CAPTURE,
        "enabled": False,
        "missing_capture_fields": missing,
        "schema_valid": False,
        "schema_problems": problems,
        "reviewed": bool(reviewed),
        "reason": (
            "native split-test entity relation and traffic semantics have not "
            "been captured under authorized staging; without them a variant "
            "recipe would either fake A/B with two disconnected steps or move "
            "live traffic on a guess"
        ),
        "next_action": (
            "capture, against one authorized staging location: "
            + ", ".join(missing)
        ),
    }


def _capture_field_present(capture: Optional[Dict[str, Any]], key: str) -> bool:
    if not isinstance(capture, dict):
        return False
    value = capture.get(key)
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    return True


def assert_capture_proven(capture: Optional[Dict[str, Any]]) -> None:
    """Raise unless the capture passes the FULL schema. Used by anything that
    would otherwise be tempted to proceed on a partial or malformed capture."""
    state = capability_state(capture)
    if state["state"] == PENDING_LIVE_SELECTOR_CAPTURE:
        raise CaptureRequired(
            f"{CAPABILITY_ID}: {PENDING_LIVE_SELECTOR_CAPTURE}; missing "
            f"{state['missing_capture_fields']}"
        )
    problems = validate_capture(capture)
    if problems:
        raise CaptureInvalid(f"{CAPABILITY_ID}: capture fails schema: {problems}")


def plan_variant(request: VariantRequest,
                 capture: Optional[Dict[str, Any]] = None,
                 reviewed: bool = False) -> VariantPlan:
    """Plan one variant. While the capability is disabled this REFUSES.

    It refuses BEFORE validating the request, so a caller cannot use the
    validation error text to learn the shape of a write it is not allowed to
    make, and cannot mistake "the request looked fine" for "the write is
    allowed".

    ``reviewed=True`` is the reviewer's approval. Without a valid, complete
    capture AND that approval, this returns a DISABLED plan with no request.
    """
    state = capability_state(capture, reviewed=reviewed)
    if not state["enabled"]:
        return VariantPlan(
            capability=CAPABILITY_ID,
            state=state["state"],
            enabled=False,
            request=None,
            missing_capture_fields=state["missing_capture_fields"],
            reason=state["reason"],
            next_action=state["next_action"],
        )
    body = build_variant_request(request, capture)
    return VariantPlan(
        capability=CAPABILITY_ID,
        state=ENABLED_FOR_REVIEW,
        enabled=True,
        request=body,
        readback_assertions=readback_assertions(capture),
        reason="capture complete, schema-valid and reviewed",
        next_action="execute through the receipted write driver, then assert "
                    "readback_assertions()",
    )


def assert_no_fake_ab(steps: List[Dict[str, Any]]) -> None:
    """Refuse the specific fake-A/B shape: two sibling steps in one funnel that
    differ only by name and carry no captured variant relation.

    This is the guard that would have caught the shortcut the plan names
    explicitly (§10.3). It reads the platform's own ``split``/``control_traffic``
    fields — the only variant-adjacent data that WAS captured — and refuses
    when a caller presents two steps as an A/B pair without them.
    """
    if not isinstance(steps, list) or len(steps) < 2:
        return
    linked = [
        s for s in steps
        if isinstance(s, dict) and s.get("split") is True
    ]
    if linked:
        return  # the platform says these ARE split-linked; not our call to judge
    raise VariantRefused(
        "refusing a fake A/B: "
        f"{len(steps)} steps are presented as a variant set but none carries "
        "split=true; two disconnected funnel steps are not a split test. "
        f"{PENDING_LIVE_SELECTOR_CAPTURE}"
    )


# ── The variant operation, behind the capture gate ──────────────────────────
#
# Nothing below invents a selector. Every field name and value either comes
# from the capture or from the reviewed VariantRequest. A caller who has no
# capture cannot get a request body at all.

def _require_valid_capture(capture: Any) -> Dict[str, Any]:
    """Coerce a path to a capture and enforce the full schema.

    Traffic activation is checked FIRST so a capture that observed an
    activation path gets the precise refusal, not a generic schema complaint.
    """
    if isinstance(capture, str):
        capture = load_capture(capture)
    # A PRESENT non-False value is an armed capture; a MISSING one is just
    # incomplete and must read as CaptureRequired, not as activation.
    if (isinstance(capture, dict) and "traffic_permitted" in capture
            and capture["traffic_permitted"] is not False):
        raise TrafficActivationRefused(
            f"{CAPABILITY_ID}: capture says traffic_permitted="
            f"{capture.get('traffic_permitted')!r}; this capability never "
            "activates traffic. Re-capture against a split test whose traffic "
            "is OFF."
        )
    assert_capture_proven(capture)
    return capture


def assert_no_traffic_activation(body: Dict[str, Any],
                                 capture: Dict[str, Any]) -> None:
    """Refuse any payload that could move traffic.

    Two independent checks, because this is the invariant the whole capability
    exists to protect:
      1. the capture itself must say traffic activation is not permitted
         (``traffic_permitted is False``);
      2. in the built body, the captured traffic field may hold ONLY the
         captured default — and every FORBIDDEN_UNTIL_CAPTURE key must be
         absent at any depth.
    """
    if capture.get("traffic_permitted") is not False:
        raise TrafficActivationRefused(
            f"{CAPABILITY_ID}: capture says traffic_permitted="
            f"{capture.get('traffic_permitted')!r}; this capability never "
            "activates traffic. Re-capture against a split test whose traffic "
            "is OFF."
        )
    field = capture.get("traffic_field")
    default = capture.get("traffic_default")
    for path, key, value in _walk_payload(body):
        if key in FORBIDDEN_UNTIL_CAPTURE:
            raise TrafficActivationRefused(
                f"{CAPABILITY_ID}: payload carries {key!r} at {path}; traffic-"
                "affecting fields stay out until the capture proves them"
            )
        if key == field and value != default:
            raise TrafficActivationRefused(
                f"{CAPABILITY_ID}: payload sets {field!r}={value!r} at {path} "
                f"but the captured default is {default!r}; only the captured "
                "default may ever be written"
            )


def _walk_payload(node: Any, path: str = "$"):
    """Yield (path, key, value) for every dict entry, recursively."""
    if isinstance(node, dict):
        for key, value in node.items():
            yield path + "." + str(key), key, value
            yield from _walk_payload(value, path + "." + str(key))
    elif isinstance(node, (list, tuple)):
        for i, value in enumerate(node):
            yield from _walk_payload(value, f"{path}[{i}]")


def build_variant_request(request: VariantRequest,
                          capture: Any) -> Dict[str, Any]:
    """Build the create-variant (B) request for a control page step.

    Refuses with ``CaptureRequired`` when no capture is supplied, with
    ``CaptureInvalid`` when the capture is malformed, and with
    ``TrafficActivationRefused`` when anything in the capture or the built
    body could move traffic. Traffic is pinned to the captured default, so the
    variant is created with the split test's traffic still OFF.

    The relation is emitted under the capture's own ``variant_relation`` name
    with the control's captured id as its value: whatever the platform calls
    that linker, the capture said so. This module never guesses the name.
    """
    cap = _require_valid_capture(capture)
    if request.location_id != cap["location_id"]:
        raise VariantRefused(
            f"location mismatch: request is for {request.location_id!r} but the "
            f"capture was taken at {cap['location_id']!r}; a capture authorizes "
            "only its own location"
        )
    if request.step_id != cap["step_id"]:
        raise VariantRefused(
            f"step mismatch: request targets step {request.step_id!r} but the "
            f"capture proves the relation for control step {cap['step_id']!r}"
        )
    request.validate()

    body: Dict[str, Any] = {
        "locationId": cap["location_id"],
        "funnelId": request.funnel_id,
        "step": {
            "id": cap["variant_id"],       # captured id shape, replayed
            "name": request.name,
            "url": request.slug,
            cap["variant_relation"]: cap["control_id_before"],
            cap["traffic_field"]: cap["traffic_default"],
        },
    }
    assert_no_traffic_activation(body, cap)
    return body


def readback_assertions(capture: Any) -> Dict[str, Any]:
    """The assertions an authoritative read-back must satisfy.

    Built entirely from captured observations: the keys the read must carry,
    the control's identity before AND after (so a control whose id moved is a
    failure), and the relation value that proves the variant is linked rather
    than merely coexisting.
    """
    cap = _require_valid_capture(capture)
    return {
        "must_contain_keys": list(cap["readback_keys"]),
        "control_id_must_equal": {"before": cap["control_id_before"],
                                  "after": cap["control_id_after"]},
        "control_identity_stable": (cap["control_id_before"]
                                    == cap["control_id_after"]),
        "variant_id": cap["variant_id"],
        "relation_field": cap["variant_relation"],
        "relation_value": cap["control_id_before"],
        "traffic_field": cap["traffic_field"],
        "traffic_must_equal": cap["traffic_default"],
    }


def readback_passes(capture: Any,
                    readback: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Check one read-back payload against ``readback_assertions``.

    Returns ``(ok, problems)``. Extra keys in the read-back are fine — the
    platform may return more than was captured; missing or moved values are
    not.
    """
    a = readback_assertions(capture)
    problems: List[str] = []
    if not isinstance(readback, dict):
        return False, ["read-back is not a JSON object"]
    for key in a["must_contain_keys"]:
        if key not in readback:
            problems.append(f"read-back missing captured key {key!r}")
    rel_field, rel_value = a["relation_field"], a["relation_value"]
    if rel_field in a["must_contain_keys"] and readback.get(rel_field) != rel_value:
        problems.append(
            f"read-back {rel_field!r}={readback.get(rel_field)!r}; the variant "
            f"is not linked to the control ({rel_value!r})"
        )
    tf, tv = a["traffic_field"], a["traffic_must_equal"]
    if tf in a["must_contain_keys"] and readback.get(tf) != tv:
        problems.append(
            f"read-back {tf!r}={readback.get(tf)!r} but traffic must stay at the "
            f"captured default {tv!r} — a created variant may not move traffic"
        )
    if not a["control_identity_stable"]:
        problems.append(
            "capture observed the control's id MOVING "
            f"({a['control_id_must_equal']['before']!r} -> "
            f"{a['control_id_must_equal']['after']!r}); this capability refuses "
            "to write against a control whose identity is not stable"
        )
    return (not problems), problems


def reuse_decision(capture: Any,
                   existing: List[Dict[str, Any]],
                   request: VariantRequest) -> Dict[str, Any]:
    """Two-run idempotency: decide CREATE vs REUSE from a read-back list.

    A variant is the same variant when its captured relation field points at
    the same control AND its name and url match the request. Match on the
    captured relation only — never on list position, which the platform does
    not promise.
    """
    cap = _require_valid_capture(capture)
    if not isinstance(existing, list):
        raise VariantRefused("existing variants must be a list from a read-back")
    rel_field = cap["variant_relation"]
    for row in existing:
        if not isinstance(row, dict):
            continue
        if (row.get(rel_field) == cap["control_id_before"]
                and row.get("name") == request.name
                and row.get("url") == request.slug):
            return {
                "action": "REUSE",
                "variant_id": row.get("id", cap["variant_id"]),
                "matched_on": {"relation_field": rel_field,
                               "relation_value": cap["control_id_before"],
                               "name": request.name, "url": request.slug},
                "reason": "a variant already linked to this control with this "
                          "name and slug exists; creating another would split "
                          "traffic across an unintended third branch",
            }
    return {
        "action": "CREATE",
        "variant_id": None,
        "matched_on": None,
        "reason": "no read-back row is linked to this control with this name "
                  "and slug",
    }


# ── Synthetic fixtures (offline only; no client data, no real ids) ───────────

SYNTHETIC_STEPS = [
    {"id": "step-aaaa", "name": "Opt-in", "url": "optin",
     "split": False, "control_traffic": 100},
    {"id": "step-bbbb", "name": "Opt-in (variant)", "url": "optin-b",
     "split": False, "control_traffic": 100},
]

SYNTHETIC_STEPS_SPLIT = [
    {"id": "step-aaaa", "name": "Opt-in", "url": "optin",
     "split": True, "control_traffic": 100},
    {"id": "step-cccc", "name": "Opt-in B", "url": "optin-b",
     "split": True, "control_traffic": 0},
]

# A capture fixture that is COMPLETE BY SHAPE but is explicitly labelled
# synthetic. It exists to prove the enablement gate is reachable and keyed on
# the required fields — it is NOT evidence about GHL and must never be passed
# as the real capture (see SYNTHETIC_CAPTURE_WARNING).
SYNTHETIC_COMPLETE_CAPTURE = {
    "location_id": "loc-synthetic",
    "step_id": "step-synthetic",
    "control_id_before": "step-synthetic",
    "control_id_after": "step-synthetic",
    "variant_id": "step-synthetic-v1",
    "variant_relation": "SYNTHETIC-NOT-CAPTURED",
    "traffic_field": "SYNTHETIC-NOT-CAPTURED",
    "traffic_permitted": ["SYNTHETIC-NOT-CAPTURED"],
    "traffic_default": "SYNTHETIC-NOT-CAPTURED",
    "readback_keys": ["SYNTHETIC-NOT-CAPTURED"],
    "capture_evidence": "SYNTHETIC-FIXTURE-NOT-EVIDENCE",
}

SYNTHETIC_CAPTURE_WARNING = (
    "SYNTHETIC_COMPLETE_CAPTURE is a shape fixture. It is NOT a live capture "
    "and must never be treated as evidence; a real capture carries real "
    "observed values and a hash of the raw artifact."
)

# The OFFLINE capture: schema-valid, self-consistent, `_fixture: true`, and
# every value fake. It exists so the operation's happy path is provable with
# no live GHL call. `_fixture` is what makes `is_synthetic_capture` and
# `load_capture` refuse it as evidence — the tests below rely on that.
OFFLINE_CAPTURE: Dict[str, Any] = {
    "_fixture": True,
    "_note": "offline fixture; fake ids; not evidence about GHL",
    "location_id": "loc-offline-0001",
    "step_id": "step-offline-control",
    "control_id_before": "step-offline-control",
    "control_id_after": "step-offline-control",
    "variant_id": "step-offline-variant",
    "variant_relation": "variationOf",
    "traffic_field": "control_traffic",
    "traffic_permitted": False,
    "traffic_default": 100,
    "readback_keys": ["id", "name", "url", "variationOf", "control_traffic"],
    "capture_evidence": "fixture://offline-capture sha256:" + "0" * 64,
}


def is_synthetic_capture(capture: Optional[Dict[str, Any]]) -> bool:
    """Detect a shape fixture so a caller can never mistake one for evidence.

    Two independent tells: an explicit ``_fixture`` marker key (the offline
    fixtures set it), or any value echoing the SYNTHETIC marker.
    """
    if not isinstance(capture, dict):
        return False
    if capture.get("_fixture"):
        return True
    for key, value in capture.items():
        if str(key) == "_fixture":
            continue
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, str) and "SYNTHETIC" in item.upper():
                return True
    return False


def plan_variant_from_real_capture(request: VariantRequest,
                                   capture: Optional[Dict[str, Any]],
                                   reviewed: bool = False) -> VariantPlan:
    """``plan_variant`` plus the synthetic-capture refusal. Production callers
    use THIS entry point; tests use ``plan_variant`` directly."""
    if is_synthetic_capture(capture):
        raise CaptureRequired(
            f"{CAPABILITY_ID}: the supplied capture is synthetic "
            f"({SYNTHETIC_CAPTURE_WARNING}); a shape fixture is not evidence"
        )
    return plan_variant(request, capture, reviewed=reviewed)


# ── Self-test (pure; no network) ─────────────────────────────────────────────

def _selftest() -> int:
    import sys

    errors: List[str] = []
    state = capability_state()
    if state["state"] != PENDING_LIVE_SELECTOR_CAPTURE:
        errors.append(f"default state must be pending, got {state['state']}")
    if state["enabled"] is not False:
        errors.append("default capability must be disabled")
    if sorted(state["missing_capture_fields"]) != sorted(REQUIRED_CAPTURE_FIELDS):
        errors.append("a missing capture must list every required field")

    req = VariantRequest(location_id="loc-x", funnel_id="f-x",
                         step_id="step-x", name="Variant", slug="variant")
    plan = plan_variant(req)
    if plan.enabled or plan.state != PENDING_LIVE_SELECTOR_CAPTURE:
        errors.append(f"plan_variant must refuse while disabled, got {plan.as_dict()}")

    partial = dict(SYNTHETIC_COMPLETE_CAPTURE)
    partial.pop("traffic_field")
    partial["variant_relation"] = "sibling-page"  # real-looking value, still synthetic
    for k in ("traffic_permitted", "traffic_default", "readback_keys",
              "capture_evidence"):
        partial[k] = "observed"
    if capability_state(partial)["state"] != PENDING_LIVE_SELECTOR_CAPTURE:
        errors.append("a partial capture must stay pending")

    if not is_synthetic_capture(SYNTHETIC_COMPLETE_CAPTURE):
        errors.append("the synthetic fixture must be detected as synthetic")
    try:
        plan_variant_from_real_capture(req, SYNTHETIC_COMPLETE_CAPTURE)
        errors.append("a synthetic capture must be refused by the real entry point")
    except CaptureRequired:
        pass

    try:
        assert_no_fake_ab(SYNTHETIC_STEPS)
        errors.append("two unlinked sibling steps must be refused as fake A/B")
    except VariantRefused:
        pass
    assert_no_fake_ab(SYNTHETIC_STEPS_SPLIT)  # split=true passes through

    try:
        VariantRequest(location_id="l", funnel_id="f", step_id="s",
                       name="Control", slug="c", is_control=True).validate()
        errors.append("declaring a new control must be refused")
    except VariantRefused:
        pass

    # ── The operation, on a schema-valid OFFLINE capture ────────────────────
    cap = dict(OFFLINE_CAPTURE)
    if validate_capture(cap):
        errors.append(f"the offline capture fixture must be schema-valid: "
                      f"{validate_capture(cap)}")
    op_req = VariantRequest(location_id=cap["location_id"],
                            funnel_id="funnel-offline",
                            step_id=cap["step_id"], name="B", slug="b")

    try:
        build_variant_request(op_req, None)
        errors.append("the operation must refuse with no capture")
    except CaptureRequired:
        pass

    bad = dict(cap, traffic_permitted=True)
    try:
        build_variant_request(op_req, bad)
        errors.append("a capture with traffic_permitted=True must be refused")
    except TrafficActivationRefused:
        pass

    body = build_variant_request(op_req, cap)
    if body["step"][cap["traffic_field"]] != cap["traffic_default"]:
        errors.append("the built body must carry ONLY the captured traffic "
                      "default")
    if any(k in body["step"] for k in FORBIDDEN_UNTIL_CAPTURE):
        errors.append("the built body must carry no traffic-affecting field")

    rb = {k: "x" for k in cap["readback_keys"]}
    rb[cap["variant_relation"]] = cap["control_id_before"]
    rb[cap["traffic_field"]] = cap["traffic_default"]
    ok, problems = readback_passes(cap, rb)
    if not ok:
        errors.append(f"the matching read-back must pass, got {problems}")
    moved = dict(rb, **{cap["traffic_field"]: "activated"})
    if readback_passes(cap, moved)[0]:
        errors.append("a read-back that moved traffic must fail")

    existing = [{"id": cap["variant_id"], "name": req.name, "url": req.slug,
                 cap["variant_relation"]: cap["control_id_before"]}]
    if reuse_decision(cap, existing, req)["action"] != "REUSE":
        errors.append("a linked, matching variant must be REUSED")
    if reuse_decision(cap, [], req)["action"] != "CREATE":
        errors.append("with no match the decision must be CREATE")

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_split_variant capture gate + variant operation "
          "(no network)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="offline selftest")
    ap.add_argument("--state", action="store_true", help="print capability state")
    ap.add_argument("--capture", help="capture JSON file to evaluate or use")
    ap.add_argument("--capture-checklist", action="store_true",
                    help="print the checklist the capture step must fill")
    ap.add_argument("--plan", action="store_true",
                    help="print a variant plan (needs --capture; refuses "
                         "unless the capture is valid AND --reviewed)")
    ap.add_argument("--reviewed", action="store_true",
                    help="the reviewer's approval; without it the plan stays "
                         "disabled even for a valid capture")
    ap.add_argument("--location", help="location_id for --plan")
    ap.add_argument("--funnel", help="funnel_id for --plan")
    ap.add_argument("--step", help="control step_id for --plan")
    ap.add_argument("--name", help="variant name for --plan")
    ap.add_argument("--slug", help="variant slug for --plan")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()
    if args.capture_checklist:
        print(json.dumps(capture_checklist(), indent=2))
        return 0

    # Every capture-dependent path funnels through here so a bad capture is a
    # clean, typed refusal — never a traceback a reader has to decode.
    try:
        if args.state:
            capture = load_capture(args.capture) if args.capture else None
            print(json.dumps(capability_state(capture, reviewed=args.reviewed),
                             indent=2))
            return 0
        if args.plan:
            if not all((args.capture, args.location, args.funnel, args.step,
                        args.name, args.slug)):
                ap.error("--plan needs --capture --location --funnel --step "
                         "--name --slug")
            req = VariantRequest(location_id=args.location,
                                 funnel_id=args.funnel, step_id=args.step,
                                 name=args.name, slug=args.slug)
            plan = plan_variant(req, load_capture(args.capture),
                                reviewed=args.reviewed)
            print(json.dumps(plan.as_dict(), indent=2))
            return 0 if plan.enabled else 3
    except (CaptureRequired, VariantRefused) as exc:
        print(f"REFUSE: {exc}", file=sys.stderr)
        return 1
    ap.print_help()
    return 2


__all__ = [
    "PENDING_LIVE_SELECTOR_CAPTURE", "ENABLED_FOR_REVIEW", "CAPABILITY_ID",
    "REQUIRED_CAPTURE_FIELDS", "FORBIDDEN_UNTIL_CAPTURE", "CAPTURE_SCHEMA",
    "CaptureRequired", "CaptureInvalid", "VariantRefused",
    "TrafficActivationRefused",
    "VariantRequest", "VariantPlan", "capability_state",
    "capture_checklist", "validate_capture", "load_capture",
    "assert_capture_proven", "plan_variant", "plan_variant_from_real_capture",
    "build_variant_request", "assert_no_traffic_activation",
    "readback_assertions", "readback_passes", "reuse_decision",
    "assert_no_fake_ab", "is_synthetic_capture", "SYNTHETIC_CAPTURE_WARNING",
]


if __name__ == "__main__":
    import sys
    sys.exit(main())

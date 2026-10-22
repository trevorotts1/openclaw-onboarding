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

So this module ships the opposite of a fake: a complete, validated SCHEMA and
a capability registry that refuses every real write, plus synthetic fixtures
that exercise the refusal paths offline.

WHAT THIS MODULE IS *NOT*
-------------------------
No network, no browser, no GHL I/O, no LLM. It cannot create a variant even if
asked: ``plan_variant`` returns a DISABLED plan and ``assert_capture_proven``
raises unless a capture artifact with every required field is supplied. The
only production-adjacent thing it does is name, precisely, what a live capture
must contain before the capability may be enabled.

ENABLING IT LATER (the exact blocker)
-------------------------------------
One authorized staging capture against a real location, recording: the
variant entity relation to its control step, the native id shape, the traffic
field names + permitted range + default, the readback payload, and whether the
control's identity or traffic moves when a variant is added. Store it, then
call ``capability_state(capture=...)`` — every required key present flips the
capability to ENABLED_FOR_REVIEW, which is still not a license to run: the
reviewer decides. Until then the state is
``PENDING_LIVE_SELECTOR_CAPTURE``.
"""

from __future__ import annotations

import json
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

    def as_dict(self) -> Dict[str, Any]:
        return {
            "capability": self.capability,
            "state": self.state,
            "enabled": self.enabled,
            "request": self.request,
            "missing_capture_fields": list(self.missing_capture_fields),
            "reason": self.reason,
            "next_action": self.next_action,
        }


def capability_state(capture: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Report the capability state, and what is missing from a capture.

    ``capture=None`` is the honest default: nothing has been captured, so the
    state is PENDING_LIVE_SELECTOR_CAPTURE and every required field is missing.
    A partial capture lists only what is still missing — it never rounds up.
    """
    missing = [f for f in REQUIRED_CAPTURE_FIELDS
               if not _capture_field_present(capture, f)]
    if not missing:
        return {
            "capability": CAPABILITY_ID,
            "state": ENABLED_FOR_REVIEW,
            "enabled": False,  # review is still owed; never self-enabling
            "missing_capture_fields": [],
            "reason": "a complete live capture is present; the capability may "
                      "be ENABLED only after review of that capture",
            "next_action": "reviewer approves the capture, then the enablement "
                           "is a separate change with its own tests",
        }
    return {
        "capability": CAPABILITY_ID,
        "state": PENDING_LIVE_SELECTOR_CAPTURE,
        "enabled": False,
        "missing_capture_fields": missing,
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
    """Raise unless the capture covers every required field. Used by anything
    that would otherwise be tempted to proceed on a partial capture."""
    state = capability_state(capture)
    if state["state"] != ENABLED_FOR_REVIEW:
        raise CaptureRequired(
            f"{CAPABILITY_ID}: {PENDING_LIVE_SELECTOR_CAPTURE}; missing "
            f"{state['missing_capture_fields']}"
        )


def plan_variant(request: VariantRequest,
                 capture: Optional[Dict[str, Any]] = None) -> VariantPlan:
    """Plan one variant. While the capability is disabled this REFUSES.

    It refuses BEFORE validating the request, so a caller cannot use the
    validation error text to learn the shape of a write it is not allowed to
    make, and cannot mistake "the request looked fine" for "the write is
    allowed".
    """
    state = capability_state(capture)
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
    # Unreachable today: capability_state never sets enabled=True. Kept so the
    # enablement change is a one-line, reviewable edit rather than a rewrite.
    request.validate()
    return VariantPlan(
        capability=CAPABILITY_ID,
        state=ENABLED_FOR_REVIEW,
        enabled=True,
        request={
            "location_id": request.location_id,
            "funnel_id": request.funnel_id,
            "step_id": request.step_id,
            "name": request.name,
            "slug": request.slug,
        },
        reason="capture complete and reviewed",
        next_action="execute through the receipted write driver",
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


def is_synthetic_capture(capture: Optional[Dict[str, Any]]) -> bool:
    """Detect the synthetic fixture (or any value echoing its marker) so a
    caller can refuse to mistake a shape test for evidence."""
    if not isinstance(capture, dict):
        return False
    for value in capture.values():
        for item in (value if isinstance(value, list) else [value]):
            if isinstance(item, str) and "SYNTHETIC" in item.upper():
                return True
    return False


def plan_variant_from_real_capture(request: VariantRequest,
                                   capture: Optional[Dict[str, Any]]) -> VariantPlan:
    """``plan_variant`` plus the synthetic-capture refusal. Production callers
    use THIS entry point; tests use ``plan_variant`` directly."""
    if is_synthetic_capture(capture):
        raise CaptureRequired(
            f"{CAPABILITY_ID}: the supplied capture is synthetic "
            f"({SYNTHETIC_CAPTURE_WARNING}); a shape fixture is not evidence"
        )
    return plan_variant(request, capture)


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

    if errors:
        for e in errors:
            print(f"  FAIL: {e}", file=sys.stderr)
        print(f"\n[selftest] FAIL — {len(errors)} error(s)", file=sys.stderr)
        return 1
    print("[selftest] PASS — ghl_split_variant disabled capability + gates "
          "(no network)")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--selftest", action="store_true", help="offline selftest")
    ap.add_argument("--state", action="store_true", help="print capability state")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    if args.state:
        print(json.dumps(capability_state(), indent=2))
        return 0
    ap.print_help()
    return 2


__all__ = [
    "PENDING_LIVE_SELECTOR_CAPTURE", "ENABLED_FOR_REVIEW", "CAPABILITY_ID",
    "REQUIRED_CAPTURE_FIELDS", "FORBIDDEN_UNTIL_CAPTURE",
    "CaptureRequired", "VariantRefused",
    "VariantRequest", "VariantPlan", "capability_state",
    "assert_capture_proven", "plan_variant", "plan_variant_from_real_capture",
    "assert_no_fake_ab", "is_synthetic_capture", "SYNTHETIC_CAPTURE_WARNING",
]


if __name__ == "__main__":
    import sys
    sys.exit(main())

#!/usr/bin/env python3
"""ghl_fallback_ladder.py — U113 (E5-8; closes G6): the SINGLE unified
browser->API->MCP fallback-ladder acceptance across Skill 6 build surfaces
("inability to fail").

WHY THIS EXISTS
----------------
Skill 6 already has method ROUTING (DIRECT / VERCEL_EMBED / SKILL44_WIDGET —
``ghl_method.py::classify_page``) and PER-SURFACE, AD-HOC fallbacks (the
page-code drag beneath the REST canvas, U30/B-U16; the survey builder's
capture-gated REST lane beneath its browser-drag primary,
``ghl_survey_rest.py``). What did NOT exist before this unit was ONE place
that declares, per surface AND per operation, the attempt order across the
three transports — **browser (UI-drive) -> API (REST) -> MCP (the GHL MCP)**
— in an auditable file, with a fault-injection-provable guarantee that a
failed rung hands off to the next one, tags every failure with the SAME
taxonomy the board already uses (``cc_board.py`` ``_CC_BLOCK_REASONS``), and
only records a fail-closed PARKED outcome when NO declared rung completed the
SAME operation that was requested.

THIS MODULE IS THE RUNNER, NOT A NEW BUILDER
---------------------------------------------
``run_ladder()`` takes the SURFACE's already-existing per-transport callables
(the caller wires ``ghl_rest_canvas`` / ``ghl_iframe_drag.smoke_first`` /
a Skill-44-MCP call, etc. into a ``{"api": fn, "browser": fn, "mcp": fn}``
mapping) and walks them in the order declared in ``fallback-ladder.json``.
This module invents NO new build logic. It selects the capable transport for
the REQUESTED OPERATION at the CONNECTED LOCATION, not a blanket transport
for the surface, and it preserves the logical run, the tenant, the native
object ids and the still-incomplete operation across every fallback.

WHAT COUNTS AS SUCCESS (the F11 completion contract)
----------------------------------------------------
A rung may only make the ladder succeed when ALL of these hold:

* ``ok`` is the boolean ``True`` — the literal ``True``, never a truthy
  value (``1``, ``"yes"``, a non-empty dict). A non-boolean ``ok`` is a
  wiring bug and raises :class:`LadderRungError` instead of passing.
* ``operation_complete`` is the boolean ``True`` — the rung states it
  finished the operation, not merely that it started or prepared something.
* ``operation`` names the SAME operation the caller requested. A rung that
  completed a different operation (for example a prerequisite that created
  the custom fields a form needs) did not complete the request. When the
  surface declares operation ids, a rung that omits ``operation`` has not
  described a completion at all and is recorded as ``partial``.
* The rung is not declared ``kind: "prerequisite"`` in the config. A
  prerequisite rung can never report the whole page/form operation complete,
  even if it wrongly claims ``operation_complete``; that contradiction is
  recorded and the ladder moves on.
* When the surface declares a connected location, the location is bound and
  the rung's observed location (when it reports one) matches the expected
  one. A cross-tenant read-back is never a completion.
* The rung's ``run_id`` (when reported) matches the logical run, so a
  fallback cannot silently continue a DIFFERENT run.

Any other ``ok: true`` outcome is classified ``partial`` or
``prerequisite_ready`` — distinct states that are recorded on the receipt
and are never allowed to become ``operation_complete``.

FALLBACK ENABLEMENT IS EXPLICIT
-------------------------------
``GHL_FALLBACK_LADDER`` is read as an explicit three-state switch:

* unset / empty  -> ``default-on``: the full declared ladder runs. Failover
  is the production default; a silently single-rung ladder was the defect
  this unit fixes.
* ``1``/``true``/``yes``/``on`` -> ``explicit-on`` (identical behaviour).
* ``0``/``false``/``no``/``off`` -> ``explicit-off``: ONLY the first declared
  operation rung is attempted. This is the deliberate single-rung revert.
* anything else -> :class:`LadderConfigError`. An unrecognized value is not
  guessed into on or off.

The chosen enablement is stamped on every receipt (``enablement``).

HANDOFF ACROSS RUNGS (DOM + SESSION)
------------------------------------
A fallback rung must not assume it shares a browser session with the rung
that failed. For every surface that drives a browser, the config declares
``dom_refresh: true`` and the caller MUST supply an enter hook for the
browser transport (``enter_hooks={"browser": fn}``) when that browser rung
is reached as a FALLBACK — after a prior rung has already run. The hook
re-establishes the page/context, refreshes DOM references, and returns at
least a ``dom_epoch``; the ladder records that epoch on the attempt. A
fallback browser rung with no enter hook refuses
(:class:`LadderConfigError`) rather than reusing a stale reference. The
PRIMARY browser rung needs no hook: it is the rung that establishes the
session, so there is no failed rung to share with.

CLEANUP
-------
The ladder never opens a page, context, session or browser process, so it has
none to release. The enter hook is where a caller re-establishes state, and
the caller keeps its own ``finally`` cleanup (``browser_manager.sh`` closes
only the session it owns).

CONTRACT FOR A RUNG CALLABLE (mirrors ``ghl_iframe_drag.smoke_first`` —
"NEVER RAISES — always returns a dict"):
    Takes no arguments (bind everything via closure/functools.partial).
    Success (completion):
        {"ok": True, "operation": <requested operation id>,
         "operation_complete": True, "detail": "...",
         "location_id": "...", "run_id": "...", "native_ids": {...}}
    Partial / prerequisite:
        {"ok": True, "operation": <id>, "prerequisite_ready": True, ...}
        {"ok": True, "operation": <id>, "partial": True, ...}
    Failure:
        {"ok": False, "code": <one of TAXONOMY_TAGS>, "detail": "..."}
    A rung that raises is treated as a WIRING BUG (an uncoded failure this
    module refuses to silently swallow or fabricate a taxonomy tag for) and
    surfaces as :class:`LadderRungError`.

TAXONOMY IS THE BOARD'S, NOT A NEW ONE (single source of truth)
------------------------------------------------------------------
Failure codes are ``cc_board.py``'s existing ``_CC_BLOCK_REASONS`` tuple
(``cc_board.py:103`` — AUTH-STOP / SELECTOR-MISS / RATE-LIMIT /
TOKEN-CONTEXT / PARKED / VERIFY-FAIL), imported directly rather than
re-declared, so the two can never drift apart.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

# ── reuse the board's own taxonomy — no second source of truth ────────────────
_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))
from cc_board import _CC_BLOCK_REASONS as TAXONOMY_TAGS  # noqa: E402

import ghl_evidence  # noqa: E402  (S06-08 tenant contract + evidence scrubber)

# ── constants ───────────────────────────────────────────────────────────────
FLAG_ENV = "GHL_FALLBACK_LADDER"
TRANSPORTS: Tuple[str, ...] = ("browser", "api", "mcp")
RUNG_KINDS: Tuple[str, ...] = ("operation", "prerequisite")
_LADDER_FILENAME = "fallback-ladder.json"
_TRUTHY = {"1", "true", "yes", "on"}
_FALSEY = {"0", "false", "no", "off"}

# Enablement labels stamped on every receipt.
ENABLE_DEFAULT_ON = "default-on"
ENABLE_EXPLICIT_ON = "explicit-on"
ENABLE_EXPLICIT_OFF = "explicit-off"

# Attempt outcome classes. ``operation_complete`` is the only class that can
# satisfy the ladder; the other two are recorded as distinct states.
CLASS_COMPLETE = "operation_complete"
CLASS_PREREQUISITE = "prerequisite_ready"
CLASS_PARTIAL = "partial"
CLASS_FAILED = "failed"


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── errors — never silently default (matches ghl_method.MethodDecisionError) ──

class LadderConfigError(ValueError):
    """Raised for a malformed fallback-ladder.json, an unknown surface or
    operation, a surface whose declared rung has no callable wired at call
    time, or an unrecognized enablement value. Never silently skipped — a bad
    config must fail loud, exactly like ``ghl_method.MethodDecisionError``
    refuses to default on bad input."""


class SurfaceNotLadderedError(LadderConfigError):
    """Raised when a surface genuinely has only ONE real transport today (see
    the config's ``not_laddered`` map). Distinguishes "no second rung exists"
    from "unknown surface" so a caller never mistakes an honest single-lane
    surface for a config bug."""

    def __init__(self, surface: str, reason: str) -> None:
        self.surface = surface
        self.reason = reason
        super().__init__(
            f"surface {surface!r} is not laddered (single real transport today): {reason}"
        )


class LadderRungError(RuntimeError):
    """Raised when a rung callable raises instead of returning a taxonomy-
    tagged dict, returns a non-boolean ``ok``, or returns a code outside
    TAXONOMY_TAGS. This module refuses to fabricate a receipt for an uncoded
    or ill-typed failure."""


# ── config load + validate ────────────────────────────────────────────────────

def _default_ladder_path() -> str:
    return str(_TOOLS_DIR / _LADDER_FILENAME)


def _load_raw(path: Optional[str] = None) -> dict:
    p = path or _default_ladder_path()
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _validate_surface_entry(name: str, entry: Mapping[str, Any]) -> None:
    if not isinstance(entry, Mapping):
        raise LadderConfigError(f"surface {name!r}: entry must be an object")
    if "alias_of" in entry:
        return
    order = entry.get("order")
    if not isinstance(order, list) or not order:
        raise LadderConfigError(f"surface {name!r}: 'order' must be a non-empty list")
    if len(order) < 2:
        raise LadderConfigError(
            f"surface {name!r}: a laddered surface needs >=2 real rungs "
            "(a single-lane surface belongs under 'not_laddered', never a "
            "fabricated one-rung 'ladder')"
        )
    seen = set()
    for transport in order:
        if transport not in TRANSPORTS:
            raise LadderConfigError(
                f"surface {name!r}: unknown transport {transport!r} "
                f"(must be one of {TRANSPORTS})"
            )
        if transport in seen:
            raise LadderConfigError(
                f"surface {name!r}: transport {transport!r} declared twice in 'order'"
            )
        seen.add(transport)

    # Rung kinds: every declared rung may carry {"kind", "why"}. At least one
    # rung must be able to COMPLETE the operation; a ladder made only of
    # prerequisites can never satisfy a request.
    rungs = entry.get("rungs", {})
    if not isinstance(rungs, Mapping):
        raise LadderConfigError(f"surface {name!r}: 'rungs' must be an object")
    kinds: Dict[str, str] = {}
    for transport, meta in rungs.items():
        if transport not in order:
            raise LadderConfigError(
                f"surface {name!r}: rung {transport!r} has metadata but is not in 'order'"
            )
        if not isinstance(meta, Mapping):
            raise LadderConfigError(
                f"surface {name!r}: rung {transport!r} metadata must be an object"
            )
        kind = meta.get("kind", "operation")
        if kind not in RUNG_KINDS:
            raise LadderConfigError(
                f"surface {name!r}: rung {transport!r} kind {kind!r} "
                f"must be one of {RUNG_KINDS}"
            )
        if kind == "prerequisite" and not str(meta.get("why", "")).strip():
            raise LadderConfigError(
                f"surface {name!r}: prerequisite rung {transport!r} must say why "
                "it cannot complete the operation"
            )
        kinds[transport] = kind
    for transport in order:
        if kinds.get(transport, "operation") == "operation":
            break
    else:
        raise LadderConfigError(
            f"surface {name!r}: every rung is declared 'prerequisite' — no rung "
            "can complete the operation, so this is not a ladder"
        )

    operations = entry.get("operations")
    if operations is not None:
        if (not isinstance(operations, list) or not operations
                or any(not isinstance(op, str) or not op.strip() for op in operations)):
            raise LadderConfigError(
                f"surface {name!r}: 'operations' must be a non-empty list of "
                "operation ids"
            )

    location = entry.get("location")
    if location is not None:
        if not isinstance(location, Mapping):
            raise LadderConfigError(f"surface {name!r}: 'location' must be an object")
        if not isinstance(location.get("required"), bool):
            raise LadderConfigError(
                f"surface {name!r}: location.required must be a boolean"
            )
        if location.get("required") and not str(location.get("carrier", "")).strip():
            raise LadderConfigError(
                f"surface {name!r}: a location-required surface must name the "
                "'carrier' field that binds the connected location"
            )

    if not isinstance(entry.get("dom_refresh", False), bool):
        raise LadderConfigError(f"surface {name!r}: 'dom_refresh' must be a boolean")


def validate_ladder_file(path: Optional[str] = None) -> dict:
    """Load + structurally validate fallback-ladder.json. Raises
    :class:`LadderConfigError` on any malformed entry. Returns the parsed
    dict on success (callers that already validated may reuse the return
    value instead of re-parsing)."""
    raw = _load_raw(path)
    surfaces = raw.get("surfaces")
    not_laddered = raw.get("not_laddered", {})
    if not isinstance(surfaces, dict) or not surfaces:
        raise LadderConfigError("fallback-ladder.json: 'surfaces' must be a non-empty object")
    if not isinstance(not_laddered, dict):
        raise LadderConfigError("fallback-ladder.json: 'not_laddered' must be an object")

    overlap = set(surfaces) & set(not_laddered)
    if overlap:
        raise LadderConfigError(
            f"fallback-ladder.json: surface(s) {sorted(overlap)} declared in BOTH "
            "'surfaces' and 'not_laddered' — a surface is either laddered or it isn't"
        )

    for name, entry in surfaces.items():
        _validate_surface_entry(name, entry)

    for name, entry in not_laddered.items():
        if not isinstance(entry, dict) or not entry.get("reason"):
            raise LadderConfigError(
                f"not_laddered surface {name!r}: must declare a non-empty 'reason'"
            )

    return raw


def _resolve_entry(raw: Mapping[str, Any], surface: str) -> Mapping[str, Any]:
    surfaces = raw["surfaces"]
    seen_aliases: List[str] = []
    name = surface
    while name in surfaces and "alias_of" in surfaces[name]:
        if name in seen_aliases:
            raise LadderConfigError(f"surface {surface!r}: alias cycle detected at {name!r}")
        seen_aliases.append(name)
        name = surfaces[name]["alias_of"]
    if name in surfaces:
        return surfaces[name]
    not_laddered = raw.get("not_laddered", {})
    if surface in not_laddered:
        raise SurfaceNotLadderedError(surface, not_laddered[surface]["reason"])
    raise LadderConfigError(
        f"surface {surface!r} is not declared in fallback-ladder.json "
        "('surfaces' or 'not_laddered')"
    )


def declared_surfaces(path: Optional[str] = None) -> List[str]:
    """Every surface name that resolves to a real (non-alias) ladder entry."""
    raw = validate_ladder_file(path)
    return sorted(
        name for name, entry in raw["surfaces"].items() if "alias_of" not in entry
    )


def get_surface(surface: str, path: Optional[str] = None) -> Mapping[str, Any]:
    """Return the fully resolved (alias-followed) declaration for ``surface``."""
    return _resolve_entry(validate_ladder_file(path), surface)


def get_ladder(surface: str, path: Optional[str] = None) -> Tuple[str, ...]:
    """Return the declared attempt order for ``surface`` as a tuple.

    Resolves aliases (e.g. "funnel" -> "page"). Raises
    :class:`SurfaceNotLadderedError` for a documented single-lane surface
    (see ``not_laddered``), or :class:`LadderConfigError` for a name that is
    neither laddered nor documented as single-lane."""
    return tuple(get_surface(surface, path=path)["order"])


def declared_operations(surface: str, path: Optional[str] = None) -> Tuple[str, ...]:
    """Operation ids the surface declares it can complete (may be empty)."""
    return tuple(get_surface(surface, path=path).get("operations", ()))


def rung_kind(surface: str, transport: str, path: Optional[str] = None) -> str:
    """``operation`` or ``prerequisite`` for one rung of one surface."""
    entry = get_surface(surface, path=path)
    return str((entry.get("rungs", {}) or {}).get(transport, {}).get("kind", "operation"))


# ── flag ────────────────────────────────────────────────────────────────────

def ladder_enablement(env: Optional[Mapping[str, str]] = None) -> str:
    """Explicit enablement state: ``default-on`` | ``explicit-on`` |
    ``explicit-off``. An unrecognized value raises instead of being guessed."""
    env = env if env is not None else os.environ
    raw = env.get(FLAG_ENV)
    if raw is None or str(raw).strip() == "":
        return ENABLE_DEFAULT_ON
    norm = str(raw).strip().lower()
    if norm in _FALSEY:
        return ENABLE_EXPLICIT_OFF
    if norm in _TRUTHY:
        return ENABLE_EXPLICIT_ON
    raise LadderConfigError(
        f"{FLAG_ENV}={raw!r} is not an explicit switch value "
        f"(on: {sorted(_TRUTHY)}; off: {sorted(_FALSEY)}; unset = full ladder on)"
    )


def ladder_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True unless the caller explicitly switched the full ladder OFF.

    Failover is ON by default; ``GHL_FALLBACK_LADDER=0`` is the deliberate
    single-rung revert. The expanded ladder can no longer be silently off.
    """
    return ladder_enablement(env) != ENABLE_EXPLICIT_OFF


# ── result types ────────────────────────────────────────────────────────────

@dataclass
class RunContext:
    """The logical run preserved across every fallback rung."""
    run_id: str
    surface: str
    operation: str
    tenant_location_id: Optional[str] = None
    native_object_ids: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "surface": self.surface,
            "operation": self.operation,
            "tenant_location_id": self.tenant_location_id,
            "native_object_ids": dict(self.native_object_ids),
        }


@dataclass
class RungAttempt:
    transport: str
    kind: str = "operation"
    ok: Any = False
    status: str = CLASS_FAILED
    code: Optional[str] = None
    detail: str = ""
    operation: Optional[str] = None
    operation_complete: Any = False
    prerequisite_ready: Any = False
    partial: Any = False
    location_id: Optional[str] = None
    run_id: Optional[str] = None
    native_ids: Dict[str, str] = field(default_factory=dict)
    dom_epoch: Any = None
    context_ok: bool = True

    def to_dict(self) -> dict:
        return {
            "transport": self.transport,
            "kind": self.kind,
            "ok": self.ok,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "operation": self.operation,
            "operation_complete": self.operation_complete,
            "prerequisite_ready": self.prerequisite_ready,
            "partial": self.partial,
            "location_id": self.location_id,
            "run_id": self.run_id,
            "native_ids": dict(self.native_ids),
            "dom_epoch": self.dom_epoch,
            "context_ok": self.context_ok,
        }


@dataclass
class LadderResult:
    surface: str
    order: Tuple[str, ...]
    operation: str
    operation_scope: str = "surface"
    attempts: List[RungAttempt] = field(default_factory=list)
    operation_complete: bool = False
    succeeded_rung: Optional[str] = None
    decision: str = "PARKED"  # "SUCCESS" | "PARKED"
    enablement: str = ENABLE_DEFAULT_ON
    ladder_active: bool = False
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    native_object_ids: Dict[str, str] = field(default_factory=dict)
    incomplete_operation: Optional[str] = None
    location_required: bool = False
    location_bound: bool = True
    warnings: List[str] = field(default_factory=list)
    decided_at: str = field(default_factory=_now)
    # S06-08 tenant contract (additive): the location the run was gated for,
    # and the location a rung's read-back observed, when either is known.
    expected_location_id: Optional[str] = None
    observed_location_id: Optional[str] = None

    @property
    def ok(self) -> bool:
        """Backward-compatible alias for ``operation_complete`` — never a
        truthy "something worked" flag."""
        return self.operation_complete

    def to_dict(self) -> dict:
        return {
            "surface": self.surface,
            "order": list(self.order),
            "operation": self.operation,
            "operation_scope": self.operation_scope,
            "attempts": [a.to_dict() for a in self.attempts],
            "ok": self.operation_complete,
            "operation_complete": self.operation_complete,
            "succeeded_rung": self.succeeded_rung,
            "decision": self.decision,
            "enablement": self.enablement,
            "ladder_active": self.ladder_active,
            "run_id": self.run_id,
            "native_object_ids": dict(self.native_object_ids),
            "incomplete_operation": self.incomplete_operation,
            "location_required": self.location_required,
            "location_bound": self.location_bound,
            "warnings": list(self.warnings),
            "decided_at": self.decided_at,
            **ghl_evidence.tenant_fields(
                self.expected_location_id, self.observed_location_id),
        }


def write_ladder_receipt(result: LadderResult, receipt_path: str, *,
                         secret_values: Any = None) -> None:
    """Persist ``result`` as a JSON receipt. Called on BOTH outcomes — a
    completing rung and an all-rungs-fail PARKED close — so success is always
    explicitly recorded (never silent) and failure is always fail-closed
    (never a silent no-op).

    S06-08: this is a no-secret sink: rung ``detail`` strings are free-form
    caller text, so the record passes through the evidence scrubber before
    write and the redaction count is stamped as ``redactions``. The write
    stays a PLAIN in-place write (its historical class, named honestly per
    prep R1) and gains the explicit 0600 mode (Q4)."""
    payload, redactions = ghl_evidence.EvidenceScrubber(
        secret_values).scrub_obj(result.to_dict())
    payload["redactions"] = int(payload.get("redactions") or 0) + redactions
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    ghl_evidence.write_text_private(receipt_path, text)


# ── the ladder runner ──────────────────────────────────────────────────────

def _require_bool_field(outcome: Mapping[str, Any], field_name: str,
                        transport: str, surface: str) -> Any:
    """Return ``outcome[field]`` only when it is a boolean; ``None`` when the
    key is absent. A truthy non-boolean is a wiring bug, never a pass."""
    if field_name not in outcome:
        return None
    value = outcome[field_name]
    if not isinstance(value, bool):
        raise LadderRungError(
            f"rung {transport!r} for surface {surface!r} returned "
            f"{field_name}={value!r} ({type(value).__name__}), not a boolean — "
            "refusing to treat a truthy value as success"
        )
    return value


def _mismatch(expected: Optional[str], observed: Optional[str]) -> bool:
    return bool(expected) and bool(observed) and expected != observed


def _run_rung(
    surface: str,
    transport: str,
    kind: str,
    callable_: Callable[[], Mapping[str, Any]],
    *,
    context: RunContext,
    entry: Mapping[str, Any],
    observed_location_id: Optional[str],
    warnings: List[str],
    require_operation_named: bool,
) -> RungAttempt:
    """Call one rung and classify its outcome. Never fabricates a pass."""
    try:
        outcome = callable_()
    except Exception as exc:  # noqa: BLE001 — deliberately re-raised, typed
        raise LadderRungError(
            f"rung {transport!r} for surface {surface!r} raised instead of "
            f"returning a taxonomy-tagged dict (rung callables must never raise, "
            f"per the smoke_first() convention): {exc!r}"
        ) from exc

    if not isinstance(outcome, Mapping):
        raise LadderRungError(
            f"rung {transport!r} for surface {surface!r} returned "
            f"{type(outcome).__name__!r}, not a mapping"
        )

    ok = _require_bool_field(outcome, "ok", transport, surface)
    if ok is None:
        raise LadderRungError(
            f"rung {transport!r} for surface {surface!r} returned no boolean 'ok' — "
            "a rung must state success or failure"
        )

    attempt = RungAttempt(
        transport=transport,
        kind=kind,
        ok=ok,
        operation=outcome.get("operation") if isinstance(outcome.get("operation"), str) else None,
        operation_complete=_require_bool_field(
            outcome, "operation_complete", transport, surface) is True,
        prerequisite_ready=_require_bool_field(
            outcome, "prerequisite_ready", transport, surface) is True,
        partial=_require_bool_field(outcome, "partial", transport, surface) is True,
        location_id=str(outcome.get("location_id") or outcome.get("observed_location_id") or "")
        or None,
        run_id=str(outcome.get("run_id") or "") or None,
        dom_epoch=outcome.get("dom_epoch"),
        detail=str(outcome.get("detail", "")),
    )
    native = outcome.get("native_ids")
    if isinstance(native, Mapping):
        attempt.native_ids = {str(k): str(v) for k, v in native.items()}

    if not ok:
        code = outcome.get("code")
        if code not in TAXONOMY_TAGS:
            raise LadderRungError(
                f"rung {transport!r} for surface {surface!r} failed with "
                f"unrecognized taxonomy code {code!r} (must be one of {TAXONOMY_TAGS}) — "
                "refusing to write a fabricated receipt for it"
            )
        attempt.code = str(code)
        attempt.status = CLASS_FAILED
        return attempt

    # ── ok is literally True: now decide whether it COMPLETED the operation ──
    # A prerequisite rung can never complete an operation, whatever it claims.
    if kind == "prerequisite":
        if attempt.operation_complete:
            warnings.append(
                f"rung {transport!r} is declared prerequisite but claimed "
                f"operation_complete for {context.operation!r}; recorded as "
                "prerequisite_ready, never as completion"
            )
        # ``ok: True`` from a declared prerequisite means the prerequisite
        # work succeeded; record that as its own state. A rung that reports
        # neither prerequisite_ready nor operation_complete has not said what
        # it finished, so it is only ``partial`` — never completion.
        if attempt.prerequisite_ready or attempt.operation_complete:
            attempt.prerequisite_ready = True
            attempt.status = CLASS_PREREQUISITE
        else:
            attempt.status = CLASS_PARTIAL
            warnings.append(
                f"rung {transport!r} is declared prerequisite but reported "
                "neither prerequisite_ready nor operation_complete; recorded "
                "as partial, not as preparation"
            )
        attempt.code = None
        return attempt

    # The rung must name the SAME operation the caller requested. When the
    # surface declares operation ids, a completion claim that does not name
    # one has not shown WHICH operation it finished.
    if require_operation_named and attempt.operation is None:
        attempt.status = CLASS_PARTIAL
        attempt.code = None
        attempt.context_ok = False
        warnings.append(
            f"rung {transport!r} reported completion without naming "
            f"{context.operation!r}; recorded as partial, not completion"
        )
        return attempt
    if attempt.operation is not None and attempt.operation != context.operation:
        attempt.status = CLASS_PARTIAL
        attempt.code = None
        attempt.context_ok = False
        warnings.append(
            f"rung {transport!r} completed {attempt.operation!r}, not the requested "
            f"{context.operation!r}; recorded as partial, not completion"
        )
        return attempt

    # A logical run may not silently change under a fallback.
    if attempt.run_id is not None and attempt.run_id != context.run_id:
        attempt.status = CLASS_FAILED
        attempt.code = "VERIFY-FAIL"
        attempt.context_ok = False
        attempt.detail = (
            f"run_id {attempt.run_id!r} does not match the logical run "
            f"{context.run_id!r}"
        )
        return attempt

    # Tenant binding: a cross-tenant read-back is a contradiction, never a create.
    expected = context.tenant_location_id
    if _mismatch(expected, attempt.location_id):
        attempt.status = CLASS_FAILED
        attempt.code = "VERIFY-FAIL"
        attempt.context_ok = False
        attempt.detail = (
            f"observed location {attempt.location_id!r} does not match the gated "
            f"tenant {expected!r}"
        )
        return attempt
    if _mismatch(expected, observed_location_id) and attempt.location_id is None:
        attempt.status = CLASS_FAILED
        attempt.code = "VERIFY-FAIL"
        attempt.context_ok = False
        attempt.detail = (
            f"a prior rung observed location {observed_location_id!r} but the gated "
            f"tenant is {expected!r}"
        )
        return attempt

    # A location-required surface is not complete without a bound location.
    location = entry.get("location") or {}
    if location.get("required") and not (expected or attempt.location_id):
        attempt.status = CLASS_PARTIAL
        attempt.code = None
        attempt.detail = (
            "operation finished without a connected location; a location-required "
            f"surface needs {location.get('carrier')!r} bound"
        )
        warnings.append(attempt.detail)
        return attempt

    if attempt.operation_complete:
        attempt.status = CLASS_COMPLETE
        return attempt

    attempt.status = CLASS_PREREQUISITE if attempt.prerequisite_ready else CLASS_PARTIAL
    return attempt


def run_ladder(
    surface: str,
    rungs: Mapping[str, Callable[[], Mapping[str, Any]]],
    *,
    operation: Optional[str] = None,
    path: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    receipt_path: Optional[str] = None,
    expected_location_id: Optional[str] = None,
    observed_location_id: Optional[str] = None,
    secret_values: Any = None,
    run_id: Optional[str] = None,
    native_object_ids: Optional[Mapping[str, str]] = None,
    enter_hooks: Optional[Mapping[str, Callable[[RunContext], Mapping[str, Any]]]] = None,
) -> LadderResult:
    """Walk ``surface``'s declared transport order for ONE requested operation,
    calling ``rungs[transport]()`` for each, stopping at the first rung that
    COMPLETES that same operation.

    - Enablement: unset -> full ladder (failover on); explicit ``0``/false/off
      -> only the first operation rung (the deliberate single-rung revert).
    - A surface that declares several operations requires ``operation``; the
      ladder refuses to guess a surface-wide route.
    - Every failed rung MUST return a code in :data:`TAXONOMY_TAGS`; anything
      else (a raise, a missing code, an unrecognized code, a non-boolean
      ``ok``) raises :class:`LadderRungError` rather than being fabricated
      into a receipt.
    - ``ok: true`` alone is NOT success. The rung must also report
      ``operation_complete: true`` for the requested ``operation``. A
      prerequisite rung, a partial rung, a different operation, a changed
      logical run, or a cross-tenant read-back is recorded as its own state
      and the ladder continues.
    - ``run_id`` / ``native_object_ids`` / the still-incomplete operation are
      preserved on the result and every rung attempt, so a fallback continues
      the SAME logical run rather than starting another one.
    - A browser rung reached as a FALLBACK on a surface with
      ``dom_refresh: true`` requires an ``enter_hooks["browser"]`` that
      re-establishes the page/context and returns a ``dom_epoch``; a stale
      DOM reference is never assumed. The primary browser rung, which
      establishes the session itself, needs no hook.
    - Returns a fail-closed ``decision="PARKED"`` result when no attempted
      rung completed the operation.
    """
    entry = get_surface(surface, path=path)
    declared_order = tuple(entry["order"])
    declared_ops = tuple(entry.get("operations", ()))
    enablement = ladder_enablement(env)
    active = enablement != ENABLE_EXPLICIT_OFF

    # ── operation selection is per operation, not a blanket surface claim ──
    if operation is None:
        if len(declared_ops) == 1:
            operation = declared_ops[0]
        elif declared_ops:
            raise LadderConfigError(
                f"surface {surface!r} declares {len(declared_ops)} operations "
                f"({list(declared_ops)}); name the operation, because a "
                "surface-wide route would be the blanket claim this ladder "
                "exists to prevent"
            )
        else:
            operation = surface
    scope = "operation" if operation in declared_ops else "surface"
    if declared_ops and operation not in declared_ops:
        raise LadderConfigError(
            f"surface {surface!r} does not declare operation {operation!r} "
            f"(declared: {list(declared_ops)}) — refusing a blanket route for an "
            "undeclared operation"
        )

    location = entry.get("location") or {}
    location_required = bool(location.get("required"))
    context = RunContext(
        run_id=run_id or uuid.uuid4().hex[:12],
        surface=surface,
        operation=operation,
        tenant_location_id=expected_location_id,
        native_object_ids={str(k): str(v) for k, v in (native_object_ids or {}).items()},
    )
    hooks = dict(enter_hooks or {})

    # Classify each declared rung so the enablement filter keeps the first
    # OPERATION rung (a prerequisite alone can never be "the one rung").
    kinds = {
        transport: str((entry.get("rungs", {}) or {}).get(transport, {}).get(
            "kind", "operation"))
        for transport in declared_order
    }
    if active:
        effective_order = declared_order
    else:
        operation_rungs = [t for t in declared_order if kinds[t] == "operation"]
        effective_order = tuple(operation_rungs[:1]) or declared_order[:1]

    attempts: List[RungAttempt] = []
    warnings: List[str] = []
    succeeded_rung: Optional[str] = None
    dom_epoch: Any = None
    observed = observed_location_id
    attempted_transports: List[str] = []

    for transport in effective_order:
        if transport not in rungs:
            raise LadderConfigError(
                f"surface {surface!r} declares rung {transport!r} but no callable "
                "was provided to run_ladder(rungs=...)"
            )

        # ── handoff: never assume a shared session or a live DOM reference ──
        hook = hooks.get(transport)
        is_fallback = bool(attempted_transports)
        if (transport == "browser" and is_fallback
                and entry.get("dom_refresh", False) and hook is None):
            raise LadderConfigError(
                f"surface {surface!r} reaches the browser rung as a FALLBACK and "
                "requires a DOM refresh; supply enter_hooks={'browser': fn} that "
                "re-establishes the page/context and returns {'dom_epoch': ...}"
            )
        if hook is not None:
            try:
                prepared = hook(context)
            except Exception as exc:  # noqa: BLE001 — typed re-raise
                raise LadderRungError(
                    f"enter hook for rung {transport!r} on surface {surface!r} raised: "
                    f"{exc!r}"
                ) from exc
            if not isinstance(prepared, Mapping):
                raise LadderRungError(
                    f"enter hook for rung {transport!r} on surface {surface!r} returned "
                    f"{type(prepared).__name__!r}, not a mapping"
                )
            if prepared.get("ready") is False:
                code = prepared.get("code")
                if code not in TAXONOMY_TAGS:
                    raise LadderRungError(
                        f"enter hook for rung {transport!r} on surface {surface!r} "
                        f"refused with unrecognized taxonomy code {code!r}"
                    )
                attempts.append(RungAttempt(
                    transport=transport,
                    kind=kinds[transport],
                    ok=False,
                    status=CLASS_FAILED,
                    code=str(code),
                    detail=str(prepared.get("detail", "enter hook refused")),
                    dom_epoch=prepared.get("dom_epoch"),
                ))
                attempted_transports.append(transport)
                continue
            if prepared.get("dom_epoch") is not None:
                dom_epoch = prepared.get("dom_epoch")
            loc = prepared.get("location_id")
            if loc:
                context.tenant_location_id = context.tenant_location_id or str(loc)

        attempt = _run_rung(
            surface,
            transport,
            kinds[transport],
            rungs[transport],
            context=context,
            entry=entry,
            observed_location_id=observed,
            warnings=warnings,
            require_operation_named=(scope == "operation"),
        )
        if attempt.dom_epoch is None and transport == "browser":
            attempt.dom_epoch = dom_epoch
        if attempt.location_id is not None:
            observed = attempt.location_id
        context.native_object_ids.update(attempt.native_ids)
        if attempt.run_id:
            context.run_id = context.run_id or attempt.run_id
        attempts.append(attempt)
        attempted_transports.append(transport)

        if attempt.status == CLASS_COMPLETE:
            succeeded_rung = transport
            break

        if attempt.status == CLASS_FAILED:
            continue
        # prerequisite_ready / partial: recorded, then the ladder continues.

    complete = succeeded_rung is not None
    location_bound = bool(expected_location_id or observed) if location_required else True
    if complete and location_required and not location_bound:
        complete = False
        succeeded_rung = None
        warnings.append("completion refused: location-required surface with no bound location")

    result = LadderResult(
        surface=surface,
        order=declared_order,
        operation=operation,
        operation_scope=scope,
        attempts=attempts,
        operation_complete=complete,
        succeeded_rung=succeeded_rung,
        decision="SUCCESS" if complete else "PARKED",
        enablement=enablement,
        ladder_active=active,
        run_id=context.run_id,
        native_object_ids=dict(context.native_object_ids),
        incomplete_operation=None if complete else operation,
        location_required=location_required,
        location_bound=location_bound if location_required else True,
        warnings=warnings,
        expected_location_id=expected_location_id,
        observed_location_id=observed,
    )

    if receipt_path:
        write_ladder_receipt(result, receipt_path, secret_values=secret_values)

    return result


if __name__ == "__main__":
    # Self-test: validate the shipped config and print the declared ladder
    # for every surface — no network, no browser, exits non-zero on any
    # LadderConfigError.
    try:
        for name in declared_surfaces():
            entry = get_surface(name)
            marks = " ".join(
                f"{t}{'*' if rung_kind(name, t) == 'prerequisite' else ''}"
                for t in get_ladder(name)
            )
            ops = ", ".join(entry.get("operations", ())) or "surface-scoped"
            print(f"{name}: {marks}  [{ops}]")
        print("(* = prerequisite-only rung; cannot complete an operation)")
        print(f"enablement when {FLAG_ENV} is unset: {ladder_enablement({})}")
        print("OK: fallback-ladder.json is structurally valid")
    except LadderConfigError as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)

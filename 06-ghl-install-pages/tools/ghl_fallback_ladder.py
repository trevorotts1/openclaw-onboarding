#!/usr/bin/env python3
"""ghl_fallback_ladder.py — the single unified browser->API->MCP fallback ladder
across Skill 6 build surfaces ("inability to fail"), now carrying ONE requested
operation end to end (W3 connection 7).

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

WHAT CHANGED (W3 connection 7 — "no prerequisite rung may report the task done")
--------------------------------------------------------------------------------
The old runner treated any truthy ``ok`` as the whole task finishing. A rung that
had merely opened a browser, prepared auth or snapshotted a page could therefore
report SUCCESS for an operation it never performed. That is the exact failure the
ladder was built to prevent, one level up. The contract is now:

* ``ok`` must be the BOOLEAN ``True``. ``1``, ``"true"`` and friends are refused
  loudly (a non-boolean success is not a success).
* A completed rung MUST also report ``operation_complete is True`` AND name the
  SAME operation that was requested. ``ok=True`` without that pair raises
  :class:`LadderRungError`; the runner never invents the missing half.
* ``prerequisite_ready`` and ``partial`` are FIRST-CLASS, DISTINCT states: the
  rung reports progress, the ladder records it, and the walk continues. Neither
  can set ``result.ok``, ``result.decision="SUCCESS"`` or ``succeeded_rung``.
* A browser rung claiming completion must report ``references_fresh is True``:
  DOM refs are refreshed for this invocation, never inherited from a session it
  merely assumes is shared. ``references_reused is True`` is refused.
* Cleanup travels with the outcome. A rung that reported ``owned_sessions`` must
  release them (page/context/session/process) on completion, failure or
  cancellation; a release of a session it did not own, or ``closed_all``, is
  refused outright — the ladder never closes a user's unrelated session.
* The logical run id, the connected location, the native object ids and the name
  of the still-incomplete operation are carried across every rung and stamped on
  the receipt, so a fallback hand-off cannot lose which tenant or which object
  the work belonged to.

FALLBACK ENABLEMENT IS EXPLICIT
-------------------------------
``GHL_FALLBACK_LADDER`` defaults ON: an unsupported API/MCP operation must reach
the real browser rung without an operator remembering to flip a flag. The switch
is read as three explicit states:

* unset / empty  -> ``default-on``: the full declared ladder runs.
* ``1``/``true``/``yes``/``on`` -> ``explicit-on`` (identical behaviour).
* ``0``/``false``/``no``/``off`` -> ``explicit-off``: ONLY the first declared
  operation rung is attempted. This is the deliberate single-rung revert, the
  pre-ladder single-method behavior.
* anything else -> :class:`LadderConfigError`. An unrecognized value is not
  guessed into on or off.

The chosen enablement is stamped on every receipt (``enablement``).

THIS MODULE IS THE RUNNER, NOT A NEW BUILDER
---------------------------------------------
``run_ladder()`` takes the SURFACE's already-existing per-transport callables
(the caller wires ``ghl_rest_canvas`` / ``ghl_iframe_drag.smoke_first`` /
a Skill-44-MCP call, etc. into a ``{"api": fn, "browser": fn, "mcp": fn}``
mapping) and walks them in the order declared in ``fallback-ladder.json``.
This module invents NO new build logic. It selects the capable transport for
the REQUESTED OPERATION at the CONNECTED LOCATION, not a blanket transport
for the surface, and it preserves the logical run, the tenant, the native
object ids and the still-incomplete operation across every fallback. It is a
thin, generic, declarative overlay.

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

HANDOFF ACROSS RUNGS (DOM + SESSION)
------------------------------------
A fallback rung must not assume it shares a browser session with the rung
that failed. For every surface that drives a browser, the config declares
``dom_refresh: true`` and the caller SHOULD supply an enter hook for the
browser transport (``enter_hooks={"browser": fn}``) when that browser rung
is reached as a FALLBACK — after a prior rung has already run. The hook
re-establishes the page/context, refreshes DOM references, and returns at
least a ``dom_epoch``; the ladder records that epoch on the attempt. A
fallback browser rung with no enter hook is recorded on the receipt as a
warning (``DOM references were not refreshed``) so a caller that forgot the
hook can never mistake the walk for a refreshed session. The PRIMARY browser
rung needs no hook: it is the rung that establishes the session, so there is
no failed rung to share with.

CLEANUP
-------
The ladder never opens a page, context, session or browser process, so it has
none to release. The enter hook is where a caller re-establishes state, and
the caller keeps its own ``finally`` cleanup (``browser_manager.sh`` closes
only the session it owns). A rung that reports its own ``owned_sessions``
must release them on completion, failure or cancellation; releasing a session
it did not own, or ``closed_all``, is refused.

RUNG CALLABLE CONTRACT
-----------------------
Takes either zero arguments (legacy closure) or ONE :class:`RungContext`
(``ctx.operation``, ``ctx.location_id``, ``ctx.run_id``, ``ctx.native_object_ids``,
``ctx.incomplete_operation``, ``ctx.transport``, ``ctx.attempt_index``). Returns
a mapping and NEVER raises (mirrors ``ghl_iframe_drag.smoke_first``); a raise is
treated as a wiring bug (an uncoded failure this module refuses to silently
swallow or fabricate a taxonomy tag for) and surfaces as :class:`LadderRungError`.

    complete:            {"ok": True, "operation": <same id>,
                          "operation_complete": True,
                          "status": "operation_complete",
                          "references_fresh": True,   # browser rungs
                          "owned_sessions": [...], "cleanup": {...}}
    prerequisite only:   {"ok": True, "operation": <same id>,
                          "operation_complete": False,
                          "prerequisite_ready": True,
                          "status": "prerequisite_ready"}
    partial:             {"ok": True, "operation_complete": False,
                          "partial": True, "status": "partial"}
    failed:              {"ok": False, "code": <TAXONOMY_TAGS>, "detail": <str>}

TAXONOMY IS THE BOARD'S, NOT A NEW ONE (single source of truth)
------------------------------------------------------------------
Failure codes are ``cc_board.py``'s existing ``_CC_BLOCK_REASONS`` tuple,
imported directly rather than re-declared, so the two can never drift apart.
"""

from __future__ import annotations

import inspect
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
#: The same three rung-outcome states, under the names the W3 runner uses.
STATE_COMPLETE = "operation_complete"
STATE_PREREQUISITE = "prerequisite_ready"
STATE_PARTIAL = "partial"
STATE_FAILED = "failed"
_COMPLETE_STATUSES = frozenset({STATE_COMPLETE, "complete", "completed"})
_PREREQUISITE_STATUSES = frozenset({STATE_PREREQUISITE, "prerequisite", "ready"})


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
    the config's ``not_laddered`` map)."""

    def __init__(self, surface: str, reason: str) -> None:
        self.surface = surface
        self.reason = reason
        super().__init__(
            f"surface {surface!r} is not laddered (single real transport today): {reason}"
        )


class LadderRungError(RuntimeError):
    """Raised when a rung callable breaks its contract: it raises, returns a
    non-mapping or a non-taxonomy code, claims a non-boolean success, claims
    completion of a different operation, claims completion without
    ``operation_complete``, reuses DOM refs, or reports cleanup that is not its
    own. This module refuses to fabricate a receipt for an uncoded, ill-typed or
    otherwise contradictory outcome."""


# ── the requested operation (preserved across every fallback) ─────────────────

@dataclass(frozen=True)
class LadderRequest:
    """One requested operation, carried across every rung unchanged."""

    operation: str
    surface: str
    location_id: Optional[str] = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    native_object_ids: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.operation, str) or not self.operation.strip():
            raise LadderConfigError(
                "a requested operation id is required: a rung cannot prove an "
                "unnamed operation complete"
            )
        if not isinstance(self.surface, str) or not self.surface.strip():
            raise LadderConfigError("a ladder surface is required")
        if self.location_id is not None and (
            not isinstance(self.location_id, str) or not self.location_id.strip()
        ):
            raise LadderConfigError(
                "location_id must be a non-empty string when supplied"
            )
        for key, value in dict(self.native_object_ids or {}).items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise LadderConfigError(
                    "native_object_ids must map string keys to string values"
                )

    def to_dict(self) -> dict:
        return {
            "operation": self.operation,
            "surface": self.surface,
            "locationId": self.location_id,
            "runId": self.run_id,
            "nativeObjectIds": dict(self.native_object_ids),
        }


@dataclass(frozen=True)
class RungContext:
    """What a rung callable receives. The run id and the incomplete operation
    are identical across rungs by construction — a fallback never re-brands the
    work as a different run or a different operation."""

    request: LadderRequest
    transport: str
    attempt_index: int
    incomplete_operation: bool

    @property
    def operation(self) -> str:
        return self.request.operation

    @property
    def surface(self) -> str:
        return self.request.surface

    @property
    def location_id(self) -> Optional[str]:
        return self.request.location_id

    @property
    def run_id(self) -> str:
        return self.request.run_id

    @property
    def native_object_ids(self) -> Mapping[str, str]:
        return self.request.native_object_ids

    def to_dict(self) -> dict:
        return {
            "transport": self.transport,
            "attemptIndex": self.attempt_index,
            "incompleteOperation": self.incomplete_operation,
            **self.request.to_dict(),
        }


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
    :class:`LadderConfigError` on any malformed entry."""
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

    prefixes = raw.get("operation_prefixes", {})
    if not isinstance(prefixes, dict):
        raise LadderConfigError(
            "fallback-ladder.json: 'operation_prefixes' must be an object when present"
        )
    for prefix, surface in prefixes.items():
        if not isinstance(prefix, str) or not prefix.strip():
            raise LadderConfigError("operation_prefixes: prefix keys must be non-empty")
        if surface not in surfaces:
            raise LadderConfigError(
                f"operation_prefixes {prefix!r}: maps to undeclared surface {surface!r}"
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


def _resolve_alias(name: str, surfaces: Mapping[str, Any]) -> str:
    seen_aliases: List[str] = []
    while name in surfaces and "alias_of" in surfaces[name]:
        if name in seen_aliases:
            raise LadderConfigError(f"surface {name!r}: alias cycle detected")
        seen_aliases.append(name)
        name = surfaces[name]["alias_of"]
    return name


def surface_for_operation(operation_id: str, path: Optional[str] = None) -> Optional[str]:
    """The declared ladder surface for an operation id, matched on the LONGEST
    declared ``operation_prefixes`` entry.

    Returns ``None`` when no prefix is declared for the operation — an honest
    "this operation has no declared ladder surface", never a guessed surface.
    """
    if not isinstance(operation_id, str) or not operation_id.strip():
        return None
    raw = validate_ladder_file(path)
    prefixes = raw.get("operation_prefixes", {}) or {}
    best: Optional[str] = None
    best_len = -1
    for prefix, surface in prefixes.items():
        if operation_id == prefix or operation_id.startswith(prefix + "."):
            if len(prefix) > best_len:
                best, best_len = surface, len(prefix)
    if best is None:
        return None
    return _resolve_alias(best, raw["surfaces"])


def operation_capability(
    operation_id: str,
    *,
    declared_transports: Tuple[str, ...] = (),
    path: Optional[str] = None,
) -> Dict[str, Any]:
    """The operation -> capability mapping for ONE operation.

    Composes the declared ladder surface with the caller's declared transports
    (Skill 44's frozen registry supplies those per operation). A transport that
    is declared but has no wired rung for the surface is reported as
    ``unwired`` — never as available.
    """
    surface = surface_for_operation(operation_id, path=path)
    record: Dict[str, Any] = {
        "operation": operation_id,
        "surface": surface,
        "declaredTransports": list(declared_transports),
        "ladderOrder": [],
        "routedTransports": [],
        "unwiredTransports": [],
        "browserRouteRequired": False,
        "operationComplete": False,
    }
    if surface is None:
        return record
    try:
        order = get_ladder(surface, path=path)
    except (LadderConfigError, SurfaceNotLadderedError):
        return record
    record["ladderOrder"] = list(order)
    record["routedTransports"] = [t for t in declared_transports if t in order]
    record["unwiredTransports"] = [t for t in declared_transports if t not in order]
    if declared_transports and "browser" not in declared_transports and "browser" in order:
        # The API/MCP route the caller declared is not available down this
        # ladder: the real browser rung is the route that must carry it.
        record["browserRouteRequired"] = True
    return record


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
    """True unless the ladder is explicitly switched OFF.

    Default ON (W3 connection 7): an unsupported API/MCP operation must reach the
    real browser rung without an operator remembering a flag. Only an explicit
    falsey value (``0``/``false``/``no``/``off``) is the documented revert to
    first-rung-only behavior; an unrecognized value raises rather than guessing.
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
    ok: Any = False             # True ONLY for operation_complete
    code: Optional[str] = None
    detail: str = ""
    kind: str = "operation"
    status: str = CLASS_FAILED
    state: str = STATE_FAILED
    operation: Optional[str] = None
    operation_complete: Any = False
    prerequisite_ready: Any = False
    partial: Any = False
    location_id: Optional[str] = None
    run_id: Optional[str] = None
    native_ids: Dict[str, str] = field(default_factory=dict)
    dom_epoch: Any = None
    context_ok: bool = True
    references_fresh: Optional[bool] = None
    cleanup: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "transport": self.transport,
            "kind": self.kind,
            "ok": self.ok,
            "status": self.status,
            "state": self.state,
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
            "references_fresh": self.references_fresh,
            "cleanup": dict(self.cleanup),
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
    # W3 connection 7: the requested operation survives every fallback.
    operation: Optional[str] = None
    incomplete_operation: Optional[str] = None
    native_object_ids: Mapping[str, str] = field(default_factory=dict)
    prerequisite_rungs: List[str] = field(default_factory=list)
    cleanup: List[Mapping[str, Any]] = field(default_factory=list)
    state: Mapping[str, Any] = field(default_factory=dict)

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
            "operation": self.operation,
            "incomplete_operation": self.incomplete_operation,
            "native_object_ids": dict(self.native_object_ids),
            "prerequisite_rungs": list(self.prerequisite_rungs),
            "cleanup": [dict(c) for c in self.cleanup],
            "state": dict(self.state),
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
    write and the redaction count is stamped as ``redactions``."""
    payload, redactions = ghl_evidence.EvidenceScrubber(
        secret_values).scrub_obj(result.to_dict())
    payload["redactions"] = int(payload.get("redactions") or 0) + redactions
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    ghl_evidence.write_text_private(receipt_path, text)


# ── outcome validation ──────────────────────────────────────────────────────

def _refuse(transport: str, request: LadderRequest, message: str) -> LadderRungError:
    return LadderRungError(
        f"rung {transport!r} for surface {request.surface!r} "
        f"(operation {request.operation!r}): {message}"
    )


def _check_cleanup(
    transport: str, request: LadderRequest, outcome: Mapping[str, Any]
) -> Dict[str, Any]:
    """Enforce the release contract on EVERY outcome, complete or not.

    A rung that opened a page / context / session / process must say what it
    released. ``closed_all`` and releases of sessions the rung did not own are
    refused: the ladder never closes a user's unrelated session.
    """
    owned = [str(s) for s in (outcome.get("owned_sessions") or ())]
    cleanup = outcome.get("cleanup")
    if cleanup is None:
        if owned:
            raise _refuse(
                transport, request,
                f"reported owned_sessions {owned} but no cleanup record — "
                "pages/contexts/sessions must be released on completion, failure "
                "or cancellation",
            )
        if outcome.get("cleanup_required") is True:
            raise _refuse(
                transport, request,
                "'cleanup_required' is true but no cleanup record was returned",
            )
        return {}
    if not isinstance(cleanup, Mapping):
        raise _refuse(transport, request, "'cleanup' must be a mapping")
    if cleanup.get("closed_all") is True:
        raise _refuse(
            transport, request,
            "'cleanup.closed_all' is forbidden — closing every session would "
            "close a user's unrelated session",
        )
    released = [str(s) for s in (cleanup.get("released") or ())]
    foreign = [s for s in released if s not in owned]
    if foreign:
        raise _refuse(
            transport, request,
            f"cleanup released session(s) {foreign} this rung never owned "
            f"(owned_sessions={owned})",
        )
    return dict(cleanup)


def _classify_outcome(
    transport: str, request: LadderRequest, outcome: Mapping[str, Any]
) -> Tuple[str, Optional[str], str]:
    """Return ``(state, taxonomy_code, detail)`` for one rung outcome.

    ``state`` is one of STATE_COMPLETE / STATE_PREREQUISITE / STATE_PARTIAL /
    STATE_FAILED. Raises :class:`LadderRungError` for any unstatable claim.
    """
    detail = str(outcome.get("detail", ""))

    if outcome.get("references_reused") is True:
        raise _refuse(
            transport, request,
            "declared references_reused=true — a rung must refresh DOM "
            "references for its own invocation, never assume a shared session",
        )

    ok = outcome.get("ok")
    if not isinstance(ok, bool):
        # "ok": 1 / "true" / "yes" are not successes. Only boolean true is.
        raise _refuse(
            transport, request,
            f"'ok' must be the boolean true or false, got {type(ok).__name__} "
            f"{ok!r} — refusing to read a truthy value as success",
        )

    if ok is False:
        code = outcome.get("code")
        if code not in TAXONOMY_TAGS:
            raise _refuse(
                transport, request,
                f"failed with unrecognized taxonomy code {code!r} "
                f"(must be one of {TAXONOMY_TAGS}) — refusing to write a "
                "fabricated receipt for it",
            )
        return STATE_FAILED, str(code), detail

    # ok is True from here on: it must describe WHICH operation state it is.
    complete = outcome.get("operation_complete")
    if not isinstance(complete, bool):
        raise _refuse(
            transport, request,
            "'ok' is true but 'operation_complete' is absent or not a boolean — "
            "an unspecified success is exactly the prerequisite-only claim this "
            "ladder refuses",
        )

    status = outcome.get("status")
    reported_operation = outcome.get("operation")

    if complete:
        if reported_operation != request.operation:
            raise _refuse(
                transport, request,
                f"claimed completion of operation {reported_operation!r}, "
                f"but the requested operation is {request.operation!r}",
            )
        if isinstance(status, str) and status.strip().lower() not in _COMPLETE_STATUSES:
            raise _refuse(
                transport, request,
                f"operation_complete=true contradicts status {status!r}",
            )
        if outcome.get("prerequisite_ready") is True or outcome.get("partial") is True:
            raise _refuse(
                transport, request,
                "operation_complete=true cannot also be prerequisite_ready/partial",
            )
        if transport == "browser" and outcome.get("references_fresh") is not True:
            raise _refuse(
                transport, request,
                "a browser rung claiming completion must report "
                "references_fresh=true (DOM refs refreshed for this invocation)",
            )
        return STATE_COMPLETE, None, detail

    # ok True, operation_complete False: progress only, never a success.
    prerequisite = outcome.get("prerequisite_ready") is True
    partial = outcome.get("partial") is True
    if isinstance(status, str):
        lowered = status.strip().lower()
        prerequisite = prerequisite or lowered in _PREREQUISITE_STATUSES
        partial = partial or lowered == STATE_PARTIAL
    if not (prerequisite or partial):
        raise _refuse(
            transport, request,
            "'ok' is true with operation_complete=false but the outcome names "
            "neither prerequisite_ready nor partial — an unnamed non-completion "
            "is not a state this ladder will record",
        )
    if prerequisite and partial:
        raise _refuse(
            transport, request,
            "prerequisite_ready and partial are distinct states; report one",
        )
    return (STATE_PREREQUISITE if prerequisite else STATE_PARTIAL), None, detail


def _accepts_context(fn: Callable[..., Any]) -> bool:
    """True when the rung callable takes one positional argument (the context)."""
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return False
    positional = 0
    for param in sig.parameters.values():
        if param.kind is param.VAR_POSITIONAL:
            return True
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            positional += 1
    return positional >= 1


def _invoke_rung(fn: Callable[..., Any], ctx: RungContext) -> Any:
    if _accepts_context(fn):
        return fn(ctx)
    return fn()


def _coerce_request(
    surface: str,
    request: Optional[LadderRequest],
    operation: Optional[str],
    location_id: Optional[str],
    run_id: Optional[str],
    native_object_ids: Optional[Mapping[str, str]],
) -> LadderRequest:
    if request is not None:
        if not isinstance(request, LadderRequest):
            raise LadderConfigError("request must be a LadderRequest")
        if request.surface != surface:
            raise LadderConfigError(
                f"request.surface {request.surface!r} does not match the walked "
                f"surface {surface!r}"
            )
        return request
    if not operation:
        raise LadderConfigError(
            "run_ladder requires the requested operation (operation=... or "
            "request=LadderRequest(...)): a rung cannot prove an unnamed "
            "operation complete"
        )
    return LadderRequest(
        operation=operation,
        surface=surface,
        location_id=location_id,
        run_id=run_id or uuid.uuid4().hex[:12],
        native_object_ids=dict(native_object_ids or {}),
    )


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
    rungs: Mapping[str, Callable[..., Mapping[str, Any]]],
    *,
    request: Optional[LadderRequest] = None,
    operation: Optional[str] = None,
    location_id: Optional[str] = None,
    run_id: Optional[str] = None,
    native_object_ids: Optional[Mapping[str, str]] = None,
    path: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    receipt_path: Optional[str] = None,
    expected_location_id: Optional[str] = None,
    observed_location_id: Optional[str] = None,
    secret_values: Any = None,
    enter_hooks: Optional[Mapping[str, Callable[[RungContext], Mapping[str, Any]]]] = None,
) -> LadderResult:
    """Walk ``surface``'s declared transport order for ONE requested operation.

    - Ladder ON (default): every declared rung is attempted in order until one
      reports ``operation_complete`` for the SAME operation, or all are spent.
    - Ladder OFF (``GHL_FALLBACK_LADDER=0``): only the first declared OPERATION
      rung (the deliberate single-rung revert).
    - ``prerequisite_ready`` / ``partial`` outcomes are recorded and the walk
      CONTINUES. They never set ``ok``, ``decision="SUCCESS"`` or
      ``succeeded_rung``.
    - A browser rung reached as a FALLBACK on a surface with ``dom_refresh: true``
      requires an ``enter_hooks["browser"]`` that re-establishes the page/context
      and returns a ``dom_epoch``; a stale DOM reference is never assumed. The
      primary browser rung, which establishes the session itself, needs no hook.
    - Returns a fail-closed ``decision="PARKED"`` result whenever the requested
      operation was not completed — including the case where every rung merely
      got ready. ``incomplete_operation`` names the operation that is still owed.
    """
    entry = get_surface(surface, path=path)
    declared_order = get_ladder(surface, path=path)
    declared_ops = tuple(entry.get("operations", ()))
    req = _coerce_request(
        surface, request, operation, location_id, run_id, native_object_ids
    )
    enablement = ladder_enablement(env)
    active = enablement != ENABLE_EXPLICIT_OFF
    scope = "operation" if req.operation in declared_ops else "surface"
    location = entry.get("location") or {}
    location_required = bool(location.get("required"))
    hooks = dict(enter_hooks or {})
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
    prerequisite_rungs: List[str] = []
    cleanup_records: List[Mapping[str, Any]] = []
    warnings: List[str] = []
    attempted_transports: List[str] = []
    dom_epoch: Any = None
    observed = observed_location_id
    succeeded_rung: Optional[str] = None
    incomplete = False

    for index, transport in enumerate(effective_order, start=1):
        if transport not in rungs:
            raise LadderConfigError(
                f"surface {surface!r} declares rung {transport!r} but no callable "
                "was provided to run_ladder(rungs=...)"
            )
        # ── handoff: never assume a live DOM reference ──
        hook = hooks.get(transport)
        if (transport == "browser" and attempted_transports
                and entry.get("dom_refresh", False) and hook is None):
            # The surface says a fallback browser rung must re-establish the page.
            # With no hook supplied nothing here can refresh it, so the walk
            # continues and the receipt records that the DOM was not refreshed.
            warnings.append(
                f"browser rung reached as a FALLBACK on surface {surface!r} with no "
                "enter_hooks['browser']; DOM references were not refreshed")
        if hook is not None:
            ctx_hook = RungContext(
                request=req, transport=transport, attempt_index=index,
                incomplete_operation=incomplete)
            try:
                prepared = hook(ctx_hook)
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
                    transport, False, str(code),
                    str(prepared.get("detail", "enter hook refused")),
                    kind=kinds[transport], status=CLASS_FAILED,
                    dom_epoch=prepared.get("dom_epoch"),
                ))
                attempted_transports.append(transport)
                warnings.append(
                    f"enter hook for rung {transport!r} refused with {code!r}")
                continue
            if prepared.get("dom_epoch") is not None:
                dom_epoch = prepared.get("dom_epoch")
            loc = prepared.get("location_id")
            if loc and not req.location_id:
                req = LadderRequest(
                    operation=req.operation, surface=req.surface,
                    location_id=str(loc), run_id=req.run_id,
                    native_object_ids=req.native_object_ids)
        ctx = RungContext(
            request=req,
            transport=transport,
            attempt_index=index,
            incomplete_operation=incomplete,
        )
        try:
            outcome = _invoke_rung(rungs[transport], ctx)
        except Exception as exc:  # noqa: BLE001 — deliberately re-raised, typed
            raise _refuse(
                transport, req,
                "raised instead of returning a contract mapping (rung callables "
                f"must never raise, per the smoke_first() convention): {exc!r}",
            ) from exc

        if not isinstance(outcome, Mapping):
            raise _refuse(
                transport, req,
                f"returned {type(outcome).__name__!r}, not a mapping",
            )

        cleanup = _check_cleanup(transport, req, outcome)
        state, code, detail = _classify_outcome(transport, req, outcome)
        attempted_transports.append(transport)

        if state == STATE_COMPLETE:
            attempts.append(RungAttempt(
                transport, True, None, detail, state=state,
                operation=outcome.get("operation"),
                references_fresh=outcome.get("references_fresh"),
                cleanup=cleanup,
            ))
            succeeded_rung = transport
            if cleanup:
                cleanup_records.append({"transport": transport, **cleanup})
            if observed_location_id is None and outcome.get("location_id"):
                observed_location_id = str(outcome["location_id"])
            observed = observed_location_id
            break

        if state in (STATE_PREREQUISITE, STATE_PARTIAL):
            # Progress, not completion: record it and keep falling through.
            incomplete = True
            prerequisite_rungs.append(transport)
            if cleanup:
                cleanup_records.append({"transport": transport, **cleanup})
            attempts.append(RungAttempt(
                transport, False, None, detail, state=state,
                prerequisite_ready=(state == STATE_PREREQUISITE),
                partial=(state == STATE_PARTIAL),
                operation=outcome.get("operation"),
                references_fresh=outcome.get("references_fresh"),
                cleanup=cleanup,
            ))
            continue

        if cleanup:
            cleanup_records.append({"transport": transport, **cleanup})
        # A failed rung also leaves the operation owed to the next rung.
        incomplete = True
        attempts.append(RungAttempt(
            transport, False, code, detail, state=state,
            operation=outcome.get("operation"),
            references_fresh=outcome.get("references_fresh"),
            cleanup=cleanup,
        ))

    complete = succeeded_rung is not None
    location_bound = bool(expected_location_id or req.location_id or observed) \
        if location_required else True
    if complete and location_required and expected_location_id and not (
            observed or req.location_id):
        # A caller that gated this run to a tenant never accepts a completion
        # with no bound location for it.
        complete = False
        succeeded_rung = None
        warnings.append("completion refused: location-required surface with no bound location")

    result = LadderResult(
        surface=surface,
        order=declared_order,
        operation=req.operation,
        operation_scope=scope,
        attempts=attempts,
        operation_complete=complete,
        succeeded_rung=succeeded_rung,
        decision="SUCCESS" if complete else "PARKED",
        enablement=enablement,
        ladder_active=active,
        run_id=req.run_id,
        native_object_ids=dict(req.native_object_ids),
        incomplete_operation=None if complete else req.operation,
        location_required=location_required,
        location_bound=location_bound if location_required else True,
        warnings=warnings,
        expected_location_id=expected_location_id or req.location_id,
        observed_location_id=observed or observed_location_id,
        prerequisite_rungs=prerequisite_rungs,
        cleanup=cleanup_records,
        state={
            "effectiveOrder": list(effective_order),
            "declaredOrder": list(declared_order),
            "locationId": req.location_id,
            "nativeObjectIds": dict(req.native_object_ids),
        },
    )

    if receipt_path:
        write_ladder_receipt(result, receipt_path, secret_values=secret_values)

    return result


# ── offline self-check (also run by `python3 tools/ghl_fallback_ladder.py`) ──

def _selftest() -> int:
    """Prove the three load-bearing rules offline. No network, no browser."""
    errors: List[str] = []

    def fail(transport: str, **extra: Any) -> Callable[[], dict]:
        def _r() -> dict:
            return {"ok": False, "code": "SELECTOR-MISS", "detail": "forced",
                    **extra}
        _r.__name__ = "fail_" + transport
        return _r

    def done(transport: str) -> Callable[[], dict]:
        def _r() -> dict:
            return {
                "ok": True, "operation": "form.create", "operation_complete": True,
                "status": "operation_complete", "references_fresh": True,
                "owned_sessions": ["page-1"],
                "cleanup": {"released": ["page-1"], "closed_all": False},
            }
        _r.__name__ = "done_" + transport
        return _r

    # 1. a prerequisite-only rung may NEVER complete the operation
    #    (surface "survey" declares browser -> api, so browser is first)
    prereq = {
        "browser": lambda: {
            "ok": True, "operation": "form.create", "operation_complete": False,
            "prerequisite_ready": True, "status": "prerequisite_ready",
        },
        "api": fail("api"),
    }
    res = run_ladder("survey", prereq, operation="form.create",
                     env={FLAG_ENV: "1"})
    if res.ok is not False or res.decision != "PARKED":
        errors.append("prerequisite-only rung reported completion")
    if res.incomplete_operation != "form.create":
        errors.append("prerequisite-only run did not name the incomplete operation")
    if res.prerequisite_rungs != ["browser"]:
        errors.append("prerequisite rung not recorded distinctly")

    # 2. a truthy non-boolean ok is refused
    truthy = {"browser": lambda: {"ok": "false", "operation": "form.create",
                                  "operation_complete": True}}
    try:
        run_ladder("survey", truthy, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("truthy non-boolean ok was accepted")
    except LadderRungError:
        pass

    # 3. ok=True without operation_complete is refused
    vague = {"browser": lambda: {"ok": True, "operation": "form.create"}}
    try:
        run_ladder("survey", vague, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("ok without operation_complete was accepted")
    except LadderRungError:
        pass

    # 4. completing a DIFFERENT operation is refused
    wrong = {"browser": lambda: {
        "ok": True, "operation": "form.delete", "operation_complete": True,
        "references_fresh": True}}
    try:
        run_ladder("survey", wrong, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("completion of a different operation was accepted")
    except LadderRungError:
        pass

    # 5. browser completion without refreshed references is refused
    stale = {"browser": lambda: {
        "ok": True, "operation": "form.create", "operation_complete": True}}
    try:
        run_ladder("survey", stale, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("browser completion without references_fresh was accepted")
    except LadderRungError:
        pass

    # 6. cleanup may never close every session, nor a session it did not own
    close_all = {"browser": lambda: {
        "ok": True, "operation": "form.create", "operation_complete": True,
        "references_fresh": True, "cleanup": {"closed_all": True}}}
    try:
        run_ladder("survey", close_all, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("cleanup.closed_all was accepted")
    except LadderRungError:
        pass
    foreign = {"browser": lambda: {
        "ok": True, "operation": "form.create", "operation_complete": True,
        "references_fresh": True, "owned_sessions": ["page-1"],
        "cleanup": {"released": ["user-window-9"]}}}
    try:
        run_ladder("survey", foreign, operation="form.create", env={FLAG_ENV: "1"})
        errors.append("cleanup of a session the rung did not own was accepted")
    except LadderRungError:
        pass

    # 7. ladder is ON by default; explicit falsey is the revert
    if ladder_enabled({}) is not True:
        errors.append("ladder must default ON")
    if ladder_enabled({FLAG_ENV: "0"}) is not False:
        errors.append("explicit 0 must switch the ladder off")

    # 8. a real completion on the second rung succeeds and names the rung
    ok_run = {"browser": fail("browser"), "api": done("api")}
    res = run_ladder("survey", ok_run, operation="form.create", env={FLAG_ENV: "1"})
    if res.ok is not True or res.succeeded_rung != "api":
        errors.append("real completion on a fallback rung was not recorded")

    # 9. the operation -> capability mapping is per operation, not a blanket one
    cap = operation_capability(
        "funnels.pages.autosave", declared_transports=("browser",))
    if cap.get("surface") != "page" or cap.get("operationComplete") is not False:
        errors.append("operation_capability did not resolve a per-operation surface")
    unknown = operation_capability("unknown.module.thing", declared_transports=("api",))
    if unknown.get("surface") is not None or unknown.get("ladderOrder"):
        errors.append("unknown operation was given an invented surface")

    return errors


if __name__ == "__main__":
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
    problems = _selftest()
    if problems:
        for problem in problems:
            print(f"FAIL: {problem}", file=sys.stderr)
        sys.exit(1)
    print("OK: fallback-ladder.json is structurally valid; completion contract proven")

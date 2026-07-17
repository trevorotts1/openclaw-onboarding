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
that declares, per surface, the attempt order across the three transports —
**browser (UI-drive) -> API (REST) -> MCP (the GHL MCP)** — in an auditable
file, with a fault-injection-provable guarantee that a failed rung hands off
to the next one, tags every failure with the SAME taxonomy the board already
uses (``cc_board.py`` ``_CC_BLOCK_REASONS``), and only records a fail-closed
PARKED outcome when EVERY declared rung has failed.

THIS MODULE IS THE RUNNER, NOT A NEW BUILDER
---------------------------------------------
``run_ladder()`` takes the SURFACE's already-existing per-transport callables
(the caller wires ``ghl_rest_canvas`` / ``ghl_iframe_drag.smoke_first`` /
a Skill-44-MCP call, etc. into a ``{"api": fn, "browser": fn, "mcp": fn}``
mapping) and walks them in the order declared in ``fallback-ladder.json``.
This module invents NO new build logic — it is a thin, generic, declarative
overlay, exactly as the unit's own revert clause describes it.

CONTRACT FOR A RUNG CALLABLE (mirrors ``ghl_iframe_drag.smoke_first`` —
"NEVER RAISES — always returns a dict"):
    Takes no arguments (bind everything via closure/functools.partial).
    Returns ``{"ok": True, ...}`` on success, or
    ``{"ok": False, "code": <one of TAXONOMY_TAGS>, "detail": <str>}`` on a
    classified failure. A rung that raises is treated as a WIRING BUG (an
    uncoded failure this module refuses to silently swallow or fabricate a
    taxonomy tag for) and surfaces as :class:`LadderRungError`.

FLAG-GATED OVERLAY (revert = flip the flag)
--------------------------------------------
``GHL_FALLBACK_LADDER=1`` (see :data:`FLAG_ENV`) turns the FULL declared
ladder on. Flag OFF (default) restricts every call to ONLY the first
declared rung — i.e. today's single-method + ad-hoc-fallback behavior is
byte-for-byte unchanged. This is the unit's own revert contract: "flip the
flag" reverts every surface to its current behavior without touching code.

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

# ── constants ───────────────────────────────────────────────────────────────
FLAG_ENV = "GHL_FALLBACK_LADDER"
TRANSPORTS: Tuple[str, ...] = ("browser", "api", "mcp")
_LADDER_FILENAME = "fallback-ladder.json"
_TRUTHY = {"1", "true", "yes", "on"}


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── errors — never silently default (matches ghl_method.MethodDecisionError) ──

class LadderConfigError(ValueError):
    """Raised for a malformed fallback-ladder.json, an unknown surface, or a
    surface whose declared rung has no callable wired at call time. Never
    silently skipped — a bad config must fail loud, exactly like
    ``ghl_method.MethodDecisionError`` refuses to default on bad input."""


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
    tagged dict, or returns a code outside TAXONOMY_TAGS. This module refuses
    to fabricate a receipt for an uncoded failure."""


# ── config load + validate ────────────────────────────────────────────────────

def _default_ladder_path() -> str:
    return str(_TOOLS_DIR / _LADDER_FILENAME)


def _load_raw(path: Optional[str] = None) -> dict:
    p = path or _default_ladder_path()
    with open(p, "r", encoding="utf-8") as fh:
        return json.load(fh)


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
        if not isinstance(entry, dict):
            raise LadderConfigError(f"surface {name!r}: entry must be an object")
        if "alias_of" in entry:
            target = entry["alias_of"]
            if target not in surfaces:
                raise LadderConfigError(
                    f"surface {name!r}: alias_of {target!r} is not itself a declared surface"
                )
            continue
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

    for name, entry in not_laddered.items():
        if not isinstance(entry, dict) or not entry.get("reason"):
            raise LadderConfigError(
                f"not_laddered surface {name!r}: must declare a non-empty 'reason'"
            )

    return raw


def declared_surfaces(path: Optional[str] = None) -> List[str]:
    """Every surface name that resolves to a real (non-alias) ladder entry."""
    raw = validate_ladder_file(path)
    return sorted(
        name for name, entry in raw["surfaces"].items() if "alias_of" not in entry
    )


def get_ladder(surface: str, path: Optional[str] = None) -> Tuple[str, ...]:
    """Return the declared attempt order for ``surface`` as a tuple.

    Resolves aliases (e.g. "funnel" -> "page"). Raises
    :class:`SurfaceNotLadderedError` for a documented single-lane surface
    (see ``not_laddered``), or :class:`LadderConfigError` for a name that is
    neither laddered nor documented as single-lane."""
    raw = validate_ladder_file(path)
    surfaces = raw["surfaces"]
    not_laddered = raw.get("not_laddered", {})

    seen_aliases: List[str] = []
    name = surface
    while name in surfaces and "alias_of" in surfaces[name]:
        if name in seen_aliases:
            raise LadderConfigError(f"surface {surface!r}: alias cycle detected at {name!r}")
        seen_aliases.append(name)
        name = surfaces[name]["alias_of"]

    if name in surfaces:
        return tuple(surfaces[name]["order"])
    if surface in not_laddered:
        raise SurfaceNotLadderedError(surface, not_laddered[surface]["reason"])
    raise LadderConfigError(
        f"surface {surface!r} is not declared in fallback-ladder.json "
        "('surfaces' or 'not_laddered')"
    )


# ── flag ────────────────────────────────────────────────────────────────────

def ladder_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when the full declared ladder is active (``GHL_FALLBACK_LADDER=1``).
    Default OFF — a caller then only attempts the FIRST declared rung, i.e.
    today's single-method + ad-hoc-fallback behavior, unchanged."""
    env = env if env is not None else os.environ
    return str(env.get(FLAG_ENV, "")).strip().lower() in _TRUTHY


# ── result types ────────────────────────────────────────────────────────────

@dataclass
class RungAttempt:
    transport: str
    ok: bool
    code: Optional[str] = None
    detail: str = ""

    def to_dict(self) -> dict:
        return {"transport": self.transport, "ok": self.ok, "code": self.code, "detail": self.detail}


@dataclass
class LadderResult:
    surface: str
    order: Tuple[str, ...]
    attempts: List[RungAttempt] = field(default_factory=list)
    ok: bool = False
    succeeded_rung: Optional[str] = None
    decision: str = "PARKED"  # "SUCCESS" | "PARKED"
    ladder_active: bool = False
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    decided_at: str = field(default_factory=_now)

    def to_dict(self) -> dict:
        return {
            "surface": self.surface,
            "order": list(self.order),
            "attempts": [a.to_dict() for a in self.attempts],
            "ok": self.ok,
            "succeeded_rung": self.succeeded_rung,
            "decision": self.decision,
            "ladder_active": self.ladder_active,
            "run_id": self.run_id,
            "decided_at": self.decided_at,
        }


def write_ladder_receipt(result: LadderResult, receipt_path: str) -> None:
    """Persist ``result`` as a JSON receipt. Called on BOTH outcomes — a
    successful rung and an all-rungs-fail PARKED close — so success is always
    explicitly recorded (never silent) and failure is always fail-closed
    (never a silent no-op)."""
    d = os.path.dirname(receipt_path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(receipt_path, "w", encoding="utf-8") as fh:
        json.dump(result.to_dict(), fh, indent=2, sort_keys=True)
        fh.write("\n")


# ── the ladder runner ──────────────────────────────────────────────────────

def run_ladder(
    surface: str,
    rungs: Mapping[str, Callable[[], Mapping[str, Any]]],
    *,
    path: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    receipt_path: Optional[str] = None,
) -> LadderResult:
    """Walk ``surface``'s declared transport order, calling ``rungs[transport]()``
    for each, stopping at the first success.

    - Flag OFF (default): only the first declared rung is attempted (today's
      single-method behavior).
    - Flag ON (``GHL_FALLBACK_LADDER=1``): every declared rung is attempted in
      order until one succeeds or all fail.
    - Every failed rung MUST return a code in :data:`TAXONOMY_TAGS`; anything
      else (a raise, a missing code, an unrecognized code) raises
      :class:`LadderRungError` rather than being fabricated into a receipt.
    - Returns a fail-closed ``decision="PARKED"`` result ONLY when every
      attempted rung failed. A success on ANY rung — including a fallback
      rung — records exactly which rung succeeded and never silently reports
      a bare pass.
    """
    declared_order = get_ladder(surface, path=path)
    active = ladder_enabled(env)
    effective_order = declared_order if active else declared_order[:1]

    attempts: List[RungAttempt] = []
    succeeded_rung: Optional[str] = None

    for transport in effective_order:
        if transport not in rungs:
            raise LadderConfigError(
                f"surface {surface!r} declares rung {transport!r} but no callable "
                "was provided to run_ladder(rungs=...)"
            )
        try:
            outcome = rungs[transport]()
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

        if outcome.get("ok"):
            attempts.append(RungAttempt(transport, True, None, str(outcome.get("detail", ""))))
            succeeded_rung = transport
            break

        code = outcome.get("code")
        if code not in TAXONOMY_TAGS:
            raise LadderRungError(
                f"rung {transport!r} for surface {surface!r} failed with "
                f"unrecognized taxonomy code {code!r} (must be one of {TAXONOMY_TAGS}) — "
                "refusing to write a fabricated receipt for it"
            )
        attempts.append(RungAttempt(transport, False, code, str(outcome.get("detail", ""))))

    ok = succeeded_rung is not None
    result = LadderResult(
        surface=surface,
        order=declared_order,
        attempts=attempts,
        ok=ok,
        succeeded_rung=succeeded_rung,
        decision="SUCCESS" if ok else "PARKED",
        ladder_active=active,
    )

    if receipt_path:
        write_ladder_receipt(result, receipt_path)

    return result


if __name__ == "__main__":
    # Self-test: validate the shipped config and print the declared ladder
    # for every surface — no network, no browser, exits non-zero on any
    # LadderConfigError.
    try:
        for name in declared_surfaces():
            print(f"{name}: {' -> '.join(get_ladder(name))}")
        print("OK: fallback-ladder.json is structurally valid")
    except LadderConfigError as exc:  # noqa: BLE001
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)

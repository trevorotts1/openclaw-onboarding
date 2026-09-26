#!/usr/bin/env python3
"""D20 SOP-slot/hint propagation into blend path (JEV spec 1.1, ss 8.9/8.10; 4.5).

(a) Declared-first sources: every part names a caller-supplied ``source`` in
    ``DECOMPOSITION_SOURCES`` (sop_slot | page_structure | campaign_manifest).
    JEV never originates parts: any ``jev_*``/unknown source is rejected.
(b) Kind preserved: ``kind`` is caller-supplied (sop_slot | comm_part |
    agent_task), never defaulted or inferred. An SOP slot never auto-expands
    into comm parts or agent tasks — this module exposes no generator; the
    comm/agent distinction from 8.9 is preserved verbatim per part.
(c) Four-way agreement: single, combined, blended, and producer-supplied
    paths must agree about which context was actually consumed (8.9). Same
    scope, same input hint sets — differing sets raise an explicit mismatch
    error naming the divergent paths, never a silent pick.
(d) Slot/hint repair: a declared slot with no consumed hint yields an
    explicit bind directive (never silently dropped); built on the REAL D19
    ``check_slot_hint_propagation`` — imported, never reimplemented.
(e) Single decomposition: the REAL D19 ``assert_single_decomposition`` —
    imported, never reimplemented (same object, identity-asserted in tests).

Per-part identity (8.10) is caller-supplied: scope_id/seq/goal/
conversion_goal travel on each part (conversion_goal may be empty when
unresolved, mirroring the D02 bundle contract). Consumed hints round-trip:
the blend path records exactly what it consumed, and the four-way check
proves the record is SAME across paths.

Stdlib only. No network, no provider access, no state writes. Validators
return ``(ok, errors)`` fail-closed; deciders raise ValueError on bad input
(never a silent default).

ponytail: hint identity is exact-string match, ceiling is vocabulary drift
(same slot spelled two ways); upgrade path is canonical hint ids behind the
same consumed-list schema (no API change).
"""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "PART_KINDS",
    "DECOMPOSITION_SOURCES",
    "FOUR_PATHS",
    "assert_single_decomposition",
    "check_slot_hint_propagation",
    "validate_part",
    "assert_four_way_agreement",
    "repair_slot_bindings",
]


def _by_path(mod_name, path):
    """Load the REAL module at path (offline test convention)."""
    import importlib.util
    import sys
    existing = sys.modules.get(mod_name)
    if existing is not None:
        return existing
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    return module


_here = Path(__file__).resolve()
_de = _here.parent.parent

_cp = _by_path("d20_collapse_policy", _de / "personas" / "collapse_policy.py")

# D19 single-decomposition guard + slot/hint check, re-exported — never
# redefined here (spec 8.9: run the approved mechanism once).
assert_single_decomposition = _cp.assert_single_decomposition
check_slot_hint_propagation = _cp.check_slot_hint_propagation

# Spec 8.9: communication parts vs agent execution tasks stay distinct.
PART_KINDS = ("sop_slot", "comm_part", "agent_task")

# Spec 8.9: declared SOP slots, existing page structures, approved campaign
# manifests first. JEV never originates a part.
DECOMPOSITION_SOURCES = ("sop_slot", "page_structure", "campaign_manifest")

# Spec 8.9: the four paths that must agree about consumed context.
FOUR_PATHS = ("single", "combined", "blended", "producer")

_REQUIRED_PART_KEYS = frozenset({
    "part_id",
    "kind",
    "source",
    "scope_id",
    "seq",
    "goal",
    "conversion_goal",
    "consumed_hints",
})


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def validate_part(part) -> tuple[bool, list[str]]:
    """Validate one caller-supplied part record. Never raises.

    Requires explicit ``kind`` (never defaulted: an SOP slot is never
    treated as a comm part or agent task) and an explicit declared-first
    ``source`` (JEV-originated sources rejected). Per-part identity
    (scope_id/seq/goal/conversion_goal) must be present; conversion_goal
    may be empty when unresolved (D02 mirror). ``consumed_hints`` is the
    blend-path round-trip record: a list of non-empty strings.
    """
    try:
        if not isinstance(part, dict):
            return False, [f"part is not an object (got {type(part).__name__})"]
        errors: list[str] = []
        unknown = set(part) - _REQUIRED_PART_KEYS
        if unknown:
            errors.append(f"part: unknown field(s) {sorted(unknown)}")
        for key in sorted(_REQUIRED_PART_KEYS):
            if key not in part:
                errors.append(f"missing required key: {key!r}")
        pid = part.get("part_id")
        if "part_id" in part and (
            not isinstance(pid, str) or not pid.strip()
        ):
            errors.append(f"'part_id': required non-empty string, got {pid!r}")
        if "kind" in part and part.get("kind") not in PART_KINDS:
            errors.append(
                f"'kind': {part.get('kind')!r} not in {list(PART_KINDS)} "
                "(caller-supplied; SOP slots never auto-expand to comm/agent)"
            )
        if "source" in part and part.get("source") not in DECOMPOSITION_SOURCES:
            errors.append(
                f"'source': {part.get('source')!r} not in "
                f"{list(DECOMPOSITION_SOURCES)} "
                "(declared-first only: JEV never originates parts)"
            )
        if "scope_id" in part and (
            not isinstance(part.get("scope_id"), str)
            or not part["scope_id"].strip()
        ):
            errors.append(
                f"'scope_id': required non-empty string, got {part.get('scope_id')!r}"
            )
        if "seq" in part and (
            not _is_int(part.get("seq")) or part["seq"] < 1
        ):
            errors.append(
                f"'seq': required int >= 1 (1-based task slot), got {part.get('seq')!r}"
            )
        if "goal" in part and (
            not isinstance(part.get("goal"), str) or not part["goal"].strip()
        ):
            errors.append(f"'goal': required non-empty string, got {part.get('goal')!r}")
        if "conversion_goal" in part and not isinstance(
            part.get("conversion_goal"), str
        ):
            errors.append(
                "'conversion_goal': required string "
                f"(empty when unresolved), got {part.get('conversion_goal')!r}"
            )
        if "consumed_hints" in part:
            hints = part["consumed_hints"]
            if not isinstance(hints, list):
                errors.append(
                    f"'consumed_hints': required list "
                    f"(got {type(hints).__name__})"
                )
            else:
                for i, h in enumerate(hints):
                    if not isinstance(h, str) or not h.strip():
                        errors.append(
                            f"'consumed_hints[{i}]': required non-empty string, "
                            f"got {h!r}"
                        )
        return (len(errors) == 0), errors
    except Exception as exc:  # fail-closed: validator never raises
        return False, [f"validator error: {exc}"]


def _clean_hints(value, name: str) -> list[str]:
    """Strip a consumed-hint list. Raises ValueError on bad input."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"{name}: consumed hints must be a list (got {type(value).__name__})"
        )
    clean: list[str] = []
    for i, h in enumerate(value):
        if not isinstance(h, str) or not h.strip():
            raise ValueError(
                f"{name}[{i}]: every consumed hint must be a non-empty string, "
                f"got {h!r}"
            )
        clean.append(h.strip())
    return clean


def assert_four_way_agreement(
    *,
    scope_id,
    single,
    combined,
    blended,
    producer,
) -> dict:
    """Prove single/combined/blended/producer consumed SAME hints. Raises.

    Same scope, same input: all four consumed-hint sets must match exactly
    (order-insensitive). Differing hint sets raise an explicit mismatch
    error naming each divergent path and the scope — never a silent pick.
    Returns ``{ok, scope_id, consumed (sorted), paths}`` on agreement.
    """
    if not isinstance(scope_id, str) or not scope_id.strip():
        raise ValueError(f"scope_id: required non-empty string, got {scope_id!r}")
    scope = scope_id.strip()
    sets = {
        name: set(_clean_hints(value, name))
        for name, value in (
            ("single", single),
            ("combined", combined),
            ("blended", blended),
            ("producer", producer),
        )
    }
    union = set().union(*sets.values())
    gaps = {name: sorted(union - s) for name, s in sets.items()}
    if any(gaps.values()):
        details = "; ".join(
            f"{name} missing {gaps[name]}"
            for name in FOUR_PATHS
            if gaps[name]
        )
        raise ValueError(
            f"consumed-context mismatch for scope {scope!r}: "
            f"single/combined/blended/producer must agree about consumed "
            f"context (spec 8.9); {details}"
        )
    return {
        "ok": True,
        "scope_id": scope,
        "consumed": sorted(union),
        "paths": list(FOUR_PATHS),
    }


def repair_slot_bindings(declared_slots, consumed_hints, *, scope_id="") -> dict:
    """Emit explicit bind directives for slots with no consumed hint. Raises.

    Runs the REAL D19 ``check_slot_hint_propagation`` (declared vs
    consumed), then converts every missing slot into a bind directive:
    add a consuming-path entry or record an explicit keep/drop approval.
    Missing count always equals directive count — nothing is silently
    dropped. Returns ``{ok, missing, undeclared, directives, scope_id}``.
    Raises ValueError on malformed input (never a silent empty repair).
    """
    if not isinstance(scope_id, str):
        raise ValueError(f"scope_id: must be a string, got {scope_id!r}")
    if not isinstance(declared_slots, (list, tuple)):
        raise ValueError(
            "declared_slots: required list "
            f"(got {type(declared_slots).__name__})"
        )
    if not isinstance(consumed_hints, (list, tuple)):
        raise ValueError(
            "consumed_hints: required list "
            f"(got {type(consumed_hints).__name__})"
        )
    check = check_slot_hint_propagation(
        list(declared_slots), list(consumed_hints)
    )
    if check["errors"]:
        raise ValueError("; ".join(check["errors"]))
    directives = [
        f"bind hint for slot {slot!r} (scope {scope_id.strip()!r}): "
        f"add a consuming-path entry or record explicit keep/drop approval; "
        f"never silently drop"
        for slot in check["missing"]
    ]
    assert len(directives) == len(check["missing"])  # never drop, by construction
    return {
        "ok": check["ok"],
        "missing": list(check["missing"]),
        "undeclared": list(check["undeclared"]),
        "directives": directives,
        "scope_id": scope_id.strip(),
    }

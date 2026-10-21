#!/usr/bin/env python3
"""launch_profiles.py: THE reader for the one launch email profile registry.

The registry (profiles/launch-email-families.json) is the single place the
seven planned launch email families define their counts, paired variants,
purpose and timing. The planner, the launch intake adapter, authoring, the
prover (tools/prove-email.py) and build emission (tools/emit_build_plan.py)
all read THIS module, so a profile fact is defined once and cannot drift
between the gate and the emitter.

Stdlib only. Fail-closed: a missing, unreadable, malformed or incomplete
registry raises RegistryError; no consumer silently falls back to a built-in
list (that is the defect class this registry removes).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

REGISTRY_PATH = (Path(__file__).resolve().parent.parent
                 / "profiles" / "launch-email-families.json")
SUPPORTED_REGISTRY_MAJOR = "1"

# The seven planned families, in plan order (spec 3.1).
PLANNED_KINDS = (
    "pre_launch", "main_launch", "doors_closing", "upsell_followup",
    "downsell_followup", "abandoned_checkout", "welcome_access",
)

_REQUIRED_FAMILY_KEYS = (
    "kind", "profile", "sequence_position", "sequence_id", "purpose",
    "destination", "email_count", "preview_count", "subject_count",
    "subject_mode", "objective", "framework_map", "cta_rules", "word_band",
    "disruptive_required", "timing", "eligibility", "lifecycle", "sender",
    "overrides",
)


class RegistryError(Exception):
    """The registry cannot be read or does not describe the seven families."""


def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").lower()).strip("-")


def load_registry(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load and validate the registry. Raises RegistryError on any defect."""
    p = Path(path) if path else REGISTRY_PATH
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RegistryError("launch email profile registry unreadable at %s: %s"
                            % (p, exc))
    if not isinstance(doc, dict):
        raise RegistryError("profile registry at %s is not a JSON object" % p)
    version = doc.get("registry_version")
    if not (isinstance(version, str) and version.split(".")[0] == SUPPORTED_REGISTRY_MAJOR):
        raise RegistryError(
            "profile registry version %r is not supported (major %s)"
            % (version, SUPPORTED_REGISTRY_MAJOR))
    families = doc.get("families")
    if not isinstance(families, list) or not families:
        raise RegistryError("profile registry declares no families[] array")

    seen_kinds, seen_profiles = set(), set()
    for fam in families:
        if not isinstance(fam, dict):
            raise RegistryError("profile registry carries a non-object family")
        missing = [k for k in _REQUIRED_FAMILY_KEYS if k not in fam]
        if missing:
            raise RegistryError(
                "family %r is missing required key(s): %s"
                % (fam.get("kind"), ", ".join(missing)))
        kind, profile = fam["kind"], fam["profile"]
        if kind in seen_kinds or profile in seen_profiles:
            raise RegistryError("duplicate family kind/profile: %r / %r"
                                % (kind, profile))
        seen_kinds.add(kind)
        seen_profiles.add(profile)
        for key in ("email_count", "preview_count", "subject_count"):
            v = fam[key]
            if not (isinstance(v, int) and not isinstance(v, bool) and v > 0):
                raise RegistryError("family %r %s must be a positive integer"
                                    % (kind, key))
        if fam["subject_count"] != 2:
            raise RegistryError("family %r subject_count must be 2 (A/B)" % kind)
        fw = fam["framework_map"]
        if not isinstance(fw, dict) or not fw:
            raise RegistryError("family %r framework_map is empty" % kind)
        if sorted(int(k) for k in fw) != list(range(1, fam["email_count"] + 1)):
            raise RegistryError(
                "family %r framework_map must cover slots 1..%d exactly"
                % (kind, fam["email_count"]))
        if not isinstance(fam["timing"], dict) or not fam["timing"].get("anchor"):
            raise RegistryError("family %r timing carries no anchor" % kind)
        for key in ("eligibility", "lifecycle", "sender", "overrides"):
            if not isinstance(fam[key], (dict, list)):
                raise RegistryError("family %r %s has the wrong shape"
                                    % (kind, key))
    missing_kinds = [k for k in PLANNED_KINDS if k not in seen_kinds]
    if missing_kinds:
        raise RegistryError("profile registry is missing the planned famil%s: %s"
                            % ("y" if len(missing_kinds) == 1 else "ies",
                               ", ".join(missing_kinds)))
    return doc


def families(registry: Optional[Dict[str, Any]] = None) -> Dict[str, Dict[str, Any]]:
    """kind -> family spec, in declared order."""
    reg = registry if registry is not None else load_registry()
    return {fam["kind"]: fam for fam in reg["families"]}


def family_aliases(fam: Dict[str, Any]) -> tuple:
    """Every name a plan/brief may use for this family, normalized."""
    return tuple(_norm(fam.get(k)) for k in
                 ("kind", "profile", "sequence_position", "sequence_id")
                 if fam.get(k))


def family_for(value: Any,
               registry: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Resolve a kind / profile / sequence_position / sequence_id to its family.

    Exact normalized match only — a value that merely contains "signature-launch"
    never selects a family (that heuristic is what made every new family resolve
    to the main landing profile)."""
    needle = _norm(value)
    if not needle:
        return None
    for fam in (registry or load_registry())["families"]:
        if needle in family_aliases(fam):
            return fam
    return None


def family_by_profile(profile: Any,
                      registry: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Resolve by the prover's profile id (exact, normalized)."""
    needle = _norm(profile)
    for fam in (registry or load_registry())["families"]:
        if needle == _norm(fam["profile"]):
            return fam
    return None


def cta_floor(fam: Dict[str, Any], slot: int) -> int:
    rules = fam.get("cta_rules") or {}
    v = rules.get(str(slot), rules.get("default", 1))
    return v if isinstance(v, int) and v >= 1 else 1


def word_band(fam: Dict[str, Any], slot: int,
              pattern: Optional[str] = None) -> List[int]:
    spec = fam.get("word_band") or {}
    if pattern:
        by_pat = (spec.get("by_pattern_slot") or {}).get(pattern) or {}
        if str(slot) in by_pat:
            return list(by_pat[str(slot)])
    by_slot = spec.get("by_slot") or {}
    if str(slot) in by_slot:
        return list(by_slot[str(slot)])
    return list(spec.get("default") or [150, 300])


def framework_map(fam: Dict[str, Any], pattern: Optional[str] = None) -> Dict[int, str]:
    if pattern:
        pm = (fam.get("pattern_maps") or {}).get(pattern) or {}
        if pm:
            return {int(k): v for k, v in pm.items()}
    return {int(k): v for k, v in (fam.get("framework_map") or {}).items()}


def wait_after_hours(fam: Dict[str, Any], gap_index: int) -> Optional[float]:
    """The declared gap (hours) AFTER email `gap_index` (1-based). A scalar
    applies to every gap; None means the family did not declare a cadence."""
    timing = fam.get("timing") or {}
    gaps = timing.get("wait_after_hours")
    if isinstance(gaps, list):
        if 1 <= gap_index <= len(gaps):
            return gaps[gap_index - 1]
        return None
    if isinstance(gaps, (int, float)) and not isinstance(gaps, bool):
        return float(gaps)
    return None

#!/usr/bin/env python3
"""brand_record.py - the F16 S2 brand record, style-source vocabulary and creative-direction
precedence. One definition, read by every consumer.

Why this file exists (spec F16 items 4, 6, 8, 11):

* FOUR modules used to speak four vocabularies for "how was the style chosen".
  `engine.decision_state` records `accepted_recommendation`; Skill 71's intake accepts
  `recommended_accepted`; Skill 83's image plan knew only `client_choice` and
  `default_to_confirm`; Skill 49's C3 knew the same two. And Skill 83 turned ABSENCE into
  `client_choice`, so a style nobody chose read as a decision. `normalize_style_source`
  below is the one normalizer: it maps both spellings to the canonical
  `recommended_accepted`, keeps a proposal a proposal, and answers `unknown` when there is
  no evidence. It is idempotent by construction - it returns only canonical values.

* The brand record is NOT a second identity system. The plan's brand hash is the value the
  existing producer already computes: `engine.brand_provenance(doc, brand_file=...)
  ["brand_file_sha256"]`, the SHA-256 of the brand file's bytes. `brand_digest` computes
  the same number over the same bytes so a consumer holding the file can prove it is the
  file the plan was built from; `brand_record` reports verified / mismatch / unbound /
  unreadable and never invents another hash.

* A missing or unrecognized `palette_status` is `unknown`, never `provided` (F16 item 8).

* Creative direction (F16 item 11): the Image Guide allows an approved FULL / ADAPT /
  SUPPRESS blend, `hypersaturation.py` appends the house grade unconditionally and cites
  a LATER owner order (Trevor Otts, 2026-10-19). `creative_direction_policy` states the
  total precedence - which source wins on the STYLE axis and which on the GRADE axis -
  and returns one grade mode a producer can obey. It removes nothing silently: an
  unapproved blend does not suppress the house grade, and an approved blend is not
  overwritten by it.

stdlib only; reads no secret.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

BRAND_RECORD_SCHEMA = "client-intake-brand-record/v1"
CREATIVE_DIRECTION_POLICY_SCHEMA = "client-intake-creative-direction/v1"

# ---------------------------------------------------------------- style source
# The three RECORDED states. A proposal the client has not accepted is not one of them.
STYLE_DECISIONS = ("client_choice", "recommended_accepted", "unknown")
# The word Skill 83 and Skill 49 already emit for a proposal the client has not accepted.
STYLE_PROPOSAL = "default_to_confirm"
STYLE_SOURCES = STYLE_DECISIONS + (STYLE_PROPOSAL,)

# Every spelling the four modules used, mapped to the one canonical value. The two live
# spellings are `engine.decision_state`'s `accepted_recommendation` and Skill 71's
# `recommended_accepted`; the rest are the source strings the shared engine writes when a
# client accepts a recommendation (see engine._ACCEPTED_SOURCE_PREFIXES).
_STYLE_ALIASES = {
    "client_choice": "client_choice",
    "client": "client_choice",
    "client-choice": "client_choice",
    "accepted_recommendation": "recommended_accepted",
    "recommended_accepted": "recommended_accepted",
    "recommendation_accepted": "recommended_accepted",
    "recommendation-accepted": "recommended_accepted",
    "recommended-accepted": "recommended_accepted",
    "proposal-accepted": "recommended_accepted",
    "proposal_accepted": "recommended_accepted",
    "palette-help": "recommended_accepted",
    "recommended-option": "recommended_accepted",
    "feel-words": "recommended_accepted",
    "default_to_confirm": STYLE_PROPOSAL,
    "default-to-confirm": STYLE_PROPOSAL,
    "suggested": STYLE_PROPOSAL,
    "proposed": STYLE_PROPOSAL,
    "recommended_unapproved": STYLE_PROPOSAL,
    "unknown": "unknown",
    "not_asked": "unknown",
    "not-asked": "unknown",
}

# ---------------------------------------------------------------- palette status
PALETTE_STATUSES = ("provided", "suggested", "default_to_confirm", "unknown")
# Spellings a confirmed palette has actually carried (Skill 83's own history).
_PALETTE_ALIASES = {"client-confirmed": "provided", "client_confirmed": "provided",
                    "confirmed": "provided", "provided": "provided",
                    "suggested": "suggested", "default_to_confirm": "default_to_confirm",
                    "default-to-confirm": "default_to_confirm", "unknown": "unknown"}

# ---------------------------------------------------------------- creative direction
GRADE_MODES = ("FULL", "ADAPT", "SUPPRESS")
HOUSE_POLICY = "house_policy_2026-10-19"      # hypersaturation.py's cited owner order
EXTERNAL_STYLE = "approved_external_style"    # the Image Guide's approved blend
IMAGE_GUIDE = "image_guide_blend_allowance"   # the guide's FULL/ADAPT/SUPPRESS allowance
EXTERNAL_KINDS = ("external_direction", "own_reference", "described")


def _text(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) else ""


def normalize_style_source(value: Any) -> str:
    """One canonical style-source value: client_choice, recommended_accepted,
    default_to_confirm (a proposal, never a decision) or unknown.

    Idempotent: every return is already canonical, so normalising it again returns it
    unchanged. An unrecognized string is `unknown` - never a choice nobody made.
    A dict entry (an answers-file entry) is read for its acceptance evidence.
    """
    if isinstance(value, dict):
        return style_source_from_entry(value)
    key = _text(value).lower().replace(" ", "_")
    return _STYLE_ALIASES.get(key, "unknown")


def is_known_style_source(value: Any) -> bool:
    """True when `value` is empty (no evidence) or one of the spellings this vocabulary owns.
    An invented string is refused by the caller rather than downgraded to `unknown`."""
    if value is None:
        return True
    if isinstance(value, dict):
        return True
    if not isinstance(value, str):
        return False
    key = value.strip().lower().replace(" ", "_")
    return not key or key in _STYLE_ALIASES


def style_source_from_entry(entry: Any) -> str:
    """The canonical source of ONE answers-file entry (the shape `client-intake-answers/v1`
    stores). Mirrors `engine.decision_state`'s rules in the canonical vocabulary: an
    acceptance the client gave is `recommended_accepted`; a suggestion or flagged default
    is still `proposed`; a missing or unknown entry is `unknown`; anything else is the
    client's own choice. Idempotent through `normalize_style_source`.
    """
    if not isinstance(entry, dict):
        return "unknown"
    accepted = entry.get("accepted") if isinstance(entry.get("accepted"), dict) else {}
    source = _text(entry.get("source")).lower()
    if entry.get("accepted_proposal") or accepted.get("approval_ref") or \
            source.startswith(("recommendation-accepted", "proposal-accepted", "palette-help",
                               "recommended-option")) or source == "feel-words":
        return "recommended_accepted"
    status = _text(entry.get("status")).lower()
    if status in ("suggested", "default_to_confirm"):
        return STYLE_PROPOSAL
    if status in ("", "unknown") and entry.get("value") is None:
        return "unknown"
    return "client_choice"


def is_recorded_decision(source: Any) -> bool:
    """True only for a decision the client actually recorded. A proposal is not one."""
    return normalize_style_source(source) in ("client_choice", "recommended_accepted")


def normalize_palette_status(value: Any) -> str:
    """One canonical palette status. Missing or unrecognized is `unknown`, never `provided`
    (F16 item 8). Idempotent: returns only the four canonical values."""
    return _PALETTE_ALIASES.get(_text(value).lower(), "unknown")


# ---------------------------------------------------------------- the brand record
def brand_digest(brand_file: Any) -> Optional[str]:
    """SHA-256 of the brand file's bytes - the SAME value the plan's producer records as
    `engine.brand_provenance(...)["brand_file_sha256"]`. None when unreadable."""
    try:
        return hashlib.sha256(Path(brand_file).read_bytes()).hexdigest()
    except (OSError, TypeError, ValueError):
        return None


def _brand_doc(brand_file: Any) -> Optional[Dict[str, Any]]:
    import json
    try:
        doc = json.loads(Path(brand_file).read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError):
        return None
    return doc if isinstance(doc, dict) else None


def brand_record(brand_file: Any, *, plan_brand_sha256: Any = None,
                 version: Any = None, owner: Any = None) -> Dict[str, Any]:
    """The brand the pages are drawn from, bound to the plan's own hash.

    `brand_sha256` is the digest of the file in hand; `plan_brand_sha256` is the value the
    plan recorded. `state` is:
      verified   both known and equal - this is the file the plan was built from
      mismatch   both known and different - a stale pin or a substituted file
      unbound    no plan hash was recorded: honest, never called verified
      unreadable the file cannot be read, so nothing is claimed
    """
    digest = brand_digest(brand_file)
    plan = _text(plan_brand_sha256) or None
    if digest is None:
        state = "unreadable"
    elif plan is None:
        state = "unbound"
    elif plan == digest:
        state = "verified"
    else:
        state = "mismatch"
    doc = _brand_doc(brand_file) or {}
    status = normalize_palette_status(doc.get("palette_status"))
    return {"schema": BRAND_RECORD_SCHEMA,
            "brand_file": _text(brand_file) or None,
            "brand_sha256": digest,
            "plan_brand_sha256": plan,
            "state": state,
            "verified": state == "verified",
            "version": version,
            "owner": _text(owner) or None,
            "brand_id": _text(doc.get("brand_id")) or None,
            "palette_status": status,
            "palette_confirmed": status == "provided",
            "palette_roles": doc.get("palette_roles") if isinstance(doc.get("palette_roles"), dict) else None}


def matches(record: Dict[str, Any]) -> bool:
    """True only when the record proves this is the plan's brand file."""
    return isinstance(record, dict) and record.get("state") == "verified"


# ---------------------------------------------------------------- creative direction
def creative_direction_policy(*, kind: Any = None, blend: Any = None,
                              approval_ref: Any = None) -> Dict[str, Any]:
    """Which source wins, on which axis, and why - explicit and total.

    STYLE axis: the client's recorded direction wins when there is one; the house look is
    used only when the client chose it or when no direction was recorded (an absence is
    reported as `not_asked`, never as a choice).

    GRADE axis (two rules that used to contradict each other):
      1. An APPROVED external blend (a FULL / ADAPT / SUPPRESS mode bound to an approval
         reference) wins over the house grade and over the Image Guide's general
         allowance, because it is the client's scoped approval of their own style.
      2. Otherwise the later owner order (hypersaturation.py, 2026-10-19) wins and the
         house grade is FULL. A blend with no approval cannot suppress the house grade,
         and a missing direction cannot either - the house grade is never silently
         removed, and an approved external style is never silently overwritten.
    """
    k = _text(kind).lower()
    want = _text(blend).upper() or None
    approved_ref = _text(approval_ref) or None
    external = k in EXTERNAL_KINDS
    if k == "house_look":
        style_owner, style_state = HOUSE_POLICY, "house_look"
    elif external:
        style_owner, style_state = "client_direction", "recorded"
    elif k in ("", "not_asked", "unknown"):
        style_owner, style_state = HOUSE_POLICY, "not_asked"
    else:  # an unrecognized kind is not a direction; it is unknown
        style_owner, style_state = "unknown", "unknown"

    conflicts = []
    if external and want in GRADE_MODES and approved_ref:
        grade_mode, grade_owner = want, EXTERNAL_STYLE
    else:
        grade_mode, grade_owner = "FULL", HOUSE_POLICY
        if want is not None and want not in GRADE_MODES:
            conflicts.append(f"blend {want!r} is not one of {list(GRADE_MODES)}; the house grade applies")
        elif want in GRADE_MODES and not approved_ref:
            conflicts.append(f"blend {want} has no approval reference; the house grade applies")
        elif want in GRADE_MODES and not external:
            conflicts.append(f"blend {want} needs an external creative direction; the house grade applies")
    # The precedence, in order. Each row names the competing claim and what happened to it.
    precedence = [
        {"rank": 1, "axis": "style", "source": style_owner,
         "wins": style_owner != "unknown",
         "why": ("the client's recorded direction is the style authority" if external else
                 "the house look is used only when chosen or when no direction was recorded")},
        {"rank": 2, "axis": "grade", "source": EXTERNAL_STYLE,
         "wins": grade_owner == EXTERNAL_STYLE,
         "why": "an approved FULL/ADAPT/SUPPRESS blend supplies the grade" if grade_owner == EXTERNAL_STYLE
                else "no approved external blend is in scope"},
        {"rank": 3, "axis": "grade", "source": HOUSE_POLICY,
         "wins": grade_owner == HOUSE_POLICY,
         "why": "the later owner order (hypersaturation.py) supplies the house grade" if grade_owner == HOUSE_POLICY
                else "superseded here only by an approved external blend"},
        {"rank": 4, "axis": "grade", "source": IMAGE_GUIDE,
         "wins": False,
         "why": "the guide's general FULL/ADAPT/SUPPRESS allowance never beats an approval or the owner order"},
    ]
    return {"schema": CREATIVE_DIRECTION_POLICY_SCHEMA,
            "direction_kind": k or None,
            "requested_blend": want,
            "approval_ref": approved_ref,
            "style_owner": style_owner,
            "style_state": style_state,
            "grade_mode": grade_mode,
            "grade_owner": grade_owner,
            "conflicts": conflicts,
            "precedence": precedence}

"""launch_prompt_policy.py -- named prompt policies for Skill 63 consumers.

Signature Launch profile (packet doc 02 section 10, spec 15 section 6):
'signature_launch_completeness' is the launch policy. A prompt passes when
every required information element is present. Length is telemetry only,
UNLESS a verified vendor ceiling exists (cap published or owner-observed
with a number), in which case exceeding that verified ceiling fails.
cap_status NOT_PUBLISHED means: no invented ceiling, no length rejection,
no silent truncation, and no padding to reach a cosmetic count. Padding
(repeated filler) fails completeness review.

Legacy profile: 'legacy_house_band' preserves the existing general house
band (5000 / ~9000 / 19000, advisory only) under its own name for legacy
consumers. The social-planner scoped hard band stays owned by its own
policy (shared-utils/social_prompt_policy.json) and is not changed here.

The single authoritative launch policy is coordinated with S71/S49
(acceptance A24); page skills must consume this named policy rather than
re-implementing length gates in adapter layers.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass

LAUNCH_POLICY_ID = "signature_launch_completeness"
LEGACY_POLICY_ID = "legacy_house_band"

REQUIRED_ELEMENTS = (
    "subject",
    "environment",
    "style",
    "lighting",
    "composition",
    "output",
)


@dataclass(frozen=True)
class CapInfo:
    status: str  # "not_published" | "published" | "owner_observed"
    chars: int | None = None


@dataclass
class PolicyResult:
    valid: bool
    policy_id: str
    char_count: int
    missing_elements: list[str]
    errors: list[str]
    note: str


def _count(prompt: str) -> int:
    return len(unicodedata.normalize("NFC", prompt).strip())


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(
        unicodedata.normalize("NFC", prompt).strip().encode("utf-8")
    ).hexdigest()


def _padding_detected(prompt: str) -> bool:
    """Repeated 8-word-gram ratio > 0.08 = filler (house expansion doctrine)."""
    words = re.findall(r"\S+", unicodedata.normalize("NFC", prompt).lower())
    if len(words) < 40:
        return False
    grams = [" ".join(words[i:i + 8]) for i in range(len(words) - 7)]
    if not grams:
        return False
    repeated = len(grams) - len(set(grams))
    return (repeated / len(grams)) > 0.08


def evaluate_launch_policy(prompt: str, elements_present: set[str],
                           cap: CapInfo) -> PolicyResult:
    count = _count(prompt)
    errors: list[str] = []
    missing = [e for e in REQUIRED_ELEMENTS if e not in elements_present]
    if not prompt.strip():
        errors.append("prompt is empty")
    if missing:
        errors.append(f"incomplete prompt: missing element(s) {missing}")
    if _padding_detected(prompt):
        errors.append("padding detected: repeated filler does not satisfy completeness")
    if cap.status in ("published", "owner_observed") and cap.chars is not None:
        if count > cap.chars:
            errors.append(f"prompt exceeds verified vendor ceiling {cap.chars} chars")
        note = f"verified ceiling {cap.chars} chars enforced; length {count} recorded as telemetry"
    elif cap.status == "not_published":
        note = ("cap_status=not_published: no vendor ceiling invented; "
                f"length {count} recorded as telemetry only")
    else:
        errors.append(f"unknown cap status '{cap.status}'")
        note = ""
    return PolicyResult(
        valid=not errors, policy_id=LAUNCH_POLICY_ID, char_count=count,
        missing_elements=missing, errors=errors, note=note,
    )


def evaluate_legacy_house_band(prompt: str) -> PolicyResult:
    """Legacy profile: advisory bands only, never a length rejection."""
    count = _count(prompt)
    if count < 5000:
        band = "THIN_STUB (advisory: expand, do not reject)"
    elif count <= 9000:
        band = "TARGET_ZONE"
    elif count <= 19000:
        band = "UPPER_BAND"
    else:
        band = "ABOVE_PREFERRED_MAX (advisory only; vendor cap NOT_PUBLISHED)"
    return PolicyResult(
        valid=bool(prompt.strip()), policy_id=LEGACY_POLICY_ID, char_count=count,
        missing_elements=[], errors=[] if prompt.strip() else ["prompt is empty"],
        note=band,
    )

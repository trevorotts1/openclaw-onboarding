"""Deterministic payload mapper: by MEANING, not by field name.

Implements design/webhook-design.md Section 4 for the oracle: container flattening
(4.2 step 1), exact alias match (step 2), fuzzy key normalization (step 3),
value-shape validation (step 4), the hard tenant check (step 5), and the
required-field gate (step 6). Unknown extras are retained verbatim on the raw
record but excluded from the canonical hash (step 7).

There is no language model here and no Model Context Protocol access. The mapper
is pure data-in, data-out.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dataclass_field
from datetime import datetime

from .aliases import (
    ALIASES,
    DEFAULT_STYLE_TRANSPARENCY_SLOT,
    DOTTED_CONTAINERS,
    KNOWN_CONTAINERS,
    TRANSPARENCY_ALIASES,
)

_WHITESPACE = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]")

# Fields whose canonical value is an enum token and is lowercased.
_ENUM_TEXT_FIELDS = {"preferred_pronoun", "episode_type", "explicit", "tts_model"}
# Fields carried on the canonical record but never fed to the hash or the pipeline
# as instructions; still surfaced so the intake layer can read them.
_EXTRA_FIELDS = {"writing_model", "web_research_tool", "workflow_trigger", "retry", "_test"}

# Required to start production (Section 4.2 step 6). show_name and host_name are
# additionally required for interview mode; the style path's q-answers through the
# transparency answer are required for every mode (the oracle enforces q1 plus the
# transparency slot, which is the always-present subset of that path).
_ALWAYS_REQUIRED = ["mode", "style", "contact_id", "location_id", "podcast_id", "first_name"]
_INTERVIEW_REQUIRED = ["show_name", "host_name"]


@dataclass
class MappingResult:
    status: str  # "accepted" | "accepted-incomplete" | "quarantine"
    canonical: dict
    missing: list = dataclass_field(default_factory=list)
    alerts: list = dataclass_field(default_factory=list)
    tenant_ok: bool = True
    raw: dict = dataclass_field(default_factory=dict)


def _fuzzy(key: str) -> str:
    return _NON_ALNUM.sub("", key.lower())


def _flatten(raw: dict) -> dict:
    """Flatten known containers, scalars-first at each level then containers in order.

    contact and location sub-objects are surfaced in dotted form (contact.id,
    contact.first_name, location.id) so a bare id is only read as a contact id when
    it truly sits inside a contact object. First hit wins: a key already present is
    never overwritten by a deeper container.
    """
    flat: dict = {}

    def put(key, value):
        if key not in flat:
            flat[key] = value

    def absorb(node):
        if not isinstance(node, dict):
            return
        # scalars and id-sensitive sub-objects first
        for key, value in node.items():
            if key in DOTTED_CONTAINERS and isinstance(value, dict):
                for sub_key, sub_value in value.items():
                    put(key + "." + sub_key, sub_value)
            elif isinstance(value, dict):
                continue  # a container; descended into below in defined order
            else:
                put(key, value)
        # then descend into known containers, in the order the spec searches them
        for container in KNOWN_CONTAINERS:
            if container in DOTTED_CONTAINERS:
                continue
            value = node.get(container)
            if isinstance(value, dict):
                absorb(value)

    absorb(raw)
    return flat


def _resolve(flat: dict, alias_keys) -> tuple:
    """Return (value, matched_key) using exact match then fuzzy match; else (None, None)."""
    for alias in alias_keys:
        if alias in flat:
            return flat[alias], alias
    fuzzy_index = {}
    for key in flat:
        fuzzy_index.setdefault(_fuzzy(key), key)
    for alias in alias_keys:
        candidate = fuzzy_index.get(_fuzzy(alias))
        if candidate is not None:
            return flat[candidate], candidate
    return None, None


def _clean_text(value) -> str:
    return _WHITESPACE.sub(" ", str(value)).strip()


def normalize_mode(value):
    token = _fuzzy(str(value))
    if "interview" in token:
        return "interview_style_podcast"
    if "personal" in token:
        return "personal_podcast_style"
    return None


def normalize_style(value):
    token = _fuzzy(str(value))
    for canonical_token, prefix in (
        ("counter_intuitive", "counterintuitive"),
        ("vulnerable", "vulnerable"),
        ("provocative", "provocative"),
        ("passionate", "passionate"),
    ):
        if token.startswith(prefix):
            return canonical_token
    return None


def _looks_like_id(value) -> bool:
    text = str(value).strip()
    if "@" in text or " " in text:
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{6,}", text))


def _parse_timestamp(value):
    text = str(value).strip()
    candidate = text[:-1] + "+00:00" if text.endswith("Z") else text
    try:
        datetime.fromisoformat(candidate)
        return text
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y", "%B %d, %Y"):
        try:
            datetime.strptime(text, pattern)
            return text
        except ValueError:
            continue
    return None


def map_payload(raw, tenant_location_id, aliases=None, style_transparency_slot=None):
    """Map a raw upstream payload to the canonical schema by meaning.

    tenant_location_id is the Location ID configured for THIS client at onboarding;
    a mapped location_id that does not equal it is quarantined (Section 4.2 step 5).
    """
    aliases = aliases or ALIASES
    slot_map = style_transparency_slot or DEFAULT_STYLE_TRANSPARENCY_SLOT
    if not isinstance(raw, dict):
        return MappingResult(status="quarantine", canonical={}, tenant_ok=False,
                             alerts=["payload is not a JSON object"], raw={})

    flat = _flatten(raw)
    canonical: dict = {}
    alerts: list = []

    for field_name, alias_keys in aliases.items():
        value, _matched = _resolve(flat, alias_keys)
        if value is None:
            continue
        if field_name == "mode":
            normalized = normalize_mode(value)
            if normalized:
                canonical[field_name] = normalized
        elif field_name == "style":
            normalized = normalize_style(value)
            if normalized:
                canonical[field_name] = normalized
        elif field_name in ("contact_id", "location_id"):
            if _looks_like_id(value):
                canonical[field_name] = str(value).strip()
        elif field_name == "publish_timestamp":
            parsed = _parse_timestamp(value)
            if parsed is not None:
                canonical[field_name] = parsed
        elif field_name in _ENUM_TEXT_FIELDS:
            canonical[field_name] = _clean_text(value).lower()
        elif field_name in _EXTRA_FIELDS:
            canonical[field_name] = value if field_name in ("retry", "_test") else _clean_text(value)
        else:
            canonical[field_name] = _clean_text(value)

    # Transparency answer lands in the style path's q-slot (Section 4.2 step 2).
    transparency_value, _t = _resolve(flat, TRANSPARENCY_ALIASES)
    if transparency_value is not None:
        slot = slot_map.get(canonical.get("style"), "q5_answer")
        if slot not in canonical:
            canonical[slot] = _clean_text(transparency_value)

    # Tenant check (hard). A mismatch means the payload belongs to another tenant or
    # is corrupted: quarantine, alert the operator, process nothing.
    mapped_location = canonical.get("location_id")
    tenant_ok = True
    if mapped_location is not None and tenant_location_id is not None:
        if mapped_location != tenant_location_id:
            tenant_ok = False
            alerts.append(
                "tenant location_id mismatch: payload=" + str(mapped_location)
                + " expected=" + str(tenant_location_id)
            )
            return MappingResult(status="quarantine", canonical=canonical, tenant_ok=False,
                                 alerts=alerts, raw=raw)

    # Required-field gate (Section 4.2 step 6). Nothing is ever guessed.
    required = list(_ALWAYS_REQUIRED)
    if canonical.get("mode") == "interview_style_podcast":
        required += _INTERVIEW_REQUIRED
    # q1 plus the transparency slot are the always-present subset of the style path.
    transparency_slot = slot_map.get(canonical.get("style"), "q5_answer")
    required += ["q1_answer", transparency_slot]

    missing = [name for name in required if not str(canonical.get(name, "")).strip()]
    if missing:
        alerts.append("missing required fields: " + ", ".join(missing))
        return MappingResult(status="accepted-incomplete", canonical=canonical,
                             missing=missing, alerts=alerts, tenant_ok=tenant_ok, raw=raw)

    return MappingResult(status="accepted", canonical=canonical, missing=[],
                         alerts=alerts, tenant_ok=tenant_ok, raw=raw)

"""Character DNA records (directive 13.1). Stdlib only.

Strict allowlist schema: unknown fields are rejected, so sensitive identity
traits outside the brief cannot sneak in. Every record carries at least one
approved reference asset ID; the prompt compiler binds those IDs into prompts.
"""
from __future__ import annotations

import json
import re

SCHEMA_VERSION = "1.0.0"

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")

# ponytail: 13.1 field set fixed; add new trait only on directive change.

#: Non-empty free-text identity fields, directive 13.1 order.
TEXT_FIELDS = (
    "age_band",
    "skin_tone_complexion",
    "facial_structure",
    "eyes",
    "nose",
    "mouth",
    "hair",
    "body_build",
    "distinguishing_features",
    "wardrobe_rules",
)

#: List fields requiring at least one entry.
LIST_MIN1 = (
    "expression_range",
    "prohibited_drift",
    "approved_reference_asset_ids",
)

#: List fields allowed to be empty.
LIST_ANY = ("accessories",)

KNOWN = frozenset(
    ["character_id", "schema_version"] + list(TEXT_FIELDS)
    + list(LIST_MIN1) + list(LIST_ANY)
)


def validate_character(d):
    """Return error list (empty = valid). Fail-closed on shape."""
    if not isinstance(d, dict):
        return ["NOT_A_RECORD"]
    errs = []
    for k in sorted(d):
        if k not in KNOWN:
            errs.append("UNKNOWN_FIELD:%s" % k)
    for k in ["character_id"] + list(TEXT_FIELDS):
        if k not in d:
            errs.append("MISSING:%s" % k)
    for k in LIST_MIN1 + LIST_ANY:
        if k not in d:
            errs.append("MISSING:%s" % k)
    if errs:
        return errs
    if d.get("schema_version") != SCHEMA_VERSION:
        errs.append("BAD_SCHEMA_VERSION:%r" % (d.get("schema_version"),))
    cid = d["character_id"]
    if not isinstance(cid, str) or not ID_RE.match(cid):
        errs.append("BAD_CHARACTER_ID:%r" % (cid,))
    for k in TEXT_FIELDS:
        v = d[k]
        if not isinstance(v, str) or not v.strip():
            errs.append("BAD_TEXT:%s" % k)
    for k in LIST_MIN1:
        v = d[k]
        if not isinstance(v, list) or not v or \
                any(not isinstance(i, str) or not i.strip() for i in v):
            errs.append("BAD_LIST:%s" % k)
    for k in LIST_ANY:
        v = d[k]
        if not isinstance(v, list) or \
                any(not isinstance(i, str) for i in v):
            errs.append("BAD_LIST:%s" % k)
    return errs


def normalize_character(d):
    """Canonical key order. Raises ValueError on invalid record."""
    errs = validate_character(d)
    if errs:
        raise ValueError("; ".join(errs))
    return {k: d[k] for k in sorted(d)}


def dumps(d):
    return json.dumps(normalize_character(d), sort_keys=True,
                      ensure_ascii=True)


def loads(s):
    return normalize_character(json.loads(s))


def reference_binding(characters):
    """Map character_id -> approved asset IDs. Raises ValueError."""
    if not isinstance(characters, list) or not characters:
        raise ValueError("NO_CHARACTERS")
    out = {}
    for c in characters:
        errs = validate_character(c)
        if errs:
            raise ValueError("; ".join(errs))
        cid = c["character_id"]
        if cid in out:
            raise ValueError("DUPLICATE_CHARACTER_ID:%s" % cid)
        out[cid] = list(c["approved_reference_asset_ids"])
    return out

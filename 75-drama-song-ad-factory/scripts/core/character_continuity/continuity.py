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


# --- cross-shot wardrobe and location check (F-PIC-6) ----------------------
# Read-only over the plan: walk wardrobe ids and location ids across shots and
# refuse a change the story did not declare.
WARDROBE_BREAK = "WARDROBE_BREAK"
LOCATION_BREAK = "LOCATION_BREAK"

# A transition that legitimately carries the story to another place.
_MOVING_TRANSITIONS = frozenset(
    {"scene_change", "location_change", "cutaway", "establishing"})


def _ordered(shots):
    return sorted(shots, key=lambda s: (s.get("song_start", 0),
                                        s.get("song_end", 0)))


def check_cross_shot_continuity(shots, wardrobe_ledger=None):
    """Refuse a wardrobe or location break across shots (the robe-shot case).

    shots: [{shot_id, scene_id?, character_ids, wardrobe_ids, location_id,
    transition?}]. A wardrobe change between consecutive shots of one
    character inside one scene is a WARDROBE_BREAK unless the ledger confirms
    it. A location change inside one scene is a LOCATION_BREAK unless the
    shot declares a moving transition.

    Returns {"outcome", "findings", "codes"}.
    """
    if not isinstance(shots, list) or not shots:
        return {"outcome": "pass", "findings": [], "codes": []}
    ordered = _ordered(shots)
    findings = []

    def fail(code, shot_id, detail):
        findings.append({"code": code, "shot_id": shot_id, "detail": detail})

    def explained(wid):
        return isinstance(wardrobe_ledger, dict) and wid in wardrobe_ledger

    by_char = {}
    for s in ordered:
        for cid in s.get("character_ids") or []:
            by_char.setdefault(cid, []).append(s)
    for cid, seq in by_char.items():
        for a, b in zip(seq, seq[1:]):
            if a.get("scene_id") != b.get("scene_id"):
                continue
            if set(a.get("wardrobe_ids") or []) == set(b.get("wardrobe_ids") or []):
                continue
            changed = set(b.get("wardrobe_ids") or []) - set(a.get("wardrobe_ids") or [])
            if wardrobe_ledger is None:
                continue
            for wid in sorted(changed):
                if not explained(wid):
                    fail(WARDROBE_BREAK, b.get("shot_id"),
                         "character %r changes into wardrobe %r mid-scene with no "
                         "wardrobe-ledger entry" % (cid, wid))

    if wardrobe_ledger is not None:
        for s in ordered:
            for wid in s.get("wardrobe_ids") or []:
                if not explained(wid):
                    fail(WARDROBE_BREAK, s.get("shot_id"),
                         "wardrobe %r has no ledger entry" % (wid,))

    for a, b in zip(ordered, ordered[1:]):
        if a.get("scene_id") != b.get("scene_id"):
            continue
        if (a.get("location_id") and b.get("location_id")
                and a.get("location_id") != b.get("location_id")):
            transition = str(b.get("transition") or "").strip().lower()
            if transition not in _MOVING_TRANSITIONS:
                fail(LOCATION_BREAK, b.get("shot_id"),
                     "location moves %r -> %r inside scene %r with no declared "
                     "transition" % (a.get("location_id"), b.get("location_id"),
                                     b.get("scene_id")))

    return {"outcome": "pass" if not findings else "fail",
            "findings": findings,
            "codes": sorted({f["code"] for f in findings})}


# --- wardrobe accessories lock (N-13) --------------------------------------
# The wardrobe ledger lists every accessory by name (stole, head wrap, glasses).
# A clip that starts from a locked picture must show the full wardrobe; a listed
# accessory missing from the shot's declared wardrobe is an ACCESSORY_BREAK.
ACCESSORY_BREAK = "ACCESSORY_BREAK"


def check_accessory_lock(wardrobe_ledger, shot_wardrobe):
    """Refuse a shot missing an accessory its wardrobe entry lists (N-13).

    wardrobe_ledger: {wardrobe_id: {"accessories": [names]}}.
    shot_wardrobe: {wardrobe_id: {"accessories": [names]}} for the shots.
    Returns the list of findings (empty = clean).
    """
    ledger = wardrobe_ledger or {}
    findings = []
    for wid, shot in (shot_wardrobe or {}).items():
        need = [str(x) for x in ((ledger.get(wid) or {}).get("accessories") or [])]
        have = {str(x) for x in ((shot or {}).get("accessories") or [])}
        for acc in need:
            if acc not in have:
                findings.append({"code": ACCESSORY_BREAK, "wardrobe_id": wid,
                                 "detail": "accessory %r missing from wardrobe %r"
                                 % (acc, wid)})
    return findings

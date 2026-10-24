#!/usr/bin/env python3
"""S75-T41: the FINAL outgoing artist/alias guard for every Suno payload.

Runs on the complete rendered payload immediately before the send boundary --
after templates, client answers, defaults and provider transforms.  Every
text-bearing field at any depth is inspected, including nested
``input.style`` / ``input.negative_tags`` / ``input.title`` / ``input.lyrics``
and any future nested prompt field.

Three outcomes, never a silent pass:

  * PASS      -- no catalog reference in any outbound text field.
  * SANITIZED -- a reference appeared only in an INSTRUCTION field (style,
                 negative tags, title, prompt).  The instruction is rewritten
                 into approved musical traits, the payload is re-guarded, and
                 only then is it sendable.
  * BLOCKED   -- an approved creative field (the lyric sheet by default)
                 collides with a catalog name or alias.  Exactly that
                 submission stops: the field and the exact match are named,
                 approved bytes are untouched, and zero provider calls occur.

Case, Unicode accents, apostrophes (straight and curly) and punctuation are
normalized before matching, so ``CÉLINE DION``, ``Celine Dion.`` and
``Celine Dion’s`` all hit the same alias.  The spaces between a reference's
words may also be absent or replaced by any punctuation run, so ``andraday``,
``ANDRA-DAY`` and ``EdSheeran groove`` hit the same alias their spaced
spelling does -- and a squashed hit still has to be the WHOLE alias-shaped
word run, never a substring of a longer word.

Object KEYS are outbound text too: every key at any depth is normalized and
matched exactly like a value, so a name can never ride out of the payload
inside a map key.  A map entry whose key carries a reference is dropped whole
(the entry is atomic, like a list tag); under an approved path it blocks
instead.  A payload value that cannot serialise into a provider payload --
display metadata -- is a hard block of its own.

The alias set is the catalog's own display references plus the explicit
aliases recorded beside them.  That scope is reported as ``alias_scope`` --
this is NOT a blacklist of every artist alive, and the receipt says so.

stdlib only, no network, no provider calls, no credential reads.
"""
from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata

TOOL_NAME = "music_styles.suno_prompt_guard"
TOOL_VERSION = "1.0.0"
SCHEMA_VERSION = "blackceo.suno-prompt-guard/v1"

#: Approved creative content: a match here BLOCKS the submission.  A lyric
#: sheet is approved bytes under an approval digest; editing it here would be
#: a silent creative rewrite.
DEFAULT_PROTECTED_PATHS = ("input.lyrics",)

#: Keys that are display-only by construction.  Seeing one anywhere in an
#: outbound payload means client metadata was serialized into a provider
#: request: a hard block, independent of whether a name is recognized.
CLIENT_METADATA_KEYS = frozenset({
    "client_references",
    "display_metadata",
    "recognition",
    "recognition_references",
    "reference_songs",
    "artist_references",
})

#: A field that may not become empty: an empty style field is not a payload.
REQUIRED_NONEMPTY_PATHS = ("input.style",)

#: Instruction fields are clause text.  A clause carrying any alias is an
#: instruction ("do not sound like ...", "in the style of ...") and is removed
#: whole; every approved musical trait in the other clauses stays.
_PUNCT_SPLIT = re.compile(r"(?<=[,;.\n])")


class PromptGuardError(ValueError):
    """A guard call the caller got wrong (never a verdict)."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


# ------------------------------------------------------------------ alias ---
def normalize(text, keep_hyphens=False):
    """Comparable form: NFKD, accents dropped, casefolded, punctuation -> space.

    ``keep_hyphens=True`` keeps ``-`` as a separator of its own, so the
    HYPHENATED spelling of a reference is matchable exactly like the spaced one.
    """
    if not isinstance(text, str):
        return ""
    folded = unicodedata.normalize("NFKD", text)
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold()
    for curly in ("’", "‘", "ʼ", "`", "´"):
        folded = folded.replace(curly, "'")
    folded = re.sub(r"[^\w'\s-]+" if keep_hyphens else r"[^\w'\s]+", " ",
                    folded, flags=re.UNICODE)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


def _alias_forms(name):
    """Every comparable spelling of one display reference.

    Matching runs on normalized text, so the forms are the spellings that
    survive it: the spaced CASE-FOLDED form (``luther vandross``), the
    PUNCTUATION-STRIPPED form (``p diddy`` -> ``pdiddy``), the HYPHENATED form
    (``luther-vandross``) and the SPACE-REMOVED form (``luthervandross``).
    A squashed or hyphenated spelling is the SAME reference, not a new one, and
    a squashed form is only ever matched as a whole alias-shaped run (see
    ``_matcher``) -- never as an arbitrary substring.
    """
    forms = set()
    norm = normalize(name)
    if not norm:
        return forms
    bases = [norm]
    # a possessive/inflected display form ("Adele's") folds to "adele s"
    if norm.endswith(" s"):
        bases.append(norm[:-2])
    for base in bases:
        for run in (base, base.replace("'", "")):
            forms.add(run)
            if " " in run:
                forms.add(run.replace(" ", ""))    # space-removed: "andraday"
                forms.add(run.replace(" ", "-"))   # hyphenated: "ed-sheeran"
    return forms


def alias_set(catalog):
    """{normalized alias: sorted style ids that display it}, from the catalog.

    Reads ONLY the display namespace.  Aliases may be given as a list, or as a
    mapping of artist -> extra aliases.
    """
    out = {}
    for record in _records(catalog):
        refs = record.get("client_references")
        if not isinstance(refs, dict):
            continue
        style_id = record.get("style_id") or record.get("id") or "<unnamed>"
        names = []
        names.extend(_strings(refs.get("artists")))
        names.extend(_strings(refs.get("reference_songs")))
        aliases = refs.get("aliases")
        if isinstance(aliases, dict):
            for artist, extra in aliases.items():
                names.append(artist)
                names.extend(_strings(extra))
        else:
            names.extend(_strings(aliases))
        for name in names:
            for form in _alias_forms(name):
                out.setdefault(form, set()).add(style_id)
    return {form: sorted(ids) for form, ids in sorted(out.items())}


def alias_revision(aliases):
    """Stable digest of the exact alias set a verdict was made against."""
    payload = json.dumps({k: v for k, v in sorted(aliases.items())},
                         sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _records(catalog):
    if isinstance(catalog, dict):
        styles = catalog.get("styles")
        if isinstance(styles, dict):
            for key, value in styles.items():
                record = dict(value) if isinstance(value, dict) else {}
                record.setdefault("style_id", key)
                yield record
            return
        if isinstance(styles, list):
            for value in styles:
                if isinstance(value, dict):
                    yield value
            return
        for key, value in catalog.items():
            if isinstance(value, dict):
                record = dict(value)
                record.setdefault("style_id", key)
                yield record
        return
    for value in (catalog or []):
        if isinstance(value, dict):
            yield value


def _strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [v for v in value if isinstance(v, str)]
    return []


# ------------------------------------------------------------------ match ---
def find_matches(text, aliases):
    """Aliases present in one text, alias-shaped on the normalized form.

    Both normalized views are matched: the spaced view (punctuation -> space)
    and the hyphen-preserving one, so every spelling a form can take is
    reachable.  A hit is always a whole alias-shaped word run -- the boundary
    in ``_matcher`` is what keeps ``andraday`` from matching inside
    ``andradaybeat`` or ``bandraday``.
    """
    if not isinstance(text, str):
        return []
    regex, _known = _matcher(aliases)
    hits = set()
    for view in (normalize(text), normalize(text, keep_hyphens=True)):
        hits.update(match.group(0) for match in regex.finditer(view))
    return sorted(hits)


#: One compiled alternation per alias set: the guard runs over every field of
#: every payload, so a per-alias regex scan would be quadratic busywork.
_MATCHER_CACHE = {}


def _matcher(aliases):
    key = tuple(sorted(aliases))
    cached = _MATCHER_CACHE.get(key)
    if cached is None:
        alternatives = "|".join(re.escape(alias) for alias in
                                sorted(key, key=len, reverse=True))
        if not alternatives:
            alternatives = r"(?!)"   # no aliases: the empty alternation never matches
        # The boundaries are what make a hit ALIAS-SHAPED: a form matches only
        # as a whole word run, so the space-removed "andraday" hits "andraday
        # beat", "andraday_beat" and "ANDRA-DAY" while never matching inside
        # "andradaybeat" or "bandraday" (a substring of a longer word is a
        # different word, not this reference).
        cached = (re.compile(r"(?<![0-9a-z])(?:%s)(?![0-9a-z])"
                             % alternatives), set(key))
        _MATCHER_CACHE[key] = cached
    return cached


def _dot(path):
    return ".".join(str(part) for part in path)


def _walk_text(value, path=()):
    """Yield (path tuple, text) for every string at any depth."""
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for key, sub in value.items():
            yield from _walk_text(sub, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            yield from _walk_text(sub, path + (index,))


def _walk_keys(value, path=()):
    if isinstance(value, dict):
        for key, sub in value.items():
            yield path + (key,), key
            yield from _walk_keys(sub, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            yield from _walk_keys(sub, path + (index,))


#: Everything a provider payload may lawfully carry.  Anything else -- a
#: display-only mapping, a custom object -- cannot serialise into a provider
#: payload and is refused at this boundary instead of being hoped past.
_JSON_SCALARS = (str, int, float, bool)


def _walk_foreign(value, path=()):
    """Yield (path, value) for every node that is not plain payload data."""
    if value is None or isinstance(value, _JSON_SCALARS):
        return
    if isinstance(value, dict):
        for key, sub in value.items():
            yield from _walk_foreign(sub, path + (key,))
    elif isinstance(value, (list, tuple)):
        for index, sub in enumerate(value):
            yield from _walk_foreign(sub, path + (index,))
    else:
        yield path, value


def _get(payload, path):
    node = payload
    for part in path:
        node = node[part]
    return node


def _set(payload, path, value):
    node = payload
    for part in path[:-1]:
        node = node[part]
    node[path[-1]] = value


def _delete(payload, path):
    parent = _get(payload, path[:-1]) if len(path) > 1 else payload
    index = path[-1]
    if isinstance(parent, list):
        del parent[index]
    else:
        parent.pop(index, None)


def is_protected(path, protected):
    dot = _dot(path)
    return any(dot == p or dot.startswith(p + ".") for p in protected)


def sanitize_instruction(text, aliases):
    """Rewrite one instruction text into its approved musical traits.

    A clause carrying any catalog alias is a reference instruction and is
    removed whole; the remaining clauses keep their order and wording.  The
    result is RE-MATCHED by the caller -- a leftover alias is a block, never a
    pass.
    """
    clauses = [c for c in _PUNCT_SPLIT.split(text) if c]
    kept = [clause for clause in clauses
            if not find_matches(clause, aliases)]
    out = "".join(kept) if kept else ""
    return re.sub(r"\s{2,}", " ", out).strip()


def _digest(value):
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ guard ---
def guard(payload, catalog, protected=DEFAULT_PROTECTED_PATHS):
    """Inspect, then either return a sendable payload or block the submission.

    Returns a receipt dict.  ``receipt["sendable"]`` is True only for PASS and
    SANITIZED.  On BLOCKED the payload is never returned for sending, the
    approved creative bytes are untouched, and ``provider_calls`` is 0.
    """
    if not isinstance(payload, dict):
        raise PromptGuardError("PAYLOAD_NOT_AN_OBJECT",
                               "the guarded payload must be an object")
    aliases = alias_set(catalog)
    revision = alias_revision(aliases)
    inspected = ([_dot(path) for path, _ in _walk_text(payload)]
                 + [_dot(path) for path, _ in _walk_keys(payload)])

    foreign = sorted({_dot(path) for path, _node in _walk_foreign(payload)})
    if foreign:
        return _receipt(payload, revision, aliases, inspected,
                        decision="BLOCKED", sendable=False,
                        blocked=[{"field": path,
                                  "match": None,
                                  "reason": "DISPLAY_METADATA_NOT_SERIALIZABLE",
                                  "detail": ("value cannot serialise into a "
                                             "provider payload; display "
                                             "metadata is display-only"),
                                  "resolution_owner": "payload builder"}
                                 for path in foreign],
                        sanitized=[], provider_calls=0)

    leaks = sorted({_dot(path) for path, key in _walk_keys(payload)
                    if key in CLIENT_METADATA_KEYS})
    if leaks:
        return _receipt(payload, revision, aliases, inspected,
                        decision="BLOCKED", sendable=False,
                        blocked=[{"field": path,
                                  "match": None,
                                  "reason": "CLIENT_METADATA_SERIALIZED",
                                  "resolution_owner": "catalog/payload-builder"}
                                 for path in leaks],
                        sanitized=[], provider_calls=0)

    guarded = copy.deepcopy(payload)
    blocked = []
    sanitized = []
    edits = []
    key_drops = []
    # A map KEY is outbound text: it is normalized and matched exactly like a
    # value, at every depth.  An entry whose key carries a reference is atomic
    # and is dropped whole; under an approved path it blocks instead.
    for key_path, key in list(_walk_keys(guarded)):
        hits = find_matches(str(key), aliases)
        if not hits:
            continue
        field = _dot(key_path)
        if is_protected(key_path, protected):
            blocked.append({
                "field": field,
                "match": hits,
                "reason": "APPROVED_CONTENT_COLLISION",
                "detail": ("approved creative content collides with catalog "
                           "reference(s); the approved bytes are unchanged and "
                           "only this submission is held"),
                "resolution_owner": "artifact revision + whole-package review",
            })
            continue
        key_drops.append(key_path)
        sanitized.append(field)
    for path, text in list(_walk_text(guarded)):
        hits = find_matches(text, aliases)
        if not hits:
            continue
        field = _dot(path)
        in_list = isinstance(_get(guarded, path[:-1]), list)
        if is_protected(path, protected):
            blocked.append({
                "field": field,
                "match": hits,
                "reason": "APPROVED_CONTENT_COLLISION",
                "detail": ("approved creative content collides with catalog "
                           "reference(s); the approved bytes are unchanged and "
                           "only this submission is held"),
                "resolution_owner": "artifact revision + whole-package review",
            })
            continue
        if in_list:
            # a tag is atomic: any reference makes the whole tag unsafe
            edits.append((path, None))
            sanitized.append(field)
            continue
        rewritten = sanitize_instruction(text, aliases)
        leftover = find_matches(rewritten, aliases)
        if leftover:
            blocked.append({
                "field": field,
                "match": leftover,
                "reason": "INSTRUCTION_UNRESOLVED",
                "detail": "reference instruction could not be rewritten "
                          "safely into approved musical traits",
                "resolution_owner": "recipe owner",
            })
            continue
        if field in REQUIRED_NONEMPTY_PATHS and not rewritten.strip():
            blocked.append({
                "field": field,
                "match": hits,
                "reason": "MISSING_TRAITS",
                "detail": "style field emptied; no approved traits survive",
                "resolution_owner": "recipe owner",
            })
            continue
        in_list = isinstance(_get(guarded, path[:-1]), list)
        edits.append((path, None if (in_list and not rewritten.strip())
                      else rewritten))
        sanitized.append(field)

    # Apply string rewrites first, then list removals descending per parent so
    # a shifted index can never delete the wrong tag.
    for path, value in edits:
        if value is not None:
            _set(guarded, path, value)
    # Key drops are whole entries and shift nothing; deepest first so an entry
    # nested inside another dropped entry goes before its container.
    for key_path in sorted(key_drops, key=len, reverse=True):
        _delete(guarded, key_path)
    removals = {}
    for path, value in edits:
        if value is None:
            removals.setdefault(path[:-1], []).append(path[-1])
    for parent_path, indexes in removals.items():
        for index in sorted(indexes, reverse=True):
            _delete(guarded, parent_path + (index,))

    # Re-scan the WHOLE guarded payload: a rewrite can never leave a hit
    # behind unnoticed, at any depth -- in values or in keys.
    already = {(b["field"], tuple(b["match"] or ())) for b in blocked}
    residual = []
    for path, text in _walk_text(guarded):
        hits = find_matches(text, aliases)
        if hits and (_dot(path), tuple(hits)) not in already:
            residual.append({"field": _dot(path), "match": hits})
    for key_path, key in _walk_keys(guarded):
        hits = find_matches(str(key), aliases)
        if hits and (_dot(key_path), tuple(hits)) not in already:
            residual.append({"field": _dot(key_path), "match": hits})
    if residual:
        blocked.extend({
            "field": item["field"],
            "match": item["match"],
            "reason": "RESIDUAL_REFERENCE",
            "detail": "a reference survived the rewrite; refusing to send",
            "resolution_owner": "recipe owner",
        } for item in residual)

    decision = "BLOCKED" if blocked else ("SANITIZED" if sanitized else "PASS")
    sendable = not blocked
    return _receipt(guarded if sendable else payload, revision, aliases,
                    inspected, decision=decision, sendable=sendable,
                    blocked=blocked, sanitized=sanitized,
                    provider_calls=0)


def _receipt(payload, revision, aliases, inspected, decision, sendable,
             blocked, sanitized, provider_calls):
    return {
        "schema": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "decision": decision,
        "sendable": sendable,
        "blocked": blocked,
        "sanitized_fields": sanitized,
        "inspected_fields": inspected,
        "alias_revision": revision,
        "alias_count": len(aliases),
        "alias_scope": ("catalog display references and their recorded "
                        "aliases only; not a universal artist blacklist"),
        "payload_digest": (_digest(payload) if sendable else None),
        "submitted_payload_digest": None,
        "preserved_approved_content_digest": _preserved_digest(payload),
        "provider_calls": provider_calls,
        "payload": payload if sendable else None,
    }


def _preserved_digest(payload):
    """Digest of every protected field, proving approval bytes did not move."""
    found = {}
    for path, text in _walk_text(payload):
        dot = _dot(path)
        if is_protected(path, DEFAULT_PROTECTED_PATHS):
            found[dot] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"_digest": _digest(found), "fields": found}


def guard_or_raise(payload, catalog, protected=DEFAULT_PROTECTED_PATHS):
    """Guard and refuse by exception when the submission is blocked.

    The supported adapter boundary calls this with the exact payload it is
    about to serialize; a retry, a resumed run or a repair re-runs it, so no
    earlier clean pass can authorize a changed payload.
    """
    receipt = guard(payload, catalog, protected)
    if not receipt["sendable"]:
        fields = ", ".join("%s(%s)" % (b["field"],
                                       ",".join(b["match"] or [b["reason"]]))
                           for b in receipt["blocked"])
        raise PromptGuardError("OUTGOING_REFERENCE_BLOCKED",
                               "refused by name: %s" % fields)
    return receipt


def guarded_send(payload, catalog, send, protected=DEFAULT_PROTECTED_PATHS):
    """The send boundary itself: guard, then dispatch the EXACT guarded bytes.

    ``send`` is any callable taking the guarded payload.  A blocked submission
    never reaches it (zero provider calls), and the receipt records the digest
    that was actually dispatched, so retries and reused runs re-guard the
    final payload rather than trusting an earlier clean intermediate.
    """
    receipt = guard_or_raise(payload, catalog, protected)
    result = send(receipt["payload"])
    receipt["submitted_payload_digest"] = receipt["payload_digest"]
    return result, receipt

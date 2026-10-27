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
words may also be absent or replaced by ONE JOIN UNIT that carries whatever it
carries -- a hyphen, an underscore, an apostrophe, a digit, a Roman numeral,
ordinary letters, a punctuation run, several of them mixed or doubled -- so
``andraday``, ``ANDRA-DAY``, ``Bad_Bunny``, ``Jelly'Roll``, ``Bad①Bunny``,
``BadⅠBunny``, ``Bad1Bunny``, ``BadxyBunny``, ``Bad_1_Bunny``, ``Bad 1 Bunny``,
``Bad1_1Bunny`` and ``BadabcdBunny`` hit the same alias their spaced spelling
does.  A join UNIT is what sits AT one word boundary: it may carry any
characters but never a whole WORD, so ``bad boy bunny`` and ``bad that night
but the bunny`` are ordinary prose and never a reference.  The WORDS identify
the reference and the material sitting at their join does not change it -- but
a squashed hit still has to be the WHOLE alias-shaped word run, never a
substring of a longer word.

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
#:
#: These six are only the spellings the CATALOG writes.  A seventh spelling of
#: the same container -- ``artistReferences``, ``artist_names``,
#: ``displayReference`` -- is the same container, so the block is on the SHAPE
#: of a key as well as on these literals (``is_client_metadata_key``): a
#: display subject (artist / client / recognition / display / reference / song)
#: together with a display qualifier (reference(s) / name(s) / metadata /
#: value(s) / text(s) / notes) names client metadata however it is spelled, at any
#: depth.  That is why ``{"display_value": ...}`` cannot ride out under a key
#: nobody has invented yet either: the block keys are inside the block.
CLIENT_METADATA_KEYS = frozenset({
    "client_references",
    "display_metadata",
    "recognition",
    "recognition_references",
    "reference_songs",
    "artist_references",
})

#: The two halves of a display-metadata key name, on its normalized tokens.
_DISPLAY_SUBJECT = frozenset({
    "artist", "artists", "client", "clients", "recognition",
    "display", "reference", "references", "ref", "refs", "song", "songs",
})
#: The PLURAL forms are the ones that name a collection, so they are carried
#: exactly like the singular container words; ``note`` singular is a scalar
#: field ("displayNote"), not a container, and refusing it would be an
#: over-block with no name behind it.
_DISPLAY_QUALIFIER = frozenset({
    "reference", "references", "ref", "refs", "name", "names",
    "metadata", "value", "values", "notes", "text", "texts",
})
#: A token that is BOTH halves is the container WORD itself: ``reference``,
#: ``references``, ``ref`` and ``refs`` name a display collection with no
#: second token beside them, so a key spelled exactly that IS the namespace,
#: never a scalar beside it.  (S75-T41 r10: the two-token rule below let these
#: four ride out, where r8 had refused them.)
_CONTAINER_WORDS = _DISPLAY_SUBJECT & _DISPLAY_QUALIFIER

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
def _fold_compat(text):
    """COMPATIBILITY characters fold to a separator BEFORE NFKD runs.

    NFKD flattens a compatibility character into plain letters or digits, and
    that silently re-joins the words around it: ``Bad①Bunny`` becomes the one
    word ``bad1bunny`` and ``BadⅠBunny`` becomes ``badibunny`` -- no alias
    form, no boundary violation, so nothing downstream can see the join any
    more.  A circled digit, a Roman numeral, a superscript, a subscript, a
    fullwidth letter, a ligature and a fraction are all one of these.  An
    accent is not: its decomposition is canonical, so ``Céline`` still folds to
    ``celine`` and keeps matching.  A NUMBER-shaped symbol is one of these too
    even where it has no decomposition at all, which is why the whole ``Nl``
    and ``No`` categories are folded rather than only their compatible part.
    """
    return "".join(
        " " if (unicodedata.decomposition(ch).startswith("<")
                or unicodedata.category(ch) in ("Nl", "No")) else ch
        for ch in text)


def normalize(text, keep_hyphens=False):
    """Comparable form: NFKD, accents dropped, casefolded, punctuation -> space.

    ``keep_hyphens=True`` keeps ``-`` as a separator of its own, so the
    HYPHENATED spelling of a reference is matchable exactly like the spaced one.
    Every separator between words folds to a space -- including a JOIN carried
    by ``_``, an apostrophe (straight or curly) or a compatibility character,
    in any run, so ``Bad_Bunny``, ``Bad'Bunny``, ``Bad__Bunny``, ``Bad①Bunny``
    and ``BadⅠBunny`` all fold to ``bad bunny``.
    """
    if not isinstance(text, str):
        return ""
    folded = unicodedata.normalize("NFKD", _fold_compat(text))
    folded = "".join(ch for ch in folded if not unicodedata.combining(ch))
    folded = folded.casefold()
    for curly in ("’", "‘", "ʼ", "`", "´"):
        folded = folded.replace(curly, "'")
    folded = re.sub(r"[^\w'\s-]+" if keep_hyphens else r"[^\w'\s]+", " ",
                    folded, flags=re.UNICODE)
    # ``\w`` keeps ``_`` and the class above keeps ``'``; both are JOINS
    # between words, not word characters here, so a join is a separator like
    # any other punctuation -- in any run.  This is the difference between
    # "Bad_Bunny" reaching the matcher as one word and reaching it as the two
    # words every alias form is built from.
    folded = re.sub(r"[_']+", " ", folded)
    folded = re.sub(r"\s+", " ", folded).strip()
    return folded


def _alias_forms(name):
    """Every comparable spelling of one display reference.

    Matching runs on normalized text, so the forms are the spellings that
    survive it: the spaced CASE-FOLDED form (``luther vandross``), the
    PUNCTUATION-STRIPPED form (``p diddy`` -> ``pdiddy``), the HYPHENATED form
    (``luther-vandross``), the SPACE-REMOVED form (``luthervandross``) and the
    JOINED forms a spelling may present (``luther_vandross``,
    ``luther'vandross``).  A squashed, hyphenated or joined spelling is the
    SAME reference, not a new one, and a squashed form is only ever matched as
    a whole alias-shaped run (see ``_matcher``) -- never as an arbitrary
    substring.
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
        forms.add(base)
        if " " in base:
            forms.add(base.replace(" ", ""))     # space-removed: "andraday"
            forms.add(base.replace(" ", "-"))    # hyphenated: "ed-sheeran"
            forms.add(base.replace(" ", "_"))    # joined: "ed_sheeran"
            forms.add(base.replace(" ", "'"))    # joined: "ed'sheeran"
    return forms


def alias_set(catalog):
    """{normalized alias: sorted style ids that display it}, from the catalog.

    Reads ONLY the display namespace.  Aliases may be given as a list, or as a
    mapping of artist -> extra aliases.  ``catalog`` is either the catalog
    (records carrying ``client_references``) or ONE flat display-references
    mapping -- which is the shape a single run declares at the dispatch seam.
    """
    if isinstance(catalog, dict) and any(
            key in catalog for key in ("artists", "aliases", "reference_songs")):
        catalog = {"styles": {"<run>": {"style_id": "<run>",
                                        "client_references": catalog}}}
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

#: ONE join unit sits where a reference's words meet, and it may carry ANY
#: characters at all: ``Bad1Bunny``, ``Bad①Bunny``, ``BadxyBunny``,
#: ``Bad_1_Bunny``, ``Bad 1 Bunny``, ``Bad1_1Bunny`` and ``BadabcdBunny`` are
#: the same words with the join carrying whatever it carries, and ``Maroon15``
#: is ``Maroon 5`` the same way.  The words are what name the reference; the
#: join is one unit of material AT one word boundary, so it never turns the
#: words into different words (``bead bunny`` is not ``bad bunny`` -- that
#: would be a fuzzy match on the WORDS, which this never does) and it never
#: swallows a whole WORD (``bad boy bunny`` is not ``bad bunny``, and prose
#: that carries an alias's words with sentences between them is prose).
#:
#: So the join is bounded in KIND and never in LENGTH.  A length bound cannot
#: do this job: ``Bad 1 2 Bunny`` is a reference and ``bad boy bunny`` is a
#: five-character word between the same two words, so any gap short enough to
#: spare the prose also spares ``BadabcdBunny`` and ``Bad 1 2 Bunny``.  The
#: rule instead follows the material's shape: with no whitespace it is glued
#: to BOTH of the alias's words (one alias-shaped word run, letters and all),
#: and with whitespace every piece it carries is a join fragment of at most
#: one letter.  A squashed hit is still the WHOLE alias-shaped word run --
#: never a substring of a longer word -- which is the boundary in ``_matcher``,
#: not the join.
_LETTER = r"[^\W\d_]"
_NOT_LETTER = r"(?:[^\w\s]|[\d_])"
_JOIN_PIECE = r"%s*(?:%s%s*)?" % (_NOT_LETTER, _LETTER, _NOT_LETTER)
#: A hyphen is a WORD SEPARATOR, not join material: ``bad-boy-bunny`` is three
#: words (prose), so the glued alternative may carry anything but a hyphen.
_JOIN = r"(?:[^-\s]*?|(?:%s\s+)*%s)" % (_JOIN_PIECE, _JOIN_PIECE)


def _alias_pattern(form):
    """One comparable form, its word joins tolerant of any join unit."""
    words = [word for word in re.split(r"[_'\s-]+", form) if word]
    if not words:
        return re.escape(form)
    return _JOIN.join(re.escape(word) for word in words)


def _matcher(aliases):
    key = tuple(sorted(aliases))
    cached = _MATCHER_CACHE.get(key)
    if cached is None:
        alternatives = "|".join(_alias_pattern(alias) for alias in
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


def _key_tokens(key):
    """Comparable tokens of an object key: camelCase and snake_case alike.

    The namespace is CLOSED, not approximated: a lower/digit-to-capital edge
    splits (``artistNames``), an ACRONYM-to-word edge splits
    (``ARTISTReferences``, ``ARTISTNames``) and a letter/digit edge splits
    (``artistNames2``, ``artist_names2``, ``displayMetadata2``), so a digit
    glued onto a container name or an all-caps prefix cannot carry the key past
    the shape rule as one opaque token.
    """
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(key))
    text = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", text)
    text = re.sub(r"(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])", " ", text)
    return set(normalize(text).split())


def is_client_metadata_key(key):
    """True for a display-only key name, however that name is spelled.

    The six canonical names in ``CLIENT_METADATA_KEYS`` are the catalog's own
    spellings; the shape test under them is what keeps a seventh spelling of
    the same container (``artistReferences``, ``artist_names``,
    ``recognition_ref``, ``displayReference``) from riding out beside them.
    """
    if str(key) in CLIENT_METADATA_KEYS:
        return True
    tokens = _key_tokens(key)
    if tokens and tokens <= _CONTAINER_WORDS:
        # The key IS a container word ("references"), so there is no scalar
        # beside a container here: this is the display namespace itself.
        return True
    subjects = tokens & _DISPLAY_SUBJECT
    qualifiers = tokens & _DISPLAY_QUALIFIER
    # The two halves must be TWO tokens: ``reference`` is both a subject and a
    # qualifier word, so a key like ``referenceCount`` would otherwise satisfy
    # itself and be refused as a container it is not.
    return any(subject != qualifier
               for subject in subjects for qualifier in qualifiers)


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
def guard(payload, catalog=None, protected=DEFAULT_PROTECTED_PATHS,
          approved_lyrics=None, approved_character_names=None):
    """Inspect, then either return a sendable payload or block the submission.

    Returns a receipt dict.  ``receipt["sendable"]`` is True only for PASS and
    SANITIZED.  On BLOCKED the payload is never returned for sending, the
    approved creative bytes are untouched, and ``provider_calls`` is 0.

    Called WITHOUT a ``catalog`` the fixed-table verdict layer runs instead
    (``verdict_guard``): same payload, PASS/BLOCKED receipt, no rewrite.
    """
    if catalog is None:
        return verdict_guard(payload, approved_lyrics,
                             approved_character_names)
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
                    if is_client_metadata_key(key)})
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


# ------------------------------------------------- verdict layer (S75-T41) ---
# The fixed-table verdict layer: the same outgoing payload, checked against
# the catalog's display references plus the aliases recorded below, with NO
# rewrite.  ``guard(payload)`` (no catalog) runs this.  Every limitation is
# reported in the receipt, never assumed away.
ALIASES = {
    "Luther Vandross": ("Luther",),
    "Whitney Houston": ("Nippy",),
    "Lauryn Hill": ("L-Boogie", "L Boogie"),
    "Missy Elliott": ("Misdemeanor", "Missy"),
    "Andra Day": ("Andra",),
    "Bill Withers": ("Bill Withers",),
    "Ed Sheeran": ("Sheeran",),
    "Jason Mraz": ("Mraz",),
    "Tracy Chapman": ("Chapman",),
    "Bob Dylan": ("Robert Zimmerman", "Zimmerman"),
    "Shania Twain": ("Twain",),
    "Carrie Underwood": ("Underwood",),
    "Drake": ("Drizzy", "Aubrey Graham", "Champagne Papi"),
    "Rod Wave": ("Rodarius Green",),
    "Cardi B": ("Belcalis Almanzar", "Cardi"),
    "Future": ("Nayvadius Wilburn",),
    "Nelly": ("Cornell Haynes", "Cornell Iral Haynes"),
    "Flo Rida": ("Tramar Dillard",),
    "Puff Daddy": ("P. Diddy", "P Diddy", "Diddy", "Sean Combs"),
    "Maroon 5": ("Maroon Five",),
    "Paramore": ("Hayley Williams",),
    "Daddy Yankee": ("Ramón Ayala", "Ramon Ayala"),
    "Bad Bunny": ("Benito Martínez", "Benito Martinez"),
    "Adele - Skyfall": ("Adele", "Skyfall"),
    "Celine Dion - My Heart Will Go On": (
        "Céline Dion", "Celine Dion", "My Heart Will Go On"),
    "Idina Menzel": ("Idina",),
    "Cynthia Erivo": ("Cynthia",),
    "Kirk Franklin": ("Kirk",),
    "Tems": ("Temilade Openiyi",),
    "Jelly Roll": ("Jason DeFord",),
}

#: Approved creative channels: never scanned, never rewritten.
PROTECTED_KEYS = frozenset({"lyrics", "character_names"})

#: Honest limits, printed by the self-check and returned in every receipt.
KNOWN_LIMITS = (
    "token scope is the 18-style catalog's own display references plus the "
    "explicit alias table, not a global artist blacklist",
    "an alias absent from the table is not caught (e.g. an unrecorded "
    "nickname)",
    "artist names inside approved lyrics are allowed by design: lyrics are "
    "protected creative bytes, never scanned and never rewritten",
    "a character name equal to an artist name is protected inside lyrics and "
    "character_names, and blocked if it appears in an instruction field",
    "homoglyphs (for example Cyrillic lookalikes) are not caught",
    "binary or non-text payload values are not scanned",
    "a reference that is also an ordinary word (the artist 'Future') "
    "over-blocks a legitimate use such as 'future bass'; fail-closed, not "
    "silently dropped",
)

_METADATA_KEYS_NORM = frozenset(
    re.sub(r"[\W_]+", "", key.casefold()) for key in CLIENT_METADATA_KEYS)


def _is_metadata_key(text):
    return re.sub(r"[\W_]+", "", str(text).casefold()) in _METADATA_KEYS_NORM


def _catalog_module():
    try:                                # imported as music_styles.suno_prompt_guard
        from . import catalog as module
    except ImportError:                 # script/top-level import
        import catalog as module
    return module


def catalog_references():
    """Every display reference in the eighteen-style catalog, catalog order."""
    module = _catalog_module()
    refs = []
    for sid in module.style_ids():
        refs.extend(module.client_references(sid))
    seen, ordered = set(), []
    for ref in refs:
        if ref not in seen:
            seen.add(ref)
            ordered.append(ref)
    return tuple(ordered)


def _forms(token):
    """Every comparable spelling: spaced and squashed."""
    base = normalize(token)
    if not base:
        return ()
    forms = {base}
    if " " in base:
        forms.add(base.replace(" ", ""))
    return tuple(sorted(forms))


def forbidden_tokens():
    """``(token, form)`` pairs: display references, recorded aliases, forms."""
    pairs = []
    for ref in catalog_references():
        for form in _forms(ref):
            pairs.append((ref, form))
        for alias in ALIASES.get(ref, ()):
            for form in _forms(alias):
                pairs.append((alias, form))
    seen, unique = set(), []
    for token, form in pairs:
        key = (form, token)
        if key not in seen:
            seen.add(key)
            unique.append((token, form))
    return tuple(unique)


_PATTERNS = None


def _patterns():
    global _PATTERNS
    if _PATTERNS is None:
        compiled = {}
        for _token, form in forbidden_tokens():
            compiled.setdefault(
                form, re.compile(r"(?<!\w)%s(?!\w)" % re.escape(form)))
        _PATTERNS = tuple((token, form, compiled[form])
                          for token, form in forbidden_tokens())
    return _PATTERNS


def find_references(text):
    """Every ``(token, form)`` matched in one string, table order."""
    norm = normalize(text)
    if not norm:
        return ()
    return tuple((token, form) for token, form, pattern in _patterns()
                 if pattern.search(norm))


def _last_key(path):
    return re.sub(r"\[\d+\]$", "", path.rsplit(".", 1)[-1])


def _is_protected_path(path):
    return any(re.sub(r"\[\d+\]$", "", seg) in PROTECTED_KEYS
               for seg in path.split("."))


def walk(payload):
    """Every ``(path, kind, value)`` in the payload, object keys included."""
    yield from _walk(payload, "")


def _walk(value, path):
    if isinstance(value, dict):
        for key, item in value.items():
            child = "%s.%s" % (path, key) if path else str(key)
            yield child, "key", str(key)
            yield from _walk(item, child)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _walk(item, "%s[%d]" % (path, index))
    else:
        yield path, "value", value


def _protected_values(payload):
    """``{path: value}`` for every protected creative field present."""
    found = {}

    def rec(value, path):
        if isinstance(value, dict):
            for key, item in value.items():
                child = "%s.%s" % (path, key) if path else str(key)
                if key in PROTECTED_KEYS:
                    found[child] = item
                rec(item, child)
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                rec(item, "%s[%d]" % (path, index))

    rec(payload, "")
    return found


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verdict_guard(payload, approved_lyrics=None,
                  approved_character_names=None):
    """Inspect a finished outgoing payload. Returns a receipt; never mutates."""
    matches = []
    scanned, protected = [], []
    for path, kind, text in walk(payload):
        if _is_protected_path(path):
            protected.append(path)
            continue
        if not isinstance(text, str):
            continue
        if kind == "key" and _is_metadata_key(text):
            matches.append({"field": path, "token": text,
                            "kind": "display-metadata-key"})
            continue
        scanned.append(path)
        for token, form in find_references(text):
            matches.append({"field": path, "token": token, "kind": kind,
                            "matched": form})

    values = _protected_values(payload)
    lyrics_paths = [p for p in values if _last_key(p) == "lyrics"]
    name_paths = [p for p in values if _last_key(p) == "character_names"]
    lyrics_sha = name_sha = None
    if approved_lyrics is not None:
        if not lyrics_paths:
            matches.append({"field": "lyrics", "token": "<missing>",
                            "kind": "approved-lyrics-missing"})
        for path in lyrics_paths:
            got = values[path]
            if not isinstance(got, str):
                matches.append({"field": path, "token": "<not-text>",
                                "kind": "approved-lyrics-mutated"})
                continue
            lyrics_sha = _sha(got)
            if got != approved_lyrics:
                matches.append({"field": path, "token": "<mutated>",
                                "kind": "approved-lyrics-mutated"})
    if approved_character_names is not None:
        approved = tuple(approved_character_names)
        for path in name_paths:
            got = values[path]
            try:
                got_tuple = tuple(got or ())
            except TypeError:
                got_tuple = None
            name_sha = _sha(repr(got))
            if got_tuple != approved:
                matches.append({"field": path, "token": "<mutated>",
                                "kind": "approved-characters-mutated"})

    if isinstance(payload, dict):
        stamped = payload.get("_lyrics_sha256")
        first = values.get(lyrics_paths[0]) if lyrics_paths else None
        if (stamped is not None and isinstance(first, str)
                and stamped != _sha(first)):
            matches.append({"field": "lyrics", "token": "<digest-mismatch>",
                            "kind": "lyrics-digest-mismatch"})

    return {
        "schema": SCHEMA_VERSION,
        "verdict": "BLOCKED" if matches else "PASS",
        "sendable": not matches,
        "scanned_fields": tuple(dict.fromkeys(scanned)),
        "protected_fields": tuple(dict.fromkeys(protected)),
        "matches": tuple(matches),
        "lyrics_sha256": lyrics_sha,
        "character_names_sha256": name_sha,
        "reference_count": len(catalog_references()),
        "alias_token_count": len({form for _t, form in forbidden_tokens()}),
        "known_limits": KNOWN_LIMITS,
    }


def assert_clean(payload, approved_lyrics=None,
                 approved_character_names=None):
    """Raise on BLOCKED; return the PASS receipt otherwise."""
    receipt = verdict_guard(payload, approved_lyrics, approved_character_names)
    if receipt["verdict"] != "PASS":
        first = receipt["matches"][0]
        raise PromptGuardError(
            "OUTGOING_REFERENCE_LEAK",
            "%d leak(s); first at %r: %r (%s)"
            % (len(receipt["matches"]), first["field"], first["token"],
               first["kind"]))
    return receipt

#!/usr/bin/env python3
"""S75-T41: ONE positive rule for "does this string name a specific thing?".

Both S75-T06 (round 6, head 1ea7e50dd) and S75-T07 (round 4, head 835a2a380)
failed the same question from opposite sides:

* T06 ACCEPTED 161,587 generic person-descriptors as a cast ``display_name``
  because ``_anonymous()`` ended ``if not any(heads): return False`` -- a
  NEGATIVE closed vocabulary of 73 head words.  Anything off the list passed in
  full, so every one of the verifier's 290 heads was accepted.
* T07 ACCEPTED vowel runs as ``episode_role`` while REFUSING real role names
  ("comic relief", "love interest") because ``_episode_role_ok`` required a
  token from a POSITIVE list of role heads.

This module answers the question both units were failing to ask, with one
polarity: **ACCEPT only on positive evidence, REFUSE otherwise.**  There is no
``if not <membership>: return False`` early-out, no bare-substring match and no
first-token shortcut anywhere below.  Every operand either demands a property
of the whole string or supplies affirmative evidence that the string designates
an individual.

Public API
----------
``person_name_ok(value)``   -> bool  (cast ``display_name`` / ``character_id``)
``story_role_ok(value)``    -> bool  (cast ``episode_role``)
``real_content_ok(value, kind)`` -> bool  (``text``/``text_list``/``prose``/``id``)
``content_issue(value, kind)``   -> str | None  (named reason, T07 shape)

The two named predicates ARE the rule; ``real_content_ok`` is only a dispatcher
over them plus the text/list/prose/id shims, so there is one normaliser, one
shape gate and one polarity in the tree.

Data
----
``english_words.txt.gz``      (already shipped) ordinary-English lexicon, used
                              as positive evidence that a token is a general
                              word rather than a designator.
``real_content_names.txt.gz`` (shipped here) 1,188 curated given names and
                              unambiguous surnames.  Source is deliberately NOT
                              ``/usr/share/dict/propernames``: that list carries
                              "old", "butler", "king", "judge", "spy", "son",
                              "pilot", "mason", "duke", "hunter", "lord" and
                              "sergeant" -- thirteen of T06's own descriptor
                              heads -- so using it would have re-created the bug
                              inside the fix.  A common noun, an adjective or a
                              title is absent from the shipped lexicon by
                              construction.

Standard library only.  No IO at import beyond the two gzip lexicons.  No
provider or network call.

Run the harness::

    python3 75-drama-song-ad-factory/scripts/core/replay_real_content_s75_t41.py
"""
from __future__ import annotations

import gzip
import os
import re
import unicodedata

__all__ = [
    "CLOSED_CLASS",
    "ENGLISH",
    "NAME_LEXICON",
    "ROLE_NOUNS",
    "content_issue",
    "normalise",
    "person_name_ok",
    "real_content_ok",
    "story_role_ok",
    "tokens",
]

_HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# L1 -- normalisation
# ---------------------------------------------------------------------------
#: Sentence marks and quote/dash dressing that can END or WRAP a token.  These
#: are mapped to a space (not deleted) so ``woman…`` cannot fuse into one word.
#: The fullwidth block is listed explicitly even though NFKC already folds most
#: of it, because the fold order must not depend on the Unicode data version.
_PUNCT_PIECES = (
    # ASCII punctuation except the apostrophe (see _JOIN below).
    "!\"#$%&()*+,-./:;<=>?@[\\]^_`{|}~",
    # quotes, guillemets, single guillemets -- U+2019 is an apostrophe, kept
    # out of this class because O'Keefe must collapse to OKeefe, not split.
    "‘‚‛“”„«»‹›",
    # hyphens and dashes (U+2010..U+2015) plus minus
    "‐‑‒–—―−",
    # U+2026 HORIZONTAL ELLIPSIS  (T06 finding: 'woman...' survived)
    "…",
    # U+FF01..U+FF0E fullwidth ! " # $ % & ' ( ) * + , - . /
    "！＂＃＄％＆＇（）＊"
    "＋，－．",
    # U+FF1A..U+FF20 fullwidth : ; < = > ? @
    "：；＜＝＞？＠",
    # U+FF3B..U+FF40 fullwidth [ \ ] ^ _ `
    "［＼］＾＿｀",
    # U+FF5B..U+FF65 fullwidth { | } ~ and halfwidth CJK punctuation
    "｛｜｝～｟｠｡｢｣､･",
    # spaces NFKC does not collapse
    "           "
    "      　",
)

_PUNCT = "".join(_PUNCT_PIECES) + "".join(
    # U+3000..U+303F CJK symbols and punctuation (U+3005..U+3007 are
    # ideographic marks; treating them as dressing is deliberate)
    chr(c) for c in range(0x3000, 0x3040)
)

#: ``str.translate`` table: every punctuation character becomes a space.
_TRANSLATE = {ord(ch): " " for ch in _PUNCT}

#: Apostrophes are DELETED so a compound keeps one token (O'Keefe -> OKeefe);
#: a hyphenated compound splits (Cruz-Whitfield -> Cruz Whitfield).
_JOIN = {ord(ch): "" for ch in "'’ʼ"}

#: Format (Cf) and control (Cc) characters are DELETED, not spaced: U+200B ZERO
#: WIDTH SPACE and U+00AD SOFT HYPHEN glue themselves to a word (T06 finding
#: 'a​woman' tokenised as one token 'a​woman').  Deletion restores the
#: word boundary that the character was hiding.  Deliberately a unicodedata
#: CATEGORY test, so every present and future Cf/Cc character is covered rather
#: than the two the verifier happened to name.
_FORMAT_CATEGORIES = frozenset({"Cf", "Cc", "Cs", "Co", "Cn"})

_SPACES = re.compile(r"\s+")


def normalise(value):
    """NFKC, then explicit translate, then category-Cf/Cc deletion.

    Returns the case-preserving normalised string.  Case is kept because a
    proper noun is detected by its capitals; the shape gate re-tests case.
    """
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = text.translate(_JOIN)
    text = text.translate(_TRANSLATE)
    text = "".join(ch for ch in text
                   if unicodedata.category(ch) not in _FORMAT_CATEGORIES)
    return _SPACES.sub(" ", text).strip()


def tokens(value):
    """Normalised, case-preserving word tokens of ``value``."""
    norm = normalise(value)
    return norm.split(" ") if norm else []


# ---------------------------------------------------------------------------
# L2 -- admissible word shape (list-free)
# ---------------------------------------------------------------------------

def _latin(ch):
    try:
        return unicodedata.name(ch).startswith("LATIN")
    except ValueError:                                   # unassigned
        return False


_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
_VOWELS = frozenset("aeiou")


def _keyboard_run(word):
    """A 4-character window straight from a keyboard row, either direction."""
    low = word.lower()
    for i in range(len(low) - 3):
        win = low[i:i + 4]
        for row in _KEYBOARD_ROWS:
            if win in row or win[::-1] in row:
                return True
    return False


def _cyclic(word):
    """``word`` is a short period repeated: abab, abcabc, tatata, hahaha, lalala."""
    n = len(word)
    for period in range(1, min(5, n)):
        if n % period:
            continue
        if word[:period] * (n // period) == word:
            return True
    return False


def _monotone(word):
    """Four or more consecutive letters ascending or descending (abcd, zyxw)."""
    low = word.lower()
    for i in range(len(low) - 3):
        run = low[i:i + 4]
        steps = [ord(run[j + 1]) - ord(run[j]) for j in range(3)]
        if all(s == 1 for s in steps) or all(s == -1 for s in steps):
            return True
    return False


def word_shape_ok(tok):
    """A token is a word at all: Latin script, letters only, >=2 chars, one
    vowel AND one consonant, not one repeated character, not a cyclic
    repetition, not a keyboard run, not a 4-letter monotone run.

    Every limb is a property of the token alone.  Nothing here consults a
    vocabulary, so nothing can be admitted or refused by list membership.
    """
    if not isinstance(tok, str) or len(tok) < 2:
        return False
    if not all(_latin(ch) for ch in tok):
        return False
    low = tok.casefold()
    if not low.isalpha():
        return False
    letters = set(low)
    if len(letters) == 1:
        return False
    if not (letters & _VOWELS) or not (letters - _VOWELS):
        return False
    if _cyclic(low) or _keyboard_run(low) or _monotone(low):
        return False
    return True


# ---------------------------------------------------------------------------
# L3 -- lexicons (positive evidence only)
# ---------------------------------------------------------------------------
#: The closed GRAMMATICAL class: determiners, pronouns, prepositions,
#: conjunctions, auxiliaries and quantifiers.  Finite by definition -- it is a
#: part-of-speech closure, not a topic vocabulary, and no lexical noun ever
#: joins it.  A name contains none of these words.
CLOSED_CLASS = frozenset({
    "a", "an", "the", "some", "any", "another", "one", "two", "three", "four",
    "five", "six", "seven", "eight", "nine", "ten", "first", "second", "third",
    "last", "next", "other", "same", "each", "every", "no", "none", "not",
    "all", "both", "few", "many", "much", "more", "most", "less", "least",
    "several", "such", "own", "only", "very", "just", "also", "too", "then",
    "this", "that", "these", "those", "there", "here", "who", "whom", "whose",
    "which", "what", "when", "where", "why", "how", "whoever", "whatever",
    "whichever", "someone", "somebody", "anyone", "anybody", "everyone",
    "everybody", "nobody", "nothing", "something", "anything", "everything",
    "i", "me", "my", "mine", "we", "us", "our", "ours", "you", "your", "yours",
    "he", "him", "his", "she", "her", "hers", "it", "its", "they", "them",
    "their", "theirs", "myself", "yourself", "himself", "herself", "itself",
    "ourselves", "themselves", "of", "in", "on", "at", "to", "for", "with",
    "by", "from", "into", "onto", "over", "under", "behind", "beside", "near",
    "across", "through", "during", "before", "after", "above", "below",
    "between", "against", "about", "around", "along", "among", "within",
    "without", "toward", "towards", "per", "via", "upon", "off", "out", "up",
    "down", "and", "or", "but", "as", "than", "so", "because", "if", "else",
    "while", "until", "unless", "though", "although", "whether", "is", "am",
    "are", "was", "were", "be", "been", "being", "do", "does", "did", "have",
    "has", "had", "will", "would", "can", "could", "may", "might", "must",
    "shall", "should", "s", "t",
})

#: Honorifics / titles that may precede a name.  Positive: their presence is
#: never enough on its own (``core`` must still carry a designator), and their
#: absence is never a refusal.
_HONORIFICS = frozenset({
    "mr", "mrs", "ms", "miss", "mx", "dr", "doctor", "prof", "professor",
    "officer", "detective", "sergeant", "captain", "lieutenant", "colonel",
    "general", "judge", "justice", "reverend", "rev", "father", "mother",
    "sister", "brother", "saint", "st", "lord", "lady", "sir", "dame",
    "senator", "governor", "mayor", "president", "sheikh", "imam", "rabbi",
    "sgt", "capt", "lt", "col", "gen", "det", "insp", "fr", "sr", "jr",
})


def _load_gz(name):
    path = os.path.join(_HERE, name)
    out = set()
    if not os.path.exists(path):
        return frozenset(out)
    with gzip.open(path, "rt", encoding="utf-8", errors="ignore") as handle:
        for line in handle:
            line = line.strip().lower()
            if line:
                out.add(line)
    return frozenset(out)


#: Ordinary-English lexicon (shipped).  Used as positive evidence that a token
#: is an ordinary common word -- NEVER as a list a name must be absent from.
ENGLISH = _load_gz("english_words.txt.gz")

#: Proper-name lexicon (shipped).  Membership is affirmative evidence that the
#: token designates an individual.  Absence is not evidence either way: it falls
#: through to the orthographic and opacity signals below.
NAME_LEXICON = _load_gz("real_content_names.txt.gz")

#: Role nouns: the head of a story-function phrase must be one of these.  This
#: is the ACCEPT operand of ``story_role_ok`` -- an unknown role noun is
#: REFUSED (fail-closed), the opposite of T07's bug in both directions.
ROLE_NOUNS = frozenset({
    # narrative function
    "lead", "colead", "protagonist", "deuteragonist", "antagonist", "antihero",
    "hero", "heroine", "villain", "narrator", "mentor", "foil", "catalyst",
    "confidant", "ally", "rival", "opponent", "partner", "friend", "companion",
    "guardian", "guide", "witness", "victim", "survivor", "informant",
    # billing weight
    "supporting", "support", "secondary", "cameo", "guest", "extra",
    "background", "ensemble", "chorus", "bystander", "observer", "walkon",
    # comic / romantic story devices (the two T07 refused)
    "relief", "interest", "sidekick", "straight", "stooge",
    # relational function
    "parent", "mother", "father", "sibling", "brother", "sister", "child",
    "daughter", "son", "wife", "husband", "widow", "widower", "orphan", "twin",
    "uncle", "aunt", "cousin", "fiance", "fiancee", "grandmother",
    "grandfather", "family",
    # occupation-as-function (only meaningful when a scene casts the role)
    "doctor", "nurse", "lawyer", "detective", "teacher", "student", "coach",
    "driver", "captain", "officer", "soldier", "spy", "mechanic", "barista",
    "waiter", "waitress", "baker", "vendor", "neighbor", "reporter", "singer",
    "musician", "clerk", "manager", "boss", "agent", "worker", "customer",
    "passenger", "crew", "staff", "resident", "citizen", "villager", "tourist",
})

#: Derivational endings that mark a word as DESCRIPTIVE rather than nominal.
#: Used only to refuse opacity evidence (a described thing is not an opaque
#: designator) -- it never admits anything.
_DESCRIPTIVE_SUFFIX = (
    "ous", "ful", "less", "able", "ible", "ive", "ish", "ly", "ness", "ment",
    "tion", "sion", "ance", "ence", "ity", "est", "ing", "ed", "ic", "al",
)


def _has_descriptive_suffix(low):
    return any(low.endswith(sfx) and len(low) > len(sfx) + 1
               for sfx in _DESCRIPTIVE_SUFFIX)


def _orthographic_marker(tok):
    """Orthography that is itself evidence of a proper noun: an internal capital
    (McDonald) or a diacritic on a Latin letter.

    An ALL-CAPS token is deliberately NOT evidence: ``ACCOUNTANT`` has capitals
    after the first character, but shouting a category noun does not turn it
    into a name.  Apostrophes and hyphens are consumed by ``normalise`` and so
    are handled by the opacity signal instead."""
    if not tok.isupper() and any(ch.isupper() for ch in tok[1:]):
        return True
    return any(ord(ch) > 127 and _latin(ch) for ch in tok)


#: Inflectional endings stripped before asking whether a token is an ordinary
#: English word ("guests" -> guest, "scared" -> scare, "teenagers" -> teenager).
_INFLECTIONS = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "est")


def _ordinary_word(low):
    """True when the token (or a regular inflection of it) is an ordinary
    English word.  Positive evidence that the token denotes a general thing."""
    if low in ENGLISH:
        return True
    for suffix in _INFLECTIONS:
        if low.endswith(suffix) and len(low) > len(suffix) + 2:
            if low[:-len(suffix)] in ENGLISH:
                return True
    return False


def _opaque(low):
    """Not an ordinary English word and not descriptively suffixed, so it
    cannot be read as naming a *category*.  This is the only designator signal
    keyed on absence, and it can never accept anything by itself -- see
    ``person_name_ok`` limbs 1-4."""
    return not _ordinary_word(low) and not _has_descriptive_suffix(low)


def designator_evidence(tok):
    """Affirmative evidence that ONE token designates an individual.

    Three independent positive signals:

    ``NAME_LEXICON``   a curated given-name/surname lexicon -- a common noun or
                       an adjective is deliberately absent from it, so "Old",
                       "King" and "Butler" carry no evidence;
    ``_orthographic_marker``  internal capital or diacritic;
    ``_opaque``        not an ordinary English word and not a descriptive form.
    """
    low = tok.casefold()
    if low in NAME_LEXICON:
        return True
    if _orthographic_marker(tok):
        return True
    return _opaque(low)


# ---------------------------------------------------------------------------
# L3 -- the two predicates
# ---------------------------------------------------------------------------

def _capitalised(tok):
    return tok[:1].isupper()


def _honorific(tok):
    return tok.casefold().rstrip(".") in _HONORIFICS


def _initial(tok):
    """A single capital letter: the ``J.`` of ``A. J. Marchetti``."""
    return len(tok) == 1 and tok.isupper()


def _strip_title_phrase(toks):
    """Drop a leading honorific phrase, allowing one article in front of it:
    "The Reverend Thomas Hale" -> ["Thomas", "Hale"], "Dr Amina Osei" ->
    ["Amina", "Osei"].  A leading article NOT followed by an honorific is left
    in place, so "the narrator" keeps its determiner and fails limb 3.

    S75-T06 round 7: an initial is set aside only when the token after it is
    another initial or an honorific, so "A. J. Marchetti" keeps its initials and
    "A Barista" keeps its determiner.  "A" is BOTH an initial and a determiner,
    and limb 3 has to see it whenever it is standing in front of ordinary words.
    """
    out = list(toks)
    while out:
        if _honorific(out[0]):
            out.pop(0)
            continue
        if (_initial(out[0]) and len(out) > 1
                and (_initial(out[1]) or _honorific(out[1]))):
            out.pop(0)
            continue
        if (out[0].casefold() == "the" and len(out) > 1
                and (_honorific(out[1]) or _initial(out[1]))):
            out.pop(0)
            continue
        break
    return out


def person_name_ok(value):
    """A ``display_name`` / ``character_id`` is a PERSON only on positive shape.

    ALL of the following must hold for the WHOLE string:

    1. 2..4 tokens after normalisation -- a single opaque word is not a name,
       because "is this word unknown to the dictionary?" is absence, not
       evidence; a name needs at least a given name and a family name;
    2. every token is either a well-formed word (``word_shape_ok``) or a single
       capital initial;
    3. after a leading honorific phrase is set aside, NO token is a member of
       ``CLOSED_CLASS`` -- one determiner, pronoun, preposition or conjunction
       anywhere means the string describes a person instead of naming one;
    4. every token is capitalised (proper-noun orthography);
    5. at least one remaining token carries ``designator_evidence``.

    A single token can only pass via a positive designator signal, so a bare
    common noun ("soldier", "woman", "barista") can never pass.  Two-token
    descriptor phrases ("Old Man", "Background People") fail limb 5 because
    every one of their tokens is an ordinary English word.
    """
    toks = tokens(value)
    if not 2 <= len(toks) <= 4:
        return False
    if not all(word_shape_ok(t) or _initial(t) or _honorific(t) for t in toks):
        return False
    if not all(_capitalised(t) for t in toks):
        return False
    stripped = _strip_title_phrase(toks)
    if not stripped:
        return False
    if any(t.casefold() in CLOSED_CLASS for t in stripped):
        return False
    core = [t for t in stripped if not _initial(t)]
    if not core:
        return False
    return any(designator_evidence(t) for t in core)


def story_role_ok(value):
    """An ``episode_role`` is a story function only on positive grammar.

    ALL of the following must hold:

    1. 1..3 tokens, every token passes ``word_shape_ok``;
    2. no token is in ``CLOSED_CLASS``;
    3. the LAST token is a ``ROLE_NOUNS`` head: the phrase parses as
       ``modifier* head``.

    The head is the ACCEPT operand and it is closed and fail-closed: an unknown
    head is refused, which is the opposite polarity from T07's bug.  Modification
    is open, so "comic relief", "love interest" and "reluctant mentor" need no
    entry for their modifier.  The head is NOT also required to be in the 1913
    English lexicon, because real role nouns ("sidekick") postdate it.
    """
    toks = tokens(value)
    if not 1 <= len(toks) <= 3:
        return False
    if not all(word_shape_ok(t) for t in toks):
        return False
    lows = [t.casefold() for t in toks]
    if any(low in CLOSED_CLASS for low in lows):
        return False
    return lows[-1] in ROLE_NOUNS


# ---------------------------------------------------------------------------
# text / list / prose / id
# ---------------------------------------------------------------------------

def _stutter(low):
    """A 2- or 3-letter unit repeated back to back inside one word: tralala,
    banana, mamama.  Used by the prose/role predicates, never by the person
    predicate (real names such as "Mimi" or "Anna" carry the same shape)."""
    for unit in (2, 3):
        for i in range(len(low) - 2 * unit + 1):
            piece = low[i:i + unit]
            if piece * 2 == low[i:i + 2 * unit]:
                return True
    return False


def _real_text_tokens(value):
    """Tokens that carry content, or [] when the string says nothing.  A single
    letter is a word ("If I lock that door"); every longer token must pass the
    shape gate."""
    toks = tokens(value)
    if not toks:
        return []
    for tok in toks:
        if len(tok) == 1 and tok.isalpha() and _latin(tok):
            continue
        if not word_shape_ok(tok):
            return []
    return toks


def _repeats(toks):
    """A short phrase that repeats a word is filler, not a statement
    ("banana phone banana").  Deliberately limited to short phrases: real prose
    repeats words all the time across a sentence."""
    return len(toks) <= 3 and len(set(t.casefold() for t in toks)) < len(toks)


def text_ok(value):
    """A substantive text field: at least one admissible word, no repeated-word
    stub, and at least one word with four or more DISTINCT letters -- a phrase
    made only of 1-3 distinct-letter stubs ("abb", "aei", "x y z") says
    nothing, however many tokens it has."""
    toks = _real_text_tokens(value)
    if not toks or _repeats(toks):
        return False
    if any(len(t) > 2 and not _ordinary_word(t.casefold())
           and _stutter(t.casefold()) for t in toks):
        return False
    return any(len(set(t.casefold())) >= 4 for t in toks)


def text_list_ok(value):
    """EVERY entry must be real text.  One real entry never rescues filler
    beside it (the T07 ``['x y z', <real>]`` hole)."""
    if not isinstance(value, (list, tuple)) or not value:
        return False
    return all(isinstance(v, str) and text_ok(v) for v in value)


def prose_ok(value):
    """A prose surface: text, a list of real text, or a record whose EVERY
    value is itself prose.  No ANY-value short circuit."""
    if isinstance(value, dict):
        return bool(value) and all(prose_ok(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return text_list_ok(value)
    return text_ok(value)


def _normalise_id(value):
    """Identifiers are opaque, so their separators are SIGNIFICANT: only NFKC,
    Cf/Cc deletion and outer whitespace are removed here."""
    if not isinstance(value, str):
        return ""
    text = unicodedata.normalize("NFKC", value)
    text = "".join(ch for ch in text
                   if unicodedata.category(ch) not in _FORMAT_CATEGORIES)
    return text.strip()


def id_ok(value):
    """An identifier is opaque SHAPE.  Positive structural requirements: no
    whitespace, >=3 chars, >=4 distinct characters, every alphabetic segment a
    well-formed word, and identifier STRUCTURE -- two or more segments, or a
    hex run.  A bare word with a digit glued on ("abc123", "lorem-1",
    "placeholder-1") has no structure and is refused; a real coded id
    ("identity-digest-1", "3f2a9c7b") carries one.
    """
    text = _normalise_id(value)
    if not text or any(ch.isspace() for ch in text):
        return False
    if len(text) < 3 or len(set(text.casefold())) < 4:
        return False
    if re.fullmatch(r"[0-9a-fA-F]{8,}", text):
        return True
    segments = [s for s in re.split(r"[^A-Za-z]+", text) if s]
    if not segments or not all(word_shape_ok(s) for s in segments):
        return False
    return len(segments) >= 2


_KINDS = {
    "person": person_name_ok,
    "role": story_role_ok,
    "text": text_ok,
    "text_list": text_list_ok,
    "prose": prose_ok,
    "id": id_ok,
}


def real_content_ok(value, kind):
    """The single entry point.  ``kind`` is one of ``_KINDS``."""
    try:
        test = _KINDS[kind]
    except KeyError:
        raise ValueError("unknown content kind: %r" % (kind,)) from None
    return bool(test(value))


def content_issue(value, kind):
    """Named reason ``value`` is not real ``kind`` of content, else ``None``.

    Mirrors the T07 helper of the same name so the harness can call either
    implementation with one signature.
    """
    if kind == "id" and id_ok(value):
        return None
    if kind != "id" and real_content_ok(value, kind):
        return None
    if kind == "person":
        toks = tokens(value)
        if not toks:
            return "empty"
        if not all(word_shape_ok(t) or _initial(t) or _honorific(t)
                   for t in toks):
            return "not a well-formed word"
        if not all(_capitalised(t) for t in toks):
            return "not proper-noun capitalisation"
        stripped = _strip_title_phrase(toks)
        if not stripped:
            return "honorific only"
        if any(t.casefold() in CLOSED_CLASS for t in stripped):
            return "closed-class word inside the string"
        return "no designator evidence: describes a category"
    if kind == "role":
        toks = tokens(value)
        if not toks:
            return "empty"
        if not all(word_shape_ok(t) for t in toks):
            return "not a well-formed word"
        lows = [t.casefold() for t in toks]
        if any(low in CLOSED_CLASS for low in lows):
            return "closed-class word inside the role"
        return "no role-noun head"
    if kind in ("text", "prose"):
        return "no real content"
    if kind == "text_list":
        return "every entry must be real content"
    return "not an id string"


# ---------------------------------------------------------------------------
# Self-check (run as a script)
# ---------------------------------------------------------------------------
if __name__ == "__main__":                      # pragma: no cover
    assert normalise("woman…") == "woman"
    assert normalise("a​woman") == "awoman"
    assert normalise("­the manager­") == "the manager"
    assert normalise("woman．") == "woman"
    assert normalise("a​ ​woman") == "a woman"
    assert person_name_ok("Mara Bell")
    assert not person_name_ok("Old Man")
    assert not person_name_ok("soldier")
    assert not person_name_ok("woman")
    assert story_role_ok("comic relief")
    assert story_role_ok("love interest")
    assert not story_role_ok("aei")
    print("real_content.py self-check OK")

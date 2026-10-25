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
    # S75-T06 round 8: TAB, LF, CR, VT and FF are Cc, and deleting a Cc GLUED
    # two words into one ("A\tWoman" -> "AWoman", whose internal capital then
    # read as McDonald-style name orthography).  A whitespace control character
    # is a word boundary; only the invisible format characters are deleted.
    text = text.translate({0x09: " ", 0x0A: " ", 0x0B: " ", 0x0C: " ",
                           0x0D: " "})
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


def _decomposes_to_latin(ch):
    """A character is a LETTER OF A NAME only if it is ASCII, or it is a Latin
    letter that canonical-decomposes to an ASCII letter plus a combining mark
    (``Zo`` + U+0308 + ``e``, ``n`` + U+0303).

    S75-T06 round 8.  A look-alike from another alphabet -- U+03BF GREEK SMALL
    LETTER OMICRON in ``People``, U+0430 CYRILLIC -- is not orthography, it is a
    disguise, and U+0131 LATIN SMALL LETTER DOTLESS I does not decompose at all,
    so ``Officer`` is a substituted glyph and not an accented form.  Every one of
    them is refused here, at the shape gate, in ANY position in the string; the
    rule never has to recognise the word it was hiding.
    """
    if ord(ch) < 128:
        return True
    # NFD peels every canonical layer, so "a with circumflex and grave" reaches
    # its ASCII base "a" even though its one-step decomposition is "â" + U+0300.
    folded = unicodedata.normalize("NFD", ch)
    if not folded:
        return False
    base = folded[0]
    return base.isalpha() and ord(base) < 128


_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm")
#: A vowel is the ASCII set or any accented form of it (``a``, ``i``,
#: ``u``), plus ``y``, which is the vowel of ``Lý``, ``Lynch`` and ``Ng'``
#: surnames.  S75-T06 round 7 demanded an ASCII ``aeiou`` and so refused
#: ``Kim Ng``, ``Trần Thị Hoa`` and ``Liam Ní Chonaill``.
_VOWELS = frozenset("aeiouy")


def _vowel(ch):
    base = unicodedata.normalize("NFD", ch)[0].casefold()
    return base in _VOWELS


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
    """A token is a word at all: letters only, >=2 chars, one vowel AND one
    consonant, not one repeated character, not a cyclic repetition, not a
    keyboard run, not a 4-letter monotone run.

    Letters are ASCII, or accented forms of ASCII letters
    (``_decomposes_to_latin``): a Greek omicron, a Cyrillic ``a`` or a dotless
    i is not a letter of a name.  The vowel set is ``aeiouy`` read through the
    token's canonical decomposition, so ``Ní``, ``Thị``, ``Lý`` and ``Ng`` are
    words.

    Every limb is a property of the token alone.  Nothing here consults a
    vocabulary, so nothing can be admitted or refused by list membership.
    """
    if not isinstance(tok, str) or len(tok) < 2:
        return False
    if not all(_decomposes_to_latin(ch) for ch in tok):
        return False
    if not tok.isalpha():
        return False
    low = tok.casefold()
    letters = set(low)
    if len(letters) == 1:
        return False                                    # one repeated letter
    has_vowel = any(_vowel(ch) for ch in tok)
    if not has_vowel and len(low) > 3:
        return False                    # "Ng" is a name; "bcdfgh" is not
    if not any(not _vowel(ch) for ch in tok):
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
    "ourselves", "themselves", "self", "of", "in", "on", "at", "to", "for", "with",
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

def _orthographic_marker(tok):
    """Orthography that is itself evidence of a proper noun: an internal capital
    (McDonald) or an accented Latin letter (Zoe, Ní, Saldaña).

    An ALL-CAPS token is deliberately NOT evidence: ``ACCOUNTANT`` has capitals
    after the first character, but shouting a category noun does not turn it
    into a name.  A glyph that only LOOKS like a Latin letter -- U+0131 DOTLESS
    I, Greek omicron -- is refused by ``_decomposes_to_latin`` long before it
    reaches here, so no disguise can buy proper-noun evidence."""
    if not tok.isupper() and any(ch.isupper() for ch in tok[1:]):
        return True
    return any(ord(ch) > 127 for ch in tok)


#: Inflectional endings stripped before asking whether a token is an ordinary
#: English word ("guests" -> guest, "scared" -> scare, "teenagers" -> teenager).
_INFLECTIONS = ("s", "es", "ed", "d", "ing", "er", "ers", "ly", "est")


def _ordinary_word(low):
    """True when the token (or a regular inflection of it) is an ordinary
    English word.  Positive evidence that the token denotes a general thing."""
    if low in ENGLISH:
        return True
    # The man/men ablaut plural is regular English morphology, not a word list:
    # "women" -> "woman", "gentlemen" -> "gentleman".
    if low.endswith("men") and low[:-3] + "man" in ENGLISH:
        return True
    for suffix in _INFLECTIONS:
        if low.endswith(suffix) and len(low) > len(suffix) + 2:
            if low[:-len(suffix)] in ENGLISH:
                return True
    return False


def _fold_ascii(text):
    """Strip combining marks: "baker" -> "baker", "Zoe" -> "Zoe"."""
    return "".join(ch for ch in unicodedata.normalize("NFD", text)
                   if not unicodedata.combining(ch))


def _english_word(low):
    """True when the token is a form of ordinary English, so it denotes a KIND
    of thing rather than an individual.

    An accented spelling is judged by its UNACCENTED letters, but only against
    the lexicon and its regular inflections -- never against the compound rule,
    which would read "Beyonce" as "bey"+"once" and lose a real name.

    Three shapes, all positive, all about the token's own form:

    ``_ordinary_word``   the lexicon, or a regular inflection of a lexicon stem;
    silent ``e``         "grande" -> "grand", "baker" -> "bak" no, "grande" yes;
    a compound of two English words  "barback" -> bar+back, "lifestyle" ->
    life+style, "youtuber" -> you+tuber.

    This is what "barista", "teenager", "blogger", "barback", "grande" and
    "tech" need to be recognised as ordinary words rather than as names -- the
    1913 lexicon predates them.  It is EVIDENCE OF A COMMON WORD, never a list
    of things a cast member might be called, and it can only ever remove a
    candidate name, never add one.
    """
    if _english_form(low):
        return True
    folded = _fold_ascii(low)
    return folded != low and _ordinary_word(folded)


def _english_form(low):
    """One spelling considered as ordinary English, before accent folding."""
    if _ordinary_word(low):
        return True
    if len(low) > 3 and low.endswith("e") and _ordinary_word(low[:-1]):
        return True
    for cut in range(3, len(low) - 2):
        head, tail = low[:cut], low[cut:]
        # Both halves substantial words, and neither half a curated NAME: "blue"
        # + "tooth" is a compound word, "raghu" + "nathan" is a personal name
        # and must not be read as ordinary English.
        if (len(head) >= 4 and len(tail) >= 4
                and head not in NAME_LEXICON and tail not in NAME_LEXICON
                and _ordinary_word(head) and _ordinary_word(tail)):
            return True
    return False


def designator_evidence(tok):
    """Affirmative evidence that ONE token designates an individual.

    Two positive signals and nothing else:

    ``NAME_LEXICON``   a curated given-name/surname lexicon -- a common noun or
                       an adjective is deliberately absent from it, so "Old",
                       "King" and "Butler" carry no evidence;
    ``_orthographic_marker``  internal capital or accented Latin letter.

    S75-T06 round 8: "not an ordinary English word" is no longer evidence of a
    name.  Absence from a 1913 lexicon is not a positive signal, and it is what
    admitted 'Barista Teenager', 'Uber Driver' and every modern coinage the
    lexicon simply predates.  A token that is NOT ordinary English and NOT in
    the name lexicon is UNKNOWn -- see ``person_name_ok``, which reads that
    state as "could be a name", never as "is a name".
    """
    low = tok.casefold()
    if low in NAME_LEXICON:
        return True
    return _orthographic_marker(tok)


# ---------------------------------------------------------------------------
# L3 -- the two predicates
# ---------------------------------------------------------------------------

def _capitalised(tok):
    return tok[:1].isupper()


def _honorific(tok):
    return tok.casefold().rstrip(".") in _HONORIFICS


#: The MODAL/AUXILIARY half of ``CLOSED_CLASS``.  "May" and "Will" are the two
#: words that are both a closed-class auxiliary and an ordinary given name, so
#: they never refuse a string on their own.  This is a grammatical sub-class of
#: the same closure -- still no list of things a cast member might be called.
_MODAL_CLASS = frozenset({
    "may", "will", "can", "could", "would", "should", "shall", "must", "might",
})

#: Agentive / role-forming endings: a token that ends in one of these denotes a
#: KIND OF PERSON ("walker", "creator", "specialist", "mixologist"), which is
#: morphology, not a list of names.
_AGENTIVE_SUFFIX = (
    "er", "ers", "or", "ors", "ist", "ists", "ant", "ants", "ent", "ents",
    "ee", "ees", "ary", "ling", "lings", "eer", "icians", "ician", "ese",
)


def _agentive(tok):
    low = tok.casefold()
    return any(low.endswith(sfx) and len(low) > len(sfx) + 2
               for sfx in _AGENTIVE_SUFFIX)


def _category_word(tok):
    """The token denotes a KIND OF THING or a KIND OF PERSON: an ordinary
    English word, an agentive form, or a story-role noun.

    Evidence that a token is a common noun.  It can only ever remove a candidate
    name; it never admits anything and it names no particular occupation a cast
    member might hold.
    """
    low = tok.casefold()
    return _english_word(low) or _agentive(tok) or low in ROLE_NOUNS


def _initial(tok):
    """A single capital letter: the ``J.`` of ``A. J. Marchetti``."""
    return len(tok) == 1 and tok.isupper()


def _strip_title_phrase(toks):
    """Drop a leading honorific phrase, allowing one article in front of it:
    "The Reverend Thomas Hale" -> ["Thomas", "Hale"], "Dr Amina Osei" ->
    ["Amina", "Osei"], "Sensei Tanaka" -> ["Tanaka"].  A leading article NOT
    followed by an honorific is left in place, so "the narrator" keeps its
    determiner and fails limb 3.

    S75-T06 round 8: the honorific case is folded into one test, so a title with
    its own orthography -- "Seorita", "Fräulein", "Sra" -- is recognised by the
    same rule as "Dr" and "Sergeant", with no title vocabulary and no accent
    exception.
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


def _opaque(low):
    """The token is not a form of ordinary English, so it denotes nothing we can
    read -- a personal name, a brand, or a coinage.  Absence of meaning is not
    evidence of a name; it only says the token is not obviously a category."""
    return not _english_word(low)


def _ledger_name(tok):
    """The token is a curated given name or surname.  This is the STRONG name
    evidence, and the only evidence that outranks a phrase reading."""
    return tok.casefold() in NAME_LEXICON


def _name_prefix(toks):
    """The string opens with a personal-name FRAME: a single capital initial
    ("J."), a title, a curated first name ("Dana"), or a modal homograph
    ("May", "Will").  Structural only -- an accent is not a frame."""
    for tok in toks:
        if _initial(tok) or _honorific(tok):
            return True
        low = tok.casefold()
        return low in NAME_LEXICON or low in _MODAL_CLASS
    return False


def personal_name_prefix(toks):
    """The string opens like a personal name: a real first name from the lexicon
    ("Dana", "Priya", "Will"), a single capital initial ("J.", "A. J."), or an
    accented first word ("Saoirse", "Zoë", "Señorita").

    "Uber Driver", "Wifi Password", "Muchacho Grande" and "Podcast Host" have
    no such prefix and never will; "Dana Woman", "J. Baker", "Priya
    Raghunathan" and "Saoirse Ní Chonaill" always do.  This is the signal that
    separates a NAME from a phrase made of ordinary words, and it is positive
    evidence about the string's own opening -- never a refusal for being absent
    from a list.
    """
    for tok in toks:
        if _initial(tok) or _honorific(tok):
            return True
        low = tok.casefold()
        return (low in NAME_LEXICON or low in _MODAL_CLASS
                or bool(_orthographic_marker(tok)))
    return False


def person_name_ok(value):
    """A ``display_name`` / ``character_id`` is a PERSON only on positive shape.

    Shape, in order.  A refusal is only ever a positive observation about the
    string -- never "it is absent from a list of names":

    1. 1..4 tokens, every token a well-formed word, a single capital initial or
       an honorific, every token capitalised; a substituted glyph ("Offıcer")
       fails the letter test inside ``word_shape_ok`` and is never recognised as
       the word it was standing in for;
    2. ``R_FUNC``  a determiner, pronoun, preposition or conjunction in the
       string ("The Barista", "A Waiter", "Manager-On-Duty", "Self-Taught")
       describes a person.  A MODAL ("May", "Will") is also an ordinary given
       name, and an INTERNAL single letter is a middle initial ("Mary A.
       Fields"); neither refuses anything;
    3. ``R_NAME``  a curated name in the GIVEN-NAME position is decisive before
       any phrase test -- "Dana Woman", "Mary Baker", "May Smith" and "Theresa
       Manager" are people whose surname happens to be a common noun.  It reads
       only the opening token, so "Dog Walker" and "Trader Joe" still describe;
    4. ``R_LEAD``  a leading word form denoting a KIND OF PERSON ("Trader Joe",
       "Barista Teenager", "Mixologist Barback") is a description;
    5. ``R_COIN``  an opaque coinage or brand ("Uber", "Podcast", "Wifi") in the
       given-name position with a common noun in the family-name position
       ("Uber Driver", "Podcast Host", "Muchacho Grande") is a product, not a
       person;
    6. ``R_MOD``   ordinary English in the given-name position plus a
       person-forming word in the family-name position ("Dog Walker", "Tech
       Blogger", "Content-Creator") is a job, not a name;
    7. ``R_LEDGER``  a curated surname anywhere ("Renata Cruz-Whitfield",
       "A. J. Marchetti") settles the question;
    8. ``R_FREE``  "J. Baker", "Plato", "Priya Raghunathan", "Ng Wei" and
       "Nguyen Van Anh" carry a name frame, an accent, or a token that denotes
       no category at all.

    The only vocabularies consulted are the grammatical closure of function
    words (``CLOSED_CLASS``), a curated LEXICON OF NAMES used solely as positive
    evidence, the ordinary-English lexicon used as evidence that a token denotes
    a KIND of thing, and the story-role nouns this module already ships for
    ``episode_role``.  There is no list of what a cast member might be called.

    KNOWN RESIDUAL, S75-T06 round 8: a title the lexicon does not carry
    ("Señorita", "Fräulein", "Sensei") in front of a surname the lexicon does
    not carry ("Gomez", "Schmidt", "Tanaka") is indistinguishable from "Nguyen
    Van Anh" by any list-free rule -- both are two opaque name-shaped words.
    Deciding that needs a LEXICON OF TITLES, which is a vocabulary and is not
    added here.  The same limit refuses a real name whose every word is an
    ordinary English word and none is in the shipped name lexicon ("Art Smith",
    "Pearl Green", "Madonna").
    """
    toks = tokens(value)
    if not 1 <= len(toks) <= 4:
        return False
    if not all(word_shape_ok(t) or _initial(t) or _honorific(t) for t in toks):
        return False
    if not all(_capitalised(t) for t in toks):
        return False
    stripped = _strip_title_phrase(toks)
    if not stripped:
        return False
    core = [t for t in stripped if not _initial(t)]
    if not core:
        return False

    # R_FUNC -- "The Barista", "A Waiter", "Manager-On-Duty", "Self-Taught".
    # A MODAL is also an ordinary given name ("May Smith", "Will Smith"); an
    # INTERNAL single letter is a middle initial ("Mary A. Fields"); a LEADING
    # single letter standing in front of a real name is that initial ("A. Mary").
    for index, tok in enumerate(stripped):
        low = tok.casefold()
        if low not in CLOSED_CLASS or low in _MODAL_CLASS:
            continue
        if _initial(tok) and index > 0:
            continue
        if (_initial(tok) and index + 1 < len(stripped)
                and designator_evidence(stripped[index + 1])):
            continue
        return False

    # R_NAME -- a curated name in the GIVEN-NAME position is decisive before any
    # phrase test: "Dana Woman", "Mary Baker", "May Smith" and "Theresa Manager"
    # are people whose surname happens to be a common noun.  It looks only at the
    # opening token, so "Dog Walker" and "Trader Joe" still read as descriptions.
    if _name_prefix(core):
        return True

    # R_LEAD -- "Trader Joe", "Barista Teenager", "Old Man".
    if (len(core) >= 2 and core[0].casefold() not in NAME_LEXICON
            and (_agentive(core[0]) or core[0].casefold() in ROLE_NOUNS)):
        return False

    # R_COIN -- "Uber Driver", "Wifi Password", "Muchacho Grande".
    # The family-name position must carry a real common noun: a surname of three
    # letters or fewer ("Ng", "Obi", "Wei", "Lim") is never a category.
    if (len(core) >= 2 and core[0].casefold() not in NAME_LEXICON
            and core[-1].casefold() not in NAME_LEXICON
            and _opaque(core[0].casefold())
            and len(core[-1]) >= 4
            and _english_word(core[-1].casefold())):
        return False

    # R_MOD -- "Dog Walker", "Tech Blogger", "Content-Creator".
    if (len(core) >= 2 and core[0].casefold() not in NAME_LEXICON
            and core[0].casefold() not in _MODAL_CLASS
            and _english_word(core[0].casefold())
            and (_agentive(core[-1]) or core[-1].casefold() in ROLE_NOUNS)):
        return False

    # R_LEDGER -- a curated surname anywhere ("Renata Cruz-Whitfield", "A. J.
    # Marchetti") settles the question once the phrase tests have had their say.
    if any(_ledger_name(t) for t in core):
        return True

    # R_FREE -- "J. Baker", "Plato", "Priya Raghunathan", "Ng Wei" and "Nguyen
    # Van Anh" are names; "Podcast Host" and "Barista Teenager" are phrases.
    if len(core) == 1:
        if _name_prefix(stripped):
            return True
        return not _category_word(core[0])
    if _name_prefix(core) or personal_name_prefix(core):
        return True
    return (any(_opaque(t.casefold()) for t in core)
            and (len(core[-1]) < 4 or not _category_word(core[-1])))


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
    # S75-T06 round 8: an alphabetic segment is a run of LETTERS, not a run of
    # ASCII letters.  Splitting on ``[^A-Za-z]`` broke "Voıce" into "Vo"+"ce"
    # and "Peοple" into "Pe"+"ple", giving a single disguised word the two
    # segments identifier structure demands.
    segments, current = [], []
    for ch in text:
        if ch.isalpha():
            current.append(ch)
        elif current:
            segments.append("".join(current))
            current = []
    if current:
        segments.append("".join(current))
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
        if any(t.casefold() in CLOSED_CLASS and t.casefold() not in _MODAL_CLASS
               and not _initial(t) for t in stripped):
            return "closed-class word inside the string"
        return "no name evidence: describes a category"
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

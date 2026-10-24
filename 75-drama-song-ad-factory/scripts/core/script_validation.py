"""Rich-scene and legacy-compatibility validation for Skill 75 (S75-T11 / S75-A11).

Reuses the released S75-T03 contracts (story_first_contracts) rather than
restating the scene schema. Adds the script-level checks the contract names:

  * a scene is authored content or it is refused (see THE RULE below)
  * beat-only bypasses (beats present, no scenes) are refused
  * legacy records that predate the contract stay readable, are marked
    COMPATIBILITY_LIMITED with their unresolved rich fields listed, and are
    never regenerated, rewritten or reported as accepted rich scenes

THE RULE
--------
A scene is authored content, or it is refused. One rule, applied to every
scene, with no flag that exempts any part of it:

  1. the scene entry is an object
  2. ``silent_scene`` is a typed declaration, not a switch: it is absent, or
     exactly true, or exactly false. A string, an int, a list, a float or any
     other truthy value is a named refusal. PRECEDENCE IS EXPLICIT: content
     beats declaration. A scene that declares ``silent_scene=true`` while
     carrying performed or spoken lines is a CONTRADICTION and is refused
     (SILENT_SCENE_CONTRADICTION) -- the lines prove speech, so the flag is
     wrong about the scene. Silence therefore exempts nothing: a silent scene
     still has to prove it is a real scene with real content, and a flag can
     never launder performed dialogue into an empty lip-sync schedule.
  3. the scene carries real performed lines: at least MIN_SCENE_LINES of them,
     at least MIN_SCENE_LINE_WORDS written words across them, and no
     placeholder among them
  4. every written statement in the scene states something. ONE content test
     (``_statement_defects``) is defined once and every written field routes
     through it: written text, never a number, bool, list or null; long enough
     to say it; not a placeholder and not an instruction to the writer; not a
     serialization literal; not one token repeated; and shaped like the kind
     of writing the field demands (see THE CONTENT TEST below)
  5. no statement is pasted into two different jobs

THE CONTENT TEST
----------------
Placeholder content cannot satisfy this, because the test reads meaning and
shape rather than punctuation. A stub spelled in ordinary vocabulary -- "The
words for this part are still to be written.", "Insert the spoken line here
after the editing.", "to be filled in later", "placeholder", "TBD", "TK",
"lorem ipsum" -- is caught by its MEANING (an unfilled slot, or a sentence
addressed to the writer telling them what to write) and not by an ellipsis or
a bracket marker. So is a run of unrelated commercial or SEO keywords ("buy
backlinks cheap seo signals crypto pump diet tea mattress"): that is a BAG OF
LABELS, not a statement. The bag carries no grammar at all -- no clause glue
binding its words, no predicate saying what happens, no anchor the sentence is
about -- and that is what the rule rejects, never the vocabulary itself.

Every comparison of written text goes through one normaliser (``_fold``), so a
homoglyph or a compatibility form cannot buy a different answer: "afraid" with
a Cyrillic or Greek lookalike letter is the same word, and is refused as the
same stagnation the plain spelling earns.

Stdlib only. Pure functions: no IO, no model dispatch, no mutation of input.
"""
from __future__ import annotations

import copy
import json
import os
import sys
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import story_first_contracts as C  # noqa: E402

ORIGIN_NEW = "NEW"
ORIGIN_LEGACY = "LEGACY"

# ponytail: a scene must carry at least this many written words across its
# spoken/sung lines, and at least two real lines, to count as authored rather
# than a placeholder. This applies to silent scenes too -- silence is a
# staging decision, never a content exemption. Raise with reviewer evidence.
MIN_SCENE_LINE_WORDS = 8
MIN_SCENE_LINES = 2

# ponytail: free-text claims are held to a word floor plus real grammar, the
# structural stand-in for "this is a statement, not a keyword list". The verb
# lexicon below is the ceiling of this rule: extend it with reviewer evidence
# (real statements the rule refused), never with a shorter floor.
MIN_CLAIM_WORDS = 4

# A time/place specification is a noun phrase ("evening, closing time"), so it
# is held to a length and variety floor instead of a clause floor. Two words
# is what separates a written time from a shrug ("sometime", "later", "0").
MIN_TIME_WORDS = 2

# --- one normaliser for every text decision -------------------------------
# A homoglyph defeats a raw comparison: "afraid" spelled with a Cyrillic or
# Greek lookalike letter is a different string and the same word. Every
# equality, change, placeholder and tokenisation decision in this module goes
# through _fold, so no spelling, compatibility form or lookalike alphabet buys
# a different answer from the one the plain spelling gets.

# The Cyrillic and Greek letters that render as Latin letters. Folded to the
# Latin letter they look like, after compatibility decomposition.
_LOOKALIKE_FOLD = {
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "һ": "h", "ԝ": "w", "в": "b",
    "к": "k", "м": "m", "т": "t",
    "α": "a", "ε": "e", "ι": "i", "ο": "o", "ρ": "p", "κ": "k", "ν": "v",
    "τ": "t", "χ": "x", "µ": "m",
}


def _fold(value):
    """The one canonical form of a written value; None when it is not text.

    Compatibility forms and case are folded, diacritics dropped, and the
    Cyrillic/Greek lookalikes of Latin letters mapped to the Latin letter they
    render as. Callers never compare raw strings for meaning.
    """
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKD", value)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = "".join(_LOOKALIKE_FOLD.get(ch, ch) for ch in text)
    text = unicodedata.normalize("NFKD", text).casefold()
    return "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in text)


def _tokens(text):
    folded = _fold(text)
    if folded is None:
        return []
    return [t for t in folded.split() if len(t) > 1 or t in ("a", "i")]


def _letters(value):
    """The folded value with its spaces removed.

    Letter-spaced spelling ("T B D", " a f r a i d ") is the same writing as
    the run-together spelling, so every meaning decision compares this form
    too.
    """
    folded = _fold(value)
    return "" if folded is None else "".join(folded.split())


def _normalized(value):
    """The comparable content of a written value; None when it is not text."""
    if not isinstance(value, str):
        return None
    return " ".join(_tokens(value))


# Closed-class English words that any clause carries and a bare keyword list
# does not. This is a structural test, never a list of banned values.
_FUNCTION_WORDS = frozenset("""
a an the of to in on at for with from by about into over under before after
and or but because so that when while as than through against between
her his their its it they she he we you i me him them us
must wants want chooses choose forces force keeps keep makes make
is are was were be been being has have had do does did
can could will would shall should may might
this that these those some any each every all both another such
more most less least many few much own same other even also only just one
up down off out since until during within without among beyond beneath
who whom whose which what where there here then
""".split())

# Words that give the sentence something to be about: a determiner, a pronoun,
# a possessive. A named participant ("Force Levi to trade ...") counts too and
# is detected on the raw text, see _has_anchor.
_ANCHOR_WORDS = frozenset("""
a an the this that these those some any each every all both another such
i me my mine we us our ours you your yours he him his she her hers it its
they them their theirs one ones someone somebody something anyone anything
everyone everything nothing none
""".split())

# Auxiliary and infinitive markers: a verb right after one of these is a
# predicate even when it is not in the lexicon ("must plan", "to trade").
_AUXILIARY_BEFORE = frozenset("""
to can could will would shall should may might must do does did
is are was were be been being has have had
""".split())

# Serialization literals are code, not prose. A field that names one of these
# names a data value, never a story value. Closed class, defined by the data
# formats, not by taste.
_NON_PROSE_TOKENS = frozenset("""
true false null none nil nan undefined void yes no
""".split())

# Tokens that name an unfilled slot rather than content.
_PLACEHOLDER_TOKENS = frozenset("""
tbd tk todo tbc tba placeholder lorem ipsum dolor
""".split())

# Punctuation markers of an unfilled slot. Only evidence when the value carries
# almost no writing of its own -- see _is_placeholder_text.
_PLACEHOLDER_MARKERS = ("...", "…", "[", "]", "<", ">", "{", "}")

# Stubs spelled in ordinary vocabulary. Matched on the folded text, so no
# spelling, case or lookalike letter evades them. Only constructions that name
# an unfilled slot are here: a phrase a character could plausibly say in the
# scene ("come back here", "your own line") is left to the shape rules, not
# refused for its words.
_STUB_PHRASES = (
    "still to be written", "to be written", "yet to be written", "not written yet",
    "to be filled", "be filled in", "fill in the", "fill this in", "fill that in",
    "to be added", "added later", "add later", "to be inserted", "to be replaced",
    "to be completed", "to be decided", "to be determined", "to be written later",
    "come back to this", "come back to it", "come back to this later",
    "the spoken line", "the sung line", "spoken line here", "line here",
    "words here", "text here", "copy here", "lyrics here",
    "goes here",
    "placeholder", "lorem ipsum", "dummy text", "sample text", "filler text",
    "remains unwritten", "remain unwritten", "still unwritten", "not yet written",
    "awaiting the writer", "from the writer", "by the writer",
    "final line from", "awaiting the final line", "final copy",
    "copy to follow", "line to follow", "to follow once", "to follow after",
    "to follow later", "after the edit", "once the edit", "after editing",
    "words will be added", "text will be added", "will be added later",
    "after the review", "before the review",
    "needs words", "needs the words", "needs text", "needs copy",
    "words are needed", "text is needed", "still needed",
)

# The same phrases with their spaces removed, so a letter-spaced spelling
# cannot evade them. Only phrases whose compact form cannot start a longer
# real word are matched compactly; the rest are matched on folded words only.
_STUB_PHRASES_COMPACT = tuple(
    compact for compact in ("".join(phrase.split()) for phrase in _STUB_PHRASES)
    if len(compact) >= 12
)

# Verbs that write or edit a script when used as an instruction. Combined with
# an authoring object and a deixis word, they are a note to the writer, not
# scene content.
_AUTHORING_VERBS = frozenset("""
insert fill replace delete remove add write rewrite expand continue complete
decide choose specify describe provide paste type draft update edit note
mention put place swap adjust revise finish redo skip
go goes come comes belong belongs
""".split())

_AUTHORING_OBJECTS = frozenset("""
line lines text words word dialogue lyric lyrics copy caption script
sentence sentences description detail details placeholder content scene
note notes version draft part section
""".split())

_DEIXIS = frozenset("""
here now later below above following instead this that these those
""".split())

# Verb forms a predicate is built from: base forms plus the irregular past and
# participle forms the stemmer below cannot derive. ponytail: this lexicon is
# the ceiling of the clause test; extend it when a real statement is refused.
_PREDICATE_FORMS = frozenset("""
be am is are was were been being have has had do does did done say says said
make makes made go goes went gone take takes took taken come comes came come
see sees saw seen know knows knew known get gets got gotten give gives gave
given find finds found think thinks thought tell tells told become becomes
became leave leaves left want wants wanted need needs needed feel feels felt
put puts keep keeps kept hold holds held let lets begin begins began start
starts started help helps helped talk talks talked turn turns turned show
shows showed shown hear hears heard play plays played run runs ran move moves
moved live lives lived believe believes believed bring brings brought happen
happens happened write writes wrote written sit sits sat stand stands stood
lose loses lost pay pays paid meet meets met include includes included
continue continues continued set sets learn learns learned change changes
changed lead leads led understand understands understood watch watches
watched follow follows followed stop stops stopped create creates created
speak speaks spoke spoken read reads spend spends spent grow grows grew grown
open opens opened walk walks walked win wins won teach teaches taught offer
offers offered remember remembers remembered consider considers considered
appear appears appeared buy buys bought wait waits waited serve serves served
die dies died send sends sent expect expects expected build builds built stay
stays stayed fall falls fell cut cuts reach reaches reached kill kills killed
remain remains remained suggest suggests suggested raise raises raised pass
passes passed sell sells sold require requires required report reports
reported decide decides decided pull pulls pulled return returns returned
explain explains explained hope hopes hoped carry carries carried break breaks
broke broken receive receives received agree agrees agreed support supports
supported hit hits produce produces produced eat eats ate eaten cover covers
covered catch catches caught draw draws drew drawn choose chooses chose
chosen cause causes caused point points pointed listen listens listened
realize realizes realized place places placed involve involves involved name
names named hide hides hid hidden hand hands handed check checks checked
bounce bounces bounced matter matters meant mean means seem seems seemed allow
rise rises rose risen allows allowed fill fills filled insert inserts inserted replace replaces
replaced delete deletes deleted describe describes described specify
specifies specified provide provides provided note notes noted mention
mentions mentioned update updates updated close closes closed still stills trade trades traded sign signs
signed post posts posted fix fixes fixed lock locks locked admit admits
admitted force forces forced expose exposes exposed plan plans planned block
blocks blocked escape escapes escaped push pushes pushed click clicks clicked
restrain restrains restrained dress dresses dressed promise promises
promised accept accepts accepted refuse refuses refused ask asks asked answer
answers answered call calls called shout shouts shouted whisper whispers
whispered sing sings sang sung laugh laughs laughed cry cries cried smile
smiles smiled argue argues argued threaten threatens threatened warn warns
warned thank thanks thanked beg begs begged demand demands demanded insist
insists insisted confess confesses confessed reveal reveals revealed
announce announces announced stare stares stared step steps stepped lean
leans leaned cross crosses crossed enter enters entered exit exits exited
glance glances glanced touch touches touched grab grabs grabbed drop drops
dropped lift lifts lifted pour pours poured borrow borrows borrowed owe owes
owed steal steals stole search searches searched discover discovers
discovered notice notices noticed ignore ignores ignored forget forgets
forgot forgotten prove proves proved doubt doubts feared fear fears trust
trusts blamed blame blames forgive forgives forgave pity pities envies envy
hates hate loves love likes like prefers prefer wishes wish hopes pretends
pretend imagines imagine dreams dream guesses guess supposes suppose figures
figure assumes assume
""".split())


# Irregular verb forms the stemmer below cannot derive.
_IRREGULAR_STEMS = {
    "written": "write", "wrote": "write", "made": "make", "said": "say",
    "done": "do", "did": "do", "went": "go", "gone": "go", "got": "get",
    "gotten": "get", "gave": "give", "given": "give", "took": "take",
    "taken": "take", "came": "come", "seen": "see", "saw": "see",
    "kept": "keep", "held": "hold", "left": "leave", "lost": "lose",
    "sent": "send", "built": "build", "broke": "break", "broken": "break",
    "chosen": "choose", "chose": "choose", "hid": "hide", "hidden": "hide",
    "began": "begin", "begun": "begin", "taught": "teach", "caught": "catch",
    "brought": "bring", "bought": "buy", "sold": "sell", "told": "tell",
    "fell": "fall", "felt": "feel", "meant": "mean", "put": "put",
}


def _verb_stems(token):
    """The stems a predicate could hide in: "opens" -> {"open"}."""
    stems = {token}
    if token in _IRREGULAR_STEMS:
        stems.add(_IRREGULAR_STEMS[token])
    for suffix in ("ing", "ed", "es", "en", "s"):
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            stem = token[: -len(suffix)]
            stems.add(stem)
            stems.add(stem + "e")
            if len(stem) > 2 and stem[-1] == stem[-2]:
                stems.add(stem[:-1])
    return stems


def _defect(code, field, detail=None):
    out = {"code": code, "field": field}
    if detail is not None:
        out["detail"] = detail
    return out


def _script_defects(script):
    """Structural defects in the container, before any scene is examined."""
    scenes = script.get("scenes")
    if scenes is not None and not isinstance(scenes, list):
        return [_defect("NOT_A_LIST", "scenes")]
    if scenes:
        return []
    if script.get("beats"):
        return [_defect("BEAT_ONLY_BYPASS", "scenes",
                        "beats are not a script; write and validate every scene")]
    return [_defect("EMPTY", "scenes", "no scenes")]


def is_legacy(script):
    """A record provably predates the rich-scene contract.

    Acceptance is not a missing-field bypass: the record must carry both an
    origin marker and a stable artifact identity, so a newly authored one-line
    object cannot be relabelled into acceptance.
    """
    if not isinstance(script, dict):
        return False
    if script.get("legacy") is not True and script.get("record_origin") != ORIGIN_LEGACY:
        if script.get("schema_version") in (None, *RICH_SCHEMA_VERSIONS):
            return False
    return bool(script.get("artifact_id") or script.get("content_digest")
                or script.get("run_id"))


def _legacy_identity(script):
    if script.get("artifact_id") or script.get("content_digest") or script.get("run_id"):
        return []
    return [_defect("LEGACY_UNPROVEN", "artifact_id",
                    "legacy claim without artifact identity; treated as new authoring")]


def _line_words(scene):
    total = 0
    for field in ("spoken_dialogue", "sung_lyrics"):
        for line in scene.get(field) or []:
            if isinstance(line, dict):
                total += C._words(line.get("text"))
    return total


def _is_placeholder_text(value):
    """Placeholder detection by MEANING, not by punctuation.

    A stub is an unfilled slot whatever it is spelled with: ellipsis, bracket,
    a slot name ("TBD", "TK", "placeholder", "lorem ipsum") or ordinary
    vocabulary carrying the same meaning ("still to be written", "to be filled
    in later"). Spelling tricks do not change the meaning either: the letters
    form is matched alongside the folded words. Punctuation is evidence only
    when the value carries almost no writing of its own, so an ellipsis inside
    real speech is not a stub.
    """
    if not isinstance(value, str):
        return False
    folded = _fold(value) or ""
    tokens = folded.split()
    letters = "".join(folded.split())
    if any(marker in value for marker in _PLACEHOLDER_MARKERS):
        if sum(1 for ch in folded if ch.isalnum()) < 3:
            return True
    if any(token in _PLACEHOLDER_TOKENS for token in tokens):
        return True
    if letters in _PLACEHOLDER_TOKENS:
        return True
    if (any(phrase in folded for phrase in _STUB_PHRASES)
            or any(phrase in letters for phrase in _STUB_PHRASES_COMPACT)):
        return True
    # "Written later.", "Added here.", "Put there." -- a stub spelled as two or
    # three ordinary words: an authoring verb, where the writing goes, and no
    # participant it happens to.
    short = [t for t in tokens if len(t) > 1 or t in ("a", "i")]
    if len(short) <= 3 and not _has_anchor(value, short):
        verbs = [t for t in short
                 if (_verb_stems(t) | {_IRREGULAR_STEMS.get(t, "")}) & _AUTHORING_VERBS]
        if verbs and set(short) & (_DEIXIS | {"later", "soon", "after", "eventually"}):
            return True
    return False


def _is_instruction_to_author(value):
    """A note to the writer is not scene content.

    "Insert the spoken line here after the editing." is written text with real
    words and real grammar, and it is still not a statement: it addresses the
    author and names what to write. Any authoring verb with an authoring object
    and a deixis word (or a "your") is such a note, whatever its vocabulary.
    """
    tokens = _tokens(value)
    verbs = [t for t in tokens if t in _AUTHORING_VERBS or
             (_verb_stems(t) & _AUTHORING_VERBS)]
    if not verbs:
        return False
    if not (set(tokens) & _AUTHORING_OBJECTS):
        return False
    return bool(set(tokens) & _DEIXIS) or "your" in tokens


def is_keyword_only(text):
    """True for a bare keyword list: too short, or no clause structure at all."""
    return bool(_statement_defects(text, "text", MIN_CLAIM_WORDS, shape=SHAPE_CLAUSE))


# --- one rule: this value states something --------------------------------

SHAPE_CLAUSE = "clause"   # a sentence that says what happens
SHAPE_PHRASE = "phrase"   # a written specification ("evening, closing time")
SHAPE_LINE = "line"       # a performed spoken or sung line

# Grammar density floor for values that are not clauses: a long run of labels
# with one glue word is still a bag of labels. Short values are held to the
# word floor instead, because "evening, closing time" is three words of spec.
_GRAMMAR_DENSITY = {SHAPE_PHRASE: 5, SHAPE_LINE: 3}


def _has_predicate(tokens):
    for index, token in enumerate(tokens):
        if token in _PREDICATE_FORMS or (_verb_stems(token) & _PREDICATE_FORMS):
            return True
        if token.endswith(("ed", "ing", "en")) and len(token) > 4:
            return True
        if index and tokens[index - 1] in _AUXILIARY_BEFORE:
            return True
    return False


def _has_anchor(value, tokens):
    if any(t in _ANCHOR_WORDS for t in tokens):
        return True
    # A named participant ("Force Levi to trade ...") is an anchor too.
    return any(word[:1].isupper() for word in value.split()[1:])


def _conjuncts(value):
    """The clauses and list entries the value is built from.

    Commas and semicolons join entries as "and" does, so they are read as
    conjunctions before folding.
    """
    folded = _fold(value.replace(",", " and ").replace(";", " and ")) or ""
    parts, current = [], []
    for token in folded.split():
        if token in ("and", "or", "but"):
            parts.append(current)
            current = []
        else:
            current.append(token)
    parts.append(current)
    return [part for part in parts if part]


def _grammar(value, tokens):
    """The three things a written value can carry: glue, predicate, anchor."""
    glue = [t for t in tokens if t in _FUNCTION_WORDS]
    return glue, _has_predicate(tokens), _has_anchor(value, tokens)


# What each shape must prove about the entries it is built from: how many
# content words make an entry substantial, and whether a substantial entry
# that names no event is tolerated in the minority (a statement may enumerate:
# "the empty ledger, the broken clock, and his direct question block that
# escape") or never (a performed line is short enough to have no excuse).
_ENTRY_RULES = {SHAPE_CLAUSE: (3, True), SHAPE_LINE: (5, False), SHAPE_PHRASE: (3, False)}


def _entry_defects(value, field, min_content, *, ratio):
    """Refuse a value whose entries are labels appended to a list.

    "Buy the backlinks, the cheap seo signals, the crypto pump tokens" is one
    imperative hung on a run of specified labels: what it carries names no
    event. A statement that enumerates still says what happens in most of what
    it enumerates, so only the majority rule fires there.
    """
    parts = _conjuncts(value)
    if len(parts) < 2:
        return []
    labelled = 0
    bare = 0
    for part in parts:
        content = [t for t in part if t not in _FUNCTION_WORDS]
        if len(content) < min_content:
            continue
        labelled += 1
        if not _has_predicate(part):
            bare += 1
    if not labelled:
        return []
    if (bare * 3 >= labelled * 2) if ratio else bare:
        return [_defect("KEYWORD_ONLY_CLAIM", field,
                        "keyword list, not a stated claim: %d of %d entries name no event"
                        % (bare, labelled))]
    return []


def _statement_defects(value, field, min_words, *, shape=SHAPE_CLAUSE):
    """Refuse a value that carries no information.

    One content test, applied to every written field in the module: written
    text (exact type str -- never a number, bool, list, dict or null), long
    enough to state anything, not an unfilled slot, not a note to the writer,
    not one token repeated, not a serialization literal, and shaped like
    writing rather than a bag of unrelated labels.

    A run of unrelated commercial or SEO keywords ("buy backlinks cheap seo
    signals crypto pump diet tea mattress") is a bag of labels, not a
    statement: it carries no clause glue binding its words, no predicate
    saying what happens to them, and no anchor for the sentence to be about.
    The rule rejects it for that shape, never for its vocabulary.
    """
    if not isinstance(value, str):
        return [_defect("CLAIM_NOT_WRITTEN", field,
                        {"reason": "value must be written text",
                         "got": type(value).__name__})]
    tokens = _tokens(value)
    if not tokens:
        return [_defect("CLAIM_NOT_WRITTEN", field, "value has no words in it")]
    if _is_placeholder_text(value):
        return [_defect("PLACEHOLDER_CLAIM", field, "value names an unfilled slot")]
    if _is_instruction_to_author(value):
        return [_defect("PLACEHOLDER_CLAIM", field,
                        "value is a note to the writer, not scene content")]
    if tokens and all(token in _NON_PROSE_TOKENS for token in tokens):
        return [_defect("CLAIM_NOT_WRITTEN", field,
                        "value names a serialization literal, not a story value")]
    if any(token in _PLACEHOLDER_TOKENS for token in tokens):
        return [_defect("PLACEHOLDER_CLAIM", field, "value names an unfilled slot")]
    if len(tokens) < min_words:
        return [_defect("KEYWORD_ONLY_CLAIM", field,
                        "value is too short to state anything (%d words, %d needed)"
                        % (len(tokens), min_words))]
    if len(set(tokens)) * 2 <= len(tokens):
        return [_defect("CLAIM_REPEATED", field, "value is one token repeated")]
    glue, predicate, anchor = _grammar(value, tokens)
    min_content, strict = _ENTRY_RULES[shape]
    if shape == SHAPE_CLAUSE:
        missing = []
        if not glue:
            missing.append("clause glue")
        if not predicate:
            missing.append("a predicate")
        if not anchor:
            missing.append("an anchor")
        if missing:
            return [_defect("KEYWORD_ONLY_CLAIM", field,
                            "keyword list, not a stated claim: no " + ", ".join(missing))]
        # The grammar has to run through the statement, not sit on one end of
        # it: a label run patched together with one leading article still
        # leaves long stretches of bare labels between its glue words.
        interior = len([t for t in tokens[1:] if t in _FUNCTION_WORDS])
        needed = max(0, -(-len(tokens) // 4) - 1)
        if interior < needed:
            return [_defect("KEYWORD_ONLY_CLAIM", field,
                            "label run, not a stated claim: %d words held together by %d"
                            % (len(tokens), interior))]
        # Every entry the statement is built from has to be part of the
        # statement: "the empty ledger and his direct question" names two
        # things with grammar, "backlinks and cheap seo signals" is two more
        # labels appended to a list.
        if strict:
            for part in _conjuncts(value):
                if len(part) < 2:
                    continue
                if not (_has_anchor(value, part) or _has_predicate(part)):
                    return [_defect("KEYWORD_ONLY_CLAIM", field,
                                    "keyword list, not a stated claim: an entry is bare labels")]
        defects = _entry_defects(value, field, min_content, ratio=strict)
        if defects:
            return defects
    elif len(tokens) >= MIN_CLAIM_WORDS:
        if not (glue or anchor):
            return [_defect("KEYWORD_ONLY_CLAIM", field,
                            "keyword list, not a written value: no clause glue, no anchor")]
        if len(glue) * _GRAMMAR_DENSITY[shape] < len(tokens):
            return [_defect("KEYWORD_ONLY_CLAIM", field,
                            "label run, not a written value: %d words bound by %d"
                            % (len(tokens), len(glue)))]
        defects = _entry_defects(value, field, min_content, ratio=False)
        if defects:
            return defects
    return []


def _claim_defects(value, field, min_words, code="KEYWORD_ONLY_CLAIM"):
    """A quality claim must state something, not name it. `code` is kept for
    callers that name their own refusal; the rule is `_statement_defects`."""
    defects = _statement_defects(value, field, min_words, shape=SHAPE_CLAUSE)
    if code != "KEYWORD_ONLY_CLAIM":
        return [_defect(code, d["field"], d.get("detail")) for d in defects]
    return defects


# Every field whose value is one written statement, with the shape its value
# must have. Used to refuse the same sentence pasted into two different jobs.
_STATEMENT_FIELDS = (
    ("dramatic_purpose", C.MIN_PURPOSE_WORDS, SHAPE_CLAUSE),
    ("time", MIN_TIME_WORDS, SHAPE_PHRASE),
    ("causal_outcome", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
    ("immediate_want", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
    ("obstacle", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
    ("visible_action", C.MIN_ACTION_WORDS, SHAPE_CLAUSE),
    ("consequential_choice", C.MIN_CHOICE_WORDS, SHAPE_CLAUSE),
    ("turn_trigger", 3, SHAPE_CLAUSE),
    ("subtext_and_behavior", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
    ("framing_movement_intent", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
    ("timing_basis", MIN_CLAIM_WORDS, SHAPE_PHRASE),
    ("transition", MIN_CLAIM_WORDS, SHAPE_CLAUSE),
)
_ALL_STATEMENT_FIELDS = tuple(field for field, _, _ in _STATEMENT_FIELDS)

# Emotion fields are a pair, not statements: they are held to being genuine
# written values and to naming a change (see _emotion_change_defects).
_EMOTION_FIELDS = ("emotion_before", "emotion_after")

RICH_SCHEMA_VERSIONS = (C.SCENE_SCHEMA_VERSION, "s75.script.v1")

COMPATIBILITY_LIMITED = "COMPATIBILITY_LIMITED"

PLACEHOLDER_TEXT = ("...", "…", "tbd", "tk", "todo", "line here", "placeholder")

# Rich fields whose absence makes a legacy record compatibility-limited.
_RICH_FIELDS = (
    "dramatic_purpose", "time", "location_id", "world_revision", "cast_ids",
    "immediate_want", "obstacle", "visible_action", "consequential_choice",
    "emotion_before", "emotion_after", "turn_trigger", "spoken_dialogue",
    "sung_lyrics", "performance_order", "sound_music_cues",
    "framing_movement_intent", "duration_seconds", "transition",
    "visible_lip_sync",
)


def _sound_cue_defects(scene):
    defects = []
    cues = scene.get("sound_music_cues") or []
    if not isinstance(cues, (list, tuple)):
        cues = [cues]
    for entry in cues:
        defects.extend(_statement_defects(entry, "sound_music_cues", MIN_CLAIM_WORDS,
                                          shape=SHAPE_PHRASE))
    return defects


def _emotion_change_defects(scene):
    """A scene must move its performers; two values that name no change are not
    a turn, and two values that are not written emotion words are not emotions
    at all. Both values are compared in the module's one normalised form, so a
    homoglyph, a case change or a spacing trick is the same value."""
    defects = []
    normalized = {}
    for field in _EMOTION_FIELDS:
        value = scene.get(field)
        if not isinstance(value, str):
            defects.append(_defect("EMOTION_NOT_GENUINE", field,
                                   {"reason": "emotion must be written text",
                                    "got": type(value).__name__}))
            normalized[field] = None
            continue
        text = _normalized(value)
        if not text:
            defects.append(_defect("EMOTION_NOT_GENUINE", field, "emotion names nothing"))
            normalized[field] = None
            continue
        value_tokens = _tokens(value)
        if _is_placeholder_text(value) or any(
                token in _PLACEHOLDER_TOKENS for token in value_tokens) or (
                value_tokens and all(token in _NON_PROSE_TOKENS for token in value_tokens)):
            defects.append(_defect("EMOTION_NOT_GENUINE", field,
                                   "emotion names a slot or a literal, not a state"))
            normalized[field] = None
            continue
        normalized[field] = text
    before = normalized.get("emotion_before")
    after = normalized.get("emotion_after")
    unchanged = before is not None and before == after
    if not unchanged and isinstance(scene.get("emotion_before"), str) \
            and isinstance(scene.get("emotion_after"), str):
        unchanged = (_letters(scene.get("emotion_before"))
                     == _letters(scene.get("emotion_after")))
    if unchanged:
        defects.append(_defect("EMOTION_STAGNANT", "emotion_after",
                               "emotion_before and emotion_after name no change"))
    return defects


def _repetition_defects(scene):
    """One statement pasted into two jobs is one statement, not two."""
    seen = {}
    defects = []
    for field in _ALL_STATEMENT_FIELDS:
        text = _normalized(scene.get(field))
        if not text:
            continue
        if text in seen:
            defects.append(_defect("CLAIM_REPEATED", field,
                                   {"reason": "same statement as another field",
                                    "same_as": seen[text]}))
        else:
            seen[text] = field
    return defects


def _context_defects(world, cast_manifest):
    defects = []
    if world is None:
        defects.append(_defect("WORLD_REQUIRED", "world",
                               "episode world must be supplied for new authoring"))
    if cast_manifest is None:
        defects.append(_defect("CAST_REQUIRED", "cast_manifest",
                               "cast manifest must be supplied for new authoring"))
    return defects


def _geography_defects(scene, world):
    """location_id must exist in the supplied world and world_revision be current."""
    defects = []
    known = C.world_location_ids(world)
    location = scene.get("location_id")
    if not known or location not in known:
        defects.append(_defect("LOCATION_UNKNOWN", "location_id",
                               {"scene_id": scene.get("scene_id"), "location_id": location}))
    revision = scene.get("world_revision")
    if revision is None:
        defects.append(_defect("WORLD_REVISION_MISSING", "world_revision",
                               scene.get("scene_id")))
    elif revision != (world or {}).get("revision"):
        defects.append(_defect("WORLD_REVISION_STALE", "world_revision",
                               {"scene_id": scene.get("scene_id"),
                                "scene": revision, "world": (world or {}).get("revision")}))
    return defects


def _performer_defects(scenes, cast_manifest):
    """Every performer named anywhere must be declared in the cast manifest."""
    declared = {entry.get("character_id") for entry in
                (cast_manifest or {}).get("cast") or [] if isinstance(entry, dict)}
    defects = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        sid = scene.get("scene_id")
        named = set(scene.get("cast_ids") or [])
        for field in ("spoken_dialogue", "sung_lyrics"):
            for line in scene.get(field) or []:
                if isinstance(line, dict):
                    named.add(line.get("character_id"))
        for cid in sorted(n for n in named if n):
            if cid not in declared:
                defects.append(_defect("PERFORMER_UNDECLARED", "cast_ids",
                                       {"scene_id": sid, "character_id": cid}))
    return defects


def _line_texts(scene):
    """Every line text the scene claims to perform, placeholders included."""
    texts = []
    for field in ("spoken_dialogue", "sung_lyrics"):
        entries = scene.get(field) or []
        if not isinstance(entries, (list, tuple)):
            entries = [entries]
        for line in entries:
            if isinstance(line, dict):
                texts.append(str(line.get("text") or "").strip())
            else:
                texts.append(str(line or "").strip())
    return texts


def _scene_content_defects(scene):
    """THE RULE for one scene. Returns every named refusal it earns.

    There is no short-circuit here and none may be added: no flag, field or
    type exempts a scene from proving it carries authored content. Content
    beats declaration -- a declared flag that contradicts the lines present is
    itself a named refusal, never a way to skip a check.
    """
    sid = scene.get("scene_id") if isinstance(scene, dict) else None
    if not isinstance(scene, dict):
        return [_defect("SCENE_ENTRY_NOT_OBJECT", "scenes",
                        "scene entry must be an object, got %s" % type(scene).__name__),
                _defect("PLACEHOLDER_SCENE", "scenes", "unstructured scene")]

    defects = []

    # 2. silence is a typed declaration, not a bypass switch.
    silence = scene.get("silent_scene")
    if silence is not None and not isinstance(silence, bool):
        defects.append(_defect("SILENT_SCENE_FLAG", "silent_scene",
                               {"reason": "silent_scene must be true or false, "
                                          "never a truthy value that switches checks off",
                                "got": type(silence).__name__}))

    # 3. real performed lines, and no placeholder among them.
    texts = _line_texts(scene)
    performed = [t for t in texts if t]
    if silence is True and performed:
        defects.append(_defect("SILENT_SCENE_CONTRADICTION", "silent_scene",
                               "declared silent while performed lines are present; "
                               "content implies speech, so the declaration is refused"))
    placeholder_free = [t for t in texts if t and not _is_placeholder_text(t)]
    if any(_is_placeholder_text(t) for t in texts):
        defects.append(_defect("PLACEHOLDER_SCENE", "scenes",
                               sid or "unstructured scene"))
    if len(placeholder_free) < MIN_SCENE_LINES or _line_words(scene) < MIN_SCENE_LINE_WORDS:
        defects.append(_defect("PLACEHOLDER_SCENE", "scenes",
                               sid or "unstructured scene"))
    for field in ("spoken_dialogue", "sung_lyrics"):
        entries = scene.get(field) or []
        if not isinstance(entries, (list, tuple)):
            entries = [entries]
        for line in entries:
            text = line.get("text") if isinstance(line, dict) else line
            defects.extend(_statement_defects(text, field, C.MIN_LINE_WORDS,
                                              shape=SHAPE_LINE))

    # 4. every written statement states something, through one content test.
    for field, min_words, shape in _STATEMENT_FIELDS:
        defects.extend(_statement_defects(scene.get(field), field, min_words, shape=shape))

    # 5. no statement pasted into two jobs.
    defects.extend(_repetition_defects(scene))
    return defects


def _lip_sync_defects(scene):
    value = scene.get("visible_lip_sync")
    if not isinstance(value, dict):
        return [_defect("LIP_SYNC_DESIGNATION", "visible_lip_sync", "explicit designation required")]
    defects = []
    intervals = value.get("intervals")
    if not isinstance(intervals, list):
        defects.append(_defect("LIP_SYNC_DESIGNATION", "visible_lip_sync.intervals",
                               "proposed or actual intervals required"))
    else:
        # Content implies speech: what is performed is what gets lip-synced.
        # A declared flag cannot launder performed lines into an empty
        # schedule -- a scene that declares silence while carrying lines is
        # refused as a contradiction in _scene_content_defects.
        speaks = _line_words(scene) > 0
        if speaks and not intervals:
            defects.append(_defect("LIP_SYNC_EMPTY_CLAIM", "visible_lip_sync.intervals",
                                   "lines are performed on screen; declare real intervals"))
        duration = scene.get("duration_seconds")
        for interval in intervals:
            if not isinstance(interval, (list, tuple)) or len(interval) != 2 or \
                    not all(isinstance(n, (int, float)) and not isinstance(n, bool)
                            for n in interval):
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "interval is not a numeric start/end pair"))
                continue
            start, end = interval
            if start < 0 or end <= start:
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "empty or negative interval"))
            elif isinstance(duration, (int, float)) and end > duration:
                defects.append(_defect("LIP_SYNC_INTERVAL", "visible_lip_sync.intervals",
                                       "interval exceeds declared duration"))
    performer = value.get("performer")
    if performer is not None and performer not in (scene.get("cast_ids") or []):
        defects.append(_defect("LIP_SYNC_PERFORMER", "visible_lip_sync.performer",
                               "performer is not in cast_ids"))
    return defects


def validate_script(script, origin=ORIGIN_NEW, world=None, cast_manifest=None):
    """Validate one script revision.

    Returns a verdict dict. `ok` is True when the revision is acceptable for
    the requested origin. Legacy revisions are readable but carry
    `compatibility_limited: True`, the unresolved rich fields and the reason,
    and are never regenerated (`regenerate` is always False).
    """
    verdict = {
        "ok": False,
        "origin": origin,
        "legacy": False,
        "compatibility_limited": False,
        "unresolved": [],
        "defects": [],
        "regenerate": False,
        "scene_count": 0,
    }
    before = copy.deepcopy(script)

    if not isinstance(script, dict):
        verdict["defects"] = [_defect("NOT_AN_OBJECT", "script")]
        return verdict

    legacy = is_legacy(script)
    verdict["legacy"] = legacy

    if legacy:
        if origin != ORIGIN_LEGACY:
            verdict["defects"] = [_defect(
                "LEGACY_NOT_NEW_AUTHORING", "script",
                "a pre-contract record cannot satisfy new generation")]
            return verdict
        defects = _legacy_identity(script) + _script_defects(script)
        scene_list = script.get("scenes") or []
        unresolved = set()
        for scene in scene_list:
            if not isinstance(scene, dict):
                unresolved.update(_RICH_FIELDS)
                defects.append(_defect("SCENE_ENTRY_NOT_OBJECT", "scenes",
                                       "scene entry must be an object, got %s"
                                       % type(scene).__name__))
                continue
            for field in _RICH_FIELDS:
                if C._blank(scene.get(field)):
                    unresolved.add(field)
        verdict["scene_count"] = len(scene_list)
        verdict["unresolved"] = sorted(unresolved)
        verdict["defects"] = defects
        verdict["ok"] = not defects
        verdict["compatibility_limited"] = not defects
        assert json.dumps(script, sort_keys=True) == json.dumps(before, sort_keys=True)
        return verdict

    defects = _script_defects(script) + _context_defects(world, cast_manifest)
    scenes = script.get("scenes") or []
    verdict["scene_count"] = len(scenes) if isinstance(scenes, list) else 0
    seen = set()
    previous = None
    for scene in scenes if isinstance(scenes, list) else []:
        if not isinstance(scene, dict):
            defects.extend(_scene_content_defects(scene))
            continue
        sid = scene.get("scene_id")
        defects.extend(_scene_content_defects(scene))
        if sid in seen:
            defects.append(_defect("DUPLICATE_SCENE_ID", "scene_id", sid))
        seen.add(sid)
        for item in C.validate_scene(scene, world=world):
            defects.append(_defect("SCENE_SCHEMA", item.get("field"), item))
        defects.extend(_lip_sync_defects(scene))
        defects.extend(_emotion_change_defects(scene))
        defects.extend(_sound_cue_defects(scene))
        if world is not None:
            defects.extend(_geography_defects(scene, world))
        predecessor = scene.get("causal_predecessor")
        if predecessor is not None and previous is not None and predecessor != previous:
            defects.append(_defect("CAUSAL_CHAIN", "causal_predecessor",
                                   {"scene_id": sid, "expected": previous,
                                    "got": predecessor}))
        previous = sid
    if cast_manifest is not None:
        for item in C.validate_cast_manifest(cast_manifest, scenes):
            defects.append(_defect("CAST", item.get("field"), item))
        defects.extend(_performer_defects(scenes, cast_manifest))

    verdict["defects"] = defects
    verdict["ok"] = not defects and verdict["scene_count"] > 0
    assert json.dumps(script, sort_keys=True) == json.dumps(before, sort_keys=True)
    return verdict


def assert_new_generation(script, **kwargs):
    """Raise ContractError unless `script` is acceptable new authoring."""
    verdict = validate_script(script, origin=ORIGIN_NEW, **kwargs)
    if not verdict["ok"]:
        raise C.ContractError("SCRIPT_INVALID", "script rejected for new generation", verdict)
    return verdict

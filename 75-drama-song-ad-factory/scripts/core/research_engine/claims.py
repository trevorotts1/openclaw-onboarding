"""claims.py: claim provenance, research authoring, bundle validation.

S75-T04 (research authoring + source-to-owner-fact mapping). SPEC row 1 and
the foundation contract in SPEC.md §"Foundation and authoring contract":
every research claim carries where it came from, and no research artifact may
pass because it is merely non-empty or large.

Three provenance classes, no others:

  owner-fact   what the business owner said. Retains the raw answer identity
               (`owner_ref`) and is never presented as independently verified.
  public-fact  an independently sourced claim. Needs a source id that resolves
               to a recorded {url, retrieved}.
  fiction      proposed story content. Allowed and expected; labelled fiction
               can never be re-read as a real-business fact.

THE SUFFICIENCY RULE (semantic, not pattern matching). A bundle entry is a
research claim only when it carries both support relations the contract names,
and each relation is re-checked against content that a placeholder cannot
manufacture:

  1. SUPPORT TO A SOURCE. public-fact: the `source` id resolves to a recorded
     {url, retrieved}. When the claim carries a citation quote, that quote must
     appear verbatim in text recorded for that source (`excerpts`), so the
     citation is checkable, not decorative.

  2. SUPPORT TO AN OWNER FACT. The claim names the run's owner fact it informs
     (`about`: {fact, anchor}) and the anchor is verified in three places at
     once: the claim text, every sentence of it, and the owner fact's own text
     AS THE RUN RECORDED IT — the bundle's own `offer`/`audience`/`action` or
     its `facts[]` entries tagged `role: "owner-fact"`. A text carried inside
     the claim (`about.fact_text`) is never evidence: it is only ever checked
     as a copy of the recorded owner fact, and a copy that disagrees is
     refused. If the validator can be satisfied by the thing it is validating,
     no wording of the claim can fail. A run of keywords typed over the
     business's vocabulary has no such relation; a sentence about something
     else has none either. On the stage path `author_bundle` writes that record
     from the brief's offer/audience/action, and that is what the run checks
     against; a `facts[]` entry is honoured where a caller-authored bundle is
     validated directly.

  2b. ON THE RUN'S OWN SUBJECT. The words the sentence asserts are read
     against what the run records — the owner facts — plus the closed research
     vocabulary below. A sentence that predicates words grounded nowhere in the
     run is a sentence about something else (it sells the domain's nouns to the
     domain's nouns), and no reshaping of the wording makes it one. And the
     sentence must be a clause: a predicate AND a word that binds it (determiner,
     pronoun, preposition, auxiliary, numeral). A term run with one verb in it
     is still a term run.

     THE SOURCE'S OWN `excerpts` ARE NOT GROUNDING. They are the record a
     citation quote is checked against (rule 1), and nothing else. A source
     record the filer wrote cannot be what makes the filer's own claim about
     this run: quoting spam into `excerpts` and then filing the same words as a
     claim used to make every one of them "grounded". A word is on this run's
     subject only where the OWNER recorded it, or when it is a research term.

     EVERY PHRASE HEAD MUST BE GROUNDED. A sentence is split at its function
     words, and the last content word of each stretch — the head, the word the
     stretch is about — must be one the run records. A modifier may be a word
     this vocabulary does not hold ("disturbed sleep"); a head may not
     ("mattress deals", "diet tea", "backlinks"). This refuses 'Tired nurses
     and weary mothers want backlinks after long winter shifts.' even though
     its unrecorded words are a minority of it.

     AND A CAPITAL LETTER NAMES NOTHING ON ITS OWN. A stretch is naming
     material — exempt from the head test — only where a name may sit: after a
     non-transfer preposition ("in Dallas", "in the United States"), and only
     when it starts like a name. In the complement of a predicate a capital
     letter is just a capital letter, so 'with Backlinks', 'rank Crypto and
     Backlinks' and 'with Mattress Deals' are refused exactly as their
     lower-case spellings are.

  3. ESCALATED CLAIMS — superlative, ranking, count, guarantee, and "$"/"#"
     styled price and rank claims — additionally declare an ALLOW-LIST class
     (market-size, market-growth, competitor-pricing, ...) and carry a source
     quote that is checked against the source record AND that itself carries
     the claim's escalated markers. A citation for some other sentence is not
     a citation for this claim.

  4. A claim about the named business's own results, price, guarantee or
     standing is never a public-fact, however it is classed or cited: market
     evidence cannot verify it. It becomes an owner-fact with its raw answer
     identity, or it is refused.

And a claim must assert: every sentence carries a predicate from the closed
assertion-verb lexicon below. A keyword list does not, whether it is comma
separated or run together as fake sentences.

Nothing here decides anything by counting separators, by word endings, or by
repetition, so one-character reshaping of a keyword run cannot buy a pass.

`validate_bundle` refuses an artifact whose claims carry no provenance tag and
refuses section bodies that hold only a brief echo. It never looks at byte
size — a 40 KB file of untagged keyword lists fails exactly like a 95-byte one.

Stdlib only, same as the rest of research_engine.
"""
from __future__ import annotations

import re
import unicodedata

PROVENANCE = ("owner-fact", "public-fact", "fiction")
SECTIONS = ("market", "audience", "competitors")
PREMISE = "premise"
VALID_SECTIONS = SECTIONS + (PREMISE,)
BUNDLE_SCHEMA_VERSION = "blackceo.research.bundle/v1"

# The owner facts of a run: the brief's own offer, audience and action. A
# research claim must say which of these it informs.
FACT_FIELDS = ("offer", "audience", "action")
FACT_ALIASES = {"offer": ("offer",), "audience": ("audience",),
                "action": ("action",), "competitors": ("offer", "audience"),
                "market": ("offer", "audience")}

# The explicit allow-list path: the classes a price/rank/count/superlative
# claim may declare. A legitimate market claim — competitor pricing, market
# growth, an audience statistic — passes here when it is cited for that claim.
ALLOWED_MARKET_CLASSES = (
    "market-size", "market-growth", "market-fact",
    "competitor-pricing", "competitor-ranking", "competitor-fact",
    "audience-evidence")

TOKEN_RE = re.compile(r"[a-z0-9]{3,}")
WORD_RE = re.compile(r"[a-z0-9]+")
SENTENCE_RE = re.compile(r"[.!?]+")
STOPWORDS = frozenset(
    "a an and or but of to in on for with from that this these those is are was "
    "were be been being it its as at by our your their they them we you i he she "
    "his her not no if then than so such can could may might will would should "
    "must have has had do does did".split())

# ---------------------------------------------------------------------------
# text normalization. "$" and "#" styled claims are claims: fullwidth and
# look-alike glyphs are folded before anything is read, and invisible
# characters are dropped, so a claim cannot dress itself as prose.
INVISIBLE_RE = re.compile(r"[​-‏‪-‮﻿­]")


def _clean(text):
    s = unicodedata.normalize("NFKC", str(text if text is not None else ""))
    return " ".join(INVISIBLE_RE.sub("", s).split()).strip()


def _norm(text):
    return _clean(text)


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _words(text):
    return WORD_RE.findall(_clean(text).lower())


def _stem(word):
    return word[:4] if len(word) >= 4 else word


def _sentences(text):
    parts = [p for p in SENTENCE_RE.split(_clean(text)) if p.strip()]
    return parts or ([_clean(text)] if _clean(text) else [])


def _content_tokens(text):
    return [t for t in TOKEN_RE.findall(_clean(text).lower())
            if t not in STOPWORDS]


def _tokens(text):
    return set(TOKEN_RE.findall(_clean(text).lower()))


# ---------------------------------------------------------------------------
# escalation markers: superlative, ranking, count, guarantee, and "$"/"#"
# styled price and rank claims. These DETECT the claim class the contract
# names; validity is never decided from them alone.
_NUMWORD = ("one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve"
            "|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
            "|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
            "|hundred|thousand|million|billion")
_NUMPHRASE = (r"(?:\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
              r"|" + _NUMWORD + r"(?:\s+(?:hundred|thousand|million|billion))?)")
_UNIT = ("families|family|clients?|customers?|students?|patients?|members?"
         "|users?|people|guests?|orders?|sales|reviews?|graduates?"
         "|enrollees?|enrolments?|employees?|coaches|years?|months?|weeks?"
         "|days?|hours?|sessions?|calls?|clinics?|locations?|cities|states"
         "|programs?|schools?|businesses?|practices?|companies")
COUNT_RE = re.compile(r"\b(" + _NUMPHRASE + r")\s*(?:\+|plus)?\s+(?:" + _UNIT
                      + r")\b", re.IGNORECASE)
MANY_RE = re.compile(r"\b(dozens|hundreds|thousands|millions|billions)\s+of\b",
                     re.IGNORECASE)
PCT_RE = re.compile(r"\b(" + _NUMPHRASE
                    + r")\s*(?:%|percent|per\s?cent)", re.IGNORECASE)
MONEY_RE = re.compile(r"[$]\s?(\d{1,3}(?:,\d{3})*(?:\.\d+)?)")
RANK_RE = re.compile(
    r"#\s*([0-9OoIl]{1,3})"
    r"|\b(?:no|number|nr)\.?\s*(\d+|one|two|three|four|five|six|seven|eight"
    r"|nine|ten)"
    r"|№\s*(\d+)"
    r"|\b(\d+)(?:st|nd|rd|th)\b"
    r"|\btop\s*-?\s*(\d+)\b",
    re.IGNORECASE)
RANK_WORD_RE = re.compile(
    r"\b(?:rated|ranked|voted|named|awarded|elected|featured|chosen|listed)\b",
    re.IGNORECASE)
SUPERLATIVE_RE = re.compile(
    r"\b(?:best|top[- ]?(?:rated|ranked|reviewed)|leading|premier|foremost"
    r"|number[- ]?one|largest|biggest|greatest|fastest(?:[- ]growing)?"
    r"|cheapest|highest[- ]?rated"
    r"|most\s+(?:trusted|popular|effective|recommended|loved|successful"
    r"|complete|comprehensive|advanced|experienced|reviewed|awarded|chosen"
    r"|sought[- ]after|cited|documented|loved)"
    r"|unbeatable|unmatched|unparalleled|unsurpassed|world[- ]class"
    r"|award[- ]winning|best[- ]selling|bestselling)\b",
    re.IGNORECASE)
GUARANTEE_RE = re.compile(
    r"\b(?:guarantee[ds]?|money[- ]back|risk[- ]free|refund(?:able|s)?)\b",
    re.IGNORECASE)

_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
            "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _mnorm(value):
    return re.sub(r"\s+", " ", str(value).strip().lower().replace(",", ""))


def _rank_core(raw):
    core = _mnorm(raw).replace(" ", "")
    core = core.replace("o", "0").replace("l", "1").replace("i", "1")
    core = core.lstrip("#№").lstrip("0") or "0"
    return _WORDNUM.get(core, core)


def _markers(text):
    """(kind, core) pairs for every escalated assertion in the text."""
    out = []
    for m in MONEY_RE.finditer(text):
        out.append(("money", _mnorm(m.group(1))))
    for m in PCT_RE.finditer(text):
        out.append(("pct", _mnorm(m.group(1))))
    for m in COUNT_RE.finditer(text):
        out.append(("count", _mnorm(m.group(1))))
    for m in MANY_RE.finditer(text):
        out.append(("count", _mnorm(m.group(1))))
    for m in RANK_RE.finditer(text):
        out.append(("rank", _rank_core(next(g for g in m.groups() if g))))
    for m in RANK_WORD_RE.finditer(text):
        out.append(("rank", _mnorm(m.group(0))))
    for m in SUPERLATIVE_RE.finditer(text):
        out.append(("super", _mnorm(m.group(0))))
    for m in GUARANTEE_RE.finditer(text):
        out.append(("guar", _mnorm(m.group(0))))
    return out


# ---------------------------------------------------------------------------
# the assertion test. A research claim predicates something of its subject.
# Closed lexicon of ASSERTION stems — verbs that state, measure or report —
# with their inflected forms derived from the stem only. A plural noun is
# never a verb form: "backlinks", "signals", "coaches", "pump" are not stems,
# so no keyword run conjures a predicate out of its own vocabulary. Directive
# verbs (buy, get, order, call) are deliberately absent: a research claim
# asserts, it does not instruct. Words that are chiefly nouns in this domain
# (sleep, work, coach, service, plan) are absent for the same reason.
ASSERT_STEMS = """
act affect agree allow appear apply ask associate assume attract avoid become
begin believe build cause change charge choose cite claim come compare complete
conclude consider continue cost create cut deliver depend design detail differ
discover discuss drive drop earn elect emerge enable encounter end enrol enroll
estimate examine exceed exist expand expect experience explain face fall feel
file find finish follow form gain generate give go grow guarantee happen help hold
identify illustrate impact imply improve include increase indicate influence
involve keep lack last lead learn limit link list live look lose maintain make
manage mean measure mention move name need note observe occur offer operate
outpace outweigh outperform overcome perform prefer predict prevent price
produce promise project propose provide publish rank rate reach receive record reduce
reflect remain report require respond result reveal review rise say score search
seem sell serve show solve spend start state stay stop study suggest support
survey take target tend test think trade treat trust turn use vary vote wake want
warn win worry write
""".split()
IRREGULAR_FORMS = {
    "become": "became", "begin": "began", "build": "built", "choose": "chose",
    "come": "came", "drive": "drove", "fall": "fell", "feel": "felt",
    "find": "found", "give": "gave", "go": "went", "grow": "grew",
    "hold": "held", "keep": "kept", "lead": "led", "lose": "lost",
    "make": "made", "rise": "rose", "say": "said", "sell": "sold",
    "spend": "spent", "take": "took", "think": "thought", "wake": "woke",
    "write": "wrote", "show": "showed", "drive": "drove",
}
AUX_FORMS = frozenset(
    "is are was were be been being am has have had do does did can could "
    "will would shall should must may might".split())


def _verb_forms():
    forms = set(AUX_FORMS)
    for stem in ASSERT_STEMS:
        forms.add(stem)
        forms.add(stem + "s")
        if stem.endswith(("s", "x", "z", "ch", "sh")):
            forms.add(stem + "es")
        if stem.endswith("y"):
            forms.add(stem[:-1] + "ies")
            forms.add(stem[:-1] + "ied")
        elif stem.endswith("e"):
            forms.add(stem + "d")
        else:
            forms.add(stem + "ed")
        forms.add(stem[:-1] + "ing" if stem.endswith("e") else stem + "ing")
    for stem, past in IRREGULAR_FORMS.items():
        forms.add(past)
    return frozenset(forms)


VERB_FORMS = _verb_forms()

# the words that bind a clause together. A run of terms has none of them, which
# is what makes it a run of terms even when one of its terms is also a verb.
FUNCTION_WORDS = frozenset(
    "a an the this that these those there it its i you he she we they me him "
    "her us them my your our their his hers whose who whom which what when "
    "where why how in on at to from by with for of as than into onto over "
    "under below beneath between among through across after before during "
    "since until against without within upon about above near and or nor but "
    "yet so because if though although while whereas unless whether not no "
    "rather very more most less least much many few several some any all each "
    "every both half one two three four five six seven eight nine ten eleven "
    "twelve twenty thirty forty fifty hundred thousand million billion "
    "hundreds thousands millions billions dozens never "
    "first "
    "second third fourth fifth once twice again also only just even still "
    "already often seldom rarely per via despite except besides instead last next previous "
    "current ago myself yourself himself herself itself ourselves yourselves "
    "themselves oneself".split())

# Research vocabulary: the words market and audience research prose is made of.
# They describe a market, an audience or an evidence method; none of them
# asserts anything about the named business's own results.
#
# TOLERANCE, NOT A WHITELIST. Round five let this list decide acceptance, and a
# list that decides acceptance is a cliff: 'firefighters', 'accountants',
# 'problems', 'times', 'meals', 'nap' and 'peaks' are all ordinary research
# prose and none of them is here, so ordinary research got refused. Nothing is
# added to this list, and nothing is refused for being absent from it. What a
# word does in the sentence — the role the predicate gives it — decides, and
# this list only says "this is ordinary domain prose, do not treat it as an
# outsider". Whether a sentence is about this run is decided structurally, in
# _check_topic, below.
RESEARCH_WORDS = frozenset("""
market markets industry industries sector sectors category categories segment
segments audience audiences demand supply growth grow growing grown trend
trends rate rates level levels share shares volume volumes sized size sizes
larger largest smaller smallest bigger biggest higher highest lower lowest
wider narrow greater greatest more most fewer fewest less least many much
several numerous majority minority average median mean total totals overall
percent percentage percentages point points proportion proportions ratio
ratios half double doubled twice thrice nearly roughly approximately almost
exactly survey surveys surveyed report reports reported reporting study
studies studied research data evidence sample samples respondent respondents
statistic statistics figure figures finding findings source sources
occupation occupations job jobs role roles position positions employment
workforce population populations adult adults people persons family families
patient patients inpatient inpatients client clients customer customers student students member
members user users employee employees staff workers nurse nurses doctor
doctors parent parents mother mothers father fathers caregiver caregivers
price prices pricing cost costs charge charges fee fees paid pay paying
spending budget budgets cheap cheaper cheapest expensive premium discount
discounts competitor competitors competing compete competition rival rivals
alternatives alternative local national regional nearby city cities town
towns area areas region regions state states country countries location
locations metro metros unit units place places practice practices clinic clinics studio studios
program programs service services course courses session sessions coach
coaches coaching provider providers brand brands product products company
companies business businesses firm firms agency agencies listing listings
listed directory directories review reviews rating ratings ranked ranking
rankings referral referrals channel channels search searches online website
websites site sites page pages web digital month months year years week weeks
day days hour hours minute minutes night nights morning mornings evening
evenings season seasons decade decades schedule schedules shift shifts
rotation rotations short shorter shortest long longer longest duration
durations frequency quality quantity pattern patterns effect effects impact
impacts risk risks factor factors cause causes correlate correlated
associated association linked relate related relation relations difference
differences change changes increase increases increased decrease decreases
decreased rise rises fall falls improve improves improved improvement
improvements sleep sleeps sleeping slept asleep insomnia awake alert rest
rested resting wellness health healthcare hospital hospitals office offices
school schools home homes documented published cited measured recorded tracked
enquiries enrollment enrolment enrolled enrollments graduates results outcome
outcomes benefit benefits need needs habit habits behavior behaviour
preference preferences better best good poor high low strong weak steady
rapid slow tired fatigue chronic exhausted restless plan plans payment
payments deposit deposits installment installments consultation
consultations appointment appointments booking bookings insurance warranty
warranties commuter commuters traveler travelers traveller travellers
sliding scale winter summer spring autumn""".split())


def _asserts(text):
    """Every sentence of the claim is a clause: it carries a predicate AND a
    word that binds one (determiner, pronoun, preposition, auxiliary, numeral).
    A run of terms with one verb typed into it is still a run of terms."""
    sentences = _sentences(text)
    return bool(sentences) and all(
        any(w in VERB_FORMS for w in _words(s))
        and any(w in FUNCTION_WORDS for w in _words(s))
        for s in sentences)


# ---------------------------------------------------------------------------
# grounding: is this sentence about this run at all? The words a sentence
# asserts are read against what THE RUN RECORDS — the owner facts it captured
# and the cited source's own recorded excerpts — plus the closed research
# vocabulary above. Content grounded nowhere in the run is content about
# something else: 'Sleep coaches sell backlinks to tired clinics.' predicates
# the run's own subject onto words no part of this run holds. Wording it
# differently cannot change that, and neither can filing it with a source.

# The verbs of transfer and sale: what a business does TO something it sells.
# A sentence that has the run's own subject doing one of these to content no
# part of the run records ('Sleep coaches sell backlinks to nurses.') is the
# spam shape, and one unrecorded word in it is enough.
COMMERCIAL_HINTS = (
    "sell", "buy", "rent", "leas", "trad", "swap", "barter", "pric", "charg",
    "cost", "offe", "suppl", "deliv", "purchas", "purc", "wholesale",
    "retail", "dropship", "bundle", "merch", "advertis", "promot", "market",
    "recommend", "list", "provide", "promise", "give", "gave", "given",
    "send", "sent", "ship", "hand", "order", "quote", "stock", "carry",
    "distribut", "licen", "subscrib", "vendor", "push")

# ---------------------------------------------------------------------------
# THE ASSERTION TYPE, NOT THE NOUN LIST.
#
# A research claim OBSERVES: it measures, counts, reports or states something
# about its subject, and its subject may be any audience, population, quantity
# or demand — one this run never named included. 'accountants report short
# sleep.' is research whatever 'accountants' is.
#
# A promotion ASSERTS AN EFFECT: it says a thing helps, improves, sells, wants,
# tracks or prices something. A sentence built that way is a claim ABOUT THE
# THING, so the thing has to be something the run records. 'Backlinks improve
# sleep quality for tired nurses.' is a claim about backlinks, and no part of
# this run ever heard of backlinks — the sleep and the nurses are borrowed to
# dress it up. That is the stuffing shape, and it is found from the predicate
# and the role it gives its arguments, never from the word being on a list.
#
# Deliberately absent: report, measure, find, survey, note, observe, record,
# estimate, study, appear, remain, tend, vary, rise, grow, increase, fall,
# lose, wake, rest. Those OBSERVE. A closed noun list is what moved the cliff in
# round five; this is the classification of what the sentence asserts, and no
# new audience noun can walk around it.
EFFECT_STEMS = """
affect allow attract boost buy carry charge choose cut deliver drive enable
follow generate give guarantee help impact improve influence involve keep lift
list need offer order outpace outweigh outperform perform prefer price promise
provide purchase push rank rate recommend sell send set shape solve
stock supply target track trade trust use want
""".split()


def _effect_forms():
    forms = set()
    for stem in EFFECT_STEMS:
        forms.add(stem)
        forms.add(stem + "s")
        if stem.endswith(("s", "x", "z", "ch", "sh")):
            forms.add(stem + "es")
        if stem.endswith("y"):
            forms.add(stem[:-1] + "ies")
            forms.add(stem[:-1] + "ied")
        elif stem.endswith("e"):
            forms.add(stem + "d")
        else:
            forms.add(stem + "ed")
        forms.add(stem[:-1] + "ing" if stem.endswith("e") else stem + "ing")
    for past in ("gave", "kept", "chose", "bought", "sold", "sent", "drove"):
        forms.add(past)
    return frozenset(forms)


EFFECT_FORMS = _effect_forms()

# Where a name may sit. A stretch that follows one of these and starts with a
# capital letter is naming material ("in Dallas", "in the United States") and
# is exempt from the phrase-head test. A stretch that follows a transfer or
# instrument preposition ("with Backlinks", "for Crypto") is asserted content
# whatever its first letter is, and so is a stretch the predicate takes
# directly ("rank Crypto and Backlinks").
NAME_PREPS = frozenset(
    "of in on at near around within across through over under beneath between "
    "among along behind beside beyond during after before since until by per "
    "via despite except against from toward towards into onto".split())
TRANSFER_PREPS = frozenset("with for to".split())

RAW_WORD_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def _word_pairs(text):
    """(lower-cased, as-written) pairs from the SAME tokeniser as _words, so a
    capital letter stays attached to the word it was written on."""
    return [(w.lower(), w) for w in RAW_WORD_RE.findall(_clean(text))]


def _is_name_stretch(prep, raw, subject=False):
    """Naming material: a stretch that sits where a name may sit — as the
    sentence's own subject, or after a non-transfer preposition — and starts
    like one. It names; it does not assert. Anywhere else a capital letter is
    just a capital letter."""
    return bool(raw) and raw[0][:1].isupper() and (
        (subject and prep is None)
        or (prep is not None and prep not in TRANSFER_PREPS))


def _stretches(pairs):
    """(governing preposition, stretch, start index) for every run of words
    between function words. The governing preposition is the last preposition
    among the function words that closed the stretch before."""
    out, prep, run, start = [], None, [], 0
    for i, (low, raw) in enumerate(pairs):
        if low in FUNCTION_WORDS:
            if run:
                out.append((prep, run, start))
                run = []
            if low in NAME_PREPS or low in TRANSFER_PREPS:
                prep = low
        else:
            if not run:
                start = i
            run.append((low, raw))
    if run:
        out.append((prep, run, start))
    return out


def _grounded_stems(facts, source):
    """Everything the OWNER recorded as content, plus the research vocabulary.

    The source's own `excerpts` are deliberately absent. They are the record a
    citation quote is checked against (rule 1), never the thing that makes a
    sentence about this run: a record the filer wrote cannot vouch for the
    filer's own claim, and a spam sentence quoted into `excerpts` used to make
    every word of itself "grounded"."""
    stems = set()
    for text in facts.values():
        stems.update(_stem(w) for w in _content_tokens(text))
    stems.update(_stem(w) for w in RESEARCH_WORDS)
    return stems


def _is_content(word):
    """Content rather than a binder, a count or a predicate — no function
    words, no numerals, no predicate, and no manner adverb (it modifies an
    assertion, it does not add one). A capital letter is no excuse: 'Backlinks'
    is content exactly as 'backlinks' is."""
    if len(word) < 3 or word in STOPWORDS or word in FUNCTION_WORDS:
        return False
    if word in VERB_FORMS or word.isdigit():
        return False
    return not (word.endswith("ly") and len(word) >= 5)


def _content_stems(words):
    """Content stems: what the words assert rather than bind, count or
    predicate."""
    return [_stem(w.lower()) for w in words if _is_content(w.lower())]


def _is_attributive(word):
    """An attributive FORM describes its head; it does not name a thing.
    'disturbed sleep', 'irregular habits', 'quiet homes' are qualities of sleep,
    habits and homes. 'a backlinks service' names a KIND of service. The
    difference is the word's FORM — an inflected or derived attributive — never
    its meaning and never its presence in a vocabulary. This is a list of
    English endings, not a list of permitted nouns: it cannot be gamed by
    swapping the stuffed word, because no noun ends in one of them by accident.
    ponytail: a bare attributive outside the research vocabulary ('sturdy
    chairs', 'ample space') is read as a referent and refused. Add a
    part-of-speech lexicon only if that trade starts to cost real research."""
    w = word.lower()
    return w in VERB_FORMS or w.endswith(
        ("ed", "ing", "ly", "al", "ar", "ary", "ory", "ous", "ive", "ful",
         "less", "ic", "ish", "y", "ey", "able", "ible", "ent", "ant", "ile",
         "ine", "ose", "ate", "ese", "an", "ian", "en", "et", "id", "oid",
         "ward", "most"))
def _predicate_tokens(words):
    """Where the sentence predicates. A token is a predicate when it is a verb
    form or one of the effect verbs below and no preposition governs it — a
    preposition governs its own noun ('before driving home' does not assert
    that anything drove)."""
    preps = NAME_PREPS | TRANSFER_PREPS
    out = []
    for i, w in enumerate(words):
        if w not in VERB_FORMS and w not in EFFECT_FORMS:
            continue
        if i and words[i - 1] in preps:
            continue
        out.append(i)
    return out


def _noun_phrases(pairs):
    """(predicate indices, [ (start, [(index, low, raw)], governing prep) ]).
    A noun phrase is a run of content between predicates and function words.
    Splitting at the predicate is what makes "Mattress deals" a subject and
    "sleep quality" its object instead of one blur of five words."""
    words = [low for low, _raw in pairs]
    preds = set(_predicate_tokens(words))
    binders = FUNCTION_WORDS | NAME_PREPS | TRANSFER_PREPS
    out, prep, run = [], None, []
    for i, (low, raw) in enumerate(pairs):
        if low in binders or i in preds:
            if run:
                out.append((run[0][0], run, prep))
                run = []
            if low in NAME_PREPS or low in TRANSFER_PREPS:
                prep = low
        else:
            run.append((i, low, raw))
    if run:
        out.append((run[0][0], run, prep))
    return sorted(preds), out


def _is_name_word(index, raw, prep, in_subject):
    """Naming material. A word names when it starts like one AND it is not the
    sentence's first word — sentence-initial capitals are just capitalisation,
    which is why 'Backlinks help tired nurses to sleep.' is asserted content
    while 'Dallas has over 40 practices listed.' names a place. And a name sits
    where a name may sit: as the subject, or after a non-transfer preposition.
    'with Backlinks' and 'rank Crypto' are asserted content however they are
    capitalised."""
    return bool(raw) and raw[:1].isupper() and index != 0 and (
        (in_subject and prep is None)
        or (prep is not None and prep not in TRANSFER_PREPS))


def _check_topic(claim, ref, text, facts, source, errors):
    """Every sentence stays on the run's own subject. Three structural tests,
    and the sentence must pass all of them. None of them asks whether a word is
    on a vocabulary list; each asks what the word DOES in this sentence.

    1. THE EFFECT TEST. A sentence that asserts what a thing DOES — helps,
       improves, sells, wants, tracks, prices — is a claim about that thing, so
       every content word in it has to be one the run records. The thing and the
       effect both come from the run, or the sentence is about something else.
       'Backlinks help tired nurses to sleep.' borrows the run's nurses and its
       sleep to sell the run a thing it never heard of; refused on 'backlinks',
       whatever 'backlinks' happens to mean. Reporting and measuring predicates
       are exempt, because they OBSERVE their subject and an audience the run
       did not name may still be observed.

    2. THE SMUGGLED MODIFIER. In what the sentence asserts, a stretch whose head
       the run records may not also carry a word it does not record. 'a
       backlinks service' is a service the run never heard of, wearing a head
       the run did record. A head the run does not record is left alone — it is
       the generic head of a measured quantity ('sleep problems', 'travel
       times', 'irregular meals'), which is where research prose puts words the
       run never named.

    3. THE TERM RUN. What it asserts with no word binding it is a run of terms
       however it is punctuated.

    And one shape is refused on a single unrecorded word whatever the counting
    says: a subject made of the run's own recorded owner-fact words doing one
    of the transfer and sale verbs (sell, offer, list, price, ...) to content
    the run does not record. That is what 'Sleep coaches sell backlinks to
    nurses.' is."""
    grounded = _grounded_stems(facts, source)
    fact_stems = set()
    for owner_text in facts.values():
        fact_stems.update(_stem(w) for w in _content_tokens(owner_text))
    for sentence in _sentences(text):
        pairs = _word_pairs(sentence)
        words = [low for low, _raw in pairs]
        preds, nps = _noun_phrases(pairs)
        cut = preds[0] if preds else len(words)
        sells = bool(cut) and any(h in words[cut - 1] for h in COMMERCIAL_HINTS)
        subject = _content_stems(words[:cut])
        own_subject = bool(subject) and all(s in fact_stems for s in subject)

        # the content of one noun phrase, naming material left out.
        def content_of(np, in_subject):
            _start, run, prep = np
            return [low for _i, low, raw in run
                    if not _is_name_word(_i, raw, prep, in_subject)
                    and _is_content(low)]

        label, bad = None, []

        # 1. THE EFFECT TEST. What an effect predicate takes as its subject and
        #    as its complement is the thing the sentence is about, so it has to
        #    be material the run records. Argument-scoped on purpose: 'Dallas
        #    has over 40 sleep coaching practices listed publicly.' names Dallas
        #    and asserts 'listed' of the practices, so only the practices are
        #    read — while 'Backlinks help tired nurses to sleep.' asserts
        #    'help' of the backlinks, and the run has never heard of backlinks.
        for i in preds:
            if words[i] not in EFFECT_FORMS:
                continue
            following = [p for p in preds if p > i]
            stop = following[0] if following else len(words)
            spoken = []
            for np in nps:
                if np[0] < i:
                    spoken = [content_of(np, True)]     # the subject
                elif np[0] < stop:
                    spoken.append(content_of(np, False))
            off = sorted({s for run in spoken for s in run
                          if _stem(s) not in grounded})
            if off:
                label, bad = "what it asserts", off
                break

        # 2. THE SMUGGLED MODIFIER. A phrase whose head the run records wears
        #    recorded material and nothing else. Two carve-outs, both
        #    structural. A head the run does not record is left alone: that is
        #    the generic head of a measured quantity ('sleep problems', 'travel
        #    times', 'irregular meals'), which is where research prose puts
        #    words the run never named. And a modifier that is an attributive
        #    FORM — a participle or a manner adverb ('disturbed sleep', 'closing
        #    shifts') — describes its head, it does not name a thing. Only a
        #    word that REFERS sits in the modifier of a recorded head, and
        #    'a backlinks service' is exactly that.
        if not bad:
            for np in nps:
                if np[0] <= cut:
                    continue
                kept = content_of(np, False)
                if not kept or _stem(kept[-1]) not in grounded:
                    continue
                off = sorted({w for w in kept[:-1]
                              if _stem(w) not in grounded
                              and not _is_attributive(w)})
                if off:
                    label, bad = "what it asserts", off
                    break

        # 3. THE TERM RUN. What it asserts with no word binding it is a run of
        #    terms however it is punctuated.
        if not bad:
            for label, span in (("what it asserts", words[cut:]),
                                ("the sentence", words)):
                stems = _content_stems(span)
                off = sorted({s for s in stems if s not in grounded})
                if not off:
                    continue
                on = len(stems) - len(off)
                bound = any(w in FUNCTION_WORDS for w in span)
                unbound_run = label == "what it asserts" and not bound
                sold = label == "what it asserts" and sells and own_subject
                if not unbound_run and not sold and len(off) <= on:
                    continue
                bad = off
                break
        if bad:
            errors.append(
                "%s: not about this run — %s carries %s, which appear in "
                "nothing the run records (its owner facts) and in no research "
                "term. Ground the words in the run's own record or drop the "
                "claim" % (ref, label, ", ".join(bad)))
            break

# ---------------------------------------------------------------------------
# owner-fact relations
def _fact_texts(record):
    """The owner facts THE RUN RECORDED: the brief's own offer/audience/action
    fields, and `facts[]` entries that carry their provenance tag. An entry
    without `role: "owner-fact"` is not an owner statement and grounds
    nothing — a claim cannot add an owner fact to the record it is checked
    against."""
    out = {}
    for field in FACT_FIELDS:
        text = _norm(record.get(field))
        if text:
            out[field] = text
    for rec in record.get("facts") or []:
        if not isinstance(rec, dict):
            continue
        if _norm(rec.get("role")).lower() != "owner-fact":
            continue
        field = _norm(rec.get("field")).lower()
        text = _norm(rec.get("text"))
        if field and text:
            out.setdefault(field, text)
    return out


def _anchor_in(text, anchor):
    a = _stem(_clean(anchor).lower())
    return any(_stem(w) == a for w in _words(text))


def _derive_about(text, facts):
    """The owner fact this claim informs, recorded as {fact, anchor}."""
    claim_words = {_stem(w) for w in _words(text)}
    for field in FACT_FIELDS:
        fact = facts.get(field)
        if not fact:
            continue
        for word in _words(fact):
            if len(word) >= 3 and _stem(word) in claim_words:
                return {"fact": field, "anchor": word}
    return None


def _check_about(claim, ref, facts, errors):
    """The owner-fact relation, verified in the claim, in every sentence of it,
    and in the owner fact's own text AS THE RUN RECORDED IT. Returns True when
    it holds.

    `about.fact_text` is the claim talking about its own evidence, so it is
    never consulted as evidence: when present it is checked as a copy of the
    recorded owner fact, and anything else — a text the claim invented, or one
    contradicting the record — is refused. When the run recorded no owner fact
    for the named field there is nothing to check the anchor against, and the
    claim is refused rather than checked against itself."""
    about = claim.get("about")
    if about is None:
        errors.append("%s: no checkable relation to any owner fact — a research "
                      "claim must say which owner fact (offer, audience, action) "
                      "it informs" % ref)
        return False
    if not isinstance(about, dict):
        errors.append("%s: about must be an object naming the owner fact "
                      "({\"fact\": ..., \"anchor\": ...}), not %s"
                      % (ref, type(about).__name__))
        return False
    field = _norm(about.get("fact")).lower()
    anchor = _norm(about.get("anchor")).lower()
    if field not in FACT_ALIASES:
        errors.append("%s: about.fact %r is not an owner fact field"
                      % (ref, about.get("fact")))
        return False
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{2,}", anchor):
        errors.append("%s: about.anchor %r is not a checkable subject term"
                      % (ref, about.get("anchor")))
        return False
    recorded = [facts[name] for name in FACT_ALIASES[field] if facts.get(name)]
    supplied = about.get("fact_text")
    if supplied is not None:
        if not isinstance(supplied, str):
            errors.append("%s: about.fact_text must be a string, not %s"
                          % (ref, type(supplied).__name__))
            return False
        copy = _norm(supplied).lower()
        if not recorded or copy not in {_norm(r).lower() for r in recorded}:
            errors.append("%s: about.fact_text is this claim's own evidence — the "
                          "%s owner fact is read from what the run recorded "
                          "(offer/audience/action, or facts[] tagged role "
                          "owner-fact), never from a text the claim carries"
                          % (ref, field))
            return False
    if not recorded:
        errors.append("%s: the run records no %s owner fact to check about.anchor "
                      "%r against — record the owner's own words (facts[] tagged "
                      "role owner-fact) or drop the claim"
                      % (ref, field, anchor))
        return False
    if not any(_anchor_in(c, anchor) for c in recorded):
        errors.append("%s: about.anchor %r is not in the %s fact text"
                      % (ref, anchor, field))
        return False
    if not _anchor_in(claim.get("text", ""), anchor):
        errors.append("%s: about.anchor %r is not in the claim text"
                      % (ref, anchor))
        return False
    for sentence in _sentences(claim.get("text", "")):
        if not _anchor_in(sentence, anchor):
            errors.append("%s: about.anchor %r is not in every sentence of the "
                          "claim — one subject per claim" % (ref, anchor))
            return False
    return True


def _is_self_claim(text):
    """Assertions about the named business's own size, results, standing,
    price or guarantees. Structural: WHO the sentence is about (the business,
    its offering, or its own people) plus WHAT it asserts (an escalation)."""
    subject = (SELF_RE.search(text) or OFFERING_NOUN_RE.search(text)
               or OUTCOME_NOUN_RE.search(text))
    return bool(subject)


OFFERING_NOUN_RE = re.compile(
    r"\b(?:programs?|services?|companies|business(?:es)?|practices?|clinics?"
    r"|studios?|academ(?:y|ies)|courses?|coach(?:es|ing)?|providers?|brands?"
    r"|products?|apps?|methods?|systems?)\b",
    re.IGNORECASE)
OUTCOME_NOUN_RE = re.compile(
    r"\b(?:customers?|clients?|students?|patients?|members|users|families"
    r"|enrol(?:lees?|ments?)|enrolled|graduates?|reviews?|testimonials?"
    r"|revenue|sales|conversions?|bookings?|appointments?|locations?"
    r"|years in business)\b",
    re.IGNORECASE)
SELF_WORD_RE = re.compile(
    r"\b(?:we|us|our|ours|ourselves|my)\b", re.IGNORECASE)
SELF_DEM_RE = re.compile(
    r"\b(?:this|that|the)\s+(?:program|service|company|business|practice"
    r"|clinic|studio|academy|course|coaching|method|system|product|offer(?:ing)?"
    r"|app|team|staff|brand|firm|agency|clients?|customers?|students?|patients?"
    r"|members|users|families)\b",
    re.IGNORECASE)
OTHER_SIDE_RE = re.compile(
    r"\b(?:compet(?:e|ing|ition|itors?)|rival(?:s)?|other|alternative(?:s)?"
    r"|local|national|similar|competing)\b(?:\s+\w+){0,2}\s+"
    r"(?:program|service|companies|business(?:es)?|practices?|clinics?"
    r"|studios?|academ(?:y|ies)|courses?|coach(?:es|ing)?|providers?|brands?"
    r"|products?|apps?|methods?|systems?)\b",
    re.IGNORECASE)


def _is_self_claim(text):
    """The claim asserts something of the named business itself. First person
    is always the business; a demonstrative plus an offering noun is the
    business unless the sentence is explicitly about the other side of the
    market — 'competing sleep programs charge $2,400' is a competitor claim,
    and stays one."""
    if SELF_WORD_RE.search(text):
        return True
    return bool(SELF_DEM_RE.search(text)) and not OTHER_SIDE_RE.search(text)


def _about_business(text):
    """The claim names the business, its offering or its own people at all —
    the class market evidence can never verify when it is escalated."""
    return bool(SELF_DEM_RE.search(text) or OFFERING_NOUN_RE.search(text)
                or OUTCOME_NOUN_RE.search(text))


# ---------------------------------------------------------------------------
def _brief_claim_ids(brief):
    """Ids of claims the owner supplied in the brief — their raw answer
    identity even when the brief did not spell one out."""
    ids = set()
    for i, c in enumerate((brief or {}).get("claims") or []):
        if isinstance(c, dict) and _nonempty(c.get("id")):
            ids.add(c["id"].strip())
        elif isinstance(c, dict):
            ids.add("claim-%d" % (i + 1))
    return ids


def is_fiction_claim(claim):
    return isinstance(claim, dict) and claim.get("provenance") == "fiction"


def tag_claims(claims, brief=None, source_ids=None):
    """Attach a provenance tag to each claim. Returns (tagged, errors).

    This is the authoring step's job: an untagged claim that came with a
    citation becomes public-fact; an untagged claim the owner filed in the
    brief becomes owner-fact with its answer identity kept. An untagged claim
    from nowhere stays untagged and is returned as an error — the validator
    below refuses it rather than inventing an origin.
    """
    source_ids = set(source_ids or ())
    brief_ids = _brief_claim_ids(brief)
    tagged, errors = [], []
    for i, claim in enumerate(claims or []):
        if not isinstance(claim, dict):
            errors.append("claim %d: not an object" % (i + 1))
            tagged.append({"id": "claim-%d" % (i + 1), "text": str(claim),
                           "status": "PASS"})
            continue
        rec = dict(claim)
        rec.setdefault("id", "claim-%d" % (i + 1))
        prov = _norm(rec.get("provenance")).lower()
        if prov and prov not in PROVENANCE:
            errors.append("%s: provenance %r is not one of %s"
                          % (rec["id"], rec.get("provenance"), ", ".join(PROVENANCE)))
        elif not prov:
            src = _norm(rec.get("source"))
            if src and (not source_ids or src in source_ids):
                rec["provenance"] = "public-fact"
                rec["capture_date"] = rec.get("capture_date") or rec.get("retrieved")
            elif rec["id"] in brief_ids:
                rec["provenance"] = "owner-fact"
                rec["owner_ref"] = rec.get("owner_ref") or "brief-claim:%s" % rec["id"]
            # else: leave untagged — validate_bundle refuses it.
        tagged.append(rec)
    return tagged, errors


def _sections_for(claim):
    explicit = claim.get("sections")
    if isinstance(explicit, list) and explicit:
        return [s for s in explicit if s in VALID_SECTIONS]
    if is_fiction_claim(claim):
        return [PREMISE]
    return list(SECTIONS)


def _dedupe(tagged):
    """One record per distinct assertion. The same sentence filed by the owner
    and again by the gatherer is one claim with the better support attached —
    not two lines of padding. Ids are kept so lineage stays visible."""
    out, by_text = [], {}
    for claim in tagged:
        if not isinstance(claim, dict):
            out.append(claim)
            continue
        key = _norm(claim.get("text")).lower()
        first = by_text.get(key) if key else None
        if first is None:
            claim.setdefault("merged_ids", [])
            by_text[key] = claim
            out.append(claim)
            continue
        if not first.get("source") and claim.get("source"):
            first["source"] = claim["source"]
            first["provenance"] = claim.get("provenance", first.get("provenance"))
        if claim.get("owner_ref") and not first.get("owner_ref"):
            first["owner_ref"] = claim["owner_ref"]
        first["merged_ids"].append(claim.get("id"))
        for section in claim.get("sections") or []:
            if section not in first.setdefault("sections", []):
                first["sections"].append(section)
    return out


def author_bundle(brief, evidence):
    """Author the research_bundle for this run.

    Tags every claim, records the owner-fact relation each one carries (or can
    prove against the brief's own facts), assigns it to the research sections
    it supports, keeps the owner's premise as explicitly fictional, and records
    the brief facts as owner statements. No network, no model call, no
    byte-size gate.
    """
    brief = brief or {}
    evidence = evidence or {}
    sources = evidence.get("sources") or brief.get("sources") or []
    tagged, errors = tag_claims(evidence.get("claims") or brief.get("claims"),
                                brief, {s.get("id") for s in sources
                                        if isinstance(s, dict)})
    premise = brief.get("premise")
    if premise:
        text = premise.get("text") if isinstance(premise, dict) else premise
        if _nonempty(text) and _norm(text).lower() not in {
                _norm(c.get("text")).lower() for c in tagged if isinstance(c, dict)}:
            tagged.append({"id": "premise-1", "text": _norm(text),
                           "provenance": "fiction", "sections": [PREMISE],
                           "label": "proposed-fiction"})
    facts = _fact_texts(brief)
    # Claims the gatherer attached to a source were matched verbatim against
    # the fetched page — that match IS the citation, so it is recorded here as
    # a per-claim quote. A claim the caller filed themselves is never given
    # one: an escalated claim they did not cite is refused by the validator.
    gathered = bool((brief or {}).get("_gathered")) or (
        isinstance(evidence, dict) and ("urls" in evidence or "fetched" in evidence))
    for claim in tagged:
        claim.setdefault("sections", _sections_for(claim))
        if isinstance(claim, dict) and not is_fiction_claim(claim) \
                and not claim.get("about"):
            derived = _derive_about(claim.get("text", ""), facts)
            if derived:
                claim["about"] = derived
        if gathered and isinstance(claim, dict) \
                and claim.get("provenance") == "public-fact" \
                and _nonempty(claim.get("source")):
            text = _norm(claim.get("text"))
            support = claim.get("support")
            support = dict(support) if isinstance(support, dict) else {}
            if text and not support.get("quote"):
                support.setdefault("source", claim.get("source"))
                support.setdefault("locator", "fetched page body, verbatim match")
                support["quote"] = text
                claim["support"] = support
            if _markers(text) and not _allowed_market_class(claim) \
                    and not _is_self_claim(text):
                sections = claim.get("sections") or []
                claim["class"] = ("audience-evidence" if "audience" in sections
                                  else "market-fact" if "market" in sections
                                  else "competitor-fact")
        support = claim.get("support")
        if isinstance(support, dict) and _nonempty(support.get("locator")):
            claim.setdefault("locator", support["locator"])
    tagged = _dedupe(tagged)
    bundle = {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "offer": _norm(brief.get("offer")),
        "audience": _norm(brief.get("audience")),
        "action": _norm(brief.get("action") or brief.get("cta")),
        "facts": [{"role": "owner-fact", "field": f, "text": _norm(brief.get(f))}
                  for f in FACT_FIELDS
                  if _nonempty(brief.get(f))],
        "sources": [dict(s) for s in sources if isinstance(s, dict)],
        "claims": tagged,
        "tagging_errors": errors,
        "generated": evidence.get("generated"),
    }
    return bundle


def _check_support(claim, ref, source, errors):
    """The citation is checked against text recorded for that source when the
    source records any: a quote the source does not hold is decoration, not
    support. A source that records no excerpt text leaves the quote checkable
    by opening the source — so the quote must at least name this claim."""
    support = claim.get("support")
    if support is None:
        return
    if not isinstance(support, dict):
        errors.append("%s: support must be an object ({{\"source\", \"locator\", "
                      "\"quote\"}}), not %s" % (ref, type(support).__name__))
        return
    for key in ("locator", "quote"):
        if key in support and not isinstance(support[key], str):
            errors.append("%s: support.%s must be a string, not %s"
                          % (ref, key, type(support[key]).__name__))
    quote = support.get("quote")
    if not isinstance(quote, str) or not quote.strip() or not source:
        return
    excerpts = source.get("excerpts")
    if not isinstance(excerpts, list) or not excerpts:
        return
    haystack = " ".join(_clean(x) for x in excerpts if isinstance(x, str))
    if _clean(quote).lower() not in haystack.lower():
        errors.append("%s: citation cannot be checked — the quoted text is not "
                      "in what source %s records" % (ref, support.get("source")))


def _check_escalation(claim, ref, text, source, errors):
    """Superlative, ranking, count, guarantee and "$"/"#" claims need an
    allow-listed class and a source citation for THIS claim: a quote that the
    source record holds and that itself carries the claim's markers."""
    markers = _markers(text)
    if not markers:
        return
    cls = claim.get("class")
    if not isinstance(cls, str) or _norm(cls).lower() not in ALLOWED_MARKET_CLASSES:
        errors.append(
            "%s: uncited claim — a superlative, ranking, count, guarantee or "
            "price claim must declare an allowed market class (%s) and carry a "
            "source citation for this claim"
            % (ref, ", ".join(ALLOWED_MARKET_CLASSES)))
        return
    support = claim.get("support")
    quote = support.get("quote") if isinstance(support, dict) else None
    if not isinstance(quote, str) or not quote.strip():
        errors.append("%s: uncited claim — a superlative, ranking, count, "
                      "guarantee or price claim must carry the source quote "
                      "that backs this exact claim" % ref)
        return
    quoted = set(_markers(quote))
    missing = sorted({(kind, core) for kind, core in markers} - quoted)
    if missing:
        errors.append(
            "%s: the citation is not for this claim — the quote does not carry "
            "%s" % (ref, ", ".join("%s %s" % m for m in missing)))


def validate_bundle(bundle):
    """Refuse a research bundle that is not real research.

    Returns a list of error strings; empty list == accepted. Every rule is
    about content and provenance — support to a source, support to an owner
    fact, a cited basis for an escalated claim. Nothing here counts bytes,
    separators, word endings or repetitions, so a padded or reshaped keyword
    run cannot buy a pass.
    """
    errors = []
    if not isinstance(bundle, dict):
        return ["bundle: not an object"]
    claims = bundle.get("claims")
    sources = bundle.get("sources") or []
    if not isinstance(claims, list) or not claims:
        return ["claims: empty research bundle (at least one claim required)"]
    if not isinstance(sources, list):
        return ["sources: not a list"] + [
            "claims: empty research bundle (at least one claim required)"]
    by_id = {s.get("id"): s for s in sources if isinstance(s, dict)}
    facts = _fact_texts(bundle)
    for err in bundle.get("tagging_errors") or []:
        errors.append("tagging: %s" % err)

    seen_text = {}
    for i, claim in enumerate(claims):
        ref = claim.get("id") if isinstance(claim, dict) else None
        ref = ref or "claim-%d" % (i + 1)
        if not isinstance(claim, dict):
            errors.append("%s: not an object" % ref)
            continue
        prov = claim.get("provenance")
        if prov not in PROVENANCE:
            errors.append("%s: no provenance tag (expected one of %s)"
                          % (ref, ", ".join(PROVENANCE)))
        raw_text = claim.get("text")
        if not isinstance(raw_text, str):
            errors.append("%s: claim text must be a string, not %s"
                          % (ref, type(raw_text).__name__))
            continue
        text = _norm(raw_text)
        if not text:
            errors.append("%s: claim text is empty" % ref)
            continue
        key = text.lower()
        if key in seen_text:
            errors.append("%s: duplicate of %s" % (ref, seen_text[key]))
        seen_text.setdefault(key, ref)

        sections = claim.get("sections")
        if not isinstance(sections, list) or not sections:
            errors.append("%s: no research section assigned" % ref)
        else:
            for s in sections:
                if s not in VALID_SECTIONS:
                    errors.append("%s: unknown section %r" % (ref, s))

        if not is_fiction_claim(claim):
            if not _asserts(text):
                errors.append("%s: keyword stuffing — a run of keywords is not a "
                              "research claim: no predicate binds it into a "
                              "clause" % ref)
            if facts or claim.get("about") is not None:
                _check_about(claim, ref, facts, errors)
            src_ref = claim.get("source")
            if not isinstance(src_ref, str):
                support = claim.get("support")
                src_ref = support.get("source") if isinstance(support, dict) else None
            _check_topic(claim, ref, text, facts,
                         by_id.get(src_ref) if isinstance(src_ref, str) else None,
                         errors)

        source = None
        if prov == "public-fact":
            src_id = claim.get("source")
            support = claim.get("support")
            if isinstance(support, dict):
                if src_id is None:
                    src_id = support.get("source")
                elif support.get("source") not in (None, src_id):
                    errors.append("%s: support.source %r disagrees with source %r"
                                  % (ref, support.get("source"), src_id))
            if not isinstance(src_id, str) or src_id not in by_id:
                errors.append("%s: public-fact with no resolvable source" % ref)
            else:
                source = by_id[src_id]
                if not _nonempty(source.get("url")):
                    errors.append("%s: source %s has no url" % (ref, src_id))
                if not _nonempty(source.get("retrieved")):
                    errors.append("%s: source %s has no capture date"
                                  % (ref, src_id))
                claim.setdefault("capture_date", source.get("retrieved"))
            _check_support(claim, ref, source, errors)
            _check_escalation(claim, ref, text, source, errors)
            if _markers(text) and (
                    _is_self_claim(text)
                    or (_about_business(text)
                        and not _allowed_market_class(claim))):
                errors.append(
                    "%s: unsupported business claim — market evidence cannot "
                    "verify the client's own results/price/guarantee; make it "
                    "an owner-fact with its raw answer identity, or remove or "
                    "qualify it" % ref)
        elif prov == "owner-fact":
            if not _nonempty(claim.get("owner_ref")):
                errors.append("%s: owner-fact with no raw answer identity "
                              "(owner_ref)" % ref)
            claim.setdefault("verification", "owner-asserted-unverified")
        elif prov == "fiction":
            claim.setdefault("label", "proposed-fiction")

    covered = {s: 0 for s in SECTIONS}
    for claim in claims:
        if isinstance(claim, dict) and claim.get("provenance") in PROVENANCE:
            for s in claim.get("sections") or []:
                if s in covered:
                    covered[s] += 1
    # A fiction-only bundle is an explicitly proposed premise, not market
    # research: row 1 allows that. Anything claiming a real fact still has to
    # support every section with a labelled claim.
    fiction_only = bool(claims) and all(
        isinstance(c, dict) and c.get("provenance") == "fiction" for c in claims)
    for section in SECTIONS:
        if not covered[section] and not fiction_only:
            errors.append(
                "%s: no claim supports this section — a header that echoes the "
                "brief is not research" % section)
    return errors


def _allowed_market_class(claim):
    cls = claim.get("class")
    return isinstance(cls, str) and _norm(cls).lower() in ALLOWED_MARKET_CLASSES


def section_claims(bundle, section):
    """Claims assigned to one section, in filed order."""
    return [c for c in (bundle.get("claims") or [])
            if isinstance(c, dict) and section in (c.get("sections") or [])]

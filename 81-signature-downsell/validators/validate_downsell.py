"""Skill 81 downsell validators (stdlib only, fail-closed).

Implements the checks named in:
- packet 11_SKILL_81_DOWNSELL_SPEC.md sections 4, 5, 6, 10
- packet 02_SHARED_CONTRACTS_AND_ARCHITECTURE.md sections 3, 4
- packet 18_END_TO_END_ACCEPTANCE_MATRIX.md section 6 (eight-section derivation)

A validator returns a list of violation codes; empty list means pass.
Validators never raise on malformed input: malformed input is a violation.
Nothing here calls GHL, charges anything, or proves a live payment.
Payment truth always comes from a verified native adapter upstream.

v0.2: fixes from independent review round 1 (2026-10-15): correct corpus prose
heading constant, CTA crash, deliverables comparison, excludes enforcement,
pains distinctness, scarcity evidence, private-label leakage, full-surface
price-leak scan, u2 guard, base-purchase protection, disclosure cross-checks.

v0.4: cure of the independent re-review of v0.3 (2026-10-16): D-9 price-format
regression restored ("$27.00", "27.00 USD", "27-dollar"; genuinely different
amounts such as "$279" and "$27.50" stay unflagged), wider D-3 scarcity
families (couple-of-spots, enrollment/registration closing, prices-rise,
selling-out, filling/running-out), D-6/N-1 decline-ref versus purchase-ref
comparison added to validate_copy (the page surface, not only the result
extension), D-8 private-label variants ("internal review", no-space
"Section3"), D-13 synonym/stem-normalized identical-promise matching plus a
same-shape lower-price owner-flag tier, N-2 take-away loss threats, and N-3
non-string scarcity evidence references counting as missing. Completed by
the partials cure lane (2026-10-16): the N-2 removal phrasing "removes
what you purchased", N-4 (wholly malformed trial-disclosure input returns
D1-DISCLOSURE-MALFORMED-INPUT instead of a clean pass), and the D-9
zero-cents widening (any run of zeros after the dot, so "$27.0" and
"$27.000" are caught while "$27.5" and "$27.50" stay unflagged).

Round 2 cure (2026-10-16), against the governing re-review that kept
D-3, D-8, D-13 and N-2 PARTIAL under fresh variants: the scarcity,
private-label and loss-of-purchase scans are widened by named family
mechanism rather than by recorded sentence (limited-time and
limited-availability claims, deadline-carrying miss-out exhortations,
too-late and going-fast wording, small-count claims with or without
"only", depletion and stock wording, availability deadlines and
final-window claims; internal-audience, abbreviated-section,
confidentiality and framework-structure label families; forfeit,
strip, cancel and withdraw loss verbs plus the passive and
object-first forms). D-13 gains a partial-paraphrase tier: same shape
at a lower total with at least one anchor deliverable matching at the
paraphrase threshold and at least one deliverable out of token
contact is flagged for owner decision (spec 11 section 4). The price
scan also covers the prefix-currency form ("USD 27") and the slang
denomination ("27 bucks", "twenty-seven bucks"). A nested malformed
prices value in validate_trial_disclosure returns
D1-DISCLOSURE-MALFORMED-INPUT instead of a clean pass.

Round 3 cure (2026-10-16), against the round 2 re-review: the plain
limited predicate for scarcity ("Seats are limited"), the "no
longer" availability claim with an inserted auxiliary, exhortation
plus deadline forms, the internal document-noun class and the
audience forms for private labels, and the remaining ordinary loss
verbs (delete, wipe, terminate, erase, the plain
lose-what-you-bought form, cut off, purchase-is-gone), all still
keyed to the bought object.

Ruling S81-DEC-LEXRES-01 fix (2026-10-16): the negation guard on
the loss-of-purchase scan now sees contracted negations. _norm
splits "won't" into "won t", which hid the negation from the
guard's "not" lookbehind and flagged the reassurance "You won't
lose what you bought with us" as a loss threat. The loss scan now
expands the "n't" ending to " not" before normalization (see
_loss_scan_text), and the threat-verb branches that carried no
guard carry the same never/not lookbehind pair, so a negated loss
statement reads as the reassurance it is. No coverage list was
widened: the three wording-coverage tails (D-3, D-8, N-2) are an
owner-accepted limitation recorded in
references/terms-entitlement-review.md.

v0.3: fixes from independent review lane 5 (2026-10-16), defects D-1 to D-15:
full-obligation totals across all price entries, never-raise hardening on
every public validator, wider fake-scarcity phrasing coverage, decline action
must carry an action_ref, whitespace-only text counts as missing everywhere,
the result extension decline ref must differ from the purchase action ref,
the loss-of-purchase scan is page-wide, more private-label variants, example
prices written as words or odd formats, installment disclosure required in
the validator and the result-extension schema, pains threshold aligned to
the missed-item threshold, paraphrase-resistant identical-promise checks,
changed access terms must record an actual difference, and the trial
renewal amount is cross-checked even when the offer schedule is empty.

D-13 zero-token cure (2026-10-17): a feature-paraphrase tier beside the
lexical tiers. When no D1 deliverable reaches the paraphrase threshold
against any U1 deliverable (the recorded zero-content-token residual,
outside ruling S81-DEC-LEXRES-01), the tier compares structured promise
features (cadence, live event, gated access, named person, evaluation,
material) item by item under the same shape and lower-total gates, and
flags a full feature-signature match with the identical-promise code
for owner decision. The D-3, D-8 and N-2 families are untouched.
"""
import re

CANONICAL_HEADING = "When Time Runs Out"
# Owner corpus, downsell instructions prose, quoted exactly (capital T on Times):
PROSE_HEADING = "When Times Run Out"

SECTION_ROLES = [
    "big_bold_claim",
    "big_bold_pain_1",
    "big_bold_pain_2",
    "big_bold_pain_3",
    "big_bold_why",
    "big_bold_who",
    "big_bold_what",
    "when_time_runs_out",
]

# Roles from the original 12-section format that must never reappear in D1.
FORBIDDEN_ROLES = {"benefit_1", "benefit_2", "benefit_3", "big_how_to",
                   "benefits", "how", "how_to", "founder_message"}
FORBIDDEN_HEADING_WORDS = ("benefit", "how to", "how-to")

# Example-only amounts from the owner sample downsell page (minor units, USD).
# Blocked in production copy/requests unless an approved price matches.
EXAMPLE_ONLY_AMOUNTS_MINOR = {100, 2700, 99700}

# Negation guard (ruling S81-DEC-LEXRES-01, 2026-10-16): a threat
# verb immediately preceded by "never" or "not" is a reassurance,
# not a threat ("You never lose what you bought with us"). Guarded
# branches carry the (?<!never )(?<!not ) lookbehind pair in front
# of the threat verb, and the loss scan feeds them text whose
# contracted negations were expanded first (see _loss_scan_text),
# so "won't" reads as the "not" the guard was written for.
LOSS_OF_PURCHASE_PATTERNS = [
    r"you will lose your (original )?purchase",
    r"you lose access to what you (already )?bought",
    r"your (original )?order will be (cancelled|removed|revoked)",
    r"(?<!never )(?<!not )lose (your|the) .{0,30}you (already )?(bought|purchased)",
    # Re-review N-2: take-away / removal threats in the same family.
    r"(?<!never )(?<!not )take away .{0,40}(you already (bought|purchased)|your access|the access)",
    r"(remove|revoke) .{0,40}(you already (bought|purchased)|your access)",
    r"you (will )?lose your access\b",
    # Partials cure lane (2026-10-16): the removal phrasing the patterns
    # above still missed, "removes what you purchased" (and its
    # take-away twin). The object is what was bought, named directly,
    # with no "already" and no "your access" in between.
    r"(?<!never )(?<!not )(remove|removes|removed|removing|revoke|revokes|take away) "
    r".{0,40}what you (already )?(bought|purchased)",
    # Round 2 cure (2026-10-16): the governing re-review found the verb
    # vocabulary still list-bound: forfeit, strip, cancel and withdraw
    # threats, the passive forms, and the object-first forms all
    # passed. The patterns below work by verb family plus bought
    # object, in both directions, instead of by recorded sentence.
    r"\b(?<!never )(?<!not )(forfeit|forfeits|forfeiting|strip|strips|stripping|"
    r"withdraw|withdraws|withdrawing)\b"
    r".{0,40}(what you (already )?(bought|purchased)"
    r"|the access you (already )?(bought|purchased)"
    r"|your (original )?(purchase|order))",
    # The cancel family needs the seller as subject: the buyer
    # cancelling is the truthful flow the spec requires ("you can
    # cancel anytime", "if you cancel, what you bought stays yours"),
    # while "we cancel what you bought" is the threat. The remove and
    # revoke forms of this family are already covered above.
    r"\b(we|us) (will |shall )?(?<!never )(?<!not )(cancel|cancelled|canceled)\b"
    r".{0,40}(what you (already )?(bought|purchased)"
    r"|the access you (already )?(bought|purchased))",
    r"\b(?<!never )(?<!not )(take away|takes away)\b"
    r".{0,40}what you (already )?(bought|purchased)",
    r"your (original )?(purchase|order) will be "
    r"(cancelled|canceled|removed|revoked|deleted|stripped)",
    r"(what you (already )?(bought|purchased)"
    r"|the access you (already )?(bought|purchased)"
    r"|the \w+ you (already )?(bought|purchased)"
    r"|your bought \w+)"
    r".{0,40}\b(gets|will be|is) "
    r"(revoked|removed|cancelled|canceled|deleted|stripped|taken away)",
    r"your bought \w+.{0,30}\b(?<!never )(?<!not )"
    r"(disappears?|vanishes)\b",
    # Round 3 cure (2026-10-16): the round 2 re-review's verb sweep
    # found the same list-bound mechanism in the remaining ordinary
    # verbs: delete, wipe, terminate and erase in the active voice,
    # the plain lose-what-you-bought form (no possessive before
    # "what"), the cut-off forms, and "your purchase is gone". Every
    # branch keeps the bought-object requirement, so a truthful
    # sentence about the buyer's own plan or paid period is not read
    # as a threat against what was already bought.
    r"\b(?<!never )(?<!not )(delete|deletes|deleted|wipe|wipes|wiped|terminate|"
    r"terminates|terminated|erase|erases|erased)\b"
    r".{0,40}(what you (already )?(bought|purchased)"
    r"|the access you (already )?(bought|purchased)"
    r"|the \w+ you (already )?(bought|purchased)"
    r"|your (original )?(purchase|order)"
    r"|your bought \w+)",
    r"\b(?<!never )(?<!not )(lose|loses)\b"
    r".{0,30}what you (already )?(bought|purchased)",
    # The object-first span is tempered so it cannot cross a
    # negation word: in "Your access won't be cut off" the negation
    # sits inside the span, and a span that crosses it would read a
    # reassurance as a threat (ruling S81-DEC-LEXRES-01).
    r"(your (access|purchase|order|account)"
    r"|the access you (already )?(bought|purchased))"
    r"(?:(?!\b(?:not|never)\b).){0,20}cut off\b",
    r"\b(?<!never )(?<!not )cut off\b.{0,40}(your (access|purchase|order)"
    r"|what you (already )?(bought|purchased))",
    r"\byour (original )?(purchase|order) (is|will be) gone\b",
    r"\byour (original )?(purchase|order) gets "
    r"(terminated|wiped|erased|deleted)\b",
]

SCARCITY_CLAIM_PATTERNS = [
    r"one time only", r"one-time only", r"never again", r"vanish",
    r"disappear", r"expires? in", r"countdown", r"timer",
    r"only \d+ (spots|seats|places) (left|remain)", r"gone for good",
    r"\d+\s?(minutes|hours|seconds) left\b",
    # Lane 5 D-3: common scarcity phrasings that carry no digit at all.
    r"only (a few|a handful|few)\b", r"\blast chance\b", r"\bhurry\b",
    r"\bdoors? (close|closes|closing)\b", r"\bclosing soon\b",
    r"\bprice (goes up|increases|will rise|is going up)\b",
    # Re-review D-3 cure: the phrasing families the v0.3 list still missed.
    # Couple-of-spots and counted/word-number spots families.
    r"only (a couple|couple)( of)? (spots|seats|places|openings)\b",
    r"\bcouple of (spots|seats|places|openings)\b",
    r"only \d+ (spots|seats|places|openings)( are| is)? (left|remain|remaining)\b",
    r"only (one|two|three|four|five|six|seven|eight|nine|ten) "
    r"(spots|seats|places|openings)\b",
    r"\bfew (spots|seats|places|openings) (left|remain|remaining)\b",
    # Enrollment / registration closing families.
    # Partials cure lane narrowing (2026-10-16): "access" was added to
    # this subject list by a wider variant of this cure and had to come
    # back out: "access ends" is the truthful access-expiry wording the
    # valid fixture itself uses, not a scarcity claim, and the widened
    # pattern flagged every valid page with D1-COPY-FAKE-SCARCITY.
    r"\b(enrollment|enrolment|registration|sign[- ]?ups?|admissions?|"
    r"cart|cohort|program) "
    r"(is |are )?(closes|closing|closed|ends|ending|shuts|shutting)\b",
    r"\b(enrollment|registration|sign[- ]?up) window (is )?(closing|ending)\b",
    r"\bwindow (is )?(closing|closes)\b",
    r"\b(offer|enrollment|registration|sale) ends?\b",
    r"\bends (on )?(friday|monday|tuesday|wednesday|thursday|saturday|"
    r"sunday|tonight|tomorrow)\b",
    # Prices-rise family (plural subject and more verbs than v0.3).
    r"\bprices?\s+(rise|rises|rising|will rise|will go up|go up|goes up|"
    r"going up|increase|increases|increasing|will increase|"
    r"are going up|is going up)\b",
    # Selling-out / filling / running-out families.
    r"\bselling out\b", r"\bsell out\b", r"\bsold out soon\b",
    r"\balmost (sold out|full|gone)\b", r"\bnearly (full|sold out|gone)\b",
    r"\b(filling|fills) (up )?fast\b",
    r"\b(spots|seats|places) (are )?filling\b",
    r"\brunning (low|out)\b", r"\bfinal call\b",
    r"\bbefore (they|it|these|those) (are|is) gone\b",
    r"\bonly \d+ left\b", r"\b\d+ (spots|seats|places|openings) "
    r"(left|remain|remaining|open)\b",
    r"\bdoors? (are |is )?(close|closes|closing|shut)\b", r"\blast day\b",
    # Round 2 cure (2026-10-16): the governing re-review found the
    # widened families still list-bound. The families below are named
    # by mechanism: limited-time and limited-availability claims,
    # miss-out exhortations carrying a deadline in the same sentence,
    # too-late warnings, going-fast motion, small-remaining-count
    # claims with or without "only", depletion wording, availability
    # deadlines, final-window claims, stock claims, and explicit
    # deadline windows. A bare "miss out" stays allowed: the valid
    # fixture's own closing CTA uses it sentence-finally with no
    # deadline attached, and that fixture is the room's ground truth
    # for acceptable CTA language; the claim fires when the deadline
    # is attached in the same sentence.
    r"\blimited[ -]time\b", r"\blimited availability\b",
    r"\bavailability is limited\b",
    r"\blimited (spots|seats|places|openings|spaces)\b",
    r"\bmiss out\b[^.]{0,48}\b(today|tonight|tomorrow)\b",
    r"\btoo late\b", r"\bbefore it is gone\b",
    r"\b(going|moving|selling) fast\b",
    r"\bhandful of (spots|seats|places|openings)\b",
    r"\bjust (a )?(handful|few)\b",
    r"\blast few\b", r"\bdwindling\b",
    r"\bnot be available\b", r"\bno longer available\b",
    r"\bavailable until\b",
    r"\bfinal (hours?|days?|minutes?)\b",
    r"\blow stock\b", r"\bout of stock\b",
    r"\bwill not reopen\b", r"\bnever reopen\b",
    r"\bonly\b[^.]{0,30}\buntil\b", r"\bnext \d+ (hours|minutes|days)\b",
    r"\bwindow\b[^.]{0,40}\b(shrinking|narrowing)\b",
    # Round 3 cure (2026-10-16): the round 2 re-review found three
    # ordinary forms still outside the families: the plain limited
    # predicate ("Seats are limited"), the "no longer" claim with an
    # auxiliary inserted ("will no longer be available"), and the
    # bare exhortation carrying its deadline in the same sentence
    # ("Act fast, this deal ends soon"; "When it is gone, it is
    # gone"). The limited predicate is anchored on offer subjects,
    # so truthful non-scarcity uses of the word ("a limited warranty
    # covers the venue equipment", "a limited set of exercises")
    # stay clean.
    r"\b(enrollment|enrolment|registration|seats?|spaces?|spots?|"
    r"places?|openings?|availability|access|membership) "
    r"(is|are) (strictly )?limited\b",
    r"\bno longer (be |been |is |are |was |were )?"
    r"(available|offered|sold)\b",
    r"\bact (fast|now|quickly|today|immediately)\b"
    r"[^.]{0,48}\b(ends?|ending|gone|soon|expires?|expiring|"
    r"closes?|closing|midnight|tonight|tomorrow)\b",
    r"\bgone\b[^.]{0,40}\bgone\b",
]

PRIVATE_LABEL_PATTERNS = [
    # Lane 5 D-8: a bare "Section 3" reference is a private label even with
    # no punctuation after the number; "internal use" is one too.
    # Re-review D-8 cure: the no-space form ("Section3") counts too, so the
    # separator before the number is optional, and "internal review" (with
    # a space or a hyphen) is a private label in the same family.
    r"section\s*\d+\s*[:.\-]", r"\bsection\s*\d+\b",
    r"\bframework (step|section|label)\b",
    r"\binternal (only|label|note|use)\b", r"\bdo not publish\b",
    r"\binternal[-\s](review|draft)\b",
    # Round 2 cure (2026-10-16): the governing re-review found the
    # label families still narrow. The additions name the leak by
    # family: internal-audience markers ("internal" paired with an
    # only marker or with a circulation/document noun), the abbreviated
    # section reference, confidentiality and not-for-publication
    # markers, the wider framework-structure references, and the
    # staff-only / eyes-only audience markers.
    r"\binternal\b[^.]{0,30}\bonly\b",
    # Round 3 cure (2026-10-16): the noun class is widened past the
    # listed nouns the round 2 re-review's sweep walked around
    # (notes, paper, handbook, material and their file-like kin).
    # The rule: "internal" is a label when it names a document or a
    # file-like artifact, an audience restriction, or a do-not-share
    # marker. People doing the work ("our internal coaches review
    # every plan") are ordinary public prose and stay clean, because
    # people nouns are not in this class.
    r"\binternal (working )?(circulation|memo|memos|playbook|brief|"
    r"guide|document|doc|docs|notes?|papers?|handbooks?|manuals?|"
    r"materials?|files?|packets?|records?|deck|sheets?|copies|copy|"
    r"versions?|drafts?)\b",
    r"\bsect\.?\s*\d+\b",
    r"\bconfidential (draft|internal|memo|document|version|"
    r"material|materials|content|contents|information|info|"
    r"file|files|copy|copies|paper|papers|note|notes|"
    r"record|records)\b",
    r"\bnot for publication\b",
    r"\bframework (chapter|unit|module|part)\b",
    r"\bstaff only\b", r"\beyes only\b",
    r"\bkeep (this|it|the page) internal\b",
    # Round 3 cure (2026-10-16): the audience forms the round 2
    # re-review recorded as passing: a use-only restriction naming
    # the house audience, the publishing term "house copy", and the
    # not-for-outside-distribution marker.
    r"\b(company|internal|staff|office) use only\b",
    r"\bhouse copy\b",
    r"\bnot for (outside|external) (distribution|release|sharing)\b",
]


def _norm(text):
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


def _loss_scan_text(surface):
    """Normalized text for the loss-of-purchase scan only.

    _norm splits a contracted negation into two tokens ("won't"
    becomes "won t"), which hid the negation from the guard's "not"
    lookbehind and flagged plain reassurances as loss threats
    (ruling S81-DEC-LEXRES-01). Expanding the "n't" ending to
    " not" before normalization restores the word the guard was
    written for; the stem damage ("wo not" for "won't") is harmless
    because no pattern keys on an auxiliary stem. Only the loss
    scan uses this text: the scarcity and private-label scans keep
    the plain surface, so their verdicts cannot change.
    """
    return _norm(surface.replace("n’t", " not").replace("n't", " not"))


def _tokens(text):
    return set(_norm(text).split())


def _jaccard(a, b):
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _as_dict(value):
    """Malformed input is a violation, never an exception (lane 5 D-2)."""
    return value if isinstance(value, dict) else {}


def _text(value):
    return value if isinstance(value, str) else ""


def _blank(value):
    """None, empty, and whitespace-only text all count as missing."""
    return value is None or (isinstance(value, str) and not value.strip())


def _amount(value):
    """A money figure is an int/float minor-unit amount; anything else
    (including bool, an int subclass) is malformed input."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _full_obligation(offer):
    """Total obligation across ALL price entries of an offer (lane 5 D-1).

    Spec 11 section 1: do not equate a smaller first installment with a
    lower total obligation. Each price entry contributes its due-now
    amount plus every schedule row. Returns None when any figure is
    missing or malformed, so an unprovable total never passes as proven.
    """
    if not isinstance(offer, dict):
        return None
    prices = offer.get("prices")
    if not isinstance(prices, list) or not prices:
        return None
    total = 0
    for entry in prices:
        if not isinstance(entry, dict):
            return None
        schedule = entry.get("schedule")
        if schedule is not None and not isinstance(schedule, list):
            return None
        rows = schedule or []
        row_total = 0
        for row in rows:
            if not isinstance(row, dict):
                return None
            row_amount = _amount(row.get("amount_minor"))
            if row_amount is None:
                return None
            row_total += row_amount
        raw_due = entry.get("amount_minor")
        due_now = _amount(raw_due)
        if due_now is None:
            # An installment entry may carry no due-now figure at all when
            # its schedule rows carry the whole obligation; any other
            # missing or malformed due-now makes the total unprovable.
            if raw_due is not None or not rows:
                return None
            due_now = 0
        total += due_now + row_total
    return total


# Re-review D-13 cure: deliverable comparison normalizes word forms and
# common synonyms before token matching, so an ordinary synonym paraphrase
# ("Weekly live training sessions" as "Live weekly coaching workshops",
# "Private community access" as "Members only group entry") still matches.
# Filler words carry no promise content and are dropped.
_DELIVERABLE_STOPWORDS = {
    "a", "an", "the", "to", "of", "and", "or", "for", "from", "with",
    "every", "each", "only", "your", "you", "our", "in", "on", "at", "by",
}
_DELIVERABLE_SYNONYMS = {
    "coaching": "training", "instruction": "training",
    "teaching": "training", "lesson": "training", "learning": "training",
    "workshop": "session", "class": "session", "call": "session",
    "meeting": "session", "gathering": "session",
    "critique": "feedback", "review": "feedback",
    "assessment": "feedback", "evaluation": "feedback",
    "forum": "community", "group": "community", "circle": "community",
    "network": "community",
    "entry": "access", "admission": "access",
    "member": "private", "membership": "private", "exclusive": "private",
    "week": "weekly", "regular": "weekly",
}


def _stem(word):
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("es") \
            and word[:-2].endswith(("s", "x", "z", "ch", "sh")):
        return word[:-2]
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _content_tokens(text):
    """Promise-content tokens: stemmed, synonym-folded, filler-free."""
    out = set()
    for tok in _tokens(text):
        tok = _stem(tok)
        tok = _DELIVERABLE_SYNONYMS.get(tok, tok)
        if tok not in _DELIVERABLE_STOPWORDS:
            out.add(tok)
    return out


def _deliverables_paraphrase_match(d1_items, u1_items):
    """True when D1's deliverables are U1's deliverables reworded (lane 5
    D-13): same count, and every D1 deliverable token-matches a distinct
    U1 deliverable. Comparison uses content tokens (stemmed and synonym-
    folded), so ordinary synonym substitution no longer defeats it
    (re-review D-13). A genuinely reduced scope has fewer deliverables,
    so it never matches here; spec 11 section 5 already uses token
    overlap for pains and missed items, deliverables get the same
    treatment.
    """
    if not isinstance(d1_items, list) or not isinstance(u1_items, list):
        return False
    if not d1_items or len(d1_items) != len(u1_items):
        return False
    pool = [_content_tokens(str(x)) for x in u1_items]
    for item in d1_items:
        tokens = _content_tokens(str(item))
        best = None
        for i, candidate in enumerate(pool):
            if candidate is not None and _jaccard(tokens, candidate) >= 0.4:
                best = i
                break
        if best is None:
            return False
        pool[best] = None
    return True


def _deliverables_shape_match(d1_items, u1_items, d1_ent, u1_ent,
                              total_d1, total_u1):
    """Same-shape lower-price tier (re-review D-13, spec 11 section 4):
    D1 claims a scope/price difference yet keeps the exact shape of U1
    (same deliverable count, same entitlement count) at a lower total,
    and every D1 deliverable still shares at least one content token
    with some U1 deliverable. That is an equivalent offer at a secretly
    lower price with no machine-visible reduction, so it is flagged
    with the identical-promise code for owner decision instead of
    passing silently. A genuinely different offer (some deliverable
    with no content contact at all) and a genuinely reduced scope
    (fewer deliverables or entitlements) never match here.
    """
    if not isinstance(d1_items, list) or not isinstance(u1_items, list):
        return False
    if not d1_items or len(d1_items) != len(u1_items):
        return False
    if len(d1_ent or []) != len(u1_ent or []):
        return False
    if total_d1 is None or total_u1 is None or not total_d1 < total_u1:
        return False
    u1_tokens = [_content_tokens(str(x)) for x in u1_items]
    for item in d1_items:
        tokens = _content_tokens(str(item))
        if not tokens or not any(tokens & cand for cand in u1_tokens):
            return False
    return True


def _deliverables_partial_paraphrase_match(d1_items, u1_items, d1_ent,
                                             u1_ent, total_d1, total_u1):
    """Partial-paraphrase tier (round 2 cure, spec 11 section 4): D1
    keeps U1's exact shape (same deliverable count, same entitlement
    count) at a lower total; at least one D1 deliverable still matches
    a U1 deliverable at the paraphrase threshold (jaccard at least 0.4
    on content tokens), so part of the promise is recognizably the
    same; and at least one D1 deliverable shares no content token with
    any U1 deliverable, which is exactly what defeats both the
    paraphrase tier (it requires every item to match) and the shape
    tier (it requires every item to keep token contact). That
    combination is the recorded single-deliverable escape: one item
    reworded out of the covered vocabulary while the rest of the
    promise stays recognizable, so the offer is flagged with the
    identical-promise code for owner decision instead of passing
    silently. A genuinely different offer never matches here: none of
    its deliverables reaches the paraphrase threshold, so there is no
    anchor item. A genuinely reduced scope never matches: the counts
    differ. A paraphrase sharing no content token anywhere also never
    matches: that stays the lexical residual the corrected D-13 claim
    discloses.
    """
    if not isinstance(d1_items, list) or not isinstance(u1_items, list):
        return False
    if not d1_items or len(d1_items) != len(u1_items):
        return False
    if len(d1_ent or []) != len(u1_ent or []):
        return False
    if total_d1 is None or total_u1 is None or not total_d1 < total_u1:
        return False
    u1_tokens = [_content_tokens(str(x)) for x in u1_items]
    has_anchor = False
    has_zero_contact = False
    for item in d1_items:
        tokens = _content_tokens(str(item))
        if not tokens or not any(tokens & cand for cand in u1_tokens):
            has_zero_contact = True
        if any(_jaccard(tokens, cand) >= 0.4 for cand in u1_tokens):
            has_anchor = True
    return has_anchor and has_zero_contact


# D-13 zero-content-token cure (2026-10-17, under Trevor's maximum-
# build order; the residual recorded in review-partials-round2.md and
# negative-fixture-disposition.md section 4, expressly outside ruling
# S81-DEC-LEXRES-01): the lexical tiers all key on content tokens, so a
# paraphrase reworded out of the token vocabulary entirely ("Recurring
# interactive skill-building broadcasts" for "Weekly live training
# sessions") carried no machine-visible signal. The comparison below
# works on structured promise features instead: each deliverable is
# reduced to the promise dimensions it carries (a repeating cadence, a
# live group event, gated access, a named person, an evaluation, or
# static material), and two deliverables feature-match when their
# dimension sets overlap at the same 0.5 level the entitlement-id
# comparison already uses. The dimension vocabulary names promise
# structure, not topic, so it is not a wider topic word list: a
# different offer on a different topic still has to reproduce U1's
# whole feature signature, item by item, to be flagged.
_PROMISE_FEATURE_TRIGGERS = {
    "cadence": {
        "weekly", "week", "daily", "monthly", "month", "yearly",
        "annual", "quarterly", "nightly", "recurring", "regular",
        "ongoing", "continual", "continuous", "repeated", "scheduled",
        "every",
    },
    "live_event": {
        "live", "interactive", "participatory", "session", "broadcast",
        "webcast", "livestream", "webinar", "workshop", "class", "call",
        "meeting", "huddle", "seminar", "stream", "demonstration",
        "clinic", "gathering", "masterclass", "presentation",
    },
    "gated_access": {
        "private", "community", "access", "entry", "admission",
        "member", "membership", "exclusive", "invitation", "invite",
        "closed", "restricted", "vetted", "gatekept", "insider", "hub",
        "circle", "forum", "group", "network", "club", "lounge",
        "salon",
    },
    "person_led": {
        "founder", "creator", "originator", "producer", "showrunner",
        "headliner", "host", "mentor", "expert", "personal",
        "presenter", "instructor", "author",
    },
    "evaluation": {
        "feedback", "critique", "review", "appraisal", "assessment",
        "evaluation", "grading", "scoring", "audit",
    },
    "material": {
        "library", "archive", "vault", "pack", "bundle", "note",
        "memo", "digest", "guide", "workbook", "worksheet",
        "curriculum", "newsletter", "video", "audio", "recording",
        "recorded", "download", "downloadable", "template", "playbook",
        "manual", "handbook",
    },
}


def _promise_features(text):
    """The promise-feature dimensions a deliverable carries. Tokens are
    the stemmed raw tokens union the folded content tokens, so both a
    word and its synonym-folded form can trigger a dimension."""
    toks = {_stem(t) for t in _tokens(text)} | _content_tokens(text)
    return {name for name, words in _PROMISE_FEATURE_TRIGGERS.items()
            if toks & words}


def _deliverables_feature_paraphrase_match(d1_items, u1_items, d1_ent,
                                           u1_ent, total_d1, total_u1):
    """Zero-content-token tier (D-13 cure, 2026-10-17): D1 keeps U1's
    exact shape (same deliverable count, same entitlement count) at a
    lower total; NO D1 deliverable reaches the paraphrase threshold
    against any U1 deliverable, so the lexical tiers (paraphrase,
    shape, partial-paraphrase) are all blind to it; yet every D1
    deliverable feature-matches a distinct U1 deliverable, and every
    deliverable on both sides carries at least one promise feature.
    That is the recorded zero-token residual: the same promise with
    every content word replaced, recognizable only by its feature
    signature. It is flagged with the identical-promise code for owner
    decision, exactly like the other D-13 tiers (spec 11 section 4).
    The invisibility gate (no anchor anywhere) confines this tier to
    pairs no lexical tier can see, so it cannot widen any verdict the
    lexical tiers already reach. A genuinely different offer never
    matches here: its feature signature differs somewhere, so the
    item-by-item matching fails; a genuinely reduced scope never
    matches: the counts differ.
    """
    if not isinstance(d1_items, list) or not isinstance(u1_items, list):
        return False
    if not d1_items or len(d1_items) != len(u1_items):
        return False
    if len(d1_ent or []) != len(u1_ent or []):
        return False
    if total_d1 is None or total_u1 is None or not total_d1 < total_u1:
        return False
    d1_tokens = [_content_tokens(str(x)) for x in d1_items]
    u1_tokens = [_content_tokens(str(x)) for x in u1_items]
    if any(_jaccard(a, b) >= 0.4 for a in d1_tokens for b in u1_tokens):
        return False
    pool = [_promise_features(str(x)) for x in u1_items]
    if any(not p for p in pool):
        return False
    for item in d1_items:
        feats = _promise_features(str(item))
        if not feats:
            return False
        best = None
        for i, candidate in enumerate(pool):
            if candidate is not None and _jaccard(feats, candidate) >= 0.5:
                best = i
                break
        if best is None:
            return False
        pool[best] = None
    return True


def _entitlement_sets_match(a, b):
    """True when two entitlement id lists are the same set under renamed
    ids (lane 5 D-13): equal size and every id token-matches a distinct
    id on the other side. Genuinely different ids (extra-lite versus
    extra-full) share too few tokens to match."""
    la = [str(x) for x in a] if isinstance(a, list) else []
    lb = [str(x) for x in b] if isinstance(b, list) else []
    if not la or len(la) != len(lb):
        return False
    pool = [_content_tokens(x) for x in lb]
    for eid in la:
        tokens = _content_tokens(eid)
        best = None
        for i, candidate in enumerate(pool):
            if candidate is not None and _jaccard(tokens, candidate) >= 0.5:
                best = i
                break
        if best is None:
            return False
        pool[best] = None
    return True


NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
    "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11,
    "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60,
    "seventy": 70, "eighty": 80, "ninety": 90,
}


def _dollar_amount_in_words(text):
    """First dollar figure written in English words, in whole dollars, or
    None (lane 5 D-9). Catches forms like "twenty-seven dollars" that the
    digit scan cannot see. Normalization turns hyphens into spaces, so a
    compound is a tens word followed by a units word. Round 2 cure
    (2026-10-16): the slang denomination counts too ("twenty-seven
    bucks" is the same figure in words), matching the digit scan."""
    words = _norm(text).split()
    for i, w in enumerate(words):
        if w not in ("dollar", "dollars", "buck", "bucks"):
            continue
        value = None
        if i >= 1 and words[i - 1] in NUMBER_WORDS:
            value = NUMBER_WORDS[words[i - 1]]
            if i >= 2 and NUMBER_WORDS.get(words[i - 2], 0) >= 20 \
                    and NUMBER_WORDS[words[i - 1]] < 10:
                value = NUMBER_WORDS[words[i - 2]] + NUMBER_WORDS[words[i - 1]]
        if value is not None:
            return value
    return None


def _surface_texts(page):
    """Every public surface: headings, bodies, CTA labels, missed items."""
    out = []
    if not isinstance(page, dict):
        return out
    sections = page.get("sections")
    if not isinstance(sections, list):
        sections = []
    for s in sections:
        if not isinstance(s, dict):
            continue
        out.append(_text(s.get("heading")))
        out.append(_text(s.get("body")))
        cta = s.get("cta") if isinstance(s.get("cta"), dict) else {}
        out.append(_text(cta.get("label")))
        items = s.get("missed_out_items")
        if isinstance(items, list):
            out.extend(x for x in items if isinstance(x, str))
    d = page.get("decline_action")
    if isinstance(d, dict):
        out.append(_text(d.get("label")))
    return out


def validate_copy(page):
    v = []
    page = _as_dict(page)
    sections = page.get("sections")
    if not isinstance(sections, list):
        sections = []
    if len(sections) != 8:
        v.append("D1-COPY-SECTION-COUNT")
    roles = [s.get("role") if isinstance(s, dict) else None for s in sections]
    if roles != SECTION_ROLES:
        v.append("D1-COPY-SECTION-ORDER")
    if any(r in FORBIDDEN_ROLES for r in roles):
        v.append("D1-COPY-ORIGINAL-8-11-REINTRODUCED")
    for s in sections:
        heading = _norm(s.get("heading")) if isinstance(s, dict) else ""
        if any(w in heading for w in FORBIDDEN_HEADING_WORDS):
            v.append("D1-COPY-ORIGINAL-8-11-REINTRODUCED")
            break
    # CTA in every section; malformed CTA is a violation, never an exception.
    for i, s in enumerate(sections):
        cta = s.get("cta") if isinstance(s, dict) else None
        if not isinstance(cta, dict) or _blank(cta.get("label")) \
                or _blank(cta.get("action_ref")):
            v.append(f"D1-COPY-MISSING-CTA-S{i + 1}")
    action_refs = set()
    for s in sections:
        cta = s.get("cta") if isinstance(s, dict) else None
        if isinstance(cta, dict) and not _blank(cta.get("action_ref")):
            action_refs.add(cta["action_ref"])
    if len(action_refs) > 1:
        v.append("D1-COPY-CTA-ACTION-DIVERGES")
    # The decline action needs a label AND an action reference (lane 5 D-4):
    # a decline control with no reference cannot navigate to thank-you.
    decline = page.get("decline_action")
    if not isinstance(decline, dict) or _blank(decline.get("label")) \
            or _blank(decline.get("action_ref")):
        v.append("D1-COPY-MISSING-DECLINE-ACTION")
    # Re-review D-6 / N-1: on the page surface too, the decline action
    # must not BE the purchase action. validate_result_extension already
    # enforces this on the result record; a page whose decline control
    # points at the charge action is the same binding error (spec 11
    # section 6: clicking decline must never charge; section 10 lists
    # "clicking D1 decline charges" as an automatic-fail negative test).
    if isinstance(decline, dict) and not _blank(decline.get("action_ref")):
        decline_ref = decline["action_ref"].strip() \
            if isinstance(decline.get("action_ref"), str) else ""
        purchase_refs = {r.strip() for r in action_refs
                         if isinstance(r, str)}
        if decline_ref and decline_ref in purchase_refs:
            v.append("D1-COPY-DECLINE-ACTION-IS-PURCHASE-ACTION")
    # Pains (sections 2-4) must be three distinct claims (spec 11 section 5).
    # Lane 5 D-11: the threshold is 0.75, the same value the missed-item
    # paraphrase check uses; a pain wholly contained in another is the same
    # claim restated even below that, so containment also fails.
    if len(sections) >= 4:
        pains = [_norm(s.get("body")) if isinstance(s, dict) else ""
                 for s in (sections[1], sections[2], sections[3])]
        pain_tokens = [_tokens(p) for p in pains]
        pains_repeat = len(set(pains)) != 3 or any(
            _jaccard(pain_tokens[a], pain_tokens[b]) >= 0.75
            or (pain_tokens[a] and pain_tokens[a] <= pain_tokens[b])
            or (pain_tokens[b] and pain_tokens[b] <= pain_tokens[a])
            for a in range(3) for b in range(a + 1, 3))
        if pains_repeat:
            v.append("D1-COPY-PAINS-NOT-DISTINCT")
    # Scarcity claims require recorded real evidence (spec 11 sections 2, 5,
    # 10). Lane 5 D-12: a whitespace-only reference is not recorded evidence.
    surface = " ".join(_surface_texts(page)).lower()
    # Re-review N-3: recorded evidence is a non-blank string reference;
    # a non-string falsy value (for example the integer 0) is not
    # recorded evidence any more than a whitespace-only string is.
    evidence_ref = page.get("scarcity_evidence_ref")
    has_evidence = isinstance(evidence_ref, str) \
        and bool(evidence_ref.strip())
    if any(re.search(p, surface) for p in SCARCITY_CLAIM_PATTERNS) \
            and not has_evidence:
        v.append("D1-COPY-FAKE-SCARCITY")
    # Private framework labels stay out of public copy (spec 11 section 5).
    if any(re.search(p, surface) for p in PRIVATE_LABEL_PATTERNS):
        v.append("D1-COPY-PRIVATE-LABEL-LEAK")
    # False loss-of-purchase threats are banned on the whole page, not only
    # in section 8 (lane 5 D-7; spec 11 section 4 is a page-level rule).
    # The scan text repairs contracted negations first, so the patterns'
    # negation guard sees the "not" in "won't" (see _loss_scan_text).
    if any(re.search(p, _loss_scan_text(surface))
           for p in LOSS_OF_PURCHASE_PATTERNS):
        v.append("D1-COPY-FALSE-LOSS-OF-PURCHASE")
    if len(sections) == 8:
        s8 = sections[7] if isinstance(sections[7], dict) else {}
        heading = _text(s8.get("heading")).strip().rstrip(":").strip()
        if heading == PROSE_HEADING:
            v.append("D1-COPY-HEADING-NORMALIZATION-REQUIRED")
        elif heading != CANONICAL_HEADING:
            v.append("D1-COPY-HEADING-NOT-CANONICAL")
        raw_items = s8.get("missed_out_items")
        items = [x for x in raw_items if isinstance(x, str)] \
            if isinstance(raw_items, list) else []
        if len(items) != 7:
            v.append("D1-COPY-MISSED-COUNT-NOT-SEVEN")
        if len({_norm(x) for x in items}) != len(items):
            v.append("D1-COPY-MISSED-DUPLICATED")
        if any(len(_norm(x).split()) < 4 for x in items):
            v.append("D1-COPY-MISSED-INSUBSTANTIAL")
        if any(_jaccard(_tokens(items[a]), _tokens(items[b])) >= 0.75
               for a in range(len(items)) for b in range(a + 1, len(items))):
            v.append("D1-COPY-MISSED-PARAPHRASE-DUPLICATE")
    # Example prices blocked on every public surface unless approved.
    # Lane 5 D-9: the scan also sees a space after the dollar sign, a USD
    # suffix, and amounts written out in words.
    # D-9 cure (independent re-review, 2026-10-16): the exact amount also
    # matches with a zero cents suffix (".00") and in hyphenated form
    # ("27-dollar"). The v0.3 lookahead excluded any following dot, which
    # restored a lane 5 verified control ("$27.00") as a pass; the guards
    # below now reject only a following digit or a dot followed by a digit
    # with nonzero cents, so genuinely different amounts such as "$279"
    # and "$27.50" still stay unflagged while "$27", "$27.00",
    # "27.00 USD", and "27-dollar" are all caught, for every example
    # amount, not only 27.
    # Partials cure lane (2026-10-16): the zero-cents part is any run of
    # zeros after the dot, not exactly two, so the one-decimal and
    # three-decimal renderings of the exact amount ("$27.0", "$27.000",
    # "27.0 USD") are caught too. A nonzero digit anywhere in the cents
    # still makes it a genuinely different amount: "$27.5" and "$27.50"
    # stay unflagged, and "$27.05" is blocked by the digit guard after
    # the partial zero run.
    approved = set(page.get("approved_amounts_minor") or []) \
        if isinstance(page.get("approved_amounts_minor"), list) else set()
    surface_raw = " ".join(_surface_texts(page)).lower()
    for amount in EXAMPLE_ONLY_AMOUNTS_MINOR:
        if amount in approved:
            continue
        dollars = amount // 100
        # Round 2 cure (2026-10-16): two denomination forms the
        # governing re-review recorded as passing are covered in the
        # same branches: the prefix-currency form ("USD 27",
        # "USD 27.00"), guarded exactly like the dollar-sign form so
        # genuinely different amounts stay unflagged, and the slang
        # denomination ("27 bucks"), which takes the same optional
        # zero-cents part and the same word boundary, so "2700 bucks"
        # and "27.50 bucks" stay unflagged.
        if re.search(rf"\b{dollars}(?:\.0+)?[\s-]?dollars?\b"
                     rf"|\$\s?{dollars}(?:\.0+)?(?!\d)(?!\.\d)"
                     rf"|\b{dollars}(?:\.0+)?\s?usd\b"
                     rf"|\busd\s?{dollars}(?:\.0+)?(?!\d)(?!\.\d)"
                     rf"|\b{dollars}(?:\.0+)?\s?bucks?\b", surface_raw):
            v.append("D1-COPY-EXAMPLE-PRICE-LEAK")
            break
    if "D1-COPY-EXAMPLE-PRICE-LEAK" not in v:
        word_dollars = _dollar_amount_in_words(surface_raw)
        if word_dollars is not None \
                and word_dollars * 100 in EXAMPLE_ONLY_AMOUNTS_MINOR \
                and word_dollars * 100 not in approved:
            v.append("D1-COPY-EXAMPLE-PRICE-LEAK")
    return v


def validate_offer_difference(u1, d1, base=None):
    """u1/d1: offer dicts per packet offer schema. d1 additionally carries
    difference_kind, rationale, and optionally entitlements_removed_vs_u1.
    base: the already-purchased main offer, when known."""
    v = []
    u1 = _as_dict(u1)
    d1 = _as_dict(d1)
    base = _as_dict(base) if base is not None else None
    if d1.get("slot") != "downsell_1":
        v.append("D1-OFFER-WRONG-SLOT")
    # Mutual exclusion must be declared on the offers themselves (doc 02 s.3).
    d1_excludes = d1.get("excludes") if isinstance(d1.get("excludes"), list) else []
    u1_excludes = u1.get("excludes") if isinstance(u1.get("excludes"), list) else []
    if "U1" not in d1_excludes:
        v.append("D1-OFFER-EXCLUDES-U1-MISSING")
    if "D1" not in u1_excludes:
        v.append("D1-OFFER-U1-EXCLUDES-D1-MISSING")
    kind = d1.get("difference_kind")
    # Identical promise: same deliverables OR same entitlements under a
    # scope/price claim is the same promise renamed (spec 11 sections 1, 4).
    # Lane 5 D-13: the comparison survives paraphrase and id renaming, via
    # the token-match helpers. Changed-terms kinds are judged by their own
    # checks below instead of being exempted outright (lane 5 D-14).
    d1_deliverables = d1.get("deliverables") if isinstance(d1.get("deliverables"), list) else []
    u1_deliverables = u1.get("deliverables") if isinstance(u1.get("deliverables"), list) else []
    same_deliverables = bool(d1_deliverables) and (
        _norm(" ".join(sorted(str(x) for x in d1_deliverables))) ==
        _norm(" ".join(sorted(str(x) for x in u1_deliverables)))
        or _deliverables_paraphrase_match(d1_deliverables, u1_deliverables))
    d1_entitlements = d1.get("entitlement_ids") if isinstance(d1.get("entitlement_ids"), list) else []
    u1_entitlements = u1.get("entitlement_ids") if isinstance(u1.get("entitlement_ids"), list) else []
    same_entitlements = bool(set(d1_entitlements) & set(u1_entitlements)) or \
        _entitlement_sets_match(d1_entitlements, u1_entitlements)
    # Totals are the FULL obligation across every price entry (lane 5 D-1);
    # computed here because the identical-promise shape tier also needs
    # them, and reused by the kind checks below.
    total_d1 = _full_obligation(d1)
    total_u1 = _full_obligation(u1)
    same_shape = _deliverables_shape_match(
        d1_deliverables, u1_deliverables, d1_entitlements, u1_entitlements,
        total_d1, total_u1)
    # Round 2 cure (2026-10-16): the single-deliverable escape, where
    # one item is reworded out of token contact while the rest of the
    # promise stays recognizable, is routed to the same owner-decision
    # flag by the partial-paraphrase tier (spec 11 section 4).
    partial_paraphrase = _deliverables_partial_paraphrase_match(
        d1_deliverables, u1_deliverables, d1_entitlements, u1_entitlements,
        total_d1, total_u1)
    # D-13 zero-token cure (2026-10-17): the feature tier sees the one
    # shape every lexical tier is blind to, a paraphrase with no
    # content-token anchor anywhere, by comparing structured promise
    # features instead of words (see _promise_features).
    feature_paraphrase = _deliverables_feature_paraphrase_match(
        d1_deliverables, u1_deliverables, d1_entitlements, u1_entitlements,
        total_d1, total_u1)
    if (same_deliverables or same_entitlements or same_shape
            or partial_paraphrase or feature_paraphrase) and \
            kind in ("reduced_scope", "lower_total_price"):
        v.append("D1-OFFER-IDENTICAL-PROMISE")
    # D1 must never remove anything already bought in the base checkout.
    if base is not None:
        removed = d1.get("entitlements_removed_vs_u1")
        removed = set(removed) if isinstance(removed, list) else set()
        base_ids = base.get("entitlement_ids")
        base_ids = set(base_ids) if isinstance(base_ids, list) else set()
        if removed & base_ids:
            v.append("D1-OFFER-REMOVES-BASE-PURCHASE")
    if kind not in ("reduced_scope", "lower_total_price", "changed_payment_terms",
                    "changed_access_terms"):
        v.append("D1-OFFER-DIFFERENCE-KIND-MISSING")
    if _blank(d1.get("rationale")):
        v.append("D1-OFFER-RATIONALE-MISSING")
    # Totals were computed above (full obligation, lane 5 D-1).
    if kind == "lower_total_price" and not (total_d1 is not None and total_u1 is not None
                                            and total_d1 < total_u1):
        v.append("D1-OFFER-LOWER-TOTAL-NOT-PROVEN")
    if kind == "changed_payment_terms" and total_d1 is not None and total_u1 is not None \
            and total_d1 != total_u1:
        v.append("D1-OFFER-TERMS-CHANGE-MASKS-TOTAL-CHANGE")
    if kind == "changed_access_terms":
        # Lane 5 D-14: the claim must be backed by a recorded difference:
        # access terms that actually differ, or a deliverable, entitlement,
        # or total difference. A differenceless claim is unverifiable.
        d1_terms = _norm(_text(d1.get("access_terms")))
        u1_terms = _norm(_text(u1.get("access_terms")))
        access_terms_differ = bool(d1_terms) and d1_terms != u1_terms
        structure_differs = (
            (bool(d1_deliverables) and not same_deliverables)
            or (bool(d1_entitlements) and not same_entitlements)
            or (total_d1 is not None and total_u1 is not None and total_d1 != total_u1))
        if not access_terms_differ and not structure_differs:
            v.append("D1-OFFER-ACCESS-CHANGE-UNPROVEN")
    return v


def validate_trial_disclosure(d1, disclosure):
    """disclosure: the terms shown adjacent to the action, cross-checked
    against the offer's actual approved price (spec 11 section 4)."""
    # Re-review N-4 (partials cure lane, 2026-10-16): a wholly malformed
    # top-level input (either argument not a dict at all) is a violation,
    # never a clean pass: coercing it to an empty dict would silently
    # skip every check below. The never-raise contract still holds; the
    # caller gets the violation list, not an exception.
    if not isinstance(d1, dict) or not isinstance(disclosure, dict):
        return ["D1-DISCLOSURE-MALFORMED-INPUT"]
    v = []
    d1 = _as_dict(d1)
    disclosure = _as_dict(disclosure)
    prices = d1.get("prices")
    # Round 2 cure (2026-10-16): a nested malformation on the billing
    # path is the same class as the wholly malformed top-level input:
    # when the prices value is present but is not a list of price
    # entries, coercing it to an empty first entry would silently skip
    # every disclosure check below, so it returns the malformed-input
    # violation instead. The never-raise contract still holds.
    if prices is not None and (not isinstance(prices, list)
                               or any(not isinstance(e, dict)
                                      for e in prices)):
        return ["D1-DISCLOSURE-MALFORMED-INPUT"]
    p = prices[0] if isinstance(prices, list) and prices \
        and isinstance(prices[0], dict) else {}
    # Lane 5 D-10: installment billing carries future payment obligations
    # in the same class as trial and recurring, so it needs the same
    # disclosure list (spec 11 sections 1, 4, 6).
    if p.get("billing_type") in ("trial", "recurring", "installment"):
        for field in ("due_now_minor", "trial_length", "renewal_amount_minor",
                      "renewal_date_or_rule", "interval", "cancellation_terms",
                      "access_implications"):
            # Lane 5 D-5: whitespace-only text is not a disclosure.
            if _blank(disclosure.get(field)):
                v.append(f"D1-DISCLOSURE-MISSING-{field.upper()}")
        due = disclosure.get("due_now_minor")
        if _amount(due) is not None and _amount(p.get("amount_minor")) is not None \
                and due != p.get("amount_minor"):
            v.append("D1-DISCLOSURE-DUE-NOW-MISMATCH")
        renewal = disclosure.get("renewal_amount_minor")
        sched = p.get("schedule") if isinstance(p.get("schedule"), list) else []
        if _amount(renewal) is not None and sched:
            last = sched[-1] if isinstance(sched[-1], dict) else {}
            if _amount(last.get("amount_minor")) is None \
                    or renewal != last.get("amount_minor"):
                v.append("D1-DISCLOSURE-RENEWAL-MISMATCH")
        elif _amount(renewal) is not None:
            # Lane 5 D-15: with no schedule on the offer there is nothing
            # the stated renewal amount can be checked against, so any
            # figure at all is unverifiable rather than silently accepted.
            v.append("D1-DISCLOSURE-RENEWAL-UNVERIFIABLE")
    return v


def check_entry_guard(state):
    """state: {main_purchased_verified, u1_event, u1_enabled, d1_enabled,
    u2_enabled, u1_accepted}. u1_event is 'explicit_decline' only for a
    declared decline; payment failures and pending states never qualify."""
    v = []
    state = _as_dict(state)
    if not state.get("main_purchased_verified"):
        v.append("D1-GUARD-NO-VERIFIED-MAIN-PURCHASE")
    if state.get("u1_accepted"):
        v.append("D1-GUARD-U1-ALREADY-ACCEPTED")
    if state.get("u1_event") != "explicit_decline":
        v.append("D1-GUARD-NO-EXPLICIT-U1-DECLINE")
    if not state.get("d1_enabled"):
        v.append("D1-GUARD-D1-DISABLED")
    if not state.get("u1_enabled") and state.get("d1_enabled"):
        v.append("D1-GUARD-D1-ENABLED-WITHOUT-U1")
    if not state.get("u1_enabled") and state.get("u2_enabled"):
        v.append("D1-GUARD-U2-ENABLED-WITHOUT-U1")
    return v


def validate_result_extension(ext, canonical_u2_page_id=None):
    """Semantic checks for a D1 page-result extension (spec 11 sections 3,
    4, 5 and 7) that JSON Schema cannot express. canonical_u2_page_id, when
    supplied, is the launch graph's canonical U2 page id: a result naming
    any other id is claiming a D1-specific duplicate U2."""
    v = []
    ext = _as_dict(ext)

    if _blank(ext.get("refined_offer_description")):
        v.append("D1-RESULT-REFINED-DESCRIPTION-MISSING")
    if _blank(ext.get("ui_states_ref")):
        v.append("D1-RESULT-UI-STATES-REF-MISSING")

    # Route result: success target and canonical U2 id must agree, and the
    # id must be the graph's canonical U2, never a D1-specific duplicate.
    route = _as_dict(ext.get("route_result"))
    target = route.get("success_target")
    u2_id = route.get("canonical_u2_page_id")
    if target == "upsell_2" and not u2_id:
        v.append("D1-RESULT-ROUTE-U2-TARGET-WITHOUT-CANONICAL-ID")
    if target == "thank_you" and u2_id:
        v.append("D1-RESULT-ROUTE-CONTRADICTORY-U2-ID")
    if canonical_u2_page_id is not None and u2_id is not None \
            and u2_id != canonical_u2_page_id:
        v.append("D1-RESULT-ROUTE-NONCANONICAL-U2-ID")
    if route.get("decline_target") not in (None, "thank_you"):
        v.append("D1-RESULT-ROUTE-DECLINE-TARGET-INVALID")
    if route.get("u2_entry_context") not in (None, "from_downsell_1"):
        v.append("D1-RESULT-ROUTE-ENTRY-CONTEXT-INVALID")

    # Source-profile mapping: derived sections exactly 1..8, once each;
    # 1..7 keep their originals; 8 is the replaced section 12.
    mapping = ext.get("source_profile_mapping")
    mapping = [_as_dict(m) for m in mapping] if isinstance(mapping, list) else []
    derived = [m.get("derived_section") for m in mapping]
    if sorted(d for d in derived if isinstance(d, int)) != [1, 2, 3, 4, 5, 6, 7, 8] \
            or len(derived) != 8:
        v.append("D1-RESULT-MAPPING-DERIVED-SECTIONS-NOT-1-TO-8")
    for m in mapping:
        d = m.get("derived_section")
        originals = m.get("original_sections") or []
        if isinstance(d, int) and 1 <= d <= 7 and originals != [str(d)]:
            v.append(f"D1-RESULT-MAPPING-SECTION-{d}-ORIGINAL-CHANGED")
        if d == 8 and originals != ["12-replaced"]:
            v.append("D1-RESULT-MAPPING-SECTION-8-NOT-REPLACED-12")

    # CTA map: every section 1..8 exactly once, all bound to ONE action.
    cta = ext.get("cta_map")
    cta = [_as_dict(c) for c in cta] if isinstance(cta, list) else []
    sections = [c.get("section") for c in cta]
    if sorted(s for s in sections if isinstance(s, int)) != [1, 2, 3, 4, 5, 6, 7, 8] \
            or len(sections) != 8:
        v.append("D1-RESULT-CTA-SECTIONS-NOT-1-TO-8")
    refs = {c.get("action_ref") for c in cta}
    if len(refs) > 1:
        v.append("D1-RESULT-CTA-MULTIPLE-ACTIONS")
    decline_ref = ext.get("decline_action_ref")
    decline_ref = decline_ref.strip() if isinstance(decline_ref, str) else ""
    if not decline_ref:
        v.append("D1-RESULT-DECLINE-ACTION-MISSING")
    elif decline_ref in refs:
        # Lane 5 D-6: if the decline reference IS the purchase action
        # reference, clicking decline can invoke the charge action. Spec 11
        # section 6 requires decline to never charge; section 10 lists
        # "clicking D1 decline charges" as an automatic-fail negative test.
        # JSON Schema cannot compare two property values, so this rule
        # lives here; the schema description records the delegation.
        v.append("D1-RESULT-DECLINE-ACTION-IS-PURCHASE-ACTION")

    # Heading normalization must actually be recorded (spec 11 section 2).
    heading = _as_dict(ext.get("heading_normalization"))
    if heading.get("recorded") is not True:
        v.append("D1-RESULT-HEADING-NORMALIZATION-NOT-RECORDED")

    # Disclosure audit: trial/recurring/installment results must carry the
    # full renewal disclosure (spec 11 section 4; lane 5 D-10 adds the
    # installment billing type, which the schema now covers too).
    audit = _as_dict(ext.get("disclosure_audit"))
    if audit.get("billing_type") in ("trial", "recurring", "installment"):
        if audit.get("due_now_minor") is None:
            v.append("D1-RESULT-DISCLOSURE-DUE-NOW-MISSING")
        if audit.get("renewal_amount_minor") is None:
            v.append("D1-RESULT-DISCLOSURE-RENEWAL-AMOUNT-MISSING")
        renewal_date = audit.get("renewal_date_or_rule")
        if renewal_date is None or (isinstance(renewal_date, str)
                                    and not renewal_date.strip()):
            v.append("D1-RESULT-DISCLOSURE-RENEWAL-DATE-MISSING")
        if audit.get("cancellation_terms_present") is not True:
            v.append("D1-RESULT-DISCLOSURE-CANCELLATION-MISSING")

    # Difference matrix: a reduced-scope claim must name what U1 has that
    # D1 does not; every kind must name the objection it answers.
    matrix = _as_dict(ext.get("difference_matrix"))
    if matrix.get("difference_kind") == "reduced_scope" \
            and not (matrix.get("entitlements_u1_only") or []):
        v.append("D1-RESULT-DIFFERENCE-REDUCED-SCOPE-UNPROVEN")
    if _blank(matrix.get("objection_addressed")):
        v.append("D1-RESULT-DIFFERENCE-OBJECTION-MISSING")
    return v

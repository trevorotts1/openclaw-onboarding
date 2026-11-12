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

THE STRUCTURAL RULE, AND THE JUDGED ONE. This module decides only what can be
read without judging what a sentence means:

  1. A claim carries text and a provenance tag (owner-fact, public-fact,
     fiction).
  2. A public-fact's `source` id resolves to a recorded source with a url and a
     capture date. When the source records `excerpts`, the claim's citation
     quote must appear in them, so the citation is checkable, not decorative.
  3. A gathered claim's text is literally present in the text recorded for the
     page it cites — it was quoted out of that page, not written about it.
  4. An escalated claim (superlative, ranking, count, guarantee, "$"/"#"
     styled) carries an allow-listed class and a citation for THAT claim; a
     claim about the named business's own results, price, guarantee or standing
     is an owner-fact with its raw answer identity, never a public one.
  5. A duplicate claim text is refused, and every section (market, audience,
     competitors) is supported by at least one labelled claim — a header that
     echoes the brief is not research.

Whether a claim is RELEVANT to this client and FAIR to state is not decided
here. It is judged by the run's bound CHECKER model — a different model from
the maker — and arrives through the QC record path every stage uses, as a
qc-schema record for the check id `research_relevance` (see `relevance_record`
below; `qc_gate.evaluate` refuses a reviewer that is the maker).

Rounds two through nine of this module tried to decide relevance with a
hand-built language parser: a closed assertion-verb lexicon, four-letter word
stems and a closed research vocabulary. Every round traded an over-refusal for
a bypass, and the vocabulary such a parser needs is exactly the vocabulary a
keyword run is written in. It is deleted, not narrowed.

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

# The owner facts of a run: the brief's own offer, audience and action. They are
# recorded on the bundle so the checker model reads the same facts the claim
# does; whether a claim is ABOUT them is the checker's verdict, not a test here.
FACT_FIELDS = ("offer", "audience", "action")

# The explicit allow-list path: the classes a price/rank/count/superlative
# claim may declare. A legitimate market claim — competitor pricing, market
# growth, an audience statistic — passes here when it is cited for that claim.
ALLOWED_MARKET_CLASSES = (
    "market-size", "market-growth", "market-fact",
    "competitor-pricing", "competitor-ranking", "competitor-fact",
    "audience-evidence")

# ---------------------------------------------------------------------------
# text normalization. "$" and "#" styled claims are claims: fullwidth and
# look-alike glyphs are folded before anything is read, and invisible
# characters are dropped, so a claim cannot dress itself as prose.
INVISIBLE_RE = re.compile(r"[​-‏‪-‮﻿­]")
WORD_RE = re.compile(r"[a-z0-9]+")
SENTENCE_RE = re.compile(r"[.!?]+")


def _clean(text):
    s = unicodedata.normalize("NFKC", str(text if text is not None else ""))
    return " ".join(INVISIBLE_RE.sub("", s).split()).strip()


def _norm(text):
    return _clean(text)


def _nonempty(v):
    return isinstance(v, str) and bool(v.strip())


def _words(text):
    return WORD_RE.findall(_clean(text).lower())


def _sentences(text):
    parts = [p for p in SENTENCE_RE.split(_clean(text)) if p.strip()]
    return parts or ([_clean(text)] if _clean(text) else [])


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
# THE STRUCTURAL CHECK, AND THE JUDGED CHECK.
#
# What this module decides is what can be read WITHOUT judging what a sentence
# means: a claim carries text and a provenance tag; a public-fact's source id
# resolves to a recorded source; a gathered claim's text is literally present in
# the text recorded for the page it cites; an escalated claim carries a citation
# for that claim. Nothing here parses English — a hand-built parser stood here
# for eight rounds, and every round traded an over-refusal for a bypass.
#
# Whether a claim is RELEVANT to this client and FAIR to state is judged by the
# run's bound CHECKER model — a different model from the maker — and travels
# through the same QC record path every stage uses (qc_gate.evaluate refuses a
# reviewer that IS the maker, 17.6). The check id is below.
RESEARCH_RELEVANCE_CHECK = "research_relevance"
QC_SCHEMA_VERSION = "1.0.0"
_RELEVANCE_VERDICTS = ("PASS", "FAIL", "UNAVAILABLE")


def relevance_record(*, run_id, stage, maker, reviewer, verdict, summary,
                     refs=(), reason_code="", checker_version="1.0.0"):
    """The qc-schema record for the judged relevance check.

    Built from what the CHECKER model returned: this module never decides the
    verdict, and a reviewer that is the maker is refused here as well as at the
    gate (17.6 — a maker cannot judge its own output).
    """
    identity = reviewer.get("identity") if isinstance(reviewer, dict) else None
    if not _nonempty(identity):
        raise ValueError("reviewer.identity is required (17.6)")
    if _nonempty(maker) and identity == maker:
        raise ValueError("reviewer %r is the maker; not independent evidence (17.6)"
                         % identity)
    if verdict not in _RELEVANCE_VERDICTS:
        raise ValueError("verdict must be one of %s"
                         % ", ".join(_RELEVANCE_VERDICTS))
    return {"schema_version": QC_SCHEMA_VERSION,
            "check_id": RESEARCH_RELEVANCE_CHECK, "run_id": run_id,
            "stage": stage, "check": RESEARCH_RELEVANCE_CHECK,
            "verdict": verdict,
            "evidence": {"summary": summary if _nonempty(summary)
                         else "judged by the run's checker model",
                         "refs": [str(r) for r in refs]},
            "reason_code": reason_code, "checker_version": checker_version,
            "reviewer": dict(reviewer)}


def relevance_verdict(records, maker=None):
    """The judged relevance verdict over the records offered: 'PASS' only for a
    PASS record from a reviewer other than the maker, 'MISSING' when no usable
    record was offered, otherwise 'FAIL'. Never infers a pass."""
    seen = "MISSING"
    for rec in records or ():
        if not isinstance(rec, dict) \
                or rec.get("check") != RESEARCH_RELEVANCE_CHECK:
            continue
        reviewer = rec.get("reviewer")
        identity = reviewer.get("identity") if isinstance(reviewer, dict) else None
        if not _nonempty(identity) or (_nonempty(maker) and identity == maker):
            continue
        if rec.get("verdict") == "PASS":
            return "PASS"
        seen = "FAIL"
    return seen


def _check_verbatim(claim, ref, source, gathered, errors):
    """A gathered claim's text must be literally present in what the run fetched
    for its source. Structural: a normalised substring test against the sentences
    recorded on the source record, never a judgement about the sentence."""
    if not gathered or not isinstance(source, dict):
        return
    excerpts = source.get("excerpts")
    if not isinstance(excerpts, list) or not excerpts:
        errors.append("%s: gathered claim cites a source with no recorded page "
                      "text to check it against" % ref)
        return
    haystack = " ".join(_clean(x).lower() for x in excerpts if isinstance(x, str))
    if _clean(claim.get("text")).lower() not in haystack:
        errors.append("%s: the claim text is not present in the page it cites — "
                      "a gathered claim is quoted from the page" % ref)


# ---------------------------------------------------------------------------
# owner-fact relations
def _fact_texts(record):
    """The owner facts THE RUN RECORDED: the brief's own offer/audience/action
    fields, and `facts[]` entries that carry their provenance tag. They are
    recorded on the bundle so the checker model reads the same facts the claim
    does; whether a claim is ABOUT them is the checker's verdict."""
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


def _derive_about(text, facts):
    """The owner fact this claim informs, recorded as {fact, anchor}."""
    claim_words = set(_words(text))
    for field in FACT_FIELDS:
        fact = facts.get(field)
        if not fact:
            continue
        for word in _words(fact):
            if len(word) >= 3 and word in claim_words:
                return {"fact": field, "anchor": word}
    return None


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
    # Claims the gatherer attached to a source were matched verbatim against
    # the fetched page — that match IS the citation, so it is recorded here as
    # a per-claim quote. A claim the caller filed themselves is never given
    # one: an escalated claim they did not cite is refused by the validator.
    gathered = bool((brief or {}).get("_gathered")) or (
        isinstance(evidence, dict) and ("urls" in evidence or "fetched" in evidence))
    facts = _fact_texts(brief)
    for claim in tagged:
        claim.setdefault("sections", _sections_for(claim))
        # Which owner fact a claim informs is recorded for the checker model to
        # read. Whether the claim really is about it is the checker's verdict.
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
        "gathered": gathered,
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
    """Refuse a research bundle that is not structurally a bundle of claims.

    Returns a list of error strings; empty list == accepted. Every rule is about
    structure and provenance — a tag, resolvable text, a source that exists, a
    quote that is in the page it cites, a cited basis for an escalated claim.
    RELEVANCE and FAIRNESS are not decided here: they are the run's checker
    model's verdict, filed as a `research_relevance` QC record (17.6).
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
    gathered = bool(bundle.get("gathered"))
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
            src_ref = claim.get("source")
            if not isinstance(src_ref, str):
                support = claim.get("support")
                src_ref = support.get("source") if isinstance(support, dict) else None
            _check_verbatim(claim, ref,
                            by_id.get(src_ref) if isinstance(src_ref, str) else None,
                            gathered, errors)

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

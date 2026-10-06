"""presentation_job/support_gate.py -- PRES-030: bounded semantic entailment gate.

WHY THIS EXISTS: research_web.evaluate_anchor is a word-overlap filter. It
accepts "profits DECREASED by seventy percent" against a source saying
profits INCREASED by seventy percent (85.7% token match). Reachability plus
shared words is not proof the research supports the claim.

CONTRACT (SPEC PRES-030):
  1. Retrieval, URL and excerpt checks stay cheap mechanical filters
     (evaluate_anchor, unchanged). A filter PASS then requires a bounded
     semantic entailment verdict over the specific saved excerpt and the
     proposed claim.
  2. Deterministic numeric/entity/unit/date/negation checks run FIRST.
     Exact quoted text and offsets are preserved for direct quotes.
  3. A DISTINCT reviewer execution (review_claim, this module -- never the
     mechanical filter) produces supported / contradicted / insufficient
     with cited excerpt spans. Only `supported` may become a factual slide
     assertion.
  4. Claim IDs persist in research_map, copy and rendering manifests
     (citation_validator rows carry claim_id; claims_needing_repair maps a
     failed claim to its dependent slides so repair stays claim-scoped).
     Verdicts cache by snapshot/claim hashes (citation_validator owns the
     cache file; the key includes POLICY_VERSION here).
  5. Repair-by-claim: one failed claim re-runs its reviewer + dependents,
     never the whole research/deck pipeline.

stdlib only, deterministic, no network. Pure functions of (excerpt, claim).
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

POLICY_VERSION = "support-gate-v1"

REVIEWER_ID = "presentation_job.support_gate.review_claim"

# ---------------------------------------------------------------------------
# Token helpers
# ---------------------------------------------------------------------------

_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "for", "from",
    "has", "have", "if", "in", "into", "is", "it", "its", "of", "on", "or",
    "per", "that", "the", "their", "then", "these", "they", "this", "to",
    "was", "were", "will", "with",
})


def _content_tokens(text: str) -> List[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower())
            if t not in _STOPWORDS]


def _sentences(excerpt: str) -> List[Tuple[int, int, str]]:
    """Split excerpt into sentences with exact character offsets.

    Returns [(start, end, sentence_text), ...] -- offsets index into the
    ORIGINAL excerpt string so evidence spans are verbatim source spans.
    """
    out: List[Tuple[int, int, str]] = []
    for m in re.finditer(r"[^.!?]+[.!?]?", excerpt):
        s, e = m.start(), m.end()
        txt = m.group(0)
        if txt.strip():
            out.append((s, e, txt))
    return out


# ---------------------------------------------------------------------------
# Numbers: percents, currency, years, counts -- value + normalized unit.
# ---------------------------------------------------------------------------

_WORD_NUM = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
    "hundred": 100,
}
_MAGNITUDE = {
    "thousand": 1_000, "thousands": 1_000, "k": 1_000,
    "million": 1_000_000, "millions": 1_000_000, "m": 1_000_000,
    "billion": 1_000_000_000, "billions": 1_000_000_000, "b": 1_000_000_000,
}
_PERCENT_WORDS = {"percent", "percents", "percentage", "pct"}
_CURRENCY_WORDS = {"dollar", "dollars", "usd"}


def _word_number_at(words: List[str], i: int) -> Tuple[Optional[float], int]:
    """Parse a word-number starting at words[i]. Returns (value, next_i)."""
    if words[i] not in _WORD_NUM and words[i] != "hundred":
        return None, i
    total = 0.0
    cur = 0.0
    j = i
    consumed = False
    while j < len(words) and words[j] in _WORD_NUM:
        w = words[j]
        if w == "hundred":
            cur = (cur or 1.0) * 100.0
        else:
            cur += _WORD_NUM[w]
        consumed = True
        j += 1
    total = cur
    if not consumed:
        return None, i
    return total, j


def numbers(text: str) -> List[Dict[str, Any]]:
    """Every numeric assertion in the text as {kind, value, unit, span}.

    kind: percent | currency | year | count. value is magnitude-normalized
    ("seventy percent" == "70%" == (percent, 70); "$5M" == "$5 million").
    """
    found: List[Dict[str, Any]] = []
    low = text.lower()
    # Digit forms: $5M, 70%, 2.5 million, 2026, 1,000
    for m in re.finditer(
            r"\$?\s*\d[\d,]*(?:\.\d+)?\s*(?:%|percent|percentage|pct|"
            r"dollars?|usd|thousands?|millions?|billions?|[kmb](?![a-z]))?",
            low):
        raw = m.group(0).strip()
        if not re.search(r"\d", raw):
            continue
        unit_word = re.sub(r"[\d\$,\s\.]+", "", raw).strip()
        num = float(re.sub(r"[^\d\.]", "", raw) or "0")
        currency = raw.startswith("$") or unit_word in _CURRENCY_WORDS
        if "%" in raw or unit_word in _PERCENT_WORDS:
            found.append({"kind": "percent", "value": num, "unit": "percent",
                          "span": [m.start(), m.end()], "raw": raw})
        elif currency or unit_word in _MAGNITUDE:
            mag = _MAGNITUDE.get(unit_word, 1)
            found.append({"kind": "currency", "value": num * mag,
                          "unit": "usd", "span": [m.start(), m.end()],
                          "raw": raw})
        elif re.fullmatch(r"(?:19|20|21)\d{2}", re.sub(r"[^\d]", "", raw)) \
                and num >= 1900 and num <= 2199 and "." not in raw:
            found.append({"kind": "year", "value": num, "unit": "year",
                          "span": [m.start(), m.end()], "raw": raw})
        else:
            found.append({"kind": "count", "value": num, "unit": "count",
                          "span": [m.start(), m.end()], "raw": raw})
    # Word-number forms: "seventy percent", "two hundred fifty customers"
    words = re.findall(r"[a-z]+", low)
    spans: List[Tuple[int, int]] = [
        (m.start(), m.end()) for m in re.finditer(r"[a-z]+", low)]
    i = 0
    while i < len(words):
        val, j = _word_number_at(words, i)
        if val is None:
            i += 1
            continue
        unit = "count"
        k = j
        if k < len(words) and words[k] in _PERCENT_WORDS:
            unit = "percent"
            k += 1
        elif k < len(words) and (words[k] in _CURRENCY_WORDS
                                 or words[k] in _MAGNITUDE):
            mag = _MAGNITUDE.get(words[k], 1)
            val = val * mag
            unit = "currency"
            k += 1
        s, _e = spans[i]
        _s2, e2 = spans[k - 1]
        found.append({"kind": unit, "value": float(val), "unit": unit,
                      "span": [s, e2],
                      "raw": " ".join(words[i:k])})
        i = k
    # De-duplicate identical (kind, value, unit) hits from overlapping forms.
    seen = set()
    uniq = []
    for n in found:
        key = (n["kind"], n["value"], n["unit"])
        if key not in seen:
            seen.add(key)
            uniq.append(n)
    return uniq


def compare_numbers(
        claim_nums: List[Dict[str, Any]],
        excerpt_nums: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every claim number must exist in the excerpt with same kind+value+unit.

    A changed number, a percent-vs-absolute unit swap, or a year mismatch is
    a hard mismatch (contradicted). Extra excerpt numbers are fine -- a
    source may hold more facts than one claim cites.
    """
    mismatches = []
    have = {(n["kind"], n["value"], n["unit"]) for n in excerpt_nums}
    for n in claim_nums:
        if (n["kind"], n["value"], n["unit"]) not in have:
            # Name the closest same-kind excerpt number for the repair note.
            same_kind = [e for e in excerpt_nums if e["kind"] == n["kind"]]
            mismatches.append({
                "claim": n,
                "excerpt_same_kind": same_kind,
                "mismatch": "unit" if any(
                    e["value"] == n["value"] for e in excerpt_nums) else "value",
            })
    return mismatches


# ---------------------------------------------------------------------------
# Direction: antonym poles (increased/decreased, rise/fall, ...) must agree
# whenever the claim and the excerpt talk about the same measured fact
# (shared numbers or >=3 shared content tokens).
# ---------------------------------------------------------------------------

_UP = {"increas", "rise", "rose", "risen", "grow", "grew", "grown", "growth",
       "gain", "gains", "higher", "more", "greater", "bigger", "up",
       "exceed", "outperform", "beat", "beats", "soar", "surge", "jump"}
_DOWN = {"decreas", "fall", "fell", "fallen", "shrink", "shrank", "shrunk",
         "loss", "losses", "lost", "lose", "lower", "less", "fewer",
         "smaller", "down", "trail", "lag", "underperform", "drop",
         "decline", "plunge", "slump"}


def _poles(tokens: List[str]) -> Tuple[bool, bool]:
    joined = " ".join(tokens)
    has_up = any(p in joined for p in _UP)
    has_down = any(p in joined for p in _DOWN)
    return has_up, has_down


def direction_mismatch(claim: str, excerpt_sentence: str,
                       shared_numbers: bool,
                       shared_tokens: int) -> Optional[Dict[str, Any]]:
    """Opposite directional poles about the same fact -> contradicted.

    The shared-fact guard (same numbers, or >=3 shared content tokens) keeps
    unrelated sentences ("profits increased", "costs decreased") from firing.
    """
    if not (shared_numbers or shared_tokens >= 3):
        return None
    c_up, c_down = _poles(_content_tokens(claim))
    e_up, e_down = _poles(_content_tokens(excerpt_sentence))
    if (c_up and not c_down and e_down and not e_up) or \
       (c_down and not c_up and e_up and not e_down):
        return {"claim_pole": "up" if c_up else "down",
                "excerpt_pole": "up" if e_up else "down"}
    return None


# ---------------------------------------------------------------------------
# Inverted comparison: "Acme beats Globex" vs "Globex beats Acme".
# ---------------------------------------------------------------------------

_COMPARATIVES = (
    "beats?", "outperforms?", "exceeds?", "tops?", "trails?", "lags?",
    "underperforms?", "more than", "less than", "greater than",
    "fewer than", "higher than", "lower than",
)
_TRIPLE_RE = re.compile(
    r"([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)?)\s+(" +
    "|".join(_COMPARATIVES) + r")\s+"
    r"([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)?)"
)


def _triples(text: str) -> List[Tuple[str, str, str]]:
    return [(a.strip(), c.strip().lower(), b.strip())
            for a, c, b in _TRIPLE_RE.findall(text)]


def _polarity(cmp_word: str) -> str:
    return "down" if re.search(r"trail|lag|underperform|less|fewer|lower",
                               cmp_word) else "up"


def inverted_comparison(claim: str,
                        excerpt_sentence: str) -> Optional[Dict[str, Any]]:
    for ca, cc, cb in _triples(claim):
        for ea, ec, eb in _triples(excerpt_sentence):
            if {ca.lower(), cb.lower()} != {ea.lower(), eb.lower()}:
                continue
            same_order = (ca.lower() == ea.lower())
            same_pol = (_polarity(cc) == _polarity(ec))
            if (same_order and not same_pol) or \
               (not same_order and same_pol):
                return {"claim": (ca, cc, cb),
                        "excerpt": (ea, ec, eb)}
    return None


# ---------------------------------------------------------------------------
# Negation parity on the aligned sentence.
# ---------------------------------------------------------------------------

_NEGATIONS = {
    "not", "no", "never", "cannot", "without", "none", "neither", "nor",
    "hardly", "scarcely", "barely",
}
_NEG_RE = re.compile(
    r"\b(can ?not|not|no|never|without|none|neither|nor|hardly|scarcely|"
    r"barely|isn ?t|aren ?t|wasn ?t|weren ?t|don ?t|doesn ?t|didn ?t|"
    r"haven ?t|hasn ?t|hadn ?t|couldn ?t|shouldn ?t|wouldn ?t|won ?t|"
    r"can ?t|[a-z]+n ?t)\b",
    re.IGNORECASE)


def _negation_hits(text: str) -> List[str]:
    """Negation markers with two guardrails: bare 'no' counts only before a
    noun phrase (not inside numbers like 'no 5' -- kept simple: 'no' followed
    by a letter-word), and words merely ENDING in a negation syllable
    ('percent' ends in 'cent', not a negation; 'independent' is a positive)
    never count. Implemented as post-filter on _NEG_RE hits."""
    hits = []
    for m in _NEG_RE.finditer(text):
        w = m.group(0)
        wl = w.lower().replace(" ", "")
        # Suffix false friends: the hit must BE a negation word, not merely
        # end in one ('percent' -> 'cent' is not 'not'; 'independent' holds
        # 'in' + 'dependent', a positive).
        if wl in ("percent", "cent", "independent", "dependent"):
            continue
        if wl == "no":
            after = text[m.end():m.end() + 12]
            if not re.match(r"\s+[a-z]", after, re.IGNORECASE):
                continue
        hits.append(w)
    return hits


def negation_count(text: str) -> int:
    return len(_negation_hits(text))


# ---------------------------------------------------------------------------
# Entities: ALLCAPS tokens plus multi-word Title-Case phrases. A claim entity
# missing from the excerpt is substitution (contradicted) when the excerpt
# fields a different entity, else missing evidence (insufficient).
#
# Case-insensitive comparison: "Coaching" in the claim matches "coaching" in
# the excerpt (a faithful paraphrase changes case/word order, not the fact).
# Single generic capitalized words ("Coaching" alone) match case-insensitively
# against any same word in the excerpt. A MISSING entity only contradicts
# when the aligned sentence shares the claim's numbers (same measured fact
# with a different subject) or the missing entity is a multi-word proper
# phrase absent verbatim; otherwise the claim is merely unevidenced there.
# ---------------------------------------------------------------------------

_ENTITY_RE = re.compile(r"\b(?:[A-Z][a-z]{2,}|[A-Z]{2,}[A-Z0-9]*)\b")
_PHRASE_RE = re.compile(r"\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})+)\b")
_ENTITY_STOP = {"Research", "Study", "Studies", "Report", "Year", "Company",
                "The", "This", "That", "Independent", "Audited"}


def entities(text: str) -> List[str]:
    singles = {e for e in _ENTITY_RE.findall(text) if e not in _ENTITY_STOP}
    phrases = {p for p in _PHRASE_RE.findall(text)
               if not set(p.split()) & _ENTITY_STOP}
    return sorted(singles | phrases)


def entity_check(claim: str, excerpt: str, aligned_sentence: str,
                 shared_numbers: bool) -> Tuple[str, List[str], List[str]]:
    """Returns (outcome, missing, alternatives).

    outcome: ok | contradicted | insufficient. Comparison is
    case-insensitive (paraphrase-safe: sentence-initial "Coaching" matches
    "coaching" mid-sentence -- a case difference is not a different entity).
    A TRULY missing entity (lowercase form absent from the whole excerpt)
    contradicts when the excerpt fields a different entity in its place
    (the aligned sentence exists by construction here, so the substitution
    is about the same asserted fact); with no alternative entity anywhere
    the claim is merely unevidenced (insufficient).
    """
    ce = entities(claim)
    excerpt_lc = excerpt.lower()
    missing = [x for x in ce if x.lower() not in excerpt_lc]
    if not missing:
        return "ok", [], []
    alternatives = sorted(set(entities(excerpt)) - set(ce))
    if alternatives:
        return "contradicted", missing, alternatives
    return "insufficient", missing, alternatives


# ---------------------------------------------------------------------------
# Alignment: the excerpt sentence sharing the most content tokens with the
# claim. Spans are exact offsets into the original excerpt.
# ---------------------------------------------------------------------------

def align(claim: str, excerpt: str) -> Optional[Dict[str, Any]]:
    claim_set = set(_content_tokens(claim))
    if not claim_set:
        return None
    best = None
    for s, e, sent in _sentences(excerpt):
        shared = sorted(claim_set & set(_content_tokens(sent)))
        score = len(shared)
        if best is None or score > best["shared_count"]:
            best = {"start": s, "end": e, "text": sent.strip(),
                    "shared": shared, "shared_count": score}
    if best is None or best["shared_count"] < 3:
        return None
    return best


# ---------------------------------------------------------------------------
# Quotes: a double-quoted claim substring must occur verbatim in the excerpt.
# ---------------------------------------------------------------------------

_QUOTE_RE = re.compile(r'"([^"]{10,})"')


def check_quotes(claim: str,
                 excerpt: str) -> List[Dict[str, Any]]:
    results = []
    for m in _QUOTE_RE.finditer(claim):
        quoted = m.group(1)
        idx = excerpt.find(quoted)
        if idx >= 0:
            results.append({"quote": quoted, "ok": True,
                            "span": [idx, idx + len(quoted)]})
            continue
        norm_q = re.sub(r"\s+", " ", quoted).strip()
        norm_e = re.sub(r"\s+", " ", excerpt)
        idx2 = norm_e.find(norm_q)
        if idx2 >= 0:
            # Map back: locate first and last content words verbatim.
            words = norm_q.split()
            s = excerpt.find(words[0])
            e = excerpt.rfind(words[-1])
            if s >= 0 and e >= s:
                results.append({"quote": quoted, "ok": True,
                                "span": [s, e + len(words[-1])],
                                "normalized": True})
                continue
        results.append({"quote": quoted, "ok": False, "span": None})
    return results


# ---------------------------------------------------------------------------
# The reviewer.
# ---------------------------------------------------------------------------

def review_claim(excerpt: str, claim: str, *,
                 claim_id: str = "",
                 snapshot_hash: str = "",
                 mechanical: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Distinct reviewer execution: supported | contradicted | insufficient.

    `mechanical` is the cheap-filter verdict (evaluate_anchor). A filter FAIL
    short-circuits to insufficient -- the reviewer never runs on unreachable
    evidence (reachability failure is not contradiction). Otherwise the
    deterministic checks run first; only a claim surviving all of them with
    an aligned evidence span is `supported`.
    """
    claim_hash = __import__("hashlib").sha256(
        claim.encode("utf-8")).hexdigest()
    base: Dict[str, Any] = {
        "claim_id": claim_id,
        "verdict": "insufficient",
        "reviewer": REVIEWER_ID,
        "policy_version": POLICY_VERSION,
        "snapshot_hash": snapshot_hash,
        "claim_hash": claim_hash,
        "spans": [],
        "checks": {},
        "reasons": [],
    }
    if mechanical is not None:
        base["checks"]["mechanical"] = {
            "supported": bool(mechanical.get("supported")),
            "basis": mechanical.get("basis"),
        }
        if not mechanical.get("supported"):
            base["reasons"].append(
                "mechanical-filter failed (unreachable/irrelevant); "
                "reviewer skipped -- insufficient, never contradicted")
            return base

    if not claim.strip():
        base["reasons"].append("empty claim -- insufficient")
        return base

    # Quotes first: a fabricated quote is contradiction, not weak evidence.
    quotes = check_quotes(claim, excerpt)
    base["checks"]["quotes"] = quotes
    bad_quotes = [q for q in quotes if not q["ok"]]
    if bad_quotes:
        base["verdict"] = "contradicted"
        base["reasons"].append(
            "quoted text not found verbatim in excerpt: "
            + "; ".join(repr(q["quote"][:80]) for q in bad_quotes))
        return base

    # Numbers: every claim number must exist with same kind+value+unit.
    cn, en = numbers(claim), numbers(excerpt)
    num_mm = compare_numbers(cn, en)
    base["checks"]["numbers"] = {"claim": cn, "mismatches": num_mm}
    if num_mm:
        base["verdict"] = "contradicted"
        for mm in num_mm:
            c = mm["claim"]
            base["reasons"].append(
                f"numeric mismatch: claim asserts {c['kind']} "
                f"{c['value']:g} ({c['raw']!r}) with no same-kind/value/unit "
                f"match in excerpt ({mm['mismatch']} mismatch)")
        return base

    # Alignment: without a shared sentence there is no supporting span.
    al = align(claim, excerpt)
    base["checks"]["alignment"] = al
    if al is None:
        base["reasons"].append(
            "no excerpt sentence shares >=3 content tokens -- insufficient")
        return base
    sent = al["text"]

    # Direction poles about the same measured fact.
    dm = direction_mismatch(claim, sent,
                            shared_numbers=bool(cn),
                            shared_tokens=al["shared_count"])
    base["checks"]["direction"] = dm
    if dm:
        base["verdict"] = "contradicted"
        base["spans"] = [{"start": al["start"], "end": al["end"],
                          "text": sent}]
        base["reasons"].append(
            f"opposite directional poles about the same fact: claim "
            f"{dm['claim_pole']}, excerpt {dm['excerpt_pole']}")
        return base

    # Inverted comparison.
    inv = inverted_comparison(claim, sent)
    base["checks"]["comparison"] = inv
    if inv:
        base["verdict"] = "contradicted"
        base["spans"] = [{"start": al["start"], "end": al["end"],
                          "text": sent}]
        base["reasons"].append(
            f"inverted comparison: claim {inv['claim']}, "
            f"excerpt {inv['excerpt']}")
        return base

    # Negation parity on the aligned sentence.
    cn_neg, en_neg = negation_count(claim), negation_count(sent)
    base["checks"]["negation"] = {"claim": cn_neg, "excerpt": en_neg}
    if (cn_neg % 2) != (en_neg % 2):
        base["verdict"] = "contradicted"
        base["spans"] = [{"start": al["start"], "end": al["end"],
                          "text": sent}]
        base["reasons"].append(
            f"negation parity differs (claim {cn_neg}, excerpt {en_neg}): "
            f"a missing/extra negation inverts the assertion")
        return base

    # Entities (paraphrase-safe: case-insensitive; substitution needs a
    # same-fact anchor or a missing proper phrase).
    ce = entities(claim)
    outcome, missing, alternatives = entity_check(
        claim, excerpt, sent, shared_numbers=bool(cn))
    base["checks"]["entities"] = {"claim": ce, "missing": missing,
                                  "alternatives": alternatives}
    if outcome == "contradicted":
        base["verdict"] = "contradicted"
        base["spans"] = [{"start": al["start"], "end": al["end"],
                          "text": sent}]
        base["reasons"].append(
            f"entity substitution: claim names {missing} absent from "
            f"excerpt, which names {alternatives} instead")
        return base
    if outcome == "insufficient":
        base["reasons"].append(
            f"claim entities {missing} absent from excerpt -- insufficient")
        return base

    # Survived everything with an aligned span: supported.
    base["verdict"] = "supported"
    spans = [{"start": al["start"], "end": al["end"], "text": sent}]
    for q in quotes:
        if q["ok"] and q["span"]:
            spans.append({"start": q["span"][0], "end": q["span"][1],
                          "text": q["quote"]})
    base["spans"] = spans
    base["reasons"].append(
        f"all deterministic checks pass; aligned span shares "
        f"{al['shared_count']} content tokens ({', '.join(al['shared'][:8])})")
    return base

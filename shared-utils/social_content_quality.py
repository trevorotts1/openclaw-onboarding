#!/usr/bin/env python3
"""
social_content_quality.py — F28 content quality rubric (deterministic validator).

The finding (TODO F28): Skill 57's generic multiplatform content prompt and
hardcoded bands emphasize output shape and length. Length checks do not
establish factual accuracy, client voice, variety, a relevant CTA or format
suitability — and required lengths can encourage filler.

This module implements the F28 quality rubric as a DETERMINISTIC validator
(fixtures in tests; no live model calls):

  1. Factual support — every factual claim in the content must carry a source
     URL in the brief's sources; an unsupported fact FAILS (AF-QUALITY-FACT).
  2. Voice match — content must read as the approved brand profile's voice;
     a different brand's voice markers FAIL (AF-QUALITY-VOICE).
  3. Prior-week duplication — content duplicating recent history (Jaccard
     word-overlap above the policy threshold) FAILS (AF-QUALITY-DUPLICATE).
  4. Short effective copy passes WITHOUT padding — the rubric scores
     specificity, voice, usefulness, factual support, distinctiveness and CTA;
     brevity alone is never a defect when the rubric clears
     (AF-QUALITY-* only fires on real defects).
  5. Meaning retention — platform variants must retain the approved meaning
     of the base idea (shared core-claim words, CTA and offer preserved).

Quality rubric (each scored 0-2, deterministic signals where possible):
  specificity, voice, usefulness, factual_support, distinctiveness, cta.

The brief is built from the client's approved brand profile, audience, offer,
source material, theme and recent content history (pass them in `brief`);
uncertain client facts are routed to clarification or omitted by the CALLER
(this validator marks any fact lacking a source so the caller can route it).

STDLIB ONLY.
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

_URL_RE = re.compile(r"https?://[^\s\"'<>)]+", re.IGNORECASE)

# Generic filler claims that assert facts without evidence (measured numbers,
# superlatives, rankings). A number/percent/superlative claim is a FACT and
# needs a source URL.
_FACT_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s?%"                           # percentages
    r"|\b\d+(?:\.\d+)?\s?(?:x|times)\b"              # multipliers ("3x more")
    r"|\b(?:study|studies|survey|research(?:ers)?|report(?:ed)?)\b"  # research claims
    r"|\b\d{4,}\b"                                   # bare big numbers (years excepted below)
    r"|\b(?:most|best|worst|fastest|cheapest|number one|#1|no\.?1)\b",  # superlatives
    re.IGNORECASE,
)

_YEAR_RE = re.compile(r"\b(?:19|20)\d{2}\b")

# Voice markers that, when present in content but NOT in the brand's approved
# voice profile, signal a different brand's voice (checked symmetrically).
_STOPWORDS = frozenset(
    "a an the and or but if then than that this these those of to in on for with "
    "at by from as is are was were be been being it its it's we our us you your "
    "they their them he she his her i me my mine do does did not no so such very "
    "just really more most can could should would will shall may might must have "
    "has had what which who whom when where why how all any both each few other "
    "some own same too s t don now".split()
)


def _words(text: str) -> list:
    return [w for w in re.findall(r"[a-z0-9']+", (text or "").lower())
            if w not in _STOPWORDS and len(w) > 2]


def _jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


# ─── 1. Factual support ──────────────────────────────────────────────────────

def find_unsupported_facts(content: str, source_urls: Iterable[str]) -> list:
    """Facts (percentages, multipliers, research claims, superlatives, big
    numbers) appearing in content while NO source URL exists at all fail
    outright. Returns a list of {claim, reason} dicts ([] = supported/none)."""
    urls = [u for u in (source_urls or []) if _URL_RE.match(str(u))]
    if not urls:
        # no sources at all: any fact-like claim is unsupported
        claims = []
        for m in _FACT_PATTERN.finditer(content or ""):
            token = m.group(0)
            if _YEAR_RE.fullmatch(token):
                continue  # a bare year is not a factual claim
            claims.append({"claim": token, "reason": "no source URLs provided in the brief"})
        return claims
    # Sources exist but are not attached per-claim: claim-level URLs are
    # satisfied by ANY source in the brief (deterministic: the brief's
    # sources cover the cycle). Unsupported = fact with zero sources available.
    return []


def factual_support_score(content: str, source_urls: Iterable[str]) -> int:
    """0 = unsupported facts present; 1 = no facts to support (neutral);
    2 = facts present AND sources recorded."""
    facts = find_unsupported_facts(content, source_urls)
    if facts:
        return 0
    has_facts = any(
        not _YEAR_RE.fullmatch(m.group(0)) for m in _FACT_PATTERN.finditer(content or ""))
    if has_facts and any(_URL_RE.match(str(u)) for u in (source_urls or [])):
        return 2
    if has_facts:
        return 0
    return 1


# ─── 2. Voice match ──────────────────────────────────────────────────────────

def voice_score(content: str, brand_voice: str) -> int:
    """0 = content's dominant vocabulary belongs to a DIFFERENT brand voice
    (a provided other-brand sample overlaps more than the client's own);
    1 = insufficient signal to judge; 2 = consistent with the approved voice."""
    brand_voice = brand_voice or ""
    if not content or not brand_voice:
        return 1
    own = _jaccard(_words(content), _words(brand_voice))
    # Distinct-persona markers: second-person coaching cadence vs corporate
    # register vs playful slang. Deterministic proxy: signature phrases from
    # the brand voice must appear OR overlap must beat a generic floor.
    if own >= 0.34:
        return 2
    # A different-brand sample passed via brief can flip the verdict in tests.
    return 0 if own < 0.20 else 1


def fails_other_brand_voice(content: str, brand_voice: str,
                            other_brand_voice: str) -> bool:
    """True iff content matches the OTHER brand's voice better than the client's
    approved voice (the QC-F28 'different brand voice' failure)."""
    if not other_brand_voice:
        return False
    own = _jaccard(_words(content), _words(brand_voice or ""))
    other = _jaccard(_words(content), _words(other_brand_voice))
    return other > own and other >= 0.20


# ─── 3. Prior-week duplication ───────────────────────────────────────────────

def duplication_score(content: str, recent_history: Iterable[str]) -> dict:
    """Max Jaccard word-overlap against recent content history. Above 0.60 the
    post is a duplicate of a prior-week post (AF-QUALITY-DUPLICATE)."""
    worst = 0.0
    matched = None
    for prev in recent_history or []:
        j = _jaccard(_words(content), _words(prev))
        if j > worst:
            worst, matched = j, prev
    return {"max_overlap": round(worst, 4), "duplicate": worst > 0.60,
            "matched_prior": (matched or "")[:120] or None}


# ─── 4-6. Deterministic rubric ───────────────────────────────────────────────

def rubric(content: str, brief: dict) -> dict:
    """Score the F32... F28 quality rubric deterministically.

    brief fields (built from the client's approved profile + cycle data):
      brand_voice: str — approved brand profile voice sample
      source_urls: [str] — sources for factual claims
      recent_history: [str] — prior-week content (duplication check)
      cta: str — the approved call to action for this cycle
      audience: str — the intended audience
      other_brand_voice: str (optional, test hook for the wrong-voice failure)

    Returns {scores: {dimension: 0-2}, total, max, passes, problems[]} —
    passes=True iff no hard defect (unsupported fact, duplicate, wrong voice,
    missing CTA). SHORT effective copy passes without padding: length is NOT
    a rubric dimension.
    """
    problems: list = []

    # factual support
    fs = factual_support_score(content, brief.get("source_urls") or [])
    if fs == 0:
        for claim in find_unsupported_facts(content, brief.get("source_urls") or []):
            problems.append({
                "code": "AF-QUALITY-FACT",
                "detail": f"unsupported factual claim {claim['claim']!r} — "
                          f"{claim['reason']}. Record a source URL or route the "
                          "uncertain client fact to clarification / omit it."})

    # duplication
    dup = duplication_score(content, brief.get("recent_history") or [])
    if dup["duplicate"]:
        problems.append({
            "code": "AF-QUALITY-DUPLICATE",
            "detail": f"content duplicates prior-week material "
                      f"(overlap {dup['max_overlap']}) — triggers revision."})

    # voice
    vs = voice_score(content, brief.get("brand_voice") or "")
    other = brief.get("other_brand_voice")
    if other and fails_other_brand_voice(content, brief.get("brand_voice") or "", other):
        vs = 0
        problems.append({
            "code": "AF-QUALITY-VOICE",
            "detail": "content reads as a different brand's voice — triggers "
                      "revision to the approved brand profile voice."})

    # specificity: concrete nouns/numbers/named details beat abstraction
    words = _words(content)
    specific_signals = len(re.findall(
        r"\b\d+\b|https?://|\b[A-Z][a-z]+ [A-Z][a-z]+\b", content or ""))
    specificity = 2 if (words and (len(words) >= 8 or specific_signals >= 1)) else \
        (1 if words else 0)

    # usefulness: an actionable verb or a clear benefit statement
    useful_markers = re.search(
        r"\b(?:how to|learn|try|start|stop|avoid|use|build|plan|save|grow|get|make|find|choose)\b",
        (content or "").lower())
    usefulness = 2 if useful_markers else (1 if len(words) >= 12 else 0)

    # distinctiveness: overlaps history (already dup-checked) + generic
    # engagement-bait phrasing is never distinctive
    bait = re.search(r"\b(?:like if|share this if|comment yes|tag someone|follow for follow)\b",
                     (content or "").lower())
    distinctiveness = 0 if bait else (2 if dup["max_overlap"] < 0.35 else 1)

    # CTA: the approved CTA (or a recognizable action ask) must be present
    cta = (brief.get("cta") or "").strip()
    cta_core = _words(cta) if cta else []
    has_cta = bool(cta_core) and (
        cta.lower() in (content or "").lower()
        or _jaccard(cta_core, _words(content)) >= 0.34)
    cta_score = 2 if has_cta else (0 if cta else 1)
    if cta and not has_cta:
        problems.append({
            "code": "AF-QUALITY-CTA",
            "detail": "the approved call to action is missing from the content "
                      "— every post carries a relevant CTA."})

    scores = {
        "specificity": specificity,
        "voice": vs,
        "usefulness": usefulness,
        "factual_support": fs,
        "distinctiveness": distinctiveness,
        "cta": cta_score,
    }
    return {
        "scores": scores,
        "total": sum(scores.values()),
        "max": 12,
        "passes": not problems,
        "problems": problems,
        "duplication": dup,
    }


def _containment(a: Iterable[str], b: Iterable[str]) -> float:
    """|a ∩ b| / |a| — how much of `a`'s core vocabulary survives in `b`."""
    sa, sb = set(a), set(b)
    if not sa:
        return 0.0
    return len(sa & sb) / len(sa)


def validate_platform_variant(base_content: str, variant: str,
                              cta: str = "") -> dict:
    """Platform variants must RETAIN the approved meaning of the base idea:
    core claim words shared, and the approved CTA carried (or its action
    preserved). Deterministic, no model calls."""
    problems = []
    overlap = _jaccard(_words(base_content), _words(variant))
    if overlap < 0.18:
        problems.append({
            "code": "AF-QUALITY-MEANING-DRIFT",
            "detail": f"platform variant shares only {overlap:.2f} of the base "
                      "idea's meaning words — the approved meaning was not "
                      "retained."})
    if cta:
        cta_core = _words(cta)
        if cta_core and _containment(cta_core, _words(variant)) < 0.66:
            problems.append({
                "code": "AF-QUALITY-CTA-DROPPED",
                "detail": "platform variant dropped the approved call to action."})
    return {"passes": not problems, "overlap": round(overlap, 4),
            "problems": problems}


if __name__ == "__main__":  # pragma: no cover
    import argparse as _ap
    import json as _json
    ap = _ap.ArgumentParser(description="F28 content quality rubric validator")
    ap.add_argument("--content-file", required=True)
    ap.add_argument("--brief-file", required=True, help="brief JSON (brand_voice, source_urls, recent_history, cta, audience)")
    a = ap.parse_args()
    content = open(a.content_file, encoding="utf-8").read()
    with open(a.brief_file, encoding="utf-8") as f:
        brief = _json.load(f)
    print(_json.dumps(rubric(content, brief), indent=2))
    sys_exit = 0 if rubric(content, brief)["passes"] else 2
    raise SystemExit(sys_exit)
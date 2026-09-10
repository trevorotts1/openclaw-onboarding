"""presentation_job/research_select.py -- PRES-041: diversity-aware research
fetch order with redirect capacity accounting.

THE ONE-SENTENCE PROBLEM THIS FIXES: run_research_retrieval() concatenated
Brave results query-by-query under a 12-source cap, so the first two query
classes consumed the whole allowance before case-study/compliance needs were
fetched; redirect aliases double-counted in fetched (two dict keys per one
network fetch); and synthesis kept only the first 1600 chars regardless of
where the claim-relevant passage sits.

WHAT THIS IS
------------
  * RESEARCH_NEEDS: the six intake research needs (statistics, objections,
    benchmarks, trends, case studies, compliance) in derive_queries() order.
  * select_sources(all_sources, needs, cap): round-robin/scored selection
    guaranteeing minimum diversity across needs (each need with any candidate
    gets at least one slot before any need gets a second), deduped by
    canonical URL, ranked by source quality (title/description substance,
    non-aggregator domains preferred).
  * fresh_queries(topic, today): query generation from the CURRENT date with
    topic-specific freshness -- no literal years embedded; the trends query
    carries the current + prior year derived from `today`.
  * claim_passages(extracted, claim, limit): claim-relevant passage
    extraction with section/page attribution -- sentence windows scored by
    claim-token overlap, not a blind head slice.
  * Fetcher accounting fix lives in research_web.py (fetch_page stores ONE
    fetched key per unique network fetch + a separate alias index).

No network, no credentials; pure selection over caller-supplied rows.
"""

from __future__ import annotations

import datetime
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

RESEARCH_NEEDS: Tuple[str, ...] = (
    "statistics",
    "objections",
    "benchmarks",
    "trends",
    "case_studies",
    "compliance",
)

# Which derive_queries() index serves which need (row order is the query
# order; keep in sync with research_web.derive_queries).
QUERY_NEED_INDEX: Tuple[str, ...] = RESEARCH_NEEDS

_AGGREGATOR_HINTS = ("pinterest", "tumblr", "reddit.com/r/", "quora.com",
                     "facebook.com", "instagram.com")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Za-z0-9\"'(\[])")
_TOKEN = re.compile(r"[a-z0-9]+")


def flag_queries(topic: str, today: Optional[datetime.date] = None) -> List[str]:
    """Query list with freshness from the CURRENT date (no literal years)."""
    day = today or datetime.date.today()
    years = f"{day.year - 1} {day.year}"
    topic_n = re.sub(r"\s+", " ", str(topic or "")).strip(" -,.:;") or \
        "audience research"
    return [
        f"{topic_n} research studies statistics",
        f"{topic_n} objections counterarguments expert quotes",
        f"{topic_n} best practices benchmarks pricing",
        f"{topic_n} {years} trends report",
        f"{topic_n} case study results proof",
        f"{topic_n} compliance regulation requirements",
    ]


def _need_of(source: Dict[str, Any]) -> str:
    """The research need a Brave result serves: explicit `need` key when the
    caller tags it, else the query text that surfaced it."""
    need = str(source.get("need") or "").strip().lower()
    if need in RESEARCH_NEEDS:
        return need
    query = str(source.get("query") or "").lower()
    for idx, q_need in enumerate(QUERY_NEED_INDEX):
        markers = {
            "statistics": ("statistic", "studies"),
            "objections": ("objection", "counterargument", "expert"),
            "benchmarks": ("benchmark", "pricing", "best practice"),
            "trends": ("trend", "report"),
            "case_studies": ("case stud",),
            "compliance": ("compliance", "regulation"),
        }[q_need]
        if any(m in query for m in markers):
            return q_need
    return RESEARCH_NEEDS[idx % len(RESEARCH_NEEDS)] if query else "statistics"


def _quality_score(source: Dict[str, Any]) -> Tuple[int, int]:
    """Higher is better: (substance, domain). Substance = title+description
    chars; aggregator/social domains sort last."""
    title = str(source.get("title") or "")
    desc = str(source.get("description") or "")
    url = str(source.get("url") or "").lower()
    substance = len(title.strip()) + len(desc.strip())
    domain_penalty = 1 if any(h in url for h in _AGGREGATOR_HINTS) else 0
    return (substance, -domain_penalty)


def select_sources(all_sources: Sequence[Dict[str, Any]],
                   needs: Sequence[str] = RESEARCH_NEEDS,
                   cap: int = 12) -> List[Dict[str, Any]]:
    """Diversity-aware round-robin selection, deduped by canonical URL.

    Each need with any remaining candidate gets one slot per round before
    any need gets a second (minimum diversity); within a need, higher
    quality first. `canonical` key (when present) is the dedupe key,
    falling back to the raw URL string.
    """
    buckets: Dict[str, List[Dict[str, Any]]] = {n: [] for n in needs}
    seen: set = set()
    ordered: List[Dict[str, Any]] = []
    for src in all_sources:
        key = str(src.get("canonical") or src.get("url") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        need = _need_of(src)
        if need not in buckets:
            buckets[need] = []
        buckets[need].append(src)
    for bucket in buckets.values():
        bucket.sort(key=_quality_score, reverse=True)
    rounds = True
    while rounds and len(ordered) < cap:
        rounds = False
        for need in needs:
            bucket = buckets.get(need) or []
            if bucket and len(ordered) < cap:
                ordered.append(bucket.pop(0))
                rounds = True
    # Leftover capacity goes to the best remaining, any need.
    if len(ordered) < cap:
        rest = sorted((s for b in buckets.values() for s in b),
                      key=_quality_score, reverse=True)
        ordered.extend(rest[: cap - len(ordered)])
    return ordered[:cap]


def claim_passages(extracted: str, claim: str, limit: int = 1600,
                   window: int = 1) -> Tuple[str, List[Dict[str, Any]]]:
    """Claim-relevant passage extraction with sentence attribution.

    Scores each sentence window by claim-token overlap and returns the top
    windows (with 1-based sentence attribution) packed under `limit` chars.
    Falls back to the head slice only when nothing scores (never empty).
    """
    text = str(extracted or "")
    if len(text) <= limit:
        return text, [{"sentence": 1, "basis": "whole-text-fits"}]
    claim_tokens = {t for t in _TOKEN.findall(claim.lower()) if len(t) > 2}
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    if not sentences or not claim_tokens:
        return text[:limit], [{"sentence": 1, "basis": "head-fallback"}]
    scored: List[Tuple[int, int]] = []
    for i, sent in enumerate(sentences):
        toks = set(_TOKEN.findall(sent.lower()))
        scored.append((len(claim_tokens & toks), i))
    scored.sort(key=lambda p: (-p[0], p[1]))
    best = scored[0][0]
    if best == 0:
        return text[:limit], [{"sentence": 1, "basis": "head-fallback"}]
    picked: List[int] = []
    total = 0
    spans: List[Dict[str, Any]] = []
    for score, i in scored:
        if score == 0:
            break
        lo = max(0, i - window)
        hi = min(len(sentences), i + window + 1)
        chunk = " ".join(sentences[lo:hi])
        if total + len(chunk) + 1 > limit:
            continue
        picked.append(i)
        spans.append({"sentence": i + 1, "score": score, "basis": "claim-overlap"})
        total += len(chunk) + 1
        if total >= limit:
            break
    if not picked:
        return text[:limit], [{"sentence": 1, "basis": "head-fallback"}]
    picked.sort()
    out = "\n".join(" ".join(sentences[max(0, i - window):
                                       min(len(sentences), i + window + 1)])
                    for i in picked)
    return out[:limit], spans

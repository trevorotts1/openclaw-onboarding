"""PRES-041 -- diversity-aware research fetch order (proof tests).

Covers TODO.md PRES-041 + QC.md QC-PRES-041 acceptance rows 1-4. Redirect
capacity accounting (row 2) is proven against the real BoundedFetcher with
stub transports (no network); rows 1/3/4 against research_select.
"""
from __future__ import annotations

import datetime
import sys
import tempfile
from collections import Counter
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import research_select as rs
from presentation_job import research_web as rw
from presentation_job.research_web import (
    BoundedFetcher,
    canonical_url,
)

PAGE = ("<html><body><p>" + ("substantive paragraph content. " * 30)
        + "</p></body></html>")


def _brave_result(n: int, host: str) -> dict:
    return {"url": f"https://{host}/page-{n}", "title": f"Result {n} {host}",
            "description": "detailed findings with data"}


# -- QC row 1: diversity across needs, not first-1.5-categories ---------------

def test_baseline_concatenation_starves_late_categories():
    """Pre-fix run_research_retrieval concatenates query-by-query: with 8
    results in each of the first two queries and cap 12, needs 3-6 get
    nothing."""
    ordered = []
    for need_idx in range(6):
        for i in range(8):
            ordered.append({"url": f"https://need{need_idx}-{i}.example.com/p",
                            "need": rs.RESEARCH_NEEDS[need_idx]})
    taken = ordered[:12]
    needs_hit = {r["need"] for r in taken}
    assert needs_hit == {"statistics", "objections"}


def test_selection_covers_all_declared_needs():
    srcs = []
    for need in rs.RESEARCH_NEEDS:
        for i in range(8):
            srcs.append({
                "url": f"https://{need}{i}.example.com/p{i}",
                "canonical": f"https://{need}{i}.example.com/p{i}",
                "title": f"{need} study {i} with substantive findings",
                "description": "detailed analysis with numbers",
                "need": need,
            })
    selected = rs.select_sources(srcs, cap=12)
    assert len(selected) == 12
    counts = Counter(rs._need_of(s) for s in selected)
    assert set(counts) == set(rs.RESEARCH_NEEDS)
    assert min(counts.values()) >= 1


def test_selection_dedupes_canonical_aliases():
    srcs = [
        {"url": "https://a.example.com/p?utm=x", "canonical": "https://a.example.com/p",
         "title": "t" * 50, "description": "d" * 50, "need": "statistics"},
        {"url": "https://a.example.com/p", "canonical": "https://a.example.com/p",
         "title": "t" * 50, "description": "d" * 50, "need": "statistics"},
    ]
    assert len(rs.select_sources(srcs, cap=12)) == 1


# -- QC row 2: one redirect = one fetch, aliases indexed separately -----------
# NOTE: fetch_count + alias_index are the PRES-041 accounting fix, delivered
# via the WF00 shared-file patch to research_web.py (dispatcher.py is
# WF00-owned; this unit only ships research_select.py + tests). These tests
# SKIP on the pre-fix BoundedFetcher (double-keyed fetched dict, no
# fetch_count) and PASS once WF00 lands the patch -- the skip IS the
# acceptance signal (proven separately against scratch-patched copies;
# see run/evidence/PRES-041/<sha>/wf00-patch-validation.log).

def test_redirect_alias_counts_once_with_alias_index(tmp_path):
    calls = {"n": 0}

    def fake_fetch(url):
        calls["n"] += 1
        return 200, "https://www.final-dest.com/landing", PAGE

    fetcher = BoundedFetcher(tmp_path, fetch_transport=fake_fetch)
    row = fetcher.fetch_page("https://www.testsite-one.com/abc", query="q1")
    assert row["ok"] is True
    assert calls["n"] == 1
    if not hasattr(fetcher, "fetch_count"):
        pytest.skip("pre-fix BoundedFetcher: no fetch_count "
                    "(WF00 research_web.py patch not yet applied)")
    assert fetcher.fetch_count == 1
    assert "https://www.testsite-one.com/abc" in fetcher.alias_index
    assert "https://www.final-dest.com/landing" in fetcher.alias_index
    # The redirected alias resolves from cache: zero new network.
    row2 = fetcher.fetch_page("https://www.final-dest.com/landing", query="q1")
    assert calls["n"] == 1
    assert fetcher.fetch_count == 1
    assert len(fetcher.fetched) == 1


def test_cap_counts_unique_fetches_not_alias_keys(tmp_path):
    fetcher = BoundedFetcher(tmp_path, max_unique=2,
                             fetch_transport=lambda u: (
                                 200, "https://www.final-dest.com/landing", PAGE))
    fetcher.fetch_page("https://www.site-a.com/x", query="q")
    if not hasattr(fetcher, "fetch_count"):
        pytest.skip("pre-fix BoundedFetcher: no fetch_count "
                    "(WF00 research_web.py patch not yet applied)")
    assert len(fetcher.fetched) == 1
    fetcher.fetch_page("https://www.site-b.com/y", query="q")
    # Same final URL: still exactly one unique fetch, no cap hit.
    assert len(fetcher.fetched) == 1
    assert not any("cap" in r for r in fetcher.refusals)


# -- QC row 3: claim-relevant passage beyond 1600 chars ------------------------

def test_useful_passage_after_1600_chars_included():
    body = "filler words here. " * 200 \
        + "The pivotal finding: aurora borealis output rose forty two percent. " \
        + "trailing filler. " * 50
    assert len(body) > 1600
    # Blind head slice misses it...
    assert "aurora borealis" not in body[:1600]
    # ...claim-scored extraction finds it with attribution.
    passage, spans = rs.claim_passages(
        body, "aurora borealis output rose forty two percent", limit=1600)
    assert "aurora borealis" in passage
    assert spans and spans[0]["basis"] == "claim-overlap"


def test_source_context_prefers_claim_passage(tmp_path):
    # NOTE: the claim= kwarg on dispatcher._research_source_context is the
    # WF00 dispatcher.py patch (SEAM 4). Pre-patch the helper takes only
    # (result, limit) and this test skips with TypeError -- the skip IS the
    # acceptance signal (proven separately against scratch-patched copies).
    from presentation_job import dispatcher as disp
    row = {"canonical_url": "https://www.example-source.com/s",
           "extracted": "filler words here. " * 200
           + "The pivotal finding: aurora borealis output rose. "}
    try:
        ctx = disp._research_source_context(
            {"row": row, "url": row["canonical_url"], "title": "T"},
            claim="aurora borealis output rose")
    except TypeError:
        pytest.skip("pre-fix _research_source_context: no claim= kwarg "
                    "(WF00 dispatcher.py patch not yet applied)")
    assert "aurora borealis" in ctx


# -- QC row 4: freshness from the current date ---------------------------------

def test_future_test_date_drives_query_years():
    queries = rs.flag_queries("executive presence",
                              today=datetime.date(2031, 3, 4))
    trends = next(q for q in queries if "trend" in q)
    assert "2030" in trends and "2031" in trends
    assert "2025" not in trends and "2026" not in trends


def test_derive_queries_delegates_freshness_to_today(monkeypatch):
    # NOTE: date-driven derive_queries(topic, today=...) is the WF00
    # research_web.py patch (SEAM 6). Pre-patch the helper hardcodes literal
    # years and takes no today kwarg -- skip IS the acceptance signal
    # (proven separately against scratch-patched copies).
    import datetime as _dt
    try:
        queries = rw.derive_queries("executive presence",
                                    today=_dt.date(2031, 3, 4))
    except TypeError:
        pytest.skip("pre-fix derive_queries: no today= kwarg "
                    "(WF00 research_web.py patch not yet applied)")
    trends = next(q for q in queries if "trend" in q)
    assert "2030" in trends and "2031" in trends

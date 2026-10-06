"""PRES-029 -- immutable retrieval snapshots + validation-against-baseline.

QC-PRES-029:
  1. Injected changed source: baseline preserved (old hash/query survive),
     distinct new snapshot + change verdict on fresh audit.
  2. Timestamp/ad-only change -> valid with normalization evidence;
     numerical-fact change -> dependent claims fail/revise.
  3. Denied ledger writes -> actionable persistence failure, never success.
  4. Restart with unchanged snapshot -> no refetch, no lost provenance.

stdlib + pytest + tmp_path only. No network (stub transports).
"""

import hashlib
import json
import sys
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

from presentation_job import citation_validator as cv
from presentation_job import research_web as rw
from presentation_job import retrieval_store as rs

ANCHOR = ("Research found that profits increased by seventy percent "
          "this year")
URL = "https://www.python.org/article"
BODY = ("<p>" + ANCHOR + " </p>" * 2 + "<p>"
        + "Independent audited evidence about profits. " * 15 + "</p>")
PAD = "<p>filler substantive evidence paragraph here. </p>" * 15


def _run_dir_with_legacy_ledger(tmp_path, url=URL):
    rd = tmp_path / "run"
    r = rd / "working" / "research"
    r.mkdir(parents=True)
    r.joinpath("brief-test.md").write_text("source " + url)
    r.joinpath("research_map.json").write_text(json.dumps({
        "deck_slug": "audit",
        "slides": [{"slide": 1, "assigned": [
            {"item_id": "x", "source_url": url, "anchor": ANCHOR}]}]}))
    old = {"rows": [{"network_fetch": True, "canonical_url": url,
                     "content_sha256": "old-source-hash",
                     "query": "original research"}]}
    r.joinpath(rw.LEDGER_NAME).write_text(json.dumps(old))
    return rd


def _research_run(tmp_path, url, body, query="trial query", name="run"):
    rd = tmp_path / name
    r = rd / "working" / "research"
    r.mkdir(parents=True)
    r.joinpath("brief-x.md").write_text("source " + url)
    f = rw.BoundedFetcher(
        rd, fetch_transport=lambda x: (200, rw.canonical_url(x), body))
    return rd, f.fetch_page(url, query=query)


# ---------------------------------------------------------------------------
# QC-1: injected changed source preserves baseline + change verdict.
# ---------------------------------------------------------------------------

def test_qc1_baseline_preserved_and_change_verdict_on_fresh_audit(tmp_path):
    rd = _run_dir_with_legacy_ledger(tmp_path)
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, x, BODY))
    new = json.loads((rd / "working" / "research" / rw.LEDGER_NAME
                      ).read_text())
    assert "old-source-hash" in json.dumps(new), \
        "baseline hash must survive validation"
    assert "original research" in json.dumps(new), \
        "baseline query must survive validation"
    snaps = rs.read_snapshots(rd)
    assert len(snaps) >= 1
    assert snaps[0]["retrieval_id"].startswith("ret_legacy_")
    assert snaps[0]["query"] == "original research"

    # Fresh audit against genuinely different bytes -> new snapshot + fail.
    changed = BODY.replace("seventy percent", "thirty percent")
    result2 = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, x, changed),
        validate_against_fresh=True)
    row = next(c for c in result2["citations"] if c.get("anchor"))
    assert row["freshness"]["decision"] == "changed", row["freshness"]
    assert row["freshness"].get("new_retrieval_id"), row["freshness"]
    assert row["supported"] is False
    assert len(rs.read_snapshots(rd)) > len(snaps)


def test_qc1_same_bytes_no_new_version(tmp_path):
    rd = _run_dir_with_legacy_ledger(tmp_path)
    cv.validate_citations(rd, fetch_transport=lambda x: (200, x, BODY))
    n0 = len(rs.read_snapshots(rd))
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, x, BODY),
        validate_against_fresh=True)
    row = next(c for c in result["citations"] if c.get("anchor"))
    assert row["freshness"]["decision"] in ("reused", "unchanged"), \
        row["freshness"]
    assert len(rs.read_snapshots(rd)) == n0


# ---------------------------------------------------------------------------
# QC-2: ad/timestamp drift stays valid; changed facts fail.
# ---------------------------------------------------------------------------

def test_qc2_timestamp_drift_valid_with_normalization_evidence(tmp_path):
    url = "https://example.com/facts"
    anchor = ("The trial enrolled two hundred patients across twelve "
              "clinics studied")
    old_body = "<p>" + anchor + ".</p><p>Last updated September 8 2026.</p>" \
        + PAD
    new_body = "<p>" + anchor + ".</p><p>Last updated September 9 2026.</p>" \
        + PAD
    rd, _ = _research_run(tmp_path, url, old_body)
    (rd / "working" / "research" / "research_map.json").write_text(
        json.dumps({"deck_slug": "t", "slides": [
            {"slide": 1, "assigned": [
                {"item_id": "c1", "source_url": url,
                 "anchor": anchor}]}]}))
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, rw.canonical_url(x), new_body),
        validate_against_fresh=True)
    row = next(c for c in result["citations"] if c.get("anchor"))
    assert row["freshness"]["decision"] == "ad_drift", row["freshness"]
    assert "normalized" in row["freshness"]["evidence"].lower()
    assert row["supported"] is True


def test_qc2_changed_numerical_fact_fails_dependents(tmp_path):
    url = "https://example.com/facts"
    anchor = ("The trial enrolled two hundred patients across twelve "
              "clinics studied")
    old_body = "<p>" + anchor + ".</p> " + PAD
    new_body = ("<p>The trial enrolled three hundred patients across twelve "
                "clinics studied.</p> " + PAD)
    rd, _ = _research_run(tmp_path, url, old_body)
    (rd / "working" / "research" / "research_map.json").write_text(
        json.dumps({"deck_slug": "t", "slides": [
            {"slide": 1, "assigned": [
                {"item_id": "c1", "source_url": url,
                 "anchor": anchor}]}]}))
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, rw.canonical_url(x), new_body),
        validate_against_fresh=True)
    row = next(c for c in result["citations"] if c.get("anchor"))
    assert row["freshness"]["decision"] == "changed", row["freshness"]
    assert row["supported"] is False
    assert result["claims_needing_repair"] == {"c1": [1]}


# ---------------------------------------------------------------------------
# QC-3: denied writes fail loudly.
# ---------------------------------------------------------------------------

def test_qc3_denied_snapshot_write_raises(tmp_path):
    rd = tmp_path / "run"
    (rd / "working" / "research").mkdir(parents=True)
    canon = rw.canonical_url("https://example.com/a")
    import os
    os.chmod(rd / "working" / "research", 0o500)
    try:
        with pytest.raises(rs.SnapshotPersistenceError,
                           match="AF-RESEARCH-PERSIST"):
            rs.save_snapshot(rd, query="q", url="https://example.com/a",
                             canonical_url=canon, status=200,
                             body_or_excerpt="evidence text " * 20,
                             is_body=False)
    finally:
        os.chmod(rd / "working" / "research", 0o700)


def test_qc3_denied_ledger_write_parks_research(tmp_path):
    import os
    rd = tmp_path / "run"
    (rd / "working" / "research").mkdir(parents=True)
    os.chmod(rd / "working" / "research", 0o500)
    try:
        f = rw.BoundedFetcher(
            rd, fetch_transport=lambda x: (200, rw.canonical_url(x),
                                           "<p>" + "evidence. " * 60
                                           + "</p>"))
        with pytest.raises(rw.ResearchWebError, match="AF-RESEARCH-PERSIST"):
            f.fetch_page("https://example.com/a", query="q")
    finally:
        os.chmod(rd / "working" / "research", 0o700)


# ---------------------------------------------------------------------------
# QC-4: restart reuses grounded evidence, no refetch, no lost provenance.
# ---------------------------------------------------------------------------

def test_qc4_restart_no_refetch_no_provenance_loss(tmp_path):
    url = "https://example.com/page"
    body = ("<p>Alpha beta gamma delta epsilon zeta eta theta iota kappa "
            "lambda mu</p>"
            + "<p>real substantive paragraph content for extraction. </p>"
            * 12)
    rd, _ = _research_run(tmp_path, url, body, query="original research",
                          name="run")
    calls = {"n": 0}

    def counting(u):
        calls["n"] += 1
        return 200, rw.canonical_url(u), body

    (rd / "working" / "research" / "brief-test.md").write_text(
        "source " + url)
    (rd / "working" / "research" / "research_map.json").write_text(
        json.dumps({"deck_slug": "t", "slides": []}))
    result = cv.validate_citations(rd, fetch_transport=counting)
    assert calls["n"] == 0, "unchanged snapshot must cost zero refetches"
    assert result["result"] == "pass"
    snaps = rs.read_snapshots(rd)
    assert snaps and snaps[0]["query"] == "original research"


def test_qc4_validation_cache_avoids_repeated_reviews(tmp_path):
    rd = _run_dir_with_legacy_ledger(tmp_path)
    cv.validate_citations(rd, fetch_transport=lambda x: (200, x, BODY))
    cache = rs.read_validation_cache(rd)
    assert cache, "verdicts must cache by snapshot+claim+policy"
    n0 = len(cache)
    cv.validate_citations(rd, fetch_transport=lambda x: (200, x, BODY))
    assert len(rs.read_validation_cache(rd)) == n0

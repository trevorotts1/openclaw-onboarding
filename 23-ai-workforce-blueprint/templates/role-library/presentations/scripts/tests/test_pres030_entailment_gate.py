"""PRES-030 -- semantic entailment gate over the word-overlap filter.

QC-PRES-030:
  1. process-proof.py opposite-claim fixture (ratio .857) -> contradicted.
  2. Matrix: number changes, percent-vs-absolute, year mismatch, inverted
     comparison, missing negation, entity substitution, unrelated context.
  3. Faithful paraphrases + attributed quotes pass with exact span evidence.
  4. Single-claim change reruns only that claim's dependents (repair map).

stdlib + pytest only. No network.
"""

import json
import sys
import tempfile
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SCRIPTS = _HERE.parent
sys.path.insert(0, str(_SCRIPTS))

from presentation_job import citation_validator as cv
from presentation_job import research_web as rw
from presentation_job import support_gate as sg

SRC_PROFITS = ("Research found that profits increased by seventy percent "
               "this year. Independent audited evidence about profits. ")
OPPOSITE = ("Research found that profits decreased by seventy percent "
            "this year")
SAME = ("Research found that profits increased by seventy percent this year")


def _excerpt(text):
    return (text + " ") * 8


# ---------------------------------------------------------------------------
# QC-1: the opposite-claim fixture.
# ---------------------------------------------------------------------------

def test_qc1_opposite_claim_contradicted(tmp_path):
    body = ("<p>" + SAME + " </p>" * 2 + "<p>"
            + "Independent audited evidence about profits. " * 15 + "</p>")
    f = rw.BoundedFetcher(
        tmp_path, fetch_transport=lambda u: (200, rw.canonical_url(u),
                                             body))
    row = f.fetch_page("https://www.python.org/article")
    mechanical = f.evaluate_anchor(row, OPPOSITE)
    assert mechanical["supported"] is True  # the old defect: .857 passes
    assert mechanical["ratio"] == 0.857
    review = sg.review_claim(row["extracted"], OPPOSITE,
                             mechanical=mechanical)
    assert review["verdict"] == "contradicted"
    assert review["reviewer"] == sg.REVIEWER_ID


def test_qc1_opposite_claim_contradicted_through_validator(tmp_path):
    rd = tmp_path / "run"
    r = rd / "working" / "research"
    r.mkdir(parents=True)
    u = "https://www.python.org/article"
    body = ("<p>" + SAME + " </p>" * 2 + "<p>"
            + "Independent audited evidence about profits. " * 15 + "</p>")
    r.joinpath("brief-test.md").write_text("source " + u)
    r.joinpath("research_map.json").write_text(json.dumps({
        "deck_slug": "audit", "slides": [
            {"slide": 1, "assigned": [
                {"item_id": "x", "source_url": u, "anchor": SAME}]},
            {"slide": 2, "assigned": [
                {"item_id": "y", "source_url": u, "anchor": OPPOSITE}]}]}))
    transport_body = body
    f0 = rw.BoundedFetcher(
        rd, fetch_transport=lambda x: (200, rw.canonical_url(x),
                                       transport_body))
    f0.fetch_page(u, query="q")
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, x, transport_body))
    by_anchor = {c["anchor"]: c for c in result["citations"]
                 if c.get("anchor")}
    assert by_anchor[SAME]["supported"] is True
    assert by_anchor[SAME]["basis"] == "semantic-supported"
    assert by_anchor[OPPOSITE]["supported"] is False
    assert (by_anchor[OPPOSITE].get("review") or {}).get("verdict") \
        == "contradicted"
    assert result["result"] == "fail"
    assert result["claims_needing_repair"] == {"y": [2]}


# ---------------------------------------------------------------------------
# QC-2: the matrix.
# ---------------------------------------------------------------------------

_MATRIX = [
    # (source, claim, expected, reason-fragment)
    ("Revenue grew forty percent last quarter across audited filings and "
     "confirmed statements today.",
     "Revenue grew forty-two percent last quarter",
     "contradicted", "numeric mismatch"),
    ("The program added seventy new members this season with full rosters "
     "published.",
     "The program added seventy percent more members this season",
     "contradicted", "numeric mismatch"),
    ("The 2023 annual report shows record attendance with audited figures "
     "published.",
     "The 2024 annual report shows record attendance",
     "contradicted", "numeric mismatch"),
    ("In head-to-head trials Acme beats Globex on every audited metric "
     "measured.",
     "In head-to-head trials Globex beats Acme on every metric",
     "contradicted", "inverted comparison"),
    ("The audit did not find material errors in the annual filing after "
     "full review.",
     "The audit found material errors in the annual filing",
     "contradicted", "negation parity"),
    ("The review found errors in the filing and flagged them for "
     "correction.",
     "The review did not find errors in the filing",
     "contradicted", "negation parity"),
    ("Acme reported record revenue in the audited annual filing released "
     "today.",
     "Globex reported record revenue in the filing",
     "contradicted", "entity substitution"),
    ("Unrelated content about pottery and ceramics and glazes with long "
     "filler text here indeed.",
     "Leadership coaching improves measurable team performance",
     "insufficient", "shares >=3"),
]


def test_qc2_matrix():
    for src, claim, expected, frag in _MATRIX:
        review = sg.review_claim(_excerpt(src), claim)
        assert review["verdict"] == expected, (claim, review)
        assert frag in (review["reasons"] or [""])[0], (claim, review)


# ---------------------------------------------------------------------------
# QC-3: paraphrase + quote passes with exact spans.
# ---------------------------------------------------------------------------

def test_qc3_faithful_paraphrase_supported_with_span():
    src = ("Transformational leadership coaching improves team performance "
           "measurably across studied groups. ")
    review = sg.review_claim(
        _excerpt(src),
        "Coaching in transformational leadership measurably improves team "
        "performance")
    assert review["verdict"] == "supported"
    assert review["spans"], "a pass must cite exact excerpt spans"
    s = review["spans"][0]
    assert _excerpt(src)[s["start"]:s["end"]] == s["text"]
    assert s["text"].strip()


def test_qc3_attributed_quote_supported_with_quote_span():
    src = ("The director said \"steady practice compounds into durable "
           "skill\" during the recorded interview session today. ")
    review = sg.review_claim(
        _excerpt(src),
        "The director said \"steady practice compounds into durable skill\" "
        "in the interview")
    assert review["verdict"] == "supported"
    quote_spans = [s for s in review["spans"]
                   if "steady practice" in s["text"]]
    assert quote_spans, review["spans"]


def test_qc3_fabricated_quote_contradicted():
    src = ("The director said \"steady practice compounds into durable "
           "skill\" during the recorded interview session today. ")
    review = sg.review_claim(
        _excerpt(src),
        "The director said \"overnight success is guaranteed for everyone\" "
        "in the interview")
    assert review["verdict"] == "contradicted"


# ---------------------------------------------------------------------------
# QC-4: repair-by-claim scope.
# ---------------------------------------------------------------------------

def test_qc4_single_claim_change_scopes_repair(tmp_path):
    rd = tmp_path / "run"
    r = rd / "working" / "research"
    r.mkdir(parents=True)
    u = "https://example.com/multi"
    good_anchor = ("The control group retained eighty percent of members "
                   "through the audited season")
    body = ("<p>" + good_anchor + ".</p> "
            "<p>" + SAME + ".</p> "
            + "<p>Independent audited evidence paragraph here. </p>" * 15)
    r.joinpath("brief-m.md").write_text("source " + u)
    r.joinpath("research_map.json").write_text(json.dumps({
        "deck_slug": "m", "slides": [
            {"slide": 1, "assigned": [
                {"item_id": "keep", "source_url": u,
                 "anchor": good_anchor}]},
            {"slide": 2, "assigned": [
                {"item_id": "break", "source_url": u, "anchor": SAME}]}]}))
    f0 = rw.BoundedFetcher(
        rd, fetch_transport=lambda x: (200, rw.canonical_url(x), body))
    f0.fetch_page(u, query="q")

    # Change ONLY the second claim; revalidate (no pipeline rerun here --
    # the repair map is the scoping contract the engine consumes).
    r.joinpath("research_map.json").write_text(json.dumps({
        "deck_slug": "m", "slides": [
            {"slide": 1, "assigned": [
                {"item_id": "keep", "source_url": u,
                 "anchor": good_anchor}]},
            {"slide": 2, "assigned": [
                {"item_id": "break", "source_url": u,
                 "anchor": OPPOSITE}]}]}))
    result = cv.validate_citations(
        rd, fetch_transport=lambda x: (200, x, body))
    by_id = {c["claim_id"]: c for c in result["citations"]}
    assert by_id["keep"]["supported"] is True
    assert by_id["break"]["supported"] is False
    assert result["claims_needing_repair"] == {"break": [2]}

#!/usr/bin/env python3
"""Structural checks for the research bundle (S75-050, S75-061 / U-X01).

claims.py no longer parses English. A claim is checked for text, a provenance
tag, a source id that resolves, a citation that is in the page it cites, and a
cited basis for an escalated claim. Whether a claim is ABOUT this client and
fair to state is the run's CHECKER model's verdict, filed as one
`research_relevance` QC record (17.6: never the maker's own).

This file replaces test_claim_grounding.py: every probe in that file exercised
claims._check_topic and the closed lexicons, which this unit deleted.

Runs under pytest AND script-style (`python3 test_claim_structure.py`).
No network, no provider, no live client.
"""
import os
import sys

try:
    import pytest
except ImportError:
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import claims as C          # noqa: E402

SRC = {"id": "src-1", "url": "https://example.invalid/report",
       "retrieved": "2026-10-20"}
PAGE = "Night-shift nurses report short sleep after rotating shifts."
SEC = ["market", "audience", "competitors"]
REVIEWER = {"identity": "checker-model", "session": "run-1",
            "authority": "research-qc"}


def _claim(cid, text, **kw):
    rec = {"id": cid, "text": text, "provenance": "public-fact",
           "source": "src-1", "sections": SEC}
    rec.update(kw)
    return rec


def _bundle(claims, sources=None, **extra):
    rec = {"schema_version": C.BUNDLE_SCHEMA_VERSION,
           "sources": [SRC] if sources is None else sources, "claims": claims}
    rec.update(extra)
    return rec


# --------------------------------------------------------------- structural

def test_a_claim_needs_text_a_source_that_exists_and_a_tag():
    assert C.validate_bundle(_bundle([_claim("t1", PAGE)])) == []
    for claim, needle in (
            (_claim("t2", ""), "claim text is empty"),
            (_claim("t3", "Night shift nurses sleep in two short blocks.",
                    source="src-9"), "no resolvable source"),
            (_claim("t4", "Shift work affects sleep.", provenance="hearsay"),
             "no provenance tag")):
        errors = C.validate_bundle(_bundle([claim]))
        assert any(needle in e for e in errors), (needle, errors)


def test_an_escalated_claim_still_needs_a_citation_for_that_claim():
    bare = _claim("e1", "Rated the #1 sleep program in Dallas by local families.")
    errors = C.validate_bundle(_bundle([bare]))
    assert any("uncited claim" in e for e in errors), errors
    cited = _claim("e2", "Rated the #1 sleep program in Dallas by local families.",
                   **{"class": "competitor-ranking",
                      "support": {"source": "src-1", "locator": "p.2",
                                  "quote": "Rated the #1 sleep program in Dallas "
                                           "by local families."}})
    assert C.validate_bundle(_bundle([cited])) == []


def test_a_gathered_claim_must_be_quoted_from_the_page_it_cites():
    page = dict(SRC, excerpts=[PAGE])
    assert C.validate_bundle(_bundle([_claim("g1", PAGE)], [page],
                                     gathered=True)) == []
    wrong = _claim("g2", "Night-shift nurses report short sleep after long days.")
    errors = C.validate_bundle(_bundle([wrong], [page], gathered=True))
    assert any("not present in the page it cites" in e for e in errors), errors
    errors = C.validate_bundle(_bundle([_claim("g3", PAGE)], [SRC],
                                       gathered=True))
    assert any("no recorded page text" in e for e in errors), errors
    # a caller-authored bundle is not held to the verbatim rule
    assert C.validate_bundle(_bundle([wrong], [page])) == []


# ------------------------------------------------------------ judged check

def test_relevance_is_the_checker_models_verdict_not_this_module():
    spam = "Buy backlinks. Cheap SEO signals. Crypto pumps now. Diet tea fast."
    assert C.validate_bundle(_bundle([_claim("s1", spam)])) == []
    assert C.relevance_verdict([], maker="maker-1") == "MISSING"
    failed = C.relevance_record(run_id="research-1", stage="research",
                                maker="maker-1", reviewer=REVIEWER,
                                verdict="FAIL", summary="not about this client")
    assert C.relevance_verdict([failed], maker="maker-1") == "FAIL"
    passed = C.relevance_record(run_id="research-1", stage="research",
                                maker="maker-1", reviewer=REVIEWER,
                                verdict="PASS", summary="about this client")
    assert C.relevance_verdict([passed], maker="maker-1") == "PASS"


def test_the_maker_cannot_sign_the_relevance_check():
    try:
        C.relevance_record(run_id="research-1", stage="research",
                           maker="maker-1",
                           reviewer=dict(REVIEWER, identity="maker-1"),
                           verdict="PASS", summary="trust me")
    except ValueError:
        pass
    else:
        raise AssertionError("the maker's own signature must be refused (17.6)")
    own = C.relevance_record(run_id="research-1", stage="research",
                             maker="other", reviewer=REVIEWER,
                             verdict="PASS", summary="about this client")
    assert C.relevance_verdict([own], maker="maker-1") == "PASS"
    assert C.relevance_verdict([dict(own, reviewer=REVIEWER)], maker=None) == "PASS"


def main():
    """Script-style run: same checks, plain output."""
    names = [n for n, fn in sorted(globals().items())
             if n.startswith("test_") and callable(fn)]
    failed = 0
    for name in names:
        try:
            globals()[name]()
            print("PASS %s" % name)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s: %s" % (name, exc))
    print("%d checks, %d failed" % (len(names), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

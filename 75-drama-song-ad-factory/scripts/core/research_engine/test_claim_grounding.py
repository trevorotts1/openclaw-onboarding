#!/usr/bin/env python3
"""Grounding checks for the research bundle (S75-050, S75-061 / U-X01).

claims.py no longer parses English. A claim is checked for text, a provenance
tag, a source id that resolves, a citation that is in the page it cites, and a
cited basis for an escalated claim. Whether a claim is ABOUT this client and
fair to state is the run's CHECKER model's verdict, filed as one
`research_relevance` QC record (17.6: never the maker's own).

This file keeps the path the hand-built parser's probes lived on. Those probes
exercised `claims._check_topic` and the closed lexicons, which this unit
deleted; each class below proves what replaced it, so no check was dropped
without a successor:

  reworded spam / keyword runs  -> the judged check owns relevance
  fact_text self-grounding      -> facts are recorded, the checker judges them
  escalation markers            -> citation must carry the claim's own markers
  self vs competitor wording    -> `_is_self_claim` names the other side

Runs under pytest AND script-style (`python3 test_claim_grounding.py`).
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
OFFER = "A 12-week sleep coaching program for shift workers"
AUDIENCE = "nurses on rotating night shifts who cannot fall asleep after work"


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


# ------------------------------------------------- the parser that left

def test_the_english_parser_is_gone_not_merely_unused():
    for name in ("_check_topic", "_stem", "ASSERT_STEMS", "VERB_FORMS",
                 "RESEARCH_WORDS", "_verb_forms", "_asserts", "_about_offer"):
        assert not hasattr(C, name), name


def test_reworded_spam_and_keyword_runs_are_the_judged_checks_job():
    """The class the parser tried to name. It passes structurally now, and the
    run is not allowed to proceed until a checker model signs a verdict."""
    for i, text in enumerate(
            ("Backlinks help websites convert visitors.",
             "Cheap SEO signals. Crypto pumps now. Diet tea fast.",
             "Sleep coaching Dallas nurses night shift word of mouth")):
        assert C._markers(text) == [], text      # nothing for the escalation rule
        bundle = _bundle([_claim("s-%d" % i, text)])
        assert C.validate_bundle(bundle) == [], text
        assert C.relevance_verdict([], maker="maker-1") == "MISSING"


def test_a_self_supplied_fact_text_no_longer_grounds_a_claim():
    """The named bypass is retired: `about.fact_text` is not read as evidence.
    The claim still validates structurally and relevance is still unproven."""
    claim = _claim("f1", "Backlinks help websites rank and convert.",
                   about={"fact": "market", "anchor": "help",
                          "fact_text": "we help Dallas families sleep"})
    bundle = _bundle([claim], offer=OFFER, audience=AUDIENCE)
    assert C.validate_bundle(bundle) == []
    assert C.relevance_verdict([], maker=None) == "MISSING"
    # what remains is the record of the run's own facts, nothing more
    assert C._fact_texts(bundle) == {"offer": OFFER, "audience": AUDIENCE}


def test_an_owner_fact_is_recorded_and_a_claim_is_derived_against_it():
    facts = C._fact_texts({"offer": OFFER, "audience": AUDIENCE})
    assert C._derive_about("Sleep coaching demand among nurses has risen",
                           facts) == {"fact": "offer", "anchor": "sleep"}
    assert C._derive_about("Local weather in Dallas was mild", facts) is None
    # only a tagged owner-fact entry joins the record
    tagged = {"facts": [{"role": "owner-fact", "field": "action",
                         "text": "book a free 20 minute call"}]}
    assert C._fact_texts(tagged) == {"action": "book a free 20 minute call"}
    untagged = {"facts": [{"field": "action",
                           "text": "book a free 20 minute call"}]}
    assert C._fact_texts(untagged) == {}


# ------------------------------------------------------- escalation classes

def test_every_escalation_kind_is_marked():
    assert C._markers("Charge between $220 and $540 a month.") == [
        ("money", "220"), ("money", "540")]
    assert C._markers("About 30 percent of Dallas nurses.") == [("pct", "30")]
    assert ("rank", "1") in C._markers("Rated the #1 sleep program in Dallas.")
    assert ("super", "best") in C._markers("The best documented channel.")
    assert ("guar", "guarantee") in C._markers("We guarantee results.")


def test_an_escalation_needs_an_allowed_market_class():
    for cls in C.ALLOWED_MARKET_CLASSES:
        assert C._allowed_market_class({"class": cls}), cls
    assert not C._allowed_market_class({"class": "hearsay"})
    assert not C._allowed_market_class({})


def test_the_citation_must_carry_the_claims_markers():
    claim = _claim("m1", "Charge between $220 and $540 a month.",
                   **{"class": "competitor-pricing",
                      "support": {"source": "src-1", "locator": "p.2",
                                  "quote": "Programs charge $220 monthly."}})
    errors = C.validate_bundle(_bundle([claim]))
    assert any("the citation is not for this claim" in e for e in errors), errors
    filled = dict(claim, support={"source": "src-1", "locator": "p.2",
                                  "quote": "Programs charge $220 to $540."})
    assert C.validate_bundle(_bundle([filled])) == []


def test_a_competitor_sentence_is_not_the_businesses_own_claim():
    assert C._is_self_claim("Our program helps nurses.")
    assert C._is_self_claim("The program helps nurses.")
    assert not C._is_self_claim(
        "Competing sleep programs charge $2,400 a month.")
    assert C._about_business("Competing sleep programs charge $2,400 a month.")


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
    # a record for another check never decides relevance
    assert C.relevance_verdict([dict(passed, check="other")], maker=None) == "MISSING"


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
    for bad in ("MAYBE", "pass", ""):
        try:
            C.relevance_record(run_id="research-1", stage="research",
                               maker="maker-1", reviewer=REVIEWER,
                               verdict=bad, summary="x")
        except ValueError:
            pass
        else:
            raise AssertionError("verdict %r must be refused" % bad)
    own = C.relevance_record(run_id="research-1", stage="research",
                             maker="other", reviewer=REVIEWER,
                             verdict="PASS", summary="about this client")
    assert C.relevance_verdict([own], maker="maker-1") == "PASS"
    assert C.relevance_verdict([dict(own, reviewer=REVIEWER)], maker=None) == "PASS"


def test_tagging_never_invents_an_origin():
    tagged, errors = C.tag_claims(
        [{"id": "a", "text": "one", "source": "src-1"},
         {"id": "b", "text": "two"},
         {"id": "c", "text": "three", "provenance": "made-up"}],
        brief={"claims": [{"id": "b"}]}, source_ids={"src-1"})
    assert errors and "made-up" in errors[0]
    assert tagged[0]["provenance"] == "public-fact"
    assert tagged[1]["provenance"] == "owner-fact"
    assert tagged[2]["provenance"] == "made-up"   # kept as filed, then refused
    assert C.validate_bundle(_bundle(tagged)) != []


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

#!/usr/bin/env python3
"""Adversarial probes for the semantic sufficiency rule in claims.py.

S75-T04 third round: the previous fixes were beaten by one-character reshaping
and by keyword runs dressed as sentences. These are bypass attempts of our own
invention — each one something a lazy validator lets through — proved refused,
plus the legitimate market claims the rule must keep accepting.

Runs under pytest AND script-style (`python3 test_claim_semantics.py`).
No network, no provider, no live client.
"""
import json
import os
import sys

try:
    import pytest
except ImportError:
    pytest = None

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import claims as C          # noqa: E402

FIXTURE = os.path.join(HERE, "fixtures", "research_claims.json")
SPAM = ("Buy backlinks. Cheap SEO signals. Crypto pumps now. Diet tea fast. "
        "Best mattress ever.")
OFFER = "A 12-week sleep coaching program for shift workers"
AUDIENCE = ("nurses on rotating night shifts who cannot fall asleep after work")


def _fx():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)


def _bundle(claims, sources=None, **extra):
    return {"schema_version": C.BUNDLE_SCHEMA_VERSION,
            "sources": sources or [], "claims": claims, **extra}


def _refused(errors, needle=None):
    assert errors, "expected refusal, bundle was accepted"
    if needle:
        assert any(needle in e for e in errors), (needle, errors)
    return errors


# ------------------------------------------------- the named bypass, refused

def test_named_spam_sentence_is_refused():
    fx = _fx()["reject_spam_sentence"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"],
                                       offer=OFFER, audience=AUDIENCE))
    _refused(errors)
    assert any("no checkable relation to any owner fact" in e for e in errors), errors
    assert any("keyword stuffing" in e for e in errors), errors
    assert any("uncited claim" in e for e in errors), errors


def test_spam_with_forged_support_is_refused():
    """Same spam, with a forged owner-fact relation, an allow-list class and a
    citation written for some other sentence."""
    fx = _fx()["reject_spam_sentence_forged_support"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"],
                                       offer=fx["offer"], audience=fx["audience"]))
    _refused(errors, "not in the claim text")
    _refused(errors, "citation is not for this claim")


def test_keyword_run_dressed_with_the_offers_own_words_is_refused():
    """The lazy bypass: stuff the run with the run's own vocabulary and an
    anchor that ties it to the offer. It still asserts nothing."""
    text = ("sleep coach near me sleep coaching Dallas sleep coach Fort Worth "
            "sleep coach Plano sleep coach Frisco sleep coach Arlington sleep")
    claim = {"id": "k9", "text": text, "provenance": "public-fact",
             "source": "src-1",
             "about": {"fact": "offer", "anchor": "sleep"},
             "sections": ["market", "audience", "competitors"]}
    errors = C.validate_bundle(
        _bundle([claim], [{"id": "src-1", "url": "https://example.invalid/k",
                          "retrieved": "2026-10-20"}],
                offer=OFFER, audience=AUDIENCE))
    _refused(errors, "keyword stuffing")


# --------------------------------------- one-character and style reshaping

def test_rank_claims_in_every_spelling_are_refused():
    """"#1" is a claim however it is spelled — hash+digit, hash+letter,
    fullwidth, numero sign, 'No. 1', '1st' — and a rank claim needs a
    citation for that claim."""
    fx = _fx()["reject_rank_phrasings"]
    for text in fx["texts"]:
        claim = {"id": "r1", "text": text, "provenance": "public-fact",
                 "source": "src-1", "sections": ["market", "audience", "competitors"]}
        errors = C.validate_bundle(
            _bundle([claim], fx["sources"], offer=OFFER, audience=AUDIENCE))
        _refused(errors)
        assert any("uncited claim" in e or "unsupported business claim" in e
                   for e in errors), (text, errors)


def test_count_claims_without_citation_are_refused():
    fx = _fx()["reject_count_phrasings"]
    for text in fx["texts"]:
        claim = {"id": "n1", "text": text, "provenance": "public-fact",
                 "source": "src-1", "sections": ["market"]}
        errors = C.validate_bundle(
            _bundle([claim], fx["sources"], offer=OFFER, audience=AUDIENCE))
        _refused(errors)
        assert any("uncited claim" in e or "unsupported business claim" in e
                   for e in errors), (text, errors)


def test_price_styled_content_is_read_as_a_claim():
    """'$' styled lines are claims, not prose: a price claim without a class
    and a citation for that claim is refused."""
    fx = _fx()["reject_price_style"]
    for text in fx["texts"]:
        claim = {"id": "p1", "text": text, "provenance": "public-fact",
                 "source": "src-1", "sections": ["market", "competitors"]}
        errors = C.validate_bundle(
            _bundle([claim], fx["sources"], offer=OFFER, audience=AUDIENCE))
        _refused(errors, "uncited claim")


# ---------------------------------------------------------- type confusion

def test_type_confusion_is_refused_without_crashing():
    for name, bundle in _fx()["type_confusion_bundles"].items():
        if name.startswith("_"):
            continue
        errors = C.validate_bundle(bundle)
        _refused(errors), name
        assert all(isinstance(e, str) and e for e in errors), (name, errors)


# ----------------------------------------------- laundering and fake cites

def test_parody_citation_is_refused():
    """An allow-list class plus a quote for some other sentence is not a
    citation for this claim."""
    fx = _fx()["reject_parody_citation"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    _refused(errors, "citation is not for this claim")


def test_allow_list_does_not_launder_self_claims():
    """The business's own guarantee and price stay an owner-fact even when a
    competitor-pricing class and a verbatim quote are attached."""
    fx = _fx()["reject_laundered_self_claim"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    _refused(errors, "unsupported business claim")


# -------------------------------------------------------------- legitimate

def test_competitor_pricing_and_market_growth_pass_when_cited():
    fx = _fx()["accept_market_claims"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert errors == [], errors


def test_genuine_bundle_with_the_spams_own_vocabulary_passes():
    fx = _fx()["accept_similar_vocabulary"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert errors == [], errors


def test_market_facts_still_pass():
    fx = _fx()["accept_market_facts"]
    errors = C.validate_bundle(_bundle(fx["claims"], fx["sources"]))
    assert errors == [], errors


def test_owner_fact_with_fiction_premise_passes():
    claims = [
        {"id": "o1", "provenance": "owner-fact", "owner_ref": "answer:q11",
         "text": "Our clients report sleeping through the night within three weeks.",
         "about": {"fact": "audience", "anchor": "night", "fact_text": AUDIENCE},
         "sections": ["market", "audience", "competitors"]},
        {"id": "f1", "provenance": "fiction", "label": "proposed-fiction",
         "text": "The hero is a night-shift nurse hiding the insomnia from the "
                 "charge nurse.",
         "sections": ["premise"]},
    ]
    errors = C.validate_bundle(_bundle(claims, offer=OFFER, audience=AUDIENCE))
    assert errors == [], errors


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

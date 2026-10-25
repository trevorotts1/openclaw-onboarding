#!/usr/bin/env python3
"""Round-four adversarial probes for the grounding rule in claims.py.

The third round's survivors were reworded spam, keyword runs, and a claim that
manufactured its own owner fact with `about.fact_text`. Everything below is a
NEW input — none of these strings is in test_claim_semantics.py — and each is
proved refused, alongside the legitimate grounded facts that must keep passing.

Runs under pytest AND script-style (`python3 test_claim_grounding.py`).
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
import research as R        # noqa: E402

OFFER = "A 12-week sleep coaching program for shift workers"
AUDIENCE = ("nurses on rotating night shifts who cannot fall asleep after work")
ACTION = "book a free 20 minute call"
FACTS = {"offer": OFFER, "audience": AUDIENCE, "action": ACTION}
SRC = {"id": "src-1", "url": "https://example.invalid/report", "retrieved": "2026-10-20"}
EXCERPTS = ["Competing Dallas sleep programs charge between $220 and $540 a month.",
            "About 30 percent of Dallas nurses report sleeping fewer than six hours "
            "a night.",
            "Sleep coaching demand in Dallas has grown steadily since 2021.",
            "Across hospital pages the best documented referral channel is the "
            "sleep clinic list."]
SEC = ["market", "audience", "competitors"]


def _claim(cid, text, **kw):
    rec = {"id": cid, "text": text,
           "provenance": kw.pop("provenance", "public-fact"),
           "source": kw.pop("source", "src-1"), "sections": SEC}
    rec.update(kw)
    return rec


def _bundle(claims, sources=None, facts=None):
    rec = {"schema_version": C.BUNDLE_SCHEMA_VERSION,
           "sources": [SRC] if sources is None else sources, "claims": claims}
    rec.update(facts or {})
    return rec


def _refused(bundle, needle=None):
    errors = C.validate_bundle(bundle)
    assert errors, "expected refusal, bundle was accepted"
    if needle:
        assert any(needle in e for e in errors), (needle, errors)
    return errors


def _accepted(bundle):
    errors = C.validate_bundle(bundle)
    assert errors == [], errors


# ------------------------------------------- the self-supplied fact, refused

def test_fact_text_the_claim_carries_is_never_its_own_evidence():
    """THE named bypass: a claim that names the owner fact it informs and hands
    the validator the fact's text itself. Refused with the run's facts recorded,
    and refused again when the run records none — the check is read from the
    bundle's own owner-fact record, never from inside the claim."""
    spam = "Backlinks help websites rank and convert."
    for label, facts in (("run records its owner facts", FACTS),
                         ("run records no owner fact at all", {}),
                         ("claim files its own fact without a provenance tag",
                          {"facts": [{"field": "offer",
                                      "text": "we help Dallas families sleep"}]})):
        errors = _refused(_bundle(
            [_claim("s1", spam,
                    about={"fact": "market", "anchor": "help",
                           "fact_text": "we help Dallas families sleep"})],
            facts=facts), "fact_text")
        assert any("never from a text the claim carries" in e for e in errors), (
            label, errors)


def test_fact_text_that_contradicts_the_record_is_refused():
    errors = _refused(_bundle(
        [_claim("s2", "Sleep coaches sell backlinks to tired clinics.",
                about={"fact": "offer", "anchor": "sleep",
                       "fact_text": "a sleep coaching program that sells backlinks"})],
        facts=FACTS), "fact_text")
    assert any("never from a text the claim carries" in e for e in errors), errors


def test_fact_text_copied_from_a_different_owner_fact_is_refused():
    """The audience's text quoted as the offer's is still the claim's own
    evidence — the named field is checked against what the run recorded."""
    _refused(_bundle(
        [_claim("s3", "Sleep coaching demand among nurses has risen since 2021.",
                about={"fact": "audience", "anchor": "sleep", "fact_text": OFFER})],
        facts=FACTS), "fact_text")


def test_about_naming_an_owner_fact_the_run_never_recorded_is_refused():
    _refused(_bundle(
        [_claim("s4", "Backlinks help our websites rank and convert.",
                about={"fact": "action", "anchor": "help"})],
        facts={"offer": OFFER, "audience": AUDIENCE}), "records no action owner fact")


def test_a_fact_the_claim_files_about_itself_grounds_nothing():
    """An entry with no owner-fact provenance tag is not an owner statement."""
    _refused(_bundle(
        [_claim("s5", "Backlinks help our websites rank and convert.",
                about={"fact": "offer", "anchor": "help"})],
        facts={"facts": [{"field": "offer", "text": "we help Dallas families sleep"}]}),
        "records no offer owner fact")


def test_fact_text_of_the_wrong_type_is_refused_without_crashing():
    _refused(_bundle(
        [_claim("s6", "Backlinks help our websites rank and convert.",
                about={"fact": "market", "anchor": "help",
                       "fact_text": ["we help Dallas families sleep"]})],
        facts=FACTS), "about.fact_text must be a string")


def test_a_fact_text_that_matches_the_record_is_only_a_copy():
    """Over-refusal control: a claim that quotes the recorded owner fact back
    is accepted — the copy is checked against the record, not invented."""
    _accepted(_bundle(
        [_claim("ok1", "Sleep coaching demand among nurses has risen since 2021.",
                about={"fact": "offer", "anchor": "sleep", "fact_text": OFFER})],
        facts=FACTS))
    # ... and the same copy folded into look-alike glyphs is still a copy
    _accepted(_bundle(
        [_claim("ok2", "Sleep coaching demand among nurses has risen since 2021.",
                about={"fact": "offer", "anchor": "sleep",
                       "fact_text": "Ａ 12-week sleep coaching program for shift "
                                    "workers"})],
        facts=FACTS))


# --------------------------------- reworded spam, in ordinary vocabulary

SPAM = [
    ("Sleep coaches sell billboard space to tired landlords. "
     "Sleep programs offer vape subscriptions to tired families. "
     "Sleep clinics list sneaker deals for tired mothers."),
    ("Sleep coaches sell car warranties to tired nurses."),
    ("Competing sleep programs rent billboard space to tired landlords."),
    ("Sleep coaches recommend crypto wallets to tired shift workers. "
     "Sleep programs recommend vape pens to tired nurses."),
    ("Sleep coaches sell backlinks to nurses."),
]


def test_reworded_spam_is_refused_however_it_is_worded():
    for i, text in enumerate(SPAM):
        errors = _refused(_bundle(
            [_claim("sp%d" % i, text, about={"fact": "offer", "anchor": "sleep"})],
            facts=FACTS))
        assert any("not about this run" in e or "keyword stuffing" in e
                   for e in errors), (text, errors)


def test_spam_filed_as_an_owner_statement_is_refused_the_same_way():
    _refused(_bundle(
        [_claim("sp-o", "Sleep coaches sell backlinks to nurses.",
                provenance="owner-fact", owner_ref="answer:q4",
                about={"fact": "offer", "anchor": "sleep"})], facts=FACTS),
        "not about this run")


def test_a_claim_that_sells_what_the_run_records_still_passes():
    """Over-refusal control: the same sentence shape with grounded content."""
    _accepted(_bundle(
        [_claim("ok3", "Sleep coaches sell sleep coaching to tired nurses.",
                about={"fact": "offer", "anchor": "sleep"})], facts=FACTS))


# ------------------------------------------------------------ keyword runs

RUNS = [
    "sleep clinic plano insomnia help sleep coaching fort worth backlinks",
    "sleep clinic plano insomnia helps sleep coaching fort worth backlinks",
    "the sleep clinic plano insomnia help sleep coaching fort worth backlinks",
    "a sleep coaches dallas insomnia helping sleep clinic dallas backlinks",
    "sleep, coaches, dallas, insomnia, help, clinic, backlinks",
    "sleep coaches dallas. sleep clinic plano. sleep backlinks help",
]


def test_keyword_runs_are_refused_with_or_without_a_verb():
    for i, text in enumerate(RUNS):
        errors = _refused(_bundle(
            [_claim("k%d" % i, text, about={"fact": "offer", "anchor": "sleep"})],
            facts=FACTS))
        assert any("keyword stuffing" in e or "not about this run" in e
                   for e in errors), (text, errors)


# ------------------------------------------- what must keep passing, passes

CITED = [
    ("competitor pricing", "Competing Dallas sleep programs charge between $220 "
                           "and $540 a month.", "competitor-pricing",
     "charge between $220 and $540 a month", "competitors", "sleep", OFFER),
    ("audience statistic", "About 30 percent of Dallas nurses report sleeping "
                           "fewer than six hours a night.", "audience-evidence",
     "About 30 percent of Dallas nurses report sleeping fewer than six hours "
     "a night.", "audience", "nurses", AUDIENCE),
    ("market growth", "Sleep coaching demand in Dallas has grown steadily since "
                      "2021.", "market-growth",
     "Sleep coaching demand in Dallas has grown steadily since 2021.",
     "market", "sleep", OFFER),
    ("the spam's own vocabulary, grounded",
     "Across hospital pages the best documented referral channel is the sleep "
     "clinic list.", "competitor-ranking",
     "the best documented referral channel is the sleep clinic list",
     "competitors", "sleep", OFFER),
]


def test_legitimate_grounded_facts_pass_the_same_instrument():
    sources = [dict(SRC, excerpts=EXCERPTS)]
    for label, text, cls, quote, fact, anchor, fact_text in CITED:
        _accepted(_bundle(
            [_claim("ok-" + cls, text, **{"class": cls,
                                          "support": {"source": "src-1",
                                                      "locator": "p.1",
                                                      "quote": quote},
                                          "about": {"fact": fact, "anchor": anchor,
                                                    "fact_text": fact_text.lower()}})],
            sources=sources, facts=FACTS))


def test_claims_grounded_only_in_the_run_owner_facts_pass():
    _accepted(_bundle(
        [_claim("ok4", "Shift workers report short sleep after rotating shifts.",
                about={"fact": "audience", "anchor": "shift"})], facts=FACTS))
    _accepted(_bundle(
        [_claim("ok5", "Our clients report sleeping through the night within "
                       "three weeks.", provenance="owner-fact",
                owner_ref="answer:q11",
                about={"fact": "audience", "anchor": "night", "fact_text": AUDIENCE})],
        facts=FACTS))


def test_sourced_claims_still_pass_when_filed_bare():
    """The third round kept uncited sourced claims passing; they still do."""
    for text, fact, anchor in (
            ("Sleep coaching in Dallas is marketed mostly through local search "
             "and referral.", "offer", "sleep"),
            ("Shift workers report disturbed sleep after rotating shifts.",
             "audience", "shift"),
            ("Sleep coaching programs attract tired commuters in Dallas.",
             "offer", "sleep"),
            ("Registered nursing is one of the larger occupations in the "
             "United States.", "audience", "nursing")):
        _accepted(_bundle(
            [_claim("ok-bare", text, about={"fact": fact, "anchor": anchor})],
            facts=FACTS))


# ------------------------------------------------------------- end to end

def test_cli_refuses_the_self_supplied_fact_and_accepts_a_grounded_bundle(tmp_path):
    good = _bundle(
        [_claim("g1", "Sleep coaching demand among nurses has risen since 2021.",
                about={"fact": "offer", "anchor": "sleep", "fact_text": OFFER})],
        facts=FACTS)
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(good), encoding="utf-8")
    assert R.main(["--validate-bundle", str(path)]) == 0

    bad = _bundle(
        [_claim("b1", "Backlinks help our websites rank and convert.",
                about={"fact": "offer", "anchor": "help",
                       "fact_text": "we help Dallas families sleep"})], facts=FACTS)
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert R.main(["--validate-bundle", str(path)]) == R.EXIT["rejected"] == 4


def test_stage_refuses_the_self_supplied_fact_before_it_writes(tmp_path):
    brief = dict(FACTS)
    brief.update({"sub_avatar": {"avatar": "nurse", "emotional_wound": "awake",
                                 "desired_transformation": "rested"},
                  "sources": [SRC],
                  "claims": [{"id": "c1",
                              "text": "Backlinks help our websites rank and convert.",
                              "source": "src-1",
                              "about": {"fact": "offer", "anchor": "help",
                                        "fact_text": "we help Dallas families sleep"}}]})
    env, code = R.run_stage(brief, str(tmp_path), gather=False)
    assert code == R.EXIT["rejected"], env
    assert not (tmp_path / "research").exists(), "no artifact on refusal"


# ----------------- round five: the three families that survived round four

MAJORITY_SPAM = [
    "Tired nurses and weary mothers want backlinks after long winter shifts.",
    "Sleep services give tired parents mattress deals every winter.",
    "Sleep coaching keeps tired nurses awake with diet tea.",
    "Sleep programs keep tired families awake with crypto pumps.",
    "Sleep studies find tired nurses want diet tea after shifts.",
    "Tired nurses want backlinks after shifts.",
    "Sleep clinics find tired parents want diet tea after winter shifts.",
]
CAPITAL_SPAM = [
    "Sleep coaches help tired nurses with Backlinks.",
    "Sleep coaches rank Crypto and Backlinks for tired nurses.",
    "Sleep coaches help tired nurses with Mattress Deals.",
]
LAUNDERED = [
    "Sleep coaches sell mattress deals to tired parents.",
    "Sleep programs offer crypto pumps to tired families.",
    "Sleep services list diet tea for tired mothers.",
    "Sleep clinics price mattress deals for tired parents.",
    "Sleep coaches sell backlinks to tired clinics.",
]


def _about_offer():
    return {"fact": "offer", "anchor": "sleep", "fact_text": OFFER}


def test_a_minority_of_unrecorded_words_is_still_a_sentence_about_something_else():
    """Round five. A majority of grounded words no longer buys a pass: the head
    of a stretch of content is the word the stretch is ABOUT, and if the run
    records no such word the sentence is about something else however many
    grounded words pad it. Round four counted, and counting let these through."""
    for i, text in enumerate(MAJORITY_SPAM):
        _refused(_bundle([_claim("mv%d" % i, text, about=_about_offer())],
                         facts=FACTS), "not about this run")


def test_a_capital_letter_names_nothing_in_a_predicates_complement():
    """Round five. 'Backlinks' where the predicate asserts it is content
    exactly as 'backlinks' is. The lower-case twin is refused by the same rule,
    which is what proves the capital letter was the only difference."""
    for i, text in enumerate(CAPITAL_SPAM):
        _refused(_bundle([_claim("cap%d" % i, text, about=_about_offer())],
                         facts=FACTS), "not about this run")
        _refused(_bundle([_claim("low%d" % i, text.lower(), about=_about_offer())],
                         facts=FACTS), "not about this run")


def test_the_filers_own_excerpt_is_never_grounding():
    """Round five. A source record the filer wrote cannot be what makes the
    filer's own claim about this run. Quoting the claim into `excerpts` used to
    ground every word of it; it grounds nothing now, so the only place this
    record appears is the citation check."""
    for i, text in enumerate(LAUNDERED):
        src = dict(SRC, excerpts=[text])
        _refused(_bundle([_claim("ld%d" % i, text, about=_about_offer())],
                         sources=[src], facts=FACTS), "not about this run")
    # hidden among genuine excerpt sentences, and as one long excerpt
    src = dict(SRC, excerpts=["Night-shift nurses report short sleep after "
                              "rotating shifts."] + LAUNDERED)
    _refused(_bundle([_claim("ld-hid", LAUNDERED[0], about=_about_offer())],
                     sources=[src], facts=FACTS), "not about this run")
    _refused(_bundle([_claim("ld-run", " ".join(LAUNDERED),
                             about=_about_offer())],
                     sources=[src], facts=FACTS), "not about this run")
    # over-refusal control: a genuine sourced sentence never needed the excerpt
    genuine = "Night-shift nurses report short sleep after rotating shifts."
    _accepted(_bundle([_claim("ld-ok", genuine,
                              about={"fact": "audience", "anchor": "nurses"})],
                      sources=[dict(SRC, excerpts=[genuine])], facts=FACTS))


def test_a_name_where_a_name_may_sit_is_still_a_name():
    """Over-refusal control for round five's naming rule. A place name in the
    subject, or after a non-transfer preposition, is naming material: it names,
    it does not assert."""
    for text, fact, anchor in (
            ("Dallas has over 40 sleep coaching practices listed publicly.",
             "offer", "sleep"),
            ("Sleep coaching programs attract tired commuters in Dallas.",
             "offer", "sleep"),
            ("Registered nursing is one of the larger occupations in the "
             "United States.", "audience", "nursing")):
        kw = {"about": {"fact": fact, "anchor": anchor}}
        if "40" in text:                   # 'listed' is a rank marker
            kw["class"] = "market-size"
            kw["support"] = {"source": "src-1", "locator": "p.1",
                             "quote": "over 40 sleep coaching practices listed"}
        _accepted(_bundle([_claim("nm", text, **kw)], facts=FACTS))


def main():
    """Script-style run: same checks, plain output."""
    import inspect
    import shutil
    import tempfile
    from pathlib import Path
    names = [n for n, fn in sorted(globals().items())
             if n.startswith("test_") and callable(fn)]
    failed = 0
    for name in names:
        fn = globals()[name]
        tmp = None
        kwargs = {}
        for param in inspect.signature(fn).parameters:
            if param == "tmp_path":
                tmp = Path(tempfile.mkdtemp(prefix="research-grounding-"))
                kwargs[param] = tmp
        try:
            fn(**kwargs)
            print("PASS %s" % name)
        except AssertionError as exc:
            failed += 1
            print("FAIL %s: %s" % (name, exc))
        finally:
            if tmp is not None:
                shutil.rmtree(tmp, ignore_errors=True)
    print("%d checks, %d failed" % (len(names), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

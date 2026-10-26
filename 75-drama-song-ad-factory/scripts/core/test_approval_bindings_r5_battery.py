#!/usr/bin/env python3
"""Battery for the idiom register, the revision binding and the selection screen.

Round 5 locked the idiom register and the revision binding. Round 6 locks the
SELECTION screen: an ordinal selects an artifact only beside an artifact name.

The repair these lock in is b821a02dd ("refuse an unseen referent, open the
idiom register"). This file adds the cases that repair's own battery does not
carry: the form screens ON the idiom register (an idiom that also asks for a
change, a question, a negation, a quote, a condition or an unseen referent must
still refuse), the ambiguity texts named in the round-5 brief, and the promise
that a receipt binds only the revision the reply itself named. Nothing here
changes behaviour -- every case is asserted against the gate as it stands.

Run: python3 scripts/core/test_approval_bindings_r5_battery.py
 or: python3 -m pytest -q scripts/core/test_approval_bindings_r5_battery.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import approval_bindings as B  # noqa: E402
from script_approval import approval_events as AE  # noqa: E402

#: an idiom affirmative is still refused by every form screen it trips
IDIOM_SCREEN_REFUSALS = (
    "Green light the drama song ad package and change the ending.",
    "Green light the drama song ad package, but the music is too loud.",
    "Green light the drama song ad package and rewrite the lyrics.",
    "Should we green light the drama song ad package?",
    "Do not green light the drama song ad package.",
    "Green light the drama song ad package after we see the script.",
    "Green light the drama song ad package if the ending is happier.",
    "My partner said green light the drama song ad package.",
    'The note said "green light the drama song ad package".',
    "Fire away on option 2.",
)

#: an idiom that names no artifact and no package approves nothing specific
IDIOM_NOTHING_NAMED = (
    "Green light.",
    "Full steam ahead.",
    "You have our blessing.",
    "Green light one of the packages.",
)

#: the ambiguity texts the round-5 brief names by hand
AMBIGUITY_NAMED_BY_THE_BRIEF = (
    "them", "one of them", "the rest", "all of those",
    "yes", "ok", "sounds good", "go ahead", "approved",
    "whatever you think", "you decide", "lgtm",
)

#: a revision that was never presented refuses by name
UNSEEN_REVISION_REFUSALS = (
    "I approve the whole package, revision 99.",
    "I approve the whole creative package, version 42.",
    "The scene plan revision 9 is approved.",
    "The script revision 2 is approved.",
    "The lyrics revision 7 are approved.",
    "The episode world rev 5 is approved.",
    "The creative package manifest revision 3 is approved.",
)

#: an artifact that was never presented refuses by name, package or not
UNSEEN_KIND_REFUSALS = (
    "I approve the music.",
    "I approve the whole drama song ad package and the music.",
    "Green light the music.",
)

#: a revision that WAS presented binds exactly the revision the reply named
SEEN_REVISION_BINDS = (
    ("The scene plan revision 1 is approved.", ["scene_plan"]),
    ("The script revision 1 and the lyrics revision 1 are approved.", ["lyrics", "script"]),
)

NAMED_REFUSAL_CODES = ("APPROVAL_NAMES_UNSEEN_REVISION",
                       "APPROVAL_NAMES_UNKNOWN_ARTIFACT",
                       "APPROVAL_NAMES_UNSEEN_ARTIFACT")

#: an ordinal that SELECTS one artifact names nothing that was presented
ORDINAL_SELECTIONS = (
    "We approve the second script.",
    "We approve the second script and the lyrics.",
    "We approve the first script.",
    "We approve the third lyric.",
    "We approve the 2nd script.",
    "We approve script two.",
    "We approve the second script at revision 1.",
)

#: a selection beside a package name never falls through to the whole package
ORDINAL_SELECTION_BESIDE_PACKAGE = (
    "We approve the second script and the drama song ad package.",
    "We approve the drama song ad package and the first lyric.",
)

#: an ordinal that NUMBERS a presented revision is not a selection
ORDINAL_REVISION_REFERENCES = (
    ("We approve the script at revision 1.", ["script"]),
    ("We approve version 1 of the script.", ["script"]),
    ("We approve the script, rev 1.", ["script"]),
    ("We approve the first revision of the script.", ["script"]),
)


def components():
    return {k: {"revision": 1, "digest": "digest-" + k} for k in B.COMPONENTS}


def client_ctx(text, **extra):
    ctx = {"reply_text": text, "source": "client", "source_ref": "tg-msg-1",
           "approved_by": "client_001", "timestamp": "2026-10-24T12:00:00Z"}
    ctx.update(extra)
    return ctx


def _bound_book():
    book = B.ApprovalBook()
    book.bind("package", components(), tenant_id="t1", run_id="r1")
    return book


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except B.BindingError as exc:
        return exc
    raise AssertionError("expected BindingError")


def _assert_refused(book, exc, text):
    assert exc.code != "APPROVED", (text, exc.code)
    assert str(exc).strip(), text                     # a refusal says which
    assert book.receipts_for("package") == [], text
    assert book.coverage("package")["approved"] == [], text
    verdict = book.admissibility("package")
    assert verdict["ok"] is False and verdict["code"] != "APPROVED", (text, verdict)


def test_idiom_register_keeps_every_form_screen():
    """Opening the idiom register did NOT loosen anything: an idiom that also
    asks for a change, a question, a negation, a quote, a condition or a
    selection still refuses, and mints nothing."""
    for text in IDIOM_SCREEN_REFUSALS:
        book = _bound_book()
        _assert_refused(book, _raises(book.approve, "package", client_ctx(text)), text)


def test_idiom_register_names_nothing_approves_nothing():
    for text in IDIOM_NOTHING_NAMED:
        book = _bound_book()
        _assert_refused(book, _raises(book.approve, "package", client_ctx(text)), text)


def test_the_named_ambiguity_texts_mint_nothing():
    """The texts the brief names must mint 0 components -- the idiom register
    is not a way around the ambiguity rule."""
    for text in AMBIGUITY_NAMED_BY_THE_BRIEF:
        book = _bound_book()
        _assert_refused(book, _raises(book.approve, "package", client_ctx(text)), text)


def test_unseen_revision_refuses_by_name_and_mints_nothing():
    for text in UNSEEN_REVISION_REFUSALS:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(text))
        assert exc.code == "APPROVAL_NAMES_UNSEEN_REVISION", (text, exc.code)
        _assert_refused(book, exc, text)


def test_unseen_artifact_refuses_by_name_and_mints_nothing():
    for text in UNSEEN_KIND_REFUSALS:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(text))
        assert exc.code in NAMED_REFUSAL_CODES, (text, exc.code)
        _assert_refused(book, exc, text)


def test_receipt_binds_only_the_revision_the_reply_named():
    """The referent is bound in both directions: a receipt never binds a
    revision the reply did not name, and never a wider scope than it named."""
    for text, covers in SEEN_REVISION_BINDS:
        book = _bound_book()
        receipt = book.approve("package", client_ctx(text))
        assert receipt["decision"] == "approved" and receipt["state"] == B.ACTIVE, text
        assert sorted(receipt["components"]) == covers, (text, receipt["components"])
        want = AE.named_revision(text)
        assert want == 1, text
        for kind, value in receipt["components"].items():
            assert value == book.binding("package")["components"][kind], (text, kind, value)
            assert value["revision"] == want, (text, kind, value)
        verdict = book.admissibility("package")
        assert verdict["code"] == "APPROVAL_INCOMPLETE", (text, verdict)


def test_idiom_affirmatives_still_open_at_their_named_scope():
    """The other half: what the repair opened must stay open."""
    for text in ("Green light the drama song ad package and the script.",
                 "Full steam ahead on the drama song ad package and the lyrics.",
                 "Let's move forward with the creative package and the script.",
                 "You have our blessing on the creative package and the script."):
        book = _bound_book()
        receipt = book.approve("package", client_ctx(text))
        assert sorted(receipt["components"]) == sorted(B.COMPONENTS), text
        assert book.admissibility("package")["ok"] is True, text


def test_an_ordinal_selection_never_mints_a_receipt():
    """"We approve the second script." names no presented artifact: one script
    was shown, so "the second" is a member of a list that was never presented.
    It must never reach the name-gap carve-out and mint a receipt."""
    for text in ORDINAL_SELECTIONS:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(text))
        assert exc.code == "APPROVAL_IS_A_SELECTION", (text, exc.code)
        _assert_refused(book, exc, text)


def test_an_ordinal_beside_a_package_name_mints_nothing():
    """A selection beside a package name never falls through to a whole-package
    mint the client did not name."""
    for text in ORDINAL_SELECTION_BESIDE_PACKAGE:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(text))
        assert exc.code == "APPROVAL_IS_A_SELECTION", (text, exc.code)
        _assert_refused(book, exc, text)


def test_an_ordinal_that_numbers_a_revision_still_resolves():
    """The other half of the screen: a numeral that numbers a presented
    revision is not a selection, and still opens at its own scope. A screen that
    refused these too would be a blanket refusal, not a repair."""
    for text, covers in ORDINAL_REVISION_REFERENCES:
        book = _bound_book()
        receipt = book.approve("package", client_ctx(text))
        assert receipt["decision"] == "approved" and receipt["state"] == B.ACTIVE, text
        assert sorted(receipt["components"]) == covers, (text, receipt["components"])
        verdict = book.admissibility("package")
        assert verdict["code"] == "APPROVAL_INCOMPLETE", (text, verdict)


# =========================================================================== #
# ROUND 6 -- the selection screen is ADJACENCY, not a scan of the whole reply
# =========================================================================== #
#
# THE RULE, in one sentence: an ordinal or a number counts as SELECTING one
# artifact only when it is adjacent to an artifact name -- the name being the
# word next to it, or the name reached across a determiner ("the"), the
# preposition "of" or a revision noun ("revision"), with only whitespace between
# the words and no punctuation -- and a numeral that names a revision is exempt
# from this screen only where the reply names an ACTUAL revision number there.
#
# That rule has two sides, and both are counted below so a regression in either
# direction fails loudly. Refusing everything scores perfectly on the failure
# the screen was built to catch, so the OPEN set is asserted with the same force
# as the REFUSE set.

#: MUST REFUSE -- picks one artifact out of a list that was never presented.
#: The first 18 are the round-5 verifier's still_mints_should_not, reproduced
#: verbatim; the rest are this round's own variants of the same two families.
SELECTION_REFUSALS = (
    # family A -- the round-5 ordinal register stopped at "tenth"
    "We approve the eleventh script.",
    "We approve the twelfth script.",
    "We approve the zeroth script.",
    "We approve the last script.",
    "We approve the next script.",
    "We approve the previous script.",
    "We approve the penultimate script.",
    "We approve the nth script.",
    "We approve the upper script.",
    # family B -- the revision-noun exemption fired with no revision number
    "We approve the second revision script.",
    "We approve the second rev script.",
    "We approve the second v script.",
    "We approve the second version script.",
    "We approve the last revision script.",
    "We approve revision second of the script.",
    "We approve the second revision of the script.",
    "We approve the 2nd revision of the script.",
    "We approve the 2nd version of the script.",
    # this round's variants of the same families
    "We approve the thirteenth script.",
    "We approve the twentieth script.",
    "We approve the 21st script.",
    "We approve the first script and the lyrics.",
    "We approve the 3rd lyric.",
    "We approve script two.",
    "We approve the second story.",
    "We approve the fifth storyboard.",
    "We approve the 4th music.",
    "We approve the 2nd revision script.",
    "We approve the second revision of the lyrics.",
    "We approve the last revision of the script.",
    "We approve the next revision of the script.",
    "We approve the previous revision script.",
    "We approve the other script and the second lyrics.",
    "We approve the second scene plan and the script.",
)

#: MUST OPEN -- a genuine approval of a presented artifact that also carries a
#: number naming something else: a clock time, a date, a duration, an act/
#: phase/take figure, an fps rate, a team size, a score, a part count. The first
#: 20 are the round-5 verifier's over_refusal_regressions, reproduced verbatim.
MEASUREMENT_APPROVALS = (
    "We approve the drama song ad package at 2:30.",
    "We approve the drama song ad package for client 7.",
    "We approve the drama song ad package, delivery window 3 days.",
    "We approve the drama song ad package - 3 verses, 2 choruses.",
    "We approve the drama song ad package. One house: ours.",
    "We approve the script and the lyrics; take two.",
    "We approve the script and the lyrics on 2026-10-24.",
    "We approve the script and the two-part harmony.",
    "We approve the script and the three-act structure.",
    "We approve the script for act 2.",
    "We approve the script at 24 fps.",
    "We approve the script, 2 verses.",
    "We approve the script. It runs 4 minutes.",
    "We approve the script. Our team of five is happy.",
    "We approve the lyrics and the script for the second campaign.",
    "We approve the lyrics in 4/4.",
    "We approve the scene plan and the script at 30 fps.",
    "We approve the research bundle and the scene plan for take 3.",
    "We approve the episode world and the script for phase 1.",
    "We approve the causal story beats and the script. 10 out of 10.",
    # this round's variants
    "We approve the script for take 2.",
    "We approve the script at 1080p.",
    "We approve the lyrics and the script. 5 stars.",
    "We approve the script and the lyrics. 1st of October.",
    "We approve the drama song ad package, one per week.",
    "We approve the script. Team of three signed off.",
    "We approve the script and the lyrics, 2 of us agree.",
    "We approve the scene plan and the script for act three.",
    "We approve the research bundle and the script. Rated 8.",
    "We approve the script on 2026-10-25 at 09:30.",
    "We approve the episode world and the script. 6 hours of work.",
)

#: one sentence -- asserted to be one sentence, and quoted in the refusal text
ADJACENCY_RULE = (
    "An ordinal or number selects one artifact only when it is adjacent to an "
    "artifact name -- the next word, or the name reached across a determiner, "
    "the preposition 'of' or a revision noun, with only whitespace between and "
    "no punctuation -- and a numeral that names a revision is exempt only where "
    "the reply names an actual revision number there.")

#: the adjacency rule pinned at the predicate, BOTH sides, word by word
ADJACENCY_PROBES = (
    # the ordinal sits in the slot that names the artifact -> SELECTION
    ("We approve the second script.", True),
    ("We approve script two.", True),
    ("We approve the 2nd script.", True),
    ("We approve the eleventh script.", True),
    ("We approve the penultimate script.", True),
    ("We approve the last revision script.", True),
    ("We approve the last revision of the script.", True),
    ("We approve the second script and the lyrics.", True),
    # the number names a measurement somewhere else -> NOT a selection
    ("We approve the script at 2:30.", False),
    ("We approve the script on 2026-10-24.", False),
    ("We approve the script, 2 verses.", False),
    ("We approve the script. It runs 4 minutes.", False),
    ("We approve the script at 24 fps.", False),
    ("We approve the script for act 2.", False),
    ("We approve the script and the two-part harmony.", False),
    ("We approve the script. Our team of five is happy.", False),
    ("We approve the script. 10 out of 10.", False),
)


def _refused(book, text):
    exc = _raises(book.approve, "package", client_ctx(text))
    _assert_refused(book, exc, text)
    return exc


def test_the_selection_register_is_open_ended_and_refuses_every_member():
    """Round 5's register stopped at "tenth" and its revision exemption fired
    with no revision number at all. Every member of both families -- the 18 the
    verifier measured plus this round's variants -- mints nothing."""
    refused = 0
    for text in SELECTION_REFUSALS:
        _refused(_bound_book(), text)
        refused += 1
    assert refused == len(SELECTION_REFUSALS) == 34, refused


def test_over_refusal_would_fail_loudly():
    """THE OTHER SIDE, and the reason this file exists. Every reply here is a
    genuine approval of a presented artifact that happens to carry a number.
    Refusing one of them is the regression round 5 shipped, so the count is
    asserted: a blanket refusal cannot pass this test."""
    opened = []
    for text in MEASUREMENT_APPROVALS:
        book = _bound_book()
        receipt = book.approve("package", client_ctx(text))
        assert receipt["decision"] == "approved", text
        assert receipt["components"], text
        opened.append(text)
    assert len(opened) == len(MEASUREMENT_APPROVALS) == 31, len(opened)


def test_adjacency_not_presence_is_what_decides_a_selection():
    """Both sides of the one-sentence rule, pinned at the predicate itself: the
    ordinal selects beside a name and only beside a name."""
    for text, expected in ADJACENCY_PROBES:
        assert AE.selects_one_artifact(text) is expected, text


def test_a_revision_reference_needs_an_actual_revision_number():
    """A revision noun beside an ordinal is NOT an exemption on its own. Where
    the reply names a number, that number must have been presented; where it
    names none ("the last revision"), the ordinal is still judged as a
    selection. Either way revision 1 is never bound without being named."""
    unseen = (
        "We approve the second revision of the script.",
        "We approve the 2nd revision of the script.",
        "We approve the 2nd version of the script.",
        "We approve revision second of the script.",
        "We approve the second revision script.",
    )
    for text in unseen:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(text))
        assert exc.code == "APPROVAL_NAMES_UNSEEN_REVISION", (text, exc.code)
        assert AE.named_revision(text) == 2, (text, AE.named_revision(text))
        _assert_refused(book, exc, text)
    for text in ("We approve the last revision script.",
                 "We approve the last revision of the script.",
                 "We approve the next revision of the script."):
        exc = _refused(_bound_book(), text)
        assert exc.code == "APPROVAL_IS_A_SELECTION", (text, exc.code)
        assert AE.named_revision(text) is None, (text, AE.named_revision(text))
    # the number it DOES name still binds: "first revision" is revision 1
    book = _bound_book()
    receipt = book.approve("package",
                           client_ctx("We approve the first revision of the script."))
    assert sorted(receipt["components"]) == ["script"], receipt["components"]
    assert receipt["components"]["script"]["revision"] == 1, receipt
    assert AE.named_revision("We approve the first revision of the script.") == 1


def test_the_rule_is_one_sentence():
    assert ADJACENCY_RULE.count(".") == 1 and ADJACENCY_RULE.endswith("."), ADJACENCY_RULE


if __name__ == "__main__":
    failures = 0
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith("test_") and callable(fn)]
    for name, fn in tests:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - standalone runner
            failures += 1
            print("FAIL %s: %s: %s" % (name, type(exc).__name__, exc))
        else:
            print("ok   %s" % name)
    print("\n%d passed, %d failed, %d total" % (len(tests) - failures, failures, len(tests)))
    sys.exit(1 if failures else 0)

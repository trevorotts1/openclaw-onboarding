#!/usr/bin/env python3
"""Round-5 regression battery for the idiom register and the revision binding.

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

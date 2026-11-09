#!/usr/bin/env python3
"""Focused tests for approval_bindings (S75-T12 / S75-A12).

Run: python3 scripts/core/test_approval_bindings.py
 or: python3 -m pytest -q scripts/core/test_approval_bindings.py
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import approval_bindings as B  # noqa: E402

FIXTURE = os.path.join(os.path.dirname(HERE), "..", "tests", "fixtures",
                       "artifact_binding_changes.json")


def components(**overrides):
    base = {kind: {"revision": 1, "digest": "digest-" + kind} for kind in B.COMPONENTS}
    base.update(overrides)
    return base


def client_ctx(text="I approve the whole creative package.", **extra):
    ctx = {"reply_text": text, "source": "client", "source_ref": "tg-msg-1",
           "approved_by": "client_001", "timestamp": "2026-10-24T12:00:00Z"}
    ctx.update(extra)
    return ctx


def _raises(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except B.BindingError as exc:
        return exc
    raise AssertionError("expected BindingError")


def _book():
    book = B.ApprovalBook()
    book.bind("package", components(), tenant_id="t1", run_id="r1")
    book.approve("package", client_ctx())
    book.elect("storyboard_approval", 1, "digest-storyboard", client_ctx("approve storyboard"))
    return book


def test_full_package_binds_and_approves():
    book = _book()
    assert book.admissibility("package")["ok"] is True
    receipt = book.receipt_for("package")
    assert receipt["package"] == B.PACKAGE_APPROVAL
    assert set(receipt["components"]) == set(B.COMPONENTS)


def test_missing_component_refused():
    incomplete = components()
    incomplete.pop("lyrics")
    exc = _raises(B.ApprovalBook().bind, "package", incomplete)
    assert exc.code == "BINDING_INCOMPLETE"


def test_per_scene_binding_refused():
    with_scene = components()
    with_scene["scene_plan.scene_03"] = {"revision": 1, "digest": "scene-3"}
    exc = _raises(B.ApprovalBook().bind, "package", with_scene)
    assert exc.code == "NO_GRANULAR_APPROVAL_LOOP"


def test_per_character_binding_refused():
    with_character = components()
    with_character["character_images"] = {"revision": 1, "digest": "img"}
    exc = _raises(B.ApprovalBook().bind, "package", with_character)
    assert exc.code == "NO_GRANULAR_APPROVAL_LOOP"


def test_overlapping_binding_refused():
    book = B.ApprovalBook()
    book.bind("package", components())
    exc = _raises(book.bind, "second_package", components())
    assert exc.code == "BINDING_OVERLAP"
    assert "script" in exc.packet["overlap"]


def test_overlap_refused_even_with_partial_rerun():
    book = B.ApprovalBook()
    book.bind("package", components())
    partial = {k: v for k, v in components().items() if k in ("script", "lyrics")}
    exc = _raises(book.bind, "rerun", partial)
    assert exc.code == "BINDING_INCOMPLETE"


def test_approval_without_reply_refused():
    book = B.ApprovalBook()
    book.bind("package", components())
    exc = _raises(book.approve, "package", {"source": "client", "approved_by": "client_001"})
    assert exc.code == "APPROVAL_NOT_ACTUAL"


def test_approval_without_identity_refused():
    book = B.ApprovalBook()
    book.bind("package", components())
    exc = _raises(book.approve, "package", {"reply_text": "approve", "source": "client"})
    assert exc.code == "APPROVAL_NOT_ACTUAL"


def test_preference_is_not_approval():
    book = B.ApprovalBook()
    book.bind("package", components())
    exc = _raises(book.approve, "package", client_ctx("show me the script first"))
    assert exc.code == "PREFERENCE_IS_NOT_APPROVAL"
    assert book.admissibility("package")["ok"] is False


def test_non_client_source_cannot_approve():
    book = B.ApprovalBook()
    book.bind("package", components())
    exc = _raises(book.approve, "package", client_ctx(source="assistant"))
    assert exc.code == "APPROVAL_NOT_ACTUAL"


def test_missing_receipt_fails_closed():
    book = B.ApprovalBook()
    book.bind("package", components())
    verdict = book.admissibility("package")
    assert verdict == {"ok": False, "code": "APPROVAL_MISSING", "binding_id": "package"}


def test_component_change_goes_stale():
    book = _book()
    moved = book.update_component("package", "script", 2, "digest-script-v2")
    assert moved["changed"] is True
    assert moved["invalidated"] == [book.receipt_for("package")["receipt_id"]]
    verdict = book.admissibility("package")
    assert verdict["ok"] is False
    assert verdict["code"] == "APPROVAL_INVALIDATED"


def test_elected_kind_cannot_be_rebound_as_component():
    book = B.ApprovalBook()
    exc = _raises(book.elect, "script", 1, "digest-script", client_ctx())
    assert exc.code == "COMPONENT_ALREADY_COVERED"


def test_elected_per_character_refused():
    exc = _raises(B.ApprovalBook().elect, "character_images", 1, "img", client_ctx())
    assert exc.code == "NO_GRANULAR_APPROVAL_LOOP"


def test_change_scenarios_from_fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        fixture = json.load(f)
    for case in fixture["cases"]:
        book = _book()
        by_name = {"package": book.receipt_for("package")["receipt_id"],
                   "storyboard_approval": book.elected("storyboard_approval")["receipt_id"]}
        result = book.note_change(case["changed"])
        got = sorted(result["invalidated"])
        want = sorted(by_name[n] for n in case["expect_invalidated"])
        assert got == want, "%s: %r != %r" % (case["name"], got, want)
        for name in case["expect_active"]:
            live = [r for r in book.receipt_list() if r["receipt_id"] == by_name[name]][0]
            assert live["state"] == B.ACTIVE, case["name"]


def test_binding_digest_changes_with_any_component():
    first = B.binding_digest(components())
    second = B.binding_digest(components(script={"revision": 2, "digest": "digest-script-v2"}))
    assert first != second


def test_components_match_the_stage_contract():
    import story_first_contracts as C
    assert set(B.COMPONENTS) == set(C.APPROVAL_BINDS["package_approval"])
    for kind in ("episode_cast_manifest", "episode_world", "scene_plan", "script", "lyrics"):
        assert kind in B.COMPONENTS


def test_digest_drift_is_refused_not_permission():
    book = _book()
    book.binding("package")["binding_digest"] = "drifted"
    verdict = book.admissibility("package")
    assert verdict["ok"] is False
    assert verdict["code"] == "APPROVAL_STALE"

def _fixture():
    with open(FIXTURE, encoding="utf-8") as f:
        return json.load(f)

def _presented():
    """The one presentation, as the interpreter reads it: nothing approved."""
    arts = {k: {"revision": 1, "sha256": "digest-" + k} for k in B.COMPONENTS}
    return ({"artifacts": arts, "approvals": [], "sent": True,
             "asks": [{"ask_id": "ask-1", "kinds": list(B.COMPONENTS), "state": "open",
                       "revisions": {k: 1 for k in B.COMPONENTS}}]},
            {"source": "client", "source_ref": "tg-msg-9", "presentation_ask_id": "ask-1"})

def test_nothing_short_of_an_unambiguous_approval_opens_the_gate():
    """The coverage failure: every refusal, condition, scope, selection,
    question and quote must leave the gate closed and record nothing."""
    from script_approval import approval_events as AE
    rec, ctx = _presented()
    for case in _fixture()["reply_decisions"]["must_not_open"]:
        read = AE.interpret_reply(case["text"], rec, ctx)
        assert read["intent"] == case["intent"], "%s read as %s" % (case["name"], read["intent"])
        assert AE.is_affirmative(case["text"]) is False, case["name"]
        book = B.ApprovalBook()
        book.bind("package", components(), tenant_id="t1", run_id="r1")
        exc = _raises(book.approve, "package", client_ctx(case["text"]))
        assert exc.code != "APPROVED", case["name"]
        verdict = book.admissibility("package")
        assert verdict["ok"] is False and book.receipt_for("package") is None, case["name"]

def test_plain_approvals_still_open_the_gate():
    from script_approval import approval_events as AE
    rec, ctx = _presented()
    for case in _fixture()["reply_decisions"]["must_open"]:
        read = AE.interpret_reply(case["text"], rec, ctx)
        assert read["intent"] == case["intent"], "%s read as %s" % (case["name"], read["intent"])
        book = B.ApprovalBook()
        book.bind("package", components(), tenant_id="t1", run_id="r1")
        receipt = book.approve("package", client_ctx(case["text"]))
        assert receipt["decision"] == "approved" and receipt["state"] == B.ACTIVE, case["name"]
        assert sorted(receipt["components"]) == case["covers"], case["name"]
        assert book.admissibility("package")["ok"] is True, case["name"]


# --------------------------------------------------------------------------- #
# round 4: scope is bound in BOTH directions
# --------------------------------------------------------------------------- #

def _bound_book():
    book = B.ApprovalBook()
    book.bind("package", components(), tenant_id="t1", run_id="r1")
    return book


def test_battery_sizes_are_the_deliverable():
    replies = _fixture()["reply_decisions"]
    assert len(replies["ambiguous_scope"]) >= 15, len(replies["ambiguous_scope"])
    assert len(replies["partial_scope"]) >= 10, len(replies["partial_scope"])
    assert len(replies["must_open"]) >= 20, len(replies["must_open"])
    named = {c["text"] for c in replies["ambiguous_scope"]}
    for text in ("approve one of them", "approved", "yes", "sounds good",
                 "the ones we discussed", "all of those"):
        assert text in named, text
    for case in replies["must_open"]:
        assert case["covers"] == sorted(B.COMPONENTS), case["name"]
        canon, package = B._scan_scope(case["text"])
        assert package or canon, "%s names no artifact" % case["name"]
    with_noun = [c for c in replies["must_open"] if B._scan_scope(c["text"])[0]]
    assert len(with_noun) >= 20, len(with_noun)


def test_ambiguity_battery_mints_nothing_at_all():
    """A reply that approves nothing specific never covers the package."""
    for case in _fixture()["reply_decisions"]["ambiguous_scope"]:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(case["text"]))
        assert exc.code != "APPROVED", case["name"]
        assert book.receipts_for("package") == [], case["name"]
        assert book.receipt_for("package") is None, case["name"]
        assert book.coverage("package")["approved"] == [], case["name"]
        verdict = book.admissibility("package")
        assert verdict["ok"] is False and verdict["code"] != "APPROVED", case["name"]


def test_partial_scope_covers_only_what_is_named():
    """'The scene plan is approved.' approves one component, not eight."""
    for case in _fixture()["reply_decisions"]["partial_scope"]:
        book = _bound_book()
        receipt = book.approve("package", client_ctx(case["text"]))
        assert receipt["decision"] == "approved" and receipt["state"] == B.ACTIVE, case["name"]
        assert sorted(receipt["components"]) == case["covers"], (
            "%s covered %s" % (case["name"], sorted(receipt["components"])))
        assert len(case["covers"]) < len(B.COMPONENTS), case["name"]
        assert receipt["scope"] == "partial", case["name"]
        coverage = book.coverage("package")
        assert coverage["approved"] == case["covers"], case["name"]
        assert coverage["missing"] == sorted(set(B.COMPONENTS) - set(case["covers"])), case["name"]
        verdict = book.admissibility("package")
        assert verdict["ok"] is False and verdict["code"] == "APPROVAL_INCOMPLETE", (
            case["name"], verdict)
        assert verdict["missing"] == coverage["missing"], case["name"]


def test_partial_battery_covers_every_foundation_component():
    """1-of-8 and 2-of-8 for every foundation component."""
    import story_first_contracts as C
    cases = _fixture()["reply_decisions"]["partial_scope"]
    for kind in C._FOUNDATION:
        assert [c for c in cases if c["covers"] == [kind]], "no 1-of-8 for %s" % kind
        assert [c for c in cases if kind in c["covers"] and len(c["covers"]) == 2], (
            "no 2-of-8 for %s" % kind)


def test_partial_approval_completes_only_when_the_rest_is_named():
    book = _bound_book()
    book.approve("package", client_ctx("The scene plan is approved."))
    assert book.admissibility("package")["ok"] is False
    book.approve("package", client_ctx("I approve the whole creative package."))
    assert book.coverage("package")["missing"] == []
    assert book.admissibility("package")["ok"] is True


def test_partial_receipt_is_invalidated_by_its_own_component_only():
    book = _bound_book()
    receipt = book.approve("package", client_ctx("The scene plan is approved."))
    moved = book.update_component("package", "script", 2, "digest-script-v2")
    assert moved["invalidated"] == [], moved
    assert receipt["state"] == B.ACTIVE
    moved = book.update_component("package", "scene_plan", 2, "digest-scene_plan-v2")
    assert moved["invalidated"] == [receipt["receipt_id"]], moved


def test_unseen_referent_mints_nothing_and_names_the_refusal():
    """A reply naming a revision or an artifact that was never presented mints
    NOTHING, and its refusal names what was never presented."""
    for case in _fixture()["reply_decisions"]["unseen_referent"]:
        book = _bound_book()
        exc = _raises(book.approve, "package", client_ctx(case["text"]))
        assert exc.code == case["expect_code"], (
            "%s refused as %s" % (case["name"], exc.code))
        assert exc.code != "APPROVED", case["name"]
        assert book.receipts_for("package") == [], case["name"]
        assert book.receipt_for("package") is None, case["name"]
        assert book.coverage("package")["approved"] == [], case["name"]
        verdict = book.admissibility("package")
        assert verdict["ok"] is False and verdict["code"] != "APPROVED", case["name"]


def test_a_receipt_never_binds_a_revision_the_reply_did_not_name():
    """The partial form of the same defect: "revision 9" must not mint rev 1."""
    book = _bound_book()
    receipt = book.approve("package", client_ctx("The scene plan is approved."))
    assert receipt["components"]["scene_plan"] == {"revision": 1, "digest": "digest-scene_plan"}, receipt

    moved = _bound_book()
    moved.update_component("package", "scene_plan", 9, "digest-scene_plan-v9")
    receipt = moved.approve("package", client_ctx("The scene plan revision 9 is approved."))
    assert receipt["components"]["scene_plan"] == {"revision": 9, "digest": "digest-scene_plan-v9"}, (
        receipt["components"])
    assert sorted(receipt["components"]) == ["scene_plan"], receipt["components"]
    exc = _raises(moved.approve, "package", client_ctx("The scene plan revision 1 is approved."))
    assert exc.code == "APPROVAL_NAMES_UNSEEN_REVISION", exc.code


def test_idiom_register_opens_on_the_named_scope():
    """Clear idiom affirmatives that name what they approve open the gate at
    exactly that scope -- the register that was refused 7 in 10."""
    from script_approval import approval_events as AE
    for case in _fixture()["reply_decisions"]["idiom_scope"]:
        book = _bound_book()
        receipt = book.approve("package", client_ctx(case["text"]))
        assert receipt["decision"] == "approved" and receipt["state"] == B.ACTIVE, case["name"]
        assert sorted(receipt["components"]) == case["covers"], (
            "%s covered %s" % (case["name"], sorted(receipt["components"])))
        whole = set(case["covers"]) == set(B.COMPONENTS)
        assert receipt["scope"] == (B.PACKAGE_APPROVAL if whole else "partial"), case["name"]
        assert AE.is_idiom_approval(case["text"], B._SCOPE_WORDS) is True, case["name"]
        verdict = book.admissibility("package")
        assert verdict["ok"] is whole, (case["name"], verdict)


def test_no_negation_or_condition_word_enters_the_approval_vocabulary():
    """"no", "not", "but" and "if" never become words an approval may be made
    of, in any of the three registers."""
    from script_approval import approval_events as AE
    for name in ("_GRAMMAR_WORDS", "_FUNCTION_WORDS", "_IDIOM_WORDS"):
        words = getattr(AE, name)
        assert not ({"no", "not", "but", "if"} & set(words)), (name,)
    for name in ("_GRAMMAR_WORDS", "_FUNCTION_WORDS", "_IDIOM_WORDS"):
        assert not (set(AE._BLOCKED) & set(getattr(AE, name))), name


def test_the_two_referent_vocabularies_are_one_list():
    """approval_events names the artifacts a reply may name; approval_bindings
    binds those same words to the presented components. One vocabulary."""
    from script_approval import approval_events as AE
    bound = {p for _, p in B._ARTIFACT_PHRASES} | set(B._PACKAGE_PHRASES)
    assert set(AE.REFERENT_PHRASES) == bound, (
        "only in events: %s / only in bindings: %s"
        % (sorted(set(AE.REFERENT_PHRASES) - bound), sorted(bound - set(AE.REFERENT_PHRASES))))


def _report():
    """Print decision / state / covered count per reply. A covered count of 8
    on an ambiguous or partial reply is the leak this battery exists to catch."""
    replies = _fixture()["reply_decisions"]
    for group in ("ambiguous_scope", "partial_scope", "must_open"):
        print("== %s" % group)
        leaks, opened = 0, 0
        for case in replies[group]:
            book = _bound_book()
            try:
                receipt = book.approve("package", client_ctx(case["text"]))
            except B.BindingError as exc:
                print("%-42s %-7s %-11s components=0 (%s)" % (
                    case["name"], "refused", exc.code, case["text"][:40]))
                continue
            covered = sorted(receipt["components"])
            if group != "must_open" and len(covered) == len(B.COMPONENTS):
                leaks += 1
            if group == "must_open" and book.admissibility("package")["ok"]:
                opened += 1
            print("%-42s %-7s %-11s components=%d %s" % (
                case["name"], receipt["decision"], receipt["state"], len(covered),
                ",".join(covered) if group == "partial_scope" else ""))
        print("-- %d cases, %d leaks, opened %d/%d\n"
              % (len(replies[group]), leaks, opened, len(replies[group])))
    return leaks


if __name__ == "__main__":
    if "--report" in sys.argv:
        sys.exit(1 if _report() else 0)
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

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


def client_ctx(text="approve", **extra):
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

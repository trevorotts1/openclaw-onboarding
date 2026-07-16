"""Tests for U106 (E5-1, closes G1) — Skill-6 companion to U30: the
community/course/channel builders' smoke_first() call-site hardening +
survival-probe / selector-drift-card idempotency.

This is the CODE/OFFLINE leg of U106 (deps: none — reuses U30's smoke_first()
if U30 lands first; U30 had not landed as of this build, so this unit
generalizes the shared helper itself in ghl_run_state.py). The LIVE-CREATE
leg (a live proof run that actually creates a community/course on the
operator box, with present->delete->absent cleanup proof) is out of scope
here and deferred to a LIVE-PROOF-tier run — nothing in this file touches a
browser, the network, or a live GHL/Convert-and-Flow account.

Covers:
  (b) smoke_first() is called by BOTH the community (_build_channels) and
      course (_build_outline) bulk paths, and a FAILING smoke aborts before
      any further bulk item is attempted — proven via dependency-injected
      fakes (add_channel=/add_lesson=), never a live browser.
  (c) the community/course/channel surfaces are declared in
      iframe-survival-targets.json's schema, and a SEEDED drift (a stripped
      iframe / a regressed selector) on any of them produces exactly ONE
      SELECTOR-MISS/VERIFY-FAIL board card — idempotent across repeated
      scans of the same evidence_root.
"""
import contextlib
import copy
import json
import os
import subprocess
import sys
import tempfile

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import ghl_run_state as run_state  # noqa: E402
import ghl_community_builder as cb  # noqa: E402
import ghl_course_builder as course  # noqa: E402
import ghl_selector_drift_probe as canary  # noqa: E402  (module renamed from ghl_selector_canary by U30/B-U16)


@contextlib.contextmanager
def _fake_browser():
    """Patch the shared browser primitives (cb._ab/_eval/_snapshot — both
    builders route the executor + list-scan through cb's module globals,
    read at CALL time) with always-succeed fakes, so a REAL LOCKed anchor's
    module-creation click/fill/wait ('course.outline.add_module' etc.)
    resolves without a real browser. Same shape as ghl_course_builder.py's
    own `_selftest()` mocked walk."""
    orig = (cb._ab, cb._eval, cb._snapshot)

    def fake_ab(session, *args, timeout=30, stdin=None):
        return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="OK", stderr="")

    def fake_eval(session, js, timeout=20):
        return "CLICKED:x" if ".click()" in js else "OK"

    try:
        cb._ab = fake_ab
        cb._eval = fake_eval
        cb._snapshot = lambda s, timeout=20: "OK"
        yield
    finally:
        cb._ab, cb._eval, cb._snapshot = orig


def _fully_locked_selectors():
    """A deepcopy of the REAL selectors-live-communities-courses.json with
    EVERY in-area anchor forced to 'locked' — the clean baseline a seeded
    drift test flips exactly ONE anchor away from, rather than starting from
    the honestly-still-pending set (privacy_switch etc.) which would count
    as pre-existing 'misses' unrelated to the seeded drift."""
    out = copy.deepcopy(cb.load_selectors())
    for a in canary.flatten_community_course_anchors(out):
        parts = a["id"].split(".")
        node = out
        for p in parts[:-1]:
            node = node[p]
        node[parts[-1]]["status"] = "locked"
    return out


# ═══════════════════════════════════════════════════════════════════════════
# smoke_first() — the generalized shared gate (ghl_run_state.py)
# ═══════════════════════════════════════════════════════════════════════════
def test_smoke_first_pass_returns_create_result_and_calls_create_once():
    calls = []
    result = run_state.smoke_first(
        "t:smoke", lambda: (calls.append(1), "the-thing")[1], lambda r: True)
    assert result == "the-thing"
    assert calls == [1]


def test_smoke_first_accepts_dict_verdict_with_ok_key():
    result = run_state.smoke_first("t:smoke", lambda: "x", lambda r: {"ok": True, "extra": 1})
    assert result == "x"


def test_smoke_first_fail_raises_before_any_further_work():
    with pytest.raises(run_state.SmokeFirstFailed) as ei:
        run_state.smoke_first("t:smoke-fail", lambda: "half-made", lambda r: False)
    assert ei.value.step == "t:smoke-fail"
    assert ei.value.result == "half-made"


def test_smoke_first_dict_verdict_fail_preserves_diagnostics():
    with pytest.raises(run_state.SmokeFirstFailed) as ei:
        run_state.smoke_first("t:smoke-fail2", lambda: "x",
                              lambda r: {"ok": False, "present_in_nav": False})
    assert ei.value.verdict == {"ok": False, "present_in_nav": False}
    assert "STOP before the bulk run" in str(ei.value)


# ═══════════════════════════════════════════════════════════════════════════
# helpers
# ═══════════════════════════════════════════════════════════════════════════
def _community_plan(channel_names):
    return cb.plan_community({
        "community_name": "Founders", "location_id": "L",
        "channels": channel_names,
    })


def _course_plan(module_lesson_pairs):
    """module_lesson_pairs: [("Welcome", ["Intro", "Setup"]), ("Build", ["First"])]"""
    modules = [{"title": mtitle, "lessons": [{"title": lt} for lt in lessons]}
              for mtitle, lessons in module_lesson_pairs]
    return course.plan_course({"course_name": "Launch", "location_id": "L", "modules": modules})


# ═══════════════════════════════════════════════════════════════════════════
# (b) community path — _build_channels() smoke-gates the channel bulk-add
# ═══════════════════════════════════════════════════════════════════════════
def test_build_channels_smoke_passes_then_the_rest_of_the_bulk_run_fires():
    plan = _community_plan(["Welcome", "General", "Wins"])
    calls = []
    written = []

    def fake_add_channel(session, sels, ch, evidence_root, shot_n, gov, keep):
        calls.append(ch["name"])
        return cb._receipt("channel", ch["slug"], "created",
                           verify={"present_in_nav": True, "method": "list-scan"})

    res = cb._build_channels(
        "s", {}, plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
        add_channel=fake_add_channel, write_receipt=lambda root, rc: written.append(rc))

    assert calls == ["Welcome", "General", "Wins"]          # smoke item + the rest, IN ORDER
    assert res["channels"] == 3
    assert len(written) == 3


def test_build_channels_smoke_fails_aborts_before_any_further_channel():
    plan = _community_plan(["Welcome", "General", "Wins"])
    calls = []

    def failing_first_add_channel(session, sels, ch, evidence_root, shot_n, gov, keep):
        calls.append(ch["name"])
        # The FIRST (smoke) channel's own store-delta check fails — never
        # trust a CLI "created"; present_in_nav=False is the honest arbiter.
        return cb._receipt("channel", ch["slug"], "created",
                           verify={"present_in_nav": False, "method": "list-scan"})

    with pytest.raises(run_state.SmokeFirstFailed) as ei:
        cb._build_channels(
            "s", {}, plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
            add_channel=failing_first_add_channel, write_receipt=lambda root, rc: None)

    # Exactly ONE channel was attempted (the smoke) — "General"/"Wins" NEVER
    # ran; a failed smoke aborts BEFORE the bulk run, it does not run it and
    # then fail partway.
    assert calls == ["Welcome"]
    assert ei.value.step == "C4:smoke:welcome"


def test_build_channels_empty_plan_is_a_noop_no_smoke_attempted():
    plan = _community_plan([])
    calls = []
    res = cb._build_channels(
        "s", {}, plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
        add_channel=lambda *a, **k: calls.append(1), write_receipt=lambda *a: None)
    assert calls == []
    assert res == {"channels": 0, "steps_done": []}


def test_community_live_build_calls_ghl_run_state_smoke_first_call_site():
    """Call-site test (spec 'smoke_first() is called by the community ...
    path'): patch ghl_run_state.smoke_first itself with a spy and prove
    _build_channels routes the FIRST channel through it (not a hand-rolled
    duplicate gate)."""
    plan = _community_plan(["Welcome", "General"])
    seen_steps = []
    orig = run_state.smoke_first

    def spy(step, create_fn, verify_fn, *, log=None):
        seen_steps.append(step)
        return orig(step, create_fn, verify_fn, log=log)

    def fake_add_channel(session, sels, ch, evidence_root, shot_n, gov, keep):
        return cb._receipt("channel", ch["slug"], "created",
                           verify={"present_in_nav": True})

    run_state.smoke_first = spy
    try:
        cb._build_channels(
            "s", {}, plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
            add_channel=fake_add_channel, write_receipt=lambda *a: None)
    finally:
        run_state.smoke_first = orig
    assert seen_steps == ["C4:smoke:welcome"]


# ═══════════════════════════════════════════════════════════════════════════
# (b) course path — _build_outline() smoke-gates the lesson bulk-add
# ═══════════════════════════════════════════════════════════════════════════
def test_build_outline_smoke_passes_then_the_rest_of_the_bulk_run_fires():
    plan = _course_plan([("Welcome", ["Intro", "Setup"]), ("Build", ["First"])])
    calls = []
    written = []

    def fake_add_lesson(session, sels, module, lesson, evidence_root, shot_n, gov, keep):
        calls.append((module["title"], lesson["title"]))
        return course._receipt("lesson", lesson["slug"], "created",
                               verify={"present_in_outline": True, "method": "snapshot"})

    with _fake_browser():
        res = course._build_outline(
            "s", cb.load_selectors(), plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
            resume=False, done_lessons=set(),
            add_lesson=fake_add_lesson, write_receipt=lambda root, rc: written.append(rc))

    assert calls == [("Welcome", "Intro"), ("Welcome", "Setup"), ("Build", "First")]
    assert len(written) == 3
    assert len(res["steps_done"]) == 3


def test_build_outline_smoke_fails_aborts_before_any_further_lesson():
    plan = _course_plan([("Welcome", ["Intro", "Setup"]), ("Build", ["First"])])
    calls = []

    def failing_first_add_lesson(session, sels, module, lesson, evidence_root, shot_n, gov, keep):
        calls.append((module["title"], lesson["title"]))
        return course._receipt("lesson", lesson["slug"], "created",
                               verify={"present_in_outline": False, "method": "snapshot"})

    with _fake_browser():
        with pytest.raises(run_state.SmokeFirstFailed) as ei:
            course._build_outline(
                "s", cb.load_selectors(), plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
                resume=False, done_lessons=set(),
                add_lesson=failing_first_add_lesson, write_receipt=lambda root, rc: None)

    # Exactly ONE lesson attempted (the smoke) — "Setup"/"First" never ran.
    assert calls == [("Welcome", "Intro")]
    assert ei.value.step.startswith("M4:smoke:")


def test_build_outline_resume_skips_done_lessons_and_still_smokes_the_first_new_one():
    plan = _course_plan([("Welcome", ["Intro", "Setup"]), ("Build", ["First"])])
    done = {l["slug"] for m in plan["modules"] for l in m["lessons"]
           if m["title"] == "Welcome" and l["title"] == "Intro"}
    calls = []

    def fake_add_lesson(session, sels, module, lesson, evidence_root, shot_n, gov, keep):
        calls.append(lesson["title"])
        return course._receipt("lesson", lesson["slug"], "created",
                               verify={"present_in_outline": True})

    with _fake_browser():
        res = course._build_outline(
            "s", cb.load_selectors(), plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
            resume=True, done_lessons=done,
            add_lesson=fake_add_lesson, write_receipt=lambda *a: None)

    assert calls == ["Setup", "First"]                       # Intro skipped (already done)
    assert any(s.startswith("M4:resume-skip:") for s in res["steps_done"])


def test_course_live_build_calls_ghl_run_state_smoke_first_call_site():
    """Call-site test for the COURSE path (spec 'smoke_first() is called by
    the ... AND course paths')."""
    plan = _course_plan([("Welcome", ["Intro", "Setup"])])
    seen_steps = []
    orig = run_state.smoke_first

    def spy(step, create_fn, verify_fn, *, log=None):
        seen_steps.append(step)
        return orig(step, create_fn, verify_fn, log=log)

    def fake_add_lesson(session, sels, module, lesson, evidence_root, shot_n, gov, keep):
        return course._receipt("lesson", lesson["slug"], "created",
                               verify={"present_in_outline": True})

    run_state.smoke_first = spy
    try:
        with _fake_browser():
            course._build_outline(
                "s", cb.load_selectors(), plan, "/tmp/x", [0], cb._NoopGovernor(), cb._NoopKeepalive(),
                resume=False, done_lessons=set(),
                add_lesson=fake_add_lesson, write_receipt=lambda *a: None)
    finally:
        run_state.smoke_first = orig
    assert len(seen_steps) == 1 and seen_steps[0].startswith("M4:smoke:")


# ═══════════════════════════════════════════════════════════════════════════
# (c) survival-probe target list — schema declares community/course/channel
# ═══════════════════════════════════════════════════════════════════════════
def test_iframe_survival_targets_schema_declares_new_object_types():
    path = os.path.join(TOOLS, "iframe-survival-targets.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    schema_desc = doc["_schema"]["object_type"]
    for obj in ("community", "course", "channel"):
        assert obj in schema_desc, f"{obj} not declared in iframe-survival-targets.json _schema"
    # The array itself intentionally still ships empty — no live client URLs
    # belong in this repo; real entries are populated at LIVE-PROOF time.
    assert doc["targets"] == []


def test_run_iframe_survival_check_accepts_new_object_types_untouched():
    """run_iframe_survival_check() never branches on object_type — proves the
    community/course/channel target types work through the EXISTING check
    with zero code changes needed there."""
    survived_html = '<html><iframe src="https://x.leadconnectorhq.com/y"></iframe></html>'
    targets = [
        {"id": "community.portal.published", "url": "https://x/c", "object_type": "community"},
        {"id": "course.preview.published", "url": "https://x/co", "object_type": "course"},
        {"id": "channel.portal.published", "url": "https://x/ch", "object_type": "channel"},
    ]
    report = canary.run_iframe_survival_check(targets, lambda url: survived_html)
    assert report.summary()["clean"] is True
    assert report.summary()["total_targets"] == 3


# ═══════════════════════════════════════════════════════════════════════════
# (c) seeded drift -> exactly ONE card, idempotent across repeats
# ═══════════════════════════════════════════════════════════════════════════
def test_seeded_iframe_drift_on_community_course_channel_files_one_card_each_idempotent():
    stripped_html = "<html><p>no iframe here</p></html>"
    targets = [
        {"id": "community.portal.published", "url": "https://x/c", "object_type": "community"},
        {"id": "course.preview.published", "url": "https://x/co", "object_type": "course"},
        {"id": "channel.portal.published", "url": "https://x/ch", "object_type": "channel"},
    ]
    with tempfile.TemporaryDirectory() as tmp:
        cards = []

        def notifier(payload):
            cards.append(payload)

        rep1 = canary.run_iframe_survival_check(
            targets, lambda url: stripped_html, evidence_root=tmp, board_notifier=notifier)
        rep2 = canary.run_iframe_survival_check(
            targets, lambda url: stripped_html, evidence_root=tmp, board_notifier=notifier)

        # The scan itself still honestly reports the ongoing miss BOTH times.
        assert rep1.summary()["clean"] is False and len(rep1.summary()["misses"]) == 3
        assert rep2.summary()["clean"] is False and len(rep2.summary()["misses"]) == 3

        # But exactly ONE card per target across the two repeated scans —
        # never a duplicate on the second pass.
        assert len(cards) == 3
        carded_ids = {c["target"] for c in cards}
        assert carded_ids == {"community.portal.published", "course.preview.published",
                              "channel.portal.published"}
        assert all(c["prefix"] == "VERIFY-FAIL" for c in cards)   # reused taxonomy, no 8th value


def test_seeded_selector_drift_via_community_course_probe_files_one_card_idempotent():
    """The companion SELECTOR-MISS-taxonomy path (probe_community_course_selectors):
    seed a regression on a REAL locked anchor and prove the same idempotent
    single-card discipline, using the actual selectors-live-communities-
    courses.json loaded via ghl_community_builder.load_selectors()."""
    locked = _fully_locked_selectors()
    baseline = canary.probe_community_course_selectors(locked)
    assert baseline.summary()["clean"] is True

    drifted = copy.deepcopy(locked)
    drifted["community"]["group_nav"]["add_channel_control"]["status"] = "capture-pending"

    with tempfile.TemporaryDirectory() as tmp:
        cards = []
        rep1 = canary.probe_community_course_selectors(
            drifted, evidence_root=tmp, board_notifier=lambda p: cards.append(p))
        rep2 = canary.probe_community_course_selectors(
            drifted, evidence_root=tmp, board_notifier=lambda p: cards.append(p))

        assert "community.group_nav.add_channel_control" in rep1.summary()["misses"]
        assert "community.group_nav.add_channel_control" in rep2.summary()["misses"]
        assert len(cards) == 1                      # idempotent — not 2
        assert cards[0]["prefix"] == canary.BOARD_NOTE_SELECTOR_MISS
        assert cards[0]["prefix"] == "SELECTOR-MISS"


def test_notify_once_is_the_shared_dedup_primitive_both_checks_route_through():
    with tempfile.TemporaryDirectory() as tmp:
        not_yet_created = os.path.join(tmp, "fresh-evidence-root")
        fired = []
        r1 = canary.notify_once(not_yet_created, "K:1", lambda p: fired.append(p), {})
        # A not-yet-created evidence_root is created on demand by notify_once
        # (os.makedirs) — this must not raise, and the FIRST call fires.
        assert r1 is True
        assert len(fired) == 1
        r2 = canary.notify_once(not_yet_created, "K:1", lambda p: fired.append(p), {})
        assert r2 is False and len(fired) == 1     # same key, same root -> deduped


# ═══════════════════════════════════════════════════════════════════════════
# module-level selftests still pass with the U106 additions wired in
# ═══════════════════════════════════════════════════════════════════════════
@pytest.mark.parametrize("mod", [run_state, cb, course, canary])
def test_module_selftest_still_passes(mod):
    assert mod._selftest() == 0

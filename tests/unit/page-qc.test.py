#!/usr/bin/env python3
"""Unit tests for shared-utils/page_qc.py — Page-QC v2, the SEMANTIC scorer (U25/B-U11).

Locks down the six binary-acceptance items from the spec:
  (a) scorecard schema-validates and is present for a fixture build
  (b) a seeded flat-copy/voiceless fixture PASSES the FAB-QC structural shape but
      FAILS Page-QC on S2/S3 — proof the semantic layer adds signal FAB-QC cannot
  (c) a broken-image fixture hard-misses S4 (deterministic, key-free)
  (d) a no-key box yields SKIP + a qc_starved-class operator visibility event,
      never a numeric score
  (f) a two-pass spread > 1.5 provably triggers a third pass + median
        (the 8.5-threshold CI-guard item (e) is covered by
         tests/unit/page-qc-gate-guard.test.sh, not here)

Run:
    python3 tests/unit/page-qc.test.py
    or: pytest tests/unit/page-qc.test.py
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_SHARED_UTILS = _REPO_ROOT / "shared-utils"
assert _SHARED_UTILS.is_dir(), f"shared-utils not found at {_SHARED_UTILS}"
sys.path.insert(0, str(_SHARED_UTILS))

# fab_qc must be import-able as a top-level module (page_qc does `import fab_qc`).
_fab_spec = importlib.util.spec_from_file_location("fab_qc", _SHARED_UTILS / "fab_qc.py")
fab_qc = importlib.util.module_from_spec(_fab_spec)
sys.modules["fab_qc"] = fab_qc
_fab_spec.loader.exec_module(fab_qc)

_pqc_spec = importlib.util.spec_from_file_location("page_qc", _SHARED_UTILS / "page_qc.py")
page_qc = importlib.util.module_from_spec(_pqc_spec)
sys.modules["page_qc"] = page_qc
_pqc_spec.loader.exec_module(page_qc)


def _funnel_fixture(**overrides) -> dict:
    base = {
        "artifact": {"pages": [
            {"page_id": "p1", "copy": {
                "hero": ("Get our free funnel swipe file today and finally grow the email list "
                         "you have put off building for months. Inside you get the exact opt-in "
                         "page, the seven-email follow-up sequence, and the pre-launch checklist "
                         "we use to ship a converting funnel in a single focused afternoon, with "
                         "no guesswork and nothing left to chance for a busy founder."),
                "form": "Enter your best email for instant access"}},
        ]},
        "template": {"copyFramework": {"primaryPersona": "Russell Brunson"}},
        "conversion_goal": "email opt-in",
        "blend_directive": {"voice": "russell-brunson", "attributes": ["urgent", "story-driven"]},
        "seo_panel": {"keyword": "funnel swipe file", "canonical": "https://x/optin"},
    }
    base.update(overrides)
    return base


def _high_judge(_dim, _payload):
    return {"score": 9.0, "reasoning": "strong on every axis"}


class TestPageQcCore(unittest.TestCase):
    def test_weights_sum_to_100_and_threshold_8_5(self):
        self.assertEqual(sum(page_qc.W.values()), 100)
        self.assertEqual(page_qc.THRESHOLD, 8.5)

    def test_healthy_build_passes_and_validates_schema(self):
        r = page_qc.grade(_funnel_fixture(), judge_fn=_high_judge)
        self.assertTrue(r["available"])
        self.assertTrue(r["passed"], r)
        self.assertGreaterEqual(r["score"], 8.5)
        self.assertEqual(r["hard_misses"], [])
        self.assertTrue(page_qc.validate_schema(r))
        self.assertEqual(len(r["dimensions"]), 6)

    # ---- (a) schema presence for a fixture build --------------------------
    def test_schema_present_for_every_fixture_build(self):
        for judge in (_high_judge, lambda d, p: {"score": 4.0, "reasoning": "meh"}):
            r = page_qc.grade(_funnel_fixture(), judge_fn=judge)
            self.assertIn("dimensions", r)
            self.assertTrue(page_qc.validate_schema(r))

    # ---- (b) flat/voiceless copy fails Page-QC on S2/S3 while a FAB-QC-style
    #          structural gate (grammatical, placeholder-free, floor-clearing copy)
    #          would PASS — the proof the semantic layer adds signal. -----------
    def test_flat_voiceless_copy_passes_fab_qc_shape_fails_page_qc_s2_s3(self):
        inp = _funnel_fixture()
        # FAB-QC's own structural gate would PASS this: grammatical, no placeholder
        # tokens, clears the word floor. Confirm that independently via fab_qc D2.
        fab_texts = fab_qc._texts_of(inp["artifact"])  # noqa: SLF001
        self.assertFalse(any(fab_qc._has_placeholder(t) for t in fab_texts))  # noqa: SLF001
        self.assertGreaterEqual(sum(len(t.split()) for t in fab_texts), fab_qc._BODY_SLOT_FLOOR)  # noqa: SLF001

        def flat_voiceless_judge(dim, _payload):
            if dim in ("S2", "S3"):
                return {"score": 2.0, "reasoning": "grammatical but flat, no persona voice"}
            return {"score": 9.0, "reasoning": "fine"}

        r = page_qc.grade(inp, judge_fn=flat_voiceless_judge)
        self.assertFalse(r["passed"])
        self.assertIn("S3 Voice/persona fidelity", r["hard_misses"])
        s2 = next(d for d in r["dimensions"] if d["name"] == "S2 Emotional strength")
        self.assertLessEqual(s2["score"], 3.0)

    # ---- (c) broken-image fixture hard-misses S4 (deterministic, key-free) ----
    def test_broken_image_hard_misses_s4_deterministically(self):
        inp = _funnel_fixture(image_manifest=[
            {"cdn_url": "https://cdn.example.com/hero.png", "http_status": 404},
        ])
        # Even with NO judge at all, the deterministic broken-image finding is
        # visible in deterministic_findings (never silently lost on a no-key box).
        skip = page_qc.grade(inp, env={})
        self.assertFalse(skip["available"])
        self.assertEqual(skip["deterministic_findings"]["broken_images"],
                          ["https://cdn.example.com/hero.png"])

        r = page_qc.grade(inp, judge_fn=_high_judge)
        self.assertFalse(r["passed"])
        self.assertIn("S4 Image quality & congruence", r["hard_misses"])
        s4 = next(d for d in r["dimensions"] if d["name"].startswith("S4"))
        self.assertTrue(s4["hard_miss"])
        self.assertEqual(s4["score"], 0.0)

    def test_broken_image_dom_marker_also_detected(self):
        inp = _funnel_fixture(dom_html='<img data-img-broken="true" src="/x/broken.png">')
        found = page_qc._detect_broken_images(inp)  # noqa: SLF001
        self.assertEqual(found, ["/x/broken.png"])

    # ---- (d) no-key box -> SKIP, never a numeric score, + qc_starved event ----
    def test_no_key_box_skips_honestly_never_fabricates(self):
        r = page_qc.grade(_funnel_fixture(), env={})
        self.assertFalse(r["available"])
        self.assertIsNone(r["score"])
        self.assertIsNone(r["passed"])
        self.assertEqual(r["dimensions"], [])
        self.assertEqual(r["verdict"], "page_qc: unavailable (no judge key)")
        self.assertTrue(page_qc.validate_schema(r))

    def test_has_judge_key_respects_injected_env_only(self):
        self.assertFalse(page_qc.has_judge_key(env={}))
        self.assertTrue(page_qc.has_judge_key(env={"OLLAMA_CLOUD_API_KEY": "set"}))
        self.assertTrue(page_qc.has_judge_key(env={"OPENROUTER_API_KEY": "set"}))

    def test_qc_starved_event_posted_on_skip(self):
        captured = {}

        class _FakeBoard:
            @staticmethod
            def post_activity(task_id, activity_type, message, metadata=None, env=None):
                captured["task_id"] = task_id
                captured["activity_type"] = activity_type
                captured["message"] = message
                captured["metadata"] = metadata
                return True

        ok = page_qc.post_qc_starved_event("task-123", board=_FakeBoard())
        self.assertTrue(ok)
        self.assertEqual(captured["task_id"], "task-123")
        self.assertEqual(captured["activity_type"], "updated")
        self.assertTrue(captured["metadata"]["qc_starved"])
        self.assertEqual(captured["metadata"]["qc_gate"], "page-qc")

    def test_qc_starved_event_empty_task_id_is_noop(self):
        self.assertFalse(page_qc.post_qc_starved_event("", board=object()))

    # ---- (f) two-pass spread > 1.5 triggers a third pass + median -------------
    def test_two_pass_spread_triggers_third_pass_and_median(self):
        calls = {"n": 0}

        def spread_judge(_dim, _payload):
            calls["n"] += 1
            seq = {1: 9.0, 2: 6.0, 3: 8.0}   # |9-6|=3 > 1.5 -> 3rd pass -> median(9,6,8)=8
            return {"score": seq.get(calls["n"], 8.0), "reasoning": f"pass{calls['n']}"}

        r = page_qc._score_via_judge("S1", {}, spread_judge)  # noqa: SLF001
        self.assertEqual(calls["n"], 3)
        self.assertEqual(r["score"], 8.0)

    def test_within_spread_uses_two_passes_only(self):
        calls = {"n": 0}

        def tight_judge(_dim, _payload):
            calls["n"] += 1
            seq = {1: 8.0, 2: 9.0}           # |8-9|=1 <= 1.5 -> no 3rd pass -> median=8.5
            return {"score": seq[calls["n"]], "reasoning": "ok"}

        r = page_qc._score_via_judge("S1", {}, tight_judge)  # noqa: SLF001
        self.assertEqual(calls["n"], 2)
        self.assertEqual(r["score"], 8.5)

    def test_third_pass_itself_unparseable_falls_back_to_median_of_two(self):
        calls = {"n": 0}

        def bad_third_judge(_dim, _payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return {"score": 9.0, "reasoning": "p1"}
            if calls["n"] == 2:
                return {"score": 6.0, "reasoning": "p2"}
            return {"error": "provider timeout"}   # 3rd pass fails to parse

        r = page_qc._score_via_judge("S1", {}, bad_third_judge)  # noqa: SLF001
        self.assertEqual(calls["n"], 3)
        self.assertEqual(r["score"], 7.5)   # median of the two VALID passes (9, 6)

    def test_judge_failure_with_key_present_is_fail_closed_not_skip(self):
        """A judge that NEVER returns a valid score (key present, model malfunction)
        is a fail-closed HARD MISS for that dimension — not a silent SKIP. The key
        being present means an unparseable response is a real gate problem."""
        def always_broken(_dim, _payload):
            return {"error": "500 upstream"}

        # include a screenshot so S4 also goes through the judge (no screenshot ->
        # S4 short-circuits to N/A=10 without ever calling judge_fn, by design).
        r = page_qc.grade(_funnel_fixture(screenshot_b64="Zm9v"), judge_fn=always_broken)
        self.assertTrue(r["available"])
        self.assertFalse(r["passed"])
        self.assertEqual(len(r["hard_misses"]), 6)  # every dimension fail-closed


class TestPageQcS1HardMiss(unittest.TestCase):
    def test_s1_le_3_is_hard_miss(self):
        def low_s1(dim, _p):
            return {"score": 2.5, "reasoning": "no offer clarity"} if dim == "S1" else {"score": 9.0, "reasoning": "ok"}

        r = page_qc.grade(_funnel_fixture(), judge_fn=low_s1)
        self.assertIn("S1 Conversion likelihood", r["hard_misses"])


class TestPageQcS3DegradesWithoutBlend(unittest.TestCase):
    def test_no_blend_directive_degrades_never_hard_misses(self):
        inp = _funnel_fixture()
        inp.pop("blend_directive")

        def low_everything(_dim, _p):
            return {"score": 2.0, "reasoning": "low"}

        r = page_qc.grade(inp, judge_fn=low_everything)
        # S1 <= 3 is ALWAYS a hard miss; S3 <= 3 is a hard miss ONLY with a blend
        # directive present — confirm S3 itself is NOT hard-missed here.
        self.assertNotIn("S3 Voice/persona fidelity", r["hard_misses"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

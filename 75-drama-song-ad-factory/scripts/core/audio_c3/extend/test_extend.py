#!/usr/bin/env python3
"""U-GEN322: the top_up driver's own test - the file suno_extend.py:52 promises.

``top_up`` is the finished extend-to-exact-length driver the module documents
("Drive Suno extend until the take is exactly the target length"). No
production stage calls it (there is no extend stage: batch_mode STAGES has 12
rows and none extends; every extend plan in the tree - length_formula
``extend_plan``, music_director ``build_extend_request`` - is a planner with no
executor). This file pins the driver's contract so that whichever way the
driver's fate is decided - wired to a paid path, or deleted - its behaviour is
proven before it is touched:

  * a take at or above the target never spends an extend round;
  * a short take is driven to EXACTLY the target, round by round, and the
    delivered timing map ends on the target;
  * every round's ``continue_at`` sits strictly inside its source take;
  * every failure is closed: no ``delivered_s`` and no timing map when the
    target is not reached;
  * the package re-export (``audio_c3.extend.top_up``) is the same function.

``extend_fn`` is a stub in every test: zero provider calls, no network.

Run: python3 test_extend.py
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                       # this module
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))   # scripts/core, for audio_c3.*

import suno_extend as S                        # noqa: E402


class Stub:
    """A scripted stand-in for the dispatch transport: payloads in, takes out."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, payload):
        self.calls.append(payload)
        return self.results.pop(0)


class TopUp(unittest.TestCase):
    def test_take_at_target_spends_no_round(self):
        fn = Stub()
        r = S.top_up(300.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual((r["status"], r["action"], r["extend_rounds"]), ("ok", "none", 0))
        self.assertEqual(r["delivered_s"], 300.0)
        self.assertEqual(fn.calls, [])                       # never called
        self.assertEqual(r["timing_map"]["span_end_s"], 300.0)

    def test_long_take_is_trimmed_not_extended(self):
        fn = Stub()
        r = S.top_up(305.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual((r["status"], r["extend_rounds"]), ("ok", 0))
        self.assertEqual(r["delivered_s"], 300.0)
        self.assertEqual(r["trimmed_s"], 5.0)
        self.assertEqual(fn.calls, [])

    def test_short_take_reaches_the_target_in_one_round(self):
        # The reference receipt: a 282 s take topped up to 300 s.
        fn = Stub({"duration_s": 300.0, "audio_id": "a2"})
        r = S.top_up(282.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual((r["status"], r["action"], r["extend_rounds"]), ("ok", "extend", 1))
        self.assertEqual(r["delivered_s"], 300.0)
        self.assertEqual(r["trimmed_s"], 0.0)
        self.assertEqual(r["timing_map"]["span_end_s"], 300.0)
        self.assertEqual([s["label"] for s in r["timing_map"]["segments"]],
                         ["take", "extend-round-1"])
        self.assertEqual(len(fn.calls), 1)
        # the catalog was read for a real round (endpoint/model/version), not hardcoded
        self.assertEqual(fn.calls[0]["input"]["model"], S.DEFAULT_EXTEND_VERSION)
        self.assertTrue(fn.calls[0]["endpoint"])

    def test_every_round_continues_strictly_inside_its_source(self):
        fn = Stub({"duration_s": 290.0, "audio_id": "a2"},
                  {"duration_s": 296.0, "audio_id": "a3"},
                  {"duration_s": 306.0, "audio_id": "a4"})
        r = S.top_up(282.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual((r["status"], r["extend_rounds"]), ("ok", 3))
        self.assertEqual(r["delivered_s"], 300.0)
        self.assertEqual(r["trimmed_s"], 6.0)               # 306 produced, 300 kept
        sources = [282.0, 290.0, 296.0]
        for call, src in zip(fn.calls, sources):
            ca = call["input"]["continue_at"]
            self.assertLess(ca, src)                        # KIE: 0 < continueAt < duration
            self.assertGreater(ca, 0.0)
        self.assertEqual(r["timing_map"]["span_end_s"], 300.0)

    def test_no_progress_fails_closed(self):
        fn = Stub({"duration_s": 282.0, "audio_id": "a2"})
        r = S.top_up(282.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual(r["status"], "extend-no-progress")
        self.assertNotIn("delivered_s", r)                  # never a short master
        self.assertNotIn("timing_map", r)

    def test_missing_audio_id_fails_closed(self):
        fn = Stub({"duration_s": 290.0})                    # no id for a further round
        r = S.top_up(282.0, 300.0, fn, "a1", "https://cb.invalid/x")
        self.assertEqual(r["status"], "extend-no-audio-id")
        self.assertNotIn("delivered_s", r)
        self.assertNotIn("timing_map", r)

    def test_round_cap_fails_closed(self):
        fn = Stub({"duration_s": 290.0, "audio_id": "a2"},
                  {"duration_s": 296.0, "audio_id": "a3"})
        r = S.top_up(282.0, 300.0, fn, "a1", "https://cb.invalid/x", max_rounds=2)
        self.assertEqual(r["status"], "extend-unresolved")
        self.assertEqual(r["extend_rounds"], 2)
        self.assertNotIn("delivered_s", r)
        self.assertNotIn("timing_map", r)

    def test_a_non_callable_extender_is_refused(self):
        with self.assertRaises(S.ExtendError):
            S.top_up(282.0, 300.0, None, "a1", "https://cb.invalid/x")

    def test_package_reexport_keeps_the_driver_alive(self):
        # __init__.py:26 imports it and __init__.py:47 lists it in __all__:
        # those two lines are the whole reason the driver is still here.
        import audio_c3.extend as pkg
        self.assertIn("top_up", pkg.__all__)
        self.assertTrue(callable(pkg.top_up))
        r = pkg.top_up(300.0, 300.0, Stub(), "a1", "https://cb.invalid/x")
        self.assertEqual((r["status"], r["delivered_s"]), ("ok", 300.0))


class Catalog(unittest.TestCase):
    """The one work copy suno_extend reads: 68-kie-audio/models.json."""

    def test_work_copy_resolves_and_carries_suno_extend(self):
        cats = S.catalog()
        self.assertIn(S.EXTEND_CATALOG_ID, cats)
        self.assertTrue(S._catalog_path().is_file(), S._catalog_path())
        self.assertEqual(S.route_model(), "ai-music-api/extend")
        self.assertTrue(S.endpoint().startswith("/api/"))
        self.assertIn(S.DEFAULT_EXTEND_VERSION, S.version_enum())


class TimingMap(unittest.TestCase):
    def test_a_map_that_does_not_reach_the_length_is_refused(self):
        with self.assertRaises(S.ExtendError):
            S.timing_map([("take", 100.0)], 120.0)

    def test_a_map_ends_on_the_target(self):
        m = S.timing_map([("take", 282.0), ("extend", 18.0)], 300.0)
        self.assertEqual((m["span_start_s"], m["span_end_s"]), (0.0, 300.0))
        self.assertEqual(m["segment_count"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)

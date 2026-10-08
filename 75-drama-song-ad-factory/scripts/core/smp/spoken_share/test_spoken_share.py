#!/usr/bin/env python3
"""Mocked tests for the SMP weekly ad's D15 spoken-share rule (AF-SMP-U2).

Owner: Decision log 36-37 applied to Skill 35 (2026-10-07), plan 6.15.

Covers: target 45 percent / band 40-55 for every length and style; rap
counted as spoken; first sung line within about 10 seconds; the rule
replaces every other spoken-share limit inside ``core/smp/``; fail-closed
measurements; zero paid calls (mocked socket, no transport import); no
media files and no operator paths in the owned dir.

Dual-mode -- plain python3 and pytest:

    python3 core/smp/spoken_share/test_spoken_share.py
    python3 -m pytest core/smp/spoken_share/
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import spoken_share as M  # noqa: E402  module under test

OWNED_DIR = HERE
MEDIA_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
             ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
             ".webm", ".srt")
# Source substrings that would put a transport, a spend path or an operator
# path inside this owned directory (checked on the shipped module only).
# The operator-home needle is assembled at runtime so a scan of this
# directory for operator paths does not trip over the detector itself.
_OPERATOR_HOME = "/" + "Users/"
FORBIDDEN_SOURCE = (
    "urllib", "requests", "http.client", "socket", "subprocess", "ftplib",
    "telnetlib", "websocket", "spend_ledger", "openai", "kie.ai", "api.kie",
    "pm2", "expanduser", "/users/", "/home/", ".openclaw",
    _OPERATOR_HOME, "os.environ",
)
MODULE_SRC = os.path.join(OWNED_DIR, "spoken_share.py")
INIT_SRC = os.path.join(OWNED_DIR, "__init__.py")


def line(delivery, duration_s, start_s=None, line_id=None):
    """One planner line: duration always explicit, start optional."""
    out = {"delivery": delivery, "duration_s": duration_s}
    if start_s is not None:
        out["start_s"] = start_s
    if line_id is not None:
        out["line_id"] = line_id
    return out


def in_band_ad():
    """45.0% spoken, first sung at 5.0s -- the exact target, in band."""
    return [
        line("spoken", 5, 0.0, "opener"),
        line("sung", 55, 5.0, "hook"),
        line("spoken", 40, 60.0, "story"),
    ], 100.0


class ConstantsTests(unittest.TestCase):
    def test_owner_numbers_are_exact(self):
        self.assertEqual(M.SPOKEN_TARGET_PCT, 45)
        self.assertEqual(M.SPOKEN_MIN_PCT, 40)
        self.assertEqual(M.SPOKEN_MAX_PCT, 55)
        self.assertEqual(M.FIRST_SUNG_WITHIN_SECONDS, 10)

    def test_band_is_floor_then_ceiling(self):
        self.assertEqual(M.SPOKEN_BAND_PCT, (40, 55))
        self.assertEqual(M.SPOKEN_BAND_PCT,
                         (M.SPOKEN_MIN_PCT, M.SPOKEN_MAX_PCT))

    def test_rap_counts_as_spoken_and_never_as_sung(self):
        self.assertIn("rap", M.SPOKEN_DELIVERIES)
        self.assertIn("spoken", M.SPOKEN_DELIVERIES)
        self.assertEqual(M.SPOKEN_DELIVERIES, frozenset({"spoken", "rap"}))
        self.assertNotIn("rap", M.SUNG_DELIVERIES)
        self.assertEqual(M.DELIVERIES, ("spoken", "rap", "sung"))

    def test_one_band_for_every_length_and_style(self):
        # No per-length table: the retarget ships one band only.
        self.assertEqual(M.RETIRED_TABLE_NAMES,
                         ("D15_TARGETS", "SHARE_TARGETS_BY_LENGTH"))
        self.assertFalse([name for name in dir(M)
                          if name in M.RETIRED_TABLE_NAMES],
                         "a retired per-length table is still exported")

    def test_rule_identity_and_source(self):
        self.assertEqual(M.RULE_ID, "D15")
        self.assertEqual(M.STEP, "smp-weekly-drama-song")
        self.assertEqual(M.KIE_PATH, "Skill 74")
        self.assertIn("Decision log 36-37", M.SOURCE)
        self.assertIn("plan 6.15", M.SOURCE)
        self.assertIn("2026-10-07", M.SOURCE)

    def test_retired_bands_are_the_ones_the_rule_replaces(self):
        self.assertEqual(M.RETIRED_BAND_PCT, ((40, 70), (35, 40)))
        # built at import from the tuple, never stored as one literal
        self.assertTrue(M.STALE_PHRASES)
        for phrase in M.STALE_PHRASES:
            self.assertIsInstance(phrase, str)
            self.assertTrue(phrase)


class PlannerTextTests(unittest.TestCase):
    def test_planner_line_carries_every_requirement(self):
        text = M.planner_line()
        self.assertEqual(M.check_planner_text(text), [], text)
        self.assertIn("target 45%", text)
        self.assertIn("never more than 55%", text)
        self.assertIn("never less than 40%", text)
        self.assertIn("rap counts as spoken", text)
        self.assertIn("first sung line within about 10 seconds", text)

    def test_planner_line_states_the_short_opener(self):
        self.assertIn("short spoken opener", M.planner_line())

    def test_weekly_ad_limits_is_the_one_dict(self):
        limits = M.weekly_ad_limits()
        self.assertEqual(limits, {
            "step": "smp-weekly-drama-song",
            "rule": "D15",
            "target_pct": 45,
            "min_pct": 40,
            "max_pct": 55,
            "band_pct": [40, 55],
            "rap_counts_as_spoken": True,
            "first_sung_within_seconds": 10,
            "source": M.SOURCE,
        })
        self.assertIsInstance(limits["band_pct"], list)

    def test_limits_do_not_change_between_calls(self):
        self.assertEqual(M.weekly_ad_limits(), M.weekly_ad_limits())

    def test_missing_requirement_is_named(self):
        reasons = M.check_planner_text("spoken share target 45% only")
        joined = "\n".join(reasons)
        for needle in ("55 percent ceiling", "40 percent floor",
                       "counts rap as spoken",
                       "first sung line within about 10 seconds"):
            self.assertIn(needle, joined, reasons)
        self.assertNotIn("states the 45 percent target", joined)

    def test_retired_wording_in_a_planner_text_is_refused(self):
        retired = "%d-%d" % M.RETIRED_BAND_PCT[0]
        text = M.planner_line() + " spoken share band " + retired
        reasons = M.check_planner_text(text)
        self.assertTrue(any("retired limit wording present" in r
                            for r in reasons), reasons)
        self.assertIn(retired, M.find_stale_limits(text))

    def test_check_and_scan_reject_non_text(self):
        for bad in (None, 45, ["45"]):
            with self.assertRaises(TypeError):
                M.check_planner_text(bad)
            with self.assertRaises(TypeError):
                M.find_stale_limits(bad)
            with self.assertRaises(TypeError):
                M.find_competing_limits(bad)


class MeasurementTests(unittest.TestCase):
    def test_spoken_and_rap_both_count_sung_does_not(self):
        lines = [line("spoken", 10), line("rap", 5), line("sung", 80)]
        self.assertEqual(M.spoken_seconds(lines), 15.0)

    def test_line_without_a_delivery_defaults_to_spoken(self):
        self.assertEqual(M.spoken_seconds([{"duration_s": 7}]), 7.0)

    def test_delivery_label_is_normalized(self):
        self.assertTrue(M.counts_as_spoken("  RAP "))
        self.assertTrue(M.counts_as_spoken("Spoken"))
        self.assertFalse(M.counts_as_spoken("sung"))
        self.assertEqual(M.normalize_delivery(" Melodic "), "melodic")

    def test_duration_falls_back_to_start_and_end(self):
        self.assertEqual(M.spoken_seconds(
            [{"delivery": "spoken", "start_s": 4, "end_s": 14}]), 10.0)

    def test_share_is_a_percent_of_runtime_at_one_decimal(self):
        lines, duration = in_band_ad()
        self.assertEqual(M.spoken_share_pct(lines, duration), 45.0)
        self.assertEqual(M.spoken_share_pct(
            [line("spoken", 1), line("sung", 3)], 4.0), 25.0)
        # 1 dp, not a float tail
        self.assertEqual(M.spoken_share_pct(
            [line("spoken", 1), line("sung", 2)], 3.0), 33.3)

    def test_fail_closed_measurements(self):
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_seconds(["not a line"])
        self.assertEqual(ctx.exception.code, "line_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_seconds([{"line_id": "x", "delivery": "spoken"}])
        self.assertEqual(ctx.exception.code, "line_duration_missing")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_seconds([{"duration_s": "soon"}])
        self.assertEqual(ctx.exception.code, "line_duration_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_seconds([{"duration_s": -1}])
        self.assertEqual(ctx.exception.code, "line_duration_negative")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_share_pct([line("spoken", 10)], 0)
        self.assertEqual(ctx.exception.code, "duration_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.spoken_share_pct([line("spoken", 10)], "long")
        self.assertEqual(ctx.exception.code, "duration_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.normalize_delivery("")
        self.assertEqual(ctx.exception.code, "delivery_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.normalize_delivery(None)
        self.assertEqual(ctx.exception.code, "delivery_invalid")

    def test_error_message_carries_the_code(self):
        try:
            M.spoken_share_pct([line("spoken", 1)], 0)
        except M.SpokenShareError as exc:
            self.assertIn("duration_invalid", str(exc))
        else:  # pragma: no cover
            self.fail("expected a refusal")


class FirstSungTests(unittest.TestCase):
    def test_no_sung_line_returns_none(self):
        self.assertIsNone(M.first_sung_start(
            [line("spoken", 10), line("rap", 10)]))

    def test_rap_never_satisfies_the_rule(self):
        self.assertIsNone(M.first_sung_start([line("rap", 20, 0.0)]))

    def test_first_sung_is_the_earliest_sung_start(self):
        lines = [line("sung", 10, 3.0), line("sung", 5, 40.0),
                 line("spoken", 45, 45.0)]
        self.assertEqual(M.first_sung_start(lines), 3.0)

    def test_start_falls_back_to_the_running_cursor(self):
        lines = [line("spoken", 6), line("sung", 10)]
        self.assertEqual(M.first_sung_start(lines), 6.0)

    def test_bad_start_is_refused(self):
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.first_sung_start([{"delivery": "sung", "start_s": "later",
                                 "duration_s": 3}])
        self.assertEqual(ctx.exception.code, "line_start_invalid")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.first_sung_start([{"delivery": "sung", "start_s": 0,
                                 "duration_s": 3}, "junk"])
        self.assertEqual(ctx.exception.code, "line_invalid")

    def test_measures_one_ad_only(self):
        self.assertIsNone(M.first_sung_start([]))


class EvaluateTests(unittest.TestCase):
    def test_in_band_ad_passes(self):
        lines, duration = in_band_ad()
        out = M.evaluate(lines, duration)
        self.assertEqual(out["outcome"], "ok", out["reasons"])
        self.assertEqual(out["reasons"], [])
        self.assertEqual(out["spoken_pct"], 45.0)
        self.assertEqual(out["band_pct"], [40, 55])
        self.assertEqual(out["target_pct"], 45)
        self.assertEqual(out["first_sung_at_s"], 5.0)
        self.assertIs(out["rap_counts_as_spoken"], True)
        self.assertEqual(out["step"], "smp-weekly-drama-song")
        self.assertEqual(out["source"], M.SOURCE)

    def test_band_boundaries_are_inclusive(self):
        # exactly on the floor (40%) -- hook still lands at 10s: passes
        floor = [line("spoken", 10, 0.0), line("sung", 60, 10.0),
                 line("spoken", 30, 70.0)]
        out = M.evaluate(floor, 100.0)
        self.assertEqual(out["spoken_pct"], 40.0)
        self.assertEqual(out["outcome"], "ok", out["reasons"])
        # exactly on the ceiling (55%) -- passes
        ceil = [line("spoken", 10, 0.0), line("sung", 45, 10.0),
                line("spoken", 45, 55.0)]
        out = M.evaluate(ceil, 100.0)
        self.assertEqual(out["spoken_pct"], 55.0)
        self.assertEqual(out["outcome"], "ok", out["reasons"])

    def test_one_step_outside_the_band_fails(self):
        under = [line("spoken", 9, 0.0), line("sung", 61, 10.0),
                 line("spoken", 30, 71.0)]
        self.assertEqual(M.evaluate(under, 100.0)["spoken_pct"], 39.0)
        self.assertEqual(M.evaluate(under, 100.0)["outcome"], "fail")
        over = [line("spoken", 11, 0.0), line("sung", 44, 11.0),
                line("spoken", 45, 55.0)]
        self.assertEqual(M.evaluate(over, 100.0)["spoken_pct"], 56.0)
        self.assertEqual(M.evaluate(over, 100.0)["outcome"], "fail")

    def test_below_the_floor_fails(self):
        lines = [line("sung", 80, 0.0), line("spoken", 20, 80.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("below the 40% floor", out["reasons"][0])
        self.assertIn("20.0%", out["reasons"][0])

    def test_above_the_ceiling_fails(self):
        lines = [line("spoken", 10, 0.0), line("sung", 40, 10.0),
                 line("spoken", 50, 50.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("above the 55% ceiling", out["reasons"][0])
        self.assertIn("60.0%", out["reasons"][0])

    def test_rap_is_counted_so_a_rap_heavy_ad_is_not_under_the_floor(self):
        # 5 spoken + 45 rap + 5 spoken = 55% spoken-style, hook at 5s: ok
        lines = [line("spoken", 5, 0.0), line("sung", 45, 5.0),
                 line("rap", 45, 50.0), line("spoken", 5, 95.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(M.spoken_seconds(lines), 55.0)
        self.assertEqual(out["spoken_pct"], 55.0)
        self.assertEqual(out["outcome"], "ok", out["reasons"])
        # the identical ad with rap sung instead measures 10%: under the floor
        no_rap = [lines[0], lines[1],
                  {"delivery": "sung", "duration_s": 45, "start_s": 50},
                  lines[3]]
        below = M.evaluate(no_rap, 100.0)
        self.assertEqual(below["spoken_pct"], 10.0)
        self.assertEqual(below["outcome"], "fail")
        self.assertTrue(any("below the 40% floor" in r
                            for r in below["reasons"]), below["reasons"])

    def test_first_sung_line_must_start_within_about_ten_seconds(self):
        # in band (45%) but the hook arrives at 15s
        lines = [line("spoken", 15, 0.0), line("sung", 55, 15.0),
                 line("spoken", 30, 70.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(out["spoken_pct"], 45.0)
        self.assertEqual(out["outcome"], "fail", out["reasons"])
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("first sung line at 15.0s, after the 10 second limit",
                      out["reasons"][0])

    def test_starting_exactly_at_ten_seconds_is_in_time(self):
        lines = [line("spoken", 10, 0.0), line("sung", 45, 10.0),
                 line("spoken", 45, 55.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(out["spoken_pct"], 55.0)
        self.assertEqual(out["outcome"], "ok", out["reasons"])

    def test_no_sung_line_is_its_own_failure(self):
        out = M.evaluate([line("spoken", 45), line("rap", 55)], 100.0)
        self.assertEqual(out["spoken_pct"], 100.0)
        self.assertEqual(out["outcome"], "fail")
        self.assertTrue(any("above the 55% ceiling" in r
                            for r in out["reasons"]), out["reasons"])
        self.assertTrue(any("no sung line" in r for r in out["reasons"]),
                        out["reasons"])
        self.assertIsNone(out["first_sung_at_s"])

    def test_every_reason_is_reported_at_once(self):
        # 90% spoken: over the ceiling *and* the hook arrives at 90s
        lines = [line("spoken", 90, 0.0), line("sung", 10, 90.0)]
        out = M.evaluate(lines, 100.0)
        self.assertEqual(out["outcome"], "fail")
        self.assertEqual(len(out["reasons"]), 2, out["reasons"])

    def test_evaluate_never_raises_on_a_merely_out_of_band_ad(self):
        lines, duration = in_band_ad()
        self.assertIsInstance(M.evaluate(lines, duration), dict)
        self.assertIsInstance(M.evaluate(
            [line("sung", 100, 0.0)], duration), dict)

    def test_evaluate_is_deterministic(self):
        lines, duration = in_band_ad()
        import json
        first = json.dumps(M.evaluate(lines, duration), sort_keys=True)
        second = json.dumps(M.evaluate(lines, duration), sort_keys=True)
        self.assertEqual(first, second)

    def test_evaluate_refuses_a_bad_runtime(self):
        lines, _ = in_band_ad()
        with self.assertRaises(M.SpokenShareError):
            M.evaluate(lines, 0)


class BudgetTests(unittest.TestCase):
    def test_sixty_second_ad_budget(self):
        budget = M.spoken_budget(60)
        self.assertEqual(budget, {"duration_s": 60.0, "target_s": 27.0,
                                  "min_s": 24.0, "max_s": 33.0,
                                  "first_sung_by_s": 10.0})

    def test_ninety_second_ad_budget_uses_the_same_band(self):
        budget = M.spoken_budget(90)
        self.assertEqual(budget["target_s"], 40.5)
        self.assertEqual(budget["min_s"], 36.0)
        self.assertEqual(budget["max_s"], 49.5)
        self.assertEqual(budget["first_sung_by_s"], 10.0)

    def test_budget_refuses_a_bad_runtime(self):
        for bad in (0, -1, "long"):
            with self.assertRaises(M.SpokenShareError):
                M.spoken_budget(bad)


class CompetingLimitTests(unittest.TestCase):
    def test_inline_limit_outside_this_package_is_named(self):
        text = "SPOKEN_SHARE_MAX = 62  # old\nOTHER_MAX = 1\n"
        found = M.find_competing_limits(text)
        self.assertEqual(len(found), 1, found)
        self.assertIn("SPOKEN_SHARE_MAX", found[0])

    def test_retired_band_constants_are_named(self):
        for name in M.RETIRED_TABLE_NAMES:
            text = "%s = (30, 70)\n" % name
            found = M.find_competing_limits(text)
            self.assertEqual(len(found), 1, found)
            self.assertIn(name, found[0])

    def test_own_constants_are_not_flagged_as_competing(self):
        text = ("SPOKEN_TARGET_PCT = 45\n"
                "SPOKEN_MIN_PCT = 40\n"
                "SPOKEN_MAX_PCT = 55\n"
                "SPOKEN_BAND_PCT = (40, 55)\n"
                "FIRST_SUNG_WITHIN_SECONDS = 10\n")
        self.assertEqual(M.find_competing_limits(text), [])

    def test_an_alias_without_an_inline_value_is_left_alone(self):
        text = "SPOKEN_SHARE_CEILING = SPOKEN_MAX_PCT\n"
        self.assertEqual(M.find_competing_limits(text), [])

    def test_unrelated_constants_are_not_limits(self):
        text = ("NEGATIVE_TAGS = 7\nLENGTHS = (60, 90)\n"
                "TEASER_MAX_SECONDS = 15.0\n")
        self.assertEqual(M.find_competing_limits(text), [])

    def test_a_plain_sung_share_constant_is_still_a_limit(self):
        found = M.find_competing_limits("SUNG_SHARE_PCT = 12\n")
        self.assertEqual(len(found), 1, found)

    def test_stale_phrases_cover_both_retired_bands(self):
        for phrase in M.STALE_PHRASES:
            self.assertEqual(M.find_stale_limits("x " + phrase + " y"),
                             [phrase], phrase)

    def test_clean_text_reports_nothing(self):
        self.assertEqual(M.find_stale_limits(M.planner_line()), [])
        self.assertEqual(M.find_competing_limits(M.planner_line()), [])


class ScannerTests(unittest.TestCase):
    """The retarget replaces every other limit instead of racing it."""

    def _tree(self, body):
        root = tempfile.mkdtemp(prefix="AF-SMP-U2-scan-")
        self.addCleanup(shutil.rmtree, root, True)
        pkg = os.path.join(root, "core", "smp", "other_module")
        os.makedirs(pkg)
        with open(os.path.join(pkg, "mod.py"), "w", encoding="utf-8") as h:
            h.write(body)
        return root

    def test_real_smp_tree_carries_no_other_limit(self):
        findings = M.scan_smp_modules()
        self.assertEqual(findings, {}, findings)

    def test_a_planted_competing_limit_is_named(self):
        root = self._tree("D15_TARGETS = (30, 70)\n")
        findings = M.scan_smp_modules(root)
        self.assertEqual(len(findings), 1, findings)
        path, hits = list(findings.items())[0]
        self.assertTrue(path.endswith(os.path.join("other_module", "mod.py")),
                        path)
        # the stale name and the inline value are both surfaced
        self.assertIn("D15_TARGETS = (30, 70)", hits, hits)

    def test_a_planted_retired_band_in_prose_is_named(self):
        root = self._tree("The weekly ad keeps a %d-%d percent band.\n"
                          % M.RETIRED_BAND_PCT[0])
        findings = M.scan_smp_modules(root)
        self.assertEqual(len(findings), 1, findings)

    def test_this_package_is_skipped_so_it_can_name_the_retired_bands(self):
        # the shipped module spells the retired table names in order to
        # detect them, so a naive text scan would flag its own file --
        # the scanner must skip this directory and still return clean.
        with open(MODULE_SRC, "r", encoding="utf-8") as handle:
            source = handle.read()
        stale_in_own_file = M.find_stale_limits(source)
        self.assertTrue(stale_in_own_file, "module no longer names them")
        self.assertEqual(M.scan_smp_modules(os.path.join(
            M.build_root(), "core", "smp")), {})

    def test_unreadable_file_is_reported_not_skipped(self):
        root = self._tree("clean = 1\n")
        with open(os.path.join(root, "core", "smp", "other_module",
                               "mod.py"), "wb") as h:
            h.write(b"\xff\xfe\x00broken")
        findings = M.scan_smp_modules(root)
        self.assertEqual(len(findings), 1, findings)
        self.assertTrue(list(findings.values())[0][0].startswith("unreadable"),
                        findings)

    def test_pycache_and_non_python_files_are_ignored(self):
        root = self._tree("clean = 1\n")
        os.makedirs(os.path.join(root, "core", "smp", "__pycache__"))
        with open(os.path.join(root, "core", "smp", "__pycache__",
                               "junk.py"), "w", encoding="utf-8") as h:
            h.write("SPOKEN_MAX_PCT = 99\n")
        with open(os.path.join(root, "core", "smp", "other_module",
                               "notes.bin"), "wb") as h:
            h.write(b"D15_TARGETS = (1, 2)")
        self.assertEqual(M.scan_smp_modules(root), {})

    def test_missing_root_reports_nothing_rather_than_raising(self):
        self.assertEqual(M.scan_smp_modules(
            os.path.join(tempfile.gettempdir(), "AF-SMP-U2-absent-root")),
            {})

    def test_build_root_is_found_by_walking_up(self):
        root = M.build_root()
        self.assertTrue(os.path.isdir(os.path.join(root, "core", "smp")),
                        root)
        self.assertTrue(os.path.isdir(os.path.join(root, "core", "smp",
                                                   "spoken_share")), root)


class ZeroSpendTests(unittest.TestCase):
    def test_no_network_even_with_socket_mocked_broken(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            lines, duration = in_band_ad()
            self.assertEqual(M.evaluate(lines, duration)["outcome"], "ok")
            self.assertEqual(M.scan_smp_modules(), {})
            self.assertEqual(M.spoken_budget(60)["target_s"], 27.0)

    def test_mocked_socket_is_actually_armed(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            with self.assertRaises(AssertionError):
                import socket  # noqa: F401
                socket.socket()

    def test_module_source_carries_no_transport_no_spend_no_operator_path(self):
        with open(MODULE_SRC, "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in FORBIDDEN_SOURCE:
            self.assertNotIn(needle, source, "source contains %r" % needle)
        self.assertNotIn("import " + "socket", source)
        # the only KIE path is named, never dialled
        self.assertIn(M.KIE_PATH, source)
        self.assertEqual(M.KIE_PATH, "Skill 74")

    def test_package_source_carries_no_transport(self):
        with open(INIT_SRC, "r", encoding="utf-8") as handle:
            source = handle.read()
        for needle in FORBIDDEN_SOURCE:
            self.assertNotIn(needle, source, "init contains %r" % needle)

    def test_module_never_opens_a_file_for_writing(self):
        with open(MODULE_SRC, "r", encoding="utf-8") as handle:
            source = handle.read()
        self.assertIsNone(re.search(r"open\(\s*['\"]w", source),
                          "module opens a file for writing")

    def test_owned_dir_holds_no_media_files(self):
        for name in sorted(os.listdir(OWNED_DIR)):
            self.assertFalse(name.lower().endswith(MEDIA_EXT),
                             "media file in owned dir: %s" % name)

    def test_owned_dir_holds_only_this_package(self):
        # .pytest_cache / __pycache__ are the runners' own artifacts.
        allowed = {"__init__.py", "spoken_share.py", "test_spoken_share.py",
                   "__pycache__", ".pytest_cache", "README.md"}
        unexpected = [n for n in sorted(os.listdir(OWNED_DIR))
                      if n not in allowed]
        self.assertEqual(unexpected, [], unexpected)

    def test_shipped_files_carry_no_operator_path(self):
        for path in (MODULE_SRC, INIT_SRC):
            with open(path, "r", encoding="utf-8") as handle:
                source = handle.read()
            for needle in (_OPERATOR_HOME, "/home/", ".openclaw",
                           "expanduser"):
                self.assertNotIn(needle, source,
                                 "%s contains %r" % (path, needle))

    def test_zero_paid_calls_helper_surface_is_pure(self):
        # the numbers this planner reads are arithmetic, not a quote
        self.assertEqual(M.spoken_budget(120)["target_s"], 54.0)
        self.assertEqual(M.SPOKEN_TARGET_PCT, 45)


class ShadowCompatTests(unittest.TestCase):
    """This package and core/spoken_share both answer to ``spoken_share``.

    pytest puts ``core/smp`` on ``sys.path``, so an ``import spoken_share``
    anywhere in the session can land here. Every name the canonical package
    hands to its readers must then still exist, carrying the same rule.
    """

    def test_fraction_names_match_the_percent_rule(self):
        self.assertEqual(M.TARGET, 0.45)
        self.assertEqual(M.FLOOR, 0.40)
        self.assertEqual(M.CAP, 0.55)
        self.assertEqual(M.TARGET, M.SPOKEN_TARGET_PCT / 100.0)
        self.assertEqual(M.FLOOR, M.SPOKEN_MIN_PCT / 100.0)
        self.assertEqual(M.CAP, M.SPOKEN_MAX_PCT / 100.0)
        self.assertEqual(M.FIRST_SUNG_WITHIN_SECONDS, 10)

    def test_rule_id_is_exported_by_both_import_paths(self):
        self.assertEqual(M.RULE_ID, "D15")
        import spoken_share as pkg
        if getattr(pkg, "__file__", "").endswith("spoken_share.py"):
            self.skipTest("plain run bound the module, not the package")
        self.assertEqual(pkg.RULE_ID, "D15")
        self.assertIn("RULE_ID", pkg.__all__)

    def test_check_first_sung_passes_on_an_early_hook(self):
        out = M.check_first_sung([{"delivery": "spoken", "seconds": 5},
                                  {"delivery": "sung", "seconds": 30}])
        self.assertEqual(out["verdict"], "PASS", out)
        self.assertEqual(out["first_sung_start_s"], 5.0)
        self.assertEqual(out["limit_s"], 10)

    def test_check_first_sung_fails_when_nothing_is_sung(self):
        out = M.check_first_sung([{"delivery": "rap", "seconds": 40},
                                  {"delivery": "spoken", "seconds": 20}])
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIsNone(out["first_sung_start_s"])
        self.assertTrue(any("no singing" in r for r in out["reasons"]), out)

    def test_check_first_sung_fails_on_a_late_hook(self):
        out = M.check_first_sung([{"delivery": "spoken", "seconds": 15},
                                  {"delivery": "sung", "seconds": 45}])
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(out["first_sung_start_s"], 15.0)
        self.assertTrue(out["reasons"], out)

    def test_check_first_sung_accepts_start_and_end_records(self):
        out = M.check_first_sung([{"delivery": "spoken", "start": 0,
                                   "end": 4},
                                  {"delivery": "sung", "start": 4,
                                   "end": 40}])
        self.assertEqual(out["verdict"], "PASS", out)
        self.assertEqual(out["first_sung_start_s"], 4.0)

    def test_check_first_sung_refuses_bad_segments(self):
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung([])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENTS")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung("not a list")
        self.assertEqual(ctx.exception.code, "BAD_SEGMENTS")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung([{"delivery": "yodel", "seconds": 3}])
        self.assertEqual(ctx.exception.code, "BAD_DELIVERY")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung([{"delivery": "sung"}])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENT")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung([{"delivery": "sung", "start": 9, "end": 4}])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENT")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.check_first_sung([{"delivery": "sung", "seconds": -1}])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENT")

    def test_music_styles_still_reads_the_rule_when_this_package_wins(self):
        """The sibling regression this shadow caused must not come back."""
        build = M.build_root()
        added = [os.path.join(build, "core"), build]
        for path in reversed(added):
            sys.path.insert(0, path)
        try:
            from music_styles import music_styles as MS
        except ImportError:
            self.skipTest("music_styles sibling not present")
        finally:
            for _ in added:
                if sys.path and sys.path[0] in added:
                    sys.path.pop(0)
        self.assertEqual(MS.SPOKEN_SHARE_TARGET, 0.45)
        self.assertEqual(MS.SPOKEN_SHARE_MIN, 0.40)
        self.assertEqual(MS.SPOKEN_SHARE_MAX, 0.55)
        self.assertEqual(MS.FIRST_SUNG_WITHIN_SECONDS, 10)
        self.assertEqual(
            MS.check_first_sung([{"delivery": "spoken", "seconds": 6},
                                 {"delivery": "sung", "seconds": 30}]),
            M.check_first_sung([{"delivery": "spoken", "seconds": 6},
                                {"delivery": "sung", "seconds": 30}]))


class ImportTests(unittest.TestCase):
    def test_import_from_another_working_directory(self):
        code = ("import sys; sys.path.insert(0, %r); import spoken_share as M;"
                "print(M.SPOKEN_TARGET_PCT, M.SPOKEN_MIN_PCT,"
                "M.SPOKEN_MAX_PCT, M.FIRST_SUNG_WITHIN_SECONDS)" % HERE)
        proc = subprocess.run([sys.executable, "-c", code], cwd=tempfile.gettempdir(),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(), "45 40 55 10")

    def test_package_exports_everything_the_planner_reads(self):
        for name in ("weekly_ad_limits", "planner_line", "evaluate",
                     "spoken_share_pct", "first_sung_start",
                     "scan_smp_modules", "check_planner_text",
                     "spoken_budget", "counts_as_spoken", "KIE_PATH"):
            self.assertIn(name, M.__all__, name)
            self.assertTrue(hasattr(M, name), name)

    def test_schema_and_tool_versions_are_stamped(self):
        self.assertEqual(M.SCHEMA_VERSION, "blackceo.smp.spoken-share/v1")
        self.assertEqual(M.TOOL_NAME, "smp.spoken_share")
        self.assertTrue(re.match(r"^\d+\.\d+\.\d+$", M.TOOL_VERSION))


if __name__ == "__main__":
    unittest.main(verbosity=2)

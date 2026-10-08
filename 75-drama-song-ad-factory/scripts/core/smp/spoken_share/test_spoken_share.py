#!/usr/bin/env python3
"""Tests for the SMP thin re-export of the D15 spoken-share rule (manual L1).

The rule itself is implemented once in ``core/spoken_share/spoken_share.py``.
``core/smp/spoken_share/spoken_share.py`` is a thin re-export so imports under
``core/smp/`` keep resolving. These tests prove: the file is thin, every
exported name is the core module's own object, the owner's numbers and rules
behave through the re-export (rap counts as spoken, first sung within about
10 seconds), and the source carries no transport, spend path or operator path.

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

import spoken_share as M  # noqa: E402  module under test (the re-export)

OWNED_DIR = HERE
MODULE_SRC = os.path.join(OWNED_DIR, "spoken_share.py")
INIT_SRC = os.path.join(OWNED_DIR, "__init__.py")
CORE_PATH = os.path.abspath(os.path.join(
    HERE, "..", "..", "spoken_share", "spoken_share.py"))
MEDIA_EXT = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".aac",
             ".png", ".jpg", ".jpeg", ".gif", ".webp", ".mp4", ".mov",
             ".webm", ".srt")
_OPERATOR_HOME = "/" + "Users/"
FORBIDDEN_SOURCE = (
    "urllib", "requests", "http.client", "socket", "subprocess", "ftplib",
    "telnetlib", "websocket", "spend_ledger", "openai", "kie.ai", "api.kie",
    "pm2", "expanduser", "/users/", "/home/", ".openclaw",
    _OPERATOR_HOME, "os.environ",
)
THIN_MAX_LINES = 20


def load_core():
    """The core module instance the re-export bound itself to (one execution).

    Loading the file a second time would make equal-but-distinct objects and
    break identity; the re-export caches its load under this exact name.
    """
    cached = sys.modules.get("_smp_core_spoken_share")
    if cached is not None:
        return cached
    import importlib.util
    spec = importlib.util.spec_from_file_location("_core_spoken_share",
                                                  CORE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CORE = load_core()


def seg(delivery, seconds, start=None):
    """One timing segment in the core module's record shape."""
    out = {"delivery": delivery, "seconds": seconds}
    if start is not None:
        out["start"] = start
    return out


def in_band_ad():
    """45.0% spoken-style, first real singing at 15.0s (15%) -- both targets."""
    return [
        seg("spoken", 15, 0.0),
        seg("sung", 55, 15.0),
        seg("spoken", 30, 70.0),
    ], 100.0


class ThinnessTests(unittest.TestCase):
    def test_module_is_under_twenty_lines(self):
        with open(MODULE_SRC, "r", encoding="utf-8") as handle:
            count = sum(1 for _ in handle)
        self.assertLess(count, THIN_MAX_LINES, "module is %d lines" % count)

    def test_every_exported_name_is_the_core_objects_own(self):
        # plain run binds spoken_share.py (the re-export module); pytest binds
        # the package, which re-exports a subset -- names absent on M are
        # allowed unless the core package's __all__ demands them.
        demanded = set(getattr(CORE, "__all__", ()))
        for name in CORE.__dict__:
            if name.startswith("_"):
                continue
            if not hasattr(M, name):
                if name in demanded:
                    self.fail("core package exports %r; smp does not" % name)
                continue
            self.assertIs(getattr(M, name), getattr(CORE, name), name)

    def test_implementation_lives_in_core_not_here(self):
        self.assertIn("spoken_share/spoken_share.py",
                      M.check_share.__code__.co_filename)
        self.assertNotIn(os.path.join("smp", "spoken_share"),
                         M.check_share.__code__.co_filename)
        self.assertIn("spoken_share/spoken_share.py",
                      M.check_first_sung.__code__.co_filename)


class ConstantsTests(unittest.TestCase):
    def test_owner_numbers_are_exact(self):
        self.assertEqual(M.SPOKEN_TARGET_PCT, 45)
        self.assertEqual(M.SPOKEN_MIN_PCT, 40)
        self.assertEqual(M.SPOKEN_MAX_PCT, 55)
        self.assertEqual(M.FIRST_SUNG_TARGET_PCT, 15)

    def test_band_is_floor_then_ceiling(self):
        self.assertEqual(M.FLOOR, 0.40)
        self.assertEqual(M.CAP, 0.55)
        self.assertEqual(M.TARGET, 0.45)
        self.assertEqual(M.TARGET, M.SPOKEN_TARGET_PCT / 100.0)
        self.assertEqual(M.FLOOR, M.SPOKEN_MIN_PCT / 100.0)
        self.assertEqual(M.CAP, M.SPOKEN_MAX_PCT / 100.0)

    def test_rap_counts_as_spoken_and_never_as_sung(self):
        self.assertIn("rap", M.SPOKEN_STYLE_DELIVERIES)
        self.assertIn("spoken", M.SPOKEN_STYLE_DELIVERIES)
        self.assertEqual(M.SPOKEN_STYLE_DELIVERIES, frozenset({"spoken",
                                                               "rap"}))
        self.assertNotIn("rap", [d for d in M.DELIVERIES if d != "rap"
                                 and d == "sung"])
        self.assertEqual(M.DELIVERIES, ("spoken", "rap", "sung"))
        self.assertTrue(M.is_spoken_style("  RAP "))
        self.assertTrue(M.is_spoken_style("Spoken"))
        self.assertFalse(M.is_spoken_style("sung"))

    def test_rule_identity_and_source(self):
        self.assertEqual(M.SCHEMA_VERSION, "blackceo.spoken-share/v1")
        self.assertEqual(M.TOOL_NAME, "spoken_share")
        self.assertIn("Decision log 37", M.SOURCE)
        self.assertIn("2026-10-07", M.SOURCE)

    def test_one_band_for_every_length_and_style(self):
        band = M.band()
        self.assertEqual(band["applies_to"],
                         "every length and every music style")
        self.assertIs(band["rap_counts_as_spoken"], True)
        self.assertEqual(band["floor_pct"], 40)
        self.assertEqual(band["cap_pct"], 55)
        # the same fractions for 60 s and 600 s -- nothing keyed by length
        self.assertEqual(M.seconds_for(60)["target_s"], 27.0)
        self.assertEqual(M.seconds_for(600)["target_s"], 270.0)
        self.assertEqual(M.seconds_for(60)["floor_s"], 24.0)
        self.assertEqual(M.seconds_for(60)["cap_s"], 33.0)


class MeasurementTests(unittest.TestCase):
    def test_spoken_and_rap_both_count_sung_does_not(self):
        lines = [seg("spoken", 10), seg("rap", 5), seg("sung", 80)]
        self.assertEqual(M.measure_share(lines)["spoken_style_seconds"], 15.0)

    def test_share_is_a_percent_of_runtime_at_one_decimal(self):
        lines, _duration = in_band_ad()
        self.assertEqual(M.measure_share(lines)["share_pct"], 45.0)
        self.assertEqual(M.measure_share(
            [seg("spoken", 1), seg("sung", 3)])["share_pct"], 25.0)
        self.assertEqual(M.measure_share(
            [seg("spoken", 1), seg("sung", 2)])["share_pct"], 33.3)

    def test_fail_closed_measurements(self):
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.measure_share(["not a segment"])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENT")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.measure_share([{"delivery": "yodel", "seconds": 3}])
        self.assertEqual(ctx.exception.code, "BAD_DELIVERY")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.measure_share([{"delivery": "spoken"}])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENT")
        with self.assertRaises(M.SpokenShareError) as ctx:
            M.measure_share([])
        self.assertEqual(ctx.exception.code, "BAD_SEGMENTS")

    def test_error_message_carries_the_code(self):
        try:
            M.measure_share([{"delivery": "spoken"}])
        except M.SpokenShareError as exc:
            self.assertIn("BAD_SEGMENT", str(exc))
        else:  # pragma: no cover
            self.fail("expected a refusal")


class FirstSungTests(unittest.TestCase):
    def test_no_sung_line_returns_fail(self):
        out = M.check_first_sung([seg("spoken", 10), seg("rap", 10)])
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIsNone(out["first_sung_start_s"])
        self.assertTrue(any("no real singing" in r for r in out["reasons"]),
                        out["reasons"])

    def test_rap_never_satisfies_the_rule(self):
        out = M.check_first_sung([seg("rap", 20, 0.0)])
        self.assertEqual(out["verdict"], "FAIL")
        self.assertIsNone(out["first_sung_start_s"])

    def test_first_sung_is_the_earliest_real_sung_stretch(self):
        # a 2 s blip at 3 s is not real singing; the 10 s stretch at 40 s is.
        lines = [seg("sung", 2, 3.0), seg("spoken", 35, 5.0),
                 seg("sung", 10, 40.0), seg("spoken", 50, 50.0)]
        out = M.check_first_sung(lines)
        self.assertEqual(out["first_sung_start_s"], 40.0)

    def test_start_falls_back_to_the_running_cursor(self):
        out = M.check_first_sung([seg("spoken", 6), seg("sung", 10)])
        self.assertEqual(out["first_sung_start_s"], 6.0)

    def test_target_is_15_percent_and_judged_by_the_band(self):
        # 100 s cut: target 15 s; accept 10-20 s, flag to 25 s / 5 s, redo past.
        def hook(first):
            return M.check_first_sung([seg("spoken", first, 0.0),
                                       seg("sung", 100 - first, first)])
        self.assertEqual(hook(15)["verdict"], "PASS")
        self.assertEqual(hook(20)["verdict"], "PASS")
        self.assertEqual(hook(24)["verdict"], "FLAG")
        self.assertEqual(hook(7)["verdict"], "FLAG")
        out = hook(30)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertTrue(any("redo" in r for r in out["reasons"]), out["reasons"])

    def test_bad_input_is_refused(self):
        with self.assertRaises(M.SpokenShareError):
            M.check_first_sung([])
        with self.assertRaises(M.SpokenShareError):
            M.check_first_sung("not a list")


class ShareCheckTests(unittest.TestCase):
    def test_in_band_share_passes(self):
        out = M.check_share(0.45)
        self.assertEqual(out["verdict"], "PASS", out["reasons"])
        self.assertEqual(out["reasons"], [])
        self.assertEqual(out["share_pct"], 45.0)

    def test_band_boundaries_are_inclusive(self):
        self.assertEqual(M.check_share(0.40)["verdict"], "PASS")
        self.assertEqual(M.check_share(0.50)["verdict"], "PASS")
        self.assertEqual(M.check_share(0.55)["verdict"], "FLAG")   # H8 band

    def test_below_the_floor_fails(self):
        out = M.check_share(0.20)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("redo", out["reasons"][0])

    def test_above_the_ceiling_fails(self):
        out = M.check_share(0.60)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(len(out["reasons"]), 1, out["reasons"])
        self.assertIn("redo", out["reasons"][0])

    def test_rag_is_counted_so_a_rap_heavy_ad_is_not_under_the_floor(self):
        # 5 spoken + 45 rap + 5 spoken = 55% spoken-style: in band
        lines = [seg("spoken", 5, 0.0), seg("sung", 45, 5.0),
                 seg("rap", 45, 50.0), seg("spoken", 5, 95.0)]
        measured = M.measure_share(lines)
        self.assertEqual(measured["spoken_style_seconds"], 55.0)
        self.assertEqual(measured["share_pct"], 55.0)
        # 10 points off the 45% goal: accepted with a flag under the H8 band
        self.assertEqual(M.check_share(measured["share"])["verdict"], "FLAG")
        # the identical ad with rap sung instead measures 10%: under the floor
        no_rap = [lines[0], lines[1],
                  {"delivery": "sung", "seconds": 45, "start": 50},
                  lines[3]]
        below = M.check_share(M.measure_share(no_rap)["share"])
        self.assertEqual(below["verdict"], "FAIL")
        self.assertTrue(any("redo" in r for r in below["reasons"]),
                        below["reasons"])

    def test_refusal_text_is_compact_and_empty_when_passing(self):
        self.assertEqual(M.refusal(0.45), "")
        self.assertTrue(M.refusal(0.20).startswith("REFUSED"))

    def test_check_share_refuses_a_malformed_share(self):
        with self.assertRaises(M.SpokenShareError):
            M.check_share("long")
        with self.assertRaises(M.SpokenShareError):
            M.check_share(None)

    def test_check_share_is_deterministic(self):
        import json
        first = json.dumps(M.check_share(0.45), sort_keys=True)
        second = json.dumps(M.check_share(0.45), sort_keys=True)
        self.assertEqual(first, second)


class PlanTests(unittest.TestCase):
    def test_in_band_plan_passes(self):
        lines, duration = in_band_ad()
        out = M.check_plan(duration, lines)
        self.assertEqual(out["verdict"], "PASS", out["reasons"])
        self.assertEqual(out["share_pct"], 45.0)
        self.assertEqual(out["length_s"], 100.0)

    def test_plan_fails_on_band_and_on_the_hook_together(self):
        # 90% spoken: over the ceiling *and* the hook arrives at 90s
        lines = [seg("spoken", 90, 0.0), seg("sung", 10, 90.0)]
        out = M.check_plan(100.0, lines)
        self.assertEqual(out["verdict"], "FAIL")
        self.assertEqual(len(out["reasons"]), 2, out["reasons"])

    def test_plan_refusal_is_compact_and_empty_when_passing(self):
        lines, duration = in_band_ad()
        self.assertEqual(M.plan_refusal(duration, lines), "")
        self.assertTrue(M.plan_refusal(100.0, [seg("spoken", 100)]).startswith(
            "REFUSED"))

    def test_seconds_for_refuses_a_bad_length(self):
        for bad in (0, -1, "long"):
            with self.assertRaises(M.SpokenShareError):
                M.seconds_for(bad)


class ZeroSpendTests(unittest.TestCase):
    def test_no_network_even_with_socket_mocked_broken(self):
        with mock.patch("socket.socket",
                        side_effect=AssertionError("network call")):
            lines, duration = in_band_ad()
            self.assertEqual(M.check_plan(duration, lines)["verdict"], "PASS")
            self.assertEqual(M.check_share(0.45)["verdict"], "PASS")

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
        self.assertEqual(M.seconds_for(120)["target_s"], 54.0)
        self.assertEqual(M.SPOKEN_TARGET_PCT, 45)


class ImportTests(unittest.TestCase):
    def test_import_from_another_working_directory(self):
        code = ("import sys; sys.path.insert(0, %r); import spoken_share as M;"
                "print(M.SPOKEN_TARGET_PCT, M.SPOKEN_MIN_PCT,"
                "M.SPOKEN_MAX_PCT, M.FIRST_SUNG_TARGET_PCT)" % HERE)
        proc = subprocess.run([sys.executable, "-c", code],
                              cwd=tempfile.gettempdir(),
                              capture_output=True, text=True, timeout=60)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.strip(), "45 40 55 15")

    def test_package_exports_every_name_the_core_package_hands_out(self):
        core_init = os.path.abspath(os.path.join(
            HERE, "..", "..", "spoken_share", "__init__.py"))
        with open(core_init, "r", encoding="utf-8") as handle:
            text = handle.read()
        exported = re.findall(r'^\s{4}([A-Z][A-Z0-9_a-z]*),?\s*$', text,
                              re.M)
        exported += re.findall(r'^\s{4}([a-z][a-z0-9_]*),?\s*$', text, re.M)
        for name in exported:
            self.assertIn(name, M.__dict__, name)
            self.assertIn(name, M.__all__, name)


if __name__ == "__main__":
    unittest.main(verbosity=2)
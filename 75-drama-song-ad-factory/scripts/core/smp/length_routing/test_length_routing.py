#!/usr/bin/env python3
"""test_length_routing.py — mocked routing tests for SMP-W1-U4.

Covers the acceptance line one check each:

- the 59.0 second hard cap (the planner version must end by 59.0 s) and the
  62-63 second approved-ad range that sits over it;
- the 90-second option posts ONLY to Facebook Reels, Instagram Reels, TikTok
  and LinkedIn — never YouTube Shorts, never the Instagram feed;
- the per-channel routing table: TikTok 180 s, Facebook Reels 3-90 s,
  Instagram Reels 15 minutes, LinkedIn 30 minutes, Threads 5 minutes,
  YouTube Shorts 60 s, Instagram feed 60 s;
- Google Business Profile refused until a limit is verified, Stories refused
  in favour of the 15-second teaser, unknown destinations refused by name;
- every row carries a reason, allowed or not;
- zero paid calls, no transport, Skill 74 the only KIE path, no media files,
  no operator paths, no file writes.

Everything is pure data: no network, no key, no subprocess, nothing to mock
beyond the channel lists themselves.

Run (from the repository root):
    python3 core/smp/length_routing/test_length_routing.py
    python3 -m unittest discover -s core/smp/length_routing -p 'test_*.py'
"""
from __future__ import annotations

import ast
import atexit
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]              # core/smp/length_routing -> repo root
for _p in (str(REPO), str(HERE)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PKG = importlib.import_module("core.smp.length_routing")
LR = importlib.import_module("core.smp.length_routing.length_routing")

# --- check ledger -----------------------------------------------------------

TALLY = {"ok": 0, "fail": 0}
FAILED = []


def _report():
    print("\nchecks: %d ok, %d failed" % (TALLY["ok"], TALLY["fail"]))
    for name in FAILED:
        print("  failed: %s" % name)


atexit.register(_report)

SEVEN = (
    "YouTube Shorts",
    "Instagram feed",
    "Facebook Reels",
    "TikTok",
    "Instagram Reels",
    "LinkedIn",
    "Threads",
)
FOUR = ("Facebook Reels", "Instagram Reels", "TikTok", "LinkedIn")
ALL_SURFACE = list(SEVEN) + [
    "Google Business Profile",
    "Instagram Stories",
    "Facebook Stories",
    "TikTok Stories",
    "Pinterest",
    "MySpace",
]


class Ledger(unittest.TestCase):
    """Records every check so one assertion never hides the rest."""

    def ok(self, cond, msg):
        if cond:
            TALLY["ok"] += 1
        else:
            TALLY["fail"] += 1
            FAILED.append(msg)
        self.assertTrue(cond, msg)

    @staticmethod
    def plan(length, connected=ALL_SURFACE):
        return {row["channel"]: row for row in LR.route_channels(
            length, connected
        )}


# --- 1. 59.0 second hard cap ------------------------------------------------

class TestHardCap(Ledger):
    def test_cap_boundary_passes(self):
        for dur in (0.0, 30.0, 58.9, 59.0):
            ok, why = LR.validate_duration(dur, 60)
            self.ok(ok is True, "59.0 cap accepts %s (%s)" % (dur, why))

    def test_over_cap_refused_with_the_59_0_reason(self):
        for dur in (59.1, 60.0, 61.0, 62.5, 90.0, 120.0):
            ok, why = LR.validate_duration(dur, 60)
            self.ok(ok is False, "%s must fail the 59.0 cap" % dur)
            self.ok("59.0" in why, "reason names the cap for %s: %s"
                    % (dur, why))
            self.ok("60 seconds or less" in why,
                    "reason names the GoHighLevel 60 s limit for %s: %s"
                    % (dur, why))

    def test_approved_ad_range_is_named(self):
        for dur in (62.0, 62.5, 63.0):
            ok, why = LR.validate_duration(dur, 60)
            self.ok(ok is False, "approved-ad duration %s is refused" % dur)
            self.ok("approved ads run 62-63 seconds" in why,
                    "reason names the 62-63 approved range: %s" % why)
            self.ok("59.0" in why, "reason names the cap: %s" % why)

    def test_constants_match_the_owner_plan(self):
        self.ok(LR.HARD_CAP_S == 59.0, "HARD_CAP_S == 59.0")
        self.ok(LR.PLAN_OPTIONS_S == (60, 90), "options are 60 and 90 only")
        self.ok(LR.APPROVED_AD_RANGE_S == (62.0, 63.0),
                "approved ads run 62-63 seconds")
        self.ok(LR.NINETY_WINDOW_S == (88.0, 95.0),
                "90-second acceptance window 88.0-95.0")

    def test_bad_inputs_refused_by_name(self):
        cases = [
            ("abc", 60), (None, 60), (True, 60), (float("nan"), 60),
            (float("inf"), 60), (-1, 60), (-0.5, 60),
        ]
        for dur, opt in cases:
            ok, why = LR.validate_duration(dur, opt)
            self.ok(ok is False, "validate(%r, %s) refused" % (dur, opt))
            self.ok(bool(why), "validate(%r, %s) carries a reason"
                    % (dur, opt))
        for opt in (30, 45, "90", 120, None):
            ok, why = LR.validate_duration(60, opt)
            self.ok(ok is False, "option %r refused" % (opt,))
            self.ok("60 or 90" in why,
                    "option refusal names both options: %s" % why)


# --- 2. 90-second option ----------------------------------------------------

class TestNinetyOption(Ledger):
    def test_window_boundary(self):
        for dur in (88.0, 90.0, 91.0, 95.0):
            ok, why = LR.validate_duration(dur, 90)
            self.ok(ok is True, "90-window accepts %s (%s)" % (dur, why))
        for dur in (87.9, 80.0, 62.5, 95.1, 96.0, 120.0):
            ok, why = LR.validate_duration(dur, 90)
            self.ok(ok is False, "90-window refuses %s" % dur)
            self.ok("88.0 to 95.0" in why,
                    "window refusal names 88.0 to 95.0: %s" % why)

    def test_option_allow_lists(self):
        self.ok(tuple(LR.channels_for_option(60)) == SEVEN,
                "60-second option reaches all seven surfaces")
        self.ok(tuple(LR.channels_for_option(90)) == FOUR,
                "90-second option is exactly %s (got %r)"
                % (FOUR, LR.channels_for_option(90)))
        for name in ("YouTube Shorts", "Instagram feed"):
            self.ok(name not in LR.OPTION_90_CHANNELS,
                    "%s is outside the 90-second option" % name)
        self.ok(LR.OPTION_90_CHANNELS == FOUR,
                "OPTION_90_CHANNELS is the owner's four")
        with self.assertRaises(ValueError) as ctx:
            LR.channels_for_option(30)
        self.ok("60 or 90" in str(ctx.exception),
                "unknown option refused by name: %s" % ctx.exception)

    def test_ninety_never_reaches_shorts_or_the_instagram_feed(self):
        plan = self.plan(90)
        for name in ("YouTube Shorts", "Instagram feed"):
            row = plan[name]
            self.ok(row["allowed"] is False,
                    "90 never posts to %s" % name)
            self.ok("60 seconds or less" in row["reason"],
                    "%s reason names its limit: %s" % (name, row["reason"]))

    def test_ninety_reaches_only_the_four(self):
        plan = self.plan(90)
        for name in FOUR:
            self.ok(plan[name]["allowed"] is True,
                    "90 posts to %s: %s" % (name, plan[name]["reason"]))
        for name in ("Threads", "Pinterest", "MySpace",
                     "Google Business Profile", "Instagram Stories",
                     "Facebook Stories", "TikTok Stories"):
            self.ok(plan[name]["allowed"] is False,
                    "90 does not post to %s" % name)
        self.ok("only to Facebook Reels, Instagram Reels, TikTok, LinkedIn"
                in plan["Threads"]["reason"],
                "Threads refusal names the four: %s"
                % plan["Threads"]["reason"])

    def test_ninety_window_durations_behave_like_the_option(self):
        plan = self.plan(92)
        self.ok(plan["Threads"]["allowed"] is False,
                "92 s (inside the option window) keeps Threads out")
        self.ok(plan["YouTube Shorts"]["allowed"] is False,
                "92 s never reaches YouTube Shorts")
        self.ok(plan["TikTok"]["allowed"] is True, "92 s reaches TikTok")
        self.ok(plan["Facebook Reels"]["allowed"] is False
                and "tops out at 90" in plan["Facebook Reels"]["reason"],
                "92 s exceeds the Facebook Reels 90 s ceiling: %s"
                % plan["Facebook Reels"]["reason"])

    def test_sixty_reaches_every_surface(self):
        plan = self.plan(60)
        for name in SEVEN:
            self.ok(plan[name]["allowed"] is True,
                    "60 posts to %s: %s" % (name, plan[name]["reason"]))
        for name in ALL_SURFACE:
            self.ok(bool(plan[name]["reason"]),
                    "every row carries a reason (%s)" % name)


# --- 3. per-channel length routing table ------------------------------------

class TestRoutingTable(Ledger):
    CASES = (
        # (duration, channel, expected allowed, fragment expected in reason)
        (60, "YouTube Shorts", True, ""),
        (61, "YouTube Shorts", False, "60 seconds or less"),
        (60, "Instagram feed", True, ""),
        (61, "Instagram feed", False, "60 seconds or less"),
        (62.5, "YouTube Shorts", False, "60 seconds or less"),
        (63, "Instagram feed", False, "60 seconds or less"),
        (3, "Facebook Reels", True, ""),
        (2, "Facebook Reels", False, "3 seconds or more"),
        (90, "Facebook Reels", True, ""),
        (91, "Facebook Reels", False, "tops out at 90"),
        (180, "TikTok", True, ""),
        (181, "TikTok", False, "tops out at 180"),
        (3, "TikTok", True, ""),
        (2, "TikTok", False, "3 seconds or more"),
        (900, "Instagram Reels", True, ""),
        (901, "Instagram Reels", False, "tops out at 900"),
        (1800, "LinkedIn", True, ""),
        (1801, "LinkedIn", False, "tops out at 1800"),
        (300, "Threads", True, ""),
        (301, "Threads", False, "tops out at 300"),
        (120, "Threads", True, ""),
        (62.5, "Threads", True, ""),
        (62.5, "Facebook Reels", True, ""),
        (62.5, "TikTok", True, ""),
        (62.5, "Instagram Reels", True, ""),
        (62.5, "LinkedIn", True, ""),
    )

    def test_every_row_of_the_table(self):
        for dur, channel, expect, fragment in self.CASES:
            row = self.plan(dur, [channel])[channel]
            self.ok(row["allowed"] is expect,
                    "%s s on %s -> %s (reason: %s)"
                    % (dur, channel, expect, row["reason"]))
            if fragment:
                self.ok(fragment in row["reason"],
                        "%s s on %s reason names %r: %s"
                        % (dur, channel, fragment, row["reason"]))

    def test_table_constants(self):
        want = {
            "YouTube Shorts": (0.0, 60.0),
            "Instagram feed": (0.0, 60.0),
            "Facebook Reels": (3.0, 90.0),
            "TikTok": (3.0, 180.0),
            "Instagram Reels": (0.0, 900.0),
            "LinkedIn": (0.0, 1800.0),
            "Threads": (0.0, 300.0),
        }
        self.ok(dict(LR.CHANNEL_LIMITS) == want,
                "routing table is TikTok 180 / FB Reels 3-90 / IG Reels "
                "15 min / LinkedIn 30 min / Threads 5 min / Shorts 60 / "
                "feed 60 (got %r)" % (dict(LR.CHANNEL_LIMITS),))
        self.ok(LR.CHANNEL_LIMITS["Instagram Reels"][1] == 15 * 60,
                "Instagram Reels = 15 minutes")
        self.ok(LR.CHANNEL_LIMITS["LinkedIn"][1] == 30 * 60,
                "LinkedIn = 30 minutes")
        self.ok(LR.CHANNEL_LIMITS["Threads"][1] == 5 * 60, "Threads = 5 minutes")


# --- 4. never-routed destinations ------------------------------------------

class TestNeverRouted(Ledger):
    def test_google_business_profile_never_routes(self):
        for dur in (30, 60, 90, 180):
            row = self.plan(dur, ["Google Business Profile"])[
                "Google Business Profile"]
            self.ok(row["allowed"] is False,
                    "Google Business Profile never accepts %s s" % dur)
            self.ok("not verified" in row["reason"],
                    "reason says the limit is not verified: %s"
                    % row["reason"])

    def test_stories_carry_the_teaser_only(self):
        for name in ("Instagram Stories", "Facebook Stories",
                     "TikTok Stories", "X Stories"):
            for dur in (15, 60, 90):
                row = self.plan(dur, [name])[name]
                self.ok(row["allowed"] is False,
                        "%s never takes the full ad at %s s" % (name, dur))
                self.ok("teaser" in row["reason"],
                        "reason names the teaser: %s" % row["reason"])

    def test_unknown_destination_refused_by_name(self):
        for name in ("MySpace", "Bluesky", "Pinterest", "x", "youtube shorts"):
            row = self.plan(60, [name])[name]
            self.ok(row["allowed"] is False,
                    "unknown destination %r is refused" % name)
            self.ok("not a Skill 35 destination" in row["reason"],
                    "%r refusal is explicit: %s" % (name, row["reason"]))

    def test_blank_channel_rows_are_skipped(self):
        plan = LR.route_channels(60, ["", "   ", None, "TikTok"])
        self.ok([r["channel"] for r in plan] == ["TikTok"],
                "blank channels are skipped, TikTok kept: %r" % (plan,))


# --- 5. routing a bad duration ---------------------------------------------

class TestBadDurationRouting(Ledger):
    def test_non_numeric_length_denies_everything_with_a_reason(self):
        for bad in ("abc", None, True, float("nan"), -5, -0.5):
            plan = LR.route_channels(bad, ["TikTok", "Threads"])
            self.ok(len(plan) == 2, "%r still yields one row per channel"
                    % (bad,))
            for row in plan:
                self.ok(row["allowed"] is False,
                        "%r never allows %s" % (bad, row["channel"]))
                self.ok(bool(row["reason"]),
                        "%r carries a reason for %s" % (bad, row["channel"]))

    def test_single_channel_string_is_not_split(self):
        plan = LR.route_channels(60, "TikTok")
        self.ok(len(plan) == 1 and plan[0]["channel"] == "TikTok",
                "a bare channel name is one row: %r" % (plan,))

    def test_no_connected_channels_is_an_empty_plan(self):
        self.ok(LR.route_channels(60, []) == [], "no channels, no rows")
        self.ok(LR.route_channels(60, None) == [], "None channels, no rows")

    def test_row_shape(self):
        row = LR.route_channels(60, ["TikTok"])[0]
        self.ok(set(row) == {"channel", "allowed", "reason"},
                "row keys are channel/allowed/reason: %r" % (row,))
        self.ok(isinstance(row["allowed"], bool), "allowed is a bool")


# --- 6. wave interface ------------------------------------------------------

class TestWaveInterface(Ledger):
    def test_the_three_router_names_are_one_function(self):
        self.ok(LR.route_channels is LR.channel_acceptance
                and LR.route_channels is LR.route,
                "route_channels / channel_acceptance / route are one call")
        self.ok(PKG.route_channels is LR.route_channels,
                "package re-export is the same function")

    def test_package_surface(self):
        for name in LR.__all__:
            self.ok(hasattr(PKG, name), "package exports %s" % name)
        self.ok(PKG.HARD_CAP_S == 59.0, "package HARD_CAP_S == 59.0")
        self.ok(PKG.OPTION_90_CHANNELS == FOUR,
                "package 90-second option is the four")

    def test_weekly_step_contract_shapes(self):
        # SMP-W1-U1 calls router(int(length), connected) and reads back a
        # non-empty list of {channel, allowed, reason} rows.
        out = LR.channel_acceptance(int(90), list(SEVEN))
        self.ok(isinstance(out, list) and out,
                "weekly_step gets a non-empty list back")
        by = {r["channel"]: r for r in out}
        self.ok(by["YouTube Shorts"]["allowed"] is False,
                "weekly_step sees Shorts refused at 90")
        self.ok(all(by[c]["allowed"] for c in FOUR),
                "weekly_step sees the four accepted at 90")
        self.ok(all(r.get("reason") for r in out),
                "weekly_step sees a reason on every row")

    def test_how_weekly_step_loads_this_unit(self):
        # SMP-W1-U1 loads the file standalone with spec_from_file_location
        # and takes the first callable named channel_acceptance /
        # route_channels / route. Reproduce that exact binding here.
        spec = importlib.util.spec_from_file_location(
            "smp_length_routing", HERE / "length_routing.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fn = None
        for name in ("channel_acceptance", "route_channels", "route"):
            candidate = getattr(mod, name, None)
            if callable(candidate):
                fn = candidate
                break
        self.ok(fn is not None,
                "the wave's router interface finds a callable here")
        out = fn(int(90), list(SEVEN))
        by = {r["channel"]: r for r in out}
        self.ok(by["Threads"]["allowed"] is False
                and by["TikTok"]["allowed"] is True,
                "the standalone-loaded router answers the same way")


# --- 7. hygiene: zero paid calls, Skill 74 only, no media, no operator paths

SOURCES = ("length_routing.py", "__init__.py")
TRANSPORT = (
    "urllib", "http.client", "socket", "subprocess", "requests.",
    "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib", "asyncio",
    "os.system", "popen", "urlopen", "://",
)
SECOND_KIE_CLIENT = (
    "kie.ai", "kieai", "KIE_API_KEY", "KIE_API_HOST", "KIE_SECRET",
    "createTask", "recordInfo", "api.kie", "Bearer ",
)
OPERATOR_PATHS = ("/Users/", "/home/", "/Volumes/")
MEDIA_EXT = (
    ".mp4", ".mov", ".m4v", ".mkv", ".avi", ".png", ".jpg", ".jpeg",
    ".gif", ".webp", ".svg", ".wav", ".mp3", ".m4a", ".aac", ".hevc",
)
WRITE_CALLS = (
    "open", "urlopen", "write_text", "write_bytes", "mkdir", "makedirs",
    "unlink", "remove", "rename", "touch", "system", "popen", "Popen",
    "run", "send", "request",
)
NET_IMPORTS = (
    "urllib", "http", "socket", "subprocess", "requests", "httpx",
    "aiohttp", "ftplib", "smtplib", "telnetlib", "ssl",
)


class TestHygiene(Ledger):
    @staticmethod
    def _text(name):
        return (HERE / name).read_text(encoding="utf-8")

    def test_zero_paid_calls_and_no_transport(self):
        for name in SOURCES:
            src = self._text(name)
            for token in TRANSPORT:
                self.ok(token not in src,
                        "%s carries no transport token %r" % (name, token))
            tree = ast.parse(src)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        root = alias.name.split(".")[0]
                        self.ok(root not in NET_IMPORTS,
                                "%s does not import %s" % (name, root))
                elif isinstance(node, ast.ImportFrom):
                    root = (node.module or "").split(".")[0]
                    self.ok(root not in NET_IMPORTS,
                            "%s does not import from %s" % (name, root))
                elif isinstance(node, ast.Call):
                    func = node.func
                    label = (func.id if isinstance(func, ast.Name)
                             else func.attr if isinstance(func, ast.Attribute)
                             else "")
                    self.ok(label not in WRITE_CALLS,
                            "%s never calls %s" % (name, label))

    def test_skill_74_is_the_only_kie_path(self):
        for name in SOURCES:
            src = self._text(name)
            for token in SECOND_KIE_CLIENT:
                self.ok(token not in src,
                        "%s carries no second KIE client token %r"
                        % (name, token))
        self.ok(LR.KIE_PATH == "skill-74",
                "KIE_PATH is skill-74, the live adapter")
        self.ok(LR.KIE_DISPATCH == "not_required",
                "routing dispatches nothing: KIE_DISPATCH not_required")
        self.ok(not hasattr(LR, "client") and not hasattr(LR, "session")
                and not hasattr(LR, "engine"),
                "module exposes no client/session/engine")

    def test_no_operator_paths(self):
        for name in SOURCES:
            src = self._text(name)
            for token in OPERATOR_PATHS:
                self.ok(token not in src,
                        "%s carries no operator path %r" % (name, token))

    def test_no_media_files_ship(self):
        offenders = []
        for path in HERE.rglob("*"):
            if "__pycache__" in path.parts or not path.is_file():
                continue
            if path.suffix.lower() in MEDIA_EXT:
                offenders.append(path.name)
        self.ok(not offenders, "no media files in the module dir: %r"
                % offenders)
        shipped = sorted(
            p.name for p in HERE.iterdir()
            if p.is_file() and "__pycache__" not in p.name
        )
        self.ok(all(name.endswith((".py", ".md")) for name in shipped),
                "module dir ships only .py/.md: %r" % shipped)

    def test_no_file_writes_in_the_module(self):
        for name in SOURCES:
            tree = ast.parse(self._text(name))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                label = (func.id if isinstance(func, ast.Name)
                         else func.attr if isinstance(func, ast.Attribute)
                         else "")
                self.ok(label not in ("open", "write_text", "write_bytes",
                                      "mkdir", "makedirs", "unlink",
                                      "remove", "rename", "touch"),
                        "%s performs no file write via %r" % (name, label))


# --- 8. pure data: nothing to mock, nothing to pay for ----------------------

class TestPureData(Ledger):
    def test_routing_is_deterministic(self):
        first = LR.route_channels(90, list(SEVEN))
        second = LR.route_channels(90, list(SEVEN))
        self.ok(first == second, "routing is deterministic")

    def test_plan_is_json_serialisable(self):
        import json
        blob = json.dumps(LR.route_channels(60, ALL_SURFACE))
        self.ok(json.loads(blob) == LR.route_channels(60, ALL_SURFACE),
                "the plan round-trips through JSON for the sheet write-back")

    def test_documented_source_and_schema(self):
        self.ok(LR.SCHEMA_VERSION == "blackceo.smp-length-routing/v1",
                "schema version pinned")
        self.ok("6.15" in LR.SOURCE, "source cites plan section 6.15")


class TestZZSummary(Ledger):
    def test_no_failed_checks(self):
        self.ok(TALLY["fail"] == 0,
                "%d check(s) failed" % TALLY["fail"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

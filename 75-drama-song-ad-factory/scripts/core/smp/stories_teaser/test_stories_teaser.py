#!/usr/bin/env python3
"""Mocked tests for the D27/D35 15-second Stories teaser cut (plan 6.15).

Offline, stdlib only, zero paid calls, zero network, zero media. Covered,
one test per acceptance rule:
  free cut window + end card | peak clamp inside the ad | peak tie/score |
  hold floor from the shared CTA rule | 15 s hard cap | IG 15 s segment
  split | TikTok 15 s Story limit | Facebook 60 s clip | Google Business
  Profile excluded until verified | unknown channel refused | moments and
  duration validation | no transport / no KIE client / Skill 74 only path |
  no media files / no operator paths / no file writes | link validation |
  schema stamps and package exports

Run: python3 core/smp/stories_teaser/test_stories_teaser.py
"""
import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _build_root():
    """Walk up to the directory that owns core/artifact_graph.py."""
    node = HERE
    while True:
        if os.path.isfile(os.path.join(node, "core", "artifact_graph.py")):
            return node
        parent = os.path.dirname(node)
        if parent == node:
            raise SystemExit("build root not found above %s" % HERE)
        node = parent


BUILD_ROOT = _build_root()
sys.path.insert(0, BUILD_ROOT)

import core.smp.stories_teaser as PKG                      # noqa: E402
import core.smp.stories_teaser.teaser as V                  # noqa: E402
from core.delivery_variants.checks import check_cta_hold   # noqa: E402

FAILS = []

MEDIA_SUFFIXES = (".mp4", ".mov", ".avi", ".mkv", ".webm", ".png", ".jpg",
                  ".jpeg", ".gif", ".webp", ".heic", ".wav", ".mp3", ".m4a",
                  ".pdf")
# Tokens that would mean a paid path, a second KIE client, or transport.
FORBIDDEN_TOKENS = ("kie.ai", "createTask", "recordInfo", "KIE_API_KEY",
                    "urllib", "http.client", "socket", "subprocess",
                    "httpx", "requests.", "os.system", "popen")
WRITE_CALLS = ("open", "write_text", "write_bytes", "mkdir", "makedirs",
               "unlink", "remove", "rename")
MEDIA_ROOT = os.path.join(BUILD_ROOT, "core", "smp", "stories_teaser")
MODULE_SOURCES = ("teaser.py", "__init__.py")   # shipped module, scanned for transport
PACKAGE_SOURCES = ("teaser.py", "__init__.py", "test_stories_teaser.py")

AD = {"id": "ad-2026-10-07-01", "duration_seconds": 62.5, "aspect": "9:16"}
MOMENTS = [{"start": 12.0, "score": 5},
           {"start": 30.0, "score": 9},
           {"start": 55.0, "score": 4}]


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises_code(fn, code):
    try:
        fn()
    except V.TeaserError as exc:
        return exc.code == code, "code=%s" % exc.code
    except Exception as exc:                              # noqa: BLE001
        return False, "%s: %s" % (type(exc).__name__, exc)
    return False, "no exception raised"


def sources(names=PACKAGE_SOURCES):
    for name in names:
        path = os.path.join(MEDIA_ROOT, name)
        with open(path, "r", encoding="utf-8") as handle:
            yield name, handle.read()


def test_free_cut_window_and_end_card():
    plan = V.plan_teaser(AD, MOMENTS)
    check("schema stamped", plan["schema_version"] == V.TEASER_SCHEMA,
          str(plan["schema_version"]))
    check("unit stamped", plan["unit_id"] == V.UNIT_ID, str(plan["unit_id"]))
    check("teaser is exactly 15 seconds",
          plan["teaser"]["duration_seconds"] == 15.0,
          str(plan["teaser"]["duration_seconds"]))
    check("hard cap recorded", plan["teaser"]["max_seconds"] == 15.0)
    check("12 second cut window", plan["cut"]["duration_seconds"] == 12.0,
          str(plan["cut"]["duration_seconds"]))
    check("cut starts at the peak", plan["cut"]["start"] == 30.0,
          str(plan["cut"]["start"]))
    check("cut ends before the ad end",
          0 <= plan["cut"]["start"] < plan["cut"]["end"] <= AD["duration_seconds"],
          str(plan["cut"]))
    check("peak is the most intense moment",
          plan["cut"]["peak"] == {"start": 30.0, "score": 9.0},
          str(plan["cut"]["peak"]))
    check("cut reason names the intense moment",
          plan["cut"]["reason"] == "most intense moment",
          str(plan["cut"]["reason"]))
    end_card = plan["end_card"]
    check("end card copy is watch the full video",
          end_card["text"].lower() == "watch the full video", end_card["text"])
    check("end card follows the cut", end_card["start"] == plan["cut"]["end"],
          str(end_card["start"]))
    check("end card is 3 seconds", end_card["duration_seconds"] == 3.0,
          str(end_card["duration_seconds"]))
    check("end card passes the shared CTA hold floor",
          check_cta_hold(end_card["duration_seconds"])[0] == "PASS",
          str(check_cta_hold(end_card["duration_seconds"])))
    check("end card + cut = teaser total",
          plan["cut"]["duration_seconds"] + end_card["duration_seconds"]
          == plan["teaser"]["duration_seconds"])
    check("stories pixels 1080x1920", plan["teaser"]["pixels"] == "1080x1920",
          str(plan["teaser"]["pixels"]))


def test_peak_near_end_clamps_inside_ad():
    moments = [{"start": 60.0, "score": 9}, {"start": 5.0, "score": 2}]
    plan = V.plan_teaser(AD, moments)
    check("clamp pulls the window onto the ad end",
          plan["cut"]["start"] == 50.5 and plan["cut"]["end"] == 62.5,
          str(plan["cut"]))
    check("peak stays inside the window",
          plan["cut"]["start"] <= plan["cut"]["peak"]["start"] <= plan["cut"]["end"],
          str(plan["cut"]["peak"]))
    check("window still 12 seconds", plan["cut"]["duration_seconds"] == 12.0)
    check("teaser still 15 seconds",
          plan["teaser"]["duration_seconds"] == 15.0)


def test_peak_at_start_and_tie_and_score():
    at_start = V.plan_teaser(AD, [{"start": 0.0, "score": 7},
                                  {"start": 40.0, "score": 3}])
    check("peak at 0 starts the cut at 0", at_start["cut"]["start"] == 0.0,
          str(at_start["cut"]["start"]))
    tied = V.pick_peak([{"start": 40.0, "score": 8}, {"start": 10.0, "score": 8}],
                       AD["duration_seconds"])
    check("score tie picks the earliest moment", tied["start"] == 10.0,
          str(tied))
    highest = V.pick_peak([{"start": 40.0, "score": 8},
                           {"start": 10.0, "score": 2},
                           {"start": 55.0, "score": 8.5}], AD["duration_seconds"])
    check("highest score wins", highest["start"] == 55.0, str(highest))


def test_hold_shrinks_window_total_stays_15():
    plan = V.plan_teaser(AD, MOMENTS, end_card_hold_seconds=4.0)
    check("hold 4s keeps the teaser at 15 seconds",
          plan["teaser"]["duration_seconds"] == 15.0,
          str(plan["teaser"]["duration_seconds"]))
    check("window shrinks to 11 seconds",
          plan["cut"]["duration_seconds"] == 11.0,
          str(plan["cut"]["duration_seconds"]))
    check("end card holds 4 seconds",
          plan["end_card"]["duration_seconds"] == 4.0,
          str(plan["end_card"]["duration_seconds"]))


def test_end_card_hold_floor_and_window_refusals():
    ok, detail = raises_code(
        lambda: V.plan_teaser(AD, MOMENTS, end_card_hold_seconds=2.5),
        "end_card_hold_below_floor")
    check("hold under the 3 second CTA floor refused", ok, detail)
    ok, detail = raises_code(
        lambda: V.plan_teaser(AD, MOMENTS, end_card_hold_seconds=15.0),
        "end_card_hold_invalid")
    check("hold that leaves no cut window refused", ok, detail)
    ok, detail = raises_code(
        lambda: V.plan_teaser(AD, MOMENTS, end_card_hold_seconds="3"),
        "end_card_hold_invalid")
    check("non-numeric hold refused", ok, detail)


def test_short_and_bad_ads_refused():
    ok, detail = raises_code(
        lambda: V.plan_teaser(dict(AD, duration_seconds=14.0), MOMENTS),
        "ad_too_short")
    check("ad under 15 seconds refused", ok, detail)
    for bad in (0, -1, "62.5", True, None):
        ok, detail = raises_code(
            lambda value=bad: V.plan_teaser(dict(AD, duration_seconds=value),
                                            MOMENTS),
            "duration_invalid")
        check("bad duration %r refused" % (bad,), ok, detail)
    ok, detail = raises_code(lambda: V.plan_teaser("ad", MOMENTS), "ad_invalid")
    check("non-object ad refused", ok, detail)
    ok, detail = raises_code(
        lambda: V.plan_teaser(dict(AD, aspect="21:9"), MOMENTS), "aspect_invalid")
    check("unknown aspect refused", ok, detail)


def test_moments_validation():
    ok, detail = raises_code(lambda: V.plan_teaser(AD, []), "no_intensity_moments")
    check("empty moments refused", ok, detail)
    for bad in ([{}], [{"start": 70.0, "score": 1}], [{"start": 5.0}],
                ["peak"], [{"start": 5.0, "score": "9"}]):
        ok, detail = raises_code(
            lambda value=bad: V.plan_teaser(AD, value), "moment_invalid")
        check("bad moments %r refused" % (bad,), ok, detail)
    ok, detail = raises_code(lambda: V.pick_peak([], 62.5),
                             "no_intensity_moments")
    check("pick_peak refuses an empty moment list", ok, detail)


def test_story_segments_split():
    one = V.story_segments(15.0)
    check("15s is one Instagram segment", len(one) == 1 and one[0]["end"] == 15.0,
          str(one))
    parts = V.story_segments(31.0)
    check("31s splits into three 15s-capped segments", len(parts) == 3,
          str(parts))
    for duration in (1.0, 15.0, 15.1, 30.0, 31.0, 62.5):
        parts = V.story_segments(duration)
        contiguous = parts[0]["start"] == 0.0 and parts[-1]["end"] == duration
        contiguous = contiguous and all(
            parts[i]["end"] == parts[i + 1]["start"] for i in range(len(parts) - 1))
        capped = all(seg["end"] - seg["start"] <= 15.0 + 1e-9 for seg in parts)
        check("segments contiguous and capped for %.1fs" % duration,
              contiguous and capped, str(parts))
    ok, detail = raises_code(lambda: V.story_segments(0), "duration_invalid")
    check("zero-length story refused", ok, detail)
    ok, detail = raises_code(lambda: V.story_segments(10, 0), "segment_invalid")
    check("zero segment size refused", ok, detail)


def test_instagram_splits_into_15s_segments():
    route = V.route_channel("instagram", 15.0)
    check("instagram accepts the 15s teaser as one segment",
          route["accepted"] and route["segments"] == 1
          and route["segment_seconds"] == 15.0, str(route))
    split = V.route_channel("instagram", 31.0)
    check("instagram splits a longer story into 15s segments",
          split["accepted"] and split["segments"] == 3
          and len(split["segment_plan"]) == 3, str(split))


def test_tiktok_15s_story_limit():
    ok_route = V.route_channel("tiktok", 15.0)
    check("tiktok accepts exactly 15 seconds",
          ok_route["accepted"] and ok_route["segments"] == 1, str(ok_route))
    over = V.route_channel("tiktok", 15.5)
    check("tiktok refuses over 15 seconds",
          not over["accepted"] and over["segments"] == 0
          and "15" in over["reason"], str(over))
    check("tiktok refusal carries a code", over.get("code") == "over_tiktok_story_limit",
          str(over))


def test_facebook_clip_limit():
    ok_route = V.route_channel("facebook", 60.0)
    check("facebook accepts a 60s story clip",
          ok_route["accepted"] and ok_route["segments"] == 1, str(ok_route))
    over = V.route_channel("facebook", 60.5)
    check("facebook refuses over 60 seconds",
          not over["accepted"] and "60" in over["reason"], str(over))


def test_google_business_profile_excluded_until_verified():
    route = V.route_channel("google_business_profile", 15.0)
    check("google business profile refused", not route["accepted"],
          str(route))
    check("refusal carries the unverified-limit reason",
          route.get("reason") == V.GBP_REASON
          and "until the Story length limit is verified" in route["reason"],
          str(route.get("reason")))
    check("refusal code names the unverified limit",
          route.get("code") == V.GBP_CODE, str(route.get("code")))
    check("refusal posts zero segments", route["segments"] == 0, str(route))


def test_plan_routing_table():
    plan = V.plan_teaser(AD, MOMENTS)
    names = [entry["channel"] for entry in plan["routing"]]
    check("default routing covers the four Story destinations",
          names == list(V.DEFAULT_CHANNELS), str(names))
    by_name = {entry["channel"]: entry for entry in plan["routing"]}
    check("google business profile never accepted",
          by_name["google_business_profile"]["accepted"] is False,
          str(by_name["google_business_profile"]))
    accepted = [entry for entry in plan["routing"] if entry["accepted"]]
    check("instagram, facebook and tiktok accepted",
          [entry["channel"] for entry in accepted]
          == ["instagram", "facebook", "tiktok"], str(accepted))
    check("every accepted destination fits its limit",
          all(entry["segments"] >= 1 for entry in accepted), str(accepted))
    check("teaser never exceeds the 15s Story cap",
          plan["teaser"]["duration_seconds"] <= V.TEASER_MAX_SECONDS)
    only_ig = V.plan_teaser(AD, MOMENTS, channels=["instagram"])
    check("caller may narrow the channel list",
          [entry["channel"] for entry in only_ig["routing"]] == ["instagram"],
          str(only_ig["routing"]))


def test_channel_argument_validation():
    ok, detail = raises_code(lambda: V.route_channel("pinterest", 15.0),
                             "unknown_channel")
    check("unknown channel refused by route_channel", ok, detail)
    ok, detail = raises_code(
        lambda: V.plan_teaser(AD, MOMENTS, channels=["pinterest"]),
        "unknown_channel")
    check("unknown channel refused by plan_teaser", ok, detail)
    for bad in ([], "instagram"):
        ok, detail = raises_code(
            lambda value=bad: V.plan_teaser(AD, MOMENTS, channels=value),
            "channels_invalid")
        check("bad channels %r refused" % (bad,), ok, detail)
    ok, detail = raises_code(
        lambda: V.plan_teaser(AD, MOMENTS, channels=[123]), "unknown_channel")
    check("non-name channel entry refused", ok, detail)


def test_zero_paid_calls_and_skill74_only_kie_path():
    plan = V.plan_teaser(AD, MOMENTS)
    check("cost block is all zero",
          plan["cost"]["credits"] == 0 and plan["cost"]["paid_calls"] == 0,
          str(plan["cost"]))
    check("no KIE dispatch for a free cut",
          plan["cost"]["kie_dispatch"] == "not_required"
          and plan["cost"]["kie_path"] == "skill-74", str(plan["cost"]))
    hits = []
    for name, text in sources(MODULE_SOURCES):
        for token in FORBIDDEN_TOKENS:
            if token in text:
                hits.append("%s:%s" % (name, token))
    check("package source carries no transport, no paid client, no second KIE path",
          not hits, ", ".join(hits))
    check("module exposes no session or client object",
          not any(hasattr(V, attr) for attr in ("session", "client", "engine")))


def test_no_media_files_in_module_dir():
    media = [name for name in os.listdir(MEDIA_ROOT)
             if name.lower().endswith(MEDIA_SUFFIXES)]
    check("module directory holds no media files", not media, ", ".join(media))


def test_no_operator_paths_and_no_file_writes():
    hits = []
    home = "/" + "Users/"
    home_alt = "/" + "home/"
    box = "black" + "ceomacmini"
    for name, text in sources():
        for token in (home, home_alt, box):
            if token in text:
                hits.append("%s:%s" % (name, token))
    check("package source carries no operator path", not hits, ", ".join(hits))
    tree = ast.parse(open(os.path.join(MEDIA_ROOT, "teaser.py"),
                          encoding="utf-8").read())
    writes = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            label = getattr(target, "id", None) or getattr(target, "attr", None)
            if label in WRITE_CALLS:
                writes.append("%s:%s" % (node.lineno, label))
    check("teaser module writes no files", not writes, ", ".join(writes))


def test_link_validation():
    keep = V.plan_teaser(AD, MOMENTS, link="https://blackceo.com/action")
    check("valid link kept on the plan",
          keep["link"] == "https://blackceo.com/action", str(keep["link"]))
    check("plan works with no link", V.plan_teaser(AD, MOMENTS)["link"] is None)
    for bad in ("ftp://example.com", 123, "blackceo.com"):
        ok, detail = raises_code(
            lambda value=bad: V.plan_teaser(AD, MOMENTS, link=value),
            "link_invalid")
        check("bad link %r refused" % (bad,), ok, detail)


def test_cut_window_validation():
    ok, detail = raises_code(lambda: V.cut_window(0.0, 10.0, 12.0), "ad_too_short")
    check("window longer than the ad refused", ok, detail)
    ok, detail = raises_code(lambda: V.cut_window(-1.0, 62.5), "peak_invalid")
    check("negative peak refused", ok, detail)


def test_exports_and_envelope():
    for name in ("TeaserError", "TEASER_SCHEMA", "TEASER_MAX_SECONDS",
                 "END_CARD_TEXT", "END_CARD_HOLD_SECONDS", "CUT_WINDOW_SECONDS",
                 "INSTAGRAM_SEGMENT_SECONDS", "TIKTOK_STORY_MAX_SECONDS",
                 "FACEBOOK_STORY_CLIP_SECONDS", "GBP_REASON", "GBP_CODE",
                 "KIE_PATH", "DEFAULT_CHANNELS", "CHANNEL_POLICY",
                 "story_segments", "pick_peak", "cut_window", "route_channel",
                 "plan_teaser"):
        check("package exports %s" % name, hasattr(PKG, name))
    plan = V.plan_teaser(AD, MOMENTS)
    check("plan carries the schema and unit stamp",
          plan["schema_version"] == V.TEASER_SCHEMA
          and plan["unit_id"] == V.UNIT_ID, str(plan["unit_id"]))
    check("source block keeps the ad identity",
          plan["source"]["ad_id"] == AD["id"]
          and plan["source"]["duration_seconds"] == 62.5, str(plan["source"]))


TESTS = [
    test_free_cut_window_and_end_card,
    test_peak_near_end_clamps_inside_ad,
    test_peak_at_start_and_tie_and_score,
    test_hold_shrinks_window_total_stays_15,
    test_end_card_hold_floor_and_window_refusals,
    test_short_and_bad_ads_refused,
    test_moments_validation,
    test_story_segments_split,
    test_instagram_splits_into_15s_segments,
    test_tiktok_15s_story_limit,
    test_facebook_clip_limit,
    test_google_business_profile_excluded_until_verified,
    test_plan_routing_table,
    test_channel_argument_validation,
    test_zero_paid_calls_and_skill74_only_kie_path,
    test_no_media_files_in_module_dir,
    test_no_operator_paths_and_no_file_writes,
    test_link_validation,
    test_cut_window_validation,
    test_exports_and_envelope,
]


def main():
    for test in TESTS:
        try:
            test()
        except Exception as exc:                          # noqa: BLE001
            check("%s raised" % test.__name__, False,
                  "%s: %s" % (type(exc).__name__, exc))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for name in FAILS:
            print("  FAILED: %s" % name)
        return 1
    print("all %d outcome tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""D27/D35 15-second Stories teaser cut, plan section 6.15. Stdlib only.

Free cut from the weekly drama-song ad: the most intense moment plus a
"watch the full video" end card, sized for Instagram, Facebook and TikTok
Stories. The output is a cut plan (start, end, end card, per-channel
routing) — data, not a render: nothing here writes media, uploads, or
calls a provider, so paid calls stay at zero. Skill 74 (kie-live-adapter)
is the only KIE path in this build and this module never reaches it.

Google Business Profile sits in the planner's Story-capable channel list
but is refused here until its Story length limit is verified (plan 6.15).
"""
from __future__ import annotations

import math
import re
import sys
from pathlib import Path


def _ensure_build_root_on_path():
    """core/ siblings live at the build root. Find it the way core/end_card
    does: walk up to the directory that owns core/artifact_graph.py, so the
    package imports with any single sys.path entry. core/ has no
    __init__.py, so the `core` namespace portions merge across sys.path.
    """
    try:
        from core.delivery_variants.checks import check_cta_hold  # noqa: F401
        return
    except ImportError:
        pass
    for parent in Path(__file__).resolve().parents:
        if (parent / "core" / "artifact_graph.py").is_file():
            if str(parent) not in sys.path:
                sys.path.insert(0, str(parent))
            return
    # leave sys.path alone; the import below reports the real failure


_ensure_build_root_on_path()

from core.delivery_variants.checks import (
    CTA_HOLD_MIN_SECONDS,
    PASS as CTA_PASS,
    check_cta_hold,
)
from core.delivery_variants.variants import ASPECTS, expected_dimensions

TEASER_SCHEMA = "blackceo.smp.stories_teaser/v1"
UNIT_ID = "SMP-W1-U5"
TEASER_MAX_SECONDS = 15.0                # Stories teaser hard length
END_CARD_TEXT = "Watch the full video"   # plan 6.15 end-card copy
END_CARD_HOLD_SECONDS = 3.0              # floor = CTA_HOLD_MIN_SECONDS
CUT_WINDOW_SECONDS = TEASER_MAX_SECONDS - END_CARD_HOLD_SECONDS   # 12.0
INSTAGRAM_SEGMENT_SECONDS = 15.0         # IG splits Stories into 15 s segments
FACEBOOK_STORY_CLIP_SECONDS = 60.0       # FB Stories, 60 s per clip
TIKTOK_STORY_MAX_SECONDS = 15.0          # TikTok Stories 15 s
STORY_ASPECT = "9:16"
GBP_REASON = "Google Business Profile excluded until the Story length limit is verified"
GBP_CODE = "google_business_profile_story_limit_unverified"
KIE_PATH = "skill-74"                    # Skill 74 kie-live-adapter, the only KIE client
DEFAULT_CHANNELS = ("instagram", "facebook", "tiktok", "google_business_profile")
_URL = re.compile(r"^https?://[^/\s?#]+[^\s]*$", re.IGNORECASE)

#: One entry per Story destination Skill 35 publishes to through GoHighLevel.
#: `segment` = platform splits the Story into fixed-length pieces; `clip` =
#: one clip up to the platform limit; `excluded` = never posted here.
CHANNEL_POLICY = {
    "instagram": {
        "mode": "segment",
        "segment_seconds": INSTAGRAM_SEGMENT_SECONDS,
        "platform_limit_seconds": 60.0,
    },
    "facebook": {
        "mode": "clip",
        "platform_limit_seconds": FACEBOOK_STORY_CLIP_SECONDS,
    },
    "tiktok": {
        "mode": "clip",
        "platform_limit_seconds": TIKTOK_STORY_MAX_SECONDS,
    },
    "google_business_profile": {
        "mode": "excluded",
        "code": GBP_CODE,
        "reason": GBP_REASON,
    },
}


class TeaserError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _number(value, code, minimum=None, exclusive_minimum=None):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TeaserError(code, "%r is not a number" % (value,))
    number = float(value)
    if not math.isfinite(number):
        raise TeaserError(code, "%r is not finite" % (value,))
    if minimum is not None and number < minimum:
        raise TeaserError(code, "%.3f below minimum %.3f" % (number, minimum))
    if exclusive_minimum is not None and number <= exclusive_minimum:
        raise TeaserError(code, "%.3f must be above %.3f" % (number, exclusive_minimum))
    return number


def story_segments(duration_seconds, segment_seconds=INSTAGRAM_SEGMENT_SECONDS):
    """Split a Story length into Instagram's 15 s segments (plan 6.15).

    Returns one record per segment: index, start, end. Segments are
    contiguous, never longer than `segment_seconds`, and cover the full
    duration.
    """
    duration = _number(duration_seconds, "duration_invalid", exclusive_minimum=0.0)
    size = _number(segment_seconds, "segment_invalid", exclusive_minimum=0.0)
    count = int(math.ceil(duration / size))
    segments = []
    start = 0.0
    for index in range(1, count + 1):
        end = duration if index == count else start + size
        segments.append({"index": index,
                         "start": round(start, 6),
                         "end": round(end, 6)})
        start = end
    return segments


def pick_peak(moments, duration_seconds):
    """The most intense moment: highest score, earliest start on a tie."""
    duration = _number(duration_seconds, "duration_invalid", exclusive_minimum=0.0)
    if not isinstance(moments, (list, tuple)) or not moments:
        raise TeaserError("no_intensity_moments",
                          "need at least one intensity moment to pick the most intense moment")
    scored = []
    for moment in moments:
        if not isinstance(moment, dict):
            raise TeaserError("moment_invalid", "moment %r is not an object" % (moment,))
        start = _number(moment.get("start"), "moment_invalid", minimum=0.0)
        if start > duration:
            raise TeaserError("moment_invalid",
                              "moment start %.3f is beyond the ad end %.3f" % (start, duration))
        score = _number(moment.get("score"), "moment_invalid")
        scored.append((start, score))
    best = max(scored, key=lambda item: (item[1], -item[0]))
    return {"start": best[0], "score": best[1]}


def cut_window(peak_start, duration_seconds, window_seconds=CUT_WINDOW_SECONDS):
    """Clamp the cut to the ad so the peak always stays inside the window."""
    peak = _number(peak_start, "peak_invalid", minimum=0.0)
    duration = _number(duration_seconds, "duration_invalid", exclusive_minimum=0.0)
    window = _number(window_seconds, "window_invalid", exclusive_minimum=0.0)
    if window > duration:
        raise TeaserError("ad_too_short",
                          "cut window %.3fs is longer than the ad %.3fs" % (window, duration))
    start = min(max(peak, 0.0), duration - window)
    return {"start": round(start, 6),
            "end": round(start + window, 6),
            "duration_seconds": round(window, 6)}


def route_channel(channel, duration_seconds):
    """Post/segment/refuse one Story destination for a teaser of this length."""
    duration = _number(duration_seconds, "duration_invalid", exclusive_minimum=0.0)
    policy = CHANNEL_POLICY.get(channel)
    if policy is None:
        raise TeaserError("unknown_channel",
                          "%r is not a Story destination: %s"
                          % (channel, ", ".join(sorted(CHANNEL_POLICY))))
    if policy["mode"] == "excluded":
        return {"channel": channel, "accepted": False, "segments": 0,
                "code": policy["code"], "reason": policy["reason"]}
    if policy["mode"] == "segment":
        segments = story_segments(duration, policy["segment_seconds"])
        return {"channel": channel, "accepted": True, "segments": len(segments),
                "segment_seconds": policy["segment_seconds"],
                "segment_plan": segments}
    limit = policy["platform_limit_seconds"]
    if duration > limit:
        return {"channel": channel, "accepted": False, "segments": 0,
                "code": "over_%s_story_limit" % channel,
                "reason": "%.3fs exceeds the %.0fs %s Story limit"
                          % (duration, limit, channel)}
    return {"channel": channel, "accepted": True, "segments": 1,
            "clip_max_seconds": limit}


def plan_teaser(ad, moments, channels=None, end_card_hold_seconds=END_CARD_HOLD_SECONDS,
                link=None):
    """Plan the free 15 s Stories cut from an existing ad (plan 6.15).

    `ad` needs `duration_seconds` (and optionally `id`, `aspect`).
    `moments` are intensity markers: `{"start": seconds, "score": number}`.
    Pure data — no file is written, no provider is called, paid_calls is 0.
    """
    if not isinstance(ad, dict):
        raise TeaserError("ad_invalid", "ad %r is not an object" % (ad,))
    duration = _number(ad.get("duration_seconds"), "duration_invalid",
                       exclusive_minimum=0.0)
    hold = _number(end_card_hold_seconds, "end_card_hold_invalid",
                   exclusive_minimum=0.0)
    status, detail = check_cta_hold(hold)
    if status != CTA_PASS:
        raise TeaserError("end_card_hold_below_floor", detail)
    if hold >= TEASER_MAX_SECONDS:
        raise TeaserError("end_card_hold_invalid",
                          "hold %.3fs leaves no cut window under %.0fs"
                          % (hold, TEASER_MAX_SECONDS))
    if duration < TEASER_MAX_SECONDS:
        raise TeaserError("ad_too_short",
                          "ad %.3fs is shorter than the %.0fs teaser" % (duration, TEASER_MAX_SECONDS))
    if link is not None and not (isinstance(link, str) and _URL.match(link)):
        raise TeaserError("link_invalid", "link %r is not an http(s) URL" % (link,))
    if channels is None:
        channels = DEFAULT_CHANNELS
    if isinstance(channels, str) or not isinstance(channels, (list, tuple)) or not channels:
        raise TeaserError("channels_invalid", "channels must be a non-empty list of names")
    unknown = [name for name in channels if name not in CHANNEL_POLICY]
    if unknown:
        raise TeaserError("unknown_channel", "not a Story destination: %s" % (unknown,))
    aspect = ad.get("aspect", STORY_ASPECT)
    if aspect not in ASPECTS:
        raise TeaserError("aspect_invalid", "%r is not an approved aspect" % (aspect,))

    peak = pick_peak(moments, duration)
    window = TEASER_MAX_SECONDS - hold
    cut = cut_window(peak["start"], duration, window)
    teaser_duration = round(cut["duration_seconds"] + hold, 6)
    width, height = expected_dimensions(aspect)

    return {
        "schema_version": TEASER_SCHEMA,
        "unit_id": UNIT_ID,
        "source": {"ad_id": ad.get("id"),
                   "duration_seconds": duration,
                   "aspect": aspect},
        "cut": {"start": cut["start"],
                "end": cut["end"],
                "duration_seconds": cut["duration_seconds"],
                "peak": peak,
                "reason": "most intense moment"},
        "end_card": {"text": END_CARD_TEXT,
                     "start": cut["end"],
                     "duration_seconds": hold,
                     "hold_floor_seconds": CTA_HOLD_MIN_SECONDS},
        "teaser": {"duration_seconds": teaser_duration,
                   "max_seconds": TEASER_MAX_SECONDS,
                   "aspect": aspect,
                   "pixels": "%dx%d" % (width, height)},
        "routing": [route_channel(name, teaser_duration) for name in channels],
        "cost": {"credits": 0, "paid_calls": 0,
                 "kie_dispatch": "not_required", "kie_path": KIE_PATH},
        "link": link,
    }


__all__ = [
    "CHANNEL_POLICY",
    "CUT_WINDOW_SECONDS",
    "DEFAULT_CHANNELS",
    "END_CARD_HOLD_SECONDS",
    "END_CARD_TEXT",
    "FACEBOOK_STORY_CLIP_SECONDS",
    "GBP_CODE",
    "GBP_REASON",
    "INSTAGRAM_SEGMENT_SECONDS",
    "KIE_PATH",
    "STORY_ASPECT",
    "TEASER_MAX_SECONDS",
    "TEASER_SCHEMA",
    "TIKTOK_STORY_MAX_SECONDS",
    "UNIT_ID",
    "TeaserError",
    "cut_window",
    "pick_peak",
    "plan_teaser",
    "route_channel",
    "story_segments",
]

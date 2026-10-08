#!/usr/bin/env python3
"""length_routing.py — Skill 35 planner length rules and per-channel routing.

Wave unit SMP-W1-U4. Source: Owner D27 / D35, plan section 6.15, decision
log 35 (2026-10-07).

What it decides, in the order the planner asks:

1. **59.0 second hard cap.** The planner version of the weekly drama song
   must END by 59.0 seconds. GoHighLevel publishes YouTube Shorts and the
   Instagram feed at 60 seconds, so the render is held one tenth under that
   line. Approved ads run 62-63 seconds — over the cap *and* over the 60
   second Shorts/feed limit — so a planner version in that range is refused
   by name rather than silently routed somewhere it does not belong.

2. **90-second option route.** The 90-second option posts ONLY to Facebook
   Reels, Instagram Reels, TikTok and LinkedIn — never to YouTube Shorts and
   never to the Instagram feed. Threads is deliberately outside the
   90-second option even though its own limit is 5 minutes: the option list
   is an explicit allow-list from the owner plan, not the output of a limit
   calculation. The per-channel table below still governs every other
   duration (a 120 second clip still reaches Threads).

3. **Per-channel length routing table** (GoHighLevel, checked 2026-10-07):

   ==================  ==============  =========================
   channel             min seconds     max seconds
   ==================  ==============  =========================
   YouTube Shorts      0               60
   Instagram feed      0               60
   Facebook Reels      3               90
   TikTok              3               180
   Instagram Reels     0               900   (15 minutes)
   LinkedIn            0               1800  (30 minutes)
   Threads             0               300   (5 minutes)
   ==================  ==============  =========================

   Google Business Profile is refused until its limit is verified in the
   GoHighLevel documentation, and every Stories surface carries the
   15-second teaser only (SMP-W1-U5) — both with the client-facing reason.

Skill 74 is the only KIE path, and this module never reaches KIE at all: no
key, no host, no second client, no transport of any kind. It is pure data
plus pure functions, so the mocked tests make zero paid calls. stdlib only.
"""
from __future__ import annotations

import math

SCHEMA_VERSION = "blackceo.smp-length-routing/v1"
TOOL_VERSION = "0.1.0"
SOURCE = "Owner D27 / D35 plan 6.15 decision 35 (2026-10-07)"
SHAPE = "9:16"

KIE_PATH = "skill-74"          # the kie-live-adapter: the only KIE client
KIE_DISPATCH = "not_required"  # routing is pure data; nothing is dispatched

# --- length rules (plan 6.15) ----------------------------------------------

HARD_CAP_S = 59.0                    # the planner version must END by this
PLAN_OPTIONS_S = (60, 90)            # the only two lengths Skill 35 offers
NINETY_WINDOW_S = (88.0, 95.0)       # where the 90-second option must land
APPROVED_AD_RANGE_S = (62.0, 63.0)   # approved ads run 62-63 seconds

# --- per-channel routing table (GoHighLevel, checked 2026-10-07) -----------

# channel -> (min_seconds, max_seconds)
CHANNEL_LIMITS = {
    "YouTube Shorts": (0.0, 60.0),
    "Instagram feed": (0.0, 60.0),
    "Facebook Reels": (3.0, 90.0),
    "TikTok": (3.0, 180.0),
    "Instagram Reels": (0.0, 900.0),
    "LinkedIn": (0.0, 1800.0),
    "Threads": (0.0, 300.0),
}

# The two weekly options, as explicit allow-lists. 60 seconds reaches every
# feed surface; the 90-second option is ONLY the four named below.
OPTION_60_CHANNELS = tuple(CHANNEL_LIMITS)
OPTION_90_CHANNELS = (
    "Facebook Reels",
    "Instagram Reels",
    "TikTok",
    "LinkedIn",
)

# Destinations that never take the weekly ad, with the client-facing reason.
NEVER = {
    "Google Business Profile": (
        "Google Business Profile video limit is not verified in the "
        "GoHighLevel documentation; do not post until a limit is verified"
    ),
}
STORIES_SUFFIX = " Stories"
TEASER_REASON = (
    "Stories carry the 15-second teaser only, never the full weekly ad"
)

NOT_A_DESTINATION = "%s is not a Skill 35 destination in this routing table"


def _seconds(value):
    """Seconds as a float, or None when the value is not a finite number."""
    if value is None or isinstance(value, bool):
        return None
    try:
        secs = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(secs):
        return None
    return secs


def _fmt(seconds):
    """Human seconds: 59 -> '59', 62.5 -> '62.5', 900 -> '900'."""
    return "%g" % seconds


def validate_duration(duration, option):
    """(ok, reason) — the planner-side gate that runs *before* any routing.

    option 60 is capped at HARD_CAP_S. option 90 must land inside
    NINETY_WINDOW_S. Anything else — including a duration that is not a
    number — is refused by name instead of guessed at.
    """
    secs = _seconds(duration)
    if secs is None:
        return False, "duration must be a number of seconds; got %r" % (
            duration,
        )
    if secs < 0:
        return False, "duration must not be negative; got %s seconds" % (
            _fmt(secs),
        )
    if option not in PLAN_OPTIONS_S:
        return False, "length option must be one of %s seconds; got %r" % (
            " or ".join(_fmt(o) for o in PLAN_OPTIONS_S), option,
        )
    if option == 60:
        if secs <= HARD_CAP_S:
            return True, ""
        if APPROVED_AD_RANGE_S[0] <= secs <= APPROVED_AD_RANGE_S[1]:
            return False, (
                "approved ads run %s-%s seconds, which is over the %.1f "
                "second planner cap: YouTube Shorts and the Instagram feed "
                "take 60 seconds or less, so the planner version must end "
                "by %.1f seconds, got %s"
                % (_fmt(APPROVED_AD_RANGE_S[0]), _fmt(APPROVED_AD_RANGE_S[1]),
                   HARD_CAP_S, HARD_CAP_S, _fmt(secs))
            )
        return False, (
            "the planner version must end by %.1f seconds (GoHighLevel: "
            "YouTube Shorts and the Instagram feed take 60 seconds or "
            "less); got %s" % (HARD_CAP_S, _fmt(secs))
        )
    low, high = NINETY_WINDOW_S
    if low <= secs <= high:
        return True, ""
    return False, (
        "the 90 second option must land in the %.1f to %.1f second "
        "window; got %s" % (low, high, _fmt(secs))
    )


def channels_for_option(option):
    """The explicit allow-list for one weekly option, every feed surface.

    60 seconds: all seven destinations. 90 seconds: Facebook Reels,
    Instagram Reels, TikTok and LinkedIn only. Any other option is refused
    by name (ValueError) rather than silently mapped onto one of these.
    """
    if option == 60:
        return OPTION_60_CHANNELS
    if option == 90:
        return OPTION_90_CHANNELS
    raise ValueError(
        "length option must be one of %s seconds; got %r"
        % (" or ".join(_fmt(o) for o in PLAN_OPTIONS_S), option)
    )


def _decide_channel(name, secs):
    """(allowed, reason) for one channel at one duration."""
    if name in NEVER:
        return False, NEVER[name]
    if name.endswith(STORIES_SUFFIX):
        return False, TEASER_REASON
    limits = CHANNEL_LIMITS.get(name)
    if limits is None:
        return False, NOT_A_DESTINATION % name
    low, high = limits
    # Platform limit first: a limit breach is the honest reason, and it is
    # what YouTube Shorts and the Instagram feed report at any length over 60.
    if secs < low:
        return False, "%s takes %s seconds or more; got %s" % (
            name, _fmt(low), _fmt(secs),
        )
    if secs > high:
        if high == 60.0:
            return False, (
                "%s accepts 60 seconds or less, so the %s second version "
                "cannot post there" % (name, _fmt(secs))
            )
        return False, "%s tops out at %s seconds; got %s" % (
            name, _fmt(high), _fmt(secs),
        )
    # Inside every platform limit: the 90-second option allow-list still
    # governs anything that landed in its acceptance window.
    low_w, high_w = NINETY_WINDOW_S
    if low_w <= secs <= high_w and name not in OPTION_90_CHANNELS:
        return False, (
            "%s is not in the 90 second option route: that option posts "
            "only to %s" % (name, ", ".join(OPTION_90_CHANNELS))
        )
    return True, "%s second weekly drama song accepted by %s" % (
        _fmt(secs), name,
    )


def route_channels(length, connected):
    """One row per connected channel: {channel, allowed, reason}.

    Every row carries a reason, allowed or not, so the planner schedule can
    show the client exactly why a surface was skipped. This is the interface
    `core/smp/weekly_step` (SMP-W1-U1) binds to; this unit is the authority
    on the table.
    """
    secs = _seconds(length)
    if secs is None:
        bad = "duration must be a number of seconds; got %r" % (length,)
    elif secs < 0:
        bad = "duration must not be negative; got %s seconds" % _fmt(secs)
    else:
        bad = None
    if isinstance(connected, str):
        connected = [connected]
    plan = []
    for channel in list(connected or ()):
        name = str(channel).strip() if channel is not None else ""
        if not name:
            continue
        if bad is not None:
            allowed, reason = False, bad
        else:
            allowed, reason = _decide_channel(name, secs)
        plan.append(
            {"channel": name, "allowed": allowed, "reason": reason}
        )
    return plan


# The three names the wave's router interface looks for; one function.
channel_acceptance = route_channels
route = route_channels

__all__ = [
    "APPROVED_AD_RANGE_S",
    "CHANNEL_LIMITS",
    "HARD_CAP_S",
    "KIE_DISPATCH",
    "KIE_PATH",
    "NINETY_WINDOW_S",
    "NEVER",
    "OPTION_60_CHANNELS",
    "OPTION_90_CHANNELS",
    "PLAN_OPTIONS_S",
    "SCHEMA_VERSION",
    "SHAPE",
    "SOURCE",
    "STORIES_SUFFIX",
    "TEASER_REASON",
    "TOOL_VERSION",
    "channel_acceptance",
    "channels_for_option",
    "route",
    "route_channels",
    "validate_duration",
]

"""length_routing — Skill 35 planner length rules and per-channel routing.

Wave unit SMP-W1-U4, Owner D27 / D35 plan section 6.15 decision 35
(2026-10-07).

Exports the three pieces the weekly planner needs:

- ``validate_duration(duration, option)`` — the 59.0 second hard cap for the
  60-second option and the acceptance window for the 90-second option;
- ``route_channels(length, connected)`` (also exported as
  ``channel_acceptance`` and ``route``, the names the wave's router
  interface looks for) — one ``{channel, allowed, reason}`` row per connected
  channel, from the per-channel length routing table;
- ``channels_for_option(option)`` — the explicit allow-list for each weekly
  option: 60 seconds reaches all seven destinations, 90 seconds posts only
  to Facebook Reels, Instagram Reels, TikTok and LinkedIn.

Skill 74 is the only KIE path; this package never reaches KIE, holds no key
and makes no paid call. stdlib only, pure data, no file writes.
"""
from .length_routing import (
    APPROVED_AD_RANGE_S,
    CHANNEL_LIMITS,
    HARD_CAP_S,
    KIE_DISPATCH,
    KIE_PATH,
    NINETY_WINDOW_S,
    NEVER,
    OPTION_60_CHANNELS,
    OPTION_90_CHANNELS,
    PLAN_OPTIONS_S,
    SCHEMA_VERSION,
    SHAPE,
    SOURCE,
    STORIES_SUFFIX,
    TEASER_REASON,
    TOOL_VERSION,
    channel_acceptance,
    channels_for_option,
    route,
    route_channels,
    validate_duration,
)

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

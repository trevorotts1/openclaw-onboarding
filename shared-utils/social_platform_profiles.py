#!/usr/bin/env python3
"""
social_platform_profiles.py — F39 versioned platform strategy profile loader.

Loads 35-social-media-planner/config/platform-capabilities.json, enforces
profile freshness (checked_at vs the policy staleness window), and returns the
selected profile for a platform with:
  - profile_version + checked_at (recorded into the content contract),
  - supported GHL formats / unsupported native features,
  - organic vs advertising guidance kept separate.

Freshness contract (SPEC "Platform strategy matrix ... continued"):
  - a stale profile (checked_at older than the policy window) triggers a
    refresh task; until the refresh succeeds the LAST VERIFIED SAFE profile
    keeps serving (never stops otherwise valid client publishing);
  - an unsupported native-only format yields the supported alternative or an
    isolated attention state — never a silent drop and never a block on other
    channels.

STDLIB ONLY.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Optional

_CAPS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "..", "35-social-media-planner", "config",
                          "platform-capabilities.json")
_POLICY_CACHE: Optional[dict] = None


def load_profiles(path: Optional[str] = None) -> dict:
    """Load the versioned platform capability profiles (cached)."""
    global _POLICY_CACHE
    if _POLICY_CACHE is None or path:
        p = path or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "35-social-media-planner", "config",
                                 "platform-capabilities.json")
        try:
            with open(p) as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        _POLICY_CACHE = data
        return data
    return _POLICY_CACHE


def profile_is_stale(profile: dict, now: Optional[datetime.datetime] = None) -> bool:
    """True iff checked_at is older than the policy staleness window."""
    pol = load_profiles().get("policy", {})
    window = int(pol.get("stale_after_days", 45))
    try:
        checked = _dt.date.fromisoformat(str(profile.get("checked_at", ""))[:10])
    except ValueError:
        return True  # unparsable date = stale (fail toward refresh)
    today = now.date() if isinstance(now, _dt.datetime) else (now or _dt.date.today())
    if isinstance(today, _dt.datetime):
        today = today.date()
    return (today - checked).days > window


def select_profile(platform: str, now: Optional[_dt.datetime] = None) -> dict:
    """Select the strategy profile for `platform` and evaluate freshness.

    Returns {platform, profile_version, checked_at, stale, source_urls,
    supported_formats, unsupported_features, organic_guidance,
    advertising_guidance, format_rules, measurement_goals, timing_policy,
    actions[]} — actions name the refresh task when stale, or the approved
    supported variant / unavailable mark when a requested format is not
    supported. NEVER raises for a stale profile: the last verified safe
    profile continues to be used.
    """
    caps = load_profiles()
    profiles = caps.get("profiles") or {}
    pid = (platform or "").strip().lower()
    if pid not in profiles:
        return {"platform": pid, "found": False, "needs_adapter": True,
                "actions": [{
                    "type": "create_profile_task",
                    "detail": (f"no reviewed capability/strategy profile for "
                               f"'{pid}' — produce a clearly labeled draft and "
                               "create an adapter/profile task for that channel; "
                               "never fabricate channel support.")}]}
    p = profiles[pid]
    stale = profile_is_stale(p, now)
    actions = []
    if stale:
        actions.append({
            "type": "refresh_profile",
            "detail": (f"profile for {pid} is stale (checked_at "
                       f"{p.get('checked_at')}) — refresh task created; the last "
                       "verified safe profile continues to be used."),
        })
    return {
        "platform": pid,
        "found": True,
        "profile_version": p.get("profile_version"),
        "checked_at": p.get("checked_at"),
        "stale": stale,
        "source_urls": p.get("source_urls"),
        "supported_formats": list(p.get("ghl_supported_formats") or []),
        "unsupported_features": list(p.get("ghl_unsupported_native_features") or []),
        "organic_guidance": p.get("organic_guidance_summary"),
        "advertising_guidance": p.get("advertising_guidance_summary"),
        "format_rules": p.get("format_rules"),
        "measurement_goals": p.get("measurement_goals"),
        "timing_policy": p.get("timing_policy"),
        "actions": actions,
    }


def resolve_format(profile: dict, requested_format: str) -> dict:
    """Resolve a requested native format against the profile's GHL support.

    Supported → {supported: True, format}. Unsupported → the approved supported
    variant (first supported format) or an explicit unavailable mark — NEVER a
    block on other channels and NEVER a silent drop.
    """
    fmt = (requested_format or "").strip().lower()
    supported = [f.lower() for f in profile.get("supported_formats", [])]
    unsupported = [f.lower() for f in profile.get("unsupported_features", [])]
    if fmt in supported:
        return {"supported": True, "format": fmt}
    # A profile may declare the WHOLE platform unsupported through the adapter
    # (e.g. Threads pending active GHL support) — every requested format is
    # then an isolated unavailable mark, other channels continue.
    all_unsupported = any("all" in u for u in unsupported)
    if fmt and (fmt in unsupported or (all_unsupported and fmt not in supported)):
        if supported:
            return {
                "supported": False, "requested": fmt,
                "approved_variant": supported[0],
                "detail": (f"'{fmt}' is not supported through the active adapter "
                           f"on this platform — the approved supported variant is "
                           f"'{supported[0]}'; this one capability is marked "
                           "unavailable and other channels continue."),
            }
        return {
            "supported": False, "requested": fmt, "unavailable": True,
            "detail": (f"'{fmt}' is unavailable through the active adapter and the "
                       "platform has no supported formats — this platform's "
                       "capability is marked unavailable; other channels continue."),
        }
    return {"supported": False, "requested": fmt,
            "detail": f"'{fmt}' is not a format this profile declares — "
                      "present the supported alternative before production."}


def record_in_contract(profile: dict) -> dict:
    """The content-contract provenance block: which verified profile version
    produced the content (F39 requirement: retain evidence of the version)."""
    return {
        "profile_platform": profile.get("platform"),
        "profile_version": profile.get("profile_version"),
        "profile_checked_at": profile.get("checked_at"),
        "profile_source_urls": profile.get("source_urls"),
    }


if __name__ == "__main__":  # pragma: no cover
    import sys
    pid = sys.argv[1] if len(sys.argv) > 1 else "instagram"
    import pprint
    pprint.pp(select_profile(pid))
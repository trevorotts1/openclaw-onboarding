#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: two-show channel selector
# -----------------------------------------------------------------------------
# Selects the Podbean Channel ID (podcast_id) BY MODE for the publish step,
# per the fleet-wide two-show convention. Source of the convention at build
# time of this unit: SKILL.md (two-show section; branch fix/podcast-audit-t4-
# two-show-convention, co-landing in the same merge batch),
# config/payload-schema.json (podcast_id description; branch fix/podcast-audit-
# t7-payload-schema), and universal-sops/podcast-craft/SOP-PODCAST-02-CLIENT-
# ONBOARDING.md Section 2.5 (branch fix/podcast-audit-t5-sop02-two-shows).
#
# Every client runs TWO shows under the operator's single Podbean host
# account, one channel per show:
#
#   personal mode   (personal_podcast_style)   -> the client's PERSONAL show
#                                                 channel, carried by the env
#                                                 var PODBEAN_PODCAST_ID (the
#                                                 default channel).
#   interview mode  (interview_style_podcast)  -> the client's INTERVIEW show
#                                                 channel, carried by the env
#                                                 var PODBEAN_PODCAST_ID_<SHOW_SLUG>
#                                                 where SHOW_SLUG is the
#                                                 interview show's slug in
#                                                 uppercase, underscore
#                                                 separated form, for example
#                                                 PODBEAN_PODCAST_ID_SOFT_GIRL_ERA.
#
# The publish step passes the mode-selected channel as the payload's
# podcast_id, and the operator's n8n publish gate matches the client's roster
# rows by identity plus channel (channel-preferred selection with a legacy
# fallback for single-row clients). That only resolves correctly when the
# podcast_id here is the channel the episode's mode belongs to; this resolver
# therefore never falls back to the other show's channel. A mode-to-channel
# mismatch is a provisioning defect to fix, never something the engine works
# around.
#
# CLI usage (offline; env labels only, no values ever printed):
#
#   podcast_channel.py --mode personal --check
#       Exit 0 when the personal channel resolves, nonzero with the exact
#       missing env var NAME in the message otherwise.
#   podcast_channel.py --mode interview --show-name "Soft Girl Era" --check
#       Same guarantee for the interview channel env var.
#   podcast_channel.py --mode interview --show-name "Soft Girl Era"
#       Prints the resolved channel id (the only case where a value leaves the
#       script; used by the controller and publish glue to build the payload).
#   podcast_channel.py --mode interview --show-name "Soft Girl Era" --print-var
#       Prints only the env var NAME (label-only probe; no value at all).
#
# Stdlib only. Static and deterministic: no network, no secrets, no
# model/provider name in this runtime helper.
# =============================================================================
"""Two-show channel selection for the podcast engine (mode -> Podbean channel)."""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Mapping, Optional, Tuple

__all__ = [
    "MODE_PERSONAL",
    "MODE_INTERVIEW",
    "DEFAULT_CHANNEL_ENV",
    "MODE_ENV_KEY",
    "ChannelError",
    "UnknownModeError",
    "UnknownShowError",
    "normalize_mode",
    "show_slug",
    "channel_env_key",
    "resolve_channel",
]

# The two canonical mode values (payload-schema.json enum).
MODE_PERSONAL = "personal_podcast_style"
MODE_INTERVIEW = "interview_style_podcast"

# Human forms accepted at intake, normalized to the enum values
# (payload-schema.json mode description).
_HUMAN_MODE_ALIASES = {
    "personal": MODE_PERSONAL,
    "personal podcast": MODE_PERSONAL,
    "personal_podcast": MODE_PERSONAL,
    "solo": MODE_PERSONAL,
    "interview": MODE_INTERVIEW,
    "interview style podcast": MODE_INTERVIEW,
    "interview_style_podcast": MODE_INTERVIEW,
    "interview podcast": MODE_INTERVIEW,
}

# PODBEAN_PODCAST_ID holds the DEFAULT channel, which the fleet convention
# assigns to the personal show; each additional show gets its own
# PODBEAN_PODCAST_ID_<SHOW_SLUG> variable (SKILL.md two-show model,
# SOP-PODCAST-02 Section 2.5 step 3).
DEFAULT_CHANNEL_ENV = "PODBEAN_PODCAST_ID"
MODE_ENV_KEY = {
    MODE_PERSONAL: DEFAULT_CHANNEL_ENV,
    MODE_INTERVIEW: "PODBEAN_PODCAST_ID_<SHOW_SLUG>",
}


class ChannelError(ValueError):
    """Base for channel-selection failures (message names env labels only)."""


class UnknownModeError(ChannelError):
    """The mode is not one of the two production modes."""


class UnknownShowError(ChannelError):
    """Interview mode was asked but no interview show identifier was supplied."""


def normalize_mode(mode: str) -> str:
    """Normalize a mode string to its canonical payload enum value.

    Accepts the two enum values plus the human forms the mapper accepts at
    intake (Personal, Personal Podcast, Interview, Interview Style Podcast),
    case-insensitive and whitespace-tolerant. Raises UnknownModeError for
    anything else, including season_strategy and episode_asset_pack presets:
    they produce no published episode and therefore have no channel.
    """
    if mode is None:
        raise UnknownModeError(
            "mode is empty; expected personal_podcast_style or interview_style_podcast"
        )
    key = " ".join(str(mode).strip().lower().split())
    if key in (MODE_PERSONAL, MODE_INTERVIEW):
        return key
    mapped = _HUMAN_MODE_ALIASES.get(key)
    if mapped is not None:
        return mapped
    raise UnknownModeError(
        "mode %r is not a production mode; expected %s or %s"
        % (mode, MODE_PERSONAL, MODE_INTERVIEW)
    )


def show_slug(show_name: str) -> str:
    """Derive the SHOW_SLUG used in PODBEAN_PODCAST_ID_<SHOW_SLUG>.

    The show name in uppercase, underscore separated form: lowercase, every run
    of non-alphanumeric characters collapses to one underscore, leading and
    trailing underscores dropped. Example: "Soft Girl Era" -> SOFT_GIRL_ERA.
    """
    slug = re.sub(r"[^a-z0-9]+", "_", str(show_name).strip().lower()).strip("_")
    return slug.upper()


def channel_env_key(mode: str, show_name: str = "") -> str:
    """Return the env var NAME (label only, never a value) that carries the
    channel for this mode. Interview mode requires a show identifier; personal
    mode ignores it. Raises UnknownShowError when interview mode has none."""
    normalized = normalize_mode(mode)
    if normalized == MODE_PERSONAL:
        return DEFAULT_CHANNEL_ENV
    slug = show_slug(show_name)
    if not slug:
        raise UnknownShowError(
            "interview mode needs the interview show name (or the explicit slug) "
            "to build PODBEAN_PODCAST_ID_<SHOW_SLUG>; none was supplied"
        )
    return "PODBEAN_PODCAST_ID_" + slug


def resolve_channel(
    mode: str,
    show_name: str = "",
    env: Optional[Mapping[str, str]] = None,
    payload_podcast_id: str = "",
) -> Tuple[str, str]:
    """Resolve the mode-selected Podbean Channel ID (the payload's podcast_id).

    Precedence: an explicit non-empty payload_podcast_id wins as-is (the
    controller already resolved it, or the operator overrode it; the value is
    never guessed here anyway). Otherwise the env var for the mode is read:
    PODBEAN_PODCAST_ID for personal mode, PODBEAN_PODCAST_ID_<SHOW_SLUG> for
    interview mode.

    Returns (channel_id, env_var_name). Raises UnknownModeError on a bad mode,
    UnknownShowError when interview mode lacks a show identifier, and
    ChannelError naming the exact missing env var otherwise. There is NO
    cross-show fallback: a missing interview channel never borrows
    PODBEAN_PODCAST_ID, and vice versa; that would publish an episode to the
    wrong show.
    """
    key = channel_env_key(mode, show_name)
    value = (payload_podcast_id or "").strip()
    if value:
        return value, key
    store = os.environ if env is None else env
    value = str(store.get(key) or "").strip()
    if not value:
        raise ChannelError(
            "%s is not set; the two-show convention requires it for mode %s "
            "(capture the channel at onboarding; the resolver never guesses "
            "and never borrows the other show's channel)"
            % (key, normalize_mode(mode))
        )
    return value, key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="podcast_channel.py",
        description="Select the Podbean Channel ID (podcast_id) BY MODE per the "
        "two-show convention: personal mode reads PODBEAN_PODCAST_ID, interview "
        "mode reads PODBEAN_PODCAST_ID_<SHOW_SLUG>. Never guesses, never falls "
        "back to the other show's channel.",
    )
    parser.add_argument("--mode", required=True,
                        help="production mode (personal_podcast_style or "
                             "interview_style_podcast; human forms accepted)")
    parser.add_argument("--show-name", default="",
                        help="the interview show name (or explicit slug) used to "
                             "build PODBEAN_PODCAST_ID_<SHOW_SLUG>; interview "
                             "mode only")
    parser.add_argument("--show-slug", default="",
                        help="explicit SHOW_SLUG override; takes precedence over "
                             "--show-name derivation")
    parser.add_argument("--payload-podcast-id", default="",
                        help="an already-resolved channel id; wins as-is over env")
    parser.add_argument("--check", action="store_true",
                        help="probe only: exit 0 when the mode's channel resolves, "
                             "nonzero naming the missing env var; prints nothing")
    parser.add_argument("--print-var", action="store_true",
                        help="print only the env var NAME for the mode (label-only "
                             "probe), never a value")
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    show_key = args.show_slug or args.show_name
    try:
        key = channel_env_key(args.mode, show_key)
        if args.print_var:
            print(key)
            return 0
        channel, _ = resolve_channel(
            args.mode,
            show_key,
            payload_podcast_id=args.payload_podcast_id,
        )
    except ChannelError as exc:
        if args.check:
            # A label-only diagnosis: the message names the env var, no value.
            print("CHANNEL CHECK FAILED: %s" % (exc,), file=sys.stderr)
            return 1
        raise

    if args.check:
        # SET-or-NOT-SET only; the value itself is never printed on a probe.
        print("CHANNEL CHECK OK: %s is SET for mode %s" % (key, normalize_mode(args.mode)))
        return 0
    print(channel)
    return 0


if __name__ == "__main__":
    sys.exit(main())

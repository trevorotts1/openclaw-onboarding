#!/usr/bin/env python3
"""speed.py: pure send-and-read rules for the KIE dispatch path.

Plan 06 F-SPD-1..3 (blast, tiered poll, chain child), F-SPD-7 (ledger
stamps), and plan section 9 rows N-79 (one burst, paced 20 per 15 s, no
drip), N-80 (outlier re-send), N-87 (spend guard), N-88 (resubmit at
once), N-92 (read by expected finish, clip length shot+1), N-97 (slow
route head start), 10B/10D.

Every function is pure: no clock unless a `now` is passed, no sleep, no
network, no spend. Callers do the sleeping and the sending.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

TOOL_NAME = "speed"
TOOL_VERSION = "1.0.0"

_HERE = Path(__file__).resolve()
SPEED_LIMITS_PATH = _HERE.parents[3] / "references" / "speed-limits.json"

# Static fallback mirrors references/speed-limits.json. A missing or
# unreadable file falls back to these, never to zero.
_DEFAULT = {
    "pacing": {"requests_per_window": 20, "window_seconds": 15.0},
    "poll_tiers_seconds": [2.0, 5.0, 10.0],
    "poll_early_window_seconds": 30.0,
    "poll_tier_mid_seconds": 180.0,
    "outlier": {"limits_seconds": {"picture": 120, "h3_image_to_video": 600,
                                   "nine_picture": 1320, "lipsync": 420,
                                   "lipsync_long": 600},
                "resends": 1},
    "resubmit": {"max_tries": 2, "overloaded_max_sends": 5,
                 "overloaded_interval_seconds": 30},
    "spend_guard": {"ceiling_multiple": 1.5, "warn_fraction": 0.8,
                    "stop_fraction": 1.0, "remake_rounds": 1},
    "chain_child": {"max_seconds_after_parent": 60},
    "upload_freshness_hours": 23,
    "clip_length": {"shot_plus_seconds": 1, "camera_move_extra_seconds": 2},
    "slow_route_head_start": {
        "routes": ["nine-picture", "long-take"],
        "requires_owner_choice": "go ahead if every check passes"},
}


def load_limits(path=None):
    """The speed limits dict; the JSON file when readable, else the fallback."""
    p = Path(path or SPEED_LIMITS_PATH)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return dict(_DEFAULT)
    if not isinstance(data, dict):
        return dict(_DEFAULT)
    merged = dict(_DEFAULT)
    merged.update(data)
    return merged


def pacing(limits=None):
    """(requests, window_seconds) - the one send pace everywhere (N-79)."""
    lim = limits if isinstance(limits, dict) else load_limits()
    raw = lim.get("pacing") or {}
    try:
        req = int(raw.get("requests_per_window") or 20)
        win = float(raw.get("window_seconds") or 15.0)
    except (TypeError, ValueError):
        req, win = 20, 15.0
    return req, win


def poll_interval_s(elapsed_s, limits=None):
    """Tiered poll cadence (F-SPD-2): 2 s early, then 5 s, then 10 s.

    elapsed_s: seconds since the burst was sent. An unreadable elapsed
    reads the slowest tier - never a busy loop.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    tiers = lim.get("poll_tiers_seconds") or [2.0, 5.0, 10.0]
    try:
        early = float(lim.get("poll_early_window_seconds") or 30.0)
        mid = float(lim.get("poll_tier_mid_seconds") or 180.0)
        e = float(elapsed_s)
    except (TypeError, ValueError):
        return float(tiers[-1])
    if e < 0:
        return float(tiers[0])
    if e < early:
        return float(tiers[0])
    if e < mid:
        return float(tiers[1])
    return float(tiers[-1])


#: The plan's job-kind spellings -> the limits table's key (N-80). Without
#: this, "h3" or "lip-sync" would miss the table and fall to the slowest
#: limit (1320 s), firing the one re-send far too late.
_OUTLIER_KINDS = {
    "picture": "picture", "image": "picture",
    "h3": "h3_image_to_video", "h3_image-to-video": "h3_image_to_video",
    "h3_image_to_video": "h3_image_to_video",
    "nine": "nine_picture", "nine-picture": "nine_picture",
    "nine_picture": "nine_picture", "long_take": "nine_picture",
    "long-take": "nine_picture",
    "lip_sync": "lipsync", "lip-sync": "lipsync", "lipsync": "lipsync",
    "lipsync_long": "lipsync_long",
}


def outlier_limit_s(job_kind, limits=None, stamped_limit_s=None):
    """The re-send point (N-80), in seconds.

    The table's seconds ARE twice the model's nine-in-ten time - the plan
    prints 120 / 600 / 1320 / 420 for picture / H3 / nine-picture / lip-sync -
    so they are used directly, never multiplied again. A run may stamp its
    own measured limit for a length it has run before; that wins. Unknown
    kind falls to the slowest known limit.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    if isinstance(stamped_limit_s, (int, float)) and not isinstance(
            stamped_limit_s, bool) and stamped_limit_s > 0:
        return float(stamped_limit_s)
    table = (lim.get("outlier") or {}).get("limits_seconds") or {}
    key = _OUTLIER_KINDS.get(str(job_kind or "").lower(),
                             str(job_kind or "").lower())
    base = table.get(key)
    if base is None:
        base = max([v for v in table.values() if isinstance(v, (int, float))]
                   or [600])
    return float(base)


def outlier_resend_due(elapsed_s, job_kind, limits=None,
                       stamped_limit_s=None):
    """True when a job passed twice its nine-in-ten time: ONE re-send (N-80)."""
    if not isinstance(elapsed_s, (int, float)) or isinstance(elapsed_s, bool):
        return False
    return float(elapsed_s) >= outlier_limit_s(job_kind, limits,
                                               stamped_limit_s)


def chain_child_late(parent_landed_at, child_submitted_at, limits=None):
    """(ok, code) for a chain child (F-SPD-3 / S01 rules 1 and 5).

    A chain child submits within 60 s of the parent landing. A child with
    no timestamps, or one submitted before its parent landed, is late -
    fail closed, never silently pass.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    try:
        max_s = float((lim.get("chain_child") or {}).get(
            "max_seconds_after_parent") or 60)
        p = float(parent_landed_at)
        c = float(child_submitted_at)
    except (TypeError, ValueError):
        return False, "CHAIN_CHILD_LATE"
    if c < p or (c - p) > max_s:
        return False, "CHAIN_CHILD_LATE"
    return True, ""


def spend_guard(balance, estimate, limits=None):
    """N-87: (status, ceiling, code) for one burst.

    balance/estimate in credits. Ceiling is the estimate plus one remake
    round times the ceiling multiple. status: 'ok' | 'warn' | 'stop'.
    An unreadable balance or estimate is 'stop' - never a silent park,
    never a spend on a number nobody checked.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    sg = lim.get("spend_guard") or {}
    try:
        mult = float(sg.get("ceiling_multiple") or 1.5)
        warn = float(sg.get("warn_fraction") or 0.8)
        stop = float(sg.get("stop_fraction") or 1.0)
        rounds = int(sg.get("remake_rounds") or 1)
        est = float(estimate)
        bal = float(balance)
    except (TypeError, ValueError):
        return "stop", None, "SPEND_GUARD_UNREADABLE"
    if est < 0 or bal < 0:
        return "stop", None, "SPEND_GUARD_UNREADABLE"
    ceiling = est * mult
    need = est * (1 + rounds)
    if bal < need or ceiling <= 0:
        return "stop", ceiling, "SPEND_GUARD_BALANCE_LOW"
    used = est / ceiling if ceiling else 1.0
    if used >= stop:
        return "stop", ceiling, "SPEND_GUARD_CEILING"
    if used >= warn:
        return "warn", ceiling, "SPEND_GUARD_EIGHTY"
    return "ok", ceiling, ""


def clip_seconds_for(shot_seconds, camera_move=False, limits=None):
    """N-92 / rule H8: ask for the shot plus 1 s; a camera move may need more."""
    lim = limits if isinstance(limits, dict) else load_limits()
    cl = lim.get("clip_length") or {}
    try:
        base = float(shot_seconds)
        plus = float(cl.get("shot_plus_seconds") or 1)
        extra = float(cl.get("camera_move_extra_seconds") or 2)
    except (TypeError, ValueError):
        return None
    want = base + plus + (extra if camera_move else 0.0)
    return want


def status_read_due(expected_finish_at, now, job_kind=None, limits=None):
    """N-92: read a job's status by its expected finish time, not on a timer.

    Never read a nine-picture job before 4 minutes, nor a picture before
    40 s (plan 10B item 4). Due at expected finish; unreadable times are
    not due (a caller keeps its last known plan).
    """
    floors = {"picture": 40, "nine_picture": 240}
    try:
        due_at = float(expected_finish_at)
        t = float(now)
    except (TypeError, ValueError):
        return False
    floor = floors.get(str(job_kind or "").lower(), 0)
    return t >= max(due_at, floor)


def resubmit_plan(failure_code, sends_used, paid_takes_used=0, limits=None):
    """N-88: resubmit a failed/refused job at once, up to twice.

    An OmniHuman 'overloaded' refusal costs 0 and does not count against
    the two-try rule: up to 5 sends, 30 s apart (section 3C.1a).
    Returns (resubmit_now, next_wait_s).
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    rs = lim.get("resubmit") or {}
    try:
        max_tries = int(rs.get("max_tries") or 2)
        ov_sends = int(rs.get("overloaded_max_sends") or 5)
        ov_wait = float(rs.get("overloaded_interval_seconds") or 30)
        used = int(sends_used or 1)
    except (TypeError, ValueError):
        return False, None
    code = str(failure_code or "").upper()
    if "OVERLOAD" in code or "UPSTREAM_SERVICE_TEMPORARILY" in code:
        if used < ov_sends:
            return True, ov_wait
        return False, None
    if int(paid_takes_used or 0) < max_tries:
        return True, 0.0
    return False, None


def upload_is_fresh(created_at_epoch, now_epoch, limits=None):
    """F-QM-7: an upload link older than 23 h is uploaded again before use."""
    lim = limits if isinstance(limits, dict) else load_limits()
    try:
        hours = float(lim.get("upload_freshness_hours") or 23)
        born = float(created_at_epoch)
        now = float(now_epoch)
    except (TypeError, ValueError):
        return False
    if now < born:
        return False
    return (now - born) <= hours * 3600.0


def slow_route_first(jobs, limits=None):
    """N-97 / N-79: slowest route first in the burst.

    A stable sort by route rank; unknown routes after the slow ones. Never
    drops a job.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    slow = [str(r) for r in ((lim.get("slow_route_head_start") or {})
                             .get("routes") or [])]

    def rank(job):
        route = str((job or {}).get("route") or "").lower()
        for i, name in enumerate(slow):
            if name in route:
                return i
        return len(slow)

    return sorted(list(jobs or []), key=rank)


def head_start_allowed(owner_choice, limits=None):
    """N-97: the slow route goes early ONLY on the pre-authorized choice.

    The run owner must have chosen "go ahead if every check passes" at
    intake; any other choice (or none) keeps every job for the one video
    burst after the picture gate. Never inferred, never assumed.
    """
    lim = limits if isinstance(limits, dict) else load_limits()
    want = str((lim.get("slow_route_head_start") or {})
               .get("requires_owner_choice") or "").strip().lower()
    got = str(owner_choice or "").strip().lower()
    return bool(want) and got == want


def head_start_jobs(jobs, owner_choice, limits=None):
    """N-97: the reference-only slow-route jobs that may be sent early.

    Empty unless the owner pre-authorized. A nine-picture or long-take job
    needs only the locked references and its composition keyframe, so it can
    go with the keyframe burst; every other job waits for the video burst.
    """
    if not head_start_allowed(owner_choice, limits):
        return []
    lim = limits if isinstance(limits, dict) else load_limits()
    slow = [str(r) for r in ((lim.get("slow_route_head_start") or {})
                             .get("routes") or [])]
    out = []
    for job in (jobs or []):
        route = str((job or {}).get("route") or "").lower()
        if any(name in route for name in slow):
            out.append(job)
    return out

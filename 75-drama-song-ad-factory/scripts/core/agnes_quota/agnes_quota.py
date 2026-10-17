#!/usr/bin/env python3
"""Agnes daily quota tracker: one SQLite ledger per key pool (SPEC A5.3, A11, A12).

Stdlib only. This is a planner, never a permission -- a vendor 402 always wins
(record_vendor_402 zeroes the whole UTC day whatever the local count).

Ledger row: (utc_day, kind=video|image, units, run_id, logical_key, state).
States: reserved -> succeeded (still counted) | failed (released back to the
day); vendor_402 marks the whole UTC day exhausted.

Whole-run admission (Trevor 2026-10-13): no run is ever split across days.
fits_today(clips, now) answers "run now" or "wait whole until the next 00:00
UTC reset", never "take what fits today and finish tomorrow".

progress() writes <run_dir>/control/agnes-progress.json (SPEC A11) by writing a
temp file in that same folder and renaming it over the target.
"""
from __future__ import annotations

import json
import math
import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOL_NAME = "agnes_quota"
TOOL_VERSION = "1.0.0"

# Daily limits per key pool.
# Source: https://wiki.agnes-ai.com/en/docs/tokenplan.md -- read 2026-10-13.
# "agnes-video-2.5-flash = 500 seconds per day" and "agnes-image-2.5-flash =
# 4,000 images per day" on every plan (Starter/Plus/Pro), counted by generated
# video duration; the console window resets 00:00:00 UTC (screenshot of the
# Plus plan, captured 2026-09-28, read 2026-10-13). Overridable per box by
# AGNES_DAILY_VIDEO_SECONDS / AGNES_DAILY_IMAGES.
LIMITS = {"video": 500, "image": 4000}
LIMIT_ENV = {"video": "AGNES_DAILY_VIDEO_SECONDS", "image": "AGNES_DAILY_IMAGES"}

# Seconds requested per Agnes clip (fixed 10-second segments, SPEC A5.1).
CLIP_SECONDS = 10

# 5-minute cap: the 5-minute choice is D = 300 - 2 = 298 delivered seconds
# (SPEC A5.1, A15.6). Longer runs are refused, never split across days.
AGNES_MAX_DELIVERED_S = 298
AGNES_LENGTH_CAP = "AGNES_LENGTH_CAP"
AGNES_QUOTA_EXHAUSTED = "AGNES_QUOTA_EXHAUSTED"

# ETA: trial A measured 679.6 s / 711.7 s / 768.0 s accepted -> done for a
# 10-second clip (~11-13 min), 2 clips in flight at a time
# (RESEARCH.md "Agnes time per 10 s clip", test A, read 2026-10-13; SPEC A5.2,
# A11 "the measured 11-13 min per round of 2").
CLIPS_PER_ROUND = 2
ROUND_MIN_LOW = 11
ROUND_MIN_HIGH = 13

NEXT_DAY_REASON = "agnes-quota-next-day"
PROGRESS_NAME = "agnes-progress.json"

DDL = """
CREATE TABLE IF NOT EXISTS quota(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  utc_day TEXT NOT NULL,
  kind TEXT NOT NULL CHECK(kind IN ('video','image')),
  units INTEGER NOT NULL DEFAULT 0,
  run_id TEXT NOT NULL DEFAULT '',
  logical_key TEXT NOT NULL DEFAULT '',
  state TEXT NOT NULL CHECK(state IN ('reserved','succeeded','failed','vendor_402')),
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_quota_day_kind ON quota(utc_day, kind, state);
CREATE INDEX IF NOT EXISTS idx_quota_day_state ON quota(utc_day, state);
"""

COUNTED = ("reserved", "succeeded")
KINDS = tuple(LIMITS)


class QuotaError(Exception):
    """Refusal with a stable code (AGNES_LENGTH_CAP, AGNES_QUOTA_EXHAUSTED)."""

    def __init__(self, code, message=""):
        super().__init__(message or code)
        self.code = code


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc)
    if now.tzinfo is None:
        return now.replace(tzinfo=timezone.utc)
    return now


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_day(now=None):
    """UTC calendar day of the vendor window: 'YYYY-MM-DD'."""
    return _now(now).strftime("%Y-%m-%d")


def next_reset_utc(now=None):
    """The next 00:00 UTC after `now` -- the whole-day wait target (A5.3)."""
    n = _now(now)
    return datetime(n.year, n.month, n.day, tzinfo=timezone.utc) + timedelta(days=1)


def limits(env=os.environ):
    """Effective daily limits; env overrides win over LIMITS."""
    out = {}
    for kind, default in LIMITS.items():
        raw = env.get(LIMIT_ENV[kind])
        out[kind] = int(str(raw).strip()) if raw is not None and str(raw).strip() else default
    return out


def state_path(env=os.environ):
    """Persistent ledger path for this platform (SPEC A12).

    DSAF_AGNES_QUOTA_DB always wins. Then the Docker rows (HOME is the
    platform), then OpenClaw's own env marker, then the Claude Code row.
    """
    override = (env.get("DSAF_AGNES_QUOTA_DB") or "").strip()
    if override:
        return Path(override)
    home = Path(env.get("HOME") or str(Path.home()))
    hs = str(home)
    docker = hs == "/data" or hs.startswith("/data/") or hs == "/home/node"
    openclaw = bool(env.get("OPENCLAW_SKILLS_DIR") or env.get("OPENCLAW_HOME"))
    # ponytail: OPENCLAW_SKILLS_DIR / OPENCLAW_HOME are the only markers the
    # gateway exports into child processes; a new marker adds one name here.
    if docker or openclaw:
        return home / ".openclaw" / "drama-runs" / ".agnes-quota.sqlite3"
    return home / ".drama-song-ad-factory" / "agnes-quota.sqlite3"


def _connect(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    conn.execute("PRAGMA busy_timeout=10000")
    conn.executescript(DDL)
    return conn


def _exhausted(conn, day):
    return conn.execute(
        "SELECT 1 FROM quota WHERE utc_day=? AND state='vendor_402' LIMIT 1",
        (day,)).fetchone() is not None


def _used(conn, day, kind):
    row = conn.execute(
        "SELECT COALESCE(SUM(units),0) FROM quota "
        "WHERE utc_day=? AND kind=? AND state IN ('reserved','succeeded')",
        (day, kind)).fetchone()
    return int(row[0]) if row else 0


def remaining(kind, now=None, env=os.environ):
    """Units of `kind` still available in the UTC day of `now` (0 after a 402)."""
    if kind not in KINDS:
        raise ValueError("unknown kind: %r" % (kind,))
    day = utc_day(now)
    conn = _connect(state_path(env))
    try:
        if _exhausted(conn, day):
            return 0
        return max(0, int(limits(env)[kind]) - _used(conn, day, kind))
    finally:
        conn.close()


def reserve(kind, units, run_id, logical_key="", now=None, env=os.environ):
    """Hold `units` of `kind` for this UTC day. Returns the ledger row id.

    Raises QuotaError(AGNES_QUOTA_EXHAUSTED) rather than going negative: the
    vendor's day, not ours, decides, so a short day never half-arms a job.
    """
    if kind not in KINDS:
        raise ValueError("unknown kind: %r" % (kind,))
    units = int(units)
    if units < 0:
        raise ValueError("units must be >= 0")
    day = utc_day(now)
    stamp = _iso(_now(now))
    conn = _connect(state_path(env))
    try:
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            if _exhausted(conn, day):
                raise QuotaError(
                    AGNES_QUOTA_EXHAUSTED,
                    "Agnes vendor 402 exhausted %s" % day)
            free = max(0, int(limits(env)[kind]) - _used(conn, day, kind))
            if units > free:
                raise QuotaError(
                    AGNES_QUOTA_EXHAUSTED,
                    "Agnes %s quota: %s of %s left on %s, %s requested"
                    % (kind, free, limits(env)[kind], day, units))
            cur = conn.execute(
                "INSERT INTO quota(utc_day, kind, units, run_id, logical_key,"
                " state, created_at) VALUES(?,?,?,?,?,'reserved',?)",
                (day, kind, units, str(run_id), str(logical_key), stamp))
            return int(cur.lastrowid)
    finally:
        conn.close()


def settle(row_id, ok=True, env=os.environ):
    """Close a reservation. ok keeps the units spent; not ok releases them."""
    state = "succeeded" if ok else "failed"
    conn = _connect(state_path(env))
    try:
        cur = conn.execute(
            "UPDATE quota SET state=? WHERE id=? AND state='reserved'",
            (state, int(row_id)))
        return cur.rowcount == 1
    finally:
        conn.close()


def record_vendor_402(now=None, env=os.environ):
    """Vendor said the day is out. That wins over every local count (A5.3).

    Only the UTC day of `now` is zeroed; tomorrow opens clean.
    """
    day = utc_day(now)
    conn = _connect(state_path(env))
    try:
        conn.execute(
            "INSERT INTO quota(utc_day, kind, units, run_id, logical_key,"
            " state, created_at) VALUES(?,'video',0,'vendor','vendor-402',"
            "'vendor_402',?)",
            (day, _iso(_now(now))))
        return day
    finally:
        conn.close()


def fits_today(clips, now, allowance=1.2, env=os.environ):
    """Whole-run admission for `clips` Agnes clips: run now, or wait for the
    next 00:00 UTC reset. Never a partial start (SPEC A5.3, Trevor 2026-10-13).
    """
    clips = int(clips)
    video_seconds = clips * CLIP_SECONDS
    need = int(math.ceil(video_seconds * float(allowance)))
    free = remaining("video", now, env)
    fits = free >= need
    return {
        "fits": fits,
        "clips": clips,
        "video_seconds": video_seconds,
        "allowance": float(allowance),
        "allowance_seconds": need,
        "daily_video_seconds": int(limits(env)["video"]),
        "remaining_video_seconds": free,
        "waiting_reason": None if fits else NEXT_DAY_REASON,
        "next_continue_utc": None if fits else _iso(next_reset_utc(now)),
    }


def check_length(delivered_s):
    """Refuse a run longer than the 5-minute Agnes cap (SPEC A15.6)."""
    if float(delivered_s) > AGNES_MAX_DELIVERED_S:
        raise QuotaError(
            AGNES_LENGTH_CAP,
            "Agnes runs are capped at 5 minutes: %s delivered seconds > %s"
            % (delivered_s, AGNES_MAX_DELIVERED_S))
    return float(delivered_s)


def progress(run_dir, clips_total, clips_done, in_flight=0, waiting_reason=None,
             next_continue_utc=None, updated_utc=None, now=None):
    """Write <run_dir>/control/agnes-progress.json (SPEC A11), atomically.

    ETA = remaining rounds of 2 clips x the measured 11-13 min.
    """
    total = int(clips_total)
    done = int(clips_done)
    left = max(0, total - done)
    rounds = int(math.ceil(left / float(CLIPS_PER_ROUND)))
    record = {
        "clips_total": total,
        "clips_done": done,
        "in_flight": int(in_flight),
        "waiting_reason": waiting_reason,
        "next_continue_utc": next_continue_utc,
        "eta_minutes_low": rounds * ROUND_MIN_LOW,
        "eta_minutes_high": rounds * ROUND_MIN_HIGH,
        "updated_utc": updated_utc or _iso(_now(now)),
    }
    control = Path(run_dir) / "control"
    control.mkdir(parents=True, exist_ok=True)
    tmp = control / ("%s.%d.tmp" % (PROGRESS_NAME, os.getpid()))
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, control / PROGRESS_NAME)
    return record


__all__ = [
    "AGNES_LENGTH_CAP",
    "AGNES_MAX_DELIVERED_S",
    "AGNES_QUOTA_EXHAUSTED",
    "CLIPS_PER_ROUND",
    "CLIP_SECONDS",
    "LIMITS",
    "NEXT_DAY_REASON",
    "PROGRESS_NAME",
    "QuotaError",
    "ROUND_MIN_HIGH",
    "ROUND_MIN_LOW",
    "check_length",
    "fits_today",
    "limits",
    "next_reset_utc",
    "progress",
    "record_vendor_402",
    "remaining",
    "reserve",
    "settle",
    "state_path",
    "utc_day",
]

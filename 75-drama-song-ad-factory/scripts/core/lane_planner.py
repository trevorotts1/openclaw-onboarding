#!/usr/bin/env python3
"""lane_planner.py: parallel minute-lanes for ads 120 s and up (W-G-008). Stdlib only.

Below 120 s of song NOTHING changes: one lane, exactly today's flow. At 120 s
and up the shot list is cut into N = ceil(L / 60) lanes, about 60 s each, cut
ON shot boundaries (a shot is never split). Each lane then makes its own
stills, motion clips and lip-sync segments AT THE SAME TIME as the others, on
the same character, through the same picture gate, with at most 2 lip-sync
jobs per segment then the best take, and mouth strips.

Shared steps run ONCE, before the split (constant SHARED_STEPS_BEFORE): song +
song checker, plan/shot list, character, close-up picture gate. Fan-in runs
ONCE, after the lanes (constant SHARED_STEPS_AFTER): one edit over the full
song, one independent checker for the whole ad (hard audio-length rule,
captions = lyrics, face through the call to action), one repair.

Rate safety across lanes (references/kie-rate-limit.md): ONE shared governor,
class SharedGovernor --
  * at most KIE_PER_WINDOW (20) NEW generation requests per rolling 10 s in
    total across all lanes,
  * per-lane share floor(18 / N) per 10 s (KIE_LANE_SHARE_NUM = 18), leaving
    headroom under the account limit,
  * a 429 is resubmitted, never dropped: submit() runs every request through
    load_governor.kie_request, whose contract the governor reuses instead of
    re-implementing.
Heavy local jobs (ffmpeg) at most 2 at once across all lanes: lanes run them
through the EXISTING machine-wide gate, load_governor.heavy_slot (file locks,
default cap 2) -- re-exported here as heavy_slot so a lane has one import.

Resume and reuse: classify_tag() answers "reuse" / "poll" / "submit" against
the run's spend ledger. A job tag already in the ledger is POLLED, never
resubmitted; a finished file is REUSED, so a re-run never pays twice.

Spend stays under the run cap across all lanes together: every lane plans its
jobs against the ONE ledger run (caller keeps one run_id for the whole ad).

Runnable self-check (stdlib, no framework, no network, fake clock):
    python3 scripts/core/test_lane_planner.py
"""
from __future__ import annotations

import math
import os
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # core/ on sys.path (house style)

import load_governor as _LG  # noqa: E402  (heavy gate + kie_request, never re-implemented)
import spend_ledger as _L  # noqa: E402  (ledger schema check for classify_tag)

LANE_MIN_SONG_S = 120.0      # below this: one lane, today's flow, unchanged
LANE_TARGET_S = 60.0         # about one minute per lane
KIE_PER_WINDOW = 20          # NEW generation requests per 10 s, all lanes together
KIE_WINDOW_S = 10.0
KIE_LANE_SHARE_NUM = 18      # per-lane share = floor(18 / N)
EPS = 1e-6

# The steps that happen EXACTLY ONCE per ad (never per lane).
SHARED_STEPS_BEFORE = (
    "song",
    "song-checker",
    "plan-shot-list",
    "character",
    "closeup-picture-gate",
)
SHARED_STEPS_AFTER = (
    "one-edit-full-song",
    "one-independent-checker-whole-ad",
    "one-repair",
)

#: Lanes run every heavy local job through the ONE machine-wide gate (cap 2).
heavy_slot = _LG.heavy_slot


class LanePlanError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


def lane_count(song_length_s):
    """1 below 120 s; ceil(L / 60) at 120 s and up."""
    L = float(song_length_s)
    return 1 if L < LANE_MIN_SONG_S else int(math.ceil(L / LANE_TARGET_S))


def lane_share(lanes):
    """Per-lane budget per 10 s: floor(18 / N); one lane keeps today's 20."""
    n = max(1, int(lanes))
    if n <= 1:
        return KIE_PER_WINDOW
    return max(1, KIE_LANE_SHARE_NUM // n)


def _shot_window(shot):
    if not isinstance(shot, dict):
        raise LanePlanError("BAD_SHOT", "shot is not a record: %r" % (shot,))
    sid = shot.get("shot_id")
    s, e = shot.get("song_start"), shot.get("song_end")
    if not isinstance(sid, str) or not sid.strip():
        raise LanePlanError("BAD_SHOT", "shot without shot_id")
    for v in (s, e):
        if not isinstance(v, (int, float)) or isinstance(v, bool):
            raise LanePlanError("BAD_SHOT", "shot %s window not numeric" % sid)
    if not float(s) < float(e):
        raise LanePlanError("BAD_SHOT", "shot %s window not ordered" % sid)
    return {"shot_id": sid, "song_start": float(s), "song_end": float(e)}


def _boundaries(recs, song_length_s, lanes):
    """lanes-1 cut times, each ON a shot end (a shot is never split)."""
    ends = sorted({r["song_end"] for r in recs})
    cuts = []
    for k in range(1, lanes):
        target = song_length_s * k / lanes
        hit = next((e for e in ends if e >= target - EPS), None)
        if hit is None:
            raise LanePlanError(
                "LANE_BOUNDARY_UNREACHABLE",
                "no shot boundary at or after %.3f s (shots end at %.3f s)"
                % (target, ends[-1]))
        if cuts and abs(hit - cuts[-1]) <= EPS:
            raise LanePlanError(
                "LANE_BOUNDARY_INSIDE_SHOT",
                "target %.3f s falls inside one shot that cannot be split" % target)
        cuts.append(hit)
    return cuts


def plan_lanes(shots, song_length_s):
    """Split a shot list into minute-lanes. Returns the lane plan dict.

    shots: shot-planner records (shot_id + song_start/song_end). Fails closed:
    empty/invalid shots, too few shots for the lane count, a lane boundary that
    would have to split a shot. A shot NEVER straddles two lanes.
    """
    L = float(song_length_s)
    if not L > 0:
        raise LanePlanError("BAD_SONG_LENGTH", "song length must be > 0: %r" % (song_length_s,))
    if not isinstance(shots, (list, tuple)) or not shots:
        raise LanePlanError("NO_SHOTS", "plan_lanes needs a non-empty shot list")
    recs = sorted((_shot_window(s) for s in shots), key=lambda r: (r["song_start"], r["song_end"]))
    n = lane_count(L)
    if n > len(recs):
        raise LanePlanError(
            "LANES_OVER_SHOTS", "%d lanes need at least %d shots; got %d" % (n, n, len(recs)))
    cuts = _boundaries(recs, L, n) if n > 1 else []
    lanes = []
    rest = list(recs)
    for i in range(n):
        end = cuts[i] if i < len(cuts) else None
        take = [r for r in rest if end is None or r["song_end"] <= end + EPS]
        if not take:
            raise LanePlanError("EMPTY_LANE", "lane %d would carry no shots" % i)
        take_ids = {r["shot_id"] for r in take}
        rest = [r for r in rest if r["shot_id"] not in take_ids]
        lanes.append({
            "lane_index": i,
            "song_start": min(r["song_start"] for r in take),
            "song_end": max(r["song_end"] for r in take),
            "shot_ids": [r["shot_id"] for r in take],
        })
    if rest:
        raise LanePlanError("SHOTS_UNPLACED", "%d shots not placed into a lane" % len(rest))
    return {
        "song_length_s": L,
        "lanes": n,
        "lane_share_per_10s": lane_share(n),
        "shared_steps_before": list(SHARED_STEPS_BEFORE),
        "shared_steps_after": list(SHARED_STEPS_AFTER),
        "lanes_detail": lanes,
    }


class SharedGovernor:
    """ONE KIE governor across all lanes: 20 new generation requests per
    rolling 10 s in total, floor(18 / N) per lane per 10 s. Clock and sleep are
    injectable (the tests drive a fake clock); production uses time.time /
    time.sleep only through load_governor.kie_request.
    """

    def __init__(self, lanes, *, per_window=KIE_PER_WINDOW, window_s=KIE_WINDOW_S,
                 share_num=KIE_LANE_SHARE_NUM, clock=time.time, sleep=time.sleep):
        self.lanes = max(1, int(lanes))
        self.per_window = int(per_window)
        self.window_s = float(window_s)
        self.lane_share = (self.per_window if self.lanes <= 1
                           else max(1, int(share_num) // self.lanes))
        self._clock = clock
        self._sleep = sleep
        self._stamps = []      # [accepted_time, lane]

    def _slide(self, now):
        self._stamps = [s for s in self._stamps if now - s[0] < self.window_s]

    def acquire(self, lane):
        """Block until THIS lane may send one NEW generation request."""
        while True:
            now = self._clock()
            self._slide(now)
            mine = sum(1 for s in self._stamps if s[1] == lane)
            if len(self._stamps) < self.per_window and mine < self.lane_share:
                self._stamps.append([now, lane])
                return
            wait = self._stamps[0][0] + self.window_s - now
            self._sleep(max(0.05, wait))

    def submit(self, lane, fn, *, label="kie", retries=6, backoff_s=2.0):
        """One lane's NEW generation request: governor slot, then
        load_governor.kie_request (429 -> back off and resubmit, never dropped)."""
        return _LG.kie_request(
            fn, label, generation=True, retries=retries, backoff_s=backoff_s,
            sleep=self._sleep, acquire=lambda: self.acquire(lane))


def _open_ledger_ro(db_path):
    if not db_path or not os.path.exists(db_path):
        raise LanePlanError(
            "NO_LEDGER",
            "no spend ledger at %r: create the run (intake) before planning lane jobs"
            % (db_path,))
    try:
        conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True, timeout=10,
                               check_same_thread=False)
    except sqlite3.Error as exc:
        raise LanePlanError("LEDGER_UNREADABLE", "open failed: %s" % exc)
    try:
        row = conn.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'").fetchone()
    except sqlite3.DatabaseError as exc:
        conn.close()
        raise LanePlanError("LEDGER_UNREADABLE", str(exc))
    if not row or row[0] not in _L.COMPATIBLE:
        conn.close()
        raise LanePlanError("LEDGER_INCOMPATIBLE", "schema=%s" % (row[0] if row else None))
    return conn


def classify_tag(db_path, run_id, logical_key, artifact_path=""):
    """reuse | poll | submit for one job tag, read from the run's spend ledger.

    reuse  — a finished file is on disk (a re-run never pays twice);
    poll   — the tag is already in the ledger: POLL it, never resubmit;
    submit — no ledger row and no file: a genuinely new job.
    """
    on_disk = bool(artifact_path) and os.path.isfile(artifact_path) and os.path.getsize(artifact_path) > 0
    conn = _open_ledger_ro(db_path)
    try:
        known = conn.execute(
            "SELECT 1 FROM jobs WHERE run_id=? AND logical_key=? LIMIT 1",
            (run_id, logical_key)).fetchone()
        if not known:
            known = conn.execute(
                "SELECT artifact_path FROM results WHERE run_id=? AND logical_key=? LIMIT 1",
                (run_id, logical_key)).fetchone()
            row_path = known[0] if known else ""
        else:
            got = conn.execute(
                "SELECT artifact_path FROM results WHERE run_id=? AND logical_key=? LIMIT 1",
                (run_id, logical_key)).fetchone()
            row_path = got[0] if got else ""
    finally:
        conn.close()
    if known:
        row_disk = bool(row_path) and os.path.isfile(row_path) and os.path.getsize(row_path) > 0
        return "reuse" if (on_disk or row_disk) else "poll"
    return "reuse" if on_disk else "submit"

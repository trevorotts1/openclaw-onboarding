#!/usr/bin/env python3
"""Load governor for Skill 75: the local-load safeguards, enforced in code. stdlib only.

Why: on 2026-10-08 several agent windows started heavy local jobs at once and
crashed the Mac. Rules here are code paths the heavy call sites go through, not
advice a builder can skip.

1. heavy_slot(job)    machine-wide gate: at most DSAF_HEAVY_SLOTS (default 2) heavy
                       jobs at once across EVERY process, via fcntl.flock files in a
                       fixed shared dir. Waits while free memory < 30 percent
                       (re-check every 15 s); after 20 min raises HeavyJobTimeout
                       naming the job. Never runs anyway, never skips silently.
2. bounded()/run_ffmpeg()  every ffmpeg argv gets `nice -n 10` and `-threads <=4`,
                       and run_ffmpeg runs it inside heavy_slot.
3. StageRegistry       deletes a stage's intermediate files once the next stage has
                       consumed them and its output is verified; never deliverables;
                       every deletion logged, a failed one prints WARNING.
4. kie_request(fn)     KIE pacing, two separate limiters (references/kie-rate-limit.md):
                       generation=True  NEW generation requests (submit/create) draw from one
                         20-per-rolling-10-s file-lock token bucket, shared across processes,
                         one bucket per KIE key.
                       generation=False status polls, health, record-info, preflight, save use
                         a gentler per-process limiter (default 1 request/s,
                         DSAF_KIE_POLL_INTERVAL_S) and never touch the generation bucket.
                       A 429 means the job did NOT run and is NOT queued: back off and
                       resubmit; retries exhausted raises KieRateLimitError naming the job.
5. Never the OpenAI whisper stack: run_heavy refuses any whisper executable (faster-whisper
   runs only inside lyric_timing).

Heavy local jobs: ffmpeg render/encode/concat/decode, audio cutting, stem
separation, the singing detector, transcription, image/video post-processing.
ffprobe metadata reads are light and skip the gate.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path

CAP_ENV = "DSAF_HEAVY_SLOTS"        # heavy-job cap; default 2
DIR_ENV = "DSAF_GOVERNOR_DIR"       # shared dir override (tests); default below
DEFAULT_CAP = 2
MIN_FREE_PCT = 30.0
POLL_S = 15.0
MAX_WAIT_S = 20 * 60
NICE = 10
MAX_THREADS = 4
KIE_MAX, KIE_WINDOW_S = 20, 10.0    # KIE: 20 NEW generation requests / 10 s per account
POLL_ENV = "DSAF_KIE_POLL_INTERVAL_S"   # gentle limiter for polls/health; default 1 s
POLL_DEFAULT_S = 1.0


class LoadGovernorError(Exception):
    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code


class HeavyJobTimeout(LoadGovernorError):
    pass


def shared_dir():
    d = os.environ.get(DIR_ENV)
    p = Path(d) if d else Path.home() / ".cache" / "drama-song-ad-factory"
    p.mkdir(parents=True, exist_ok=True)
    return p


def slot_cap():
    try:
        return max(1, int(os.environ.get(CAP_ENV, DEFAULT_CAP)))
    except ValueError:
        return DEFAULT_CAP


# ── memory ───────────────────────────────────────────────────────────────────
def _sh(argv):
    return subprocess.run(argv, capture_output=True, text=True, timeout=10,
                          check=True).stdout


def free_pct():
    """System free memory percent, or None when unmeasurable.
    macOS: memory_pressure "free percentage", then vm_stat. Linux: MemAvailable."""
    if sys.platform == "darwin":
        try:
            m = re.search(r"free percentage:\s*(\d+)", _sh(["memory_pressure"]))
            if m:
                return float(m.group(1))
        except (OSError, subprocess.SubprocessError):
            pass
        try:
            out, total = _sh(["vm_stat"]), int(_sh(["sysctl", "-n", "hw.memsize"]))
            page = int(re.search(r"page size of (\d+)", out).group(1))
            pages = sum(int(re.search(r"Pages %s:\s+(\d+)" % k, out).group(1))
                        for k in ("free", "inactive", "speculative"))
            return 100.0 * pages * page / total
        except (OSError, subprocess.SubprocessError, AttributeError, ValueError):
            return None
    try:
        kv = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            k, _, v = line.partition(":")
            kv[k] = int(v.split()[0])
        return 100.0 * kv["MemAvailable"] / kv["MemTotal"]
    except (OSError, KeyError, ValueError, IndexError):
        return None


# ── receipt ──────────────────────────────────────────────────────────────────
_LOG = []                # heavy-job rows for the run receipt
_LOCK = threading.Lock()
_tl = threading.local()


def receipt():
    """Run-receipt block: every heavy job with its wait time. Copy, not drain."""
    with _LOCK:
        rows = list(_LOG)
    return {"heavy_jobs": rows,
            "total_wait_s": round(sum(r["waited_s"] for r in rows), 2),
            "cap": slot_cap(), "min_free_pct": MIN_FREE_PCT}


def _say(msg):
    print("[load-governor] " + msg, file=sys.stderr, flush=True)


# ── 1. the machine-wide gate ─────────────────────────────────────────────────
@contextlib.contextmanager
def heavy_slot(job, *, poll_s=POLL_S, max_wait_s=MAX_WAIT_S, probe=None,
               sleep=time.sleep, min_free_pct=MIN_FREE_PCT):
    """with heavy_slot("ffmpeg-render"): ... Blocks until a slot is free AND
    memory is healthy. A nested call in the same thread rides the outer slot."""
    if getattr(_tl, "depth", 0) > 0:
        _tl.depth += 1
        try:
            yield
        finally:
            _tl.depth -= 1
        return
    probe = probe or free_pct
    t0 = time.monotonic()
    fd, announced, why = None, False, ""
    base = shared_dir() / "heavy-slots"
    base.mkdir(parents=True, exist_ok=True)
    paths = [base / ("slot-%d.lock" % i) for i in range(slot_cap())]
    pct = None
    while True:
        pct = probe()
        if pct is None:
            why = "free memory unmeasurable"
        elif pct < min_free_pct:
            why = "free memory %.0f%% < %.0f%%" % (pct, min_free_pct)
        else:
            why = ""
            for i, p in enumerate(paths):
                f = os.open(str(p), os.O_RDWR | os.O_CREAT, 0o600)
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fd, slot = f, i
                    break
                except OSError:
                    os.close(f)
            if fd is not None:
                break
            why = "all %d heavy slots busy" % len(paths)
        if not announced:
            _say("WAIT %s: %s" % (job, why))
            announced = True
        if time.monotonic() - t0 >= max_wait_s:
            msg = ("heavy job %r waited %.0f s (%s); refusing to run into load "
                   "-- retry when the machine is quiet" % (job, time.monotonic() - t0, why))
            _say("FAIL " + msg)
            raise HeavyJobTimeout("HEAVY_JOB_TIMEOUT", msg)
        sleep(poll_s)
    waited = time.monotonic() - t0
    _say("START %s (slot %d, waited %.1f s, free %s)"
         % (job, slot, waited, "%.0f%%" % pct if pct is not None else "?"))
    _tl.depth = 1
    t1 = time.monotonic()
    try:
        yield
    finally:
        _tl.depth = 0
        ran = time.monotonic() - t1
        os.close(fd)                      # releases the flock
        _say("END %s (ran %.1f s)" % (job, ran))
        with _LOCK:
            _LOG.append({"job": job, "slot": slot, "waited_s": round(waited, 2),
                         "ran_s": round(ran, 2),
                         "free_pct_at_start": None if pct is None else round(pct, 1)})


def heavy(job):
    """Decorator form of heavy_slot for a whole heavy function."""
    def deco(fn):
        import functools

        @functools.wraps(fn)
        def wrapper(*a, **k):
            with heavy_slot(job):
                return fn(*a, **k)
        return wrapper
    return deco


# ── 2. ffmpeg argv + runner ──────────────────────────────────────────────────
def _is(argv_exe, name):
    return os.path.basename(str(argv_exe)).lower() == name


def bounded(argv, threads=None):
    """Idempotent: ffmpeg argv -> `nice -n 10 ffmpeg -threads <=4 ...`.
    `threads` (e.g. size_ffmpeg) only ever lowers the 4 cap."""
    a = [str(x) for x in argv]
    if a[:1] == ["nice"]:
        a = a[3:] if a[1:2] == ["-n"] else a[1:]
    cap = min(MAX_THREADS, int(threads)) if threads else MAX_THREADS
    cap = max(1, cap)
    if not a or not _is(a[0], "ffmpeg"):
        raise LoadGovernorError("NOT_FFMPEG", "bounded() builds ffmpeg argv only: %r" % a[:1])
    if "-threads" in a:
        i = a.index("-threads")
        try:
            cap = min(cap, int(a[i + 1]))
        except (IndexError, ValueError):
            pass
        a[i:i + 2] = []
    return ["nice", "-n", str(NICE), a[0], "-threads", str(cap)] + a[1:]


def ffmpeg_argv(args, ffmpeg="ffmpeg", threads=None):
    """Build an ffmpeg argv from the args after the executable."""
    return bounded([ffmpeg] + list(args), threads)


def run_heavy(argv, job, **kw):
    """subprocess.run inside heavy_slot. ffmpeg argv is bounded first.
    Refuses the banned OpenAI whisper executables."""
    exe = os.path.basename(str(argv[0])).lower()
    if "whisper" in exe:
        raise LoadGovernorError("LOCAL_ASR_FORBIDDEN",
                                "the OpenAI whisper stack is banned; transcription goes through lyric_timing")
    if _is(argv[0], "ffmpeg") or (argv[0] == "nice" and _is(argv[3] if len(argv) > 3 else "", "ffmpeg")):
        argv = bounded(argv)
    with heavy_slot(job):
        return subprocess.run(argv, **kw)


def run_ffmpeg(argv, job="ffmpeg", **kw):
    return run_heavy(argv, job, **kw)


# ── 3. intermediate cleanup ──────────────────────────────────────────────────
_DELIVERABLE = re.compile(r"master|receipt|song|stem|vocal|lyric|final|deliver", re.I)
_DELIVERABLE_EXT = {".srt", ".vtt", ".mp3", ".wav"}


def is_deliverable(path):
    p = Path(path)
    return bool(_DELIVERABLE.search(p.name)) or p.suffix.lower() in _DELIVERABLE_EXT


class StageRegistry:
    """register(stage, files) -> consumed(stage, output): delete that stage's
    intermediates once its output exists, is non-empty and passes `verify`."""

    def __init__(self):
        self.pending = {}
        self.log = []

    def register(self, stage, files):
        for f in files or []:
            self.pending.setdefault(stage, []).append(str(f))

    def consumed(self, stage, output, verify=None):
        out = Path(output)
        ok = out.is_file() and out.stat().st_size > 0 and (verify is None or bool(verify(out)))
        for f in self.pending.get(stage, []):
            if not ok:
                self.log.append({"stage": stage, "file": f, "action": "kept-output-unverified"})
            elif is_deliverable(f) or Path(f).resolve() == out.resolve():
                self.log.append({"stage": stage, "file": f, "action": "kept-deliverable"})
            else:
                try:
                    os.unlink(f)
                    self.log.append({"stage": stage, "file": f, "action": "deleted"})
                except FileNotFoundError:
                    self.log.append({"stage": stage, "file": f, "action": "already-gone"})
                except OSError as e:
                    print("WARNING: could not delete intermediate %s: %s" % (f, e),
                          file=sys.stderr, flush=True)
                    self.log.append({"stage": stage, "file": f, "action": "delete-failed",
                                     "error": str(e)})
        if ok:
            self.pending.pop(stage, None)
        return self.log


# ── 4. KIE pacing ────────────────────────────────────────────────────────────
class KieRateLimitError(LoadGovernorError):
    pass


def key_tag():
    """Bucket name per KIE key (hash only; the key itself is never written)."""
    k = os.environ.get("KIE_API_KEY", "")
    return hashlib.sha256(k.encode()).hexdigest()[:12] if k else "nokey"


def kie_acquire(max_req=KIE_MAX, window_s=KIE_WINDOW_S, sleep=time.sleep, clock=time.time):
    """Block until this process may send one NEW generation request (rolling
    window; all processes sharing this KIE key share stamps.json under flock)."""
    d = shared_dir() / "kie-rate" / key_tag()
    d.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(d / "bucket.lock"), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        while True:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                st = d / "stamps.json"
                try:
                    stamps = json.loads(st.read_text())
                except (OSError, ValueError):
                    stamps = []
                now = clock()
                stamps = [t for t in stamps if now - t < window_s]
                if len(stamps) < max_req:
                    stamps.append(now)
                    st.write_text(json.dumps(stamps))
                    return
                wait = stamps[0] + window_s - now
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
            sleep(max(0.05, wait))
    finally:
        os.close(fd)


_poll_last = [0.0]
_poll_lock = threading.Lock()


def kie_poll_acquire(interval_s=None, sleep=time.sleep, clock=time.monotonic):
    """Gentle per-process limiter for status polls, health and record-info reads.
    Never consumes generation tokens."""
    if interval_s is None:
        try:
            interval_s = float(os.environ.get(POLL_ENV, POLL_DEFAULT_S))
        except ValueError:
            interval_s = POLL_DEFAULT_S
    with _poll_lock:
        wait = _poll_last[0] + interval_s - clock()
        if wait > 0:
            sleep(wait)
        _poll_last[0] = clock() if wait <= 0 else _poll_last[0] + interval_s


_LIMITED = re.compile(r"rate.?limit|too many requests|\bhttp\s*429\b|\b429\b\s*(?:too|error|rate)"
                      r"|[\"']?(?:code|status|http_status|status_code)[\"']?\s*[:=]\s*[\"']?429\b", re.I)


def is_rate_limited(result):
    if getattr(result, "code", None) == 429:
        return True
    if isinstance(result, (tuple, list)):       # (rc, stdout): scan each part unescaped
        return any(is_rate_limited(x) for x in result)
    text = result if isinstance(result, str) else json.dumps(result, default=str)
    return bool(_LIMITED.search(text))


def kie_request(fn, label="kie", *, generation=False, retries=6, backoff_s=2.0,
                is_limited=is_rate_limited, sleep=time.sleep, acquire=None):
    """Run one KIE request. generation=True (submit/create task) draws from the
    20-per-10-s bucket; anything else uses the gentle poll limiter.
    429 / rate-limit reply: the request did NOT run and is not queued. Back off
    2,4,8.. s and resubmit; after `retries` raise KieRateLimitError naming the
    job. A 429 is never counted as submitted and a job is never dropped silently."""
    acquire = acquire or (kie_acquire if generation else kie_poll_acquire)
    for n in range(retries + 1):
        acquire()
        try:
            res = fn()
        except Exception as e:                      # noqa: BLE001
            if not is_limited(e):
                raise
            res = e
        if not is_limited(res):
            return res
        if n == retries:
            break
        _say("KIE 429 on %s; backing off %.0f s (retry %d/%d)" % (label, backoff_s * 2 ** n, n + 1, retries))
        sleep(backoff_s * 2 ** n)
    msg = ("KIE kept rate-limiting job %s after %d retries (HTTP 429: it did NOT run and is not "
           "queued); NOT submitted, NOT dropped, resubmit it" % (label, retries))
    _say("FAIL " + msg)
    raise KieRateLimitError("KIE_RATE_LIMITED", msg)

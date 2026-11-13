#!/usr/bin/env python3
"""S75-049 acceptance: one quota contract between agnes_dispatch and agnes_quota.

The finding (S75-049): the door expected ``reserve`` to return a dict or False
and reported the real module's row number / ``QuotaError`` as "could not be
called"; the row id was thrown away so ``settle`` never ran and a failed clip
kept its seconds; the slot folder was resolved AFTER the reservation; a vendor
402 was never recorded; 503/429 retried with no upper bound.

Every check below runs offline: the HTTP layer, the clock and the sleeper are
fakes, and the quota ledger goes to a throwaway file through
``DSAF_AGNES_QUOTA_DB``. No key is real and no request leaves this machine.

Run: python3 -B agnes_dispatch/test_quota_contract_s75_049.py
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                 # core/

import agnes_dispatch.agnes_dispatch as A   # noqa: E402 (module under test)
import agnes_quota as Q                      # noqa: E402 (the real ledger)
import spend_ledger as L                     # noqa: E402 (same core/ tree)

FAKE_KEY = "cpk-FAKE-KEY-s75-049-never-a-real-key"
BIG_PROMPT = ("The character stands in the kitchen, breathing hard, hands flat "
              "on the counter, morning light cutting across her face. ") * 160
VIDEO_URL = "https://cdn.example.invalid/clip.mp4"
MP4 = b"FAKE-MP4-BYTES"
QUEUE_FULL = {"error": {"code": "video_queue_full", "message": "queue full"}}
QUOTA_402 = {"error": {"code": "quota_exhausted",
                       "message": "Insufficient Token Plan quota"}}

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------------------
# fixtures

class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += float(seconds)


class FakeAgnes:
    """Scripted create/poll answers; no network, no key printed anywhere."""

    def __init__(self, create_answers=None, poll_answers=None, media=MP4,
                 now=time.monotonic):
        self.create_answers = [tuple(a) for a in (create_answers or [])]
        self.poll_answers = [tuple(a) for a in (poll_answers or [])]
        self.media = media
        self.now = now
        self.posts = []
        self._n = 0

    def __call__(self, method, url, key, body):
        method = str(method or "GET").upper()
        if method == "POST":
            self.posts.append(body)
            if self.create_answers:
                status, payload = self.create_answers.pop(0)
            else:
                status, payload = 200, None
            if payload is None:
                self._n += 1
                payload = {"video_id": "vid-%d" % self._n, "status": "queued"}
            return status, payload
        if method == "GET":
            if self.poll_answers:
                return self.poll_answers.pop(0)
            return 200, {"status": "completed", "progress": 100,
                         "metadata": {"url": VIDEO_URL}}
        if method == "DOWNLOAD":
            return 200, self.media
        raise AssertionError("unexpected transport method %r" % method)


class SpyQuota:
    """The real quota module plus a record of every reserve/settle call."""

    def __init__(self, module=None):
        self.module = module
        self.reserved = []
        self.settles = []

    def __getattr__(self, name):
        return getattr(self.module, name)

    def reserve(self, **kwargs):
        self.reserved.append(kwargs)
        return self.module.reserve(**kwargs)

    def settle(self, row_id, outcome=None, seconds_used=None):
        self.settles.append((row_id, outcome, seconds_used))
        return self.module.settle(row_id, outcome, seconds_used)


class NoPoolQuota:
    """A quota planner that cannot name a slot folder: no ``state_path``."""

    def __init__(self):
        self.reserved = []

    def reserve(self, **kwargs):
        self.reserved.append(kwargs)
        return 1


@contextlib.contextmanager
def workdir():
    with tempfile.TemporaryDirectory(prefix="agnes-s75-049-") as d:
        yield d


@contextlib.contextmanager
def quota_env(root):
    """Point the real quota ledger at this test's throwaway file."""
    db = os.path.join(root, "agnes-quota.sqlite3")
    home = os.path.join(root, "home")
    os.makedirs(home, exist_ok=True)
    old = {k: os.environ.get(k) for k in ("DSAF_AGNES_QUOTA_DB", "HOME")}
    os.environ["DSAF_AGNES_QUOTA_DB"] = db
    os.environ["HOME"] = home
    try:
        yield {"DSAF_AGNES_QUOTA_DB": db, "HOME": home}
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class Run:
    """One throwaway run: spend ledger, working folder and quota folder."""

    def __init__(self, root):
        self.root = root
        self.save = os.path.join(root, "work", "agnes")
        self.pool = os.path.join(root, "quota")
        os.makedirs(self.save, exist_ok=True)
        os.makedirs(self.pool, exist_ok=True)
        self.ledger = os.path.join(root, "control", "spend.sqlite3")
        os.makedirs(os.path.dirname(self.ledger), exist_ok=True)
        L.init_run(self.ledger, "run-t", 100)


def card_receipt(agnes="yes"):
    return {"answers": {"video_style": "2D Hand-Painted",
                        "audio_style": "Soul Ballad",
                        "length": "60 seconds",
                        "video_model": "MiniMax H3 768P"},
            "who": "trevor", "at": "2026-10-13T00:00:00Z",
            "agnes": {"answer": agnes, "at": "2026-10-13T00:00:00Z"}}


def request():
    return {"card_receipt": card_receipt("yes"),
            "storyboard": {"shots": [{"shot_id": "s1",
                                      "status": "storyboard_approved"}],
                           "review": {"outcome": "pass"}}}


def video(run, quota, **kw):
    args = dict(save_dir=run.save, ledger_db=run.ledger, run_id="run-t",
                logical_key="seg-1", attempt_id="a1", prompt=BIG_PROMPT,
                quota=quota, key=FAKE_KEY, pool_dir=run.pool)
    args.update(kw)
    return A.dispatch_video(request(), **args)


def quota_rows(env_map):
    conn = sqlite3.connect(env_map["DSAF_AGNES_QUOTA_DB"])
    try:
        return conn.execute(
            "SELECT id, kind, units, state FROM quota ORDER BY id").fetchall()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# 1. success settles: the row id is carried and closed as succeeded

def test_success_settles_the_reservation():
    with workdir() as d:
        with quota_env(d) as qenv:
            run = Run(d)
            clock = FakeClock()
            quota = SpyQuota(Q)
            env = video(run, quota, transport=FakeAgnes(now=clock),
                        sleep=clock.sleep, clock=clock)
            check("a successful clip is ok", env["outcome"] == "ok",
                  json.dumps(env))
            check("the reservation was one row of 10 video seconds",
                  [r[1:3] for r in quota_rows(qenv)] == [("video", 10)],
                  repr(quota_rows(qenv)))
            check("settle closed the row id as succeeded with 10 s used",
                  quota.settles == [(1, "succeeded", 10)],
                  repr(quota.settles))
            check("the day now shows 490 of 500 seconds left",
                  Q.remaining("video", env=qenv) == 490,
                  repr(Q.remaining("video", env=qenv)))
            check("the row is succeeded in the ledger",
                  [r[3] for r in quota_rows(qenv)] == ["succeeded"],
                  repr(quota_rows(qenv)))


# ---------------------------------------------------------------------------
# 2. failure releases the seconds

def test_failed_clip_releases_its_seconds():
    with workdir() as d:
        with quota_env(d) as qenv:
            run = Run(d)
            clock = FakeClock()
            quota = SpyQuota(Q)
            fake = FakeAgnes(create_answers=[
                (400, {"error": {"code": "bad_request",
                                 "message": "prompt too long"}})],
                now=clock)
            env = video(run, quota, transport=fake, sleep=clock.sleep,
                        clock=clock)
            check("a vendor 400 is reported by its own name",
                  env["reason_code"] == "bad_request", json.dumps(env))
            check("settle closed the row as failed with the seconds used",
                  quota.settles == [(1, "failed", 10)], repr(quota.settles))
            check("the failed clip gave its 10 seconds back",
                  Q.remaining("video", env=qenv) == 500,
                  repr(Q.remaining("video", env=qenv)))
            check("the row is failed in the ledger",
                  [r[3] for r in quota_rows(qenv)] == ["failed"],
                  repr(quota_rows(qenv)))


def test_task_failed_also_releases():
    with workdir() as d:
        with quota_env(d) as qenv:
            run = Run(d)
            clock = FakeClock()
            quota = SpyQuota(Q)
            fake = FakeAgnes(poll_answers=[
                (200, {"status": "failed", "error": {"message": "render died"}})],
                now=clock)
            env = video(run, quota, transport=fake, sleep=clock.sleep,
                        clock=clock)
            check("a failed task is AGNES_TASK_FAILED",
                  env["reason_code"] == "AGNES_TASK_FAILED", json.dumps(env))
            check("a failed task releases its seconds",
                  quota.settles == [(1, "failed", 10)]
                  and Q.remaining("video", env=qenv) == 500,
                  repr((quota.settles, Q.remaining("video", env=qenv))))


# ---------------------------------------------------------------------------
# 3. a pool folder that cannot be resolved reserves nothing

def test_missing_pool_directory_reserves_nothing():
    with workdir() as d:
        run = Run(d)
        quota = NoPoolQuota()
        fake = FakeAgnes()
        env = video(run, quota, pool_dir=None, transport=fake)
        check("an unresolvable slot folder stops the door",
              env["outcome"] == "error"
              and env["reason_code"] == "agnes-quota-unavailable",
              json.dumps(env))
        check("nothing was reserved and nothing was sent",
              quota.reserved == [] and fake.posts == [],
              repr((quota.reserved, fake.posts)))


# ---------------------------------------------------------------------------
# 4. a vendor 402 records the day exhausted and stops the day

def test_402_stops_the_day():
    with workdir() as d:
        with quota_env(d) as qenv:
            run = Run(d)
            clock = FakeClock()
            fake = FakeAgnes(create_answers=[(402, QUOTA_402)], now=clock)
            env = video(run, Q, transport=fake, sleep=clock.sleep, clock=clock)
            check("402 names AGNES_QUOTA_EXHAUSTED",
                  env["reason_code"] == "AGNES_QUOTA_EXHAUSTED",
                  json.dumps(env))
            check("the pool ledger records the day as exhausted until reset",
                  env["evidence"].get("quota_state") == "exhausted_until_reset",
                  repr(env["evidence"]))
            check("no video seconds are left that day",
                  Q.remaining("video", env=qenv) == 0,
                  repr(Q.remaining("video", env=qenv)))
            second = FakeAgnes(now=clock)
            env2 = video(run, Q, logical_key="seg-2", transport=second,
                         sleep=clock.sleep, clock=clock)
            check("the next job that day is refused before any submit",
                  env2["reason_code"] == "AGNES_QUOTA_EXHAUSTED"
                  and second.posts == [], json.dumps(env2))


# ---------------------------------------------------------------------------
# 5. the seventh 503 fails by name

def test_seventh_503_fails_by_name():
    with workdir() as d:
        with quota_env(d) as qenv:
            run = Run(d)
            clock = FakeClock()
            fake = FakeAgnes(create_answers=[(503, QUEUE_FULL)] * 7, now=clock)
            env = video(run, Q, transport=fake, sleep=clock.sleep, clock=clock)
            check("the seventh 503 fails by name",
                  env["outcome"] == "error"
                  and env["reason_code"] == "AGNES_QUEUE_FULL",
                  json.dumps(env))
            check("503 was tried exactly seven times",
                  len(fake.posts) == 7, repr(len(fake.posts)))
            check("six back-offs ran and none is unbounded",
                  clock.t == 660.0, repr(clock.t))
            check("the cap released its reservation",
                  Q.remaining("video", env=qenv) == 500,
                  repr(Q.remaining("video", env=qenv)))


# ---------------------------------------------------------------------------

def test_no_check_failed():
    """Last, so both runners see every FAIL the checks above recorded."""
    assert not FAILS, "failed checks: %s" % FAILS


def main():
    tests = sorted((globals()[n] for n in list(globals())
                    if n.startswith("test_") and callable(globals()[n])),
                   key=lambda f: f.__code__.co_firstlineno)
    for name in tests:
        try:
            name()
        except Exception as exc:                  # noqa: BLE001
            check("%s raised" % name.__name__, False,
                  "%s: %s" % (type(exc).__name__, exc))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d tests passed" % len(tests))
    return 0


if __name__ == "__main__":
    sys.exit(main())

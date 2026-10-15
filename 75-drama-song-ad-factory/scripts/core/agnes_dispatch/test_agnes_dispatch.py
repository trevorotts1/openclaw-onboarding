#!/usr/bin/env python3
"""Tests for agnes_dispatch: the one Agnes door (BUILD-PLAN W1-agnes-core-U1).

Zero paid calls: every HTTP answer comes from the fake Agnes below, the clock
and the sleeper are test-driven, and the key is a fake string that must never
reach stdout, stderr, an envelope or a ledger. Nothing here talks to
``apihub.agnes-ai.com`` or ``api.kie.ai``.

Run: python3 agnes_dispatch/test_agnes_dispatch.py
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                 # core/

import agnes_dispatch.agnes_dispatch as A   # noqa: E402 (module under test)
import spend_ledger as L                     # noqa: E402 (same core/ tree)

FAKE_KEY = "cpk-FAKE-KEY-9f3a1bZZ-never-a-real-key"
#: A prompt inside the decided 5,000-20,000 band.
BIG_PROMPT = ("The character stands in the kitchen, breathing hard, hands flat "
              "on the counter, morning light cutting across her face. ") * 160
VIDEO_URL = "https://cdn.example.invalid/clip.mp4"
MP4 = b"FAKE-MP4-BYTES"
PNG = b"FAKE-PNG-BYTES"
QUEUE_FULL = {"error": {"code": "video_queue_full", "message": "queue full"}}
RATE_LIMIT = {"error": {"code": "rate_limit_exceeded", "message": "rpm"}}

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


# ---------------------------------------------------------------------------
# fixtures

class FakeClock:
    """A clock the door itself moves: it only advances when the door sleeps."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += float(seconds)


class FakeAgnes:
    """A fake Agnes: scripted create/poll answers, no network, no key printed.

    ``create_answers`` / ``poll_answers`` are ``(status, payload)`` pairs;
    a payload of None means "a normal answer for this call".
    """

    def __init__(self, create_answers=None, poll_answers=None, media=MP4,
                 now=time.monotonic):
        self.create_answers = [tuple(a) for a in (create_answers or [])]
        self.poll_answers = [tuple(a) for a in (poll_answers or [])]
        self.media = media
        self.now = now
        self.posts = []
        self.poll_urls = []
        self.poll_times = []
        self.downloads = []
        self.keys_seen = []
        self.on_poll = None
        self._n = 0

    def __call__(self, method, url, key, body):
        method = str(method or "GET").upper()
        self.keys_seen.append(key)
        if method == "POST":
            self.posts.append(body)
            if self.create_answers:
                status, payload = self.create_answers.pop(0)
            else:
                status, payload = 200, None
            if payload is None:
                self._n += 1
                payload = {"video_id": "vid-%d" % self._n, "status": "queued",
                           "progress": 0}
            return status, payload
        if method == "GET":
            if self.on_poll:
                self.on_poll(len(self.poll_times))
            self.poll_urls.append(url)
            self.poll_times.append(self.now())
            if self.poll_answers:
                return self.poll_answers.pop(0)
            return 200, {"status": "completed", "progress": 100,
                         "metadata": {"url": VIDEO_URL}}
        if method == "DOWNLOAD":
            self.downloads.append(url)
            return 200, self.media
        raise AssertionError("unexpected transport method %r" % method)


class FakeQuota:
    """Stands in for unit W1-agnes-core-U2's agnes_quota (same release group)."""

    def __init__(self, answer=None, state_path=None):
        self.answer = {"outcome": "ok"} if answer is None else answer
        self.calls = []
        self._state = state_path

    def reserve(self, kind=None, units=None, run_id=None, logical_key=None):
        self.calls.append({"kind": kind, "units": units, "run_id": run_id,
                           "logical_key": logical_key})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer

    def state_path(self):
        return self._state or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                           "agnes-quota.sqlite3")


@contextlib.contextmanager
def workdir():
    with tempfile.TemporaryDirectory(prefix="agnes-u1-") as d:
        yield d


class Run:
    """One throwaway run: ledger, working folder and quota folder."""

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


def approved_storyboard():
    return {"shots": [{"shot_id": "s1", "status": "storyboard_approved"},
                      {"shot_id": "s2", "status": "storyboard_approved"}],
            "review": {"outcome": "pass"}}


def request(video=True, agnes="yes", storyboard=True, extra=None):
    req = {"card_receipt": card_receipt(agnes)}
    if video and storyboard:
        req["storyboard"] = approved_storyboard()
    if extra:
        req.update(extra)
    return req


def jobs(ledger, logical_key=None):
    conn = sqlite3.connect(ledger)
    try:
        rows = conn.execute(
            "SELECT logical_key, attempt_id, state, final_outcome,"
            " remote_task_id, actual_cost, estimated_cost FROM jobs"
            + (" WHERE logical_key=?" if logical_key else ""),
            (logical_key,) if logical_key else ()).fetchall()
    finally:
        conn.close()
    return rows


def video(run, **kw):
    """One video dispatch with every test seam injected."""
    args = dict(save_dir=run.save, ledger_db=run.ledger, run_id="run-t",
                logical_key="seg-1", attempt_id="a1", prompt=BIG_PROMPT,
                quota=FakeQuota(), key=FAKE_KEY, pool_dir=run.pool)
    args.update(kw)
    return A.dispatch_video(request(), **args)


# ---------------------------------------------------------------------------
# Prove: image round trip at cost 0

def test_image_round_trip_at_cost_zero():
    with workdir() as d:
        run = Run(d)
        fake = FakeAgnes(create_answers=[
            (200, {"data": [{"url": "https://cdn.example.invalid/still.png",
                             "b64_json": None}]})], media=PNG)
        quota = FakeQuota()
        env = A.dispatch_image(request(video=False), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="still-1", attempt_id="a1",
                               prompt="Front-facing head-and-shoulders close-up.",
                               quota=quota, key=FAKE_KEY, transport=fake)
        check("image round trip is ok", env["outcome"] == "ok", json.dumps(env))
        check("image cost is 0", env["evidence"]["actual_cost"] == 0)
        check("image bytes saved", os.path.isfile(env["evidence"]["saved_paths"][0]))
        row = jobs(run.ledger, "still-1")
        check("image ledger row reconciled at 0",
              len(row) == 1 and row[0][2] == "reconciled"
              and row[0][5] == 0, repr(row))
        check("image reserved 1 unit of quota",
              quota.calls == [{"kind": "image", "units": 1, "run_id": "run-t",
                               "logical_key": "still-1"}], repr(quota.calls))
        check("image body carries the model, size, ratio and no n",
              fake.posts[0]["model"] == A.IMAGE_MODEL
              and fake.posts[0]["size"] == "2K"
              and fake.posts[0]["ratio"] == "9:16"
              and "n" not in fake.posts[0], repr(fake.posts[0]))


# ---------------------------------------------------------------------------
# Prove: video create -> polls >= 15 s apart -> mp4 saved

def test_video_create_polls_and_saves():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        quota = FakeQuota()
        fake = FakeAgnes(now=clock, poll_answers=[
            (200, {"status": "queued", "progress": 0}),
            (200, {"status": "running", "progress": 40}),
            (200, {"status": "completed", "progress": 100,
                   "metadata": {"url": VIDEO_URL}})])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock,
                    quota=quota,
                    first_frame="https://cdn.example.invalid/still.png")
        check("video round trip is ok", env["outcome"] == "ok", json.dumps(env))
        check("video saved as mp4", env["evidence"]["saved_paths"][0].endswith(".mp4")
              and os.path.isfile(env["evidence"]["saved_paths"][0]))
        check("video bytes match the download",
              open(env["evidence"]["saved_paths"][0], "rb").read() == MP4)
        check("video sha256 recorded", len(env["evidence"]["sha256"]) == 64)
        gaps = [b - a for a, b in zip(fake.poll_times, fake.poll_times[1:])]
        check("polls are at least 15 s apart",
              len(fake.poll_times) == 3 and all(g >= A.POLL_MIN_S - 1e-9 for g in gaps),
              repr(fake.poll_times))
        body = fake.posts[0]
        check("video body is the decided keyframe body",
              body["model"] == A.VIDEO_MODEL and body["mode"] == "keyframe"
              and body["seconds"] == "10" and body["size"] == "720P"
              and body["aspect_ratio"] == "9:16"
              and body["first_frame"] == "https://cdn.example.invalid/still.png"
              and "n" not in body, repr(body))
        check("poll URL names the video id and the model",
              "video_id=vid-1" in fake.poll_urls[0]
              and "model_name=" + A.VIDEO_MODEL in fake.poll_urls[0],
              repr(fake.poll_urls[0]))
        check("video ledger row reconciled at 0",
              jobs(run.ledger, "seg-1")[0][2:] == ("reconciled", "succeeded",
                                                   "vid-1", 0, 0),
              repr(jobs(run.ledger, "seg-1")))
        check("video reserved 10 seconds of quota",
              quota.calls == [{"kind": "video", "units": 10, "run_id": "run-t",
                               "logical_key": "seg-1"}], repr(quota.calls))
        receipt = os.path.join(run.save, "seg-1.a1.prompt-receipt.json")
        check("prompt receipt written for the ledger row", os.path.isfile(receipt))
        rec = json.load(open(receipt, encoding="utf-8"))
        check("prompt receipt matches qc_gate's row shape",
              rec["logical_key"] == "seg-1" and rec["attempt_id"] == "a1"
              and rec["check"]["verdict"] == "PASS"
              and len(rec["prompt_sha256"]) == 64, repr(rec))


def test_poll_s_under_fifteen_is_clamped():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, poll_answers=[
            (200, {"status": "queued"}),
            (200, {"status": "completed", "metadata": {"url": VIDEO_URL}})])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock, poll_s=3)
        check("a 3-second poll request still polls at >= 15 s",
              env["outcome"] == "ok"
              and all(b - a >= A.POLL_MIN_S - 1e-9
                      for a, b in zip(fake.poll_times, fake.poll_times[1:])),
              repr(fake.poll_times))


# ---------------------------------------------------------------------------
# Prove: a 3rd concurrent video waits for a slot

def test_third_video_waits_for_a_slot():
    with workdir() as d:
        run = Run(d)
        fake = FakeAgnes()
        hold = threading.Event()
        fake.on_poll = lambda n: hold.wait(timeout=20)
        slept = []

        def sleep(seconds):
            slept.append((threading.current_thread().name, float(seconds)))
            time.sleep(0.002)

        results = {}

        def one(name):
            results[name] = video(run, logical_key=name, attempt_id="a1",
                                  transport=fake, sleep=sleep, clock=time.monotonic)

        threads = [threading.Thread(target=one, args=(n,), name=n)
                   for n in ("seg-1", "seg-2", "seg-3")]
        threads[0].start()
        threads[1].start()
        wait_until(lambda: len(fake.posts) == 2, "two jobs were created")
        threads[2].start()
        wait_until(lambda: any(n == "seg-3" for n, _ in slept),
                   "the third job waited for a slot")
        check("a third video does not create a job while two are in flight",
              len(fake.posts) == 2, repr(len(fake.posts)))
        hold.set()
        for t in threads:
            t.join(timeout=30)
        check("all three videos finished once slots freed",
              len(fake.posts) == 3
              and all(results[n]["outcome"] == "ok" for n in results),
              repr({n: r["outcome"] for n, r in results.items()}))
        check("every video row reconciled",
              len(jobs(run.ledger)) == 3
              and all(r[2] == "reconciled" for r in jobs(run.ledger)),
              repr(jobs(run.ledger)))


def wait_until(cond, what, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if cond():
            return True
        time.sleep(0.005)
    raise AssertionError("timed out waiting until %s" % what)


# ---------------------------------------------------------------------------
# Prove: 503 x2 then 200 -> one submitted row; 429 then 200 -> one row

def test_503_twice_then_200_is_one_submitted_row():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, create_answers=[(503, QUEUE_FULL),
                                                    (503, QUEUE_FULL)])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        rows = jobs(run.ledger, "seg-1")
        check("503 twice then 200 is ok", env["outcome"] == "ok", json.dumps(env))
        check("503 was retried twice (3 attempts)",
              len(fake.posts) == 3, repr(len(fake.posts)))
        check("503 backoff was 60 s then 120 s", clock.t == 180.0, repr(clock.t))
        check("exactly one ledger row, submitted once",
              len(rows) == 1 and rows[0][2] == "reconciled"
              and rows[0][4] == "vid-1", repr(rows))
        check("the ok envelope reports the queue wait",
              env["evidence"]["retries"] == 2
              and env["evidence"]["queue_full_wait_s"] == 180,
              repr(env["evidence"]))


def test_429_then_200_is_one_row():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, create_answers=[(429, RATE_LIMIT)])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        rows = jobs(run.ledger, "seg-1")
        check("429 then 200 is ok", env["outcome"] == "ok", json.dumps(env))
        check("429 was resubmitted (2 attempts)",
              len(fake.posts) == 2, repr(len(fake.posts)))
        check("429 backed off 60 s", clock.t >= 60.0, repr(clock.t))
        check("exactly one row for the 429 job",
              len(rows) == 1 and rows[0][4] == "vid-1", repr(rows))


def test_thirty_minutes_of_503_reports_queue_full_and_keeps_waiting():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        loud = []
        fake = FakeAgnes(now=clock,
                         create_answers=[(503, QUEUE_FULL)] * 20)
        real_loud = A._loud
        A._loud = lambda kind, code, detail: loud.append((kind, code, detail))
        try:
            env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        finally:
            A._loud = real_loud
        check("30 minutes of continuous 503 does not give up",
              env["outcome"] == "ok", json.dumps(env))
        check("AGNES_QUEUE_FULL is reported loudly, once",
              len(loud) == 1 and loud[0][1] == "AGNES_QUEUE_FULL"
              and loud[0][0] in ("warn", "fail"), repr(loud))


# ---------------------------------------------------------------------------
# Prove: 402 / 401 -> the named codes and no submit

def test_402_is_quota_exhausted_with_no_submit():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, create_answers=[
            (402, {"error": {"code": "quota_exhausted",
                             "message": "Insufficient Token Plan quota"}})])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        rows = jobs(run.ledger, "seg-1")
        check("402 names AGNES_QUOTA_EXHAUSTED",
              env["outcome"] == "rejected"
              and env["reason_code"] == "AGNES_QUOTA_EXHAUSTED",
              json.dumps(env))
        check("402 keeps the vendor message",
              env["evidence"]["vendor_message"] == "Insufficient Token Plan quota",
              repr(env["evidence"]))
        check("402 was submitted once and never marked submitted",
              len(fake.posts) == 1 and len(rows) == 1
              and rows[0][4] is None and rows[0][2] == "reconciled"
              and rows[0][5] == 0, repr(rows))


def test_401_is_key_refused_with_no_submit():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, create_answers=[
            (401, {"error": {"code": "unauthorized",
                             "message": "This token status is unavailable"}})])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        rows = jobs(run.ledger, "seg-1")
        check("401 names AGNES_KEY_REFUSED",
              env["outcome"] == "rejected"
              and env["reason_code"] == "AGNES_KEY_REFUSED", json.dumps(env))
        check("401 was never marked submitted",
              len(fake.posts) == 1 and len(rows) == 1 and rows[0][4] is None,
              repr(rows))


def test_403_is_key_refused_too():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, create_answers=[
            (403, {"error": {"code": "forbidden", "message": "no permission"}})])
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        check("403 names AGNES_KEY_REFUSED",
              env["reason_code"] == "AGNES_KEY_REFUSED", json.dumps(env))


# ---------------------------------------------------------------------------
# Prove: seconds "12" refused locally; the prompt band; storyboard approval

def test_seconds_other_than_ten_is_refused_locally():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock)
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock,
                    seconds="12")
        check("seconds 12 is refused locally",
              env["reason_code"] == "AGNES_SECONDS_NOT_10"
              and env["outcome"] == "rejected", json.dumps(env))
        check("seconds 12 never reached Agnes or the ledger",
              len(fake.posts) == 0 and jobs(run.ledger) == [],
              repr((fake.posts, jobs(run.ledger))))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(extra={"seconds": "12"}),
                               save_dir=run.save, ledger_db=run.ledger,
                               run_id="run-t", logical_key="seg-1",
                               attempt_id="a1", prompt=BIG_PROMPT,
                               quota=FakeQuota(), key=FAKE_KEY,
                               pool_dir=run.pool, transport=FakeAgnes())
        check("seconds carried by the request are refused too",
              env["reason_code"] == "AGNES_SECONDS_NOT_10", json.dumps(env))


def test_prompt_band():
    with workdir() as d:
        run = Run(d)
        fake = FakeAgnes()
        env = video(run, transport=fake, prompt="x" * 21000)
        check("a 21,000-character prompt is refused",
              env["reason_code"] == "AGNES_PROMPT_OVER_BAND"
              and env["outcome"] == "rejected", json.dumps(env))
        check("the over-band prompt never reached Agnes",
              len(fake.posts) == 0 and jobs(run.ledger) == [])
    with workdir() as d:
        run = Run(d)
        env = video(run, transport=FakeAgnes(), prompt="x" * 4000)
        check("a 4,000-character prompt is FLAGged and still sent",
              env["outcome"] == "ok"
              and env["evidence"]["warnings"] == ["PROMPT_UNDER_BAND"]
              and env["evidence"]["prompt_verdict"] == "FLAG", json.dumps(env))
        receipt = json.load(open(os.path.join(run.save,
                                              "seg-1.a1.prompt-receipt.json"),
                                 encoding="utf-8"))
        check("the FLAG lands in the prompt receipt",
              receipt["check"]["verdict"] == "FLAG", repr(receipt))
    with workdir() as d:
        run = Run(d)
        env = video(run, transport=FakeAgnes(),
                    prompt="x" * A.PROMPT_MIN_CHARS)
        check("a 5,000-character prompt is PASS, not FLAG",
              env["outcome"] == "ok" and env["evidence"]["warnings"] == [])


def test_video_before_storyboard_approval_is_refused():
    with workdir() as d:
        run = Run(d)
        fake = FakeAgnes()
        env = A.dispatch_video(request(storyboard=False), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="seg-1", attempt_id="a1",
                               prompt=BIG_PROMPT, quota=FakeQuota(),
                               key=FAKE_KEY, pool_dir=run.pool, transport=fake)
        check("video before storyboard approval is refused",
              env["reason_code"] == "STORYBOARD_NOT_APPROVED", json.dumps(env))
        check("the storyboard refusal sent nothing",
              len(fake.posts) == 0 and jobs(run.ledger) == [])
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(storyboard=False, extra={
            "storyboard": {"shots": [{"shot_id": "s1",
                                      "status": "draft"}],
                           "review": {"outcome": "pass"}}}),
            save_dir=run.save, ledger_db=run.ledger, run_id="run-t",
            logical_key="seg-1", attempt_id="a1", prompt=BIG_PROMPT,
            quota=FakeQuota(), key=FAKE_KEY, pool_dir=run.pool)
        check("an unapproved shot card is refused",
              env["reason_code"] == "STORYBOARD_NOT_APPROVED", json.dumps(env))


# ---------------------------------------------------------------------------
# Prove: the fake key never appears in stdout, stderr, envelope or ledger

def test_fake_key_never_escapes():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock)
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            env = video(run, transport=fake, sleep=clock.sleep, clock=clock)
        blobs = [out.getvalue(), err.getvalue(), json.dumps(env, default=str),
                 open(run.ledger, "rb").read().decode("utf-8", "replace")]
        for name in os.listdir(run.save):
            blobs.append(open(os.path.join(run.save, name), "rb").read().decode(
                "utf-8", "replace"))
        check("the run succeeded (so every surface was exercised)",
              env["outcome"] == "ok", json.dumps(env))
        check("the key reached the transport header",
              fake.keys_seen and all(k == FAKE_KEY for k in fake.keys_seen))
        check("the fake key is nowhere in stdout, stderr, envelope or ledger",
              not any(FAKE_KEY in blob for blob in blobs),
              repr([b[:200] for b in blobs if FAKE_KEY in b]))


# ---------------------------------------------------------------------------
# Gate order: the placeholder is refused before anything is reserved

def test_placeholder_is_refused_before_anything_is_reserved():
    with workdir() as d:
        run = Run(d)
        fake = FakeAgnes()
        env = A.dispatch_video(request(extra={"shot": {"note": "{{TODO}}"}}),
                               save_dir=run.save, ledger_db=run.ledger,
                               run_id="run-t", logical_key="seg-1",
                               attempt_id="a1", prompt=BIG_PROMPT,
                               quota=FakeQuota(), key=FAKE_KEY,
                               pool_dir=run.pool, transport=fake)
        check("an unfilled placeholder is refused first",
              env["reason_code"] == "REQUEST_PLACEHOLDER"
              and env["outcome"] == "rejected", json.dumps(env))
        check("the placeholder refusal reserved nothing",
              len(fake.posts) == 0 and jobs(run.ledger) == [])


# ---------------------------------------------------------------------------
# Gate order: on-screen text, song pick, script approval, card, AGNES choice

def test_gates_are_imported_and_applied_in_order():
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(agnes="no"), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="seg-1", attempt_id="a1",
                               prompt=BIG_PROMPT, quota=FakeQuota(),
                               key=FAKE_KEY, pool_dir=run.pool,
                               transport=FakeAgnes())
        check("agnes.answer != yes is AGNES_NOT_CHOSEN",
              env["reason_code"] == "AGNES_NOT_CHOSEN"
              and env["evidence"]["agnes_answer"] == "no", json.dumps(env))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(extra={"card_receipt": {
            "answers": {"video_style": "2D Hand-Painted"}}}),
            save_dir=run.save, ledger_db=run.ledger, run_id="run-t",
            logical_key="seg-1", attempt_id="a1", prompt=BIG_PROMPT,
            quota=FakeQuota(), key=FAKE_KEY, pool_dir=run.pool,
            transport=FakeAgnes())
        check("an unanswered card is CARD_UNANSWERED",
              env["reason_code"] == "CARD_UNANSWERED"
              and env["outcome"] == "waiting", json.dumps(env))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(
            request(extra={"shot": {"on_screen_text": "SALE TODAY"}}),
            save_dir=run.save, ledger_db=run.ledger, run_id="run-t",
            logical_key="seg-1", attempt_id="a1", prompt=BIG_PROMPT,
            quota=FakeQuota(), key=FAKE_KEY, pool_dir=run.pool,
            transport=FakeAgnes())
        check("unchecked on-screen text is ONSCREEN_TEXT_NOT_CHECKED",
              env["reason_code"] == "ONSCREEN_TEXT_NOT_CHECKED", json.dumps(env))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="seg-1", attempt_id="a1",
                               prompt=BIG_PROMPT, quota=FakeQuota(), key=None,
                               pool_dir=run.pool)
        check("no key at all is AGNES_KEY_MISSING",
              env["reason_code"] == "AGNES_KEY_MISSING", json.dumps(env))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="seg-1", attempt_id="a1",
                               prompt=BIG_PROMPT,
                               quota=FakeQuota({"outcome": "waiting",
                                                "reason_code":
                                                    "agnes-quota-next-day"}),
                               key=FAKE_KEY, pool_dir=run.pool)
        check("a closed quota gate waits, it never sends",
              env["reason_code"] == "agnes-quota-next-day"
              and env["outcome"] == "waiting", json.dumps(env))
    with workdir() as d:
        run = Run(d)
        env = A.dispatch_video(request(), save_dir=run.save,
                               ledger_db=run.ledger, run_id="run-t",
                               logical_key="seg-1", attempt_id="a1",
                               prompt=BIG_PROMPT, quota=FakeQuota(NotImplementedError(
                                   "no quota module")), key=FAKE_KEY,
                               pool_dir=run.pool)
        check("a broken quota module stops the door before any network call",
              env["reason_code"] == "agnes-quota-unavailable"
              and env["outcome"] == "error", json.dumps(env))


def test_unknown_after_timeout_is_polled_never_resubmitted():
    with workdir() as d:
        run = Run(d)
        clock = FakeClock()
        fake = FakeAgnes(now=clock, poll_answers=[(200, {"status": "running"})] * 5)
        env = video(run, transport=fake, sleep=clock.sleep, clock=clock,
                    timeout_s=40)
        rows = jobs(run.ledger, "seg-1")
        check("a job still unknown after the wait budget is held, not retried",
              env["reason_code"] == "unknown-outcome-no-retry"
              and env["outcome"] == "waiting"
              and len(fake.posts) == 1, json.dumps(env))
        check("the unknown row keeps the remote task id",
              rows[0][2] == "unknown" and rows[0][4] == "vid-1", repr(rows))


# ---------------------------------------------------------------------------

def test_no_check_failed():
    """Last, so both runners see every FAIL the checks above recorded."""
    assert not FAILS, "failed checks: %s" % FAILS


TESTS = sorted((globals()[n] for n in list(globals())
                if n.startswith("test_") and callable(globals()[n])),
               key=lambda f: f.__code__.co_firstlineno)


def main():
    for name in TESTS:
        try:
            name()
        except Exception as exc:                          # noqa: BLE001
            check("%s raised" % name.__name__, False,
                  "%s: %s" % (type(exc).__name__, exc))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

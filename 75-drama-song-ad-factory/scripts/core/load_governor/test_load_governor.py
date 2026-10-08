#!/usr/bin/env python3
"""Tests for the Skill 75 load governor. stdlib only, no ffmpeg, no network.

Run: python3 scripts/core/load_governor/test_load_governor.py
"""
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)
TMP = tempfile.mkdtemp(prefix="lg-test-")
os.environ["DSAF_GOVERNOR_DIR"] = TMP          # never touch a real shared dir
os.environ.pop("DSAF_HEAVY_SLOTS", None)

import load_governor as LG  # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, (" (%s)" % detail) if not cond and detail else ""))
    if not cond:
        FAILS.append(name)


def holder():
    """A separate process that holds one heavy slot until its stdin closes."""
    code = ("import sys; sys.path.insert(0, %r)\n"
            "import load_governor as LG\n"
            "with LG.heavy_slot('holder', probe=lambda: 90.0):\n"
            "    print('held', flush=True); sys.stdin.read()\n" % CORE)
    p = subprocess.Popen([sys.executable, "-c", code],
                         stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         env=dict(os.environ))
    assert p.stdout.readline().strip() == "held"
    return p


def release(p):
    p.stdin.close()
    p.wait(timeout=10)


# 1. third heavy job waits while two processes hold the two slots
a, b = holder(), holder()
try:
    t0 = time.monotonic()
    try:
        with LG.heavy_slot("third-job", poll_s=0.05, max_wait_s=0.4, probe=lambda: 90.0):
            got = True
    except LG.HeavyJobTimeout as e:
        got, msg = False, str(e)
    check("third job does not run while 2 slots held", not got)
    check("timeout names the job", "third-job" in msg)
    check("it actually waited", time.monotonic() - t0 >= 0.4)
    release(a)
    with LG.heavy_slot("third-job", poll_s=0.05, max_wait_s=5, probe=lambda: 90.0):
        got = True
    check("third job runs once a slot frees", got)
finally:
    for p in (a, b):
        if p.poll() is None:
            release(p)

# cap from env var
os.environ["DSAF_HEAVY_SLOTS"] = "1"
c = None
try:
    check("cap env var read", LG.slot_cap() == 1)
finally:
    os.environ.pop("DSAF_HEAVY_SLOTS")
check("default cap is 2", LG.slot_cap() == 2)

# nested use in one thread rides the outer slot (no self-deadlock)
with LG.heavy_slot("outer", probe=lambda: 90.0):
    with LG.heavy_slot("inner", poll_s=0.01, max_wait_s=0.1, probe=lambda: 90.0):
        pass
check("nested heavy_slot does not take a second slot", True)

# 2. low memory: waits, then fails loudly after the timeout; never runs
ran = []
try:
    with LG.heavy_slot("ffmpeg-render", poll_s=0.05, max_wait_s=0.3, probe=lambda: 12.0):
        ran.append(1)
except LG.HeavyJobTimeout as e:
    err = str(e)
check("low memory: job never started", not ran)
check("low memory: loud failure names job + memory", "ffmpeg-render" in err and "12%" in err)
try:
    with LG.heavy_slot("unreadable", poll_s=0.05, max_wait_s=0.2, probe=lambda: None):
        ran.append(2)
except LG.HeavyJobTimeout:
    pass
check("unmeasurable memory never starts a job", ran == [])
# memory recovers mid-wait -> job starts and wait is in the receipt
seq = iter([10.0, 10.0, 80.0])
with LG.heavy_slot("recovers", poll_s=0.05, max_wait_s=5, probe=lambda: next(seq)):
    pass
row = [r for r in LG.receipt()["heavy_jobs"] if r["job"] == "recovers"][0]
check("wait time lands in the receipt", row["waited_s"] >= 0.1 and LG.receipt()["total_wait_s"] >= 0.1)

# 3. ffmpeg argv always carries nice and -threads
for args, thr, want in (
        (["-i", "a.mp4", "o.mp4"], None, "4"),
        (["-i", "a.mp4", "-threads", "16", "o.mp4"], None, "4"),
        (["-threads", "2", "-i", "a.mp4", "o.mp4"], None, "2"),
        (["-i", "a.mp4", "o.mp4"], 8, "4"),
        (["-i", "a.mp4", "o.mp4"], 3, "3")):
    v = LG.ffmpeg_argv(args, threads=thr)
    check("argv %s/%s" % (args[:2], thr),
          v[:3] == ["nice", "-n", "10"] and v[3] == "ffmpeg" and v[4:6] == ["-threads", want]
          and v.count("-threads") == 1, v)
again = LG.bounded(LG.ffmpeg_argv(["-i", "x", "y"]))
check("bounded is idempotent", again == LG.ffmpeg_argv(["-i", "x", "y"]))
try:
    LG.bounded(["ffprobe", "x"])
    check("bounded refuses non-ffmpeg", False)
except LG.LoadGovernorError:
    check("bounded refuses non-ffmpeg", True)
try:
    LG.run_heavy(["whisper", "a.mp3"], "asr")
    check("OpenAI whisper refused", False)
except LG.LoadGovernorError as e:
    check("OpenAI whisper refused", e.code == "LOCAL_ASR_FORBIDDEN")
rc = LG.run_heavy([sys.executable, "-c", "print(1)"], "plain-heavy", capture_output=True, text=True)
check("run_heavy runs a non-ffmpeg job through the gate", rc.stdout.strip() == "1")

# 4. cleanup never touches deliverables
d = tempfile.mkdtemp(prefix="lg-clean-")
mk = lambda n: (open(os.path.join(d, n), "w").write("x"), os.path.join(d, n))[1]  # noqa: E731
seg, tmpclip = mk("seg_001.mp4"), mk("conform_002.mp4")
master, srt, song, stem, rcpt = (mk("ad-master.mp4"), mk("ad.srt"), mk("ad.mp3"),
                                 mk("vocal-stem.wav"), mk("run-receipt.json"))
out = mk("next-stage-out.mp4")
reg = LG.StageRegistry()
reg.register("conform", [seg, tmpclip, master, srt, song, stem, rcpt])
reg.consumed("conform", out, verify=lambda p: False)
check("unverified output deletes nothing", all(os.path.exists(f) for f in (seg, tmpclip)))
reg.consumed("conform", out, verify=lambda p: True)
check("verified: intermediates deleted", not os.path.exists(seg) and not os.path.exists(tmpclip))
check("deliverables survive", all(os.path.exists(f) for f in (master, srt, song, stem, rcpt)))
acts = {os.path.basename(r["file"]): r["action"] for r in reg.log}
check("every deletion is logged", acts.get("seg_001.mp4") == "deleted" and acts.get("ad-master.mp4") == "kept-deliverable")
reg2 = LG.StageRegistry()
reg2.register("s", [os.path.join(d, "gone_dir", "x.mp4")])
os.mkdir(os.path.join(d, "ro"))
ro = os.path.join(d, "ro", "inter.mp4")
open(ro, "w").write("x")
os.chmod(os.path.join(d, "ro"), 0o500)
reg2.register("s", [ro])
import io, contextlib  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stderr(buf):
    reg2.consumed("s", out)
os.chmod(os.path.join(d, "ro"), 0o700)
if os.geteuid() != 0:
    check("failed deletion prints WARNING", "WARNING" in buf.getvalue()
          and any(r["action"] == "delete-failed" for r in reg2.log))

# 5. KIE limiter: never above 20 per rolling 10 s, retries on 429
class Clock:
    t = 1000.0
    def now(self): return self.t
    def sleep(self, s): self.t += s
clk, sent = Clock(), []
def one():
    LG.kie_acquire(sleep=clk.sleep, clock=clk.now)
    sent.append(clk.t)
for _ in range(95):
    one()
worst = max(sum(1 for u in sent if t <= u < t + 10.0) for t in sent)
check("KIE never exceeds 20 in any 10 s window", worst <= 20, worst)
check("KIE limiter really spaced them", sent[-1] - sent[0] >= 30)
# two real processes share the bucket
code = ("import sys; sys.path.insert(0, %r)\nimport load_governor as LG\n"
        "for _ in range(12): LG.kie_acquire()\nprint('done')\n" % CORE)
t0 = time.time()
shared = tempfile.mkdtemp(dir=TMP)
ps = [subprocess.Popen([sys.executable, "-c", code], stdout=subprocess.PIPE, text=True,
                       env=dict(os.environ, DSAF_GOVERNOR_DIR=shared)) for _ in range(2)]
[p.wait(timeout=60) for p in ps]
import json  # noqa: E402
stamps = sorted(json.load(open(os.path.join(shared, "kie-rate", "stamps.json"))))
check("two processes share one bucket (<=20 in window)",
      max(sum(1 for u in stamps if t <= u < t + 10.0) for t in stamps) <= 20 and time.time() - t0 >= 5)

calls = {"n": 0}
def flaky():
    calls["n"] += 1
    return (0, '{"code": 429, "msg": "rate limited"}') if calls["n"] < 3 else (0, '{"state":"ok"}')
naps = []
r = LG.kie_request(flaky, "submit", sleep=naps.append, acquire=lambda: None)
check("429 is backed off and retried", r[1] == '{"state":"ok"}' and calls["n"] == 3 and naps == [2.0, 4.0])
try:
    LG.kie_request(lambda: (0, "Too Many Requests"), "poll", retries=2, sleep=lambda s: None, acquire=lambda: None)
    check("persistent 429 fails loudly", False)
except LG.KieRateLimitError as e:
    check("persistent 429 fails loudly", "poll" in str(e))
check("a task id containing 429 is not a rate limit", not LG.is_rate_limited('{"task_id":"a14290b"}'))

# 6. wiring: every heavy call site goes through the governor
SITES = {"final_assembler/assembler.py": "run_ffmpeg", "final_assembler/frame_text.py": "run_ffmpeg",
         "final_assembler/sung_vocal_guard.py": "run_ffmpeg",
         "singing_detector/singing_detector.py": "run_ffmpeg",
         "lip_sync/stem_offset/stem_offset.py": "run_ffmpeg", "lip_sync/lip_gate/lip_gate.py": "run_ffmpeg",
         "shot_planner/motion_score.py": "run_ffmpeg", "delivery_variants/song_files.py": "run_ffmpeg",
         "audio_c3/lyric_timing.py": "heavy_slot", "kie_dispatch/kie_dispatch.py": "kie_request"}
for rel, needle in SITES.items():
    src = open(os.path.join(CORE, rel), encoding="utf-8").read()
    check("wired: %s uses %s" % (rel, needle), needle in src)

print("FAILED: %s" % FAILS if FAILS else "all load_governor checks passed")
sys.exit(1 if FAILS else 0)

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
os.environ.pop("KIE_API_KEY", None)

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

# 5. KIE limiter: 20 NEW generation requests per rolling 10 s; polls separate; 429 resubmits
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
stamps = sorted(json.load(open(os.path.join(shared, "kie-rate", LG.key_tag(), "stamps.json"))))
check("two processes share one bucket (<=20 in window)",
      max(sum(1 for u in stamps if t <= u < t + 10.0) for t in stamps) <= 20 and time.time() - t0 >= 5)

calls = {"n": 0}
def flaky():
    calls["n"] += 1
    return (0, '{"code": 429, "msg": "rate limited"}') if calls["n"] < 3 else (0, '{"state":"ok"}')
naps = []
r = LG.kie_request(flaky, "submit", generation=True, sleep=naps.append, acquire=lambda: None)
check("429 is backed off and resubmitted", r[1] == '{"state":"ok"}' and calls["n"] == 3 and naps == [2.0, 4.0])
try:
    LG.kie_request(lambda: (0, "Too Many Requests"), "submit --request job-7.json", generation=True,
                   retries=2, sleep=lambda s: None, acquire=lambda: None)
    check("persistent 429 fails loudly naming the job", False)
except LG.KieRateLimitError as e:
    check("persistent 429 fails loudly naming the job", "job-7.json" in str(e) and "NOT submitted" in str(e))

# polls never consume generation tokens (real bucket in a fresh shared dir)
os.environ["DSAF_GOVERNOR_DIR"] = tempfile.mkdtemp(dir=TMP)
LG.load_governor._poll_last[0] = 0.0
LG.kie_request(lambda: (0, "{}"), "wait", sleep=lambda s: None)
for _ in range(30):
    LG.kie_request(lambda: (0, "{}"), "poll", sleep=lambda s: None)
check("polls do not consume generation tokens",
      not os.path.exists(os.path.join(os.environ["DSAF_GOVERNOR_DIR"], "kie-rate")))
LG.kie_request(lambda: (0, "{}"), "submit", generation=True)
check("a generation request does consume one token",
      len(json.load(open(os.path.join(os.environ["DSAF_GOVERNOR_DIR"], "kie-rate", LG.key_tag(), "stamps.json")))) == 1)
# poll limiter: default 1 per second per process, configurable
pc = Clock(); LG.load_governor._poll_last[0] = 0.0; pn = []
mono = lambda: pc.t  # noqa: E731
for _ in range(4):
    LG.kie_poll_acquire(sleep=lambda x: (pn.append(x), pc.sleep(x)), clock=mono)
check("polls paced at 1 per second by default", len(pn) == 3 and all(abs(x - 1.0) < 1e-6 for x in pn), pn)
pn.clear()
LG.kie_poll_acquire(interval_s=0.25, sleep=lambda x: (pn.append(x), pc.sleep(x)), clock=mono)
check("poll interval is configurable", pn and abs(pn[0] - 0.25) < 1e-6, pn)
# dispatch: only submit is a generation request; a persistent 429 is never "submitted"
import kie_dispatch.kie_dispatch as KD  # noqa: E402
check("only submit-style commands are generation", KD.GENERATION_CMDS >= {"submit"} and
      not ({"health", "wait", "save", "preflight", "status", "record-info"} & KD.GENERATION_CMDS))
rc, parsed, _ = KD._call(lambda argv: (_ for _ in ()).throw(LG.KieRateLimitError("KIE_RATE_LIMITED", "job x")),
                         "adapter", ["submit"])
check("exhausted 429 is reported as not submitted", parsed and parsed["state"] == "rate_limited")

# make_runner end to end: a 429 on submit is resubmitted; polls leave the bucket alone
fake = os.path.join(TMP, "fake_adapter.py")
open(fake, "w").write("import sys, os\nc = os.path.join(os.environ['FAKE_DIR'], 'n')\n"
    "n = int(open(c).read()) if os.path.exists(c) else 0\n"
    "if sys.argv[1] == 'submit':\n    open(c, 'w').write(str(n + 1))\n"
    "    print('{\"code\": 429}' if n < 2 else '{\"state\": \"ok\"}')\nelse:\n    print('{\"state\": \"ok\"}')\n")
os.environ["FAKE_DIR"] = tempfile.mkdtemp(dir=TMP)
os.environ["DSAF_GOVERNOR_DIR"] = tempfile.mkdtemp(dir=TMP)
os.environ[LG.load_governor.POLL_ENV] = "0"
LG.load_governor.time.sleep = lambda s: None          # skip the real 2 s / 4 s backoff
run = KD.make_runner(30)
for cmd in ("health", "wait", "save"):
    run([fake, cmd, "--json"])
check("make_runner: polls/health/save leave the generation bucket untouched",
      not os.path.exists(os.path.join(os.environ["DSAF_GOVERNOR_DIR"], "kie-rate")))
rc, out = run([fake, "submit", "--request", "r.json"])
check("make_runner: submit 429 resubmitted until it runs",
      '"ok"' in out and open(os.path.join(os.environ["FAKE_DIR"], "n")).read() == "3")
check("make_runner: 3 submit attempts drew 3 generation tokens", len(json.load(open(os.path.join(
    os.environ["DSAF_GOVERNOR_DIR"], "kie-rate", LG.key_tag(), "stamps.json")))) == 3)

# docs agree with references/kie-rate-limit.md
SK = os.path.join(CORE, "..", "..")
check("constants match KIE docs (20 per 10 s)", (LG.load_governor.KIE_MAX, LG.load_governor.KIE_WINDOW_S) == (20, 10.0))
skill_md = open(os.path.join(SK, "SKILL.md"), encoding="utf-8").read()
check("SKILL.md says generation-only 20 per 10 s, polls separate",
      "NEW generation" in skill_md and "never consume generation tokens" in skill_md)
ref = os.path.join(SK, "references", "kie-rate-limit.md")  # lands via the docs PR
if os.path.exists(ref):
    rt = open(ref, encoding="utf-8").read()
    check("reference doc agrees", "20 new generation requests per 10 seconds" in rt and "not queued" in rt)
check("JSON code 429 inside an (rc, stdout) reply is a rate limit", LG.is_rate_limited((0, '{"code": 429}\\n')))
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

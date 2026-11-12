#!/usr/bin/env python3
"""Runnable checks for the skill75-keepalive cron registrar and its program.

Every check prints its TRUE result and is paired with a negative control where
one is meaningful -- a check that cannot fail is not evidence. The stub below
is a real `openclaw` stand-in on PATH: it records every argv and moves one job
marker file, so "registered once", "never a duplicate" and "silent" are measured
facts, not source-text claims.

Proves:
  A  --dry-run writes nothing anywhere and registers nothing
  B  --apply registers exactly ONE job, named skill75-keepalive, every 10
     minutes, with --no-deliver, an isolated session and a pinned model
  C  a second --apply is a no-op (exactly one registration, ever)
  D  a durable tombstone makes --apply a no-op (never resurrected)
  E  an UNKNOWN `cron list --json` refuses to register (no duplicate risk)
  F  uninstall.sh --apply tombstones first and removes the job; --dry-run
     writes nothing
  G  the prompt ships ONE command (the program at
     scripts/core/heartbeat/keepalive_core.py) and no code block of its own;
     the installer substitutes the runs dir; and that program, run against a
     stand-in skill tree, delivers exactly one first message for a healthy run
     and nothing more 10 minutes later
  H  stall recovery through the shipped program, cases a-d: a run folder with
     a SPACE in it reaches the native control as one argument and the client is
     told the pickup; an unauthorized box calls the control zero times and is
     announced once; three failures raise EXHAUSTED with no fourth call; and
     "picking it back up" is said only where recovery really acted and
     returned 0
  I  the same news is never repeated, driven by a fake clock: 54 ticks over 9
     hours of an unchanged needs_you state send exactly 2 messages; a stage
     change sends at once; an unchanged progress state sends every 30 minutes,
     not every 10; a nudge that falls in quiet hours goes out at 8:00 AM; the
     nudge and reminder wording is the reminder wording; and after the ladder
     KEEPALIVE_CLIENT_SILENT is raised once with no further sends

Run: python3 timer-artifacts/checks/test_keepalive_cron.py
Stdlib only; writes only inside tempfile.mkdtemp(); never touches launchd,
crontab, pm2 or any real scheduling surface.
"""
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                       # timer-artifacts/
INSTALLER = ROOT / "install-keepalive-cron.sh"
UNINSTALL = ROOT / "uninstall.sh"
PROMPT = ROOT / "keepalive-cron-prompt.txt"

FS = []

STUB = r'''#!/bin/sh
LOG="${STUB_LOG:?}"
STATE="${STUB_STATE:?}"
# one line per call: a multi-line --message must not split the record
printf '%s\n' "$(printf '%s' "$*" | tr '\n' ' ')" >> "$LOG"
case "$*" in
  "cron add --help") echo "--name --cron --message --agent --no-deliver --session --model"; exit 0 ;;
  "cron rm --help"|"cron remove --help"|"cron delete --help") echo "usage"; exit 0 ;;
  "cron list --json")
    if [ -n "${STUB_LIST_FAIL:-}" ]; then exit 1; fi
    if [ -f "$STATE/job" ]; then printf '[{"name":"skill75-keepalive"}]\n'
    else printf '[]\n'; fi
    exit 0 ;;
  cron\ add*)  touch "$STATE/job"; exit 0 ;;
  cron\ rm*|cron\ remove*|cron\ delete*) rm -f "$STATE/job"; exit 0 ;;
esac
exit 0
'''


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FS.append(name)


class Box(object):
    """One isolated box: stub binary, its state, and a fake $HOME."""

    def __init__(self, work):
        self.root = Path(work)
        self.bin = self.root / "bin"
        self.bin.mkdir(parents=True)
        self.state = self.root / "state"
        self.state.mkdir()
        self.home = self.root / "home"
        (self.home / ".openclaw").mkdir(parents=True)
        self.log = self.root / "calls.log"
        self.log.write_text("")
        stub = self.bin / "openclaw"
        stub.write_text(STUB)
        stub.chmod(0o755)
        self.env = dict(os.environ, OPENCLAW_BIN=str(stub), STUB_LOG=str(self.log),
                        STUB_STATE=str(self.state), HOME=str(self.home),
                        SKILL75_KEEPALIVE_RUNS_DIR=str(self.root / "runs"))
        for k in ("SKILL75_KEEPALIVE_AGENT", "DS_AGENT_ID", "STUB_LIST_FAIL",
                  "SKILL75_KEEPALIVE_MODEL"):
            self.env.pop(k, None)

    def run(self, script, *args, **extra):
        env = dict(self.env, **extra)
        return subprocess.run(["bash", str(script)] + list(args), env=env,
                              capture_output=True, text=True)

    def calls(self):
        return [ln for ln in self.log.read_text().splitlines() if ln]

    def tree(self):
        return sorted(str(p.relative_to(self.root)) for p in self.root.rglob("*"))


# --- the shipped program, run against a stand-in skill root ------------------
#: the REAL watcher and the REAL keepalive program, copied into the stand-in
#: tree (a symlink would resolve __file__ back into the repository and lose
#: the fake control).
HEARTBEAT = HERE.parent.parent / "scripts" / "core" / "heartbeat"
WATCHER = HEARTBEAT / "run_watch.py"
KEEPALIVE = HEARTBEAT / "keepalive_core.py"

#: the stand-in native control: one JSON argv line per call, then FACTORY_RC.
FACTORY = '''#!/usr/bin/env python3
"""fake native control: records its argv, then exits with FACTORY_RC."""
import json
import os
import sys

log = os.environ.get("FACTORY_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps(sys.argv) + "\\n")
raise SystemExit(int(os.environ.get("FACTORY_RC", "0")))
'''


def write_json(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc), encoding="utf-8")


def make_stage_run(runs_dir, name, stamp, stage="research", state="RUNNING",
                   authorized=False, target="5550001",
                   timezone="America/New_York"):
    """One run folder whose single stage carries this state and stamp."""
    run = Path(runs_dir) / name
    (run / "control").mkdir(parents=True)
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute("CREATE TABLE stages (run_id TEXT, stage TEXT, state TEXT,"
                " owner TEXT, lease_expires REAL, reason TEXT, updated_at REAL)")
    con.execute("CREATE TABLE events (id TEXT, run_id TEXT, stage TEXT,"
                " kind TEXT, detail TEXT, at REAL)")
    con.execute("INSERT INTO stages VALUES (?,?,?,?,?,?,?)",
                (name, stage, state, "worker-1", None, None, int(stamp)))
    con.commit()
    con.close()
    write_json(run / "control" / "origin.json",
               {"kind": "chat", "target": target, "timezone": timezone})
    if authorized:
        write_json(run / "control" / "recovery-authorization.json",
                   {"authorized": True, "scope": ["resume"], "by": "operator",
                    "run_id": name})
    return run


def make_run(runs_dir, name, authorized=True, target="5550001"):
    """A RUNNING stage with 45 minutes of silence: a real stall."""
    return make_stage_run(runs_dir, name, time.time() - 45 * 60,
                          stage="research", state="RUNNING",
                          authorized=authorized, target=target)


def add_event(run, run_id, stage, at, kind="progress"):
    """A durable event row: the only thing that advances the watchdog clock."""
    con = sqlite3.connect(str(Path(run) / "control" / "state.sqlite3"))
    con.execute("INSERT INTO events(id, run_id, stage, kind, detail, at)"
                " VALUES(?,?,?,?,?,?)",
                (hashlib.sha256(("%s|%s|%g|%s" % (run_id, stage, at, kind))
                                .encode()).hexdigest(), run_id, stage, kind,
                 "", float(at)))
    con.commit()
    con.close()


def ny_ts(year, month, day, hour, minute=0):
    """Epoch seconds for a wall-clock time in the client's own time zone."""
    import datetime
    from zoneinfo import ZoneInfo
    return int(datetime.datetime(year, month, day, hour, minute,
                                 tzinfo=ZoneInfo("America/New_York")).timestamp())


def core_box(work):
    """(box, skill, runs): the shipped program in a stand-in skill tree."""
    box = Box(work)
    skill = Path(work) / "skill"
    hb = skill / "scripts" / "core" / "heartbeat"
    hb.mkdir(parents=True)
    (skill / "scripts" / "core" / "intake_preflight").mkdir(parents=True)
    shutil.copy2(str(WATCHER), str(hb / "run_watch.py"))
    shutil.copy2(str(KEEPALIVE), str(hb / "keepalive_core.py"))
    (skill / "scripts" / "core" / "intake_preflight" / "factory.py").write_text(
        FACTORY, encoding="utf-8")
    runs = Path(work) / "runs"
    runs.mkdir()
    return box, skill, runs


def run_core(box, skill, runs, factory_log, extra=None, now=None):
    """One tick of the shipped program against the stand-in tree."""
    env = dict(box.env, FACTORY_LOG=str(factory_log))
    env["PATH"] = str(box.bin) + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    if extra:
        env.update(extra)
    argv = [sys.executable,
            str(skill / "scripts" / "core" / "heartbeat" / "keepalive_core.py"),
            "--runs-dir", str(runs)]
    if now is not None:
        argv += ["--now", str(int(now))]
    return subprocess.run(argv, env=env, capture_output=True, text=True,
                          timeout=300)


def events(runs):
    p = Path(runs) / ".keepalive" / "events.log"
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def factory_calls(path):
    p = Path(path)
    if not p.is_file():
        return []
    return [json.loads(ln) for ln in p.read_text().splitlines() if ln.strip()]


def rewind_gate(runs, rid):
    """Simulate the next tick being more than 30 minutes later."""
    p = Path(runs) / ".keepalive" / "run-registry.json"
    doc = json.loads(p.read_text())
    doc["runs"][rid]["last_recovery_attempt_at"] = 0
    p.write_text(json.dumps(doc), encoding="utf-8")


def sent_messages(box):
    return [c for c in box.calls() if c.startswith("message send")]


def main():
    tmp = tempfile.mkdtemp(prefix="keepalive-cron-")

    # A. dry-run writes nothing and registers nothing -----------------------
    box = Box(os.path.join(tmp, "a"))
    before = box.tree()
    r = box.run(INSTALLER)
    check("A: dry-run exits 0", r.returncode == 0, r.stderr)
    check("A: dry-run calls no cron add",
          not any(c.startswith("cron add --name") for c in box.calls()), box.calls())
    check("A: dry-run writes nothing on the box", box.tree() == before,
          set(box.tree()) ^ set(before))
    check("A: dry-run prints the plan", "cron add" in r.stdout, r.stdout)

    # negative control: --apply DOES move the stub's job marker
    r = box.run(INSTALLER, "--apply")
    check("A-neg (control): --apply does register", (box.state / "job").is_file(),
          r.stderr)

    # B. one job, the right shape -----------------------------------------
    box = Box(os.path.join(tmp, "b"))
    r = box.run(INSTALLER, "--apply")
    adds = [c for c in box.calls() if c.startswith("cron add --name")]
    check("B: --apply exits 0", r.returncode == 0, r.stderr)
    check("B: exactly one registration", len(adds) == 1, adds)
    add = adds[0] if adds else ""
    check("B: named skill75-keepalive", "--name skill75-keepalive" in add, add)
    check("B: every 10 minutes", "--cron */10 * * * *" in add, add)
    check("B: silent (--no-deliver)", "--no-deliver" in add, add)
    check("B: isolated session", "--session isolated" in add, add)
    check("B: cheap/local model pinned", "--model ollama/deepseek-v4.1-flash:cloud" in add, add)
    check("B: no agent guessed on a one-agent box", "--agent" not in add, add)
    check("B: no second cron kind (one job only)",
          len([c for c in box.calls() if c.startswith("cron add --name")]) == 1)

    # an explicit agent and model are honored
    box = Box(os.path.join(tmp, "b2"))
    box.run(INSTALLER, "--apply", "--agent", "video", "--model", "ollama/qwen3:4b")
    add = [c for c in box.calls() if c.startswith("cron add --name")][0]
    check("B2: an explicit agent is passed", "--agent video" in add, add)
    check("B2: an explicit model is passed", "--model ollama/qwen3:4b" in add, add)

    # C. idempotent: a second --apply adds nothing ------------------------
    calls_before = len([c for c in box.calls() if c.startswith("cron add --name")])
    r = box.run(INSTALLER, "--apply")
    check("C: second --apply exits 0", r.returncode == 0, r.stderr)
    check("C: second --apply registers nothing",
          len([c for c in box.calls() if c.startswith("cron add --name")]) == calls_before)
    check("C: it says it was already present", "already present" in r.stdout, r.stdout)

    # D. tombstone wins ----------------------------------------------------
    box = Box(os.path.join(tmp, "d"))
    tdir = box.home / ".openclaw" / "workspace" / ".cron-tombstones"
    tdir.mkdir(parents=True)
    (tdir / "skill75-keepalive").write_text("TOMBSTONED test\n")
    r = box.run(INSTALLER, "--apply")
    check("D: a tombstoned job exits 0", r.returncode == 0, r.stderr)
    check("D: a tombstoned job is never registered",
          not any(c.startswith("cron add --name") for c in box.calls()), box.calls())
    check("D: it says why", "tombstoned" in r.stdout, r.stdout)

    # E. UNKNOWN presence refuses to register (D10) ------------------------
    box = Box(os.path.join(tmp, "e"))
    env = {"STUB_LIST_FAIL": "1"}
    r = box.run(INSTALLER, "--apply", **env)
    check("E: an unreadable list exits 3", r.returncode == 3, r.returncode)
    check("E: an unreadable list never registers (no duplicate)",
          not any(c.startswith("cron add --name") for c in box.calls()), box.calls())
    check("E: it says UNKNOWN", "UNKNOWN" in r.stdout, r.stdout)

    # F. uninstall ---------------------------------------------------------
    box = Box(os.path.join(tmp, "f"))
    box.run(INSTALLER, "--apply")
    check("F: (setup) job registered", (box.state / "job").is_file())
    before = box.tree()
    r = box.run(UNINSTALL)
    check("F: uninstall --dry-run exits 0", r.returncode == 0, r.stderr)
    check("F: uninstall --dry-run writes nothing", box.tree() == before,
          set(box.tree()) ^ set(before))
    r = box.run(UNINSTALL, "--apply")
    check("F: uninstall --apply exits 0", r.returncode == 0, r.stderr)
    check("F: the job is gone", not (box.state / "job").is_file())
    marker = box.home / ".openclaw" / "workspace" / ".cron-tombstones" / "skill75-keepalive"
    check("F: a durable tombstone is written", marker.is_file())
    check("F: the tombstone names the job", "name: skill75-keepalive" in marker.read_text())
    r = box.run(INSTALLER, "--apply")
    check("F: a re-install after uninstall does not resurrect it",
          not (box.state / "job").is_file() and "tombstoned" in r.stdout, r.stdout)

    # G. the prompt is one command, and that command runs ------------------
    box = Box(os.path.join(tmp, "g"))
    r = box.run(INSTALLER)
    rendered = r.stdout
    prompt = PROMPT.read_text(encoding="utf-8")
    check("G: the prompt runs the shipped keepalive program",
          "python3 -B" in prompt
          and "scripts/core/heartbeat/keepalive_core.py" in prompt,
          prompt[-400:])
    check("G: the prompt carries no code block of its own",
          "PY_KEEPALIVE_CORE" not in prompt)
    check("G: the prompt uses the client's own Telegram sender",
          "openclaw message send --channel telegram" in prompt)
    check("G: the prompt forbids inventing a target", "do NOT guess one" in prompt)
    check("G: the prompt keeps the run folder off-limits to the agent, and spend",
          "Do not write to the run folder yourself" in prompt
          and "Never spend" in prompt)
    check("G: the runs dir is substituted, not left as a placeholder",
          "__RUNS_DIR__" not in rendered and str(box.root / "runs") in rendered,
          "runs dir missing from the rendered command")
    check("G: internal codes are facts to act on, never sent to the client",
          "HEARTBEAT_EXPIRED" in prompt and "internal codes to the client" in prompt)
    check("G: the prompt forbids printing a secret", "Never print a key" in prompt)

    # G (run). a healthy run gets exactly one first message ---------------
    box, skill, runs = core_box(os.path.join(tmp, "g1"))
    base = int(time.time())
    run = make_stage_run(runs, "run-g", base - 60, stage="music",
                         state="RUNNING")
    flog = Path(box.root) / "factory.log"
    r = run_core(box, skill, runs, flog, now=base)
    check("G (run): a healthy tick exits 0", r.returncode == 0, r.stderr)
    check("G (run): the first progress message is delivered exactly once",
          len(sent_messages(box)) == 1, box.calls())
    check("G (run): the message is the plain-English stage phrase",
          bool(sent_messages(box))
          and "your ad's music is being created" in sent_messages(box)[0],
          sent_messages(box))
    add_event(run, "run-g", "music", base + 600, kind="worker-heartbeat")
    run_core(box, skill, runs, flog, now=base + 600)
    check("G (run): an unchanged state 10 minutes later sends nothing again",
          len(sent_messages(box)) == 1, box.calls())

    # H (a). a stall in a run folder whose path has a SPACE, authorized ------
    box, skill, runs = core_box(os.path.join(tmp, "h"))
    run = make_run(runs, "run with space", authorized=True)
    flog = Path(box.root) / "factory.log"
    r = run_core(box, skill, runs, flog)
    calls = factory_calls(flog)
    check("H (a): the program exits 0", r.returncode == 0, r.stderr)
    check("H (a): recovery runs the control exactly once", len(calls) == 1, calls)
    argv = calls[0] if calls else []
    check("H (a): the run folder reaches the control as ONE argument",
          "--run-dir" in argv and argv[argv.index("--run-dir") + 1] == str(run)
          and " " in str(run), argv)
    codes_a = [e["code"] for e in events(runs)]
    check("H (a): an acted, successful recovery raises no failure",
          not [c for c in codes_a if c.startswith("KEEPALIVE_RECOVERY")], codes_a)
    msg_a = " ".join(sent_messages(box))
    check("H (a): the client is told it is picked back up",
          "picking it back up" in msg_a, msg_a)

    # H (b). no written authorization: zero control calls, one notice -------
    box, skill, runs = core_box(os.path.join(tmp, "i"))
    run = make_run(runs, "run-i", authorized=False)
    flog = Path(box.root) / "factory.log"
    r = run_core(box, skill, runs, flog)
    check("H (b): the program exits 0", r.returncode == 0, r.stderr)
    check("H (b): an unauthorized run calls the control zero times",
          factory_calls(flog) == [], factory_calls(flog))
    codes_b = [e["code"] for e in events(runs)]
    check("H (b): exactly one NOT_AUTHORIZED notice",
          codes_b.count("KEEPALIVE_RECOVERY_NOT_AUTHORIZED") == 1, codes_b)
    rewind_gate(runs, "run-i")
    run_core(box, skill, runs, flog)
    check("H (b): a later tick does not repeat the notice",
          [e["code"] for e in events(runs)].count(
              "KEEPALIVE_RECOVERY_NOT_AUTHORIZED") == 1,
          [e["code"] for e in events(runs)])
    check("H (b): still zero control calls", factory_calls(flog) == [],
          factory_calls(flog))
    msg_b = " ".join(sent_messages(box))
    check("H (b): the client is told a person is looking",
          "flagged it for a person" in msg_b and "picking it back up" not in msg_b,
          msg_b)

    # H (c). three failing attempts -> EXHAUSTED, and no fourth call --------
    box, skill, runs = core_box(os.path.join(tmp, "j"))
    run = make_run(runs, "run-j", authorized=True)
    flog = Path(box.root) / "factory.log"
    fail = {"FACTORY_RC": "1"}
    for _ in range(2):
        run_core(box, skill, runs, flog, extra=fail)
        rewind_gate(runs, "run-j")
    run_core(box, skill, runs, flog, extra=fail)          # the third attempt
    codes_c = [e["code"] for e in events(runs)]
    check("H (c): three attempts made three calls", len(factory_calls(flog)) == 3,
          factory_calls(flog))
    check("H (c): every failure is named, with its return code",
          codes_c.count("KEEPALIVE_RECOVERY_FAILED") == 3, codes_c)
    check("H (c): the third failure raises EXHAUSTED once",
          codes_c.count("KEEPALIVE_RECOVERY_EXHAUSTED") == 1, codes_c)
    rewind_gate(runs, "run-j")
    run_core(box, skill, runs, flog, extra=fail)
    check("H (c): no fourth call after it is exhausted",
          len(factory_calls(flog)) == 3, factory_calls(flog))
    msg_c = " ".join(sent_messages(box))

    # H (d). the pickup sentence belongs to a recovery that acted and won ---
    check("H (d): 'picking it back up' only where recovery acted and returned 0",
          "picking it back up" in msg_a
          and "picking it back up" not in msg_b
          and "picking it back up" not in msg_c,
          "a=%r b=%r c=%r" % (msg_a, msg_b, msg_c))

    # I (a). 54 ticks over 9 hours of an unchanged needs_you state ----------
    box, skill, runs = core_box(os.path.join(tmp, "k1"))
    base = ny_ts(2026, 6, 10, 9, 0)          # 9:00 AM, the client's own zone
    make_stage_run(runs, "run-needs", base - 60, stage="storyboard",
                   state="WAITING_APPROVAL")
    flog = Path(box.root) / "factory.log"
    for n in range(54):                       # nine hours, a tick every 10 min
        run_core(box, skill, runs, flog, now=base + n * 600)
    sent = sent_messages(box)
    check("I (a): 54 ticks over 9 hours of an unchanged needs_you state send "
          "exactly 2 messages", len(sent) == 2, sent)
    check("I (a): the second one is the nudge, in reminder wording",
          len(sent) == 2 and "Just a reminder" in sent[1], sent)
    check("I (a): the reminder says nothing is being charged",
          len(sent) == 2 and "Nothing is being charged while it waits" in sent[1],
          sent)

    # I (b). a stage change sends at once ----------------------------------
    box, skill, runs = core_box(os.path.join(tmp, "k2"))
    base = ny_ts(2026, 6, 10, 9, 0)
    run = make_stage_run(runs, "run-change", base - 60, stage="storyboard",
                         state="WAITING_APPROVAL")
    flog = Path(box.root) / "factory.log"
    run_core(box, skill, runs, flog, now=base)
    check("I (b): the first needs_you message goes out",
          len(sent_messages(box)) == 1, box.calls())
    con = sqlite3.connect(str(run / "control" / "state.sqlite3"))
    con.execute("UPDATE stages SET stage='music', updated_at=? WHERE run_id=?",
                (int(base + 540), "run-change"))
    con.commit()
    con.close()
    run_core(box, skill, runs, flog, now=base + 600)
    check("I (b): a stage change sends at once, ten minutes after the first",
          len(sent_messages(box)) == 2, box.calls())

    # I (c). an unchanged progress state sends every 30 minutes, not every 10
    box, skill, runs = core_box(os.path.join(tmp, "k3"))
    base = ny_ts(2026, 6, 10, 9, 0)
    run = make_stage_run(runs, "run-progress", base - 60, stage="music",
                         state="RUNNING")
    flog = Path(box.root) / "factory.log"
    counts = []
    for n in (0, 1, 2, 3):
        at = base + n * 600
        add_event(run, "run-progress", "music", at, kind="worker-heartbeat")
        run_core(box, skill, runs, flog, now=at)
        counts.append(len(sent_messages(box)))
    check("I (c): an unchanged progress state sends once at 0 and not at 10 or "
          "20 minutes", counts[0] == 1 and counts[1] == 1 and counts[2] == 1,
          counts)
    check("I (c): and again at 30 minutes, not every 10", counts[3] == 2, counts)

    # I (d). quiet hours hold the nudge until 8:00 AM ----------------------
    box, skill, runs = core_box(os.path.join(tmp, "k4"))
    base = ny_ts(2026, 6, 10, 20, 50)        # 8:50 PM, the client's own zone
    make_stage_run(runs, "run-quiet", base - 60, stage="storyboard",
                   state="WAITING_APPROVAL")
    flog = Path(box.root) / "factory.log"
    run_core(box, skill, runs, flog, now=base)
    check("I (d): a first-time needs_you message goes out at once, even at night",
          len(sent_messages(box)) == 1, box.calls())
    run_core(box, skill, runs, flog, now=base + 2 * 60 * 60)   # 10:50 PM
    check("I (d): the nudge that falls at 10:50 PM is held",
          len(sent_messages(box)) == 1, box.calls())
    run_core(box, skill, runs, flog, now=ny_ts(2026, 6, 11, 8, 0))
    check("I (d): it goes out at 8:00 AM instead",
          len(sent_messages(box)) == 2, box.calls())

    # I (e). after the ladder: one silent notice, then nothing -------------
    box, skill, runs = core_box(os.path.join(tmp, "k5"))
    base = ny_ts(2026, 6, 10, 9, 0)
    make_stage_run(runs, "run-ladder", base - 60, stage="storyboard",
                   state="WAITING_APPROVAL")
    flog = Path(box.root) / "factory.log"
    for at in (base, base + 2 * 60 * 60, base + 24 * 60 * 60):
        run_core(box, skill, runs, flog, now=at)
    check("I (e): the first message, the nudge and the reminder are three sends",
          len(sent_messages(box)) == 3, box.calls())
    run_core(box, skill, runs, flog, now=base + 24 * 60 * 60 + 600)
    codes_e = [e["code"] for e in events(runs)]
    check("I (e): after the ladder, KEEPALIVE_CLIENT_SILENT is raised once",
          codes_e.count("KEEPALIVE_CLIENT_SILENT") == 1, codes_e)
    run_core(box, skill, runs, flog, now=base + 24 * 60 * 60 + 1200)
    codes_e = [e["code"] for e in events(runs)]
    check("I (e): a later tick repeats nothing and sends nothing more",
          codes_e.count("KEEPALIVE_CLIENT_SILENT") == 1
          and len(sent_messages(box)) == 3, (codes_e, sent_messages(box)))

    print()
    if FS:
        print("%d FAILED: %s" % (len(FS), ", ".join(FS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

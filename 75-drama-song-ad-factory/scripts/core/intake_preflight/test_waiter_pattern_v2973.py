#!/usr/bin/env python3
"""S75-012: there is ONE waiter, and it waits on facts, not process names.

Live proof: two shells spun ~8 h on `while pgrep -f "run_vtv_music.py"` —
`pgrep -f` matched the waiter's own argv and the loop met itself. The shell
waiter (and its pattern rulebook) is gone; the runbook now names the one
Python waiter, and this test proves the runbook says so and that the waiter's
own self-check passes:

  1. the runbook no longer documents a shell waiter (no `pgrep -f`, no
     `until [ -s ... ]`, no sqlite3 polling loop);
  2. it forbids a shell loop and a process-name match;
  3. it names `scripts/core/intake_preflight/wait_for_stage.py` with
     `--run-dir` and `--stage` and states all four exit codes;
  4. `wait_for_stage.py --selftest` exits 0.

Run: python3 scripts/core/intake_preflight/test_waiter_pattern_v2973.py
stdlib only, no network, no spend, no provider.
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parents[2]                       # 75-drama-song-ad-factory/
RUNBOOK = SKILL / "references" / "stage-runbook.md"
WAITER = HERE / "wait_for_stage.py"

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main():
    text = RUNBOOK.read_text(encoding="utf-8")

    check("runbook documents no pgrep waiter", "pgrep -f" not in text)
    check("runbook documents no artifact shell loop",
          'until [ -s "$RUN/music/picked-song.mp3"' not in text)
    check("runbook documents no sqlite3 shell polling loop",
          "sqlite3 \"$RUN/control/state.sqlite3\"" not in text)
    check("runbook forbids a shell loop and a process-name match",
          "Never write a shell loop, never match a process name" in text)
    check("runbook names the one waiter",
          "scripts/core/intake_preflight/wait_for_stage.py" in text)
    check("runbook shows --run-dir and --stage",
          '--run-dir "$RUN" --stage' in text)
    for code, meaning in (("Exit 0 = finished", "0"),
                          ("Exit 2 = still not finished", "2"),
                          ("Exit 4 = the stage is blocked", "4"),
                          ("Exit 1 = the", "1")):
        check("runbook states exit %s" % meaning, code in text)

    probe = subprocess.run([sys.executable, "-B", str(WAITER), "--selftest"],
                           capture_output=True, text=True, timeout=120)
    check("wait_for_stage.py --selftest exits 0", probe.returncode == 0,
          (probe.stdout + probe.stderr)[-400:])

    print()
    if FAILS:
        print("FAILED: %d: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_waiter_pattern_v2973: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

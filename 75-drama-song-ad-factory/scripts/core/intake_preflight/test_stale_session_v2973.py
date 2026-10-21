#!/usr/bin/env python3
"""L4.2 (v2.9.73): the stale-session guard.

Live proof: sessions ran 17-20 h on code older than the installed skill;
three merged fixes could not reach them.

Proves, behaviourally (stdlib only, $0, no provider):
  1. a process that booted on an older version than the installed skill
     REFUSES `next`: outcome error, reason SKILL_UPDATED, exit code 1, and
     BOTH versions are named (installed_version, boot_version). The installed
     version is read from skill-version.txt, so a bump never breaks this test;
  2. the refusal names the stage command in no part (no stage, no command in
     data) — no stage command is ever handed out by stale code;
  3. the CLI carries it end to end (the real factory.py subprocess);
  4. a process whose boot version EQUALS the installed one is never stale;
  5. a boot version NEWER than the installed one (a box on an older install
    after a rollback) is never stale — only NEWER installed refuses;
  6. a version this process could not read at boot (None/empty) is never
     stale (a bare install must not brick itself);
  7. an UNREADABLE disk version is never stale (nothing to compare);
  8. non-numeric versions never refuse (no crash on a drifted file).

Run: python3 scripts/core/intake_preflight/test_stale_session_v2973.py
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = Path(HERE).parent
SKILL = Path(HERE).parents[2]

sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F            # noqa: E402


def _bump(version, by):
    """v2.9.74 -> v2.9.75; a version without a trailing number -> v<by>."""
    i = len(version or "")
    while i and version[i - 1].isdigit():
        i -= 1
    digits = (version or "")[i:]
    if not digits:
        return "v%d" % by
    return "%s%d" % (version[:i], int(digits) + by)


# Read the installed version from the skill root, never hard-code it: bumping
# skill-version.txt must not be able to break this test again (G3 class).
INSTALLED = F._skill_version_on_disk() or ""
OLDER = _bump(INSTALLED, -2)        # a boot two releases behind
NEWER = _bump(INSTALLED, 1)         # a box still on a newer install

FAILS = []


def check(name, cond, detail=""):
    print("%s %s%s" % ("ok" if cond else "FAIL", name,
                       (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def make_run(tmp):
    """A real run dir with an initialized store (all stages NOT_STARTED)."""
    import state_store as SS
    from batch_mode.batch import STAGES  # noqa: F401
    run = Path(tempfile.mkdtemp(prefix="stale-", dir=tmp))
    (run / "control").mkdir(parents=True)
    with SS.Store(run / "control" / "state.sqlite3") as st:
        st.init_run("run-stale", [s for s, _ in STAGES])
    return run


class A:
    run_dir = ""
    orchestrated = False


def main():
    tmp = Path(tempfile.mkdtemp(prefix="stale-guard-"))
    run = make_run(tmp)
    A.run_dir = str(run)

    # the version under test must really come from skill-version.txt
    check("installed version read from skill-version.txt",
          bool(INSTALLED), repr(INSTALLED))

    # 1. boot older than installed -> refuse, both named
    F._BOOT_SKILL_VERSION = OLDER
    env = F.cmd_next(A())
    check("older boot refuses: error SKILL_UPDATED",
          env["outcome"] == "error" and env["reason_code"] == "SKILL_UPDATED",
          str(env)[:220])
    check("both versions named",
          env["data"]["installed_version"] == INSTALLED
          and env["data"]["boot_version"] == OLDER,
          str(env.get("data")))
    check("the refusal text names both versions too",
          INSTALLED in (env.get("next_action") or "")
          and OLDER in (env.get("next_action") or ""),
          env.get("next_action", "")[:160])

    # 2. no stage command in the refusal envelope
    d = env.get("data") or {}
    check("no stage / command in the refusal",
          "stage" not in d and "command" not in d, str(sorted(d)))

    # 3. the real CLI carries it end to end (exit 1), via the documented
    #    boot-version override a launcher (or a restarted process) records
    p = subprocess.run(
        [sys.executable, str(Path(HERE) / "factory.py"), "next",
         "--run-dir", str(run)],
        capture_output=True, text=True, timeout=60,
        env=dict(os.environ, DSAF_BOOT_SKILL_VERSION=OLDER))
    env_cli = json.loads(p.stdout)
    check("CLI end to end: error SKILL_UPDATED, exit 1",
          env_cli["reason_code"] == "SKILL_UPDATED" and p.returncode == 1,
          "%s rc=%d" % (env_cli.get("reason_code"), p.returncode))
    env_cli_both = env_cli["data"]
    check("CLI refusal names installed %s and boot %s"
          % (env_cli_both.get("installed_version"),
             env_cli_both.get("boot_version")),
          env_cli_both.get("installed_version") == INSTALLED
          and env_cli_both.get("boot_version") == OLDER,
          str(env_cli_both))
    F._BOOT_SKILL_VERSION = INSTALLED       # restore equal boot

    # 4. equal version: never stale
    F._BOOT_SKILL_VERSION = INSTALLED
    env4 = F.cmd_next(A())
    check("equal boot version proceeds normally",
          env4["reason_code"] not in ("SKILL_UPDATED",), str(env4)[:120])

    # 5. boot NEWER than installed (boxed rollback): never stale
    F._BOOT_SKILL_VERSION = NEWER
    env5 = F.cmd_next(A())
    check("a boot newer than the installed never refuses",
          env5["reason_code"] != "SKILL_UPDATED", str(env5)[:120])

    # 6/7. unreadable versions never refuse
    F._BOOT_SKILL_VERSION = ""
    env6 = F.cmd_next(A())
    check("no boot version: never stale", env6["outcome"] == "ok",
          str(env6)[:120])
    F._BOOT_SKILL_VERSION = INSTALLED
    orig = F._skill_version_on_disk
    F._skill_version_on_disk = lambda: ""
    try:
        env7 = F.cmd_next(A())
        check("unreadable disk version: never stale",
              env7["outcome"] == "ok", str(env7)[:120])
    finally:
        F._skill_version_on_disk = orig

    # 8. non-numeric junk never refuses
    F._BOOT_SKILL_VERSION = "not-a-version"
    orig2 = F._skill_version_on_disk
    F._skill_version_on_disk = lambda: "unparseable"
    try:
        env8 = F.cmd_next(A())
        check("non-numeric versions: never stale, no crash",
              env8["outcome"] == "ok", str(env8)[:120])
    finally:
        F._skill_version_on_disk = orig2
        F._BOOT_SKILL_VERSION = INSTALLED

    print()
    if FAILS:
        print("FAILED: %d: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("test_stale_session_v2973: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
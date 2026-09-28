#!/usr/bin/env python3
# tests/unit/rr-escalation-wiring.test.py
#
# Wiring gates for the Rescue Rangers escalation fix (the sender itself is
# proven by rr-escalate.test.py, the AGENTS.md stamper by
# rescue-escalation-v4-stamp.test.py):
#   D  install.sh ships rr-escalate.sh + the stamper and RUNS the stamper on
#      the workspace AGENTS.md; the dept changelog no longer claims a wiring
#      that did not exist.
#   E  the eight maintenance senders go through rr-escalate.sh (which always
#      sends boxName and fails on refusal) instead of a box-less curl whose
#      answer was never read; the watchdog Telegram leg uses the operator
#      account, and only when that account has a token.
#   G  Skill 65 tells senders where the send path is.
#   H  the dead relay address is gone from every shipped file.
# Hermetic: file reads only. Run: python3 tests/unit/rr-escalation-wiring.test.py
import os
import re
import subprocess
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PASS = FAIL = 0


def check(cond, name, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print("  ok " + name)
    else:
        FAIL += 1
        print("  FAIL " + name + (("\n       " + str(detail)[:500]) if detail else ""))


def read(rel):
    with open(os.path.join(REPO, rel), encoding="utf-8", errors="replace") as fh:
        return fh.read()


print("== D: install.sh ships the sender and stamps the workspace AGENTS.md ==")
inst = read("install.sh")
check(re.search(r"for SCRIPT in [^\n]*rr-escalate\.sh", inst) is not None,
      "install.sh copies rr-escalate.sh into ~/.openclaw/scripts")
check(re.search(r'python3 "\$_RR_STAMP_PY" --agents "\$OC_WORKSPACE/AGENTS\.md"', inst) is not None,
      "install.sh runs stamp-rescue-escalation.py against the workspace AGENTS.md")
dept_log = read("23-ai-workforce-blueprint/templates/role-library/rescue-rangers/CHANGELOG-RESCUE-DEPT.md")
check("wired into install.sh (client role) for fresh boxes." not in dept_log,
      "CHANGELOG-RESCUE-DEPT no longer lists install stamping as an open item")

print("== E: the eight senders use rr-escalate.sh, never a box-less curl ==")
SENDERS = [
    "06-ghl-install-pages/tools/browser_manager.sh",
    "23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh",
    "scripts/agent-browser-reaper.sh",
    "scripts/bootstrap-validate-daily.sh",
    "scripts/check-company-root.sh",
    "scripts/disk-usage-alert.sh",
    "scripts/index-model-drift-check.sh",
    "scripts/pre-july14-embedding-migration-check.sh",
]
for rel in SENDERS:
    src = read(rel)
    calls = re.findall(r'bash "[^\n]*"[^\n]* --agent [^\n]*(?:\n[^\n]*)?--problem', src) if "rr-escalate.sh" in src else []
    raw_post = re.search(r'curl[^\n]*\n?[^\n]*RESCUE_RANGERS_WEBHOOK_URL', src)
    boxless = re.search(r'\\"client\\":|"client": os\.environ', src)
    check(calls and not raw_post and not boxless,
          "%s escalates through rr-escalate.sh (box field + refusal detection)" % rel,
          "calls=%d raw_post=%s boxless=%s" % (len(calls), bool(raw_post), bool(boxless)))
    check("REJECTED" in src, "%s logs a rejection instead of claiming success" % rel)

wd = read("23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh")
send = re.search(r"openclaw message send \\\n(?:\s+[^\n]*\\\n)*", wd)
check(send is not None and "--account operator" in send.group(0),
      "watchdog Telegram send uses --account operator", send.group(0) if send else "no send found")
check("_operator_tg_account_ready" in wd and "botToken" in wd,
      "watchdog skips the Telegram leg when the operator account has no token")

print("== G: Skill 65 points senders at rr-escalate.sh ==")
skill = read("65-rescue-receiver/SKILL.md")
check("rr-escalate.sh" in skill and "only RECEIVES" in skill,
      "65-rescue-receiver/SKILL.md: sending uses rr-escalate.sh, this skill only receives")

print("== H: the dead relay address is gone ==")
DEAD = "webhook/" + "rescue-rangers"          # built, so this file never carries it
ALLOWED = {
    "CHANGELOG.md",                               # release history, not a live address
    "tests/unit/rescue-contract-rr017.test.py",   # forbidden-pattern checks only
}
files = subprocess.run(["git", "-C", REPO, "ls-files"], capture_output=True, text=True).stdout.split("\n")
hits = []
for rel in files:
    if not rel or rel in ALLOWED:
        continue
    p = os.path.join(REPO, rel)
    try:
        with open(p, encoding="utf-8", errors="ignore") as fh:
            if DEAD in fh.read():
                hits.append(rel)
    except (OSError, IsADirectoryError):
        continue
check(files and not hits, "no tracked file carries the dead relay address", hits[:10])

print("\nRESULT: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)

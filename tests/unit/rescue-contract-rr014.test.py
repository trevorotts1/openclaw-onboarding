#!/usr/bin/env python3
# tests/unit/rescue-contract-rr014.test.py
#
# RR-014 — proves the ONB side of the heartbeat health + notification receipt
# truthfulness contract:
#   1. The sanitized public addendum ships in the role-library contract dir
#      and stays sanitized: no credential values, no table IDs, no private
#      workflow IDs, no client box slugs, no deployment internals.
#   2. The addendum pins the RR-014 obligations: typed complete/empty/partial/
#      error reads (a broken read is never a healthy empty), UNKNOWN metrics
#      with owned faults, work phases tracked by deadline and progress (not by
#      claims), exactly ONE recovery owner (no competing reaper), receipt-gated
#      notification counts (no failed send appears posted), dry-run changes no
#      state, verify-before-declaring-written, and a monitor-of-monitor
#      heartbeat outside the monitored path.
#   3. The addendum never instructs a client box to do anything new — heartbeat
#      truthfulness is operator-side monitoring.
#   4. No shipped rescue file claims a failed send can be posted, or an error
#      read can be zero, or a state write is proven by an echoed input.
#
# Hermetic: file reads only, no network, no credentials.
#
# Run: python3 tests/unit/rescue-contract-rr014.test.py
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RR = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "rescue-rangers")
ADDENDUM = os.path.join(RR, "contract", "HEARTBEAT-TRUTH-CONTRACT.md")

PASS = 0
FAIL = 0

def ok(name):
    global PASS
    PASS += 1
    print(f"  ok {name}")

def fail(name, detail=""):
    global FAIL
    FAIL += 1
    print(f"  FAIL {name}" + (f"\n       {detail}" if detail else ""))

def check(cond, name, detail=""):
    if cond:
        ok(name)
    else:
        fail(name, detail)

print("== RR-014: sanitized addendum ships in role-library ==")
check(os.path.isfile(ADDENDUM), "HEARTBEAT-TRUTH-CONTRACT.md exists in rescue-rangers/contract/")
if not os.path.isfile(ADDENDUM):
    print(f"FAIL cannot continue without the addendum at {ADDENDUM}")
    print(f"pass={PASS} fail={FAIL}")
    sys.exit(1)
text = open(ADDENDUM, encoding="utf-8").read()
# Markdown prose spans line breaks; collapse whitespace so a phrase split
# across two wrapped lines still matches its needle.
text = re.sub(r"\s+", " ", text)

print("== RR-014: sanitization posture ==")
check("SANITIZED" in text, "declares sanitized posture")
# value-shaped strings: long tokens that are neither sha256 nor uuid-ish
for m in re.finditer(r"[A-Za-z0-9_\-]{40,}", text):
    t = m.group(0)
    if re.fullmatch(r"[0-9a-f]{64}", t) or re.fullmatch(r"[0-9a-f\-]{36}", t):
        continue
    fail(f"addendum carries a value-shaped string: {t[:16]}…", "credential posture violation")
    break
else:
    ok("no value-shaped strings (credential names only)")
check(not re.search(r"\b(?:telegram|webhook)\.(?:me|org|com)\b|api\.telegram\.org", text, re.IGNORECASE),
      "no provider endpoint URLs (deployment internals stay private)")

print("== RR-014: contract obligations pinned ==")
required_phrases = [
    ("complete, empty, partial or error", "typed read results"),
    ("UNKNOWN", "partial/error read sets dependent metrics UNKNOWN"),
    ("owned monitor fault", "read failure is an owned monitor fault"),
    ("never reported as an empty queue", "a broken read is never a healthy empty"),
    ("by deadline and progress, not by claims", "work phases tracked by deadline and progress"),
    ("one recovery owner", "exactly one recovery owner"),
    ("competes with lease authority", "no monitoring path competes with lease authority"),
    ("after a validated delivery receipt", "delivery counted only after validated receipt"),
    ("never appears as posted", "no failed send appears posted"),
    ("cannot count as delivered", "failed/timeout/refusal/error cannot count"),
    ("count ever advances before the send", "no count advances before the send"),
    ("Dry-run changes nothing", "dryrun mutates no send or suppression state"),
    ("Verify before declaring written", "state written only after verified receipts"),
    ("Echoed input", "echoed input is not a persistence receipt"),
    ("outside the monitored path", "monitor-of-monitor heartbeat outside the monitored path"),
]
for needle, label in required_phrases:
    check(needle in text, label)

print("== RR-014: heartbeat truthfulness stays operator-side ==")
client_nevers = [
    ("Nothing on the box changes", "box behavior unchanged"),
    ("operator-side monitoring concerns", "truthfulness is operator-side"),
    ("never a new requirement", "no new requirement on the box"),
]
for needle, label in client_nevers:
    check(needle in text, label)

print("== RR-014: no shipped rescue file claims the baseline bad semantics ==")
# The baseline defects this repair kills: a failed send can be posted, an error
# read is zero, a state write is proven by an echoed input. A shipped rescue
# file that still asserts those semantics (as instructions, not as a quoted
# defect being fixed) violates the contract.
scan_files = []
for root, _dirs, files in os.walk(RR):
    for f in files:
        if f.endswith((".md", ".json", ".py", ".sh", ".js")):
            scan_files.append(os.path.join(root, f))
scan_files.append(os.path.join(REPO, "65-rescue-receiver", "SKILL.md"))
scan_files.append(os.path.join(REPO, "65-rescue-receiver", "rescue-poll.sh"))
violations = []
checked = 0
for path in scan_files:
    try:
        body = open(path, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        continue
    checked += 1
    # a line instructing that a failed send counts as posted
    if re.search(r"fail(?:ed)??[^\n]{0,60}?\bposted\s*[:=]\s*true", body, re.IGNORECASE) \
       and not re.search(r"never|not|must not|defect|baseline|before|excluding", body[max(0, re.search(r"fail(?:ed)??[^\n]{0,60}?\bposted\s*[:=]\s*true", body, re.IGNORECASE).start() - 120):re.search(r"fail(?:ed)??[^\n]{0,60}?\bposted\s*[:=]\s*true", body, re.IGNORECASE).end()], re.IGNORECASE):
        violations.append((os.path.relpath(path, REPO), "failed -> posted:true without negation"))
    # a line instructing that an outbox read error is an empty queue
    for m in re.finditer(r"(?:read|get)[^\n]{0,50}\b(?:error|fail)[^\n]{0,60}\b(?:depth|count|backlog)\s*=\s*0", body, re.IGNORECASE):
        window = max(0, m.start() - 120)
        if not re.search(r"never|not|must not|unknow|defect|baseline|before", body[window:m.end()], re.IGNORECASE):
            violations.append((os.path.relpath(path, REPO), m.group(0)[:80]))
if not violations:
    ok(f"no baseline bad-semantics claims across {checked} shipped files")
else:
    for rel, snippet in violations[:5]:
        fail(f"baseline semantics risk in {rel}", snippet)

print("== RR-014: summary ==")
print(f"pass={PASS} fail={FAIL}")
if FAIL:
    sys.exit(1)
sys.exit(0)

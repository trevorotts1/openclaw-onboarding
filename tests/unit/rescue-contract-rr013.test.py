#!/usr/bin/env python3
# tests/unit/rescue-contract-rr013.test.py
#
# RR-013 — proves the ONB side of the provider capacity and model selection
# contract:
#   1. The sanitized public addendum ships in the role-library contract dir
#      and stays sanitized: no credential values, no table IDs, no private
#      workflow IDs, no client box slugs.
#   2. The addendum pins the RR-013 obligations: persisted selection (model
#      change without code edits), operator asked when preference is missing,
#      verified-capacity-only enforcement (no unlimited inference from a
#      provider name), atomic leased reservations, failed reservation does not
#      dispatch, Retry-After honored with durable requeue (never dropped), and
#      permitted-only fallback with owned escalation when the chain exhausts.
#   3. The addendum never instructs a client box to hold a reservation, call a
#      provider, or treat a capacity wait as a failure — capacity is
#      operator-side.
#   4. No shipped rescue script/doc encodes a plan limit as a universal
#      verified provider fact (the "do not encode user-mentioned plan limits"
#      clause) — concurrency figures may appear only as measured, sourced,
#      account-scoped statements in the private repo, not as fleet-wide facts.
#
# Hermetic: file reads only, no network, no credentials.
#
# Run: python3 tests/unit/rescue-contract-rr013.test.py
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
RR = os.path.join(REPO, "23-ai-workforce-blueprint", "templates", "role-library", "rescue-rangers")
ADDENDUM = os.path.join(RR, "contract", "PROVIDER-CAPACITY-CONTRACT.md")

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

print("== RR-013: sanitized addendum ships in role-library ==")
check(os.path.isfile(ADDENDUM), "PROVIDER-CAPACITY-CONTRACT.md exists in rescue-rangers/contract/")
if not os.path.isfile(ADDENDUM):
    print(f"FAIL cannot continue without the addendum at {ADDENDUM}")
    print(f"pass={PASS} fail={FAIL}")
    sys.exit(1)
text = open(ADDENDUM, encoding="utf-8").read()

print("== RR-013: sanitization posture ==")
check("no credential values" in text.lower() or "SANITIZED" in text, "declares sanitized posture")
# value-shaped strings: long tokens that are neither sha256 nor uuid-ish
for m in re.finditer(r"[A-Za-z0-9_\-]{40,}", text):
    t = m.group(0)
    if re.fullmatch(r"[0-9a-f]{64}", t) or re.fullmatch(r"[0-9a-f\-]{36}", t):
        continue
    fail(f"addendum carries a value-shaped string: {t[:16]}…", "credential posture violation")
    break
else:
    ok("no value-shaped strings (credential names only)")
check(not re.search(r"\bX-Rescue-Secret:\s*\S", text), "no literal secret header value")
check("apihub" not in text and "api.deepseek.com" not in text and "ollama.com" not in text,
      "no provider endpoint URLs (deployment internals stay private)")

print("== RR-013: contract obligations pinned ==")
required_phrases = [
    # persisted selection, no code edit
    ("persisted, not hardcoded", "selection is persisted, not hardcoded"),
    ("no code edit", "model change takes effect without editing code"),
    # operator asked when missing
    ("asks the operator", "missing preference asks the operator; nothing silently chosen"),
    # verified capacity only / no unlimited inference
    ("only when it is verified", "limits enforced only when verified"),
    ("desired budget until verified", "plan description is desired budget, not fact"),
    ("unlimited", "nothing infers unlimited from a provider name"),
    # atomic leased reservations
    ("reserve seats atomically", "reservations are atomic per account"),
    ("lease", "reservations are leased with a deadline"),
    ("released when the call ends", "finally-release on end/fail/cancel"),
    # failed reservation does not dispatch; requeue not drop
    ("does not dispatch", "a failed reservation does not dispatch"),
    ("never dropped", "deferred work is never dropped"),
    # 429 / Retry-After
    ("Retry-After is honored", "429 Retry-After honored"),
    # fallback policy
    ("never silently selected", "unauthorized/paid fallback never silently selected"),
    ("owned escalation", "exhausted chain is an owned escalation"),
]
for needle, label in required_phrases:
    check(needle in text, label)

print("== RR-013: capacity stays operator-side ==")
client_nevers = [
    ("never calls a model", "box never calls a provider"),
    ("never holds a reservation", "box never holds a reservation"),
    ("operator-side concerns", "capacity is operator-side concern"),
    ("never sees a capacity refusal shaped", "capacity refusal is never the box's fault"),
]
for needle, label in client_nevers:
    check(needle in text, label)

print("== RR-013: no shipped rescue file encodes plan limits as universal facts ==")
# The "do not encode user-mentioned plan limits as universal verified provider
# facts" clause: concurrency figures in shipped (public) files must never be
# stated as fleet-wide provider facts. The private FLEET repo owns measured,
# sourced, account-scoped numbers; ONB ships policy, not figures.
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
    # a bare concurrency/parallel-call claim worded as a provider fact
    for m in re.finditer(
        r"(?:provider|account|api)[^\n]{0,80}\b(?:allows?|permits?|supports?|cap(?:acity)?\s+of)\b[^\n]{0,40}\b\d+\s*concurrent",
        body, re.IGNORECASE):
        # allow the explicitly-conditional wording ("verified ... for that account")
        window = max(0, m.start() - 120)
        ctx = body[window:m.end()]
        if not re.search(r"verif|measured|source|account-scoped|do not|never", ctx, re.IGNORECASE):
            violations.append((os.path.relpath(path, REPO), m.group(0)[:90]))
if not violations:
    ok(f"no unsourced provider concurrency facts across {checked} shipped files")
else:
    for rel, snippet in violations[:5]:
        fail(f"plan-limit-as-fact risk in {rel}", snippet)

print("== RR-013: summary ==")
print(f"pass={PASS} fail={FAIL}")
if FAIL:
    sys.exit(1)
sys.exit(0)

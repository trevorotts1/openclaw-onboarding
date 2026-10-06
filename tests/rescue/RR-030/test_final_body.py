#!/usr/bin/env python3
"""tests/rescue/RR-030/test_final_body.py   (RR plan fix F88)

The client-facing final update must be plain sentences, never the machine dump
('Repair status: partial. Verification: unverified. Remaining blocker: repair_not_verified. Owner: ...').

  B1  repaired + verified                   -> "Fixed and checked."
  B2  partial / not_repaired + blocker      -> "We are still working on this: <plain words>."
  B3  blocker owned by a person (operator)  -> "A specialist will follow up."
  B4  no machine vocabulary ever appears in any output
  B5  missing / unreadable / empty result file -> a safe sentence, exit 0
  B6  repaired but NOT verified is not "Fixed and checked."
  B7  the poll wires final-body into RR_NOTIFICATION_FINAL_BODY and the old dump is gone from the source
Runs the shipped rescue-notification.py as a subprocess against fixture result-v3 objects. Offline."""
import json, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
WORKER = os.path.join(REPO, "65-rescue-receiver", "rescue-notification.py")
POLL = os.path.join(REPO, "65-rescue-receiver", "rescue-poll.sh")
PASS = FAIL = 0

def ok(n):
    global PASS; PASS += 1; print("  ok   " + n)
def bad(n, d=""):
    global FAIL; FAIL += 1; print("  FAIL " + n + " " + str(d)[:300])
def check(c, n, d=""):
    ok(n) if c else bad(n, d)

TMP = tempfile.mkdtemp(prefix="rr030-finalbody-")
def body(result, raw=None, path=None):
    p = path or os.path.join(TMP, "r.json")
    if path is None:
        with open(p, "w") as fh:
            fh.write(raw if raw is not None else json.dumps(result))
    r = subprocess.run([sys.executable, WORKER, "final-body", "--result-json", p],
                       capture_output=True, text=True, timeout=30)
    return r.returncode, r.stdout.strip()

def v3(repair, verification, blocker=None, reply="I restarted the thing"):
    d = {"schema_version": 3, "incident_id": "inc", "instruction_id": "ins", "attempt_id": "a",
         "runtime_id": "box", "repair_status": repair, "verification_status": verification,
         "evidence_refs": ["agent_turn:ins"], "remaining_blocker": blocker,
         "reply": {"text": reply, "reply_chars": len(reply)}}
    return d

MACHINE = re.compile(r"repair status|verification:|remaining blocker|owner:|next action|assigned_agent|repair_not_verified|"
                     r"structured_result_missing|unverified|not_repaired|_", re.I)

print("== F88: client-facing final body is plain English ==")
rc, out = body(v3("repaired", "verified"))
check((rc, out) == (0, "Fixed and checked."), "B1 repaired + verified -> 'Fixed and checked.'", (rc, out))

blk = {"reason": "repair_not_verified", "owner": "assigned_agent", "next_action": "run the original acceptance check"}
rc, out = body(v3("partial", "unverified", blk))
check(rc == 0 and out.startswith("We are still working on this: ") and out.endswith("."), "B2 partial -> 'We are still working on this: ...'", out)
rc, out2 = body(v3("not_repaired", "unverified", {"reason": "Gateway needs a restart", "owner": "assigned_agent"}))
check(out2 == "We are still working on this: gateway needs a restart.", "B2 a human-written reason is kept (lower-cased first word)", out2)

rc, out = body(v3("not_repaired", "unverified", {"reason": "repair_not_verified", "owner": "operator", "next_action": "page"}))
check(out == "A specialist will follow up.", "B3 operator-owned blocker -> 'A specialist will follow up.'", out)

for name, res in (("partial/code", v3("partial", "unverified", blk)),
                  ("not_repaired/no blocker", v3("not_repaired", "unverified", None)),
                  ("partial/operator", v3("partial", "unverified", {"reason": "x_y", "owner": "operator", "next_action": "z_z"})),
                  ("repaired/verified", v3("repaired", "verified"))):
    rc, o = body(res)
    check(rc == 0 and not MACHINE.search(o), "B4 no machine vocabulary in output (%s)" % name, o)

rc, o = body(None, path=os.path.join(TMP, "does-not-exist.json"))
check(rc == 0 and o == "We are still working on this: we have not confirmed the fix yet.", "B5 missing file -> safe sentence, exit 0", (rc, o))
rc, o = body(None, raw="not json at all {")
check(rc == 0 and o.startswith("We are still working on this"), "B5 unreadable JSON -> safe sentence, exit 0", (rc, o))
rc, o = body(None, raw="")
check(rc == 0 and o.startswith("We are still working on this"), "B5 empty file -> safe sentence, exit 0", (rc, o))

rc, o = body(v3("repaired", "unverified"))
check(o != "Fixed and checked.", "B6 repaired but unverified is NOT 'Fixed and checked.'", o)
rc, o = body(v3("advice_delivered", "verified"))
check(o != "Fixed and checked.", "B6 advice delivered is NOT 'Fixed and checked.'", o)

src = open(POLL, encoding="utf-8").read()
check("rescue-notification.py\" final-body" in src, "B7 rescue-poll.sh builds the body with final-body")
check("Repair status: %s" not in src and "Remaining blocker: %s" not in src, "B7 the old machine-dump format string is gone from rescue-poll.sh")

print("\nRR-030 F88 final body: %d passed, %d failed" % (PASS, FAIL))
sys.exit(1 if FAIL else 0)

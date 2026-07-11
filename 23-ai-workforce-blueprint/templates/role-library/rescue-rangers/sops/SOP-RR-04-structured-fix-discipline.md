# SOP-RR-04 — Structured-Fix Discipline (BINDING)

**SOP ID:** `SOP-RR-04-STRUCTURED-FIX`
**Owner:** Structured-Fix Operator (with the Diagnostician's confirmed root cause)
**Type:** Per-routed-ticket
**Scope:** Every remedy applied to a box through the rescue path.
**HARD RULE:** DRY-RUN first, live only on explicit opt-in, always within the tier's
fix budget, always with a recorded one-line revert. Credentials, DNS, deletion, and
model sovereignty are **never** auto-applied.

---

## 9. Standard Operating Procedures

### SOP 9.1 — Confirm the Inputs

**Steps:** Require a confirmed root cause + named class from the Diagnostician, a
tier + budget from the Dispatcher, and confirmation the class is NOT in the never-auto
set. Missing any → back to the Dispatcher. You do not improvise a destructive command
from memory; only sanctioned `remediate.sh` fix cards + the maintenance path.

---

### SOP 9.2 — DRY-RUN, then the Reversibility Gate

**Steps:**
1. Run `remediate.sh <class>` in DRY-RUN (the default — live requires
   `RESCUE_REMEDIATE_LIVE=1` set for THIS ticket only). Read the printed plan + its
   one-line revert; verify it matches the diagnosis exactly.
2. **Reversibility gate:** config-free + reversible → proceed. Config-touching +
   reversible → record the one-line revert (and snapshot where the maintenance path
   provides one) FIRST, then proceed. Irreversible / never-auto class → STOP,
   prepare the exact command + revert, hand to the Dispatcher to page the Operator.

---

### SOP 9.3 — Go Live Within Budget

**Steps:** Set `RESCUE_REMEDIATE_LIVE=1` for this ticket, run the fix, hold to the
**FAST 180s / LONG 1,320s / default 300s** ceiling. Overrunning the budget is itself
a failure signal — stop, report, let the Dispatcher re-tier or page. Never run an
unbounded fix.

---

### SOP 9.4 — Verify End-to-End (no exit-code-only closes)

**Steps:** Re-run the SAME falsifiable check the Diagnostician used (port listening,
`/health` 200, cron parked, offset sane). A fix is done when the SYMPTOM is gone,
proven by the same test that confirmed it — not because the command exited 0.
Record the fix class + mode + verify result in the ledger (`rescue_ledger.py answer
… --fix-class … --fix-mode …`); the answer goes back through the relay `answer`
action.

---

### SOP 9.5 — On Failure / Over-Budget / Three Strikes

**Steps:** Stop at the budget or the third consecutive same-defect fail. REVERT any
partial change using the recorded one-line revert (never leave a box half-fixed —
either verified or reverted). Report with evidence to the Dispatcher, who routes to
QC/Postmortem.

**Never-auto set (prepare + page, never apply):** rotating/writing any credential;
changing DNS or Cloudflare records; deleting data or files; swapping/substituting a
client's model or provider. The Operator owns every one-way door.

**Outputs:** A verified, reversible fix (or a clean revert + escalation).
**Hand to:** Ticket Clerk (record), QC/Postmortem (on P1 / 3-strike).

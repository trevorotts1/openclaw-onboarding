# SOP-RR-06 — Decision Rule & Step Gate (BINDING)

**SOP ID:** `SOP-RR-06-DECISION-RULE-STEP-GATE`
**Owner:** Rescue Rangers runner (the AI that runs a case)
**Type:** Per-case, every step
**Scope:** Every Rescue Rangers case, from intake to close, on every box.
**HARD RULE:** No step of a case is done until `rr_step_gate.py record` has written its artifact. Never use a text search to decide a step is done. Never print a result you did not get.

---

## 9. Standard Operating Procedures

### SOP 9.1 — The Eight Steps and Their Artifacts

Each step of a case is one JSON file in `<cases root>/<ticket_id>/`. A step can only be
started when `check` confirms every earlier step's artifact exists, parses, belongs to
this ticket, carries its required fields, and is chained to the artifact before it by a
sha256 digest. Evidence files named in an artifact must exist and be non-empty.

| Step | Artifact file | What it holds |
|---|---|---|
| 1 | `01-intake.json` | the escalation exactly as received |
| 2 | `02-cap.json` | the live daily-cap reading for this box |
| 3 | `03-triage.json` | severity, failure class, what the box already tried |
| 4 | `04-decision.json` | the route: `tell_agent` \| `fix_ourselves` \| `page_operator` \| `not_an_incident` |
| 5 | `05-work.json` | what was done (the instruction text sent, or the fix applied) |
| 6 | `06-verify.json` | the acceptance check that was re-run, and its result |
| 7 | `07-reply.json` | the outcome delivered to the client's agent, with the delivery receipt |
| 8 | `08-close.json` | the closing state written to the ledger, with the ledger receipt |

Every artifact also carries, added by the script and never by the runner: `step`,
`recorded_at`, `prev_sha256` (digest of the previous step's file; `""` for step 1),
`body_sha256` (digest of the runner-supplied body). A recorded step is never
overwritten. Exit codes: `0` allowed / recorded, `20` REFUSED, `2` usage or filesystem
failure.

---

### SOP 9.2 — The Three Commands

Run from the folder holding `rr_step_gate.py`, with the rules file beside it.

1. **`check`** — before starting a step. Refuses unless steps 1 to N-1 are all valid.
   ```
   python3 rr_step_gate.py check --cases-root <cases root> --ticket RR-000123 --step 4
   ```
2. **`record`** — writes the artifact for a step, atomically, after validating the
   steps before it and the body it is given.
   ```
   python3 rr_step_gate.py record --cases-root <cases root> --ticket RR-000123 --step 4 --from 04-decision.json
   ```
3. **`audit`** — validates every step that exists and prints which step is next.
   ```
   python3 rr_step_gate.py audit --cases-root <cases root> --ticket RR-000123
   ```

`python3 rr_step_gate.py selftest` exercises the gate itself.

---

### SOP 9.3 — The Decision Rule

The route in `04-decision.json` is a recorded decision, not a judgement made in the
moment. Rules are read from `decision-rules.json` beside the script and evaluated in
order; the first rule that matches is the route. The gate refuses a `rule_id` that is
not in that file, and refuses a `route` that differs from the rule's own route.

| Rule | When | Route |
|---|---|---|
| R0 | the box is at or over its daily cap, or the live cap table could not be read | `page_operator` |
| R1 | this is a test, a duplicate, or a routine question the agent can answer itself | `not_an_incident` |
| R2 | the fix would rotate, regenerate or revoke a credential; change DNS or Cloudflare; delete data or files; or change the client's model or provider | `page_operator` |
| R3 | only the client can do it in their own account: sign in again, approve access, add a payment method, top up a balance, confirm a choice | `tell_agent` |
| R4 | the client's agent cannot act: gateway down, looping, not answering, or the same instruction already failed once on this ticket | `fix_ourselves` |
| R5 | the fault is in something we shipped, or the same failure is open on two or more boxes | `fix_ourselves` (also: open a repository fix) |
| R6 | the fix matches a listed, reversible fix card on a reachable box with a one-line undo | `fix_ourselves` |
| R7 | anything else | `tell_agent` |

Rule R2 has no exception for "we hold the key". Holding a provider key means the operator CAN do it, not that a machine may.

---

### SOP 9.4 — Who Does What

| Who | Does | Never |
|---|---|---|
| The client's agent | Tells its owner what is happening; does what only the owner can do in their own account — signs in again, approves access, adds a payment method, tops up a balance, confirms a choice | Never applies a fix on a box, never pages the Operator itself |
| The Rescue Rangers runner | Reads the live cap, triages, records the decision, applies a listed reversible fix, re-runs the same acceptance check, and hands the reply to the client's agent | Never says a step is done without an artifact, never prints a result it did not get |
| The Operator | Every one-way door: rotate, regenerate or revoke a credential; change DNS or Cloudflare; delete data or files; change the client's model or provider — and anything else the rule table routes to `page_operator` | Never delegates a one-way door to a machine |

---

### SOP 9.5 — The Cap

The cap in step 2 is read from the live table `rr_cap_counters`. The drill ledger `rescue_ledger.py` is never used for a live case; the gate refuses it.

**Outputs:** A case folder whose every finished step carries a recorded, chained
artifact, and a decision whose rule and route agree.
**Hand to:** The client's agent (the reply), the Operator (a `page_operator` route).

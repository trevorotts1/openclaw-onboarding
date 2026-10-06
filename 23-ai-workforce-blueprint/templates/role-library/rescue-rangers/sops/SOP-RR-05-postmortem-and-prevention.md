# SOP-RR-05 — Postmortem & Prevention (BINDING)

**SOP ID:** `SOP-RR-05-POSTMORTEM-PREVENTION`
**Owner:** QC / Postmortem Specialist
**Type:** Retrospective (never gates the live rescue)
**Scope:** Every P1 and every three-strike ticket.
**HARD RULE:** Every P1 and 3-strike gets a postmortem that ends in a DURABLE
artifact — a Skill-61 fix-class proposal, a repo issue, or a documented known-benign
note. Findings that die in a thread do not count. Rescue findings become fleet
prevention.

---

## 9. Standard Operating Procedures

### SOP 9.0 — Durable Postmortem Job Path (RR-035, BINDING)

Qualification is mechanical, not judgment: **P1 severity OR third strike
episode** (mint = episode 1; each recurrence folds one more episode).
The FLEET quality plane (`rescue/service/postmortem-service.mjs`)
persists the severity/strike assessment and transactionally enqueues
**exactly one** postmortem job per qualifying ticket — replays and
restarts converge to the same job, never a second.

- **Owner is always `postmortem-qc`**, never the mitigation actor; the job
  carries its own due time (72h), evidence digest + reference, lease and
  retry. The mitigation actor is recorded alongside so the claim gate can
  refuse self-review.
- **Mitigation never waits** for the retrospective: the ticket closes
  through the ledger independently; the job is a side effect of the
  outcome, never a gate on it.
- **Independent reviewer required:** the claim refuses the recorded
  mitigation actor. The QC record stores reviewer, artifact reference,
  root cause, prevention proposal, and evidence version
  (ledger-schema | assessor-schema | ticket-version).
- **A proposed fix can NEVER auto-activate:** `activate:true` is refused;
  no apply/deploy path exists in the quality plane. Acceptance is a
  routing decision through normal review/batch release only.
- **Operator-only weekly prevention review** with health + missed-run
  catchup; week keys are `pmweek|*`, cursor + receipts DISTINCT from the
  RR-038 daily operations digest (`digest|*`) — the two planes never
  share state. A provider outage leaves weeks open and jobs pending;
  catchup regenerates them on the next run instead of skipping.
- **Privacy:** attach evidence by digest + reference; never regenerate
  guesses and never copy client problem text into the retrospective.

Merge gate: the FLEET service + battery land first (RR-035 FLEET slice);
this SOP text takes effect with that landing, not before.

### SOP 9.1 — Pull the Durable Record

**Steps:** Read the ticket from the ledger (`rescue_ledger.py get --ticket-id <id>`):
symptom, confirmed root cause, evidence, fix class/mode, answer, and
`return_delivered`. Ground truth is the ledger — never reconstruct from memory or a
Telegram thread.

---

### SOP 9.2 — Verify Answer Quality + Delivery

**Steps:** Confirm the diagnosis was evidence-backed (log line / config value / doc
citation, not a guess); the fix was reversible and verified END-TO-END by the same
falsifiable check; and the outcome actually reached the client agent
(`return_delivered=1`). An answer that only landed in the operator group is an
**incomplete dispatch** — flag it to the Dispatcher to chase the return leg.

---

### SOP 9.3 — Classify the Failure

**Steps:** Map to the known taxonomy the maintenance department + Skill 61 catalog
(restart-velocity loop, orphan gateway / deferral deadlock, subtractive-threshold
config freeze, Telegram offset corruption, MCP timeout/announce spam, billing
furnace). Note the matching Skill-61 class, or describe a NEW class with its
detection signature.

---

### SOP 9.4 — Produce the Durable Artifact (one, sometimes two)

- **Skill-61 fix-class proposal** — for a repeatable box-level loop/wedge a
  deterministic watchdog could catch. Include: the detection signature (D-class), the
  reversible kill-card (exact command + one-line revert), and whether it is safe for
  the unattended path (config-free) or must be PREPARED-and-operator-applied. Hand to
  the openclaw-maintenance department (Skill-61 owner).
- **Repo issue** — for a bug/gap in the onboarding repo, a skill, or an SOP. File
  with the repro, the evidence, and the exact file:line.
- **Known-benign note** — for a false alarm: record WHY so the same symptom is not
  re-escalated (feeds the Diagnostician's hypothesis set).

---

### SOP 9.5 — Weekly Quality Review

**Steps:** Run the operator-only weekly prevention review (SOP 9.0 job
queue is the source list, not a fresh scan). Read the week's resolved +
incomplete tickets. Flag: any answered ticket
with `return_delivered=0`; any client that hit the daily cap; any defect class that
recurred; any diagnosis later contradicted (a wrong-layer fix). Summarize into a
short prevention memo for the Dispatcher + Operator; recommend FAST-tiering recurring
classes with a ready `remediate.sh` card.

**Outputs:** A prevention artifact per qualifying ticket; a weekly prevention memo.
**Hand to:** openclaw-maintenance / Skill-61 owner (fix-classes), Operator (repo
issues), Dispatcher (tiering + return-leg chases).

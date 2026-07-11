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

**Steps:** Read the week's resolved + incomplete tickets. Flag: any answered ticket
with `return_delivered=0`; any client that hit the daily cap; any defect class that
recurred; any diagnosis later contradicted (a wrong-layer fix). Summarize into a
short prevention memo for the Dispatcher + Operator; recommend FAST-tiering recurring
classes with a ready `remediate.sh` card.

**Outputs:** A prevention artifact per qualifying ticket; a weekly prevention memo.
**Hand to:** openclaw-maintenance / Skill-61 owner (fix-classes), Operator (repo
issues), Dispatcher (tiering + return-leg chases).

# ZHC Bugs Department -- Standard Operating Procedures (B-9.1 to B-9.5)

**Department:** Bugs
**Version:** 1.0
**Authority:** THE_HEALER_AND_BUGS_DEPARTMENT.md PART 2.4
**SOP count:** 5

These SOPs are the operational backbone of the ZHC Bugs Department. They are transplanted verbatim from the build authority document and govern every function from ticket intake through closure and knowledge capture. All five SOPs are also embedded within the relevant specialist role files (bug-intake-clerk.md, triage-dedup-analyst.md, bug-librarian.md) per the standard role template.

---

## SOP B-9.1 -- Bug Ticket Intake

**Owned by:** Bug Intake Clerk (Registrar)

Validate schema, assign id, open Kanban card in REPORTED, acknowledge reporter, write to the ledger. Failure mode: malformed ticket = return to reporter with the exact missing fields, never silently discard.

---

## SOP B-9.2 -- Triage, Severity, and Dedup

**Owned by:** Triage and Dedup Analyst

Confirm severity (P0 run-dead: SLA heal-start < 30 min; P1: < 4 h; P2: next business cycle; P3: backlog), signature-match against the knowledge base, set dedup_of/recurrence, flag healed-bug recurrences CRITICAL, move card to TRIAGED.

---

## SOP B-9.3 -- Kanban Lifecycle

**Owned by:** Bug Librarian (board hygiene); card moves shared across all three specialists and Healers per the column ownership rules below.

The board columns and who moves cards: REPORTED (Intake Clerk) -> TRIAGED (Analyst) -> HEALING (the assigned Healer owns the card) -> VERIFYING (Healer: fix applied, regression running) -> HEALED (report sent, regression green) -> REGRESSION WATCH (Librarian, time-boxed) -> CLOSED. Every transition stamps the ticket. SLA timers per severity; breaches auto-flag to the Chief Healer and appear in the weekly report.

---

## SOP B-9.4 -- Healer Handoff and Status Sync

**Owned by:** Triage and Dedup Analyst (initiates handoff); Bug Librarian (monitors status sync)

Package the ticket + evidence to the assigned Healer, keep ticket status and Kanban card in lockstep with the Healer's incident ledger (single source of truth: the ticket id links the Healer's incident record), surface blockers.

---

## SOP B-9.5 -- Closure, Knowledge Capture, and Metrics

**Owned by:** Bug Librarian (Pattern Keeper)

On HEALED: capture root cause, fix summary, SOP/core-file patches, teaching link into the knowledge base; move through REGRESSION WATCH to CLOSED on schedule; publish weekly metrics to the operator: new bugs, healed, mean time to heal, SLA breaches, and the same-bug-twice count, which must read 0.

---

*All five SOPs are also embedded in the relevant specialist role files (bug-intake-clerk.md carries B-9.1; triage-dedup-analyst.md carries B-9.2; bug-librarian.md carries B-9.3 and B-9.5) with full expanded step-by-step detail. This file is the SOP library reference index for the Bugs Department.*

---

## 9. Standard Operating Procedures (Numbered)

### SOP 9.1 -- Bug Ticket Intake (Full Procedure)

**When to run:** Every time a bug or system failure is reported via any channel: Telegram message, operator manual report, automated alert, or another department's escalation.
**Frequency:** Continuous -- every inbound bug report triggers this SOP before any other action.
**Inputs:** Raw report (message text, screenshot, error log, or automated alert payload), the bug-ticket-schema.json schema, and the Kanban board access.

**Steps:**
1. **Define -- Classify the report.** Is this a new bug, a question about system behavior (not a bug), or a recurrence of a known issue? A question that is not a bug gets redirected to the appropriate department within 5 minutes with a clear explanation. A potential recurrence of a known issue also enters this SOP -- dedup is the Triage Analyst's job, not the Intake Clerk's. Intake Clerk's role: accept the report and open the ticket. Never pre-filter at intake.
2. **Measure -- Validate the report against the schema.** Pull bug-ticket-schema.json. Every required field must be derivable from the report: bug_id (auto-assigned by the Intake Clerk), reporter (who reported it and via what channel), timestamp (when the report was received -- use the platform timestamp, not when the Intake Clerk processes it), component (what part of the system is affected -- if unknown, use "unknown" rather than guessing), description (verbatim from the reporter, not paraphrased), reproduction_steps (ask the reporter if not provided -- do not invent steps), severity_proposal (Intake Clerk makes a preliminary proposal; Triage Analyst confirms), environment (which instance, which version, which platform -- ask if not provided). If reproduction_steps or environment are missing: acknowledge the report, open a PENDING ticket, and ask the reporter for the missing information. Close-PENDING when the information arrives.
3. **Analyze -- Assign the bug_id and open the Kanban card.** Bug IDs follow the format defined in bug-ticket-schema.json. The Kanban card opens in REPORTED status. Set the card fields to match the ticket: bug_id, reporter, timestamp, component, description (truncated to the card's display limit with a link to the full ticket), and severity_proposal. The REPORTED status is the signal to the Triage and Dedup Analyst that a new ticket is ready for triage.
4. **Improve -- Acknowledge the reporter.** Send an acknowledgment to the reporter within 5 minutes of ticket creation: the bug_id, the confirmed receipt, and the expected next-contact timing based on severity_proposal (P0: you will hear back in 30 minutes; P1: 4 hours; P2: next business cycle; P3: we've logged it). The acknowledgment is a commitment -- it must be sent even if the ticket is PENDING for missing information.
5. **Control -- Write to the incident ledger.** Record the ticket in the department's incident ledger: bug_id, timestamp, reporter, component, severity_proposal, and ledger_status ("OPEN"). The incident ledger is the audit trail; the Kanban board is the workflow tool. Both must be updated. Mismatch between ledger and Kanban board is a bookkeeping error that the Bug Librarian's SOP B-9.3 will catch -- prevent it at intake.

**Outputs:** Bug ticket (schema-valid), Kanban card in REPORTED status, acknowledgment sent to reporter, ledger entry created.
**Hand to:** Triage and Dedup Analyst (the REPORTED Kanban card is the handoff signal).
**Failure mode:** If the Kanban board is unavailable (system down, auth failure), open the ticket in the incident ledger only, note "KANBAN UNAVAILABLE -- ledger only," alert the Bug Librarian and Director of Bugs, and retry the Kanban card creation when the board returns. Never delay the ledger entry or the reporter acknowledgment waiting for the Kanban board.

---

### SOP 9.2 -- Triage, Severity Confirmation, and Dedup (Full Procedure)

**When to run:** When a Kanban card moves into REPORTED status (the intake handoff signal). The Triage and Dedup Analyst processes every REPORTED card within the P0/P1/P2/P3 SLA from the card's timestamp.
**Frequency:** Continuous -- triggered per new REPORTED card. P0/P1 cards pre-empt all other work.
**Inputs:** Bug ticket (all fields from SOP B-9.1 intake), the knowledge base (all closed and open tickets for signature matching), and SOP B-9.2 severity criteria.

**Steps:**
1. **Define -- Establish triage priority.** The severity_proposal from the Intake Clerk is a preliminary classification. The Triage Analyst's job is to confirm or correct it. Pull the ticket from the REPORTED queue in timestamp order, but promote any P0 proposals to the front of the queue immediately. SLA clock for the Analyst's decision starts at the ticket's intake timestamp, not when the Analyst picks it up.
2. **Measure -- Confirm severity against the SOP B-9.2 criteria.** P0: the system is run-dead for the client -- core functionality unavailable, data at risk, or revenue is actively being lost right now. SLA for heal-start: 30 minutes from intake. P1: major feature broken, a workaround exists but the workaround is a significant degradation. SLA for heal-start: 4 hours. P2: non-critical bug; the system runs; no revenue impact; workaround is easy or unnecessary. SLA for triage: next business cycle. P3: cosmetic, minor, low-impact. SLA for triage: backlog scheduling. If the evidence in the ticket does not match the severity_proposal: assign the correct severity and note the reclassification reason.
3. **Analyze -- Signature-match against the knowledge base.** Search the knowledge base for tickets with similar: component (same part of the system), symptom description (same error message, same failure mode), and environment. If a match is found: set dedup_of to the matching bug_id and note the similarity basis. If the matched ticket is HEALED or CLOSED: set recurrence_flag to true and reclassify the severity as CRITICAL (regardless of the original severity classification) -- a previously-healed bug recurring is a systemic failure, not a routine bug. If no match is found: set dedup_of to "none" and recurrence_flag to false.
4. **Improve -- Assign the Healer and set the SLA deadline.** Route to the appropriate Healer based on the component (match the component to the Healer who owns that part of the system). Set the SLA deadline using the confirmed severity. Record: severity_confirmed, dedup_of, recurrence_flag, assigned_healer, SLA_deadline. Move the Kanban card to TRIAGED.
5. **Control -- Initiate healer handoff (SOP B-9.4).** Package the ticket, the triage decision, and all supporting evidence (reproduction steps, logs, environment details, knowledge base dedup notes) into the handoff package. The handoff package is not the raw ticket -- it is the ticket plus the analyst's triage findings. The Healer should be able to begin work immediately without asking for anything.

**Outputs:** Triage decision record (severity_confirmed, dedup_of, recurrence_flag, assigned_healer, SLA_deadline), Kanban card in TRIAGED status, healer handoff package initiated.
**Hand to:** Assigned Healer (via healer handoff SOP B-9.4); Bug Librarian (to monitor SLA timers).
**Failure mode:** If the knowledge base is unavailable for dedup checking: proceed with the triage decision without dedup. Set dedup_checked to false and note "KNOWLEDGE BASE UNAVAILABLE -- dedup skipped." Flag to the Bug Librarian to perform dedup retroactively when the knowledge base returns. A dedup skip on a P0 is a risk: if it is a recurrence, the Healer needs to know -- flag this risk explicitly in the handoff package.

---

### SOP 9.3 -- Kanban Lifecycle and SLA Enforcement (Full Procedure)

**When to run:** Continuously. The Bug Librarian owns board hygiene. This SOP governs all card transitions and SLA monitoring across the department.
**Frequency:** Continuous monitoring; explicit board review at the start of every business day and every 4 hours during business hours for P0 tickets.
**Inputs:** The Kanban board (all columns), the incident ledger, and the SLA deadlines recorded in each ticket.

**Steps:**
1. **Define -- Map the current state of every open card.** At the start of every monitoring cycle: pull all open cards. For each card, compare its current column (REPORTED, TRIAGED, HEALING, VERIFYING, HEALED, REGRESSION WATCH) to its ticket's SLA deadline and its last-transition timestamp. Calculate the time elapsed since the last transition. Any card where (current_time - last_transition_timestamp) > (SLA_deadline - intake_timestamp) is breached.
2. **Measure -- Check for SLA breaches.** A breach is detected when: (a) a REPORTED card has not moved to TRIAGED within the severity's triage SLA, (b) a TRIAGED card has not moved to HEALING within the severity's heal-start SLA, or (c) any P0 card has been in HEALING or VERIFYING for more than 4 hours without a status update from the Healer. SLA breach actions: immediately auto-flag to the Chief Healer and the Director of Bugs via Telegram (single message with bug_id, severity, current column, time breached, and assigned roles).
3. **Analyze -- Validate that card status matches the incident ledger.** Every card transition must be reflected in the incident ledger within 5 minutes of the card move. A card in HEALING status with no ledger entry for the HEALING transition is a bookkeeping error. The Bug Librarian corrects ledger mismatches immediately and notes the correction in the ledger.
4. **Improve -- Manage REGRESSION WATCH timing.** When a ticket moves to REGRESSION WATCH: record the watch_end_date based on the severity (P0: 7-day watch; P1: 5-day watch; P2: 3-day watch; P3: 1-day watch). At the watch_end_date: if no recurrence has been reported, move the card to CLOSED and update the ledger. If a recurrence is reported during the watch: do not move to CLOSED -- reopen as a new P0 ticket (regardless of the original severity) with recurrence_flag true and dedup_of referencing the current ticket.
5. **Control -- Publish weekly board status.** Every Monday: compile the board's current state (cards in each column, any overdue cards, any cards in REGRESSION WATCH and their remaining watch time) and deliver it to the Director of Bugs as the Board Status Report. This is separate from the weekly metrics report (SOP B-9.5) but informs it.

**Outputs:** Board hygiene maintained (all cards current), SLA breach alerts fired, ledger synchronized with board, weekly Board Status Report.
**Hand to:** Director of Bugs (SLA breach alerts and Board Status Report); Bug Librarian (self-owned process).
**Failure mode:** If the Kanban board is unavailable: maintain SLA tracking and board state in the incident ledger only. Alert the Director and all active Healers that the board is down. Resume board synchronization when it returns. SLA enforcement does not pause for board outages.

---

### SOP 9.4 -- Healer Handoff and Status Sync (Full Procedure)

**When to run:** After every triage decision (the Triage Analyst initiates). Ongoing: the Bug Librarian monitors status synchronization between the Kanban board and the Healer's incident ledger throughout the HEALING and VERIFYING phases.
**Frequency:** Per ticket handoff (Triage Analyst). Continuous synchronization monitoring (Bug Librarian).
**Inputs:** Triage decision record (from SOP B-9.2), full bug ticket, Healer assignment, SLA deadline, knowledge base dedup notes if applicable.

**Steps:**
1. **Define -- Assemble the handoff package.** The handoff package is not the raw ticket. It is: (a) the full ticket with all fields, (b) the triage decision summary (severity_confirmed, dedup_of, recurrence_flag, SLA_deadline), (c) all reproduction evidence (steps, logs, environment details, screenshots or recordings if available), (d) the knowledge base entry for any dedup match (so the Healer knows what was tried before if this is a recurrence), (e) the assigned Healer's identifier and the expected first-response time from them.
2. **Measure -- Deliver the handoff package to the assigned Healer.** Send via the department's designated handoff channel. The Healer must acknowledge receipt within the first-response SLA (P0: 15 minutes; P1: 1 hour; P2: next business cycle; P3: 48 hours). If no acknowledgment within the SLA: alert the Director of Bugs and re-route to an available Healer.
3. **Analyze -- Maintain status synchronization during HEALING.** The single source of truth for a ticket's status is the ticket record itself. The Healer's incident ledger must link to the ticket via bug_id. The Kanban card must reflect the Healer's current stage (HEALING when diagnosis is active, VERIFYING when a fix is applied and regression tests are running). The Bug Librarian checks synchronization every 4 hours for P0/P1 tickets and every business day for P2/P3 tickets.
4. **Improve -- Surface blockers.** If the Healer reports a blocker (cannot reproduce, fix requires vendor action, fix requires operator decision), the Bug Librarian escalates the blocker to the Director of Bugs within 1 hour. The blocker is logged in the ticket as a status note with timestamp. The SLA clock does not pause for a blocker unless the Director explicitly grants a pause and records the reason.
5. **Control -- Confirm HEALED status.** When the Healer moves the card to HEALED: verify that the Healer's incident ledger entry for this ticket includes: the root cause, the fix applied (specific technical action, not "fixed the bug"), and the regression test result (test name, pass/fail, timestamp). If any of these three are missing: the card cannot move to HEALED. Return to the Healer with the missing fields.

**Outputs:** Handoff package delivered to Healer; ongoing synchronization maintained; HEALED confirmation with complete closure data.
**Hand to:** Assigned Healer (handoff package). Bug Librarian (ongoing monitoring). Director of Bugs (blocker escalations).
**Failure mode:** If the assigned Healer is unavailable (agent down, no response within SLA), escalate immediately to the Director of Bugs and Chief Healer. Do not hold the ticket in TRIAGED waiting for an unavailable Healer. The Director re-routes to an available Healer within the SLA window.

---

### SOP 9.5 -- Closure, Knowledge Capture, and Metrics (Full Procedure)

**When to run:** When a Healer moves a card to HEALED status. Also runs at the end of REGRESSION WATCH for final closure, and every Monday for weekly metrics compilation.
**Frequency:** Per HEALED ticket (closure cycle); weekly (metrics report).
**Inputs:** HEALED ticket with complete closure data (root cause, fix summary, regression test results), knowledge base write access, and the incident ledger for the metrics period.

**Steps:**
1. **Define -- Confirm the HEALED ticket has complete closure data.** Required before knowledge capture begins: root_cause (specific, not vague), fix_summary (what was changed and where), regression_test_result (test name, pass result, timestamp), and SLA compliance status (was the SLA met or breached, and if breached, by how long). If any of these are missing: the card stays in HEALED and the Bug Librarian pings the Healer for the missing data. Maximum wait: 1 hour for P0/P1, 24 hours for P2/P3, then escalate to Director.
2. **Measure -- Author the knowledge base entry.** The knowledge base entry must include: (a) bug_id and ticket link, (b) symptom signature (the observable symptom that triggered the report -- specific enough that another agent or operator would recognize a recurrence within 10 seconds), (c) root cause (the technical cause, not the symptom), (d) fix summary (what was changed), (e) regression test path or test name (so a future Healer can verify the fix is still in place), (f) tags for the component and the failure category. The knowledge base entry is the institutional memory -- write it as if the original Healer is unavailable and a new Healer must handle the recurrence.
3. **Analyze -- Move through REGRESSION WATCH to CLOSED.** After the knowledge base entry is authored: move the card to REGRESSION WATCH and set the watch_end_date per the severity schedule (SOP B-9.3). During the watch period: the Bug Librarian monitors for recurrence reports that reference this bug_id. At watch_end_date with no recurrence: move to CLOSED, update the ledger, and close the ticket.
4. **Improve -- Compile the weekly metrics report.** Every Monday: query the incident ledger for the past 7-day period. Calculate: new_bugs_count, healed_count, mean_time_to_heal (for each healed ticket: HEALED_timestamp - intake_timestamp, then mean), sla_breaches (tickets where HEALED_timestamp > SLA_deadline), same_bug_twice_count (tickets with recurrence_flag=true reported in this period). For any same_bug_twice event: include a root-cause note explaining why the original fix failed to prevent recurrence. Draft the report and submit to the QC Specialist before delivery to the operator.
5. **Control -- Deliver the weekly report after QC clearance.** Never send the weekly metrics report to the operator without QC Specialist clearance (SOP QC-9.3 of the QC Specialist Bugs file). After clearance: deliver via the designated operator channel. Archive the report to the department's metrics log with the period dates as the filename suffix.

**Outputs:** Knowledge base entry (complete), Kanban card in CLOSED status, ledger updated, weekly metrics report (QC-cleared and delivered to operator).
**Hand to:** Operator (weekly metrics report). Knowledge base (entry created). Bug Librarian (ledger closed).
**Failure mode:** If the knowledge base write fails (system unavailable, auth error): write the knowledge base entry to a pending file in the department's scratch directory, note the pending status on the ticket, and retry when the knowledge base returns. Never close a ticket as CLOSED without a knowledge base entry successfully written and confirmed.

---

*Bugs Department SOPs v1.0 -- Full procedural reference for all five core operating procedures.*

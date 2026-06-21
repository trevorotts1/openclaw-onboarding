# PA-04-01 — Task Capture and Intake

**Role:** Task & Priority Manager
**Department:** Personal Assistant (04)
**SOP class:** Core operating procedure (generic role standard — applies to every client of this role)
**Method:** DMAIC (Define, Measure, Analyze, Improve, Control)

> This is a GENERIC role procedure. It describes HOW this role operates,
> not any one client's private data. The owner referenced below is whoever
> this assistant serves; substitute the live owner profile from the workspace
> USER.md at run time. Tools named are the workspace defaults; use whatever
> calendar, task, document, and messaging tools the workspace is wired to.

---

## Define

Task Capture is the front door of the personal-assistant task system. Every commitment the owner makes, every request that arrives, and every follow-up the assistant notices must land in one trusted system within minutes of being surfaced. Nothing lives only in the owner's head, a chat thread, or the assistant's short-term memory.

**Purpose of this procedure**
- Guarantee that no commitment is ever lost between the moment it is spoken and the moment it is acted on.
- Replace the owner's mental load of remembering tasks with a single authoritative list the assistant maintains.
- Make every task actionable at capture time: it must have an owner, a next action, and a place it lives.

**When to run**
- Continuously — the instant a task is generated in conversation, email, a meeting, a message, or the assistant's own observation.

**Frequency**
- Real-time on creation; plus a twice-daily sweep (morning and end-of-day) to catch anything missed.

**Inputs**
- Spoken or written requests from the owner.
- Inbound email, chat, and meeting notes that imply an action.
- Commitments the owner makes to other people that the assistant overhears or is copied on.
- Recurring obligations (bills, renewals, check-ins) surfaced by the calendar or prior tasks.

**Outputs**
- A task record in the workspace task tool with: clear action verb, owner, due date or 'no date', source, and priority hint.
- An acknowledgement to the requester when the task came from a third party ('Got it, I'll handle X by Y').

**Hand-to (downstream)**
- The Daily Top 3 Selection procedure (PA-04-02) for prioritization, and the Delegation and Routing procedure (PA-04-04) when the task belongs to someone else.

**Definition of done**
- Every surfaced task exists as a single record in the task tool with a next action; the owner's head is empty of 'I must remember to...'.

## Measure

Capture quality is measured by how rarely a task is discovered late — i.e., a commitment that surfaced but was never recorded and only came to light when it became urgent or was missed.

**Signals this procedure tracks**
- Tasks discovered already overdue that were never captured (the 'leak rate').
- Time between a task being surfaced and being recorded.
- Duplicate records created for the same commitment.

**Key metrics**
- **Capture latency** — median minutes from surfacing to recorded; target under 5 minutes for live requests.
- **Leak rate** — tasks that surfaced but were never captured, found per week; target zero.
- **Duplicate rate** — duplicate task records per 100 captures; target under 2.

**Where the measurement is recorded**
- Capture metrics are tallied in the role MEMORY.md weekly note; the task tool itself is the system of record for the tasks.

## Analyze

Most capture failures are not memory failures — they are friction failures. If recording a task takes too many steps, the assistant or owner skips it under pressure. Analyze where friction is highest.

**Decision rules**
- If a request is ambiguous, capture it anyway with a 'clarify' flag rather than dropping it; clarify on the next owner touchpoint.
- If the same commitment arrives twice, merge into the existing record rather than creating a second one.
- If a task is clearly someone else's job, capture it as a delegation candidate and route via PA-04-04.

**Common failure modes and how to read them**
- **Verbal-only commitments:** Tasks agreed to in conversation that never get written down. Capture them in the same minute they are spoken.
- **Inbox-as-task-list:** Treating an unread email as a reminder. Convert to a real task record; the inbox is not a task system.
- **Over-capture noise:** Recording every passing idea as a task until the list is unusable. Capture commitments, not musings.

## Improve

The capture procedure improves by removing steps. The fastest possible path from 'task exists' to 'task recorded' wins.

**Step-by-step procedure**
1. The moment a task is surfaced, write it down immediately in the task tool — before doing anything else with it.
2. Phrase the task as an action: start with a verb and name the concrete outcome ('Draft reply to the supplier', not 'supplier email').
3. Attach the source (who asked, where it came from) so the task can be traced and verified later.
4. Set a due date if one exists; if not, mark it 'no date' rather than guessing — undated is honest, a fake date is noise.
5. Add a one-line priority hint (urgent / important / someday) so the Daily Top 3 selection has signal to work with.
6. If the task came from a third party, send a short acknowledgement so they know it is handled.
7. Run the twice-daily sweep: scan email, chat, and meeting notes for any commitment that did not already become a task.

**Escalation path**
- If the owner is generating tasks faster than they can be captured and triaged, raise it: the issue is capacity, and the owner should decide what to stop accepting.

**Optimization loop**
- Build quick-capture habits: one keystroke or one phrase that creates a task record.
- Periodically review the leak rate and trace each leaked task back to where capture broke down.

## Control

Control keeps this procedure stable and trustworthy over time. The guardrails below are non-negotiable; the review cadence catches drift; and the audit trail makes every run verifiable after the fact.

**Guardrails (never violate)**
- Never let a commitment live only in memory or only in a chat thread.
- Never create a task without a clear next action.
- Never silently drop an ambiguous request — capture and flag it.

**Review cadence**
- Weekly: review leak rate and duplicate rate; adjust capture friction points.

**Failure mode to actively prevent**
- 'I will put that in the system later.' Later never comes. Capture every task the moment it is generated.

**Audit trail**
- Each task record carries its source and creation time.
- The weekly MEMORY.md note records leak count and any capture-process change made.

## Worked walkthrough

A generic, end-to-end run of this procedure, shown so the assistant can see the method in motion. The names, numbers, and details below are illustrative of the shape of the work, not any one owner's private information.

- **Run step 1.** The moment a task is surfaced, write it down immediately in the task tool — before doing anything else with it. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 2.** Phrase the task as an action: start with a verb and name the concrete outcome ('Draft reply to the supplier', not 'supplier email'). In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 3.** Attach the source (who asked, where it came from) so the task can be traced and verified later. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 4.** Set a due date if one exists; if not, mark it 'no date' rather than guessing — undated is honest, a fake date is noise. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 5.** Add a one-line priority hint (urgent / important / someday) so the Daily Top 3 selection has signal to work with. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 6.** If the task came from a third party, send a short acknowledgement so they know it is handled. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 7.** Run the twice-daily sweep: scan email, chat, and meeting notes for any commitment that did not already become a task. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.

By the end of the walkthrough the definition of done is satisfied: every surfaced task exists as a single record in the task tool with a next action; the owner's head is empty of 'I must remember to...'. If any step could not be completed, the assistant follows the escalation path above rather than guessing or skipping — an honest gap surfaced early is always cheaper than a silent failure discovered late.

## Operating checklist

**Before the run**
- All required inputs are on hand: Spoken or written requests from the owner; Inbound email, chat, and meeting notes that imply an action; Commitments the owner makes to other people that the assistant overhears or is copied on; Recurring obligations (bills, renewals, check-ins) surfaced by the calendar or prior tasks.
- The trigger condition is genuinely met (see *When to run*), not merely assumed.
- The owner's current preferences and goals are loaded from the workspace USER.md.

**During the run**
- Each step is completed in order; nothing is skipped to save time under pressure.
- Every decision follows the decision rules above; exceptions are logged with the reason.
- Anything that cannot be done is escalated immediately, not deferred silently.

**After the run**
- All outputs exist and are where the downstream procedure expects them: A task record in the workspace task tool with: clear action verb, owner, due date or 'no date', source, and priority hint; An acknowledgement to the requester when the task came from a third party ('Got it, I'll handle X by Y').
- The metrics for this run are recorded (Capture latency, Leak rate, Duplicate rate).
- The hand-off is made: The Daily Top 3 Selection procedure (PA-04-02) for prioritization, and the Delegation and Routing procedure (PA-04-04) when the task belongs to someone else.
- Any lesson learned is written to the role MEMORY.md so the next run inherits it.

---

*End of PA-04-01. This procedure is owned by the Task & Priority Manager. Update it whenever the underlying workflow, tools, or owner preferences change, and log the change in the role MEMORY.md so the next run inherits the improvement.*

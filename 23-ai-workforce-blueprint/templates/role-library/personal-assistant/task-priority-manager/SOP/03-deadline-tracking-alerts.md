# PA-04-03 — Deadline Tracking and Alerts

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

Deadline Tracking ensures every commitment with a date is watched, surfaced ahead of time, and never missed by surprise. The assistant owns the timeline so the owner never has to ask 'when was that due?'

**Purpose of this procedure**
- Prevent missed deadlines by alerting the owner with enough lead time to act.
- Distinguish hard deadlines (real consequences) from soft ones (preferences) and treat each appropriately.
- Maintain a single, trusted forward view of everything coming due.

**When to run**
- Daily in the morning review; continuously for hard deadlines as they approach.

**Frequency**
- Daily, with real-time alerting for imminent hard deadlines.

**Inputs**
- Every dated task from the Task Capture system.
- Calendar events and external due dates (renewals, filings, payments).
- Lead-time requirements for each deadline (how long the work actually takes).

**Outputs**
- Timely alerts to the owner ahead of each deadline, sized to the lead time the work needs.
- A forward 'what's due this week / next week' view delivered in the morning review.

**Hand-to (downstream)**
- The Daily Top 3 Selection (PA-04-02) so imminent deadlines claim a daily slot, and the owner for any decision the deadline forces.

**Definition of done**
- No deadline is ever met by surprise; every one is surfaced with enough time to do the work calmly.

## Measure

Tracking is measured by lead time delivered, not just by 'nothing missed' — a deadline met in a last-minute panic is a tracking failure even if the work got done.

**Signals this procedure tracks**
- Deadlines met with adequate lead time vs. last-minute scrambles.
- Deadlines missed entirely.
- Soft deadlines repeatedly pushed (a sign of a deeper prioritization problem).

**Key metrics**
- **On-time rate** — deadlines met without a last-minute scramble; target above 95%.
- **Miss count** — deadlines missed entirely; target zero.
- **Lead-time delivered** — median days of warning given before a deadline; sized to the work.

**Where the measurement is recorded**
- Each missed or scrambled deadline is logged with a root cause in MEMORY.md for the weekly review.

## Analyze

Most scrambles come from tracking the deadline date but not the work's lead time. A task due Friday that takes three days must alert on Tuesday, not Friday.

**Decision rules**
- Alert lead time = the deadline minus the realistic time the work takes, minus a buffer.
- Hard deadlines get escalating alerts as they approach; soft deadlines get one gentle reminder.
- A soft deadline pushed three or more times is escalated as a prioritization decision, not just a reminder.

**Common failure modes and how to read them**
- **Date-only tracking:** Alerting on the due date instead of the start-by date. Always work backwards from the lead time.
- **Hard/soft blindness:** Treating every deadline identically. Reserve escalating alerts for deadlines with real consequences.
- **Silent slippage:** Soft deadlines quietly sliding forever. Surface chronic slippage to the owner as a decision.

## Improve

Tracking improves by learning each task type's real lead time and by tuning alert timing so the owner gets warned exactly when action is still easy.

**Step-by-step procedure**
1. Each morning, pull every dated task and the calendar into one forward view.
2. For each deadline, compute the start-by date by subtracting the work's realistic duration plus a buffer.
3. Flag anything whose start-by date is today or past — these need action now, not on the due date.
4. Deliver the forward view in the morning review: due today, this week, next week.
5. For imminent hard deadlines, set escalating alerts and confirm the owner has the time blocked to do the work.
6. For soft deadlines pushed repeatedly, present the owner a clear choice: commit, reschedule, or drop.
7. Log any miss or scramble with its root cause so the lead-time estimate for that task type improves.

**Escalation path**
- If a hard deadline cannot be met with the time remaining, escalate to the owner immediately with options (negotiate the date, add help, reduce scope) — never let it arrive silently.

**Optimization loop**
- Maintain a small library of lead-time estimates per recurring task type.
- Tune alert timing so the owner is warned while action is still low-stress.

## Control

Control keeps this procedure stable and trustworthy over time. The guardrails below are non-negotiable; the review cadence catches drift; and the audit trail makes every run verifiable after the fact.

**Guardrails (never violate)**
- Never alert only on the due date for work that needs lead time.
- Never let a hard deadline approach without confirming the work is scheduled.
- Never let a soft deadline slip indefinitely without surfacing it.

**Review cadence**
- Weekly: review on-time rate and every scramble's root cause; refine lead-time estimates.

**Failure mode to actively prevent**
- Only monitoring hard deadlines and ignoring soft ones until the soft ones quietly become hard.

**Audit trail**
- The forward view is delivered every morning and archived.
- Every miss/scramble has a logged root cause and a corrective adjustment.

## Worked walkthrough

A generic, end-to-end run of this procedure, shown so the assistant can see the method in motion. The names, numbers, and details below are illustrative of the shape of the work, not any one owner's private information.

- **Run step 1.** Each morning, pull every dated task and the calendar into one forward view. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 2.** For each deadline, compute the start-by date by subtracting the work's realistic duration plus a buffer. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 3.** Flag anything whose start-by date is today or past — these need action now, not on the due date. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 4.** Deliver the forward view in the morning review: due today, this week, next week. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 5.** For imminent hard deadlines, set escalating alerts and confirm the owner has the time blocked to do the work. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 6.** For soft deadlines pushed repeatedly, present the owner a clear choice: commit, reschedule, or drop. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 7.** Log any miss or scramble with its root cause so the lead-time estimate for that task type improves. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.

By the end of the walkthrough the definition of done is satisfied: no deadline is ever met by surprise; every one is surfaced with enough time to do the work calmly. If any step could not be completed, the assistant follows the escalation path above rather than guessing or skipping — an honest gap surfaced early is always cheaper than a silent failure discovered late.

## Operating checklist

**Before the run**
- All required inputs are on hand: Every dated task from the Task Capture system; Calendar events and external due dates (renewals, filings, payments); Lead-time requirements for each deadline (how long the work actually takes).
- The trigger condition is genuinely met (see *When to run*), not merely assumed.
- The owner's current preferences and goals are loaded from the workspace USER.md.

**During the run**
- Each step is completed in order; nothing is skipped to save time under pressure.
- Every decision follows the decision rules above; exceptions are logged with the reason.
- Anything that cannot be done is escalated immediately, not deferred silently.

**After the run**
- All outputs exist and are where the downstream procedure expects them: Timely alerts to the owner ahead of each deadline, sized to the lead time the work needs; A forward 'what's due this week / next week' view delivered in the morning review.
- The metrics for this run are recorded (On-time rate, Miss count, Lead-time delivered).
- The hand-off is made: The Daily Top 3 Selection (PA-04-02) so imminent deadlines claim a daily slot, and the owner for any decision the deadline forces.
- Any lesson learned is written to the role MEMORY.md so the next run inherits it.

---

*End of PA-04-03. This procedure is owned by the Task & Priority Manager. Update it whenever the underlying workflow, tools, or owner preferences change, and log the change in the role MEMORY.md so the next run inherits the improvement.*

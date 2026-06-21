# PA-38-04 — Post-Trip Review and Expense Reconciliation

**Role:** Travel Logistics Specialist
**Department:** Personal Assistant (38)
**SOP class:** Core operating procedure (generic role standard — applies to every client of this role)
**Method:** DMAIC (Define, Measure, Analyze, Improve, Control)

> This is a GENERIC role procedure. It describes HOW this role operates,
> not any one client's private data. The owner referenced below is whoever
> this assistant serves; substitute the live owner profile from the workspace
> USER.md at run time. Tools named are the workspace defaults; use whatever
> calendar, task, document, and messaging tools the workspace is wired to.

---

## Define

Post-Trip Review and Expense Reconciliation closes out a trip: reconcile every cost, capture what was learned, and refine the owner's travel preferences and the planning rules so the next trip is smoother.

**Purpose of this procedure**
- Reconcile all travel expenses accurately and promptly.
- Capture lessons from the trip so the same problems do not recur.
- Keep the owner's travel preference profile and the planning rules current.

**When to run**
- Immediately after the owner returns from a trip.

**Frequency**
- Per trip.

**Inputs**
- All receipts and charges from the trip.
- The trip's plan, confirmations, and disruption log.
- The owner's feedback on how the trip went.

**Outputs**
- A reconciled expense summary, ready for the owner's accounting or reimbursement process.
- Updated travel preferences and planning rules captured for future trips.

**Hand-to (downstream)**
- The owner's finance/accounting process (the expense summary) and the Trip Planning procedure (PA-38-01) which inherits the refined preferences and rules.

**Definition of done**
- Every cost is reconciled, the trip's lessons are captured, and the preference profile and planning rules are updated.

## Measure

Closeout quality is measured by reconciliation accuracy and by whether lessons actually improve the next trip.

**Signals this procedure tracks**
- Expenses reconciled vs. left as loose charges.
- Lessons captured vs. lost to memory.
- Preference updates that show up in the next trip's planning.

**Key metrics**
- **Reconciliation accuracy** — charges matched to receipts and categorized correctly; target 100%.
- **Reconciliation timeliness** — days from return to a finished expense summary; minimize.
- **Lesson-applied rate** — trip lessons that change the next trip's plan; target high.

**Where the measurement is recorded**
- The expense summary is filed to the owner's process; lessons and preference updates go in MEMORY.md.

## Analyze

Expense closeout fails when receipts go missing or charges are miscategorized; the review fails when lessons are noted but never applied. Analyze for both completeness and follow-through.

**Decision rules**
- Match every charge to a receipt; flag any charge without one rather than guessing.
- Categorize expenses to the owner's accounting structure, not a generic one.
- Every captured lesson must update either the preference profile or a planning rule — otherwise it is not really captured.

**Common failure modes and how to read them**
- **Missing receipts:** Reconciling from memory when a receipt is lost. Flag the gap; do not fabricate a figure.
- **Stale preferences:** Learning the owner hates a red-eye but never recording it. Update the profile every trip.
- **Lost lessons:** Noting a problem in conversation but never changing the rule. Tie every lesson to a concrete update.

## Improve

Closeout improves by making reconciliation fast and complete and by reliably folding each trip's lessons back into planning.

**Step-by-step procedure**
1. Gather every receipt and charge from the trip.
2. Match each charge to its receipt; flag any charge that has no receipt rather than guessing the amount.
3. Categorize the expenses to the owner's accounting structure and produce a clean summary.
4. File the expense summary to the owner's accounting or reimbursement process.
5. Debrief the trip with the owner: what worked, what was uncomfortable, what to change.
6. Update the owner's travel preference profile with anything learned (seating, timing, lodging, transport).
7. Update the planning rules (buffers, route choices, fallbacks) so PA-38-01 inherits the improvement.

**Escalation path**
- If expenses cannot be reconciled (a significant charge with no receipt or an unexplained discrepancy), escalate to the owner rather than filing an inaccurate summary.

**Optimization loop**
- Capture receipts in real time during the trip to make closeout fast and complete.
- Keep the preference profile and planning rules in one place the next trip's planning reads.

## Control

Control keeps this procedure stable and trustworthy over time. The guardrails below are non-negotiable; the review cadence catches drift; and the audit trail makes every run verifiable after the fact.

**Guardrails (never violate)**
- Never reconcile a charge from memory when the receipt is missing; flag it.
- Never file an expense summary you know to be inaccurate.
- Never end a trip review without updating preferences or planning rules.

**Review cadence**
- Per trip (the review IS the cadence); periodically review the preference profile for staleness.

**Failure mode to actively prevent**
- Closing a trip without capturing its lessons — so the same avoidable discomfort recurs on every future trip.

**Audit trail**
- Each trip's expense summary and reconciliation gaps are recorded.
- Preference and rule updates are logged and verified applied next trip.

## Worked walkthrough

A generic, end-to-end run of this procedure, shown so the assistant can see the method in motion. The names, numbers, and details below are illustrative of the shape of the work, not any one owner's private information.

- **Run step 1.** Gather every receipt and charge from the trip. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 2.** Match each charge to its receipt; flag any charge that has no receipt rather than guessing the amount. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 3.** Categorize the expenses to the owner's accounting structure and produce a clean summary. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 4.** File the expense summary to the owner's accounting or reimbursement process. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 5.** Debrief the trip with the owner: what worked, what was uncomfortable, what to change. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 6.** Update the owner's travel preference profile with anything learned (seating, timing, lodging, transport). In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.
- **Run step 7.** Update the planning rules (buffers, route choices, fallbacks) so PA-38-01 inherits the improvement. In practice this means the assistant does it deliberately and records the result, so the next step has what it needs and the run can be verified later.

By the end of the walkthrough the definition of done is satisfied: every cost is reconciled, the trip's lessons are captured, and the preference profile and planning rules are updated. If any step could not be completed, the assistant follows the escalation path above rather than guessing or skipping — an honest gap surfaced early is always cheaper than a silent failure discovered late.

## Operating checklist

**Before the run**
- All required inputs are on hand: All receipts and charges from the trip; The trip's plan, confirmations, and disruption log; The owner's feedback on how the trip went.
- The trigger condition is genuinely met (see *When to run*), not merely assumed.
- The owner's current preferences and goals are loaded from the workspace USER.md.

**During the run**
- Each step is completed in order; nothing is skipped to save time under pressure.
- Every decision follows the decision rules above; exceptions are logged with the reason.
- Anything that cannot be done is escalated immediately, not deferred silently.

**After the run**
- All outputs exist and are where the downstream procedure expects them: A reconciled expense summary, ready for the owner's accounting or reimbursement process; Updated travel preferences and planning rules captured for future trips.
- The metrics for this run are recorded (Reconciliation accuracy, Reconciliation timeliness, Lesson-applied rate).
- The hand-off is made: The owner's finance/accounting process (the expense summary) and the Trip Planning procedure (PA-38-01) which inherits the refined preferences and rules.
- Any lesson learned is written to the role MEMORY.md so the next run inherits it.

---

*End of PA-38-04. This procedure is owned by the Travel Logistics Specialist. Update it whenever the underlying workflow, tools, or owner preferences change, and log the change in the role MEMORY.md so the next run inherits the improvement.*

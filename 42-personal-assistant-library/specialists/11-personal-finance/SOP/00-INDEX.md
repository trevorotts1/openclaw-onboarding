# SOP Index — Personal Finance Assistant

**Department:** Personal Finance Assistant (11-personal-finance)
**Total SOPs:** 5
**Format:** DMAIC (Define, Measure, Analyze, Improve, Control)
**Last updated:** 2026-06-02

---

## SOP Quick Reference

| SOP ID | Name | Frequency | Trigger | File |
|--------|------|-----------|---------|------|
| PA-11-01 | Bill Calendar | Weekly reconciliation + real-time on new obligation | New recurring commitment, due-date change, Sunday review | [PA-11-01-bill-calendar.md](PA-11-01-bill-calendar.md) |
| PA-11-02 | Subscription Audit | Quarterly (every 90 days) + pre-subscription gate | Scheduled audit, "I'm bleeding money," new subscription inquiry | [PA-11-02-subscription-audit.md](PA-11-02-subscription-audit.md) |
| PA-11-03 | Expense Capture | Continuous (real-time) + daily sweep + weekly summary | Any purchase above $0, receipt lands, daily end-of-day prompt | [PA-11-03-expense-capture.md](PA-11-03-expense-capture.md) |
| PA-11-04 | Renewal & Negotiation Prep | Per-renewal (30 days out) | Bill Calendar identifies upcoming renewal, "this bill seems high" | [PA-11-04-renewal-negotiation-prep.md](PA-11-04-renewal-negotiation-prep.md) |
| PA-11-05 | Weekly Money Brief | Weekly (Sunday 7 PM) + monthly deep dive (first Sunday) | Automatic Sunday trigger, owner request, pre-major-spending decision | [PA-11-05-weekly-money-brief.md](PA-11-05-weekly-money-brief.md) |

---

## SOP Taxonomy

### Foundation (Build First, Run Always)
- **PA-11-01 — Bill Calendar:** The operating system. Every recurring obligation lives here. Without this, nothing else works reliably.
- **PA-11-03 — Expense Capture:** The data pipeline. Every dollar spent flows through here into categorized, searchable records.

### Health & Optimization (Scheduled Cadence)
- **PA-11-02 — Subscription Audit:** The waste-finder. Quarterly deep scan of every subscription, membership, and recurring charge with cancel/negotiate/schedule actions.
- **PA-11-04 — Renewal & Negotiation Prep:** The money-saver. One-page briefing packets delivered 30 days before every renewal with competitor pricing and scripts.

### Communication (Weekly Rhythm)
- **PA-11-05 — Weekly Money Brief:** The deliverable. Every Sunday, a 90-second snapshot that replaces financial anxiety with clarity — 3 numbers, zero judgment, one action.

---

## SOP Dependency Map

```
PA-11-01 (Bill Calendar) ───────── Foundation ─ feeds PA-11-04 + PA-11-05
    │
    ├── PA-11-02 (Subscription Audit) ← uses calendar data, feeds audit results back to PA-11-01 + PA-11-04
    │
    ├── PA-11-03 (Expense Capture) ──── Independent data pipeline ─ feeds PA-11-05
    │
    ├── PA-11-04 (Renewal & Negotiation Prep) ← triggered by PA-11-01 calendar + PA-11-02 audit
    │
    └── PA-11-05 (Weekly Money Brief) ← consumes output from ALL four other SOPs
         │
         ├── Bill forecast from PA-11-01
         ├── Subscription flags from PA-11-02
         ├── Weekly spending data from PA-11-03
         └── Upcoming renewals from PA-11-04
```

---

## Reading Order for New Personal Finance Assistants

1. **PA-11-01 — Bill Calendar** (the foundation — every financial obligation is tracked here first)
2. **PA-11-03 — Expense Capture** (the data pipeline — without clean expense data, nothing else is accurate)
3. **PA-11-05 — Weekly Money Brief** (the deliverable — understand what {{TOKEN}} actually sees every Sunday)
4. **PA-11-02 — Subscription Audit** (the waste-finder — quarterly rhythm, read before first audit cycle)
5. **PA-11-04 — Renewal & Negotiation Prep** (the money-saver — read before first renewal window opens)

---

## Cross-SOP Integration Points

| Integration | From SOP | To SOP | What Flows |
|---|---|---|---|
| Bill calendar feeds renewal prep | PA-11-01 | PA-11-04 | Upcoming renewals trigger 30-day prep briefs |
| Bill calendar feeds money brief | PA-11-01 | PA-11-05 | 7-day bill forecast populates "Due This Week" section |
| Subscription audit updates bill calendar | PA-11-02 | PA-11-01 | Cancelled subscriptions removed, negotiated rates updated |
| Subscription audit triggers renewal prep | PA-11-02 | PA-11-04 | "Negotiate" items get a PA-11-04 briefing packet |
| Expense capture feeds money brief | PA-11-03 | PA-11-05 | Weekly category totals populate "Spent This Week" section |
| Money brief references all four | PA-11-05 | PA-11-01 → PA-11-04 | Consolidated snapshot pulls from every upstream SOP |

---

## DMAIC Compliance

All SOPs follow the DMAIC structure:
- **Define:** Purpose, trigger conditions, scope
- **Measure:** What success looks like, key metrics
- **Analyze:** Root cause patterns, failure modes, data insights (Section 3 in every SOP)
- **Improve:** Step-by-step procedure, scripts, frameworks
- **Control:** Escalation rules, output artifacts, duration estimates, maintenance cadence

Each SOP includes CTQ binary checks, metric targets, escalation rules, and a Definition of Done.

---

## Version

| Field | Value |
|---|---|
| Version | 1.0 |
| Last Updated | 2026-06-02 |
| Total SOPs | 5 |
| Department | Specialist 11 — Personal Finance Assistant |
| Owner | {{TOKEN}} |

# Failed Payment Recovery (payment plans only)

**id:** `failed-payment-recovery`
**category:** launch-c · **family:** failed_payment · **start:** new, small
**Stays:** draft only. Nothing here sends or goes live.

---

## Gate — read this first

Build this automation **only when the launch plan says the offer has payment plans**:

```
launch_plan.offer.payment_plans == true
```

Source: `shared-utils/signature_launch_contract/launch-plan.schema.json` (`offer.payment_plans`
is the switch that "opens the failed_payment automation family (spec 3.3). false forbids it.").

When `payment_plans` is `false` or absent:

- do **not** create the workflow,
- do **not** add a `failed_payment` entry to `automations[]`,
- the package records `failed payment: not applicable (offer has no payment plans)`.

This gate is the only hard rule in the file. It is what checklist line **A1** reads.

---

## What this runs

A small transactional recovery sequence for a failed installment charge:

| # | Step | Timing | Channel | What it does |
|---|---|---|---|---|
| 1 | Recovery email | Immediate | Email | Says the scheduled payment for `{plan_amount}` did not go through, gives the one update-payment link. No shame copy. |
| 2 | SMS nudge | +4 h, inside 8 a.m.–9 p.m. recipient local | SMS | Same link, one sentence, reply invitation + STOP. **Skipped when `a2p_ready` is false.** |
| 3 | Retry check + follow-up | +2 days (or the processor's retry date if later) | Email | If/Else on `payment-recovered`: end on success, otherwise the same link and the processor's stated retry date. |
| 4 | Final notice | +3 days after step 3 | Email | Last automatic reminder + invitation to reply. Names only the consequence the client actually configured. |
| 5 | Close out | After step 4 | Tag | `payment-recovery-exhausted`, remove `payment-failed-active`. |

Goal: `payment-recovered`. A recovered buyer exits at the if/else before any further send.

## Facts, not inventions

`{plan_amount}`, the retry date and "what happens next" come from the offer and the payment
processor only. This template never types a price or a deadline of its own.

## Build rail

**Skill 44 engine** (`caf` / `CampaignBuilder`). The official GHL API cannot create, update,
publish or trigger a workflow — its only workflow operation is `GET /workflows/`
(`GHL-CAPABILITY-NOTE.md`, U-GHL-PROBE, 2026-10-20).

- `CampaignBuilder` creates the workflow as a draft and auto-creates a **Tag Added** trigger only.
- The **Payment Failed** trigger needs `caf workflows patch-trigger --trigger-json <file>`
  (snapshot before write) or the Tier-4 managed browser.
- Duration waits are verifiable through the engine; a calendar-date wait would need the browser.
- Every action stays inactive until a separate client approval switches it live.

## Files

- `failed-payment-recovery.json` — the machine-readable template (gate, trigger, sequence, build plan).
- `failed-payment-recovery.md` — this page.

## Check (no new test suite)

```
python3 -m json.tool 44-convert-and-flow-operator/automation-templates/launch-c/failed-payment-recovery.json > /dev/null
```

Proves checklist **A1** for this family: the template exists, its start is "new, small", and its
`gate.field` is `offer.payment_plans` with `equals: true`. Checklist **A2** is met by
`draft_only: true` and the closing tag step; this family never adds promotional sends.

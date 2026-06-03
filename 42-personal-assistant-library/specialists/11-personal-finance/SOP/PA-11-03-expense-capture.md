# SOP PA-11-03: Expense Capture

**Department:** Specialist 11 — Personal Finance Assistant
**SOP ID:** PA-11-03
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To capture every meaningful expense in real time — from the $4.50 coffee to the $4,500 equipment purchase — so {{TOKEN}} always has a clear, accurate picture of where money is going without relying on memory, bank-lag, or end-of-month receipt archaeology.

---

## DMAIC Section 3 — Analyze (Where Expense Tracking Breaks Down)

### 3.1 The Invisible Expense Problem

Most expense systems fail at the edges — the small, the irregular, and the reimbursable. Here's what actually happens:

| Failure Point | Example | Why It Matters |
|---|---|---|
| **Micro-transaction blindness** | Coffee, parking, app store purchases, tips. Individually trivial, collectively hundreds per month. These never make it into manual tracking because they feel "not worth logging." | $5/day × 30 days = $150/month of invisible spend |
| **Split-transaction confusion** | A Target run that includes groceries, office supplies, and a gift. The bank sees one charge: "Target — $87.42." The budget needs three categories. | Miscategorization corrupts the entire spending picture |
| **Reimbursement amnesia** | {{TOKEN}} pays for a business meal, forgets to submit it, and effectively gives the company a $75 loan forever. | Direct cash loss — 100% avoidable |
| **Cash evaporation** | ATM withdrawal of $200. The bank says "$200 — ATM." Three weeks later, {{TOKEN}} has no idea where it went. | $200/month of untraceable spending |
| **Spousal/partner spend blind spot** | A shared account where both people spend. One person's "Target — $87.42" is the other person's mystery charge. | Budget disagreements, double-counting |
| **Annual/irregular surprise** | Car registration, property tax, insurance deductible, holiday gifts. Not monthly, so not in the monthly mental budget. | Cash-flow shock when they land |

### 3.2 Why "I'll Just Check My Bank App" Fails

Bank apps show transactions, not expenses. The difference: a transaction is "Amazon — $34.99." An expense is "Book: 'Deep Work' by Cal Newport — Professional Development — $34.99." Without the second, {{TOKEN}} can't answer:
- "How much did I spend on professional development last quarter?"
- "Is my food delivery habit actually $600/month?"
- "What did I spend on that client dinner — and did I get reimbursed?"

---

## Trigger Conditions

- Any purchase above $0 (micro-capture)
- Any business expense (reimbursement tracking)
- Any receipt lands in {{TOKEN}}'s email, camera roll, or messages
- Daily: "End-of-day sweep" prompt — "Any cash spending today? Any receipts I should log?"
- Weekly: "Receipt gap check" — match captured receipts against bank transactions

---

## Procedure

### Step 1: Instant Capture Channels

I make capture frictionless by meeting {{TOKEN}} wherever the expense happens:

| Channel | Method |
|---|---|
| **Digital receipt (email)** | Auto-forwarded to tracking inbox. I extract merchant, amount, date, and category. |
| **Physical receipt** | {{TOKEN}} snaps a photo, sends it to me. I transcribe and categorize within 5 minutes. |
| **Verbal mention** | "Hey, I just spent $200 on [thing]" — I log it immediately. This is the safety net for cash and Venmo. |
| **Bank feed sync** | Where available, I pull transactions daily and flag uncategorized ones for {{TOKEN}}'s input. |

### Step 2: The Capture Standard

Every expense gets logged with:

| Field | Example |
|---|---|
| Date | June 2, 2026 |
| Amount | $87.42 |
| Merchant | Target |
| Category | Split: $45 Groceries, $25 Office Supplies, $17.42 Gift |
| Payment Method | {{PAYMENT_CARD_REF}} |
| Business/Personal | Personal |
| Reimbursable? | No |
| Receipt Link | [photo/receipt attached] |
| Notes | Paper towels, printer ink, birthday card for mom |

### Step 3: Split-Transaction Handling

For multi-category purchases, I break the total into line items immediately — never defer. If {{TOKEN}} doesn't have the breakdown handy, I estimate with a flag: "⚠️ Estimated split — confirm when you have the receipt." The flag triggers a follow-up within 24 hours.

### Step 4: Daily Categorization Sweep

End of each day: I review every uncategorized transaction, apply categories, and flag anything unusual:
- New merchant never seen before → "First time at [merchant] — what category?"
- Amount significantly different from pattern → "Target is usually ~$40 — this was $87. Big trip or something to flag?"
- Potential duplicate → "Two DoorDash charges today — confirm both are yours?"

### Step 5: Weekly Cash-Flow Summary

Every Sunday, I compile the week's spending into a one-glance summary:

| Category | This Week | vs. Weekly Average | Trend |
|---|---|---|---|
| Food & Dining | $245.00 | +$62.00 | ⬆️ |
| Transportation | $38.50 | -$12.00 | ⬇️ |
| Shopping | $112.00 | +$89.00 | ⬆️🔴 |
| Bills & Utilities | $210.00 | On track | ➡️ |

Categories more than 30% above average get an automatic flag — not as judgment, but as awareness. "You spent $89 more on shopping this week than usual. Worth noting — not necessarily a problem."

---

## Output Artifacts

- Daily expense log (continuously updated)
- Weekly Cash-Flow Summary (delivered Sunday evening)
- Reimbursement tracker (business expenses flagged and followed up)
- Monthly category trend report (rolled up from weekly summaries)

---

## Estimated Duration

- Per-expense capture: 1-2 minutes (receipt → logged)
- Daily sweep: 5-10 minutes
- Weekly summary: 15 minutes

---

## Escalation

- Unusually large single expense (>2x normal discretionary spend) → gentle same-day flag: "Just checking — was the $X at [merchant] expected?"
- Uncategorized transaction stays unresolved >7 days → escalate with reminder
- Cash withdrawal >$200 with no logged purpose after 48 hours → follow up

---

*Knowing where your money goes isn't about restriction — it's about intention. When {{TOKEN}} sees the full picture, every dollar becomes a choice instead of a mystery.*

---

## CTQ Checks (Critical-to-Quality)

- [ ] Every purchase above $0 captured same-day with merchant, amount, date, and category
- [ ] Split transactions broken into line items within 24 hours (zero multi-category lump sums older than 1 day)
- [ ] Daily categorization sweep completed — zero uncategorized transactions older than 24 hours
- [ ] Weekly Cash-Flow Summary delivered every Sunday with all categories covered
- [ ] Business expenses flagged for reimbursement within 24 hours of capture

## Definition of Done

Every dollar {{TOKEN}} spent this week is logged, categorized, and summarized in her Sunday Cash-Flow Brief — she knows exactly where her money went without opening a bank app.

## Tone & Persona Note

This is awareness work, not audit work. Never say "you overspent" — say "spending was higher here this week." Data, not verdict. When {{TOKEN}}'s coffee budget spikes, frame it as "busy week, huh?" not "that's a lot of lattes." Money tracking should feel like a mirror, not a microscope. For Black women professionals navigating spaces where worth is questioned, financial clarity is power — deliver it with warmth and zero shame.

## Escalation

- Unusually large single expense (>2x normal discretionary spend) → gentle same-day flag to {{TOKEN}} and cc Specialist 09 (Daily Check-In)
- Uncategorized transaction unresolved >7 days → escalate to Specialist 14 (Life-Admin Archivist) for receipt/document retrieval
- Cash withdrawal >$200 with no logged purpose after 48 hours → flag to {{TOKEN}} via Specialist 09 (Daily Check-In)
- Suspicious/unrecognized charge → immediate alert to {{TOKEN}}; loop in Specialist 11's PA-11-02 (Subscription Audit) if recurring

*Knowing where your money goes isn't about restriction — it's about intention. When {{TOKEN}} sees the full picture, every dollar becomes a choice instead of a mystery.*

*Version 1.0 — SOP PA-11-03 — {{TOKEN}}*

# SOP PA-11-02: Subscription Audit

**Department:** Specialist 11 — Personal Finance Assistant
**SOP ID:** PA-11-02
**Version:** 1.0
**Owner:** {{TOKEN}}

---

## Purpose

To systematically audit every active subscription, membership, and recurring charge in {{TOKEN}}'s financial life — identifying waste, flagging unused services, and reducing subscription creep before it silently drains thousands of dollars a year. The average person underestimates their monthly subscription spend by 2-3x; this SOP closes that gap.

---

## DMAIC Section 3 — Analyze (Subscription Waste Patterns)

### 3.1 The Leak Map

Every subscription audit I run reveals the same leak patterns. Here's what I look for and why:

| Leak Type | Detection Signal | Annual Cost (Typical) |
|---|---|---|
| **Forgotten Trial** | A charge that started at $0 or $1, then escalated to full price. The user stopped using the service in week 2 but never cancelled. | $120-$360 |
| **The Duplicate** | Two subscriptions that solve the same problem (e.g., two cloud storage services, two streaming platforms with overlapping content, two project management tools). {{TOKEN}} uses one; the other auto-renews silently. | $100-$500 |
| **The Grandfathered Price Trap** | A service {{TOKEN}} signed up for years ago at a lower rate. The provider has since raised prices for new customers but kept {{TOKEN}} on the old plan — which somehow costs MORE than the current offering because it lacks bundled features. | $50-$300 |
| **The "Someday" Subscription** | A learning platform, software tool, or membership {{TOKEN}} subscribed to with genuine intent. Usage dropped to zero within 60 days, but the emotional attachment ("I'll get back to it") prevents cancellation. | $100-$1,000+ |
| **The Bundled Blind Spot** | A subscription billed through a third party (Apple, Amazon, mobile carrier) that doesn't appear on credit card statements with a recognizable name. These are nearly invisible in manual reviews. | $50-$200 |
| **The Family Plan Overbuy** | {{TOKEN}} pays for a family or team plan but only one person uses it — or the plan covers 5 seats and 2 are empty. | $60-$300 |
| **The Auto-Upgrade** | A service upgraded {{TOKEN}} from Basic to Premium/Pro automatically (often tied to a "free trial of Premium" that was never downgraded). | $60-$240 |

### 3.2 Why Manual Reviews Fail

I've observed that ad-hoc subscription checks miss 40-60% of waste because:
- Credit card statements use merchant names that don't match the service ("DIGITALOCEAN" vs. "that server I spun up for a project")
- Apple/Google in-app subscriptions are buried in platform settings, not on bank statements
- Annual subscriptions don't appear in most monthly reviews at all
- The emotional cost of cancellation ("but I MIGHT use it") overrides financial logic unless there's an objective framework

---

## Trigger Conditions

- Quarterly (every 90 days) — automatic scheduled audit
- {{TOKEN}} says "I feel like I'm bleeding money" or "I don't even know what I'm subscribed to"
- A new subscription is about to be added (pre-purchase check: "Do you already have something that does this?")
- Annual financial review

---

## Procedure

### Step 1: Full Surface Scan

Pull every subscription source simultaneously:

1. **Bank & credit card statements** — last 3 full months. Extract every recurring charge. Use pattern matching: same merchant, same approximate amount, same day of month.
2. **Apple ID subscriptions** — Settings → Apple ID → Subscriptions. Screenshot or export.
3. **Google Play subscriptions** — Play Store → Payments & Subscriptions → Subscriptions.
4. **Amazon** — Memberships & Subscriptions (Prime, Channels, Subscribe & Save).
5. **PayPal** — Automatic payments dashboard.
6. **Email search** — "subscription," "receipt," "renewal," "your plan," "welcome to" across the last 12 months (catches annual subscriptions invisible on 3-month bank scans).

### Step 2: Build the Audit Table

Consolidate everything into a single view:

| Service | Cost/Mo | Billed Through | Last Used | Usage Status | Action |
|---|---|---|---|---|---|
| Netflix Premium | $22.99 | Chase Visa | June 1, 2026 | Weekly | KEEP |
| Canva Pro | $12.99 | Apple ID | March 15, 2026 | Dormant 79 days | REVIEW |
| Domain: example.io | $39/yr | Namecheap (PayPal) | Never launched | Zero usage | CANCEL |

### Step 3: Classify Every Subscription

Apply the **Usage-Value Matrix:**

- **HIGH usage + HIGH value** → KEEP. No action needed.
- **HIGH usage + LOW value** → NEGOTIATE. Is there a cheaper plan? A competitor? A bundle?
- **LOW usage + HIGH value** → SCHEDULE. Set a 30-day reactivation deadline. If unused by then, cancel.
- **LOW usage + LOW value** → CANCEL. No mercy. Cancel immediately.

### Step 4: Execute

For items marked CANCEL: cancel within 24 hours and confirm cancellation email is received. For items marked NEGOTIATE: open PA-11-04 (Renewal & Negotiation Prep). For items marked SCHEDULE: set a calendar reminder 30 days out with a simple question: "Did you use [service] this month? If not, cancel."

### Step 5: Prevention — The Pre-Subscription Gate

Before {{TOKEN}} starts any new subscription, I run a quick check: "You currently have [X] that also does [overlapping function]. Are you replacing it or adding to it?" If adding, I ask: "What's the 30-day usage goal? If you don't hit it, we cancel."

---

## Output Artifacts

- Full Subscription Audit Table
- Cancel/Schedule/Negotiate action list with deadlines
- Savings Report: total monthly and annual savings from cancelled subscriptions
- Updated Bill Calendar (PA-11-01) reflecting all changes

---

## Estimated Duration

- Full audit: 60-90 minutes per quarter
- Ongoing gate checks: 2 minutes per new subscription inquiry

---

## Escalation

- Subscription that cannot be cancelled (broken cancellation flow, unresponsive vendor) → escalate with chargeback option
- {{TOKEN}} resists cancelling a LOW-LOW subscription → don't push. Flag it and revisit next quarter with fresh usage data.

---

*Subscriptions are the only expense that grows while you sleep. A 90-day audit keeps the garden weeded — and keeps {{TOKEN}}'s money going to things that actually matter.*

---

## CTQ Checks (Critical-to-Quality)

- [ ] Full surface scan completed across all 6 sources (bank, Apple, Google, Amazon, PayPal, email) — zero skipped
- [ ] Every subscription classified into the Usage-Value Matrix (KEEP / NEGOTIATE / SCHEDULE / CANCEL)
- [ ] All CANCEL items cancelled within 24 hours with confirmation email received
- [ ] Savings Report produced with total monthly and annual dollar figures
- [ ] Updated Bill Calendar (PA-11-01) reflects all changes within same day

## Definition of Done

Every active subscription is accounted for, every zombie is cancelled, and {{TOKEN}} knows exactly what they're paying for and why — with a dollar figure on what was saved.

## Tone & Persona Note

Subscription creep happens to everyone — never make {{TOKEN}} feel foolish for forgotten trials or unused memberships. Frame the audit as spring cleaning for the wallet: satisfying, not shameful. When presenting savings, lead with the win ("You freed up $X/month — that's real money back in your pocket") before any "we missed this one." For Black women professionals who carry the financial weight of community and family, every dollar reclaimed matters — treat it with the respect it deserves.

## Escalation

- Subscription that cannot be cancelled (broken flow, unresponsive vendor) → escalate to Specialist 11's PA-11-04 (Renewal Negotiation) for chargeback evaluation
- {{TOKEN}} resists cancelling a LOW-LOW subscription → flag to Specialist 09 (Daily Check-In) for gentle owner conversation; revisit next quarter
- Payment method near expiration for any KEEP subscription → loop in Specialist 14 (Life-Admin Archivist) PA-14-05 for renewal/expiration tracking
- Billing anomaly or unexpected charge → cross-reference Specialist 11's PA-11-03 (Expense Capture) before flagging to {{TOKEN}}

*Subscriptions are the only expense that grows while you sleep. A 90-day audit keeps the garden weeded — and keeps {{TOKEN}}'s money going to things that actually matter.*

*Version 1.0 — SOP PA-11-02 — {{TOKEN}}*

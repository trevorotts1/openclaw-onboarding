# Membership / Continuity Stick + Retention Sequence

**id:** `membership-stick-retention`
**category:** funnel-specific-followups
**aliases:** membership onboarding · continuity stick sequence · member retention automation · subscription churn reduction · membership save sequence · cancellation save flow · monthly re-engagement sequence · annual upgrade sequence

---

## What this runs
Four-phase automation covering the full membership lifecycle: **(A) rapid onboarding** to drive consumption and a quick win before the first renewal, **(B) monthly engagement** touches built around the "something new and scarce each month" stick mechanism Brunson cites in Marketing Secrets Blackbook, **(C) annual upgrade offer** (Brunson: "yearly or lifetime accounts are incredibly effective upsells with continuity programs"), and **(D) the Cancellation Funnel intercept** — the FHC Other Recipe #3, a Survey → Article 2-page funnel that identifies the specific cancel reason and addresses it to save the sale.

The core principle from DotCom Secrets: **bond with the Attractive Character FIRST, then present the continuity program — waiting dramatically increases stick rate** (how long the customer remains an active, paying member).

## TRIGGER
- **Starts when:** membership purchase or trial activation completes (tag `member-active`).
- **Segmentation inputs:** trial vs paid; engaged vs not-engaged in first 7 days; monthly vs annual billing; cancellation intent (exits normal flow → Phase D).
- **Exits when:** member cancels (`member-cancelled` → winback nurture), member upgrades to annual/lifetime (`member-annual`), or opt-out.

## CHANNELS
Email + SMS (SMS on trial-end warning, cancellation intercept, and cancel-save follow-up).

---

## SEQUENCE

### Phase A — Rapid Onboarding (Days 1–7)

Brunson, Marketing Secrets Blackbook Secret 53: *"Simple tweaks to the onboarding process that result in a fraction of a percentage reduction in churn rate equal millions of dollars. We're giving away free domains, adding gamification, and simplifying the process so they have a working funnel within hours instead of days."* Consumption is retention.

| Step | Delay | Subject angle | Body framework |
|------|-------|---------------|----------------|
| **A1 — Welcome + access** | Immediate | "You're in — here's how to get started in the next 10 minutes" | Attractive Character welcome (Soap Opera "Set the Stage" energy). Deliver login + one-click link to the START HERE module. Frame the monthly value hook immediately. |
| **A2 — Consumption nudge** (non-engaged only) | +2 days, if no lesson-start | "Did you get a chance to start? Here's the one thing to do first" | Jim Edwards "If you want X, do this" — one instruction, one first-result, single CTA. Curiosity loop teasing Week 2. |
| **A3 — Quick-win story** | +4 days | "[Name], here's what members get in their first week" | Short Epiphany Bridge testimonial. "One gold nugget" framing (MSB Secret 54): the ONE thing in this program that delivers the clearest breakthrough. Single CTA to Lesson 1 / quick-start track. |
| **A4 — Trial-end warning** (trial only) | 48h before trial ends | "Your membership trial ends in 48 hours" | Remind of what they lose on cancel; one-click continue; annual upgrade option with savings math. Honest timing only. |

---

### Phase B — Monthly Engagement + Re-Engagement

Brunson, MSB Secret 45: *"In order to make continuity work, you need to give them something new (and scarce) each month... it's like, Hey, I wonder what they're going to send me next?"* That curiosity is the stick emotion.

| Step | Timing | Subject angle | Body framework |
|------|--------|---------------|----------------|
| **B1 — Monthly content drop** | 1st of month (or content release date) | "This month's [program name]: [specific topic]" | Curiosity hook + specific outcome ("this month you'll be able to do X"). Link to new module/newsletter. MSB Secret 87 "hook of discovery" tone. |
| **B2 — Mid-month re-engage** (non-openers only) | +14 days from B1 | "Did you miss [month]'s [program name]?" | One sentence + direct link. Daily Seinfeld Sequence tone: conversational, human, one point only. |
| **B3 — Streak/progress note** (engaged members only) | +7 days from B1 | "You're on a [X]-month streak — here's what's next" | Acknowledge engagement, celebrate milestone, tease next month. Identity-building: "people who do this get Y — and you're doing this." Deepens the AC bond. |

---

### Phase C — Annual Upgrade Offer

Brunson, DotCom Secrets: *"We have found yearly or lifetime accounts to be incredibly effective upsells with continuity programs."* MSB Secret 45: FunnelU gives an **extra savings bonus** for going annual — a real exclusive benefit, not fake value.

| Step | Timing | Subject angle | Body framework |
|------|--------|---------------|----------------|
| **C1 — Annual offer** | 30 days after activation (monthly members) | "Save [X amount] — the annual option" | Star/Story/Solution: state savings + real exclusive annual bonus. Honest math: "X monthly × 12 = Y; annual = Z, you save W." Single CTA. |
| **C2 — Annual follow-up** (non-upgraders, 7 days later) | +7 days | "The annual option closes [date] — last chance" | Stealth/Columbo soft-close: "By the way — the annual rate with the bonus is still available through [date]." One paragraph. Honest deadline. Close on the stated date. |

---

### Phase D — Cancellation Save (Cancellation Funnel Intercept)

Funnel Hacker's Cookbook Other Recipe #3: *"The Cancellation Funnel is used when a customer is trying to either refund, cancel a service, or return a product. Many times they are canceling because they don't understand something about what you offer. Doing a quiz first lets you figure out what their specific concern is, and then you can try to save the sale on the next page. This can drastically reduce refunds, cancellations and churn."*

Structure: **Survey Page → Article/Response Page** (2 pages, FHC recipe).

| Step | Timing | Subject angle | Body framework |
|------|--------|---------------|----------------|
| **D1 — Cancel-intent intercept** | Immediate on cancel trigger | "Before you go — can we help?" | Route to the 2-page Cancellation Funnel Survey. Page 1 = quiz: why are you leaving? (branching: too expensive / no time / not what I expected / got what I needed / technical issue / other). |
| **D2 — Quiz-branched save** | Immediate redirect from survey | Personalized per reason (see below) | Page 2 = Article tailored to their specific answer. BRANCHES: (1) Price → pause/downgrade + value-received recap; (2) Time → pause feature + "5-minute module" hook; (3) Not what expected → orientation offer + clarification; (4) Got what I needed → celebrate + tease what's next + pause option; (5) Technical → human support routing. FHC: "show how close they are to gold and remind them of all the work they've already done, which they'll lose if they leave." |
| **D3 — Final save** | +48h from D2 (if still un-cancelled, no re-engagement) | "Your membership is still active — one last thing" | Jim Edwards PAS: problem (why they wanted to leave), agitate (what the exit costs — progress, access, monthly benefit), solve (best save offer from D2). Then: "If you still want to cancel, click here and we'll process it immediately — no questions." Respect their decision. |

After D3 with no action: process cancel, route to post-cancel winback (Daily Seinfeld cadence with occasional offers).

---

## COPY PERSONA + SCRIPT
- **Primary:** DotCom Secrets (Brunson) — Continuity Funnel #3; Soap Opera Sequence ("Set the Stage" welcome); Daily Seinfeld Sequence (ongoing monthly tone); stick-rate / bond-first principle.
- **Support:** Marketing Secrets Blackbook — Secret 45 (Power of Continuity: low-barrier entry, monthly scarce value, annual upgrade); Secret 53 (Consumption: onboarding quick win = retention); Secret 87 (Subscription Selling Secret: "hook of discovery" for monthly content-drop subject lines).
- **Save-email copy:** `jim-edwards-copywriting-secrets` — "If you want X, do this" (onboarding nudges); PAS (cancellation save D3); Stealth/Columbo ("By the way") for the annual offer C2; honest scarcity/urgency discipline throughout.
- **Structural:** `russell-brunson-the-funnel-hackers-cookbook` — Membership Funnel recipe (VSL + Order → Offer Wall → Membership Access Page → Member Area) + Cancellation Funnel (Other Recipe #3: Survey → Article).

---

## GHL BUILD (Skill 44 / caf) — 4 linked workflows

**Workflow 1 — `FSF — Membership: Onboarding (Phase A)`**
Trigger: Order Submitted = membership product (or Tag Added `member-active`)
1. Email + SMS — A1 Welcome + access; tag `member-active`
2. Wait 2 days → If `member-lesson-started`? FALSE → Email A2; TRUE → skip
3. Wait 2 days → Email A3 (quick-win story)
4. If trial: Wait until 48h before trial end → Email + SMS A4

**Workflow 2 — `FSF — Membership: Monthly Engagement (Phase B)`**
Trigger: Cron (1st of month) for all contacts tagged `member-active`
1. Email B1 — Monthly content drop
2. Wait 14 days → If opened/clicked B1? FALSE → Email B2; TRUE → skip
3. If logged in/consumed? TRUE → Email B3 (streak note); FALSE → skip

**Workflow 3 — `FSF — Membership: Annual Upgrade (Phase C)`**
Trigger: Tag `member-active` + Wait 30 days (monthly-billed only, filter out `member-annual`)
1. Email C1 — Annual savings offer; tag `annual-offer-sent`
2. Wait 7 days → If `member-annual`? FALSE → Email C2 (Stealth close); TRUE → end
3. At offer-close date → tag `annual-offer-closed`; remove offer

**Workflow 4 — `FSF — Membership: Cancellation Save (Phase D)`**
Trigger: Tag Added `cancel-intent` (set by cancel-link trigger-link click or cancel-page visit)
1. Pause Phase B workflow for this contact
2. Email + SMS D1 → route to Cancellation Funnel survey page
3. On survey submit → branch by `cancel-reason-*` tag → Email D2 (personalized save)
4. Wait 48h → If re-engaged or `cancel-rescinded`? FALSE → Email D3 (final save)
5. If no action → tag `member-cancelled`; exit all active member workflows; enter winback nurture

**Goal events:** `member-annual` (upgrade), `trial-converted` (trial → paid), `member-cancelled` (cancel), `cancel-rescinded` (save successful).
**Tags:** `member-active`, `member-annual`, `member-cancelled`, `trial-converted`, `member-lesson-started`, `annual-offer-sent`, `annual-offer-closed`, `cancel-intent`, `cancel-reason-price`, `cancel-reason-time`, `cancel-reason-expectation`, `cancel-reason-done`, `cancel-reason-tech`, `cancel-rescinded`.

> The Cancellation Funnel (Phase D) is a 2-page funnel (Survey → Article) — not just an email. The D1 email routes the member to that page. The GHL Pause function on Workflow 2 prevents monthly emails from firing during an active cancel-save. The annual upgrade deadline in C2 must be real and honored.

## FLEXIBILITY NOTE
This template is a **recommended default and a resource — it is not a rule**. Modes:
1. **User has an explicit desire** → do exactly that; this template is an optional reference only, never imposed.
2. **User is unsure** → suggest this proven sequence and why, but let them decide.
3. **User wants it handled** → build from this template.
Always overridable, mixable, customizable, or ignorable. It assists; it does not dominate.

## SOURCE FIDELITY
Funnel Hacker's Cookbook (Membership Funnel recipe; Cancellation Funnel Other Recipe #3: Survey → Article; "quiz identifies specific concern → try to save the sale; drastically reduces refunds, cancellations, and churn") · DotCom Secrets (Continuity Funnel #3: bond with AC first → stick rate; Who/What/Why/How for trial; Star/Story/Solution for paid; yearly/lifetime upsells; Soap Opera + Daily Seinfeld) · Marketing Secrets Blackbook Secret 45 (low barrier, something new + scarce each month, annual upgrade with savings bonus) + Secret 53 (onboarding-driven consumption reduces churn) + Secret 87 (hook-of-discovery for subscription selling) · Copywriting Secrets (PAS, "If you want X", Stealth close, honest scarcity). No invented mechanics.

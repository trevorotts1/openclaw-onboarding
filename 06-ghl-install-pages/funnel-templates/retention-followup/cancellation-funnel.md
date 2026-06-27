# Cancellation Funnel — Skill-6 Template

- **id:** `cancellation-funnel`
- **Category:** retention-followup
- **Library entry:** #20
- **Length class:** Short-form (2 pages — a branching survey + one save page per branch)
- **Aliases:** Cancellation Funnel, Save-the-Sale Funnel, Retention Funnel, Churn-Save Funnel, Refund Deflection Funnel, Cancel-Flow Funnel, Win-Back Save Funnel
- **Source book:** The Funnel Hacker's Cookbook

---

## When to use / trigger criteria

Intercept a customer **at the moment they try to cancel, refund, return, or downgrade.** A quiz pinpoints the exact reason; a tailored save page addresses that specific concern and gives a reason to stay — drastically reducing refunds and churn.

**Goals:** reduce refund/chargeback rate · reduce subscription/membership churn · deflect cancellations by resolving the specific objection · downsell/pause instead of losing the customer · capture structured cancellation-reason data.

**Keywords:** cancellation, cancel flow, save the sale, retention, churn, reduce refunds, refund deflection, win-back, exit survey, downsell to save, pause subscription.

**Signals:** customer clicks Cancel/Refund/Return/Downgrade · high refund or churn is the problem · subscription/membership/continuity losing members · "keep customers from leaving" / "save the sale" · need a "why are you leaving?" survey with a tailored response.

**Anti-signals:** acquiring new leads/buyers (front-end funnel) · nurturing a happy customer (Follow-Up Funnel) · general feedback with no save intent (Ask/Survey Funnel).

---

## Page structure

1. **Cancellation Reason Survey (branching quiz)** — catch the customer at the cancel click and diagnose the single real reason.
   - Empathetic, non-defensive headline ("Before you go — one quick question so we can help").
   - Single-select reason quiz: *Too expensive · No time to use it · Didn't get results · Too complicated · Found another solution · Just exploring · Other.*
   - Conditional logic routes each answer to its matching save page. One tap, no friction. Reason captured as a tag/field for reporting.

2. **Personalized Save Page (one variant per branch)** — address the exact concern with empathy + reframe + a reason to stay.
   - Empathy open naming their concern (StoryBrand: acknowledge the problem, brand = guide).
   - Targeted reframe / false-belief break (Epiphany Bridge mini-story or proof).
   - Stay-incentive matched to the reason; short relevant proof.
   - Primary CTA: **"Keep my account & get [bonus]"**. Secondary/last-resort: confirm cancel — but downsell/pause is offered first.

   **Branch save-plays:**
   - *Too expensive* → downsell to lower tier / annual discount / pause; ROI reframe.
   - *No time* → pause/freeze, quick-start path, or concierge onboarding.
   - *Didn't get results* → onboarding call, success roadmap, extended-access guarantee + case study.
   - *Too complicated* → free/done-for-you setup, simplified plan, tutorial bundle.
   - *Found another solution* → differentiation reframe + matching offer / unique bonus.
   - *Just exploring / Other* → soft re-engagement, extended trial, route back into the Follow-Up Funnel.

---

## Copy framework

- **Primary persona:** **The Attractive Character as empathetic Guide** — brand voice, but in service of the customer. Understanding and helpful, never defensive or guilt-tripping.
- **Primary script:** **StoryBrand SB7** — customer is the hero about to fail; brand is the guide with a plan; staying is the CTA that avoids the failure of leaving.
- **Secondary scripts:** **Epiphany Bridge** (per-branch reframe of the false belief behind the objection) · **Copywriting Secrets** (objection-crushing + "reason why" formulas, risk-reversal/guarantee, downsell pitch) · **Expert Secrets false-belief pattern** (vehicle/internal/external belief per reason).
- **Rule:** one objection → one page → one tailored offer. Lead with empathy, never argue. Stakes = the result they'll miss by leaving. Stay-CTA gets prominence, but the cancel path always stays available (never trap them).

---

## GHL build notes (Skill 6 + Skill 44)

- **Skill 6 role:** instantiates a 2-step funnel — a survey/quiz step and a dynamic save step whose content swaps per branch (N save pages, or one page with conditional sections).
- **Skill 6 pages:** Page 1 Reason Survey · Page 2 Save page(s) (one per reason, or single page with conditional blocks driven by the captured reason).
- **Skill 44 widgets:**
  - Survey/Quiz widget — single-select reasons with conditional routing; answer mapped to a contact field/tag.
  - Calendar widget on the *no results* / *too complicated* branches for a save/onboarding call.
  - Order/downsell form widget for the *too expensive* branch (lower-tier/discount), plus pause/freeze where billing supports it.
- **Automations:**
  - Trigger: cancel/refund/downgrade button enters the contact and tags `cancel-intent`.
  - Branch on survey answer → apply reason tag → route to matching save page.
  - On **stay** CTA: tag `saved`, grant the bonus/discount/pause, remove `cancel-intent`, optionally re-enroll in the Follow-Up Funnel.
  - On **confirmed cancel**: process cancellation, tag `churned`, enroll in a win-back sequence.
  - Reporting view: reasons + save-rate per branch to fix upstream churn causes.
- **Notes:** both pages instant-loading and mobile-first (they appear mid-frustration); surface downsell/pause **before** the final cancel confirmation on every branch.

# Viral Front-End Funnel

*Skill-6 funnel template — group: `traffic-advanced` — generated 2026-06-26*
*Source: BRUNSON-FUNNEL-LIBRARY.md entry #32 (Traffic Secrets)*

## Identity
- **id:** `viral-front-end`
- **name:** Viral Front-End Funnel
- **aliases:** Viral Funnel, Referral Front-End, Invite-to-Unlock Funnel, Viral Loop Funnel
- **category:** Traffic / Advanced — Viral Acquisition
- **length class:** short-form (2-3 pages + referral loop)
- **buildable:** YES

## When To Use / Trigger Criteria
**Goals (request shapes that should match):**
- Engineer a front-end with built-in referral mechanics so each sign-up is incentivized to recruit more sign-ups (target viral coefficient > 1).
- Grow a list explosively for a launch, waitlist, giveaway, or pre-launch (Brunson's example: sign up + share 5 invite codes -> 1.6M sign-ups in six weeks).

**Keywords:** `viral`, `referral`, `invite friends`, `waitlist`, `share to unlock`, `giveaway`, `viral coefficient`, `k-factor`, `refer to move up the list`, `early access`, `pre-launch list explosion`

**Signals:**
- Client wants rapid, low-cost list growth around a launch or waitlist.
- There is a compelling free/early-access reward worth sharing for.
- The offer has natural social spread (broad appeal, status, scarcity).

**Anti-signals (do NOT match / route elsewhere):**
- High-ticket niche B2B where the audience won't share publicly.
- No reward valuable enough to motivate sharing — referral mechanics fall flat.

## Page Structure
### 0. (Loop entry) Referred-Friend Landing
*Purpose:* Where invited friends land — same registration page, attributed to the referrer to close the loop.

*Key elements / blocks:*
- Pre-framed headline ('[Name] invited you')
- Same email capture
- Referral attribution captured on submit

### 1. Registration / Squeeze Page
*Purpose:* Capture the email with a curiosity-driven, big-promise hook for the free reward or early access.

*Key elements / blocks:*
- Big-promise headline + curiosity subhead
- Single email field (zero nav, zero distraction)
- Scarcity/exclusivity framing (waitlist, limited spots, launch countdown)
- Social proof / live sign-up counter

### 2. Share / Unlock Page (the viral engine)
*Purpose:* Immediately give the new subscriber a personal share link and make sharing the path to the reward.

*Key elements / blocks:*
- Personal unique referral link + one-click share buttons (SMS, WhatsApp, X, FB, copy-link)
- Progress tracker: 'Invite 5 friends to unlock ___' with live referral count
- Tiered rewards ladder (1 referral = X, 3 = Y, 5 = Z / move up the waitlist)
- Epiphany-Bridge micro-story explaining WHY sharing helps them + their friends

### 3. Reward / Confirmation Page (delivered on threshold)
*Purpose:* Deliver the unlocked reward/early access and keep the loop alive.

*Key elements / blocks:*
- Reward delivery (download, access code, position confirmation)
- Renewed CTA: keep sharing for the next tier
- Bridge into the core/front-end offer or value ladder

## Copy Framework
**Primary persona:**
- **expert** — Russell Brunson — Expert Secrets persona (The Attractive Character / Expert): Epiphany Bridge story script, the Big Domino, false-belief patterns (vehicle/internal/external), Perfect Webinar, The Stack and Close, Hook-Story-Offer.

**Supporting personas:**
- **edwards** — Jim Edwards — Copywriting Secrets persona (The Copy Mechanic): the Big Promise headline formulas, fascination/curiosity bullets, the order-bump and OTO close formulas, the 'one-sentence' hook.
- **strategist** — Russell Brunson — Traffic Secrets persona (The Traffic Strategist): Dream 100, Hook-Story-Offer for native content, the Funnel Hub + Shadow Funnel capture doctrine.

**Scripts:**
- Hook-Story-Offer + curiosity Big-Promise headline (Jim Edwards) for the registration squeeze.
- Epiphany Bridge micro-story on the share page to make the 'why share' emotional, not transactional.
- Scarcity + status framing on the rewards ladder (move up the list / exclusive access).

*Notes:* The reward must feel worth more than the social cost of sharing. Make the share CTA the single dominant action on page 2 — the loop dies if sharing is optional or buried.

## GHL Build Notes (Skill 6 + Skill 44)
**Pages (Skill 6):**
- Build as a GHL Funnel: Step 1 Registration -> Step 2 Share/Unlock (thank-you step) -> Step 3 Reward delivery.
- Referred-friend traffic hits Step 1 with a referral query param captured into a hidden field.

**Skill 44 widgets (forms / calendars / surveys):**
- Skill 44 Form widget: email capture on Step 1 with a hidden 'referrer_id' field.
- Skill 44 cannot natively render share-to-unlock loops — embed a custom HTML/JS share block OR integrate an external referral tool (e.g. a referral SaaS) on Step 2.

**Automations / workflows:**
- Workflow: on signup -> generate/assign a unique referral code (custom value) -> email the share link.
- Workflow: referral count threshold met -> tag 'unlocked' -> send reward email + grant access.
- Workflow: referred-friend signup -> increment referrer's referral count custom field.

*Build notes:* HONEST LIMITATION: GHL has no native viral/referral primitive. Skill 6 builds the 3 funnel steps; Skill 44 builds the opt-in form; the referral counting/unlock requires custom fields + workflows (or an external referral platform webhooked into GHL). Document this in the build ticket.

## Metrics To Calibrate
- Viral coefficient (k-factor)
- Invites sent per signup
- Referred-signup conversion rate
- Unlock-threshold completion rate
- Cost per acquired email

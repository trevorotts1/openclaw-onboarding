# The 3 Closes Follow-Up Funnel — EMOTION → LOGIC → FEAR

**id:** `three-closes-master-followup` · **category:** sales-close-sequences
**Aliases:** 3 closes, three closes framework, emotion-logic-fear, follow-up funnel, communication funnel, 30-day nurture-to-close
**Source:** DotCom Secrets (Brunson — Follow-Up Funnels + 3 Closes) · Expert Secrets (Epiphany Bridge + Stack) · Marketing Secrets Blackbook (customized follow-up funnels, urgency/scarcity, Stack Don't Switch) · Lead Funnels Swipe File (multi-channel) · Copywriting Secrets (Edwards)

> **The master close architecture.** A single offer is sold **three different ways in sequence** because different buyers respond to different closes:
> - **EMOTION** converts the emotionally-driven (story / Epiphany Bridge) — makes them *want* it.
> - **LOGIC** converts the analytical justifier (Stack / ROI / proof / guarantee) — makes yes the *smart* choice.
> - **FEAR / URGENCY** converts the procrastinator at the deadline (scarcity / FOMO) — makes *now* the only time.

---

## TRIGGER
- New opt-in (front-end), buyer ascending the value ladder, `interested-[offer]` Seinfeld click, or webinar/VSL watched.
- **Exit:** purchase → buyer onboarding + next rung; end of Fear phase, no buy → long-term Seinfeld nurture.

## CHANNELS
Email (core) · SMS (Logic recap + Fear deadline) · Facebook Messenger (mirror key beats) · desktop push · retargeting ads · direct mail (high-ticket only). *Brunson's multi-channel follow-up funnel.*

## CADENCE
30–60 days. **Emotion** days 0–5 · **Logic** days 6–12 · **Fear/Urgency** final 24–72h window.

---

## THE SEQUENCE

### PHASE 1 — EMOTION (days 0–5)
| Step | Beat | Persona |
|------|------|---------|
| 1 | Run the **Soap Opera Sequence** (Set Stage → Drama/Wall → Epiphany → Hidden Benefits → Urgency/CTA) | Epiphany Bridge / Attractive Character |
| 2 (Day 5) | Bridge email: recap transformation → "let me show you exactly what you get and why it pays for itself" | Edwards transition |

### PHASE 2 — LOGIC (days 6–12)
| Step | Beat | Subject angle | Persona |
|------|------|---------------|---------|
| 3 (Day 6) | **The Stack as logic** — each deliverable + standalone value, accumulate total, reveal lower price ("dollars for dimes") | "Here's everything you get (real value: $X)" | Brunson Stack + Edwards Ultimate Bullet Formula |
| 4 (Day 8) | **ROI / cost-of-inaction math** + comparison vs. DIY / do-nothing / competitor method (never named) | "The math nobody does (cheaper to buy than to wait)" | Edwards PAS on inaction; good-vs-bad negative |
| 5 (Day 10) | **Proof + Guarantee** — testimonials, case studies, data, risk-reversal; FAQ answers top 2–3 objections | "Still on the fence? Read this" | Edwards proof + guarantee; Brunson false-belief handling |

### PHASE 3 — FEAR / URGENCY (final 24–72h)
| Step | Beat | Subject angle | Persona |
|------|------|---------------|---------|
| 6 (Day 12) | Bridge: announce the deadline / closing window (email + SMS) | "Heads up: this closes [date]" | Brunson urgency intro |
| 7 (T-48h) | 48-hour warning; restate offer + three scarcity levers (time/price/quantity) | "48 hours left" | Blackbook Secret 51 |
| 8 (T-24h) | 24h / fast-action bonus expiring; cost-of-inaction (what they lose) | "Tomorrow this is gone" | Edwards FOMO + regret future-pacing |
| 9 (T-3h & T-1h) | Final hours — "doors closing," last call. Two short emails + SMS at 1h | "3 hours" / "Final call — closing now" | Brunson takeaway/FOMO (honored) |
| 10 (post-close) | Branch: buyers → onboarding + ascend; non-buyers → optional one downsell → Seinfeld nurture | — | Stack Don't Switch ascension |

---

## COPY PERSONA & SCRIPT
- **Primary:** Brunson — **3 Closes** + Attractive Character + **Stack**.
- **Supporting:** Edwards — Problem/Agitate/Solve, Before/After/Bridge, the 13-part offer block, proof, single CTA.
- **The three close modules:**
  - *Emotion* = story (Soap Opera / Epiphany Bridge) → make them WANT it.
  - *Logic* = the Stack + the math + proof + guarantee → make yes SMART (and spouse/boss-approvable).
  - *Fear* = scarcity (limited time/price/quantity) + cost of inaction → make NOW the only time.

---

## GHL BUILD (Skill 44 → GoHighLevel)
**Workflow:** `3 Closes Master — Emotion → Logic → Fear` (one workflow, three labeled sections).

1. **Trigger:** `Tag Added = start-3closes-[offer]` (from opt-in, webinar-attended, or Seinfeld interest click). Filter: not `buyer-[offer]`.
2. **Emotion** = Soap Opera steps (Day 0–4) + bridge (Day 5).
3. **Logic** = Stack email (Day 6) + ROI/comparison (Day 8) + Proof/Guarantee (Day 10), each with Buy CTA.
4. **Fear** = deadline announce (Day 12) + T-48h + T-24h + T-3h + T-1h — **emails + SMS off a fixed campaign-deadline custom field** so the on-page countdown timer matches every channel.
5. **Multi-channel mirrors:** FB/IG DM action on Stack + Final-Call; desktop push Day 6 & T-24h; sync a retargeting audience.

**If/Else & Goals:**
- **Purchase Goal** (`buyer-[offer]`) anywhere → exit, enroll buyer onboarding + next value-ladder offer, STOP close emails.
- Stack email opened, no click → resend w/ new subject + one hero benefit. Sales page clicked 2+ no buy → tag `hot-no-buy`, prioritize SMS in Fear phase.
- **Checkout started, not completed** → fire `abandoned-cart-recovery` immediately (overrides schedule).
- Post-close: non-buyers → one optional downsell → `seinfeld-daily-sequence`.

**Honor the deadline:** when the cart closes in GHL, the offer/price genuinely changes.

## INTEGRITY GUARDRAILS
Same true offer sold three ways (never inflate to fit a close) · Stack values must be defensible · the Fear-phase deadline MUST be real (cart truly closes, bonus truly expires).

## KPIs
Conversion **by phase** (which close won each buyer) · overall conversion · Fear-phase revenue concentration (usually the biggest beat) · cart-close spike · revenue per lead over 30–60 days · ascension rate.

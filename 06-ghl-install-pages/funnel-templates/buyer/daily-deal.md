# Daily Deal Funnel

**id:** `daily-deal` · **category:** Buyer Funnel · **group:** buyer · **length:** short-form · **library ref:** #13

**Aliases:** Daily Deal Funnel · Groupon-Style Funnel · LivingSocial-Style Funnel · Deal of the Day Funnel · Flash Deal Funnel

**Source books:** The Funnel Hacker's Cookbook

---

## When to use / trigger criteria

A **deeply discounted front-end offer** to acquire new customers (the Groupon/LivingSocial model). The thank-you page encourages buyers to **share the same deal** with their network, creating built-in viral distribution. Use when the goal is fast customer acquisition + organic spread from an irresistible, time-boxed discount.

**Goals:** acquire many new customers fast with a deep discount · trigger viral/word-of-mouth distribution · move excess inventory / fill capacity · seed a buyer list cheaply with urgency.

**Keywords:** daily deal · deal of the day · flash sale · groupon style · deep discount · limited time deal · today only · share the deal · refer a friend deal · viral discount.

**Signals:** steep/limited-time discount (not a free sample) · goal includes sharing/referral/viral spread · time-boxed urgency is core · local service or product with capacity to fill.

**Route elsewhere when:** free/just-shipping front end → 2-Step Tripwire · recurring → Membership/Continuity · long convincing required → VSL / Sales Letter · free physical book → Book Funnel.

---

## Page structure (2 pages)

1. **Deal Order Page** — One irresistible, deeply discounted, time-boxed deal; convert fast on a simple order form.
   - Deal headline with savings framed (was/now); single hero offer + short benefit bullets; prominent **countdown timer** (today-only urgency); scarcity (limited quantity / claimed-count); low-friction order form; trust badges + a couple of testimonials.
2. **Social Share Thank-You Page** — Confirm purchase and immediately incentivize sharing the same deal (viral loop).
   - Thank-you + deal-claimed confirmation; "share this deal with friends" incentive (unlock bonus / give-a-discount); **pre-filled referral/share links** (Facebook, X, WhatsApp, email, copy-link); personal referral link with tracking; delivery/redemption instructions.

---

## Copy framework

- **Primary persona — `edwards-copywriting-secrets`** (Copywriting Secrets): writes the high-urgency deal copy — urgency + scarcity + deadline formulas, deep-discount/value framing, short punchy benefit copy, and the share-to-unlock incentive.
- **Sales script — Hook / Story / Offer (compressed) + urgency/scarcity close** (Lead Funnels): fast hook, tight offer, minimal story; urgency does the closing.
- **Supporting — `russell-brunson-lead-funnels`** (Lead Funnels): Hook/Story/Offer + unique-mechanism — frames the deal hook and the why-this-is-special angle.
- **Supporting — `leland-brand-mapping-strategy`** (The Brand Mapping Strategy): brand-voice consistency (Be/Do/Have, Signature Story) — keeps the discount on-brand so it builds equity instead of cheapening it.
- **Supporting — `miller-building-storybrand`** (Building a StoryBrand): SB7 Call-to-Action / invite-others framing — writes the share-the-deal CTA so the buyer becomes a guide inviting friends.

Keep everything short — urgency and the deal do the selling.

---

## GHL build notes (Skill 6 + Skill 44)

**Funnel type:** GHL Funnel, 2 steps.

**Skill 6 steps:** Create Funnel → name with client prefix → Create. Add New Step ×2: (1) Deal Order Page (countdown timer via custom HTML/JS in the code block), (2) Social Share Thank-You Page (share buttons + pre-filled referral links).

**Skill 44 widgets:** single-step Order Form on Step 1 · Tags + referral/follow-up workflow · optional referral/affiliate tracking links.

**Products (GHL Payments):** discounted deal product.

The countdown timer and social-share/referral buttons are custom HTML/JS in the code-block element; build heavier versions in Vercel and embed. Pre-build the order form, tags, and referral tracking via Skill 44 (or GHL MCP/API). The viral loop lives on the thank-you page: pre-fill the share links with the buyer's personal referral code.

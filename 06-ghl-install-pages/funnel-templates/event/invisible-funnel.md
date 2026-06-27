# Invisible Funnel

**id:** `invisible-funnel` · **category:** Event Funnels · **library ref:** #14 · **length:** medium-form
**aliases:** Invisible Funnel Webinar, Pay-If-You-Like-It Funnel, Try-Before-You-Buy Webinar
**source books:** The Funnel Hacker's Cookbook, DotCom Secrets · **origin:** Daegan Smith

## When to use / trigger criteria
Use when a paid training/event should be framed as **free upfront** — the attendee registers and enters a credit card but is only charged if they liked the content — then a high-ticket backend is soft-sold.

- **Goals:** maximize registrations by removing the paywall; convert on content quality; feed a high-ticket backend application.
- **Keywords:** "invisible funnel", "pay if you like it", "only charged if", "try before you buy", "risk-free training", "card now charge later".
- **Signals:** client says "pay only if they get value"; strong content confidence; wants volume + revenue; plans a high-ticket coaching/consulting backend.
- **Anti-signals:** pure free lead magnet (use Squeeze/Lead Magnet); normal paid checkout (use Webinar Funnel); client won't store cards for delayed billing.

## Page structure
1. **Registration Page (conditional billing)** — Big-Promise headline; plain-language billing explainer ("do nothing and your card is billed in 2 days; didn't love it, tell us and owe nothing"); fascination bullets teasing the 3 secrets; risk-reversal block; registration + payment form. *Widgets: registration form, delayed-billing order form, guarantee block.*
2. **Confirmation / Indoctrination Page** — access + add-to-calendar; short indoctrination video; restate of pay-if-you-like terms; what to bring. *Widgets: add-to-calendar, reminder opt-in.*
3. **Event Delivery Page** — live/prerecorded event embed; Perfect Webinar body (Intro → 3 Secrets → Stack → soft transition); live chat; soft-sell CTA to the application. *Widgets: video embed, live chat.*
4. **Charge-or-Cancel + High-Ticket Application Page** — "loved it? do nothing / not for you? cancel" branching; soft-sell application CTA; qualification application form; calendar booking for the closer call. *Widgets: cancel/keep survey, application form, calendar booking.*

## Copy framework
- **Primary persona:** `perfect-webinar` (Expert Secrets) — the event body is a Perfect Webinar (Intro/Hook → 3 Secrets → The Stack → Close).
- **Supporting:** `copywriting-secrets` (registration Big-Promise headline + bullets + the conditional-billing risk-reversal), `epiphany-bridge` (indoctrination/origin story), `star-story-solution` (high-ticket take-away application).
- The conditional-billing language is the load-bearing copy element — keep it transparent and repeated on pages 1, 2, 4. Trust is what makes attendees allow the charge.

## GHL build notes (Skill 6 + Skill 44)
- **Skill 6** builds 4 funnel pages and wires the payment element for **authorize-now / capture-later (delayed billing)**.
- **Skill 44 widgets:** registration form (name/email/phone); delayed-capture order form; add-to-calendar + reminders; multi-field application form; calendar booking widget for the closer; cancel/keep survey.
- **Automations:** tag on register + pre-event reminders; 2-day post-event timer → capture charge unless `invisible-cancel` tag; cancel link voids capture; on application submit → notify closer + confirm booking.
- **Products:** event price (conditional capture) + high-ticket backend (sold by application/phone).

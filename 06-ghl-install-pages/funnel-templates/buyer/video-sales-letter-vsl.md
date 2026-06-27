# Video Sales Letter (VSL) Funnel

**id:** `video-sales-letter-vsl` · **category:** Buyer Funnel · **group:** buyer · **length:** medium-form · **library ref:** #10

**Aliases:** VSL Funnel · Video Sales Letter · Sales Video Funnel · Auto-Play VSL Funnel

**Source books:** The Funnel Hacker's Cookbook · Marketing Secrets Blackbook · Expert Secrets

---

## When to use / trigger criteria

A **video makes the primary sale** on a landing page. The Add-to-Cart button can be hidden until after the price reveal to force watch-through. Includes an order form with a bump and a post-purchase OTO/downsell sequence. Use when video out-converts written copy for the audience/offer, or when the story is best carried on camera.

**Goals:** sell a product where a single sales video does the convincing · force watch-through with a timed/hidden CTA reveal · maximize AOV with bump + OTO after the video sale · run a high-converting front or mid-ladder buyer offer.

**Keywords:** VSL · video sales letter · sales video · auto-play video page · timed CTA reveal · hidden buy button · watch this video · video pitch.

**Signals:** client has/wants a sales VIDEO as the primary pitch · audience responds to video over long copy · offer benefits from a delayed CTA reveal · story-/demonstration-/face-to-camera pitch.

**Route elsewhere when:** audience prefers to read → Sales Letter Funnel · free/just-shipping front end → 2-Step Tripwire (a 5-min VSL can still be the page video) · live/registered event → Webinar Funnel · recurring core → Membership/Continuity.

---

## Page structure (4 pages)

1. **VSL Sales Page** — Autoplay Video Sales Letter makes the sale; the CTA/order button reveals on a timer (after the price reveal) to force watch-through; the order form with bump converts.
   - Curiosity headline above the player; autoplay VSL embed; **timed CTA reveal (hidden until price reveal)**; order form with **order bump**; guarantee/testimonials/FAQ below the fold for skimmers; optional transcript toggle.
2. **OTO / Upsell Page** — One-click upsell (next tier, bundle, or done-for-you) immediately after the video sale.
   - Interrupt headline; upsell mini-VSL or short copy; one-click accept + decline link.
3. **Downsell Page** — Recover OTO decliners with a lower-priced or payment-plan version.
   - Downsell offer; one-click accept + decline link.
4. **Confirmation / Thank-You Page** — Confirm purchase, deliver access, bond, bridge to the next offer.
   - Order summary + access; Attractive-Character welcome; next-step CTA into the value ladder.

---

## Copy framework

- **Primary persona — `edwards-copywriting-secrets`** (Copywriting Secrets): writes the VSL script and page copy — Copywriting Secrets has a dedicated VSL chapter (headline, benefit-stacking, objection-preemption) plus the bump/OTO copy.
- **Video script — 5-Minute Perfect Webinar** (under $100) or **full Perfect Webinar** (higher ticket), with an **Epiphany Bridge** story (Expert Secrets): intro + story + one/three secrets + stack/close.
- **Supporting — `russell-brunson-the-funnel-hackers-cookbook`** (The Funnel Hacker's Cookbook): VSL recipe — hidden/timed CTA reveal, order-form + bump + OTO placement.
- **Supporting — `brunson-marketing-secrets-blackbook`** (Marketing Secrets Blackbook): Attractive Character + Epiphany Bridge — shapes the on-camera story and bonding voice.

The CTA stays hidden until the price reveal in the video.

---

## GHL build notes (Skill 6 + Skill 44)

**Funnel type:** GHL Funnel, 4 steps.

**Skill 6 steps:** Create Funnel → name with client prefix → Create. Add New Step ×4: (1) VSL Sales Page, (2) OTO/Upsell, (3) Downsell, (4) Confirmation/Thank-You.

**Skill 44 widgets:** Order Form + Order Bump on Step 1 · One-Click Upsell on Steps 2 and 3 · Tags + purchase-trigger workflow.

**Products (GHL Payments):** core product · OTO · downsell.

The timed CTA reveal needs custom JS, so **build the VSL page in Vercel and pull into the GHL step via embed link** (the code-block element alone may not render the timed-reveal cleanly). Pre-build the order form, tags, and products via Skill 44 (or GHL MCP/API) and embed them. Host the video on Vimeo/Wistia/YouTube and embed.

# Storefront Funnel

**id:** `storefront` · **category:** Buyer Funnel · **group:** buyer · **length:** short-form (hub) · **library ref:** #21

**Aliases:** Storefront Funnel · Product Gallery Funnel · Window-Shopping Funnel · Funnel Storefront · Catalog Funnel

**Source books:** The Funnel Hacker's Cookbook

---

## When to use / trigger criteria

All products sit together **like window shopping**, with each product linking into its **own dedicated sales funnel** rather than a generic product page or shared cart. Mimics a traditional ecommerce site but routes every visitor into a proper funnel. Use when a client has multiple products/offers and wants one branded hub where each item still gets the full funnel treatment.

**Goals:** present multiple products/offers in one branded gallery · route every product click into its own dedicated funnel (no shared cart) · give an ecommerce "shop" feel while preserving funnel conversion · organize offers along the value ladder for browsing buyers.

**Keywords:** storefront · store · shop page · product gallery · catalog · all products · window shopping · multiple products · product cards.

**Signals:** client has multiple distinct products to show together · wants a "shop"/"store" feel but with funnels, not a cart · needs a hub to link out to several individual funnels · browsing buyers choosing among offers.

**Route elsewhere when:** single product/offer → use that product's VSL or Sales Letter Funnel directly · brand-hub website with blog/PR/social → Funnel Hub (other group) · free/just-shipping single front end → 2-Step Tripwire / Book Funnel · recurring-only offer → Membership/Continuity.

---

## Page structure (1 gallery hub + N linked product funnels)

1. **Storefront Gallery Page** — Display all products together as browsable cards (window shopping). Each product card links **out** to its own dedicated funnel (VSL or Sales Letter), never to a shared cart.
   - Brand header + light store-like navigation; grid of **product cards** (image, name, one-line benefit, price/anchor); each card CTA links to that product's dedicated funnel; optional value-ladder ordering (entry → premium) / categories; brand signature-story / trust band; **no shared cart**.
2. **[Per-product] Dedicated Product Funnel (separate template)** — Each card lands the visitor in its **own** funnel built from a buyer-group template (`video-sales-letter-vsl` or `sales-letter`), with that funnel's order form, bump, and OTOs; inherits the storefront's brand voice.

---

## Copy framework

- **Primary persona — `leland-brand-mapping-strategy`** (The Brand Mapping Strategy): governs brand architecture across the storefront — consistent brand voice, Signature Story, Be/Do/Have depth — so all product cards feel like one coherent brand.
- **Sales script — StoryBrand SB7 per product card (compressed)** (Building a StoryBrand): each card is a micro-narrative — customer as Hero, product as the Plan/next step — in one line, so the browser clicks into the right funnel.
- **Supporting — `miller-building-storybrand`** (Building a StoryBrand): SB7 one-liner / BrandScript per card — writes each card as a clear customer-as-hero micro-narrative.
- **Supporting — `edwards-copywriting-secrets`** (Copywriting Secrets): product-card microcopy — benefit-first names, one-line hooks, button copy.
- **Supporting — `brunson-marketing-secrets-blackbook`** (Marketing Secrets Blackbook): Value Ladder ordering — arranges the storefront low-to-high so browsing buyers see the ladder.

The deep selling copy lives in each linked funnel (VSL or Sales Letter template), not on the storefront itself.

---

## GHL build notes (Skill 6 + Skill 44)

**Funnel type:** GHL Funnel or Website (1 gallery page) + N separate product funnels.

**Skill 6 steps:** Create Funnel/Website → name with client prefix → Create. Build Page 1 = Storefront Gallery Page (product-card grid with outbound links). For each product, build a **separate** funnel from the VSL or Sales Letter buyer template and link its card to it.

**Skill 44 widgets:** optional opt-in/newsletter form on the gallery footer · optional tags on product-card click-through · each linked product funnel uses its own template's Skill 44 widgets (order form, bump, one-click upsell).

**Products (GHL Payments):** no shared cart on the storefront; each product is sold in its own funnel via that funnel's product.

The storefront is a hub: build the gallery as a GHL page (custom HTML grid in the code block, or a Vercel-built gallery pulled in via embed link) whose product-card buttons link **out** to each product's own funnel. Do **not** wire a shared cart. Build each product funnel separately from the buyer-group VSL or Sales Letter template. Pre-create any opt-in form/tags via Skill 44 (or GHL MCP/API). Store product images in GHL media storage via Skill 44 / GHL MCP / API.

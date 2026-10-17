# Layout and Clean Copy Profiles — Skill 82 (S82-04)

**Scope:** the terminal Signature Launch thank-you page (page role
`thank_you`), rendered by `scripts/render_thank_you.py` from the order
view produced by `scripts/thank_you_resolver.py`. Per packet doc 16
section 1, S82 owns the shared **Order summary / access blocks**
component: input is the resolved order view (verified purchases only,
never URL claims); output is the accessible summary table and the
per-entitlement access blocks specified below. Consumers: the final
thank-you page and approved confirmation states only.

This component has a version (Skill 82 v0.3.0), an input schema
(`schemas/order-view.schema.json`), the DOM contract in section 2 of
this document, accessibility expectations in section 5, and tests
(`tests/test_render.py`). The layout in this document is the proposed
Skill 82 contract (packet doc 12 section 1): the owner supplied no
precise thank-you layout, and nothing here is copied from the upsell /
downsell copy IP.

## 1. Page job

Confirm and deliver exactly what the customer actually purchased, its
actual charges and terms, and what happens next. Reassurance and
access, at reduced promotional pressure (doc 12 section 4; doc 16
section 5: "thank-you prioritizes reassurance and access"). This page
sells nothing: see `references/no-pitch-policy.md`.

## 2. Layout contract, top to bottom

### 2.1 First viewport (header) — all four elements, always, in order

1. **Confirmation status, honestly worded.** The resolver's confirmation
   headline (`confirmation.headline`), as the page `<h1>`, plus a visible
   status label: `Confirmed`, `Partly pending`, `Pending`, or
   `Needs attention`. A pending or failed item anywhere forbids
   "You are all set" — in the headline, the status label, and anywhere
   else on the page.
2. **Concise reassurance.** The standing reassurance line (section 3,
   profile-independent): the page confirms exactly what was purchased,
   nothing more was added, and there is nothing else to buy here.
3. **Primary next action.** The first granted access block, rendered as
   the primary button ("Start here: {purchased item name}",
   `data-cta-class` = that block's access classification). If no access
   is granted yet, the primary action is the reconciliation/support
   route instead (see `references/states.md`) — never a purchase.
4. **Order reference.** "Order reference: {order number}" in text,
   from the verified snapshot's native order reference. Never a guessed
   or sequential ID, and never enough on its own to open the receipt
   (doc 12 section 5).

The header is followed by an `aria-live="polite"` status region
(`role="status"`) carrying the same confirmation state, so assistive
technology announces the outcome without reading the whole page.

### 2.2 Order summary (the S82 shared component, part 1)

An accessible, real **table** — never an image of a receipt, never a
screenshot, never text baked into a graphic (doc 12 section 8):

- `<caption>` naming the order reference and stating the amounts are
  the actual charges from the verified purchase record.
- One row per purchased item, in resolver slot order (main, bump,
  upsell_1, downsell_1, upsell_2): item name (row header), per-item
  status label (section 4), billing line (section 2.4), and the actual
  unit amount formatted from integer minor units.
- A `Total paid` row from the verified paid total. When a pending total
  exists, a separate `Pending (not yet confirmed)` row — pending money
  is never folded into the paid total or presented as charged and
  confirmed.

Only items in the verified order view appear. Nothing unpurchased,
nothing from the list of pages visited, nothing grouped in from another
journey by shared email (doc 12 sections 3 and 5).

### 2.3 Access / next-step blocks (the S82 shared component, part 2)

One block per **granted** access block in the view, keyed to the
purchased entitlement ID and its S44 fulfillment state:

- Block heading: the purchased item's name.
- Action: a real link to the official protected delivery destination,
  labeled by its classification ("Access: …", "Download: …",
  "Schedule Included Service: …"), carrying
  `data-cta-class` = the CTA classification (section 3.3).
- A paid item whose fulfillment has no delivery URL yet renders the
  honest fallback text (access is being prepared; it also arrives by
  email; contact support) — never a placeholder or guessed URL.
- No block exists for a pending, failed, refunded, or unpurchased
  entitlement. A block for an entitlement not in the view is a defect,
  not a feature.

Then **What happens next**: delivery expectations in plain text —
confirmed access is ready now and also arrives by email (so leaving
the page never strands the customer; fulfillment does not depend on
reaching this page, doc 12 section 6); each pending item is named with
"delivery starts when its payment is confirmed — you do not need to
buy it again"; each failed item is named with "no charge and no access
for it; your confirmed items are not affected".

### 2.4 Billing schedule

Shown per item in the summary's Billing column, from the item's
verified `billing` terms only:

- One-time: `One-time charge`.
- Recurring: `Recurring — every {interval}`, plus each verified
  schedule entry (label/date and amount) where the snapshot carries a
  schedule. Trial terms and next-charge dates are shown only when the
  verified snapshot carries them; they are never invented to fill the
  space. A recurring charge that cannot be shown completely is an
  automatic failure (doc 16 section 8: unsupported or concealed
  recurring charge).

### 2.5 Support path

Closing section, always present: how to get help with this order
(support CTA, classification `support`), and purchase management
(`manage_purchase` CTA: receipts, billing portal, subscription
management for the existing purchase). Copy must state that the buyer
never needs to share card details with support. Support is also the
fallback route in every delayed/error state (`references/states.md`).

### 2.6 What never appears

- No new-offer section, recommendation, "complete your setup" step, or
  "one more thing" (no-pitch policy). The resolver's `recommendations`
  list must be empty and the renderer renders nothing from it.
- No share/community action unless it is actually part of the approved
  fulfillment plan with a supplied, valid destination (doc 12
  section 4) — rendered, if ever, as a `noncommercial_next_step`.
- No price, name, or status for anything not in the verified view.
- No payment-card data, in any form, anywhere in the HTML.

## 3. Clean copy profiles

Copy profiles are selected by the resolver's confirmation status, not
hand-authored per page. Wording patterns below are the approved
patterns; `{name}` is a purchased item's verified display name.

### 3.1 Paid — `confirmation.status: confirmed` (every item paid)

- Headline (resolver): "You are all set. Your purchase is confirmed."
  This is the **only** profile that may use "You are all set".
- Status label: `Confirmed`.
- Reassurance: standing line (2.1.2).
- Next steps: access ready now + email fallback (2.3).
- Tone: plain, warm, finished. No urgency, no scarcity, no next offer.

### 3.2 Partially pending — `partially_pending` (base paid, ≥1 extra pending)

- Headline (resolver): "Your confirmed purchases are ready below.
  Items still pending are labeled and are not confirmed yet."
- Status label: `Partly pending`.
- The base purchase is confirmed in words and its access blocks render
  normally; each pending extra is labeled `Pending` in its own row and
  named in What happens next as not confirmed yet (2.3 pattern).
- "You are all set" is forbidden anywhere in this profile.
- Valid base access is never withheld because an optional charge is
  unresolved (A20).

### 3.3 Pending — `confirmation.status: pending` (nothing confirmed yet)

- Headline pattern: "We are still confirming your purchase." (Used when
  the whole order is unresolved; the renderer's reconciling state in
  `references/states.md` usually carries this profile.)
- Status label: `Pending`. No item is described as delivered, ready,
  or confirmed. No access blocks render.
- Copy states what is happening (payment still being confirmed), what
  happens when it resolves (access + email), and the support route.
- Checking again never starts another purchase; the buyer is told so.

### 3.4 Failed-extra — `attention_required` (≥1 item failed)

- Headline (resolver, failed-only): "Your confirmed purchases are
  ready below. A failed item is labeled separately and does not affect
  them." (With pending items also present, the resolver's combined
  "need attention" headline applies.)
- Status label: `Needs attention`. The failed item's row label is
  `Failed`, visually and textually distinct from `Paid` (section 4).
- What happens next names the failed item: no charge, no access, and
  confirmed items unaffected. Support path is the remedy route; the
  page offers no re-purchase action for the failed item (that would be
  a new-charge CTA).

### 3.5 The pitch line, stated once

An access, download, login, or scheduling action **for a purchased
benefit is not a pitch**. A button that initiates a new paid offer
**is** — whatever its label says. The test is the action's effect
(no-pitch policy section 1). Every rendered action carries one of
these classifications as `data-cta-class`, and no other:

`access` · `download` · `manage_purchase` · `support` ·
`schedule_included_service` · `noncommercial_next_step`

### 3.6 Tone rules (all profiles)

- Reduced promotional pressure: no urgency/scarcity language, no
  countdowns, no superlatives about the purchase, no cross-sell copy.
- Typography and brand tokens come from the launch's brand file via
  brand tokens (doc 16 section 2) — colors, brand name, support
  contact. The renderer accepts tokens; it does not hardcode a brand.
- Layout fits the copy; approved copy is never silently shortened to
  fit the template (doc 16 section 4).
- Statuses are words first: color is a redundant cue, never the only
  signal (section 5).

## 4. Per-item status labels

| View `display_status` | Label | Visual treatment (`ty82-status--*`) |
|---|---|---|
| `paid` | Paid | green text + pill border |
| `pending` | Pending | amber text + pill border |
| `failed` | Failed | red text + pill border |
| `requires_customer_action` | Action needed | amber text + pill border |
| `refunded` | Refunded | grey text + pill border |
| `partially_refunded` | Partially refunded | grey text + pill border |
| `unknown` | Confirming | amber text + pill border |

Pending, failed, and completed are always clearly separated (doc 12
section 8): distinct label text, distinct class, distinct color.

## 5. Accessibility, mobile, and keyboard requirements

- **Landmarks and headings:** one `<h1>` (the confirmation headline);
  sections in fixed order (order, access, what happens next, help),
  each a `<section>` with `aria-labelledby` pointing at its `<h2>`;
  heading levels never skip.
- **Status announcements:** the confirmation state sits in a
  `role="status"` / `aria-live="polite"` region; error fragments use
  `role="alert"`. State changes (reconciling → resolved) are announced
  by updating that region, not by moving focus.
- **The summary is a table** with `<caption>`, column headers
  (`scope="col"`) and row headers (`scope="row"`). It is fully usable
  as text: no image of a receipt, no canvas, no screenshot substitute.
- **Keyboard:** every action is a real `<a>` or `<button type="button">`
  in DOM order (primary action → access blocks → manage/support);
  visible focus via `:focus-visible` outline; no keyboard traps, no
  positive `tabindex`, no click-only divs. A retry is a button, never a
  timed auto-click.
- **Motion:** the reconciling spinner is decorative (`aria-hidden`)
  and is disabled under `prefers-reduced-motion: reduce`.
- **Color/contrast:** status is never carried by color alone (section
  4 labels); token colors must meet the launch brand's contrast rules
  in the target environment (doc 16 section 8: accessibility is a
  scored criterion).
- **Mobile:** the layout reflows rather than shrinks — the table's
  padding tightens and buttons go full-width under the mobile
  breakpoint; price, status, and disclosures stay visible in every
  responsive mode (doc 16 section 5). Content order on mobile is the
  DOM order above; nothing purchase-critical is hidden behind a tab or
  accordion.
- **Untrusted text:** all customer/brand/supplied text is HTML-escaped
  by the renderer; raw user-provided HTML is never concatenated into
  the page (doc 16 section 6).

## 6. Renderer implementation notes

- `scripts/render_thank_you.py` (stdlib only) renders one
  self-contained fragment: `<section class="ty82">` + a `<style>` block
  whose selectors are all namespaced under `.ty82` / `ty82-` classes,
  using token variables (`--ty82-primary`, `--ty82-accent`,
  `--ty82-background`, `--ty82-text`) set from the brand tokens.
  Namespacing exists to survive embedding in the GHL builder without
  collisions or broad resets (doc 16 section 6).
- Hosting/privacy guidance (no-store, noindex) is emitted as an HTML
  comment because a fragment cannot set headers or `<head>` meta; the
  host page owns those, and a robots tag alone is never claimed as
  privacy (doc 12 section 8; `references/states.md` section 5).
- Delayed, outage, and error rendering live in the same renderer and
  are specified in `references/states.md` (S82-06).

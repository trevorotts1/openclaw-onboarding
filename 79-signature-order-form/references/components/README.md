# S79 checkout components (draft, fixture level)

**REVIEW-ONLY.** Every draft here (`*.html`, `components.css`) is a design reference for review. None is installable: do not paste any of them into a Skill 06 custom-code block. They carry fixture copy (`TEST`), include markers, and a stylesheet link that Skill 06 drops, and the bump and consent checkboxes are unbound custom controls that add nothing to an order and gate nothing. Bump and consent must be native order-form settings (Skill 06, native Convert and Flow controls). Skill 06's custom-code lint must refuse `TEST`, include markers and bump or consent inputs (carried in `06-ghl-install-pages/tools/ghl_rest_canvas.py`).

Binding contract for the component drafts in this directory:

- `combined-checkout.html` assembles explanation, offer details, order bump, and guarantee/terms around the native checkout slot for a single simple offer (S79-03). Product Selection is skipped in this mode only.
- `post-selection-checkout.html` (FIXTURE-ONLY, outside the done claim; the wired route is `per_offer_instances`, see `83-black-friday-launcher/DECISIONS-PENDING.md`) renders the validated selection summary with a change-package path, plus recovery and reconfirmation states driven by `scripts/selection_flow.py` (S79-04). The summary's billing type and schedule rows come from the selection itself through `billing_summary()` in that module; times in the selection are timezone-aware ISO-8601 and compared as instants (CHK-07).
- `order-bump.html` renders exactly the states the bump fixture model produces: offered (unchecked), suppressed because the entitlement is already included or owned, and disabled because unavailable. Checking the box only modifies the pending order; the native submission processes the purchase.
- `offer-details.html` values come from `scripts/quote_display.py`, built from verified native price records and passed through the billing display audit before render.
- `guarantee-terms.html` renders guarantee and consent copy from approved references in the checkout request, never invented per launch. Consent starts unchecked.
- The native checkout slot is installed by Skill 06 with native Convert and Flow controls. No component in this directory may contain homemade card, expiry, or CVC inputs, and no raw payment data may appear in markup, logs, or screenshots.
- Brand values bind from Skill 71 tokens at install time; `components.css` names the token contract and carries neutral fallbacks for standalone review.
- Status and error copy renders into the `aria-live` status region; failed and pending states keep the visitor on checkout with the approved copy and the reconcile-first retry policy (doc 09 sections 7 and 8).

- Design stages: the page's wireframes and mockups are made by Skill 71's shared image service on the checkout role spec (`71-blackceo-signature-page/references/copy-specs/roles/checkout.json`) through Skill 49's `checkout_wrapper.py`; the section order there is the order above and in `QC-STATES.md`.

These are drafts for review, not installed pages. L2 rendered proof in an authorized location is still required before any stronger claim.

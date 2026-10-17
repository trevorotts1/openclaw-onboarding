# S79 checkout components (draft, fixture level)

Binding contract for the component drafts in this directory:

- `combined-checkout.html` assembles explanation, offer details, order bump, and guarantee/terms around the native checkout slot for a single simple offer (S79-03). Product Selection is skipped in this mode only.
- `post-selection-checkout.html` renders the validated selection summary with a change-package path, plus recovery and reconfirmation states driven by `work/selection/selection_flow.py` (S79-04).
- `order-bump.html` renders exactly the states the bump fixture model produces: offered (unchecked), suppressed because the entitlement is already included or owned, and disabled because unavailable. Checking the box only modifies the pending order; the native submission processes the purchase.
- `offer-details.html` values come from `work/display/quote_display.py`, built from verified native price records and passed through the billing display audit before render.
- `guarantee-terms.html` renders guarantee and consent copy from approved references in the checkout request, never invented per launch. Consent starts unchecked.
- The native checkout slot is installed by Skill 06 with native Convert and Flow controls. No component in this directory may contain homemade card, expiry, or CVC inputs, and no raw payment data may appear in markup, logs, or screenshots.
- Brand values bind from Skill 71 tokens at install time; `components.css` names the token contract and carries neutral fallbacks for standalone review.
- Status and error copy renders into the `aria-live` status region; failed and pending states keep the visitor on checkout with the approved copy and the reconcile-first retry policy (doc 09 sections 7 and 8).

These are drafts for review, not installed pages. L2 rendered proof in an authorized location is still required before any stronger claim.

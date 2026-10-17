# Eight-Section Design Profile - Skill 81 (S81-04)

Status: build candidate. Governing sources: packet 11 section 8; packet 16 sections 4, 5, 6, 8.

## Production sequence (shared workflow, D1 profile)

Approved copy -> section/action plan -> desktop wireframe -> mobile wireframe (intentional reflow, never a shrunk desktop) -> visual mockup -> per-asset prompts approved -> generation through the selected client-owned provider -> visual QC -> final layout -> responsive HTML -> S06 native install -> native action and route tests.

## D1-specific design rules

1. **Show the real scope difference.** The page must visually communicate what D1 actually is (smaller scope, or same scope on different terms) rather than look like the U1 page with a lower red number. Section 7's inclusions AND limitations get equal visual honesty.
2. **Original-buyer reassurance is a first-viewport element.** The visitor just declined U1 after buying the main offer. The first viewport states: your original purchase is confirmed and safe, this is an optional alternative, and declining changes nothing about what they already own.
3. **Disclosures never shrink.** Trial/recurring terms (due now, renewal amount, renewal date or rule, interval, cancellation, access implications) render at body size adjacent to the action in every responsive mode. No miniature footer type for money terms.
4. **One action, one decline, everywhere.** Every section's CTA is the same native action component; the decline action ("continue with my current order") is visible without scrolling-hunting and styled as a real choice, not a hidden text link.
5. **Section rhythm.** Varied, purposeful geometry per section (doc 16 section 5): the three pains must not render as three identical cards; section 8's seven missed-out items render as a single scannable list under the canonical heading, visually distinct from section 7's inclusions list so "what you get" and "what you will not get" can never be confused.
6. **States are designed, not improvised.** Default, focus, selected (where the component has a selection analogue), loading/processing (CTAs disabled, spinner at the action), error/failed (recoverable, retry or continue-without-extra), pending/requires-action, expired-context (checkout fallback), and completed/success states all have desktop and mobile previews before install (doc 16 section 5 requires default, focus, selected, loading, error and completed previews). The completed state matters doubly here: it is the section 7 handoff trigger to U2 or final thank-you, and it may render only from verified native success evidence.
7. **Brand comes from the launch brand file only** (shared tokens and loader owned by S71). No per-page palette invention. Imagery follows the launch creative direction with provider provenance recorded per asset; a planned asset is not a generated asset.
8. **Accessibility and performance** per doc 16: real buttons for actions, links for navigation, visible focus order preserved, no animation that hides price or shifts the pay button, reduced-motion respected.

## QC gates for this profile

Independent copy and visual review of the entire page and every error/disclosure state; each applicable criterion at least 8/10, target average 8.5. Automatic fails per doc 16 section 8 (wrong price/product, concealed recurring charge, invented scarcity or proof, broken native action, incorrect entitlement) apply unchanged.

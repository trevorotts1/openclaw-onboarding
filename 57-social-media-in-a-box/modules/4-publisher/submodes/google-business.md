# Publisher sub-mode — google-business  (DOCUMENTED STUB)

**Status:** stub — PRD Open Decision **D2**. A routed Google-Business branch exists in the main
orchestrator (transactional "What's New"/"Special Offer" with a direct CTA + local-SEO keywords),
but there is **no canonical poster digest among the 20 workflows**.

## Behavior in 0.1.0
- The strategy/reformat coverage is generated (prompt 03 Google Business strategy), but the sub-mode
  does NOT post; it returns a stub result and logs that a real poster target is required.
- Build the real sub-mode only if the missing `executeWorkflow` target surfaces.

## Contract
- Result: `{platform:"google-business", success:false, totalPosts:0, processedAccounts:0,
  errors:["stub: no canonical GBP poster in the 20-workflow family (D2)"]}`.

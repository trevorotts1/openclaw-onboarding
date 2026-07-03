# Publisher sub-mode — facebook

**Source:** `part5-fbig-carousel` (32 nodes) + the main orchestrator Facebook branch.
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- `post` — feed post (Hook → Story → Lesson; ends with an algorithm question).
- `story` — casual, under-15-word text, "Tap to read".
- `reel` — 0-3s visual-hook script with [Visual Cues].
- `carousel` — **10-slide** image carousel (prompt 09), scheduled 10am ET with a next-slot fallback.

## Contract
- Caption **1,500–1,800 chars**, **5–7 hashtags**, hook in first ~125 chars (`AF-SM-CAPTION-BAND`,
  `AF-SM-HASHTAG-COUNT`).
- 10 slides, each `textOnImage ≤ 8 words` + image prompt 1,000–1,700 chars (`AF-SM-CAROUSEL-SLIDES`,
  `AF-SM-HEADLINE-WORDS`, `AF-SM-IMGPROMPT-BAND`); assemble only with ≥2 images (`AF-SM-CAROUSEL-FLOOR`).
- Result: `{platform:"facebook", success, totalPosts, processedAccounts, errors}`.

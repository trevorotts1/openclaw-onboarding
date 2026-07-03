# Publisher sub-mode — instagram

**Source:** `06-instagram-poster` (19 nodes) + `part5-fbig-carousel` (shared carousel engine).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- `post` — aesthetic micro-blog; headline in ALL CAPS / emoji; 15–20 niche hashtags at the bottom.
- `story` — interactive (polls/stickers), drives "Link in Bio".
- `reel` — high-energy script, trending-audio vibe, fast cuts.
- `carousel` — **10-slide** carousel; per-account split; `postTypes` gate each branch.

## Contract
- Carousel caption **1,500–1,800 chars**, **5–7 hashtags**; reformatter IG variant uses **5–15
  hashtags** and `followUpComment ≤ 500 chars` (`AF-SM-HASHTAG-COUNT`, `AF-SM-FOLLOWUP-BAND`).
- 10 slides (`AF-SM-CAROUSEL-SLIDES`); ≥2-image assembly floor (`AF-SM-CAROUSEL-FLOOR`).
- Result: `{platform:"instagram", success, totalPosts, processedAccounts, errors}`.

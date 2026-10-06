# Publisher sub-mode — tiktok

**Source:** `09-tiktok-poster` (5 nodes).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- Video, privacy `PUBLIC_TO_EVERYONE`; comments / duet / stitch enabled.
- Raw, UGC-feel script; visual shock in the first 3 seconds; caption carries 3–4 semantic keywords
  (TikTok as a search engine).

## Contract
- Uses the 25.0s video lane (EXACTLY 25.0s, render model picked by the Skill 67 selector; `AF-SM-STORYBOARD`).
- Result: `{platform:"tiktok", success, totalPosts, processedAccounts, errors}`.

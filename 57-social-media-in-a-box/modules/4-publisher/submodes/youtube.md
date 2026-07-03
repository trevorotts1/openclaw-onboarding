# Publisher sub-mode — youtube

**Source:** `08-youtube-poster` (8 nodes).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- Long video — structured script (Hook/Promise → Bumper → Value → Subscribe CTA), **public**.
- Short — loopable script (last sentence flows back into the first to encourage replays).

## Contract
- Uses the Sora video lane output (storyboard 3–7 scenes, EXACTLY 25.0s; `AF-SM-STORYBOARD`).
- Result: `{platform:"youtube", success, totalPosts, processedAccounts, errors}`.

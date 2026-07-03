# Publisher sub-mode — pinterest

**Source:** `10-pinterest-poster` (5 nodes).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- Pin with `title` / `link` / `boardIds`.
- SEO-focused description ("How to [Benefit]…", "5 Ways to…"), keyword-rich for search indexing.

## Contract
- Result: `{platform:"pinterest", success, totalPosts, processedAccounts, errors}`.

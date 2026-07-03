# Publisher sub-mode — linkedin

**Source:** `07-linkedin-poster` (4 nodes) + `part7-linkedin-carousel` (33 nodes).
**Endpoint:** `POST services.leadconnectorhq.com/social-media-posting/{locationId}/posts` (client PIT).

## Capabilities
- `post` — "bro-etry" one-sentence-per-line; NO external link in the body; the link goes in a
  separate `followUpComment`.
- `carousel` — **9-slide PDF document carousel** (prompt 10): `postAsPdf:true` + `pdfTitle ≤ 100
  chars`. Skips gracefully when the location has no connected LinkedIn account.

## Contract
- Caption **1,500–1,900 chars**, **exactly 3 hashtags** (`AF-SM-CAPTION-BAND`, `AF-SM-HASHTAG-COUNT`).
- `pdfTitle ≤ 100 chars` (`AF-SM-PDFTITLE-BAND`); 9 slides (`AF-SM-CAROUSEL-SLIDES`); `postAsPdf:true`
  required (`AF-SM-CONTRACT-SCHEMA`); `followUpComment ≤ 500 chars` (`AF-SM-FOLLOWUP-BAND`).
- Result: `{platform:"linkedin", success, totalPosts, processedAccounts, errors}`.

# Module 4 — Publisher (GHL-direct)

**Source:** `06-instagram` (19) + `07-linkedin` (4) + `08-youtube` (8) + `09-tiktok` (5) +
`10-pinterest` (5) + `part5-fbig-carousel` (32) + `part7-linkedin-carousel` (33) + `delete-posts`
(7). **Phase:** P7. **Prover of the unlock:** `scripts/build_manifest.py` (P6 certificate).

Every sub-mode posts through **the client's OWN GHL (Convert & Flow) location** using **the client's
own Private Integration Token + locationId + connected social accounts** — never operator
credentials, never direct platform APIs — via:

```
POST https://services.leadconnectorhq.com/social-media-posting/{locationId}/posts
```

The entry-script BYPASS-SCAN refuses any hand-rolled poster that calls a platform API directly
(`AF-SM-POST-BYPASS`).

## Sub-modes (`submodes/`)

| Sub-mode | Capabilities |
|---|---|
| `facebook` | post / story / reel / **10-slide carousel** (scheduled 10am ET, next-slot fallback) |
| `instagram` | post / story / reel / **10-slide carousel** (per-account split; postTypes gate each branch) |
| `linkedin` | post + `followUpComment` / **9-slide PDF document carousel** (`postAsPdf:true`, `pdfTitle ≤ 100`); skips gracefully with no LinkedIn account |
| `youtube` | long video + Short, public |
| `tiktok` | video, `PUBLIC_TO_EVERYONE`, comments/duet/stitch on |
| `pinterest` | pin with title / link / boardIds |
| `google-business` | **documented stub** (route + strategy exist; no canonical poster among the 20 — PRD Open Decision D2) |

## Normalized result contract (`AF-SM-PUBLISH-RESULT`)

Each sub-mode returns `{platform, success, totalPosts, processedAccounts, errors}`. The `clean`
sub-mode (delete-posts) lists posts in a date range, filters by status, and deletes — bulk rollback
of a scheduled week, and nothing else.

## The unlock (`AF-SM-PUBLISH-UNPROVEN`)

The publisher physically cannot run without the P6 signed `PROCESS-CERTIFICATE` (config hash,
prompt-hash pin, every gate certificate, per-run ZERO-Anthropic proof, agency isolation). `done` is
claimed **only** from that certificate **plus a live GHL post-listing verify** (independent
end-to-end verify, client-outcome level — never the poster's own return value).

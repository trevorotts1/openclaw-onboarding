# Social Planner — Community publishing and comments

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inherited`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Registry state

`social.accounts.list`, `social.posts.create/list/get/delete`, `social.comments.*`, `social.queues.*` and `social.statistics` are in the registry as public rows; most carry `B-SOCIAL-SPEC`, a recorded spec conflict. Treat that as "verify the executable contract at implementation time", not as a green light for a live write.

## Identity mapping (the failure this page exists to prevent)

- Use the connected channel's `account.id` — never `oauthId`.
- Use a returned member `contactId` — never a staff user id.
- Validate the saved author against the group's observed backend id.
- Every Community account in one request needs its own `postAsUser` mapping.
- Private-channel membership is channel-specific: a member valid on one channel may be invalid on another.

## Synthetic payload fragment (not a complete scheduled request)

```json
{"accountIds":["SYNTHETIC_COMMUNITY_ACCOUNT_ID"],"type":"post","summary":"Approved discussion content","media":[],"communityPostDetails":{"title":"Approved discussion title","notifyAllGroupMembers":false,"postAsUser":{"SYNTHETIC_COMMUNITY_ACCOUNT_ID":{"id":"SYNTHETIC_MEMBER_CONTACT_ID","name":"Observed Member Display Name"}}}}
```

Add only the documented scheduling/draft/publication fields for the intended action. Media entries use documented objects such as `{url,type}`, never an invented `mediaUrls`.

## Limits and scopes

- Title 1,000 characters; Community caption 100,000; four media items.
- Split requests per platform so another platform cannot silently truncate the Community caption.
- Scope evidence: accounts `socialplanner/account.readonly`; members `socialplanner/oauth.readonly`; validation `socialplanner/account.readonly`; post write `socialplanner/post.write`; comments `socialplanner/comments.write`. The word `oauth` in a scope name does not by itself forbid a PIT.

## Lifecycle

`approved content → author/account preflight → submitted → draft_saved OR scheduled OR publishing → published_verified OR failed OR pending_moderation/processing`

A created record or accepted schedule is not a published post. A null permalink is not automatically failure; use the documented status plus destination inspection.

Failure cases to test: wrong `oauthId` rejected; staff id rejected; author revoked after scheduling; notification without approval refused; duplicate scheduled payload does not duplicate a post.

Readback: read the post id/state/content from the documented post read and confirm the destination thread.

## Comments

The comment endpoint uses the internal post/comment id, not a native platform id. `isParentThread:true` targets the post; false targets an existing comment. Community text limit is 8,000. `notifyAllGroupMembers` defaults false and needs explicit broadcast approval. External attachment URLs are not rendered by current Community behavior: do not report a successful comment as a successfully attached resource.

Re-sync: new groups/channels may need Social Planner reconnection. Re-query accounts after re-sync; never derive an account id from a slug.

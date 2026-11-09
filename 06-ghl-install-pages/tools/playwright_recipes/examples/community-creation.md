# Community creation on a populated native list

The native app's Groups list was captured with separate Active and Inactive
filters on November 9, 2026. `community_creation.py` reads both complete captured
lists twice, checks every card's exact title/status, and refuses changing or
paginated inventory. The canonical Groups list must be the job's `start_url`.

The script no longer treats every nonempty group list as an automatic create
block. A new unique name can use the native full-page Create Group sequence with
authored name, slug and description, and Discovery explicitly off. This path
requires `allow_creation:true`. Native Create initially produces an Active row.
The default `inactive:true` path first binds that fresh creation's exact name/
slug redirect and unique new card, then uses only that card's captured status
control and exact Deactivate Group confirmation. Both filters are independently
read again to prove the new row is Inactive and every unrelated group is
unchanged. Explicit `inactive:false` retains the new Active row and never clicks
a status control. Existing groups are never deactivated implicitly.

Immediately after this handler submits the unique new name/slug, the native app
returns to the exact location-bound list with `groupCreated` and `groupSlug`
query parameters. The handler requires both exact authored values, rejects
duplicate/unrecognized keys, and records that native transaction binding before
list navigation removes the query. The name is then independently read in the
Active list. Native name length is at most 30 characters.

The receipt is `GROUP_CREATED_SLUG_IDENTIFIED`, with
`identity_source:native_creation_redirect`, `slug_identity_verified:true`,
`portal_identity_verified:false`, `discovery_verified:false`,
`independent_readback:VERIFIED` and `functional_verified:false`. This observed
create redirect is not accepted from intake or from an existing name-only card.
It does not establish portal authentication, privacy or member behavior. No
privacy control is present on the captured Create Group page.
`group_status` is `Inactive` by default or `Active` when explicitly requested;
`native_deactivation_attempted` and `inactive_verified` match that exact mode.

Existing groups are handled separately from new creation:

- One exact active name match, with explicit `inactive:false`: the script opens
  that uniquely inventoried card's native Login popup, requires the exact
  requested slug/home URL, matching native title/group name and captured modern
  Learning/Settings links without a password wall. It closes only that new popup
  afterward. `GROUP_REUSED_IDENTITY_CONFIRMED` records this causal card-to-portal
  identity binding; name-only card text is never sufficient. Description,
  Discovery and functional verification remain pending. No credentials are
  typed and no invite, join, ownership or status control is clicked.
- Duplicate, differently cased or inactive same-name groups:
  `EXISTING_GROUP_IDENTITY_UNVERIFIED`; those identities need separate capture.
- An existing Active group with `inactive:true`:
  `EXISTING_GROUP_STATE_UNVERIFIED`. Reusing or creating a container does not
  implicitly authorize a status change to an existing group.

No membership invitation, ownership transfer or activation action is used.
The existing Forbidden portal is not retried. Privacy/access and branding are
separate portal operations. Optional tests and live client execution are deferred
at the owner's request; captured controls alone are not a completed live build.

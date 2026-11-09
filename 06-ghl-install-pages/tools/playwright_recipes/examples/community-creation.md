# Community creation on a populated native list

The native app's Groups list was captured with separate Active and Inactive
filters on November 9, 2026. `community_creation.py` reads both complete captured
lists twice, checks every card's exact title/status, and refuses changing or
paginated inventory. The canonical Groups list must be the job's `start_url`.

The script no longer treats every nonempty group list as an automatic create
block. A new unique name can use the native full-page Create Group sequence with
authored name, slug and description, and Discovery explicitly off. This path
requires `allow_creation:true` and **explicit `inactive:false`**: the owner job
must request a newly active group. No active/inactive status control is clicked.

The newly created name is independently read back in the Active list. Current
native cards expose no slug, opaque ID or portal link. The receipt therefore
remains `GROUP_CREATED_PENDING_IDENTITY`, with `slug_identity_verified:false`,
`discovery_verified:false`, `independent_readback:REQUIRED` and
`functional_verified:false`. The `slug` field is the authored input, not invented
native proof. No privacy control is present on the captured Create Group page.

Two other cases stop before native writes:

- A same-name group in either list: `EXISTING_GROUP_IDENTITY_UNVERIFIED`. Name-only
  cards cannot prove the requested slug or safely authorize a reuse.
- Inactive creation: `GROUP_SLUG_IDENTITY_REQUIRED`. The script will not create and
  then blindly deactivate a same-name row without an exact native identity.

No Login, membership invitation, ownership transfer or activation action is used.
The existing Forbidden portal is not retried. Privacy/access and branding are
separate portal operations. Optional tests and live client execution are deferred
at the owner's request; captured controls alone are not a completed live build.

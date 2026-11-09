# Communities, groups, channels and Learning association

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inheritented`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## What is public and what is not

Public Social Planner operations cover connected accounts, eligible members, membership validation, posts and comments. They do **not** establish general group/channel creation, full member administration, or course-to-group association. The registry's `social.*` rows are public with blocker `B-SOCIAL-SPEC` (spec conflict to verify at execution); group/channel operations are **browser-backed** (`skill06_authoring`).

| Operation | Default route | Proof required |
|---|---|---|
| Discover/reuse group | Managed UI (+ connected-account metadata) | Exact location, slug, observed backend id |
| Create group / update branding / access | Managed UI | Saved and reopened; before/after fields |
| Create/update/order channels | Managed UI | Target group, name, order, settings |
| Premium/read-only channel settings | Managed UI where present | Exact membership policy; no unapproved price |
| Attach existing course in Learning | Managed UI unless a verified API/MCP contract exists | Correct course, correct group, learner-visible |
| Detach course | Managed UI | Association removed; course not deleted |
| List/validate publishing members | Public Social Planner | Per account, paginated, `isActive` |
| Invite/approve/remove/ban/role | Managed UI or native workflow action | Explicit access change proof |
| Post/comment | Public Social Planner | Real post state and destination |

A Community author-membership validation read does not grant membership. Calendar groups are not Community groups.

## Object distinctions

`community_group_id` (opaque backend id) ≠ `community_group_slug` (portal slug) ≠ `community_channel_id` ≠ `social_account_id` (connected Community channel account.id) ≠ `member_contact_id`. Never treat a connected Social Planner account id as the group id.

## Learning association algorithm

Input is a validated relationship plan, not a URL:

```json
{"schema_version":"1.0.0","location_id":"SYNTHETIC_LOCATION","course_product_id":"SYNTHETIC_COURSE","group_ref":{"group_id":null,"group_slug":"approved-group-slug","portal_host":"approved-client-portal.example"},"desired_access":{"mode":"all_members","policy_ref":"APPROVED_POLICY"},"operation":"attach","approval_ref":"SYNTHETIC_APPROVAL"}
```

1. Resolve group and course in the same location.
2. Enumerate existing associations first; an identical association is an idempotent verified result.
3. Use "attach existing course", never "create new course".
4. Set only the approved access policy.
5. Save, reload, verify the exact course + policy.
6. Detach removes only the relationship; it never deletes the course.

Relationship receipts are separate from course-create receipts.

## Cleanup residue

Known group cleanup is deactivation with visible residue (group URL + inactive status), not a proven delete. Only use a genuine delete when the product exposes it, the contract is captured, and that exact deletion is approved.

## Minimal failure/readback

Failure: attach a course from another location → refuse before clicking. Failure: fake selector marked `captured` → the builder must STOP and report; tests may inject fakes but must label them fake.

Readback: reopen the group's Learning tab and confirm course id + policy; then verify with an authorized member/test identity for the requested delivery level.

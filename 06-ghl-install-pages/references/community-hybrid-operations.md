# Community hybrid operations — groups, channels, members, content, Learning

Owner: **WF09 / GHL-009**. Scope: the managed-UI half of Skill 6's hybrid Community work,
plus the course-to-Learning relationship operator. Public Social Planner post/comment
operations belong to **WF10** (`public/community_social.py`); this reference never claims
a public API for group/channel/member/Learning authoring.

## 1. Boundary — what is public, what is managed UI, what is unavailable

Verified public surfaces in this contract: Community **social posts/comments** and
**publishing-member lookup/validation** (WF10). They do not establish group/channel
creation, full member administration, or course-to-group association endpoints.
Calendar groups are not Community groups. The retired "community MCP" stays retired.

| Operation | Route | Executor | Proof / constraint |
|---|---|---|---|
| Discover / reuse group | managed UI | `ghl_community_builder` | list-scan by name/slug (list has NO search box) |
| Create group | managed UI | `ghl_community_builder` | ZHC name, privacy, branding CDN URL only, native submit |
| Update group details/branding | managed UI | `_execute_group_update` | only requested fields; read each back |
| Change group access/privacy | managed UI | `_execute_change_access` | approval_ref + admin role; read privacy back |
| Activate / deactivate group | managed UI | `_execute_set_active` | card-scoped Status dropdown; residue on deactivate |
| Create/update/order channels | managed UI | `_add_channel`, `_execute_channel_update`, `_execute_channel_order` | row-scoped controls; verify nav order |
| Private / read-only / premium channels | managed UI where present | `_execute_channel_settings` | approval for premium; never changes billing; `feature_unavailable` when the tenant lacks it |
| Attach existing course in Learning | managed UI | `ghl_learning_association.attach_existing_course` | enumerate first, idempotent, policy verified |
| Inspect / update Learning access | managed UI | same (policy select) | policy separate from course ownership |
| Detach course from group | managed UI | `ghl_learning_association.detach_course` | relationship only; course proven present |
| List eligible publishing members | public Social Planner | WF10 | per connected channel account, paginated |
| Validate publishing membership | public | WF10 | backend group id + member contact id, explicit `isActive` |
| Invite/approve/remove/ban/role/grant/revoke | managed UI or native workflow action | `ghl_community_members` | exact person; approvals; row read-back |
| Create/edit/schedule/read post, comments | public Social Planner | WF10 | correct account/author, actual state |
| Pin / moderate / delete unsupported content | managed UI | `ghl_community_content` | exact content identity; approval for hide/delete |
| Course/group member-view verification | managed UI under approved identity | `ghl_community_members`, `ghl_community_content` | visible content/access must match the request |

Each catalog entry has an executor or an honest `feature_unavailable`. Placeholder
executors are not completion.

## 2. Learning association (A12)

Input is a relationship plan, not a page URL:

```json
{
  "schema_version": "1.0.0",
  "location_id": "SYNTHETIC_LOCATION",
  "course_product_id": "RESOLVED_COURSE_ID",
  "course_name": "ZHC Launch 101",
  "group_ref": {"group_id": null, "group_slug": "approved-group-slug",
                 "portal_host": "approved-client-portal.example"},
  "desired_access": {"mode": "all_members", "policy_ref": "APPROVED_POLICY",
                      "policy_label": "All members"},
  "operation": "attach",
  "approval_ref": "APPROVAL_REFERENCE"
}
```

Algorithm (implemented in `tools/ghl_learning_association.py`):

1. Validate the plan: same location (any supplied `course_location_id` /
   `group_location_id` must equal `location_id`), resolved course id (never "new"),
   resolved group, approved policy, `approval_ref`.
2. Open the exact group's Learning tab using registered selectors.
3. Enumerate existing associations FIRST. A matching course + policy returns a verified
   idempotent `reused` result and writes no duplicate.
4. Use the existing-course selection action. A create-new-course control is refused in
   code (`_click`/`_fill` guard), not just in prose.
5. Resolve identity before clicking: course id or exact name; ambiguity stops.
6. Set only the approved access policy — never silently flip all-members ↔ paid.
7. Save, reload the relationship view, verify the exact course AND the policy label.
   A mismatch STOP-and-reports.
8. Store a **separate** `learning_association` receipt from the course-create receipt.
9. Detach removes only the matching row's own remove control, then proves the
   association is gone AND the course still exists (`course_deleted=false`). Detach
   never calls a course delete and never uses a global first-match.

Frozen interface: **WF09-CP01** — `plan_association`, `read_associations`,
`attach_existing_course`, `detach_course`, `execute`, `build_association`, plus the
stable result envelope. A later change is `WF09-CP02` with a migration note and the
affected-consumer list.

## 3. Member administration

- The exact group and exact person are mandatory (`member_contact_id` preferred, or a
  single unambiguous email). Ambiguous matches stop before any action.
- Role elevation, removal, ban and revoke require `approval_ref`; elevation to
  `admin`/`owner` can never happen silently.
- Routine invite/approve may use the tenant's established automation authorization
  (`automation_authorized=True`) instead of a new approval each time.
- A native Grant/Revoke Group Access workflow action requires its real step schema; the
  code refuses to invent an action id and never treats workflow enrollment as access
  proof. Access is verified from the member's own row.
- Group access and course-offer access are distinct facts in the result:
  `group_access` vs `course_offer_access` (the operator only asserts the scope it read).
- Broad member notifications require an approval.

## 4. Content and moderation split

`ghl_community_content.classify_route()` is the single routing statement:

- `post_create`, `post_update`, `post_schedule`, `post_read`, `comment_*` →
  **public Social Planner, owner WF10** (not implemented here).
- `pin`, `unpin`, `hide`, `restore`, `delete`, `list_pending`, `verify_view`, `moderate`
  → **managed UI, WF09**.
- Anything else → `feature_unavailable`.

Moderation/hide/delete need a moderator+ role and `approval_ref` for hide/delete. Every
action is row-scoped to the exact content id/permalink and the state is re-read.

## 5. Group and channel settings

- Only the requested fields travel. Unrelated group configuration is never rewritten;
  the before/after snapshot records exactly what changed.
- Channel rename/description, ordering, and private/read-only/premium settings are
  row-scoped. Order is verified against the rendered nav sequence.
- Premium requires an approval and **never** changes price, recurring billing, or an
  existing subscription; such fields are rejected at plan time.
- `feature_unavailable` is the honest result when a tenant lacks a channel setting; the
  catalog does not claim every optional UI feature exists everywhere.

## 6. One browser writer per tenant/session

`ghl_community_builder.browser_writer(location_id)` is the guard. A second writer for the
same authenticated tenant raises `StopAndReport("writer.busy")`; different locations may
run independent managed sessions. Narrow operators (association/member/content) are
called by the owning builder and never spawn their own browser or login. Browser pauses
do not serialize unrelated public API work (WF10).

## 7. Cleanup honesty — deactivation with residue (D09, A13)

- A Community group has **no delete** on any known rail. The former "delete the scratch
  group / zero residue" promise was removed (D09). Cleanup of a group this run
  **created** is a card-scoped deactivate that records
  `{group_url, status: "inactive", slug, residue}`.
- A **reused** group (or a run that stopped before create) is preserved and reported
  `cleanup_primitive: "preserve"`, `deleted: false` — never a fake delete (A13).
- Courses are the true-delete rail (search-narrow + card-scoped + type CONFIRM); that
  belongs to `ghl_course_builder._delete_course`.

## 8. Selectors and capture status

- Machine map: `tools/selectors-live-communities-courses.json`.
- Prose: `tools/SELECTORS-LIVE-community.md` (§4 for the WF09 hybrid surfaces) and
  `tools/SELECTORS-LIVE-course.md` (§5 for the association cross-reference).
- Phase B (2026-07-10) locked the group create/channel/deactivate core and the course
  wizard/outline/delete. Everything added for the hybrid group update/access/activation,
  channel settings, members, content moderation, and Learning association is
  **capture-pending**: `status:"capture-pending"`, `conf: 0`, an explanatory `note`,
  and a capture recipe. The live walk STOP-and-reports rather than guessing CSS (D8).
- Shared gate registrations live in `tools/gates.json`
  (`community_builder_gates`, `learning_association_gates`).

## 9. Acceptance map (this lane)

| ID | Behavior proved by |
|---|---|
| A12 | `tests/test_community_learning_association.py` — same-location refusal, existing-course-only, idempotent attach, separate receipt, exact policy verification, detach removes only the relationship and proves the course survives |
| A13 | `tests/test_community_builder_hybrid.py` — `cleanup_decision` preserves reused resources; created scratch groups deactivate with recorded `group_url`/`status`/`slug` residue and `deleted: false`; `qc-built-community.sh` rejects a delete claim that carries residue |

## 10. Change-request intake

WF09 is the sole writer of the Community/course selector JSON, selector prose and shared
`gates.json` registrations. WF08 (course media), WF26 (Meeting Rooms) and WF34 (marketing
quizzes) submit captured selector/gate fragments through a Document-2 §6.2 change
request; WF09 applies them inside this lease and reviews the result. At the 2026-11-08
build no request record existed in the run's `change-requests/GHL-009/` folder, so none
was applied.

## 11. Live activation still pending

No live canary ran in this lane. Notebook of external work: capture the pending selectors
on the authorized operator test group; confirm admin/moderator roles for the acting
operator; confirm which optional channel settings and moderation controls the tenant
actually exposes; record the capture date and verification example, then flip statuses
to `locked`. Until then these operations are implemented and offline-tested, not
live-proven.

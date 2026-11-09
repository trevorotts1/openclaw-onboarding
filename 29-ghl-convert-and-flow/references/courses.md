# Courses — API-first construction and the browser seam

> **Authority.** The executable registry (`44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/public/operations.py`) is the only implementation authority. This reference is a derived, source-indexed view. Reading it cannot enable an operation; enablement is per `(operation_id, tenant)` in the capability gate.
>
> **Evidence state (2026-11-08).** Pages were not refetched in this lane. `ghl-contract-sources.json` labels each source `inheritented`/`reopened-at-spec-time`, never "verified live". A source-reported capability is not a measured entitlement of this or any client account. Machine-readable rows: `ghl-hybrid-capability-index.json`.

## Registry state

No `courses.*` row exists in the registry at this branch base. That is a **gap**, not permission to claim browser-only construction. The rows and typed adapter are owed by **WF06** (`public/courses.py`, command module) with media binding by **WF08** and the Skill 6 coordinator by **WF07**. Until those rows land, `ghl-hybrid-capability-index.json → documented_unregistered` carries the documented routes with their gap labels.

Do not edit `ghl_course_builder.py`, `ghl_object_router.py`, `ghl_method_decision.py`, `v2_dispatcher.py` or `ghl_public_client.py` from this skill: they are WF07/WF24 leases.

## Object distinctions (do not collapse)

| Internal name | Vendor object | Identity rule |
|---|---|---|
| `course_product_id` | Course product (`/courses/products`) | Returned id; never a title |
| `course_category_id` | Category/module | Parent-before-child; `parentCategory` |
| `course_lesson_id` | Lesson | Created with `categoryId` |
| `course_offer_id` | Offer | Separate from commerce product/price |
| `commerce_product_id` | `/products/` | Not the course id |
| `community_group_id` | Community group | Separate object; association is its own record |

A portal slug is not a group id. A course offer, a commerce price, an enrollment and a group association are four objects.

## DTO facts that must not be guessed

- Create Course requires `title`. Description, poster and `customizations` are optional. The request excludes `locationId`, `userId`, `id`, `originId`, `source`, `processing`.
- Create Category requires `title`; settings live in `metadata` (lowercase d).
- Create Lesson requires `title` and `categoryId`; lesson settings live in `metaData` (capital D). Category and lesson visibility vocabularies differ.
- There is no course `status` property to invent. Draft intent is expressed by module/lesson visibility, offer/access state and explicit release operations.
- A CDN URL is not a native `contentId`. `contentType` without a real content association is not proof of media.

## Minimal synthetic request (shape only)

```json
{"title":"ZHC Launch 101","description":"Approved description","posterImage":"https://approved.example/course-cover.png"}
```

Failure case to test: creating a lesson without `categoryId` must fail locally, not silently attach to a guess. Failure case to test: `contentType:"video"` with no verified `contentId` must be refused.

Readback: re-read the course, its categories in order, and the lesson's `categoryId`/visibility; a create response is not display-order proof.

## Media binding — three paths, one honest outcome

- **Path A** verified same-location native content id → attach via the documented lesson operation, then verify content readback/playback.
- **Path B** documented course import → dedicated serializer; lifecycle `planned → submitted → processing → reconciled → content_verified`; a processing response is **not** completed course creation.
- **Path C** managed-browser native-content step only when A/B cannot ingest the asset. Keep API-created ids; attach only the missing step; record route, asset hash and processing outcome.

Separate proof fields: `asset_persisted`, `native_content_ready`, `lesson_association_verified`, `learner_render_verified`. A permanent URL proves only the first.

## Offers, enrollment, assessment

- Offers/enrollments use course offer/enrollment endpoints, never renamed commerce product/price calls.
- `POST /courses/enrollments` taking a contact and an offer is not evidence money was paid.
- Revoking an offer can remove access to several included products: compute the affected set first.
- Lesson quizzes use the lesson-quiz create + question upsert relationship. A quiz label in lesson `metaData` is not an assessment. This is **not** a marketing quiz (WF34).

## Current-main evidence (labelled, not a green light)

`06-ghl-install-pages/tools/ghl_course_builder.py` is a working managed-browser builder whose module docstring still says GHL has "NO known public create API". That statement is historical. The replacement text and the router flip are WF07's lease; a change request is filed, not applied here.

## A18 checks

1. Every implemented course operation has a registry row before a doc calls it implemented.
2. Every documented route without a row carries a `GAP-WF06-*` label here and in the index.
3. No page claims every media/group function is public.
4. No page claims the course was delivered before `learner_render_verified`.

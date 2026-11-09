# Course API-first build — Skill 6 operator reference

> **Authority.** `29-ghl-convert-and-flow/references/ghl-hybrid-capability-index.json` and the
> executable registry (`44-.../public/operations.py`) decide what is implemented. This page
> explains how Skill 6 builds a course without pretending a plan is an object.
>
> **Evidence state (2026-11-08).** No page was refetched in this lane. Public course rows are
> owned by WF06 and are not yet in the registry on this branch; they are labelled
> `documented-unimplemented` with `GAP-WF06-*` owners. The managed-browser builder is the
> proven fallback and the only rail for a UI-only native-content step.

## 1. Division of labour

| Concern | Owner | Rail |
|---|---|---|
| Typed public course/category/lesson/offer/enrollment/import adapter | WF06 | public REST |
| Router/method decision and central construction hooks | WF07 | calls the adapter |
| Native lesson media binding | WF08 | API/import first, managed UI only for the missing step |
| Shared multipart transport | WF01 | central transport |
| Managed-browser course builder | Skill 6 (existing, proven) | `tools/ghl_course_builder.py` |
| Course docs/index | WF14 (this reference) | documentation only |

Do not edit `ghl_course_builder.py`, `ghl_object_router.py`, `ghl_method_decision.py`,
`v2_dispatcher.py` or `ghl_public_client.py` from this reference. A defect there is a change
request to the owning lane.

## 2. Object distinctions

- A course is not a commerce product. `course_product_id` ≠ `commerce_product_id`.
- A category/module is not a lesson; a lesson has `categoryId`.
- An offer is not a price; enrollment is not payment.
- A Community group is a separate object; attaching a course is a relationship record.
- A CDN URL is not a native `contentId`.

## 3. Build order (API-first)

1. Validate the internal plan locally: unique logical keys, existing parents, no cycles,
   approved content references, explicit visibility. Duplicate display titles are allowed when
   keys differ.
2. Resolve tenant/scopes and reconciliation candidates by recorded id/logical key. A title match
   is a candidate, never permission to edit or delete.
3. Create/update the course shell; persist the returned id immediately.
4. Create categories parent-before-child; apply deterministic ordering after ids exist.
5. Create lessons with complete supported metadata and explicit visibility, per-lesson
   checkpoints.
6. Bind approved text/native video/audio/downloads/assessment through the media seam.
7. Apply final sequencing and read back actual order.
8. For drip/locked modules, resolve real prerequisites; reject cycles; do not publish content to
   satisfy a validation error.
9. Create/update the offer only when the plan requests it; keep commerce price and membership
   access separate.
10. Create/reuse the Community and attach only when requested.
11. Verify content and learner destination at the requested delivery level.
12. Emit the aggregate delivery receipt and board/launch events through the shared bridge.

## 4. Three media paths

- **A — verified native content id:** attach via the documented lesson operation; verify
  readback/playback.
- **B — documented import:** dedicated serializer; lifecycle
  `planned → submitted → processing → reconciled → content_verified`. A processing response is
  **not** completed course creation. Reconcile before any repeat submission.
- **C — managed UI only for the missing ingestion step:** keep API-created ids, navigate to the
  exact lesson, attach the already-validated local asset through the supported upload action,
  wait for processing, read back the native association. Never rebuild the whole course.

Record: source asset hash, target lesson, processing outcome, actual route.

## 5. Proof fields (never collapse)

`asset_persisted` · `native_content_ready` · `lesson_association_verified` ·
`learner_render_verified`

A permanent URL proves only `asset_persisted`. An admin preview does not prove a paid member can
open the course.

## 6. Minimal synthetic shapes

```json
{"title":"ZHC Launch 101","description":"Approved description","posterImage":"https://approved.example/course-cover.png"}
```

```json
{"title":"Welcome","visibility":"draft","sequenceNo":1}
```

```json
{"title":"Introduction","categoryId":"SYNTHETIC_CATEGORY_ID","description":"Approved text","visibility":"draft","sequenceNo":1}
```

Failure cases to exercise:

- lesson without `categoryId` → refuse locally;
- `contentType:"video"` with no verified `contentId` → refuse;
- duplicate display title with distinct keys → keep both;
- stale/unknown write outcome → reconcile, never repeat;
- unsupported assessment setting → explicit hybrid work or feature gap, never silent omission.

Readback: re-read course, ordered categories, lesson parent/visibility, native content state, and
(where requested) the learner destination.

## 7. Offers, enrollment, assessment

- Use course offer/enrollment operations, not renamed commerce calls.
- `POST /courses/enrollments` with a contact + offer is not payment proof.
- Revoking an offer can remove several included products: compute the affected set first.
- Lesson quizzes use the quiz-create + question-upsert relationship. A quiz label in `metaData`
  is not an assessment. This is not a marketing quiz (WF34).

## 8. QC checklist

- [ ] Plan-to-object equality: every logical key maps to a real id; parent/order/visibility correct.
- [ ] Intended text present; required media processed and attached; required resources accessible.
- [ ] Group association and access verified when requested.
- [ ] No obsolete test still asserts "courses have no public API".
- [ ] Every route used has a registry row; every missing row is named as a gap.
- [ ] Cleanup acts only on objects created by this run and recorded in its ownership manifest.

## 9. Current-main note (labelled historical)

`tools/ghl_course_builder.py` opens with "GoHighLevel has NO known public create API". That
statement predates the documented course contract and is the stale claim revision 3.0 replaces.
The code/docstring flip belongs to WF07; this reference and the Skill 6 prose carry the corrected
doctrine meanwhile.

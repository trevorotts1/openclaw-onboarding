# SOP-GHL-03 — Course Production

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Courses department owns outcomes/content; Skill 6 coordinates construction and deployment · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request to create or update a course, its modules, lessons, or lesson media in GHL —
including "create a course with 3 modules and attach my videos".

**Inputs:**
- Signed curriculum handoff: business outcome, audience, prerequisite, module map, one outcome per
  lesson, assessment binding.
- Media assets with a permanent location, type, checksum and rights status.
- `location_id`, `company_id`, target course product, category and visibility decision.

**Required pointers:**
- Skill 6 `ghl_course_builder.py` / `ghl_object_router.py` (course coordinator and route selection).
- Skill 44 public course operations (`public/courses.py`, command module) and shared transport.
- KIE/course-asset handoff manifest (Skill 07/46/66/67/68/74) — assets only, never GHL entities.
- `universal-sops/ghl-hybrid-operations/SOP-GHL-04-COMMUNITY-AND-LEARNING.md` — group association.

**Ordered steps:**
1. Confirm the signed module map exists. Do not write lesson one before sign-off is recorded.
2. Create the course shell with public DTOs only. Do not invent course draft or media fields.
3. Create modules, then lessons, in order; keep a stable local key per module/lesson so duplicate
   display titles stay distinct and a resume cannot duplicate objects.
4. Persist media to its permanent location first; then bind it to the lesson through the proven
   upload/import/browser operation. Listing a URL in a plan is not binding.
5. Verify each lesson readback: title, category, visibility, content, bound media, order.
6. Run learner-visible checks on the student view once, end to end.
7. Publish/release only the approved visibility; record requested vs actual visibility.
8. Emit one receipt per logical object (course, module, lesson, media binding) with `readback.state`.

**Allowed route changes:**
- Public course operations first; import/browser binding only for media/content gaps; existing
  Firebase/internal fallback only where a documented gap exists.
- Never create the shell through one rail and the lessons through another as a workaround for a lost
  response.

**Required output / receipt:** course/product id, module and lesson ids, media binding evidence,
learner-check evidence, changelog row for content changes, receipts with `actual_visibility`.

**Approval boundary:** releasing a course/lesson to learners, changing price/offer, publishing
student-facing content, and deleting/archiving a course require an explicit owner decision. Draft
creation does not.

**Failures:**
- Recoverable: import still processing → record `processing`, re-check; media upload retry inside the
  documented budget; duplicate lesson title → reuse the stable key.
- Terminal: missing required lesson content/media → refuse completion (a plan or a title is not
  content); published lesson edited in place → stop and version-bump; wrong tenant → stop, never
  re-parent the object.
- Never report "course created" from an import job or a draft shell alone.

**Acceptance:** modules/lessons/assessments exist with real content and bound media; duplicate titles
remain distinct; resume creates no duplicates; the learner view works; receipts prove binding, not
listing.

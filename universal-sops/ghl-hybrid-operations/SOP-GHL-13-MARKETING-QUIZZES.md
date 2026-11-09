# SOP-GHL-13 — Marketing Quizzes

**Cluster:** `universal-sops/ghl-hybrid-operations/` · **Owner:** Skill 6 (quiz coordinator; page owner for placement) · **Revision:** 3.0 (2026-11-08)

**Trigger:** A request for a lead-generation/assessment quiz that is NOT a course lesson quiz —
including "create a lead-generation quiz, not a course quiz".

**Inputs:** outcome (lead capture, segmentation, qualification), question set, scoring rules,
branching logic, result-page logic, CRM effects (tags/fields/workflows), placement page/site.

**Required pointers:** Skill 6 managed quiz coordinator/reference/selector file; `SOP-GHL-03` for a
course lesson quiz (different object and grading path); the page owner for placement; Skill 44 for
CRM wiring.

**Ordered steps:**
1. Classify: marketing quiz vs course lesson quiz. A marketing quiz captures leads and outcomes; a
   lesson quiz measures learning inside a course. Never reuse the lesson-quiz path for a lead quiz.
2. Define outcome, scoring, branching and the result logic BEFORE building.
3. Pre-create every `zhc_` field/tag the quiz writes (GET-first), and document them in the Data
   Dictionary.
4. Build the native quiz: questions, answers, scoring, branches, result mapping.
5. Wire CRM effects: field writes, tag application, workflow trigger — after the quiz id exists.
6. Submit one controlled test submission. Verify stored answers, computed outcome/score, field/tag
   effects, workflow enrollment, and the result page.
7. Install on the intended page/site with exactly one embed; scan for duplicates.
8. Emit receipts: quiz built, CRM wiring verified, test submission verified.

**Allowed route changes:** Skill 6 native builder first; page owner for placement; Skill 44 for CRM
wiring; private fallback only for a documented gap. Never create a second quiz to replace a lost
response.

**Required output / receipt:** quiz id, question/branch map, outcome mapping, `zhc_` objects created,
test-submission evidence, page placement ref, receipts.

**Approval boundary:** publishing the quiz publicly, wiring a live workflow, and capturing real leads
require owner approval. Draft quiz creation does not.

**Failures:** Recoverable — missing dependency → create via the approved dependency step and re-run the
test; embed duplicate → remove the duplicate. Terminal — undefined outcome/scoring, a lesson-quiz
requirement misrouted here, or CRM effects that cannot be verified → stop. A quiz that scores but
writes no CRM effect is not complete.

**Acceptance:** native quiz produces the intended outcome/score and lead-capture effects end to end,
distinct from course lesson quizzes, installed once on the intended page.

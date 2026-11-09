# Marketing quiz build — Skill 06 / WF34

**Status:** implementation complete and offline-verified on a SYNTHETIC fixture.
**Live status:** NOT RUN. No live GoHighLevel write, no client account, no real
contact, no owner notification happened in this lane.

Companion code: `tools/ghl_marketing_quiz_builder.py`
Dedicated selectors: `tools/selectors-live-marketing-quiz.json`
Frozen interface (CP01): `tests/fixtures/marketing-quiz/cp01-interface.json`
Acceptance fixture: `tests/fixtures/marketing-quiz/fake-browser-crm-acceptance.json`
Example plan: `tests/fixtures/marketing-quiz/plan.example.json`
Tests: `tests/test_marketing_quiz_builder.py`

---

## 1. What a standalone marketing quiz is — and is not

A **standalone marketing quiz** is a lead-generation quiz: scored questions,
branching, personal result copy, contact capture plus consent, and a routed
follow-up.

It is **not** any of the following, and the builder refuses all of them:

| Lookalike | Why it is not proof | What this lane does |
|---|---|---|
| `funnel-templates/lead/survey-quiz.{md,json}` | a page-layout recipe, no builder | the layout is still used for pages; the quiz contract lives here |
| `23-ai-workforce-blueprint/.../quiz-builder/` role template | a department role | untouched |
| `job_type='quiz'` auto-routed to `ghl_survey_builder.build_survey` | produces a plain survey: no scoring, no outcome, no result copy, no consent, no lead verification | this coordinator now owns that contract and registers through WF07 |
| any `courses.*` / `lesson_quiz` / `lessons/quiz` endpoint | course lesson quiz, not lead capture | refused before a plan is emitted (`CourseQuizEndpointRefused`) |

A new public marketing-quiz contract, if HighLevel later publishes one, becomes
another executor under the same `ACCEPTED_RAIL`-gated contract — it never
silently replaces it.

---

## 2. Plan contract (`skill6-marketing-quiz-plan/1`)

```json
{
  "schema": "skill6-marketing-quiz-plan/1",
  "quiz_name": "ZHC Growth Stage Quiz",
  "location_id": "LOC_TEST_0001",
  "rail": "managed_browser",
  "page_gates": { "...": "see section 6" },
  "questions": [
    {"id": "q1", "prompt": "...", "type": "single_choice", "required": true,
     "field_key": "zhc_quiz_q1_stage",
     "choices": [{"id": "a", "label": "...", "score": 0}]},
    {"id": "q2", "prompt": "...", "type": "single_choice", "required": true,
     "choices": [{"id": "c", "label": "Paid ads", "score": 4}],
     "branch": {"when_choice": "c", "goto": "q4"}}
  ],
  "outcomes": [
    {"key": "operator", "title": "Operator", "result_copy": "...",
     "score_min": 8, "score_max": 11, "tags": ["zhc_quiz_operator"],
     "router": {"question_id": "q2", "choice_id": "c"},
     "result_page": {"path": "pages/result-operator.html"}}
  ],
  "capture": {
    "required": true,
    "consent": {"required": true, "text": "...", "field_key": "zhc_quiz_consent"},
    "fields": [{"field_key": "zhc_quiz_email", "source": "Email", "required": true}]
  },
  "field_tag_mapping": {
    "outcome_field_key": "zhc_quiz_outcome",
    "score_field_key": "zhc_quiz_score",
    "custom_fields": [{"field_key": "zhc_quiz_outcome", "data_type": "text"}],
    "tags": [{"tag": "zhc_quiz_lead"}]
  },
  "followup_workflows": [
    {"key": "wf_quiz_operator", "outcome": "operator", "approved": true}
  ]
}
```

Question types: `single_choice`, `multi_choice`, `short_text`, `email`,
`consent`. Only `single_choice` / `multi_choice` are scored.

Every dependent key/tag uses the idempotent `zhc_` prefix so Skill 44 reuses an
existing field rather than creating a duplicate.

---

## 3. Outcome mapping (the deterministic contract)

```
1. A router answer wins: outcome.router = {question_id, choice_id}.
2. Otherwise the CONTIGUOUS score band decides: score_min <= score <= score_max.
3. Score = sum of the chosen scored choices along the path actually walked
   (a branch jump skips the questions it jumps over).
```

Validation requires the outcome ranges to be **contiguous, non-overlapping, and
to cover the entire reachable score band**. A gap, an overlap, or a range whose
upper edge exceeds the reachable maximum is a refusal, not a warning. The
reachable band is computed from the branch DAG, so a branch that skips high-value
questions correctly lowers the maximum.

`outcome_boundaries()` returns, for every outcome, a concrete answer set for its
minimum and its maximum edge, each scored through the real scoring path. That is
the proof that no boundary is a fiction.

`--cp01` freezes this mapping in `tests/fixtures/marketing-quiz/cp01-interface.json`
(score band, per-outcome ranges, routers, boundary answer sets, dependent fields,
fixture sha256) for WF07 / WF09 / WF22 / WF23 to consume.

### Router precedence and boundaries

Because a router answer can override the band, boundary search is a bounded DFS
that accepts only a path whose real `select_outcome` result is the requested
outcome. A boundary that cannot be produced without tripping a router raises
`OutcomeContradiction` instead of being reported as reachable.

---

## 4. Branching

`branch = {when_choice, goto}` on a scored question. Rules:

- `when_choice` must be a choice id of that question.
- `goto` must be a question id **strictly later** in the plan. Backward or
  self jumps are refused: they loop forever and GHL's Jump-To cannot express a
  loop either.

The translation layer adds one native Jump-To rule per branch and sets
`converge_slide = "Contact Capture"` so a branch cannot fall through into a
sibling branch's required fields (which would make the quiz unsubmittable).

---

## 5. Capture, consent, fields, tags, workflows

- `capture.required = true` **forces** `consent.required = true` with non-empty
  text. A submission without consent raises `ConsentRequired` and creates no
  contact — an unconsented lead is never recorded.
- A missing required capture value raises `CaptureIncomplete`.
- Consent is stored in its own boolean field (`zhc_quiz_consent` by default).
- On submission the coordinator writes:
  `zhc_quiz_outcome` (outcome key), `zhc_quiz_score` (integer), the captured
  fields, the plan-level tags plus the outcome's tags, and enrolls the contact
  in **only** that outcome's approved workflows.
- Only `approved: true` follow-up workflows may be planned. An unapproved or
  unknown workflow key is a refusal.
- Sensitive data is refused by name: government identifiers, payment
  credentials, bank details, health details, passwords, dates of birth.

---

## 6. Page gates (IG-PAGE-01) — enforced in the plan

`page_gates` is required and must contain all of:

| Gate | Required shape |
|---|---|
| `wireframes` | `{desktop, mobile}` both non-empty |
| `mockups` | `{desktop, mobile}` both non-empty |
| `design_style_intake` | `{style: block|hybrid|circular, approved: true}` |
| `copy_budget` | positive `headline_max`, `body_max`, `image_prompt_max` |
| `native_full_width` | `true` (CSS in a code block is not a substitute) |
| `seo` | title 1..60, description 1..155, `https://` canonical |
| `native_checkout` | `{mode: "native", bypassed: false}` |

Any missing or false gate raises `PageGateIncomplete` before a build step exists.

---

## 7. Execute plan and the single clicker

`build_quiz(plan, evidence_root, dry_run=True)` is dry-run by default. It emits an
ordered 11-step plan; steps 4–6 delegate to `ghl_survey_builder.build_survey`
(the ONE managed clicker), step 8 to the page builder, step 9 to Skill 44, and
steps 10–11 are verification. Every step names a selector id that must exist in
`tools/selectors-live-marketing-quiz.json`; an unknown id refuses the plan.

Selector status is honest: anchors shared with the LOCKED survey flow are marked
`verified_live: true` with their provenance; quiz-specific nodes (title control,
add slide, conditional logic, capture slide, result page copy, submit control) are
`runtime_capture: true`, `verified_live: false`, with a `find` search seed and no
invented CSS. A live capture pass replaces those with locked anchors and bumps the
file version.

### Why scoring is not a native survey feature

GHL surveys do not compute a weighted score. The coordinator therefore computes
outcome and score deterministically, stores them as custom fields, and routes the
follow-up by workflow. Result pages carry the per-outcome copy. No course-quiz
API and no invented survey scoring setting is claimed.

---

## 8. Verification (`verify_acceptance`)

Against a `trust: "FAKE"` fixture it proves:

1. every outcome boundary is reachable (min and max), scored through the real path;
2. every outcome has at least one passing submission;
3. every submission's computed outcome equals the fixture's declared outcome;
4. lead capture and routing: exactly one contact per submission, with the mapped
   fields/tags and only the intended approved workflows;
5. every declared branch is exercised by some submission;
6. desktop and mobile render carry a hydrated DOM, native full width, and no
   console errors; each outcome's rendered result copy matches the plan;
7. every required question is actually enforced (a walk missing it fails).

It always returns `live: false`. A fixture that does not declare `trust: FAKE` is
refused (`FixtureNotSynthetic`) — a fake run is never reported as live proof.

---

## 9. Acceptance map

| Requirement | Where it is proved |
|---|---|
| B21 — marketing quiz separate from lesson quiz; outcomes and lead/field/tag/workflow effects verify | `tests/test_marketing_quiz_builder.py::test_b21_*`, module `--selftest` |
| IG-PAGE-01 — wireframes, mockups, design-style intake, copy/prompt budgets, native full-width, SEO gates enforced | `test_ig_page_01_*` |
| IG-PAGE-02 — intended contact, field, tag, result and workflow outcome proved | `test_ig_page_02_*` |

Live canary: **NOT RUN** — no approved live GoHighLevel write in this lane.
Offline tests and a FAKE fixture are labelled separately and are never described
as live proof.

---

## 10. Cross-lane pieces (not edited here)

| Need | Owner | State |
|---|---|---|
| Register `quiz` → `ghl_marketing_quiz_builder.build_quiz` in `v2_dispatcher`; add a `quiz` ObjectRoute | WF07 / GHL-007 | change request filed from this lane |
| Shared gate rows / any shared selector JSON entry | WF09 / GHL-009 | existing gates reused; no shared file edited |
| Skill version / index bump | WF21 / GHL-021 | not touched here |

Until WF07 lands the registration, `job_type='quiz'` still resolves to the plain
survey builder **without** this contract — the coordinator is callable directly
(`build_quiz`) and by an explicit `builder=` injection.

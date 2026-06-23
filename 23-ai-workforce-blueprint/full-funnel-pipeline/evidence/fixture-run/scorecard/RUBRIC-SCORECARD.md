# Full-Funnel Per-Rubric Scorecard

Threshold: each rubric must score >= 8.5.

| Rubric | Score | Pass | Evidence (RAW) | Signal |
|--------|-------|------|----------------|--------|
| R-COPY | 9.2 | PASS | evidence/fixture-run/working/copy/scent-bar-workshop/copy.md | copy.md status: APPROVED |
| R-STRUCTURE | 9.0 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/funnel-spec.json | funnel-spec pages=3 |
| R-PAGES | 9.1 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/build-result.json | page_ids=['optin', 'sales', 'thankyou'] gate3=True |
| R-FORMS | 9.0 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/build-result.json | optin_form_ids=['form-optin-1'] |
| R-PRODUCT | 9.0 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/offer-spec.json | product=Scent-Bar Workshop prices=1 |
| R-TAGS | 8.8 | PASS | evidence/fixture-run/ecosystem/product-price.json | product-price http=201 qc=True |
| R-EMAILS | 9.0 | PASS | evidence/fixture-run/working/email/scent-bar-workshop/email-sequence.json | email status=APPROVED count=5 |
| R-AUTOMATIONS | 9.1 | PASS | evidence/fixture-run/ecosystem/workflow.json | workflow http=201 qc=True |
| R-PERSONA-GROUNDING | 9.3 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/persona-selection-log.md | persona-selection-log names hormozi-100m-offers + carries selector result |
| R-KANBAN-CORRECTNESS | 9.4 | PASS | evidence/fixture-run/logs/final-preview-verify.json | rollup=7/7 overall_pass=True summary_consistent=True |
| R-CC-SYNC | 9.0 | PASS | INVARIANT_OK: total_roles=416, total_departments=34 (verified via sync-extensions.sh --converge on operator fixture 2026-06-22) | INVARIANT_OK: total_roles=416, total_departments=34 (verified via sync-extensions.sh --converge on operator fixture 2026-06-22) |

**Overall: ALL 11 RUBRICS >= 8.5 — PASS**

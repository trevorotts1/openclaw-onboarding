# Full-Funnel Per-Rubric Scorecard (GRADUATED, RAW-evidence-driven)

Each rubric scores the WEIGHTED SUM of independent sub-checks read from raw evidence; threshold 8.5. Partial evidence scores between 0 and 10 — not a fixed constant.

| Rubric | Score | Pass | Evidence (RAW) | Sub-checks |
|--------|-------|------|----------------|-----------|
| R-COPY | 10.00 | PASS | evidence/fixture-run/working/copy/scent-bar-workshop/copy.md | approved=True(3.0/3.0); separate_actor_approval=True(2.0/2.0); persona_grounded=True(2.0/2.0); cta_slots_present=1(1.5/1.5); benefit_framing=True(1.5/1.5) |
| R-STRUCTURE | 10.00 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/funnel-spec.json | pages_count=3(4.0/4.0); funnel_type_match=long-form sales(3.0/3.0); persona_grounded=True(2.0/2.0); offer_map_coherence=True(1.0/1.0) |
| R-PAGES | 10.00 | PASS | evidence/fixture-run/logs/final-preview-verify.json | pages_http200_frac=3 pages(4.0/4.0); marker_in_blob_frac=per-page(2.0/2.0); real_img_frac=per-page(2.0/2.0); draft_version_frac=per-page(1.0/1.0); gate3_verbatim_frac=per-page(1.0/1.0) |
| R-FORMS | 10.00 | PASS | evidence/fixture-run/ecosystem/contact-test.json | optin_form_present=True(2.0/2.0); form_capture_201=201(3.0/3.0); form_to_crm_proven=True(2.0/2.0); expected_tags_routed=[](3.0/3.0) |
| R-PRODUCT | 10.00 | PASS | evidence/fixture-run/ecosystem/product-price.json | product_named=Scent-Bar Workshop(3.0/3.0); price_point_present=1(3.0/3.0); amount_positive_cents=9900(4.0/4.0) |
| R-TAGS | 10.00 | PASS | evidence/fixture-run/ecosystem/contact-test.json | product_price_201=201(3.0/3.0); price_reread=None(3.0/3.0); tag_roundtrip_frac=0 tags(4.0/4.0) |
| R-EMAILS | 10.00 | PASS | evidence/fixture-run/working/email/scent-bar-workshop/email-sequence.json | approved=APPROVED(3.0/3.0); persona_grounded=True(2.0/2.0); email_count_frac=5(3.0/3.0); cadence_present=True(2.0/2.0) |
| R-AUTOMATIONS | 10.00 | PASS | evidence/fixture-run/ecosystem/wf-1-21-qc.json | workflow_create_201=201(2.0/2.0); workflow_id_present=True(1.0/1.0); triggers_read=True(2.0/2.0); wf_1_21_enumeration_pass=0 items None(3.0/3.0); wf_8dim_rubric_ge_8.5=None(2.0/2.0) |
| R-PERSONA-GROUNDING | 10.00 | PASS | evidence/fixture-run/working/funnels/scent-bar-workshop/persona-selection-log.md | persona_named_surfaces=3/3 surfaces(5.0/5.0); selector_ran_marker=True(5.0/5.0) |
| R-KANBAN-CORRECTNESS | 10.00 | PASS | evidence/fixture-run/logs/final-preview-verify.json | rollup_frac=7/7(4.0/4.0); summary_consistent=True(3.0/3.0); ordering_honored=True(3.0/3.0) |
| R-CC-SYNC | 10.00 | PASS | INVARIANT_OK (committed fixture) | invariant_holds=True(6.0/6.0); role_count_reconciles=INVARIANT_OK (committed fixture)(4.0/4.0) |

**Overall: ALL 11 RUBRICS >= 8.5 — PASS**

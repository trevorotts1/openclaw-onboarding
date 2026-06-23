# Full-Funnel Per-Rubric Scorecard (GRADUATED, RAW-evidence-driven)

Each rubric scores the WEIGHTED SUM of independent sub-checks read from raw evidence; threshold 8.5. Partial evidence scores between 0 and 10 — not a fixed constant.

| Rubric | Score | Pass | Evidence (RAW) | Sub-checks |
|--------|-------|------|----------------|-----------|
| R-COPY | 10.00 | PASS | working/copy/focusforge/copy.md | approved=True(3.0/3.0); separate_actor_approval=True(2.0/2.0); persona_grounded=True(2.0/2.0); cta_slots_present=5(1.5/1.5); benefit_framing=True(1.5/1.5) |
| R-STRUCTURE | 9.17 | PASS | working/funnels/focusforge/funnel-spec.json | pages_count=3(4.0/4.0); funnel_type_match=long-form sales(3.0/3.0); persona_grounded=True(2.0/2.0); offer_map_coherence=True(1.0/1.0); live_published_status=DRAFT-only (reversible)(1.0/2.0) |
| R-PAGES | 8.85 | PASS | logs/final-preview-verify.json | pages_http200_frac=3 pages(4.0/4.0); marker_in_blob_frac=per-page(2.0/2.0); real_img_frac=per-page(2.0/2.0); draft_version_frac=per-page(1.0/1.0); public_publish_frac=per-page publish status(1.5/3.0); gate3_verbatim_frac=per-page(1.0/1.0) |
| R-FORMS | 9.20 | PASS | ecosystem/contact-test.json | optin_form_present=True(2.0/2.0); form_capture_201=201(3.0/3.0); form_to_crm_proven=substituted (public-widget 403); attribution+tags(1.2/2.0); expected_tags_routed=['focusforge-applicant', 'focusforge-optin', 'textable-no'](3.0/3.0) |
| R-PRODUCT | 10.00 | PASS | ecosystem/product-price.json | product_named=FocusForge(3.0/3.0); price_point_present=1(3.0/3.0); amount_positive_cents=150000(4.0/4.0) |
| R-TAGS | 10.00 | PASS | ecosystem/contact-test.json | product_price_201=201(3.0/3.0); price_reread=200(3.0/3.0); tag_roundtrip_frac=2 tags(4.0/4.0) |
| R-EMAILS | 10.00 | PASS | working/email/focusforge/email-sequence.json | approved=APPROVED(3.0/3.0); persona_grounded=True(2.0/2.0); email_count_frac=5(3.0/3.0); cadence_present=True(2.0/2.0) |
| R-AUTOMATIONS | 10.00 | PASS | ecosystem/wf-1-21-qc.json | workflow_create_201=201(2.0/2.0); workflow_id_present=True(1.0/1.0); triggers_read=True(2.0/2.0); wf_1_21_enumeration_pass=21 items PASS(3.0/3.0); wf_8dim_rubric_ge_8.5=9.3(2.0/2.0) |
| R-PERSONA-GROUNDING | 8.20 | FAIL | working/funnels/focusforge/persona-selection-log.md | persona_named_surfaces=6/3 surfaces(5.0/5.0); selector_grounding_strength=ran (DEGRADED: only task_fit live ~0.8; layers 1-4 neutral-0.6 floor -> layer-quality mean 0.64)(3.2/5.0) |
| R-KANBAN-CORRECTNESS | 10.00 | PASS | kanban/board.json | rollup_frac=3/3(4.0/4.0); summary_consistent=True(3.0/3.0); ordering_honored=True(3.0/3.0) |
| R-CC-SYNC | 10.00 | PASS | logs/cc-invariant.json | invariant_holds=True(6.0/6.0); role_count_reconciles=416==416(4.0/4.0) |

**Overall: ONE OR MORE RUBRICS BELOW 8.5 — FAIL**

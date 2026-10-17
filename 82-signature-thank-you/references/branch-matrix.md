# Branch Matrix — Skill 82 Final Thank-You (S82-09)

**Scope.** Every case that touches the terminal thank-you from packet
doc 18 (`18_END_TO_END_ACCEPTANCE_MATRIX.md` sections 2, 4, 5, 7) and
spec 12 section 10, with an honest coverage status for each:

- **COVERED-L1** — an executable deterministic test in this skill
  proves the case offline; the exact test file and test name are
  cited. (Verified by reading the test files, not their docstrings.)
- **COVERED-DOC** — a contract in this skill's references governs the
  case, but no L1 test proves it; the reason is stated.
- **PENDING-L3/L4** — the case cannot close offline; the missing live
  proof is named.

**Level warning (doc 18 sections 1 and 3).** A13's minimum evidence
is **L4** and A20's is **L4**; A14's is L1 positive/negative plus
semantic review. The COVERED-L1 rows below are the offline halves of
those units — they do not close A13/A20, whose live halves are rows
P-01/P-02. Nothing in this matrix upgrades an L1 result into an L4
claim.

## A. COVERED-L1 (31)

| ID | Case (source) | Evidence — test file :: test |
|---|---|---|
| L1-01 | All 64 normal-path cases: same main package, bump inclusion, no simultaneous U1/D1, amounts/terms, purchased entitlements present, unpurchased absent (doc 18 §2) | tests/test_thank_you.py :: AllFixtureCasesTest.test_all_64_cases |
| L1-02 | Five terminal purchase sets, U2 enabled — none; U1; U1+U2; D1; D1+U2 — each × bump, in the view and in the rendered page (doc 18 §2; spec §10) | tests/test_thank_you.py :: FiveTerminalPurchaseSetsTest.test_five_sets_times_bump; tests/test_render.py :: FiveTerminalPurchaseSetsRenderTest.test_five_sets_render_exactly_purchased |
| L1-03 | Three terminal purchase sets, U2 disabled — none; U1; D1 (doc 18 §2) | tests/test_thank_you.py :: AllFixtureCasesTest.test_all_64_cases (the 24 `u2_enabled=false` fixtures) |
| L1-04 | Original order plus bump arriving in ONE event stay together; bump not dropped (spec §10; doc 18 §2) | tests/test_event_adapter.py :: EventAdapterTest.test_1_main_plus_bump_single_event |
| L1-05 | Delayed/later extra event under the same native order appends to that order's snapshot (spec §10, offline half) | tests/test_event_adapter.py :: EventAdapterTest.test_2_later_u1_event_same_order_merges |
| L1-06 | Decline-all: buyer declines U1 and D1, terminal set is the original purchase only (spec §10) | tests/test_thank_you.py :: FiveTerminalPurchaseSetsTest.test_five_sets_times_bump (empty-extras set); :: AllFixtureCasesTest.test_all_64_cases (`u1_no_d1_no` decisions) |
| L1-07 | Duplicate event: identical redelivery deduped (totals not doubled); conflicting redelivery raises, never silently merges (spec §10; doc 18 §4) | tests/test_thank_you.py :: NegativeTest.test_duplicate_event_deduped; tests/test_event_adapter.py :: EventAdapterTest.test_5_duplicate_event_deduped_conflict_raises |
| L1-08 | Event provenance: snapshot `event_ids` manifest must equal the line items' event IDs — over-claim, under-claim, shared ID, and tampered view provenance all fail closed (review observation O-01) | tests/test_event_provenance.py :: EventProvenanceTest (test_manifest_with_extra_id_rejected, test_manifest_missing_a_line_id_rejected, test_two_lines_sharing_one_event_id_rejected, test_view_provenance_event_ids_tampered_rejected, test_identical_duplicate_still_dedupes) |
| L1-09 | Refunded extra only — full and partial: extra's access removed, confirmation not "all set", original purchase's row, amount, and access untouched (spec §10) | tests/test_repairs.py :: RepairD04RefundHonestyTest.test_repair_d04_partially_refunded_extra_not_all_set; :: .test_repair_d04_refunded_extra_keeps_paid_main_confirmation_honest |
| L1-10 | Pending asynchronous payment: item labeled Pending, kept out of the paid total, no access block; base confirmed and accessible (doc 18 §4) | tests/test_thank_you.py :: NegativeTest.test_pending_charge_never_shown_confirmed; tests/test_render.py :: PendingAndFailedRenderTest.test_pending_set_never_all_set_and_base_access_kept; tests/test_event_adapter.py :: EventAdapterTest.test_9_line_payment_status_wins_over_event_status |
| L1-11 | Negative: a pending charge relabeled as a successful confirmation is rejected (`false_confirmation`) (spec §10; doc 18 §4) | tests/test_thank_you.py :: NegativeTest.test_pending_charge_never_shown_confirmed (tampered-confirmation half) |
| L1-12 | Failed extra, including U2 failing after U1 paid: base (and U1) access preserved, failed item labeled, no access for it (spec §10 "no valid base access when U2 fails"; doc 18 §4 declined-payment effect side) | tests/test_thank_you.py :: NegativeTest.test_extra_failed_base_access_preserved; tests/test_render.py :: PendingAndFailedRenderTest.test_failed_extra_keeps_base_access |
| L1-13 | Delayed extra / unknown outcome: bounded reconciling state — retry budget shown, support route present, refreshing never starts a purchase, no buy CTA (spec §10; doc 18 §4) | tests/test_render.py :: ReconcilingRenderTest.test_reconciling_fragment_has_retry_support_no_buy; :: .test_reconciling_banner_over_partial_view |
| L1-14 | Provider outage: last verified cached view renders labeled as such, with an explicit "Unresolved items" list; never presented as freshly confirmed (spec 12 §5) | tests/test_render.py :: OutageRenderTest.test_outage_cached_labels_unresolved_items |
| L1-15 | Wrong order reference: a view carrying another order's ref/number/journey is rejected; the error state shows support and no receipt (spec §10) | tests/test_repairs.py :: RepairD03OrderIdentityTest (test_repair_d03_order_ref_mismatch_rejected, test_repair_d03_order_number_mismatch_rejected, test_repair_d03_journey_mismatch_rejected); tests/test_render.py :: ErrorRenderTest.test_each_error_kind_has_support_and_no_receipt (`wrong_order_reference`) |
| L1-16 | Wrong tenant: a snapshot from another tenant is rejected (`wrong_tenant`) (spec §10; doc 18 §7 cross-tenant) | tests/test_thank_you.py :: NegativeTest.test_wrong_tenant_rejected |
| L1-17 | Stale session: expired-context error UX — explanation, sign-in/support fallback, no order data (spec §10; enforcement side is DOC-08/P-03) | tests/test_render.py :: ErrorRenderTest.test_each_error_kind_has_support_and_no_receipt (`stale_session`); :: .test_error_via_render_thank_you_state |
| L1-18 | Direct URL without purchase / redirected success URL without purchase: no verified snapshot (or an unverified one) builds nothing (spec §10; doc 18 §4, §7) | tests/test_thank_you.py :: NegativeTest.test_unverified_and_query_only_inputs_rejected; :: .test_query_string_premium_claim_rejected (no-snapshot half) |
| L1-19 | Native read failure with support fallback: error fragment carries support, no items, no amounts, no fake sample receipt (spec §10) | tests/test_render.py :: ErrorRenderTest.test_each_error_kind_has_support_and_no_receipt (`native_read_failure`) |
| L1-20 | Negative: query-string premium access (`vip=true`, offer/entitlement claims in URL) rejected at resolver, validator, and access-link layers (spec §10) | tests/test_thank_you.py :: NegativeTest.test_query_string_premium_claim_rejected; tests/test_access.py :: ValidateAccessTests.test_vip_claim_in_url_fails; :: .test_email_claim_in_url_fails |
| L1-21 | Negative: unpurchased U1 displayed on a D1 path is rejected by both validators (spec §10) | tests/test_thank_you.py :: NegativeTest.test_unpurchased_u1_on_d1_path_rejected |
| L1-22 | Negative: a new upsell button / recommendation block on the final page is rejected; every rendered CTA carries an allowed classification and none is a new-charge class (spec §10; A14) | tests/test_thank_you.py :: NegativeTest.test_new_upsell_cta_rejected; tests/test_render.py :: CtaClassificationRenderTest.test_all_rendered_ctas_use_allowed_classes |
| L1-23 | Negative: historical purchases grouped by shared email — impossible by construction (adapter has no email input) and two orders from one buyer never merge (spec §10) | tests/test_event_adapter.py :: EventAdapterTest.test_4_no_email_input_two_orders_stay_separate; :: .test_3_extra_under_different_order_not_merged |
| L1-24 | Negative: duplicate onboarding send from page refresh — page side: the `confirmation_shown` observation is idempotent (same view → same dedupe key) and emits no send (spec §10; send-side proof is P-05) | tests/test_continuity.py :: ConfirmationObservationTests.test_same_view_same_key_idempotent; :: .test_record_shape_and_no_send |
| L1-25 | U2 from each qualified path: paid U1 → U2 and paid D1 → U2 both reach the same terminal set with U2 access (spec §10; doc 18 §2) | tests/test_repairs.py :: RepairD02U2QualificationTest.test_repair_d02_u2_with_paid_qualifier_still_passes |
| L1-26 | Contradictory U2: a U2 purchase with no paid U1 or D1 in the same journey (including a merely pending qualifier) is rejected by resolver and both validators (doc 18 §5) | tests/test_repairs.py :: RepairD02U2QualificationTest.test_repair_d02_resolver_rejects_u2_without_qualification; :: .test_repair_d02_resolver_rejects_u2_with_pending_qualifier; :: .test_repair_d02_validator_rejects_u2_without_qualification |
| L1-27 | U2 disabled variant: terminal sets resolve without U2 and no U2 access appears (doc 18 §5) | tests/test_thank_you.py :: AllFixtureCasesTest.test_all_64_cases (24 `u2_enabled=false` fixtures) |
| L1-28 | Access destinations: https only, no identity/entitlement claims in URLs, destination must independently authorize, no access block for an entitlement not in the view, mailto never an access block (doc 18 §7; A13 access side) | tests/test_access.py :: ValidateAccessTests (test_honest_manifest_passes, test_http_access_destination_fails, test_missing_independent_authorization_fails, test_access_for_unviewed_entitlement_fails, test_mailto_as_access_block_fails, test_cli_exit_codes) |
| L1-29 | Unsafe HTML in client-supplied text: malicious display names, brand strings, and `javascript:` URLs are escaped/neutralized in the render (doc 18 §7) | tests/test_render.py :: EscapingRenderTest.test_malicious_display_name_is_escaped; :: .test_malicious_brand_and_url_are_neutralized |
| L1-30 | Private data in the page's own records: the confirmation observation contains no PII-shaped fields (doc 18 §7) | tests/test_continuity.py :: ConfirmationObservationTests.test_record_contains_no_pii_fields |
| L1-31 | S44 ev1 `entitlement_version` reaches the page-side dedupe key: the resolver carries a well-formed ev1 value (S44 producer envelope or explicit version input) into the view's order-level field, so the `confirmation_shown` key equals the worker-side ev1 key; no version supplied → view identical to the shipped fixture view and the derived-fingerprint fallback unchanged; malformed/forged version shapes and a cross-tenant/launch envelope fail closed in the resolver and fail order-view schema validation (gap I6; contract §§2–3) | tests/test_ev1_dedupe.py :: Ev1DedupeTests (test_envelope_version_reaches_view_and_key, test_explicit_version_input_reaches_view_and_key, test_absent_version_view_is_fixture_identical, test_absent_version_observation_unchanged, test_malformed_explicit_version_rejected, test_malformed_envelope_version_rejected, test_envelope_for_another_tenant_or_launch_rejected, test_schema_allows_ev1_and_rejects_forged_shapes) |

## B. COVERED-DOC (9)

Contract only — no L1 test proves the case; reason stated per row.

| ID | Case (source) | Contract — reference | Why not L1 |
|---|---|---|---|
| DOC-01 | Cached previous-buyer state: a shared computer's next visitor sees nothing of the previous buyer's receipt; cached data is only ever the same buyer's, same order's (spec §10) | references/states.md §3; references/access-and-privacy.md §6 (shared-computer rule) | The cache itself is host/native state; no offline harness exists to simulate a second buyer against a real cache. The outage render test (L1-14) covers only the same-buyer's cached view. |
| DOC-02 | U1 disabled profile: no D1/U2 can follow; terminal set is the original purchase (doc 18 §5) | spec 12 §3; doc 02 §4 route rules | Enable/disable routing is S49's route graph, not S82's resolver; the resulting terminal set (original only) is L1-covered by L1-02/L1-06. |
| DOC-03 | D1 disabled profile: a U1 decline goes straight to thank-you; terminal sets are none/U1 (doc 18 §5) | spec 12 §3; doc 02 §4 route rules | Same routing ownership as DOC-02; the resulting sets are L1-covered by L1-02/L1-03. |
| DOC-04 | Trial terms display: trial length and next-charge date shown only when the verified snapshot carries them, never invented (doc 18 §5, trial D1 with renewal) | references/layout-and-copy-profiles.md (billing column rules); references/no-pitch-policy.md §2 | The packet fixture catalog carries **no trial price** (all launch-example prices are one-time, empty schedules), so no fixture exists to build an honest L1 test from. |
| DOC-05 | Recurring main offer / one product with multiple payment schedules: interval and each verified schedule entry rendered from the snapshot's billing terms (doc 18 §5) | references/layout-and-copy-profiles.md (billing column rules); renderer `_item_billing_text` implements it | Same fixture gap as DOC-04: no recurring price exists in the packet catalog. Renderer support is implemented but unproven by test — not claimed as L1. |
| DOC-06 | Already-owned U2 / returning buyer: historical entitlements stay separate from this journey's purchases unless a display explicitly labels the difference (doc 18 §5) | references/native-order-summary-integration.md (identity rules) | The negative half (no silent grouping) is L1-proven by L1-23; the labeled-display variant needs an approved display rule that does not exist yet. |
| DOC-07 | Required customer authentication: the item renders as "Action needed", neither paid nor failed, with no access until authentication completes (doc 18 §4) | references/states.md §2 (status-label rules) | No shipped test constructs a `requires_customer_action` snapshot; the status mapping exists in resolver/renderer but is unexercised. |
| DOC-08 | Wrong-location token: identity validation covers tenant **and** location **and** launch before any render (doc 18 §7) | references/access-and-privacy.md §2; resolver `expected_identity` check | The resolver enforces the full identity triple, but the shipped L1 test names only the tenant case (L1-16); location/launch mismatches were probed in independent review, not in a shipped test. |
| DOC-09 | Private customer data in analytics events, error logs, and screenshots (doc 18 §7) | references/access-and-privacy.md; spec 12 §8 (dummy fixture identities, redaction before artifacts) | Analytics/logging/screenshot pipelines are host-side; S82's own record surface is L1-covered by L1-30, the pipelines are not S82 code. |

## C. PENDING-L3/L4 (8)

| ID | Case (source) | Missing live proof |
|---|---|---|
| P-01 | A13 at its required level: final summary and access match the native record and real protected access (doc 18 §3, A13 = L4) | Installed S79/S80/S81 native product mappings, an S06 native order read (including native-summary-vs-snapshot verification), and authorized sandbox payment proof — listed in references/native-order-summary-integration.md; CR-S82-002 tracks the S44 side. |
| P-02 | Abandoned browser after successful base purchase / tab close (spec §10; A20 = L4) | **Filed and S82-reviewed at L4 (2026-10-16).** S44's CR-S82-002 completion filing supplies the read-backs for references/s44-fulfillment-continuity.md §6 items 1–2 (base grant from the purchase event with no thank-you visit; extra-failure journey with the base grant intact), and S82's independent review finds both SUPPORTED for A20 — A20 is READY to present to SWARM. Two caveats ride with it: the native leg is CLAIMED (S44 firsthand read-backs, no raw native payloads on file) pending SWARM's re-read of the cited native IDs, and the extra-failure form is payment-never-completed (draft unpaid invoice, no transaction), not a declined charge — the sandbox has no payment provider. The A20 unit stays `planned` in the ledger until SWARM verifies and INTEGRATION records. Verdicts: handoffs/change-requests/CR-S82-002-L4-COMPLETION-S44.md (Checks 1–2); work/review-cr-s82-002-l4-completion.md (Checks 1–2). |
| P-03 | Order-summary leak to an unauthenticated visitor, live half (spec §10; doc 18 §7) | An L3 test in an authorized test location proving the native authenticated context / opaque-reference path serves no receipt to an unauthenticated request. Offline half is L1-18/L1-20. |
| P-04 | Delayed / out-of-order native event delivery against the states UX (spec §10; doc 18 A19's S82 side) | L4 native delivery of a genuinely delayed and an out-of-order extra event, read back against the reconciling/pending rendering. Offline halves are L1-05/L1-13. |
| P-05 | Duplicate onboarding send, send side: page + S44 worker observing the same completion produce exactly one send (spec §10; A20/A19) | **Filed and S82-reviewed at L4 (2026-10-16).** S44's completion filing (continuity §6 item 3) proves exactly one send on a clean buyer-2 re-run, with the second claim path returning already-claimed against the `confirmation_shown` dedupe discipline; S82's independent review accepts it as SUPPORTED with its disclosure carried verbatim: run 1 produced 2 native sends against 1 claim through an S44 operator recovery error (the pipeline itself never re-sent), and the check proves exactly one *send*, not one delivered confirmation (test-domain delivery failed). Native leg CLAIMED pending SWARM re-read. Page side is L1-24. Verdicts: handoffs/change-requests/CR-S82-002-L4-COMPLETION-S44.md (Check 3); work/review-cr-s82-002-l4-completion.md (Check 3). |
| P-06 | Duplicate-entitlement bump: bump whose entitlement is already included in the selected main package (doc 18 §5) | An approved suppress/explain rule from S49/S79 (doc 02 §3 assigns the rule to the offer layer); S82 has no test or contract for it yet — an upstream-rule gap, not a live-proof gap. |
| P-07 | Zero-price registration, then first paid offer (doc 18 §5) | The free-entry journey is S49/S79 checkout behavior; S82's half (the first paid offer's thank-you) is an ordinary paid set under L1-02, but the end-to-end journey needs L4 proof that free entry manufactured no saved payment context. |
| P-08 | A14 semantic review: a recorded independent verdict on the candidate artifact set (doc 18 §3, A14 = L1 + semantic review) | **Verdict exists — PASS at the offline level.** The independent semantic review was performed 2026-10-15 and recorded in review-s82-final.md §6: reviewer session `fb9b8532…` (≠ every artifact author), artifact = the rendered TEST ONLY fragment, SHA-256 `230ad69b…` (6,292 bytes), pre-screen clean, all six protocol §2 pitch tests PASS with per-surface results recorded. P-08 is closed for the candidate artifact; per semantic-review-protocol.md §6, each real launch's rendered page still needs its own recorded verdict. Verdict: rooms/S82/review-s82-final.md §6. |

## D. Enumerated and ruled out of the S82 surface (not counted)

From doc 18 §4/§5/§7, these cases belong to other owners; S82
consumes only their outcomes (as paid/pending/failed item states,
which are covered above):

- **Declined initial card** — no purchase exists, so no thank-you is
  reached (S79/S06 checkout). The extra-payment decline outcome is
  L1-12.
- **Insufficient stock; unavailable offer** — checkout-domain
  (S79/S06); nothing reaches S82.
- **Changed price between selection and checkout** — S79's
  revalidation; S82 displays only verified snapshot amounts, and a
  tampered displayed amount fails provenance validation (independent
  review probe P1, review-s82-01-03.md).
- **Expired one-click context** — native payment capability (S79/S06);
  S82 never initiates a charge, so it holds no one-click context.
- **Expired deadline** — the deadline display component is S71's
  (doc 16 §1); the terminal thank-you carries no deadline element.
- **Double click (payment button); refresh/back browser mechanics;
  offline browser as a network condition** — browser/native behavior.
  Their S82-visible effects are covered: duplicate effects (L1-07),
  refresh dedupe (L1-24), page-side outage rendering (L1-14).
- **Secret-file permission failure, public CDP/noVNC access, expired
  browser auth** — S06's lane in doc 18 §7; no S82 surface.

## Tallies

- **COVERED-L1: 30** (rows L1-01…L1-30)
- **COVERED-DOC: 9** (rows DOC-01…DOC-09)
- **PENDING-L3/L4: 8** (rows P-01…P-08)
- Ruled out of S82 surface: 7 groups, listed in section D, not
  counted in any tally.

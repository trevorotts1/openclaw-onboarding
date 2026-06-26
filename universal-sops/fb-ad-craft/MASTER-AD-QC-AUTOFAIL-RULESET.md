# MASTER AD QC AUTO-FAIL RULESET — Facebook & Instagram Ad Generator (Skill 48)

**Department:** Paid Advertisement — Facebook & Instagram Ad Generator (Skill 48 / `facebook-instagram-ad-run-producer` conductor + `direct-response-ad-copywriter`).
**Authority:** This ruleset is the binary, machine-checkable companion to `AD-PIPELINE-MANIFEST.json`. Every `in_ruleset:true` autofail in the manifest has exactly one row in Section 5 below. `48-facebook-ad-generator/scripts/ad_sync_check.py` reconciles this table against the manifest in BOTH directions and exits 4 on any drift.
**Mirrors:** the Movie Producer `MASTER-VIDEO-QC-AUTOFAIL-RULESET.md` Section-5 contract and the Presentations `MASTER-QC-AUTOFAIL-RULESET.md`.

---

## 0. WHY DESCRIPTION ALONE FAILED (read before wiring)

The ad doctrine — "write 70 overlays, pick 10, exactly 3 CTAs, 1500×1500, never invent a Meta interest, never charge twice, two human pauses" — is **prose**. Prose is bypassable: a stage can be skipped, a receipt fabricated, a balance unchecked, a Meta interest invented, an image double-charged, and nothing on disk fails.

**Doctrine: a rule not auto-failed at a gate does not exist.** Every binary trigger below is enforced by a Python symbol in `ad_director.py` / `ad_build_check.py` (the `py_symbol` column of the manifest), is checked BEFORE any 1–10 scoring (no averaging away), and is proven by a deliberately-failing negative test in `test_ad_preflight.py` (Guard A: `ad_gate_integrity_check.py`).

---

## 1. THE LOAD-BEARING AUTO-FAILS (the ship-blockers)

These are the spine of the pipeline:

1. **AF-FBAD-BRIEF-INCOMPLETE** (S0-INTAKE) — no complete intake brief, no job.
2. **AF-FBAD-COST-CEILING** (S0-INTAKE) — the up-front estimate must be approved AND ≤ the per-job ceiling BEFORE any money is spent. HARD STOP.
3. **AF-FBAD-DEP-SKIPPED** (Driver) — a stage may not start until EVERY stage in its `depends_on[]` is attested with its artifact present. The two human gates (PICK-10, PUBLISH) can NEVER be skipped.
4. **AF-FBAD-SELECTION-COUNT / AF-FBAD-SELECTION-SUBSET** (PICK-10, human gate) — the owner picks exactly 10 real, in-range, distinct overlays.
5. **AF-FBAD-IMAGE-TASKID / AF-FBAD-IMAGE-SIZE / AF-FBAD-IMAGE-MODEL** (S5) — every image carries a REAL Kie task id, is 1500×1500, and uses a gpt-image-* model (any version).
6. **AF-FBAD-TARGETING-REAL** (S6) — every interest resolves to a real Meta entity OR is marked flagged-unverified; inventing one fails.
7. **AF-FBAD-GHL-URL / AF-FBAD-PLAI-FIELDS / AF-FBAD-ADTEXT-DOC** (S7) — the package is real: hosted public links (HTTP-200), every PLAI field, 10 copy-paste Headline+Body pairs.
8. **AF-FBAD-APPROVE** (PUBLISH, human gate) — the PLAI handoff happens only after a named owner approval (who + when + confirmed).

---

## 2. MONEY + IDEMPOTENCY AUTO-FAILS (spend can never run away or double-charge)

The money model is: **estimate up front → per-job ceiling → a cheap LOCAL running tally that stops before crossing → a single balance preflight at start.** It is NOT a balance lookup per image.

- **AF-FBAD-COST-CEILING** (S0) — estimate ≤ ceiling before any spend.
- **AF-FBAD-KIE-BALANCE** (Phase-0) — a single live balance preflight at start; below the estimated floor or unverifiable = HARD ABORT (exit 4).
- **AF-FBAD-TALLY-CROSS** (S5) — the local running tally never crosses the ceiling; the next paid image stops if it would.
- **AF-FBAD-RECEIPT-NAMESPACE** (S0) — every paid receipt is namespaced by the unique run-id, with a "what already happened" log, so a retry never re-spends or double-uploads.

---

## 3. THE CHECK ORDER (how QC runs this ruleset)

1. **Phase-0 balance** — `AF-FBAD-KIE-BALANCE` HARD-ABORTS (exit 4) for a paid job before any dispatch.
2. **Per-phase dependency preconditions** — `AF-FBAD-DEP-SKIPPED` (exit 2): before a phase, every `depends_on[]` phase is attested (by its owning_role) with its produces_artifact on disk, or (for a non-human dependency) owner-skipped. Human gates are never skippable.
3. **Per-phase receipt validation** — the phase's `_chk_*` checker(s) validate the present receipt; a present-but-invalid receipt is exit 3.
4. **Independent QC** — a gate opens only with zero autofails AND an 8.5+ average (no category < 7) from a DIFFERENT worker than the maker (`AF-FBAD-*-QC` + `AF-FBAD-QC-INDEPENDENCE`). A triggered AF is never averaged away.

---

## 4. THE INDEPENDENT-QC GATES + REPORT CARDS (Gate A–E)

Five gates get a 1–10 grade from an **independent** reviewer (never the maker). A gate passes only when: average ≥ **8.5**, no category < **7**, zero autofails, and the grade is independent. Below the line fires the redo loop (Gate A/B/D: 2 redos; Gate C: 3 redos per image; Gate E: fix-in-place or back to the item's stage), escalating to the owner only after the redo budget is spent.

| Gate | What gets graded | Maker | Independent grader | Auto-fail |
|---|---|---|---|---|
| **A — The Words** | 70 overlays + 10 bodies + 10 headlines | Direct-Response Ad Copywriter | Ad Quality Reviewer | `AF-FBAD-COPY-QC` |
| **B — Image Prompts** | the 10 picture-instructions | AI Image Generator Specialist | Independent Prompt Reviewer | `AF-FBAD-PROMPT-QC` |
| **C — The Images** | the 10 finished ad pictures (baked-in text legibility lives here) | AI Image Generator Specialist | Independent VISION reviewer (can see the picture, did not make it) | `AF-FBAD-IMAGE-QC` |
| **D — The Targeting** | the 3-tier targeting brief | Audience Research Specialist | Independent Targeting Reviewer | `AF-FBAD-TARGETING-QC` |
| **E — The Final Package** | the whole bundle before approve | Facebook Ads Specialist | Devil's Advocate — Paid Advertisement | `AF-FBAD-PACKAGE-QC` |

Cross-cutting: **AF-FBAD-QC-INDEPENDENCE** fails any gate whose scorecard is self-graded (grader == maker, `independent` not true, or the block missing). For Gate C the reviewer must be able to actually SEE the picture — this is the real enforcement of in-image text legibility now that the separate text-reading (OCR) step is dropped; the human at the approve pause is the final backstop.

---

## 5. REQUIRED WIRING (what the integrator keeps in lockstep)

Any added/changed FB/IG-ad SOP, role, or gate MUST, in one change:
- (i) update `AD-PIPELINE-MANIFEST.json` (+ bump `manifest_version`);
- (ii) add/point the enforcing `py_symbol` in `ad_director.py` / `ad_build_check.py`;
- (iii) add the AF code row to the Section-5 table below;
- (iv) add a deliberately-failing negative test in `test_ad_preflight.py`.

`ad_sync_check.py` exits 4 if any of those four is skipped. `ad_gate_integrity_check.py` (Guard A) exits 1 if a declared+enforced gate has no triggering negative test.

---

## 6. THE MACHINE-CHECKABLE SUMMARY TABLE (one row per auto-fail, the wireable list)

| Code | Stage | Level | Trigger (one line) | Detection |
|---|---|---|---|---|
| AF-FBAD-BRIEF-INCOMPLETE | S0-INTAKE | JOB | intake brief absent or any required field missing | `_chk_brief_complete`: job-manifest brief_complete:true AND every REQUIRED_BRIEF_FIELDS field non-empty |
| AF-FBAD-COST-CEILING | S0-INTAKE | JOB | up-front estimate over the per-job ceiling before any spend | `_chk_cost_ceiling`: cost_estimate_approved:true AND estimated_cost_usd <= money_ceiling_usd |
| AF-FBAD-RECEIPT-NAMESPACE | S0-INTAKE | JOB | run-id ledger missing / run_id != job_id / no events log | `_chk_run_ledger`: ad_run_ledger.json run_id == job_id AND an events[] log present |
| AF-FBAD-OVERLAY-COUNT | S1-OVERLAYS | JOB | overlay count != the locked count | `_chk_overlay_count`: s1-receipt overlay_count == OVERLAY_COUNT_LOCKED |
| AF-FBAD-OVERLAY-WORDCOUNT | S1-OVERLAYS | JOB | an overlay line outside the word band | `_chk_overlay_wordcount`: every word_counts[i] in OVERLAY_WORD_MIN..OVERLAY_WORD_MAX |
| AF-FBAD-OVERLAY-TOPLINE | S1-OVERLAYS | JOB | the fixed locked top line is missing | `_chk_overlay_topline`: s1-receipt top_line_present:true |
| AF-FBAD-ON-MISSION | S1-OVERLAYS | JOB | copy sells a product instead of featuring the guest/show | `_chk_on_mission`: s1-receipt on_mission:true |
| AF-FBAD-AUDIENCE-WORDING | S1-OVERLAYS | JOB | the client's exact audience wording was paraphrased away | `_chk_audience_wording`: s1-receipt audience_wording_preserved:true |
| AF-FBAD-COPY-QC | S2-PRIMARY-TEXT | JOB | Gate A independent words scorecard below the line | `_chk_copy_qc`: copy-qc avg>=QC_MIN_AVERAGE, no category<QC_MIN_CATEGORY, pass:true |
| AF-FBAD-SELECTION-COUNT | PICK-10 | JOB | the saved selection is not exactly the locked count of distinct picks | `_chk_selection_count`: distinct picks == SELECTION_COUNT_LOCKED |
| AF-FBAD-SELECTION-SUBSET | PICK-10 | JOB | a pick is not a real in-range overlay index | `_chk_selection_subset`: every pick in 1..overlay_count |
| AF-FBAD-BODY-HOOK | S2-PRIMARY-TEXT | JOB | a body's hook exceeds the char cap | `_chk_body_hook`: every body hook_chars in 1..BODY_HOOK_MAX_CHARS |
| AF-FBAD-BODY-CTA | S2-PRIMARY-TEXT | JOB | a body has the wrong number of calls-to-action | `_chk_body_cta`: every body cta_count == BODY_CTA_COUNT |
| AF-FBAD-BODY-EMOJI | S2-PRIMARY-TEXT | JOB | a body's emoji count is out of band | `_chk_body_emoji`: every body emoji_count in BODY_EMOJI_MIN..BODY_EMOJI_MAX |
| AF-FBAD-HEADLINE-SHAPE | S3-HEADLINES | JOB | a headline uses a non-locked shape | `_chk_headline_shape`: every headline shape in HEADLINE_SHAPES_LOCKED |
| AF-FBAD-PROMPT-ORDER | S4-IMAGE-PROMPTS | JOB | a prompt's sections deviate from the fixed build order | `_chk_prompt_order`: every prompt sections == PROMPT_BUILD_ORDER |
| AF-FBAD-PROMPT-RICHNESS | S4-IMAGE-PROMPTS | JOB | a prompt outside the richness char band | `_chk_prompt_richness`: every prompt char_count in PROMPT_MIN_CHARS..PROMPT_MAX_CHARS |
| AF-FBAD-PROMPT-STYLEBLOCK | S4-IMAGE-PROMPTS | JOB | a prompt lacks the brand style-block or the exact baked-in words | `_chk_prompt_styleblock`: every prompt styleblock_ok:true AND baked_text_present:true |
| AF-FBAD-PROMPT-QC | S4-IMAGE-PROMPTS | JOB | Gate B independent prompt scorecard below the line | `_chk_prompt_qc`: prompt-qc avg>=QC_MIN_AVERAGE, no category<QC_MIN_CATEGORY, pass:true |
| AF-FBAD-IMAGE-TASKID | S5-IMAGE-GEN | JOB | an image carries no real (non-placeholder) Kie task id | `_chk_image_taskid` (paid only): every image kie_task_id non-null, not a FABRICATED_TASK_ID_TOKENS member |
| AF-FBAD-IMAGE-SIZE | S5-IMAGE-GEN | JOB | an image is not the locked 1:1 square size | `_chk_image_size`: every image width==height==IMAGE_EDGE_PX |
| AF-FBAD-IMAGE-MODEL | S5-IMAGE-GEN | JOB | an image model is not a gpt-image-* model | `_chk_image_model`: every image model startswith GPT_IMAGE_MODEL_PREFIX (any gpt-image version) |
| AF-FBAD-TALLY-CROSS | S5-IMAGE-GEN | JOB | the local running spend tally crossed the ceiling | `_chk_tally_ceiling`: ledger spent_usd <= ceiling AND no image would_cross:true |
| AF-FBAD-IMAGE-QC | S5-IMAGE-GEN | JOB | Gate C independent VISION scorecard below the line (baked-in text legibility) | `_chk_image_qc`: image-qc avg>=QC_MIN_AVERAGE, no category<QC_MIN_CATEGORY, pass:true |
| AF-FBAD-TARGETING-SHAPE | S6-TARGETING | JOB | the brief is not the PLAI 3-tier shape with a why per group | `_chk_targeting_shape`: each group has layer1/2/3 (non-empty) + an explanation |
| AF-FBAD-TARGETING-REAL | S6-TARGETING | JOB | an interest is invented (neither resolved nor flagged-unverified) | `_chk_targeting_real`: each interest resolved with a meta_id OR flagged_unverified:true |
| AF-FBAD-TARGETING-QC | S6-TARGETING | JOB | Gate D independent targeting scorecard below the line | `_chk_targeting_qc`: targeting-qc avg>=QC_MIN_AVERAGE, no category<QC_MIN_CATEGORY, pass:true |
| AF-FBAD-FANOUT | S7-DELIVER | JOB | selection/bodies/headlines/prompts/images counts not all equal | `_chk_fanout`: counts all equal AND == SELECTION_COUNT_LOCKED |
| AF-FBAD-GHL-URL | S7-DELIVER | JOB | an image not hosted in GoHighLevel with a real public link + HTTP-200 | `_chk_ghl_url`: each delivered image_url https, not a FABRICATED_URL_TOKENS member, http_status==200 |
| AF-FBAD-ADTEXT-DOC | S7-DELIVER | JOB | the ad-text doc lacks 10 Headline+Body block pairs matching the copy | `_chk_adtext_doc`: adtext_block_pairs == SELECTION_COUNT_LOCKED AND adtext_matches_copy:true |
| AF-FBAD-PLAI-FIELDS | S7-DELIVER | JOB | the PLAI brief is missing a required builder field | `_chk_plai_fields`: every REQUIRED_PLAI_FIELDS field present |
| AF-FBAD-BOARD | S7-DELIVER | JOB | the job is not on the Command Center board (no campaign_id) | `_chk_board`: s7-deliver-receipt campaign_id present |
| AF-FBAD-PACKAGE-QC | S7-DELIVER | JOB | Gate E independent package scorecard below the line | `_chk_package_qc`: package-qc avg>=QC_MIN_AVERAGE, no category<QC_MIN_CATEGORY, pass:true |
| AF-FBAD-QC-INDEPENDENCE | S7-DELIVER | JOB | a QC scorecard is self-graded (grader == maker / not independent) | `_chk_qc_independence`: every present scorecard independent:true AND grader != maker |
| AF-FBAD-APPROVE | PUBLISH | JOB | the PLAI handoff reached without a named owner approval | `_chk_approve`: approval-receipt approved_by + approval_received_at + owner_confirmed:true |
| AF-FBAD-KIE-BALANCE | Phase-0 | JOB | paid job balance below floor or unverifiable | `kie_balance_preflight`: live Kie balance >= estimated_cost x FBAD_CREDIT_PER_USD x FBAD_KIE_BALANCE_FLOOR_MULTIPLIER; unverifiable = HARD ABORT (exit 4) |
| AF-FBAD-DEP-SKIPPED | Driver | JOB | a phase dispatched before a depends_on phase was attested (or wrong owning_role); a human gate can never be skipped | `ad_director.check_dependency_preconditions`: every depends_on phase attested by its owning_role with produces_artifact present, or (non-human) a logged owner-authorized skip |

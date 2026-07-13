# Skill 6 Blended-Persona + Kanban v2 — BUILD LEDGER (U1–U105)

**Source:** `skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md` §E.2.
**Run init:** 2026-07-13T21:21:25Z. **State:** SETUP ONLY — no unit built; run gated on D1–D23 ratification.

**Status vocabulary:**
- `pending` — not started (initial state of every unit).
- `in_progress` — a builder agent is actively working the unit (builder ≠ judge).
- `done` — builder claims complete; NOT yet independently judged. A producer/builder claim alone is a hypothesis, never proof.
- `failed` — the unit tripped a fail-closed rule or scored below the 8.5 gate; back to the auto-fix loop.
- `verified` — a separate judge (ideally a different model) scored ≥8.5 across the 10 categories with quoted proof, survived the break-it pass, and the work merged. Only `verified` counts as truly complete.

> Note on **U91**: the spec document itself already executed this banned-term scrub in place (`done-in-document`); per §E.2 the execution run re-verifies it as the checklist's FIRST row, so it is carried here as `pending` (re-verify) at init.
> Note on the **U17 ⇄ U19** merge-pair: these two units merge together or not at all — neither reaches `verified` alone.

| id | description | label | status | evidence | timestamp |
|---|---|---|---|---|---|
| U1 | `persona_for_job` carries the blend (`--blend` mode through `_run_selector`; default-off; bundle superset to every consumer) | | pending | | 2026-07-13T21:21:25Z |
| U2 | Blend Directive v2 — structured voice attributes per slot from `voice_style{}` + voice-contract echo; guardrail byte-identical | | pending | | 2026-07-13T21:21:25Z |
| U3 | Schema-1.4 enrichment: `emotional_register`/`audience_resonance`/`conversion_style` on all 99+ personas; D6-pipeline stamping | | pending | | 2026-07-13T21:21:25Z |
| U4 | `conversion_goal` first-class input: kwarg + argv/env + source ladder + directive slot 5 + per-department confirm policy | | pending | | 2026-07-13T21:21:25Z |
| U5 | Per-page scoped blends: `scope_hint` + NEW `task_persona_bundle_scope` table (090 never altered) + per-scope chips | | pending | | 2026-07-13T21:21:25Z |
| U6 | min-2/max-4 persona-count invariant: `validate_blend_invariant` + receipts + hygiene companion alert | | pending | | 2026-07-13T21:21:25Z |
| U7 | Skill 6 convergence (THE unification unit): dispatcher consumes the bundle, per-page blends, crosswalked template hint, declared-vs-used | | pending | | 2026-07-13T21:21:25Z |
| U8 | Book-to-persona embeddings wiring: post-synthesis index write + publish index-verify + scheduled disk-vs-index drift check | | pending | | 2026-07-13T21:21:25Z |
| U9 | Exemplar convention + write-time injection (CALIBRATION-ONLY clause, receipts; Skill 6 lead/buyer/event + Skill 35 packs) | | pending | | 2026-07-13T21:21:25Z |
| U10 | Anti-copy guard: deterministic similarity ceiling vs injected exemplars, key-free, hard-miss | | pending | | 2026-07-13T21:21:25Z |
| U11 | Winner-harvest flywheel: ≥9.0 outputs → operator-approved card → CLIENT-LOCAL exemplar library | | pending | | 2026-07-13T21:21:25Z |
| U12 | Blend observability: match-score distribution advisory in deep-health + `persona_grounding_degraded` event/chip | | pending | | 2026-07-13T21:21:25Z |
| U13 | Regression corpus 20 → 40+ (≥5 emotional-register + ≥5 conversion-style cases; gate stays ≥90%) | | pending | | 2026-07-13T21:21:25Z |
| U14 | Blueprint-generation reconciliation: `_section-map.json`, Section-4 load-contract hazard, Skill 23 CHANGELOG backfill | | pending | | 2026-07-13T21:21:25Z |
| U15 | Bundle-acquisition ladder in `v2_dispatcher` (threaded → CC fetch → local `--blend` → absent; receipt always) | | pending | | 2026-07-13T21:21:25Z |
| U16 | Per-page `build_blend_directive`; template persona demoted to crosswalk-resolved topic hint; `copy_persona` back-compat | | pending | | 2026-07-13T21:21:25Z |
| U17 | Copy stage consumes the bundle (SOP + prompt seam; log format back-compatible) — merges ONLY with U19 | | pending | | 2026-07-13T21:21:25Z |
| U18 | Execute D5: `copy_craft_pool` in the crosswalk + P2/SOP gate-text convergence + guard | | pending | | 2026-07-13T21:21:25Z |
| U19 | FAB-QC D4 v2 — bundle-aware voice grounding; legacy path byte-identical (pairs U17; the v1 P0's missing half) | | pending | | 2026-07-13T21:21:25Z |
| U20 | Producer reports USED personas to the card; declared-vs-used comparator + `persona_mismatch` chip/event | | pending | | 2026-07-13T21:21:25Z |
| U21 | Ingest parity: optional persona fields on `ingest_task`; CC pins producer personas instead of re-matching | | pending | | 2026-07-13T21:21:25Z |
| U22 | Guards + fixtures + ONE end-to-end operator-box proof run for the whole unification block | | pending | | 2026-07-13T21:21:25Z |
| U23 | Decision-engine hardening: `derive_page_signals`, site-level routing rule, routing corpus + monthly live routing-drift proof | | pending | | 2026-07-13T21:21:25Z |
| U24 | Execute D6: prove + schedule the shipped GitHub archival rail (reconcile exit-0 + byte-match; FAB-QC receipt check) | | pending | | 2026-07-13T21:21:25Z |
| U25 | Page-QC v2 semantic scorer: `shared-utils/page_qc.py`, six dimensions, 8.5, client's own judge, SKIP-not-fabricate | | pending | | 2026-07-13T21:21:25Z |
| U26 | QC-contract fix: `runQCOnReview` reads the posted producer score; disagreement >1.0 HELD + `qc_disagreement`; both-gates rule | | pending | | 2026-07-13T21:21:25Z |
| U27 | Skill-6 board reconcile: `cc_board.py reconcile` + `skill6_board_projection` advisory + drift banner | | pending | | 2026-07-13T21:21:25Z |
| U28 | Headless D6 coverage audit (every launch site) + stale-browser reaper proof on Mac AND VPS + schedule-presence check | | pending | | 2026-07-13T21:21:25Z |
| U29 | ENV-MATRIX live proof: the ASSUMED VPS mount row + first-hour ground truth on one Mac + one VPS + stale-env preflight | | pending | | 2026-07-13T21:21:25Z |
| U30 | Iframe: page-code drag flag-wired, `frame_click`, `smoke_first()` generalized, scheduled selector-drift probe + rename the four legacy-named Skill-6 files | | pending | | 2026-07-13T21:21:25Z |
| U31 | Page inventory + staged lifecycle (flag → operator card → fail-closed execute) + evidence-root retention | | pending | | 2026-07-13T21:21:25Z |
| U32 | Maria-pattern proof harness: seed all four stuck states, run the real jobs, assert every net fires | | pending | | 2026-07-13T21:21:25Z |
| U33 | Triad-stall alert (day-0→21 dead zone) + advancer gate-consistency pin (advancer must honor the Triad, loudly) | | pending | | 2026-07-13T21:21:25Z |
| U34 | Fake-agent root cause: phantom-assignee silent skip becomes loud, capped, self-healing (`task-dispatcher.ts:431–436`) | | pending | | 2026-07-13T21:21:25Z |
| U35 | Phantom-assignment healer: idempotent script + sweep-integrated self-heal | | pending | | 2026-07-13T21:21:25Z |
| U36 | Fleet box-count audit (read-only): class-a phantoms, class-b holds, DDL protection, version — per-box ledger | | pending | | 2026-07-13T21:21:25Z |
| U37 | "Routed but not runnable" visible ON the card + modal (class-b hold chip) | | pending | | 2026-07-13T21:21:25Z |
| U38 | S3 closure: operator-box proof of the three review-lane nets + human-promote control for parked review cards | | pending | | 2026-07-13T21:21:25Z |
| U39 | S4 closure: producer→review→done lifecycle contract proof (both refusals + QC-promote path) | | pending | | 2026-07-13T21:21:25Z |
| U40 | Advancer watchdog (`sweep-liveness`, watch the watchers) + fix the phantom `'working'` probe metric | | pending | | 2026-07-13T21:21:25Z |
| U41 | Create-task proven end-to-end ON-BOX: shipped Playwright suite + workspace-scoped create + SSE assertion | | pending | | 2026-07-13T21:21:25Z |
| U42 | Task-detail FULLY populated: multi-persona plan in the modal, honest engine-card persona surface, field matrix | | pending | | 2026-07-13T21:21:25Z |
| U43 | Home-dashboard missing-cards: induced-failure proof on the operator box + fleet version/build audit field | | pending | | 2026-07-13T21:21:25Z |
| U44 | Catch-all conformance: `general-task` seeded fleet-wide, display "General Stuff" (D8), INGEST-06 proof, stale producer-doc fix | | pending | | 2026-07-13T21:21:25Z |
| U45 | Board-truth regression pack: todo bucket mapping, label single-source, 10-status manifest lockstep, dead-`'archived'` cleanup | | pending | | 2026-07-13T21:21:25Z |
| U46 | Criticality-tiered health aggregation (critical = database + gateway; both call sites; `tier` exposed) | | pending | | 2026-07-13T21:21:25Z |
| U47 | ONE `<HealthIndicator />` (operator clickable / client dot+word), mobile-visible; retire the five incidental store writers | | pending | | 2026-07-13T21:21:25Z |
| U48 | Key detection: Docker `/data/.openclaw` env paths + `envCandidates` completion (zai, elevenlabs, fish-audio + sweep) | | pending | | 2026-07-13T21:21:25Z |
| U49 | `verifyKey()` on the five media connectors + every Prove outcome surfaced (no silent swallow; no dead buttons) | | pending | | 2026-07-13T21:21:25Z |
| U50 | Model-catalog honesty (Fish Audio fallback never `active`; swallow-audit) + sticky filter bar + deprecated toggle (D14) | | pending | | 2026-07-13T21:21:25Z |
| U51 | Port-4000 AGREEMENT proof fleet-wide: public-URL probe required, `cc_port`/`override_ack_set` ledger rows | | pending | | 2026-07-13T21:21:25Z |
| U52 | Cloudflare Access + Google-login posture proof wired into standing validation + operator-box human login proof | | pending | | 2026-07-13T21:21:25Z |
| U53 | Self-updater: fix `check-updates.sh` canonical paths + AGENTS.md cleanup; crown ONE executor (D12); prove the loop | | pending | | 2026-07-13T21:21:25Z |
| U54 | Whole-app responsive audit PROGRAM: mechanical route inventory (38 @ pin) × 3 breakpoints, fix by defect class, repeatable gate | | pending | | 2026-07-13T21:21:25Z |
| U55 | CEO hero: one data source, visible windows, ONE unified attention definition (click-through), strip filter fix, contract test | | pending | | 2026-07-13T21:21:25Z |
| U56 | Department detail: fix the two hard-wired-empty pairs, purge demo seeds + cleanup migration, four contract tests | | pending | | 2026-07-13T21:21:25Z |
| U57 | Department metric unification + DELETE the dead mislabeled `CEODashboard` branch + blockers/velocity panel | | pending | | 2026-07-13T21:21:25Z |
| U58 | Individual-agent performance boards: per-agent endpoint (QC join), index + detail pages, trend series, trio exclusion | | pending | | 2026-07-13T21:21:25Z |
| U59 | Devil's Advocate end-to-end: prove the generator FIRST (gating), demo purge, write path + bridge, PRD-conform surfaces (D15) | | pending | | 2026-07-13T21:21:25Z |
| U60 | My AI CEO Phase A: decompose + re-skin, Operations Rail (trust-join fix), delegate endpoint, context meter, mobile system | | pending | | 2026-07-13T21:21:25Z |
| U61 | Gateway spikes S1–S3 (model/effort override; agent addressing; usage frames) — operator-box, read-only, evidence files | | pending | | 2026-07-13T21:21:25Z |
| U62 | My AI CEO Phase B: model/thinking/agent passthrough + exact usage metering — HARD-gated per U61 verdicts | | pending | | 2026-07-13T21:21:25Z |
| U63 | P0 live: fix the podcast publish path that failed on `image_url = null` + fail-closed entry guard + retry the episode | | pending | | 2026-07-13T21:21:25Z |
| U64 | P0 live: deploy the complete 51-node Anthology Drive Broker over the live 20-node `501` stub | | pending | | 2026-07-13T21:21:25Z |
| U65 | SECURITY: vault the hardcoded Podbean OAuth secrets; deploy the 8-node Podbean broker | | pending | | 2026-07-13T21:21:25Z |
| U66 | Repair the n8n management-API key wiring (kills the "manual import" bottleneck); no-op write round-trip proof | | pending | | 2026-07-13T21:21:25Z |
| U67 | Podcast golden snapshot v2 + `PODCAST_SNAPSHOT_ID` confirmation (no-409 dry run) | | pending | | 2026-07-13T21:21:25Z |
| U68 | Facebook-workflow activation becomes a runbook checklist item with a QC-gate assertion | | pending | | 2026-07-13T21:21:25Z |
| U69 | Publish the 3 draft Anthology release-notification workflows; re-cut the anthology snapshot | | pending | | 2026-07-13T21:21:25Z |
| U70 | Provision the declared-but-unprovisioned `chapter_rewrite1`/`chapter_rewrite2` fields via the engine's own path | | pending | | 2026-07-13T21:21:25Z |
| U71 | Clear the WAF/edge 403 on `verify-imported`; run the never-yet-run snapshot chain end-to-end once | | pending | | 2026-07-13T21:21:25Z |
| U72 | Remove the leftover live gate-test workflow (TEMP — its own name demands deletion at cutover) | | pending | | 2026-07-13T21:21:25Z |
| U73 | Resolve the `Anthology Writer - Ben` monolith: exactly ONE live path, docs name it | | pending | | 2026-07-13T21:21:25Z |
| U74 | Canonicalize the podcast pipeline per D19 (kill the double-publish risk) | | pending | | 2026-07-13T21:21:25Z |
| U75 | Archive the 8 inactive `* CC`-suffixed duplicate workflows after a reference scan | | pending | | 2026-07-13T21:21:25Z |
| U76 | Instance-wide n8n/GHL audit read IN FULL + 100% finding disposition + adjacent-engine GHL surfaces | | pending | | 2026-07-13T21:21:25Z |
| U77 | Podcast dashboard transplant into the Command Center per its own WIRING.md (engine-gated nav; all gates re-run) | | pending | | 2026-07-13T21:21:25Z |
| U78 | Anthology live triage T1–T3 on the operator's own box (version / drift signal / seeded+engine state) | | pending | | 2026-07-13T21:21:25Z |
| U79 | The REAL A7 repair: root-cause the silent mirror drop, then a converging self-healing reconcile (banner = last resort) | | pending | | 2026-07-13T21:21:25Z |
| U80 | Anthology tracking-document truth-up (1/55 checklist vs 56 shipped Python files — the audit trail must certify again) | | pending | | 2026-07-13T21:21:25Z |
| U81 | Prove the Social Media Planner UNBROKEN against the graphics handoff end-to-end — or capture the exact break | | pending | | 2026-07-13T21:21:25Z |
| U82 | Resolve the band↔routing contradiction in ONE place (`prompt-bands.json` vs the Ideogram routing rule) + CI locks | | pending | | 2026-07-13T21:21:25Z |
| U83 | Dedicated Graphics prompt-author + prompt-QC roles (per D17), wired into the manifests and dispatch SOP | | pending | | 2026-07-13T21:21:25Z |
| U84 | On-box CONTENT proof for P3-05 (manifest `src_git_sha` + named files — never a version stamp alone) | | pending | | 2026-07-13T21:21:25Z |
| U85 | One-question-at-a-time UNFAKEABLE at the record layer: driver turn-ledger stamp + `AF-SP-INTAKE-UNPACED` (per D18) | | pending | | 2026-07-13T21:21:25Z |
| U86 | Reproduce + fix the on-box presentation Python breakage by root-cause class (stale content / deps preflight / `--workspace` flag) | | pending | | 2026-07-13T21:21:25Z |
| U87 | 4-phase SACRED process-fidelity proof run (golden fixture, every prover receipt, phase-order check with teeth) | | pending | | 2026-07-13T21:21:25Z |
| U88 | The content→conversation loop proven end-to-end ONCE on the operator's box (35 → 44 → GHL → 38, + Gap C matcher leg) | | pending | | 2026-07-13T21:21:25Z |
| U89 | ONE canonical relationship lattice document (Skills 6/44/35/38/3) + per-skill pointer + QC citation tripwires | | pending | | 2026-07-13T21:21:25Z |
| U90 | Strengthen Skill 3 as a first-class backstop: on-box drift gate, CLI version pin, consumer conformance battery | | pending | | 2026-07-13T21:21:25Z |
| U91 | Banned-term scrub of the spec text (12 v1 hit-lines superseded) — executed in the document; run verifies first | done-in-document (re-verify) | pending | | 2026-07-13T21:21:25Z |
| U92 | Docs-language CI guard (fails NEW occurrences; allowlists history, vendor literals, legacy filenames until renamed) | | pending | | 2026-07-13T21:21:25Z |
| U93 | Rename the remaining legacy-named files + live doctrine text + the two CC comments, with one-release shims (per D20; four Skill-6 files owned by U30) | | pending | | 2026-07-13T21:21:25Z |
| U94 | Requester-stamping completeness at every human creation door + trust-coverage health metric ≥95% (absorbs v1 U20) | | pending | | 2026-07-13T21:21:25Z |
| U95 | Orchestrator-only report-back invariant guard (static call-site pin + behavioral fixture + mutation proof) | | pending | | 2026-07-13T21:21:25Z |
| U96 | ROUTED hand-off row: push-client-embeddings → the fleet-roll run (mechanism + 2026-07-14 embedding-model EOL context) | | pending | | 2026-07-13T21:21:25Z |
| U97 | ROUTED hand-off row: AI-Workforce-Interview → CC-provisioning → the Skill 23/32 lane (+ false-block regression guard) | | pending | | 2026-07-13T21:21:25Z |
| U98 | Guarded blend-adoption ripple: Skill 35 per-day blend via scoped bundles; product-voice engines advisory-only; anthology LAST | | pending | | 2026-07-13T21:21:25Z |
| U99 | Raw-writer convergence to `transition()` + CI guard against new raw `UPDATE tasks SET status` writers | | pending | | 2026-07-13T21:21:25Z |
| U100 | Producer-reconcile generalized: Skill 35 cycle-manifest variant + the `mc_board` engine family, each with a health projection | | pending | | 2026-07-13T21:21:25Z |
| U101 | Per-department SLA table (`config/board-slas.json`) feeding board-hygiene + stale-sweep, rendered on settings | | pending | | 2026-07-13T21:21:25Z |
| U102 | Operator daily column-age digest (batched) + `notification-failures.jsonl` size as a health field | | pending | | 2026-07-13T21:21:25Z |
| U103 | Due-date smart default in `createTaskCore` — priority-based, non-binding, editable/clearable; no client-facing prompt | | pending | | 2026-07-13T21:21:25Z |
| U104 | Engine-mirrored card honesty: GatePanel empty-state copy fix, "Start Planning" gated off for anthology cards, card-type empty states | | pending | | 2026-07-13T21:21:25Z |
| U105 | Task-modal in-app help: typed copy map + reusable `<FieldHelp />` popover + "i" icons + accessibility/mobile behavior | | pending | | 2026-07-13T21:21:25Z |

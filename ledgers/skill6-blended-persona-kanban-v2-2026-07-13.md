# Skill 6 Blended-Persona Kanban v2 — MASTER VERIFICATION LEDGER (117-unit, PENDING)

> Source of truth: MASTER SPEC v2 Section E.2. One row per unit, U1-U117. Fresh 117-unit pending ledger (supersedes the stale 105-unit version).
> Status legend: `pending` -> (in-progress) -> `merged` -> `verified`. No unit is `done` until BOTH merged AND judge-verified at the standing 8.5 gate.
> The `[<Model> x<count>]` label column is the per-unit model/agent assignment, filled at dispatch. Blank = not yet assigned.

| id | description | [<Model> x<count>] label | status | evidence | timestamp |
|---|---|---|---|---|---|
| U1 | [A/A-U1] (ONB, P0) `persona_for_job` carries the blend (`--blend` mode through `_run_selector`; default-off; bundle superset to every consumer) | [Sonnet 5 x1] build U1 | verified | QC 9.35 (pass, gate 8.5). Merged `skill6-v2/U1` (6a31a7fe) into `main` via merge commit `292f4ee4` (clean, zero conflict markers per `git merge-tree` pre-check). Ripple commit `9f406872` (CHANGELOG.md v20.0.17 entry + all 11 repo version markers rolled v20.0.16→v20.0.17 via `scripts/bump-version.sh`, `--check` green). Pushed to `origin/main`; remote HEAD re-read via `git fetch origin main` and confirmed = `9f4068729102d17e6278721e19e1e5babb3a1f47`. Annotated tag `v20.0.17` (tag object `7ba7b9dc9ea7bae2c37e7b9341ddbe72a1c39fd2`, `git cat-file -t` = `tag`, confirming annotated not lightweight) pushed to origin. Test proof: `shared-utils/test-persona-for-job.sh` 24/24 PASS on merged `main` (11 single-persona self-test cases + 7 new blend-mode cases + 6 multi-slot cases), `python3 -m py_compile` clean. | 2026-07-13T22:17:04-04:00 |
| U2 | [A/A-U2] (ONB, P0) Blend Directive v2 — structured voice attributes per slot from `voice_style{}` + voice-contract echo; guardrail byte-identical | [Sonnet 5 x1] build U2 | verified | QC 8.9 (pass, gate 8.5). Merged `skill6-v2/U2` (1cb2c874) into `main` via merge commit `86420ff7` (clean, zero conflict markers — `git merge --no-commit --no-ff` staged with no conflicts, merge-base `a8a88b26` confirmed ancestor of `main` pre-merge). Ripple commit `e8cc7fce` (CHANGELOG.md v20.0.18 entry + all 11 repo version markers rolled v20.0.17→v20.0.18 via `scripts/bump-version.sh`, `--check` green before and after). Pushed to `origin/main`; remote HEAD re-read via `git fetch origin main` AND independently via `gh api repos/trevorotts1/openclaw-onboarding/commits/main` and confirmed = `e8cc7fce7542dc667a72685c9ce57d85748e7e2f`. Annotated tag `v20.0.18` (tag object `367a6e2a67944dd795ce75a600543ba5a9530e1`, `gh api .../git/tags/<sha>` = `type: tag`, confirming annotated not lightweight) pushed to origin and re-verified via `gh api .../git/refs/tags/v20.0.18`. Test proof (full `persona-blend-match-quality-guard.yml` CI sequence, all 8 steps, run locally on the merged tree pre-push): `py_compile` clean; W7 46-test contract suite 46/46 PASS; P4-01 20-case regression corpus 20/20=100%>=90% gate; P4-02 four-slot synergy suite 10/10 PASS; A-U2's own `test-a-u2-blend-directive-v2.py` 16/16 PASS (accept a: >=4 voice-attribute lines/populated slot; accept b: byte-identical v1 degrade on the 1.2 fixture incl. collapsed branch; accept c: guardrail trailing + text untouched; degrade-gracefully house-voice/topic-only/non-content); match-score-distribution logging 10/10 PASS; book-to-persona e2e round trip 5/5 PASS; D6 duality-tags pipeline shell suite 42/42 PASS. | 2026-07-13T22:22:43-04:00 |
| U3 | [A/A-U3] (ONB, P1) Schema-1.4 enrichment: `emotional_register`/`audience_resonance`/`conversion_style` on all 99+ personas; D6-pipeline stamping |  | pending |  |  |
| U4 | [A/A-U4] (both, P1) `conversion_goal` first-class input: kwarg + argv/env + source ladder + directive slot 5 + per-department confirm policy |  | pending |  |  |
| U5 | [A/A-U5] (both, P1) Per-page scoped blends: `scope_hint` + NEW `task_persona_bundle_scope` table (090 never altered) + per-scope chips |  | pending |  |  |
| U6 | [A/A-U6] (both, P1) min-2/max-4 persona-count invariant: `validate_blend_invariant` + receipts + hygiene companion alert |  | pending |  |  |
| U7 | [A/A-U7] (both, P1) **Skill 6 convergence (THE unification unit)**: dispatcher consumes the bundle, per-page blends, crosswalked template hint, declared-vs-used |  | pending |  |  |
| U8 | [A/A-U8] (ONB, P1) Book-to-persona embeddings wiring: post-synthesis index write + publish index-verify + scheduled disk-vs-index drift check |  | pending |  |  |
| U9 | [A/A-U9] (ONB, P2) Exemplar convention + write-time injection (CALIBRATION-ONLY clause, receipts; Skill 6 lead/buyer/event + Skill 35 packs) |  | pending |  |  |
| U10 | [A/A-U10] (ONB, P2) Anti-copy guard: deterministic similarity ceiling vs injected exemplars, key-free, hard-miss |  | pending |  |  |
| U11 | [A/A-U11] (both, P3) Winner-harvest flywheel: ≥9.0 outputs → operator-approved card → CLIENT-LOCAL exemplar library |  | pending |  |  |
| U12 | [A/A-U12] (CC (+ONB probe), P2) Blend observability: match-score distribution advisory in deep-health + `persona_grounding_degraded` event/chip |  | pending |  |  |
| U13 | [A/A-U13] (ONB, P2) Regression corpus 20 → 40+ (≥5 emotional-register + ≥5 conversion-style cases; gate stays ≥90%) |  | pending |  |  |
| U14 | [A/A-U14] (ONB, P2) Blueprint-generation reconciliation: `_section-map.json`, Section-4 load-contract hazard, Skill 23 CHANGELOG backfill |  | pending |  |  |
| U15 | [B/B-U1] (ONB (+CC endpoint), P0) Bundle-acquisition ladder in `v2_dispatcher` (threaded → CC fetch → local `--blend` → absent; receipt always) |  | pending |  |  |
| U16 | [B/B-U2] (ONB, P0) Per-page `build_blend_directive`; template persona demoted to crosswalk-resolved topic hint; `copy_persona` back-compat |  | pending |  |  |
| U17 | [B/B-U3] (ONB, P0) Copy stage consumes the bundle (SOP + prompt seam; log format back-compatible) — **merges ONLY with U19** |  | pending |  |  |
| U18 | [B/B-U4] (ONB, P1) Execute D5: `copy_craft_pool` in the crosswalk + P2/SOP gate-text convergence + guard |  | pending |  |  |
| U19 | [B/B-U5] (ONB, P0) **FAB-QC D4 v2** — bundle-aware voice grounding; legacy path byte-identical (pairs U17; the v1 P0's missing half) |  | pending |  |  |
| U20 | [B/B-U6] (both, P1) Producer reports USED personas to the card; declared-vs-used comparator + `persona_mismatch` chip/event |  | pending |  |  |
| U21 | [B/B-U7] (both, P1) Ingest parity: optional persona fields on `ingest_task`; CC pins producer personas instead of re-matching |  | pending |  |  |
| U22 | [B/B-U8] (both, P1) Guards + fixtures + ONE end-to-end operator-box proof run for the whole unification block |  | pending |  |  |
| U23 | [B/B-U9] (ONB, P2) Decision-engine hardening: `derive_page_signals`, site-level routing rule, routing corpus + monthly live routing-drift proof |  | pending |  |  |
| U24 | [B/B-U10] (ONB, P1) Execute D6: prove + schedule the shipped GitHub archival rail (reconcile exit-0 + byte-match; FAB-QC receipt check) |  | pending |  |  |
| U25 | [B/B-U11] (ONB, P0) **Page-QC v2** semantic scorer: `shared-utils/page_qc.py`, six dimensions, 8.5, client's own judge, SKIP-not-fabricate |  | pending |  |  |
| U26 | [B/B-U12] (CC, P0) **QC-contract fix**: `runQCOnReview` reads the posted producer score; disagreement >1.0 HELD + `qc_disagreement`; both-gates rule |  | pending |  |  |
| U27 | [B/B-U13] (both, P1) Skill-6 board reconcile: `cc_board.py reconcile` + `skill6_board_projection` advisory + drift banner |  | pending |  |  |
| U28 | [B/B-U14] (ONB, P2) Headless D6 coverage audit (every launch site) + stale-browser reaper proof on Mac AND VPS + schedule-presence check |  | pending |  |  |
| U29 | [B/B-U15] (ONB + live, P2) ENV-MATRIX live proof: the ASSUMED VPS mount row + first-hour ground truth on one Mac + one VPS + stale-env preflight |  | pending |  |  |
| U30 | [B/B-U16] (ONB, P2) Iframe: page-code drag flag-wired, `frame_click`, `smoke_first()` generalized, scheduled selector-drift probe + **rename the four legacy-named Skill-6 files** |  | pending |  |  |
| U31 | [B/B-U17] (ONB, P2) Page inventory + staged lifecycle (flag → operator card → fail-closed execute) + evidence-root retention |  | pending |  |  |
| U32 | [C/C-01] (CC, P1) Maria-pattern proof harness: seed all four stuck states, run the real jobs, assert every net fires |  | pending |  |  |
| U33 | [C/C-02] (CC, P1) Triad-stall alert (day-0→21 dead zone) + advancer gate-consistency pin (advancer must honor the Triad, loudly) |  | pending |  |  |
| U34 | [C/C-03] (CC, P1) **Fake-agent root cause**: phantom-assignee silent skip becomes loud, capped, self-healing (`task-dispatcher.ts:431–436`) |  | pending |  |  |
| U35 | [C/C-04] (CC, P1) Phantom-assignment healer: idempotent script + sweep-integrated self-heal |  | pending |  |  |
| U36 | [C/C-05] (live (read-only), P1) Fleet box-count audit (read-only): class-a phantoms, class-b holds, DDL protection, version — per-box ledger |  | pending |  |  |
| U37 | [C/C-06] (CC, P1) "Routed but not runnable" visible ON the card + modal (class-b hold chip) |  | pending |  |  |
| U38 | [C/C-07] (CC, P1) S3 closure: operator-box proof of the three review-lane nets + human-promote control for parked review cards |  | pending |  |  |
| U39 | [C/C-08] (both, P1) S4 closure: producer→review→done lifecycle contract proof (both refusals + QC-promote path) |  | pending |  |  |
| U40 | [C/C-09] (CC, P1) Advancer watchdog (`sweep-liveness`, watch the watchers) + fix the phantom `'working'` probe metric |  | pending |  |  |
| U41 | [C/C-10] (CC + live, P1) Create-task proven end-to-end ON-BOX: shipped Playwright suite + workspace-scoped create + SSE assertion |  | pending |  |  |
| U42 | [C/C-11] (CC, P1) Task-detail FULLY populated: multi-persona plan in the modal, honest engine-card persona surface, field matrix |  | pending |  |  |
| U43 | [C/C-12] (CC + live, P1) Home-dashboard missing-cards: induced-failure proof on the operator box + fleet version/build audit field |  | pending |  |  |
| U44 | [C/C-13] (both, P1) Catch-all conformance: `general-task` seeded fleet-wide, display "General Stuff" (D8), INGEST-06 proof, stale producer-doc fix |  | pending |  |  |
| U45 | [C/C-14] (CC, P2) Board-truth regression pack: todo bucket mapping, label single-source, 10-status manifest lockstep, dead-`'archived'` cleanup |  | pending |  |  |
| U46 | [HL/U46] (CC, P1) Criticality-tiered health aggregation (critical = database + gateway; both call sites; `tier` exposed) |  | pending |  |  |
| U47 | [HL/U47] (CC, P1) ONE `<HealthIndicator />` (operator clickable / client dot+word), mobile-visible; retire the five incidental store writers |  | pending |  |  |
| U48 | [HL/U60] (CC, P1) Key detection: Docker `/data/.openclaw` env paths + `envCandidates` completion (zai, elevenlabs, fish-audio + sweep) |  | pending |  |  |
| U49 | [HL/U61] (CC, P1) `verifyKey()` on the five media connectors + every Prove outcome surfaced (no silent swallow; no dead buttons) |  | pending |  |  |
| U50 | [HL/U62] (CC, P1) Model-catalog honesty (Fish Audio fallback never `active`; swallow-audit) + sticky filter bar + deprecated toggle (D14) |  | pending |  |  |
| U51 | [HL/U66] (live (read-only), P1) Port-4000 AGREEMENT proof fleet-wide: public-URL probe required, `cc_port`/`override_ack_set` ledger rows |  | pending |  |  |
| U52 | [HL/U67] (live (read-only), P1) Cloudflare Access + Google-login posture proof wired into standing validation + operator-box human login proof |  | pending |  |  |
| U53 | [HL/U68] (both, P1) Self-updater: fix `check-updates.sh` canonical paths + AGENTS.md cleanup; crown ONE executor (D12); prove the loop |  | pending |  |  |
| U54 | [HL/U69] (CC, P1) Whole-app responsive audit PROGRAM: mechanical route inventory (38 @ pin) × 3 breakpoints, fix by defect class, repeatable gate |  | pending |  |  |
| U55 | [JM/U51] (CC, P1) CEO hero: one data source, visible windows, ONE unified attention definition (click-through), strip filter fix, contract test |  | pending |  |  |
| U56 | [JM/U52] (CC, P1) Department detail: fix the two hard-wired-empty pairs, purge demo seeds + cleanup migration, four contract tests |  | pending |  |  |
| U57 | [JM/U53] (CC, P1) Department metric unification + DELETE the dead mislabeled `CEODashboard` branch + blockers/velocity panel |  | pending |  |  |
| U58 | [JM/U54] (CC, P1) Individual-agent performance boards: per-agent endpoint (QC join), index + detail pages, trend series, trio exclusion |  | pending |  |  |
| U59 | [JM/U55] (both, P1) Devil's Advocate end-to-end: prove the generator FIRST (gating), demo purge, write path + bridge, PRD-conform surfaces (D15) |  | pending |  |  |
| U60 | [JM/U63] (CC, P1) My AI CEO Phase A: decompose + re-skin, Operations Rail (trust-join fix), delegate endpoint, context meter, mobile system |  | pending |  |  |
| U61 | [JM/U64] (live (read-only), P1) Gateway spikes S1–S3 (model/effort override; agent addressing; usage frames) — operator-box, read-only, evidence files |  | pending |  |  |
| U62 | [JM/U65] (CC, P2) My AI CEO Phase B: model/thinking/agent passthrough + exact usage metering — HARD-gated per U61 verdicts |  | pending |  |  |
| U63 | [GK-01] (ONB + n8n, P0) **P0 live**: fix the podcast publish path that failed on `image_url = null` + fail-closed entry guard + retry the episode |  | pending |  |  |
| U64 | [GK-02] (n8n, P0) **P0 live**: deploy the complete 51-node Anthology Drive Broker over the live 20-node `501` stub |  | pending |  |  |
| U65 | [GK-03] (n8n, P1) SECURITY: vault the hardcoded Podbean OAuth secrets; deploy the 8-node Podbean broker |  | pending |  |  |
| U66 | [GK-04] (live (operator), P1) Repair the n8n management-API key wiring (kills the "manual import" bottleneck); no-op write round-trip proof |  | pending |  |  |
| U67 | [GK-05] (GHL + n8n, P1) Podcast golden snapshot v2 + `PODCAST_SNAPSHOT_ID` confirmation (no-409 dry run) |  | pending |  |  |
| U68 | [GK-06] (ONB, P1) Facebook-workflow activation becomes a runbook checklist item with a QC-gate assertion |  | pending |  |  |
| U69 | [GK-07] (GHL, P1) Publish the 3 draft Anthology release-notification workflows; re-cut the anthology snapshot |  | pending |  |  |
| U70 | [GK-08] (GHL, P1) Provision the declared-but-unprovisioned `chapter_rewrite1`/`chapter_rewrite2` fields via the engine's own path |  | pending |  |  |
| U71 | [GK-09] (ONB + GHL, P1) Clear the WAF/edge 403 on `verify-imported`; run the never-yet-run snapshot chain end-to-end once |  | pending |  |  |
| U72 | [GK-10] (n8n, P1) Remove the leftover live gate-test workflow (TEMP — its own name demands deletion at cutover) |  | pending |  |  |
| U73 | [GK-11] (n8n, P1) Resolve the `Anthology Writer - Ben` monolith: exactly ONE live path, docs name it |  | pending |  |  |
| U74 | [GK-12] (n8n + ONB, P1) Canonicalize the podcast pipeline per D19 (kill the double-publish risk) |  | pending |  |  |
| U75 | [GK-13] (n8n, P2) Archive the 8 inactive `* CC`-suffixed duplicate workflows after a reference scan |  | pending |  |  |
| U76 | [GK-14] (live (read-only), P2) Instance-wide n8n/GHL audit read IN FULL + 100% finding disposition + adjacent-engine GHL surfaces |  | pending |  |  |
| U77 | [GK-15] (CC, P1) Podcast dashboard transplant into the Command Center per its own WIRING.md (engine-gated nav; all gates re-run) |  | pending |  |  |
| U78 | [GK-16] (live (read-only), P1) Anthology live triage T1–T3 on the operator's own box (version / drift signal / seeded+engine state) |  | pending |  |  |
| U79 | [GK-17] (CC (+ONB), P1) The REAL A7 repair: root-cause the silent mirror drop, then a converging self-healing reconcile (banner = last resort) |  | pending |  |  |
| U80 | [GK-18] (ONB, P2) Anthology tracking-document truth-up (1/55 checklist vs 56 shipped Python files — the audit trail must certify again) |  | pending |  |  |
| U81 | [GK-19] (live (operator), P0) Prove the Social Media Planner UNBROKEN against the graphics handoff end-to-end — or capture the exact break |  | pending |  |  |
| U82 | [GK-20] (ONB, P1) Resolve the band↔routing contradiction in ONE place (`prompt-bands.json` vs the Ideogram routing rule) + CI locks |  | pending |  |  |
| U83 | [GK-21] (ONB, P1) Dedicated Graphics prompt-author + prompt-QC roles (per D17), wired into the manifests and dispatch SOP |  | pending |  |  |
| U84 | [GK-22] (live → fleet, P0) On-box CONTENT proof for P3-05 (manifest `src_git_sha` + named files — never a version stamp alone) |  | pending |  |  |
| U85 | [GK-23] (ONB, P1) One-question-at-a-time UNFAKEABLE at the record layer: driver turn-ledger stamp + `AF-SP-INTAKE-UNPACED` (per D18) |  | pending |  |  |
| U86 | [GK-24] (ONB + live, P1) Reproduce + fix the on-box presentation Python breakage by root-cause class (stale content / deps preflight / `--workspace` flag) |  | pending |  |  |
| U87 | [GK-25] (live (operator), P2) 4-phase SACRED process-fidelity proof run (golden fixture, every prover receipt, phase-order check with teeth) |  | pending |  |  |
| U88 | [GK-26] (live (operator), P1) The content→conversation loop proven end-to-end ONCE on the operator's box (35 → 44 → GHL → 38, + Gap C matcher leg) |  | pending |  |  |
| U89 | [GK-27] (ONB, P1) ONE canonical relationship lattice document (Skills 6/44/35/38/3) + per-skill pointer + QC citation tripwires |  | pending |  |  |
| U90 | [GK-28] (ONB, P1) Strengthen Skill 3 as a first-class backstop: on-box drift gate, CLI version pin, consumer conformance battery |  | pending |  |  |
| U91 | [X/U-X1] (doc, P0) Banned-term scrub of the spec text (12 v1 hit-lines superseded) — **executed in this document**; run verifies first | [Sonnet 5 x1] build U91 | verified | Verify-only doc unit, no repo/branch (repo=none). Primary-source read of `skill6-blended-persona-kanban-MASTER-SPEC-v2-2026-07-13.md`: case-insensitive search for the retired term across the assembled spec returns 14 lines, ALL confined to the LANGUAGE CONFORMANCE defining sentence (L12) + annotated legacy-filename citations (L325,728,926,989,1213,1443,2165-2170,2174) — meets the binary acceptance test stated at spec L2261/X.1.2. LLM read (not bare pattern-match) of B-U9 (L845-850 = master U23) and B-U16 (L924-929 = master U30) confirms the monthly routing-drift-check and scheduled selector-drift-probe language/acceptance survived with meaning intact. 12-hit-line v1 accounting (9 Class-A + 1 Class-B + 2 Class-C) documented at spec L2148-2158. | 2026-07-13T22:10:45-04:00 |
| U92 | [X/U-X2] (ONB, P1) Docs-language CI guard (fails NEW occurrences; allowlists history, vendor literals, legacy filenames until renamed) |  | pending |  |  |
| U93 | [X/U-X3] (both, P2) Rename the remaining legacy-named files + live doctrine text + the two CC comments, with one-release shims (per D20; the four Skill-6 files are owned by U30 — one owner each, no double-rename) |  | pending |  |  |
| U94 | [X/U-X4] (CC, P1) Requester-stamping completeness at every human creation door + trust-coverage health metric ≥95% (absorbs v1 U20) |  | pending |  |  |
| U95 | [X/U-X5] (CC, P1) Orchestrator-only report-back invariant guard (static call-site pin + behavioral fixture + mutation proof) |  | pending |  |  |
| U96 | [X/U-X6] (doc, P1) ROUTED hand-off row: push-client-embeddings → the fleet-roll run (mechanism + 2026-07-14 embedding-model EOL context) |  | pending |  |  |
| U97 | [X/U-X7] (doc, P1) ROUTED (narrowed per updated D22): the interview→CC-provisioning GATE mechanism + its false-block regression guard stay in the Skill 23/32 lane; the department-provisioning WORK is now IN-spec as U107–U110 |  | pending |  |  |
| U98 | [E4-1 (v1 U28)] (ONB, P3) Blend GOVERNS the product-voice engines (D1 ruling): Skill 35 per-day blend via scoped bundles; Skills 51/58/54/59 reconciled so the blend governs voice+content — local voice logic removed, structure preserved, voice-path hash re-pin proven; anthology LAST |  | pending |  |  |
| U99 | [E4-2 (v1 U9)] (CC, P1) Raw-writer convergence to `transition()` + CI guard against new raw `UPDATE tasks SET status` writers |  | pending |  |  |
| U100 | [E4-3 (v1 U17)] (both, P2) Producer-reconcile generalized: Skill 35 cycle-manifest variant + the `mc_board` engine family, each with a health projection |  | pending |  |  |
| U101 | [E4-4 (v1 U25)] (CC, P2) Per-department SLA table (`config/board-slas.json`) feeding board-hygiene + stale-sweep, rendered on settings |  | pending |  |  |
| U102 | [E4-5 (v1 U27)] (CC, P2) Operator daily column-age digest (batched) + `notification-failures.jsonl` size as a health field |  | pending |  |  |
| U103 | [E4-6 (v1 U48)] (CC, P1) Due-date smart default in `createTaskCore` — priority-based, non-binding, editable/clearable; no client-facing prompt |  | pending |  |  |
| U104 | [E4-7 (v1 U49)] (CC, P1) Engine-mirrored card honesty: GatePanel empty-state copy fix, "Start Planning" gated off for anthology cards, card-type empty states |  | pending |  |  |
| U105 | [E4-8 (v1 U50)] (CC, P2) Task-modal in-app help: typed copy map + reusable `<FieldHelp />` popover + "i" icons + accessibility/mobile behavior |  | pending |  |  |
| U106 | [E5-1 (G1)] (ONB + live, P2) **Communities / courses / channels build + live-prove** (Skill-6 companion to U30): live-create a community → add channels → create a course on the operator box, smoke-first / receipt / cleanup discipline |  | pending |  |  |
| U107 | [E5-2 (G2a)] (both, P1) **Vertical never force-added**: interview→provisioning never force-adds a vertical (e.g. real estate) to a client who is not that vertical; provisioned set = interview-derived only |  | pending |  |  |
| U108 | [E5-3 (G2b)] (both, P1) **Department opt-out + functionality WARNING**: a client can opt a department OUT, shown a clear warning of the functionality lost, recorded and honored by provisioning |  | pending |  |  |
| U109 | [E5-4 (G2c)] (both, P1) **Floor-wipe provisioning bug**: interview provisioning must NEVER wipe / overwrite the department floor — fix + regression-prove |  | pending |  |  |
| U110 | [E5-5 (G2d)] (both, P1) **Department-set board wiring**: new / fewer-than-floor department sets wire correctly onto the Command Center board (no orphan/ghost columns; catch-all honored) |  | pending |  |  |
| U111 | [E5-6 (G4)] (ONB, P1) **"Any content" blend-governance proof**: NAME + prove email, blog, newsletter, and text-message engines EACH receive and are governed by the blend through the U1 seam |  | pending |  |  |
| U112 | [E5-7 (G5)] (ONB + live, P2) **Skill 6 bulk-send GHL workflow**: add many contacts via tag / arrays into a GHL workflow (surfaced in a live SMS firefight) — build + prove |  | pending |  |  |
| U113 | [E5-8 (G6)] (ONB, P2) **Unified fallback ladder**: single browser→API→MCP fallback-ladder acceptance across Skill 6 surfaces ("inability to fail") on top of method routing + per-surface drag fallbacks |  | pending |  |  |
| U114 | [E5-9 (G3)] (ONB, P3) **Product-voice-engine governance conformance** (D1 ruling): decommission independent local voice logic in Skills 51/58/54/59; prove the blend GOVERNS each engine's voice+content; no-exemption invariant |  | pending |  |  |
| U115 | [E6-1 (G7)] (both, P1) **Per-part / per-persona governance** (operator ruling ADD-1): decompose multi-part / long-horizon tasks into parts, assign + TRACK a governing blend PER PART (own audience+topic), surface per-part assignment on board + task detail (reuses the U5 scoped-bundle table) |  | pending |  |  |
| U116 | [E6-2 (G8)] (both, P1) **Communication trigger + audience-confirmation prompt** (operator ruling ADD-2): every outside-world comms (page/blog/email/SMS/social) is blend-governed + topic-factored, PROMPTS for standard-vs-specific audience before writing, surfaces the chosen audience on the card |  | pending |  |  |
| U117 | [E6-3 (G9)] (both, P1) **Comms-artifact QC + conformance invariant** (ADD-3): score comms on per-part governance, blend used, topic considered, audience confirmed (extends U25/U19/U26); per-part governance + audience prompt become part of the D1/FAB-QC invariant |  | pending |  |  |

**Total: 117 units (U1-U117). U1 = `verified` (merged `skill6-v2/U1` -> `main` @ `292f4ee4`, ripple @ `9f406872`, tag `v20.0.17`). U2 = `verified` (merged `skill6-v2/U2` -> `main` @ `86420ff7`, ripple @ `e8cc7fce`, tag `v20.0.18`). U91 = `verified` (doc unit, no repo/branch, primary-source re-verified this pass). Remaining 114 units `pending`, labels/evidence blank pending dispatch.**

# Changelog - Book-to-Persona

All notable changes to this skill wrapper are documented here.

---

## v6.17.0 - 2026-07-09 - feat(schema 1.3): additive audience/topic/voice_style/usable_as enrichment across all 99 personas + vocab-validated publish path

Additive-only enrichment layer that turns the catalog into the reasoning surface for the Skill-23 voice-first AUDIENCE+TOPIC blend matcher. No persona keys added or removed (the N38 count triad stays green at 99); the persona-set count, blueprint dirs, and INDEX-MANIFEST are untouched.

- **`persona-categories.json` schema 1.2 -> 1.3:** every one of the 99 personas gains `audiences[]`, `topics[]`, `voice_style{summary(req),tone[],devices[],cadence,signature_moves[],avoid[]}`, and `usable_as[]` (subset of `[audience,topic,task]`; default when absent = `[topic,task]` — serving as an AUDIENCE voice must be explicit; 21 personas carry `audience`). Adds top-level controlled-vocabulary arrays `audienceTags` (450) and `topicTags` (752), derived as the union of the per-persona tags so every used tag is a vocab member. `lastUpdated` bumped to 2026-07-09.
- **Tag-validator extended (`pipeline/persona_fleet.py`):** `_validate_entry` now validates `audiences[]`/`topics[]` against the `audienceTags`/`topicTags` controlled vocab (kebab-case + membership when the vocab is populated), `usable_as[]` against the enum, and requires `voice_style.summary` when `voice_style` is present. All new fields OPTIONAL so a schema-1.2 entry still validates.
- **Publish path made enrichment-safe:** `CANONICAL_ENTRY_FIELDS` extended with the four enrichment fields and `sync_categories` now carries forward any repo-side enrichment a (possibly older 1.2) workspace does not itself supply — so a `publish-personas-to-fleet.sh` run can never silently strip the 1.3 enrichment. Propagation stays through the one atomic publish command; the coupled artifacts are never hand-edited.

## v6.16.2 - 2026-07-06 - feat(FDN-1 + DEP-6): blackceo-house-voice fallback seed + hunt-thomas CODE-craft specialist + software-craft domainTag (81->83, prebuilt-index v2.4.0)

Lands the two remaining persona-library additions against the published **prebuilt-index-v2.4.0** asset (83 personas). Supersedes ONB PRs #532/#539.

- **`personas/blackceo-house-voice/persona-blueprint.md` + `persona-categories.json`:** hand-authored brand-neutral fallback persona (`fallback:true`, domains `["communication"]`, no perspective/specialty tags) — the permanent `DEFAULT_PERSONA_FALLBACK` seed so no task is ever naked. Excluded from the normal scoring funnel.
- **`personas/hunt-thomas-pragmatic-programmer/persona-blueprint.md` + `persona-categories.json`:** first true software-craft specialist (The Pragmatic Programmer), domain `["software-craft", …]`, `_craft_slot:"code"`.
- **New controlled-vocab `domainTags` entry `software-craft`** so hunt-thomas's craft domain is in-vocab (mirrored in the selector's four craft tables — see the 23-ai-workforce-blueprint change).
- **`INDEX-MANIFEST.json`:** `persona_count`/`canonical_persona_count`/`embedded_persona_count` = 83, `release_tag` `prebuilt-index-v2.4.0`, `asset_rebuild_required:false`, `persona_set_md5` re-stamped to the shipped 83-key categories (metadata-only re-pin, persona membership unchanged — NOT an asset rebuild). `INSTALL.md` counts re-baselined to 83 / ~1,189 rows.
- Count triad agrees at 83 (blueprint dirs == categories keys == manifest persona_count == canonical_persona_count == embedded_persona_count). No client names.

## v6.16.1 - 2026-07-05 - fix(DEP-13 P3 hygiene): stale install counts, pending-publish nag, LRU task cache, provisioning default, log-format unification

P3 hygiene bundle from the persona-matching analysis (train DEP-13: F1.5, F1.6, F2.4, F2.5, F4.6). No behavior change to matching quality — these close staleness / unbounded-growth / silent-default footguns.

- **F1.5 — stale install docs + manifest note (`INSTALL.md`, `shared-utils/prebuilt-index/INDEX-MANIFEST.json`):** `INSTALL.md` Step 5 hardcoded "48 personas / ~7,615 chunks" and a `< 7000`-row verifier — both stale AND inverted for the current SECTION-TAGGED asset (~1,161 rows for the current SET; the real index would have FALSE-FAILED the doc's own verify). Corrected the persona count to 82 and the row references to the section-tagged count; the Step 5-E verifier now checks against the manifest's `chunk_count` (exported by Step 5-B) with a conservative floor, instead of the obsolete paragraph-index threshold. Refreshed the pinned offline-fallback asset/sha to the current release. Dropped the stale `ROHDE NOTE (open)` from the manifest `notes` (the selector's `_CATEGORY_DOMAINS['design']` already includes `visual-storytelling`, so the "gap" it described is fixed — the note was causing re-litigation of a closed defect).
  - **NEW `shared-utils/prebuilt-index/assert-install-doc-consistency.py`** + wired into `persona-set-asset-consistency-guard.yml`: fails CI when `INSTALL.md`'s persona-count prose drifts from `INDEX-MANIFEST.json` `persona_count` (a one-step re-baseline seam is a NOTICE, larger drift FAILS; no hardcoded count in prose also passes). Test: `tests/unit/install-doc-consistency.test.sh`.
- **F1.6 — pending-publish nag (`scripts/persona-inbox-watcher.sh` → v6.7.0):** a `.fleet-publish-pending.json` marker (workspace personas added but not yet published to the fleet) blocked nothing until the next commit/roll, so a set could sit unpublished for days. The watcher now emits an OPERATOR-ONLY nag once per `PERSONA_PENDING_NAG_HOURS` window (default 24h) when the marker is older than that. Client-silent by construction: routed only through the existing opt-in, co-mingling-guarded operator-chat resolver (`_operator_notify`; log-only when no operator chat is configured), and the marker only exists on the operator's fleet-publish box. Throttled so it never fires every 10-minute cron tick.
- **F2.4 — LRU-bounded task-embedding cache (`shared-utils/semantic_task_fit.py`):** the module-level `_TASK_EMBED_CACHE` grew one entry per unique task text for the process lifetime (harmless for the CLI, a latent leak if imported into a long-lived server). Now an `OrderedDict` bounded to `_TASK_EMBED_CACHE_MAX` MRU entries (default 256, override `SEMANTIC_TASK_FIT_CACHE_MAX`); reads go through `_task_cache_get`/`_task_cache_put` so the "embed the task once, share across N personas" contract is preserved and eviction is O(1) from the oldest end. Test: `tests/unit/semantic-task-fit-lru.test.py`.
- **F2.5 — no stale positive provisioning default (`shared-utils/provision-persona-index.sh`):** `persona_count` defaulted to `54` when the manifest read failed, silently gating the persona-dir check against an obsolete constant. Now defaults to `0` and treats `0`/absent/unreadable as "no trustworthy count" → `_pidx_skip_warn` skip-with-warn (additive; keeps the current index), never a positive lie. Refreshed the stale `(54)` / `(4413)` gate comments to say "read live from the manifest".
- **F4.6 — selection-log format:** verified consistent — the canonical selector's `write_selection_log_md` (Markdown TABLE) is the single writer/format of `persona-selection-log.md`. The competing bracketed "self-selection" prose is removed by the dispatch-injection train (F4.1/FDN-3) that deletes agent self-selection; no separate change is made here to avoid re-touching the version-lockstep Skill-23 protocol doc.
- **Re-land onto main @ v17.0.33 (skill-22 v6.16.0 held by DEP-12/F1.4):** merged latest `main`; re-headed this entry `v6.16.0 → v6.16.1` and bumped `skill-version.txt` above main (main already occupies v6.16.0). Resolved the `shared-utils/provision-persona-index.sh` conflict by KEEPING main's F2.1 SUBSET/SUPERSET + client-local-preservation gate documentation and folding in F2.5's absent/zero/unreadable `persona_count` → skip-with-warn clause (comment-only; the F2.5 executable default `0` + `_pidx_skip_warn` auto-merged unchanged). Manifest `persona_count` is still `81` (FDN-7's 81→82 re-baseline not yet landed), so the new INSTALL.md doc-consistency step reports a one-step ±1 NOTICE and passes; it becomes an exact match once FDN-7/DEP-6 ship the 82nd persona.

## v6.16.0 - 2026-07-05 - fix(F1.4): Phase-6 categories write is FAIL-LOUD + AUTO-REPAIR — a lint failure can no longer strand an unselectable persona

A blueprint that finished the pipeline could be left with NO key under
`persona-categories.json.personas` — invisible to `persona-selector-v2.py`'s
`list_available_personas()` universe (which reads exactly that dict's keys), an
unselectable orphan. Root cause: `pipeline/orchestrator.py` Phase 6 wrapped
`_append_persona_to_categories` in a `try/except` that caught EVERY exception
(including the P13-2 schema-lint `PersonaCategoriesSchemaError`) and logged a
WARNING — the run still exited 0 (a silent success, the categories-side mirror
of F1.2's "registered but not embedded"). Fixes, mirroring F1.2 / FDN-5's
fail-loud exit pattern:

- **NEW `_phase6_register_categories()`** replaces the swallow-and-warn call
  site. It gives the contract TWO independent guarantees:
  1. **Never-to-zero on registration itself (AUTO-REPAIR):** when the normal
     auto-classified append fails, the persona is re-registered with a
     SAFE-DEFAULT tag set (`domain: ["leadership"]`, a controlled-vocab member
     so it passes both the schema-lint gate and `persona_fleet.py sync-categories`
     validation) plus an additive `needs_retag: true` marker — rather than
     skipping the entry. The persona ALWAYS gets a categories key and stays
     selectable.
  2. **Fail-loud:** a Phase-6 write that needed the repair (or failed even that)
     is recorded in a module-level accumulator; `main()` then exits the distinct
     `PHASE6_CATEGORIES_EXIT_CODE = 9` (never 0), so the caller
     (`add-persona-from-source.sh` / the inbox watcher) can tell "operator must
     re-tag" apart from a clean build and route to retry/quarantine.
- **`_append_persona_to_categories(..., domain_override=, needs_retag=)`**:
  additive params power the auto-repair path (bypass the auto-classifier, write
  the safe-default entry, stamp the marker). Existing callers are unchanged.
- **`persona-categories.json` → schema 1.2**: registers the optional additive
  `needs_retag` marker (documented in `persona-categories.README.md`). It is a
  workspace-only field — `sync-categories` ships only the canonical seed fields,
  so it never leaks into the shipped seed.
- **Test:** `tests/unit/phase6-categories-fail-loud.test.sh` — 21 assertions
  driving the happy path, the lint-failure auto-repair (safe default + marker),
  the SystemExit(9) fail-loud gate (and its no-op on a clean run), the hard-fail
  (both writes raise) path, never-to-zero selector-universe visibility, and
  multi-book accumulator aggregation. Hermetic (no network / no Gemini key;
  sandboxed log/status/categories paths — never touches the real workspace).
- **Re-land:** merged latest `main` into the branch (skill-22 v6.15.2 / repo
  v17.0.29) after the F1.2/FDN-5 (v6.15.1) and F1.3/F2.2 (v6.15.2) merges;
  resolved the single-book `main()`-tail conflict by KEEPING BOTH fail-loud gates
  in order — Phase-5 embed (exit 8) then Phase-6 categories (exit 9);
  skill-version `v6.15.2 → v6.16.0`.
- **Re-land onto v17.0.33 (post Wave-0):** merged latest `main`; resolved the two
  skill-22-local conflicts (`skill-version.txt` → `v6.16.0`, CHANGELOG head).
  Re-pinned `shared-utils/prebuilt-index/INDEX-MANIFEST.json`
  `persona_set_md5` `e57f4150…` → `925207fd…` so the D13 provision-idempotency
  5d/5e assertion (which hashes the schema-1.2 `persona-categories.json` against
  the manifest pin) goes green — metadata-only, persona MEMBERSHIP unchanged at
  81 (`persona_count`/`canonical`/`embedded` and `asset_rebuild_required:false`
  untouched → protected-ref asset-consistency guard stays green). Also fixed a
  full-batch `main()`-tail regression introduced by the earlier tail merge: the
  F1.2/FDN-5 `if embed_failed: sys.exit(8)` gate had been relocated into the dead
  tail of `_exit_if_categories_failed()` (after its unconditional `sys.exit(9)`),
  so full-batch mode had silently lost its exit-8 embed fail-loud gate. Restored
  it INSIDE `main()` before the Phase-6 categories gate, matching the single-book
  ordering (embed 8 → categories 9).
## v6.15.3 - 2026-07-05 - fix(persona-provisioning/F2.1): client-box updates no longer destroy client-locally-added personas

FOUNDATION train FDN-6, fix F2.1 (persona-matching-analysis-2026-07-05.md §2.2). A client box that ran this skill on the client's OWN book had its persona DEREGISTERED and its vectors CLOBBERED at every `openclaw update`, via two compounding mechanisms in `shared-utils/provision-persona-index.sh` (the helper that reconciles this skill's `persona-categories.json` + blueprints onto client boxes):

1. `reconcile_persona_assets` blind-copied the shipped seed `persona-categories.json` over the workspace copy whenever the md5 differed, so the client's extra persona keys were overwritten and the selector universe (= categories keys) silently deregistered the client's persona. → Replaced the blind `cp -f` with a UNION MERGE (`_pidx_union_merge_categories`): seed WINS for seed slugs; box-local keys not in the seed are PRESERVED and stamped `origin:"local"`. With no local persona the merge is a byte-identical seed copy, so the canonical `persona_set_md5` is preserved exactly (reconcile idempotency contract unchanged).

2. `provision_persona_index` gate condition (c) required installed `chunk_count == manifest` EXACTLY, so a canonical index carrying the manifest asset PLUS the client's own locally-embedded persona (more chunks/personas) was judged non-canonical and the whole DB was re-downloaded, destroying the client's vectors. → Gate now uses SUPERSET semantics WHEN a client LOCAL DELTA exists (more persona dirs OR more distinct embedded personas than manifest): canonical iff columns ok AND installed chunks ≥ manifest AND embedded-persona coverage ≥ manifest AND persona dirs ≥ manifest. WITHOUT a local delta the historical EXACT semantics are retained so a stale same-set short/over-chunked index still converges (the 6260/7615/9456-row convergence the gate was built for is preserved; `tests/unit/provision-idempotency.test.sh` unchanged and green). On a genuine re-download, origin:local persona rows are EXPORTED from the old DB and RE-INSERTED into the fresh canonical DB (`_pidx_export_local_rows` / `_pidx_reinsert_local_rows`); anything that cannot be carried over is queued in `.persona-local-reembed-queue` (furnace-safe — NO embedding here) for a delta re-embed with the CLIENT's OWN key, never an operator/shared key.

`update-skills.sh` Step U6b surfaces the `.persona-local-reembed-queue` marker in the operator completion report (operator-visible only, never client-visible — silent-updates doctrine).

Shared-gate RE-LAND: `.github/workflows/both-paths-delivery-guard.yml` step D12 hard-asserted the retired equality literal `chunk_count != manifest chunk_count`, which the SUPERSET semantics above removed — the stale assertion would have failed the repo-wide both-paths delivery guard. Updated D12 to assert the superset wording (`chunk_count >= manifest`) plus the `_HAS_LOCAL_DELTA` decision marker, so the guard now verifies the F2.1 superset gate rather than the removed equality string.

New regression lock: `tests/unit/provision-preserves-local-personas.test.sh` (16 assertions: union-merge preservation + seed-wins + no-drift md5; superset index → skip/preserve; genuine subset → still re-provisions; export→re-insert round-trip).

## v6.15.2 - 2026-07-05 - fix(F1.3/F2.2): close the `--no-asset` counted-but-vector-less window with an `embedded_persona_count` 5th triad member

A `--no-asset` staging bump (`pipeline/persona_fleet.py set-manifest-counts --no-asset`) lifts the four SET counts (blueprint dirs / categories keys / `persona_count` / `canonical_persona_count`) and flips `asset_rebuild_required:true`, but the published `gemini-index.sqlite.gz` still embeds ZERO vectors for the new persona(s). Every existing triad gate compares counts only, so N38 went green (pre-commit, CI, U6b, publish gate all passed) while the served asset was stale — a live, test-exercised path that could land a "counted-but-vector-less" persona on client boxes (Layer-5 retrieval silently degrades to keyword for them). Three cheap gates now close it, no new machinery:

- **`pipeline/persona_fleet.py`** — `triad_counts()` now also reads `INDEX-MANIFEST.embedded_persona_count` (the 5th SET-triad member) + `asset_rebuild_required`. `cmd_triad` keeps the four SET counts as a hard invariant AND checks the embedded count: when `asset_rebuild_required:false` but `embedded_persona_count != persona_count`, the asset lacks vectors for the delta → **exit 5** (`ASSET DISAGREES`). When `asset_rebuild_required:true` (a legitimate mid-flight `--no-asset` bump), the 5th member is **carved out** (exit 0) with an explicit note naming the pending asset rebuild as the real cause. `set-manifest-counts --no-asset` deliberately DOES NOT touch `embedded_persona_count`, so the lag — and therefore the gate — is provable; `build-and-publish.sh` (full build) is the only writer that advances it (from the live `SELECT COUNT(DISTINCT persona_id)`). Legacy manifests without the field stay back-compatible (5th member skipped).
- **Coordinated non-skill-22 gates (same change, separate files):** `.github/workflows/persona-set-asset-consistency-guard.yml` refuses `asset_rebuild_required:true` on a PROTECTED ref (main / release/* / tag) while ALLOWING it on PR branches so staging stays possible, and enforces the same `embedded_persona_count` 5th member with the `--no-asset` carve-out. `update-skills.sh` Step U6b + `shared-utils/provision-persona-index.sh` now REFUSE to (re)provision a client box from an `asset_rebuild_required:true` manifest (warn + keep the box's current index) so a staged asset can never propagate as canonical. `shared-utils/prebuilt-index/INDEX-MANIFEST.json` carries `embedded_persona_count: 81`.
- **Test:** `tests/unit/asset-rebuild-required-gate.test.sh` — provisioning refuses a staged manifest (keeps the current index, no clobber), the triad exits 5 on counted-but-vector-less and 0-with-carve-out on a staged bump, `set-manifest-counts --no-asset` leaves `embedded_persona_count` stale, and the manifest a `--no-asset` bump produces is refused end-to-end by provisioning.

_Note: the canonical N38 impl `23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py` deliberately was NOT edited — skill 23's `skill-version.txt`/`SKILL.md version:` are repo-locked version markers, so touching it forces a repo-wide `/version` bump (out of scope, and a tag-race hazard with concurrent trains). The 5th-member enforcement lives instead in `persona_fleet.py` (the publish + `assert-personas-published.sh` pre-roll gate) and the dedicated CI guard, which are real merge/roll gates on the exact files that move._
## v6.15.1 - 2026-07-05 - fix(pipeline): Phase-5 embed failure is fatal end-to-end (F1.2 / FDN-5)

Persona-Matching-Overhaul FOUNDATION train FDN-5, fix F1.2 — "registered but not
embedded ships silently". Before this, `pipeline/orchestrator.py` marked
`phase5: FAILED` in `pipeline-status.json` but `process_book()` never checked
Phase 5's outcome, so the orchestrator exited 0; `add-persona-from-source.sh`
saw `PIPELINE_RC=0` and marked the persona ready-to-publish even though its
blueprint was **matchable but vector-less** on that box (Layer-5 semantic
retrieval can never surface it — the exact failure class N38 guards against, but
on the workspace side where N38 does not run).

- **`pipeline/orchestrator.py`** — Phase-5 `FAILED` now propagates a DISTINCT
  process exit code (`8` = EMBED_FAILED) end-to-end, in BOTH `--single-book`
  mode and full-batch mode. The blueprint is deliberately LEFT ON DISK so an
  idempotent retry re-embeds only: `run_synthesis` gained a `_phase3_already`
  re-entry that SKIPS the costly LLM synthesis (and an already-COMPLETE Phase 3b)
  when the blueprint exists and `phase3 == COMPLETE`, running Phase 5/6 only; the
  single-book early-return is now `phase5`-aware so a retry re-enters to re-embed
  instead of short-circuiting.
- **`scripts/add-persona-from-source.sh`** — on `rc 8` it prints a LOUD
  EMBED_FAILED banner and propagates `exit 8` (so `persona-inbox-watcher.sh`
  quarantines/retries) WITHOUT marking fleet-publish pending. Added the
  WORKSPACE triad-equivalent as a terminal gate: blueprint on disk + registered
  in `persona-categories.json` + ≥1 index row — a second net for the case where
  the pipeline exits 0 but Phase 5's safety-net indexer silently no-ops. Warn-only
  under `--skip-index`.
- **Reconciled to the FDN-4 shared contract (no duplicate helper).** The terminal
  gate delegates to the ONE shared `pipeline/usable-persona-contract.sh` (landed
  in v6.15.0 / FDN-4) via a thin shim in the wrapper — it does NOT re-implement
  the three-leg contract, so the workspace triad-equivalent (F1.2) and the inbox
  watcher's `processed/` gate (F1.1) share exactly one source of truth.
- **Tests** — `tests/unit/workspace-usable-persona-triad.test.sh` (5 hermetic
  cases against the shared contract script, incl. the vector-less / "registered
  but not embedded" FAIL and no cross-slug credit) and
  `tests/unit/orchestrator-embed-fail-exit8.test.py` (Phase-5 FAILED → exit 8,
  DONE → exit 0, blueprint left on disk).
- **Re-land:** rebased onto `main` (v6.15.0) after the FDN-4 shared-contract
  merge; resolved the `tests/unit/usable-persona-contract.test.sh` add/add
  collision by renaming this train's test and dropping the redundant
  `lib-usable-persona-contract.sh`; skill-version `v6.15.0 → v6.15.1`.

## v6.15.0 - 2026-07-05 - fix(F1.1): inbox-watcher false-success — shared usable-persona contract gates the `processed/` move

A book could be consumed and moved to `inbox/processed/` with a SUCCESS log line while NO persona was ever built — silently losing the source with no retry. Root cause: `scripts/add-persona-from-source.sh` exited **0** on the "orchestrator missing" branch (environment broken, treated as success), and `scripts/persona-inbox-watcher.sh` treated any exit-0 as SUCCESS and moved the source to `processed/` — no blueprint, no `persona-categories.json` key, no index row, so the N38 triad could never see it and there was no source left to retry.

- **`scripts/add-persona-from-source.sh`** (→ v10.14.35): the orchestrator-missing branch now exits **7 (`ORCHESTRATOR_MISSING`)** instead of 0, so the caller can tell "environment broken, retry later" apart from "usable persona built". Retired the dead `pipeline_status` field from the written `source.json` (it was written in two places and read nowhere — a no-op that pretended to carry state). Also hoisted `SCRIPT_DIR_APS` to an unconditional definition up front so the terminal fleet-publish phase can never hit a `set -u` unbound-variable abort on an installed box (pre-fix it was only defined inside the orchestrator-fallback branch).
- **NEW `pipeline/usable-persona-contract.sh`** (v1.0.0): the ONE shared, fail-closed "is this persona actually usable on this box?" contract — asserts all three legs (blueprint present + non-empty; slug is a key under `.personas` in `persona-categories.json`; ≥1 row in the `gemini-index.sqlite` `embeddings` table whose `file_path` is under `coaching-personas/personas/<slug>/`). Distinct exit codes per missing leg (2/3/4). Prefix-slug-safe (a `foo-bar` index row does not satisfy `foo`). Modelled on Skill 23 SOP-07 `assert_persona_grounded()`.
- **`scripts/persona-inbox-watcher.sh`** (→ v6.6.1): the success branch now asserts the usable-persona contract BEFORE any `mv` to `processed/`. A zero exit from the converter is necessary but not sufficient; any missing leg routes the source through the existing failure/retry/quarantine path (never `processed/`), so a book can no longer be lost silently.
- **Test:** `tests/unit/usable-persona-contract.test.sh` — per-leg exit codes + prefix-slug safety, plus an end-to-end watcher harness (sandboxed HOME, stub converter) proving the watcher never moves a source to `processed/` on false-success, on a vector-less (no-index-row) persona, or on an `ORCHESTRATOR_MISSING` (exit 7) result.

## v6.14.0 - 2026-07-05 - feat(pipeline): ONE atomic "publish personas to the fleet" command + workspace↔repo divergence guards

The book pipeline writes the WORKSPACE only; the repo library (blueprint dirs + `persona-categories.json` seed), the INDEX-MANIFEST, and the release asset used to be caught up by hand, so they lagged and the N38 count triad went red at CI/roll. New `pipeline/publish-personas-to-fleet.sh` moves all four together atomically (sanitized blueprints, controlled-vocab categories, delegated HASH-SKIP asset rebuild) and refuses (rolling back — no half-commit) unless the triad + asset sha256 all agree at N. New `pipeline/assert-personas-published.sh` (standalone + pre-commit + `update-skills.sh` pre-roll) and `pipeline/fleet-publish-status.sh` (terminal-phase pending marker written by `add-persona-from-source.sh`) make a forgotten publish impossible. Hermetic core: `pipeline/persona_fleet.py`. Regression lock: `tests/unit/publish-personas-to-fleet.test.sh`. Runbook: `PIPELINE.md` → "Adding books → publishing personas to the fleet".

## v6.13.1 - 2026-07-01 - fix(pipeline-hardening): full-rebuild guard + persona-categories schema-lint + appendix status surfacing

Final-review Points 12 and 13 fixes for `pipeline/gemini-indexer.py` and `pipeline/orchestrator.py`
(`23-ai-workforce-blueprint/scripts/persona-selector-v2.py` consumes the same field but tracks the repo
version, so its half of the change is logged there, not here).

- **`gemini-indexer.py` full-rebuild guard**: the wrapper now inspects `sys.argv` before delegating to
  `embedding_engine._indexer_main()`. If `--rebuild` (FULL rebuild) is requested, `--status` is not also
  present, and `--force-full-rebuild` was not passed, it resolves the `coaching_personas` dir and checks for
  the `.prebuilt-index-version` sentinel; if present, it REFUSES (stderr message, exit 3) without calling
  `main()`, protecting the canonical sha256-verified ship-don't-re-embed index. `--force-full-rebuild`
  (operator-only, never for client-facing docs) is stripped from argv and lets `--rebuild` through.
  Incremental/delta runs (no `--rebuild`) are unaffected.
- **`orchestrator.py` schema-lint gate**: added `PersonaCategoriesSchemaError`, `_lint_tag_list()`, and
  `_lint_persona_categories_write()` — a hard-fail schema-lint validating every `domain[]`/`perspective[]`
  tag on a new persona entry is a well-formed lowercase-kebab-case string that matches or well-formed-extends
  the existing `domainTags[]`/`perspectiveTags[]` vocab. Wired into `_append_persona_to_categories()`
  immediately before the `json.dump` write; a malformed tag raises naming the offending key and the file on
  disk is left byte-for-byte unchanged.
- **`orchestrator.py` appendix status surfacing**: `_append_persona_to_categories()` now stamps an
  `appendixStatus` field (`COMPLETE`/`COMPLETE_WITH_WARNINGS`/`FAILED`/`MISSING`) on every new persona entry —
  prefers the caller's `pipeline-status.json` phase3b verdict (passed from `process_book`'s Phase 6 call
  site), falls back to a `PLAYBOOK-APPENDIX.md` file-existence check when no status is supplied.

---

## v6.11.1 - 2026-06-27 - fix(task-mode-wiring): Persona Reflex now mandatory + explicit, and its body actually merges

The Persona Reflex in CORE_UPDATES.md is rewritten from "load returned persona's Task Mode" to a MANDATORY
4-step load-and-apply for every professional task: search (with `--mode leadership`), open the matched
`persona-blueprint.md`, LOAD Section 4 (Execution Standard + Decision Logic + Definition of Done + Failure
Patterns) and Section 7B, BUILD to that standard, then VERIFY against the Definition of Done. Paired with a
fence-aware fix to the CORE_UPDATES merger (`update-skills.sh`) so the Reflex BODY actually transfers into
AGENTS.md instead of only stamping the "applied" marker. Guarded by `tests/unit/persona-task-mode-wiring.test.sh`.

---

## [v6.10.0] - 2026-06-27

### Deepened — acuff-miner-new-model-of-selling + miller-building-storybrand blueprints

Two existing persona blueprints upgraded from concise first-pass versions to full 14-section depth, passing independent no-padding verification.

- **`acuff-miner-new-model-of-selling/persona-blueprint.md`** (v1.1 → v1.2): 197 → 317 lines (+120). Expanded Section 1 with full bios for both authors (Acuff: 20-year pharma career, Salesman/District Manager awards, Delta Point founding; Miner: #45 earner out of 100M worldwide, 12-year NEPQ development arc), added "why this pairing is uniquely qualified" block. Section 2 adds Definition Reset keystone, Three-Destinations qualifier (D1/D2/D3), post-trust era framing with named statistics (3% trust, 95% talk-too-much, 86% wrong-questions). Section 3 gains milestone per phase, completion criteria, session length guidance. Section 4A gains decision-logic table (15 rows). Section 4B gains pre-delivery Yes/No checklist. Section 4C gains Amateur vs Expert comparison table. Section 4D (Task Mode Activation Language) is entirely new. Section 5 restructured into Coaching Principles + Eight Laws of Sales Intent + Five Rules of Buying. Section 7 gains confidence scoring table and 12-trigger lists for both coaching and task mode. Sections 8–14 all materially expanded with question libraries, tool list, objection table, session structure, and routing rules.

- **`miller-building-storybrand/persona-blueprint.md`** (v2.0 → v2.1): 179 → 628 lines (+449). Section 1 rewritten to include Science Mike McHargue + Kahneman + Amy Cuddy + Viktor Frankl science backbone and expanded author credibility proof. Section 2 restructured (Root Cause / Execution Gap / Theory of Change / Repeatable System). Section 3 is a full new 3-phase coaching arc (Assessment → Challenge → Support/Verify/Improve) with per-phase diagnostic/challenge/support questions, milestones, session arc, and setback/celebration protocols. Section 4 expanded: ≥7-step execution checklist, 8 non-negotiable rules, 11-row decision table, 11-item QC checklist, 8-row failure taxonomy, Amateur→Expert gap table, activation language. Sections 5–14 entirely new (Foundational Principles, Problem-Solution Map, Trigger Detection with confidence scoring, Voice & Language, Quote Library with 10 direct quotes + 8 one-liners + 5 metaphors, Question Library with 4×7 coaching + 3×4 governance questions, 5 coaching tools + 5 agent execution frameworks, objections table + counterintuitive truths, 6-session arc + task structure, department routing table + 5 handoff sequences + 4 hard stops, Companion Appendix Index). No filler — every added section introduces framework-specific content distinct from adjacent sections.

Verified no padding: acuff-miner uses distinct question sets per section; miller sections 4/5/9/10 cover governance, principles, verbatim quotes, and question libraries respectively — no repetition across sections.

---

## [v6.9.2] - 2026-06-27

### Fixed — persona-categories.json schema consistency + Pedro Day-4 source-gap accuracy

- **`persona-categories.json` — `brunson-network-marketing-secrets.appendix`**: was the only one of the 11 appendix-bearing personas whose `appendix` field was a dict object (`{present, richness, sections, notes}`) instead of a path string. Normalised to the string path `personas/brunson-network-marketing-secrets/PLAYBOOK-APPENDIX.md` (matching the other 10 entries); the richness detail is preserved without loss in new sibling fields `appendix_sections` (A–H) and `appendix_notes`. Zero dict-form `appendix` fields now remain.
- **`pedro-adao-challenge-secrets-masterclass` Day-4 source-gap note (3 locations: blueprint Source-Type line, blueprint Section-14 honesty note, appendix Source-fidelity note)**: tightened from the imprecise "Day-4 module partially absent" to the forensically-verified statement of fact — the source FILE contains only Days 1, 2, 3, 5 (Days 1 and 3 each duplicated → six segments); the dedicated Day-4 "Planning Your Challenge" session recording is **genuinely absent** (no Day-4 segment/opener/closer exists), corroborated only by the Day-3 preview and Day-5 "yesterday" back-references. No content fabricated; the note now states a verbatim Day-4 module requires sourcing the original Day-4 recording separately.

## [v6.9.0] - 2026-06-26

### Shipped — PLAYBOOK-APPENDIX.md for all 10 QC-approved book personas
Delivers the Phase 3b companion appendix for every book persona shipped in v14.3.16–v14.3.19.
Each persona directory now contains:
1. `persona-blueprint.md` — upgraded to companion-aware version (frontmatter `companion: PLAYBOOK-APPENDIX.md`; cross-references appendix throughout instead of embedding scripts/recipes/frameworks inline).
2. `PLAYBOOK-APPENDIX.md` — 8-section (A-H) rich asset file: hook/headline formulas, funnel/page recipes, sales + objection + discovery + follow-up scripts, email sequences, frameworks/models with steps + worked examples, brand-voice patterns, verbatim swipe file, asset coverage map.

Books shipped: The New Model of Selling (NEPQ), The Brand Mapping Strategy, Coach Builder, Building a StoryBrand, Marketing Secrets Blackbook, Copywriting Secrets, Lead Funnels, Network Marketing Secrets, The Sketchnote Workbook, The Funnel Hacker's Cookbook.

persona-categories.json bumped to schema v1.1; all 10 entries gain `appendix`, `appendix_status`, `appendix_richness`, merged custom tags, and `_perspective_note` where applicable. PERSONA-ROUTER.md gains `[+APPENDIX]` markers.

---

## [v6.8.0] - 2026-06-26

### Added — Phase 3b Playbook Appendix (depth preservation; fixes over-concise funnel/website copy)
The 14-section `persona-blueprint.md` DISTILLS a whole book into a governance +
coaching persona. That distillation was making the funnel/website copy it drives
too concise — the book's actual reusable assets were compressed away. This release
adds a mandatory companion, `PLAYBOOK-APPENDIX.md`, generated automatically for
EVERY future book, that PRESERVES those assets at full fidelity so copy
specialists write rich, brand-building copy.

**Pipeline code changes (every future book gets the appendix automatically):**
- `agent-prompts/extraction-agent-prompt.md` — added the **Playbook Asset Lens
  (items 21-30)**: headline/hook/subject formulas, page-by-page funnel/page recipes,
  sequences, sales/objection/follow-up/discovery scripts, email scripts & sequences,
  frameworks/models/templates with steps, brand-voice & brand-building language
  patterns, offer/guarantee/CTA/bonus language, a verbatim swipe file, and an asset
  coverage self-report — each captured as PATTERN + worked EXAMPLE + SOURCE. Min
  output raised 5,000 → 8,000 chars. Explicit no-fabrication rule (`NONE IN SOURCE`).
- `agent-prompts/analysis-agent-prompt.md` — added **Dimension 13 (Playbook Asset
  Inventory & Patternization)**: 13A Asset Coverage Map, 13B Patternized Asset
  Catalog, 13C Full Recipe Set check, 13D Brand-Building Language Bank. Min output
  raised 3,000 → 5,000 chars.
- `agent-prompts/playbook-appendix-prompt.md` — **NEW** Phase 3b prompt; emits the
  8-section (A-H) appendix with the Pattern/Worked-example/Source capture convention
  and explicit per-section floors.
- `agent-prompts/synthesis-agent-prompt.md` — blueprint now cross-references the
  companion appendix instead of summarizing frameworks/scripts/recipes away.
- `pipeline/orchestrator.py` — new `run_playbook_appendix()` (Phase 3b) wired into
  `run_synthesis()` after the blueprint write and before Gemini indexing; new
  `_validate_appendix()` quality-floor gate (`APPENDIX_*` constants), `_appendix_system()`
  prompt loader, and `_appendix_model_call()` router (same chain as Phase 3). Fail-loud
  on the structure/honesty gate (`phase3b: FAILED`), one stricter retry on richness
  shortfall, NO fabrication for thin books (`COMPLETE_WITH_WARNINGS`).
- Docs/QC: `SKILL.md`, `PIPELINE.md`, `CHECKLIST.md`, `QC.md`, and
  `qc-book-to-persona-coaching-leadership-system.sh` updated to document and assert
  the appendix + new floors.

### Quality floor (enforced)
- HARD (fail-loud): file present + non-empty, all 8 sections A-H, Asset Coverage Map
  present, >= 6,000 chars.
- SOFT (warn + one retry): >= 12,000 chars and >= 12 Pattern/Worked-example blocks for
  asset-rich books. Section minimums: A >= 12 formulas, C >= 10 scripts, F >= 15
  brand-voice patterns, G >= 20 swipe items; B = full recipe set; E = full framework set.

---

## [v6.7.13] - 2026-06-26

### Added (book-persona research scaffolding — all 10 QC-approved personas)
Adds `extraction-notes.md`, `analysis-notes.md`, and `source.json` to every one
of the 10 book personas shipped in v14.3.16 and v14.3.18. These files are the
Phase 1 (extraction) and Phase 2 (analysis) research artifacts generated by the
pipeline before the Phase 3 persona-blueprint is assembled.

**Personas receiving research scaffolding:**
- `acuff-miner-new-model-of-selling` (Jerry Acuff & Jeremy Miner) — QC 9.0
- `leland-brand-mapping-strategy` (Karen Tiber Leland) — QC 9.2 + UPDATED persona-blueprint.md (710 lines, rebuilt from full-text; prior 303-line stub replaced)
- `miller-coach-builder` (Donald Miller) — QC 9.0 + UPDATED persona-blueprint.md (711 lines; prior 666-line version replaced with richer extraction)
- `miller-building-storybrand` (Donald Miller) — QC 9.4
- `brunson-marketing-secrets-blackbook` (Russell Brunson) — QC 9.0
- `edwards-copywriting-secrets` (Jim Edwards) — QC 9.0
- `russell-brunson-lead-funnels` (Russell Brunson) — QC 9.2
- `brunson-network-marketing-secrets` (Russell Brunson) — QC 9.0
- `rohde-the-sketchnote-workbook` (Mike Rohde) — QC 9.0
- `russell-brunson-the-funnel-hackers-cookbook` (Russell Brunson) — QC 8.7

### Changed
- `leland-brand-mapping-strategy/persona-blueprint.md`: replaced 303-line draft with the complete 710-line dual-purpose blueprint (Coaching Mode + Task Mode both built; all 14 sections present; seven-element Brand Mapping Process© fully operationalized).
- `miller-coach-builder/persona-blueprint.md`: replaced 666-line version with the complete 711-line extraction including full Task Mode section.

---

## [v6.7.2] - 2026-06-11

### Added (book-persona library)
- **New persona: `hormozi-100m-leads` — Alex Hormozi, $100M Leads** (Acquisition.com
  Volume II). Built from the full book text via the standard 3-phase pipeline and
  matched 1:1 to the `hormozi-100m-offers` persona format:
  - `personas/hormozi-100m-leads/extraction-notes.md` (12 structured extraction items)
  - `personas/hormozi-100m-leads/analysis-notes.md` (8-dimension analysis)
  - `personas/hormozi-100m-leads/persona-blueprint.md` (all 14 sections + self-rating;
    "Engaged Lead Machine Architect" — Core Four, Rule of 100, Lead Getters, CAC/LTGP).
- **`persona-categories.json`**: registered `hormozi-100m-leads`
  (`domain: marketing/sales/strategy-innovation`; `custom: lead-generation, advertising,
  core-four`). Explicitly positioned as the companion volume to `hormozi-100m-offers`
  (offers = "what do I sell?", leads = "who do I sell it to?").

### Embedding wiring (operator index)
- New persona staged in the operator coaching-personas index source dir; embeds
  incrementally via `shared-utils/embedding_engine.py`
  (`gemini-embedding-2-preview` @ 3072 dims). Indexing is content-hash incremental —
  the new persona embeds on the next indexer run (~99 chunks).
  NOTE: at ship time the operator Google API key was returning 429 RESOURCE_EXHAUSTED
  on base model `gemini-embedding-2` (account quota cap), so the live re-index is
  deferred until quota clears / a quota increase is granted — no code change required.

## [v6.6.1] - 2026-06-09

### Fixed (critical — EPUB/MOBI/AZW3 ebook extraction)
- **add-persona-from-source.sh: EPUB/MOBI/AZW3 front-door mis-wire** (primary bug).
  The `book` branch previously ran pdfplumber on every book format, which always
  produced empty or garbage text for non-PDF files.  Fix: PDF still gets inline
  pdfplumber pre-extraction; EPUB/MOBI/AZW3/KFX now skip shell-side pre-extraction
  entirely — `source.json` is written with an empty `text_file` field, which causes
  `run_extraction()` in the orchestrator to skip the `_pre_text_path` shortcut
  (L1010) and fall through to the correct multi-format `extract_book_text()` dispatch
  (ebooklib for EPUB, `mobi` library for MOBI, Calibre `ebook-convert` for
  AZW/AZW3/KFX).  The orchestrator already had this logic; the script was just
  short-circuiting it with a broken pre-extracted file.

### Fixed (minor — generic web URLs)
- **add-persona-from-source.sh: HTTP branch** now supported.  Generic `http(s)://`
  URLs (non-YouTube) are fetched via `curl` and HTML is parsed to readable text via
  BeautifulSoup (`<article>` / `<main>` / `<body>` extraction with script/style/nav
  stripped).  Previously the HTTP branch exited with an error telling users to
  "download the page manually".

### Fixed (minor — new personas invisible to dept selector)
- **add-persona-from-source.sh: auto-classification** of `domain[]` and
  `perspective[]` tags.  New personas were written to `persona-categories.json`
  with empty `domain[]`/`perspective[]` arrays, making them invisible to
  `write_governing_personas_md`'s dept-scope filter until hand-tagged.  The update
  section now performs keyword-based classification against the canonical tag
  taxonomy (12 domain tags, 6 perspective tags) using title+author+slug as the
  probe string.  No LLM or API call — pure keyword matching, instant, free.  Falls
  back to `["coaching"]` / `[]` if nothing matches.  Existing entries with empty
  `domain[]` are also backfilled on first run.

### Changed
- Script version bumped to v10.14.33 (header + banner).
- `unknown/missing` error message now lists generic web URLs as a supported type.
- Closing `NEXT STEP` note updated: auto-classification handles initial tagging;
  user only needs to review/refine rather than fill from scratch.
- SKILL.md `When To Use This Skill` and `Supported Input Formats` updated to
  include generic web URL as a first-class supported source type.

## [v6.6.0] - 2026-06-09

### Fixed (critical — new sources never processed)
- **orchestrator.py: argparse + `--single-book --slug SLUG`** (#1 fix). Builds a
  one-element BOOKS entry from the slug's `source.json` marker and runs ONLY that
  folder through phases 1-3. Without this, every source added via
  `add-persona-from-source.sh` silently never processed (slug not in hardcoded list).
- **Path unification**: `BASE`/`BOOKS_DIR`/`PERSONAS_DIR` in orchestrator.py and
  `PERSONAS_DIR` in gemini-indexer.py now resolve to ONE canonical root:
  VPS→`/data/.openclaw/master-files/coaching-personas`,
  Mac→`~/.openclaw/workspace/data/coaching-personas`. Eliminates the 3-divergent-roots
  bug where script-write ≠ orchestrator-read ≠ indexer-scan.
- **Pre-extracted text consumption**: `run_extraction` checks for pre-extracted
  `text/<slug>.txt` BEFORE attempting book file extraction, so YouTube/video/text
  sources written by `add-persona-from-source.sh` don't re-invoke whisper.
- **Duplicate `import subprocess`** removed (was shadowing the top-level import).
- **`load_status()` JSON parse hardened** (try/except + mkdir parents).
- **Lazy prompt loading**: prompts loaded on first use, not at import time, so
  `--single-book` doesn't crash when the agent-prompts dir is temporarily missing.
- **SKILL.md stale claims fixed**: YouTube now documents yt-dlp (not Skill 16);
  auto-tagging claim replaced with accurate "tags are stubs, fill manually" message.

### Fixed (schema — personas invisible to dept filter)
- **add-persona-from-source.sh schema fix**: writes `domain`/`perspective`/`custom`
  (canonical fields) instead of `domain_tags`/`perspective_tags`. Also migrates
  existing entries with old field names on first run. Without this fix, all
  script-added personas were invisible to the `write_governing_personas_md` dept filter.

### Added
- **`scripts/persona-inbox-watcher.sh`**: cron-driven (*/10) inbox scanner. Drop any
  supported file into `coaching-personas/inbox/` and it auto-converts to a persona via
  `add-persona-from-source.sh`. TOKEN-SAFE: `MAX_PER_RUN=5` cap, lock files, stale-lock
  reaping (2h TTL), self-disables if orchestrator missing. Cron installed by install.sh
  with dedupe guard.
- **install.sh Step 6.4**: explicit Skill 22 Python deps install
  (pdfplumber, pypdf, ebooklib, lxml, mobi, beautifulsoup4, aiohttp, numpy) with
  per-package verification and LOUD warn on failure. Three-tier install order:
  uv → pip3 --break-system-packages → Linuxbrew python3.
- **install.sh Calibre headless fix**: dropped `--no-install-recommends` and added
  `libegl1 libopengl0 libxcb-cursor0 xvfb` to the apt install. Validates with
  `xvfb-run -a ebook-convert --version`. Falls back to upstream isolated installer
  (`download.calibre-ebook.com/linux-installer.sh isolated=y`) on apt failure.
- **create_role_workspaces.py `--refresh-personas-only`**: re-writes `governing-personas.md`
  for every dept folder cheaply (no LLM, idempotent). Called automatically by
  orchestrator.py Phase 6b after each new persona is appended to
  `persona-categories.json`, so the dashboard auto-updates.
- **orchestrator.py Phase 6b**: invokes `create_role_workspaces.py --refresh-personas-only`
  after each successful Phase 3 so `governing-personas.md` is always current.
- **`_append_persona_to_categories`** now writes canonical `domain`/`perspective`/`custom`
  fields (aligned with `write_governing_personas_md` reader).

### Changed
- `_persona_categories_path()` now checks the unified canonical path first (VPS + Mac).
- SKILL.md: next-step message updated to reference `domain[]`/`perspective[]` arrays.
- `add-persona-from-source.sh` book extraction label updated (pdfplumber/ebooklib/Calibre).
- orchestrator.py `PROMPTS_DIR` now searches skill folder `agent-prompts/` first.
- orchestrator.py `STATUS_FILE` and `LOG_FILE` now live in `BASE` (the canonical
  coaching-personas root) rather than `~/clawd/projects/coaching-personas-matrix`.

---

## [v1.5.0] - March 7, 2026

### Changed
- Converted INSTALL.md to agent-executable, autonomous execution format.
- Ensured TYP guardrails are present: MANDATORY TYP CHECK, CONFLICT RULE, and TYP file storage instructions.
- Fixed duplicate step numbering and added a pipeline execution test step to validate Phase 1, Phase 2, Phase 3 readiness.

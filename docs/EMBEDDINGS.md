# EMBEDDINGS — the single source of truth

How every corpus in this repo is embedded, matched, verified, and shipped.
If a build, agent, or script touches embeddings and disagrees with this page,
the build is wrong. CI enforces the invariants below
(`.github/workflows/embedding-integrity-guard.yml`).

## The six corpora

**P4-03 (2026-07-12) ground truth:** there are TWO entirely separate embedding
SYSTEMS on two different stacks, not connected to each other. System 1
(corpora 1–2, Python, this repo) is the mature "embed once, push to clients"
pipeline. System 2 (corpora 5–6, TypeScript, the Command Center repo) was
**broken as a fleet pipeline** before P4-03 — every client box burned its OWN
key re-embedding an IDENTICAL shared SOP library, the table was never wired
into install at all, and two health surfaces (`embedding_health.py` here vs.
`heartbeat-canary-probe.py` in the CC repo) disagreed about the SAME box
state. P4-03 closes the gap: corpus 5 now has its own embed-once pipeline
mirroring corpus 1's, and corpus 6's per-department vectors are cached
instead of re-embedded on every dispatch. See
`shared-utils/sop-embed-once/` for the implementation and
`SECTION 6 / P4-03` of the 2026-07-11 spec for the full root-cause writeup.

| # | Corpus | Retrieval model | Store | Integrity gate |
|---|--------|-----------------|-------|----------------|
| 1 | Coaching personas (Skill 22 blueprints) | Gemini vectors, section-level | `workspace/data/coaching-personas/gemini-index.sqlite` | real-vector hard gate + `--verify` + count triad |
| 2 | Persona matching at runtime | cosine over corpus 1 + category/keyword ladder | same DB + `persona-categories.json` | provider/model row filter + dim guard + keyword fallback |
| 3 | Role library (426 roles) | deterministic `_index.json` lookup — **no embeddings by design** | `23-ai-workforce-blueprint/templates/role-library/_index.json` | `content_sha` (CONTENT-HASH) via `hash-content-manifest.py`, CI `library-lockstep` |
| 4 | SOP libraries (content) | deterministic — **no embeddings by design** | dept SOPs: `_index.json sops[]` (131) · craft clusters: `universal-sops/` | dept SOPs: CONTENT-HASH · universal-sops: `_content-manifest.json` via `scripts/hash-universal-sops-manifest.py` |
| 5 | **CC SOP / routing embeddings** (System 2, TypeScript) | Gemini vectors, one row per SOP | Command Center `mission-control.db` → `sop_embeddings` (migration 057) | real-vector hard gate (`embed_sop_library.py --verify`) + sha256 asset gate + dual-surface row-count reconciliation |
| 6 | **Department-router semantic vectors** (System 2, TypeScript) | Gemini/OpenAI vectors, one row per department, in-memory cache | `department-router.ts` in-process cache (not persisted) | content-hash cache key (`name+purpose+keywords`), invalidated on department edit |

## Non-negotiable invariants (EMBED-1..9)

1. **ONE DB path (EMBED-1).** The persona index is
   `<workspace>/data/coaching-personas/gemini-index.sqlite` — the file
   `embedding_engine.DB_PATH` reads, `provision-persona-index.sh` installs, and
   `detect_platform paths["gemini_index"]` resolves (both copies:
   `shared-utils/detect_platform.py` and `23-ai-workforce-blueprint/lib/detect_platform.py`).
   Historical defect: `paths["gemini_index"]` pointed at
   `workspace/data/gemini-index.sqlite`, so the section indexer wrote to a DB
   the search path never read. If that orphan file exists on a box, its rows
   are invisible — converge (re-embed or install the current prebuilt asset)
   and delete it. The indexer warns when it sees the orphan.
2. **Sandbox is explicit (EMBED-2).** All paths are HOME-relative on Mac, so a
   faked `$HOME` silently redirects reads AND writes. Writers targeting the
   default live DB call `detect_platform.assert_live_workspace_for_write()`:
   overridden `$HOME` without `OPENCLAW_SANDBOX=1` → exit 4. Tests sandbox ON
   PURPOSE with `OPENCLAW_SANDBOX=1` (and preferably explicit `--db`).
3. **Real vectors or fail loud (EMBED-3).** The pinned contract is
   `gemini-embedding-2` @ **3072-dim float32** (`GEMINI_MODEL` /
   `GEMINI_OUTPUT_DIM` in `shared-utils/embedding_engine.py` — the ONLY place
   the model is named). A missing GOOGLE_API_KEY/GEMINI_API_KEY (checked
   against ALL canonical secret stores, never just process env) aborts the
   run non-zero. Nothing may ever silently persist a fake/hash-derived vector:
   the old `gemini-section-indexer.py` fallback that wrote fake 768-dim
   vectors stamped `gemini/3072` is deleted. Fake vectors exist ONLY behind
   `--allow-fake-embeddings` + explicit `--db`, stamped truthfully
   `provider='fake' model='deterministic-hash-768' dim=768`.
   Machine check: `python3 shared-utils/embedding_engine.py --verify [--db X]`
   → rc 0 pass / rc 4 fail (every row must be gemini/3072 with blob length
   dim*4).
4. **Converge-aware chunk indexer (EMBED-4).** The canonical index is
   section-level. `cmd_index` (chunk indexer) skips any file whose md5 already
   exists as a section row — no accidental full re-embed, no mixed units.
5. **Section indexer is the build path (EMBED-5).** Skill-22 orchestrator
   Phase 5 prefers `23-ai-workforce-blueprint/scripts/gemini-section-indexer.py
   --persona-id <slug>`; the chunk wrapper is fallback only. Phase 5 is
   fail-loud for a GENUINE indexing bug (non-zero exit outside the
   credential family, or wrapper-not-found ⇒ `FAILED` in
   pipeline-status.json, never "Re-indexing complete", `EMBED_FAILED` exit
   8 end-to-end). See EMBED-9 for the ONE deliberate non-fatal exception
   (a missing/invalid key).
6. **Publishing is hermetic (EMBED-6).** `shared-utils/prebuilt-index/
   build-and-publish.sh` stages base asset + repo blueprints in a temp dir —
   it never touches a live workspace. Refuses to publish unless: base sha256
   matches, count triad agrees (blueprint dirs == categories keys == embedded
   personas), and EVERY row passes the real-vector gate.
7. **Selector never scores foreign vectors (EMBED-7).**
   `semantic_task_fit.py` excludes rows whose provider/model is definitely not
   the current gemini model (fake rows, stale slugs, openai rows) and never
   cosine-compares mismatched dimensions.
8. **Health checks the real DB (EMBED-8).** `embedding_health.py` leg-b reads
   provider/model/dim from the actual embeddings table (and flags rows whose
   blob length disagrees with the stamped dim = fake/corrupt).
9. **A missing/invalid key is DEFERRED, never a blocked persona (EMBED-9,
   A-U8).** `gemini-section-indexer.py` returns exit 4 for BOTH the upfront
   "no usable Gemini embedder" preflight refusal AND a mid-run
   credential-shaped exception (`embedding_engine.is_credential_error()` —
   401/403/permission/API-key-rejected); any OTHER mid-run exception returns
   exit 6 (still fail-loud — EMBED-3/EMBED-5 unchanged). Orchestrator Phase 5
   classifies exit 4 as `DEFERRED` (`classify_phase5_result`): it writes an
   honest `personas/<slug>/embedding-receipt.json`
   (`{"status":"deferred","reason":"embedding: deferred (no key / key
   invalid)", ...}`), does NOT propagate `EMBED_FAILED`, and the blueprint
   ships as-is — the pipeline's re-embed-only re-entry retries automatically
   on the next run once a key resolves. This is the client's OWN key per
   standing doctrine (the operator never substitutes keys) — a client box
   without one yet is an expected, honest state, not a defect. Two
   consumers close the loop so a deferred persona is never a silent hole:
   `persona_fleet.py index-verify` (wired into
   `publish-personas-to-fleet.sh` step 1.5, exit 7) requires every
   publishable persona be EITHER indexed OR carry a `status:"deferred"`
   receipt before the fleet asset ships; and
   `shared-utils/persona_embedding_drift_probe.py` (wired into
   `fleet_refresh_runner.py` as a NON-GATING advisory, alongside
   `embedding_health.py`) compares `personas/` on disk vs. the index vs.
   receipts on the operator's own box and flags an UNEXPLAINED gap (never a
   receipted deferral) as one advisory record per run.

## Corpus 1 — coaching personas: build → embed → register → ship

- **Build**: Skill 22 orchestrator (`22-…/pipeline/orchestrator.py`) writes
  `personas/<slug>/persona-blueprint.md` under
  `<workspace>/data/coaching-personas/`.
- **Embed (Phase 5)**: section indexer per persona (EMBED-5). One row per
  `## Section N`; `mode` from `embedding_engine.{COACHING,LEADERSHIP}_SECTION_NUMBER`
  (3=coaching, 4=leadership); md5 HASH-SKIP prevents re-embedding unchanged
  blueprints; provider/model/dim stamped on every row; post-write verification
  aborts on any contract violation. A missing/invalid key `DEFERS` rather
  than blocking the persona — see EMBED-9.
- **Register (Phase 6)**: `_append_persona_to_categories()` updates the
  canonical `persona-categories.json`
  (`<workspace>/data/coaching-personas/persona-categories.json`; the skill
  copy is a read-only shipped seed). A persona in the index but not in
  categories is silently under-selected at Stage B — registration is NOT
  optional.
- **Ship fleet-wide**: clients NEVER re-embed. They pull the prebuilt asset
  (GitHub Release `gemini-index.sqlite.gz`, manifest
  `shared-utils/prebuilt-index/INDEX-MANIFEST.json`) via
  `provision-persona-index.sh` (sha256 hard gate, idempotency on
  chunk-count + persona-dir count + `.prebuilt-index-version` sentinel).

### Landing a delta (N new personas) — the canonical runbook

1. Finish the builds; confirm live embed + registration (Phase 5/6 logs, or
   `python3 shared-utils/embedding_engine.py --verify` + `--status`). If any
   persona's Phase 5 reads `DEFERRED` (no key yet — check
   `personas/<slug>/embedding-receipt.json`), resolve the key and re-run the
   pipeline (idempotent re-embed-only re-entry) BEFORE step 4 —
   `persona_fleet.py index-verify` (step 4b below) will otherwise refuse.
2. Add to the REPO: blueprint dirs under
   `22-book-to-persona-coaching-leadership-system/personas/` + matching keys
   in `22-…/persona-categories.json` (count triad: dirs == keys).
3. Re-stamp content manifests: `python3
   23-ai-workforce-blueprint/scripts/hash-content-manifest.py` (personas carry
   content_sha in `_index.json`).
4. Publish: `shared-utils/prebuilt-index/build-and-publish.sh
   [--persona-id <slug> …]` with the Gemini key SET. It downloads the current
   asset, embeds ONLY the delta, enforces the real-vector gate + triad, bumps
   the manifest, uploads the new release tag.
5. Update `tests/unit/prebuilt-index-section-tagged.test.sh` (KNOWN_TAGS +
   persona/chunk counts) to the new canon; commit manifest + test together.
6. Fleet + operator boxes converge on next install/update run (sentinel and
   chunk-count mismatch trigger the re-download). NOTE: a local index that is
   AHEAD of the published asset gets clobbered back by the provision gate —
   publish the delta asset BEFORE running install/update on the box that
   built it.

## Corpus 2 — persona matching at runtime

- **CLI / reflex search**: `gemini-search.py` (3 identical wrappers →
  `embedding_engine.search()`); `--mode leadership` = Section 4 rows,
  `--mode coaching` = Section 3; same-provider query embedding enforced;
  stale/mixed/keyless index ⇒ LOUD keyword fallback, never cross-model cosine.
- **Selector**: `persona-selector-v2.py` Stage C uses
  `shared-utils/semantic_task_fit.py` (`semantic_persona_ids`, Layer-5 task
  fit) against the same DB, with the EMBED-7 row filter; falls back to
  keyword overlap, then neutral 0.6.
- **Categories**: `persona-categories.json` drives Stage B domain filtering
  and specialist recall. Keep index personas ⟷ categories keys in lockstep
  (the count triad + `.persona-set-version` re-wire cascade cover this at
  install/update time).

## Corpus 3 — role library (no embeddings BY DESIGN)

426 roles under `templates/role-library/`, matched deterministically:
`create_role_workspaces.py::library_lookup` (normalized title/slug variant
keys, dept-scoped) — never semantic. Integrity: `content_sha` per role/dept in
`_index.json`, stamped by `hash-content-manifest.py`; edits without a re-stamp
fail `check_manifest` (CI `library-lockstep`, repo gate
`qc-assert-repo-consistency.py` rc 6). Do not add an embedding index here
without updating this page and the gates.

## Corpus 4 — SOP libraries (no embeddings BY DESIGN)

Two DIFFERENT things — never conflate the counts:
- **Dept SOPs (131)**: `templates/role-library/<dept>/sops/*.md`, covered by
  `_index.json sops[]` + CONTENT-HASH (same pipeline as roles).
- **universal-sops craft clusters**: routed by content
  (`how_to_use_department.py`, routing docs), integrity-covered by
  `universal-sops/_content-manifest.json` — regenerate with
  `python3 scripts/hash-universal-sops-manifest.py` after ANY edit
  (`--check` runs in CI).
- Workspace nav tables (`departments/<dept>/SOP/00-INDEX.md`) are regenerated
  by `regenerate-sop-index.py` on the installed box; the Command Center
  ingests raw markdown directly.

## Corpus 5 — CC SOP / routing embeddings (System 2, TypeScript, mission-control.db)

**Who embeds, who pays:** the OPERATOR embeds the canonical shared SOP
library (`sops.jsonl`, the SAME content `ingest-sop-library.py` loads into
every client's `sops` table) ONCE, mirroring corpus 1. Clients spend their own
key ONLY on genuinely client-specific content — custom SOPs from
`sop_proposals` that are NOT covered by the shipped asset — via
`scripts/backfill-sop-embeddings.ts` (CC repo) in delta-only mode.

- **Build (operator box only)**: `shared-utils/sop-embed-once/build-and-publish.sh`
  — mirrors `shared-utils/prebuilt-index/build-and-publish.sh` field-for-field:
  hermetic staging dir, HASH-SKIP incremental embed
  (`shared-utils/sop-embed-once/embed_sop_library.py`, md5 of the SAME
  title+description+keywords+first-8-steps text shape as
  `sop-embeddings.ts::buildSOPEmbedText()` in the CC repo — kept in lockstep
  by hand, not by import, since it is a cross-language/cross-repo pair),
  REAL-VECTOR HARD GATE (`--verify`, gemini-embedding-2 @3072 float32, refuses
  to publish a short/wrong-dim row), sha256 + row-count triad, GitHub Release
  asset (`sop-embeddings.sqlite.gz`) + manifest
  (`shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json` — `sop_count`,
  `chunk_count`, `sha256`, `embedding_model`, `dims`, `release_tag`, the direct
  analog of `INDEX-MANIFEST.json`).
- **Ship (every client box, install + every Sunday update)**:
  `32-command-center-setup/scripts/ingest-sop-library.sh` calls
  `shared-utils/sop-embed-once/provision_sop_embeddings.py` immediately after
  the SOP content ingest — sha256-verified download, idempotency gate (marker
  table `sop_embeddings_shipped_asset`: release_tag + row count), scoped
  `INSERT OR REPLACE` restricted to `sop_id`s the box's own `sops` table
  actually has, ZERO embedding API calls. A box with no published asset yet
  (`asset_rebuild_required:true` in the seed manifest) additively no-ops —
  never blocks install/update.
- **Client-delta only**: `scripts/backfill-sop-embeddings.ts` (CC repo) is
  incremental — it already skips any `sop_id` with a row for the active
  model, so shared-library rows imported by provisioning are never re-embedded
  UNLESS `--force` is passed. `--force` REFUSES a full re-embed when the
  `sop_embeddings_shipped_asset` marker table is present, mirroring
  `embedding_engine._refuse_full_rebuild_if_prebuilt` — the operator-only
  override for a genuine embedding-model migration.
- **Health**: TWO surfaces read the SAME ground truth and must never
  disagree — `shared-utils/embedding_health.py::check_cc_sop_index` (leg-b
  now reads REAL row counts via `_read_cc_sop_row_counts`, not a stamp table
  CC's migrations never create) and the CC repo's own
  `32-command-center-setup/scripts/heartbeat-canary-probe.py` (row-count/
  coverage gate, cron'd every 6h). See `tests/unit/embedding-health-cc-sop-reconciliation.test.py`.
- **Standing guard (EMBED-3/EMBED-8 analog)**: the client-box import path
  asserts `embedding_model`+`dims` match between the shipped asset and the
  manifest's declared contract BEFORE importing a single row — refuses to
  mix vector spaces (a 1536-dim OpenAI row can never land next to a
  3072-dim Gemini row for the same corpus).

## Corpus 6 — department-router semantic vectors (System 2, TypeScript, in-memory)

`department-router.ts::semanticRankDepartments()` embeds the LIVE task text on
every `comDispatch()` call (unavoidable — the task text is dynamic) but, as of
P4-03, embeds each department's `deptEmbedText()` (`name + purpose +
keywords`) vector ONCE per department-config version — not on every call. The
cache key is a content hash of that same text; an operator editing a
department's name/purpose/keywords changes the hash and naturally invalidates
the stale cached vector on the next dispatch (no explicit version field
needed). Effect: an N-department fleet drops from N+1 embed calls per
dispatch (1 task + N departments) to 1 (task only) — the department vectors
are computed once and reused until the department config changes.

This corpus is deliberately NOT persisted to `mission-control.db` — it is a
per-process cache, cheap to rebuild on restart, and never shipped as a
GitHub Release asset (department configs are per-client, not a shared
library).

## Provider reliability (build pipeline)

- Keys are read from ALL canonical secret stores and DEQUOTED
  (`KEY="…"` tolerated) — `orchestrator.get_keys()`,
  `embedding_engine._read_secret()`.
- Ollama→OpenRouter fallback converts model ids through
  `orchestrator._openrouter_fallback_model()` (vendor inserted, route prefix
  stripped: `ollama/deepseek-v4-pro:cloud` → `deepseek/deepseek-v4-pro`).
  Never hand `openrouter/…`-prefixed ids to the OpenRouter API.

## Quick reference — commands

```bash
# Verify an index (rc 0 pass / 4 fail):
python3 shared-utils/embedding_engine.py --verify [--db /path/to.sqlite]
# Status (counts, provider, embedder readiness):
python3 shared-utils/embedding_engine.py --status
# Embed one persona into the LIVE index (real HOME, key set):
python3 23-ai-workforce-blueprint/scripts/gemini-section-indexer.py --persona-id <slug>
# Sandbox/test run (explicit, never touches live):
OPENCLAW_SANDBOX=1 python3 …/gemini-section-indexer.py --db /tmp/x.sqlite --personas-root /tmp/personas [--allow-fake-embeddings]
# Publish a delta asset:
shared-utils/prebuilt-index/build-and-publish.sh --persona-id <slug>
# SOP integrity:
python3 scripts/hash-universal-sops-manifest.py --check
python3 23-ai-workforce-blueprint/scripts/hash-content-manifest.py --check

# Corpus 5 (CC SOP embeddings) — verify a staged/published asset (rc 0 pass / 4 fail):
python3 shared-utils/sop-embed-once/embed_sop_library.py --db /path/to/sop-embeddings.sqlite --verify
# Publish a delta asset (operator box only, needs a Gemini key):
shared-utils/sop-embed-once/build-and-publish.sh
# Dry-run (no key needed, proves the count/manifest math only):
shared-utils/sop-embed-once/build-and-publish.sh --dry-run
# Provision the shipped asset into a client's mission-control.db (normally
# called automatically by ingest-sop-library.sh):
python3 shared-utils/sop-embed-once/provision_sop_embeddings.py \
  shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json /path/to/mission-control.db
```

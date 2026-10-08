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
`heartbeat-embedding-probe.py` in the CC repo) disagreed about the SAME box
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
| 4 | SOP libraries (content) | deterministic — **no embeddings by design** | dept SOPs: `_index.json sops[]` (145) · craft clusters: `universal-sops/` | dept SOPs: CONTENT-HASH · universal-sops: `_content-manifest.json` via `scripts/hash-universal-sops-manifest.py` |
| 5 | **CC SOP / routing embeddings** (System 2, TypeScript) | Gemini vectors, one row per SOP | Command Center `mission-control.db` → `sop_embeddings` (migration 057); shipped asset also carries `role_library_embeddings` (by slug) | real-vector hard gate (`embed_sop_library.py --verify`, both tables) + sha256 asset gate + dual-surface row-count reconciliation |
| 6 | **Department-router semantic vectors** (System 2, TypeScript) | Gemini/OpenAI vectors (local Ollama on a local-mode box), one row per department, in-memory cache | `department-router.ts` in-process cache (not persisted) | content-hash cache key (`name+purpose+keywords`), invalidated on department edit |

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
   dim*4). The ONE other contract is the explicit local Ollama opt-in (see
   "Local Ollama mode" below): `--verify --verify-provider ollama` holds such an
   index to `ollama/$OLLAMA_EMBED_MODEL` @ `$OLLAMA_EMBED_DIM` (default
   `embeddinggemma-2:740m` @ 768). It is never selected automatically.
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
   cosine-compares mismatched dimensions. On a local-mode box it scores only
   rows on the index's own ollama model.
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
  keyword overlap, then neutral 0.6. On a local-mode box it embeds the task
  with the local Ollama model (see "Local Ollama mode").
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

The role *lookup* above stays deterministic. Separately, the Command Center
imports each role's how-to.md as a `sops` row (`importRoleLibrary()`, slug
`role-library:<dept>/<role>`, no per-box embed). Those rows get their vectors
from the central Corpus 5 asset: `role_library_vectors.py` renders every role
through the same `fill_tokens()` a box uses (neutral values), parses it exactly
as the CC does, and ships one vector per role-folder slug a box build is known
to use (`role_library_embeddings`); `provision_sop_embeddings.py` maps them onto
the box's rows by exact slug.

## Corpus 4 — SOP libraries (no embeddings BY DESIGN)

Two DIFFERENT things — never conflate the counts:
- **Dept SOPs (145)**: `templates/role-library/<dept>/sops/*.md`, covered by
  `_index.json sops[]` + CONTENT-HASH (same pipeline as roles). Since
  `sop-library-v3.0.0` each one also ships as a row of the Command Center SOP
  library (built by `shared-utils/sop-library/build_sop_library.py`), so its
  vector comes from the central Corpus 5 asset -- never a per-box embed.
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
  `32-command-center-setup/scripts/heartbeat-embedding-probe.py` (row-count/
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

On a local-mode Command Center (`SOP_EMBEDDING_PROVIDER=ollama`) the router
embeds with the CC's local model (`SOP_EMBEDDING_MODEL`) through the same
`fetchEmbeddings()` and caches the vectors the same way. The context-pack
skill matcher does the same. See "Local Ollama mode" below.

## Local Ollama mode (explicit per-box opt-in, corpora 1–2, 5 and 6)

For a box whose Gemini key cannot pay (e.g. HTTP 402), both searches can run on
the box's own local Ollama (default `embeddinggemma-2:740m` @ 768, free, no key).
Nothing selects it automatically. A box stays on Gemini until an operator
switches it.

The persona engine's local model is set per box by two keys. The process
environment wins; otherwise they are read from the box's `secrets/.env` (or the
`openclaw.json` `env` block), so a fresh shell, cron run, or agent `exec` uses
the same model:

| Key | Default | Meaning |
|---|---|---|
| `OLLAMA_EMBED_MODEL` | `embeddinggemma-2:740m` | Ollama model for `--reembed-local`, the rows' `model` stamp, and `--verify --verify-provider ollama`. |
| `OLLAMA_EMBED_DIM` | `768` | Vector width every local embed and the verify contract must match. |

`embeddinggemma-2:740m` @ 768 is the only supported local model. The override
keys exist for testing a replacement model. The model must be pulled into the
local Ollama first (`ollama pull <model>`).
`embeddinggemma*` models get their model-card task prefixes
(`task: search result | query: …` for queries, `title: none | text: …` for
documents). Other models get the raw text. Query-time `search()` always embeds
with the model the index is stamped with, so a later env change cannot produce
cross-model scores. To switch models, set the keys and re-run `--reembed-local`.
It re-embeds every row not already on the new model. An index stamped with any
other local model fails `--verify --verify-provider ollama` (rc 4) with a hint
to re-embed with `--reembed-local`, and `search()` prints the same warning. While a re-embed is partial, the index is
mixed-model: verify fails and `search()` uses keyword mode.

- **CC SOP index (corpus 5)**: in the Command Center's `.env.local` set
  `SOP_EMBEDDING_PROVIDER=ollama` (optionally `SOP_EMBEDDING_OLLAMA_URL`,
  `SOP_EMBEDDING_MODEL`, `SOP_EMBEDDING_DIMS`), restart the CC, then run
  `tsx scripts/backfill-sop-embeddings.ts --batch-size=10`. The backfill stamps the
  `sop_embeddings_local_provider` marker table before it writes a row.
  `provision_sop_embeddings.py` SKIPs any DB carrying that marker, so the Sunday
  update never re-imports the Gemini asset over local vectors.
- **Persona index (corpora 1–2)**: `python3 shared-utils/embedding_engine.py
  --reembed-local [--batch-size N --pause S]` re-embeds every existing row in
  place (ids and section metadata kept), stamped `provider='ollama'`. It is
  resumable and ends with the ollama `--verify`. `search()` then embeds queries
  with the same local model (`OLLAMA_EMBED_URL`, default
  `http://127.0.0.1:11434`). If Ollama is down, it embeds the query with Gemini
  on the box's own key and ranks it against the Gemini fallback copy (see
  "Gemini fallback while Ollama is down"), and only then falls back to keyword.
  `provision-persona-index.sh` keeps an index that has `provider='ollama'` rows
  and never installs the Gemini asset over it.
- **Persona selector Layer-5 and Stage C** (`semantic_task_fit.py`): a box
  is in local mode when its persona index carries `provider='ollama'` rows,
  which only `--reembed-local` writes. That is the same check `search()` uses.
  The task is embedded once per selection through
  `embedding_engine._ollama_embed` with the model the index is stamped with
  (query prefix for embeddinggemma). It is scored only against rows on that
  model, with method `ollama_embedding`. A local-mode box does not call Gemini
  while its Ollama answers. If Ollama is down, the selector logs one line, then
  uses the Gemini fallback copy (next section) for the rest of that process,
  with method `gemini_embedding` and `db=gemini-fallback-index.sqlite` in the
  detail. A mixed-model index (partial re-embed) uses keyword overlap.
- **CC department router and skill matcher** (corpus 6 and the context-pack
  skill match): with `SOP_EMBEDDING_PROVIDER=ollama` both embed with the CC's
  `SOP_EMBEDDING_MODEL` at `SOP_EMBEDDING_OLLAMA_URL`. Set the model to
  `embeddinggemma-2:740m` on a local box. With an embeddinggemma model the task
  gets `task: search result | query: …` and the department or skill text gets
  `title: none | text: …`. If Ollama is down, the router logs one line and the
  next picker decides (decision engine, then keyword). The skill matcher uses
  keyword scoring. Neither ever calls Gemini or OpenAI in this mode. The SOP
  index itself (corpus 5) is still embedded raw, without prefixes.
- **Health**: `embedding_health.py` checks a local-mode store against its own
  model and dims, with a smoke embed to the loopback Ollama. A non-loopback URL
  fails, because Ollama Cloud never embeds (B.6).
- **Gemini fallback while Ollama is down**: see the next section.
- **Known limits**: personas added by a newer prebuilt asset do not reach a
  local-mode box until an operator moves the index aside, re-provisions, and
  re-runs `--reembed-local`.
- **Leaving local mode**: drop the CC marker table, set
  `SOP_EMBEDDING_PROVIDER=google`, and re-provision. For personas, move
  `gemini-index.sqlite` aside and re-provision.

### Gemini fallback while Ollama is down (persona selection and the CC SOP vote)

Trevor's rule: a local-mode box whose Ollama is down uses paid Gemini on the
box's OWN Google key for persona selection, and falls to keyword only if Gemini
also fails or the box has no key. Each client Mac uses its own key. An operator
key or another client's key is never used.

- **The copy**: a local index (768-dim `ollama` rows) cannot be compared with a
  Gemini query vector, so the shared Gemini persona set (the prebuilt index
  release asset, `INDEX-MANIFEST.json`) is installed as a SEPARATE file,
  `gemini-fallback-index.sqlite`, next to `gemini-index.sqlite`.
  `provision_gemini_fallback_index` in `provision-persona-index.sh` downloads it
  with the same sha256 gate, skips when `.gemini-fallback-index-version` equals
  the manifest `release_tag`, and never touches the live index. `--reembed-local`
  and the indexer never write the copy. Skill 76 (`wire.sh`, step 5b) provisions
  it on client Macs that have their own Google key and skips cleanly otherwise.
  It leaves `memory.search.fallback` alone.
- **Order** (`embedding_engine.search()` and `semantic_task_fit.py`, which is
  vendored byte-identically into the Presentations persona service):
  local Ollama, then (on an Ollama failure) a Gemini query embedding against the
  fallback copy, then keyword. The vector space always matches the rows it is
  compared with: a Gemini vector is never scored against local rows, and a local
  vector never against the copy. No key, no copy, or any Gemini error or timeout
  (30 s) gives keyword with one log line.
  On this fallback path only, the box's own key is looked up where
  `embedding_health.py` looks: env, `~/.openclaw/.env`, `~/.openclaw/secrets/.env`,
  `openclaw.json` `env.vars` / `env`, and `models.providers.google.apiKey`
  (`embedding_engine.fallback_google_key`). The normal Gemini-box lookup is unchanged.
- **Latching**: in the selector, the first Ollama failure moves the rest of that
  process to the fallback, and the first Gemini failure moves it to keyword.
  After a 60 s cooldown (`SEMANTIC_TASK_FIT_LOCAL_RETRY_SECS`) the next embed
  re-probes local Ollama, so a long-lived process returns to the free local
  model once it is back (a still-dead Ollama just re-latches). The next process
  tries local Ollama first again. `search()` is one process per
  query, so it simply tries local first each time.
- **SOP vote (CC v7.6.108+)**: the Command Center's SOP vote falls back the same
  way, against table `sop_embeddings_gemini_fallback` (never `sop_embeddings`,
  the local 768-dim table). Skill 76 (`wire.sh`, step 5c) runs the CC's
  `scripts/provision-gemini-fallback-sop-set.ts` from the box's CC dir with
  `--manifest shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json --db <the
  resolved mission-control.db>`. It downloads the sha256-pinned shared asset and
  maps it onto the box's `sops` (zero embedding API calls, so the box's key is
  only needed at query time; the step is still skipped without a key). Node is
  one that loads better-sqlite3 (the CC's serving process, then Homebrew node
  22/20, then PATH, because an nvm Node 24 fails it). Skipped on no key, no CC,
  or CC older than 7.6.108. Bounded at 600 s, never fatal, and re-run only when
  the manifest sha256 or the box's `sops` count changes
  (`~/.openclaw/local-embedder/gemini-sop-fallback.done`). update-skills.sh also
  calls `wire.sh --sop-fallback-only` right after the Command Center refresh, so a
  CC that reaches 7.6.108 later in the same roll is provisioned in that roll.
- **Per-agent multimodal and re-index retries (skill 76 v1.3.0)**: an agent that
  inherits the local provider but has `memory.search.multimodal.enabled=true` is
  set to false in the same atomic write (local text embedder, no multimodal
  adapter); agents with their own provider are reported and untouched. A
  transient SQLite re-index error is retried 2 more times with a backoff.
- **Health**: `embedding_health.py` reports `gemini_fallback_copy_present` and
  `gemini_fallback_key_present` (names only, never the key) for a local-mode
  persona index. They are informational and do not change pass or fail.

## Runtime decision-engine retrieval (JEV 1.1, Python, this repo)

The decision engine consumes embeddings; it never owns them. Two additive
modules under `shared-utils/decision_engine/retrieval/` carry the spec-9
rules. Both are stdlib-only, perform **zero embedding calls and zero
network/provider access**, and take every provider/model/dimension fact from
the caller — so they add no second embedding path.

- `cache_identity.py` (spec 9.3/9.5/9.6) — the JEV cache-identity table (spec 9.5)
  as code. Every 9.5 purpose has its own key builder
  (`shared_doc_key`, `department_key`, `query_key`,
  `alignment_evidence_key`, `same_task_decision_key`, `provider_health_key`);
  keys are namespace-versioned (`jev1`/`v1`) and content-hashed, never
  positional. `spaces_compatible`/`require_compatible` refuse cross-space
  reuse (model, dimensions, task type, preprocessing version), and
  `validate_vector` rejects fake/corrupt/wrong-dimension/zero-norm rows —
  spec 9.3's "same dimension alone does not make two vector spaces
  compatible". `QueryEmbeddingCache` is the 9.6 single-flight: N concurrent
  identical queries cost exactly 1 embed call, and its caches are
  per-instance (never process-global).
- `asset_join.py` (spec 7.4/9.4) — joins the centrally shipped role-library
  vectors (corpus 5's `role_library_embeddings`) to local role rows on EXACT
  `(slug, content_version)`. A version bump is a miss, never a fuzzy match.
  `plan_delta_embeds` is the delta-only planner: a rerun over unchanged shared
  roles plans zero embeds, which is the regression lock for the reviewed
  role-library-import fix (corpus 5's "clients install compatible assets, not
  re-embed the whole shared corpus"). Tenant rows shadowing a shared slug
  raise `DuplicateAssetError`; deferred/missing vectors stay in the candidate
  pool rather than being silently dropped.

**Not a seventh corpus.** These modules reference corpora 1-6 by key; they do
not create a new index, store, or asset, and they do not flatten the six into
one. `retrieval_query` / `retrieval_document` are the only cross-reusable task
pair; every other task-type pairing is refused.

Provider/model constants stay pinned in `embedding_engine.py` and the Command
Center's own constants — the retrieval modules take them as call arguments and
duplicate no model strings.

## Provider reliability (build pipeline)

- Keys are read from ALL canonical secret stores and DEQUOTED
  (`KEY="…"` tolerated) — `orchestrator.get_keys()`,
  `embedding_engine._read_secret()`.
- Ollama→OpenRouter fallback converts model ids through
  `orchestrator._openrouter_fallback_model()` (vendor inserted, route prefix
  stripped: `ollama/deepseek-v4.1-flash:cloud` → `deepseek/deepseek-v4.1-flash`).
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

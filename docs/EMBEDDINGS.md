# EMBEDDINGS — the single source of truth

How every corpus in this repo is embedded, matched, verified, and shipped.
If a build, agent, or script touches embeddings and disagrees with this page,
the build is wrong. CI enforces the invariants below
(`.github/workflows/embedding-integrity-guard.yml`).

## The four corpora

| # | Corpus | Retrieval model | Store | Integrity gate |
|---|--------|-----------------|-------|----------------|
| 1 | Coaching personas (Skill 22 blueprints) | Gemini vectors, section-level | `workspace/data/coaching-personas/gemini-index.sqlite` | real-vector hard gate + `--verify` + count triad |
| 2 | Persona matching at runtime | cosine over corpus 1 + category/keyword ladder | same DB + `persona-categories.json` | provider/model row filter + dim guard + keyword fallback |
| 3 | Role library (426 roles) | deterministic `_index.json` lookup — **no embeddings by design** | `23-ai-workforce-blueprint/templates/role-library/_index.json` | `content_sha` (CONTENT-HASH) via `hash-content-manifest.py`, CI `library-lockstep` |
| 4 | SOP libraries | deterministic — **no embeddings by design** | dept SOPs: `_index.json sops[]` (131) · craft clusters: `universal-sops/` | dept SOPs: CONTENT-HASH · universal-sops: `_content-manifest.json` via `scripts/hash-universal-sops-manifest.py` |

## Non-negotiable invariants (EMBED-1..8)

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
   fail-loud (non-zero exit or wrapper-not-found ⇒ `FAILED` in
   pipeline-status.json, never "Re-indexing complete").
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

## Corpus 1 — coaching personas: build → embed → register → ship

- **Build**: Skill 22 orchestrator (`22-…/pipeline/orchestrator.py`) writes
  `personas/<slug>/persona-blueprint.md` under
  `<workspace>/data/coaching-personas/`.
- **Embed (Phase 5)**: section indexer per persona (EMBED-5). One row per
  `## Section N`; `mode` from `embedding_engine.{COACHING,LEADERSHIP}_SECTION_NUMBER`
  (3=coaching, 4=leadership); md5 HASH-SKIP prevents re-embedding unchanged
  blueprints; provider/model/dim stamped on every row; post-write verification
  aborts on any contract violation.
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
   `python3 shared-utils/embedding_engine.py --verify` + `--status`).
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
```

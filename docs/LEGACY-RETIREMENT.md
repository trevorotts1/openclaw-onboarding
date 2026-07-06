# Legacy Retirement Tracking

Scripts in this list contain known legacy local path-candidate loops that bypass or
duplicate the canonical `get_openclaw_paths()` resolver from
`shared-utils/detect_platform.py`. Each file either:

- imports the shared resolver AND also keeps a local `~/clawd/...` fallback list, or
- contains a local candidate-loop list with `HOME / "clawd" / ...` items directly.

**These files are on the retirement list and WILL be cleaned up one release after
fleet migration to the canonical resolver is complete.** Until then they are
explicitly tracked here so the CI guard can distinguish "known legacy" from "rogue
new addition."

The CI step `"AF3: local-candidate-loop guard (32-command-center-setup + repo-wide)"`
in `.github/workflows/qc-static.yml` reads this allowlist. Any Python file that is
NOT listed here and contains a local `~/clawd` candidate loop (a list-item expression
of the form `HOME / "clawd" / ...` or `expanduser("~/clawd/...")` followed by a
comma) will FAIL the build.

---

## Retired orphan modules (no longer the source of truth)

These modules have been superseded by a live replacement. They are kept on disk only
so historical runs/references resolve, and are explicitly documented here so the
renderer-identity gates (`AF-RENDERER`, `AF-CONVERTER-PARITY`) and the department docs
can distinguish "retired orphan" from "live builder."

| Retired module | Replaced by | Status / notes |
|----------------|-------------|----------------|
| `23-ai-workforce-blueprint/templates/presentation-render/render_deck.py` | `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py` (the ONE canonical renderer) | RETIRED — orphan: nothing imports it. Its prompt char-floor / structural-block / model-sovereignty checks were folded into `build_deck.py`. `build_deck.py` writes the authoritative render record to `working/checkpoints/process_manifest.json` via `write_process_manifest()`; the old `render_manifest.json` is no longer written or read. `sync_check.py` (V1) still pins `render_deck.py`'s `PROMPT_CHAR_FLOOR/CEILING` constants equal to `build_deck.py`'s as a drift-detection backstop until the orphan file is deleted. **Do not key any gate off `render_manifest.json`.** Remove the orphan file (and the V1 drift pin) in a cleanup release once no fleet box references the old path. |

---

## Tracked files with local candidate loops (pending removal)

### 32-command-center-setup (primary AF3 scope)

The two scripts called out in AF3(a) import the shared resolver
(`get_openclaw_paths()`) but keep local `~/clawd` roots in a `roots.extend([...])`
block alongside it. These are the direct retirement targets.

| File | Local loop location | Status |
|------|---------------------|--------|
| `32-command-center-setup/scripts/generate-kpi-rollup.py` | `find_zhc_company_dir()` — `roots.extend([HOME / "clawd" / "zero-human-company", HOME / "clawd" / "zhc", ...])` lines 83-88 | TRACKED — remove local loop after fleet migration |
| `32-command-center-setup/scripts/generate-brand-css.py`  | `find_zhc_company_config()` — `roots.extend([HOME / "clawd" / "zero-human-company", HOME / "clawd" / "zhc", ...])` lines 79-84 | TRACKED — remove local loop after fleet migration |
| `32-command-center-setup/scripts/seed-workspaces.py`     | `_zhc_root_candidates()` — `roots.extend([Path.home() / "clawd" / ..., ...])` | TRACKED — remove local loop after fleet migration |
| `32-command-center-setup/scripts/seed-dashboard-content.py` | `for root in [Path.home() / "clawd/zero-human-company", ...]` inline loop | TRACKED — remove local loop after fleet migration |

### Skill 23 (ai-workforce-blueprint)

| File | Local loop location | Status |
|------|---------------------|--------|
| `23-ai-workforce-blueprint/scripts/populate-sops-from-manifest.py` | inline candidate list with `HOME / "clawd" / ...` items | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/scripts/sync-md-content-to-db.py`       | inline list with `Path.home() / "clawd" / ...` items | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/scripts/backfill-build-state.py`        | inline list with `Path.home() / "clawd" / ...` items | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py`       | single-item list `[Path.home() / "clawd" / "departments", ...]` | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/scripts/persona-selector-v2.py`         | single-path list `[Path.home() / "clawd" / "skills" / ..., ...]` | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/scripts/_qc_company_info.py`            | candidate + parent list with `Path.home() / "clawd" / "zero-human-company"` items (v11.18.4: byte-equivalent extraction out of `qc-completeness.sh`'s inline resolver heredoc for stock-bash-3.2 compatibility — calls `get_openclaw_paths()` first; the `~/clawd` scan is a non-standard-layout fallback) | TRACKED — remove after fleet migration |

#### Presentation-render templates (`~/clawd/secrets/.env` secret-location fallback)

These deck/image generator templates resolve the API key from the client's
own env stores via a `SECRETS_CANDIDATES` list. The `~/clawd/secrets/.env` item is
a legit secret-location fallback (tried after the `~/.openclaw/workspace/.env` and
`~/.openclaw/secrets/.env` stores), NOT a company-root candidate loop. It matches
the AF3 `expanduser("~/clawd/...")`-list-item pattern, so it is tracked here.

| File | Local loop location | Status |
|------|---------------------|--------|
| `23-ai-workforce-blueprint/templates/presentation-render/kie_generate.py`                | `SECRETS_CANDIDATES` list with `os.path.expanduser("~/clawd/secrets/.env"),` item | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/build_deck.py`   | `SECRETS_CANDIDATES` list with `os.path.expanduser("~/clawd/secrets/.env"),` item | TRACKED — remove after fleet migration |
| `23-ai-workforce-blueprint/templates/role-library/presentations/scripts/kie_generate.py` | `_secrets_candidates()` list with `os.path.expanduser("~/clawd/secrets/.env"),` item | TRACKED — remove after fleet migration |

#### Skill 58 (podcast-production-engine) credential resolvers (`~/clawd/secrets` secret-store fallback)

These per-episode credential resolvers discover the client's Convert and Flow and
provider tokens across the fleet's multiple env stores. The `~/clawd/secrets` and
`~/clawd/secrets/.env` items are legit secret-store fallbacks (searched alongside
`~/.openclaw` and `/data/.openclaw`, after live process env), NOT company-root
candidate loops. They match the AF3 `expanduser("~/clawd/...")`-list-item pattern,
so they are tracked here.

| File | Local loop location | Status |
|------|---------------------|--------|
| `58-podcast-production-engine/scripts/caf/field_layer/resolver.py` | `_SWEEP_DIRS` list with `os.path.expanduser("~/clawd/secrets"),` item | TRACKED — remove after fleet migration |
| `58-podcast-production-engine/scripts/ghl_credential_gate.py` | `ENV_FILE_PATHS` list with `os.path.expanduser("~/clawd/secrets/.env"),` and `SWEEP_DIRS` list with `os.path.expanduser("~/clawd/secrets"),` items | TRACKED — remove after fleet migration |

### Skill 22 (book-to-persona)

| File | Local loop location | Status |
|------|---------------------|--------|
| `22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py` | candidate list with `Path.home() / "clawd" / "scripts" / ...` item | TRACKED — remove after fleet migration |

### shared-utils

| File | Local loop location | Status |
|------|---------------------|--------|
| `shared-utils/key_resolver.py`  | list with `os.path.expanduser("~/clawd/secrets/.env"),` item | TRACKED — consolidate into api_key_utils |
| `shared-utils/api_key_utils.py` | list with `os.path.expanduser("~/clawd/secrets/.env"),` item | TRACKED — kept as single canonical secrets lookup |
| `shared-utils/llm_score.py`     | candidate list with `Path.home() / "clawd" / "data" / ...` and `Path.home() / "clawd" / "coaching-personas" / ...` items | TRACKED — remove after fleet migration |

---

## Retirement trigger (automated — deterministic, not vibes)

The retirement trigger is built into `scripts/fleet-refresh.sh`. It fires
**automatically** when:

1. `fleet-refresh.sh --apply` completes a run against the full fleet.
2. Every box in the loaded-state manifest (`.fleet-loaded-state.json` in the
   repo root) reports `loaded=YES` (i.e. CEO_ORCHESTRATOR_RULE_V2 is present
   in the live injected system prompt).
3. `retirement_triggered` is not already `True` in the manifest.

When all three conditions hold, fleet-refresh.sh opens (or updates) a
`retirement-tracker` GitHub issue titled
_"Retire legacy shim + clawd fallbacks (auto-triggered: all boxes loaded)"_
on `trevorotts1/openclaw-onboarding` via `gh issue create`. If `gh` is not
on PATH the trigger writes a `.fleet-retirement-triggered` sentinel file so
the event is not lost.

**DRY-RUN SAFETY:** `--dry-run` (the default) and `--verify-only` are
**100% inert** for the retirement path. The manifest is never written and
`retirement_triggered` is never set during a dry-run. This avoids the AF4
QC defect where a per-box `--dry-run` persisted `retirement_triggered=True`
and permanently blocked issue creation.

**Idempotency:** once `retirement_triggered=True` is set in
`.fleet-loaded-state.json`, subsequent `--apply` runs update (comment on)
the existing issue rather than creating duplicates.

**Fixture/dry-run verification:** `scripts/test-fleet-refresh.sh` Tests
13a-13d prove the trigger contract without touching any real box or network:
- 13a: dry-run does NOT write the manifest
- 13b: all-loaded APPLY fires the trigger and sets `retirement_triggered=True`
- 13c: second all-loaded APPLY is idempotent (no duplicate)
- 13d: partial-loaded APPLY does NOT fire the trigger

## Retirement plan

After the trigger fires and the retirement-tracker issue is open:

1. Remove the `roots.extend([HOME / "clawd" / ..., ...])` block from each tracked
   file in 32-command-center-setup. Replace with a simple `Path(_PATHS["company_root"])`
   lookup (raise `RuntimeError` if missing rather than silently scanning local paths).
2. Remove the equivalent blocks from the Skill 23 and Skill 22 files listed above.
3. Consolidate `shared-utils/key_resolver.py` secrets path into `api_key_utils.py`.
4. Remove the DEPRECATED SHIM marker from
   `23-ai-workforce-blueprint/scripts/select-persona-for-task.py`.
5. Remove the file entries from the tables above.
6. The CI guard will then enforce "zero local candidate loops" with an empty allowlist.

**Trigger:** `fleet-refresh.sh --apply` fires automatically when the last box
reports `loaded=YES` (see "Retirement trigger" section above).

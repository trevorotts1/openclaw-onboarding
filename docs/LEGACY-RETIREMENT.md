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

## Retirement plan

After fleet migration to the canonical `get_openclaw_paths()` resolver is confirmed
complete (all managed clients on OpenClaw >= the version that ships `company_root`
in the platform paths map):

1. Remove the `roots.extend([HOME / "clawd" / ..., ...])` block from each tracked
   file in 32-command-center-setup. Replace with a simple `Path(_PATHS["company_root"])`
   lookup (raise `RuntimeError` if missing rather than silently scanning local paths).
2. Remove the equivalent blocks from the Skill 23 and Skill 22 files listed above.
3. Consolidate `shared-utils/key_resolver.py` secrets path into `api_key_utils.py`.
4. Remove the file entries from the tables above.
5. The CI guard will then enforce "zero local candidate loops" with an empty allowlist.

**Trigger (AF4 — automated, deterministic):** The retirement trigger is now
machine-enforced. `fleet-refresh.sh` (via `shared-utils/fleet_manifest.py`) tracks
per-box `loaded=YES` state in `fleet-manifest.json` at the repo root. When the LAST
box reports `loaded=YES`, the trigger fires automatically:

1. A sentinel file `legacy-retirement-triggered` is written to the repo root.
2. A GitHub issue titled **"Retire legacy shim + clawd fallbacks (AF4 retirement trigger)"**
   is opened (or updated if it already exists) in `trevorotts1/openclaw-onboarding`
   via `gh issue create`.
3. `fleet-manifest.json` is updated with `retirement_triggered: true` and the
   issue number — making subsequent runs idempotent (they report
   "already triggered" and do nothing).

The trigger is **NOT vibes** — it fires exactly once when all fleet boxes cross the
`loaded=YES` threshold, with a verifiable audit trail in `fleet-manifest.json`,
the sentinel file, and the GitHub issue.

**Fleet manifest schema** (`fleet-manifest.json`):
```json
{
  "schema_version": 1,
  "boxes": {
    "<box-name>": {
      "loaded": true,
      "loaded_confidence": "authoritative | proxy | unknown",
      "last_updated_ts": 1234567890,
      "onboarding_version": "v11.13.0",
      "cc_version": "4.14.0"
    }
  },
  "retirement_triggered": false,
  "retirement_issue_number": null,
  "retirement_triggered_ts": null
}
```

**Dry-run fixture test:** `bash scripts/test-fleet-refresh.sh` includes Test 13
(five sub-tests) that prove the trigger fires on a simulated all-loaded state and
is inert for a partial fleet. The CLI entry point also supports:

```bash
# Simulate all-loaded and show trigger output (no gh call):
python3 shared-utils/fleet_manifest.py \
  --repo-root . \
  --simulate-all-loaded \
  --boxes "box-a,box-b,box-c" \
  --dry-run
```

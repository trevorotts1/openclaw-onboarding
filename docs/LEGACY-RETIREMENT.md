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

**Trigger:** Once `get_openclaw_paths()["company_root"]` is verified to return a
non-empty value on every managed Mac and VPS in the fleet (check via
`openclaw config get env.vars.ZHC_COMPANY_ROOT` or equivalent), the retirement can
proceed.

# Changelog - Book-to-Persona

All notable changes to this skill wrapper are documented here.

---

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

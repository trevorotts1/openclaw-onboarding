# SOP: Adding a Capability After Build

**Version:** 2.0.0
**Applies to:** All client boxes (Mac and VPS)
**Owner department:** Project Architecture Office (PAO) / General Task (for one-off additions)

---

## Common Pre-Conditions (verify ALL before any event below)

| # | Check | How |
|---|-------|-----|
| 1 | Box is ONLINE | `openclaw gateway status` returns `running` |
| 2 | SSH / terminal access confirmed | `echo $HOSTNAME` succeeds |
| 3 | OpenClaw version up to date | `openclaw --version` ≥ installed skill's minimum |
| 4 | Repo clone is fresh from correct remote | `git remote get-url origin` matches intended URL exactly |
| 5 | `OLLAMA_API_KEY` is set | `echo $OLLAMA_API_KEY` is non-empty |
| 6 | No other agent mid-build on this box | `openclaw subagents list` returns empty or non-critical agents |

## Platform Resolver (run once at top of any manual session)

```bash
# Resolve OC_ROOT — run this first so all subsequent commands use the right path
if [ -d /data/.openclaw ]; then
  OC_ROOT="/data/.openclaw"     # VPS (Hostinger Docker)
elif [ -d "$HOME/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"     # Mac (homebrew openclaw)
else
  echo "ERROR: cannot find OpenClaw root" && exit 1
fi
echo "OC_ROOT=$OC_ROOT"
```

---

## Event 1 — New Book / Video / Web URL (new persona source)

**Trigger:** Owner provides a book file, YouTube link, web URL, or video file to add as a coaching persona.

### Steps

1. Verify pre-conditions above.
2. Confirm source type (PDF/EPUB/MOBI = book, youtube.com = YouTube, http(s):// = web, mp4/mov/mkv = video).
3. Run the ingestion script:
   ```bash
   bash $OC_ROOT/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
     --source "<path-or-url>" \
     --title "Title" \
     --author "Author"
   ```
4. Script auto-invokes the 3-phase pipeline (Extraction → Analysis → Synthesis) and re-indexes Gemini.
5. Review the auto-classification in `persona-categories.json` for the new slug:
   ```bash
   python3 -c "
   import json
   cat = json.load(open('$OC_ROOT/master-files/coaching-personas/persona-categories.json'))
   slug = '<new-slug>'
   print(json.dumps(cat['personas'].get(slug, {}), indent=2))
   "
   ```
6. If `domain[]` shows only `["coaching"]` (default fallback), manually refine the tags in `persona-categories.json`.
7. Regenerate `governing-personas.md` for affected departments:
   ```bash
   bash $OC_ROOT/skills/23-ai-workforce-blueprint/scripts/generate-governing-personas.sh
   ```

### Verification Gate

```bash
# Blueprint written
ls $OC_ROOT/master-files/coaching-personas/personas/<slug>/persona-blueprint.md

# persona-categories.json has the new entry
python3 -c "import json; c=json.load(open('$OC_ROOT/master-files/coaching-personas/persona-categories.json')); print('OK' if '<slug>' in c.get('personas',{}) else 'MISSING')"

# governing-personas.md updated (check timestamp)
ls -la $OC_ROOT/workspace/agents/main/departments/*/governing-personas.md | head -5
```

---

## Event 2 — New Department

**Trigger:** Owner wants a department that was not in the initial Skill 23 build, or a new dept slug appears in `_index.json`.

### Steps

1. Verify pre-conditions above.
2. Run `add-department.sh` — this is the CANONICAL path for all new department adds:
   ```bash
   bash $OC_ROOT/skills/32-command-center-setup/scripts/add-department.sh \
     --slug <slug> \
     --name "<Display Name>" \
     --icon "🔧" \
     --head-name "<Name> Lead"
   ```
   This creates: CC workspaces row + head agent + QC/Research/DA trio + routing registration + role-library entry + persona-stale marker.

3. Run converge — **MANDATORY closing step, never skip**:
   ```bash
   bash $OC_ROOT/skills/32-command-center-setup/scripts/sync-extensions.sh --converge
   ```
   Converge: validates `_index.json` invariants → refreshes build-state → regenerates ORG-CHART.md → re-syncs CC dashboard. FAIL LOUD if CC sync fails.

### Verification Gate (REQUIRED — checks the CC, not just openclaw.json)

```bash
# 1. CC workspaces row exists
python3 - "$OC_ROOT" "$slug" <<'PY'
import sys, sqlite3, glob
oc, slug = sys.argv[1], sys.argv[2]
dbs = glob.glob(f"{oc.replace('/data/.openclaw','').replace(oc,'')}/projects/command-center/mission-control.db") + \
      ["/app/mission-control.db", "/opt/mission-control/mission-control.db"]
db = next((d for d in dbs if __import__('os').path.exists(d)), None)
if not db: print("DB NOT FOUND"); sys.exit(1)
row = sqlite3.connect(db).execute("SELECT id,name FROM workspaces WHERE slug=?", (slug,)).fetchone()
print(f"workspaces row: {row or 'MISSING'}")
PY

# 2. Routing registered in openclaw.json
python3 -c "
import json, sys
cfg = json.load(open('$OC_ROOT/openclaw.json'))
depts = [d.get('dept_slug','') for d in cfg.get('extension_registry',{}).get('departments',[])]
slug = '<slug>'
print('routing: OK' if slug in depts else f'routing: MISSING (found: {depts})')
"

# 3. Board visible (the CC loadDepartments() path)
# Open the CC in browser and confirm the new dept card appears on the dashboard.

# 4. QC specialist row exists
python3 -c "
import sqlite3
# Use the same db path discovered above
conn = sqlite3.connect('<db-path>')
rows = conn.execute(\"SELECT id,name,role_type FROM agents WHERE workspace_id=? AND (role_type='QC Specialist' OR role LIKE '%QC%')\", ('<slug>',)).fetchall()
print('qc_specialist:', rows or 'MISSING')
"

# 5. Sample route works
openclaw message send --channel telegram --body "Test task for <slug> dept"
# Confirm it routes to the new dept board
```

---

## Event 3 — New Role / Specialist (under an existing dept)

**Trigger:** Owner wants to add a single specialist role under an existing department on a live box.

### Steps

1. Verify pre-conditions above.
2. Run `add-role.sh`:
   ```bash
   bash $OC_ROOT/skills/23-ai-workforce-blueprint/scripts/add-role.sh \
     --dept <dept-slug> \
     --role "<Role Name>"
   ```
   This creates: role workspace + agent row + persona governance file + `.persona-index-stale` marker + `_index.json` upsert.

3. **REQUIRED: Fill how-to.md from the role-library template.** Remove the `[PENDING — FILL FROM LIBRARY]` marker.
   The role is BLOCKED from live status until this is done. QC gate will catch it.
   ```bash
   # Template location
   ls $OC_ROOT/skills/23-ai-workforce-blueprint/templates/role-library/<dept-slug>/<role-slug>/how-to.md
   # Copy and edit it
   cp [...] $OC_ROOT/workspace/agents/main/departments/<dept-slug>/roles/<role-slug>/how-to.md
   # Then edit to remove [PENDING] and fill in actual SOPs
   ```

4. Run converge — **MANDATORY closing step, never skip**:
   ```bash
   bash $OC_ROOT/skills/32-command-center-setup/scripts/sync-extensions.sh --converge
   ```

### Verification Gate

```bash
# Role dir exists under dept
ls $OC_ROOT/workspace/agents/main/departments/<dept-slug>/roles/<role-slug>/

# IDENTITY.md and SOUL.md written
ls $OC_ROOT/workspace/agents/main/departments/<dept-slug>/roles/<role-slug>/{IDENTITY.md,SOUL.md,how-to.md}

# Agent row in CC DB
sqlite3 <db-path> "SELECT id,name,role FROM agents WHERE workspace_id='<dept-slug>' AND name LIKE '%<role>%';"
```

---

## Event 4 — New SOP

**Trigger:** Owner or agent needs a new SOP for a role or department.

### Steps

1. Identify the owning department and role (or company-wide universal SOP).
2. Author the SOP markdown file (you write it FIRST, then call `add-sop.sh`).
   Must have: title, context, and at least 3 numbered steps.
   ```bash
   cat > /tmp/new-sop.md << 'EOF'
   # <SOP Title>

   ## Purpose
   <one-line purpose>

   ## Steps
   1. <Step 1>
   2. <Step 2>
   3. <Step 3>
   EOF
   ```

3. Register the SOP with `add-sop.sh` (validates substance, places file, regenerates `00-INDEX.md`):
   ```bash
   bash $OC_ROOT/skills/32-command-center-setup/scripts/add-sop.sh \
     --dept <dept-slug> \
     [--role <role-slug>] \
     --title "<SOP Title>" \
     --file /tmp/new-sop.md \
     [--keywords "kw1,kw2"]
   ```

4. Run converge — **MANDATORY closing step, never skip**:
   ```bash
   bash $OC_ROOT/skills/32-command-center-setup/scripts/sync-extensions.sh --converge
   ```
   Converge ingests the SOP into the CC dashboard via `POST /api/sops/import-role-library`.

### Verification Gate

```bash
# SOP file placed and 00-INDEX.md regenerated
cat $OC_ROOT/workspace/agents/main/departments/<dept-slug>/SOP/00-INDEX.md | grep <sop-slug>

# Converge completed without error (check add-ledger)
tail -1 $OC_ROOT/extension-sync/add-ledger.jsonl | python3 -c "import json,sys; d=json.loads(sys.stdin.read()); print(d.get('status'))"
```

---

## Event 5 — New Skill (repo-level skill released)

**Trigger:** A new skill (e.g. Skill 44) is released in the onboarding repo and the Sunday cron detected version drift.

### Steps

1. Pull the latest repo:
   ```bash
   cd ~/Downloads/openclaw-onboarding && git pull origin main
   ```
2. Run the update-skills script:
   ```bash
   bash update-skills.sh
   ```
3. Verify the skill is installed:
   ```bash
   ls $OC_ROOT/skills/ | grep <skill-number>
   ```
4. If the skill adds a new department, also run Event 2 steps above.
5. Send owner confirmation via Telegram (N rule — use `openclaw message send`).

### Verification Gate

```bash
openclaw --version  # should match the new version
ls $OC_ROOT/skills/<skill-number>-*/
```

---

## Event 6 — New Persona Type / Persona Governance Update

**Trigger:** A new persona style, domain tag, or perspective tag is added to the persona taxonomy.

### Steps

1. Update `persona-categories.json` with the new domain/perspective tags.
2. Re-classify existing personas if needed:
   ```bash
   # Re-run auto-classification pass on all existing personas
   bash $OC_ROOT/skills/22-book-to-persona-coaching-leadership-system/scripts/add-persona-from-source.sh \
     --source <path> --skip-index
   ```
3. Re-index Gemini:
   ```bash
   python3 $OC_ROOT/workspace/scripts/gemini-indexer.py
   ```
4. Regenerate `governing-personas.md` for ALL departments:
   ```bash
   bash $OC_ROOT/skills/23-ai-workforce-blueprint/scripts/generate-governing-personas.sh
   ```

### Verification Gate

```bash
# Confirm new domain/perspective tags appear in persona-categories.json
python3 -c "
import json
c = json.load(open('$OC_ROOT/master-files/coaching-personas/persona-categories.json'))
print('Domain tags:', list(c.get('domainTags', {}).keys()))
print('Perspective tags:', list(c.get('perspectiveTags', {}).keys()))
"

# Confirm governing-personas.md updated for the affected dept
grep -l '<new-tag>' $OC_ROOT/workspace/agents/main/departments/*/governing-personas.md
```

---

## Event 7 — New / Updated Template Library (funnel or automation)

**Trigger:** The Skill-6 funnel template library (`06-ghl-install-pages/funnel-templates/`) or the
Skill-44 automation template library (`44-convert-and-flow-operator/automation-templates/`) gains,
removes, or edits a template — e.g. a Sunday-cron skill update refreshes the 38/28 templates or the
funnel→automation link map. These libraries are LOAD-BEARING (the matchers reference them by
path/id; the link map pairs them), so a refresh requires a box-side re-index + env check that the
other six events do not cover.

### Steps

1. **Rebuild + commit the catalog indexes** (lexical — NO embeddings needed):
   ```bash
   python3 $OC_ROOT/skills/06-ghl-install-pages/tools/funnel_matcher_cli.py --build-index
   python3 $OC_ROOT/skills/44-convert-and-flow-operator/automation-templates/_matcher/cli.py --build-index
   ```
   (The indexes are written PORTABLY — relative paths, no operator-local path. The operator commits
   them; boxes pull the committed index.)
2. **Verify the matcher env vars are wired** onto the persistent dept agent (so STEP 0 / Step 0.4
   actually activate — they are env-gated and DARK by default):
   ```bash
   bash $OC_ROOT/skills/44-convert-and-flow-operator/tools/engine/wire-ghl-env.sh
   # wires GHL_FUNNEL_CATALOG / GHL_FUNNEL_INDEX / GHL_FUNNEL_AUTOMATION_LINKS and
   #       CAF_AUTOMATION_CATALOG / CAF_AUTOMATION_INDEX / CAF_FUNNEL_AUTOMATION_LINKS
   ```
3. **(Optional) ingest the templates into the Command Center** for lexical SOP/keyword search:
   ```bash
   python3 $OC_ROOT/skills/32-command-center-setup/scripts/ingest-template-libraries.py
   ```
   Lexical only — do NOT re-embed the persona corpus (shared-corpus re-embedding bloat lesson).
4. **Sample-match to prove it took:**
   ```bash
   python3 $OC_ROOT/skills/06-ghl-install-pages/tools/funnel_matcher_cli.py --match "grow my email list"
   python3 $OC_ROOT/skills/44-convert-and-flow-operator/automation-templates/_matcher/cli.py --match "new subscriber welcome" 
   ```

### Verification Gate

```bash
# Indexes in sync with disk + link map (0 drift, 0 broken refs, portable):
python3 $OC_ROOT/skills/scripts/check-funnel-automation-library-drift.py

# The matcher env vars are present on the gateway-inherited env:
openclaw config get env.vars.GHL_FUNNEL_INDEX
openclaw config get env.vars.CAF_AUTOMATION_INDEX
```

---

## Failure Modes

| Failure | Recovery |
|---------|----------|
| `sync-extensions.sh` exits non-zero | Check `$OC_ROOT/extension-sync/sync-*.log`; restore backup `$OC_ROOT/openclaw.json.bak-reg-<ts>` |
| `add-department.sh` returns `FATAL: mission-control.db not found` | CC not installed — run `seed-workspaces.py` first to create the DB |
| Dept slug not in naming map | Ensure repo is on latest main; if slug truly doesn't exist, inform owner capability is not yet available |
| Gateway restart fails (LaunchAgent err 125 on Mac) | Use `openclaw gateway run` instead; set up watchdog cron (see Mac client gateway SOP) |
| QC gate < 8.5 | Do NOT deliver to owner; fix the failing check, re-run QC |
| CC board shows dept but routing doesn't work | Run `add-department.sh --slug <slug> --name "<name>"` again (idempotent) to backfill routing |
| Persona not searchable after add | Run `python3 $OC_ROOT/workspace/scripts/gemini-indexer.py` manually |

---

## Hand-To

After completion, hand off to:
- **Owner (Telegram):** confirmation message with Event type and what was added
- **Head of General Task / Chief Project Architect:** update project tracker if part of a larger initiative
- **SOP Writer:** document any new patterns discovered

---

## SOP Author

Project Architecture Office — SOP Writer role
QC reviewed per Rule 6 (different model from writer)
v2.0.0: 2026-06-09 — full rewrite covering all 6 events (G4 audit fix); added
  platform resolver, CC verification gates (SELECT from workspaces, loadDepartments
  check, sample route), persona auto-re-index + governing-personas regen steps for
  persona events, and dept CC+routing+QC-specialist wiring for department event.
  Replaced sync-extensions-only guidance with the correct dual-path (sync-extensions
  for index-detected depts, add-department.sh for manual adds).
v1.0.0: 2026-06-09 — initial version (sync-extensions focused, no CC verification).

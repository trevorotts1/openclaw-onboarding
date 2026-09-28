# Teach Yourself Protocol - How to Use

## Step-by-Step Process

### 1. Announce
Tell the user: "I am activating the Teach Yourself Protocol to permanently retain this knowledge."
Never execute TYP silently. The user must always know when it is running.

### 2. Understand What You Are Learning
- What category? (tool, API, process, preference, contact, credential, playbook/SOP)
- How often will you use it? (daily, weekly, rarely)
- What priority? (CRITICAL, HIGH, STANDARD, REFERENCE)

### 3. Assess Size
| Content Size | Classification | What to Do |
|-------------|---------------|------------|
| One or two sentences | Small | Core files only |
| Up to a short paragraph (about five sentences) | Medium | Core files only, be concise |
| Longer than a short paragraph | Large | Deep file in master folder + core-file pointer |
| 100+ lines | Very Large | Deep file in master folder + core-file pointer |
| Multi-topic / API docs | Massive | Folder structure + deep files + core-file pointer |

Always-on rules (safety rules, never-do rules, identity essentials, hard constraints) stay
inline in the core file at any size, shortened, because the agent only opens a deep file
when a pointer's WHEN fires.

### 4. Check for Existing Knowledge
Search ALL core files and the master files folder BEFORE creating anything new.
- If found and matches: update it, do not duplicate
- If found but conflicts: flag to user, ask which version is correct
- If not found: proceed to create new

### 5. Create Deep File (If Needed)

**STORAGE PATH (canonical, non-negotiable):**
- Mac: `~/Downloads/openclaw-master-files/<typ-subfolder>/` (e.g., `playbooks/`, `processes/`, `apis/`, `skills/`, `references/`)
- VPS: `/data/.openclaw/master-files/<typ-subfolder>/` (same subfolder names)

**PERSISTENCE NOTE (VPS — MANDATORY CHECK):**
On a Hostinger Docker VPS, ALL files MUST live under `/data/.openclaw/` (the bind-mounted
persistent volume). Files written anywhere else — `/tmp/`, the container's root filesystem,
or any path NOT under `/data/` — are EPHEMERAL and will be WIPED on container restart. Before
saving any deep file or playbook, confirm the path starts with `/data/.openclaw/`.

**DEDICATED PLAYBOOK SUBFOLDER — ENFORCED:**
When the user invokes TYP on a playbook, book, SOP, or process document (e.g., "use
the Teach Yourself Protocol on this playbook"), the content MUST be placed in a dedicated
subfolder named `playbooks/` inside the master files root:
- Mac:  `~/Downloads/openclaw-master-files/playbooks/`
- VPS:  `/data/.openclaw/master-files/playbooks/`

If this subfolder does not exist yet, CREATE it before saving the file. Never store
playbooks loose in the master files root or inside a different subfolder type.

Save COMPLETE, UNABRIDGED content to that path with this header:
```
# [Topic Name]
- Source: [where this came from]
- Date learned: [date]
- Priority: [CRITICAL/HIGH/STANDARD/REFERENCE]
- Referenced by: [which core files point to this]
```
NEVER truncate the deep file. It is the full reference.

**POINTER FORMAT (required in every core file that references a deep file):**
One line, at most two sentences: WHAT it is, WHERE it lives (full path), WHEN to read it
(concrete trigger words a user would say).
```
[Topic]: [what it is] lives at ~/Downloads/openclaw-master-files/<subfolder>/<filename>.md. Read it whenever the user mentions [trigger words].
```

### MANDATORY — NO-PASTE RULE
**Long playbooks, SOPs, API docs, and any block longer than a short paragraph (about five sentences, always-on rules excepted) MUST NEVER be pasted into any bootstrap file (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, SOUL.md, IDENTITY.md).** Store the full document in the master-files TYP subfolder. Add only a one-to-two-sentence pointer (WHAT, WHERE, WHEN) to the file; always-on rules stay inline, shortened. Vagueness about storage path or pointer format is what causes bloat: this rule is absolute.

### 6. Write Core File Pointers (ONE TO TWO SENTENCES, ENFORCED)

Add a pointer (one line, at most two sentences) to the relevant core file(s).
The agent decides whether AGENTS.md, TOOLS.md, or both should get the entry, but at
minimum ONE of them MUST receive it. Every pointer MUST answer all three of these:

1. **WHAT it is**: a few words naming the topic and what it does
2. **WHERE it lives**: the EXACT file path to the playbook/deep file so the agent
   can find, read, and execute it (full absolute path, no vagueness)
3. **WHEN to read it**: concrete trigger words a user would say

If any of the three are missing, the pointer does NOT earn its place in the bootstrap file.
Always-on rules (safety rules, never-do rules, identity essentials, hard constraints) stay
inline next to the pointer, shortened. Everything situational lives in the deep file.

### 7. Confirm to User
Report:
- What you learned
- Where the full document is stored (exact path)
- Which core files were updated and what was added to each
- Confirmation that the playbook subfolder was created/used (if applicable)
- Confirmation that the path is persistence-safe (VPS: under /data/.openclaw/)

## Priority Tags

| Priority | Tag | Use When | Core File Entry |
|----------|-----|----------|---------------|
| CRITICAL | [PRIORITY: CRITICAL] | Daily use, core operations | Pointer (1 to 2 sentences) |
| HIGH | [PRIORITY: HIGH] | Weekly use, quality matters | Pointer (1 to 2 sentences) |
| STANDARD | [PRIORITY: STANDARD] | Occasional use | Pointer (1 to 2 sentences) |
| REFERENCE | [PRIORITY: REFERENCE] | Rare, edge cases | Pointer (1 to 2 sentences) |

## Staleness Detection
- Under 30 days: Fresh. Use confidently.
- 30-90 days: Aging. Note the age if errors occur.
- Over 90 days: Stale. Verify before relying on it.

## Which Core File Gets What

| Knowledge Type | Primary File | Secondary Files |
|---------------|-------------|-----------------|
| Tool/API usage | TOOLS.md | MEMORY.md |
| Behavioral rules | AGENTS.md | IDENTITY.md |
| User preferences | USER.md | MEMORY.md |
| Personal identity | IDENTITY.md | SOUL.md |
| Recurring tasks | HEARTBEAT.md | MEMORY.md |
| Contact info | USER.md | MEMORY.md |
| Lessons learned | MEMORY.md | IDENTITY.md |
| Playbook/SOP/Process | AGENTS.md or TOOLS.md | MEMORY.md |

## Common Mistakes

1. Dumping full content into core files (causes bloat, burns tokens) — **the #1 root cause of bootstrap file inflation**
2. Vague storage path — "somewhere in master-files" is not a path; use the canonical path (Mac: `~/Downloads/openclaw-master-files/<subfolder>/`; VPS: `/data/.openclaw/master-files/<subfolder>/`)
3. Missing or incomplete pointer in the core file — every deep file reference needs the full path AND a "when to go deeper" trigger
4. Creating deep file but not referencing it from any core file (orphan file, invisible)
5. Creating duplicate master files folders (search first)
6. Skipping the announcement (user must know TYP is active)
7. Summarizing the deep file (deep file is COMPLETE, never truncate)
8. Not checking for existing knowledge (always search first)
9. Pointer too thin (no exact path, or a vague WHEN the agent will never match)
10. Pointer too thick (more than two sentences; move the detail into the deep file)
11. **Storing a playbook in the wrong subfolder** — playbooks/SOPs always go in `playbooks/`, not loosely in the master-files root or in `processes/` by default
12. **Writing a pointer that omits the trigger or exact path**: all three elements (WHAT, WHERE, WHEN) are required for the pointer to earn its place
13. **VPS: writing files outside /data/.openclaw/** — any path not under the bind-mount is wiped on container restart; always verify the storage path before writing

## Self-Heal Migration (Existing Clients)

If the workspace was created before the mandatory storage path rules were introduced
(v10.15.37+ Mac / v10.16.36+ VPS), run the migration script to fix bloat and
misplaced documents:

```bash
bash scripts/typ-migrate.sh --dry-run    # preview issues
bash scripts/typ-migrate.sh              # apply fixes
```

**Platform detection** (automatic, same logic as apply-fleet-standards.sh):
- `/data/.openclaw/openclaw.json` exists → VPS → `MASTER_FILES_ROOT=/data/.openclaw/master-files`
- else → Mac → `MASTER_FILES_ROOT=$HOME/Downloads/openclaw-master-files`

See `MIGRATION-TYP.md` in this folder for the complete procedure.

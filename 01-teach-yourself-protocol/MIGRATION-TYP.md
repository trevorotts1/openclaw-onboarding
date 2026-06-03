# TYP Self-Heal Migration Procedure

## Purpose

Prevention of bootstrap-file bloat was shipped in v10.15.36/v10.16.35 (canonical storage
paths, mandatory no-paste rule, pointer format). This document defines the MIGRATION
procedure for existing fleet clients that were onboarded before those rules existed and
already have bloat or misplaced documents in their workspaces.

The script `scripts/typ-migrate.sh` automates detection and remediation. This document
explains what it does, why each step exists, and what the agent or operator must do
after running it.

---

## When to Run This

Run `typ-migrate.sh` on any existing client where you suspect:

- Bootstrap files (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, SOUL.md, IDENTITY.md) are
  unusually large (>200–400 lines).
- Documents are stored in wrong locations (e.g. `~/clawd/projects/`, the root of
  `~/Downloads/`, or `/data/` directly) instead of the canonical master-files path.
- Spawned subagents are not respecting the no-paste rule (AGENTS.md is missing the
  mandatory TYP rule block).
- The client was installed before v10.15.36 (Mac) / v10.16.35 (VPS).

---

## Platform-Aware Storage Paths

**CRITICAL — Mac vs VPS differ. Never hardcode one platform.**

The script uses the same detection logic as `scripts/apply-fleet-standards.sh`:

```bash
if [ -f /data/.openclaw/openclaw.json ]; then
  # VPS (Docker container layout)
  MASTER_FILES_ROOT="/data/.openclaw/master-files"
else
  # Mac mini layout
  MASTER_FILES_ROOT="$HOME/Downloads/openclaw-master-files"
fi
```

This is the canonical platform detection. It is reliable because:
- VPS containers always mount OpenClaw data at `/data/.openclaw/`.
- Mac installs always use `$HOME/.openclaw/`.
- The check is a file-existence test, not a hostname or uname test (both can be wrong
  or missing in automated contexts).

TYP subfolders are identical across platforms: `processes/`, `apis/`, `skills/`, `references/`.

---

## Migration Steps (Automated)

Run the script on the affected client machine or via SSH:

```bash
# Auto-detect workspace (recommended)
bash scripts/typ-migrate.sh

# Dry run first to see what would change
bash scripts/typ-migrate.sh --dry-run --verbose

# Specify workspace manually if auto-detection misses it
bash scripts/typ-migrate.sh /path/to/agent/workspace

# VPS example (via SSH into container)
bash scripts/typ-migrate.sh /data/.openclaw/agents/main/workspace
```

The script runs 7 steps in order:

### Step 1: Bloat Detection

Scans every bootstrap file for:
- **Whole-file bloat**: any file over 400 lines (likely contains pasted docs).
- **Section bloat**: any `##` section with more than 25 non-blank lines.

Both thresholds are conservative to avoid false positives on well-written files.

### Step 2: Misplacement Detection

Scans known wrong locations (`~/clawd/projects/`, `~/Downloads/` root, `/data/` root)
for `.md` files that match TYP deep-file signatures:
- Contains `Date learned:`, `Priority: CRITICAL/HIGH/STANDARD/REFERENCE`, or `Referenced by:`

Files correctly placed inside `master-files/` are excluded from misplacement warnings.

### Step 3: Subagent Rule Inheritance Check

Looks for the block heading `MANDATORY — Teach Yourself Protocol (TYP) Storage Rule`
in AGENTS.md. If absent, marks it for injection.

**Why this matters:** Spawned subagents read `AGENTS.md` (and `TOOLS.md`, `USER.md`)
on every session. If the no-paste rule is not in those files, subagents will not
inherit it and will continue creating bloat. This check ensures the prevention release
(v10.15.36+) rules are actually present in the agent's workspace even if the workspace
was created by an older installer.

### Step 4: Relocate Misplaced Files

For each misplaced TYP doc:
1. Classifies the correct subfolder (`apis/`, `processes/`, `skills/`, `references/`)
   from the filename and content keywords.
2. Copies the file to `<MASTER_FILES_ROOT>/<subfolder>/`.
3. Replaces the original file with a forwarding stub pointing to the new location.

If the destination already exists, content is appended under a `--- MIGRATION APPEND ---`
header (never overwrites, never loses data).

### Step 5: Extract Bloated Bootstrap Sections

For each bloated section in a bootstrap file:
1. **Backup-first**: copies the original file to `<file>.bak-typ-<timestamp>`.
2. Extracts the full section content to `<MASTER_FILES_ROOT>/processes/<slug>.md`
   with a TYP header (Source, Date, Priority, Referenced by).
3. Replaces the section in the bootstrap file with a **MIGRATION NOTICE** block
   that includes:
   - The full path to the extracted file.
   - Instructions for the agent to write a proper TYP summary (10–25 lines,
     Five Question Test).
   - An explicit warning: NEVER paste the content back.

**The agent writes the summary, not the script.** Automated summarization would produce
summaries that fail the Five Question Test. The notice gives the agent the full doc path
and the criteria; the agent writes the correct summary the next time it encounters the
notice in context.

### Step 6: Inject Missing Subagent Rule

If the mandatory TYP rule block was absent from AGENTS.md:
1. Backs up AGENTS.md.
2. Appends the canonical rule block (with both Mac and VPS storage paths).
3. Includes the line: "This rule applies to ALL spawned subagents — they read
   AGENTS.md on every session."

### Step 7: Verify

- Confirms AGENTS.md contains the mandatory TYP rule marker.
- Reports backup file names (with timestamp suffix `.bak-typ-<ts>`).
- Exits 0 on success, 1 on verification error.

---

## After Running the Script: Agent Actions Required

The script produces MIGRATION NOTICE blocks in bootstrap files. The agent must act on each:

1. **Read the full content** at the extracted file path.
2. **Write a proper TYP summary** (10–25 lines) in the bootstrap file, replacing the
   MIGRATION NOTICE block.
3. **Five Question Test** — the summary must answer:
   - What is this? (one sentence)
   - When do I use it? (triggers)
   - What do I need to know right now? (key facts)
   - Full reference path?
   - When should I go deeper?
4. **Confirm** to the operator what was summarized, where the full doc lives, and
   that the bootstrap file is now clean.

---

## Idempotency

Re-running the script on a clean workspace is a no-op. It exits 0 with
"No issues found. Workspace is TYP-clean." Re-running after partial remediation
picks up remaining issues only (already-relocated files are excluded, already-present
TYP rule is not re-added).

---

## Backup Files

Every file the script modifies gets a backup copy with suffix `.bak-typ-<timestamp>`.
Example: `AGENTS.md.bak-typ-20260603120000`.

These files are safe to delete once the workspace has been verified clean.
They are never committed to the repo.

---

## Subagent Inheritance — The Key Principle

The mandatory no-paste rule must live in AGENTS.md (and TOOLS.md / USER.md for the
prevention release). Spawned subagents read those three files on every session. Without
the rule in those files, subagents will not inherit it regardless of what INSTRUCTIONS.md
or teach-yourself-protocol-full.md say — those are reference docs, not bootstrap files.

The migration script enforces this by checking and injecting the rule into AGENTS.md.
The prevention release (v10.15.36+) adds it to TOOLS.md and USER.md templates for all
new installs.

---

## Script Location

```
scripts/typ-migrate.sh
```

Usage summary:

| Command | Effect |
|---------|--------|
| `bash scripts/typ-migrate.sh` | Auto-detect workspace, detect + remediate |
| `bash scripts/typ-migrate.sh --dry-run` | Report issues without writing anything |
| `bash scripts/typ-migrate.sh --dry-run --verbose` | Verbose issue report |
| `bash scripts/typ-migrate.sh /path/to/workspace` | Explicit workspace path |
| `bash scripts/typ-migrate.sh --dry-run /path/to/workspace` | Dry run at explicit path |

Exit codes: 0 = clean / fully remediated. 1 = fatal error. 2 = dry-run found issues.

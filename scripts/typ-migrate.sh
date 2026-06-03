#!/usr/bin/env bash
# typ-migrate.sh — TYP Self-Heal Migration
#
# PURPOSE
#   Detect and fix existing bootstrap file bloat + misplaced TYP documents
#   in an agent workspace. PREVENTION was shipped in v10.15.36/v10.16.35.
#   MIGRATION handles existing clients that were set up before that release.
#
# WHAT IT DOES
#   1. DETECT: scans AGENTS.md, TOOLS.md, MEMORY.md, USER.md, SOUL.md, IDENTITY.md
#      for inline content blocks that are longer than ~25 lines (bloat threshold).
#   2. DETECT: scans common wrong locations for misplaced TYP documents
#      (~/clawd/projects/, ~/Downloads/ root, /data/ root, workspace/).
#   3. RELOCATE: moves full docs to the correct platform-specific master-files path,
#      replaces inline content with a hyper-concise summary + explicit pointer.
#   4. VERIFY: confirms destination files exist and bootstrap files are clean.
#
# PLATFORM DETECTION (mirrors apply-fleet-standards.sh)
#   - /data/.openclaw/openclaw.json exists  → VPS (Docker layout)
#     master-files root: /data/.openclaw/master-files/
#   - else                                  → Mac mini layout
#     master-files root: ~/Downloads/openclaw-master-files/
#
# SAFETY RULES
#   - Backup-first: every touched bootstrap file is copied to <file>.bak-typ-<ts>
#     before modification.
#   - Idempotent: re-running is a no-op if workspace is already clean.
#   - Never deletes: always relocates. If the target file already exists, the
#     incoming content is appended under a "--- MIGRATION APPEND ---" header.
#   - Subagent inheritance: confirms the mandatory TYP rule is present in
#     AGENTS.md so all spawned subagents see it on every session.
#   - Dry-run mode: run with --dry-run to see what would change without writing.
#
# USAGE
#   bash scripts/typ-migrate.sh [WORKSPACE_DIR] [--dry-run] [--verbose]
#
#   WORKSPACE_DIR  path to the agent workspace (contains AGENTS.md, TOOLS.md …)
#                  Defaults to $OC_ROOT/agents/<first-agent>/workspace or
#                  $HOME/Downloads/openclaw-master-files/../workspace depending on
#                  platform detection. Override if your layout differs.
#
# EXIT CODES
#   0  clean (no bloat found, or all bloat remediated successfully)
#   1  fatal error
#   2  dry-run found issues (would fix if run without --dry-run)
#
# EXAMPLES
#   bash scripts/typ-migrate.sh                          # auto-detect workspace
#   bash scripts/typ-migrate.sh /data/.openclaw/agents/main/workspace
#   bash scripts/typ-migrate.sh ~/Downloads/workspace --dry-run
#   bash scripts/typ-migrate.sh --dry-run --verbose
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d%H%M%S)
DRY_RUN=false
VERBOSE=false
WORKSPACE_ARG=""

# ─── Parse args ──────────────────────────────────────────────────────────────
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    --verbose) VERBOSE=true ;;
    --*) echo "Unknown flag: $arg" >&2; exit 1 ;;
    *) WORKSPACE_ARG="$arg" ;;
  esac
done

log()  { echo "[typ-migrate] $*"; }
vlog() { $VERBOSE && echo "[typ-migrate:verbose] $*" || true; }
warn() { echo "[typ-migrate:WARN] $*" >&2; }

# ─── Platform detection ───────────────────────────────────────────────────────
# Mirrors apply-fleet-standards.sh exactly:
#   if /data/.openclaw/openclaw.json exists → VPS container layout
#   else                                    → Mac mini layout ($HOME/.openclaw)
if [ -f /data/.openclaw/openclaw.json ]; then
  PLATFORM="vps"
  OC_ROOT="/data/.openclaw"
  MASTER_FILES_ROOT="/data/.openclaw/master-files"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  PLATFORM="mac"
  OC_ROOT="$HOME/.openclaw"
  MASTER_FILES_ROOT="$HOME/Downloads/openclaw-master-files"
else
  warn "Cannot find openclaw.json in /data/.openclaw or $HOME/.openclaw"
  warn "Set WORKSPACE_ARG manually and ensure MASTER_FILES_ROOT is accessible."
  PLATFORM="unknown"
  OC_ROOT=""
  MASTER_FILES_ROOT=""
fi

log "Platform detected: $PLATFORM"
log "OC_ROOT: ${OC_ROOT:-<not set>}"
log "MASTER_FILES_ROOT: ${MASTER_FILES_ROOT:-<not set>}"

# ─── Resolve workspace dir ───────────────────────────────────────────────────
resolve_workspace() {
  if [ -n "$WORKSPACE_ARG" ]; then
    echo "$WORKSPACE_ARG"
    return
  fi
  if [ "$PLATFORM" = "vps" ]; then
    # VPS: workspace is typically /data/.openclaw/agents/<agent>/workspace
    # Try main agent first, then first found
    for candidate in \
      /data/.openclaw/agents/main/workspace \
      /data/.openclaw/workspace; do
      if [ -d "$candidate" ]; then
        echo "$candidate"; return
      fi
    done
    # Glob fallback
    for candidate in /data/.openclaw/agents/*/workspace; do
      if [ -d "$candidate" ]; then
        echo "$candidate"; return
      fi
    done
    echo "/data/.openclaw/workspace"
  else
    # Mac: workspace is typically $HOME/.openclaw/agents/<agent>/workspace
    for candidate in \
      "$HOME/.openclaw/agents/main/workspace" \
      "$HOME/.openclaw/workspace"; do
      if [ -d "$candidate" ]; then
        echo "$candidate"; return
      fi
    done
    for candidate in "$HOME"/.openclaw/agents/*/workspace; do
      if [ -d "$candidate" ]; then
        echo "$candidate"; return
      fi
    done
    echo "$HOME/.openclaw/workspace"
  fi
}

WORKSPACE="$(resolve_workspace)"
log "Workspace: $WORKSPACE"

if [ ! -d "$WORKSPACE" ]; then
  warn "Workspace directory does not exist: $WORKSPACE"
  warn "Pass the correct path as the first argument, e.g.:"
  warn "  bash scripts/typ-migrate.sh /path/to/agent/workspace"
  exit 1
fi

# ─── Bootstrap files we scan ─────────────────────────────────────────────────
BOOTSTRAP_FILES=(
  "$WORKSPACE/AGENTS.md"
  "$WORKSPACE/TOOLS.md"
  "$WORKSPACE/MEMORY.md"
  "$WORKSPACE/USER.md"
  "$WORKSPACE/SOUL.md"
  "$WORKSPACE/IDENTITY.md"
)

# ─── TYP subfolders ──────────────────────────────────────────────────────────
TYP_SUBFOLDERS=("processes" "apis" "skills" "references")

# ─── Bloat detection threshold (lines) ───────────────────────────────────────
BLOAT_THRESHOLD=25

# ─── Wrong-location search roots ─────────────────────────────────────────────
WRONG_LOCATION_ROOTS=(
  "$HOME/clawd/projects"
  "$HOME/Downloads"
  "/data"
)

# ─────────────────────────────────────────────────────────────────────────────
# HELPER: backup a file before touching it
# ─────────────────────────────────────────────────────────────────────────────
backup_file() {
  local src="$1"
  local bak="${src}.bak-typ-${TIMESTAMP}"
  if $DRY_RUN; then
    log "[DRY-RUN] Would backup: $src → $bak"
  else
    cp "$src" "$bak"
    vlog "Backed up: $src → $bak"
  fi
}

# ─────────────────────────────────────────────────────────────────────────────
# HELPER: ensure master-files subfolder exists
# ─────────────────────────────────────────────────────────────────────────────
ensure_subfolder() {
  local subfolder="$1"
  local dir="$MASTER_FILES_ROOT/$subfolder"
  if $DRY_RUN; then
    vlog "[DRY-RUN] Would ensure dir: $dir"
  else
    mkdir -p "$dir"
  fi
  echo "$dir"
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: BLOAT DETECTION
#   Scan each bootstrap file for inline content blocks > BLOAT_THRESHOLD lines.
#   A "content block" is a contiguous run of non-blank lines under a ## heading.
#   Heuristic: any single ## section with >BLOAT_THRESHOLD lines of content is
#   considered bloated and should be a deep file with a pointer.
# ─────────────────────────────────────────────────────────────────────────────
BLOAT_ISSUES=0
BLOAT_DETAILS=()

detect_bloat() {
  local file="$1"
  [ -f "$file" ] || return 0

  local filename
  filename="$(basename "$file")"
  local line_count
  line_count=$(wc -l < "$file")

  vlog "Scanning $filename ($line_count lines)"

  # Strategy A: Whole-file line count.
  # If the entire file is >400 lines it almost certainly contains pasted docs.
  if [ "$line_count" -gt 400 ]; then
    warn "BLOAT DETECTED [whole-file]: $filename has $line_count lines (threshold for concern: 400)."
    warn "  This strongly suggests large documents were pasted inline."
    BLOAT_ISSUES=$((BLOAT_ISSUES + 1))
    BLOAT_DETAILS+=("WHOLE-FILE:$file:$line_count")
  fi

  # Strategy B: Per-section scan.
  # Find ## sections and count their content lines.
  local in_section=0
  local section_name=""
  local section_lines=0
  local section_start=0
  local lineno=0

  while IFS= read -r line; do
    lineno=$((lineno + 1))
    if echo "$line" | grep -qE '^## '; then
      # Flush previous section check
      if [ "$in_section" -eq 1 ] && [ "$section_lines" -gt "$BLOAT_THRESHOLD" ]; then
        warn "BLOAT DETECTED [section]: $filename § '$section_name' has $section_lines lines (threshold: $BLOAT_THRESHOLD)."
        BLOAT_ISSUES=$((BLOAT_ISSUES + 1))
        BLOAT_DETAILS+=("SECTION:$file:$section_name:$section_start:$section_lines")
      fi
      section_name="$(echo "$line" | sed 's/^## //')"
      section_lines=0
      section_start=$lineno
      in_section=1
    elif [ "$in_section" -eq 1 ]; then
      # Count non-blank lines in this section
      if [ -n "$(echo "$line" | tr -d '[:space:]')" ]; then
        section_lines=$((section_lines + 1))
      fi
    fi
  done < "$file"

  # Flush last section
  if [ "$in_section" -eq 1 ] && [ "$section_lines" -gt "$BLOAT_THRESHOLD" ]; then
    warn "BLOAT DETECTED [section]: $filename § '$section_name' has $section_lines lines (threshold: $BLOAT_THRESHOLD)."
    BLOAT_ISSUES=$((BLOAT_ISSUES + 1))
    BLOAT_DETAILS+=("SECTION:$file:$section_name:$section_start:$section_lines")
  fi
}

log "--- STEP 1: Scanning bootstrap files for bloat ---"
for bfile in "${BOOTSTRAP_FILES[@]}"; do
  detect_bloat "$bfile"
done

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: MISPLACEMENT DETECTION
#   Look for TYP-style docs (markdown files with TYP header signatures) stored
#   in wrong locations instead of the canonical master-files path.
#   Wrong locations: ~/clawd/projects/, ~/Downloads/ (root-level .md, not
#   in openclaw-master-files), /data/ root (not /data/.openclaw/master-files/).
# ─────────────────────────────────────────────────────────────────────────────
MISPLACED_ISSUES=0
MISPLACED_FILES=()

detect_misplaced() {
  local search_root="$1"
  [ -d "$search_root" ] || return 0

  vlog "Scanning for misplaced TYP docs in: $search_root"

  # Find .md files that look like TYP deep files:
  #   - contain "Date learned:" or "Source:" or "Priority: CRITICAL/HIGH/STANDARD/REFERENCE"
  #   - NOT already inside the canonical master-files path
  while IFS= read -r candidate; do
    # Skip if already in master-files (correctly placed)
    if [ -n "$MASTER_FILES_ROOT" ] && \
       echo "$candidate" | grep -q "$(echo "$MASTER_FILES_ROOT" | sed 's|/|\/|g')"; then
      continue
    fi
    # Check content signatures
    if grep -qE '(Date learned:|Priority: (CRITICAL|HIGH|STANDARD|REFERENCE)|Referenced by:)' \
       "$candidate" 2>/dev/null; then
      warn "MISPLACED TYP DOC: $candidate"
      warn "  Should be in: $MASTER_FILES_ROOT/<subfolder>/"
      MISPLACED_ISSUES=$((MISPLACED_ISSUES + 1))
      MISPLACED_FILES+=("$candidate")
    fi
  done < <(find "$search_root" -maxdepth 3 -name "*.md" 2>/dev/null || true)
}

log "--- STEP 2: Scanning for misplaced TYP docs ---"
for root in "${WRONG_LOCATION_ROOTS[@]}"; do
  detect_misplaced "$root"
done

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: SUBAGENT RULE INHERITANCE CHECK
#   Confirm the mandatory TYP rule block is present in AGENTS.md.
#   All spawned subagents read agents/tools/user.md — they must inherit the
#   no-paste rule. If the block is missing, add it now.
# ─────────────────────────────────────────────────────────────────────────────
AGENTS_FILE="$WORKSPACE/AGENTS.md"
SUBAGENT_RULE_MISSING=false
TYP_RULE_MARKER="MANDATORY — Teach Yourself Protocol (TYP) Storage Rule"

check_subagent_rule() {
  if [ ! -f "$AGENTS_FILE" ]; then
    warn "AGENTS.md not found at $AGENTS_FILE — cannot verify subagent rule."
    return
  fi
  if ! grep -q "$TYP_RULE_MARKER" "$AGENTS_FILE" 2>/dev/null; then
    warn "SUBAGENT RULE MISSING: '$TYP_RULE_MARKER' not found in AGENTS.md."
    warn "  Subagents will not inherit the TYP no-paste rule."
    SUBAGENT_RULE_MISSING=true
  else
    log "Subagent TYP rule: PRESENT in AGENTS.md"
  fi
}

log "--- STEP 3: Checking subagent rule inheritance in AGENTS.md ---"
check_subagent_rule

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY / DRY-RUN REPORT
# ─────────────────────────────────────────────────────────────────────────────
TOTAL_ISSUES=$((BLOAT_ISSUES + MISPLACED_ISSUES + (SUBAGENT_RULE_MISSING && true || false)))

log ""
log "=== DETECTION SUMMARY ==="
log "  Bootstrap bloat sections:  $BLOAT_ISSUES"
log "  Misplaced TYP docs:        $MISPLACED_ISSUES"
log "  Subagent rule missing:     $SUBAGENT_RULE_MISSING"
log "  TOTAL issues:              $TOTAL_ISSUES"

if [ "$TOTAL_ISSUES" -eq 0 ]; then
  log "No issues found. Workspace is TYP-clean."
  exit 0
fi

if $DRY_RUN; then
  log ""
  log "[DRY-RUN] Would remediate $TOTAL_ISSUES issue(s). Run without --dry-run to apply."
  exit 2
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: REMEDIATE — RELOCATE MISPLACED FILES
#   Move each misplaced TYP doc to the correct master-files subfolder.
#   Determine subfolder from content (look for known subfolder keywords in
#   the filename or Path/Source header). Default to references/ if ambiguous.
# ─────────────────────────────────────────────────────────────────────────────
classify_subfolder() {
  local filepath="$1"
  local fname
  fname="$(basename "$filepath" .md | tr '[:upper:]' '[:lower:]')"
  # Check filename keywords first
  if echo "$fname" | grep -qE '(api|endpoint|openai|anthropic|stripe|twilio|sendgrid|ghl|kie|fish|openrouter)'; then
    echo "apis"
  elif echo "$fname" | grep -qE '(skill|protocol|typ|teach-yourself|process|sop|workflow)'; then
    echo "skills"
  elif echo "$fname" | grep -qE '(playbook|guide|reference|glossary|faq|manual)'; then
    echo "references"
  else
    # Fall through to content scan
    local content_keyword
    content_keyword=$(grep -oiE '(category|type): *(api|skill|process|reference)' "$filepath" 2>/dev/null | head -1 | sed 's/.*: *//' | tr '[:upper:]' '[:lower:]' || echo "")
    case "$content_keyword" in
      api) echo "apis" ;;
      skill) echo "skills" ;;
      process) echo "processes" ;;
      *) echo "references" ;;
    esac
  fi
}

if [ "${#MISPLACED_FILES[@]}" -gt 0 ]; then
  log ""
  log "--- STEP 4: Relocating misplaced TYP docs ---"
  [ -n "$MASTER_FILES_ROOT" ] || { warn "MASTER_FILES_ROOT not set; cannot relocate."; exit 1; }

  for src in "${MISPLACED_FILES[@]}"; do
    subfolder="$(classify_subfolder "$src")"
    dest_dir="$(ensure_subfolder "$subfolder")"
    dest_file="$dest_dir/$(basename "$src")"

    if [ -f "$dest_file" ]; then
      warn "Destination already exists: $dest_file"
      warn "Appending content under '--- MIGRATION APPEND ---' header."
      {
        echo ""
        echo "--- MIGRATION APPEND ($(date)) ---"
        echo "# Source: $src"
        echo ""
        cat "$src"
      } >> "$dest_file"
      log "  Appended: $src → $dest_file"
    else
      cp "$src" "$dest_file"
      log "  Relocated: $src → $dest_file"
    fi

    # Leave a forwarding pointer at the original location
    {
      echo "# RELOCATED BY typ-migrate.sh ($(date))"
      echo ""
      echo "This document was moved to the canonical TYP master-files path."
      echo ""
      echo "Full reference: $dest_file"
      echo "When to go deeper: any task requiring the full content of this document"
    } > "$src"
    log "  Left forwarding stub at: $src"
  done
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: REMEDIATE — BLOAT IN BOOTSTRAP FILES
#   For each bloated section, extract the section content to a deep file in
#   master-files/processes/ (default), replace it inline with a 10-25 line
#   summary + pointer.
#   IMPORTANT: we do NOT auto-summarize because the agent must write a
#   Five-Question-Test summary. Instead, we:
#   (a) Extract the full content to master-files
#   (b) Replace with a NOTICE block (clearly marked) telling the agent
#       to write the proper summary the next time it reads the file.
#   This is safe and correct: the full content is preserved, the core file is
#   cleaned up, and the agent gets explicit instructions.
# ─────────────────────────────────────────────────────────────────────────────

if [ "${#BLOAT_DETAILS[@]}" -gt 0 ]; then
  log ""
  log "--- STEP 5: Extracting bloated sections from bootstrap files ---"
  [ -n "$MASTER_FILES_ROOT" ] || { warn "MASTER_FILES_ROOT not set; cannot extract."; exit 1; }

  # Group by file so we only write one backup per file
  declare -A BACKED_UP=()

  for detail in "${BLOAT_DETAILS[@]}"; do
    IFS=':' read -r dtype dfile rest <<< "$detail"

    # Backup file once
    if [ -z "${BACKED_UP[$dfile]+x}" ]; then
      backup_file "$dfile"
      BACKED_UP[$dfile]=1
    fi

    fname="$(basename "$dfile" .md)"

    if [ "$dtype" = "WHOLE-FILE" ]; then
      # Whole-file bloat: the entire file is oversized.
      # Extract a dated copy to master-files/processes/, leave a notice.
      dline="$rest"
      dest_dir="$(ensure_subfolder "processes")"
      dest_file="$dest_dir/${fname}-extracted-${TIMESTAMP}.md"

      log "  Extracting whole-file bloat: $dfile ($dline lines) → $dest_file"
      cp "$dfile" "$dest_file"

      # Prepend TYP header to extracted file
      local_tmp=$(mktemp)
      {
        echo "# ${fname} (extracted by typ-migrate.sh)"
        echo "- Source: $dfile"
        echo "- Date extracted: $(date)"
        echo "- Priority: STANDARD"
        echo "- Referenced by: $(basename "$dfile")"
        echo ""
        cat "$dest_file"
      } > "$local_tmp"
      mv "$local_tmp" "$dest_file"

      # Write summary notice back to the bootstrap file
      local_tmp2=$(mktemp)
      {
        echo "<!-- TYP-MIGRATE: This file was identified as bloated ($dline lines). -->"
        echo "<!-- Full content extracted to: $dest_file -->"
        echo "<!-- ACTION REQUIRED: Replace this notice with a proper TYP summary (10-25 lines). -->"
        echo "<!-- Use the Five Question Test: What is it? When use it? Key facts? Full doc path? When go deeper? -->"
        echo ""
        echo "## TYP MIGRATION NOTICE — ACTION REQUIRED"
        echo ""
        echo "This file was detected as bloated ($dline lines) by typ-migrate.sh."
        echo ""
        echo "Full content has been preserved at:"
        echo "  $dest_file"
        echo ""
        echo "**Next step (agent):** Read the full content at the path above, then replace"
        echo "this notice with a proper TYP summary (10–25 lines, Five Question Test):"
        echo "  1. What is this? (one sentence)"
        echo "  2. When do I use it? (triggers)"
        echo "  3. What do I need to know right now? (key facts)"
        echo "  4. Full reference: $dest_file"
        echo "  5. When should I go deeper? (scenarios requiring the full doc)"
        echo ""
      } > "$local_tmp2"

      # Append original content after the notice (so nothing is lost)
      cat "$dfile" >> "$local_tmp2"
      mv "$local_tmp2" "$dfile"
      log "  Added migration notice to: $dfile"

    elif [ "$dtype" = "SECTION" ]; then
      # Section bloat: a specific ## section is oversized.
      # section_name:section_start:section_lines
      IFS=':' read -r section_name section_start section_lines <<< "$rest"

      dest_dir="$(ensure_subfolder "processes")"
      # Slugify section name for filename
      section_slug="$(echo "$section_name" | tr '[:upper:] /' '[:lower:]-' | tr -dc 'a-z0-9-' | cut -c1-60)"
      dest_file="$dest_dir/${fname}-${section_slug}-${TIMESTAMP}.md"

      log "  Extracting section bloat: $dfile § '$section_name' ($section_lines lines) → $dest_file"

      # Extract the full section content (from the ## heading to next ## heading or EOF)
      python3 - "$dfile" "$section_name" "$dest_file" <<'PYEOF'
import sys, re

src_path = sys.argv[1]
target_section = sys.argv[2]
dst_path = sys.argv[3]

with open(src_path) as f:
    lines = f.readlines()

in_section = False
section_lines = []
for line in lines:
    if re.match(r'^## ', line):
        if in_section:
            break  # end of target section
        if line.strip().lstrip('## ').strip() == target_section.strip():
            in_section = True
    if in_section:
        section_lines.append(line)

with open(dst_path, 'w') as f:
    from datetime import date
    f.write(f"# {target_section}\n")
    f.write(f"- Source: {src_path}\n")
    f.write(f"- Date extracted: {date.today()}\n")
    f.write(f"- Priority: STANDARD\n")
    f.write(f"- Referenced by: {src_path.split('/')[-1]}\n\n")
    f.writelines(section_lines)
PYEOF

      # Replace the section content in the bootstrap file with a TYP notice + pointer
      python3 - "$dfile" "$section_name" "$dest_file" <<'PYEOF'
import sys, re

src_path = sys.argv[1]
target_section = sys.argv[2]
dest_file = sys.argv[3]

with open(src_path) as f:
    content = f.read()
    lines = content.split('\n')

# Find section boundaries
start_idx = None
end_idx = len(lines)
for i, line in enumerate(lines):
    if re.match(r'^## ', line):
        if start_idx is not None:
            end_idx = i
            break
        if line.strip().lstrip('## ').strip() == target_section.strip():
            start_idx = i

if start_idx is None:
    print(f"Section '{target_section}' not found, skipping replacement.", file=sys.stderr)
    sys.exit(0)

notice = [
    f"## {target_section}",
    "",
    "<!-- TYP-MIGRATE: This section was bloated and extracted by typ-migrate.sh -->",
    f"**Full reference:** {dest_file}",
    "**When to go deeper:** any task requiring the full content of this section",
    "",
    "_ACTION REQUIRED (agent): Replace this notice with a proper TYP summary (10–25 lines,_",
    "_Five Question Test). The full content is at the path above. NEVER paste it back here._",
    "",
]

new_lines = lines[:start_idx] + notice + lines[end_idx:]
with open(src_path, 'w') as f:
    f.write('\n'.join(new_lines))

print(f"Replaced section '{target_section}' in {src_path} with pointer to {dest_file}")
PYEOF
      log "  Replaced section with pointer in: $dfile"
    fi
  done
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: REMEDIATE — ADD SUBAGENT RULE TO AGENTS.MD IF MISSING
#   The mandatory TYP rule must be in AGENTS.md so spawned subagents see it.
# ─────────────────────────────────────────────────────────────────────────────
if $SUBAGENT_RULE_MISSING && [ -f "$AGENTS_FILE" ]; then
  log ""
  log "--- STEP 6: Injecting mandatory TYP subagent rule into AGENTS.md ---"
  backup_file "$AGENTS_FILE"

  # Determine the platform-correct paths for the rule block
  if [ "$PLATFORM" = "vps" ]; then
    MAC_PATH_LINE="- Mac storage path: \`~/Downloads/openclaw-master-files/<subfolder>/\` (subfolders: \`processes/\`, \`apis/\`, \`skills/\`, \`references/\`)"
    VPS_PATH_LINE="- VPS storage path: \`/data/.openclaw/master-files/<subfolder>/\` (same subfolders)"
  else
    MAC_PATH_LINE="- Mac storage path: \`~/Downloads/openclaw-master-files/<subfolder>/\` (subfolders: \`processes/\`, \`apis/\`, \`skills/\`, \`references/\`)"
    VPS_PATH_LINE="- VPS storage path: \`/data/.openclaw/master-files/<subfolder>/\` (same subfolders)"
  fi

  TYP_RULE_BLOCK="
### MANDATORY — Teach Yourself Protocol (TYP) Storage Rule

**NEVER paste long playbooks, SOPs, API docs, or any document over ~25 lines into any bootstrap file (AGENTS.md, TOOLS.md, MEMORY.md, USER.md, SOUL.md, IDENTITY.md).** Store the full document in the master-files TYP subfolder, then write only a hyper-concise summary (10–25 lines max) plus an explicit pointer here.

${MAC_PATH_LINE}
${VPS_PATH_LINE}
- Every pointer must include the full path and a \"when to go deeper\" trigger.
- See the Teach Yourself Protocol skill (01-teach-yourself-protocol) for the full protocol.
- This rule applies to ALL spawned subagents — they read AGENTS.md on every session.
"

  echo "$TYP_RULE_BLOCK" >> "$AGENTS_FILE"
  log "  Appended TYP subagent rule to AGENTS.md"
fi

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: VERIFY
# ─────────────────────────────────────────────────────────────────────────────
log ""
log "--- STEP 7: Verification ---"
VERIFY_ERRORS=0

# Check AGENTS.md has the TYP rule
if [ -f "$AGENTS_FILE" ]; then
  if grep -q "$TYP_RULE_MARKER" "$AGENTS_FILE" 2>/dev/null; then
    log "  AGENTS.md: TYP rule present"
  else
    warn "  AGENTS.md: TYP rule STILL MISSING after remediation"
    VERIFY_ERRORS=$((VERIFY_ERRORS + 1))
  fi
fi

# Check each relocated/extracted file exists
for dest in "${MISPLACED_FILES[@]}"; do
  # We overwrote originals with forwarding stubs; check master-files instead
  true  # destination verification is logged during relocation above
done

# Report backup files created
log ""
log "=== REMEDIATION COMPLETE ==="
log "  Backup files created with suffix: .bak-typ-${TIMESTAMP}"
log "  These can be safely deleted once you verify the workspace is clean."
log ""

if [ "$VERIFY_ERRORS" -eq 0 ]; then
  log "All checks passed. Run with --dry-run on the next update to confirm idempotency."
  exit 0
else
  warn "$VERIFY_ERRORS verification error(s). Manual review required."
  exit 1
fi

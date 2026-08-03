#!/usr/bin/env bash
# 04-update-core-files.sh -- Skill 41 Build With AI Playbook Generator
#
# The SINGLE canonical writer of the AGENTS.md / MEMORY.md / TOOLS.md pointer
# blocks. Each block sits behind a VERSION-FREE BEGIN/END marker and is written
# REPLACE-IN-PLACE (a MARKER-REFRESH writer): a re-run — including after a version
# bump — overwrites the block in place instead of appending a duplicate, and any
# LEGACY version-stamped variant of the same marker (e.g.
# `<!-- BEGIN skill-41 memory-rules v1.5.8 -->`) is stripped, so a box wired by an
# older version ends up with exactly ONE block after the refresh.
#
# WHY THE REWRITE (two real defects):
#   1. The markers embedded the RUNTIME SKILL VERSION and the "already at current
#      version" guard was `grep -qF "<begin marker with that version>"`. That only
#      protected against re-running THE SAME VERSION; a bump changed the marker and
#      appended a second copy of the same rules.
#   2. The stale-block remover used `grep -qP` — GNU-only. macOS BSD grep has no
#      `-P`, so on every client Mac the removal branch silently evaluated false and
#      the old block was never stripped: the bump path ALWAYS duplicated. The new
#      writer is pure awk and portable.
#
# MEMORY.md gets a TYP POINTER, never the rule corpus: core bootstrap files are
# re-billed to the model on every turn, so the rule text lives in the deep file
# references/memory-design-rules.md, which this script installs into the client's
# master-files folder so the pointer can never dangle.
#
# Backs up each core file ONCE (`<file>.skill41.bak`) rather than writing a new
# timestamped backup on every fleet roll. UNIVERSAL -- no client data.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib-master-files.sh"

SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SKILL_VERSION="$(tr -d '[:space:]' < "$SKILL_DIR/skill-version.txt")"

echo "[skill 41] Updating core files (AGENTS.md, MEMORY.md, TOOLS.md) [skill v${SKILL_VERSION}]..."

# Find workspace root (where AGENTS.md lives)
WORKSPACE_ROOT="${WORKSPACE_ROOT:-${HOME}/clawd}"
if [[ ! -f "$WORKSPACE_ROOT/AGENTS.md" ]]; then
  echo "[skill 41] WARNING: AGENTS.md not found at $WORKSPACE_ROOT/AGENTS.md -- skipping core file updates"
  exit 0
fi

# MARKER-REFRESH writer: strip the version-free block AND any legacy version-stamped
# variant, then append the fresh block. Idempotent and bump-safe.
append_block() { # file marker-id content
  local file="$1" mid="$2" content="$3"
  [[ -f "$file" ]] || { echo "[skill 41] $(basename "$file") missing -- skipping"; return 0; }
  local begin="<!-- BEGIN skill-41 $mid -->" end="<!-- END skill-41 $mid -->"
  [[ -f "$file.skill41.bak" ]] || cp "$file" "$file.skill41.bak" 2>/dev/null || true
  local blk tmp
  blk="$(mktemp)"; tmp="$(mktemp)"
  { printf '%s\n' "$begin"; printf '%s\n' "$content"; printf '%s\n' "$end"; } > "$blk"
  # TRUE replace-in-place: substitute the block where it already sits (version-free
  # marker OR any legacy `<mid> vX.Y.Z` variant), drop further duplicates, and append
  # at EOF only when genuinely absent — so the file stays BYTE-STABLE across re-runs
  # even when several skills write blocks into the same core file.
  awk -v mid="$mid" -v blkfile="$blk" '
    BEGIN { skip = 0; done = 0 }
    {
      if (skip == 0 && $0 ~ ("^<!-- BEGIN skill-41 " mid "( v[0-9][^ ]*)? -->$")) {
        skip = 1
        if (!done) { while ((getline l < blkfile) > 0) print l; close(blkfile); done = 1 }
        next
      }
      if (skip == 1) {
        if ($0 ~ ("^<!-- END skill-41 " mid "( v[0-9][^ ]*)? -->$")) skip = 0
        next
      }
      print
    }
    END { if (!done) { print ""; while ((getline l < blkfile) > 0) print l; close(blkfile) } }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$blk" "$tmp"
  echo "[skill 41] $(basename "$file"): wrote block '$mid' (replace-in-place)"
}

# One-time sweep of the LEGACY generic-installer memory stub for this skill, which
# carried the same rule corpus under a different marker family and so survived every
# marker-refresh. Same namespace — a self-clean, not a cross-writer edit.
strip_legacy_stub() { # file
  local file="$1" tmp
  [[ -f "$file" ]] || return 0
  grep -qF '<!-- BEGIN skill:41-build-with-ai-playbook:memory -->' "$file" 2>/dev/null || return 0
  tmp="$(mktemp)"
  awk '
    BEGIN { skip = 0 }
    {
      if (skip == 0 && $0 ~ /^<!-- BEGIN skill:41-build-with-ai-playbook:memory -->$/) { skip = 1; next }
      if (skip == 1) { if ($0 ~ /^<!-- END skill:41-build-with-ai-playbook:memory -->$/) skip = 0; next }
      print
    }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  echo "[skill 41] $(basename "$file"): removed legacy generic-installer memory stub"
}

# The legacy AGENTS.md marker used a different shape (`SKILL41: BUILD_WITH_AI`).
# Strip it once so the refreshed, version-free block is the only one left.
strip_legacy_agents_marker() {
  local file="$1" tmp
  grep -qF '<!-- BEGIN SKILL41: BUILD_WITH_AI -->' "$file" 2>/dev/null || return 0
  tmp="$(mktemp)"
  awk '
    BEGIN { skip = 0 }
    {
      if (skip == 0 && $0 ~ /^<!-- BEGIN SKILL41: BUILD_WITH_AI -->$/) { skip = 1; next }
      if (skip == 1 && $0 ~ /^<!-- END SKILL41: BUILD_WITH_AI -->$/)   { skip = 0; next }
      if (skip == 0) print
    }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  echo "[skill 41] $(basename "$file"): removed legacy SKILL41: BUILD_WITH_AI block"
}

# ── Master-files root + the MEMORY.md pointer target ─────────────────────────
MFD="$(resolve_master_files_dir)"
SKILL_DEST="$MFD/41-build-with-ai-playbook"
RULES_SRC="$SKILL_DIR/references/memory-design-rules.md"
RULES_DEST="$SKILL_DEST/references/memory-design-rules.md"
if [[ -f "$RULES_SRC" && "$SKILL_DIR" != "$SKILL_DEST" ]]; then
  mkdir -p "$SKILL_DEST/references" 2>/dev/null || true
  if [[ ! -f "$RULES_DEST" || "$RULES_SRC" -nt "$RULES_DEST" ]]; then
    cp "$RULES_SRC" "$RULES_DEST" 2>/dev/null && echo "[skill 41] installed rule reference -> $RULES_DEST"
  fi
fi

# ---- AGENTS.md ----
strip_legacy_agents_marker "$WORKSPACE_ROOT/AGENTS.md"
append_block "$WORKSPACE_ROOT/AGENTS.md" "build-with-ai" \
"Build With AI: when the operator asks to build a GoHighLevel or Convert and Flow workflow or automation using AI, do not answer from memory. Read the playbook at MASTER_FILES_DIR/build-with-ai-playbook.md and follow it to the letter. Create the required tags, custom fields, and custom values FIRST. Full protocol: protocols/build-with-ai-protocol.md (skill-bundled)."

# ---- MEMORY.md ----
strip_legacy_stub "$WORKSPACE_ROOT/MEMORY.md"
append_block "$WORKSPACE_ROOT/MEMORY.md" "memory-rules" \
"## Skill 41 — Build With AI design rules [PRIORITY: HIGH]
- **WHAT:** 7 binding rules — Dependency-First, No-Fabrication, ZHC-Prefix, Verification,
  Event-Log, Conversation-Pairing, Operator-Approval.
- **WHEN (trigger):** before generating any Build-with-AI prompt, creating any tag / custom
  field / custom value, or publishing a built workflow. Read the rules; never work from memory.
- **WHY:** hard constraints — dependencies exist BEFORE the prompt names them, no invented
  triggers or actions, agent tags are \`ZHC-\` and fields \`ZHC_\`, the 12-point checklist runs
  before publish, dependency creation is OPERATOR-approved only.
- **Full text / go deeper:** $RULES_DEST
  (per-rule deep specs: $SKILL_DEST/protocols/)"

# ---- TOOLS.md ----
append_block "$WORKSPACE_ROOT/TOOLS.md" "tools" \
"Build With AI quick-reference:
- Prompt template: templates/build-with-ai-prompt-template.md (8 sections)
- Dependency creation: protocols/dependency-creation-protocol.md (API endpoints, scopes, body shapes)
- Webhook config: protocols/webhook-configuration-protocol.md (CUSTOM/POST/GET modes, headers, raw JSON)
- Verification checklist: protocols/verification-checklist.md (12 points)
- GHL triggers: references/ghl-triggers-catalog.md (14 categories)
- GHL actions: references/ghl-actions-catalog.md (14 categories)
- Design rules (full text): references/memory-design-rules.md
- Event logging: scripts/lib-master-files.sh append_jsonl <type> <json>
- No keys, no client data -- UNIVERSAL."

echo "[skill 41] Core file updates complete (idempotent replace-in-place)"
exit 0

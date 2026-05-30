#!/usr/bin/env bash
# 05-install-sales-brain-extension.sh — Skill 39
# ADDITIVE drop-in of the RE Sales-Brain extension into the client's installed
# Skill 38. THIS NEVER OVERWRITES Skill 38's own sales-best-practices-protocol.md.
# It:
#   1. Copies references/sales-brain-real-estate-extension.md → Skill 38's
#      protocols/ as a NEW file (sales-best-practices-real-estate-extension.md).
#   2. Verifies Skill 38's own protocol file is byte-unchanged (hash compare).
#   3. Appends ONE pointer line to AGENTS.md behind a BEGIN/END marker.
#   4. Emits a sales_brain_extension_installed event.
# Idempotent (diffs the file + checks the marker).

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
P="[skill 39][sales-brain-ext]"

OS="$(uname -s)"
case "$OS" in
  Darwin) DEFAULT_SKILLS_DIR="$HOME/.openclaw/skills" ;;
  *)      DEFAULT_SKILLS_DIR="/data/.openclaw/skills" ;;
esac
SKILLS_DIR="${OPENCLAW_SKILLS_DIR:-$DEFAULT_SKILLS_DIR}"
S38="$SKILLS_DIR/38-conversational-ai-system"
S38_PROTO_DIR="$S38/protocols"
S38_OWN="$S38_PROTO_DIR/sales-best-practices-protocol.md"
EXT_SRC="$SKILL_ROOT/references/sales-brain-real-estate-extension.md"
EXT_DST="$S38_PROTO_DIR/sales-best-practices-real-estate-extension.md"

if [ ! -d "$S38_PROTO_DIR" ]; then
  echo "$P BLOCKED: Skill 38 protocols dir not found at $S38_PROTO_DIR — install Skill 38 first."
  exit 1
fi
[ -f "$EXT_SRC" ] || { echo "$P BLOCKED: extension source missing: $EXT_SRC"; exit 1; }

# Snapshot Skill 38's own protocol hash BEFORE we touch anything.
own_before=""
[ -f "$S38_OWN" ] && own_before="$(shasum "$S38_OWN" 2>/dev/null | awk '{print $1}')"

# 1+2. Install the extension as a NEW file (never the own protocol).
if [ -f "$EXT_DST" ] && cmp -s "$EXT_SRC" "$EXT_DST"; then
  echo "$P extension already current: $EXT_DST"
else
  cp "$EXT_SRC" "$EXT_DST" && echo "$P installed RE Sales-Brain extension (NEW file): $EXT_DST"
fi

# Verify Skill 38's own protocol is byte-unchanged.
own_after=""
[ -f "$S38_OWN" ] && own_after="$(shasum "$S38_OWN" 2>/dev/null | awk '{print $1}')"
if [ -n "$own_before" ] && [ "$own_before" != "$own_after" ]; then
  echo "$P FATAL: Skill 38's own sales-best-practices-protocol.md changed — aborting (additive rule violated)."
  exit 1
fi
echo "$P verified: Skill 38's own sales-best-practices-protocol.md is UNTOUCHED."

# 3. Append the AGENTS.md pointer behind a marker (idempotent).
MARKER_BEGIN="<!-- BEGIN skill-39 sales-brain-re-extension -->"
MARKER_END="<!-- END skill-39 sales-brain-re-extension -->"
AGENTS=""
for cand in "$SKILLS_DIR/../AGENTS.md" "$HOME/.openclaw/AGENTS.md" "$HOME/clawd/AGENTS.md" "/data/.openclaw/AGENTS.md"; do
  [ -f "$cand" ] && { AGENTS="$cand"; break; }
done
marker_added="false"
if [ -n "$AGENTS" ]; then
  if grep -qF "$MARKER_BEGIN" "$AGENTS" 2>/dev/null; then
    echo "$P AGENTS.md pointer already present in $AGENTS"
    marker_added="true"
  else
    cp "$AGENTS" "$AGENTS.skill39.bak" 2>/dev/null || true
    {
      printf '\n%s\n' "$MARKER_BEGIN"
      echo "When the conversation is in a REAL-ESTATE sales context, ALSO load"
      echo "\`38-conversational-ai-system/protocols/sales-best-practices-real-estate-extension.md\`"
      echo "(installed additively by Skill 39 — RE objection patterns, CMA pricing-reveal timing, SPICED-RE)."
      echo "This EXTENDS, never replaces, Skill 38's \`sales-best-practices-protocol.md\`."
      printf '%s\n' "$MARKER_END"
    } >> "$AGENTS"
    echo "$P appended AGENTS.md pointer to $AGENTS (backup: $AGENTS.skill39.bak)"
    marker_added="true"
  fi
else
  echo "$P WARN: AGENTS.md not found in known locations — add the pointer manually (see CORE_UPDATES.md)."
fi

# 4. Emit the event.
MASTER_FILES_DIR="${MASTER_FILES_DIR:-}" bash "$SCRIPT_DIR/lib-re-events.sh" re_event sales_brain_extension_installed \
  "$(printf '{"lead_ref":"n/a","source":"none","target_skill38_path":"%s","marker_added":%s}' "$EXT_DST" "$marker_added")" \
  && echo "$P emitted sales_brain_extension_installed event" || true

echo "$P Done. Re-run is idempotent."
exit 0

#!/usr/bin/env bash
# 07-update-core-files.sh — Skill 40
# The SINGLE canonical writer of the AGENTS.md / MEMORY.md / TOOLS.md pointer
# blocks. Each block sits behind a VERSION-FREE BEGIN/END marker and is written
# REPLACE-IN-PLACE (a MARKER-REFRESH writer): a re-run — including after a version
# bump — overwrites the block in place instead of appending a duplicate, and any
# LEGACY version-stamped variant of the same marker (e.g.
# `<!-- BEGIN skill-40 memory-rules v1.0.0 -->`) is stripped, so a box wired by an
# older version ends up with exactly ONE block after the refresh.
#
# WHY THE REWRITE: the previous writer used version-stamped markers plus a
# `grep -qF "<exact begin marker>"` guard. That guard only protected against
# re-running THE SAME VERSION — the next version bump changed the marker string,
# the guard passed, and a SECOND copy of the same rules was appended, with nothing
# removing the first. Idempotency is now a property of the WRITER, not of a string
# literal, so a rename can no longer create a duplicate.
#
# MEMORY.md gets a TYP POINTER, never the rule corpus: core bootstrap files are
# re-billed to the model on every turn, so the rule text lives in the deep file
# references/memory-design-rules.md, which this script installs into the client's
# master-files folder so the pointer can never dangle.
#
# Backs up each core file before its first edit. UNIVERSAL — no client data.

set -uo pipefail
P="[skill 40][core-files]"
OS="$(uname -s)"
case "$OS" in
  Darwin) ROOTS=( "$HOME/.openclaw" "$HOME/clawd" ) ;;
  *)      ROOTS=( "/data/.openclaw" "/data/clawd" "$HOME/.openclaw" ) ;;
esac

find_core() { local name="$1" r; for r in "${ROOTS[@]}"; do [ -f "$r/$name" ] && { echo "$r/$name"; return 0; }; done; return 1; }

# MARKER-REFRESH writer: remove any existing block for this VERSION-FREE marker id
# (and any legacy `<mid> vX.Y.Z` variant), then append the fresh block. Idempotent
# and bump-safe: never leaves a duplicate behind.
append_block() { # file marker-id content
  local file="$1" mid="$2" content="$3"
  local begin="<!-- BEGIN skill-40 $mid -->" end="<!-- END skill-40 $mid -->"
  [ -f "$file.skill40.bak" ] || cp "$file" "$file.skill40.bak" 2>/dev/null || true
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
      if (skip == 0 && $0 ~ ("^<!-- BEGIN skill-40 " mid "( v[0-9][^ ]*)? -->$")) {
        skip = 1
        if (!done) { while ((getline l < blkfile) > 0) print l; close(blkfile); done = 1 }
        next
      }
      if (skip == 1) {
        if ($0 ~ ("^<!-- END skill-40 " mid "( v[0-9][^ ]*)? -->$")) skip = 0
        next
      }
      print
    }
    END { if (!done) { print ""; while ((getline l < blkfile) > 0) print l; close(blkfile) } }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$blk" "$tmp"
  echo "$P $(basename "$file"): wrote block '$mid' (replace-in-place)"
}

# One-time sweep of the LEGACY generic-installer memory stub for this skill, which
# carried the same rule corpus under a different marker family and so survived every
# marker-refresh. Same namespace — a self-clean, not a cross-writer edit.
strip_legacy_stub() { # file
  local file="$1" tmp
  [ -f "$file" ] || return 0
  grep -qF '<!-- BEGIN skill:40-zhc-public-records-scraper:memory -->' "$file" 2>/dev/null || return 0
  tmp="$(mktemp)"
  awk '
    BEGIN { skip = 0 }
    {
      if (skip == 0 && $0 ~ /^<!-- BEGIN skill:40-zhc-public-records-scraper:memory -->$/) { skip = 1; next }
      if (skip == 1) { if ($0 ~ /^<!-- END skill:40-zhc-public-records-scraper:memory -->$/) skip = 0; next }
      print
    }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  echo "$P $(basename "$file"): removed legacy generic-installer memory stub"
}

# ── Master-files root + the MEMORY.md pointer target ─────────────────────────
# Resolution order mirrors scripts/01-locate-master-files-folder.sh, then the
# platform default used by repo scripts/typ-migrate.sh + apply-fleet-standards.sh.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
resolve_master_files_dir() {
  local s
  [ -n "${MASTER_FILES_DIR:-}" ] && { printf '%s\n' "$MASTER_FILES_DIR"; return 0; }
  for s in "$HOME/.openclaw/.skill-40-master-files-dir" \
           "$HOME/.openclaw/.skill-39-master-files-dir" \
           "$HOME/.openclaw/.skill-38-master-files-dir"; do
    [ -s "$s" ] && { head -n1 "$s"; return 0; }
  done
  if [ -f /data/.openclaw/openclaw.json ]; then
    printf '%s\n' "/data/.openclaw/master-files"
  else
    printf '%s\n' "$HOME/Downloads/openclaw-master-files"
  fi
}
MFD="$(resolve_master_files_dir)"
SKILL_DEST="$MFD/40-zhc-public-records-scraper"
RULES_SRC="$SKILL_ROOT/references/memory-design-rules.md"
RULES_DEST="$SKILL_DEST/references/memory-design-rules.md"
if [ -f "$RULES_SRC" ] && [ "$SKILL_ROOT" != "$SKILL_DEST" ]; then
  mkdir -p "$SKILL_DEST/references" 2>/dev/null || true
  if [ ! -f "$RULES_DEST" ] || [ "$RULES_SRC" -nt "$RULES_DEST" ]; then
    cp "$RULES_SRC" "$RULES_DEST" 2>/dev/null && echo "$P installed rule reference -> $RULES_DEST"
  fi
fi

if AGENTS="$(find_core AGENTS.md)"; then
  append_block "$AGENTS" "public-records" \
"For any public-records query: auto-detect county+state, then route Tier 1 -> Tier 2 -> Tier 3 -> else Tier 4 (honest gap). NEVER fabricate a record; no source -> say so.
- Compliance first: check robots.txt before any fetch; honor each target's ToS (tos_url acknowledged); stamp every record source + retrieved_at. Disallowed/unattributed -> honest gap.
- Cost+rate caps: respect PR_DAILY_CAP + per-target rate limit; bulk ops above PR_BULK_CONFIRM_THRESHOLD need an operator-confirmed cost estimate.
- 30-day cache; --force-refresh to bypass one query.
- RE pairing: surface pre-foreclosure/NOD, tax-delinquency, comps, permits, tax, ownership for Skill 39; Skill 40 never runs outreach.
- Event log: append one line to \$MASTER_FILES_DIR/public-records-queries.jsonl per query/cache-hit/tier-decision/cost-estimate/rate-wait/compliance-block/honest-gap (types + counts only, never raw record contents)."
else
  echo "$P WARN: AGENTS.md not found — add the block manually (see CORE_UPDATES.md)."
fi

if MEM="$(find_core MEMORY.md)"; then
  strip_legacy_stub "$MEM"
  append_block "$MEM" "memory-rules" \
"## Skill 40 — Public-records design rules [PRIORITY: HIGH]
- **WHAT:** 7 binding rules — No-Fabrication, Compliance, Cost-Cap, Cache, Stay-In-Lane,
  Permissible-Use, Event-Log.
- **WHEN (trigger):** before any records lookup, tier decision, bulk run, or
  cache/attribution question. Read the rules; never work from memory.
- **WHY:** hard constraints — no source + retrieved_at means it is not a record, robots.txt
  and ToS bind, caps bind, bulk needs an operator estimate, Skill 40 never runs outreach.
- **Full text / go deeper:** $RULES_DEST
  (per-rule deep specs: $SKILL_DEST/protocols/)"
else
  echo "$P WARN: MEMORY.md not found — add the block manually (see CORE_UPDATES.md)."
fi

if TOOLS="$(find_core TOOLS.md)"; then
  append_block "$TOOLS" "tools" \
"Skill 40 libraries (UNIVERSAL; no keys, no client data):
- scripts/lib-records.sh query \"<address-or-zip>\" \"<record-type>\" [--force-refresh] - tiered router (compliance + cache + honest gap).
- scripts/lib-cost-cap.sh {estimate <n>|under_daily_cap|record_query|rate_wait <target>} - cost+rate guard.
- scripts/lib-pr-events.sh pr_event <type> <json> - append one line to public-records-queries.jsonl.
Caps (env): PR_DAILY_CAP, PR_PER_TARGET_MIN_INTERVAL_S, PR_BULK_CONFIRM_THRESHOLD, PR_COST_PER_QUERY, PR_CACHE_TTL_DAYS."
else
  echo "$P WARN: TOOLS.md not found — add the block manually (see CORE_UPDATES.md)."
fi

echo "$P core-file updates complete (idempotent replace-in-place, backups written before first edit)."
exit 0

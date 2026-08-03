#!/usr/bin/env bash
# 08-update-core-files.sh — Skill 39
# The SINGLE canonical writer of the AGENTS.md / MEMORY.md / TOOLS.md pointer
# blocks (the former duplicate AGENTS writer 04-update-agents-md.sh was folded in
# here and removed — no more double-post). Each block sits behind a VERSION-FREE
# BEGIN/END marker and is written REPLACE-IN-PLACE (a MARKER-REFRESH writer): a
# re-run — including after a version bump — overwrites the block in place instead
# of appending a duplicate. It also strips any LEGACY version-stamped variant of
# the same marker (e.g. `<!-- BEGIN skill-39 tools v1.0.0 -->`) so boxes wired by
# an older version get exactly ONE block after the refresh. Backs up each core
# file before its first edit. UNIVERSAL — no client data.

set -uo pipefail
P="[skill 39][core-files]"

OS="$(uname -s)"
case "$OS" in
  Darwin) ROOTS=( "$HOME/.openclaw" "$HOME/clawd" ) ;;
  *)      ROOTS=( "/data/.openclaw" "/data/clawd" "$HOME/.openclaw" ) ;;
esac

find_core() { # base-name -> first existing path
  local name="$1" r
  for r in "${ROOTS[@]}"; do [ -f "$r/$name" ] && { echo "$r/$name"; return 0; }; done
  return 1
}

# ── Master-files root + the MEMORY.md pointer target ─────────────────────────
# MEMORY.md gets a POINTER, never the rule corpus: core bootstrap files are
# re-billed to the model on every turn, so the rule text lives in a deep file
# (references/memory-design-rules.md) that this script installs next to the
# skill in the client's master-files folder. Resolution order mirrors
# scripts/01-locate-master-files-folder.sh, then the platform default used by
# repo scripts/typ-migrate.sh + scripts/apply-fleet-standards.sh.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
resolve_master_files_dir() {
  local s
  [ -n "${MASTER_FILES_DIR:-}" ] && { printf '%s\n' "$MASTER_FILES_DIR"; return 0; }
  for s in "$HOME/.openclaw/.skill-39-master-files-dir" "$HOME/.openclaw/.skill-38-master-files-dir"; do
    [ -s "$s" ] && { head -n1 "$s"; return 0; }
  done
  if [ -f /data/.openclaw/openclaw.json ]; then
    printf '%s\n' "/data/.openclaw/master-files"
  else
    printf '%s\n' "$HOME/Downloads/openclaw-master-files"
  fi
}
MFD="$(resolve_master_files_dir)"
SKILL_DEST="$MFD/39-real-estate-playbook"
RULES_SRC="$SKILL_ROOT/references/memory-design-rules.md"
RULES_DEST="$SKILL_DEST/references/memory-design-rules.md"
if [ -f "$RULES_SRC" ] && [ "$SKILL_ROOT" != "$SKILL_DEST" ]; then
  mkdir -p "$SKILL_DEST/references" 2>/dev/null || true
  if [ ! -f "$RULES_DEST" ] || [ "$RULES_SRC" -nt "$RULES_DEST" ]; then
    cp "$RULES_SRC" "$RULES_DEST" 2>/dev/null && echo "$P installed rule reference -> $RULES_DEST"
  fi
fi

# MARKER-REFRESH writer: remove any existing block for this VERSION-FREE marker id
# (and any legacy `<mid> vX.Y.Z` variant), then append the fresh block. Idempotent
# and bump-safe: never leaves a duplicate behind. (Fulfils the CORE_UPDATES promise
# of a replace-in-place writer; FIX-XC-11a + FIX-S36-11(ii).)
append_block() { # file marker-id content
  local file="$1" mid="$2" content="$3"
  local begin="<!-- BEGIN skill-39 $mid -->" end="<!-- END skill-39 $mid -->"
  [ -f "$file.skill39.bak" ] || cp "$file" "$file.skill39.bak" 2>/dev/null || true
  local blk tmp
  blk="$(mktemp)"; tmp="$(mktemp)"
  { printf '%s\n' "$begin"; printf '%s\n' "$content"; printf '%s\n' "$end"; } > "$blk"
  # TRUE replace-in-place: substitute the block where it already sits (matching the
  # version-free marker OR any legacy `<mid> vX.Y.Z` variant), dropping any further
  # duplicates; append at EOF only when the block is genuinely absent. Substituting
  # in position — rather than strip-then-append — keeps the file BYTE-STABLE across
  # re-runs even when several skills write blocks into the same core file.
  awk -v mid="$mid" -v blkfile="$blk" '
    BEGIN { skip = 0; done = 0 }
    {
      if (skip == 0 && $0 ~ ("^<!-- BEGIN skill-39 " mid "( v[0-9][^ ]*)? -->$")) {
        skip = 1
        if (!done) { while ((getline l < blkfile) > 0) print l; close(blkfile); done = 1 }
        next
      }
      if (skip == 1) {
        if ($0 ~ ("^<!-- END skill-39 " mid "( v[0-9][^ ]*)? -->$")) skip = 0
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

# One-time sweep of the LEGACY generic-installer memory stub for this skill
# (`<!-- BEGIN skill:39-real-estate-playbook:memory -->`), which carried the same
# rule corpus under a different marker family and therefore survived every
# marker-refresh. Same namespace, so this is a self-clean, not a cross-writer edit.
strip_legacy_stub() { # file
  local file="$1" tmp
  [ -f "$file" ] || return 0
  grep -qF '<!-- BEGIN skill:39-real-estate-playbook:memory -->' "$file" 2>/dev/null || return 0
  tmp="$(mktemp)"
  awk '
    BEGIN { skip = 0 }
    {
      if (skip == 0 && $0 ~ /^<!-- BEGIN skill:39-real-estate-playbook:memory -->$/) { skip = 1; next }
      if (skip == 1) { if ($0 ~ /^<!-- END skill:39-real-estate-playbook:memory -->$/) skip = 0; next }
      print
    }
  ' "$file" > "$tmp"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  echo "$P $(basename "$file"): removed legacy generic-installer memory stub"
}

# ---- AGENTS.md ----
if AGENTS="$(find_core AGENTS.md)"; then
  append_block "$AGENTS" "real-estate" \
"Real-estate context only (never fires for a non-RE client):
- Property intelligence: run scripts/property-lookup.sh --address \"<addr>\" — it geocodes (keyless Census first) then reports lookup/comps/Street View as AVAILABLE vs HONEST GAP via the operator-keyed provider and appends the F52 event. NEVER fabricate; absence -> honest gap + operator-supplied-key path. (Primitives: scripts/lib-property.sh {geocode|lookup|comps|streetview}.)
- Buyer/seller/investor qualification: supply the matching question set conversationally (protocols/buyer-qualification-protocol.md, protocols/seller-qualification-protocol.md); honor fair-housing guardrails; tag ZHC-buyer-lead / ZHC-seller-lead / ZHC-investor-lead.
- Showing scheduler: confirm access details, set 24h+2h reminders, surface the state disclosure pointer (protocols/showing-scheduler-protocol.md + protocols/state-disclosure-compliance-protocol.md), escalate the disclosure decision to the licensed agent.
- Lead routing: best-fit agent by specialty; round-robin on ties; fair-housing respected (protocols/lead-routing-protocol.md).
- Pre-foreclosure outreach: consume Skill 40 output; care-first playbook (protocols/pre-foreclosure-outreach-protocol.md); tag ZHC-pre-foreclosure-prospect. Skill 39 never scrapes records itself.
- GHL + Command Center sync: scripts/lib-ghl-sync.sh applies tags (ghl_tag), places/advances the pipeline (ghl_opportunity), books showings (ghl_book), and moves the Kanban card (cc_move) — fail-soft HONEST no-op when a credential is absent (never fakes success). A builder never self-promotes its own task to done.
- Event log: append one line to \$MASTER_FILES_DIR/real-estate-events.jsonl for every property lookup, showing, comps/CMA request, qualification, route, and pre-foreclosure touch."
else
  echo "$P WARN: AGENTS.md not found in known locations — add the block manually (see CORE_UPDATES.md)."
fi

# ---- MEMORY.md ----
if MEM="$(find_core MEMORY.md)"; then
  strip_legacy_stub "$MEM"
  append_block "$MEM" "memory-rules" \
"## Skill 39 — Real-estate design rules [PRIORITY: HIGH]
- **WHAT:** 7 binding rules — No-Fabrication, Fair-Housing, Disclosure-Pointer, CMA-Anchor,
  Pre-Foreclosure Care, Event-Log, Skill-38-Additive.
- **WHEN (trigger):** before any property lookup, comps/CMA, qualification, showing, lead
  route or pre-foreclosure outreach. Read the rules; never work from memory.
- **WHY:** hard constraints — never invent property facts, never steer by protected class,
  never give disclosure legal advice, never price before the CMA, log PII-free.
- **Full text / go deeper:** $RULES_DEST
  (per-rule deep specs: $SKILL_DEST/protocols/)"
else
  echo "$P WARN: MEMORY.md not found in known locations — add the block manually (see CORE_UPDATES.md)."
fi

# ---- TOOLS.md ----
if TOOLS="$(find_core TOOLS.md)"; then
  append_block "$TOOLS" "tools" \
"Skill 39 tools (UNIVERSAL; no keys, no client data):
- scripts/property-lookup.sh --address \"<addr>\" [--want caps] - runtime property-intelligence worker; resolves provider status, prints AVAILABLE vs HONEST GAP per capability, appends one F52 property_lookup event. NEVER fabricates.
- scripts/lib-property.sh {geocode|lookup|comps|streetview} <arg> - provider-abstraction primitives; honest gap (available:false / matched:false) when a key is absent. streetview fetches the image BYTES server-side and emits a local image_path — the API key is NEVER placed in the emitted URL/output.
- scripts/lib-re-events.sh re_event <type> <json> - append one line to \$MASTER_FILES_DIR/real-estate-events.jsonl (MASTER_FILES_DIR resolved from persisted state; loud-fails rather than writing to Downloads).
- scripts/lib-ghl-sync.sh {ghl_tag|ghl_opportunity|ghl_book|cc_move} ... - fail-soft GoHighLevel (via the Tier-0 caf CLI) + Command Center Kanban writes; HONEST no-op when a credential is absent (never fabricates success, never prints a secret; a builder never self-promotes its own task to done).
Provider env vars (operator-supplied): GOOGLE_MAPS_API_KEY (geocode+streetview), MAPBOX_TOKEN (geocode), RENTCAST_API_KEY / RESO_API_TOKEN (lookup+comps). GHL writes: GOHIGHLEVEL_API_KEY (caf also resolves CAF_API_KEY/GHL_API_KEY). Command Center: MC_API_TOKEN + MISSION_CONTROL_URL (default http://localhost:4000). US Census geocoder is keyless."
else
  echo "$P WARN: TOOLS.md not found in known locations — add the block manually (see CORE_UPDATES.md)."
fi

echo "$P core-file updates complete (idempotent, backups written before first edit)."
exit 0

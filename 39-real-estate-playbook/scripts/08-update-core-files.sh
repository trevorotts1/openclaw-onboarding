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

# MARKER-REFRESH writer: remove any existing block for this VERSION-FREE marker id
# (and any legacy `<mid> vX.Y.Z` variant), then append the fresh block. Idempotent
# and bump-safe: never leaves a duplicate behind. (Fulfils the CORE_UPDATES promise
# of a replace-in-place writer; FIX-XC-11a + FIX-S36-11(ii).)
append_block() { # file marker-id content
  local file="$1" mid="$2" content="$3"
  local begin="<!-- BEGIN skill-39 $mid -->" end="<!-- END skill-39 $mid -->"
  [ -f "$file.skill39.bak" ] || cp "$file" "$file.skill39.bak" 2>/dev/null || true
  local tmp tmp2
  tmp="$(mktemp)"; tmp2="$(mktemp)"
  # Drop the current version-free block AND any legacy version-stamped variant.
  awk -v mid="$mid" '
    BEGIN { skip = 0 }
    {
      if (skip == 0 && $0 ~ ("^<!-- BEGIN skill-39 " mid "( v[0-9][^ ]*)? -->$")) { skip = 1; next }
      if (skip == 1 && $0 ~ ("^<!-- END skill-39 " mid "( v[0-9][^ ]*)? -->$"))   { skip = 0; next }
      if (skip == 0) print
    }
  ' "$file" > "$tmp"
  # Collapse any trailing blank lines left behind, then append the fresh block.
  awk 'BEGIN{blanks=0}{if($0==""){blanks++}else{while(blanks>0){print"";blanks--}print}}' "$tmp" > "$tmp2"
  { cat "$tmp2"; printf '\n%s\n' "$begin"; printf '%s\n' "$content"; printf '%s\n' "$end"; } > "$file"
  rm -f "$tmp" "$tmp2"
  echo "$P $(basename "$file"): wrote block '$mid' (replace-in-place)"
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
  append_block "$MEM" "memory-rules" \
"Real-estate design rules:
1. No-Fabrication Rule - never invent an address/price/sqft/comp/owner/photo. No provider/no match -> honest gap + operator-supplied-key path. Mark operator-provided figures source:operator.
2. Fair-Housing Rule - never ask about or steer by protected class in qualification or routing.
3. Disclosure-Pointer Rule - disclosure compliance is a POINTER matrix, not legal advice; the decision escalates to the licensed agent/broker.
4. CMA-Anchor Rule - never reveal a price before the CMA walk-through; anchor on verified comps, not the seller's hoped list price.
5. Pre-Foreclosure Care Rule - distressed-owner outreach is empathetic, options-focused, never predatory; honor do-not-contact + state cooling-off rules.
6. Event-Log Rule - every RE action appends one line to real-estate-events.jsonl (field names + counts, never raw PII).
7. Skill-38-Additive Rule - the RE Sales-Brain layer is an additive drop-in; never overwrite Skill 38's own protocol."
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

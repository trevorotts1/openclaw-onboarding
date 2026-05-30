#!/usr/bin/env bash
# 08-update-core-files.sh — Skill 39
# Appends the AGENTS.md / MEMORY.md / TOOLS.md pointer blocks behind clearly-named
# BEGIN/END markers. Idempotent (skips a block whose marker already exists).
# Backs up each core file before its first edit. UNIVERSAL — no client data.

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

append_block() { # file marker-id heredoc-content
  local file="$1" mid="$2" content="$3"
  local begin="<!-- BEGIN skill-39 $mid -->" end="<!-- END skill-39 $mid -->"
  if grep -qF "$begin" "$file" 2>/dev/null; then
    echo "$P $(basename "$file"): block '$mid' already present — skipping"
    return 0
  fi
  [ -f "$file.skill39.bak" ] || cp "$file" "$file.skill39.bak" 2>/dev/null || true
  { printf '\n%s\n' "$begin"; printf '%s\n' "$content"; printf '%s\n' "$end"; } >> "$file"
  echo "$P $(basename "$file"): appended block '$mid'"
}

# ---- AGENTS.md ----
if AGENTS="$(find_core AGENTS.md)"; then
  append_block "$AGENTS" "real-estate v1.0.0" \
"Real-estate context only (never fires for a non-RE client):
- Property intelligence: geocode (keyless Census first) then lookup/comps/Street View via the operator-keyed provider. NEVER fabricate; absence -> honest gap + operator-supplied-key path.
- Buyer/seller/investor qualification: supply the matching question set conversationally; honor fair-housing guardrails; tag ZHC-buyer-lead / ZHC-seller-lead / ZHC-investor-lead.
- Showing scheduler: confirm access details, set 24h+2h reminders, surface the state disclosure pointer, escalate the disclosure decision to the licensed agent.
- Lead routing: best-fit agent by specialty; round-robin on ties; fair-housing respected.
- Pre-foreclosure outreach: consume Skill 40 output; care-first playbook; tag ZHC-pre-foreclosure-prospect. Skill 39 never scrapes records itself.
- Event log: append one line to \$MASTER_FILES_DIR/real-estate-events.jsonl for every property lookup, showing, comps/CMA request, qualification, route, and pre-foreclosure touch."
else
  echo "$P WARN: AGENTS.md not found in known locations — add the block manually (see CORE_UPDATES.md)."
fi

# ---- MEMORY.md ----
if MEM="$(find_core MEMORY.md)"; then
  append_block "$MEM" "memory-rules v1.0.0" \
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
  append_block "$TOOLS" "tools v1.0.0" \
"Skill 39 libraries (UNIVERSAL; no keys, no client data):
- scripts/lib-property.sh {geocode|lookup|comps|streetview} <arg> - provider abstraction; honest gap (available:false / matched:false) when a key is absent. NEVER fabricates.
- scripts/lib-re-events.sh re_event <type> <json> - append one line to \$MASTER_FILES_DIR/real-estate-events.jsonl.
Provider env vars (operator-supplied): GOOGLE_MAPS_API_KEY (geocode+streetview), MAPBOX_TOKEN (geocode), RENTCAST_API_KEY / RESO_API_TOKEN (lookup+comps). US Census geocoder is keyless."
else
  echo "$P WARN: TOOLS.md not found in known locations — add the block manually (see CORE_UPDATES.md)."
fi

echo "$P core-file updates complete (idempotent, backups written before first edit)."
exit 0

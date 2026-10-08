#!/usr/bin/env bash
# shared-utils/ghl-creds.sh -- source me. Thin shell face of ghl_creds.py (INF002).
#
#   . ghl-creds.sh ; ghl_creds_resolve
#
# Fills GOHIGHLEVEL_LOCATION_ID (and GOHIGHLEVEL_API_KEY) ONLY when they are empty,
# from every store and every name; when no location id is stored it asks the GHL API
# which location the Convert and Flow private integration token belongs to.
# Sets GHL_CREDS_STATUS = ok | missing | unresolved | unchecked and GHL_CREDS_NOTE.
# missing/unresolved mean: install WITH A NOTE (GHL_CREDS_NOTE), never fail.
# Never prints a credential; changes no file except the small location cache.
# bash 3.2 compatible.

_GHL_CREDS_HERE="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

ghl_creds_resolve() {
  local py="" d
  for d in "$_GHL_CREDS_HERE" "$HOME/.openclaw/skills/shared-utils" "/data/.openclaw/skills/shared-utils" "/home/node/.openclaw/skills/shared-utils"; do
    [ -f "$d/ghl_creds.py" ] && { py="$d/ghl_creds.py"; break; }
  done
  if [ -z "$py" ] || ! command -v python3 >/dev/null 2>&1; then
    export GHL_CREDS_STATUS="unchecked" GHL_CREDS_NOTE="shared credential lookup not available here"
    return 0
  fi
  local out
  out="$(python3 "$py" 2>/dev/null)" || out=""
  if [ -z "$out" ]; then
    export GHL_CREDS_STATUS="unchecked" GHL_CREDS_NOTE="shared credential lookup returned nothing"
    return 0
  fi
  eval "$out"
  return 0
}

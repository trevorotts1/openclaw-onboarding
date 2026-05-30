#!/usr/bin/env bash
# 03-load-tier1-counties.sh — Skill 40
# Validates + indexes the shipped Tier-1 county configs. For each config: checks
# it is valid JSON and carries the required fields (slug, county_fips, state,
# platform, tos_url, record_types, selectors). Writes a compact index to the
# master files. Idempotent (rebuilds the index each run). Does NOT fetch anything.

set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
TIER1_DIR="$SKILL_ROOT/references/tier1-counties"
P="[skill 40][tier1]"

OS="$(uname -s)"
case "$OS" in Darwin) DEFMFD="$HOME/Downloads" ;; *) DEFMFD="/data" ;; esac
STATE_FILE="$HOME/.openclaw/.skill-40-master-files-dir"
MFD="${MASTER_FILES_DIR:-}"
[ -z "$MFD" ] && [ -f "$STATE_FILE" ] && MFD="$(tr -d '[:space:]' < "$STATE_FILE" 2>/dev/null || true)"
[ -z "$MFD" ] && MFD="$DEFMFD"
INDEX="$MFD/public-records-cache/tier1-index.json"
mkdir -p "$(dirname "$INDEX")" 2>/dev/null || true

command -v jq >/dev/null 2>&1 || { echo "$P BLOCKED: jq required"; exit 1; }
[ -d "$TIER1_DIR" ] || { echo "$P BLOCKED: tier1 dir missing: $TIER1_DIR"; exit 1; }

COUNT=0; BAD=0
ENTRIES="[]"

for f in "$TIER1_DIR"/*.json; do
  [ -f "$f" ] || continue
  if ! jq -e . "$f" >/dev/null 2>&1; then echo "$P INVALID JSON: $(basename "$f")"; BAD=$((BAD+1)); continue; fi
  # Explicit per-key required-field check.
  missing=""
  for k in slug county_fips state platform tos_url record_types selectors; do
    jq -e "has(\"$k\")" "$f" >/dev/null 2>&1 || missing="$missing $k"
  done
  if [ -n "$missing" ]; then echo "$P $(basename "$f") MISSING fields:$missing"; BAD=$((BAD+1)); continue; fi
  slug="$(jq -r '.slug' "$f")"; fips="$(jq -r '.county_fips' "$f")"; plat="$(jq -r '.platform' "$f")"
  ENTRIES="$(jq -c --arg s "$slug" --arg f "$fips" --arg p "$plat" '. + [{slug:$s, county_fips:$f, platform:$p}]' <<< "$ENTRIES")"
  COUNT=$((COUNT+1))
  echo "$P indexed: $slug (FIPS $fips, platform $plat)"
done

jq -cn --argjson entries "$ENTRIES" --argjson n "$COUNT" '{generated_at:(now|todate), count:$n, counties:$entries}' > "$INDEX"
echo "$P wrote index ($COUNT counties) → $INDEX"
[ "$BAD" -eq 0 ] && echo "$P all Tier-1 configs valid" || { echo "$P $BAD invalid config(s) — fix before relying on them"; exit 1; }
echo "$P NOTE: indexing != live-valid. Run 05-validate-target.sh <slug> against the live portal before any live run."
exit 0

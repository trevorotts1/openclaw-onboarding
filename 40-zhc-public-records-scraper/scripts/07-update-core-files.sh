#!/usr/bin/env bash
# 07-update-core-files.sh — Skill 40
# Appends the AGENTS.md / MEMORY.md / TOOLS.md pointer blocks behind clearly-named
# BEGIN/END markers. Idempotent. Backs up each core file before its first edit.
# UNIVERSAL — no client data.

set -uo pipefail
P="[skill 40][core-files]"
OS="$(uname -s)"
case "$OS" in
  Darwin) ROOTS=( "$HOME/.openclaw" "$HOME/clawd" ) ;;
  *)      ROOTS=( "/data/.openclaw" "/data/clawd" "$HOME/.openclaw" ) ;;
esac

find_core() { local name="$1" r; for r in "${ROOTS[@]}"; do [ -f "$r/$name" ] && { echo "$r/$name"; return 0; }; done; return 1; }

append_block() {
  local file="$1" mid="$2" content="$3"
  local begin="<!-- BEGIN skill-40 $mid -->" end="<!-- END skill-40 $mid -->"
  if grep -qF "$begin" "$file" 2>/dev/null; then echo "$P $(basename "$file"): block '$mid' already present — skipping"; return 0; fi
  [ -f "$file.skill40.bak" ] || cp "$file" "$file.skill40.bak" 2>/dev/null || true
  { printf '\n%s\n' "$begin"; printf '%s\n' "$content"; printf '%s\n' "$end"; } >> "$file"
  echo "$P $(basename "$file"): appended block '$mid'"
}

if AGENTS="$(find_core AGENTS.md)"; then
  append_block "$AGENTS" "public-records v1.0.0" \
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
  append_block "$MEM" "memory-rules v1.0.0" \
"Public-records design rules:
1. No-Fabrication Rule - never invent a record; no source -> Tier 4 honest gap. A record without source+retrieved_at is not a record.
2. Compliance Rule - robots.txt binding; each target ToS acknowledged; every record attributed. Disallowed -> honest gap, never override.
3. Cost-Cap Rule - per-day cap + per-target rate limit binding; bulk ops require up-front cost estimate + operator confirm.
4. Cache Rule - 30-day cache; key is hash(target+query), never a raw address as a filename.
5. Stay-In-Lane Rule - Skill 40 finds/attributes/caches/logs; it never runs outreach (Skill 39 does).
6. Permissible-Use Rule - operator owns lawful permissible-purpose use (FCRA/DPPA/state); skill surfaces the reminder, gives no legal advice.
7. Event-Log Rule - every action appends one line to public-records-queries.jsonl (types+counts+status, never raw record contents)."
else
  echo "$P WARN: MEMORY.md not found — add the block manually (see CORE_UPDATES.md)."
fi

if TOOLS="$(find_core TOOLS.md)"; then
  append_block "$TOOLS" "tools v1.0.0" \
"Skill 40 libraries (UNIVERSAL; no keys, no client data):
- scripts/lib-records.sh query \"<address-or-zip>\" \"<record-type>\" [--force-refresh] - tiered router (compliance + cache + honest gap).
- scripts/lib-cost-cap.sh {estimate <n>|under_daily_cap|record_query|rate_wait <target>} - cost+rate guard.
- scripts/lib-pr-events.sh pr_event <type> <json> - append one line to public-records-queries.jsonl.
Caps (env): PR_DAILY_CAP, PR_PER_TARGET_MIN_INTERVAL_S, PR_BULK_CONFIRM_THRESHOLD, PR_COST_PER_QUERY, PR_CACHE_TTL_DAYS."
else
  echo "$P WARN: TOOLS.md not found — add the block manually (see CORE_UPDATES.md)."
fi

echo "$P core-file updates complete (idempotent, backups written before first edit)."
exit 0

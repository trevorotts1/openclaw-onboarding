#!/usr/bin/env bash
# 04-update-agents-md.sh — Skill 39 (Real Estate Playbook)
#
# Appends a single ADDITIVE, idempotent, marker-fenced block to the CLIENT
# agent's AGENTS.md that tells the runtime agent WHEN to use the real-estate
# playbook (property lookup, buyer/seller qualification, showing scheduling,
# disclosure compliance, lead routing, the pre-foreclosure outreach playbook),
# WHERE the tools live, and the cardinal NEVER-FABRICATE rule.
#
# It does NOT edit any other skill's block and does NOT modify Skill 38's
# Sales-Brain core (that hook is documented + installed additively by
# scripts/05-install-sales-brain-extension.sh).
#
# Idempotent: re-running detects the BEGIN marker and replaces the block in
# place rather than appending a second copy. OS-aware Darwin + Linux.
#
# Usage: 04-update-agents-md.sh [/path/to/AGENTS.md]
# If no path is given it resolves the client's main agent AGENTS.md from the
# standard OpenClaw layout.

set -uo pipefail

OS="$(uname -s)"
case "$OS" in
  Darwin) OC_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}" ;;
  Linux)  OC_HOME="${OPENCLAW_HOME:-/data/.openclaw}" ;;
  *) OC_HOME="${OPENCLAW_HOME:-$HOME/.openclaw}" ;;
esac

AGENTS_MD="${1:-}"
if [ -z "$AGENTS_MD" ]; then
  for cand in "$OC_HOME/agents/main/AGENTS.md" "$OC_HOME/AGENTS.md"; do
    if [ -f "$cand" ]; then AGENTS_MD="$cand"; break; fi
  done
fi

if [ -z "$AGENTS_MD" ]; then
  echo "ERROR: could not locate AGENTS.md (pass the path explicitly)." >&2
  exit 1
fi
[ -f "$AGENTS_MD" ] || { echo "ERROR: AGENTS.md not found at $AGENTS_MD" >&2; exit 1; }

BEGIN="<!-- BEGIN SKILL39: REAL_ESTATE_PLAYBOOK -->"
END="<!-- END SKILL39: REAL_ESTATE_PLAYBOOK -->"

read -r -d '' BLOCK <<'BLOCK_EOF'
<!-- BEGIN SKILL39: REAL_ESTATE_PLAYBOOK -->
## Real Estate Playbook (Skill 39)

When a conversation is about buying, selling, or investing in property, use the
real-estate playbook on top of the Sales-Brain (Skill 38):

- **Property intelligence** — to look up a property, normalize the address and
  run `39-real-estate-playbook/scripts/03-property-lookup.sh --address "<addr>"`.
  It tells you which capabilities (property_lookup / mls / geocode / street_view
  / comps) are AVAILABLE vs an HONEST GAP. CARDINAL RULE: **never fabricate
  property data** — no invented price, beds/baths, comps, or owner. If a
  capability is an honest gap, say so plainly and offer to pull it once a
  provider key is added.
- **Buyer qualification** — ask the buyer questions (timeline, financing,
  neighborhood, must-haves). Tag the contact `ZHC-buyer-lead`. See
  `protocols/buyer-qualification-protocol.md`.
- **Seller qualification** — ask the seller questions (motivation, timeline,
  target price, occupancy). Tag `ZHC-seller-lead`. See
  `protocols/seller-qualification-protocol.md`.
- **Investor signals** — tag `ZHC-investor-lead`. Pre-foreclosure / distressed
  prospects (sourced via Skill 40) are tagged `ZHC-pre-foreclosure-prospect`;
  outreach is governed by `protocols/pre-foreclosure-outreach-protocol.md`.
- **Showings** — respect lockbox + MLS showing rules; see
  `protocols/showing-scheduler-protocol.md`.
- **Disclosure compliance** — surface the state-specific disclosure obligations
  before any offer; see `protocols/disclosure-compliance-protocol.md`. This is a
  COMPLIANCE pointer, not legal advice.
- **Lead routing** — route to the agent whose specialty matches (buyer/seller/
  investor/relocation/luxury); see `protocols/lead-routing-protocol.md`.
- **Open house** — automate reminders + follow-up via
  `protocols/open-house-automation-protocol.md`.

Every property lookup, showing, and CMA request is logged as one JSONL event to
`<MASTER_FILES_DIR>/real-estate-events.jsonl` (F52 master-files event contract).

Tags this skill uses: `ZHC-buyer-lead`, `ZHC-seller-lead`, `ZHC-investor-lead`,
`ZHC-pre-foreclosure-prospect`. Create each tag in GHL FIRST (Settings → Tags)
before any workflow filters on it.
<!-- END SKILL39: REAL_ESTATE_PLAYBOOK -->
BLOCK_EOF

# Write the fresh block to a temp file (avoids passing multi-line text via awk -v,
# which awk rejects with "newline in string").
BLOCK_FILE="$(mktemp)"
printf '%s\n' "$BLOCK" > "$BLOCK_FILE"

TMP="$(mktemp)"
if grep -qF "$BEGIN" "$AGENTS_MD"; then
  # Idempotent refresh: drop the old fenced block (BEGIN..END inclusive), then
  # re-append the fresh block. Keeps everything else byte-for-byte.
  awk -v b="$BEGIN" -v e="$END" '
    index($0, b) {skip=1; next}
    skip==1 && index($0, e) {skip=0; next}
    skip==0 {print}
  ' "$AGENTS_MD" > "$TMP"
  # strip any trailing blank lines left behind, then append the fresh block
  awk 'BEGIN{blanks=0} {if($0==""){blanks++} else {while(blanks>0){print "";blanks--} print $0}}' "$TMP" > "$TMP.2"
  {
    cat "$TMP.2"
    printf '\n'
    cat "$BLOCK_FILE"
  } > "$AGENTS_MD"
  rm -f "$TMP" "$TMP.2"
  echo "[skill 39] refreshed AGENTS.md block in place: $AGENTS_MD"
else
  {
    printf '\n'
    cat "$BLOCK_FILE"
  } >> "$AGENTS_MD"
  rm -f "$TMP"
  echo "[skill 39] appended AGENTS.md block: $AGENTS_MD"
fi
rm -f "$BLOCK_FILE"
exit 0

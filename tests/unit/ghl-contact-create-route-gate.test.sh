#!/usr/bin/env bash
# ghl-contact-create-route-gate.test.sh — repo-level regression gate for the
# safe contact upsert policy.
#
# FAILS if a primary GHL operating instruction maps a GENERIC add/save intent
# ("add/save this person", "add/save a contact") directly to POST /contacts/
# (bare create) without marking it as forced / explicit-new-record.
#
# Legitimate explicit-new-record teachings ("explicit NEW record ONLY",
# "explicitly requested NEW record", "explicit-new-record") are allow-listed.
# Workflow "Contact Created" triggers are event names, not write instructions,
# and are excluded by only scanning the listed operating-instruction files.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FAIL=0

# Files that teach agents how to write contacts (primary operating instructions).
FILES=(
  "29-ghl-convert-and-flow/INSTRUCTIONS.md"
  "29-ghl-convert-and-flow/SKILL.md"
  "29-ghl-convert-and-flow/references/contacts.md"
  "29-ghl-convert-and-flow/references/modules.md"
  "36-ghl-mcp-setup/INSTRUCTIONS.md"
  "36-ghl-mcp-setup/CORE_UPDATES.md"
  "05-ghl-setup/INSTRUCTIONS.md"
  "05-ghl-setup/ghl-setup-full.md"
  "06-ghl-install-pages/v2-autonomous-build-sop.md"
  "44-convert-and-flow-operator/SKILL.md"
  "44-convert-and-flow-operator/INSTRUCTIONS.md"
  "44-convert-and-flow-operator/CORE_UPDATES.md"
  "44-convert-and-flow-operator/QC.md"
)

for rel in "${FILES[@]}"; do
  f="$REPO_ROOT/$rel"
  [ -f "$f" ] || { echo "FAIL: missing instruction file: $rel"; FAIL=1; continue; }
  # Find bare-create endpoint mentions in lines that ALSO carry a generic
  # add/save intent but do NOT carry an explicit-new marker.
  while IFS= read -r line; do
    lineno="${line%%:*}"; text="${line#*:}"
    low="$(printf '%s' "$text" | tr '[:upper:]' '[:lower:]')"
    case "$low" in
      *upsert*|*"explicit new"*|*"explicitly requested new"*|*"explicit-new-record"*|*"new record only"*|*"new-record only"*)
        continue ;;
    esac
    case "$low" in
      *"add/save"*|*"add this person"*|*"save this person"*|*"save a contact"*|*"add a contact"*|*"generic add"*)
        case "$low" in
          *"post /contacts/"*)
            echo "FAIL: $rel:$lineno maps generic add/save to bare POST /contacts/: $text"
            FAIL=1 ;;
        esac ;;
    esac
  done < <(grep -n "POST /contacts/" "$f" 2>/dev/null || true)
done

# The CLI default must stay upsert-safe: the upsert command exists and the
# duplicate flag defaults off (omitted unless explicitly requested).
CLI="$REPO_ROOT/44-convert-and-flow-operator/tools/engine/cli_anything/gohighlevel/gohighlevel_cli.py"
grep -q 'contacts.command("upsert")' "$CLI" \
  || { echo "FAIL: contacts upsert command missing from CLI"; FAIL=1; }
grep -q 'createNewIfDuplicateAllowed' "$CLI" \
  || { echo "FAIL: createNewIfDuplicateAllowed handling missing from CLI"; FAIL=1; }
grep -q 'is_flag=True, default=False' "$CLI" \
  || { echo "FAIL: duplicate flag must default off (is_flag/default False)"; FAIL=1; }
grep -q 'WRITE SUCCEEDED' "$CLI" \
  || { echo "FAIL: upsert read-back verification missing from CLI"; FAIL=1; }

if [ "$FAIL" -ne 0 ]; then
  echo "GATE FAILED — generic add/save must route to upsert, not bare create."
  exit 1
fi
echo "GATE PASSED — generic add/save routes to upsert in all primary instructions."

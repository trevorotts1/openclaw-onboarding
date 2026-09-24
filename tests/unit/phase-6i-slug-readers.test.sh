#!/usr/bin/env bash
# phase-6i-slug-readers.test.sh — every reader of the company slug in the
# build state must also accept the `slug` key, and the role-library pin must
# count symlinked how-to.md files.
#
# LIVE (2026-09-23): Karen Vaughn's build state stores the company slug under
# `slug`; the readers only tried companySlug / clientSlug, so Phase 6i logged
# "no CLIENT_SLUG resolved -- SKIPPING" on every run. Angeleen Harris's 448
# how-to.md are symlinks, and `find -type f` without -L counted 0.
# Runs the REAL jq filters extracted from the scripts against fixtures.
set -uo pipefail
P="[phase-6i-slug-readers]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }
command -v jq >/dev/null 2>&1 || { echo "$P SKIP: jq not installed"; exit 0; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RFI="$ROOT/32-command-center-setup/scripts/run-full-install.sh"
US="$ROOT/update-skills.sh"

# name|file|pattern locating the reader line; the filter is its first '…' string
READERS=(
  "run-full-install update-only slug|$RFI|CLIENT_SLUG=\$(state_get '"
  "update-skills U6c slug|$US|_U6C_SLUG=\$(jq -r '"
  "update-skills CC refresh slug|$US|_CC_SLUG=\$(jq -r '"
)
for r in "${READERS[@]}"; do
  IFS='|' read -r name file pat <<<"$r"
  line="$(grep -F "$pat" "$file" | head -1)"
  filter="$(printf '%s' "$line" | sed -E "s/^[^']*'([^']*)'.*/\1/")"
  [[ -n "$line" && -n "$filter" ]] || { fail "$name: reader line not found"; continue; }
  [[ "$pat" == *state_get* ]] && filter="$filter // empty"   # state_get appends this
  got="$(printf '{"slug":"acme-co"}' | jq -r "$filter")"
  [[ "$got" == "acme-co" ]] && pass "$name: reads a state that only has \`slug\`" \
                           || fail "$name: \`slug\`-only state read as '$got' (filter: $filter)"
  got="$(printf '{"companySlug":"canon","slug":"other"}' | jq -r "$filter")"
  [[ "$got" == "canon" ]] && pass "$name: companySlug still wins" || fail "$name: precedence broken ('$got')"
done

if grep -qF 'rl_howtos="$(find -L "$rl_dir" -name how-to.md' "$RFI"; then
  pass "ROLE_LIBRARY_PATH pin counts symlinked how-to.md (find -L)"
else
  fail "ROLE_LIBRARY_PATH pin counts how-to.md without -L (symlinked libraries read as empty)"
fi

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]

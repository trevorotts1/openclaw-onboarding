#!/usr/bin/env bash
# scripts/test-single-update-skills-entrypoint.sh
# ============================================================================
# Guards the fleet-wide fatal this repo shipped once already: TWO scripts
# named "update-skills.sh" (repo root vs scripts/), where the wrong one could
# be invoked successfully and quietly do partial work while bumping its own
# version stamp -- a hollow update reported as a success.
#
# scripts/update-skills.sh is now a retired, loud-failing shim. This suite
# proves, mechanically:
#   (A) scripts/update-skills.sh CANNOT be invoked successfully -- no flag,
#       no env var, no code path returns 0. It mutates nothing.
#   (B) update-skills.sh (repo root) remains the real, substantial updater
#       (not itself reduced to a stub).
#   (C) no doc/script/cron template in the repo references
#       "scripts/update-skills.sh" outside an explicit allowlist -- so a new
#       instruction telling a human or an agent to actually RUN the legacy
#       path can never again land silently. Every allowlisted file either (i)
#       explicitly warns AGAINST running it, (ii) is test/self-heal machinery
#       that detects the string on purpose, (iii) is a historical record
#       (CHANGELOG/ledger/ticket) of the incident itself, or (iv) is the shim
#       file / this guard's own machinery.
#
# Exit codes: 0 = clean; 1 = a regression was found.
# ============================================================================
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
LEGACY="$REPO/scripts/update-skills.sh"
ROOT_UPDATER="$REPO/update-skills.sh"

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# OCT4 issue #10: the retired shim was DELETED outright. Its absence IS the
# guard: any file at this path is an instant regression.
if [ -e "$LEGACY" ]; then
  bad "scripts/update-skills.sh exists — the retired shim must stay deleted (OCT4 issue #10)"
else
  ok "scripts/update-skills.sh is deleted (single updater entrypoint holds)"
fi
[ -f "$ROOT_UPDATER" ] || { echo "FATAL: $ROOT_UPDATER not found"; exit 2; }

# ============================================================================
# (A) The legacy path can NEVER be invoked successfully.
# ============================================================================
hdr "(B) update-skills.sh (repo root) is still the real updater, not a stub"

ROOT_LINES="$(wc -l < "$ROOT_UPDATER" | tr -d ' ')"
if [ "$ROOT_LINES" -gt 1000 ]; then
  ok "root update-skills.sh is substantial ($ROOT_LINES lines)"
else
  bad "root update-skills.sh looks reduced to a stub ($ROOT_LINES lines)"
fi
grep -q "^SELF=\"\$(basename" "$ROOT_UPDATER" \
  && bad "root update-skills.sh looks like it was accidentally overwritten with the shim" \
  || ok "root update-skills.sh was not accidentally overwritten with the shim"
grep -q "LEGACY_UPDATER_PATH_FRAGMENT=" "$ROOT_UPDATER" \
  && ok "root update-skills.sh still carries the weekly-cron self-heal for boxes still on the legacy URL" \
  || bad "root update-skills.sh lost the weekly-cron self-heal (LEGACY_UPDATER_PATH_FRAGMENT)"

# ============================================================================
# (C) No new reference to the legacy path outside the explicit allowlist.
# ============================================================================
hdr "(C) no doc/script/cron template references scripts/update-skills.sh as something to run"

# Every file allowed to contain the literal string "scripts/update-skills.sh",
# and WHY. Adding a file here must come with a reason in the same PR.
ALLOWLIST=(
  ".githooks/pre-commit"                                        # historical incident comment
  ".github/workflows/config-injection-shapes-guard.yml"          # path trigger only
  ".github/workflows/gws-credential-preservation-guard.yml"      # path trigger only
  ".github/workflows/single-update-skills-entrypoint-guard.yml"  # this guard's own path triggers
  "22-book-to-persona-coaching-leadership-system/CHANGELOG.md"   # historical record of the incident + fix
  "22-book-to-persona-coaching-leadership-system/INSTALL.md"     # explicit "do not run this" warning
  "32-command-center-setup/CORE_UPDATES.md"                      # explicit "NOT scripts/update-skills.sh" warning
  "CHANGELOG.md"                                                 # historical record of the incident + fix
  "CONTRIBUTING.md"                                               # explicit "never scripts/update-skills.sh" warning
  "QUALITY-CONTROL/tickets/U073.md"                               # historical ticket
  "Start Here.md"                                                 # explicit "NOT scripts/update-skills.sh" warning
  "UPDATE-PLAYBOOK.md"                                            # explicit "never scripts/update-skills.sh" warning
  "install.sh"                                                    # explicit "never scripts/update-skills.sh" warning
  "ledgers/evidence/GK-01-U63/README.md"                          # historical evidence
  "scripts/qc-assert-chmod600-real.py"                            # historical incident comment
  "scripts/setup-weekly-update.sh"                                # self-heal DETECTS this string on purpose
  "scripts/test-config-injection-shapes.sh"                       # negative-assertion test (asserts absence of a bad literal)
  "scripts/test-single-update-skills-entrypoint.sh"               # this file
  "tests/test-ungated-claim-points.sh"                            # comment, substring-filtered from a write-site scan
  "tests/unit/cron-owner-chat-guard.test.sh"                      # test assertions against the shim
  "tests/unit/full-update-path-contract.test.sh"                  # negative-assertion tests
  "tests/unit/one-front-door-full-path.test.sh"                   # asserts the shim stays DELETED (OCT4 issue #10)
  "tests/unit/fleet-refresh-roll-safety.test.py"                 # asserts the cron heal repoints the legacy URL away
  "update-skills.sh"                                              # root script's own self-heal + LEGACY_UPDATER_PATH_FRAGMENT
)

is_allowed() {
  local f="$1" a
  for a in "${ALLOWLIST[@]}"; do
    [ "$f" = "$a" ] && return 0
  done
  return 1
}

UNEXPECTED=""
while IFS= read -r -d '' f; do
  rel="${f#"$REPO"/}"
  case "$rel" in
    .git/*) continue ;;
  esac
  # Binary files (e.g. packaged .skill zip snapshots) are out of scope for a
  # text-reference guard; `grep -I` (below) already skips them, this is belt
  # and suspenders for the file-listing pass.
  if ! grep -qI . "$f" 2>/dev/null; then continue; fi
  if grep -qF "scripts/update-skills.sh" "$f" 2>/dev/null; then
    if ! is_allowed "$rel"; then
      UNEXPECTED="${UNEXPECTED}${UNEXPECTED:+$'\n'}$rel"
    fi
  fi
done < <(find "$REPO" -type f -print0 2>/dev/null)

if [ -n "$UNEXPECTED" ]; then
  bad "new/unexpected reference(s) to scripts/update-skills.sh outside the allowlist:"
  printf '%s\n' "$UNEXPECTED" | sed 's/^/      /'
else
  ok "every reference to scripts/update-skills.sh in the repo is in the explicit allowlist"
fi

# The allowlist itself must not silently rot into a junk drawer: every listed
# file must still actually exist AND still actually contain the string
# (otherwise the allowlist is hiding a stale entry instead of proving one).
STALE=""
for a in "${ALLOWLIST[@]}"; do
  p="$REPO/$a"
  if [ ! -f "$p" ]; then
    STALE="${STALE}${STALE:+$'\n'}$a (file no longer exists)"
  elif ! grep -qF "scripts/update-skills.sh" "$p" 2>/dev/null; then
    STALE="${STALE}${STALE:+$'\n'}$a (no longer contains the string — remove from allowlist)"
  fi
done
if [ -n "$STALE" ]; then
  bad "stale allowlist entries (remove them so the allowlist stays a real inventory):"
  printf '%s\n' "$STALE" | sed 's/^/      /'
else
  ok "allowlist has no stale entries"
fi

printf '\n=========================================\n'
printf 'SINGLE-UPDATE-SKILLS-ENTRYPOINT GUARD: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
printf '=========================================\n'
[ "$FAIL" -eq 0 ]

#!/usr/bin/env bash
# tests/unit/ghl-mcp-root-ownership-status-routing.test.sh
#
# DEFECT 1, part (c): the repo's own roll/update path (install.sh Step 14a,
# update-skills.sh's post-wiring STATUS reaper) must surface the NEW
# ROOT_OWNERSHIP_MISMATCH status LOUDLY, with the real remedy, rather than
# letting it fall through to the generic PIN_MISMATCH/PIN_INVALID message —
# which is exactly the misdiagnosis that hid this defect in the first place
# (an operator who is told "re-vet the pin" never learns the pin was fine and
# the problem was root ownership).
#
# WHAT IS PROVEN:
#   install.sh:       start_ghl_mcp_autostart() routes a STATUS line
#                      containing ROOT_OWNERSHIP_MISMATCH to the dedicated
#                      warning, not the generic PIN_MISMATCH one — using the
#                      REAL function, with a stub ghl-mcp-autostart.sh on
#                      disk (no real build/git/pm2 touched).
#   update-skills.sh: the STATUS-line case block (the "R14: REAP THE GHL MCP
#                      STATUS LINE" section) does the same, given
#                      GHL_MCP_STATUS_LINE set directly (no /tmp log file
#                      touched).
#
# Both are proven against a HARMLESS control case (HEALTHY_ALREADY / a status
# NOT containing ROOT_OWNERSHIP_MISMATCH) to confirm the new arm did not
# swallow unrelated states — the anti-vacuity check.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"

FAILURES=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }

echo "=== ghl-mcp-root-ownership-status-routing.test.sh ==="
echo ""

[ -f "$INSTALL_SH" ] || { echo "FATAL: $INSTALL_SH not found"; exit 1; }
[ -f "$UPDATE_SH" ] || { echo "FATAL: $UPDATE_SH not found"; exit 1; }

# ── install.sh: start_ghl_mcp_autostart() ────────────────────────────────────
INSTALL_FN="$(awk '/^start_ghl_mcp_autostart\(\) \{/,/^}/' "$INSTALL_SH")"
if [ -z "$INSTALL_FN" ]; then
  fail "(install.sh setup) could not extract start_ghl_mcp_autostart() — anchors drifted"
else
  pass "(install.sh setup) extracted start_ghl_mcp_autostart()"
fi
if ! printf '%s' "$INSTALL_FN" | grep -qF 'ROOT_OWNERSHIP_MISMATCH'; then
  fail "(install.sh setup) extracted function does not route ROOT_OWNERSHIP_MISMATCH"
fi

_run_install_case() {  # <status_word_to_have_autostart_print>
  local status_word="$1" tmp
  tmp="$(mktemp -d "${TMPDIR:-/tmp}/ghl-install-status.XXXXXX")"
  mkdir -p "$tmp/scripts"
  cat > "$tmp/scripts/ghl-mcp-autostart.sh" <<EOF
#!/usr/bin/env bash
printf 'STATUS: ghl-mcp-autostart=${status_word} (synthetic test line)\n'
EOF
  chmod +x "$tmp/scripts/ghl-mcp-autostart.sh"
  local out
  out="$(
    ONBOARDING_DIR="$tmp"
    LOG_FILE="$tmp/install.log"
    warn()    { printf 'WARN: %s\n' "$*"; }
    note()    { printf 'NOTE: %s\n' "$*"; }
    success() { printf 'OK: %s\n' "$*"; }
    eval "$INSTALL_FN"
    start_ghl_mcp_autostart
  )"
  rm -rf "$tmp"
  printf '%s' "$out"
}

OUT="$(_run_install_case ROOT_OWNERSHIP_MISMATCH)"
if printf '%s' "$OUT" | grep -qF 'docker exec -u node' && printf '%s' "$OUT" | grep -qF 'WARN:'; then
  pass "(install.sh) ROOT_OWNERSHIP_MISMATCH -> dedicated WARN naming docker exec -u node, not the generic pin message"
else
  fail "(install.sh) ROOT_OWNERSHIP_MISMATCH did not route to the dedicated remedy. Output: $OUT"
fi
if printf '%s' "$OUT" | grep -qF 're-vet upstream'; then
  fail "(install.sh) ROOT_OWNERSHIP_MISMATCH fell through to the generic PIN_MISMATCH message (the exact misdiagnosis this fix exists to stop)"
else
  pass "(install.sh) ROOT_OWNERSHIP_MISMATCH did NOT fall through to the generic pin-revet message"
fi

# Anti-vacuity: an unrelated, harmless status must still route normally.
OUT="$(_run_install_case HEALTHY_ALREADY)"
if printf '%s' "$OUT" | grep -qF 'OK:' && printf '%s' "$OUT" | grep -qiF 'answering json-rpc'; then
  pass "(install.sh) HEALTHY_ALREADY still routes to its own success message (anti-vacuity control)"
else
  fail "(install.sh) HEALTHY_ALREADY routing regressed. Output: $OUT"
fi

# ── update-skills.sh: the STATUS-line case block ─────────────────────────────
UPDATE_CASE="$(awk '/^  case "\$GHL_MCP_STATUS_LINE" in/,/^  esac/' "$UPDATE_SH")"
if [ -z "$UPDATE_CASE" ]; then
  fail "(update-skills.sh setup) could not extract the GHL_MCP_STATUS_LINE case block — anchors drifted"
else
  pass "(update-skills.sh setup) extracted the GHL_MCP_STATUS_LINE case block"
fi
if ! printf '%s' "$UPDATE_CASE" | grep -qF 'ROOT_OWNERSHIP_MISMATCH'; then
  fail "(update-skills.sh setup) extracted case block does not route ROOT_OWNERSHIP_MISMATCH"
fi

_run_update_case() {  # <status_word>
  local status_word="$1"
  (
    GHL_MCP_STATUS_LINE="STATUS: ghl-mcp-autostart=${status_word} (synthetic test line)"
    eval "$UPDATE_CASE"
  )
}

OUT="$(_run_update_case ROOT_OWNERSHIP_MISMATCH)"
if printf '%s' "$OUT" | grep -qF 'docker exec -u node'; then
  pass "(update-skills.sh) ROOT_OWNERSHIP_MISMATCH -> dedicated warning naming docker exec -u node"
else
  fail "(update-skills.sh) ROOT_OWNERSHIP_MISMATCH did not route to the dedicated remedy. Output: $OUT"
fi
if printf '%s' "$OUT" | grep -qF 'the vetted commit pin could not be honoured'; then
  fail "(update-skills.sh) ROOT_OWNERSHIP_MISMATCH fell through to the generic PIN_MISMATCH message"
else
  pass "(update-skills.sh) ROOT_OWNERSHIP_MISMATCH did NOT fall through to the generic pin message"
fi

# Anti-vacuity control.
OUT="$(_run_update_case HEALTHY_ALREADY)"
if printf '%s' "$OUT" | grep -qiF 'answering json-rpc'; then
  pass "(update-skills.sh) HEALTHY_ALREADY still routes to its own message (anti-vacuity control)"
else
  fail "(update-skills.sh) HEALTHY_ALREADY routing regressed. Output: $OUT"
fi

echo ""
echo "=== Result: $FAILURES failure(s) ==="
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1

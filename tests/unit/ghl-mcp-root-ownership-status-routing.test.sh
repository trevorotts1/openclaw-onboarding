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
#
# PRESENCE CHECK: start_ghl_mcp_autostart() was deleted when install.sh Step 14a
# became a retirement scan (GU-019) — a fresh install no longer runs the
# autostart at all, so install.sh has no STATUS line of its own to route. The
# original install.sh half below stays reachable behind LEGACY_PRESENT:
# restoring the function re-arms those assertions instead of bypassing them.
# What locks install.sh now is the contract that replaced the function — the
# step must exist as a retirement scan, it must carry its refusal marker and
# read-only scanner, it must contain no start invocation, and its state router
# must still decide on evidence (three live cases, run for real).
LEGACY_PRESENT=0
if grep -qF 'start_ghl_mcp_autostart() {' "$INSTALL_SH"; then
  LEGACY_PRESENT=1
fi

if [ "$LEGACY_PRESENT" -eq 0 ]; then
  echo "--- RETIRED: start_ghl_mcp_autostart() absent from install.sh; locking Step 14a's retirement contract instead ---"

  _code_of() { awk '{ sub(/#.*/, ""); print }' "$1"; }   # live code only
  C_INSTALL="$(mktemp "${TMPDIR:-/tmp}/ghl-status-code.XXXXXX")"
  _code_of "$INSTALL_SH" > "$C_INSTALL"

  if grep -qF 'Step 14a: GHL community MCP' "$C_INSTALL"; then
    pass "(install.sh) Step 14a still ships as the GHL community MCP step (retirement scan)"
  else
    fail "(install.sh) Step 14a: GHL community MCP step is missing from install.sh (comment-stripped)"
  fi

  if grep -qE '^[[:space:]]*GHL_MCP_RETIRED=1' "$C_INSTALL"; then
    pass "(install.sh) GHL_MCP_RETIRED=1 is assigned on a live line (the step declares retirement)"
  else
    fail "(install.sh) GHL_MCP_RETIRED=1 is no longer assigned — Step 14a stopped declaring the retirement"
  fi

  if grep -qF '# >>> GHL-MCP-RETIREMENT-BEGIN' "$INSTALL_SH" \
     && grep -qF '# <<< GHL-MCP-RETIREMENT-END' "$INSTALL_SH"; then
    pass "(install.sh) GHL-MCP-RETIREMENT-BEGIN/END markers present — the read-only scan block tests extract still ships"
  else
    fail "(install.sh) GHL-MCP-RETIREMENT markers missing — the extracted retirement scan block is gone"
  fi

  # The step must contain NO start invocation: nothing may shell out to the
  # community lifecycle script (statement/argument boundary, 60-char window,
  # same rule scripts/qc-assert-ghl-mcp-supervised.sh enforces).
  if grep -qE '(^|[;&|({"=])[[:space:]]*(bash|sh|zsh|exec|nohup|setsid|source)[[:space:]]+[^|;&]{0,60}ghl-mcp-(autostart|probe)\.sh' "$C_INSTALL"; then
    fail "(install.sh) install.sh still invokes the community lifecycle script on a live line — Step 14a is a start path again, not a retirement scan"
    grep -nE '(^|[;&|({"=])[[:space:]]*(bash|sh|zsh|exec|nohup|setsid|source)[[:space:]]+[^|;&]{0,60}ghl-mcp-(autostart|probe)\.sh' "$C_INSTALL" | sed 's/^/        /'
  else
    pass "(install.sh) install.sh contains no invocation of ghl-mcp-autostart.sh / ghl-mcp-probe.sh (comment-stripped) — Step 14a never starts the service"
  fi

  if grep -qF 'ghl-mcp-retirement=' "$C_INSTALL"; then
    pass "(install.sh) Step 14a reports its own status surface: STATUS: ghl-mcp-retirement=<STATE> (replaces the deleted STATUS routing)"
  else
    fail "(install.sh) Step 14a no longer prints STATUS: ghl-mcp-retirement= — the retirement state is silent"
  fi

  # Control: the comment-stripper must still yield real live function
  #   definitions, otherwise the absence claim above could pass on an empty strip.
  if grep -qE 'oc_ghl_mcp_write_receipt[[:space:]]*\(\)[[:space:]]*\{' "$C_INSTALL"; then
    pass "(install.sh) control — comment-stripped install.sh still contains live function definitions (oc_ghl_mcp_write_receipt), so the no-invocation claim is about real code"
  else
    fail "(install.sh) control failed — comment-stripped install.sh contains no live function definitions; the no-invocation claim proves nothing"
  fi

  # Behaviour, not description: the replacement state router decides on
  # evidence — present beats unknown beats absent. Run the REAL function
  # extracted from the shipped installer, three ways.
  STATE_FN="$(awk '/^oc_ghl_mcp_state_from\(\) \{/,/^}/' "$INSTALL_SH")"
  if [ -n "$STATE_FN" ]; then
    _state() { ( eval "$STATE_FN"; oc_ghl_mcp_state_from "$@" ) 2>/dev/null; }
    _got_all_absent="$(_state absent absent absent)"
    _got_present="$(_state present absent absent)"
    _got_unknown="$(_state absent unknown absent)"
    if [ "$_got_all_absent" = "RETIRED_VERIFIED" ]; then
      pass "(install.sh) state router: every surface absent -> RETIRED_VERIFIED"
    else
      fail "(install.sh) state router: all-absent should be RETIRED_VERIFIED, got '${_got_all_absent}'"
    fi
    if [ "$_got_present" = "MIGRATION_FAILED" ]; then
      pass "(install.sh) state router: a present residual surface -> MIGRATION_FAILED (evidence beats an absent majority)"
    else
      fail "(install.sh) state router: one present surface should be MIGRATION_FAILED, got '${_got_present}'"
    fi
    if [ "$_got_unknown" = "UNVERIFIED" ]; then
      pass "(install.sh) state router: an unreadable surface -> UNVERIFIED (never reported as off)"
    else
      fail "(install.sh) state router: an unknown surface should be UNVERIFIED, got '${_got_unknown}'"
    fi
  else
    fail "(install.sh) could not extract oc_ghl_mcp_state_from() from install.sh — the retirement state router is gone"
  fi

  rm -f "$C_INSTALL"
elif [ "$LEGACY_PRESENT" -eq 1 ]; then
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

fi
# Both halves of the legacy route run only while start_ghl_mcp_autostart()
# ships; the retirement contract above runs while it does not. Either way the
# update-skills.sh half below still runs — that STATUS-line router is live in
# both worlds.

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

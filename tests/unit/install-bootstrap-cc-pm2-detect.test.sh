#!/usr/bin/env bash
# =============================================================================
# install-bootstrap-cc-pm2-detect.test.sh
#
# THE DEFECT THIS LOCKS (QC on PR #761, install.sh's
# bootstrap_command_center_shell, "Absence check 2"). The pm2-jlist secret-leak
# fix replaced `pm2 jlist | python3 -c 'json.load(...)'` with individual
# `pm2 id <name>` lookups, then tested the result with a bare
# `grep -qE '[0-9]'` against pm2's RAW combined stdout. On a FRESH PM2_HOME —
# the normal state of a brand-new client box — `pm2 id` implicitly spawns the
# pm2 daemon, and before printing its actual result pm2 writes an ASCII banner
# + "Spawning PM2 daemon with pm2_home=..." notice + first-run VersionCheck
# message ("This PM2 is not UP TO DATE" / "Upgrade to version X.Y.Z") to
# STDOUT — all full of digits. That banner alone satisfies `grep -qE '[0-9]'`
# on the FIRST loop iteration, so the code took the "pm2 already runs a
# Command Center app — bootstrap trigger skipped" branch and
# run-full-install.sh was NEVER invoked, on every fresh box.
#
# WHY THIS IS WORSE THAN THE LEAK IT FIXED: the OLD `pm2 jlist` code failed
# SAFE in this exact scenario (the banner corrupted the JSON blob, json.load()
# raised, the `except` fired, the `if` was false, and execution fell through to
# attempt the bootstrap). The replacement failed UNSAFE — it silently skipped
# and logged a false "already runs" message, with no error surfaced anywhere.
#
# THE FIX under test (install.sh's current Absence check 2), two independent
# layers: (1) PM2_DISCRETE_MODE=true, scoped to just the `pm2 id` call, which
# pm2/lib/Client.js gates its entire banner/spawn-notice/VersionCheck block on;
# (2) even if some other stray line reaches stdout regardless, only the LAST
# LINE is tested, and it must match pm2's real `[ N ]` / `[]` array shape (an
# opening bracket immediately followed by a digit), never a bare "contains a
# digit anywhere" test.
#
# WHY THE STUB PM2 BELOW IGNORES PM2_DISCRETE_MODE ON PURPOSE. If the fake pm2
# honored discrete mode and suppressed its own banner when the env var is set,
# T1 below would pass for the WRONG reason — because the banner never
# appeared, not because the code's last-line/shape isolation is doing its job.
# The stub always emits the banner (worst case: some future pm2 version, a
# plugin, or a locale message that ISN'T gated by discrete mode) so T1 is
# pinned on layer (2) alone. T4 separately confirms layer (1) is present in
# the source, as a non-decisive control.
#
# FALSIFIED AGAINST THE UNFIXED CODE. Run with a repo root as $1 to point it at
# any tree (the anchors below match both the buggy and fixed install.sh, since
# only the loop BODY changed, not the function's opening/closing lines). Against
# the pre-fix commit (fe5c6535, PR #761 as originally submitted) T1 FAILS
# (bootstrap incorrectly skipped); against the fix, T1 PASSES. T2 and T3 are
# anti-vacuity controls (a "fix" that stopped detecting a REAL running process,
# or that broke the "pm2 absent" happy path, would satisfy T1 and be worthless)
# and pass on both trees on purpose.
#
# Hermetic: temp HOME/SKILLS_DIR/LOG_FILE, a fake `pm2` on PATH (no real pm2
# daemon is ever spawned), PATH scoped to exclude the host's real `lsof` so
# Absence check 3 can never depend on what happens to be listening on this
# machine, and a stub run-full-install.sh that only writes a marker — no real
# Command Center install runs.
# =============================================================================
set -uo pipefail

REPO_ROOT="${1:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
INSTALL_SH="$REPO_ROOT/install.sh"

PASS=0; FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS+1)); }
fail() { printf '  FAIL: %s\n' "$1"; FAIL=$((FAIL+1)); }

TMPROOT="$(mktemp -d)"
trap 'rm -rf "$TMPROOT"' EXIT

echo "== install-bootstrap-cc-pm2-detect =="
echo "   repo root: $INSTALL_SH"

# Extract bootstrap_command_center_shell() verbatim between its own opening
# and first column-0 closing brace. Stable in both the buggy and fixed file —
# only the loop body inside changed.
extract_bootstrap_fn() {
  awk '/^bootstrap_command_center_shell\(\) \{/,/^}/' "$INSTALL_SH"
}

if ! extract_bootstrap_fn | grep -q 'bootstrap_command_center_shell'; then
  fail "SETUP: could not extract bootstrap_command_center_shell() from $INSTALL_SH — anchors drifted"
  echo; echo "passed: $PASS   failed: $FAIL"; exit 1
fi

# Build the probe: stub the handful of install.sh globals/helpers the
# function touches, append the real extracted function body, then call it.
build_probe() {   # $1 = dir the probe.sh will live in
  local d="$1"
  {
    echo '#!/bin/bash'
    echo 'set -euo pipefail'
    echo 'note()    { echo "NOTE: $*"; }'
    echo 'warn()    { echo "WARN: $*"; }'
    echo 'success() { echo "SUCCESS: $*"; }'
    echo 'resolve_owner_name() { printf "%s" "Test Owner"; }'
    extract_bootstrap_fn
    echo 'bootstrap_command_center_shell'
  } > "$d/probe.sh"
}

# A fake pm2 that ALWAYS emits a realistic fresh-PM2_HOME banner (ASCII art +
# daemon-spawn notice + first-run VersionCheck message, all full of digits)
# ahead of its actual `pm2 id` result, on every invocation — see header for
# why it deliberately does not honor PM2_DISCRETE_MODE. $PM2_STUB_MATCH_NAME
# (if set) is the one app name this fake pm2 reports as a live process
# ("[ 0 ]"); every other name — and every name when unset — gets "[]".
build_fake_pm2() {   # $1 = bin dir to create pm2 in
  local bindir="$1"
  mkdir -p "$bindir"
  cat > "$bindir/pm2" <<'PM2STUB'
#!/bin/bash
if [ "${1:-}" = "id" ]; then
  name="${2:-}"
  echo ""
  echo "                        -------------"
  echo ""
  echo "                Load Balance 4 instances of api.js:"
  echo "                \$ pm2 start api.js -i 4"
  echo ""
  echo "                        -------------"
  echo "[PM2] Spawning PM2 daemon with pm2_home=${PM2_HOME:-unset}"
  echo "[PM2] This PM2 is not UP TO DATE"
  echo "[PM2] Upgrade to version 7.0.3"
  if [ -n "${PM2_STUB_MATCH_NAME:-}" ] && [ "$name" = "$PM2_STUB_MATCH_NAME" ]; then
    echo "[ 0 ]"
  else
    echo "[]"
  fi
  exit 0
fi
echo "[]"
exit 0
PM2STUB
  chmod +x "$bindir/pm2"
}

build_stub_run_install() {   # $1 = SKILLS_DIR
  local skills_dir="$1"
  mkdir -p "$skills_dir/32-command-center-setup/scripts"
  cat > "$skills_dir/32-command-center-setup/scripts/run-full-install.sh" <<'RUNSTUB'
#!/bin/bash
echo "STUB-RUN-FULL-INSTALL called with args: $*"
exit 0
RUNSTUB
  chmod +x "$skills_dir/32-command-center-setup/scripts/run-full-install.sh"
}

# run_scenario NAME MATCH_NAME(or empty) INCLUDE_PM2(1/0)
# Echoes: three tab-separated fields: OUT_MARKER LOG_MARKER SKIP_MARKER
run_scenario() {
  local scen="$1" match_name="$2" include_pm2="$3"
  local D="$TMPROOT/$scen"
  mkdir -p "$D/home" "$D/skills" "$D/bin"
  build_stub_run_install "$D/skills"
  build_probe "$D"
  local path_env="/usr/bin:/bin"
  if [ "$include_pm2" = "1" ]; then
    build_fake_pm2 "$D/bin"
    path_env="$D/bin:/usr/bin:/bin"
  fi
  local OUT
  OUT=$(env -i \
        HOME="$D/home" \
        SKILLS_DIR="$D/skills" \
        LOG_FILE="$D/log.txt" \
        PATH="$path_env" \
        PM2_STUB_MATCH_NAME="$match_name" \
        bash "$D/probe.sh" 2>&1)
  printf '%s' "$OUT" > "$D/stdout.txt"
  : > "$D/log.txt.marker"  # ensure log.txt path is inspectable even if never created
  [ -f "$D/log.txt" ] || : > "$D/log.txt"
  echo "$OUT"
}

# ---------------------------------------------------------------------------
# T1 — DECISIVE. Fresh PM2_HOME (banner present, no process registered under
# any of the three known names) => must PROCEED to bootstrap, not skip.
# ---------------------------------------------------------------------------
echo
echo "== T1 - fresh PM2_HOME, banner present, no match => bootstrap attempted =="
D="$TMPROOT/t1"
OUT=$(run_scenario t1 "" 1)
LOG_CONTENT="$(cat "$TMPROOT/t1/log.txt" 2>/dev/null || true)"
if printf '%s' "$OUT" | grep -q 'already runs a Command Center app'; then
  fail "T1: bootstrap was SKIPPED with a false \"already runs\" note despite no real match (the regression)"
else
  pass "T1: no false \"already runs\" skip"
fi
if printf '%s' "$OUT" | grep -q 'SUCCESS: Command Center locked shell bootstrapped' \
   && printf '%s' "$LOG_CONTENT" | grep -q 'STUB-RUN-FULL-INSTALL called'; then
  pass "T1: bootstrap was actually ATTEMPTED (run-full-install.sh invoked)"
else
  fail "T1: bootstrap was NOT attempted (out=[$OUT] log=[$LOG_CONTENT])"
fi

# ---------------------------------------------------------------------------
# T2 — CONTROL / anti-vacuity: a genuinely running Command Center app must
# still be detected and the bootstrap correctly skipped. A "fix" that stopped
# detecting real processes (e.g. always falling through) would pass T1 and be
# worthless.
# ---------------------------------------------------------------------------
echo
echo "== T2 - CONTROL: real process present => still correctly detected+skipped =="
OUT=$(run_scenario t2 "blackceo-command-center" 1)
LOG_CONTENT="$(cat "$TMPROOT/t2/log.txt" 2>/dev/null || true)"
if printf '%s' "$OUT" | grep -q 'already runs a Command Center app' \
   && ! printf '%s' "$LOG_CONTENT" | grep -q 'STUB-RUN-FULL-INSTALL called'; then
  pass "T2: real pm2 process is detected and bootstrap correctly skipped"
else
  fail "T2: real running process was NOT detected (out=[$OUT] log=[$LOG_CONTENT])"
fi

# ---------------------------------------------------------------------------
# T3 — CONTROL / anti-vacuity: pm2 entirely absent from PATH must be unchanged
# behaviour (this branch is gated on `command -v pm2` and untouched by the fix).
# ---------------------------------------------------------------------------
echo
echo "== T3 - CONTROL: pm2 absent entirely => unchanged (bootstrap attempted) =="
OUT=$(run_scenario t3 "" 0)
LOG_CONTENT="$(cat "$TMPROOT/t3/log.txt" 2>/dev/null || true)"
if printf '%s' "$OUT" | grep -q 'SUCCESS: Command Center locked shell bootstrapped' \
   && printf '%s' "$LOG_CONTENT" | grep -q 'STUB-RUN-FULL-INSTALL called' \
   && ! printf '%s' "$OUT" | grep -q 'already runs a Command Center app'; then
  pass "T3: pm2 absent from PATH still proceeds to bootstrap, as before"
else
  fail "T3: pm2-absent path regressed (out=[$OUT] log=[$LOG_CONTENT])"
fi

# ---------------------------------------------------------------------------
# T4 — non-decisive control: confirm the PM2_DISCRETE_MODE defense-in-depth
# layer is present in source (documents the belt; T1 alone proves the braces).
# ---------------------------------------------------------------------------
echo
echo "== T4 - CONTROL: PM2_DISCRETE_MODE belt is present in source =="
# Comment lines stripped first -- this must find the env var on a real CODE
# line (the `pm2 id` invocation itself), not merely mentioned in the prose
# explaining the fix above it, or a reworded/deleted comment would leave this
# vacuously green while the actual belt was gone.
if extract_bootstrap_fn | grep -v '^[[:space:]]*#' | grep -q 'PM2_DISCRETE_MODE=true pm2 id'; then
  pass "T4: PM2_DISCRETE_MODE=true is set on the real pm2 id invocation (not just in a comment)"
else
  fail "T4: PM2_DISCRETE_MODE defense-in-depth layer is missing from the executable code"
fi

echo
echo "────────────────────────────"
echo "passed: $PASS   failed: $FAIL"
[ "$FAIL" -eq 0 ]

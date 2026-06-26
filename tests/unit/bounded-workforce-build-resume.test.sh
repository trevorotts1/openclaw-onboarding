#!/usr/bin/env bash
# tests/unit/bounded-workforce-build-resume.test.sh
#
# CI guard for the STUCK-BUILD PARK LOOP fix (v14.1.5,
# fix/stuck-build-park-loop-durable). The onboarding-resume cron was already
# bounded (tests/unit/bounded-resume-cron.test.sh); this is the equivalent guard
# for the workforce-build-resume cron + the agent-browser circuit-breaker, which
# were the actual token furnace.
#
# Assertion groups:
#   (1) DURABLE_PARK         -- the PARK marker lives in the box's durable state
#                               dir (workspace/.park), NOT TMPDIR, so it survives
#                               a reboot. Same relative path in every actor.
#   (2) HARD_STUCK_CAP       -- resume-workforce-build.sh defines MAX_STUCK_FIRES
#                               (consecutive no-progress fires) and it is bounded.
#   (3) STUCK_CAP_DISABLES   -- the stuck-cap branch PARKS + self_remove_cron +
#                               exit 0, with NO "never stop / slow-retry forever /
#                               NOT self-removing" language. The OLD never-stop
#                               run-accounting (MAX_RUNS_BEFORE_SELF_REMOVE /
#                               "NEVER-STOP: run #") is GONE.
#   (4) PARK_GATE_STOPS      -- an already-parked build stops immediately
#                               (park_is_set -> self_remove_cron -> exit 0).
#   (5) REGISTRAR_PARK_AWARE -- ensure-pipeline-crons.sh does NOT re-register a
#                               parked box's resume cron.
#   (6) INSTALL_PARK_AWARE   -- install.sh does NOT (re)install a parked box's
#                               resume cron.
#   (7) BREAKER_DURABLE      -- browser_manager.sh breaker/PARK state is durable
#                               (no longer hard-pinned to $LOCKDIR/breaker), the
#                               breaker READS the box park marker, and a trip
#                               WRITES it (cross-stop the resume cron).
#   (8) UNPARK_PATH          -- scripts/unpark-build.sh exists, is bash -n clean,
#                               clears the park marker, and re-registers the cron.
#
# Exit 0 = all checks pass. Exit 1 = one or more failed (CI FAIL).

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

RESUME="$REPO_ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh"
ENSURE="$REPO_ROOT/scripts/ensure-pipeline-crons.sh"
INSTALL="$REPO_ROOT/install.sh"
BMGR="$REPO_ROOT/06-ghl-install-pages/tools/browser_manager.sh"
UNPARK="$REPO_ROOT/scripts/unpark-build.sh"

MARKER_REL="workspace/.park/workforce-build.parked"

echo "=== bounded-workforce-build-resume.test.sh ==="
echo ""

# ---------------------------------------------------------------------------
# (1) DURABLE_PARK
# ---------------------------------------------------------------------------
echo "--- (1) DURABLE_PARK: park marker in the durable state dir, not TMPDIR ---"
if [[ -f "$RESUME" ]]; then
  if grep -q 'PARK_DIR="\$OC_ROOT/workspace/.park"' "$RESUME" \
     && grep -q "BOX_PARK_MARKER=\"\$PARK_DIR/workforce-build.parked\"" "$RESUME"; then
    pass "1a: resume-workforce-build.sh PARK_DIR is \$OC_ROOT/workspace/.park (durable)"
  else
    fail "1a: resume-workforce-build.sh PARK_DIR/BOX_PARK_MARKER not anchored to \$OC_ROOT/workspace/.park"
  fi
  if grep -qE 'BOX_PARK_MARKER=.*(TMPDIR|/tmp)' "$RESUME"; then
    fail "1b: resume-workforce-build.sh park marker references TMPDIR/tmp (would evaporate on reboot)"
  else
    pass "1b: resume-workforce-build.sh park marker does NOT use TMPDIR/tmp"
  fi
else
  fail "1: resume-workforce-build.sh not found at $RESUME"
fi

# Every actor must agree on the SAME marker path. It is composed from a durable
# dir ending in `workspace/.park` and the file `workforce-build.parked` — some
# actors build it across two assignments (PARK_DIR=…/workspace/.park then
# …/workforce-build.parked), so assert BOTH components are present.
for f in "$RESUME" "$ENSURE" "$INSTALL" "$BMGR" "$UNPARK"; do
  bn="$(basename "$f")"
  if [[ -f "$f" ]] && grep -Fq "workspace/.park" "$f" && grep -Fq "workforce-build.parked" "$f"; then
    pass "1c-$bn: composes the canonical marker path ($MARKER_REL)"
  else
    fail "1c-$bn: does NOT compose the canonical marker path ($MARKER_REL)"
  fi
done

# ---------------------------------------------------------------------------
# (2) HARD_STUCK_CAP
# ---------------------------------------------------------------------------
echo ""
echo "--- (2) HARD_STUCK_CAP: MAX_STUCK_FIRES defined + bounded ---"
if [[ -f "$RESUME" ]]; then
  cap_line="$(grep 'MAX_STUCK_FIRES=' "$RESUME" | grep -v '^[[:space:]]*#' | head -1 || true)"
  if [[ -z "$cap_line" ]]; then
    fail "2a: MAX_STUCK_FIRES not defined in resume-workforce-build.sh"
  else
    pass "2a: MAX_STUCK_FIRES defined ($cap_line)"
    # The literal default must be an integer within a sane range (2..96).
    def_val="$(printf '%s' "$cap_line" | grep -oE ':-[0-9]+' | grep -oE '[0-9]+' | head -1 || true)"
    if [[ -z "$def_val" ]]; then
      fail "2b: could not parse MAX_STUCK_FIRES default integer"
    elif (( def_val < 2 || def_val > 96 )); then
      fail "2b: MAX_STUCK_FIRES default $def_val out of safe range 2..96"
    else
      pass "2b: MAX_STUCK_FIRES default $def_val within safe range (2..96)"
    fi
  fi
fi

# ---------------------------------------------------------------------------
# (3) STUCK_CAP_DISABLES + old never-stop furnace removed
# ---------------------------------------------------------------------------
echo ""
echo "--- (3) STUCK_CAP_DISABLES: cap branch parks + self_remove_cron + exit 0 ---"
if [[ -f "$RESUME" ]]; then
  cap_block="$(awk '/_stuck >= MAX_STUCK_FIRES/,/exit 0/' "$RESUME" 2>/dev/null | head -60 || true)"
  if [[ -z "$cap_block" ]]; then
    fail "3a: could not extract the stuck-cap branch"
  else
    echo "$cap_block" | grep -q 'park_set'        && pass "3a: stuck-cap branch PARKS (park_set)"        || fail "3a: stuck-cap branch does NOT park_set"
    echo "$cap_block" | grep -q 'self_remove_cron' && pass "3b: stuck-cap branch self_remove_cron"        || fail "3b: stuck-cap branch does NOT self_remove_cron"
    echo "$cap_block" | grep -q 'exit 0'          && pass "3c: stuck-cap branch exit 0 (bounded)"        || fail "3c: stuck-cap branch does not exit 0"
    if echo "$cap_block" | grep -qiE 'NOT self.remov|slow.retry|never stop|keep retrying'; then
      fail "3d: stuck-cap branch contains perpetual-loop language"
    else
      pass "3d: stuck-cap branch has no perpetual-loop language"
    fi
  fi
  # The OLD never-stop run-accounting furnace must be GONE.
  if grep -qE 'MAX_RUNS_BEFORE_SELF_REMOVE|NEVER-STOP: run #' "$RESUME"; then
    fail "3e: OLD never-stop run-accounting still present (MAX_RUNS_BEFORE_SELF_REMOVE / 'NEVER-STOP: run #')"
  else
    pass "3e: OLD never-stop run-accounting furnace removed"
  fi
fi

# ---------------------------------------------------------------------------
# (4) PARK_GATE_STOPS
# ---------------------------------------------------------------------------
echo ""
echo "--- (4) PARK_GATE_STOPS: already-parked build stops immediately ---"
if [[ -f "$RESUME" ]]; then
  gate_block="$(awk '/if park_is_set; then/,/^fi$/' "$RESUME" 2>/dev/null | head -8 || true)"
  if echo "$gate_block" | grep -q 'self_remove_cron' && echo "$gate_block" | grep -q 'exit 0'; then
    pass "4a: park gate calls self_remove_cron + exit 0 when parked"
  else
    fail "4a: park gate does not stop (self_remove_cron + exit 0) when parked"
  fi
fi

# ---------------------------------------------------------------------------
# (5) REGISTRAR_PARK_AWARE
# ---------------------------------------------------------------------------
echo ""
echo "--- (5) REGISTRAR_PARK_AWARE: ensure-pipeline-crons.sh skips a parked box ---"
if [[ -f "$ENSURE" ]]; then
  reg_block="$(awk '/_ensure_workforce_build_resume\(\)/,/_cron_present "workforce-build-resume"/' "$ENSURE" 2>/dev/null | head -20 || true)"
  if echo "$reg_block" | grep -q 'BOX_PARK_MARKER' && echo "$reg_block" | grep -qi 'PARKED'; then
    pass "5a: _ensure_workforce_build_resume checks BOX_PARK_MARKER and skips when parked"
  else
    fail "5a: _ensure_workforce_build_resume is NOT park-aware (would resurrect a parked cron)"
  fi
else
  fail "5: ensure-pipeline-crons.sh not found"
fi

# ---------------------------------------------------------------------------
# (6) INSTALL_PARK_AWARE
# ---------------------------------------------------------------------------
echo ""
echo "--- (6) INSTALL_PARK_AWARE: install.sh skips a parked box ---"
if [[ -f "$INSTALL" ]]; then
  inst_block="$(awk '/install_workforce_resume_cron\(\)/,/workforce-build-resume" *; then/' "$INSTALL" 2>/dev/null | head -25 || true)"
  if echo "$inst_block" | grep -q 'workforce-build.parked'; then
    pass "6a: install_workforce_resume_cron checks the park marker before installing"
  else
    fail "6a: install_workforce_resume_cron is NOT park-aware"
  fi
else
  fail "6: install.sh not found"
fi

# ---------------------------------------------------------------------------
# (7) BREAKER_DURABLE
# ---------------------------------------------------------------------------
echo ""
echo "--- (7) BREAKER_DURABLE: agent-browser breaker/PARK state is durable + cross-stops ---"
if [[ -f "$BMGR" ]]; then
  # The breaker marker functions must NOT be pinned to the ephemeral TMPDIR dir.
  if grep -qE '_bm_breaker_marker\(\).*LOCKDIR/breaker' "$BMGR"; then
    fail "7a: breaker marker still hard-pinned to \$LOCKDIR/breaker (TMPDIR — evaporates on reboot)"
  else
    pass "7a: breaker marker no longer hard-pinned to \$LOCKDIR/breaker"
  fi
  grep -q 'BM_BOX_PARK_MARKER=' "$BMGR" \
    && pass "7b: browser_manager.sh defines the canonical BM_BOX_PARK_MARKER" \
    || fail "7b: browser_manager.sh missing BM_BOX_PARK_MARKER"
  # bm_breaker_check must READ the box park marker.
  bc_block="$(awk '/bm_breaker_check\(\)/,/^}/' "$BMGR" 2>/dev/null || true)"
  echo "$bc_block" | grep -q 'BM_BOX_PARK_MARKER' \
    && pass "7c: bm_breaker_check READS the box park marker (breaker honors the marker)" \
    || fail "7c: bm_breaker_check does NOT read the box park marker"
  # A trip must WRITE the box park marker (so the resume cron stops too).
  if echo "$bc_block" | grep -q '> "\$BM_BOX_PARK_MARKER"'; then
    pass "7d: a breaker trip WRITES the box park marker (cross-stops the resume cron)"
  else
    fail "7d: a breaker trip does NOT write the box park marker"
  fi
else
  fail "7: browser_manager.sh not found"
fi

# ---------------------------------------------------------------------------
# (8) UNPARK_PATH
# ---------------------------------------------------------------------------
echo ""
echo "--- (8) UNPARK_PATH: operator un-park script present + sound ---"
if [[ -f "$UNPARK" ]]; then
  if bash -n "$UNPARK" 2>/dev/null; then
    pass "8a: unpark-build.sh is bash -n clean"
  else
    fail "8a: unpark-build.sh has a syntax error"
  fi
  grep -q 'rm -f "\$BOX_PARK_MARKER"' "$UNPARK" \
    && pass "8b: unpark-build.sh clears the park marker" \
    || fail "8b: unpark-build.sh does NOT clear the park marker"
  grep -q 'ensure-pipeline-crons.sh' "$UNPARK" \
    && pass "8c: unpark-build.sh re-registers the resume cron" \
    || fail "8c: unpark-build.sh does NOT re-register the resume cron"
else
  fail "8: scripts/unpark-build.sh not found"
fi

# ---------------------------------------------------------------------------
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if (( FAIL > 0 )); then
  echo "FAIL: $FAIL check(s) failed — CI guard triggered"
  exit 1
fi
echo "PASS: all bounded-workforce-build-resume checks pass"
exit 0

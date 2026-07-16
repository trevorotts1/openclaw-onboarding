#!/usr/bin/env bash
# ============================================================
#  test-u53-hl-u68-crown-executor-single-path.sh
#  MASTER SPEC v2 — U53 [HL/U68] Self-updater: crown ONE executor
#  (Decision D-HL-3, D12) — ONB-side regression lock.
#
#  D-HL-3 (ratified recommendation, MASTER SPEC v2 Section E.3 /
#  H+L.4): "declare update.sh (with CC_APP_DIR pinned by the caller)
#  the ONLY path that mutates a Command Center checkout during any
#  fleet roll; the onboarding repo's skill-32 refresh and the Sunday
#  cron both route through it ... make skill-32's refresh a thin
#  wrapper (CC_APP_DIR=... bash update.sh), delete duplicated
#  pull/build logic there."
#
#  P1-07 (commits 98c7df25 / a314b563, 2026-07-11 — predates this
#  spec's 2026-07-13 grounding pin) already crowned CC's own
#  update.sh as the single build+restart executor via
#  cc_route_update_through_canonical_path() in
#  32-command-center-setup/scripts/run-full-install.sh, called from
#  BOTH of update-skills.sh's D5 call sites (the --update-only
#  refresh and the F10 full-bootstrap branch). This test does not
#  re-implement or re-litigate P1-07's own behavioral proof (see
#  tests/probe/test-cc-route-update-canonical-path.sh for that) — it
#  adds the piece that was still missing: a STATIC, spec-referenced
#  regression lock proving the "ONE crowned executor / thin wrapper"
#  INVARIANT itself, at BOTH call-site layers, so a future edit can
#  never silently re-introduce a second, competing CC build/restart
#  path without this test catching it.
#
#  Extracts the REAL source text by anchor (not a hardcoded line
#  range, not a reimplementation) so line-number drift never
#  invalidates this test; a genuine anchor drift is caught loudly by
#  the vacuous-extraction guards below, never a silent pass.
#
#  Touches no live box, no real git remote, no real pm2/npm — pure
#  static text-extraction and string assertions against the repo's
#  own tracked files.
#
#  EXIT CODES: 0 all passed, 1 one or more failed.
# ============================================================
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
RUN_FULL_INSTALL="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"
UPDATE_SKILLS="$REPO_ROOT/update-skills.sh"
FAIL_COUNT=0
PASS_COUNT=0

_pass() { echo "  PASS: $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
_fail() { echo "  FAIL: $1" >&2; FAIL_COUNT=$((FAIL_COUNT + 1)); }
_section() { echo ""; echo "=== $1 ==="; }

for f in "$RUN_FULL_INSTALL" "$UPDATE_SKILLS"; do
  if [ ! -f "$f" ]; then
    _fail "source file not found: $f"
    echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
    exit 1
  fi
done

# ------------------------------------------------------------------
# Block 1 — run-full-install.sh's PHASE 6 caller: the --update-only
# branch must delegate build+restart to cc_route_update_through_
# canonical_path() and must NEVER inline a competing `npm run build`
# or a bare `pm2 restart` of its own.
# ------------------------------------------------------------------
_section "Block 1 — run-full-install.sh Phase 6 (--update-only) delegates, never inlines a second build/restart path"

BLOCK1="$(awk '
  /log "INFO" "phase=6 dashboard-deploy: starting"/ { flag=1 }
  flag { print }
  /elif \[\[ "\$\(state_get .\.commandCenterPhase6Done.\)" == "true" \]\]; then/ { exit }
' "$RUN_FULL_INSTALL")"

# Strip full-line comments and log()/echo() prose lines before scanning for
# real invocations — this file's own prose legitimately explains, in
# comments AND in human-readable log/echo strings, what it used to do / must
# never do again ("... instead of a hand-rolled npm run build + bare pm2
# restart with no rollback", "git pull + npm install + ... + pm2 restart"),
# and a naive raw-text grep would misfire on that EXPLANATORY text as if it
# were a live call. `_strip_prose` is shared by both blocks below.
_strip_prose() { grep -vE '^\s*#' | grep -vE '^\s*(log|echo) "'; }
BLOCK1_CODE="$(printf '%s\n' "$BLOCK1" | _strip_prose)"

if [ -z "$BLOCK1" ] || ! printf '%s' "$BLOCK1" | grep -q "UPDATE_ONLY"; then
  _fail "Block 1 extraction is empty/vacuous — anchor drift in run-full-install.sh; every downstream assertion below would be meaningless"
else
  _pass "Block 1 extracted non-vacuously from run-full-install.sh (anchors intact)"

  _CALLS=$(printf '%s' "$BLOCK1_CODE" | grep -c "cc_route_update_through_canonical_path" || true)
  if [ "$_CALLS" -eq 1 ]; then
    _pass "Phase 6 --update-only branch delegates to cc_route_update_through_canonical_path() exactly once"
  else
    _fail "expected exactly 1 call to cc_route_update_through_canonical_path() in the --update-only branch, found $_CALLS — the single-executor invariant (D-HL-3) is not being honored at this call site"
  fi

  if printf '%s' "$BLOCK1_CODE" | grep -q "npm run build"; then
    _fail "Phase 6 --update-only branch inlines its OWN 'npm run build' — this is exactly the duplicated build logic D-HL-3 says to delete (build must live ONLY inside the crowned executor's own tiers)"
  else
    _pass "Phase 6 --update-only branch never inlines a bare 'npm run build' outside the crowned executor"
  fi

  if printf '%s' "$BLOCK1_CODE" | grep -q "pm2 restart"; then
    _fail "Phase 6 --update-only branch inlines its OWN 'pm2 restart' — restart must be owned exclusively by cc_route_update_through_canonical_path()'s tiers, never duplicated at the caller"
  else
    _pass "Phase 6 --update-only branch never inlines a bare 'pm2 restart' outside the crowned executor"
  fi
fi

# ------------------------------------------------------------------
# Block 2 — update-skills.sh's D5 section (the "onboarding repo's
# skill-32 refresh path" D-HL-3 names) must be a THIN WRAPPER: it may
# only ever shell out to run-full-install.sh (both the --update-only
# refresh call and the F10 full-bootstrap call), and must never
# itself perform npm/pm2/git mutation of the Command Center checkout.
# ------------------------------------------------------------------
_section "Block 2 — update-skills.sh D5 section is a thin wrapper around run-full-install.sh (no duplicated pull/build logic)"

BLOCK2="$(awk '
  /# D5 — Command Center web-app refresh \(v14\.27\.0\):/ { flag=1 }
  flag { print }
  /# Conditional gateway restart: only restart when openclaw\.json was actually/ { exit }
' "$UPDATE_SKILLS")"

BLOCK2_CODE="$(printf '%s\n' "$BLOCK2" | _strip_prose)"

if [ -z "$BLOCK2" ] || ! printf '%s' "$BLOCK2" | grep -q "_CC_RUN_INSTALL"; then
  _fail "Block 2 extraction is empty/vacuous — anchor drift in update-skills.sh; every downstream assertion below would be meaningless"
else
  _pass "Block 2 extracted non-vacuously from update-skills.sh (anchors intact)"

  if printf '%s' "$BLOCK2" | grep -qF 'bash "$_CC_RUN_INSTALL" --update-only'; then
    _pass "D5 refresh call site delegates to run-full-install.sh --update-only (thin wrapper, per D-HL-3)"
  else
    _fail "D5 section no longer delegates its refresh to 'bash \"\$_CC_RUN_INSTALL\" --update-only' — the thin-wrapper contract D-HL-3 requires is not met"
  fi

  if printf '%s' "$BLOCK2" | grep -qF 'bash "$_CC_RUN_INSTALL" "$_CC_SLUG" "$_CC_COMPANY" "$_CC_EMAIL"'; then
    _pass "D5 F10 full-bootstrap call site also delegates to run-full-install.sh (no separate ad-hoc clone/build path)"
  else
    _fail "D5 F10 bootstrap branch no longer delegates to run-full-install.sh via 'bash \"\$_CC_RUN_INSTALL\" \"\$_CC_SLUG\" \"\$_CC_COMPANY\" \"\$_CC_EMAIL\"' — a duplicated bootstrap path may have been introduced"
  fi

  _DUP_FOUND=""
  for pat in 'npm install' 'npm run build' 'npm run db:push' 'pm2 restart' 'git pull' 'git reset --hard' 'git clone'; do
    if printf '%s' "$BLOCK2_CODE" | grep -qF "$pat"; then
      _DUP_FOUND="${_DUP_FOUND}${_DUP_FOUND:+, }$pat"
    fi
  done
  if [ -z "$_DUP_FOUND" ]; then
    _pass "D5 section contains ZERO direct npm/pm2/git mutation calls — every mutating step is delegated to run-full-install.sh, never duplicated inline (the exact D-HL-3 'delete duplicated pull/build logic' requirement)"
  else
    _fail "D5 section directly invokes mutating command(s) [$_DUP_FOUND] instead of delegating — duplicated pull/build logic has crept back into the onboarding-repo wrapper, in violation of D-HL-3"
  fi
fi

# ------------------------------------------------------------------
# Block 3 — cc_route_update_through_canonical_path()'s tier-1 branch
# must invoke the freshly-pulled CC's OWN update.sh with CC_APP_DIR
# pinned at the checkout it just built/restarted — the literal text
# of the D-HL-3 ruling ("CC_APP_DIR=<checkout> bash update.sh").
# Complements (does not replace) the BEHAVIORAL proof of the same
# invariant in tests/probe/test-cc-route-update-canonical-path.sh.
# ------------------------------------------------------------------
_section "Block 3 — tier 1 pins CC_APP_DIR at the freshly-pulled checkout when invoking update.sh (D-HL-3 literal text)"

FUNC_BODY="$(awk '/^cc_route_update_through_canonical_path\(\) \{/{flag=1} flag{print} flag && /^}/{exit}' "$RUN_FULL_INSTALL")"

if [ -z "$FUNC_BODY" ] || ! printf '%s' "$FUNC_BODY" | grep -q "tier=1"; then
  _fail "cc_route_update_through_canonical_path() extraction is empty/vacuous — anchor drift in run-full-install.sh"
else
  _pass "cc_route_update_through_canonical_path() extracted non-vacuously"
  if printf '%s' "$FUNC_BODY" | grep -qF 'CC_APP_DIR="$DASHBOARD_DIR" CC_PORT="$DASHBOARD_PORT" bash "$update_sh"'; then
    _pass "tier 1 invokes update.sh with CC_APP_DIR (+ CC_PORT) pinned to the freshly-pulled checkout — matches D-HL-3's ruling verbatim"
  else
    _fail "tier 1 no longer pins CC_APP_DIR=\$DASHBOARD_DIR when invoking update.sh — the crowned-executor contract D-HL-3 requires is not met in source"
  fi
fi

_section "SUMMARY"
echo "  Passed: $PASS_COUNT   Failed: $FAIL_COUNT"
if [ "$FAIL_COUNT" -gt 0 ]; then
  exit 1
fi
exit 0

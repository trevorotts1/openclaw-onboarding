#!/usr/bin/env bash
# ============================================================================
# test-cc-at-pin-stale-currency.sh
#
# REGRESSION GUARD for the AT-PIN-stale defect in
# 32-command-center-setup/scripts/run-full-install.sh (fleet roll 20261010).
#
# The Skill-32 installer's phase=6 --update-only ladder treated "HEAD contains
# cc-compat.json's pinnedTag" as proof the Command Center checkout is CURRENT.
# When CC main moves PAST the pin mid-roll (v7.6.112 -> origin/main 933f1993d)
# while the onboarding pinnedTag lags, the AT-PIN branch exited 0 with the
# checkout still behind origin/main; update-skills.sh's independent currency
# check (merge-base --is-ancestor origin/<default> HEAD) then printed
# "FATAL: ... not current on origin/main" (exit 2) and skipped the CC steps
# below it: 11 boxes in the roll-20261010 ledger.
#
# THIS TEST extracts the REAL ladder VERBATIM (awk-anchored, line-drift safe)
# plus the REAL cc_git_sync_to_default_branch / cc_zero_downtime_ready helpers,
# and drives them against a real local git remote — no reimplementation of the
# logic under test.
#
#   T1 TEETH — a checkout at the pinned tag with origin/main ahead reproduces
#              the stale shape: origin/main is NOT an ancestor of HEAD.
#   T2 FIXED — the ladder converges FORWARD: exit 0, origin/<default> IS an
#              ancestor of HEAD, the pin is still contained (never below the
#              pin), the box's local commit survives, CC_AT_PIN=0 so the
#              canonical deploy still rebuilds the moved checkout, and no
#              fail_install fired (no bare FATAL).
#   T3 NO-OP — a checkout already current on origin/<default> is left alone
#              (CC_AT_PIN=1, HEAD unchanged) — the fast path is not broken.
#
# Self-contained: bash + git. No network (origin is a local path), no real
# client box, no credentials.
# ============================================================================
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/.." && pwd)"
INSTALLER="$REPO_ROOT/32-command-center-setup/scripts/run-full-install.sh"

[ -f "$INSTALLER" ] || { echo "FATAL: installer not found at $INSTALLER"; exit 2; }

PASS=0; FAIL=0
ok()  { printf '  \033[32m✓ PASS\033[0m — %s\n' "$1"; PASS=$((PASS+1)); }
bad() { printf '  \033[31m✗ FAIL\033[0m — %s\n' "$1"; FAIL=$((FAIL+1)); }
hdr() { printf '\n\033[1m%s\033[0m\n' "$1"; }

# Extract ONE function verbatim, anchored by name (survives line-number drift).
extract_func() {
  local name="$1" file="$2"
  awk -v pat="^${name}\\\\(\\\\) \\\\{" '
    $0 ~ pat { p=1 }
    p { print }
    p && /^}/ { exit }
  ' "$file"
}

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
FRAG="$WORK/helpers.frag"
{
  extract_func cc_git_sync_to_default_branch "$INSTALLER"
  extract_func cc_zero_downtime_ready          "$INSTALLER"
} > "$FRAG"
if ! grep -q 'cc_git_sync_to_default_branch()' "$FRAG" || ! grep -q 'cc_zero_downtime_ready()' "$FRAG"; then
  echo "FATAL: helper extraction from $INSTALLER failed (function drift?)"; exit 2
fi

# The phase=6 ladder VERBATIM: from `CC_ZERO_DOWNTIME=0` to the `fi` before the
# next `cc_security_preflight --checkout`. Fails loudly if the anchors drift, so
# the suite never silently tests nothing.
LADDER_BODY="$(awk '/^  CC_ZERO_DOWNTIME=0$/{p=1} p&&/^  cc_security_preflight --checkout/{p=0} p{print}' "$INSTALLER")"
if [ -z "$LADDER_BODY" ] || ! printf '%s\n' "$LADDER_BODY" | grep -q 'CC_AT_PIN=0'; then
  echo "FATAL: phase=6 ladder could not be extracted from $INSTALLER (anchor drift?)"; exit 2
fi

git_id() { git -C "$1" rev-parse HEAD 2>/dev/null; }

# Drive the extracted ladder in a sandbox: the real helpers are sourced, the
# installer's own log/fail_install are stubbed (fail_install does NOT exit, so
# the test can inspect the outcome).
run_ladder() {
  local dir="$1" pinned="$2" logf="$3"
  (
    LOG_FILE="$logf"
    DASHBOARD_DIR="$dir"
    CC_UPDATE_TARGET="$pinned"
    # shellcheck disable=SC1090
    source "$FRAG"
    log() { printf 'LOG: %s %s\n' "${1:-}" "${2:-}" >>"$logf"; }
    fail_install() { printf 'FAILINSTALL: %s\n' "${1:-}" >>"$logf"; return 1; }
    eval "$LADDER_BODY"
    _rc=$?
    printf 'CC_AT_PIN=%s\nCC_UPDATE_TARGET=%s\n' "${CC_AT_PIN:-}" "${CC_UPDATE_TARGET:-}" >>"$logf"
    exit "$_rc"
  )
}

# bare origin seeded c1 (tagged v7.6.112 = the pin); clone then set the checkout
# to the pin. advance_origin pushes c2 so origin/main moves PAST the pin.
build_origin() {
  local root; root="$(mktemp -d "$WORK/origin.XXXXXX")"
  local origin="$root/origin.git" seed="$root/seed"
  git init --quiet --bare "$origin"
  git init --quiet "$seed"
  git -C "$seed" config user.email test@example.test
  git -C "$seed" config user.name  "Test"
  git -C "$seed" checkout --quiet -b main
  printf 'v1\n' > "$seed/main.txt"
  git -C "$seed" add -A
  git -C "$seed" commit --quiet -m c1
  git -C "$seed" tag v7.6.112
  git -C "$origin" symbolic-ref HEAD refs/heads/main
  git -C "$seed" remote add origin "$origin"
  git -C "$seed" push --quiet origin main
  git -C "$seed" push --quiet origin v7.6.112
  printf '%s\t%s\t%s\n' "$root" "$origin" "$seed"
}
advance_origin() {
  local seed="$1"
  printf 'v2\n' > "$seed/main.txt"
  git -C "$seed" commit --quiet -am c2
  git -C "$seed" push --quiet origin main
}

# ---------------------------------------------------------------------------
hdr "T1 — teeth: checkout at the pinned tag with origin/main ahead IS stale"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
PIN="$(git -C "$SEED" rev-parse v7.6.112)"
CO="$ROOT/checkout"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" config user.email box@example.test
git -C "$CO" config user.name  "Box"
git -C "$CO" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
git -C "$CO" reset -q --hard v7.6.112
git -C "$CO" commit --quiet --allow-empty -m "box local commit"
LOCAL="$(git_id "$CO")"
advance_origin "$SEED"
git -C "$CO" fetch --quiet origin "+refs/heads/main:refs/remotes/origin/main"
if git -C "$CO" merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
  bad "T1: origin/main was already an ancestor of HEAD (fixture did not reproduce the stale shape)"
else
  ok "T1: HEAD contains the pin but NOT origin/main — the stale shape is reproduced"
fi
if git -C "$CO" merge-base --is-ancestor "$PIN" HEAD 2>/dev/null; then
  ok "T1: HEAD contains the pinned release (so the old AT-PIN branch would fire)"
else
  bad "T1: HEAD does not contain the pin (fixture wrong)"
fi

# ---------------------------------------------------------------------------
hdr "T2 — fixed: the ladder converges FORWARD to origin/main (never below the pin, local commit kept)"
LOGF="$ROOT/t2.log"
if run_ladder "$CO" "$PIN" "$LOGF"; then RC=0; else RC=$?; fi
grep -q 'FAILINSTALL' "$LOGF" && bad "T2: ladder called fail_install" || ok "T2: ladder did not fail_install"
[ "$RC" -eq 0 ] && ok "T2: ladder returned 0" || bad "T2: ladder returned $RC"
grep -q 'converged forward' "$LOGF" && ok "T2: ladder logged the forward convergence into origin/main" \
  || bad "T2: ladder did not log a forward convergence"
if git -C "$CO" merge-base --is-ancestor origin/main HEAD 2>/dev/null; then
  ok "T2: origin/main IS now an ancestor of HEAD (the updater predicate would pass)"
else
  bad "T2: HEAD still does not contain origin/main — the FATAL would persist"
fi
git -C "$CO" merge-base --is-ancestor "$PIN" HEAD 2>/dev/null \
  && ok "T2: the pin is still contained (never moved below the pinned release)" \
  || bad "T2: HEAD moved below the pinned release"
git -C "$CO" merge-base --is-ancestor "$LOCAL" HEAD 2>/dev/null \
  && ok "T2: the box's local commit survived the convergence" \
  || bad "T2: the box's local commit was LOST"
grep -q '^CC_AT_PIN=0$' "$LOGF" \
  && ok "T2: CC_AT_PIN=0 (canonical deploy still rebuilds the moved checkout)" \
  || bad "T2: CC_AT_PIN not 0 — the moved checkout would not be deployed"
TIP="$(git -C "$CO" rev-parse origin/main)"
grep -q "^CC_UPDATE_TARGET=$TIP$" "$LOGF" \
  && ok "T2: the deploy target was retargeted to the converged origin/main tip (update.sh cannot revert to the pin)" \
  || bad "T2: deploy target not retargeted — update.sh could revert HEAD to the pin"
rm -rf "$ROOT"

# ---------------------------------------------------------------------------
hdr "T3 — no-op: a checkout already current on origin/main is left alone"
read -r ROOT ORIGIN SEED <<EOF
$(build_origin)
EOF
PIN="$(git -C "$SEED" rev-parse v7.6.112)"
advance_origin "$SEED"
CO="$ROOT/checkout"
git clone --quiet "$ORIGIN" "$CO"
git -C "$CO" symbolic-ref refs/remotes/origin/HEAD refs/remotes/origin/main
BEFORE="$(git_id "$CO")"
LOGF="$ROOT/t3.log"
if run_ladder "$CO" "$PIN" "$LOGF"; then ok "T3: ladder returned 0"; else bad "T3: ladder returned nonzero"; fi
[ "$(git_id "$CO")" = "$BEFORE" ] && ok "T3: the current checkout was not moved" \
  || bad "T3: the current checkout was moved"
grep -q '^CC_AT_PIN=1$' "$LOGF" && ok "T3: CC_AT_PIN=1 (an unchanged checkout is not redeployed)" \
  || bad "T3: CC_AT_PIN not 1 on a current checkout"
rm -rf "$ROOT"

# ---------------------------------------------------------------------------
printf '\n\033[1m%d passed, %d failed\033[0m\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1

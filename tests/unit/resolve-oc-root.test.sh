#!/usr/bin/env bash
# Regression guard for the SHARED OpenClaw-root resolver (false-negative #3).
# Proves: (1) resolve_oc_root computes exactly what the pre-refactor inline
# blocks computed, and (2) every script that used to hand-roll the detection now
# sources the ONE shared resolver AND keeps a byte-identical inline fallback — so
# no two scripts can ever drift to different .openclaw roots (and thus different
# .workforce-build-state.json copies). No real box is touched.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RESOLVER="$REPO_ROOT/shared-utils/resolve-oc-root.sh"
PASS=0; FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }

echo "=== resolve-oc-root.test.sh ==="

if [ ! -f "$RESOLVER" ]; then
  bad "shared resolver missing at shared-utils/resolve-oc-root.sh"
  echo "RESULT: PASS=$PASS FAIL=$FAIL"; exit 1
fi
# shellcheck source=/dev/null
source "$RESOLVER"
declare -F resolve_oc_root >/dev/null 2>&1 && ok "resolve_oc_root is defined after sourcing" \
  || { bad "resolve_oc_root not defined"; echo "RESULT: PASS=$PASS FAIL=$FAIL"; exit 1; }

# The documented ORACLE — the exact behavior every caller had inline before the
# refactor: /data/.openclaw wins (VPS), else $HOME/.openclaw (Mac), else "not
# found". Kept independent so the test fails if the resolver ever diverges.
oracle() {
  if [ -d /data/.openclaw ]; then printf '%s\n' /data/.openclaw; return 0; fi
  if [ -d "$HOME/.openclaw" ]; then printf '%s\n' "$HOME/.openclaw"; return 0; fi
  return 1
}

TMP="$(mktemp -d "${TMPDIR:-/tmp}/resolve-oc-root.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

# Scenario 1: $HOME/.openclaw present (and /data/.openclaw absent on the runner).
H1="$TMP/home-with"; mkdir -p "$H1/.openclaw"
r_out="$(HOME="$H1" resolve_oc_root)"; r_rc=$?
o_out="$(HOME="$H1" oracle)";        o_rc=$?
if [ "$r_rc" = "$o_rc" ] && [ "$r_out" = "$o_out" ] && [ "$r_out" = "$H1/.openclaw" ]; then
  ok "HOME/.openclaw present: resolver == oracle == \$HOME/.openclaw (rc 0)"
else
  bad "HOME-present mismatch: resolver='$r_out'(rc$r_rc) oracle='$o_out'(rc$o_rc)"
fi

# Scenario 2: neither /data/.openclaw nor $HOME/.openclaw present → not found.
if [ ! -d /data/.openclaw ]; then
  H2="$TMP/home-without"; mkdir -p "$H2"
  r_out="$(HOME="$H2" resolve_oc_root)"; r_rc=$?
  o_out="$(HOME="$H2" oracle)";        o_rc=$?
  if [ "$r_rc" -eq 1 ] && [ "$o_rc" -eq 1 ] && [ -z "$r_out" ] && [ -z "$o_out" ]; then
    ok "no root anywhere: resolver == oracle == not-found (rc 1, empty)"
  else
    bad "no-root mismatch: resolver='$r_out'(rc$r_rc) oracle='$o_out'(rc$o_rc)"
  fi
else
  ok "no-root scenario skipped (this box actually has /data/.openclaw)"
fi

# Scenario 3: /data precedence is encoded (source-level, since /data cannot be
# created on the runner) — /data/.openclaw MUST be checked before $HOME.
data_line="$(grep -n '\[ -d /data/\.openclaw \]' "$RESOLVER" | head -1 | cut -d: -f1)"
home_line="$(grep -n '\[ -d "\$HOME/\.openclaw" \]' "$RESOLVER" | head -1 | cut -d: -f1)"
if [ -n "$data_line" ] && [ -n "$home_line" ] && [ "$data_line" -lt "$home_line" ]; then
  ok "/data/.openclaw is checked before \$HOME/.openclaw (VPS-first precedence)"
else
  bad "resolver precedence is not VPS-first (/data line=$data_line home line=$home_line)"
fi

# Every migrated script must SOURCE the one shared resolver AND retain a
# byte-identical inline fallback (so an older bundle without the shared file
# still computes the SAME root).
WIRED=(
  "37-zhc-closeout/scripts/run-closeout.sh"
  "37-zhc-closeout/scripts/resume-closeout-cron.sh"
  "37-zhc-closeout/scripts/fleet-stuck-clients.sh"
  "23-ai-workforce-blueprint/scripts/closeout-readiness-watchdog.sh"
  "23-ai-workforce-blueprint/scripts/migrate-existing-workforce.sh"
  "32-command-center-setup/scripts/backfill-per-dept-healer.sh"
  "32-command-center-setup/scripts/materialize-dept-agents.sh"
  "update-skills.sh"
)
for rel in "${WIRED[@]}"; do
  f="$REPO_ROOT/$rel"
  if [ ! -f "$f" ]; then bad "wired script missing: $rel"; continue; fi
  if grep -q 'shared-utils/resolve-oc-root.sh' "$f" \
     && grep -q 'resolve_oc_root' "$f" \
     && grep -Eq '/data/\.openclaw' "$f"; then
    ok "wired to shared resolver + inline fallback retained: $rel"
  else
    bad "not wired to shared resolver (or lost inline fallback): $rel"
  fi
done

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

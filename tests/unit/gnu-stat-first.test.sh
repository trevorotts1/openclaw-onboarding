#!/usr/bin/env bash
# gnu-stat-first.test.sh — class C: mtime / mode / owner lookups must work under
# GNU (Linux) AND BSD (Mac) stat.
#
# THE BUG: `stat -f FMT f || stat -c FMT f`. GNU reads `-f` as "filesystem
# status" and FMT as a second FILE: it prints a multi-line filesystem block for
# f to stdout, fails on FMT, and only then falls over to `-c`. The captured
# value is that block plus the number, so the lock-age arithmetic errors out
# (stale locks never clear) and chmod/chown receive garbage. Same class as the
# run-full-install.sh _cc_mtime fix (PR #1242, tests/unit/cc-mtime-portable).
#
# Runs the REAL functions under every stat flavour available here: native, plus
# GNU via gstat (coreutils) shimmed in as `stat` on a Mac. CI (ubuntu) is GNU.
set -uo pipefail
P="[gnu-stat-first]"; PASS=0; FAIL=0
pass() { PASS=$((PASS+1)); echo "$P PASS: $*"; }
fail() { FAIL=$((FAIL+1)); echo "$P FAIL: $*" >&2; }

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT

# ── static: no BSD-first chain left in the fixed files ──────────────────────
FILES=(install.sh update-skills.sh scripts/reconcile-rr-agent-map.sh
       15-blackceo-team-management/scripts/lib/rr-config-lock.sh
       15-blackceo-team-management/scripts/lib/rr-promote-atomic.sh
       23-ai-workforce-blueprint/scripts/resume-workforce-build.sh)
for f in "${FILES[@]}"; do
  hits="$(grep -nE "stat -f ['\"]?%[^|]*\|\| *stat -c" "$ROOT/$f" || true)"
  [[ -z "$hits" ]] && pass "$f: no BSD-first stat chain" || fail "$f: BSD-first stat chain: $hits"
done

# ── behavioural: extract the real functions ─────────────────────────────────
awk '/^_rr_lock_age\(\)/{p=1} p{print} p&&/^}$/{exit}' \
  "$ROOT/15-blackceo-team-management/scripts/lib/rr-config-lock.sh" > "$TMP/lockage.sh"
awk '/^dir_age_seconds\(\)/{p=1} p{print} p&&/^}$/{exit}' \
  "$ROOT/scripts/reconcile-rr-agent-map.sh" > "$TMP/dirage.sh"
awk '/^  _lsc_mode_owner\(\)/{p=1} p{print} p&&/^  }$/{exit}' "$ROOT/install.sh" > "$TMP/modeowner.sh"
for fn in lockage dirage modeowner; do
  [[ -s "$TMP/$fn.sh" ]] || { echo "$P FATAL: could not extract $fn" >&2; exit 1; }
done
# rr-promote-atomic.sh's MODE line and resume-workforce-build.sh's marker-age
# lines are top-level / mid-function: run those exact lines.
grep -A3 '^MODE="$(stat' "$ROOT/15-blackceo-team-management/scripts/lib/rr-promote-atomic.sh" \
  | sed -n '1,2p' > "$TMP/promote-mode.sh"
grep -A3 '    m="$(stat -c %Y "$INTERVIEW_REPORT_MARKER"' "$ROOT/23-ai-workforce-blueprint/scripts/resume-workforce-build.sh" \
  | sed -n '1,3p' > "$TMP/report-age.sh"

mkdir -p "$TMP/lockdir"; touch "$TMP/f"; chmod 640 "$TMP/f"

declare -a FLAVOURS=("native:$PATH")
if command -v gstat >/dev/null 2>&1; then
  mkdir -p "$TMP/gnu"; ln -s "$(command -v gstat)" "$TMP/gnu/stat"
  FLAVOURS+=("gnu-shim:$TMP/gnu:$PATH")
fi
stat --version >/dev/null 2>&1 && echo "$P native stat is GNU" || echo "$P native stat is BSD"

for f in "${FLAVOURS[@]}"; do
  name="${f%%:*}"; path="${f#*:}"
  run() { PATH="$path" bash -c "set -u; $1" _ "${@:2}" 2>&1; }

  out="$(run 'source "$1"; _rr_lock_age "$2"' "$TMP/lockage.sh" "$TMP/lockdir")"
  [[ "$out" =~ ^[0-9]{1,3}$ ]] && pass "$name: rr-config-lock _rr_lock_age -> $out" \
    || fail "$name: rr-config-lock _rr_lock_age -> $(printf '%s' "$out" | head -2 | tr '\n' ' ')"

  out="$(run 'source "$1"; dir_age_seconds "$2"' "$TMP/dirage.sh" "$TMP/lockdir")"
  [[ "$out" =~ ^[0-9]{1,3}$ ]] && pass "$name: reconcile-rr-agent-map dir_age_seconds -> $out" \
    || fail "$name: reconcile-rr-agent-map dir_age_seconds -> $(printf '%s' "$out" | head -2 | tr '\n' ' ')"

  out="$(run 'source "$1"; _lsc_mode_owner "$2"' "$TMP/modeowner.sh" "$TMP/f")"
  [[ "$out" =~ ^640\|[0-9]+:[0-9]+$ ]] && pass "$name: install.sh _lsc_mode_owner -> $out" \
    || fail "$name: install.sh _lsc_mode_owner -> $(printf '%s' "$out" | head -2 | tr '\n' ' ')"

  out="$(run 'LIVE="$2"; source "$1"; printf %s "$MODE"' "$TMP/promote-mode.sh" "$TMP/f")"
  [[ "$out" == "640" ]] && pass "$name: rr-promote-atomic MODE -> $out" \
    || fail "$name: rr-promote-atomic MODE -> $(printf '%s' "$out" | head -2 | tr '\n' ' ')"

  out="$(run 'INTERVIEW_REPORT_MARKER="$2"; source "$1"; age_h=$(( ( $(date -u +%s) - m ) / 3600 )); echo "$age_h"' "$TMP/report-age.sh" "$TMP/f")"
  [[ "$out" == "0" ]] && pass "$name: resume-workforce-build marker age -> ${out}h" \
    || fail "$name: resume-workforce-build marker age -> $(printf '%s' "$out" | head -2 | tr '\n' ' ')"
done

echo "$P Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]]

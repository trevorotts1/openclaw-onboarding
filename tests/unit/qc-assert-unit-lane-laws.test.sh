#!/usr/bin/env bash
# tests/unit/qc-assert-unit-lane-laws.test.sh
#
# Proves scripts/qc-assert-unit-lane-laws.sh DISCRIMINATES: one clean case that
# must pass and one case per law that must fail for exactly that law. A gate that
# cannot fail is not a gate, so every FAIL case also asserts the law name in the
# output — a blanket non-zero would otherwise pass this suite.
#
# Offline. No network, no gh, no credential. Fixtures are throwaway git repos.
#
# Run: bash tests/unit/qc-assert-unit-lane-laws.test.sh

set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
GATE="$ROOT/scripts/qc-assert-unit-lane-laws.sh"

[ -f "$GATE" ] || { echo "FATAL: gate not found at $GATE" >&2; exit 2; }

WORK="$(mktemp -d "${TMPDIR:-/tmp}/unit-lane-laws.XXXXXX")"
cleanup() { rm -rf "$WORK"; }
# KEEP_WORK=1 keeps the fixtures for debugging.
if [ -z "${KEEP_WORK:-}" ]; then trap cleanup EXIT; fi

FAILURES=0
CHECKS=0

fail() { echo "FAIL: $*" >&2; FAILURES=$((FAILURES + 1)); }
ok()   { echo "ok: $*"; }

assert_rc() { # name expected actual
  CHECKS=$((CHECKS + 1))
  if [ "$2" -eq "$3" ]; then ok "$1 (rc=$3)"; else fail "$1: expected rc=$2, got rc=$3"; fi
}

assert_has() { # name haystack needle
  CHECKS=$((CHECKS + 1))
  case "$2" in
    *"$3"*) ok "$1" ;;
    *) fail "$1: output does not contain '$3'" ;;
  esac
}

assert_lacks() { # name haystack needle
  CHECKS=$((CHECKS + 1))
  case "$2" in
    *"$3"*) fail "$1: output LEAKED '$3'" ;;
    *) ok "$1" ;;
  esac
}

BOT="41898282+github-actions[bot]@users.noreply.github.com"
PIN="49-signature-funnel/scripts/SF-PROVER-PIN.sha256"
CLONE="$WORK/clone"
TMPL="$WORK/tmp"
mkdir -p "$CLONE" "$TMPL"

# ── fixture builder ──────────────────────────────────────────────────────────
# mk_repo <name> — sets REPO_PATH (never echo: a command substitution would run
# in a subshell and lose BASE).
BASE=""
REPO_PATH=""
mk_repo() {
  local d="$WORK/repo-$1"
  mkdir -p "$d"
  git -C "$d" init -q -b main
  git -C "$d" config user.email "builder@example.test"
  git -C "$d" config user.name "builder"
  printf 'base\n' > "$d/base.txt"
  git -C "$d" add -A
  git -C "$d" commit -qm "base"
  REPO_PATH="$d"
  BASE="$(git -C "$d" rev-parse HEAD)"
}

# head_commit <repo> <msg> [file]
head_commit() {
  local d="$1" msg="$2" f="${3:-note.txt}"
  mkdir -p "$d/$(dirname "$f")"
  printf '%s\n' "$msg" >> "$d/$f"
  git -C "$d" add -A
  git -C "$d" commit -qm "$msg"
  git -C "$d" rev-parse HEAD
}

# bot_commit_pin <repo> <msg>
bot_commit_pin() {
  local d="$1" msg="$2"
  mkdir -p "$d/$(dirname "$PIN")"
  printf 'pin-%s\n' "$msg" >> "$d/$PIN"
  git -C "$d" add -A
  GIT_AUTHOR_EMAIL="$BOT" GIT_COMMITTER_EMAIL="$BOT" GIT_AUTHOR_NAME="github-actions[bot]" \
    GIT_COMMITTER_NAME="github-actions[bot]" git -C "$d" commit -qm "$msg"
  git -C "$d" rev-parse HEAD
}

# hand_commit_pin <repo> <msg>
hand_commit_pin() {
  local d="$1" msg="$2"
  mkdir -p "$d/$(dirname "$PIN")"
  printf 'pin-%s\n' "$msg" >> "$d/$PIN"
  git -C "$d" add -A
  git -C "$d" commit -qm "$msg"
  git -C "$d" rev-parse HEAD
}

# good_transcript <path> [extra lines...]
good_transcript() {
  local t="$1"; shift
  {
    echo "\$ gh pr list --state open"
    echo "(no open PR touches the files this lane edits)"
    echo "\$ git log --oneline -5 origin/main -- note.txt"
    echo "abc1234 previous change"
    echo "\$ cd $CLONE"
    echo "\$ git checkout -b build/unit"
    echo "work..."
    local line
    for line in "$@"; do echo "$line"; done
  } > "$t"
}

run_gate() { # <outfile> <args...>
  local out="$1"; shift
  "$GATE" "$@" > "$out" 2>&1
  echo $?
}

COMMON_ARGS=(
  --unit INST-001
  --builder-model deepseek-chain
  --qc-model opus-chain
  --clone "$CLONE"
  --tmpdir "$TMPL"
  --main-ref main
)

# ── 1. clean case passes ────────────────────────────────────────────────────
mk_repo clean; R="$REPO_PATH"; B1="$BASE"; H="$(head_commit "$R" "clean change")"
good_transcript "$WORK/t-clean.txt"
RC="$(run_gate "$WORK/o-clean.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --main-ref "$B1" --allow-unmerged --qc-verdict-text "CONFIRMED")"
OUT="$(cat "$WORK/o-clean.txt")"
assert_rc "clean: exit" 0 "$RC"
assert_has "clean: no FAIL" "$OUT" "0 FAIL"
assert_has "clean: L13 SKIP reported separately" "$OUT" "L13 SKIP"

# ── 2. L4 --no-verify ───────────────────────────────────────────────────────
good_transcript "$WORK/t.txt" '$ git commit --no-verify -m "x"'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L4: exit" 1 "$RC"
assert_has "L4 FAIL named" "$(cat "$WORK/o.txt")" "L4 FAIL"

# ── 3. L7 ssh ───────────────────────────────────────────────────────────────
good_transcript "$WORK/t.txt" '$ ssh deploy@example.test uptime'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L7: exit" 1 "$RC"
assert_has "L7 FAIL named" "$(cat "$WORK/o.txt")" "L7 FAIL"

# ── 4. L8 fleet contact ─────────────────────────────────────────────────────
good_transcript "$WORK/t.txt" '$ ssh rescue-someone uptime'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L8: exit" 1 "$RC"
assert_has "L8 FAIL named" "$(cat "$WORK/o.txt")" "L8 FAIL"

# ── 5. L9 secret printed (value must never be echoed) ───────────────────────
SECRET="ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
good_transcript "$WORK/t.txt" "\$ export TOKEN=$SECRET"
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
OUT="$(cat "$WORK/o.txt")"
assert_rc "L9: exit" 1 "$RC"
assert_has "L9 FAIL named" "$OUT" "L9 FAIL"
assert_lacks "L9: secret value NOT echoed" "$OUT" "$SECRET"

# ── 6. L10 missing collision checks ─────────────────────────────────────────
{ echo "\$ cd $CLONE"; echo "edited note.txt directly"; } > "$WORK/t.txt"
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L10 missing: exit" 1 "$RC"
assert_has "L10 missing FAIL named" "$(cat "$WORK/o.txt")" "L10 FAIL"
assert_has "L10 missing names the open-PR check" "$(cat "$WORK/o.txt")" "no 'gh pr list --state open' in the transcript"

# ── 7. L10 out of order ─────────────────────────────────────────────────────
{ echo "\$ git log --oneline -5 origin/main -- note.txt"; echo "\$ gh pr list --state open"; echo "\$ cd $CLONE"; } > "$WORK/t.txt"
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L10 order: exit" 1 "$RC"
assert_has "L10 order FAIL named" "$(cat "$WORK/o.txt")" "open-PR check runs AFTER"

# ── 8. L11 two PRs without a recut pointer ──────────────────────────────────
good_transcript "$WORK/t.txt"
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --pr 3002 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L11 no pointer: exit" 1 "$RC"
assert_has "L11 no pointer FAIL named" "$(cat "$WORK/o.txt")" "L11 FAIL"

# ── 9. L11 two PRs WITH a recut pointer passes ──────────────────────────────
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --pr 3002 --recut-pointer "#3002 replaces #3001" \
  --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L11 with pointer: exit" 0 "$RC"
assert_has "L11 with pointer PASS" "$(cat "$WORK/o.txt")" "L11 PASS"

# ── 10. L12 merge main into the branch ──────────────────────────────────────
mk_repo merge; R2="$REPO_PATH"; B2="$BASE"
head_commit "$R2" "work" >/dev/null
git -C "$R2" checkout -q -b side
head_commit "$R2" "side work" side.txt >/dev/null
git -C "$R2" checkout -q main
git -C "$R2" merge -q --no-ff side -m "Merge remote-tracking branch 'origin/main' into build/unit"
H2="$(git -C "$R2" rev-parse HEAD)"
good_transcript "$WORK/t2.txt"
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R2" --base "$B2" --head "$H2" \
  --transcript "$WORK/t2.txt" --pr 3003 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L12: exit" 1 "$RC"
assert_has "L12 FAIL named" "$(cat "$WORK/o.txt")" "L12 FAIL"

# ── 11. L13 not an ancestor, no --allow-unmerged ────────────────────────────
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --main-ref "$B1" --qc-verdict-text "CONFIRMED")"
assert_rc "L13 unmerged: exit" 1 "$RC"
assert_has "L13 FAIL named" "$(cat "$WORK/o.txt")" "L13 FAIL"

# ── 12. L13 ancestry passes when head is on the ref ─────────────────────────
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --main-ref HEAD --qc-verdict-text "CONFIRMED")"
assert_rc "L13 landed: exit" 0 "$RC"
assert_has "L13 PASS named" "$(cat "$WORK/o.txt")" "L13 PASS"

# ── 13. L14 workspace path outside clone/tmpdir ─────────────────────────────
good_transcript "$WORK/t.txt" '$ cd /somewhere/else/entirely'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L14: exit" 1 "$RC"
assert_has "L14 FAIL named" "$(cat "$WORK/o.txt")" "L14 FAIL"

# ── 14. L15 same model ──────────────────────────────────────────────────────
RC="$(run_gate "$WORK/o.txt" --unit INST-001 --builder-model opus-chain --qc-model opus-chain \
  --clone "$CLONE" --tmpdir "$TMPL" --main-ref main --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L15: exit" 1 "$RC"
assert_has "L15 FAIL named" "$(cat "$WORK/o.txt")" "L15 FAIL"

# ── 15. L16 no verdict ──────────────────────────────────────────────────────
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --allow-unmerged --qc-verdict-text "looks fine to me")"
assert_rc "L16 missing: exit" 1 "$RC"
assert_has "L16 missing FAIL named" "$(cat "$WORK/o.txt")" "L16 FAIL"

# ── 16. L16 FAILED verdict on a landed commit ───────────────────────────────
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R" --base "$B1" --head "$H" \
  --transcript "$WORK/t-clean.txt" --pr 3001 --main-ref HEAD --qc-verdict-text "FAILED: two defects")"
assert_rc "L16 failed+landed: exit" 1 "$RC"
assert_has "L16 failed+landed FAIL named" "$(cat "$WORK/o.txt")" "QC said FAILED but the commit is landed"

# ── 17. L5 hand-written pin ─────────────────────────────────────────────────
mk_repo handpin; R3="$REPO_PATH"; B3="$BASE"
H3="$(hand_commit_pin "$R3" "hand edit the pin")"
good_transcript "$WORK/t3.txt" '$ git log --oneline -5 origin/main -- 49-signature-funnel/scripts/SF-PROVER-PIN.sha256'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R3" --base "$B3" --head "$H3" \
  --transcript "$WORK/t3.txt" --pr 3004 --allow-unmerged --qc-verdict-text "CONFIRMED")"
assert_rc "L5: exit" 1 "$RC"
assert_has "L5 FAIL named" "$(cat "$WORK/o.txt")" "L5 FAIL"

# ── 18. L5 passes, L6 fails, on two bot pin commits ─────────────────────────
mk_repo twopin; R4="$REPO_PATH"; B4="$BASE"
bot_commit_pin "$R4" "mint one" >/dev/null
H4="$(bot_commit_pin "$R4" "mint two")"
good_transcript "$WORK/t4.txt" '$ git log --oneline -5 origin/main -- 49-signature-funnel/scripts/SF-PROVER-PIN.sha256'
RC="$(run_gate "$WORK/o.txt" "${COMMON_ARGS[@]}" --repo "$R4" --base "$B4" --head "$H4" \
  --transcript "$WORK/t4.txt" --pr 3005 --allow-unmerged --qc-verdict-text "CONFIRMED")"
OUT="$(cat "$WORK/o.txt")"
assert_rc "L6: exit" 1 "$RC"
assert_has "L6 FAIL named" "$OUT" "L6 FAIL"
assert_has "L5 still PASS with two bot mints" "$OUT" "L5 PASS"

# ── 19. usage error fails closed ────────────────────────────────────────────
RC="$(run_gate "$WORK/o.txt" --unit INST-001 --base "$BASE" \
  --builder-model a --qc-model b --clone "$CLONE" --tmpdir "$TMPL" --pr 1)"
assert_rc "usage: missing --head exits 2" 2 "$RC"

# ── summary ─────────────────────────────────────────────────────────────────
echo "---"
if [ "$FAILURES" -gt 0 ]; then
  echo "SUITE FAILED: $FAILURES of $CHECKS assertions failed" >&2
  exit 1
fi
echo "SUITE PASSED: $CHECKS assertions"
exit 0

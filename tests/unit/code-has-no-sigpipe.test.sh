#!/usr/bin/env bash
# tests/unit/code-has-no-sigpipe.test.sh
#
# Regression lock for the intermittent CI guard failure diagnosed 2026-09-17.
#
# THE BUG
#   scripts/guard-ghl-activation-resilience.sh runs under `set -uo pipefail` and
#   defined its matcher as:
#
#       code_has() { printf '%s' "$1" | grep -Eq "$2"; }
#
#   The blob it greps is the stripped source of 06-ghl-install-pages/tools/
#   inject-ghl-auth.sh — ~40 KB, more than one write() worth. `grep -q` exits on
#   the FIRST match and closes the read end while printf is still writing, printf
#   takes SIGPIPE (exit 141), and `pipefail` makes the whole pipeline 141. The
#   `if` sees non-zero and reports a marker that IS PRESENT as ABSENT.
#
#   It is intermittent because it is a scheduling race: if printf's last write
#   lands before grep is scheduled to exit, nothing happens. Evidence — run
#   35227933960's sibling job on PR #1184 logged
#       scripts/guard-ghl-activation-resilience.sh: line 175: printf: write error: Broken pipe
#   one line before
#       ✗ FAIL — R3 ABSENT: token-only cookie re-assert ...
#   while the identical tree passed on main.
#
# THE FIX
#   A here-string. Bash feeds grep directly, so there is no second process to
#   kill and no race:  code_has() { grep -Eq "$2" <<<"$1"; }
#
# WHAT THIS TEST LOCKS
#   T1  The REAL definitions in the guard use a here-string and pipe nothing.
#   T2  50/50 trials: a 200 KB blob whose match is on line 1 returns 0 under
#       `set -o pipefail`.
#   T3  CONTROL — the same 50 trials with a genuinely ABSENT pattern return 1.
#       Without this, T2 would pass for a matcher that always returns 0.
#   T4  Here-string semantics are identical to the old pipe for this use: `^`
#       and `$` anchors still work, the case-insensitive variant still works,
#       and the newline `<<<` appends does not make a real pattern match an
#       empty blob.
#   T5  No CI guard / qc-assert script has regrown `printf|echo ... | grep -q`.
#
# Bash 3.2 safe: no associative arrays, no mapfile, no case modifiers.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GUARD="$REPO_ROOT/scripts/guard-ghl-activation-resilience.sh"

PASS=0
FAIL=0
ok()  { printf '  \033[32m✓\033[0m %s\n' "$1"; PASS=$((PASS + 1)); }
bad() { printf '  \033[31m✗\033[0m %s\n' "$1"; FAIL=$((FAIL + 1)); }

echo ""
echo "═══ code-has-no-sigpipe — grep -q must never SIGPIPE a producer under pipefail ═══"
echo ""

if [ ! -f "$GUARD" ]; then
  bad "guard script not found: $GUARD"
  echo ""; echo "FAILED — cannot run without the guard under test."; exit 1
fi

# ── T1. The real definitions, read out of the guard itself ───────────────────
echo "── T1. code_has / code_has_i are here-string matchers (read from the guard) ──"

DEFS="$(grep -E '^code_has(_i)?\(\)' "$GUARD")"

if [ -z "$DEFS" ]; then
  bad "T1: no code_has()/code_has_i() definition found in ${GUARD#$REPO_ROOT/}"
else
  n_defs=$(printf '%s\n' "$DEFS" | grep -c '^code_has')
  if [ "$n_defs" -eq 2 ]; then
    ok "T1: found both definitions in ${GUARD#$REPO_ROOT/}"
  else
    bad "T1: expected 2 definitions (code_has, code_has_i), found $n_defs"
  fi

  if grep -q '<<<' <<<"$DEFS"; then
    ok "T1: definitions feed grep from a here-string"
  else
    bad "T1: definitions do NOT use a here-string — the SIGPIPE race is back: $DEFS"
  fi

  if grep -qE '\|[[:space:]]*grep' <<<"$DEFS"; then
    bad "T1: definitions pipe into grep — REGRESSION, grep -q will SIGPIPE the producer: $DEFS"
  else
    ok "T1: definitions pipe nothing into grep"
  fi
fi

# Load the REAL definitions so T2-T4 test shipped code, not a copy.
eval "$DEFS"

if ! type code_has >/dev/null 2>&1 || ! type code_has_i >/dev/null 2>&1; then
  bad "T1: could not load code_has/code_has_i from the guard"
  echo ""; echo "FAILED — the functions under test would not load."; exit 1
fi

# ── Build a ~200 KB multi-line blob whose match is on the FIRST line ─────────
FILLER="$(head -c 200000 /dev/zero | tr '\0' 'x' | fold -w 120)"
BLOB="1:MARKER_PRESENT_AT_TOP
$FILLER
99999:MARKER_PRESENT_AT_END"

blob_bytes=${#BLOB}
if [ "$blob_bytes" -lt 200000 ]; then
  bad "fixture too small (${blob_bytes} bytes) — a blob under one pipe buffer cannot exercise the race"
else
  ok "fixture: ${blob_bytes}-byte multi-line blob, match on line 1"
fi

# ── T2. 50 consecutive trials, present marker, under pipefail ────────────────
echo ""
echo "── T2. 50x: a PRESENT marker on line 1 of a 200 KB blob must return 0 ──"
set -o pipefail
misses=0
i=1
while [ "$i" -le 50 ]; do
  if ! code_has "$BLOB" 'MARKER_PRESENT_AT_TOP'; then
    misses=$((misses + 1))
  fi
  i=$((i + 1))
done
if [ "$misses" -eq 0 ]; then
  ok "T2: 50/50 trials found the marker (0 false negatives)"
else
  bad "T2: $misses/50 trials reported a PRESENT marker as ABSENT — SIGPIPE race is live"
fi

# ── T3. CONTROL: the same 50 trials with an ABSENT pattern must return 1 ─────
echo ""
echo "── T3. CONTROL — an ABSENT pattern must return 1 (proves T2 can fail) ──"
false_hits=0
i=1
while [ "$i" -le 50 ]; do
  if code_has "$BLOB" 'MARKER_THAT_IS_NOWHERE_IN_THE_BLOB'; then
    false_hits=$((false_hits + 1))
  fi
  i=$((i + 1))
done
if [ "$false_hits" -eq 0 ]; then
  ok "T3: 50/50 trials correctly reported the absent pattern as absent"
else
  bad "T3: $false_hits/50 trials matched a pattern that is not in the blob — the matcher is vacuous"
fi

# ── T4. Here-string semantics match the old pipe for this use ────────────────
echo ""
echo "── T4. here-string semantics are identical for these patterns ──"

code_has "$BLOB" '^1:MARKER_PRESENT_AT_TOP$' \
  && ok "T4: ^...\$ anchors still match a full interior line" \
  || bad "T4: ^...\$ anchored match broke"

code_has "$BLOB" '^99999:MARKER_PRESENT_AT_END$' \
  && ok "T4: the LAST line still matches with a \$ anchor (trailing newline is inert)" \
  || bad "T4: last-line \$ anchored match broke"

code_has_i "$BLOB" 'marker_present_at_top' \
  && ok "T4: code_has_i is case-insensitive" \
  || bad "T4: code_has_i lost case-insensitivity"

code_has "$BLOB" 'marker_present_at_top' \
  && bad "T4: code_has matched case-insensitively — it must be case-SENSITIVE" \
  || ok "T4: code_has stays case-sensitive"

# `<<<` appends one newline, so an EMPTY blob is one empty line rather than no
# input. Every pattern these guards use requires at least one character, so an
# empty blob must still not match.
if code_has "" 'ACT_MAX_ATTEMPTS'; then
  bad "T4: an empty blob matched a real pattern — the appended newline changed behaviour"
else
  ok "T4: an empty blob matches no real pattern (appended newline is inert)"
fi

# ── T5. The class has not regrown anywhere in the CI guard surface ───────────
echo ""
echo "── T5. no CI guard / qc-assert script pipes an in-memory string into grep -q ──"

offenders="$(
  cd "$REPO_ROOT" || exit 0
  find . -path ./.git -prune -o \
       \( -name 'guard-*.sh' -o -name 'qc-assert-*.sh' \) -print 2>/dev/null \
  | sort \
  | while IFS= read -r f; do
      grep -HnE '^[^#]*(printf|echo)[^|]*\|[^|]*grep[[:space:]]+-[A-Za-z]*q' "$f" 2>/dev/null
    done
)"

if [ -z "$offenders" ]; then
  ok "T5: none found"
else
  bad "T5: the SIGPIPE-prone shape is back in a CI guard script:"
  printf '%s\n' "$offenders" | sed 's/^/        /'
  echo "        Remedy: grep -Eq \"\$pattern\" <<<\"\$string\"  (here-string, no second process)"
fi

# ── Verdict ──────────────────────────────────────────────────────────────────
echo ""
if [ "$FAIL" -eq 0 ]; then
  printf '\033[32mcode-has-no-sigpipe PASS — %d checks, 0 failures.\033[0m\n' "$PASS"
  echo ""
  exit 0
fi
printf '\033[31mcode-has-no-sigpipe FAILED — %d failure(s) of %d checks.\033[0m\n' "$FAIL" "$((PASS + FAIL))"
echo ""
exit 1

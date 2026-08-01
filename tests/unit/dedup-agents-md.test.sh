#!/usr/bin/env bash
# tests/unit/dedup-agents-md.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Regression lock for scripts/dedup-agents-md.py — the mechanical, no-model-
# judgment duplicate-block remover for the LIVE (gateway-injected) AGENTS.md.
#
# ROOT CAUSE THIS COVERS: scripts/apply-fleet-standards.sh stamps ~10 marker-
# guarded blocks into AGENTS.md using `if grep -qF "$MARKER" file; then no-op;
# else cat >> file; fi`. That guard false-negatives whenever a historical
# stamp predates the marker, so the block RE-APPENDS on later runs. Measured
# on a fleet box: up to 8 copies of one heading, ~23,000 bytes of pure
# repetition. Past the empirical ~400,000-char injection ceiling that bloat
# SILENTLY TRUNCATES the file the gateway injects every turn. This suite
# proves the cleanup tool removes ONLY exact duplicates, never a near-
# duplicate, prefers the marked copy, refuses to write an unbalanced
# BEGIN/END result, is idempotent, and cleanly skips when there is nothing to
# do — plus a static check that apply-fleet-standards.sh actually calls it
# before the first marker-guarded stamp (so the surviving copy is the one the
# grep-guard below it then finds).
#
# Fully offline: no network, no openclaw CLI, no client data. Requires
# python3 (stdlib only). Exit 0 = all pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DEDUP="$REPO_ROOT/scripts/dedup-agents-md.py"
FLEET_STD="$REPO_ROOT/scripts/apply-fleet-standards.sh"

PASS=0
FAIL=0
ok()  { PASS=$((PASS + 1)); printf '  PASS: %s\n' "$1"; }
bad() { FAIL=$((FAIL + 1)); printf '  FAIL: %s\n' "$1"; }

echo "=== dedup-agents-md.test.sh ==="

if [ ! -f "$DEDUP" ]; then
  bad "scripts/dedup-agents-md.py exists"
  printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
  exit 1
fi
ok "scripts/dedup-agents-md.py exists"

if python3 -m py_compile "$DEDUP" 2>/dev/null; then
  ok "scripts/dedup-agents-md.py compiles"
else
  bad "scripts/dedup-agents-md.py compiles"
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/dedup-agents-md.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

run_dedup() {
  # $1 = file, remaining args passed through
  local f="$1"; shift
  python3 "$DEDUP" --file "$f" "$@"
}

# ---------------------------------------------------------------------------
# (a) exact duplicates removed -- keeps exactly one, reports the count
# ---------------------------------------------------------------------------
echo "-- (a) exact duplicates removed --"
F_A="$WORK/a-AGENTS.md"
HEADING_A="## Persona Reflex (stamped by apply-fleet-standards.sh)"
BODY_A=$'\nEvery specialist checks persona assignment.\n\n'
{
  printf '# AGENTS.md\n\nPreamble text.\n\n'
  for _i in 1 2 3 4 5; do printf '%s\n%s' "$HEADING_A" "$BODY_A"; done
  printf '## Unrelated Section\n\nOther content.\n'
} > "$F_A"

OUT_A="$(run_dedup "$F_A" --apply)"; RC_A=$?
[ "$RC_A" -eq 0 ] && ok "(a) apply exits 0" || bad "(a) apply exits 0 (rc=$RC_A)"
COUNT_A=$(grep -c -F "$HEADING_A" "$F_A")
[ "$COUNT_A" -eq 1 ] && ok "(a) 5 exact duplicates collapsed to 1" || bad "(a) 5 exact duplicates collapsed to 1 (found $COUNT_A)"
printf '%s\n' "$OUT_A" | grep -q 'blocks_removed=4' && ok "(a) summary reports blocks_removed=4" || bad "(a) summary reports blocks_removed=4"
grep -q 'Unrelated Section' "$F_A" && ok "(a) unrelated trailing content preserved" || bad "(a) unrelated trailing content preserved"
BACKUPS_A=$(find "$WORK" -maxdepth 1 -name 'a-AGENTS.md.bak-dedup-*' | wc -l | tr -d ' ')
[ "$BACKUPS_A" -eq 1 ] && ok "(a) exactly one timestamped backup created" || bad "(a) exactly one timestamped backup created (found $BACKUPS_A)"

# ---------------------------------------------------------------------------
# (b) near-duplicates preserved -- never touched, flagged for manual review
# ---------------------------------------------------------------------------
echo "-- (b) near-duplicates preserved --"
F_B="$WORK/b-AGENTS.md"
cat > "$F_B" <<'EOF'
# AGENTS.md

## Platform Facts (stamped by apply-fleet-standards.sh)

Variant ONE body text.

## Platform Facts (stamped by apply-fleet-standards.sh)

Variant TWO body text (different).

## Trailer

end.
EOF
cp "$F_B" "$WORK/b-before.md"
OUT_B="$(run_dedup "$F_B" --apply)"
if cmp -s "$F_B" "$WORK/b-before.md"; then
  ok "(b) near-duplicate file left byte-identical (no removal)"
else
  bad "(b) near-duplicate file left byte-identical (no removal)"
fi
printf '%s\n' "$OUT_B" | grep -q 'blocks_removed=0' && ok "(b) summary reports blocks_removed=0" || bad "(b) summary reports blocks_removed=0"
printf '%s\n' "$OUT_B" | grep -q 'NEAR-DUP' && ok "(b) NEAR-DUP flagged for manual review" || bad "(b) NEAR-DUP flagged for manual review"

# ---------------------------------------------------------------------------
# (c) marked copy kept over unmarked
# ---------------------------------------------------------------------------
echo "-- (c) marked copy kept over unmarked --"
F_C="$WORK/c-AGENTS.md"
cat > "$F_C" <<'EOF'
# AGENTS.md

## Owner Reporting Rules (stamped by apply-fleet-standards.sh)

Body text identical across all copies.

## Owner Reporting Rules (stamped by apply-fleet-standards.sh)

Body text identical across all copies.

<!-- OWNER_REPORTING_V1 -->
## Owner Reporting Rules (stamped by apply-fleet-standards.sh)

Body text identical across all copies.

EOF
run_dedup "$F_C" --apply >/dev/null
COUNT_C=$(grep -c -F "## Owner Reporting Rules" "$F_C")
[ "$COUNT_C" -eq 1 ] && ok "(c) 3 copies collapsed to 1" || bad "(c) 3 copies collapsed to 1 (found $COUNT_C)"
grep -qF '<!-- OWNER_REPORTING_V1 -->' "$F_C" && ok "(c) the MARKED copy is the one that survived" || bad "(c) the MARKED copy is the one that survived"

# ---------------------------------------------------------------------------
# (d) BEGIN/END pairs stay balanced -- refuses to write an unbalanced result
# ---------------------------------------------------------------------------
echo "-- (d) BEGIN/END pairs stay balanced --"
F_D="$WORK/d-AGENTS.md"
# Three byte-identical "## Foo" occurrences (each body includes its own
# trailing END line as literal text): copy 0 carries the file's ONLY BEGIN
# prefix; copy 1 has no prefix; copy 2 carries a single-token marker prefix.
# Rule 4 prefers the MARKED copy (2) over "first occurrence" (0), so copy 0 --
# and with it the only BEGIN -- is removed, while a surviving copy's body
# still contains an END. That is a genuine BEGIN=0/END=1 imbalance.
cat > "$F_D" <<'EOF'
# AGENTS.md

<!-- BEGIN skill:99-fixture:agents -->
## Foo

Shared body text.
<!-- END skill:99-fixture:agents -->

## Foo

Shared body text.
<!-- END skill:99-fixture:agents -->

<!-- SOME_OTHER_MARKER_V1 -->
## Foo

Shared body text.
<!-- END skill:99-fixture:agents -->

EOF
cp "$F_D" "$WORK/d-before.md"
OUT_D="$(run_dedup "$F_D" --apply)"; RC_D=$?
[ "$RC_D" -eq 3 ] && ok "(d) exit code 3 on refused write" || bad "(d) exit code 3 on refused write (rc=$RC_D)"
if cmp -s "$F_D" "$WORK/d-before.md"; then
  ok "(d) file left untouched when write would unbalance BEGIN/END"
else
  bad "(d) file left untouched when write would unbalance BEGIN/END"
fi
printf '%s\n' "$OUT_D" | grep -qi 'unbalanced' && ok "(d) loud unbalanced/REFUSED message printed" || bad "(d) loud unbalanced/REFUSED message printed"
BACKUPS_D=$(find "$WORK" -maxdepth 1 -name 'd-AGENTS.md.bak-dedup-*' | wc -l | tr -d ' ')
[ "$BACKUPS_D" -eq 0 ] && ok "(d) no backup left behind on refused write" || bad "(d) no backup left behind on refused write (found $BACKUPS_D)"

# ---------------------------------------------------------------------------
# (e) idempotent on second run
# ---------------------------------------------------------------------------
echo "-- (e) idempotent on second run --"
F_E="$WORK/e-AGENTS.md"
cat > "$F_E" <<'EOF'
# AGENTS.md

## Persona Reflex (stamped by apply-fleet-standards.sh)

Body one.

## Persona Reflex (stamped by apply-fleet-standards.sh)

Body one.

EOF
run_dedup "$F_E" --apply >/dev/null
cp "$F_E" "$WORK/e-after-first.md"
OUT_E2="$(run_dedup "$F_E" --apply)"
if cmp -s "$F_E" "$WORK/e-after-first.md"; then
  ok "(e) second run produces byte-identical file"
else
  bad "(e) second run produces byte-identical file"
fi
printf '%s\n' "$OUT_E2" | grep -q 'blocks_removed=0' && printf '%s\n' "$OUT_E2" | grep -qi 'idempotent' \
  && ok "(e) second run reports 0 removed / idempotent no-op" \
  || bad "(e) second run reports 0 removed / idempotent no-op"
BACKUPS_E=$(find "$WORK" -maxdepth 1 -name 'e-AGENTS.md.bak-dedup-*' | wc -l | tr -d ' ')
[ "$BACKUPS_E" -eq 1 ] && ok "(e) no NEW backup created on the idempotent second run" || bad "(e) no NEW backup created on the idempotent second run (found $BACKUPS_E)"

# ---------------------------------------------------------------------------
# (f) a file with no duplicates is left byte-identical
# ---------------------------------------------------------------------------
echo "-- (f) file with no duplicates left byte-identical --"
F_F="$WORK/f-AGENTS.md"
cat > "$F_F" <<'EOF'
# AGENTS.md

## Section One

Unique body one.

## Section Two

Unique body two.

### Sub-section

Unique nested body.
EOF
cp "$F_F" "$WORK/f-before.md"
run_dedup "$F_F" --apply >/dev/null
if cmp -s "$F_F" "$WORK/f-before.md"; then
  ok "(f) file with no duplicates unchanged byte-for-byte"
else
  bad "(f) file with no duplicates unchanged byte-for-byte"
fi
BACKUPS_F=$(find "$WORK" -maxdepth 1 -name 'f-AGENTS.md.bak-dedup-*' | wc -l | tr -d ' ')
[ "$BACKUPS_F" -eq 0 ] && ok "(f) no backup created (nothing to write)" || bad "(f) no backup created (nothing to write) (found $BACKUPS_F)"

# ---------------------------------------------------------------------------
# (g) no file present -> clean skip
# ---------------------------------------------------------------------------
echo "-- (g) no file present -> clean skip --"
MISSING="$WORK/does-not-exist/AGENTS.md"
OUT_G="$(run_dedup "$MISSING" --apply)"; RC_G=$?
[ "$RC_G" -eq 0 ] && ok "(g) exit code 0 on missing file" || bad "(g) exit code 0 on missing file (rc=$RC_G)"
printf '%s\n' "$OUT_G" | grep -q 'SKIP' && ok "(g) informational SKIP message printed" || bad "(g) informational SKIP message printed"
[ ! -e "$(dirname "$MISSING")" ] && ok "(g) no directories/files created as a side effect" || bad "(g) no directories/files created as a side effect"

# ---------------------------------------------------------------------------
# (extra) default (no flags) is dry-run, explicitly announced, never writes
# ---------------------------------------------------------------------------
echo "-- (extra) default is an explicit dry-run --"
F_X="$WORK/x-AGENTS.md"
cat > "$F_X" <<'EOF'
# AGENTS.md

## Persona Reflex (stamped by apply-fleet-standards.sh)

Body one.

## Persona Reflex (stamped by apply-fleet-standards.sh)

Body one.
EOF
cp "$F_X" "$WORK/x-before.md"
OUT_X="$(run_dedup "$F_X")"  # no --apply, no --dry-run
if cmp -s "$F_X" "$WORK/x-before.md"; then
  ok "(extra) default (no flags) never writes"
else
  bad "(extra) default (no flags) never writes"
fi
printf '%s\n' "$OUT_X" | grep -q 'DRY-RUN' && printf '%s\n' "$OUT_X" | grep -qi 'default' \
  && ok "(extra) default dry-run is explicitly announced" \
  || bad "(extra) default dry-run is explicitly announced"

# ---------------------------------------------------------------------------
# Static wiring check: apply-fleet-standards.sh calls the deduper BEFORE the
# first marker-guarded stamp (ROLE_DISCIPLINE_V1), so the surviving marked
# copy is what that stamp's own grep-guard then finds.
# ---------------------------------------------------------------------------
echo "-- static wiring check --"
if [ -f "$FLEET_STD" ]; then
  DEDUP_LINE=$(grep -n 'dedup-agents-md.py' "$FLEET_STD" | head -1 | cut -d: -f1)
  ROLE_DISC_LINE=$(grep -n 'ROLE_DISC_MARKER=' "$FLEET_STD" | head -1 | cut -d: -f1)
  if [ -n "$DEDUP_LINE" ] && [ -n "$ROLE_DISC_LINE" ] && [ "$DEDUP_LINE" -lt "$ROLE_DISC_LINE" ]; then
    ok "apply-fleet-standards.sh invokes dedup-agents-md.py before ROLE_DISCIPLINE_V1 stamp"
  else
    bad "apply-fleet-standards.sh invokes dedup-agents-md.py before ROLE_DISCIPLINE_V1 stamp"
  fi
  if grep -qE '_DEDUP_SCRIPT" --apply --file "\$AGENTS_FILE_EARLY"' "$FLEET_STD"; then
    ok "dedup is called against AGENTS_FILE_EARLY (the same file the stamps below it target)"
  else
    bad "dedup is called against AGENTS_FILE_EARLY (the same file the stamps below it target)"
  fi
  if grep -B2 'AGENTS.md dedup exited' "$FLEET_STD" | grep -q 'WARNING'; then
    ok "a dedup failure is logged as an advisory WARNING, not a hard failure"
  else
    bad "a dedup failure is logged as an advisory WARNING, not a hard failure"
  fi
else
  bad "scripts/apply-fleet-standards.sh exists for the wiring check"
fi

printf 'RESULT: PASS=%d FAIL=%d\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ]

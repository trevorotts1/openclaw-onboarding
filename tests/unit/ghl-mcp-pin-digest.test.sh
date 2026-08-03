#!/usr/bin/env bash
# tests/unit/ghl-mcp-pin-digest.test.sh
#
# MUTATION PROOFS for the self-invalidating GHL MCP vetting digest.
#
# The claim this file exists to prove is narrow and testable: FORGETTING TO
# RE-VET FAILS CLOSED. Every mutation below is something a hurried human or an
# agent would plausibly do -- edit a word, paste a new SHA, delete a line -- and
# every one of them must produce a REFUSAL, not a silent pass.
#
# A gate whose failure path is untested is a gate nobody has ever seen fail, and
# that is indistinguishable from a gate that cannot fail. So the negative cases
# outnumber the positive one on purpose.
#
#   M0  the shipped, properly sealed record                     -> PASS  (rc 0)
#   M1  verdict word hand-edited (PENDING -> CLEAN)             -> REFUSE (rc 1)
#   M2  pin SHA swapped without re-vetting                      -> REFUSE (rc 1)
#   M3  dependency lockfile hash edited without re-vetting      -> REFUSE (rc 1)
#   M4  source repository (mirror) URL swapped                  -> REFUSE (rc 1)
#   M5  digest line deleted entirely                            -> REFUSE (rc 1)
#   M6  digest line emptied                                     -> REFUSE (rc 1)
#   M7  review date advanced without re-vetting                 -> REFUSE (rc 1)
#   M8  reviewer attribution changed without re-vetting         -> REFUSE (rc 1)
#   M9  verdict DIRTY, correctly sealed                         -> REFUSE (rc 1)
#   M10 verdict DIRTY, correctly sealed, --integrity-only       -> PASS  (rc 0)
#   M11 short SHA in the commit field                           -> REFUSE (rc 1)
#   M12 digest present but not a sha256                         -> REFUSE (rc 1)
#   M13 pin file absent                                         -> rc 2 (distinct
#       from a gate failure, so a caller can tell "not delivered" from "lying")
#   M14 a hand-recomputed digest over a DIFFERENT canonical form -> REFUSE
#   M15 the vetting tool refuses a branch name as a candidate
#   M16 the vetting tool refuses an unknown verdict word
#   M17 the vetting tool refuses to write without a verdict at all
#   M18 the digest binds the repo URL: the policy gate and the canonical
#       primitive agree that a swapped mirror is a mismatch (no second
#       implementation of the algorithm can drift away from the first)
#   M19 REGRESSION: the vetting tool must NOT refill a built-in fallback that
#       was deliberately EMPTIED for fail-closed. An empty `${VAR:-}` default is
#       a decision, not a blank to fill; refilling it silently reinstates the
#       bypass the gate exists to close. This was a real defect, caught in the
#       merge chain, and it is fixed here -- so it gets a test.
#
# Exit 0 = every proof held. Exit 1 = at least one did not (CI FAIL).

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKER="$REPO_ROOT/scripts/ghl-mcp-check-pin-digest.sh"
VET="$REPO_ROOT/scripts/ghl-mcp-vet-pin.sh"
PIN_SRC="$REPO_ROOT/config/ghl-mcp-pin.env"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== ghl-mcp-pin-digest.test.sh — mutation proofs ==="
echo ""

for f in "$CHECKER" "$VET" "$PIN_SRC"; do
  if [ ! -f "$f" ]; then
    echo "  FAIL: required file not found: $f"
    exit 1
  fi
done

WORK="$(mktemp -d "${TMPDIR:-/tmp}/ghl-pin-digest-test.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# Every mutation starts from a pristine copy of the shipped record.
fresh() { cp "$PIN_SRC" "$WORK/pin.env"; printf '%s' "$WORK/pin.env"; }

# Rewrite one KEY="value" assignment, exactly the way a human hand-edit would.
edit_field() {
  local file="$1" key="$2" val="$3"
  sed "s|^${key}=\".*\"|${key}=\"${val}\"|" "$file" > "$file.tmp" && mv "$file.tmp" "$file"
}

run_check() {
  local file="$1"; shift
  bash "$CHECKER" --pin-file "$file" --quiet "$@" >/dev/null 2>&1
  echo $?
}

expect_rc() {
  local label="$1" want="$2" got="$3"
  if [ "$got" = "$want" ]; then pass "$label (rc=$got)"; else fail "$label — expected rc=$want, got rc=$got"; fi
}

# ── M0 — the shipped record must PASS, or every negative below is meaningless ─
P="$(fresh)"
expect_rc "M0  shipped sealed record is accepted" 0 "$(run_check "$P")"

# ── M1 — the one-word edit the whole design exists to defeat ─────────────────
# This is the exact defeat of a naive "CI asserts VERDICT == CLEAN" check.
P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_VERDICT "PENDING"
rc_pending="$(run_check "$P")"
edit_field "$P" GHL_MCP_PIN_VETTED_VERDICT "CLEAN"
rc_reclean="$(run_check "$P")"
if [ "$rc_pending" = "1" ]; then
  pass "M1a hand-set verdict PENDING is refused (rc=1)"
else
  fail "M1a hand-set verdict PENDING — expected rc=1, got rc=$rc_pending"
fi
# Flipping the word back to CLEAN restores the ORIGINAL value, so the digest
# recomputes again. That is correct and worth stating plainly: the digest binds
# the verdict to the commit, it does not make the file immutable. What it
# forbids is a verdict that no longer matches what was reviewed -- which is
# every case below.
expect_rc "M1b flipping the word back restores the original tuple" 0 "$rc_reclean"

# ── M2 — a pin bump with no re-vetting: the headline failure mode ────────────
P="$(fresh)"
edit_field "$P" GHL_MCP_VETTED_COMMIT "1234567890abcdef1234567890abcdef12345678"
expect_rc "M2  pin SHA changed without re-vetting is refused" 1 "$(run_check "$P")"

# ── M3 — dependency tree swapped under a still-CLEAN verdict ─────────────────
P="$(fresh)"
edit_field "$P" GHL_MCP_DEPS_LOCK_SHA256 "$(printf 'a%.0s' $(seq 1 64))"
expect_rc "M3  lockfile hash changed without re-vetting is refused" 1 "$(run_check "$P")"

# ── M4 — mirror swap: same SHA, same verdict, completely different bytes ─────
P="$(fresh)"
edit_field "$P" GHL_MCP_REPO_URL "https://github.com/someone-else/not-the-mirror.git"
expect_rc "M4  source repository URL swapped is refused" 1 "$(run_check "$P")"

# ── M5/M6 — "just delete the line that complains" must not work ──────────────
P="$(fresh)"
grep -v '^GHL_MCP_PIN_VETTED_DIGEST=' "$P" > "$P.tmp" && mv "$P.tmp" "$P"
expect_rc "M5  deleting the digest line is refused (never a skip)" 1 "$(run_check "$P")"

P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_DIGEST ""
expect_rc "M6  emptying the digest is refused" 1 "$(run_check "$P")"

# ── M7/M8 — provenance fields are bound too ─────────────────────────────────
P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_ON "2030-01-01"
expect_rc "M7  review date advanced without re-vetting is refused" 1 "$(run_check "$P")"

P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_BY "somebody who did not do the review"
expect_rc "M8  reviewer changed without re-vetting is refused" 1 "$(run_check "$P")"

# ── M9/M10 — a correctly sealed DIRTY verdict ───────────────────────────────
# Sealed properly (digest recomputes) but the judgment was negative. The record
# is INTACT and the verdict is REFUSED: the two states must stay distinguishable,
# because "the review said no" and "someone broke the file" need different fixes.
P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_VERDICT "DIRTY"
NEWDIG="$(bash "$CHECKER" --pin-file "$P" --compute)"
edit_field "$P" GHL_MCP_PIN_VETTED_DIGEST "$NEWDIG"
expect_rc "M9  correctly sealed DIRTY verdict is refused"                   1 "$(run_check "$P")"
expect_rc "M10 correctly sealed DIRTY verdict passes --integrity-only"      0 "$(run_check "$P" --integrity-only)"

# ── M11/M12 — malformed records report as malformed, not as mismatches ──────
P="$(fresh)"
edit_field "$P" GHL_MCP_VETTED_COMMIT "bfc2bbe"
expect_rc "M11 a short SHA is refused (a short SHA is not a pin)" 1 "$(run_check "$P")"

P="$(fresh)"
edit_field "$P" GHL_MCP_PIN_VETTED_DIGEST "not-a-sha256"
expect_rc "M12 a non-sha256 digest is refused" 1 "$(run_check "$P")"

# ── M13 — an absent pin file is its own exit code ───────────────────────────
expect_rc "M13 absent pin file reports rc=2, distinct from a gate failure" 2 \
  "$(run_check "$WORK/definitely-not-here.env")"

# ── M14 — a plausible but WRONG hand-recomputation ──────────────────────────
# Somebody who knows a digest is involved, guesses the canonical form, and pipes
# the fields through sha256 the obvious way. The domain separator and the field
# labels mean the guess does not land.
P="$(fresh)"
edit_field "$P" GHL_MCP_VETTED_COMMIT "1234567890abcdef1234567890abcdef12345678"
GUESS="$(printf '1234567890abcdef1234567890abcdef12345678|CLEAN|2026-08-03' | shasum -a 256 2>/dev/null | awk '{print $1}')"
if [ -n "$GUESS" ]; then
  edit_field "$P" GHL_MCP_PIN_VETTED_DIGEST "$GUESS"
  expect_rc "M14 a guessed pipe-joined digest is refused" 1 "$(run_check "$P")"
else
  pass "M14 skipped — no shasum on PATH"
fi

# ── M15..M17 — the writing tool refuses bad input before it touches anything ─
# These run offline: argument validation happens before the tool contacts the
# mirror, so the proofs hold on a CI runner with no network too.
P="$(fresh)"
out="$(bash "$VET" main --pin-file "$P" --verdict clean 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'not a hex commit SHA'; then
  pass "M15 the vetting tool refuses a branch name as a candidate (rc=$rc)"
else
  fail "M15 the vetting tool accepted a branch name (rc=$rc)"
fi
if ! cmp -s "$P" "$PIN_SRC"; then fail "M15 the refused run modified the pin file"; else pass "M15 the refused run wrote nothing"; fi

P="$(fresh)"
out="$(bash "$VET" bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3 --pin-file "$P" --verdict maybe 2>&1)"; rc=$?
if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q "There is no default"; then
  pass "M16 the vetting tool refuses an unknown verdict word (rc=$rc)"
else
  fail "M16 the vetting tool accepted an unknown verdict word (rc=$rc)"
fi
if ! cmp -s "$P" "$PIN_SRC"; then fail "M16 the refused run modified the pin file"; else pass "M16 the refused run wrote nothing"; fi

# M17 needs the mirror to produce a review, so it is only asserted when the
# network is available. Without it the tool cannot get far enough to prove the
# no-verdict path, and a test that silently degrades to "true" is worse than one
# that says it was skipped.
if [ "${GHL_MCP_PIN_TEST_NETWORK:-0}" = "1" ]; then
  P="$(fresh)"
  bash "$VET" bfc2bbe15a4090b82351593b6ca52eed7a8dbbe3 --pin-file "$P" >/dev/null 2>&1; rc=$?
  if [ "$rc" = "3" ]; then pass "M17 review-only run exits 3 and writes nothing"; else fail "M17 review-only run — expected rc=3, got rc=$rc"; fi
  if ! cmp -s "$P" "$PIN_SRC"; then fail "M17 the review-only run modified the pin file"; else pass "M17 the review-only run wrote nothing"; fi
else
  echo "  SKIP: M17 (set GHL_MCP_PIN_TEST_NETWORK=1 to exercise the mirror-backed review path)"
fi

# ── M18 — one algorithm, two callers, no drift ───────────────────────────────
# The policy gate (this suite's subject) delegates the tuple to
# scripts/ghl-mcp-pin-digest.sh. If either ever grew its own copy of the
# algorithm they could disagree, and the effective policy would become whichever
# one a caller happened to invoke. Assert they agree on the same file, and that
# both see a swapped mirror URL as a mismatch.
PRIMITIVE="$REPO_ROOT/scripts/ghl-mcp-pin-digest.sh"
if [ -f "$PRIMITIVE" ]; then
  P="$(fresh)"
  wrapper_digest="$(bash "$CHECKER" --pin-file "$P" --compute 2>/dev/null)"
  primitive_digest="$(bash "$PRIMITIVE" compute "$P" 2>/dev/null)"
  if [ -n "$wrapper_digest" ] && [ "$wrapper_digest" = "$primitive_digest" ]; then
    pass "M18a the policy gate and the canonical primitive compute the same digest"
  else
    fail "M18a digest implementations disagree — wrapper=$wrapper_digest primitive=$primitive_digest"
  fi
  edit_field "$P" GHL_MCP_REPO_URL "https://github.com/someone-else/not-the-mirror.git"
  bash "$PRIMITIVE" verify "$P" >/dev/null 2>&1
  prc=$?
  if [ "$prc" = "1" ]; then
    pass "M18b the canonical primitive itself refuses a swapped mirror URL (rc=1)"
  else
    fail "M18b the primitive did not bind the repo URL — expected rc=1, got rc=$prc"
  fi
else
  fail "M18 scripts/ghl-mcp-pin-digest.sh is missing — the canonical algorithm has no home"
fi

# ── M19 — the tool must not undo a fail-closed decision ──────────────────────
# v21.6.0 deleted the silent hardcoded commit fallback so a box that cannot read
# the pin file REFUSES rather than building a baked-in constant. A vetting tool
# whose fallback-sync regex matched the empty string would refill it on the next
# pin bump and quietly reinstate that bypass -- forever, and invisibly, because
# the pin gate would then see a "matching" fallback and report PASS.
for _f in scripts/ghl-mcp-autostart.sh platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh; do
  _full="$REPO_ROOT/$_f"
  [ -f "$_full" ] || continue
  if grep -Eq '^[[:space:]]*GHL_MCP_VETTED_COMMIT="\$\{GHL_MCP_VETTED_COMMIT:-[0-9a-f]{40}\}"' "$_full"; then
    fail "M19 $_f carries a POPULATED commit fallback — the fail-closed empty default was refilled"
  else
    pass "M19 $_f keeps its fail-closed empty commit fallback"
  fi
done

echo ""
echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0

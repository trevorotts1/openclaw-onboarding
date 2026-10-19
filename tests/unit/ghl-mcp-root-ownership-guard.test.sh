#!/usr/bin/env bash
# tests/unit/ghl-mcp-root-ownership-guard.test.sh
#
# DEFECT 1 (worst of three, proven live on a real VPS box, 2026-08-04):
# scripts/ghl-mcp-autostart.sh's mirror-migration self-heal (the block that
# repoints a box's MCP `origin` from the retired upstream to the org mirror)
# silently NO-OP'd when the script ran as ROOT against a checkout owned by
# uid 1000 (the fleet-standard box user). Every git command in
# ensure_repo_at_pin() hit git's "detected dubious ownership" fatal, and a
# blanket `2>/dev/null` swallowed it -- no WARN, no FATAL, no trace. The
# operator then saw an innocent-looking "PIN_MISMATCH -- cannot check out
# vetted commit" and reasonably blamed the pin gate. This is the SAME disease
# as the root-cron bug fixed earlier the same night.
#
# THE FIX under test (the GHL-MCP-ROOT-OWNERSHIP-GUARD block):
# assert_ownership_matches_runtime_user() detects the exact failing
# condition -- EUID 0 running against an EXISTING checkout owned by a
# DIFFERENT uid -- BEFORE any git command runs, and fails LOUD through the
# same report()/STATUS contract every other refusal in this script uses,
# naming the exact remedy (docker exec -u node <ctr>, matching the
# convention documented at scripts/activate-loop-protection.sh:118).
#
# WHY THIS TEST CANNOT SIMPLY "run as root": tests must not require sudo/root
# and must not depend on chown succeeding (unprivileged CI runners cannot
# chown to an arbitrary uid). Instead it proves the DECISION FUNCTION against
# every input combination directly, using the script's own id/stat-reading
# code with a controllable environment:
#   - id -u is read for real (this test process's real uid)
#   - GHL_MCP_ALLOW_ROOT is the documented escape hatch
#   - the "am I root" and "does the owner differ" checks are proven
#     independently via a directory this process genuinely owns (uid match,
#     the always-true real-world case for a non-root test runner) and via
#     asserting the FATAL branch's literal remedy text is present and
#     unconditional when the guard's OWN preconditions are stubbed true.
#
# Extraction, not re-implementation: the GHL-MCP-ROOT-OWNERSHIP-GUARD block is
# sourced verbatim from the shipped script (same convention as
# tests/unit/ghl-mcp-env-credential-guard.test.sh / ghl-mcp-unset-verb.test.sh).
# A hand-written copy of this logic could pass while the shipped file regressed.

set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
SRC="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"

FAILURES=0
pass() { printf '  PASS  %s\n' "$*"; }
fail() { printf '  FAIL  %s\n' "$*" >&2; FAILURES=$((FAILURES+1)); }

echo "=== ghl-mcp-root-ownership-guard.test.sh ==="
echo ""

[ -f "$SRC" ] || { echo "FATAL: $SRC not found"; exit 1; }

BLOCK="$(mktemp "${TMPDIR:-/tmp}/ghl-root-guard-block.XXXXXX")"
awk '/^# >>> GHL-MCP-ROOT-OWNERSHIP-GUARD-BEGIN/{f=1;next} /^# <<< GHL-MCP-ROOT-OWNERSHIP-GUARD-END/{f=0} f' \
  "$SRC" > "$BLOCK"
if [ ! -s "$BLOCK" ]; then
  echo "FATAL: the GHL-MCP-ROOT-OWNERSHIP-GUARD markers are missing from $SRC — the guard cannot be proven, failing closed."
  rm -f "$BLOCK"; exit 1
fi

for _needle in '_ghl_owner_uid' 'assert_ownership_matches_runtime_user' 'ROOT_OWNERSHIP_MISMATCH' 'docker exec -u node'; do
  grep -qF "$_needle" "$BLOCK" \
    || { echo "FATAL: extracted block no longer contains $_needle"; rm -f "$BLOCK"; exit 1; }
done
pass "(setup) extracted GHL-MCP-ROOT-OWNERSHIP-GUARD block, contains all load-bearing pieces"

# Also prove the CALLER actually short-circuits on the guard's signal (rc=3),
# never falling through to the generic PIN_MISMATCH/BUILD_FAILED report — a
# refactor that changed the return code without updating the caller would
# make this whole fix invisible again behind the exact symptom it exists to
# stop being confused with.
#
# PRESENCE CHECK: ensure_repo_at_pin() was deleted along with the start/pin
# path when the community MCP was retired (GU-019), so the wiring it carried is
# gone with it — and with no caller left, there is nothing that can fall through
# to a generic PIN_MISMATCH report. The original wiring assertions stay here,
# reachable behind the presence check: restoring ensure_repo_at_pin() re-arms
# them instead of bypassing them. What locks the tree now is the retirement
# contract that replaced the caller.
if grep -qF 'ensure_repo_at_pin() {' "$SRC"; then
  if grep -qF 'assert_ownership_matches_runtime_user || return 3' "$SRC" \
     && grep -q '_PIN_RC" = "3"' "$SRC"; then
    pass "(setup) ensure_repo_at_pin() returns 3 on the guard's refusal, and the caller special-cases rc=3 before the generic PIN_MISMATCH/BUILD_FAILED branches"
  else
    fail "(setup) the ensure_repo_at_pin()/caller wiring for rc=3 is missing or was refactored — ROOT_OWNERSHIP_MISMATCH could silently fall through to a generic report again"
  fi
else
  _code_of() { awk '{ sub(/#.*/, ""); print }' "$1"; }   # live code only
  C_AUTO="$(mktemp "${TMPDIR:-/tmp}/ghl-root-code.XXXXXX")"
  _code_of "$SRC" > "$C_AUTO"

  # G1: the caller is gone as live code, not merely unwired.
  if grep -qE 'ensure_repo_at_pin[[:space:]]*\(\)[[:space:]]*\{' "$C_AUTO"; then
    fail "G1: ensure_repo_at_pin() is defined as live code in scripts/ghl-mcp-autostart.sh — the pin-gate caller is back, so the rc=3 wiring assertion above must be re-armed"
  else
    pass "G1: ensure_repo_at_pin() (the pin-gate caller this defect lived in) is not defined as live code — retirement removed the checkout path wholesale"
  fi

  # G2: the operations whose "dubious ownership" fatal the defect swallowed no
  #     longer run at all.
  if grep -qE 'git[[:space:]]+(clone|checkout)' "$C_AUTO"; then
    fail "G2: a live git clone/checkout still ships in scripts/ghl-mcp-autostart.sh — a root-owned checkout can silently no-op again"
  else
    pass "G2: no live git clone/checkout in scripts/ghl-mcp-autostart.sh (comment-stripped) — the checkout whose silent failure hid this defect cannot run"
  fi

  # G3: the refusal is why nothing reaches a pin gate.
  if grep -qF 'report "START_REFUSED_RETIRED"' "$C_AUTO"; then
    pass "G3: the script refuses to start (live START_REFUSED_RETIRED) — no live path reaches the pin/build gate the old caller guarded"
  else
    fail "G3: scripts/ghl-mcp-autostart.sh no longer reports START_REFUSED_RETIRED on a live line — the retirement refusal is gone"
  fi

  # G4 (control): the comment-stripper must still yield real live function
  #     definitions, otherwise the two absence claims above (G1, G2) could pass
  #     on an empty strip.
  if grep -qE 'oc_mcp_unset[[:space:]]*\(\)[[:space:]]*\{' "$C_AUTO"; then
    pass "G4: control — comment-stripped autostart still contains live function definitions (oc_mcp_unset), so G1/G2 are absence claims about real code"
  else
    fail "G4: control failed — comment-stripped scripts/ghl-mcp-autostart.sh contains no live function definitions; G1/G2 prove nothing"
  fi

  rm -f "$C_AUTO"
fi

# ── Harness: source the block with log()/report() stubbed, MCP_DIR pointed at
#    a real temp dir this test process genuinely owns. ───────────────────────
_run_guard() {  # _run_guard <MCP_DIR_has_git 0|1> <extra env assignments...>
  local has_git="$1"; shift
  local box; box="$(mktemp -d "${TMPDIR:-/tmp}/ghl-root-box.XXXXXX")"
  [ "$has_git" = "1" ] && mkdir -p "$box/.git"
  (
    # shellcheck disable=SC1090
    SELF_DIR="$box"
    MCP_DIR="$box"
    STATUS="UNKNOWN"
    log() { printf '[log] %s\n' "$*"; }
    report() { STATUS="$1"; shift; printf 'STATUS: ghl-mcp-autostart=%s %s\n' "$STATUS" "$*"; }
    . "$BLOCK"
    "$@"
    _rc=$?
    printf 'RC=%s\n' "$_rc"
  )
  local _out_rc=$?
  rm -rf "$box"
  return $_out_rc
}

# (1) No .git at all (fresh clone target) -> guard must NOT fire, regardless
#     of uid, because there is nothing whose ownership could disagree yet.
OUT="$(_run_guard 0 assert_ownership_matches_runtime_user 2>&1)"
if printf '%s' "$OUT" | grep -q 'RC=0$'; then
  pass "(1) no existing .git checkout -> guard is a no-op (rc=0), never blocks a fresh clone"
else
  fail "(1) no existing .git checkout should be rc=0. Output: $OUT"
fi

# (2) A real checkout this test process OWNS (the only privilege level a CI
#     runner can prove without sudo) -> whether or not the process happens to
#     be uid 0, the ownership matches, so the guard must NEVER fire. This is
#     the anti-vacuity control: a guard that fires on ANY existing .git dir
#     regardless of ownership would break every ordinary (non-root, or
#     root-on-a-root-owned-box) run.
OUT="$(_run_guard 1 assert_ownership_matches_runtime_user 2>&1)"
if printf '%s' "$OUT" | grep -q 'RC=0$'; then
  pass "(2) checkout owned by the SAME uid running this process -> guard is a no-op (rc=0) — never blocks a matching-ownership run"
else
  fail "(2) an owned checkout must never trip the guard. Output: $OUT"
fi

# (3) GHL_MCP_ALLOW_ROOT=1 escape hatch — even when every other precondition
#     could fire, the explicit override must always win.
OUT="$(
  box="$(mktemp -d "${TMPDIR:-/tmp}/ghl-root-box.XXXXXX")"
  mkdir -p "$box/.git"
  (
    SELF_DIR="$box"; MCP_DIR="$box"; STATUS="UNKNOWN"
    log() { :; }; report() { :; }
    GHL_MCP_ALLOW_ROOT=1
    export GHL_MCP_ALLOW_ROOT
    . "$BLOCK"
    assert_ownership_matches_runtime_user
    printf 'RC=%s\n' "$?"
  )
  rm -rf "$box"
)"
if printf '%s' "$OUT" | grep -q 'RC=0$'; then
  pass "(3) GHL_MCP_ALLOW_ROOT=1 always short-circuits to rc=0 (the documented test/emergency escape hatch)"
else
  fail "(3) GHL_MCP_ALLOW_ROOT=1 did not short-circuit. Output: $OUT"
fi

# (4) THE DEFECT SIGNATURE ITSELF, forced deterministically. We cannot
#     actually become uid 0 nor chown to a foreign uid without privileges
#     this test must not require, so the root/mismatch PRECONDITIONS are
#     stubbed to their "true" values (id and _ghl_owner_uid), and the REAL,
#     unmodified assert_ownership_matches_runtime_user() body is exercised
#     end to end. This proves the actual comparison + refusal logic, not a
#     re-description of it.
OUT="$(
  box="$(mktemp -d "${TMPDIR:-/tmp}/ghl-root-box.XXXXXX")"
  mkdir -p "$box/.git"
  (
    SELF_DIR="$box"; MCP_DIR="$box"; STATUS="UNKNOWN"
    LOGLINES=""
    log() { LOGLINES="${LOGLINES}
$*"; }
    report() { STATUS="$1"; shift; printf 'STATUS: ghl-mcp-autostart=%s %s\n' "$STATUS" "$*"; }
    . "$BLOCK"
    # Stub id(1) to report uid 0 (root) for this subshell only.
    id() { printf '0'; }
    # Stub the owner-detection helper to report a DIFFERENT uid (1000/node) —
    # the exact fleet-standard VPS shape (box user uid 1000, root invoking).
    _ghl_owner_uid() { printf '1000'; }
    assert_ownership_matches_runtime_user
    printf 'RC=%s\n' "$?"
    printf '%s\n' "$LOGLINES"
  )
  rm -rf "$box"
)"
if printf '%s' "$OUT" | grep -q 'RC=1$' \
   && printf '%s' "$OUT" | grep -qF 'STATUS: ghl-mcp-autostart=ROOT_OWNERSHIP_MISMATCH' \
   && printf '%s' "$OUT" | grep -qF 'docker exec -u node'; then
  pass "(4) THE DEFECT: uid 0 vs owner uid 1000 -> guard FAILS LOUD (rc=1), reports STATUS=ROOT_OWNERSHIP_MISMATCH, and names the docker exec -u node remedy — never a silent no-op"
else
  fail "(4) the root/ownership-mismatch case did not refuse loudly as expected. Output:"
  printf '%s\n' "$OUT" | sed 's/^/        /'
fi

# (5) Anti-vacuity: uid 0 running against a checkout ALSO owned by uid 0 (a
#     deliberately root-owned box) must NOT fire — root is not inherently the
#     problem; the OWNERSHIP MISMATCH is.
OUT="$(
  box="$(mktemp -d "${TMPDIR:-/tmp}/ghl-root-box.XXXXXX")"
  mkdir -p "$box/.git"
  (
    SELF_DIR="$box"; MCP_DIR="$box"; STATUS="UNKNOWN"
    log() { :; }; report() { :; }
    . "$BLOCK"
    id() { printf '0'; }
    _ghl_owner_uid() { printf '0'; }
    assert_ownership_matches_runtime_user
    printf 'RC=%s\n' "$?"
  )
  rm -rf "$box"
)"
if printf '%s' "$OUT" | grep -q 'RC=0$'; then
  pass "(5) uid 0 against a checkout ALSO owned by uid 0 -> no mismatch, guard is a no-op (root itself is not the defect; the DISAGREEMENT is)"
else
  fail "(5) a root-owned checkout run as root should never trip the guard. Output: $OUT"
fi

# (6) Anti-vacuity: ownership CANNOT be determined (stat unavailable/fails) ->
#     never blocks on a guess.
OUT="$(
  box="$(mktemp -d "${TMPDIR:-/tmp}/ghl-root-box.XXXXXX")"
  mkdir -p "$box/.git"
  (
    SELF_DIR="$box"; MCP_DIR="$box"; STATUS="UNKNOWN"
    log() { :; }; report() { :; }
    . "$BLOCK"
    id() { printf '0'; }
    _ghl_owner_uid() { printf ''; }
    assert_ownership_matches_runtime_user
    printf 'RC=%s\n' "$?"
  )
  rm -rf "$box"
)"
if printf '%s' "$OUT" | grep -q 'RC=0$'; then
  pass "(6) ownership undeterminable -> guard does not block on a guess (rc=0)"
else
  fail "(6) an undeterminable owner should not trip the guard. Output: $OUT"
fi

rm -f "$BLOCK"

echo ""
echo "=== Result: $FAILURES failure(s) ==="
[ "$FAILURES" -eq 0 ] && exit 0 || exit 1

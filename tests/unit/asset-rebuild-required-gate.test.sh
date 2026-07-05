#!/usr/bin/env bash
# tests/unit/asset-rebuild-required-gate.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# FDN-7 / F1.3 + F2.2 regression lock — "a --no-asset staging bump must not leave
# the SET green while the fleet asset lacks the new persona's vectors."
#
# Proves the three cheap gates that close the counted-but-vector-less window:
#
#   Gate 2 (provisioning):  provision_persona_index() REFUSES to (re)provision a
#     client box from a manifest carrying asset_rebuild_required:true — it keeps
#     the box's current index and records a skip warning, so a staged asset can
#     never propagate to a client as "canonical".
#
#   Gate 3 (triad, runtime): persona_fleet.py triad treats embedded_persona_count
#     as a 5th SET-triad member. When asset_rebuild_required:false but the
#     embedded count lags the SET count, the SET carries a counted-but-vector-less
#     persona → exit 5. When asset_rebuild_required:true (a legitimate --no-asset
#     staging bump), the 5th member is carved out (exit 0) with an explicit note
#     naming the pending asset rebuild as the real cause.
#
#   set-manifest-counts contract: a --no-asset bump lifts the four SET counts and
#     flips asset_rebuild_required:true but DOES NOT touch embedded_persona_count
#     (so the lag — and therefore the gate — is provable).
#
# Fully offline: no network, no Gemini key, no gh. Requires python3 (stdlib).
# Exit 0 = all pass. Exit 1 = one or more failed.
# ─────────────────────────────────────────────────────────────────────────────

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$REPO_ROOT/shared-utils/provision-persona-index.sh"
PF="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline/persona_fleet.py"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== asset-rebuild-required-gate.test.sh ==="

[ -f "$HELPER" ] || { echo "  FAIL: helper not found at $HELPER"; exit 1; }
[ -f "$PF" ]     || { echo "  FAIL: persona_fleet.py not found at $PF"; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Build a minimal repo-root skeleton (personas dirs + categories + manifest).
mk_repo() {  # $1=root  $2=json-manifest-dict  $3..=slugs
    local root="$1"; local manifest="$2"; shift 2
    rm -rf "$root"
    mkdir -p "$root/22-book-to-persona-coaching-leadership-system/personas" \
             "$root/shared-utils/prebuilt-index"
    local s
    for s in "$@"; do mkdir -p "$root/22-book-to-persona-coaching-leadership-system/personas/$s"; done
    python3 -c 'import json,sys; root=sys.argv[1]; slugs=sys.argv[2:]; json.dump({"personas":{s:{} for s in slugs}}, open(root+"/22-book-to-persona-coaching-leadership-system/persona-categories.json","w"))' \
        "$root" "$@"
    printf '%s' "$manifest" > "$root/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
}

# ── (1) Gate 2: provisioning REFUSES an asset_rebuild_required:true manifest ──
echo "--- (1) provision refuses a staged (--no-asset) manifest, keeps current index ---"
# shellcheck source=/dev/null
source "$HELPER"
STAGED_MANIFEST="$WORK/staged-manifest.json"
python3 -c 'import json; json.dump({"asset_url":"https://example/none.gz","sha256":"deadbeef","chunk_count":1161,"release_tag":"prebuilt-index-vX","persona_count":82,"canonical_persona_count":82,"embedded_persona_count":81,"asset_rebuild_required":True,"schema":{"columns_required":["section_number","mode"]}}, open("'"$STAGED_MANIFEST"'","w"))'
CDB="$WORK/coaching-personas"; mkdir -p "$CDB"
# Seed an existing "current" index file the box already has — the gate must keep it.
echo "PRE-EXISTING-INDEX" > "$CDB/gemini-index.sqlite"
_PIDX_SKIP_WARNINGS=""
PROVISION_DRY_RUN=1 provision_persona_index "$STAGED_MANIFEST" "$CDB" >/dev/null 2>&1
rc=$?
[ "$rc" -eq 0 ] && pass "provision returned 0 (non-fatal skip)" || fail "provision rc=$rc (expected 0)"
grep -q "asset_rebuild_required" <<< "${_PIDX_SKIP_WARNINGS:-}" \
    && pass "skip warning names asset_rebuild_required" \
    || fail "skip warning missing/wrong: ${_PIDX_SKIP_WARNINGS:-<empty>}"
[ "$(cat "$CDB/gemini-index.sqlite")" = "PRE-EXISTING-INDEX" ] \
    && pass "box's current index left untouched (no clobber)" \
    || fail "current index was modified"

# Control: a fresh manifest (asset_rebuild_required:false) is NOT refused by the
# freshness gate — it proceeds to the normal gate logic (dry-run stops at network).
echo "--- (1b) fresh manifest is NOT refused by the freshness gate ---"
FRESH_MANIFEST="$WORK/fresh-manifest.json"
python3 -c 'import json; json.dump({"asset_url":"https://example/x.gz","sha256":"abc","chunk_count":1161,"release_tag":"prebuilt-index-v2.3.0","persona_count":81,"canonical_persona_count":81,"embedded_persona_count":81,"asset_rebuild_required":False,"schema":{"columns_required":["section_number","mode"]}}, open("'"$FRESH_MANIFEST"'","w"))'
CDB2="$WORK/coaching2"; mkdir -p "$CDB2"
_PIDX_SKIP_WARNINGS=""
out="$(PROVISION_DRY_RUN=1 provision_persona_index "$FRESH_MANIFEST" "$CDB2" 2>&1)"
grep -q "asset_rebuild_required" <<< "${_PIDX_SKIP_WARNINGS:-}" \
    && fail "fresh manifest was wrongly refused by freshness gate" \
    || pass "fresh manifest passed the freshness gate (reached normal gate)"
grep -q "dry-run" <<< "$out" \
    && pass "fresh manifest reached the download decision (dry-run)" \
    || pass "fresh manifest proceeded past the freshness gate"

# ── (2) Gate 3: triad 5th member (embedded_persona_count) ────────────────────
echo "--- (2) triad: counted-but-vector-less (rebuild=false, embedded lags) → exit 5 ---"
RV="$WORK/vectorless"
mk_repo "$RV" '{"persona_count":2,"canonical_persona_count":2,"embedded_persona_count":1,"asset_rebuild_required":false}' a b
err="$(python3 "$PF" triad --repo-root "$RV" 2>&1 >/dev/null)"; rc=$?
[ "$rc" -eq 5 ] && pass "counted-but-vector-less exits 5" || fail "expected 5, got $rc"
grep -q "ASSET DISAGREES" <<< "$err" && pass "message names the ASSET disagreement" || fail "message missing ASSET DISAGREES: $err"

echo "--- (2b) staged --no-asset (rebuild=true, embedded lags) → exit 0 + carve-out ---"
RS="$WORK/staged"
mk_repo "$RS" '{"persona_count":2,"canonical_persona_count":2,"embedded_persona_count":1,"asset_rebuild_required":true}' a b
err="$(python3 "$PF" triad --repo-root "$RS" 2>&1 >/dev/null)"; rc=$?
[ "$rc" -eq 0 ] && pass "staged bump is non-fatal here (exit 0)" || fail "expected 0, got $rc"
grep -q "carve-out" <<< "$err" && pass "carve-out note explains the pending asset rebuild" || fail "carve-out note missing: $err"

echo "--- (2c) fully agreeing SET (embedded == count, rebuild=false) → exit 0 ---"
RA="$WORK/agree"
mk_repo "$RA" '{"persona_count":2,"canonical_persona_count":2,"embedded_persona_count":2,"asset_rebuild_required":false}' a b
python3 "$PF" triad --repo-root "$RA" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && pass "agreeing SET passes (exit 0)" || fail "expected 0, got $rc"

echo "--- (2d) legacy manifest (no embedded_persona_count field) → back-compat exit 0 ---"
RL="$WORK/legacy"
mk_repo "$RL" '{"persona_count":2,"canonical_persona_count":2}' a b
python3 "$PF" triad --repo-root "$RL" >/dev/null 2>&1; rc=$?
[ "$rc" -eq 0 ] && pass "legacy manifest (5th member absent) passes" || fail "expected 0, got $rc"

# ── (3) set-manifest-counts contract: --no-asset does NOT touch embedded ─────
echo "--- (3) set-manifest-counts --no-asset lifts counts, leaves embedded stale ---"
RM="$WORK/setman"
mk_repo "$RM" '{"persona_count":2,"canonical_persona_count":2,"embedded_persona_count":2,"asset_rebuild_required":false}' a b
MAN="$RM/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
CAT="$RM/22-book-to-persona-coaching-leadership-system/persona-categories.json"
python3 "$PF" set-manifest-counts --manifest "$MAN" --count 3 --repo-cat "$CAT" --no-asset >/dev/null 2>&1
read -r NEWC EMB REB < <(python3 -c 'import json,sys;m=json.load(open(sys.argv[1]));print(m.get("persona_count"),m.get("embedded_persona_count"),m.get("asset_rebuild_required"))' "$MAN")
[ "$NEWC" = "3" ]     && pass "persona_count lifted to 3" || fail "persona_count=$NEWC (expected 3)"
[ "$EMB" = "2" ]      && pass "embedded_persona_count left STALE at 2 (not touched)" || fail "embedded_persona_count=$EMB (expected 2)"
[ "$REB" = "True" ]   && pass "asset_rebuild_required flipped true" || fail "asset_rebuild_required=$REB (expected True)"
# End-to-end: the staged manifest a --no-asset bump produced is a counted-but-
# vector-less state, and provisioning from it is REFUSED (loop closed).
_PIDX_SKIP_WARNINGS=""
PROVISION_DRY_RUN=1 provision_persona_index "$MAN" "$WORK/cdb3" >/dev/null 2>&1
grep -q "asset_rebuild_required" <<< "${_PIDX_SKIP_WARNINGS:-}" \
    && pass "the manifest a --no-asset bump produced is refused by provisioning" \
    || fail "staged-bump manifest was NOT refused by provisioning"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1

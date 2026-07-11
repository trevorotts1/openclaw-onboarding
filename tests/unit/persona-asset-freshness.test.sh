#!/usr/bin/env bash
# tests/unit/persona-asset-freshness.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# FIX F1.3 / F2.2 regression lock — the persona-SET 5th triad member
# (embedded_persona_count) + the asset_rebuild_required freshness contract.
#
# Proves, hermetically (no network, no Gemini key, no gh):
#   (A) persona_fleet.py triad and qc-assert-repo-consistency.py both FAIL when
#       the served asset is STALE — embedded_persona_count < the agreed SET count
#       while asset_rebuild_required==false (a persona was counted but its vectors
#       were never embedded/published — the exact F1.3 defect).
#   (B) BOTH checkers PASS (carve-out) on a --no-asset STAGING bump
#       (asset_rebuild_required==true) — staging stays possible off protected refs.
#   (C) BOTH checkers PASS when the asset is genuinely fresh (embedded == SET).
#   (D) a legacy manifest with NO embedded_persona_count is tolerated additively.
#   (E) provision_persona_index REFUSES to (re)provision a client box from a stale
#       (asset_rebuild_required==true) manifest, keeps the box's current index,
#       returns 0, and surfaces the reason in _PIDX_SKIP_WARNINGS — even with a
#       matching sha256/asset present (the refusal fires BEFORE any download).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PF="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline/persona_fleet.py"
QC="$REPO_ROOT/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py"
PROVISION="$REPO_ROOT/shared-utils/provision-persona-index.sh"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

for f in "$PF" "$QC" "$PROVISION"; do
    [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

SB="$(mktemp -d -t paf-test.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

# ── fixture builder: a repo with N personas + a manifest whose embedded count +
#    asset_rebuild_required flag are caller-controlled ─────────────────────────
mk_repo() {  # $1=root  $2=N (personas)  $3=embedded  $4=rebuild(true|false)
    local root="$1" n="$2" embedded="$3" rebuild="$4"
    local sk="$root/22-book-to-persona-coaching-leadership-system"
    mkdir -p "$sk/personas" "$root/shared-utils/prebuilt-index" \
             "$root/23-ai-workforce-blueprint"
    ROOT="$root" N="$n" EMB="$embedded" RB="$rebuild" python3 - <<'PY'
import json, os
root = os.environ["ROOT"]; n = int(os.environ["N"])
emb = os.environ["EMB"]; rb = os.environ["RB"] == "true"
sk = root + "/22-book-to-persona-coaching-leadership-system"
cat = {"schemaVersion": "1.1", "created": "2026-01-01",
       "domainTags": ["leadership"], "perspectiveTags": [],
       "personas": {}, "lastUpdated": "2026-01-01"}
for i in range(n):
    s = f"p-{i}"
    cat["personas"][s] = {"author": "A", "book": "B",
                          "domain": ["leadership"], "perspective": [], "custom": []}
    d = f"{sk}/personas/{s}"
    os.makedirs(d, exist_ok=True)
    open(d + "/persona-blueprint.md", "w").write(f"# {s}\n\nbody\n")
json.dump(cat, open(sk + "/persona-categories.json", "w"), indent=2)
man = {"persona_count": n, "canonical_persona_count": n,
       "chunk_count": 10, "sha256": "deadbeef",
       "release_tag": "prebuilt-index-v0.0.1",
       "asset_url": "https://example.invalid/none.gz",
       "persona_set_md5": "x", "asset_rebuild_required": rb}
if emb != "absent":
    man["embedded_persona_count"] = int(emb)
json.dump(man, open(root + "/shared-utils/prebuilt-index/INDEX-MANIFEST.json", "w"), indent=2)
PY
}

triad_rc() { python3 "$PF" triad --repo-root "$1" >/dev/null 2>&1; echo $?; }

# qc-assert 5th-member failures for a fixture (prints the count of persona-set
# failure tuples the function returns for <root>/23-ai-workforce-blueprint).
qc_persona_fail_count() {
    python3 - "$QC" "$1/23-ai-workforce-blueprint" <<'PY'
import importlib.util, sys
spec = importlib.util.spec_from_file_location("qc", sys.argv[1])
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
print(len(m._persona_set_triad_failures(sys.argv[2])))
PY
}

echo "=== (A) STALE asset (embedded 80 != SET 81, rebuild=false) → FAIL both checkers ==="
RA="$SB/a"; mk_repo "$RA" 81 80 false
[ "$(triad_rc "$RA")" = "5" ] && pass "persona_fleet triad exits 5 on stale asset" \
    || fail "persona_fleet triad did not exit 5 on stale asset (got $(triad_rc "$RA"))"
out="$(python3 "$PF" triad --repo-root "$RA" 2>&1)"
echo "$out" | grep -qiE 'embedded_persona_count' && pass "triad message names the 5th member (embedded_persona_count)" \
    || fail "triad message did not name embedded_persona_count"
[ "$(qc_persona_fail_count "$RA")" -ge 1 ] && pass "qc-assert reports a persona-set failure on stale asset" \
    || fail "qc-assert did not report a failure on stale asset"

echo "=== (B) STAGED --no-asset bump (embedded 80 != SET 81, rebuild=true) → PASS (carve-out) ==="
RB="$SB/b"; mk_repo "$RB" 81 80 true
[ "$(triad_rc "$RB")" = "0" ] && pass "persona_fleet triad exits 0 (carve-out) on staged bump" \
    || fail "persona_fleet triad did not carve out the staged bump (got $(triad_rc "$RB"))"
[ "$(qc_persona_fail_count "$RB")" = "0" ] && pass "qc-assert carves out the staged bump (0 failures)" \
    || fail "qc-assert did not carve out the staged bump"

echo "=== (C) FRESH asset (embedded 81 == SET 81, rebuild=false) → PASS both ==="
RC="$SB/c"; mk_repo "$RC" 81 81 false
[ "$(triad_rc "$RC")" = "0" ] && pass "persona_fleet triad exits 0 on fresh asset" \
    || fail "persona_fleet triad did not pass a fresh asset (got $(triad_rc "$RC"))"
[ "$(qc_persona_fail_count "$RC")" = "0" ] && pass "qc-assert passes a fresh asset" \
    || fail "qc-assert failed a fresh asset"

echo "=== (D) LEGACY manifest (no embedded_persona_count, rebuild=false) → tolerated ==="
RD="$SB/d"; mk_repo "$RD" 81 absent false
[ "$(triad_rc "$RD")" = "0" ] && pass "persona_fleet triad tolerates a legacy manifest" \
    || fail "persona_fleet triad rejected a legacy manifest (got $(triad_rc "$RD"))"
[ "$(qc_persona_fail_count "$RD")" = "0" ] && pass "qc-assert tolerates a legacy manifest" \
    || fail "qc-assert rejected a legacy manifest"

echo "=== (E) provision_persona_index REFUSES a stale (asset_rebuild_required=true) manifest ==="
RE="$SB/e"; mk_repo "$RE" 81 80 true
MAN_E="$RE/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
DB_DIR_E="$SB/e-db"; mkdir -p "$DB_DIR_E"
# Pre-existing (good) index the box must KEEP.
echo "existing" > "$DB_DIR_E/gemini-index.sqlite"
# shellcheck source=/dev/null
source "$PROVISION"
_PIDX_SKIP_WARNINGS=""
rc=0; PROVISION_DRY_RUN=1 provision_persona_index "$MAN_E" "$DB_DIR_E" >"$SB/e.out" 2>&1 || rc=$?
[ "$rc" = "0" ] && pass "provision_persona_index returns 0 (additive skip) on a stale manifest" \
    || fail "provision_persona_index returned $rc on a stale manifest"
grep -qiE 'asset_rebuild_required[:=]true' "$SB/e.out" && pass "provision names asset_rebuild_required:true as the skip reason" \
    || fail "provision skip reason did not name asset_rebuild_required"
case "${_PIDX_SKIP_WARNINGS:-}" in
    *asset_rebuild_required:true*|*asset_rebuild_required=true*) pass "reason surfaced in _PIDX_SKIP_WARNINGS accumulator" ;;
    *) fail "_PIDX_SKIP_WARNINGS did not capture the stale-asset reason" ;;
esac
# Refusal must fire BEFORE any download decision — no dry-run download line.
if grep -qi "would download" "$SB/e.out"; then
    fail "provision reached the download stage on a stale manifest (should refuse earlier)"
else
    pass "provision refused BEFORE any download decision (kept the box's current index)"
fi
[ "$(cat "$DB_DIR_E/gemini-index.sqlite")" = "existing" ] && pass "box's current index left untouched" \
    || fail "box's current index was modified"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]

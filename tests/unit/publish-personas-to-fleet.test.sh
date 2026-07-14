#!/usr/bin/env bash
# tests/unit/publish-personas-to-fleet.test.sh
# ─────────────────────────────────────────────────────────────────────────────
# Hermetic tests for the atomic persona "publish to fleet" tooling
# (22-…/pipeline/publish-personas-to-fleet.sh + assert-personas-published.sh +
# persona_fleet.py). No network, no Gemini key, no gh — everything runs in
# --no-asset mode against throwaway fixture repos + workspaces.
#
#   (a) add a mock persona to a fixture workspace, run publish --no-asset, and
#       assert the repo blueprint dirs + categories keys + manifest counts ALL
#       move to N together (triad agrees), and the shipped blueprint was
#       SANITIZED of an operator-local path.
#   (b) create an artificial divergence (index/manifest at N, repo at N-1) and
#       assert the GUARD fails with the actionable remediation message.
#   (c) force a mid-run failure (out-of-vocabulary tag) and assert the repo is
#       left in its EXACT pre-run state (no half-committed blueprint dir).
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PIPE="$REPO_ROOT/22-book-to-persona-coaching-leadership-system/pipeline"
PUBLISH="$PIPE/publish-personas-to-fleet.sh"
GUARD="$PIPE/assert-personas-published.sh"
PF="$PIPE/persona_fleet.py"

PASS=0; FAIL=0
pass() { echo "  PASS: $*"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $*"; FAIL=$((FAIL+1)); }

for f in "$PUBLISH" "$GUARD" "$PF"; do
    [ -f "$f" ] || { echo "FATAL: missing $f"; exit 2; }
done

SB="$(mktemp -d -t pptf-test.XXXXXX)"
trap 'rm -rf "$SB"' EXIT

# ── fixture builders ─────────────────────────────────────────────────────────
mk_repo() {  # $1=root  $2..=slugs (built with in-vocab tags, manifest count = n)
    local root="$1"; shift
    local sk="$root/22-book-to-persona-coaching-leadership-system"
    mkdir -p "$sk/personas" "$root/shared-utils/prebuilt-index"
    ROOT="$root" python3 - "$@" <<'PY'
import json, os, sys
root = os.environ["ROOT"]; slugs = sys.argv[1:]
sk = root + "/22-book-to-persona-coaching-leadership-system"
cat = {"schemaVersion": "1.1", "created": "2026-01-01",
       "domainTags": ["leadership", "sales", "marketing", "mindset"],
       "perspectiveTags": ["mens-challenges", "womens-challenges"],
       "personas": {}, "lastUpdated": "2026-01-01"}
for s in slugs:
    cat["personas"][s] = {"author": "A", "book": "B",
                          "domain": ["leadership"], "perspective": [], "custom": ["x-tag"]}
json.dump(cat, open(sk + "/persona-categories.json", "w"), indent=2)
man = {"persona_count": len(slugs), "canonical_persona_count": len(slugs),
       "chunk_count": 10, "sha256": "deadbeef",
       "release_tag": "prebuilt-index-v0.0.1",
       "asset_url": "https://example.invalid/none.gz", "persona_set_md5": "x"}
json.dump(man, open(root + "/shared-utils/prebuilt-index/INDEX-MANIFEST.json", "w"), indent=2)
PY
    local s
    for s in "$@"; do
        mkdir -p "$sk/personas/$s"
        printf '# %s\n\nRepo blueprint body.\n' "$s" > "$sk/personas/$s/persona-blueprint.md"
    done
}

mk_ws() {  # $1=ws  $2..=slugs (categories + blueprints; p_new gets a leaked path)
    local ws="$1"; shift
    mkdir -p "$ws/personas"
    WS="$ws" python3 - "$@" <<'PY'
import json, os, sys
ws = os.environ["WS"]; slugs = sys.argv[1:]
cat = {"schemaVersion": "1.1", "created": "2026-01-01",
       "domainTags": ["leadership", "sales", "marketing", "mindset"],
       "perspectiveTags": ["mens-challenges", "womens-challenges"],
       "personas": {}, "lastUpdated": "2026-06-30"}
for s in slugs:
    cat["personas"][s] = {"author": "A", "book": "B",
                          "domain": ["leadership"], "perspective": [], "custom": ["x-tag"]}
json.dump(cat, open(ws + "/persona-categories.json", "w"), indent=2)
PY
    local s
    for s in "$@"; do
        mkdir -p "$ws/personas/$s"
        {
          printf '# %s\n\nWorkspace blueprint body.\n\n' "$s"
          printf '**Saved to:** `~/Downloads/openclaw-master-files/coaching-personas/personas/%s/persona-blueprint.md`\n' "$s"
        } > "$ws/personas/$s/persona-blueprint.md"
        # A-U8: this fixture workspace has no Gemini key and no
        # gemini-index.sqlite (this test is offline/hermetic, --no-asset) —
        # an honest deferred receipt is what a REAL keyless box's Phase 5
        # would have written, and is what index-verify (step 1.5) requires
        # in place of an actual index row.
        cat > "$ws/personas/$s/embedding-receipt.json" <<JSON
{"persona_id": "$s", "status": "deferred",
 "reason": "embedding: deferred (no key / key invalid)",
 "indexer_exit_code": 4, "timestamp": "2026-06-30T00:00:00"}
JSON
    done
}

tree_md5() {  # deterministic fingerprint of the repo persona artifacts
    local root="$1"
    ( cd "$root" && \
      find 22-book-to-persona-coaching-leadership-system/personas -type f | sort | xargs cat 2>/dev/null; \
      cat 22-book-to-persona-coaching-leadership-system/persona-categories.json; \
      cat shared-utils/prebuilt-index/INDEX-MANIFEST.json ) | \
      { md5sum 2>/dev/null || md5 -q 2>/dev/null; } | awk '{print $1}'
}

triad_n() {  # print the 4 triad counts as "d k p c"
    python3 "$PF" triad --repo-root "$1" --json | python3 -c \
      'import json,sys;c=json.load(sys.stdin)["counts"];print(c["blueprint_dirs"],c["categories.json_keys"],c["manifest.persona_count"],c["manifest.canonical_persona_count"])'
}

echo "=== (a) publish --no-asset moves repo dirs + categories + manifest to N together ==="
RA="$SB/a-repo"; WA="$SB/a-ws"
mk_repo "$RA" p-one p-two
mk_ws   "$WA" p-one p-two p-three-new
before="$(triad_n "$RA")"; [ "$before" = "2 2 2 2" ] && pass "fixture repo starts at 2 2 2 2" || fail "fixture repo baseline wrong: $before"
rc=0; "$PUBLISH" --repo "$RA" --workspace "$WA" --no-asset --yes >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && pass "publish --no-asset exit 0" || fail "publish --no-asset exit $rc"
after="$(triad_n "$RA")"
[ "$after" = "3 3 3 3" ] && pass "all four moved to N=3 together ($after)" || fail "triad did not move together: $after"
rc=0; "$GUARD" --repo "$RA" --repo-only >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && pass "guard --repo-only agrees after publish" || fail "guard --repo-only exit $rc after publish"
if grep -q "openclaw-master-files" "$RA/22-book-to-persona-coaching-leadership-system/personas/p-three-new/persona-blueprint.md"; then
    fail "shipped blueprint still contains the operator-local path (not sanitized)"
else
    pass "shipped blueprint was sanitized (no operator-local path)"
fi

echo "=== (b) guard FAILS loud on an artificial divergence (manifest N, repo N-1) ==="
RB="$SB/b-repo"
mk_repo "$RB" p-one p-two
# bump ONLY the manifest to 3 (index advanced, repo library lagged)
python3 - "$RB" <<'PY'
import json,sys
mp=sys.argv[1]+"/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
m=json.load(open(mp)); m["persona_count"]=3; m["canonical_persona_count"]=3
json.dump(m,open(mp,"w"),indent=2)
PY
out="$("$GUARD" --repo "$RB" --repo-only 2>&1)"; rc=$?
[ "$rc" -eq 5 ] && pass "guard exits 5 (triad disagrees)" || fail "guard exit was $rc (expected 5)"
echo "$out" | grep -q "publish-personas-to-fleet.sh" && pass "guard message names the remediation command" || fail "guard message missing remediation command"
echo "$out" | grep -qi "TRIAD DISAGREES" && pass "guard message states TRIAD DISAGREES" || fail "guard message missing 'TRIAD DISAGREES'"

echo "=== (c) mid-run failure (out-of-vocab tag) leaves NO half-committed state ==="
RC="$SB/c-repo"; WC="$SB/c-ws"
mk_repo "$RC" p-one p-two
mk_ws   "$WC" p-one p-two p-bad
# poison p-bad's workspace categories entry with an out-of-vocabulary domain tag
python3 - "$WC" <<'PY'
import json,sys
cp=sys.argv[1]+"/persona-categories.json"
c=json.load(open(cp)); c["personas"]["p-bad"]["domain"]=["not-a-real-domain"]
json.dump(c,open(cp,"w"),indent=2)
PY
snap_before="$(tree_md5 "$RC")"
rc=0; "$PUBLISH" --repo "$RC" --workspace "$WC" --no-asset --yes >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 4 ] && pass "publish exits 4 (controlled-vocabulary violation)" || fail "publish exit was $rc (expected 4)"
snap_after="$(tree_md5 "$RC")"
[ "$snap_before" = "$snap_after" ] && pass "repo restored to EXACT pre-run state (rollback, no half-commit)" || fail "repo left half-committed (fingerprint changed)"
[ ! -d "$RC/22-book-to-persona-coaching-leadership-system/personas/p-bad" ] && pass "no orphan p-bad blueprint dir left behind" || fail "orphan p-bad blueprint dir remains after rollback"
after_c="$(triad_n "$RC")"
[ "$after_c" = "2 2 2 2" ] && pass "repo triad still 2 2 2 2 after rollback" || fail "repo triad drifted after failure: $after_c"

echo "=== (d) A-U8 index-verify: a persona with NEITHER an index entry NOR a deferred receipt blocks publish ==="
RD="$SB/d-repo"; WD="$SB/d-ws"
mk_repo "$RD" p-one p-two
mk_ws   "$WD" p-one p-two p-unexplained
# p-unexplained gets NO index row and NO honest receipt — an unexplained gap.
rm -f "$WD/personas/p-unexplained/embedding-receipt.json"
snap_before_d="$(tree_md5 "$RD")"
rc=0; out_d="$("$PUBLISH" --repo "$RD" --workspace "$WD" --no-asset --yes 2>&1)" || rc=$?
[ "$rc" -eq 7 ] && pass "publish exits 7 (index-verify FAILED)" || fail "publish exit was $rc (expected 7)"
echo "$out_d" | grep -q "p-unexplained" && pass "index-verify names the offending slug" || fail "index-verify output missing offending slug"
snap_after_d="$(tree_md5 "$RD")"
[ "$snap_before_d" = "$snap_after_d" ] && pass "repo restored to EXACT pre-run state (rollback, no half-commit)" || fail "repo left half-committed after index-verify failure"
[ ! -d "$RD/22-book-to-persona-coaching-leadership-system/personas/p-unexplained" ] && pass "no orphan p-unexplained blueprint dir left behind" || fail "orphan p-unexplained blueprint dir remains after rollback"

echo "=== (e) A-U8 index-verify: an indexed persona (real index row, no receipt needed) passes ==="
RE="$SB/e-repo"; WE="$SB/e-ws"
mk_repo "$RE" p-one p-two
mk_ws   "$WE" p-one p-two p-indexed
rm -f "$WE/personas/p-indexed/embedding-receipt.json"
python3 - "$WE" <<'PY'
import sqlite3, sys
db = sys.argv[1] + "/gemini-index.sqlite"
conn = sqlite3.connect(db)
conn.execute("""CREATE TABLE embeddings (id TEXT PRIMARY KEY, file_path TEXT,
    chunk_index INTEGER, content TEXT, vector BLOB, last_updated REAL,
    provider TEXT, model TEXT, dim INTEGER)""")
# file_path must contain the literal "coaching-personas/personas/" substring —
# the SAME filter embedding_engine.py's search()/keyword_fallback_search() use
# (and persona_fleet.py::_indexed_slugs / persona_embedding_drift_probe.py
# mirror), so a fixture path outside a coaching-personas/personas/ tree is
# correctly NOT recognized as an index hit.
conn.execute("INSERT INTO embeddings VALUES (?,?,?,?,?,?,?,?,?)",
    ("row0", "/box/workspace/data/coaching-personas/personas/p-indexed/persona-blueprint.md",
     0, "content", b"\x00" * 12288, 0.0, "gemini", "gemini-embedding-2", 3072))
conn.commit(); conn.close()
PY
rc=0; "$PUBLISH" --repo "$RE" --workspace "$WE" --no-asset --yes >/dev/null 2>&1 || rc=$?
[ "$rc" -eq 0 ] && pass "publish exit 0 (real index row satisfies index-verify with no receipt)" || fail "publish exit $rc (expected 0)"

echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] || exit 1
exit 0

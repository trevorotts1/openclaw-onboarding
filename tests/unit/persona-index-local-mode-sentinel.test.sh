#!/usr/bin/env bash
# tests/unit/persona-index-local-mode-sentinel.test.sh   (CAN013 regression)
#
# Fleet roll 20261019 canary: update-skills.sh exited 1 with
#   "sentinel=prebuilt-index-v2.4.2, manifest release_tag=prebuilt-index-v2.4.4
#    - persona provisioning incomplete"
# on a LOCAL-OLLAMA-MODE box. provision_persona_index deliberately KEEPS such an
# index (rows are provider='ollama', not the Gemini asset), so its
# .prebuilt-index-version sentinel can never reach release_tag, and the U6b D3
# re-assertion + the currency probe read that as a failed provision forever.
#
# Proves, on a scratch HOME (no network, no live box):
#   1. local-mode box: helper sets _PIDX_LOCAL_MODE=1, keeps the index, and the
#      currency probe reports it applicable-not-stale (rc 0).   [fails pre-fix]
#   2. update-skills.sh's D3 re-assertion honours _PIDX_LOCAL_MODE. [fails pre-fix]
#   3. a Gemini box on an OLDER index is brought to release_tag (file:// asset).
#   4. an unreachable asset leaves an ACTIONABLE reason in _PIDX_SKIP_WARNINGS
#      (release tag + URL), not just a sentinel mismatch.         [fails pre-fix]
set -uo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
HELPER="$REPO/shared-utils/provision-persona-index.sh"
US="$REPO/update-skills.sh"
PASS=0; FAIL=0
ok()  { echo "  PASS: $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }
WORK="$(mktemp -d)"; trap 'rm -rf "$WORK"' EXIT
TAG_OLD="prebuilt-index-v2.4.2"; TAG_NEW="prebuilt-index-v2.4.4"

mk_db() {  # mk_db <path> <provider> <nrows>   (2 personas, required columns present)
  python3 -I - "$@" <<'PY'
import sqlite3, sys
p, prov, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
c = sqlite3.connect(p)
c.execute("CREATE TABLE embeddings(id INTEGER, file_path TEXT, provider TEXT, section_number INTEGER, mode TEXT, persona_id TEXT)")
c.executemany("INSERT INTO embeddings VALUES(?,?,?,?,?,?)",
              [(i, "/x/personas/p%d/f.md" % (i % 2), prov, 3, "both", "p%d" % (i % 2)) for i in range(n)])
c.commit(); c.close()
PY
}
mk_box() {  # mk_box <dir> <provider> <nrows> <sentinel>
  mkdir -p "$1/personas/p0" "$1/personas/p1"
  mk_db "$1/gemini-index.sqlite" "$2" "$3"
  printf '%s\n' "$4" > "$1/.prebuilt-index-version"
}
mk_manifest() {  # mk_manifest <path> <asset_url> <sha>
  python3 -I -c 'import json,sys
json.dump({"release_tag":sys.argv[4],"asset_url":sys.argv[2],"sha256":sys.argv[3],"chunk_count":3,"persona_count":2,
 "schema":{"columns_required":["section_number","mode"]}}, open(sys.argv[1],"w"))' "$1" "$2" "$3" "$TAG_NEW"
}

echo "=== persona-index-local-mode-sentinel.test.sh ==="
# shellcheck source=/dev/null
source "$HELPER"

# ── 1. local-mode box ───────────────────────────────────────────────────────
B1="$WORK/local"; mk_box "$B1" ollama 5 "$TAG_OLD"
mk_manifest "$WORK/m1.json" "file://$WORK/does-not-exist.gz" "00"
before="$(shasum "$B1/gemini-index.sqlite" | cut -d' ' -f1)"
_PIDX_SKIP_WARNINGS=""
provision_persona_index "$WORK/m1.json" "$B1" >"$WORK/p1.out" 2>&1
[ "${_PIDX_LOCAL_MODE:-0}" = "1" ] && ok "local-mode box flagged _PIDX_LOCAL_MODE=1" || bad "local-mode flag not set"
[ "$(shasum "$B1/gemini-index.sqlite" | cut -d' ' -f1)" = "$before" ] && ok "local index kept untouched" || bad "local index was modified"

# currency probe (extracted verbatim from update-skills.sh)
awk 'f&&/^  }$/{print;exit} /^  _persona_index_currency_probe\(\) \{/{f=1} f' "$US" > "$WORK/probe.inc"
[ -s "$WORK/probe.inc" ] || bad "could not extract _persona_index_currency_probe"
H="$WORK/home"; mkdir -p "$H/.openclaw/workspace/data" "$WORK/sk/shared-utils/prebuilt-index"
cp -R "$B1" "$H/.openclaw/workspace/data/coaching-personas"
cp "$WORK/m1.json" "$WORK/sk/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
( HOME="$H" SKILLS_DIR="$WORK/sk" EXTRACTED_DIR="$WORK/none"; source "$WORK/probe.inc"; _persona_index_currency_probe ) >"$WORK/probe.out" 2>&1
rc=$?
[ "$rc" -eq 0 ] && ok "currency probe: local-mode box with old sentinel is not stale (rc 0)" || bad "probe rc=$rc: $(cat "$WORK/probe.out")"
# control: a Gemini box with the same old sentinel must STILL read stale (probe discriminates)
rm -f "$H/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite"
mk_db "$H/.openclaw/workspace/data/coaching-personas/gemini-index.sqlite" gemini 5
( HOME="$H" SKILLS_DIR="$WORK/sk" EXTRACTED_DIR="$WORK/none"; source "$WORK/probe.inc"; _persona_index_currency_probe ) >"$WORK/probe2.out" 2>&1
[ "$?" -eq 1 ] && ok "control: gemini box with old sentinel still reads stale (rc 1)" || bad "control probe did not flag stale gemini box"

# ── 2. D3 re-assertion honours the flag ─────────────────────────────────────
grep -q '_PIDX_LOCAL_MODE:-0' "$US" && grep -q '_U6B_SENTINEL_NA' "$US" \
  && ok "update-skills.sh D3 re-assertion consults _PIDX_LOCAL_MODE" || bad "update-skills.sh D3 re-assertion ignores local mode"

# ── 3. older Gemini index is brought to release_tag ─────────────────────────
python3 -I - "$WORK/asset" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
c.execute("CREATE TABLE embeddings(id INTEGER, file_path TEXT, provider TEXT, section_number INTEGER, mode TEXT, persona_id TEXT)")
c.executemany("INSERT INTO embeddings VALUES(?,?,?,?,?,?)", [(i,"/x/personas/p%d/f.md"%(i%2),"gemini",3,"both","p%d"%(i%2)) for i in range(3)])
c.commit(); c.close()
PY
gzip -c "$WORK/asset" > "$WORK/asset.gz"; SHA="$(shasum -a 256 "$WORK/asset.gz" | cut -d' ' -f1)"
B3="$WORK/gem"; mk_box "$B3" gemini 1 "$TAG_OLD"
mk_manifest "$WORK/m3.json" "file://$WORK/asset.gz" "$SHA"
_PIDX_SKIP_WARNINGS=""
provision_persona_index "$WORK/m3.json" "$B3" >"$WORK/p3.out" 2>&1
[ "$(tr -d '[:space:]' < "$B3/.prebuilt-index-version")" = "$TAG_NEW" ] && [ "${_PIDX_LOCAL_MODE:-0}" = "0" ] \
  && ok "gemini box on $TAG_OLD upgraded to $TAG_NEW, not flagged local" || bad "gemini box not upgraded: $(cat "$WORK/p3.out")"

# ── 4. unreachable asset -> actionable reason ───────────────────────────────
B4="$WORK/dead"; mk_box "$B4" gemini 1 "$TAG_OLD"
mk_manifest "$WORK/m4.json" "file://$WORK/missing.gz" "$SHA"
_PIDX_SKIP_WARNINGS=""
provision_persona_index "$WORK/m4.json" "$B4" >"$WORK/p4.out" 2>&1
case "$_PIDX_SKIP_WARNINGS" in
  *"$TAG_NEW"*"missing.gz"*) ok "failed download leaves actionable reason (tag + url): ${_PIDX_SKIP_WARNINGS:0:120}..." ;;
  *) bad "no actionable reason recorded for failed download: '${_PIDX_SKIP_WARNINGS}'" ;;
esac

echo "=== $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ]

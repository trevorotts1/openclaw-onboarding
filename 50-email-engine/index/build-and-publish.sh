#!/usr/bin/env bash
# =============================================================================
# 50-email-engine/index/build-and-publish.sh
# -----------------------------------------------------------------------------
# EMBED-ONCE publisher for the SEPARATE email-superlibrary Gemini index.
# Cloned in spirit from shared-utils/prebuilt-index/build-and-publish.sh.
#
# OPERATOR BOX ONLY — needs `gh` auth + a client-supplied Google/Gemini key for
# the DELTA embed. This is INCREMENTAL + FURNACE-SAFE: it downloads the CURRENT
# published email-index asset, then runs gemini-indexer.py, whose HASH-SKIP guard
# embeds ONLY the new/changed email-library entries and skips every unchanged one.
# It NEVER starts from empty (a build-from-empty would be a full furnace re-embed).
#
# It publishes to a SEPARATE release tag from the persona index (email-index-v*),
# a SEPARATE sqlite (email-index.sqlite.gz), and updates ONLY EMAIL-INDEX-MANIFEST.json.
#
# USAGE:
#   index/build-and-publish.sh [--new-tag email-index-vX.Y.Z] [--entry-id <id> ...] [--dry-run]
#     --entry-id <id>   embed ONLY this catalog entry (repeatable). Default: --reindex-all
#                       (still incremental — HASH-SKIP skips unchanged entries).
#     --dry-run         do everything EXCEPT the gemini embed + the gh upload
#                       (proves the count/manifest math without spending credits).
# =============================================================================
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SELF_DIR/.." && pwd)"
MANIFEST="$SELF_DIR/EMAIL-INDEX-MANIFEST.json"
INDEXER="$SELF_DIR/gemini-indexer.py"
LIB="$SKILL_DIR/email-library"

NEW_TAG=""
DRY_RUN=0
ENTRY_IDS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --new-tag) NEW_TAG="$2"; shift 2 ;;
        --entry-id) ENTRY_IDS+=("$2"); shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,32p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 required" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 1; }
[ -f "$INDEXER" ]  || { echo "indexer not found: $INDEXER" >&2; exit 1; }

CUR_TAG="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("release_tag",""))' "$MANIFEST")"
CUR_URL="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("asset_url",""))' "$MANIFEST")"
CUR_SHA="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("sha256",""))' "$MANIFEST")"
FIRST_BUILD=0
[ -z "$CUR_SHA" ] && FIRST_BUILD=1

echo "→ email-index build (separate asset; current tag=$CUR_TAG first_build=$FIRST_BUILD)"

# ── 1) Download the CURRENT published asset unless this is the first build ────
GEMINI_INDEX="$(python3 - "$SKILL_DIR" <<'PY'
import sys, os
# Resolve the box-local email index path; fall back to a workspace path.
cands = [os.path.expanduser("~/.openclaw/data/email-index/email-index.sqlite"),
         "/data/.openclaw/data/email-index/email-index.sqlite",
         os.path.join(sys.argv[1], ".email-index", "email-index.sqlite")]
print(cands[0])
PY
)"
mkdir -p "$(dirname "$GEMINI_INDEX")"
if [ "$FIRST_BUILD" = "0" ] && [ "$DRY_RUN" = "0" ]; then
    echo "→ [1/5] downloading current published asset ($CUR_TAG) so the indexer embeds only the DELTA"
    TMP_GZ="$(mktemp -t email-index.XXXXXX.gz)"
    trap 'rm -f "$TMP_GZ"' EXIT
    if curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$CUR_URL" -o "$TMP_GZ"; then
        if command -v sha256sum >/dev/null 2>&1; then GOT="$(sha256sum "$TMP_GZ" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$TMP_GZ" | awk '{print $1}')"; fi
        [ "$GOT" = "$CUR_SHA" ] || { echo "WARN: base asset sha256 mismatch — refusing to build on a corrupt base" >&2; exit 1; }
        gunzip -c "$TMP_GZ" > "$GEMINI_INDEX"
        echo "  ✓ base asset in place + sha256 verified"
    else
        echo "WARN: could not download current asset — refusing (a build from empty would be a full furnace re-embed)" >&2
        exit 1
    fi
else
    echo "→ [1/5] first build (no prior asset) — the indexer builds the full email corpus once"
fi

# ── 2) Incremental index (HASH-SKIP embeds ONLY new/changed entries) ──────────
echo "→ [2/5] incremental index — HASH-SKIP embeds ONLY new/changed email-library entries"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] skipping the gemini embed step"
elif [ "${#ENTRY_IDS[@]}" -gt 0 ]; then
    for _id in "${ENTRY_IDS[@]}"; do
        echo "  indexing entry-id=$_id"
        python3 "$INDEXER" --entry-id "$_id"
    done
else
    python3 "$INDEXER" --reindex-all
fi

# ── 3) Recompute counts / sizes / sha256 + corpus_md5 ─────────────────────────
echo "→ [3/5] recomputing file_count + corpus_md5 (+ sha256/sizes when the asset exists)"
FILE_COUNT="$(find "$LIB" -name '*.md' ! -name 'README.md' | wc -l | tr -d ' ')"
CORPUS_MD5="$(python3 - "$LIB" <<'PY'
import hashlib, os, glob, sys
files = sorted(f for f in glob.glob(os.path.join(sys.argv[1], "**", "*.md"), recursive=True)
               if os.path.basename(f) != "README.md")
h = hashlib.md5()
for f in files:
    h.update(os.path.basename(f).encode()); h.update(open(f, "rb").read())
print(h.hexdigest())
PY
)"
NEW_SHA="$CUR_SHA"; GZ_BYTES=0; DB_BYTES=0; CHUNKS=0
if [ "$DRY_RUN" = "0" ] && [ -f "$GEMINI_INDEX" ]; then
    REBUILT_GZ="$(mktemp -t email-index-out.XXXXXX.gz)"
    gzip -c "$GEMINI_INDEX" > "$REBUILT_GZ"
    if command -v sha256sum >/dev/null 2>&1; then NEW_SHA="$(sha256sum "$REBUILT_GZ" | awk '{print $1}')"; else NEW_SHA="$(shasum -a 256 "$REBUILT_GZ" | awk '{print $1}')"; fi
    GZ_BYTES="$(wc -c < "$REBUILT_GZ" | tr -d ' ')"
    DB_BYTES="$(wc -c < "$GEMINI_INDEX" | tr -d ' ')"
    CHUNKS="$(python3 -c 'import sqlite3,sys
try:
    c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]); c.close()
except Exception:
    print(0)' "$GEMINI_INDEX")"
fi
echo "  file_count=$FILE_COUNT corpus_md5=$CORPUS_MD5 chunks=$CHUNKS"

# ── 4) Bump the manifest (email-index tag only) ───────────────────────────────
if [ -z "$NEW_TAG" ]; then
    NEW_TAG="$(python3 - "$CUR_TAG" <<'PY'
import re, sys
t = sys.argv[1] or "email-index-v1.0.0"
m = re.search(r'(\d+)\.(\d+)\.(\d+)$', t)
if not m:
    print("email-index-v1.0.0"); raise SystemExit
maj, minr, pat = (int(x) for x in m.groups())
print(t[:m.start()] + f"{maj}.{minr}.{pat+1}")
PY
)"
fi
NEW_URL="https://github.com/trevorotts1/openclaw-onboarding/releases/download/$NEW_TAG/email-index.sqlite.gz"
echo "→ [4/5] bumping EMAIL-INDEX-MANIFEST.json → release_tag=$NEW_TAG file_count=$FILE_COUNT chunk_count=$CHUNKS"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] manifest not written"
else
    python3 - "$MANIFEST" "$FILE_COUNT" "$CHUNKS" "$NEW_SHA" "$NEW_TAG" "$NEW_URL" "$GZ_BYTES" "$DB_BYTES" "$CORPUS_MD5" <<'PY'
import json, sys, datetime
(mp, fc, chunks, sha, tag, url, gz, db, cmd5) = sys.argv[1:10]
m = json.load(open(mp))
today = datetime.date.today().isoformat()
m["file_count"] = int(fc); m["chunk_count"] = int(chunks)
m["sha256"] = sha; m["release_tag"] = tag; m["asset_url"] = url
m["gz_size_bytes"] = int(gz); m["source_db_bytes"] = int(db)
m["corpus_md5"] = cmd5; m["build_date"] = today; m["manifest_last_updated"] = today
m["asset_rebuild_required"] = (int(chunks) == 0)
json.dump(m, open(mp, "w"), indent=2); open(mp, "a").write("\n")
print("  ✓ manifest written")
PY
fi

# ── 5) Publish the SEPARATE GitHub Release asset ──────────────────────────────
echo "→ [5/5] publishing email-index GitHub Release asset ($NEW_TAG)"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would: gh release create/upload $NEW_TAG email-index.sqlite.gz"
elif [ -f "${REBUILT_GZ:-/nonexistent}" ]; then
    command -v gh >/dev/null 2>&1 || { echo "gh CLI required to publish" >&2; exit 1; }
    UP_GZ="$(dirname "$REBUILT_GZ")/email-index.sqlite.gz"
    cp -f "$REBUILT_GZ" "$UP_GZ"
    if gh release view "$NEW_TAG" -R trevorotts1/openclaw-onboarding >/dev/null 2>&1; then
        gh release upload "$NEW_TAG" "$UP_GZ" --clobber -R trevorotts1/openclaw-onboarding
    else
        gh release create "$NEW_TAG" "$UP_GZ" -R trevorotts1/openclaw-onboarding \
            --title "$NEW_TAG" --notes "Email-superlibrary Gemini index: $FILE_COUNT entries / $CHUNKS chunks (delta-embedded, HASH-SKIP)."
    fi
    rm -f "$UP_GZ" "$REBUILT_GZ"
    echo "  ✓ published $NEW_TAG"
else
    echo "  (no rebuilt asset to publish — dry-run or embed step skipped)"
fi

echo "DONE. Commit EMAIL-INDEX-MANIFEST.json (release_tag=$NEW_TAG). Client boxes provision via provision-email-index.sh (download + sha256 verify; NEVER re-embed)."

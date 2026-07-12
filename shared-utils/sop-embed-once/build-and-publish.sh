#!/usr/bin/env bash
# shared-utils/sop-embed-once/build-and-publish.sh
# ─────────────────────────────────────────────────────────────────────────────
# P4-03 step 1 — the MISSING "embed once, push to clients" pipeline for the CC
# SOP/routing embedding system (System 2). Mirrors
# shared-utils/prebuilt-index/build-and-publish.sh (System 1, proven, mature)
# field-for-field: incremental (HASH-SKIP), hermetic, real-vector hard gate,
# manifest-driven, GitHub Release asset.
#
# Before this script, the ONLY writer of sop_embeddings was
# scripts/backfill-sop-embeddings.ts in the CC repo, run PER CLIENT with the
# CLIENT's own key against the shared SOP library — the exact "operator
# generates embeddings so clients don't burn tokens" contract, broken. This
# script embeds the CANONICAL shared sops.jsonl ONCE with the OPERATOR's key
# and publishes a versioned sop_embeddings sqlite asset every client box pulls
# read-only (shared-utils/provision-sop-embeddings.sh).
#
# USAGE (operator box only — needs gh auth + a Gemini/Google API key for the DELTA):
#   shared-utils/sop-embed-once/build-and-publish.sh [--new-tag sop-embeddings-vX.Y.Z]
#                                                     [--jsonl-tag <onboarding-release-tag>]
#                                                     [--sop-slug <slug> ...]
#                                                     [--dry-run]
#
#   --jsonl-tag   which onboarding release carries the canonical sops-library-v2.jsonl.gz
#                 asset (default: the tag ingest-sop-library.sh currently pins).
#   --sop-slug    embed ONLY this SOP (repeatable). Default: consider every SOP
#                 (still incremental — HASH-SKIP skips unchanged rows).
#   --new-tag     release tag for the rebuilt asset. Default: auto-bump the
#                 patch of the manifest's current release_tag.
#   --dry-run     do everything EXCEPT the gemini embed + the gh upload
#                 (proves the count/manifest math without spending credits).
#
# Ordered steps (fully HERMETIC — stages in a temp dir, never touches a live
# workspace or a live mission-control.db): download current asset (if any) →
# download canonical sops.jsonl → incremental embed (HASH-SKIP) → REAL-VECTOR
# HARD GATE → recompute counts/sha256/sizes → bump manifest → gh release upload.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
MANIFEST="$SELF_DIR/SOP-EMBEDDINGS-MANIFEST.json"
EMBEDDER="$SELF_DIR/embed_sop_library.py"
REPO_SLUG="trevorotts1/openclaw-onboarding"
SOP_ASSET_NAME="sops-library-v2.jsonl.gz"

NEW_TAG=""
JSONL_TAG=""
DRY_RUN=0
SOP_SLUGS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --new-tag) NEW_TAG="$2"; shift 2 ;;
        --jsonl-tag) JSONL_TAG="$2"; shift 2 ;;
        --sop-slug) SOP_SLUGS+=("$2"); shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 required" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 1; }
[ -f "$EMBEDDER" ]  || { echo "embedder not found: $EMBEDDER" >&2; exit 1; }

BUILD_DIR="$(mktemp -d -t sop-embed-once-build.XXXXXX)"
STAGED_DB="$BUILD_DIR/sop-embeddings.sqlite"
trap 'rm -rf "$BUILD_DIR"' EXIT
echo "→ hermetic build dir: $BUILD_DIR"

# Preflight: a real Gemini key must resolve before we spend a download — a
# keyless run can no longer produce fake vectors (the embedder hard-fails via
# embedding_engine.get_embedder), but failing here is faster/clearer.
KEY_STATE="$(python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "shared-utils"))
from embedding_engine import _read_secret
print("SET" if (_read_secret("GOOGLE_API_KEY") or _read_secret("GEMINI_API_KEY")) else "NOT-SET")
PY
)"
echo "→ GOOGLE_API_KEY/GEMINI_API_KEY: $KEY_STATE"
if [ "$KEY_STATE" != "SET" ] && [ "$DRY_RUN" != "1" ]; then
    echo "ERROR: no Gemini key resolves from any canonical secret store — the delta embed would fail. Set the key (by name) and re-run." >&2
    exit 1
fi

# ── 1) Download the CURRENT published asset (if the manifest carries one) ────
CUR_TAG="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("release_tag") or "")' "$MANIFEST")"
CUR_URL="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("asset_url") or "")' "$MANIFEST")"
CUR_SHA="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("sha256") or "")' "$MANIFEST")"

if [ -n "$CUR_URL" ] && [ -n "$CUR_SHA" ]; then
    echo "→ [1/6] downloading current published asset ($CUR_TAG) so the embedder computes only the DELTA"
    TMP_GZ="$(mktemp -t sop-embeddings.XXXXXX.gz)"
    if curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$CUR_URL" -o "$TMP_GZ" 2>/dev/null; then
        if command -v sha256sum >/dev/null 2>&1; then GOT="$(sha256sum "$TMP_GZ" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$TMP_GZ" | awk '{print $1}')"; fi
        [ "$GOT" = "$CUR_SHA" ] || { echo "WARN: downloaded asset sha256 mismatch ($GOT != $CUR_SHA) — refusing to build on a corrupt base" >&2; rm -f "$TMP_GZ"; exit 1; }
        gunzip -c "$TMP_GZ" > "$STAGED_DB"
        rm -f "$TMP_GZ"
        echo "  ✓ base asset staged + sha256 verified"
    else
        echo "WARN: could not download current asset ($CUR_URL) — starting from an EMPTY staged DB (full first publish)" >&2
        rm -f "$TMP_GZ"
    fi
else
    echo "→ [1/6] no prior published asset in the manifest — this is the FIRST publish (full embed of the shared library)"
fi

# ── 2) Download the canonical shared SOP library (sops.jsonl) ────────────────
echo "→ [2/6] resolving canonical sops.jsonl (the SAME content ingest-sop-library.sh downloads)"
DEFAULT_JSONL_TAG="v10.13.29"
JSONL_TAG="${JSONL_TAG:-$DEFAULT_JSONL_TAG}"
JSONL_URL="https://github.com/${REPO_SLUG}/releases/download/${JSONL_TAG}/${SOP_ASSET_NAME}"
STAGED_JSONL_GZ="$BUILD_DIR/${SOP_ASSET_NAME}"
STAGED_JSONL="$BUILD_DIR/sops.jsonl"
if [ "$DRY_RUN" = "1" ] && ! curl -L --fail -sS -o "$STAGED_JSONL_GZ" "$JSONL_URL" 2>/dev/null; then
    echo "  [dry-run] could not download $JSONL_URL (offline/sandboxed dry-run) — synthesizing a tiny fixture jsonl so the count/manifest math is still provable"
    printf '%s\n' \
      '{"slug":"dry-run-fixture-sop","name":"Dry Run Fixture SOP","description":"Synthetic fixture for --dry-run math proof only.","task_keywords":"dry-run,fixture","steps":[{"name":"Step one"},{"name":"Step two"}]}' \
      > "$STAGED_JSONL"
elif [ ! -f "$STAGED_JSONL_GZ" ]; then
    curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$JSONL_URL" -o "$STAGED_JSONL_GZ"
    gunzip -c "$STAGED_JSONL_GZ" > "$STAGED_JSONL"
else
    gunzip -c "$STAGED_JSONL_GZ" > "$STAGED_JSONL"
fi
SOP_COUNT_SRC="$(wc -l < "$STAGED_JSONL" | tr -d ' ')"
echo "  ✓ staged $SOP_COUNT_SRC SOP record(s) from $STAGED_JSONL"

# ── 3) Incremental embed (HASH-SKIP embeds ONLY new/changed SOPs) ────────────
echo "→ [3/6] incremental embed — HASH-SKIP guard embeds ONLY new/changed SOPs (NO full furnace)"
EMBED_ARGS=(--jsonl "$STAGED_JSONL" --db "$STAGED_DB")
if [ "${#SOP_SLUGS[@]}" -gt 0 ]; then
    for _s in "${SOP_SLUGS[@]}"; do EMBED_ARGS+=(--sop-slug "$_s"); done
fi
if [ "$DRY_RUN" = "1" ]; then
    EMBED_ARGS+=(--dry-run)
fi
python3 "$EMBEDDER" "${EMBED_ARGS[@]}"

# ── 3.5) REAL-VECTOR HARD GATE ────────────────────────────────────────────────
# Skipped on --dry-run (no vectors were actually written).
if [ "$DRY_RUN" != "1" ]; then
    echo "→ [3.5/6] real-vector hard gate — verifying every row is gemini/3072 float32"
    python3 "$EMBEDDER" --db "$STAGED_DB" --verify
fi

# ── 4) Recompute counts / sizes / sha256 from the rebuilt DB ──────────────────
echo "→ [4/6] recomputing counts + sha256"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] skipping gzip/sha256/publish — count math only"
    ROW_COUNT="$(python3 -c '
import sqlite3, sys, os
p = sys.argv[1]
if not os.path.exists(p):
    print(0)
else:
    c = sqlite3.connect(p)
    try:
        print(c.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0])
    except Exception:
        print(0)
' "$STAGED_DB")"
    echo "  staged sop_embeddings row_count=$ROW_COUNT (source sops=$SOP_COUNT_SRC) — dry-run stops here"
    echo "DONE (dry-run). No manifest written, no release published."
    exit 0
fi

REBUILT_GZ="$(mktemp -t sop-embeddings-out.XXXXXX.gz)"
gzip -c "$STAGED_DB" > "$REBUILT_GZ"
if command -v sha256sum >/dev/null 2>&1; then NEW_SHA="$(sha256sum "$REBUILT_GZ" | awk '{print $1}')"; else NEW_SHA="$(shasum -a 256 "$REBUILT_GZ" | awk '{print $1}')"; fi
GZ_BYTES="$(wc -c < "$REBUILT_GZ" | tr -d ' ')"
DB_BYTES="$(wc -c < "$STAGED_DB" | tr -d ' ')"
ROW_COUNT="$(python3 -c 'import sqlite3,sys;c=sqlite3.connect(sys.argv[1]);print(c.execute("SELECT COUNT(*) FROM sop_embeddings").fetchone()[0])' "$STAGED_DB")"
echo "  sop_embeddings row_count=$ROW_COUNT  source sops=$SOP_COUNT_SRC"

# Triad guard — refuse to publish a mismatched asset (mirrors the persona
# pipeline's N38 triad gate): every source SOP must have been embedded.
if [ "$ROW_COUNT" -lt "$SOP_COUNT_SRC" ]; then
    echo "WARN: row_count ($ROW_COUNT) < source sop count ($SOP_COUNT_SRC) — NOT publishing an incomplete asset" >&2
    rm -f "$REBUILT_GZ"
    exit 1
fi

# ── 5) Bump the manifest ──────────────────────────────────────────────────────
if [ -z "$NEW_TAG" ]; then
    if [ -z "$CUR_TAG" ]; then
        NEW_TAG="sop-embeddings-v1.0.0"
    else
        NEW_TAG="$(python3 - "$CUR_TAG" <<'PY'
import re, sys
t = sys.argv[1]
m = re.search(r'(\d+)\.(\d+)\.(\d+)$', t)
if not m:
    print(t + "-rebuilt"); raise SystemExit
maj, minr, pat = (int(x) for x in m.groups())
print(t[:m.start()] + f"{maj}.{minr}.{pat+1}")
PY
)"
    fi
fi
NEW_URL="https://github.com/${REPO_SLUG}/releases/download/${NEW_TAG}/sop-embeddings.sqlite.gz"
echo "→ [5/6] bumping manifest → release_tag=$NEW_TAG sop_count=$ROW_COUNT"
python3 - "$MANIFEST" "$ROW_COUNT" "$NEW_SHA" "$NEW_TAG" "$NEW_URL" "$GZ_BYTES" "$DB_BYTES" "$JSONL_TAG" <<'PY'
import json, sys, datetime
(mp, sop_count, sha, tag, url, gz, db, jsonl_tag) = sys.argv[1:9]
m = json.load(open(mp))
today = datetime.date.today().isoformat()
m["model"] = "gemini-embedding-2"
m["dims"] = 3072
m["provider"] = "gemini"
m["sop_count"] = int(sop_count)
m["chunk_count"] = int(sop_count)   # one row per SOP — chunk_count == sop_count for this corpus
m["sha256"] = sha
m["release_tag"] = tag
m["asset_url"] = url
m["gz_size_bytes"] = int(gz)
m["gz_size_mb"] = round(int(gz) / (1024 * 1024), 2)
m["source_db_bytes"] = int(db)
m["build_date"] = today
m["manifest_last_updated"] = today
m["source_jsonl_release_tag"] = jsonl_tag
m["asset_rebuild_required"] = False
json.dump(m, open(mp, "w"), indent=2)
open(mp, "a").write("\n")
print("  ✓ manifest written")
PY

# ── 6) Publish the new GitHub Release asset ───────────────────────────────────
echo "→ [6/6] publishing GitHub Release asset ($NEW_TAG)"
command -v gh >/dev/null 2>&1 || { echo "gh CLI required to publish" >&2; rm -f "$REBUILT_GZ"; exit 1; }
UP_GZ="$(dirname "$REBUILT_GZ")/sop-embeddings.sqlite.gz"
cp -f "$REBUILT_GZ" "$UP_GZ"
if gh release view "$NEW_TAG" -R "$REPO_SLUG" >/dev/null 2>&1; then
    gh release upload "$NEW_TAG" "$UP_GZ" --clobber -R "$REPO_SLUG"
else
    gh release create "$NEW_TAG" "$UP_GZ" -R "$REPO_SLUG" \
        --title "$NEW_TAG" --notes "Incremental SOP-embeddings rebuild: $ROW_COUNT SOPs (delta-embedded, HASH-SKIP, gemini-embedding-2 @3072)."
fi
rm -f "$UP_GZ" "$REBUILT_GZ"
echo "  ✓ published $NEW_TAG"
echo "DONE. Commit the updated SOP-EMBEDDINGS-MANIFEST.json (release_tag=$NEW_TAG)."

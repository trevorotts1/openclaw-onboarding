#!/usr/bin/env bash
# shared-utils/prebuilt-index/build-and-publish.sh
# ─────────────────────────────────────────────────────────────────────────────
# FIX 3 (BREAK 3) — the MISSING publish automation for the prebuilt persona index.
#
# Adding a persona = add a blueprint dir + a persona-categories.json key. The
# gemini-index.sqlite ASSET (on GitHub Releases) and INDEX-MANIFEST.json must
# then be rebuilt + re-published. Before this script that was a hand step that
# lagged the source by DAYS — the exact gap that let one client answer "no new
# personas since March."
#
# THIS SCRIPT IS INCREMENTAL AND FURNACE-SAFE. It does NOT re-embed all personas.
# It downloads the CURRENT published asset, then runs gemini-section-indexer.py,
# whose md5 HASH-SKIP guard (gemini-section-indexer.py:219-237) embeds ONLY the
# new/changed personas and HASH-SKIPs every unchanged one. Persona #55 = ~tens of
# vectors, never the full 4413.
#
# USAGE (operator box only — needs gh auth + a Gemini/Google API key for the DELTA):
#   shared-utils/prebuilt-index/build-and-publish.sh [--new-tag prebuilt-index-vX.Y.Z]
#                                                     [--persona-id <slug> ...]
#                                                     [--dry-run]
#
#   --persona-id <slug>   embed ONLY this persona (repeatable). Default: --reindex-all
#                         (still incremental — HASH-SKIP skips unchanged personas).
#   --new-tag             release tag for the rebuilt asset. Default: auto-bump the
#                         patch of the manifest's current release_tag.
#   --dry-run             do everything EXCEPT the gemini embed + the gh upload
#                         (proves the count/manifest math without spending credits).
#
# Ordered steps: download current asset → reconcile blueprints → incremental
# index → recompute counts/sha256/sizes → bump manifest → gh release upload.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"
MANIFEST="$SELF_DIR/INDEX-MANIFEST.json"
INDEXER="$REPO_ROOT/23-ai-workforce-blueprint/scripts/gemini-section-indexer.py"
PROVISION_HELPER="$REPO_ROOT/shared-utils/provision-persona-index.sh"
SK22="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"

NEW_TAG=""
DRY_RUN=0
PERSONA_IDS=()
while [ $# -gt 0 ]; do
    case "$1" in
        --new-tag) NEW_TAG="$2"; shift 2 ;;
        --persona-id) PERSONA_IDS+=("$2"); shift 2 ;;
        --dry-run) DRY_RUN=1; shift ;;
        -h|--help) sed -n '2,40p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 required" >&2; exit 1; }
[ -f "$MANIFEST" ] || { echo "manifest not found: $MANIFEST" >&2; exit 1; }
[ -f "$INDEXER" ]  || { echo "indexer not found: $INDEXER" >&2; exit 1; }

# Resolve the live gemini index + canonical personas dir the indexer writes to.
GEMINI_INDEX="$(python3 - "$REPO_ROOT" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[1]) / "shared-utils"))
from detect_platform import get_openclaw_paths
print(get_openclaw_paths()["gemini_index"])
PY
)"
COACHING_DB_DIR="$(dirname "$GEMINI_INDEX")/coaching-personas"
echo "→ gemini index: $GEMINI_INDEX"
echo "→ coaching dir: $COACHING_DB_DIR"

# base_tag / base_sha decouple "what to download" from "what to publish" so the
# manifest can be pre-staged with the next release_tag (e.g. v2.2.1) while still
# downloading the last good published asset (e.g. v2.2.0). When base_tag is
# absent the manifest's own release_tag is used (backward-compatible).
CUR_TAG="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("base_tag") or d["release_tag"])' "$MANIFEST")"
CUR_URL="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("base_asset_url") or d["asset_url"])' "$MANIFEST")"
CUR_SHA="$(python3 -c 'import json,sys;d=json.load(open(sys.argv[1]));print(d.get("base_sha256") or d["sha256"])' "$MANIFEST")"

# ── 1) Download the CURRENT published asset (NEVER start empty) ───────────────
echo "→ [1/6] downloading current published asset ($CUR_TAG) so the indexer embeds only the DELTA"
TMP_GZ="$(mktemp -t gemini-index.XXXXXX.gz)"
trap 'rm -f "$TMP_GZ"' EXIT
if curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$CUR_URL" -o "$TMP_GZ"; then
    if command -v sha256sum >/dev/null 2>&1; then GOT="$(sha256sum "$TMP_GZ" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$TMP_GZ" | awk '{print $1}')"; fi
    [ "$GOT" = "$CUR_SHA" ] || { echo "WARN: downloaded asset sha256 mismatch ($GOT != $CUR_SHA) — refusing to build on a corrupt base" >&2; exit 1; }
    mkdir -p "$COACHING_DB_DIR"
    gunzip -c "$TMP_GZ" > "$GEMINI_INDEX"
    echo "  ✓ base asset in place + sha256 verified"
else
    echo "WARN: could not download current asset — refusing to build (a build from empty would be a full furnace re-embed)" >&2
    exit 1
fi

# ── 1.5) Back-stamp blank provider/model/dim on the downloaded base asset ─────
# gemini-section-indexer.py did not write provider/model/dim before this fix
# (those columns were missing from its INSERT). The 11 delta personas added to
# v2.2.0 via the incremental indexer arrived with provider=NULL. The search()
# path in embedding_engine.py includes "OR provider IS NULL" as a safety net,
# but the per-row metadata contract requires every row to carry the correct
# provider/model/dim so analytics, status, and future tooling work correctly.
# init_db() only calls _backfill_provider_columns() when the columns themselves
# are absent — it does NOT re-run when they already exist but some rows are NULL.
# This step explicitly backfills any NULL rows from the blob length before the
# incremental index runs, guaranteeing the published asset has no blank-provider
# rows regardless of how many delta personas were previously indexed.
echo "→ [1.5/6] back-stamping blank provider/model/dim rows on downloaded asset (no re-embed)"
python3 - "$GEMINI_INDEX" <<'PY'
import sqlite3, sys
DB = sys.argv[1]
# dim->provider/model map mirrors embedding_engine._DIM_TO_PROVIDER
_DIM_MAP = {
    3072: ("gemini", "gemini-embedding-2"),
    1536: ("openai", "text-embedding-3-small"),
}
conn = sqlite3.connect(DB, timeout=30.0)
cur = conn.cursor()
# Ensure provider/model/dim columns exist (may be absent on very old base assets)
existing = {r[1] for r in cur.execute("PRAGMA table_info(embeddings)")}
for col, coltype in [("provider", "TEXT"), ("model", "TEXT"), ("dim", "INTEGER")]:
    if col not in existing:
        cur.execute(f"ALTER TABLE embeddings ADD COLUMN {col} {coltype}")
conn.commit()
cur.execute("SELECT id, vector FROM embeddings WHERE provider IS NULL OR provider = ''")
rows = cur.fetchall()
updated = 0
flagged = 0
for row_id, blob in rows:
    if blob is None:
        continue
    dim = len(blob) // 4  # float32 = 4 bytes per element
    if dim in _DIM_MAP:
        prov, mdl = _DIM_MAP[dim]
        cur.execute(
            "UPDATE embeddings SET provider=?, model=?, dim=? WHERE id=?",
            (prov, mdl, dim, row_id),
        )
        updated += 1
    else:
        cur.execute(
            "UPDATE embeddings SET provider='unknown', model='unknown', dim=? WHERE id=?",
            (dim, row_id),
        )
        flagged += 1
conn.commit()
conn.close()
if flagged:
    print(f"  WARN: {flagged} row(s) stamped provider='unknown' (unrecognised dim)")
print(f"  ✓ backstamped {updated} blank-provider row(s) from blob length — no re-embed")
PY

# ── 2) Reconcile canonical blueprints into the coaching dir ───────────────────
echo "→ [2/6] reconciling canonical blueprints into $COACHING_DB_DIR"
if [ -f "$PROVISION_HELPER" ]; then
    # shellcheck source=/dev/null
    source "$PROVISION_HELPER"
    WS="$(dirname "$(dirname "$COACHING_DB_DIR")")"   # …/workspace
    reconcile_persona_assets "$SK22" "$COACHING_DB_DIR" "$WS"
fi

# ── 3) Incremental index (HASH-SKIP embeds ONLY new/changed personas) ─────────
echo "→ [3/6] incremental index — HASH-SKIP guard embeds ONLY new/changed personas (NO full furnace)"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] skipping the gemini embed step"
elif [ "${#PERSONA_IDS[@]}" -gt 0 ]; then
    for _pid in "${PERSONA_IDS[@]}"; do
        echo "  indexing persona-id=$_pid"
        python3 "$INDEXER" --persona-id "$_pid"
    done
else
    python3 "$INDEXER" --reindex-all
fi

# ── 4) Recompute counts / sizes / sha256 from the rebuilt DB ──────────────────
echo "→ [4/6] recomputing counts + sha256"
REBUILT_GZ="$(mktemp -t gemini-index-out.XXXXXX.gz)"
gzip -c "$GEMINI_INDEX" > "$REBUILT_GZ"
if command -v sha256sum >/dev/null 2>&1; then NEW_SHA="$(sha256sum "$REBUILT_GZ" | awk '{print $1}')"; else NEW_SHA="$(shasum -a 256 "$REBUILT_GZ" | awk '{print $1}')"; fi
GZ_BYTES="$(wc -c < "$REBUILT_GZ" | tr -d ' ')"
DB_BYTES="$(wc -c < "$GEMINI_INDEX" | tr -d ' ')"
read -r CHUNKS PERSONAS <<EOF
$(python3 - "$GEMINI_INDEX" <<'PY'
import sqlite3, sys
c = sqlite3.connect(sys.argv[1])
chunks = c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]
personas = c.execute("SELECT COUNT(DISTINCT persona_id) FROM embeddings WHERE persona_id IS NOT NULL").fetchone()[0]
print(chunks, personas)
PY
)
EOF
DIR_PERSONAS="$(find "$SK22/personas" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
CAT_PERSONAS="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("personas",{})))' "$SK22/persona-categories.json")"
SET_MD5="$(python3 -c 'import hashlib,sys;print(hashlib.md5(open(sys.argv[1],"rb").read()).hexdigest())' "$SK22/persona-categories.json")"
echo "  embeddings chunks=$CHUNKS  embedded personas=$PERSONAS  blueprint dirs=$DIR_PERSONAS  categories keys=$CAT_PERSONAS"

# Triad guard — refuse to publish a mismatched asset (mirrors the N38 7th assertion).
if [ "$DIR_PERSONAS" != "$CAT_PERSONAS" ] || [ "$PERSONAS" != "$DIR_PERSONAS" ]; then
    echo "WARN: persona count triad disagrees (dirs=$DIR_PERSONAS keys=$CAT_PERSONAS embedded=$PERSONAS) — NOT publishing a broken asset" >&2
    rm -f "$REBUILT_GZ"; exit 1
fi

# ── 5) Bump the manifest ──────────────────────────────────────────────────────
if [ -z "$NEW_TAG" ]; then
    # If the manifest was pre-staged with a target release_tag that is already
    # AHEAD of the base we downloaded (e.g. manifest.release_tag=v2.2.1 while
    # we downloaded base_tag=v2.2.0), honour the pre-staged tag directly.
    MANIFEST_TAG="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["release_tag"])' "$MANIFEST")"
    if [ "$MANIFEST_TAG" != "$CUR_TAG" ]; then
        NEW_TAG="$MANIFEST_TAG"
        echo "  using pre-staged release_tag=$NEW_TAG (base was $CUR_TAG)"
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
NEW_URL="https://github.com/trevorotts1/openclaw-onboarding/releases/download/$NEW_TAG/gemini-index.sqlite.gz"
echo "→ [5/6] bumping manifest → release_tag=$NEW_TAG persona_count=$DIR_PERSONAS chunk_count=$CHUNKS"
python3 - "$MANIFEST" "$DIR_PERSONAS" "$CHUNKS" "$NEW_SHA" "$NEW_TAG" "$NEW_URL" "$GZ_BYTES" "$DB_BYTES" "$SET_MD5" "$DIR_PERSONAS" <<'PY'
import json, sys, datetime
(mp, personas, chunks, sha, tag, url, gz, db, set_md5, canon) = sys.argv[1:12]
m = json.load(open(mp))
today = datetime.date.today().isoformat()
m["persona_count"] = int(personas)
m["canonical_persona_count"] = int(canon)
m["chunk_count"] = int(chunks)
m["sha256"] = sha
m["release_tag"] = tag
m["asset_url"] = url
m["gz_size_bytes"] = int(gz)
m["gz_size_mb"] = round(int(gz) / (1024 * 1024), 2)
m["source_db_bytes"] = int(db)
m["build_date"] = today
m["manifest_last_updated"] = today
m["persona_set_md5"] = set_md5
m["asset_rebuild_required"] = False
# Clear the base_tag / base_sha256 / base_asset_url staging fields once the
# build has succeeded — the new release_tag IS the canonical asset now.
for _k in ("base_tag", "base_sha256", "base_asset_url"):
    m.pop(_k, None)
json.dump(m, open(mp, "w"), indent=2)
open(mp, "a").write("\n")
print("  ✓ manifest written")
PY

# ── 6) Publish the new GitHub Release asset ───────────────────────────────────
echo "→ [6/6] publishing GitHub Release asset ($NEW_TAG)"
if [ "$DRY_RUN" = "1" ]; then
    echo "  [dry-run] would: gh release create $NEW_TAG $REBUILT_GZ (or gh release upload)"
else
    command -v gh >/dev/null 2>&1 || { echo "gh CLI required to publish" >&2; exit 1; }
    UP_GZ="$(dirname "$REBUILT_GZ")/gemini-index.sqlite.gz"
    cp -f "$REBUILT_GZ" "$UP_GZ"
    if gh release view "$NEW_TAG" -R trevorotts1/openclaw-onboarding >/dev/null 2>&1; then
        gh release upload "$NEW_TAG" "$UP_GZ" --clobber -R trevorotts1/openclaw-onboarding
    else
        gh release create "$NEW_TAG" "$UP_GZ" -R trevorotts1/openclaw-onboarding \
            --title "$NEW_TAG" --notes "Incremental persona-index rebuild: $DIR_PERSONAS personas / $CHUNKS chunks (delta-embedded, HASH-SKIP)."
    fi
    rm -f "$UP_GZ"
    echo "  ✓ published $NEW_TAG"
fi

rm -f "$REBUILT_GZ"
echo "DONE. Commit the updated INDEX-MANIFEST.json (release_tag=$NEW_TAG). The N38 triad gate + persona-set-asset-consistency-guard CI will verify it."

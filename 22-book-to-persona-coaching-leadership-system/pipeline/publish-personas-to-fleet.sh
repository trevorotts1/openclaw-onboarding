#!/usr/bin/env bash
# 22-book-to-persona-coaching-leadership-system/pipeline/publish-personas-to-fleet.sh
# ─────────────────────────────────────────────────────────────────────────────
# THE ONE COMMAND — publish the current WORKSPACE persona set to the fleet,
# bringing ALL FOUR coupled artifacts into a consistent state in ONE atomic run:
#
#   (a) repo blueprint dirs   22-…/personas/<slug>/persona-blueprint.md
#                             (copied from the workspace, SANITIZED of
#                             operator-local absolute paths)
#   (b) repo persona-categories.json  (workspace entries merged in, validated
#                             against the controlled-vocabulary tag sets)
#   (c) INDEX-MANIFEST.json   persona_count / canonical_persona_count /
#                             chunk_count / sha256 / release_tag / persona_set_md5
#   (d) the gzipped index RELEASE ASSET  (rebuilt + published; the fleet is only
#                             pointed at it after a sha256 match)
#
# WHY THIS EXISTS
#   The Skill-22 book pipeline writes ONLY the workspace
#   (~/.openclaw/workspace/data/coaching-personas/). Nothing copied the new
#   persona back into the repo library, so the workspace/asset advanced while
#   the repo blueprint dirs + categories seed lagged — main went red at the new
#   count (or a roll shipped the OLD count) until someone hand-caught the repo
#   up. This command closes that gap STRUCTURALLY: it is the mandated, single,
#   atomic, re-runnable step that moves all four together, and REFUSES to
#   complete (nonzero, NO half-committed state) unless the N38 count triad AND
#   the index-asset persona count ALL equal the same N.
#
# ATOMICITY
#   Every repo file it may touch (personas/ blueprint tree, persona-categories.json,
#   INDEX-MANIFEST.json) is snapshotted before any write. On ANY failure — vocab
#   violation, asset build failure, a triad that does not agree at the end — the
#   snapshot is RESTORED and the script exits nonzero. A successful run leaves a
#   consistent working tree for the operator to review + commit (the script does
#   NOT git-commit — the operator owns GitHub).
#
# IDEMPOTENT / RE-RUNNABLE
#   If the repo already matches the workspace and the triad already agrees, it is
#   a no-op success — it does NOT re-embed, re-tag, or re-upload.
#
# USAGE
#   pipeline/publish-personas-to-fleet.sh [--workspace DIR] [--repo ROOT]
#                                         [--no-asset] [--dry-run] [--yes]
#
#   --workspace DIR   workspace coaching-personas dir (default: live-resolve;
#                     env PUBLISH_PERSONAS_WORKSPACE overrides). Must contain
#                     personas/ and persona-categories.json.
#   --repo ROOT       repo root to publish INTO (default: this checkout).
#   --no-asset        HERMETIC: sync (a)+(b) + the manifest COUNT fields (c) +
#                     prove the triad, but SKIP the embed + asset publish (d).
#                     Marks the manifest asset_rebuild_required=true. No network,
#                     no Gemini key, no gh — used by the tests and to stage a
#                     repo-side catch-up you will follow with a real asset build.
#   --dry-run         run build-and-publish.sh --dry-run (proves the count/asset
#                     math without spending embed credits or uploading).
#   --yes             non-interactive (assume yes).
#
# EXIT CODES
#   0  all four artifacts consistent at N (published, or --no-asset staged)
#   2  usage / environment error
#   4  controlled-vocabulary violation (rolled back)
#   5  triad did not agree at the end (rolled back)
#   6  asset build/publish failed (rolled back)
#   7  INDEX-VERIFY FAILED (A-U8) — a workspace persona is neither indexed in
#      the live gemini-index.sqlite nor covered by an honest
#      embedding-receipt.json deferred marker (checked before any repo write)
# ─────────────────────────────────────────────────────────────────────────────
set -uo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PF="$SELF_DIR/persona_fleet.py"
DEFAULT_REPO_ROOT="$(cd "$SELF_DIR/../.." && pwd)"

WORKSPACE="${PUBLISH_PERSONAS_WORKSPACE:-}"
REPO_ROOT="$DEFAULT_REPO_ROOT"
NO_ASSET=0
DRY_RUN=0
ASSUME_YES=0

while [ $# -gt 0 ]; do
    case "$1" in
        --workspace) WORKSPACE="$2"; shift 2 ;;
        --repo)      REPO_ROOT="$2"; shift 2 ;;
        --no-asset)  NO_ASSET=1; shift ;;
        --dry-run)   DRY_RUN=1; shift ;;
        --yes|-y)    ASSUME_YES=1; shift ;;
        -h|--help)   sed -n '2,60p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

command -v python3 >/dev/null 2>&1 || { echo "python3 required" >&2; exit 2; }
[ -f "$PF" ] || { echo "core helper not found: $PF" >&2; exit 2; }

REPO_ROOT="$(cd "$REPO_ROOT" 2>/dev/null && pwd)" || { echo "bad --repo: $REPO_ROOT" >&2; exit 2; }
SK22="$REPO_ROOT/22-book-to-persona-coaching-leadership-system"
REPO_PERSONAS="$SK22/personas"
REPO_CAT="$SK22/persona-categories.json"
MANIFEST="$REPO_ROOT/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
BUILD_PUBLISH="$REPO_ROOT/shared-utils/prebuilt-index/build-and-publish.sh"
STATUS_HELPER="$SELF_DIR/fleet-publish-status.sh"
for f in "$REPO_PERSONAS" "$REPO_CAT" "$MANIFEST"; do
    [ -e "$f" ] || { echo "repo persona artifact missing: $f" >&2; exit 2; }
done

# ── Resolve the workspace (live) if not given ────────────────────────────────
if [ -z "$WORKSPACE" ]; then
    for c in "/data/.openclaw/workspace/data/coaching-personas" \
             "/data/.openclaw/master-files/coaching-personas" \
             "$HOME/.openclaw/workspace/data/coaching-personas"; do
        if [ -d "$c" ]; then WORKSPACE="$c"; break; fi
    done
fi
[ -n "$WORKSPACE" ] && [ -d "$WORKSPACE" ] || {
    echo "ERROR: workspace coaching-personas dir not found. Pass --workspace DIR." >&2
    exit 2; }
[ -f "$WORKSPACE/persona-categories.json" ] || {
    echo "ERROR: $WORKSPACE has no persona-categories.json — is this the coaching-personas dir?" >&2
    exit 2; }

echo "════════════════════════════════════════════════════════════════════"
echo " publish-personas-to-fleet"
echo "   workspace : $WORKSPACE"
echo "   repo      : $REPO_ROOT"
echo "   mode      : $([ "$NO_ASSET" = 1 ] && echo 'no-asset (hermetic, counts only)' || { [ "$DRY_RUN" = 1 ] && echo 'dry-run (asset math, no upload)' || echo 'FULL (embed + publish asset)'; })"
echo "════════════════════════════════════════════════════════════════════"

# ── SNAPSHOT (for atomic rollback) ───────────────────────────────────────────
SNAP="$(mktemp -d -t persona-fleet-snap.XXXXXX)"
SUCCESS=0
restore_snapshot() {
    rm -rf "$REPO_PERSONAS"
    cp -R "$SNAP/personas" "$REPO_PERSONAS"
    cp -f "$SNAP/persona-categories.json" "$REPO_CAT"
    cp -f "$SNAP/INDEX-MANIFEST.json" "$MANIFEST"
}
cleanup() {
    local rc=$?
    if [ "$SUCCESS" != "1" ] && [ -d "$SNAP/personas" ]; then
        echo "→ ROLLBACK: restoring repo persona artifacts to their pre-run state (no half-committed state)" >&2
        restore_snapshot
    fi
    rm -rf "$SNAP"
    exit $rc
}
trap cleanup EXIT
cp -R "$REPO_PERSONAS" "$SNAP/personas"
cp -f "$REPO_CAT" "$SNAP/persona-categories.json"
cp -f "$MANIFEST" "$SNAP/INDEX-MANIFEST.json"

die() { echo "ERROR: $*" >&2; exit "${2:-1}"; }

# ── 1) Enumerate the workspace persona set ───────────────────────────────────
WS_SLUGS=(); while IFS= read -r _l; do [ -n "$_l" ] && WS_SLUGS+=("$_l"); done \
    < <(python3 "$PF" workspace-slugs --workspace "$WORKSPACE")
N_WS="${#WS_SLUGS[@]}"
[ "$N_WS" -gt 0 ] || die "no publishable personas in the workspace (need both a blueprint AND a categories entry)" 2
echo "→ [1/5] workspace persona set: $N_WS personas"

# Which workspace personas are NOT yet in the repo library?
MISSING=(); while IFS= read -r _l; do [ -n "$_l" ] && MISSING+=("$_l"); done \
    < <(python3 "$PF" diff-slugs --workspace "$WORKSPACE" --repo-root "$REPO_ROOT")
echo "     personas missing from the repo library: ${#MISSING[@]}"

# ── 1.5) INDEX-VERIFY (A-U8) — every publishable persona is indexed OR ──────
#         honestly deferred. Checks THIS box's live gemini-index.sqlite (the
#         same DB Skill-22's Phase 5 writes at synthesis time and
#         embedding_engine.search() reads) against $WORKSPACE/personas/<slug>/
#         embedding-receipt.json deferred markers. This is orthogonal to
#         --no-asset / --dry-run (both operate on a SEPARATE staged/hermetic
#         DB for the fleet release asset) — it runs in every mode, catching a
#         persona that is semantically INVISIBLE on this box before it ships.
LIVE_GEMINI_INDEX="$WORKSPACE/gemini-index.sqlite"
echo "→ [1.5/5] index-verify: every persona indexed or honestly deferred (db=$LIVE_GEMINI_INDEX)"
if ! python3 "$PF" index-verify --workspace "$WORKSPACE" --db "$LIVE_GEMINI_INDEX" \
        --slugs "$(IFS=,; echo "${WS_SLUGS[*]}")"; then
    die "index-verify FAILED — a workspace persona is neither indexed nor honestly deferred; see above" 7
fi

# ── 2) Sync repo blueprint dirs (SANITIZED) ──────────────────────────────────
echo "→ [2/5] syncing repo blueprint dirs (sanitized of operator-local paths)"
BP_CHANGED=0
for slug in "${WS_SLUGS[@]}"; do
    src="$WORKSPACE/personas/$slug/persona-blueprint.md"
    [ -f "$src" ] || { echo "     ! $slug has no workspace blueprint — skipping" >&2; continue; }
    dst_dir="$REPO_PERSONAS/$slug"
    dst="$dst_dir/persona-blueprint.md"
    mkdir -p "$dst_dir"
    tmp="$(mktemp)"
    if ! python3 "$PF" sanitize --in "$src" --out "$tmp"; then
        rm -f "$tmp"; die "sanitize failed for $slug" 2
    fi
    if [ ! -f "$dst" ] || ! cmp -s "$tmp" "$dst"; then
        mv -f "$tmp" "$dst"; BP_CHANGED=$((BP_CHANGED+1))
    else
        rm -f "$tmp"
    fi
done
echo "     $BP_CHANGED blueprint(s) written/updated"

# ── 3) Sync repo persona-categories.json (controlled-vocab validated) ────────
echo "→ [3/5] syncing repo persona-categories.json (controlled-vocab tags)"
CSV="$(IFS=,; echo "${WS_SLUGS[*]}")"
if ! python3 "$PF" sync-categories \
        --workspace-cat "$WORKSPACE/persona-categories.json" \
        --repo-cat "$REPO_CAT" --slugs "$CSV"; then
    die "categories sync failed (controlled-vocabulary violation) — rolling back" 4
fi

# ── 4) Manifest + release asset ──────────────────────────────────────────────
DIR_N="$(find "$REPO_PERSONAS" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d ' ')"
if [ "$NO_ASSET" = "1" ]; then
    echo "→ [4/5] --no-asset: syncing manifest COUNT fields to N=$DIR_N (asset NOT rebuilt)"
    python3 "$PF" set-manifest-counts --manifest "$MANIFEST" --count "$DIR_N" \
        --repo-cat "$REPO_CAT" --no-asset \
        || die "manifest count sync failed" 6
else
    echo "→ [4/5] rebuilding + publishing the index asset via build-and-publish.sh"
    [ -f "$BUILD_PUBLISH" ] || die "build-and-publish.sh not found: $BUILD_PUBLISH" 2
    BP_ARGS=()
    [ "$DRY_RUN" = "1" ] && BP_ARGS+=(--dry-run)
    # Embed ONLY the delta personas via --persona-id (HASH-SKIP handles the rest).
    # When nothing is missing we pass no --persona-id, so build-and-publish.sh
    # runs its default reindex-all, which still HASH-SKIPs every persona (no furnace).
    if [ "${#MISSING[@]}" -gt 0 ]; then
        for slug in "${MISSING[@]}"; do BP_ARGS+=(--persona-id "$slug"); done
    fi
    # ${BP_ARGS[@]+...} keeps this safe under `set -u` with an empty array (bash 3.2).
    if ! bash "$BUILD_PUBLISH" ${BP_ARGS[@]+"${BP_ARGS[@]}"}; then
        die "build-and-publish.sh failed — rolling back all repo persona edits" 6
    fi
fi

# ── 5) FINAL ATOMIC GATE — the triad must agree at N ─────────────────────────
echo "→ [5/5] verifying the count triad agrees at N"
if ! python3 "$PF" triad --repo-root "$REPO_ROOT"; then
    die "triad did NOT agree after publish — rolling back" 5
fi
FINAL_N="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["persona_count"])' "$MANIFEST")"

# Full mode: prove the fleet is pointed at an asset whose sha256 matches the
# manifest (the "only point at it after a sha256 match" gate). Skipped for
# --no-asset (asset intentionally not rebuilt) and --dry-run (nothing uploaded).
if [ "$NO_ASSET" != "1" ] && [ "$DRY_RUN" != "1" ]; then
    echo "     verifying published asset sha256 == manifest.sha256 (only point the fleet at a matching asset)"
    A_URL="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["asset_url"])' "$MANIFEST")"
    A_SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST")"
    A_TAG="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["release_tag"])' "$MANIFEST")"
    TGZ="$(mktemp -t published-asset.XXXXXX.gz)"
    DL_OK=0
    # Prefer curl (public release URL); fall back to gh release download so a
    # box with gh auth but no curl still verifies.
    if command -v curl >/dev/null 2>&1; then
        curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$A_URL" -o "$TGZ" 2>/dev/null && DL_OK=1
    fi
    if [ "$DL_OK" != "1" ] && command -v gh >/dev/null 2>&1; then
        gh release download "$A_TAG" -R trevorotts1/openclaw-onboarding \
            --pattern 'gemini-index.sqlite.gz' --output "$TGZ" --clobber >/dev/null 2>&1 && DL_OK=1
    fi
    if [ "$DL_OK" = "1" ]; then
        if command -v sha256sum >/dev/null 2>&1; then GOT="$(sha256sum "$TGZ" | awk '{print $1}')"; else GOT="$(shasum -a 256 "$TGZ" | awk '{print $1}')"; fi
        rm -f "$TGZ"
        # A genuine mismatch means the release serves different bytes than the
        # manifest claims — refuse (rollback) so the fleet is never pointed at it.
        [ "$GOT" = "$A_SHA" ] || die "published asset sha256 mismatch ($GOT != $A_SHA) — refusing to point the fleet at a mismatched asset" 6
        echo "     ✓ published asset sha256 verified"
    else
        # Could not FETCH the asset (transient network / no curl+gh). This is NOT
        # a mismatch — build-and-publish.sh wrote the manifest sha256 from the exact
        # gz it uploaded, so the pointer is consistent by construction. We do NOT
        # roll back here (the asset is already published; a rollback would orphan
        # it). Warn loudly + require a manual sha256 confirmation before rolling.
        rm -f "$TGZ"
        echo "     ⚠️  could not DOWNLOAD the published asset to re-verify sha256 (network/tooling)." >&2
        echo "     ⚠️  manifest sha256 = $A_SHA (tag $A_TAG). Confirm the release asset matches before rolling the fleet." >&2
    fi
fi

SUCCESS=1
# Clear the pipeline pending-publish marker now that the fleet is caught up.
[ -f "$STATUS_HELPER" ] && bash "$STATUS_HELPER" clear "$WORKSPACE" >/dev/null 2>&1 || true

echo "════════════════════════════════════════════════════════════════════"
echo " ✓ DONE — all four artifacts consistent at N=$FINAL_N personas."
if [ "$NO_ASSET" = "1" ]; then
    echo "   NOTE: --no-asset synced the repo + manifest COUNTS only. Run a FULL"
    echo "   publish (or shared-utils/prebuilt-index/build-and-publish.sh) to"
    echo "   rebuild + publish the embedding asset before rolling the fleet."
fi
echo "   Review the diff and COMMIT:"
echo "     git add 22-book-to-persona-coaching-leadership-system/personas \\"
echo "             22-book-to-persona-coaching-leadership-system/persona-categories.json \\"
echo "             shared-utils/prebuilt-index/INDEX-MANIFEST.json"
echo "════════════════════════════════════════════════════════════════════"

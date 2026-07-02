#!/usr/bin/env bash
# =============================================================================
# 50-email-engine/index/provision-email-index.sh
# -----------------------------------------------------------------------------
# CLIENT-BOX provisioner for the SEPARATE email-superlibrary Gemini index.
# Source this file (do NOT execute it) then call:
#
#   provision_email_index  <EMAIL_INDEX_MANIFEST_PATH>  <EMAIL_INDEX_DB_DIR>
#
# Cloned in spirit from shared-utils/provision-persona-index.sh's
# provision_persona_index(). It DOWNLOADS the sha256-verified prebuilt vectors
# and NEVER re-embeds per box (furnace-safe). It is idempotent: a box that
# already holds the canonical asset (chunk_count + release sentinel match the
# manifest) SKIPS the download. sha256 is a HARD gate — a corrupt asset is never
# installed; the box keyword-degrades to the lexical catalog (email_matcher.py).
#
# CLIENT KEYS ONLY: this provisioner needs NO key at all (it only downloads a
# published asset). Embedding (which would need a key) happens ONCE on the
# operator box via build-and-publish.sh — never here.
#
# PROVISION_DRY_RUN=1 prints the gate decision and returns BEFORE any network I/O
# (used to prove the gate / idempotency).
# =============================================================================

provision_email_index() {
    local MANIFEST_PATH="$1"
    local DB_DIR="$2"
    local DB="$DB_DIR/email-index.sqlite"
    local SENTINEL="$DB_DIR/.email-index-version"

    if [ ! -f "$MANIFEST_PATH" ]; then
        echo "  ⚠️  Email-index provisioning SKIPPED: manifest not found ($MANIFEST_PATH) — lexical catalog still serves (additive)"
        return 0
    fi
    command -v python3 >/dev/null 2>&1 || {
        echo "  ⚠️  Email-index provisioning SKIPPED: python3 absent — lexical catalog still serves"
        return 0
    }

    local ASSET_URL SHA CHUNKS TAG REBUILD
    ASSET_URL="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("asset_url",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    SHA="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("sha256",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    CHUNKS="$(python3 -c 'import json,sys;print(int(json.load(open(sys.argv[1])).get("chunk_count",0) or 0))' "$MANIFEST_PATH" 2>/dev/null || echo 0)"
    TAG="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("release_tag",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    REBUILD="$(python3 -c 'import json,sys;print(str(json.load(open(sys.argv[1])).get("asset_rebuild_required",False)).lower())' "$MANIFEST_PATH" 2>/dev/null || echo true)"

    mkdir -p "$DB_DIR"

    # The asset is not published yet (first-build pending): the manifest carries
    # no sha256 and asset_rebuild_required=true. NEVER re-embed on a client box —
    # keyword-degrade to the lexical catalog until the operator publishes.
    if [ -z "$SHA" ] || [ "$REBUILD" = "true" ]; then
        echo "  → Email index asset not yet published (release=$TAG, chunk_count=$CHUNKS). Client stays on the LEXICAL catalog (email_matcher.py). NO per-box re-embed."
        return 0
    fi

    # ── Idempotency gate ─────────────────────────────────────────────────────
    local INSTALLED_CHUNKS="n/a" INSTALLED_TAG="" NEED=1 REASON=""
    if [ ! -f "$DB" ]; then
        REASON="index-absent"
    else
        INSTALLED_CHUNKS="$(python3 -c 'import sqlite3,sys
try:
    c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]); c.close()
except Exception:
    print(0)' "$DB" 2>/dev/null || echo 0)"
        [ -f "$SENTINEL" ] && INSTALLED_TAG="$(tr -d '[:space:]' < "$SENTINEL" 2>/dev/null || true)"
        if [ "$CHUNKS" -gt 0 ] 2>/dev/null && [ "$INSTALLED_CHUNKS" = "$CHUNKS" ] && [ "$INSTALLED_TAG" = "$TAG" ]; then
            NEED=0
        else
            REASON="chunk:${INSTALLED_CHUNKS}!=${CHUNKS} sentinel:${INSTALLED_TAG:-<none>}!=${TAG}"
        fi
    fi

    if [ "$NEED" -eq 0 ]; then
        echo "  ✓ Email index already canonical (release=$TAG, $INSTALLED_CHUNKS chunks) — skipping download"
        return 0
    fi

    echo "  → Email index NEEDS (re)provision to $TAG — reasons: $REASON"
    if [ "${PROVISION_DRY_RUN:-0}" = "1" ]; then
        echo "  [dry-run] would download canonical email index (release=$TAG, chunk_count=$CHUNKS) from $ASSET_URL — NO re-embed"
        return 0
    fi

    # ── Download + sha256 HARD gate + install (no re-embed) ──────────────────
    local GZ="/tmp/email-index.sqlite.$$.gz"
    if curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$ASSET_URL" -o "$GZ" 2>/dev/null; then
        local ACTUAL
        if command -v sha256sum >/dev/null 2>&1; then ACTUAL="$(sha256sum "$GZ" | awk '{print $1}')"; else ACTUAL="$(shasum -a 256 "$GZ" | awk '{print $1}')"; fi
        if [ "$ACTUAL" = "$SHA" ]; then
            if gunzip -c "$GZ" > "$DB.tmp" 2>/dev/null; then
                mv -f "$DB.tmp" "$DB"
                printf '%s\n' "$TAG" > "$SENTINEL"
                echo "  ✓ Email index installed at $DB (sha256 verified, release=$TAG, $CHUNKS chunks) — NO re-embed"
            else
                rm -f "$DB.tmp"
                echo "  warn: email index decompress failed — keyword-degrades to lexical catalog until re-run"
            fi
        else
            echo "  warn: email index sha256 MISMATCH (expected $SHA, got $ACTUAL) — NOT installing corrupt index"
        fi
        rm -f "$GZ"
    else
        echo "  warn: email index download failed — keyword-degrades to lexical catalog (re-run: openclaw update)"
    fi
}

#!/usr/bin/env bash
# shared-utils/provision-persona-index.sh
# ─────────────────────────────────────────────────────────────────────────────
# Shared helper: idempotent persona-index provisioning + GHL funnel catalog
# wiring.  Source this file (do NOT execute it directly) then call:
#
#   provision_persona_index  <MANIFEST_PATH>  <COACHING_DB_DIR>
#   wire_ghl_funnel_catalog  <SKILLS_DIR>     <OC_SECRETS_ENV>  <OC_JSON>
#
# Callers: install.sh Step 6b, update-skills.sh Step U6b.
# ─────────────────────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# provision_persona_index <manifest_path> <coaching_db_dir>
#
# Downloads the prebuilt gemini-index.sqlite.gz listed in the manifest ONLY
# when the installed DB is absent or stale:
#
#   (a) DB file missing
#   (b) DB present but embeddings table is MISSING the section_number or mode
#       column (i.e. the installed asset is pre-section-tag)
#   (c) DB present, columns ok, but .prebuilt-index-version sentinel !=
#       manifest release_tag (newer release available)
#
# On any other condition the function short-circuits (no download, no
# re-embed) — furnace kill + live-operator-index guard.
#
# sha256 is a HARD gate: a corrupt asset is NEVER installed; the box
# keyword-degrades and warns instead.
# ---------------------------------------------------------------------------
provision_persona_index() {
    local MANIFEST_PATH="$1"
    local COACHING_DB_DIR="$2"
    local COACHING_DB="$COACHING_DB_DIR/gemini-index.sqlite"
    local VERSION_SENTINEL="$COACHING_DB_DIR/.prebuilt-index-version"

    if [ ! -f "$MANIFEST_PATH" ]; then
        echo "  note: Persona-index manifest not found ($MANIFEST_PATH) — skipping prebuilt index provisioning (additive)"
        return 0
    fi

    # Read manifest fields
    local _PIDX_ASSET_URL _PIDX_SHA _PIDX_CHUNKS _PIDX_TAG _PIDX_COLS
    _PIDX_ASSET_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_url"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_CHUNKS="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("chunk_count",0) or 0))' "$MANIFEST_PATH" 2>/dev/null || echo 0)"
    _PIDX_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("release_tag",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_COLS="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(",".join(m.get("schema",{}).get("columns_required",[])))' "$MANIFEST_PATH" 2>/dev/null || echo "section_number,mode")"

    mkdir -p "$COACHING_DB_DIR"

    # ── Idempotency gate ─────────────────────────────────────────────────────
    local _PIDX_HAVE=0
    if [ -f "$COACHING_DB" ]; then
        # (b) Check for required columns
        local _COL_OK=1
        for _COL in $(echo "$_PIDX_COLS" | tr ',' ' '); do
            local _HAS_COL
            _HAS_COL="$(python3 -c "
import sqlite3, sys
try:
    c = sqlite3.connect(sys.argv[1])
    cols = [r[1] for r in c.execute('PRAGMA table_info(embeddings)').fetchall()]
    c.close()
    print('yes' if sys.argv[2] in cols else 'no')
except Exception:
    print('no')
" "$COACHING_DB" "$_COL" 2>/dev/null || echo no)"
            if [ "$_HAS_COL" != "yes" ]; then
                _COL_OK=0
                echo "  warn: Installed persona index missing column '$_COL' (pre-section-tag asset) — refreshing"
                break
            fi
        done

        if [ "$_COL_OK" -eq 1 ]; then
            # (c) Check version sentinel
            local _INSTALLED_TAG=""
            [ -f "$VERSION_SENTINEL" ] && _INSTALLED_TAG="$(cat "$VERSION_SENTINEL" 2>/dev/null | tr -d '[:space:]')"
            if [ -n "$_PIDX_TAG" ] && [ "$_INSTALLED_TAG" = "$_PIDX_TAG" ]; then
                _PIDX_HAVE=1
                local _PIDX_EXIST_CHUNKS
                _PIDX_EXIST_CHUNKS="$(python3 -c 'import sqlite3,sys
try:
    c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]); c.close()
except Exception:
    print(0)' "$COACHING_DB" 2>/dev/null || echo 0)"
                echo "  ✓ Persona index already current (release=$_INSTALLED_TAG, $_PIDX_EXIST_CHUNKS chunks, section_number+mode columns present) — skipping download"
            else
                echo "  note: Persona index version sentinel '$_INSTALLED_TAG' != manifest '$_PIDX_TAG' — refreshing to $(_PIDX_TAG)"
            fi
        fi
    fi

    # ── Download + verify + install ──────────────────────────────────────────
    if [ "$_PIDX_HAVE" -eq 0 ]; then
        if [ -z "$_PIDX_ASSET_URL" ] || [ -z "$_PIDX_SHA" ]; then
            echo "  warn: Persona index manifest missing asset_url/sha256 — skipping prebuilt provisioning (additive)"
            return 0
        fi

        local _PIDX_PERSONA_COUNT
        _PIDX_PERSONA_COUNT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("persona_count","?"))' "$MANIFEST_PATH" 2>/dev/null || echo "?")"
        echo "  Downloading prebuilt persona index ($_PIDX_PERSONA_COUNT personas) from $_PIDX_ASSET_URL"

        local _PIDX_GZ="/tmp/gemini-index.sqlite.$$.gz"
        if curl -L --retry 3 --retry-delay 5 --fail -H "Accept: application/octet-stream" "$_PIDX_ASSET_URL" -o "$_PIDX_GZ" 2>/dev/null; then
            # SHA256 HARD GATE — verify BEFORE decompress
            local _PIDX_ACTUAL
            if command -v sha256sum >/dev/null 2>&1; then
                _PIDX_ACTUAL="$(sha256sum "$_PIDX_GZ" | awk '{print $1}')"
            else
                _PIDX_ACTUAL="$(shasum -a 256 "$_PIDX_GZ" | awk '{print $1}')"
            fi
            if [ "$_PIDX_ACTUAL" = "$_PIDX_SHA" ]; then
                if gunzip -c "$_PIDX_GZ" > "$COACHING_DB.tmp" 2>/dev/null; then
                    mv -f "$COACHING_DB.tmp" "$COACHING_DB"
                    # Stamp version sentinel
                    printf '%s\n' "$_PIDX_TAG" > "$VERSION_SENTINEL"
                    echo "  ✓ Persona index installed at $COACHING_DB (sha256 verified, $_PIDX_PERSONA_COUNT personas, release=$_PIDX_TAG)"
                else
                    rm -f "$COACHING_DB.tmp"
                    echo "  warn: Persona index decompress failed — gemini-search keyword-degrades until re-run"
                fi
            else
                echo "  warn: Persona index sha256 MISMATCH (expected $_PIDX_SHA, got $_PIDX_ACTUAL) — NOT installing corrupt index"
            fi
            rm -f "$_PIDX_GZ"
        else
            echo "  warn: Persona index download failed — gemini-search keyword-degrades until the index is provisioned (re-run install or run: openclaw update)"
        fi
    fi
}

# ---------------------------------------------------------------------------
# wire_ghl_funnel_catalog <skills_dir> <oc_secrets_env> <oc_json>
#
# Writes GHL_FUNNEL_CATALOG (path to the funnel-templates/ directory) and
# GHL_FUNNEL_INDEX (path to the agent-readable catalog README.md) to BOTH
# secrets/.env (chmod 600) and openclaw.json env.vars block.
#
# These are box-local paths (not secrets) so they are safe to write
# unconditionally; an operator can override them via env before calling.
# Only writes if the 06-ghl-install-pages/funnel-templates/ directory exists
# under skills_dir.
# ---------------------------------------------------------------------------
wire_ghl_funnel_catalog() {
    local _SKILLS_DIR="$1"
    local _OC_SECRETS_ENV="$2"
    local _OC_JSON="$3"

    local _CATALOG_DIR="$_SKILLS_DIR/06-ghl-install-pages/funnel-templates"
    if [ ! -d "$_CATALOG_DIR" ]; then
        echo "  note: GHL funnel-templates not found at $_CATALOG_DIR — skipping catalog wiring (additive)"
        return 0
    fi

    local _CATALOG_INDEX="$_CATALOG_DIR/README.md"
    local _GHL_FUNNEL_CATALOG="${GHL_FUNNEL_CATALOG:-$_CATALOG_DIR}"
    local _GHL_FUNNEL_INDEX="${GHL_FUNNEL_INDEX:-$_CATALOG_INDEX}"

    # Write to secrets/.env
    if [ -n "$_OC_SECRETS_ENV" ]; then
        mkdir -p "$(dirname "$_OC_SECRETS_ENV")" 2>/dev/null || true
        [ ! -f "$_OC_SECRETS_ENV" ] && { touch "$_OC_SECRETS_ENV"; chmod 600 "$_OC_SECRETS_ENV" 2>/dev/null || true; }
        # Replace or append GHL_FUNNEL_CATALOG
        grep -v "^GHL_FUNNEL_CATALOG=" "$_OC_SECRETS_ENV" > "$_OC_SECRETS_ENV.tmp" 2>/dev/null || true
        mv "$_OC_SECRETS_ENV.tmp" "$_OC_SECRETS_ENV" 2>/dev/null || true
        printf 'GHL_FUNNEL_CATALOG=%s\n' "$_GHL_FUNNEL_CATALOG" >> "$_OC_SECRETS_ENV"
        # Replace or append GHL_FUNNEL_INDEX
        grep -v "^GHL_FUNNEL_INDEX=" "$_OC_SECRETS_ENV" > "$_OC_SECRETS_ENV.tmp" 2>/dev/null || true
        mv "$_OC_SECRETS_ENV.tmp" "$_OC_SECRETS_ENV" 2>/dev/null || true
        printf 'GHL_FUNNEL_INDEX=%s\n' "$_GHL_FUNNEL_INDEX" >> "$_OC_SECRETS_ENV"
        chmod 600 "$_OC_SECRETS_ENV" 2>/dev/null || true
    fi

    # Write to openclaw.json env.vars
    if [ -f "$_OC_JSON" ] && command -v python3 >/dev/null 2>&1; then
        GHL_FUNNEL_CATALOG_VAL="$_GHL_FUNNEL_CATALOG" \
        GHL_FUNNEL_INDEX_VAL="$_GHL_FUNNEL_INDEX" \
        OC_JSON_PATH="$_OC_JSON" \
        python3 - <<'PYEOF' 2>/dev/null || true
import json, os
p = os.environ['OC_JSON_PATH']
catalog = os.environ['GHL_FUNNEL_CATALOG_VAL']
index = os.environ['GHL_FUNNEL_INDEX_VAL']
try:
    d = json.load(open(p))
except Exception:
    d = {}
d.setdefault('env', {}).setdefault('vars', {})['GHL_FUNNEL_CATALOG'] = catalog
d.setdefault('env', {}).setdefault('vars', {})['GHL_FUNNEL_INDEX'] = index
json.dump(d, open(p, 'w'), indent=2)
PYEOF
    fi

    echo "  ✓ GHL funnel catalog wired: GHL_FUNNEL_CATALOG=$_GHL_FUNNEL_CATALOG"
}

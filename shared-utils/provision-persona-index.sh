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
# _pidx_md5 <file> — portable md5 (Linux md5sum / macOS md5 -q).
# ---------------------------------------------------------------------------
_pidx_md5() {
    if command -v md5sum >/dev/null 2>&1; then
        md5sum "$1" 2>/dev/null | awk '{print $1}'
    else
        md5 -q "$1" 2>/dev/null
    fi
}

# ---------------------------------------------------------------------------
# provision_persona_index <manifest_path> <coaching_db_dir>
#
# CANONICAL IDEMPOTENCY GATE (v14.27.2).
#
# (Re)downloads the prebuilt gemini-index.sqlite.gz listed in the manifest when
# the installed DB is NOT the canonical v2.1.0 asset.  NEED_PROVISION is true
# when ANY of the following hold (matches the prove-floor canonical target):
#
#   (a) index file absent
#   (b) embeddings table is MISSING a required column (section_number / mode)
#   (c) chunk_count != manifest chunk_count (4413) — i.e. a NON-canonical
#       partial index (the 6260 / 7615 / 9456-row locally-re-embedded indexes
#       that the OLD "has section_number column ⇒ provisioned" gate wrongly
#       treated as done and SKIPPED, so those boxes never converged)
#   (d) persona-dir count under <coaching_db_dir>/personas != manifest
#       persona_count (54)
#   (e) the .prebuilt-index-version sentinel != manifest release_tag
#
# SKIP (no download, no re-embed) ONLY when the index genuinely IS the
# canonical asset.  CONTENT-CANONICAL = index present AND columns ok AND
# chunk_count == manifest AND persona-dir count == manifest.
#
# LIVE-OPERATOR-INDEX / FURNACE GUARD: a box whose index is content-canonical
# but whose sentinel is absent/empty/stale (e.g. the live operator index, which
# was BUILT locally rather than downloaded and so was never stamped) is
# self-healed — the sentinel is stamped to the manifest tag and the 90MB
# download is SKIPPED.  Re-downloading only happens when the CONTENT is
# non-canonical (wrong chunk_count or missing columns), so the operator's
# canonical 4413-row index is never clobbered or re-fetched on every update.
#
# sha256 is a HARD gate: a corrupt asset is NEVER installed; the box
# keyword-degrades and warns instead.
#
# PROVISION_DRY_RUN=1 prints the gate decision and returns BEFORE any network
# I/O (used by tests/unit/provision-idempotency.test.sh to prove the gate).
# ---------------------------------------------------------------------------
provision_persona_index() {
    local MANIFEST_PATH="$1"
    local COACHING_DB_DIR="$2"
    local COACHING_DB="$COACHING_DB_DIR/gemini-index.sqlite"
    local VERSION_SENTINEL="$COACHING_DB_DIR/.prebuilt-index-version"
    local PERSONAS_DIR="$COACHING_DB_DIR/personas"

    if [ ! -f "$MANIFEST_PATH" ]; then
        echo "  note: Persona-index manifest not found ($MANIFEST_PATH) — skipping prebuilt index provisioning (additive)"
        return 0
    fi

    # Read manifest fields
    local _PIDX_ASSET_URL _PIDX_SHA _PIDX_CHUNKS _PIDX_TAG _PIDX_COLS _PIDX_PERSONAS
    _PIDX_ASSET_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_url"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_CHUNKS="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("chunk_count",0) or 0))' "$MANIFEST_PATH" 2>/dev/null || echo 0)"
    _PIDX_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("release_tag",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_COLS="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(",".join(m.get("schema",{}).get("columns_required",[])))' "$MANIFEST_PATH" 2>/dev/null || echo "section_number,mode")"
    _PIDX_PERSONAS="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("persona_count",54) or 54))' "$MANIFEST_PATH" 2>/dev/null || echo 54)"

    mkdir -p "$COACHING_DB_DIR"

    # ── Canonical idempotency gate ───────────────────────────────────────────
    local _COLS_OK=1 _CHUNK_OK=0 _DIR_OK=0 _SENT_OK=0
    local _INSTALLED_CHUNKS="n/a" _INSTALLED_TAG="" _PERSONA_DIR_COUNT=0
    local _GATE_REASONS=""

    if [ ! -f "$COACHING_DB" ]; then
        _GATE_REASONS="index-absent"
    else
        # (b) required columns
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
                _COLS_OK=0
                _GATE_REASONS="$_GATE_REASONS missing-column:$_COL"
            fi
        done

        # (c) chunk_count vs manifest (HARD canonical signal)
        _INSTALLED_CHUNKS="$(python3 -c 'import sqlite3,sys
try:
    c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]); c.close()
except Exception:
    print(0)' "$COACHING_DB" 2>/dev/null || echo 0)"
        if [ "$_PIDX_CHUNKS" -gt 0 ] 2>/dev/null && [ "$_INSTALLED_CHUNKS" = "$_PIDX_CHUNKS" ]; then
            _CHUNK_OK=1
        else
            _GATE_REASONS="$_GATE_REASONS chunk-count:${_INSTALLED_CHUNKS}!=${_PIDX_CHUNKS}"
        fi

        # (e) version sentinel
        [ -f "$VERSION_SENTINEL" ] && _INSTALLED_TAG="$(cat "$VERSION_SENTINEL" 2>/dev/null | tr -d '[:space:]')"
        if [ -n "$_PIDX_TAG" ] && [ "$_INSTALLED_TAG" = "$_PIDX_TAG" ]; then
            _SENT_OK=1
        else
            _GATE_REASONS="$_GATE_REASONS sentinel:${_INSTALLED_TAG:-<none>}!=${_PIDX_TAG}"
        fi
    fi

    # (d) persona-dir count (checked even when the index file is absent)
    if [ -d "$PERSONAS_DIR" ]; then
        _PERSONA_DIR_COUNT="$(find "$PERSONAS_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    fi
    if [ "$_PIDX_PERSONAS" -gt 0 ] 2>/dev/null && [ "$_PERSONA_DIR_COUNT" = "$_PIDX_PERSONAS" ]; then
        _DIR_OK=1
    else
        _GATE_REASONS="$_GATE_REASONS persona-dir-count:${_PERSONA_DIR_COUNT}!=${_PIDX_PERSONAS}"
    fi

    # CONTENT-CANONICAL = present + columns + chunk_count + persona dirs all match.
    local _CONTENT_CANON=0
    if [ -f "$COACHING_DB" ] && [ "$_COLS_OK" -eq 1 ] && [ "$_CHUNK_OK" -eq 1 ] && [ "$_DIR_OK" -eq 1 ]; then
        _CONTENT_CANON=1
    fi

    local _PIDX_HAVE=0
    if [ "$_CONTENT_CANON" -eq 1 ]; then
        _PIDX_HAVE=1
        if [ "$_SENT_OK" -ne 1 ]; then
            # Self-heal: content proves canonicity; stamp the sentinel rather than
            # re-download (live-operator-index + furnace guard).
            printf '%s\n' "$_PIDX_TAG" > "$VERSION_SENTINEL" 2>/dev/null || true
            echo "  ✓ Persona index content-canonical ($_INSTALLED_CHUNKS chunks == manifest $_PIDX_CHUNKS, section_number+mode present, $_PERSONA_DIR_COUNT/$_PIDX_PERSONAS persona dirs) but sentinel was '${_INSTALLED_TAG:-<none>}' — stamped sentinel=$_PIDX_TAG (self-heal) and skipping download"
        else
            echo "  ✓ Persona index already canonical (release=$_PIDX_TAG, $_INSTALLED_CHUNKS chunks == manifest $_PIDX_CHUNKS, section_number+mode present, $_PERSONA_DIR_COUNT/$_PIDX_PERSONAS persona dirs) — skipping download"
        fi
        return 0
    fi

    echo "  → Persona index NEEDS (re)provision to canonical $_PIDX_TAG — reasons:$_GATE_REASONS"

    # Dry-run: prove the gate decision without any network I/O.
    if [ "${PROVISION_DRY_RUN:-0}" = "1" ]; then
        echo "  [dry-run] would download canonical index (release=$_PIDX_TAG, chunk_count=$_PIDX_CHUNKS, personas=$_PIDX_PERSONAS) from $_PIDX_ASSET_URL"
        return 0
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
# reconcile_persona_assets <skill22_dir> <coaching_db_dir> <workspace_dir>
#
# (v14.27.2) Reconciles the canonical persona-categories.json + the 54
# persona-blueprint.md from the shipped Skill-22 source into the WORKSPACE
# locations the running agent actually reads (the resolver in
# resolve_persona_categories_path.py + orchestrator.py).  Boxes that drifted to
# 40 personas / a non-canonical categories md5 (because the resolver only
# SEEDED an absent canonical path and never RECONCILED a stale one) now
# converge to the canonical 54 personas (categories md5
# c544561074e6e1d65aed1840b6f03b8c).
#
# Idempotent + additive: only writes when the target is missing, empty, or
# content-differs (md5).  Never deletes box-local persona dirs.  Must run
# BEFORE provision_persona_index so the persona-dir count is 54 by gate time
# (keeps the index gate furnace-safe).
#
# Writes as the invoking (box) user into the workspace — never root, never
# the shipped Skill-22 seed (which stays the immutable source).
# ---------------------------------------------------------------------------
reconcile_persona_assets() {
    local _SK22="$1"
    local _COACHING_DB_DIR="$2"
    local _WS="$3"

    local _SRC_CATS="$_SK22/persona-categories.json"
    local _SRC_PERSONAS="$_SK22/personas"

    if [ ! -f "$_SRC_CATS" ] || [ ! -d "$_SRC_PERSONAS" ]; then
        echo "  note: Skill-22 persona source not found at $_SK22 — skipping persona reconcile (additive)"
        return 0
    fi

    local _SRC_MD5
    _SRC_MD5="$(_pidx_md5 "$_SRC_CATS")"

    # 1) persona-categories.json → canonical data/ path (+ stale legacy path).
    #    The resolver prefers <ws>/data/coaching-personas/ over <ws>/coaching-personas/,
    #    so the data/ write is authoritative; the legacy write only overwrites an
    #    already-present stale file so no fallback can shadow the canonical one.
    local _CANON_CAT="$_COACHING_DB_DIR/persona-categories.json"
    local _LEGACY_CAT="$_WS/coaching-personas/persona-categories.json"

    local _canon_md5=""
    [ -f "$_CANON_CAT" ] && _canon_md5="$(_pidx_md5 "$_CANON_CAT")"
    if [ "$_canon_md5" != "$_SRC_MD5" ]; then
        mkdir -p "$(dirname "$_CANON_CAT")"
        cp -f "$_SRC_CATS" "$_CANON_CAT"
        echo "  ✓ persona-categories.json reconciled → $_CANON_CAT (md5 $_SRC_MD5)"
    else
        echo "  ✓ persona-categories.json already canonical at $_CANON_CAT (md5 $_SRC_MD5)"
    fi

    if [ -f "$_LEGACY_CAT" ]; then
        local _legacy_md5
        _legacy_md5="$(_pidx_md5 "$_LEGACY_CAT")"
        if [ "$_legacy_md5" != "$_SRC_MD5" ]; then
            cp -f "$_SRC_CATS" "$_LEGACY_CAT"
            echo "  ✓ persona-categories.json (legacy) reconciled → $_LEGACY_CAT (md5 $_SRC_MD5)"
        fi
    fi

    # 2) 54 persona-blueprint.md → <coaching_db_dir>/personas/<slug>/.
    local _TGT_PERSONAS="$_COACHING_DB_DIR/personas"
    mkdir -p "$_TGT_PERSONAS"
    local _copied=0 _ok=0
    local _pd _slug _src_bp _tgt_bp
    for _pd in "$_SRC_PERSONAS"/*/; do
        [ -d "$_pd" ] || continue
        _slug="$(basename "$_pd")"
        _src_bp="${_pd%/}/persona-blueprint.md"
        [ -s "$_src_bp" ] || continue
        _tgt_bp="$_TGT_PERSONAS/$_slug/persona-blueprint.md"
        if [ -s "$_tgt_bp" ] && [ "$(_pidx_md5 "$_tgt_bp")" = "$(_pidx_md5 "$_src_bp")" ]; then
            _ok=$((_ok + 1))
        else
            mkdir -p "$_TGT_PERSONAS/$_slug"
            cp -f "$_src_bp" "$_tgt_bp"
            _copied=$((_copied + 1))
        fi
    done
    local _final
    _final="$(find "$_TGT_PERSONAS" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    echo "  ✓ persona-blueprints reconciled: $_copied copied, $_ok already-canonical, $_final persona dirs on disk (target 54)"
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

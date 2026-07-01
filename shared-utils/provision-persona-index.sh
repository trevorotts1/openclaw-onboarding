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

    # 3) Persona-SET version stamp (FIX 2 / BREAK 2 — silent fleet freeze).
    #    Mirrors the .prebuilt-index-version sentinel, but for the SET (not the
    #    index). Records the installed persona-categories.json md5 + persona_count
    #    + lastUpdated so update-skills.sh can DETERMINISTICALLY detect "the set
    #    grew" and trigger a re-wire. Before this stamp, a box that copied a stale
    #    categories.json drifted with ZERO alarms (the index sentinel guarded the
    #    INDEX, never the SET). Sets _SET_CHANGED=1 (exported) when the SET differs
    #    from the previously-stamped one so the caller re-wires matching + Command
    #    Center + the dept persona reflex. Static file compare only — NO embeddings.
    local _SET_SENTINEL="$_COACHING_DB_DIR/.persona-set-version"
    local _SRC_COUNT _SRC_UPDATED _PREV_SET_MD5=""
    _SRC_COUNT="$(python3 -c 'import json,sys;print(len(json.load(open(sys.argv[1])).get("personas",{})))' "$_SRC_CATS" 2>/dev/null || echo 0)"
    _SRC_UPDATED="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("lastUpdated",""))' "$_SRC_CATS" 2>/dev/null || echo "")"
    [ -f "$_SET_SENTINEL" ] && _PREV_SET_MD5="$(python3 -c 'import json,sys;
try:
    print(json.load(open(sys.argv[1])).get("md5",""))
except Exception:
    print("")' "$_SET_SENTINEL" 2>/dev/null || echo "")"
    if [ "$_PREV_SET_MD5" != "$_SRC_MD5" ]; then
        printf '{"md5":"%s","persona_count":%s,"lastUpdated":"%s","stampedAt":"%s"}\n' \
            "$_SRC_MD5" "$_SRC_COUNT" "$_SRC_UPDATED" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
            > "$_SET_SENTINEL" 2>/dev/null || true
        export _SET_CHANGED=1
        echo "  ✓ persona-SET version CHANGED (was md5=${_PREV_SET_MD5:-<none>} → now $_SRC_MD5; $_SRC_COUNT personas) — stamped $_SET_SENTINEL; _SET_CHANGED=1 (re-wire will run)"
    else
        export _SET_CHANGED=0
        echo "  ✓ persona-SET unchanged (md5=$_SRC_MD5, $_SRC_COUNT personas) — no re-wire needed"
    fi
}

# ---------------------------------------------------------------------------
# reconcile_qmd_persona_index <coaching_db_dir>
#
# FIX 1 / BREAK 1 — the literal "no new personas since March" symptom.
#
# The agent answers persona-inventory questions conversationally by running the
# `qmd` tool (a declared bin of Skill 22) against its `coaching-personas`
# collection. On drifted boxes that collection was created once against the
# SKILL-BUNDLED personas folder (~/.openclaw/skills/22-…/personas), frozen at the
# March snapshot, and NO pipeline step ever re-pointed or re-indexed it — so the
# agent read a frozen store even though the SET + gemini index were current.
#
# This helper makes the PIPELINE own that store: it (re)points the qmd
# `coaching-personas` collection at the CANONICAL personas dir (the same dir
# reconcile_persona_assets just populated with the current 54 blueprints) and
# re-indexes it. If it cannot be re-pointed, it TEARS DOWN the orphan collection
# so the agent can never read a stale store (inventory then answers from
# persona-categories.json per the N16 hard rule).
#
# FURNACE-SAFE: this is a BM25 / full-text re-index only (`qmd collection add` /
# `qmd update`). It does NOT run `qmd embed`, so ZERO vector embeddings are
# computed. Must run AFTER reconcile_persona_assets (so the canonical dir holds
# all current blueprints) and after provision_persona_index.
# ---------------------------------------------------------------------------
# --- F1 helpers (qmd reconcile robustness) ------------------------------------
# _qmd_collection_files_count <collection> — echo the integer "Files:" count qmd
# reports for the collection, or empty. `qmd collection list` never prints the
# on-disk source path (which is why the old grep-the-path canonicity test could
# never match), but it DOES print a per-collection block:
#     <name> (qmd://<name>/)
#       Pattern: ...
#       Files:   N
#       Updated: ...
# Parsing Files: lets us PROVE the store is non-empty before declaring success.
_qmd_collection_files_count() {
    local _c="$1"
    # SIGPIPE-SAFE (v16.2.13). The awk reads the ENTIRE stream (no early `exit`)
    # and prints the FIRST "Files:" count in the target block at END, so
    # `qmd collection list` is never killed by a downstream-closed pipe. The old
    # `exit`-on-first-match closed the read end → `qmd collection list` died with
    # SIGPIPE (rc 141) → under the caller's `set -o pipefail` the pipeline returned
    # 141 → the standalone `_FILES="$(_qmd_collection_files_count ...)"` assignment
    # inherited 141 → `set -e` aborted the WHOLE updater before the Skill-41
    # config-shape wiring + the .onboarding-version stamp ran. The trailing
    # `|| true` additionally absorbs a non-zero from `qmd` itself, so this helper
    # can NEVER return non-zero and can never abort a caller under
    # `set -e`+`pipefail`, at any call site (the count semantics are unchanged:
    # echo the integer count, or nothing).
    qmd collection list 2>/dev/null | awk -v want="$_c" '
        index($0, "qmd://" want "/") { inblk=1; next }
        inblk && !got && tolower($0) ~ /files:/ { n=$0; gsub(/[^0-9]/, "", n); val=n; got=1 }
        inblk && index($0, "qmd://") { inblk=0 }
        END { if (got) print val }
    ' || true
}

# _qmd_rebuild_better_sqlite3 — best-effort ABI repair. A Node major bump
# (e.g. Node 26) leaves qmd's native better-sqlite3 with a NODE_MODULE_VERSION
# mismatch: the binary still EXISTS (command -v qmd succeeds) but every call
# errors — previously indistinguishable from "absent". Rebuild the native addon
# in qmd's own module dir, then (caller) re-probes. macOS BSD readlink lacks -f,
# so we fall back to the bare bin path + the npm-global candidate.
_qmd_rebuild_better_sqlite3() {
    command -v npm >/dev/null 2>&1 || { echo "    (npm not on PATH — cannot rebuild better-sqlite3)"; return 1; }
    local _bin _real r
    _bin="$(command -v qmd 2>/dev/null || true)"
    _real="$(readlink -f "$_bin" 2>/dev/null || true)"
    [ -n "$_real" ] || _real="$_bin"
    local _candidates=()
    if [ -n "$_real" ]; then
        _candidates+=("$(cd "$(dirname "$_real")/.." 2>/dev/null && pwd)")
        _candidates+=("$(cd "$(dirname "$_real")/../.." 2>/dev/null && pwd)")
    fi
    _candidates+=("$(npm root -g 2>/dev/null)/qmd")
    for r in "${_candidates[@]}"; do
        [ -n "$r" ] || continue
        if [ -d "$r/node_modules/better-sqlite3" ]; then
            ( cd "$r" && npm rebuild better-sqlite3 ) >/dev/null 2>&1 && return 0
        fi
    done
    # last resort: rebuild against the global tree
    npm rebuild better-sqlite3 -g >/dev/null 2>&1 && return 0
    return 1
}

reconcile_qmd_persona_index() {
    local _COACHING_DB_DIR="$1"
    local _PERSONAS_DIR="$_COACHING_DB_DIR/personas"
    local _COLL="coaching-personas"
    # Sentinel we write ourselves to record what was indexed (canonical path +
    # persona-md count). Replaces the unprovable "grep the path out of
    # `qmd collection list`" canonicity test (qmd never prints the path).
    local _SENTINEL="$_COACHING_DB_DIR/.qmd-collection-canon"

    if ! command -v qmd >/dev/null 2>&1; then
        echo "  note: qmd not installed — skipping qmd persona-store reconcile (additive; inventory answers from persona-categories.json per N16)"
        return 0
    fi
    if [ ! -d "$_PERSONAS_DIR" ]; then
        echo "  note: canonical personas dir absent ($_PERSONAS_DIR) — skipping qmd reconcile (additive)"
        return 0
    fi

    # --- ABI probe (F1): qmd present but failing every call (better-sqlite3
    # NODE_MODULE_VERSION break after a Node upgrade) was indistinguishable from
    # "absent" and never repaired. Probe with a real read; on failure attempt an
    # npm rebuild, then re-probe. If still broken, emit the DISTINCT
    # qmd-abi-broken status and tear down the collection so a query ERRORS
    # (N16 persona-categories.json fallback) rather than silently reading a
    # frozen/empty store.
    if ! qmd collection list >/dev/null 2>&1; then
        echo "  ⚠ qmd present but failing a basic probe (likely a better-sqlite3 ABI break after a Node upgrade) — attempting npm rebuild better-sqlite3"
        _qmd_rebuild_better_sqlite3
        if qmd collection list >/dev/null 2>&1; then
            echo "  ✓ qmd recovered after npm rebuild better-sqlite3"
        else
            echo "  STATUS: qmd-abi-broken — qmd still failing after rebuild; removing any '$_COLL' collection so inventory queries ERROR → persona-categories.json fallback (N16)"
            qmd collection remove "$_COLL" >/dev/null 2>&1 || true
            rm -f "$_SENTINEL" 2>/dev/null || true
            return 0
        fi
    fi

    # persona-md count under the canonical dir — RECURSIVE: blueprints live one
    # level down as <slug>/persona-blueprint.md, so this matches the recursive
    # mask used for indexing below.
    local _MD_COUNT
    _MD_COUNT="$(find "$_PERSONAS_DIR" -mindepth 1 -name '*.md' -type f 2>/dev/null | wc -l | tr -d ' ')"
    [ -n "$_MD_COUNT" ] || _MD_COUNT=0

    local _LIST _HAS_COLL=0 _POINTS_CANON=0
    _LIST="$(qmd collection list 2>/dev/null || true)"
    if printf '%s' "$_LIST" | grep -q "$_COLL"; then
        _HAS_COLL=1
        # Canonical iff the sentinel path == canonical dir AND the live Files:
        # count ≥ persona-md count (so a present-but-empty/short store is NOT
        # treated as canonical and gets rebuilt instead of trusted).
        if [ -f "$_SENTINEL" ]; then
            local _SENT_PATH _FILES
            _SENT_PATH="$(sed -n '1p' "$_SENTINEL" 2>/dev/null || true)"
            _FILES="$(_qmd_collection_files_count "$_COLL")"
            if [ "$_SENT_PATH" = "$_PERSONAS_DIR" ] && [ -n "$_FILES" ] && [ "$_FILES" -ge "$_MD_COUNT" ] 2>/dev/null; then
                _POINTS_CANON=1
            fi
        fi
    fi

    if [ "$_HAS_COLL" -eq 1 ] && [ "$_POINTS_CANON" -eq 0 ]; then
        echo "  → qmd '$_COLL' collection is stale/mispointed or short (sentinel/Files: disagree with canonical $_PERSONAS_DIR) — removing so it can be re-indexed at the canonical path"
        qmd collection remove "$_COLL" >/dev/null 2>&1 || true
        rm -f "$_SENTINEL" 2>/dev/null || true
        _HAS_COLL=0
    fi

    if [ "$_HAS_COLL" -eq 0 ]; then
        # RECURSIVE mask: every blueprint is <slug>/persona-blueprint.md one level
        # down — '*.md' (non-recursive) matched 0 files yet `qmd collection add`
        # still exits 0, producing a confident-but-EMPTY store.
        if qmd collection add "$_PERSONAS_DIR" --name "$_COLL" --mask '**/*.md' >/dev/null 2>&1; then
            local _FILES
            _FILES="$(_qmd_collection_files_count "$_COLL")"
            if [ "${_FILES:-0}" -gt 0 ] 2>/dev/null; then
                printf '%s\n%s\n' "$_PERSONAS_DIR" "$_MD_COUNT" > "$_SENTINEL" 2>/dev/null || true
                echo "  ✓ qmd '$_COLL' collection (re)indexed at canonical $_PERSONAS_DIR (${_FILES} files indexed, BM25/full-text only — furnace-safe)"
            else
                echo "  ⚠ qmd '$_COLL' add reported success but indexed ZERO files (an empty store is the worst state — it returns 'No results' instead of erroring) — tearing it down so inventory queries ERROR → persona-categories.json fallback (N16)"
                qmd collection remove "$_COLL" >/dev/null 2>&1 || true
                rm -f "$_SENTINEL" 2>/dev/null || true
            fi
        else
            qmd collection remove "$_COLL" >/dev/null 2>&1 || true
            rm -f "$_SENTINEL" 2>/dev/null || true
            echo "  note: could not (re)create qmd '$_COLL' at canonical path — removed any stale collection so the agent cannot read a frozen store (inventory answers from persona-categories.json per N16)"
        fi
    else
        # Already canonical → refresh its index so newly-added persona dirs
        # surface, then RE-VERIFY Files: > 0 (a bad update can empty the store).
        qmd update >/dev/null 2>&1 || true
        local _FILES
        _FILES="$(_qmd_collection_files_count "$_COLL")"
        if [ "${_FILES:-0}" -gt 0 ] 2>/dev/null; then
            printf '%s\n%s\n' "$_PERSONAS_DIR" "$_MD_COUNT" > "$_SENTINEL" 2>/dev/null || true
            echo "  ✓ qmd '$_COLL' collection already canonical at $_PERSONAS_DIR (${_FILES} files) — re-indexed (qmd update; BM25, furnace-safe)"
        else
            echo "  ⚠ qmd '$_COLL' canonical store now indexes ZERO files after update — tearing it down so inventory queries ERROR → persona-categories.json fallback (N16)"
            qmd collection remove "$_COLL" >/dev/null 2>&1 || true
            rm -f "$_SENTINEL" 2>/dev/null || true
        fi
    fi
}

# ---------------------------------------------------------------------------
# rewire_on_persona_set_change <skills_dir> <workspace_dir>
#
# FIX 4 / cascade — re-wire everything the SET touches when it grew.
#
# Called by install.sh / update-skills.sh ONLY when reconcile_persona_assets
# exported _SET_CHANGED=1. The matcher (persona-selector-v2.py) and the dashboard
# already read the SET live, so they self-heal once the SET is current and the
# index carries the new vectors — but two derived artifacts do NOT refresh on
# their own:
#
#   (1) per-dept governing-personas.md — authored FROM the SET at build time;
#       stale until re-written. Re-run create_role_workspaces.py
#       --refresh-personas-only (cheap, idempotent, NO LLM calls).
#   (2) persona_assignment stickiness — a sticky row keeps serving a persona that
#       was picked from the OLD candidate universe for up to ANTI_STALENESS_THRESHOLD
#       dispatches. Flag every row needs_review=1 (persona-selector-v2.py
#       --mode bust-stickiness) so check_sticky_assignment cannot serve a stale pick.
#
# Both steps are static/idempotent — NO embeddings. Safe to run on every SET
# change and a no-op when the workspace/scripts are absent.
# ---------------------------------------------------------------------------
rewire_on_persona_set_change() {
    local _SKILLS_DIR="$1"
    local _WS="$2"
    local _SCRIPTS="$_SKILLS_DIR/23-ai-workforce-blueprint/scripts"
    local _PY; _PY="$(command -v python3 || true)"

    if [ -z "$_PY" ]; then
        echo "  note: python3 not found — skipping persona-SET re-wire (additive)"
        return 0
    fi

    # (1) Regenerate every dept's governing-personas.md from the new SET.
    if [ -f "$_SCRIPTS/create_role_workspaces.py" ]; then
        if "$_PY" "$_SCRIPTS/create_role_workspaces.py" --refresh-personas-only --workspace-root "$_WS" >/dev/null 2>&1; then
            echo "  ✓ re-wire: governing-personas.md refreshed for every dept from the new SET"
        else
            echo "  note: re-wire: governing-personas.md refresh returned non-zero (additive; dashboard reads SET live)"
        fi
    fi

    # (2) Bust persona stickiness so a stale pick can't keep winning.
    if [ -f "$_SCRIPTS/persona-selector-v2.py" ]; then
        if "$_PY" "$_SCRIPTS/persona-selector-v2.py" --mode bust-stickiness >/dev/null 2>&1; then
            echo "  ✓ re-wire: persona stickiness busted (all persona_assignment rows flagged needs_review=1)"
        else
            echo "  note: re-wire: bust-stickiness returned non-zero (additive; ANTI_STALENESS_THRESHOLD still bounds drift)"
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

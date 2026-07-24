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
# _pidx_union_merge_categories <seed_categories_json> <target_categories_json>
#
# F2.1 fix — persona-categories.json UNION MERGE (replaces the old blind
# `cp -f seed target`).  The old copy DEREGISTERED any persona a client box
# legitimately added by running Skill-22 on the client's OWN book: the
# selector's universe is the `personas` keys of persona-categories.json, so
# overwriting the client's file with the shipped seed silently un-registered
# every client-local persona at every update.
#
# Contract:
#   • SEED WINS for seed slugs (canonical author/book/domain/perspective/custom
#     — the seed entry replaces whatever the box had for that same slug).
#   • BOX-LOCAL keys NOT present in the seed are PRESERVED, and stamped
#     `"origin":"local"` so downstream tooling (and provision_persona_index's
#     re-download export path) can distinguish them from seed personas.
#   • When the target has ZERO local-only keys the merge is a BYTE-IDENTICAL
#     copy of the seed (shutil.copyfile) so the canonical persona_set_md5 is
#     preserved exactly — the reconcile idempotency contract is unchanged for
#     every box that never added a local persona.
#
# Pure-Python stdlib, NO embeddings, NO network.  Echoes one status token:
#   COPIED         — no local keys; byte-identical seed copy
#   MERGED:<n>     — <n> box-local persona(s) preserved (origin:local)
#   SKIP:<reason>  — could not read the seed (target left untouched)
# ---------------------------------------------------------------------------
_pidx_union_merge_categories() {
    local _seed="$1" _target="$2"
    python3 - "$_seed" "$_target" <<'PYEOF' 2>/dev/null || echo "SKIP:python-error"
import json, sys, shutil, os

seed_path, target_path = sys.argv[1], sys.argv[2]

try:
    with open(seed_path) as fh:
        seed = json.load(fh)
except Exception as e:
    print("SKIP:seed-unreadable")
    sys.exit(0)

seed_personas = seed.get("personas", {})

# Collect box-local personas: slugs present in the CURRENT target but absent
# from the seed. Everything else defers to the seed (seed wins seed slugs).
local_only = {}
if os.path.exists(target_path):
    try:
        with open(target_path) as fh:
            cur = json.load(fh)
        for slug, entry in (cur.get("personas", {}) or {}).items():
            if slug not in seed_personas:
                e = dict(entry) if isinstance(entry, dict) else {"value": entry}
                e.setdefault("origin", "local")
                local_only[slug] = e
    except Exception:
        # Unreadable/legacy-shape target (e.g. the old {"categories": "..."} stub):
        # nothing to preserve, fall through to the canonical seed copy.
        local_only = {}

if not local_only:
    # Byte-identical copy — preserves the canonical persona_set_md5 exactly.
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    shutil.copyfile(seed_path, target_path)
    print("COPIED")
    sys.exit(0)

# Union: start from the full seed doc (seed metadata + seed personas win),
# then append the preserved box-local personas.
merged = dict(seed)
merged_personas = dict(seed_personas)
merged_personas.update(local_only)   # local-only slugs only; seed slugs already win
merged["personas"] = merged_personas
os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
tmp = target_path + ".mergetmp"
with open(tmp, "w") as fh:
    json.dump(merged, fh, indent=2)
os.replace(tmp, target_path)
print("MERGED:%d" % len(local_only))
PYEOF
}

# ---------------------------------------------------------------------------
# _pidx_skip_warn <reason>
#
# P11-1 (FINAL-REVIEW-2026-07-01 Point 11 fix 1). Every "skip because the
# helper/bundle is missing" path in this file previously used a plain
# `echo "  note: ..."` / `echo "  warn: ..."` line — cosmetic text that never
# matched install.sh's print_install_summary() log-grep (warn_pat='^  ⚠️',
# scanned against the tee'd $LOG_FILE) and was never read back by
# update-skills.sh either. A box that skipped provisioning therefore
# keyword-degraded SILENTLY until the next full install — invisible to the
# install/update completion report the operator actually reads.
#
# This helper (a) emits the SAME "  ⚠️  " prefix install.sh's own warn()
# function produces, so install.sh's existing log-grep completion report
# picks it up with ZERO additional install.sh wiring (its whole stdout is
# already tee'd to $LOG_FILE), and (b) accumulates every reason into
# _PIDX_SKIP_WARNINGS (exported, semicolon-joined) so a caller without a
# tee'd log (update-skills.sh) can read it back after calling into this file
# and fold it into its own completion report explicitly.
# ---------------------------------------------------------------------------
_pidx_skip_warn() {
    local _reason="$1"
    echo "  ⚠️  Persona-index provisioning SKIPPED: $_reason"
    _PIDX_SKIP_WARNINGS="${_PIDX_SKIP_WARNINGS:+$_PIDX_SKIP_WARNINGS; }$_reason"
    export _PIDX_SKIP_WARNINGS
}

# ---------------------------------------------------------------------------
# F2.1 client-local persona PRESERVATION across an index re-download.
#
# When provision_persona_index MUST re-download the canonical asset (genuine
# subset / missing column), a client's own Skill-22 personas (embedded locally
# with the client's OWN key) would be destroyed by the whole-DB replace. These
# helpers export those rows from the old DB first and re-insert them into the
# freshly-downloaded canonical DB, so the client's personas survive.
#
# "Local" personas are the ones reconcile_persona_assets stamped origin:local in
# persona-categories.json (i.e. present on the box but not in the shipped seed).
# ---------------------------------------------------------------------------

# _pidx_local_slugs <categories_json> — echo newline-separated slugs tagged
# origin:local. Empty output when the file is absent/unreadable or has none.
_pidx_local_slugs() {
    local _cats="$1"
    [ -f "$_cats" ] || return 0
    python3 -c '
import json,sys
try:
    d=json.load(open(sys.argv[1]))
except Exception:
    sys.exit(0)
for slug,entry in (d.get("personas",{}) or {}).items():
    if isinstance(entry,dict) and entry.get("origin")=="local":
        print(slug)
' "$_cats" 2>/dev/null || true
}

# _pidx_export_local_rows <old_db> <categories_json> <export_json>
# Export every embeddings row whose persona slug (dir above file_path) is
# origin:local into <export_json> (a JSON {columns:[...], rows:[[...]]}). Echoes
# the exported row count on stdout; empty/0 when nothing to preserve. Non-zero
# return only on a hard failure the caller should treat as "export impossible".
_pidx_export_local_rows() {
    local _olddb="$1" _cats="$2" _out="$3"
    [ -f "$_olddb" ] || { echo 0; return 0; }
    [ -f "$_cats" ]  || { echo 0; return 0; }
    python3 - "$_olddb" "$_cats" "$_out" <<'PYEOF'
import json,sys,os,sqlite3
olddb,cats,out=sys.argv[1],sys.argv[2],sys.argv[3]
try:
    d=json.load(open(cats))
except Exception:
    print(0); sys.exit(0)
local={s for s,e in (d.get("personas",{}) or {}).items()
       if isinstance(e,dict) and e.get("origin")=="local"}
if not local:
    print(0); sys.exit(0)
try:
    c=sqlite3.connect(olddb)
    cols=[r[1] for r in c.execute("PRAGMA table_info(embeddings)").fetchall()]
    if "file_path" not in cols:
        c.close(); print(0); sys.exit(0)
    rows=[]
    for row in c.execute("SELECT %s FROM embeddings" % ",".join(f'"{x}"' for x in cols)):
        fp=row[cols.index("file_path")]
        if not fp: continue
        slug=os.path.basename(os.path.dirname(fp))
        if slug in local:
            rows.append(list(row))
    c.close()
except Exception:
    # Hard failure: signal export-impossible so the caller queues a re-embed.
    print("ERR"); sys.exit(2)
json.dump({"columns":cols,"rows":rows}, open(out,"w"))
print(len(rows))
PYEOF
}

# _pidx_reinsert_local_rows <new_db> <export_json> — INSERT OR IGNORE the
# exported rows into the freshly-downloaded DB, restricted to columns that
# exist in the new schema (schema-flexible). Echoes the inserted row count.
_pidx_reinsert_local_rows() {
    local _newdb="$1" _in="$2"
    [ -f "$_newdb" ] || { echo 0; return 0; }
    [ -f "$_in" ]    || { echo 0; return 0; }
    python3 - "$_newdb" "$_in" <<'PYEOF'
import json,sys,sqlite3
newdb,inp=sys.argv[1],sys.argv[2]
try:
    payload=json.load(open(inp))
except Exception:
    print(0); sys.exit(0)
cols=payload.get("columns",[]); rows=payload.get("rows",[])
if not rows:
    print(0); sys.exit(0)
try:
    c=sqlite3.connect(newdb)
    newcols=[r[1] for r in c.execute("PRAGMA table_info(embeddings)").fetchall()]
    keep=[i for i,x in enumerate(cols) if x in newcols]
    if not keep:
        c.close(); print(0); sys.exit(0)
    kc=[cols[i] for i in keep]
    sql="INSERT OR IGNORE INTO embeddings (%s) VALUES (%s)" % (
        ",".join(f'"{x}"' for x in kc), ",".join("?" for _ in kc))
    n=0
    for r in rows:
        c.execute(sql,[r[i] for i in keep]); n+=1
    c.commit(); c.close()
except Exception:
    print(0); sys.exit(0)
print(n)
PYEOF
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
#   (c) SUBSET index (F2.1): installed chunk_count < manifest chunk_count, OR
#       fewer DISTINCT personas embedded than manifest persona_count — i.e. a
#       NON-canonical partial index (the 6260 / 7615 / 9456-row locally-
#       re-embedded indexes the OLD "has section_number column ⇒ provisioned"
#       gate wrongly treated as done, so those boxes never converged).
#       A SUPERSET index (installed >= manifest on BOTH chunks and personas)
#       is canonical — it is the manifest asset PLUS the client's own
#       locally-embedded personas, and MUST NOT be clobbered by a re-download.
#   (d) persona-dir count under <coaching_db_dir>/personas < manifest
#       persona_count (read live from the manifest; a superset of dirs — client
#       added their own — is fine. F2.5: an absent/zero/unreadable manifest
#       persona_count is "no trustworthy count" and triggers skip-with-warn,
#       NEVER a stale positive default.)
#   (e) the .prebuilt-index-version sentinel != manifest release_tag
#
# SKIP (no download, no re-embed) ONLY when the index genuinely IS AT LEAST the
# canonical asset.  CONTENT-CANONICAL = index present AND columns ok AND
# chunk_count >= manifest AND embedded-persona count >= manifest AND
# persona-dir count >= manifest (superset semantics — F2.1).
#
# LIVE-OPERATOR-INDEX / FURNACE GUARD: a box whose index is content-canonical
# but whose sentinel is absent/empty/stale (e.g. the live operator index, which
# was BUILT locally rather than downloaded and so was never stamped) is
# self-healed — the sentinel is stamped to the manifest tag and the 90MB
# download is SKIPPED.  Re-downloading only happens when the CONTENT is a
# genuine SUBSET (fewer chunks/personas than manifest, or missing columns), so
# neither the operator's canonical index NOR a client's canonical+local-delta
# index is ever clobbered or re-fetched on every update.
#
# CLIENT-LOCAL PRESERVATION (F2.1): when a re-download IS required (genuine
# subset / missing column), rows for box-local personas (those tagged
# origin:local in persona-categories.json) are EXPORTED from the old DB first
# and RE-INSERTED into the freshly-downloaded canonical DB, so the client's own
# Skill-22 personas survive the convergence. If export/re-insert is impossible,
# a .persona-local-reembed-queue marker is written (furnace-safe, no embedding
# here) so the caller can surface "re-embed local personas with the client's
# own key" to the operator.
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
        _pidx_skip_warn "manifest not found ($MANIFEST_PATH) — skipping prebuilt index provisioning (additive)"
        return 0
    fi

    # ── ASSET-FRESHNESS GATE (FDN-7 / F1.3 gate 2) ───────────────────────────
    # A manifest carrying asset_rebuild_required:true was count-synced by a
    # --no-asset staging bump (persona_fleet.py set-manifest-counts): the SET
    # counts were lifted but the published gemini-index.sqlite.gz still lacks
    # vectors for the newest persona(s). (Re)provisioning from it would download
    # / stamp a counted-but-vector-less asset as "canonical", degrading Layer-5
    # to keyword for those personas. REFUSE and KEEP the box's current index
    # until a real build-and-publish.sh (or full publish-personas-to-fleet.sh)
    # rebuilds+publishes the asset and clears the flag. Mirrors the
    # update-skills.sh U6b pre-roll so a DIRECT caller (install.sh Step 6b) is
    # protected identically. Fail-open on a read error (never block on a hiccup).
    local _PIDX_ASSET_REBUILD
    _PIDX_ASSET_REBUILD="$(python3 -c 'import json,sys
try:
    print("true" if json.load(open(sys.argv[1])).get("asset_rebuild_required") is True else "false")
except Exception:
    print("false")' "$MANIFEST_PATH" 2>/dev/null || echo false)"
    if [ "$_PIDX_ASSET_REBUILD" = "true" ]; then
        _pidx_skip_warn "INDEX-MANIFEST asset_rebuild_required:true (a --no-asset staging manifest — the published asset lacks vectors for the newest persona(s)); KEEPING the current persona index and skipping provisioning until shared-utils/prebuilt-index/build-and-publish.sh rebuilds+publishes the asset (clears the flag)"
        return 0
    fi

    # Read manifest fields
    local _PIDX_ASSET_URL _PIDX_SHA _PIDX_CHUNKS _PIDX_TAG _PIDX_COLS _PIDX_PERSONAS
    _PIDX_ASSET_URL="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["asset_url"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["sha256"])' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_CHUNKS="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("chunk_count",0) or 0))' "$MANIFEST_PATH" 2>/dev/null || echo 0)"
    _PIDX_TAG="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("release_tag",""))' "$MANIFEST_PATH" 2>/dev/null || true)"
    _PIDX_COLS="$(python3 -c 'import json,sys; m=json.load(open(sys.argv[1])); print(",".join(m.get("schema",{}).get("columns_required",[])))' "$MANIFEST_PATH" 2>/dev/null || echo "section_number,mode")"
    # F2.5: default persona_count to 0 (NOT a stale positive constant). A partial /
    # corrupt manifest that cannot yield persona_count must NOT silently gate the
    # persona-dir check against an obsolete hardcoded number (it was 54, which the
    # SET long ago outgrew). 0 means "no trustworthy count" → skip-with-warn below,
    # exactly like a missing asset_url/sha256, rather than proceeding on a lie.
    _PIDX_PERSONAS="$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1])).get("persona_count",0) or 0))' "$MANIFEST_PATH" 2>/dev/null || echo 0)"
    if ! [ "$_PIDX_PERSONAS" -gt 0 ] 2>/dev/null; then
        _pidx_skip_warn "manifest persona_count missing/zero/unreadable ($MANIFEST_PATH) — skipping prebuilt index provisioning (additive; keeping current index)"
        return 0
    fi

    mkdir -p "$COACHING_DB_DIR"

    # ── Canonical idempotency gate ───────────────────────────────────────────
    local _COLS_OK=1 _CHUNK_OK=0 _DIR_OK=0 _SENT_OK=0 _COVERAGE_OK=0
    local _INSTALLED_CHUNKS="n/a" _INSTALLED_TAG="" _PERSONA_DIR_COUNT=0
    local _INDEX_PERSONAS=0
    local _GATE_REASONS=""

    # (d-pre) persona-dir count — computed FIRST because it (with the embedded-
    # persona count) tells us whether the box carries a legitimate client LOCAL
    # persona delta, which selects superset-vs-exact gate semantics below.
    # (checked even when the index file is absent).
    if [ -d "$PERSONAS_DIR" ]; then
        _PERSONA_DIR_COUNT="$(find "$PERSONAS_DIR" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"
    fi

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

        # Raw chunk count.
        _INSTALLED_CHUNKS="$(python3 -c 'import sqlite3,sys
try:
    c=sqlite3.connect(sys.argv[1]); print(c.execute("SELECT COUNT(*) FROM embeddings").fetchone()[0]); c.close()
except Exception:
    print(0)' "$COACHING_DB" 2>/dev/null || echo 0)"

        # Raw DISTINCT embedded-persona count (persona slug = the dir one level
        # above each chunk's file_path, per embedding_engine.get_persona_name).
        # Scoped to PERSONA rows only ('%/personas/%', the same filter
        # embedding_engine uses to identify persona chunks) so non-persona rows
        # shipped in the asset (e.g. hormozi_leads_rows) can NEVER inflate the
        # count and spuriously flip the local-delta decision.
        _INDEX_PERSONAS="$(python3 -c 'import sqlite3,sys,os
try:
    c=sqlite3.connect(sys.argv[1])
    seen=set()
    for (fp,) in c.execute("SELECT DISTINCT file_path FROM embeddings WHERE file_path LIKE ?", ("%/personas/%",)):
        if not fp: continue
        seen.add(os.path.basename(os.path.dirname(fp)))
    c.close(); print(len(seen))
except Exception:
    print(0)' "$COACHING_DB" 2>/dev/null || echo 0)"

        # (e) version sentinel
        [ -f "$VERSION_SENTINEL" ] && _INSTALLED_TAG="$(cat "$VERSION_SENTINEL" 2>/dev/null | tr -d '[:space:]')"
        if [ -n "$_PIDX_TAG" ] && [ "$_INSTALLED_TAG" = "$_PIDX_TAG" ]; then
            _SENT_OK=1
        else
            _GATE_REASONS="$_GATE_REASONS sentinel:${_INSTALLED_TAG:-<none>}!=${_PIDX_TAG}"
        fi
    fi

    # ── SUPERSET-vs-EXACT decision (F2.1) ────────────────────────────────────
    # A client LOCAL DELTA = the box carries MORE personas than the manifest
    # ships (a client ran Skill-22 on their OWN book): more persona dirs OR more
    # DISTINCT personas embedded than manifest.persona_count.
    #   • WITH a local delta → SUPERSET semantics (>=): the box is the canonical
    #     asset PLUS the client's own personas and must NOT be clobbered.
    #   • WITHOUT a local delta (same persona set) → historical EXACT semantics:
    #     a stale over-/under-chunked same-set index still converges to canonical
    #     (preserves the 6260/7615/9456-row convergence the gate was built for).
    local _HAS_LOCAL_DELTA=0
    if [ "$_PIDX_PERSONAS" -gt 0 ] 2>/dev/null; then
        if [ "$_PERSONA_DIR_COUNT" -gt "$_PIDX_PERSONAS" ] 2>/dev/null || [ "$_INDEX_PERSONAS" -gt "$_PIDX_PERSONAS" ] 2>/dev/null; then
            _HAS_LOCAL_DELTA=1
        fi
    fi

    if [ -f "$COACHING_DB" ]; then
        # (c) chunk_count
        if [ "$_PIDX_CHUNKS" -gt 0 ] 2>/dev/null; then
            if [ "$_HAS_LOCAL_DELTA" -eq 1 ]; then
                if [ "$_INSTALLED_CHUNKS" -ge "$_PIDX_CHUNKS" ] 2>/dev/null; then
                    _CHUNK_OK=1
                else
                    _GATE_REASONS="$_GATE_REASONS chunk-count:${_INSTALLED_CHUNKS}<${_PIDX_CHUNKS}"
                fi
            else
                if [ "$_INSTALLED_CHUNKS" = "$_PIDX_CHUNKS" ]; then
                    _CHUNK_OK=1
                else
                    _GATE_REASONS="$_GATE_REASONS chunk-count:${_INSTALLED_CHUNKS}!=${_PIDX_CHUNKS}"
                fi
            fi
        else
            _GATE_REASONS="$_GATE_REASONS chunk-count:${_INSTALLED_CHUNKS}!=${_PIDX_CHUNKS}"
        fi

        # (c2) embedded-persona coverage — "every manifest persona has >=1 row"
        # is a superset check in BOTH modes (the manifest set must be fully
        # present; a local delta only ADDS to it).
        if [ "$_PIDX_PERSONAS" -gt 0 ] 2>/dev/null && [ "$_INDEX_PERSONAS" -ge "$_PIDX_PERSONAS" ] 2>/dev/null; then
            _COVERAGE_OK=1
        else
            _GATE_REASONS="$_GATE_REASONS embedded-personas:${_INDEX_PERSONAS}<${_PIDX_PERSONAS}"
        fi
    fi

    # (d) persona-dir count — superset when a local delta exists, exact otherwise.
    if [ "$_PIDX_PERSONAS" -gt 0 ] 2>/dev/null; then
        if [ "$_HAS_LOCAL_DELTA" -eq 1 ]; then
            if [ "$_PERSONA_DIR_COUNT" -ge "$_PIDX_PERSONAS" ] 2>/dev/null; then
                _DIR_OK=1
            else
                _GATE_REASONS="$_GATE_REASONS persona-dir-count:${_PERSONA_DIR_COUNT}<${_PIDX_PERSONAS}"
            fi
        else
            if [ "$_PERSONA_DIR_COUNT" = "$_PIDX_PERSONAS" ]; then
                _DIR_OK=1
            else
                _GATE_REASONS="$_GATE_REASONS persona-dir-count:${_PERSONA_DIR_COUNT}!=${_PIDX_PERSONAS}"
            fi
        fi
    else
        _GATE_REASONS="$_GATE_REASONS persona-dir-count:${_PERSONA_DIR_COUNT}!=${_PIDX_PERSONAS}"
    fi

    # CONTENT-CANONICAL = present + columns + chunks + persona coverage + dirs.
    local _CONTENT_CANON=0
    if [ -f "$COACHING_DB" ] && [ "$_COLS_OK" -eq 1 ] && [ "$_CHUNK_OK" -eq 1 ] && [ "$_COVERAGE_OK" -eq 1 ] && [ "$_DIR_OK" -eq 1 ]; then
        _CONTENT_CANON=1
    fi

    local _PIDX_HAVE=0
    if [ "$_CONTENT_CANON" -eq 1 ]; then
        _PIDX_HAVE=1
        local _DELTA_NOTE=""
        [ "$_HAS_LOCAL_DELTA" -eq 1 ] && _DELTA_NOTE=" [client local persona delta preserved: ${_INDEX_PERSONAS} embedded / ${_PERSONA_DIR_COUNT} dirs >= manifest ${_PIDX_PERSONAS}]"
        if [ "$_SENT_OK" -ne 1 ]; then
            # Self-heal: content proves canonicity; stamp the sentinel rather than
            # re-download (live-operator-index + furnace guard).
            printf '%s\n' "$_PIDX_TAG" > "$VERSION_SENTINEL" 2>/dev/null || true
            echo "  ✓ Persona index content-canonical ($_INSTALLED_CHUNKS chunks >= manifest $_PIDX_CHUNKS, section_number+mode present, $_PERSONA_DIR_COUNT/$_PIDX_PERSONAS persona dirs)$_DELTA_NOTE but sentinel was '${_INSTALLED_TAG:-<none>}' — stamped sentinel=$_PIDX_TAG (self-heal) and skipping download"
        else
            echo "  ✓ Persona index already canonical (release=$_PIDX_TAG, $_INSTALLED_CHUNKS chunks >= manifest $_PIDX_CHUNKS, section_number+mode present, $_PERSONA_DIR_COUNT/$_PIDX_PERSONAS persona dirs)$_DELTA_NOTE — skipping download"
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
            _pidx_skip_warn "manifest missing asset_url/sha256 (partial bundle) — skipping prebuilt provisioning (additive)"
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
                    # ── F2.1: preserve client-local persona rows across the replace ──
                    # Export origin:local persona rows from the OLD db BEFORE the mv,
                    # then re-insert them into the freshly-downloaded canonical db so
                    # the client's own Skill-22 personas survive the convergence.
                    local _CANON_CAT_PROV="$COACHING_DB_DIR/persona-categories.json"
                    local _LOCAL_EXPORT="/tmp/persona-local-rows.$$.json"
                    local _LOCAL_N="0" _REEMBED_QUEUE="$COACHING_DB_DIR/.persona-local-reembed-queue"
                    if [ -f "$COACHING_DB" ]; then
                        _LOCAL_N="$(_pidx_export_local_rows "$COACHING_DB" "$_CANON_CAT_PROV" "$_LOCAL_EXPORT")"
                    fi
                    mv -f "$COACHING_DB.tmp" "$COACHING_DB"
                    # Stamp version sentinel
                    printf '%s\n' "$_PIDX_TAG" > "$VERSION_SENTINEL"
                    echo "  ✓ Persona index installed at $COACHING_DB (sha256 verified, $_PIDX_PERSONA_COUNT personas, release=$_PIDX_TAG)"
                    if [ "$_LOCAL_N" = "ERR" ]; then
                        # Export impossible — queue a delta re-embed (furnace-safe: NO
                        # embedding here) so the operator re-embeds with the CLIENT's key.
                        _pidx_local_slugs "$_CANON_CAT_PROV" > "$_REEMBED_QUEUE" 2>/dev/null || true
                        _pidx_skip_warn "client-local persona rows could not be exported before the index re-download — queued for delta re-embed at $_REEMBED_QUEUE (re-embed with the client's OWN key; blueprints remain on disk)"
                    elif [ "${_LOCAL_N:-0}" != "0" ] 2>/dev/null; then
                        local _REINS
                        _REINS="$(_pidx_reinsert_local_rows "$COACHING_DB" "$_LOCAL_EXPORT")"
                        if [ "${_REINS:-0}" = "$_LOCAL_N" ] 2>/dev/null; then
                            rm -f "$_REEMBED_QUEUE" 2>/dev/null || true
                            echo "  ✓ preserved $_REINS client-local persona row(s) across the re-download (origin:local personas stay embedded)"
                        else
                            _pidx_local_slugs "$_CANON_CAT_PROV" > "$_REEMBED_QUEUE" 2>/dev/null || true
                            _pidx_skip_warn "re-inserted $_REINS/$_LOCAL_N client-local persona row(s) after re-download — queued the rest for delta re-embed at $_REEMBED_QUEUE (client's OWN key)"
                        fi
                    fi
                    rm -f "$_LOCAL_EXPORT" 2>/dev/null || true
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
    export _RECONCILE_OK=1

    local _SRC_CATS="$_SK22/persona-categories.json"
    local _SRC_PERSONAS="$_SK22/personas"

    if [ ! -f "$_SRC_CATS" ] || [ ! -d "$_SRC_PERSONAS" ]; then
        export _RECONCILE_OK=0
        _pidx_skip_warn "Skill-22 persona source not found at $_SK22 — skipping persona reconcile (additive)"
        return 0
    fi

    local _SRC_MD5
    _SRC_MD5="$(_pidx_md5 "$_SRC_CATS")"

    # 1) persona-categories.json → canonical data/ path (+ stale legacy path).
    #    The resolver prefers <ws>/data/coaching-personas/ over <ws>/coaching-personas/,
    #    so the data/ write is authoritative; the legacy write only overwrites an
    #    already-present stale file so no fallback can shadow the canonical one.
    #
    #    F2.1: UNION MERGE, not blind `cp -f`. Seed wins seed slugs; box-local
    #    personas (a client who ran Skill-22 on their OWN book) are PRESERVED and
    #    stamped origin:local so the client's personas stay REGISTERED in the
    #    selector's universe across every update. When the box has no local
    #    persona the merge is a byte-identical seed copy (canonical md5 preserved).
    local _CANON_CAT="$_COACHING_DB_DIR/persona-categories.json"
    local _LEGACY_CAT="$_WS/coaching-personas/persona-categories.json"

    local _canon_md5=""
    [ -f "$_CANON_CAT" ] && _canon_md5="$(_pidx_md5 "$_CANON_CAT")"
    local _canon_status
    _canon_status="$(_pidx_union_merge_categories "$_SRC_CATS" "$_CANON_CAT")"
    local _canon_new_md5
    _canon_new_md5="$(_pidx_md5 "$_CANON_CAT")"
    case "$_canon_status" in
        MERGED:*)
            echo "  ✓ persona-categories.json UNION-merged → $_CANON_CAT (seed wins seed slugs; ${_canon_status#MERGED:} box-local persona(s) PRESERVED origin:local; md5 $_canon_new_md5)"
            ;;
        COPIED)
            if [ "$_canon_md5" = "$_SRC_MD5" ]; then
                echo "  ✓ persona-categories.json already canonical at $_CANON_CAT (md5 $_SRC_MD5)"
            else
                echo "  ✓ persona-categories.json reconciled → $_CANON_CAT (no box-local personas; canonical md5 $_SRC_MD5)"
            fi
            ;;
        *)
            export _RECONCILE_OK=0
            _pidx_skip_warn "persona-categories.json union-merge could not read the seed ($_canon_status) — canonical categories NOT written (additive)"
            ;;
    esac

    if [ -f "$_LEGACY_CAT" ]; then
        local _legacy_status
        _legacy_status="$(_pidx_union_merge_categories "$_SRC_CATS" "$_LEGACY_CAT")"
        case "$_legacy_status" in
            MERGED:*)
                echo "  ✓ persona-categories.json (legacy) UNION-merged → $_LEGACY_CAT (${_legacy_status#MERGED:} box-local persona(s) preserved)"
                ;;
            COPIED)
                echo "  ✓ persona-categories.json (legacy) reconciled → $_LEGACY_CAT"
                ;;
        esac
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

# qmd provisioning removed 2026-07-23.  The `qmd` tool (a local vector-search
# tool backed by better-sqlite3) was replaced by Google/OpenAI embeddings.
# reconcile_qmd_persona_index() and all _qmd_* helpers have been removed.
# Inventory answers now come from persona-categories.json per the N16 hard rule.
# Version-pinned rebuilds (qmd-version-pin.sh) are also archived.


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

    # Set VAR=value in secrets/.env (scoped, idempotent, clobber-guarded).
    # v20.0.10 FIX: the old body unconditionally `grep -v | mv | append`-ed each
    # var, which (a) MOVED it to the bottom of the file on EVERY run -- so an
    # unchanged run never left secrets/.env byte-identical, breaking hash-based
    # revert / integrity checks -- and (b) swallowed a failed grep (`|| true`)
    # whose empty .tmp the `mv` then clobbered the WHOLE file with. This helper
    # is idempotent (exact line already present -> no-op, no reorder) and never
    # clobbers (backs up to .bak; only swaps in the rewritten .tmp when grep did
    # not error AND the tmp is non-empty / a legit all-removed case).
    _pidx_write_env() {
        local var="$1"; local val="$2"; local f="$3"
        [ -f "$f" ] || { touch "$f"; chmod 600 "$f" 2>/dev/null || true; }
        if grep -qxF "${var}=${val}" "$f" 2>/dev/null; then
            return 0
        fi
        cp -p "$f" "$f.bak" 2>/dev/null || true
        local _grc=0
        grep -v "^${var}=" "$f" > "$f.tmp" 2>/dev/null || _grc=$?
        if [ "$_grc" -le 1 ] && { [ -s "$f.tmp" ] || [ "$_grc" -eq 1 ]; }; then
            mv "$f.tmp" "$f" 2>/dev/null || rm -f "$f.tmp" 2>/dev/null || true
        else
            rm -f "$f.tmp" 2>/dev/null || true
        fi
        printf '%s=%s\n' "$var" "$val" >> "$f"
        chmod 600 "$f" 2>/dev/null || true
    }

    # Write to secrets/.env
    if [ -n "$_OC_SECRETS_ENV" ]; then
        mkdir -p "$(dirname "$_OC_SECRETS_ENV")" 2>/dev/null || true
        [ ! -f "$_OC_SECRETS_ENV" ] && { touch "$_OC_SECRETS_ENV"; chmod 600 "$_OC_SECRETS_ENV" 2>/dev/null || true; }
        _pidx_write_env "GHL_FUNNEL_CATALOG" "$_GHL_FUNNEL_CATALOG" "$_OC_SECRETS_ENV"
        _pidx_write_env "GHL_FUNNEL_INDEX" "$_GHL_FUNNEL_INDEX" "$_OC_SECRETS_ENV"
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

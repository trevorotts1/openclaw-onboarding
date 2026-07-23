#!/usr/bin/env bash
# shared-utils/qmd-version-pin.sh
# ─────────────────────────────────────────────────────────────────────────────
# Shared helper: VERSION-PINNED qmd persona-store rebuild.
#
# Complements reconcile_qmd_persona_index() in provision-persona-index.sh.
# reconcile_* repoints/re-indexes the `coaching-personas` qmd collection when it
# is MISPOINTED (wrong path) — but it cannot tell that the personas at the SAME
# canonical path CHANGED CONTENT (a persona added/edited in place, a Skill-22 SET
# bump). On a content bump with an unchanged path, a `qmd update` may or may not
# pick up new dirs and there is no record of WHICH library version the live index
# was built from — so a box can silently serve a stale full-text store.
#
# This helper makes the rebuild DETERMINISTIC: it pins the index to an EXPECTED
# version (the Skill-22 / persona-SET version the library shipped) by writing a
# sentinel next to the canonical personas dir, and REBUILDS the collection
# (remove + re-add, BM25 full-text only) whenever the live pin != expected.
#
# FURNACE-SAFE: BM25 / full-text only (`qmd collection add` / `qmd update`).
# It NEVER runs `qmd embed`, so ZERO vector embeddings are computed.
# ADDITIVE: if qmd is absent or the rebuild fails, it tears down any stale
# collection so the agent can never read a frozen store (inventory then answers
# from persona-categories.json per the Skill-22 N16 hard rule).
#
# Source this file (do NOT execute it directly) then call:
#
#   qmd_version_pin_rebuild <PERSONAS_DIR> <EXPECTED_VERSION> [COLLECTION_NAME]
#
#   PERSONAS_DIR     canonical personas dir (…/coaching-personas-db/personas)
#   EXPECTED_VERSION version string the library shipped (e.g. Skill-22 v6.13.0
#                    from 22-…/skill-version.txt). Drives the rebuild decision.
#   COLLECTION_NAME  optional; defaults to "coaching-personas".
#
# Returns 0 on success/no-op (in sync, or qmd absent → skip), 0 too when a stale
# store was torn down (the N16 fallback keeps the agent correct), and 1 only on
# an unexpected internal error.
#
# Callers: install.sh Step 6b, update-skills.sh Step U6b — AFTER
# reconcile_persona_assets + provision_persona_index + reconcile_qmd_persona_index.
# ─────────────────────────────────────────────────────────────────────────────

# ---------------------------------------------------------------------------
# qmd_pin_file <personas_dir>
#
# Path of the version-pin sentinel for a personas dir. Stored as a sibling of
# the personas dir so it travels with the canonical store and is not confused
# with the prebuilt-index sentinel used by provision_persona_index.
# ---------------------------------------------------------------------------
qmd_pin_file() {
    local _personas_dir="$1"
    printf '%s\n' "$(dirname "$_personas_dir")/.qmd-persona-index-version"
}

# ---------------------------------------------------------------------------
# qmd_read_pin <personas_dir>  → prints the recorded version (empty if none)
# ---------------------------------------------------------------------------
qmd_read_pin() {
    local _pin
    _pin="$(qmd_pin_file "$1")"
    [ -f "$_pin" ] && tr -d '[:space:]' < "$_pin" 2>/dev/null || printf ''
}

# ---------------------------------------------------------------------------
# qmd_write_pin <personas_dir> <version>
# ---------------------------------------------------------------------------
qmd_write_pin() {
    local _pin
    _pin="$(qmd_pin_file "$1")"
    printf '%s\n' "$2" > "$_pin" 2>/dev/null || return 1
}

# ---------------------------------------------------------------------------
# qmd_version_pin_rebuild <personas_dir> <expected_version> [collection_name]
# ---------------------------------------------------------------------------
qmd_version_pin_rebuild() {
    local _personas_dir="$1"
    local _expected="$2"
    local _coll="${3:-coaching-personas}"

    if [ -z "$_personas_dir" ] || [ -z "$_expected" ]; then
        echo "  qmd-pin: usage: qmd_version_pin_rebuild <personas_dir> <expected_version> [collection]" >&2
        return 1
    fi

    if ! command -v qmd >/dev/null 2>&1; then
        echo "  qmd-pin: qmd not installed — skipping version-pin rebuild (additive; inventory answers from persona-categories.json per N16)"
        return 0
    fi
    if [ ! -d "$_personas_dir" ]; then
        echo "  qmd-pin: canonical personas dir absent ($_personas_dir) — skipping (additive)"
        return 0
    fi

    local _live_pin
    _live_pin="$(qmd_read_pin "$_personas_dir")"

    # Does the collection currently exist?
    local _list _has_coll=0
    _list="$(qmd collection list 2>/dev/null || true)"
    printf '%s' "$_list" | grep -q "$_coll" && _has_coll=1

    # In sync = collection present AND pin already equals the expected version.
    if [ "$_has_coll" -eq 1 ] && [ "$_live_pin" = "$_expected" ]; then
        echo "  qmd-pin: '$_coll' already at pinned version $_expected — no rebuild needed"
        return 0
    fi

    local _n_dirs
    _n_dirs="$(find "$_personas_dir" -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')"

    if [ "$_has_coll" -eq 1 ]; then
        echo "  qmd-pin: '$_coll' version drift (live='${_live_pin:-none}' expected='$_expected') — rebuilding (BM25, furnace-safe)"
        qmd collection remove "$_coll" >/dev/null 2>&1 || true
    else
        echo "  qmd-pin: '$_coll' missing — building at pinned version $_expected (BM25, furnace-safe)"
    fi

    if qmd collection add "$_personas_dir" --name "$_coll" --mask '*.md' >/dev/null 2>&1; then
        qmd_write_pin "$_personas_dir" "$_expected" || true
        echo "  ✓ qmd-pin: '$_coll' (re)built at $_personas_dir ($_n_dirs persona dirs) — pinned to $_expected (BM25/full-text only)"
        return 0
    fi

    # Rebuild failed — tear down any partial/stale collection so the agent can
    # never read a frozen store, and drop the pin (forces a retry next run).
    qmd collection remove "$_coll" >/dev/null 2>&1 || true
    rm -f "$(qmd_pin_file "$_personas_dir")" 2>/dev/null || true
    echo "  qmd-pin: could not (re)build '$_coll' — removed any stale collection + pin so inventory falls back to persona-categories.json per N16 (additive)"
    return 0
}

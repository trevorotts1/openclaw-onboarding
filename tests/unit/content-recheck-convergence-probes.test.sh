#!/usr/bin/env bash
# tests/unit/content-recheck-convergence-probes.test.sh
# ---------------------------------------------------------------------------
# Fleet-roll coverage audit gap #8: proves the SOP-library/embeddings,
# persona-index, weekly-cron, AGENTS.md-hygiene, and UPDATE-PENDING-flag-
# currency probes added right before update-skills.sh's CONTENT RECHECK
# `exit 0` behave exactly like _cc_currency_probe's already-shipped contract:
#
#   * return 1 (non-zero) ONLY when a full pass would ACTUALLY repair
#     something on this box.
#   * return 0 for absent / unknown / already-current / any read error --
#     NEVER forcing a full pass on a box that genuinely has nothing to do.
#   * never write, delete, or invoke a mutating subcommand.
#
# and that the aggregation gate built on top of them:
#   * still fires the fast `exit 0` when every probe reports "converged".
#   * falls through (no exit) the instant ANY ONE probe reports outstanding
#     work, and names it in the printed message.
#
# METHOD. Like tests/unit/sop-embeddings-independent-gate.test.sh, this does
# NOT reimplement any probe logic: it extracts the real blocks VERBATIM from
# update-skills.sh between named markers and sources them. If those markers
# drift or vanish the suite fails loudly (exit 2) rather than silently
# testing nothing. The one non-probe helper the AGENTS.md probe depends on
# (oc_resolve_workspace_announced) is extracted the same way, by brace-
# matching its own top-level function definition.
#
# FULLY OFFLINE. No network call, no real DB, no real box. Every filesystem
# path used by a probe under test (HOME, SKILLS_DIR, EXTRACTED_DIR,
# DASHBOARD_DB_PATH, the `openclaw` CLI) is redirected into a throwaway
# $WORK directory / PATH-shimmed mock; nothing under the real $HOME or
# /data/.openclaw is ever read or written.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UPDATER="$REPO_ROOT/update-skills.sh"
RESOLVE_DB_PY="$REPO_ROOT/shared-utils/resolve_db.py"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

[ -f "$UPDATER" ] || { echo "FATAL: $UPDATER not found"; exit 2; }
[ -f "$RESOLVE_DB_PY" ] || { echo "FATAL: $RESOLVE_DB_PY not found"; exit 2; }

WORK="$(mktemp -d -t convergence-probes-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- verbatim extraction between markers, mirroring
#     tests/unit/sop-embeddings-independent-gate.test.sh -----------------
extract_block() {
  awk -v b=">>> $1-BEGIN" -v e="<<< $1-END" '
    index($0, b) { p=1; next }
    index($0, e) { p=0 }
    p { print }
  ' "$UPDATER"
}

# --- verbatim extraction of a single top-level `name() { ... }` function,
#     by brace-matching its own bare closing "}" line (col 0). Used only for
#     oc_resolve_workspace_announced, a pre-existing helper the AGENTS.md
#     probe depends on but does not itself define.
extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$UPDATER"
}

extract_block "CONTENT-RECHECK-CONVERGENCE-PROBES" > "$WORK/probes.inc"
if [ ! -s "$WORK/probes.inc" ]; then
  echo "FATAL: marker block 'CONTENT-RECHECK-CONVERGENCE-PROBES' not found in update-skills.sh (marker drift?)"
  exit 2
fi
extract_block "CONTENT-RECHECK-CONVERGENCE-GATE" > "$WORK/gate.inc"
if [ ! -s "$WORK/gate.inc" ]; then
  echo "FATAL: marker block 'CONTENT-RECHECK-CONVERGENCE-GATE' not found in update-skills.sh (marker drift?)"
  exit 2
fi
extract_function "oc_resolve_workspace_announced" > "$WORK/resolve_ws.inc"
if [ ! -s "$WORK/resolve_ws.inc" ]; then
  echo "FATAL: could not extract oc_resolve_workspace_announced() from update-skills.sh (drift?)"
  exit 2
fi

{
  echo 'probes_block() {'
  cat "$WORK/probes.inc"
  echo '}'
} > "$WORK/probes-wrapped.sh"
bash -n "$WORK/probes-wrapped.sh" || { echo "FATAL: extracted PROBES block does not parse"; exit 2; }

{
  echo 'gate_block() {'
  cat "$WORK/gate.inc"
  echo '}'
} > "$WORK/gate-wrapped.sh"
bash -n "$WORK/gate-wrapped.sh" || { echo "FATAL: extracted GATE block does not parse"; exit 2; }

cp "$WORK/resolve_ws.inc" "$WORK/resolve_ws.sh"
bash -n "$WORK/resolve_ws.sh" || { echo "FATAL: extracted oc_resolve_workspace_announced() does not parse"; exit 2; }

echo "== static: all five probes are present and wired ahead of the exit =="
for fn in _sop_library_currency_probe _persona_index_currency_probe \
          _weekly_cron_currency_probe _agents_md_hygiene_probe \
          _pending_flag_currency_probe; do
  grep -q "^  ${fn}() {\$" "$WORK/probes.inc" \
    && ok "PROBES block defines ${fn}()" || bad "PROBES block missing ${fn}()"
done
for fn in _cc_currency_probe _sop_library_currency_probe _persona_index_currency_probe \
          _weekly_cron_currency_probe _agents_md_hygiene_probe _pending_flag_currency_probe; do
  grep -q "${fn}" "$WORK/gate.inc" \
    && ok "GATE block calls ${fn}" || bad "GATE block does not call ${fn}"
done

# Executable-code-only view of the block: strips comment-only lines so the
# mutation checks below cannot false-positive on this file's OWN prose (the
# header comments explicitly discuss "cron create/edit/delete", "exit 0",
# and "INSERT/UPDATE/DELETE" as things the probes must NOT do -- and the
# word "update" is baked into "weekly-onboarding-update" throughout every
# probe's echo strings, which would otherwise trip a bare "UPDATE " grep).
grep -vE '^\s*#' "$WORK/probes.inc" > "$WORK/probes-code-only.inc"

echo ""
echo "== static: probes never mutate anything (no writes, no destructive SQL/CLI) =="
if grep -qE 'openclaw cron (create|edit|delete)' "$WORK/probes-code-only.inc"; then
  bad "a probe invokes a mutating 'openclaw cron' subcommand"
else
  ok "no probe invokes openclaw cron create/edit/delete"
fi
if grep -qiE 'sqlite3.*\b(INSERT INTO|UPDATE[[:space:]]+[A-Za-z_]+[[:space:]]+SET|DELETE FROM|DROP TABLE)\b' "$WORK/probes-code-only.inc"; then
  bad "a probe issues a mutating SQL statement"
else
  ok "no probe issues INSERT/UPDATE/DELETE/DROP SQL"
fi
if grep -qE '(^|[^_a-zA-Z.])exit[[:space:]]' "$WORK/probes-code-only.inc"; then
  bad "a probe calls exit (must never abort the roll)"
else
  ok "no probe calls exit -- advisory only, like _cc_currency_probe"
fi
if grep -qE '\?mode=ro' "$WORK/probes.inc"; then
  ok "every sqlite3 query opens the DB read-only (?mode=ro)"
else
  bad "no ?mode=ro sqlite3 open found -- expected read-only DB access"
fi

# ===========================================================================
# SOP LIBRARY / EMBEDDINGS PROBE
# ===========================================================================
make_sop_db() {  # make_sop_db <path> <sops_rows> <embed_rows_from_sops>
  local db="$1" n_sops="$2" n_emb="$3"
  python3 - "$db" "$n_sops" "$n_emb" <<'PYEOF'
import sqlite3, sys
db, n_sops, n_emb = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
con = sqlite3.connect(db)
con.executescript("""
CREATE TABLE sops (id TEXT PRIMARY KEY, name TEXT NOT NULL, slug TEXT NOT NULL UNIQUE, steps TEXT NOT NULL);
CREATE TABLE sop_embeddings (sop_id TEXT PRIMARY KEY, embedding BLOB NOT NULL);
""")
for i in range(n_sops):
    con.execute("INSERT INTO sops (id,name,slug,steps) VALUES (?,?,?,'[]')", (f"sop_{i}", f"sop-{i}", f"sop-{i}"))
for i in range(n_emb):
    con.execute("INSERT INTO sop_embeddings (sop_id, embedding) VALUES (?,?)", (f"sop_{i}", b"\x00"))
con.commit(); con.close()
PYEOF
}

run_sop_probe() {  # run_sop_probe <db_path_or_empty> <canon_sops> <manifest_emb_count>
  local db="$1" canon="$2" emb_count="$3"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/probes-wrapped.sh"
    probes_block
    SKILLS_DIR="$WORK/sop-skills-dir-unused"
    EXTRACTED_DIR="$WORK/sop-extracted-unused"
    mkdir -p "$SKILLS_DIR/shared-utils/sop-library" "$SKILLS_DIR/shared-utils/sop-embed-once"
    cp "$RESOLVE_DB_PY" "$SKILLS_DIR/shared-utils/resolve_db.py"
    printf '{"canonical_sop_count": %s}\n' "$canon" > "$SKILLS_DIR/shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json"
    printf '{"sop_count": %s}\n' "$emb_count" > "$SKILLS_DIR/shared-utils/sop-embed-once/SOP-EMBEDDINGS-MANIFEST.json"
    if [ -n "$db" ]; then
      DASHBOARD_DB_PATH="$db"
      export DASHBOARD_DB_PATH
    else
      unset DASHBOARD_DB_PATH DATABASE_PATH 2>/dev/null || true
    fi
    _sop_library_currency_probe
  )
}

echo ""
echo "== SOP library/embeddings probe =="
D_SOP="$WORK/sop"; mkdir -p "$D_SOP"

make_sop_db "$D_SOP/converged.db" 5 5
run_sop_probe "$D_SOP/converged.db" 5 5 >/tmp/sop1.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(sop) converged box (sops>=canon, embeddings>=manifest) returns 0" \
  || bad "(sop) converged box returned $RC (expected 0): $(cat /tmp/sop1.out)"

make_sop_db "$D_SOP/under-sops.db" 3 3
run_sop_probe "$D_SOP/under-sops.db" 5 3 >/tmp/sop2.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(sop) under-populated sops table returns 1 (outstanding)" \
  || bad "(sop) under-populated sops returned $RC (expected 1): $(cat /tmp/sop2.out)"
grep -q "under-populated" /tmp/sop2.out && ok "(sop) reports under-populated state" || bad "(sop) missing under-populated message"

make_sop_db "$D_SOP/under-emb.db" 5 2
run_sop_probe "$D_SOP/under-emb.db" 5 5 >/tmp/sop3.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(sop) sops current but embeddings under manifest count returns 1" \
  || bad "(sop) under-populated embeddings returned $RC (expected 1): $(cat /tmp/sop3.out)"
grep -q "embeddings-under-populated" /tmp/sop3.out && ok "(sop) reports embeddings-under-populated state" || bad "(sop) missing embeddings-under-populated message"

run_sop_probe "" 5 5 >/tmp/sop4.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(sop) no DB resolvable returns 0 (absent, not forced)" \
  || bad "(sop) absent DB returned $RC (expected 0): $(cat /tmp/sop4.out)"
rm -f /tmp/sop1.out /tmp/sop2.out /tmp/sop3.out /tmp/sop4.out

# ===========================================================================
# PERSONA-INDEX PROBE
# ===========================================================================
run_persona_probe() {  # run_persona_probe <release_tag_or_empty_manifest> <sentinel_value_or_absent>
  local release_tag="$1" sentinel="$2"
  local CASE_DIR; CASE_DIR="$(mktemp -d "$WORK/persona-case-XXXXXX")"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/probes-wrapped.sh"
    probes_block
    HOME="$CASE_DIR/home"
    mkdir -p "$HOME/.openclaw/workspace/data/coaching-personas"
    SKILLS_DIR="$CASE_DIR/skills-dir-unused"
    # shellcheck disable=SC2034  # read by _persona_index_currency_probe (dynamically sourced above) as its EXTRACTED_DIR fallback, not this scope
    EXTRACTED_DIR="$CASE_DIR/extracted-unused"
    mkdir -p "$SKILLS_DIR/shared-utils/prebuilt-index"
    if [ -n "$release_tag" ]; then
      printf '{"release_tag": "%s"}\n' "$release_tag" > "$SKILLS_DIR/shared-utils/prebuilt-index/INDEX-MANIFEST.json"
    fi
    if [ -n "$sentinel" ]; then
      printf '%s' "$sentinel" > "$HOME/.openclaw/workspace/data/coaching-personas/.prebuilt-index-version"
    fi
    _persona_index_currency_probe
  )
}

echo ""
echo "== Persona-index probe =="
run_persona_probe "tag-v7" "tag-v7" >/tmp/pip1.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(persona) sentinel == release_tag returns 0 (current)" \
  || bad "(persona) matching sentinel returned $RC (expected 0): $(cat /tmp/pip1.out)"

run_persona_probe "tag-v8" "tag-v7" >/tmp/pip2.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(persona) sentinel != release_tag returns 1 (stale, outstanding)" \
  || bad "(persona) stale sentinel returned $RC (expected 1): $(cat /tmp/pip2.out)"

run_persona_probe "tag-v9" "" >/tmp/pip3.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(persona) sentinel absent (never provisioned) returns 1" \
  || bad "(persona) missing sentinel returned $RC (expected 1): $(cat /tmp/pip3.out)"

run_persona_probe "" "" >/tmp/pip4.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(persona) manifest absent returns 0 (nothing to compare, not forced)" \
  || bad "(persona) absent manifest returned $RC (expected 0): $(cat /tmp/pip4.out)"
rm -f /tmp/pip1.out /tmp/pip2.out /tmp/pip3.out /tmp/pip4.out

# ===========================================================================
# WEEKLY-CRON PROBE
# ===========================================================================
make_openclaw_mock() {  # make_openclaw_mock <bindir> <cron_json>
  local bindir="$1" json="$2"
  mkdir -p "$bindir"
  cat > "$bindir/openclaw" <<EOF
#!/usr/bin/env bash
if [ "\$1" = "cron" ] && [ "\$2" = "list" ]; then
  cat <<'JSONEOF'
$json
JSONEOF
  exit 0
fi
exit 1
EOF
  chmod +x "$bindir/openclaw"
}

run_cron_probe() {  # run_cron_probe <json_or_empty> <tombstoned:yes/no> <no_cli:yes/no>
  local json="$1" tomb="$2" no_cli="$3"
  local CASE_DIR; CASE_DIR="$(mktemp -d "$WORK/cron-case-XXXXXX")"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/probes-wrapped.sh"
    probes_block
    HOME="$CASE_DIR/home"
    mkdir -p "$HOME/.openclaw/workspace/.cron-tombstones"
    if [ "$tomb" = "yes" ]; then
      printf 'TOMBSTONED\n' > "$HOME/.openclaw/workspace/.cron-tombstones/weekly-onboarding-update"
    fi
    BINDIR="$CASE_DIR/bin"
    if [ "$no_cli" = "yes" ]; then
      PATH="/usr/bin:/bin"
    else
      make_openclaw_mock "$BINDIR" "$json"
      PATH="$BINDIR:$PATH"
    fi
    _weekly_cron_currency_probe
  )
}

echo ""
echo "== Weekly-cron registration probe =="
run_cron_probe '[{"name":"weekly-onboarding-update","id":"1"}]' no no >/tmp/wcp1.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(cron) job present in JSON returns 0 (registered)" \
  || bad "(cron) present-job case returned $RC (expected 0): $(cat /tmp/wcp1.out)"

run_cron_probe '[{"name":"some-other-cron","id":"1"}]' no no >/tmp/wcp2.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(cron) job absent + not tombstoned returns 1 (outstanding)" \
  || bad "(cron) absent-job case returned $RC (expected 1): $(cat /tmp/wcp2.out)"

run_cron_probe '[{"name":"some-other-cron","id":"1"}]' yes no >/tmp/wcp3.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(cron) job absent BUT tombstoned returns 0 (deliberate, not outstanding)" \
  || bad "(cron) tombstoned case returned $RC (expected 0): $(cat /tmp/wcp3.out)"

run_cron_probe '' no yes >/tmp/wcp4.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(cron) openclaw CLI missing returns 0 (unknown, not forced)" \
  || bad "(cron) no-CLI case returned $RC (expected 0): $(cat /tmp/wcp4.out)"

run_cron_probe 'not valid json{{{' no no >/tmp/wcp5.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(cron) unparseable JSON returns 0 (advisory, not forced -- NOT fail-open like oc_cron_present)" \
  || bad "(cron) unparseable-JSON case returned $RC (expected 0): $(cat /tmp/wcp5.out)"
rm -f /tmp/wcp1.out /tmp/wcp2.out /tmp/wcp3.out /tmp/wcp4.out /tmp/wcp5.out

# ===========================================================================
# AGENTS.md HYGIENE PROBE
# ===========================================================================
run_agents_probe() {  # run_agents_probe <agents_md_fixture_file>
  local fixture="$1"
  local CASE_DIR; CASE_DIR="$(mktemp -d "$WORK/agents-case-XXXXXX")"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/resolve_ws.sh"
    # shellcheck source=/dev/null
    source "$WORK/probes-wrapped.sh"
    probes_block
    HOME="$CASE_DIR/home"
    WS="$CASE_DIR/ws"
    mkdir -p "$HOME/.openclaw" "$WS"
    python3 -c "
import json
json.dump({'agents': {'list': [{'id': 'main', 'workspace': '$WS'}]}}, open('$HOME/.openclaw/openclaw.json', 'w'))
"
    if [ -n "$fixture" ]; then
      cp "$fixture" "$WS/AGENTS.md"
    fi
    _agents_md_hygiene_probe
  )
}

echo ""
echo "== AGENTS.md hygiene probe =="
D_AMH="$WORK/amh"; mkdir -p "$D_AMH"

cat > "$D_AMH/clean.md" <<'EOF'
# AGENTS.md

<!-- ROLE_DISCIPLINE_V1 -->
## Role Discipline
Some body text.

<!-- BEGIN skill:16-summarize-youtube:agents -->
## Skill 16
body
<!-- END skill:16-summarize-youtube:agents -->
EOF
run_agents_probe "$D_AMH/clean.md" >/tmp/amh1.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(agents.md) clean file (no dup markers, balanced BEGIN/END) returns 0" \
  || bad "(agents.md) clean case returned $RC (expected 0): $(cat /tmp/amh1.out)"

cat > "$D_AMH/dup-marker.md" <<'EOF'
# AGENTS.md

<!-- ROLE_DISCIPLINE_V1 -->
## Role Discipline
First copy.

<!-- ROLE_DISCIPLINE_V1 -->
## Role Discipline
First copy.
EOF
run_agents_probe "$D_AMH/dup-marker.md" >/tmp/amh2.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(agents.md) duplicated marker token returns 1 (dedup has real work)" \
  || bad "(agents.md) duplicate-marker case returned $RC (expected 1): $(cat /tmp/amh2.out)"
grep -q "duplicate-marker-tokens=1" /tmp/amh2.out && ok "(agents.md) reports duplicate-marker-tokens=1" || bad "(agents.md) missing duplicate-marker-tokens count"

cat > "$D_AMH/orphan-end.md" <<'EOF'
# AGENTS.md

Some content.

<!-- END skill:16-summarize-youtube:agents -->

More content.
EOF
run_agents_probe "$D_AMH/orphan-end.md" >/tmp/amh3.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(agents.md) orphan END with no matching BEGIN returns 1" \
  || bad "(agents.md) orphan-END case returned $RC (expected 1): $(cat /tmp/amh3.out)"
grep -q "orphan-BEGIN/END-pairs=1" /tmp/amh3.out && ok "(agents.md) reports orphan-BEGIN/END-pairs=1" || bad "(agents.md) missing orphan-pairs count"

run_agents_probe "" >/tmp/amh4.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(agents.md) no AGENTS.md on this box returns 0 (absent, not forced)" \
  || bad "(agents.md) absent-file case returned $RC (expected 0): $(cat /tmp/amh4.out)"
rm -f /tmp/amh1.out /tmp/amh2.out /tmp/amh3.out /tmp/amh4.out

# ===========================================================================
# UPDATE PENDING FLAG CURRENCY PROBE
# ===========================================================================
run_pending_probe() {  # run_pending_probe <agents_md_fixture_file> <onboarding_version>
  local fixture="$1" version="$2"
  local CASE_DIR; CASE_DIR="$(mktemp -d "$WORK/pending-case-XXXXXX")"
  (
    set -euo pipefail
    # shellcheck source=/dev/null
    source "$WORK/resolve_ws.sh"
    # shellcheck source=/dev/null
    source "$WORK/probes-wrapped.sh"
    probes_block
    HOME="$CASE_DIR/home"
    WS="$CASE_DIR/ws"
    mkdir -p "$HOME/.openclaw" "$WS"
    python3 -c "
import json
json.dump({'agents': {'list': [{'id': 'main', 'workspace': '$WS'}]}}, open('$HOME/.openclaw/openclaw.json', 'w'))
"
    if [ -n "$fixture" ]; then
      cp "$fixture" "$WS/AGENTS.md"
    fi
    ONBOARDING_VERSION="$version"
    _pending_flag_currency_probe
  )
}

echo ""
echo "== UPDATE PENDING flag currency probe =="
D_PFC="$WORK/pfc"; mkdir -p "$D_PFC"

# no PENDING block at all -> clean, not forced (mirrors "no PENDING present ->
# clean write" from the mutation-proof table).
cat > "$D_PFC/no-flag.md" <<'EOF'
# AGENTS.md

Some ordinary content. Nothing pending here.
EOF
run_pending_probe "$D_PFC/no-flag.md" "v21.7.5" >/tmp/pfc1.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(pending) no PENDING section returns 0 (clean)" \
  || bad "(pending) no-flag case returned $RC (expected 0): $(cat /tmp/pfc1.out)"

# CURRENT-version PENDING block -> not stale, returns 0 ("CURRENT PENDING
# present -> not duplicated, not swept spuriously").
cat > "$D_PFC/current-flag.md" <<'EOF'
# AGENTS.md

## UPDATE PENDING -- Skill Update to v21.7.5

A skill update was applied via update-skills.sh. Activate each new skill below.
EOF
run_pending_probe "$D_PFC/current-flag.md" "v21.7.5" >/tmp/pfc2.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(pending) PENDING section naming the CURRENT version returns 0 (not stale)" \
  || bad "(pending) current-version case returned $RC (expected 0): $(cat /tmp/pfc2.out)"

# STALE (prior-version) PENDING block -> returns 1, outstanding
# ("stale PENDING present (older version stamp)").
cat > "$D_PFC/stale-flag.md" <<'EOF'
# AGENTS.md

## UPDATE PENDING -- Skill Update to v21.7.2

A skill update was applied via update-skills.sh on 2026-06-15. Activate each new skill below.
EOF
run_pending_probe "$D_PFC/stale-flag.md" "v21.7.5" >/tmp/pfc3.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(pending) PENDING section naming an OLDER version returns 1 (stale, outstanding)" \
  || bad "(pending) stale-version case returned $RC (expected 1): $(cat /tmp/pfc3.out)"
grep -q "state=stale sections=1" /tmp/pfc3.out && ok "(pending) reports state=stale sections=1" || bad "(pending) missing state=stale sections=1 message"

# THREE stacked stale blocks (the measured VPS case) -> still returns 1, and
# is reported as a SINGLE outstanding finding covering all three sections.
cat > "$D_PFC/triple-stale.md" <<'EOF'
# AGENTS.md

## UPDATE PENDING -- Skill Update to v21.6.9

wave 1, never processed.

## UPDATE PENDING -- Skill Update to v21.7.0

wave 2, never processed.

## UPDATE PENDING -- Skill Update to v21.7.3

wave 3, never processed.
EOF
run_pending_probe "$D_PFC/triple-stale.md" "v21.7.5" >/tmp/pfc4.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(pending) three stacked stale sections still returns 1 (outstanding)" \
  || bad "(pending) triple-stale case returned $RC (expected 1): $(cat /tmp/pfc4.out)"
grep -q "state=stale sections=3" /tmp/pfc4.out && ok "(pending) reports all three stacked sections (sections=3)" || bad "(pending) missing sections=3 count: $(cat /tmp/pfc4.out)"

# Legacy "ONBOARDING PENDING" wording (predates the version-stamped flag,
# per Start Here.md) never matches "Skill Update to X" -> unparsable -> stale.
cat > "$D_PFC/legacy-onboarding-pending.md" <<'EOF'
# AGENTS.md

## ONBOARDING PENDING - EXECUTE NOW

Legacy install-time flag, no version token at all.
EOF
run_pending_probe "$D_PFC/legacy-onboarding-pending.md" "v21.7.5" >/tmp/pfc5.out 2>&1
RC=$?
[ "$RC" -eq 1 ] && ok "(pending) legacy unparsable ONBOARDING PENDING section returns 1 (fail toward outstanding)" \
  || bad "(pending) legacy-wording case returned $RC (expected 1): $(cat /tmp/pfc5.out)"

run_pending_probe "" "v21.7.5" >/tmp/pfc6.out 2>&1
RC=$?
[ "$RC" -eq 0 ] && ok "(pending) no AGENTS.md on this box returns 0 (absent, not forced)" \
  || bad "(pending) absent-file case returned $RC (expected 0): $(cat /tmp/pfc6.out)"
rm -f /tmp/pfc1.out /tmp/pfc2.out /tmp/pfc3.out /tmp/pfc4.out /tmp/pfc5.out /tmp/pfc6.out

# ===========================================================================
# AGGREGATION GATE: fast-exit fires ONLY when every probe converges;
# falls through the instant any ONE probe reports outstanding work.
# ===========================================================================
run_gate() {  # run_gate <cc_rc> <sop_rc> <persona_rc> <cron_rc> <agents_rc> <pending_rc>
  local cc="$1" sop="$2" persona="$3" cron="$4" agents="$5" pending="$6"
  (
    set -euo pipefail
    # Stubs: the gate only needs each probe's RETURN CODE to decide whether
    # to fast-exit -- it does not care about a probe's internal logic, which
    # is proven separately above against fixtures. `eval` bakes each fixed
    # exit code straight into the function body (a bare `return "$cc"` would
    # instead try to read a positional parameter of the STUBBED function,
    # not this outer variable).
    eval "_cc_currency_probe() { echo stub-cc; return $cc; }"
    eval "_sop_library_currency_probe() { echo stub-sop; return $sop; }"
    eval "_persona_index_currency_probe() { echo stub-persona; return $persona; }"
    eval "_weekly_cron_currency_probe() { echo stub-cron; return $cron; }"
    eval "_agents_md_hygiene_probe() { echo stub-agents; return $agents; }"
    eval "_pending_flag_currency_probe() { echo stub-pending; return $pending; }"
    # shellcheck source=/dev/null
    source "$WORK/gate-wrapped.sh"
    # shellcheck disable=SC2034  # read by gate_block (dynamically sourced above) for its cleanup rm -rf, not this scope
    TEMP_EXTRACT="$WORK/gate-temp-extract-$$-unused"
    # shellcheck disable=SC2034  # read by gate_block (dynamically sourced above) for its cleanup rm -rf, not this scope
    TEMP_ZIP="$WORK/gate-temp-zip-$$-unused"
    gate_block
    echo "GATE_FELL_THROUGH rc=$?"
  )
}

echo ""
echo "== Aggregation gate: fast-exit vs fall-through =="
OUT="$(run_gate 0 0 0 0 0 0 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ok "(gate) all six probes converged (rc=0 each) -- subshell exits 0" \
  || bad "(gate) all-converged case exited $RC (expected 0): $OUT"
echo "$OUT" | grep -q "nothing to do" && ok "(gate) prints the fast-exit 'nothing to do' message" || bad "(gate) missing fast-exit message: $OUT"
if echo "$OUT" | grep -q "GATE_FELL_THROUGH"; then
  bad "(gate) all-converged case did NOT fast-exit -- fell through instead: $OUT"
else
  ok "(gate) exit 0 actually fired (never reached the fall-through echo)"
fi

for combo in "1:0:0:0:0:0:Command Center currency" \
             "0:1:0:0:0:0:SOP library" \
             "0:0:1:0:0:0:persona-index sentinel" \
             "0:0:0:1:0:0:weekly-onboarding-update cron" \
             "0:0:0:0:1:0:AGENTS.md dedup" \
             "0:0:0:0:0:1:UPDATE PENDING flag currency"; do
  IFS=':' read -r cc sop persona cron agents pending label <<< "$combo"
  OUT="$(run_gate "$cc" "$sop" "$persona" "$cron" "$agents" "$pending" 2>&1)"; RC=$?
  if echo "$OUT" | grep -q "GATE_FELL_THROUGH"; then
    ok "(gate) '${label}' outstanding -> falls through (does not exit 0)"
  else
    bad "(gate) '${label}' outstanding did NOT fall through (incorrectly fast-exited): $OUT"
  fi
  echo "$OUT" | grep -q "OUTSTANDING" && echo "$OUT" | grep -qF "$label" \
    && ok "(gate) names '${label}' in the OUTSTANDING message" \
    || bad "(gate) did not name '${label}' in the OUTSTANDING message: $OUT"
done

echo ""
echo "== Idempotency proof: a genuinely converged box still gets the fast exit =="
OUT="$(run_gate 0 0 0 0 0 0 2>&1)"; RC=$?
[ "$RC" -eq 0 ] && ! echo "$OUT" | grep -q "GATE_FELL_THROUGH" \
  && ok "(idempotency) re-running the gate on an all-converged box exits 0 again (stable, not a one-shot fluke)" \
  || bad "(idempotency) second run diverged: rc=$RC out=$OUT"

echo ""
echo "----------------------------------------"
echo "  PASS: $PASS    FAIL: $FAIL"
echo "----------------------------------------"
[ "$FAIL" -eq 0 ] || exit 1

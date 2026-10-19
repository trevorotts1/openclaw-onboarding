#!/usr/bin/env bash
# tests/unit/ghl-mcp-retirement-tool-retained.test.sh
#
# GHL-101 / defect B2 — the RETIREMENT TOOL must survive the install/roll.
#
# THE DEFECT. install.sh and update-skills.sh pruned every scripts/ghl-mcp-*.sh
# plus scripts/lib/ghl-mcp-paths.sh from the installed persistent scripts tree.
# update-skills.sh then deletes its source checkout ($TEMP_EXTRACT) at the end
# of the roll. On a source-less box the only remaining copy of the retirement
# tool was gone, so `bash <installed>/scripts/ghl-mcp-autostart.sh --retire`
# could no longer run — the operator's only recovery path after a failed
# migration.
#
# WHAT THIS TEST PROVES, and why none of it is a restatement:
#   A  Both REAL pruners (extracted verbatim from install.sh and
#      update-skills.sh between their markers, not reimplemented) leave the
#      retirement tool, scripts/lib/ghl-mcp-paths.sh and the digest primitive in
#      the destination, while still removing the resurrection surfaces.
#   B  A SOURCE-LESS installed tree — a copy outside the repo, with an empty
#      $HOME and no source checkout anywhere — runs --status, --retire --dry-run
#      and --dry-run with exit 0 and a real STATUS line. A "No such file or
#      directory" is a failure, not a skip.
#   C  NEGATIVE CONTROL: deleting the sourced dependency (lib/ghl-mcp-paths.sh)
#      makes the tool refuse with PATHS_LIB_MISSING. If the dependency were
#      optional, the test FAILS — that is the vacuity guard. A second control
#      deletes the tool itself and proves the harness sees a real missing file.
#
# HERMETIC: every supervisor is stubbed on a minimal PATH. `pm2` is deliberately
# NOT on that PATH — this test must never run `pm2 jlist`, which dumps process
# environments. Nothing outside a throwaway temp root is read or written.
#
# Exit 0 = every case behaved. Exit 1 = one or more did not.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
AUTOSTART="$REPO_ROOT/scripts/ghl-mcp-autostart.sh"
PATHS_LIB="$REPO_ROOT/scripts/lib/ghl-mcp-paths.sh"
DIGEST_TOOL="$REPO_ROOT/scripts/ghl-mcp-pin-digest.sh"
BASE="${GHL_MCP_RETAIN_TEST_ROOT:-${TMPDIR:-/tmp}/ghl-mcp-retain-test}"

PASS=0
FAIL=0
pass() { printf '  PASS: %s\n' "$1"; PASS=$((PASS + 1)); }
fail() { printf '  FAIL: %s\n' "$1" >&2; FAIL=$((FAIL + 1)); }

printf '=== ghl-mcp-retirement-tool-retained.test.sh (GHL-101 / B2) ===\n'

for f in "$INSTALL_SH" "$UPDATE_SH" "$AUTOSTART" "$PATHS_LIB" "$DIGEST_TOOL"; do
  [ -f "$f" ] || { printf '  FAIL: required file missing: %s\n' "$f" >&2; exit 1; }
done
bash -n "$INSTALL_SH" || { printf '  FAIL: install.sh does not parse\n' >&2; exit 1; }
bash -n "$UPDATE_SH"  || { printf '  FAIL: update-skills.sh does not parse\n' >&2; exit 1; }
bash -n "$AUTOSTART"  || { printf '  FAIL: %s does not parse\n' "$AUTOSTART" >&2; exit 1; }
bash -n "$PATHS_LIB"  || { printf '  FAIL: %s does not parse\n' "$PATHS_LIB" >&2; exit 1; }
pass 'all modified/delivered scripts parse (bash -n)'

mkdir -p "$BASE" || exit 1
WORK="$(mktemp -d "$BASE/case.XXXXXX")" || exit 1
trap 'rm -rf "$WORK"' EXIT

# _extract <file> <begin-marker> <end-marker> — the block is taken from the
# REAL file, so a future edit to the pruner is exercised here automatically.
_extract() {
  awk -v b="$2" -v e="$3" 'index($0,b){on=1;next} index($0,e){on=0} on' "$1"
}

_install_block() {
  _extract "$INSTALL_SH" '# >>> GHL-MCP-RETIREMENT-SCRIPTS-BEGIN' '# <<< GHL-MCP-RETIREMENT-SCRIPTS-END'
}
_update_fn() {
  _extract "$UPDATE_SH" '# >>> GHL-MCP-RETIREMENT-PRUNE-BEGIN' '# <<< GHL-MCP-RETIREMENT-PRUNE-END'
}

# ── dependency inventory (recursive) ────────────────────────────────────────
# The tool SOURCES the path library and EXECUTES the digest primitive. If either
# reference changes, the retained set in both installers must be re-reviewed.
if grep -q 'SELF_DIR/lib/ghl-mcp-paths.sh' "$AUTOSTART"; then
  pass 'retirement tool sources scripts/lib/ghl-mcp-paths.sh (hard dependency)'
else
  fail 'retirement tool no longer references SELF_DIR/lib/ghl-mcp-paths.sh — re-inventory its dependencies'
fi
if grep -q 'ghl-mcp-pin-digest.sh' "$AUTOSTART"; then
  pass 'retirement tool executes scripts/ghl-mcp-pin-digest.sh (dependency)'
else
  fail 'retirement tool no longer references ghl-mcp-pin-digest.sh — re-inventory its dependencies'
fi
# The path library must stay dependency-free: a second source in it would need
# retaining too, and nothing tells the installers about it.
if awk '{ sub(/#.*/, ""); print }' "$PATHS_LIB" | grep -Eq '(^|[[:space:];&|(])(source|\.)[[:space:]]+[^[:space:]]'; then
  fail 'scripts/lib/ghl-mcp-paths.sh now sources another file — add it to the retained set'
else
  pass 'path library has no further sourced dependencies'
fi

# ── A. the REAL pruners ─────────────────────────────────────────────────────
# A staging box carries the repo's scripts/ tree at <stage>/scripts, exactly as
# the whole-tree copy delivers it. install.sh's block resolves scripts from
# $SKILLS_DIR/../scripts, so SKILLS_DIR is <stage>/skills.
_stage_tree() {  # <stage>
  mkdir -p "$1/skills" "$1/platform/vps/36-ghl-mcp-setup-scripts"
  cp -Rp "$REPO_ROOT/scripts/." "$1/scripts/"
  printf '#!/bin/sh\nexit 0\n' > "$1/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
  chmod +x "$1/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh"
}

_assert_retained() {  # <scripts-root> <label>
  local root="$1" label="$2" rel
  for rel in ghl-mcp-autostart.sh lib/ghl-mcp-paths.sh ghl-mcp-pin-digest.sh; do
    if [ -f "$root/$rel" ]; then
      pass "$label retains $rel"
    else
      fail "$label REMOVED $rel — the retirement tool cannot run after the source checkout is deleted"
    fi
  done
}

_assert_pruned() {  # <scripts-root> <label>
  local root="$1" label="$2" rel
  for rel in ghl-mcp-probe.sh ghl-mcp-assert-runtime.sh ghl-mcp-check-pin-digest.sh \
             ghl-mcp-vet-pin.sh qc-assert-ghl-mcp-supervised.sh; do
    if [ -e "$root/$rel" ]; then
      fail "$label failed to prune resurrection surface $rel"
    else
      pass "$label prunes $rel"
    fi
  done
}

# A1 — install.sh's post-copy prune.
STAGE_I="$WORK/stage-install"
_stage_tree "$STAGE_I"
INSTALL_PRUNE="$(_install_block)"
if [ -z "$INSTALL_PRUNE" ]; then
  fail 'could not extract the GHL-MCP-RETIREMENT-SCRIPTS block from install.sh'
else
  (
    SKILLS_DIR="$STAGE_I/skills"
    note() { :; }
    warn() { printf 'WARN: %s\n' "$*" >&2; }
    eval "$INSTALL_PRUNE"
  ) || fail "install.sh prune block exited non-zero"
  _assert_retained "$STAGE_I/scripts" 'install.sh prune'
  _assert_pruned   "$STAGE_I/scripts" 'install.sh prune'
fi

# A2 — update-skills.sh's prune helper, called the way the roll calls it.
STAGE_U="$WORK/stage-update"
_stage_tree "$STAGE_U"
UPDATE_FN="$(_update_fn)"
if [ -z "$UPDATE_FN" ]; then
  fail 'could not extract the GHL-MCP-RETIREMENT-PRUNE helper from update-skills.sh'
else
  eval "$UPDATE_FN"
  if declare -F prune_retired_ghl_mcp_surfaces >/dev/null 2>&1; then
    prune_retired_ghl_mcp_surfaces "$STAGE_U/scripts" "$STAGE_U/platform" >/dev/null
    _assert_retained "$STAGE_U/scripts" 'update-skills prune'
    _assert_pruned   "$STAGE_U/scripts" 'update-skills prune'
    if [ -e "$STAGE_U/platform/vps/36-ghl-mcp-setup-scripts/start-ghl-mcp-server.sh" ]; then
      fail 'update-skills prune failed to remove the VPS start script'
    else
      pass 'update-skills prune removes the VPS start script'
    fi
  else
    fail 'extracted block did not define prune_retired_ghl_mcp_surfaces'
  fi
fi

# ── B. SOURCE-LESS installed tree ───────────────────────────────────────────
# The installed destination is a COPY: $OC_CONFIG/scripts. Nothing under $WORK
# is a git checkout, $HOME is empty, and the minimal PATH carries no source
# tree. This is the state a box is in after the updater deletes $TEMP_EXTRACT.
INSTALLED="$WORK/installed"
mkdir -p "$INSTALLED/scripts" "$WORK/home" "$WORK/data" "$WORK/logs" "$WORK/bin"
cp -Rp "$STAGE_I/scripts/." "$INSTALLED/scripts/"
TOOL="$INSTALLED/scripts/ghl-mcp-autostart.sh"

if [ -f "$TOOL" ]; then
  pass 'installed tree carries the retirement tool'
else
  fail 'installed tree has no retirement tool — cannot test a source-less box'
fi
if [ -e "$WORK/.git" ] || [ -d "$INSTALLED/.git" ] || [ -d "$WORK/home/.openclaw" ]; then
  fail 'scratch tree contains a checkout or a populated $HOME — the source-less case would be vacuous'
else
  pass 'scratch tree is source-less (no .git, empty $HOME)'
fi

# Stubs: deterministic, and NO pm2 (pm2 jlist dumps process environments).
mkdir -p "$WORK/bin"
_stub() {  # <name> <body>
  printf '#!/bin/sh\n%s\n' "$2" > "$WORK/bin/$1"
  chmod +x "$WORK/bin/$1"
}
_stub openclaw 'exit 0'
_stub crontab  'exit 1'
_stub lsof     'exit 1'
_stub pgrep    'exit 1'
_stub ps       'exit 0'
_stub systemctl 'case "$1" in is-enabled) echo disabled ;; is-active) echo inactive ;; esac; exit 0'
if [ -x "$WORK/bin/pm2" ]; then
  fail 'test PATH accidentally contains pm2'
fi
# The minimal PATH also guarantees pm2/launchctl from the operator's shell are
# unreachable, so this test cannot touch a real supervisor.
TOOL_PATH="$WORK/bin:/usr/bin:/bin"
unset PM2_HOME OPENCLAW_ROOT GHL_MCP_PATHS_LIB GHL_MCP_PIN_OVERRIDE

_run_tool() {  # <scripts-dir> <args...>
  local scripts_dir="$1"; shift
  env -u PM2_HOME -u OPENCLAW_ROOT -u GHL_MCP_PATHS_LIB \
      HOME="$WORK/home" PATH="$TOOL_PATH" \
      GHL_MCP_PLATFORM_OVERRIDE=linux-home \
      GHL_MCP_DATA_ROOT="$WORK/data/.openclaw" \
      GHL_MCP_DIR="$WORK/data/.openclaw/mcp-servers/ghl-community-mcp" \
      GHL_MCP_LOG_DIR_OVERRIDE="$WORK/logs" \
      bash "$scripts_dir/ghl-mcp-autostart.sh" "$@" 2>&1
}

# B1 — --status
OUT_STATUS="$(_run_tool "$INSTALLED/scripts" --status)"; RC_STATUS=$?
if [ "$RC_STATUS" -eq 0 ]; then
  pass 'source-less --status exits 0'
else
  fail "source-less --status exited $RC_STATUS (output: $OUT_STATUS)"
fi
case "$OUT_STATUS" in
  *"STATUS: ghl-mcp-autostart="*) pass 'source-less --status prints a real STATUS line' ;;
  *) fail "source-less --status printed no STATUS line (output: $OUT_STATUS)" ;;
esac
case "$OUT_STATUS" in
  *PATHS_LIB_MISSING*|*"No such file"*)
    fail "source-less --status reports a missing file: $OUT_STATUS" ;;
  *) pass 'source-less --status resolved every dependency' ;;
esac
case "$OUT_STATUS" in
  *RETIRED_VERIFIED_OFF*|*SERVICE_PRESENT*) pass 'source-less --status reaches a real retirement verdict' ;;
  *) fail "source-less --status reached no verdict (output: $OUT_STATUS)" ;;
esac

# B2 — the documented dry run (--retire --dry-run). It prints the retirement
# plan, or the already-retired verdict; either is real output from the tool.
OUT_DRY="$(_run_tool "$INSTALLED/scripts" --retire --dry-run)"; RC_DRY=$?
if [ "$RC_DRY" -eq 0 ]; then
  pass 'source-less --retire --dry-run exits 0'
else
  fail "source-less --retire --dry-run exited $RC_DRY (output: $OUT_DRY)"
fi
case "$OUT_DRY" in
  *RETIRE_DRY_RUN*|*RETIRED_VERIFIED_OFF*) pass 'source-less --retire --dry-run prints a real plan/verdict' ;;
  *) fail "source-less --retire --dry-run printed no plan/verdict (output: $OUT_DRY)" ;;
esac
case "$OUT_DRY" in
  *PATHS_LIB_MISSING*|*"No such file"*)
    fail "source-less --retire --dry-run reports a missing file: $OUT_DRY" ;;
  *) pass 'source-less --retire --dry-run resolved every dependency' ;;
esac

# B3 — the bare --dry-run flag named in the defect report. Start mode is
# RETIRED: with no pin delivered it reports PIN_UNVERIFIED (by W07 design) and
# MUST still exit 0 with a well-formed STATUS line rather than a shell error.
OUT_BARE="$(_run_tool "$INSTALLED/scripts" --dry-run)"; RC_BARE=$?
if [ "$RC_BARE" -eq 0 ]; then
  pass 'source-less --dry-run exits 0'
else
  fail "source-less --dry-run exited $RC_BARE (output: $OUT_BARE)"
fi
case "$OUT_BARE" in
  *"STATUS: ghl-mcp-autostart="*) pass 'source-less --dry-run prints a well-formed STATUS line' ;;
  *) fail "source-less --dry-run printed no STATUS line (output: $OUT_BARE)" ;;
esac
case "$OUT_BARE" in
  *"No such file"*) fail "source-less --dry-run hit a missing file: $OUT_BARE" ;;
  *) pass 'source-less --dry-run was not a file-not-found failure' ;;
esac

# ── C. NEGATIVE CONTROLS (vacuity guards) ───────────────────────────────────
# C1 — delete the SOURCED dependency. The tool MUST refuse and name it. If it
# still produced a verdict, the "dependency" was not a dependency and B proves
# nothing.
NEG_LIB="$WORK/neg-lib"
cp -Rp "$STAGE_I/scripts" "$NEG_LIB"
rm -f "$NEG_LIB/lib/ghl-mcp-paths.sh"
OUT_NEG="$(_run_tool "$NEG_LIB" --status)"; RC_NEG=$?
case "$OUT_NEG" in
  *PATHS_LIB_MISSING*) pass 'negative control: deleting lib/ghl-mcp-paths.sh makes the tool refuse' ;;
  *) fail "negative control FAILED: tool still ran without its library (rc=$RC_NEG, output: $OUT_NEG)" ;;
esac
case "$OUT_NEG" in
  *RETIRED_VERIFIED_OFF*|*SERVICE_PRESENT*)
    fail 'negative control FAILED: a verdict was produced with the dependency deleted — the test is vacuous' ;;
  *) pass 'negative control: no retirement verdict without the dependency' ;;
esac

# C2 — delete the tool itself. This is the exact pre-fix failure mode; the
# harness must observe it as a real missing file.
NEG_TOOL="$WORK/neg-tool"
cp -Rp "$STAGE_I/scripts" "$NEG_TOOL"
rm -f "$NEG_TOOL/ghl-mcp-autostart.sh"
OUT_NOTOOL="$(env HOME="$WORK/home" PATH="$TOOL_PATH" bash "$NEG_TOOL/ghl-mcp-autostart.sh" --status 2>&1)"; RC_NOTOOL=$?
if [ "$RC_NOTOOL" -ne 0 ] && printf '%s' "$OUT_NOTOOL" | grep -q 'No such file'; then
  pass 'negative control: a pruned tool is observed as a real missing file'
else
  fail "negative control FAILED: deleting the tool was not detected (rc=$RC_NOTOOL, output: $OUT_NOTOOL)"
fi

printf '\n=== %d passed, %d failed ===\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0

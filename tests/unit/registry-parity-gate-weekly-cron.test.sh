#!/usr/bin/env bash
# tests/unit/registry-parity-gate-weekly-cron.test.sh
# ---------------------------------------------------------------------------
# R0 -- proves the registry-parity gate wired into scripts/setup-weekly-
# update.sh's GENERATED Saturday cron script (.openclaw-self-update) actually
# catches the strip class, on the entry point that matters most: this is the
# ONE cron that changes a box's OpenClaw BINARY version, unattended, at
# 23:59 every Saturday.
#
# METHOD: extract the OCUPDATE_EOF heredoc body VERBATIM (the generated
# script itself, not a paraphrase of it) from setup-weekly-update.sh, then
# extract the registry-parity function definitions from THAT extracted body
# by brace-matching, and source them. If the heredoc markers or function
# shapes drift, this suite fails loudly (exit 2) rather than testing stale
# copies. Same technique as tests/unit/registry-parity-gate.test.sh
# (update-skills.sh's own copy of this gate) and
# tests/unit/content-recheck-convergence-probes.test.sh.
#
# FULLY OFFLINE. HOME is redirected into a throwaway sandbox for every test.
# ---------------------------------------------------------------------------
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SETUP_SCRIPT="$REPO_ROOT/scripts/setup-weekly-update.sh"

[ -f "$SETUP_SCRIPT" ] || { echo "FATAL: $SETUP_SCRIPT not found"; exit 2; }
if [ -z "${BASH_VERSION:-}" ]; then echo "FATAL: not running under bash"; exit 2; fi
echo "Running under BASH_VERSION=$BASH_VERSION (asserted, not assumed)"

PASS=0
FAIL=0
ok()  { PASS=$((PASS+1)); echo "  ✓ $1"; }
bad() { FAIL=$((FAIL+1)); echo "  ✗ $1"; }

WORK="$(mktemp -d -t weekly-cron-parity-test-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

# --- Step 1: extract the generated inner script VERBATIM, between the
#     `<< 'OCUPDATE_EOF'` opener and the bare `OCUPDATE_EOF` terminator. ---
INNER="$WORK/openclaw-self-update.sh"
awk '
  /<< .OCUPDATE_EOF.$/ { p=1; next }
  p && $0 == "OCUPDATE_EOF" { exit }
  p { print }
' "$SETUP_SCRIPT" > "$INNER"
if [ ! -s "$INNER" ]; then
  echo "FATAL: could not extract the OCUPDATE_EOF heredoc body from $SETUP_SCRIPT (marker drift?)"
  exit 2
fi
echo "Extracted generated inner script: $(wc -l < "$INNER" | tr -d ' ') lines -> $INNER"
/bin/bash -n "$INNER" || { echo "FATAL: extracted inner script fails bash -n -- not a valid test target"; exit 2; }

# --- Step 2: extract just the registry-parity function definitions from the
#     inner script, by brace-matching, same technique as the update-skills.sh
#     suite. Global-variable style (no `local`) matches this file's own
#     convention -- it is a flat generated cron script, not a function
#     library. ---
extract_function() {
  awk -v fn="$1() {" '
    $0 == fn { p=1 }
    p { print }
    p && $0 == "}" { exit }
  ' "$INNER"
}
FUNCS="oc_registry_snapshot oc_registry_dir_count oc_registry_parity_check"
GATE="$WORK/gate.inc"
: > "$GATE"
for fn in $FUNCS; do
  out="$(extract_function "$fn")"
  if [ -z "$out" ]; then
    echo "FATAL: function '$fn() {' not found verbatim in the extracted inner script (drift?)"
    exit 2
  fi
  printf '%s\n' "$out" >> "$GATE"
  echo >> "$GATE"
done
echo "Extracted ${#FUNCS} functions totalling $(wc -l < "$GATE" | tr -d ' ') lines"

# ---------------------------------------------------------------------------
# fixture builders (same shape as the update-skills.sh suite)
# ---------------------------------------------------------------------------
new_sandbox() {
  local tag="$1" ids_csv="$2" dirnames_csv="$3" sbx cfgfile IFS_OLD id d first
  sbx="$WORK/sbx-$tag"
  mkdir -p "$sbx/.openclaw/agents"
  cfgfile="$sbx/.openclaw/openclaw.json"
  {
    printf '{"agents":{"list":['
    IFS_OLD="$IFS"; IFS=','
    first=1
    for id in $ids_csv; do
      IFS="$IFS_OLD"
      [ -z "$id" ] && continue
      [ "$first" = 1 ] || printf ','
      printf '{"id":"%s"}' "$id"
      first=0
      IFS=','
    done
    IFS="$IFS_OLD"
    printf ']}}'
  } > "$cfgfile"
  IFS_OLD="$IFS"; IFS=','
  for d in $dirnames_csv; do
    IFS="$IFS_OLD"
    [ -z "$d" ] && continue
    mkdir -p "$sbx/.openclaw/agents/$d"
    IFS=','
  done
  IFS="$IFS_OLD"
  printf '%s' "$sbx"
}

run_pair() {
  # run_pair <pre-sandbox> <post-sandbox> -- runs oc_registry_parity_check
  # pre then post in ONE subshell (globals persist), exactly how the real
  # generated script runs them (same process, before/after `npm update`).
  local pre_sbx="$1" post_sbx="$2"
  (
    HOME="$pre_sbx"; export HOME
    OC_CFG="$HOME/.openclaw/openclaw.json"
    OC_AGENTS_DIR="$HOME/.openclaw/agents"
    OC_LOG="$WORK/oc.log"
    OC_GATE_BLOCK=""
    # shellcheck disable=SC1090
    source "$GATE"
    echo "--pre--"
    oc_registry_parity_check pre
    echo "pre RC=$? GATE_BLOCK=[${OC_GATE_BLOCK:-}]"
    HOME="$post_sbx"; export HOME
    OC_CFG="$HOME/.openclaw/openclaw.json"
    OC_AGENTS_DIR="$HOME/.openclaw/agents"
    OC_GATE_BLOCK=""
    echo "--post--"
    oc_registry_parity_check post
    echo "RC=$? GATE_BLOCK=[${OC_GATE_BLOCK:-}]"
  ) 2>&1
}

# ---------------------------------------------------------------------------
# SCENARIO A (CONTROL): healthy, unchanged.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO A: healthy box, unchanged (CONTROL) ==="
rm -f "$WORK/oc.log"
h="$(new_sandbox healthy "main,dept-sales,dept-support,dept-content" "main,dept-sales,dept-support,dept-content")"
out="$(run_pair "$h" "$h")"
echo "$out" | sed 's/^/    /'
# The per-run "no loss" line is written to $OC_LOG (>>), not stdout/stderr --
# matching the real generated script, which logs to a file, not the console.
# Check both: the returned RC/GATE_BLOCK pair AND the log's own record.
if printf '%s' "$out" | grep -q "RC=0 GATE_BLOCK=\[\]" && grep -q "no loss: pre=4 post=4" "$WORK/oc.log" 2>/dev/null; then
  ok "healthy unchanged box: no violation, 'no loss' logged to \$OC_LOG"
else
  bad "healthy unchanged box: expected clean pass (see $WORK/oc.log)"
fi

# ---------------------------------------------------------------------------
# SCENARIO B (ASSERTION): already stripped before this cron ever runs.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO B: registry already stripped before this cron runs (ASSERTION) ==="
s="$(new_sandbox stripped "main" "main,dept-sales,dept-support,dept-content")"
out="$(
  (
    HOME="$s"; export HOME
    OC_CFG="$HOME/.openclaw/openclaw.json"
    OC_AGENTS_DIR="$HOME/.openclaw/agents"
    OC_LOG="$WORK/oc.log"
    OC_GATE_BLOCK=""
    # shellcheck disable=SC1090
    source "$GATE"
    oc_registry_parity_check pre
    echo "RC=$? GATE_BLOCK=[${OC_GATE_BLOCK:-}]"
  ) 2>&1
)"
echo "$out" | sed 's/^/    /'
if printf '%s' "$out" | grep -q "RC=78" && printf '%s' "$out" | grep -q "ABSOLUTE FLOOR"; then
  ok "already-stripped box: pre check refuses (rc=78) with ABSOLUTE FLOOR -- this cron would NOT have run npm update"
else
  bad "already-stripped box: expected rc=78 + ABSOLUTE FLOOR"
fi

# ---------------------------------------------------------------------------
# SCENARIO C (ASSERTION): the strip happens DURING the binary upgrade window
# -- pre healthy, post stripped. This is the exact incident-shape scenario:
# the check that fires AFTER `npm update -g openclaw` has already run.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO C: strip during the upgrade window, pre healthy / post stripped (ASSERTION) ==="
preC="$(new_sandbox preC "main,dept-sales,dept-support,dept-content" "main,dept-sales,dept-support,dept-content")"
postC="$(new_sandbox postC "main" "main,dept-sales,dept-support,dept-content")"
out="$(run_pair "$preC" "$postC")"
echo "$out" | sed 's/^/    /'
if printf '%s' "$out" | grep -q "RC=78" ; then
  ok "strip during upgrade window: post check refuses (rc=78) -- fires as a post-hoc alarm since npm has already run"
else
  bad "strip during upgrade window: expected rc=78 on post"
fi

# ---------------------------------------------------------------------------
# SCENARIO D (ASSERTION, regression-only): partial loss below the floor.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO D: partial loss below the absolute floor (ASSERTION, regression-only) ==="
preD="$(new_sandbox preD "main,dept-sales,dept-support,dept-content" "main,dept-sales,dept-support,dept-content")"
postD="$(new_sandbox postD "main,dept-sales" "main,dept-sales,dept-support,dept-content")"
out="$(run_pair "$preD" "$postD")"
echo "$out" | sed 's/^/    /'
if printf '%s' "$out" | grep -q "RC=78" && printf '%s' "$out" | grep -q "REGRESSION"; then
  ok "partial loss (4->2, dircount unchanged) refused via REGRESSION"
else
  bad "partial loss: expected rc=78 + REGRESSION"
fi

# ---------------------------------------------------------------------------
# SCENARIO E (MUTATION PROOF): disable the absolute-floor condition, re-run
# Scenario B. Must flip the same bad case from refused to silently passed.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO E: MUTATION PROOF -- disable the absolute-floor check, re-run Scenario B ==="
sed 's/if \[ "\$count" -le 1 \] \&\& \[ "\$dircount" -gt 2 \]; then/if false; then/' "$GATE" > "$WORK/gate.mutated.inc"
if diff -q "$GATE" "$WORK/gate.mutated.inc" >/dev/null 2>&1; then
  echo "FATAL: mutation sed made no change -- the targeted condition text has drifted"
  exit 2
fi
out="$(
  (
    HOME="$s"; export HOME   # the Scenario B already-stripped sandbox
    OC_CFG="$HOME/.openclaw/openclaw.json"
    OC_AGENTS_DIR="$HOME/.openclaw/agents"
    OC_LOG="$WORK/oc.log"
    OC_GATE_BLOCK=""
    # shellcheck disable=SC1090
    source "$WORK/gate.mutated.inc"
    oc_registry_parity_check pre
    echo "RC=$? GATE_BLOCK=[${OC_GATE_BLOCK:-}]"
  ) 2>&1
)"
echo "$out" | sed 's/^/    /'
if printf '%s' "$out" | grep -q "RC=0 GATE_BLOCK=\[\]"; then
  ok "MUTATION PROOF: with the absolute-floor check disabled, the same already-stripped box now silently passes -- confirms the Scenario B rc=78 is the real check enforcing, not incidental"
else
  bad "MUTATION PROOF FAILED: disabling the check should have flipped Scenario B to a clean pass"
fi

# ---------------------------------------------------------------------------
# SCENARIO F (CONTROL): malformed config -> UNDETERMINED, never a false pass.
# ---------------------------------------------------------------------------
echo ""
echo "=== SCENARIO F: malformed config is UNDETERMINED, not a false pass (CONTROL) ==="
rm -f "$WORK/oc.log"
m="$WORK/sbx-malformed"
mkdir -p "$m/.openclaw/agents"
printf '{not valid json' > "$m/.openclaw/openclaw.json"
out="$(run_pair "$m" "$m")"
echo "$out" | sed 's/^/    /'
skipped_count="$(grep -c "count checks SKIPPED" "$WORK/oc.log" 2>/dev/null || echo 0)"
if printf '%s' "$out" | grep -q "RC=0" && [ "$skipped_count" -ge 2 ] && ! grep -q "no loss" "$WORK/oc.log" 2>/dev/null; then
  ok "malformed config: UNDETERMINED, count checks explicitly skipped both phases (x$skipped_count) in \$OC_LOG, never 'no loss'"
else
  bad "malformed config: expected explicit skip (x2) in \$OC_LOG, never a false 'no loss' (see $WORK/oc.log)"
fi

echo ""
echo "============================================================"
echo "RESULT: $PASS passed, $FAIL failed"
echo "============================================================"
[ "$FAIL" -eq 0 ]

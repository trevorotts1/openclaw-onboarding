#!/usr/bin/env bash
# bootstrap-compact-weekly.sh — the weekly compaction run for ONE box.
#
# Runs scripts/compact-bootstrap.py across EVERY workspace this box declares in
# openclaw.json, then re-verifies every pointer and every ledgered block.
#
# WHY IT EXISTS. bootstrap-validate-daily.sh MEASURES: it reports a file that has
# grown past its lean target and exits non-zero. Nothing acts on that. This is
# the acting half — the one job that moves owner-authored cold content out to the
# reference root verbatim and leaves a four-line pointer behind. It only acts
# when a file is genuinely over its target; under target it measures and stops.
#
# ZERO MODEL TOKENS. This is a COMMAND cron, not an agent cron. It runs pure
# shell and python3, so no model is invoked and no message is delivered to any
# chat. NOTHING here hardcodes a model name. The box's configured default is read
# from agents.defaults.model purely so the log line says which model WOULD run if
# an operator ever converts this to an agent job — the value is reported, never
# assumed and never substituted for.
#
# THE SWITCH (see docs/COMPACT-CORE-SOP.md §12). Resolution order, first wins:
#   1. $OPENCLAW_BOOTSTRAP_COMPACT_MODE
#   2. $OC_CONFIG/bootstrap-compact.conf          (one word)
#   3. agents.defaults.bootstrapCompactMode in openclaw.json
#   4. "report"                                   (repo default)
# report = run the plan and print it, write NOTHING. apply = perform the plan.
# The default is deliberately report so a box's first scheduled week produces a
# reviewable plan rather than a surprise edit; an operator flips it to apply.
# An unrecognised value is treated as report and warns, because honouring a typo
# as "apply" would write to a bootstrap file nobody authorised.
#
# PLATFORM. Same detection block every other script in this repo uses:
#   VPS  (/data/.openclaw exists) -> /data/.openclaw
#   Mac / container (default)     -> $HOME/.openclaw
# Override with OC_ROOT / OC_CONFIG. Workspaces and the reference root are
# resolved by compact-bootstrap.py itself, from config and platform — never
# hardcoded here.
#
# Usage: bootstrap-compact-weekly.sh [--quiet] [--mode report|apply] [extra args]

set -o pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

QUIET=0
MODE_ARG=""
ARGS=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1 ;;
    --mode) MODE_ARG="${2:-}"; shift ;;
    --mode=*) MODE_ARG="${1#--mode=}" ;;
    *) ARGS+=("$1") ;;
  esac
  shift
done

# ── Platform resolution ──────────────────────────────────────────────────────
if [ -z "${OC_ROOT:-}" ]; then
  if [ -d /data/.openclaw ]; then OC_ROOT="/data/.openclaw"
  else OC_ROOT="$HOME/.openclaw"; fi
fi
CONFIG="${OC_CONFIG:-$OC_ROOT/openclaw.json}"
ENGINE="${COMPACT_ENGINE:-$SCRIPT_DIR/compact-bootstrap.py}"

say() { [ "$QUIET" -eq 1 ] || echo "$@"; }

say "=== bootstrap-compact-weekly.sh :: $(date '+%Y-%m-%d %H:%M:%S %Z') ==="

if [ ! -f "$ENGINE" ]; then
  echo "FATAL: compaction engine not found at $ENGINE" >&2
  exit 2
fi
command -v python3 >/dev/null 2>&1 || { echo "FATAL: python3 not on PATH" >&2; exit 2; }

# ── A small config reader. python3 only: jq is ABSENT in the Contabo container. ─
_read_cfg() {
  CONFIG="$CONFIG" KEY="$1" python3 - <<'PYEOF' 2>/dev/null || true
import json, os
try:
    d = json.load(open(os.environ["CONFIG"], encoding="utf-8"))
    v = d.get("agents", {}).get("defaults", {}).get(os.environ["KEY"])
    print(v if isinstance(v, str) else "")
except Exception:
    print("")
PYEOF
}

# ── The switch ───────────────────────────────────────────────────────────────
RAW_MODE=""
SOURCE=""
if [ -n "$MODE_ARG" ]; then
  RAW_MODE="$MODE_ARG"; SOURCE="--mode"
elif [ -n "${OPENCLAW_BOOTSTRAP_COMPACT_MODE:-}" ]; then
  RAW_MODE="$OPENCLAW_BOOTSTRAP_COMPACT_MODE"; SOURCE="OPENCLAW_BOOTSTRAP_COMPACT_MODE"
elif [ -s "$OC_ROOT/bootstrap-compact.conf" ]; then
  RAW_MODE="$(head -n1 "$OC_ROOT/bootstrap-compact.conf" 2>/dev/null | tr -d '[:space:]')"
  SOURCE="$OC_ROOT/bootstrap-compact.conf"
else
  RAW_MODE="$(_read_cfg bootstrapCompactMode)"
  [ -n "$RAW_MODE" ] && SOURCE="agents.defaults.bootstrapCompactMode"
fi

case "${RAW_MODE:-}" in
  apply)      MODE="apply" ;;
  report|'')  MODE="report"; [ -n "$SOURCE" ] || SOURCE="repo default" ;;
  *)
    MODE="report"
    echo "  [compact-weekly] WARN: unrecognised mode '$RAW_MODE' from $SOURCE — using report" >&2
    SOURCE="repo default (after an unrecognised value)"
    ;;
esac

# The box's configured default model. REPORTED, never applied: this job spends
# zero model tokens. It is printed so that anyone converting this to an agent job
# uses the box's own default instead of pasting a model name into a script.
BOX_MODEL="$(_read_cfg model)"

say "Config:        $CONFIG"
say "Mode:          $MODE (from $SOURCE)"
say "Box default model (reported only, unused — this job spends zero model tokens): ${BOX_MODEL:-UNSET}"
say ""

WORKSPACES="$(python3 "$ENGINE" --list-workspaces 2>/dev/null || true)"
if [ -z "$WORKSPACES" ]; then
  echo "FAIL: no workspace resolved from $CONFIG — nothing was checked" >&2
  exit 2
fi
say "Workspaces this box declares:"
say "$WORKSPACES" | sed 's/^/  /'
say ""

# ── The run ──────────────────────────────────────────────────────────────────
RUN_FLAG="--dry-run"
[ "$MODE" = "apply" ] && RUN_FLAG="--apply"

RC=0
python3 "$ENGINE" "$RUN_FLAG" ${ARGS[@]+"${ARGS[@]}"} || RC=$?
say ""

# --apply runs the verification itself. In report mode run it explicitly, so the
# weekly job always ends on a fresh pointer + ledger verdict either way.
if [ "$MODE" != "apply" ]; then
  CHECK_RC=0
  python3 "$ENGINE" --check ${ARGS[@]+"${ARGS[@]}"} || CHECK_RC=$?
  [ "$CHECK_RC" -ne 0 ] && RC="$CHECK_RC"
fi

say ""
say "=== done, mode=$MODE exit=$RC ==="
exit "$RC"

#!/usr/bin/env bash
# qc-assert-provider-timeouts.sh — v1.0.0
#
# STATIC QC INVARIANT: fails the build when a configured LLM provider carries
# NO `timeoutSeconds` key.
#
# EVIDENCE THIS PREVENTS: a provider missing `timeoutSeconds` silently falls
# back to the gateway's 120s default. Against a thinking-model primary that
# produced `LLM idle timeout (120s)`, `FailoverError: LLM request timed out`,
# `durationMs=122368`, and stuck-session aborts on an affected box — while the
# gateway itself reported healthy throughout.
#
# ⚠️ CRITICAL DESIGN POINT: the fault was an ABSENT key, not an inconsistent
# value. A detector that only compares values ACROSS providers never sees a
# key that isn't there at all — that is exactly how this hid. This gate
# therefore asserts PRESENCE first, per provider, before it ever looks at the
# value:
#   FAIL — `timeoutSeconds` key is ABSENT from a provider entry
#   WARN — present but < 600 (box-dependent; not fatal, some boxes run 300)
#   PASS — present and >= 600
#
# ⚠️ The absent-config-file / absent-`models.providers` case is NOT the same
# as "checked and found clean" — reporting a bare PASS there would be a false
# all-clear (empty result reads as "no problem found"). This gate reports
# UNDETERMINED instead, with the reason, and exits with a DISTINCT code (3) —
# never 0. A missing instrument must never look like a clean sweep.
#
# READ-ONLY: this is an assertion, not a fixer. It never writes or modifies
# anything. (The fixer counterpart — fills the gap to 600s when the key is
# absent, never overwrites an operator's explicit value — is
# scripts/apply-fleet-standards.sh's PROVIDER timeoutSeconds FLOOR block.)
#
# Config resolution (first that applies wins):
#   1. an explicit path passed as $1
#   2. $SMOKE_OC_CONFIG (parity with the other provider gates in this family:
#      qc-assert-provider-capability-invariants.sh,
#      qc-assert-ollama-provider-platform.sh)
#   3. a repo-relative fixture path suitable for CI
#      (tests/fixtures/qc-assert-provider-timeouts/openclaw.json). CI has no
#      live box config, so this is intentionally the LAST resort, not a box
#      path — and its absence by default is expected to produce UNDETERMINED,
#      not a silent skip.
#
# Exit codes:
#   0  — checked: every provider has timeoutSeconds and none is < 600 (PASS;
#        WARNs may still have printed and do not change this)
#   1  — checked: at least one provider is MISSING timeoutSeconds (FAIL)
#   2  — usage error
#   3  — UNDETERMINED: the instrument itself is absent (config file not
#        found, unreadable, unparseable, or models.providers missing / not an
#        object) — this NEVER collapses into exit 0
#
# Usage:
#   bash scripts/qc-assert-provider-timeouts.sh
#   bash scripts/qc-assert-provider-timeouts.sh /path/to/openclaw.json
#   bash scripts/qc-assert-provider-timeouts.sh --quiet
#   SMOKE_OC_CONFIG=/path/to/openclaw.json bash scripts/qc-assert-provider-timeouts.sh
#
# Wired in:
#   Not yet wired into scripts/qc-system-integrity.sh — this is a new gate;
#   wiring it in is a separate change.

set -uo pipefail

QUIET=0
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG_ARG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1; shift ;;
    -h|--help)
      sed -n '1,54p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    --*) echo "Unknown arg: $1" >&2; exit 2 ;;
    *)
      if [ -n "$CONFIG_ARG" ]; then
        echo "Unknown arg: $1" >&2
        exit 2
      fi
      CONFIG_ARG="$1"
      shift
      ;;
  esac
done

_pass() { [ "$QUIET" = "0" ] && printf '[qc-provider-timeouts] PASS  %s\n' "$*"; }
_fail() { printf '[qc-provider-timeouts] FAIL  %s\n' "$*" >&2; }
_warn() { printf '[qc-provider-timeouts] WARN  %s\n' "$*" >&2; }
_info() { [ "$QUIET" = "0" ] && printf '[qc-provider-timeouts] INFO  %s\n' "$*"; }
_undetermined() { printf '[qc-provider-timeouts] UNDETERMINED  %s\n' "$*" >&2; }

FIXTURE_DEFAULT="$REPO_ROOT/tests/fixtures/qc-assert-provider-timeouts/openclaw.json"

OC_CONFIG="$CONFIG_ARG"
[ -z "$OC_CONFIG" ] && OC_CONFIG="${SMOKE_OC_CONFIG:-}"
[ -z "$OC_CONFIG" ] && OC_CONFIG="$FIXTURE_DEFAULT"

_info "config: $OC_CONFIG"

if [ ! -f "$OC_CONFIG" ]; then
  _undetermined "config file not found: $OC_CONFIG — the provider timeoutSeconds invariant DID NOT RUN. This is not a pass: no provider was inspected."
  exit 3
fi

# ─── Read-only single-pass analysis ──────────────────────────────────────────
ANALYSIS="$(python3 - "$OC_CONFIG" <<'PYEOF'
import json
import sys

path = sys.argv[1]

try:
    with open(path, encoding='utf-8') as fh:
        cfg = json.load(fh)
except Exception as e:
    print(f'UNDETERMINED|cannot parse {path} as JSON: {e}')
    sys.exit(0)

if not isinstance(cfg, dict):
    print(f'UNDETERMINED|{path} does not contain a JSON object at the top level')
    sys.exit(0)

models = cfg.get('models')
if not isinstance(models, dict):
    print(f'UNDETERMINED|models is missing or not an object in {path}')
    sys.exit(0)

providers = models.get('providers')
if not isinstance(providers, dict):
    print(f'UNDETERMINED|models.providers is missing or not an object in {path}')
    sys.exit(0)

if not providers:
    print('CHECKED_EMPTY|0 providers configured under models.providers')
    sys.exit(0)

for name, prov in sorted(providers.items()):
    if not isinstance(prov, dict):
        print(f'FAIL|{name}|provider entry is not an object ({type(prov).__name__}) — cannot verify timeoutSeconds')
        continue
    if 'timeoutSeconds' not in prov:
        print(f'FAIL|{name}|timeoutSeconds key is ABSENT — falls back to the gateway 120s default')
        continue
    val = prov['timeoutSeconds']
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        print(f'FAIL|{name}|timeoutSeconds is present but not numeric ({val!r})')
        continue
    if val < 600:
        print(f'WARN|{name}|timeoutSeconds={val} (< 600; box-dependent, not fatal)')
    else:
        print(f'PASS|{name}|timeoutSeconds={val}')
PYEOF
)"
PY_RC=$?
if [ "$PY_RC" -ne 0 ]; then
  echo "[qc-provider-timeouts] usage error: python3 analysis failed (rc=$PY_RC)" >&2
  exit 2
fi

if [ -z "$ANALYSIS" ]; then
  _undetermined "python3 analysis produced no output for $OC_CONFIG — treating as instrument-absent rather than a silent pass."
  exit 3
fi

FAILURES=0
WARNINGS=0
CHECKED=0

while IFS='|' read -r kind a b; do
  [ -z "$kind" ] && continue
  case "$kind" in
    UNDETERMINED)
      _undetermined "$a"
      exit 3
      ;;
    CHECKED_EMPTY)
      _info "$a"
      ;;
    FAIL)
      _fail "provider '$a' — $b"
      FAILURES=$((FAILURES + 1))
      CHECKED=$((CHECKED + 1))
      ;;
    WARN)
      _warn "provider '$a' — $b"
      WARNINGS=$((WARNINGS + 1))
      CHECKED=$((CHECKED + 1))
      ;;
    PASS)
      _pass "provider '$a' — $b"
      CHECKED=$((CHECKED + 1))
      ;;
  esac
done <<< "$ANALYSIS"

if [ "$FAILURES" -gt 0 ]; then
  _fail "$FAILURES of $CHECKED provider(s) have NO timeoutSeconds key — each one falls back to the 120s gateway default. Against a thinking-model primary this produces 'LLM idle timeout (120s)' / FailoverError / stuck-session aborts while the gateway itself still reports healthy."
  echo "REMEDY: set timeoutSeconds explicitly on every provider (>= 600 recommended)." >&2
  exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
  _info "$WARNINGS provider(s) set timeoutSeconds below 600 (WARN, non-blocking, box-dependent)."
fi

_pass "$CHECKED provider(s) checked — every provider that has a timeoutSeconds key is present, and none is missing it."
exit 0

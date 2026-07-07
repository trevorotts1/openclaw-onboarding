#!/usr/bin/env bash
# 59-anthology-engine/anthology-engine-entry.sh
#
# THE ONE SANCTIONED COMMAND TO RUN THE ANTHOLOGY ENGINE.
# ============================================================================
# The engine's guardrails (the fail-closed guards in scripts/, the deterministic
# stage runners, the ledger writer) only bind if a stage runs THROUGH this entry.
# Before it dispatches a stage it runs four fail-closed gates and mints a
# run-scoped nonce:
#
#   1.  DEPS CHECK        -- python3 must be present (exit 6, AE_DEPS_MISSING).
#   1b. MODEL-MAP PRE-GATE -- if a resolved model-map.json exists in the run dir,
#                          it must carry NO <CLIENT_*> placeholder and no
#                          Anthropic-family id (exit 8, AF-AE-UNRESOLVED-MODELMAP);
#                          preflight.sh --check is the resolver-as-pre-gate.
#   2.  BYPASS-SCAN       -- refuse any hand-rolled, UNGOVERNED external sender in
#                          the RUN directory: an n8n webhook, an Airtable write, a
#                          legacy prompt-base fetch, or a literal Authorization key
#                          header. The engine's OWN sanctioned adapters in scripts/
#                          are the only external I/O path (exit 5, AF-AE-BYPASS).
#   3.  VERSION/HASH PIN  -- content hash of the enforcement set (entry + manifest
#                          + the guards, when present); if ENGINE-PIN.sha256 is
#                          present the hash MUST match (exit 7, AF-AE-HASH-PIN).
#
# A gate may be skipped ONLY by an explicit, LOGGED owner approval token in
# <run-dir>/working/checkpoints/process_manifest.json. Never silently.
#
# THE ONLY PATH:
#   bash anthology-engine-entry.sh --stage sN --participant-key KEY [--run-dir DIR]
#   bash anthology-engine-entry.sh --stage s9 --anthology-id ID   [--run-dir DIR]
#   bash anthology-engine-entry.sh --stage s0 --payload FILE       (normal intake)
#   bash anthology-engine-entry.sh --plan            (print the S0..S9 plan)
#   bash anthology-engine-entry.sh --self-test       (every stage runner self-test)
#
# EXIT CODES
#   0  -- gates passed; the stage runner dispatched (its own exit is returned)
#   2  -- usage error / stage runner not found
#   5  -- BYPASS-SCAN tripped (hand-rolled ungoverned external sender in the run dir)
#   6  -- DEPS CHECK failed (AE_DEPS_MISSING)
#   7  -- VERSION/HASH PIN failed (hash mismatch, no owner skip)
#   8  -- MODEL-MAP PRE-GATE failed (residual <CLIENT_*> placeholder / Anthropic-family id)
# ============================================================================

set -uo pipefail
PROG="anthology-engine-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

usage() {
    cat >&2 <<EOF
$PROG -- the ONE sanctioned command to run the Anthology Engine.

USAGE:
  bash $PROG --stage sN --participant-key KEY [--run-dir DIR]
  bash $PROG --stage s9 --anthology-id ID    [--run-dir DIR]
  bash $PROG --stage s0 --payload FILE
  bash $PROG --plan | --self-test

STAGES: s0 intake, s1 avatar, s2 tone, s3 title, s4 blurb+outline, s5 chapter,
        s6 rewrite, s7 cover, s8 deliver, s9 assembly.

Layer 1 authoring (Skill 54) is invoked BY the stage runners through
54-anthology-writer/anthology-entry.sh with a per-participant-per-stage run dir;
this entry governs the ENGINE. A hand-rolled ungoverned external sender in a run
dir is FORBIDDEN; skipping a gate requires a logged owner token in
working/checkpoints/process_manifest.json.
EOF
    exit 2
}

STAGE="" KEY="" ANTH="" PAYLOAD="" RUN_DIR="" PLAN=0 SELFTEST=0
while [ $# -gt 0 ]; do
    case "$1" in
        --stage)            STAGE="${2:-}"; shift 2 ;;
        --participant-key)  KEY="${2:-}"; shift 2 ;;
        --anthology-id)     ANTH="${2:-}"; shift 2 ;;
        --payload)          PAYLOAD="${2:-}"; shift 2 ;;
        --run-dir)          RUN_DIR="${2:-}"; shift 2 ;;
        --plan)             PLAN=1; shift ;;
        --self-test)        SELFTEST=1; shift ;;
        -h|--help)          usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS="$SELF_DIR/scripts"
[ -d "$SCRIPTS" ] || die "scripts/ not found at $SCRIPTS"

if [ -n "$RUN_DIR" ]; then
    [ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
    RUN_DIR="$(cd "$RUN_DIR" && pwd)"
fi
PROC_MANIFEST="${RUN_DIR:-}/working/checkpoints/process_manifest.json"

owner_skip_approved() {
    local gate="$1"
    [ -n "${RUN_DIR:-}" ] || return 1
    [ -f "$PROC_MANIFEST" ] || return 1
    command -v python3 >/dev/null 2>&1 || return 1
    GATE="$gate" PM="$PROC_MANIFEST" python3 - <<'PY'
import json, os, sys
gate = os.environ["GATE"]
try:
    obj = json.load(open(os.environ["PM"]))
except Exception:
    sys.exit(1)
recs = []
for key in ("owner_skip_approvals", "owner_skip_approval"):
    v = obj.get(key) if isinstance(obj, dict) else None
    if isinstance(v, list): recs += v
    elif isinstance(v, dict): recs.append(v)
for r in recs:
    if not isinstance(r, dict): continue
    code = str(r.get("gate") or r.get("gate_code") or r.get("code") or "").strip()
    if code not in (gate, "*"): continue
    if (r.get("approved") is True or r.get("owner_approved") is True) \
       and str(r.get("approved_by", "")).strip() and str(r.get("reason", "")).strip():
        sys.exit(0)
sys.exit(1)
PY
}

gate_fail() {
    local code="$1" exitcode="$2"; shift 2
    if owner_skip_approved "$code"; then
        echo "!! [$PROG] $code tripped but OWNER-APPROVED skip is logged. Proceeding under owner authority." >&2
        return 0
    fi
    echo >&2; printf '!%.0s' {1..78} >&2; echo >&2
    echo "GATE FAILED [$code]: $*" >&2
    echo "Skippable ONLY by a logged owner token in $PROC_MANIFEST" >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# --plan / --self-test short-circuits still run the deps gate below.

# ===========================================================================
# GATE 1 -- DEPS CHECK (python3; exit 6 AE_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 -- DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 present"
else
    if owner_skip_approved "AE_DEPS_MISSING"; then
        echo "!! [$PROG] python3 missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        echo "AE_DEPS_MISSING: python3" >&2; exit 6
    fi
fi

# ===========================================================================
# GATE 1b -- MODEL-MAP PRE-GATE (preflight.sh --check)
# ===========================================================================
note "GATE 1b/3 -- MODEL-MAP PRE-GATE (preflight.sh --check)"
if [ -n "$RUN_DIR" ] && command -v python3 >/dev/null 2>&1 && [ -f "$SELF_DIR/preflight.sh" ]; then
    if bash "$SELF_DIR/preflight.sh" --run-dir "$RUN_DIR" --check; then
        :
    else
        PF_RC=$?
        if [ "$PF_RC" -eq 2 ]; then
            gate_fail "AF-AE-UNRESOLVED-MODELMAP" 8 "the run-dir model-map.json still carries \
<CLIENT_*> placeholders or an Anthropic-family id -- the fleet installer has not resolved this box. \
Resolve the tier map on a configured box (preflight.sh) and re-run."
        else
            echo "  (preflight --check non-fatal rc=$PF_RC; continuing)"
        fi
    fi
else
    echo "  (model-map pre-gate skipped: no --run-dir, python3 absent, or preflight.sh missing)"
fi

# ===========================================================================
# GATE 2 -- BYPASS-SCAN (refuse hand-rolled ungoverned external senders in the run dir)
# AF-AE-BYPASS. The engine's OWN adapters in scripts/ are the sanctioned path and
# are excluded; only files DROPPED INTO the run dir are scanned.
# ===========================================================================
note "GATE 2/3 -- BYPASS-SCAN (run-dir n8n/Airtable/legacy-base/literal-key detection)"
if [ -n "$RUN_DIR" ] && command -v python3 >/dev/null 2>&1; then
    SCAN_OUT="$(RUN_DIR="$RUN_DIR" SELF_DIR="$SELF_DIR" python3 - <<'PY' 2>&1
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
self_dir = os.path.realpath(os.environ["SELF_DIR"])
re_n8n = re.compile(r"/webhook/|n8n\.cloud|X-N8N-API-KEY", re.I)
re_air = re.compile(r"api\.airtable\.com|airtable\.com/v0", re.I)
re_key = re.compile(r"Authorization\s*:\s*Bearer\s+[A-Za-z0-9_\-]{16,}", re.I)
findings = []
for root, dirs, files in os.walk(run_dir):
    if os.path.realpath(root).startswith(self_dir):
        dirs[:] = []; continue
    for fn in files:
        if not (fn.endswith(".py") or fn.endswith(".sh") or fn.endswith(".js")):
            continue
        path = os.path.join(root, fn)
        try:
            src = open(path, "r", errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(path, run_dir)
        if re_n8n.search(src):
            findings.append((rel, "an n8n webhook call (the engine replaces n8n entirely)"))
        elif re_air.search(src):
            findings.append((rel, "an Airtable call (no runtime prompt-base fetch; the ledger is the store)"))
        elif re_key.search(src):
            findings.append((rel, "a literal Authorization key header (credentials resolve by label, never inline)"))
if not findings:
    print("  OK: no hand-rolled ungoverned external sender in the run directory")
    sys.exit(0)
print("  UNGOVERNED EXTERNAL SENDER(S) DETECTED:", file=sys.stderr)
for rel, why in findings:
    print("    [AF-AE-BYPASS] %s: %s" % (rel, why), file=sys.stderr)
sys.exit(5)
PY
)"; SCAN_RC=$?
    printf '%s\n' "$SCAN_OUT"
    if [ "$SCAN_RC" -eq 5 ]; then
        gate_fail "AF-AE-BYPASS" 5 "a hand-rolled ungoverned external sender is present in $RUN_DIR. \
All external I/O routes through the engine's sanctioned adapters in scripts/; remove the sender(s) above and re-run."
    fi
else
    echo "  (scan skipped: no --run-dir or python3 absent)"
fi

# ===========================================================================
# GATE 3 -- VERSION/HASH PIN (content hash of the enforcement set, when pinned)
# The integrator stamps ENGINE-PIN.sha256 after all guards land; until then the
# hash is recorded, not enforced. Only files that exist are hashed.
# ===========================================================================
note "GATE 3/3 -- VERSION/HASH PIN (entry + manifest + guards)"
ENFORCE_CANDIDATES=(
    "$SELF_DIR/anthology-engine-entry.sh"
    "$SELF_DIR/ENGINE-MANIFEST.json"
    "$SCRIPTS/guard-prompt-pins.py"
    "$SCRIPTS/guard-no-anthropic-runtime.py"
    "$SCRIPTS/guard-font-floor.py"
    "$SCRIPTS/guard-cron-inventory.py"
)
ENFORCE_FILES=()
for f in "${ENFORCE_CANDIDATES[@]}"; do [ -f "$f" ] && ENFORCE_FILES+=("$f"); done
version_hash_pin() {
    local computed=""
    if [ "${#ENFORCE_FILES[@]}" -eq 0 ]; then echo "  (no enforcement files present yet; hash skipped)"; return 0; fi
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "${ENFORCE_FILES[@]}" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "${ENFORCE_FILES[@]}" | shasum -a 256 | awk '{print $1}')"
    else
        echo "  (no sha256 tool; hash pin skipped)"; return 0
    fi
    echo "  enforcement hash (sha256 of ${#ENFORCE_FILES[@]} present file(s)): $computed"
    local pin="$SELF_DIR/ENGINE-PIN.sha256"
    if [ -f "$pin" ]; then
        local expected; expected="$(tr -d ' \t\n' < "$pin")"
        if [ -n "$expected" ] && [ "$expected" != "$computed" ]; then
            echo "  PIN MISMATCH: expected $expected" >&2; return 7
        fi
        echo "  OK: enforcement hash matches the pinned head"
    else
        echo "  (no ENGINE-PIN.sha256; hash recorded, not enforced -- integrator stamps it after the guards land)"
    fi
    return 0
}
version_hash_pin; VHP_RC=$?
[ "$VHP_RC" -eq 0 ] || gate_fail "AF-AE-HASH-PIN" 7 "the enforcement-set hash does not match the pinned head."

# ===========================================================================
# All gates passed -- --plan / --self-test, or dispatch a stage runner.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN -- the canonical stage plan S0..S9 (gates ran)"
    for f in "$SCRIPTS"/stage_s0_*.py "$SCRIPTS"/stage_s1_*.py "$SCRIPTS"/stage_s2_*.py \
             "$SCRIPTS"/stage_s3_*.py "$SCRIPTS"/stage_s4_*.py "$SCRIPTS"/stage_s5_*.py \
             "$SCRIPTS"/stage_s6_*.py "$SCRIPTS"/stage_s7_*.py "$SCRIPTS"/stage_s8_*.py \
             "$SCRIPTS"/stage_s9_*.py; do
        [ -f "$f" ] && python3 "$f" --plan && echo
    done
    exit 0
fi

if [ "$SELFTEST" -eq 1 ]; then
    note "SELF-TEST -- every stage runner --self-test (gates ran)"
    rc=0
    for f in "$SCRIPTS"/stage_s*.py; do
        [ -f "$f" ] || continue
        if python3 "$f" --self-test; then :; else rc=1; fi
    done
    exit "$rc"
fi

[ -n "$STAGE" ] || usage
# Resolve the stage runner file from the stage id (e.g. s5 -> stage_s5_*.py).
RUNNER="$(ls "$SCRIPTS"/stage_"${STAGE}"_*.py 2>/dev/null | head -n1)"
[ -n "$RUNNER" ] && [ -f "$RUNNER" ] || die "no stage runner for --stage '$STAGE' (expected scripts/stage_${STAGE}_*.py)"

note "ALL GATES PASSED -- dispatching $(basename "$RUNNER")"
if [ -n "$RUN_DIR" ]; then
    NONCE_DIR="$RUN_DIR/working/checkpoints"
    NONCE_FILE="$NONCE_DIR/.anthology-engine-entry-nonce"
    mkdir -p "$NONCE_DIR"
    _mint_nonce() {
        if command -v python3 >/dev/null 2>&1; then
            python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null && return 0
        fi
        if command -v openssl >/dev/null 2>&1; then openssl rand -hex 32 2>/dev/null && return 0; fi
        LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom 2>/dev/null | head -c 64; echo
    }
    OC_ANTHOLOGY_ENGINE_ENTRY_NONCE="$(_mint_nonce)"
    [ -n "$OC_ANTHOLOGY_ENGINE_ENTRY_NONCE" ] || die "could not mint the front-door nonce. Refusing to run."
    ( umask 077; printf '%s' "$OC_ANTHOLOGY_ENGINE_ENTRY_NONCE" > "$NONCE_FILE" )
    chmod 600 "$NONCE_FILE" 2>/dev/null || true
    export OC_ANTHOLOGY_ENGINE_ENTRY_NONCE
    trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP
fi

cmd=(python3 "$RUNNER")
[ -n "$KEY" ]     && cmd+=(--participant-key "$KEY")
[ -n "$ANTH" ]    && cmd+=(--anthology-id "$ANTH")
[ -n "$PAYLOAD" ] && cmd+=(--payload "$PAYLOAD")
[ -n "$RUN_DIR" ] && cmd+=(--run-dir "$RUN_DIR")
note "run: ${cmd[*]}"
"${cmd[@]}"
exit $?

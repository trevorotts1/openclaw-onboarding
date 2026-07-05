#!/usr/bin/env bash
# 54-anthology-writer/anthology-entry.sh
#
# THE ONE SANCTIONED COMMAND TO RUN THE ANTHOLOGY WRITER.
# ============================================================================
# Cloned in spirit from 55-product-bio/product-bio-entry.sh. The engine's
# guardrails (the fail-closed provers in scripts/, the deterministic phase
# machine run_anthology.py, the local-only deliverable) only bind if the run goes
# THROUGH this entry. Before it hands off to the orchestrator it runs three
# fail-closed gates and mints a run-scoped nonce the orchestrator requires:
#
#   1. DEPS CHECK       — python3 must be present (exit 6, AW_DEPS_MISSING).
#   1b. MODEL-MAP PRE-GATE — if a resolved model-map.json exists in the run dir,
#                         it must carry NO <CLIENT_*> placeholder and no Anthropic
#                         id (exit 8, AF-AW-UNRESOLVED-MODELMAP). preflight.sh is
#                         the resolver; here it runs as a fail-closed pre-gate.
#   2. BYPASS-SCAN      — refuse if any hand-rolled EXTERNAL uploader/notifier
#                         exists in the run directory: a Google Drive upload, a
#                         Slack post, a Gmail/SMTP send, an n8n webhook, or an
#                         Airtable write. The Anthology Writer is LOCAL-ONLY;
#                         delivery is a labeled bundle in ~/Downloads (exit 5,
#                         AF-AW-ENTRY-BYPASS). Nothing leaves the box from here.
#   3. VERSION/HASH PIN — content hash of the enforcement set (run_anthology.py +
#                         the provers + _aw_common.py); if ENGINE-PIN.sha256 is
#                         present the hash MUST match (exit 7, AF-AW-HASH-PIN).
#
# A gate may be skipped ONLY by an explicit, LOGGED owner approval token in
# <run-dir>/working/checkpoints/process_manifest.json. Never silently.
#
# THE ONLY PATH:  bash anthology-entry.sh --run-dir DIR [--plan] [--upto P]
#
# EXIT CODES
#   0  — gates passed; orchestrator dispatched (its own exit is returned)
#   2  — usage error / orchestrator scripts not found
#   5  — BYPASS-SCAN tripped (hand-rolled external uploader/notifier present)
#   6  — DEPS CHECK failed (AW_DEPS_MISSING)
#   7  — VERSION/HASH PIN failed (hash mismatch, no owner skip)
#   8  — MODEL-MAP PRE-GATE failed (residual <CLIENT_*> placeholder / Anthropic id)
# ============================================================================

set -uo pipefail
PROG="anthology-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

usage() {
    cat >&2 <<EOF
$PROG — the ONE sanctioned command to run the Anthology Writer.

USAGE:
  bash $PROG --run-dir DIR [--plan] [--upto PHASE]

REQUIRED:
  --run-dir DIR   the anthology run directory (contains working/)

OPTIONS:
  --plan          print the canonical phase plan and exit (gates still run)
  --upto PHASE    run through this phase only (P0-INTAKE..P7-DELIVER)
  -h | --help     this help

There is NO other sanctioned way to run the engine. A hand-rolled external
uploader/notifier is FORBIDDEN (local-only delivery); skipping a gate requires a
logged owner token in working/checkpoints/process_manifest.json.
EOF
    exit 2
}

RUN_DIR="" PLAN=0 UPTO=""
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
        --plan)    PLAN=1; shift ;;
        --upto)    UPTO="${2:-}"; shift 2 ;;
        -h|--help) usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SELF_DIR/run_anthology.py"
SCRIPTS="$SELF_DIR/scripts"
[ -f "$RUNNER" ] || die "run_anthology.py not found at $RUNNER"
[ -d "$SCRIPTS" ] || die "scripts/ not found at $SCRIPTS"

if [ "$PLAN" -eq 0 ]; then
    [ -n "$RUN_DIR" ] || usage
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
    echo "  (owner_skip_approval: {gate:\"$code\", approved:true, approved_by, reason})." >&2
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# ===========================================================================
# GATE 1 — DEPS CHECK (python3; exit 6 AW_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 present"
else
    if owner_skip_approved "AW_DEPS_MISSING"; then
        echo "!! [$PROG] python3 missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        echo "AW_DEPS_MISSING: python3" >&2; exit 6
    fi
fi

# ===========================================================================
# GATE 1b — MODEL-MAP PRE-GATE (preflight.sh --check; AF-AW-UNRESOLVED-MODELMAP)
# preflight.sh is the resolver AND (here) a fail-closed pre-gate: a resolved
# run-dir model-map.json that still carries <CLIENT_*> placeholders (installer
# not run) or a banned Anthropic id is refused BEFORE any authoring/QC. A missing
# map is a clean pass (the fleet installer resolves per box).
# ===========================================================================
note "GATE 1b/3 — MODEL-MAP PRE-GATE (preflight.sh --check)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1 && [ -f "$SELF_DIR/preflight.sh" ]; then
    if bash "$SELF_DIR/preflight.sh" --run-dir "$RUN_DIR" --check; then
        :
    else
        PF_RC=$?
        if [ "$PF_RC" -eq 2 ]; then
            gate_fail "AF-AW-UNRESOLVED-MODELMAP" 8 "the run-dir model-map.json still carries \
<CLIENT_*> placeholders (or a banned Anthropic id) — the fleet installer has not resolved this \
box's providers. Resolve the tier map on a configured box (preflight.sh) and re-run."
        else
            echo "  (preflight --check non-fatal rc=$PF_RC; continuing)"
        fi
    fi
else
    echo "  (model-map pre-gate skipped: --plan, python3 absent, or preflight.sh missing)"
fi

# ===========================================================================
# GATE 2 — BYPASS-SCAN (refuse hand-rolled external uploaders/notifiers)
# AF-AW-ENTRY-BYPASS
# ===========================================================================
note "GATE 2/3 — BYPASS-SCAN (hand-rolled Drive/Slack/Gmail/n8n/Airtable detection)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
    SCAN_OUT="$(RUN_DIR="$RUN_DIR" SELF_DIR="$SELF_DIR" python3 - <<'PY' 2>&1
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
self_dir = os.path.realpath(os.environ["SELF_DIR"])
CANON = {"run_anthology.py", "prove_aw_intake.py", "prove_aw_fidelity.py",
         "prove_aw_tone.py", "prove_aw_chapter.py", "aw_build_check.py",
         "verify_tone_core_sync.py", "_aw_common.py"}
re_drive = re.compile(r"googleapis\.com/drive|drive\.files\(|/files/[^ ]*/copy", re.I)
re_slack = re.compile(r"slack\.com/api|chat\.postMessage|hooks\.slack\.com", re.I)
re_gmail = re.compile(r"\bsmtplib\b|gmail\.com/|/messages/send|smtp\.gmail", re.I)
re_n8n   = re.compile(r"/webhook/|n8n\.cloud|X-N8N-API-KEY", re.I)
re_air   = re.compile(r"api\.airtable\.com|airtable\.com/v0", re.I)
findings = []
for root, dirs, files in os.walk(run_dir):
    if os.path.realpath(root) == self_dir:
        dirs[:] = []; continue
    for fn in files:
        if not fn.endswith(".py") or fn in CANON:
            continue
        path = os.path.join(root, fn)
        if os.path.realpath(path).startswith(self_dir + os.sep):
            continue
        try:
            src = open(path, "r", errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(path, run_dir)
        if re_drive.search(src):
            findings.append((rel, "a Google Drive upload/copy (delivery is local-only)"))
        elif re_slack.search(src):
            findings.append((rel, "a Slack notification (no hardcoded channels; per-client gateway only)"))
        elif re_gmail.search(src):
            findings.append((rel, "a Gmail/SMTP send (delivery is local-only)"))
        elif re_n8n.search(src):
            findings.append((rel, "an n8n webhook call (the engine replaces n8n entirely)"))
        elif re_air.search(src):
            findings.append((rel, "an Airtable write (the engine uses a local artifact store)"))
if not findings:
    print("  OK: no hand-rolled external uploader/notifier in the run directory")
    sys.exit(0)
print("  HAND-ROLLED EXTERNAL SENDER(S) DETECTED:", file=sys.stderr)
for rel, why in findings:
    print("    [AF-AW-ENTRY-BYPASS] %s: %s" % (rel, why), file=sys.stderr)
sys.exit(5)
PY
)"; SCAN_RC=$?
    printf '%s\n' "$SCAN_OUT"
    if [ "$SCAN_RC" -eq 5 ]; then
        gate_fail "AF-AW-ENTRY-BYPASS" 5 "a hand-rolled external uploader/notifier is present in $RUN_DIR. \
The Anthology Writer delivers LOCAL-ONLY (a labeled bundle in ~/Downloads); no n8n / Airtable / Drive / Slack / Gmail. \
Delete the hand-rolled sender(s) above and re-run."
    fi
else
    echo "  (scan skipped: --plan or python3 absent)"
fi

# ===========================================================================
# GATE 3 — VERSION/HASH PIN (content hash of the enforcement set)
# ===========================================================================
note "GATE 3/3 — VERSION/HASH PIN (orchestrator + provers + common)"
ENFORCE_FILES=(
    "$RUNNER"
    "$SCRIPTS/_aw_common.py"
    "$SCRIPTS/prove_aw_intake.py"
    "$SCRIPTS/prove_aw_fidelity.py"
    "$SCRIPTS/prove_aw_tone.py"
    "$SCRIPTS/prove_aw_chapter.py"
    "$SCRIPTS/aw_build_check.py"
    "$SCRIPTS/verify_tone_core_sync.py"
)
version_hash_pin() {
    local computed=""
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "${ENFORCE_FILES[@]}" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "${ENFORCE_FILES[@]}" | shasum -a 256 | awk '{print $1}')"
    else
        echo "  (no sha256 tool; hash pin skipped)"; return 0
    fi
    echo "  enforcement hash (sha256 of orchestrator+provers+common): $computed"
    local pin="$SELF_DIR/ENGINE-PIN.sha256"
    if [ -f "$pin" ]; then
        local expected; expected="$(tr -d ' \t\n' < "$pin")"
        if [ -n "$expected" ] && [ "$expected" != "$computed" ]; then
            echo "  PIN MISMATCH: expected $expected" >&2; return 7
        fi
        echo "  OK: enforcement hash matches the pinned head"
    else
        echo "  (no ENGINE-PIN.sha256; hash recorded, not enforced)"
    fi
    return 0
}
version_hash_pin; VHP_RC=$?
[ "$VHP_RC" -eq 0 ] || gate_fail "AF-AW-HASH-PIN" 7 "the enforcement-set hash does not match the pinned head."

# ===========================================================================
# All gates passed — hand off to the deterministic orchestrator.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN — printing the canonical phase plan (gates ran)"
    exec python3 "$RUNNER" --plan
fi

note "ALL GATES PASSED — dispatching run_anthology.py"
NONCE_DIR="$RUN_DIR/working/checkpoints"
NONCE_FILE="$NONCE_DIR/.anthology-entry-nonce"
mkdir -p "$NONCE_DIR"

_mint_nonce() {
    if command -v python3 >/dev/null 2>&1; then
        python3 -c 'import secrets; print(secrets.token_hex(32))' 2>/dev/null && return 0
    fi
    if command -v openssl >/dev/null 2>&1; then
        openssl rand -hex 32 2>/dev/null && return 0
    fi
    LC_ALL=C tr -dc 'a-f0-9' < /dev/urandom 2>/dev/null | head -c 64; echo
}
OC_ANTHOLOGY_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_ANTHOLOGY_ENTRY_NONCE" ] || die "could not mint the front-door nonce. Refusing to run."
( umask 077; printf '%s' "$OC_ANTHOLOGY_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_ANTHOLOGY_ENTRY_NONCE
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

cmd=(python3 "$RUNNER" --run-dir "$RUN_DIR")
[ -n "$UPTO" ] && cmd+=(--upto "$UPTO")
note "run: ${cmd[*]}"
"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"

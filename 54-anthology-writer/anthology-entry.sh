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
#   2. MODEL-MAP PRE-GATE — if a resolved model-map.json exists in the run dir,
#                         it must carry NO <CLIENT_*> placeholder and no Anthropic
#                         id (exit 8, AF-AW-UNRESOLVED-MODELMAP). preflight.sh is
#                         the resolver; here it runs as a fail-closed pre-gate.
#   3. BYPASS-SCAN      — refuse if any hand-rolled EXTERNAL uploader/notifier
#                         exists in the run directory: a Google Drive upload, a
#                         Slack post, a Gmail/SMTP send, an n8n webhook, or an
#                         Airtable write. The Anthology Writer is LOCAL-ONLY;
#                         delivery is a labeled bundle in ~/Downloads (exit 5,
#                         AF-AW-ENTRY-BYPASS). Nothing leaves the box from here.
#   4. VERSION/HASH PIN — content hash of the enforcement set (run_anthology.py +
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
  bash $PROG --run-dir DIR [--plan] [--upto PHASE] [--status] [--resume] [--json]

REQUIRED:
  --run-dir DIR   the anthology run directory (contains working/)

OPTIONS:
  --plan          print the canonical phase plan and exit (gates still run)
  --upto PHASE    run through this phase only (P0-INTAKE..P7-DELIVER)
  --status        read process_manifest.json, print phase/progress/failed/certificate
                  presence and exit 0 WITHOUT tripping any gates (read-only)
  --resume        skip phases marked "passed" in process_manifest.json; resume at
                  the failed_phase or the first unpassed phase
  --json          machine-parseable output (applies to --status or --plan)
  -h | --help     this help

There is NO other sanctioned way to run the engine. A hand-rolled external
uploader/notifier is FORBIDDEN (local-only delivery); skipping a gate requires a
logged owner token in working/checkpoints/process_manifest.json.
EOF
    exit 2
}

RUN_DIR="" PLAN=0 UPTO="" STATUS=0 RESUME=0 JSON=0
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
        --plan)    PLAN=1; shift ;;
        --upto)    UPTO="${2:-}"; shift 2 ;;
        --status)  STATUS=1; shift ;;
        --resume)  RESUME=1; shift ;;
        --json)    JSON=1; shift ;;
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

# ---------------------------------------------------------------------------
# CLAIM-BEFORE-ACT: acquire a per-run-dir lock so two concurrent dispatchers
# (or a retry + fresh run) can never race on the nonce or working/ state.
# The lock is released on exit via trap (EXIT INT TERM HUP). If the lock is
# contended we print the holder's PID and abort (claim-first, act-second).
#
# Uses mkdir (atomic on all filesystems) for portable mutual exclusion.
# mkdir returns success only to the first caller; subsequent callers see
# a lock-held message with the holder's PID and exit 9.
# ---------------------------------------------------------------------------
if [ -n "${RUN_DIR:-}" ]; then
    LOCK_DIR="$RUN_DIR/.anthology.lock"
    mkdir -p "$RUN_DIR"
    if ! mkdir "$LOCK_DIR" 2>/dev/null; then
        LOCK_HOLDER="$(cat "$LOCK_DIR/pid" 2>/dev/null | tr -d '[:space:]' || echo "unknown")"
        echo "Another agent holds this run dir (PID $LOCK_HOLDER)" >&2
        exit 9
    fi
    echo "$$" > "$LOCK_DIR/pid"
    # Release the lock on any exit path (normal, interrupt, terminate, hangup).
    trap 'rm -rf "$LOCK_DIR"' EXIT INT TERM HUP
fi

PROC_MANIFEST="${RUN_DIR:-}/working/checkpoints/process_manifest.json"
json_flag=""  # set -u safe: defined at module scope for --status and --plan paths

# --status: read-only surface — skip ALL gates, print status, exit.
if [ "$STATUS" -eq 1 ]; then
    [ -n "$RUN_DIR" ] || die "--status requires --run-dir DIR"
    [ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
    [ "$JSON" -eq 1 ] && json_flag="--json"
    exec python3 "$RUNNER" --run-dir "$RUN_DIR" --status $json_flag
    exit 0
fi

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
    # FIX-18: Reject a wildcard "*" gate code — one record disarming EVERY entry gate
    # is a security defect. Require an exact AF code (AF-AW-HASH-PIN, AF-AW-ENTRY-BYPASS,
    # AW_DEPS_MISSING, etc.) so each skip token gates exactly ONE failure mode.
    if code == "*":
        print("REJECTED: wildcard gate {'gate':'*'} in process_manifest.json disarms EVERY "
              "entry gate from one record — require an exact AF code (AF-AW-HASH-PIN, "
              "AF-AW-ENTRY-BYPASS, AW_DEPS_MISSING, ...)", file=sys.stderr)
        sys.exit(2)
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
    echo >&2
    # Print recovery guidance via the shared _aw_common AF_CODE_GUIDANCE
    if command -v python3 >/dev/null 2>&1; then
        SKILL_DIR="$SELF_DIR" CODE="$code" RUN_DIR="${RUN_DIR:-}" python3 - <<'PY'
import os, sys
skill_dir = os.environ.get("SKILL_DIR", "")
run_dir = os.environ.get("RUN_DIR", "")
code = os.environ.get("CODE", "")
sys.path.insert(0, os.path.join(skill_dir, "scripts"))
try:
    import _aw_common
    _aw_common.print_af_guidance(code, run_dir=run_dir, skill_dir=skill_dir)
except Exception:
    pass
PY
    fi
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# When --json is active, stdout must carry ONLY the final JSON object. Redirect
# all gate/orchestrator chatter to stderr so `--json | jq` / `| python3 -m
# json.tool` sees a single parseable JSON document on stdout.
if [ "$JSON" -eq 1 ]; then
    exec 3>&1   # save real stdout
    exec 1>&2   # gate/orchestrator output -> stderr
fi

# ===========================================================================
# GATE 1 — DEPS CHECK (python3; exit 6 AW_DEPS_MISSING)
# ===========================================================================
note "GATE 1/4 — DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  [PASS] python3 present"
else
    if owner_skip_approved "AW_DEPS_MISSING"; then
        echo "!! [$PROG] python3 missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        echo "AW_DEPS_MISSING: python3" >&2; exit 6
    fi
fi

# ===========================================================================
# GATE 2 — MODEL-MAP PRE-GATE (preflight.sh --check; AF-AW-UNRESOLVED-MODELMAP)
# preflight.sh is the resolver AND (here) a fail-closed pre-gate: a resolved
# run-dir model-map.json that still carries <CLIENT_*> placeholders (installer
# not run) or a banned Anthropic id is refused BEFORE any authoring/QC. A missing
# map is a clean pass (the fleet installer resolves per box).
# ===========================================================================
note "GATE 2/4 — MODEL-MAP PRE-GATE (preflight.sh --check)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1 && [ -f "$SELF_DIR/preflight.sh" ]; then
    if bash "$SELF_DIR/preflight.sh" --run-dir "$RUN_DIR" --check; then
        # Fresh-box landmine: a MISSING skill-root model-map.json passes --check by
        # design ("installer resolves per box"), but any invocation that will reach
        # authoring phases fails at P6 without one. Warn at entry, fatal stays at P6.
        SKILL_ROOT_MAP="$SELF_DIR/model-map.json"
        if [ ! -f "$SKILL_ROOT_MAP" ] && [ ! -f "$SELF_DIR/config/model-map.json" ]; then
            echo "WARNING: model-map.json absent — authoring will fail at P6; run preflight/model resolution first" >&2
        fi
        :
    else
        PF_RC=$?
        if [ "$PF_RC" -eq 2 ]; then
            MODEL_MAP_PATH="$RUN_DIR/model-map.json"
            gate_fail "AF-AW-UNRESOLVED-MODELMAP" 8 "the run-dir $MODEL_MAP_PATH still carries \
<CLIENT_PROVIDER_ID> or <CLIENT_MODEL> placeholders (or a banned Anthropic id). \
Run: preflight.sh --resolve --interactive to configure your provider keys."
        else
            echo "  (preflight --check non-fatal rc=$PF_RC; continuing)"
        fi
    fi
else
    echo "  (model-map pre-gate skipped: --plan, python3 absent, or preflight.sh missing)"
fi

# ===========================================================================
# GATE 3 — BYPASS-SCAN (refuse hand-rolled external uploaders/notifiers)
# AF-AW-ENTRY-BYPASS
# ===========================================================================
note "GATE 3/4 — BYPASS-SCAN (hand-rolled Drive/Slack/Gmail/n8n/Airtable detection)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
    SCAN_OUT="$(RUN_DIR="$RUN_DIR" SELF_DIR="$SELF_DIR" python3 - <<'PY' 2>&1
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
self_dir = os.path.realpath(os.environ["SELF_DIR"])
CANON = {"run_anthology.py", "prove_aw_intake.py", "prove_aw_avatar.py",
         "prove_aw_fidelity.py", "prove_aw_tone.py", "prove_aw_chapter.py",
         "aw_build_check.py", "verify_tone_core_sync.py", "_aw_common.py"}
re_drive = re.compile(r"googleapis\.com/drive|drive\.files\(|/files/[^ ]*/copy", re.I)
re_slack = re.compile(r"slack\.com/api|chat\.postMessage|hooks\.slack\.com", re.I)
re_gmail = re.compile(r"\bsmtplib\b|gmail\.com/|/messages/send|smtp\.gmail|\bsmtp\b", re.I)
re_n8n   = re.compile(r"/webhook/|n8n\.cloud|X-N8N-API-KEY|gohighlevel\.com", re.I)
re_air   = re.compile(r"api\.airtable\.com|airtable\.com/v0", re.I)
re_webhook = re.compile(r"\bwebhook\b", re.I)
re_ext_req = re.compile(r"\brequests\b.*['\"](https?://[^'\"]+\.com|https?://[^'\"]+\.io|https?://[^'\"]+\.net)", re.I)
findings = []
for root, dirs, files in os.walk(run_dir):
    if os.path.realpath(root) == self_dir:
        dirs[:] = []; continue
    for fn in files:
        if fn in CANON:
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
        elif re_webhook.search(src):
            findings.append((rel, "a webhook call (delivery is local-only)"))
        elif re_ext_req.search(src):
            findings.append((rel, "an HTTP request to an external host (delivery is local-only)"))
if not findings:
    print("  [PASS] no hand-rolled external uploader/notifier in the run directory")
    sys.exit(0)
print("  HAND-ROLLED EXTERNAL SENDER(S) DETECTED:", file=sys.stderr)
for rel, why in findings:
    print("    [AF-AW-ENTRY-BYPASS] %s: %s" % (rel, why), file=sys.stderr)
sys.exit(5)
PY
)"; SCAN_RC=$?
    printf '%s\n' "$SCAN_OUT"
    if [ "$SCAN_RC" -ne 0 ]; then
        gate_fail "AF-AW-ENTRY-BYPASS" 5 "a hand-rolled external uploader/notifier is present in $RUN_DIR (or \
scanner failed unexpectedly, rc=$SCAN_RC — refusing to proceed). \
The Anthology Writer delivers LOCAL-ONLY (a labeled bundle in ~/Downloads); no n8n / Airtable / Drive / Slack / Gmail / webhooks / non-local HTTP. \
Delete the hand-rolled sender(s) above and re-run."
    fi
else
    echo "  (scan skipped: --plan or python3 absent)"
fi

# ===========================================================================
# GATE 4 — VERSION/HASH PIN (content hash of the enforcement set)
# ===========================================================================
note "GATE 4/4 — VERSION/HASH PIN (orchestrator + provers + common)"
ENFORCE_FILES=()
while IFS= read -r f; do
    [ -n "$f" ] && ENFORCE_FILES+=("$SELF_DIR/$f")
done < "$SCRIPTS/ENFORCEMENT-FILES.list"
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
    if [ ! -f "$pin" ]; then
        echo "  ENGINE-PIN.sha256 MISSING — the enforcement-set pin is not shipped" >&2; return 7
    fi
    local expected; expected="$(tr -d ' \t\n' < "$pin")"
    if [ -z "$expected" ]; then
        echo "  ENGINE-PIN.sha256 is EMPTY — pin must carry the expected hash" >&2; return 7
    fi
    if [ "$expected" != "$computed" ]; then
        echo "  PIN MISMATCH: expected $expected, computed $computed" >&2; return 7
    fi
    echo "  OK: enforcement hash matches the pinned head"
    return 0
}
version_hash_pin; VHP_RC=$?
[ "$VHP_RC" -eq 0 ] || gate_fail "AF-AW-HASH-PIN" 7 "the enforcement-set hash does not match the pinned head."

# ===========================================================================
# All gates passed — hand off to the deterministic orchestrator.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN — printing the canonical phase plan (gates ran)"
    exec python3 "$RUNNER" --plan $json_flag
fi

note "ALL GATES PASS — dispatching run_anthology.py"

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

cmd=(python3 "$RUNNER" --run-dir "$RUN_DIR")
[ -n "$UPTO" ] && cmd+=(--upto "$UPTO")
[ "$RESUME" -eq 1 ] && cmd+=(--resume)
note "run: ${cmd[*]}"
__json_start=0
if [ "$JSON" -eq 1 ]; then
    __json_start=$(date +%s)
fi
"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true

if [ "$JSON" -eq 1 ]; then
    __json_end=$(date +%s)
    __duration=$(( __json_end - __json_start ))
    __phases=0; __passed=0; __failed_phase="null"; __cert_sha="null"
    __pm="$RUN_DIR/working/checkpoints/process_manifest.json"
    if [ -f "$__pm" ] && command -v python3 >/dev/null 2>&1; then
        __json_data="$(python3 - "$__pm" "$RUN_DIR" 2>/dev/null <<'PYEOF'
import json, sys, os
try:
    pm = json.load(open(sys.argv[1]))
except Exception:
    pm = {}
phases = pm.get("phases", [])
passed = sum(1 for p in phases if p.get("passed"))
failed_phase = pm.get("failed_phase")
cert_sha = None
cert_path = os.path.join(sys.argv[2], "delivery", "PROCESS-CERTIFICATE.json")
if os.path.isfile(cert_path):
    try:
        cert_sha = json.load(open(cert_path)).get("certificate_sha")
    except Exception:
        pass
print(json.dumps({"phases": len(phases), "passed": passed,
    "failed_phase": failed_phase, "certificate_sha": cert_sha}))
PYEOF
)"
        if [ -n "$__json_data" ]; then
            __phases=$(echo "$__json_data" | python3 -c "import json,sys;print(json.load(sys.stdin)['phases'])" 2>/dev/null || echo 0)
            __passed=$(echo "$__json_data" | python3 -c "import json,sys;print(json.load(sys.stdin)['passed'])" 2>/dev/null || echo 0)
            __failed_phase=$(echo "$__json_data" | python3 -c "import json,sys;print(json.dumps(json.load(sys.stdin)['failed_phase']))" 2>/dev/null || echo "null")
            __cert_sha=$(echo "$__json_data" | python3 -c "import json,sys;x=json.load(sys.stdin)['certificate_sha'];print(json.dumps(x))" 2>/dev/null || echo "null")
        fi
    fi
    printf '{"phases":%s,"passed":%s,"failed_phase":%s,"certificate_sha":%s,"run_dir":"%s","duration":%s}\n' \
        "$__phases" "$__passed" "$__failed_phase" "$__cert_sha" "$RUN_DIR" "$__duration" >&3
    exec 1>&3 3>&-   # restore real stdout, close the saved fd
fi

exit "$_rc"

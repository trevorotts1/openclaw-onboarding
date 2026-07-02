#!/usr/bin/env bash
# 50-email-engine/email-engine-entry.sh
#
# THE ONE SANCTIONED COMMAND TO RUN THE EMAIL ENGINE.
# ============================================================================
# Cloned in spirit from 23-ai-workforce-blueprint/scripts/presentation-canonical-entry.sh.
#
# The Email Engine's guardrails (the fail-closed floor prover prove-email.py, the
# deterministic phase machine run_email_engine.py, DRAFT-ONLY deploy) only bind if
# the run goes THROUGH this entry. Before it hands off to the orchestrator it runs
# three fail-closed gates and mints a run-scoped nonce the orchestrator requires:
#
#   1. DEPS CHECK       — python3 must be present (exit 6, EMAIL_DEPS_MISSING).
#   2. BYPASS-SCAN      — refuse if any hand-rolled EMAIL SENDER exists in the run
#                         directory: a direct SMTP / SendGrid / Mailgun / Postmark /
#                         SES send, or a direct GoHighLevel/LeadConnector message
#                         send outside the sanctioned DRAFT-ONLY Skill-44 handoff
#                         (exit 5, AF-EMAIL-SEND-BYPASS). Nothing sends from here.
#   3. VERSION/HASH PIN — content hash of prove-email.py + run_email_engine.py; if a
#                         pin file is present the hash MUST match (exit 7).
#
# A gate may be skipped ONLY by an explicit, LOGGED owner approval token in
# <run-dir>/working/checkpoints/process_manifest.json ("owner_skip_approval(s)":
# approved:true + approved_by + reason naming the gate code). Never silently.
#
# THE FORBIDDEN PATH:  python3 working/*send*.py   (a hand-rolled sender)
# THE ONLY PATH:       bash email-engine-entry.sh --run-dir DIR [--plan] [--upto P3-QC]
#
# EXIT CODES
#   0  — gates passed; orchestrator dispatched (its own exit is returned)
#   2  — usage error / orchestrator scripts not found
#   5  — BYPASS-SCAN tripped (hand-rolled sender present, no owner skip)
#   6  — DEPS CHECK failed (EMAIL_DEPS_MISSING)
#   7  — VERSION/HASH PIN failed (hash mismatch, no owner skip)
# ============================================================================

set -uo pipefail
PROG="email-engine-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

usage() {
    cat >&2 <<EOF
$PROG — the ONE sanctioned command to run the Email Engine.

USAGE:
  bash $PROG --run-dir DIR [--plan] [--upto PHASE]

REQUIRED:
  --run-dir DIR   the email run directory (contains working/)

OPTIONS:
  --plan          print the canonical phase plan and exit (gates still run)
  --upto PHASE    run through this phase only (P1-SELECT|P2-GENERATE|P3-QC|P4-DEPLOY)
  -h | --help     this help

There is NO other sanctioned way to run the engine. A hand-rolled email sender is
FORBIDDEN; skipping a gate requires a logged owner token in
working/checkpoints/process_manifest.json.
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
PROVER="$SELF_DIR/tools/prove-email.py"
RUNNER="$SELF_DIR/run_email_engine.py"
[ -f "$PROVER" ] || die "prove-email.py not found at $PROVER"
[ -f "$RUNNER" ] || die "run_email_engine.py not found at $RUNNER"

if [ "$PLAN" -eq 0 ]; then
    [ -n "$RUN_DIR" ] || usage
    [ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
    RUN_DIR="$(cd "$RUN_DIR" && pwd)"
fi

PROC_MANIFEST="${RUN_DIR:-}/working/checkpoints/process_manifest.json"

# --- owner_skip_approval: a gate is skippable ONLY by a logged owner token ---
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
# GATE 1 — DEPS CHECK (python3; exit 6 EMAIL_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 present"
else
    if owner_skip_approved "EMAIL_DEPS_MISSING"; then
        echo "!! [$PROG] python3 missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        echo "EMAIL_DEPS_MISSING: python3" >&2; exit 6
    fi
fi

# ===========================================================================
# GATE 2 — BYPASS-SCAN (refuse hand-rolled email senders in the run directory)
# AF-EMAIL-SEND-BYPASS
# ===========================================================================
note "GATE 2/3 — BYPASS-SCAN (hand-rolled email sender detection)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
    SCAN_OUT="$(RUN_DIR="$RUN_DIR" SELF_DIR="$SELF_DIR" python3 - <<'PY' 2>&1
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
self_dir = os.path.realpath(os.environ["SELF_DIR"])
CANON = {"prove-email.py", "run_email_engine.py", "email_matcher.py",
         "email_matcher_cli.py", "emit_build_plan.py"}
re_smtp = re.compile(r"\bsmtplib\b|\bSMTP\s*\(", re.I)
re_esp  = re.compile(r"sendgrid|mailgun|postmarkapp|\bpostmark\b|ses\.send_email|send_raw_email", re.I)
re_ghl  = re.compile(r"services\.leadconnectorhq\.com|/conversations/messages|api/v1/emails/send", re.I)
re_send = re.compile(r"\bsend_email\b|\bsendEmail\b|\bdeliver_now\b|\bsend_message\s*\(", re.I)
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
        if re_smtp.search(src) or re_esp.search(src):
            findings.append((rel, "direct SMTP/ESP send (bypasses the draft-only handoff)"))
        elif re_ghl.search(src):
            findings.append((rel, "direct GoHighLevel/LeadConnector message send"))
        elif re_send.search(src):
            findings.append((rel, "a hand-rolled send_email/send_message call"))
if not findings:
    print("  OK: no hand-rolled email sender found in the run directory")
    sys.exit(0)
print("  HAND-ROLLED SENDER(S) DETECTED:", file=sys.stderr)
for rel, why in findings:
    print("    [AF-EMAIL-SEND-BYPASS] %s: %s" % (rel, why), file=sys.stderr)
sys.exit(5)
PY
)"; SCAN_RC=$?
    printf '%s\n' "$SCAN_OUT"
    if [ "$SCAN_RC" -eq 5 ]; then
        gate_fail "AF-EMAIL-SEND-BYPASS" 5 "a hand-rolled email sender is present in $RUN_DIR. \
The Email Engine deploys DRAFT-ONLY through the Skill-44 handoff; nothing sends from here. \
Delete the hand-rolled sender(s) above and re-run."
    fi
else
    echo "  (scan skipped: --plan or python3 absent)"
fi

# ===========================================================================
# GATE 3 — VERSION/HASH PIN (content hash of the enforcement pair)
# ===========================================================================
note "GATE 3/3 — VERSION/HASH PIN (prove-email.py + run_email_engine.py)"
version_hash_pin() {
    local computed=""
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "$PROVER" "$RUNNER" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "$PROVER" "$RUNNER" | shasum -a 256 | awk '{print $1}')"
    else
        echo "  (no sha256 tool; hash pin skipped)"; return 0
    fi
    echo "  enforcement hash (sha256 of prove-email.py+run_email_engine.py): $computed"
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
[ "$VHP_RC" -eq 0 ] || gate_fail "AF-ENGINE-HASH-PIN" 7 "the enforcement pair hash does not match the pinned head."

# ===========================================================================
# All gates passed — hand off to the deterministic orchestrator.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN — printing the canonical phase plan (gates ran)"
    exec python3 "$RUNNER" --plan
fi

note "ALL GATES PASSED — dispatching run_email_engine.py"
# FRONT-DOOR NONCE HANDSHAKE — run_email_engine.py exits 4 unless OC_EMAIL_ENTRY_NONCE
# matches the run-scoped 0600 file minted below. A random per-run nonce cannot be
# conjured from shipped source; it is consumed (deleted) after the run.
NONCE_DIR="$RUN_DIR/working/checkpoints"
NONCE_FILE="$NONCE_DIR/.email-entry-nonce"
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
OC_EMAIL_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_EMAIL_ENTRY_NONCE" ] || die "could not mint the front-door nonce. Refusing to run."
( umask 077; printf '%s' "$OC_EMAIL_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_EMAIL_ENTRY_NONCE
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

cmd=(python3 "$RUNNER" --run-dir "$RUN_DIR")
[ -n "$UPTO" ] && cmd+=(--upto "$UPTO")
note "run: ${cmd[*]}"
"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"

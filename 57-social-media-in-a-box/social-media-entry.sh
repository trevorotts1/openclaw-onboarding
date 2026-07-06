#!/usr/bin/env bash
# 57-social-media-in-a-box/social-media-entry.sh
#
# THE ONE SANCTIONED COMMAND TO RUN SOCIAL MEDIA IN A BOX.
# ============================================================================
# Cloned in spirit from 50-email-engine/email-engine-entry.sh.
#
# The skill's guardrails (the fail-closed provers + the deterministic phase
# machine run_social_media.py) only bind if the run goes THROUGH this entry.
# Before it hands off to the orchestrator it runs three fail-closed gates and
# mints a run-scoped nonce the orchestrator requires:
#
#   1. DEPS CHECK       — python3 must be present (exit 6, SMIB_DEPS_MISSING).
#   2. BYPASS-SCAN      — refuse if any hand-rolled SOCIAL POSTER exists in the
#                         run directory: a DIRECT platform API send (Facebook /
#                         Instagram Graph, LinkedIn, TikTok, YouTube, Pinterest)
#                         outside the sanctioned GHL-direct social-media-posting
#                         handoff (exit 5, AF-SM-POST-BYPASS). Posting goes
#                         ONLY through the client's own GHL location.
#   3. VERSION/HASH PIN — content hash of run_social_media.py + the 6 provers;
#                         if a pin file is present the hash MUST match (exit 7).
#
# A gate may be skipped ONLY by an explicit, LOGGED owner approval token in
# <run-dir>/working/checkpoints/process_manifest.json ("owner_skip_approval(s)":
# approved:true + approved_by + reason naming the gate code). Never silently.
#
# THE FORBIDDEN PATH:  python3 working/*post*.py   (a hand-rolled platform poster)
# THE ONLY PATH:       bash social-media-entry.sh --run-dir DIR --mode week
#
# EXIT CODES
#   0  — gates passed; orchestrator dispatched (its own exit is returned)
#   2  — usage error / orchestrator not found
#   5  — BYPASS-SCAN tripped (hand-rolled poster present, no owner skip)
#   6  — DEPS CHECK failed (SMIB_DEPS_MISSING)
#   7  — VERSION/HASH PIN failed (hash mismatch, no owner skip)
# ============================================================================

set -uo pipefail
PROG="social-media-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

usage() {
    cat >&2 <<EOF
$PROG — the ONE sanctioned command to run Social Media in a Box.

USAGE:
  bash $PROG --run-dir DIR --mode MODE [--plan]

REQUIRED:
  --run-dir DIR   the run directory (contains working/)
  --mode MODE     engine : week | day | carousel | video | podcast-cover | plan | clean
                  folds  : podcast | newsletter | blog | engage           (C3-C6)
                  creative: brief | campaign | client-copy | reactive     (M1-M4)
                  deferred: syndicate (v0.4.0, fails closed)               (C9)

OPTIONS:
  --plan          print the mode's canonical phase plan and exit (gates still run)
  -h | --help     this help

There is NO other sanctioned way to run the skill. A hand-rolled social poster is
FORBIDDEN; posting goes ONLY through the client's own GHL location. Skipping a gate
requires a logged owner token in working/checkpoints/process_manifest.json.
EOF
    exit 2
}

RUN_DIR="" MODE="" PLAN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
        --mode)    MODE="${2:-}"; shift 2 ;;
        --plan)    PLAN=1; shift ;;
        -h|--help) usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNNER="$SELF_DIR/run_social_media.py"
[ -f "$RUNNER" ] || die "run_social_media.py not found at $RUNNER"
[ -n "$MODE" ] || usage

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
    printf '!%.0s' {1..78} >&2; echo >&2
    exit "$exitcode"
}

# ===========================================================================
# GATE 1 — DEPS CHECK (python3; exit 6 SMIB_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 present"
else
    if owner_skip_approved "SMIB_DEPS_MISSING"; then
        echo "!! [$PROG] python3 missing but OWNER-APPROVED skip logged; proceeding." >&2
    else
        echo "SMIB_DEPS_MISSING: python3" >&2; exit 6
    fi
fi

# ===========================================================================
# GATE 2 — BYPASS-SCAN (refuse hand-rolled social posters in the run directory)
# AF-SM-POST-BYPASS
# ===========================================================================
note "GATE 2/3 — BYPASS-SCAN (hand-rolled social poster detection)"
if [ "$PLAN" -eq 0 ] && command -v python3 >/dev/null 2>&1; then
    SCAN_OUT="$(RUN_DIR="$RUN_DIR" SELF_DIR="$SELF_DIR" python3 - <<'PY' 2>&1
import os, re, sys
run_dir = os.path.realpath(os.environ["RUN_DIR"])
self_dir = os.path.realpath(os.environ["SELF_DIR"])
# A direct platform API call bypasses the sanctioned GHL-direct handoff.
re_platform = re.compile(
    r"graph\.facebook\.com|graph\.instagram\.com|api\.linkedin\.com|"
    r"open\.tiktokapis\.com|googleapis\.com/youtube|www\.googleapis\.com/youtube|"
    r"api\.pinterest\.com", re.I)
re_send = re.compile(r"\bpost_to_(?:facebook|instagram|linkedin|tiktok|youtube|pinterest)\b", re.I)
findings = []
for root, dirs, files in os.walk(run_dir):
    if os.path.realpath(root).startswith(self_dir):
        dirs[:] = []; continue
    for fn in files:
        if not fn.endswith(".py"):
            continue
        path = os.path.join(root, fn)
        if os.path.realpath(path).startswith(self_dir + os.sep):
            continue
        try:
            src = open(path, "r", errors="replace").read()
        except Exception:
            continue
        rel = os.path.relpath(path, run_dir)
        if re_platform.search(src):
            findings.append((rel, "direct platform API send (bypasses the GHL-direct handoff)"))
        elif re_send.search(src):
            findings.append((rel, "a hand-rolled platform poster function"))
if not findings:
    print("  OK: no hand-rolled social poster found in the run directory")
    sys.exit(0)
print("  HAND-ROLLED POSTER(S) DETECTED:", file=sys.stderr)
for rel, why in findings:
    print("    [AF-SM-POST-BYPASS] %s: %s" % (rel, why), file=sys.stderr)
sys.exit(5)
PY
)"; SCAN_RC=$?
    printf '%s\n' "$SCAN_OUT"
    if [ "$SCAN_RC" -eq 5 ]; then
        gate_fail "AF-SM-POST-BYPASS" 5 "a hand-rolled social poster is present in $RUN_DIR. \
Posting goes ONLY through the client's own GHL location (services.leadconnectorhq.com/social-media-posting). \
Delete the hand-rolled poster(s) above and re-run."
    fi
else
    echo "  (scan skipped: --plan or python3 absent)"
fi

# ===========================================================================
# GATE 3 — VERSION/HASH PIN (content hash of the engine + provers)
# ===========================================================================
note "GATE 3/3 — VERSION/HASH PIN (run_social_media.py + provers)"
PIN_INPUTS=("$RUNNER"
    "$SELF_DIR/scripts/preflight_gate.py" "$SELF_DIR/scripts/prove_bands.py"
    "$SELF_DIR/scripts/validate_contract.py" "$SELF_DIR/scripts/scrub_gate.py"
    "$SELF_DIR/scripts/build_manifest.py" "$SELF_DIR/scripts/ledger.py"
    "$SELF_DIR/scripts/label_deliverables.py" "$SELF_DIR/scripts/defer_stub.py"
    "$SELF_DIR/scripts/mc_board.py")
version_hash_pin() {
    local computed=""
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "${PIN_INPUTS[@]}" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "${PIN_INPUTS[@]}" | shasum -a 256 | awk '{print $1}')"
    else
        echo "  (no sha256 tool; hash pin skipped)"; return 0
    fi
    echo "  enforcement hash (sha256 of engine+provers): $computed"
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
[ "$VHP_RC" -eq 0 ] || gate_fail "AF-SM-ENGINE-HASH-PIN" 7 "the engine+provers hash does not match the pinned head."

# ===========================================================================
# All gates passed — hand off to the deterministic orchestrator.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN — printing the mode phase plan (gates ran)"
    exec python3 "$RUNNER" --mode "$MODE" --plan
fi

note "ALL GATES PASSED — dispatching run_social_media.py (mode=$MODE)"
# FRONT-DOOR NONCE HANDSHAKE — run_social_media.py exits 4 unless OC_SMIB_ENTRY_NONCE
# matches the run-scoped 0600 file minted below. A random per-run nonce cannot be
# conjured from shipped source; it is consumed (deleted) after the run.
NONCE_DIR="$RUN_DIR/working/checkpoints"
NONCE_FILE="$NONCE_DIR/.smib-entry-nonce"
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
OC_SMIB_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_SMIB_ENTRY_NONCE" ] || die "could not mint the front-door nonce. Refusing to run."
( umask 077; printf '%s' "$OC_SMIB_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_SMIB_ENTRY_NONCE
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

cmd=(python3 "$RUNNER" --mode "$MODE" --run-dir "$RUN_DIR")
note "run: ${cmd[*]}"
"${cmd[@]}"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"

#!/usr/bin/env bash
# 53-book-writer/book-writer-entry.sh
#
# THE ONE SANCTIONED COMMAND TO RUN THE BOOK WRITER ENGINE.
# ============================================================================
# Cloned in spirit from 55-product-bio/product-bio-entry.sh. The engine's
# guardrails (the fail-closed provers in scripts/, the deterministic
# assembler/certifier run_book_writer.py, the local-only labeled deliverable)
# only bind if the run goes THROUGH this entry. Before it hands off to the
# assembler it runs three fail-closed gates and mints a run-scoped nonce the
# assembler requires:
#
#   1. DEPS CHECK       — python3 must be present (exit 6, BW_DEPS_MISSING).
#   2. BYPASS-SCAN      — refuse if any hand-rolled EXTERNAL uploader/notifier
#                         exists in the run dir: Google Drive, Slack, Gmail/SMTP,
#                         an n8n webhook, an Airtable write, or a GHL call. The
#                         Book Writer is LOCAL-ONLY; delivery is a labeled bundle
#                         in ~/Downloads (exit 5, AF-BK-ENTRY-BYPASS).
#   3. VERSION/HASH PIN — content hash of the enforcement set (run_book_writer.py
#                         + _bw_common.py + the twelve provers); if
#                         ENGINE-PIN.sha256 is present the hash MUST match
#                         (exit 7, AF-BK-HASH-PIN).
#
# THE ONLY PATH:  bash book-writer-entry.sh --run-dir DIR [--plan]
#
# EXIT CODES
#   0  — gates passed; assembler dispatched (its own exit is returned)
#   2  — usage error / assembler not found
#   5  — BYPASS-SCAN tripped (hand-rolled external uploader/notifier present)
#   6  — DEPS CHECK failed (BW_DEPS_MISSING)
#   7  — VERSION/HASH PIN failed (hash mismatch)
# ============================================================================
set -uo pipefail
PROG="book-writer-entry.sh"

die() { echo "FATAL [$PROG]: $*" >&2; exit 2; }
note() { echo "=== [$PROG] $* ==="; }

usage() {
    cat >&2 <<EOF
$PROG — the ONE sanctioned command to run the Book Writer Engine.

USAGE:
  bash $PROG --run-dir DIR [--plan]

REQUIRED:
  --run-dir DIR   the book run directory (contains run/ authored artifacts)

OPTIONS:
  --plan          print the canonical phase plan and exit (gates still run)
  -h | --help     this help

There is NO other sanctioned way to run the engine. A hand-rolled external
uploader/notifier is FORBIDDEN (local-only delivery).
EOF
    exit 2
}

RUN_DIR="" PLAN=0
while [ $# -gt 0 ]; do
    case "$1" in
        --run-dir) RUN_DIR="${2:-}"; shift 2 ;;
        --plan)    PLAN=1; shift ;;
        -h|--help) usage ;;
        *) die "unknown argument: $1 (run with --help)" ;;
    esac
done

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
RUNNER="$SELF_DIR/run_book_writer.py"
SCRIPTS="$SELF_DIR/scripts"
[ -f "$RUNNER" ] || die "run_book_writer.py not found at $RUNNER"
[ -d "$SCRIPTS" ] || die "scripts/ not found at $SCRIPTS"

if [ "$PLAN" -eq 0 ]; then
    [ -n "$RUN_DIR" ] || usage
    [ -d "$RUN_DIR" ] || die "--run-dir not found: $RUN_DIR"
    RUN_DIR="$(cd "$RUN_DIR" && pwd)"
fi

# ===========================================================================
# GATE 1 — DEPS CHECK (python3; exit 6 BW_DEPS_MISSING)
# ===========================================================================
note "GATE 1/3 — DEPS CHECK (python3)"
if command -v python3 >/dev/null 2>&1; then
    echo "  OK: python3 present"
else
    echo "BW_DEPS_MISSING: python3" >&2; exit 6
fi

# ===========================================================================
# GATE 2 — BYPASS-SCAN (refuse hand-rolled external uploaders/notifiers)
# AF-BK-ENTRY-BYPASS
# ===========================================================================
note "GATE 2/3 — BYPASS-SCAN + HASH-PIN (Drive/Slack/Gmail/n8n/Airtable/GHL + enforcement pin)"
if [ "$PLAN" -eq 0 ]; then
    PROC_OUT="$(python3 "$SCRIPTS/prove_bw_process.py" --run-dir "$RUN_DIR" --skill-dir "$SELF_DIR" 2>&1)"
    PROC_RC=$?
    printf '%s\n' "$PROC_OUT"
    if [ "$PROC_RC" -ne 0 ]; then
        echo >&2
        echo "GATE FAILED: local-only delivery — no n8n / Airtable / Drive / Slack / Gmail / GHL;" >&2
        echo "the enforcement set must match its pin. Fix and re-run." >&2
        if printf '%s' "$PROC_OUT" | grep -q "AF-BK-ENTRY-BYPASS"; then exit 5; fi
        if printf '%s' "$PROC_OUT" | grep -q "AF-BK-HASH-PIN"; then exit 7; fi
        exit 2
    fi
    echo "  OK: no hand-rolled external sender + enforcement hash consistent"
else
    echo "  (scan skipped: --plan)"
fi

# ===========================================================================
# All gates passed — hand off to the deterministic assembler/certifier.
# ===========================================================================
if [ "$PLAN" -eq 1 ]; then
    note "PLAN — printing the canonical phase plan (gates ran)"
    exec python3 "$RUNNER" --plan
fi

note "ALL GATES PASSED — dispatching run_book_writer.py"
# FRONT-DOOR NONCE HANDSHAKE — run_book_writer.py exits 4 unless
# OC_BOOK_WRITER_ENTRY_NONCE matches the run-scoped 0600 file minted below.
NONCE_DIR="$RUN_DIR/run/checkpoints"
NONCE_FILE="$NONCE_DIR/.book-writer-entry-nonce"
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
OC_BOOK_WRITER_ENTRY_NONCE="$(_mint_nonce)"
[ -n "$OC_BOOK_WRITER_ENTRY_NONCE" ] || die "could not mint the front-door nonce. Refusing to run."
( umask 077; printf '%s' "$OC_BOOK_WRITER_ENTRY_NONCE" > "$NONCE_FILE" )
chmod 600 "$NONCE_FILE" 2>/dev/null || true
export OC_BOOK_WRITER_ENTRY_NONCE
trap 'rm -f "$NONCE_FILE" 2>/dev/null || true' EXIT INT TERM HUP

note "run: python3 $RUNNER --run-dir $RUN_DIR"
python3 "$RUNNER" --run-dir "$RUN_DIR"
_rc=$?
rm -f "$NONCE_FILE" 2>/dev/null || true
exit "$_rc"

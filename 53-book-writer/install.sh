#!/usr/bin/env bash
# 53-book-writer/install.sh — per-skill installer (idempotent).
# ============================================================================
# Mirrors 52/55: makes the entry, verify, and scripts executable, and (optionally)
# copies the skill into a destination skills dir. Re-running is safe — never aborts
# on `cp: identical` and never mutates anything but permissions + the copy target.
#
# USAGE:
#   bash install.sh                 # chmod +x in place (source checkout)
#   bash install.sh --dest DIR      # also copy the skill into DIR/53-book-writer/
# ============================================================================
set -uo pipefail
SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
DEST=""
while [ $# -gt 0 ]; do
    case "$1" in
        --dest) DEST="${2:-}"; shift 2 ;;
        -h|--help) echo "usage: bash install.sh [--dest DIR]"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 2 ;;
    esac
done

chmod_all() {
    local d="$1"
    chmod +x "$d/book-writer-entry.sh" "$d/run_book_writer.py" "$d/verify.sh" \
             "$d/verify-deps.sh" "$d/preflight.sh" "$d/qc-book-writer.sh" \
             "$d/install.sh" 2>/dev/null || true
    chmod +x "$d/scripts/"*.py 2>/dev/null || true
    chmod +x "$d/examples/golden-marcus-halloway/broken-variants/make_broken.py" 2>/dev/null || true
}

# SK2-09: the enforcement-set hash MUST be pinned. The pin is committed with the
# skill; if it is somehow absent at install time, mint it here so prove_bw_process
# (AF-BK-HASH-PIN) is enforced rather than fail-closed on a missing pin. The order
# of files MUST match prove_bw_process.ENFORCE_FILES exactly.
ENFORCE_REL=(
    "run_book_writer.py" "scripts/_bw_common.py"
    "scripts/prove_bw_intake.py" "scripts/prove_bw_titlelock.py"
    "scripts/prove_bw_stories.py" "scripts/prove_bw_chapters.py"
    "scripts/prove_bw_continuity.py" "scripts/prove_bw_tone.py"
    "scripts/prove_bw_challenge.py" "scripts/prove_bw_433.py"
    "scripts/prove_bw_placeholder.py" "scripts/prove_bw_noanthropic.py"
    "scripts/prove_bw_anon.py" "scripts/prove_bw_process.py"
)
mint_pin() {
    local d="$1"
    local pin="$d/ENGINE-PIN.sha256"
    local rel f computed
    local files=()
    [ -f "$pin" ] && return 0   # committed/present — never overwrite
    for rel in "${ENFORCE_REL[@]}"; do
        f="$d/$rel"
        [ -f "$f" ] || { echo "install: cannot mint ENGINE-PIN — missing $rel" >&2; return 0; }
        files+=("$f")
    done
    computed=""
    if command -v sha256sum >/dev/null 2>&1; then
        computed="$(cat "${files[@]}" | sha256sum | awk '{print $1}')"
    elif command -v shasum >/dev/null 2>&1; then
        computed="$(cat "${files[@]}" | shasum -a 256 | awk '{print $1}')"
    else
        echo "install: no sha256 tool; ENGINE-PIN not minted (prove_bw_process fails closed)" >&2
        return 0
    fi
    printf '%s\n' "$computed" > "$pin"
    echo "install: minted ENGINE-PIN.sha256 ($computed)"
}

if [ -n "$DEST" ]; then
    TARGET="$DEST/53-book-writer"
    mkdir -p "$TARGET"
    # cp -R with no abort on identical; rsync-like idempotent copy
    cp -R "$SELF_DIR/." "$TARGET/" 2>/dev/null || {
        echo "install: copy to $TARGET reported non-fatal diffs (idempotent) " >&2; }
    chmod_all "$TARGET"
    mint_pin "$TARGET"
    echo "Skill 53 (Book Writer) installed -> $TARGET"
else
    chmod_all "$SELF_DIR"
    mint_pin "$SELF_DIR"
    echo "Skill 53 (Book Writer) made executable in place -> $SELF_DIR"
fi
echo "Next: bash $SELF_DIR/preflight.sh   (probe client providers) ; bash $SELF_DIR/verify.sh   (self-check)"

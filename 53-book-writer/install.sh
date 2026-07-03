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

if [ -n "$DEST" ]; then
    TARGET="$DEST/53-book-writer"
    mkdir -p "$TARGET"
    # cp -R with no abort on identical; rsync-like idempotent copy
    cp -R "$SELF_DIR/." "$TARGET/" 2>/dev/null || {
        echo "install: copy to $TARGET reported non-fatal diffs (idempotent) " >&2; }
    chmod_all "$TARGET"
    echo "Skill 53 (Book Writer) installed -> $TARGET"
else
    chmod_all "$SELF_DIR"
    echo "Skill 53 (Book Writer) made executable in place -> $SELF_DIR"
fi
echo "Next: bash $SELF_DIR/preflight.sh   (probe client providers) ; bash $SELF_DIR/verify.sh   (self-check)"

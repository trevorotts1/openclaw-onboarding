#!/usr/bin/env bash
# scripts/wire-social-media.sh
#
# AC-14 — idempotent wiring for Social Media in a Box (Skill 57).
#
# Wires the unified ORGANIC social engine into an installed box (or verifies it
# in-repo): (1) ensures the shared universal-sops/social-media-craft/ SOP cluster
# is present under the skills root, (2) confirms the 57 engine tree is present,
# (3) registers the ONE weekly-theme cron (social-media-weekly-theme, 0 8 * * 6)
# via the engine's own idempotent registrar. Every step is check-then-act, so a
# second run is a no-op. Runs identically under `bash -c` and `zsh -c`.
#
# SAFE BY DEFAULT: the cron step is a DRY-RUN plan unless --apply is given, and
# the copy step is skipped when source and target resolve to the SAME directory
# (in-repo mode) so `cp` never aborts with "identical".
#
# USAGE:
#   bash scripts/wire-social-media.sh [--onboarding-dir DIR] [--skills-dir DIR] [--apply]
#     --onboarding-dir DIR   source repo tree (default: this script's repo root, or $ONBOARDING_DIR)
#     --skills-dir DIR       install target root (default: --onboarding-dir, or $SKILLS_DIR)
#     --apply                actually register the weekly-theme cron (default: dry-run plan)
#
# EXIT: 0 wired / 2 a required source is missing / 3 usage.

set -u

PROG="wire-social-media.sh"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SELF_DIR/.." && pwd)"

ONBOARDING_DIR="${ONBOARDING_DIR:-$REPO_ROOT}"
SKILLS_DIR="${SKILLS_DIR:-}"
APPLY=0

while [ $# -gt 0 ]; do
    case "$1" in
        --onboarding-dir) ONBOARDING_DIR="${2:-}"; shift 2 ;;
        --skills-dir)     SKILLS_DIR="${2:-}"; shift 2 ;;
        --apply)          APPLY=1; shift ;;
        -h|--help)        sed -n '2,27p' "$0"; exit 3 ;;
        *) echo "FATAL [$PROG]: unknown arg $1" >&2; exit 3 ;;
    esac
done

# Default the install target to the source tree (in-repo wiring / verification).
[ -n "$SKILLS_DIR" ] || SKILLS_DIR="$ONBOARDING_DIR"

ok()   { printf '  OK: %s\n' "$*"; }
warn() { printf '  WARN: %s\n' "$*" >&2; }
die()  { printf 'FATAL [%s]: %s\n' "$PROG" "$*" >&2; exit 2; }

# Canonicalize a directory path (portable; macOS has no coreutils realpath).
_canon() { ( cd "$1" 2>/dev/null && pwd -P ) || printf '%s' "$1"; }

# Idempotent tree copy that never aborts on identical: no-op when src==dst.
_copy_tree() {
    src="$1"; dst="$2"; label="$3"
    [ -d "$src" ] || die "missing source $label: $src"
    if [ "$(_canon "$src")" = "$(_canon "$dst")" ]; then
        ok "$label already in place (source == target, no copy needed)"
        return 0
    fi
    mkdir -p "$dst"
    cp -R "$src/." "$dst/" 2>/dev/null || cp -R "$src/." "$dst/" || true
    ok "$label wired to $dst"
}

echo "=== [$PROG] wiring Social Media in a Box (Skill 57) ==="
echo "  onboarding: $ONBOARDING_DIR"
echo "  skills:     $SKILLS_DIR"

# (1) Shared SOP cluster.
_copy_tree "$ONBOARDING_DIR/universal-sops/social-media-craft" \
           "$SKILLS_DIR/universal-sops/social-media-craft" \
           "universal-sops/social-media-craft"

# (2) Engine tree.
_copy_tree "$ONBOARDING_DIR/57-social-media-in-a-box" \
           "$SKILLS_DIR/57-social-media-in-a-box" \
           "57-social-media-in-a-box engine"

ENGINE="$SKILLS_DIR/57-social-media-in-a-box"
[ -f "$ENGINE/social-media-entry.sh" ] || die "engine entry missing after wire: $ENGINE/social-media-entry.sh"
chmod +x "$ENGINE/social-media-entry.sh" "$ENGINE/verify.sh" "$ENGINE/scripts/"*.sh 2>/dev/null || true

# (3) The ONE weekly-theme cron (idempotent; dry-run unless --apply).
REG="$ENGINE/scripts/register-social-cron.sh"
if [ -f "$REG" ]; then
    if [ "$APPLY" -eq 1 ]; then
        if bash "$REG" --apply; then ok "weekly-theme cron registered (social-media-weekly-theme, 0 8 * * 6)"
        else warn "cron registrar returned non-zero (see output above)"; fi
    else
        bash "$REG" >/dev/null 2>&1 || true
        ok "weekly-theme cron registrar present (dry-run; re-run with --apply to register)"
    fi
else
    warn "register-social-cron.sh not found under the engine (cron not wired)"
fi

echo "=== [$PROG] done ==="
exit 0

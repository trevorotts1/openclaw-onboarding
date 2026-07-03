#!/usr/bin/env bash
# scripts/verify-social-media.sh
#
# AC-14 — read-only verification that Social Media in a Box (Skill 57) is fully
# wired into the workforce. Asserts all five insertion-point kinds landed:
#   1. the shared universal-sops/social-media-craft/ SOP cluster (8 files)
#   2. the 57 engine tree (manifest + entry + orchestrator + verify)
#   3. the Start Here.md reusable-engine bullet
#   4. the README skill-inventory row
#   5. the 20 role-file Section-8 rows across the 5 consuming departments
#
# Idempotent + read-only (writes nothing). Runs identically under `bash -c` and
# `zsh -c`. Nonzero on ANY missing piece.
#
# USAGE:  bash scripts/verify-social-media.sh [--root DIR]
#           --root DIR   repo/skills root to check (default: this script's repo root)
#
# EXIT: 0 all wired / 1 one or more pieces missing.

set -u

PROG="verify-social-media.sh"
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$SELF_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
    case "$1" in
        --root) ROOT="${2:-}"; shift 2 ;;
        -h|--help) sed -n '2,21p' "$0"; exit 0 ;;
        *) echo "unknown arg: $1" >&2; exit 1 ;;
    esac
done

FAILS=0
ok()  { printf '  OK: %s\n' "$*"; }
bad() { printf '  FAIL: %s\n' "$*" >&2; FAILS=$((FAILS+1)); }

# Assert a file exists.
need_file() { if [ -f "$1" ]; then ok "$2"; else bad "$2 (missing: $1)"; fi; }
# Assert a fixed string is present in a file.
need_str()  { if [ -f "$1" ] && grep -qF -- "$2" "$1"; then ok "$3"; else bad "$3"; fi; }

echo "=== [$PROG] verifying Social Media in a Box (Skill 57) wiring under $ROOT ==="

# (1) Shared SOP cluster — the 8 mirror-of-email-craft files.
CRAFT="$ROOT/universal-sops/social-media-craft"
for f in README.md SOCIAL-PIPELINE-MANIFEST.json MASTER-SOCIAL-QC-AUTOFAIL-RULESET.md \
         SOP-SOCIAL-01-INTAKE.md SOP-SOCIAL-02-RUN.md SOP-SOCIAL-03-CREATIVE-INTERJECTION.md \
         SOP-SOCIAL-04-VERIFY.md SOP-SOCIAL-05-ENGAGE-REPORT.md; do
    need_file "$CRAFT/$f" "social-media-craft/$f"
done

# (2) Engine tree.
ENGINE="$ROOT/57-social-media-in-a-box"
for f in SOCIAL-MANIFEST.json social-media-entry.sh run_social_media.py verify.sh config/bands.json; do
    need_file "$ENGINE/$f" "engine/$f"
done

# (3) Start Here.md reusable-engine bullet.
SH="$ROOT/Start Here.md"
need_str "$SH" "Social Media in a Box (Skill 57)" "Start Here.md engine bullet present"
need_str "$SH" "universal-sops/social-media-craft/" "Start Here.md shared-procedure pointer present"

# (4) README skill-inventory row.
need_str "$ROOT/README.md" "| 57-social-media-in-a-box |" "README skill-inventory row present"

# (5) The 20 Section-8 role rows across the 5 consuming departments.
RL="$ROOT/23-ai-workforce-blueprint/templates/role-library"
WANT=20
COUNT=0
for rel in \
    social-media/director-of-social-media.md social-media/twitter-x-specialist.md \
    social-media/facebook-specialist.md social-media/instagram-specialist.md \
    social-media/linkedin-specialist.md social-media/tiktok-specialist.md \
    social-media/pinterest-specialist.md social-media/youtube-channel-specialist-organic-only.md \
    social-media/community-manager.md social-media/qc-role--social-media.md \
    marketing/chief-marketing-officer.md marketing/content-marketing-strategist.md \
    marketing/email-campaign-strategist.md marketing/conversion-copywriter.md \
    podcast/director-of-podcast.md podcast/audio-post-producer.md \
    graphics/social-media-graphics-specialist.md graphics/thumbnail--cover-designer.md \
    crm/tag--segmentation-specialist.md crm/automation-workflow-specialist.md; do
    f="$RL/$rel"
    if [ -f "$f" ] && grep -qF "Social Media in a Box (Skill 57)" "$f"; then
        COUNT=$((COUNT+1))
    else
        bad "Section-8 row missing in role file: $rel"
    fi
done
if [ "$COUNT" -eq "$WANT" ]; then
    ok "all $WANT role-file Section-8 rows present"
else
    bad "found $COUNT/$WANT role-file Section-8 rows"
fi

echo
if [ "$FAILS" -eq 0 ]; then
    echo "[$PROG] PASS — all five insertion-point kinds are wired."
    exit 0
else
    echo "[$PROG] FAIL — $FAILS wiring check(s) failed."
    exit 1
fi

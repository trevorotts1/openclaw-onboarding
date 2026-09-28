#!/usr/bin/env bash
# check-doc-currency-guards.sh — a handful of hand-authored prose lines that
# state a version/count as fact and are NOT covered by any existing marker or
# ledger, so they drift silently. Same pattern as
# scripts/check-readme-current-release.sh (a sibling, not a merge into it —
# that script is README-only; this one covers the other docs the 2026-09-28
# stale-docs sweep found drifting the same way), kept in a separate file so
# each guard's failure output names exactly one drifted claim.
#
# Guards in this file:
#   1. DIRECT-TO-AGENT-UPDATE-MESSAGE.md's "This release pairs with Command
#      Center vX.Y.Z" line must equal cc-compat.json's pinnedTag. Found stale
#      at v7.1.1 (the v25.0.4-era pin) while pinnedTag had moved to v7.6.70 —
#      nothing rolled it because it lives outside version-markers.json's
#      pure-token markers, same root cause as the README guard.
#   2. docs/interview-launch-recovery.md's "Paired releases: onboarding
#      vX.Y.Z / Command Center vX.Y.Z" line must equal /version and
#      cc-compat.json's pinnedTag. Found stale at v25.0.16 / v7.1.5.
#   3. The coaching-persona count quoted in TERMINOLOGY.md and MIGRATION.md
#      must equal the real blueprint directory count
#      (22-book-to-persona-coaching-leadership-system/personas/*), the same
#      ground truth AGENTS.md's N38 persona-count triad already uses. Found
#      stale at 81 (TERMINOLOGY.md) and 40 (MIGRATION.md) against a real
#      count of 99.
#
# Usage: bash scripts/check-doc-currency-guards.sh   (run from repo root)
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FAIL=0

# ── 1. DIRECT-TO-AGENT-UPDATE-MESSAGE.md paired Command Center version ─────
if [ -f DIRECT-TO-AGENT-UPDATE-MESSAGE.md ] && [ -f cc-compat.json ]; then
  PINNED_TAG=$(python3 -c "import json; print(json.load(open('cc-compat.json'))['commandCenter']['pinnedTag'])" 2>/dev/null || echo "MISSING")
  DTA_CC=$(grep -oE 'pairs with Command Center v[0-9]+\.[0-9]+\.[0-9]+' DIRECT-TO-AGENT-UPDATE-MESSAGE.md | head -1 | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
  if [ "$DTA_CC" != "$PINNED_TAG" ]; then
    echo "DRIFT: DIRECT-TO-AGENT-UPDATE-MESSAGE.md 'pairs with Command Center $DTA_CC' != cc-compat.json pinnedTag ($PINNED_TAG)"
    FAIL=1
  else
    echo "OK: DIRECT-TO-AGENT-UPDATE-MESSAGE.md paired Command Center matches cc-compat.json pinnedTag ($DTA_CC)"
  fi
else
  echo "WARNING: DIRECT-TO-AGENT-UPDATE-MESSAGE.md or cc-compat.json not found — skipped."
fi

# ── 2. docs/interview-launch-recovery.md paired releases line ──────────────
if [ -f docs/interview-launch-recovery.md ] && [ -f version ] && [ -f cc-compat.json ]; then
  REPO_VER=$(head -1 version | tr -d '[:space:]')
  PINNED_TAG=$(python3 -c "import json; print(json.load(open('cc-compat.json'))['commandCenter']['pinnedTag'])" 2>/dev/null || echo "MISSING")
  ILR_LINE=$(grep -E '^Paired releases: onboarding v[0-9]+\.[0-9]+\.[0-9]+ / Command Center v[0-9]+\.[0-9]+\.[0-9]+' docs/interview-launch-recovery.md | head -1 || echo "")
  ILR_ONB=$(echo "$ILR_LINE" | grep -oE 'onboarding v[0-9]+\.[0-9]+\.[0-9]+' | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
  ILR_CC=$(echo "$ILR_LINE" | grep -oE 'Command Center v[0-9]+\.[0-9]+\.[0-9]+' | grep -oE 'v[0-9]+\.[0-9]+\.[0-9]+' || echo "MISSING")
  if [ "$ILR_ONB" != "$REPO_VER" ]; then
    echo "DRIFT: docs/interview-launch-recovery.md 'Paired releases' onboarding version ($ILR_ONB) != /version ($REPO_VER)"
    FAIL=1
  else
    echo "OK: docs/interview-launch-recovery.md paired onboarding version matches /version ($ILR_ONB)"
  fi
  if [ "$ILR_CC" != "$PINNED_TAG" ]; then
    echo "DRIFT: docs/interview-launch-recovery.md 'Paired releases' Command Center version ($ILR_CC) != cc-compat.json pinnedTag ($PINNED_TAG)"
    FAIL=1
  else
    echo "OK: docs/interview-launch-recovery.md paired Command Center version matches cc-compat.json pinnedTag ($ILR_CC)"
  fi
else
  echo "WARNING: docs/interview-launch-recovery.md, version, or cc-compat.json not found — skipped."
fi

# ── 3. Coaching-persona count (TERMINOLOGY.md, MIGRATION.md) ───────────────
PERSONA_DIR="22-book-to-persona-coaching-leadership-system/personas"
if [ -d "$PERSONA_DIR" ]; then
  REAL_PERSONA_COUNT=$(find "$PERSONA_DIR" -mindepth 1 -maxdepth 1 -type d | wc -l | tr -d '[:space:]')

  if [ -f TERMINOLOGY.md ]; then
    TERM_COUNT=$(grep -oE 'One of the [0-9]+ personas in the .coaching-personas. library' TERMINOLOGY.md | head -1 | grep -oE '[0-9]+' || echo "MISSING")
    if [ "$TERM_COUNT" != "$REAL_PERSONA_COUNT" ]; then
      echo "DRIFT: TERMINOLOGY.md states $TERM_COUNT coaching personas, real count is $REAL_PERSONA_COUNT ($PERSONA_DIR/*)"
      FAIL=1
    else
      echo "OK: TERMINOLOGY.md persona count matches $PERSONA_DIR ($TERM_COUNT)"
    fi
  fi

  if [ -f MIGRATION.md ]; then
    MIGRATION_COUNT=$(grep -oE 'Indexing [0-9]+ personas' MIGRATION.md | head -1 | grep -oE '[0-9]+' || echo "MISSING")
    if [ "$MIGRATION_COUNT" != "$REAL_PERSONA_COUNT" ]; then
      echo "DRIFT: MIGRATION.md states $MIGRATION_COUNT personas, real count is $REAL_PERSONA_COUNT ($PERSONA_DIR/*)"
      FAIL=1
    else
      echo "OK: MIGRATION.md persona count matches $PERSONA_DIR ($MIGRATION_COUNT)"
    fi
  fi
else
  echo "WARNING: $PERSONA_DIR not found — persona count checks skipped."
fi

if [ "$FAIL" -ne 0 ]; then
  echo ""
  echo "FIX: edit the drifted line(s) above by hand to match their source of truth"
  echo "     (cc-compat.json pinnedTag, /version, or the real persona directory count)."
  exit 1
fi

echo ""
echo "All doc-currency guards agree with their source of truth."

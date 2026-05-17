#!/usr/bin/env bash
# Orchestrate all v2.1 migrations end-to-end.
#
# Run this ONCE after upgrading to v10.5.0 to:
#   1. Verify platform detection
#   2. Patch every existing SOUL.md / IDENTITY.md with the persona deferral clause
#   3. Re-index every persona at section level (replaces character-chunk index)
#   4. Create role-level workspaces for every existing department
#
# Safe to re-run. Each step is idempotent.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
SKILL23_SCRIPTS="$REPO_ROOT/23-ai-workforce-blueprint/scripts"

echo "============================================================"
echo "OpenClaw v2.1 Migration Runner"
echo "============================================================"
echo ""

# --- Step 1: Platform detection ---
echo "[1/4] Platform detection..."
if ! source "$SHARED_UTILS/detect-platform.sh"; then
  echo "  FAIL: cannot detect platform"
  exit 1
fi
echo "  Platform: $OPENCLAW_PLATFORM"
echo "  Root:     $OPENCLAW_ROOT"
echo "  Workspace: $OPENCLAW_WORKSPACE"
echo "  Company root: $OPENCLAW_COMPANY_ROOT"
echo ""

# --- Step 2: Migrate persona deferral clauses ---
echo "[2/4] Persona Governance Override migration..."
if [ -d "$OPENCLAW_COMPANY_ROOT" ]; then
  python3 "$SHARED_UTILS/migrate-deferral-clauses.py" || {
    echo "  WARN: migration script exited with non-zero status — continuing"
  }
else
  echo "  SKIP: $OPENCLAW_COMPANY_ROOT does not exist (no companies built yet)"
fi
echo ""

# --- Step 3: Section-level Gemini re-index ---
echo "[3/4] Gemini section-level re-index..."
PERSONAS_DIR="$OPENCLAW_WORKSPACE/coaching-personas/personas"
if [ -d "$PERSONAS_DIR" ] && [ -n "$(ls -A "$PERSONAS_DIR" 2>/dev/null)" ]; then
  python3 "$SKILL23_SCRIPTS/gemini-section-indexer.py" --reindex-all || {
    echo "  WARN: section indexer exited with non-zero status — continuing"
  }
else
  echo "  SKIP: no personas at $PERSONAS_DIR (run Skill 22 first)"
fi
echo ""

# --- Step 4: Role-level workspace creation ---
echo "[4/4] Role-level workspace creation..."
if [ -d "$OPENCLAW_COMPANY_ROOT" ]; then
  python3 "$SKILL23_SCRIPTS/post-build-role-workspaces.py" || {
    echo "  WARN: role workspace creator exited with non-zero status — continuing"
  }
else
  echo "  SKIP: no companies built yet"
fi
echo ""

echo "============================================================"
echo "v2.1 migrations complete."
echo "Next: run verify-v2.1-installation.sh to smoke-test everything."
echo "============================================================"

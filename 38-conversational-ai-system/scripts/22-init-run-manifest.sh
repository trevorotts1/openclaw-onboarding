#!/usr/bin/env bash
# 22-init-run-manifest.sh
# Skill 38 — initialize a Run Manifest at the start of a playbook run.
# Idempotent: if a run-manifest-*.md exists from today's date in $MASTER_FILES_DIR,
# append a "## Re-entry" stamp to it; otherwise create a new manifest from the template.
# OS-aware via uname -s. bash -n clean.

set -euo pipefail

OS_NAME="$(uname -s)"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATE_DEFAULT="${SCRIPT_DIR}/../templates/run-manifest-template.md"
TEMPLATE_PATH="${RUN_MANIFEST_TEMPLATE:-$TEMPLATE_DEFAULT}"

: "${MASTER_FILES_DIR:?MASTER_FILES_DIR must be set (path to operator master files folder)}"

if [ ! -f "$TEMPLATE_PATH" ]; then
  echo "[22-init-run-manifest] template not found: $TEMPLATE_PATH" >&2
  exit 1
fi

mkdir -p "$MASTER_FILES_DIR"

TODAY="$(date '+%Y-%m-%d')"
NOW_ISO="$(date '+%Y-%m-%dT%H:%M:%S%z')"
TIMESTAMP_SLUG="$(date '+%Y%m%d-%H%M%S')"

OPERATOR_NAME=""
if command -v git >/dev/null 2>&1; then
  OPERATOR_NAME="$(git config user.name 2>/dev/null || true)"
fi
if [ -z "$OPERATOR_NAME" ]; then
  OPERATOR_NAME="${USER:-unspecified}"
fi

EXISTING_TODAY="$(find "$MASTER_FILES_DIR" -maxdepth 1 -type f -name "run-manifest-${TODAY}*.md" 2>/dev/null | sort | head -n1 || true)"

if [ -n "$EXISTING_TODAY" ]; then
  {
    printf '\n## Re-entry — %s\n' "$NOW_ISO"
    printf 'Operator: %s\n' "$OPERATOR_NAME"
    printf 'OS: %s\n' "$OS_NAME"
    printf 'MASTER_FILES_DIR: %s\n' "$MASTER_FILES_DIR"
  } >> "$EXISTING_TODAY"
  echo "$EXISTING_TODAY"
  exit 0
fi

NEW_MANIFEST="${MASTER_FILES_DIR}/run-manifest-${TIMESTAMP_SLUG}.md"
cp "$TEMPLATE_PATH" "$NEW_MANIFEST"

{
  printf '\n<!-- init by 22-init-run-manifest.sh on %s -->\n' "$NOW_ISO"
  printf '<!-- Operator: %s | OS: %s | MASTER_FILES_DIR: %s -->\n' \
    "$OPERATOR_NAME" "$OS_NAME" "$MASTER_FILES_DIR"
} >> "$NEW_MANIFEST"

echo "$NEW_MANIFEST"

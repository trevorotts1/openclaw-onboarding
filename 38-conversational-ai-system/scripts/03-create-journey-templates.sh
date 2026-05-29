#!/usr/bin/env bash
# 03-create-journey-templates.sh — Skill 38 / Step 9.28 (Customer Journey Templates Library, v5.11)
# Copies the 8 journey templates + registry from this skill's templates/ folder
# into <MASTER_FILES_DIR>/journey-templates/. Idempotent (does NOT overwrite).

set -euo pipefail
# The pointer file written by 01-locate-master-files-folder.sh contains a BARE PATH
# (one line: the master-files directory), NOT shell `KEY=value` assignments. It must be
# READ, never `source`d — `. <file>` tries to EXECUTE its contents, and when the path is
# a directory bash errors "Is a directory" (or runs the path as a command). Read it into
# MASTER_FILES_DIR with cat instead.
MASTER_FILES_POINTER="$HOME/.openclaw/.skill-38-master-files-dir"
if [ -z "${MASTER_FILES_DIR:-}" ] && [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(head -n1 "$MASTER_FILES_POINTER" | tr -d '\r')"
fi
: "${MASTER_FILES_DIR:?MASTER_FILES_DIR not set — run 01-locate-master-files-folder.sh first}"

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
SRC="$SKILL_DIR/templates/journey-templates"
DST="$MASTER_FILES_DIR/journey-templates"

[ -d "$SRC" ] || { echo "[skill 38] ERR: $SRC not found"; exit 1; }
mkdir -p "$DST"

for type in coach e-commerce saas service-provider course-creator real-estate consulting wellness; do
  mkdir -p "$DST/$type"
  if [ ! -f "$DST/$type/journey.md" ]; then
    cp "$SRC/$type/journey.md" "$DST/$type/journey.md"
    echo "[skill 38] installed $type/journey.md"
  else
    echo "[skill 38] $type/journey.md already exists — preserved"
  fi
done

if [ ! -f "$DST/registry.md" ]; then
  cp "$SRC/registry.md" "$DST/registry.md"
  echo "[skill 38] installed registry.md"
else
  echo "[skill 38] registry.md already exists — preserved"
fi

echo "[skill 38] journey templates installed at $DST"

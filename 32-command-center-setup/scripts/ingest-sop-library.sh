#!/usr/bin/env bash
# Skill 32 — SOP V2 Library Ingestion (Mac mini variant)
# Introduced in onboarding v10.13.29 (Skill 32 v6.6.0) — Mac mirror of
# the VPS v10.14.37 release that introduced the library.
#
# Downloads the canonical 2,555-SOP V2 library from this repo's release
# asset and ingests it into the local mission-control.db. Applies
# migration 028 (V2 schema additions) if not already applied.
#
# Usage (from inside the Mac mini's OpenClaw install):
#   ingest-sop-library.sh <client-slug> [release-tag]
#
# - <client-slug>: e.g. "trevor", "sample-client". Used to scope
#                  client_template_vars rows.
# - [release-tag]: pin a release (default: latest stable, set in
#                  ONBOARDING_VERSION below).

set -euo pipefail

CLIENT="${1:?usage: ingest-sop-library.sh <client-slug> [release-tag]}"
TAG="${2:-v10.13.29}"

REPO="trevorotts1/openclaw-onboarding"
ASSET="sops-library-v2.jsonl.gz"
URL="https://github.com/${REPO}/releases/download/${TAG}/${ASSET}"

DB="/data/projects/command-center/mission-control.db"
WORK="$(mktemp -d -t sop-library-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

if [ ! -f "$DB" ]; then
  echo "[sop-library] mission-control.db not found at $DB — Skill 32 dashboard must be installed first."
  exit 2
fi

echo "[sop-library] client=$CLIENT  tag=$TAG"
echo "[sop-library] downloading $URL"
curl -fsSL -o "$WORK/${ASSET}" "$URL"
gunzip -k "$WORK/${ASSET}"
JSONL="$WORK/${ASSET%.gz}"
COUNT=$(wc -l < "$JSONL" | tr -d ' ')
echo "[sop-library] downloaded $COUNT SOP records"

# Backup before any writes
BACKUP="${DB}.bak-pre-sop-v2-$(date -u +%Y%m%dT%H%M%SZ)"
cp "$DB" "$BACKUP"
echo "[sop-library] backed up DB → $BACKUP"

# Hand off to the Python ingester (sits next to this script)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/ingest-sop-library.py" "$CLIENT" "$JSONL" "$DB"

echo "[sop-library] done. backup retained at $BACKUP"

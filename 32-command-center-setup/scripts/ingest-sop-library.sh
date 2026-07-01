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

# Resolve mission-control.db (mirror add-department.sh:115-126, Mac FIRST) so this
# "Mac mini variant" actually resolves on a Mac. The old hardcoded VPS-only
# /data/projects path made this script exit 2 on every Mac. $MISSION_CONTROL_DB
# overrides for non-standard boxes.
DB=""
if [ -n "${MISSION_CONTROL_DB:-}" ] && [ -f "${MISSION_CONTROL_DB}" ]; then
  DB="${MISSION_CONTROL_DB}"
else
  for _cand in \
    "$HOME/projects/command-center/mission-control.db" \
    "$HOME/projects/mission-control/mission-control.db" \
    "/opt/mission-control/mission-control.db" \
    "/app/mission-control.db" \
    "/data/projects/command-center/mission-control.db"; do
    if [ -f "$_cand" ]; then DB="$_cand"; break; fi
  done
fi
WORK="$(mktemp -d -t sop-library-XXXXXX)"
trap 'rm -rf "$WORK"' EXIT

if [ -z "$DB" ] || [ ! -f "$DB" ]; then
  echo "[sop-library] mission-control.db not found (checked \$MISSION_CONTROL_DB, Mac ~/projects/command-center, VPS /data/projects/command-center) — Skill 32 dashboard must be installed first."
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

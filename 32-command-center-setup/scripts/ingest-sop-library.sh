#!/usr/bin/env bash
# Skill 32 — SOP V2 Library Ingestion (Mac mini variant)
# Introduced in onboarding v10.13.29 (Skill 32 v6.6.0) — Mac mirror of
# the VPS v10.14.37 release that introduced the library.
#
# Downloads the canonical 2,617-SOP V2 library from this repo's release
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

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ----------------------------------------------------------------------------
# MANIFEST PIN (v20.1.0). tag / sha256 / canonical row count now come from ONE
# committed file — shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json — so the
# updater (update-skills.sh Step U6c), this script, and
# shared-utils/embedding_health.py's coverage leg can never disagree about
# which asset is canonical or how many rows a populated box must hold.
# Hardcoded fallbacks preserve the pre-manifest behaviour on a box whose
# shared-utils tree has not been refreshed yet.
# ----------------------------------------------------------------------------
SOP_LIB_MANIFEST="${SOP_LIB_MANIFEST:-$SCRIPT_DIR/../../shared-utils/sop-library/SOP-LIBRARY-MANIFEST.json}"
_mf() {  # _mf <key> <fallback> — read a scalar from the manifest, never fatal
  local _k="$1" _fb="$2" _v=""
  if [ -f "$SOP_LIB_MANIFEST" ] && command -v python3 >/dev/null 2>&1; then
    _v="$(python3 -c 'import json,sys
try:
    v=json.load(open(sys.argv[1])).get(sys.argv[2])
    print("" if v is None else v)
except Exception:
    print("")' "$SOP_LIB_MANIFEST" "$_k" 2>/dev/null || true)"
  fi
  printf '%s' "${_v:-$_fb}"
}

TAG="${2:-$(_mf release_tag v10.13.29)}"
REPO="trevorotts1/openclaw-onboarding"
ASSET="$(_mf asset sops-library-v2.jsonl.gz)"
EXPECTED_SHA256="$(_mf sha256 '')"
CANONICAL_SOP_COUNT="$(_mf canonical_sop_count 2617)"
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

# ----------------------------------------------------------------------------
# ALREADY-POPULATED SKIP GATE (v20.1.0). A box already at/above the manifest's
# canonical population is left COMPLETELY untouched: no download, no backup, no
# write, no network I/O at all. This is what makes the step safe to run on
# EVERY update of EVERY box:
#   - a healthy box (library already ingested) is never clobbered or re-ingested,
#     and its client-authored SOPs are never at risk;
#   - a re-run is free and provably idempotent;
#   - only an under-populated box does any work.
# SOP_LIB_FORCE=1 overrides (operator escape hatch for a genuine re-ingest).
# ----------------------------------------------------------------------------
CURRENT_COUNT="$(sqlite3 "file:${DB}?mode=ro" \
  "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='sops';" 2>/dev/null || echo 0)"
if [ "${CURRENT_COUNT:-0}" = "1" ]; then
  CURRENT_COUNT="$(sqlite3 "file:${DB}?mode=ro" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo 0)"
else
  CURRENT_COUNT=0
fi
echo "[sop-library] db=$DB  current sops rows=$CURRENT_COUNT  canonical=$CANONICAL_SOP_COUNT"
if [ "${SOP_LIB_FORCE:-0}" != "1" ] && [ "${CURRENT_COUNT:-0}" -ge "${CANONICAL_SOP_COUNT:-2617}" ] 2>/dev/null; then
  echo "[sop-library] SKIP — this box already holds $CURRENT_COUNT sops rows (>= canonical $CANONICAL_SOP_COUNT)."
  echo "[sop-library] Nothing downloaded, nothing written, DB untouched. (SOP_LIB_FORCE=1 to re-ingest anyway.)"
  echo "[sop-library] downloaded 0 SOP records (skipped — already populated)"
  exit 0
fi

echo "[sop-library] downloading $URL"
curl -fsSL -o "$WORK/${ASSET}" "$URL"

# sha256 HARD GATE — a truncated/corrupt/substituted asset is NEVER ingested.
# Mirrors provision_sop_embeddings.py's sha256 contract. Skipped only when the
# manifest carries no pin (pre-manifest fallback path).
if [ -n "$EXPECTED_SHA256" ]; then
  if command -v shasum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(shasum -a 256 "$WORK/${ASSET}" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null 2>&1; then
    ACTUAL_SHA256="$(sha256sum "$WORK/${ASSET}" | awk '{print $1}')"
  else
    ACTUAL_SHA256=""
  fi
  if [ -n "$ACTUAL_SHA256" ] && [ "$ACTUAL_SHA256" != "$EXPECTED_SHA256" ]; then
    echo "[sop-library] FATAL: sha256 mismatch for $ASSET@$TAG" >&2
    echo "[sop-library]   expected $EXPECTED_SHA256" >&2
    echo "[sop-library]   actual   $ACTUAL_SHA256" >&2
    echo "[sop-library] REFUSING to ingest a corrupt/substituted library. DB untouched." >&2
    exit 5
  fi
  echo "[sop-library] sha256 verified against manifest pin"
fi

gunzip -k "$WORK/${ASSET}"
JSONL="$WORK/${ASSET%.gz}"
COUNT=$(wc -l < "$JSONL" | tr -d ' ')
echo "[sop-library] downloaded $COUNT SOP records"
if [ "${COUNT:-0}" -lt 1 ]; then
  echo "[sop-library] FATAL: asset produced 0 SOP records — refusing to ingest an empty library. DB untouched." >&2
  exit 6
fi

# Backup before any writes
BACKUP="${DB}.bak-pre-sop-v2-$(date -u +%Y%m%dT%H%M%SZ)"
cp "$DB" "$BACKUP"
echo "[sop-library] backed up DB → $BACKUP"

# Hand off to the Python ingester (sits next to this script)
python3 "$SCRIPT_DIR/ingest-sop-library.py" "$CLIENT" "$JSONL" "$DB"

# ----------------------------------------------------------------------------
# POST-INGEST POPULATION ASSERT (v20.1.0). The ingester swallows per-row upsert
# errors into an `errors` tally and still exits 0, so "it ran" is NOT proof
# "it landed". Re-read the table and REFUSE to report success unless the box
# actually reached the manifest's canonical population. This is the difference
# between a green update and a green LIE.
# ----------------------------------------------------------------------------
# WAL-checkpoint + bounded retry before the ro population read. A live Command
# Center (next-server) keeps this DB open in WAL mode and may not have
# checkpointed the just-committed ingest, so a bare ?mode=ro read can race and
# see 0/stale rows — falsely aborting a genuinely-successful ingest before the
# stamp write (observed fleet-wide). Best-effort checkpoint (tolerate lock
# contention) then re-read, up to a few times. The assert below is UNCHANGED:
# it still FATALs on a real short-fall after the retries — a green LIE is still
# refused, only the false negative is fixed.
FINAL_COUNT=0
for _sop_try in 1 2 3 4 5 6; do
  sqlite3 "$DB" "PRAGMA wal_checkpoint(TRUNCATE);" >/dev/null 2>&1 || true
  FINAL_COUNT="$(sqlite3 "file:${DB}?mode=ro" "SELECT COUNT(*) FROM sops;" 2>/dev/null || echo 0)"
  if [ "${FINAL_COUNT:-0}" -ge "${CANONICAL_SOP_COUNT:-2617}" ] 2>/dev/null; then
    break
  fi
  sleep 2
done
if [ "${FINAL_COUNT:-0}" -lt "${CANONICAL_SOP_COUNT:-2617}" ] 2>/dev/null; then
  echo "[sop-library] FATAL: post-ingest population is $FINAL_COUNT rows, BELOW the canonical $CANONICAL_SOP_COUNT." >&2
  echo "[sop-library] The ingest did NOT land. DB backup retained at $BACKUP." >&2
  echo "[sop-library] This box's SOP library is INCOMPLETE — do not treat this update as successful." >&2
  exit 7
fi
echo "[sop-library] population verified: $FINAL_COUNT sops rows (>= canonical $CANONICAL_SOP_COUNT)"

# P4-03 step 2 — provision the shipped SOP-embeddings asset (zero client-key
# embed calls for the shared library). Runs AFTER the SOP content ingest so
# `sops` rows exist to join against. Additive/idempotent: no-ops when no asset
# has been published yet (SOP-EMBEDDINGS-MANIFEST.json asset_rebuild_required),
# skips a re-download when the box is already canonical, and NEVER blocks this
# script's own exit code (mirrors install.sh Step 6b / update-skills.sh U6b's
# additive treatment of provision_persona_index).
SOP_EMBED_DIR="$(cd "$SCRIPT_DIR/../../shared-utils/sop-embed-once" 2>/dev/null && pwd || true)"
if [ -n "$SOP_EMBED_DIR" ] && [ -f "$SOP_EMBED_DIR/SOP-EMBEDDINGS-MANIFEST.json" ]; then
  python3 "$SOP_EMBED_DIR/provision_sop_embeddings.py" \
    "$SOP_EMBED_DIR/SOP-EMBEDDINGS-MANIFEST.json" "$DB" \
    || echo "[sop-library] note: SOP-embeddings provisioning step returned non-zero (additive; SOP content ingest already succeeded above)"
else
  echo "[sop-library] note: SOP-EMBEDDINGS-MANIFEST.json not found — skipping SOP-embeddings provisioning (additive)"
fi

# ----------------------------------------------------------------------------
# EMBEDDING-COST TRANSPARENCY (v20.1.0). Ingesting CONTENT rows costs nothing —
# every write above is a local sqlite upsert and provision_sop_embeddings.py
# makes ZERO embedding API calls (it is a straight ATTACH+INSERT of a shipped
# asset, and it no-ops entirely while SOP-EMBEDDINGS-MANIFEST.json carries
# asset_rebuild_required:true, which it does today — no embeddings asset has
# ever been published). So the rows this script just landed are UNEMBEDDED.
# Say so OUT LOUD: embedding them is a real, metered cost on the CLIENT's own
# Gemini key and must stay an explicit operator decision, never an invisible
# side effect of an update.
# ----------------------------------------------------------------------------
EMB_ROWS="$(sqlite3 "file:${DB}?mode=ro" "SELECT COUNT(*) FROM sop_embeddings;" 2>/dev/null || echo 0)"
if [ "${EMB_ROWS:-0}" -lt "${FINAL_COUNT:-0}" ] 2>/dev/null; then
  echo "[sop-library] NOTE (operator): $FINAL_COUNT sops row(s) present, $EMB_ROWS embedded."
  echo "[sop-library]   The newly-ingested rows are NOT embedded. This script made ZERO embedding"
  echo "[sop-library]   API calls and incurred ZERO cost on the client's key — by design."
  echo "[sop-library]   Semantic SOP search stays keyword-only for the unembedded rows until an"
  echo "[sop-library]   operator explicitly runs the embed step, which BILLS THE CLIENT'S OWN"
  echo "[sop-library]   Gemini key. Do not run it as part of a routine roll."
fi

echo "[sop-library] done. backup retained at $BACKUP"

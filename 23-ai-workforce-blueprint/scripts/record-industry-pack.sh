#!/usr/bin/env bash
# record-industry-pack.sh — PRD-2.15: Record the industry vertical pack that
# ran for this interview into .workforce-build-state.json as the industryPack
# provenance object.
#
# DATA FLOW:
#   Phase 0 research + early answers blob
#       └→ shared-utils/industry-detector.py --file <blob>
#              └→ {industry_slug, confidence, matched_signals, needs_confirmation}
#              └→ writes state.industryPack
#
# USAGE:
#   record-industry-pack.sh --blob-file <path>           # auto-detect from blob
#   record-industry-pack.sh --slug <slug> --source owner-confirmed
#   record-industry-pack.sh --slug <slug> --source owner-corrected --confidence 1.0
#   record-industry-pack.sh --blob-file <path> --source auto-detected
#
# FLAGS:
#   --blob-file <path>      Text blob to run through industry-detector.py
#   --slug <slug>           Override slug (skip detector)
#   --source <enum>         auto-detected | owner-confirmed | owner-corrected
#   --confidence <0-1>      Override confidence (default: from detector output)
#   --state <path>          Override state file path (default: resolved from platform)
#   --dry-run               Print what would be written; don't write
#
# EXIT CODES:
#   0  success
#   1  error (missing required arg, state not found, write failed)
#
# NOTE: If detector returns slug="unknown" (no signals), still writes the provenance
# object with slug="unknown" so the field EXISTS. build-workforce.py treats "unknown"
# as a loud warning (not a hard block) — a legitimately unclassifiable business should
# not be un-buildable.
#
# PRD-2.15 / v11.11.0
set -euo pipefail

# ── Platform detection (no tildes) ──────────────────────────────────────────
if [ -d /data/.openclaw/workspace ]; then
  STATE_DIR=/data/.openclaw/workspace
elif [ -d "${HOME}/.openclaw/workspace" ]; then
  STATE_DIR="${HOME}/.openclaw/workspace"
else
  echo "ERROR: cannot find .openclaw/workspace directory" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_ROOT="$(cd "$SKILL_DIR/.." && pwd)"
DETECTOR="${REPO_ROOT}/shared-utils/industry-detector.py"

# ── Parse args ───────────────────────────────────────────────────────────────
BLOB_FILE=""
SLUG_OVERRIDE=""
SOURCE_OVERRIDE=""
CONFIDENCE_OVERRIDE=""
STATE_OVERRIDE=""
DRY_RUN=false

while [ $# -gt 0 ]; do
  case "$1" in
    --blob-file)   BLOB_FILE="$2";           shift 2 ;;
    --slug)        SLUG_OVERRIDE="$2";       shift 2 ;;
    --source)      SOURCE_OVERRIDE="$2";     shift 2 ;;
    --confidence)  CONFIDENCE_OVERRIDE="$2"; shift 2 ;;
    --state)       STATE_OVERRIDE="$2";      shift 2 ;;
    --dry-run)     DRY_RUN=true;             shift   ;;
    *) echo "unknown flag: $1" >&2; exit 1 ;;
  esac
done

STATE="${STATE_OVERRIDE:-${STATE_DIR}/.workforce-build-state.json}"
if [ ! -f "$STATE" ]; then
  echo "ERROR: state file not found: $STATE" >&2
  exit 1
fi

NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# ── Determine slug + confidence + matched_signals ────────────────────────────
if [ -n "$SLUG_OVERRIDE" ]; then
  SLUG="$SLUG_OVERRIDE"
  CONFIDENCE="${CONFIDENCE_OVERRIDE:-1.0}"
  MATCHED_SIGNALS="[]"
  SOURCE="${SOURCE_OVERRIDE:-owner-confirmed}"
else
  if [ -z "$BLOB_FILE" ]; then
    echo "ERROR: provide --blob-file <path> or --slug <slug>" >&2
    exit 1
  fi
  if [ ! -f "$BLOB_FILE" ]; then
    echo "ERROR: blob file not found: $BLOB_FILE" >&2
    exit 1
  fi
  if [ ! -f "$DETECTOR" ]; then
    echo "ERROR: industry-detector.py not found at $DETECTOR" >&2
    exit 1
  fi

  DETECT_OUT=$(python3 "$DETECTOR" --file "$BLOB_FILE" --format json 2>/dev/null || true)
  if [ -z "$DETECT_OUT" ]; then
    echo "WARN: industry-detector.py returned no output — defaulting to slug=unknown" >&2
    DETECT_OUT='{"industry_slug":"unknown","confidence":0.0,"matched_signals":[]}'
  fi

  SLUG=$(echo "$DETECT_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('industry_slug','unknown'))")
  CONFIDENCE=$(echo "$DETECT_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('confidence',0.0))")
  MATCHED_SIGNALS=$(echo "$DETECT_OUT" | python3 -c "import json,sys; d=json.load(sys.stdin); print(json.dumps(d.get('matched_signals',[])))")
  SOURCE="${SOURCE_OVERRIDE:-auto-detected}"
fi

# Log the unknown slug case per spec
if [ "$SLUG" = "unknown" ]; then
  echo "WARN: industry slug is 'unknown' — no strong signals detected. Will write provenance but build-workforce.py will warn loudly. Phase 5 confirmation was expected to set the slug." >&2
fi

# Validate source enum
case "$SOURCE" in
  auto-detected|owner-confirmed|owner-corrected) ;;
  *) echo "ERROR: --source must be auto-detected|owner-confirmed|owner-corrected, got: $SOURCE" >&2; exit 1 ;;
esac

# Build the industryPack object
INDUSTRY_PACK_JSON=$(python3 - <<PYEOF
import json
print(json.dumps({
    "slug": "${SLUG}",
    "confidence": float("${CONFIDENCE}"),
    "source": "${SOURCE}",
    "matchedSignals": ${MATCHED_SIGNALS},
    "detectedAt": "${NOW}",
}))
PYEOF
)

if [ "$DRY_RUN" = true ]; then
  echo "[DRY-RUN] Would write industryPack to $STATE:"
  echo "$INDUSTRY_PACK_JSON" | python3 -m json.tool
  exit 0
fi

# ── Atomic write ─────────────────────────────────────────────────────────────
TMP="${STATE}.tmp.$$"
jq --argjson pack "$INDUSTRY_PACK_JSON" \
   '.industryPack = $pack' \
   "$STATE" > "$TMP"
mv -f "$TMP" "$STATE"

echo "record-industry-pack: wrote industryPack.slug=${SLUG} source=${SOURCE} confidence=${CONFIDENCE} to $STATE"

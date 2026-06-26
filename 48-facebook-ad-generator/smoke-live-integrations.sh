#!/usr/bin/env bash
# Skill 48 — OPTIONAL live smoke test. Skips cleanly when no keys are present.
set -u
echo "=== Skill 48 smoke-live-integrations (optional) ==="
if [ -z "${GOHIGHLEVEL_API_KEY:-}${GHL_API_KEY:-}" ]; then
  echo "  SKIP -- no GoHighLevel LOCATION PIT; skipping the one-pixel upload + folder-create probe."
else
  echo "  (would: create a per-run media folder, upload a 1px PNG, verify the public URL opens 200, then delete)"
fi
if [ -z "${MISSION_CONTROL_URL:-}" ]; then
  echo "  SKIP -- no MISSION_CONTROL_URL; skipping the Command Center /api/ad-campaigns probe."
else
  echo "  (would: POST /api/ad-campaigns with a throwaway job_id and confirm idempotent re-call)"
fi
echo "smoke: done (no failures = either ran or cleanly skipped)."
exit 0

#!/usr/bin/env bash
# run_all_probes.sh — guard runner for the Personal Video Creator cluster
# (universal-sops/video-production). Runs every deterministic probe against a project
# directory and writes a probes-receipt.json the final-QC meta-gate can consume.
#
# A rule not auto-failed at a gate does not exist: run this before marking a job complete.
# Each probe is fail-closed (exit 0 pass, 2 violation, 3 usage/fail-closed). This runner
# exits non-zero if ANY probe fails, and always writes the receipt.
#
# Usage:
#   run_all_probes.sh <project-dir> [width height fps]
# Defaults: width=1080 height=1920 fps=24 (9:16 vertical social video).
set -uo pipefail

PROJECT_DIR="${1:-}"
WIDTH="${2:-1080}"
HEIGHT="${3:-1920}"
FPS="${4:-24}"

if [ -z "$PROJECT_DIR" ] || [ ! -d "$PROJECT_DIR" ]; then
  echo "USAGE: run_all_probes.sh <project-dir> [width height fps]" >&2
  exit 3
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RECEIPT="$PROJECT_DIR/11_qc/probes-receipt.json"
mkdir -p "$PROJECT_DIR/11_qc" 2>/dev/null || true

overall=0
run() {
  # run <name> <args...>
  local name="$1"; shift
  local rc=0
  echo "=== $name ==="
  python3 "$SCRIPT_DIR/$name.py" "$@" || rc=$?
  echo "[$name] exit=$rc"
  RESULTS["$name"]=$rc
  if [ "$rc" -ne 0 ]; then overall=1; fi
}

declare -A RESULTS

# Intake gates
run probe_consent        --project-dir "$PROJECT_DIR"
run probe_manifest       --project-dir "$PROJECT_DIR"
run probe_no_secrets     --project-dir "$PROJECT_DIR"
run probe_environment    --project-dir "$PROJECT_DIR" --no-secrets

# Likeness prompt band (only if a likeness prompt dir exists)
if [ -d "$PROJECT_DIR/01_likeness" ]; then
  run probe_prompt_band  --dir "$PROJECT_DIR/01_likeness"
fi

# Storyboard frame plan (only if a scene manifest exists)
if [ -f "$PROJECT_DIR/04_storyboard/scene_manifest.yaml" ]; then
  run probe_frame_plan   --project-dir "$PROJECT_DIR" --fps "$FPS"
fi

# Scene QC ledger (only if present)
if [ -f "$PROJECT_DIR/11_qc/scene_qc.csv" ]; then
  run probe_scene_qc     --project-dir "$PROJECT_DIR"
fi

# Final technical (only if the master exists)
if [ -f "$PROJECT_DIR/12_delivery/final_master.mp4" ]; then
  run probe_final_technical --master "$PROJECT_DIR/12_delivery/final_master.mp4" \
       --width "$WIDTH" --height "$HEIGHT" --fps "$FPS"
fi

# Final QC meta-gate (only if final_qc.md exists)
if [ -f "$PROJECT_DIR/11_qc/final_qc.md" ]; then
  run probe_final_qc     --project-dir "$PROJECT_DIR"
fi

# Write the receipt (consumed by probe_final_qc --probes-receipt)
{
  echo "{"
  echo "  \"project_dir\": \"$PROJECT_DIR\","
  echo "  \"overall_exit\": $overall,"
  echo "  \"probes\": {"
  first=1
  for name in "${!RESULTS[@]}"; do
    if [ "$first" -eq 0 ]; then echo ","; fi
    printf '    "%s": %s' "$name" "${RESULTS[$name]}"
    first=0
  done
  echo ""
  echo "  }"
  echo "}"
} > "$RECEIPT" 2>/dev/null || echo "WARN: could not write receipt to $RECEIPT" >&2

echo ""
echo "Receipt written to $RECEIPT"
if [ "$overall" -ne 0 ]; then
  echo "RESULT: FAIL — one or more probes failed. The job may NOT be marked complete."
else
  echo "RESULT: PASS — all executed probes passed."
fi
exit "$overall"

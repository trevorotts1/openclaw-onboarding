#!/usr/bin/env bash
# =============================================================================
# RESCUE RANGERS :: stamp-rescue-escalation-section.sh
# Renders scripts/rescue-escalation-section.md.tpl with a box's real tokens and
# appends it to that box's AGENTS.md IFF the marker is absent (idempotent).
# (Topic-4 FIX 4-E — kills R5 "template drift risk at onboarding". Runnable now;
#  install.sh wiring on a fresh box is DEFERRED to the operator/onboarding roll.)
# -----------------------------------------------------------------------------
# The repo template stays the SINGLE SOURCE OF TRUTH. This script is what an
# install.sh client-role step (or the operator's propagate roll) calls so a newly
# onboarded box gets the escalation INSTRUCTIONS, not just the env vars.
#
# MARKER: "## Escalate to Rescue Rangers" (same marker propagate-rescue-webhook.sh
# checks) — present => no-op, so re-running never duplicates the section.
#
# USAGE:
#   stamp-rescue-escalation-section.sh --agents PATH/AGENTS.md \
#       --person "Jane" --client "acme" --agent "Aria" \
#       --box-name "acme-mac" --box-type "Mac Mini" \
#       --oc-version "2026.5.22" --return-to "123456" [--tpl PATH]
#   stamp-rescue-escalation-section.sh --self-test
# =============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MARKER='## Escalate to Rescue Rangers'

# Default template: walk up to the repo root and find scripts/rescue-escalation-section.md.tpl.
_default_tpl() {
  local d="$HERE"
  for _ in 1 2 3 4 5 6 7 8; do
    if [ -f "$d/scripts/rescue-escalation-section.md.tpl" ]; then
      echo "$d/scripts/rescue-escalation-section.md.tpl"; return 0
    fi
    d="$(dirname "$d")"
  done
  return 1
}

render() {
  # render TPL PERSON CLIENT AGENT BOX_NAME BOX_TYPE OC_VERSION RETURN_TO
  local tpl="$1"; shift
  local person="$1" client="$2" agent="$3" box_name="$4" box_type="$5" oc_version="$6" return_to="$7"
  # Use python for safe substitution (no sed metachar pitfalls in tokens).
  PERSON="$person" CLIENT="$client" AGENT="$agent" BOX_NAME="$box_name" \
  BOX_TYPE="$box_type" OC_VERSION="$oc_version" RETURN_TO="$return_to" \
  python3 - "$tpl" <<'PY'
import os, sys
tpl = open(sys.argv[1], encoding="utf-8").read()
for k in ("PERSON","CLIENT","AGENT","BOX_NAME","BOX_TYPE","OC_VERSION","RETURN_TO"):
    tpl = tpl.replace("{{%s}}" % k, os.environ.get(k, ""))
sys.stdout.write(tpl)
PY
}

stamp() {
  local agents="$1" tpl="$2"; shift 2
  if [ -f "$agents" ] && grep -qF "$MARKER" "$agents"; then
    echo "[stamp-rescue] marker present in $agents — no-op (idempotent)."
    return 0
  fi
  mkdir -p "$(dirname "$agents")"
  { [ -f "$agents" ] && printf '\n'; render "$tpl" "$@"; } >> "$agents"
  echo "[stamp-rescue] appended escalation section to $agents."
}

self_test() {
  echo "[stamp-rescue] self-test: render tokens + idempotent append"
  local tpl; tpl="$(_default_tpl)" || { echo "template not found" >&2; return 1; }
  local tmp; tmp="$(mktemp -d)"
  local agents="$tmp/AGENTS.md"
  printf '# Agent Instructions\n\nExisting content.\n' > "$agents"
  stamp "$agents" "$tpl" "Jane Doe" "acme" "Aria" "acme-mac" "Mac Mini" "2026.5.22" "123456"
  grep -qF "$MARKER" "$agents" || { echo "FAIL: marker not appended"; return 1; }
  grep -qF "acme-mac" "$agents" || { echo "FAIL: BOX_NAME token not rendered"; return 1; }
  grep -qF '{{PERSON}}' "$agents" && { echo "FAIL: unrendered token left"; return 1; }
  local n1; n1="$(grep -cF "$MARKER" "$agents")"
  # re-run must NOT duplicate
  stamp "$agents" "$tpl" "Jane Doe" "acme" "Aria" "acme-mac" "Mac Mini" "2026.5.22" "123456"
  local n2; n2="$(grep -cF "$MARKER" "$agents")"
  [ "$n1" = "1" ] && [ "$n2" = "1" ] || { echo "FAIL: section duplicated ($n1 -> $n2)"; return 1; }
  echo "  render case: PASS (tokens filled, no unrendered {{TOKEN}})"
  echo "  idempotency case: PASS (marker present => second run is a no-op)"
  rm -rf "$tmp"
  echo "[stamp-rescue] self-test: PASS"
}

# ---- arg parse ----
AGENTS=""; TPL=""; PERSON=""; CLIENT=""; AGENT=""; BOX_NAME=""; BOX_TYPE=""; OC_VERSION=""; RETURN_TO=""
if [ "${1:-}" = "--self-test" ]; then self_test; exit $?; fi
while [ $# -gt 0 ]; do
  case "$1" in
    --agents) AGENTS="$2"; shift 2 ;;
    --tpl) TPL="$2"; shift 2 ;;
    --person) PERSON="$2"; shift 2 ;;
    --client) CLIENT="$2"; shift 2 ;;
    --agent) AGENT="$2"; shift 2 ;;
    --box-name) BOX_NAME="$2"; shift 2 ;;
    --box-type) BOX_TYPE="$2"; shift 2 ;;
    --oc-version) OC_VERSION="$2"; shift 2 ;;
    --return-to) RETURN_TO="$2"; shift 2 ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done
[ -n "$AGENTS" ] || { echo "--agents is required (or --self-test)" >&2; exit 2; }
[ -n "$TPL" ] || TPL="$(_default_tpl)" || { echo "template not found; pass --tpl" >&2; exit 2; }
stamp "$AGENTS" "$TPL" "$PERSON" "$CLIENT" "$AGENT" "$BOX_NAME" "$BOX_TYPE" "$OC_VERSION" "$RETURN_TO"

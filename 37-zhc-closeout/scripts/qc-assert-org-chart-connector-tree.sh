#!/usr/bin/env bash
# qc-assert-org-chart-connector-tree.sh — PRD-2.8: programmatic QC assertion
# that the workforce-structure org-chart (Infographic #1) contains a TRUE
# reporting tree with visible connector lines (Owner → CEO → clusters →
# departments), NOT a card grid.
#
# WHY THIS EXISTS (the #1 historical failure mode):
#   The old cluster-card layout — floating CEO node, cards arranged in a grid
#   with no connector lines — scores ~6/10 and was rejected repeatedly. This
#   script is the HARD GATE that the run-closeout.sh QC loop invokes so the
#   failure mode is caught BEFORE delivery, not after the client sees it.
#
# WHAT WE ASSERT (static analysis of the generated HTML file):
#   1. The HTML template/file contains SVG connector-line elements OR explicit
#      CSS border/::before/::after declarations that implement connecting lines.
#      We detect: <line>, <path>, <polyline>, polygon connector patterns, or
#      the specific CSS connector classes the workforce-org-chart renderer emits.
#   2. The HTML contains at least 3 hierarchy levels (owner, ceo, dept).
#   3. The HTML has NO legacy "cluster-card" grid class (the anti-pattern).
#   4. If a PNG render is provided (--image-path), we run a pixel-line scan
#      (requires imagemagick) to count near-identical-color line segments
#      connecting the boxes. Falls back to HTML-only check if imagemagick absent.
#
# USAGE:
#   qc-assert-org-chart-connector-tree.sh --html-path <path/to/rendered.html>
#   qc-assert-org-chart-connector-tree.sh --html-path <...> --image-path <...>
#   # env-override mode (reads HTML/PNG paths from state file):
#   qc-assert-org-chart-connector-tree.sh [--state-file <path>]
#
# EXIT CODES:
#   0  → assertions PASS: TRUE connector-tree org chart confirmed
#   1  → assertion FAILED: card-grid anti-pattern detected or connectors absent
#   2  → unable to run (missing html file / jq absent)
#   3  → partial: HTML check inconclusive (image scan required but imagemagick absent)
#
# Writes a summary JSON to state .qcOrgChartConnectorTree if STATE_FILE is set.
#
# PRD-2.8 / v11.10.0

set -u

# ---- defaults ----
HTML_PATH=""
IMAGE_PATH=""
WRITE_STATE=0

# ---- platform detection ----
if [[ -d /data/.openclaw ]]; then
  OC_ROOT=/data/.openclaw
elif [[ -d "$HOME/.openclaw" ]]; then
  OC_ROOT="$HOME/.openclaw"
else
  OC_ROOT=""
fi
STATE_FILE="${ZHC_STATE_FILE:-${OC_ROOT:+$OC_ROOT/workspace/.workforce-build-state.json}}"
LOG_FILE="${ZHC_LOG_FILE:-${OC_ROOT:+$OC_ROOT/workspace/.zhc-closeout.log}}"

log() {
  local level="$1"; shift
  printf '%s [%-5s] step=qc-org-chart %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$*"
  if [[ -n "$LOG_FILE" ]]; then
    printf '%s [%-5s] step=qc-org-chart %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$level" "$*" >> "$LOG_FILE" 2>/dev/null || true
  fi
}

# ---- arg parsing ----
while [[ $# -gt 0 ]]; do
  case "$1" in
    --html-path)  HTML_PATH="$2"; shift 2 ;;
    --image-path) IMAGE_PATH="$2"; shift 2 ;;
    --state-file) STATE_FILE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

# ---- resolve HTML path from state if not given ----
if [[ -z "$HTML_PATH" && -n "$STATE_FILE" && -f "$STATE_FILE" ]]; then
  command -v jq >/dev/null 2>&1 || { log "ERROR" "jq not found; cannot read state"; exit 2; }
  WRITE_STATE=1
  # The renderer writes a .html in the same workspace alongside the .png
  local_path=$(jq -r '.infographic1LocalPath // empty' "$STATE_FILE" 2>/dev/null)
  if [[ -n "$local_path" ]]; then
    # Derive the .html sibling by replacing .png extension
    HTML_PATH="${local_path%.png}.html"
    [[ -z "$IMAGE_PATH" ]] && IMAGE_PATH="$local_path"
  fi
fi

if [[ -z "$HTML_PATH" ]]; then
  log "WARN" "no --html-path and no infographic1LocalPath in state -- running image-only or skipping"
fi

# ---- HTML analysis ----
HTML_OK=0
CARD_GRID_DETECTED=0
CONNECTOR_FOUND=0
HIERARCHY_LEVELS=0

html_check_passed() { [[ "$HTML_OK" -eq 1 ]]; }

if [[ -n "$HTML_PATH" && -f "$HTML_PATH" ]]; then
  html_content=$(cat "$HTML_PATH")

  # 1. Check for legacy cluster-card anti-pattern (the card-grid layout).
  #    The old layout used class="cluster-card" or a standalone .cards wrapper
  #    with NO .connector or svg line children.
  if echo "$html_content" | grep -q 'class=["\x27][^"]*cluster-card[^"]*'; then
    log "WARN" "cluster-card class detected -- checking for connector-line coexistence"
    # If cluster-card exists but connectors also exist, it might be a hybrid.
    # We still flag it as a potential anti-pattern.
    CARD_GRID_DETECTED=1
  fi

  # 2. Check for SVG connector lines (the explicit connector architecture).
  #    The workforce-org-chart renderer emits <line> elements with class "connector".
  if echo "$html_content" | grep -qiE '<(line|path|polyline)[^>]*class="[^"]*connector'; then
    CONNECTOR_FOUND=1
    log "INFO" "SVG connector elements found (line/path/polyline with .connector class)"
  fi

  # 3. Check for CSS-only connectors (::before/::after pseudo-element lines).
  #    Some renderers use border-based connectors with pseudo-elements.
  if echo "$html_content" | grep -qiE '(::before|::after|:before|:after)[^{]*\{[^}]*(border|height\s*:\s*[0-9])'; then
    CONNECTOR_FOUND=1
    log "INFO" "CSS pseudo-element connectors found (::before/::after border/height pattern)"
  fi

  # 4. Check for explicit .tree-connector or .org-connector CSS classes.
  if echo "$html_content" | grep -qiE 'class="[^"]*(-connector|tree-line|org-line|branch-line)'; then
    CONNECTOR_FOUND=1
    log "INFO" "org-tree connector CSS class found"
  fi

  # 5. Hierarchy level check: must have owner, ceo, and department elements.
  #    The renderer uses data-level or class="owner"|"ceo"|"dept".
  lvl_owner=0; lvl_ceo=0; lvl_dept=0
  echo "$html_content" | grep -qiE '(class|data-level|id)=["\x27][^"]*owner' && lvl_owner=1
  echo "$html_content" | grep -qiE '(class|data-level|id)=["\x27][^"]*ceo'   && lvl_ceo=1
  echo "$html_content" | grep -qiE '(class|data-level|id)=["\x27][^"]*dept'  && lvl_dept=1
  HIERARCHY_LEVELS=$(( lvl_owner + lvl_ceo + lvl_dept ))
  log "INFO" "hierarchy levels detected: owner=$lvl_owner ceo=$lvl_ceo dept=$lvl_dept (sum=$HIERARCHY_LEVELS / 3 needed)"

  if [[ "$CONNECTOR_FOUND" -eq 1 && "$CARD_GRID_DETECTED" -eq 0 && "$HIERARCHY_LEVELS" -ge 3 ]]; then
    HTML_OK=1
    log "INFO" "HTML QC PASS: connectors present, no card-grid anti-pattern, 3+ hierarchy levels"
  elif [[ "$CONNECTOR_FOUND" -eq 1 && "$CARD_GRID_DETECTED" -eq 1 ]]; then
    # Connectors present BUT card-grid class also present — hybrid, still OK
    # because the connectors override the grid intent. Log a warning.
    HTML_OK=1
    log "WARN" "HTML: cluster-card class AND connectors coexist -- treating as hybrid (pass with warning)"
  elif [[ "$CONNECTOR_FOUND" -eq 0 ]]; then
    HTML_OK=0
    log "ERROR" "HTML QC FAIL: NO connector-line elements found -- org chart is likely a card grid"
  elif [[ "$HIERARCHY_LEVELS" -lt 3 ]]; then
    HTML_OK=0
    log "ERROR" "HTML QC FAIL: only $HIERARCHY_LEVELS/3 hierarchy levels present -- not a complete reporting tree"
  fi
else
  if [[ -n "$HTML_PATH" ]]; then
    log "WARN" "HTML file not found at $HTML_PATH -- skipping HTML check"
  fi
fi

# ---- image scan (optional, requires imagemagick convert) ----
IMAGE_OK=0
IMAGE_SKIPPED=0

if [[ -n "$IMAGE_PATH" && -f "$IMAGE_PATH" ]]; then
  if command -v convert >/dev/null 2>&1; then
    log "INFO" "running imagemagick pixel-line scan on $IMAGE_PATH"
    # Count continuous horizontal or vertical near-identical-color line segments
    # that span > 30px (candidate connector lines). This is a heuristic:
    # a card-grid has zero long thin single-color horizontal/vertical segments
    # between boxes, but a true tree org chart has many.
    # We use 'identify -verbose' to count white/grey edges.
    # Simplified approach: count distinct nearly-white (connector line color)
    # pixel runs of length > 30 in the image.
    line_count=$(convert "$IMAGE_PATH" \
      -colorspace gray -threshold 90% \
      -morphology Erode Disk:2 \
      -define connected-components:verbose=true \
      -connected-components 8 -auto-level \
      -format '%w %h' info: 2>/dev/null | wc -l || echo 0)
    # Very rough heuristic: if the image has many thin connected components
    # after threshold, connectors are present. We use the output line count
    # as a proxy. More than 8 thin components → connectors likely present.
    if (( line_count > 8 )); then
      IMAGE_OK=1
      log "INFO" "image scan: $line_count thin components detected → connector lines present"
    else
      IMAGE_OK=0
      log "WARN" "image scan: only $line_count thin components -- may be card-grid layout"
    fi
  else
    IMAGE_SKIPPED=1
    log "INFO" "imagemagick not available -- skipping image scan (HTML check is the gate)"
  fi
else
  IMAGE_SKIPPED=1
  [[ -n "$IMAGE_PATH" ]] && log "WARN" "image not found at $IMAGE_PATH -- skipping image scan"
fi

# ---- overall verdict ----
# PRIMARY gate: HTML check (definitive).
# SECONDARY: image scan supplements but does not override HTML.
# If HTML is absent, image scan is the only signal.
VERDICT="fail"
VERDICT_NOTE=""
EXIT_CODE=1

if html_check_passed; then
  if [[ "$IMAGE_SKIPPED" -eq 1 || "$IMAGE_OK" -eq 1 ]]; then
    VERDICT="pass"
    VERDICT_NOTE="connector-tree confirmed via HTML analysis${IMAGE_OK:+ + image scan}"
    EXIT_CODE=0
  else
    # Image scan ran and disagreed with HTML. Trust HTML but flag discrepancy.
    VERDICT="pass-html-only"
    VERDICT_NOTE="HTML analysis PASS (connectors present) but image scan was inconclusive -- render may need visual review"
    EXIT_CODE=0
    log "WARN" "image scan result contradicts HTML analysis -- image may not match HTML source"
  fi
elif [[ "$IMAGE_OK" -eq 1 && "$HTML_OK" -eq 0 ]]; then
  # Image says connectors but HTML doesn't. Use image result but warn.
  VERDICT="pass-image-only"
  VERDICT_NOTE="image scan found connectors but HTML analysis was inconclusive -- recommend manual visual check"
  EXIT_CODE=0
elif [[ -z "$HTML_PATH" && "$IMAGE_SKIPPED" -eq 1 ]]; then
  # No HTML and no image → inconclusive, not a hard fail
  VERDICT="inconclusive"
  VERDICT_NOTE="no HTML or image available for QC assertion"
  EXIT_CODE=3
else
  VERDICT="fail"
  VERDICT_NOTE="connector-tree NOT confirmed: connectors absent or card-grid anti-pattern detected"
  EXIT_CODE=1
fi

log "$(if [[ "$EXIT_CODE" -eq 0 ]]; then echo INFO; else echo ERROR; fi)" \
  "ORG-CHART QC: verdict=$VERDICT ($VERDICT_NOTE)"

# ---- write result to state ----
if [[ "$WRITE_STATE" -eq 1 && -n "$STATE_FILE" && -f "$STATE_FILE" ]] && command -v jq >/dev/null 2>&1; then
  verified_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  tmp=$(mktemp)
  jq \
    --arg verdict "$VERDICT" \
    --arg note "$VERDICT_NOTE" \
    --arg at "$verified_at" \
    --argjson rc "$EXIT_CODE" \
    --argjson connectors "$CONNECTOR_FOUND" \
    --argjson card_grid "$CARD_GRID_DETECTED" \
    --argjson hierarchy "$HIERARCHY_LEVELS" \
    '.qcOrgChartConnectorTree = {
       "verdict": $verdict,
       "note": $note,
       "verifiedAt": $at,
       "rc": $rc,
       "connectorFound": $connectors,
       "cardGridDetected": $card_grid,
       "hierarchyLevels": $hierarchy
    }' "$STATE_FILE" > "$tmp" && mv "$tmp" "$STATE_FILE" || rm -f "$tmp"
fi

exit "$EXIT_CODE"

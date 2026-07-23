#!/usr/bin/env bash
# tests/unit/test_generate_cover_probe.sh
#
# REGRESSION GUARD — U033: cover-gen gate content-validity probe.
#
# The probe_downloaded_image() function in generate_cover.sh verifies that a
# downloaded file is a real JPEG/PNG image with dimensions >= COVER_MIN_SIDE
# and square aspect ratio within 2% tolerance. It rejects HTML error pages,
# undersized images, and non-square content BEFORE finalize.
#
# WHAT THIS FILE PROVES (hermetic: temp dirs, synthetic images via ffmpeg, no
# network, no real Kie API):
#
#   T1  a valid 1400x1400 JPEG passes the probe (return 0)
#   T2  an HTML file (wrong format) fails the probe (return non-zero)
#   T3  an undersized 100x100 JPEG fails the probe (return non-zero)
#   T4  MUTATION PROOF: mutate the dimension check to accept any size, verify
#       T3 turns RED (probe passes when it should fail), revert, verify GREEN
#
# Run: bash tests/unit/test_generate_cover_probe.sh

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$REPO_ROOT/58-podcast-production-engine/scripts/generate_cover.sh"

PASS=0; FAIL=0
ok()  { echo "  ok   — $1"; PASS=$((PASS+1)); }
bad() { echo "  FAIL — $1"; FAIL=$((FAIL+1)); }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Source the script to get probe_downloaded_image and its dependencies.
# We need to stub out the parts that would fail without a full environment.
COVER_MIN_SIDE=1400
COVER_MAX_SIDE=3000
COVER_MAX_BYTES=524288

log()  { :; }  # silence log output during tests
err()  { echo "[ERR] $*" >&2; }
int_from() { awk '{printf "%d", $1}' <<<"${1:-0}"; }

# Extract probe_downloaded_image from the script (lines 164-200).
# We eval it in this shell so it has access to our stubs.
eval "$(sed -n '164,200p' "$SCRIPT")"

echo "=== cover-gen probe tests (U033) ==="

# ---------------------------------------------------------------------------
# T1 — valid 1400x1400 JPEG passes the probe
# ---------------------------------------------------------------------------
VALID_JPEG="$TMP/valid_1400x1400.jpg"
ffmpeg -y -v error -f lavfi -i "color=c=red:s=1400x1400:d=1" -frames:v 1 "$VALID_JPEG" 2>/dev/null
if [[ ! -f "$VALID_JPEG" ]]; then
  bad "T1: could not create valid 1400x1400 JPEG fixture"
else
  if probe_downloaded_image "$VALID_JPEG"; then
    ok "T1: valid 1400x1400 JPEG passes the probe (return 0)"
  else
    bad "T1: valid 1400x1400 JPEG FAILED the probe (should pass)"
  fi
fi

# ---------------------------------------------------------------------------
# T2 — HTML file (wrong format) fails the probe
# ---------------------------------------------------------------------------
HTML_FILE="$TMP/error_404.html"
cat > "$HTML_FILE" <<'HTML'
<!DOCTYPE html>
<html>
<head><title>404 Not Found</title></head>
<body><h1>404 Not Found</h1><p>The requested URL was not found.</p></body>
</html>
HTML
if probe_downloaded_image "$HTML_FILE"; then
  bad "T2: HTML file PASSED the probe (should fail — wrong format)"
else
  ok "T2: HTML file fails the probe (return non-zero — wrong format rejected)"
fi

# ---------------------------------------------------------------------------
# T3 — undersized 100x100 JPEG fails the probe
# ---------------------------------------------------------------------------
UNDERSIZED_JPEG="$TMP/undersized_100x100.jpg"
ffmpeg -y -v error -f lavfi -i "color=c=blue:s=100x100:d=1" -frames:v 1 "$UNDERSIZED_JPEG" 2>/dev/null
if [[ ! -f "$UNDERSIZED_JPEG" ]]; then
  bad "T3: could not create undersized 100x100 JPEG fixture"
else
  if probe_downloaded_image "$UNDERSIZED_JPEG"; then
    bad "T3: undersized 100x100 JPEG PASSED the probe (should fail — too small)"
  else
    ok "T3: undersized 100x100 JPEG fails the probe (return non-zero — too small rejected)"
  fi
fi

# ---------------------------------------------------------------------------
# T4 — MUTATION PROOF: mutate the dimension check, verify T3 turns RED, revert
# ---------------------------------------------------------------------------
# The critical line is: if [[ "$w" -lt "$COVER_MIN_SIDE" || "$h" -lt "$COVER_MIN_SIDE" ]]; then
# Mutate it to: if [[ "$w" -lt "0" || "$h" -lt "0" ]]; then
# This makes the probe accept any size, so T3 should turn RED (probe passes).

MUTATED_SCRIPT="$TMP/generate_cover_mutated.sh"
sed 's/"\$w" -lt "\$COVER_MIN_SIDE" || "\$h" -lt "\$COVER_MIN_SIDE"/"\$w" -lt "0" || "\$h" -lt "0"/' "$SCRIPT" > "$MUTATED_SCRIPT"

# Re-extract the mutated probe function.
eval "$(sed -n '164,200p' "$MUTATED_SCRIPT")"

if probe_downloaded_image "$UNDERSIZED_JPEG"; then
  ok "T4 RED: with mutated dimension check, undersized JPEG passes (mutation detected)"
else
  bad "T4 RED: mutation did NOT turn the test RED (probe still rejects undersized)"
fi

# Revert: re-extract the original probe function.
eval "$(sed -n '164,200p' "$SCRIPT")"

if probe_downloaded_image "$UNDERSIZED_JPEG"; then
  bad "T4 GREEN: after revert, undersized JPEG still passes (revert failed)"
else
  ok "T4 GREEN: after revert, undersized JPEG fails again (mutation proof complete)"
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "=== $PASS passed, $FAIL failed ==="
[[ $FAIL -eq 0 ]] || exit 1
exit 0

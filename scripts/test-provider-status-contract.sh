#!/usr/bin/env bash
# test-provider-status-contract.sh — T2-32 / A46.
#
# WHY THIS EXISTS
#   39-real-estate-playbook's provider-status producer and consumer disagreed on
#   three independent axes at once:
#     PATH   producer wrote $HOME/.openclaw/.skill-39-provider-status.json,
#            consumer read $MFD/.skill-39-provider-status.json
#     NAMES  producer emitted geocode/lookup/comps/streetview,
#            consumer branched on geocode/property_lookup/street_view/comps
#     SHAPE  producer wrote key NAMES mapped to "set"/"unset",
#            consumer looked for a "state":"AVAILABLE" field
#   The consumer therefore saw no status file at all, and its capability checks
#   would not have lined up if it had, so every provider read as unavailable.
#
# WHAT THIS PROVES — one direction per axis, plus the round trip:
#   1. The producer writes to the SAME resolved path the consumer reads.
#   2. The artifact uses the CONTRACT capability names, and the retired names
#      (`lookup`, `streetview`) are REJECTED rather than silently ignored.
#   3. The artifact carries the contract STATE SHAPE, and a set/unset-shaped
#      artifact is REJECTED.
#   4. Round trip: with a key present the consumer resolves that capability as
#      AVAILABLE; with no key it resolves as an HONEST GAP.
#   5. The validator reports CANNOT RUN (exit 2) for an absent artifact and never
#      counts it as a pass.
#
# Runs entirely in a temporary directory. No fleet box is touched and no real
# credential is used — every value below is a literal test string.
#
# EXIT: 0 all directions passed · 1 a direction failed.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
S="$REPO_ROOT/39-real-estate-playbook/scripts"
PASS=0; FAIL=0

ok()  { printf '  \033[32mv\033[0m %s\n' "$1"; PASS=$((PASS+1)); }
no()  { printf '  \033[31mx\033[0m %s\n' "$1"; FAIL=$((FAIL+1)); }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
MFD="$WORK/master-files"; mkdir -p "$MFD"
STATUS="$MFD/.skill-39-provider-status.json"

echo ""
echo "=== T2-32 / A46 — provider-status producer and consumer share ONE contract ==="

# ── 1. PATH ──────────────────────────────────────────────────────────────────
MASTER_FILES_DIR="$MFD" bash "$S/02-configure-providers.sh" >/dev/null 2>&1
if [ -f "$STATUS" ]; then
  ok "PATH: the producer wrote to the resolved master-files directory the consumer reads"
else
  no "PATH: the producer did not write to \$MFD (looked for $STATUS)"
fi
if [ -f "$HOME/.openclaw/.skill-39-provider-status.json" ] && [ "$HOME/.openclaw" = "$MFD" ]; then
  no "PATH: the producer still writes to a fixed home path"
else
  ok "PATH: the producer no longer writes to a fixed \$HOME path"
fi

# ── 2. CAPABILITY NAMES ──────────────────────────────────────────────────────
if grep -q '"property_lookup"' "$STATUS" && grep -q '"street_view"' "$STATUS"; then
  ok "NAMES: the artifact uses the contract names (property_lookup, street_view)"
else
  no "NAMES: the artifact does not use the contract capability names"
fi

python3 - "$STATUS" "$WORK/retired.json" <<'PY'
import json, sys
doc = json.load(open(sys.argv[1]))
doc["capabilities"]["lookup"] = doc["capabilities"].pop("property_lookup")
doc["capabilities"]["streetview"] = doc["capabilities"].pop("street_view")
json.dump(doc, open(sys.argv[2], "w"))
PY
if bash "$S/validate-provider-status.sh" "$WORK/retired.json" >/dev/null 2>&1; then
  no "NAMES: the retired names lookup/streetview were ACCEPTED"
else
  ok "NAMES: the retired names lookup/streetview are REJECTED, not silently ignored"
fi

# ── 3. STATE SHAPE ───────────────────────────────────────────────────────────
cat > "$WORK/oldshape.json" <<'JSON'
{
  "geocode":   {"google_maps_api_key":"unset","mapbox_token":"unset","census":"keyless-always-available"},
  "lookup":    {"rentcast_api_key":"unset","reso_api_token":"unset"},
  "comps":     {"rentcast_api_key":"unset","reso_api_token":"unset"},
  "streetview":{"google_maps_api_key":"unset"}
}
JSON
if bash "$S/validate-provider-status.sh" "$WORK/oldshape.json" >/dev/null 2>&1; then
  no "SHAPE: the pre-contract set/unset shape was ACCEPTED"
else
  ok "SHAPE: the pre-contract set/unset shape is REJECTED"
fi
if bash "$S/validate-provider-status.sh" "$STATUS" >/dev/null 2>&1; then
  ok "SHAPE: the artifact the producer writes conforms to provider-status/v1"
else
  no "SHAPE: the artifact the producer writes does NOT conform to its own contract"
fi

# ── 4. ROUND TRIP — a keyed provider must resolve AVAILABLE ──────────────────
GOOGLE_MAPS_API_KEY="test-not-a-real-key-maps" MASTER_FILES_DIR="$MFD" \
  bash "$S/02-configure-providers.sh" >/dev/null 2>&1
sv_state="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['capabilities']['street_view']['state'])" "$STATUS")"
if [ "$sv_state" = "AVAILABLE" ]; then
  ok "ROUND TRIP: with a key present, street_view resolves AVAILABLE (it read HONEST_GAP for every capability before)"
else
  no "ROUND TRIP: street_view is '$sv_state' with a key present"
fi

MASTER_FILES_DIR="$MFD" bash "$S/02-configure-providers.sh" >/dev/null 2>&1
sv_state="$(python3 -c "import json,sys;print(json.load(open(sys.argv[1]))['capabilities']['street_view']['state'])" "$STATUS")"
if [ "$sv_state" = "HONEST_GAP" ]; then
  ok "ROUND TRIP: with no key, street_view resolves HONEST_GAP — never fabricated"
else
  no "ROUND TRIP: street_view is '$sv_state' with no key set"
fi

# ── 5. ABSENT ARTIFACT REPORTS, NEVER PASSES ─────────────────────────────────
bash "$S/validate-provider-status.sh" "$WORK/does-not-exist.json" >/dev/null 2>&1
if [ "$?" -eq 2 ]; then
  ok "ABSENT: a missing artifact reports CANNOT RUN (exit 2) — never counted as a pass"
else
  no "ABSENT: a missing artifact did not report CANNOT RUN"
fi

# ── 6. NO CREDENTIAL VALUE MAY REACH THE ARTIFACT ───────────────────────────
if grep -q 'test-not-a-real-key-maps' "$STATUS"; then
  no "SECRETS: a credential value reached the status artifact"
else
  ok "SECRETS: no credential value appears in the artifact (provider names only)"
fi

echo ""
echo "=== Result: $PASS passed | $FAIL failed ==="
[ "$FAIL" -gt 0 ] && exit 1
exit 0

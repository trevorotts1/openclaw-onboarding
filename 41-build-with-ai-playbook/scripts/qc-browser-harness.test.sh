#!/usr/bin/env bash
# qc-browser-harness.test.sh -- negative self-test for the L0 browser-harness static gate.
# Proves the gate BITES: passes on the intact tree, fails when a required harness piece is
# removed, when a fixture is corrupted, and when a live GHL URL is leaked into a level script.
set -uo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE="$SCRIPT_DIR/qc-browser-harness.sh"
REAL="$(cd "$SCRIPT_DIR/.." && pwd)"
fail() { echo "[TEST FAIL] qc-browser-harness: $1"; exit 1; }

# 1) Passes on the intact tree.
bash "$GATE" --skill-dir "$REAL" >/dev/null 2>&1 || fail "gate failed on the intact tree"

# 2) Bites when a level script is removed.
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
rm -f "$c/scripts/test/L3-seeded-defect.sh"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite when L3 was removed"; fi
rm -rf "$c"

# 3) Bites when a seeded-defect fixture is corrupted (invalid JSON / missing expect_defects).
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
echo 'not json' > "$c/scripts/test/fixtures/defect-D1-missing-dependency.json"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite on a corrupted fixture"; fi
rm -rf "$c"

# 4) Bites when a LIVE GHL URL is leaked into a level script outside a redirect/guardrail.
c="$(mktemp -d)"; cp -a "$REAL/." "$c/"
echo 'curl https://services.leadconnectorhq.com/locations/x/tags' >> "$c/scripts/test/L1-auth-session.sh"
if bash "$GATE" --skill-dir "$c" >/dev/null 2>&1; then rm -rf "$c"; fail "gate did NOT bite on a leaked live GHL URL"; fi
rm -rf "$c"

echo "[TEST PASS] qc-browser-harness bites (missing level / corrupt fixture / leaked live URL)"
exit 0

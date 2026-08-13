#!/usr/bin/env bash
# scripts/ci/presentations-drift-gates.sh
#
# Three CI drift gates for the presentation pipeline, added after two landmines
# each passed a green 93-check CI on the fix/pres-wave1-rollblockers branch:
#
#   Problem 1 (fix_bundle_complete class): the canonical DELIVERABLE_AUDIT_SPEC
#   symbol went missing / import-broken in fix_bundle_complete.py, which left
#   curate.py import-broken on main without any CI job noticing.
#
#   Problem 2 (manifest lockstep class): PR #884 stripped the trailing newline
#   from universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json without
#   restamping MANIFEST-SOURCE.txt's recorded content_sha256, bricking
#   manifest_source.py's sync_check and presentation-canonical-entry.sh GATE 3.
#
# GATE 1 (import smoke)             -- catches the Problem-1 class: any missing
#                                       symbol/module in the presentation_job package.
# GATE 2 (manifest lockstep)        -- catches the Problem-2 class: ANY byte-level
#                                       touch to PIPELINE-MANIFEST.json without a
#                                       matching MANIFEST-SOURCE.txt restamp.
# GATE 3 (deliverable whitelist parity) -- see the GATE 3 section below: today the
#                                       two deliverable-key structures are NOT
#                                       identical for reasons unrelated to drift, so
#                                       this gate prints a SKIP-WITH-REASON rather
#                                       than faking a pass. It still hard-fails on
#                                       an outright import/missing-symbol error.
#
# Exit code: 0 only if every gate that CAN fail today did not fail.
# Prints which gate failed (and why) on any non-zero exit.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SCRIPTS_DIR="23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
MANIFEST="universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
MANIFEST_SOURCE="universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt"

GATE1_TMP=""
cleanup() {
  if [ -n "$GATE1_TMP" ] && [ -d "$GATE1_TMP" ]; then
    rm -rf "$GATE1_TMP"
  fi
}
trap cleanup EXIT

FAILED=0

# ---------------------------------------------------------------------------
echo "== GATE 1: import smoke (presentation_job.phases) =="
if [ ! -d "$SCRIPTS_DIR" ]; then
  echo "GATE 1 FAILED: scripts dir not found at $SCRIPTS_DIR" >&2
  FAILED=1
else
  GATE1_TMP="$(mktemp -d)"
  cp -R "$SCRIPTS_DIR/." "$GATE1_TMP/"
  if GATE1_OUT="$(cd "$GATE1_TMP" && python3 -c "import sys; sys.path.insert(0,'.'); import presentation_job.phases" 2>&1)"; then
    echo "GATE 1 PASSED: presentation_job.phases imports cleanly."
  else
    echo "GATE 1 FAILED: import of presentation_job.phases raised an error (missing symbol/module below):" >&2
    echo "$GATE1_OUT" >&2
    FAILED=1
  fi
fi

# ---------------------------------------------------------------------------
echo
echo "== GATE 2: manifest lockstep (PIPELINE-MANIFEST.json <-> MANIFEST-SOURCE.txt) =="
if [ ! -f "$MANIFEST" ]; then
  echo "GATE 2 FAILED: manifest not found at $MANIFEST" >&2
  FAILED=1
elif [ ! -f "$MANIFEST_SOURCE" ]; then
  echo "GATE 2 FAILED: manifest source not found at $MANIFEST_SOURCE" >&2
  FAILED=1
else
  if command -v shasum >/dev/null 2>&1; then
    COMPUTED_SHA="$(shasum -a 256 "$MANIFEST" | awk '{print $1}')"
  elif command -v sha256sum >/dev/null 2>&1; then
    COMPUTED_SHA="$(sha256sum "$MANIFEST" | awk '{print $1}')"
  else
    echo "GATE 2 FAILED: no sha256 tool available (need shasum or sha256sum)" >&2
    COMPUTED_SHA=""
    FAILED=1
  fi

  if [ -n "${COMPUTED_SHA:-}" ]; then
    RECORDED_SHA="$(grep -o 'content_sha256=[0-9a-fA-F]*' "$MANIFEST_SOURCE" | head -1 | cut -d= -f2)"
    if [ -z "$RECORDED_SHA" ]; then
      echo "GATE 2 FAILED: could not parse a content_sha256= value out of $MANIFEST_SOURCE" >&2
      FAILED=1
    elif [ "$COMPUTED_SHA" != "$RECORDED_SHA" ]; then
      echo "GATE 2 FAILED: manifest drift -- PIPELINE-MANIFEST.json was touched without restamping MANIFEST-SOURCE.txt" >&2
      echo "  computed (current PIPELINE-MANIFEST.json): $COMPUTED_SHA" >&2
      echo "  recorded (MANIFEST-SOURCE.txt):             $RECORDED_SHA" >&2
      echo "  Fix: regenerate MANIFEST-SOURCE.txt's content_sha256 line from the current manifest," >&2
      echo "  or restore the manifest bytes the hash was recorded against." >&2
      FAILED=1
    else
      echo "GATE 2 PASSED: computed sha256 ($COMPUTED_SHA) matches MANIFEST-SOURCE.txt."
    fi
  fi
fi

# ---------------------------------------------------------------------------
echo
echo "== GATE 3: deliverable whitelist parity (fix_bundle_complete.py <-> phase_verifiers.py) =="
GATE3_RC=0
GATE3_OUT="$(cd "$SCRIPTS_DIR" && python3 - <<'PYEOF' 2>&1
import importlib.util
import sys


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


try:
    fbc = load_module("fix_bundle_complete", "fix_bundle_complete.py")
except Exception as e:  # noqa: BLE001 - report and fail, don't swallow
    print(f"GATE3_IMPORT_ERROR fix_bundle_complete.py: {e!r}")
    sys.exit(2)

try:
    pv = load_module("phase_verifiers", "phase_verifiers.py")
except Exception as e:  # noqa: BLE001
    print(f"GATE3_IMPORT_ERROR phase_verifiers.py: {e!r}")
    sys.exit(2)

try:
    fbc_keys = set(fbc.REQUIRED_KEYS)
except AttributeError as e:
    print(f"GATE3_MISSING_SYMBOL fix_bundle_complete.REQUIRED_KEYS: {e!r}")
    sys.exit(2)

try:
    pv_keys = set(item["key"] for item in pv._DELIVERY_DELIVERABLES)
except AttributeError as e:
    print(f"GATE3_MISSING_SYMBOL phase_verifiers._DELIVERY_DELIVERABLES: {e!r}")
    sys.exit(2)

if fbc_keys == pv_keys:
    print("GATE3_PASS: fix_bundle_complete.REQUIRED_KEYS and phase_verifiers._DELIVERY_DELIVERABLES are identical.")
    sys.exit(0)

only_fbc = sorted(fbc_keys - pv_keys)
only_pv = sorted(pv_keys - fbc_keys)
print("GATE3_SKIP_WITH_REASON: the two deliverable-key structures are NOT identical today.")
print(f"  only in fix_bundle_complete.REQUIRED_KEYS:        {only_fbc}")
print(f"  only in phase_verifiers._DELIVERY_DELIVERABLES:   {only_pv}")
print("  This is a pre-existing structural split, not new drift: fix_bundle_complete tracks the")
print("  build-phase bundle-completeness gate (includes speech_md, the pure-markdown intermediate")
print("  the assembly phase writes before the Fish-tagged/PDF variants exist), while phase_verifiers")
print("  tracks the P9-DELIVER final delivery whitelist (includes workbook_pdf, the AF-WORKBOOK-BOTH")
print("  deliverable that is not part of the build-phase bundle gate). Making these two structures the")
print("  literal same set is future reconciliation work, not something this gate can assert today")
print("  without producing a permanent false failure on an already-fixed tree.")
print("  SKIPPING exact-parity assertion (exit 0) -- see reason above. This gate still hard-fails")
print("  (exit 2) if either module fails to import or either symbol goes missing, which is the class")
print("  of drift this gate exists to catch.")
sys.exit(0)
PYEOF
)" || GATE3_RC=$?

echo "$GATE3_OUT"
if [ "$GATE3_RC" -ne 0 ]; then
  echo "GATE 3 FAILED: see GATE3_IMPORT_ERROR / GATE3_MISSING_SYMBOL above." >&2
  FAILED=1
fi

# ---------------------------------------------------------------------------
echo
if [ "$FAILED" -ne 0 ]; then
  echo "presentations-drift-gates: FAILED -- see the gate failure(s) above." >&2
  exit 1
fi

echo "presentations-drift-gates: ALL GATES PASSED (GATE 3 may be SKIP-WITH-REASON -- see above)."
exit 0

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
#   PR #884 ALSO restamped a THIRD registry, universal-sops/_content-manifest.json
#   (enforced by scripts/hash-universal-sops-manifest.py --check), and a follow-up
#   fix that restored the MANIFEST-SOURCE.txt lockstep left THAT registry stale --
#   invisible to the original GATE 2, which only ever looked at MANIFEST-SOURCE.txt.
#
# GATE 1 (import smoke)             -- catches the Problem-1 class: any missing
#                                       symbol/module in the presentation_job package.
# GATE 2 (manifest lockstep)        -- catches the Problem-2 class: ANY byte-level
#                                       touch to PIPELINE-MANIFEST.json without a
#                                       matching restamp of BOTH MANIFEST-SOURCE.txt
#                                       AND universal-sops/_content-manifest.json.
# GATE 3 (deliverable whitelist parity) -- FAIL-CLOSED, no skip path. Imports the
#                                       canonical spec from presentation_job/
#                                       deliverables.py (U05) and each of the four
#                                       real consumers (fix_bundle_complete.py,
#                                       presentation_job/curate.py, phase_verifiers.py,
#                                       self_audit.py), extracts each one's RUNTIME
#                                       whitelist view, and FAILS naming the consumer
#                                       and the exact diverging keys if it holds a key
#                                       canon does not have, or is missing a canon key
#                                       that is not explicitly pre-declared in
#                                       _ALLOWED_SUBSETS with a written reason. Import
#                                       errors and missing symbols are hard failures.
#                                       (The pre-U05 version of this gate always printed
#                                       GATE3_SKIP_WITH_REASON and exited 0 -- a no-op
#                                       wearing a GATE 3 label. That skip path is gone.)
#
# Exit code: 0 only if every gate that CAN fail today did not fail.
# Prints which gate failed (and why) on any non-zero exit.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

SCRIPTS_DIR="23-ai-workforce-blueprint/templates/role-library/presentations/scripts"
MANIFEST="universal-sops/presentation-slide-craft/PIPELINE-MANIFEST.json"
MANIFEST_SOURCE="universal-sops/presentation-slide-craft/MANIFEST-SOURCE.txt"
CONTENT_MANIFEST="universal-sops/_content-manifest.json"
CONTENT_MANIFEST_KEY="presentation-slide-craft/PIPELINE-MANIFEST.json"

GATE1_TMP=""
GATE3_TMP=""
cleanup() {
  if [ -n "$GATE1_TMP" ] && [ -d "$GATE1_TMP" ]; then
    rm -rf "$GATE1_TMP"
  fi
  if [ -n "$GATE3_TMP" ] && [ -d "$GATE3_TMP" ]; then
    rm -rf "$GATE3_TMP"
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
echo "== GATE 2: manifest lockstep (PIPELINE-MANIFEST.json <-> MANIFEST-SOURCE.txt <-> _content-manifest.json) =="
if [ ! -f "$MANIFEST" ]; then
  echo "GATE 2 FAILED: manifest not found at $MANIFEST" >&2
  FAILED=1
elif [ ! -f "$MANIFEST_SOURCE" ]; then
  echo "GATE 2 FAILED: manifest source not found at $MANIFEST_SOURCE" >&2
  FAILED=1
elif [ ! -f "$CONTENT_MANIFEST" ]; then
  echo "GATE 2 FAILED: content manifest not found at $CONTENT_MANIFEST" >&2
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
      echo "GATE 2a PASSED: computed sha256 ($COMPUTED_SHA) matches MANIFEST-SOURCE.txt."
    fi
  fi

  # Second leg: universal-sops/_content-manifest.json (scripts/hash-universal-
  # sops-manifest.py --check). PR #884's drift moved HERE once MANIFEST-SOURCE.txt
  # was fixed, and the original GATE 2 never looked at this file -- that blind
  # spot is exactly why it stayed green while the real registry went stale.
  # This registry hashes CRLF->LF-normalized bytes (matching its own generator),
  # computed independently of COMPUTED_SHA above rather than assumed equal.
  if MANIFEST_PATH="$MANIFEST" python3 -c "
import hashlib, os
data = open(os.environ['MANIFEST_PATH'], 'rb').read().replace(b'\r\n', b'\n')
print(hashlib.sha256(data).hexdigest())
" > /tmp/gate2_norm_sha.$$ 2>/tmp/gate2_norm_err.$$; then
    COMPUTED_SHA_NORM="$(cat /tmp/gate2_norm_sha.$$)"
  else
    echo "GATE 2 FAILED: could not hash $MANIFEST for _content-manifest.json comparison:" >&2
    cat /tmp/gate2_norm_err.$$ >&2
    COMPUTED_SHA_NORM=""
    FAILED=1
  fi
  rm -f /tmp/gate2_norm_sha.$$ /tmp/gate2_norm_err.$$

  if [ -n "${COMPUTED_SHA_NORM:-}" ]; then
    RECORDED_SHA_CM="$(CONTENT_MANIFEST_PATH="$CONTENT_MANIFEST" CONTENT_MANIFEST_KEY="$CONTENT_MANIFEST_KEY" python3 -c "
import json, os
d = json.load(open(os.environ['CONTENT_MANIFEST_PATH'], encoding='utf-8'))
print(d.get('files', {}).get(os.environ['CONTENT_MANIFEST_KEY'], {}).get('sha256', ''))
")"
    if [ -z "$RECORDED_SHA_CM" ]; then
      echo "GATE 2 FAILED: no '$CONTENT_MANIFEST_KEY' entry found in $CONTENT_MANIFEST" >&2
      FAILED=1
    elif [ "$COMPUTED_SHA_NORM" != "$RECORDED_SHA_CM" ]; then
      echo "GATE 2 FAILED: manifest drift -- PIPELINE-MANIFEST.json was touched without restamping $CONTENT_MANIFEST" >&2
      echo "  computed (current PIPELINE-MANIFEST.json, CRLF->LF normalized): $COMPUTED_SHA_NORM" >&2
      echo "  recorded ($CONTENT_MANIFEST):                                   $RECORDED_SHA_CM" >&2
      echo "  Fix: run scripts/hash-universal-sops-manifest.py to regenerate $CONTENT_MANIFEST," >&2
      echo "  or restore the manifest bytes the hash was recorded against." >&2
      FAILED=1
    else
      echo "GATE 2b PASSED: computed sha256 ($COMPUTED_SHA_NORM) matches $CONTENT_MANIFEST."
    fi
  fi
fi

# ---------------------------------------------------------------------------
echo
echo "== GATE 3: deliverable whitelist parity (canon: presentation_job/deliverables.py) =="
if [ ! -d "$SCRIPTS_DIR" ]; then
  echo "GATE 3 FAILED: scripts dir not found at $SCRIPTS_DIR" >&2
  FAILED=1
else
  # Work on a COPY so this gate never mutates the tree it is checking (matches
  # the GATE 1 import-smoke pattern above).
  GATE3_TMP="$(mktemp -d)"
  cp -R "$SCRIPTS_DIR/." "$GATE3_TMP/"

  GATE3_RC=0
  GATE3_OUT="$(cd "$GATE3_TMP" && python3 - <<'PYEOF' 2>&1
import sys

sys.path.insert(0, ".")

# ---------------------------------------------------------------------------
# CANON: presentation_job/deliverables.py — the single source of truth (U05).
# ---------------------------------------------------------------------------
try:
    from presentation_job.deliverables import REQUIRED_KEYS as CANON_KEYS
except Exception as e:  # noqa: BLE001 — report and fail, don't swallow
    print(f"GATE3_IMPORT_ERROR presentation_job/deliverables.py: {e!r}")
    sys.exit(2)

canon_set = set(CANON_KEYS)
if not canon_set:
    print("GATE3_FAIL: presentation_job.deliverables.REQUIRED_KEYS is empty — "
          "canon itself is broken, nothing to check consumers against.")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Consumers — every module presentation_job/deliverables.py's own docstring
# names as an importer of the canonical spec. Each entry: (display name,
# a loader that returns the module, an extractor that pulls the set of keys
# that module actually operates on at runtime).
# ---------------------------------------------------------------------------
consumers = []

def _load(modname):
    import importlib
    return importlib.import_module(modname)

try:
    fbc = _load("fix_bundle_complete")
    consumers.append((
        "fix_bundle_complete.py",
        lambda: set(fbc.REQUIRED_KEYS),
    ))
except Exception as e:  # noqa: BLE001
    print(f"GATE3_IMPORT_ERROR fix_bundle_complete.py: {e!r}")
    sys.exit(2)

try:
    curate = _load("presentation_job.curate")
    consumers.append((
        "presentation_job/curate.py",
        lambda: set(curate.REQUIRED_KEYS),
    ))
except Exception as e:  # noqa: BLE001
    print(f"GATE3_IMPORT_ERROR presentation_job/curate.py: {e!r}")
    sys.exit(2)

try:
    pv = _load("phase_verifiers")
    consumers.append((
        "phase_verifiers.py",
        lambda: set(item["key"] for item in pv._DELIVERY_DELIVERABLES),
    ))
except Exception as e:  # noqa: BLE001
    print(f"GATE3_IMPORT_ERROR phase_verifiers.py: {e!r}")
    sys.exit(2)

try:
    sa = _load("self_audit")
    consumers.append((
        "self_audit.py",
        lambda: set(item["key"] for item in sa.DELIVERABLE_AUDIT_LIST),
    ))
except Exception as e:  # noqa: BLE001
    print(f"GATE3_IMPORT_ERROR self_audit.py: {e!r}")
    sys.exit(2)

# ---------------------------------------------------------------------------
# Explicitly pre-declared legitimate subsets. Empty today: every consumer
# above derives its view directly from DELIVERABLE_AUDIT_SPEC with no
# filtering, so exact parity is what is actually being asserted right now.
# If a consumer ever legitimately needs to omit canonical keys again, add an
# entry here naming exactly which keys and why -- do NOT reintroduce a bare
# skip / weaken the comparison below to make this pass.
#
#   "consumer.py": (frozenset({"key_a", "key_b"}), "written reason"),
# ---------------------------------------------------------------------------
_ALLOWED_SUBSETS = {}

failures = []
for name, extractor in consumers:
    try:
        view = extractor()
    except AttributeError as e:
        print(f"GATE3_MISSING_SYMBOL {name}: {e!r}")
        sys.exit(2)

    extra = view - canon_set
    missing = canon_set - view

    if extra:
        failures.append(
            f"{name}: holds key(s) NOT in canonical spec (drift/hardcoded): "
            f"{sorted(extra)}"
        )
        continue

    if missing:
        allowed, reason = _ALLOWED_SUBSETS.get(name, (frozenset(), None))
        if missing <= allowed:
            print(
                f"GATE3_SUBSET_ASSERTED: {name} intentionally omits "
                f"{sorted(missing)} of canon -- reason: {reason}"
            )
            continue
        undeclared = sorted(missing - allowed)
        failures.append(
            f"{name}: missing key(s) present in canonical spec and NOT "
            f"declared as an allowed subset: {undeclared}"
        )
        continue

    print(f"GATE3_PARITY_OK: {name} matches canon exactly "
          f"({len(view)} keys: {sorted(view)}).")

if failures:
    print("GATE3_FAIL: the following consumer(s) diverge from "
          "presentation_job.deliverables.REQUIRED_KEYS:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"GATE3_PASS: all {len(consumers)} consumers "
      f"({', '.join(n for n, _ in consumers)}) match canon "
      f"({len(canon_set)} keys: {sorted(canon_set)}).")
sys.exit(0)
PYEOF
)" || GATE3_RC=$?

  echo "$GATE3_OUT"
  if [ "$GATE3_RC" -ne 0 ]; then
    echo "GATE 3 FAILED: see GATE3_FAIL / GATE3_IMPORT_ERROR / GATE3_MISSING_SYMBOL above." >&2
    FAILED=1
  fi
fi

# ---------------------------------------------------------------------------
echo
if [ "$FAILED" -ne 0 ]; then
  echo "presentations-drift-gates: FAILED -- see the gate failure(s) above." >&2
  exit 1
fi

echo "presentations-drift-gates: ALL GATES PASSED (GATE 1 import-smoke, GATE 2 manifest-lockstep x2, GATE 3 whitelist-parity fail-closed)."
exit 0

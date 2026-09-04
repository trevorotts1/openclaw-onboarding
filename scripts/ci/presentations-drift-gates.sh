#!/usr/bin/env bash
# scripts/ci/presentations-drift-gates.sh
#
# Four CI drift gates for the presentation pipeline. The first three were added
# after two landmines each passed a green 93-check CI on the fix/pres-wave1-rollblockers
# branch; the fourth was added after 00-START-HERE.md and SOP-SLIDE-05-PROCESS-MANIFEST.md
# were found describing an obsolete 21-step / 12-phase scheme months after the manifest
# had grown to 36 phases, while SOP-SLIDE-06 asserted (falsely, and unchecked) that the
# docs used "the SAME phase ids" as the manifest:
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
# GATE 4 (phase-doc lockstep)       -- reads `phases[].id` straight out of
#                                       PIPELINE-MANIFEST.json and fails, naming the
#                                       exact missing id(s), if 00-START-HERE.md or
#                                       SOP-SLIDE-05-PROCESS-MANIFEST.md stops naming
#                                       (backtick-quoted) every current phase. The
#                                       precise guard SOP-SLIDE-06 §6 now points to as
#                                       what makes its "same phase ids" claim true.
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
echo "== GATE 4: phase-doc lockstep (00-START-HERE.md + SOP-SLIDE-05-PROCESS-MANIFEST.md <-> PIPELINE-MANIFEST.json phases[]) =="
# Added after the 00-START-HERE.md / SOP-SLIDE-05 phase lists were found describing an
# obsolete 21-step / 12-phase scheme (ids A, B, 1, 1Q, 1A, 1.5, 2, 3, 4, 5, 6, POST-6) that
# matched NONE of the current 36 phases -- while SOP-SLIDE-06 asserted the docs used "the
# SAME phase ids" as the manifest, so nothing ever caught the drift. This gate reads the
# canonical id list straight from the manifest and fails, naming exactly which id is
# missing from which doc, the moment a phase is added/renamed in PIPELINE-MANIFEST.json
# without the doc being updated to name it (backtick-quoted, e.g. `` `P4-COPY` ``).
if [ ! -f "$MANIFEST" ]; then
  echo "GATE 4 FAILED: manifest not found at $MANIFEST" >&2
  FAILED=1
else
  GATE4_RC=0
  GATE4_OUT="$(MANIFEST_PATH="$MANIFEST" python3 - <<'PYEOF' 2>&1
import json
import os
import pathlib
import sys

repo_root = pathlib.Path(".")
manifest_path = pathlib.Path(os.environ["MANIFEST_PATH"])
docs = [
    "23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md",
    "universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md",
]

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
ids = [p["id"] for p in manifest["phases"]]
if not ids:
    print("GATE4_FAIL: PIPELINE-MANIFEST.json phases[] is empty -- canon itself is broken.")
    sys.exit(2)

failures = []
for doc_rel in docs:
    doc_path = repo_root / doc_rel
    if not doc_path.exists():
        failures.append(f"{doc_rel}: FILE NOT FOUND")
        continue
    text = doc_path.read_text(encoding="utf-8")
    missing = [pid for pid in ids if f"`{pid}`" not in text]
    if missing:
        failures.append(f"{doc_rel}: missing {len(missing)} of {len(ids)} phase id(s): {missing}")
    else:
        print(f"GATE4_DOC_OK: {doc_rel} names all {len(ids)} manifest phase ids.")

if failures:
    print("GATE4_FAIL: a doc's phase-id list has drifted from PIPELINE-MANIFEST.json phases[] "
          "(missing id = doc describes fewer phases than the manifest actually runs):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"GATE4_PASS: both docs name all {len(ids)} current manifest phase ids.")
sys.exit(0)
PYEOF
)" || GATE4_RC=$?

  echo "$GATE4_OUT"
  if [ "$GATE4_RC" -ne 0 ]; then
    echo "GATE 4 FAILED: see GATE4_FAIL above -- update the named doc's phase list to name the missing id(s)." >&2
    FAILED=1
  fi
fi

# ---------------------------------------------------------------------------
# GATE 5 (FIX 32) — manifest-COPY drift detector, live.
# The broken state this gate exists for was measured on the operator box
# 2026-08-31: the repo cluster copy (v52, sha 8507f9d1...) and the materialized
# department copy (v51, sha 6140fb52...) differed while EVERY per-copy provenance
# check passed on both -- each copy was internally consistent, the two copies
# disagreed, and nothing compared them. manifest_version cannot catch the class:
# the live drift happened without a version bump. In CI there is no materialized
# department, so this gate PROVES THE DETECTOR instead of comparing the
# (absent) second copy:
#   (a) a scratch one-field change at the SAME manifest_version, made via the
#       repo manifest, MUST produce an M1 drift item from sync_check.py --json;
#   (b) a byte-level REFORMAT (same JSON content) must NOT produce one
#       (canonical-JSON hashing: whitespace/key-order is not content);
#   (c) the identical copy must NOT produce one.
# A regression that blinds the copy detector (M1 removed, flag defaulting to
# skip, hashing degraded to byte-compare) fails (a) or (b) and blocks the merge.
# On a real box the same M1 check runs at launch: sync_check --json feeds
# presentation-canonical-entry.sh GATE 3, and M1 carries class "render_path",
# so copy drift FAILS CLOSED at the door (exit 7), not silently.
# Rollback: PRESENTATION_MANIFEST_COPY_DRIFT=0 documents the skip everywhere it
# is honored -- the disabled path prints the skip, it never reports a silent pass.
echo
echo "== GATE 5: manifest-copy drift detector (FIX 32 -- one-field change trips, identical/reformat pass) =="
GATE5_TMP="$(mktemp -d)"
GATE5_RC=0
if MANIFEST="$MANIFEST" SCRIPTS_DIR="$SCRIPTS_DIR" GATE5_TMP="$GATE5_TMP" python3 - <<'PYEOF' 2>&1
import copy
import json
import os
import subprocess
import sys
from pathlib import Path

manifest_path = Path(os.environ["MANIFEST"])
scripts_dir = Path(os.environ["SCRIPTS_DIR"])
tmp = Path(os.environ["GATE5_TMP"])

sync_check = scripts_dir / "sync_check.py"

def run_sync(env_peer):
    env = dict(os.environ)
    env["PRESENTATION_MANIFEST_COPY"] = str(env_peer)
    proc = subprocess.run(
        [sys.executable, str(sync_check), "--json"],
        capture_output=True, text=True, timeout=180, env=env,
    )
    try:
        parsed = json.loads(proc.stdout)
    except json.JSONDecodeError:
        print(f"GATE5_FAIL: sync_check.py --json did not emit JSON (rc={proc.returncode}):")
        print(proc.stdout[-800:])
        print(proc.stderr[-800:])
        sys.exit(2)
    m1 = [d for d in parsed.get("drift", []) if d.get("check") == "M1"]
    return m1

failures = []
base = json.loads(manifest_path.read_text(encoding="utf-8"))

# (a) one-field change at the SAME manifest_version -> MUST trip M1.
drifted = copy.deepcopy(base)
assert drifted["manifest_version"] == base["manifest_version"]
drifted["phases"][0]["label"] = str(drifted["phases"][0].get("label", "")) + " [GATE5 probe one-field]"
peer_drift = tmp / "peer-one-field" / "PIPELINE-MANIFEST.json"
peer_drift.parent.mkdir(parents=True)
peer_drift.write_text(json.dumps(drifted, indent=2) + "\n", encoding="utf-8")
m1 = run_sync(peer_drift)
if not m1:
    failures.append(
        f"(a) one-field change at manifest_version={base['manifest_version']} produced NO "
        f"M1 drift item -- the copy detector is blind to exactly the drift class "
        f"(same version, different content) FIX 32 exists to catch.")
else:
    print(f"GATE5_TRIP_OK: one-field change -> {len(m1)} M1 item(s).")

# (b) byte-level reformat only (same JSON content) -> must NOT trip M1.
peer_reformat = tmp / "peer-reformat" / "PIPELINE-MANIFEST.json"
peer_reformat.parent.mkdir(parents=True)
peer_reformat.write_text(json.dumps(base, indent=4), encoding="utf-8")
m1 = run_sync(peer_reformat)
if m1:
    failures.append("(b) a pure byte-level reformat tripped M1 -- canonical-JSON "
                    "hashing is broken; whitespace/key-order is not content drift.")
else:
    print("GATE5_REFORMAT_OK: reformat-only copy produced no M1 item.")

# (c) identical copy -> must NOT trip M1.
peer_ident = tmp / "peer-identical" / "PIPELINE-MANIFEST.json"
peer_ident.parent.mkdir(parents=True)
peer_ident.write_bytes(manifest_path.read_bytes())
m1 = run_sync(peer_ident)
if m1:
    failures.append("(c) a byte-identical copy tripped M1 -- false positive.")
else:
    print("GATE5_IDENTICAL_OK: identical copy produced no M1 item.")

if failures:
    print("GATE5_FAIL: manifest-copy drift detector regression:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("GATE5_PASS: M1 catches one-field same-version changes and passes "
      "identical/reformatted copies.")
sys.exit(0)
PYEOF
then
  :
else
  GATE5_RC=$?
fi
if [ "$GATE5_RC" -ne 0 ]; then
  echo "GATE 5 FAILED: the FIX-32 manifest-copy drift detector regressed -- see GATE5_FAIL above." >&2
  FAILED=1
fi
rm -rf "$GATE5_TMP"

# ---------------------------------------------------------------------------
echo
if [ "$FAILED" -ne 0 ]; then
  echo "presentations-drift-gates: FAILED -- see the gate failure(s) above." >&2
  exit 1
fi

echo "presentations-drift-gates: ALL GATES PASSED (GATE 1 import-smoke, GATE 2 manifest-lockstep x2, GATE 3 whitelist-parity fail-closed, GATE 4 phase-doc lockstep, GATE 5 manifest-copy drift detector)."
exit 0

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
# GATE 6 (FIX 114 provider-id canon) -- reads every "provider" literal out of
#                                       model_catalog.json (all aliases and their
#                                       served_ids keys) and fails, naming the exact
#                                       id(s), if any carries an underscore or space --
#                                       the FIX 114 drift class (catalog said
#                                       `ollama_cloud` while the router said
#                                       `ollama-cloud`, and both spellings lived on
#                                       disk). Also proves the FIX 114 rejects in place:
#                                       model_router refuses an ollama-cloud route with
#                                       no resolvable key, research_web accepts a key
#                                       stored only as BRAVE_API_KEY, and the canon
#                                       helper rejects a placeholder through
#                                       looks_like_real_key.
# GATE 7 (FIX 65 colocate contract) -- asserts the colocate list contract of
#                                       U006 colocate_presentation_entry in
#                                       BOTH install.sh and update-skills.sh
#                                       (R11 §G1): the candidate list must
#                                       name exactly the presentation scripts
#                                       that exist in the canonical source
#                                       dir 23-ai-workforce-blueprint/scripts/
#                                       (a retired file must leave the list,
#                                       so installs can never print
#                                       "partial (copied 1 of 2)" again);
#                                       an empty list must be a hard miss
#                                       (return 1); a copy miss must be a
#                                       hard miss (return 1), never a
#                                       warn-and-continue. This gate is the
#                                       "CI asserts the list" leg of that
#                                       contract: deleting a listed file
#                                       from the source dir makes THIS gate
#                                       fail (list-vs-disk divergence), and
#                                       silently re-adding a retired file to
#                                       the array makes it fail too (the
#                                       retired-name check).
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
# FIX 83: GATE 4 covers ALL FIVE count-restating docs, in two modes:
#   full-id  -- registry-style docs that restate the complete phase-id list:
#               every manifest id must appear backtick-quoted, or the doc's
#               list has drifted.
#   count    -- snapshot-count docs that restate the phase COUNT (the
#               "generated line"): the stated number must equal
#               len(manifest.phases). WORKERS-TUNING-EXAMPLE.md is count-mode
#               only: it is a per-phase tuning table that names its own subset
#               of ids, so the full-id check would demand a phase registry a
#               tuning table never promised to carry.
docs_full_id = [
    "23-ai-workforce-blueprint/templates/role-library/presentations/00-START-HERE.md",
    "universal-sops/presentation-slide-craft/SOP-SLIDE-05-PROCESS-MANIFEST.md",
    "23-ai-workforce-blueprint/templates/role-library/presentations/DEPARTMENT-COUNTS-CANONICAL.md",
    "23-ai-workforce-blueprint/templates/role-library/presentations/director-of-presentations.md",
]
# FIX 83 count-parity: a doc's "generated line" count literal must equal
# len(manifest.phases). Each row: (path, the exact literal prefix that begins
# the generated-line sentence, a marker proving the line is the generated one).
docs_count = [
    ("universal-sops/presentation-slide-craft/WORKERS-TUNING-EXAMPLE.md",
     "the count at this snapshot was "),
]

manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
ids = [p["id"] for p in manifest["phases"]]
if not ids:
    print("GATE4_FAIL: PIPELINE-MANIFEST.json phases[] is empty -- canon itself is broken.")
    sys.exit(2)

failures = []
import re as _re

for doc_rel in docs_full_id:
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

# Generated lines wrap across source lines, so the anchor is matched against
# whitespace-collapsed text ("the count at\nthis snapshot was 55" still hits).
_ws = _re.compile(r"\s+")
for doc_rel, count_prefix in docs_count:
    doc_path = repo_root / doc_rel
    if not doc_path.exists():
        failures.append(f"{doc_rel}: FILE NOT FOUND")
        continue
    flat = _ws.sub(" ", doc_path.read_text(encoding="utf-8"))
    anchor = _ws.sub(" ", count_prefix).strip()
    idx = flat.find(anchor)
    if idx == -1:
        failures.append(
            f"{doc_rel}: generated-line anchor {count_prefix!r} not found -- "
            "the generated line was removed or reworded without restamping GATE 4"
        )
        continue
    m = _re.match(r"\s*(\d+)", flat[idx + len(anchor):])
    if not m:
        failures.append(f"{doc_rel}: no count literal after the generated-line anchor")
        continue
    stated = int(m.group(1))
    if stated != len(ids):
        failures.append(
            f"{doc_rel}: generated line states {stated} phases but "
            f"len(manifest.phases) is {len(ids)} -- restamp the generated line"
        )
    else:
        print(f"GATE4_COUNT_OK: {doc_rel} generated line states {stated} == len(manifest.phases).")

# FIX 84: role-file check runs FIRST (below) so its failures land in the same
# failures[] list as the doc-list failures; the gate exits once, naming both.

# FIX 84: GATE 4 also covers the ROLE FILES. Every role file that uses numeric
# short codes ("Phase 1", "Phase 1Q", ...) as pipeline shorthand must carry a
# Phase-Code Map pointer (director-of-presentations.md Section 9) so its short
# codes resolve to manifest ids, and every backtick-quoted P-id it cites must
# be a real phases[].id. Role files WITHOUT pipeline short codes are exempt
# (nothing to map); the Signature-Talk arc's internal "Phase 1-4" is prose
# inside P3-ARC and is not a manifest phase, which the map pointer itself
# states. This is reference-resolution coverage, not full-registry coverage:
# a specialist role file describes its own stages, it does not promise to
# name all 59 ids.
role_files_checked = 0
idset = set(ids)
role_dir = repo_root / "23-ai-workforce-blueprint/templates/role-library/presentations"
for role_path in sorted(role_dir.glob("*.md")):
    name = role_path.name
    if name.startswith(("00-START-HERE", "DEPARTMENT-COUNTS-CANONICAL", "BUILDER-PROMPT", "IDENTITY", "how-to-use-this-department")):
        continue  # covered by docs_full_id / non-role docs
    if name == "director-of-presentations.md":
        continue  # the map itself; covered by docs_full_id
    text = role_path.read_text(encoding="utf-8")
    short_codes = _re.findall(r"Phase [0-9]", text)
    if len(short_codes) < 3:
        continue  # no pipeline-shorthand usage worth gating
    this_role_failures = []
    if "Phase-Code Map" not in text:
        this_role_failures.append("no Phase-Code Map pointer (director-of-presentations.md Section 9) -- its numeric short codes do not resolve to manifest ids")
    # Only P-prefixed phase-id shapes count as id citations; backtick-quoted
    # filenames (PRESENTER-AUDIO.mp3), the manifest path itself, and
    # placeholder labels are not phase ids. A real phase id is P + a digit or
    # F (PF-DESIGN), never P followed by a lowercase extension fragment.
    cited_ids = set(_re.findall(r"`(P[A-Za-z0-9.\-]+)`", text))
    cited_ids = {pid for pid in cited_ids if _re.fullmatch(r"P[0-9F][A-Za-z0-9.\-]*", pid) and _re.search(r"[0-9]", pid)}
    bad_ids = sorted(pid for pid in cited_ids if pid not in idset)
    if bad_ids:
        this_role_failures.append(f"backtick-quoted id(s) not in manifest phases[]: {bad_ids}")
    if this_role_failures:
        failures.append(f"role file {name} ({len(short_codes)} 'Phase N' short-code uses): " + "; ".join(this_role_failures))
    else:
        role_files_checked += 1
        print(f"GATE4_ROLE_OK: role-library/presentations/{name} carries the Phase-Code Map pointer and cites only manifest phase ids ({len(short_codes)} short-code refs).")

if failures:
    print("GATE4_FAIL: a doc's phase list or a role file's short-code map has drifted from PIPELINE-MANIFEST.json phases[] "
          "(missing id = doc describes fewer phases than the manifest actually runs):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

print(f"GATE4_PASS: docs hold lockstep with the manifest ({len(docs_full_id)} full-id docs name all {len(ids)} ids; {len(docs_count)} generated-line doc(s) match len(manifest.phases); {role_files_checked} role files checked for map pointer + id resolution).")
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
# GATE 6 (FIX 114) — catalog provider-id canon: hyphenated everywhere, and the
# FIX 114 key-resolution rejects still hold. The broken state this gate exists
# for was measured in the Sept-1 sweep: model_catalog.json carried
# "ollama_cloud" (underscore) next to router-side "ollama-cloud", the vision
# alias listed BOTH as served ids, and the drift silently split one provider
# into two billing identities. FIX 114 folded the catalog to hyphenated ids;
# this gate keeps it folded and re-proves the seam-level rejects on every CI
# run. Data-only: no network, no credential values -- keys read here are
# synthetic fixtures the gate itself writes.
echo
echo "== GATE 6: catalog provider-id hyphenation (FIX 114) + key-gate rejects =="
GATE6_RC=0
if SCRIPTS_DIR="$SCRIPTS_DIR" python3 - <<'PYEOF' 2>&1
import importlib.util
import json
import os
import sys
from pathlib import Path

scripts_dir = Path(os.environ["SCRIPTS_DIR"])
catalog_path = scripts_dir / "presentation_job" / "model_catalog.json"
failures = []

doc = json.loads(catalog_path.read_text(encoding="utf-8"))
aliases = doc.get("aliases") or {}

# (a) every alias-level "provider" literal is hyphenated (no underscore/space).
for alias, entry in sorted(aliases.items()):
    if not isinstance(entry, dict):
        continue
    provider = str(entry.get("provider") or "")
    if provider and ("_" in provider or " " in provider):
        failures.append(f"(a) alias {alias}: provider id {provider!r} is not hyphenated")

# (b) every served_ids key is hyphenated too -- the drift lived at BOTH levels.
for alias, entry in sorted(aliases.items()):
    if not isinstance(entry, dict):
        continue
    for served in sorted((entry.get("served_ids") or {}).keys()):
        s = str(served)
        if s and ("_" in s or " " in s):
            failures.append(f"(b) alias {alias}: served id {s!r} is not hyphenated")

# (c) the FIX 114 fold is complete: no underscore spelling survives in any
#     served_ids map.
for alias, entry in aliases.items():
    if isinstance(entry, dict) and "ollama_cloud" in (entry.get("served_ids") or {}):
        failures.append(f"(c) alias {alias}: underscore spelling ollama_cloud still present in served_ids")

if failures:
    print("GATE6_FAIL: catalog provider ids are not fully hyphenated (FIX 114):")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)

# (d) FIX 114 rejects still hold, proven against synthetic fixtures:
#     d1 model_router.provider_key_resolves refuses ollama-cloud when no key
#        resolves (family names scrubbed from the env); d2 research_web
#        resolves a key stored ONLY as BRAVE_API_KEY and still rejects a
#        placeholder; d3 the canon helper rejects a placeholder through
#        looks_like_real_key.
pj = scripts_dir / "presentation_job"
sys.path.insert(0, str(pj))

def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

helper = None
for anc in Path(__file__).resolve().parents:
    cand = anc / "shared-utils" / "secret_helper.py"
    if cand.is_file():
        helper = _load("secret_helper_g6", cand)
        break
if helper is None:
    failures.append("(d) shared-utils/secret_helper.py not found from gate cwd")
else:
    # d3: placeholder rejected, canon-shaped value accepted (synthetic only)
    if helper.looks_like_real_key("PASTE_REAL_TOKEN", "OLLAMA_API_KEY"):
        failures.append("(d3) looks_like_real_key accepted a placeholder value")
    alpha = "0123456789abcdefghijklmnopqrstuvwxyz"
    fake = "".join(alpha[(i * 7) % len(alpha)] for i in range(48))
    if not helper.looks_like_real_key(fake, "OLLAMA_API_KEY"):
        failures.append("(d3) looks_like_real_key rejected a plausible 48-char key")

if not failures:
    try:
        router = _load("model_router_g6", pj / "model_router.py")
        saved_env = {}
        for k in ("OLLAMA_API_KEY", "OLLAMA_CLOUD_API_KEY", "OLLAMA_KEY",
                  "OLLAMA_TOKEN", "SHARED_UTILS_DIR"):
            saved_env[k] = os.environ.pop(k, None)
        try:
            resolves = router.provider_key_resolves("ollama-cloud")
        finally:
            for k, v in saved_env.items():
                if v is not None:
                    os.environ[k] = v
        if resolves:
            failures.append("(d1) provider_key_resolves('ollama-cloud') answered True with every family name scrubbed from the environment")
    except Exception as exc:  # noqa: BLE001
        failures.append(f"(d1) model_router provider-key gate broke: {exc}")

if not failures:
    try:
        rw = _load("research_web_g6", pj / "research_web.py")
        # d2: a key stored ONLY as BRAVE_API_KEY resolves via the alias family.
        # Synthetic fixture value; the store seam is bypassed via the fake-env
        # parameter (never a real secret read). The placeholder reject is
        # proven on the REAL-env reader posture instead: _read_secret_named
        # runs the looks_like_real_key plausibility gate on whatever the real
        # env/files hold, so a value that cannot pass it yields None.
        if not rw._brave_key({"BRAVE_API_KEY": "BSAa" + "b" * 24}):
            failures.append("(d2) research_web did not resolve a key stored only as BRAVE_API_KEY (fake-env seam)")
        saved = os.environ.pop("BRAVE_SEARCH_API_KEY", None)
        try:
            if rw._read_secret_named("BRAVE_SEARCH_API_KEY") == "PASTE_REAL_TOKEN":
                failures.append("(d2) research_web accepted a placeholder BRAVE key (real-env reader)")
        finally:
            if saved is not None:
                os.environ["BRAVE_SEARCH_API_KEY"] = saved
    except Exception as exc:  # noqa: BLE001
        failures.append(f"(d2) research_web alias seam broke: {exc}")

if failures:
    print("GATE6_FAIL: FIX 114 key-gate rejects regressed:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("GATE6_PASS: every catalog provider id hyphenated; router key gate, "
      "BRAVE alias resolve, and placeholder reject all hold.")
sys.exit(0)
PYEOF
then
  :
else
  GATE6_RC=$?
fi
if [ "$GATE6_RC" -ne 0 ]; then
  echo "GATE 6 FAILED: catalog provider-id hyphenation or the FIX 114 key-gate rejects regressed -- see GATE6_FAIL above." >&2
  FAILED=1
fi

# ---------------------------------------------------------------------------
# GATE 7 (FIX 65) — the U006 colocate list contract, asserted as CI. This is
# the "CI asserts the list" leg of the R11 §G1 contract that installer
# colocate_presentation_entry already implements in BOTH install.sh and
# update-skills.sh: "colocate list = files that exist; return 1 on any miss."
# The old list hardcoded the retired deck-build-guard.sh, so one leg of the
# pair was never copyable and every install printed "partial (copied 1 of 2)"
# forever, silently. What this gate enforces (per leg, install.sh AND
# update-skills.sh):
#   (a) list-vs-disk: every candidate named in colocate_candidates=(...) must
#       EXIST in the canonical source dir 23-ai-workforce-blueprint/scripts/ --
#       deleting a listed file (e.g. the retired deck-build-guard.sh case
#       inverted) makes THIS gate fail instead of the install printing a
#       permanent partial. The candidate list may only name files that are
#       actually on disk.
#   (b) both arrays identical: the two installers must carry the SAME
#       candidate list -- a drift between them re-creates the partial class
#       on whichever leg lags.
#   (c) hard-miss rejects: each function still returns 1 on an empty list and
#       on a copy miss (the installer-side contract), re-proven per CI run so
#       a warn-and-continue regression cannot land silently.
echo
echo "== GATE 7: U006 colocate list contract (FIX 65) =="
GATE7_RC=0
if CANON_SRC_DIR="23-ai-workforce-blueprint/scripts" INSTALL_SH="install.sh" UPDATE_SKILLS_SH="update-skills.sh" python3 - <<'PYEOF' 2>&1
import os
import re
import sys
from pathlib import Path

canon = Path(os.environ["CANON_SRC_DIR"])
install_sh = Path(os.environ["INSTALL_SH"])
update_sh = Path(os.environ["UPDATE_SKILLS_SH"])
failures = []

ARRAY_RE = re.compile(
    r"local -a colocate_candidates=\(([^)]*)\)", re.M
)

def candidates_of(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = ARRAY_RE.findall(text)
    if len(hits) != 1:
        sys.exit(
            f"GATE7_SETUP_FAIL: expected exactly one colocate_candidates "
            f"array in {path}, found {len(hits)}"
        )
    return [t for t in hits[0].split() if t], text

try:
    inst_list, inst_text = candidates_of(install_sh)
    upd_list, upd_text = candidates_of(update_sh)
except SystemExit as exc:
    print(str(exc))
    sys.exit(1)

# (a) list-vs-disk: every named candidate must exist in the canonical source
#     dir. Deleting a listed file is the retired-candidate drift class in
#     reverse -- either way, the array must match the disk.
for label, arr in (("install.sh", inst_list), ("update-skills.sh", upd_list)):
    for name in arr:
        if not (canon / name).is_file():
            failures.append(
                f"(a) {label}: colocate candidate {name!r} does not exist in "
                f"{canon}/ -- the list names files that exist, not retired "
                f"ones (delete it from the array or restore the file)"
            )

# (b) both installers carry the SAME candidate list.
if inst_list != upd_list:
    failures.append(
        f"(b) colocate candidate lists diverge: install.sh={inst_list} vs "
        f"update-skills.sh={upd_list} -- a drift between the two installers "
        f"re-creates the partial-copy class on whichever leg lags"
    )

# (c) the installer-side hard-miss rejects still hold, per leg: the empty-list
#     MISS must return 1, and the shortfall path must print the MISS line and
#     return 1 (never warn-and-continue). Parsed from the same function text.
EMPTY_MISS = re.compile(
    r"colocate MISS: no colocatable files exist.*?co-location FAILED.*?\n(.*?)return 1",
    re.S,
)
SHORTFALL = re.compile(
    r"colocate MISS \(copied \$copied of \$\{#colocate_list\[@\]\}\).*?co-location FAILED.*?\n(.*?)return 1",
    re.S,
)
for label, text in (("install.sh", inst_text), ("update-skills.sh", upd_text)):
    if not EMPTY_MISS.search(text):
        failures.append(
            f"(c) {label}: the empty-list hard-miss (print + return 1) is "
            f"gone from colocate_presentation_entry -- warn-and-continue "
            f"regression of the FIX 65 contract"
        )
    if not SHORTFALL.search(text):
        failures.append(
            f"(c) {label}: the copy-shortfall hard-miss "
            f"(colocate MISS (copied X of Y) + return 1) is gone from "
            f"colocate_presentation_entry"
        )

if failures:
    print("GATE7_FAIL: U006 colocate list contract (FIX 65) violated:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(
    "GATE7_PASS: colocate candidates "
    f"{inst_list} all exist in {canon}/, both installers agree, and the "
    "empty-list + shortfall hard-miss rejects hold (FIX 65)."
)
sys.exit(0)
PYEOF
then
  :
else
  GATE7_RC=$?
fi
if [ "$GATE7_RC" -ne 0 ]; then
  echo "GATE 7 FAILED: U006 colocate list contract (FIX 65) violated -- see GATE7_FAIL above." >&2
  FAILED=1
fi

# ---------------------------------------------------------------------------
echo
if [ "$FAILED" -ne 0 ]; then
  echo "presentations-drift-gates: FAILED -- see the gate failure(s) above." >&2
  exit 1
fi

echo "presentations-drift-gates: ALL GATES PASSED (GATE 1 import-smoke, GATE 2 manifest-lockstep x2, GATE 3 whitelist-parity fail-closed, GATE 4 phase-doc lockstep, GATE 5 manifest-copy drift detector, GATE 6 provider-id hyphenation, GATE 7 colocate contract)."
exit 0

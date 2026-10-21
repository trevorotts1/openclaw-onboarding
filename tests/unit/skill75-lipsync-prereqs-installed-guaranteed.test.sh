#!/usr/bin/env bash
# tests/unit/skill75-lipsync-prereqs-installed-guaranteed.test.sh
#
# REGRESSION GUARD - skill 75 (drama-song-ad-factory) lip-sync prerequisites are
# INSTALLED by the install/update path, not left as an advisory manual step.
#
# THE GAP THIS CLOSES.  Skill 75's lip-sync gate is fail-closed by design: with
# mediapipe/opencv/numpy missing, or assets/face_landmarker.task absent, every
# lip-sync job is refused (UNMEASURED / PictureGateUnavailable).  Both pieces were
# declared in PREREQS.json as type=manual severity=optional, and
# shared-utils/check-skill-prereqs.sh never blocks on manual types.  Neither
# install.sh nor update-skills.sh installed them, so every fresh box and every
# re-wired box landed with the same two holes and rediscovered them on the first
# paid lip-sync job.
#
# Weakening the gate is NOT the fix.  The gate stays fail-closed; this check makes
# sure the REASON it fires is removed at install time, and stays removed across
# fleet rolls (update-skills.sh replaces the skill folder, so a previously
# downloaded model must be backfilled).
#
# WHAT THIS PROVES (static only; no network, no install, no interpreter run):
#   T1  mediapipe AND opencv are pip-installed somewhere in the FRESH-INSTALL path
#       (install.sh itself, or a script install.sh invokes).
#   T2  face_landmarker.task is obtained WITH verification (sha256 or size pin)
#       into the skill's assets/ directory, in that same path.
#   T3  the SAME guarantee is reachable from update-skills.sh, so a fleet roll
#       backfills boxes that were installed before the fix.
#   T4  the detection actually discriminates: a COPY of the ensuring file with the
#       mediapipe line removed is rejected.  Nothing on disk is mutated.
#
# Detection is semantic, not a fixed function name, so it holds whether the fix is
# a shared ensure script called by both installers or inline blocks in each.
#
# Exit 0 = the two gaps are guaranteed by the install/update path.
# Exit 1 = a gap can silently survive a fresh install or a fleet roll.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
INSTALL_SH="$REPO_ROOT/install.sh"
UPDATE_SH="$REPO_ROOT/update-skills.sh"
SKILL_DIR="$REPO_ROOT/75-drama-song-ad-factory"

PASS=0
FAIL=0
pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== skill75-lipsync-prereqs-installed-guaranteed.test.sh ==="
echo ""

[ -f "$INSTALL_SH" ] || { echo "  FAIL: $INSTALL_SH not found"; exit 1; }
[ -f "$UPDATE_SH" ]  || { echo "  FAIL: $UPDATE_SH not found"; exit 1; }
[ -d "$SKILL_DIR" ]  || { echo "  FAIL: $SKILL_DIR not found"; exit 1; }

# ---------------------------------------------------------------------------
# Detectors.  Each reads ONE file and answers a yes/no by exit status.
# ---------------------------------------------------------------------------

# T1: python deps actually pip-installed (mediapipe + opencv + a pip invocation).
file_installs_py_deps() {
    local f="$1"
    [ -f "$f" ] || return 1
    grep -qi 'mediapipe' "$f" 2>/dev/null || return 1
    grep -qi 'opencv'    "$f" 2>/dev/null || return 1
    # a real install invocation, not a comment that merely names the packages
    grep -Eq '(python3?|"\$[A-Za-z_][A-Za-z0-9_]*"|[A-Za-z0-9_./-]*/python[0-9.]*)[[:space:]]+-m[[:space:]]+pip[[:space:]]+install|pip[0-9.]*[[:space:]]+install|pip install' "$f" 2>/dev/null || return 1
    return 0
}

# T2: face_landmarker.task fetched WITH verification into the model directory.
# Accepts either an inline verified fetch or a call to the skill's own verifier.
file_verifies_model() {
    local f="$1"
    [ -f "$f" ] || return 1
    # downstream verifier that pins sha256 AND byte size, invoked for real
    # (a bare comment mentioning it does not count).
    if grep -Eq '^[[:space:]]*[^#[:space:]].*install_face_model' "$f" 2>/dev/null; then
        return 0
    fi
    grep -q 'face_landmarker' "$f" 2>/dev/null || return 1
    grep -Eqi 'sha256|sha_256|shasum' "$f" 2>/dev/null || return 1
    grep -Eqi 'MODEL_BYTES|expected_bytes|byte_size|getsize|wc -c|stat -f%z|stat -c%s' "$f" 2>/dev/null || return 1
    return 0
}

# Does <consumer> reference <provider> by path or basename?
file_references() {
    local consumer="$1" provider="$2"
    [ -f "$consumer" ] || return 1
    local base
    base="$(basename "$provider")"
    grep -Fq "$base" "$consumer" 2>/dev/null && return 0
    grep -Fq "$provider" "$consumer" 2>/dev/null && return 0
    return 1
}

# Every candidate file that could carry the ensure step, in a stable order.
# The lip_sync/lip_gate READERS are excluded: they merely name the packages in a
# failure string ("run pip install mediapipe ..."), which would look like an
# install and make the check vacuous. install_face_model.py (a real downloader)
# stays in.
candidate_files() {
    local d f
    for f in "$INSTALL_SH" "$UPDATE_SH"; do printf '%s\n' "$f"; done
    for d in "$REPO_ROOT/shared-utils" "$REPO_ROOT/scripts" "$REPO_ROOT/platform" "$SKILL_DIR/scripts"; do
        [ -d "$d" ] || continue
        find "$d" -type f \( -name '*.sh' -o -name '*.py' \) 2>/dev/null
    done | grep -v '/lip_gate/' | grep -v '/__pycache__/' | grep -v '/tests/' | sort -u
}

# True when <consumer> guarantees the deps itself, or invokes a file that does.
consumer_guarantees() {
    local consumer="$1" f
    if file_installs_py_deps "$consumer" && file_verifies_model "$consumer"; then
        return 0
    fi
    while IFS= read -r f; do
        [ "$f" = "$consumer" ] && continue
        if file_installs_py_deps "$f" && file_verifies_model "$f" && file_references "$consumer" "$f"; then
            return 0
        fi
    done < <(candidate_files)
    return 1
}

# ---------------------------------------------------------------------------
# T1 + T2: fresh-install path
# ---------------------------------------------------------------------------
if consumer_guarantees "$INSTALL_SH"; then
    pass "T1/T2 fresh install guarantees mediapipe+opencv and a verified face_landmarker.task"
else
    fail "T1/T2 fresh install does NOT guarantee mediapipe+opencv AND a verified face model (install.sh or a script it invokes must pip-install mediapipe+opencv and place a sha256/size-verified face_landmarker.task)"
fi

# ---------------------------------------------------------------------------
# T3: fleet-roll path
# ---------------------------------------------------------------------------
if consumer_guarantees "$UPDATE_SH"; then
    pass "T3 update-skills.sh backfills the same two prerequisites on a fleet roll"
else
    fail "T3 update-skills.sh does NOT backfill the prerequisites; boxes installed before the fix stay broken after a roll (the skill folder is replaced on update)"
fi

# ---------------------------------------------------------------------------
# T2b: the verifier pins BOTH hash and size, into assets/
# ---------------------------------------------------------------------------
MODEL_INSTALLER="$SKILL_DIR/scripts/core/lip_sync/lip_gate/install_face_model.py"
if [ -f "$MODEL_INSTALLER" ] \
   && grep -q 'face_landmarker.task' "$MODEL_INSTALLER" \
   && grep -Eqi 'sha256' "$MODEL_INSTALLER" \
   && grep -Eqi 'MODEL_BYTES' "$MODEL_INSTALLER" \
   && grep -q '"assets"' "$MODEL_INSTALLER"; then
    pass "T2b install_face_model.py pins sha256 + byte size and targets assets/face_landmarker.task"
else
    fail "T2b install_face_model.py must pin sha256 AND byte size and place assets/face_landmarker.task"
fi

# ---------------------------------------------------------------------------
# T4: discrimination.  Mutate a COPY; the copy must be rejected.
# ---------------------------------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PROVIDER=""
# Prefer the file the fresh-install path actually invokes.
while IFS= read -r f; do
    [ "$f" = "$INSTALL_SH" ] && continue
    if file_installs_py_deps "$f" && file_verifies_model "$f" && file_references "$INSTALL_SH" "$f"; then
        PROVIDER="$f"; break
    fi
done < <(candidate_files)
# Fall back to an inline block in install.sh itself.
if [ -z "$PROVIDER" ] && file_installs_py_deps "$INSTALL_SH" && file_verifies_model "$INSTALL_SH"; then
    PROVIDER="$INSTALL_SH"
fi

if [ -z "$PROVIDER" ]; then
    fail "T4 cannot prove discrimination: no installer file currently installs mediapipe+opencv (fix not landed yet)"
else
    # strip every line that installs or names mediapipe
    grep -vi 'mediapipe' "$PROVIDER" > "$TMP/mutated.sh" 2>/dev/null
    if file_installs_py_deps "$TMP/mutated.sh"; then
        fail "T4 NON-DISCRIMINATING: detector passed a copy with the mediapipe line removed ($PROVIDER)"
    else
        pass "T4 detector discriminates: removing mediapipe from a copy of $(basename "$PROVIDER") is rejected"
    fi

    # model verification must also be required, not merely mentioned
    grep -Ei 'sha256|MODEL_BYTES|install_face_model' "$PROVIDER" >/dev/null 2>&1 \
        && { grep -Evi 'sha256|MODEL_BYTES|install_face_model' "$PROVIDER" > "$TMP/mutated2.sh" 2>/dev/null
             if file_verifies_model "$TMP/mutated2.sh"; then
                 fail "T4 NON-DISCRIMINATING: detector passed a copy with every hash/size pin removed ($PROVIDER)"
             else
                 pass "T4 detector discriminates: removing hash/size verification from a copy is rejected"
             fi; }
fi

# ---------------------------------------------------------------------------
echo ""
echo "  Result: $PASS passed, $FAIL failed"
if [ "$FAIL" -ne 0 ]; then
    echo "  FAIL: the two skill-75 lip-sync prerequisites are not guaranteed by the install/update path."
    exit 1
fi
echo "  OK: skill-75 lip-sync prerequisites are installed by install.sh and backfilled by update-skills.sh."
exit 0

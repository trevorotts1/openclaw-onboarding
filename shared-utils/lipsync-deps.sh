#!/usr/bin/env bash
# shared-utils/lipsync-deps.sh
#
# Skill 75 (75-drama-song-ad-factory) lip-sync gate prerequisites. Installed by
# BOTH install.sh (fresh box) and update-skills.sh (every fleet roll, so boxes
# that are already wired get backfilled too).
#
# Two pieces used to ship missing on every box because INSTALL.md step 2b was a
# manual step nothing automated:
#   1. mediapipe + opencv + numpy importable by the python3 the skill runs on.
#   2. assets/face_landmarker.task, the sha256-pinned mediapipe face model.
# Both lip-sync gates are fail-closed. This module removes the REASON for the
# gate to fire; it never weakens the gate. An install that fails prints a
# FAILED line with the exact URL/status and leaves a marker so the next update
# pass retries. A box that is still missing a piece still refuses lip-sync jobs.
#
# Idempotent: when everything is present and valid the only work is import
# probes plus one file hash (well under 2s) and no network call is made.
#
# Check-only mode (never mutates, safe to run anywhere):
#   bash shared-utils/lipsync-deps.sh --check
#   DRAMA_LIPSYNC_CHECK=1 bash shared-utils/lipsync-deps.sh
# Exit codes: 0 all present, 2 something missing, 1 tooling error (no python3).
#
# Repair an already-broken box, one line:
#   bash <(curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/shared-utils/lipsync-deps.sh)
#
# Interpreter: skill 75 runs its lip_gate scripts with `python3` from PATH
# (no venv in the skill), so that is the interpreter these packages must land
# in. LIPSYNC_PY overrides the probe/install interpreter, but note the gate
# itself still uses python3, so an override only helps when python3 points at
# the same interpreter.

LIPSYNC_PKG_SPECS=("mediapipe>=0.10.14" "opencv-python-headless" "numpy")
LIPSYNC_MODEL_NAME="face_landmarker.task"
LIPSYNC_MODEL_SHA256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
LIPSYNC_MODEL_BYTES="3758596"
LIPSYNC_MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task"

_lipsync_log()  { printf '  lipsync-deps: %s\n' "$*"; }
_lipsync_fail() { printf '  lipsync-deps: FAILED: %s\n' "$*" >&2; }

# OpenClaw root: /data/.openclaw on a VPS container, OC_CONFIG or ~/.openclaw
# on a Mac. Same /data-else-HOME rule the rest of the fleet uses.
_lipsync_oc_root() {
    if [ -n "${OC_CONFIG:-}" ]; then printf '%s' "$OC_CONFIG"; return 0; fi
    if [ -d "/data/.openclaw" ]; then printf '%s' "/data/.openclaw"; return 0; fi
    printf '%s' "$HOME/.openclaw"
}

_lipsync_skills_dir() {
    if [ -n "${SKILLS_DIR:-}" ]; then printf '%s' "$SKILLS_DIR"; return 0; fi
    if declare -F discover_skills_dir >/dev/null 2>&1; then
        local _d=""
        _d="$(discover_skills_dir 2>/dev/null || true)"
        if [ -n "$_d" ]; then printf '%s' "$_d"; return 0; fi
    fi
    if [ -d "/data/.openclaw/skills" ]; then printf '%s' "/data/.openclaw/skills"; return 0; fi
    printf '%s' "$(_lipsync_oc_root)/skills"
}

_lipsync_skill_dir() { printf '%s' "$(_lipsync_skills_dir)/75-drama-song-ad-factory"; }
_lipsync_model_path() { printf '%s' "$(_lipsync_skill_dir)/assets/$LIPSYNC_MODEL_NAME"; }
_lipsync_clip_model_path() { printf '%s' "$(_lipsync_skill_dir)/scripts/core/lip_sync/lip_gate/$LIPSYNC_MODEL_NAME"; }
_lipsync_marker() { printf '%s' "$(_lipsync_oc_root)/.lipsync-deps.pending"; }

_lipsync_py() {
    if [ -n "${LIPSYNC_PY:-}" ] && [ -x "${LIPSYNC_PY}" ]; then printf '%s' "$LIPSYNC_PY"; return 0; fi
    local _p=""
    _p="$(command -v python3 2>/dev/null || true)"
    if [ -n "$_p" ]; then printf '%s' "$_p"; return 0; fi
    return 1
}

# Space-separated list of the three modules that do not import (empty = all ok).
_lipsync_missing_mods() {
    "$1" -c 'import sys
missing = []
for m in ("mediapipe", "cv2", "numpy"):
    try:
        __import__(m)
    except Exception:
        missing.append(m)
print(" ".join(missing))' 2>/dev/null || printf 'mediapipe cv2 numpy'
}

_lipsync_sha256() {
    "$1" -c 'import hashlib, sys
h = hashlib.sha256()
with open(sys.argv[1], "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""):
        h.update(b)
print(h.hexdigest())' "$2" 2>/dev/null
}

# A model counts as good only at the exact pinned size AND sha256.
_lipsync_model_valid() {
    local _py="$1" _path="$2" _size=""
    [ -f "$_path" ] || return 1
    _size="$(wc -c < "$_path" 2>/dev/null | tr -d ' ' || true)"
    [ "$_size" = "$LIPSYNC_MODEL_BYTES" ] || return 1
    [ "$(_lipsync_sha256 "$_py" "$_path")" = "$LIPSYNC_MODEL_SHA256" ] || return 1
    return 0
}

# Both gates must be able to find a good model:
#   picture gate  -> assets/ or $LIPSYNC_FACE_MODEL
#   clip gate     -> $LIPSYNC_FACE_MODEL or the lip_gate/ dir next to the code
_lipsync_model_ok() {
    local _py="$1"
    if [ -n "${LIPSYNC_FACE_MODEL:-}" ] && _lipsync_model_valid "$_py" "$LIPSYNC_FACE_MODEL"; then
        return 0
    fi
    _lipsync_model_valid "$_py" "$(_lipsync_model_path)" || return 1
    _lipsync_model_valid "$_py" "$(_lipsync_clip_model_path)" || return 1
    return 0
}

_lipsync_mark_pending() {
    local _m
    _m="$(_lipsync_marker)"
    mkdir -p "$(dirname "$_m")" 2>/dev/null || true
    printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo unknown)" "$1" > "$_m" 2>/dev/null || true
}

_lipsync_clear_pending() {
    rm -f "$(_lipsync_marker)" 2>/dev/null || true
}

_lipsync_pip_install() {
    # Runs pip in the caller's process (no subshell) so the exit code is pip's.
    local _py="$1" _out="" _rc=0
    _out="$("$_py" -m pip install --quiet --disable-pip-version-check --no-input "${LIPSYNC_PKG_SPECS[@]}" 2>&1)" || _rc=$?
    if [ "$_rc" -eq 0 ]; then _lipsync_log "installed ${LIPSYNC_PKG_SPECS[*]} into $_py"; return 0; fi

    # PEP 668 box: system python refuses a bare install. --user is the smallest
    # step that does not touch system site-packages. _rc is reset per attempt so
    # a fallback that succeeds is reported as the success it is.
    _rc=0
    _out="$("$_py" -m pip install --quiet --user --disable-pip-version-check --no-input "${LIPSYNC_PKG_SPECS[@]}" 2>&1)" || _rc=$?
    if [ "$_rc" -eq 0 ]; then _lipsync_log "installed ${LIPSYNC_PKG_SPECS[*]} with --user into $_py"; return 0; fi

    # Last resort on a Debian/Ubuntu container whose python is marked
    # externally managed and where --user is also refused. Loudly announced:
    # this is the only path that makes the gate runnable on such a box.
    _rc=0
    _out="$("$_py" -m pip install --quiet --break-system-packages --disable-pip-version-check --no-input "${LIPSYNC_PKG_SPECS[@]}" 2>&1)" || _rc=$?
    if [ "$_rc" -eq 0 ]; then
        _lipsync_log "installed ${LIPSYNC_PKG_SPECS[*]} with --break-system-packages (externally-managed python) into $_py"
        return 0
    fi

    _lipsync_fail "pip install ${LIPSYNC_PKG_SPECS[*]} failed (pip exit $_rc) for $_py"
    printf '%s\n' "$_out" | sed 's/^/    /' >&2
    case "$_out" in
        *"No matching distribution"*|*"Could not find a version"*)
            _lipsync_fail "mediapipe has no wheel for $("$_py" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo this-python). The lip-sync gate runs as \`python3\`, so python3 on PATH must be a supported interpreter (3.10-3.12): install one and make python3 resolve to it, then re-run this check." ;;
        *"externally-managed-environment"*)
            _lipsync_fail "this python is externally managed and all three install modes were refused; install the packages with the box's package manager or point python3 at an interpreter without that marker." ;;
    esac
    return 2
}

# ensure_lipsync_deps [--check|--apply]
#   --check  report present/missing, never mutate (DRAMA_LIPSYNC_CHECK=1 = same)
#   --apply  install what is missing (default)
# Returns 0 satisfied, 2 still missing, 1 tooling error.
ensure_lipsync_deps() {
    local _mode="apply" _rc=0
    case "${1:-}" in
        --check|check)     _mode="check" ;;
        --apply|apply|"")  _mode="apply" ;;
        *) _lipsync_fail "unknown argument '$1' (use --check or --apply)"; return 1 ;;
    esac
    if [ "${DRAMA_LIPSYNC_CHECK:-0}" = "1" ]; then _mode="check"; fi

    local _py=""
    if ! _py="$(_lipsync_py)"; then
        _lipsync_fail "no python3 on PATH; cannot check or install mediapipe/opencv/numpy"
        _lipsync_mark_pending "no-python3"
        return 1
    fi

    local _skill_dir="" _missing="" _model_ok=0
    _skill_dir="$(_lipsync_skill_dir)"

    # No skill 75 on this box -> no lip-sync gate -> nothing to prepare. Not a
    # failure, and no packages are pulled for a skill that is not installed.
    if [ ! -d "$_skill_dir" ]; then
        _lipsync_log "skill 75 not installed in $(_lipsync_skills_dir) - nothing to prepare"
        return 0
    fi

    _missing="$(_lipsync_missing_mods "$_py")"
    if _lipsync_model_ok "$_py"; then _model_ok=1; fi

    if [ "$_mode" = "check" ]; then
        _lipsync_log "check-only (interpreter: $_py; skill: $_skill_dir)"
        local _m _name
        for _m in mediapipe cv2 numpy; do
            _name="$_m"
            [ "$_m" = "cv2" ] && _name="opencv"
            case " $_missing " in
                *" $_m "*) _lipsync_log "  MISSING  $_name" ;;
                *)         _lipsync_log "  present  $_name" ;;
            esac
        done
        if [ "$_model_ok" -eq 1 ]; then
            _lipsync_log "  present  $LIPSYNC_MODEL_NAME"
        else
            _lipsync_log "  MISSING  $LIPSYNC_MODEL_NAME (expected $( [ -n "${LIPSYNC_FACE_MODEL:-}" ] && printf '%s' "$LIPSYNC_FACE_MODEL" || printf '%s' "$(_lipsync_model_path)"), sha256 $LIPSYNC_MODEL_SHA256, $LIPSYNC_MODEL_BYTES bytes)"
        fi
        if [ -z "$_missing" ] && [ "$_model_ok" -eq 1 ]; then
            _lipsync_log "OK: all lip-sync prerequisites present"
            return 0
        fi
        _lipsync_log "INCOMPLETE: lip-sync gate will refuse jobs until the missing pieces are installed"
        return 2
    fi

    # ---- apply mode -------------------------------------------------------
    if [ -z "$_missing" ]; then
        _lipsync_log "mediapipe, opencv, numpy already importable in $_py (nothing to do)"
    else
        _lipsync_log "missing python modules: $_missing -> installing ${LIPSYNC_PKG_SPECS[*]}"
        if ! _lipsync_pip_install "$_py"; then
            _rc=2
        fi
        _missing="$(_lipsync_missing_mods "$_py")"
        if [ -n "$_missing" ]; then
            _lipsync_fail "after install these still do not import in $_py: $_missing"
            _rc=2
        fi
    fi

    # ---- model ------------------------------------------------------------
    if [ "$_model_ok" -eq 1 ]; then
        _lipsync_log "$LIPSYNC_MODEL_NAME already present and valid (nothing to do)"
    else
        local _installer="$_skill_dir/scripts/core/lip_sync/lip_gate/install_face_model.py"
        if [ ! -f "$_installer" ]; then
            _lipsync_fail "model missing and the skill's installer is absent: $_installer (is skill 75 installed in $(_lipsync_skills_dir)?)"
            _rc=2
        else
            local _out="" _prc=0
            _out="$("$_py" "$_installer" 2>&1)" || _prc=$?
            if [ "$_prc" -ne 0 ]; then
                _lipsync_fail "model download failed (installer exit $_prc) from $LIPSYNC_MODEL_URL"
                printf '%s\n' "$_out" | sed 's/^/    /' >&2
                _rc=2
            else
                _lipsync_log "$_out"
                # The clip gate (mouth_landmarks.model_path) looks next to its own
                # module, not in assets/. Mirror the verified file there so a box
                # does not need LIPSYNC_FACE_MODEL set for a measured lip-sync job.
                local _src _dst
                _src="$(_lipsync_model_path)"
                _dst="$(_lipsync_clip_model_path)"
                if _lipsync_model_valid "$_py" "$_src"; then
                    if ! _lipsync_model_valid "$_py" "$_dst"; then
                        mkdir -p "$(dirname "$_dst")" 2>/dev/null || true
                        cp -p "$_src" "$_dst" 2>/dev/null || cp "$_src" "$_dst" 2>/dev/null || true
                    fi
                    _lipsync_model_valid "$_py" "$_dst" || _lipsync_fail "could not mirror $LIPSYNC_MODEL_NAME to $_dst (clip gate will need LIPSYNC_FACE_MODEL)"
                fi
            fi
        fi
        if ! _lipsync_model_ok "$_py"; then _rc=2; fi
    fi

    if [ "$_rc" -eq 0 ]; then
        _lipsync_clear_pending
        _lipsync_log "OK: mediapipe, opencv, numpy and $LIPSYNC_MODEL_NAME all present"
        return 0
    fi
    local _model_state="missing"
    if _lipsync_model_ok "$_py"; then _model_state="ok"; fi
    _lipsync_mark_pending "missing: python=${_missing:-none} model=$_model_state"
    _lipsync_fail "lip-sync prerequisites still incomplete; the fail-closed gate will refuse lip-sync jobs on this box until repaired. Re-run: bash <(curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/shared-utils/lipsync-deps.sh)"
    return 2
}

# Executed directly (including `bash <(curl ...)`); sourced by install.sh and
# update-skills.sh with LIPSYNC_DEPS_LIB_ONLY=1.
if [ "${LIPSYNC_DEPS_LIB_ONLY:-0}" != "1" ]; then
    ensure_lipsync_deps "${1:---apply}"
    exit $?
fi

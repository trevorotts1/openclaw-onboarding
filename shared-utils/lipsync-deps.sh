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
# Interpreter: the ONE canonical python (oc_python in platform/common.sh,
# v27.1.80): on a Linux box the image's /usr/bin/python3, which is what the
# gateway runs skill 75's lip_gate scripts with; on a Mac python3 from PATH.
# Never the Homebrew python3 a `docker exec` PATH lists first. LIPSYNC_PY
# overrides the probe/install interpreter (a Homebrew python is still refused
# on Linux by the install step).

LIPSYNC_PKG_SPECS=("mediapipe>=0.10.14" "opencv-python-headless" "numpy")
LIPSYNC_MODEL_NAME="face_landmarker.task"
LIPSYNC_MODEL_SHA256="64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff"
LIPSYNC_MODEL_BYTES="3758596"
LIPSYNC_MODEL_URL="https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"

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
# ONE face-model path (D19): the locator default, <skill>/assets/, or the
# LIPSYNC_FACE_MODEL override. The legacy lip_gate/ location is migration
# source only — every reader resolves through scripts/core/face_model_locator.py.
_lipsync_model_path() { printf '%s' "$(_lipsync_skill_dir)/assets/$LIPSYNC_MODEL_NAME"; }
_lipsync_legacy_model_path() { printf '%s' "$(_lipsync_skill_dir)/scripts/core/lip_sync/lip_gate/$LIPSYNC_MODEL_NAME"; }
_lipsync_marker() { printf '%s' "$(_lipsync_oc_root)/.lipsync-deps.pending"; }

# Load the ONE-PYTHON resolver (platform/common.sh) from the repo layout, the
# installed layout (<root>/skills/shared-utils -> <root>/platform) or the root.
_lipsync_load_resolver() {
    declare -F oc_python >/dev/null 2>&1 && return 0
    local _here="" _c
    _here="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" 2>/dev/null && pwd)"
    for _c in "$_here/../platform/common.sh" "$_here/../../platform/common.sh" \
              "$(_lipsync_oc_root)/platform/common.sh"; do
        # shellcheck source=/dev/null
        [ -f "$_c" ] && { . "$_c"; return 0; }
    done
    return 1
}

_lipsync_py() {
    if [ -n "${LIPSYNC_PY:-}" ] && [ -x "${LIPSYNC_PY}" ]; then printf '%s' "$LIPSYNC_PY"; return 0; fi
    _lipsync_load_resolver || { _lipsync_fail "platform/common.sh (the one-python resolver) not found under $(_lipsync_oc_root); refresh the onboarding bundle"; return 1; }
    oc_python
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

# One path for every gate (D19): the override when set, else assets/. The
# picture gate and the measured lip-sync gate resolve through
# scripts/core/face_model_locator.py and must see this exact file.
_lipsync_model_ok() {
    local _py="$1"
    if [ -n "${LIPSYNC_FACE_MODEL:-}" ]; then
        _lipsync_model_valid "$_py" "$LIPSYNC_FACE_MODEL"
        return $?
    fi
    _lipsync_model_valid "$_py" "$(_lipsync_model_path)"
}

# Old boxes kept the model in the legacy lip_gate/ location. Migrate a verified
# copy instead of re-downloading; the legacy file is not read by any gate now.
_lipsync_migrate_legacy() {
    local _py="$1" _src _dst
    _src="$(_lipsync_legacy_model_path)"
    _dst="$(_lipsync_model_path)"
    [ -n "${LIPSYNC_FACE_MODEL:-}" ] && return 0
    _lipsync_model_valid "$_py" "$_dst" && return 0
    _lipsync_model_valid "$_py" "$_src" || return 0
    mkdir -p "$(dirname "$_dst")" 2>/dev/null || true
    cp -p "$_src" "$_dst" 2>/dev/null || cp "$_src" "$_dst" 2>/dev/null || true
    if _lipsync_model_valid "$_py" "$_dst"; then
        _lipsync_log "migrated $LIPSYNC_MODEL_NAME from legacy lip_gate/ to $(dirname "$_dst")"
        return 0
    fi
    _lipsync_fail "could not migrate $LIPSYNC_MODEL_NAME from $_src"
    return 1
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
    # ONE-PYTHON: a venv interpreter installs into its own venv; anything else
    # goes through oc_pip_install (<python> -m pip install --user, plus the PEP
    # 668 override when the interpreter is externally managed, on Linux AND on a
    # Homebrew-python Mac, always together with --user). The old bare
    # system-site --break-system-packages tier (no --user) is gone: it wrote
    # into Homebrew's own site-packages on Hostinger boxes.
    local _py="$1" _out="" _rc=0
    if "$_py" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' >/dev/null 2>&1; then
        _out="$("$_py" -m pip install --quiet --disable-pip-version-check --no-input "${LIPSYNC_PKG_SPECS[@]}" 2>&1)" || _rc=$?
    elif _lipsync_load_resolver; then
        _out="$(OC_PYTHON="$_py" oc_pip_install --quiet --no-input "${LIPSYNC_PKG_SPECS[@]}" 2>&1)" || _rc=$?
    else
        _out="platform/common.sh (the one-python resolver) not found; refusing an install outside it"; _rc=1
    fi
    if [ "$_rc" -eq 0 ]; then _lipsync_log "installed ${LIPSYNC_PKG_SPECS[*]} into $_py"; return 0; fi

    _lipsync_fail "package install of ${LIPSYNC_PKG_SPECS[*]} failed (pip exit $_rc) for $_py"
    printf '%s\n' "$_out" | sed 's/^/    /' >&2
    case "$_out" in
        *"No matching distribution"*|*"Could not find a version"*)
            _lipsync_fail "no mediapipe/opencv wheel for $("$_py" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || echo this-python) on this platform (mediapipe ships py3-none wheels; check the network and the pip log above), then re-run this check." ;;
        *"externally-managed-environment"*)
            _lipsync_fail "$_py refused the --user install as externally managed even with the PEP 668 override; use a venv interpreter (LIPSYNC_PY=<venv>/bin/python), then re-run." ;;
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
        _lipsync_fail "no canonical python3 (one-python resolver); cannot check or install mediapipe/opencv/numpy"
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
            _lipsync_log "  MISSING  $LIPSYNC_MODEL_NAME (expected $( [ -n "${LIPSYNC_FACE_MODEL:-}" ] && printf '%s' "$LIPSYNC_FACE_MODEL" || printf '%s' "$(_lipsync_model_path)"), sha256 $LIPSYNC_MODEL_SHA256, $LIPSYNC_MODEL_BYTES bytes; one path for every gate via face_model_locator)"
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
        _lipsync_migrate_legacy "$_py" || _rc=2
        if ! _lipsync_model_ok "$_py"; then
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

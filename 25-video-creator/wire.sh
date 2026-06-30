#!/usr/bin/env bash
# =============================================================================
# 25-video-creator/wire.sh
# Skill-25 wiring installer — (re)syncs the installed `video-creator` copy and
# (re)builds its venv on every update pass.
#
# WHY THIS FILE EXISTS (root cause it fixes — same class of bug as skill 44):
#   update-skills.sh's wiring loop walks ONLY numbered skill dirs (`[0-9]*/`,
#   update-skills.sh:1617) and runs a skill's own installer ONLY when one is
#   found at the skill ROOT, in this priority:
#     wire.sh > install.sh > scripts/install.sh > setup-*.sh
#   (update-skills.sh:1631-1646). Skill 25 does NOT install in place: per its
#   INSTALL.md it installs by COPYING the whole skill into an UN-numbered
#   ~/.openclaw/skills/video-creator/ (the runtime location referenced by
#   TOOLS.md / CORE_UPDATES.md / qc-video-creator.sh) and building a local `venv`
#   with pinned deps (`moviepy==1.0.3 opencv-python requests pillow numpy`).
#   The wiring loop re-syncs the NUMBERED source (25-video-creator/) but never
#   re-copies the un-numbered runtime copy and never rebuilds its venv — so the
#   installed `video-creator` silently drifts behind the synced source
#   fleet-wide (source on disk != working install), exactly like `caf` did.
#   This wire.sh sits at the skill ROOT so the loop DOES pick it up (first in the
#   priority list) and reconciles the installed copy + venv to match the source.
#
# WHAT IT DOES (idempotent, fail-soft):
#   - replicates the committed install (INSTALL.md Step 2/3): copy the skill
#     source into <VC_DIR>, create/keep a `venv`, pip-install the pinned runtime,
#     make the scripts executable
#   - writes <VC_DIR>/.installed-from so scripts/tool-drift-check.sh can PROVE the
#     installed copy matches the current skill-version
#   - FAST no-op when the stamp version already matches source AND the venv python
#     can import the load-bearing pin `moviepy.editor` (source-on-disk alone is
#     never trusted — that is the exact drift bug this guards; `moviepy.editor`
#     also catches the documented MoviePy v1-vs-v2 hazard, since v2 removed it)
#   - NEVER aborts the overall update: every failure is logged loudly and the
#     script still exits 0 (the wiring loop continues regardless)
#
# Invoked by update-skills.sh as:  bash wire.sh --idempotent   (arg ignored;
#   idempotency is unconditional here). Honours VIDEO_CREATOR_DIR / VENV_DIR /
#   PYTHON env overrides for tests. No bare `gws`, no destructive ops (additive
#   copy, mirroring INSTALL.md's `cp -r`), no client-specific values.
# =============================================================================

# Fail-soft by contract: do NOT use `set -e` / `set -u`. A per-skill installer
# must never take down the fleet-wide update. Errors are handled explicitly and
# this script ALWAYS exits 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[skill25/wire] $*"; }

# ---- install root: the UN-numbered runtime copy, sibling of this source ------
# Derive from SCRIPT_DIR's parent so the path is platform-correct (Mac
# $HOME/.openclaw/skills vs Linux /data/.openclaw/skills) WITHOUT hardcoding. On
# Mac this equals the ~/.openclaw/skills/video-creator path tool-drift-check.sh
# probes. INSTALL.md names the venv `venv` (Step 2) — match that exactly.
SKILLS_PARENT="$(dirname "$SCRIPT_DIR")"
VC_DIR="${VIDEO_CREATOR_DIR:-$SKILLS_PARENT/video-creator}"
VENV_DIR="${VENV_DIR:-$VC_DIR/venv}"
STAMP="$VC_DIR/.installed-from"
PY="${PYTHON:-python3}"

# Pinned runtime per INSTALL.md Step 2.4. MoviePy MUST stay v1.x — its scripts
# import `moviepy.editor`, which MoviePy v2 removed.
PIP_PINS=( "moviepy==1.0.3" opencv-python requests pillow numpy )

# ---- source version: the truth the installed copy must match ----------------
SRC_VER="unknown"
if [ -f "$SCRIPT_DIR/skill-version.txt" ]; then
  SRC_VER="$(tr -d '[:space:]' < "$SCRIPT_DIR/skill-version.txt" 2>/dev/null || echo unknown)"
  [ -z "$SRC_VER" ] && SRC_VER="unknown"
fi

# ---- preflight: missing source scripts or python -> log + bow out -----------
if [ ! -d "$SCRIPT_DIR/scripts" ]; then
  log "ERROR: skill source scripts/ not found at $SCRIPT_DIR/scripts — cannot install video-creator. Skipping (update continues)."
  exit 0
fi
if ! command -v "$PY" >/dev/null 2>&1; then
  log "ERROR: '$PY' not found — cannot build video-creator venv. Skipping (update continues)."
  exit 0
fi
# Safety: never let the install dir resolve onto the source dir (would self-copy).
if [ "$VC_DIR" = "$SCRIPT_DIR" ]; then
  log "ERROR: install dir resolved to the source dir ($VC_DIR) — refusing to self-copy. Skipping (update continues)."
  exit 0
fi

# ---- drift stamp: record the source version this copy was built from --------
# Format matches scripts/tool-drift-check.sh's parser (SKILL_VERSION= /
# ONBOARDING_VERSION=). ONBOARDING_VERSION is left to the env if the updater
# exports it, else empty — an empty installed marker is correctly ignored by the
# guard (it only compares wire markers when BOTH sides are non-empty), so the
# SKILL_VERSION comparison stays the authoritative freshness signal.
write_stamp() {
  mkdir -p "$VC_DIR" 2>/dev/null || true
  if {
        echo "TOOL=video-creator"
        echo "SKILL_VERSION=$SRC_VER"
        echo "ONBOARDING_VERSION=${ONBOARDING_VERSION:-}"
        echo "INSTALLED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date 2>/dev/null)"
        echo "SOURCE_PATH=$SCRIPT_DIR"
      } > "$STAMP" 2>/dev/null; then
    log "stamped $STAMP (SKILL_VERSION=$SRC_VER)"
  else
    log "WARN: could not write stamp $STAMP (non-fatal)"
  fi
}

# ---- idempotency: fast no-op when already current --------------------------
# Current == stamp SKILL_VERSION matches source AND the venv python can import
# the load-bearing pin `moviepy.editor` (creds-free; also proves MoviePy is v1,
# since v2 removed that module) AND a representative script is present in the
# copy. Source-on-disk alone is deliberately NOT trusted — that is the drift bug.
is_current() {
  [ -f "$STAMP" ] || return 1
  local stamped
  stamped="$(grep -E '^SKILL_VERSION=' "$STAMP" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '[:space:]')"
  [ -n "$stamped" ] && [ "$stamped" = "$SRC_VER" ] || return 1
  [ -x "$VENV_DIR/bin/python" ] || return 1
  [ -f "$VC_DIR/scripts/text_to_video.py" ] || return 1
  "$VENV_DIR/bin/python" -c "import moviepy.editor" >/dev/null 2>&1 || return 1
  return 0
}

if is_current; then
  log "video-creator already current (SKILL_VERSION=$SRC_VER, venv import OK) — no rebuild needed."
  write_stamp   # refresh INSTALLED_AT / ONBOARDING_VERSION; cheap, idempotent
  exit 0
fi

# ---- rebuild (idempotent): sync source copy + venv + pinned deps ------------
rebuild() {
  log "rebuilding video-creator for SKILL_VERSION=$SRC_VER -> $VC_DIR"

  mkdir -p "$VC_DIR" || { log "ERROR: mkdir $VC_DIR failed"; return 1; }

  # Additive sync of the source into the install copy (mirrors INSTALL.md's
  # `cp -r`). The venv lives ONLY in $VC_DIR and is absent from the source, so
  # this never clobbers it; user output/config under $VC_DIR is likewise kept.
  if ! cp -R "$SCRIPT_DIR/." "$VC_DIR/"; then
    log "ERROR: source copy ($SCRIPT_DIR -> $VC_DIR) failed"
    return 1
  fi
  chmod +x "$VC_DIR/scripts/"*.py 2>/dev/null || true

  # venv: create if missing, otherwise reuse (idempotent).
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "creating venv -> $VENV_DIR"
    "$PY" -m venv "$VENV_DIR" || { log "ERROR: venv creation failed"; return 1; }
  fi

  # shellcheck disable=SC1091
  . "$VENV_DIR/bin/activate" 2>/dev/null || { log "ERROR: venv activate failed"; return 1; }
  pip install --upgrade pip -q 2>/dev/null || log "WARN: pip self-upgrade warned (continuing)"
  if ! pip install -q "${PIP_PINS[@]}"; then
    log "ERROR: 'pip install ${PIP_PINS[*]}' failed"
    deactivate 2>/dev/null || true
    return 1
  fi
  deactivate 2>/dev/null || true

  log "rebuild complete."
  return 0
}

if rebuild; then
  write_stamp
  log "OK: video-creator (re)synced and stamped at SKILL_VERSION=$SRC_VER."
else
  log "WARN: video-creator rebuild hit an error (see lines above). Update continues; tool-drift-check will flag this box for an operator rebuild."
fi

# Fail-soft contract: ALWAYS succeed so the wiring loop never aborts.
exit 0

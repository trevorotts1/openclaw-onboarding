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
#     source into <VC_DIR>, create/keep a venv, pip-install the pinned runtime,
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
# VENV LOCATION (fixed 2026-09 — was previously <VC_DIR>/venv, INSIDE the skill
#   root): OpenClaw's skill discovery walks every skill root up to depth 6 on
#   every rescan, skipping only dot-prefixed names and node_modules — it does
#   NOT skip `venv`. A ~215 MB site-packages tree inside the skill root got
#   walked on every rescan. The venv now lives OUTSIDE every skill root, as a
#   sibling of the skills parent: $(dirname "$SKILLS_PARENT")/venvs/video-creator
#   (Mac ~/.openclaw/venvs/video-creator, VPS /data/.openclaw/venvs/video-creator),
#   still overridable by VENV_DIR. A legacy <VC_DIR>/venv is migrated in place
#   (moved, not rebuilt) the first time this script runs after the fix.
#
# DUPLICATE SKILL REGISTRATION (fixed 2026-09): the runtime copy previously
#   carried its own SKILL.md (copied verbatim from the source), so OpenClaw
#   registered `video-creator` twice and logged a precedence collision on every
#   scan. The copy step below excludes SKILL.md (and venv/.venv) so only
#   25-video-creator registers the skill; any stale <VC_DIR>/SKILL.md left over
#   from an older install is removed on every pass.
#
# Invoked by update-skills.sh as:  bash wire.sh --idempotent   (arg ignored;
#   idempotency is unconditional here). Honours VIDEO_CREATOR_DIR / VENV_DIR /
#   PYTHON env overrides for tests. No bare `gws`, no destructive ops beyond the
#   one named below, no client-specific values.
#   The one allowed `rm -rf` is the legacy <VC_DIR>/venv, and only once its
#   contents are safely moved (or a healthy replacement already exists) at the
#   new location — never a blind delete.
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
# probes. The venv is derived the same way, one level further up, so it lands
# outside every skill root (see the VENV LOCATION header note above).
SKILLS_PARENT="$(dirname "$SCRIPT_DIR")"
VC_DIR="${VIDEO_CREATOR_DIR:-$SKILLS_PARENT/video-creator}"
VENV_DIR="${VENV_DIR:-$(dirname "$SKILLS_PARENT")/venvs/video-creator}"
LEGACY_VENV="$VC_DIR/venv"   # pre-fix location: INSTALL.md named it `venv`, inside VC_DIR
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

# ---- venv migration: move any legacy in-skill-root venv out, before anything
# else runs (including the is_current fast path, so an already-current box
# still migrates instead of keeping the duplicate skill + in-root venv forever).
venv_ok() { [ -x "$1/bin/python" ] && "$1/bin/python" -c "import moviepy.editor" >/dev/null 2>&1; }
if [ "$LEGACY_VENV" != "$VENV_DIR" ] && [ -d "$LEGACY_VENV" ]; then
  mkdir -p "$(dirname "$VENV_DIR")" 2>/dev/null || true
  if [ -e "$VENV_DIR" ] && venv_ok "$VENV_DIR"; then
    rm -rf "$LEGACY_VENV" && log "removed legacy venv at $LEGACY_VENV (new location already healthy)"
  else
    [ -e "$VENV_DIR" ] && rm -rf "$VENV_DIR"   # broken/partial new one; legacy replaces it
    if mv "$LEGACY_VENV" "$VENV_DIR" 2>/dev/null; then
      log "moved legacy venv $LEGACY_VENV -> $VENV_DIR"
    else
      log "WARN: legacy venv move failed ($LEGACY_VENV -> $VENV_DIR)"
    fi
  fi
fi
# A venv relocated by `mv` (by this script, or by hand before this fix existed)
# keeps a stale activate script pointing at the old path (bin/python still
# imports fine; `source activate` does not). Repair it in place, in-process —
# no reinstall, no network.
if [ -x "$VENV_DIR/bin/python" ] && [ -f "$VENV_DIR/bin/activate" ] && ! grep -qF "$VENV_DIR" "$VENV_DIR/bin/activate" 2>/dev/null; then
  if "$VENV_DIR/bin/python" -m venv --without-pip "$VENV_DIR" >/dev/null 2>&1; then
    log "repaired venv activate/scripts for relocated venv at $VENV_DIR"
  else
    log "WARN: venv script repair failed for $VENV_DIR"
  fi
fi
# The runtime copy must never register a second `video-creator` skill: a stale
# SKILL.md from an older install (this fix stops copying a new one) is removed
# on every pass.
rm -f "$VC_DIR/SKILL.md" 2>/dev/null

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
  # `cp -r`), EXCEPT SKILL.md (would register a 2nd `video-creator` skill) and
  # any venv/.venv that might exist in the source folder (the venv lives only
  # at $VENV_DIR, outside every skill root — never copied into $VC_DIR). User
  # output/config already under $VC_DIR is untouched either way.
  local _entry _base
  for _entry in "$SCRIPT_DIR"/* "$SCRIPT_DIR"/.[!.]*; do
    [ -e "$_entry" ] || continue
    _base="$(basename "$_entry")"
    case "$_base" in SKILL.md|venv|.venv) continue ;; esac
    cp -R "$_entry" "$VC_DIR/" || { log "ERROR: copy $_entry -> $VC_DIR failed"; return 1; }
  done
  chmod +x "$VC_DIR/scripts/"*.py 2>/dev/null || true

  # venv: create if missing, otherwise reuse (idempotent). Lives outside the
  # skill root (see header) so OpenClaw's skill-root scan never walks it.
  mkdir -p "$(dirname "$VENV_DIR")" 2>/dev/null || true
  if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "creating venv -> $VENV_DIR"
    "$PY" -m venv "$VENV_DIR" || { log "ERROR: venv creation failed"; return 1; }
  fi

  # Use the venv's own python module invocations directly — never bare `pip`
  # and never `source activate` — so this does not depend on activate having
  # been (re)generated correctly (see the relocation repair above) or on the
  # calling shell's PATH.
  "$VENV_DIR/bin/python" -m pip install --upgrade pip -q 2>/dev/null || log "WARN: pip self-upgrade warned (continuing)"
  if ! "$VENV_DIR/bin/python" -m pip install -q "${PIP_PINS[@]}"; then
    log "ERROR: 'pip install ${PIP_PINS[*]}' failed"
    return 1
  fi

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

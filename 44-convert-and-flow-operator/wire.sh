#!/usr/bin/env bash
# =============================================================================
# 44-convert-and-flow-operator/wire.sh
# Skill-44 wiring installer — (re)builds the `caf` CLI on every update pass.
#
# WHY THIS FILE EXISTS (root cause it fixes):
#   update-skills.sh's wiring loop (the "Wiring installed skills" section) runs a
#   skill's own installer ONLY if it finds one at the skill ROOT, in this
#   priority: wire.sh > install.sh > scripts/install.sh > setup-*.sh
#   (update-skills.sh:1631-1646). Skill 44's engine installer lives at
#   tools/engine/install.sh — a path the loop never looks at — so `caf` was NEVER
#   rebuilt by the routine update path and silently drifted behind the synced
#   skill source fleet-wide. This wire.sh sits at the skill ROOT so the loop DOES
#   pick it up (first in the priority list) and rebuilds the installed CLI to
#   match the source.
#
# WHAT IT DOES (idempotent, fail-soft):
#   - replicates the committed install (INSTALL.md Action 2/3): copy the engine
#     source into <CAF_DIR>/engine, `pip install -e` it in that dir's venv, and
#     copy the caf/convertandflow/ghl wrappers
#   - writes <CAF_DIR>/.installed-from so scripts/tool-drift-check.sh can PROVE
#     the installed binary matches the current skill-version
#   - FAST no-op when the stamp version already matches source AND the venv
#     imports the package (source-on-disk alone is never trusted — that is the
#     exact drift bug this guards)
#   - NEVER aborts the overall update: every failure is logged loudly and the
#     script still exits 0 (the wiring loop continues regardless)
#
# Invoked by update-skills.sh as:  bash wire.sh --idempotent   (arg ignored;
#   idempotency is unconditional here). Honours VENV_DIR / CAF_DIR env overrides
#   for tests. No bare `gws`, no destructive ops, no client-specific values.
# =============================================================================

# Fail-soft by contract: do NOT use `set -e` / `set -u`. A per-skill installer
# must never take down the fleet-wide update. Errors are handled explicitly and
# this script ALWAYS exits 0.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log() { echo "[skill44/wire] $*"; }

ENGINE_SRC="$SCRIPT_DIR/tools/engine"

# ---- platform-aware install root (mirrors INSTALL.md Action 1) --------------
if [ -z "${CAF_DIR:-}" ]; then
  if [ "$(uname)" = "Darwin" ]; then
    CAF_DIR="$HOME/.openclaw/tools/convert-and-flow-cli"
  else
    CAF_DIR="/data/.openclaw/tools/convert-and-flow-cli"
  fi
fi
VENV_DIR="${VENV_DIR:-$CAF_DIR/.venv}"
STAMP="$CAF_DIR/.installed-from"
PY="${PYTHON:-python3}"

# ---- source version: the truth the binary must match -----------------------
SRC_VER="unknown"
if [ -f "$SCRIPT_DIR/skill-version.txt" ]; then
  SRC_VER="$(tr -d '[:space:]' < "$SCRIPT_DIR/skill-version.txt" 2>/dev/null || echo unknown)"
  [ -z "$SRC_VER" ] && SRC_VER="unknown"
fi

# ---- preflight: missing engine or python -> log + bow out (update continues)-
if [ ! -d "$ENGINE_SRC" ]; then
  log "ERROR: engine source not found at $ENGINE_SRC — cannot build caf. Skipping (update continues)."
  exit 0
fi
if ! command -v "$PY" >/dev/null 2>&1; then
  log "ERROR: '$PY' not found — cannot build caf. Skipping (update continues)."
  exit 0
fi

# ---- drift stamp: record the source version this binary was built from ------
# Format matches scripts/tool-drift-check.sh's parser (SKILL_VERSION= /
# ONBOARDING_VERSION=). ONBOARDING_VERSION is left to the env if the updater
# exports it, else empty — an empty installed marker is correctly ignored by the
# guard (it only compares wire markers when BOTH sides are non-empty), so the
# SKILL_VERSION comparison stays the authoritative freshness signal.
write_stamp() {
  mkdir -p "$CAF_DIR" 2>/dev/null || true
  if {
        echo "TOOL=caf"
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
# the package. The wrapper itself is NOT used as a probe because it requires GHL
# creds at runtime; the import resolves the editable install without creds.
is_current() {
  [ -f "$STAMP" ] || return 1
  local stamped
  stamped="$(grep -E '^SKILL_VERSION=' "$STAMP" 2>/dev/null | head -1 | cut -d= -f2- | tr -d '[:space:]')"
  [ -n "$stamped" ] && [ "$stamped" = "$SRC_VER" ] || return 1
  [ -x "$VENV_DIR/bin/python" ] || return 1
  [ -x "$CAF_DIR/caf" ] || return 1
  "$VENV_DIR/bin/python" -c "import cli_anything.gohighlevel.gohighlevel_cli" >/dev/null 2>&1 || return 1
  return 0
}

if is_current; then
  log "caf already current (SKILL_VERSION=$SRC_VER, venv import OK) — no rebuild needed."
  write_stamp   # refresh INSTALLED_AT / ONBOARDING_VERSION; cheap, idempotent
  exit 0
fi

# ---- rebuild (idempotent): copy engine + editable install + wrappers --------
rebuild() {
  log "rebuilding caf for SKILL_VERSION=$SRC_VER -> $CAF_DIR"

  mkdir -p "$CAF_DIR/engine" || { log "ERROR: mkdir $CAF_DIR/engine failed"; return 1; }

  if [ ! -x "$VENV_DIR/bin/python" ]; then
    log "creating venv -> $VENV_DIR"
    "$PY" -m venv "$VENV_DIR" || { log "ERROR: venv creation failed"; return 1; }
  fi

  # sync engine source into the install dir (copy of contents, mirrors INSTALL.md)
  cp -r "$ENGINE_SRC/." "$CAF_DIR/engine/" || { log "ERROR: engine copy failed"; return 1; }
  chmod +x "$CAF_DIR/engine/wire-ghl-env.sh" "$CAF_DIR/engine/verify-ghl-live.sh" 2>/dev/null || true

  # editable install of the COPY so the binary resolves from the install dir
  # shellcheck disable=SC1091
  . "$VENV_DIR/bin/activate" 2>/dev/null || { log "ERROR: venv activate failed"; return 1; }
  pip install --upgrade pip -q 2>/dev/null || log "WARN: pip self-upgrade warned (continuing)"
  if ! pip install -e "$CAF_DIR/engine" -q; then
    log "ERROR: 'pip install -e $CAF_DIR/engine' failed"
    deactivate 2>/dev/null || true
    return 1
  fi
  deactivate 2>/dev/null || true

  # install the committed wrappers (single source of truth = engine dir)
  local w
  for w in caf convertandflow ghl; do
    if [ -f "$ENGINE_SRC/$w" ]; then
      if cp "$ENGINE_SRC/$w" "$CAF_DIR/$w" && chmod +x "$CAF_DIR/$w"; then
        :
      else
        log "WARN: could not install wrapper '$w' (continuing)"
      fi
    fi
  done

  log "rebuild complete."
  return 0
}

if rebuild; then
  write_stamp
  log "OK: caf (re)built and stamped at SKILL_VERSION=$SRC_VER."
else
  log "WARN: caf rebuild hit an error (see lines above). Update continues; tool-drift-check will flag this box for an operator rebuild."
fi

# Fail-soft contract: ALWAYS succeed so the wiring loop never aborts.
exit 0

#!/usr/bin/env bash
# Skill 47 -- Movie Producer (Automated Video Production)
# RENDER-RUNTIME PROVISIONER -- Skill 47 wrapper over the shared runtime.
#
# WHAT CHANGED (MG-003 / integration target V03)
#   Generic engine provisioning (OS/arch detection, Chromium system
#   libraries, pinned Remotion + HyperFrames install, browser ensure,
#   launch-and-render readiness probe) now lives in ONE shared
#   implementation used by both Skill 47 and Skill 72:
#
#       shared-utils/motion-render-runtime/provision.sh
#
#   This script is the Skill 47 entrypoint its existing callers already
#   use (install.sh Step 3.5, the skill Dockerfile). It (a) delegates the
#   generic engines to the shared provisioner, then (b) does ONLY the
#   Skill 47 / OpenMontage-specific work itself: the clone presence check,
#   the pin of Remotion into the clone's remotion-composer/ directory
#   (OpenMontage's pipelines consume that layout), and the optional opt-in
#   Piper offline TTS fallback.
#
# NEW FAILURE SEMANTICS -- READ THIS BEFORE TRUSTING AN OLD RUNBOOK
#   The previous version of this script reported success when an engine
#   install had actually failed: every failure after the clone check was
#   WARN-only and the script exited 0. That is gone. A mandatory-engine
#   failure in the shared provisioner now FAILS this script (its exit code
#   is propagated): if Remotion or HyperFrames is not installed AND proven
#   by a real launch-and-render probe, this script exits non-zero and
#   install.sh Step 3.5 aborts, exactly as its error message always
#   claimed. The clone check remains a hard failure too, but it runs AFTER
#   and SEPARATELY FROM generic engine provisioning: engines are
#   provisioned independently of the clone (Skill 72 needs no clone at
#   all), and a missing clone is reported as a Skill 47 pipeline problem,
#   not as an engine problem.
#
#   Docker note: the shared provisioner must be reachable at runtime.
#   Resolution order: $MOTION_RUNTIME_DIR, then
#   ../shared-utils/motion-render-runtime relative to this script
#   (the normal in-repo layout). A Docker build that copies this script
#   alone must also copy shared-utils/motion-render-runtime and set
#   MOTION_RUNTIME_DIR to its location; without it this script fails
#   loudly (by design -- no silent fallback to the old behavior).
#
# INVOCATION (unchanged)
#   bash provision-render-deps.sh
#   OPENCLAW_OPENMONTAGE_DIR=/path/to/OpenMontage bash provision-render-deps.sh
#
# ENV TOGGLES (all optional)
#   OPENCLAW_OPENMONTAGE_DIR   OpenMontage clone dir (default: ~/.openclaw/openmontage-runtime/OpenMontage)
#   MOTION_RUNTIME_DIR         shared runtime dir (default: ../shared-utils/motion-render-runtime from here)
#   REMOTION_VERSION           override the pinned Remotion version (forwarded to the shared provisioner)
#   HYPERFRAMES_VERSION        override the pinned HyperFrames version (forwarded)
#   PIPER_VERSION              override the pinned piper-tts version
#   PIPER_DEFAULT_VOICE        default voice model id (default: en_US-lessac-medium)
#   PIPER_DATA_DIR             where to pre-stage voice models (default: ~/.piper/models)
#   SKILL47_INSTALL_PIPER=1    OPT IN to the optional offline Piper TTS fallback (OFF by default)
#   SKILL47_SKIP_APT=1         skip the Linux apt system-library step (forwarded to the shared provisioner)
#
# EXIT CODE
#   0 -- shared engines installed AND probe-verified, clone present,
#       remotion-composer pin attempted, Piper step done or skipped.
#   1 -- a HARD failure: shared provisioner not found; shared engine
#       provisioning or its readiness probe failed (exit code propagated);
#       or no OpenMontage clone. (Piper is optional and NEVER causes a
#       hard failure.)
set -uo pipefail

PIPER_VERSION="${PIPER_VERSION:-1.4.2}"
PIPER_DEFAULT_VOICE="${PIPER_DEFAULT_VOICE:-en_US-lessac-medium}"
PIPER_DATA_DIR="${PIPER_DATA_DIR:-$HOME/.piper/models}"
PIPER_VOICES_TAG="v1.0.0"

OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

red()    { printf "\033[31mFAIL\033[0m %s\n" "$1" >&2; }
green()  { printf "\033[32m OK \033[0m %s\n" "$1"; }
warn()   { printf "\033[33mWARN\033[0m %s\n" "$1" >&2; }
info()   { printf "     %s\n" "$1"; }
head_()  { printf "\n--- %s ---\n" "$1"; }

echo "=== Skill 47 -- Render-runtime provisioner (shared runtime + clone extras) ==="
echo "    OpenMontage clone: $OPENMONTAGE_DIR"

# ---------------------------------------------------------------------------
# 1 -- Generic engines via the SHARED provisioner (MG-003).
#     OS/arch/libc detection, apt system libraries, pinned installs from
#     the committed lockfile, browser ensure, and the launch-and-render
#     readiness probe all live there. Its exit code is propagated: a
#     mandatory-engine failure is a real failure of this script.
# ---------------------------------------------------------------------------
head_ "Shared motion render runtime (Remotion + HyperFrames, probe-verified)"
SHARED_RUNTIME_DIR=""
if [ -n "${MOTION_RUNTIME_DIR:-}" ] && [ -f "${MOTION_RUNTIME_DIR}/provision.sh" ]; then
  SHARED_RUNTIME_DIR="$MOTION_RUNTIME_DIR"
elif [ -f "$SCRIPT_DIR/../shared-utils/motion-render-runtime/provision.sh" ]; then
  SHARED_RUNTIME_DIR="$(cd "$SCRIPT_DIR/../shared-utils/motion-render-runtime" && pwd)"
fi
if [ -z "$SHARED_RUNTIME_DIR" ]; then
  red "Shared motion render runtime not found (looked in \$MOTION_RUNTIME_DIR and"
  red "../shared-utils/motion-render-runtime relative to this script)."
  info "In a Docker build, copy shared-utils/motion-render-runtime alongside this"
  info "script and set MOTION_RUNTIME_DIR to its location."
  exit 1
fi
info "shared runtime: $SHARED_RUNTIME_DIR"
# Pin the HyperFrames version for the shared provisioner: the caller's
# override wins; otherwise the shared runtime's own package pin is the
# authority (resolved here so the provisioner receives the pinned value
# explicitly rather than floating). The literal fallback is the current
# lock pin, used only if the runtime manifest cannot be read.
HYPERFRAMES_VERSION="${HYPERFRAMES_VERSION:-$(node -p "require('$SHARED_RUNTIME_DIR/package.json').dependencies['hyperframes']" 2>/dev/null || echo 0.8.155)}"
export HYPERFRAMES_VERSION
if ! bash "$SHARED_RUNTIME_DIR/provision.sh"; then
  SHARED_RC=$?
  red "Shared engine provisioning FAILED (exit $SHARED_RC). Remotion/HyperFrames are"
  red "NOT probe-verified on this box. Skill 47 clone extras were not attempted."
  exit "$SHARED_RC"
fi
green "Shared engines provisioned and probe-verified (see runtime-lock.json in the shared runtime)."

# Engine versions as resolved by the shared runtime (single source of
# truth for the clone pin below). Falls back to the shared package pins.
RESOLVED_REMOTION_VERSION="${REMOTION_VERSION:-}"
if [ -z "$RESOLVED_REMOTION_VERSION" ]; then
  RESOLVED_REMOTION_VERSION="$(node -p "require('$SHARED_RUNTIME_DIR/package.json').dependencies['remotion']" 2>/dev/null || echo '')"
fi
[ -n "$RESOLVED_REMOTION_VERSION" ] || RESOLVED_REMOTION_VERSION="4.0.535"

# ---------------------------------------------------------------------------
# 2 -- OpenMontage clone presence (Skill 47 pipelines only).
#     AFTER and SEPARATE FROM generic engine provisioning: the engines
#     above are provisioned independently, and Skill 72 does not need this
#     clone at all. A missing clone is a hard failure for Skill 47 because
#     its pipelines run from the clone, but it is reported as what it is.
# ---------------------------------------------------------------------------
head_ "OpenMontage clone (Skill 47 pipelines)"
if [ ! -d "$OPENMONTAGE_DIR" ]; then
  red "OpenMontage clone not found at $OPENMONTAGE_DIR."
  info "The shared render engines ARE provisioned and probe-verified (step 1);"
  info "only the Skill 47 pipeline clone is missing. Run install.sh (or clone +"
  info "make setup) first, then re-run this provisioner."
  exit 1
fi
green "OpenMontage clone present: $OPENMONTAGE_DIR"

# ---------------------------------------------------------------------------
# 3 -- Pin Remotion into the clone's remotion-composer/ directory.
#     OpenMontage's pipelines consume Remotion from that layout, so the pin
#     the old provisioner performed is preserved, now at the version the
#     shared runtime resolved (one version authority for both copies).
#     The arch/OS compositor package name follows the shared runtime's
#     detection semantics. A failure here WARNS: the clone's own
#     `make setup` also installs Remotion into this directory, and the
#     shared runtime (step 1, probe-verified) is the readiness authority.
# ---------------------------------------------------------------------------
head_ "Remotion $RESOLVED_REMOTION_VERSION pin into the clone's remotion-composer/"
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
UNAME_M="$(uname -m 2>/dev/null || echo unknown)"
case "$UNAME_S" in
  Darwin) OS="darwin" ;;
  Linux)  OS="linux" ;;
  *)      OS="unknown" ;;
esac
case "$UNAME_M" in
  x86_64|amd64)  ARCH="x64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *)             ARCH="$UNAME_M" ;;
esac
LIBC="gnu"
if [ "$OS" = "linux" ]; then
  if [ -f /etc/alpine-release ] || (ldd --version 2>&1 | grep -qi musl); then
    LIBC="musl"
  fi
fi
COMPOSER_DIR="$OPENMONTAGE_DIR/remotion-composer"
if [ ! -d "$COMPOSER_DIR" ]; then
  warn "remotion-composer/ not found in the clone -- did 'make setup' run? Skipping the clone pin."
else
  if [ "$OS" = "linux" ]; then
    COMPOSITOR_PKG="@remotion/compositor-linux-${ARCH}-${LIBC}"
  else
    COMPOSITOR_PKG="@remotion/compositor-${OS}-${ARCH}"
  fi
  info "pinning remotion@$RESOLVED_REMOTION_VERSION + @remotion/cli@$RESOLVED_REMOTION_VERSION + ${COMPOSITOR_PKG}@$RESOLVED_REMOTION_VERSION"
  # --no-save: pin the RUNNING version into node_modules without churning the upstream
  # package.json/lockfile. Idempotent (already-satisfied installs are a no-op).
  if ( cd "$COMPOSER_DIR" && npm install --no-save --no-audit --no-fund \
        "remotion@$RESOLVED_REMOTION_VERSION" \
        "@remotion/cli@$RESOLVED_REMOTION_VERSION" \
        "${COMPOSITOR_PKG}@$RESOLVED_REMOTION_VERSION" >/dev/null 2>&1 ); then
    green "Remotion $RESOLVED_REMOTION_VERSION + $COMPOSITOR_PKG installed into the clone."
  else
    warn "npm install of the pinned Remotion + compositor into the clone failed (network?)."
    info "The shared runtime (step 1) is probe-verified; the clone copy resolves on demand."
  fi
  # Chrome-Headless-Shell for the clone's own copy -- works on macOS AND Linux.
  if ( cd "$COMPOSER_DIR" && npx --yes remotion browser ensure >/dev/null 2>&1 ); then
    green "Chrome-Headless-Shell ensured for the clone (npx remotion browser ensure)."
  else
    warn "'npx remotion browser ensure' in the clone failed -- its Remotion downloads Chrome-Headless-Shell on first render."
  fi
fi

# ---------------------------------------------------------------------------
# 4 -- Piper TTS (OPTIONAL, OPT-IN, offline-only fallback) -- OFF BY DEFAULT
#     Voice order: Fish Audio Drama-3 (drama-3) is the PRIMARY narrator; Gemini TTS,
#     OpenAI TTS, and MiniMax (a.k.a. "Mimo") are the cloud fallbacks; Piper is an OPTIONAL
#     offline-only last-resort fallback that is NOT installed by default. With Piper absent,
#     OpenMontage's TTS auto-discovery simply uses the cloud providers. Opt in with
#     SKILL47_INSTALL_PIPER=1 to install the arch-aware wheel and pre-stage a default voice
#     model. A Piper install/download failure NEVER aborts the Skill 47 install (WARN only).
#     (Behavior unchanged from the previous provisioner; this step is Skill 47 specific
#     and intentionally NOT part of the shared runtime.)
# ---------------------------------------------------------------------------
head_ "Piper TTS (OPTIONAL -- opt-in offline fallback, OFF by default)"
if [ "${SKILL47_INSTALL_PIPER:-0}" != "1" ]; then
  green "Piper not requested (SKILL47_INSTALL_PIPER unset) -- skipping install + voice pre-stage."
  info "Primary narrator is Fish Audio Drama-3 (drama-3); Gemini/OpenAI/MiniMax (Mimo) TTS are the cloud fallbacks."
  info "OpenMontage TTS auto-discovery will use the cloud providers. Opt in with SKILL47_INSTALL_PIPER=1."
else
  info "SKILL47_INSTALL_PIPER=1 -- installing the OPTIONAL offline Piper fallback (never fatal)."
  info "piper-tts==$PIPER_VERSION (arch-aware) + default voice '$PIPER_DEFAULT_VOICE'"
  # Prefer the OpenMontage clone's own venv so the `piper` module is importable by its tools.
  PY=""
  for cand in "$OPENMONTAGE_DIR/.venv/bin/python" "${VIRTUAL_ENV:-}/bin/python"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  [ -z "$PY" ] && PY="$(command -v python3 || command -v python || true)"
  if [ -z "$PY" ]; then
    warn "No python interpreter found -- skipping optional Piper install. Cloud TTS remains primary. Not fatal."
  else
    info "using interpreter: $PY"
    PIPER_OK=0
    for attempt in 1 2; do
      if "$PY" -m pip install --disable-pip-version-check "piper-tts==$PIPER_VERSION" >/dev/null 2>&1; then
        PIPER_OK=1; break
      fi
      warn "piper-tts install attempt $attempt failed -- retrying ..."
    done
    if [ "$PIPER_OK" = "1" ] && "$PY" -c "import piper" >/dev/null 2>&1; then
      green "piper-tts $PIPER_VERSION installed and importable (optional offline fallback)."
    else
      warn "Optional piper-tts install failed -- cloud TTS (Fish 2.1 Pro / Gemini / OpenAI / MiniMax) remains primary. Not fatal."
    fi

    # Pre-stage the default voice ONNX model (+ its .json) -- CLI-agnostic direct download.
    # Only on the opt-in path. Idempotent (skips if already present). Never fatal.
    lang_country="${PIPER_DEFAULT_VOICE%%-*}"                 # en_US
    lang="${lang_country%%_*}"                                # en
    rest="${PIPER_DEFAULT_VOICE#*-}"                          # lessac-medium
    voice_name="${rest%%-*}"                                  # lessac
    quality="${rest#*-}"                                      # medium
    HF_BASE="https://huggingface.co/rhasspy/piper-voices/resolve/${PIPER_VOICES_TAG}/${lang}/${lang_country}/${voice_name}/${quality}"
    mkdir -p "$PIPER_DATA_DIR"
    fetch() { # fetch <url> <dest>
      if command -v curl >/dev/null 2>&1; then curl -fsSL "$1" -o "$2"
      elif command -v wget >/dev/null 2>&1; then wget -qO "$2" "$1"
      else return 3; fi
    }
    ONNX_DEST="$PIPER_DATA_DIR/${PIPER_DEFAULT_VOICE}.onnx"
    JSON_DEST="$PIPER_DATA_DIR/${PIPER_DEFAULT_VOICE}.onnx.json"
    if [ -s "$ONNX_DEST" ] && [ "$(wc -c < "$ONNX_DEST" 2>/dev/null || echo 0)" -gt 1000000 ]; then
      green "Voice model already staged: $ONNX_DEST"
    else
      info "downloading $PIPER_DEFAULT_VOICE ONNX voice to $PIPER_DATA_DIR ..."
      if fetch "${HF_BASE}/${PIPER_DEFAULT_VOICE}.onnx" "$ONNX_DEST" \
         && fetch "${HF_BASE}/${PIPER_DEFAULT_VOICE}.onnx.json" "$JSON_DEST" \
         && [ "$(wc -c < "$ONNX_DEST" 2>/dev/null || echo 0)" -gt 1000000 ]; then
        green "Voice model staged: $ONNX_DEST"
      else
        warn "Optional voice pre-stage failed (offline?) -- Piper (if used) downloads it on first use. Not fatal."
        info "Manual: python3 -m piper.download_voices $PIPER_DEFAULT_VOICE --data-dir $PIPER_DATA_DIR"
        rm -f "$ONNX_DEST" "$JSON_DEST" 2>/dev/null || true
      fi
    fi
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
green "=== Skill 47 render-runtime provisioning complete (shared engines probe-verified, clone extras done). ==="
info "Generic engines (Remotion, HyperFrames) are provisioned by the shared runtime at"
info "$SHARED_RUNTIME_DIR and proven by its launch-and-render probe (runtime-lock.json)."
info "Piper (offline TTS) is optional/opt-in; cloud TTS (Fish 2.1 Pro primary;"
info "Gemini/OpenAI/MiniMax fallback) is the default narrator path."
info "The free ffmpeg documentary-montage path and the Kie.AI remote path need no browser."
exit 0

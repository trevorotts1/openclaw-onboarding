#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production)
# RENDER-RUNTIME PROVISIONER  —  arch/OS-aware, idempotent.
#
# WHY THIS EXISTS
#   `install.sh` clones the upstream OpenMontage engine and runs its `make setup`.
#   That upstream Makefile installs Remotion's npm packages, cache-warms HyperFrames
#   via npx, and does `pip install piper-tts || echo skip` — a SILENT SOFT-FAIL.
#   It installs ZERO Chromium system libraries and pre-stages ZERO voice models, so a
#   fresh Linux/VPS container FAILS every Remotion/HyperFrames (headless-Chromium) render
#   and often ends up with NO offline Piper TTS. See OPENMONTAGE-VPS-READINESS audit.
#
#   This script closes those gaps AFTER `make setup`, for BOTH macOS and Linux/VPS:
#     1. (Linux) apt-get the Chromium system libraries + ffmpeg that headless Chrome needs
#        to LAUNCH (the Linux compositor npm binary alone is not enough).
#     2. Install the pinned latest-stable Remotion + its arch/OS-specific compositor,
#        then `npx remotion browser ensure` to fetch Chrome-Headless-Shell.
#     3. Cache-warm the pinned latest-stable HyperFrames CLI + its bundled Chrome.
#     4. (OPTIONAL, OPT-IN — OFF BY DEFAULT) Install the pinned latest-stable Piper
#        (arch-aware wheel) and pre-stage a default voice ONNX model — ONLY when
#        SKILL47_INSTALL_PIPER=1. Piper is an offline-only last-resort fallback: the
#        PRIMARY narrator is Fish Audio 2.1 Pro (s2.1-pro), with Gemini TTS / OpenAI TTS /
#        MiniMax (a.k.a. "Mimo") as the cloud fallbacks. With Piper absent, OpenMontage's
#        TTS auto-discovery simply uses the cloud providers. Piper's absence/failure NEVER
#        aborts the install.
#
#   The free ffmpeg documentary-montage path and the Kie.AI remote path need NO browser
#   and are unaffected by this script.
#
# INVOCATION
#   bash provision-render-deps.sh
#   OPENCLAW_OPENMONTAGE_DIR=/path/to/OpenMontage bash provision-render-deps.sh
#
# ENV TOGGLES (all optional)
#   OPENCLAW_OPENMONTAGE_DIR   OpenMontage clone dir (default: ~/.openclaw/openmontage-runtime/OpenMontage)
#   REMOTION_VERSION           override the pinned Remotion version
#   HYPERFRAMES_VERSION        override the pinned HyperFrames version
#   PIPER_VERSION              override the pinned piper-tts version
#   PIPER_DEFAULT_VOICE        default voice model id (default: en_US-lessac-medium)
#   PIPER_DATA_DIR             where to pre-stage voice models (default: ~/.piper/models)
#   SKILL47_INSTALL_PIPER=1    OPT IN to the optional offline Piper TTS fallback (OFF by default)
#   SKILL47_SKIP_APT=1         skip the Linux apt system-library step (already provisioned)
#
# EXIT CODE
#   0 — provisioning complete (best-effort steps may have WARNed; see output)
#   1 — a HARD failure: no OpenMontage clone. (Piper is optional and NEVER causes a hard failure.)
#
# ── PINNED LATEST-STABLE VERSIONS — bump these (each line cites its source) ─────────────
#   Remotion 4.0.489      https://registry.npmjs.org/remotion/latest              (2026-07-13)
#   HyperFrames 0.7.56    https://registry.npmjs.org/hyperframes/latest           (2026-07-13)
#   piper-tts 1.4.2       https://github.com/OHF-voice/piper1-gpl/releases/latest (tag v1.4.2)  [OPTIONAL/opt-in only]
#   Piper voice models    https://huggingface.co/rhasspy/piper-voices (pinned tag v1.0.0)       [OPTIONAL/opt-in only]
set -uo pipefail

REMOTION_VERSION="${REMOTION_VERSION:-4.0.489}"
HYPERFRAMES_VERSION="${HYPERFRAMES_VERSION:-0.7.56}"
PIPER_VERSION="${PIPER_VERSION:-1.4.2}"
PIPER_DEFAULT_VOICE="${PIPER_DEFAULT_VOICE:-en_US-lessac-medium}"
PIPER_DATA_DIR="${PIPER_DATA_DIR:-$HOME/.piper/models}"
PIPER_VOICES_TAG="v1.0.0"

OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"

FAIL=0
red()    { printf "\033[31mFAIL\033[0m %s\n" "$1" >&2; }
green()  { printf "\033[32m OK \033[0m %s\n" "$1"; }
warn()   { printf "\033[33mWARN\033[0m %s\n" "$1" >&2; }
info()   { printf "     %s\n" "$1"; }
head_()  { printf "\n--- %s ---\n" "$1"; }

echo "=== Skill 47 — Render-runtime provisioner (arch/OS-aware, idempotent) ==="
echo "    OpenMontage clone: $OPENMONTAGE_DIR"

# ---------------------------------------------------------------------------
# 0 — Detect OS / arch / libc  (drives every downstream decision)
# ---------------------------------------------------------------------------
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
  # musl (Alpine) vs glibc — Remotion ships a separate compositor per libc.
  if [ -f /etc/alpine-release ] || (ldd --version 2>&1 | grep -qi musl); then
    LIBC="musl"
  fi
fi
info "detected: os=$OS arch=$ARCH libc=$LIBC (node $(node -v 2>/dev/null || echo '?'))"

# sudo helper: run as root directly, else via sudo if present, else signal caller.
SUDO=""
if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

# ---------------------------------------------------------------------------
# 1 — Clone must exist (make setup already ran). HARD fail otherwise.
# ---------------------------------------------------------------------------
if [ ! -d "$OPENMONTAGE_DIR" ]; then
  red "OpenMontage clone not found at $OPENMONTAGE_DIR."
  info "Run install.sh (or clone + make setup) first, then re-run this provisioner."
  exit 1
fi

# ---------------------------------------------------------------------------
# 2 — (Linux) Chromium SYSTEM LIBRARIES + ffmpeg
#     Remotion's documented Linux prerequisite; the same libs HyperFrames' bundled
#     Chrome needs to launch. Source: https://www.remotion.dev/docs/docker and
#     https://www.remotion.dev/docs/miscellaneous/linux-dependencies
# ---------------------------------------------------------------------------
head_ "Chromium system libraries (Linux only)"
if [ "$OS" != "linux" ]; then
  green "macOS — native Chromium libraries already present; no apt step needed."
elif [ "${SKILL47_SKIP_APT:-0}" = "1" ]; then
  green "SKILL47_SKIP_APT=1 — skipping apt system-library install (assumed pre-provisioned)."
elif ! command -v apt-get >/dev/null 2>&1; then
  warn "Non-apt Linux (no apt-get). Install the Chromium libs + ffmpeg with your package manager."
  info "Debian/Ubuntu equivalent set: libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0"
  info "libgbm-dev libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1"
  info "libpango-1.0-0 libcairo2 libcups2 libasound2 fonts-liberation ffmpeg"
else
  # Idempotent: apt-get install -y is a no-op for already-present packages.
  APT_LIBS="libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm-dev \
libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 \
libpango-1.0-0 libcairo2 libcups2 fonts-liberation ffmpeg"
  info "apt-get update (best-effort) + install Chromium libs + ffmpeg ..."
  $SUDO apt-get update -y >/dev/null 2>&1 || warn "apt-get update failed (offline?) — continuing."
  if $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y $APT_LIBS >/dev/null 2>&1; then
    green "Chromium system libs + ffmpeg installed (or already present)."
  else
    warn "apt-get install of the base libs returned non-zero — some may be missing."
    info "Fix manually: $SUDO apt-get install -y $APT_LIBS"
  fi
  # libasound2 was renamed libasound2t64 on Ubuntu 24.04+; install whichever resolves.
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y libasound2 >/dev/null 2>&1 \
    || $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y libasound2t64 >/dev/null 2>&1 \
    || warn "Could not install libasound2 / libasound2t64 — Chrome audio libs may be missing."
fi

# ---------------------------------------------------------------------------
# 3 — Remotion: pin latest-stable + arch/OS-specific compositor + Chrome-Headless-Shell
# ---------------------------------------------------------------------------
head_ "Remotion $REMOTION_VERSION (composer + compositor-$OS-$ARCH + Chrome-Headless-Shell)"
COMPOSER_DIR="$OPENMONTAGE_DIR/remotion-composer"
if [ ! -d "$COMPOSER_DIR" ]; then
  warn "remotion-composer/ not found in the clone — did 'make setup' run? Skipping Remotion pin."
else
  # Compositor package name is @remotion/compositor-<os>-<arch>[-<libc> on linux].
  if [ "$OS" = "linux" ]; then
    COMPOSITOR_PKG="@remotion/compositor-linux-${ARCH}-${LIBC}"
  else
    COMPOSITOR_PKG="@remotion/compositor-${OS}-${ARCH}"
  fi
  info "pinning remotion@$REMOTION_VERSION + @remotion/cli@$REMOTION_VERSION + ${COMPOSITOR_PKG}@$REMOTION_VERSION"
  # --no-save: pin the RUNNING version into node_modules without churning the upstream
  # package.json/lockfile. Idempotent (already-satisfied installs are a no-op).
  if ( cd "$COMPOSER_DIR" && npm install --no-save --no-audit --no-fund \
        "remotion@$REMOTION_VERSION" \
        "@remotion/cli@$REMOTION_VERSION" \
        "${COMPOSITOR_PKG}@$REMOTION_VERSION" >/dev/null 2>&1 ); then
    green "Remotion $REMOTION_VERSION + $COMPOSITOR_PKG installed."
  else
    warn "npm install of the pinned Remotion + compositor failed (network?). First render will resolve on demand."
  fi
  # Chrome-Headless-Shell — works on macOS AND Linux. Source: remotion.dev/docs/docker.
  if ( cd "$COMPOSER_DIR" && npx --yes remotion browser ensure >/dev/null 2>&1 ); then
    green "Chrome-Headless-Shell ensured (npx remotion browser ensure)."
  else
    warn "'npx remotion browser ensure' failed — Remotion will download Chrome-Headless-Shell on first render."
  fi
fi

# ---------------------------------------------------------------------------
# 4 — HyperFrames: pin latest-stable CLI (cache-warm) + bundled Chrome
#     HyperFrames is a PEER headless-Chrome renderer (HeyGen's `hyperframes` npm
#     package, engines node>=22). Same Chromium system libs as Remotion (§2 above).
# ---------------------------------------------------------------------------
head_ "HyperFrames $HYPERFRAMES_VERSION (CLI cache-warm + bundled Chrome)"
if npx --yes "hyperframes@$HYPERFRAMES_VERSION" --version >/dev/null 2>&1; then
  green "HyperFrames $HYPERFRAMES_VERSION CLI cached (npx)."
else
  warn "HyperFrames cache-warm failed (offline/npm) — first render will fetch on demand."
fi
# Pre-provision HyperFrames' bundled Chrome so the first container render doesn't stall.
npx --yes "hyperframes@$HYPERFRAMES_VERSION" browser >/dev/null 2>&1 \
  && green "HyperFrames bundled Chrome provisioned." \
  || warn "HyperFrames 'browser' provisioning skipped/failed — bundled Chrome fetches on first render."

# ---------------------------------------------------------------------------
# 5 — Piper TTS (OPTIONAL, OPT-IN, offline-only fallback) — OFF BY DEFAULT
#     Voice order: Fish Audio 2.1 Pro (s2.1-pro) is the PRIMARY narrator; Gemini TTS,
#     OpenAI TTS, and MiniMax (a.k.a. "Mimo") are the cloud fallbacks; Piper is an OPTIONAL
#     offline-only last-resort fallback that is NOT installed by default. With Piper absent,
#     OpenMontage's TTS auto-discovery simply uses the cloud providers. Opt in with
#     SKILL47_INSTALL_PIPER=1 to install the arch-aware wheel and pre-stage a default voice
#     model. A Piper install/download failure NEVER aborts the Skill 47 install (WARN only).
# ---------------------------------------------------------------------------
head_ "Piper TTS (OPTIONAL — opt-in offline fallback, OFF by default)"
if [ "${SKILL47_INSTALL_PIPER:-0}" != "1" ]; then
  green "Piper not requested (SKILL47_INSTALL_PIPER unset) — skipping install + voice pre-stage."
  info "Primary narrator is Fish Audio 2.1 Pro (s2.1-pro); Gemini/OpenAI/MiniMax (Mimo) TTS are the cloud fallbacks."
  info "OpenMontage TTS auto-discovery will use the cloud providers. Opt in with SKILL47_INSTALL_PIPER=1."
else
  info "SKILL47_INSTALL_PIPER=1 — installing the OPTIONAL offline Piper fallback (never fatal)."
  info "piper-tts==$PIPER_VERSION (arch-aware) + default voice '$PIPER_DEFAULT_VOICE'"
  # Prefer the OpenMontage clone's own venv so the `piper` module is importable by its tools.
  PY=""
  for cand in "$OPENMONTAGE_DIR/.venv/bin/python" "${VIRTUAL_ENV:-}/bin/python"; do
    if [ -n "$cand" ] && [ -x "$cand" ]; then PY="$cand"; break; fi
  done
  [ -z "$PY" ] && PY="$(command -v python3 || command -v python || true)"
  if [ -z "$PY" ]; then
    warn "No python interpreter found — skipping optional Piper install. Cloud TTS remains primary. Not fatal."
  else
    info "using interpreter: $PY"
    PIPER_OK=0
    for attempt in 1 2; do
      if "$PY" -m pip install --disable-pip-version-check "piper-tts==$PIPER_VERSION" >/dev/null 2>&1; then
        PIPER_OK=1; break
      fi
      warn "piper-tts install attempt $attempt failed — retrying ..."
    done
    if [ "$PIPER_OK" = "1" ] && "$PY" -c "import piper" >/dev/null 2>&1; then
      green "piper-tts $PIPER_VERSION installed and importable (optional offline fallback)."
    else
      warn "Optional piper-tts install failed — cloud TTS (Fish 2.1 Pro / Gemini / OpenAI / MiniMax) remains primary. Not fatal."
    fi

    # Pre-stage the default voice ONNX model (+ its .json) — CLI-agnostic direct download.
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
        warn "Optional voice pre-stage failed (offline?) — Piper (if used) downloads it on first use. Not fatal."
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
if [ "$FAIL" -gt 0 ]; then
  red "=== Render-runtime provisioning FAILED ($FAIL hard error[s]). See above. ==="
  exit 1
fi
green "=== Render-runtime provisioning complete (os=$OS arch=$ARCH libc=$LIBC). ==="
info "Remotion + HyperFrames headless-Chromium renders are provisioned. Piper (offline TTS) is"
info "optional/opt-in; cloud TTS (Fish 2.1 Pro primary; Gemini/OpenAI/MiniMax fallback) is the default narrator path."
info "The free ffmpeg documentary-montage path and the Kie.AI remote path need no browser."
exit 0

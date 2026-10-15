#!/usr/bin/env bash
# Shared motion render runtime -- PROVISIONER (Skill 47 + Skill 72)
#
# WHY THIS EXISTS
#   Skill 47's provision-render-deps.sh and Skill 72 both need the same two
#   headless-Chromium render engines (Remotion + HyperFrames) at the same
#   pinned versions, with the same OS/arch system libraries. Duplicated
#   per-skill provisioning drifts and, worse, the old Skill 47 script
#   reported success when an engine install had actually failed (every
#   failure was WARN-only). This shared provisioner is the single
#   implementation both skills call. Skill 47 keeps its own wrapper for
#   OpenMontage-clone-specific work; Skill 72 invokes this script directly.
#
# WHAT IT DOES
#   1. Detects OS / arch / libc (drives the Remotion compositor choice).
#   2. (Linux) Installs the Chromium system libraries + ffmpeg via apt.
#   3. Installs the pinned engines from the COMMITTED package-lock.json
#      with `npm ci` into a versioned staging directory. It NEVER fetches
#      `latest`, and it has NO OpenMontage-clone requirement.
#   4. Ensures the Remotion Chrome-Headless-Shell browser.
#   5. Runs probe.mjs -- a real launch-and-render readiness probe, not a
#      node_modules presence check -- inside the staging directory.
#   6. Only when the probe passes: atomically promotes the staging
#      directory to .runtime/versions/<id>/ and flips the .runtime/current
#      symlink to it. A failed or interrupted run leaves the previously
#      verified runtime untouched and active.
#
# EXIT CODE (no WARN-only success for mandatory engines)
#   0 -- install (or verified reuse) complete AND the probe passed for
#        every mandatory engine. runtime-lock.json records the proof.
#   1 -- a HARD failure: missing node/npm, unsupported platform, apt is
#        not the gate (the probe is), npm install failure, browser
#        failure, or a failed probe for a mandatory engine. The output
#        names the failed step/engine on a line starting with FAIL.
#
# LAYOUT (all generated state is gitignored; see .gitignore)
#   shared-utils/motion-render-runtime/
#     package.json / package-lock.json   committed pins (the contract)
#     provision.sh / probe.mjs           committed code
#     .runtime/
#       versions/<lock-hash>/            one verified runtime per lockfile
#       current -> versions/<lock-hash>  atomic symlink flip after probe
#       runtime-lock.json                copy of the active probe record
#       staging-*                        transient; removed on failure
#
# ENV TOGGLES (all optional)
#   MOTION_RUNTIME_SKIP_APT=1   skip the Linux apt system-library step
#   SKILL47_SKIP_APT=1          legacy Skill 47 name for the same skip
#   REMOTION_VERSION=x.y.z      DEVELOPMENT override: pin every @remotion/*
#                               package to a different version. Bypasses the
#                               committed lockfile (npm install, not ci)
#                               and lands in its own versions/ directory.
#   HYPERFRAMES_VERSION=x.y.z   DEVELOPMENT override for hyperframes,
#                               same lockfile-bypass semantics.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.runtime"
VERSIONS_DIR="$STATE_DIR/versions"
CURRENT_LINK="$STATE_DIR/current"

red()   { printf "\033[31mFAIL\033[0m %s\n" "$1" >&2; }
green() { printf "\033[32m OK \033[0m %s\n" "$1"; }
warn()  { printf "\033[33mWARN\033[0m %s\n" "$1" >&2; }
info()  { printf "     %s\n" "$1"; }
head_() { printf "\n--- %s ---\n" "$1"; }

fail_out() { red "$1"; exit 1; }

echo "=== Shared motion render runtime -- provisioner ==="
echo "    runtime home: $SCRIPT_DIR"

# ---------------------------------------------------------------------------
# 0 -- Detect OS / arch / libc + toolchain presence
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
  if [ -f /etc/alpine-release ] || (ldd --version 2>&1 | grep -qi musl); then
    LIBC="musl"
  fi
fi
[ "$OS" = "unknown" ] && fail_out "Unsupported OS: $UNAME_S (expected Darwin or Linux)."

command -v node >/dev/null 2>&1 || fail_out "node is not installed. The motion render runtime requires Node >= 22."
command -v npm  >/dev/null 2>&1 || fail_out "npm is not installed. The motion render runtime requires Node >= 22."
NODE_MAJOR="$(node -p 'Number(process.versions.node.split(".")[0])' 2>/dev/null || echo 0)"
[ "${NODE_MAJOR:-0}" -ge 22 ] || fail_out "Node >= 22 is required (found $(node -v 2>/dev/null || echo unknown))."
info "detected: os=$OS arch=$ARCH libc=$LIBC (node $(node -v), npm $(npm -v))"

# sudo helper: run as root directly, else via sudo if present, else empty.
SUDO=""
if [ "$(id -u 2>/dev/null || echo 1)" != "0" ]; then
  if command -v sudo >/dev/null 2>&1; then SUDO="sudo"; fi
fi

# ---------------------------------------------------------------------------
# 1 -- (Linux) Chromium SYSTEM LIBRARIES + ffmpeg
#     Same set the Skill 47 provisioner installed; Remotion's documented
#     Linux prerequisite, and what HyperFrames' bundled Chrome needs.
#     A failure here WARNS: the probe's real browser launch is the hard
#     gate, so missing libs surface as a probe FAIL, never a silent pass.
# ---------------------------------------------------------------------------
head_ "Chromium system libraries (Linux only)"
if [ "$OS" != "linux" ]; then
  green "macOS -- native Chromium libraries already present; no apt step needed."
elif [ "${MOTION_RUNTIME_SKIP_APT:-0}" = "1" ] || [ "${SKILL47_SKIP_APT:-0}" = "1" ]; then
  green "apt step skipped (MOTION_RUNTIME_SKIP_APT / SKILL47_SKIP_APT) -- assumed pre-provisioned."
elif ! command -v apt-get >/dev/null 2>&1; then
  warn "Non-apt Linux (no apt-get). Install the Chromium libs + ffmpeg with your package manager."
  info "Debian/Ubuntu equivalent set: libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0"
  info "libgbm-dev libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1"
  info "libpango-1.0-0 libcairo2 libcups2 libasound2 fonts-liberation ffmpeg"
else
  APT_LIBS="libnss3 libdbus-1-3 libatk1.0-0 libatk-bridge2.0-0 libgbm-dev \
libxrandr2 libxkbcommon-dev libxfixes3 libxcomposite1 libxdamage1 \
libpango-1.0-0 libcairo2 libcups2 fonts-liberation ffmpeg"
  info "apt-get update (best-effort) + install Chromium libs + ffmpeg ..."
  $SUDO apt-get update -y >/dev/null 2>&1 || warn "apt-get update failed (offline?) -- continuing."
  if $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y $APT_LIBS >/dev/null 2>&1; then
    green "Chromium system libs + ffmpeg installed (or already present)."
  else
    warn "apt-get install of the base libs returned non-zero -- some may be missing."
    info "Fix manually: $SUDO apt-get install -y $APT_LIBS"
  fi
  # libasound2 was renamed libasound2t64 on Ubuntu 24.04+; install whichever resolves.
  $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y libasound2 >/dev/null 2>&1 \
    || $SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y libasound2t64 >/dev/null 2>&1 \
    || warn "Could not install libasound2 / libasound2t64 -- Chrome audio libs may be missing."
fi

# ---------------------------------------------------------------------------
# 2 -- Install plan: locked (default) or development override
# ---------------------------------------------------------------------------
head_ "Engine install plan"
PIN_REMOTION="$(node -p "require('$SCRIPT_DIR/package.json').dependencies['remotion']" 2>/dev/null || echo '')"
PIN_HYPERFRAMES="$(node -p "require('$SCRIPT_DIR/package.json').dependencies['hyperframes']" 2>/dev/null || echo '')"
[ -n "$PIN_REMOTION" ] && [ -n "$PIN_HYPERFRAMES" ] || fail_out "Could not read pins from $SCRIPT_DIR/package.json."

OVERRIDE=0
if [ -n "${REMOTION_VERSION:-}" ] && [ "$REMOTION_VERSION" != "$PIN_REMOTION" ]; then OVERRIDE=1; fi
if [ -n "${HYPERFRAMES_VERSION:-}" ] && [ "$HYPERFRAMES_VERSION" != "$PIN_HYPERFRAMES" ]; then OVERRIDE=1; fi
EFF_REMOTION="${REMOTION_VERSION:-$PIN_REMOTION}"
EFF_HYPERFRAMES="${HYPERFRAMES_VERSION:-$PIN_HYPERFRAMES}"

if [ "$OVERRIDE" = "1" ]; then
  PLAN_ID="override-$(printf '%s' "remotion=$EFF_REMOTION hyperframes=$EFF_HYPERFRAMES" | (sha256sum 2>/dev/null || shasum -a 256) | cut -c1-16)"
  info "DEVELOPMENT OVERRIDE active (remotion=$EFF_REMOTION hyperframes=$EFF_HYPERFRAMES). The committed lockfile is bypassed for this run only."
else
  LOCK_HASH="$( (sha256sum "$SCRIPT_DIR/package-lock.json" 2>/dev/null || shasum -a 256 "$SCRIPT_DIR/package-lock.json") | cut -c1-16 )"
  PLAN_ID="lock-$LOCK_HASH"
  info "locked install from committed package-lock.json (plan $PLAN_ID): remotion=$PIN_REMOTION hyperframes=$PIN_HYPERFRAMES"
fi
TARGET_DIR="$VERSIONS_DIR/$PLAN_ID"
mkdir -p "$VERSIONS_DIR"

run_probe() { # run_probe <install-dir>
  MOTION_RUNTIME_LOCK_OUT="$1/runtime-lock.json" node "$1/probe.mjs"
}

promote() { # promote <staging-dir>
  local staging="$1"
  rm -rf "$TARGET_DIR.tmp-promote"
  mv "$staging" "$TARGET_DIR.tmp-promote"
  rm -rf "$TARGET_DIR"
  mv "$TARGET_DIR.tmp-promote" "$TARGET_DIR"
  # Atomic symlink flip: build the new link beside the old, then rename over.
  ln -s "versions/$PLAN_ID" "$STATE_DIR/current.tmp.$$"
  mv -Tf "$STATE_DIR/current.tmp.$$" "$CURRENT_LINK" 2>/dev/null || { rm -f "$CURRENT_LINK"; ln -s "versions/$PLAN_ID" "$CURRENT_LINK"; }
  cp "$TARGET_DIR/runtime-lock.json" "$STATE_DIR/runtime-lock.json"
}

# ---------------------------------------------------------------------------
# 3 -- Fast path: the active runtime already matches this plan and its
#      recorded probe passed. Re-run the probe to prove it still launches
#      and renders TODAY (a stale lock is not readiness), then exit 0.
# ---------------------------------------------------------------------------
CURRENT_TARGET=""
if [ -L "$CURRENT_LINK" ]; then
  CURRENT_TARGET="$(cd "$STATE_DIR" && readlink current || true)"
fi
if [ "$CURRENT_TARGET" = "versions/$PLAN_ID" ] && [ -f "$TARGET_DIR/runtime-lock.json" ]; then
  head_ "Existing verified runtime for this plan -- re-running probe"
  if run_probe "$TARGET_DIR"; then
    cp "$TARGET_DIR/runtime-lock.json" "$STATE_DIR/runtime-lock.json"
    green "=== Shared motion render runtime READY (plan $PLAN_ID, probe passed, no reinstall needed). ==="
    exit 0
  fi
  warn "The active runtime for plan $PLAN_ID failed its probe -- reinstalling into staging."
fi

# ---------------------------------------------------------------------------
# 4 -- Staged install. The previously verified runtime stays active until
#      the new one passes its probe (atomic switch in step 5).
# ---------------------------------------------------------------------------
head_ "Installing engines into staging (previous verified runtime stays active)"
STAGING="$STATE_DIR/staging-$PLAN_ID-$$"
rm -rf "$STAGING"
mkdir -p "$STAGING"
cp "$SCRIPT_DIR/probe.mjs" "$STAGING/probe.mjs"
if [ "$OVERRIDE" = "1" ]; then
  node -e '
    const fs = require("fs");
    const [src, dst, remotionV, hyperframesV] = process.argv.slice(1);
    const pkg = JSON.parse(fs.readFileSync(src, "utf8"));
    for (const k of Object.keys(pkg.dependencies)) {
      if (k === "remotion" || k.startsWith("@remotion/")) pkg.dependencies[k] = remotionV;
      if (k === "hyperframes") pkg.dependencies[k] = hyperframesV;
    }
    fs.writeFileSync(dst, JSON.stringify(pkg, null, 2) + "\n");
  ' "$SCRIPT_DIR/package.json" "$STAGING/package.json" "$EFF_REMOTION" "$EFF_HYPERFRAMES" \
    || fail_out "Failed to build the override package.json."
  if ! ( cd "$STAGING" && npm install --no-audit --no-fund ); then
    rm -rf "$STAGING"
    fail_out "npm install failed for the override plan (remotion=$EFF_REMOTION hyperframes=$EFF_HYPERFRAMES). Previous verified runtime (if any) is untouched."
  fi
else
  cp "$SCRIPT_DIR/package.json" "$STAGING/package.json"
  cp "$SCRIPT_DIR/package-lock.json" "$STAGING/package-lock.json"
  if ! ( cd "$STAGING" && npm ci --no-audit --no-fund ); then
    rm -rf "$STAGING"
    fail_out "npm ci failed for the locked plan $PLAN_ID. Previous verified runtime (if any) is untouched."
  fi
fi
green "Engines installed into staging."

head_ "Remotion browser (Chrome-Headless-Shell) ensure"
if ! ( cd "$STAGING" && ./node_modules/.bin/remotion browser ensure ); then
  rm -rf "$STAGING"
  fail_out "Remotion browser ensure failed. Previous verified runtime (if any) is untouched."
fi
green "Chrome-Headless-Shell ensured."

# HyperFrames ships a bundled Chrome; warm it now so the probe (and the
# first real render) do not stall on a download. If this CLI version has
# no browser subcommand, the probe's doctor check is the gate.
if ( cd "$STAGING" && ./node_modules/.bin/hyperframes --help 2>/dev/null | grep -qw browser ); then
  ( cd "$STAGING" && ./node_modules/.bin/hyperframes browser ensure >/dev/null 2>&1 ) \
    && green "HyperFrames bundled Chrome provisioned." \
    || warn "HyperFrames 'browser ensure' warm-up failed -- the probe's doctor check decides readiness."
fi

# ---------------------------------------------------------------------------
# 5 -- Probe, then promote atomically. A probe failure is a hard failure:
#      staging is discarded and the previous runtime stays active.
# ---------------------------------------------------------------------------
head_ "Readiness probe (launch + render, not a presence check)"
if ! run_probe "$STAGING"; then
  rm -rf "$STAGING"
  fail_out "Readiness probe FAILED for plan $PLAN_ID (see probe output above). The staging install was discarded; the previous verified runtime (if any) is untouched and still active."
fi
promote "$STAGING"
green "=== Shared motion render runtime READY (plan $PLAN_ID promoted to .runtime/current, probe passed). ==="
info "Active runtime: $CURRENT_LINK -> versions/$PLAN_ID"
info "Proof record:   $STATE_DIR/runtime-lock.json"
exit 0

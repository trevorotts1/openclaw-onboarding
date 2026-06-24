#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production) — FAIL-LOUD runtime-dependency preflight
#
# Mirrors the pattern from:
#   .github/workflows/presentation-deps-gate.yml
#   install.sh Step 6.5 (soffice/poppler fail-loud)
#   qc-completeness.sh hard-fail
#
# EXIT CODES:
#   0 — all required binaries present; safe to proceed
#   1 — one or more required binaries missing; precise fix printed
#
# NEVER continue silently on a missing dep — the soffice/poppler lesson.
set -euo pipefail

FAIL=0

red()   { printf "\033[31m%s\033[0m\n" "$1" >&2; }
green() { printf "\033[32m%s\033[0m\n" "$1"; }
info()  { printf "%s\n" "$1"; }

info ""
info "=== Skill 47 -- Movie Producer (Automated Video Production) -- Runtime-Dep Preflight ==="
info ""

# ---- Helper ----
check_binary() {
  local name="$1" fix_mac="$2" fix_linux="$3"
  if command -v "$name" >/dev/null 2>&1; then
    green "  [PASS] $name found: $(command -v "$name")"
  else
    red   "  [FAIL] $name NOT FOUND"
    red   "         macOS fix:  $fix_mac"
    red   "         Linux fix:  $fix_linux"
    FAIL=$((FAIL+1))
  fi
}

# ---- FFmpeg (required for all compose/stitch paths) ----
check_binary "ffmpeg" \
  "brew install ffmpeg" \
  "sudo apt-get update && sudo apt-get install -y ffmpeg"

# ---- ffprobe (ships with ffmpeg — same install) ----
check_binary "ffprobe" \
  "brew install ffmpeg  # ffprobe ships with ffmpeg" \
  "sudo apt-get install -y ffmpeg  # ffprobe ships with ffmpeg"

# ---- Node.js >= 18 (required for Remotion + npx hyperframes) ----
check_binary "node" \
  "brew install node" \
  "curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"

if command -v node >/dev/null 2>&1; then
  NODE_MAJOR=$(node -e "process.stdout.write(process.versions.node.split('.')[0])" 2>/dev/null || echo "0")
  if [ "$NODE_MAJOR" -ge 18 ] 2>/dev/null; then
    green "  [PASS] node version $NODE_MAJOR >= 18"
  else
    red   "  [FAIL] node version $NODE_MAJOR is < 18 (required >= 18)"
    red   "         macOS fix:  brew upgrade node"
    red   "         Linux fix:  curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash - && sudo apt-get install -y nodejs"
    FAIL=$((FAIL+1))
  fi
fi

# ---- npx (ships with Node.js) ----
check_binary "npx" \
  "brew install node  # npx ships with node" \
  "sudo apt-get install -y nodejs  # npx ships with nodejs"

# ---- git (required for cloning OpenMontage) ----
check_binary "git" \
  "xcode-select --install" \
  "sudo apt-get install -y git"

# ---- python3 (required for make setup + tool registry) ----
check_binary "python3" \
  "brew install python3" \
  "sudo apt-get install -y python3 python3-pip"

# ---- npx hyperframes (probe — not installed yet, but npx must be able to resolve) ----
info ""
info "  Probing HyperFrames (npx --yes hyperframes --version)..."
if npx --yes hyperframes --version >/dev/null 2>&1; then
  green "  [PASS] npx hyperframes resolves"
else
  # Non-blocking on the preflight (it fetches from npm; network may be offline in CI)
  printf "\033[33m  [WARN] npx hyperframes probe failed -- may be a network issue; will retry during make setup\033[0m\n"
fi

# ---- Piper TTS (soft-fail: cloud TTS fallback if missing; make setup handles it) ----
info ""
info "  Checking piper-tts (soft-fail: TTS falls back to cloud if missing)..."
if python3 -c "import piper" >/dev/null 2>&1; then
  green "  [PASS] piper-tts importable"
else
  printf "\033[33m  [WARN] piper-tts not importable -- TTS will use cloud providers instead (install via: pip install piper-tts)\033[0m\n"
fi

# ---- Summary ----
info ""
if [ "$FAIL" -gt 0 ]; then
  red "=== PREFLIGHT FAILED: $FAIL required binary/check(s) missing ==="
  red "    Fix the items above, then re-run: bash preflight.sh"
  exit 1
else
  green "=== [PASS] All required binaries present. Preflight OK. ==="
  exit 0
fi

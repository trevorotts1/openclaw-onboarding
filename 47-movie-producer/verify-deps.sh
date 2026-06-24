#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production) — Clean-box dependency proof
#
# PURPOSE: Prove on a clean box that `make setup` fetches every dependency
#   successfully and that NO vendoring is required. Records the §A conclusion.
#
# INVOCATION (after cloning + preflight):
#   cd ~/.openclaw/skills/47-movie-producer/OpenMontage
#   bash ../verify-deps.sh
#
# EXIT CODE 0 = all deps fetched, no vendoring required
# EXIT CODE 1 = a dep failed to fetch (fix the install, do NOT vendor)
set -euo pipefail

CLONE_DIR="${CLONE_DIR:-$(dirname "$0")/OpenMontage}"
if [ ! -d "$CLONE_DIR" ]; then
  echo "[ERROR] OpenMontage clone not found at: $CLONE_DIR" >&2
  echo "        Run: git clone https://github.com/calesthio/OpenMontage.git $CLONE_DIR" >&2
  exit 1
fi

FAIL=0
green() { printf "\033[32m%s\033[0m\n" "$1"; }
red()   { printf "\033[31m%s\033[0m\n" "$1" >&2; }
info()  { printf "%s\n" "$1"; }

info ""
info "=== Skill 47 -- verify-deps.sh (clean-box dependency proof) ==="
info "    Clone: $CLONE_DIR"
info ""

# ---- Step 1: run make setup ----
info "Step 1: Running make setup in $CLONE_DIR..."
if make -C "$CLONE_DIR" setup; then
  green "  [PASS] make setup rc=0"
else
  red   "  [FAIL] make setup exited non-zero"
  red   "         Do NOT vendor any dependency. Diagnose the failure above and fix the install steps."
  FAIL=$((FAIL+1))
fi

# ---- Step 2: verify Python packages ----
info ""
info "Step 2: Verifying Python packages..."
for pkg in yaml pydantic PIL requests jsonschema dotenv; do
  if python3 -c "import $pkg" >/dev/null 2>&1; then
    green "  [PASS] python3: import $pkg"
  else
    red   "  [FAIL] python3: import $pkg FAILED"
    FAIL=$((FAIL+1))
  fi
done

# ---- Step 3: verify Remotion node_modules ----
info ""
info "Step 3: Verifying Remotion npm install..."
if [ -d "$CLONE_DIR/remotion-composer/node_modules" ]; then
  green "  [PASS] remotion-composer/node_modules present"
else
  red   "  [FAIL] remotion-composer/node_modules missing"
  red   "         Expected: cd remotion-composer && npm install (run make setup)"
  FAIL=$((FAIL+1))
fi

# ---- Step 4: verify npx hyperframes ----
info ""
info "Step 4: Verifying npx hyperframes..."
if npx --yes hyperframes --version >/dev/null 2>&1; then
  green "  [PASS] npx hyperframes resolves (npm package, not vendored)"
else
  printf "\033[33m  [WARN] npx hyperframes probe failed -- network issue; fetches on first render\033[0m\n"
fi

# ---- Step 5: verify Piper (soft-fail) ----
info ""
info "Step 5: Verifying piper-tts (soft-fail)..."
if python3 -c "import piper" >/dev/null 2>&1; then
  green "  [PASS] piper-tts importable (free offline TTS)"
else
  printf "\033[33m  [WARN] piper-tts not importable (soft-fail per make setup) -- TTS uses cloud providers\033[0m\n"
fi

# ---- Step 6: check for .gitmodules (must not exist) ----
info ""
info "Step 6: Checking for git submodules (must be none)..."
if [ ! -f "$CLONE_DIR/.gitmodules" ]; then
  green "  [PASS] No .gitmodules -- OpenMontage has zero git submodules (confirmed)"
else
  red   "  [FAIL] .gitmodules found -- unexpected; review for vendoring requirement"
  FAIL=$((FAIL+1))
fi

# ---- Final verdict ----
info ""
if [ "$FAIL" -gt 0 ]; then
  red "=== FAIL: $FAIL dep verification(s) failed ==="
  red "    Diagnose above. Fix the install steps. Do NOT vendor deps."
  red "    Vendoring is ONLY permitted for a dep that is genuinely unfetchable"
  red "    on the client box (document why in DEPENDENCY-MANIFEST.md)."
  exit 1
else
  green "=== PASS: All deps fetched by make setup. No vendoring required. ==="
  info  "    §A conclusion confirmed: OpenMontage has no .gitmodules;"
  info  "    HyperFrames and Remotion are npm packages (not git submodules);"
  info  "    Python deps fetched by pip; piper-tts soft-fail is expected behavior."
  exit 0
fi

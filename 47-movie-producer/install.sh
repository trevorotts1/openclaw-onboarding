#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production) — Automated Installer
# Mirrors the fail-loud pattern from presentation-deps-gate.yml + install.sh Step 6.5.
# Run via: bash install.sh
# Must be executed from the skill directory or with SKILL_DIR set.
# NOTE: "OpenMontage" below refers to the UPSTREAM engine (github.com/calesthio/OpenMontage,
# AGPLv3) that this Movie Producer skill clones onto the client box — not the skill dir name.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/skills/47-movie-producer/OpenMontage}"
SKILL_NAME="movie-producer"

red()    { printf "\033[31mFAIL\033[0m %s\n" "$1"; }
green()  { printf "\033[32mPASS\033[0m %s\n" "$1"; }
yellow() { printf "\033[33mWARN\033[0m %s\n" "$1"; }
info()   { printf "     %s\n" "$1"; }

echo "=== Skill 47 / Movie Producer (Automated Video Production) — Install ==="
echo "    Skill dir:        $SKILL_DIR"
echo "    Clone target:     $OPENMONTAGE_DIR"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — Fail-loud runtime dependency preflight
# ---------------------------------------------------------------------------
echo "--- Step 1: Runtime dependency preflight ---"
bash "$SKILL_DIR/preflight.sh" || {
  echo ""
  red "Preflight FAILED. Fix the missing dependencies listed above, then re-run install.sh."
  exit 1
}
echo ""

# ---------------------------------------------------------------------------
# Step 2 — Clone OpenMontage onto the client box
# ---------------------------------------------------------------------------
echo "--- Step 2: Clone OpenMontage ---"
if [ -d "$OPENMONTAGE_DIR/.git" ]; then
  yellow "OpenMontage already cloned at $OPENMONTAGE_DIR — pulling latest."
  git -C "$OPENMONTAGE_DIR" pull --ff-only
else
  git clone https://github.com/calesthio/OpenMontage.git "$OPENMONTAGE_DIR"
fi

ACTUAL_REMOTE="$(git -C "$OPENMONTAGE_DIR" remote get-url origin)"
EXPECTED_REMOTE="https://github.com/calesthio/OpenMontage.git"
if [ "$ACTUAL_REMOTE" != "$EXPECTED_REMOTE" ]; then
  red "Remote mismatch: expected '$EXPECTED_REMOTE', got '$ACTUAL_REMOTE'"
  exit 1
fi
green "OpenMontage cloned — remote verified: $ACTUAL_REMOTE"
echo ""

# ---------------------------------------------------------------------------
# Step 3 — make setup (pip + remotion npm + npx hyperframes + piper)
# ---------------------------------------------------------------------------
echo "--- Step 3: make setup (fetches all dependencies) ---"
info "This installs: Python packages, Remotion npm, HyperFrames via npx, Piper TTS (soft-fail)."
info "AGPLv3 note: all deps fetched at runtime — NO OpenMontage source vendored into this template."
( cd "$OPENMONTAGE_DIR" && make setup ) || {
  red "make setup failed. Check error output above. Do NOT vendor — fix the dep and re-run."
  exit 1
}
green "make setup complete — no vendoring required."
echo ""

# ---------------------------------------------------------------------------
# Step 4 — Drop Kie adapters into the clone
# ---------------------------------------------------------------------------
echo "--- Step 4: Install Kie.AI adapters ---"
cp "$SKILL_DIR/kie-adapters/tools/graphics/kie_image.py" \
   "$OPENMONTAGE_DIR/tools/graphics/kie_image.py"
cp "$SKILL_DIR/kie-adapters/tools/video/kie_video.py" \
   "$OPENMONTAGE_DIR/tools/video/kie_video.py"

python3 -c "import ast; ast.parse(open('$OPENMONTAGE_DIR/tools/graphics/kie_image.py').read())" \
  && green "kie_image.py syntax OK" \
  || { red "kie_image.py syntax error — reinstall the skill bundle."; exit 1; }

python3 -c "import ast; ast.parse(open('$OPENMONTAGE_DIR/tools/video/kie_video.py').read())" \
  && green "kie_video.py syntax OK" \
  || { red "kie_video.py syntax error — reinstall the skill bundle."; exit 1; }
echo ""

# ---------------------------------------------------------------------------
# Step 5 — Write the client .env (Kie key ONLY)
# ---------------------------------------------------------------------------
echo "--- Step 5: Write client .env ---"
ENV_FILE="$OPENMONTAGE_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" << 'ENVEOF'
# Kie.AI API key — CLIENT'S OWN KEY ONLY.
# Obtain a key at https://kie.ai
# All image/video generation routes through Kie.AI when this is set.
# Leave blank (or remove) to run the free documentary-montage path only.
KIE_API_KEY=YOUR_CLIENT_KIE_API_KEY_HERE
#
# DO NOT add FAL_KEY, RUNWAY_API_KEY, HEYGEN_API_KEY, OPENAI_API_KEY,
# GOOGLE_API_KEY, or REPLICATE_API_KEY here.
# Those providers must remain UNAVAILABLE on the client box so all
# generative asset production routes exclusively through Kie.AI.
# OPERATOR KEY RULE: The operator's own KIE_API_KEY MUST NEVER appear here.
ENVEOF
  yellow ".env created — replace YOUR_CLIENT_KIE_API_KEY_HERE with the client's actual Kie.AI key."
else
  yellow ".env already exists at $ENV_FILE — not overwritten. Verify KIE_API_KEY is set."
fi
echo ""

# ---------------------------------------------------------------------------
# Step 6 — Set a low budget cap in config.yaml
# ---------------------------------------------------------------------------
echo "--- Step 6: Budget cap configuration ---"
CONFIG_FILE="$OPENMONTAGE_DIR/config.yaml"
if [ -f "$CONFIG_FILE" ]; then
  # Check whether budget.mode is already cap
  if grep -q "mode: cap" "$CONFIG_FILE" 2>/dev/null; then
    green "config.yaml already has budget.mode: cap"
  else
    yellow "config.yaml found but budget.mode is not 'cap'. Manually set:"
    info "  budget:"
    info "    mode: cap"
    info "    total_usd: 5.00"
    info "    single_action_approval_usd: 0.50"
    info "    require_approval_for_new_paid_tool: true"
    info "  checkpoint:"
    info "    policy: guided"
  fi
else
  yellow "config.yaml not found — make setup may not have generated it. Check the OpenMontage clone."
fi
echo ""

# ---------------------------------------------------------------------------
# Step 7 — Verify provider routing (fail-loud if native providers available)
# ---------------------------------------------------------------------------
echo "--- Step 7: Provider routing verification ---"
( cd "$OPENMONTAGE_DIR" && make preflight 2>/dev/null ) || {
  yellow "make preflight returned non-zero or is not available — verify provider routing manually:"
  info "  cd $OPENMONTAGE_DIR"
  info "  python3 -c \"from tools.tool_registry import get_registry; r=get_registry(); [print(c, [(t.provider, str(t.get_status())) for t in r.get_by_capability(c)]) for c in ['image_generation','video_generation']]\""
}
echo ""

# ---------------------------------------------------------------------------
# Step 8 — Run QC
# ---------------------------------------------------------------------------
echo "--- Step 8: Install QC ---"
bash "$SKILL_DIR/qc-movie-producer.sh" || {
  red "QC failed. Review output above."
  exit 1
}
echo ""

echo "=== Skill 47 / Movie Producer (Automated Video Production) — INSTALL COMPLETE ==="
echo ""
echo "Next steps:"
echo "  1. Edit $ENV_FILE — replace YOUR_CLIENT_KIE_API_KEY_HERE with the client's Kie.AI key."
echo "  2. Verify the budget cap in $CONFIG_FILE"
echo "  3. Test the free path: cd $OPENMONTAGE_DIR && make demo"
echo "  4. See INSTRUCTIONS.md and EXAMPLES.md for pipeline execution."

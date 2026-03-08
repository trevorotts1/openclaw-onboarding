#!/bin/bash
# OpenClaw Onboarding - Master Install Script
# One command installs everything, step by step.
# Usage: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash

set -e

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding"
RAW_URL="https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main"
SKILLS_DIR="$HOME/.openclaw/skills"
ENV_FILE="$HOME/clawd/secrets/.env"
TEMP_DIR=$(mktemp -d)
SUMMARY_INSTALLED=()
SUMMARY_NEEDS_KEY=()
SUMMARY_SKIPPED=()

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

print_step() { echo -e "\n${BLUE}==>${NC} $1"; }
print_ok()   { echo -e "${GREEN}✅${NC} $1"; }
print_warn() { echo -e "${YELLOW}⚠️${NC}  $1"; }
print_fail() { echo -e "${RED}❌${NC} $1"; }

echo ""
echo "╔════════════════════════════════════════════╗"
echo "║   OpenClaw Onboarding - Master Installer   ║"
echo "╚════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────
# STEP 1: Check OpenClaw is installed
# ─────────────────────────────────────────────
print_step "Checking OpenClaw..."
if ! command -v openclaw &>/dev/null; then
  print_fail "OpenClaw is not installed. Install it first: https://docs.openclaw.ai"
  exit 1
fi
print_ok "OpenClaw found"

# ─────────────────────────────────────────────
# STEP 2: Download the repo
# ─────────────────────────────────────────────
print_step "Downloading OpenClaw Onboarding from GitHub..."
curl -s -L "$REPO_URL/archive/refs/heads/main.zip" -o "$TEMP_DIR/onboarding.zip"
unzip -q "$TEMP_DIR/onboarding.zip" -d "$TEMP_DIR"
EXTRACTED="$TEMP_DIR/openclaw-onboarding-main"
print_ok "Downloaded and extracted"

# ─────────────────────────────────────────────
# STEP 3: Copy all skills to ~/.openclaw/skills/
# ─────────────────────────────────────────────
print_step "Installing skill folders..."
mkdir -p "$SKILLS_DIR"
for skill_dir in "$EXTRACTED"/[0-9]*; do
  skill_name=$(basename "$skill_dir")
  cp -r "$skill_dir" "$SKILLS_DIR/"
  echo "  Installed: $skill_name"
done

# Copy update scripts
mkdir -p "$SKILLS_DIR/scripts"
cp "$EXTRACTED/scripts/"* "$SKILLS_DIR/scripts/" 2>/dev/null || true
chmod +x "$SKILLS_DIR/scripts/"*.sh 2>/dev/null || true
print_ok "All skills installed to $SKILLS_DIR"

# ─────────────────────────────────────────────
# STEP 4: Check and install dependencies
# ─────────────────────────────────────────────
print_step "Checking dependencies..."

# Python3
if command -v python3 &>/dev/null; then
  print_ok "Python3 found"
else
  print_warn "Python3 not found - some skills may not work"
fi

# QMD
if command -v qmd &>/dev/null; then
  print_ok "QMD found ($(qmd --version 2>/dev/null | head -1))"
else
  print_warn "QMD not installed. Installing now..."
  if command -v bun &>/dev/null; then
    bun install -g https://github.com/tobi/qmd 2>/dev/null && print_ok "QMD installed" || print_fail "QMD install failed - install manually"
  else
    print_warn "Installing bun first..."
    curl -fsSL https://bun.sh/install | bash 2>/dev/null
    export PATH="$HOME/.bun/bin:$PATH"
    bun install -g https://github.com/tobi/qmd 2>/dev/null && print_ok "QMD installed" || print_fail "QMD install failed"
  fi
fi

# Python packages
for pkg in pdfplumber ebooklib html2text; do
  python3 -c "import $pkg" 2>/dev/null && print_ok "$pkg found" || {
    print_warn "Installing $pkg..."
    pip3 install $pkg --break-system-packages -q 2>/dev/null && print_ok "$pkg installed" || print_warn "$pkg install failed"
  }
done

# Calibre
if command -v ebook-convert &>/dev/null; then
  print_ok "Calibre found"
else
  print_warn "Calibre not found - MOBI/AZW3 books won't work without it"
  print_warn "Install with: brew install --cask calibre"
fi

# ─────────────────────────────────────────────
# STEP 5: API Keys
# ─────────────────────────────────────────────
print_step "Checking API keys..."

check_or_ask_key() {
  local key_name="$1"
  local description="$2"
  local existing=""

  if [ -f "$ENV_FILE" ]; then
    existing=$(grep "^${key_name}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2-)
  fi

  if [ -n "$existing" ] && [ "$existing" != '""' ]; then
    print_ok "$key_name found"
    return 0
  fi

  echo ""
  print_warn "$key_name not found ($description)"
  read -p "  Enter $key_name (or press Enter to skip): " user_key
  if [ -n "$user_key" ]; then
    mkdir -p "$(dirname "$ENV_FILE")"
    echo "${key_name}=${user_key}" >> "$ENV_FILE"
    print_ok "$key_name saved"
    return 0
  else
    print_warn "$key_name skipped - add it later to $ENV_FILE"
    return 1
  fi
}

check_or_ask_key "MOONSHOT_API_KEY"    "Required for book-to-persona Phase 1 (Kimi)" && SUMMARY_INSTALLED+=("Moonshot API") || SUMMARY_NEEDS_KEY+=("MOONSHOT_API_KEY")
check_or_ask_key "OPENROUTER_API_KEY"  "Required for book-to-persona Phase 2 (DeepSeek) and fallbacks" && true || SUMMARY_NEEDS_KEY+=("OPENROUTER_API_KEY")
check_or_ask_key "OPENAI_API_KEY"      "Required for book-to-persona Phase 3 (Codex)" && true || SUMMARY_NEEDS_KEY+=("OPENAI_API_KEY")
check_or_ask_key "GITHUB_TOKEN"        "Required to push new personas to GitHub repo" && true || SUMMARY_NEEDS_KEY+=("GITHUB_TOKEN")

# ─────────────────────────────────────────────
# STEP 6: Set up QMD collections
# ─────────────────────────────────────────────
print_step "Setting up QMD collections..."

PERSONAS_DIR="$SKILLS_DIR/21-book-to-persona/personas"
if [ -d "$PERSONAS_DIR" ] && command -v qmd &>/dev/null; then
  if qmd status 2>/dev/null | grep -q "coaching-personas"; then
    print_ok "QMD coaching-personas collection already exists"
  else
    print_warn "Adding coaching-personas to QMD..."
    qmd collection add "$PERSONAS_DIR" --name coaching-personas --mask "**/*.md" 2>/dev/null
    qmd update 2>/dev/null
    print_ok "coaching-personas indexed. Running embed (this takes 3-8 minutes)..."
    qmd embed 2>/dev/null &
    QMD_PID=$!
    print_ok "QMD embed running in background (pid $QMD_PID)"
    SUMMARY_INSTALLED+=("QMD coaching-personas collection")
  fi
fi

# ─────────────────────────────────────────────
# STEP 7: Set up weekly update cron
# ─────────────────────────────────────────────
print_step "Setting up weekly Sunday 2 AM skill update cron..."
if crontab -l 2>/dev/null | grep -q "update-skills.sh"; then
  print_ok "Weekly update cron already installed"
else
  CRON_JOB="0 2 * * 0 $SKILLS_DIR/scripts/update-skills.sh >> $HOME/.openclaw/skills/.update-log 2>&1"
  (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
  print_ok "Weekly update cron installed (Sundays at 2:00 AM)"
  SUMMARY_INSTALLED+=("Weekly auto-update cron")
fi

# Save installed version
REMOTE_VERSION=$(grep -m1 "^## \[v" "$EXTRACTED/CHANGELOG.md" | sed 's/## \[\(v[0-9.]*\)\].*/\1/')
echo "$REMOTE_VERSION" > "$SKILLS_DIR/.onboarding-version"

# ─────────────────────────────────────────────
# Clean up
# ─────────────────────────────────────────────
rm -rf "$TEMP_DIR"

# ─────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════╗"
echo "║              Install Complete              ║"
echo "╚════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}Version installed: $REMOTE_VERSION${NC}"
echo ""
echo -e "${GREEN}Skills folder: $SKILLS_DIR${NC}"
echo ""

if [ ${#SUMMARY_NEEDS_KEY[@]} -gt 0 ]; then
  echo -e "${YELLOW}API keys needed (add to $ENV_FILE):${NC}"
  for key in "${SUMMARY_NEEDS_KEY[@]}"; do
    echo "  - $key"
  done
  echo ""
fi

echo -e "${BLUE}Next step for your AI agent:${NC}"
echo "  Tell your AI: 'Read $SKILLS_DIR/01-teach-yourself-protocol/SKILL.md and begin onboarding.'"
echo ""
echo "  Your AI will walk through each skill in order."
echo "  You only need to answer when it asks for credentials or account info."
echo ""

if [ -n "$QMD_PID" ]; then
  echo -e "${YELLOW}QMD embed still running in background (pid $QMD_PID).${NC}"
  echo "  Personas will be searchable once it completes (3-8 min)."
  echo "  Check: qmd status"
  echo ""
fi

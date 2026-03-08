#!/bin/bash
# OpenClaw Onboarding - Master Install Script
# One command installs everything, step by step.
# Usage: curl -fsSL https://raw.githubusercontent.com/trevorotts1/openclaw-onboarding/main/install.sh | bash

set -e

REPO_URL="https://github.com/trevorotts1/openclaw-onboarding"
SKILLS_DIR="$HOME/.openclaw/skills"
TEMP_DIR=$(mktemp -d)
SUMMARY_INSTALLED=()
SUMMARY_NEEDS_KEY=()
SUMMARY_SKIPPED=()

# All env file locations to search (in priority order)
ENV_SEARCH_PATHS=(
  "$HOME/clawd/secrets/.env"
  "$HOME/.openclaw/.env"
  "$HOME/.openclaw/config/.env"
  "$HOME/clawd/.env"
  "$HOME/.env"
)
# Primary env file - where new keys get written
PRIMARY_ENV="$HOME/clawd/secrets/.env"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

print_step()  { echo -e "\n${BLUE}==>${NC} ${BOLD}$1${NC}"; }
print_ok()    { echo -e "  ${GREEN}✅${NC} $1"; }
print_warn()  { echo -e "  ${YELLOW}⚠️${NC}  $1"; }
print_fail()  { echo -e "  ${RED}❌${NC} $1"; }
print_info()  { echo -e "  ${BLUE}ℹ${NC}  $1"; }
print_skip()  { echo -e "  ${YELLOW}⏭${NC}  $1"; }

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║        OpenClaw Onboarding - Auto Installer      ║"
echo "║  Skills install automatically. Sit back.         ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ─────────────────────────────────────────────
# STEP 1: Check OpenClaw is installed
# ─────────────────────────────────────────────
print_step "Checking OpenClaw..."
if ! command -v openclaw &>/dev/null; then
  print_fail "OpenClaw is not installed."
  echo ""
  echo "  Install OpenClaw first: https://docs.openclaw.ai"
  echo "  Then re-run this command."
  exit 1
fi
print_ok "OpenClaw $(openclaw --version 2>/dev/null || echo 'found')"

# ─────────────────────────────────────────────
# STEP 2: Scan ALL env files for existing keys
# ─────────────────────────────────────────────
print_step "Scanning for existing API keys..."
declare -A FOUND_KEYS

for env_path in "${ENV_SEARCH_PATHS[@]}"; do
  if [ -f "$env_path" ]; then
    print_info "Checking $env_path"
    while IFS='=' read -r key val; do
      [[ "$key" =~ ^#.*$ ]] && continue
      [[ -z "$key" ]] && continue
      key=$(echo "$key" | xargs)
      val=$(echo "$val" | xargs)
      if [ -n "$val" ] && [ "$val" != '""' ] && [ "$val" != "''" ]; then
        FOUND_KEYS["$key"]="$val"
      fi
    done < "$env_path"
  fi
done

KEY_COUNT=${#FOUND_KEYS[@]}
print_ok "Found $KEY_COUNT existing keys across all env files"

# ─────────────────────────────────────────────
# STEP 3: Download the package
# ─────────────────────────────────────────────
print_step "Downloading OpenClaw Onboarding from GitHub..."
curl -s -L "$REPO_URL/archive/refs/heads/main.zip" -o "$TEMP_DIR/onboarding.zip"
unzip -q "$TEMP_DIR/onboarding.zip" -d "$TEMP_DIR"
EXTRACTED="$TEMP_DIR/openclaw-onboarding-main"
print_ok "Downloaded and extracted"

# ─────────────────────────────────────────────
# STEP 4: Install skills to ~/.openclaw/skills/
# ─────────────────────────────────────────────
print_step "Installing all skill folders..."
mkdir -p "$SKILLS_DIR"
SKILL_COUNT=0
for skill_dir in "$EXTRACTED"/[0-9]*; do
  skill_name=$(basename "$skill_dir")
  cp -r "$skill_dir" "$SKILLS_DIR/"
  SKILL_COUNT=$((SKILL_COUNT + 1))
done
mkdir -p "$SKILLS_DIR/scripts"
cp "$EXTRACTED/scripts/"* "$SKILLS_DIR/scripts/" 2>/dev/null || true
chmod +x "$SKILLS_DIR/scripts/"*.sh 2>/dev/null || true
print_ok "$SKILL_COUNT skills installed to $SKILLS_DIR"

# ─────────────────────────────────────────────
# STEP 5: QMD (install FIRST - required by skills 22 + 23)
# ─────────────────────────────────────────────
print_step "Installing QMD (required - installs now, before platform skills)..."
if command -v qmd &>/dev/null; then
  print_ok "QMD already installed ($(qmd --version 2>/dev/null | head -1))"
else
  echo "  QMD not found. Installing..."
  if command -v bun &>/dev/null; then
    bun add -g @anthropic/qmd 2>/dev/null && print_ok "QMD installed via bun" || {
      print_warn "bun install failed. Trying npm..."
      npm install -g @anthropic/qmd 2>/dev/null && print_ok "QMD installed via npm" || {
        print_fail "QMD install failed. Install manually: npm install -g @anthropic/qmd"
        print_warn "Continuing without QMD - skills 22 and 23 will need it later"
      }
    }
  else
    print_warn "bun not found. Installing bun first..."
    curl -fsSL https://bun.sh/install | bash 2>/dev/null
    export PATH="$HOME/.bun/bin:$PATH"
    bun add -g @anthropic/qmd 2>/dev/null && print_ok "QMD installed via bun" || {
      npm install -g @anthropic/qmd 2>/dev/null && print_ok "QMD installed via npm" || {
        print_fail "QMD install failed. Install manually: npm install -g @anthropic/qmd"
        print_warn "Continuing - skill 22 install will retry"
      }
    }
  fi
fi

# ─────────────────────────────────────────────
# STEP 6: Other Dependencies
# ─────────────────────────────────────────────
print_step "Checking other dependencies..."

# Python3
if command -v python3 &>/dev/null; then
  print_ok "Python3 $(python3 --version 2>&1 | cut -d' ' -f2)"
else
  print_warn "Python3 not found - Skill 22 pipeline will not work without it"
fi

# Python packages
for pkg in pdfplumber ebooklib html2text; do
  python3 -c "import $pkg" 2>/dev/null && print_ok "$pkg" || {
    pip3 install $pkg --break-system-packages -q 2>/dev/null && print_ok "$pkg installed" || print_warn "$pkg install failed - install manually: pip3 install $pkg"
  }
done

# Calibre (optional - for MOBI/AZW3)
if command -v ebook-convert &>/dev/null; then
  print_ok "Calibre (MOBI/AZW3 support)"
else
  print_info "Calibre not found - MOBI/AZW3 books won't convert. Install: brew install --cask calibre"
fi

# ─────────────────────────────────────────────
# STEP 7: API Keys - check all env files, ask if missing, offer skip
# ─────────────────────────────────────────────
print_step "Checking API keys..."
echo "  (Checked all env files: ${ENV_SEARCH_PATHS[*]})"
echo ""

PENDING_FILE="$HOME/.openclaw/skills/.pending-setup.md"

log_pending() {
  local key_name="$1"
  local description="$2"
  local skill="$3"
  mkdir -p "$(dirname "$PENDING_FILE")"
  if [ ! -f "$PENDING_FILE" ]; then
    cat > "$PENDING_FILE" << HEADER
# Pending Skill Setup
These API keys were skipped during install. Your AI agent checks this file and will remind you when it is time to set them up.

HEADER
  fi
  cat >> "$PENDING_FILE" << ENTRY

## $key_name
- **Skill:** $skill
- **What it unlocks:** $description
- **How to add:** echo '${key_name}=YOUR_KEY_HERE' >> $PRIMARY_ENV
- **Status:** PENDING
ENTRY
}

check_key() {
  local key_name="$1"
  local description="$2"
  local skill="$3"

  # Check all env files (already loaded into FOUND_KEYS)
  if [ -n "${FOUND_KEYS[$key_name]}" ]; then
    print_ok "$key_name (found in env files)"
    SUMMARY_INSTALLED+=("$key_name")
    return 0
  fi

  echo ""
  print_warn "$key_name not found in any env file"
  echo "    Needed for: $description"
  echo ""
  echo "    Options:"
  echo "      [1] Enter the key now"
  echo "      [2] Skip this key - remind me later"
  echo "      [3] Skip permanently - I don't use this service"
  echo ""
  read -t 30 -p "    Choose (1/2/3) [2]: " choice || choice="2"
  choice="${choice:-2}"
  echo ""

  case "$choice" in
    1)
      read -p "    Enter $key_name: " user_key
      if [ -n "$user_key" ]; then
        mkdir -p "$(dirname "$PRIMARY_ENV")"
        echo "${key_name}=${user_key}" >> "$PRIMARY_ENV"
        FOUND_KEYS["$key_name"]="$user_key"
        print_ok "$key_name saved to $PRIMARY_ENV"
        SUMMARY_INSTALLED+=("$key_name")
        return 0
      else
        print_warn "Empty key - logging as pending"
        log_pending "$key_name" "$description" "$skill"
        SUMMARY_NEEDS_KEY+=("$key_name")
        return 1
      fi
      ;;
    3)
      print_skip "$key_name permanently skipped"
      SUMMARY_SKIPPED+=("$key_name")
      return 1
      ;;
    *)
      log_pending "$key_name" "$description" "$skill"
      print_skip "$key_name - logged as pending. Agent will remind you."
      SUMMARY_NEEDS_KEY+=("$key_name")
      return 1
      ;;
  esac
}

check_key "MOONSHOT_API_KEY"   "Book-to-Persona Phase 1: Kimi K2.5 book extraction"        "22-book-to-persona-coaching-leadership-system"
check_key "OPENROUTER_API_KEY" "Book-to-Persona Phase 2: DeepSeek analysis + model routing" "22-book-to-persona-coaching-leadership-system"
check_key "OPENAI_API_KEY"     "Book-to-Persona Phase 3: Codex persona synthesis"           "22-book-to-persona-coaching-leadership-system"
check_key "GITHUB_TOKEN"       "Push new personas to GitHub after pipeline runs"             "22-book-to-persona-coaching-leadership-system"
check_key "TAVILY_API_KEY"     "Skill 21: AI-optimized deep research search"                "21-tavily-search"
check_key "GHL_API_KEY"        "Skills 05-06: GoHighLevel / Convert and Flow integration"   "05-ghl-setup"
check_key "KIE_API_KEY"        "Skill 07: KIE.ai image generation"                          "07-kie-setup"

# ─────────────────────────────────────────────
# STEP 8: QMD Collection Setup (runs in background)
# ─────────────────────────────────────────────
print_step "Setting up QMD coaching-personas collection..."

PERSONAS_DIR="$SKILLS_DIR/22-book-to-persona-coaching-leadership-system/personas"
if [ -d "$PERSONAS_DIR" ] && command -v qmd &>/dev/null; then
  if qmd status 2>/dev/null | grep -q "coaching-personas"; then
    print_ok "QMD coaching-personas collection already exists"
  else
    qmd collection add "$PERSONAS_DIR" --name coaching-personas --mask "**/*.md" 2>/dev/null && {
      qmd update -c coaching-personas 2>/dev/null
      print_ok "coaching-personas added to QMD"
      print_info "Starting QMD embed in background (3-8 min)..."
      qmd embed -c coaching-personas 2>/dev/null &
      QMD_PID=$!
      SUMMARY_INSTALLED+=("QMD coaching-personas collection")
    } || print_warn "QMD collection setup failed - run manually after install"
  fi
else
  [ ! -d "$PERSONAS_DIR" ] && print_warn "Personas folder not found - QMD setup skipped"
  ! command -v qmd &>/dev/null && print_warn "QMD not available - install manually then re-run skill 22"
fi

# ─────────────────────────────────────────────
# STEP 9: Weekly update cron
# ─────────────────────────────────────────────
print_step "Setting up weekly skill auto-update..."
if crontab -l 2>/dev/null | grep -q "update-skills.sh"; then
  print_ok "Weekly update cron already active"
else
  CRON_JOB="0 2 * * 0 $SKILLS_DIR/scripts/update-skills.sh >> $HOME/.openclaw/skills/.update-log 2>&1"
  (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
  print_ok "Weekly update cron set (Sundays at 2:00 AM)"
  SUMMARY_INSTALLED+=("Weekly auto-update cron")
fi

# Save installed version
REMOTE_VERSION=$(grep -m1 "^## \[v" "$EXTRACTED/CHANGELOG.md" 2>/dev/null | sed 's/## \[\(v[0-9.]*\)\].*/\1/' || echo "unknown")
echo "$REMOTE_VERSION" > "$SKILLS_DIR/.onboarding-version"

# Cleanup
rm -rf "$TEMP_DIR"

# ─────────────────────────────────────────────
# SUMMARY + AUTO-START SIGNAL
# ─────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║            Files installed successfully          ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""
echo -e "  Version: ${GREEN}$REMOTE_VERSION${NC}"
echo -e "  Skills:  ${GREEN}$SKILLS_DIR${NC}"
echo ""

if [ ${#SUMMARY_INSTALLED[@]} -gt 0 ]; then
  echo -e "  ${GREEN}Ready:${NC}"
  for item in "${SUMMARY_INSTALLED[@]}"; do
    echo "    ✅ $item"
  done
  echo ""
fi

if [ ${#SUMMARY_NEEDS_KEY[@]} -gt 0 ]; then
  echo -e "  ${YELLOW}Pending API keys (agent will remind you):${NC}"
  for item in "${SUMMARY_NEEDS_KEY[@]}"; do
    echo "    ⏳ $item"
  done
  echo -e "  Details: $PENDING_FILE"
  echo ""
fi

if [ ${#SUMMARY_SKIPPED[@]} -gt 0 ]; then
  echo -e "  ${YELLOW}Permanently skipped:${NC}"
  for item in "${SUMMARY_SKIPPED[@]}"; do
    echo "    ⏭ $item"
  done
  echo ""
fi

if [ -n "$QMD_PID" ]; then
  echo -e "  ${YELLOW}QMD embed running in background (pid $QMD_PID, ~3-8 min)${NC}"
  echo "  Check progress: qmd status"
  echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo -e "  ${BOLD}${GREEN}READY. Your AI agent will now begin installing skills.${NC}"
echo ""
echo -e "  ${BLUE}Paste this to your AI agent to begin:${NC}"
echo ""
echo -e "  ${BOLD}Read $SKILLS_DIR/Start\\ Here.md and begin onboarding now."
echo "  Install every skill in order, starting with skill 01."
echo "  Do not ask me to begin - just start."
echo -e "  Confirm each skill installed before moving to the next.${NC}"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

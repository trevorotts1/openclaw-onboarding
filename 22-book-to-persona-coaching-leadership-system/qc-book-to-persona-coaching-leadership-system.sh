#!/usr/bin/env bash
# Skill 22 — Book-to-Persona Coaching Leadership System — Install QC
# v10.12.0: dropped erroneous Skill 31 assert; added real INSTALL.md dependency checks.
# QC runs in a DIFFERENT sub-agent than the installer (N5).
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/.openclaw/workspace" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GEMINI_API_KEY:=}"; : "${GOOGLE_API_KEY:=}"; : "${OPENAI_API_KEY:=}"
: "${OLLAMA_CLOUD_API_KEY:=}"; : "${OPENROUTER_API_KEY:=}"

py_pkg(){ python3 -c "import $1" 2>/dev/null; }

echo ""
echo "═══ Skill 22 — Book-to-Persona Coaching Leadership — Install QC ═══"
echo ""

echo "--- Structural (Skill 22 present) ---"
assert "Skill 22 folder present"                        "[ -d \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system\" ]"
assert "INSTRUCTIONS.md present (TYP read-order req)"   "[ -f \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system/INSTRUCTIONS.md\" ]"
assert "pipeline/orchestrator.py present"               "[ -f \"$SKILLS_DIR_DEFAULT/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py\" ]"

echo ""
echo "--- Runtime: Python + required packages (INSTALL.md hard prereqs) ---"
assert "Python 3.8+ installed"                          "python3 -c 'import sys; sys.exit(0 if sys.version_info[:2] >= (3,8) else 1)'"
assert "pdfplumber package importable"                  "py_pkg pdfplumber"
assert "pypdf package importable"                       "py_pkg pypdf"
assert "ebooklib package importable"                    "py_pkg ebooklib"
assert "aiohttp package importable"                     "py_pkg aiohttp"
assert "beautifulsoup4 package importable (bs4)"        "py_pkg bs4"
assert "mobi package importable"                        "py_pkg mobi"
assert "lxml package importable"                        "py_pkg lxml"
assert "numpy package importable"                       "py_pkg numpy"
warn_only "google-genai package importable (Gemini path)" "py_pkg google.genai"
warn_only "openai package importable (OpenAI fallback per N18)" "py_pkg openai"

echo ""
echo "--- Runtime: Calibre ebook-convert (N26) ---"
assert "Calibre 'ebook-convert' binary on PATH or known location" \
  "command -v ebook-convert >/dev/null 2>&1 \
   || [ -x /opt/homebrew/bin/ebook-convert ] \
   || [ -x /usr/local/bin/ebook-convert ] \
   || [ -x /Applications/calibre.app/Contents/MacOS/ebook-convert ] \
   || [ -x /usr/bin/ebook-convert ] \
   || [ -x /snap/bin/ebook-convert ] \
   || [ -x /opt/calibre/ebook-convert ]"

echo ""
echo "--- Runtime: API keys / model providers (N1, N18) ---"
assert "Embedding key present (GEMINI_API_KEY or GOOGLE_API_KEY or OPENAI_API_KEY)" \
  "[ -n \"$GEMINI_API_KEY\" ] || [ -n \"$GOOGLE_API_KEY\" ] || [ -n \"$OPENAI_API_KEY\" ]"
warn_only "Ollama Cloud key present (Phase 1/2 primary)" "[ -n \"$OLLAMA_CLOUD_API_KEY\" ]"
warn_only "OpenRouter key present (Phase 1/2/3 fallback)" "[ -n \"$OPENROUTER_API_KEY\" ]"

echo ""
echo "--- Pipeline outputs (warn if not yet produced) ---"
warn_only "coaching-personas folder exists"             "[ -d \"$WORKSPACE/coaching-personas\" ] || find $HOME/Downloads ~/Downloads -maxdepth 4 -name 'coaching-personas' 2>/dev/null | head -1 | grep -q ."
warn_only "persona-categories.json present"             "find $HOME/Downloads ~/Downloads \"$WORKSPACE\" -maxdepth 5 -name 'persona-categories.json' 2>/dev/null | head -1 | grep -q ."
warn_only "PERSONA-ROUTER.md present"                   "find $HOME/Downloads ~/Downloads \"$WORKSPACE\" -maxdepth 5 -name 'PERSONA-ROUTER.md' 2>/dev/null | head -1 | grep -q ."

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 22 QC FAILED"; exit 1; } || { green "Skill 22 QC PASS"; exit 0; }

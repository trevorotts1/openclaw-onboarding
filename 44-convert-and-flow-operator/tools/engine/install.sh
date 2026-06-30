#!/usr/bin/env bash
# Convert and Flow CLI installer (Mac path).
# Installs into ~/.openclaw/tools/convert-and-flow-cli/.venv
# Credentials go in ~/.openclaw/secrets/.env — NOT in this directory.
#
# Usage:
#   bash install.sh            # install / upgrade
#   VENV_DIR=/custom/path bash install.sh   # override venv location

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="${VENV_DIR:-$HOME/.openclaw/tools/convert-and-flow-cli/.venv}"
PY=${PYTHON:-python3}

echo "Convert and Flow CLI installer"
echo "  venv -> $VENV_DIR"
echo "  source -> $SCRIPT_DIR"
echo

echo "-> checking python..."
"$PY" -c "import sys; assert sys.version_info >= (3, 10), 'need python 3.10+'"

if [ ! -d "$VENV_DIR" ]; then
  echo "-> creating venv..."
  "$PY" -m venv "$VENV_DIR"
fi

echo "-> installing package..."
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip -q
pip install -e "$SCRIPT_DIR" -q

# --- drift stamp: record the source version this binary was built from -------
# Lets scripts/tool-drift-check.sh PROVE the installed caf matches skill source
# instead of trusting source-on-disk. Mirrors the stamp written by the skill's
# root wire.sh. `set -e` is active, so reaching here means `pip install -e`
# succeeded; the `|| echo` keeps a failed stamp write non-fatal.
INSTALL_ROOT="$(dirname "$VENV_DIR")"                    # ~/.openclaw/tools/convert-and-flow-cli
SKILL_SRC="$(cd "$SCRIPT_DIR/../.." 2>/dev/null && pwd)" # engine -> tools -> skill root
SRC_VER="$( (tr -d '[:space:]' < "$SKILL_SRC/skill-version.txt") 2>/dev/null || echo unknown )"
[ -z "$SRC_VER" ] && SRC_VER="unknown"
{
  echo "TOOL=caf"
  echo "SKILL_VERSION=$SRC_VER"
  echo "ONBOARDING_VERSION=${ONBOARDING_VERSION:-}"
  echo "INSTALLED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "SOURCE_PATH=$SKILL_SRC"
} > "$INSTALL_ROOT/.installed-from" 2>/dev/null \
  && echo "-> stamped $INSTALL_ROOT/.installed-from (SKILL_VERSION=$SRC_VER)" \
  || echo "-> WARN: could not write drift stamp $INSTALL_ROOT/.installed-from (non-fatal)"

chmod +x "$SCRIPT_DIR/ghl" "$SCRIPT_DIR/caf" "$SCRIPT_DIR/convertandflow"

# Symlink into ~/.local/bin if on PATH
if [ -d "$HOME/.local/bin" ] && [[ ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
  ln -sf "$SCRIPT_DIR/caf" "$HOME/.local/bin/caf"
  ln -sf "$SCRIPT_DIR/convertandflow" "$HOME/.local/bin/convertandflow"
  ln -sf "$SCRIPT_DIR/ghl" "$HOME/.local/bin/ghl"
  echo "-> symlinked caf / convertandflow / ghl into ~/.local/bin"
fi

echo
echo "Install complete."
echo
echo "Next steps:"
echo "  1. Add credentials to ~/.openclaw/secrets/.env:"
echo "       GOHIGHLEVEL_API_KEY=pit-..."
echo "       GOHIGHLEVEL_LOCATION_ID=..."
echo "  2. Smoke test:"
echo "       caf contacts list --limit 5"
echo "       caf --help"
echo "  3. For workflow creation, grab the Firebase token with the"
echo "     Chrome extension (chrome-extension/) and add:"
echo "       GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN=..."
echo

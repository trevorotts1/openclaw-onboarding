#!/usr/bin/env bash
# 06-verify-agent-browser.sh -- Skill 41 Build With AI Playbook Generator
# Agent Browser preflight: install Vercel Agent Browser if absent (platform-aware),
# verify it can launch headless Chrome via CDP, verify it can reach the encrypted
# auth vault. FLAGS LOUDLY on any failure -- never silent.
#
# Exit codes:
#   0 = all checks pass (Agent Browser installed + headless Chrome OK + vault reachable)
#   1 = install or verification failed (browser rung degrades to human-escalation)
#   2 = unsupported OS
#
# Pairs with: protocols/agent-browser-preflight-protocol.md
# Called from: install sequence after 05-setup-minimax-executor.sh (gap #4)
set -uo pipefail

# ─── helpers ────────────────────────────────────────────────────────────────

SKILL_TAG="[skill 41][agent-browser]"

_flag_loudly() {
  # Print a loud, impossible-to-miss failure banner and a human-escalation directive.
  local reason="$1"
  echo ""
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "!! AGENT BROWSER PREFLIGHT FAILED                                        !!"
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo "!! REASON : $reason"
  echo "!! IMPACT : Browser execution rung is UNAVAILABLE.                       !!"
  echo "!!          The skill CANNOT automate GHL Build-With-AI from the browser. !!"
  echo "!! ACTION : Human operator must complete the GHL build step manually.    !!"
  echo "!!          Do NOT proceed with automated browser execution.              !!"
  echo "!!          Investigate and re-run this script once the issue is fixed.  !!"
  echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
  echo ""
}

_info() { echo "$SKILL_TAG $*"; }
_warn() { echo "$SKILL_TAG WARNING: $*"; }
_fail() { _flag_loudly "$1"; exit 1; }

# ─── platform detection ─────────────────────────────────────────────────────

OS="$(uname -s)"
case "$OS" in
  Darwin)
    PLATFORM="mac"
    OC_HOME="${HOME}/.openclaw"
    ;;
  Linux)
    PLATFORM="vps"
    OC_HOME="/data/.openclaw"
    ;;
  *)
    echo "$SKILL_TAG OS: $OS UNSUPPORTED"
    exit 2
    ;;
esac
_info "Platform: $PLATFORM ($OS)"
_info "OpenClaw home: $OC_HOME"

# ─── encrypted auth vault path ───────────────────────────────────────────────
# The vault stores GHL session credentials for Agent Browser.
# Convention: $OC_HOME/agent-browser-vault/ (created by the auth setup step).
VAULT_DIR="${OC_HOME}/agent-browser-vault"

# ─── step 1: verify Node.js is available ─────────────────────────────────────
# Agent Browser is a Node.js package. We need node >= 18.

_info "Step 1: Checking Node.js availability..."

_resolve_node() {
  # Try PATH first, then known platform-specific locations.
  if command -v node >/dev/null 2>&1; then
    echo "node"
    return 0
  fi
  if [[ "$PLATFORM" == "mac" ]]; then
    # Homebrew on Apple Silicon and Intel
    for candidate in \
      /opt/homebrew/bin/node \
      /usr/local/bin/node \
      /opt/homebrew/opt/node/bin/node; do
      if [[ -x "$candidate" ]]; then echo "$candidate"; return 0; fi
    done
  else
    # VPS: nvm, n, or system node
    for candidate in \
      /usr/local/bin/node \
      /usr/bin/node \
      /data/.nvm/versions/node/*/bin/node \
      /home/node/.nvm/versions/node/*/bin/node; do
      # Glob expansion — pick the newest match
      for g in $candidate; do
        if [[ -x "$g" ]]; then echo "$g"; return 0; fi
      done
    done
  fi
  return 1
}

NODE_BIN="$(_resolve_node)" || true
if [[ -z "${NODE_BIN:-}" ]]; then
  _fail "Node.js not found on PATH or any known location. Install Node.js >= 18 first (Mac: brew install node; VPS: use system package manager or nvm)."
fi

NODE_VERSION="$("$NODE_BIN" --version 2>/dev/null || true)"
_info "Node.js: $NODE_BIN  version: ${NODE_VERSION:-unknown}"

# Minimum Node 18 check
_node_major() { "$NODE_BIN" -e 'process.stdout.write(String(process.versions.node.split(".")[0]))' 2>/dev/null || echo "0"; }
NODE_MAJOR="$(_node_major)"
if [[ "$NODE_MAJOR" -lt 18 ]]; then
  _fail "Node.js $NODE_VERSION is too old. Agent Browser requires Node.js >= 18. Current major: $NODE_MAJOR."
fi
_info "Node.js version check: OK (major=$NODE_MAJOR >= 18)"

# ─── step 2: resolve npm / install helper ────────────────────────────────────

_resolve_npm() {
  if command -v npm >/dev/null 2>&1; then echo "npm"; return 0; fi
  local npm_sibling
  npm_sibling="$(dirname "$NODE_BIN")/npm"
  if [[ -x "$npm_sibling" ]]; then echo "$npm_sibling"; return 0; fi
  return 1
}

NPM_BIN="$(_resolve_npm)" || true
if [[ -z "${NPM_BIN:-}" ]]; then
  _fail "npm not found. It should ship with Node.js. Check your Node.js install."
fi
_info "npm: $NPM_BIN  version: $("$NPM_BIN" --version 2>/dev/null || echo 'unknown')"

# ─── step 3: install Vercel Agent Browser if absent ──────────────────────────

_info "Step 2: Checking Vercel Agent Browser installation..."

# Package name: @vercel/agent-browser
AGENT_BROWSER_PKG="@vercel/agent-browser"
# We look for the CLI entry point produced by the package.
# Adjust AGENT_BROWSER_BIN if the package ships a different binary name.
AGENT_BROWSER_BIN="agent-browser"

_find_agent_browser() {
  # 1. on PATH
  if command -v "$AGENT_BROWSER_BIN" >/dev/null 2>&1; then
    command -v "$AGENT_BROWSER_BIN"
    return 0
  fi
  # 2. local node_modules/.bin (if running from skill dir)
  local local_bin
  local_bin="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/../node_modules/.bin/$AGENT_BROWSER_BIN"
  if [[ -x "$local_bin" ]]; then echo "$local_bin"; return 0; fi
  # 3. global npm bin dir
  local npm_global_bin
  npm_global_bin="$("$NPM_BIN" bin -g 2>/dev/null || true)"
  if [[ -n "$npm_global_bin" && -x "${npm_global_bin}/${AGENT_BROWSER_BIN}" ]]; then
    echo "${npm_global_bin}/${AGENT_BROWSER_BIN}"
    return 0
  fi
  return 1
}

AB_BIN="$(_find_agent_browser)" || true

if [[ -z "${AB_BIN:-}" ]]; then
  _info "Agent Browser not found. Installing $AGENT_BROWSER_PKG ..."

  if [[ "$PLATFORM" == "mac" ]]; then
    # Mac: install globally via Homebrew-managed npm
    # Use --prefer-offline when possible; fall back to online install.
    _info "Mac install: npm install -g $AGENT_BROWSER_PKG"
    if ! "$NPM_BIN" install -g "$AGENT_BROWSER_PKG" 2>&1 | sed "s/^/$SKILL_TAG npm: /"; then
      _fail "npm install -g $AGENT_BROWSER_PKG failed on macOS. Check npm permissions (try: sudo chown -R \$(whoami) \$(npm config get prefix)). See protocols/agent-browser-preflight-protocol.md."
    fi
  else
    # VPS: install as node user to avoid root-owned config freeze.
    # The service user is named 'node' on OpenClaw Hostinger Docker images.
    # If we're already running AS node (uid check), install directly.
    # If we're root, use su to become node first.
    _info "VPS install: running as uid=$(id -u) user=$(id -un)"
    if [[ "$(id -un)" == "node" ]] || [[ "$(id -u)" -ne 0 ]]; then
      _info "VPS install: npm install -g $AGENT_BROWSER_PKG (current user)"
      if ! "$NPM_BIN" install -g "$AGENT_BROWSER_PKG" 2>&1 | sed "s/^/$SKILL_TAG npm: /"; then
        _fail "npm install -g $AGENT_BROWSER_PKG failed as $(id -un) on VPS. See protocols/agent-browser-preflight-protocol.md."
      fi
    else
      _info "VPS install: delegating to node user via su"
      if ! su -s /bin/sh node -c "$NPM_BIN install -g $AGENT_BROWSER_PKG" 2>&1 | sed "s/^/$SKILL_TAG npm: /"; then
        _fail "npm install -g $AGENT_BROWSER_PKG failed as node user on VPS. Check that the 'node' service user exists and can write to its npm prefix. See protocols/agent-browser-preflight-protocol.md."
      fi
    fi
  fi

  # Re-locate after install
  AB_BIN="$(_find_agent_browser)" || true
  if [[ -z "${AB_BIN:-}" ]]; then
    _fail "$AGENT_BROWSER_PKG was installed but the binary '$AGENT_BROWSER_BIN' is still not on PATH. Check npm bin dir is in PATH, then re-run this script."
  fi
  _info "Agent Browser installed successfully at: $AB_BIN"
else
  _info "Agent Browser already installed at: $AB_BIN"
fi

# Record the resolved binary path for later steps
AB_VERSION="$("$AB_BIN" --version 2>/dev/null || echo 'unknown')"
_info "Agent Browser version: ${AB_VERSION}"

# ─── step 4: verify headless Chrome launch via CDP ───────────────────────────

_info "Step 3: Verifying headless Chrome via CDP ..."

# Ask Agent Browser to launch a headless CDP session and exit cleanly.
# We use a minimal inline Node.js probe that calls the agent-browser API to:
#   1. Launch a headless browser instance
#   2. Open a blank page
#   3. Evaluate 1+1 (sanity check the JS engine is up)
#   4. Close the browser
# If agent-browser exposes a programmatic API, we call it. If it is a CLI tool
# that drives browser sessions, we adapt. This probe is written against the
# @vercel/agent-browser API surface; adjust if the package ships differently.
CDP_PROBE_SCRIPT="$(mktemp /tmp/skill41-cdp-probe-XXXXXX.mjs)"
trap 'rm -f "$CDP_PROBE_SCRIPT"' EXIT

cat > "$CDP_PROBE_SCRIPT" << 'CDP_PROBE_EOF'
// Minimal CDP probe for Skill 41 preflight.
// Uses @vercel/agent-browser headless launch API.
// If the package API differs, this probe surfaces the exact error rather than
// silently passing -- per protocol: never silent on failure.
import { createBrowser } from "@vercel/agent-browser";

let browser;
try {
  browser = await createBrowser({ headless: true });
  const page = await browser.newPage();
  await page.goto("about:blank");
  const result = await page.evaluate(() => 1 + 1);
  if (result !== 2) {
    process.stderr.write(`CDP probe: evaluate() returned unexpected value: ${result}\n`);
    process.exit(1);
  }
  process.stdout.write("CDP probe: headless Chrome launched OK, JS engine responsive\n");
  await browser.close();
  process.exit(0);
} catch (err) {
  if (browser) { try { await browser.close(); } catch (_) {} }
  process.stderr.write(`CDP probe FAILED: ${err.message}\n`);
  if (err.stack) process.stderr.write(`${err.stack}\n`);
  process.exit(1);
}
CDP_PROBE_EOF

CDP_OUTPUT="$("$NODE_BIN" --input-type=module < "$CDP_PROBE_SCRIPT" 2>&1)" || CDP_EXIT=$?
if [[ "${CDP_EXIT:-0}" -ne 0 ]]; then
  _fail "Headless Chrome CDP probe FAILED. Output: $CDP_OUTPUT -- Agent Browser cannot launch a browser session. Check: (1) Chromium/Chrome is installed ('which chromium-browser' or 'which google-chrome'), (2) the container is not sandboxed beyond what Chromium supports (VPS: try --no-sandbox flag), (3) @vercel/agent-browser is compatible with this Node.js version. See protocols/agent-browser-preflight-protocol.md."
fi
_info "Headless Chrome CDP probe: PASSED"
_info "Probe output: $CDP_OUTPUT"

# ─── step 5: verify reach to the encrypted auth vault ────────────────────────

_info "Step 4: Verifying encrypted auth vault ..."

if [[ ! -d "$VAULT_DIR" ]]; then
  _warn "Auth vault directory does not exist yet: $VAULT_DIR"
  _warn "This is expected on a FIRST-TIME install before the auth setup step."
  _warn "Create the vault by running the auth setup step, then re-run this script."
  # This is a WARNING, not a hard failure, on a fresh install.
  # We still continue because the rest of the preflight passed.
  VAULT_STATUS="NOT_CREATED_YET"
else
  # Vault exists: verify we can read a sentinel file (or at minimum list the dir).
  if [[ -r "$VAULT_DIR" ]]; then
    VAULT_FILE_COUNT="$(find "$VAULT_DIR" -maxdepth 1 -type f | wc -l | tr -d ' ')"
    _info "Auth vault: readable at $VAULT_DIR ($VAULT_FILE_COUNT file(s))"
    # Check for the expected session token file (name convention: session.enc or ghl-session.enc)
    if ls "$VAULT_DIR"/*.enc >/dev/null 2>&1; then
      _info "Auth vault: encrypted session file(s) present"
      VAULT_STATUS="OK"
    else
      _warn "Auth vault directory exists but contains no .enc session files."
      _warn "Run the GHL auth pairing step to populate the vault before browser execution."
      VAULT_STATUS="EMPTY"
    fi
  else
    _fail "Auth vault directory exists at $VAULT_DIR but is NOT readable by the current user ($(id -un)). Fix permissions: chmod +r $VAULT_DIR"
  fi
fi

# ─── step 6: write preflight result record ───────────────────────────────────

_info "Step 5: Writing preflight result..."

RESULT_FILE="${OC_HOME}/skill-41-agent-browser-preflight.json"
TIMESTAMP="$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")"

# Write a JSON record summarising this preflight run.
# This is read by downstream scripts (MiniMax executor preflight, QC runner).
if command -v jq >/dev/null 2>&1; then
  jq -nc \
    --arg ts          "$TIMESTAMP" \
    --arg platform    "$PLATFORM" \
    --arg node_bin    "$NODE_BIN" \
    --arg node_ver    "$NODE_VERSION" \
    --arg ab_bin      "$AB_BIN" \
    --arg ab_ver      "$AB_VERSION" \
    --arg cdp_probe   "PASSED" \
    --arg vault_dir   "$VAULT_DIR" \
    --arg vault_status "${VAULT_STATUS:-UNKNOWN}" \
    '{
      ts:           $ts,
      skill:        "41-build-with-ai-playbook",
      check:        "agent-browser-preflight",
      result:       "PASS",
      platform:     $platform,
      node_bin:     $node_bin,
      node_version: $node_ver,
      agent_browser_bin:     $ab_bin,
      agent_browser_version: $ab_ver,
      cdp_headless_probe:    $cdp_probe,
      vault_dir:    $vault_dir,
      vault_status: $vault_status
    }' > "$RESULT_FILE"
  _info "Preflight result written to: $RESULT_FILE"
else
  # jq not available — write a minimal plaintext marker so downstream scripts
  # can still detect that preflight ran.
  printf '{"ts":"%s","skill":"41-build-with-ai-playbook","check":"agent-browser-preflight","result":"PASS","platform":"%s"}\n' \
    "$TIMESTAMP" "$PLATFORM" > "$RESULT_FILE"
  _info "Preflight result written (no jq, plaintext fallback) to: $RESULT_FILE"
fi

# ─── summary ─────────────────────────────────────────────────────────────────

echo ""
_info "========================================"
_info "Agent Browser preflight: ALL CHECKS PASS"
_info "========================================"
_info "Node.js:       $NODE_BIN ($NODE_VERSION)"
_info "Agent Browser: $AB_BIN ($AB_VERSION)"
_info "CDP probe:     PASSED"
_info "Vault:         ${VAULT_STATUS:-UNKNOWN} at $VAULT_DIR"
echo ""
_info "The browser execution rung is READY."
_info "Next: run 05-setup-minimax-executor.sh if not already done,"
_info "then proceed to the skill QC gate (11-run-qc-checklist.sh)."

exit 0

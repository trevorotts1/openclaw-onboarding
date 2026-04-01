# Skill 32: Command Center Setup - Quality Control

## QC Checks

### 1. Required Files Present

```bash
FILES="SKILL.md INSTALL.md INSTRUCTIONS.md CORE_UPDATES.md command-center-setup.skill skill-version.txt"
OK=true
for f in $FILES; do
  if [ -f "$f" ]; then
    echo "  [PASS] $f exists"
  else
    echo "  [FAIL] $f MISSING"
    OK=false
  fi
done
$OK && echo "RESULT: ALL FILES PRESENT" || echo "RESULT: MISSING FILES"
```

Expected: All 6 files present.

### 2. Command Center Scripts Present

```bash
echo "--- Checking scripts directory ---"
if [ -d scripts ]; then
  echo "  [PASS] scripts/ directory exists"
  for script in scripts/*; do
    echo "  [INFO] Found: $(basename $script)"
  done
else
  echo "  [FAIL] scripts/ directory missing"
fi

echo "--- Checking workspace structure ---"
WS_DIR=~/.openclaw/workspaces/command-center
[ -d "$WS_DIR" ] && echo "  [PASS] Workspace directory exists at $WS_DIR" || echo "  [INFO] Workspace not yet created (install not run)"

echo "--- Checking PM2 ---"
pm2 --version >/dev/null 2>&1 && echo "  [PASS] PM2 installed" || echo "  [WARN] PM2 not installed (run: npm install -g pm2)"

echo "--- Checking cloudflared ---"
cloudflared --version >/dev/null 2>&1 && echo "  [PASS] cloudflared installed" || echo "  [INFO] cloudflared not installed (Phase 6b will install)"
```

### 3. Key Environment Variables

```bash
echo "Checking env vars..."
for var in TELEGRAM_BOT_TOKEN OPENCLAW_API_KEY CLOUDFLARE_TUNNEL_TOKEN; do
  val=$(printenv "$var" 2>/dev/null)
  [ -n "$val" ] && echo "  [PASS] $var is set" || echo "  [INFO] $var not set (may be optional or set in config)"
done
```

- `TELEGRAM_BOT_TOKEN` - Required for Telegram command center group
- `OPENCLAW_API_KEY` - Required for agent communication
- `CLOUDFLARE_TUNNEL_TOKEN` - Set after Phase 6b completes

### 4. Functional Test

```bash
# Check if dashboard is accessible (if installed)
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
if [ "$STATUS" = "200" ]; then
  echo "  [PASS] Dashboard accessible at localhost:3000 (HTTP $STATUS)"
else
  echo "  [INFO] Dashboard not responding at localhost:3000 (not installed or not running)"
fi

# Check PM2 process
pm2 list 2>/dev/null | grep -i command-center && echo "  [PASS] Command Center PM2 process running" || echo "  [INFO] Command Center not running in PM2"

# Verify config validates
openclaw config validate 2>&1 | head -3

echo "RESULT: Functional test complete"
```

Expected: Dashboard returns 200 if installed, PM2 shows running process, config validates.

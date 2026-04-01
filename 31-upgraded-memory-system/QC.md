# Skill 31: Upgraded Memory System - Quality Control

## QC Checks

### 1. Required Files Present

```bash
FILES="SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md HOW-YOUR-MEMORY-WORKS.md skill-version.txt"
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

Expected: All 7 files present.

### 2. Memory System Wired in Workspace

Check that core memory directories and files exist:

```bash
echo "--- Layer 1: Markdown Files ---"
ls ~/clawd/MEMORY.md 2>/dev/null && echo "  [PASS] MEMORY.md exists" || echo "  [FAIL] MEMORY.md missing"
[ -d ~/clawd/memory ] && echo "  [PASS] memory/ directory exists" || echo "  [FAIL] memory/ directory missing"

echo "--- Layer 2: Memory Flush ---"
grep -q "memoryFlush" ~/.openclaw/openclaw.json 2>/dev/null && echo "  [PASS] memoryFlush configured" || echo "  [FAIL] memoryFlush not found"

echo "--- Layer 3: Session Indexing ---"
grep -q "sessionMemory" ~/.openclaw/openclaw.json 2>/dev/null && echo "  [PASS] sessionMemory enabled" || echo "  [FAIL] sessionMemory not found"

echo "--- Layer 4: Gemini Embedding ---"
grep -q '"backend"' ~/.openclaw/openclaw.json 2>/dev/null && echo "  [INFO] backend value:" && grep '"backend"' ~/.openclaw/openclaw.json | head -1 || echo "  [FAIL] backend not configured"

echo "--- Layer 5: Mem0 ---"
openclaw plugins list 2>/dev/null | grep -qi mem0 && echo "  [PASS] Mem0 plugin loaded" || echo "  [FAIL] Mem0 plugin not loaded"
```

### 3. Key Environment Variables

```bash
echo "Checking env vars..."
for var in GOOGLE_API_KEY GEMINI_API_KEY OPENROUTER_API_KEY; do
  val=$(printenv "$var" 2>/dev/null)
  [ -n "$val" ] && echo "  [PASS] $var is set" || echo "  [INFO] $var not set (may be optional)"
done
```

- `GOOGLE_API_KEY` / `GEMINI_API_KEY` - Required for Layer 4 (Gemini Embedding 2)
- `OPENROUTER_API_KEY` - Used by Mem0 LLM if configured with Gemini

### 4. Functional Test

```bash
# Verify MEMORY.md has real content (not just a template header)
LINES=$(wc -l < ~/clawd/MEMORY.md 2>/dev/null || echo 0)
[ "$LINES" -gt 10 ] && echo "  [PASS] MEMORY.md has $LINES lines" || echo "  [FAIL] MEMORY.md too short ($LINES lines)"

# Verify daily log directory has at least one entry
LOGS=$(ls ~/clawd/memory/*.md 2>/dev/null | wc -l)
[ "$LOGS" -gt 0 ] && echo "  [PASS] $LOGS daily log file(s) found" || echo "  [WARN] No daily logs yet"

# Verify config validates
openclaw config validate 2>&1 | head -3

echo "RESULT: Functional test complete"
```

Expected: MEMORY.md has 10+ lines, at least 1 daily log, config validates.

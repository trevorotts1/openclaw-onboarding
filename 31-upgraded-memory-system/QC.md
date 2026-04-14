# QC Checklist — Skill 31: Upgraded Memory System

Run this after installation to verify all eight layers are in place and the memory stack is actually active.

---

## Section 1: File Structure + Version Check

```bash
SKILL_DIR="$HOME/.openclaw/skills/31-upgraded-memory-system"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$HOME/.openclaw/skills/upgraded-memory-system"

echo "Using skill dir: $SKILL_DIR"

for f in SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md \
         FULL-DOC.md HOW-YOUR-MEMORY-WORKS.md skill-version.txt; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

[ -f "$SKILL_DIR/skill-version.txt" ] && echo "Installed version: $(cat "$SKILL_DIR/skill-version.txt")"
```

**Pass criteria:** all required files are present.

---

## Section 2: Dependency + Environment Checks

Layer 4 requires Google Gemini dependencies.

```bash
python3 --version >/dev/null 2>&1 && echo "PASS: python3 found" || echo "FAIL: python3 missing"
python3 -c "from google import genai; import numpy; print('SDK ready')" 2>/dev/null \
  && echo "PASS: google-genai + numpy importable" \
  || echo "FAIL: google-genai and/or numpy missing"

echo "GOOGLE_API_KEY length: ${#GOOGLE_API_KEY}"
[ -n "$GOOGLE_API_KEY" ] \
  && echo "PASS: GOOGLE_API_KEY set" \
  || echo "INFO: GOOGLE_API_KEY not set - Layer 4 may be pending"
```

**Pass criteria:** Python packages import cleanly. `GOOGLE_API_KEY` is present unless Layer 4 is intentionally pending.

---

## Section 3: Eight-Layer Wiring Checks

### Layer 1: Markdown memory files

```bash
[ -f ~/.openclaw/workspace/MEMORY.md ] && echo "PASS: MEMORY.md exists" || echo "FAIL: MEMORY.md missing"
[ -d ~/.openclaw/workspace/memory ] && echo "PASS: memory/ directory exists" || echo "FAIL: memory/ directory missing"
```

### Layer 2: memoryFlush configured

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
md = obj.get('agents', {}).get('defaults', {})
flush = md.get('compaction', {}).get('memoryFlush', {})
print('PASS' if flush else 'FAIL', 'memoryFlush present' if flush else 'memoryFlush missing')
print('batchSize =', flush.get('batchSize'))
print('paths =', flush.get('paths'))
PY
```

### Layer 3: session memory enabled

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
ms = obj.get('agents', {}).get('defaults', {}).get('memorySearch', {})
print('sessionMemory =', ms.get('sessionMemory'))
print('PASS' if ms.get('sessionMemory') is True else 'FAIL', 'sessionMemory check')
PY
```

### Layer 4: Gemini search backend configured

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
mem = obj.get('memory', {})
ms = obj.get('agents', {}).get('defaults', {}).get('memorySearch', {})
print('memory.backend =', mem.get('backend'))
print('memorySearch.provider =', ms.get('provider'))
print('memorySearch.model =', ms.get('model'))
PY
```

**Expected:**
- `memory.backend` = `builtin`
- `memorySearch.provider` = `gemini`
- model = `models/gemini-embedding-2-preview`

### Layer 5: memory-core enabled

```bash
openclaw memory status 2>/dev/null | grep -E "Backend.*builtin" \
  && echo "PASS: memory-core (builtin backend) active" \
  || echo "FAIL: memory-core not detected"
```

### Layer 6: Cognee graph memory (optional)

```bash
openclaw cognee status 2>/dev/null | grep -i "connected" \
  && echo "PASS: Cognee connected" \
  || echo "INFO: Cognee not connected (optional layer)"
```

### Layer 7: Obsidian vault configured

```bash
ls /Applications/Obsidian.app 2>/dev/null \
  && echo "PASS: Obsidian app installed" \
  || echo "INFO: Obsidian not installed (Mac only)"
openclaw obsidian status 2>/dev/null | grep -i "vault" \
  && echo "PASS: Obsidian vault configured" \
  || echo "INFO: Obsidian vault not configured"
```

### Layer 8: Wiki system initialized

```bash
openclaw wiki status 2>/dev/null | grep -i "initialized" \
  && echo "PASS: Wiki system initialized" \
  || echo "INFO: Wiki system not initialized"
```

**Pass criteria:** Layers 1-5 and 7-8 pass (Layer 6 optional). Layer 4 passes if API key is available, or is explicitly marked pending if not.

---

## Section 4: Functional Tests

### 4.1 Config validation

```bash
openclaw config validate
```

**Expected:** config validates successfully.

### 4.2 Daily-memory presence

```bash
COUNT=$(ls ~/.openclaw/workspace/memory/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "Daily memory files: $COUNT"
[ "$COUNT" -ge 1 ] && echo "PASS: daily memory exists" || echo "WARN: no daily memory files yet"
```

### 4.3 Memory plugin runtime visibility

```bash
openclaw status 2>/dev/null | grep -i memory-core || echo "INFO: openclaw status did not print memory-core"
```

### 4.4 Search-path sanity

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
paths = obj.get('agents', {}).get('defaults', {}).get('compaction', {}).get('memoryFlush', {}).get('paths', [])
print('paths:', paths)
print('PASS' if any('memory' in str(x).lower() for x in paths) else 'FAIL', 'memory path included')
PY
```

---

## Section 5: Knowledge Verification

**Q1.** What are the eight layers?
> **Expected:** markdown memory files, memoryFlush summaries, session memory search, Gemini embedding search, memory-core auto-capture, Cognee graph knowledge, Obsidian vault, Wiki system.

**Q2.** What env var powers Layer 4?
> **Expected:** `GOOGLE_API_KEY`

**Q3.** What Python packages are required for Layer 4?
> **Expected:** `google-genai` and `numpy`

**Q4.** What powers Layer 5?
> **Expected:** `memory-core` (builtin backend, replaces the legacy memory plugin)

**Q5.** What search model should be configured?
> **Expected:** `models/gemini-embedding-2-preview`

**Pass criteria:** 5/5 correct.

---

## Section 6: Anti-Pattern Checks

Fail the skill if any of these happen:

- `memory.backend` is left on old Google Embedding 2 or anything other than `builtin`
- `memorySearch.provider` does not match `gemini`
- Layer 4 is claimed active without `GOOGLE_API_KEY`
- memory-core is not enabled but the system is reported as fully installed
- `google-genai` / `numpy` are missing but Layer 4 is reported as working
- session memory is disabled
- memoryFlush is absent from config

**Pass criteria:** zero anti-patterns triggered.

---

## Section 7: Active Memory Verification Checklist (10-Point)

Active Memory (Layer 8) is REQUIRED. Run these 10 checks to verify full activation:

### Check 1: Memory Backend is "builtin"
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
backend = obj.get('memory', {}).get('backend')
print('memory.backend =', backend)
print('PASS' if backend == 'builtin' else 'FAIL', '- must be "builtin"')
PY
```

### Check 2: Auto-Capture is Enabled
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
auto_capture = obj.get('agents', {}).get('defaults', {}).get('memory', {}).get('autoCapture')
print('memory.autoCapture =', auto_capture)
print('PASS' if auto_capture is True else 'FAIL', '- must be true')
PY
```

### Check 3: Auto-Recall is Enabled
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
auto_recall = obj.get('agents', {}).get('defaults', {}).get('memory', {}).get('autoRecall')
print('memory.autoRecall =', auto_recall)
print('PASS' if auto_recall is True else 'FAIL', '- must be true')
PY
```

### Check 4: Active Memory Master Switch is On
```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path.home()/'.openclaw/openclaw.json'
obj = json.loads(p.read_text())
am_enabled = obj.get('agents', {}).get('defaults', {}).get('activeMemory', {}).get('enabled')
print('activeMemory.enabled =', am_enabled)
print('PASS' if am_enabled is True else 'WARN', '- should be true (optional but recommended)')
PY
```

### Check 5: Memory-Core Reports Active Status
```bash
openclaw memory status 2>/dev/null | grep -E "Backend.*builtin" \
  && echo "PASS: memory-core backend is builtin" \
  || echo "FAIL: memory-core backend not builtin"
```

### Check 6: Auto-Capture Shows Enabled in Status
```bash
openclaw memory status 2>/dev/null | grep -i "auto.*capture" | grep -i "enabled" \
  && echo "PASS: auto-capture enabled" \
  || echo "FAIL: auto-capture not enabled"
```

### Check 7: Auto-Recall Shows Enabled in Status
```bash
openclaw memory status 2>/dev/null | grep -i "auto.*recall" | grep -i "enabled" \
  && echo "PASS: auto-recall enabled" \
  || echo "FAIL: auto-recall not enabled"
```

### Check 8: Gateway Has Been Restarted Since Config Change
```bash
openclaw status 2>/dev/null | grep -i "gateway" | head -1
echo "INFO: If config was changed recently, verify gateway was restarted"
```

### Check 9: Memory Search Returns Results
```bash
# This tests that memory-core is actually working
openclaw memory search "test query" 2>/dev/null | head -5 \
  && echo "PASS: memory search returns results" \
  || echo "WARN: memory search did not return results (may be empty)"
```

### Check 10: Wiki System Initialized (Layer 8 Component)
```bash
openclaw wiki status 2>/dev/null | grep -i "initialized" \
  && echo "PASS: Wiki system initialized" \
  || echo "FAIL: Wiki system not initialized"
```

### Active Memory Scoring

| Score | Interpretation |
|-------|----------------|
| 10/10 | Active Memory fully activated and operational |
| 8-9/10 | Core Active Memory working, minor config optional |
| 6-7/10 | Active Memory functional but missing recommended settings |
| < 6/10 | Active Memory NOT properly activated - FIX REQUIRED |

**Pass criteria for Layer 8:** Checks 1-3, 5-7, and 10 must PASS. This is REQUIRED, not optional.

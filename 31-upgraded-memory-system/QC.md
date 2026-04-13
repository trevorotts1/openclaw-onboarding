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

# QC Checklist — Skill 31: Upgraded Memory System

Run this after installation to verify all five layers are in place and the memory stack is actually active.

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

## Section 3: Five-Layer Wiring Checks

### Layer 1: Markdown memory files

```bash
[ -f ~/clawd/MEMORY.md ] && echo "PASS: MEMORY.md exists" || echo "FAIL: MEMORY.md missing"
[ -d ~/clawd/memory ] && echo "PASS: memory/ directory exists" || echo "FAIL: memory/ directory missing"
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
- `memory.backend` = `gemini`
- `memorySearch.provider` = `gemini`
- model = `models/gemini-embedding-2-preview`

### Layer 5: Mem0 plugin installed and loaded

```bash
openclaw plugins list 2>/dev/null | grep -i mem0 \
  && echo "PASS: Mem0 plugin listed" \
  || echo "FAIL: Mem0 plugin not detected"
```

**Pass criteria:** Layers 1, 2, 3, and 5 pass. Layer 4 passes if API key is available, or is explicitly marked pending if not.

---

## Section 4: Functional Tests

### 4.1 Config validation

```bash
openclaw config validate
```

**Expected:** config validates successfully.

### 4.2 Daily-memory presence

```bash
COUNT=$(ls ~/clawd/memory/*.md 2>/dev/null | wc -l | tr -d ' ')
echo "Daily memory files: $COUNT"
[ "$COUNT" -ge 1 ] && echo "PASS: daily memory exists" || echo "WARN: no daily memory files yet"
```

### 4.3 Memory plugin runtime visibility

```bash
openclaw status 2>/dev/null | grep -i mem0 || echo "INFO: openclaw status did not print mem0"
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

**Q1.** What are the five layers?
> **Expected:** markdown memory files, memoryFlush summaries, session memory search, Gemini embedding search, Mem0 plugin memory.

**Q2.** What env var powers Layer 4?
> **Expected:** `GOOGLE_API_KEY`

**Q3.** What Python packages are required for Layer 4?
> **Expected:** `google-genai` and `numpy`

**Q4.** What plugin powers Layer 5?
> **Expected:** `openclaw-mem0`

**Q5.** What search model should be configured?
> **Expected:** `models/gemini-embedding-2-preview`

**Pass criteria:** 5/5 correct.

---

## Section 6: Anti-Pattern Checks

Fail the skill if any of these happen:

- `memory.backend` is left on old Google Embedding 2 or anything other than `gemini`
- `memorySearch.provider` does not match `gemini`
- Layer 4 is claimed active without `GOOGLE_API_KEY`
- Mem0 plugin is missing but the system is reported as fully installed
- `google-genai` / `numpy` are missing but Layer 4 is reported as working
- session memory is disabled
- memoryFlush is absent from config

**Pass criteria:** zero anti-patterns triggered.

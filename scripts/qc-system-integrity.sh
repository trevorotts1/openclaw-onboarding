#!/bin/bash
# qc-system-integrity.sh — v9.6.2
#
# Executable runner for SYSTEM-DIAGNOSTIC-CHECKLIST.md.
# Runs the 9 check sections + cross-cutting checks. Exits 0 only when all green.
#
# Categories: 1=Interview, 2=Workforce, 3=Book-to-Persona, 4=Gemini, 5=Semantic,
#             6=Keyword, 7=Tasks/Kanban, 8=Persona, 9=Agent linking, X=Cross-cutting.

set -u  # NOT -e — we want to keep running after failures, then report all at the end

PASS=0
FAIL=0
WARN=0
FAILURES=()
WARNINGS=()

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
blue()   { printf "\033[34m%s\033[0m\n" "$1"; }

check() {
  local id="$1"; local desc="$2"; local cmd="$3"; local remedy="${4:-}"
  if eval "$cmd" >/dev/null 2>&1; then
    green "  ✓ $id  $desc"
    PASS=$((PASS+1))
  else
    red   "  ✗ $id  $desc"
    PASS=$PASS  # explicit no-op
    FAIL=$((FAIL+1))
    FAILURES+=("$id|$desc|$remedy")
  fi
}

warn_check() {
  local id="$1"; local desc="$2"; local cmd="$3"; local remedy="${4:-}"
  if eval "$cmd" >/dev/null 2>&1; then
    green "  ✓ $id  $desc"
    PASS=$((PASS+1))
  else
    yellow "  ⚠ $id  $desc (warn-only)"
    WARN=$((WARN+1))
    WARNINGS+=("$id|$desc|$remedy")
  fi
}

# ─── platform detect ─────────────────────────────────────────────────────────
# Wave 6 housekeeping: VPS WORKSPACE corrected to /data/.openclaw/workspace
# (the canonical path used everywhere else); /data/clawd was legacy drift.
# Platform label corrected: 'desktop' → 'mac' to match openclaw.json and the
# detect_platform.py shared util.
if [ -d "/data/.openclaw" ]; then
  PLATFORM=vps
  WORKSPACE=/data/.openclaw/workspace
  SECRETS=/data/.openclaw/secrets/.env
  OCJSON=/data/.openclaw/openclaw.json
  MASTER=/data/Downloads/openclaw-master-files
else
  PLATFORM=mac
  WORKSPACE=$HOME/clawd
  SECRETS=$HOME/.openclaw/secrets/.env
  OCJSON=$HOME/.openclaw/openclaw.json
  MASTER=$HOME/Downloads/openclaw-master-files
fi

ZHC=$WORKSPACE/zero-human-company
ZHC_ALT=$WORKSPACE/zhc

# Auto-pick the most-recently-modified company under ZHC
COMPANY_DIR=$(ls -dt "$ZHC"/*/ 2>/dev/null | head -1)
[ -z "$COMPANY_DIR" ] && COMPANY_DIR=$(ls -dt "$ZHC_ALT"/*/ 2>/dev/null | head -1)
COMPANY_DIR=${COMPANY_DIR%/}

echo
blue "══════════════════════════════════════════════════"
blue "  OpenClaw System Integrity Check — v9.6.2"
blue "══════════════════════════════════════════════════"
echo "Platform:   $PLATFORM"
echo "Workspace:  $WORKSPACE"
echo "ZHC root:   $ZHC"
echo "Company:    ${COMPANY_DIR:-<none built yet>}"
echo "Date:       $(date)"
echo

# ─── CHECK 1: AI Workforce Interview ─────────────────────────────────────────
blue "── CHECK 1: AI Workforce Interview (Skill 23) ──"
check "1.1" "ZHC company folder exists" \
  "[ -n \"$COMPANY_DIR\" ] && [ -d \"$COMPANY_DIR/departments\" ]" \
  "Run Skill 23 first via 'Start AI workforce blueprint' in your agent chat"
check "1.2" "Pre-interview research file present" \
  "[ -f \"$COMPANY_DIR/pre-interview-research.md\" ]" \
  "Either the client said 'no docs' or Step 6a was skipped — fine if intentional"
check "1.3" "workforce-interview-answers.md exists" \
  "[ -f \"$COMPANY_DIR/workforce-interview-answers.md\" ]" \
  "Interview hasn't been run yet"
check "1.4" "interview-handoff.md has a status field" \
  "[ -f \"$COMPANY_DIR/interview-handoff.md\" ] && grep -q 'status' \"$COMPANY_DIR/interview-handoff.md\"" \
  "Handoff file missing or malformed; rerun Skill 23 Option C (Audit/Resume)"
check "1.5" "MEMORY.md has '## AI Workforce Build' section" \
  "grep -q '## AI Workforce Build' $WORKSPACE/MEMORY.md" \
  "Re-apply Skill 23 CORE_UPDATES.md to your MEMORY.md"

# ─── CHECK 2: AI Workforce Skill Set (build phase) ───────────────────────────
echo
blue "── CHECK 2: AI Workforce Skill Set (build phase) ──"
# 2.1 — dept count match
if [ -f "$COMPANY_DIR/departments.json" ]; then
  EXPECTED=$(python3 -c "import json; print(len(json.load(open('$COMPANY_DIR/departments.json'))))" 2>/dev/null)
  ACTUAL=$(ls -d "$COMPANY_DIR/departments"/*/ 2>/dev/null | wc -l | tr -d ' ')
  if [ -n "$EXPECTED" ] && [ "$EXPECTED" = "$ACTUAL" ]; then
    green "  ✓ 2.1  Department count matches interview ($ACTUAL = $EXPECTED)"; PASS=$((PASS+1))
  else
    red "  ✗ 2.1  Dept count mismatch: $ACTUAL folders vs $EXPECTED expected in departments.json"; FAIL=$((FAIL+1))
    FAILURES+=("2.1|Dept count mismatch|Re-run Skill 23 or verify departments.json is fresh")
  fi
else
  red "  ✗ 2.1  departments.json missing"; FAIL=$((FAIL+1))
  FAILURES+=("2.1|departments.json missing|Re-run Skill 23 build phase")
fi
# 2.2 — directors per dept
check "2.2" "Each dept has a director subfolder (00-*/)" \
  "[ -d \"$COMPANY_DIR/departments\" ] && [ \$(find \"$COMPANY_DIR/departments\" -maxdepth 2 -type d -name '00-*' | wc -l) -gt 0 ]" \
  "Re-run build-workforce.py; create_role_workspace() failed"
# 2.3 — symlink check
if [ -d "$COMPANY_DIR/departments" ]; then
  COPIED=$(find "$COMPANY_DIR/departments" -maxdepth 2 -type f \( -name "AGENTS.md" -o -name "TOOLS.md" -o -name "USER.md" \) 2>/dev/null | wc -l | tr -d ' ')
  SYMLINKED=$(find "$COMPANY_DIR/departments" -maxdepth 2 -type l \( -name "AGENTS.md" -o -name "TOOLS.md" -o -name "USER.md" \) 2>/dev/null | wc -l | tr -d ' ')
  if [ "$COPIED" = "0" ] && [ "$SYMLINKED" -gt 0 ]; then
    green "  ✓ 2.3  AGENTS/TOOLS/USER.md SYMLINKED ($SYMLINKED) — none copied"; PASS=$((PASS+1))
  elif [ "$COPIED" -gt 0 ] && [ "$SYMLINKED" = "0" ]; then
    red "  ✗ 2.3  AGENTS/TOOLS/USER.md COPIED ($COPIED) — should be symlinked (pre-v9.6.1 bug)"; FAIL=$((FAIL+1))
    FAILURES+=("2.3|Files copied instead of symlinked|Re-run build-workforce.py — v9.6.1+ uses symlinks")
  elif [ "$COPIED" = "0" ] && [ "$SYMLINKED" = "0" ]; then
    yellow "  ⚠ 2.3  No AGENTS/TOOLS/USER.md found in any dept (build may be incomplete)"; WARN=$((WARN+1))
  else
    yellow "  ⚠ 2.3  Mixed: $SYMLINKED symlinked, $COPIED copied (drift detected)"; WARN=$((WARN+1))
    WARNINGS+=("2.3|Mixed symlinks and copies|Delete the copies, re-run build")
  fi
else
  yellow "  ⚠ 2.3  No departments folder to check"; WARN=$((WARN+1))
fi
# 2.4 — dept directors in agents.list[]
DIR_AGENTS=$(python3 -c "import json; cfg=json.load(open('$OCJSON')); print(sum(1 for a in cfg.get('agents',{}).get('list',[]) if a.get('id','').startswith('dept-')))" 2>/dev/null)
if [ -n "$DIR_AGENTS" ] && [ "$DIR_AGENTS" -gt 0 ]; then
  green "  ✓ 2.4  $DIR_AGENTS department director agents in agents.list[]"; PASS=$((PASS+1))
else
  red "  ✗ 2.4  No dept director agents in agents.list[]"; FAIL=$((FAIL+1))
  FAILURES+=("2.4|No dept agents in config|Re-run build-workforce.py add_agent_to_config()")
fi
# 2.5 — canonical sub-agent config on every dept agent
BAD_CONFIG=$(python3 -c "
import json
cfg=json.load(open('$OCJSON'))
bad=[]
for a in cfg.get('agents',{}).get('list',[]):
    if a.get('id','').startswith('dept-'):
        s=a.get('subagents',{})
        if (a.get('bootstrapMaxChars') != 200000 or
            a.get('bootstrapTotalMaxChars') != 400000 or
            s.get('maxChildrenPerAgent') != 20 or
            s.get('maxConcurrent') != 100 or
            s.get('maxSpawnDepth') != 5 or
            s.get('thinking') != 'high' or
            s.get('allowAgents') != ['*']):
            bad.append(a['id'])
print(len(bad), '|', ','.join(bad[:5]))
" 2>/dev/null)
BAD_COUNT=$(echo "$BAD_CONFIG" | cut -d'|' -f1 | tr -d ' ')
if [ "$BAD_COUNT" = "0" ]; then
  green "  ✓ 2.5  All dept directors have canonical sub-agent + bootstrap config"; PASS=$((PASS+1))
else
  red "  ✗ 2.5  $BAD_COUNT dept director(s) missing canonical config: $(echo "$BAD_CONFIG" | cut -d'|' -f2)"; FAIL=$((FAIL+1))
  FAILURES+=("2.5|Missing canonical config|Re-run build-workforce.py — v9.6.1+ propagates correct fields")
fi
# 2.6 — SOPs not stubs
if [ -d "$COMPANY_DIR/departments" ]; then
  STUBS=$(grep -rl "to be personalized based on research" "$COMPANY_DIR/departments" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$STUBS" = "0" ]; then
    green "  ✓ 2.6  No SOP stubs remaining (all populated)"; PASS=$((PASS+1))
  else
    yellow "  ⚠ 2.6  $STUBS SOP file(s) still contain stub placeholders"; WARN=$((WARN+1))
    WARNINGS+=("2.6|$STUBS SOPs are stubs|Run populate-sops-from-manifest.py")
  fi
fi
# 2.7 — "no guessing" rule
if [ -d "$COMPANY_DIR/departments" ]; then
  SOPS_TOTAL=$(find "$COMPANY_DIR/departments" -type f -name "0[1-9]-*.md" | wc -l | tr -d ' ')
  SOPS_WITH_RULE=$(grep -l "DO NOT GUESS\|Guessing is forbidden\|no guessing" "$COMPANY_DIR/departments"/*/*/0[1-9]-*.md 2>/dev/null | wc -l | tr -d ' ')
  if [ "$SOPS_TOTAL" -gt 0 ] && [ "$SOPS_WITH_RULE" = "$SOPS_TOTAL" ]; then
    green "  ✓ 2.7  All $SOPS_TOTAL SOPs contain the 'no guessing' rule"; PASS=$((PASS+1))
  elif [ "$SOPS_TOTAL" = "0" ]; then
    yellow "  ⚠ 2.7  No SOPs found to check"; WARN=$((WARN+1))
  else
    yellow "  ⚠ 2.7  Only $SOPS_WITH_RULE / $SOPS_TOTAL SOPs contain the rule"; WARN=$((WARN+1))
    WARNINGS+=("2.7|Some SOPs missing no-guessing rule|Re-run populate-sops-from-manifest.py")
  fi
fi
check "2.9" "Devil's Advocate per dept" \
  "[ \$(find \"$COMPANY_DIR/departments\" -type f -path '*/devils-advocate/SOP.md' 2>/dev/null | wc -l) -gt 0 ]" \
  "Re-run build-workforce.py — DA auto-creation step failed"
check "2.10" "ORG-CHART.md at company root" \
  "[ -f \"$COMPANY_DIR/ORG-CHART.md\" ]" \
  "Re-run generate_org_chart() in build-workforce.py"

# ─── CHECK 3: Book-to-Persona ────────────────────────────────────────────────
echo
blue "── CHECK 3: Book-to-Persona (Skill 22) ──"
PERSONA_DIR=$MASTER/coaching-personas/personas
check "3.1" "persona-blueprint.md present in at least one persona folder" \
  "[ -d \"$PERSONA_DIR\" ] && [ \$(find \"$PERSONA_DIR\" -name 'persona-blueprint.md' | wc -l) -gt 0 ]" \
  "Run Skill 22 pipeline on at least one book"
check "3.5" "persona-categories.json present + valid JSON" \
  "python3 -c 'import json; json.load(open(\"$MASTER/coaching-personas/persona-categories.json\"))'" \
  "Re-run gemini-indexer.py or rebuild Skill 22"
warn_check "3.6" "No stale Kimi 2.5 / DeepSeek 3.2 / GPT-5.3 hardwires in Skill 22" \
  "! grep -q 'moonshot/kimi-k2.5\\|deepseek/deepseek-v3.2\\|gpt-5.3-codex' $HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/_meta.json 2>/dev/null" \
  "Re-apply v9.5.0+ skill 22 _meta.json"
warn_check "3.7" "No Anthropic refs in Skill 22 active code" \
  "! grep -rn 'anthropic/\\|claude-opus\\|claude-sonnet' $HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/*.py 2>/dev/null" \
  "Manual review of orchestrator.py imports + calls"

# ─── CHECK 4: Gemini Engine ──────────────────────────────────────────────────
echo
blue "── CHECK 4: Gemini Embeddings 2 (Skill 31) ──"
GEMINI_INDEXER=""
for c in "$WORKSPACE/scripts/gemini-indexer.py" "$HOME/.openclaw/workspace/scripts/gemini-indexer.py"; do
  [ -f "$c" ] && GEMINI_INDEXER="$c" && break
done
GEMINI_SEARCH=""
for c in "$WORKSPACE/scripts/gemini-search.py" "$HOME/.openclaw/workspace/scripts/gemini-search.py"; do
  [ -f "$c" ] && GEMINI_SEARCH="$c" && break
done
check "4.1" "gemini-indexer.py present" \
  "[ -n \"$GEMINI_INDEXER\" ]" \
  "Re-run install.sh Step 6 — Gemini scripts copy"
check "4.2" "gemini-search.py present" \
  "[ -n \"$GEMINI_SEARCH\" ]" \
  "Same — re-run install Step 6"
if [ -n "$GEMINI_INDEXER" ]; then
  warn_check "4.3" "gemini-indexer --status returns a coaching-personas collection" \
    "python3 \"$GEMINI_INDEXER\" --status 2>/dev/null | grep -qi 'coaching-personas'" \
    "Run: python3 $GEMINI_INDEXER  (full index)"
  warn_check "4.4" "clawd workspace collection indexed" \
    "python3 \"$GEMINI_INDEXER\" --status 2>/dev/null | grep -qi 'clawd'" \
    "Run: python3 $GEMINI_INDEXER"
fi

# ─── CHECK 5: Semantic Search (runtime persona selector) ─────────────────────
echo
blue "── CHECK 5: Semantic Search ──"
SELECTOR=$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/select-persona-for-task.py
check "5.1" "select-persona-for-task.py present + executable" \
  "[ -x \"$SELECTOR\" ]" \
  "Re-run update-skills.sh --only 23"
if [ -x "$SELECTOR" ] && [ -n "$COMPANY_DIR" ]; then
  warn_check "5.2" "Test selector invocation returns a persona id" \
    "python3 \"$SELECTOR\" --dept marketing --task 'Write a launch email' --format id 2>/dev/null | grep -q ." \
    "Check governing-personas.md in marketing dept; ensure persona-categories.json valid"
fi

# ─── CHECK 6: Keyword Search ─────────────────────────────────────────────────
echo
blue "── CHECK 6: Keyword Search ──"
warn_check "6.1" "persona-categories.json has domain_tags fields" \
  "python3 -c 'import json; d=json.load(open(\"$MASTER/coaching-personas/persona-categories.json\")); p=d.get(\"personas\",d); print(any((v.get(\"domain_tags\") or v.get(\"tags\")) for v in p.values()))' 2>/dev/null | grep -q True" \
  "Re-tag personas via Skill 22 indexing"

# ─── CHECK 7: Task Assignments / Kanban ──────────────────────────────────────
echo
blue "── CHECK 7: Task Assignments (Kanban / Command Center) ──"
CC_DB=""
for c in "$HOME/projects/command-center/mission-control.db" "$HOME/projects/mission-control/mission-control.db" "/opt/mission-control/mission-control.db"; do
  [ -f "$c" ] && CC_DB="$c" && break
done
if [ -n "$CC_DB" ]; then
  green "  ✓ 7.0  Mission Control DB present at $CC_DB"; PASS=$((PASS+1))
  # 7.1 — dept count in DB matches departments.json
  if [ -f "$COMPANY_DIR/departments.json" ]; then
    JSON_COUNT=$(python3 -c "import json; print(len(json.load(open('$COMPANY_DIR/departments.json'))))" 2>/dev/null)
    SLUG=$(basename "$COMPANY_DIR")
    DB_COUNT=$(sqlite3 "$CC_DB" "SELECT COUNT(*) FROM workspaces WHERE company_id='$SLUG'" 2>/dev/null)
    if [ -n "$DB_COUNT" ] && [ "$DB_COUNT" = "$JSON_COUNT" ]; then
      green "  ✓ 7.1  Kanban dept count ($DB_COUNT) matches departments.json ($JSON_COUNT)"; PASS=$((PASS+1))
    else
      red "  ✗ 7.1  Kanban dept count $DB_COUNT vs departments.json $JSON_COUNT — MISMATCH"; FAIL=$((FAIL+1))
      FAILURES+=("7.1|Kanban count mismatch|Re-run python3 32-command-center-setup/scripts/seed-workspaces.py")
    fi
    # 7.2 — brand colors in companies.config
    BRAND=$(sqlite3 "$CC_DB" "SELECT config FROM companies WHERE slug='$SLUG'" 2>/dev/null)
    if echo "$BRAND" | grep -q '"primary"'; then
      green "  ✓ 7.2  Brand colors present in companies.config"; PASS=$((PASS+1))
    else
      yellow "  ⚠ 7.2  No brand colors in DB (will use neutral defaults)"; WARN=$((WARN+1))
      WARNINGS+=("7.2|No brand colors|Re-run seed-workspaces.py with COMPANY_BRAND_COLORS env var")
    fi
  fi
else
  yellow "  ⚠ 7.0  Mission Control DB not found — Skill 32 may not be installed"; WARN=$((WARN+1))
fi
warn_check "7.5" "Kanban dashboard reachable at localhost:4000" \
  "[ \"\$(curl -s -o /dev/null -w '%{http_code}' http://localhost:4000 2>/dev/null)\" = '200' ]" \
  "Check pm2: pm2 list | grep command-center"

# ─── CHECK 8: Persona Assignments ────────────────────────────────────────────
echo
blue "── CHECK 8: Persona Assignments ──"
check "8.1" "governing-personas.md present per dept" \
  "[ \$(find \"$COMPANY_DIR/departments\" -name 'governing-personas.md' 2>/dev/null | wc -l) -gt 0 ]" \
  "Re-run build-workforce.py create_governing_personas_md()"
check "8.2" "persona-matrix.md at company root" \
  "[ -f \"$COMPANY_DIR/persona-matrix.md\" ]" \
  "Re-run build-workforce.py generate_persona_matrix()"

# ─── CHECK 9: Agent Linking ──────────────────────────────────────────────────
echo
blue "── CHECK 9: Agent Linking ──"
BAD_WS=$(python3 -c "
import json, os
cfg=json.load(open('$OCJSON'))
bad=[]
for a in cfg.get('agents',{}).get('list',[]):
    if a.get('id','').startswith('dept-'):
        ws=a.get('workspace','')
        if not os.path.isdir(ws):
            bad.append(a['id'])
print(len(bad))
" 2>/dev/null)
if [ "$BAD_WS" = "0" ]; then
  green "  ✓ 9.2  All dept-* agents point at existing workspace dirs"; PASS=$((PASS+1))
else
  red "  ✗ 9.2  $BAD_WS dept-* agent(s) have stale workspace paths"; FAIL=$((FAIL+1))
  FAILURES+=("9.2|Stale workspaces|Re-run Skill 23 build")
fi
check "9.8" "Master AGENTS.md / TOOLS.md / USER.md exist at workspace root" \
  "[ -f \"$WORKSPACE/AGENTS.md\" ] && [ -f \"$WORKSPACE/TOOLS.md\" ] && [ -f \"$WORKSPACE/USER.md\" ]" \
  "Bootstrap missing — re-run install.sh"

# ─── CROSS-CUTTING ───────────────────────────────────────────────────────────
echo
blue "── CROSS-CUTTING ──"
check "X.2" "Bootstrap limits canonical (200K / 400K)" \
  "[ \"\$(python3 -c 'import json; c=json.load(open(\"$OCJSON\")); print(c[\"agents\"][\"defaults\"][\"bootstrapMaxChars\"], c[\"agents\"][\"defaults\"][\"bootstrapTotalMaxChars\"])' 2>/dev/null)\" = '200000 400000' ]" \
  "Re-run install.sh Step 0"

# ─── SUMMARY ─────────────────────────────────────────────────────────────────
echo
blue "═══════════════════════════════════════════════════"
blue "  SUMMARY"
blue "═══════════════════════════════════════════════════"
echo "  Passed:   $PASS"
[ "$WARN" -gt 0 ] && yellow "  Warnings: $WARN" || echo "  Warnings: $WARN"
[ "$FAIL" -gt 0 ] && red "  Failures: $FAIL" || echo "  Failures: $FAIL"
echo

if [ "$FAIL" -gt 0 ]; then
  red "FAILURE DETAILS:"
  for f in "${FAILURES[@]}"; do
    id=$(echo "$f" | cut -d'|' -f1)
    desc=$(echo "$f" | cut -d'|' -f2)
    remedy=$(echo "$f" | cut -d'|' -f3)
    echo "  [$id] $desc"
    [ -n "$remedy" ] && echo "       → $remedy"
  done
  echo
fi

if [ "$WARN" -gt 0 ]; then
  yellow "WARNING DETAILS:"
  for w in "${WARNINGS[@]}"; do
    id=$(echo "$w" | cut -d'|' -f1)
    desc=$(echo "$w" | cut -d'|' -f2)
    remedy=$(echo "$w" | cut -d'|' -f3)
    echo "  [$id] $desc"
    [ -n "$remedy" ] && echo "       → $remedy"
  done
  echo
fi

if [ "$FAIL" -eq 0 ]; then
  green "ALL CHECKS PASSED ✓"
  exit 0
else
  red "SYSTEM INTEGRITY: FAIL"
  echo "See SYSTEM-DIAGNOSTIC-CHECKLIST.md for full remediation recipes."
  exit 1
fi

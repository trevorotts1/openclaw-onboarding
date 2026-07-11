#!/bin/bash
# qc-system-integrity.sh — v9.6.2
#
# Executable runner for SYSTEM-DIAGNOSTIC-CHECKLIST.md.
# Runs the 9 check sections + cross-cutting checks. Exits 0 only when all green.
#
# Categories: 1=Interview, 2=Workforce, 3=Book-to-Persona, 4=Gemini, 5=Semantic,
#             6=Keyword, 7=Tasks/Kanban, 8=Persona, 9=Agent linking, X=Cross-cutting.
# Cross-cutting (X): X.7=PRD-1.10 migration, X.8=provider-capability invariants,
#             X.9=Ollama provider platform standard (Mac local daemon vs VPS cloud).

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

# PRD 2.7: canonical coaching-personas workspace (workspace/data/coaching-personas/).
# ~/.openclaw/workspace is the runtime workspace on new Mac installs; /data/.openclaw/workspace on VPS.
if [ -d "/data/.openclaw/workspace" ]; then
  PC_WORKSPACE="/data/.openclaw/workspace"
elif [ -d "$HOME/.openclaw/workspace" ]; then
  PC_WORKSPACE="$HOME/.openclaw/workspace"
else
  PC_WORKSPACE="$WORKSPACE"
fi
PC_DIR="$PC_WORKSPACE/data/coaching-personas"

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
  "grep -q '## AI Workforce Build' \"$WORKSPACE/MEMORY.md\"" \
  "Re-apply Skill 23 CORE_UPDATES.md to your MEMORY.md"

# ─── CHECK 2: AI Workforce Skill Set (build phase) ───────────────────────────
echo
blue "── CHECK 2: AI Workforce Skill Set (build phase) ──"
# 2.1 — dept count match
if [ -f "$COMPANY_DIR/departments.json" ]; then
  # H2: inject path via env var so a quote in the directory name can't break the Python string literal
  EXPECTED=$(DEPT_JSON="$COMPANY_DIR/departments.json" python3 -c "import json,os; print(len(json.load(open(os.environ['DEPT_JSON']))))" 2>/dev/null)
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
# H2: inject via env var — OCJSON path must not be shell-expanded inside a Python string literal
DIR_AGENTS=$(OC_JSON="$OCJSON" python3 -c "import json,os; cfg=json.load(open(os.environ['OC_JSON'])); print(sum(1 for a in cfg.get('agents',{}).get('list',[]) if a.get('id','').startswith('dept-')))" 2>/dev/null)
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

# v10.15.4 / v10.16.4 — sections 2.11-2.14: role-library materialization coverage.
# These sections close the silent-failure gap discovered during the 5-client audit
# (one client 1/222, one client 146 thin, one client legacy-tree, one client 0 SOPs, one client crash).
# All checks are best-effort — they WARN rather than FAIL so the existing
# integrity gate is not over-tightened. The dedicated qc-completeness.sh script
# is the authoritative gate for "are you done?"
LIB_INDEX="$HOME/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"
[ -f "/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json" ] && \
  LIB_INDEX="/data/.openclaw/skills/23-ai-workforce-blueprint/templates/role-library/_index.json"

# 2.11 — per-dept role-folder count vs library expected
if [ -d "$COMPANY_DIR/departments" ] && [ -f "$LIB_INDEX" ]; then
  ROLE_COVERAGE=$(python3 - <<PYEOF 2>/dev/null
import json, os
from pathlib import Path
idx = json.load(open("$LIB_INDEX"))
expected = idx.get("departments", {})
total_exp = 0
total_have = 0
gaps = []
for dept_dir in sorted(Path("$COMPANY_DIR/departments").iterdir()):
    if not dept_dir.is_dir() or dept_dir.name.startswith(("_", ".")):
        continue
    exp = expected.get(dept_dir.name, {}).get("role_count", 0)
    have = sum(1 for r in dept_dir.iterdir() if r.is_dir() and not r.name.startswith(("_", ".")))
    total_exp += exp
    total_have += have
    if exp and have / exp < 0.75:
        gaps.append(f"{dept_dir.name}={have}/{exp}")
pct = round(100.0 * total_have / total_exp, 1) if total_exp else 0.0
print(f"{pct}|{total_have}|{total_exp}|" + ",".join(gaps[:5]))
PYEOF
)
  PCT=$(echo "$ROLE_COVERAGE" | cut -d'|' -f1)
  GAPS=$(echo "$ROLE_COVERAGE" | cut -d'|' -f4)
  if python3 -c "import sys; sys.exit(0 if float('$PCT') >= 75 else 1)" 2>/dev/null; then
    green "  ✓ 2.11 Role-library materialization ${PCT}% (>= 75% threshold)"; PASS=$((PASS+1))
  else
    yellow "  ⚠ 2.11 Role-library materialization ${PCT}% (gaps: ${GAPS:-N/A})"; WARN=$((WARN+1))
    WARNINGS+=("2.11|role-library ${PCT}%|Run qc-completeness.sh for full breakdown then migrate-existing-workforce.sh")
  fi
fi

# 2.12 — per-dept library-fill provenance marker count
if [ -d "$COMPANY_DIR/departments" ]; then
  LIB_FILLED=$(grep -rl "<!-- Filled from role-library v" "$COMPANY_DIR/departments" 2>/dev/null | wc -l | tr -d ' ')
  ROLE_FOLDERS=$(find "$COMPANY_DIR/departments" -mindepth 2 -maxdepth 2 -type d \! -name "_*" \! -name ".*" 2>/dev/null | wc -l | tr -d ' ')
  if [ "$ROLE_FOLDERS" -gt 0 ]; then
    PCT_LIB=$(python3 -c "print(round(100.0 * $LIB_FILLED / $ROLE_FOLDERS, 1))" 2>/dev/null)
    if python3 -c "import sys; sys.exit(0 if float('${PCT_LIB:-0}') >= 75 else 1)" 2>/dev/null; then
      green "  ✓ 2.12 how-to.md library provenance ${LIB_FILLED}/${ROLE_FOLDERS} (${PCT_LIB}%)"; PASS=$((PASS+1))
    else
      yellow "  ⚠ 2.12 how-to.md library provenance ${LIB_FILLED}/${ROLE_FOLDERS} (${PCT_LIB}%)"; WARN=$((WARN+1))
      WARNINGS+=("2.12|library-fill ${PCT_LIB}%|Re-run post-build-role-workspaces.py")
    fi
  fi
fi

# 2.13 — IDENTITY.md per role folder
if [ -d "$COMPANY_DIR/departments" ]; then
  ID_COUNT=$(find "$COMPANY_DIR/departments" -mindepth 3 -maxdepth 3 -type f -name "IDENTITY.md" 2>/dev/null | wc -l | tr -d ' ')
  ROLE_FOLDERS=${ROLE_FOLDERS:-$(find "$COMPANY_DIR/departments" -mindepth 2 -maxdepth 2 -type d \! -name "_*" \! -name ".*" 2>/dev/null | wc -l | tr -d ' ')}
  if [ "$ROLE_FOLDERS" -gt 0 ]; then
    PCT_ID=$(python3 -c "print(round(100.0 * $ID_COUNT / $ROLE_FOLDERS, 1))" 2>/dev/null)
    if python3 -c "import sys; sys.exit(0 if float('${PCT_ID:-0}') >= 95 else 1)" 2>/dev/null; then
      green "  ✓ 2.13 IDENTITY.md per role ${ID_COUNT}/${ROLE_FOLDERS} (${PCT_ID}%)"; PASS=$((PASS+1))
    else
      yellow "  ⚠ 2.13 IDENTITY.md per role ${ID_COUNT}/${ROLE_FOLDERS} (${PCT_ID}%)"; WARN=$((WARN+1))
      WARNINGS+=("2.13|IDENTITY.md ${PCT_ID}%|Re-run post-build-role-workspaces.py")
    fi
  fi
fi

# 2.14 — legacy tree detection (misrouted workspace tree pattern)
LEGACY_FOUND=""
for cand in /data/clawd/departments "$HOME/clawd/departments"; do
  if [ -d "$cand" ]; then
    # Compare with workspace departments dir; if different paths, flag.
    if [ -n "$COMPANY_DIR" ]; then
      CANON_DEPT=$(cd "$COMPANY_DIR/departments" 2>/dev/null && pwd -P)
      CANON_CAND=$(cd "$cand" 2>/dev/null && pwd -P)
      if [ -n "$CANON_CAND" ] && [ "$CANON_CAND" != "$CANON_DEPT" ]; then
        LEGACY_FOUND="${LEGACY_FOUND}${cand} "
      fi
    fi
  fi
done
if [ -z "$LEGACY_FOUND" ]; then
  green "  ✓ 2.14 No legacy /clawd/departments tree present"; PASS=$((PASS+1))
else
  yellow "  ⚠ 2.14 Legacy tree(s) present: ${LEGACY_FOUND}— content may be stranded"; WARN=$((WARN+1))
  WARNINGS+=("2.14|legacy tree ${LEGACY_FOUND}|Run reconcile-legacy-tree.py from Release 2 (v10.15.5/v10.16.5)")
fi

# ─── CHECK 3: Book-to-Persona ────────────────────────────────────────────────
echo
blue "── CHECK 3: Book-to-Persona (Skill 22) ──"
# PRD 2.7: persona-categories.json canonical path is PC_DIR (workspace/data/coaching-personas/).
# The skill-folder copy is the shipped seed (READ-ONLY); check that the canonical one exists.
check "3.0" "persona-categories.json canonical dir resolves (PRD 2.7)" \
  "[ -d \"$PC_DIR\" ] || { mkdir -p \"$PC_DIR\" && echo 'created'; }" \
  "Skill 22 orchestrator creates this on first run; no action needed pre-install."
PERSONA_DIR=$PC_DIR/personas
check "3.1" "persona-blueprint.md present in at least one persona folder" \
  "[ -d \"$PERSONA_DIR\" ] && [ \$(find \"$PERSONA_DIR\" -name 'persona-blueprint.md' | wc -l) -gt 0 ]" \
  "Run Skill 22 pipeline on at least one book"
check "3.5" "persona-categories.json present + valid JSON (canonical: workspace/data/coaching-personas/)" \
  "python3 -c 'import json; json.load(open(\"$PC_DIR/persona-categories.json\"))' 2>/dev/null || python3 -c 'import json; json.load(open(\"$MASTER/coaching-personas/persona-categories.json\"))'" \
  "Run Skill 22 orchestrator at least once to seed canonical path $PC_DIR/persona-categories.json"
warn_check "3.6" "No stale Kimi 2.5 / DeepSeek 3.2 / GPT-5.3 hardwires in Skill 22" \
  "! grep -q 'moonshot/kimi-k2.6\\|deepseek/deepseek-v3.2\\|gpt-5.3-codex' $HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/_meta.json 2>/dev/null" \
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
SELECTOR=$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/persona-selector-v2.py
check "5.1" "persona-selector-v2.py present + executable (canonical selector)" \
  "[ -x \"$SELECTOR\" ]" \
  "Re-run update-skills.sh --only 23"
if [ -x "$SELECTOR" ] && [ -n "$COMPANY_DIR" ]; then
  warn_check "5.2" "Test selector invocation returns a persona id" \
    "python3 \"$SELECTOR\" --department marketing --task 'Write a launch email' --format json 2>/dev/null | python3 -c 'import sys,json; r=json.load(sys.stdin); sys.exit(0 if r.get(\"persona_id\") else 1)'" \
    "Check governing-personas.md in marketing dept; ensure persona-categories.json valid"
fi
# Legacy shim check: select-persona-for-task.py must redirect to v2, not stand alone
LEGACY_SELECTOR=$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/select-persona-for-task.py
if [ -f "$LEGACY_SELECTOR" ]; then
  check "5.1a" "select-persona-for-task.py is a shim (not the original v1)" \
    "grep -q 'DEPRECATED SHIM' \"$LEGACY_SELECTOR\" || grep -q 'persona-selector-v2' \"$LEGACY_SELECTOR\"" \
    "select-persona-for-task.py should delegate to persona-selector-v2.py; see archive/README.md"
fi

# ─── CHECK 6: Keyword Search ─────────────────────────────────────────────────
echo
blue "── CHECK 6: Keyword Search ──"
warn_check "6.1" "persona-categories.json has domain_tags fields (canonical path)" \
  "python3 -c '
import json, sys
for p in [\"$PC_DIR/persona-categories.json\", \"$MASTER/coaching-personas/persona-categories.json\"]:
    try:
        d=json.load(open(p)); personas=d.get(\"personas\",d)
        if any((v.get(\"domain_tags\") or v.get(\"domain\") or v.get(\"tags\")) for v in personas.values() if isinstance(v,dict)):
            sys.exit(0)
    except: pass
sys.exit(1)
' 2>/dev/null" \
  "Re-tag personas via Skill 22 indexing; canonical file at $PC_DIR/persona-categories.json"

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
    # H2: inject path via env var
    JSON_COUNT=$(DEPT_JSON="$COMPANY_DIR/departments.json" python3 -c "import json,os; print(len(json.load(open(os.environ['DEPT_JSON']))))" 2>/dev/null)
    SLUG=$(basename "$COMPANY_DIR")
    # H1: escape single-quotes in SLUG before interpolating into sqlite3 query string
    SLUG_ESC="${SLUG//\'/\'\'}"
    DB_COUNT=$(sqlite3 "$CC_DB" "SELECT COUNT(*) FROM workspaces WHERE company_id='${SLUG_ESC}'" 2>/dev/null)
    if [ -n "$DB_COUNT" ] && [ "$DB_COUNT" = "$JSON_COUNT" ]; then
      green "  ✓ 7.1  Kanban dept count ($DB_COUNT) matches departments.json ($JSON_COUNT)"; PASS=$((PASS+1))
    else
      red "  ✗ 7.1  Kanban dept count $DB_COUNT vs departments.json $JSON_COUNT — MISMATCH"; FAIL=$((FAIL+1))
      FAILURES+=("7.1|Kanban count mismatch|Re-run python3 32-command-center-setup/scripts/seed-workspaces.py")
    fi
    # 7.2 — brand colors in companies.config
    BRAND=$(sqlite3 "$CC_DB" "SELECT config FROM companies WHERE slug='${SLUG_ESC}'" 2>/dev/null)
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

# 9.9 (v10.15.51) — Shared core-file unification (Zero-Human-Workforce file model):
# every non-workflow-agent workspace's AGENTS.md / TOOLS.md / USER.md MUST be a
# symlink resolving to THIS box's canonical (agents.defaults.workspace). Per-agent
# IDENTITY/SOUL/MEMORY/HEARTBEAT are NOT checked here (they stay each agent's own).
# Nested workflow agents (*/workflows/*/agents/*) are EXEMPT. The expected target is
# resolved from THIS box's own openclaw.json — never a foreign/hardcoded path.
UNIFY_BAD=$(OCJSON="$OCJSON" python3 - <<'PYEOF' 2>/dev/null || echo "ERR"
import json, os
ocjson = os.environ["OCJSON"]
try:
    cfg = json.load(open(ocjson))
except Exception:
    print("ERR"); raise SystemExit
agents = cfg.get("agents", {})

# CANON_DIR = box's own default agent workspace (per-agent main override ->
# agents.defaults.workspace), resolved to a real path.
canon = ""
for ag in agents.get("list", []) or []:
    if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
        canon = os.path.expanduser(ag["workspace"]); break
if not canon:
    ws = agents.get("defaults", {}).get("workspace")
    if ws:
        canon = os.path.expanduser(ws)
if not canon:
    canon = "/data/.openclaw/workspace" if os.path.isdir("/data/.openclaw") else os.path.expanduser("~/.openclaw/workspace")
canon_real = os.path.realpath(canon)

# Enumerate candidate agent workspaces: openclaw.json agents[].workspace plus a
# scan of the workspace's agents/ + departments/ trees.
cands = set()
for ag in agents.get("list", []) or []:
    if isinstance(ag, dict) and ag.get("workspace"):
        cands.add(os.path.expanduser(ag["workspace"]))
for sub in ("agents", "departments"):
    base = os.path.join(canon_real, sub)
    if os.path.isdir(base):
        for root, dirs, files in os.walk(base):
            if os.path.exists(os.path.join(root, "AGENTS.md")) \
               or os.path.exists(os.path.join(root, "IDENTITY.md")) \
               or os.path.exists(os.path.join(root, "SOUL.md")):
                cands.add(root)

bad = []
for w in cands:
    wr = os.path.realpath(w)
    if wr == canon_real:
        continue
    # NESTED WORKFLOW AGENT EXEMPTION.
    if "/workflows/" in (wr + "/") and "/agents/" in (wr + "/").split("/workflows/", 1)[1]:
        continue
    for f in ("AGENTS.md", "TOOLS.md", "USER.md"):
        p = os.path.join(wr, f)
        if not os.path.exists(p):
            continue  # absent is allowed (left absent by the unifier)
        if not os.path.islink(p):
            bad.append("%s/%s NOT a symlink" % (wr, f)); continue
        if os.path.realpath(p) != os.path.join(canon_real, f):
            bad.append("%s/%s -> %s (expected canonical)" % (wr, f, os.path.realpath(p)))
print(len(bad))
for b in bad[:10]:
    print("    "+b)
PYEOF
)
UNIFY_COUNT=$(printf '%s\n' "$UNIFY_BAD" | head -1)
if [ "$UNIFY_COUNT" = "0" ]; then
  green "  ✓ 9.9  All non-workflow-agent workspaces share AGENTS/TOOLS/USER via canonical symlink"; PASS=$((PASS+1))
elif [ "$UNIFY_COUNT" = "ERR" ]; then
  warn_check "9.9" "Shared core-file unification (could not read openclaw.json — skipped)" "false" \
    "openclaw.json unreadable; re-run after install completes"
else
  red "  ✗ 9.9  $UNIFY_COUNT non-workflow-agent core file(s) not symlinked to canonical:"; FAIL=$((FAIL+1))
  printf '%s\n' "$UNIFY_BAD" | tail -n +2
  FAILURES+=("9.9|Shared core files not unified (AGENTS/TOOLS/USER must symlink to canonical workspace)|Run link_shared_core_files (re-run update-skills.sh or install.sh Step 10a)")
fi

# ─── CROSS-CUTTING ───────────────────────────────────────────────────────────
echo
blue "── CROSS-CUTTING ──"
check "X.2" "Bootstrap limits canonical (200K / 400K)" \
  "[ \"\$(python3 -c 'import json; c=json.load(open(\"$OCJSON\")); print(c[\"agents\"][\"defaults\"][\"bootstrapMaxChars\"], c[\"agents\"][\"defaults\"][\"bootstrapTotalMaxChars\"])' 2>/dev/null)\" = '200000 400000' ]" \
  "Re-run install.sh Step 0"

# ─── COACHING-PERSONAS PIPELINE INTEGRITY (P0-005 / Phase 14) ────────────────
echo
blue "── COACHING-PERSONAS PIPELINE (Phase 14) ──"

# Resolve workspace root (Mac default → VPS fallback)
WS_ROOT="${WORKSPACE_ROOT:-$HOME/.openclaw/workspace}"
[ -d "/data/.openclaw/workspace" ] && [ ! -d "$WS_ROOT" ] && WS_ROOT="/data/.openclaw/workspace"

GEMINI_INDEX_DB="$WS_ROOT/data/coaching-personas/gemini-index.sqlite"
PERSONAS_DIR="$WS_ROOT/data/coaching-personas/personas"
# PRD 2.7: canonical write target first; skill-folder copy is shipped seed (READ-ONLY).
PERSONA_CATALOG_CANDIDATES=(
  "$WS_ROOT/data/coaching-personas/persona-categories.json"
  "$HOME/.openclaw/workspace/data/coaching-personas/persona-categories.json"
  "/data/.openclaw/workspace/data/coaching-personas/persona-categories.json"
  "$HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"
  "/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/persona-categories.json"
)
PERSONA_CATALOG=""
for p in "${PERSONA_CATALOG_CANDIDATES[@]}"; do
  [ -f "$p" ] && PERSONA_CATALOG="$p" && break
done
# Warn if still resolving from skill folder (should only happen before first Skill 22 run).
if [ -n "$PERSONA_CATALOG" ] && echo "$PERSONA_CATALOG" | grep -q "22-book-to-persona"; then
  echo "  [WARN] persona-categories.json resolved from shipped skill folder (pre-Skill-22 run); canonical path: $WS_ROOT/data/coaching-personas/persona-categories.json"
fi

# X.3 — coaching-personas/ has ≥40 .md blueprint files (matches persona-categories.json catalog)
check "X.3" "coaching-personas/personas has ≥40 persona blueprints" \
  "[ -d \"$PERSONAS_DIR\" ] && [ \"\$(find \"$PERSONAS_DIR\" -maxdepth 2 -name '*.md' 2>/dev/null | wc -l | tr -d ' ')\" -ge 40 ]" \
  "Run Skill 22 pipeline on a fresh batch of source books to populate personas/, or restore from backup."

# X.4 — persona-categories.json catalog count matches on-disk personas
if [ -n "$PERSONA_CATALOG" ]; then
  check "X.4" "persona-categories.json catalog count matches on-disk personas" \
    "python3 -c '
import json, os, glob, sys
cat=json.load(open(\"$PERSONA_CATALOG\"))
cat_n=len(cat) if isinstance(cat, list) else len(cat.get(\"personas\", []))
disk_n=len([d for d in glob.glob(\"$PERSONAS_DIR/*\") if os.path.isdir(d)])
sys.exit(0 if disk_n >= cat_n else 1)
' 2>/dev/null" \
    "Catalog says one count; disk has another. Re-run Skill 22 pipeline or audit the catalog."
fi

# X.5 — gemini-index.sqlite exists and has ≥40 embedding rows from coaching-personas/
check "X.5" "gemini-index.sqlite has ≥40 embedded rows from coaching-personas/" \
  "[ -f \"$GEMINI_INDEX_DB\" ] && [ \"\$(sqlite3 \"$GEMINI_INDEX_DB\" \"SELECT COUNT(DISTINCT file_path) FROM embeddings WHERE file_path LIKE '%coaching-personas/personas/%'\" 2>/dev/null)\" -ge 40 ]" \
  "Run: python3 ~/.openclaw/skills/23-ai-workforce-blueprint/scripts/gemini-indexer.py (then verify with --status)"

# X.6 — Coaching-mode invocation smoke test (gemini-search.py returns ≥1 persona for a known query)
check "X.6" "gemini-search.py returns ≥1 persona for a known leadership query (coaching invocation smoke)" \
  "[ -f \"$GEMINI_INDEX_DB\" ] && python3 \"$WS_ROOT/scripts/gemini-search.py\" 'leadership coaching' --limit 1 2>/dev/null | grep -qE 'PERSONA:|SCORE:|KEYWORD-HITS:'" \
  "If empty: re-index. If hard-error: check google-genai or openai package install."

# ─── CHECK X.7: PRD 1.10 migration status ────────────────────────────────────
# Check whether any legacy company locations exist that have NOT been migrated.
# This is a warning (not a failure) — the system still works while legacy roots exist,
# but the operator should run the migration to silence future fallback warnings.
CANONICAL_ROOT="$MASTER/zero-human-company"
MIGRATION_LOG="$CANONICAL_ROOT/.migration-log.json"
LEGACY_WITH_COMPANIES=0
for LDIR in "$HOME/clawd/zero-human-company" "$HOME/clawd/zhc" \
            "/data/.openclaw/workspace/zero-human-company" "/data/clawd/zero-human-company" \
            "$HOME/.openclaw/workspace/zero-human-company"; do
  if [ -d "$LDIR" ] && [ "$(find "$LDIR" -maxdepth 1 -mindepth 1 -type d ! -name '.*' 2>/dev/null | wc -l | tr -d ' ')" -gt 0 ]; then
    LEGACY_WITH_COMPANIES=$((LEGACY_WITH_COMPANIES+1))
  fi
done
if [ "$LEGACY_WITH_COMPANIES" -eq 0 ]; then
  green "  ✓ X.7  No legacy ZHC company roots with un-migrated companies"; PASS=$((PASS+1))
elif [ -f "$MIGRATION_LOG" ]; then
  # H2: inject path via env var
  MIGRATED_COUNT=$(MIGRATION_LOG_PATH="$MIGRATION_LOG" python3 -c "import json,os; d=json.load(open(os.environ['MIGRATION_LOG_PATH'])); print(len([e for e in d.get('migrations',[]) if e.get('type')=='primary']))" 2>/dev/null || echo "0")
  WARNINGS+=("X.7|Legacy ZHC roots still contain ${LEGACY_WITH_COMPANIES} folder(s); ${MIGRATED_COUNT} already migrated|Run: bash ~/.openclaw/skills/scripts/migrate-zhc-to-master-files.sh --apply")
  WARN=$((WARN+1))
else
  WARNINGS+=("X.7|${LEGACY_WITH_COMPANIES} legacy ZHC root(s) with companies found — run migration|bash ~/.openclaw/skills/scripts/migrate-zhc-to-master-files.sh --dry-run  (then --apply)")
  WARN=$((WARN+1))
fi

# ─── CHECK X.8: Provider capability invariants (v12.14.0) ───────────────────
# Hard-fail: ensures no shipped config has fallback=none or multimodal.enabled=true
# against a text-only embedding provider (the silent memory-death bug class).
# Delegates to qc-assert-provider-capability-invariants.sh so the single-source-of-truth
# logic stays in that script (same logic the smoke test and CI both exercise).
echo
blue "── CHECK X.8: Provider capability invariants ──"
PROVIDER_INVARIANT_SCRIPT=""
for _pi_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-provider-capability-invariants.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-provider-capability-invariants.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-provider-capability-invariants.sh"; do
  [[ -f "$_pi_cand" ]] && PROVIDER_INVARIANT_SCRIPT="$_pi_cand" && break
done
if [[ -n "$PROVIDER_INVARIANT_SCRIPT" ]]; then
  # Run once, capture both output and exit code atomically
  _pi_tmp=$(mktemp)
  bash "$PROVIDER_INVARIANT_SCRIPT" > "$_pi_tmp" 2>&1
  PROVIDER_INVARIANT_RC=$?
  PROVIDER_INVARIANT_OUT=$(cat "$_pi_tmp"); rm -f "$_pi_tmp"
  if [[ "$PROVIDER_INVARIANT_RC" = "0" ]]; then
    green "  ✓ X.8  Provider capability invariants pass (no fallback=none, no multimodal/text-only mismatch)"; PASS=$((PASS+1))
  else
    # Extract each FATAL line as a separate named failure
    _X8_FOUND=0
    while IFS= read -r _pline; do
      case "$_pline" in
        *"I1: INVARIANT VIOLATED"*)
          red "  ✗ X.8a memorySearch.fallback=\"none\" — no fallback path on provider failure (memory silently dies)"
          FAIL=$((FAIL+1))
          FAILURES+=("X.8a|memorySearch.fallback=none — no recovery path|Set agents.defaults.memorySearch.fallback to a working text-embedding provider (e.g. openai, openrouter)")
          _X8_FOUND=1
          ;;
        *"I2: INVARIANT VIOLATED"*)
          _detail=$(printf '%s' "$_pline" | sed 's/.*I2: INVARIANT VIOLATED[^:]*: //')
          red "  ✗ X.8b multimodal.enabled=true against text-only embedding provider: $_detail"
          FAIL=$((FAIL+1))
          FAILURES+=("X.8b|multimodal.enabled=true on text-only provider: $_detail|Disable multimodal.enabled on that agent or switch to a multimodal-capable embedding provider")
          _X8_FOUND=1
          ;;
      esac
    done <<< "$PROVIDER_INVARIANT_OUT"
    # Catch any failure the pattern above missed (script exited 1 but no I1/I2 lines matched)
    if [[ "$_X8_FOUND" = "0" ]]; then
      red "  ✗ X.8  Provider capability invariant check failed (rc=$PROVIDER_INVARIANT_RC)"
      FAIL=$((FAIL+1))
      FAILURES+=("X.8|Provider capability invariant check failed|Run: bash scripts/qc-assert-provider-capability-invariants.sh for details")
    fi
  fi
else
  yellow "  ⚠ X.8  qc-assert-provider-capability-invariants.sh not found — skipping provider invariant check"
  WARN=$((WARN+1))
  WARNINGS+=("X.8|qc-assert-provider-capability-invariants.sh missing|Update openclaw-onboarding to v12.14.0+")
fi

# ─── CHECK X.9: Ollama provider platform standard (v12.21.0) ────────────────
# Hard-fail: the Ollama provider MUST match the box type.
#   Mac client → signed-in LOCAL daemon (baseUrl http://127.0.0.1:11434,
#                apiKey "ollama-local") which serves BOTH local + :cloud models.
#   VPS client → cloud-direct (baseUrl https://ollama.com + client OLLAMA_API_KEY).
#   All boxes  → no :cloud model with maxTokens > 64000.
# Delegates to qc-assert-ollama-provider-platform.sh (single-source-of-truth).
echo
blue "── CHECK X.9: Ollama provider platform standard ──"
OLLAMA_PLATFORM_SCRIPT=""
for _op_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-ollama-provider-platform.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-ollama-provider-platform.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-ollama-provider-platform.sh"; do
  [[ -f "$_op_cand" ]] && OLLAMA_PLATFORM_SCRIPT="$_op_cand" && break
done
if [[ -n "$OLLAMA_PLATFORM_SCRIPT" ]]; then
  _op_tmp=$(mktemp)
  bash "$OLLAMA_PLATFORM_SCRIPT" > "$_op_tmp" 2>&1
  OLLAMA_PLATFORM_RC=$?
  OLLAMA_PLATFORM_OUT=$(cat "$_op_tmp"); rm -f "$_op_tmp"
  if [[ "$OLLAMA_PLATFORM_RC" = "0" ]]; then
    green "  ✓ X.9  Ollama provider matches the $PLATFORM platform standard (local daemon on Mac / cloud-direct on VPS; :cloud maxTokens ≤ 64000)"; PASS=$((PASS+1))
  else
    _X9_FOUND=0
    while IFS= read -r _opline; do
      case "$_opline" in
        *"INVARIANT VIOLATED"*)
          _opdetail=$(printf '%s' "$_opline" | sed 's/.*INVARIANT VIOLATED — //')
          red "  ✗ X.9  $_opdetail"
          FAIL=$((FAIL+1))
          FAILURES+=("X.9|Ollama provider platform mismatch: $_opdetail|See docs/OLLAMA-PROVIDER-BY-PLATFORM.md — Mac=local daemon 127.0.0.1:11434/ollama-local, VPS=ollama.com+OLLAMA_API_KEY")
          _X9_FOUND=1
          ;;
      esac
    done <<< "$OLLAMA_PLATFORM_OUT"
    if [[ "$_X9_FOUND" = "0" ]]; then
      red "  ✗ X.9  Ollama provider platform check failed (rc=$OLLAMA_PLATFORM_RC)"
      FAIL=$((FAIL+1))
      FAILURES+=("X.9|Ollama provider platform check failed|Run: bash scripts/qc-assert-ollama-provider-platform.sh for details")
    fi
  fi
else
  yellow "  ⚠ X.9  qc-assert-ollama-provider-platform.sh not found — skipping Ollama platform check"
  WARN=$((WARN+1))
  WARNINGS+=("X.9|qc-assert-ollama-provider-platform.sh missing|Update openclaw-onboarding to v12.21.0+")
fi

# ─── CHECK X.10: No client names in repo files (v12.22.0) ───────────────────
# Hard-fail: real client names must NEVER appear in committed repo files.
# This repo is a fleet-wide generic template. Client-identifying strings are a
# co-mingling + privacy violation. Delegates to qc-assert-no-client-names.sh.
echo
blue "── CHECK X.10: No client names in repo files ──"
NO_CLIENT_NAMES_SCRIPT=""
for _ncn_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-no-client-names.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-no-client-names.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-no-client-names.sh"; do
  [[ -f "$_ncn_cand" ]] && NO_CLIENT_NAMES_SCRIPT="$_ncn_cand" && break
done
if [[ -n "$NO_CLIENT_NAMES_SCRIPT" ]]; then
  _ncn_tmp=$(mktemp)
  bash "$NO_CLIENT_NAMES_SCRIPT" > "$_ncn_tmp" 2>&1
  NO_CLIENT_NAMES_RC=$?
  NO_CLIENT_NAMES_OUT=$(cat "$_ncn_tmp"); rm -f "$_ncn_tmp"
  if [[ "$NO_CLIENT_NAMES_RC" = "0" ]]; then
    green "  ✓ X.10 No real client names found in tracked repo files"; PASS=$((PASS+1))
  else
    red "  ✗ X.10 Client name(s) found in repo — co-mingling/privacy violation"
    FAIL=$((FAIL+1))
    FAILURES+=("X.10|Client name(s) found in tracked repo files|Run: bash scripts/qc-assert-no-client-names.sh for the offender list, then genericize each hit")
    while IFS= read -r _ncnline; do
      case "$_ncnline" in
        *"INVARIANT VIOLATED"*) ;;  # already reported above
        "  "*)
          red "$_ncnline" ;;  # indented offender lines
      esac
    done <<< "$NO_CLIENT_NAMES_OUT"
  fi
else
  yellow "  ⚠ X.10 qc-assert-no-client-names.sh not found — skipping client-name check"
  WARN=$((WARN+1))
  WARNINGS+=("X.10|qc-assert-no-client-names.sh missing|Update openclaw-onboarding to v12.22.0+")
fi

# ─── CHECK X.11: Workspace department materialization (v12.23.0) ────────────
# Hard-fail: a required department's WORKSPACE must be MATERIALIZED, not a SHELL.
# This closes the false-"done" class where a role-library TEMPLATE was copied to
# the skills/ tree (skills/.../role-library/<dept>/) and reported "the client is
# updated / the department is installed / airtight" while the client's actual
# workspace department (workspace/zero-human-company/<company>/departments/<dept>/)
# was left an empty shell (only DREAMS.md + memory/, no role subdirs, no
# IDENTITY.md/SOUL.md, no real SOPs). "TEMPLATE DEPLOYED" and "WORKSPACE
# INSTANTIATED" are two separate states; this check verifies the WORKSPACE.
# Delegates to qc-assert-workspace-departments-built.sh (single source of truth).
#   rc=3 (AF-WORKSPACE-SHELL: a dept is SHELL/PARTIAL)       -> HARD FAIL.
#   rc=5 (AF-PHANTOM-DEPT-TREE: one canonical dept materialized
#         twice as sibling dirs, or a '.bak' dept tree on disk) -> HARD FAIL (C5).
#   rc=6 (AF-BOARD-JOIN-DRIFT: chosen != provisioned != displayed — the C-series
#         JOIN. A department the client PAID FOR with no Command Center column is a
#         department they CANNOT SEE; a ghost column has no tree behind it)
#                                                             -> HARD FAIL (C7).
#   rc=4 (no workspace / not built yet)                       -> warn (CHECK 1.1 owns it).
#   rc=2 (gate could not run)                                 -> warn.
#
# EVERY non-zero rc the delegate can return MUST have an explicit arm below. A WARN
# does NOT change this script's exit code (see the FAIL==0 -> exit 0 at the bottom),
# so any drift class that falls through to the `*)` catch-all is FAIL-OPEN: the box
# prints "ALL CHECKS PASSED" while a proven defect sits on it, mislabeled as an
# infrastructure error. When qc-assert-workspace-departments-built.sh grows a new
# rc, it gets an arm HERE in the same change — that is the contract.
echo
blue "── CHECK X.11: Workspace department materialization ──"
WORKSPACE_SHELL_SCRIPT=""
for _ws_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-workspace-departments-built.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-workspace-departments-built.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-workspace-departments-built.sh"; do
  [[ -f "$_ws_cand" ]] && WORKSPACE_SHELL_SCRIPT="$_ws_cand" && break
done
if [[ -n "$WORKSPACE_SHELL_SCRIPT" ]]; then
  _ws_tmp=$(mktemp)
  bash "$WORKSPACE_SHELL_SCRIPT" > "$_ws_tmp" 2>&1
  WORKSPACE_SHELL_RC=$?
  WORKSPACE_SHELL_OUT=$(cat "$_ws_tmp"); rm -f "$_ws_tmp"
  case "$WORKSPACE_SHELL_RC" in
    0)
      green "  ✓ X.11 All required workspace departments fully materialized (raw counts verified)"; PASS=$((PASS+1)) ;;
    3)
      red "  ✗ X.11 AF-WORKSPACE-SHELL — a required department's WORKSPACE is a SHELL/PARTIAL (template-on-disk ≠ workspace built)"
      FAIL=$((FAIL+1))
      FAILURES+=("X.11|Workspace department(s) not materialized (SHELL/PARTIAL)|Run: bash scripts/qc-assert-workspace-departments-built.sh for the per-dept raw counts, then run build-workforce.py / post-build-role-workspaces.py to instantiate the workspace")
      # surface the SHELL/PARTIAL/MISSING summary lines
      while IFS= read -r _wsline; do
        case "$_wsline" in
          *"SHELL ("*|*"PARTIAL ("*|*"MISSING ("*) red "$_wsline" ;;
        esac
      done <<< "$WORKSPACE_SHELL_OUT" ;;
    5)
      red "  ✗ X.11 AF-PHANTOM-DEPT-TREE — the same canonical department is materialized twice (phantom duplicate dept trees) or a '.bak' tree is carried as a department"
      FAIL=$((FAIL+1))
      FAILURES+=("X.11|Phantom duplicate department tree(s) on disk (two sibling dirs resolve to ONE canonical slug, and/or a '.bak' dept dir)|Run: python3 23-ai-workforce-blueprint/scripts/reconcile-legacy-tree.py --merge-duplicates (dry-run) then --merge-duplicates --apply — keeps the canonical winner, layers the loser's unique roles in, archives the loser OUT of departments/ (never deletes)")
      # surface the collision / phantom-backup lines
      while IFS= read -r _wsline; do
        case "$_wsline" in
          *"COLLISION:"*|*"PHANTOM BACKUP DIR:"*) red "$_wsline" ;;
        esac
      done <<< "$WORKSPACE_SHELL_OUT" ;;
    6)
      red "  ✗ X.11 AF-BOARD-JOIN-DRIFT — the departments the client CHOSE, the departments PROVISIONED on disk, and the departments DISPLAYED on their Command Center board do not agree"
      FAIL=$((FAIL+1))
      FAILURES+=("X.11|Board-join drift (chosen != provisioned != displayed) — a department the client paid for may have NO board column (they cannot see it), or a ghost column has no tree behind it|Run: python3 23-ai-workforce-blueprint/scripts/prove-board-join.py --json   # the full six-class diff, then: python3 32-command-center-setup/scripts/seed-workspaces.py   # re-seed the board from the chosen list")
      # surface the drift-class lines (the six classes + the named departments)
      while IFS= read -r _wsline; do
        case "$_wsline" in
          *"CHOSEN_NOT_PROVISIONED"*|*"PROVISIONED_NOT_CHOSEN"*|\
          *"CHOSEN_NOT_DISPLAYED"*|*"DISPLAYED_NOT_CHOSEN"*|\
          *"PROVISIONED_NOT_DISPLAYED"*|*"DISPLAYED_NOT_PROVISIONED"*|\
          *"CANNOT VOUCH"*) red "$_wsline" ;;
        esac
      done <<< "$WORKSPACE_SHELL_OUT" ;;
    4)
      yellow "  ⚠ X.11 No materialized workspace found yet (workforce not built — see CHECK 1.1)"; WARN=$((WARN+1))
      WARNINGS+=("X.11|No workspace departments dir resolved (workforce not built yet)|Run Skill 23 build; this becomes a hard-fail once a workspace exists") ;;
    *)
      # FAIL-CLOSED CATCH-ALL: an UNKNOWN non-zero rc is a gate this consumer has not
      # been taught. It must never be downgraded to a WARN — a WARN does not change
      # the exit code, so an untaught drift class would print "ALL CHECKS PASSED".
      # Only rc=0 is a pass; everything unrecognised and non-zero HARD-FAILS.
      if [[ "$WORKSPACE_SHELL_RC" -eq 2 ]]; then
        yellow "  ⚠ X.11 Workspace gate could not run (rc=2)"; WARN=$((WARN+1))
        WARNINGS+=("X.11|Workspace gate could not run (rc=2)|Ensure department-floor.py + prove-board-join.py + python3 are present; re-run scripts/qc-assert-workspace-departments-built.sh")
      else
        red "  ✗ X.11 Workspace gate returned an UNRECOGNISED non-zero rc=$WORKSPACE_SHELL_RC — refusing to pass on an unknown verdict"
        FAIL=$((FAIL+1))
        FAILURES+=("X.11|Unrecognised workspace-gate rc=$WORKSPACE_SHELL_RC (this consumer has not been taught this drift class)|Run: bash scripts/qc-assert-workspace-departments-built.sh to see the verdict, and add an explicit arm for rc=$WORKSPACE_SHELL_RC to CHECK X.11 in scripts/qc-system-integrity.sh")
        while IFS= read -r _wsline; do
          case "$_wsline" in
            *"INVARIANT VIOLATED"*|*"AF-"*) red "$_wsline" ;;
          esac
        done <<< "$WORKSPACE_SHELL_OUT"
      fi ;;
  esac
else
  yellow "  ⚠ X.11 qc-assert-workspace-departments-built.sh not found — skipping workspace-shell check"
  WARN=$((WARN+1))
  WARNINGS+=("X.11|qc-assert-workspace-departments-built.sh missing|Update openclaw-onboarding to v12.23.0+")
fi

# ─── CHECK X.12: Repo consistency + artifact coverage (complete check) ────────
# Hard-fail: the INSTALLED skill repo must be internally consistent across its
# six 5-dimension sources of truth (FLOOR / ROSTERS / ROLE LIBRARY / SOP SOURCE /
# PERSONA DOMAINS / no ORPHANS) AND across its DOWNSTREAM artifacts (org-chart /
# routing / command-center / dreaming / bootstrap / skills-count / version —
# v12.25.0). A client build must REFUSE to run against an inconsistent repo — six
# departments once shipped UNBUILDABLE because no gate cross-checked floor vs
# rosters; the artifact gate closes the remaining classes (a floor dept silently
# absent from the org chart / routing map / Command Center columns, a per-dept
# dreaming exclusion, a missing bootstrap template, a stale skill count, a drifted
# version marker). This runs the SAME gate as CI (qc-assert-repo-consistency.py,
# which runs BOTH gates by default) against the installed skill dir.
#   rc=0 -> consistent.  rc=5 -> CONSISTENCY drift.  rc=6 -> ARTIFACT drift.
#   rc=2 -> could not load (warn). 5 and 6 are both hard fails.
echo
blue "── CHECK X.12: Repo consistency + artifact coverage (floor/roster/library/SOP/persona + org-chart/routing/CC/dreaming/bootstrap/skills/version) ──"
CONSISTENCY_GATE=""
for _cg in \
  "$HOME/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py" \
  "/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py" \
  "$(dirname "${BASH_SOURCE[0]}")/../23-ai-workforce-blueprint/scripts/qc-assert-repo-consistency.py"; do
  [[ -f "$_cg" ]] && CONSISTENCY_GATE="$_cg" && break
done
if [[ -n "$CONSISTENCY_GATE" ]]; then
  _cg_skill_dir="$(cd "$(dirname "$CONSISTENCY_GATE")/.." && pwd)"
  _cg_tmp=$(mktemp)
  # Bare invocation runs BOTH the 5-dimension gate and the artifact-coverage gate.
  python3 "$CONSISTENCY_GATE" --skill-dir "$_cg_skill_dir" > "$_cg_tmp" 2>&1
  CONSISTENCY_RC=$?
  case "$CONSISTENCY_RC" in
    0)
      green "  ✓ X.12 Repo consistent: all floor depts aligned across floor/roster/library/SOP/persona AND every downstream artifact (org-chart/routing/CC/dreaming/bootstrap/skills/version)"; PASS=$((PASS+1)) ;;
    5)
      red "  ✗ X.12 REPO DRIFT (5-dimension) — a department/role/SOP/persona is inconsistent; a client build MUST NOT run against this repo"
      FAIL=$((FAIL+1))
      FAILURES+=("X.12|Repo consistency drift (floor x roster x library x SOP x persona)|Run: python3 $CONSISTENCY_GATE --only consistency — fix every DRIFT row (missing roster / unresolvable role / missing persona-domain mapping) before building")
      while IFS= read -r _cgl; do
        case "$_cgl" in *"[LIBRARY/SOP]"*|*"[ROSTER]"*|*"[PERSONA-DOMAIN]"*|*"[INSTANTIATE]"*|*"[SOP-SOURCE]"*|*"[ORPHAN"*) red "    $_cgl" ;; esac
      done < "$_cg_tmp" ;;
    6)
      red "  ✗ X.12 ARTIFACT DRIFT — a downstream artifact omits a floor dept, or skills/version/bootstrap disagree; a client build MUST NOT run against this repo"
      FAIL=$((FAIL+1))
      FAILURES+=("X.12|Artifact-coverage drift (org-chart/routing/command-center/dreaming/bootstrap/skills-count/version)|Run: python3 $CONSISTENCY_GATE --only artifact — fix every DRIFT dimension (run bump-version.sh for version drift; correct the README/install.sh skill count; restore the bootstrap template) before building")
      while IFS= read -r _cgl; do
        case "$_cgl" in *"[ORG-CHART]"*|*"[ROUTING]"*|*"[COMMAND-CENTER]"*|*"[DREAMING]"*|*"[GENERATOR-WIRING]"*|*"[BOOTSTRAP]"*|*"[SKILLS-COUNT]"*|*"[VERSION-MARKERS]"*) red "    $_cgl" ;; esac
      done < "$_cg_tmp" ;;
    *)
      yellow "  ⚠ X.12 Repo-consistency gate could not run (rc=$CONSISTENCY_RC)"; WARN=$((WARN+1))
      WARNINGS+=("X.12|Repo-consistency gate could not run (rc=$CONSISTENCY_RC)|Ensure python3 + the skill scripts are present; re-run $CONSISTENCY_GATE") ;;
  esac
  rm -f "$_cg_tmp"
else
  yellow "  ⚠ X.12 qc-assert-repo-consistency.py not found — skipping repo-consistency check"
  WARN=$((WARN+1))
  WARNINGS+=("X.12|qc-assert-repo-consistency.py missing|Update openclaw-onboarding to the version that ships the repo-consistency gate")
fi

# ─── CHECK X.13: GHL MCP supervision standard (v12.22.0) ─────────────────────
# Hard-fail: the SHIPPED GHL-MCP autostart scripts (skill 36, Tier 2) MUST be
# configured for PROPER, REBOOT-SURVIVING, PORT-PINNED supervision so a FRESH
# install can never reproduce the fleet incident (12/19 boxes down/unsupervised).
# Forbidden regressions: a BARE `nohup node …` (unsupervised, dies on teardown)
# and an UNPINNED port (main.js reads PORT before MCP_SERVER_PORT → binds a random
# port). Delegates to qc-assert-ghl-mcp-supervised.sh (single source of truth).
echo
blue "── CHECK X.13: GHL MCP supervision standard ──"
GHL_SUP_SCRIPT=""
for _gs_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-ghl-mcp-supervised.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-ghl-mcp-supervised.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-ghl-mcp-supervised.sh"; do
  [[ -f "$_gs_cand" ]] && GHL_SUP_SCRIPT="$_gs_cand" && break
done
if [[ -n "$GHL_SUP_SCRIPT" ]]; then
  _gs_tmp=$(mktemp)
  bash "$GHL_SUP_SCRIPT" > "$_gs_tmp" 2>&1
  GHL_SUP_RC=$?
  GHL_SUP_OUT=$(cat "$_gs_tmp"); rm -f "$_gs_tmp"
  if [[ "$GHL_SUP_RC" = "0" ]]; then
    green "  ✓ X.13 GHL MCP autostart is supervised (launchd/pm2/systemd), reboot-surviving, and PORT-pinned (no bare nohup, no random port)"; PASS=$((PASS+1))
  else
    red "  ✗ X.13 GHL MCP supervision invariant violated — a fresh install could ship an unsupervised / random-port GHL MCP"
    FAIL=$((FAIL+1))
    FAILURES+=("X.13|GHL MCP autostart not properly supervised / PORT not pinned|Run: bash scripts/qc-assert-ghl-mcp-supervised.sh — fix every INVARIANT VIOLATED line (use pm2+save+resurrect on VPS, launchd KeepAlive on Mac, pin BOTH PORT and MCP_SERVER_PORT, remove bare nohup)")
    while IFS= read -r _gsline; do
      case "$_gsline" in
        *"INVARIANT VIOLATED"*|*"offender:"*) red "    $_gsline" ;;
      esac
    done <<< "$GHL_SUP_OUT"
  fi
else
  yellow "  ⚠ X.13 qc-assert-ghl-mcp-supervised.sh not found — skipping GHL MCP supervision check"
  WARN=$((WARN+1))
  WARNINGS+=("X.13|qc-assert-ghl-mcp-supervised.sh missing|Update openclaw-onboarding to v12.22.0+")
fi

# ─── CHECK X.14: Platform-facts stamp in AGENTS.md (W7.4) ───────────────────
# Hard-fail: the active AGENTS.md must carry the <!-- PLATFORM_FACTS_V1 -->
# marker written by apply-fleet-standards.sh so every agent always knows:
#   • which platform this box is (mac / vps-hostinger / vps-contabo)
#   • where its env/secrets file lives
#   • where new passwords/tokens/keys go
# Delegates to qc-assert-platform-facts-stamped.sh (single source of truth).
#   rc=0 -> stamp present + platform consistent -> PASS
#   rc=1 -> INVARIANT VIOLATED (stamp absent or mismatch) -> HARD FAIL
#   rc=2 -> AGENTS.md not found (warn-only — pre-install)
echo
blue "── CHECK X.14: Platform-facts stamp in AGENTS.md (W7.4) ──"
PLATFORM_FACTS_SCRIPT=""
for _pf_cand in \
  "$(dirname "${BASH_SOURCE[0]}")/qc-assert-platform-facts-stamped.sh" \
  "$HOME/.openclaw/skills/scripts/qc-assert-platform-facts-stamped.sh" \
  "/data/.openclaw/skills/scripts/qc-assert-platform-facts-stamped.sh"; do
  [[ -f "$_pf_cand" ]] && PLATFORM_FACTS_SCRIPT="$_pf_cand" && break
done
if [[ -n "$PLATFORM_FACTS_SCRIPT" ]]; then
  _pf_tmp=$(mktemp)
  bash "$PLATFORM_FACTS_SCRIPT" > "$_pf_tmp" 2>&1
  PLATFORM_FACTS_RC=$?
  PLATFORM_FACTS_OUT=$(cat "$_pf_tmp"); rm -f "$_pf_tmp"
  case "$PLATFORM_FACTS_RC" in
    0)
      green "  ✓ X.14 PLATFORM_FACTS_V1 stamp present in AGENTS.md (platform label consistent)"; PASS=$((PASS+1)) ;;
    1)
      red "  ✗ X.14 PLATFORM_FACTS_V1 stamp absent or platform mismatch — agent does not know where env/secrets live"
      FAIL=$((FAIL+1))
      FAILURES+=("X.14|PLATFORM_FACTS_V1 missing or mismatched in AGENTS.md|Run: bash scripts/apply-fleet-standards.sh (W7.2 — stamps the block idempotently)")
      while IFS= read -r _pfline; do
        case "$_pfline" in
          *"INVARIANT VIOLATED"*) red "    $_pfline" ;;
        esac
      done <<< "$PLATFORM_FACTS_OUT" ;;
    2)
      yellow "  ⚠ X.14 AGENTS.md not found — platform-facts check skipped (pre-install or AGENTS.md path unresolvable)"
      WARN=$((WARN+1))
      WARNINGS+=("X.14|AGENTS.md not found — platform-facts stamp cannot be verified pre-install|Run install.sh or resolve AGENTS.md path; then re-run apply-fleet-standards.sh") ;;
    *)
      yellow "  ⚠ X.14 Platform-facts check could not run (rc=$PLATFORM_FACTS_RC)"
      WARN=$((WARN+1))
      WARNINGS+=("X.14|qc-assert-platform-facts-stamped.sh failed unexpectedly (rc=$PLATFORM_FACTS_RC)|Run: bash scripts/qc-assert-platform-facts-stamped.sh for details") ;;
  esac
else
  yellow "  ⚠ X.14 qc-assert-platform-facts-stamped.sh not found — skipping platform-facts check"
  WARN=$((WARN+1))
  WARNINGS+=("X.14|qc-assert-platform-facts-stamped.sh missing|Update openclaw-onboarding to the version that ships W7.4")
fi

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

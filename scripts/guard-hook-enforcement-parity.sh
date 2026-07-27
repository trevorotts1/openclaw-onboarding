#!/bin/bash
# guard-hook-enforcement-parity.sh
set -eo pipefail
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || { echo "FATAL -- not a git repository" >&2; exit 1; }
cd "$REPO_ROOT"
FAIL=0; FINDINGS_3C=0; HOOK=".githooks/pre-commit"
if [ ! -f "$HOOK" ]; then echo "FAIL 3a: $HOOK does not exist"; FAIL=1
elif [ ! -x "$HOOK" ]; then echo "FAIL 3a: $HOOK is not executable"; FAIL=1
else echo "PASS 3a: $HOOK exists, is a regular file, and is executable"; fi
EXTERNAL_SCRIPTS=()
while IFS= read -r line; do
  var_def=$(echo "$line" | sed -n 's/^[[:space:]]*\([A-Z_][A-Z0-9_]*\)="\{0,1\}\([a-zA-Z0-9._/-]*\.sh\)"\{0,1\}[[:space:]]*$/\1:\2/p' || true)
  if [ -n "$var_def" ]; then EXTERNAL_SCRIPTS+=("${var_def#*:}"); continue; fi
  script_path=$(echo "$line" | sed -n 's/.*bash  *\([^;&| ][^;&| ]*\).*/\1/p' || true)
  [ -z "$script_path" ] && script_path=$(echo "$line" | sed -n 's/.*bash  *\([^;&| ][^;&| ]*\)[[:space:]]*$/\1/p' || true)
  [ -n "$script_path" ] && [[ "$script_path" == */* ]] && EXTERNAL_SCRIPTS+=("$script_path")
done < <(cat "$HOOK" 2>/dev/null || true)
if [ ${#EXTERNAL_SCRIPTS[@]} -eq 0 ]; then echo "WARN 3b: no external scripts found"
else
  echo "3b: parsed ${#EXTERNAL_SCRIPTS[@]} external script invocation(s) from $HOOK"
  for script in "${EXTERNAL_SCRIPTS[@]}"; do
    if [ ! -f "$script" ]; then echo "FAIL 3b: $script does not exist"; FAIL=1
    elif [ ! -x "$script" ]; then echo "FAIL 3b: $script is not executable"; FAIL=1
    else echo "PASS 3b: $script exists and is executable"; fi
  done
fi
echo ""; echo "3c: CI counterpart coverage audit (WARN-MODE)"
GATE_SECTIONS=()
while IFS= read -r line; do
  gate_num=$(echo "$line" | sed -n 's/^#[[:space:]]*──[[:space:]]*\([0-9][0-9]*\)\. .*──[[:space:]]*$/\1/p' || true)
  [ -n "$gate_num" ] && [ "$gate_num" != "0" ] && GATE_SECTIONS+=("$gate_num")
done < <(grep -E '^#[[:space:]]*──[[:space:]]*[0-9]+\.' "$HOOK" 2>/dev/null || true)
TOTAL_SECTIONS=${#GATE_SECTIONS[@]}
if [ "$TOTAL_SECTIONS" -eq 0 ]; then echo "FAIL 3c: could not parse gate sections"; FAIL=1
else
  echo "3c: found $TOTAL_SECTIONS gate section(s): ${GATE_SECTIONS[*]}"
  declare -A GATE_WORKFLOWS
  GATE_WORKFLOWS[1]="qc-static.yml"; GATE_WORKFLOWS[2]="qc-static.yml"
  GATE_WORKFLOWS[3]="qc-static.yml"; GATE_WORKFLOWS[4]="qc-static.yml"
  GATE_WORKFLOWS[5]="version-consistency.yml"; GATE_WORKFLOWS[6]="agent-browser-lifecycle-guard.yml"
  GATE_WORKFLOWS[7]="persona-set-asset-consistency-guard.yml"
  WORKFLOW_DIR=".github/workflows"; ALL_BRANCH_COUNT=0; MAIN_ONLY_COUNT=0
  for gate in "${GATE_SECTIONS[@]}"; do
    wf="${GATE_WORKFLOWS[$gate]:-}"
    if [ -z "$wf" ]; then echo "  gate $gate: WARNING -- no CI counterpart mapped"; FINDINGS_3C=$((FINDINGS_3C + 1)); continue; fi
    wf_path="$WORKFLOW_DIR/$wf"
    if [ ! -f "$wf_path" ]; then echo "  gate $gate: WARNING -- mapped workflow $wf does not exist"; FINDINGS_3C=$((FINDINGS_3C + 1)); continue; fi
    HAS_PUSH=0; HAS_BRANCH_FILTER=0; IN_PUSH=0
    while IFS= read -r wfline; do
      if [ "$IN_PUSH" -eq 0 ]; then
        echo "$wfline" | grep -qE '^[[:space:]]*push[[:space:]]*:' && { IN_PUSH=1; HAS_PUSH=1; }
      else
        echo "$wfline" | grep -qE '^[[:space:]]*branches[[:space:]]*:' && HAS_BRANCH_FILTER=1
        echo "$wfline" | grep -qE '^[a-zA-Z_-]+[[:space:]]*:' && ! echo "$wfline" | grep -qE '^[[:space:]]*branches[[:space:]]*:' && IN_PUSH=0
      fi
    done < "$wf_path"
    if [ "$HAS_PUSH" -eq 1 ] && [ "$HAS_BRANCH_FILTER" -eq 1 ]; then
      echo "  gate $gate: CI counterpart $wf -- main-only"; MAIN_ONLY_COUNT=$((MAIN_ONLY_COUNT + 1)); FINDINGS_3C=$((FINDINGS_3C + 1))
    elif [ "$HAS_PUSH" -eq 1 ] && [ "$HAS_BRANCH_FILTER" -eq 0 ]; then
      echo "  gate $gate: CI counterpart $wf -- all-branch coverage"; ALL_BRANCH_COUNT=$((ALL_BRANCH_COUNT + 1))
    else echo "  gate $gate: CI counterpart $wf -- no push trigger"; FINDINGS_3C=$((FINDINGS_3C + 1)); fi
  done
  echo ""; echo "3c SUMMARY: $TOTAL_SECTIONS gate sections checked, $MAIN_ONLY_COUNT with main-only CI counterparts, $ALL_BRANCH_COUNT with all-branch coverage"
fi
if [ "$FAIL" -ne 0 ]; then echo ""; echo "guard-hook-enforcement-parity.sh: checks 3a/3b FAILED"; exit 1; fi
echo ""; echo "guard-hook-enforcement-parity.sh: checks 3a/3b PASSED; 3c is WARN-MODE with $FINDINGS_3C findings (exit 0 per Rule 3.5 stage 1)"
exit 0

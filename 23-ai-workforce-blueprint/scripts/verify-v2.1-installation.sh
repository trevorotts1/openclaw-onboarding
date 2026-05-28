#!/usr/bin/env bash
# Smoke-test every shipped v2.1 piece end-to-end.
#
# Exits 0 if all green. Non-zero if any check fails.
# Designed to run on the install target (Mac or VPS) after `git pull`.

set +e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SHARED_UTILS="$REPO_ROOT/shared-utils"
SKILL23_DIR="$REPO_ROOT/23-ai-workforce-blueprint"
SKILL23_SCRIPTS="$SKILL23_DIR/scripts"

PASS=0
FAIL=0
FAIL_LIST=""

check_file() {
  local desc="$1"
  local path="$2"
  if [ -f "$path" ]; then
    PASS=$((PASS+1))
    echo "  PASS  $desc"
  else
    FAIL=$((FAIL+1))
    FAIL_LIST="$FAIL_LIST\n    $desc :: $path"
    echo "  FAIL  $desc (missing: $path)"
  fi
}

check_script_runs() {
  local desc="$1"
  shift
  if "$@" > /dev/null 2>&1; then
    PASS=$((PASS+1))
    echo "  PASS  $desc"
  else
    local exit_code=$?
    FAIL=$((FAIL+1))
    FAIL_LIST="$FAIL_LIST\n    $desc (exit $exit_code)"
    echo "  FAIL  $desc (exit $exit_code)"
  fi
}

check_python_imports() {
  local desc="$1"
  local script_path="$2"
  if python3 -c "import ast; ast.parse(open('$script_path').read())" > /dev/null 2>&1; then
    PASS=$((PASS+1))
    echo "  PASS  $desc"
  else
    FAIL=$((FAIL+1))
    FAIL_LIST="$FAIL_LIST\n    $desc (syntax error in $script_path)"
    echo "  FAIL  $desc syntax error"
  fi
}

echo "============================================================"
echo "v2.1 Installation Verification"
echo "Repo root: $REPO_ROOT"
echo "============================================================"
echo ""

echo "=== Files present ==="
check_file "shared-utils: detect-platform.sh"                "$SHARED_UTILS/detect-platform.sh"
check_file "shared-utils: detect_platform.py"                "$SHARED_UTILS/detect_platform.py"
check_file "shared-utils: migrate-deferral-clauses.py"       "$SHARED_UTILS/migrate-deferral-clauses.py"
check_file "shared-utils: industry-detector.py"              "$SHARED_UTILS/industry-detector.py"
check_file "shared-utils: extract-behavioral-patterns.py"    "$SHARED_UTILS/extract-behavioral-patterns.py"
check_file "shared-utils: adaptive_weights.py"               "$SHARED_UTILS/adaptive_weights.py"
check_file "shared-utils: devils-advocate.py"                "$SHARED_UTILS/devils-advocate.py"
check_file "shared-utils: nudge-incomplete-interviews.py"    "$SHARED_UTILS/nudge-incomplete-interviews.py"

check_file "Skill 23: INSTRUCTIONS.md"                       "$SKILL23_DIR/INSTRUCTIONS.md"
check_file "Skill 23: department-naming-map.json"            "$SKILL23_DIR/department-naming-map.json"
check_file "Skill 23: skill-version.txt"                     "$SKILL23_DIR/skill-version.txt"
check_file "Skill 23: universal-how-to-template.md"          "$SKILL23_DIR/templates/universal-how-to-template.md"
check_file "Skill 23: role-doc-generation-prompt.md"         "$SKILL23_DIR/prompts/role-doc-generation-prompt.md"
check_file "Skill 23: infer-task-category.py"                "$SKILL23_SCRIPTS/infer-task-category.py"
check_file "Skill 23: create_role_workspaces.py"             "$SKILL23_SCRIPTS/create_role_workspaces.py"
check_file "Skill 23: post-build-role-workspaces.py"         "$SKILL23_SCRIPTS/post-build-role-workspaces.py"
# v10.15.4: vendored lib/ must ride along so detect_platform resolves at install path
check_file "Skill 23: lib/detect_platform.py (vendored)"     "$SKILL23_DIR/lib/detect_platform.py"
check_file "Skill 23: persona-selector-v2.py"                "$SKILL23_SCRIPTS/persona-selector-v2.py"
check_file "Skill 23: gemini-section-indexer.py"             "$SKILL23_SCRIPTS/gemini-section-indexer.py"
check_file "Skill 23: crm-suggested-roles.md"                "$SKILL23_DIR/suggested-roles/crm-suggested-roles.md"
check_file "Skill 23: openclaw-maintenance-suggested-roles.md" "$SKILL23_DIR/suggested-roles/openclaw-maintenance-suggested-roles.md"
check_file "Skill 23: social-media-suggested-roles.md"       "$SKILL23_DIR/suggested-roles/social-media-suggested-roles.md"
check_file "Skill 23: paid-advertisement-suggested-roles.md" "$SKILL23_DIR/suggested-roles/paid-advertisement-suggested-roles.md"
check_file "Skill 23: _deprecated/README.md"                 "$SKILL23_DIR/suggested-roles/_deprecated/README.md"

echo ""
echo "=== Python syntax ==="
for f in \
  "$SHARED_UTILS/detect_platform.py" \
  "$SHARED_UTILS/migrate-deferral-clauses.py" \
  "$SHARED_UTILS/industry-detector.py" \
  "$SHARED_UTILS/extract-behavioral-patterns.py" \
  "$SHARED_UTILS/adaptive_weights.py" \
  "$SHARED_UTILS/devils-advocate.py" \
  "$SHARED_UTILS/nudge-incomplete-interviews.py" \
  "$SKILL23_SCRIPTS/infer-task-category.py" \
  "$SKILL23_SCRIPTS/create_role_workspaces.py" \
  "$SKILL23_SCRIPTS/post-build-role-workspaces.py" \
  "$SKILL23_SCRIPTS/persona-selector-v2.py" \
  "$SKILL23_SCRIPTS/gemini-section-indexer.py" \
; do
  check_python_imports "syntax: $(basename "$f")" "$f"
done

echo ""
echo "=== Bash syntax ==="
for f in \
  "$SHARED_UTILS/detect-platform.sh" \
  "$SCRIPT_DIR/run-v2.1-migrations.sh" \
  "$SCRIPT_DIR/verify-v2.1-installation.sh" \
; do
  if bash -n "$f" 2>/dev/null; then
    PASS=$((PASS+1))
    echo "  PASS  syntax: $(basename "$f")"
  else
    FAIL=$((FAIL+1))
    FAIL_LIST="$FAIL_LIST\n    syntax: $(basename "$f")"
    echo "  FAIL  syntax: $(basename "$f")"
  fi
done

echo ""
echo "=== Runtime smoke tests ==="
check_script_runs "industry-detector: 'business coach'" \
  python3 "$SHARED_UTILS/industry-detector.py" --text "I am a business coach helping entrepreneurs"

check_script_runs "infer-task-category: 'write a cold email'" \
  python3 "$SKILL23_SCRIPTS/infer-task-category.py" "write a cold email"

check_script_runs "adaptive_weights: email-outreach + leadership" \
  python3 "$SHARED_UTILS/adaptive_weights.py" --task "write a cold email" --mode leadership

check_script_runs "migrate-deferral-clauses: dry-run" \
  python3 "$SHARED_UTILS/migrate-deferral-clauses.py" --dry-run

check_script_runs "post-build-role-workspaces: dry-run" \
  python3 "$SKILL23_SCRIPTS/post-build-role-workspaces.py" --dry-run

check_script_runs "gemini-section-indexer: dry-run" \
  python3 "$SKILL23_SCRIPTS/gemini-section-indexer.py" --reindex-all --dry-run

echo ""
echo "============================================================"
TOTAL=$((PASS + FAIL))
echo "RESULT: $PASS / $TOTAL passing"
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "FAILURES:"
  echo -e "$FAIL_LIST"
  exit 1
fi
echo "All v2.1 checks GREEN."
echo "============================================================"
exit 0

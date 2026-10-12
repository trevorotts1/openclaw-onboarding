#!/usr/bin/env bash
# tests/unit/memory-corpus-no-defaults-extrapaths.test.sh
#
# REGRESSION GUARD (system-memory-fix): fails the build if any materializer,
# config template, or onboarding instruction in this repo plants the shared
# master-files corpus into a place the OpenClaw runtime UNIONS onto every
# department agent — i.e. agents.defaults.memorySearch.extraPaths, OR any
# per-department agent's memorySearch.extraPaths.
#
# WHY THIS GUARD EXISTS (field-confirmed memory-DB bloat):
#   The OpenClaw runtime unions each agent's memorySearch.extraPaths onto
#   agents.defaults.memorySearch.extraPaths. So a corpus path placed in
#   `defaults` (or in any per-dept agent's extraPaths) gets re-embedded into
#   EVERY department's memory DB — one full copy of the corpus per department —
#   producing multi-GB-per-box bloat. The corpus must be embedded ONCE, on the
#   single `main` agent only (agents.list[] entry with id="main"), which is what
#   31-upgraded-memory-system/scripts/activate-memory-stack.sh now does.
#
# What is FLAGGED (build FAIL):
#   (A) Any *.sh / *.py materializer that writes a NON-EMPTY corpus path into
#       agents.defaults.memorySearch.extraPaths.
#   (B) Any materializer (Skill 32 materialize-dept-agents.sh in particular)
#       whose per-department agent template ships a NON-EMPTY extraPaths.
#   (C) Any INSTALL/FULL-DOC instruction that tells the operator/agent to put the
#       corpus into agents.defaults.memorySearch.extraPaths or into a
#       per-department (dept-*) agent's extraPaths.
#
# What is NOT flagged (CORRECT — must stay):
#   - Corpus attached to agents.list[main].memorySearch.extraPaths (embed-once).
#   - Empty extraPaths: []  on agents.defaults and on per-dept agents.
#   - Comment / prose lines that DESCRIBE the guard (they contain the words
#     "MUST stay empty", "embed", "guard", "do not", "never", "bloat", etc.).
#   - This test file and tests/ fixtures.
#
# Exit 0 = pass. Exit 1 = a memory-bloat corpus-placement regression was found.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PASS=0
FAIL=0

pass() { echo "  PASS: $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL: $1"; FAIL=$((FAIL+1)); }

echo "=== memory-corpus-no-defaults-extrapaths.test.sh ==="
echo ""

# Corpus dir name fragments the onboarding searches for (case-insensitive).
CORPUS_RE='openclaw-master-files|openclaw master files|OpenClaw Master Files|master-files-dir|MASTER_FILES_DIR'

# ─────────────────────────────────────────────────────────────────────────────
# (A) The Skill 31 materializer (activate-memory-stack.sh) must keep
#     agents.defaults.memorySearch.extraPaths EMPTY, and attach the corpus only
#     to the main agent.
# ─────────────────────────────────────────────────────────────────────────────
echo "--- (A) activate-memory-stack.sh: defaults.extraPaths empty + corpus on main only ---"
ACTIVATE="$REPO_ROOT/31-upgraded-memory-system/scripts/activate-memory-stack.sh"
if [ -f "$ACTIVATE" ]; then
  # The canonical agents.defaults.memorySearch block must declare an empty
  # extraPaths (the bloat guard). We assert the literal empty declaration exists.
  if grep -qE '"extraPaths":[[:space:]]*\[\]' "$ACTIVATE"; then
    pass "activate-memory-stack.sh declares an empty extraPaths in the defaults block"
  else
    fail "activate-memory-stack.sh: agents.defaults.memorySearch.extraPaths is not declared empty"
  fi
  # It must attach the corpus to agents.list[main] (the embed-once mechanism).
  if grep -q 'agents.list\[main\]\|id") == "main"\|get("id") == "main"' "$ACTIVATE" \
     && grep -qi 'corpus' "$ACTIVATE"; then
    pass "activate-memory-stack.sh attaches the shared corpus to the main agent (embed-once)"
  else
    fail "activate-memory-stack.sh: no main-agent corpus-attach (embed-once) mechanism found"
  fi
else
  fail "activate-memory-stack.sh not found at $ACTIVATE"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (B) No materializer (*.sh / *.py) writes a corpus path into
#     agents.defaults.memorySearch.extraPaths, and the per-dept materializer
#     ships an EMPTY per-dept extraPaths.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (B) No materializer plants the corpus into defaults / per-dept extraPaths ---"

CODE_FILES=$(find "$REPO_ROOT" \
  -path "$REPO_ROOT/.git" -prune -o \
  -path "$REPO_ROOT/tests" -prune -o \
  -path "*/node_modules/*" -prune -o \
  \( -name '*.sh' -o -name '*.py' \) -print 2>/dev/null)

B_FAIL=0
while IFS= read -r f; do
  [ -f "$f" ] || continue
  rel="${f#$REPO_ROOT/}"
  # Look for a NON-EMPTY extraPaths assignment that carries a corpus path on the
  # same line (e.g.  extraPaths: ["/…/openclaw-master-files"]  or  in python:
  # "extraPaths": ["…master…"]). Drop comment lines first.
  hits=$(grep -nE 'extraPaths' "$f" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*#' \
    | grep -vE '"extraPaths":[[:space:]]*\[\]|extraPaths"?\][[:space:]]*=[[:space:]]*\[\]|extraPaths.*=.*\[\][[:space:]]*$' \
    | grep -iE "$CORPUS_RE" \
    || true)
  if [ -n "$hits" ]; then
    fail "$rel: a corpus path is written into a non-empty extraPaths (bloat source):"
    echo "$hits" | sed 's/^/        /'
    B_FAIL=1
  fi
done <<< "$CODE_FILES"

if [ "$B_FAIL" -eq 0 ]; then
  pass "no materializer writes a corpus path into a non-empty extraPaths"
fi

# The Skill 32 per-dept materializer must ship extraPaths: [] in its desired_entry.
MAT="$REPO_ROOT/32-command-center-setup/scripts/materialize-dept-agents.sh"
if [ -f "$MAT" ]; then
  if grep -qE '"extraPaths":[[:space:]]*\[\]' "$MAT"; then
    pass "materialize-dept-agents.sh writes empty per-department extraPaths"
  else
    fail "materialize-dept-agents.sh: per-department extraPaths is not empty"
  fi
else
  fail "materialize-dept-agents.sh not found at $MAT"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (C) No INSTALL/FULL-DOC instruction tells the agent to place the corpus into
#     agents.defaults.memorySearch.extraPaths.
#     We scan JSON-ish doc blocks: a line that pairs the defaults path with the
#     corpus is the regression. Guard/prose lines are excluded by requiring the
#     literal `agents.defaults.memorySearch.extraPaths` token paired with a
#     corpus path within the surrounding 2 lines is hard in grep, so we use a
#     simpler, robust rule: flag any *non-comment, non-blockquote* doc line that
#     contains BOTH "defaults" AND "extraPaths" AND a corpus name on that line.
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (C) No doc instructs putting the corpus into defaults.extraPaths ---"

DOC_FILES=(
  "$REPO_ROOT/31-upgraded-memory-system/FULL-DOC.md"
  "$REPO_ROOT/32-command-center-setup/INSTALL.md"
)
C_FAIL=0
for d in "${DOC_FILES[@]}"; do
  [ -f "$d" ] || continue
  rel="${d#$REPO_ROOT/}"
  # Blockquote (>) lines are guard prose — exempt. Flag a line that puts a corpus
  # path on the same line as a defaults extraPaths instruction.
  hits=$(grep -nE 'defaults.*extraPaths|extraPaths.*defaults' "$d" 2>/dev/null \
    | grep -vE '^[0-9]+:[[:space:]]*>' \
    | grep -iE "$CORPUS_RE" \
    || true)
  if [ -n "$hits" ]; then
    fail "$rel: doc instructs placing the corpus into agents.defaults extraPaths:"
    echo "$hits" | sed 's/^/        /'
    C_FAIL=1
  fi
done
if [ "$C_FAIL" -eq 0 ]; then
  pass "no doc instructs placing the corpus into agents.defaults.memorySearch.extraPaths"
fi

# ─────────────────────────────────────────────────────────────────────────────
# (D) The embedding cache is capped wherever the memorySearch block is templated
#     (so the cache cannot run away again).
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "--- (D) Embedding cache is capped (maxEntries) in the templated memorySearch block ---"
if [ -f "$ACTIVATE" ]; then
  if grep -qE '"maxEntries"' "$ACTIVATE"; then
    pass "activate-memory-stack.sh caps the embedding cache (maxEntries)"
  else
    fail "activate-memory-stack.sh: no embedding-cache cap (maxEntries) in the canonical block"
  fi
fi

# ─────────────────────────────────────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [ "$FAIL" -gt 0 ]; then
  echo "FAIL: $FAIL check(s) failed — memory-bloat corpus-placement regression detected"
  exit 1
fi
echo "PASS: corpus is embed-once (main agent only); no defaults/per-dept bloat"
exit 0

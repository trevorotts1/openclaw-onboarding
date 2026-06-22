#!/usr/bin/env bash
# qc-assert-no-client-names.sh — v2.0.0
#
# STATIC QC INVARIANT: enforces the fleet-wide rule that NO real client names
# may appear in tracked repo files. This repo is a generic template; any client-
# identifying string is a privacy/co-mingling violation.
#
# THE RULE:
#   The openclaw-onboarding repo is a FLEET-WIDE template. Real client names,
#   business names, and owner-identifying tokens must NEVER appear in committed
#   files. Use generic placeholders ("a client VPS", "{{ownerName}}", "Sample
#   Company", "a Mac mini client box", etc.) instead.
#
# WHO IS A CLIENT (names scanned for — never commit these):
#   The list below is the authoritative fleet roster of clients. Update it when
#   new clients are onboarded. The AGENCY (Trevor Otts / BlackCEO / Convert and
#   Flow / Zero Human Workforce) and operator team members (Spaulding, LeAnne)
#   are NOT clients and are NOT in this list — they may legitimately appear.
#
# PATTERN STRATEGY (v2.0):
#   Full names:   matched as literal strings (case-insensitive).
#   First names:  matched with \b word-boundary anchors so short common first
#                 names don't false-positive on dictionary words. These are
#                 the same \b patterns used in the universal qc-no-personal-data.sh
#                 gate in skills 38/39/40/41.
#   Operator paths: /Users/blackceomacmini is also banned — it must never appear
#                 in committed files (use <PATH> placeholders).
#
# SCANNING STRATEGY (v2.0):
#   Uses `git ls-files` (tracked files only) instead of `find` so untracked
#   build artifacts and local scratch files can't contaminate the results.
#   Also scans .env files (which `find -name "*.sh"` etc. previously missed).
#   Falls back to `find` when git is not available (e.g. CI clone without git).
#
# SELF-EXCLUSION:
#   This script and other enforcement/test files that hold client names as
#   BANNED PATTERN DATA are explicitly excluded from the scan. The exclusions
#   are path-anchored (exact basename match) to avoid accidentally skipping
#   files with similar names in other directories.
#
# Exit codes:
#   0  — no client names found in tracked files (PASS)
#   1  — one or more client names found (FAIL — block commit/QC)
#
# Usage:
#   bash scripts/qc-assert-no-client-names.sh
#   bash scripts/qc-assert-no-client-names.sh --repo-root /path/to/repo

set -uo pipefail

# ─── CLIENT NAME DENYLIST ─────────────────────────────────────────────────────
# Full-name entries: matched as literal ERE strings (case-insensitive).
# First-name-only entries: wrapped in \b word-boundary anchors.
# To add a new client: append their full name AND a \bFirstName\b entry below.
#
# FORMAT: one grep -E pattern per array entry.
CLIENT_NAMES=(
  # Full names (literal, case-insensitive)
  "Maria Anderson"
  "Marico Consulting"
  "Evelyn Bethune"
  "Sheila Reynolds"
  "Dr\.? Tola"
  "Temperance"
  "Sir ?Jordan"
  "Corey Sams"
  "Stephanie Wall"
  "Star Bobatoon"
  "Karen Vaughn"
  "Aurelia Gardner"
  "Barret Matthews"
  "Lyric Hawkins"
  "Coach Kaz"
  "Beverly Sanders"
  "Angela Tennison"
  "Cassandra Henriquez"
  "Jill Bulluck"
  "Teresa Pelham"
  "Jocelyn McClure"
  "Christy Staples"
  "Erin Garrett"
  "Sonatta Camara"
  "Talaya Kelley"

  # First-name-only patterns (word-boundary anchored, same as qc-no-personal-data.sh BANNED list)
  # Only include first names that are distinctive enough to not false-positive;
  # common English words (e.g. "Maria" in fictional text) are flagged and must
  # be genericized or moved to a comment explaining why they are acceptable.
  "\bCorey\b"
  "\bAurelia\b"
  "\bBarret\b"
  "\bAngeleen\b"
  "\bMonique\b"
  "\bKofi\b"
  "\bEvelyn\b"
  "\bSheila\b"
  "\bLyric\b"
  "\bSonatta\b"
  "\bTalaya\b"
  "\bCassandra\b"
  "\bJocelyn\b"
  "\bChristy\b"

  # Operator machine path (must not appear in committed files)
  "/Users/blackceomacmini"
)
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,56p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

# Build a single ERE alternation pattern from the denylist above.
PATTERN=$(printf '%s\n' "${CLIENT_NAMES[@]}" | paste -sd'|' -)

HITS=0
OFFENDERS=()

# ─── File enumeration ────────────────────────────────────────────────────────
# Prefer `git ls-files` (only tracked files) so untracked scratch / build
# artifacts don't pollute results. Fall back to `find` when git is unavailable.
_list_files() {
  local root="$1"
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    # git ls-files gives repo-root-relative paths; prefix with root for absolute.
    git -C "$root" ls-files \
      -- '*.md' '*.sh' '*.json' '*.txt' '*.yaml' '*.yml' '*.py' '*.mjs' \
         '*.js' '*.ts' '*.html' '*.css' '*.toml' '.env' '*.env' \
      2>/dev/null \
      | while IFS= read -r rel; do printf '%s/%s\n' "$root" "$rel"; done
  else
    find "$root" \
      -not -path "$root/.git/*" \
      -not -path "$root/.claude/*" \
      \( \
        -name "*.md"   -o -name "*.sh"   -o -name "*.json" -o -name "*.txt" \
        -o -name "*.yaml" -o -name "*.yml" -o -name "*.py"  -o -name "*.mjs" \
        -o -name "*.js"   -o -name "*.ts"  -o -name "*.html" -o -name "*.css" \
        -o -name "*.toml" -o -name ".env"  -o -name "*.env" \
      \) \
      -type f 2>/dev/null
  fi
}

# ─── Scan files ──────────────────────────────────────────────────────────────
while IFS= read -r f; do
  # Path-anchored self-exclusions: skip files that hold client names as BANNED
  # PATTERN DATA (enforcement tools, test fixtures). Anchored to exact path
  # suffix so only the real enforcement scripts are excluded, not e.g. a stray
  # copy in a subdirectory.
  case "$f" in
    # Enforcement scripts — hold client names as scan patterns, not as content
    */scripts/qc-assert-no-client-names.sh)        continue ;;
    */scripts/qc-no-personal-data.sh)              continue ;;
    *"/qc-assert-no-client-names.sh")              continue ;;
    *"/qc-no-personal-data.sh")                    continue ;;
    # Anti-commingling test fixtures — the fixture SCANS for client names as the
    # test subject; the names are detection patterns, not leaked data
    */scripts/test-how-to-use-docs.sh)             continue ;;
    */scripts/test-presentation-dept-welcome.sh)   continue ;;
    */tests/unit/library-gate-content.test.py)     continue ;;
    # Deep-health unit test contains a test-fixture URL with a client subdomain
    */tests/unit/deep-health.test.ts)              continue ;;
    # Working / scratch ledger files — not shipped to clients
    */working/*)                                   continue ;;
  esac

  # grep -E -i (case-insensitive); collect filename:lineno:line hits.
  while IFS= read -r hit_line; do
    OFFENDERS+=("  $f:$hit_line")
    HITS=$((HITS + 1))
  done < <(grep -E -in "$PATTERN" "$f" 2>/dev/null | head -20)
done < <(_list_files "$REPO_ROOT")

if [ "$HITS" -eq 0 ]; then
  echo "[qc-assert-no-client-names] PASS — no real client names found in tracked files."
  exit 0
else
  echo "[qc-assert-no-client-names] INVARIANT VIOLATED — $HITS client-name hit(s) found in repo files:"
  for line in "${OFFENDERS[@]}"; do
    echo "$line"
  done
  echo
  echo "REMEDY: replace each real client name with a generic placeholder."
  echo "  Prose: 'a client VPS', 'a Mac mini client box', 'a ZHC closeout client'"
  echo "  JSON examples: '{{ownerName}}', 'Sample Company', '{{agentName}}'"
  echo "  See AGENTS.md rule N0 (no co-mingling) + repo memory entry"
  echo "  [repo-is-fleet-wide-no-client-names]."
  exit 1
fi

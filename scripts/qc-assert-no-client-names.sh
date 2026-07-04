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
#   The authoritative fleet roster is EXTERNALIZED to an operator-local,
#   gitignored file ($OPENCLAW_CLIENT_ROSTER or ~/.openclaw/client-roster.txt) so
#   real names never ship in this repo. Update that file when new clients are
#   onboarded. The AGENCY (the operating agency / brand) and operator team
#   members are NOT clients and belong in NO roster — they may legitimately appear.
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

# ─── CLIENT NAME DENYLIST (EXTERNALIZED) ──────────────────────────────────────
# The real client roster no longer lives in this file (or anywhere tracked). It
# is loaded at runtime from an operator-local, gitignored roster file so that no
# real client name, chat ID, or GHL location ID ever ships in the repo.
#
#   Load order:  $OPENCLAW_CLIENT_ROSTER  →  ${HOME}/.openclaw/client-roster.txt
#   Format:      one ERE pattern per line; blank lines and '#' comments ignored.
#                Full names match literally; short first names use \bName\b;
#                opaque IDs (chat IDs, GHL location IDs) go one-per-line.
#   Template:    scripts/client-roster.example.txt (placeholders only, tracked).
#
# TWO MODES:
#   FULL MODE (roster present) — scan every tracked file for the roster patterns
#     PLUS the always-on tokens below. This is the authoritative check; it runs
#     on operator boxes and in pre-commit where the roster exists.
#   STRUCTURAL MODE (roster absent, e.g. CI) — the roster-specific scan is
#     SKIPPED with a stderr WARNING, but the always-on tokens are STILL scanned,
#     so the gate never fails open: a committed operator path or a leaked
#     .example placeholder name still exits non-zero.

# Always-on tokens scanned in BOTH modes (not client-roster data):
#   - operator machine path (must never appear in committed files)
#   - the obviously-fake placeholder names from client-roster.example.txt; if any
#     of these appear in tracked content they are a template leak → hard fail.
ALWAYS_ON_TOKENS=(
  "/Users/blackceomacmini"
  "ExampleClientAlpha"
  "ExampleClientBeta"
  "PlaceholderCo"
  "Testclient Sentinel"
)

# Resolve the roster path (env override wins; else operator-local default).
_roster_path() {
  if [ -n "${OPENCLAW_CLIENT_ROSTER:-}" ]; then
    printf '%s\n' "$OPENCLAW_CLIENT_ROSTER"
  else
    printf '%s\n' "${HOME:-/root}/.openclaw/client-roster.txt"
  fi
}

# Load roster patterns into CLIENT_NAMES (one per line, comments/blanks stripped).
# Returns 0 and sets ROSTER_AVAILABLE=1 if a non-empty roster was read; else 1.
CLIENT_NAMES=()
ROSTER_AVAILABLE=0
_load_roster() {
  local f; f="$(_roster_path)"
  [ -f "$f" ] || return 1
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    CLIENT_NAMES+=("$line")
  done < "$f"
  [ "${#CLIENT_NAMES[@]}" -gt 0 ] && ROSTER_AVAILABLE=1
  [ "$ROSTER_AVAILABLE" = 1 ]
}
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

# Load the external roster (if present) and decide the mode.
if _load_roster; then
  MODE="full"
else
  MODE="structural"
  echo "WARNING: client-name roster not found (looked in \$OPENCLAW_CLIENT_ROSTER," \
       "then ${HOME:-/root}/.openclaw/client-roster.txt); SKIPPING the roster-specific" \
       "client-name check. Always-on tokens (operator path + .example placeholders)" \
       "are still enforced. Set OPENCLAW_CLIENT_ROSTER or create" \
       "~/.openclaw/client-roster.txt (see scripts/client-roster.example.txt) to" \
       "enable the full check." >&2
fi

# Build a single ERE alternation pattern: always-on tokens in both modes, plus
# the external roster patterns when a roster is available.
SCAN_TOKENS=("${ALWAYS_ON_TOKENS[@]}")
if [ "$MODE" = "full" ]; then
  SCAN_TOKENS+=("${CLIENT_NAMES[@]}")
fi
PATTERN=$(printf '%s\n' "${SCAN_TOKENS[@]}" | paste -sd'|' -)

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
         '*.template' '*.tmpl' '*.example' '*.sample' '*.tsx' '*.jsx' '*.cjs' \
         '*.conf' '*.cfg' '*.ini' '*.xml' '*.csv' '*.plist' '*.tf' '*.env.template' \
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
        -o -name "*.template" -o -name "*.tmpl" -o -name "*.example" \
        -o -name "*.sample" -o -name "*.tsx" -o -name "*.jsx" -o -name "*.cjs" \
        -o -name "*.conf" -o -name "*.cfg" -o -name "*.ini" -o -name "*.xml" \
        -o -name "*.csv" -o -name "*.plist" -o -name "*.tf" \
      \) \
      -type f 2>/dev/null
  fi
}

# ─── Self-exclusion predicate ─────────────────────────────────────────────────
# Path-anchored self-exclusions: skip files that hold client names as BANNED
# PATTERN DATA (enforcement tools, test fixtures). Anchored to exact path suffix
# so only the real enforcement scripts are excluded, not e.g. a stray copy in a
# subdirectory.
_is_excluded() {
  case "$1" in
    # Enforcement scripts — hold client names as scan patterns, not as content
    */scripts/qc-assert-no-client-names.sh)        return 0 ;;
    */scripts/qc-no-personal-data.sh)              return 0 ;;
    *"/qc-assert-no-client-names.sh")              return 0 ;;
    *"/qc-no-personal-data.sh")                    return 0 ;;
    # Roster template — placeholder names are its whole purpose (tracked template)
    */scripts/client-roster.example.txt)           return 0 ;;
    *"/client-roster.example.txt")                 return 0 ;;
    # Planted self-test fixture + its harness — hold a placeholder sentinel as the
    # DETECTION subject, not as leaked content
    */tests/fixtures/no-client-names/planted-client-name.txt) return 0 ;;
    */tests/fixtures/no-client-names/selftest-qc-assert.sh)   return 0 ;;
    # Anti-commingling test fixtures — the fixture SCANS for client names as the
    # test subject; the names are detection patterns, not leaked data
    */scripts/test-how-to-use-docs.sh)             return 0 ;;
    */scripts/test-presentation-dept-welcome.sh)   return 0 ;;
    */tests/unit/library-gate-content.test.py)     return 0 ;;
    # Deep-health unit test contains a test-fixture URL with a client subdomain
    */tests/unit/deep-health.test.ts)              return 0 ;;
    # GHL auth-fallback secret-hygiene test holds the operator-path string as its
    # detection literal (it greps for /Users/blackceomacmini) — pattern, not leak
    */06-ghl-install-pages/tests/test_ghl_secret_hygiene.py) return 0 ;;
    # Working / scratch ledger files — not shipped to clients
    */working/*)                                   return 0 ;;
  esac
  return 1
}

# ─── Scan files ──────────────────────────────────────────────────────────────
# Build the (self-exclusion-filtered) file list once, then grep it in a SINGLE
# batched pass. A per-file grep loop spawns one process per file (thousands of
# tracked files) and is pathologically slow; batching grep over the whole list
# is functionally identical but orders of magnitude faster. Hits are read back
# as `path:lineno:line` and the same `head -20`-per-file cap is reapplied so a
# single noisy file cannot flood the report.
FILES=()
while IFS= read -r f; do
  _is_excluded "$f" && continue
  FILES+=("$f")
done < <(_list_files "$REPO_ROOT")

declare -A _PER_FILE_HITS=()
if [ "${#FILES[@]}" -gt 0 ]; then
  while IFS= read -r hit_line; do
    [ -z "$hit_line" ] && continue
    # grep -H output is `path:lineno:line`; split off the path (first field).
    path="${hit_line%%:*}"
    n=$(( ${_PER_FILE_HITS["$path"]:-0} + 1 ))
    _PER_FILE_HITS["$path"]=$n
    [ "$n" -gt 20 ] && continue   # per-file cap (matches prior head -20 behavior)
    OFFENDERS+=("  $hit_line")
    HITS=$((HITS + 1))
  done < <(printf '%s\0' "${FILES[@]}" \
             | xargs -0 grep -E -Hin "$PATTERN" 2>/dev/null)
fi

if [ "$HITS" -eq 0 ]; then
  if [ "$MODE" = "full" ]; then
    echo "[qc-assert-no-client-names] PASS (full) — no roster client names, operator paths, or placeholder leaks in tracked files."
  else
    echo "[qc-assert-no-client-names] PASS (structural) — no operator paths or .example placeholder leaks in tracked files. NOTE: roster-specific client-name check was SKIPPED (no roster; see WARNING above)."
  fi
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

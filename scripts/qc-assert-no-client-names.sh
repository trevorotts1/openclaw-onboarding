#!/usr/bin/env bash
# qc-assert-no-client-names.sh — v3.0.0
#
# ─── THE RULE (operator, 2026-07-11 — AUTHORITATIVE; supersedes v2.x) ─────────
# This repo is a FLEET-WIDE template shipped to every client. Exactly THREE
# things are enforceable, and NOTHING else:
#
#   1. No CLIENT / ROSTER MEMBER real HUMAN NAMES — an actual customer or team
#      member. NOT book characters. NOT personas. NOT authors of referenced works.
#   2. No genuine SECRETS — live tokens, API keys, `pit-` GHL tokens, bot tokens,
#      private keys. ABSOLUTE. DO NOT WEAKEN THIS.
#   3. Nothing built for ONE client — repo content stays generic + fleet-reusable.
#
# ─── ⚠️ EXPLICITLY EXEMPT — NEVER flag, block, or scrub ⚠️ ────────────────────
#   • Cloudflare Access Application UUIDs / AUD tags
#   • Telegram chat IDs
#   • GHL location IDs
#   • ANY opaque identifier (UUID, numeric ID, hash)
#   • Book titles
#   • Persona names derived from books
#   • Authors of referenced works
#   • Product proper nouns
#
# GOVERNING PRINCIPLE: opaque infrastructure identifiers and product content are
# NOT the target. v2.x of this gate swept opaque IDs into the scan; that was
# WRONG and is removed. Do not re-add an identifier pass here.
#
# ─── ⛔ WHY THIS GATE IS DELIBERATELY NARROW ──────────────────────────────────
# NEVER enforce the NAME rule with a grep / regex / name-roster ALONE. A pattern
# match cannot tell a client's real name from a book-persona name — it either
# misses real leaks or blocks legitimate product PRs forever. The AUTHORITATIVE
# name check is the LLM reviewer (scripts/qc-llm-diff-review.py, run on every PR).
# This script survives only as a cheap always-on scan for the two things that DO
# have a literal shape: the operator machine path, and .example placeholder leaks.
# (Regex IS still correct for SECRETS — a secret has a literal shape; a human
# name does not.)
#
# WHO IS A CLIENT (names scanned for — never commit these):
#   The authoritative fleet roster is EXTERNALIZED to an operator-local,
#   gitignored file ($OPENCLAW_CLIENT_ROSTER or ~/.openclaw/client-roster.txt) so
#   real names never ship in this repo. It is a HUMAN-NAME roster: opaque IDs are
#   NOT roster entries and are filtered out on load (see _load_roster). The AGENCY
#   (the operating agency / brand) and operator team members are NOT clients and
#   belong in NO roster — they may legitimately appear.
#
# PATTERN STRATEGY (v3.0):
#   Full names:   matched as literal strings (case-insensitive).
#   First names:  matched with \b word-boundary anchors so short common first
#                 names don't false-positive on dictionary words.
#   Opaque IDs:   NOT SCANNED. Exempt. Filtered out of the roster on load.
#   Operator paths: /Users/blackceomacmini is banned — it must never appear
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

# ─── CLIENT HUMAN-NAME DENYLIST (EXTERNALIZED) ────────────────────────────────
# The real client roster no longer lives in this file (or anywhere tracked). It
# is loaded at runtime from an operator-local, gitignored roster file so that no
# real client name ever ships in the repo.
#
#   Load order:  $OPENCLAW_CLIENT_ROSTER  →  ${HOME}/.openclaw/client-roster.txt
#   Format:      one ERE pattern per line; blank lines and '#' comments ignored.
#                HUMAN NAMES ONLY. Full names match literally; short first names
#                use \bName\b.
#   ⚠️ OPAQUE IDs (Telegram chat IDs, GHL location IDs, UUIDs, AUD tags, hashes)
#      are EXEMPT and are FILTERED OUT of the roster on load — even if an old
#      operator roster file still lists them. They are not client-identifying in
#      the sense this gate protects, and scanning for them blocked legitimate PRs.
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
  # FIX-PRES-05: also ban the DASH-SEPARATED session-path form of the operator
  # home (the `-Users-<operator>/…` scratchpad spelling that evaded the slash-only
  # token in test_cc_contract.py). The BARE username is intentionally NOT an
  # always-on token: it is the very literal each skill's own leak-detection scans
  # for (test_funnel_matcher.py / check-funnel-automation-library-drift.py /
  # qc-no-personal-data.sh), so scanning for it here would false-positive on those
  # legitimate detection patterns.
  "-Users-blackceomacmini"
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

# ─── OPAQUE-ID FILTER (the EXEMPT list, enforced at load time) ────────────────
# Returns 0 (true) when a roster line is an OPAQUE IDENTIFIER rather than a human
# name. Opaque IDs are EXEMPT (see the header) and must never become scan terms:
# a Telegram chat ID / GHL location ID / UUID / AUD tag / hash is infrastructure,
# not a client's identity. Older operator roster files may still contain them;
# this filter makes the gate correct regardless of what is on the operator's disk.
#
# A line is an opaque ID when it is:
#   • pure numeric ................ 8123456789            (Telegram chat ID)
#   • whitespace-free w/ a digit ... aB3xKp9QrTn2LmVw7ZcY (GHL location ID, UUID,
#                                    AUD tag, hash — these are base62/hex blobs)
#   • whitespace-free and >=16 chars (a long opaque blob with no digits)
# A human name always has whitespace ("Jane Doe") or is a short \b-anchored
# first-name pattern ("\bJane\b") — neither of which matches the above.
_is_opaque_id() {
  local line="$1"
  case "$line" in
    *[[:space:]]*) return 1 ;;                       # has whitespace -> a name
  esac
  case "$line" in
    *[0-9]*) return 0 ;;                             # digit + no space -> opaque
  esac
  [ "${#line}" -ge 16 ] && return 0                  # long opaque blob
  return 1
}

# Load roster HUMAN NAMES into CLIENT_NAMES (comments/blanks stripped, opaque IDs
# filtered out). Returns 0 and sets ROSTER_AVAILABLE=1 if at least one name was
# read; else 1.
CLIENT_NAMES=()
ROSTER_AVAILABLE=0
_load_roster() {
  local f; f="$(_roster_path)"
  [ -f "$f" ] || return 1
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    _is_opaque_id "$line" && continue   # EXEMPT — never a scan term
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
      sed -n '1,72p' "$0"
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
    # ─── PRODUCT TREE — EXEMPT (book titles / personas / authors) ─────────────
    # These directories are named after the AUTHORS of published books and hold
    # book-derived PERSONA content. Authors of referenced works, book titles and
    # persona names are on the EXEMPT list — they are PRODUCT, not client data.
    # A single roster first-name collision here would fail every persona PR
    # forever, which is exactly the over-reach this gate is being corrected for.
    # The LLM reviewer (scripts/qc-llm-diff-review.py) is what reviews this tree:
    # it can tell a book persona from a customer; a regex cannot.
    */22-book-to-persona-coaching-leadership-system/personas/*) return 0 ;;
    */personas/*)                                  return 0 ;;
    */persona-catalog*)                            return 0 ;;
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
  echo "[qc-assert-no-client-names] INVARIANT VIOLATED — $HITS client/roster human-name hit(s) found in repo files:"
  for line in "${OFFENDERS[@]}"; do
    echo "$line"
  done
  echo
  echo "REMEDY: replace each real client/roster HUMAN NAME with a generic placeholder."
  echo "  Prose: 'a client VPS', 'a Mac mini client box', 'a ZHC closeout client'"
  echo "  JSON examples: '{{ownerName}}', 'Sample Company', '{{agentName}}'"
  echo
  echo "NOT A VIOLATION (EXEMPT — if the gate flagged one of these, the gate is wrong):"
  echo "  Cloudflare Access Application UUIDs / AUD tags · Telegram chat IDs ·"
  echo "  GHL location IDs · any opaque identifier (UUID, numeric ID, hash) ·"
  echo "  book titles · persona names derived from books · authors of referenced"
  echo "  works · product proper nouns."
  echo "  Opaque infrastructure identifiers and product content are NOT the target."
  echo
  echo "  See AGENTS.md → 'FLEET-REPO CONTENT RULE' for the full rule."
  exit 1
fi

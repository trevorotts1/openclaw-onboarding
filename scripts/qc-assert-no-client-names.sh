#!/usr/bin/env bash
# qc-assert-no-client-names.sh — v2.5.0
#
# v2.5.0 FIX (CRITICAL-1 escaped detection — only ~25% effective): a real
# client's identity was found committed in 4 tracked-file locations while
# this gate reported PASS. Root cause: a two-word roster entry is loaded as
# the literal "First Last" string, which only matches when both words appear
# together with a single space — so 1 of the 4 occurrences matched (the full
# name) and 3 did not (first name alone in prose, a
# <firstname>.zerohumanworkforce.com hostname, and a
# bak-<firstname>-...-<date> backup-filename suffix). FIX:
# scripts/qc-expand-roster-name-forms.py now derives first-name/last-name-
# alone and hyphen/underscore/fused-compound forms from every multi-word
# roster entry and folds them into the same scan pattern — see that script's
# header for the two-tier precision guard (self-corroborating compounds get
# no filter; standalone single words are dropped when they also read as
# ordinary English, via the same dictionary check
# qc-derive-roster-from-accounts.py already uses for single-word candidates,
# so a client literally named a common word does not flag ordinary prose
# everywhere). Never echoes a name; only pattern shapes are described here.
#
# v2.4.0 FIX (bypass was unprovable): --no-verify leaves no trace, and until
# now this gate wrote nothing durable of its own, so "the gate was never
# bypassed" was a claim that could never be proven either way. FIX: every
# real exit path now appends ONE line (timestamp, calling context — a commit
# SHA / GITHUB_SHA when known, or the literal "pre-push" — and the verdict)
# to an append-only log OUTSIDE the repo ($OPENCLAW_GATE_LOG_DIR or
# ~/.openclaw/logs/qc-assert-no-client-names.log). A --no-verify commit/push
# never calls this script at all, so its ABSENCE from the log on a given SHA
# is itself the evidence of a bypass. The log never records a matched name,
# path, or line — only the hit COUNT — so it can never itself become a
# second leak surface.
#
# v2.3.0 FIX (CI green without weakening fail-closed): v2.2.0 made structural
# mode exit 2 in CI. But CI can NEVER have a roster — a bare GitHub runner has
# no operator-local files BY DESIGN, and putting client PII into CI secrets was
# explicitly rejected. So v2.2.0's CI exit-2 was not a gate that could ever
# pass; it was a permanently red battery that blocked every PR. FIX: in CI,
# structural mode now REPORTS ONLY — exit 0 with a loud ::warning:: workflow
# annotation plus the full CANNOT VERIFY stderr message, so every CI run shows
# exactly what was and was not verified (never a silent pass). The hard gate
# lives where a roster genuinely exists: locally and in .githooks/pre-commit,
# where structural mode STILL exits 2 (fail closed) and any roster hit exits 1.
# Positive hits are UNCHANGED everywhere: an always-on-token hit or a roster
# hit fails (exit 1) in CI and locally alike. Only the "cannot verify in CI"
# state moved from red to annotated-green — nothing that CAN be checked was
# weakened.
#
# v2.1.0 FIX (fleet-embeddings-CI-blind-spot): STRUCTURAL mode used to exit 0
# ("PASS (structural)") whenever no roster was available — which is EVERY run
# on a bare GitHub Actions runner, since CI never has $OPENCLAW_CLIENT_ROSTER
# or ~/.openclaw/client-roster.txt. That meant the CRITICAL-1 CI step
# (.github/workflows/qc-static.yml) had run the roster-specific check exactly
# zero times in this repo's history and always reported success regardless.
# FIX: when running under a real CI environment (GITHUB_ACTIONS=true / CI=true
# — GitHub's own default env vars) AND no roster is available, this exits
# non-zero with an unambiguous "CANNOT VERIFY" message instead of a silent
# PASS. A gate that cannot do its job must never report success.
#
# v2.2.0 FIX (the roster had never run ANYWHERE, not just CI): v2.1.0 scoped
# the fail-closed fix to CI only, to avoid hard-blocking local commits on
# operator boxes that also had no curated roster — including, it turned out,
# the primary operator Mac itself: NO box had ever had a curated
# ~/.openclaw/client-roster.txt. So v2.1.0 bought an honest CI red light
# while the actual per-name check still ran nowhere, ever — a better-labeled
# gap, not a closed one. FIX: scripts/qc-derive-roster-from-accounts.py
# derives a real roster STRUCTURALLY, at runtime, from the fleet's own
# ~/clawd/accounts/accounts.md ($OPENCLAW_ACCOUNTS_MD to override) — data
# that already exists locally and is never committed, printed, or logged by
# name. When neither a curated roster NOR an accounts.md derivation is
# available, structural mode now reports CANNOT VERIFY in EVERY environment,
# not just CI — "no roster anywhere" is a genuinely exceptional state now
# that a real local source exists, not the default everywhere.
# A second, independent, roster-free signal (scripts/qc-heuristic-name-shapes.py)
# also runs in every mode as an ADVISORY (non-blocking) floor — see that
# script's header for why it is advisory rather than a hard gate (measured
# false-positive rates at three scopes, all unusable as a blocking check on
# this repo's own tracked tree).
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
#   0  — no client names found (PASS), OR structural CANNOT VERIFY in CI
#        (report-only there: ::warning:: annotation + stderr message; CI can
#        never hold a roster by design, so the unverifiable state is surfaced
#        loudly instead of blocking every PR)
#   1  — one or more client names found (FAIL — block commit/QC, all envs)
#   2  — structural CANNOT VERIFY locally / in pre-commit (FAIL CLOSED — a
#        roster genuinely exists on operator boxes via accounts.md, so "no
#        roster anywhere" is exceptional and must block)
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

# ─── DERIVED roster fallback (no curated file needed) ──────────────────────
# scripts/qc-derive-roster-from-accounts.py builds a roster STRUCTURALLY from
# ~/clawd/accounts/accounts.md ($OPENCLAW_ACCOUNTS_MD to override) — the real,
# already-existing local source of the fleet roster. This exists because a
# curated ~/.openclaw/client-roster.txt has never actually been created on
# ANY operator box (this repo's own pre-fix history proves it: the roster-
# specific check has run exactly zero times anywhere, CI or local). Without
# this, "make CI fail closed" alone would only convert a false PASS into an
# honest but permanently-empty CANNOT VERIFY — the roster-specific check
# still never runs anywhere. This is what makes it actually run, on the one
# machine that has the data to run it with.
# NEVER echoes a derived name — only appends to CLIENT_NAMES in-process via
# process substitution (no temp file, nothing written to disk, nothing
# printed to this script's own stdout/stderr).
_load_derived_roster() {
  local derive_script="$SCRIPT_DIR/qc-derive-roster-from-accounts.py"
  [ -f "$derive_script" ] || return 1
  command -v python3 >/dev/null 2>&1 || return 1
  local line
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    CLIENT_NAMES+=("$line")
  done < <(python3 "$derive_script" 2>/dev/null)
  [ "${#CLIENT_NAMES[@]}" -gt 0 ]
}
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ─── Fast grep binary (v2.5.0) ─────────────────────────────────────────────
# The v2.5.0 expanded pattern set (see below) roughly triples the number of
# alternatives in the scan regex. Measured directly on this repo's own
# ~7,000 tracked files: macOS's system BSD grep takes ~20s for a 30-
# alternative case-insensitive scan; GNU grep (Homebrew's `ggrep`, or plain
# `grep` when it's already GNU — e.g. every Linux CI runner) does the SAME
# scan in ~1.3s. A gate slow enough to make a pre-commit hook painful gets
# `--no-verify`'d, which is the same "gate that cannot do its job" failure
# mode as a false-positive flood — so prefer the fast engine when present,
# and silently keep working on the slower one otherwise (this is a
# performance choice, not a correctness one: both engines return identical
# matches for the ERE patterns this script builds).
GREP_BIN="grep"
if command -v ggrep >/dev/null 2>&1; then
  GREP_BIN="ggrep"
elif grep --version 2>/dev/null | head -1 | grep -q "GNU grep"; then
  GREP_BIN="grep"
fi

# ─── Durable audit log (OUTSIDE the repo) ──────────────────────────────────
# Fix for "--no-verify leaves no trace, so 'the gate was never bypassed' is
# unprovable": this gate now writes ONE append-only line per invocation to a
# path outside the repo tree, so the evidence survives even a skipped hook,
# a fresh clone, or a wiped working tree (a --no-verify commit/push simply
# never calls this script, so its ABSENCE from the log is itself the record).
# Format: timestamp | context=<commit SHA, GITHUB_SHA, or the literal
# "pre-push"> | result=<verdict> | exit=<code> | hits=<count> | mode=<mode>.
# NEVER writes a matched name, path, or line — only counts — so the log
# itself can never become a second place a client name leaks.
GATE_LOG_DIR="${OPENCLAW_GATE_LOG_DIR:-${HOME:-/root}/.openclaw/logs}"
GATE_LOG_FILE="$GATE_LOG_DIR/qc-assert-no-client-names.log"
_log_gate_run() {
  local result="$1" exit_code="$2"
  local ts context
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo 'unknown-time')"
  if [ -n "${QC_GATE_CONTEXT:-}" ]; then
    context="$QC_GATE_CONTEXT"
  elif [ -n "${GITHUB_SHA:-}" ]; then
    context="$GITHUB_SHA"
  else
    context="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo 'no-git-head')"
  fi
  mkdir -p "$GATE_LOG_DIR" 2>/dev/null
  printf '%s | context=%s | result=%s | exit=%s | hits=%s | mode=%s\n' \
    "$ts" "$context" "$result" "$exit_code" "${HITS:-0}" "${MODE:-unset}" \
    >> "$GATE_LOG_FILE" 2>/dev/null
  return 0
}

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,56p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1" >&2; _log_gate_run "USAGE_ERROR" 2; exit 2 ;;
  esac
done

# Detect a real CI environment. Both vars are set automatically by GitHub
# Actions on every run ("Always set to true" per GitHub's own docs) — this is
# environment introspection, not a credential and not invented: it is the
# documented, standard way a script tells "running in CI" from "running on a
# human's machine". https://docs.github.com/en/actions/reference/workflows-and-actions/variables
IS_CI=0
if [ "${GITHUB_ACTIONS:-}" = "true" ] || [ "${CI:-}" = "true" ]; then
  IS_CI=1
fi

# Load a roster and decide the mode. THREE tiers, most-authoritative first:
#   1. Curated roster ($OPENCLAW_CLIENT_ROSTER or ~/.openclaw/client-roster.txt)
#   2. DERIVED roster (structurally parsed from ~/clawd/accounts/accounts.md)
#   3. Neither available -> structural, no per-name check ran ANYWHERE.
ROSTER_SOURCE=""
if _load_roster; then
  MODE="full"
  ROSTER_SOURCE="curated"
else
  echo "WARNING: curated client-name roster not found (looked in" \
       "\$OPENCLAW_CLIENT_ROSTER, then ${HOME:-/root}/.openclaw/client-roster.txt)." \
       "Trying the accounts.md-derived roster next." >&2
  if _load_derived_roster; then
    MODE="full"
    ROSTER_SOURCE="derived"
    echo "NOTE: no curated roster; loaded a roster DERIVED structurally from" \
         "accounts.md instead (see qc-derive-roster-from-accounts.py's own count" \
         "line above — no names are echoed here or there). This is a real," \
         "roster-based check, not the no-roster fallback." >&2
  else
    MODE="structural"
    echo "WARNING: the accounts.md-derived roster is ALSO unavailable (missing," \
         "unreadable, or produced zero candidates — see" \
         "qc-derive-roster-from-accounts.py's own stderr above). SKIPPING the" \
         "roster-specific client-name check entirely: no source could run it in" \
         "this environment. Always-on tokens (operator path + .example" \
         "placeholders) are still enforced below, but that is NOT the same" \
         "check and this run CANNOT report a full PASS on that basis." >&2
    if [ "$IS_CI" = 1 ]; then
      echo "NOTE: this is a CI environment (GITHUB_ACTIONS/CI=true) — CI can never" \
           "have either roster source by design (no operator-local files exist on a" \
           "bare runner), so this is expected here and is REPORTED ONLY (warning" \
           "annotation, exit 0) below — the blocking per-name gate runs locally /" \
           "in pre-commit where a roster exists." >&2
    fi
  fi
fi

# Build the ERE alternation pattern(s): always-on tokens in both modes, plus
# the external roster patterns when a roster is available. v2.5.0 splits this
# into TWO alternations at two different precision tiers — see
# scripts/qc-expand-roster-name-forms.py's header for the full rationale:
#   PATTERN     (case-INSENSITIVE scan) — always-on tokens, the roster's own
#     full-name/single-word literals (UNCHANGED from pre-v2.5.0), plus the
#     "CI:" expansion forms (compounds + hostname- and backup-filename-
#     corroborated forms), all of which carry their own corroborating
#     structure so case-insensitivity does not flood the scan with ordinary-
#     prose collisions.
#   CS_PATTERN  (case-SENSITIVE scan) — the "CS:" expansion forms only
#     (bare first-name/last-name-alone \bWord\b patterns). Measured on this
#     repo's own tracked tree: case-INSENSITIVE bare-word matching produced
#     100+ false-positive file hits per noisy candidate; every one of those
#     vanished under an exact-case match, with zero measured recall loss
#     (real name mentions in prose are capitalized the same way the roster
#     derived them). Kept as a SEPARATE pass (not folded into PATTERN)
#     specifically so it does not inherit -i.
SCAN_TOKENS=("${ALWAYS_ON_TOKENS[@]}")
CS_TOKENS=()
if [ "$MODE" = "full" ]; then
  SCAN_TOKENS+=("${CLIENT_NAMES[@]}")
  # v2.5.0 FIX (CRITICAL-1 escaped detection): a two-word roster entry is
  # loaded above as the literal "First Last" — it only matches when BOTH
  # words appear together, in that order, with a single space. A real client
  # leaked into 4 tracked-file locations while this gate reported PASS: 1
  # occurrence matched the full-name literal; the other 3 used the first
  # name ALONE (prose + a <firstname>.zerohumanworkforce.com hostname) and a
  # bak-<firstname>-... backup-filename suffix, none of which contain the
  # full-name substring. scripts/qc-expand-roster-name-forms.py derives the
  # additional forms that catch that class. Never echoes a name; only new
  # ERE patterns, each tagged "CI:" or "CS:", cross this pipe.
  EXPAND_SCRIPT="$SCRIPT_DIR/qc-expand-roster-name-forms.py"
  if [ -f "$EXPAND_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
    while IFS= read -r tagged_pattern; do
      [ -z "$tagged_pattern" ] && continue
      case "$tagged_pattern" in
        CI:*) SCAN_TOKENS+=("${tagged_pattern#CI:}") ;;
        CS:*) CS_TOKENS+=("${tagged_pattern#CS:}") ;;
      esac
    done < <(printf '%s\n' "${CLIENT_NAMES[@]}" | python3 "$EXPAND_SCRIPT" 2>/dev/null)
  fi
fi
PATTERN=$(printf '%s\n' "${SCAN_TOKENS[@]}" | paste -sd'|' -)
# CS_PATTERN is finalized further below, AFTER the tracked-file list exists —
# see the "ambient-frequency filter" block near the scan loop for why.

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
    # v2.5.0: directories whose LEGITIMATE, intended content is real public
    # figures' names — not clients. Measured on this repo's own tree while
    # building the v2.5.0 expanded detection: a roster candidate's surname
    # collided with a real, unrelated, published author cited by this skill's
    # own core content (e.g. a book-persona extraction citing that book's
    # actual author). This is structural, not a one-off: every file in this
    # directory is, by the skill's own design, a summary of a named, publicly
    # published book — proper names are the intended content, not incidental.
    */22-book-to-persona-coaching-leadership-system/personas/*) return 0 ;;
    # The operator co-mingling-guard skill exists specifically to repeatedly
    # name the BlackCEO operator team (Trevor / LeAnne / Spaulding) so a
    # client box never routes to them as "workers" — see this script's own
    # ALWAYS_ON_TOKENS comment: "the AGENCY and operator team members are NOT
    # clients." One operator team member's surname also happens to match a
    # roster candidate; excluding the directory whose entire purpose is
    # naming the operator team is the structural fix, not a one-off.
    */15-blackceo-team-management/*)               return 0 ;;
    # Single-occurrence public-figure citations, confirmed by manual review
    # during the v2.5.0 sweep — each is a specific book/author reference in
    # role-library "recommended reading" material (reused verbatim across
    # every client, not client-specific), or a real public entrepreneur's
    # name used as a Facebook ad-interest-targeting keyword (not a person
    # this repo is about). Listed individually (not directory-scoped) because
    # each is an isolated collision, not a systemic pattern like the two
    # directories above.
    */23-ai-workforce-blueprint/templates/role-library/app-development/deep-research-specialist-app-development.md) return 0 ;;
    */23-ai-workforce-blueprint/templates/role-library/_stage1_drafts/app-development/deep-research-specialist-app-development.md) return 0 ;;
    */23-ai-workforce-blueprint/templates/role-library/graphics/presentation-designer-slides-decks.md) return 0 ;;
    */23-ai-workforce-blueprint/templates/role-library/_stage1_drafts/graphics/presentation-designer-slides-decks.md) return 0 ;;
    */23-ai-workforce-blueprint/templates/role-library/openclaw-maintenance/deep-research-role--openclaw-maintenance.md) return 0 ;;
    */23-ai-workforce-blueprint/templates/role-library/_stage1_drafts/openclaw-maintenance/deep-research-role--openclaw-maintenance.md) return 0 ;;
    */42-personal-assistant-library/specialists/07-brainstorming-ideation/governing-personas.md) return 0 ;;
    */42-personal-assistant-library/specialists/07-brainstorming-ideation/how-to.md) return 0 ;;
    */52-avatar-alchemist/prompts/15-facebook-audiences/user.md) return 0 ;;
    */44-convert-and-flow-operator/tools/check-ghl-token-liveness.sh) return 0 ;;
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

# ─── v2.5.0: ambient-frequency filter for CS_TOKENS (standalone bare-word
# forms) ─────────────────────────────────────────────────────────────────
# A standalone \bWord\b form (case-sensitive, dictionary-filtered) can still
# collide with THIS repo's own vocabulary in ways a literary dictionary
# check cannot catch — Title Case is the default casing for markdown
# headers and table headers throughout ~7,000 tracked files, so a roster
# word component that ALSO happens to double as ordinary repo vocabulary
# floods the gate exactly the way a client literally named "Grace" or
# "Mark" was the risk to guard against. MEASURED on this repo's own tree
# before shipping: every genuinely name-shaped CS candidate matched 7 or
# fewer tracked files; one candidate that also reads as an ordinary
# business/doc term matched 108 — a two-order-of-magnitude gap with a clean
# separation, not a borderline call.
# FIX: before a CS_TOKEN is allowed to BLOCK, pre-check how many tracked
# files it matches on THIS run's own tree. A real, isolated identity leak
# appears in a handful of related files; a token that saturates the repo is
# functionally indistinguishable from ordinary vocabulary regardless of
# what generated it. Tokens over the ceiling are dropped from the blocking
# CS_PATTERN and reported via a single ADVISORY count to stderr instead
# (never the word itself, never which candidate) — the same non-blocking-
# but-visible treatment this script already gives
# qc-heuristic-name-shapes.py's own measured-too-noisy findings. The full
# multi-word name literal, and the compound/hostname/backup-filename forms
# for the SAME roster entry, remain fully enforced above regardless — this
# filter only ever removes the single riskiest form, never the others.
CS_AMBIENT_FILE_CEILING=10
CS_TOKENS_FILTERED=()
CS_TOKENS_SUPPRESSED=0
if [ "${#CS_TOKENS[@]}" -gt 0 ] && [ "${#FILES[@]}" -gt 0 ]; then
  for cs_tok in "${CS_TOKENS[@]}"; do
    tok_file_count=$(printf '%s\0' "${FILES[@]}" \
      | xargs -0 "$GREP_BIN" -E -l "$cs_tok" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${tok_file_count:-0}" -gt "$CS_AMBIENT_FILE_CEILING" ]; then
      CS_TOKENS_SUPPRESSED=$((CS_TOKENS_SUPPRESSED + 1))
    else
      CS_TOKENS_FILTERED+=("$cs_tok")
    fi
  done
  if [ "$CS_TOKENS_SUPPRESSED" -gt 0 ]; then
    echo "NOTE: $CS_TOKENS_SUPPRESSED standalone-name detection pattern(s) suppressed" \
         "(matched more than $CS_AMBIENT_FILE_CEILING tracked files ambiently on this run —" \
         "indistinguishable from ordinary repo vocabulary at this scope, so NOT enforced" \
         "as a blocking check here; the full name, and the hostname/backup-filename/" \
         "compound forms for the same roster entries, are still enforced above)." >&2
  fi
fi
CS_PATTERN=""
[ "${#CS_TOKENS_FILTERED[@]}" -gt 0 ] && CS_PATTERN=$(printf '%s\n' "${CS_TOKENS_FILTERED[@]}" | paste -sd'|' -)

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
             | xargs -0 "$GREP_BIN" -E -Hin "$PATTERN" 2>/dev/null)

  # v2.5.0: second pass, CASE-SENSITIVE, for the "CS:" standalone bare-word
  # forms only (see the PATTERN/CS_PATTERN build comment above for why this
  # cannot be folded into the -i pass above). Same per-file cap, same
  # OFFENDERS/HITS accounting — a hit is a hit regardless of which pass
  # found it.
  if [ -n "$CS_PATTERN" ]; then
    while IFS= read -r hit_line; do
      [ -z "$hit_line" ] && continue
      path="${hit_line%%:*}"
      n=$(( ${_PER_FILE_HITS["$path"]:-0} + 1 ))
      _PER_FILE_HITS["$path"]=$n
      [ "$n" -gt 20 ] && continue
      OFFENDERS+=("  $hit_line")
      HITS=$((HITS + 1))
    done < <(printf '%s\0' "${FILES[@]}" \
               | xargs -0 "$GREP_BIN" -E -Hn "$CS_PATTERN" 2>/dev/null)
  fi
fi

# ─── Advisory (non-blocking) roster-free floor ─────────────────────────────
# Independent second signal, needs no roster, runs in EVERY mode. Never
# touches HITS or the exit code — see scripts/qc-heuristic-name-shapes.py's
# header for why it is advisory rather than a gate (measured false-positive
# rates at three scopes on this repo's own tree, all unusable as a blocker).
HEURISTIC_SCRIPT="$SCRIPT_DIR/qc-heuristic-name-shapes.py"
if [ -f "$HEURISTIC_SCRIPT" ] && command -v python3 >/dev/null 2>&1; then
  python3 "$HEURISTIC_SCRIPT" --repo-root "$REPO_ROOT" || true
fi

if [ "$HITS" -eq 0 ]; then
  if [ "$MODE" = "full" ]; then
    if [ "$ROSTER_SOURCE" = "derived" ]; then
      echo "[qc-assert-no-client-names] PASS (full, roster DERIVED from accounts.md) — no derived-roster client names, operator paths, or placeholder leaks in tracked files."
    else
      echo "[qc-assert-no-client-names] PASS (full, curated roster) — no roster client names, operator paths, or placeholder leaks in tracked files."
    fi
    _log_gate_run "PASS" 0
    exit 0
  else
    # Structural mode (no roster from EITHER source — curated file or
    # accounts.md derivation) must NEVER report a bare PASS, in any
    # environment. A check that did not run must never report success.
    if [ "$IS_CI" = 1 ]; then
      # v2.3.0: CI is REPORT-ONLY for the unverifiable state. CI can never
      # have a roster by design (no operator-local files on a bare runner;
      # client PII must never be provisioned into CI secrets), so exiting 2
      # here was not an enforceable gate — it was a permanently red battery
      # blocking every PR. Instead: exit 0, but surface the CANNOT VERIFY
      # loudly as a workflow annotation (shows in the run's Annotations
      # summary) plus the full stderr message. Nothing that CAN be verified
      # in CI was weakened: always-on-token hits and (when a roster IS
      # present, e.g. a self-hosted runner) roster hits still exit 1.
      # The HARD gate for the per-name check lives where a roster genuinely
      # exists: local runs and .githooks/pre-commit on the operator box,
      # where this same state still exits 2 (fail closed) below.
      echo "::warning title=qc-assert-no-client-names::CANNOT VERIFY (structural, CI) — no roster source exists on a bare CI runner by design, so the roster-specific per-name check DID NOT RUN here. Always-on tokens were checked and are clean. The blocking per-name gate runs locally, and in .githooks/pre-commit only on a clone where scripts/install-git-hooks.sh has been run."
      echo "[qc-assert-no-client-names] CANNOT VERIFY (structural, CI — report-only) — neither a curated roster nor an accounts.md-derived roster is available in this CI environment (CI never has either — no operator-local files exist on a bare runner, and client PII is intentionally never provisioned into CI secrets), so the roster-specific per-name check DID NOT RUN. Always-on tokens (operator path + .example placeholder leaks) were checked and are clean, but that alone does NOT mean 'no client names' — this is NOT a pass of the per-name check. See the ADVISORY heuristic output above for a second, non-authoritative signal. The blocking per-name gate runs locally, and in .githooks/pre-commit only on a clone where scripts/install-git-hooks.sh has been run, where the accounts.md-derived roster exists and this same state fails closed (exit 2)." >&2
      _log_gate_run "CANNOT_VERIFY_CI_REPORT_ONLY" 0
      exit 0
    else
      # LOCAL / pre-commit: a roster genuinely exists on this class of machine
      # (accounts.md derivation), so "no roster anywhere" is a genuinely
      # exceptional state — FAIL CLOSED.
      echo "[qc-assert-no-client-names] CANNOT VERIFY (structural) — neither \$OPENCLAW_CLIENT_ROSTER / ~/.openclaw/client-roster.txt NOR an accounts.md-derived roster could be loaded (see the WARNINGs above for which one failed and why), so the roster-specific per-name check DID NOT RUN. Always-on tokens (operator path + .example placeholder leaks) were checked and are clean, but that alone does NOT mean 'no client names'. Fix: provide a curated roster, or point \$OPENCLAW_ACCOUNTS_MD at a readable accounts.md-shaped file (default ~/clawd/accounts/accounts.md)." >&2
      _log_gate_run "CANNOT_VERIFY_FAIL_CLOSED" 2
      exit 2
    fi
  fi
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
  _log_gate_run "FAIL_HITS_FOUND" 1
  exit 1
fi

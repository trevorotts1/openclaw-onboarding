#!/usr/bin/env bash
# qc-config-schema-safety.sh — machine-enforce that NO Skill 38 install script
# writes a config shape that fails `openclaw config validate` on 2026.5.27, and
# that no script uses jq syntax that jq 1.7 rejects.
#
# ROOT CAUSE this gate kills (verified on a live 2026.5.27 box):
#   1. Writing the legacy `.cron.jobs` config block — crons MUST go through the
#      gateway cron store (`openclaw cron add`). `.cron.jobs` => config validate
#      fails ("cron: Invalid input").
#   2. Writing `agents.defaults.async` / `agents.defaults.batch` model keys —
#      these are NOT in the schema => config validate fails ("Invalid input").
#   3. A leading `.hooks //= {};` (or any `<path> //= …;`) jq statement — jq 1.7
#      REJECTS the `;` top-level separator with a compile error, so the merge
#      never runs and the hook config is never written.
#
# HOW IT CHECKS: static scan over the numbered install scripts (00–24) +
# skill38-calendar-sync.sh, looking for the BAD PATTERNS *as jq/config code*
# (jq mutation/read expressions), not the explanatory PROSE that documents why
# they are banned. Prose is excluded two ways: (a) full-line `#` comments are
# stripped; (b) any line whose only occurrence is inside an `echo`/`printf`
# string is ignored. Each pattern is anchored to its jq form (a leading `.`,
# `(.`, or `| .`) so an operator-facing sentence that merely names the key is
# not flagged.
#
# Pure BASH (so it respects qc-static's ban on claude-/anthropic strings in .py).
# Exit 0 = clean; 1 = a config-invalidating / jq-1.7-invalid pattern found.
#
# Usage:
#   bash scripts/qc-config-schema-safety.sh
#   bash scripts/qc-config-schema-safety.sh --scripts-dir DIR

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPTS_DIR="$SCRIPT_DIR"

while [ $# -gt 0 ]; do
  case "$1" in
    --scripts-dir) SCRIPTS_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,40p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

echo "=== qc-config-schema-safety: scanning $SCRIPTS_DIR ==="

FAIL=0

# Collect the numbered install scripts + calendar-sync (the ones that touch config).
TARGETS=()
for f in "$SCRIPTS_DIR"/[0-9][0-9]-*.sh "$SCRIPTS_DIR"/skill38-calendar-sync.sh; do
  [ -f "$f" ] && TARGETS+=("$f")
done

if [ "${#TARGETS[@]}" -eq 0 ]; then
  echo "  [FAIL] no install scripts found under $SCRIPTS_DIR"
  exit 1
fi

# code_lines: emit non-comment lines that are NOT pure prose, so the pattern
# checks only see real jq/config code. Prose that merely NAMES a banned key —
# `#` comments, `echo`/`printf` strings, and the QC reporter wrappers
# (report_pass/report_fail/section/echo) — is not a violation.
code_lines() {
  grep -vE '^[[:space:]]*#' "$1" \
    | grep -vE '^[[:space:]]*(echo|printf|report_pass|report_fail|section)[[:space:]]'
}

# scan PATTERN LABEL FIXHINT — flag any target whose code matches PATTERN.
scan() {
  local pattern="$1" label="$2" hint="$3" f hits
  for f in "${TARGETS[@]}"; do
    hits="$(code_lines "$f" | grep -nE "$pattern" || true)"
    if [ -n "$hits" ]; then
      echo "  [FAIL] $(basename "$f"): $label ($hint):"
      printf '%s\n' "$hits" | sed 's/^/        /'
      FAIL=1
    fi
  done
}

# 1. Legacy `.cron.jobs` as a jq path (leading `.`, `(.`, or `| .`).
scan '(^|[^A-Za-z0-9_(])\(?\.cron\.jobs' \
  "writes/reads the legacy '.cron.jobs' config block" \
  "use 'openclaw cron add' — .cron.jobs fails config validate on 2026.5.27"

# 2. Unsupported `agents.defaults.async` / `.batch` model keys as a jq path.
scan '(^|[^A-Za-z0-9_(])\(?\.agents\.defaults\.(async|batch)' \
  "writes the unsupported 'agents.defaults.async/.batch' model key(s)" \
  "not in the 2026.5.27 schema — persist tier models to secrets.env instead"

# 3. jq `<path> //= <expr>;` — jq 1.7 rejects the top-level ';' separator.
scan '//=.*;' \
  "uses jq '//= …;' (the ';' top-level separator)" \
  "jq 1.7 rejects it — use '= (… // …) |' instead"

# 4. Sourcing the master-files POINTER file (a bare path / directory) with `.`/`source`.
#    The pointer holds a bare PATH, not KEY=value — `. <dir>` errors "Is a directory".
scan '(^|[[:space:];])(\.|source)[[:space:]]+.*\.skill-38-master-files-dir' \
  "sources the master-files pointer (bare path / directory)" \
  "read it with MASTER_FILES_DIR=\"\$(head -n1 <pointer>)\" — '. <pointer>' errors 'Is a directory'"

# 5. Hardcoded legacy skill path (the directory no longer exists; resolve dynamically
#    from the script's own location).
scan 'clawd/skills/38-openclaw-cloudflare-tunnel' \
  "hardcoded legacy skill path" \
  "~/clawd/skills/38-openclaw-cloudflare-tunnel no longer exists — resolve from \"\$(cd \"\$SCRIPT_DIR/..\" && pwd)\""

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — no config-invalidating writes and no jq-1.7-invalid programs in the install scripts."
  exit 0
else
  echo "RESULT: FAIL — a config-invalidating pattern (or jq-1.7-invalid program) is present. See above."
  exit 1
fi

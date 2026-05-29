#!/usr/bin/env bash
# qc-config-keys.sh — machine-enforce that no install script writes a config shape
# that INVALIDATES the openclaw 2026.5.27 config (so a fresh install can't ship a
# config that fails `openclaw config validate`), and that no script trips the known
# jq-1.7 / pointer-sourcing install bugs.
#
# WHY (verified on a live 2026.5.27 box, v1.4.11):
#   1. The Model Wizard wrote `agents.defaults.async` / `agents.defaults.batch` keys —
#      REJECTED by the .strict() 2026.5.27 schema (config validate FAILS).
#   2. Crons were written as a `cron.jobs` JSON config block — does NOT validate on
#      2026.5.27 (must be registered via `openclaw cron add`).
#   3. A jq merge used the top-level `.hooks //= {};` form — jq 1.7+ REJECTS it
#      ("syntax error, unexpected ';'").
#   4. Scripts `source`d the master-files POINTER file (a bare path / directory) —
#      `. <dir>` errors "Is a directory".
#
# This gate scans scripts/*.sh and FAILS (exit 1) if any of those anti-patterns
# reappear. It is BASH-only (no .py — qc-static bans claude-/anthropic strings in .py
# under 22/23, and keeping this gate in bash sidesteps that entirely) and runs in CI.
#
# Exit codes: 0 = clean; 1 = at least one config-invalidating / install-breaking pattern.
#
# Usage:
#   bash scripts/qc-config-keys.sh
#   bash scripts/qc-config-keys.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help)   sed -n '1,30p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

SCRIPTS_DIR="$SKILL_DIR/scripts"
if [ ! -d "$SCRIPTS_DIR" ]; then
  echo "RESULT: NO SCRIPTS DIR ($SCRIPTS_DIR) — the scan target moved. Treating as FAIL."
  exit 1
fi

# This QC script must exclude ITSELF (it intentionally names the banned patterns in
# comments/regex above).
SELF="$SCRIPT_DIR/qc-config-keys.sh"

FAIL=0
note_fail() { echo "  [FAIL] $1"; echo "         $2"; FAIL=1; }

echo "=== qc-config-keys: install-script config-invalidating / install-breaking pattern gate ==="
echo "skill_dir : $SKILL_DIR"
echo ""

for f in "$SCRIPTS_DIR"/*.sh; do
  [ -f "$f" ] || continue
  [ "$f" = "$SELF" ] && continue
  rel="${f#"$SKILL_DIR"/}"

  # 1. Invalid model-tier keys (agents.defaults.async / agents.defaults.batch WRITES).
  #    A jq WRITE is the dotted key immediately followed by `//=` or by a single `=`
  #    (assignment), optionally with a deeper `.model` segment first — e.g.
  #    `.agents.defaults.async.model = $as` or `.agents.defaults.batch //= {}`.
  #    READ-backs (`.async.model // empty`) and prose mentions (no immediately-
  #    attached assignment operator) are NOT flagged.
  MTRE='\.agents\.defaults\.(async|batch)(\.[A-Za-z_]+)*[[:space:]]*(//=|=[^=])'
  if grep -nE "$MTRE" "$f" >/dev/null 2>&1; then
    while IFS= read -r line; do
      note_fail "$rel: writes invalid model-tier key" \
        "agents.defaults.async/.batch is rejected by the 2026.5.27 .strict() schema (config validate FAILS). Persist async/batch to secrets.env, only the real-time model goes in agents.list[].model. -> $line"
    done < <(grep -nE "$MTRE" "$f")
  fi

  # 2. Legacy cron.jobs config-block WRITE (any `.cron.jobs ... +=` or `.cron.jobs = ` or
  #    `.cron //= {jobs:` assignment). Reads inside `openclaw cron`-based code are gone;
  #    a `.cron.jobs` assignment means the script writes the invalid block.
  if grep -nE '\.cron(\.jobs)?[[:space:]]*(//=|\+?=)|"jobs"[[:space:]]*:' "$f" >/dev/null 2>&1; then
    while IFS= read -r line; do
      note_fail "$rel: writes legacy cron.jobs config block" \
        "cron.jobs JSON does not validate on 2026.5.27 — register crons via 'openclaw cron add'. -> $line"
    done < <(grep -nE '\.cron(\.jobs)?[[:space:]]*(//=|\+?=)|"jobs"[[:space:]]*:' "$f")
  fi

  # 3. jq-1.7-invalid top-level update-assignment `... //= ... ;` (the trailing ';' is a
  #    program separator jq 1.7+ rejects). Flag any `//=` immediately followed (same line
  #    or via a trailing ';') by a top-level statement separator.
  if grep -nE '//=[^|]*;[[:space:]]*$' "$f" >/dev/null 2>&1; then
    while IFS= read -r line; do
      note_fail "$rel: jq 1.7-invalid '//= ... ;' update-assignment" \
        "jq 1.7+ rejects the top-level '//= {};' form. Use '.x = (.x // {}) | ...' instead. -> $line"
    done < <(grep -nE '//=[^|]*;[[:space:]]*$' "$f")
  fi

  # 4. Sourcing the master-files POINTER file (a bare path / directory) with `.`/`source`.
  #    The pointer holds a bare PATH, not KEY=value — it must be read with cat/head.
  if grep -nE '(^|[[:space:];])(\.|source)[[:space:]]+.*\.skill-38-master-files-dir' "$f" >/dev/null 2>&1; then
    while IFS= read -r line; do
      note_fail "$rel: sources the master-files pointer (bare path / directory)" \
        "'. <pointer>' executes the path — when it is a directory bash errors 'Is a directory'. Read it with: MASTER_FILES_DIR=\"\$(head -n1 <pointer>)\". -> $line"
    done < <(grep -nE '(^|[[:space:];])(\.|source)[[:space:]]+.*\.skill-38-master-files-dir' "$f")
  fi

  # 5. Hardcoded legacy skill path (the directory no longer exists; resolve dynamically
  #    from the script's own location). Only flag bare defaults, not comments.
  if grep -nE 'clawd/skills/38-openclaw-cloudflare-tunnel' "$f" | grep -vE '^[0-9]+:[[:space:]]*#' >/dev/null 2>&1; then
    while IFS= read -r line; do
      note_fail "$rel: hardcoded legacy skill path" \
        "~/clawd/skills/38-openclaw-cloudflare-tunnel no longer exists. Resolve the skill root from the script's own location: \"\$(cd \"\$SCRIPT_DIR/..\" && pwd)\". -> $line"
    done < <(grep -nE 'clawd/skills/38-openclaw-cloudflare-tunnel' "$f" | grep -vE '^[0-9]+:[[:space:]]*#')
  fi
done

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — no install script writes a config-invalidating shape or trips the known jq-1.7 / pointer-sourcing install bugs."
  exit 0
else
  echo "RESULT: FAIL — at least one install script would invalidate the config or break a fresh install (see above)."
  exit 1
fi

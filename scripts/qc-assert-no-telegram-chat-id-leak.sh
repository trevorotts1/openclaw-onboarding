#!/usr/bin/env bash
# qc-assert-no-telegram-chat-id-leak.sh — v1.0.0
#
# STATIC QC INVARIANT: catches Telegram chat-ID leaks that the operator-only
# denylist in qc-assert-no-client-names.sh is STRUCTURALLY BLIND to.
#
# WHY THIS EXISTS (the gap it closes):
#   The existing name/id denylist only knows the three OPERATOR ids
#   (5252140759 / 6663821679 / 6771245262). It has no way to recognise a REAL
#   CLIENT chat id — a client id is just a 9–10 digit integer with no operator
#   fingerprint — so a real client id sails straight through the denylist. That
#   is exactly how the real client id "…4298" shipped inside a sessions.json
#   session key ("agent:main:telegram:direct:<REAL-CLIENT-ID>") in
#   scripts/test-fleet-refresh.sh and a docstring in
#   shared-utils/fleet_refresh_runner.py.
#
# STRATEGY — SHAPE over DENYLIST (repo-safe, no client ids hardcoded):
#   Instead of enumerating forbidden client ids (impossible — we can't ship
#   them), we enumerate the SANCTIONED shapes and fail on everything else.
#
#   PART A — session-key literal (primary, high precision, zero exclusions):
#     Any "…telegram:direct:<N>" where <N> is an 8–10 digit chat-id-shaped
#     integer is a FAIL, UNLESS <N> is the sanctioned placeholder 1234567890.
#     Real client ids ship in this exact shape; placeholders/operator ids never
#     appear in session-key form in this repo.  This alone re-catches the two
#     historical leaks.
#
#   PART B — chat-id-shaped integer in a Telegram-identity context (defence in
#     depth): an 8–10 digit integer sitting next to a telegram-identity token
#     (allowFrom / groupAllowFrom / ownerChatId / chatId / helpChatId / ownerId
#     / "Telegram ID" / *CHAT_ID / telegram:direct) is a FAIL, UNLESS every such
#     id on the line is EXEMPT:
#       • the sanctioned placeholder 1234567890, or
#       • one of the three OPERATOR ids (5252140759 / 6663821679 / 6771245262) —
#         these are non-client operator ids that legitimately appear all over
#         the repo in allowFrom / operator-reject / OPERATOR_CHAT_IDS guards.
#     A handful of fixture / teaching files hold SYNTHETIC (non-real) chat ids as
#     test DATA and are path-excluded from PART B only (see PARTB_EXCLUDE). PART A
#     still scans them, so a real session-key leak there is still caught.
#
#   NOTE: the operator-id allowlist is the INVERSE of the old denylist. The old
#   gate only KNEW operator ids and let clients through; this gate treats the
#   operator ids as the ONLY sanctioned real ids and fails on any *other*
#   chat-id-shaped integer in a telegram context — which is precisely a client id.
#
# PART C — OPTIONAL DENYLIST (box-mode): if the external client roster is present
#   ($OPENCLAW_CLIENT_ROSTER else ~/.openclaw/client-roster.txt) it may list real
#   client chat ids (one numeric id per line). When present, any literal match in
#   a tracked file is a hard FAIL. When absent (CI / structural mode) the shape
#   rules above carry the gate — it NEVER fails open, and NO real client id is
#   ever hardcoded here or in the repo.
#
# Exit codes:
#   0  — no telegram chat-id leak found (PASS)
#   1  — one or more leaks found (FAIL — block commit/QC)
#
# Usage:
#   bash scripts/qc-assert-no-telegram-chat-id-leak.sh
#   bash scripts/qc-assert-no-telegram-chat-id-leak.sh --repo-root /path/to/repo

set -uo pipefail

# ─── Sanctioned literals (NOT client data) ────────────────────────────────────
PLACEHOLDER_ID="1234567890"
# Operator ids: non-client, appear intentionally throughout the repo in
# allowFrom / operator-reject / OPERATOR_CHAT_IDS guards. Hardcoding them here is
# safe (they are not secrets and not client data) and is what lets PART B stay
# zero-false-positive without a client denylist.
OPERATOR_IDS=("5252140759" "6663821679" "6771245262")

# An id is "sanctioned" (exempt) iff it is the placeholder or an operator id.
_is_sanctioned_id() {
  local id="$1"
  [ "$id" = "$PLACEHOLDER_ID" ] && return 0
  local op
  for op in "${OPERATOR_IDS[@]}"; do [ "$id" = "$op" ] && return 0; done
  return 1
}

# ─── External roster (PART C, optional box-mode denylist) ─────────────────────
_roster_path() {
  if [ -n "${OPENCLAW_CLIENT_ROSTER:-}" ]; then
    printf '%s\n' "$OPENCLAW_CLIENT_ROSTER"
  else
    printf '%s\n' "${HOME:-/root}/.openclaw/client-roster.txt"
  fi
}
ROSTER_IDS=()
ROSTER_AVAILABLE=0
_load_roster_ids() {
  local f; f="$(_roster_path)"
  [ -f "$f" ] || return 1
  local line
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|\#*) continue ;; esac
    # Only numeric chat-id-shaped roster entries are relevant to THIS gate
    # (names are handled by qc-assert-no-client-names.sh). Accept 6+ digit ints.
    if printf '%s' "$line" | grep -qE '^[0-9]{6,}$'; then
      ROSTER_IDS+=("$line")
    fi
  done < "$f"
  [ "${#ROSTER_IDS[@]}" -gt 0 ] && ROSTER_AVAILABLE=1
  return 0
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    -h|--help) sed -n '1,80p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

_load_roster_ids || true

# ─── File enumeration (tracked files; find fallback) ──────────────────────────
_list_files() {
  local root="$1"
  if git -C "$root" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "$root" ls-files \
      -- '*.md' '*.sh' '*.json' '*.txt' '*.yaml' '*.yml' '*.py' '*.mjs' \
         '*.js' '*.ts' '*.html' '*.css' '*.toml' '.env' '*.env' \
         '*.template' '*.tmpl' '*.example' '*.sample' '*.tsx' '*.jsx' '*.cjs' \
         '*.conf' '*.cfg' '*.ini' '*.xml' '*.csv' '*.plist' '*.tf' '*.env.template' \
      2>/dev/null \
      | while IFS= read -r rel; do printf '%s/%s\n' "$root" "$rel"; done
  else
    find "$root" \
      -not -path "$root/.git/*" -not -path "$root/.claude/*" \
      \( -name "*.md" -o -name "*.sh" -o -name "*.json" -o -name "*.txt" \
        -o -name "*.yaml" -o -name "*.yml" -o -name "*.py" -o -name "*.mjs" \
        -o -name "*.js" -o -name "*.ts" -o -name "*.html" -o -name "*.css" \
        -o -name "*.toml" -o -name ".env" -o -name "*.env" \
        -o -name "*.template" -o -name "*.tmpl" -o -name "*.example" \
        -o -name "*.sample" -o -name "*.tsx" -o -name "*.jsx" -o -name "*.cjs" \
        -o -name "*.conf" -o -name "*.cfg" -o -name "*.ini" -o -name "*.xml" \
        -o -name "*.csv" -o -name "*.plist" -o -name "*.tf" \) \
      -type f 2>/dev/null
  fi
}

# ─── Self-exclusion (this gate + its selftest hold the patterns as DATA) ──────
_is_self() {
  case "$1" in
    */scripts/qc-assert-no-telegram-chat-id-leak.sh) return 0 ;;
    *"/qc-assert-no-telegram-chat-id-leak.sh")       return 0 ;;
    */tests/fixtures/telegram-chat-id-leak/*)        return 0 ;;
    *"/selftest-telegram-chat-id-leak.sh")           return 0 ;;
  esac
  return 1
}

# ─── PART B path-exclusions: fixture / teaching files holding SYNTHETIC ids ───
# These files carry non-real chat ids as test DATA or teaching examples. They are
# excluded from PART B ONLY (PART A session-key scan still applies to them, so a
# real "telegram:direct:<id>" leak in any of them is still caught). Anchored to
# exact path suffix so only the intended files are skipped.
_is_partb_excluded() {
  case "$1" in
    */15-blackceo-team-management/EXAMPLES.md)                    return 0 ;;
    */platform/vps/INSTALL-GOTCHAS.md)                            return 0 ;;
    */37-zhc-closeout/scripts/test-closeout-gated-pipeline.sh)    return 0 ;;
    */37-zhc-closeout/scripts/test-closeout-ghost-and-rating.sh)  return 0 ;;
    */tests/unit/cron-owner-chat-guard.test.sh)                   return 0 ;;
  esac
  return 1
}

# ─── Collect scannable files ──────────────────────────────────────────────────
FILES=()
while IFS= read -r f; do
  _is_self "$f" && continue
  FILES+=("$f")
done < <(_list_files "$REPO_ROOT")

HITS=0
OFFENDERS=()
_rel() { printf '%s' "${1#$REPO_ROOT/}"; }

if [ "${#FILES[@]}" -eq 0 ]; then
  echo "[qc-assert-no-telegram-chat-id-leak] no scannable files under $REPO_ROOT" >&2
  exit 0
fi

# ─── PART A — session-key literal ─────────────────────────────────────────────
# Match "telegram:direct:<8-10 digits>"; fail unless the id is the placeholder.
while IFS= read -r hit; do
  [ -z "$hit" ] && continue
  path="${hit%%:*}"; rest="${hit#*:}"; lineno="${rest%%:*}"
  id="$(printf '%s' "$hit" | grep -oE 'telegram:direct:[0-9]{8,10}' | grep -oE '[0-9]{8,10}' | head -1)"
  [ -z "$id" ] && continue
  [ "$id" = "$PLACEHOLDER_ID" ] && continue
  OFFENDERS+=("  [A/session-key] $(_rel "$path"):${lineno}: leaked chat-id ${id} in telegram:direct session key")
  HITS=$((HITS + 1))
done < <(printf '%s\0' "${FILES[@]}" | xargs -0 grep -EHn 'telegram:direct:[0-9]{8,10}' 2>/dev/null)

# ─── PART B — chat-id-shaped integer in a telegram-identity context ───────────
PARTB_FILES=()
for f in "${FILES[@]}"; do
  _is_partb_excluded "$f" && continue
  PARTB_FILES+=("$f")
done

CTX='allowFrom|groupAllowFrom|ownerAllowFrom|ownerChatId|chatId|helpChatId|ownerId|Telegram[ _]?ID|CHAT_ID|telegram:direct'
if [ "${#PARTB_FILES[@]}" -gt 0 ]; then
  while IFS= read -r hit; do
    [ -z "$hit" ] && continue
    path="${hit%%:*}"; rest="${hit#*:}"; lineno="${rest%%:*}"; text="${rest#*:}"
    # Extract every chat-id-shaped integer on the line (word-bounded so 13-digit
    # ms timestamps etc. don't yield a spurious 10-digit substring).
    unsan=""
    while IFS= read -r id; do
      [ -z "$id" ] && continue
      _is_sanctioned_id "$id" && continue
      unsan="$unsan $id"
    done < <(printf '%s' "$text" | grep -oE '\b[0-9]{8,10}\b')
    if [ -n "$unsan" ]; then
      OFFENDERS+=("  [B/telegram-ctx] $(_rel "$path"):${lineno}: non-sanctioned chat-id(s)${unsan} in a telegram-identity context")
      HITS=$((HITS + 1))
    fi
  done < <(printf '%s\0' "${PARTB_FILES[@]}" | xargs -0 grep -EHn "$CTX" 2>/dev/null)
fi

# ─── PART C — optional roster denylist (box-mode) ─────────────────────────────
if [ "$ROSTER_AVAILABLE" = 1 ]; then
  ROSTER_PATTERN="$(printf '%s\n' "${ROSTER_IDS[@]}" | paste -sd'|' -)"
  while IFS= read -r hit; do
    [ -z "$hit" ] && continue
    path="${hit%%:*}"; rest="${hit#*:}"; lineno="${rest%%:*}"
    match="$(printf '%s' "$hit" | grep -oE "$ROSTER_PATTERN" | head -1)"
    OFFENDERS+=("  [C/roster] $(_rel "$path"):${lineno}: roster client chat-id ${match} present in tracked file")
    HITS=$((HITS + 1))
  done < <(printf '%s\0' "${FILES[@]}" | xargs -0 grep -EHn "$ROSTER_PATTERN" 2>/dev/null)
fi

# ─── Verdict ──────────────────────────────────────────────────────────────────
MODE="structural"; [ "$ROSTER_AVAILABLE" = 1 ] && MODE="full (roster denylist active)"
if [ "$HITS" -eq 0 ]; then
  echo "[qc-assert-no-telegram-chat-id-leak] PASS ($MODE) — no client Telegram chat-id leak in tracked files."
  echo "  Sanctioned only: placeholder $PLACEHOLDER_ID + operator ids ${OPERATOR_IDS[*]}."
  exit 0
fi
echo "[qc-assert-no-telegram-chat-id-leak] INVARIANT VIOLATED — $HITS Telegram chat-id leak(s):"
# De-dup + stable order
printf '%s\n' "${OFFENDERS[@]}" | awk '!seen[$0]++'
echo
echo "REMEDY: a real client Telegram chat id must NEVER ship in this fleet-wide"
echo "  template. Replace it with the sanctioned placeholder ${PLACEHOLDER_ID}."
echo "  Operator ids (${OPERATOR_IDS[*]}) are the only real ids allowed, and only"
echo "  in operator-guard contexts. See memory [repo-is-fleet-wide-no-client-names]."
exit 1

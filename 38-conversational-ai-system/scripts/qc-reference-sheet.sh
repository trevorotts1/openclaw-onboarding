#!/usr/bin/env bash
# qc-reference-sheet.sh — machine-enforce that the generated CLIENT REFERENCE
# SHEET always carries the two copy-paste artifacts a client cannot proceed
# without:
#
#   1. The Authorization header / BEARER TOKEN — a real, copy-paste-ready
#      `Authorization: Bearer <token>` (the literal word "Bearer" must appear).
#   2. The GHL Custom Webhook RAW BODY as a real ```json fenced code block
#      (copyable), plus the hook URL (`https://<host>/hooks/<id>`).
#
# ROOT CAUSE this gate kills: on a live client (Teresa) the generated reference
# sheet had NO bearer token and NO copyable ```json Raw Body. The client opened
# their reference doc, the token was missing, and there was no JSON to copy into
# GHL's Build-with-AI. That stranded the client. The reference sheet MUST contain
# both, ALWAYS — this is enforced, not optional.
#
# HOW IT CHECKS (two modes):
#   * --sheet <path>  → static-check an already-generated reference sheet file.
#   * (default)       → drive 21-generate-client-reference-sheet.sh in a sandbox
#                       (no `openclaw` on PATH, dummy env → Layer-3 markdown
#                       fallback, no network), then check the markdown it writes.
#     The default mode is what CI runs: it proves the GENERATOR emits both
#     artifacts, so a template/script regression that drops them fails the build.
#
# REQUIRED MARKERS (all must be present in the checked sheet):
#   - the word "Bearer"
#   - at least one ```json fenced code block (opening fence, line-anchored)
#   - a hook URL of the form https://.../hooks/<id>
#
# Exit codes: 0 = sheet carries all required markers;
#             1 = one or more markers missing;
#             2 = could not produce/locate a reference sheet to check (the
#                 generator failed or the scan target moved — treated as FAILURE,
#                 never a blind PASS).
#
# Usage:
#   bash scripts/qc-reference-sheet.sh                 # generate + check (CI)
#   bash scripts/qc-reference-sheet.sh --json          # machine output
#   bash scripts/qc-reference-sheet.sh --sheet FILE    # check an existing sheet
#   bash scripts/qc-reference-sheet.sh --skill-dir DIR # point at a skill root

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
JSON_MODE=0
SHEET=""

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --sheet)     SHEET="$2"; shift 2 ;;
    --json)      JSON_MODE=1; shift ;;
    -h|--help)   sed -n '1,52p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

GEN_SCRIPT="$SKILL_DIR/scripts/21-generate-client-reference-sheet.sh"

# ---------------------------------------------------------------------------
# If no --sheet was passed, generate one in a sandbox and check that output.
# We strip `openclaw` from PATH so the generator takes the Layer-3 markdown
# fallback (no network, no Telegram sends) and writes a plain .md we can read.
# ---------------------------------------------------------------------------
TMP=""
cleanup() { [ -n "$TMP" ] && rm -rf "$TMP"; }
trap cleanup EXIT

GEN_LOG=""
if [ -z "$SHEET" ]; then
  if [ ! -f "$GEN_SCRIPT" ]; then
    if [ "$JSON_MODE" = "1" ]; then
      printf '{"verdict":"NO_SHEET","reason":"generator not found: %s"}\n' "$GEN_SCRIPT"
    else
      echo "RESULT: NO SHEET — generator not found ($GEN_SCRIPT). Treating as FAIL."
    fi
    exit 2
  fi

  TMP="$(mktemp -d)"
  MASTER_FILES_DIR="$TMP/master-files"
  mkdir -p "$MASTER_FILES_DIR"

  # Sandbox PATH without `openclaw` so the generator stays offline (Layer 3).
  SANDBOX_PATH=""
  IFS=':' read -ra _parts <<< "$PATH"
  for p in "${_parts[@]}"; do
    [ -x "$p/openclaw" ] && continue
    if [ -z "$SANDBOX_PATH" ]; then SANDBOX_PATH="$p"; else SANDBOX_PATH="$SANDBOX_PATH:$p"; fi
  done
  [ -n "$SANDBOX_PATH" ] || SANDBOX_PATH="$PATH"

  GEN_LOG="$TMP/gen.log"
  set +e
  env -i \
    HOME="$TMP" \
    PATH="$SANDBOX_PATH" \
    MASTER_FILES_DIR="$MASTER_FILES_DIR" \
    PUBLIC_HOSTNAME="claw.qc-reference-sheet.example.com" \
    ROUTE_ID="QCREF" \
    HOOK_NAME="QCREF" \
    AGENT_ID="main" \
    ROUTING_AGENT_ID="main" \
    HOOKS_TOKEN="hooks_qc_reference_sheet_dummy_token" \
    CLIENT_BUSINESS_NAME="QC Reference Sheet Test Co" \
    CLIENT_TELEGRAM_CHAT_ID="0" \
    SKILL38_TEMPLATES_DIR="$SKILL_DIR/templates" \
    bash "$GEN_SCRIPT" >"$GEN_LOG" 2>&1
  GEN_RC=$?
  set -e 2>/dev/null || true

  # The Layer-3 fallback writes 01-client-reference-sheet.md under
  # <MASTER_FILES_DIR>/conversation-workflows/. Locate the rendered sheet.
  SHEET="$MASTER_FILES_DIR/conversation-workflows/01-client-reference-sheet.md"
  if [ ! -f "$SHEET" ]; then
    # Fallback: any reference-sheet markdown the generator staged.
    SHEET="$(find "$MASTER_FILES_DIR" -name '*reference-sheet*.md' -o -name '01-client-reference-sheet.md' 2>/dev/null | head -n1)"
  fi

  if [ -z "$SHEET" ] || [ ! -f "$SHEET" ]; then
    if [ "$JSON_MODE" = "1" ]; then
      printf '{"verdict":"NO_SHEET","generator_rc":%s,"reason":"generator produced no reference sheet"}\n' "$GEN_RC"
    else
      echo "=== qc-reference-sheet: generator output check ==="
      echo "generator rc: $GEN_RC"
      echo "generator log:"; sed 's/^/    /' "$GEN_LOG" 2>/dev/null || true
      echo "RESULT: NO SHEET — the generator produced no reference sheet to check. Treating as FAIL."
    fi
    exit 2
  fi
fi

if [ ! -f "$SHEET" ]; then
  if [ "$JSON_MODE" = "1" ]; then
    printf '{"verdict":"NO_SHEET","reason":"sheet not found: %s"}\n' "$SHEET"
  else
    echo "RESULT: NO SHEET — file not found ($SHEET). Treating as FAIL."
  fi
  exit 2
fi

# ---------------------------------------------------------------------------
# Marker checks (line-anchored for the ```json fence so a stray inline mention
# of "```json" in prose does not satisfy it).
# ---------------------------------------------------------------------------
MISSING=()

grep -q "Bearer" "$SHEET" || MISSING+=('the word "Bearer" (Authorization: Bearer <token>)')

# A real opening ```json fence on its own line (optional leading whitespace).
grep -Eq '^[[:space:]]*```json[[:space:]]*$' "$SHEET" || \
  MISSING+=('a ```json fenced code block (copyable GHL Raw Body)')

# A hook URL of the form https://.../hooks/<id>
grep -Eq 'https://[^[:space:]]+/hooks/[A-Za-z0-9._-]+' "$SHEET" || \
  MISSING+=('a hook URL (https://<host>/hooks/<id>)')

if [ "$JSON_MODE" = "1" ]; then
  miss_json="["
  first=1
  for m in "${MISSING[@]:-}"; do
    [ -z "$m" ] && continue
    esc="${m//\"/\\\"}"
    if [ "$first" = "1" ]; then miss_json="$miss_json\"$esc\""; first=0
    else miss_json="$miss_json,\"$esc\""; fi
  done
  miss_json="$miss_json]"
  if [ "${#MISSING[@]}" -eq 0 ]; then
    printf '{"sheet":"%s","verdict":"PASS","missing":%s}\n' "$SHEET" "$miss_json"
  else
    printf '{"sheet":"%s","verdict":"FAIL","missing":%s}\n' "$SHEET" "$miss_json"
  fi
else
  echo "=== qc-reference-sheet: client reference sheet copy-paste-artifact gate ==="
  echo "sheet : $SHEET"
  echo ""
  if [ "${#MISSING[@]}" -eq 0 ]; then
    echo "  [PASS] Bearer token present"
    echo "  [PASS] copyable \`\`\`json Raw Body present"
    echo "  [PASS] hook URL present"
    echo ""
    echo "RESULT: PASS — the reference sheet carries the bearer token, a copyable JSON Raw Body, and the hook URL."
  else
    grep -q "Bearer" "$SHEET" && echo "  [PASS] Bearer token present" || echo "  [FAIL] bearer token MISSING"
    grep -Eq '^[[:space:]]*```json[[:space:]]*$' "$SHEET" && echo "  [PASS] copyable \`\`\`json Raw Body present" || echo "  [FAIL] copyable \`\`\`json Raw Body MISSING"
    grep -Eq 'https://[^[:space:]]+/hooks/[A-Za-z0-9._-]+' "$SHEET" && echo "  [PASS] hook URL present" || echo "  [FAIL] hook URL MISSING"
    echo ""
    echo "RESULT: FAIL — the reference sheet is missing required copy-paste artifact(s):"
    for m in "${MISSING[@]}"; do echo "          - $m"; done
  fi
fi

[ "${#MISSING[@]}" -eq 0 ]

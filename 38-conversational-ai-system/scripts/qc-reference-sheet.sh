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
# REQUIRED ADDITIONAL MARKERS under --require-manual-fill (the bulletproof set):
#   - a section literally named "🚀 Quick Start" (heading)
#   - a COMPLETE explanation/reference section AFTER Quick Start ("📖 Full
#     Reference & Explanation" heading, appearing later in the file)
#   - the manual Custom-Webhook fill instructions ("Custom Webhook" + a
#     "manually"/"paste" verb + the "Build with AI will NOT fill" line)
#   - SEPARATE Authorization header code blocks: one fenced block whose ONLY
#     content is "Authorization" (the key) and one fenced block whose content is
#     "Bearer <token>" (the value) — NEVER combined on one line. The VALUE block
#     must be ONLY "Bearer <token>" and must NOT contain the word "Authorization"
#     (no combined "Authorization: Bearer <token>" copy block).
#   - the create-tags-FIRST instruction (create the tag before building, check
#     Settings -> Tags)
#   - the POST-BUILD verification section (verify trigger/tag-exists + custom
#     webhook + publish AFTER Build with AI runs)
#   - lead-with-values ORDER (Webhook URL before the ```json Raw Body; manual
#     fill before the Workflow-AI prompt pointer)
#   - the enriched "Your Communication Playbooks" section: WHERE playbooks are
#     stored (conversation-workflows/ + mirrored to Notion); the "Want another
#     communication playbook? Just ask me!" CTA with a copyable "Help me build a
#     [purpose] playbook" example + more examples (missed-call/appointment-
#     reminder/lead-nurture/review-request); the build WALKTHROUGH (brainstorm →
#     create → store → matching Workflow AI prompt wired to the client's Convert
#     and Flow account); the Convert-and-Flow abilities (create TAGS, update the
#     CALENDAR, create/book APPOINTMENTS); and the explicit "connected to your
#     Convert and Flow account ... just ask" statement
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
REQUIRE_MANUAL_FILL=0

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    --sheet)     SHEET="$2"; shift 2 ;;
    --json)      JSON_MODE=1; shift ;;
    # --require-manual-fill: ALSO require the manual Custom-Webhook fill instructions
    # (Build with AI only builds the SHAPE; the client must paste URL/headers/body by
    # hand) AND that the sheet LEADS with the copy-paste values in spec order
    # (URL → Bearer → Raw Body JSON → manual fill steps).
    --require-manual-fill) REQUIRE_MANUAL_FILL=1; shift ;;
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

# --require-manual-fill: the sheet MUST also carry the mandatory manual
# Custom-Webhook fill instructions AND lead with the copy-paste values in order.
# GHL's Build-with-AI only builds the workflow SHAPE; it does NOT fill the URL /
# Authorization header / Content-Type / Raw Body — the client must paste those by
# hand. We require: a "Custom Webhook" mention, a "manually"/"paste" verb, and the
# explicit "Build with AI will not fill" instruction; plus the lead-with-values
# ordering (URL heading before the Raw Body json fence, and the manual-fill heading
# before the Workflow-AI-prompt pointer).
if [ "$REQUIRE_MANUAL_FILL" = "1" ]; then
  grep -qi "Custom Webhook" "$SHEET" || \
    MISSING+=('a "Custom Webhook" mention in the manual-fill instructions')
  grep -qiE 'manually|paste' "$SHEET" || \
    MISSING+=('a "manually"/"paste" instruction for the Custom Webhook fields')
  grep -qiE 'Build with AI will[[:space:]]+(not|n.t)[[:space:]]+fill' "$SHEET" || \
    MISSING+=('the explicit "Build with AI will NOT fill these for you" instruction')

  # --- Quick Start first, then a full explanation AFTER it (BOTH required) ---
  # The sheet MUST lead with a section literally named "🚀 Quick Start", AND it
  # MUST carry a complete explanation/reference section that appears AFTER it.
  grep -qE '^#+[[:space:]]*🚀[[:space:]]*Quick Start[[:space:]]*$' "$SHEET" || \
    MISSING+=('a section literally named "🚀 Quick Start"')
  QS_LN="$(grep -nE '^#+[[:space:]]*🚀[[:space:]]*Quick Start[[:space:]]*$' "$SHEET" | head -1 | cut -d: -f1)"
  EXPL_LN="$(grep -niE '^#+[[:space:]].*(Full Reference|Reference &amp;? Explanation|Reference & Explanation|How it works|How the .* works)' "$SHEET" | head -1 | cut -d: -f1)"
  if [ -z "$QS_LN" ] || [ -z "$EXPL_LN" ] || [ "$EXPL_LN" -le "$QS_LN" ]; then
    MISSING+=('a complete explanation/reference section AFTER the "🚀 Quick Start" section')
  fi

  # --- SEPARATE Authorization key + value code blocks (own copy buttons) ---
  # One fenced code block whose ONLY content is the literal header KEY
  # "Authorization" (on its own line, between two fences), and a separate fenced
  # block whose content is the VALUE "Bearer <token>". They must NEVER be combined
  # into one "Authorization: Bearer <token>" line — 50+ clients copy each field
  # individually. We detect a standalone "Authorization" fenced block via awk:
  # inside a ``` fence, a line that is exactly "Authorization".
  HAS_AUTH_KEY_BLOCK="$(awk '
    /^[[:space:]]*```/ { infence = !infence; next }
    infence && $0 ~ /^[[:space:]]*Authorization[[:space:]]*$/ { found=1 }
    END { print (found ? "yes" : "no") }
  ' "$SHEET")"
  [ "$HAS_AUTH_KEY_BLOCK" = "yes" ] || \
    MISSING+=('a SEPARATE code block containing ONLY the header key "Authorization" (its own copy button)')
  # A separate "Bearer <token>" value block (inside a fence, a line starting with Bearer).
  HAS_BEARER_VALUE_BLOCK="$(awk '
    /^[[:space:]]*```/ { infence = !infence; next }
    infence && $0 ~ /^[[:space:]]*Bearer[[:space:]]+/ { found=1 }
    END { print (found ? "yes" : "no") }
  ' "$SHEET")"
  [ "$HAS_BEARER_VALUE_BLOCK" = "yes" ] || \
    MISSING+=('a SEPARATE code block containing the header value "Bearer <token>" (its own copy button)')
  # NEGATIVE GUARD: the header VALUE copy block must be JUST "Bearer <token>" — it
  # must NOT repeat the header KEY. The exact bug is a copy block whose line is
  # "Authorization: Bearer <token>" (the second block emitted combined), so the
  # client pastes "Authorization: Bearer ..." into the VALUE box. We FAIL if any
  # COPY LINE is of the form "Authorization:" + "Bearer ..." — matched whether the
  # line sits in a real ``` fence or in the template's illustrative
  # "[code block ...]" markup. We anchor on a line that STARTS with optional
  # whitespace then "Authorization:" and also contains "Bearer", so plain prose
  # that merely names both words (e.g. "Re-check the Authorization header ...
  # Bearer token wrong") is NOT flagged.
  if grep -Eq '^[[:space:]]*Authorization:[[:space:]]*Bearer' "$SHEET"; then
    MISSING+=('the Authorization VALUE code block must be ONLY "Bearer <token>" — it must NOT be a combined "Authorization: Bearer <token>" copy block (the second copy block repeats the header key)')
  fi

  # --- create-tags-FIRST instruction (the Teresa blank-tag bug) ---
  grep -qiE 'create (the |your )?tag.*(first|before)|tag.*(first|before).*(build|workflow)' "$SHEET" || \
    MISSING+=('the create-tags-FIRST instruction (create the tag before building the workflow)')
  grep -qiE 'Settings[[:space:]]*(->|→|>)[[:space:]]*Tags' "$SHEET" || \
    MISSING+=('a "Settings -> Tags" pointer for where to check tags')

  # --- POST-BUILD verification section (verify trigger/tag + webhook + publish) ---
  grep -qiE '^#+[[:space:]].*(Verify|Verification|Post-build).*(Build with AI|after)' "$SHEET" || \
  grep -qiE '^#+[[:space:]].*(Verify AFTER|verify after Build)' "$SHEET" || \
    MISSING+=('a POST-BUILD verification section (verify AFTER Build with AI runs)')
  # The post-build verification MUST cover the trigger tag-existence bug, the
  # custom webhook fields, and publish — and tell the client what to do if wrong.
  grep -qiE 'does not contain|contains.*tag|tag.*(exist|real|blank)|references a (real|blank)' "$SHEET" || \
    MISSING+=('the post-build TRIGGER tag-existence check (a blank/non-existent tag in a contains/does-not-contain filter is the bug)')
  grep -qiE 'Publish(ed)?,? not Draft|not[[:space:]]+Draft|Draft.*Publish' "$SHEET" || \
    MISSING+=('the post-build PUBLISH check (confirm Published, not Draft)')

  # --- "Your Communication Playbooks" section (placed AFTER Quick Start, BEFORE
  #     the deep Full Reference) — answers the client's first question:
  #     "where are my workflows / communication playbooks?" It must be prominent
  #     (a heading) and tell them (a) WHERE they live — the conversation-workflows/
  #     folder + human-facing copies in Notion (→ Google Docs → text); (b) the
  #     "just ask me" CTA with a copyable "Help me build a [purpose] playbook"
  #     example; (c) the build WALKTHROUGH (brainstorm with you using known
  #     business context, then create the playbook, store it in
  #     conversation-workflows/ mirrored to Notion, help create the matching
  #     Workflow AI prompt wired to the client's Convert and Flow / GoHighLevel
  #     account); and (d) that the AI is connected to the client's Convert and Flow
  #     account and can take real actions on their behalf — create TAGS, update the
  #     CALENDAR, and create/book APPOINTMENTS.
  grep -qiE '^#+[[:space:]].*Communication Playbooks?' "$SHEET" || \
    MISSING+=('a prominent "Your Communication Playbooks" section (where the client'\''s playbooks live)')
  grep -qiE 'conversation-workflows' "$SHEET" || \
    MISSING+=('the "Communication Playbooks" section must say playbooks live in (and are stored in) the conversation-workflows/ folder')
  grep -qi 'Notion' "$SHEET" || \
    MISSING+=('the "Communication Playbooks" section must point to the human-facing copies in (mirrored to) Notion')
  # The "just ask me" call-to-action — "Want another communication playbook? Just
  # ask me!" (the older "Want a NEW communications playbook? Start here" wording
  # also satisfies this).
  grep -qiE 'Want another communications? playbook|Want a NEW communications? playbook|just ask me' "$SHEET" || \
    MISSING+=('the "Want another communication playbook? Just ask me!" call-to-action')
  # A copyable, concrete example: "Help me build a [purpose] playbook" (the
  # missed-call follow-up example, or the literal [purpose] form).
  grep -qiE 'help me build a .*playbook' "$SHEET" || \
    MISSING+=('a concrete copyable example: "Help me build a [purpose] playbook" (e.g. missed-call follow-up)')
  grep -qiE 'missed-call|appointment-reminder|lead-nurture|review-request' "$SHEET" || \
    MISSING+=('at least one additional playbook example (missed-call / appointment-reminder / lead-nurture / review-request)')
  grep -qiE 'brainstorm' "$SHEET" || \
    MISSING+=('the build walkthrough must say the AI will brainstorm it with the client (using known business context, not a 50-question interrogation)')
  # The matching Workflow AI prompt, wired to the client's Convert and Flow
  # (GoHighLevel) account.
  grep -qiE 'Workflow AI prompt|Workflow-AI prompt' "$SHEET" || \
    MISSING+=('the build walkthrough must say the AI helps create the matching Workflow AI prompt')
  grep -qiE 'Convert and Flow' "$SHEET" || \
    MISSING+=('the build walkthrough must say the Workflow AI prompt is wired to the client'\''s Convert and Flow (GoHighLevel) account')
  # The AI can take real actions in Convert and Flow on the client's behalf:
  # create TAGS, update the CALENDAR, create/book APPOINTMENTS.
  grep -qiE 'tag' "$SHEET" || \
    MISSING+=('the Convert and Flow abilities must include creating/applying TAGS')
  grep -qiE 'calendar' "$SHEET" || \
    MISSING+=('the Convert and Flow abilities must include updating the CALENDAR')
  grep -qiE 'appointment' "$SHEET" || \
    MISSING+=('the Convert and Flow abilities must include creating/booking APPOINTMENTS')
  # Explicit: the AI is connected to the client's Convert and Flow account and can
  # do these things for them — just ask.
  grep -qiE 'connected to your Convert and Flow' "$SHEET" || \
    MISSING+=('the explicit "you have an AI that is connected to your Convert and Flow account and can do these things for you — just ask" statement')
  # The Communication Playbooks section must sit AFTER Quick Start and BEFORE the
  # deep Full Reference & Explanation (the "where are my playbooks" answer should
  # be high up, not buried in the deep reference).
  CP_LN="$(grep -nE '^#+[[:space:]].*Communication Playbooks' "$SHEET" | head -1 | cut -d: -f1)"
  if [ -n "$QS_LN" ] && [ -n "$CP_LN" ] && [ "$CP_LN" -le "$QS_LN" ]; then
    MISSING+=('the "Your Communication Playbooks" section must come AFTER the Quick Start')
  fi
  if [ -n "$CP_LN" ] && [ -n "$EXPL_LN" ] && [ "$CP_LN" -ge "$EXPL_LN" ]; then
    MISSING+=('the "Your Communication Playbooks" section must come BEFORE the deep Full Reference & Explanation')
  fi

  # Lead-with-values ORDER: the Webhook-URL line must come before the ```json Raw Body,
  # and the manual-fill section must come before the Workflow-AI-prompt pointer.
  URL_LN="$(grep -nE '^#+[[:space:]].*Webhook URL' "$SHEET" | head -1 | cut -d: -f1)"
  JSON_LN="$(grep -nE '^[[:space:]]*```json[[:space:]]*$' "$SHEET" | head -1 | cut -d: -f1)"
  MANUAL_LN="$(grep -niE '^#+[[:space:]].*(Manually fill|manual.*fill)' "$SHEET" | head -1 | cut -d: -f1)"
  WAIPROMPT_LN="$(grep -niE '^#+[[:space:]].*Workflow-AI prompt' "$SHEET" | head -1 | cut -d: -f1)"
  if [ -z "$URL_LN" ] || [ -z "$JSON_LN" ] || [ "$URL_LN" -ge "$JSON_LN" ]; then
    MISSING+=('the Webhook URL must LEAD (appear before the ```json Raw Body)')
  fi
  if [ -z "$MANUAL_LN" ] || [ -z "$WAIPROMPT_LN" ] || [ "$MANUAL_LN" -ge "$WAIPROMPT_LN" ]; then
    MISSING+=('the manual Custom-Webhook fill steps must come before the Workflow-AI prompt')
  fi
fi

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

#!/usr/bin/env bash
# bash >= 4 required (associative arrays / mapfile / case modifiers); macOS ships 3.2 at /bin/bash.
if [ "${BASH_VERSINFO[0]:-0}" -lt 4 ] && [ -z "${_OC_BASH_REEXEC:-}" ]; then
  for _oc_b in /opt/homebrew/bin/bash /usr/local/bin/bash; do
    [ -x "$_oc_b" ] && _OC_BASH_REEXEC=1 exec "$_oc_b" "$0" "$@"
  done
  echo "FATAL: bash >= 4 required (macOS ships 3.2): brew install bash" >&2; exit 3
fi
# qc-built-workflow.sh — Skill 44: per-build QC for a constructed GHL workflow
#
# DISTINCT from qc-convert-and-flow.sh (install-level QC for the skill itself).
# This script verifies a BUILT WORKFLOW artifact against the WF checklist items.
#
# Usage:
#   ./qc-built-workflow.sh <workflow-id> [--publish-intent DRAFT|LIVE] [--re-entry ONCE|ALLOW-MULTIPLE] \
#                          [--fab] [--evidence <evidence_root>] [--conversational] [--json]
#                          [--deps <dependency-manifest.json>] [--handoff <path>]
#
#   workflow-id       GHL workflow id (required)
#   --publish-intent  Client's publish decision: DRAFT (default) or LIVE
#   --re-entry        Client's re-entry decision: ONCE (default) or ALLOW-MULTIPLE
#   --fab             Run the FAB-QC library-aware overlay (fail-CLOSED — see below)
#   --evidence        Canonical evidence_root (from Step 0.4); implies --fab
#   --conversational  Run Skill 38 qc-trinity-registry.sh as a HARD gate; WF-19 FAILs
#                     mechanically (not REQUIRES_HUMAN_REVIEW) on non-zero trinity exit
#   --json            Emit per-item PASS/FAIL as JSON to stdout (for QC sub-agent parsing)
#
# NOTE on export routing (Tier awareness): `caf workflows list` reads via the LOCATION
# PIT (Tier 0, public API). `caf workflows get` / `caf workflows export` route through the
# INTERNAL Firebase client and REQUIRE the Firebase refresh token — they are NOT Tier-0
# PIT reads. On a Tier-4 (agent-browser) build with no Firebase token, export cannot run,
# so this mechanical QC cannot run: that is a fail-CLOSED "no-token = NOT DONE" condition
# (exit 2, REQUIRES_OPERATOR agent-browser read-back), never a silent pass.
#
# Exit codes:
#   0  = ALL mechanically-checkable items PASS (and, when --fab, FAB-QC scored >= 8.5)
#   1  = one or more items FAIL (or --fab and FAB-QC below 8.5 / unavailable — fail-closed)
#   2  = workflow not found, caf not available, or export blocked by a missing Firebase
#        token on a Tier-4 build (hard prereq failure — REQUIRES_OPERATOR)
#
# Mechanically-checkable WF items (asserted here):
#   WF-3  Trigger present
#   WF-4  Trigger active flag vs publish-intent (WF-ACTIVE GATE)
#   WF-5  Publish state (draft/published) vs publish-intent
#   WF-6  Re-entry/allow-multiple vs re-entry decision
#   WF-7  Action sequence: at minimum one action node present + delivery chain not empty
#   WF-12 SMS From-number non-empty (for any SMS-type action nodes)
#   WF-22 Email body non-empty + >=200 rendered chars (for any email-type action nodes)
#   WF-15 Delivery chain linkage: summary of the graph validator (0 orphans,
#         0 dangling, 0 unwired branches, 0 cross-branch violations) with node/edge counts in the reason
#   WF-18 Dependency manifest: every tag/field/custom value/calendar/pipeline
#         referenced by the export is listed in the --deps manifest (FAIL when
#         no manifest is supplied)
#   WF-21 Snapshot file is present and non-empty on disk (reversibility only)
#   WF-23 Graph validator (tools/validate_graph.py): seven structural conditions
#         - root, reachability, referential integrity, branch completeness,
#         termination, acyclicity, cross-branch containment. UNVERIFIED is never PASS.
#   WF-24 Trigger entrance link: the trigger's targetActionId equals the root
#         node id
#
# Non-mechanical items (WF-1,2,8,9,10,11,13,14,16,17,19,20) require human/LLM review;
# they are noted in the JSON output as "requires_human_review".
#
# Invoked by the independent QC sub-agent (different model than the build agent — INSTRUCTIONS.md Step 9.2) during Step 9.
set -euo pipefail

# ── Arg parsing ───────────────────────────────────────────────────────────────
WORKFLOW_ID=""
PUBLISH_INTENT="DRAFT"
RE_ENTRY_DECISION="ONCE"
JSON_MODE=0
FAB_MODE=0
FAB_EVIDENCE=""
CONVERSATIONAL=0
DEPS_MANIFEST=""
HANDOFF_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --publish-intent) PUBLISH_INTENT="${2:-DRAFT}"; shift 2 ;;
    --re-entry)       RE_ENTRY_DECISION="${2:-ONCE}"; shift 2 ;;
    --json)           JSON_MODE=1; shift ;;
    --fab)            FAB_MODE=1; shift ;;        # run the FAB-QC library-aware overlay
    --evidence)       FAB_EVIDENCE="${2:-}"; FAB_MODE=1; shift 2 ;;
    --deps)           DEPS_MANIFEST="${2:-}"; shift 2 ;;
    --handoff)        HANDOFF_FILE="${2:-}"; shift 2 ;;
    --conversational) CONVERSATIONAL=1; shift ;;  # WF-19: exec Skill 38 qc-trinity-registry.sh as a HARD gate
    -*)               echo "Unknown option: $1" >&2; exit 2 ;;
    *)                WORKFLOW_ID="$1"; shift ;;
  esac
done

if [ -z "$WORKFLOW_ID" ]; then
  echo "ERROR: workflow-id required" >&2
  echo "Usage: $0 <workflow-id> [--publish-intent DRAFT|LIVE] [--re-entry ONCE|ALLOW-MULTIPLE] [--conversational] [--handoff <path>] [--json]" >&2
  exit 2
fi

PUBLISH_INTENT="${PUBLISH_INTENT^^}"
RE_ENTRY_DECISION="${RE_ENTRY_DECISION^^}"

# ── Prereq: caf available ─────────────────────────────────────────────────────
if ! command -v caf >/dev/null 2>&1; then
  echo "ERROR: caf not found on PATH. Cannot perform per-build QC." >&2
  exit 2
fi

# ── Resolve skill dir (for snapshot path) ─────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM="${OPENCLAW_PLATFORM:-mac}"
if [ "$PLATFORM" = "mac" ]; then
  CAF_DATA="$HOME/.openclaw/tools/convert-and-flow-cli/data"
else
  CAF_DATA="/data/.openclaw/tools/convert-and-flow-cli/data"
fi
SNAPSHOT_DIR="$CAF_DATA/snapshots"
BUILD_EVENTS_LEDGER="$CAF_DATA/build-events.jsonl"

# ── Export the workflow ────────────────────────────────────────────────────────
TMP=$(mktemp "${TMPDIR:-/tmp}/qc-wf-export-XXXXXX")
trap 'rm -f "$TMP"' EXIT

EXPORT_ERR=""
if ! EXPORT_ERR=$(caf workflows export --workflow-id "$WORKFLOW_ID" --out "$TMP" 2>&1); then
  # `caf workflows export` routes through the INTERNAL Firebase client (NOT the Tier-0
  # PIT). If the failure is a missing/expired Firebase token, this is a Tier-4 build whose
  # mechanical QC CANNOT run — fail-closed "no-token = NOT DONE" (never a silent pass).
  if echo "$EXPORT_ERR" | grep -qiE 'firebase|refresh[ _-]?token|id[ _-]?token|internal client|no token|token[^"]*(missing|expired|not found)|tier[ _-]?4'; then
    echo "REQUIRES_OPERATOR: caf workflows export needs the internal Firebase token, which is absent/expired." >&2
    echo "TIER-4 BUILD (agent-browser): mechanical Step-9 QC cannot run without export. NOT DONE." >&2
    echo "Backstop: an agent-browser read-back of the built workflow must confirm the build before done." >&2
  else
    echo "ERROR: caf workflows export --workflow-id $WORKFLOW_ID --out $TMP failed: $EXPORT_ERR" >&2
  fi
  rm -f "$TMP"
  exit 2
fi

if [ ! -s "$TMP" ]; then
  echo "ERROR: export produced an empty file for workflow $WORKFLOW_ID" >&2
  exit 2
fi

EXPORT_OUT=$(cat "$TMP")

# Detect a genuine API failure via a TOP-LEVEL JSON error key ONLY — never a whole-body
# grep for "error"/"404", which false-aborts on innocent copy (an email body reading
# "Did our last message error out? Call us at 404-..." is a valid workflow, not a failure).
EXPORT_TOPLEVEL_ERR=$(printf '%s' "$EXPORT_OUT" | python3 -c "
import sys, json
try:
  o = json.load(sys.stdin)
except Exception:
  print(''); sys.exit(0)
if isinstance(o, dict):
  for k in ('error','errors','statusCode','message'):
    v = o.get(k)
    # A top-level 'message'/'statusCode' only counts as an error alongside a 4xx/5xx code
    # or an explicit error key; a plain descriptive 'message' on a real export is fine.
    if k in ('error','errors') and v:
      print('top-level error key: %s' % k); break
    if k == 'statusCode' and isinstance(v,(int,str)) and str(v)[:1] in ('4','5'):
      print('http %s' % v); break
" 2>/dev/null || echo "")

if [ -n "$EXPORT_TOPLEVEL_ERR" ]; then
  echo "ERROR: workflow $WORKFLOW_ID export returned a top-level API error ($EXPORT_TOPLEVEL_ERR)" >&2
  exit 2
fi

# ── Result tracking ───────────────────────────────────────────────────────────
declare -A ITEM_STATUS
declare -A ITEM_OBSERVED
declare -A ITEM_EXPECTED
declare -A ITEM_NOTES
PASS_COUNT=0
FAIL_COUNT=0

record_pass() {
  local item="$1" observed="$2" expected="$3" notes="${4:-}"
  ITEM_STATUS["$item"]="PASS"
  ITEM_OBSERVED["$item"]="$observed"
  ITEM_EXPECTED["$item"]="$expected"
  ITEM_NOTES["$item"]="$notes"
  PASS_COUNT=$((PASS_COUNT + 1))
}

record_fail() {
  local item="$1" observed="$2" expected="$3" notes="${4:-}"
  ITEM_STATUS["$item"]="FAIL"
  ITEM_OBSERVED["$item"]="$observed"
  ITEM_EXPECTED["$item"]="$expected"
  ITEM_NOTES["$item"]="$notes"
  FAIL_COUNT=$((FAIL_COUNT + 1))
}

record_human() {
  local item="$1" notes="${2:-}"
  ITEM_STATUS["$item"]="REQUIRES_HUMAN_REVIEW"
  ITEM_OBSERVED["$item"]="n/a"
  ITEM_EXPECTED["$item"]="n/a"
  ITEM_NOTES["$item"]="$notes"
}

record_na() {
  local item="$1" notes="${2:-}"
  ITEM_STATUS["$item"]="N/A"
  ITEM_OBSERVED["$item"]="n/a"
  ITEM_EXPECTED["$item"]="n/a"
  ITEM_NOTES["$item"]="$notes"
}

# ── WF-3: Trigger present ─────────────────────────────────────────────────────
TRIGGER_TYPE=""
if echo "$EXPORT_OUT" | grep -qiE '"type".*"trigger|triggerType|trigger_type|event_type'; then
  TRIGGER_TYPE=$(echo "$EXPORT_OUT" | grep -oiE '"triggerType"[[:space:]]*:[[:space:]]*"[^"]*"|"trigger_type"[[:space:]]*:[[:space:]]*"[^"]*"|"type"[[:space:]]*:[[:space:]]*"[A-Z_]*TRIGGER[^"]*"' | head -1 || echo "present")
  record_pass "WF-3" "${TRIGGER_TYPE:-present}" "trigger present" "Trigger node found in export"
elif echo "$EXPORT_OUT" | grep -qiE 'trigger|contactCreated|formSubmitted|tagAdded|ContactCreate|FormSubmit|TagAdd'; then
  record_pass "WF-3" "trigger_found" "trigger present" "Trigger keyword found in export"
else
  record_fail "WF-3" "no_trigger_found" "trigger present" "No trigger node detected in caf workflows export output"
fi

# ── WF-4: Trigger active flag vs publish-intent (WF-ACTIVE GATE) ──────────────
EXPECTED_ACTIVE="false"
[ "$PUBLISH_INTENT" = "LIVE" ] && EXPECTED_ACTIVE="true"

OBSERVED_ACTIVE="unknown"
# Anchored to the JSON "key":value shape (never a loose whole-body `active.*true`,
# which false-matched innocent email copy) and portable ERE `[[:space:]]` (BSD grep
# does not support `\s` / `\|`).
if echo "$EXPORT_OUT" | grep -qiE '"active"[[:space:]]*:[[:space:]]*true|"triggerActive"[[:space:]]*:[[:space:]]*true'; then
  OBSERVED_ACTIVE="true"
elif echo "$EXPORT_OUT" | grep -qiE '"active"[[:space:]]*:[[:space:]]*false|"triggerActive"[[:space:]]*:[[:space:]]*false'; then
  OBSERVED_ACTIVE="false"
fi

if [ "$OBSERVED_ACTIVE" = "$EXPECTED_ACTIVE" ]; then
  record_pass "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "Trigger active state matches publish-intent ($PUBLISH_INTENT)"
elif [ "$OBSERVED_ACTIVE" = "unknown" ]; then
  record_human "WF-4" "Trigger active state not visible in export — cannot machine-assert; requires human review per skill 36 for trigger-bucket state (MVP-deferred)"
else
  WF4_NOTE="WF-ACTIVE BUG: publish-intent=$PUBLISH_INTENT but trigger active=$OBSERVED_ACTIVE. Workflow will silently never fire."
  [ "$PUBLISH_INTENT" = "LIVE" ] && \
    record_fail "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "$WF4_NOTE" || \
    record_pass "WF-4" "$OBSERVED_ACTIVE" "$EXPECTED_ACTIVE" "Client chose DRAFT — inactive trigger is correct"
fi

# ── WF-5: Publish state ────────────────────────────────────────────────────────
EXPECTED_STATUS="draft"
[ "$PUBLISH_INTENT" = "LIVE" ] && EXPECTED_STATUS="published"

OBSERVED_STATUS="unknown"
# Anchored "status":"value" + portable ERE (no loose `status.*published`, no `\s`/`\|`).
if echo "$EXPORT_OUT" | grep -qiE '"status"[[:space:]]*:[[:space:]]*"published"'; then
  OBSERVED_STATUS="published"
elif echo "$EXPORT_OUT" | grep -qiE '"status"[[:space:]]*:[[:space:]]*"draft"'; then
  OBSERVED_STATUS="draft"
fi

if [ "$OBSERVED_STATUS" = "$EXPECTED_STATUS" ]; then
  record_pass "WF-5" "$OBSERVED_STATUS" "$EXPECTED_STATUS" "Publish state matches client decision ($PUBLISH_INTENT)"
elif [ "$OBSERVED_STATUS" = "unknown" ]; then
  record_human "WF-5" "Publish status not directly readable in export output — cannot machine-assert; requires human review"
else
  record_fail "WF-5" "$OBSERVED_STATUS" "$EXPECTED_STATUS" "Publish state mismatch: client chose $PUBLISH_INTENT but workflow status is $OBSERVED_STATUS. Never publish without explicit YES."
fi

# ── WF-6: Re-entry / allow-multiple ───────────────────────────────────────────
EXPECTED_REENTRY="false"
[ "$RE_ENTRY_DECISION" = "ALLOW-MULTIPLE" ] && EXPECTED_REENTRY="true"

OBSERVED_REENTRY="unknown"
# Anchored key:value + portable ERE (no loose `allow_multiple.*true`, no `\s`/`\|`).
if echo "$EXPORT_OUT" | grep -qiE '"allowMultiple"[[:space:]]*:[[:space:]]*true|"reEntry"[[:space:]]*:[[:space:]]*true|"allow_multiple"[[:space:]]*:[[:space:]]*true|"re_entry"[[:space:]]*:[[:space:]]*true'; then
  OBSERVED_REENTRY="true"
elif echo "$EXPORT_OUT" | grep -qiE '"allowMultiple"[[:space:]]*:[[:space:]]*false|"reEntry"[[:space:]]*:[[:space:]]*false|"allow_multiple"[[:space:]]*:[[:space:]]*false|"re_entry"[[:space:]]*:[[:space:]]*false'; then
  OBSERVED_REENTRY="false"
fi

if [ "$OBSERVED_REENTRY" = "$EXPECTED_REENTRY" ]; then
  record_pass "WF-6" "$OBSERVED_REENTRY" "$EXPECTED_REENTRY" "Re-entry setting matches client decision ($RE_ENTRY_DECISION)"
elif [ "$OBSERVED_REENTRY" = "unknown" ]; then
  record_human "WF-6" "Re-entry not directly readable in export — cannot machine-assert; requires human review; client decision was $RE_ENTRY_DECISION"
else
  record_fail "WF-6" "$OBSERVED_REENTRY" "$EXPECTED_REENTRY" "Re-entry mismatch: client chose $RE_ENTRY_DECISION but setting is $OBSERVED_REENTRY"
fi

# ── WF-7: Action sequence — at least one action node present ──────────────────
# Action-node recognition is derived from the BUILDER's VERIFIED_ACTIONS set
# (tools/engine/.../workflow_builder.py — the single source of truth), unioned
# with six legacy export names. If the builder file is absent or unparseable we
# fall back to the complete inline VERIFIED_ACTIONS list (v2.1.12, 56 actions +
# legacy) so recognition can never silently regress to the old 12-name list.
WF7_BUILDER_FILE="$SCRIPT_DIR/tools/engine/cli_anything/gohighlevel/utils/workflow_builder.py"
WF7_EXTRA_LEGACY_NAMES='add_tag|remove_tag|update_contact|create_task|create_note|end'
WF7_INLINE_FALLBACK='add_contact_tag|add_notes|add_tag|add_to_workflow|array_functions|assign_user|call|chatgpt|conversation_ai|create_note|create_opportunity|create_task|create_update_contact|custom_code|custom_webhook|datetime_formatter|dnd_contact|drip|edit_conversation|email|end|facebook_conversion_api|fb_interactive_messenger|find_contact|find_opportunity|gmb|google_sheets|goto|if_else|ig_interactive_messenger|instagram-dm|internal_notification|ivr_connect_call|ivr_gather|math_operation|membership_grant_offer|membership_revoke_offer|messenger|number_formatter|remove_assigned_user|remove_contact_tag|remove_from_all_workflows|remove_from_workflow|remove_opportunity|remove_tag|respond_on_comment|review_request|slack_message|sms|stripe_one_time_charge|task-notification|text_formatter|transition|update_appointment_status|update_contact|update_contact_field|update_custom_value|voicemail|wait|webhook|workflow_goal|workflow_split'
WF7_NAMES=$(python3 - "$WF7_BUILDER_FILE" "$WF7_EXTRA_LEGACY_NAMES" <<'WF7PY' 2>/dev/null || true
import ast, os, re, sys
path, extra = sys.argv[1], sys.argv[2]
if not os.path.isfile(path):
    sys.exit(0)
try:
    src = open(path, "r", encoding="utf-8").read()
except Exception:
    sys.exit(0)
m = re.search(r'^\s*VERIFIED_ACTIONS\s*=\s*frozenset\(', src, re.M)
if not m:
    sys.exit(0)
# Scan to the matching close-paren of the frozenset( literal.
depth = 0
i = m.end() - 1
while i < len(src):
    if src[i] == '(':
        depth += 1
    elif src[i] == ')':
        depth -= 1
        if depth == 0:
            break
    i += 1
else:
    sys.exit(0)
names = set(n for n in extra.split('|') if n)
try:
    frag = ast.parse(src[m.start():i + 1])
    for lit in frag.body[0].value.args[0].elts:
        if isinstance(lit, ast.Constant) and isinstance(lit.value, str):
            names.add(lit.value)
except Exception:
    sys.exit(0)
print('|'.join(sorted(names)))
WF7PY
)
if [ -n "$WF7_NAMES" ]; then
  ACTION_PATTERN="$WF7_NAMES"
  WF7_NAME_SOURCE="builder VERIFIED_ACTIONS + legacy"
else
  ACTION_PATTERN="$WF7_INLINE_FALLBACK"
  WF7_NAME_SOURCE="inline fallback (VERIFIED_ACTIONS v2.1.12 + legacy)"
fi
ACTION_COUNT=0
# Exact, quote-anchored match: a name that merely STARTS with a verified
# type (e.g. "add_contact_tag_extra") is an unknown type and stays rejected.
ACTION_COUNT=$(echo "$EXPORT_OUT" | grep -oiE "\"type\"[[:space:]]*:[[:space:]]*\"($ACTION_PATTERN)\"" | wc -l || echo 0)
ACTION_COUNT=$(echo "$ACTION_COUNT" | tr -d ' ')

if [ "$ACTION_COUNT" -gt 0 ]; then
  record_pass "WF-7" "${ACTION_COUNT}_action_nodes_present" ">=1 action nodes" "Action-node names from $WF7_NAME_SOURCE; link_steps ordering verified by engine (caf builds apply link_steps before save)"
else
  record_fail "WF-7" "0_action_nodes_found" ">=1 action nodes" "No recognizable action nodes found in export (names from $WF7_NAME_SOURCE). Delivery chain may be empty."
fi

# ── WF-12: SMS From-number ────────────────────────────────────────────────────
# WF-12 mechanical assertion (hardened): every SMS node MUST carry a fromNumber
# KEY. On a LIVE/published workflow the value must additionally be NON-EMPTY
# (an empty From silently fails to send). On a DRAFT workflow an empty From is a
# WARNING the QC sub-agent must surface (GHL may resolve a location default at
# send time, which is unproven and must be confirmed before going LIVE).
# Output is three counts: "<missing_key> <empty_on_live> <empty_on_draft>".
SMS_FROM_CHECK=$(echo "$EXPORT_OUT" | PUBLISH_INTENT="$PUBLISH_INTENT" python3 -c "
import sys, json, os
data = sys.stdin.read()
live = os.environ.get('PUBLISH_INTENT','DRAFT').upper() == 'LIVE'
try:
  obj = json.loads(data)
  # Steps may live at several keys depending on export shape.
  steps = obj.get('steps') or obj.get('actions') or obj.get('nodes') or []
  wd = obj.get('workflowData') or {}
  if isinstance(wd, dict) and wd.get('templates'):
    steps = wd['templates']
  if not isinstance(steps, list):
    steps = []
  missing_key = empty_live = empty_draft = total_sms = 0
  for s in steps:
    if not isinstance(s, dict):
      continue
    t = (s.get('type','') or '').upper()
    if 'SMS' in t or 'SEND_SMS' in t:
      total_sms += 1
      attrs = s.get('attributes') if isinstance(s.get('attributes'), dict) else {}
      has_key = ('fromNumber' in s) or ('from_number' in s) or ('phoneNumber' in s) \
                or ('fromNumber' in attrs) or ('from_number' in attrs) or ('phoneNumber' in attrs)
      val = (s.get('fromNumber') or s.get('from_number') or s.get('phoneNumber')
             or attrs.get('fromNumber') or attrs.get('from_number') or attrs.get('phoneNumber') or '')
      if not has_key:
        missing_key += 1
      elif not str(val).strip():
        if live:
          empty_live += 1
        else:
          empty_draft += 1
  print('%d %d %d %d' % (missing_key, empty_live, empty_draft, total_sms))
except Exception:
  print('-1 -1 -1 -1')
" 2>/dev/null || echo "-1 -1 -1 -1")

read -r SMS_MISSING_KEY SMS_EMPTY_LIVE SMS_EMPTY_DRAFT SMS_TOTAL <<< "$SMS_FROM_CHECK"

if [ "$SMS_MISSING_KEY" = "-1" ]; then
  # Could not parse JSON — use text-grep fallback
  if echo "$EXPORT_OUT" | grep -qiE '"type"[[:space:]]*:[[:space:]]*"(sms|send_sms)"'; then
    if echo "$EXPORT_OUT" | grep -qiE '"?(fromNumber|from_number|phoneNumber)"?[[:space:]]*:[[:space:]]*""'; then
      record_fail "WF-12" "sms_node_with_empty_from_number" "fromNumber key present + non-empty on every SMS node" "CRITICAL: SMS node with empty From-number detected (text-grep fallback) — will silently fail to send"
    elif echo "$EXPORT_OUT" | grep -qiE 'fromNumber|from_number|phoneNumber'; then
      record_pass "WF-12" "from_number_key_present" "fromNumber key present on every SMS node" "Text-grep fallback: a From-number key is present (human review recommended for full JSON parse)"
    else
      record_fail "WF-12" "sms_present_no_from_number_key" "fromNumber key present on every SMS node" "CRITICAL: SMS node(s) present but no From-number key found (text-grep fallback). sms_step must emit fromNumber."
    fi
  else
    record_pass "WF-12" "no_sms_nodes" "n/a — no SMS nodes" "No SMS nodes detected in export"
  fi
elif [ "$SMS_TOTAL" -eq 0 ]; then
  record_pass "WF-12" "no_sms_nodes" "n/a — no SMS nodes" "No SMS nodes in this workflow"
elif [ "$SMS_MISSING_KEY" -gt 0 ]; then
  record_fail "WF-12" "${SMS_MISSING_KEY}_of_${SMS_TOTAL}_sms_nodes_missing_fromNumber_key" "fromNumber key present on every SMS node" "CRITICAL: $SMS_MISSING_KEY SMS node(s) have NO fromNumber key — sms_step must emit it (WF-12 gap)"
elif [ "$SMS_EMPTY_LIVE" -gt 0 ]; then
  record_fail "WF-12" "${SMS_EMPTY_LIVE}_of_${SMS_TOTAL}_sms_nodes_empty_from_on_LIVE" "non-empty From on every SMS node of a LIVE workflow" "CRITICAL: $SMS_EMPTY_LIVE SMS node(s) have an EMPTY From-number on a LIVE/published workflow — will silently fail to send. Set CAF_SMS_FROM_NUMBER or pass from_number."
elif [ "$SMS_EMPTY_DRAFT" -gt 0 ]; then
  record_pass "WF-12" "${SMS_EMPTY_DRAFT}_of_${SMS_TOTAL}_sms_nodes_empty_from_on_DRAFT" "fromNumber key present on every SMS node" "WARNING: fromNumber key present but EMPTY on $SMS_EMPTY_DRAFT SMS node(s) of a DRAFT workflow. GHL location-default at send time is UNPROVEN — confirm a From-number before going LIVE."
else
  record_pass "WF-12" "all_${SMS_TOTAL}_sms_nodes_have_nonempty_from_number" "fromNumber key present + non-empty" "All $SMS_TOTAL SMS node(s) carry a non-empty From-number"
fi

# ── WF-22: EMAIL BODY NON-EMPTY (SEND_INTEGRITY_CODE_GATES_V1) ────────────────
# Added 2026-09-03 after ~3,000 emails shipped with a subject and an EMPTY BODY
# and still passed QC. WF-12 covered SMS From-numbers; NOTHING covered email
# bodies. An email node whose body/html renders to no text is a blank send.
# Output: "<total_email_nodes> <empty_bodies> <short_bodies> <parse_ok>"
EMAIL_BODY_CHECK=$(printf '%s' "$EXPORT_OUT" | python3 -c "
import sys, json, re
def rendered(s):
    if not isinstance(s, str): return ''
    t = re.sub(r'<[^>]+>', ' ', s).replace('&nbsp;', ' ')
    return ' '.join(t.split())
total = empty = short = 0
def looks_email(node, attrs):
    blob = ' '.join(str(node.get(k, '')) for k in ('type','actionType','action','name','templateType')).lower()
    if 'email' in blob: return True
    return ('subject' in attrs) and ('body' in attrs or 'html' in attrs)
def walk(o):
    global total, empty, short
    if isinstance(o, dict):
        a = o.get('attributes')
        if isinstance(a, dict) and looks_email(o, a):
            total += 1
            body = rendered(a.get('body') or '') or rendered(a.get('html') or '')
            if not body: empty += 1
            elif len(body) < 200: short += 1
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
try:
    walk(json.load(sys.stdin)); ok = 1
except Exception:
    ok = 0
print('%d %d %d %d' % (total, empty, short, ok))
" 2>/dev/null || echo "0 0 0 0")
read -r EMAIL_TOTAL EMAIL_EMPTY EMAIL_SHORT EMAIL_PARSE_OK <<< "$EMAIL_BODY_CHECK"

if [ "${EMAIL_PARSE_OK:-0}" != "1" ]; then
  # Parse failed — fall back to a text grep for literally-empty body/html values.
  if printf '%s' "$EXPORT_OUT" | grep -qE '"(body|html)"[[:space:]]*:[[:space:]]*""'; then
    record_fail "WF-22" "empty_email_body_detected_textgrep" "every email node has a non-empty body" \
      "CRITICAL: an email node with an EMPTY body/html was found (text-grep fallback). This ships a subject line with no message. DO NOT send."
  else
    record_human "WF-22" "Export JSON could not be parsed — email bodies NOT machine-verified. A QC agent must open each email step and confirm the body is present and is the intended copy."
  fi
elif [ "${EMAIL_TOTAL:-0}" -eq 0 ]; then
  record_pass "WF-22" "no_email_nodes" "n/a — no email nodes" "No email nodes detected in this workflow"
elif [ "${EMAIL_EMPTY:-0}" -gt 0 ]; then
  record_fail "WF-22" "${EMAIL_EMPTY}_of_${EMAIL_TOTAL}_email_nodes_have_EMPTY_body" "every email node has a non-empty body" \
    "CRITICAL: $EMAIL_EMPTY of $EMAIL_TOTAL email node(s) render to an EMPTY body — a subject line with no message. This is the exact failure that sent ~3,000 blank emails. DO NOT publish or send; repair the body and re-run QC."
elif [ "${EMAIL_SHORT:-0}" -gt 0 ]; then
  record_fail "WF-22" "${EMAIL_SHORT}_of_${EMAIL_TOTAL}_email_nodes_under_200_chars" "every email body >= 200 rendered chars" \
    "$EMAIL_SHORT of $EMAIL_TOTAL email node(s) render to fewer than 200 characters of text — almost always truncated or placeholder copy. Confirm with the owner before shipping."
else
  record_pass "WF-22" "all_${EMAIL_TOTAL}_email_nodes_have_nonempty_body" "every email node has a non-empty body" \
    "All $EMAIL_TOTAL email node(s) carry a non-empty body of >= 200 rendered characters"
fi

# ── WF-23: Graph validator; WF-15 derives from same report ────────────────────
VALIDATOR="${QC_GRAPH_VALIDATOR:-$SCRIPT_DIR/tools/validate_graph.py}"
GRAPH_UNVERIFIED=0
GRAPH_JSON=""
GRAPH_RC=0
GRAPH_META_RC=0
if [ ! -f "$VALIDATOR" ]; then
  GRAPH_RC=99
else
  GRAPH_JSON=$(python3 "$VALIDATOR" graph --export "$TMP" 2>/dev/null) || GRAPH_RC=$?
fi

GRAPH_META=$(printf '%s' "$GRAPH_JSON" | python3 -c 'import json,sys
def emit_fail():
    print("parse=fail")
    sys.exit(3)
try:
    d=json.load(sys.stdin)
except Exception:
    emit_fail()
if not isinstance(d,dict) or ("failures" in d and not isinstance(d["failures"],list)):
    emit_fail()
required=("verdict","nodes","edges","root","failures","orphans","unverified")
missing=[]
for k in required:
    v=d.get(k)
    ok=(k in d)
    if k=="verdict": ok=ok and isinstance(v,str)
    elif k in ("nodes","edges","orphans"): ok=ok and isinstance(v,int) and not isinstance(v,bool) and v>=0
    elif k=="root": ok=ok and (v is None or isinstance(v,str))
    elif k=="failures": ok=ok and isinstance(v,list)
    elif k=="unverified": ok=ok and isinstance(v,list)
    if not ok: missing.append(k)
if not isinstance(d.get("failures"),list):
    emit_fail()
failures=d["failures"]
def count_kind(kind):
    return sum(1 for f in failures if isinstance(f,dict) and f.get("kind")==kind)
kinds=sorted({str(f.get("kind","?")) for f in failures if isinstance(f,dict)})
verdict=d.get("verdict") if isinstance(d.get("verdict"),str) else "none"
nodes=d.get("nodes") if isinstance(d.get("nodes"),int) and not isinstance(d.get("nodes"),bool) and d["nodes"]>=0 else "none"
edges=d.get("edges") if isinstance(d.get("edges"),int) and not isinstance(d.get("edges"),bool) and d["edges"]>=0 else "none"
orphans=d.get("orphans") if isinstance(d.get("orphans"),int) and not isinstance(d.get("orphans"),bool) and d["orphans"]>=0 else "none"
root=d.get("root")
root=root.strip() if isinstance(root,str) else ""
root=root or "none"
unverified=len(d["unverified"]) if isinstance(d.get("unverified"),list) else "none"
contradiction="none"
if verdict not in ("PASS","FAIL","UNVERIFIED"): contradiction="unknown_verdict"
elif len(failures)>0 and verdict=="PASS": contradiction="pass_with_failures"
elif len(failures)==0 and verdict=="FAIL": contradiction="fail_without_failure"
elif len(failures)>0 and verdict=="UNVERIFIED": contradiction="unverified_with_failures"
elif isinstance(orphans,int) and not isinstance(orphans,bool) and orphans>=0 and orphans!=count_kind("ORPHAN"): contradiction="orphans_mismatch"
values={"parse":"ok","verdict":verdict,"nodes":nodes,"edges":edges,"root":root,"failures":len(failures),"orphans":orphans,"dangling":count_kind("DANGLING"),"unwired":count_kind("UNWIRED_BRANCH"),"cross":count_kind("CROSS_BRANCH"),"cycle":count_kind("CYCLE"),"unverified":unverified,"kinds":",".join(kinds) or "none","missing":",".join(missing) or "none","contradiction":contradiction}
print(" ".join("%s=%s"%(k,values[k]) for k in ("parse","verdict","nodes","edges","root","failures","orphans","dangling","unwired","cross","cycle","unverified","kinds","missing","contradiction")))') || GRAPH_META_RC=$?

GRAPH_PARSE=""
GRAPH_VERDICT=""
GRAPH_NODES=""
GRAPH_EDGES=""
GRAPH_ROOT=""
GRAPH_FAILURES=""
GRAPH_ORPHANS=""
GRAPH_DANGLING=""
GRAPH_UNWIRED=""
GRAPH_CROSS=""
GRAPH_CYCLE=""
GRAPH_UNVERIFIED_COUNT=""
GRAPH_KINDS=""
GRAPH_MISSING=""
GRAPH_CONTRADICTION=""
for tok in $GRAPH_META; do
  case "$tok" in
    parse=*) GRAPH_PARSE="${tok#parse=}" ;;
    verdict=*) GRAPH_VERDICT="${tok#verdict=}" ;;
    nodes=*) GRAPH_NODES="${tok#nodes=}" ;;
    edges=*) GRAPH_EDGES="${tok#edges=}" ;;
    root=*) GRAPH_ROOT="${tok#root=}" ;;
    failures=*) GRAPH_FAILURES="${tok#failures=}" ;;
    orphans=*) GRAPH_ORPHANS="${tok#orphans=}" ;;
    dangling=*) GRAPH_DANGLING="${tok#dangling=}" ;;
    unwired=*) GRAPH_UNWIRED="${tok#unwired=}" ;;
    cross=*) GRAPH_CROSS="${tok#cross=}" ;;
    cycle=*) GRAPH_CYCLE="${tok#cycle=}" ;;
    unverified=*) GRAPH_UNVERIFIED_COUNT="${tok#unverified=}" ;;
    kinds=*) GRAPH_KINDS="${tok#kinds=}" ;;
    missing=*) GRAPH_MISSING="${tok#missing=}" ;;
    contradiction=*) GRAPH_CONTRADICTION="${tok#contradiction=}" ;;
  esac
done

GRAPH_COUNTS="$GRAPH_NODES nodes / $GRAPH_EDGES edges / $GRAPH_ORPHANS orphans / $GRAPH_DANGLING dangling edges / $GRAPH_UNWIRED unwired branches / $GRAPH_CROSS cross-branch violations / $GRAPH_CYCLE cycles"

if [ "$GRAPH_RC" -eq 99 ]; then
  record_fail "WF-23" "validator_missing" "tools/validate_graph.py present" "Claimed structural gate is absent (tools/validate_graph.py) — fail closed; a missing validator can never pass QC."
  record_fail "WF-15" "validator_missing" "graph validator summary" "WF-15 is derived from WF-23; the validator is absent, so linkage is unproven."
elif [ "$GRAPH_META_RC" -ne 0 ] || [ "$GRAPH_PARSE" != "ok" ]; then
  record_fail "WF-23" "validator_report_malformed" "parseable graph validator JSON" "Graph validator report malformed; parser exit status=$GRAPH_META_RC."
  record_fail "WF-15" "validator_report_malformed" "complete graph validator summary" "Graph validator report malformed; parser exit status=$GRAPH_META_RC. Malformed report is FAIL, never human-review PASS."
elif [ "$GRAPH_MISSING" != "none" ] || [ -z "$GRAPH_VERDICT" ] || [ -z "$GRAPH_NODES" ] || [ -z "$GRAPH_EDGES" ] || [ -z "$GRAPH_ROOT" ] || [ -z "$GRAPH_FAILURES" ] || [ -z "$GRAPH_ORPHANS" ] || [ -z "$GRAPH_UNVERIFIED_COUNT" ]; then
  record_fail "WF-23" "validator_report_incomplete missing=$GRAPH_MISSING" "complete graph validator report" "Required graph validator field missing or invalid: $GRAPH_MISSING. Missing fields are FAIL, never defaulted to zero."
  record_fail "WF-15" "validator_report_incomplete missing=$GRAPH_MISSING" "complete graph validator summary" "Required graph validator field missing or invalid: $GRAPH_MISSING. Missing fields are FAIL, never defaulted to zero."
elif [ "$GRAPH_CONTRADICTION" != "none" ]; then
  record_fail "WF-23" "validator_report_contradiction $GRAPH_CONTRADICTION" "consistent graph validator report" "Graph validator report contradicts itself: $GRAPH_CONTRADICTION; counts=$GRAPH_COUNTS; failures=$GRAPH_FAILURES; verdict=$GRAPH_VERDICT."
  record_fail "WF-15" "validator_report_contradiction $GRAPH_CONTRADICTION" "consistent graph validator report" "Graph validator report contradicts itself: $GRAPH_CONTRADICTION; counts=$GRAPH_COUNTS; failures=$GRAPH_FAILURES; verdict=$GRAPH_VERDICT."
elif [ "$GRAPH_FAILURES" -gt 0 ]; then
  record_fail "WF-23" "$GRAPH_COUNTS" "no structural failures (exit 0)" "Graph validator FAILED: $GRAPH_KINDS over $GRAPH_NODES nodes / $GRAPH_EDGES edges."
  record_fail "WF-15" "$GRAPH_COUNTS / failures=$GRAPH_FAILURES ($GRAPH_KINDS)" "0 orphans / 0 dangling / 0 unwired branches / 0 cross-branch violations" "Delivery chain is NOT fully linked: $GRAPH_KINDS. Do not ship this workflow."
elif [ "$GRAPH_RC" -eq 0 ] && [ "$GRAPH_VERDICT" = "PASS" ]; then
  record_pass "WF-23" "$GRAPH_COUNTS / root=$GRAPH_ROOT" "root+reachability+integrity+branches+termination+acyclic+cross-branch" "root+reachability+integrity+branches+termination+acyclic+cross-branch"
  record_pass "WF-15" "$GRAPH_COUNTS / root=$GRAPH_ROOT" "delivery chain fully linked" "Validator aggregate: $GRAPH_NODES nodes, $GRAPH_EDGES edges, $GRAPH_ORPHANS orphans, $GRAPH_DANGLING dangling edges, $GRAPH_UNWIRED unwired branches, $GRAPH_CROSS cross-branch violations, root=$GRAPH_ROOT"
elif [ "$GRAPH_RC" -eq 2 ] || [ "$GRAPH_VERDICT" = "UNVERIFIED" ]; then
  record_human "WF-23" "Graph validator could not verify this readback (exit $GRAPH_RC): the export is unparseable or does not expose branch targets. A QC agent must inspect the saved graph by hand; UNVERIFIED is never a PASS."
  record_human "WF-15" "Linkage unverified — WF-23 returned UNVERIFIED; a human must confirm the delivery chain."
  GRAPH_UNVERIFIED=1
else
  record_fail "WF-23" "validator_outcome_unexpected rc=$GRAPH_RC verdict=$GRAPH_VERDICT" "validator exit 0 and verdict PASS" "Unexpected graph validator outcome: rc=$GRAPH_RC verdict=$GRAPH_VERDICT; counts=$GRAPH_COUNTS."
  record_fail "WF-15" "validator_outcome_unexpected rc=$GRAPH_RC verdict=$GRAPH_VERDICT" "verified delivery chain" "Unexpected graph validator outcome: rc=$GRAPH_RC verdict=$GRAPH_VERDICT; counts=$GRAPH_COUNTS."
fi

# ── WF-18 + WF-21: Snapshot exists ────────────────────────────────────────────
SNAPSHOT_FOUND=0
if [ -d "$SNAPSHOT_DIR" ]; then
  WF_SNAPSHOT_DIR="$SNAPSHOT_DIR"
  # Search for any snapshot file containing the workflow id in its path
  if find "$SNAPSHOT_DIR" -name "*.json" 2>/dev/null | grep -q "$WORKFLOW_ID" 2>/dev/null; then
    SNAPSHOT_FOUND=1
  elif find "$SNAPSHOT_DIR" -path "*/$WORKFLOW_ID/*" -name "*.json" 2>/dev/null | head -1 | grep -q .; then
    SNAPSHOT_FOUND=1
  fi
fi

if [ "$SNAPSHOT_FOUND" -eq 1 ]; then
  SNAPSHOT_PATH=$(find "$SNAPSHOT_DIR" -name "*.json" 2>/dev/null | grep "$WORKFLOW_ID" | head -1 || echo "found")
  record_pass "WF-21" "snapshot_exists_and_non_empty" "snapshot present under data/snapshots/" "Snapshot: $SNAPSHOT_PATH — build is reversible via caf workflows restore"
else
  record_na "WF-21" "fresh-build: no snapshot on disk — N/A for a first-time build. caf workflows restore is not applicable until a snapshot is captured."
fi

# WF-18 — dependency manifest gate. Snapshot presence proves reversibility
# (WF-21) and nothing about dependencies; a build that references a tag,
# field, custom value, calendar or pipeline that does not exist is NOT
# verified by having a restore point. No manifest is a FAIL, never N/A.
if [ -z "$DEPS_MANIFEST" ]; then
  record_fail "WF-18" "no_dependency_manifest" "every referenced dependency listed in --deps manifest" "No --deps manifest supplied. The dependency-first contract is unproven: pass the machine-readable manifest listing every tag/field/custom value/calendar/pipeline the export references."
else
  DEPS_RC=0
  DEPS_JSON=$(python3 "$VALIDATOR" deps --export "$TMP" --deps "$DEPS_MANIFEST" 2>/dev/null) || DEPS_RC=$?
  DEPS_FIELDS=$(printf '%s' "$DEPS_JSON" | python3 -c "
import json,sys
try:
  d=json.load(sys.stdin)
except Exception:
  print('UNVERIFIED 0 none'); raise SystemExit
missing=d.get('missing') or []
print('%s %s %s' % (d.get('verdict','UNVERIFIED'), d.get('referenced',0), ','.join('%s:%s' % (m.get('kind'),m.get('name')) for m in missing) or 'none'))
" 2>/dev/null || echo "UNVERIFIED 0 none")
  read -r DEPS_VERDICT DEPS_REFERENCED DEPS_MISSING <<< "$DEPS_FIELDS"
  if [ "$DEPS_RC" -eq 0 ] && [ "$DEPS_VERDICT" = "PASS" ]; then
    record_pass "WF-18" "$DEPS_REFERENCED referenced / 0 missing" "every referenced dependency present in the manifest" "Dependency manifest covers every referenced object ($DEPS_MISSING missing)."
  else
    record_fail "WF-18" "referenced=$DEPS_REFERENCED missing=$DEPS_MISSING" "every referenced dependency present in the manifest" "Dependency manifest gate FAILED (exit $DEPS_RC): $DEPS_MISSING. Create these objects in GHL (or record approval) before shipping."
  fi
fi

# ── WF-24: Trigger entrance link ──────────────────────────────────────────────
# The trigger's targetActionId must equal the root node id. A trigger that is
# not linked to the first node renders as a floating card above a graph it does
# not enter; the graph hash cannot see it. Absent field => REQUIRES_HUMAN_REVIEW.
TRIGGER_LINK=$(printf '%s' "$EXPORT_OUT" | python3 -c "
import json,sys
try:
  d=json.load(sys.stdin)
except Exception:
  print('UNVERIFIED none none'); raise SystemExit
target=root=None
nodes=None
for d1 in (d, d.get('data') if isinstance(d,dict) else None):
  if not isinstance(d1, dict): continue
  wd=d1.get('workflowData')
  if isinstance(wd, dict) and isinstance(wd.get('templates'), list): nodes=wd['templates']
  elif isinstance(d1.get('templates'), list): nodes=d1['templates']
  if nodes: break
for n in nodes or []:
  if isinstance(n, dict) and n.get('parentKey') in (None, ''):
    root=n.get('id'); break
def walk(v):
  global target
  if isinstance(v, dict):
    for k,item in v.items():
      if k in ('targetActionId','target_action_id') and isinstance(item,str) and item: target=item
      walk(item)
  elif isinstance(v, list):
    for item in v: walk(item)
walk(d)
print('%s %s %s' % ('LINKED' if target else 'ABSENT', target or 'none', root or 'none'))
" 2>/dev/null || echo "UNVERIFIED none none")
read -r TRIGGER_STATE TRIGGER_TARGET TRIGGER_ROOT <<< "$TRIGGER_LINK"
if [ "$TRIGGER_STATE" = "LINKED" ] && [ "$TRIGGER_ROOT" != "none" ] && [ "$TRIGGER_TARGET" = "$TRIGGER_ROOT" ]; then
  record_pass "WF-24" "targetActionId=$TRIGGER_TARGET root=$TRIGGER_ROOT" "trigger link equals root node id" "Trigger entrance linked to the root node."
elif [ "$TRIGGER_STATE" = "ABSENT" ] || [ "$TRIGGER_ROOT" = "none" ]; then
  record_human "WF-24" "The export does not expose the trigger's targetActionId; a QC agent must GET /workflow/<loc>/<wf>/trigger/<trigger-id> and confirm it equals the root node id ($TRIGGER_ROOT)."
else
  record_fail "WF-24" "targetActionId=$TRIGGER_TARGET root=$TRIGGER_ROOT" "trigger link equals root node id" "Trigger link does not point at the root node (or the readback is unparseable). The canvas shows a trigger that does not enter the graph."
fi

# ── Human-review items (noted, not failed by script) ─────────────────────────
record_human "WF-1"  "Workflow name must be verified against plan/outline by QC agent reading export output"
record_human "WF-2"  "Tags must be verified by QC agent: check each tag in export against plan, GET-verify in GHL"
record_human "WF-8"  "If/Else conditions (fields, operators, AND/OR logic) require QC agent review of export output"
record_human "WF-9"  "Wait timing requires QC review: duration/event mode, source, Set event start time before dependent waits, offsets, timezone, past-due and re-entry; see references/workflow-timing.md"
record_human "WF-10" "Custom fields (data type + exact name) require QC agent review of export output"
record_human "WF-11" "Custom values (non-empty + exact name) require QC agent review of export output"
record_human "WF-13" "Email From Name/From Email require QC agent review of export output"
record_human "WF-14" "Webhook URL/method/headers require QC agent review of export output"
record_human "WF-16" "Advanced settings (Stop-on-Response, time window, timezone) require QC agent review"
record_human "WF-17" "Edge case decisions require QC agent review against plan"
record_human "WF-20" "Hallucination detection (WF-20) requires QC agent to reconcile all build-agent claims against export"

# ── WF-19: TRINITY completeness — MECHANICAL HARD GATE for conversational builds ──
# With --conversational, WF-19 is enforced by executing Skill 38's qc-trinity-registry.sh
# (the SAME script the SOPs claim is a hard pre-registration gate). Any non-zero exit
# (INCOMPLETE trinity, or NO conversation-workflows folder) is a mechanical WF-19 FAIL —
# a conversational workflow that registers without all three TRINITY legs is not done.
# With --handoff, scope the registry check to that build's playbook slug where supported.
# Without a usable slug or handoff, the registry-wide fallback is explicitly recorded.
# Without --conversational the item stays human-review (TRINITY is N/A for a mechanical
# automation with no SMS/conversational-AI leg).
if [ "$CONVERSATIONAL" -eq 1 ]; then
  _TRINITY=""
  for _cand in \
    "$SCRIPT_DIR/../38-conversational-ai-system/scripts/qc-trinity-registry.sh" \
    "$HOME/.openclaw/skills/38-conversational-ai-system/scripts/qc-trinity-registry.sh" \
    "/data/.openclaw/skills/38-conversational-ai-system/scripts/qc-trinity-registry.sh"; do
    if [ -f "$_cand" ]; then _TRINITY="$_cand"; break; fi
  done
  if [ -z "$_TRINITY" ]; then
    # Claimed hard gate is unavailable → fail CLOSED, never skip a claimed gate.
    record_fail "WF-19" "trinity_registry_not_found" "qc-trinity-registry.sh present + exit 0" \
      "REQUIRES_OPERATOR: --conversational build but Skill 38 qc-trinity-registry.sh not found on any known path — cannot verify TRINITY; fail-closed."
  else
    SLUG=""
    SCOPE_NOTE=""
    if [ -n "$HANDOFF_FILE" ]; then
      SLUG=$(python3 -c 'import json,os,re,sys; p=sys.argv[1]; keys=("playbook_slug","playbookSlug","slug","playbook","playbook_id","playbookId"); d={};
try:
 d=json.load(open(p,encoding="utf-8"))
except Exception:
 pass
pick=lambda o: next((str(o[k]).strip() for k in keys if isinstance(o,dict) and o.get(k) is not None and str(o[k]).strip()),"")
v=pick(d) or pick(d.get("build_contract")) or pick(d.get("buildContract"))
if not v:
 for k in ("to_build","toBuild"):
  a=d.get(k) if isinstance(d,dict) else None
  if isinstance(a,list) and a:
   v=pick(a[0]); break
if not v:
 b=os.path.basename(p)
 for s in ("--build-contract.json","-build-contract.json",".handoff.json","-handoff.json",".json"):
  if b.endswith(s):
   b=b[:-len(s)]; break
 v=b
print(re.sub(r"[^A-Za-z0-9._-]","",v))' "$HANDOFF_FILE" 2>/dev/null || true)
      if [ -n "$SLUG" ]; then
        SCOPE_NOTE=""
        TRINITY_OUT=""
        if TRINITY_OUT=$(bash "$_TRINITY" --slug "$SLUG" --json 2>&1); then
          _trc=0
        else
          _trc=$?
          if printf '%s' "$TRINITY_OUT" | grep -qiE 'unknown option|unrecognized option|illegal option|invalid option|usage:'; then
            SCOPE_NOTE=" (fallback: qc-trinity-registry.sh rejected --slug)"
            if TRINITY_OUT=$(bash "$_TRINITY" 2>&1); then
              _trc=0
            else
              _trc=$?
            fi
          fi
        fi
      else
        SCOPE_NOTE=" (registry-wide: no playbook slug in handoff)"
        TRINITY_OUT=""
        if TRINITY_OUT=$(bash "$_TRINITY" 2>&1); then
          _trc=0
        else
          _trc=$?
        fi
      fi
    else
      SCOPE_NOTE=" (registry-wide (no handoff))"
      SLUG=""
      TRINITY_OUT=""
      if TRINITY_OUT=$(bash "$_TRINITY" 2>&1); then
        _trc=0
      else
        _trc=$?
      fi
    fi

    TRINITY_DETAIL="$(printf '%s' "$TRINITY_OUT" | tr '\n' ' ' | cut -c1-240)"
    if [ -n "$SLUG" ]; then
      SCOPE_SLUG_TEXT=" Scope: slug=$SLUG"
    elif [ -z "$HANDOFF_FILE" ]; then
      SCOPE_SLUG_TEXT=" Scope: registry-wide (no handoff)"
    else
      SCOPE_SLUG_TEXT=" Scope: registry-wide (no slug in handoff)"
    fi
    if [ "$_trc" -eq 0 ]; then
      if [ -n "$SLUG" ]; then
        record_pass "WF-19" "trinity_complete slug=$SLUG" "all TRINITY legs present" \
          "qc-trinity-registry.sh exit 0 — GHL workflow + Layer-2 playbook + Build-with-AI prompt all present. Detail: $TRINITY_DETAIL$SCOPE_NOTE$SCOPE_SLUG_TEXT"
      else
        record_pass "WF-19" "trinity_complete" "all TRINITY legs present" \
          "qc-trinity-registry.sh exit 0 — GHL workflow + Layer-2 playbook + Build-with-AI prompt all present. Detail: $TRINITY_DETAIL$SCOPE_NOTE$SCOPE_SLUG_TEXT"
      fi
    else
      record_fail "WF-19" "trinity_incomplete_exit_${_trc}" "all TRINITY legs present (exit 0)" \
        "CRITICAL: qc-trinity-registry.sh exit $_trc — TRINITY incomplete or no conversation-workflows folder. A conversational workflow must NOT register without all three legs. Detail: $TRINITY_DETAIL$SCOPE_NOTE$SCOPE_SLUG_TEXT"
    fi
  fi
else
  record_human "WF-19" "TRINITY N/A for this mechanical build. Re-run with --conversational to enforce qc-trinity-registry.sh as a hard gate (any non-zero exit = WF-19 FAIL)."
fi

# ── WEIGHTED QUALITY RUBRIC (references/workflow-quality-rubric.md) ────────────
# SUPERSET OVERLAY computed AFTER WF-1..21 (never instead of). Each of the 8
# dimensions maps to existing WF evidence. Dimensions whose WF evidence is fully
# machine-asserted here get a mechanical anchor (1/5/10); dimensions that depend
# on REQUIRES_HUMAN_REVIEW WF items emit a conservative machine FLOOR plus a
# rubric_human_grade flag so the Step-9 QC sub-agent grades them 1/5/10 and
# recomputes the final weighted score. The script's own weighted score is a
# FLOOR (machine-knowable lower bound), surfaced alongside the WF result so a
# real build emits BOTH numbers. Ship threshold (final, after human grading): >= 8.5.
#
# Weights: D1=20 D2=15 D3=15 D4=12 D5=12 D6=10 D7=8 D8=8  (sum=100)

_wf() { echo "${ITEM_STATUS[$1]:-UNKNOWN}"; }

# D2 Trigger correctness — fully mechanical (WF-3 + WF-4)
if [ "$(_wf WF-3)" = "PASS" ] && [ "$(_wf WF-4)" = "PASS" ]; then D2=10
elif [ "$(_wf WF-3)" = "PASS" ]; then D2=5
else D2=1; fi

# D3 Action completeness & ordering — fully mechanical (WF-7 + WF-15)
if [ "$(_wf WF-7)" = "PASS" ] && [ "$(_wf WF-15)" = "PASS" ]; then D3=10
elif [ "$(_wf WF-7)" = "PASS" ]; then D3=5
else D3=1; fi

# D6 Deliverability integrity — WF-12 is mechanical; WF-13/2/10/11 need human.
# Machine FLOOR from WF-12: empty-on-LIVE => 1, key-present(empty draft / non-empty) => 5 floor.
if [ "$(_wf WF-12)" = "FAIL" ] || [ "$(_wf WF-22)" = "FAIL" ]; then D6=1
else D6=5; fi   # floor; QC sub-agent raises to 10 once senders + deps GET-verified
D6_HUMAN=1

# D8 Naming/testability — WF-5 + WF-18/21 mechanical; WF-1/WF-20 need human.
# WF-18/WF-21 score N/A on a fresh build (no prior snapshot to compare against),
# which is not a failure. Treat N/A as passing for the D8 floor so a clean
# first-time build is not penalised.
_wf18="${ITEM_STATUS[WF-18]:-UNKNOWN}"
_wf21="${ITEM_STATUS[WF-21]:-UNKNOWN}"
if [ "$(_wf WF-5)" = "PASS" ] \
   && { [ "$_wf18" = "PASS" ] || [ "$_wf18" = "N/A" ]; } \
   && { [ "$_wf21" = "PASS" ] || [ "$_wf21" = "N/A" ]; }; then D8=5
else D8=1; fi   # floor; QC sub-agent raises to 10 once names + WF-20 reviewed
D8_HUMAN=1

# D1 Goal-fit, D4 Branching, D5 Edge cases — depend on human-review WF items.
# Emit a conservative floor of 5 (build mechanically present, quality ungraded)
# and flag for human grading. NOT 10 — the script must never claim goal-fit.
D1=5; D1_HUMAN=1
D4=5; D4_HUMAN=1
D5=5; D5_HUMAN=1

# D7 Idempotency — WF-6 mechanical; Stop-on-Response (WF-16) needs human.
if [ "$(_wf WF-6)" = "PASS" ]; then D7=5
else D7=1; fi   # floor; QC sub-agent raises to 10 once Stop-on-Response reviewed
D7_HUMAN=1

# Weighted FLOOR score (machine lower bound, x100 to stay integer-safe in bash)
RUBRIC_FLOOR_X100=$(( D1*20 + D2*15 + D3*15 + D4*12 + D5*12 + D6*10 + D7*8 + D8*8 ))
# Format as N.NN
RUBRIC_FLOOR=$(printf "%d.%02d" $(( RUBRIC_FLOOR_X100 / 100 )) $(( RUBRIC_FLOOR_X100 % 100 )))
RUBRIC_NEEDS_HUMAN=$(( D1_HUMAN + D4_HUMAN + D5_HUMAN + D6_HUMAN + D7_HUMAN + D8_HUMAN ))

# Weighted CEILING (SK1-46): best case where every human-graded dimension is later
# scored 10 (mechanical D2/D3 keep their machine score). If even this ceiling is
# below the 8.5 ship threshold, the weighted rubric PROVES the build can never ship
# regardless of human grading — so the rubric must participate in the exit decision,
# not merely be printed. (Gate applied in the exit section below.)
_ceil() { if [ "$2" = "1" ]; then echo 10; else echo "$1"; fi; }
RUBRIC_CEILING_X100=$(( $(_ceil "$D1" "$D1_HUMAN")*20 + $(_ceil "$D2" 0)*15 \
  + $(_ceil "$D3" 0)*15 + $(_ceil "$D4" "$D4_HUMAN")*12 + $(_ceil "$D5" "$D5_HUMAN")*12 \
  + $(_ceil "$D6" "$D6_HUMAN")*10 + $(_ceil "$D7" "$D7_HUMAN")*8 + $(_ceil "$D8" "$D8_HUMAN")*8 ))
RUBRIC_CEILING=$(printf "%d.%02d" $(( RUBRIC_CEILING_X100 / 100 )) $(( RUBRIC_CEILING_X100 % 100 )))

# Identify the lowest scoring dimension(s) for the loop-back message.
LOWEST_DIM=""; LOWEST_VAL=11
for d in "D1:$D1" "D2:$D2" "D3:$D3" "D4:$D4" "D5:$D5" "D6:$D6" "D7:$D7" "D8:$D8"; do
  v="${d#*:}"
  if [ "$v" -lt "$LOWEST_VAL" ]; then LOWEST_VAL="$v"; LOWEST_DIM="${d%%:*}"; fi
done

# ── Output ─────────────────────────────────────────────────────────────────────
# WF-19 is a MECHANICAL item on a --conversational build (trinity hard gate) and a
# human-review item otherwise — place it in the right display bucket accordingly.
if [ "$CONVERSATIONAL" -eq 1 ]; then
  MECHANICAL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-22" "WF-15" "WF-18" "WF-19" "WF-21" "WF-23" "WF-24")
  HUMAN_ITEMS=("WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-20")
else
  MECHANICAL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-22" "WF-15" "WF-18" "WF-21" "WF-23" "WF-24")
  HUMAN_ITEMS=("WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-19" "WF-20")
fi

if [ "$JSON_MODE" -eq 1 ]; then
  # Build JSON manually (no python dependency required)
  echo "{"
  echo "  \"workflow_id\": \"$WORKFLOW_ID\","
  echo "  \"publish_intent\": \"$PUBLISH_INTENT\","
  echo "  \"re_entry_decision\": \"$RE_ENTRY_DECISION\","
  echo "  \"mechanical_pass\": $PASS_COUNT,"
  echo "  \"mechanical_fail\": $FAIL_COUNT,"
  echo "  \"overall_mechanical\": \"$([ "$FAIL_COUNT" -eq 0 ] && echo PASS || echo FAIL)\","
  echo "  \"items\": {"
  ALL_ITEMS=("WF-3" "WF-4" "WF-5" "WF-6" "WF-7" "WF-12" "WF-22" "WF-15" "WF-18" "WF-21" "WF-23" "WF-24" \
             "WF-1" "WF-2" "WF-8" "WF-9" "WF-10" "WF-11" "WF-13" "WF-14" "WF-16" "WF-17" "WF-19" "WF-20")
  FIRST=1
  for item in "${ALL_ITEMS[@]}"; do
    [ "$FIRST" -eq 0 ] && echo ","
    FIRST=0
    STATUS="${ITEM_STATUS[$item]:-UNKNOWN}"
    OBSERVED="${ITEM_OBSERVED[$item]:-n/a}"
    EXPECTED="${ITEM_EXPECTED[$item]:-n/a}"
    NOTES="${ITEM_NOTES[$item]:-}"
    # Escape quotes
    OBSERVED=$(echo "$OBSERVED" | sed 's/"/\\"/g')
    EXPECTED=$(echo "$EXPECTED" | sed 's/"/\\"/g')
    NOTES=$(echo "$NOTES" | sed 's/"/\\"/g')
    printf '    "%s": {"status": "%s", "observed": "%s", "expected": "%s", "notes": "%s"}' \
      "$item" "$STATUS" "$OBSERVED" "$EXPECTED" "$NOTES"
  done
  echo ""
  echo "  },"
  # Weighted quality rubric (SUPERSET overlay, computed AFTER WF-1..21)
  echo "  \"rubric\": {"
  echo "    \"weighted_floor\": $RUBRIC_FLOOR,"
  echo "    \"weighted_ceiling\": $RUBRIC_CEILING,"
  echo "    \"ship_threshold\": 8.5,"
  echo "    \"needs_human_grading\": $RUBRIC_NEEDS_HUMAN,"
  echo "    \"lowest_dimension\": \"$LOWEST_DIM\","
  echo "    \"note\": \"weighted_floor is the machine-knowable lower bound; the Step-9 QC sub-agent grades the human dimensions (D1/D4/D5/D6/D7/D8) 1/5/10 per references/workflow-quality-rubric.md and recomputes the final score. Ship only if final >= 8.5.\","
  echo "    \"dimensions\": {"
  echo "      \"D1_goal_fit\":       {\"weight\": 20, \"score_floor\": $D1, \"human_grade_required\": true},"
  echo "      \"D2_trigger\":        {\"weight\": 15, \"score\": $D2, \"human_grade_required\": false},"
  echo "      \"D3_steps_ordering\": {\"weight\": 15, \"score\": $D3, \"human_grade_required\": false},"
  echo "      \"D4_branching\":      {\"weight\": 12, \"score_floor\": $D4, \"human_grade_required\": true},"
  echo "      \"D5_edge_cases\":     {\"weight\": 12, \"score_floor\": $D5, \"human_grade_required\": true},"
  echo "      \"D6_deliverability\": {\"weight\": 10, \"score_floor\": $D6, \"human_grade_required\": true},"
  echo "      \"D7_idempotency\":    {\"weight\": 8,  \"score_floor\": $D7, \"human_grade_required\": true},"
  echo "      \"D8_naming\":         {\"weight\": 8,  \"score_floor\": $D8, \"human_grade_required\": true}"
  echo "    }"
  echo "  }"
  echo "}"
else
  # Human-readable output
  echo "═══════════════════════════════════════════════════════════"
  echo "  Skill 44 Per-Build QC — workflow: $WORKFLOW_ID"
  echo "  Publish intent: $PUBLISH_INTENT | Re-entry: $RE_ENTRY_DECISION"
  echo "═══════════════════════════════════════════════════════════"
  echo ""
  echo "── Mechanical assertions ──"
  for item in "${MECHANICAL_ITEMS[@]}"; do
    STATUS="${ITEM_STATUS[$item]:-UNKNOWN}"
    OBSERVED="${ITEM_OBSERVED[$item]:-n/a}"
    EXPECTED="${ITEM_EXPECTED[$item]:-n/a}"
    NOTES="${ITEM_NOTES[$item]:-}"
    printf "  %-6s %-5s | observed: %-45s | expected: %s\n" "$item" "$STATUS" "$OBSERVED" "$EXPECTED"
    [ -n "$NOTES" ] && printf "         NOTE: %s\n" "$NOTES"
  done
  echo ""
  echo "── Items requiring QC agent review (not machine-assertable) ──"
  for item in "${HUMAN_ITEMS[@]}"; do
    NOTES="${ITEM_NOTES[$item]:-}"
    printf "  %-6s REQUIRES_HUMAN_REVIEW | %s\n" "$item" "$NOTES"
  done
  echo ""
  echo "═══════════════════════════════════════════════════════════"
  echo "  Mechanical result: $PASS_COUNT PASS | $FAIL_COUNT FAIL"
  echo "═══════════════════════════════════════════════════════════"
  if [ "$FAIL_COUNT" -gt 0 ]; then
    echo "  PER-BUILD QC FAILED — $FAIL_COUNT mechanical blocker(s). See items above."
    echo "  Do NOT declare workflow done. Fix failing items and re-run QC."
  else
    echo "  Mechanical QC PASSED — QC agent must still review human-review items above."
  fi
  echo ""
  # Weighted quality rubric (SUPERSET overlay — computed AFTER WF-1..21, never instead of)
  echo "── Weighted quality rubric (references/workflow-quality-rubric.md) ──"
  printf "  %-22s w=%-3s %s\n" "D1 Goal-fit"        "20" "floor=$D1  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D2 Trigger"         "15" "score=$D2"
  printf "  %-22s w=%-3s %s\n" "D3 Steps/ordering"  "15" "score=$D3"
  printf "  %-22s w=%-3s %s\n" "D4 Branching"       "12" "floor=$D4  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D5 Edge cases"      "12" "floor=$D5  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D6 Deliverability"  "10" "floor=$D6  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D7 Idempotency"     "8"  "floor=$D7  [HUMAN GRADE REQUIRED]"
  printf "  %-22s w=%-3s %s\n" "D8 Naming/testability" "8" "floor=$D8  [HUMAN GRADE REQUIRED]"
  echo "  ─────────────────────────────────────────────"
  echo "  WEIGHTED FLOOR SCORE: $RUBRIC_FLOOR / 10   (ship threshold: >= 8.5)"
  echo "  WEIGHTED CEILING:     $RUBRIC_CEILING / 10   (best case if human dims all grade 10)"
  echo "  Lowest dimension: $LOWEST_DIM"
  echo "  NOTE: this is the machine-knowable FLOOR. The Step-9 QC sub-agent must grade the"
  echo "        $RUBRIC_NEEDS_HUMAN human dimensions (D1/D4/D5/D6/D7/D8) 1/5/10 per the rubric and"
  echo "        recompute the FINAL weighted score. Ship ONLY if the final score is >= 8.5;"
  echo "        below 8.5 → loop, naming the low dimension ($LOWEST_DIM)."
  echo ""
fi

# ── FAB-QC overlay (library-aware: template fidelity / copy substance / persona / ──
#    flexibility / funnel<->automation link). SUPERSET on top of WF-1..21 (which is the
#    D3 mechanical floor). Runs whenever --fab/--evidence is passed. The shared scorer is
#    the same one Skill 6 uses (shared-utils/fab_qc.py). The combined "done" bar is:
#    WF mechanical PASS AND FAB >= 8.5.
#
# FAIL-CLOSED CONTRACT (FIX-XC-03g): when FAB_MODE=1 the overlay is a HARD gate. If the
# score is UNAVAILABLE for ANY reason — scorer absent, evidence_root missing, or the
# scorer emits nothing — the build is NOT auto-passed. FAB_RC=1, the verdict is
# REQUIRES_OPERATOR, and the script exits non-zero. A claimed gate is never silently
# skipped. The canonical evidence_root is created in Step 0.4 (automation_matcher.step0_match
# writes routing/match-decision.json + persona-selection-log.md there) and the SAME root is
# passed here at Step 9.3c via --evidence.
FAB_RC=0
FAB_SCORE="n/a"
FAB_STATUS="not_run"
FAB_FAIL_REASON=""
if [ "$FAB_MODE" -eq 1 ]; then
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
  FAB_SCORER="$REPO_ROOT/shared-utils/fab_qc.py"
  FAB_PRODUCER="$REPO_ROOT/shared-utils/fab_artifact.py"
  # Canonical evidence_root default (Step 0.4). A missing root is NOT a pass — it fails closed below.
  if [ -z "$FAB_EVIDENCE" ]; then FAB_EVIDENCE="$CAF_DATA/evidence/$WORKFLOW_ID"; fi
  echo ""
  echo "═══ FAB-QC overlay (library-aware, >= 8.5 — FAIL-CLOSED) ═══"
  if [ ! -f "$FAB_SCORER" ]; then
    FAB_RC=1; FAB_STATUS="requires_operator"
    FAB_FAIL_REASON="FAB-QC scorer not found ($FAB_SCORER) — cannot prove >= 8.5"
    echo "  REQUIRES_OPERATOR: $FAB_FAIL_REASON"
  elif [ ! -d "$FAB_EVIDENCE" ]; then
    FAB_RC=1; FAB_STATUS="requires_operator"
    FAB_FAIL_REASON="evidence_root not found ($FAB_EVIDENCE) — Step 0.4 must create it and Step 9.3c must pass the SAME root via --evidence"
    echo "  REQUIRES_OPERATOR: $FAB_FAIL_REASON"
  else
    # PRODUCER (D4): convert the REAL exported workflow ($TMP) into build/fab-artifact.json so the
    # scorer below judges the actual built steps + copy, not a hand-authored fixture. Only writes
    # when a routing/match-decision.json receipt exists (a template-aware build) and never clobbers
    # an existing artifact. Best-effort: it never blocks QC.
    if [ -f "$FAB_PRODUCER" ] && [ -f "$FAB_EVIDENCE/routing/match-decision.json" ] \
       && [ ! -f "$FAB_EVIDENCE/build/fab-artifact.json" ]; then
      python3 "$FAB_PRODUCER" --evidence "$FAB_EVIDENCE" --kind automation \
        --workflow "$TMP" --quiet 2>/dev/null || true
    fi
    FAB_JSON="$(python3 "$FAB_SCORER" --evidence "$FAB_EVIDENCE" --kind automation --json 2>/dev/null || true)"
    if [ -n "$FAB_JSON" ]; then
      FAB_SCORE="$(printf '%s' "$FAB_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["score"]);' 2>/dev/null || echo n/a)"
      FAB_PASS="$(printf '%s' "$FAB_JSON" | python3 -c 'import json,sys;d=json.load(sys.stdin);print("1" if d["passed"] else "0");' 2>/dev/null || echo 0)"
      python3 "$FAB_SCORER" --evidence "$FAB_EVIDENCE" --kind automation 2>/dev/null || true
      if [ "$FAB_PASS" = "1" ]; then
        FAB_STATUS="pass"
      else
        FAB_RC=1; FAB_STATUS="fail"
        FAB_FAIL_REASON="FAB-QC below 8.5 (score $FAB_SCORE)"
      fi
    else
      # Scorer produced nothing (missing routing/match-decision.json, malformed evidence,
      # or a scorer error). This is UNAVAILABLE, not a pass → fail CLOSED.
      FAB_RC=1; FAB_STATUS="requires_operator"
      FAB_FAIL_REASON="FAB-QC could not score this evidence tree (ensure Step 0.4 wrote routing/match-decision.json + persona-selection-log.md under $FAB_EVIDENCE)"
      echo "  REQUIRES_OPERATOR: $FAB_FAIL_REASON"
    fi
  fi
fi

# ── Append to build-events ledger ─────────────────────────────────────────────
mkdir -p "$(dirname "$BUILD_EVENTS_LEDGER")" 2>/dev/null || true
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ" 2>/dev/null || date +"%Y-%m-%dT%H:%M:%SZ")
VERDICT="$([ "$FAIL_COUNT" -eq 0 ] && [ "$FAB_RC" -eq 0 ] && echo PASS || echo FAIL)"
cat >> "$BUILD_EVENTS_LEDGER" 2>/dev/null << LEDGER_EOF
{"event":"qc_run","timestamp":"${TIMESTAMP}","workflow_id":"${WORKFLOW_ID}","publish_intent":"${PUBLISH_INTENT}","re_entry":"${RE_ENTRY_DECISION}","mechanical_pass":${PASS_COUNT},"mechanical_fail":${FAIL_COUNT},"verdict":"${VERDICT}","conversational":${CONVERSATIONAL},"fab_mode":${FAB_MODE},"fab_score":"${FAB_SCORE}","fab_status":"${FAB_STATUS}","rubric_weighted_floor":${RUBRIC_FLOOR},"rubric_weighted_ceiling":${RUBRIC_CEILING},"rubric_ship_threshold":8.5,"rubric_needs_human_grading":${RUBRIC_NEEDS_HUMAN},"rubric_lowest_dimension":"${LOWEST_DIM}"}
LEDGER_EOF

[ "$FAIL_COUNT" -gt 0 ] && exit 1
# WF-23/WF-15 UNVERIFIED is a non-success outcome: the caller must never see 0.
if [ "${GRAPH_UNVERIFIED:-0}" = "1" ]; then
  echo "PER-BUILD QC UNVERIFIED — WF-23 could not verify the saved graph (no structural failures were reported, but the export is unparseable or does not expose branch targets). UNVERIFIED is not a pass; a human must inspect the graph." >&2
  exit 2
fi
# FAB-QC overlay is a HARD, FAIL-CLOSED gate when it ran: the build is "done" only if the
# score is available AND >= 8.5. An UNAVAILABLE score is REQUIRES_OPERATOR, never a pass.
if [ "$FAB_RC" -ne 0 ]; then
  if [ "$FAB_STATUS" = "requires_operator" ]; then
    echo "PER-BUILD QC FAILED — REQUIRES_OPERATOR: ${FAB_FAIL_REASON}. FAB-QC is a hard gate and cannot be skipped."
  else
    echo "PER-BUILD QC FAILED — ${FAB_FAIL_REASON:-FAB-QC below 8.5 (score $FAB_SCORE)}. Fix the lowest dimension and re-run."
  fi
  exit 1
fi
# ── Rubric ship gate (SK1-46): the weighted rubric now participates in the exit ──
# decision. If the CEILING (every human dimension optimistically graded 10) is still
# below the 8.5 ship threshold, the build can NEVER ship regardless of human grading
# — so this is a hard, no-false-positive FAIL. (When --fab ran, the FAB overlay above
# is the authoritative >= 8.5 proof; this ceiling gate is the floor-side backstop for
# the mechanical-only path that previously ignored the rubric entirely.)
if [ "$RUBRIC_CEILING_X100" -lt 850 ]; then
  echo "PER-BUILD QC FAILED — weighted rubric ceiling ${RUBRIC_CEILING}/10 is below the 8.5 ship threshold; even perfect human grading of the ungraded dimensions cannot reach ship quality. Lowest dimension: ${LOWEST_DIM}. Fix it and re-run."
  exit 1
fi
exit 0

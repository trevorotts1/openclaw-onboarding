#!/usr/bin/env bash
# 11-run-qc-checklist.sh — Skill 38 Pre-Handoff QC (mechanical checks)
# Automates the file-existence / cron / config-validate / tunnel-curl
# items from protocols/pre-handoff-qc-protocol.md. Human-judgment items
# (tone, copy, agent behavior) stay in the markdown checklist.
#
# OS-aware (Darwin + Linux). Exit 0 on full pass, 1 if any item fails.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# -------- OS detection --------
OS_KERNEL="$(uname -s 2>/dev/null || echo unknown)"
case "$OS_KERNEL" in
  Darwin) OS=mac ;;
  Linux)  OS=linux ;;
  *)      OS=other ;;
esac

# -------- Master files dir --------
MASTER_FILES_POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
if [ -f "$MASTER_FILES_POINTER" ]; then
  MASTER_FILES_DIR="$(cat "$MASTER_FILES_POINTER")"
else
  MASTER_FILES_DIR="${MASTER_FILES_DIR:-}"
fi

PASS=0
FAIL=0
report_pass() { echo "  [PASS] $*"; PASS=$((PASS+1)); }
report_fail() { echo "  [FAIL] $*"; FAIL=$((FAIL+1)); }
section()     { echo ""; echo "=== $* ==="; }

# -------- Resolve skill 38 root --------
# Resolve DYNAMICALLY from this script's own location — this script lives at
# <skill-root>/scripts/11-run-qc-checklist.sh, so the skill root is SCRIPT_DIR's parent.
# Do NOT hardcode a legacy path (~/clawd/skills/38-openclaw-cloudflare-tunnel no longer
# exists; the skill is 38-conversational-ai-system under whatever skills root it was
# installed to). SKILL38_ROOT may still be overridden via env for tests.
SKILL38_ROOT="${SKILL38_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"

section "Skill 38 root"
if [ -d "$SKILL38_ROOT" ]; then
  report_pass "skill root: $SKILL38_ROOT"
else
  report_fail "skill root not found (SKILL38_ROOT=$SKILL38_ROOT)"
fi

# -------- File existence: protocols / templates / scripts / references --------
# NOTE (v1.4.18): the QC/handoff protocol is the REPO-ROOT ../QC-PROTOCOL.md
# (the governing Sub-Agent Handoff + Mandatory QC Protocol) plus the skill's own
# protocols/pre-handoff-qc-protocol.md. There is no protocols/qc-protocol.md or
# protocols/handoff-protocol.md in this skill (those phantom entries used to FAIL
# on every clean install). Check the files that actually ship.
section "File existence — protocols/ (skill QC protocol + repo-root governing protocol)"
PROTOCOL_FILES=(
  "protocols/pre-handoff-qc-protocol.md"
)
for f in "${PROTOCOL_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done
# The governing QC protocol lives at the repo root (one level above the skill).
if [ -f "$SKILL38_ROOT/../QC-PROTOCOL.md" ]; then
  report_pass "../QC-PROTOCOL.md (repo-root governing Sub-Agent Handoff + Mandatory QC Protocol)"
else
  echo "  [SKIP] ../QC-PROTOCOL.md not found relative to the skill root (expected when the skill is installed standalone, outside the onboarding repo)"
fi

section "File existence — templates/ (journey + channel)"
# Journey templates live under templates/journey-templates/ (8 per-vertical dirs,
# each with journey.md, plus a registry.md) — NOT a single templates/journey-template.md
# (that phantom path used to FAIL on every clean install).
TEMPLATE_FILES=(
  "templates/channel-playbook-template.md"
  "templates/client-reference-sheet-template.md"
  "templates/journey-templates/registry.md"
)
for f in "${TEMPLATE_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done
# Assert the 8 customer-journey templates are present (coach + 7 verticals).
JOURNEY_COUNT="$(find "$SKILL38_ROOT/templates/journey-templates" -mindepth 2 -name 'journey.md' 2>/dev/null | wc -l | tr -d ' ')"
if [ "${JOURNEY_COUNT:-0}" -ge 8 ]; then
  report_pass "templates/journey-templates/ has $JOURNEY_COUNT journey.md files (coach + 7 verticals)"
else
  report_fail "templates/journey-templates/ has only ${JOURNEY_COUNT:-0} journey.md files (expected 8: coach + 7 verticals)"
fi

section "File existence — scripts/ (install + QC)"
SCRIPT_FILES=(
  "scripts/11-run-qc-checklist.sh"
  "scripts/12-scaffold-channel-playbooks.sh"
  "scripts/qc-23-key-bodies.sh"
  "scripts/qc-trinity-registry.sh"
  "scripts/qc-send-directive.sh"
  "scripts/qc-conversation-memory.sh"
  "scripts/qc-playbook-doc.sh"
  "scripts/qc-reference-sheet.sh"
  "scripts/22-notify-client-doc.sh"
  "scripts/qc-notify-client-doc.sh"
  "scripts/24-update-tools-md.sh"
  "scripts/qc-tools-md-ghl-ref.sh"
  "scripts/qc-communications-playbook-standard.sh"
  "scripts/qc-ghl-raw-body-standard.sh"
  "scripts/qc-notion-doc-standard.sh"
  "scripts/33-runtime-tool-gating-prover.sh"
  "scripts/qc-runtime-tool-gating.sh"
)
for f in "${SCRIPT_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done

section "File existence — references/"
REFERENCE_FILES=(
  "references/subagent-delegation-pattern.md"
)
for f in "${REFERENCE_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done

# -------- openclaw cron list --------
# These are the exact names 04-register-crons.sh registers via `openclaw cron add`
# (model-version-freshness is BUNDLED into proactive-suggestions-scan; the monthly
# comprehensive review IS system-health-heartbeat — there is no separate cron for them).
section "openclaw cron list — 5 expected crons"
EXPECTED_CRONS=(
  "conversation-log-summarizer"
  "analytics-weekly-digest"
  "weekly-tune-up"
  "proactive-suggestions-scan"
  "system-health-heartbeat"
)
if command -v openclaw >/dev/null 2>&1; then
  CRON_OUT="$(openclaw cron list 2>&1 || true)"
  for name in "${EXPECTED_CRONS[@]}"; do
    if printf '%s\n' "$CRON_OUT" | grep -q "$name"; then
      report_pass "cron present: $name"
    else
      report_fail "cron MISSING: $name"
    fi
  done
  # Runtime credential watcher (INFORMATIONAL, non-blocking — registered by
  # 04-register-crons.sh; does NOT affect the FAIL count so it can never break a
  # green build on a box that predates it).
  if printf '%s\n' "$CRON_OUT" | grep -q "ghl-pit-liveness"; then
    echo "  [PASS] cron present: ghl-pit-liveness (daily runtime-PIT liveness watcher)"
  else
    echo "  [INFO] cron ghl-pit-liveness not found — run scripts/04-register-crons.sh to register the daily runtime-PIT watcher (non-blocking)"
  fi
else
  report_fail "openclaw CLI not on PATH — cannot verify cron list"
fi

# -------- openclaw config validate --------
section "openclaw config validate"
if command -v openclaw >/dev/null 2>&1; then
  if openclaw config validate >/dev/null 2>&1; then
    report_pass "config validates clean"
  else
    report_fail "openclaw config validate exited non-zero"
  fi
else
  report_fail "openclaw CLI not on PATH — cannot run config validate"
fi

# -------- Public tunnel curl --------
section "Public tunnel reachability"
if [ -n "${PUBLIC_HOSTNAME:-}" ] && [ -n "${ROUTE_ID:-}" ]; then
  URL="https://${PUBLIC_HOSTNAME}/hooks/${ROUTE_ID}"
  HTTP_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$URL" || echo "000")"
  case "$HTTP_CODE" in
    200|401|403|404|405)
      report_pass "tunnel live ($URL → HTTP $HTTP_CODE)"
      ;;
    000)
      report_fail "tunnel UNREACHABLE ($URL → connect/DNS failure)"
      ;;
    *)
      report_pass "tunnel responds ($URL → HTTP $HTTP_CODE)"
      ;;
  esac
else
  echo "  [SKIP] PUBLIC_HOSTNAME or ROUTE_ID not set; cannot probe tunnel"
fi

# -------- AGENTS.md marker blocks --------
section "AGENTS.md marker blocks"
AGENTS_MD="${AGENTS_MD:-${HOME}/.openclaw/AGENTS.md}"
[ -f "$AGENTS_MD" ] || AGENTS_MD="${MASTER_FILES_DIR:-}/AGENTS.md"
if [ -f "$AGENTS_MD" ]; then
  for marker in "INBOUND_WEBHOOK_CLASSIFICATION" "SKILL38_RUNTIME_ROUTING" "workflow-builder" "SKILL38_ZHC_TAG_PREFIX" "STEP_1_35_AGGRESSION_PRE_ROUTING" "STEP_1_42_INTERRUPTS_AND_FAQ" "STEP_2_0_GEO_QUALIFICATION" "STEP_2_5_CRM_FIELD_WRITE"; do
    if grep -q "$marker" "$AGENTS_MD"; then
      report_pass "AGENTS.md contains marker: $marker"
    else
      report_fail "AGENTS.md MISSING marker: $marker"
    fi
  done
else
  report_fail "AGENTS.md not found (tried \$AGENTS_MD and \$MASTER_FILES_DIR/AGENTS.md)"
fi

# -------- MEMORY.md marker block --------
section "MEMORY.md marker block"
MEMORY_MD="${MEMORY_MD:-${HOME}/.openclaw/MEMORY.md}"
[ -f "$MEMORY_MD" ] || MEMORY_MD="${MASTER_FILES_DIR:-}/MEMORY.md"
if [ -f "$MEMORY_MD" ]; then
  if grep -q "skill-38" "$MEMORY_MD" || grep -q "SKILL38_MEMORY_RULES" "$MEMORY_MD"; then
    report_pass "MEMORY.md contains skill-38 memory-rules block"
  else
    report_fail "MEMORY.md MISSING skill-38 memory-rules block"
  fi
else
  report_fail "MEMORY.md not found"
fi

# -------- 23-key GHL body linter (machine-enforced) --------
section "23-key GHL RAW BODY linter (qc-23-key-bodies.sh)"
QC_23="$SCRIPT_DIR/qc-23-key-bodies.sh"
[ -f "$QC_23" ] || QC_23="$SKILL38_ROOT/scripts/qc-23-key-bodies.sh"
if [ -f "$QC_23" ]; then
  if bash "$QC_23" >/dev/null 2>&1; then
    report_pass "all GHL RAW BODY examples are 23-key, flat, placeholder-free"
  else
    report_fail "qc-23-key-bodies.sh found 23-key-rule violation(s) — run it directly for detail"
  fi
else
  report_fail "qc-23-key-bodies.sh not found (looked in scripts/)"
fi

# -------- THE TRINITY registry completeness (machine-enforced) --------
section "THE TRINITY registry completeness (qc-trinity-registry.sh)"
QC_TRINITY="$SCRIPT_DIR/qc-trinity-registry.sh"
[ -f "$QC_TRINITY" ] || QC_TRINITY="$SKILL38_ROOT/scripts/qc-trinity-registry.sh"
if [ -f "$QC_TRINITY" ]; then
  TRINITY_RC=0
  bash "$QC_TRINITY" >/dev/null 2>&1 || TRINITY_RC=$?
  case "$TRINITY_RC" in
    0) report_pass "every registered workflow has its playbook + Build-with-AI prompt" ;;
    3) echo "  [SKIP] no conversation-workflows folder yet (nothing to check)" ;;
    *) report_fail "qc-trinity-registry.sh found incomplete trinity row(s) — run it directly for detail" ;;
  esac
else
  report_fail "qc-trinity-registry.sh not found (looked in scripts/)"
fi

# -------- Mandatory GHL send-directive gate (machine-enforced) --------
section "GHL send-directive gate (qc-send-directive.sh)"
QC_SEND="$SCRIPT_DIR/qc-send-directive.sh"
[ -f "$QC_SEND" ] || QC_SEND="$SKILL38_ROOT/scripts/qc-send-directive.sh"
if [ -f "$QC_SEND" ]; then
  if bash "$QC_SEND" >/dev/null 2>&1; then
    report_pass "every GHL inbound SERVER messageTemplate carries the mandatory send-directive (SEND/Conversations API/drafting-is-not-sending/do-not-end-turn)"
  else
    report_fail "qc-send-directive.sh found a GHL inbound server template missing the send-directive — run it directly for detail"
  fi
else
  report_fail "qc-send-directive.sh not found (looked in scripts/)"
fi

# -------- Conversation-memory read/append gate (machine-enforced) --------
section "Conversation-memory gate (qc-conversation-memory.sh)"
QC_MEM="$SCRIPT_DIR/qc-conversation-memory.sh"
[ -f "$QC_MEM" ] || QC_MEM="$SKILL38_ROOT/scripts/qc-conversation-memory.sh"
if [ -f "$QC_MEM" ]; then
  if bash "$QC_MEM" >/dev/null 2>&1; then
    report_pass "every GHL inbound SERVER messageTemplate carries the conversation-memory read-before + append-after steps (single-turn sessions remember via the per-contact log)"
  else
    report_fail "qc-conversation-memory.sh found a GHL inbound server template missing the read-before/append-after conversation-log steps — run it directly for detail"
  fi
else
  report_fail "qc-conversation-memory.sh not found (looked in scripts/)"
fi

# -------- Per-playbook human-facing doc gate (machine-enforced) --------
section "Per-playbook human-facing doc gate (qc-playbook-doc.sh)"
QC_PBDOC="$SCRIPT_DIR/qc-playbook-doc.sh"
[ -f "$QC_PBDOC" ] || QC_PBDOC="$SKILL38_ROOT/scripts/qc-playbook-doc.sh"
if [ -f "$QC_PBDOC" ]; then
  PBDOC_RC=0
  bash "$QC_PBDOC" >/dev/null 2>&1 || PBDOC_RC=$?
  case "$PBDOC_RC" in
    0) report_pass "every registered conversation playbook has a recorded human-facing doc (Notion → Google Docs → text) in the client's account" ;;
    2) echo "  [SKIP] no conversation playbooks registered yet (nothing to check) — gate fires once the first playbook is built" ;;
    3) echo "  [SKIP] no conversation-workflows folder yet (run 09-install-conversation-workflows.sh)" ;;
    *) report_fail "qc-playbook-doc.sh found a registered playbook with NO recorded human-facing doc (the Notion→Docs→text deliverable was skipped) — run it directly for detail" ;;
  esac
else
  report_fail "qc-playbook-doc.sh not found (looked in scripts/)"
fi

# -------- Client reference sheet copy-paste artifacts (machine-enforced) --------
section "Client reference sheet copy-paste artifacts (qc-reference-sheet.sh)"
QC_REF="$SCRIPT_DIR/qc-reference-sheet.sh"
[ -f "$QC_REF" ] || QC_REF="$SKILL38_ROOT/scripts/qc-reference-sheet.sh"
if [ -f "$QC_REF" ]; then
  if bash "$QC_REF" >/dev/null 2>&1; then
    report_pass "generated client reference sheet carries the bearer token, a copyable \`\`\`json GHL Raw Body, and the hook URL"
  else
    report_fail "qc-reference-sheet.sh: the generated reference sheet is MISSING the bearer token and/or the copyable \`\`\`json GHL Raw Body and/or the hook URL (this strands the client) — run it directly for detail"
  fi
else
  report_fail "qc-reference-sheet.sh not found (looked in scripts/)"
fi

# -------- Mandatory Telegram doc-delivery gate (machine-enforced) --------
section "Mandatory Telegram doc-delivery gate (qc-notify-client-doc.sh)"
QC_NOTIFY="$SCRIPT_DIR/qc-notify-client-doc.sh"
[ -f "$QC_NOTIFY" ] || QC_NOTIFY="$SKILL38_ROOT/scripts/qc-notify-client-doc.sh"
if [ -f "$QC_NOTIFY" ]; then
  if bash "$QC_NOTIFY" >/dev/null 2>&1; then
    report_pass "mandatory Telegram doc-delivery is wired (22-notify-client-doc.sh sends via gateway, discovers chat from transcripts, LOUD-fails on no chat)"
  else
    report_fail "qc-notify-client-doc.sh: the mandatory Telegram doc-delivery step is missing/unwired (every client gets their link via Telegram, no matter what) — run it directly for detail"
  fi
else
  report_fail "qc-notify-client-doc.sh not found (looked in scripts/)"
fi

# -------- Runtime assertion: the client doc link was actually delivered --------
# Step 6.5 records clientDocDelivered=true in the run-state file once the link is
# sent. At pre-handoff QC the install is NOT complete unless this is true. The
# state file lives next to the master files (or in the OpenClaw data dir).
section "Client doc delivered via Telegram (clientDocDelivered=true)"
RUN_STATE_CANDIDATES=()
[ -n "${RUN_STATE_FILE:-}" ] && RUN_STATE_CANDIDATES+=("$RUN_STATE_FILE")
[ -n "${MASTER_FILES_DIR:-}" ] && RUN_STATE_CANDIDATES+=("$MASTER_FILES_DIR/.skill38-run-state.env")
RUN_STATE_CANDIDATES+=("${HOME}/.openclaw/.skill38-run-state.env" "/data/.openclaw/.skill38-run-state.env")
STATE_FOUND=""
for sf in "${RUN_STATE_CANDIDATES[@]}"; do
  [ -f "$sf" ] && { STATE_FOUND="$sf"; break; }
done
if [ -n "$STATE_FOUND" ]; then
  if grep -q '^clientDocDelivered=true' "$STATE_FOUND"; then
    report_pass "clientDocDelivered=true (client was sent their setup-doc link via Telegram) — $STATE_FOUND"
  else
    report_fail "clientDocDelivered is NOT true in $STATE_FOUND — the client was never sent their doc link via Telegram (run scripts/22-notify-client-doc.sh; the install is not complete)"
  fi
else
  echo "  [SKIP] run-state file not found; cannot assert clientDocDelivered (run scripts/22-notify-client-doc.sh during the live install)"
fi

# -------- Backend-ready gate: the agent is ready to RECEIVE --------
# The install is not "complete" until the backend can RECEIVE inbound: a live
# hooks.mappings entry for HOOK_NAME with deliver:false and a working model, AND
# /healthz returns 200. Testing only happens after BOTH the doc AND this pass.
section "Backend ready to receive (hooks.mappings live + deliver:false + model + /healthz 200)"
OC_CONFIG=""
for cfg in "${OPENCLAW_CONFIG:-}" "${HOME}/.openclaw/openclaw.json" "/data/.openclaw/openclaw.json" "/root/.openclaw/openclaw.json"; do
  [ -n "$cfg" ] && [ -f "$cfg" ] && { OC_CONFIG="$cfg"; break; }
done
if [ -n "$OC_CONFIG" ] && command -v python3 >/dev/null 2>&1; then
  BACKEND_OUT="$(HOOK_NAME="${HOOK_NAME:-${ROUTE_ID:-}}" python3 - "$OC_CONFIG" <<'PY_BACKEND_EOF' 2>/dev/null || true
import json, os, sys
try:
    d = json.load(open(sys.argv[1]))
except Exception as e:
    print("ERR:cannot-parse-config"); sys.exit(0)
hooks = d.get("hooks") or {}
maps = hooks.get("mappings") or []
if isinstance(maps, dict):
    maps = list(maps.values())
want = (os.environ.get("HOOK_NAME") or "").strip()
chosen = None
for m in maps:
    if not isinstance(m, dict):
        continue
    mid = str(m.get("id") or m.get("match") or "")
    if want and mid == want:
        chosen = m; break
if chosen is None and maps:
    # No HOOK_NAME provided (or no exact match): assert at least one agent mapping is live.
    for m in maps:
        if isinstance(m, dict) and (m.get("action") == "agent" or m.get("agent_id")):
            chosen = m; break
if chosen is None:
    print("ERR:no-live-hooks-mapping"); sys.exit(0)
deliver = chosen.get("deliver", None)
model = (chosen.get("model") or "").strip()
problems = []
if deliver is not False:
    problems.append("deliver-not-false")
if not model:
    problems.append("no-model")
if problems:
    print("ERR:" + ",".join(problems)); sys.exit(0)
print("OK")
PY_BACKEND_EOF
)"
  case "$BACKEND_OUT" in
    OK) report_pass "hooks.mappings is live with deliver:false and a model set ($OC_CONFIG)" ;;
    ERR:no-live-hooks-mapping) report_fail "no live hooks.mappings agent entry — the backend cannot RECEIVE inbound (run scripts/15-configure-hooks-mappings.sh)" ;;
    ERR:*) report_fail "hooks.mappings is not receive-ready: ${BACKEND_OUT#ERR:} (need deliver:false + a working model)" ;;
    *) report_fail "could not evaluate hooks.mappings readiness from $OC_CONFIG" ;;
  esac
else
  echo "  [SKIP] openclaw.json not found (or python3 missing); cannot assert hooks.mappings readiness"
fi

# /healthz 200 — the gateway is up and ready to receive.
if [ -n "${PUBLIC_HOSTNAME:-}" ]; then
  HZ_URL="https://${PUBLIC_HOSTNAME}/healthz"
  HZ_CODE="$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$HZ_URL" 2>/dev/null || echo 000)"
  if [ "$HZ_CODE" = "200" ]; then
    report_pass "/healthz returns 200 ($HZ_URL) — gateway is up and ready to receive"
  else
    report_fail "/healthz did not return 200 ($HZ_URL → HTTP $HZ_CODE) — gateway not confirmed receiving; do NOT test inbound yet"
  fi
elif command -v openclaw >/dev/null 2>&1; then
  LOCAL_HZ="$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:${OPENCLAW_PORT:-3000}/healthz" 2>/dev/null || echo 000)"
  if [ "$LOCAL_HZ" = "200" ]; then
    report_pass "/healthz returns 200 (localhost) — gateway is up and ready to receive"
  else
    echo "  [SKIP] PUBLIC_HOSTNAME unset and localhost /healthz not 200 (HTTP $LOCAL_HZ); cannot assert gateway readiness here"
  fi
else
  echo "  [SKIP] PUBLIC_HOSTNAME unset and openclaw CLI not on PATH; cannot probe /healthz"
fi

# -------- Backend ready to RECEIVE (live gate; SKIPs with no install) --------
# hooks.mappings live + deliver:false + a working model + healthz 200. On a box
# with no install this exits 3 (SKIP).
section "Backend ready to RECEIVE (qc-backend-ready.sh)"
QC_BACKEND="$SCRIPT_DIR/qc-backend-ready.sh"
[ -f "$QC_BACKEND" ] || QC_BACKEND="$SKILL38_ROOT/scripts/qc-backend-ready.sh"
if [ -f "$QC_BACKEND" ]; then
  BACKEND_RC=0
  bash "$QC_BACKEND" >/dev/null 2>&1 || BACKEND_RC=$?
  case "$BACKEND_RC" in
    0) report_pass "backend ready to receive: hooks.mappings live + deliver:false + a working model + healthz 200 (testing may proceed once the client doc gate also passes)" ;;
    3) echo "  [SKIP] no openclaw.json on this box — cannot verify backend readiness here" ;;
    *) report_fail "qc-backend-ready.sh: backend NOT ready to receive (hooks.mappings / deliver:false / model / healthz) — do NOT test, do NOT hand off; run it directly for detail" ;;
  esac
else
  report_fail "qc-backend-ready.sh not found (looked in scripts/)"
fi

# -------- install-script config-invalidating pattern gate (machine-enforced) --------
section "Config schema-safety — no config-invalidating install scripts (qc-config-schema-safety.sh)"
QC_CFG="$SCRIPT_DIR/qc-config-schema-safety.sh"
[ -f "$QC_CFG" ] || QC_CFG="$SKILL38_ROOT/scripts/qc-config-schema-safety.sh"
if [ -f "$QC_CFG" ]; then
  if bash "$QC_CFG" >/dev/null 2>&1; then
    report_pass "no install script writes a config-invalidating shape (no agents.defaults.async/.batch, no cron.jobs JSON, no jq-1.7-invalid '//= ;', no pointer-sourcing, no hardcoded legacy skill path)"
  else
    report_fail "qc-config-schema-safety.sh found an install script that would invalidate the config or break a fresh install — run it directly for detail"
  fi
else
  report_fail "qc-config-schema-safety.sh not found (looked in scripts/)"
fi

# -------- F52 JSONL data contract (machine-enforced) --------
section "F52 JSONL data contract (qc-feature-logs.sh)"
QC_LOGS="$SCRIPT_DIR/qc-feature-logs.sh"
[ -f "$QC_LOGS" ] || QC_LOGS="$SKILL38_ROOT/scripts/qc-feature-logs.sh"
if [ -f "$QC_LOGS" ]; then
  if bash "$QC_LOGS" >/dev/null 2>&1; then
    report_pass "all five Round-3 feature logs are JSONL (timestamp+event_type), documented in protocol + INSTRUCTIONS.md, and seeded by the installer"
  else
    report_fail "qc-feature-logs.sh found an F52 data-contract violation — run it directly for detail"
  fi
else
  report_fail "qc-feature-logs.sh not found (looked in scripts/)"
fi

# -------- F45 + F47 behavioral substance (machine-enforced) --------
section "F45 + F47 substance (qc-f45-f47-substance.sh)"
QC_F45F47="$SCRIPT_DIR/qc-f45-f47-substance.sh"
[ -f "$QC_F45F47" ] || QC_F45F47="$SKILL38_ROOT/scripts/qc-f45-f47-substance.sh"
if [ -f "$QC_F45F47" ]; then
  if bash "$QC_F45F47" >/dev/null 2>&1; then
    report_pass "F45 (geo) + F47 (smart FAQ) carry every roadmap substance point: F47 = parallel layer alongside the workflow, a SENTENCE not a sub-flow, the 'By the way…Coming back to' handoff, sales-vs-ops faq-scope, faqs.md match, the F44-vs-F47 difference, ZHC-faq-detoured hand-off, ZHC-faq-answered, faq-detour-log.jsonl; F45 = default-OFF + per-product toggle, pixel/IP->area-code->form->ask priority, ALWAYS-confirm + exact question + all 5 branches (here/elsewhere/vacation/moving/no-engagement=do-not-disqualify), 4 out-of-area modes, service-areas.md (radius/zips/states/counties), the 3 ZHC tags, geo-qualification-log.jsonl + confirmed_with_customer invariant"
  else
    report_fail "qc-f45-f47-substance.sh found a missing F45/F47 substance point — run it directly for detail"
  fi
else
  report_fail "qc-f45-f47-substance.sh not found (looked in scripts/)"
fi

# -------- GHL TOOLS.md quick-reference gate (machine-enforced) --------
section "GHL TOOLS.md quick-reference gate (qc-tools-md-ghl-ref.sh)"
QC_TOOLS="$SCRIPT_DIR/qc-tools-md-ghl-ref.sh"
[ -f "$QC_TOOLS" ] || QC_TOOLS="$SKILL38_ROOT/scripts/qc-tools-md-ghl-ref.sh"
if [ -f "$QC_TOOLS" ]; then
  if bash "$QC_TOOLS" >/dev/null 2>&1; then
    report_pass "GHL API quick-reference (injected into client TOOLS.md by 24-update-tools-md.sh) carries every messaging channel type + calendar/appointment/invoice op + required scopes, is concise, and is free of personal/client data"
  else
    report_fail "qc-tools-md-ghl-ref.sh found a missing operation/scope, a bloated block, or personal/client data in the GHL TOOLS.md quick-reference — run it directly for detail"
  fi
else
  report_fail "qc-tools-md-ghl-ref.sh not found (looked in scripts/)"
fi

# Also assert the block is actually present in the installed client TOOLS.md.
section "GHL quick-reference present in client TOOLS.md"
case "$OS" in
  mac)   WS_DEFAULT_TOOLS="$HOME/clawd/TOOLS.md" ;;
  linux) WS_DEFAULT_TOOLS="/data/clawd/TOOLS.md" ;;
  *)     WS_DEFAULT_TOOLS="$HOME/clawd/TOOLS.md" ;;
esac
TOOLS_MD_CHECK="${TOOLS_MD:-${OPENCLAW_WORKSPACE:+$OPENCLAW_WORKSPACE/TOOLS.md}}"
[ -n "$TOOLS_MD_CHECK" ] || TOOLS_MD_CHECK="$WS_DEFAULT_TOOLS"
if [ -f "$TOOLS_MD_CHECK" ]; then
  if grep -qF "SKILL38: GHL_API_QUICK_REFERENCE" "$TOOLS_MD_CHECK"; then
    report_pass "client TOOLS.md contains the GHL API quick-reference block: $TOOLS_MD_CHECK"
  else
    report_fail "client TOOLS.md is MISSING the GHL API quick-reference block ($TOOLS_MD_CHECK) — run scripts/24-update-tools-md.sh"
  fi
else
  echo "  [SKIP] client TOOLS.md not found at $TOOLS_MD_CHECK; cannot assert the GHL quick-reference block (run scripts/24-update-tools-md.sh during the live install)"
fi

# -------- conversational-logs dir presence + writability --------
section "conversational-logs dir (per-contact memory store)"
if [ -n "${MASTER_FILES_DIR:-}" ]; then
  LOGS_DIR="$MASTER_FILES_DIR/conversational-logs"
  if [ -d "$LOGS_DIR" ]; then
    if [ -w "$LOGS_DIR" ]; then
      report_pass "conversational-logs dir exists and is writable by this user: $LOGS_DIR"
    else
      report_fail "conversational-logs dir exists but is NOT writable (agent cannot append = silent memory loss): $LOGS_DIR — chown to the gateway runtime user"
    fi
  else
    report_fail "conversational-logs dir MISSING: $LOGS_DIR — run 09-install-conversation-workflows.sh"
  fi
else
  echo "  [SKIP] MASTER_FILES_DIR not resolved; cannot check conversational-logs dir"
fi


# -------- Backend self-test gate (machine-enforced, REQ 5) --------
section "Backend self-test standard (qc-self-test.sh)"
QC_SELFTEST="$SCRIPT_DIR/qc-self-test.sh"
[ -f "$QC_SELFTEST" ] || QC_SELFTEST="$SKILL38_ROOT/scripts/qc-self-test.sh"
if [ -f "$QC_SELFTEST" ]; then
  if bash "$QC_SELFTEST" >/dev/null 2>&1; then
    report_pass "backend self-test is wired (24-self-test-hook.sh POSTs a synthetic flat-23-key inbound, verifies 200/{ok:true} + model + log read + GHL send, cleans up, and is a blocking readiness gate)"
  else
    report_fail "qc-self-test.sh: the backend self-test is missing/unwired (the agent must self-test by ground truth BEFORE the client) — run it directly for detail"
  fi
else
  report_fail "qc-self-test.sh not found (looked in scripts/)"
fi

# -------- No-personal-data gate (machine-enforced, REQ 7) --------
section "UNIVERSAL skill — no personal/client data (qc-no-personal-data.sh)"
QC_NOPII="$SCRIPT_DIR/qc-no-personal-data.sh"
[ -f "$QC_NOPII" ] || QC_NOPII="$SKILL38_ROOT/scripts/qc-no-personal-data.sh"
if [ -f "$QC_NOPII" ]; then
  if bash "$QC_NOPII" --no-gen >/dev/null 2>&1; then
    report_pass "no real personal/client identifiers in the skill tree (UNIVERSAL)"
  else
    report_fail "qc-no-personal-data.sh found a real personal/client identifier in the skill — run it directly for detail"
  fi
else
  report_fail "qc-no-personal-data.sh not found (looked in scripts/)"
fi

# -------- ZHC programmatic-tag-prefix gate (machine-enforced, Round-3 Queue-A) --------
section "ZHC tag-prefix rule (qc-zhc-tag-prefix.sh)"
QC_ZHC="$SCRIPT_DIR/qc-zhc-tag-prefix.sh"
[ -f "$QC_ZHC" ] || QC_ZHC="$SKILL38_ROOT/scripts/qc-zhc-tag-prefix.sh"
if [ -f "$QC_ZHC" ]; then
  if bash "$QC_ZHC" >/dev/null 2>&1; then
    report_pass "every programmatically created tag example uses the ZHC- prefix (MEMORY Rule 20 + AGENTS block + protocol + Round-3 Queue-A tags)"
  else
    report_fail "qc-zhc-tag-prefix.sh found a programmatic-tag example missing the ZHC- prefix (or a missing rule doc) — run it directly for detail"
  fi
else
  report_fail "qc-zhc-tag-prefix.sh not found (looked in scripts/)"
fi

# -------- ZHC Pixel (F49) invariant gate (machine-enforced) --------
section "ZHC Pixel rule (qc-zhc-pixel.sh)"
QC_PIXEL="$SCRIPT_DIR/qc-zhc-pixel.sh"
[ -f "$QC_PIXEL" ] || QC_PIXEL="$SKILL38_ROOT/scripts/qc-zhc-pixel.sh"
if [ -f "$QC_PIXEL" ]; then
  if bash "$QC_PIXEL" >/dev/null 2>&1; then
    report_pass "F49 ZHC Pixel invariants hold (hook pixel-visitor-signal registered, Pixel Concierge protocol + AGENTS Step 1.45, ZHC-/ZHC_ prefixes, GDPR/CCPA/DNT/deletion privacy controls, scope precheck + gated deploy, no personal data)"
  else
    report_fail "qc-zhc-pixel.sh found an F49 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-zhc-pixel.sh not found (looked in scripts/)"
fi

# -------- Runtime assertion: the backend self-test PASSED (selfTestPassed=true) --------
# REQ 5(e): the install is NOT complete until the agent's own backend self-test
# passed by ground truth. Same run-state file as clientDocDelivered.
section "Backend self-test passed (selfTestPassed=true)"
ST_STATE_FOUND=""
for sf in "${RUN_STATE_CANDIDATES[@]:-}"; do
  [ -n "$sf" ] && [ -f "$sf" ] && { ST_STATE_FOUND="$sf"; break; }
done
[ -n "$ST_STATE_FOUND" ] || { for sf in "${HOME}/.openclaw/.skill38-run-state.env" "/data/.openclaw/.skill38-run-state.env" "${MASTER_FILES_DIR:-}/.skill38-run-state.env"; do [ -f "$sf" ] && { ST_STATE_FOUND="$sf"; break; }; done; }
if [ -n "$ST_STATE_FOUND" ]; then
  if grep -q '^selfTestPassed=true' "$ST_STATE_FOUND"; then
    report_pass "selfTestPassed=true (the agent self-tested the backend by ground truth before any client test) — $ST_STATE_FOUND"
  else
    report_fail "selfTestPassed is NOT true in $ST_STATE_FOUND — run scripts/24-self-test-hook.sh until it passes; do NOT mark complete or tell the client to test"
  fi
else
  echo "  [SKIP] run-state file not found; cannot assert selfTestPassed (run scripts/24-self-test-hook.sh during the live install)"
fi

# -------- Communication Playbook Standard gate (machine-enforced) --------
section "Communication Playbook Standard (qc-communications-playbook-standard.sh)"
QC_COMMS_STD="$SCRIPT_DIR/qc-communications-playbook-standard.sh"
[ -f "$QC_COMMS_STD" ] || QC_COMMS_STD="$SKILL38_ROOT/scripts/qc-communications-playbook-standard.sh"
if [ -f "$QC_COMMS_STD" ]; then
  if bash "$QC_COMMS_STD" >/dev/null 2>&1; then
    report_pass "communications-playbook-standard.md carries the 'EVERY COMMUNICATION PLAYBOOK MUST INCLUDE ALL OF THE FOLLOWING' mandatory checklist + every required item (a)-(i)"
  else
    report_fail "qc-communications-playbook-standard.sh found a missing mandatory item in the communication playbook standard — run it directly for detail"
  fi
else
  report_fail "qc-communications-playbook-standard.sh not found (looked in scripts/)"
fi

# -------- GHL Raw Body JSON Standard gate (machine-enforced) --------
section "GHL Raw Body JSON Standard (qc-ghl-raw-body-standard.sh)"
QC_BODY_STD="$SCRIPT_DIR/qc-ghl-raw-body-standard.sh"
[ -f "$QC_BODY_STD" ] || QC_BODY_STD="$SKILL38_ROOT/scripts/qc-ghl-raw-body-standard.sh"
if [ -f "$QC_BODY_STD" ]; then
  if bash "$QC_BODY_STD" >/dev/null 2>&1; then
    report_pass "ghl-raw-body-json-standard.md codifies the FLAT 23-key body (23 is the minimum AND the standard) + the canonical body is lint-clean (composes qc-23-key-bodies.sh)"
  else
    report_fail "qc-ghl-raw-body-standard.sh found a missing rule or a body violating the 23-key/flat rule — run it directly for detail"
  fi
else
  report_fail "qc-ghl-raw-body-standard.sh not found (looked in scripts/)"
fi

# -------- Notion Client-Doc Standard gate (machine-enforced) --------
section "Notion Client-Doc Standard (qc-notion-doc-standard.sh)"
QC_NOTION_STD="$SCRIPT_DIR/qc-notion-doc-standard.sh"
[ -f "$QC_NOTION_STD" ] || QC_NOTION_STD="$SKILL38_ROOT/scripts/qc-notion-doc-standard.sh"
if [ -f "$QC_NOTION_STD" ]; then
  if bash "$QC_NOTION_STD" >/dev/null 2>&1; then
    report_pass "notion-client-doc-standard.md codifies the ordered client-doc structure (1-12) + the generator matches it (composes qc-reference-sheet.sh --require-manual-fill)"
  else
    report_fail "qc-notion-doc-standard.sh found a missing ordered mandatory item or a generator mismatch — run it directly for detail"
  fi
else
  report_fail "qc-notion-doc-standard.sh not found (looked in scripts/)"
fi

# -------- Multi-Tenant Agent Isolation (F21) invariant gate (machine-enforced) --------
section "Multi-tenant isolation rule (qc-multi-tenant.sh)"
QC_MT="$SCRIPT_DIR/qc-multi-tenant.sh"
[ -f "$QC_MT" ] || QC_MT="$SKILL38_ROOT/scripts/qc-multi-tenant.sh"
if [ -f "$QC_MT" ]; then
  if bash "$QC_MT" >/dev/null 2>&1; then
    report_pass "F21 multi-tenant isolation invariants hold (protocol + AGENTS Step 0.8 + MEMORY Rule 26, per-tenant scoping/namespacing + tenant.md config + hooks.mappings tenant_id convention, PII-free multi-tenant-events.jsonl seeded, per-tenant root scaffolded, toggle default OFF)"
  else
    report_fail "qc-multi-tenant.sh found an F21 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-multi-tenant.sh not found (looked in scripts/)"
fi

# -------- Customer Segmentation Awareness (F17) invariant gate (machine-enforced) --------
section "Customer segmentation rule (qc-segmentation.sh)"
QC_SEG="$SCRIPT_DIR/qc-segmentation.sh"
[ -f "$QC_SEG" ] || QC_SEG="$SKILL38_ROOT/scripts/qc-segmentation.sh"
if [ -f "$QC_SEG" ]; then
  if bash "$QC_SEG" >/dev/null 2>&1; then
    report_pass "F17 customer segmentation invariants hold (protocol + AGENTS Step 1.85 + MEMORY Rule 27, five segments + per-client tag_map/segment-map.md mapping + multi-tag precedence + the four behavior overrides + before-reply-draft placement + ZHC-segment- tag prefix + operator-only guard, PII-free segmentation-events.jsonl seeded with the segment-map.md companion, toggle default OFF)"
  else
    report_fail "qc-segmentation.sh found an F17 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-segmentation.sh not found (looked in scripts/)"
fi

# -------- Proactive Outreach Campaigns (F15) invariant gate (machine-enforced) --------
section "Proactive outreach campaigns rule (qc-proactive-outreach.sh)"
QC_OUTREACH="$SCRIPT_DIR/qc-proactive-outreach.sh"
[ -f "$QC_OUTREACH" ] || QC_OUTREACH="$SKILL38_ROOT/scripts/qc-proactive-outreach.sh"
if [ -f "$QC_OUTREACH" ]; then
  if bash "$QC_OUTREACH" >/dev/null 2>&1; then
    report_pass "F15 proactive outreach invariants hold (protocol + MEMORY Rule 28, NO inbound AGENTS step — cron/event-driven, campaign-definition format cron|event trigger + GHL-tag audience + Communication-Playbook-rendered message + frequency cap + opt-out + ZHC-outreach- tag, STRICT quiet-hours respect Step 9.8, reactive-vs-proactive tracked separately via direction:proactive, operator-only/never-customer-invoked SEND, F29 migrates onto this infra, PII-free outreach-events.jsonl seeded with the outreach-campaigns/ dir + example campaign, toggle default OFF)"
  else
    report_fail "qc-proactive-outreach.sh found an F15 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-proactive-outreach.sh not found (looked in scripts/)"
fi

# -------- A/B Testing of Reply Variants (F16) invariant gate (machine-enforced) --------
section "A/B testing of reply variants rule (qc-ab-testing.sh)"
QC_ABTEST="$SCRIPT_DIR/qc-ab-testing.sh"
[ -f "$QC_ABTEST" ] || QC_ABTEST="$SKILL38_ROOT/scripts/qc-ab-testing.sh"
if [ -f "$QC_ABTEST" ]; then
  if bash "$QC_ABTEST" >/dev/null 2>&1; then
    report_pass "F16 A/B testing invariants hold (protocol + AGENTS Step 1.87 + MEMORY Rule 29, two variants a/b per channel + experiments/ab-experiments mapping + deterministic-by-contact sticky assignment + at-draft-time placement + the three outcome metrics booked/converted/sentiment + the two-proportion z-test with default N=30/arm + auto-promote-with-operator-notify + ZHC-abtest-variant- tags + operator-only/A-B-injection guard, PII-free ab-test-events.jsonl seeded with the ab-experiments/ scaffold, toggle default OFF)"
  else
    report_fail "qc-ab-testing.sh found an F16 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-ab-testing.sh not found (looked in scripts/)"
fi

section "Voice / phone integration rule (qc-voice-phone.sh)"
QC_VOICE="$SCRIPT_DIR/qc-voice-phone.sh"
[ -f "$QC_VOICE" ] || QC_VOICE="$SKILL38_ROOT/scripts/qc-voice-phone.sh"
if [ -f "$QC_VOICE" ]; then
  if bash "$QC_VOICE" >/dev/null 2>&1; then
    report_pass "F14 voice/phone invariants hold (protocol + MEMORY Rule 30 + setup wizard, STT Whisper-large-v3 via OpenRouter/Groq/Ollama -> brain -> TTS ElevenLabs Flash 2.5/OSS over Twilio Media Streams + /hooks/voice-call-event scaffolding + greeting->listen->respond->handoff/booking state machine + < 800ms first-audio target + degrade-to-text fallback + operator-only outbound-dial guard + ZHC-voice-* tags + the HONEST live-telephony gap, PII-free voice-call-events.jsonl seeded, toggle default OFF)"
  else
    report_fail "qc-voice-phone.sh found an F14 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-voice-phone.sh not found (looked in scripts/)"
fi

section "Webhook chaining rule (qc-webhook-chaining.sh)"
QC_WEBHOOK="$SCRIPT_DIR/qc-webhook-chaining.sh"
[ -f "$QC_WEBHOOK" ] || QC_WEBHOOK="$SKILL38_ROOT/scripts/qc-webhook-chaining.sh"
if [ -f "$QC_WEBHOOK" ]; then
  if bash "$QC_WEBHOOK" >/dev/null 2>&1; then
    report_pass "F18 webhook-chaining invariants hold (protocol + AGENTS Step 2.9 STEP_2_9_WEBHOOK_CHAINING + MEMORY Rule 31, the operator-defined webhook-chains/ registry + the four allow-listed trigger events booking_completed/invoice_sent/escalation_raised/transcript_exported + the https-only target + the PII-free payload (opaque contact_ref) + the exponential-backoff/max-attempts retry policy + the async/never-block-the-reply invariant + the operator-only/never-customer-invoked outbound SSRF/exfiltration guard + the ZHC-webhook-chain-fired/-failed tags, PII-free webhook-chain-events.jsonl seeded with the registry + example chain, toggle default OFF)"
  else
    report_fail "qc-webhook-chaining.sh found an F18 invariant violation — run it directly for detail"
  fi
else
  report_fail "qc-webhook-chaining.sh not found (looked in scripts/)"
fi

section "Model fallback chain + model tier (qc-model-fallback.sh)"
QC_MODELFB="$SCRIPT_DIR/qc-model-fallback.sh"
[ -f "$QC_MODELFB" ] || QC_MODELFB="$SKILL38_ROOT/scripts/qc-model-fallback.sh"
if [ -f "$QC_MODELFB" ]; then
  if bash "$QC_MODELFB" >/dev/null 2>&1; then
    report_pass "U-8 + U-10 wiring holds (references/model-fallback-chain.md documents skill38.model_chain.primary/.fallbacks + the three model-tier enum values, scripts/32-verify-model-failover-support.sh present, MEMORY Rule 38, the Saturday freshness cron reviews the whole chain, model-failover-events.jsonl seeded, every playbook model-tier is realtime-light/realtime-standard/reasoning-max)"
  else
    report_fail "qc-model-fallback.sh found a model-fallback/model-tier violation - run it directly for detail"
  fi
else
  report_fail "qc-model-fallback.sh not found (looked in scripts/)"
fi

section "Workflow visual, Part 4 truth diagram (qc-workflow-visual.sh)"
QC_VISUAL="$SCRIPT_DIR/qc-workflow-visual.sh"
[ -f "$QC_VISUAL" ] || QC_VISUAL="$SKILL38_ROOT/scripts/qc-workflow-visual.sh"
if [ -f "$QC_VISUAL" ]; then
  if bash "$QC_VISUAL" >/dev/null 2>&1; then
    report_pass "U-11 wiring holds (protocols/workflow-visual-protocol.md + scripts/31-generate-workflow-visual.sh + MEMORY Rule 39 + kie-image-events.jsonl seeded; every registered playbook has a current, non-stale truth diagram, a missing hero.png only WARNs)"
  else
    report_fail "qc-workflow-visual.sh found a missing/stale truth diagram or missing visual wiring - run it directly for detail"
  fi
else
  report_fail "qc-workflow-visual.sh not found (looked in scripts/)"
fi

section "Canonical playbook engine unit tests (qc-playbook-engine.sh)"
QC_ENGINE="$SCRIPT_DIR/qc-playbook-engine.sh"
[ -f "$QC_ENGINE" ] || QC_ENGINE="$SKILL38_ROOT/scripts/qc-playbook-engine.sh"
if [ -f "$QC_ENGINE" ]; then
  if bash "$QC_ENGINE" >/dev/null 2>&1; then
    report_pass "U-16 holds (tools/playbook_engine.py + tools/tests/test_playbook_engine.py present; python3 -m unittest green; the canonical parser every gate shells out to is sound)"
  else
    report_fail "qc-playbook-engine.sh: the playbook_engine.py unit tests failed or the engine/tests are missing - run it directly for detail"
  fi
else
  report_fail "qc-playbook-engine.sh not found (looked in scripts/)"
fi

section "Per-phase tool gating (qc-tool-gating.sh)"
QC_TOOLGATE="$SCRIPT_DIR/qc-tool-gating.sh"
[ -f "$QC_TOOLGATE" ] || QC_TOOLGATE="$SKILL38_ROOT/scripts/qc-tool-gating.sh"
if [ -f "$QC_TOOLGATE" ]; then
  if bash "$QC_TOOLGATE" >/dev/null 2>&1; then
    report_pass "U-1 wiring holds (protocols/tool-gating-protocol.md + STEP_1_88_TOOL_GATING marker + MEMORY Rule 32 + tool-gate-events.jsonl seeded; every checked phase is in-vocabulary and escalate_to_human is never gated off)"
  else
    report_fail "qc-tool-gating.sh found a tool-gating violation or missing wiring - run it directly for detail"
  fi
else
  report_fail "qc-tool-gating.sh not found (looked in scripts/)"
fi

section "Runtime tool-gating prover (qc-runtime-tool-gating.sh)"
QC_RTGATE="$SCRIPT_DIR/qc-runtime-tool-gating.sh"
[ -f "$QC_RTGATE" ] || QC_RTGATE="$SKILL38_ROOT/scripts/qc-runtime-tool-gating.sh"
if [ -f "$QC_RTGATE" ]; then
  if bash "$QC_RTGATE" >/dev/null 2>&1; then
    report_pass "U-1 RUNTIME proof wired (scripts/33-runtime-tool-gating-prover.sh drives a synthetic conversation whose active phase grants check_availability but NOT book_appointment, tempts the agent to book, and asserts by ground truth that it REFUSED the ungranted tool; Layer-A boundary green; wired into the box-level self-test cron)"
  else
    report_fail "qc-runtime-tool-gating.sh found the runtime tool-gating prover missing/unwired or its Layer-A boundary broken - run it directly for detail"
  fi
else
  report_fail "qc-runtime-tool-gating.sh not found (looked in scripts/)"
fi

section "Tag-driven workflow exits (qc-workflow-exits.sh)"
QC_EXITS="$SCRIPT_DIR/qc-workflow-exits.sh"
[ -f "$QC_EXITS" ] || QC_EXITS="$SKILL38_ROOT/scripts/qc-workflow-exits.sh"
if [ -f "$QC_EXITS" ]; then
  if bash "$QC_EXITS" >/dev/null 2>&1; then
    report_pass "U-2 wiring holds (protocols/workflow-exit-rules-protocol.md + STEP_1_30_EXIT_RULES marker + MEMORY Rule 33 + workflow-exit-events.jsonl seeded; every exit rule has a valid action and a resolvable route target)"
  else
    report_fail "qc-workflow-exits.sh found an exit-rule violation or missing wiring - run it directly for detail"
  fi
else
  report_fail "qc-workflow-exits.sh not found (looked in scripts/)"
fi

section "Machine-readable playbook declares (qc-playbook-declares.sh)"
QC_DECLARES="$SCRIPT_DIR/qc-playbook-declares.sh"
[ -f "$QC_DECLARES" ] || QC_DECLARES="$SKILL38_ROOT/scripts/qc-playbook-declares.sh"
if [ -f "$QC_DECLARES" ]; then
  if bash "$QC_DECLARES" >/dev/null 2>&1; then
    report_pass "U-9 + U-12 wiring holds (Section E declares block documented; every declared tools-used/exits-used/fields-used/calendars reference resolves; legacy playbooks WARN, dangling references FAIL)"
  else
    report_fail "qc-playbook-declares.sh found a declares violation or missing wiring - run it directly for detail"
  fi
else
  report_fail "qc-playbook-declares.sh not found (looked in scripts/)"
fi

section "Opportunity/pipeline stage sync (qc-opportunity-sync.sh)"
QC_OPPSYNC="$SCRIPT_DIR/qc-opportunity-sync.sh"
[ -f "$QC_OPPSYNC" ] || QC_OPPSYNC="$SKILL38_ROOT/scripts/qc-opportunity-sync.sh"
if [ -f "$QC_OPPSYNC" ]; then
  if bash "$QC_OPPSYNC" >/dev/null 2>&1; then
    report_pass "U-13 wiring holds (protocols/opportunity-sync-protocol.md + MEMORY Rule 41 + opportunity-sync-events.jsonl seeded; every stage-map stage name resolves to its declared pipeline)"
  else
    report_fail "qc-opportunity-sync.sh found an opportunity-sync violation or missing wiring - run it directly for detail"
  fi
else
  report_fail "qc-opportunity-sync.sh not found (looked in scripts/)"
fi

section "Client test mode (qc-client-test-mode.sh)"
QC_TESTMODE="$SCRIPT_DIR/qc-client-test-mode.sh"
[ -f "$QC_TESTMODE" ] || QC_TESTMODE="$SKILL38_ROOT/scripts/qc-client-test-mode.sh"
if [ -f "$QC_TESTMODE" ]; then
  if bash "$QC_TESTMODE" >/dev/null 2>&1; then
    report_pass "U-6 wiring holds (protocols/client-test-mode-protocol.md + CLIENT_TEST_MODE + STEP_0_4_TEST_MODE_REREAD markers + MEMORY Rule 37 + three-layer enforcement + TEST MODE banner + test-sessions isolation/60-min expiry + the full allow-list suppression list)"
  else
    report_fail "qc-client-test-mode.sh found a Client Test Mode violation or missing wiring - run it directly for detail"
  fi
else
  report_fail "qc-client-test-mode.sh not found (looked in scripts/)"
fi

# -------- Final summary --------
section "QC SUMMARY"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "  RESULT: PASS — all mechanical QC items green. Proceed to human-judgment items in protocols/pre-handoff-qc-protocol.md."
  # Command Center Kanban: mechanical QC passed -> move the install task to
  # `review` so the INDEPENDENT CC auto-scorer can promote it (the builder never
  # self-grades to done). FAIL-SOFT: cc-task.sh always exits 0 and `|| true`
  # guarantees it cannot change this script's exit code. No-ops when CC is absent.
  bash "$SCRIPT_DIR/cc-task.sh" review || true
  exit 0
else
  echo ""
  echo "  RESULT: FAIL — $FAIL item(s) need attention. Do NOT seal the Run Manifest."
  # Command Center Kanban: mechanical QC FAILED -> move the install task to `blocked`
  # so the failure is VISIBLE on the board (never left stranded at in_progress, never
  # wrongly marked done). FAIL-SOFT: cc-task.sh always exits 0 and `|| true` keeps it
  # from changing this script's exit code. No-ops when CC is absent. (FIX-XC-06)
  bash "$SCRIPT_DIR/cc-task.sh" fail "mechanical QC: $FAIL item(s) failed" || true
  exit 1
fi

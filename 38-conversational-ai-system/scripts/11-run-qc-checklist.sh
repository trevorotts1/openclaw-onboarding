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
SKILL38_ROOT="${SKILL38_ROOT:-${HOME}/clawd/skills/38-openclaw-cloudflare-tunnel}"
if [ ! -d "$SKILL38_ROOT" ]; then
  # try a few common alternates
  for cand in \
    "${HOME}/.openclaw/skills/38-openclaw-cloudflare-tunnel" \
    "${HOME}/clawd/skills/38" \
    "${HOME}/.claude/skills/38-openclaw-cloudflare-tunnel"; do
    [ -d "$cand" ] && SKILL38_ROOT="$cand" && break
  done
fi

section "Skill 38 root"
if [ -d "$SKILL38_ROOT" ]; then
  report_pass "skill root: $SKILL38_ROOT"
else
  report_fail "skill root not found (SKILL38_ROOT=$SKILL38_ROOT)"
fi

# -------- File existence: protocols / templates / scripts / references --------
section "File existence — protocols/"
PROTOCOL_FILES=(
  "protocols/pre-handoff-qc-protocol.md"
  "protocols/qc-protocol.md"
  "protocols/handoff-protocol.md"
)
for f in "${PROTOCOL_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done

section "File existence — templates/ (journey + channel)"
TEMPLATE_FILES=(
  "templates/channel-playbook-template.md"
  "templates/journey-template.md"
)
for f in "${TEMPLATE_FILES[@]}"; do
  if [ -f "$SKILL38_ROOT/$f" ]; then report_pass "$f"; else report_fail "MISSING: $f"; fi
done

section "File existence — scripts/ (install + QC)"
SCRIPT_FILES=(
  "scripts/11-run-qc-checklist.sh"
  "scripts/12-scaffold-channel-playbooks.sh"
  "scripts/qc-23-key-bodies.sh"
  "scripts/qc-trinity-registry.sh"
  "scripts/qc-send-directive.sh"
  "scripts/qc-conversation-memory.sh"
  "scripts/qc-playbook-doc.sh"
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
section "openclaw cron list — 5 expected crons"
EXPECTED_CRONS=(
  "weekly-tune-up"
  "proactive-suggestions-scan"
  "model-version-freshness"
  "monthly-comprehensive-review"
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
  for marker in "INBOUND_WEBHOOK_CLASSIFICATION" "SKILL38_RUNTIME_ROUTING" "workflow-builder"; do
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

# -------- Final summary --------
section "QC SUMMARY"
echo "  PASS: $PASS"
echo "  FAIL: $FAIL"
if [ "$FAIL" -eq 0 ]; then
  echo ""
  echo "  RESULT: PASS — all mechanical QC items green. Proceed to human-judgment items in protocols/pre-handoff-qc-protocol.md."
  exit 0
else
  echo ""
  echo "  RESULT: FAIL — $FAIL item(s) need attention. Do NOT seal the Run Manifest."
  exit 1
fi

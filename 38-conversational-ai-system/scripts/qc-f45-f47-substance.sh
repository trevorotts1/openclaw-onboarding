#!/usr/bin/env bash
# qc-f45-f47-substance.sh — machine-enforce the SUBSTANCE of F45 (geo-qualification)
# and F47 (smart FAQ) in their protocol files.
#
# WHY THIS GATE EXISTS
# --------------------
# qc-feature-logs.sh proves the F52 JSONL contract exists; qc-zhc-tag-prefix.sh
# proves the tag tokens are ZHC- prefixed. NEITHER proves the BEHAVIORAL substance
# the roadmap (references/conversational-ai-strategic-roadmap.md, Features 45 + 47)
# specifies. This gate fails closed if a deep-fix regression strips any required
# spec point from protocols/geo-qualification-protocol.md or
# protocols/smart-faq-tool-protocol.md.
#
# WHAT IT ENFORCES
# ----------------
# F47 (smart-faq-tool-protocol.md):
#   1. parallel FAQ-match layer ALONGSIDE the active workflow / F44 layer
#   2. a SENTENCE not a sub-flow (the F47 weight)
#   3. the return-to-step handoff string "By the way, [answer]. Coming back to [topic]"
#   4. per-workflow faq-scope.md, framed sales-relevant vs ops-relevant
#   5. matches KnowledgeBases/business/faqs.md
#   6. the explicit F44(sub-flow) vs F47(sentence) difference
#   7. bigger questions hand off to F44 (ZHC-faq-detoured)
#   8. tag ZHC-faq-answered
#   9. faq-detour-log.jsonl + schema fields (faq_topic, in_scope, returned_to_step)
#  10. Learning Loop section (U-3): unknown-becomes-known, ZHC-faq-unknown
#  11. the two new event types faq_unknown_flagged + faq_learned
#  12. the operator-only write rule (only an operator Telegram reply writes faqs.md)
#
# F45 (geo-qualification-protocol.md):
#   1. toggle default OFF (geo_qualification.enabled false)
#   2. per-product toggle (geo_qualification.per_product)
#   3. detection priority pixel/IP -> phone area code -> form address -> explicit ask
#   4. ALWAYS-confirm-before-disqualify + the exact confirmation question
#   5. all response branches: here / elsewhere / vacation / moving / no-engagement=do-not-disqualify
#   6. the 4 out-of-area modes (decline_plus_referral / limited_remote / waitlist / full_decline)
#   7. service-areas.md format (radius / zips / states / counties, per product)
#   8. tags ZHC-out-of-service-area / -confirmed / -flexible
#   9. geo-qualification-log.jsonl + the confirmed_with_customer invariant
#
# Pure BASH (grep core) — respects qc-static's .py claude-/anthropic ban. bash -n
# clean. set -uo pipefail.
#
# Exit 0 = clean; 1 = a substance violation.
#
# Usage:
#   bash scripts/qc-f45-f47-substance.sh
#   bash scripts/qc-f45-f47-substance.sh --skill-dir /path/to/38-conversational-ai-system

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

while [ $# -gt 0 ]; do
  case "$1" in
    --skill-dir) SKILL_DIR="$2"; shift 2 ;;
    -h|--help) sed -n '1,46p' "$0"; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; exit 2 ;;
  esac
done

FAIL=0
F47="$SKILL_DIR/protocols/smart-faq-tool-protocol.md"
F45="$SKILL_DIR/protocols/geo-qualification-protocol.md"

echo "=== qc-f45-f47-substance: F45 + F47 behavioral-substance guard ==="
echo "skill_dir : $SKILL_DIR"
echo ""

# require_in <file> <human-label> <fixed-string>
require_in() {
  local f="$1" label="$2" needle="$3"
  if [ ! -f "$f" ]; then
    echo "  [FAIL] missing file: $f"; FAIL=1; return
  fi
  if grep -qiF -- "$needle" "$f"; then
    echo "  [PASS] $label"
  else
    echo "  [FAIL] $label — expected to find: \"$needle\""
    FAIL=1
  fi
}

echo "--- F47 (smart-faq-tool-protocol.md) ---"
require_in "$F47" "F47.1 parallel FAQ-match layer alongside the active workflow"        "parallel FAQ-match layer"
require_in "$F47" "F47.1 runs alongside the F44 always-listening layer"                 "alongside the F44 always-listening layer"
require_in "$F47" "F47.2 a SENTENCE, not a sub-flow"                                     "a SENTENCE"
require_in "$F47" "F47.3 return-to-step handoff string"                                  "By the way, [answer]. Coming back to [topic]"
require_in "$F47" "F47.4 per-workflow faq-scope.md"                                      "faq-scope.md"
require_in "$F47" "F47.4 faq-scope framed sales-relevant vs ops-relevant"               "sales-relevant vs ops-relevant"
require_in "$F47" "F47.5 matches KnowledgeBases/business/faqs.md"                        "KnowledgeBases/business/faqs.md"
require_in "$F47" "F47.6 explicit F44 sub-flow vs F47 sentence difference"              "SUB-FLOW (save"
require_in "$F47" "F47.7 bigger questions hand off to F44 (ZHC-faq-detoured)"            "ZHC-faq-detoured"
require_in "$F47" "F47.8 tag ZHC-faq-answered"                                           "ZHC-faq-answered"
require_in "$F47" "F47.9 faq-detour-log.jsonl"                                           "faq-detour-log.jsonl"
require_in "$F47" "F47.9 schema field returned_to_step"                                  "returned_to_step"
require_in "$F47" "F47.9 schema field in_scope"                                          "in_scope"
require_in "$F47" "F47.9 schema field faq_topic"                                         "faq_topic"
require_in "$F47" "F47.10 Learning Loop section (U-3)"                                   "Learning Loop"
require_in "$F47" "F47.10 unknown-becomes-known loop (CloseBot CB-6)"                    "unknown-becomes-known"
require_in "$F47" "F47.10 unknown FAQ tag ZHC-faq-unknown"                               "ZHC-faq-unknown"
require_in "$F47" "F47.11 new event type faq_unknown_flagged"                            "faq_unknown_flagged"
require_in "$F47" "F47.11 new event type faq_learned"                                    "faq_learned"
require_in "$F47" "F47.12 operator-only write rule (only an operator Telegram reply)"    "ONLY an operator Telegram reply writes knowledge to faqs.md"

echo ""
echo "--- F45 (geo-qualification-protocol.md) ---"
require_in "$F45" "F45.1 global toggle default OFF (enabled false)"                      "\"enabled\": false"
require_in "$F45" "F45.2 per-product toggle key"                                         "per_product"
require_in "$F45" "F45.3 detection priority — pixel/IP"                                  "Pixel/IP location"
require_in "$F45" "F45.3 detection priority — phone area code"                           "Phone area code"
require_in "$F45" "F45.3 detection priority — form address"                              "Form address"
require_in "$F45" "F45.3 detection priority — explicit ask"                              "Explicit ask"
require_in "$F45" "F45.4 ALWAYS-confirm-before-disqualify"                               "ALWAYS ASK"
require_in "$F45" "F45.4 the exact confirmation question"                                "what ZIP code would the service be at"
require_in "$F45" "F45.5 branch — here / in-area"                                        "in-area"
require_in "$F45" "F45.5 branch — elsewhere / confirmed out-of-area"                     "confirmed out-of-area"
require_in "$F45" "F45.5 branch — vacation"                                              "vacation"
require_in "$F45" "F45.5 branch — moving"                                                "Moving"
require_in "$F45" "F45.5 branch — no engagement = do-not-disqualify"                     "do-not-disqualify"
require_in "$F45" "F45.6 out-of-area mode decline_plus_referral"                         "decline_plus_referral"
require_in "$F45" "F45.6 out-of-area mode limited_remote"                                "limited_remote"
require_in "$F45" "F45.6 out-of-area mode waitlist"                                      "waitlist"
require_in "$F45" "F45.6 out-of-area mode full_decline"                                  "full_decline"
require_in "$F45" "F45.7 service-areas.md"                                               "service-areas.md"
require_in "$F45" "F45.7 type radius"                                                    "type: radius"
require_in "$F45" "F45.7 type zips"                                                      "type: zips"
require_in "$F45" "F45.7 type states"                                                    "type: states"
require_in "$F45" "F45.7 type counties"                                                  "type: counties"
require_in "$F45" "F45.8 tag ZHC-out-of-service-area"                                    "ZHC-out-of-service-area"
require_in "$F45" "F45.8 tag ZHC-service-area-confirmed"                                 "ZHC-service-area-confirmed"
require_in "$F45" "F45.8 tag ZHC-service-area-flexible"                                  "ZHC-service-area-flexible"
require_in "$F45" "F45.9 geo-qualification-log.jsonl"                                    "geo-qualification-log.jsonl"
require_in "$F45" "F45.9 confirmed_with_customer invariant"                              "confirmed_with_customer:true"

echo ""
if [ "$FAIL" -eq 0 ]; then
  echo "RESULT: PASS — F45 + F47 carry every required behavioral-substance point from the roadmap."
  exit 0
else
  echo "RESULT: FAIL — an F45/F47 substance point is missing. See above."
  exit 1
fi

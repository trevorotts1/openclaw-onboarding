#!/usr/bin/env bash
# test_qc_built_funnel.sh — runs the REAL qc-built-funnel.sh + the REAL shared-utils/fab_qc.py
# against synthetic evidence trees.
#   S06-12  step type comes from the route node: a private checkout / thank-you passes,
#           an INDEXABLE thank-you fails, an unknown route role fails closed.
#   S06-16  the FAB-QC overlay is mandatory: no match-decision receipt => FAIL, scorer
#           missing => FAILED (never a skip).
# Usage: bash 06-ghl-install-pages/tests/test_qc_built_funnel.sh   (exit 0 = all pass)
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
SKILL="$(cd "$HERE/.." && pwd)"
QC="$SKILL/qc-built-funnel.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/qc-built-funnel-test.XXXXXX")" || exit 2
trap 'rm -rf "$WORK"' EXIT
export TMPDIR="$WORK"
unset CC_TASK_ID PAGE_QC_ENABLED QC_FUNNEL_LEGACY_EVIDENCE PYTHONPATH PYTHONHOME

FAILS=0
check() { # check <name> <expected_rc> <rc> <output> [must-contain]
  local name="$1" want="$2" got="$3" out="$4" needle="${5:-}"
  if [ "$got" -ne "$want" ]; then
    echo "FAIL $name: rc=$got want=$want"; echo "$out" | tail -15; FAILS=$((FAILS+1)); return
  fi
  if [ -n "$needle" ] && [[ "$out" != *"$needle"* ]]; then
    echo "FAIL $name: output lacks '$needle'"; echo "$out" | tail -15; FAILS=$((FAILS+1)); return
  fi
  echo "ok   $name"
}

BODY="$(python3 -c "print(' '.join(['word']*60))")"
PUBLIC_SEO='{"title":"Book Your Strategy Call Today","description":"Book a strategy call with our founder to map your next step.","keywords":["strategy call","business coaching","growth plan"],"author":"Jane Q Founder","canonicalUrl":"https://example.com/book","ogImage":"https://images.example-cdn.com/og.jpg","language":"en","links":[],"tags":[]}'
PRIVATE_SEO='{"title":"Order Your Program","description":"","keywords":[],"author":"","canonicalUrl":"","ogImage":"","language":"en","links":[],"tags":[],"robots":"noindex, nofollow"}'

# mk_tree <dir> <thank_you_seo_json> — a build that scores 10 on every FAB-QC dimension.
mk_tree() {
  local d="$1" ty="$2"
  mkdir -p "$d/routing" "$d/build" "$d/scorecard" "$d/pages"
  echo '{"flex_decision":"CREATE_NEW","intent_mode":"NO_SPEC"}' > "$d/routing/match-decision.json"
  printf '{"pages":[{"name":"landing","copy":{"body":"%s"}}]}\n' "$BODY" > "$d/build/fab-artifact.json"
  echo '{"overall_pass":true,"pages":[{"status":200}]}' > "$d/scorecard/verify-summary.json"
  echo 'selected_persona: Test Persona' > "$d/persona-selection-log.md"
  printf '{"page_role":"landing","seoMeta":%s}\n' "$PUBLIC_SEO" > "$d/pages/landing.json"
  printf '{"page_role":"checkout","seoMeta":%s}\n' "$PRIVATE_SEO" > "$d/pages/checkout.json"
  printf '{"page_role":"thank_you","seoMeta":%s}\n' "$ty" > "$d/pages/thank-you.json"
}

run() { OUT="$(bash "$QC" "$1" 2>&1)"; RC=$?; }

# 1. private checkout + private thank-you + public landing  -> PASS
mk_tree "$WORK/t1" "$PRIVATE_SEO"; run "$WORK/t1"
check "private checkout/thank-you pass" 0 "$RC" "$OUT" "step types={'marketing': 1, 'purchase': 1, 'thank_you': 1}"

# 2. indexable thank-you (full public SEO, no robots) -> FAIL
mk_tree "$WORK/t2" "$PUBLIC_SEO"; run "$WORK/t2"
check "indexable thank-you fails" 1 "$RC" "$OUT" "[thank_you]"

# 3. indexable checkout fails too (the page NAME says nothing; the node does)
mk_tree "$WORK/t3" "$PRIVATE_SEO"
printf '{"page_role":"checkout","seoMeta":%s}\n' "$PUBLIC_SEO" > "$WORK/t3/pages/checkout.json"; run "$WORK/t3"
check "indexable checkout fails" 1 "$RC" "$OUT" "[purchase]"

# 4. upsell / downsell / selection are private nodes (were classified as marketing)
mk_tree "$WORK/t4" "$PRIVATE_SEO"
for r in upsell_1 downsell_1 upsell_2 product_selection; do
  printf '{"page_role":"%s","seoMeta":%s}\n' "$r" "$PRIVATE_SEO" > "$WORK/t4/pages/$r.json"
done; run "$WORK/t4"
check "upsell/downsell/selection private nodes pass" 0 "$RC" "$OUT" "'purchase': 5"

# 5. role resolved from the compiled route graph (page_id -> node role), not the file name
mk_tree "$WORK/t5" "$PRIVATE_SEO"
echo '{"nodes":[{"page_id":"L1-CHECKOUT","role":"checkout"},{"page_id":"L1-LANDING","role":"landing"}]}' > "$WORK/t5/routing/route-graph.json"
printf '{"page_id":"L1-CHECKOUT","seoMeta":%s}\n' "$PRIVATE_SEO" > "$WORK/t5/pages/landing-looking-name.json"; run "$WORK/t5"
check "role from route graph node passes" 0 "$RC" "$OUT" "'purchase': 2"
printf '{"page_id":"L1-CHECKOUT","seoMeta":%s}\n' "$PUBLIC_SEO" > "$WORK/t5/pages/landing-looking-name.json"; run "$WORK/t5"
check "route-graph checkout with public meta fails" 1 "$RC" "$OUT" "[purchase]"

# 6. unknown route role -> fail closed
mk_tree "$WORK/t6" "$PRIVATE_SEO"
printf '{"page_role":"mystery_page","seoMeta":%s}\n' "$PUBLIC_SEO" > "$WORK/t6/pages/x.json"; run "$WORK/t6"
check "unknown route role fails closed" 1 "$RC" "$OUT" "unclassifiable route role"

# 7. no match-decision receipt -> FAB-QC FAIL (was a silent no-op)
mk_tree "$WORK/t7" "$PRIVATE_SEO"; rm "$WORK/t7/routing/match-decision.json"; run "$WORK/t7"
check "missing match-decision receipt fails FAB-QC" 1 "$RC" "$OUT" "no routing/match-decision.json receipt"

# 8. FAB-QC scorer missing -> FAILED, never a skip (exit 1, not 2)
mkdir -p "$WORK/lay/skill" "$WORK/lay/shared-utils"
cp "$QC" "$WORK/lay/skill/"; ln -s "$SKILL/tools" "$WORK/lay/skill/tools"
mk_tree "$WORK/t8" "$PRIVATE_SEO"
OUT="$(bash "$WORK/lay/skill/qc-built-funnel.sh" "$WORK/t8" 2>&1)"; RC=$?
check "missing fab_qc.py is FAILED" 1 "$RC" "$OUT" "FAB-QC overlay did not run"

# 9. legacy env opt-out is logged and alerted
mk_tree "$WORK/t9" "$PRIVATE_SEO"; rm -f "$WORK/t9/pages/"*.json
printf '{"name":"landing"}\n' > "$WORK/t9/pages/plain.json"
OUT="$(QC_FUNNEL_LEGACY_EVIDENCE=1 bash "$QC" "$WORK/t9" 2>&1)"; RC=$?
check "legacy env opt-out logged" 0 "$RC" "$OUT" "ALERT QC_FUNNEL_LEGACY_EVIDENCE=1"
if [ -f "$WORK/t9/scorecard/qc-alerts.jsonl" ] && [[ "$(cat "$WORK/t9/scorecard/qc-alerts.jsonl")" == *legacy_seo_evidence* ]]; then
  echo "ok   legacy env opt-out recorded in qc-alerts.jsonl"
else echo "FAIL legacy env opt-out: qc-alerts.jsonl missing legacy_seo_evidence"; FAILS=$((FAILS+1)); fi

# 10. control: env unset -> missing seoMeta is a hard FAIL and no alert file
mk_tree "$WORK/t10" "$PRIVATE_SEO"; rm -f "$WORK/t10/pages/"*.json
printf '{"name":"landing"}\n' > "$WORK/t10/pages/plain.json"; run "$WORK/t10"
check "no seoMeta without opt-out fails" 1 "$RC" "$OUT" "no seoMeta found"
if [ -e "$WORK/t10/scorecard/qc-alerts.jsonl" ]; then echo "FAIL control wrote an alert file"; FAILS=$((FAILS+1)); else echo "ok   control: no alert file"; fi

[ "$FAILS" -eq 0 ] && echo "ALL PASS" || echo "$FAILS FAILED"
exit $((FAILS > 0))

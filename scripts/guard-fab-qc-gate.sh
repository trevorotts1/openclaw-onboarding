#!/usr/bin/env bash
# guard-fab-qc-gate.sh — CI static guard for the standing FAB-QC build-quality gate.
#
# THE RULE: the funnel/automation build-quality gate (FAB-QC >= 8.5) must NOT be silently
# weakened or removed. This asserts the rubric + shared scorer exist, the 8.5 threshold is
# intact, and the gate call-sites in BOTH skills are present. A future PR that drops the
# threshold or stops calling the overlay fails this guard.
#
# Exit 0 = all invariants hold; non-zero = a gate invariant regressed (names which one).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
has()  { grep -q -- "$2" "$1" 2>/dev/null; }

RUBRIC="$ROOT/universal-sops/funnel-automation-build-quality-rubric.md"
SCORER="$ROOT/shared-utils/fab_qc.py"
DISPATCH="$ROOT/06-ghl-install-pages/tools/v2_dispatcher.py"
WF_QC="$ROOT/44-convert-and-flow-operator/qc-built-workflow.sh"
FUNNEL_QC="$ROOT/06-ghl-install-pages/qc-built-funnel.sh"
SOP="$ROOT/06-ghl-install-pages/v2-autonomous-build-sop.md"
INSTR="$ROOT/44-convert-and-flow-operator/INSTRUCTIONS.md"
PRODUCER="$ROOT/shared-utils/fab_artifact.py"
CROSSWALK_PY="$ROOT/shared-utils/persona_crosswalk.py"
CROSSWALK_JSON="$ROOT/shared-utils/persona-crosswalk.json"
PAGE_QC="$ROOT/shared-utils/page_qc.py"
ARCHIVE_GATE="$ROOT/06-ghl-install-pages/tools/ghl_archive_receipt_gate.py"
GITHUB_RECONCILE="$ROOT/06-ghl-install-pages/tools/ghl_github_reconcile.py"
SCHEDULE_ENTRY="$ROOT/06-ghl-install-pages/schedule/skill6-github-archive-reconcile-sweep.cron.json"
SCHEDULE_INSTALLER="$ROOT/06-ghl-install-pages/scripts/install-github-archive-reconcile-cron.sh"
BUNDLE_LADDER="$ROOT/06-ghl-install-pages/tools/persona_bundle_ladder.py"
COPY_SEAM="$ROOT/49-signature-funnel/scripts/copy_persona_blend_seam.py"
ANTI_COPY="$ROOT/shared-utils/anti_copy_guard.py"
ANTI_COPY_TEST="$ROOT/tests/unit/u10-anti-copy-guard.test.py"

echo "═══ FAB-QC gate guard ═══"

# 1. Rubric + scorer exist.
[ -f "$RUBRIC" ] && ok "rubric present: universal-sops/funnel-automation-build-quality-rubric.md" \
                 || bad "MISSING rubric: universal-sops/funnel-automation-build-quality-rubric.md"
[ -f "$SCORER" ] && ok "shared scorer present: shared-utils/fab_qc.py" \
                 || bad "MISSING shared scorer: shared-utils/fab_qc.py"

# 1b. FAB-artifact PRODUCER (D4) exists + is wired into BOTH build paths so the gate has
#     something REAL to score (not a hand fixture).
[ -f "$PRODUCER" ] && ok "FAB-artifact producer present: shared-utils/fab_artifact.py" \
                   || bad "MISSING producer: shared-utils/fab_artifact.py (gate scores nothing on a real build)"
if has "$DISPATCH" "_emit_fab_artifact" && has "$DISPATCH" "build_funnel_artifact"; then
  ok "Skill-6 dispatcher emits build/fab-artifact.json from the real build (producer wired)"
else
  bad "Skill-6 v2_dispatcher.py does not emit a fab-artifact (FAB gate is a no-op on real builds)"
fi
if has "$WF_QC" "fab_artifact.py"; then
  ok "Skill-44 qc-built-workflow.sh emits the fab-artifact from the export before scoring"
else
  bad "Skill-44 qc-built-workflow.sh does not run the fab-artifact producer (FAB gate scores nothing)"
fi

# 1c. Persona crosswalk (D5): 0 unresolved persona refs across all templates.
[ -f "$CROSSWALK_PY" ] && ok "persona crosswalk resolver present: shared-utils/persona_crosswalk.py" \
                       || bad "MISSING shared-utils/persona_crosswalk.py"
[ -f "$CROSSWALK_JSON" ] && ok "persona crosswalk map present: shared-utils/persona-crosswalk.json" \
                         || bad "MISSING shared-utils/persona-crosswalk.json"
if [ -f "$CROSSWALK_PY" ]; then
  if python3 "$CROSSWALK_PY" --validate >/dev/null 2>&1; then
    ok "persona crosswalk validates: 0 unresolved refs, all targets canonical"
  else
    bad "persona crosswalk FAILED: an unresolved persona ref or non-canonical target exists"
  fi
fi

# 1d. D5/B-D1 (B-U4) — copy_craft_pool: the copy-craft TASK-slot pool that replaced the old
#     5-surname cap must exist, be non-empty, and validate. Checked directly (not just via the
#     --validate call above) so a deleted `copy_craft_pool` key fails with an unambiguous message.
if [ -f "$CROSSWALK_JSON" ]; then
  if python3 -c "
import json, sys
d = json.load(open('$CROSSWALK_JSON'))
pool = d.get('copy_craft_pool') or []
sys.exit(0 if len(pool) > 0 else 1)
" 2>/dev/null; then
    ok "copy_craft_pool present + non-empty in persona-crosswalk.json (D5/B-U4)"
  else
    bad "copy_craft_pool MISSING or EMPTY in persona-crosswalk.json (D5/B-U4 copy-craft task-slot pool deleted/regressed)"
  fi
fi

# 2. Threshold == 8.5 in the scorer and the rubric (and not lowered).
if has "$SCORER" "THRESHOLD = 8.5"; then ok "scorer THRESHOLD = 8.5"; else bad "scorer THRESHOLD is not 8.5"; fi
if has "$RUBRIC" "8.5"; then ok "rubric cites the 8.5 threshold"; else bad "rubric does not cite 8.5"; fi
# weights must still sum to 100 (assert in the scorer guards this at import).
if python3 -c "import sys; sys.path.insert(0,'$ROOT/shared-utils'); import fab_qc; assert sum(fab_qc.W.values())==100 and fab_qc.THRESHOLD==8.5" 2>/dev/null; then
  ok "scorer imports + weights sum to 100 + threshold 8.5"
else
  bad "scorer failed import / weights!=100 / threshold!=8.5"
fi

# 3. Per-skill wrappers exist.
[ -f "$FUNNEL_QC" ] && ok "Skill-6 wrapper present: qc-built-funnel.sh" || bad "MISSING qc-built-funnel.sh"
[ -f "$WF_QC" ]     && ok "Skill-44 wrapper present: qc-built-workflow.sh" || bad "MISSING qc-built-workflow.sh"

# 4. Gate call-sites are wired.
if has "$DISPATCH" "_fab_overlay" && has "$DISPATCH" "FAB-QC GATE"; then
  ok "Skill-6 dispatcher enforces the FAB-QC gate before 'verified'"
else
  bad "Skill-6 v2_dispatcher.py no longer enforces the FAB-QC gate (_fab_overlay / 'FAB-QC GATE' missing)"
fi
if has "$WF_QC" "fab_qc.py" && has "$WF_QC" "FAB_MODE"; then
  ok "Skill-44 qc-built-workflow.sh runs the FAB-QC overlay"
else
  bad "Skill-44 qc-built-workflow.sh no longer runs the FAB-QC overlay"
fi

# 5. The SOP / INSTRUCTIONS document the gate.
has "$SOP" "BUILD-QC GATE"   && ok "v2-autonomous-build-sop.md §9 documents the BUILD-QC GATE" \
                             || bad "v2-autonomous-build-sop.md no longer documents the BUILD-QC GATE"
has "$INSTR" "Step 9.3c"      && ok "INSTRUCTIONS.md documents Step 9.3c (FAB overlay)" \
                             || bad "INSTRUCTIONS.md no longer documents Step 9.3c"

# 6. U25/B-U11 — Page-QC v2 (the semantic scorer FAB-QC cannot be) must NOT be
#    silently weakened or removed either: the scorer exists, its threshold stays
#    8.5 (same standing bar, never a new one), its six weights sum to 100, and the
#    Skill-6 wrapper still calls it.
[ -f "$PAGE_QC" ] && ok "Page-QC v2 scorer present: shared-utils/page_qc.py" \
                  || bad "MISSING shared-utils/page_qc.py (U25/B-U11 semantic gate)"
if python3 -c "import sys; sys.path.insert(0,'$ROOT/shared-utils'); import page_qc; assert sum(page_qc.W.values())==100 and page_qc.THRESHOLD==8.5" 2>/dev/null; then
  ok "Page-QC v2 imports + weights sum to 100 + threshold 8.5"
else
  bad "Page-QC v2 failed import / weights!=100 / threshold!=8.5 (U25/B-U11 regressed)"
fi
if has "$FUNNEL_QC" "page_qc.py" && has "$FUNNEL_QC" "PAGE_QC_ENABLED"; then
  ok "Skill-6 qc-built-funnel.sh wires the Page-QC v2 overlay (flag-gated)"
else
  bad "Skill-6 qc-built-funnel.sh no longer wires Page-QC v2 (page_qc.py / PAGE_QC_ENABLED missing)"
fi

# 7. U24/B-U10 — the shipped GitHub archival rail must stay proven + scheduled:
#    the per-build FAB-QC archive-receipt gate exists and is wired (always-on,
#    never flag-gated — it's a no-op for non-VERCEL_EMBED evidence), and the
#    reconcile sweep still exposes the --sweep-base maintenance-window mode.
[ -f "$ARCHIVE_GATE" ] && ok "GitHub archive-receipt gate present: 06-ghl-install-pages/tools/ghl_archive_receipt_gate.py" \
                        || bad "MISSING 06-ghl-install-pages/tools/ghl_archive_receipt_gate.py (U24/B-U10 gate)"
if has "$FUNNEL_QC" "ghl_archive_receipt_gate.py" && has "$FUNNEL_QC" "--gate"; then
  ok "Skill-6 qc-built-funnel.sh wires the GitHub archive-receipt gate"
else
  bad "Skill-6 qc-built-funnel.sh no longer wires the GitHub archive-receipt gate (U24/B-U10 regressed)"
fi
if has "$GITHUB_RECONCILE" "sweep_base" && has "$GITHUB_RECONCILE" "--sweep-base"; then
  ok "ghl_github_reconcile.py exposes the --sweep-base maintenance-window mode"
else
  bad "ghl_github_reconcile.py no longer exposes --sweep-base (U24/B-U10 scheduling regressed)"
fi
if has "$GITHUB_RECONCILE" "verify_repo_byte_match" && has "$GITHUB_RECONCILE" "--verify-local-repo"; then
  ok "ghl_github_reconcile.py exposes the local-fixture-repo byte-match proof (B-U10 (b), amended)"
else
  bad "ghl_github_reconcile.py no longer exposes --verify-local-repo (U24/B-U10 amended acceptance (b) regressed)"
fi
[ -f "$SCHEDULE_ENTRY" ] && has "$SCHEDULE_ENTRY" "--retry" \
  && ok "maintenance-window schedule ENTRY present, by name: schedule/skill6-github-archive-reconcile-sweep.cron.json" \
  || bad "MISSING/incomplete maintenance-window schedule entry (U24/B-U10 amended acceptance (c) regressed)"
[ -x "$SCHEDULE_INSTALLER" ] && ok "schedule-entry installer present + executable: scripts/install-github-archive-reconcile-cron.sh" \
                             || bad "MISSING/non-executable scripts/install-github-archive-reconcile-cron.sh"

# 8. U22/B-U8 — the persona-bundle-acquisition ladder (B-U1/U15) must keep
#    writing its receipt in the ONE canonical schema every downstream
#    consumer (funnel_matcher B-U2/U16, copy_persona_blend_seam B-U3/U17,
#    fab_qc D4 B-U5/U19) reads. A field silently renamed/dropped here breaks
#    the whole unification block without any single unit's own guard
#    catching it (each one only asserts the fields IT reads).
[ -f "$BUNDLE_LADDER" ] && ok "persona-bundle ladder present: 06-ghl-install-pages/tools/persona_bundle_ladder.py" \
                        || bad "MISSING 06-ghl-install-pages/tools/persona_bundle_ladder.py (B-U1/U15)"
if [ -f "$BUNDLE_LADDER" ]; then
  _BUNDLE_SCHEMA_CHECK=$(python3 - "$BUNDLE_LADDER" <<'PYEOF'
import importlib.util, sys, tempfile, os
path = sys.argv[1]
spec = importlib.util.spec_from_file_location("persona_bundle_ladder", path)
mod = importlib.util.module_from_spec(spec)
sys.modules["persona_bundle_ladder"] = mod
spec.loader.exec_module(mod)
REQUIRED = {"task_id", "source", "bundle_sha", "voice_persona_id", "topic_persona_id",
            "task_personas", "confirm_state", "degradation", "hold", "generated_at"}
with tempfile.TemporaryDirectory() as td:
    task = {"id": "guard-schema-check", "persona_bundle": {
        "voice_persona_id": "hormozi-100m-offers", "confirm_required": False}}
    receipt = mod.resolve_persona_bundle(task, td)
missing = REQUIRED - set(receipt.keys())
if missing:
    print("MISSING:" + ",".join(sorted(missing)))
    sys.exit(1)
sys.exit(0)
PYEOF
)
  if [ $? -eq 0 ]; then
    ok "persona-bundle-receipt schema carries all required fields (task_id/source/bundle_sha/voice_persona_id/topic_persona_id/task_personas/confirm_state/degradation/hold/generated_at)"
  else
    bad "persona-bundle-receipt schema regressed — $_BUNDLE_SCHEMA_CHECK"
  fi
fi
[ -f "$COPY_SEAM" ] && ok "copy-stage blend seam present: 49-signature-funnel/scripts/copy_persona_blend_seam.py" \
                     || bad "MISSING 49-signature-funnel/scripts/copy_persona_blend_seam.py (B-U3/U17)"

# 9. U10/A-U10 — the anti-copy guard (deterministic similarity ceiling vs
#    injected exemplars, key-free, hard-miss) must stay wired into the FAB-QC
#    hard-miss family: the module exists, its calibrated ceiling has not
#    drifted, it degrades to a true no-op (weight 0, excluded from `dims`)
#    when no exemplar_packs are supplied so pre-A-U10 scorecards stay
#    byte-identical, and fab_qc.py actually resolves real injected exemplars
#    from A-U9's own routing/exemplar-injection.json receipt (never a
#    fabricated comparison set).
[ -f "$ANTI_COPY" ] && ok "anti-copy guard present: shared-utils/anti_copy_guard.py" \
                     || bad "MISSING shared-utils/anti_copy_guard.py (U10/A-U10 guard)"
[ -f "$ANTI_COPY_TEST" ] && ok "anti-copy guard CI proof present: tests/unit/u10-anti-copy-guard.test.py" \
                          || bad "MISSING tests/unit/u10-anti-copy-guard.test.py (U10/A-U10 acceptance proof)"
if python3 -c "import sys; sys.path.insert(0,'$ROOT/shared-utils'); import anti_copy_guard as m; assert m.SIMILARITY_CEILING == 0.55 and m.CHAR_SHINGLE_K == 5" 2>/dev/null; then
  ok "anti-copy guard imports + SIMILARITY_CEILING=0.55 + CHAR_SHINGLE_K=5 (calibrated values intact)"
else
  bad "anti-copy guard failed import / ceiling or shingle-size drifted (U10/A-U10 regressed)"
fi
if has "$SCORER" "score_anti_copy" && has "$SCORER" "exemplar_packs" && has "$SCORER" "_load_exemplar_packs_from_receipt"; then
  ok "fab_qc.py wires the anti-copy guard into the hard-miss family (score_anti_copy / exemplar_packs / receipt resolver)"
else
  bad "fab_qc.py no longer wires the anti-copy guard (U10/A-U10 regressed)"
fi
if python3 -c "
import sys
sys.path.insert(0, '$ROOT/shared-utils')
import fab_qc
# No exemplar_packs supplied -> the anti-copy dim must be a true no-op
# (excluded from dims entirely), so pre-A-U10 scorecards stay byte-identical.
inp = {'kind': 'funnel', 'match_decision': {'flex_decision': 'CREATE_NEW'},
       'template': None, 'artifact': {'pages': [{'copy': {'hero': 'irrelevant'}}]},
       'verify': {'overall_pass': True, 'pages': [{'status': 200}]},
       'persona_log': 'selected_persona: x'}
r = fab_qc.grade(inp)
assert 'D-anti-copy Anti-copy guard' not in [d['name'] for d in r['dimensions']]
assert sum(fab_qc.W.values()) == 100
" 2>/dev/null; then
  ok "anti-copy guard degrades to a true no-op with no exemplar_packs (byte-identical pre-A-U10 scorecards); weights still sum to 100"
else
  bad "anti-copy guard degrade posture regressed (U10/A-U10 no-op contract broken) or weights != 100"
fi

# NOTE (U22/B-U8 merge-writer, 2026-07-15): the U22 branch's own section "7b"
# (a D5/B-U4/U18 forward-compat WARN hook for copy_craft_pool) is dropped here
# as redundant, not silently lost — by the time this branch reached `main`,
# U18/B-U4 had ALREADY landed (verified, ledger row U18) and section 1d above
# (added by that same U18 merge) already performs the HARD `bad()` check this
# hook was written to eventually become. Keeping both would just re-check the
# identical condition twice under two different section numbers.

echo ""
if [ "$FAIL" -ne 0 ]; then
  echo "✗ FAB-QC gate guard FAILED — a build-quality gate invariant regressed."
  exit 1
fi
echo "✓ FAB-QC gate guard PASSED."
exit 0

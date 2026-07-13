#!/usr/bin/env bash
# Skill 06 — GHL Install Pages — Install QC (agent-browser PRIMARY + Playwright FALLBACK + GHL auth)
set -u
PASS=0; FAIL=0; WARN=0
SKILL_DIR="$(dirname "$0")"
LIB="$SKILL_DIR/../lib-shared.sh"; [ -f "$LIB" ] && source "$LIB"
if ! command -v resolve_platform_paths >/dev/null 2>&1; then
  resolve_platform_paths() { export SECRETS_ENV="$HOME/.openclaw/secrets/.env" WORKSPACE="$HOME/clawd" SKILLS_DIR_DEFAULT="$HOME/.openclaw/skills"; }
fi
resolve_platform_paths
red(){ printf "\033[31m%s\033[0m\n" "$1"; }; green(){ printf "\033[32m%s\033[0m\n" "$1"; }; yellow(){ printf "\033[33m%s\033[0m\n" "$1"; }
assert(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else red "  ✗ FAIL — $1"; FAIL=$((FAIL+1)); fi; }
warn_only(){ if eval "$2" >/dev/null 2>&1; then green "  ✓ PASS — $1"; PASS=$((PASS+1)); else yellow "  ⚠ WARN — $1"; WARN=$((WARN+1)); fi; }

if [ -f "$SECRETS_ENV" ]; then set +u; set -a; . "$SECRETS_ENV" 2>/dev/null || true; set +a; set -u; fi
: "${GHL_AGENCY_EMAIL:=}"; : "${GHL_AGENCY_PASSWORD:=}"; : "${GHL_EMAIL:=}"; : "${GHL_PASSWORD:=}"

echo ""
echo "═══ Skill 06 — GHL Install Pages — Install QC ═══"
echo ""
SK="$SKILLS_DIR_DEFAULT/06-ghl-install-pages"
assert "Skill 06 folder present" "[ -d \"$SK\" ]"
assert "v3.0 hardened reference present" "[ -f \"$SK/ghl-browser-builder-full.md\" ]"
assert "auth-seed module present"   "[ -f \"$SK/tools/seed-ghl-auth.py\" ]"
assert "auth-inject script present" "[ -f \"$SK/tools/inject-ghl-auth.sh\" ]"
assert "builder helper present"     "[ -f \"$SK/tools/ghl_builder.py\" ]"
assert "gate registry present"      "[ -f \"$SK/tools/gates.json\" ]"
# D8 contract: exactly 2 captured gates (login form + auth storage), 26 runtime snapshot-gates.
assert "gate registry has 2 captured gates"  "[ \"\$(python3 -c 'import json;print(sum(1 for g in json.load(open(\"$SK/tools/gates.json\"))[\"gates\"] if g.get(\"status\")==\"captured\"))' 2>/dev/null)\" = '2' ]"
assert "gate registry has 26 runtime gates"  "[ \"\$(python3 -c 'import json;print(sum(1 for g in json.load(open(\"$SK/tools/gates.json\"))[\"gates\"] if g.get(\"status\")==\"runtime\"))' 2>/dev/null)\" = '26' ]"
# Version-marker consistency gate (repo version-bump hygiene, v19.0.1 fix):
# skill-version.txt and SKILL.md's metadata.version are repo-locked in
# lockstep by scripts/bump-version.sh (same pattern as
# 23-ai-workforce-blueprint/skill-version.txt) — they must agree with EACH
# OTHER. CHANGELOG.md keeps its own independent per-skill semver (like every
# other skill's CHANGELOG) and is only checked for being present/well-formed,
# not for numeric equality to the repo-locked markers. See
# scripts/check-version-drift.py docstring for the full rationale.
VER_CHECK="$SKILL_DIR/scripts/check-version-drift.py"
if [ -f "$VER_CHECK" ]; then
  assert "Version markers consistent (skill-version.txt == SKILL.md; CHANGELOG well-formed)" \
    "python3 \"$VER_CHECK\" \"$SK\""
else
  warn_only "version-drift checker available (scripts/check-version-drift.py)" "[ -f \"$VER_CHECK\" ]"
fi
assert "builder helper parses clean" "python3 -c \"import ast;ast.parse(open('$SK/tools/ghl_builder.py').read())\""
assert "auth-seed module parses clean" "python3 -c \"import ast;ast.parse(open('$SK/tools/seed-ghl-auth.py').read())\""
# Cross-origin iframe drag FIX (shared frame-scoped coordinate-drag primitive).
assert "iframe-drag primitive present"     "[ -f \"$SK/tools/ghl_iframe_drag.py\" ]"
assert "iframe-drag primitive parses clean" "python3 -c \"import ast;ast.parse(open('$SK/tools/ghl_iframe_drag.py').read())\""
assert "iframe-drag dep-free selftest passes" "python3 \"$SK/tools/ghl_iframe_drag.py\" --selftest"
warn_only "iframe-drag LIVE selftest passes (needs Playwright)" "python3 \"$SK/tools/ghl_iframe_drag.py\" --live-selftest"
# TOKEN-ONLY doctrine (D7): the Firebase refresh token is the ONLY auth path.
# GHL_AGENCY_EMAIL/PASSWORD are a MANUAL operator-only last resort — NOT required
# for builds and NEVER auto-invoked. So they are warn-only, not a hard assert.
warn_only "GHL manual-only login email set (operator last resort, optional)"     "[ -n \"$GHL_AGENCY_EMAIL\" ] || [ -n \"$GHL_EMAIL\" ]"
warn_only "GHL manual-only login password set (operator last resort, optional)"  "[ -n \"$GHL_AGENCY_PASSWORD\" ] || [ -n \"$GHL_PASSWORD\" ]"
assert "Secrets file chmod 600"         "[ \"\$(stat -f %A \"$SECRETS_ENV\" 2>/dev/null || stat -c %a \"$SECRETS_ENV\" 2>/dev/null)\" = '600' ]"
assert "Node.js installed" "command -v node"
assert "npm installed" "command -v npm"
warn_only "agent-browser installed (PRIMARY engine)" "command -v agent-browser || [ -x \"$HOME/.npm-global/bin/agent-browser\" ]"
warn_only "Playwright installed (FALLBACK)"   "npm list -g playwright 2>/dev/null | grep -q playwright || npm list playwright 2>/dev/null | grep -q playwright || command -v playwright"
warn_only "Firebase refresh token set (seeds logged-in session)" "[ -n \"\${GOHIGHLEVEL_FIREBASE_REFRESH_TOKEN:-}\" ] || [ -n \"\${CAF_FIREBASE_REFRESH_TOKEN:-}\" ] || [ -n \"\${GHL_FIREBASE_REFRESH_TOKEN:-}\" ]"
warn_only "Chrome/Chromium present" "command -v chromium || command -v google-chrome || ls '/Applications/Google Chrome.app' 2>/dev/null"
warn_only "Client white-label URL stored" "grep -qiE 'app\\.gohighlevel\\.com|app\\.convertandflow\\.com|app\\.[a-z0-9]+\\.com' \"$WORKSPACE/MEMORY.md\" 2>/dev/null"
assert "GHL password NOT in workspace .md files" "! grep -rE 'GHL_(AGENCY_)?PASSWORD\\s*=\\s*[A-Za-z0-9]' \"$WORKSPACE\"/*.md 2>/dev/null | grep -v 'XXX\\|xxx'"

# TOKEN-ONLY doctrine guard (D7): fails if seed-ghl-auth.py / inject-ghl-auth.sh
# reintroduce an auto UI-login / 2FA fallback, or if the doctrine sentinel is
# missing from the skill docs. Runs against the repo source when present (the
# guard ships at <repo>/scripts/guard-ghl-token-only.sh, two levels up from this
# skill dir). Skipped (warn-only) when the repo layout is absent on a client box.
REPO="$(cd "$SKILL_DIR/.." 2>/dev/null && pwd)"
GUARD="$SKILL_DIR/../scripts/guard-ghl-token-only.sh"
if [ -f "$GUARD" ]; then
  assert "TOKEN-ONLY auth doctrine intact (no auto login/2FA; sentinel present)" "bash \"$GUARD\" --repo-root \"$REPO\""
else
  warn_only "TOKEN-ONLY auth doctrine guard available" "[ -f \"$GUARD\" ]"
fi

# Tier-1 ACTIVATION RESILIENCE guard (R1..R6, no F1..F4).
GUARD_AR="$SKILL_DIR/../scripts/guard-ghl-activation-resilience.sh"
if [ -f "$GUARD_AR" ]; then
  assert "Tier-1 activation resilience intact (no single-shot regression)" "bash \"$GUARD_AR\" --repo-root \"$REPO\""
else
  warn_only "activation-resilience guard available" "[ -f \"$GUARD_AR\" ]"
fi

# Tier-2 EMAIL-2FA FALLBACK guard (containment, gate-before-login, bounded,
# self-heal, no-secret-leak, client-store-only, Tier-1-primary, sentinel).
GUARD_FB="$SKILL_DIR/../scripts/guard-ghl-auth-fallback.sh"
if [ -f "$GUARD_FB" ]; then
  assert "Tier-2 email-2FA fallback doctrine intact (gated, bounded, self-heals; sentinel present)" "bash \"$GUARD_FB\" --repo-root \"$REPO\""
else
  warn_only "Tier-2 auth-fallback guard available" "[ -f \"$GUARD_FB\" ]"
fi

# Tier-2 test layer (MOCK GHL + MOCK Gmail only — never a real account).
T2_TESTS="$SKILL_DIR/tests"
if command -v pytest >/dev/null 2>&1 && [ -f "$T2_TESTS/test_guard_ghl_auth_fallback.py" ]; then
  warn_only "Tier-2 auth-fallback pytest suite passes (mock-only)" \
    "( cd \"$SKILL_DIR\" && pytest -q tests/test_ghl_auth_orchestrator.py tests/test_ghl_auth_fallback_gates.py tests/test_ghl_auth_fallback_happy_and_selfheal.py tests/test_guard_ghl_auth_fallback.py tests/test_ghl_secret_hygiene.py )"
fi

# B8 ENFORCEMENT GUARDS (2026-06-26): CI-time static checks that no fake-pass
# shortcut or missing method-decision file can slip through.
# These guards live in $SKILL_DIR/scripts/ (skill-level, not repo-level) because
# they are specific to Skill 06 and not shared across the fleet.
GUARD_MD="$SKILL_DIR/scripts/guard-ghl-method-decision.sh"
GUARD_VU="$SKILL_DIR/scripts/guard-ghl-verify-unfakeable.sh"

if [ -f "$GUARD_MD" ]; then
  assert "B8: method-decision gate present and required in gates.json" \
    "bash \"$GUARD_MD\" --static"
else
  warn_only "B8 method-decision guard available (scripts/guard-ghl-method-decision.sh)" \
    "[ -f \"$GUARD_MD\" ]"
fi

if [ -f "$GUARD_VU" ]; then
  assert "B8: verify-layer cannot be faked (VerifyContradiction + no storage-marker pass)" \
    "bash \"$GUARD_VU\""
else
  warn_only "B8 verify-unfakeable guard available (scripts/guard-ghl-verify-unfakeable.sh)" \
    "[ -f \"$GUARD_VU\" ]"
fi

# ── Transcript build-recipe coverage (SEO panel + founder author + media folder
# discipline + ZHC casing). These are the §2/§3 end-state contracts the build must
# reach — assert the code that enforces them is present so a regression can't ship.
assert "Canonical transcript build-recipe present" \
  "[ -f \"$SK/references/ghl-build-spec-from-transcript.md\" ]"
assert "SKILL.md surfaces the canonical transcript recipe in reading order" \
  "grep -q 'ghl-build-spec-from-transcript.md' \"$SK/SKILL.md\""
assert "SEO panel builder present (build_seo_meta + founder author + populated gate)" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_builder as b;assert all(hasattr(b,n) for n in ('build_seo_meta','validate_founder_name','assert_seo_populated'))\""
assert "emit_rest_save_plan accepts a 'seo' spec (SEO is an ordered save step)" \
  "python3 -c \"import sys,inspect;sys.path.insert(0,'$SK/tools');import ghl_builder as b;assert 'seo' in inspect.signature(b.emit_rest_save_plan).parameters\""
assert "page seoMeta splice present in ghl_rest_canvas (set_page_seo/page_seo_autosave)" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_rest_canvas as c;assert all(hasattr(c,n) for n in ('build_seo_meta','set_page_seo','page_seo_autosave','assert_seo_populated'))\""
assert "ZHC prefix EMITS uppercase 'ZHC ' (transcript casing)" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_builder as b;assert b.ensure_zhc_prefix('test').startswith('ZHC ')\""
assert "Multi-step auto-naming 'ZHC part N' present" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_builder as b;assert b.zhc_step_name(None,2)=='ZHC part 2'\""
assert "Founder name is fail-closed (real name passes; placeholder/blank HALTs)" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_builder as b;assert b.validate_founder_name('Jane Maker')=='Jane Maker' and b._is_placeholder_token('placeholder') and b._is_placeholder_token('')\""
assert "Media folder-per-funnel wiring present (ensure_funnel_media_folders, never browser-routed)" \
  "python3 -c \"import sys;sys.path.insert(0,'$SK/tools');import ghl_media as m;assert hasattr(m,'ensure_funnel_media_folders') and hasattr(m,'funnel_media_folder_plan')\""

# ── VERCEL_EMBED non-blocking GitHub archival + reconciliation sweep ─────────
# Operator standing rule: a page's source must ALWAYS also live in GitHub.
# These asserts prove the doctrine fix actually shipped (not just prose) and
# guard against the "NOT GitHub" line ever creeping back into SKILL.md.
assert "GitHub archival module present" "[ -f \"$SK/tools/ghl_github_archive.py\" ]"
assert "GitHub archival module parses clean" \
  "python3 -c \"import ast;ast.parse(open('$SK/tools/ghl_github_archive.py').read())\""
assert "GitHub archival self-test passes (no network, no real subprocess)" \
  "python3 \"$SK/tools/ghl_github_archive.py\" --selftest"
assert "GitHub reconciliation sweep present" "[ -f \"$SK/tools/ghl_github_reconcile.py\" ]"
assert "GitHub reconciliation sweep parses clean" \
  "python3 -c \"import ast;ast.parse(open('$SK/tools/ghl_github_reconcile.py').read())\""
assert "run_pipeline is wired to non-blocking GitHub archival (evidence_root param + github_archive field)" \
  "python3 -c \"import sys,inspect;sys.path.insert(0,'$SK/tools');import ghl_vercel as v;sig=inspect.signature(v.run_pipeline);assert 'evidence_root' in sig.parameters;assert 'github_archive' in [f.name for f in __import__('dataclasses').fields(v.VercelEmbedReceipt)]\""
assert "SKILL.md no longer claims VERCEL_EMBED is 'NOT GitHub' (regression guard)" \
  "! grep -qi 'IS A DIRECT API UPLOAD — NOT GitHub' \"$SK/SKILL.md\""
assert "SKILL.md documents the non-blocking GitHub archive + reconciliation sweep" \
  "grep -q 'ghl_github_archive' \"$SK/SKILL.md\" && grep -q 'ghl_github_reconcile' \"$SK/SKILL.md\""
if command -v pytest >/dev/null 2>&1; then
  assert "GitHub archival + reconciliation + run_pipeline wiring pytest suites pass (mock-only)" \
    "( cd \"$SK\" && pytest -q tests/test_ghl_github_archive.py tests/test_ghl_github_reconcile.py tests/test_ghl_vercel.py )"
else
  warn_only "pytest available to run the GitHub archival test suites" "command -v pytest"
fi

echo ""
echo "═══ Result: $PASS passed | $FAIL failed | $WARN warnings ═══"
[ $FAIL -gt 0 ] && { red "Skill 06 QC FAILED"; exit 1; } || { green "Skill 06 QC PASS"; exit 0; }

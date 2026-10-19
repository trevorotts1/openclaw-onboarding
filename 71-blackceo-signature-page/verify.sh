#!/usr/bin/env bash
# Skill 71 install/update verifier. NOT a normal runtime page-build step.
set -u
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
fail=0

need_file() {
  if [ -f "$ROOT/$1" ]; then
    printf '[PASS] %s\n' "$1"
  else
    printf '[FAIL] missing %s\n' "$1" >&2
    fail=1
  fi
}

# Capability matrix (Amendment 1, Item 29 rider): with --capabilities,
# print what this host can actually run and the named skips for what it
# cannot, then exit. SKIP-RENDER means the Playwright/Chromium render
# tests skip on this host; SKIP-IMAGE means the Pillow pixel tests skip.
# Absence is reported, never worked around silently.
if [ "${1:-}" = "--capabilities" ]; then
  if command -v python3 >/dev/null 2>&1; then
    echo "CAP python $(python3 -c 'import platform; print(platform.python_version())')"
  else
    echo "MISSING python (python3 not on PATH)"
    echo "SKIP-RENDER playwright unavailable (no python3)"
    echo "SKIP-IMAGE pillow unavailable (no python3)"
    exit 0
  fi
  if python3 -c 'import PIL' >/dev/null 2>&1; then
    echo "CAP pillow $(python3 -c 'import PIL; print(PIL.__version__)')"
  else
    echo "SKIP-IMAGE pillow not importable (pixel tests skip)"
  fi
  if python3 -c 'import playwright' >/dev/null 2>&1; then
    echo "CAP playwright $(python3 -c 'import importlib.metadata as m; print(m.version("playwright"))' 2>/dev/null || echo present)"
    CHROME_BIN="$(python3 -c 'from playwright.sync_api import sync_playwright
with sync_playwright() as p: print(p.chromium.executable_path)' 2>/dev/null || true)"
    if [ -n "$CHROME_BIN" ] && [ -x "$CHROME_BIN" ]; then
      echo "CAP chromium $CHROME_BIN"
    else
      echo "SKIP-RENDER playwright present but its chromium executable is missing"
    fi
  else
    echo "SKIP-RENDER playwright not importable (render tests skip)"
  fi
  if command -v fc-list >/dev/null 2>&1; then
    echo "CAP fonts $(fc-list | wc -l | tr -d ' ') fontconfig entries"
  else
    echo "CAP fonts UNKNOWN (fontconfig fc-list unavailable)"
  fi
  exit 0
fi

for f in \
  SKILL.md skill-version.txt MASTERDOC.md INSTRUCTIONS.md INSTALL.md QC.md REPO-INTEGRATION.md \
  references/authority-map.md \
  references/BlackCEO-Signature-Landing-Page-Production-and-QC-SOP-v1.md \
  references/BlackCEO-Signature-Landing-Page-Standard-v6.md \
  references/BlackCEO-Signature-Landing-Page-Long-Form-v6.md \
  references/BlackCEO-Signature-Image-Intelligence-and-Prompt-Creation-Guide-v5.md \
  references/BlackCEO-Famous-Photographers-DNA-Style-Library-v1.1.md \
  references/BlackCEO-Cinematic-Image-Style-Systems-v2.0.md \
  references/BlackCEO-Visual-Artists-AI-Style-Intelligence-Guide-v1.0.md \
  assets/BlackCEO-Master-Visual-Reference-Guide.png \
  scripts/validate_state.py scripts/validate_prompt.py scripts/validate_image_manifest.py \
  scripts/validate_public_copy.py scripts/combine_review_pdf.py scripts/validate_review_pdf.py \
  scripts/stage_gate.py scripts/render_page.py scripts/compare_sheet.py \
  scripts/validate_page.py scripts/validate_visual_direction.py scripts/validate_image_grade.py \
  scripts/calibrate_grade.py scripts/check_authority_pins.py \
  scripts/install_local.py scripts/write_intake.py scripts/brand_colors.py \
  scripts/circle_image.py scripts/design_style.py \
  tests/run_tests.py tests/test_scripts.py \
  assets/brand/blackceo-brand.json assets/brand/brand.schema.json \
  assets/brand/client-brand.template.json assets/brand/signature-grade-block.txt \
  assets/page-references/README.md \
  assets/visual-standards/README.md assets/visual-standards/ANALYSIS.md assets/visual-standards/manifest.json \
  references/BlackCEO-Page-Brand-Law.md references/stage-contract.json \
  references/swarm-plan.md references/html-qc-rubric.md references/private-label-list.txt \
  references/external-authorities.json \
  assets/brand/gold-set/README.md assets/brand/gold-set/gold-set.json \
  CHANGELOG.md VERSION START-HERE.md EVALUATION-CHECKLIST.md \
  references/runtime-adapters.md references/kie-generation-route.md agents/openai.yaml \
  scripts/swarm_runner.py scripts/browser_sessions.py scripts/ship_run_events.py \
  scripts/reference_use.py references/reference-image-use.md references/reference-library.json \
  scripts/hypersaturation.py scripts/validate_page_color.py \
  references/hypersaturation-framework.md references/page-color-thresholds.json \
  scripts/validate_copy_structure.py scripts/validate_install.py \
  scripts/validate_funnel_completion.py scripts/check_deliverables.py \
  references/run-events-schema.md references/run-events.schema.json \
  references/run-events.example.jsonl references/report-json.schema.json \
  references/report-json.example.json references/style-selection.md \
  references/design-styles.md references/design-styles.json tests/test_design_style.py \
  references/style-selection.schema.json references/prompt-budget-policy.json \
  references/runner-profiles.json references/item-gate-spec.md \
  references/browser-hygiene.md references/funnel-completion-checklist.md \
  references/browser-engine-contract.md references/automation-handoff.md \
  references/deliverables-manifest.md references/layout-trait-vocabulary.json \
  references/composition-treatments.json references/composition-patterns.md \
  scripts/composition.py assets/visual-standards/reference-catalog.json \
  tests/test_composition_library.py \
  references/copy-specs/standard-v6.json references/copy-specs/long-form-v6.json \
  references/wireframe-build-spec.json scripts/wireframe_spec.py \
  tests/docker/Dockerfile \
  adapters/claude-code/README.md adapters/claude-nine/README.md adapters/codex/README.md \
  repo-integration/skill-department-map-entry.json \
  repo-integration/universal-sops/signature-page-craft/README.md; do
  need_file "$f"
done

# Fix 11.1: every standard image named by the manifest is a required file.
# A shell loop over manifest.json's files[].file keeps this from being 44
# hand-typed lines; one fix only, no shell-out to test_visual_standards.py.
VS_LIST="$(python3 - "$ROOT/assets/visual-standards/manifest.json" <<'VSPYEOF'
import json, sys
with open(sys.argv[1], encoding="utf-8") as fh:
    for entry in json.load(fh)["files"]:
        print(entry["file"])
VSPYEOF
)" || { printf '[FAIL] cannot read assets/visual-standards/manifest.json\n' >&2; fail=1; VS_LIST=""; }
if [ -z "$VS_LIST" ]; then
  printf '[FAIL] assets/visual-standards/manifest.json lists no image files\n' >&2
  fail=1
else
  while IFS= read -r vs_file; do
    [ -n "$vs_file" ] && need_file "assets/visual-standards/$vs_file"
  done <<VSLISTEOF
$VS_LIST
VSLISTEOF
fi

front_ver="$(awk 'BEGIN{x=0} /^---$/{x++; next} x==1 && /^version:/{sub(/^version:[[:space:]]*/,""); print; exit}' "$ROOT/SKILL.md" | tr -d '"\r')"
file_ver="$(tr -d 'vV\r[:space:]' < "$ROOT/skill-version.txt")"
front_ver="${front_ver#v}"
if [ "$front_ver" = "$file_ver" ] && [ -n "$front_ver" ]; then
  echo "[PASS] version lockstep $front_ver"
else
  echo "[FAIL] SKILL.md version '$front_ver' != skill-version.txt '$file_ver'" >&2
  fail=1
fi

for f in "$ROOT"/scripts/*.py; do
  if python3 -m py_compile "$f" 2>/dev/null; then
    echo "[PASS] python syntax $(basename "$f")"
  else
    echo "[FAIL] python syntax $(basename "$f")" >&2
    fail=1
  fi
done

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
# KIE prompt rule 12 (1.2.4): fixtures are small on purpose and are grown into the
# model's length band by tests/fit_prompt.py — same as tests/run_tests.py.
if python3 - "$ROOT" "$TMP" <<'PYEOF' >/dev/null 2>&1
import sys
sys.path.insert(0, sys.argv[1] + "/tests")
import fit_prompt
fit_prompt.fit_file(sys.argv[1] + "/tests/fixtures/prompt_good.txt", sys.argv[2] + "/prompt_good_fitted.txt")
PYEOF
then
  if python3 "$ROOT/scripts/validate_prompt.py" "$TMP/prompt_good_fitted.txt" --sauce-only >/dev/null; then
    echo "[PASS] prompt validator sanity fixture"
  else
    echo "[FAIL] prompt validator sanity fixture" >&2
    fail=1
  fi
else
  echo "[FAIL] prompt validator sanity fixture (fit_prompt failed)" >&2
  fail=1
fi

printf 'Public headline\nPublic body copy\nApply Now\n' > "$TMP/public.md"
if python3 "$ROOT/scripts/validate_public_copy.py" "$TMP/public.md" >/dev/null; then
  echo "[PASS] public-copy validator sanity fixture"
else
  echo "[FAIL] public-copy validator sanity fixture" >&2
  fail=1
fi

# Pinned external authorities (Item 11): drift is a warning, never a
# failure here. PIN OK / PIN DRIFT / PIN MISSING lines print as-is.
if [ -f "$ROOT/scripts/check_authority_pins.py" ] && [ -f "$ROOT/references/external-authorities.json" ]; then
  python3 "$ROOT/scripts/check_authority_pins.py" || true
fi

# Cross-repo parity (Item 27): when the sibling repo's checkout is
# named, run the parity checker. In the onboarding repo set
# SKILL71_999_ROOT to a 999-setup checkout; in the 999 repo set
# SKILL71_ONB_ROOT to an onboarding checkout. Unset means this install
# is verified standalone and the section reports its skip by name.
PARITY_REPO_ROOT="$(cd "$ROOT/../.." && pwd)"
if [ -n "${SKILL71_999_ROOT:-}" ]; then
  if python3 "$PARITY_REPO_ROOT/scripts/check-skill71-parity.py" \
       --onb-root "$PARITY_REPO_ROOT" --nine-root "$SKILL71_999_ROOT"; then
    echo "[PASS] parity against 999 checkout $SKILL71_999_ROOT"
  else
    echo "[FAIL] parity against 999 checkout $SKILL71_999_ROOT" >&2
    fail=1
  fi
elif [ -n "${SKILL71_ONB_ROOT:-}" ]; then
  if python3 "$PARITY_REPO_ROOT/scripts/check-skill71-parity.py" \
       --onb-root "$SKILL71_ONB_ROOT" --nine-root "$PARITY_REPO_ROOT"; then
    echo "[PASS] parity against onboarding checkout $SKILL71_ONB_ROOT"
  else
    echo "[FAIL] parity against onboarding checkout $SKILL71_ONB_ROOT" >&2
    fail=1
  fi
else
  echo "[SKIP] parity: neither SKILL71_999_ROOT nor SKILL71_ONB_ROOT is set"
fi

if [ "$fail" -eq 0 ]; then
  if python3 "$ROOT/tests/run_tests.py" >/dev/null 2>&1; then
    echo "[PASS] tests/run_tests.py"
  else
    echo "[FAIL] tests/run_tests.py" >&2
    fail=1
  fi
fi

if [ "$fail" -eq 0 ]; then
  echo "SKILL 71 VERIFY PASS"
  exit 0
fi

echo "SKILL 71 VERIFY FAIL" >&2
exit 1

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
  scripts/install_local.py \
  tests/run_tests.py tests/test_scripts.py \
  assets/brand/blackceo-brand.json assets/brand/brand.schema.json \
  assets/brand/client-brand.template.json assets/brand/signature-grade-block.txt \
  assets/page-references/README.md \
  references/BlackCEO-Page-Brand-Law.md references/stage-contract.json \
  references/swarm-plan.md references/html-qc-rubric.md references/private-label-list.txt \
  CHANGELOG.md VERSION START-HERE.md EVALUATION-CHECKLIST.md \
  references/runtime-adapters.md agents/openai.yaml \
  adapters/claude-code/README.md adapters/claude-nine/README.md adapters/codex/README.md \
  repo-integration/skill-department-map-entry.json \
  repo-integration/universal-sops/signature-page-craft/README.md; do
  need_file "$f"
done

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
if python3 "$ROOT/scripts/validate_prompt.py" "$ROOT/tests/fixtures/prompt_good.txt" --runtime-max 19000 --sauce-only >/dev/null; then
  echo "[PASS] prompt validator sanity fixture"
else
  echo "[FAIL] prompt validator sanity fixture" >&2
  fail=1
fi

printf 'Public headline\nPublic body copy\nApply Now\n' > "$TMP/public.md"
if python3 "$ROOT/scripts/validate_public_copy.py" "$TMP/public.md" >/dev/null; then
  echo "[PASS] public-copy validator sanity fixture"
else
  echo "[FAIL] public-copy validator sanity fixture" >&2
  fail=1
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

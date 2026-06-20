#!/usr/bin/env bash
# ============================================================================
# Materialize the two CI test fixtures for the Department Class-Kit gate.
#   GOOD fixture: a minimal department kit that PASSES Gates A / B / D
#                 (real 20-slide .pptx, all required files + counts, no
#                  placeholder language). Notion (Gate C) is not exercised.
#   BAD  fixture: a text-only 7-section stub with deferral language — the
#                 exact 33-failure signature that must AUTO-FAIL.
#
# Generic department documentation only — NO client names anywhere.
# Builds tiny placeholder artifacts (a few bytes each) so nothing heavy is
# committed to the repo; the gate is mechanical and only checks
# existence / counts / slide-xml count / language, not pixel content.
#
# USAGE: make-class-kit-fixtures.sh <out-dir>
#   produces <out-dir>/good-kit  and  <out-dir>/bad-kit
# ============================================================================
set -euo pipefail

OUT="${1:?usage: make-class-kit-fixtures.sh <out-dir>}"
GOOD="$OUT/good-kit"
BAD="$OUT/bad-kit"
ROLE_N=12   # generic department with 12 roles

rm -rf "$GOOD" "$BAD"
mkdir -p "$GOOD/renders-light" "$GOOD/micro-infographics/working" \
         "$GOOD/infographics" "$GOOD/deck" "$BAD"

# ---------------------------------------------------------------------------
# GOOD fixture
# ---------------------------------------------------------------------------

# A.0 master index
cat > "$GOOD/00-DELIVERY-PACKAGE-INDEX.md" <<EOF
# EXAMPLE DEPARTMENT — FINAL DELIVERY PACKAGE
Teaching order: deck -> speech -> teleprompter -> deluxe reference ->
8 topic PDFs -> 4 cheatsheets -> brand spec -> render prompts.
Package summary: 1 primary deck, 1 speech + 1 teleprompter, 20 PNGs + 20 prompts,
10 PDFs, 4 cheatsheets, micro-infographics, brand + prompt files.
EOF

# A.1 — 8 module .html + 8 module .pdf
mods=( "01-Getting-Started" "02-The-${ROLE_N}-Roles" "03-The-SOP-Rulebook" \
       "04-The-4-Presentation-Types" "05-The-Build-Pipeline" "06-The-Quality-Gates" \
       "07-The-Final-Package" "08-Intelligence-Engines" )
for m in "${mods[@]}"; do
  printf '<!doctype html><title>%s</title><h1>%s</h1><p>Generic module content.</p>' "$m" "$m" > "$GOOD/$m.html"
  printf '%%PDF-1.4\n%% minimal placeholder pdf for %s\n%%%%EOF\n' "$m" > "$GOOD/$m.pdf"
done

# A.2 — compact + DELUXE PDF + DELUXE HTML  (=> 10 PDFs total)
printf '%%PDF-1.4\n%% compact reference\n%%%%EOF\n'  > "$GOOD/Example-Department-Class-Reference.pdf"
printf '%%PDF-1.4\n%% deluxe reference\n%%%%EOF\n'   > "$GOOD/Example-Department-Class-Reference-DELUXE.pdf"
printf '<!doctype html><title>DELUXE</title><h1>The Complete Class Guide</h1>' > "$GOOD/Example-Department-Class-Reference-DELUXE.html"

# A.3 — primary deck .pptx with EXACTLY 20 slides (real zip, slideN.xml entries)
python3 - "$GOOD/deck/Example-Dept-LIGHT-${ROLE_N}.pptx" <<'PYEOF'
import sys, zipfile
path = sys.argv[1]
with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
    z.writestr("[Content_Types].xml",
               '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
    z.writestr("ppt/presentation.xml",
               '<?xml version="1.0"?><p:presentation xmlns:p="x"/>')
    for i in range(1, 21):  # 20 slides -> passes Gate B (>= 20)
        z.writestr(f"ppt/slides/slide{i}.xml",
                   f'<?xml version="1.0"?><p:sld xmlns:p="x"><!-- slide {i} --></p:sld>')
print("deck written:", path)
PYEOF

# A.4 — 20 slide PNGs + 20 slide PROMPTs + kie_task_ids.json
for i in $(seq -w 1 20); do
  printf 'PNG-placeholder slide %s' "$i" > "$GOOD/renders-light/slide-$i.png"
  printf 'Verbatim Kie.ai prompt for slide %s (light background, on-brand).' "$i" > "$GOOD/renders-light/slide-$i-PROMPT.txt"
done
printf '{"slides": "task-id log placeholder"}' > "$GOOD/renders-light/kie_task_ids.json"

# A.5 — speech + teleprompter
printf '# Example Department Speech\nWord-for-word speaker script for all 20 slides.\n' > "$GOOD/HOWTO-Example-SPEECH.md"
printf '<!doctype html><title>Teleprompter</title><div id="tele">Auto-scrolling teleprompter app.</div>' > "$GOOD/HOWTO-Example-teleprompter.html"

# A.6 — 4 cheatsheet PNGs + 4 cheatsheet PROMPTs (in infographics/)
cheats=( "1-roles" "2-sops" "3-types" "4-pipeline" )
for c in "${cheats[@]}"; do
  printf 'PNG-placeholder cheatsheet %s' "$c" > "$GOOD/infographics/cheatsheet-$c.png"
  printf 'Kie.ai prompt for cheatsheet %s (portrait 2K, light).' "$c" > "$GOOD/infographics/cheatsheet-$c-PROMPT.txt"
done

# A.7 — micro-infographics: fixed concept set + one-per-role (>= ROLE_N), 1:1 PNG/PROMPT
micros=( "01-what-it-is" "02-getting-started" "03-approval-gate" "04-pipeline-glance" \
         "05-phase-research" "06-phase-copy" "07-phase-design" "08-phase-prompts" \
         "09-phase-render" "10-phase-finish" )
for r in $(seq -w 1 ${ROLE_N}); do micros+=( "role-$r" ); done
micros+=( "sop-1" "sop-2" "sop-3" "sop-4" "types" "final-package" )
for mi in "${micros[@]}"; do
  printf 'PNG-placeholder micro %s' "$mi" > "$GOOD/micro-infographics/$mi.png"
  printf 'Kie.ai prompt for micro %s (16:9 2K, light).' "$mi" > "$GOOD/micro-infographics/$mi-PROMPT.txt"
done
printf '{"micros": "task-id log placeholder"}' > "$GOOD/micro-infographics/working/kie_task_ids.json"

# A.8 — brand spec + render-prompt master
cat > "$GOOD/BRAND-COLOR-SPEC.md" <<'EOF'
# BRAND COLOR SPEC
Light backgrounds mandatory. Palette: #FBFBF9, #14233F, #1F9D9A, #C8963E, #3A4A63.
Reusable Kie.ai gpt-image-2 style directive + aspect/resolution quick-reference.
EOF
printf '# %s-Slide Render Prompts\nAll verbatim slide prompts.\n' "20" > "$GOOD/${ROLE_N}-SLIDE-RENDER-PROMPTS.md"

# ---------------------------------------------------------------------------
# BAD fixture — text-only 7-section stub with deferral language (must AUTO-FAIL)
# ---------------------------------------------------------------------------
cat > "$BAD/department-page.md" <<'EOF'
# Example Department

## 1. Overview
This department does things.

## 2. Roles
A list of roles.

## 3. SOP Library
The SOPs.

## 4. Workflow
The pipeline.

## 5. Visuals
Infographics are generated in Phase 1 and embedded here as public-URL images.
The org chart will be added here. Add the PowerPoint file once rendered.

## 6. Signature Presentation
The signature deck is queued for Phase 1b. A slide-by-slide summary will be
added here. Sample slide imagery go here.

## 7. Outputs
The outputs list.
EOF

echo "fixtures built under: $OUT"
echo "  GOOD: $GOOD"
echo "  BAD : $BAD"

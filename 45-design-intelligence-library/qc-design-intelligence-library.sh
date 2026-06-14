#!/bin/bash

# QC Script for Skill 45 — Design Intelligence Library
# Verifies: 19 library files present (7 _system + 9 _RULES + 3 top-level), INDEX.md parses, no client data committed to repo
# Top-level repo-owned library files: README.md, INDEX.md (empty seed), DEPARTMENT-BUILD-BRIEF.md (org-builder brief).
# Client data = {ID}_{name}.md style cards and personal-photo-shoot/{client}/ identity folders ONLY.
# Category _RULES.md are repo-owned system files and are NEVER client data.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LIBRARY_DIR="$SCRIPT_DIR/library"

echo "[QC] Design Intelligence Library (Skill 45)"
echo "[QC] Library root: $LIBRARY_DIR"
echo ""

# 1. Verify system files exist (7 files under _system/)
echo "[QC] Checking _system/ files..."
_system_files=(
  "MASTER-SOP.md"
  "MODEL-SPECS.md"
  "NEGATIVE-PROMPTING-SOP.md"
  "PHOTO-SHOOT-SOP.md"
  "PPT-ANALYSIS-SOP.md"
  "STYLE-CARD-TEMPLATE.md"
  "TEST-PROTOCOL.md"
)

for file in "${_system_files[@]}"; do
  if [[ -f "$LIBRARY_DIR/_system/$file" ]]; then
    echo "  ✓ _system/$file"
  else
    echo "  ✗ MISSING: _system/$file"
    exit 1
  fi
done

# 2. Verify category _RULES.md files exist (9 files)
echo ""
echo "[QC] Checking category _RULES.md files..."
categories=(
  "advertisement-designs"
  "banner-designs"
  "book-cover-designs"
  "facebook-ad-designs"
  "magazine-cover-designs"
  "personal-photo-shoot"
  "powerpoint-designs"
  "single-image-designs"
  "social-media-designs"
)

for cat in "${categories[@]}"; do
  if [[ -f "$LIBRARY_DIR/$cat/_RULES.md" ]]; then
    echo "  ✓ $cat/_RULES.md"
  else
    echo "  ✗ MISSING: $cat/_RULES.md"
    exit 1
  fi
done

# 3. Verify top-level repo-owned library files exist (3 files)
echo ""
echo "[QC] Checking top-level library files..."
for file in "README.md" "INDEX.md" "DEPARTMENT-BUILD-BRIEF.md"; do
  if [[ -f "$LIBRARY_DIR/$file" ]]; then
    echo "  ✓ $file"
  else
    echo "  ✗ MISSING: $file"
    exit 1
  fi
done

# 4. Verify INDEX.md is valid markdown and parses
echo ""
echo "[QC] Validating INDEX.md..."
if grep -q "# DESIGN LIBRARY — MASTER INDEX" "$LIBRARY_DIR/INDEX.md"; then
  echo "  ✓ INDEX.md has expected header"
else
  echo "  ✗ INDEX.md header missing or malformed"
  exit 1
fi

if grep -q "## SINGLE IMAGE DESIGNS" "$LIBRARY_DIR/INDEX.md"; then
  echo "  ✓ INDEX.md has category tables"
else
  echo "  ✗ INDEX.md category tables missing"
  exit 1
fi

# 5. Check for client data accidentally committed
echo ""
echo "[QC] Checking for committed client data (should be empty)..."
# Client data is box-owned, never in the repo. It is ONLY:
#   (a) style-card files named {ID}_{name}.md inside a category folder, and
#   (b) per-client identity folders under personal-photo-shoot/{client}/.
# Repo-owned _RULES.md files are SYSTEM files and must NEVER be counted as client data.
client_data_count=0
client_data_files=()

# (a) Style cards: any .md in a category folder that is NOT _RULES.md.
while IFS= read -r f; do
  client_data_files+=("$f")
  ((client_data_count++)) || true
done < <(find "$LIBRARY_DIR"/*designs "$LIBRARY_DIR/personal-photo-shoot" \
            -maxdepth 1 -type f -name "*.md" ! -name "_RULES.md" 2>/dev/null)

# (b) Per-client identity folders under personal-photo-shoot/ (any subdirectory).
while IFS= read -r d; do
  client_data_files+=("$d/")
  ((client_data_count++)) || true
done < <(find "$LIBRARY_DIR/personal-photo-shoot" -mindepth 1 -maxdepth 1 -type d 2>/dev/null)

if [[ $client_data_count -eq 0 ]]; then
  echo "  ✓ No committed client data (style cards, identity profiles) — good"
else
  echo "  ⚠ Warning: $client_data_count potential client-data file(s)/folder(s) found (expected only if the skill is already installed on a box):"
  for item in "${client_data_files[@]}"; do
    echo "      - ${item#$LIBRARY_DIR/}"
  done
fi

# 6. File count summary
echo ""
echo "[QC] Library file count:"
system_count=$(find "$LIBRARY_DIR/_system" -name "*.md" | wc -l)
rules_count=$(find "$LIBRARY_DIR" -path "*/_RULES.md" | wc -l)
toplevel_count=$(find "$LIBRARY_DIR" -maxdepth 1 -name "*.md" | wc -l)
echo "  System files (_system/*.md): $system_count (expected: 7)"
echo "  Category _RULES.md: $rules_count (expected: 9)"
echo "  Top-level files (README, INDEX, DEPARTMENT-BUILD-BRIEF): $toplevel_count (expected: 3)"

expected_total=$((system_count + rules_count + toplevel_count))
echo "  Total library files: $expected_total (expected: 19)"

if [[ $system_count -ne 7 ]] || [[ $rules_count -ne 9 ]] || [[ $toplevel_count -ne 3 ]]; then
  echo "  ✗ File count mismatch"
  exit 1
fi

# 7. Verify no spaces in category directory names (kebab-case)
echo ""
echo "[QC] Verifying kebab-case directory names..."
bad_names=()
for dir in "$LIBRARY_DIR"/*; do
  if [[ -d "$dir" ]]; then
    dirname=$(basename "$dir")
    if [[ $dirname == *" "* ]]; then
      bad_names+=("$dirname")
    fi
  fi
done

if [[ ${#bad_names[@]} -eq 0 ]]; then
  echo "  ✓ All directory names are kebab-case (no spaces)"
else
  echo "  ✗ Found directories with spaces: ${bad_names[*]}"
  exit 1
fi

echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "[QC] ✓ All checks passed. Design Intelligence Library (v1.0.0)"
echo "[QC] 19 library files present + valid structure (7 _system + 9 _RULES + 3 top-level)"
echo "[QC] Ready for installation on boxes"
echo "═══════════════════════════════════════════════════════════════"

exit 0

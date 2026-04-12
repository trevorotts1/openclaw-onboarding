#!/bin/bash
# Skill 23 Validation Script
# Validates that all required files and sections are present

set -e

SKILL_DIR="$(dirname "$0")/.."
ERRORS=0

echo "=== Skill 23 AI Workforce Blueprint Validation ==="
echo ""

# Check required files exist
echo "Checking required files..."
REQUIRED_FILES=(
    "SKILL.md"
    "INSTALL.md"
    "INSTRUCTIONS.md"
    "EXAMPLES.md"
    "CORE_UPDATES.md"
    "ai-workforce-blueprint-full.md"
    "skill-version.txt"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [ -f "$SKILL_DIR/$file" ]; then
        echo "  ✓ $file exists"
    else
        echo "  ✗ $file MISSING"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
echo "Checking SKILL.md sections..."

# Check SKILL.md has required sections
REQUIRED_SECTIONS=(
    "Memory Wiki Integration"
    "Interview Persistence Protocol"
    "5-Layer Persona Alignment"
    "Act As If Protocol"
)

for section in "${REQUIRED_SECTIONS[@]}"; do
    if grep -q "$section" "$SKILL_DIR/SKILL.md"; then
        echo "  ✓ Section: $section"
    else
        echo "  ✗ Section MISSING: $section"
        ERRORS=$((ERRORS + 1))
    fi
done

echo ""
echo "Checking for memory-core references..."
MEMORY_CORE_REFS=$(grep -ri "memory-core" "$SKILL_DIR" --include="*.md" --include="*.txt" 2>/dev/null | wc -l | tr -d ' ')
if [ "$MEMORY_CORE_REFS" -ge 1 ]; then
    echo "  ✓ memory-core references found: $MEMORY_CORE_REFS"
else
    echo "  ✗ No memory-core references found (should have at least 1)"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "Checking version format..."
VERSION=$(head -1 "$SKILL_DIR/skill-version.txt" 2>/dev/null | tr -d '\n')
if echo "$VERSION" | grep -qE '^v[0-9]+\.[0-9]+\.[0-9]+$'; then
    echo "  ✓ Version format valid: $VERSION"
else
    echo "  ✗ Version format invalid: $VERSION"
    ERRORS=$((ERRORS + 1))
fi

echo ""
echo "=== Validation Complete ==="
if [ $ERRORS -eq 0 ]; then
    echo "✓ All checks passed"
    exit 0
else
    echo "✗ $ERRORS error(s) found"
    exit 1
fi
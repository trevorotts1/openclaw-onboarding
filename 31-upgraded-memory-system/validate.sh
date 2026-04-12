#!/bin/bash
# Validation script for Skill 31: Upgraded Memory System (8-Layer)

echo "=== Skill 31 Validation ==="
echo ""

SKILL_DIR="${HOME}/.openclaw/skills/31-upgraded-memory-system"
[ -d "$SKILL_DIR" ] || SKILL_DIR="${HOME}/.openclaw/skills/upgraded-memory-system"
[ -d "$SKILL_DIR" ] || SKILL_DIR="$(dirname "$0")"

echo "Skill directory: $SKILL_DIR"
echo ""

# Section 1: File Structure
echo "=== Section 1: File Structure ==="
REQUIRED_FILES="SKILL.md INSTALL.md INSTRUCTIONS.md EXAMPLES.md CORE_UPDATES.md FULL-DOC.md HOW-YOUR-MEMORY-WORKS.md QC.md MIGRATION-FROM-MEM0.md skill-version.txt"
for f in $REQUIRED_FILES; do
  [ -f "$SKILL_DIR/$f" ] && echo "PASS: $f" || echo "FAIL: $f missing"
done

if [ -f "$SKILL_DIR/skill-version.txt" ]; then
  echo "Version: $(cat "$SKILL_DIR/skill-version.txt")"
fi
echo ""

# Section 2: 8-Layer References
echo "=== Section 2: 8-Layer Content Check ==="
LAYER8_COUNT=$(grep -c "8-Layer\|8 layer\|eight layer" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "8-layer references in SKILL.md: $LAYER8_COUNT"

MEMORY_CORE_COUNT=$(grep -c "memory-core" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "memory-core references in SKILL.md: $MEMORY_CORE_COUNT"

COGNEE_COUNT=$(grep -c "Cognee" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "Cognee references in SKILL.md: $COGNEE_COUNT"

OBSIDIAN_COUNT=$(grep -c "Obsidian" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "Obsidian references in SKILL.md: $OBSIDIAN_COUNT"

WIKI_COUNT=$(grep -c "Wiki System\|Wiki System" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "Wiki System references in SKILL.md: $WIKI_COUNT"
echo ""

# Section 3: Memory-Core Verification
echo "=== Section 3: Memory-Core Verification ==="
MEMORY_CORE=$(grep -c "memory-core" "$SKILL_DIR/SKILL.md" 2>/dev/null || echo "0")
echo "memory-core references in SKILL.md: $MEMORY_CORE (should be >= 1)"

if [ "$MEMORY_CORE" -ge 1 ]; then
  echo "PASS: memory-core properly referenced"
else
  echo "WARNING: SKILL.md missing memory-core references"
fi
echo ""

# Section 4: Version Check
echo "=== Section 4: Version Check ==="
VERSION=$(cat "$SKILL_DIR/skill-version.txt" 2>/dev/null || echo "unknown")
echo "Current version: $VERSION"
if [ "$VERSION" = "v7.0.0" ]; then
  echo "PASS: Version is v7.0.0 (8-layer upgrade)"
else
  echo "FAIL: Expected v7.0.0"
fi
echo ""

# Section 5: Migration Guide Check
echo "=== Section 5: Migration Guide Check ==="
if [ -f "$SKILL_DIR/MIGRATION-FROM-MEM0.md" ]; then
  echo "PASS: MIGRATION-FROM-MEM0.md exists"
  MIGRATION_SECTIONS=$(grep -c "^##" "$SKILL_DIR/MIGRATION-FROM-MEM0.md" 2>/dev/null || echo "0")
  echo "Migration guide sections: $MIGRATION_SECTIONS"
else
  echo "FAIL: MIGRATION-FROM-MEM0.md missing"
fi
echo ""

echo "=== Validation Complete ==="

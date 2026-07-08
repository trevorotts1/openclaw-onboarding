#!/bin/bash

# QC Script for Skill 45 — Design Intelligence Library
# Verifies: 20 library files present (7 _system + 10 _RULES + 3 top-level), INDEX.md parses, no client data committed to repo
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

# 2. Verify category _RULES.md files exist (10 files)
echo ""
echo "[QC] Checking category _RULES.md files..."
categories=(
  "advertisement-designs"
  "banner-designs"
  "book-cover-designs"
  "facebook-ad-designs"
  "funnel-page-designs"
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
# Count only the top-level _system protocol files (7). Nested sidecars like
# _system/templates/NAMED-STYLES.md are client-data SEED TEMPLATES, not protocol
# files, so -maxdepth 1 keeps the count at the documented 7.
system_count=$(find "$LIBRARY_DIR/_system" -maxdepth 1 -name "*.md" | wc -l)
rules_count=$(find "$LIBRARY_DIR" -path "*/_RULES.md" | wc -l)
toplevel_count=$(find "$LIBRARY_DIR" -maxdepth 1 -name "*.md" | wc -l)
echo "  System files (_system/*.md): $system_count (expected: 7)"
echo "  Category _RULES.md: $rules_count (expected: 10)"
echo "  Top-level files (README, INDEX, DEPARTMENT-BUILD-BRIEF): $toplevel_count (expected: 3)"

expected_total=$((system_count + rules_count + toplevel_count))
echo "  Total library files: $expected_total (expected: 20)"

if [[ $system_count -ne 7 ]] || [[ $rules_count -ne 10 ]] || [[ $toplevel_count -ne 3 ]]; then
  echo "  ✗ File count mismatch"
  exit 1
fi

# 6b. Clobber-safety: a populated (box-owned) INDEX.md MUST survive a re-install.
# The two-zone contract (SKILL.md) claims the installer cannot clobber a populated
# INDEX.md. Prove it: seed a sentinel INDEX.md in a temp home, re-run the documented
# client-data seed (INSTALL.md Step 4 — `cp -n` semantics), and assert the sentinel
# survived byte-for-byte.
echo ""
echo "[QC] Clobber-safety test (populated INDEX.md survives re-install)..."
CLOBBER_TMP="$(mktemp -d)"
trap 'rm -rf "$CLOBBER_TMP"' EXIT
cat > "$CLOBBER_TMP/INDEX.md" <<'SENTINEL'
# DESIGN LIBRARY — MASTER INDEX
<!-- QC-CLOBBER-SENTINEL: box-owned, populated at runtime; MUST survive re-install -->

## SINGLE IMAGE DESIGNS
| ID | Name | Sig # | Summary | Status | Version | Date | File |
|---|---|---|---|---|---|---|---|
| SI-001 | sentinel-card | 1 | do-not-clobber | production | 1.0.0 | 2026-07-05 | single-image-designs/SI-001_sentinel.md |
SENTINEL
sentinel_before="$(shasum "$CLOBBER_TMP/INDEX.md" | awk '{print $1}')"
# Re-run the documented client-data seed exactly as INSTALL.md Step 4 does it.
# NOTE: BSD `cp -n` exits non-zero when it (correctly) skips an existing target;
# survival is asserted below via the hash + sentinel marker, not via cp's exit code.
cp -n "$LIBRARY_DIR/INDEX.md" "$CLOBBER_TMP/INDEX.md" 2>/dev/null || true
sentinel_after="$(shasum "$CLOBBER_TMP/INDEX.md" | awk '{print $1}')"
if [[ "$sentinel_before" == "$sentinel_after" ]] && grep -q "QC-CLOBBER-SENTINEL" "$CLOBBER_TMP/INDEX.md"; then
  echo "  ✓ Populated INDEX.md survived re-seed (cp -n did not clobber the box copy)"
else
  echo "  ✗ CLOBBER: the installer overwrote a populated INDEX.md — two-zone contract broken"
  exit 1
fi
rm -rf "$CLOBBER_TMP"
trap - EXIT

# 6c. Validator gate self-tests (SK1-54/55/56): the coded gates were opt-in and
# previously exercised by NO test. Assert each subcommand's exit-code contract on
# fixtures so a regression (e.g. the "sales" archetype gap, or the fail-closed consent
# gate) fails QC. Requires python3 (the gates need it on-box at runtime anyway).
echo ""
echo "[QC] diu_validator.py gate self-tests..."
VALIDATOR="$SCRIPT_DIR/scripts/diu_validator.py"
if [[ ! -f "$VALIDATOR" ]]; then
  echo "  ✗ MISSING: scripts/diu_validator.py"; exit 1
elif ! command -v python3 >/dev/null 2>&1; then
  echo "  ⚠ python3 unavailable — skipping gate self-tests (gates run on-box at runtime)"
else
  GATE_TMP="$(mktemp -d)"
  trap 'rm -rf "$GATE_TMP"' EXIT
  gate() { # gate "<label>" <expected_rc> <cmd...>
    local label="$1" want="$2"; shift 2
    local got=0; "$@" >/dev/null 2>&1 || got=$?
    if [[ "$got" == "$want" ]]; then
      echo "  ✓ $label (exit $got)"
    else
      echo "  ✗ $label: expected exit $want, got $got"; exit 1
    fi
  }
  gate "route-check webinar -> interlock"    2 python3 "$VALIDATOR" route-check --deck-kind webinar
  gate "route-check sales deck -> interlock"  2 python3 "$VALIDATOR" route-check --deck-kind "sales deck"
  gate "route-check funnel -> interlock"     2 python3 "$VALIDATOR" route-check --deck-kind funnel
  gate "route-check brand -> DIU-routable"    0 python3 "$VALIDATOR" route-check --deck-kind brand
  gate "prompt-caps SHORT within cap -> ok"   0 python3 "$VALIDATOR" prompt-caps --tier SHORT --prompt "hi"
  gate "prompt-caps SHORT over cap -> fail"   3 python3 "$VALIDATOR" prompt-caps --tier SHORT --prompt "$(python3 -c 'print("x"*600)')"
  printf '# IDENTITY — Adult\n- Consent: granted\n- Consent date: 2026-01-15\n- Minor: no\n- Storage protection: encrypted-at-rest\n' > "$GATE_TMP/id-ok.md"
  printf '# IDENTITY — Minor\n- Consent: granted\n- Consent date: 2026-01-15\n- Minor: yes\n- Storage protection: encrypted-at-rest\n' > "$GATE_TMP/id-minor.md"
  printf '# IDENTITY — NoConsent\n- Minor: no\n- Storage protection: encrypted-at-rest\n' > "$GATE_TMP/id-noconsent.md"
  printf '# IDENTITY — Plaintext\n- Consent: granted\n- Consent date: 2026-01-15\n- Minor: no\n' > "$GATE_TMP/id-plaintext.md"
  gate "consent-check compliant adult -> ok"    0 python3 "$VALIDATOR" consent-check --identity-file "$GATE_TMP/id-ok.md"
  gate "consent-check MINOR -> hard no"          4 python3 "$VALIDATOR" consent-check --identity-file "$GATE_TMP/id-minor.md"
  gate "consent-check missing consent -> fail"   4 python3 "$VALIDATOR" consent-check --identity-file "$GATE_TMP/id-noconsent.md"
  gate "consent-check unprotected PII -> fail"   4 python3 "$VALIDATOR" consent-check --identity-file "$GATE_TMP/id-plaintext.md"
  gate "consent-check missing file -> fail"      4 python3 "$VALIDATOR" consent-check --identity-file "$GATE_TMP/nope.md"
  rm -rf "$GATE_TMP"
  trap - EXIT
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
SKILL_VERSION="$(cat "$SCRIPT_DIR/skill-version.txt" 2>/dev/null | tr -d '[:space:]')"
echo "[QC] ✓ All checks passed. Design Intelligence Library (v${SKILL_VERSION:-unknown})"
echo "[QC] 20 library files present + valid structure (7 _system + 10 _RULES + 3 top-level)"
echo "[QC] Ready for installation on boxes"
echo "═══════════════════════════════════════════════════════════════"

exit 0

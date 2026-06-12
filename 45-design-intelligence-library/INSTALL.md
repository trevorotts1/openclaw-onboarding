# Skill 45 Installation — Design Intelligence Library

## The two-zone seeding contract (read this first)

The DIU library has two zones with different update semantics:

| Zone | Files | Ownership | Seeded | Updated |
|---|---|---|---|---|
| **System** | `_system/*` + every `_RULES.md` in categories | Repo | Once via installer | Every `update-skills.sh` run (rsync) |
| **Client Data** | `INDEX.md`, style cards (`{ID}_{name}.md`), `personal-photo-shoot/{client}/` folders | Box | Once via installer (`cp -n`) | Never (box owns all mutations) |

This contract ensures style cards and client identity profiles survive skill re-installation while keeping library rules and protocols current.

---

## Installation Steps

### Step 1: Verify Skill 07 (Kie.ai) is installed

```bash
openclaw config get env.vars.KIE_API_KEY
```

**If you see a key:** proceed to Step 2.

**If you see null or "not set":** Skill 07 is not yet installed or the key is not configured. 
- Run Skill 07 first: `bash $OC_ROOT/skills/07-kie-setup/install.sh`
- Then return to this installer.

Skill 45 requires Kie.ai credentials for image generation endpoints.

---

### Step 2: Create on-box library home (idempotent)

```bash
OC_ROOT="${OC_ROOT:-$HOME/.openclaw}"
LIBRARY_HOME="$OC_ROOT/master-files/design-library"

mkdir -p "$LIBRARY_HOME"
echo "[DIU] Library home: $LIBRARY_HOME"
```

---

### Step 3: Seed system files (repo-owned — always overwrite on update)

```bash
SKILL_DIR="$OC_ROOT/skills/45-design-intelligence-library"

# Copy all system files and category _RULES
rsync -av "$SKILL_DIR/library/_system/" "$LIBRARY_HOME/_system/"
rsync -av "$SKILL_DIR/library/advertisement-designs/" "$LIBRARY_HOME/advertisement-designs/"
rsync -av "$SKILL_DIR/library/banner-designs/" "$LIBRARY_HOME/banner-designs/"
rsync -av "$SKILL_DIR/library/book-cover-designs/" "$LIBRARY_HOME/book-cover-designs/"
rsync -av "$SKILL_DIR/library/facebook-ad-designs/" "$LIBRARY_HOME/facebook-ad-designs/"
rsync -av "$SKILL_DIR/library/magazine-cover-designs/" "$LIBRARY_HOME/magazine-cover-designs/"
rsync -av "$SKILL_DIR/library/personal-photo-shoot/" "$LIBRARY_HOME/personal-photo-shoot/"
rsync -av "$SKILL_DIR/library/powerpoint-designs/" "$LIBRARY_HOME/powerpoint-designs/"
rsync -av "$SKILL_DIR/library/single-image-designs/" "$LIBRARY_HOME/single-image-designs/"
rsync -av "$SKILL_DIR/library/social-media-designs/" "$LIBRARY_HOME/social-media-designs/"

echo "[DIU] System files and _RULES seeded"
```

---

### Step 4: Seed client-data zone (box-owned — idempotent, cp -n semantics)

```bash
# Copy INDEX.md only if it doesn't exist
cp -n "$SKILL_DIR/library/README.md" "$LIBRARY_HOME/README.md"
cp -n "$SKILL_DIR/library/INDEX.md" "$LIBRARY_HOME/INDEX.md"

echo "[DIU] Index seeded (idempotent)"

# Ensure category dirs exist for future style cards
for dir in advertisement-designs banner-designs book-cover-designs facebook-ad-designs magazine-cover-designs personal-photo-shoot powerpoint-designs single-image-designs social-media-designs; do
  mkdir -p "$LIBRARY_HOME/$dir"
done

echo "[DIU] Category directories ready for style cards"
```

---

### Step 5: Wire the library into Brainstorming Buddy — Graphics

The extended BB-graphics question bank now includes DIU-specific questions. These route to:
- Style Analyst (for "analyze" / "reference image" requests)
- Generation Operator (for "generate using style ID" requests)
- Photo Shoot Director (for likeness/consent requests)
- Deck Systems Specialist (for deck generation requests)

This is handled by the interview-time extension of `_brainstorming-buddy-question-banks.json` and the role library's BB-graphics edits. No manual wire-up needed.

---

### Step 6: Verification checklist

Run these checks to confirm a successful install:

```bash
OC_ROOT="${OC_ROOT:-$HOME/.openclaw}"
LIBRARY_HOME="$OC_ROOT/master-files/design-library"

# Verify system files exist
test -f "$LIBRARY_HOME/_system/MASTER-SOP.md" && echo "✓ MASTER-SOP.md" || echo "✗ MASTER-SOP.md missing"
test -f "$LIBRARY_HOME/_system/MODEL-SPECS.md" && echo "✓ MODEL-SPECS.md" || echo "✗ MODEL-SPECS.md missing"
test -f "$LIBRARY_HOME/_system/PHOTO-SHOOT-SOP.md" && echo "✓ PHOTO-SHOOT-SOP.md" || echo "✗ PHOTO-SHOOT-SOP.md missing"
test -f "$LIBRARY_HOME/_system/PPT-ANALYSIS-SOP.md" && echo "✓ PPT-ANALYSIS-SOP.md" || echo "✗ PPT-ANALYSIS-SOP.md missing"
test -f "$LIBRARY_HOME/_system/TEST-PROTOCOL.md" && echo "✓ TEST-PROTOCOL.md" || echo "✗ TEST-PROTOCOL.md missing"
test -f "$LIBRARY_HOME/_system/NEGATIVE-PROMPTING-SOP.md" && echo "✓ NEGATIVE-PROMPTING-SOP.md" || echo "✗ NEGATIVE-PROMPTING-SOP.md missing"
test -f "$LIBRARY_HOME/_system/STYLE-CARD-TEMPLATE.md" && echo "✓ STYLE-CARD-TEMPLATE.md" || echo "✗ STYLE-CARD-TEMPLATE.md missing"

# Verify category _RULES exist
for cat in advertisement-designs banner-designs book-cover-designs facebook-ad-designs magazine-cover-designs personal-photo-shoot powerpoint-designs single-image-designs social-media-designs; do
  test -f "$LIBRARY_HOME/$cat/_RULES.md" && echo "✓ $cat/_RULES.md" || echo "✗ $cat/_RULES.md missing"
done

# Verify INDEX exists
test -f "$LIBRARY_HOME/INDEX.md" && echo "✓ INDEX.md" || echo "✗ INDEX.md missing"

echo ""
echo "Installation check complete. If all items are ✓, skill 45 is ready."
```

---

### Step 7: Update the role library (on-box convergence)

When this skill lands on a box with `update-skills.sh`:

1. The 5 DIU role files are pulled into `$OC_ROOT/roles/graphics/` by Skill 23's ROLE LIBRARY gate.
2. The extended BB-graphics question bank activates.
3. On the next `sync-extensions.sh --converge` (Sunday 03:00 or manual), the 5 new roles wire into the Command Center.

No additional action needed — the standard workflow handles role materialization.

---

## Update semantics (re-installing the skill)

When `update-skills.sh` re-runs or the skill is manually re-installed:

- **_system files and _RULES:** rsync from skill dir, overwriting on-box copies (system is source-of-truth)
- **INDEX.md and style cards:** never touched (box owns these; `cp -n` skips existing files)
- **Idempotent:** running the installer 5 times is safe and produces the same result

---

## Troubleshooting

**INDEX.md shows "empty — awaiting first analysis"?**
- This is expected. INDEX seeds empty on first install. The Style Analyst or operator populates it via style-card registration.

**"Library path in MASTER-SOP says $OC_ROOT but I see a literal string"?**
- Verify Step 3 rsync completed. If paths look wrong, re-run `bash <this-installer>` (idempotent).

**Kie.ai is missing KIE_API_KEY?**
- Re-run Skill 07 (`bash $OC_ROOT/skills/07-kie-setup/install.sh`), then return here.

---

## End of INSTALL.md

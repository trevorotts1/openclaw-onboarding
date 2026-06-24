# Kie Adapter — Skill 47 Install Copy Step

This document describes the exact copy step that the Skill 47 installer
(`INSTALL.md` / `install.sh`) performs to drop the Kie adapters into the
client's cloned OpenMontage tree.

The two adapter files in this directory are authored by the fleet operator
and are NOT part of OpenMontage source (AGPLv3).  They are BaseTool
subclasses that implement the Kie.ai provider and are placed additively into
the client's clone — no OpenMontage files are modified.

---

## Directory layout (inside this skill)

```
47-openmontage-production/
  kie-adapters/
    INSTALL-COPY-STEP.md    ← this file
    tools/
      graphics/
        kie_image.py        ← KieImage BaseTool (capability: image_generation)
      video/
        kie_video.py        ← KieVideo BaseTool (capability: video_generation)
```

---

## Install step (verbatim; paste into Skill 47 INSTALL.md Step N)

> **When to run:** after `git clone https://github.com/calesthio/OpenMontage`
> and before `make setup`.

```bash
# --- Drop Kie adapters into the client's OpenMontage clone ---
# OPENMONTAGE_DIR must be set to the clone's root (e.g. ~/openmontage).
# SKILL_47_DIR must be set to the skill's install source directory.
#
# These files are OUR adapter code, not OpenMontage source.
# They are installed additively; no existing files are modified.

cp "$SKILL_47_DIR/kie-adapters/tools/graphics/kie_image.py" \
   "$OPENMONTAGE_DIR/tools/graphics/kie_image.py"

cp "$SKILL_47_DIR/kie-adapters/tools/video/kie_video.py" \
   "$OPENMONTAGE_DIR/tools/video/kie_video.py"

echo "[skill-47] Kie adapters installed:"
echo "  $OPENMONTAGE_DIR/tools/graphics/kie_image.py"
echo "  $OPENMONTAGE_DIR/tools/video/kie_video.py"
```

---

## Auto-discovery (no registry edits needed)

OpenMontage's `tools/tool_registry.py` `discover()` method walks every Python
file under `tools/` and registers any `BaseTool` subclass it finds.  Because
`kie_image.py` declares `capability = "image_generation"` and `kie_video.py`
declares `capability = "video_generation"`, both are automatically picked up
by `image_selector._providers()` and `video_selector._providers()` at
startup.

No changes to `tool_registry.py`, `image_selector.py`, `video_selector.py`,
or any OpenMontage file are required.

---

## Routing enforcement

The Skill 47 installer writes a `.env` at the OpenMontage clone root with
ONLY `KIE_API_KEY`.  All other paid-provider keys (FAL_KEY, RUNWAY_API_KEY,
HEYGEN_API_KEY, OPENAI_API_KEY, GOOGLE_API_KEY, etc.) are absent.  Each
native paid tool's `get_status()` checks its own key and returns UNAVAILABLE
when the key is absent.  The selectors' scoring engine therefore has exactly
one AVAILABLE generative provider for both image and video: `kie`.

Belt-and-suspenders: both adapters declare `quality_score = 0.90`, which
biases the scoring engine toward Kie even if another paid key is accidentally
present.  The `INSTRUCTIONS.md` also documents setting
`preferred_provider = "kie"` explicitly in pipeline manifests.

Free render engines (FFmpeg, Remotion, HyperFrames), free TTS (Piper), and
the free real-footage corpus (`tools/video/stock_sources/`) are NOT rewired
through Kie and are NOT affected by key gating.

---

## Verify (run after install, before `make setup`)

```bash
python3 -c "
import ast, sys
for path in [
    '$OPENMONTAGE_DIR/tools/graphics/kie_image.py',
    '$OPENMONTAGE_DIR/tools/video/kie_video.py',
]:
    ast.parse(open(path).read())
    print('SYNTAX OK:', path)
sys.exit(0)
"

# Confirm provider and capability declarations
grep -E 'provider\s*=|capability\s*=' \
  "$OPENMONTAGE_DIR/tools/graphics/kie_image.py" \
  "$OPENMONTAGE_DIR/tools/video/kie_video.py"
# Expected:
#   provider = "kie"
#   capability = "image_generation"
#   provider = "kie"
#   capability = "video_generation"

# Confirm KIE_API_KEY gating (available with key, unavailable without)
python3 - <<'EOF'
import sys, os
sys.path.insert(0, "$OPENMONTAGE_DIR")
os.environ.pop("KIE_API_KEY", None)
from tools.graphics.kie_image import KieImage
from tools.video.kie_video import KieVideo
assert KieImage().get_status().value == "unavailable", "kie_image must be UNAVAILABLE without key"
assert KieVideo().get_status().value == "unavailable", "kie_video must be UNAVAILABLE without key"
os.environ["KIE_API_KEY"] = "test-key-for-status-check"
assert KieImage().get_status().value == "available", "kie_image must be AVAILABLE with key"
assert KieVideo().get_status().value == "available", "kie_video must be AVAILABLE with key"
print("GATE OK: KIE_API_KEY gating verified for both adapters")
EOF
```

---

## AGPLv3 boundary

- The two `kie_*.py` files in this directory are authored by the fleet
  operator.  They are NOT a copy of OpenMontage source.
- They are placed in the CLIENT's cloned OpenMontage tree at install time,
  which keeps the AGPLv3 obligation on the client's own deployment.
- This directory (`47-openmontage-production/kie-adapters/`) contains ONLY
  our adapter code.  No OpenMontage source (`tools/`, `pipeline_defs/`,
  `remotion-composer/`, `lib/`) is vendored into the fleet template.

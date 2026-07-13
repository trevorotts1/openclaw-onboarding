#!/usr/bin/env bash
# Skill 47 — Movie Producer (Automated Video Production) — Automated Installer
# Mirrors the fail-loud pattern from presentation-deps-gate.yml + install.sh Step 6.5.
# Run via: bash install.sh
# Must be executed from the skill directory or with SKILL_DIR set.
# NOTE: "OpenMontage" below refers to the UPSTREAM engine (github.com/calesthio/OpenMontage,
# AGPLv3) that this Movie Producer skill clones onto the client box — not the skill dir name.

set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# A3 CONTENT-HASH FIX (v14.0.1): the OpenMontage clone (~56MB) MUST NOT live inside
# the hashed skill dir (~/.openclaw/skills/47-movie-producer/). The onboarding
# updater's A3 content-gate hashes that skill dir via skill-content-hash.sh; a clone
# inside it makes the DEST hash never match the clean source manifest, so A3 FAILS and
# the version stamp is BLOCKED fleet-wide. Clone OUTSIDE the skill dir, into a sibling
# runtime dir. The OPENCLAW_OPENMONTAGE_DIR override still works for custom locations.
OPENMONTAGE_DIR="${OPENCLAW_OPENMONTAGE_DIR:-$HOME/.openclaw/openmontage-runtime/OpenMontage}"
SKILL_NAME="movie-producer"

# FIX-S36-43: PIN the OpenMontage clone to a verified upstream commit so the docs
# (the pipeline table in INSTRUCTIONS.md) can never drift under an unpinned HEAD.
# This SHA is the tree whose pipeline_defs/*.yaml the docs are generated from
# (13 pipelines: animated-explainer, animation, avatar-spokesperson,
# character-animation, cinematic, clip-factory, documentary-montage,
# framework-smoke, hybrid, localization-dub, podcast-repurpose, screen-demo,
# talking-head). Override with OPENCLAW_OPENMONTAGE_SHA only when you have
# re-verified the pipeline table against the new tree.
OPENMONTAGE_PINNED_SHA="${OPENCLAW_OPENMONTAGE_SHA:-ce11f6a24f5c92e97d1461ffe1cd7a238dda1417}"

red()    { printf "\033[31mFAIL\033[0m %s\n" "$1"; }
green()  { printf "\033[32mPASS\033[0m %s\n" "$1"; }
yellow() { printf "\033[33mWARN\033[0m %s\n" "$1"; }
info()   { printf "     %s\n" "$1"; }

echo "=== Skill 47 / Movie Producer (Automated Video Production) — Install ==="
echo "    Skill dir:        $SKILL_DIR"
echo "    Clone target:     $OPENMONTAGE_DIR"
echo ""

# ---------------------------------------------------------------------------
# Step 1 — Fail-loud runtime dependency preflight
# ---------------------------------------------------------------------------
echo "--- Step 1: Runtime dependency preflight ---"
bash "$SKILL_DIR/preflight.sh" || {
  echo ""
  red "Preflight FAILED. Fix the missing dependencies listed above, then re-run install.sh."
  exit 1
}
echo ""

# ---------------------------------------------------------------------------
# Step 2 — Clone OpenMontage onto the client box
# ---------------------------------------------------------------------------
echo "--- Step 2: Clone OpenMontage ---"
# Ensure the runtime parent dir exists OUTSIDE the hashed skill dir (A3 fix, v14.0.1).
mkdir -p "$(dirname "$OPENMONTAGE_DIR")"
if [ -d "$OPENMONTAGE_DIR/.git" ]; then
  yellow "OpenMontage already cloned at $OPENMONTAGE_DIR — pulling latest."
  git -C "$OPENMONTAGE_DIR" pull --ff-only
else
  git clone https://github.com/calesthio/OpenMontage.git "$OPENMONTAGE_DIR"
fi

ACTUAL_REMOTE="$(git -C "$OPENMONTAGE_DIR" remote get-url origin)"
EXPECTED_REMOTE="https://github.com/calesthio/OpenMontage.git"
if [ "$ACTUAL_REMOTE" != "$EXPECTED_REMOTE" ]; then
  red "Remote mismatch: expected '$EXPECTED_REMOTE', got '$ACTUAL_REMOTE'"
  exit 1
fi
green "OpenMontage cloned — remote verified: $ACTUAL_REMOTE"

# FIX-S36-43: check out the PINNED SHA so the pipeline docs cannot drift under HEAD.
git -C "$OPENMONTAGE_DIR" fetch --quiet origin "$OPENMONTAGE_PINNED_SHA" 2>/dev/null || \
  git -C "$OPENMONTAGE_DIR" fetch --quiet origin || true
git -C "$OPENMONTAGE_DIR" checkout --quiet "$OPENMONTAGE_PINNED_SHA" || {
  red "Could not check out the pinned OpenMontage commit ($OPENMONTAGE_PINNED_SHA)."
  info "The upstream tree may have rewritten history. Re-verify the pipeline table in"
  info "INSTRUCTIONS.md against the new tree, then set OPENCLAW_OPENMONTAGE_SHA."
  exit 1
}
ACTUAL_SHA="$(git -C "$OPENMONTAGE_DIR" rev-parse HEAD)"
if [ "$ACTUAL_SHA" != "$OPENMONTAGE_PINNED_SHA" ]; then
  red "Pinned-SHA checkout mismatch: expected '$OPENMONTAGE_PINNED_SHA', got '$ACTUAL_SHA'"
  exit 1
fi
green "OpenMontage pinned — HEAD verified: $ACTUAL_SHA"
echo ""

# ---------------------------------------------------------------------------
# Step 3 — make setup (pip + remotion npm + npx hyperframes + piper)
# ---------------------------------------------------------------------------
echo "--- Step 3: make setup (fetches all dependencies) ---"
info "This installs: Python packages, Remotion npm, HyperFrames via npx, Piper TTS (soft-fail)."
info "AGPLv3 note: all deps fetched at runtime — NO OpenMontage source vendored into this template."
( cd "$OPENMONTAGE_DIR" && make setup ) || {
  red "make setup failed. Check error output above. Do NOT vendor — fix the dep and re-run."
  exit 1
}
green "make setup complete — no vendoring required."
echo ""

# ---------------------------------------------------------------------------
# Step 3.5 — Render-runtime provisioning (arch/OS-aware, idempotent)
# ---------------------------------------------------------------------------
# `make setup` installs the upstream npm/pip deps but NO Chromium system libraries — so a
# fresh Linux/VPS container FAILS every Remotion/HyperFrames (headless-Chromium) render.
# This step closes that gap for BOTH macOS and Linux: Chromium system libs + ffmpeg (Linux
# apt), the pinned latest Remotion + arch/OS compositor + Chrome-Headless-Shell, and the
# pinned latest HyperFrames CLI + bundled Chrome. Piper (offline TTS) is OPTIONAL and OFF by
# default — the PRIMARY narrator is Fish Audio 2.1 Pro (s2.1-pro), with Gemini TTS / OpenAI
# TTS / MiniMax (a.k.a. "Mimo") as the cloud fallbacks; Piper installs ONLY when you opt in
# and never aborts the install. The free ffmpeg + Kie paths need no browser.
#   Skip entirely on a free-path-only box:         SKILL47_SKIP_RENDER_PROVISION=1
#   Opt in to the optional offline Piper fallback:  SKILL47_INSTALL_PIPER=1
echo "--- Step 3.5: Provision render runtime (Chromium libs, Remotion, HyperFrames) ---"
if [ "${SKILL47_SKIP_RENDER_PROVISION:-0}" = "1" ]; then
  yellow "SKILL47_SKIP_RENDER_PROVISION=1 — skipping render-runtime provisioning (free-path-only box)."
else
  OPENCLAW_OPENMONTAGE_DIR="$OPENMONTAGE_DIR" bash "$SKILL_DIR/provision-render-deps.sh" || {
    red "Render-runtime provisioning FAILED (Remotion/HyperFrames/Chromium libs). Fix the errors"
    red "above, or set SKILL47_SKIP_RENDER_PROVISION=1 for a free-path-only install, then re-run"
    red "install.sh. (Piper is optional/opt-in and never causes this failure.)"
    exit 1
  }
  green "Render-runtime provisioning complete."
fi
echo ""

# ---------------------------------------------------------------------------
# Step 4 — Drop Kie adapters into the clone
# ---------------------------------------------------------------------------
echo "--- Step 4: Install Kie.AI adapters ---"
cp "$SKILL_DIR/kie-adapters/tools/graphics/kie_image.py" \
   "$OPENMONTAGE_DIR/tools/graphics/kie_image.py"
cp "$SKILL_DIR/kie-adapters/tools/video/kie_video.py" \
   "$OPENMONTAGE_DIR/tools/video/kie_video.py"

python3 -c "import ast; ast.parse(open('$OPENMONTAGE_DIR/tools/graphics/kie_image.py').read())" \
  && green "kie_image.py syntax OK" \
  || { red "kie_image.py syntax error — reinstall the skill bundle."; exit 1; }

python3 -c "import ast; ast.parse(open('$OPENMONTAGE_DIR/tools/video/kie_video.py').read())" \
  && green "kie_video.py syntax OK" \
  || { red "kie_video.py syntax error — reinstall the skill bundle."; exit 1; }
echo ""

# ---------------------------------------------------------------------------
# Step 4.5 — SK1-63: ship VIDEO-PIPELINE-MANIFEST.json to the runtime dir (fail-loud)
# ---------------------------------------------------------------------------
# The manifest is the SACRED source for executive_producer.py's autofail set. It lives
# at repo-root universal-sops/video-pipeline-craft/ and is intentionally NOT bundled
# inside the content-hashed skill dir. If it is never placed on the box, load_manifest()
# hard-exits 2 mid-pipeline. Copy it to a runtime location OUTSIDE the hashed skill dir
# (sibling of the OpenMontage clone, matching executive_producer._runtime_manifest_path)
# and FAIL LOUD here at install time if we cannot find the source.
echo "--- Step 4.5: Place VIDEO-PIPELINE-MANIFEST.json (runtime) ---"
MANIFEST_DEST="$(dirname "$OPENMONTAGE_DIR")/VIDEO-PIPELINE-MANIFEST.json"
MANIFEST_SRC="${OPENCLAW_VIDEO_PIPELINE_MANIFEST:-}"
if [ -z "$MANIFEST_SRC" ]; then
  # Walk up from the skill dir looking for the universal-sops sibling.
  _cur="$SKILL_DIR"
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12; do
    if [ -f "$_cur/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json" ]; then
      MANIFEST_SRC="$_cur/universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json"
      break
    fi
    [ "$_cur" = "/" ] && break
    _cur="$(dirname "$_cur")"
  done
fi
if [ -n "$MANIFEST_SRC" ] && [ -f "$MANIFEST_SRC" ]; then
  mkdir -p "$(dirname "$MANIFEST_DEST")"
  cp "$MANIFEST_SRC" "$MANIFEST_DEST"
  python3 -c "import json,sys; json.load(open('$MANIFEST_DEST'))" \
    && green "VIDEO-PIPELINE-MANIFEST.json placed at $MANIFEST_DEST (valid JSON)" \
    || { red "Copied manifest is not valid JSON — check $MANIFEST_SRC."; exit 1; }
else
  red "VIDEO-PIPELINE-MANIFEST.json source not found."
  info "Looked for universal-sops/video-pipeline-craft/VIDEO-PIPELINE-MANIFEST.json above"
  info "$SKILL_DIR, and OPENCLAW_VIDEO_PIPELINE_MANIFEST was unset. The fleet installer"
  info "must ship the universal-sops sibling with this skill, OR set"
  info "OPENCLAW_VIDEO_PIPELINE_MANIFEST to the manifest path, then re-run install.sh."
  exit 1
fi
echo ""

# ---------------------------------------------------------------------------
# Step 5 — Write the client .env (Kie key ONLY)
# ---------------------------------------------------------------------------
echo "--- Step 5: Write client .env ---"
ENV_FILE="$OPENMONTAGE_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" << 'ENVEOF'
# Kie.AI API key — CLIENT'S OWN KEY ONLY.
# Obtain a key at https://kie.ai
# All image/video generation routes through Kie.AI when this is set.
# Leave blank (or remove) to run the free documentary-montage path only.
KIE_API_KEY=YOUR_CLIENT_KIE_API_KEY_HERE
#
# DO NOT add FAL_KEY, RUNWAY_API_KEY, HEYGEN_API_KEY, OPENAI_API_KEY,
# GOOGLE_API_KEY, or REPLICATE_API_KEY here.
# Those providers must remain UNAVAILABLE on the client box so all
# generative asset production routes exclusively through Kie.AI.
# OPERATOR KEY RULE: The operator's own KIE_API_KEY MUST NEVER appear here.
ENVEOF
  yellow ".env created — replace YOUR_CLIENT_KIE_API_KEY_HERE with the client's actual Kie.AI key."
else
  yellow ".env already exists at $ENV_FILE — not overwritten. Verify KIE_API_KEY is set."
fi
echo ""

# ---------------------------------------------------------------------------
# Step 6 — WRITE the Rule-Zero budget cap into config.yaml (idempotent, via PyYAML)
# ---------------------------------------------------------------------------
# FIX-S36-39: the QC gate HARD-fails when budget.mode != cap, so the installer must
# actually WRITE the required config (not just print an advisory). This idempotently
# loads any existing config.yaml, sets the budget cap (total_usd <= 5) + approvals +
# guided checkpoints, and writes it back — preserving every other key. QC stays pure
# verification.
echo "--- Step 6: Write Rule-Zero budget cap into config.yaml ---"
CONFIG_FILE="$OPENMONTAGE_DIR/config.yaml"
CONFIG_FILE="$CONFIG_FILE" python3 - <<'PYEOF' || { red "Failed to write budget cap into config.yaml."; exit 1; }
import os, sys
try:
    import yaml
except ImportError:
    sys.stderr.write("PyYAML is required to write config.yaml (installed by make setup). "
                     "Run `pip install pyyaml` and re-run install.sh.\n")
    sys.exit(1)

path = os.environ["CONFIG_FILE"]
cfg = {}
if os.path.exists(path):
    with open(path) as fh:
        loaded = yaml.safe_load(fh)
    if isinstance(loaded, dict):
        cfg = loaded
    elif loaded is not None:
        sys.stderr.write("Existing config.yaml is not a YAML mapping; refusing to clobber "
                         "it. Inspect the OpenMontage clone.\n")
        sys.exit(1)

budget = cfg.get("budget")
budget = budget if isinstance(budget, dict) else {}
# Never RAISE an already-lower client cap; enforce the cap mode + a <= $5 ceiling.
existing_total = budget.get("total_usd")
if not isinstance(existing_total, (int, float)) or existing_total > 5:
    budget["total_usd"] = 5.00
budget["mode"] = "cap"
budget.setdefault("single_action_approval_usd", 0.50)
budget["require_approval_for_new_paid_tool"] = True
cfg["budget"] = budget

checkpoint = cfg.get("checkpoint")
checkpoint = checkpoint if isinstance(checkpoint, dict) else {}
checkpoint["policy"] = "guided"
cfg["checkpoint"] = checkpoint

# Belt-and-suspenders Kie routing (leaves any existing value alone if already set).
cfg.setdefault("preferred_provider", "kie")

with open(path, "w") as fh:
    yaml.safe_dump(cfg, fh, default_flow_style=False, sort_keys=False)
print(f"     config.yaml written: budget.mode=cap total_usd={cfg['budget']['total_usd']} "
      f"single_action_approval_usd={cfg['budget']['single_action_approval_usd']} "
      "checkpoint.policy=guided")
PYEOF
green "config.yaml budget cap enforced (mode: cap, total_usd <= 5.00, guided checkpoints)"
echo ""

# ---------------------------------------------------------------------------
# Step 7 — Verify provider routing (fail-loud if native providers available)
# ---------------------------------------------------------------------------
echo "--- Step 7: Provider routing verification ---"
( cd "$OPENMONTAGE_DIR" && make preflight 2>/dev/null ) || {
  yellow "make preflight returned non-zero or is not available — verify provider routing manually:"
  info "  cd $OPENMONTAGE_DIR"
  info "  python3 -c \"from tools.tool_registry import get_registry; r=get_registry(); [print(c, [(t.provider, str(t.get_status())) for t in r.get_by_capability(c)]) for c in ['image_generation','video_generation']]\""
}
echo ""

# ---------------------------------------------------------------------------
# Step 8 — Run QC
# ---------------------------------------------------------------------------
echo "--- Step 8: Install QC ---"
bash "$SKILL_DIR/qc-movie-producer.sh" || {
  red "QC failed. Review output above."
  exit 1
}
echo ""

echo "=== Skill 47 / Movie Producer (Automated Video Production) — INSTALL COMPLETE ==="
echo ""
echo "Next steps:"
echo "  1. Edit $ENV_FILE — replace YOUR_CLIENT_KIE_API_KEY_HERE with the client's Kie.AI key."
echo "  2. Verify the budget cap in $CONFIG_FILE"
echo "  3. Test the free path: cd $OPENMONTAGE_DIR && make demo"
echo "  4. See INSTRUCTIONS.md and EXAMPLES.md for pipeline execution."

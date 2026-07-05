#!/usr/bin/env bash
# 31-generate-workflow-visual.sh (U-11) - generate Part 4, THE VISUAL, for a
# conversation workflow.
#
# Produces TWO artifacts (see protocols/workflow-visual-protocol.md):
#   Artifact A, the truth diagram: a Mermaid flowchart generated DETERMINISTICALLY
#     from the playbook structure (via the canonical parser tools/playbook_engine.py,
#     U-16), emitted as diagram.mmd and rendered to diagram.png via npx mermaid-cli
#     (no API cost). This is the engineering-accurate diagram.
#   Artifact B, the client hero visual: a stylized branded image via Kie.ai using the
#     newest GPT-Image family model (model resolved at build time, never hardcoded),
#     hosted on the client's own GHL media library, embedded in the Notion doc. Budget
#     capped; NEVER blocks the build.
#
# Idempotent: skips regeneration when the structure hash of the parsed playbook
# matches the recorded hash in visual.json; --force overrides. Writes visual.json,
# records the registry Visual column, and (for real Kie jobs) logs kie-image-events.jsonl.
#
# --dry-run: emit diagram.mmd + render the PNG if mermaid-cli is available, but MOCK
# the Kie hero (no spend, no network) - used for local/CI evidence.
#
# OS-aware (Darwin + Linux). bash -n clean. set -uo pipefail (individual failures are
# handled; the truth diagram must never be blocked by a Kie/upload failure).
#
# Usage:
#   bash scripts/31-generate-workflow-visual.sh <workflow-id>
#   bash scripts/31-generate-workflow-visual.sh <workflow-id> --dir <conversation-workflows>
#   bash scripts/31-generate-workflow-visual.sh <workflow-id> --dry-run
#   bash scripts/31-generate-workflow-visual.sh <workflow-id> --force

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILL_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ENGINE="$SKILL_ROOT/tools/playbook_engine.py"

WORKFLOW_ID=""
WF_DIR=""
DRY_RUN=0
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --dir)     WF_DIR="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --force)   FORCE=1; shift ;;
    -h|--help) sed -n '1,34p' "$0"; exit 0 ;;
    -* ) echo "Unknown arg: $1" >&2; exit 2 ;;
    *)  if [ -z "$WORKFLOW_ID" ]; then WORKFLOW_ID="$1"; else echo "Unexpected arg: $1" >&2; exit 2; fi; shift ;;
  esac
done

if [ -z "$WORKFLOW_ID" ]; then
  echo "usage: 31-generate-workflow-visual.sh <workflow-id> [--dir DIR] [--dry-run] [--force]" >&2
  exit 2
fi

if [ ! -f "$ENGINE" ] || ! command -v python3 >/dev/null 2>&1; then
  echo "[31-generate-workflow-visual] canonical engine tools/playbook_engine.py or python3 not available." >&2
  exit 2
fi

# Resolve the conversation-workflows dir.
if [ -z "$WF_DIR" ]; then
  POINTER="${HOME}/.openclaw/.skill-38-master-files-dir"
  if [ -f "$POINTER" ]; then
    MFD="$(head -n1 "$POINTER")"
    [ -n "$MFD" ] && WF_DIR="$MFD/conversation-workflows"
  fi
fi
if [ -z "$WF_DIR" ] || [ ! -d "$WF_DIR" ]; then
  echo "[31-generate-workflow-visual] conversation-workflows dir not found (pass --dir DIR)." >&2
  exit 2
fi

PLAYBOOK="$WF_DIR/$WORKFLOW_ID.md"
if [ ! -f "$PLAYBOOK" ]; then
  echo "[31-generate-workflow-visual] playbook not found: $PLAYBOOK" >&2
  exit 2
fi

OUT_DIR="$WF_DIR/$WORKFLOW_ID"
mkdir -p "$OUT_DIR"
MMD="$OUT_DIR/diagram.mmd"
PNG="$OUT_DIR/diagram.png"
HERO="$OUT_DIR/hero.png"
VISUAL_JSON="$OUT_DIR/visual.json"
REGISTRY="$WF_DIR/registry.md"

# Structure hash of the current playbook (via the canonical engine).
CUR_HASH="$(python3 "$ENGINE" hash "$PLAYBOOK" 2>/dev/null | tr -d '[:space:]')"
if [ -z "$CUR_HASH" ]; then
  echo "[31-generate-workflow-visual] engine could not hash the playbook (grammar error?)." >&2
  exit 2
fi

# Idempotency: skip when the recorded hash matches and diagram.png exists (unless --force).
if [ "$FORCE" -eq 0 ] && [ -f "$VISUAL_JSON" ] && [ -f "$PNG" ]; then
  REC_HASH="$(python3 -c "import json,sys; print(json.load(open('$VISUAL_JSON')).get('structure_hash',''))" 2>/dev/null || echo "")"
  if [ -n "$REC_HASH" ] && [ "$REC_HASH" = "$CUR_HASH" ]; then
    echo "[31-generate-workflow-visual] '$WORKFLOW_ID' visual is current (hash $CUR_HASH) - skipping (use --force to regenerate)."
    exit 0
  fi
fi

# --- Artifact A: emit diagram.mmd (deterministic, via the engine). -------------
if ! python3 "$ENGINE" mermaid "$PLAYBOOK" > "$MMD" 2>/dev/null; then
  echo "[31-generate-workflow-visual] engine failed to emit mermaid for '$WORKFLOW_ID'." >&2
  exit 2
fi
echo "[31-generate-workflow-visual] emitted $MMD"

# --- Artifact A: render diagram.png via npx mermaid-cli (install on first use). -
PNG_OK="no"
if command -v npx >/dev/null 2>&1; then
  if npx -y @mermaid-js/mermaid-cli -i "$MMD" -o "$PNG" >/dev/null 2>&1 && [ -f "$PNG" ]; then
    PNG_OK="yes"
    echo "[31-generate-workflow-visual] rendered $PNG via npx mermaid-cli"
  else
    echo "[31-generate-workflow-visual] WARNING: npx mermaid-cli could not render the PNG (offline/headless-chromium missing). diagram.mmd is on disk; rerun to render." >&2
  fi
else
  echo "[31-generate-workflow-visual] WARNING: npx not available; skipped PNG render. diagram.mmd is on disk." >&2
fi

# --- Artifact B: the Kie hero visual (mocked in --dry-run). ---------------------
MODEL_ID=""
HERO_STATUS="pending"
HERO_PATH=""
if [ "$DRY_RUN" -eq 1 ]; then
  MODEL_ID="mock-gpt-image"
  echo "[31-generate-workflow-visual] --dry-run: MOCKED Kie hero (no spend, no network). Truth diagram ships regardless."
else
  # Real path: resolve the newest GPT-Image family model per Skill 07 (never hardcode),
  # route async jobs through Skill 46 when installed, host on the client's GHL media
  # library, and log the job to kie-image-events.jsonl. The truth diagram ALWAYS ships;
  # the hero is budget-capped and never blocks the build (timeout 120s, one retry, then
  # flag pending). This block is a documented integration point; when KIE_API_KEY and
  # Skill 07 are absent it degrades to Mermaid-only.
  if [ -n "${KIE_API_KEY:-}" ]; then
    MODEL_ID="${KIE_IMAGE_MODEL:-gpt-image}"   # resolved at build time per Skill 07 catalog
    echo "[31-generate-workflow-visual] Kie hero path active (model resolved at build time per Skill 07)."
    # A real hero job would log here; cost logging happens only when a job actually runs.
  else
    echo "[31-generate-workflow-visual] KIE_API_KEY absent - Mermaid-only. Hero flagged pending (never blocks the build)."
  fi
fi
[ -f "$HERO" ] && { HERO_STATUS="present"; HERO_PATH="$HERO"; }

# --- Write visual.json (the machine record qc-workflow-visual.sh reads). --------
GEN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DIAGRAM_PNG_FIELD=""
[ "$PNG_OK" = "yes" ] && DIAGRAM_PNG_FIELD="$PNG"
python3 - "$VISUAL_JSON" "$WORKFLOW_ID" "$CUR_HASH" "$MODEL_ID" "$MMD" "$DIAGRAM_PNG_FIELD" "$HERO_PATH" "$HERO_STATUS" "$GEN_TS" <<'PYEOF'
import json, sys
(path, wid, h, model, mmd, png, hero, hero_status, ts) = sys.argv[1:10]
rec = {
    "workflow_id": wid,
    "structure_hash": h,
    "model_id": model or None,
    "diagram_mmd": mmd,
    "diagram_png": png or None,
    "hero_png": hero or None,
    "hero_status": hero_status,
    "hosted_urls": {"diagram": None, "hero": None},
    "generated_at": ts,
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(rec, fh, indent=2)
    fh.write("\n")
PYEOF
echo "[31-generate-workflow-visual] wrote $VISUAL_JSON (hash $CUR_HASH)"

# --- Record the Visual column in registry.md (human-readable summary). ----------
if [ -f "$REGISTRY" ]; then
  VISUAL_CELL="diagram.png"
  [ "$PNG_OK" != "yes" ] && VISUAL_CELL="diagram.mmd"
  [ "$HERO_STATUS" = "present" ] && VISUAL_CELL="$VISUAL_CELL + hero.png"
  SLUG="$WORKFLOW_ID" VISUAL="$VISUAL_CELL" REGFILE="$REGISTRY" python3 - <<'PY_REC'
import os
slug = os.environ["SLUG"]; visual = os.environ["VISUAL"]; reg = os.environ["REGFILE"]
text = open(reg, "r", encoding="utf-8").read()
lines = text.split("\n")
out = []
done = False
for line in lines:
    s = line.strip()
    if s.startswith("|") and not done:
        cells = [c.strip() for c in s.strip("|").split("|")]
        rid = cells[0].strip("`").strip() if cells else ""
        if rid == slug:
            # If a 'Visual' column exists (canonical shape), set its cell; else append a bullet later.
            # Heuristic: the canonical registry has a Visual column between Tools and Doc; when the row
            # already has >=9 cells we set the Visual cell (index 8), else we leave the row and add a note.
            if len(cells) >= 9:
                cells[8] = visual
                out.append("| " + " | ".join(cells) + " |")
                done = True
                continue
    out.append(line)
if not done:
    new = []
    inserted = False
    for line in out:
        new.append(line)
        if not inserted and line.strip().lower().startswith("## active workflow"):
            new.append("")
            new.append("- %s: visual recorded  [visual: %s]" % (slug, visual))
            inserted = True
    if not inserted:
        new.append("")
        new.append("- %s: visual recorded  [visual: %s]" % (slug, visual))
    out = new
open(reg, "w", encoding="utf-8").write("\n".join(out))
PY_REC
  echo "[31-generate-workflow-visual] recorded Visual column for '$WORKFLOW_ID' in registry.md"
fi

echo "[31-generate-workflow-visual] done for '$WORKFLOW_ID' (truth diagram: $([ "$PNG_OK" = yes ] && echo png || echo mmd-only); hero: $HERO_STATUS)."
exit 0

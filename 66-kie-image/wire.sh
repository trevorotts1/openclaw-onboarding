#!/usr/bin/env bash
# wire.sh — Skill 66 (KIE Image): PERFORM the core-file updates.
#
# WHY THIS EXISTS (the defect it replaces)
#   Earlier skills shipped no installer, so their CORE_UPDATES.md was consumed by
#   the generic merger in update-skills.sh (wire_core_updates). That merger copies
#   the section body VERBATIM, so what landed in boxes' AGENTS.md / TOOLS.md /
#   MEMORY.md was the literal INSTRUCTION —
#       Add:
#       ```
#       ## ...
#       ```
#   — the word "Add:" and a markdown code fence wrapped around the payload, i.e.
#   the recipe pasted instead of executed. The pointer inside it was ALSO wrong: a
#   ROOTLESS relative path that resolves against whatever directory the agent
#   happens to be in, so the reference could never be opened reliably.
#
# WHAT THIS DOES INSTEAD
#   Executes the add: writes ONE compact block per core file behind a VERSION-FREE
#   marker, REPLACE-IN-PLACE (so a re-run is byte-identical and an already-pasted
#   box is HEALED, not appended to), with the master-files path RESOLVED to an
#   absolute path on this box. It then stamps the idempotency sentinel
#   `<!-- skill:66-kie-image:core-update-applied -->` so the generic merger
#   short-circuits and can never paste the recipe again.
#
# STAMP-BANK SAFETY
#   AGENTS.md carries the shared stamp bank other installers key on. This script
#   only ever touches its OWN `skill:66-kie-image:*` markers, and it only ever ADDS
#   its own sentinel — no other skill's block or stamp is read, moved or removed.
#
# Backups are timestamped and taken ONLY when a file actually changes.
# Accepts and ignores `--idempotent` (passed by update-skills.sh's wiring loop).
# Exit 0 = every core file carries exactly the current block.

set -euo pipefail

SKILL_SLUG="66-kie-image"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

# ── Resolve the workspace that owns the core files ───────────────────────────
# Same order update-skills.sh uses for its core-update wiring target, so this
# block and the shared stamp bank always land in the SAME AGENTS.md.
resolve_workspace() {
  if [ -n "${OPENCLAW_WORKSPACE:-}" ]; then printf '%s' "$OPENCLAW_WORKSPACE"; return 0; fi
  local ocroot="$HOME/.openclaw"
  [ -d /data/.openclaw ] && ocroot="/data/.openclaw"
  local ocjson="$ocroot/openclaw.json" ws=""
  if [ -f "$ocjson" ] && command -v python3 >/dev/null 2>&1; then
    ws="$(OC_JSON="$ocjson" python3 - <<'PY' 2>/dev/null || true
import json, os
try:
    cfg = json.load(open(os.environ["OC_JSON"]))
    for ag in cfg.get("agents", {}).get("list", []) or []:
        if isinstance(ag, dict) and ag.get("id") == "main" and ag.get("workspace"):
            print(os.path.expanduser(ag["workspace"])); break
    else:
        w = cfg.get("agents", {}).get("defaults", {}).get("workspace")
        if w:
            print(os.path.expanduser(w))
except Exception:
    pass
PY
)"
  fi
  [ -n "$ws" ] || ws="$ocroot/workspace"
  printf '%s' "$ws"
}
WS="$(resolve_workspace)"

# ── Resolve the master-files root (absolute — never a rootless path) ─────────
if [ -n "${OPENCLAW_MASTER_FILES_DIR:-}" ]; then
  MFD="$OPENCLAW_MASTER_FILES_DIR"
elif [ -f /data/.openclaw/openclaw.json ]; then
  MFD="/data/.openclaw/master-files"
else
  MFD="$HOME/Downloads/openclaw-master-files"
fi
SKILL_DEST="$MFD/$SKILL_SLUG"
REF_DEST="$SKILL_DEST"                    # skill folder root: models.json + references/ live here
REFERENCES_SRC="$SKILL_DIR/references"

# ── Install the registry + references so the pointers can never dangle ───────
# mkdir -p + file-by-file copy (idempotent: only newer/missing files are copied).
if [ "$SKILL_DIR" != "$SKILL_DEST" ] && { [ -f "$SKILL_DIR/models.json" ] || [ -d "$REFERENCES_SRC" ]; }; then
  mkdir -p "$SKILL_DEST/references" 2>/dev/null || true
  if [ -f "$SKILL_DIR/models.json" ]; then
    if [ ! -f "$SKILL_DEST/models.json" ] || [ "$SKILL_DIR/models.json" -nt "$SKILL_DEST/models.json" ]; then
      cp "$SKILL_DIR/models.json" "$SKILL_DEST/models.json" 2>/dev/null \
        && echo "[skill 66] installed registry -> $SKILL_DEST/models.json"
    fi
  fi
  if [ -d "$REFERENCES_SRC" ]; then
    for f in "$REFERENCES_SRC"/*; do
      [ -f "$f" ] || continue
      base="$(basename "$f")"
      if [ ! -f "$SKILL_DEST/references/$base" ] || [ "$f" -nt "$SKILL_DEST/references/$base" ]; then
        cp "$f" "$SKILL_DEST/references/$base" 2>/dev/null \
          && echo "[skill 66] installed reference -> $SKILL_DEST/references/$base"
      fi
    done
  fi
fi

AGENTS_BODY="## Media Generation Routing
- generic image -> provider router -> Agnes Image (63) or KIE Image (66)
- generic video -> provider router -> Agnes Video (64) or KIE Video (67)
- KIE audio/music/TTS -> KIE Audio (68)
- explicit model/provider wins; department manifest wins; chosen provider remembered for the task
- validators run before API dispatch
- detailed model tables live in skill references/, not here

## KIE Image (66)
- KIE.ai Market API image generation. Key: KIE_API_KEY (env var NAME per repo convention).
- Create: POST https://api.kie.ai/api/v1/jobs/createTask (async — 200 = task CREATED, not finished).
- Query: GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state: waiting/queuing/generating/success/fail).
- Default pick: GPT Image 2 (gpt-image-2-text-to-image) when compatible; explicit user model wins.
- Validators run before dispatch: scripts/validate_prompt.py, scripts/validate_payload.py, scripts/select_image_model.py, scripts/normalize_alias.py.
- Prompt band legal per model: Wan/Ideogram/Imagen 4 caps 5,000 chars VERIFIED; Qwen is token-based (never fake char cap); others NOT_PUBLISHED (house band 5K-19K is TARGET only).
- Full registry + per-family tables: $REF_DEST/models.json, $REF_DEST/references/"

TOOLS_BODY="## KIE Image API (Skill 66)
- Auth: Bearer <KIE_API_KEY>
- POST https://api.kie.ai/api/v1/jobs/createTask (asynchronous; response 200 = task created with taskId)
- GET https://api.kie.ai/api/v1/jobs/recordInfo?taskId=<TASK_ID> (state enum: waiting/queuing/generating/success/fail; resultJson.resultUrls on success)
- Callbacks: callBackUrl field; HMAC-SHA256 scheme base64(HMAC-SHA256(taskId + \".\" + timestampSeconds, webhookHmacKey)); headers X-Webhook-Timestamp / X-Webhook-Signature; ack {\"code\":200,\"msg\":\"success\"}
- Rate: 20 new generation requests/10s; 100+ concurrent. Result URLs expire ~24h; media deleted after 14 days.
- Registry: $REF_DEST/models.json + $REF_DEST/references/ (per-family limits, ratios, resolutions, reference caps)
- Validators: scripts/validate_prompt.py, scripts/validate_payload.py (run before dispatch; never after)"

MEMORY_BODY="## KIE Image (66) — installed
- KIE.ai Market API; async createTask -> recordInfo polling or Skill 46 callback (never treat 200 as done)
- Key: KIE_API_KEY; model default GPT Image 2 when compatible, explicit pick wins
- Registry + tables: $REF_DEST/models.json, $REF_DEST/references/"

CHANGED=0

write_block() { # <file> <target-key> <body>
  local file="$1" target="$2" body="$3"
  local begin="<!-- BEGIN skill:${SKILL_SLUG}:${target} -->"
  local end="<!-- END skill:${SKILL_SLUG}:${target} -->"
  [ -f "$file" ] || touch "$file" 2>/dev/null || { echo "[skill 66] cannot create $file — skipping"; return 0; }

  local tmp; tmp="$(mktemp)"
  FILE="$file" BEGIN="$begin" END="$end" BODY="$body" OUT="$tmp" python3 - <<'PY'
import os

path = os.environ["FILE"]
begin = os.environ["BEGIN"]
end = os.environ["END"]
body = os.environ["BODY"]
out = os.environ["OUT"]

with open(path, "r", encoding="utf-8", errors="surrogateescape") as fh:
    lines = fh.read().split("\n")

# REPLACE-IN-PLACE across the whole marker pair, however many copies exist. Only
# this skill's own BEGIN/END pair is matched; nothing else in the file is read.
kept = []
i = 0
first = None
while i < len(lines):
    if lines[i].strip() == begin:
        j = i + 1
        while j < len(lines) and lines[j].strip() != end:
            j += 1
        if j < len(lines):
            if first is None:
                first = len(kept)
            if kept and kept[-1] == "":
                kept.pop()
                if first is not None:
                    first = min(first, len(kept))
            i = j + 1
            continue
    kept.append(lines[i])
    i += 1

block = [""] + [begin] + body.split("\n") + [end]
if first is None:
    while kept and kept[-1] == "":
        kept.pop()
    kept.extend(block)
else:
    kept[first:first] = block

text = "\n".join(kept).rstrip("\n") + "\n"
with open(out, "w", encoding="utf-8", errors="surrogateescape") as fh:
    fh.write(text)
PY

  if cmp -s "$file" "$tmp"; then
    rm -f "$tmp"
    echo "[skill 66] $(basename "$file"): block '$target' already current — no change, no backup"
    return 0
  fi
  cp -p "$file" "$file.bak-skill66-$(date -u +%Y%m%dT%H%M%SZ)"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  CHANGED=1
  echo "[skill 66] $(basename "$file"): wrote block '$target' (replace-in-place)"
}

write_block "$WS/AGENTS.md" agents "$AGENTS_BODY"
write_block "$WS/TOOLS.md"  tools  "$TOOLS_BODY"
write_block "$WS/MEMORY.md" memory "$MEMORY_BODY"

# ── Shared idempotency sentinel ──────────────────────────────────────────────
# ADD-ONLY. This is what makes update-skills.sh's generic wire_core_updates()
# short-circuit for this skill, so the "Add:" + code-fence recipe can never be
# pasted again. No other skill's stamp is touched.
SENTINEL="<!-- skill:${SKILL_SLUG}:core-update-applied -->"
if ! grep -qF "$SENTINEL" "$WS/AGENTS.md" 2>/dev/null; then
  printf '\n%s\n' "$SENTINEL" >> "$WS/AGENTS.md"
  echo "[skill 66] stamped $SENTINEL"
fi

echo "[skill 66] core-file wiring complete (workspace: $WS; reference: $REF_DEST; changed=$CHANGED)"
exit 0

#!/usr/bin/env bash
# wire.sh — Skill 64 (Agnes Video): PERFORM the core-file updates.
#
# WHY THIS EXISTS (the defect it replaces)
#   Skill 64 shipped no installer, so its CORE_UPDATES.md was consumed by the
#   generic merger in update-skills.sh (wire_core_updates). That merger copies the
#   section body VERBATIM, so what landed in every box's AGENTS.md / TOOLS.md /
#   MEMORY.md was the literal INSTRUCTION —
#       Add:
#       ```
#       ## Agnes Video V2.0 — Video Generation [PRIORITY: HIGH]
#       …
#       ```
#   — the word "Add:" and a markdown code fence wrapped around the payload, i.e. the
#   recipe pasted instead of executed. Worse, the pointer inside it was NEVER FILLED:
#   it landed on the box as the literal template variable
#   `[MASTER_FILES_FOLDER]/64-agnes-video/agnes-video-full.md`, so the agent was
#   pointed at a path that does not exist on any box.
#
# WHAT THIS DOES INSTEAD
#   Executes the add: writes ONE compact pointer block per core file behind a
#   VERSION-FREE marker, REPLACE-IN-PLACE (so a re-run is byte-identical and an
#   already-pasted box is HEALED, not appended to), with the master-files path
#   RESOLVED to an absolute path on this box. It then stamps the shared idempotency
#   sentinel `<!-- skill:64-agnes-video:core-update-applied -->` so the generic
#   merger short-circuits and can never paste the recipe again.
#
# STAMP-BANK SAFETY
#   AGENTS.md carries the shared stamp bank ~44 other installers key on. This script
#   only ever touches its OWN `skill:64-agnes-video:*` markers, and it only ever ADDS
#   its own sentinel — no other skill's block or stamp is read, moved or removed.
#
# Backups are timestamped and taken ONLY when a file actually changes.
# Accepts and ignores `--idempotent` (passed by update-skills.sh's wiring loop).
# Exit 0 = every core file carries exactly the current block.

set -euo pipefail

SKILL_SLUG="64-agnes-video"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REFERENCE_REL="agnes-video-full.md"

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
REF_DEST="$SKILL_DEST/$REFERENCE_REL"

# ── Install the pointer target so the pointer can never dangle ───────────────
if [ -f "$SKILL_DIR/$REFERENCE_REL" ] && [ "$SKILL_DIR" != "$SKILL_DEST" ]; then
  mkdir -p "$SKILL_DEST" 2>/dev/null || true
  if [ ! -f "$REF_DEST" ] || [ "$SKILL_DIR/$REFERENCE_REL" -nt "$REF_DEST" ]; then
    cp "$SKILL_DIR/$REFERENCE_REL" "$REF_DEST" 2>/dev/null \
      && echo "[skill 64] installed reference -> $REF_DEST"
  fi
fi

AGENTS_BODY="## Agnes Video — Video Generation [PRIORITY: HIGH]
- Model choice is NOT manual: run scripts/select_agnes_video_model.py before dispatch
  (deterministic router; explicit model wins; no silent switch; semantic guard vs keyframe reinterpretation)
- Models: agnes-video-2.5-flash (seconds STRING \"4\"-\"12\", size 720P only,
  modes text/keyframe/reference, images max 5, videos NEVER) and agnes-video-v2.0
  (num_frames <= 441 AND 8n+1, frame_rate 1-60, 480p/720p/1080p, extra_body.keyframes)
- Auth: Bearer token from AGNES_AI_API_KEY (fleet-provisioned; NEVER print it)
- Pattern: POST https://apihub.agnes-ai.com/v1/videos to CREATE a task ->
  capture video_id -> POLL GET https://apihub.agnes-ai.com/agnesapi?video_id=<id>
  (Flash: ALWAYS add &model_name=agnes-video-2.5-flash) until status=completed -> read metadata.url
- Never auto-select full agnes-video-2.5 (paid, not in token plan)
- Trust returned size/seconds/metadata.size_mapping, NOT the request
- Full reference: $REF_DEST"

TOOLS_BODY="## Agnes Video API [PRIORITY: HIGH]
- Base: https://apihub.agnes-ai.com
- Auth: Bearer <AGNES_AI_API_KEY> (referenced, never printed)
- Create task:  POST /v1/videos  (models: agnes-video-2.5-flash | agnes-video-v2.0)
- Get result (Flash, ALL modes):  GET  /agnesapi?video_id=<ID>&model_name=agnes-video-2.5-flash
- Get result (V2.0):              GET  /agnesapi?video_id=<ID>  (legacy /v1/videos/<TASK_ID>)
- Async: a 200 on create means QUEUED, not done — poll for the result
- Flash: seconds STRING 4-12, size 720P only, images max 5, videos NEVER, n=1
- V2.0: num_frames <=441 AND 8n+1, frame_rate 1-60, tiers 480p/720p/1080p (normalized)
- Pricing: currently \$0/second (flash list \$0.025/s; v2.0 list \$0.005/s);
  full agnes-video-2.5 is paid and never auto-selected
- Rate limit: metered on RPM AND daily/weekly quota by account tier; treat 429
  as the live ceiling and back off — do NOT hardcode a limit
- Full reference: $REF_DEST"

MEMORY_BODY="## Agnes Video — installed
- agnes-video-2.5-flash + agnes-video-v2.0, ASYNC create+poll; key AGNES_AI_API_KEY (fleet infra, never printed)
- Router: scripts/select_agnes_video_model.py — deterministic model choice, explicit model wins, no silent switch
- Endpoint reference doc with all params, response fields, curl examples, tier limits
- Full reference: $REF_DEST"

CHANGED=0

write_block() { # <file> <target-key> <body>
  local file="$1" target="$2" body="$3"
  local begin="<!-- BEGIN skill:${SKILL_SLUG}:${target} -->"
  local end="<!-- END skill:${SKILL_SLUG}:${target} -->"
  [ -f "$file" ] || touch "$file" 2>/dev/null || { echo "[skill 64] cannot create $file — skipping"; return 0; }

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
    echo "[skill 64] $(basename "$file"): block '$target' already current — no change, no backup"
    return 0
  fi
  cp -p "$file" "$file.bak-skill64-$(date -u +%Y%m%dT%H%M%SZ)"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  CHANGED=1
  echo "[skill 64] $(basename "$file"): wrote block '$target' (replace-in-place)"
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
  echo "[skill 64] stamped $SENTINEL"
fi

echo "[skill 64] core-file wiring complete (workspace: $WS; reference: $REF_DEST; changed=$CHANGED)"
exit 0

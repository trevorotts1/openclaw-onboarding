#!/usr/bin/env bash
# wire.sh — Skill 68 (KIE Audio): PERFORM the core-file updates.
#
# WHY THIS EXISTS (the defect it replaces)
#   Skills that ship no installer get their CORE_UPDATES.md consumed by the
#   generic merger in update-skills.sh (wire_core_updates). That merger copies the
#   section body VERBATIM, so what lands in every box's AGENTS.md / TOOLS.md /
#   MEMORY.md is the literal INSTRUCTION —
#       Add:
#       ```
#       ## KIE Audio (68)
#       …
#       ```
#   — the word "Add:" and a markdown code fence wrapped around the payload, i.e. the
#   recipe pasted instead of executed. The pointer inside it is ALSO wrong: it reads
#   `[MASTER_FILES_FOLDER]/68-kie-audio/references/tts.md`, a rootless path that
#   resolves against whatever directory the agent happens to be in, so the reference
#   can never be opened reliably.
#
# WHAT THIS DOES INSTEAD
#   Executes the add: writes ONE compact pointer block per core file behind a
#   VERSION-FREE marker, REPLACE-IN-PLACE (so a re-run is byte-identical and an
#   already-pasted box is HEALED, not appended to), with the master-files path
#   RESOLVED to an absolute path on this box. It then stamps the shared idempotency
#   sentinel `<!-- skill:68-kie-audio:core-update-applied -->` so the generic
#   merger short-circuits and can never paste the recipe again.
#
# STAMP-BANK SAFETY
#   AGENTS.md carries the shared stamp bank ~44 other installers key on. This script
#   only ever touches its OWN `skill:68-kie-audio:*` markers, and it only ever ADDS
#   its own sentinel — no other skill's block or stamp is read, moved or removed.
#
# Backups are timestamped and taken ONLY when a file actually changes.
# Accepts and ignores `--idempotent` (passed by update-skills.sh's wiring loop).
# Exit 0 = every core file carries exactly the current block.

set -euo pipefail

SKILL_SLUG="68-kie-audio"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
REFERENCE_REL="references/tts.md"

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
if [ -d "$SKILL_DIR/references" ] && [ "$SKILL_DIR" != "$SKILL_DEST" ]; then
  mkdir -p "$SKILL_DEST" 2>/dev/null || true
  mkdir -p "$SKILL_DEST/references" 2>/dev/null || true
  for f in references/*.md; do
    [ -f "$f" ] || continue
    if [ ! -f "$SKILL_DEST/$f" ] || [ "$SKILL_DIR/$f" -nt "$SKILL_DEST/$f" ]; then
      cp "$SKILL_DIR/$f" "$SKILL_DEST/$f" 2>/dev/null \
        && echo "[skill 68] installed reference -> $SKILL_DEST/$f"
    fi
  done
fi

AGENTS_BODY="## Media Generation Routing
- generic image -> provider router -> Agnes Image (63) or KIE Image (66)
- generic video -> provider router -> Agnes Video (64) or KIE Video (67)
- KIE audio/music/TTS -> KIE Audio (68)
- explicit model/provider wins; department manifest wins; chosen provider remembered for the task
- validators run before API dispatch
- detailed model tables live in skill references/, not here

## KIE Audio (68)
- TTS via generic Market createTask (POST /api/v1/jobs/createTask): google/gemini-3-1-flash-tts, google/gemini-2-5-pro-tts, elevenlabs/text-to-dialogue-v3, elevenlabs/text-to-speech-multilingual-v2, elevenlabs/text-to-speech-turbo-2-5. Key: KIE_API_KEY (referenced, never printed).
- Suno music is DEDICATED (/api/v1/generate + /extend + /sounds + 14 operations) — NEVER through createTask. Models: V4/V4_5/V4_5PLUS/V4_5ALL/V5/V5_5.
- STT is NOT dispatchable: ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false — never route transcription here.
- Validator: python3 scripts/validate_audio_request.py --domain tts|music|stt --payload <file.json> (exit 2 = do not dispatch).
- Full reference: $REF_DEST (+ references/music.md, references/stt.md, references/qc.md)"

TOOLS_BODY="## KIE Audio API (TTS + Suno)
- Auth: Bearer <KIE_API_KEY> (referenced, never printed)
- TTS: POST https://api.kie.ai/api/v1/jobs/createTask; query GET /api/v1/jobs/recordInfo?taskId=<id>
  - google/gemini-3-1-flash-tts, google/gemini-2-5-pro-tts (input.speakers[] + input.dialogue_turns[]; per-turn text max 10000)
  - elevenlabs/text-to-dialogue-v3 (dialogue[] combined max 5000), /text-to-speech-multilingual-v2, /text-to-speech-turbo-2-5 (text max 5000)
- Music (Suno DEDICATED — never createTask): POST /api/v1/generate, /generate/extend, /generate/sounds, plus 14 operations (mashup = exactly 2 URLs; persona vocal window 10-30s; replace-section min 10s max 50%)
- All audio tasks ASYNC: 200 = taskId only; result via callBackUrl callback (or polling); Suno stages text -> first -> complete
- STT: no endpoint — ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false
- Validator: python3 scripts/validate_audio_request.py --domain tts|music|stt --payload <file.json>
- Full reference: $REF_DEST (+ references/music.md, references/stt.md, references/qc.md)"

MEMORY_BODY="## KIE Audio (68) — installed
- Uses the existing KIE_API_KEY (same key as Skill 07; referenced, never printed).
- TTS via generic Market createTask (Gemini speakers/dialogue_turns; ElevenLabs dialogue-v3/multilingual-v2/turbo-2-5); query recordInfo.
- Suno is DEDICATED /api/v1/generate family — never createTask.
- STT is ADVERTISED_NOT_YET_VERIFIED, dispatch_enabled false — never route transcription here.
- Full reference: $REF_DEST"

CHANGED=0

write_block() { # <file> <target-key> <body>
  local file="$1" target="$2" body="$3"
  local begin="<!-- BEGIN skill:${SKILL_SLUG}:${target} -->"
  local end="<!-- END skill:${SKILL_SLUG}:${target} -->"
  [ -f "$file" ] || touch "$file" 2>/dev/null || { echo "[skill 68] cannot create $file — skipping"; return 0; }

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
    echo "[skill 68] $(basename "$file"): block '$target' already current — no change, no backup"
    return 0
  fi
  cp -p "$file" "$file.bak-skill68-$(date -u +%Y%m%dT%H%M%SZ)"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  CHANGED=1
  echo "[skill 68] $(basename "$file"): wrote block '$target' (replace-in-place)"
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
  echo "[skill 68] stamped $SENTINEL"
fi

echo "[skill 68] core-file wiring complete (workspace: $WS; reference: $REF_DEST; changed=$CHANGED)"
exit 0

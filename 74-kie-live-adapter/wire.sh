#!/usr/bin/env bash
# wire.sh - Skill 74 (KIE Live Adapter): PERFORM the core-file updates.
#
# Writes ONE short pointer block into AGENTS.md and TOOLS.md behind a version-free marker,
# REPLACE-IN-PLACE (a re-run is byte-identical), then stamps its own sentinel
# `<!-- skill:74-kie-live-adapter:core-update-applied -->` so the generic merger in
# update-skills.sh never pastes the recipe. Only this skill's own markers are touched.
# Backups are timestamped and taken ONLY when a file changes.
# Makes no config change, writes nothing inside the skill folder, never sets a mode.
# Accepts and ignores `--idempotent`. Exit 0 = every core file carries the current block.

set -euo pipefail

SKILL_SLUG="74-kie-live-adapter"
SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"

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
    # The main agent workspace: agents.entries (OpenClaw 2026.9.x, keyed by id)
    # or the legacy agents.list[], then agents.defaults.workspace.
    a = cfg.get("agents", {}) or {}
    e = a.get("entries") if isinstance(a.get("entries"), dict) else {}
    lst = a.get("list") if isinstance(a.get("list"), list) else []
    w = ((e.get("main") or {}).get("workspace")
         or next((x.get("workspace") for x in lst
                  if isinstance(x, dict) and x.get("id") == "main" and x.get("workspace")), None)
         or (a.get("defaults") or {}).get("workspace"))
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

AGENTS_BODY="## KIE Live Adapter (74)
- Pointer only: $SKILL_DIR/scripts/kie_live_adapter.py checks KIE's live catalog and schema and can run a job.
- Default mode is shadow: it records drift and never dispatches a paid job. Mode: KIE_LIVE_ADAPTER_MODE off|shadow|active.
- It never picks or changes a model; pinned models (the fleet image pin) win. The caller owns fallback.
- Never copy it into a Presentations deck run directory."

TOOLS_BODY="## KIE Live Adapter (Skill 74)
- python3 $SKILL_DIR/scripts/kie_live_adapter.py health|discover|schema|validate|upload|submit|wait|run|credits|save --json
- Cache and receipts: ~/.openclaw/cache/kie-live-adapter"

CHANGED=0

write_block() { # <file> <target-key> <body>
  local file="$1" target="$2" body="$3"
  local begin="<!-- BEGIN skill:${SKILL_SLUG}:${target} -->"
  local end="<!-- END skill:${SKILL_SLUG}:${target} -->"
  [ -f "$file" ] || touch "$file" 2>/dev/null || { echo "[skill 74] cannot create $file - skipping"; return 0; }

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
    echo "[skill 74] $(basename "$file"): block '$target' already current - no change, no backup"
    return 0
  fi
  cp -p "$file" "$file.bak-skill74-$(date -u +%Y%m%dT%H%M%SZ)"
  cat "$tmp" > "$file"
  rm -f "$tmp"
  CHANGED=1
  echo "[skill 74] $(basename "$file"): wrote block '$target' (replace-in-place)"
}

write_block "$WS/AGENTS.md" agents "$AGENTS_BODY"
write_block "$WS/TOOLS.md"  tools  "$TOOLS_BODY"

SENTINEL="<!-- skill:${SKILL_SLUG}:core-update-applied -->"
if ! grep -qF "$SENTINEL" "$WS/AGENTS.md" 2>/dev/null; then
  printf '\n%s\n' "$SENTINEL" >> "$WS/AGENTS.md"
  echo "[skill 74] stamped $SENTINEL"
fi

echo "[skill 74] core-file wiring complete (workspace: $WS; changed=$CHANGED)"
exit 0

#!/bin/bash
# add-persona-from-source.sh — v10.14.32
#
# v10.14.32 — YouTube + local-video branches rewritten to use yt-dlp / whisper-cpp
# directly. Pre-v10.14.32 the YouTube branch shelled out to a `summarize` CLI
# (Skill 16) that does not exist as an executable on any VPS install — every
# YouTube source bombed out with exit 3/4 before Phase 1 ran. See CHANGELOG.
#
# Pipeline now:
#   YouTube  → yt-dlp auto-subs (free)  → VTT-to-text  → text file
#               ↓ (if auto-subs unavailable)
#             yt-dlp audio extract     → whisper-cpp transcribe → text file
#   Local-video → ffmpeg audio extract → whisper-cpp transcribe → text file
#
# Requires (auto-installed by install.sh + update-skills.sh in v10.14.32+):
#   yt-dlp, whisper-cpp (or whisper), ffmpeg
#
#
# Unified entry point for adding a new persona to the coaching-personas library.
# Accepts any of these source types and routes to the right extractor:
#
#   - Book PDF / EPUB / MOBI / AZW3 file path
#   - YouTube URL (single video or channel)
#   - Local video file (mp4 / mov / mkv)
#   - Plain text file (already transcribed)
#
# After extraction, the resulting text is dropped into Skill 22's input folder
# and the standard 3-phase pipeline runs (Extraction → Analysis → Synthesis).
# Result: a new persona-blueprint.md indexed by Gemini Engine and added to the
# governing-personas pool for every relevant department.
#
# USAGE:
#   add-persona-from-source.sh --source <path-or-url> [--title "Title"] [--author "Name"]
#
# EXAMPLES:
#   add-persona-from-source.sh --source "/Users/me/Books/Atomic Habits.pdf"
#   add-persona-from-source.sh --source "https://youtube.com/watch?v=abc123" \
#                              --title "Hormozi Million Dollar Offers Talk" \
#                              --author "Alex Hormozi"
#   add-persona-from-source.sh --source "/Users/me/Videos/seminar.mp4" \
#                              --title "Seth Godin Keynote" --author "Seth Godin"

set -u
# v10.14.32: pipefail so failures inside `cmd | tee log` chains return non-zero.
# Without this, Track-I forensic showed the YouTube branch could exit 0 while
# the underlying summarize call wrote 0 bytes to TEXT_FILE.
set -o pipefail

# ─── ARGS ────────────────────────────────────────────────────────────────────
SOURCE=""
TITLE=""
AUTHOR=""
SKIP_INDEX=false

while [ $# -gt 0 ]; do
  case "$1" in
    --source)      SOURCE="$2"; shift 2 ;;
    --title)       TITLE="$2"; shift 2 ;;
    --author)      AUTHOR="$2"; shift 2 ;;
    --skip-index)  SKIP_INDEX=true; shift ;;
    --help|-h)
      sed -n '1,30p' "$0"
      exit 0
      ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

if [ -z "$SOURCE" ]; then
  echo "ERROR: --source is required (book file, YouTube URL, or video file)"
  echo "Run with --help for examples."
  exit 1
fi

# ─── CANONICAL PATHS (Hostinger Docker VPS) ──────────────────────────────────
WORKSPACE=/data/.openclaw/workspace
MASTER=/data/.openclaw/master-files

PERSONA_DIR="$MASTER/coaching-personas"
TEXT_DIR="$PERSONA_DIR/text"
mkdir -p "$TEXT_DIR"

red()    { printf "\033[31m%s\033[0m\n" "$1"; }
green()  { printf "\033[32m%s\033[0m\n" "$1"; }
yellow() { printf "\033[33m%s\033[0m\n" "$1"; }
blue()   { printf "\033[34m%s\033[0m\n" "$1"; }

# ─── SOURCE TYPE DETECTION ───────────────────────────────────────────────────
detect_source_type() {
  local s="$1"
  if echo "$s" | grep -qE '^https?://.*youtube\.com|^https?://youtu\.be/'; then
    echo "youtube"
  elif echo "$s" | grep -qE '^https?://'; then
    echo "http"
  elif [ -f "$s" ]; then
    case "${s,,}" in
      *.pdf|*.epub|*.mobi|*.azw3) echo "book" ;;
      *.mp4|*.mov|*.mkv|*.avi|*.webm) echo "video" ;;
      *.txt|*.md) echo "text" ;;
      *) echo "unknown" ;;
    esac
  else
    echo "missing"
  fi
}

# bash-3.2 compat: case lowercasing
SOURCE_LC=$(echo "$SOURCE" | tr '[:upper:]' '[:lower:]')
TYPE=""
if echo "$SOURCE" | grep -qE '^https?://.*youtube\.com|^https?://youtu\.be/'; then
  TYPE="youtube"
elif echo "$SOURCE" | grep -qE '^https?://'; then
  TYPE="http"
elif [ -f "$SOURCE" ]; then
  case "$SOURCE_LC" in
    *.pdf|*.epub|*.mobi|*.azw3) TYPE="book" ;;
    *.mp4|*.mov|*.mkv|*.avi|*.webm) TYPE="video" ;;
    *.txt|*.md) TYPE="text" ;;
    *) TYPE="unknown" ;;
  esac
else
  TYPE="missing"
fi

blue "═══════════════════════════════════════════════════"
blue "  Add Persona From Source — v10.14.32"
blue "═══════════════════════════════════════════════════"
echo "Source: $SOURCE"
echo "Type:   $TYPE"
echo "Title:  ${TITLE:-<auto-detect>}"
echo "Author: ${AUTHOR:-<auto-detect>}"
echo ""

# ─── EXTRACT TO TEXT ─────────────────────────────────────────────────────────
TEXT_FILE=""
SLUG=""

case "$TYPE" in
  book)
    blue "── Extracting book text via pdfplumber ──"
    # Slug = author-title (or fall back to filename)
    BASENAME=$(basename "$SOURCE")
    BASENAME_NO_EXT="${BASENAME%.*}"
    if [ -n "$AUTHOR" ] && [ -n "$TITLE" ]; then
      SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    else
      SLUG=$(echo "$BASENAME_NO_EXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    fi
    TEXT_FILE="$TEXT_DIR/$SLUG.txt"
    python3 - <<PYEOF
import sys
try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)
text = ""
with pdfplumber.open("$SOURCE") as pdf:
    for page in pdf.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
with open("$TEXT_FILE", "w") as f:
    f.write(text)
print(f"Wrote {len(text):,} chars to $TEXT_FILE")
PYEOF
    [ $? -ne 0 ] && { red "Book extraction failed"; exit 2; }
    ;;

  youtube)
    # v10.14.32: rewritten — direct yt-dlp invocation. The old branch shelled
    # out to a `summarize` CLI (Skill 16) which doesn't exist as an executable
    # on any VPS install. Forensic Track I (2026-05-23) traced every YouTube
    # persona failure to this branch. Now:
    #   1. Try yt-dlp auto-subs (free, fast, no API cost)
    #   2. Convert .en.vtt → plain text (strip timestamps + dupes)
    #   3. Fallback: yt-dlp -x audio + whisper-cpp transcribe
    blue "── Extracting YouTube transcript via yt-dlp + whisper-cpp ──"

    if ! command -v yt-dlp >/dev/null 2>&1; then
      red "ERROR: yt-dlp not installed."
      red "  Install: brew install yt-dlp   (or)  pip3 install --user yt-dlp"
      red "  install.sh v10.14.32+ auto-installs yt-dlp + whisper-cpp + ffmpeg."
      exit 3
    fi

    YT_ID=$(echo "$SOURCE" | sed -E 's|.*(youtu\.be/\|v=)([A-Za-z0-9_-]+).*|\2|')
    if [ -z "$AUTHOR" ]; then
      yellow "  --author not specified; the persona will be named by video title."
      AUTHOR="unknown"
    fi
    if [ -z "$TITLE" ]; then
      TITLE="youtube-$YT_ID"
    fi
    SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    TEXT_FILE="$TEXT_DIR/$SLUG.txt"

    # ── Step 1: try auto-subs (cost = 0, time = seconds) ──
    yellow "  Attempting yt-dlp auto-subs (free, fast)..."
    YT_LOG="/tmp/yt-dlp-$SLUG-$$.log"
    yt-dlp \
      --skip-download \
      --write-auto-subs \
      --sub-format vtt \
      --sub-lang en \
      -o "$TEXT_DIR/$SLUG" \
      "$SOURCE" > "$YT_LOG" 2>&1 || true

    VTT_FILE="$TEXT_DIR/$SLUG.en.vtt"
    if [ -f "$VTT_FILE" ] && [ -s "$VTT_FILE" ]; then
      green "  Auto-subs found ($(wc -c < "$VTT_FILE" | tr -d ' ') bytes). Converting to text..."
      VTT_FILE_ENV="$VTT_FILE" TEXT_FILE_ENV="$TEXT_FILE" python3 <<'PYEOF'
import os, re
vtt_path = os.environ["VTT_FILE_ENV"]
txt_path = os.environ["TEXT_FILE_ENV"]
with open(vtt_path, "r", encoding="utf-8", errors="ignore") as f:
    raw = f.read()
# VTT header keys that aren't transcript content
HEADER_KEYS = ("Kind:", "Language:", "X-TIMESTAMP-MAP", "STYLE", "REGION")
lines = raw.splitlines()
out_lines = []
seen = set()
for ln in lines:
    s = ln.strip()
    if not s: continue
    if s.startswith("WEBVTT"): continue
    if s.startswith("NOTE"): continue
    if any(s.startswith(k) for k in HEADER_KEYS): continue
    # Cue identifiers (plain integer)
    if re.match(r"^\d+$", s): continue
    # Timing lines: HH:MM:SS.mmm --> HH:MM:SS.mmm  (or MM:SS.mmm -->)
    if re.match(r"^\d{1,2}:\d{2}(:\d{2})?\.\d{3}\s*-->\s*\d{1,2}:\d{2}(:\d{2})?\.\d{3}", s): continue
    # 2. Strip inline timestamp tags like <00:00:01.000> and speaker tags like <v Speaker>
    s = re.sub(r"<[^>]+>", "", s)
    # 3. Strip cue settings appended after timing (align:start position:0%)
    s = re.sub(r"\s+(align|position|line|size|vertical):\S+", "", s)
    s = s.strip()
    if not s: continue
    # 4. Dedupe identical lines (YouTube auto-caps repeat rolling text)
    if s in seen: continue
    seen.add(s)
    out_lines.append(s)
text = "\n".join(out_lines) + "\n"
with open(txt_path, "w", encoding="utf-8") as f:
    f.write(text)
print(f"  Wrote {len(text):,} chars to {txt_path}")
PYEOF
      rm -f "$VTT_FILE"
    else
      # ── Step 2: fallback to audio download + whisper transcription ──
      yellow "  No auto-subs available. Falling back to audio + whisper-cpp transcription."
      if ! command -v whisper-cpp >/dev/null 2>&1 && ! command -v whisper-cli >/dev/null 2>&1 && ! command -v whisper >/dev/null 2>&1; then
        red "ERROR: no whisper backend installed (whisper-cpp / whisper-cli / whisper)."
        red "  Install: brew install whisper-cpp   (or)  pip3 install --user openai-whisper"
        red "  See $YT_LOG for yt-dlp's auto-subs failure details."
        exit 3
      fi

      MP3_FILE="$TEXT_DIR/$SLUG.mp3"
      yt-dlp -x --audio-format mp3 -o "$TEXT_DIR/$SLUG.%(ext)s" "$SOURCE" >> "$YT_LOG" 2>&1
      if [ ! -s "$MP3_FILE" ]; then
        red "yt-dlp audio download failed. See $YT_LOG."
        exit 4
      fi
      green "  Audio downloaded ($(wc -c < "$MP3_FILE" | tr -d ' ') bytes). Transcribing with whisper..."

      if command -v whisper-cpp >/dev/null 2>&1; then
        whisper-cpp -m base -otxt -of "${TEXT_FILE%.txt}" -f "$MP3_FILE" >> "$YT_LOG" 2>&1 || true
      elif command -v whisper-cli >/dev/null 2>&1; then
        whisper-cli -m base -otxt -of "${TEXT_FILE%.txt}" -f "$MP3_FILE" >> "$YT_LOG" 2>&1 || true
      else
        whisper "$MP3_FILE" --model base --output_format txt --output_dir "$TEXT_DIR" >> "$YT_LOG" 2>&1 || true
        # `whisper` writes <basename>.txt — make sure it lands at TEXT_FILE
        WHISPER_OUT="$TEXT_DIR/$SLUG.txt"
        [ "$WHISPER_OUT" != "$TEXT_FILE" ] && [ -f "$WHISPER_OUT" ] && mv "$WHISPER_OUT" "$TEXT_FILE"
      fi
      rm -f "$MP3_FILE"
    fi

    if [ ! -s "$TEXT_FILE" ]; then
      red "YouTube transcript extraction failed (text file empty or missing)."
      red "  Source:   $SOURCE"
      red "  yt-dlp log: $YT_LOG"
      exit 4
    fi
    green "  Transcript saved: $TEXT_FILE ($(wc -c < "$TEXT_FILE" | tr -d ' ') chars)"
    ;;

  video)
    # v10.14.32: prefer whisper-cpp (fast, no GPU); fallback to whisper-cli
    # and finally to python `whisper`. yt-dlp is NOT the entry — ffmpeg
    # extracts audio directly from the local file.
    blue "── Extracting transcript from local video via ffmpeg + whisper-cpp ──"
    if ! command -v ffmpeg >/dev/null 2>&1; then
      red "ERROR: ffmpeg not installed."
      red "  Install: brew install ffmpeg   (or)  apt-get install -y ffmpeg"
      red "  install.sh v10.14.32+ auto-installs ffmpeg."
      exit 3
    fi
    if ! command -v whisper-cpp >/dev/null 2>&1 && ! command -v whisper-cli >/dev/null 2>&1 && ! command -v whisper >/dev/null 2>&1; then
      red "ERROR: no whisper backend installed (whisper-cpp / whisper-cli / whisper)."
      red "  Install: brew install whisper-cpp   (or)  pip3 install --user openai-whisper"
      exit 3
    fi

    BASENAME=$(basename "$SOURCE")
    BASENAME_NO_EXT="${BASENAME%.*}"
    if [ -n "$AUTHOR" ] && [ -n "$TITLE" ]; then
      SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    else
      SLUG=$(echo "$BASENAME_NO_EXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    fi
    TEXT_FILE="$TEXT_DIR/$SLUG.txt"
    AUDIO_TMP="/tmp/persona-audio-$$.wav"
    VIDEO_LOG="/tmp/persona-video-$SLUG-$$.log"

    # Extract audio (16 kHz mono PCM — whisper.cpp's preferred input)
    ffmpeg -i "$SOURCE" -ar 16000 -ac 1 -c:a pcm_s16le "$AUDIO_TMP" -y > "$VIDEO_LOG" 2>&1
    [ ! -s "$AUDIO_TMP" ] && { red "ffmpeg audio extraction failed. See $VIDEO_LOG."; exit 4; }

    if command -v whisper-cpp >/dev/null 2>&1; then
      whisper-cpp -m base -otxt -of "${TEXT_FILE%.txt}" -f "$AUDIO_TMP" >> "$VIDEO_LOG" 2>&1 || true
    elif command -v whisper-cli >/dev/null 2>&1; then
      whisper-cli -m base -otxt -of "${TEXT_FILE%.txt}" -f "$AUDIO_TMP" >> "$VIDEO_LOG" 2>&1 || true
    else
      whisper "$AUDIO_TMP" --model base --output_format txt --output_dir "$TEXT_DIR" >> "$VIDEO_LOG" 2>&1 || true
      WHISPER_OUT="$TEXT_DIR/$(basename "$AUDIO_TMP" .wav).txt"
      [ -f "$WHISPER_OUT" ] && mv "$WHISPER_OUT" "$TEXT_FILE"
    fi
    rm -f "$AUDIO_TMP"
    [ ! -s "$TEXT_FILE" ] && { red "Whisper transcription failed. See $VIDEO_LOG."; exit 4; }
    green "  Transcript saved: $TEXT_FILE ($(wc -c < "$TEXT_FILE" | tr -d ' ') chars)"
    ;;

  text)
    blue "── Source is already plain text; copying to text dir ──"
    BASENAME=$(basename "$SOURCE")
    BASENAME_NO_EXT="${BASENAME%.*}"
    if [ -n "$AUTHOR" ] && [ -n "$TITLE" ]; then
      SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    else
      SLUG=$(echo "$BASENAME_NO_EXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    fi
    TEXT_FILE="$TEXT_DIR/$SLUG.txt"
    cp "$SOURCE" "$TEXT_FILE"
    green "  Copied: $TEXT_FILE"
    ;;

  http)
    red "ERROR: Generic HTTP URLs not supported yet (only YouTube URLs)."
    red "Workaround: download the page text and pass as a local .txt file."
    exit 1
    ;;

  unknown|missing)
    red "ERROR: Source type unrecognized or file missing."
    red "  Got: $SOURCE"
    red "  Supported: .pdf .epub .mobi .azw3 (books), .mp4 .mov .mkv .avi .webm (video),"
    red "             .txt .md (already-transcribed text), youtube.com / youtu.be URLs."
    exit 1
    ;;
esac

# ─── ENQUEUE INTO SKILL 22 PIPELINE ──────────────────────────────────────────
blue "── Registering in Skill 22 pipeline ──"
PERSONA_FOLDER="$PERSONA_DIR/personas/$SLUG"
mkdir -p "$PERSONA_FOLDER"

# Write a marker file the pipeline can pick up
cat > "$PERSONA_FOLDER/source.json" <<JSONEOF
{
  "slug": "$SLUG",
  "title": "${TITLE:-$SLUG}",
  "author": "${AUTHOR:-unknown}",
  "source_type": "$TYPE",
  "source_path": "$SOURCE",
  "text_file": "$TEXT_FILE",
  "added": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "pipeline_status": "PENDING"
}
JSONEOF

green "  Persona folder ready: $PERSONA_FOLDER"
echo "  Text input:          $TEXT_FILE"

# ─── INVOKE PIPELINE ─────────────────────────────────────────────────────────
ORCHESTRATOR="/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"
[ ! -f "$ORCHESTRATOR" ] && ORCHESTRATOR="/data/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"

if [ ! -f "$ORCHESTRATOR" ]; then
  yellow "  Skill 22 orchestrator not found at expected path."
  yellow "  Persona registered but NOT yet run through pipeline. Run manually:"
  yellow "    python3 <orchestrator-path> --single-book --slug $SLUG"
  exit 0
fi

blue "── Invoking Skill 22 3-phase pipeline ──"
echo "  Running: python3 $ORCHESTRATOR --single-book --slug $SLUG"
python3 "$ORCHESTRATOR" --single-book --slug "$SLUG" 2>&1 | tail -20
PIPELINE_RC=$?

if [ "$PIPELINE_RC" -ne 0 ]; then
  red "Pipeline reported non-zero exit ($PIPELINE_RC). Persona may be partial."
  yellow "Check $PERSONA_FOLDER for what was produced."
  exit "$PIPELINE_RC"
fi

green "  Pipeline complete. Blueprint at: $PERSONA_FOLDER/persona-blueprint.md"

# ─── RE-INDEX GEMINI ─────────────────────────────────────────────────────────
if [ "$SKIP_INDEX" = "false" ]; then
  blue "── Re-indexing Gemini Engine (coaching-personas + workspace) ──"
  INDEXER=""
  for c in "$WORKSPACE/scripts/gemini-indexer.py" "/data/.openclaw/workspace/scripts/gemini-indexer.py"; do
    [ -f "$c" ] && INDEXER="$c" && break
  done
  if [ -n "$INDEXER" ]; then
    python3 "$INDEXER" 2>&1 | tail -5
    green "  Gemini index refreshed. New persona is now searchable."
  else
    yellow "  gemini-indexer.py not found; persona blueprint written but not yet indexed."
    yellow "  Run manually: python3 /data/.openclaw/scripts/gemini-indexer.py"
  fi
fi

# ─── UPDATE persona-categories.json ──────────────────────────────────────────
# v10.14.32: bootstrap the file on fresh VPS installs. Pre-v10.14.32 the gate
# below silently no-op'd when the file was missing, so on a brand-new VPS the
# FIRST persona produced was never indexed — Track-I forensic root cause for
# Lyric's "selector returns 0 candidates" symptom.
CAT_FILE="$PERSONA_DIR/persona-categories.json"
if [ ! -f "$CAT_FILE" ]; then
  blue "── Bootstrapping persona-categories.json (first persona on this VPS) ──"
  mkdir -p "$(dirname "$CAT_FILE")"
  cat > "$CAT_FILE" <<JSON_EOF
{
  "schemaVersion": "1.0",
  "created": "$(date -u +%Y-%m-%d)",
  "domainTags": {},
  "perspectiveTags": {},
  "personas": {}
}
JSON_EOF
  green "  Created $CAT_FILE"
fi

if [ -f "$CAT_FILE" ]; then
  blue "── Updating persona-categories.json ──"
  python3 - <<PYEOF
import json
cat_file = "$CAT_FILE"
slug = "$SLUG"
with open(cat_file) as f:
    data = json.load(f)
personas = data.get("personas", {}) if "personas" in data else data
if slug not in personas:
    personas[slug] = {
        "domain_tags": [],   # Tag manually or via post-processor
        "perspective_tags": [],
        "source_type": "$TYPE",
        "added": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    }
    if "personas" in data:
        data["personas"] = personas
    else:
        data.update(personas)
    with open(cat_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Added $SLUG to persona-categories.json (no tags yet — review and tag)")
else:
    print(f"  $SLUG already in persona-categories.json")
PYEOF
fi

echo ""
green "═══════════════════════════════════════════════════"
green "  ✓ Persona added: $SLUG"
green "═══════════════════════════════════════════════════"
echo "  Blueprint:          $PERSONA_FOLDER/persona-blueprint.md"
echo "  Source text:        $TEXT_FILE"
echo "  Searchable via:     python3 /data/.openclaw/scripts/gemini-search.py --query \"<task>\""
echo ""
yellow "  NEXT STEP: open persona-categories.json and add domain_tags + perspective_tags for $SLUG."
yellow "  Without tags, the keyword filter in select-persona-for-task.py won't include this persona"
yellow "  in dept-scoped candidate pools."

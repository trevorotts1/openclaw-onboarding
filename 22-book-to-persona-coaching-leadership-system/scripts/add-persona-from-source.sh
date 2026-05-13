#!/bin/bash
# add-persona-from-source.sh — v9.6.4
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

# ─── PLATFORM DETECT ─────────────────────────────────────────────────────────
if [ -d "/data/.openclaw" ]; then
  WORKSPACE=/data/clawd
  MASTER=/data/Downloads/openclaw-master-files
else
  WORKSPACE=$HOME/clawd
  MASTER=$HOME/Downloads/openclaw-master-files
fi

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
blue "  Add Persona From Source — v9.6.4"
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
    blue "── Extracting YouTube transcript via Skill 16 (Summarize YouTube) ──"
    if ! command -v summarize >/dev/null 2>&1 && [ ! -f "$HOME/clawd/scripts/summarize.sh" ]; then
      red "ERROR: Skill 16 (Summarize YouTube) not installed. Run install.sh first or"
      red "       install summarize CLI: see ~/.openclaw/skills/16-summarize-youtube/INSTALL.md"
      exit 3
    fi

    # Use summarize CLI to pull transcript (--transcript-only flag if supported)
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

    SUMMARIZE_CMD="summarize"
    [ -f "$HOME/clawd/scripts/summarize.sh" ] && SUMMARIZE_CMD="bash $HOME/clawd/scripts/summarize.sh"

    # Try transcript-only first, fall back to full output
    $SUMMARIZE_CMD --transcript-only "$SOURCE" > "$TEXT_FILE" 2>/dev/null \
        || $SUMMARIZE_CMD "$SOURCE" > "$TEXT_FILE" 2>/dev/null

    if [ ! -s "$TEXT_FILE" ]; then
      red "YouTube transcript extraction failed. Check that Skill 16 is configured "
      red "with valid OPENAI_API_KEY or GEMINI_API_KEY in ~/.openclaw/secrets/.env"
      exit 4
    fi
    green "  Transcript saved: $TEXT_FILE ($(wc -c < "$TEXT_FILE" | tr -d ' ') chars)"
    ;;

  video)
    blue "── Extracting transcript from local video via Whisper / ffmpeg ──"
    if ! command -v ffmpeg >/dev/null 2>&1; then
      red "ERROR: ffmpeg not installed. Install via 'brew install ffmpeg' (Mac) or apt (Linux)"
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

    # Extract audio
    ffmpeg -i "$SOURCE" -ar 16000 -ac 1 -c:a pcm_s16le "$AUDIO_TMP" -y 2>/dev/null
    [ ! -s "$AUDIO_TMP" ] && { red "ffmpeg audio extraction failed"; exit 4; }

    # Transcribe via whisper (or whisper.cpp if available)
    if command -v whisper >/dev/null 2>&1; then
      whisper "$AUDIO_TMP" --output_format txt --output_dir "$TEXT_DIR" --model base 2>/dev/null
      mv "$TEXT_DIR/$(basename "$AUDIO_TMP" .wav).txt" "$TEXT_FILE" 2>/dev/null
    elif command -v whisper-cli >/dev/null 2>&1; then
      whisper-cli -f "$AUDIO_TMP" -otxt -of "${TEXT_FILE%.txt}" 2>/dev/null
    else
      red "ERROR: whisper or whisper-cli not installed. Install via 'pip install openai-whisper' or whisper.cpp"
      rm -f "$AUDIO_TMP"
      exit 3
    fi
    rm -f "$AUDIO_TMP"
    [ ! -s "$TEXT_FILE" ] && { red "Whisper transcription failed"; exit 4; }
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
ORCHESTRATOR="$HOME/.openclaw/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"
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
  for c in "$WORKSPACE/scripts/gemini-indexer.py" "$HOME/.openclaw/workspace/scripts/gemini-indexer.py"; do
    [ -f "$c" ] && INDEXER="$c" && break
  done
  if [ -n "$INDEXER" ]; then
    python3 "$INDEXER" 2>&1 | tail -5
    green "  Gemini index refreshed. New persona is now searchable."
  else
    yellow "  gemini-indexer.py not found; persona blueprint written but not yet indexed."
    yellow "  Run manually: python3 ~/clawd/scripts/gemini-indexer.py"
  fi
fi

# ─── UPDATE persona-categories.json ──────────────────────────────────────────
CAT_FILE="$PERSONA_DIR/persona-categories.json"
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
echo "  Searchable via:     python3 ~/clawd/scripts/gemini-search.py --query \"<task>\""
echo ""
yellow "  NEXT STEP: open persona-categories.json and add domain_tags + perspective_tags for $SLUG."
yellow "  Without tags, the keyword filter in select-persona-for-task.py won't include this persona"
yellow "  in dept-scoped candidate pools."

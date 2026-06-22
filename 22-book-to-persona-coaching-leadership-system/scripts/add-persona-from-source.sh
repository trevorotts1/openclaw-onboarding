#!/bin/bash
# add-persona-from-source.sh — v10.14.34
#
# v10.14.34 — G1: Mac platform resolver added (mirrors persona-inbox-watcher.sh:51-57
#   and pipeline/orchestrator.py:52-60). Previously hardcoded VPS paths
#   (WORKSPACE=/data/.openclaw/workspace, MASTER=/data/.openclaw/master-files)
#   caused silent failure on every Mac client box. Now resolves:
#     VPS: OC_ROOT=/data/.openclaw
#     Mac: OC_ROOT=~/.openclaw
#   PERSONA_DIR, WORKSPACE, MASTER, ORCHESTRATOR, INDEXER, and the final
#   gemini-search hint message are all derived from $OC_ROOT.
#
# v10.14.33 — Skill 22 v6.6.1 source-ingestion bug fixes:
#   1. EPUB/MOBI/AZW3 ebook extraction mis-wire fixed: old code forced pdfplumber on
#      every book format (always produced empty/garbage for non-PDF files).  PDF keeps
#      inline pdfplumber.  EPUB/MOBI/AZW3/KFX skip pre-extraction; source.json gets
#      empty text_file so orchestrator extract_book_text() does the right dispatch
#      (ebooklib for EPUB, mobi lib for MOBI, Calibre ebook-convert for AZW/KFX).
#   2. Generic HTTP(S) URLs now supported via curl + BeautifulSoup HTML→text.
#   3. New personas auto-classified: domain/perspective tags derived from title/author/slug
#      via keyword matching; no longer written as empty arrays that make personas
#      invisible to the dept-scope filter.
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

# ─── PLATFORM RESOLVER ───────────────────────────────────────────────────────
# Mirrors persona-inbox-watcher.sh:51-57 and pipeline/orchestrator.py:52-60
# VPS (Hostinger Docker):  /data/.openclaw
# Mac (homebrew openclaw): ~/.openclaw
if [ -d /data/.openclaw ]; then
  OC_ROOT="/data/.openclaw"
elif [ -d "$HOME/.openclaw" ]; then
  OC_ROOT="$HOME/.openclaw"
else
  # Legacy fallback kept for backward compat
  OC_ROOT="$HOME/.openclaw"
fi

WORKSPACE="$OC_ROOT/workspace"
MASTER="$OC_ROOT/master-files"

# Skill 22 pipeline location mirrors how orchestrator.py resolves itself
# VPS: /data/.openclaw/master-files/coaching-personas
# Mac: ~/.openclaw/workspace/data/coaching-personas
if [ -d "$OC_ROOT/master-files" ]; then
  PERSONA_DIR="$OC_ROOT/master-files/coaching-personas"
else
  PERSONA_DIR="$OC_ROOT/workspace/data/coaching-personas"
fi

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
blue "  Add Persona From Source — v10.14.33"
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
    # Slug = author-title (or fall back to filename)
    BASENAME=$(basename "$SOURCE")
    BASENAME_NO_EXT="${BASENAME%.*}"
    EXT_LC=$(echo "${BASENAME##*.}" | tr '[:upper:]' '[:lower:]')
    if [ -n "$AUTHOR" ] && [ -n "$TITLE" ]; then
      SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    else
      SLUG=$(echo "$BASENAME_NO_EXT" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    fi

    if [ "$EXT_LC" = "pdf" ]; then
      # v6.6.1 FIX: PDF gets inline pdfplumber pre-extraction (keeps existing behaviour).
      blue "── Extracting PDF text via pdfplumber ──"
      TEXT_FILE="$TEXT_DIR/$SLUG.txt"
      SOURCE_ENV="$SOURCE" TEXT_FILE_ENV="$TEXT_FILE" python3 <<'PYEOF'
import sys, os
src = os.environ["SOURCE_ENV"]
dst = os.environ["TEXT_FILE_ENV"]
try:
    import pdfplumber
except ImportError:
    print("ERROR: pdfplumber not installed. Run: pip install pdfplumber")
    sys.exit(1)
text = ""
with pdfplumber.open(src) as pdf:
    for page in pdf.pages:
        t = page.extract_text()
        if t:
            text += t + "\n"
if not text.strip():
    # pdfplumber produced nothing — fall through without writing so orchestrator handles it
    print(f"WARNING: pdfplumber returned empty text for {src}; orchestrator will use pypdf fallback")
    sys.exit(0)
with open(dst, "w") as f:
    f.write(text)
print(f"Wrote {len(text):,} chars to {dst}")
PYEOF
      PYRC=$?
      [ "$PYRC" -ne 0 ] && { red "PDF pre-extraction failed"; exit 2; }
      # If pdfplumber wrote nothing, leave TEXT_FILE empty/absent so orchestrator falls back
      [ ! -s "$TEXT_FILE" ] && TEXT_FILE=""
    else
      # v6.6.1 FIX (primary): EPUB / MOBI / AZW3 / KFX — skip shell-side pre-extraction
      # entirely.  The old branch forced pdfplumber on every ebook format, which always
      # produced empty/garbage text for non-PDF files.  Instead we pass the raw source file
      # directly to the orchestrator, which already has a correct multi-format dispatch in
      # extract_book_text(): ebooklib for EPUB, mobi library for MOBI, Calibre ebook-convert
      # for AZW/AZW3/KFX.  TEXT_FILE is intentionally left blank here so that source.json
      # has an empty "text_file" field, and run_extraction() will skip the _pre_text_path
      # branch (L1010) and fall through to the book-file extraction path (L1026+).
      blue "── EPUB/MOBI/AZW3: delegating text extraction to orchestrator (ebooklib/mobi/Calibre) ──"
      yellow "  File: $SOURCE  (format: .$EXT_LC)"
      yellow "  Pre-extraction SKIPPED in script — orchestrator extract_book_text() will handle it."
      TEXT_FILE=""
    fi
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
    # v6.6.1 FIX: generic web URL — fetch page + extract readable text via BeautifulSoup.
    blue "── Fetching generic web URL ──"
    echo "  URL: $SOURCE"
    if [ -z "$TITLE" ]; then
      # Extract title from URL path
      TITLE=$(echo "$SOURCE" | sed -E 's|https?://[^/]+/||; s/[?#].*//; s|/$||; s|/|-|g; s/[^a-zA-Z0-9 -]//g' | head -c 80)
      [ -z "$TITLE" ] && TITLE="web-page"
    fi
    if [ -z "$AUTHOR" ]; then
      # Use the hostname as a stand-in for author
      AUTHOR=$(echo "$SOURCE" | sed -E 's|https?://([^/]+).*|\1|; s/^www\.//')
    fi
    SLUG=$(echo "$AUTHOR-$TITLE" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/-/g; s/-\{2,\}/-/g; s/^-//; s/-$//')
    TEXT_FILE="$TEXT_DIR/$SLUG.txt"

    # Step 1: download with curl (follow redirects, 30s timeout)
    HTML_TMP="/tmp/persona-web-$SLUG-$$.html"
    curl -fsSL --max-time 30 -A "Mozilla/5.0" -o "$HTML_TMP" "$SOURCE" 2>/tmp/persona-curl-$$.err
    if [ ! -s "$HTML_TMP" ]; then
      red "ERROR: curl failed to fetch URL: $SOURCE"
      cat /tmp/persona-curl-$$.err
      exit 4
    fi
    green "  Downloaded $(wc -c < "$HTML_TMP" | tr -d ' ') bytes"

    # Step 2: extract readable text via BeautifulSoup (already installed per dep audit)
    HTML_TMP_ENV="$HTML_TMP" TEXT_FILE_ENV="$TEXT_FILE" python3 <<'PYEOF'
import sys, os
html_path = os.environ["HTML_TMP_ENV"]
txt_path  = os.environ["TEXT_FILE_ENV"]
try:
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: beautifulsoup4 not installed. Run: pip3 install beautifulsoup4")
    sys.exit(1)
with open(html_path, "rb") as f:
    raw = f.read()
soup = BeautifulSoup(raw, "html.parser")
# Remove script, style, nav, header, footer, ads
for tag in soup(["script", "style", "nav", "header", "footer", "aside", "noscript", "iframe"]):
    tag.decompose()
# Try <article> or <main> first; fall back to <body>
article = soup.find("article") or soup.find("main") or soup.find("body") or soup
text = article.get_text(separator="\n")
# Collapse blank lines
import re
text = re.sub(r"\n{3,}", "\n\n", text).strip()
if not text:
    print("ERROR: BeautifulSoup extracted empty text from page")
    sys.exit(2)
with open(txt_path, "w", encoding="utf-8") as f:
    f.write(text + "\n")
print(f"  Extracted {len(text):,} chars to {txt_path}")
PYEOF
    PYRC=$?
    rm -f "$HTML_TMP" /tmp/persona-curl-$$.err
    [ "$PYRC" -ne 0 ] && { red "Web page text extraction failed"; exit 4; }
    [ ! -s "$TEXT_FILE" ] && { red "Web text extraction produced empty file"; exit 4; }
    green "  Web page text saved: $TEXT_FILE ($(wc -c < "$TEXT_FILE" | tr -d ' ') chars)"
    ;;

  unknown|missing)
    red "ERROR: Source type unrecognized or file missing."
    red "  Got: $SOURCE"
    red "  Supported: .pdf .epub .mobi .azw3 (books), .mp4 .mov .mkv .avi .webm (video),"
    red "             .txt .md (already-transcribed text), youtube.com / youtu.be URLs,"
    red "             http(s):// generic web URLs."
    exit 1
    ;;
esac

# ─── ENQUEUE INTO SKILL 22 PIPELINE ──────────────────────────────────────────
blue "── Registering in Skill 22 pipeline ──"
PERSONA_FOLDER="$PERSONA_DIR/personas/$SLUG"
mkdir -p "$PERSONA_FOLDER"

# Write a marker file the pipeline can pick up.
# v6.6.1: for EPUB/MOBI/AZW3 book types TEXT_FILE is intentionally empty —
# the orchestrator's extract_book_text() handles those formats via its own
# multi-format dispatch.  An empty "text_file" field tells run_extraction()
# to skip the _pre_text_path shortcut and go straight to book-file extraction.
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
# Resolve orchestrator path from $OC_ROOT (platform-resolved above)
ORCHESTRATOR="$OC_ROOT/skills/22-book-to-persona-coaching-leadership-system/pipeline/orchestrator.py"
# Fallback: try relative to this script's own location (works for dev/repo runs)
if [ ! -f "$ORCHESTRATOR" ]; then
  SCRIPT_DIR_APS="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  ORCHESTRATOR="$(cd "$SCRIPT_DIR_APS/.." && pwd)/pipeline/orchestrator.py"
fi

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
  # a71f6bbd path-drift fix: the canonical INSTALLED wrapper is
  # $OC_ROOT/scripts/gemini-indexer.py (Mac: ~/.openclaw/scripts, VPS:
  # /data/.openclaw/scripts). The pre-fix loop probed only
  # $OC_ROOT/workspace/scripts/gemini-indexer.py — a path that does not exist on
  # any current install — so this safety-net re-index silently printed
  # "not found" even on healthy boxes. Candidate order now mirrors
  # orchestrator.py Phase 5 (scripts/ first, workspace/scripts/ as legacy
  # fallback). NOTE: orchestrator.py already runs Phase 5 re-indexing above;
  # this block is an idempotent safety net (the indexer skips unchanged files
  # by content hash) and honors --skip-index.
  INDEXER=""
  for c in "$OC_ROOT/scripts/gemini-indexer.py" "$WORKSPACE/scripts/gemini-indexer.py" "$OC_ROOT/workspace/scripts/gemini-indexer.py"; do
    [ -f "$c" ] && INDEXER="$c" && break
  done
  if [ -n "$INDEXER" ]; then
    python3 "$INDEXER" 2>&1 | tail -5
    green "  Gemini index refreshed. New persona is now searchable."
  else
    yellow "  gemini-indexer.py not found; persona blueprint written but not yet indexed."
    yellow "  Run manually: python3 $OC_ROOT/scripts/gemini-indexer.py"
  fi
fi

# ─── UPDATE persona-categories.json ──────────────────────────────────────────
# v10.14.32: bootstrap the file on fresh VPS installs. Pre-v10.14.32 the gate
# below silently no-op'd when the file was missing, so on a brand-new VPS the
# FIRST persona produced was never indexed — Track-I forensic root cause for
# Known symptom: "selector returns 0 candidates" (fleet-observed bug).
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
  blue "── Updating persona-categories.json (with auto-classification) ──"
  # v6.6.1 FIX: auto-classify domain/perspective from slug+title+author so new
  # personas are immediately visible to the dept-scope filter.  Uses keyword
  # matching against the canonical tag taxonomy — no LLM, no API call, no cost.
  # Falls back to ["coaching"] / [] if nothing matches; always safe.
  python3 - <<PYEOF
import json, re
cat_file = "$CAT_FILE"
slug = "$SLUG"
title = "${TITLE:-$SLUG}".lower()
author = "${AUTHOR:-}".lower()
text_probe = slug.replace("-", " ") + " " + title + " " + author

# ── Domain classification: keyword → domain-tag mapping ──────────────────────
# NOTE: order matters — more specific tags first so they're not swamped by "coaching" fallback.
DOMAIN_KEYWORDS = {
    "sales":                ["sell", "sales", "closing", "close deals", "offers", "spin",
                             "persuasion", "prospect", "revenue", "pitch", "cold call", "crm",
                             "conversion", "client acquisition", "negotiat", "never split",
                             "split the difference", "voss"],
    "marketing":            ["marketing", "brand", "audience", "content", "social media", "hook",
                             "attraction", "funnel", "storybrand", "traffic", "advertising",
                             "permission", "tribe", "oversubscribed", "kane", "godin",
                             "this is marketing", "100m", "million dollar"],
    "copywriting":          ["copy", "copywriter", "write", "words", "message", "headline",
                             "conversion copy", "email", "letters", "hack", "wiebe",
                             "jones", "exactly what to say", "charvet"],
    "leadership":           ["leader", "leadership", "management", "team", "vision", "culture",
                             "good to great", "legacy", "executive", "ceo", "influence",
                             "authority", "command", "sinek", "start with why", "collins",
                             "find your why", "pink drive", "crucial conversation", "grenny"],
    "finance":              ["finance", "financial", "money", "profit", "cash", "wealth", "rich",
                             "invest", "budget", "income", "revenue", "pricing", "michalowicz",
                             "profit first", "100m", "dollar", "hormozi"],
    "operations":           ["operations", "process", "system", "workflow", "procedure", "efficiency",
                             "optimize", "build", "para method", "second brain", "organization",
                             "forte", "12 week year", "moran"],
    "communication":        ["communicat", "speak", "listen", "conversation", "dialogue", "words",
                             "language", "influence", "impact", "rapport", "connection", "crucial",
                             "negotiat", "never split", "exactly what to say", "jones", "charvet",
                             "grenny"],
    "mindset":              ["mindset", "belief", "mental", "attitude", "limit", "growth mindset",
                             "winner", "champion", "relentless", "unstoppable", "discipline",
                             "motivation", "can t hurt", "cant hurt", "goggins", "grover",
                             "drive", "five second", "let them", "boundaries", "habits"],
    "productivity-systems": ["productiv", "habit", "routine", "schedule", "time management",
                             "focus", "goal", "execution", "12 week", "5am", "morning",
                             "deep work", "atomic", "second brain", "para", "pkm", "forte",
                             "clear", "james clear", "sharma"],
    "coaching":             ["coach", "mentor", "guidance", "transform", "change", "potential",
                             "develop", "passion test", "five second rule", "let them theory",
                             "attwood", "robbins", "tawwab", "set boundaries"],
    "strategy-innovation":  ["strategy", "strateg", "innovation", "disrupt", "pivot", "model",
                             "competitive", "advantage", "blue ocean", "extraordinary mind",
                             "lakhiani", "samit", "oversubscribed", "priestley"],
    "personal-development": ["personal development", "self develop", "self improve", "becoming",
                             "growth", "purpose", "why", "meaning", "happiness", "joy", "soul",
                             "instinct", "passion", "jakes", "sinek"],
}

# ── Perspective classification: keyword → perspective-tag mapping ─────────────
PERSPECTIVE_KEYWORDS = {
    "african-american-experience": ["african american", "black", "obama", "jakes", "goggins",
                                    "grover", "tawwab", "brown", "colored", "minority"],
    "womens-challenges":           ["women", "woman", "female", "feminine", "girl", "lady",
                                    "obama", "brown", "brene", "mel robbins", "robbins",
                                    "attwood", "janet", "wiebe", "joanna", "tawwab", "nedra"],
    "mens-challenges":             ["men", "man", "male", "masculine", "boy", "guy",
                                    "goggins", "grover", "hormozi", "voss"],
    "family-relationships":        ["family", "parent", "child", "marriage", "relationship",
                                    "home", "belong", "grenny", "crucial", "boundaries",
                                    "let them", "obama"],
    "faith-spirituality":          ["faith", "spirit", "god", "church", "bible", "pray",
                                    "belief", "divine", "purpose", "jakes", "instinct"],
    "love-romantic-relationships": ["love", "romance", "romantic", "partner", "dating",
                                    "heart", "atlas", "boundaries", "let them"],
}

def classify(probe):
    domain = []
    for tag, kws in DOMAIN_KEYWORDS.items():
        if any(kw in probe for kw in kws):
            domain.append(tag)
    if not domain:
        domain = ["coaching"]  # safe default — everyone can use a coaching persona
    perspective = []
    for tag, kws in PERSPECTIVE_KEYWORDS.items():
        if any(kw in probe for kw in kws):
            perspective.append(tag)
    return domain, perspective

with open(cat_file) as f:
    data = json.load(f)
personas = data.get("personas", {})
if not isinstance(personas, dict):
    personas = {}
    data["personas"] = personas

if slug not in personas:
    domain_tags, perspective_tags = classify(text_probe)
    personas[slug] = {
        "author":      "$AUTHOR",
        "book":        "${TITLE:-$SLUG}",
        "domain":      domain_tags,
        "perspective": perspective_tags,
        "custom":      [],
        "source_type": "$TYPE",
        "added":       "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    }
    with open(cat_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Added {slug} to persona-categories.json")
    print(f"    domain:      {domain_tags}")
    print(f"    perspective: {perspective_tags}")
    if domain_tags == ["coaching"]:
        print("    NOTE: only default domain matched — review persona-categories.json and refine tags if needed")
else:
    # Migrate legacy domain_tags → domain, perspective_tags → perspective if needed
    entry = personas[slug]
    migrated = False
    if "domain_tags" in entry and "domain" not in entry:
        entry["domain"] = entry.pop("domain_tags")
        migrated = True
    if "perspective_tags" in entry and "perspective" not in entry:
        entry["perspective"] = entry.pop("perspective_tags")
        migrated = True
    # If existing entry has empty domain, backfill with auto-classification
    if not entry.get("domain"):
        domain_tags, _ = classify(text_probe)
        entry["domain"] = domain_tags
        migrated = True
        print(f"  Auto-filled empty domain for {slug}: {domain_tags}")
    if migrated:
        with open(cat_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"  Updated {slug} in persona-categories.json")
    else:
        print(f"  {slug} already in persona-categories.json (domain/perspective present)")
PYEOF
fi

echo ""
green "═══════════════════════════════════════════════════"
green "  ✓ Persona added: $SLUG"
green "═══════════════════════════════════════════════════"
echo "  Blueprint:          $PERSONA_FOLDER/persona-blueprint.md"
echo "  Source text:        $TEXT_FILE"
echo "  Searchable via:     python3 $OC_ROOT/scripts/gemini-search.py --query \"<task>\""
echo ""
yellow "  NEXT STEP (optional): review domain[] and perspective[] tags in persona-categories.json"
yellow "  for $SLUG.  Auto-classification has assigned initial tags from title/author/slug —"
yellow "  verify they match the content and add any extras from PERSONA-ROUTER.md §Domain Tags."

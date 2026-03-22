#!/usr/bin/env python3
"""
BlackCEO Coaching Personas Matrix - Orchestration Engine
Manages the 3-phase book-to-persona pipeline across all 21 books.

Pipeline:
  Phase 1 - Extraction (Kimi K2.5) - reads full book, extracts raw data
  Phase 2 - Analysis (DeepSeek V3.2-Speciale) - deep analytical work
  Phase 3 - Synthesis (GPT-5.3 Codex) - writes the full persona blueprint

Runs 4 books in parallel per phase. Manages queue automatically.
"""

import os
import json
import time
import asyncio
import aiohttp
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# ─── PATHS ────────────────────────────────────────────────────────────────────
BASE = Path.home() / "Downloads/openclaw-master-files/coaching-personas"
BOOKS_DIR = BASE / "books"
PERSONAS_DIR = BASE / "personas"
PROJECT_DIR = Path.home() / "clawd/projects/coaching-personas-matrix"
PROMPTS_DIR = PROJECT_DIR / "agent-prompts"
STATUS_FILE = PROJECT_DIR / "pipeline-status.json"
LOG_FILE = PROJECT_DIR / "pipeline-log.txt"

# ─── MODEL IDs ────────────────────────────────────────────────────────────────
# Phase 1 - Extraction: Kimi K2.5 via OpenRouter (262K context)
MODEL_EXTRACTION       = "moonshotai/kimi-k2.5"
MODEL_EXTRACTION_ROUTE = "openrouter"

# Phase 2 - Analysis: DeepSeek V3.2-Speciale via OpenRouter (163K context)
MODEL_ANALYSIS         = "deepseek/deepseek-v3.2"
MODEL_ANALYSIS_ROUTE   = "openrouter"

# Phase 3 - Synthesis: GPT-5.3 Codex via OpenAI direct (OAuth subscription, 400K context)
# Uses OpenAI Responses API - NOT chat completions, NOT OpenRouter
MODEL_SYNTHESIS        = "gpt-5.3-codex"
MODEL_SYNTHESIS_ROUTE  = "openai-responses"

# ─── LIMITS ───────────────────────────────────────────────────────────────────
PARALLEL_LIMIT   = 40        # Max books processed simultaneously per phase
OPENROUTER_FALLBACK_FOLDERS = {"samit-disrupt-yourself", "attwood-passion-test"}  # Books that hit Kimi content filter
CHUNK_THRESHOLD  = 80000    # Characters - books above this get chunked for Phase 2
MAX_CHUNK_SIZE   = 70000    # Characters per chunk for Phase 2
MAX_RETRIES      = 3        # Retry failed API calls this many times
RETRY_DELAY      = 10       # Seconds between retries

# ─── API KEYS ─────────────────────────────────────────────────────────────────
def get_keys():
    env_path = Path.home() / "clawd/secrets/.env"
    keys = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                keys[k.strip()] = v.strip()
    return keys

_KEYS = get_keys()
OPENROUTER_API_KEY = _KEYS.get("OPENROUTER_API_KEY") or ""
MOONSHOT_API_KEY = _KEYS.get("MOONSHOT_API_KEY") or ""
OPENAI_API_KEY     = _KEYS.get("OPENAI_API_KEY") or ""

if not OPENROUTER_API_KEY:
    raise ValueError("OPENROUTER_API_KEY not found")
if not MOONSHOT_API_KEY:
    raise ValueError("MOONSHOT_API_KEY not found")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in ~/clawd/secrets/.env")

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENAI_BASE_URL     = "https://api.openai.com/v1"

# ─── BOOK REGISTRY ────────────────────────────────────────────────────────────
BOOKS = [
    # Priority 1 - Build First
    {"title": "Atomic Habits",                  "author": "James Clear",       "file": "Atomic Habits - James Clear.pdf",                      "folder": "clear-atomic-habits"},
    {"title": "SPIN Selling",                   "author": "Neil Rackham",      "file": "SPIN Selling - Neil Rackham.pdf",                      "folder": "rackham-spin-selling"},
    {"title": "Never Split the Difference",     "author": "Chris Voss",        "file": "Never Split the Difference - Chris Voss.pdf",          "folder": "voss-never-split-difference"},
    {"title": "Influence",                      "author": "Robert Cialdini",   "file": "Influence - Robert Cialdini.pdf",                      "folder": "cialdini-influence"},
    {"title": "Building a StoryBrand 2.0",      "author": "Donald Miller",     "file": "Building a StoryBrand 2.0 - Donald Miller.pdf",        "folder": "miller-building-storybrand-2"},
    # Priority 2
    {"title": "To Sell Is Human",               "author": "Daniel Pink",       "file": "To Sell Is Human - Daniel Pink.pdf",                   "folder": "pink-to-sell-is-human"},
    {"title": "Exactly What to Say",            "author": "Phil Jones",        "file": "Exactly What to Say - Phil Jones.pdf",                 "folder": "jones-exactly-what-to-say"},
    {"title": "Start with Why",                 "author": "Simon Sinek",       "file": "Start with Why - Simon Sinek.pdf",                     "folder": "sinek-start-with-why"},
    {"title": "The Power of Habit",             "author": "Charles Duhigg",    "file": "The Power of Habit - Charles Duhigg.pdf",              "folder": "duhigg-power-of-habit"},
    {"title": "Good to Great",                  "author": "Jim Collins",       "file": "Good to Great - Jim Collins.pdf",                      "folder": "collins-good-to-great"},
    # Priority 3
    {"title": "The 5 Second Rule",              "author": "Mel Robbins",       "file": "The 5 Second Rule - Mel Robbins.pdf",                  "folder": "robbins-five-second-rule"},
    {"title": "Drive",                          "author": "Daniel Pink",       "file": "Drive - Daniel Pink.pdf",                              "folder": "pink-drive"},
    {"title": "Find Your Why",                  "author": "Simon Sinek",       "file": "Find Your Why - Simon Sinek.pdf",                      "folder": "sinek-find-your-why"},
    {"title": "Cant Hurt Me",                   "author": "David Goggins",     "file": "Cant Hurt Me - David Goggins.pdf",                     "folder": "goggins-cant-hurt-me"},
    {"title": "Instinct",                       "author": "TD Jakes",          "file": "Instinct - TD Jakes.pdf",                              "folder": "jakes-instinct"},
    # Priority 4
    {"title": "Set Boundaries Find Peace",      "author": "Nedra Tawwab",      "file": "Set Boundaries Find Peace - Nedra Tawwab.pdf",         "folder": "tawwab-set-boundaries-find-peace"},
    {"title": "Atlas of the Heart",             "author": "Brene Brown",       "file": "Atlas of the Heart - Brene Brown.pdf",                 "folder": "brown-atlas-of-heart"},
    {"title": "Becoming",                       "author": "Michelle Obama",    "file": "Becoming - Michelle Obama.pdf",                        "folder": "obama-becoming"},
    {"title": "The Light We Carry",             "author": "Michelle Obama",    "file": "The Light We Carry - Michelle Obama.pdf",              "folder": "obama-light-we-carry"},
    {"title": "Building a StoryBrand 1.0",      "author": "Donald Miller",     "file": "Building a StoryBrand 1.0 - Donald Miller.pdf",        "folder": "miller-building-storybrand-1"},
    {"title": "Hook Point",                     "author": "Brendan Kane",      "file": "Hook_Point",                                           "folder": "kane-hook-point"},
    {"title": "When",                           "author": "Daniel Pink",        "file": "When - Dan Pink.pdf",                                       "folder": "pink-when"},
    {"title": "Building a Second Brain",         "author": "Tiago Forte",        "file": "Building a Second Brain - Tiago Forte.pdf",                 "folder": "forte-building-second-brain"},
    {"title": "Crucial Conversations",           "author": "Grenny Patterson",   "file": "Crucial Conversations - Grenny Patterson.pdf",              "folder": "grenny-crucial-conversations"},
    {"title": "Profit First",                    "author": "Mike Michalowicz",   "file": "Profit First - Mike Michalowicz.pdf",                       "folder": "michalowicz-profit-first"},
    {"title": "The Let Them Theory",             "author": "Mel Robbins",        "file": "The Let Them Theory - Mel Robbins.pdf",                     "folder": "robbins-let-them-theory"},
    {"title": "The 5 AM Club",                   "author": "Robin Sharma",       "file": "The 5 AM Club - Robin Sharma.pdf",                          "folder": "sharma-5am-club"},
    {"title": "Copy Hackers Value Proposition",  "author": "Joanna Wiebe",      "file": "Copy Hackers Value Proposition - Joanna Wiebe.pdf",        "folder": "wiebe-copy-hackers"},
    {"title": "The Copywriters Handbook",         "author": "Robert Bly",         "file": "The Copywriters Handbook - Robert Bly.pdf",                "folder": "bly-copywriters-handbook"},
    {"title": "Relentless",                       "author": "Tim Grover",         "file": "Relentless - Tim Grover.pdf",                              "folder": "grover-relentless"},
    {"title": "Code of the Extraordinary Mind",   "author": "Vishen Lakhiani",    "file": "Code of the Extraordinary Mind - Vishen Lakhiani.pdf",     "folder": "lakhiani-extraordinary-mind"},
    {"title": "Oversubscribed",                   "author": "Daniel Priestley",   "file": "Oversubscribed - Daniel Priestley.mobi",                   "folder": "priestley-oversubscribed"},
    {"title": "Disrupt Yourself",                 "author": "Jay Samit",          "file": "Disrupt Yourself - Jay Samit.pdf",                         "folder": "samit-disrupt-yourself"},
    {"title": "Words that Change Minds",          "author": "Shelle Rose Charvet","file": "Words that Change Minds - Shelle Rose Charvet.pdf",        "folder": "charvet-words-change-minds"},
    {"title": "The PARA Method",                  "author": "Tiago Forte",        "file": "The PARA Method - Tiago Forte.pdf",                        "folder": "forte-para-method"},
    {"title": "The Passion Test",                 "author": "Janet Attwood",      "file": "The Passion Test - Attwood.pdf",                           "folder": "attwood-passion-test"},
    {"title": "This Is Marketing",                "author": "Seth Godin",         "file": "This Is Marketing - Seth Godin.azw3",                      "folder": "godin-this-is-marketing"},
    {"title": "The 12 Week Year",                 "author": "Brian Moran",        "file": "The 12 Week Year - Moran Lennington.pdf",                  "folder": "moran-12-week-year"},
    {"title": "100M Offers",                      "author": "Alex Hormozi",       "file": "100M Offers - Alex Hormozi.pdf",                           "folder": "hormozi-100m-offers"},
    {"title": "Good to Great Summary",          "author": "Jim Collins",       "file": "Good to Great Summary - Jim Collins.pdf",              "folder": "collins-good-to-great-summary"},
]

# ─── LOGGING ──────────────────────────────────────────────────────────────────
def log(msg):
    timestamp = datetime.datetime.now().strftime("%B %-d at %-I:%M %p")
    line = f"[{timestamp}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ─── STATUS TRACKING ──────────────────────────────────────────────────────────
def load_status():
    status = {}
    if STATUS_FILE.exists():
        status = json.loads(STATUS_FILE.read_text())
    
    for book in BOOKS:
        if book["folder"] not in status:
            status[book["folder"]] = {
                "title": book["title"],
                "author": book["author"],
                "phase1": "PENDING",
                "phase2": "PENDING",
                "phase3": "PENDING",
                "started": None,
                "completed": None,
                "errors": []
            }
    STATUS_FILE.write_text(json.dumps(status, indent=2))
    return status

def save_status(status):
    STATUS_FILE.write_text(json.dumps(status, indent=2))

def mark_phase(status, folder, phase, state, error=None):
    status[folder][f"phase{phase}"] = state
    if error:
        status[folder]["errors"].append({"phase": phase, "error": error, "time": str(datetime.datetime.now())})
    save_status(status)

# ─── MULTI-FORMAT TEXT EXTRACTION ────────────────────────────────────────────
SUPPORTED_FORMATS = {
    ".pdf":  "PDF",
    ".epub": "EPUB",
    ".mobi": "MOBI",
    ".azw":  "Kindle AZW",
    ".azw3": "Kindle AZW3",
    ".kfx":  "Kindle KFX",
}

def extract_book_text(book_path: Path) -> str:
    """
    Unified text extraction for PDF, EPUB, MOBI, AZW, AZW3, KFX.

    Routes to the appropriate extractor based on file extension:
    - PDF: pdfplumber (fastest, most accurate for PDFs)
    - EPUB: ebooklib (pure Python, lightweight)
    - MOBI/AZW/AZW3/KFX: Calibre ebook-convert (converts to txt then reads)

    All paths return plain text string ready for LLM input.
    """
    ext = book_path.suffix.lower()
    fmt = SUPPORTED_FORMATS.get(ext)

    if not fmt:
        raise ValueError(
            f"Unsupported format: {ext}\n"
            f"Supported: {', '.join(SUPPORTED_FORMATS.keys())}"
        )

    if ext == ".pdf":
        return _extract_pdf(book_path)
    elif ext == ".epub":
        return _extract_epub(book_path)
    elif ext == ".mobi":
        # MOBI: try fast Python library first, fall back to Calibre+DeDRM
        return _extract_mobi_python(book_path)
    else:
        # AZW, AZW3, KFX - Calibre + DeDRM plugin handles all of these
        return _extract_via_calibre(book_path)


def _extract_pdf(pdf_path: Path) -> str:
    """Extract text from PDF using pdfplumber (primary) or pypdf (fallback)."""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if text.strip():
            return text
        log("  Warning: pdfplumber returned empty text - trying pypdf fallback")
    except ImportError:
        log("  pdfplumber not installed, trying pypdf")
    except Exception as e:
        log(f"  pdfplumber error: {e} - trying pypdf fallback")

    try:
        import pypdf
        text = ""
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return text
    except ImportError:
        raise RuntimeError("Neither pdfplumber nor pypdf installed. Run: pip3 install pdfplumber")


def _extract_epub(epub_path: Path) -> str:
    """Extract text from EPUB using ebooklib."""
    try:
        from ebooklib import epub
        import html
        from html.parser import HTMLParser

        class _TextExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.text_parts = []
                self._skip = False
            def handle_starttag(self, tag, attrs):
                if tag in ('script', 'style'):
                    self._skip = True
            def handle_endtag(self, tag):
                if tag in ('script', 'style'):
                    self._skip = False
            def handle_data(self, data):
                if not self._skip:
                    self.text_parts.append(data)

        book = epub.read_epub(str(epub_path))
        text_parts = []

        for item in book.get_items():
            if item.get_type() == 9:  # ITEM_DOCUMENT
                parser = _TextExtractor()
                parser.feed(item.get_content().decode("utf-8", errors="ignore"))
                chunk = " ".join(parser.text_parts)
                if chunk.strip():
                    text_parts.append(chunk)

        return "\n\n".join(text_parts)

    except ImportError:
        log("  ebooklib not installed, falling back to Calibre for EPUB")
        return _extract_via_calibre(epub_path)


def _find_calibre() -> str:
    """Locate ebook-convert binary across common install paths."""
    import subprocess
    calibre_paths = [
        "/opt/homebrew/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        "/usr/bin/ebook-convert",
    ]
    for p in calibre_paths:
        if Path(p).exists():
            return p
    result = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()
    raise RuntimeError(
        "Calibre not found. Install with: brew install --cask calibre\n"
        "DeDRM plugin also required: calibre-customize -a ~/clawd/skills/book-to-persona/drm-tools/DeDRM_tools/DeDRM_plugin.zip"
    )


def _extract_mobi_python(book_path: Path) -> str:
    """
    Extract MOBI text using the `mobi` Python library (fast, no Calibre needed).
    Works on DRM-free MOBI files. Falls back to Calibre if it fails.

    The mobi library extracts to an HTML file then we parse it to plain text.
    """
    try:
        import mobi
        import tempfile
        from html.parser import HTMLParser
        from bs4 import BeautifulSoup

        with tempfile.TemporaryDirectory() as tmpdir:
            # mobi.extract() returns (temp_dir, epub_path)
            extract_dir, epub_path = mobi.extract(str(book_path))
            # If it gave us an epub, read it via ebooklib
            if epub_path and Path(epub_path).exists():
                log("  MOBI extracted to EPUB via mobi library, parsing...")
                return _extract_epub(Path(epub_path))
            else:
                # Try to find any HTML files in the extract dir
                html_files = list(Path(extract_dir).rglob("*.html")) + list(Path(extract_dir).rglob("*.htm"))
                if html_files:
                    parts = []
                    for hf in sorted(html_files):
                        soup = BeautifulSoup(hf.read_text(errors="ignore"), "html.parser")
                        parts.append(soup.get_text(separator="\n"))
                    text = "\n\n".join(parts)
                    if text.strip():
                        log(f"  MOBI extracted via HTML parsing: {len(text):,} chars")
                        return text
    except Exception as e:
        log(f"  mobi Python library failed ({e}), falling back to Calibre")

    return _extract_via_calibre(book_path)


def _extract_via_calibre(book_path: Path) -> str:
    """
    Convert MOBI, AZW, AZW3, KFX (and EPUB fallback) to plain text using Calibre.

    With DeDRM plugin installed (v10.0.9), Calibre handles DRM-protected books
    from Amazon Kindle, Adobe Adept, Barnes & Noble, and Mobipocket.

    DRM removal is for personal use only (books you legally purchased and own).
    Calibre + DeDRM plugin installed at: ~/clawd/skills/book-to-persona/drm-tools/

    Conversion chain: source format -> TXT via ebook-convert
    """
    import subprocess
    import tempfile

    calibre_bin = _find_calibre()

    with tempfile.TemporaryDirectory() as tmpdir:
        out_path = Path(tmpdir) / "output.txt"

        # ebook-convert with DRM plugin active handles protected files automatically
        # The DeDRM plugin intercepts during import - no extra flags needed
        cmd = [
            calibre_bin,
            str(book_path),
            str(out_path),
            "--txt-output-formatting=plain",  # plain is cleaner than markdown for LLM input
            "--keep-ligatures",               # preserve special chars
        ]

        log(f"  Converting {book_path.suffix.upper()} via Calibre + DeDRM...")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180  # DRM removal can take longer
        )

        if result.returncode != 0:
            stderr = result.stderr[:500]
            # Check for common DRM error messages
            if "drm" in stderr.lower() or "decryption" in stderr.lower() or "protection" in stderr.lower():
                raise RuntimeError(
                    f"DRM removal failed for {book_path.name}.\n"
                    f"This book may use a DRM type not supported by DeDRM v10.0.9.\n"
                    f"For Kindle books: ensure the book was downloaded via Kindle for Mac.\n"
                    f"Calibre stderr: {stderr}"
                )
            raise RuntimeError(
                f"Calibre conversion failed (exit {result.returncode}):\n"
                f"stderr: {stderr}"
            )

        if not out_path.exists():
            raise RuntimeError(f"Calibre ran but output file not found: {out_path}")

        text = out_path.read_text(encoding="utf-8", errors="ignore")
        if not text.strip():
            raise RuntimeError(
                f"Calibre conversion produced empty output for {book_path.name}. "
                f"File may be DRM-protected and decryption failed silently."
            )

        log(f"  Calibre conversion complete: {len(text):,} characters extracted")
        return text


# ─── LEGACY ALIAS (keeps backward compat if anything calls extract_pdf_text) ──
def extract_pdf_text(pdf_path: Path) -> str:
    """Alias for backward compatibility. Use extract_book_text() for new code."""
    return _extract_pdf(pdf_path)


# ─── (OLD PDF-ONLY FALLBACK - kept for reference, replaced by _extract_pdf) ──
def _legacy_pypdf_fallback(pdf_path):
    try:
        import pypdf
        text = ""
        reader = pypdf.PdfReader(str(pdf_path))
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except ImportError:
        pass
    raise RuntimeError("Neither pdfplumber nor pypdf is installed. Run: pip3 install pdfplumber")

# ─── CHUNKING LOGIC ───────────────────────────────────────────────────────────
def chunk_text(text: str, chunk_size: int = MAX_CHUNK_SIZE, overlap: int = 2000) -> list:
    """
    Split large book text into overlapping chunks for Phase 2 analysis.
    Used for books exceeding CHUNK_THRESHOLD characters.
    Overlap ensures no methodology context is lost at chunk boundaries.
    """
    if len(text) <= chunk_size:
        return [text]

    chunks = []
    start = 0
    total = len(text)

    while start < total:
        end = min(start + chunk_size, total)

        # Try to break at a paragraph boundary rather than mid-sentence
        if end < total:
            boundary = text.rfind("\n\n", start, end)
            if boundary > start + (chunk_size // 2):
                end = boundary

        chunk = text[start:end]
        chunks.append(chunk)
        log(f"    Chunk {len(chunks)}: chars {start:,} - {end:,} ({len(chunk):,} chars)")

        # Move forward with overlap so context carries between chunks
        start = end - overlap

    log(f"  Book chunked into {len(chunks)} segments")
    return chunks

# ─── API CALLS ────────────────────────────────────────────────────────────────

async def call_moonshot(session: aiohttp.ClientSession, system: str, user: str) -> str:
    """Call Kimi K2.5 via Moonshot direct API."""
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "kimi-k2.5",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "temperature": 1.0,
        "max_tokens": 16000
    }
    
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                "https://api.moonshot.ai/v1/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=600)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data["choices"][0]["message"]["content"]
                else:
                    error_text = await response.text()
                    log(f"  Moonshot error {response.status}: {error_text[:200]}")
                    if attempt < MAX_RETRIES:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
                import asyncio
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError("All attempts failed for moonshot direct API")

async def call_openrouter(session: aiohttp.ClientSession, model: str, system: str, user: str, max_tokens: int = 16000) -> str:
    """Call Kimi K2.5 or DeepSeek V3.2-Speciale via OpenRouter."""
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://blackceo.com",
        "X-Title": "BlackCEO Coaching Personas Matrix"
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user}
        ],
        "max_tokens": max_tokens,
        "temperature": 1.0
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=600)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data["choices"][0]["message"]["content"]
                    if content is None:
                        # Some models return null content with reasoning_content
                        reasoning = data["choices"][0]["message"].get("reasoning_content", "")
                        if reasoning:
                            log(f"  Warning: content was null, using reasoning_content ({len(reasoning):,} chars)")
                            return reasoning
                        log(f"  Warning: content was null and no reasoning_content - retrying...")
                        if attempt < MAX_RETRIES:
                            await asyncio.sleep(RETRY_DELAY * attempt)
                            continue
                        raise RuntimeError(f"API returned null content after {MAX_RETRIES} attempts")
                    return content
                else:
                    error_text = await response.text()
                    log(f"  OpenRouter error {response.status}: {error_text[:200]}")
                    if attempt < MAX_RETRIES:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {model} via OpenRouter")


async def call_codex(session: aiohttp.ClientSession, user: str, max_tokens: int = 120000) -> str:
    """
    Call GPT-5.3 Codex via OpenAI Responses API (Trevor's OAuth subscription).
    Uses the direct OpenAI API key - NOT OpenRouter.
    Model: gpt-5.3-codex
    API: /v1/responses (required - Codex does not use /v1/chat/completions)
    """
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": MODEL_SYNTHESIS,       # gpt-5.3-codex
        "input": user,
        "max_output_tokens": max_tokens,
        "temperature": 1.0
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                f"{OPENAI_BASE_URL}/responses",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=900)  # Codex synthesis takes longer
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # OpenAI Responses API format
                    for item in data.get("output", []):
                        if item.get("type") == "message":
                            for content in item.get("content", []):
                                if content.get("type") == "output_text":
                                    return content["text"]
                    raise RuntimeError(f"Unexpected response format: {json.dumps(data)[:300]}")
                else:
                    error_text = await response.text()
                    log(f"  OpenAI Codex error {response.status}: {error_text[:200]}")
                    if attempt < MAX_RETRIES:
                        log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
                        await asyncio.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            log(f"  Codex exception on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for GPT-5.3 Codex")

# ─── LOAD PROMPTS ─────────────────────────────────────────────────────────────
def load_prompt(filename: str) -> str:
    path = PROMPTS_DIR / filename
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")
    return path.read_text()

EXTRACTION_SYSTEM = load_prompt("extraction-agent-prompt.md")
ANALYSIS_SYSTEM   = load_prompt("analysis-agent-prompt.md")
SYNTHESIS_SYSTEM  = load_prompt("synthesis-agent-prompt.md")

# ─── PHASE 1 - EXTRACTION ─────────────────────────────────────────────────────
async def run_extraction(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    output_path = PERSONAS_DIR / folder / "extraction-notes.md"

    # Resolve book file - supports PDF, EPUB, MOBI, AZW, AZW3, KFX
    book_file = book["file"]
    book_path = BOOKS_DIR / book_file
    if not book_path.exists():
        # Try finding the book in any supported format
        stem = Path(book_file).stem
        found = None
        for ext in SUPPORTED_FORMATS.keys():
            candidate = BOOKS_DIR / (stem + ext)
            if candidate.exists():
                found = candidate
                break
        if found:
            book_path = found
            log(f"  Note: Using {found.name} (original file not found)")
        else:
            log(f"  [PHASE 1 FAILED] {book['title']}: Book file not found: {book_path}")
            mark_phase(status, folder, 1, "FAILED", f"File not found: {book_file}")
            return False

    fmt = SUPPORTED_FORMATS.get(book_path.suffix.lower(), "UNKNOWN")
    log(f"[PHASE 1] Starting extraction: {book['title']} [{fmt}]")
    mark_phase(status, folder, 1, "IN_PROGRESS")

    try:
        text = extract_book_text(book_path)
        log(f"  {fmt} extracted: {len(text):,} characters")

        user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here is the complete book text. Extract all 20 items as specified in your instructions.

---

{text[:900000]}"""  # Kimi K2.5 has 262K context - leave room for system prompt

        # Use OpenRouter as fallback for books that hit Kimi's content filter
        if folder in OPENROUTER_FALLBACK_FOLDERS:
            log(f"  Using OpenRouter fallback for {book['title']} (content filter)")
            result = await call_openrouter(session, "moonshotai/kimi-k2.5", EXTRACTION_SYSTEM, user_prompt, max_tokens=16000)
        else:
            result = await call_moonshot(
                session,
                EXTRACTION_SYSTEM,
                user_prompt
            )

        header = f"# EXTRACTION NOTES - {book['title']}\n**Author:** {book['author']}\n**Extracted:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}\n**Model:** {MODEL_EXTRACTION}\n\n---\n\n"
        output_path.write_text(header + result)

        log(f"  [PHASE 1 COMPLETE] {book['title']} - {len(result):,} chars saved")
        mark_phase(status, folder, 1, "COMPLETE")
        return True

    except Exception as e:
        log(f"  [PHASE 1 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 1, "FAILED", str(e))
        return False

# ─── PHASE 2 - ANALYSIS ───────────────────────────────────────────────────────
async def run_analysis(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    extraction_path = PERSONAS_DIR / folder / "extraction-notes.md"
    output_path = PERSONAS_DIR / folder / "analysis-notes.md"

    log(f"[PHASE 2] Starting analysis: {book['title']}")
    mark_phase(status, folder, 2, "IN_PROGRESS")

    try:
        extraction_text = extraction_path.read_text()
        log(f"  Extraction notes: {len(extraction_text):,} chars")

        # CHUNKING LOGIC - DeepSeek V3.2-Speciale has 163K context
        # Extraction notes for large books may exceed safe limit
        DEEPSEEK_SAFE_LIMIT = 120000  # Leave room for system prompt + output

        if len(extraction_text) > DEEPSEEK_SAFE_LIMIT:
            log(f"  Large extraction ({len(extraction_text):,} chars) - chunking for analysis")
            chunks = chunk_text(extraction_text, chunk_size=DEEPSEEK_SAFE_LIMIT, overlap=3000)

            # Run analysis on each chunk, then synthesize chunk analyses
            chunk_analyses = []
            for i, chunk in enumerate(chunks, 1):
                log(f"  Analyzing chunk {i}/{len(chunks)}...")
                user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}
CHUNK: {i} of {len(chunks)}

Analyze this portion of the extraction notes across all 12 analytical dimensions.
Note this is chunk {i} of {len(chunks)} - focus on the material present in this chunk.
A final synthesis pass will combine all chunk analyses.

---

{chunk}"""
                chunk_result = await call_openrouter(
                    session, MODEL_ANALYSIS, ANALYSIS_SYSTEM, user_prompt, max_tokens=16000
                )
                chunk_analyses.append(f"## CHUNK {i} ANALYSIS\n\n{chunk_result}")
                await asyncio.sleep(2)  # Brief pause between chunks

            # Final synthesis of all chunk analyses
            log(f"  Synthesizing {len(chunks)} chunk analyses into unified analysis...")
            synthesis_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Below are analyses from {len(chunks)} chunks of this book's extraction notes.
Synthesize them into one complete, unified analysis across all 12 analytical dimensions.
Resolve any inconsistencies. Fill gaps by inferring from context.
Produce the final structured analysis document.

---

{''.join(chunk_analyses)}"""

            result = await call_openrouter(
                session, MODEL_ANALYSIS, ANALYSIS_SYSTEM, synthesis_prompt, max_tokens=16000
            )

        else:
            user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here are the complete extraction notes from Phase 1. 
Analyze across all 12 analytical dimensions as specified.

---

{extraction_text}"""

            result = await call_openrouter(
                session, MODEL_ANALYSIS, ANALYSIS_SYSTEM, user_prompt, max_tokens=16000
            )

        header = f"# ANALYSIS NOTES - {book['title']}\n**Author:** {book['author']}\n**Analyzed:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}\n**Model:** {MODEL_ANALYSIS}\n\n---\n\n"
        output_path.write_text(header + result)

        log(f"  [PHASE 2 COMPLETE] {book['title']} - {len(result):,} chars saved")
        mark_phase(status, folder, 2, "COMPLETE")
        return True

    except Exception as e:
        log(f"  [PHASE 2 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 2, "FAILED", str(e))
        return False

# ─── PHASE 3 - SYNTHESIS ──────────────────────────────────────────────────────
async def run_synthesis(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    extraction_path = PERSONAS_DIR / folder / "extraction-notes.md"
    analysis_path = PERSONAS_DIR / folder / "analysis-notes.md"
    blueprint_path = PERSONAS_DIR / folder / "persona-blueprint.md"

    log(f"[PHASE 3] Starting synthesis: {book['title']}")
    mark_phase(status, folder, 3, "IN_PROGRESS")

    try:
        extraction_text = extraction_path.read_text()
        analysis_text = analysis_path.read_text()

        # Read the SKILL.md spec to include in synthesis prompt
        skill_path = PROJECT_DIR / "SKILL.md"
        skill_spec = skill_path.read_text() if skill_path.exists() else ""

        user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}
PERSONA FOLDER: {folder}

You have the extraction notes (Phase 1) and deep analysis (Phase 2) below.
Build the complete 14-section dual-purpose persona blueprint as specified.

The output file must be saved to:
~/Downloads/openclaw-master-files/coaching-personas/personas/{folder}/persona-blueprint.md

---

## PHASE 1 EXTRACTION NOTES
{extraction_text[:60000]}

---

## PHASE 2 ANALYSIS NOTES
{analysis_text[:60000]}

---

## SKILL.md BLUEPRINT SPECIFICATION
{skill_spec[:30000]}

---

Now write the complete persona blueprint. All 14 sections. Zero placeholders.
Both Coaching Framework (Section 3) and Agent Governance Framework (Section 4) fully built.
At the end, rate your output on the 6 dimensions specified in your instructions."""

        # Phase 3 uses GPT-5.3 Codex via OpenAI Responses API (OAuth subscription)
        # The synthesis system prompt is embedded in the user_prompt for the Responses API
        full_input = f"{SYNTHESIS_SYSTEM}\n\n---\n\n{user_prompt}"
        result = await call_codex(
            session,
            full_input,
            max_tokens=120000  # GPT-5.3 Codex supports 128K output
        )

        header = f"""# PERSONA BLUEPRINT - {book['title']}
**Source Book:** {book['title']} by {book['author']}
**Version:** 1.0.0
**Built:** {datetime.datetime.now().strftime('%B %-d at %-I:%M %p')}
**Gemini Index:** {folder}
**Index Location:** ./qmd-index/
**Coaching Mode:** BUILT
**Task Mode:** BUILT
**QC Status:** QC_PENDING

---

"""
        blueprint_path.write_text(header + result)

        log(f"  [PHASE 3 COMPLETE] {book['title']} - {len(result):,} chars saved")
        mark_phase(status, folder, 3, "COMPLETE")
        status[folder]["completed"] = datetime.datetime.now().strftime('%B %-d at %-I:%M %p')
        save_status(status)
        return True

    except Exception as e:
        log(f"  [PHASE 3 FAILED] {book['title']}: {e}")
        mark_phase(status, folder, 3, "FAILED", str(e))
        return False

# ─── PROCESS ONE BOOK ─────────────────────────────────────────────────────────
async def process_book(session: aiohttp.ClientSession, book: dict, status: dict):
    folder = book["folder"]
    s = status[folder]

    timestamp = datetime.datetime.now().strftime('%B %-d at %-I:%M %p')
    log(f"\n{'='*60}")
    log(f"STARTING: {book['title']} by {book['author']}")
    log(f"{'='*60}")

    if s["started"] is None:
        status[folder]["started"] = timestamp
        save_status(status)

    # Phase 1
    if s["phase1"] not in ("COMPLETE",):
        ok = await run_extraction(session, book, status)
        if not ok:
            log(f"  Skipping {book['title']} - extraction failed")
            return

    # Phase 2
    if s["phase2"] not in ("COMPLETE",):
        ok = await run_analysis(session, book, status)
        if not ok:
            log(f"  Skipping synthesis for {book['title']} - analysis failed")
            return

    # Phase 3
    if s["phase3"] not in ("COMPLETE",):
        await run_synthesis(session, book, status)

# ─── MAIN ORCHESTRATOR ────────────────────────────────────────────────────────
async def main():
    log("\n" + "="*60)
    log("BlackCEO Coaching Personas Matrix - Pipeline Starting")
    log(f"Books to process: {len(BOOKS)}")
    log(f"Parallel limit: {PARALLEL_LIMIT} books at a time")
    log(f"Extraction model: {MODEL_EXTRACTION}")
    log(f"Analysis model:   {MODEL_ANALYSIS}")
    log(f"Synthesis model:  {MODEL_SYNTHESIS}")
    log("="*60 + "\n")

    # Check pdfplumber is available
    try:
        import pdfplumber
        log("PDF library: pdfplumber OK")
    except ImportError:
        try:
            import pypdf
            log("PDF library: pypdf OK (pdfplumber preferred - run: pip3 install pdfplumber)")
        except ImportError:
            log("ERROR: No PDF library found. Run: pip3 install pdfplumber")
            return

    status = load_status()

    # Filter to only books that aren't fully complete
    pending = [b for b in BOOKS if status[b["folder"]]["phase3"] != "COMPLETE"]
    complete = [b for b in BOOKS if status[b["folder"]]["phase3"] == "COMPLETE"]

    log(f"Already complete: {len(complete)}")
    log(f"Pending: {len(pending)}\n")

    if not pending:
        log("All books already processed. Pipeline complete.")
        return

    # Process in batches of PARALLEL_LIMIT
    connector = aiohttp.TCPConnector(limit=20)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, len(pending), PARALLEL_LIMIT):
            batch = pending[i:i + PARALLEL_LIMIT]
            batch_num = (i // PARALLEL_LIMIT) + 1
            total_batches = (len(pending) + PARALLEL_LIMIT - 1) // PARALLEL_LIMIT

            log(f"\n--- BATCH {batch_num}/{total_batches} ---")
            log(f"Books: {', '.join(b['title'] for b in batch)}\n")

            tasks = [process_book(session, book, status) for book in batch]
            await asyncio.gather(*tasks)

            # Progress report after each batch
            done = sum(1 for b in BOOKS if status[b["folder"]]["phase3"] == "COMPLETE")
            log(f"\n--- Batch {batch_num} complete. Total done: {done}/{len(BOOKS)} ---\n")

    # Final report
    log("\n" + "="*60)
    log("PIPELINE COMPLETE")
    log("="*60)
    final_status = load_status()
    for book in BOOKS:
        s = final_status[book["folder"]]
        phases = f"P1:{s['phase1'][0]} P2:{s['phase2'][0]} P3:{s['phase3'][0]}"
        log(f"  {book['title']}: {phases}")

    complete_count = sum(1 for b in BOOKS if final_status[b["folder"]]["phase3"] == "COMPLETE")
    failed_count = sum(1 for b in BOOKS if "FAILED" in [final_status[b["folder"]][f"phase{p}"] for p in [1,2,3]])
    log(f"\nCompleted: {complete_count}/{len(BOOKS)}")
    log(f"Failed: {failed_count}")
    log(f"\nPersona blueprints saved to: {PERSONAS_DIR}")
    log(f"Status file: {STATUS_FILE}")
    log(f"Full log: {LOG_FILE}")

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    asyncio.run(main())

# Fallback list - books that hit Kimi direct content filter, route via OpenRouter
OPENROUTER_FALLBACK_FOLDERS = {"samit-disrupt-yourself", "attwood-passion-test"}

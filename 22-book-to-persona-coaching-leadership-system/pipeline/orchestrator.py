#!/usr/bin/env python3
"""
BlackCEO Coaching Personas Matrix - Orchestration Engine
Manages the 3-phase book-to-persona pipeline across all 21 books.

Pipeline (v10.10.0 — PRD §5.4 'book-to-persona' chain):
  Phase 1 - Extraction (selector-resolved, see PRD §5.4):
              1. Ollama Cloud Kimi  →  2. OpenRouter Kimi  →
              3. Ollama Cloud DeepSeek V4 Pro  →
              4. OpenRouter DeepSeek V4 Pro  →
              5. OpenRouter Gemini 3.1 Flash Lite (cheapest fallback)
  Phase 2 - Analysis (same chain as Phase 1)
  Phase 3 - Synthesis (same chain — was GPT-5.3 Codex pre-v10.10.0;
              now uses the §5.4 chain so the cheapest fallback is
              Gemini Flash Lite, not GPT, matching N1 + cost policy)

Anthropic models are FORBIDDEN by policy (N1). Filter applied at every tier.

Runs up to 4 books in parallel per phase. Manages queue automatically.

v6.6.0 additions:
  --single-book --slug SLUG  Run ONLY the named slug through phases 1-3;
                             reads its source.json to build a one-element BOOKS
                             entry (the #1 fix — without this, new sources added
                             via add-persona-from-source.sh never process).
  --source-json PATH         Alternate path for the source.json marker file.
  Path unification: BASE / BOOKS_DIR / PERSONAS_DIR and gemini-indexer.py
    PERSONAS_DIR all resolve to ONE canonical root so script-write = orchestrator-
    read = indexer-scan across VPS (/data/.openclaw/master-files/coaching-personas)
    and Mac (~/.openclaw/workspace/data/coaching-personas).
  Phase 6: after _append_persona_to_categories, invoke create_role_workspaces.py
    --refresh-personas-only so governing-personas.md auto-regenerates.
"""

import argparse
import os
import json
import sys
import time
import asyncio
import subprocess
import aiohttp
import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

# PRD 2.7: shared path resolver — persona-categories.json canonical path comes
# from get_openclaw_paths()["persona_categories"], not from a local candidate list.
_SHARED_UTILS = Path(__file__).resolve().parents[2] / "shared-utils"
if str(_SHARED_UTILS) not in sys.path:
    sys.path.insert(0, str(_SHARED_UTILS))
try:
    from detect_platform import get_openclaw_paths as _get_openclaw_paths  # type: ignore
    _OPENCLAW_PATHS_AVAILABLE = True
except ImportError:
    _OPENCLAW_PATHS_AVAILABLE = False

# §1.7: Import the shared persona-categories path resolver so orchestrator and
# generate-governing-personas.sh use the SAME resolution chain.
try:
    from resolve_persona_categories_path import get_persona_categories_path as _get_persona_categories_path  # type: ignore
    _PERSONA_RESOLVER_AVAILABLE = True
except ImportError:
    _PERSONA_RESOLVER_AVAILABLE = False

# ─── PATHS ─────────────────────────────────────────────────────────────────────
# v6.6.0: Unified canonical root.
# VPS  → /data/.openclaw/master-files/coaching-personas
# Mac  → ~/.openclaw/workspace/data/coaching-personas
# The old ~/Downloads/openclaw-master-files path is kept as last-resort legacy.
def _resolve_canonical_base() -> Path:
    vps_root = Path("/data/.openclaw/master-files/coaching-personas")
    if vps_root.parent.exists():  # /data/.openclaw/master-files exists
        return vps_root
    mac_root = Path.home() / ".openclaw" / "workspace" / "data" / "coaching-personas"
    if mac_root.parent.parent.exists():  # ~/.openclaw/workspace exists
        return mac_root
    # Legacy path kept for backward compat on old setups
    return Path.home() / "Downloads" / "openclaw-master-files" / "coaching-personas"

BASE = _resolve_canonical_base()
BOOKS_DIR = BASE / "books"
PERSONAS_DIR = BASE / "personas"
PROJECT_DIR = BASE  # status + log live alongside the personas, not in ~/clawd
PROMPTS_DIR = Path(__file__).parent.parent / "agent-prompts"
STATUS_FILE = BASE / "pipeline-status.json"
LOG_FILE = BASE / "pipeline-log.txt"

# ─── MODEL IDs (v10.10.0: PRD §5.4 'book-to-persona' chain) ──────────────────
# Model selection is dynamic via shared-utils/select_model.py with the
# 'book-to-persona' purpose_tier chain (5 positions):
#   1. ollama/kimi-k*:cloud
#   2. openrouter/moonshot/kimi-k*
#   3. ollama/deepseek-v*-pro:cloud
#   4. openrouter/deepseek/deepseek-v*-pro
#   5. openrouter/google/gemini-*-flash-lite       ← cheapest fallback
#
# Phase 3 (synthesis) used to default to GPT-5.3 Codex when nothing else was
# available. As of v10.10.0 we no longer fall through to GPT — Gemini Flash
# Lite is the cheapest non-Anthropic non-GPT path, matching the audit's
# Phase 14.4 requirement (PRD §5.4) and the no-Anthropic-models policy (N1).
# Anthropic models are FORBIDDEN. Filter applied at every tier.
# The fallback strings below are last-resort defaults only used if
# select_model.py itself is unreachable.
def _resolve_model(skill: str, purpose: str, purpose_tier: str,
                   fallback: str, input_chars: int = None) -> str:
    """Call shared-utils/select_model.py with purpose-tier + optional input_chars.

    Passing input_chars makes the selector auto-pick DeepSeek V4-pro (1M ctx) for
    inputs that won't fit in Kimi's 262K window. Default behavior with no
    input_chars uses Kimi-first (smartest thinker).
    """
    selector = Path(__file__).resolve().parents[2] / "shared-utils" / "select_model.py"
    if not selector.exists():
        selector = Path("/data/.openclaw/skills/shared-utils/select_model.py")
    if not selector.exists():
        selector = Path.home() / ".openclaw" / "skills" / "shared-utils" / "select_model.py"
    if not selector.exists():
        selector = Path.home() / "Downloads" / "openclaw-master-files" / "shared-utils" / "select_model.py"
    if not selector.exists():
        return fallback
    cmd = ["python3", str(selector),
           "--skill", skill,
           "--purpose-tier", purpose_tier,
           "--purpose", purpose,
           "--format", "id"]
    if input_chars is not None:
        cmd.extend(["--input-chars", str(input_chars)])
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        model_id = result.stdout.strip()
        if model_id and "anthropic/" not in model_id.lower() and "claude-" not in model_id.lower():
            return model_id
    except Exception:
        pass
    return fallback


def _route_for(model_id: str) -> str:
    """Resolve the API route based on the model's prefix."""
    if model_id.startswith("ollama/"):
        return "ollama"
    if "codex" in model_id:
        return "openai-responses"
    return "openrouter"


def resolve_phase_model(phase: str, input_chars: int = None) -> tuple:
    """
    Resolve (model_id, route) for a given pipeline phase.
    Pass input_chars when the actual input size is known so the selector
    can context-switch to DeepSeek V4-pro for large/huge books.

    v10.10.0 — all three phases use the PRD §5.4 'book-to-persona' chain:
      normal context: Ollama Kimi → OpenRouter Kimi → Ollama DeepSeek Pro →
                      OpenRouter DeepSeek Pro → Gemini Flash Lite
      large context (800K-3M chars): same chain, large-input variant where
                      DeepSeek Pro (1M ctx) leads
      huge context  (> 3M chars):    DeepSeek Pro only

    No GPT in the chain. No Anthropic. Gemini Flash Lite is the cheapest
    fallback per PRD §5.4 and the audit's Phase 14.4 requirement.
    """
    purpose_map = {
        "phase1": "Phase 1 extraction",
        "phase2": "Phase 2 analysis",
        "phase3": "Phase 3 synthesis",
    }
    purpose = purpose_map.get(phase, phase)
    # v10.10.0: the LAST-RESORT fallback (used only when select_model.py is
    # itself unreachable) is now Gemini Flash Lite, not GPT/Kimi. This
    # matches PRD §5.4 (the 'book-to-persona' chain ends at Flash Lite) and
    # closes audit Phase 14.4 finding ("Phase 3 = GPT-5.3 Codex").
    # Trevor 2026-06-01: book-to-persona runs on the fleet-standard DeepSeek V4 Pro
    # chain (the latest). Primary = Ollama Cloud deepseek-v4-pro:cloud; the selector
    # falls to OpenRouter deepseek/deepseek-v4-pro if Ollama isn't on the box. No kimi.
    fallback = "ollama/deepseek-v4-pro:cloud"
    # Tier-5 (no Ollama, no OpenRouter, no models matching) falls to
    # Gemini Flash Lite per PRD §5.4 position 5 — this is the LAST RESORT.
    last_resort = "openrouter/google/gemini-3.1-flash-lite-preview"

    model_id = _resolve_model("book-to-persona", purpose, "book-to-persona", fallback, input_chars=input_chars)
    # If _resolve_model couldn't find anything, it falls back to the
    # `fallback` string above. If even that's not in the client's config,
    # final defense: Gemini Flash Lite. This makes the comment "no GPT in
    # the chain" structurally true.
    if not model_id:
        model_id = last_resort
    return model_id, _route_for(model_id)


# Default models for module import (resolved without book size — caller should re-resolve per book):
MODEL_EXTRACTION, MODEL_EXTRACTION_ROUTE = resolve_phase_model("phase1")
MODEL_ANALYSIS,   MODEL_ANALYSIS_ROUTE   = resolve_phase_model("phase2")
MODEL_SYNTHESIS,  MODEL_SYNTHESIS_ROUTE  = resolve_phase_model("phase3")

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
# v10.3.0: Ollama Cloud is now the primary route for heavy reasoning. The
# selector picks ollama/* first; we only need OpenRouter/OAuth as fallback
# routes if the client doesn't have Ollama Cloud configured.
OLLAMA_API_KEY      = _KEYS.get("OLLAMA_API_KEY") or os.environ.get("OLLAMA_API_KEY", "")
OPENROUTER_API_KEY  = _KEYS.get("OPENROUTER_API_KEY") or os.environ.get("OPENROUTER_API_KEY", "")
OPENAI_API_KEY      = _KEYS.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY", "")
MOONSHOT_API_KEY    = _KEYS.get("MOONSHOT_API_KEY") or os.environ.get("MOONSHOT_API_KEY", "")  # deprecated, kept for back-compat only

# No hard requirement on any single key — at least ONE provider key must
# be present, but the selector decides which one to use. Crashing on a
# missing MOONSHOT_API_KEY was the old (pre-v10.3.0) behavior and was wrong:
# it forced clients with Ollama Cloud to also configure Moonshot, even
# though the new chain never calls Moonshot direct anymore.
if not (OLLAMA_API_KEY or OPENROUTER_API_KEY or OPENAI_API_KEY):
    raise ValueError(
        "No model provider API key found. Set at least one of: "
        "OLLAMA_API_KEY (preferred), OPENROUTER_API_KEY (fallback), or OPENAI_API_KEY (last resort) "
        "in secrets/.env or as a container env var."
    )

OLLAMA_BASE_URL     = "https://ollama.com/api"
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

# ─── PERSONA CATEGORIES UPDATER (PRD 2.7) ────────────────────────────────────
def _persona_categories_path() -> Path:
    """Locate persona-categories.json via the shared path resolver (§1.7 / PRD 2.7).

    Resolution order (§3.1):
    1. get_openclaw_paths()["persona_categories"] from detect_platform.py (canonical)
    2. shared resolve_persona_categories_path.get_persona_categories_path() (§1.7 reconciliation)
    3. BASE / persona-categories.json (local fallback)

    Both this function and generate-governing-personas.sh now call the SAME
    resolve_persona_categories_path resolver, eliminating the workspace/data/coaching-personas/
    vs workspace/coaching-personas/ path drift (§1.7).
    """
    if _OPENCLAW_PATHS_AVAILABLE:
        try:
            return _get_openclaw_paths()["persona_categories"]
        except Exception as e:
            print(f"[orchestrator] WARNING: get_openclaw_paths() failed ({e}); trying shared resolver.")

    # §1.7: Try the shared resolver (same chain as generate-governing-personas.sh)
    if _PERSONA_RESOLVER_AVAILABLE:
        try:
            resolved = _get_persona_categories_path(fail_loud=False)
            if resolved and resolved.is_file():
                return resolved
        except Exception as e:
            print(f"[orchestrator] WARNING: resolve_persona_categories_path failed ({e}); using BASE fallback.")

    # Final fallback — should not occur on a properly installed box.
    return BASE / "persona-categories.json"


def _ledger_append_phase6b_skip(folder: str, detail: str) -> None:
    """§1.7.3: Append a Phase-6b skip/fail record to the add-ledger so converge
    knows to retry governing-personas.md refresh. Best-effort — never raises."""
    import fcntl
    from datetime import datetime, timezone

    oc_root_candidates = [Path("/data/.openclaw"), Path.home() / ".openclaw"]
    oc_root = next((c for c in oc_root_candidates if c.is_dir()), None)
    if not oc_root:
        return

    ledger_dir = oc_root / "extension-sync"
    ledger_dir.mkdir(parents=True, exist_ok=True)
    ledger_path = ledger_dir / "add-ledger.jsonl"
    record = json.dumps({
        "ts": datetime.now(timezone.utc).isoformat(),
        "type": "persona",
        "slug": folder,
        "status": "phase6b-skip",
        "detail": detail,
        "by": "orchestrator",
    }, separators=(",", ":")) + "\n"
    try:
        with open(ledger_path, "a") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(record)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass  # Best-effort


def _append_persona_to_categories(book: dict, folder: str) -> None:
    """Append a new persona entry to persona-categories.json (idempotent).

    PRD 2.7: always writes to the canonical path returned by _persona_categories_path()
    (workspace/data/coaching-personas/persona-categories.json). The skill-folder copy
    is the shipped seed — if the canonical file is absent and the seed exists, the seed
    is COPIED to the canonical location rather than discarded.

    Schema 1.0: personas live under data["personas"][slug] with author, book,
    domain[], perspective[], custom[] fields. We write an empty-tags stub so
    that (a) the persona becomes visible to v2 selector's list_available_personas
    (b) the operator gets a clear "no tags yet" signal to fill in domain +
    perspective tags before the dept-scope filter will include this persona.
    """
    import shutil
    cat_path = _persona_categories_path()
    if not cat_path.exists():
        cat_path.parent.mkdir(parents=True, exist_ok=True)
        # Prefer to seed from the skill-folder copy so existing tags are preserved.
        skill_seed = Path(__file__).resolve().parents[1] / "persona-categories.json"
        if skill_seed.exists():
            shutil.copy2(skill_seed, cat_path)
            print(f"[orchestrator] Seeded {cat_path} from shipped skill-folder copy.")
        else:
            # No seed available — create a minimal v1.0 shell.
            data = {
                "schemaVersion": "1.0",
                "created": datetime.datetime.utcnow().strftime("%Y-%m-%d"),
                "domainTags": [],
                "perspectiveTags": [],
                "personas": {},
            }
            with open(cat_path, "w") as f:
                json.dump(data, f, indent=2)
        data = json.loads(cat_path.read_text())
        if "personas" not in data or not isinstance(data.get("personas"), dict):
            data["personas"] = {}
    else:
        with open(cat_path) as f:
            data = json.load(f)
        if "personas" not in data or not isinstance(data.get("personas"), dict):
            data["personas"] = {}

    if folder in data["personas"]:
        return  # Already present — idempotent no-op.

    data["personas"][folder] = {
        "author": book.get("author", "unknown"),
        "book": book.get("title", folder),
        "domain": [],          # Tag manually before dept filter will include this persona
        "perspective": [],
        "custom": [],
        "added": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    with open(cat_path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"[orchestrator] Appended {folder} to {cat_path} (no tags yet — operator must add domain + perspective).")


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
        try:
            status = json.loads(STATUS_FILE.read_text())
        except Exception:
            status = {}

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
    # Write only if the status dir exists (don't create dirs at module import time)
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
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
    """Locate ebook-convert binary across common install paths. Auto-installs (Homebrew on Mac, apt-get on Linux) if missing. N26."""
    import subprocess
    import platform
    calibre_paths = [
        # Mac
        "/opt/homebrew/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/Applications/calibre.app/Contents/MacOS/ebook-convert",
        # Linux (VPS)
        "/usr/bin/ebook-convert",
        "/usr/local/bin/ebook-convert",
        "/snap/bin/ebook-convert",
        "/opt/calibre/ebook-convert",
    ]
    for p in calibre_paths:
        if Path(p).exists():
            return p
    result = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip()

    is_linux = platform.system() == "Linux"

    if is_linux:
        # Linux/VPS path: try apt-get first, then upstream installer fallback
        log("Calibre not found. Auto-installing on Linux via apt-get (this may take a few minutes)...")
        apt_get = None
        for p in ["/usr/bin/apt-get", "/usr/local/bin/apt-get"]:
            if Path(p).exists():
                apt_get = p
                break
        if apt_get:
            sudo_bin = "/usr/bin/sudo" if Path("/usr/bin/sudo").exists() else None
            update_cmd = ([sudo_bin] if sudo_bin else []) + [apt_get, "update", "-y"]
            install_cmd = ([sudo_bin] if sudo_bin else []) + [apt_get, "install", "-y", "calibre"]
            subprocess.run(update_cmd, capture_output=False)
            install_result = subprocess.run(install_cmd, capture_output=False)
            if install_result.returncode == 0:
                log("Calibre installed via apt-get. Continuing...")
                for p in calibre_paths:
                    if Path(p).exists():
                        return p
                result_post = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
                if result_post.returncode == 0 and result_post.stdout.strip():
                    return result_post.stdout.strip()

        # apt-get failed or unavailable — try upstream Calibre installer
        log("apt-get install failed or unavailable. Falling back to upstream Calibre installer...")
        installer_cmd = (
            'wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh '
            '| sh /dev/stdin install_dir=/opt isolated=y'
        )
        install_result2 = subprocess.run(installer_cmd, shell=True, capture_output=False)
        if install_result2.returncode == 0:
            log("Calibre installed via upstream installer. Continuing...")
            for p in calibre_paths:
                if Path(p).exists():
                    return p
            result_post2 = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
            if result_post2.returncode == 0 and result_post2.stdout.strip():
                return result_post2.stdout.strip()
        raise RuntimeError(
            "Calibre auto-install failed on Linux. Please install manually:\n"
            "  sudo apt-get install -y calibre\n"
            "  OR: wget -nv -O- https://download.calibre-ebook.com/linux-installer.sh | sudo sh /dev/stdin"
        )

    # Mac path: auto-install via Homebrew
    log("Calibre not found. Auto-installing via Homebrew (this may take a few minutes)...")
    brew_paths = ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]
    brew_bin = None
    for bp in brew_paths:
        if Path(bp).exists():
            brew_bin = bp
            break
    if brew_bin is None:
        result2 = subprocess.run(["which", "brew"], capture_output=True, text=True)
        if result2.returncode == 0 and result2.stdout.strip():
            brew_bin = result2.stdout.strip()

    if brew_bin:
        install_result = subprocess.run(
            [brew_bin, "install", "--cask", "calibre"],
            capture_output=False,
        )
        if install_result.returncode == 0:
            log("Calibre installed successfully. Continuing...")
            for p in calibre_paths:
                if Path(p).exists():
                    return p
            result3 = subprocess.run(["which", "ebook-convert"], capture_output=True, text=True)
            if result3.returncode == 0 and result3.stdout.strip():
                return result3.stdout.strip()
        else:
            raise RuntimeError("Calibre auto-install failed. Please install manually: brew install --cask calibre")
    else:
        raise RuntimeError(
            "Homebrew not found and Calibre is not installed.\n"
            "Install Homebrew first: /bin/bash -c \"$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\"\n"
            "Then run: brew install --cask calibre"
        )
    raise RuntimeError("Calibre install completed but ebook-convert binary still not found. Please restart Terminal and try again.")


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
    Calibre + DeDRM plugin installed at: ~/.openclaw/skills/22-book-to-persona-coaching-leadership-system/drm-tools/

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

async def call_ollama_cloud(session: aiohttp.ClientSession, model: str, system: str, user: str, max_tokens: int = 16000) -> str:
    """
    Call Ollama Cloud (https://ollama.com/api/chat) for any ollama/* model.
    v10.3.0: this is the PRIMARY route for heavy reasoning. Kimi 2.6+ and
    DeepSeek V4-pro both run here at subscription-billed cost.

    `model` arg must be an Ollama model id WITHOUT the "ollama/" prefix
    (e.g. "kimi-k2.6:cloud" not "ollama/kimi-k2.6:cloud"). Caller strips it.
    """
    if not OLLAMA_API_KEY:
        raise RuntimeError("Ollama Cloud route requested but OLLAMA_API_KEY is not set")

    headers = {
        "Authorization": f"Bearer {OLLAMA_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
        "think": True,  # Trevor 2026-06-01: thinking ON (high) for DeepSeek V4 Pro reasoning
        "options": {
            "temperature": 1.0,
            "num_predict": max_tokens,
        },
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                f"{OLLAMA_BASE_URL}/chat",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=1800),
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    # Ollama Cloud chat response shape: {"message": {"content": "..."}}
                    msg = data.get("message", {}) if isinstance(data, dict) else {}
                    content = msg.get("content", "") if isinstance(msg, dict) else ""
                    if content:
                        return content
                    log(f"  Ollama Cloud returned empty content (attempt {attempt}/{MAX_RETRIES}); body preview: {json.dumps(data)[:200]}")
                else:
                    error_text = await response.text()
                    log(f"  Ollama Cloud error {response.status}: {error_text[:200]}")
                if attempt < MAX_RETRIES:
                    log(f"  Retrying in {RETRY_DELAY}s... (attempt {attempt}/{MAX_RETRIES})")
                    import asyncio as _asyncio
                    await _asyncio.sleep(RETRY_DELAY * attempt)
        except Exception as e:
            log(f"  Exception on attempt {attempt}: {e}")
            if attempt < MAX_RETRIES:
                import asyncio as _asyncio
                await _asyncio.sleep(RETRY_DELAY * attempt)

    raise RuntimeError(f"All {MAX_RETRIES} attempts failed for {model} via Ollama Cloud")


async def call_moonshot(session: aiohttp.ClientSession, system: str, user: str) -> str:
    """
    DEPRECATED in v10.3.0. Kept for backward compatibility but no longer
    referenced by the routing chain. The selector chain now goes:
    Ollama Cloud → OpenRouter (same models) → OAuth GPT. Moonshot direct
    API is not in the chain.

    Calls Kimi K2.5 via Moonshot direct API (legacy path).
    """
    headers = {
        "Authorization": f"Bearer {MOONSHOT_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "kimi-k2.6",
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
                timeout=aiohttp.ClientTimeout(total=1800)  # v9.5.2: 30 min for heavy reasoning
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
        "temperature": 1.0,
        "reasoning": {"effort": "high"}  # Trevor 2026-06-01: thinking HIGH (OpenRouter reasoning effort)
    }

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            async with session.post(
                f"{OPENROUTER_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=1800)  # v9.5.2: 30 min for heavy reasoning
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
                timeout=aiohttp.ClientTimeout(total=3600)  # v9.5.2: 60 min — heavy synthesis can run long on large books
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
    """Load a prompt file. Searches PROMPTS_DIR and fallback locations."""
    candidates = [PROMPTS_DIR / filename]
    # Additional search paths: skill folder agent-prompts/, legacy location
    skill_dir = Path(__file__).parent.parent
    candidates.append(skill_dir / "agent-prompts" / filename)
    for path in candidates:
        if path.exists():
            return path.read_text()
    raise FileNotFoundError(
        f"Prompt file not found: {filename}\n"
        f"Searched: {[str(c) for c in candidates]}"
    )

# Lazy-loaded — evaluated when first used, not at import time.
# This allows `--single-book` to run even if the agent-prompts dir is temporarily
# unavailable (the orchestrator errors with a clear message at the right callsite).
_PROMPT_CACHE: dict = {}

def _get_prompt(filename: str) -> str:
    if filename not in _PROMPT_CACHE:
        _PROMPT_CACHE[filename] = load_prompt(filename)
    return _PROMPT_CACHE[filename]

def _extraction_system() -> str:  return _get_prompt("extraction-agent-prompt.md")
def _analysis_system()   -> str:  return _get_prompt("analysis-agent-prompt.md")
def _synthesis_system()  -> str:  return _get_prompt("synthesis-agent-prompt.md")

# ─── PHASE 1 - EXTRACTION ─────────────────────────────────────────────────────
async def run_extraction(session: aiohttp.ClientSession, book: dict, status: dict) -> bool:
    folder = book["folder"]
    output_path = PERSONAS_DIR / folder / "extraction-notes.md"
    (PERSONAS_DIR / folder).mkdir(parents=True, exist_ok=True)

    log(f"[PHASE 1] Starting extraction: {book['title']}")
    mark_phase(status, folder, 1, "IN_PROGRESS")

    try:
        # v6.6.0: Check for pre-extracted text FIRST (YouTube/video/text sources
        # write their transcript to a text file via add-persona-from-source.sh
        # before calling the orchestrator; we must consume it here, not re-invoke
        # whisper).  Two possible locations:
        #   a) book["_text_file"] — stashed by _build_book_from_source_json()
        #   b) BASE/text/<slug>.txt — the canonical location written by the script
        text = ""
        _pre_text_path = None
        if book.get("_text_file") and Path(book["_text_file"]).exists():
            _pre_text_path = Path(book["_text_file"])
        else:
            for _candidate in [
                BASE / "text" / f"{folder}.txt",
                PERSONAS_DIR / folder / "text" / f"{folder}.txt",
            ]:
                if _candidate.exists() and _candidate.stat().st_size > 0:
                    _pre_text_path = _candidate
                    break

        if _pre_text_path:
            text = _pre_text_path.read_text(encoding="utf-8", errors="ignore")
            log(f"  Using pre-extracted text ({_pre_text_path}): {len(text):,} chars")
        else:
            # Standard book extraction path: resolve file → extract text
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
            text = extract_book_text(book_path)
            log(f"  {fmt} extracted: {len(text):,} characters")

        if not text.strip():
            log(f"  [PHASE 1 FAILED] {book['title']}: text extraction produced empty result")
            mark_phase(status, folder, 1, "FAILED", "Empty text after extraction")
            return False

        # v9.5.1: re-resolve model PER BOOK based on its actual char count.
        # Books > 800K chars switch from Kimi (262K ctx) to DeepSeek V4-pro (1M ctx).
        # Books > 3M chars get DeepSeek-only.
        per_book_model, per_book_route = resolve_phase_model("phase1", input_chars=len(text))
        log(f"  Model for this book (Phase 1, {len(text):,} chars): {per_book_model} via {per_book_route}")

        # If the resolved model is DeepSeek-pro (1M ctx) we can pass the full text.
        # Otherwise truncate to leave room for the system prompt (Kimi: 262K tokens ≈ 900K chars cap).
        max_chars = 3_500_000 if "deepseek-v" in per_book_model and "pro" in per_book_model else 900_000

        user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here is the complete book text. Extract all 20 items as specified in your instructions.

---

{text[:max_chars]}"""

        # v10.3.0: Route the call based on the resolved model. Priority is
        # Ollama Cloud first (cheap subscription), OpenRouter same-model
        # fallback second, OAuth GPT third. Moonshot direct API is no longer
        # in the routing chain (Kimi 2.6 + DeepSeek V4-pro both available
        # via Ollama Cloud and OpenRouter — no need for the direct route).
        _ext_sys = _extraction_system()
        if folder in OPENROUTER_FALLBACK_FOLDERS:
            log(f"  Using OpenRouter fallback for {book['title']} (content filter)")
            or_model = per_book_model.replace("ollama/", "").replace("openrouter/", "")
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "ollama":
            # PRIMARY route — strip the "ollama/" prefix and call Ollama Cloud
            ollama_model = per_book_model.replace("ollama/", "", 1)
            try:
                result = await call_ollama_cloud(session, ollama_model, _ext_sys, user_prompt, max_tokens=16000)
            except Exception as e:
                # Ollama Cloud failed — fall back to OpenRouter same model
                log(f"  Ollama Cloud call failed ({e}); falling back to OpenRouter same model")
                fallback_model = per_book_model.replace("ollama/", "openrouter/").replace(":cloud", "")
                result = await call_openrouter(session, fallback_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "openrouter":
            or_model = per_book_model.replace("openrouter/", "", 1)
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)
        elif per_book_route == "openai-responses":
            # OAuth GPT — uses existing OpenAI client path
            if "call_openai_responses" in globals():
                result = await call_openai_responses(session, per_book_model, _ext_sys, user_prompt, max_tokens=16000)
            else:
                result = await call_codex(session, user_prompt, max_tokens=16000)
        else:
            # Unknown route — try OpenRouter as a safe default
            log(f"  WARN: unknown route '{per_book_route}' for model {per_book_model}; trying OpenRouter")
            or_model = per_book_model.replace("ollama/", "openrouter/").replace(":cloud", "").replace("openrouter/", "", 1)
            result = await call_openrouter(session, or_model, _ext_sys, user_prompt, max_tokens=16000)

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
                # v9.6.2: resolve model per chunk based on chunk size, route accordingly
            per_chunk_model, per_chunk_route = resolve_phase_model("phase2", input_chars=len(chunk))
            log(f"    Model for chunk {i}: {per_chunk_model} via {per_chunk_route}")
            _ana_sys = _analysis_system()
            if per_chunk_route == "openai-responses":
                if "call_openai_responses" in globals():
                    chunk_result = await call_openai_responses(session, per_chunk_model, _ana_sys, user_prompt, max_tokens=16000)
                else:
                    chunk_result = await call_codex(session, user_prompt, max_tokens=16000)
            elif per_chunk_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route
                ollama_model = per_chunk_model.replace("ollama/", "", 1)
                try:
                    chunk_result = await call_ollama_cloud(session, ollama_model, _ana_sys, user_prompt, max_tokens=16000)
                except Exception as e:
                    log(f"    Ollama Cloud chunk call failed ({e}); falling back to OpenRouter")
                    fallback_model = per_chunk_model.replace("ollama/", "openrouter/").replace(":cloud", "")
                    chunk_result = await call_openrouter(session, fallback_model, _ana_sys, user_prompt, max_tokens=16000)
            else:
                or_model = per_chunk_model.replace("openrouter/", "", 1)
                chunk_result = await call_openrouter(session, or_model, _ana_sys, user_prompt, max_tokens=16000)
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

            # v9.6.2: resolve model for the synthesis pass — uses combined size of all chunk analyses
            combined_size = sum(len(ca) for ca in chunk_analyses)
            synth_model, synth_route = resolve_phase_model("phase2", input_chars=combined_size)
            log(f"  Synthesis model: {synth_model} via {synth_route}")
            _ana_sys2 = _analysis_system()
            if synth_route == "openai-responses":
                if "call_openai_responses" in globals():
                    result = await call_openai_responses(session, synth_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
                else:
                    result = await call_codex(session, synthesis_prompt, max_tokens=16000)
            elif synth_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route
                ollama_model = synth_model.replace("ollama/", "", 1)
                try:
                    result = await call_ollama_cloud(session, ollama_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
                except Exception as e:
                    log(f"  Ollama Cloud synthesis call failed ({e}); falling back to OpenRouter")
                    fallback_model = synth_model.replace("ollama/", "openrouter/").replace(":cloud", "")
                    result = await call_openrouter(session, fallback_model, _ana_sys2, synthesis_prompt, max_tokens=16000)
            else:
                or_model = synth_model.replace("openrouter/", "", 1)
                result = await call_openrouter(session, or_model, _ana_sys2, synthesis_prompt, max_tokens=16000)

        else:
            user_prompt = f"""BOOK: {book['title']}
AUTHOR: {book['author']}

Here are the complete extraction notes from Phase 1.
Analyze across all 12 analytical dimensions as specified.

---

{extraction_text}"""

            # v9.6.2: resolve model per book size
            single_model, single_route = resolve_phase_model("phase2", input_chars=len(extraction_text))
            log(f"  Single-pass model: {single_model} via {single_route}")
            _ana_sys3 = _analysis_system()
            if single_route == "openai-responses":
                if "call_openai_responses" in globals():
                    result = await call_openai_responses(session, single_model, _ana_sys3, user_prompt, max_tokens=16000)
                else:
                    result = await call_codex(session, user_prompt, max_tokens=16000)
            elif single_route == "ollama":
                # v10.3.0: Ollama Cloud is now a real route
                ollama_model = single_model.replace("ollama/", "", 1)
                try:
                    result = await call_ollama_cloud(session, ollama_model, _ana_sys3, user_prompt, max_tokens=16000)
                except Exception as e:
                    log(f"  Ollama Cloud single-pass call failed ({e}); falling back to OpenRouter")
                    fallback_model = single_model.replace("ollama/", "openrouter/").replace(":cloud", "")
                    result = await call_openrouter(session, fallback_model, _ana_sys3, user_prompt, max_tokens=16000)
            else:
                or_model = single_model.replace("openrouter/", "", 1)
                result = await call_openrouter(session, or_model, _ana_sys3, user_prompt, max_tokens=16000)

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
        # v6.6.0: look in the skill folder, not PROJECT_DIR (which is now BASE)
        skill_path_candidates = [
            Path(__file__).parent.parent / "SKILL.md",
            BASE / "SKILL.md",
        ]
        skill_spec = ""
        for sp in skill_path_candidates:
            if sp.exists():
                skill_spec = sp.read_text()
                break

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

        # v9.6.2: Phase 3 model resolved per book via heavy-tier selector.
        # Synthesis input combines all extraction + analysis notes — can be large.
        phase3_input_size = len(user_prompt)
        phase3_model, phase3_route = resolve_phase_model("phase3", input_chars=phase3_input_size)
        log(f"  Phase 3 synthesis model: {phase3_model} via {phase3_route} (input ~{phase3_input_size:,} chars)")

        _syn_sys = _synthesis_system()
        full_input = f"{_syn_sys}\n\n---\n\n{user_prompt}"
        if phase3_route == "openai-responses":
            # OAuth GPT route — preferred for Phase 3 synthesis (no per-call cost)
            result = await call_codex(session, full_input, max_tokens=120000)
        elif phase3_route == "ollama":
            # v10.3.0: Ollama Cloud is now a real route — call it directly
            ollama_model = phase3_model.replace("ollama/", "", 1)
            try:
                result = await call_ollama_cloud(session, ollama_model, _syn_sys, user_prompt, max_tokens=120000)
            except Exception as e:
                log(f"  Ollama Cloud call failed ({e}); falling back to OpenRouter same model")
                fallback_model = phase3_model.replace("ollama/", "openrouter/").replace(":cloud", "")
                result = await call_openrouter(session, fallback_model, _syn_sys, user_prompt, max_tokens=120000)
        else:
            # OpenRouter route (e.g. OpenRouter Kimi / OpenRouter DeepSeek-pro)
            or_model = phase3_model.replace("openrouter/", "", 1)
            result = await call_openrouter(session, or_model, _syn_sys, user_prompt, max_tokens=120000)

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

        # Phase 5: Auto re-index persona in Gemini Engine.
        # Pre-v10.14.27 hardcoded the legacy ~/clawd/scripts/gemini-indexer.py
        # path, which doesn't exist on Mac-new (~/.openclaw/...) or VPS
        # (/data/.openclaw/...) — so the indexer was silently skipped on
        # every modern install, leaving the new persona's blueprint
        # un-embedded and invisible to Layer 5 (semantic_task_fit).
        # Now searches all 3 canonical locations.
        indexer_candidates = [
            Path.home() / ".openclaw" / "workspace" / "scripts" / "gemini-indexer.py",
            Path("/data/.openclaw/workspace/scripts/gemini-indexer.py"),
            Path.home() / "clawd" / "scripts" / "gemini-indexer.py",  # legacy
        ]
        indexer_path = next((p for p in indexer_candidates if p.exists()), None)
        if indexer_path is not None:
            log(f"Phase 5: Re-indexing persona in Gemini Engine ({indexer_path})...")
            result_proc = subprocess.run(
                [sys.executable, str(indexer_path)],
                capture_output=True,
                text=True,
                check=False
            )
            if result_proc.returncode != 0:
                log(f"  Warning: gemini-indexer.py exited with code {result_proc.returncode}: {result_proc.stderr[:300]}")
            log("Phase 5: Re-indexing complete.")
        else:
            log(f"  Warning: gemini-indexer.py not found in any of {[str(c) for c in indexer_candidates]}, skipping re-indexing")

        # Phase 6: Append new persona to persona-categories.json so the
        # selector's list_available_personas() can see it on the next run.
        # Pre-v10.14.27 only the add-persona-from-source.sh wrapper did
        # this — direct orchestrator calls (e.g. orchestrator.py --single-book)
        # left the persona invisible to the v2 selector.
        try:
            _append_persona_to_categories(book, folder)
        except Exception as e:
            log(f"  Warning: failed to append {folder} to persona-categories.json: {e}")

        # Phase 6b: v6.6.0 — auto-regenerate governing-personas.md for every
        # department so the command-center dashboard picks up the new persona
        # without a manual `create_role_workspaces.py` run.
        # Uses the --refresh-personas-only flag added in this same PR.
        # Non-fatal: the new persona is still fully usable even if this step fails.
        try:
            crw_candidates = [
                Path(__file__).resolve().parents[2] / "23-ai-workforce-blueprint" / "scripts" / "create_role_workspaces.py",
                Path("/data/.openclaw/skills/23-ai-workforce-blueprint/scripts/create_role_workspaces.py"),
                Path.home() / ".openclaw" / "skills" / "23-ai-workforce-blueprint" / "scripts" / "create_role_workspaces.py",
            ]
            crw_path = next((p for p in crw_candidates if p.exists()), None)
            if crw_path:
                log(f"Phase 6b: Refreshing governing-personas.md for all departments ({crw_path})...")
                crw_proc = subprocess.run(
                    [sys.executable, str(crw_path), "--refresh-personas-only"],
                    capture_output=True, text=True, check=False, timeout=60,
                )
                if crw_proc.returncode == 0:
                    log("Phase 6b: governing-personas.md refresh complete.")
                    # §1.7.3: structured success line for converge/QC
                    print(f"[PERSONA-REFRESH] DONE: governing-personas.md refreshed for all depts")
                else:
                    reason = crw_proc.stderr[:200].strip() or f"rc={crw_proc.returncode}"
                    log(f"  Warning: --refresh-personas-only exited {crw_proc.returncode}: {reason}")
                    # §1.7.3: structured failure line the agent can surface
                    print(f"[PERSONA-REFRESH] FAILED: {reason}")
                    # Append to add-ledger for converge retry
                    _ledger_append_phase6b_skip(folder, f"FAILED: {reason}")
            else:
                msg = "Skill 23 not installed (create_role_workspaces.py not found)"
                log(f"  Phase 6b: {msg} — governing-personas.md NOT refreshed (non-fatal).")
                # §1.7.3: structured SKIPPED line
                print(f"[PERSONA-REFRESH] SKIPPED: {msg}")
                _ledger_append_phase6b_skip(folder, f"SKIPPED: {msg}")
        except Exception as e:
            log(f"  Warning: Phase 6b refresh failed: {e}")
            print(f"[PERSONA-REFRESH] FAILED: {e}")
            _ledger_append_phase6b_skip(folder, f"FAILED: {e}")

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

# ─── PARSE ARGS ───────────────────────────────────────────────────────────────
def _parse_args():
    """
    v6.6.0: argparse so callers can run a single slug instead of the full list.

    --single-book / --slug SLUG
        Build a ONE-element BOOKS entry from the slug's source.json marker
        (written by add-persona-from-source.sh) and run ONLY that folder
        through phases 1-3. This is the #1 fix: without it, every source
        added via add-persona-from-source.sh silently never runs through
        the pipeline because the slug isn't in the hardcoded BOOKS list.

    --source-json PATH
        Explicit path to source.json (overrides the default search).
    """
    parser = argparse.ArgumentParser(
        prog="orchestrator.py",
        description="BlackCEO Coaching Personas Matrix — 3-phase book-to-persona pipeline.",
    )
    parser.add_argument(
        "--single-book", action="store_true",
        help="Run only the single slug specified by --slug (used by add-persona-from-source.sh).",
    )
    parser.add_argument(
        "--slug", metavar="SLUG",
        help="Slug to process when --single-book is given.",
    )
    parser.add_argument(
        "--source-json", metavar="PATH",
        help="Explicit path to source.json for --single-book mode.",
    )
    return parser.parse_args()


def _build_book_from_source_json(slug: str, source_json_path: str = None) -> dict:
    """
    Build a BOOKS-compatible dict from a slug's source.json marker file.
    Searches the canonical personas/<slug>/source.json location when no
    explicit path is given.

    source.json schema (written by add-persona-from-source.sh):
      {
        "slug":        "hormozi-100m-offers",
        "title":       "100M Offers",
        "author":      "Alex Hormozi",
        "source_type": "book",          # book / youtube / video / text
        "source_path": "/path/to/file",
        "text_file":   "/path/to/text/hormozi-100m-offers.txt",
        "added":       "2026-06-01T12:00:00Z",
        "pipeline_status": "PENDING"
      }
    """
    if source_json_path:
        sj_path = Path(source_json_path)
    else:
        sj_path = PERSONAS_DIR / slug / "source.json"

    if not sj_path.exists():
        raise FileNotFoundError(
            f"source.json not found for slug '{slug}'.\n"
            f"Expected: {sj_path}\n"
            "Run add-persona-from-source.sh to register the source first."
        )

    with open(sj_path) as f:
        data = json.load(f)

    source_type = data.get("source_type", "text")
    # For book types, the file field should point to the book file.
    # For video/youtube/text, the pipeline will use the pre-extracted text_file.
    book_file = data.get("source_path", "")
    if source_type != "book":
        # Non-book: the text file is the canonical input; use a dummy "file"
        # that the extraction phase will skip in favour of the pre-extracted text.
        book_file = data.get("text_file", "")

    return {
        "title":  data.get("title", slug),
        "author": data.get("author", "unknown"),
        "file":   str(Path(book_file).name) if book_file else f"{slug}.txt",
        "folder": slug,
        # Stash the full text_file path so run_extraction can pick it up.
        "_text_file": data.get("text_file", ""),
        "_source_type": source_type,
    }


def _ensure_status_entry(status: dict, book: dict) -> dict:
    """
    Guarantee a status entry exists for this book's folder.
    Used by --single-book mode where load_status() only iterates BOOKS.
    """
    folder = book["folder"]
    if folder not in status:
        status[folder] = {
            "title":   book["title"],
            "author":  book["author"],
            "phase1":  "PENDING",
            "phase2":  "PENDING",
            "phase3":  "PENDING",
            "started":   None,
            "completed": None,
            "errors":    [],
        }
        save_status(status)
    return status


# ─── MAIN ORCHESTRATOR ────────────────────────────────────────────────────────
async def main(args=None):
    if args is None:
        args = _parse_args()

    # ── Single-book mode (--single-book --slug SLUG) ──────────────────────────
    if args.single_book:
        if not args.slug:
            print("ERROR: --single-book requires --slug SLUG", file=sys.stderr)
            sys.exit(1)

        log("\n" + "="*60)
        log(f"Skill 22 Pipeline — Single-book mode: {args.slug}")
        log("="*60 + "\n")

        try:
            book = _build_book_from_source_json(args.slug, args.source_json)
        except FileNotFoundError as e:
            log(f"ERROR: {e}")
            sys.exit(1)

        # Load status, ensure entry for this slug
        status = {}
        if STATUS_FILE.exists():
            try:
                status = json.loads(STATUS_FILE.read_text())
            except Exception:
                status = {}
        _ensure_status_entry(status, book)

        log(f"  Title:  {book['title']}")
        log(f"  Author: {book['author']}")
        log(f"  Folder: {book['folder']}")
        log(f"  Source type: {book.get('_source_type', 'book')}")
        s = status[book["folder"]]
        log(f"  Status: P1={s['phase1']} P2={s['phase2']} P3={s['phase3']}")

        if s["phase3"] == "COMPLETE":
            log("  Persona already COMPLETE. Use --force to re-run (not yet implemented).")
            log("  Blueprint at: " + str(PERSONAS_DIR / book["folder"] / "persona-blueprint.md"))
            return

        connector = aiohttp.TCPConnector(limit=5)
        async with aiohttp.ClientSession(connector=connector) as session:
            await process_book(session, book, status)

        final = status[book["folder"]]
        log("\n" + "="*60)
        log(f"Single-book pipeline complete: {args.slug}")
        log(f"  P1={final['phase1']}  P2={final['phase2']}  P3={final['phase3']}")
        log("="*60)
        return

    # ── Full-batch mode (default: process all pending books in BOOKS list) ────
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

# Fallback list — books that hit Kimi direct content filter, route via OpenRouter
# NOTE: This duplicate definition (also at line ~153) is kept here to avoid
# breaking any callers that access it via module inspection. The set at line ~153
# is the canonical one used at runtime; this one is a no-op (already defined).
# OPENROUTER_FALLBACK_FOLDERS = {"samit-disrupt-yourself", "attwood-passion-test"}

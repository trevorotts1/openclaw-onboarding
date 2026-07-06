#!/usr/bin/env python3
"""
build_teleprompter.py -- No-AI generator for the Presenter's Speech TELEPROMPTER.

OWNED BY: Presenter's Speech Writer (ROLE-20), Presentations department.
Referenced by presenters-speech-writer.md SOP 9.2 (delivered alongside the PDF).
Does NOT touch build_deck.py / sync_check.py / PIPELINE-MANIFEST.json (other owners).
build_deck registers the OUTPUT filename `presenter-teleprompter.html` in the bundle.

WHAT IT DOES
------------
Reads the FINISHED `PRESENTERS-SPEECH.md` (the word-for-word script, see CONTRACT
below), parses every slide, and emits a SINGLE self-contained
`presenter-teleprompter.html` -- inline CSS + inline JS + the speech as inline JSON.
No external assets, no network, no build step. The owner double-clicks it and reads.

There is NO AI in this generator. It is a deterministic markdown -> HTML transform.

CONTRACT (what PRESENTERS-SPEECH.md looks like; produced by speech_build_harness.py)
------------------------------------------------------------------------------------
    # PRESENTER'S SPEECH -- <deck_slug>
    DURATION_MIN: 60 | SPOKEN_RATE_WPM: 130
    PAUSE_BUDGET_SEC: 30 | NET_SPOKEN_SEC: 3570
    TARGET_WORDS: 7735 | ACTUAL_WORDS: 7700 | RATIO: 99.5%
    WITHIN_10PCT_BAND: true
    BUILD_AT: 2026-06-17T...

    ## Slide 1 -- Welcome  (WELCOME)
    > STAGE: WELCOME  KIND: normal  BUDGET: 90w  ACTUAL: 88w  SECONDS: 41s

    Hello and welcome, everybody. [PAUSE] ...

    ---

    ## Slide 2 -- Is this you?  (WHO_FOR)
    > STAGE: WHO_FOR  KIND: normal  BUDGET: 60w  ACTUAL: 58w  SECONDS: 27s

    Let me tell you exactly who this is for. ...

    ---

The parser is tolerant: the `## Slide N -- Headline  (STAGE)` line and the
`> ... SECONDS: Ns` metadata line are the load-bearing contract; the rest of the
header is read best-effort. If `SECONDS:` is absent, the per-slide countdown is
computed from the word count at the file's WPM.

ACCEPTED SLIDE HEADER FORMATS (any of these trigger a new slide):
  ## Slide N -- Headline  (STAGE)        ← canonical contract format
  ### Slide N -- Headline                ← extra # tolerated
  [Slide N] Headline                     ← bracket form (agent/client output)
  [Slide N]: Headline                    ← bracket + colon
  [Slide N]                              ← bare bracket (headline may follow on same line or be absent)
  Slide N -- Headline                    ← bare (no ## markers)
  Slide N: Headline                      ← colon separator
  Slide N                                ← bare number only (on its own line)
All forms normalize internally to {no, headline, stage}. Headlines/stages are
extracted best-effort; absent ones default to empty string. If the file has
NO slide markers at all, the parser falls back to splitting on `---` horizontal
rules (treating each section as one slide) with a WARNING printed to stderr
instead of a hard FATAL crash.

FEATURES (the teleprompter, all client-side, vanilla JS, zero dependencies)
- Pre-loaded speech (inline JSON) + a "Load .md" file picker + a "Paste" fallback.
- THREE SELECTABLE SCROLL MODES (a segmented Manual / Auto / Voice control,
  persisted to localStorage; legacy saved values "traditional"/"spoken" migrate
  to "auto"/"voice" so an upgraded file keeps the presenter's old choice):
  * MANUAL: no engine motion — the presenter drives with the wheel, arrow keys,
    the slide rail, or a presenter clicker (Space/PageDown = next slide). The
    always-available floor; every other mode falls back here or to AUTO.
  * AUTO (the previous "Traditional" fixed-speed mode, unchanged): a
    requestAnimationFrame fixed-speed engine with a SUB-PIXEL accumulator
    (carries the fractional remainder so it stays smooth even at the slow
    floor), a dt CLAMP (a stalled / GC / tab-refocus frame can never produce a
    jump), and a curved 18..240 px/s speed range so the slow end is
    readably-slow-but-visibly-moving.
  * VOICE (voice-tracking; the previous "Spoken" mode, hardened): the Web
    Speech API (SpeechRecognition || webkitSpeechRecognition; continuous +
    interim results) listens to the mic and a fuzzy token sequence-aligner
    drives the scroll to keep the spoken word in the reading zone.
    - ADJUSTABLE SENSITIVITY (slider, persisted): one control maps to the
      aligner's fuzz tolerance + lookahead window + backtrack so the presenter
      can tune between "strict word-for-word" and "loose paraphrase-friendly".
    - SLIDING-WINDOW ALIGNMENT: the search window slides forward WITH the
      matches inside one utterance, so a long final result can advance the
      full distance the presenter actually spoke (not just one fixed window).
    - MANUAL-NAV RESYNC: jumping via the rail / arrow keys / clicker RE-SEEDS
      the aligner cursor to the target slide's first token, so voice tracking
      resumes from where the presenter jumped instead of yanking the view back.
    - HARDENED RESTART: recognition re-arms via a short deferred restart and
      recreates the recognizer object if start() throws; a watchdog restarts a
      silently-dead session; repeated hard failures fall back to AUTO with a
      notice. Mic-denied / unsupported auto-falls-back with a one-line notice;
      the Voice option is hidden entirely where SpeechRecognition is absent
      (e.g. Firefox).
    - HOLD: in Voice mode the Play control becomes Follow/Hold — Hold freezes
      the scroll while recognition + highlight continue, Follow eases the view
      back to the live spoken position.
- SMART FUZZY HIGHLIGHT: the script is tokenized once (normalized, with {slide,
  block} back-refs); a bounded local sequence-aligner maps speech onto the script
  tolerant of paraphrase, skips, repeats and ad-libs, confidence-gated. Two-tier
  render: already-spoken tokens dim/strike, the current/interim region is accented
  and drives the scroll anchor (the visual tracked-position indicator). The
  highlight tint derives from the locked brand accent (color-mix with an amber
  rgba fallback for older engines), never a hardcoded house color.
- Big adjustable font (default ~48px) with +/- controls.
- Scroll-speed slider; default seeded from the speech WPM.
- Play / pause on the scroll (Space, or clicker B key).
- PRESENTER-CLICKER keys: PageUp/PageDown + "." map to prev/next; B = pause.
- EYE-LINE READING GUIDE: a fixed anchor line + dim mask above/below the reading
  zone keeps the presenter's gaze at camera height (toggle / G key).
- Mirror modes for beam-splitter rigs: horizontal (scaleX(-1), M key) AND vertical
  flip (scaleY(-1), V key), independently toggleable.
- Mic / recognition-STATUS chip (idle / listening / heard / paused / blocked).
- Progress bar + "Slide N of M".
- A slide RAIL on the left to jump to any slide; current slide is highlighted.
- Manual prev / next slide with the arrow keys, in lockstep with the scroll.
- Per-slide pacing COUNTDOWN from the SECONDS: metadata (turns amber, then red,
  when the presenter runs over that slide's budget).
- Fullscreen toggle.
- Settings persisted to localStorage (font, speed, mirror, vmirror, guide, mode,
  theme).
- Dark high-contrast theme (default) with a light toggle.
- Brand / company name in the header, read from intake.json if available.

DEFERRED (tracked, not built this pass): multi-camera pop-out window, per-slide
WPM auto-calibration, 3-2-1 countdown overlay, post-run actual-vs-budget report.

USAGE
-----
  python3 build_teleprompter.py --speech PRESENTERS-SPEECH.md \
      --out working/delivery/presenter-teleprompter.html [--intake intake.json]
  python3 build_teleprompter.py --sample --out SAMPLE-teleprompter.html
  python3 build_teleprompter.py --emit-sample-speech SAMPLE-PRESENTERS-SPEECH.md
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Per-slide metadata line, e.g.:
#   > STAGE: WELCOME  KIND: normal  BUDGET: 90w  ACTUAL: 88w  SECONDS: 41s
META_RE = re.compile(
    r"^>\s*"
    r"(?:STAGE:\s*(?P<stage>[A-Z_]+))?\s*"
    r"(?:KIND:\s*(?P<kind>\w+))?\s*"
    r"(?:BUDGET:\s*(?P<budget>\d+)\s*w)?\s*"
    r"(?:ACTUAL:\s*(?P<actual>\d+)\s*w)?\s*"
    r"(?:SECONDS:\s*(?P<seconds>\d+)\s*s)?",
    re.IGNORECASE,
)
# Canonical slide header: ## Slide N -- Headline  (STAGE)
# Also matches ### Slide N ...
SLIDE_RE = re.compile(
    r"^#{1,3}\s+Slide\s+(?P<no>\d+)\s*--\s*(?P<headline>.*?)\s*"
    r"(?:\((?P<stage>[^)]*)\))?\s*$",
    re.IGNORECASE,
)
# Bracket form: [Slide N] optional headline / [Slide N]: headline
SLIDE_BRACKET_RE = re.compile(
    r"^\[Slide\s+(?P<no>\d+)\][\s:]*(?P<headline>.*?)\s*"
    r"(?:\((?P<stage>[^)]*)\))?\s*$",
    re.IGNORECASE,
)
# Bare form (no ## or brackets): "Slide N -- Headline" / "Slide N: Headline" / "Slide N"
# Must be at the start of the line and followed by optional separator + headline.
# Guard: bare "Slide N" only triggers on its own line (nothing else on line except
# an optional headline); it must NOT fire inside body prose like "on this slide ..."
SLIDE_BARE_RE = re.compile(
    r"^Slide\s+(?P<no>\d+)"           # "Slide N"
    r"(?:\s*(?:--|:)\s*(?P<headline>.*?))?"  # optional "-- Headline" or ": Headline"
    r"\s*(?:\((?P<stage>[^)]*)\))?\s*$",     # optional "(STAGE)"
    re.IGNORECASE,
)


def _match_slide_header(line):
    """Try all slide-header patterns. Return (no, headline, stage) on match, else None."""
    for pattern in (SLIDE_RE, SLIDE_BRACKET_RE, SLIDE_BARE_RE):
        m = pattern.match(line.strip())
        if m:
            no = int(m.group("no"))
            headline = (m.group("headline") or "").strip()
            # Remove trailing (STAGE) artifact that sometimes bleeds into headline
            headline = re.sub(r"\s*\([A-Z_]+\)\s*$", "", headline).strip()
            stage = (m.group("stage") or "").strip() if "stage" in m.groupdict() else ""
            return no, headline, stage
    return None
# Header key/value lines, e.g.  SPOKEN_RATE_WPM: 130
HEADER_KV_RE = re.compile(r"^([A-Z_]+):\s*(.+)$")
# Pacing cues we surface as their own line in the teleprompter (both forms).
CUE_RE = re.compile(
    r"\[\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\s*\]"
    r"|\(\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\b[^)]*\)",
    re.IGNORECASE,
)


def normalize_cue(raw):
    inner = raw.strip().strip("[]()").strip().upper()
    if inner.startswith("PAUSE"):
        return "[PAUSE]" if inner == "PAUSE" else "[" + " ".join(inner.split()) + "]"
    if inner.startswith("BREATHE"):
        return "[BREATHE]"
    if inner.startswith("SHORT"):
        return "[SHORT PAUSE]"
    if "LONG" in inner and "BREAK" in inner:
        return "[LONG BREAK]"
    if inner.startswith("BREAK"):
        return "[BREAK]"
    return "[" + inner + "]"


def word_count(text):
    stripped = CUE_RE.sub(" ", text)
    return len([w for w in re.split(r"\s+", stripped.strip()) if w])


def parse_speech(md_text, default_wpm=130):
    """Parse PRESENTERS-SPEECH.md into a dict: {meta, wpm, deck_title, slides[...]}.

    Each slide: {no, headline, stage, kind, budget, actual, seconds, blocks[...]}
    where blocks is an ordered list of {"type": "body"|"cue", "text": ...}.
    Robust to the `---` slide separators and to a missing SECONDS metadatum.

    Accepted slide-header variants (see _match_slide_header):
      ## Slide N -- Headline (STAGE)   ← canonical
      ### Slide N -- Headline          ← extra # tolerated
      [Slide N] Headline               ← bracket form
      [Slide N]: Headline              ← bracket + colon
      Slide N: Headline                ← bare with colon
      Slide N -- Headline              ← bare with dash
      Slide N                          ← bare number only
    If NO slide markers exist at all, the text is split on `---` horizontal rules
    (one section per slide) and a WARNING is printed instead of crashing.
    """
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta = {}
    deck_title = "Presenter's Speech"
    wpm = default_wpm

    # Pull the header block (everything before the first slide marker).
    i = 0
    while i < len(lines):
        line = lines[i]
        if _match_slide_header(line) is not None:
            break
        m_title = re.match(r"^#\s+PRESENTER'?S?\s+SPEECH\s*--\s*(.+)$", line, re.IGNORECASE)
        if m_title:
            deck_title = m_title.group(1).strip()
        # split possible "K: v | K2: v2" header lines
        for piece in line.split("|"):
            kv = HEADER_KV_RE.match(piece.strip())
            if kv:
                meta[kv.group(1).upper()] = kv.group(2).strip()
        i += 1

    if meta.get("SPOKEN_RATE_WPM"):
        try:
            wpm = int(re.sub(r"[^0-9]", "", meta["SPOKEN_RATE_WPM"]) or default_wpm)
        except ValueError:
            wpm = default_wpm

    slides = []
    cur = None
    body_lines = []

    def flush_body():
        """Turn the accumulated body lines of the current slide into ordered blocks."""
        if cur is None:
            return
        text = "\n".join(body_lines).strip()
        blocks = []
        # Split on blank lines into paragraph blocks, then pull standalone cues out.
        for block in re.split(r"\n\s*\n", text):
            block = block.strip()
            if not block:
                continue
            parts = re.split(f"({CUE_RE.pattern})", block, flags=re.IGNORECASE)
            buf = ""
            for part in parts:
                if part is None:
                    continue
                if CUE_RE.fullmatch(part.strip()):
                    if buf.strip():
                        blocks.append({"type": "body", "text": re.sub(r"\s+", " ", buf).strip()})
                        buf = ""
                    blocks.append({"type": "cue", "text": normalize_cue(part)})
                else:
                    buf += part
            if buf.strip():
                blocks.append({"type": "body", "text": re.sub(r"\s+", " ", buf).strip()})
        cur["blocks"] = blocks
        spoken_plain = " ".join(b["text"] for b in blocks if b["type"] == "body")
        wc = cur.get("actual") or word_count(spoken_plain)
        cur["words"] = wc
        if not cur.get("seconds"):
            cur["seconds"] = round(wc / (wpm / 60.0)) if wc else 0

    while i < len(lines):
        line = lines[i]
        slide_match = _match_slide_header(line)
        if slide_match is not None:
            flush_body()
            no, headline, stage = slide_match
            cur = {
                "no": no,
                "headline": headline,
                "stage": stage,
                "kind": "normal",
                "budget": None, "actual": None, "seconds": None,
                "blocks": [],
            }
            slides.append(cur)
            body_lines = []
            i += 1
            continue
        if cur is not None and line.strip().startswith(">"):
            mm = META_RE.match(line.strip())
            if mm:
                if mm.group("stage") and not cur["stage"]:
                    cur["stage"] = mm.group("stage")
                if mm.group("kind"):
                    cur["kind"] = mm.group("kind")
                if mm.group("budget"):
                    cur["budget"] = int(mm.group("budget"))
                if mm.group("actual"):
                    cur["actual"] = int(mm.group("actual"))
                if mm.group("seconds"):
                    cur["seconds"] = int(mm.group("seconds"))
            i += 1
            continue
        if line.strip() == "---":
            i += 1
            continue
        if cur is not None:
            body_lines.append(line)
        i += 1
    flush_body()

    # ------------------------------------------------------------------ #
    # FALLBACK: no slide markers found at all — split on "---" separators #
    # (or on paragraph breaks) and synthesize numbered slides with a      #
    # WARNING instead of crashing.                                         #
    # ------------------------------------------------------------------ #
    if not slides:
        print(
            "WARNING: no slide markers found in the speech file (tried ## Slide N, "
            "[Slide N], and bare Slide N forms). Falling back to splitting on '---' "
            "horizontal rules. Per-slide pacing will be computed from word counts at "
            f"{wpm} WPM. Add '## Slide N -- Headline' headers for accurate pacing.",
            file=sys.stderr,
        )
        sections = re.split(r"(?m)^---\s*$", md_text)
        if len(sections) <= 1:
            # No --- either — split on double newlines (paragraphs as slides)
            sections = [s for s in re.split(r"\n\s*\n\s*\n", md_text) if s.strip()]
        for idx, section in enumerate(sections, start=1):
            section = section.strip()
            if not section:
                continue
            # Use the first non-empty line as the headline if it looks like one
            first_line = next((ln.strip().lstrip("#").strip()
                               for ln in section.splitlines() if ln.strip()), "")
            # If the first line is very long it's body text not a headline; truncate
            headline = first_line[:80] if first_line else f"Section {idx}"
            body_text = section
            blocks = [{"type": "body", "text": re.sub(r"\s+", " ", body_text.strip())}]
            wc = word_count(body_text)
            slides.append({
                "no": idx,
                "headline": headline,
                "stage": "",
                "kind": "normal",
                "budget": None,
                "actual": None,
                "seconds": round(wc / (wpm / 60.0)) if wc else 0,
                "words": wc,
                "blocks": blocks,
            })

    return {
        "deck_title": deck_title,
        "wpm": wpm,
        "meta": meta,
        "slides": slides,
    }


# Filler words dropped during normalization (mirror of the JS NORM filler set).
_FILLER = {"um", "uh", "erm", "uhh", "umm", "er", "ah", "like", "you", "know"}
_NUM_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four", "5": "five",
    "6": "six", "7": "seven", "8": "eight", "9": "nine", "10": "ten",
}


def _norm_token(raw):
    """Normalize one word to a comparison token: lowercase, strip punctuation,
    fold cheap small numbers to words. Returns '' if it normalizes to nothing."""
    t = raw.lower()
    t = re.sub(r"[^a-z0-9']", "", t)
    t = t.strip("'")
    if not t:
        return ""
    if t in _NUM_WORDS:
        t = _NUM_WORDS[t]
    return t


def tokenize_script(data):
    """Flatten every body block into a single ordered token array with
    back-references. Each token is {t, slide, block, w} where:
      t     = normalized comparison token (lowercased, de-punctuated)
      slide = slide index (0-based, into data['slides'])
      block = block index within that slide's blocks[]
      w     = the original surface word (for per-token span rendering)
    Cue blocks are skipped (they are not spoken). Filler tokens that normalize
    to '' are skipped so the aligner never has to match them. The same {slide,
    block, tokenIndexInBlock} lets the runtime wrap each surface word in a span.
    """
    tokens = []
    slides = data.get("slides") or []
    for si, s in enumerate(slides):
        for bi, b in enumerate(s.get("blocks") or []):
            if b.get("type") != "body":
                continue
            words = re.split(r"\s+", (b.get("text") or "").strip())
            wi = 0
            for w in words:
                if not w:
                    continue
                nt = _norm_token(w)
                if nt and nt not in _FILLER:
                    tokens.append({"t": nt, "slide": si, "block": bi, "wi": wi, "w": w})
                wi += 1
    return tokens


def read_brand_name(intake_path):
    """Best-effort company/brand name from intake.json. Returns '' if unavailable."""
    if not intake_path:
        return ""
    p = Path(intake_path)
    if not p.exists():
        return ""
    try:
        data = json.loads(p.read_text())
    except Exception:
        return ""
    for key in ("COMPANY_NAME", "company_name", "BRAND_NAME", "brand_name",
                "OWNER_NAME", "owner_name", "CLIENT_NAME", "client_name"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


HOUSE_ACCENT = "#f2b134"

# ---------------------------------------------------------------------------
# AF-BUNDLE-COMPLETE floors (enforced at the point of production).
# The teleprompter is a REQUIRED deliverable. The static HTML template (inline
# CSS + the full vanilla-JS engine) is ~40 KB before any speech content, so a
# real render is always well above this floor; a file below it is truncated or
# degenerate and must hard-fail rather than ship. The bundle gate reads this
# same floor; the producer refuses to write anything under it.
# ---------------------------------------------------------------------------
TELEPROMPTER_MIN_BYTES = 20000

# External-asset detector: a self-contained teleprompter loads NOTHING over the
# network. Matches only resource-loading tags whose src/href/data points off-box
# (http(s):// or protocol-relative //). Inline JSON speech data — including any
# URL spoken in the script — is plain text inside <script type="application/json">
# and is NOT matched here, so legitimate spoken content never false-fails.
EXTERNAL_ASSET_RE = re.compile(
    r'<(?:script|link|img|iframe|source|audio|video|object|embed)\b'
    r'[^>]*?\b(?:src|href|data)\s*=\s*["\']?\s*(?:https?:)?//',
    re.IGNORECASE,
)
EXTERNAL_IMPORT_RE = re.compile(
    r'@import\s+(?:url\()?\s*["\']?\s*(?:https?:)?//', re.IGNORECASE
)


def verify_teleprompter_html(html):
    """Return a list of fatal issues with a rendered teleprompter (empty == valid).

    Enforces the AF-BUNDLE-COMPLETE floors at the point of production so a
    degenerate file is never written:
      1. every template placeholder was substituted,
      2. the file is self-contained (no external asset loads / @import),
      3. the file is at/above TELEPROMPTER_MIN_BYTES.
    """
    issues = []
    for ph in ("__SPEECH_JSON__", "__TOKENS_JSON__", "__BRAND_NAME__",
               "__WPM__", "__ACCENT_HEX__"):
        if ph in html:
            issues.append(f"unsubstituted template placeholder {ph}")
    m = EXTERNAL_ASSET_RE.search(html)
    if m:
        issues.append(f"not self-contained: external asset load near {m.group(0)!r}")
    if EXTERNAL_IMPORT_RE.search(html):
        issues.append("not self-contained: external @import in CSS")
    n = len(html.encode("utf-8"))
    if n < TELEPROMPTER_MIN_BYTES:
        issues.append(
            f"teleprompter is {n} bytes, below the {TELEPROMPTER_MIN_BYTES}-byte "
            f"minimum (truncated/degenerate)"
        )
    return issues


def read_design_system_accent(design_system_path):
    """Best-effort locked brand accent hex from design_system.json.

    Reads brand.accent (preferred), falling back to brand.accent_hex then
    brand.primary. Returns the HOUSE_ACCENT fallback if the file is absent,
    unreadable, or has no usable accent. Validates the value is a #RGB/#RRGGBB
    hex string before accepting it.
    """
    if not design_system_path:
        return HOUSE_ACCENT
    p = Path(design_system_path)
    if not p.exists():
        return HOUSE_ACCENT
    try:
        data = json.loads(p.read_text())
    except Exception:
        return HOUSE_ACCENT
    brand = data.get("brand") if isinstance(data, dict) else None
    if not isinstance(brand, dict):
        return HOUSE_ACCENT
    for key in ("accent", "accent_hex", "primary"):
        v = brand.get(key)
        if isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{3}([0-9A-Fa-f]{3})?", v.strip()):
            return v.strip()
    return HOUSE_ACCENT


# ---------------------------------------------------------------------------
# HTML template. The speech payload is injected as inline JSON at __SPEECH_JSON__,
# the brand name at __BRAND_NAME__, the default WPM at __WPM__, and the locked
# brand accent hex at __ACCENT_HEX__ (from design_system.json, fallback #f2b134).
# Everything else is static, self-contained CSS + JS. No external assets.
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Presenter's Speech -- Teleprompter</title>
<style>
  :root {
    --bg: #0b0d12; --fg: #f5f7fa; --muted: #8a93a3; --accent: __ACCENT_HEX__;
    --rail: #141821; --rail-active: #1d2430; --cue: __ACCENT_HEX__; --over: #ff5a5a;
    --ok: #57d977; --warn: __ACCENT_HEX__;
  }
  html.light {
    --bg: #fbfbf9; --fg: #1a1a1a; --muted: #6b6b6b; --accent: #b9810a;
    --rail: #f0efe9; --rail-active: #e4e2d8; --cue: #b9810a; --over: #c62828;
    --ok: #2e7d32; --warn: #b9810a;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; background: var(--bg); color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
  #app { display: grid; grid-template-columns: 240px 1fr; grid-template-rows: auto 1fr auto;
    height: 100vh; grid-template-areas: "head head" "rail stage" "rail bar"; }
  header { grid-area: head; display: flex; align-items: center; gap: 16px;
    padding: 10px 18px; border-bottom: 1px solid var(--rail-active); flex-wrap: wrap; }
  header .brand { font-weight: 700; font-size: 16px; }
  header .brand .sub { color: var(--muted); font-weight: 400; margin-left: 8px; font-size: 13px; }
  header .spacer { flex: 1; }
  header .ctl { display: flex; align-items: center; gap: 6px; font-size: 13px; color: var(--muted); }
  header button, header input[type=range] { font: inherit; }
  header button { background: var(--rail); color: var(--fg); border: 1px solid var(--rail-active);
    border-radius: 6px; padding: 6px 10px; cursor: pointer; font-size: 13px; }
  header button:hover { border-color: var(--accent); }
  header button.on { background: var(--accent); color: #1a1a1a; border-color: var(--accent); }
  #rail { grid-area: rail; overflow-y: auto; background: var(--rail);
    border-right: 1px solid var(--rail-active); padding: 8px 0; }
  #rail .item { padding: 8px 14px; cursor: pointer; border-left: 3px solid transparent;
    font-size: 13px; color: var(--muted); line-height: 1.3; }
  #rail .item:hover { background: var(--rail-active); }
  #rail .item.active { background: var(--rail-active); border-left-color: var(--accent); color: var(--fg); }
  #rail .item .n { font-weight: 700; color: var(--fg); }
  #rail .item .h { display: block; font-size: 12px; }
  #stage { grid-area: stage; overflow-y: auto; scroll-behavior: smooth; position: relative; padding: 6vh 8vw 60vh; }
  #stage.mirror #scroll { transform: scaleX(-1); }
  .slide { margin: 0 0 7vh; }
  .slide .label { color: var(--muted); font-size: 18px; letter-spacing: .06em;
    text-transform: uppercase; margin-bottom: 14px; border-bottom: 1px solid var(--rail-active);
    padding-bottom: 8px; }
  .slide .label .num { color: var(--fg); font-weight: 700; }
  .slide.cur .label .num { color: var(--accent); }
  .slide p { margin: 0 0 0.7em; line-height: 1.5; }
  .slide p.cue { color: var(--cue); font-weight: 700; letter-spacing: .05em; }
  .slide p.owner { color: var(--accent); font-weight: 600; }
  #bar { grid-area: bar; display: flex; align-items: center; gap: 16px;
    padding: 8px 18px; border-top: 1px solid var(--rail-active); font-size: 14px; }
  #progwrap { flex: 1; height: 8px; background: var(--rail-active); border-radius: 4px; overflow: hidden; }
  #prog { height: 100%; width: 0; background: var(--accent); transition: width .2s linear; }
  #count { font-variant-numeric: tabular-nums; font-weight: 700; min-width: 96px; text-align: right; }
  #count.warn { color: var(--warn); } #count.over { color: var(--over); }
  #pos { color: var(--muted); min-width: 110px; }
  #loader { position: fixed; inset: 0; background: rgba(0,0,0,.78); display: none;
    align-items: center; justify-content: center; z-index: 50; }
  #loader .box { background: var(--rail); border: 1px solid var(--rail-active); border-radius: 12px;
    padding: 22px; width: min(640px, 92vw); }
  #loader h2 { margin: 0 0 12px; }
  #loader textarea { width: 100%; height: 220px; background: var(--bg); color: var(--fg);
    border: 1px solid var(--rail-active); border-radius: 8px; padding: 10px; font: 13px/1.4 monospace; }
  #loader .row { display: flex; gap: 10px; margin-top: 12px; flex-wrap: wrap; }
  .hint { color: var(--muted); font-size: 12px; }
  kbd { background: var(--rail-active); border-radius: 4px; padding: 1px 5px; font-size: 12px; }

  /* Mode control, status chip, two-tier highlight, guide */
  #stage.vmirror #scroll { transform: scaleY(-1); }
  #stage.mirror.vmirror #scroll { transform: scaleX(-1) scaleY(-1); }
  .modes { display: inline-flex; border: 1px solid var(--rail-active);
    border-radius: 8px; overflow: hidden; }
  .modes button { border: 0; border-radius: 0; margin: 0; }
  .modes button + button { border-left: 1px solid var(--rail-active); }
  .slide .tok { transition: color .15s ease, background .15s ease; }
  /* committed (already-spoken): dimmed + struck */
  .slide .tok.spoken { color: var(--muted); text-decoration: line-through;
    text-decoration-thickness: 1px; opacity: .65; }
  /* current/interim region: accent highlight (drives the scroll anchor).
     rgba amber = fallback for engines without color-mix; the color-mix line
     re-derives the tint from the LOCKED brand accent so it always matches. */
  .slide .tok.cur { color: var(--accent); background: rgba(242,177,52,.14);
    background: color-mix(in srgb, var(--accent) 16%, transparent);
    border-radius: 4px; }
  html.light .slide .tok.cur { background: rgba(185,129,10,.15);
    background: color-mix(in srgb, var(--accent) 18%, transparent); }
  /* eye-line reading guide: fixed anchor line + dim mask above/below the zone */
  #guide { position: absolute; inset: 0; pointer-events: none; display: none; z-index: 5; }
  #stage.guide #guide { display: block; }
  #guide .mask-top, #guide .mask-bot { position: absolute; left: 0; right: 0;
    background: rgba(0,0,0,.45); }
  html.light #guide .mask-top, html.light #guide .mask-bot { background: rgba(255,255,255,.45); }
  #guide .mask-top { top: 0; height: 26%; }
  #guide .mask-bot { top: 38%; bottom: 0; }
  #guide .line { position: absolute; left: 0; right: 0; top: 26%; height: 2px;
    background: var(--accent); opacity: .8; }
  /* recognition-status chip */
  #micChip { display: none; align-items: center; gap: 6px; font-size: 12px;
    padding: 4px 10px; border-radius: 999px; background: var(--rail);
    border: 1px solid var(--rail-active); color: var(--muted); }
  #micChip.show { display: inline-flex; }
  #micChip .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--muted); }
  #micChip.listening .dot { background: var(--ok); animation: pulse 1.2s infinite; }
  #micChip.heard .dot { background: var(--accent); }
  #micChip.paused .dot { background: var(--muted); }
  #micChip.err .dot { background: var(--over); }
  @keyframes pulse { 0%,100%{opacity:1;} 50%{opacity:.3;} }
  #notice { position: fixed; left: 50%; bottom: 18px; transform: translateX(-50%);
    background: var(--rail); border: 1px solid var(--accent); color: var(--fg);
    padding: 10px 16px; border-radius: 8px; font-size: 13px; max-width: 80vw;
    z-index: 60; display: none; box-shadow: 0 6px 24px rgba(0,0,0,.4); }
  #notice.show { display: block; }
  header button[hidden] { display: none; }
  header .ctl[hidden] { display: none; }   /* .ctl sets display:flex; [hidden] must still win */
</style>
</head>
<body>
<div id="app">
  <header>
    <div class="brand">__BRAND_NAME__<span class="sub" id="decktitle"></span></div>
    <div class="spacer"></div>
    <div class="ctl">
      <span class="modes" role="group" aria-label="Scroll mode">
        <button id="modeManualBtn" title="No auto-scroll: wheel, arrows, rail, or clicker (Space = next slide)">Manual</button>
        <button id="modeAutoBtn" title="Fixed-speed auto-scroll (Space = play/pause)">Auto</button>
        <button id="modeVoiceBtn" title="Voice-tracking: the prompter listens and follows what you actually say (Space = follow/hold)">Voice</button>
      </span>
      <span id="micChip"><span class="dot"></span><span class="txt">idle</span></span>
    </div>
    <div class="ctl"><button id="playBtn" title="Space">Play</button></div>
    <div class="ctl" id="speedCtl">Speed
      <button id="spdDown">-</button>
      <input id="speed" type="range" min="0" max="100" value="35">
      <button id="spdUp">+</button>
    </div>
    <div class="ctl" id="sensCtl" hidden>Sensitivity
      <input id="sens" type="range" min="0" max="100" value="50"
        title="Left = strict word-for-word tracking; right = loose, paraphrase-friendly tracking">
    </div>
    <div class="ctl">Font
      <button id="fontDown">A-</button><button id="fontUp">A+</button>
    </div>
    <div class="ctl">
      <button id="mirrorBtn" title="Horizontal mirror for beam splitter">Mirror H</button>
      <button id="vmirrorBtn" title="Vertical flip for beam splitter">Mirror V</button>
      <button id="guideBtn" title="Eye-line reading guide">Guide</button>
      <button id="themeBtn">Light</button>
      <button id="fsBtn" title="Fullscreen">Full</button>
      <button id="loadBtn">Load .md</button>
    </div>
  </header>
  <nav id="rail"></nav>
  <main id="stage"><div id="scroll"></div>
    <div id="guide"><div class="mask-top"></div><div class="line"></div><div class="mask-bot"></div></div>
  </main>
  <footer id="bar">
    <button id="prevBtn" title="Left arrow">&#8592; Prev</button>
    <button id="nextBtn" title="Right arrow">Next &#8594;</button>
    <div id="pos">Slide 0 of 0</div>
    <div id="progwrap"><div id="prog"></div></div>
    <div id="count" title="Time remaining on this slide">00:00</div>
  </footer>
</div>

<div id="loader">
  <div class="box">
    <h2>Load a Presenter's Speech</h2>
    <p class="hint">Pick a PRESENTERS-SPEECH.md file, or paste its contents below.</p>
    <input id="fileInput" type="file" accept=".md,.markdown,.txt">
    <textarea id="pasteArea" placeholder="Accepted formats:
## Slide 1 -- Welcome  (WELCOME)
[Slide 1] Welcome
Slide 1: Welcome
Slide 1 -- Welcome

&gt; STAGE: WELCOME  KIND: normal  BUDGET: 90w  ACTUAL: 88w  SECONDS: 41s

Hello and welcome, everybody. [PAUSE] ..."></textarea>
    <div class="row">
      <button id="parsePaste">Use pasted text</button>
      <button id="closeLoader">Cancel</button>
    </div>
  </div>
</div>

<div id="notice"></div>

<script id="speech-data" type="application/json">__SPEECH_JSON__</script>
<script id="token-data" type="application/json">__TOKENS_JSON__</script>
<script>
"use strict";
const DEFAULT_WPM = __WPM__;
const FONT_KEY = "ptp.font", SPEED_KEY = "ptp.speed", MIRROR_KEY = "ptp.mirror", THEME_KEY = "ptp.theme";
const MODE_KEY = "ptp.mode", VMIRROR_KEY = "ptp.vmirror", GUIDE_KEY = "ptp.guide";
const SENS_KEY = "ptp.sens";
// Mode values: "manual" | "auto" | "voice". Legacy persisted values migrate:
// "traditional" -> "auto", "spoken" -> "voice" (never lose a presenter's choice).
function migrateMode(v){
  if(v==="traditional") return "auto";
  if(v==="spoken") return "voice";
  return (v==="manual"||v==="auto"||v==="voice") ? v : null;
}

// ---- cue / pacing parsing (mirror of the Python parser, for pasted/loaded files)
const CUE_RE = /\[\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\s*\]|\(\s*(?:PAUSE|BREATHE|BREAK|LONG[- ]?BREAK|SHORT\s+PAUSE)\b[^)]*\)/ig;
const OWNER_RE = /\((?:OWNER|CLIENT)[^)]*\)/ig;
function normCue(raw){
  let s = raw.trim().replace(/^[\[\(]|[\]\)]$/g,"").trim().toUpperCase();
  if(s.startsWith("PAUSE")) return s==="PAUSE" ? "[PAUSE]" : "["+s.split(/\s+/).join(" ")+"]";
  if(s.startsWith("BREATHE")) return "[BREATHE]";
  if(s.startsWith("SHORT")) return "[SHORT PAUSE]";
  if(s.includes("LONG")&&s.includes("BREAK")) return "[LONG BREAK]";
  if(s.startsWith("BREAK")) return "[BREAK]";
  return "["+s+"]";
}
function wordCount(t){ return t.replace(CUE_RE," ").trim().split(/\s+/).filter(Boolean).length; }

// ---- markdown -> data (used only for runtime Load/Paste; build-time uses Python)
// Accepts all slide-header variants: ## Slide N -- H (STAGE), ### Slide N -- H,
// [Slide N] H, [Slide N]: H, Slide N -- H, Slide N: H, bare Slide N.
function parseMarkdown(md){
  const lines = md.replace(/\r\n?/g,"\n").split("\n");
  let wpm = DEFAULT_WPM, deck = "Presenter's Speech";
  // Canonical: ## Slide N -- Headline (STAGE) or ### Slide N ...
  const slideRe  = /^#{1,3}\s+Slide\s+(\d+)\s*--\s*(.*?)\s*(?:\(([^)]*)\))?\s*$/i;
  // Bracket: [Slide N] Headline or [Slide N]: Headline
  const slideBrRe = /^\[Slide\s+(\d+)\][\s:]*([^(]*?)\s*(?:\(([^)]*)\))?\s*$/i;
  // Bare: "Slide N -- Headline" / "Slide N: Headline" / "Slide N" (whole line)
  const slideBareRe = /^Slide\s+(\d+)(?:\s*(?:--|:)\s*([^(]*?))?\s*(?:\(([^)]*)\))?\s*$/i;
  const metaRe = /^>\s*(?:STAGE:\s*([A-Z_]+))?\s*(?:KIND:\s*(\w+))?\s*(?:BUDGET:\s*(\d+)\s*w)?\s*(?:ACTUAL:\s*(\d+)\s*w)?\s*(?:SECONDS:\s*(\d+)\s*s)?/i;

  function matchSlide(line){
    for(const re of [slideRe, slideBrRe, slideBareRe]){
      const m=re.exec(line.trim());
      if(m){
        let hl=(m[2]||"").trim().replace(/\s*\([A-Z_]+\)\s*$/,"").trim();
        return {no:+m[1], headline:hl, stage:(m[3]||"").trim()};
      }
    }
    return null;
  }

  const slides=[]; let cur=null, body=[];
  function flush(){
    if(!cur) return;
    const text = body.join("\n").trim();
    const blocks=[];
    text.split(/\n\s*\n/).forEach(block=>{
      block=block.trim(); if(!block) return;
      const parts = block.split(new RegExp("("+CUE_RE.source+")","i"));
      let buf="";
      parts.forEach(part=>{
        if(part===undefined) return;
        if(new RegExp("^(?:"+CUE_RE.source+")$","i").test(part.trim())){
          if(buf.trim()){ blocks.push({type:"body",text:buf.replace(/\s+/g," ").trim()}); buf=""; }
          blocks.push({type:"cue",text:normCue(part)});
        } else { buf+=part; }
      });
      if(buf.trim()) blocks.push({type:"body",text:buf.replace(/\s+/g," ").trim()});
    });
    const plain = blocks.filter(b=>b.type==="body").map(b=>b.text).join(" ");
    const wc = cur.actual || wordCount(plain);
    cur.words = wc;
    if(!cur.seconds) cur.seconds = wc ? Math.round(wc/(wpm/60)) : 0;
    cur.blocks = blocks;
  }
  let inHeader=true;
  for(let i=0;i<lines.length;i++){
    const line=lines[i];
    const sm=matchSlide(line);
    if(sm){
      inHeader=false; flush();
      cur={no:sm.no, headline:sm.headline, stage:sm.stage,
           kind:"normal", budget:null, actual:null, seconds:null, blocks:[]};
      slides.push(cur); body=[]; continue;
    }
    if(inHeader){
      const dt=/^#\s+PRESENTER'?S?\s+SPEECH\s*--\s*(.+)$/i.exec(line);
      if(dt) deck=dt[1].trim();
      line.split("|").forEach(pc=>{ const kv=/^([A-Z_]+):\s*(.+)$/.exec(pc.trim());
        if(kv && kv[1].toUpperCase()==="SPOKEN_RATE_WPM"){ const n=parseInt(kv[2].replace(/[^0-9]/g,"")); if(n) wpm=n; } });
      continue;
    }
    if(cur && line.trim().startsWith(">")){
      const mm=metaRe.exec(line.trim());
      if(mm){ if(mm[1]&&!cur.stage)cur.stage=mm[1]; if(mm[2])cur.kind=mm[2];
        if(mm[3])cur.budget=+mm[3]; if(mm[4])cur.actual=+mm[4]; if(mm[5])cur.seconds=+mm[5]; }
      continue;
    }
    if(line.trim()==="---") continue;
    if(cur) body.push(line);
  }
  flush();
  // Fallback: no slide markers — split on "---" or paragraph breaks
  if(!slides.length){
    const secs = md.split(/\n---\n/);
    const chunks = secs.length > 1 ? secs : md.split(/\n\s*\n\s*\n/);
    chunks.forEach((chunk,idx)=>{
      chunk=chunk.trim(); if(!chunk) return;
      const firstLine=chunk.split("\n").find(l=>l.trim())||"";
      const hl=firstLine.replace(/^#+\s*/,"").trim().slice(0,80)||"Section "+(idx+1);
      const wc=wordCount(chunk);
      slides.push({no:idx+1, headline:hl, stage:"", kind:"normal",
        budget:null, actual:null, seconds:wc?Math.round(wc/(wpm/60)):0,
        words:wc, blocks:[{type:"body",text:chunk.replace(/\s+/g," ").trim()}]});
    });
  }
  return {deck_title:deck, wpm, slides};
}

// ---- state
let DATA = JSON.parse(document.getElementById("speech-data").textContent || "{}");
let TOKENS = JSON.parse((document.getElementById("token-data")||{}).textContent || "[]");
let slides = DATA.slides || [];
let WPM = DATA.wpm || DEFAULT_WPM;
let current = 0;            // index of the current slide
let playing = false;
let rafId = null, lastTs = 0;
let slideStart = performance.now();   // when the current slide became current
// MODE: "manual" (no engine motion) | "auto" (fixed-speed RAF, default+fallback)
//       | "voice" (voice-tracking). Legacy "traditional"/"spoken" migrate on boot.
let MODE = "auto";
let voiceTargetTop = 0;    // VOICE: scroll target the RAF tween chases (set by the aligner)
const stage = document.getElementById("stage");
const scrollEl = document.getElementById("scroll");

function esc(t){ const d=document.createElement("div"); d.textContent=t; return d.innerHTML; }
function ownerize(html){
  return html.replace(OWNER_RE, m=>'<span class="owner">'+esc(m)+'</span>');
}

// ---- Objective 3 normalization (mirror of the Python _norm_token / _FILLER set)
const FILLER = new Set(["um","uh","erm","uhh","umm","er","ah","like","you","know"]);
const NUMW = {"0":"zero","1":"one","2":"two","3":"three","4":"four","5":"five",
  "6":"six","7":"seven","8":"eight","9":"nine","10":"ten"};
function normTok(raw){
  let t=raw.toLowerCase().replace(/[^a-z0-9']/g,"").replace(/^'+|'+$/g,"");
  if(!t) return "";
  if(NUMW[t]) t=NUMW[t];
  return t;
}
// Build {slide}:{block}:{wi} -> global token index from TOKENS (built server-side
// AND rebuilt at runtime for Load/Paste). Lets render wrap each surface word in a
// span carrying its global token index so the aligner can highlight it.
let TOK_INDEX = {};
let SLIDE_FIRST_TOKEN = [];   // slide idx -> global index of its first token (voice resync)
function rebuildTokenIndex(){
  TOK_INDEX = {};
  SLIDE_FIRST_TOKEN = [];
  for(let gi=0; gi<TOKENS.length; gi++){
    const t=TOKENS[gi];
    TOK_INDEX[t.slide+":"+t.block+":"+t.wi]=gi;
    if(SLIDE_FIRST_TOKEN[t.slide]===undefined) SLIDE_FIRST_TOKEN[t.slide]=gi;
  }
}
// Tokenize the loaded slides[] the same way Python does, for runtime Load/Paste.
function buildTokensFromSlides(){
  const out=[];
  slides.forEach((s,si)=>{
    (s.blocks||[]).forEach((b,bi)=>{
      if(b.type!=="body") return;
      const words=(b.text||"").trim().split(/\s+/);
      let wi=0;
      words.forEach(w=>{
        if(!w) return;
        const nt=normTok(w);
        if(nt && !FILLER.has(nt)) out.push({t:nt,slide:si,block:bi,wi:wi,w:w});
        wi++;
      });
    });
  });
  return out;
}
// Render one body block: wrap each surface word in a span; tokenized words get a
// data-ti = global token index so highlightUpTo()/highlightCur() can style them.
function renderBody(text, slideIdx, blockIdx){
  const words=(text||"").trim().split(/\s+/);
  let wi=0, html="";
  words.forEach((w,k)=>{
    if(!w) return;
    const nt=normTok(w);
    const tokenized = nt && !FILLER.has(nt);
    const ti = tokenized ? TOK_INDEX[slideIdx+":"+blockIdx+":"+wi] : undefined;
    const surface = ownerize(esc(w));
    if(ti!==undefined) html+='<span class="tok" data-ti="'+ti+'">'+surface+'</span>';
    else html+='<span class="tok">'+surface+'</span>';
    html+= (k<words.length-1?" ":"");
    wi++;
  });
  return html;
}

function render(){
  document.getElementById("decktitle").textContent = DATA.deck_title ? "  /  "+DATA.deck_title : "";
  scrollEl.innerHTML = "";
  const rail = document.getElementById("rail"); rail.innerHTML = "";
  slides.forEach((s, idx)=>{
    const sec = document.createElement("section");
    sec.className = "slide"; sec.id = "slide-"+idx; sec.dataset.idx = idx;
    const lab = document.createElement("div"); lab.className="label";
    const stageTxt = s.stage ? " &nbsp; "+esc(s.stage.replace(/_/g," ")) : "";
    lab.innerHTML = '<span class="num">Slide '+s.no+'</span> &nbsp; '+esc(s.headline)+stageTxt;
    sec.appendChild(lab);
    (s.blocks||[]).forEach((b,bi)=>{
      const p=document.createElement("p");
      if(b.type==="cue"){ p.className="cue"; p.textContent=b.text; }
      else { p.innerHTML = renderBody(b.text, idx, bi); }
      sec.appendChild(p);
    });
    scrollEl.appendChild(sec);

    const item=document.createElement("div"); item.className="item"; item.dataset.idx=idx;
    item.innerHTML='<span class="n">Slide '+s.no+'</span><span class="h">'+esc(s.headline)+'</span>';
    item.onclick=()=>goTo(idx, true);
    rail.appendChild(item);
  });
  _tokSpans = null;  // DOM rebuilt; drop the cached token-span list
  applyFont(); updateActive(); updatePos();
}

function slideEls(){ return Array.from(scrollEl.querySelectorAll(".slide")); }
function railEls(){ return Array.from(document.querySelectorAll("#rail .item")); }

function goTo(idx, smooth){
  idx = Math.max(0, Math.min(slides.length-1, idx));
  current = idx;
  const el = document.getElementById("slide-"+idx);
  const top = el ? el.offsetTop - stage.clientHeight*0.12 : 0;
  if(el) stage.scrollTo({top: top, behavior: smooth?"smooth":"auto"});
  slideStart = performance.now();
  // VOICE resync: a manual jump (rail / arrows / clicker) RE-SEEDS the aligner
  // at the target slide's first token and moves the tween target with the jump,
  // so voice tracking resumes from HERE instead of dragging the view back.
  if(MODE==="voice"){
    const seed = SLIDE_FIRST_TOKEN[idx];
    if(seed!==undefined){ cursor = seed; interimEnd = seed; renderHighlight(); }
    voiceTargetTop = Math.max(0, top);
  }
  updateActive(); updatePos();
}

function detectCurrentFromScroll(){
  // the slide whose top is closest above the 18% line of the viewport
  const line = stage.scrollTop + stage.clientHeight*0.18;
  let idx=0;
  slideEls().forEach((el,i)=>{ if(el.offsetTop <= line) idx=i; });
  if(idx!==current){ current=idx; slideStart=performance.now(); updateActive(); }
  updatePos();
}

function updateActive(){
  slideEls().forEach((el,i)=> el.classList.toggle("cur", i===current));
  railEls().forEach((el,i)=>{
    el.classList.toggle("active", i===current);
    if(i===current) el.scrollIntoView({block:"nearest"});
  });
}

function updatePos(){
  document.getElementById("pos").textContent = "Slide "+(slides.length?current+1:0)+" of "+slides.length;
  const max = stage.scrollHeight - stage.clientHeight;
  const pct = max>0 ? (stage.scrollTop/max*100) : 0;
  document.getElementById("prog").style.width = pct.toFixed(1)+"%";
}

function fmt(s){ s=Math.max(0,Math.round(s)); const m=Math.floor(s/60); const r=s%60;
  return (m<10?"0":"")+m+":"+(r<10?"0":"")+r; }

function tickCountdown(){
  const cnt = document.getElementById("count");
  const s = slides[current];
  if(!s){ cnt.textContent="00:00"; return; }
  const budget = s.seconds || 0;
  const elapsed = (performance.now()-slideStart)/1000;
  const remain = budget - elapsed;
  cnt.textContent = (remain<0?"-":"")+fmt(Math.abs(remain));
  cnt.classList.toggle("over", remain < 0);
  cnt.classList.toggle("warn", remain >= 0 && budget>0 && remain < budget*0.2);
}

// ---- auto-scroll engine (Objective 1: sub-pixel accumulator + dt clamp + curved range)
const SPEED_FLOOR = 18;   // px/s at slider minimum: readably slow but VISIBLY moving
const SPEED_TOP   = 240;  // px/s at slider maximum
const DT_MAX      = 0.05; // seconds; clamp a stalled/GC/refocus frame to ~3 frames @60fps
let scrollAccum   = 0;    // fractional sub-pixel scroll carry
function speedPxPerSec(){
  const v = +document.getElementById("speed").value / 100; // 0..1
  // Mild ease (v^1.3) so the low half of the slider has fine control while the
  // floor stays above the visible-motion threshold and the top reaches ~240px/s.
  return SPEED_FLOOR + Math.pow(v, 1.3) * (SPEED_TOP - SPEED_FLOOR);
}
// Reset the timestamp + sub-pixel carry on EVERY transition into motion so a
// stale lastTs can never multiply into a jump. Called on play/speed/mode change.
function resetScrollClock(){ lastTs = 0; scrollAccum = 0; }
function loop(ts){
  if(!playing){ rafId=null; return; }
  if(!lastTs) lastTs=ts;
  let dt=(ts-lastTs)/1000; lastTs=ts;
  dt = Math.min(dt, DT_MAX);            // clamp: a stalled/GC/refocus frame can never jump
  if(dt < 0) dt = 0;
  if(MODE==="voice"){
    // VOICE: tween toward the voice-derived target instead of constant speed.
    tweenTowardVoiceTarget(dt);
  } else if(MODE==="auto"){
    // AUTO: accumulate sub-pixel scroll, write only the integer delta,
    // carry the remainder — smooth even at the slow floor at any frame rate.
    scrollAccum += speedPxPerSec()*dt;
    const whole = Math.trunc(scrollAccum);
    if(whole !== 0){ stage.scrollTop += whole; scrollAccum -= whole; }
  }
  // MANUAL: no engine motion (the RAF is not armed in manual mode).
  detectCurrentFromScroll();
  tickCountdown();
  const atEnd = stage.scrollTop >= stage.scrollHeight - stage.clientHeight - 1;
  if(atEnd && MODE==="auto"){ setPlaying(false); }
  else rafId=requestAnimationFrame(loop);
}
function setPlaying(p){
  if(MODE==="manual") p=false;          // manual mode has no engine to play
  playing=p; resetScrollClock();
  const btn = document.getElementById("playBtn");
  // In VOICE mode the control reads Follow/Hold (recognition + highlight keep
  // running on Hold; only the scroll-following freezes).
  btn.textContent = MODE==="voice" ? (p?"Hold":"Follow") : (p?"Pause":"Play");
  btn.classList.toggle("on", p);
  if(MODE==="voice" && !p) micChip("paused","hold");
  if(p && !rafId) rafId=requestAnimationFrame(loop);
}
// SPOKEN smoothing tween: ease the real scrollTop toward the voice-derived
// target so motion stays smooth between recognition events instead of snapping.
// Sub-pixel safe (writes integer deltas, carries the remainder via scrollAccum).
function tweenTowardVoiceTarget(dt){
  const cur = stage.scrollTop;
  const diff = voiceTargetTop - cur;
  if(Math.abs(diff) < 0.5){ scrollAccum = 0; return; }
  // Exponential approach, frame-rate independent; capped so a big jump still eases.
  const k = 1 - Math.pow(0.0001, dt); // ~time-constant smoothing
  scrollAccum += diff * k;
  const whole = Math.trunc(scrollAccum);
  if(whole !== 0){ stage.scrollTop += whole; scrollAccum -= whole; }
}

// ========================================================================
// Objective 3 -- Smart fuzzy sequence aligner (bounded local Levenshtein)
// Maps the spoken token stream onto TOKENS tolerant of paraphrase/skip/
// repeat/ad-lib, confidence-gated, two-tier highlight.
// ========================================================================
let cursor = 0;            // committed position in TOKENS (already-spoken boundary)
let interimEnd = 0;        // furthest token touched by the live interim region
// ADJUSTABLE SENSITIVITY (persisted slider 0..100, default 50): ONE control maps
// to the three aligner tolerances. Low = strict word-for-word (small window,
// tight fuzz — resists false jumps); high = loose paraphrase-friendly (wide
// window, generous fuzz — follows heavy ad-libbing). 50 reproduces the previous
// fixed tuning (WINDOW 28 / BACKTRACK 6 / FUZZ ~0.34).
function sensValue(){
  const el = document.getElementById("sens");
  const v = el ? +el.value : 50;
  return Math.max(0, Math.min(100, isNaN(v)?50:v)) / 100;   // 0..1
}
function alignWindow(){   return Math.round(16 + sensValue()*32); }  // 16..48, 50 -> 32
function alignBacktrack(){ return Math.round(4  + sensValue()*8);  } // 4..12, 50 -> 8
function alignFuzz(){     return 0.20 + sensValue()*0.28; }          // 0.20..0.48, 50 -> 0.34

// Normalized Levenshtein on two short tokens (0 = identical, 1 = totally different).
function tokDist(a,b){
  if(a===b) return 0;
  const m=a.length, n=b.length;
  if(!m||!n) return 1;
  let prev=new Array(n+1), cur=new Array(n+1);
  for(let j=0;j<=n;j++) prev[j]=j;
  for(let i=1;i<=m;i++){
    cur[0]=i;
    for(let j=1;j<=n;j++){
      const cost=a[i-1]===b[j-1]?0:1;
      cur[j]=Math.min(prev[j]+1, cur[j-1]+1, prev[j-1]+cost);
    }
    [prev,cur]=[cur,prev];
  }
  return prev[n]/Math.max(m,n);
}
// fuzz is read ONCE per alignSpoken call (not per comparison) — the aligner's
// inner loop runs heard×window comparisons per recognition event, and a DOM
// read per comparison would waste ~thousands of getElementById calls an event.
function tokEq(a,b,fz){ return tokDist(a,b) <= (fz!==undefined ? fz : alignFuzz()); }

// Feed a chunk of recognized words. `commit` = true for final results (advance the
// committed cursor), false for interim (drives the current/interim highlight only).
function alignSpoken(text, commit){
  if(!TOKENS.length) return;
  const heard = text.split(/\s+/).map(normTok).filter(w=>w && !FILLER.has(w));
  if(!heard.length) return;
  // ANCHOR-THEN-BAND alignment, starting at [cursor-BACKTRACK]:
  //  * The FIRST match in an utterance may search the full sensitivity window W
  //    ahead (re-acquisition: tolerates a skipped phrase/paragraph or a stretch
  //    of ad-libs since the last event).
  //  * Once anchored, each subsequent heard word only searches a NARROW forward
  //    band (BAND tokens). The band slides with the matches, so one long final
  //    utterance can advance the full distance actually spoken — but a stray
  //    common-word match can no longer leapfrog half the deck (the greedy
  //    wide-window cascade measured cursor->deck-end on a 65-word final; the
  //    narrow band kills that failure mode while a false +BAND overshoot
  //    self-corrects as later words fail to match on the false path).
  //  * Unmatched heard words = ad-libs/insertions: absorbed, position held.
  const W = alignWindow();
  const BAND = Math.round(3 + sensValue()*7);   // 3..10 tokens, sensitivity-scaled
  const FZ = alignFuzz();
  const lo = Math.max(0, cursor - alignBacktrack());
  let si = lo, matched = 0, lastMatch = -1, anchored = false;
  for(let hk=0; hk<heard.length; hk++){
    // search forward for this heard word: wide until anchored, narrow after
    let found=-1;
    const hi = Math.min(TOKENS.length, si + (anchored ? BAND : W));
    for(let p=si; p<hi; p++){
      if(tokEq(heard[hk], TOKENS[p].t, FZ)){ found=p; break; }
    }
    if(found>=0){ matched++; lastMatch=found; si=found+1; anchored=true; }
    // unmatched heard word = ad-lib/insertion: absorb it, keep si put.
  }
  // Confidence gate: need >=2 matched words (or >=1 when only 1-2 heard) to move,
  // and an actual forward landing. Otherwise hold the last good position.
  const need = heard.length<=2 ? 1 : 2;
  if(matched < need || lastMatch < 0){ return; }
  const target = lastMatch + 1; // committed boundary sits just past the last spoken word
  if(commit){
    if(target > cursor){ cursor = target; }     // forward only; never run backward off garbage
    interimEnd = cursor;
    renderHighlight();
    anchorToToken(Math.max(0, cursor-1));
  } else {
    interimEnd = Math.max(cursor, target);
    renderHighlight();
    anchorToToken(Math.max(0, interimEnd-1));
  }
}

// Two-tier highlight: tokens < cursor = spoken (dim/strike); cursor..interimEnd = current.
let _tokSpans = null;
function tokSpans(){
  if(!_tokSpans) _tokSpans = scrollEl.querySelectorAll(".tok[data-ti]");
  return _tokSpans;
}
function renderHighlight(){
  const spans = tokSpans();
  spans.forEach(sp=>{
    const ti=+sp.dataset.ti;
    sp.classList.toggle("spoken", ti < cursor);
    sp.classList.toggle("cur", ti >= cursor && ti <= interimEnd);
  });
}
// Set the voice-derived scroll target so the current token sits in the upper-third
// reading zone; the RAF tween (tweenTowardVoiceTarget) eases scrollTop toward it.
function anchorToToken(ti){
  const tok = TOKENS[Math.min(ti, TOKENS.length-1)];
  if(!tok) return;
  const slideEl = document.getElementById("slide-"+tok.slide);
  if(!slideEl) return;
  const span = scrollEl.querySelector('.tok[data-ti="'+ti+'"]') || slideEl;
  const rectTop = span.offsetTop;  // offset within scrollEl
  voiceTargetTop = Math.max(0, rectTop - stage.clientHeight*0.30);
  // keep slide tracking + countdown honest
  if(tok.slide !== current){ current=tok.slide; slideStart=performance.now(); updateActive(); }
  updatePos();
}
function resetAligner(){ cursor=0; interimEnd=0; _tokSpans=null; renderHighlight(); }

// ========================================================================
// Web Speech API recognizer (VOICE mode) + the three-way mode switch
// ========================================================================
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const SPEECH_SUPPORTED = !!SR;
let rec = null, shouldListen = false;
let recFailures = 0;          // consecutive HARD recognition failures
let lastRecEvent = 0;         // ts of the last onstart/onresult (watchdog input)
let restartTimer = null, watchdogTimer = null;
const REC_MAX_FAILURES = 3;   // hard failures before falling back to AUTO
const REC_WATCHDOG_MS  = 15000; // no events for this long while listening => restart

function micChip(state, txt){
  const c=document.getElementById("micChip");
  c.className = "show "+state;
  c.querySelector(".txt").textContent = txt;
}
function showNotice(msg, ms){
  const n=document.getElementById("notice");
  n.textContent=msg; n.classList.add("show");
  clearTimeout(n._t); n._t=setTimeout(()=>n.classList.remove("show"), ms||5000);
}

function makeRecognizer(){
  const r = new SR();
  r.lang = (navigator.language && navigator.language.slice(0,2)==="en") ? navigator.language : "en-US";
  r.continuous = true; r.interimResults = true;
  r.onstart = ()=>{ lastRecEvent = Date.now(); micChip("listening","listening"); };
  r.onresult = e=>{
    lastRecEvent = Date.now(); recFailures = 0;
    let interim="", final="";
    for(let i=e.resultIndex; i<e.results.length; i++){
      const res=e.results[i];
      if(res.isFinal) final += res[0].transcript+" ";
      else interim += res[0].transcript+" ";
    }
    if(final.trim()){ alignSpoken(final, true); micChip("heard","heard"); }
    if(interim.trim()){ alignSpoken(interim, false); micChip("listening","listening"); }
  };
  r.onerror = e=>{
    if(e.error==="not-allowed" || e.error==="service-not-allowed"){
      micChip("err","mic blocked");
      showNotice("Microphone unavailable. Switched to Auto (fixed-speed) mode. Scroll by hand or press Play.");
      setMode("auto", true);
    } else if(e.error==="no-speech" || e.error==="aborted"){
      // benign; re-arm happens in onend
    } else {
      // network / audio-capture / unknown: count it; repeated hard failures
      // mean the speech service is unusable — fall back rather than spin.
      recFailures++;
      micChip("err", e.error||"error");
      if(recFailures >= REC_MAX_FAILURES){
        showNotice("Voice tracking keeps failing ("+(e.error||"error")+"). Switched to Auto mode.");
        setMode("auto", true);
      }
    }
  };
  r.onend = ()=>{
    // Chrome fires onend after ~7s silence even with continuous=true. Re-arm on
    // a short DEFERRED restart (an immediate rec.start() inside onend can throw
    // InvalidStateError and silently kill listening); recreate the recognizer
    // object if start() throws anyway.
    if(shouldListen) scheduleRestart(250);
    else micChip("paused","paused");
  };
  return r;
}
function scheduleRestart(ms){
  clearTimeout(restartTimer);
  restartTimer = setTimeout(()=>{
    if(!shouldListen) return;
    micChip("listening","re-arming");
    try { rec.start(); }
    catch(_){
      try { rec = makeRecognizer(); rec.start(); }
      catch(err2){
        recFailures++;
        if(recFailures >= REC_MAX_FAILURES){
          showNotice("Voice tracking could not restart. Switched to Auto mode.");
          setMode("auto", true);
        } else scheduleRestart(1000);
      }
    }
  }, ms||250);
}
function startRecognition(){
  if(!SPEECH_SUPPORTED) return false;
  try {
    rec = makeRecognizer();
    shouldListen = true; recFailures = 0; lastRecEvent = Date.now();
    rec.start();
    // Watchdog: a recognition session can die with NO error and NO onend (seen
    // after long tab-background stretches). If we are supposed to be listening
    // but have heard no events for REC_WATCHDOG_MS, force a restart.
    clearInterval(watchdogTimer);
    watchdogTimer = setInterval(()=>{
      if(shouldListen && Date.now()-lastRecEvent > REC_WATCHDOG_MS){
        lastRecEvent = Date.now();
        try{ rec.stop(); }catch(_){ scheduleRestart(100); }
      }
    }, 5000);
    return true;
  } catch(err){
    showNotice("Voice mode could not start. Using Auto mode.");
    setMode("auto", true);
    return false;
  }
}
function stopRecognition(){
  shouldListen=false;
  clearTimeout(restartTimer); clearInterval(watchdogTimer);
  if(rec){ try{ rec.stop(); }catch(_){} rec=null; }
  micChip("paused","off");
}

// Three-way mode switch. silent=true skips the privacy notice (auto-fallback).
function updateModeButtons(){
  const map = {manual:"modeManualBtn", auto:"modeAutoBtn", voice:"modeVoiceBtn"};
  Object.keys(map).forEach(m=>{
    document.getElementById(map[m]).classList.toggle("on", MODE===m);
  });
}
function setMode(mode, silent){
  mode = migrateMode(mode) || "auto";
  if(mode==="voice" && !SPEECH_SUPPORTED) mode="auto";
  MODE = mode;
  localStorage.setItem(MODE_KEY, mode);
  updateModeButtons();
  // Speed applies to AUTO; Sensitivity applies to VOICE; Play is idle in MANUAL.
  document.getElementById("speedCtl").hidden = (mode==="voice");
  document.getElementById("sensCtl").hidden = (mode!=="voice");
  document.getElementById("playBtn").hidden = (mode==="manual");
  resetScrollClock();
  if(mode==="voice"){
    // Seed the aligner at the CURRENT slide (voice can start mid-deck), and
    // start the tween from the current scroll position.
    const seed = SLIDE_FIRST_TOKEN[current];
    cursor = (seed!==undefined) ? seed : 0;
    interimEnd = cursor; _tokSpans = null; renderHighlight();
    voiceTargetTop = stage.scrollTop;
    if(!silent) showNotice("Voice mode sends audio to your browser's speech service (cloud-based in Chrome/Edge). Choose Manual or Auto for sensitive content.", 7000);
    document.getElementById("micChip").classList.add("show");
    startRecognition();
    setPlaying(true);   // RAF runs as the smoothing tween toward the voice target
  } else {
    stopRecognition();
    document.getElementById("micChip").classList.remove("show");
    setPlaying(false);
  }
}

// ---- font / mirror / theme
function applyFont(){
  const px = +(localStorage.getItem(FONT_KEY)||48);
  scrollEl.style.fontSize = px+"px";
}
function bumpFont(d){
  let px=+(localStorage.getItem(FONT_KEY)||48); px=Math.max(20,Math.min(96,px+d));
  localStorage.setItem(FONT_KEY,px); applyFont();
}
function applyMirror(){
  const on = localStorage.getItem(MIRROR_KEY)==="1";
  stage.classList.toggle("mirror", on);
  document.getElementById("mirrorBtn").classList.toggle("on", on);
}
function applyVmirror(){
  const on = localStorage.getItem(VMIRROR_KEY)==="1";
  stage.classList.toggle("vmirror", on);
  document.getElementById("vmirrorBtn").classList.toggle("on", on);
}
function applyGuide(){
  const on = localStorage.getItem(GUIDE_KEY)==="1";
  stage.classList.toggle("guide", on);
  document.getElementById("guideBtn").classList.toggle("on", on);
}
function applyTheme(){
  const light = localStorage.getItem(THEME_KEY)==="light";
  document.documentElement.classList.toggle("light", light);
  document.getElementById("themeBtn").textContent = light?"Dark":"Light";
}

// ---- wiring
document.getElementById("modeManualBtn").onclick=()=>setMode("manual");
document.getElementById("modeAutoBtn").onclick=()=>setMode("auto");
document.getElementById("modeVoiceBtn").onclick=()=>setMode("voice");
document.getElementById("sens").oninput=e=>{ localStorage.setItem(SENS_KEY, e.target.value); };
document.getElementById("vmirrorBtn").onclick=()=>{ localStorage.setItem(VMIRROR_KEY, localStorage.getItem(VMIRROR_KEY)==="1"?"0":"1"); applyVmirror(); };
document.getElementById("guideBtn").onclick=()=>{ localStorage.setItem(GUIDE_KEY, localStorage.getItem(GUIDE_KEY)==="1"?"0":"1"); applyGuide(); };
document.getElementById("playBtn").onclick=()=>setPlaying(!playing);
document.getElementById("spdUp").onclick=()=>{ const s=document.getElementById("speed"); s.value=Math.min(100,+s.value+5); localStorage.setItem(SPEED_KEY,s.value); resetScrollClock(); };
document.getElementById("spdDown").onclick=()=>{ const s=document.getElementById("speed"); s.value=Math.max(0,+s.value-5); localStorage.setItem(SPEED_KEY,s.value); resetScrollClock(); };
document.getElementById("speed").oninput=e=>{ localStorage.setItem(SPEED_KEY,e.target.value); resetScrollClock(); };
document.getElementById("fontUp").onclick=()=>bumpFont(4);
document.getElementById("fontDown").onclick=()=>bumpFont(-4);
document.getElementById("prevBtn").onclick=()=>goTo(current-1,true);
document.getElementById("nextBtn").onclick=()=>goTo(current+1,true);
document.getElementById("mirrorBtn").onclick=()=>{ localStorage.setItem(MIRROR_KEY, localStorage.getItem(MIRROR_KEY)==="1"?"0":"1"); applyMirror(); };
document.getElementById("themeBtn").onclick=()=>{ localStorage.setItem(THEME_KEY, localStorage.getItem(THEME_KEY)==="light"?"dark":"light"); applyTheme(); };
document.getElementById("fsBtn").onclick=()=>{ if(!document.fullscreenElement) document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen(); else document.exitFullscreen&&document.exitFullscreen(); };
stage.addEventListener("scroll", ()=>{ if(!playing){ detectCurrentFromScroll(); tickCountdown(); } });

document.addEventListener("keydown", e=>{
  if(e.target.tagName==="TEXTAREA"||e.target.tagName==="INPUT") return;
  // Presenter-clicker keys: PageDown/PageUp/period = next/prev; B = pause/blank toggle.
  // Space is mode-aware: MANUAL = next slide (clicker-style page flip);
  // AUTO = play/pause; VOICE = follow/hold.
  if(e.code==="Space"){ e.preventDefault(); if(MODE==="manual") goTo(current+1,true); else setPlaying(!playing); }
  else if(e.code==="ArrowRight"||e.code==="ArrowDown"||e.code==="PageDown"){ e.preventDefault(); goTo(current+1,true); }
  else if(e.code==="ArrowLeft"||e.code==="ArrowUp"||e.code==="PageUp"){ e.preventDefault(); goTo(current-1,true); }
  else if(e.key==="b"||e.key==="B"){ e.preventDefault(); setPlaying(!playing); }   // clicker "blank/pause" key
  else if(e.key==="."){ e.preventDefault(); goTo(current+1,true); }                  // some clickers emit "."
  else if(e.key==="+"||e.key==="="){ bumpFont(4); }
  else if(e.key==="-"){ bumpFont(-4); }
  else if(e.key==="m"||e.key==="M"){ document.getElementById("mirrorBtn").click(); }
  else if(e.key==="v"||e.key==="V"){ document.getElementById("vmirrorBtn").click(); }
  else if(e.key==="g"||e.key==="G"){ document.getElementById("guideBtn").click(); }
  else if(e.key==="f"||e.key==="F"){ document.getElementById("fsBtn").click(); }
});

// ---- loader (Load .md / Paste)
const loader=document.getElementById("loader");
document.getElementById("loadBtn").onclick=()=>loader.style.display="flex";
document.getElementById("closeLoader").onclick=()=>loader.style.display="none";
document.getElementById("fileInput").onchange=e=>{
  const f=e.target.files[0]; if(!f) return;
  const r=new FileReader(); r.onload=()=>{ ingest(r.result); loader.style.display="none"; }; r.readAsText(f);
};
document.getElementById("parsePaste").onclick=()=>{
  const t=document.getElementById("pasteArea").value; if(t.trim()){ ingest(t); loader.style.display="none"; }
};
function ingest(md){
  const parsed=parseMarkdown(md);
  if(parsed.slides.length){
    DATA=parsed; slides=parsed.slides; WPM=parsed.wpm; current=0;
    TOKENS=buildTokensFromSlides(); rebuildTokenIndex();  // re-tokenize for VOICE highlight
    resetAligner();
    if(MODE==="voice") setMode("auto", true);             // restart cleanly in a fixed mode on new file
    render(); goTo(0,false); setPlaying(false);
  }
  else alert("No slides could be parsed. The file may be empty. Accepted formats: '## Slide N -- Headline', '[Slide N] Headline', 'Slide N: Headline', or use '---' separators for a paragraph fallback.");
}

// ---- boot
(function boot(){
  if(localStorage.getItem(SPEED_KEY)) document.getElementById("speed").value=localStorage.getItem(SPEED_KEY);
  else {
    // seed speed from WPM: faster speech => faster default scroll
    const v=Math.max(10,Math.min(70, Math.round((WPM-90)/2)+25));
    document.getElementById("speed").value=v;
  }
  if(localStorage.getItem(SENS_KEY)) document.getElementById("sens").value=localStorage.getItem(SENS_KEY);
  applyMirror(); applyVmirror(); applyGuide(); applyTheme();
  if(!localStorage.getItem(FONT_KEY)) localStorage.setItem(FONT_KEY, 48);
  rebuildTokenIndex();  // map {slide,block,wi}->token index before first render
  // Hide VOICE where unsupported (e.g. Firefox): Manual/Auto only, no dead state.
  if(!SPEECH_SUPPORTED){
    document.getElementById("modeVoiceBtn").hidden = true;
    document.getElementById("micChip").classList.remove("show");
  }
  if(!slides.length){ render(); loader.style.display="flex"; }
  else { render(); goTo(0,false); }
  // Restore the persisted mode (legacy "traditional"/"spoken" values migrate);
  // VOICE only auto-resumes when supported. Default: AUTO.
  const savedMode = migrateMode(localStorage.getItem(MODE_KEY));
  if(savedMode==="voice" && SPEECH_SUPPORTED) setMode("voice");
  else setMode(savedMode || "auto", true);
  setInterval(()=>{ if(!playing) tickCountdown(); }, 250);
})();
</script>
</body>
</html>
"""


def build_html(data, brand_name, wpm, accent_hex=HOUSE_ACCENT):
    payload = json.dumps(data, ensure_ascii=False)
    # guard against the JSON closing the inline <script> early
    payload = payload.replace("</", "<\\/")
    tokens = tokenize_script(data)
    token_payload = json.dumps(tokens, ensure_ascii=False).replace("</", "<\\/")
    html = HTML_TEMPLATE
    html = html.replace("__SPEECH_JSON__", payload)
    html = html.replace("__TOKENS_JSON__", token_payload)
    html = html.replace("__BRAND_NAME__", (brand_name or "Presenter's Speech").replace("&", "&amp;").replace("<", "&lt;"))
    html = html.replace("__WPM__", str(int(wpm)))
    html = html.replace("__ACCENT_HEX__", accent_hex or HOUSE_ACCENT)
    return html


# Built-in stub speech in the exact PRESENTERS-SPEECH.md contract.
SAMPLE_SPEECH_MD = """# PRESENTER'S SPEECH -- From Overlooked to Overbooked: The 90-Day Authority Webinar
DURATION_MIN: 60 | SPOKEN_RATE_WPM: 130
PAUSE_BUDGET_SEC: 30 | NET_SPOKEN_SEC: 3570
TARGET_WORDS: 7735 | ACTUAL_WORDS: 491 | RATIO: 6.3%
WITHIN_10PCT_BAND: false
BUILD_AT: 2026-06-17T00:00:00+00:00

## Slide 1 -- Welcome  (WELCOME)
> STAGE: WELCOME  KIND: normal  BUDGET: 90w  ACTUAL: 87w  SECONDS: 40s

Hello and welcome, everybody.

[PAUSE]

Congratulations on taking the first step just by being here. I mean that. You could be doing a hundred other things right now, and instead you showed up for your future.

So before we go one inch further, do me a favor. Drop in the chat where you are watching from today. Go ahead, I will wait.

[BREATHE]

Quick housekeeping. Stay to the very end, because what I save for the last ten minutes is the part nobody else will give you for free.

---

## Slide 2 -- Is this you?  (WHO_FOR)
> STAGE: WHO_FOR  KIND: normal  BUDGET: 60w  ACTUAL: 58w  SECONDS: 27s

Let me tell you exactly who this is for.

This is for the person who is genuinely good at what they do, and is quietly furious that the world has not noticed yet. If you are nodding right now, you are in the right room. (PAUSE 2 seconds) And if you are just curious, that is fine too. Stay. Steal everything.

---

## Slide 3 -- I was exactly where you are  (CREDIBILITY)
> STAGE: CREDIBILITY  KIND: owner_prompt  BUDGET: 40w  ACTUAL: 35w  SECONDS: 16s

Five years ago I was the best-kept secret in my whole industry. Talented, broke, and invisible.

(OWNER: say the one true detail about your lowest moment here, in your own words.)

[PAUSE]

And then one Tuesday something broke open for me, and I want to give you that exact moment today.

---

## Slide 4 -- The big promise  (BIG_PROMISE)
> STAGE: BIG_PROMISE  KIND: hook  BUDGET: 55w  ACTUAL: 54w  SECONDS: 25s

Here is the one thing I need you to believe before you leave today.

It is not that you need more talent. It is not that you need more time. (PAUSE 2 seconds) It is that you are one decision away from being seen.

Say it with me. You are not behind. You are one decision away.

---

## Slide 5 -- One decision away  (CLOSE)
> STAGE: CLOSE  KIND: hook  BUDGET: 35w  ACTUAL: 33w  SECONDS: 15s

So I will leave you the way we started.

(PAUSE 2 seconds)

You are not behind. You are one decision away. Make it today. I will see you on the inside.

---
"""


def main():
    ap = argparse.ArgumentParser(description="Presenter's Speech teleprompter HTML generator (no AI)")
    ap.add_argument("--speech", help="path to the finished PRESENTERS-SPEECH.md")
    ap.add_argument("--out", default="presenter-teleprompter.html", help="output HTML path")
    ap.add_argument("--intake", help="path to intake.json (for brand/company name)")
    ap.add_argument("--design-system",
                    help="path to design_system.json (for the locked brand accent color); "
                         "falls back to house amber #f2b134 when absent")
    ap.add_argument("--sample", action="store_true", help="build from the built-in stub speech")
    ap.add_argument("--emit-sample-speech", metavar="PATH",
                    help="write the built-in stub PRESENTERS-SPEECH.md to PATH and exit")
    args = ap.parse_args()

    if args.emit_sample_speech:
        Path(args.emit_sample_speech).write_text(SAMPLE_SPEECH_MD, encoding="utf-8")
        print(f"Wrote sample speech to {args.emit_sample_speech}")
        return

    if args.sample:
        md = SAMPLE_SPEECH_MD
    elif args.speech:
        md = Path(args.speech).read_text()
    else:
        ap.error("provide --speech PATH or --sample")

    data = parse_speech(md)
    if not data["slides"]:
        print(
            "FATAL: no slides could be parsed from the speech file. The file appears\n"
            "to be empty or contains no recognizable content.\n"
            "Accepted slide header formats:\n"
            "  ## Slide N -- Headline  (STAGE)   ← canonical\n"
            "  [Slide N] Headline                 ← bracket form\n"
            "  Slide N: Headline                  ← bare with colon\n"
            "  Slide N -- Headline                ← bare with dash\n"
            "  Slide N                            ← bare number only\n"
            "Or separate sections with '---' horizontal rules for the paragraph fallback.",
            file=sys.stderr,
        )
        sys.exit(2)
    brand = read_brand_name(args.intake)
    accent = read_design_system_accent(args.design_system)
    html = build_html(data, brand, data["wpm"], accent)
    # AF-BUNDLE-COMPLETE: refuse to emit a degenerate/non-self-contained file.
    # Failing loud here means a gated phase invocation halts instead of shipping
    # a junk teleprompter that would later be caught (or missed) at closeout.
    issues = verify_teleprompter_html(html)
    if issues:
        print("FATAL: refusing to write an invalid teleprompter "
              "(AF-BUNDLE-COMPLETE floor):", file=sys.stderr)
        for it in issues:
            print(f"  - {it}", file=sys.stderr)
        sys.exit(3)
    Path(args.out).write_text(html, encoding="utf-8")
    written = Path(args.out).stat().st_size
    if written < TELEPROMPTER_MIN_BYTES:
        print(f"FATAL: written teleprompter {args.out} is {written} bytes, below "
              f"the {TELEPROMPTER_MIN_BYTES}-byte minimum (AF-BUNDLE-COMPLETE).",
              file=sys.stderr)
        sys.exit(3)
    print(f"Rendered {args.out}")
    print(f"Slides: {len(data['slides'])}  |  WPM: {data['wpm']}  |  "
          f"brand: {brand or '(none from intake)'}  |  accent: {accent}")
    print(f"HTML size: {len(html):,} bytes (self-contained: inline CSS + JS + speech JSON)")


if __name__ == "__main__":
    main()

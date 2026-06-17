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

FEATURES (the teleprompter, all client-side)
- Pre-loaded speech (inline JSON) + a "Load .md" file picker + a "Paste" fallback.
- Big adjustable font (default ~48px) with +/- controls.
- Scroll-speed slider; default seeded from the speech WPM.
- Play / pause on the scroll (Space).
- Mirror mode (CSS transform: scaleX(-1)) for a beam-splitter rig.
- Progress bar + "Slide N of M".
- A slide RAIL on the left to jump to any slide; current slide is highlighted.
- Manual prev / next slide with the arrow keys, in lockstep with the scroll.
- Per-slide pacing COUNTDOWN from the SECONDS: metadata (turns amber, then red,
  when the presenter runs over that slide's budget).
- Fullscreen toggle.
- Settings persisted to localStorage (font, speed, mirror, theme).
- Dark high-contrast theme (default) with a light toggle.
- Brand / company name in the header, read from intake.json if available.

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
# Slide header, e.g.:  ## Slide 12 -- Management mode  (MANAGEMENT_MODE)
SLIDE_RE = re.compile(
    r"^##\s+Slide\s+(?P<no>\d+)\s*--\s*(?P<headline>.*?)\s*"
    r"(?:\((?P<stage>[^)]*)\))?\s*$"
)
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
    """
    lines = md_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    meta = {}
    deck_title = "Presenter's Speech"
    wpm = default_wpm

    # Pull the header block (everything before the first "## Slide").
    i = 0
    while i < len(lines):
        line = lines[i]
        if SLIDE_RE.match(line):
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
        sm = SLIDE_RE.match(line)
        if sm:
            flush_body()
            cur = {
                "no": int(sm.group("no")),
                "headline": (sm.group("headline") or "").strip(),
                "stage": (sm.group("stage") or "").strip(),
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

    return {
        "deck_title": deck_title,
        "wpm": wpm,
        "meta": meta,
        "slides": slides,
    }


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


# ---------------------------------------------------------------------------
# HTML template. The speech payload is injected as inline JSON at __SPEECH_JSON__,
# the brand name at __BRAND_NAME__, and the default WPM at __WPM__.
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
    --bg: #0b0d12; --fg: #f5f7fa; --muted: #8a93a3; --accent: #f2b134;
    --rail: #141821; --rail-active: #1d2430; --cue: #f2b134; --over: #ff5a5a;
    --ok: #57d977; --warn: #f2b134;
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
</style>
</head>
<body>
<div id="app">
  <header>
    <div class="brand">__BRAND_NAME__<span class="sub" id="decktitle"></span></div>
    <div class="spacer"></div>
    <div class="ctl"><button id="playBtn" title="Space">Play</button></div>
    <div class="ctl">Speed
      <button id="spdDown">-</button>
      <input id="speed" type="range" min="0" max="100" value="35">
      <button id="spdUp">+</button>
    </div>
    <div class="ctl">Font
      <button id="fontDown">A-</button><button id="fontUp">A+</button>
    </div>
    <div class="ctl">
      <button id="mirrorBtn" title="Mirror for beam splitter">Mirror</button>
      <button id="themeBtn">Light</button>
      <button id="fsBtn" title="Fullscreen">Full</button>
      <button id="loadBtn">Load .md</button>
    </div>
  </header>
  <nav id="rail"></nav>
  <main id="stage"><div id="scroll"></div></main>
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
    <textarea id="pasteArea" placeholder="## Slide 1 -- Welcome  (WELCOME)
&gt; STAGE: WELCOME  KIND: normal  BUDGET: 90w  ACTUAL: 88w  SECONDS: 41s

Hello and welcome, everybody. [PAUSE] ..."></textarea>
    <div class="row">
      <button id="parsePaste">Use pasted text</button>
      <button id="closeLoader">Cancel</button>
    </div>
  </div>
</div>

<script id="speech-data" type="application/json">__SPEECH_JSON__</script>
<script>
"use strict";
const DEFAULT_WPM = __WPM__;
const FONT_KEY = "ptp.font", SPEED_KEY = "ptp.speed", MIRROR_KEY = "ptp.mirror", THEME_KEY = "ptp.theme";

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
function parseMarkdown(md){
  const lines = md.replace(/\r\n?/g,"\n").split("\n");
  let wpm = DEFAULT_WPM, deck = "Presenter's Speech";
  const slideRe = /^##\s+Slide\s+(\d+)\s*--\s*(.*?)\s*(?:\(([^)]*)\))?\s*$/;
  const metaRe = /^>\s*(?:STAGE:\s*([A-Z_]+))?\s*(?:KIND:\s*(\w+))?\s*(?:BUDGET:\s*(\d+)\s*w)?\s*(?:ACTUAL:\s*(\d+)\s*w)?\s*(?:SECONDS:\s*(\d+)\s*s)?/i;
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
    const sm=slideRe.exec(line);
    if(sm){
      inHeader=false; flush();
      cur={no:+sm[1], headline:(sm[2]||"").trim(), stage:(sm[3]||"").trim(),
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
  return {deck_title:deck, wpm, slides};
}

// ---- state
let DATA = JSON.parse(document.getElementById("speech-data").textContent || "{}");
let slides = DATA.slides || [];
let WPM = DATA.wpm || DEFAULT_WPM;
let current = 0;            // index of the current slide
let playing = false;
let rafId = null, lastTs = 0;
let slideStart = performance.now();   // when the current slide became current
const stage = document.getElementById("stage");
const scrollEl = document.getElementById("scroll");

function esc(t){ const d=document.createElement("div"); d.textContent=t; return d.innerHTML; }
function ownerize(html){
  return html.replace(OWNER_RE, m=>'<span class="owner">'+esc(m)+'</span>');
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
    (s.blocks||[]).forEach(b=>{
      const p=document.createElement("p");
      if(b.type==="cue"){ p.className="cue"; p.textContent=b.text; }
      else { p.innerHTML = ownerize(esc(b.text)); }
      sec.appendChild(p);
    });
    scrollEl.appendChild(sec);

    const item=document.createElement("div"); item.className="item"; item.dataset.idx=idx;
    item.innerHTML='<span class="n">Slide '+s.no+'</span><span class="h">'+esc(s.headline)+'</span>';
    item.onclick=()=>goTo(idx, true);
    rail.appendChild(item);
  });
  applyFont(); updateActive(); updatePos();
}

function slideEls(){ return Array.from(scrollEl.querySelectorAll(".slide")); }
function railEls(){ return Array.from(document.querySelectorAll("#rail .item")); }

function goTo(idx, smooth){
  idx = Math.max(0, Math.min(slides.length-1, idx));
  current = idx;
  const el = document.getElementById("slide-"+idx);
  if(el) stage.scrollTo({top: el.offsetTop - stage.clientHeight*0.12, behavior: smooth?"smooth":"auto"});
  slideStart = performance.now();
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

// ---- auto-scroll engine
function speedPxPerSec(){
  const v = +document.getElementById("speed").value; // 0..100
  // 8..220 px/s, seeded default tuned so a ~48px line reads near WPM cadence
  return 8 + (v/100)*212;
}
function loop(ts){
  if(!playing){ rafId=null; return; }
  if(!lastTs) lastTs=ts;
  const dt=(ts-lastTs)/1000; lastTs=ts;
  stage.scrollTop += speedPxPerSec()*dt;
  detectCurrentFromScroll();
  tickCountdown();
  const atEnd = stage.scrollTop >= stage.scrollHeight - stage.clientHeight - 1;
  if(atEnd){ setPlaying(false); }
  else rafId=requestAnimationFrame(loop);
}
function setPlaying(p){
  playing=p; lastTs=0;
  document.getElementById("playBtn").textContent = p?"Pause":"Play";
  document.getElementById("playBtn").classList.toggle("on", p);
  if(p && !rafId) rafId=requestAnimationFrame(loop);
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
function applyTheme(){
  const light = localStorage.getItem(THEME_KEY)==="light";
  document.documentElement.classList.toggle("light", light);
  document.getElementById("themeBtn").textContent = light?"Dark":"Light";
}

// ---- wiring
document.getElementById("playBtn").onclick=()=>setPlaying(!playing);
document.getElementById("spdUp").onclick=()=>{ const s=document.getElementById("speed"); s.value=Math.min(100,+s.value+5); localStorage.setItem(SPEED_KEY,s.value); };
document.getElementById("spdDown").onclick=()=>{ const s=document.getElementById("speed"); s.value=Math.max(0,+s.value-5); localStorage.setItem(SPEED_KEY,s.value); };
document.getElementById("speed").oninput=e=>localStorage.setItem(SPEED_KEY,e.target.value);
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
  if(e.code==="Space"){ e.preventDefault(); setPlaying(!playing); }
  else if(e.code==="ArrowRight"||e.code==="ArrowDown"){ e.preventDefault(); goTo(current+1,true); }
  else if(e.code==="ArrowLeft"||e.code==="ArrowUp"){ e.preventDefault(); goTo(current-1,true); }
  else if(e.key==="+"||e.key==="="){ bumpFont(4); }
  else if(e.key==="-"){ bumpFont(-4); }
  else if(e.key==="m"||e.key==="M"){ document.getElementById("mirrorBtn").click(); }
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
  if(parsed.slides.length){ DATA=parsed; slides=parsed.slides; WPM=parsed.wpm; current=0; render(); goTo(0,false); setPlaying(false); }
  else alert("No '## Slide N' headers found. Check the file format.");
}

// ---- boot
(function boot(){
  if(localStorage.getItem(SPEED_KEY)) document.getElementById("speed").value=localStorage.getItem(SPEED_KEY);
  else {
    // seed speed from WPM: faster speech => faster default scroll
    const v=Math.max(10,Math.min(70, Math.round((WPM-90)/2)+25));
    document.getElementById("speed").value=v;
  }
  applyMirror(); applyTheme();
  if(!localStorage.getItem(FONT_KEY)) localStorage.setItem(FONT_KEY, 48);
  if(!slides.length){ render(); loader.style.display="flex"; }
  else { render(); goTo(0,false); }
  setInterval(()=>{ if(!playing) tickCountdown(); }, 250);
})();
</script>
</body>
</html>
"""


def build_html(data, brand_name, wpm):
    payload = json.dumps(data, ensure_ascii=False)
    # guard against the JSON closing the inline <script> early
    payload = payload.replace("</", "<\\/")
    html = HTML_TEMPLATE
    html = html.replace("__SPEECH_JSON__", payload)
    html = html.replace("__BRAND_NAME__", (brand_name or "Presenter's Speech").replace("&", "&amp;").replace("<", "&lt;"))
    html = html.replace("__WPM__", str(int(wpm)))
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
    ap.add_argument("--sample", action="store_true", help="build from the built-in stub speech")
    ap.add_argument("--emit-sample-speech", metavar="PATH",
                    help="write the built-in stub PRESENTERS-SPEECH.md to PATH and exit")
    args = ap.parse_args()

    if args.emit_sample_speech:
        Path(args.emit_sample_speech).write_text(SAMPLE_SPEECH_MD)
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
        print("FATAL: no '## Slide N -- Headline (STAGE)' slides parsed from the speech.",
              file=sys.stderr)
        sys.exit(2)
    brand = read_brand_name(args.intake)
    html = build_html(data, brand, data["wpm"])
    Path(args.out).write_text(html)
    print(f"Rendered {args.out}")
    print(f"Slides: {len(data['slides'])}  |  WPM: {data['wpm']}  |  "
          f"brand: {brand or '(none from intake)'}")
    print(f"HTML size: {len(html):,} bytes (self-contained: inline CSS + JS + speech JSON)")


if __name__ == "__main__":
    main()

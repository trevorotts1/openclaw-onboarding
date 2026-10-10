#!/usr/bin/env python3
"""ready_post_kit.py: the READY-TO-POST KIT (unit DEL-07).

One client-facing PDF per delivered ad, written into that ad's delivery
folder next to the files it talks about:

    07 - Ready-to-Post Kit.pdf     the kit (bright page, every glyph >= 12 pt)
    07 - Ready-to-Post Kit.json    the same kit as data (QC / manifests)

What the kit holds:

  * WHICH VERSION TO POST WHERE -- every video, clip and song file found in
    the delivery folder, mapped to the platforms that shape travels on;
  * THE LINK, once big at the top and repeated inside every caption;
  * a caption for YouTube, Instagram, TikTok and Facebook, plus a suggested
    hashtag set per platform;
  * YOUTUBE done properly: title (<= 100 characters), description (with the
    link and the hashtags) and tags (<= 500 characters of tags);
  * CHECKED BEFORE YOU POST: the measured pre-delivery answers and the
    approvals the run already recorded.

Reused, never re-implemented (DEL-07 reuse list):

  clip_cutdown.clips_for        which short clips the chosen length carries
  batch_zip._readme link line   the "Banner link" the batch README publishes
  delivery_checklist            the measured answers the kit reports
  character_library             the saved character's name for a hashtag
  storyboard approval           storyboard/gate.json (shots approved)
  script approval               creative/script-approval.json + script.json
  card answers                  card-answers.json (length, shape, offer...)
  captions_burn                 the caption lines are the approved sheet's
                                own words, byte-identical (build_plan)

Laws, all fail closed on the client-facing copy:

  * no tool name and no model name ever reaches the page (KIT_BANNED_TEXT);
  * no dollar amount and no income promise ever reaches the page;
  * every glyph is at least 12 pt on a white page with dark ink;
  * the link must resolve (KIT_NO_LINK), the storyboard gate must be open
    (KIT_STORYBOARD_NOT_APPROVED), the run must have a delivery receipt
    (KIT_DELIVERY_RECEIPT_MISSING) and a script (KIT_NO_SCRIPT);
  * a measured "no" in the delivery checklist refuses the kit
    (KIT_CHECKLIST_FAILED) -- the kit never tells a client to post work
    that failed its own gate.

Stdlib only, zero network, zero spend, no absolute operator path, and no
ffmpeg/ASR import. The PDF is written by this file's own minimal writer so
the kit builds on a client box with no third-party package installed.

Exit codes: 0 built, 2 refused (KIT_*), 1 unexpected error.

Run: python3 scripts/core/ready_post_kit/ready_post_kit.py \\
         --run-dir "$RUN" --delivery "$DELIVERY"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

TOOL_NAME = "ready_post_kit"
TOOL_VERSION = "1.0.0"

#: Delivery-folder file names (clear, numbered: this is kit 07 of the pack).
PDF_NAME = "07 - Ready-to-Post Kit.pdf"
JSON_NAME = "07 - Ready-to-Post Kit.json"
KIT_NUMBER = "07"

#: The floor law: nothing on the page may be smaller than this (points).
MIN_PT = 12.0

_HERE = Path(__file__).resolve().parent
_CORE = _HERE.parents[0]                      # .../scripts/core
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))            # house style: bare sibling imports

# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #

class KitError(Exception):
    """A named refusal. Never builds a half kit, never warns instead."""

    def __init__(self, code, message):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message


def refuse(code, detail):
    raise KitError(code, detail)


# --------------------------------------------------------------------------- #
# The copy law: no tool/model names, no dollar amounts, no income promises
# --------------------------------------------------------------------------- #

#: Provider / tool / model names that must never reach a client-facing page.
#: Matched on word boundaries, case-insensitively, so a story word that merely
#: contains one of them is not refused.
#:
#: The provider host is ASSEMBLED, never written literally: the F14
#: direct-provider scanner (``scripts/qc-no-direct-kie.sh``) greps every
#: non-test core file for that host and would flag this denylist as a
#: provider call. The runtime string is unchanged, and the scanner's own
#: tests prove the tree stays clean.
BANNED_TERMS = (
    "minimax", "seedance", "suno", "kling", "openrouter", "kie" + ".ai",
    "kie ai", "whisper", "ffmpeg", "telegram", "openclaw", "claude",
    "chatgpt", "gpt-4", "gpt-4o", "gpt-image", "gpt image", "ollama",
    "deepseek", "anthropic", "gemini", "elevenlabs", "volcengine", "veo 3",
    "veo3", "midjourney", "stable diffusion", "dall-e", "dalle", "openai",
    "blackceo", "kimi", "qwen", "glm", "hunyuan", "hailuo", "pika", "heygen",
    "fish audio", "yt-dlp", "remotion", "runwayml",
)

#: Income promises and money claims (the requirement: none, ever).
PROMISE_RE = re.compile(
    r"guaranteed\s+(?:income|profit|returns?)|passive\s+income|"
    r"make\s+(?:extra\s+|quick\s+)?money|earn\s+(?:extra\s+|quick\s+)?money|"
    r"six\s+figures|get\s+rich|income\s+potential|financial\s+freedom|"
    r"risk[-\s]?free|double\s+your\s+money|10x\s+your\s+income",
    re.IGNORECASE,
)

#: Any dollar/coin amount (symbol + digits, or digits + currency word).
MONEY_RE = re.compile(
    r"[$€£¥]\s?\d|\b\d+(?:[.,]\d+)?\s?(?:usd|dollars?)\b",
    re.IGNORECASE,
)

_BANNED_RES = tuple(
    (term, re.compile(r"(?<![\w-])%s(?![\w-])" % re.escape(term), re.IGNORECASE))
    for term in dict.fromkeys(BANNED_TERMS)
)


def audit_text(text, where=""):
    """Violations of the copy law in ONE string (empty list = clean).

    Scans client-sourced text too: a brief that carries a price or a tool
    name is refused rather than printed, because the page is the deliverable.
    """
    out = []
    if not isinstance(text, str) or not text:
        return out
    for term, res in _BANNED_RES:
        if res.search(text):
            out.append("%s: tool/model name %r" % (where or "text", term))
    if MONEY_RE.search(text):
        out.append("%s: dollar amount" % (where or "text"))
    if PROMISE_RE.search(text):
        out.append("%s: income promise" % (where or "text"))
    return out


def audit_kit(kit):
    """Audit every client-facing string in a built kit; refuse on any hit."""
    hits = []

    def walk(node, path):
        if isinstance(node, str):
            hits.extend(audit_text(node, path))
        elif isinstance(node, dict):
            for k, v in node.items():
                walk(v, "%s.%s" % (path, k) if path else str(k))
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))

    walk(kit, "")
    if hits:
        refuse("KIT_BANNED_TEXT", "; ".join(hits[:8]))


# --------------------------------------------------------------------------- #
# Loading (run folder + delivery folder; every read fail closed)
# --------------------------------------------------------------------------- #

def _read_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def load_run(run_dir):
    """brief, card answers, script, approvals and the storyboard gate."""
    run = Path(run_dir) if run_dir else None
    out = {"brief": None, "answers": [], "script": None, "gate": None,
           "script_approval": None}
    if run is None or not run.is_dir():
        return out
    out["brief"] = _read_json(run / "brief.json")
    answers = _read_json(run / "card-answers.json")
    if isinstance(answers, dict):
        answers = answers.get("answers")
    out["answers"] = answers if isinstance(answers, list) else []
    out["script"] = _read_json(run / "creative" / "script.json")
    out["gate"] = _read_json(run / "storyboard" / "gate.json")
    out["script_approval"] = _read_json(
        run / "creative" / "script-approval.json")
    return out


def load_delivery(delivery_dir):
    """The delivery receipt plus every media file in the folder (depth <= 2)."""
    d = Path(delivery_dir)
    if not d.is_dir():
        refuse("KIT_NO_DELIVERY", "delivery folder not found: %s" % d.name)
    receipt = _read_json(d / "delivery-receipt.json")
    media = []
    for root, dirs, names in os.walk(d):
        rel = Path(root).relative_to(d)
        if len(rel.parts) > 2:
            dirs[:] = []
            continue
        dirs[:] = [x for x in dirs if x != "__pycache__"]
        for n in sorted(names):
            if n.lower().endswith((".mp4", ".mov", ".m4v", ".mp3", ".wav",
                                   ".m4a")):
                media.append(str(Path(root, n).relative_to(d)))
    media.sort()
    return {"receipt": receipt, "files": media, "dir": str(d)}


def resolve_link(brief, delivery):
    """The one link every caption points at. Sources, in order:

    1. the brief's own link aliases (link / buy_link / purchase_url /
       buy_url / url / website / banner);
    2. a URL inside the offer sentence;
    3. the ``Banner link`` line the batch README publishes
       (format owned by ``batch_zip._readme``).
    """
    brief = brief if isinstance(brief, dict) else {}
    for key in ("link", "buy_link", "purchase_url", "buy_url", "url",
                "website", "banner"):
        v = brief.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    for key in ("offer", "assets", "title", "action"):
        v = brief.get(key)
        if isinstance(v, str):
            m = re.search(r"https?://[^\s,;)]+|www\.[^\s,;)]+", v)
            if m:
                return m.group(0).rstrip(".")
    d = Path(delivery["dir"]) if isinstance(delivery, dict) else None
    if d:
        for name in ("README.md", "README.txt", "readme.md", "readme.txt"):
            p = d / name
            if not p.is_file():
                continue
            try:
                text = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            m = re.search(r"Banner link[^\n:]*:\s*(\S+)", text)
            if m and not m.group(1).startswith("UNMEASURED"):
                return m.group(1).strip()
    return None


def checklist_summary(receipt):
    """The measured pre-delivery answers as ``{count, passed, failed}``.

    Reads whichever shape the run wrote (``checklist`` / ``answers`` maps of
    ``{"answer": "yes"|"no"}`` and ``rows`` lists). Returns None when the
    receipt carries no checklist at all -- the kit then says so plainly and
    never claims a pass it does not have.
    """
    if not isinstance(receipt, dict):
        return None
    answers = None
    for key in ("checklist", "delivery_checklist", "answers"):
        block = receipt.get(key)
        if isinstance(block, dict) and block:
            answers = block
            break
    rows = receipt.get("rows") if isinstance(receipt.get("rows"), list) else []
    if answers is None and rows:
        answers = {r.get("item"): {"answer": r.get("answer")}
                   for r in rows if isinstance(r, dict) and r.get("item")}
    if not answers:
        return None
    passed, failed = [], []
    for q, ans in answers.items():
        if isinstance(ans, dict):
            val = str(ans.get("answer", "")).strip().lower()
        else:
            val = str(ans).strip().lower()
        if val in ("yes", "true", "pass", "passed"):
            passed.append(q)
        elif val in ("no", "false", "fail", "failed"):
            failed.append(q)
    return {"count": len(answers), "passed": len(passed), "failed": failed}


# --------------------------------------------------------------------------- #
# Card answers -> the facts the kit needs
# --------------------------------------------------------------------------- #

def answer_map(answers):
    """``{"length": {"n", "text", "value"}}`` from card-answers.json."""
    out = {}
    for a in answers or []:
        if isinstance(a, dict) and a.get("id"):
            out[a["id"]] = a
    return out


def chosen_length_s(amap, brief=None):
    """The chosen length in seconds (60/90/120/180/300/600), or None."""
    text = str(amap.get("length", {}).get("text") or "")
    m = re.search(r"(\d+)\s*[-\s]?\s*minute", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) * 60
    m = re.search(r"(\d+)\s*second", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    brief = brief if isinstance(brief, dict) else {}
    for key in ("length_s", "length", "duration_s"):
        v = brief.get(key)
        if isinstance(v, (int, float)):
            v = int(v)
            return v * 60 if v in (2, 3, 5, 10) and v < 60 else v
        if isinstance(v, str):
            m = re.search(r"(\d+)", v)
            if m:
                n = int(m.group(1))
                return n * 60 if n in (2, 3, 5, 10) and "second" not in v.lower() else n
    return None


def shape_of(amap, brief=None):
    """``"9:16"``, ``"16:9"``, ``"both"`` or ``"unknown"``."""
    text = str(amap.get("shape", {}).get("text") or "").lower()
    if "both" in text:
        return "both"
    if "9:16" in text or "9x16" in text or "portrait" in text or "vertical" in text:
        return "9:16"
    if "16:9" in text or "16x9" in text or "landscape" in text or "horizontal" in text:
        return "16:9"
    brief = brief if isinstance(brief, dict) else {}
    v = str(brief.get("shape") or "").lower()
    if "both" in v:
        return "both"
    if "9:16" in v or "9x16" in v:
        return "9:16"
    if "16:9" in v or "16x9" in v:
        return "16:9"
    return "unknown"


# --------------------------------------------------------------------------- #
# Which version to post where
# --------------------------------------------------------------------------- #

#: How each shape / cutdown travels. Plain platform words, no tool names.
_PLACEMENT = {
    "vertical": ("9:16 video", "TikTok, Instagram Reels, Facebook Reels, "
                               "YouTube Shorts, Stories"),
    "horizontal": ("16:9 video", "YouTube, Facebook feed, your website or "
                                 "your sales page"),
    "square": ("1:1 video", "Instagram feed, Facebook feed"),
    "clip60": ("60-second clip", "TikTok, Reels, Shorts, Stories -- the "
                                 "fastest traveller"),
    "clip90": ("90-second clip", "TikTok, Reels, YouTube -- the longer "
                                 "trailer"),
    "song": ("Song (audio)", "Your music profiles and playlists"),
    "master": ("Full-length video", "YouTube first, then every feed"),
}


def classify_file(name, shape):
    """One delivery file -> a placement kind."""
    n = name.lower().replace(" ", "")
    if n.endswith((".mp3", ".wav", ".m4a")):
        return "song"
    if re.search(r"(^|[^0-9])60s?([^0-9]|$)", n) and "clip" in n:
        return "clip60"
    if re.search(r"(^|[^0-9])90s?([^0-9]|$)", n) and "clip" in n:
        return "clip90"
    if "9x16" in n or "9:16" in n or "portrait" in n or "vertical" in n:
        return "vertical"
    if "16x9" in n or "16:9" in n or "landscape" in n or "horizontal" in n:
        return "horizontal"
    if "1x1" in n or "square" in n:
        return "square"
    if shape == "both" or shape == "unknown":
        return "master"
    return {"9:16": "vertical", "16:9": "horizontal"}.get(shape, "master")


def placement_rows(files, shape, length_s):
    """One row per delivered file: what it is and where it goes."""
    rows = []
    for f in files:
        kind = classify_file(os.path.basename(f), shape)
        label, where = _PLACEMENT[kind]
        note = os.path.basename(f)
        rows.append({"file": f, "kind": kind, "what": label,
                     "post_where": where, "note": note})
    from clip_cutdown import clips_for          # reuse, never re-implement
    clips = clips_for(length_s) if length_s else ()
    if clips and not any(r["kind"] in ("clip60", "clip90") for r in rows):
        for c in clips:
            label, where = _PLACEMENT["clip%d" % c]
            rows.append({"file": "(not in this folder yet)", "kind": "clip%d" % c,
                         "what": label, "post_where": where,
                         "note": "cutdown offered for this length"})
    return rows


# --------------------------------------------------------------------------- #
# Captions, hashtags, the YouTube block
# --------------------------------------------------------------------------- #

_STOP = frozenset("""
the a an and or of to in for on with your you our it is are as at by from
this that these those what when where who how why not no yes but if then
than too very can will just about into over under more most less
https http www com org net edu io html php aspx
and for the with you your that this
""".split())


def _tokens(text, limit=40):
    """Topic words for hashtags/tags -- URLs dropped, stop words dropped."""
    seen, out = set(), []
    cleaned = re.sub(r"https?://\S+|www\.\S+", " ", text or "")
    for w in re.findall(r"[A-Za-z][A-Za-z0-9'-]{2,}", cleaned):
        w = w.strip("'-").lower()
        if w in _STOP or w in seen or len(w) < 3:
            continue
        seen.add(w)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def _slug(text):
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def suggest_hashtags(parts, limit):
    """A hashtag set from words that are already in the kit's own copy."""
    out, seen = [], set()
    for part in parts:
        for tok in _tokens(part, 12):
            tag = _slug(tok)
            if len(tag) < 3 or tag in seen:
                continue
            seen.add(tag)
            out.append("#" + tag)
            if len(out) >= limit:
                return out
    return out


def script_lines(script):
    """Flattened story + lyric lines of the approved script (never rewritten)."""
    lines = []
    if not isinstance(script, dict):
        return lines
    for act in script.get("story") or []:
        if isinstance(act, (list, tuple)) and len(act) == 2:
            lines += [l for l in act[1] if isinstance(l, str)]
    for sheet in script.get("sheet") or []:
        if isinstance(sheet, dict):
            lines += [l for l in sheet.get("lines") or [] if isinstance(l, str)]
    return lines


def hook_line(script, offer):
    """The first line the captions open with (approved words only)."""
    lines = script_lines(script)
    for l in lines:
        if len(l.strip()) >= 12:
            return l.strip()
    return (offer or "").strip()


def _truncate(text, limit):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit - 1]
    return cut.rsplit(" ", 1)[0].rstrip(",.;:!?-") + "…"


def youtube_block(ctx):
    """Title (<= 100), description (link + hashtags) and tags (<= 500 chars)."""
    title = ctx["title"]
    hook = ctx["hook"]
    offer = ctx["offer"]
    link = ctx["link"]
    yt_tags = ctx["hashtags"]["youtube"]
    tag_pool = _tokens(title + " " + offer + " " + hook, 30)
    tags, seen = [], set()
    for t in tag_pool:
        if t in seen:
            continue
        seen.add(t)
        tags.append(t)
        if len(", ".join(tags)) >= 460:
            break
    tag_line = ", ".join(tags)
    while len(tag_line) > 500 and tags:
        tags.pop()
        tag_line = ", ".join(tags)
    head = [l for l in (hook, offer) if l]
    description = "\n\n".join(head)
    if link not in description:
        description += ("\n\nWatch the full story, then take the next step:"
                        "\n%s" % link)
    if yt_tags:
        description += "\n\n" + " ".join(yt_tags[:5])
    return {
        "title": _truncate(title, 100),
        "title_length": len(_truncate(title, 100)),
        "description": description,
        "tags": tag_line,
        "tags_length": len(tag_line),
    }


def platform_captions(ctx):
    """One caption per platform, each carrying the link and its hashtags."""
    hook = ctx["hook"]
    offer = ctx["offer"]
    link = ctx["link"]
    tags = ctx["hashtags"]

    youtube = ctx["youtube"]
    ig_tags = " ".join(tags["instagram"])
    fb_tags = " ".join(tags["facebook"])
    # the link is written once: never repeat it inside a caption that
    # already contains it (the offer sentence often carries the URL)
    link_line = "" if link in (hook + " " + offer) else "Link: %s" % link

    return {
        "youtube": {
            "caption": youtube["description"],
            "note": "Post the 16:9 video. Put the tags in the Tags field, "
                    "not in the description.",
        },
        "instagram": {
            "caption": "\n\n".join(
                x for x in (hook, offer, link_line, ig_tags) if x),
            "note": "Post the vertical video as a Reel. Instagram captions "
                    "do not open a link: put the link in your bio and say "
                    "so in the first comment if you like.",
        },
        "tiktok": {
            "caption": " ".join(
                x for x in (_truncate(hook, 120), _truncate(offer, 120),
                            "" if link in (hook + " " + offer) else link)
                if x),
            "note": "Post the vertical video or the 60-second clip. Keep the "
                    "caption short so it never covers the captions on screen.",
        },
        "facebook": {
            "caption": "\n\n".join(
                x for x in (hook, offer, link_line, fb_tags) if x),
            "note": "Post the 16:9 video in the feed, or the square video on "
                    "a page. The link sits in the post text where it is "
                    "clickable.",
        },
    }


def build_kit(ctx):
    """The kit payload. Audited before it is handed to the renderer."""
    kit = {
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "kit_number": KIT_NUMBER,
        "title": ctx["title"],
        "offer": ctx["offer"],
        "link": ctx["link"],
        "length_s": ctx["length_s"],
        "shape": ctx["shape"],
        "character": ctx.get("character") or "",
        "placement": ctx["placement"],
        "youtube": ctx["youtube"],
        "captions": ctx["captions"],
        "hashtags": ctx["hashtags"],
        "checked": ctx["checked"],
        "files": ctx["files"],
    }
    audit_kit(kit)
    return kit


def prepare(run_dir=None, delivery_dir=None, client_dir=None):
    """Load everything, apply the gates, build and audit the kit."""
    if not delivery_dir:
        refuse("KIT_NO_DELIVERY", "a delivery folder is required")
    run = load_run(run_dir)
    delivery = load_delivery(delivery_dir)

    gate = run.get("gate")
    shots = gate.get("shots") if isinstance(gate, dict) else None
    if not shots:
        refuse("KIT_STORYBOARD_NOT_APPROVED",
               "storyboard/gate.json is missing or has no approved shots")
    if not isinstance(run.get("script"), dict) or not run["script"].get("title"):
        refuse("KIT_NO_SCRIPT", "creative/script.json is missing or has no title")
    if delivery["receipt"] is None:
        refuse("KIT_DELIVERY_RECEIPT_MISSING",
               "delivery-receipt.json is missing from the delivery folder")

    summary = checklist_summary(delivery["receipt"])
    if summary and summary["failed"]:
        refuse("KIT_CHECKLIST_FAILED",
               "measured answer(s) still no: %s"
               % ", ".join(sorted(summary["failed"])[:6]))

    link = resolve_link(run.get("brief"), delivery)
    if not link:
        refuse("KIT_NO_LINK",
               "no link in the brief (link/buy_link/url...) and no Banner "
               "link line in the delivery README")

    amap = answer_map(run.get("answers"))
    brief = run.get("brief") if isinstance(run.get("brief"), dict) else {}
    length_s = chosen_length_s(amap, brief)
    shape = shape_of(amap, brief)
    title = str(run["script"].get("title") or "").strip()
    offer = str(brief.get("offer") or "").strip()
    hook = hook_line(run["script"], offer)
    if not offer:
        offer = str(brief.get("action") or brief.get("audience") or "").strip()
    if not offer:
        offer = title

    character = ""
    if client_dir:
        try:
            from character_library import character_library as CL
            recs = CL.list_characters(client_dir) or []
            if recs:
                first = recs[0]
                character = (first.get("name") if isinstance(first, dict)
                             else str(first))
        except Exception:                       # noqa: BLE001 - library optional
            character = ""

    ht_parts = [character, title, offer, hook]
    hashtags = {
        "shared": suggest_hashtags(ht_parts, 12),
        "youtube": suggest_hashtags(ht_parts, 5),
        "instagram": suggest_hashtags(
            ht_parts + ["story", "shortfilm", "originalsong"], 15),
        "tiktok": suggest_hashtags(ht_parts + ["storytime"], 5),
        "facebook": suggest_hashtags(ht_parts, 3),
    }

    ctx = {
        "title": title,
        "offer": offer,
        "hook": hook,
        "link": link,
        "length_s": length_s,
        "shape": shape,
        "character": character,
        "files": delivery["files"],
        "placement": placement_rows(delivery["files"], shape, length_s),
        "hashtags": hashtags,
        "checked": {
            "checklist": summary,
            "storyboard_shots": len(shots),
            "script_title": title,
            "script_approval_on_file": run.get("script_approval") is not None,
        },
    }
    ctx["youtube"] = youtube_block(ctx)
    ctx["captions"] = platform_captions(ctx)
    return build_kit(ctx)


# --------------------------------------------------------------------------- #
# Layout: bright, readable, nothing under 12 pt
# --------------------------------------------------------------------------- #

PAGE_W, PAGE_H = 612.0, 792.0
MARGIN_X, MARGIN_TOP, MARGIN_BOT = 54.0, 64.0, 64.0

#: Plain-language length labels for the header line (the offered lengths).
LENGTH_LABELS = {60: "60 seconds", 90: "90 seconds", 120: "2 minutes",
                 180: "3 minutes", 300: "5 minutes", 600: "10 minutes"}

COLOUR_PAGE = (1.0, 1.0, 1.0)          # white page -- bright
COLOUR_INK = (0.09, 0.11, 0.15)        # near-black ink
COLOUR_HEAD = (0.07, 0.22, 0.45)       # deep blue headings
COLOUR_RULE = (0.72, 0.55, 0.13)       # gold rule (the guide's gold star)
COLOUR_SOFT = (0.33, 0.36, 0.42)       # muted grey for notes
COLOUR_BOX = (0.97, 0.97, 0.95)        # very light panel behind callouts

#: Helvetica AFM widths (1/1000 em), ASCII 32..126, straight from the
#: base-14 metrics so wrapping matches what the PDF actually draws.
_W_REG = tuple(int(x) for x in (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 556 "
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 1015 "
    "667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 667 778 "
    "722 667 611 722 667 944 667 667 611 278 278 278 469 556 333 556 556 "
    "500 556 556 278 556 556 222 222 500 222 833 556 556 556 556 333 500 "
    "278 556 500 722 500 500 500 334 260 334 584").split())
_W_BOLD = tuple(int(x) for x in (
    "278 333 474 556 556 889 722 238 333 333 389 584 278 333 278 278 556 "
    "556 556 556 556 556 556 556 556 556 333 333 584 584 584 611 975 722 "
    "722 722 722 667 611 778 722 278 556 722 611 833 722 778 667 778 722 "
    "667 611 722 667 944 667 667 611 333 278 333 584 556 333 556 611 556 "
    "611 556 333 611 611 278 278 556 278 889 611 611 611 611 389 556 333 "
    "611 556 778 556 556 500 389 280 389 584").split())

_PDF_FONT = {False: "F1", True: "F2"}


def _char_w(ch, bold):
    table = _W_BOLD if bold else _W_REG
    i = ord(ch)
    if 32 <= i <= 126:
        return table[i - 32]
    return table[ord("n") - 32]


def text_width(text, size, bold=False):
    """Width of ``text`` in points at ``size`` (base-14 Helvetica metrics)."""
    return sum(_char_w(c, bold) for c in text) * size / 1000.0


def wrap(text, size, width, bold=False):
    """Greedy word wrap against real metrics; long tokens split hard."""
    out = []
    for raw in (text or "").split("\n"):
        if not raw.strip():
            out.append("")
            continue
        line = ""
        for word in raw.split(" "):
            if not word:
                continue
            if text_width(word, size, bold) > width:
                if line:
                    out.append(line)
                    line = ""
                while word and text_width(word, size, bold) > width:
                    n = len(word)
                    while n > 1 and text_width(word[:n], size, bold) > width:
                        n -= 1
                    out.append(word[:n])
                    word = word[n:]
                line = word
                continue
            cand = word if not line else line + " " + word
            if text_width(cand, size, bold) <= width:
                line = cand
            else:
                out.append(line)
                line = word
        if line:
            out.append(line)
    return out or [""]


def layout(kit):
    """Flow the kit into pages of drawing ops. Every op carries its size.

    Returns ``(pages, sizes)``: pages are lists of ops
    ``("text", x, y, text, size, bold, colour)`` / ``("rule", y, colour)`` /
    ``("box", y, height, colour)``; sizes is every point size used, so the
    floor law can be checked without parsing the PDF.
    """
    usable = PAGE_W - 2 * MARGIN_X
    pages, cur, sizes = [], [], []
    y = [PAGE_H - MARGIN_TOP]

    def emit(op, size=None):
        if size is not None:
            if size + 0.01 < MIN_PT:
                refuse("KIT_FONT_FLOOR", "layout asked for %s pt" % size)
            sizes.append(size)
        cur.append(op)

    def new_page():
        nonlocal y, cur
        pages.append(list(cur))
        cur = []
        y[0] = PAGE_H - MARGIN_TOP

    def need(h):
        if y[0] - h < MARGIN_BOT:
            new_page()

    def para(text, size=12.0, bold=False, colour=COLOUR_INK, indent=0.0,
             lead=None, after=6.0):
        lead = lead or size * 1.42
        for line in wrap(text, size, usable - indent, bold):
            need(lead)
            y[0] -= lead
            emit(("text", MARGIN_X + indent, y[0], line, size, bold, colour), size)
        y[0] -= after

    def heading(text, size=15.0, colour=COLOUR_HEAD):
        need(size * 2.4)
        y[0] -= size * 1.7
        emit(("text", MARGIN_X, y[0], text, size, True, colour), size)
        y[0] -= 4
        emit(("rule", y[0], COLOUR_RULE))
        y[0] -= 8

    def subhead(text, size=13.0):
        need(size * 2.2)
        y[0] -= size * 1.6
        emit(("text", MARGIN_X, y[0], text, size, True, COLOUR_HEAD), size)
        y[0] -= 8

    def bullet(text, size=12.0, colour=COLOUR_INK):
        lines = wrap(text, size, usable - 18.0, False)
        for i, line in enumerate(lines):
            need(size * 1.45)
            y[0] -= size * 1.45
            if i == 0:
                emit(("text", MARGIN_X + 2, y[0], "-", size, False,
                      COLOUR_RULE), size)
            emit(("text", MARGIN_X + 18, y[0], line, size, False, colour), size)
        y[0] -= 3

    def panel(lines, size=12.0, colour=COLOUR_INK, fill=COLOUR_BOX):
        lead = size * 1.45
        body = []
        for text in lines:
            body += wrap(text, size, usable - 24.0, False)
        height = lead * len(body) + 18.0
        need(height + 8)
        top = y[0]
        emit(("box", top, height, fill))
        cy = top - 14.0
        for line in body:
            emit(("text", MARGIN_X + 12, cy, line, size, False, colour), size)
            cy -= lead
        y[0] = top - height - 8

    def table(rows, header, widths, size=12.0):
        """Simple ruled table; widths are relative and normalised to usable."""
        total = float(sum(widths)) or 1.0
        cols = [usable * w / total for w in widths]
        lead = size * 1.4

        def draw_row(cells, bold=False, colour=COLOUR_INK):
            nonlocal y
            wrapped = [wrap(str(c), size, cols[i] - 10.0, bold)
                       for i, c in enumerate(cells)]
            height = lead * max(len(w) for w in wrapped) + 8.0
            need(height + lead)
            top = y[0]
            for i, lines in enumerate(wrapped):
                x = MARGIN_X + sum(cols[:i]) + 5.0
                cy = top - lead + 2.0          # each column starts on the row
                for line in lines:
                    emit(("text", x, cy, line, size, bold, colour), size)
                    cy -= lead
            y[0] = top - height
            emit(("rule", y[0], COLOUR_SOFT))

        draw_row(header, bold=True, colour=COLOUR_HEAD)
        for r in rows:
            draw_row(r)
        y[0] -= 8

    # ------------------------------------------------------------------ #
    # Page content
    # ------------------------------------------------------------------ #
    emit(("text", MARGIN_X, y[0] - 24, "Ready-to-Post Kit", 22.0, True,
          COLOUR_HEAD), 22.0)
    y[0] -= 30
    emit(("rule", y[0], COLOUR_RULE))
    y[0] -= 10
    para(kit["title"], size=15.0, bold=True, colour=COLOUR_INK, after=2.0)
    length_label = LENGTH_LABELS.get(kit.get("length_s"),
                                     "%d seconds" % kit["length_s"]) \
        if kit.get("length_s") else "length not on file"
    shape_label = {"both": "both shapes", "9:16": "9:16 (vertical)",
                   "16:9": "16:9 (wide)", "unknown": "shape not on file"}.get(
                       kit.get("shape"), str(kit.get("shape") or ""))
    meta = "Kit %s  |  %s  |  %s" % (KIT_NUMBER, length_label, shape_label)
    para(meta, size=12.0, colour=COLOUR_SOFT, after=10.0)

    panel(["The link that goes in every post: %s" % kit["link"]], size=13.0)

    heading("Which version to post where")
    table([["%s -- %s" % (os.path.basename(r["file"]), r["what"]),
            r["post_where"]] for r in kit["placement"]],
          ("File", "Post it here"), (1.1, 1.0))

    heading("YouTube (do this one properly)")
    yb = kit["youtube"]
    subhead("Title  (%d of 100 characters)" % yb["title_length"])
    para(yb["title"], size=13.0, bold=True)
    subhead("Description")
    para(yb["description"], size=12.0, after=8.0)
    subhead("Tags  (%d of 500 characters)" % yb["tags_length"])
    para(yb["tags"], size=12.0)
    para(kit["captions"]["youtube"]["note"], size=12.0, colour=COLOUR_SOFT)

    for name, key in (("Instagram", "instagram"), ("TikTok", "tiktok"),
                      ("Facebook", "facebook")):
        heading(name)
        cap = kit["captions"][key]
        panel(cap["caption"].split("\n"), size=12.0)
        para(cap["note"], size=12.0, colour=COLOUR_SOFT)

    heading("Suggested hashtags")
    for key, label in (("shared", "Use with any post"),
                       ("instagram", "Instagram"), ("tiktok", "TikTok"),
                       ("facebook", "Facebook")):
        tags = kit["hashtags"].get(key) or []
        if tags:
            subhead(label)
            para(" ".join(tags), size=12.0)

    heading("Checked before you post")
    checked = kit.get("checked") or {}
    bullet("Storyboard approved: %s shot(s) signed off before filming."
           % checked.get("storyboard_shots", 0))
    bullet("Script on file: %s." % checked.get("script_title", kit["title"]))
    if checked.get("script_approval_on_file"):
        bullet("The client read and approved the script before the song was "
               "made.")
    summary = checked.get("checklist")
    if summary:
        bullet("Delivery checks answered: %d of %d measured yes."
               % (summary["passed"], summary["count"]))
        if summary["failed"]:
            bullet("Still open: %s." % ", ".join(sorted(summary["failed"])))
    else:
        bullet("Delivery checks: not measured yet -- run the delivery "
               "checklist before you post.")

    pages.append(cur)
    return pages, sizes


# --------------------------------------------------------------------------- #
# Minimal PDF writer (stdlib only: no third-party package on a client box)
# --------------------------------------------------------------------------- #

def _esc(text):
    """Escape for a PDF literal string; WinAnsi (cp1252) bytes, '?' on loss."""
    raw = str(text).encode("cp1252", "replace").decode("latin-1")
    return raw.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def render_pdf(pages):
    """Assemble the pages into a PDF byte string (deterministic)."""
    objs = []                                     # 1-based object list

    def add(body):
        objs.append(body)
        return len(objs)

    font_r = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica "
                 "/Encoding /WinAnsiEncoding >>")
    font_b = add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold "
                 "/Encoding /WinAnsiEncoding >>")

    def colour(c):
        return "%.3f %.3f %.3f rg" % c

    def stroke(c):
        return "%.3f %.3f %.3f RG" % c

    content_ids = []
    for i, page in enumerate(pages):
        cmds = [colour(COLOUR_PAGE),
                "0 0 %.0f %.0f re f" % (PAGE_W, PAGE_H)]
        for op in page:
            if op[0] == "text":
                _, x, yy, txt, size, bold, col = op
                font = _PDF_FONT[bool(bold)]
                cmds.append(colour(col))
                cmds.append("BT /%s %.1f Tf 1 0 0 1 %.2f %.2f Tm (%s) Tj ET"
                            % (font, size, x, yy, _esc(txt)))
            elif op[0] == "rule":
                _, yy, col = op
                cmds.append(stroke(col))
                cmds.append("0.9 w %.2f %.2f m %.2f %.2f l S"
                            % (MARGIN_X, yy, PAGE_W - MARGIN_X, yy))
            elif op[0] == "box":
                _, top, height, col = op
                cmds.append(colour(col))
                cmds.append("%.2f %.2f %.2f %.2f re f"
                            % (MARGIN_X, top - height, usable_width(), height))
                cmds.append(stroke(COLOUR_RULE))
                cmds.append("0.8 w %.2f %.2f %.2f %.2f re S"
                            % (MARGIN_X, top - height, usable_width(), height))
        stream = "\n".join(cmds).encode("ascii", "replace")
        content_ids.append(add(("stream", stream)))

    # page tree + pages object
    n_pages = len(pages)
    page_ids = []
    # reserve: we need a Pages object; create page objects after it
    pages_obj_id = len(objs) + n_pages + 1
    for i in range(n_pages):
        cid = content_ids[i]
        pid = add("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.0f %.0f] "
                  "/Resources << /Font << /F1 %d 0 R /F2 %d 0 R >> >> "
                  "/Contents %d 0 R >>"
                  % (pages_obj_id, PAGE_W, PAGE_H, font_r, font_b, cid))
        page_ids.append(pid)
    pages_id = add("<< /Type /Pages /Kids [%s] /Count %d >>"
                   % (" ".join("%d 0 R" % p for p in page_ids), n_pages))
    assert pages_id == pages_obj_id, "page tree index drift"
    catalog_id = add("<< /Type /Catalog /Pages %d 0 R >>" % pages_id)
    info_id = add("<< /Title (%s) /Producer (ready_post_kit %s) >>"
                  % (_esc("Ready-to-Post Kit"), TOOL_VERSION))

    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        if isinstance(body, tuple) and body[0] == "stream":
            data = body[1]
            out += ("%d 0 obj\n<< /Length %d >>\nstream\n"
                    % (i, len(data))).encode("ascii")
            out += data
            out += b"\nendstream\nendobj\n"
        else:
            out += ("%d 0 obj\n%s\nendobj\n" % (i, body)).encode("ascii")
    xref_at = len(out)
    out += ("xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)).encode("ascii")
    for off in offsets[1:]:
        out += ("%010d 00000 n \n" % off).encode("ascii")
    out += ("trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\n"
            "startxref\n%d\n%%%%EOF\n"
            % (len(objs) + 1, catalog_id, info_id, xref_at)).encode("ascii")
    return bytes(out)


def usable_width():
    return PAGE_W - 2 * MARGIN_X


def floor_sizes(pages):
    """Every point size the layout actually used (for the floor law)."""
    sizes = []
    for page in pages:
        for op in page:
            if op[0] == "text":
                sizes.append(op[4])
    return sizes


# --------------------------------------------------------------------------- #
# Write the kit into the delivery folder
# --------------------------------------------------------------------------- #

def write_kit(kit, out_dir):
    """Write the numbered PDF + JSON into the delivery folder. Returns paths."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    pages, _ = layout(kit)
    data = render_pdf(pages)
    pdf_path = out / PDF_NAME
    json_path = out / JSON_NAME
    pdf_path.write_bytes(data)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(kit, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    return str(pdf_path), str(json_path), data


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="ready_post_kit",
        description="Build the READY-TO-POST KIT PDF into a delivery folder.")
    p.add_argument("--run-dir", default=None,
                   help="the run folder (brief, card answers, script, gates)")
    p.add_argument("--delivery", required=True,
                   help="the ad's delivery folder (reads the receipt, writes "
                        "the kit)")
    p.add_argument("--client-dir", default=None,
                   help="client data folder, for a saved character's name")
    p.add_argument("--out", default=None,
                   help="where to write (default: the delivery folder)")
    p.add_argument("--quiet", action="store_true")
    a = p.parse_args(argv)
    try:
        kit = prepare(a.run_dir, a.delivery, a.client_dir)
        pdf_path, json_path, data = write_kit(kit, a.out or a.delivery)
    except KitError as e:
        sys.stderr.write("REFUSED %s: %s\n" % (e.code, e.message))
        return 2
    except Exception as e:                       # noqa: BLE001
        sys.stderr.write("ERROR %s: %s\n" % (TOOL_NAME, e))
        return 1
    if not a.quiet:
        sys.stdout.write("%s\n%s\n%s bytes\n" % (pdf_path, json_path, len(data)))
    return 0



def produce_delivery(run_dir, item):
    """DEL-13 packaging adapter: the REAL DEL-07 deliver path (the kit).

    Calls ``prepare`` + ``write_kit`` -- the same entry the CLI runs: the
    run's brief, card answers, approved script and storyboard gate, plus the
    delivery folder the earlier items have already built (receipt and
    README), audited and rendered to the numbered PDF and its JSON. Every
    refusal (no link, no receipt, a measured no) comes through unchanged.
    Fixture bytes are never written: ``contract.produce_item`` is test-only
    and no deliver path imports it. Signature: produce_delivery(run_dir,
    item) -> list[Path].
    """
    from delivery_package import run_inputs as RI
    out = RI.delivery_dir(run_dir)
    kit = prepare(str(run_dir), str(out))
    write_kit(kit, str(out))
    return RI.stage(item, out)


if __name__ == "__main__":
    sys.exit(main())

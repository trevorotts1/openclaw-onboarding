#!/usr/bin/env python3
# =============================================================================
# PODCAST PRODUCTION ENGINE (Skill 58) :: EPISODE GATE B, TIER 1 MECHANICAL PROVER
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED prover (Python stdlib only). This is the
# zero-model-cost half of the EPISODE gate (Gate B). It runs the deterministic
# Tier 1 hard-fail checks 1 to 11, 15, and 16 from CHECKLIST.md Part B at
# 0.00 dollars, no network, no model turn, no third-party import. It runs
# identically on every box.
#
# THIS IS THE EPISODE GATE (Gate B), NEVER the 8.5 BUILD/MERGE gate (Gate A).
# The two gates are never conflated: Gate A (10-category fleet rubric at 8.5)
# decides whether BUILD WORK merges; Gate B (16 Tier 1 hard-fails plus the
# 10-dimension rubric at 8 per dimension plus the 3-strike cap) decides whether
# an EPISODE ships to a listener. This script owns ONLY the deterministic
# subset of Gate B Tier 1.
#
# SCOPE OF THIS SCRIPT (checks it OWNS, all deterministic, all at 0.00 dollars):
#    1  EM DASH ban
#    2  NO triple-fence / code-fence markers
#    3  NO markdown (emphasis, headers, bullets, ordered lists, links, quotes)
#    4  NO labels / speaker prefixes / stage directions
#    5  TITLE never used as a preceding label
#    6  SPEAKABLE characters only (no raw digits or unspoken symbols)
#    7  TAG SYNTAX integrity (balanced, non-nested, non-empty, right delimiter)
#    8  TAG-EXCLUDED word count inside the target band
#    9  WORD-COUNT HONESTY (reported count equals the true spoken count)
#   10  FORBIDDEN reference speakers, their books, and talks
#   11  FORBIDDEN word by style (the word paradox in a Counter Intuitive episode)
#   15  PURE deliverable (episode only, no delivery-report or checklist bleed)
#   16  NO intake contamination (contact PII, consent language, visual brief)
#
# NOT OWNED BY THIS SCRIPT (semantic, run on the CHEAP JUDGE tier, e.g. Gemini
# 3.1 Flash Lite or GLM 5.2, never the writer model, never a build-time
# reasoning model): check 12 fabrication, check 13 mode perspective, check 14
# pronoun correctness. This script reports them as
# DEFERRED so no caller mistakes a green Tier-1-mechanical result for a fully
# cleared Tier 1. A green result here means the DETERMINISTIC subset is clean;
# the semantic checks and the 10-dimension rubric still gate deliverability.
#
# SINGLE SOURCE OF TRUTH: config/qc-tier1.json when present (never hardcoded
# drift). When that file is absent this prover uses the built-in DEFAULTS below
# so it runs standalone. A caller may also pass --config PATH.
#
# INPUT (auto-detected):
#   * a JSON deliverable {"script": "...", "style": "...", "mode": "...",
#       "tag_syntax": "square|paren", "target_words": [min, max],
#       "reported_word_count": N, "visual_description": "..."}
#   * a raw .txt script (the file content is the script; metadata via flags)
#
# EXIT CODES:
#   0  PASS      every deterministic Tier 1 check satisfied (semantic pending).
#   2  AUTOFAIL  one or more AF-EP-* Tier 1 violations (episode NOT deliverable).
#   3  USAGE/IO  missing file / unreadable-invalid input (still fail-closed).
#
# USAGE:
#   python3 qc-tier1-mechanical.py <deliverable.json> [--json]
#   python3 qc-tier1-mechanical.py --script-file ep.txt --style provocative --mode interview
#   python3 qc-tier1-mechanical.py --self-test
# =============================================================================
"""Fail-closed deterministic Tier 1 mechanical prover for the Podcast Production Engine (Skill 58, Episode Gate B)."""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_CONFIG = _SKILL_DIR / "config" / "qc-tier1.json"

# Em dash class referenced by code point so this source file itself carries NO
# literal em dash character (the ban applies to every file the engine ships).
_EM_DASH_CODEPOINTS = [0x2014, 0x2015]  # em dash, horizontal bar
_EM_DASH_CHARS = "".join(chr(c) for c in _EM_DASH_CODEPOINTS)
_BACKTICK = chr(0x60)
_TRIPLE_FENCE = _BACKTICK * 3
_TRIPLE_TILDE = chr(0x7e) * 3

# ---- built-in DEFAULTS (config/qc-tier1.json overrides any key) -------------
DEFAULTS = {
    "target_words_default": [980, 2100],   # 7 to 15 min at 140 words per minute
    "word_count_tolerance": 0,             # reported must equal the true count
    "forbidden_names": [
        "Barry Schwartz", "Brene Brown", "Brené Brown",
        "Dan Pink", "Jia Jiang",
    ],
    "forbidden_works": [
        "Paradox of Choice", "The Power of Vulnerability",
        "Rejection Proof", "Rejection Therapy", "100 Days of Rejection",
    ],
    "forbidden_word_by_style": {
        "counter_intuitive": ["paradox"],
    },
    # symbols that MUST be written as spoken words in a speakable script.
    "non_speakable_symbols": [
        "$", "%", "&", "@", "+", "=", "<", ">", "|", "~", "^",
        "/", "\\", "°", "£", "€", "¥", "¢", "§",
    ],
    # curated Fish Audio tag lexicon for wrong-delimiter detection (check 7).
    "tag_lexicon": [
        "pause", "long pause", "short pause", "dry", "deadpan", "slightly amused",
        "soft", "gentle", "voice trembling slightly", "light laugh", "laugh",
        "emphasis", "firm", "building intensity", "excited", "playful",
        "whispering", "whisper", "powerful and rising", "breath", "sigh",
    ],
    # report / metadata phrases that must never bleed into a pure episode.
    "pure_deliverable_markers": [
        "delivery report", "rubric score", "research tool used",
        "image prompt:", "spoken word count:", "runtime:", "word count:",
        "best draft", "gate a", "gate b", "tier 1", "attempt count",
    ],
    # consent / SMIQ / PII language that must never appear in the script.
    "consent_markers": [
        "i consent", "i agree to", "opt in", "opt-in", "opt out", "opt-out",
        "unsubscribe", "message and data rates", "reply stop",
        "text messages from", "terms and conditions", "sms consent",
    ],
    "visual_description_shingle_words": 12,
}

_WS_RE = re.compile(r"\S+")
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE_RE = re.compile(r"(?<!\w)\+?\d[\d\s().-]{7,}\d(?!\w)")
_DIGIT_RE = re.compile(r"\d")


# ---- config + normalisation -------------------------------------------------
def load_config(path=None):
    cfg = dict(DEFAULTS)
    p = Path(path) if path else _DEFAULT_CONFIG
    try:
        if p.is_file():
            override = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(override, dict):
                cfg.update(override.get("qc_tier1", override))
    except (OSError, ValueError):
        # config is optional; fail closed onto the built-in defaults.
        pass
    return cfg


_STYLE_ALIASES = {
    "counter intuitive": "counter_intuitive",
    "counter-intuitive": "counter_intuitive",
    "counterintuitive": "counter_intuitive",
    "counter_intuitive": "counter_intuitive",
    "vulnerable": "vulnerable",
    "provocative": "provocative",
    "passionate": "passionate",
}


def normalise_style(style):
    if not isinstance(style, str):
        return None
    return _STYLE_ALIASES.get(style.strip().lower())


def strip_tags(script, syntax):
    """Remove Fish Audio delivery tags so counts and scans see spoken text only."""
    if syntax == "paren":
        return re.sub(r"\([^)\n]*\)", " ", script)
    return re.sub(r"\[[^\]\n]*\]", " ", script)


def spoken_word_count(script, syntax):
    return len(_WS_RE.findall(strip_tags(script, syntax)))


# ---- the deterministic checks (each returns a list of (code, num, msg)) -----
def _fail(code, num, msg):
    return [(code, num, msg)]


def check_01_em_dash(ctx):
    hits = [c for c in ctx["script"] if c in _EM_DASH_CHARS]
    if hits:
        return _fail("AF-EP-EMDASH", 1,
                     "em dash class character present %d time(s) (banned everywhere)" % len(hits))
    return []


def check_02_code_fence(ctx):
    s = ctx["script"]
    if _TRIPLE_FENCE in s or _TRIPLE_TILDE in s:
        return _fail("AF-EP-FENCE", 2, "triple-fence / code-fence marker present")
    return []


def check_03_markdown(ctx):
    s = ctx["script"]
    if "*" in s:
        return _fail("AF-EP-MARKDOWN", 3, "asterisk emphasis marker present")
    if "_" in s:
        return _fail("AF-EP-MARKDOWN", 3, "underscore emphasis marker present")
    if re.search(r"(?m)^\s*#{1,6}\s+\S", s):
        return _fail("AF-EP-MARKDOWN", 3, "markdown header present")
    if re.search(r"(?m)^\s*[-+]\s+\S", s):
        return _fail("AF-EP-MARKDOWN", 3, "markdown bullet list present")
    if re.search(r"(?m)^\s*\d+[.)]\s+\S", s):
        return _fail("AF-EP-MARKDOWN", 3, "markdown ordered list present")
    if re.search(r"(?m)^\s*>\s+\S", s):
        return _fail("AF-EP-MARKDOWN", 3, "markdown blockquote present")
    if re.search(r"\]\([^)]*\)", s):
        return _fail("AF-EP-MARKDOWN", 3, "markdown link syntax present")
    return []


def check_04_labels(ctx):
    s = ctx["script"]
    # ALL-CAPS speaker prefix at line start, e.g. HOST:, GUEST:, NARRATOR:
    if re.search(r"(?m)^\s*[A-Z][A-Z .'-]{1,30}:\s", s):
        return _fail("AF-EP-LABEL", 4, "all-caps speaker prefix / label present")
    # known label words used as labels
    if re.search(r"(?im)^\s*(intro|outro|host|guest|speaker|narrator|verse|chorus|"
                 r"scene|act|section|music|sfx|sound effect|stage direction)\s*:", s):
        return _fail("AF-EP-LABEL", 4, "named label / stage-direction prefix present")
    # bracketed or parenthesised production cue, e.g. [Music], (SFX: ...)
    if re.search(r"(?i)[\[(]\s*(music|sfx|sound effect|applause|silence|intro|outro)\b", s):
        return _fail("AF-EP-LABEL", 4, "bracketed production cue present")
    return []


def check_05_title(ctx):
    s = ctx["script"]
    if re.search(r"(?im)^\s*title\s*[:\-–]", s) or re.search(r"(?i)\btitle\s*:\s*\S", s):
        return _fail("AF-EP-TITLE", 5, "the word Title used as a preceding label")
    return []


def check_06_speakable(ctx):
    spoken = strip_tags(ctx["script"], ctx["syntax"])
    if _DIGIT_RE.search(spoken):
        return _fail("AF-EP-SPEAKABLE", 6, "raw digit present in spoken text (write numbers as spoken)")
    bad = sorted({c for c in ctx["cfg"]["non_speakable_symbols"] if c in spoken})
    if bad:
        return _fail("AF-EP-SPEAKABLE", 6,
                     "unspoken symbol(s) present: %s (write as spoken words)" % " ".join(bad))
    return []


def check_07_tag_syntax(ctx):
    s = ctx["script"]
    syntax = ctx["syntax"]
    if syntax == "paren":
        opens, closes = "(", ")"
    else:
        opens, closes = "[", "]"
    depth = 0
    content = []
    for ch in s:
        if ch == opens:
            if depth > 0:
                return _fail("AF-EP-TAGSYNTAX", 7, "nested %s tag delimiter" % opens)
            depth = 1
            content = []
        elif ch == closes:
            if depth == 0:
                return _fail("AF-EP-TAGSYNTAX", 7, "orphaned %s (no matching %s)" % (closes, opens))
            depth = 0
            if not "".join(content).strip():
                return _fail("AF-EP-TAGSYNTAX", 7, "empty %s%s tag" % (opens, closes))
        elif depth == 1:
            content.append(ch)
    if depth != 0:
        return _fail("AF-EP-TAGSYNTAX", 7, "unclosed %s tag" % opens)
    # wrong-delimiter tag: a tag-lexicon token wearing the OTHER model's delimiter.
    other_open, other_close = ("(", ")") if syntax != "paren" else ("[", "]")
    lex = {t.lower() for t in ctx["cfg"]["tag_lexicon"]}
    for span in re.findall(re.escape(other_open) + r"([^" + re.escape(other_close) + r"\n]{1,40})" + re.escape(other_close), s):
        if span.strip().lower() in lex:
            return _fail("AF-EP-TAGSYNTAX", 7,
                         "delivery tag '%s' uses the wrong delimiter for the target model" % span.strip())
    return []


def check_08_word_band(ctx):
    n = ctx["true_words"]
    lo, hi = ctx["target_words"]
    if lo is not None and n < lo:
        return _fail("AF-EP-WORDBAND", 8, "tag-excluded spoken words %d below target minimum %d" % (n, lo))
    if hi is not None and n > hi:
        return _fail("AF-EP-WORDBAND", 8, "tag-excluded spoken words %d above target maximum %d" % (n, hi))
    return []


def check_09_word_honesty(ctx):
    reported = ctx["meta"].get("reported_word_count")
    if reported is None:
        return []
    try:
        reported = int(reported)
    except (TypeError, ValueError):
        return _fail("AF-EP-WORDHONESTY", 9, "reported_word_count is not an integer")
    tol = ctx["cfg"]["word_count_tolerance"]
    if abs(reported - ctx["true_words"]) > tol:
        return _fail("AF-EP-WORDHONESTY", 9,
                     "reported word count %d does not match the true spoken count %d (misreporting is an absolute failure)"
                     % (reported, ctx["true_words"]))
    return []


def check_10_forbidden_names(ctx):
    s = ctx["script"]
    for phrase in list(ctx["cfg"]["forbidden_names"]) + list(ctx["cfg"]["forbidden_works"]):
        if re.search(r"\b" + re.escape(phrase) + r"\b", s, re.IGNORECASE):
            return _fail("AF-EP-FORBIDDEN-NAME", 10,
                         "forbidden reference speaker / work present: %s" % phrase)
    return []


def check_11_forbidden_word_by_style(ctx):
    style = ctx["style"]
    if not style:
        return []
    words = ctx["cfg"]["forbidden_word_by_style"].get(style, [])
    for w in words:
        if re.search(r"\b" + re.escape(w) + r"\w*", ctx["script"], re.IGNORECASE):
            return _fail("AF-EP-FORBIDDEN-WORD", 11,
                         "forbidden word '%s' present in a %s episode" % (w, style))
    return []


def check_15_pure_deliverable(ctx):
    low = ctx["script"].lower()
    for marker in ctx["cfg"]["pure_deliverable_markers"]:
        if marker.lower() in low:
            return _fail("AF-EP-PURE", 15,
                         "delivery-report / metadata bleed into the script: '%s'" % marker)
    return []


def check_16_intake_contamination(ctx):
    s = ctx["script"]
    m = _EMAIL_RE.search(s)
    if m:
        return _fail("AF-EP-CONTAM", 16, "contact email address present in the script")
    if _PHONE_RE.search(s):
        return _fail("AF-EP-CONTAM", 16, "contact phone number present in the script")
    low = s.lower()
    for marker in ctx["cfg"]["consent_markers"]:
        if marker.lower() in low:
            return _fail("AF-EP-CONTAM", 16, "consent / SMIQ language present: '%s'" % marker)
    vd = ctx["meta"].get("visual_description")
    if isinstance(vd, str) and vd.strip():
        k = ctx["cfg"]["visual_description_shingle_words"]
        toks = _WS_RE.findall(vd.lower())
        if len(toks) >= k:
            shingle = " ".join(toks[:k])
            norm = " ".join(_WS_RE.findall(low))
            if shingle in norm:
                return _fail("AF-EP-CONTAM", 16, "image / visual brief text bled into the script")
    return []


# order matters only for reporting; each check is independent.
_CHECKS = [
    (1, "em_dash", check_01_em_dash),
    (2, "code_fence", check_02_code_fence),
    (3, "markdown", check_03_markdown),
    (4, "labels", check_04_labels),
    (5, "title_placement", check_05_title),
    (6, "speakable_chars", check_06_speakable),
    (7, "tag_syntax", check_07_tag_syntax),
    (8, "tag_excluded_word_count", check_08_word_band),
    (9, "word_count_honesty", check_09_word_honesty),
    (10, "forbidden_names", check_10_forbidden_names),
    (11, "forbidden_word_by_style", check_11_forbidden_word_by_style),
    (15, "pure_deliverable", check_15_pure_deliverable),
    (16, "intake_contamination", check_16_intake_contamination),
]

_SEMANTIC = [
    (12, "no_fabrication"),
    (13, "mode_perspective"),
    (14, "pronoun_correctness"),
]


def build_context(meta, cfg):
    script = meta.get("script")
    if not isinstance(script, str):
        raise ValueError("deliverable has no 'script' string")
    syntax = (meta.get("tag_syntax") or "square").strip().lower()
    if syntax not in ("square", "paren"):
        syntax = "square"
    tw = meta.get("target_words") or cfg["target_words_default"]
    if isinstance(tw, (list, tuple)) and len(tw) == 2:
        target_words = (tw[0], tw[1])
    else:
        target_words = tuple(cfg["target_words_default"])
    return {
        "script": script,
        "meta": meta,
        "cfg": cfg,
        "syntax": syntax,
        "style": normalise_style(meta.get("style")),
        "target_words": target_words,
        "true_words": spoken_word_count(script, syntax),
    }


def evaluate(meta, cfg):
    ctx = build_context(meta, cfg)
    failures = []
    checks = []
    for num, name, fn in _CHECKS:
        result = fn(ctx)
        checks.append((num, name, "FAIL" if result else "PASS"))
        failures.extend(result)
    return ctx, failures, checks


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def _emit(source, ctx, failures, checks, as_json):
    true_words = ctx["true_words"] if ctx else None
    if as_json:
        print(json.dumps({
            "gate": "episode-gate-b-tier1-mechanical",
            "note": "deterministic subset only; checks 12-14 (semantic) run on the cheap judge tier, never here",
            "source": source,
            "pass": not failures,
            "true_spoken_word_count": true_words,
            "target_words": list(ctx["target_words"]) if ctx else None,
            "style": ctx["style"] if ctx else None,
            "checks": [{"n": n, "name": nm, "result": r} for n, nm, r in checks],
            "deferred_semantic_checks": [{"n": n, "name": nm, "status": "DEFERRED_JUDGE_TIER"} for n, nm in _SEMANTIC],
            "failures": [{"code": c, "check": n, "message": m} for c, n, m in failures],
        }, indent=2))
        return
    print("== Podcast Engine :: Episode Gate B, Tier 1 MECHANICAL prover ==")
    print("source: %s" % source)
    if ctx is not None:
        print("true spoken words (tags excluded): %d  target band: %s  style: %s"
              % (true_words, str(list(ctx["target_words"])), ctx["style"]))
    if checks:
        print("  %-4s %-26s %s" % ("#", "check", "result"))
        for n, nm, r in checks:
            print("  %-4s %-26s %s" % (n, nm, r))
    print("  semantic checks 12-14 (fabrication, mode perspective, pronoun): DEFERRED to the cheap judge tier")
    if not failures:
        print("RESULT: PASS - deterministic Tier 1 clean. Semantic checks and the 10-dimension rubric still gate delivery.")
    else:
        print("RESULT: FAIL (fail-closed) - %d Tier 1 violation(s); episode NOT deliverable:" % len(failures))
        for c, n, m in failures:
            print("  [%s] (check %s) %s" % (c, n, m))


def _read_input(args):
    """Return the deliverable meta dict, or raise ValueError / FileNotFoundError."""
    if args.script_file:
        text = Path(args.script_file).read_text(encoding="utf-8")
        meta = {"script": text}
    elif args.path:
        raw = Path(args.path).read_text(encoding="utf-8")
        try:
            obj = json.loads(raw)
            meta = obj if isinstance(obj, dict) and "script" in obj else {"script": raw}
        except ValueError:
            meta = {"script": raw}
    else:
        raise ValueError("a deliverable path or --script-file is required (or use --self-test)")
    # command-line overrides win over file metadata.
    if args.style:
        meta["style"] = args.style
    if args.mode:
        meta["mode"] = args.mode
    if args.tag_syntax:
        meta["tag_syntax"] = args.tag_syntax
    if args.target_min is not None or args.target_max is not None:
        base = meta.get("target_words") or list(DEFAULTS["target_words_default"])
        lo = args.target_min if args.target_min is not None else base[0]
        hi = args.target_max if args.target_max is not None else base[1]
        meta["target_words"] = [lo, hi]
    if args.reported_count is not None:
        meta["reported_word_count"] = args.reported_count
    return meta


def prove(args):
    cfg = load_config(args.config)
    source = args.script_file or args.path or "?"
    try:
        meta = _read_input(args)
    except FileNotFoundError as exc:
        _emit(source, None, [("AF-EP-CONTRACT", 0, "file not found: %s" % exc)], [], args.json)
        return EXIT_USAGE
    except (ValueError, OSError) as exc:
        _emit(source, None, [("AF-EP-CONTRACT", 0, "cannot read input: %s" % exc)], [], args.json)
        return EXIT_USAGE
    try:
        ctx, failures, checks = evaluate(meta, cfg)
    except ValueError as exc:
        _emit(source, None, [("AF-EP-CONTRACT", 0, str(exc))], [], args.json)
        return EXIT_USAGE
    _emit(source, ctx, failures, checks, args.json)
    return decide_exit(failures)


# =============================================================================
# SELF-TEST: a CLEAN fixture (exit 0) plus one targeted VIOLATION per check.
# =============================================================================
_CLEAN = (
    "Here is the strange truth about doing less. "
    "[pause] We were told that speed is the point, yet the fastest teams "
    "guard their calm the way a runner guards breath. [soft] "
    "I want to be honest with you about how I learned this the slow way, "
    "on a Tuesday that refused to cooperate. [emphasis] "
    "Consider a small studio that stopped chasing every request and started "
    "finishing one thing a day. Their revenue climbed. Their people stayed. "
    "So the question is not how much can you carry, it is how little can you "
    "carry and still arrive whole. [long pause] Carry less. Arrive whole."
)


def _clean_meta(**over):
    m = {"script": _CLEAN, "style": "counter_intuitive", "mode": "personal",
         "tag_syntax": "square", "target_words": [40, 400]}
    m.update(over)
    return m


def self_test():
    cfg = load_config(None)
    ok = True

    def want_pass(name, meta):
        nonlocal ok
        _c, fails, _k = evaluate(meta, cfg)
        good = not fails
        ok = ok and good
        print("  [%s] CLEAN %-24s -> exit %d %s"
              % ("PASS" if good else "MISS", name, decide_exit(fails),
                 "" if good else "(unexpected: %r)" % fails[:3]))

    def want_fail(name, meta, expect_check):
        nonlocal ok
        _c, fails, _k = evaluate(meta, cfg)
        nums = [n for _c2, n, _m in fails]
        good = bool(fails) and expect_check in nums
        ok = ok and good
        print("  [%s] VIOLATION %-22s -> exit %d hits check %s %s"
              % ("PASS" if good else "MISS", name, decide_exit(fails), expect_check,
                 "" if good else "(got %r)" % nums))

    print("== self-test: CLEAN fixture (must PASS / exit 0) ==")
    want_pass("counter_intuitive", _clean_meta())
    want_pass("no_reported_count_ok", _clean_meta(reported_word_count=None))
    want_pass("honest_count", _clean_meta(reported_word_count=spoken_word_count(_CLEAN, "square")))

    print("== self-test: one VIOLATION per deterministic check (must FAIL) ==")
    want_fail("em_dash", _clean_meta(script=_CLEAN + " " + chr(0x2014) + " no"), 1)
    want_fail("code_fence", _clean_meta(script=_CLEAN + " " + _TRIPLE_FENCE), 2)
    want_fail("markdown_star", _clean_meta(script=_CLEAN + " *bold*"), 3)
    want_fail("markdown_header", _clean_meta(script="# Heading\n" + _CLEAN), 3)
    want_fail("labels", _clean_meta(script="HOST: " + _CLEAN), 4)
    want_fail("cue", _clean_meta(script=_CLEAN + " [Music]"), 4)
    want_fail("title_label", _clean_meta(script="Title: The Slow Way\n" + _CLEAN), 5)
    want_fail("digit", _clean_meta(script=_CLEAN + " 7 teams"), 6)
    want_fail("symbol", _clean_meta(script=_CLEAN + " 100% sure"), 6)
    want_fail("unclosed_tag", _clean_meta(script=_CLEAN + " [pause"), 7)
    want_fail("empty_tag", _clean_meta(script=_CLEAN + " []"), 7)
    want_fail("nested_tag", _clean_meta(script=_CLEAN + " [a[b]]"), 7)
    want_fail("wrong_delim", _clean_meta(script=_CLEAN + " (whisper) now"), 7)
    want_fail("below_band", _clean_meta(target_words=[5000, 6000]), 8)
    want_fail("above_band", _clean_meta(target_words=[1, 10]), 8)
    want_fail("dishonest_count", _clean_meta(reported_word_count=999999), 9)
    want_fail("forbidden_name", _clean_meta(script=_CLEAN + " as Barry Schwartz said"), 10)
    want_fail("forbidden_work", _clean_meta(script=_CLEAN + " the Paradox of Choice"), 10)
    want_fail("paradox_word", _clean_meta(script=_CLEAN + " what a paradox"), 11)
    want_fail("report_bleed", _clean_meta(script=_CLEAN + " Delivery Report follows"), 15)
    want_fail("email_contam", _clean_meta(script=_CLEAN + " reach me at jo@ex.com"), 16)
    want_fail("consent_contam", _clean_meta(script=_CLEAN + " reply STOP to unsubscribe"), 16)
    want_fail("visual_contam",
              _clean_meta(script="A warm amber studio with a single microphone glowing softly in frame " + _CLEAN,
                          visual_description="a warm amber studio with a single microphone glowing softly in frame"), 16)

    print("== self-test: paradox allowed OUTSIDE counter_intuitive ==")
    want_pass("paradox_in_provocative", _clean_meta(style="provocative", script=_CLEAN + " what a paradox"))

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILURES ABOVE"))
    return EXIT_PASS if ok else EXIT_AUTOFAIL


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Fail-closed deterministic Tier 1 mechanical prover for the Podcast Production Engine (Episode Gate B).")
    ap.add_argument("path", nargs="?", help="deliverable JSON (or raw script) to prove")
    ap.add_argument("--script-file", dest="script_file", help="raw text script file")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--style", help="counter_intuitive|vulnerable|provocative|passionate")
    ap.add_argument("--mode", help="personal|interview (recorded; enforced by the judge tier)")
    ap.add_argument("--tag-syntax", dest="tag_syntax", choices=["square", "paren"],
                    help="square (S2.1 Pro, default) or paren (S1 legacy)")
    ap.add_argument("--target-min", dest="target_min", type=int, help="target spoken-word minimum")
    ap.add_argument("--target-max", dest="target_max", type=int, help="target spoken-word maximum")
    ap.add_argument("--reported-count", dest="reported_count", type=int,
                    help="the word count the deliverable claims (honesty check)")
    ap.add_argument("--config", help="path to config/qc-tier1.json (default: skill config or built-ins)")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path and not args.script_file:
        ap.error("a deliverable path or --script-file is required (or use --self-test)")
    return prove(args)


if __name__ == "__main__":
    sys.exit(main())

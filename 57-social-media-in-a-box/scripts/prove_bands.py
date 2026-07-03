#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: THE SACRED-BANDS FLOOR PROVER
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED prover (Python stdlib only). Cloned in
# spirit from the Presentations deterministic stripped-length prover pattern
# (build_deck.py) and Skill 50's prove-email.py. Every SACRED band below is
# fail-closed — a violating asset is NOT accepted and NOT unlocked for the
# publisher. A violation is sys.exit(2) with a named AF-SM-* code. No network,
# no model judgement, no third-party imports. It runs identically on every box
# (operator or client); it never touches a provider.
#
# SINGLE SOURCE OF TRUTH: config/bands.json. This prover READS the numbers from
# that file — it never hardcodes them — so the bands and the prover can never
# drift. Bands are the DEFAULT floor; a logged client-exact override is honored
# via a per-asset "band_override": [lo, hi] and recorded on the certificate.
#
# INPUT SHAPES (auto-detected; forced with --kind):
#   * carousel   — {platform, carouselCaption, pdfTitle?, slides:[{textOnImage,
#                   prompt}], images_ready?, hashtags?}
#   * series     — {days:[{body, imageprompt, followupcomment}]}  (7-part)
#   * reformat   — {instagram:{post, followUpComment, hashtags?},
#                   linkedin:{post, followUpComment, hashtags?}}
#   * storyboard — {scenes:[{Scene, duration}]}  (or a bare JSON array)
#   * post       — {platform, body, hashtags?}
#
# EXIT CODES:
#   0  PASS      — every SACRED band satisfied (per-field PASS table printed).
#   2  AUTOFAIL  — one or more AF-SM-* band violations.
#   3  USAGE/IO  — missing file / unreadable-invalid JSON (still fail-closed).
#
# USAGE:
#   python3 prove_bands.py <asset.json> [--json] [--kind K] [--bands PATH]
#   python3 prove_bands.py --self-test
# =============================================================================
"""Fail-closed deterministic SACRED-bands prover for Social Media in a Box (Skill 57)."""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

_SKILL_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_BANDS = _SKILL_DIR / "config" / "bands.json"

_WORD_RE = re.compile(r"[^\s]+")
_HASHTAG_RE = re.compile(r"(?<!\w)#\w[\w]*")


def _load_bands(path):
    try:
        obj = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SystemExit("FATAL: cannot read bands file %s: %s" % (path, exc))
    return obj.get("bands", obj)


def _chars(text):
    """Raw character length of the field value (the band is 'characters total')."""
    return len(text if isinstance(text, str) else "")


def _words(text):
    return len(_WORD_RE.findall(text if isinstance(text, str) else ""))


def _count_hashtags(rec, text_field):
    """Prefer an explicit hashtags[] list; else count #tokens in the text field."""
    ht = rec.get("hashtags")
    if isinstance(ht, list):
        return len([h for h in ht if isinstance(h, str) and h.strip()])
    return len(_HASHTAG_RE.findall(rec.get(text_field) or ""))


def _band(bands, key):
    b = bands.get(key)
    if not isinstance(b, dict):
        raise SystemExit("FATAL: bands.json missing band %r" % key)
    return b


def _chk_range(val, lo, hi):
    if lo is not None and val < lo:
        return False
    if hi is not None and val > hi:
        return False
    return True


# ---- R1 uniform override resolution (all five evaluators) -------------------
# Every band is the DEFAULT floor; a logged client-exact override wins and is
# recorded on the certificate. This resolver is the single place override
# precedence is decided: run-level rec["overrides"][band_key] > legacy
# rec["band_override"] (post body only) > the default band bounds. Config-level
# overrides (client bandOverrides) are merged INTO rec["overrides"] by the
# orchestrator before proving. A client-exact number is NEVER floored or capped
# here (that guarantee is honored at intake); the prover only measures against
# whichever bound applies and reports whether an override was in force so
# AF-SM-OVERRIDE-UNLOGGED can require it be logged.
def _band_bounds(band):
    if "exact" in band:
        return band["exact"], band["exact"]
    return band.get("min"), band.get("max")


def _spec_bounds(spec, d_lo, d_hi):
    if isinstance(spec, list) and len(spec) == 2:
        return spec[0], spec[1]
    if isinstance(spec, dict):
        if "exact" in spec:
            return spec["exact"], spec["exact"]
        return spec.get("min", d_lo), spec.get("max", d_hi)
    return d_lo, d_hi


def _resolve(rec, key, band, extra_spec=None):
    """Return (lo, hi, overridden). extra_spec lets an evaluator pass a
    field-specific override channel (e.g. hashtagPolicy for hashtag bands)."""
    d_lo, d_hi = _band_bounds(band)
    ov = rec.get("overrides")
    spec = ov.get(key) if isinstance(ov, dict) else None
    if spec is None and extra_spec is not None:
        spec = extra_spec
    if spec is None and key == "post_body_words":
        bo = rec.get("band_override")
        if isinstance(bo, list) and len(bo) == 2:
            spec = bo
    if spec is not None:
        lo, hi = _spec_bounds(spec, d_lo, d_hi)
        return lo, hi, True
    return d_lo, d_hi, False


# ---- per-kind evaluation ----------------------------------------------------
def evaluate_carousel(rec, bands):
    fails, checks = [], []
    platform = str(rec.get("platform", "")).lower()
    is_li = platform == "linkedin"

    cap_key = "caption_linkedin" if is_li else "caption_fb_ig"
    cap_band = _band(bands, cap_key)
    cap = rec.get("carouselCaption") or ""
    n = _chars(cap)
    lo, hi, ovr = _resolve(rec, cap_key, cap_band)
    ok = _chk_range(n, lo, hi)
    checks.append(("caption chars", n, "%s-%s%s" % (lo, hi, "*" if ovr else ""), ok))
    if not ok:
        fails.append((cap_band["af"], "carouselCaption is %d chars, outside %s-%s (%s)"
                      % (n, lo, hi, platform)))

    ht_key = "hashtags_linkedin" if is_li else "hashtags_fb_ig"
    ht_band = _band(bands, ht_key)
    ht = _count_hashtags(rec, "carouselCaption")
    lo, hi, ovr = _resolve(rec, ht_key, ht_band, extra_spec=rec.get("hashtagPolicy"))
    ok = _chk_range(ht, lo, hi)
    want = "%s-%s%s" % (lo, hi, "*" if ovr else "")
    checks.append(("hashtags", ht, want, ok))
    if not ok:
        fails.append((ht_band["af"], "%d hashtags, want %s (%s)" % (ht, want, platform)))

    if is_li:
        pt_band = _band(bands, "pdf_title")
        pt = _chars(rec.get("pdfTitle") or "")
        lo, hi, _ = _resolve(rec, "pdf_title", pt_band)
        ok = _chk_range(pt, lo, hi)
        checks.append(("pdfTitle chars", pt, "<=%s" % hi, ok))
        if not ok:
            fails.append((pt_band["af"], "pdfTitle is %d chars, over %s" % (pt, hi)))

    slides = rec.get("slides")
    slide_key = "carousel_slides_linkedin" if is_li else "carousel_slides_fb_ig"
    slide_band = _band(bands, slide_key)
    nslides = len(slides) if isinstance(slides, list) else -1
    floor = _band(bands, "carousel_assemble_floor")["min"]  # R2: real assembly floor
    s_lo, s_hi, s_ovr = _resolve(rec, slide_key, slide_band)
    if s_ovr:
        # R2: client-exact slide-count override accepted within floor 2 .. platform max.
        if s_lo < floor or s_hi < floor:
            ok = False
            fails.append(("AF-SM-CAROUSEL-FLOOR", "slide-count override %s-%s below assembly floor %d"
                          % (s_lo, s_hi, floor)))
        else:
            ok = _chk_range(nslides, s_lo, s_hi)
        want = "%s-%s* (floor %d)" % (s_lo, s_hi, floor)
    else:
        ok = nslides == slide_band["exact"]
        want = "exactly %d" % slide_band["exact"]
    checks.append(("slide count", nslides, want, ok))
    if not ok and s_ovr and _chk_range(nslides, s_lo, s_hi):
        pass  # floor failure already recorded above
    elif not ok:
        fails.append((slide_band["af"], "%d slides, need %s (%s)" % (nslides, want, platform)))

    hw_band = _band(bands, "headline_words")
    ip_band = _band(bands, "image_prompt_carousel")
    hw_lo, hw_hi, _ = _resolve(rec, "headline_words", hw_band)
    ip_lo, ip_hi, _ = _resolve(rec, "image_prompt_carousel", ip_band)
    if isinstance(slides, list):
        for i, s in enumerate(slides, 1):
            if not isinstance(s, dict):
                fails.append((slide_band["af"], "slide %d is not an object" % i))
                continue
            w = _words(s.get("textOnImage") or "")
            if not _chk_range(w, hw_lo, hw_hi):
                fails.append((hw_band["af"], "slide %d textOnImage is %d words, over %s"
                              % (i, w, hw_hi)))
            c = _chars(s.get("prompt") or "")
            if not _chk_range(c, ip_lo, ip_hi):
                fails.append((ip_band["af"], "slide %d image prompt is %d chars, outside %s-%s"
                              % (i, c, ip_lo, ip_hi)))

    if "images_ready" in rec:
        floor = _band(bands, "carousel_assemble_floor")
        ir = rec.get("images_ready")
        ir = ir if isinstance(ir, int) else -1
        ok = ir >= floor["min"]
        checks.append(("images ready", ir, ">=%d" % floor["min"], ok))
        if not ok:
            fails.append((floor["af"], "%d images ready, assembly floor is %d" % (ir, floor["min"])))

    return fails, checks


def evaluate_series(rec, bands):
    fails, checks = [], []
    days = rec.get("days")
    if not isinstance(days, list) or not days:
        return [("AF-SM-CONTENT-MISSING", "series has no days[] array")], checks
    body_band = _band(bands, "post_body_words")
    ip_band = _band(bands, "image_prompt_series")
    fu_band = _band(bands, "followup_series")
    # R1: uniform override across the series evaluator (body words, image prompt, followUp).
    b_lo, b_hi, _ = _resolve(rec, "post_body_words", body_band)
    ip_lo, ip_hi, _ = _resolve(rec, "image_prompt_series", ip_band)
    fu_lo, fu_hi, _ = _resolve(rec, "followup_series", fu_band)
    worst_body, worst_ip, worst_fu = 10 ** 9, 10 ** 9, 0
    for i, d in enumerate(days, 1):
        if not isinstance(d, dict):
            fails.append(("AF-SM-CONTENT-MISSING", "day %d is not an object" % i))
            continue
        w = _words(d.get("body") or "")
        worst_body = min(worst_body, w)
        if not _chk_range(w, b_lo, b_hi):
            fails.append((body_band["af"], "day %d body is %d words, outside %s-%s" % (i, w, b_lo, b_hi)))
        c = _chars(d.get("imageprompt") or "")
        worst_ip = min(worst_ip, c)
        if not _chk_range(c, ip_lo, ip_hi):
            fails.append((ip_band["af"], "day %d imageprompt is %d chars, under %s" % (i, c, ip_lo)))
        f = _chars(d.get("followupcomment") or "")
        worst_fu = max(worst_fu, f)
        if not _chk_range(f, fu_lo, fu_hi):
            fails.append((fu_band["af"], "day %d followupcomment is %d chars, over %s" % (i, f, fu_hi)))
    checks.append(("min body words", worst_body, ">=%s" % b_lo, _chk_range(worst_body, b_lo, None)))
    checks.append(("min imageprompt chars", worst_ip, ">=%s" % ip_lo, _chk_range(worst_ip, ip_lo, None)))
    checks.append(("max followup chars", worst_fu, "<=%s" % fu_hi, _chk_range(worst_fu, None, fu_hi)))
    return fails, checks


def evaluate_reformat(rec, bands):
    fails, checks = [], []
    fu_band = _band(bands, "followup_reformatter")
    fu_lo, fu_hi, _ = _resolve(rec, "followup_reformatter", fu_band)
    # R3: per-platform hashtagPolicy map on the reformat record, e.g. {"linkedin":[0,0]}.
    hp = rec.get("hashtagPolicy") if isinstance(rec.get("hashtagPolicy"), dict) else {}
    ig = rec.get("instagram")
    if isinstance(ig, dict):
        ht_band = _band(bands, "hashtags_ig_reformat")
        ht = _count_hashtags(ig, "post")
        lo, hi, ovr = _resolve(rec, "hashtags_ig_reformat", ht_band, extra_spec=hp.get("instagram"))
        ok = _chk_range(ht, lo, hi)
        checks.append(("ig hashtags", ht, "%s-%s%s" % (lo, hi, "*" if ovr else ""), ok))
        if not ok:
            fails.append((ht_band["af"], "instagram %d hashtags, want %s-%s" % (ht, lo, hi)))
        f = _chars(ig.get("followUpComment") or "")
        ok = _chk_range(f, fu_lo, fu_hi)
        checks.append(("ig followUp chars", f, "<=%s" % fu_hi, ok))
        if not ok:
            fails.append((fu_band["af"], "instagram followUpComment is %d chars, over %s" % (f, fu_hi)))
    li = rec.get("linkedin")
    if isinstance(li, dict):
        ht_band = _band(bands, "hashtags_linkedin")
        ht = _count_hashtags(li, "post")
        lo, hi, ovr = _resolve(rec, "hashtags_linkedin", ht_band, extra_spec=hp.get("linkedin"))
        ok = _chk_range(ht, lo, hi)
        checks.append(("li hashtags", ht, "%s-%s%s" % (lo, hi, "*" if ovr else ""), ok))
        if not ok:
            fails.append((ht_band["af"], "linkedin %d hashtags, want %s-%s" % (ht, lo, hi)))
        f = _chars(li.get("followUpComment") or "")
        ok = _chk_range(f, fu_lo, fu_hi)
        checks.append(("li followUp chars", f, "<=%s" % fu_hi, ok))
        if not ok:
            fails.append((fu_band["af"], "linkedin followUpComment is %d chars, over %s" % (f, fu_hi)))
    # C7: FB/IG Stories caption band (content-completeness fold), when present.
    sc = rec.get("storiesCaption")
    if isinstance(sc, str):
        sc_band = _band(bands, "stories_caption")
        lo, hi, _ = _resolve(rec, "stories_caption", sc_band)
        n = _chars(sc)
        ok = _chk_range(n, lo, hi)
        checks.append(("stories caption chars", n, "<=%s" % hi, ok))
        if not ok:
            fails.append((sc_band["af"], "storiesCaption is %d chars, over %s" % (n, hi)))
    return fails, checks


def evaluate_storyboard(rec, bands):
    fails, checks = [], []
    scenes = rec if isinstance(rec, list) else rec.get("scenes")
    obj = rec if isinstance(rec, dict) else {}
    sc_band = _band(bands, "storyboard_scenes")
    sec_band = _band(bands, "storyboard_seconds")
    n = len(scenes) if isinstance(scenes, list) else -1
    sc_lo, sc_hi, _ = _resolve(obj, "storyboard_scenes", sc_band)
    ok = _chk_range(n, sc_lo, sc_hi)
    checks.append(("scene count", n, "%s-%s" % (sc_lo, sc_hi), ok))
    if not ok:
        fails.append((sc_band["af"], "%d scenes, want %s-%s" % (n, sc_lo, sc_hi)))
    total = 0.0
    if isinstance(scenes, list):
        for i, s in enumerate(scenes, 1):
            dur = s.get("duration") if isinstance(s, dict) else None
            if not isinstance(dur, (int, float)):
                fails.append((sc_band["af"], "scene %d has no numeric duration" % i))
            else:
                total += float(dur)
    # R6: 25.0s is the Sora lane's real API constraint (kept). A client-exact
    # override (overrides.storyboard_seconds) opens the non-Sora creative-video
    # lane; default stays EXACTLY 25.0s.
    sec_lo, sec_hi, sec_ovr = _resolve(obj, "storyboard_seconds", sec_band)
    if sec_ovr:
        ok = _chk_range(total, sec_lo, sec_hi)
        checks.append(("total seconds", round(total, 3), "%s-%s*" % (sec_lo, sec_hi), ok))
        if not ok:
            fails.append((sec_band["af"], "durations sum to %.3fs, outside override %s-%s" % (total, sec_lo, sec_hi)))
    else:
        want = float(sec_band["exact"])
        tol = float(sec_band.get("tolerance", 0.0))
        ok = abs(total - want) <= tol
        checks.append(("total seconds", round(total, 3), "== %.1f" % want, ok))
        if not ok:
            fails.append((sec_band["af"], "durations sum to %.3fs, must be EXACTLY %.1fs" % (total, want)))
    return fails, checks


def evaluate_post(rec, bands):
    fails, checks = [], []
    band = _band(bands, "post_body_words")
    lo, hi, ovr = _resolve(rec, "post_body_words", band)
    note = ("client-exact override %s-%s" % (lo, hi)) if ovr else ("default >=%s" % lo)
    w = _words(rec.get("body") or "")
    ok = _chk_range(w, lo, hi)
    checks.append(("body words", w, note, ok))
    if not ok:
        fails.append((band["af"], "post body is %d words, outside %s" % (w, note)))
    return fails, checks


def evaluate_podcast(rec, bands):
    """C3 podcast fold. Measures the fold artifact's declared ffprobe/cover numbers
    against the SACRED podcast bands (mirrors how carousel uses images_ready).
    Fish-Audio/Podbean unconfigured -> the mode emits {"deferred": true} and the
    orchestrator records PODCAST_DEFERRED (a labeled skip, never a band failure)."""
    fails, checks = [], []
    if rec.get("deferred") is True:
        checks.append(("podcast", "PODCAST_DEFERRED", "graceful skip", True))
        return fails, checks
    for key, field, label in (("podcast_script_words", "scriptWords", "script words"),
                              ("podcast_duration_seconds", "durationSeconds", "duration s"),
                              ("podcast_bitrate_kbps", "bitrateKbps", "bitrate kbps")):
        band = _band(bands, key)
        v = rec.get(field)
        lo, hi, _ = _resolve(rec, key, band)
        num = v if isinstance(v, (int, float)) else -1
        ok = isinstance(v, (int, float)) and _chk_range(num, lo, hi)
        checks.append((label, num, "%s-%s" % (lo, hi), ok))
        if not ok:
            fails.append((band["af"], "%s is %s, outside %s-%s" % (label, v, lo, hi)))
    tag = rec.get("minTagsPerParagraph")
    tband = _band(bands, "podcast_tag_density")
    ok = isinstance(tag, (int, float)) and tag >= tband["min"]
    checks.append(("min [emotion] tags/paragraph", tag, ">=%d" % tband["min"], ok))
    if not ok:
        fails.append((tband["af"], "min [emotion] tags per paragraph is %s, need >=%d" % (tag, tband["min"])))
    cband = _band(bands, "podcast_cover_px")
    cw, ch = rec.get("coverWidth"), rec.get("coverHeight")
    ok = cw == cband["exact"] and ch == cband["exact"]
    checks.append(("cover px", "%sx%s" % (cw, ch), "%dx%d" % (cband["exact"], cband["exact"]), ok))
    if not ok:
        fails.append((cband["af"], "cover is %sx%s, need %dx%d JPEG"
                      % (cw, ch, cband["exact"], cband["exact"])))
    return fails, checks


def evaluate_newsletter(rec, bands):
    """C4 newsletter fold. Subject <=60 / preview <=120 (client-overridable, logged)."""
    fails, checks = [], []
    for key, field, label in (("email_subject", "subject", "subject chars"),
                              ("email_preview", "preview", "preview chars")):
        band = _band(bands, key)
        lo, hi, _ = _resolve(rec, key, band)
        n = _chars(rec.get(field) or "")
        ok = _chk_range(n, lo, hi)
        checks.append((label, n, "%s-%s" % (lo, hi), ok))
        if not ok:
            fails.append((band["af"], "%s is %d, outside %s-%s" % (label, n, lo, hi)))
    if not (rec.get("html") or "").strip():
        fails.append(("AF-SM-EMAIL-HTML", "newsletter missing table-based inline-CSS html body"))
        checks.append(("html body", "missing", "present", False))
    else:
        checks.append(("html body", "present", "present", True))
    return fails, checks


def evaluate_blog(rec, bands):
    """C5 blog fold. Title <=80 / meta <=160 / body 700+ words (client-overridable)."""
    fails, checks = [], []
    band = _band(bands, "blog_title")
    lo, hi, _ = _resolve(rec, "blog_title", band)
    n = _chars(rec.get("title") or "")
    ok = _chk_range(n, lo, hi)
    checks.append(("title chars", n, "%s-%s" % (lo, hi), ok))
    if not ok:
        fails.append((band["af"], "blog title is %d chars, outside %s-%s" % (n, lo, hi)))
    band = _band(bands, "blog_meta")
    lo, hi, _ = _resolve(rec, "blog_meta", band)
    n = _chars(rec.get("metaDescription") or "")
    ok = _chk_range(n, lo, hi)
    checks.append(("meta chars", n, "<=%s" % hi, ok))
    if not ok:
        fails.append((band["af"], "blog metaDescription is %d chars, over %s" % (n, hi)))
    band = _band(bands, "blog_body_words")
    lo, hi, _ = _resolve(rec, "blog_body_words", band)
    w = _words(rec.get("body") or "")
    ok = _chk_range(w, lo, hi)
    checks.append(("body words", w, ">=%s" % lo, ok))
    if not ok:
        fails.append((band["af"], "blog body is %d words, under %s" % (w, lo)))
    return fails, checks


def _detect_kind(obj):
    if isinstance(obj, list):
        return "storyboard"
    if not isinstance(obj, dict):
        return "post"
    if obj.get("kind"):
        return obj["kind"]
    if "slides" in obj:
        return "carousel"
    if "days" in obj:
        return "series"
    if "scenes" in obj:
        return "storyboard"
    if "durationSeconds" in obj or "scriptWords" in obj or obj.get("deferred") is True:
        return "podcast"
    if "subject" in obj and "preview" in obj:
        return "newsletter"
    if "metaDescription" in obj or ("title" in obj and "body" in obj):
        return "blog"
    if "instagram" in obj or "linkedin" in obj:
        return "reformat"
    return "post"


_EVALUATORS = {
    "carousel": evaluate_carousel, "series": evaluate_series,
    "reformat": evaluate_reformat, "storyboard": evaluate_storyboard,
    "post": evaluate_post, "podcast": evaluate_podcast,
    "newsletter": evaluate_newsletter, "blog": evaluate_blog,
}


def evaluate(obj, bands, kind=None):
    k = kind or _detect_kind(obj)
    fn = _EVALUATORS.get(k, evaluate_post)
    return k, fn(obj, bands)


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def _emit(source, kind, failures, checks, as_json):
    if as_json:
        print(json.dumps({
            "gate": "social-media-bands-prover", "source": source, "kind": kind,
            "pass": not failures,
            "checks": [{"field": f, "value": v, "want": w, "ok": ok} for f, v, w, ok in checks],
            "failures": [{"code": c, "message": m} for c, m in failures],
        }, indent=2))
        return
    print("== Social Media in a Box :: SACRED-bands prover (kind=%s) ==" % kind)
    print("source: %s" % source)
    if checks:
        print("  %-22s %-12s %-14s %s" % ("field", "measured", "band", "result"))
        for f, v, w, ok in checks:
            print("  %-22s %-12s %-14s %s" % (f, v, w, "PASS" if ok else "FAIL"))
    if not failures:
        print("RESULT: PASS — every SACRED band satisfied.")
    else:
        print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
        for c, m in failures:
            print("  [%s] %s" % (c, m))


def prove(path, as_json=False, kind=None, bands_path=None):
    p = Path(path)
    if not p.is_file():
        _emit(str(p), "?", [("AF-SM-CONTRACT-JSON", "file not found: %s" % p)], [], as_json)
        return EXIT_USAGE
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (ValueError, OSError) as exc:
        _emit(str(p), "?", [("AF-SM-CONTRACT-JSON", "cannot read/parse JSON: %s" % exc)], [], as_json)
        return EXIT_USAGE
    bands = _load_bands(bands_path or _DEFAULT_BANDS)
    k, (failures, checks) = evaluate(obj, bands, kind=kind)
    _emit(str(p), k, failures, checks, as_json)
    return decide_exit(failures)


# =============================================================================
# SELF-TEST — built-in VALID (exit 0) + VIOLATION (exit nonzero) fixtures.
# =============================================================================
def _pad_chars(n):
    return "x" * n


def _pad_words(n):
    return " ".join(["word"] * n)


def _valid_fbig_carousel():
    return {
        "kind": "carousel", "platform": "facebook",
        "carouselCaption": _pad_chars(1600) + " #a #b #c #d #e",
        "slides": [{"textOnImage": "Hook line here", "prompt": _pad_chars(1200)} for _ in range(10)],
        "images_ready": 10,
    }


def _valid_linkedin_carousel():
    return {
        "kind": "carousel", "platform": "linkedin",
        "pdfTitle": "A Provocative Billboard Headline That Stops The Scroll Today",
        "carouselCaption": _pad_chars(1700) + " #one #two #three",
        "slides": [{"textOnImage": "Short headline", "prompt": _pad_chars(1300)} for _ in range(9)],
    }


def _valid_series():
    return {"kind": "series", "days": [
        {"body": _pad_words(320), "imageprompt": _pad_chars(1900), "followupcomment": _pad_chars(400)}
        for _ in range(7)]}


def _valid_reformat():
    return {"kind": "reformat",
            "instagram": {"post": "hook " + " ".join("#h%d" % i for i in range(8)), "followUpComment": _pad_chars(300)},
            "linkedin": {"post": "hook #one #two #three", "followUpComment": _pad_chars(300)}}


def _valid_storyboard():
    return {"kind": "storyboard", "scenes": [
        {"Scene": "a", "duration": 5.0}, {"Scene": "b", "duration": 8.5},
        {"Scene": "c", "duration": 6.5}, {"Scene": "d", "duration": 5.0}]}


def _valid_podcast():
    return {"kind": "podcast", "scriptWords": 1750, "minTagsPerParagraph": 2,
            "durationSeconds": 720, "bitrateKbps": 192, "coverWidth": 1400, "coverHeight": 1400}


def _valid_newsletter():
    return {"kind": "newsletter", "subject": "Your week in 5 minutes",
            "preview": "The one shift that changed everything", "html": "<table>...</table>"}


def _valid_blog():
    return {"kind": "blog", "title": "Why your first 100 customers matter",
            "metaDescription": "A field guide to loyalty over reach.", "body": _pad_words(900)}


def self_test():
    bands = _load_bands(_DEFAULT_BANDS)
    ok = True

    def check_pass(name, fixture, kind=None):
        nonlocal ok
        _, (fails, _c) = evaluate(fixture, bands, kind=kind)
        good = not fails
        ok = ok and good
        print("  [%s] VALID %-26s -> exit %d %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), "" if good else ("(unexpected: %r)" % fails[:4])))

    def check_fail(name, fixture, expect, kind=None):
        nonlocal ok
        _, (fails, _c) = evaluate(fixture, bands, kind=kind)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print("  [%s] VIOLATION %-24s -> exit %d has %s %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), expect, "" if good else ("codes=%s" % codes)))

    print("== self-test: VALID fixtures (must PASS / exit 0) ==")
    check_pass("fbig-carousel", _valid_fbig_carousel())
    check_pass("linkedin-carousel", _valid_linkedin_carousel())
    check_pass("series-7part", _valid_series())
    check_pass("reformat", _valid_reformat())
    check_pass("storyboard-25s", _valid_storyboard())
    check_pass("podcast", _valid_podcast())
    check_pass("newsletter", _valid_newsletter())
    check_pass("blog", _valid_blog())

    print("== self-test: R1-R4 client-exact OVERRIDES (must PASS with override recorded) ==")
    # R1: caption override on a carousel (a 2,200-char caption week)
    f = _valid_fbig_carousel(); f["carouselCaption"] = _pad_chars(2200) + " #a #b #c #d #e"
    f["overrides"] = {"caption_fb_ig": [2000, 2400]}
    check_pass("carousel-caption-override", f)
    # R1: series short-form 120-word days via override
    f = _valid_series()
    for d in f["days"]:
        d["body"] = _pad_words(120)
    f["overrides"] = {"post_body_words": [100, 300]}
    check_pass("series-shortform-override", f)
    # R2: 5-slide teaser carousel via client-exact slide override (floor 2)
    f = _valid_fbig_carousel(); f["slides"] = f["slides"][:5]; f["images_ready"] = 5
    f["overrides"] = {"carousel_slides_fb_ig": {"exact": 5}}
    check_pass("carousel-5slide-override", f)
    # R3: no hashtags on LinkedIn via hashtagPolicy [0,0]
    f = _valid_linkedin_carousel(); f["carouselCaption"] = _pad_chars(1700)
    f["hashtagPolicy"] = [0, 0]
    check_pass("linkedin-zero-hashtags", f)
    # R3: reformat LinkedIn [0,0]
    f = _valid_reformat(); f["linkedin"]["post"] = "hook with no tags"
    f["hashtagPolicy"] = {"linkedin": [0, 0]}
    check_pass("reformat-li-zero-hashtags", f)
    # R6: non-25s creative video lane via storyboard_seconds override
    f = _valid_storyboard()
    f["scenes"] = [{"Scene": "a", "duration": 20.0}, {"Scene": "b", "duration": 20.0},
                   {"Scene": "c", "duration": 18.0}]
    f["overrides"] = {"storyboard_seconds": [55, 60]}
    check_pass("video-55-60s-override", f)
    # C7: stories caption on reformat
    f = _valid_reformat(); f["storiesCaption"] = "Tap to read the whole story"
    check_pass("reformat-stories-caption", f)

    print("== self-test: VIOLATION fixtures (must FAIL / exit nonzero) ==")
    f = _valid_fbig_carousel(); f["carouselCaption"] = _pad_chars(900) + " #a #b #c #d #e"
    check_fail("caption-too-short", f, "AF-SM-CAPTION-BAND")
    f = _valid_linkedin_carousel(); f["carouselCaption"] = _pad_chars(2100) + " #one #two #three"
    check_fail("caption-li-too-long", f, "AF-SM-CAPTION-BAND")
    f = _valid_fbig_carousel(); f["carouselCaption"] = _pad_chars(1600) + " #a #b"
    check_fail("hashtags-too-few", f, "AF-SM-HASHTAG-COUNT")
    f = _valid_linkedin_carousel(); f["carouselCaption"] = _pad_chars(1700) + " #a #b #c #d"
    check_fail("hashtags-li-not-3", f, "AF-SM-HASHTAG-COUNT")
    f = _valid_linkedin_carousel(); f["pdfTitle"] = _pad_chars(140)
    check_fail("pdftitle-too-long", f, "AF-SM-PDFTITLE-BAND")
    f = _valid_fbig_carousel(); f["slides"] = f["slides"][:8]
    check_fail("carousel-slides-not-10", f, "AF-SM-CAROUSEL-SLIDES")
    f = _valid_fbig_carousel(); f["slides"][0]["textOnImage"] = _pad_words(12)
    check_fail("headline-over-8-words", f, "AF-SM-HEADLINE-WORDS")
    f = _valid_fbig_carousel(); f["slides"][0]["prompt"] = _pad_chars(400)
    check_fail("imgprompt-too-short", f, "AF-SM-IMGPROMPT-BAND")
    f = _valid_fbig_carousel(); f["images_ready"] = 1
    check_fail("assemble-floor", f, "AF-SM-CAROUSEL-FLOOR")
    f = _valid_series(); f["days"][2]["body"] = _pad_words(120)
    check_fail("body-under-300", f, "AF-SM-POSTBODY-WORDS")
    f = _valid_series(); f["days"][2]["imageprompt"] = _pad_chars(900)
    check_fail("series-imgprompt-short", f, "AF-SM-IMGPROMPT-BAND")
    f = _valid_series(); f["days"][2]["followupcomment"] = _pad_chars(700)
    check_fail("followup-over-600", f, "AF-SM-FOLLOWUP-BAND")
    f = _valid_reformat(); f["instagram"]["followUpComment"] = _pad_chars(600)
    check_fail("reformat-followup-over-500", f, "AF-SM-FOLLOWUP-BAND")
    f = _valid_reformat(); f["instagram"]["post"] = "hook #one #two"
    check_fail("ig-reformat-hashtags-few", f, "AF-SM-HASHTAG-COUNT")
    f = _valid_storyboard(); f["scenes"][0]["duration"] = 9.0
    check_fail("storyboard-not-25s", f, "AF-SM-STORYBOARD")
    f = {"kind": "storyboard", "scenes": [{"Scene": "a", "duration": 25.0}, {"Scene": "b", "duration": 0.0}]}
    check_fail("storyboard-too-few-scenes", f, "AF-SM-STORYBOARD")
    # R2: a slide-count override BELOW the 2-image assembly floor is rejected
    f = _valid_fbig_carousel(); f["slides"] = f["slides"][:1]; f["images_ready"] = 1
    f["overrides"] = {"carousel_slides_fb_ig": {"exact": 1}}
    check_fail("carousel-override-below-floor", f, "AF-SM-CAROUSEL-FLOOR")
    # fold violations
    f = _valid_podcast(); f["durationSeconds"] = 300
    check_fail("podcast-duration-short", f, "AF-SM-PODCAST-DURATION")
    f = _valid_podcast(); f["coverWidth"] = 1080; f["coverHeight"] = 1080
    check_fail("podcast-cover-wrong-size", f, "AF-SM-PODCAST-COVER")
    f = _valid_podcast(); f["scriptWords"] = 800
    check_fail("podcast-script-short", f, "AF-SM-PODCAST-SCRIPT")
    f = _valid_newsletter(); f["subject"] = _pad_chars(80)
    check_fail("email-subject-too-long", f, "AF-SM-EMAIL-SUBJECT")
    f = _valid_newsletter(); f["preview"] = _pad_chars(160)
    check_fail("email-preview-too-long", f, "AF-SM-EMAIL-PREVIEW")
    f = _valid_newsletter(); f["html"] = ""
    check_fail("email-html-missing", f, "AF-SM-EMAIL-HTML")
    f = _valid_blog(); f["title"] = _pad_chars(120)
    check_fail("blog-title-too-long", f, "AF-SM-BLOG-TITLE")
    f = _valid_blog(); f["body"] = _pad_words(200)
    check_fail("blog-body-short", f, "AF-SM-BLOG-BODY")
    f = _valid_reformat(); f["storiesCaption"] = _pad_chars(400)
    check_fail("stories-caption-too-long", f, "AF-SM-STORIES-CAPTION")

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed SACRED-bands prover for Social Media in a Box (Skill 57).")
    ap.add_argument("path", nargs="?", help="asset.json to prove")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    ap.add_argument("--kind", choices=list(_EVALUATORS.keys()), help="force the input kind")
    ap.add_argument("--bands", help="path to bands.json (default: config/bands.json)")
    ap.add_argument("--self-test", dest="self_test", action="store_true", help="run built-in fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json, kind=args.kind, bands_path=args.bands)


if __name__ == "__main__":
    sys.exit(main())

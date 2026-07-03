#!/usr/bin/env python3
# =============================================================================
# SKILL 57 — SOCIAL MEDIA IN A BOX :: JSON-CONTRACT VALIDATOR
# -----------------------------------------------------------------------------
# DETERMINISTIC, NO-AI, FAIL-CLOSED. Every LLM call in the pipeline has a
# declared output schema; this validator parses/validates the output BEFORE the
# pipeline advances. It enforces:
#   * strict JSON / declared object shape         -> AF-SM-CONTRACT-JSON
#   * per-platform required keys                  -> AF-SM-CONTRACT-SCHEMA
#       - FB/IG carousel : carouselCaption + slides[] (each textOnImage+prompt)
#       - LinkedIn carousel: pdfTitle + postAsPdf:true + carouselCaption + slides[]
#       - reformat : requested-platform blocks present
#       - publish_result : {platform, success, totalPosts, processedAccounts, errors}
#   * em-dash / smart-character ban (JSON-safe)   -> AF-SM-CONTRACT-EMDASH
#   * Gemini 4-grid selector = a single digit 0-3 -> AF-SM-GRID-DIGIT
#   * QC bot output = 'Good' OR the exact 4-field
#     set, JSON-safe for SeedDream re-injection    -> AF-SM-QC-JSON
#
# The em-dash ban is enforced in triplicate in the prompts AND re-checked here
# deterministically (PRD 4.2). No network, no model, stdlib only.
#
# EXIT: 0 PASS / 2 AUTOFAIL / 3 USAGE-IO.
# USAGE:
#   python3 validate_contract.py <output.json> [--json] [--kind K]
#   python3 validate_contract.py --self-test
# =============================================================================
"""Fail-closed JSON-contract validator for Social Media in a Box (Skill 57)."""

import argparse
import json
import re
import sys
from pathlib import Path

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_JSON = "AF-SM-CONTRACT-JSON"
AF_SCHEMA = "AF-SM-CONTRACT-SCHEMA"
AF_EMDASH = "AF-SM-CONTRACT-EMDASH"
AF_GRID = "AF-SM-GRID-DIGIT"
AF_QC = "AF-SM-QC-JSON"

# Em dash + en dash + curly/smart quotes: banned from JSON-safe output.
_SMART_RE = re.compile("[—–‘’“”]")
_EMDASH_RE = re.compile("[—–]")
_QC_FIELDS = ("fix_type", "edit_instructions", "negative_prompt_additions", "issue_summary")
_QC_FIX_TYPES = ("REGENERATE_FULL", "INPAINT_REGION", "PROMPT_ADJUSTMENT")


def _iter_strings(obj, path="$"):
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _iter_strings(v, "%s.%s" % (path, k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_strings(v, "%s[%d]" % (path, i))


def _emdash_scan(obj, af=AF_EMDASH):
    fails = []
    for path, s in _iter_strings(obj):
        if _EMDASH_RE.search(s):
            fails.append((af, "%s contains an em/en dash (use regular hyphens only)" % path))
    return fails


def _content_emdash_scan(rec, af=AF_EMDASH):
    """R4 (em-dash split): the em-dash ban over CONTENT fields (posts, captions,
    comments) stays the DEFAULT (35's human-voice DNA) but is client-overridable
    with a per-client logged `emDashPolicy: allow-content` (recorded on the
    certificate). The machine-reinjected JSON-safe fields (QC bot / grid selector)
    keep the ban FOREVER, fail-closed, in evaluate_qc/evaluate_grid - that half is
    technical (the string is re-injected into SeedDream payloads) and never
    overridable. Client-supplied copy (client-copy mode) is verbatim -> the
    engine may never edit it, so its em dashes pass here (scrub may still BLOCK a
    secret/name leak, never silently edit)."""
    policy = str(rec.get("emDashPolicy", "")).strip().lower() if isinstance(rec, dict) else ""
    if policy == "allow-content":
        return []
    return _emdash_scan(rec, af)


# ---- per-kind evaluation ----------------------------------------------------
def evaluate_carousel(rec):
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "carousel output is not a JSON object")]
    platform = str(rec.get("platform", "")).lower()
    is_li = platform == "linkedin"
    if not rec.get("carouselCaption"):
        fails.append((AF_SCHEMA, "missing carouselCaption"))
    slides = rec.get("slides")
    if not isinstance(slides, list) or not slides:
        fails.append((AF_SCHEMA, "missing slides[] array"))
    else:
        for i, s in enumerate(slides, 1):
            if not isinstance(s, dict) or "textOnImage" not in s or "prompt" not in s:
                fails.append((AF_SCHEMA, "slide %d missing textOnImage/prompt" % i))
    if is_li:
        if not rec.get("pdfTitle"):
            fails.append((AF_SCHEMA, "LinkedIn carousel missing pdfTitle"))
        if rec.get("postAsPdf") is not True:
            fails.append((AF_SCHEMA, "LinkedIn carousel requires postAsPdf:true"))
    fails.extend(_content_emdash_scan(rec))
    return fails


def evaluate_reformat(rec):
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "reformat output is not a JSON object")]
    requested = rec.get("requestedPlatforms")
    if isinstance(requested, list):
        for p in requested:
            if p not in rec:
                fails.append((AF_SCHEMA, "requested platform %r has no output block" % p))
    if not any(k in rec for k in ("facebook", "instagram", "linkedin", "youtube", "tiktok",
                                  "pinterest", "twitter")):
        fails.append((AF_SCHEMA, "reformat output has no platform blocks"))
    fails.extend(_content_emdash_scan(rec))
    return fails


def evaluate_newsletter(rec):
    """C4 newsletter contract: subject + preview + html (table-based inline CSS)."""
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "newsletter output is not a JSON object")]
    for k in ("subject", "preview", "html"):
        if not str(rec.get(k, "")).strip():
            fails.append((AF_SCHEMA, "newsletter missing %r" % k))
    fails.extend(_content_emdash_scan(rec))
    return fails


def evaluate_blog(rec):
    """C5 blog contract: title + body + metaDescription."""
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "blog output is not a JSON object")]
    for k in ("title", "body", "metaDescription"):
        if not str(rec.get(k, "")).strip():
            fails.append((AF_SCHEMA, "blog missing %r" % k))
    fails.extend(_content_emdash_scan(rec))
    return fails


def evaluate_podcast(rec):
    """C3 podcast contract: either a labeled deferral or the script + audio + cover set."""
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "podcast output is not a JSON object")]
    if rec.get("deferred") is True:
        return fails  # PODCAST_DEFERRED graceful skip: no contract to enforce
    for k in ("script", "audioUrl", "coverUrl"):
        if not str(rec.get(k, "")).strip():
            fails.append((AF_SCHEMA, "podcast missing %r (or set deferred:true)" % k))
    fails.extend(_content_emdash_scan(rec))
    return fails


def evaluate_client_copy(rec):
    """M3 client-copy contract: the engine PACKAGES, never authors. Validate only
    that a platform + verbatim copy are present; the byte-for-byte verbatim
    guarantee (AF-SM-CLIENT-COPY-MUTATED) is proven at the manifest. The em-dash
    ban does NOT apply - these are the client's exact words, never edited."""
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "client-copy output is not a JSON object")]
    if not str(rec.get("platform", "")).strip():
        fails.append((AF_SCHEMA, "client-copy missing platform"))
    if not str(rec.get("copy") or rec.get("body") or "").strip():
        fails.append((AF_SCHEMA, "client-copy missing the supplied copy/body"))
    return fails


def evaluate_grid(rec):
    val = rec.get("output") if isinstance(rec, dict) else rec
    s = str(val).strip()
    if not re.fullmatch(r"[0-3]", s):
        return [(AF_GRID, "grid selector output %r is not a single digit 0-3" % s)]
    return []


def evaluate_qc(rec):
    val = rec.get("output") if isinstance(rec, dict) else rec
    if not isinstance(val, str):
        return [(AF_QC, "QC output is not a string")]
    text = val.strip()
    if text == "Good":
        return []
    fails = []
    # must contain each of the 4 fields, each on its own line "name: value"
    lines = [ln for ln in text.splitlines() if ln.strip()]
    seen = {}
    for ln in lines:
        m = re.match(r"^\s*([a-z_]+)\s*:\s*(.*)$", ln)
        if m:
            seen[m.group(1)] = m.group(2)
    for f in _QC_FIELDS:
        if f not in seen:
            fails.append((AF_QC, "QC fix output missing field %r (must be 'Good' or the exact 4-field set)" % f))
    ft = seen.get("fix_type", "").strip()
    if ft and ft not in _QC_FIX_TYPES:
        fails.append((AF_QC, "fix_type %r not one of %s" % (ft, "|".join(_QC_FIX_TYPES))))
    # JSON-safety: no double quotes, no backslashes, no smart chars/em dashes.
    if '"' in text:
        fails.append((AF_QC, "QC output contains a double quote (must be JSON-safe for SeedDream re-injection)"))
    if "\\" in text:
        fails.append((AF_QC, "QC output contains a backslash (must be JSON-safe)"))
    if _SMART_RE.search(text):
        fails.append((AF_QC, "QC output contains an em dash or smart quote (use plain hyphens/quotes)"))
    return fails


def evaluate_publish_result(rec):
    fails = []
    if not isinstance(rec, dict):
        return [(AF_JSON, "publish result is not a JSON object")]
    required = ("platform", "success", "totalPosts", "processedAccounts", "errors")
    for k in required:
        if k not in rec:
            fails.append((AF_SCHEMA, "publish result missing %r (normalized contract)" % k))
    if "success" in rec and not isinstance(rec["success"], bool):
        fails.append((AF_SCHEMA, "publish result 'success' must be boolean"))
    if "errors" in rec and not isinstance(rec["errors"], list):
        fails.append((AF_SCHEMA, "publish result 'errors' must be an array"))
    return fails


def _detect_kind(obj):
    if isinstance(obj, dict):
        if obj.get("kind"):
            return obj["kind"]
        if "processedAccounts" in obj or "totalPosts" in obj:
            return "publish_result"
        if "slides" in obj:
            return "carousel"
        if "subject" in obj and "html" in obj:
            return "newsletter"
        if "metaDescription" in obj:
            return "blog"
        if obj.get("deferred") is True or ("audioUrl" in obj and "coverUrl" in obj):
            return "podcast"
        if "copy" in obj and "platform" in obj:
            return "client_copy"
        if "requestedPlatforms" in obj or "coreTheme" in obj:
            return "reformat"
        if "output" in obj:
            v = str(obj["output"]).strip()
            return "grid" if re.fullmatch(r"[0-9]", v) else "qc"
    return "reformat"


_EVALUATORS = {
    "carousel": evaluate_carousel, "reformat": evaluate_reformat,
    "grid": evaluate_grid, "qc": evaluate_qc, "publish_result": evaluate_publish_result,
    "newsletter": evaluate_newsletter, "blog": evaluate_blog, "podcast": evaluate_podcast,
    "client_copy": evaluate_client_copy,
}


def evaluate(obj, kind=None):
    k = kind or _detect_kind(obj)
    fn = _EVALUATORS.get(k, evaluate_reformat)
    return k, fn(obj)


def decide_exit(failures):
    return EXIT_PASS if not failures else EXIT_AUTOFAIL


def _emit(source, kind, failures, as_json):
    if as_json:
        print(json.dumps({"gate": "social-media-contract-validator", "source": source,
                          "kind": kind, "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Social Media in a Box :: contract validator (kind=%s) ==" % kind)
    print("source: %s" % source)
    if not failures:
        print("RESULT: PASS — contract satisfied.")
    else:
        print("RESULT: FAIL (fail-closed) — %d violation(s):" % len(failures))
        for c, m in failures:
            print("  [%s] %s" % (c, m))


def prove(path, as_json=False, kind=None):
    p = Path(path)
    if not p.is_file():
        _emit(str(p), "?", [(AF_JSON, "file not found: %s" % p)], as_json)
        return EXIT_USAGE
    raw = p.read_text(encoding="utf-8")
    # QC / grid outputs may be raw text; try JSON first, else wrap as {"output": raw}.
    try:
        obj = json.loads(raw)
    except ValueError:
        obj = {"output": raw.strip()}
    k, failures = evaluate(obj, kind=kind)
    _emit(str(p), k, failures, as_json)
    return decide_exit(failures)


# =============================================================================
# SELF-TEST
# =============================================================================
def _valid_fbig():
    return {"kind": "carousel", "platform": "facebook", "carouselCaption": "hook and value",
            "slides": [{"textOnImage": "a", "prompt": "b"} for _ in range(10)]}


def _valid_linkedin():
    return {"kind": "carousel", "platform": "linkedin", "pdfTitle": "Title", "postAsPdf": True,
            "carouselCaption": "hook", "slides": [{"textOnImage": "a", "prompt": "b"} for _ in range(9)]}


def _valid_qc_fix():
    return {"kind": "qc", "output": ("fix_type: INPAINT_REGION\n"
            "edit_instructions: Correct the misspelled word. Keep everything else the same.\n"
            "negative_prompt_additions: misspelled text, typos\n"
            "issue_summary: The word is misspelled and needs correction.")}


def self_test():
    ok = True

    def cp(name, fx, kind=None):
        nonlocal ok
        _, fails = evaluate(fx, kind=kind)
        good = not fails
        ok = ok and good
        print("  [%s] VALID %-22s -> exit %d %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), "" if good else fails[:3]))

    def cf(name, fx, expect, kind=None):
        nonlocal ok
        _, fails = evaluate(fx, kind=kind)
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print("  [%s] VIOLATION %-20s -> exit %d has %s %s" % ("PASS" if good else "MISS", name,
              decide_exit(fails), expect, "" if good else codes))

    print("== self-test: VALID (exit 0) ==")
    cp("fbig-carousel", _valid_fbig())
    cp("linkedin-carousel", _valid_linkedin())
    cp("grid-digit", {"kind": "grid", "output": "2"})
    cp("qc-good", {"kind": "qc", "output": "Good"})
    cp("qc-fix", _valid_qc_fix())
    cp("publish-result", {"kind": "publish_result", "platform": "facebook", "success": True,
                          "totalPosts": 7, "processedAccounts": 1, "errors": []})
    cp("publish-result-twitter", {"kind": "publish_result", "platform": "twitter", "success": True,
                                  "totalPosts": 7, "processedAccounts": 1, "errors": []})
    cp("newsletter", {"kind": "newsletter", "subject": "Your week", "preview": "one shift",
                      "html": "<table></table>"})
    cp("blog", {"kind": "blog", "title": "T", "body": "long body", "metaDescription": "m"})
    cp("podcast-deferred", {"kind": "podcast", "deferred": True})
    cp("podcast-full", {"kind": "podcast", "script": "hi", "audioUrl": "https://x/a.mp3",
                        "coverUrl": "https://x/c.jpg"})
    cp("client-copy", {"kind": "client_copy", "platform": "instagram", "copy": "post this exactly"})
    # R4: content em dash PASSES only with a logged allow-content policy
    cp("carousel-emdash-allowed", {"kind": "carousel", "platform": "facebook",
        "carouselCaption": "hook — value", "emDashPolicy": "allow-content",
        "slides": [{"textOnImage": "a", "prompt": "b"} for _ in range(10)]})
    # R4: client-copy is verbatim -> its em dashes never trip the content ban
    cp("client-copy-emdash-verbatim", {"kind": "client_copy", "platform": "linkedin",
        "copy": "our signature style uses em dashes on purpose"})

    print("== self-test: VIOLATION (exit nonzero) ==")
    f = _valid_fbig(); del f["carouselCaption"]
    cf("missing-caption", f, AF_SCHEMA)
    f = _valid_linkedin(); f["postAsPdf"] = False
    cf("linkedin-no-pdf-flag", f, AF_SCHEMA)
    f = _valid_fbig(); f["carouselCaption"] = "hook — value"
    cf("em-dash", f, AF_EMDASH)
    cf("grid-not-digit", {"kind": "grid", "output": "the second one"}, AF_GRID)
    cf("grid-out-of-range", {"kind": "grid", "output": "7"}, AF_GRID)
    f = _valid_qc_fix(); f["output"] = f["output"].replace("issue_summary:", "summary:")
    cf("qc-missing-field", f, AF_QC)
    f = _valid_qc_fix(); f["output"] = f["output"] + '\nnote: has a "quote"'
    cf("qc-double-quote", f, AF_QC)
    f = _valid_qc_fix(); f["output"] = f["output"].replace("correction.", "correction — now.")
    cf("qc-em-dash", f, AF_QC)
    cf("publish-missing-key", {"kind": "publish_result", "platform": "x", "success": True}, AF_SCHEMA)
    # R4: default policy (no opt-out) STILL bans content em dashes, fail-closed
    cf("carousel-emdash-default-banned", {"kind": "carousel", "platform": "facebook",
        "carouselCaption": "hook — value",
        "slides": [{"textOnImage": "a", "prompt": "b"} for _ in range(10)]}, AF_EMDASH)
    cf("newsletter-missing-html", {"kind": "newsletter", "subject": "s", "preview": "p"}, AF_SCHEMA)
    cf("blog-missing-meta", {"kind": "blog", "title": "t", "body": "b"}, AF_SCHEMA)
    cf("podcast-missing-audio", {"kind": "podcast", "script": "s", "coverUrl": "c"}, AF_SCHEMA)
    cf("client-copy-missing-platform", {"kind": "client_copy", "copy": "x"}, AF_SCHEMA)

    print("== self-test: %s ==" % ("ALL ASSERTIONS PASSED" if ok else "FAILED"))
    return 0 if ok else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fail-closed JSON-contract validator (Skill 57).")
    ap.add_argument("path", nargs="?")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--kind", choices=list(_EVALUATORS.keys()))
    ap.add_argument("--self-test", dest="self_test", action="store_true")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if not args.path:
        ap.error("a path is required (or use --self-test)")
    return prove(args.path, as_json=args.json, kind=args.kind)


if __name__ == "__main__":
    sys.exit(main())

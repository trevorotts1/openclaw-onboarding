"""lyric_writer.py: sung-copy rules (directive 11.3) over campaign-schema lyrics. stdlib only.

Rules: short first-person lines, one idea per line, critical=true on every
line carrying offer/claim/product/CTA wording (100% coverage per acceptance
profile), pronunciation_map on every line naming the product. CTA lines
(line_id containing "cta") are exempt from first-person (imperative voice).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protected_names  # noqa: E402  H7 build gate

SCHEMA_VERSION = "blackceo.lyric-writer/v1"
TOOL_VERSION = "0.1.0"

# ponytail: fixed ceilings, no per-campaign override; add when directive names numbers.
MAX_WORDS = 18
MIN_SIGNIFICANT_LEN = 4
LINE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
FIRST_PERSON = frozenset({
    "i", "me", "my", "mine", "myself", "we", "us", "our", "ours",
    "ourselves", "i'm", "i've", "i'll", "i'd", "we're", "we've",
    "we'll", "we'd",
})
EXIT = {"ok": 0, "rejected": 4, "error": 1}
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def words(text):
    return re.findall(r"[a-z0-9]+(?:'[a-z]+)?", text.lower())


def significant(text):
    """Brief words that force critical coverage (len>=4 alnum tokens)."""
    if not isinstance(text, str):
        return set()
    return {w for w in words(text) if len(w) >= MIN_SIGNIFICANT_LEN}


def brief_words(brief):
    out = set()
    b = brief or {}
    for key in ("product_name", "offer_text", "cta_text"):
        out |= significant(b.get(key))
    claims = b.get("claims") or []
    for c in claims if isinstance(claims, list) else []:
        out |= significant(c)
    return out


def product_tokens(brief):
    return significant((brief or {}).get("product_name"))


def _res(outcome, reason_code, errors, lines, coverage):
    return {
        "schema_version": SCHEMA_VERSION,
        "tool_version": TOOL_VERSION,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": errors,
        "line_count": len(lines) if isinstance(lines, list) else 0,
        "coverage": coverage,
        "next_action": (
            "Proceed to lyric QC." if outcome == "ok"
            else "Fix the listed lyric errors and re-run validate_lyrics."
        ),
    }


def validate_lyrics(lines, brief=None):
    """Validate sung lines against the brief. Returns outcome/reason/coverage."""
    brief = brief or {}
    if not isinstance(lines, list) or not lines:
        return _res("rejected", "lyrics-empty",
                    [{"error": "lyrics-empty", "detail": "lyrics must be a non-empty list"}],
                    lines, {"critical_words": 0, "covered": 0, "missing": []})

    errors, seen, ok_lines = [], set(), []
    crit_words = brief_words(brief)
    prod = product_tokens(brief)

    for i, ln in enumerate(lines):
        tag = "line %d" % i
        if not isinstance(ln, dict):
            errors.append({"error": "line-not-an-object", "detail": tag})
            continue
        lid = ln.get("line_id")
        if not isinstance(lid, str) or not LINE_ID_RE.match(lid):
            errors.append({"error": "line-id-invalid", "detail": "%s: %r" % (tag, lid)})
            lid = tag
        elif lid in seen:
            errors.append({"error": "line-id-duplicate", "detail": lid})
        seen.add(lid if isinstance(lid, str) else tag)

        text = ln.get("text")
        if not isinstance(text, str) or not text.strip():
            errors.append({"error": "line-empty", "detail": lid})
            continue
        toks = words(text)
        if len(toks) > MAX_WORDS:
            errors.append({"error": "line-too-long",
                           "detail": "%s: %d words, max %d" % (lid, len(toks), MAX_WORDS)})
        core = text.strip().rstrip(".!?;").lower()
        if re.search(r"[.!?;]", core):
            errors.append({"error": "line-multi-idea",
                           "detail": "%s: one idea per line" % lid})
        cta = "cta" in str(lid).lower()
        if not cta and not (set(toks) & FIRST_PERSON):
            errors.append({"error": "line-not-first-person", "detail": lid})

        ltoks = set(toks)
        hits = sorted(crit_words & ltoks)
        if hits and ln.get("critical") is not True:
            errors.append({"error": "critical-missing",
                           "detail": "%s: carries %s but critical != true" % (lid, hits)})

        ptoks = sorted(prod & ltoks)
        pmap = ln.get("pronunciation_map")
        if ptoks:
            if not isinstance(pmap, dict) or not pmap:
                errors.append({"error": "pronunciation-missing",
                               "detail": "%s: names product %s, needs pronunciation_map" % (lid, ptoks)})
            else:
                for k, v in pmap.items():
                    if not isinstance(v, str) or not v.strip():
                        errors.append({"error": "pronunciation-invalid",
                                       "detail": "%s: map[%r] must be a non-empty string" % (lid, k)})
                    elif str(k).lower() not in text.lower():
                        errors.append({"error": "pronunciation-key-absent",
                                       "detail": "%s: map key %r not in line text" % (lid, k)})
        elif isinstance(pmap, dict):
            for k, v in pmap.items():
                if not isinstance(v, str) or not v.strip():
                    errors.append({"error": "pronunciation-invalid",
                                   "detail": "%s: map[%r] must be a non-empty string" % (lid, k)})
                elif str(k).lower() not in text.lower():
                    errors.append({"error": "pronunciation-key-absent",
                                   "detail": "%s: map key %r not in line text" % (lid, k)})
        ok_lines.append(ln)

    # H7: the sheet may not change a protected name or rewrite a packet line.
    packet = brief.get("packet_lines")
    if packet is not None:
        for msg in protected_names.check_sheet(
                lines, packet, protected_names.protected_list(brief)):
            errors.append({"error": msg.split()[0].lower().replace("_", "-"),
                           "detail": msg})

    covered = {w for ln in ok_lines if ln.get("critical") is True
               for w in crit_words & set(words(ln.get("text") or ""))}
    missing = sorted(crit_words - covered)
    if missing:
        errors.append({"error": "coverage-missing",
                       "detail": "critical words with no critical line: %s" % missing})
    coverage = {"critical_words": len(crit_words), "covered": len(covered), "missing": missing}

    if errors:
        return _res("rejected", errors[0]["error"], errors, lines, coverage)
    return _res("ok", "lyrics-valid", [], lines, coverage)


def _spoken_share():
    try:
        import spoken_share as ss               # core/ on sys.path
    except ImportError:
        from .. import spoken_share as ss       # imported as core.*
    return ss


def steer_opening(blocks, length_s=None, basis="planned"):
    """H6: steer the sheet's opening toward first real singing at 15% of
    runtime (about 9 s in a 60 s ad). ``blocks`` is the planned timeline
    [{"delivery": "spoken"|"sung"|"rap", "seconds": n}, ...]; pass the
    vocal-stem measurement with basis="measured" for a take. Returns the
    spoken_share verdict plus action (keep / shorten_opener /
    lengthen_opener / add_sung_hook) and move_by_s: how far to move the
    sung hook. One rule, owned by core/spoken_share; nothing re-derived.
    """
    ss = _spoken_share()
    res = ss.steer_first_sung(blocks, basis)
    if length_s is not None:
        res["plan_target_s"] = ss.seconds_for(length_s)["first_sung_target_s"]
    return res


def validate_campaign(campaign):
    """Validate a campaign record's lyrics (campaign-schema shape) + brief."""
    if not isinstance(campaign, dict):
        return _res("error", "campaign-not-an-object",
                    [{"error": "campaign-not-an-object", "detail": "campaign must be a JSON object"}],
                    None, {"critical_words": 0, "covered": 0, "missing": []})
    if not isinstance(campaign.get("brief"), dict):
        return _res("rejected", "brief-missing",
                    [{"error": "brief-missing", "detail": "campaign.brief object is required"}],
                    campaign.get("lyrics"), {"critical_words": 0, "covered": 0, "missing": []})
    return validate_lyrics(campaign.get("lyrics"), campaign.get("brief"))


def load_fixture(name):
    with open(FIXTURE_DIR / name, encoding="utf-8") as f:
        return json.load(f)


def selftest():
    checks, fails = [], []

    def expect(name, want_outcome, want_reason):
        try:
            fx = load_fixture(name)
        except (OSError, json.JSONDecodeError) as e:
            checks.append(name)
            fails.append("%s: unreadable (%s)" % (name, e))
            return
        r = validate_lyrics(fx.get("lines"), fx.get("brief"))
        ok = r["outcome"] == want_outcome and (
            want_reason is None or r["reason_code"] == want_reason)
        checks.append(name)
        if not ok:
            fails.append("%s: outcome=%s reason=%s, want %s/%s"
                         % (name, r["outcome"], r["reason_code"],
                            want_outcome, want_reason))

    expect("valid.json", "ok", "lyrics-valid")
    expect("missing-critical.json", "rejected", "critical-missing")
    expect("coverage-gap.json", "rejected", "coverage-missing")
    expect("multi-idea.json", "rejected", "line-multi-idea")
    expect("not-first-person.json", "rejected", "line-not-first-person")
    expect("pronunciation-missing.json", "rejected", "pronunciation-missing")

    for bad in (None, [], {"lines": [], "brief": {}}):
        r = validate_lyrics(bad if isinstance(bad, list) else (bad or {}).get("lines"),
                            (bad or {}).get("brief") if isinstance(bad, dict) else None)
        checks.append("inline:%r" % (str(bad)[:40],))
        if r["outcome"] == "ok":
            fails.append("inline %r accepted, want reject" % (bad,))

    # CTA exemption holds: second-person imperative with cta line_id passes
    r = validate_lyrics(
        [{"line_id": "cta01", "text": "Tap to claim your kit today", "critical": True}],
        {"product_name": "", "offer_text": "", "cta_text": "Tap to claim your kit",
         "claims": []})
    checks.append("cta-exempt")
    if r["outcome"] != "ok":
        fails.append("cta-exempt rejected: %s" % r["reason_code"])

    print("lyric_writer selftest: %s (%d checks, %d failures)"
          % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
    for f in fails:
        print(" -", f)
    return 0 if not fails else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="lyric_writer.py",
                                 description="Sung-copy rules over campaign-schema lyrics.")
    ap.add_argument("--selftest", action="store_true", help="Run QC fixtures.")
    ap.add_argument("--lyrics", default=None, help="JSON file: campaign record or fixture.")
    ap.add_argument("--brief", default=None, help="JSON file: brief (skip if lyrics file is a campaign).")
    a = ap.parse_args(argv)
    if a.selftest:
        return selftest()
    if not a.lyrics:
        ap.error("one of --selftest or --lyrics is required")
    try:
        with open(a.lyrics, encoding="utf-8") as f:
            doc = json.load(f)
        brief = None
        if a.brief:
            with open(a.brief, encoding="utf-8") as f:
                brief = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        r = {"schema_version": SCHEMA_VERSION, "tool_version": TOOL_VERSION,
             "outcome": "error", "reason_code": "lyrics-unreadable",
             "errors": [{"error": "lyrics-unreadable", "detail": str(e)[:200]}],
             "line_count": 0, "coverage": {"critical_words": 0, "covered": 0, "missing": []},
             "next_action": "Supply readable JSON lyric input."}
    else:
        if (isinstance(doc, dict) and isinstance(doc.get("brief"), dict)
                and "lines" not in doc and isinstance(doc.get("lyrics"), list)):
            r = validate_campaign(doc)
        elif isinstance(doc, dict) and "lines" in doc:
            r = validate_lyrics(doc.get("lines"), doc.get("brief") if brief is None else brief)
        else:
            r = validate_lyrics(doc if isinstance(doc, list) else None, brief)
    json.dump(r, sys.stdout, indent=2, sort_keys=True, default=str)
    sys.stdout.write("\n")
    return EXIT[r["outcome"]]


if __name__ == "__main__":
    sys.exit(main())

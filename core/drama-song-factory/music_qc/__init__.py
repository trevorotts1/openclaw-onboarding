#!/usr/bin/env python3
"""Song QC: directive 17.2 + 12.4 + 17.8 lyric/timing gates. Stdlib only.

Approved lyrics are the textual source of truth (12.4): ASR/observed text
is timing and mismatch evidence, never permission to rewrite. Approved
pronunciation mappings may change spelling in generation input, never
meaning. Missing approved lines, omitted critical sales lines, or extra
unapproved lines that damage meaning FAIL.

Thresholds come from core/acceptance-profile.json (critical coverage 1.0,
overall 0.98).
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

TOOL_NAME = "music_qc"
TOOL_VERSION = "1.0.0"

_prof = None


def profile():
    """Acceptance thresholds (lyrics/timing), read from the profile."""
    global _prof
    if _prof is None:
        p = (Path(__file__).resolve().parents[1] / "acceptance-profile.json")
        _prof = json.loads(p.read_text(encoding="utf-8"))
    return _prof


def norm(text):
    """Fold for comparison: lowercase, de-accent, keep alnum only."""
    t = unicodedata.normalize("NFKD", text or "").lower()
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def tokenize(text):
    return norm(text).split()


def map_generation_spelling(text, pronunciation_map=None):
    """Apply approved spelling substitutions (spelling only, never meaning)."""
    out = text or ""
    for src, dst in (pronunciation_map or {}).items():
        if src and dst:
            out = out.replace(src, dst)
    return out


def diff_lyrics(approved_lines, observed_lines, pronunciation_map=None):
    """Approved-vs-observed lyric diff. Per-line records feed continuity.

    approved_lines: [{line_id, text, critical?}]; observed_lines:
    [{line_id?, text}]. Scores track approved-line coverage so drops,
    rewrites, and ad-lib padding all fail closed.
    """
    cov_min = profile()["lyrics"]["overall_normalized_coverage_min"]
    approved_words, critical_words = [], set()
    line_map = {}
    for ln in approved_lines or []:
        words = tokenize(map_generation_spelling(
            ln.get("text", ""), pronunciation_map))
        line_map[ln.get("line_id", "")] = {
            "line_id": ln.get("line_id", ""), "words": words,
            "critical": bool(ln.get("critical"))}
        approved_words.extend(words)
        if ln.get("critical"):
            critical_words.update(words)
    observed_words, matched = [], 0
    remaining = list(approved_words)
    for ln in observed_lines or []:
        for w in tokenize(ln.get("text", "")):
            observed_words.append(w)
            if w in remaining:
                remaining.remove(w)
                matched += 1
    approved_set = set(approved_words)
    adlib_words = [w for w in observed_words if w not in approved_set]
    missing_words = sorted(set(approved_words) - set(observed_words))
    critical_missing = sorted(critical_words - set(observed_words))
    obs_by_id = {ln.get("line_id", ""): ln.get("text", "")
                 for ln in observed_lines or []}
    line_results = []
    for lid, rec in line_map.items():
        seen = tokenize(obs_by_id.get(lid, ""))
        missing = [w for w in rec["words"] if w not in seen]
        hit = len(rec["words"]) - len(missing)
        frac = (hit / len(rec["words"])) if rec["words"] else 1.0
        line_results.append(
            {"line_id": lid, "critical": rec["critical"],
             "approved": " ".join(rec["words"]),
             "observed": " ".join(seen),
             "coverage": round(frac, 4),
             "missing": missing,
             "verdict": ("PASS" if not missing
                         else ("FAIL" if rec["critical"] else "WARN"))})
    approved_n = len(approved_words)
    coverage = (matched / approved_n) if approved_n else 1.0
    return {
        "approved_word_count": approved_n,
        "observed_word_count": len(observed_words),
        "matched_word_count": matched,
        "coverage": round(coverage, 4),
        "coverage_min": cov_min,
        "coverage_ok": coverage >= cov_min,
        "missing_words": missing_words,
        "critical_missing": critical_missing,
        "adlib_words": adlib_words,
        "adlib_damage": bool(adlib_words),
        "per_line": line_results,
    }


def check_song_qc(approved_lines, observed_lines, checks,
                  pronunciation_map=None):
    """17.2 song QC verdict. checks: continuity flags the provider cannot
    self-report (persona/genre/tempo continuity, clipping, transitions,
    duration); FAIL/UNAVAILABLE reasons outrank any average."""
    diff = diff_lyrics(approved_lines, observed_lines, pronunciation_map)
    findings = []
    if diff["critical_missing"]:
        findings.append(("FAIL", "critical",
                         "omitted critical sales lines: %s"
                         % ",".join(diff["critical_missing"][:8])))
    if not diff["coverage_ok"]:
        findings.append(("FAIL", "coverage",
                         "approved-word coverage %.4f below %.2f"
                         % (diff["coverage"], diff["coverage_min"])))
    if diff["adlib_damage"]:
        findings.append(("FAIL", "adlib",
                         "unapproved words damage meaning: %s"
                         % ",".join(diff["adlib_words"][:8])))
    for key in ("persona_continuity", "genre_continuity",
                "tempo_continuity", "clipping", "transitions",
                "master_duration"):
        got = (checks or {}).get(key)
        if got in (None, "UNAVAILABLE"):
            findings.append(("UNAVAILABLE", key,
                             "no evidence supplied; cannot pass"))
        elif got in ("FAIL", False):
            findings.append(("FAIL", key, "failed: %s" % key))
    verdict = "PASS"
    if any(v == "FAIL" for v, _, _ in findings):
        verdict = "FAIL"
    elif any(v == "UNAVAILABLE" for v, _, _ in findings):
        verdict = "UNAVAILABLE"
    return {"verdict": verdict,
            "findings": [{"verdict": v, "check": k, "detail": d}
                         for v, k, d in findings],
            "lyric_diff": diff,
            "checker_version": TOOL_VERSION}

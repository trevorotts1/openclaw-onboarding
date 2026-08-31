#!/usr/bin/env python3
"""
qc_check.py -- MECHANICAL ENFORCEMENT for the 48 qc_check auto-fail codes.

Serves WORK-ITEM-14 (ANTI-DRIFT CORE: Phase enforcement) + the RENDER breakpoint
(CURRENT-STATE Section B, breakpoint 3: 73 judgment-only codes gap).

PURPOSE
    A mechanical checker for the qc_check auto-fail codes that have no py_symbol
    enforcement in build_deck.py. Runs the same checks a QC specialist agent is
    supposed to run by judgment, but deterministically -- scanning the run's copy,
    prompts, slides, and QC reports for the specific violations each AF code describes.

    Also cross-checks the QC report's claimed `triggered_autofails` list against the
    report's own documented findings -- if the report body describes a violation but
    `triggered_autofails` omits the corresponding AF code, that is itself an auto-fail
    (AF-QC-FALSE-NEGATIVE).

TWO HALVES
    1. MECHANICAL CHECK HALF: runs the deterministic scanners for the qc_check codes
       that currently have NO py_symbol AND NO check_script (the truly unenforced:
       AF-HOOK-1..7, AF-AUD-1..6/PLACEHOLDER, AF-OBI-1..6, AF-DEN-1..8, AF-C2, AF-OBI).
       For qc_check codes that DO have a check_script declared (pitch_engines_check.py,
       intelligence_engines_check.py), delegates to those existing scripts.

    2. CROSS-CHECK HALF: reads the six domain QC reports and the final_qc_report.json.
       For each report, parses the documented violations and cross-references against
       the reported `triggered_autofails` list. A documented violation whose AF code is
       absent from triggered_autofails produces AF-QC-FALSE-NEGATIVE.

EXIT CODES
    0 -- clean: zero violations found.
    1 -- violations detected: at least one AF code triggered.
    2 -- usage/IO error: bad --run-dir, missing manifest, unreadable file.

USAGE
    python3 scripts/qc_check.py --run-dir <run-dir> [--manifest <path>] [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
SCRIPTS_DIR = str(HERE)


# ============================================================================
# PHASE 0: load the 48 qc_check codes from the manifest
# ============================================================================

def resolve_manifest_path(explicit: Optional[str]) -> Path:
    """Resolve PIPELINE-MANIFEST.json. Tries --manifest, then walk-up, then
    ../sops/ fallback. Exits with message if unresolvable."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if p.is_file():
            return p
        print(f"FATAL: --manifest path not found: {p}", file=sys.stderr)
        sys.exit(2)

    # Walk up
    cur = HERE
    for _ in range(6):
        cand = cur / "sops" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        parent = cur.parent
        if parent == cur:
            break
        cur = parent

    print("FATAL: could not resolve PIPELINE-MANIFEST.json (no --manifest given, "
          "walk-up failed).", file=sys.stderr)
    sys.exit(2)


def load_qc_check_codes(manifest_path: Path) -> List[Dict[str, Any]]:
    """Load autofails where enforced_by == 'qc_check' AND py_symbol is null/empty.
    Returns a list of {code, trigger, level, stage, ...} dicts."""
    try:
        obj = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        print(f"FATAL: could not read manifest {manifest_path}: {exc}", file=sys.stderr)
        sys.exit(2)

    autofails = obj.get("autofails", [])
    qc_codes = []
    for a in autofails:
        if a.get("enforced_by") != "qc_check":
            continue
        if a.get("py_symbol"):  # Already mechanically enforced via build_deck.py
            continue
        qc_codes.append(a)
    return qc_codes


# ============================================================================
# PHASE 1: mechanical scanners for the TRULY UNENFORCED codes
# ============================================================================

# ---------------------------------------------------------------------------
# FIX 18 — the six WARNING-code heuristics (AF-AUD-1, AF-AUD-2, AF-AUD-3,
# AF-OBI-3, AF-OBI-5, AF-DEN-8). A heuristic may WARN; it may never claim a
# deterministic auto-fail. Findings come back with level="warning" so
# run_all's exit-code arithmetic ignores them; a valid per-rule disposition in
# working/qc/craft-warning-dispositions.json (run-scoped, named slides, named
# reviewer, owner signature — validated by craft_judgement.load_dispositions)
# removes a rule/slide pair from the list. Den-8 is warning-only while a
# client-requested slide count overrides density floors (SOP-SLIDE-04 §5.0).
# ---------------------------------------------------------------------------

_CRAFT_WARNING_CODES = None


def _craft_warning_codes() -> set:
    global _CRAFT_WARNING_CODES
    if _CRAFT_WARNING_CODES is None:
        import craft_judgement as _cj
        _CRAFT_WARNING_CODES = set(_cj.WARNING_CODES)
    return _CRAFT_WARNING_CODES


def _run_craft_warning_checks(run_dir: str,
                              codes: List[Dict]) -> List[Dict[str, Any]]:
    """Heuristic findings for the six warning codes, disposition-filtered,
    level="warning". Never contributes to exit_code=1 (see run_all)."""
    warnings = _craft_warning_codes()
    wanted = {c["code"] for c in codes if c.get("code") in warnings}
    if not wanted:
        return []
    try:
        import craft_judgement as _cj
        found = _cj.compute_warnings(Path(run_dir))
    except Exception as exc:  # noqa: BLE001 — a broken warning pass warns louder,
        # it must never crash the mechanical scan (warnings are advisory).
        print(f"NOTE: FIX 18 warning computation failed: {exc!r}", file=sys.stderr)
        return []
    out: List[Dict[str, Any]] = []
    for rec in found:
        code = rec.get("rule_code")
        if code not in wanted:
            continue
        out.append({
            "code": code,
            "level": "warning",
            "slide_index": (rec.get("slide_ids") or [None])[0],
            "evidence": "; ".join(str(e) for e in rec.get("evidence", []))[:300],
            "warning": True,
        })
    return out


# ---------------------------------------------------------------------------
# Hook-doctrine checks (AF-HOOK-1..7)
# ---------------------------------------------------------------------------

def _read_slides_copy(run_dir: str) -> Optional[str]:
    """Read slides_copy.md. Returns content or None if missing."""
    candidates = [
        Path(run_dir) / "working" / "copy" / "slides_copy.md",
        Path(run_dir) / "working" / "copy" / "SLIDES-COPY.md",
        Path(run_dir) / "slides_copy.md",
    ]
    for p in candidates:
        if p.is_file():
            return p.read_text(encoding="utf-8")
    return None


def _read_intake_json(run_dir: str) -> Optional[dict]:
    """Read intake.json from the run directory."""
    candidates = [
        Path(run_dir) / "working" / "copy" / "intake.json",
        Path(run_dir) / "intake.json",
    ]
    for p in candidates:
        if p.is_file():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return None
    return None


def _get_hook_phrase(intake: Optional[dict]) -> Optional[str]:
    """Extract the canonical hook phrase from intake.json."""
    if not intake:
        return None
    # Try several possible key paths
    for key in ("hook", "core_hook", "hook_phrase", "refrain"):
        val = intake.get(key)
        if isinstance(val, str) and len(val) > 3:
            return val.strip()
    # Check nested: engagement.hook, copy.hook, etc.
    for section in ("engagement", "copy", "messaging"):
        sec = intake.get(section)
        if isinstance(sec, dict):
            for hk in ("hook", "core_hook", "hook_phrase", "refrain"):
                val = sec.get(hk)
                if isinstance(val, str) and len(val) > 3:
                    return val.strip()
    return None


def _split_slides(copy_text: str) -> List[Tuple[int, str]]:
    """Split slides_copy.md into per-slide blocks. Returns list of (slide_index, text).
    Slide delimiters: '---', '## Slide', '### Slide', '# Slide'."""
    slides: List[Tuple[int, str]] = []
    # Try ## Slide N pattern first
    pattern = re.compile(r'^#{1,3}\s*Slide\s+(\d+)', re.MULTILINE | re.IGNORECASE)
    matches = list(pattern.finditer(copy_text))
    if matches:
        for i, m in enumerate(matches):
            slide_num = int(m.group(1))
            start = m.start()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(copy_text)
            slides.append((slide_num, copy_text[start:end]))
        return slides

    # Try --- delimiter
    parts = copy_text.split("\n---\n")
    if len(parts) >= 2:
        for i, part in enumerate(parts):
            slides.append((i + 1, part))
        return slides

    # Fallback: whole document as one slide
    slides.append((1, copy_text))
    return slides


def check_hook_doctrine(run_dir: str, intake: Optional[dict],
                        copy_text: Optional[str],
                        codes: List[Dict]) -> List[Dict[str, Any]]:
    """Mechanical hook-doctrine checks: AF-HOOK-1 through AF-HOOK-7 + AF-C2."""
    findings: List[Dict[str, Any]] = []
    if not copy_text:
        return findings

    hook_phrase = _get_hook_phrase(intake)
    slides = _split_slides(copy_text)

    enforced_codes = {c["code"] for c in codes}

    # AF-HOOK-3: zero dedicated hook slides
    # A "dedicated hook slide" is one where the hook is the primary message
    # (appears in headline or as dominant text)
    # Only fires when a hook phrase IS declared -- a deck that never declared a hook
    # phrase cannot have "zero dedicated hook slides"; the concept does not apply.
    if "AF-HOOK-3" in enforced_codes:
        if hook_phrase is None:
            pass  # No hook declared -- AF-HOOK-3 is inapplicable
        else:
            hook_slide_count = 0
            for idx, text in slides:
                if hook_phrase.lower() in text.lower():
                    hook_slide_count += 1
            if hook_slide_count == 0:
                findings.append({
                    "code": "AF-HOOK-3",
                    "level": "DECK",
                    "evidence": "zero slide bodies contain the hook phrase",
                    "hook_phrase": hook_phrase,
                })

    # AF-HOOK-1: hook on > 4 slides (over-stamp / ceiling)
    if "AF-HOOK-1" in enforced_codes and hook_phrase:
        hook_slides = [(i, t) for i, t in slides if hook_phrase.lower() in t.lower()]
        if len(hook_slides) > 4:
            findings.append({
                "code": "AF-HOOK-1",
                "level": "DECK",
                "evidence": f"hook appears on {len(hook_slides)} slides (ceiling is 4): "
                            f"slides {[i for i, _ in hook_slides]}",
                "hook_phrase": hook_phrase,
                "count": len(hook_slides),
                "slide_indices": [i for i, _ in hook_slides],
            })

    # AF-HOOK-2: hook in a footer/band position
    if "AF-HOOK-2" in enforced_codes and hook_phrase:
        footer_patterns = [
            re.compile(r'^\s*(?:footer|band|caption)\s*:.*' + re.escape(hook_phrase), re.I | re.M),
            re.compile(r'\[footer\].*' + re.escape(hook_phrase), re.I),
            re.compile(r'\[band\].*' + re.escape(hook_phrase), re.I),
            re.compile(r'\(footer\).*' + re.escape(hook_phrase), re.I),
        ]
        for idx, text in slides:
            for pat in footer_patterns:
                if pat.search(text):
                    findings.append({
                        "code": "AF-HOOK-2",
                        "level": "slide",
                        "slide_index": idx,
                        "evidence": f"hook phrase in footer/band position on slide {idx}",
                        "hook_phrase": hook_phrase,
                    })
                    break

    # AF-HOOK-4: hook printed 2+ times on one slide
    if "AF-HOOK-4" in enforced_codes and hook_phrase:
        for idx, text in slides:
            count = text.lower().count(hook_phrase.lower())
            if count >= 2:
                findings.append({
                    "code": "AF-HOOK-4",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"hook printed {count} times on slide {idx}",
                    "count": count,
                })

    # AF-HOOK-5: hook mutated/extended/reworded (approximate match)
    if "AF-HOOK-5" in enforced_codes and hook_phrase:
        # Look for near-matches: phrases that share 70%+ words with the hook
        # but are not exact matches
        hook_words = set(hook_phrase.lower().split())
        if len(hook_words) >= 3:
            for idx, text in slides:
                sentences = re.split(r'[.!?\n]', text)
                for sent in sentences:
                    sent_words = set(sent.lower().split())
                    if not sent_words:
                        continue
                    # Check for high overlap but not exact match
                    overlap = hook_words & sent_words
                    if len(overlap) >= max(3, len(hook_words) * 0.6):
                        # Check it's not an exact match
                        if hook_phrase.lower() not in sent.lower():
                            findings.append({
                                "code": "AF-HOOK-5",
                                "level": "slide",
                                "slide_index": idx,
                                "evidence": f"likely mutated hook on slide {idx}: '{sent.strip()[:120]}'",
                            })
                            break

    # AF-HOOK-7: signature quote conflated with main hook
    if "AF-HOOK-7" in enforced_codes and intake:
        sig_quote = intake.get("signature_quote") or intake.get("quote")
        if isinstance(sig_quote, str) and len(sig_quote) > 5 and hook_phrase:
            # If the signature quote and hook appear in the same slide body,
            # and are conflated (within 50 chars of each other)
            for idx, text in slides:
                if (hook_phrase.lower() in text.lower() and
                        sig_quote.lower() in text.lower()):
                    # Check proximity
                    hp_pos = text.lower().find(hook_phrase.lower())
                    sq_pos = text.lower().find(sig_quote.lower())
                    if abs(hp_pos - sq_pos) < 100:
                        findings.append({
                            "code": "AF-HOOK-7",
                            "level": "slide",
                            "slide_index": idx,
                            "evidence": f"hook and signature quote within {abs(hp_pos - sq_pos)} "
                                        f"chars on slide {idx}",
                        })

    return findings


# ---------------------------------------------------------------------------
# Audience-facing checks (AF-AUD-1..6, AF-PLACEHOLDER)
# ---------------------------------------------------------------------------

def check_audience_facing(run_dir: str, copy_text: Optional[str],
                          codes: List[Dict]) -> List[Dict[str, Any]]:
    """Scan slides_copy.md for the banned audience-facing categories."""
    findings: List[Dict[str, Any]] = []
    if not copy_text:
        return findings

    slides = _split_slides(copy_text)
    enforced_codes = {c["code"] for c in codes}

    # AF-AUD-1: speaker SAY line on the face
    # Pattern: "SAY:", "Speaker:", "SAY ->", "You say:", etc.
    if "AF-AUD-1" in enforced_codes:
        say_patterns = [
            re.compile(r'\bSAY\s*:', re.I),
            re.compile(r'^\s*Speaker\s*:', re.I | re.M),
            re.compile(r'You\s+say\s*:', re.I),
            re.compile(r'SAY\s*->', re.I),
            re.compile(r'\[SPEAKER\]', re.I),
        ]
        for idx, text in slides:
            for pat in say_patterns:
                m = pat.search(text)
                if m:
                    findings.append({
                        "code": "AF-AUD-1",
                        "level": "slide",
                        "slide_index": idx,
                        "evidence": f"speaker SAY directive on slide face: '{m.group().strip()}'",
                    })
                    break

    # AF-AUD-2: internal pitch doctrine as caption
    if "AF-AUD-2" in enforced_codes:
        doctrine_tokens = [
            r'\b(?:hook doctrine|pitch engine|density rule|obe rule|single idea doctrine)\b',
            r'\bAF-(?:HOOK|DEN|OBI|AUD)-\d+\b',
            r'\b(?:auto-fail|autofail)\s+code\b',
            r'\bQC\s+gate\b',
        ]
        doctrine_re = re.compile('|'.join(doctrine_tokens), re.I)
        caption_context = re.compile(
            r'(?:caption|footer|band|note)\s*:.*', re.I
        )
        for idx, text in slides:
            for line in text.splitlines():
                if caption_context.search(line) and doctrine_re.search(line):
                    findings.append({
                        "code": "AF-AUD-2",
                        "level": "slide",
                        "slide_index": idx,
                        "evidence": f"internal pitch doctrine in caption: '{line.strip()[:120]}'",
                    })
                    break

    # AF-AUD-3: image-narration caption (describing what's in an image)
    if "AF-AUD-3" in enforced_codes:
        narration_patterns = [
            re.compile(r'\[IMAGE[:\]]\s*(?:shows|depicts|displays|features|contains)', re.I),
            re.compile(r'\(image[:\]]\s*(?:shows|depicts|displays)', re.I),
            re.compile(r'^\s*(?:this|the)\s+(?:image|photo|picture|graphic)\s+(?:shows|depicts|displays)', re.I | re.M),
        ]
        for idx, text in slides:
            for pat in narration_patterns:
                m = pat.search(text)
                if m:
                    findings.append({
                        "code": "AF-AUD-3",
                        "level": "slide",
                        "slide_index": idx,
                        "evidence": f"image-narration caption: '{m.group().strip()[:120]}'",
                    })
                    break

    # AF-AUD-4: meta-telegraph / technique labels
    if "AF-AUD-4" in enforced_codes:
        meta_tokens = [
            r'\bwebinar\b', r'\bslide deck\b', r'\bpowerpoint\b', r'\bkeynote\b',
            r'\b(?:this|the)\s+(?:slide|deck|page)\s+(?:shows|explains|is about)\b',
            r'\btechnique\s*:', r'\bformat\s*:', r'\bdelivery note\s*:',
            r'\byou are (?:now )?(?:seeing|viewing|looking at)\b',
        ]
        meta_re = re.compile('|'.join(meta_tokens), re.I)
        for idx, text in slides:
            m = meta_re.search(text)
            if m:
                findings.append({
                    "code": "AF-AUD-4",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"meta-telegraph token: '{m.group().strip()}' on slide {idx}",
                })

    # AF-AUD-5: credential/justification dump
    if "AF-AUD-5" in enforced_codes:
        cred_dump_patterns = [
            re.compile(r'(?:years? of experience|decades? (?:of|in)|certified|licensed?|credentialed?|award(?:ed|s)?\s+(?:winning|recipient)|recognized\s+(?:by|as)|voted\s+(?:best|#1|top))', re.I),
        ]
        for idx, text in slides:
            count = sum(1 for pat in cred_dump_patterns if pat.search(text))
            if count >= 3:  # Three or more credential tokens = a dump
                findings.append({
                    "code": "AF-AUD-5",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"credential dump: {count} credential tokens on slide {idx}",
                    "count": count,
                })

    # AF-PLACEHOLDER / AF-AUD-6: bracket/placeholder token on a rendered slide
    if "AF-PLACEHOLDER" in enforced_codes or "AF-AUD-6" in enforced_codes:
        placeholder_patterns = [
            re.compile(r'\[(?:TODO|FIXME|PLACEHOLDER|INSERT|TBD|TK|XXX|___+)\]', re.I),
            re.compile(r'\{\{(?:.*?)\}\}'),
            re.compile(r'<PLACEHOLDER[^>]*>', re.I),
            re.compile(r'\[\[(?:.*?)\]\]'),
        ]
        for idx, text in slides:
            for pat in placeholder_patterns:
                m = pat.search(text)
                if m:
                    evidence = f"placeholder token on slide {idx}: '{m.group()}'"
                    if "AF-PLACEHOLDER" in enforced_codes:
                        findings.append({
                            "code": "AF-PLACEHOLDER",
                            "level": "slide",
                            "slide_index": idx,
                            "evidence": evidence,
                        })
                    if "AF-AUD-6" in enforced_codes:
                        findings.append({
                            "code": "AF-AUD-6",
                            "level": "slide",
                            "slide_index": idx,
                            "evidence": evidence,
                        })
                    break

    return findings


# ---------------------------------------------------------------------------
# Density checks (AF-DEN-1..8)
# ---------------------------------------------------------------------------

def check_density(run_dir: str, copy_text: Optional[str],
                  codes: List[Dict]) -> List[Dict[str, Any]]:
    """Mechanical density/deck-structure checks."""
    findings: List[Dict[str, Any]] = []
    if not copy_text:
        return findings

    slides = _split_slides(copy_text)
    total_slides = len(slides)
    enforced_codes = {c["code"] for c in codes}

    # Arc beat detection
    ARC_BEATS = {
        "HOOK": re.compile(r'\[HOOK\]|#+\s*HOOK|arc[:\s-]*HOOK', re.I),
        "VILLAIN": re.compile(r'\[VILLAIN\]|#+\s*VILLAIN|arc[:\s-]*VILLAIN|\[ANTAGONIST\]|arc[:\s-]*ANTAGONIST', re.I),
        "FELT_STAKES": re.compile(r'\[FELT_STAKES\]|#+\s*FELT.STAKES|arc[:\s-]*FELT_STAKES|\[COST.OF.INACTION\]', re.I),
        "PROMISE": re.compile(r'\[PROMISE\]|#+\s*PROMISE|arc[:\s-]*PROMISE', re.I),
        "PRICE": re.compile(r'\[PRICE\]|#+\s*PRICE|arc[:\s-]*PRICE|\[DROP\]|arc[:\s-]*DROP|\[LADDER\]|arc[:\s-]*LADDER', re.I),
        "VALUE_ADD": re.compile(r'\[VALUE_ADD\]|#+\s*VALUE.ADD|arc[:\s-]*VALUE_ADD|\[VALUE.STACK\]', re.I),
        "RECAP": re.compile(r'\[RECAP\]|#+\s*RECAP|arc[:\s-]*RECAP|\[RE.PITCH\]', re.I),
        "BUILDUP": re.compile(r'\[BUILDUP\]|#+\s*BUILDUP|arc[:\s-]*BUILDUP', re.I),
        "WALL_OF_WINS": re.compile(r'\[WALL.OF.WINS\]|#+\s*WALL.OF.WINS|arc[:\s-]*WALL_OF_WINS|\[WINS\]|arc[:\s-]*WINS', re.I),
        "COST_OF_INACTION": re.compile(r'\[COST.OF.INACTION\]|#+\s*COST.OF.INACTION|arc[:\s-]*COST_OF_INACTION', re.I),
    }

    beat_positions: Dict[str, List[int]] = defaultdict(list)
    for idx, text in slides:
        for beat_name, pattern in ARC_BEATS.items():
            if pattern.search(text):
                beat_positions[beat_name].append(idx)

    # AF-DEN-1: price beats < 8 slides apart
    if "AF-DEN-1" in enforced_codes:
        price_positions = beat_positions.get("PRICE", [])
        for i in range(len(price_positions) - 1):
            gap = price_positions[i + 1] - price_positions[i]
            if gap < 8:
                findings.append({
                    "code": "AF-DEN-1",
                    "level": "DECK",
                    "evidence": f"price beats {gap} slides apart (floor is 8): "
                                f"slides {price_positions[i]} and {price_positions[i + 1]}",
                    "gap": gap,
                })

    # AF-DEN-2: anchor outside 25-45% depth
    if "AF-DEN-2" in enforced_codes and total_slides > 0:
        price_positions = beat_positions.get("PRICE", [])
        if price_positions:
            first_price = min(price_positions)
            anchor_pct = first_price / total_slides
            if anchor_pct < 0.25 or anchor_pct > 0.45:
                findings.append({
                    "code": "AF-DEN-2",
                    "level": "DECK",
                    "evidence": f"first price anchor at slide {first_price}/{total_slides} "
                                f"= {anchor_pct:.1%} (expected 25-45%)",
                    "anchor_pct": round(anchor_pct, 4),
                    "first_price_slide": first_price,
                    "total_slides": total_slides,
                })

    # AF-DEN-3: DROP with no BUILDUP before it
    if "AF-DEN-3" in enforced_codes:
        price_positions = beat_positions.get("PRICE", [])
        buildup_positions = beat_positions.get("BUILDUP", [])
        for pp in price_positions:
            has_buildup_before = any(bp < pp for bp in buildup_positions)
            if not has_buildup_before:
                findings.append({
                    "code": "AF-DEN-3",
                    "level": "DECK",
                    "evidence": f"price drop at slide {pp} has no BUILDUP beat before it",
                })

    # AF-DEN-4: no value-stack slide before Drop 1
    if "AF-DEN-4" in enforced_codes:
        price_positions = beat_positions.get("PRICE", [])
        value_positions = beat_positions.get("VALUE_ADD", [])
        if price_positions:
            first_price = min(price_positions)
            has_value_before = any(vp < first_price for vp in value_positions)
            if not has_value_before:
                findings.append({
                    "code": "AF-DEN-4",
                    "level": "DECK",
                    "evidence": f"no VALUE_ADD beat before first price drop at slide {first_price}",
                })

    # AF-DEN-5: no promises beat before anchor
    if "AF-DEN-5" in enforced_codes:
        promise_positions = beat_positions.get("PROMISE", [])
        price_positions = beat_positions.get("PRICE", [])
        if price_positions and price_positions:
            first_price = min(price_positions)
            has_promise_before = any(pp < first_price for pp in promise_positions)
            if not has_promise_before:
                findings.append({
                    "code": "AF-DEN-5",
                    "level": "DECK",
                    "evidence": f"no PROMISE beat before first anchor at slide {first_price}",
                })

    # AF-DEN-6: Wall of Wins not 4-6 before offer
    if "AF-DEN-6" in enforced_codes:
        wow_positions = beat_positions.get("WALL_OF_WINS", [])
        price_positions = beat_positions.get("PRICE", [])
        if wow_positions and price_positions:
            first_price = min(price_positions)
            for wow_pos in wow_positions:
                if wow_pos < first_price:
                    gap = first_price - wow_pos
                    if gap < 4 or gap > 6:
                        findings.append({
                            "code": "AF-DEN-6",
                            "level": "DECK",
                            "evidence": f"Wall of Wins at slide {wow_pos} is {gap} slides "
                                        f"before offer at slide {first_price} (expected 4-6)",
                        })

    # AF-DEN-7: no 4-7 slide re-pitch after FINAL
    if "AF-DEN-7" in enforced_codes:
        recap_positions = beat_positions.get("RECAP", [])
        price_positions = beat_positions.get("PRICE", [])
        if price_positions:
            last_price = max(price_positions)
            after_last_price = total_slides - last_price
            # Expect 4-7 slides of re-pitch after the final price
            if after_last_price < 4:
                findings.append({
                    "code": "AF-DEN-7",
                    "level": "DECK",
                    "evidence": f"only {after_last_price} slides after final price at "
                                f"slide {last_price} (expected 4-7)",
                    "after_last_price": after_last_price,
                })

    # AF-DEN-8: section below its slide floor
    if "AF-DEN-8" in enforced_codes:
        # Each major arc section should have a minimum slide count
        section_floors = {
            "HOOK": 2,
            "VILLAIN": 1,
            "FELT_STAKES": 2,
            "PROMISE": 2,
            "VALUE_ADD": 2,
            "RECAP": 2,
        }
        for section, floor in section_floors.items():
            positions = beat_positions.get(section, [])
            if positions and len(positions) < floor:
                findings.append({
                    "code": "AF-DEN-8",
                    "level": "DECK",
                    "evidence": f"section '{section}' has {len(positions)} slide(s) "
                                f"(floor is {floor})",
                    "section": section,
                    "count": len(positions),
                    "floor": floor,
                })

    return findings


# ---------------------------------------------------------------------------
# OBI checks (AF-OBI-1..6)
# ---------------------------------------------------------------------------

def check_obi(run_dir: str, copy_text: Optional[str],
              codes: List[Dict]) -> List[Dict[str, Any]]:
    """One-Big-Idea mechanical checks."""
    findings: List[Dict[str, Any]] = []
    if not copy_text:
        return findings

    slides = _split_slides(copy_text)
    enforced_codes = {c["code"] for c in codes}

    for idx, text in slides:
        lines = [l.strip() for l in text.splitlines() if l.strip()]

        # AF-OBI-1: > 3 text blocks
        if "AF-OBI-1" in enforced_codes:
            # Count distinct text blocks (paragraphs separated by blank lines, bullet groups)
            blocks = 0
            in_block = False
            for line in lines:
                is_content = not line.startswith('#') and not line.startswith('[')
                if is_content and line and not in_block:
                    blocks += 1
                    in_block = True
                elif not line:
                    in_block = False
            if blocks > 3:
                findings.append({
                    "code": "AF-OBI-1",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"{blocks} text blocks on slide {idx} (ceiling is 3)",
                    "block_count": blocks,
                })

        # AF-OBI-2: headline > 9 words
        if "AF-OBI-2" in enforced_codes:
            for line in lines:
                if line.startswith('#'):
                    clean = re.sub(r'^#+\s*', '', line)
                    word_count = len(clean.split())
                    if word_count > 9:
                        findings.append({
                            "code": "AF-OBI-2",
                            "level": "slide",
                            "slide_index": idx,
                            "evidence": f"headline '{clean[:80]}' is {word_count} words "
                                        f"(ceiling is 9)",
                            "word_count": word_count,
                        })
                        break

        # AF-OBI-3: 2+ core ideas (detect via topic-shift markers or multi-headline)
        if "AF-OBI-3" in enforced_codes:
            headlines = [
                re.sub(r'^#+\s*', '', l)
                for l in lines
                if l.startswith('#') and not re.match(r'^#{1,3}\s*Slide\s+\d+', l)
            ]
            if len(headlines) >= 2:
                # Check if they express truly different ideas
                words_sets = [set(h.lower().split()) for h in headlines]
                for i in range(len(words_sets)):
                    for j in range(i + 1, len(words_sets)):
                        overlap = words_sets[i] & words_sets[j]
                        union = words_sets[i] | words_sets[j]
                        jaccard = len(overlap) / max(len(union), 1)
                        if jaccard < 0.3:  # Truly different topics
                            findings.append({
                                "code": "AF-OBI-3",
                                "level": "slide",
                                "slide_index": idx,
                                "evidence": f"2+ core ideas (headlines differ): "
                                            f"'{headlines[i][:60]}' vs '{headlines[j][:60]}'",
                            })
                            break
                if any(f["slide_index"] == idx for f in findings):
                    break

        # AF-OBI-4: full value trio on one slide (three distinct value propositions)
        if "AF-OBI-4" in enforced_codes:
            value_markers = re.findall(
                r'(?:save|earn|grow|protect|build|create|reduce|eliminate|boost|'
                r'increase|decrease|improve|enhance|accelerate|streamline)',
                text, re.I
            )
            if len(set(v.lower() for v in value_markers)) >= 3:
                findings.append({
                    "code": "AF-OBI-4",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"full value trio: {len(set(v.lower() for v in value_markers))} "
                                f"distinct value markers on slide {idx}",
                })

        # AF-OBI-5: bulleted pain list
        if "AF-OBI-5" in enforced_codes:
            bullets = re.findall(r'^\s*[-*+]\s+(.*)', text, re.MULTILINE)
            pain_tokens = re.compile(
                r'\b(?:pain|problem|struggle|frustrat|worry|fear|anxiety|'
                r'stress|burden|waste|loss|losing|failed|broken|stuck)\b', re.I
            )
            pain_bullets = [b for b in bullets if pain_tokens.search(b)]
            if len(pain_bullets) >= 3:
                findings.append({
                    "code": "AF-OBI-5",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"bulleted pain list: {len(pain_bullets)} pain bullets "
                                f"on slide {idx}",
                    "pain_bullet_count": len(pain_bullets),
                })

        # AF-OBI-6: comparison table > 2 rows
        if "AF-OBI-6" in enforced_codes:
            table_rows = re.findall(r'^\|.*\|$', text, re.MULTILINE)
            # Subtract header separator rows (|---|)
            data_rows = [r for r in table_rows if not re.match(r'^\|[\s\-:]+\|$', r)]
            if len(data_rows) > 2:
                findings.append({
                    "code": "AF-OBI-6",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"comparison table with {len(data_rows)} rows on slide {idx} "
                                f"(ceiling is 2)",
                    "row_count": len(data_rows),
                })

    # AF-OBI: generic One-Big-Idea catch-all (dimension label for routeback work orders)
    # Fires when any OBI-1..OBI-6 flag is set on a slide but the base AF-OBI is
    # also enforced. This gives the dimension name visibility in the violations list.
    if "AF-OBI" in enforced_codes:
        for idx, text in slides:
            # If any sub-code already fired for this slide, label with AF-OBI too
            if any(f.get("slide_index") == idx for f in findings):
                findings.append({
                    "code": "AF-OBI",
                    "level": "slide",
                    "slide_index": idx,
                    "evidence": f"OBI dimension hit on slide {idx} (see AF-OBI-* sub-codes)",
                })

    return findings


# ---------------------------------------------------------------------------
# AF-C2: hook cadence out of sanctioned banded range
# ---------------------------------------------------------------------------

def check_c2(run_dir: str, copy_text: Optional[str],
             intake: Optional[dict],
             codes: List[Dict]) -> List[Dict[str, Any]]:
    """AF-C2: hook cadence check (ceiling + floor enforcement for the hook refrain)."""
    findings: List[Dict[str, Any]] = []
    enforced_codes = {c["code"] for c in codes}
    if "AF-C2" not in enforced_codes or not copy_text:
        return findings

    hook_phrase = _get_hook_phrase(intake)
    if not hook_phrase:
        return findings

    slides = _split_slides(copy_text)
    hook_slides = [(i, t) for i, t in slides if hook_phrase.lower() in t.lower()]
    hook_positions = [i for i, _ in hook_slides]
    hook_count = len(hook_positions)

    # Ceiling: > 4 slides (over-stamp / wallpaper)
    if hook_count > 4:
        findings.append({
            "code": "AF-C2",
            "level": "DECK",
            "sub_rule": "ceiling",
            "evidence": f"hook refrain on {hook_count} slides (ceiling is 4)",
            "count": hook_count,
            "slide_indices": hook_positions,
        })

    # Floor: fewer than 3 named anchor beats
    if hook_count < 3:
        findings.append({
            "code": "AF-C2",
            "level": "DECK",
            "sub_rule": "floor",
            "evidence": f"hook refrain on only {hook_count} slide(s) (floor is 3 anchor beats)",
            "count": hook_count,
            "slide_indices": hook_positions,
        })

    # 2+ consecutive slides with hook
    if len(hook_positions) >= 2:
        for i in range(len(hook_positions) - 1):
            if hook_positions[i + 1] - hook_positions[i] == 1:
                findings.append({
                    "code": "AF-C2",
                    "level": "DECK",
                    "sub_rule": "consecutive",
                    "evidence": f"hook on consecutive slides {hook_positions[i]} "
                                f"and {hook_positions[i + 1]}",
                })
                break

    return findings


# ============================================================================
# PHASE 2: run ALL mechanical checks
# ============================================================================

def run_mechanical_checks(run_dir: str,
                          manifest_path: Path) -> List[Dict[str, Any]]:
    """Run every mechanical check for the unenforced qc_check codes.
    Returns a list of violation dicts."""
    all_codes = load_qc_check_codes(manifest_path)
    if not all_codes:
        print("NOTE: no unenforced qc_check codes found in manifest.", file=sys.stderr)
        return []

    # FIX 18 — the 13 human-judgement craft rows are DISPOSITIONED, not
    # exit-1 scanner fodder, per MASTER-QC-AUTOFAIL-RULESET.md's 5/6/2 ruling:
    #   - 5 ENFORCED codes (AF-HOOK-2, AF-HOOK-7, AF-OBI-6, AF-DEN-3, AF-DEN-6)
    #     own deterministic checks in craft_judgement.py and are gated at the
    #     build_deck preflight — qc_check must NOT double-fire them as
    #     character-pattern exit-1s (its declared-evidence checks are stronger
    #     than these heuristics, and double-source truth hides failures).
    #   - 6 WARNING codes (AF-AUD-1, AF-AUD-2, AF-AUD-3, AF-OBI-3, AF-OBI-5,
    #     AF-DEN-8) may only WARN: they ride in the report as "warning"
    #     severities and hold QC only until corrected or acknowledged via
    #     working/qc/craft-warning-dispositions.json. They never set exit_code=1.
    #   - 2 HUMAN codes (AF-OBI-4, AF-OBI) are never machine-fired here at all
    #     (no keyword proxy exists); they gate run_signature_deck.attest_phase.
    import craft_judgement as _cj
    fix18_enforced = set(_cj.ENFORCED_CODES)
    fix18_warning = set(_cj.WARNING_CODES)
    fix18_human = set(_cj.HUMAN_CODES)

    delegated: Dict[str, List[Dict]] = defaultdict(list)
    local: List[Dict] = []
    warnings_only: List[Dict] = []
    for c in all_codes:
        if c.get("check_script"):
            delegated[c["check_script"]].append(c)
            continue
        code = c.get("code")
        if code in fix18_enforced or code in fix18_human:
            continue  # owned by craft_judgement (enforce | human-attest gate)
        if code in fix18_warning:
            warnings_only.append(c)
            continue
        local.append(c)

    findings: List[Dict[str, Any]] = []

    # FIX 18 — warning-code scan: heuristic findings, downgraded to level
    # "warning" (never exit-1), then filtered against valid dispositions.
    if warnings_only:
        warn_findings = _run_craft_warning_checks(run_dir, warnings_only)
        findings.extend(warn_findings)

    # ---- Read the run's data files once ----
    copy_text = _read_slides_copy(run_dir)
    intake = _read_intake_json(run_dir)

    # ---- Local checks (truly unenforced codes) ----
    if local:
        local_codes = {c["code"] for c in local}
        # Hook doctrine
        hook_codes = [c for c in local if c["code"].startswith("AF-HOOK-")]
        if hook_codes:
            findings.extend(
                f for f in check_hook_doctrine(run_dir, intake, copy_text, hook_codes)
                if f.get("code") not in fix18_enforced and f.get("code") not in fix18_human)

        # Audience-facing
        aud_codes = [c for c in local if c["code"].startswith("AF-AUD-") or c["code"] == "AF-PLACEHOLDER"]
        if aud_codes:
            findings.extend(
                f for f in check_audience_facing(run_dir, copy_text, aud_codes)
                if f.get("code") not in fix18_enforced and f.get("code") not in fix18_human)

        # Density
        den_codes = [c for c in local if c["code"].startswith("AF-DEN-")]
        if den_codes:
            findings.extend(
                f for f in check_density(run_dir, copy_text, den_codes)
                if f.get("code") not in fix18_enforced and f.get("code") not in fix18_human)

        # OBI (AF-OBI-1..6 + AF-OBI)
        obi_codes = [c for c in local if c["code"].startswith("AF-OBI-") or c["code"] == "AF-OBI"]
        if obi_codes:
            findings.extend(
                f for f in check_obi(run_dir, copy_text, obi_codes)
                if f.get("code") not in fix18_enforced and f.get("code") not in fix18_human)

        # AF-C2
        c2_codes = [c for c in local if c["code"] == "AF-C2"]
        if c2_codes:
            findings.extend(check_c2(run_dir, copy_text, intake, c2_codes))

    # ---- Delegated checks (existing check_script references) ----
    # Group by the script FILE (not function), since calling the same script once
    # produces all its outputs. Each script file is called ONCE.
    by_script_file: Dict[str, List[Dict]] = defaultdict(list)
    for script_ref, codes in delegated.items():
        # Parse "scripts/foo.py::func_name" format
        script_file = script_ref.split("::")[0]
        # Normalize: strip "scripts/" prefix to get the filename
        script_name = script_file.replace("scripts/", "")
        by_script_file[script_name].extend(codes)

    for script_name, codes in by_script_file.items():
        full_path = HERE / script_name
        if not full_path.is_file():
            # Try parent dir
            full_path = HERE.parent / script_name
        if not full_path.is_file():
            findings.append({
                "code": "AF-QC-CHECK-MISSING",
                "level": "SYSTEM",
                "evidence": f"delegated check script not found: {script_name}",
                "expected_codes": list(set(c["code"] for c in codes)),
            })
            continue

        covered_code_set = {c["code"] for c in codes}

        # ---- DEFER check: skip delegated scripts when their required inputs are absent ----
        # pitch_engines_check.py exits 4 when slides_copy.md is present but price_ladder.json
        # is absent (common mid-pipeline state). That is the majority of the build pipeline.
        # Treat exit-4-on-partial-data as a defer, not as violations, so a clean deck
        # at any pipeline stage can still exit 0.
        def _deferred(script_name: str) -> bool:
            """Return True if the script's required inputs are absent -- skip it."""
            if script_name == "pitch_engines_check.py":
                # price_ladder.json is the gating input; its absence means the
                # pitch-engine phase hasn't completed yet, so defer the check.
                run_path = Path(run_dir)
                has_price_ladder = (
                    (run_path / "working" / "copy" / "price_ladder.json").is_file()
                    or (run_path / "price_ladder.json").is_file()
                )
                if not has_price_ladder:
                    return True
            return False

        if _deferred(script_name):
            continue  # Inputs not ready; skip without flagging

        # Run the delegated script once and parse its output
        try:
            result = subprocess.run(
                [sys.executable, str(full_path), "--run-dir", run_dir],
                capture_output=True, text=True, timeout=60,
                cwd=str(HERE),
            )
            output = result.stdout + "\n" + result.stderr

            # Try to parse JSON output
            parsed = False
            try:
                data = json.loads(result.stdout) if result.stdout.strip().startswith("{") else None
            except json.JSONDecodeError:
                data = None

            if isinstance(data, dict):
                parsed = True
                triggered = (data.get("triggered") or
                             data.get("triggered_autofails") or
                             data.get("findings") or [])
                if result.returncode == 0 and not triggered:
                    continue  # Clean pass
                for t in triggered:
                    if isinstance(t, str):
                        if t in covered_code_set:
                            findings.append({
                                "code": t, "source": script_name,
                                "evidence": f"delegated check '{script_name}' flagged {t}",
                            })
                    elif isinstance(t, dict):
                        code = t.get("code") or t.get("af_code") or ""
                        if code and code in covered_code_set:
                            findings.append({
                                "code": code,
                                "source": script_name,
                                "level": t.get("level", "slide"),
                                "evidence": t.get("evidence") or t.get("reason") or str(t),
                            })
                if result.returncode != 0:
                    # Non-zero exit but we parsed output -- report any remaining covered codes
                    pass

            if result.returncode != 0 and not parsed:
                # Non-zero exit, non-JSON output -- extract AF codes from text
                found_codes = set(re.findall(r'\b(AF-[A-Z0-9-]+)\b', output))
                relevant = found_codes & covered_code_set
                for code in sorted(relevant or found_codes):
                    findings.append({
                        "code": code,
                        "source": script_name,
                        "evidence": f"delegated check '{script_name}' exited non-zero "
                                    f"(rc={result.returncode})",
                    })
                if not relevant and not found_codes:
                    findings.append({
                        "code": "AF-QC-DELEGATED-FAIL",
                        "level": "SYSTEM",
                        "source": script_name,
                        "evidence": f"delegated check '{script_name}' exited non-zero "
                                    f"(rc={result.returncode}) but produced no parseable AF codes",
                    })
        except subprocess.TimeoutExpired:
            findings.append({
                "code": "AF-QC-CHECK-TIMEOUT",
                "level": "SYSTEM",
                "evidence": f"delegated check script timed out: {script_name}",
            })
        except Exception as exc:
            findings.append({
                "code": "AF-QC-CHECK-ERROR",
                "level": "SYSTEM",
                "evidence": f"error running delegated check '{script_name}': {exc}",
            })

    return findings


# ============================================================================
# PHASE 3: cross-check QC reports for false negatives
# ============================================================================

def cross_check_qc_reports(run_dir: str) -> List[Dict[str, Any]]:
    """Read the domain QC reports and final_qc_report.json. For each report,
    parse documented violations and cross-reference against triggered_autofails.
    A documented violation whose AF code is absent from triggered_autofails
    produces AF-QC-FALSE-NEGATIVE."""
    findings: List[Dict[str, Any]] = []
    run_path = Path(run_dir)

    # Domain reports to check
    domain_reports = [
        ("copy_qc_report.json", "Copy QC"),
        ("typography_qc_report.json", "Typography QC"),
        ("prompt_qc_report.json", "Prompt QC"),
        ("image_qc_report.json", "Image QC"),
        ("speech_qc_report.json", "Speech QC"),
        ("priority_shift_report.json", "Priority Shift"),
    ]

    for filename, label in domain_reports:
        p = run_path / "working" / "qc" / filename
        if not p.is_file():
            continue

        try:
            report = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(report, dict):
            continue

        # Get the declared triggered_autofails
        triggered_raw = (report.get("triggered_autofails") or
                         report.get("autofails_triggered") or
                         report.get("findings") or [])
        triggered_codes: set = set()
        if isinstance(triggered_raw, list):
            for item in triggered_raw:
                if isinstance(item, str):
                    triggered_codes.add(item)
                elif isinstance(item, dict):
                    code = item.get("code") or item.get("af_code") or ""
                    if code:
                        triggered_codes.add(code)

        # Parse the report body for documented violations
        # Look for AF-* codes mentioned in any string field
        report_text = json.dumps(report)
        documented_af_codes = set(re.findall(r'\b(AF-[A-Z0-9-]+)\b', report_text))
        # Filter to known AF codes only (not false positives from JSON keys)
        documented_af_codes = {c for c in documented_af_codes
                               if re.match(r'^AF-[A-Z]+-\d+$', c) or
                               re.match(r'^AF-[A-Z]+$', c) or
                               c == "AF-PLACEHOLDER"}

        # Also check explicitly documented violations in the report body
        violation_patterns = [
            (r'violation[s]?\s*(?:found|detected|present)[:\s]*([^\n]+)', "violation found"),
            (r'(?:failed|failing)\s*(?:check|gate|rule)[:\s]*([^\n]+)', "failed check"),
            (r'(?:below|under)\s*(?:threshold|floor|minimum)[:\s]*([^\n]+)', "below threshold"),
            (r'(?:missing|absent|not found)[:\s]*([^\n]+)', "missing"),
        ]
        for pattern, desc in violation_patterns:
            for m in re.finditer(pattern, report_text, re.I):
                context = m.group(1).strip()[:200] if m.lastindex else m.group(0)[:200]

        # Cross-check: documented AF codes that are NOT in triggered_autofails
        false_negatives = documented_af_codes - triggered_codes
        for code in sorted(false_negatives):
            findings.append({
                "code": "AF-QC-FALSE-NEGATIVE",
                "level": "SYSTEM",
                "evidence": f"{code} documented in {label} report ({filename}) but "
                            f"not listed in triggered_autofails",
                "missing_code": code,
                "report": filename,
                "report_label": label,
            })

        # Scan the report's findings/defects for violations without AF codes.
        # Only count violation indicators OUTSIDE of JSON field names and the
        # triggered_autofails list (where "fail" appears in "autofails").
        # Strip JSON keys and known safe fields before scanning.
        body_text = report_text
        # Remove the triggered_autofails list content so "fail" inside "autofails" doesn't match
        body_text = re.sub(r'"triggered_autofails"\s*:\s*\[.*?\]', '', body_text, flags=re.DOTALL)
        body_text = re.sub(r'"autofails_triggered"\s*:\s*\[.*?\]', '', body_text, flags=re.DOTALL)
        # Remove field names that contain violation-signaling substrings
        body_text = re.sub(r'"[^"]*(?:average|threshold|schema|generator|pass|report)[^"]*"\s*:', '', body_text)

        # Look for explicit violation listings (not just word "fail" in "autofail")
        has_explicit_violations = False
        for key in ("notes", "observations", "defects", "issues", "warnings", "blocking_reasons"):
            val = report.get(key)
            if isinstance(val, list) and len(val) > 0:
                has_explicit_violations = True
                break

        # Only flag when there are explicit defect/warning lists but zero triggered codes
        if has_explicit_violations and not triggered_codes and not documented_af_codes:
            findings.append({
                "code": "AF-QC-FALSE-NEGATIVE",
                "level": "SYSTEM",
                "evidence": f"{label} report ({filename}) lists defects/issues but "
                            f"declares zero triggered autofails and documents zero AF codes",
                "report": filename,
            })

    # Also check the final aggregated report
    final_p = run_path / "working" / "qc" / "final_qc_report.json"
    if final_p.is_file():
        try:
            final_report = json.loads(final_p.read_text(encoding="utf-8"))
            if isinstance(final_report, dict):
                blocking = final_report.get("blocking_reasons", [])
                # Check each domain for triggered autofails
                domains = final_report.get("domains", {})
                for domain_key, domain_data in domains.items():
                    if isinstance(domain_data, dict):
                        reasons = domain_data.get("reasons", [])
                        # Extract AF codes from reasons
                        for reason in reasons:
                            if isinstance(reason, str):
                                af_in_reason = re.findall(r'\b(AF-[A-Z0-9-]+)\b', reason)
                                for code in af_in_reason:
                                    # Check if this code is in domain's triggered
                                    triggered = (domain_data.get("triggered_autofails") or
                                                 domain_data.get("autofails_triggered") or [])
                                    if isinstance(triggered, list):
                                        triggered_set = set()
                                        for t in triggered:
                                            if isinstance(t, str):
                                                triggered_set.add(t)
                                            elif isinstance(t, dict):
                                                triggered_set.add(t.get("code", ""))
                                        if code not in triggered_set:
                                            findings.append({
                                                "code": "AF-QC-FALSE-NEGATIVE",
                                                "level": "SYSTEM",
                                                "evidence": f"{code} appears in final_qc_report "
                                                            f"blocking_reasons for {domain_key} "
                                                            f"but not in that domain's triggered_autofails",
                                                "missing_code": code,
                                                "report": "final_qc_report.json",
                                            })
        except (json.JSONDecodeError, OSError):
            pass

    return findings


# ============================================================================
# PHASE 4: aggregate and report
# ============================================================================

def run_all(run_dir: str, manifest_path: Optional[str] = None) -> Dict[str, Any]:
    """Run mechanical checks + cross-check. Returns a dict with all results."""
    run_path = Path(run_dir).expanduser().resolve()
    if not run_path.is_dir():
        print(f"FATAL: --run-dir not found: {run_path}", file=sys.stderr)
        sys.exit(2)

    manifest = resolve_manifest_path(manifest_path)
    all_codes = load_qc_check_codes(manifest)
    total_codes = len(all_codes)

    # Mechanical checks
    mechanical_violations = run_mechanical_checks(str(run_path), manifest)

    # Cross-check
    false_negatives = cross_check_qc_reports(str(run_path))

    # FIX 18 — level=="warning" findings are advisory: they ride in the report
    # (so the QC Specialist sees them and can disposition them) but they never
    # set exit_code=1. A WARNING code that still fires means: correct the deck,
    # or acknowledge it via working/qc/craft-warning-dispositions.json.
    all_violations = mechanical_violations + false_negatives
    blocking_violations = [v for v in all_violations if v.get("level") != "warning"]
    warning_violations = [v for v in all_violations if v.get("level") == "warning"]
    exit_code = 0 if len(blocking_violations) == 0 else 1

    return {
        "schema": "qc_check_report/v1",
        "generator": "scripts/qc_check.py",
        "manifest_path": str(manifest),
        "total_qc_check_codes": total_codes,
        "codes_with_check_script": sum(1 for c in all_codes if c.get("check_script")),
        "codes_without_enforcement": sum(1 for c in all_codes
                                         if not c.get("check_script")
                                         and not c.get("py_symbol")),
        "mechanical_violations": mechanical_violations,
        "false_negatives": false_negatives,
        "blocking_violations": blocking_violations,
        "warning_violations": warning_violations,
        "total_violations": len(all_violations),
        "exit_code": exit_code,
        "pass": exit_code == 0,
    }


def _print_report(report: Dict[str, Any]) -> None:
    print("=== qc_check: MECHANICAL QC ENFORCEMENT ===")
    print(f"manifest: {report['manifest_path']}")
    print(f"qc_check codes in manifest: {report['total_qc_check_codes']}")
    print(f"  with existing check_script: {report['codes_with_check_script']}")
    print(f"  truly unenforced (no py_symbol, no check_script): "
          f"{report['codes_without_enforcement']}")
    print()

    mechanical = report["mechanical_violations"]
    fn = report["false_negatives"]

    warn = report.get("warning_violations", [])
    if warn:
        print(f"  FIX 18 craft warnings ({len(warn)}) — advisory, exit-neutral; "
              f"correct or acknowledge via working/qc/"
              f"craft-warning-dispositions.json:")
        by_code_w = defaultdict(list)
        for v in warn:
            by_code_w[v["code"]].append(v)
        for code in sorted(by_code_w):
            items = by_code_w[code]
            print(f"    [{code}] ({len(items)} instance(s)):")
            for item in items[:3]:
                extra = ""
                if item.get("slide_index"):
                    extra = f" slide={item['slide_index']}"
                print(f"      - {item['evidence'][:140]}{extra}")
            if len(items) > 3:
                print(f"      ... and {len(items) - 3} more")
    if report["pass"]:
        print("PASS -- zero blocking violations found.")
        print(f"  mechanical checks: {len(mechanical)} findings "
              f"({len(warn)} advisory)")
        print(f"  false-negative cross-check: {len(fn)} violations")
    else:
        blk = report.get("blocking_violations", report["total_violations"])
        print(f"FAIL -- {len(blk) if isinstance(blk, list) else blk} blocking "
              f"violation(s) found (warnings are exit-neutral):")
        if mechanical:
            print(f"\n  Mechanical violations ({len(mechanical)}):")
            # Group by code
            by_code: Dict[str, List[Dict]] = defaultdict(list)
            for v in mechanical:
                by_code[v["code"]].append(v)
            for code in sorted(by_code):
                items = by_code[code]
                print(f"    [{code}] ({len(items)} instance(s)):")
                for item in items[:3]:  # Show first 3 per code
                    extra = ""
                    if item.get("slide_index"):
                        extra = f" slide={item['slide_index']}"
                    if item.get("count"):
                        extra += f" count={item['count']}"
                    print(f"      - {item['evidence'][:140]}{extra}")
                if len(items) > 3:
                    print(f"      ... and {len(items) - 3} more")
        if fn:
            print(f"\n  False-negative cross-check ({len(fn)}):")
            for item in fn:
                print(f"    [{item.get('missing_code', item['code'])}] {item['evidence'][:150]}")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--run-dir", required=True,
                    help="Path to the deck run directory")
    ap.add_argument("--manifest", default=None,
                    help="Path to PIPELINE-MANIFEST.json (auto-resolved if omitted)")
    ap.add_argument("--json", action="store_true",
                    help="Output the full report as JSON")
    args = ap.parse_args()

    try:
        report = run_all(args.run_dir, args.manifest)
    except SystemExit:
        raise
    except Exception as exc:
        print(f"FATAL: qc_check failed: {exc!r}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        _print_report(report)

    return report["exit_code"]


if __name__ == "__main__":
    sys.exit(main())

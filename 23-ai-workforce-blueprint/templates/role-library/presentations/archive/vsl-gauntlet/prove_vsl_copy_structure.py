#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""prove_vsl_copy_structure.py — fail-closed prover for the VSL page
(presentations upsell pipeline, GAUNTLET-LOOP DESIGN-OPUS §6.1-6.5, §10.3).

Enforces the SACRED VSL structure declared in scripts/structure/vsl_structure.json, IN
ORDER, plus the email/phone gate's hard requirements:

  * a hero with a video player (video element / iframe / player div + a video URL)  -> AF-PRES-VSL-VIDEO-MISSING
  * the 5 canonical sections in canonical order   -> AF-PRES-VSL-SECTION-{COUNT,MISSING,UNKNOWN,ORDER}
  * per-section stripped-word band (measured)     -> AF-PRES-VSL-SECTION-BAND
  * the gate overlay is present AND carries email + first-name + cell-phone fields
    (all required)                                -> AF-PRES-VSL-GATE-FIELDS-MISSING
  * a real (non-static-mock) gate: a form embed
    (Skill-44 iframe/script embed) rather than a
    plain div with no form                        -> AF-PRES-VSL-GATE-NOT-REAL
  * the gate placement time is within [3:00, 8:00]
    (read from the video metadata object / vsl
    spec / gate_time_seconds)                     -> AF-PRES-VSL-GATE-BAND
  * the offer recap + a CTA + a brand footer are present  -> AF-PRES-VSL-RECAP-MISSING / -CTA-MISSING / -FOOTER-MISSING
  * gate must pause the video and resume on submit -> AF-PRES-VSL-GATE-PAUSE-RESUME-MISSING

Input modes:
  --html   <VSL page HTML fragment>   — element-ledger assertions on the page itself.
  --meta   <vsl_spec.json or gate metadata JSON> — the video metadata carrying duration /
           revelation timestamp / gate_time_seconds (the 3-8 min band check).
  --ledger <copy_ledger.json>         — Skill 56 copy-ledger pattern for VSL-stage assets.

stdlib only. Exit 0 = pass, 2 = violation (autofail), 3 = usage/IO (fail-closed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

EXIT_PASS = 0
EXIT_AUTOFAIL = 2
EXIT_USAGE = 3

AF_EMPTY = "AF-PRES-VSL-EMPTY"
AF_VIDEO = "AF-PRES-VSL-VIDEO-MISSING"
AF_GATE_FIELDS = "AF-PRES-VSL-GATE-FIELDS-MISSING"
AF_GATE_NOT_REAL = "AF-PRES-VSL-GATE-NOT-REAL"
AF_GATE_BAND = "AF-PRES-VSL-GATE-BAND"
AF_GATE_PAUSE = "AF-PRES-VSL-GATE-PAUSE-RESUME-MISSING"
AF_RECAP = "AF-PRES-VSL-RECAP-MISSING"
AF_CTA = "AF-PRES-VSL-CTA-MISSING"
AF_FOOTER = "AF-PRES-VSL-FOOTER-MISSING"
AF_COUNT = "AF-PRES-VSL-SECTION-COUNT"
AF_SECTION_MISSING = "AF-PRES-VSL-SECTION-MISSING"
AF_UNKNOWN = "AF-PRES-VSL-SECTION-UNKNOWN"
AF_ORDER = "AF-PRES-VSL-SECTION-ORDER"
AF_BAND = "AF-PRES-VSL-SECTION-BAND"
AF_STRUCTURE = "AF-PRES-VSL-STRUCTURE-LOAD"

_TAG_RE = re.compile(r"<[^>]+>")
_SCRIPT_DIR = Path(__file__).resolve().parent
STRUCTURE = _SCRIPT_DIR / "structure" / "vsl_structure.json"

# The 3-8 minute gate band, in seconds (DESIGN-OPUS §6.3).
GATE_BAND_MIN = 180
GATE_BAND_MAX = 480


def _norm(s: Any) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def _strip_tags(blob: Any) -> str:
    return _TAG_RE.sub(" ", str(blob or ""))


def _stripped_words(blob: Any) -> int:
    return len([w for w in re.split(r"\s+", _strip_tags(blob).strip()) if w])


def _phrase_present(norm_text: str, phrase: str) -> bool:
    p = _norm(phrase)
    if not p or not norm_text:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(p) + r"(?![a-z0-9])", norm_text) is not None


def _load_canonical() -> Dict[str, Any]:
    return json.loads(STRUCTURE.read_text(encoding="utf-8"))


def _sections(canon: Dict[str, Any]) -> List[Dict[str, Any]]:
    return canon["sections"]


def _body(html: str) -> str:
    low = html.lower()
    m = re.search(r"<body[^>]*>(.*)</body>", low, re.S)
    if m:
        return html[m.start(1):m.end(1)]
    m = re.search(r"</head[^>]*>", low, re.S)
    if m:
        return html[m.end():]
    return html


def _attr_pos(html: str, sid: str) -> Optional[int]:
    raw = html.lower()
    attr_patterns = [
        rf'class="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'id="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'data-section="[^"]*\b{re.escape(sid)}\b[^"]*"',
        rf'<{re.escape(sid)}(?=[\s>])',
    ]
    found: List[int] = []
    for pat in attr_patterns:
        m = re.search(pat, raw)
        if m:
            found.append(m.start())
    return min(found) if found else None


def _phrase_first_pos(norm_text: str, entry: Dict[str, Any]) -> Optional[int]:
    phrases = [entry["id"]] + list(entry.get("aliases", []))
    found: List[int] = []
    for ph in phrases:
        m = re.search(r"(?<![a-z0-9])" + re.escape(_norm(ph)) + r"(?![a-z0-9])", norm_text)
        if m:
            found.append(m.start())
    return min(found) if found else None


def _section_pos(html: str, norm_text: str, entry: Dict[str, Any]) -> Optional[int]:
    apos = _attr_pos(html, entry["id"])
    if apos is not None:
        return apos
    return _phrase_first_pos(norm_text, entry)


def _field_present(html: str, field_id: str, aliases: List[str]) -> bool:
    raw = html.lower()
    attr_patterns = [
        rf'name="{re.escape(field_id)}"',
        rf'id="{re.escape(field_id)}"',
        rf'data-field="{re.escape(field_id)}"',
    ]
    if field_id == "email":
        attr_patterns.append(r'type="email"')
    if field_id == "cell_phone":
        attr_patterns.append(r'name="[^"]*phone[^"]*"')
        attr_patterns.append(r'type="tel"')
    for pat in attr_patterns:
        if re.search(pat, raw):
            return True
    norm = _norm(_strip_tags(html))
    return any(_phrase_present(norm, a) for a in aliases)


def _video_player_present(html: str) -> bool:
    raw = html.lower()
    video_patterns = [
        r'<video\b', r'<iframe[^>]*youtube', r'<iframe[^>]*vimeo',
        r'<iframe[^>]*src="[^"]+\.mp4', r'data-video-src=', r'class="[^"]*\bvideo\b[^"]*"',
        r'data-player=',
    ]
    return any(re.search(p, raw) for p in video_patterns)


def _gate_is_real_form(html: str) -> bool:
    """A REAL Skill-44 gate is an embedded form (form element, iframe script embed, or a
    div that embeds a GHL script/iframe). A static mock = a div with inputs but no form
    semantics and no embed. We fail-closed on ambiguity only if NOTHING form-like exists."""
    raw = html.lower()
    form_patterns = [
        r'<form\b',
        r'<iframe\b[^>]*src=',
        r'script[^>]*src="[^"]*/(embed|form)[^"]*"',
        r'data-form-id=',
        r'class="[^"]*\b(ghl|leadconnector|form-embed)\b[^"]*"',
    ]
    return any(re.search(p, raw) for p in form_patterns)


def _has_pause_resume_controller(html: str) -> bool:
    raw = html.lower()
    patterns = [
        r'\.pause\(\)', r'\.play\(\)', r'currenttime', r'video\.pause', r'video\.play',
        r'addlistener\(["\']play', r'ontimeupdate',
    ]
    hits = sum(1 for p in patterns if re.search(p, raw))
    # Must see BOTH a pause-side and a resume-side signal to prove the controller.
    return bool(re.search(r'\.pause\(\)|video\.pause|currenttime', raw)) and \
        bool(re.search(r'\.play\(\)|video\.play', raw))


def _gate_band_violation(gate_time: Any) -> Optional[Tuple[str, str]]:
    """gate_time may be seconds (int/float) or an ISO-ish clock string 'MM:SS' / 'H:MM:SS'."""
    if isinstance(gate_time, bool):
        return (AF_GATE_BAND, f"gate_time is a boolean ({gate_time}), not a timestamp")
    if isinstance(gate_time, (int, float)):
        t = float(gate_time)
    elif isinstance(gate_time, str):
        s = gate_time.strip()
        try:
            t = float(s)
        except ValueError:
            parts = [p for p in re.split(r"[:]", s) if p]
            try:
                nums = [float(p) for p in parts]
            except ValueError:
                return (AF_GATE_BAND, f"gate_time {gate_time!r} is not a parseable timestamp")
            if len(nums) == 2:
                t = nums[0] * 60 + nums[1]
            elif len(nums) == 3:
                t = nums[0] * 3600 + nums[1] * 60 + nums[2]
            else:
                return (AF_GATE_BAND, f"gate_time {gate_time!r} has unsupported parts {nums}")
    else:
        return (AF_GATE_BAND, f"gate_time has unexpected type {type(gate_time).__name__}")

    if t < GATE_BAND_MIN or t > GATE_BAND_MAX:
        return (AF_GATE_BAND,
                f"gate_time {t:.0f}s is outside the [3:00, 8:00] band "
                f"({GATE_BAND_MIN}s-{GATE_BAND_MAX}s)")
    return None


def _extract_gate_time(meta: Any) -> Optional[Any]:
    """Pull gate_time_seconds / gate_time / placement from a vsl_spec.json / metadata object.
    Scans a few known keys; a sane prover never trusts a single path."""
    if not isinstance(meta, dict):
        return None
    for key in ("gate_time_seconds", "gate_time", "gate_time_sec", "placement_seconds",
                "gate_seconds", "gate_timestamp"):
        if key in meta:
            return meta[key]
    # nested: spec = { "vsl": { "gate_time_seconds": ... } }
    for nested in ("vsl", "gate", "video", "spec", "metadata"):
        v = meta.get(nested)
        if isinstance(v, dict):
            for key in ("gate_time_seconds", "gate_time", "gate_time_sec",
                        "placement_seconds", "gate_seconds", "gate_timestamp"):
                if key in v:
                    return v[key]
    return None


def _default_gate_time_from_meta(meta: Any) -> Optional[float]:
    """If no explicit gate_time is given but we have a video duration D and/or revelation R,
    compute the design's default (DESIGN-OPUS §6.3 rule 3): clamp(R+20s, 180, 480); if R
    unknown or D<180, min(0.9*D, 480) but never below 180 and never above D-10s."""
    if not isinstance(meta, dict):
        return None

    def _num(*keys: str) -> Optional[float]:
        for key in keys:
            if key in meta and isinstance(meta[key], (int, float)) and not isinstance(meta[key], bool):
                return float(meta[key])
            v = meta.get(key)
            if isinstance(v, dict):
                for k2 in ("seconds", "sec", "value"):
                    if k2 in v and isinstance(v[k2], (int, float)):
                        return float(v[k2])
        return None

    duration = _num("duration_seconds", "duration", "video_duration", "length_seconds")
    reveal = _num("revelation_seconds", "revelation", "revelation_time",
                  "first_big_revelation", "revelation_sec")

    if reveal is not None:
        return max(GATE_BAND_MIN, min(reveal + 20.0, GATE_BAND_MAX))
    if duration is not None:
        if duration < GATE_BAND_MIN:
            return None  # video too short for the gate band at all (design F18 default)
        return max(GATE_BAND_MIN, min(0.9 * duration, GATE_BAND_MAX))
    return None


# ---------------------------------------------------------------------------
# HTML-mode evaluation.
# ---------------------------------------------------------------------------
def _verify_html(html: str, canon: Dict[str, Any]) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    body_html = _body(html)
    norm = _norm(_strip_tags(body_html))
    if _stripped_words(body_html) < 20:
        return [(AF_EMPTY, "VSL page has no meaningful body copy (fail-closed)")]

    sections = _sections(canon)
    canon_ids = [s["id"] for s in sections]

    # 1) hero video player.
    if not _video_player_present(body_html):
        fails.append((AF_VIDEO, "no video player (video element / player iframe / player div) "
                                "in the VSL hero"))

    # 2) sections present + order.
    present: Dict[str, int] = {}
    for sec in sections:
        pos = _section_pos(body_html, norm, sec)
        if pos is None:
            fails.append((AF_SECTION_MISSING,
                          f"canonical VSL section {sec['id']!r} absent from the page"))
        else:
            present[sec["id"]] = pos
    positions = [(s, present[s]) for s in canon_ids if s in present]
    for i in range(1, len(positions)):
        if positions[i][1] < positions[i - 1][1]:
            fails.append((AF_ORDER,
                          f"sections out of canonical order: {positions[i - 1][0]!r} (pos "
                          f"{positions[i - 1][1]}) before {positions[i][0]!r} (pos "
                          f"{positions[i][1]})"))
            break

    by_id = {s["id"]: s for s in sections}
    # 3) gate overlay + required fields.
    if _section_pos(body_html, norm, by_id["gate-overlay"]) is None:
        fails.append((AF_GATE_FIELDS, "no gate overlay section on the VSL page"))
    for req in canon.get("gate_fields", {}).get("required", []):
        if not _field_present(body_html, req["id"], req.get("aliases", [])):
            fails.append((AF_GATE_FIELDS,
                          f"gate form missing required field {req['id']!r}"))

    # 4) gate must be a real embedded form, not a static mock.
    if _section_pos(body_html, norm, by_id["gate-overlay"]) is not None and \
            not _gate_is_real_form(body_html):
        fails.append((AF_GATE_NOT_REAL,
                      "gate overlay present but no real form embed found (static mock is "
                      "forbidden — Skill 6/Skill 44 rule)"))

    # 5) pause/resume controller (gate must force-pause the video, resume on submit).
    if _section_pos(body_html, norm, by_id["gate-overlay"]) is not None and \
            not _has_pause_resume_controller(body_html):
        fails.append((AF_GATE_PAUSE,
                      "no pause/resume video controller bound to the gate overlay"))

    # 6) offer recap + CTA + brand footer.
    if _section_pos(body_html, norm, by_id["offer-recap"]) is None:
        fails.append((AF_RECAP, "no offer recap section on the VSL page"))
    if _section_pos(body_html, norm, by_id["final-cta"]) is None:
        fails.append((AF_CTA, "no final CTA section on the VSL page"))
    if _section_pos(body_html, norm, by_id["brand-footer"]) is None:
        fails.append((AF_FOOTER, "no brand footer on the VSL page"))

    # 7) whole-page stripped-word floor.
    total_floor = sum(int(s.get("word_min", 0) or 0) for s in sections)
    wc = _stripped_words(body_html)
    if wc < total_floor:
        fails.append((AF_BAND, f"VSL page has {wc} stripped words, under the {total_floor}-word "
                               f"aggregate floor"))
    return fails


# ---------------------------------------------------------------------------
# Meta evaluation (gate placement band).
# ---------------------------------------------------------------------------
def _verify_meta(meta: Any, html_present: bool) -> List[Tuple[str, str]]:
    if not isinstance(meta, dict):
        return [(AF_GATE_BAND, "VSL metadata is not a JSON object (cannot prove gate band)")]
    gate_time = _extract_gate_time(meta)
    if gate_time is None:
        defaulted = _default_gate_time_from_meta(meta)
        if defaulted is None:
            return [(AF_GATE_BAND,
                     "no gate_time in metadata and no duration/revelation to derive the "
                     "3-8 min default (fail-closed; DESIGN-OPUS §6.3)")]
        # A defaulted placement is ACCEPTED (F18 honest default) but reported distinctly.
        print(f"note: gate_time defaulted from metadata -> {defaulted:.0f}s (within band)")
        return [] if GATE_BAND_MIN <= defaulted <= GATE_BAND_MAX else \
            [(AF_GATE_BAND, f"derived default gate_time {defaulted:.0f}s outside band")]
    viol = _gate_band_violation(gate_time)
    return [] if viol is None else [viol]


# ---------------------------------------------------------------------------
# Ledger-mode evaluation (Skill 56 pattern).
# ---------------------------------------------------------------------------
def _match_section(name: str, sections: List[Dict[str, Any]]) -> Optional[str]:
    n = _norm(name)
    if not n:
        return None
    for sec in sections:
        if n == sec["id"]:
            return sec["id"]
    for sec in sections:
        for alias in sec.get("aliases", []):
            a = _norm(alias)
            if a and (a in n or n in a):
                return sec["id"]
    return None


def _section_copy(sec: Any) -> str:
    if not isinstance(sec, dict):
        return ""
    for k in ("copy", "text", "body", "content", "html"):
        v = sec.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return ""


def _verify_ledger_asset(asset: Dict[str, Any], sections: List[Dict[str, Any]],
                         vlabel: str) -> List[Tuple[str, str]]:
    fails: List[Tuple[str, str]] = []
    secs = asset.get("sections")
    if not isinstance(secs, list) or not secs:
        return [(AF_SECTION_MISSING, f"variant {vlabel}: no sections declared")]

    canon_ids = [s["id"] for s in sections]
    word_min_by_id = {s["id"]: s.get("word_min") for s in sections}
    resolved: List[str] = []
    for s in secs:
        name = s.get("name") if isinstance(s, dict) else s
        cid = _match_section(name, sections)
        if cid is None:
            fails.append((AF_UNKNOWN, f"variant {vlabel}: section {name!r} matches no canonical "
                                      f"VSL section"))
            continue
        resolved.append(cid)
        floor = word_min_by_id.get(cid)
        if isinstance(floor, int) and floor > 0:
            wc = _stripped_words(_section_copy(s))
            if wc < floor:
                fails.append((AF_BAND, f"variant {vlabel}: section {cid!r} has {wc} stripped "
                                       f"words, under the {floor}-word floor"))

    if len(secs) != len(canon_ids):
        fails.append((AF_COUNT, f"variant {vlabel}: {len(secs)} sections, expected "
                                f"{len(canon_ids)}"))

    seen = set(resolved)
    for cid in canon_ids:
        if cid not in seen:
            fails.append((AF_SECTION_MISSING, f"variant {vlabel}: canonical section {cid!r} absent"))

    firstseen: List[str] = []
    for cid in resolved:
        if cid not in firstseen:
            firstseen.append(cid)
    if firstseen != [c for c in canon_ids if c in seen]:
        fails.append((AF_ORDER, f"variant {vlabel}: sections not in canonical VSL order "
                                f"(got {firstseen})"))
    return fails


def _verify_ledger(ledger: Any) -> List[Tuple[str, str]]:
    if not isinstance(ledger, dict):
        return [(AF_EMPTY, "ledger root is not a JSON object")]
    items = ledger.get("assets")
    if items is None and isinstance(ledger, dict):
        items = ledger.get("pages")
    if not isinstance(items, list):
        return [(AF_EMPTY, "ledger has no assets/pages list (cannot prove; fail-closed)")]
    stage_assets = [a for a in items if isinstance(a, dict) and _norm(a.get("stage")) == "vsl"]
    if not stage_assets:
        return [(AF_EMPTY, "no VSL-stage assets in the ledger (cannot prove; fail-closed)")]

    canon = _load_canonical()
    sections = _sections(canon)
    required = canon.get("variants_required", ["a", "b"])
    by_variant: Dict[str, Dict[str, Any]] = {}
    for a in stage_assets:
        by_variant[_norm(a.get("variant"))] = a

    fails: List[Tuple[str, str]] = []
    for v in required:
        if v not in by_variant:
            fails.append((AF_COUNT, f"VSL variant {v!r} missing (both {required} required)"))
            continue
        fails.extend(_verify_ledger_asset(by_variant[v], sections, v))
    return fails


# ---------------------------------------------------------------------------
# Front door.
# ---------------------------------------------------------------------------
def _emit(source: str, failures: List[Tuple[str, str]], as_json: bool) -> None:
    if as_json:
        print(json.dumps({"gate": "presentations-vsl-copy-structure", "source": source,
                          "pass": not failures,
                          "failures": [{"code": c, "message": m} for c, m in failures]}, indent=2))
        return
    print("== Presentations :: VSL page structure (email/phone gate) ==")
    print(f"source: {source}")
    if not failures:
        print("RESULT: PASS — hero video, 5 canonical sections in order, real email/phone "
              "gate in the 3-8 min band, pause/resume controller, offer recap + CTA + footer.")
        return
    print(f"RESULT: FAIL (fail-closed) — {len(failures)} violation(s):")
    for code, msg in failures:
        print(f"  [{code}] {msg}")


def prove_html_path(html_path: str, meta_path: Optional[str], as_json: bool = False) -> int:
    p = Path(html_path)
    if not p.is_file():
        _emit(str(p), [("USAGE", f"HTML file not found: {p}")], as_json)
        return EXIT_USAGE
    try:
        html = p.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        _emit(str(p), [("USAGE", f"cannot read HTML: {exc}")], as_json)
        return EXIT_USAGE
    try:
        canon = _load_canonical()
    except (ValueError, OSError) as exc:
        _emit(str(p), [(AF_STRUCTURE, f"cannot load vsl_structure.json: {exc}")], as_json)
        return EXIT_USAGE
    fails = _verify_html(html, canon)
    if meta_path:
        mp = Path(meta_path)
        if not mp.is_file():
            _emit(str(p), [("USAGE", f"metadata file not found: {mp}")], as_json)
            return EXIT_USAGE
        try:
            meta = json.loads(mp.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            _emit(str(p), [("USAGE", f"cannot read/parse metadata JSON: {exc}")], as_json)
            return EXIT_USAGE
        fails.extend(_verify_meta(meta, html_present=True))
    _emit(str(p), fails, as_json)
    return EXIT_PASS if not fails else EXIT_AUTOFAIL


# ---------------------------------------------------------------------------
# Self-test — must DISCRIMINATE.
# ---------------------------------------------------------------------------
_VALID_BLOCKS = {
    "hero-video": ('<section class="hero-video" data-section="hero"><h1>Watch This Video</h1>'
                   '<video id="vsl-video" controls preload="metadata" '
                   'src="https://cdn.example.com/vsl.mp4"></video></section>'),
    "gate-overlay": ('<section class="gate-overlay" id="gate" data-section="gate-overlay">'
                     '<div class="ghl-form-embed" data-form-id="f123">'
                     '<form id="gate-form"><label>Email <input type="email" '
                     'name="email" /></label><label>First Name <input type="text" '
                     'name="first_name" /></label><label>Cell Phone <input type="tel" '
                     'name="cell_phone" /></label>'
                     '<button type="submit">Unlock the Rest</button></form>'
                     '<script>const v=document.getElementById("vsl-video");'
                     'v.addEventListener("timeupdate",()=>{if(v.currentTime>=420){'
                     'v.pause();document.getElementById("gate").style.display="flex";'
                     '}});document.getElementById("gate-form").addEventListener("submit",'
                     '()=>{v.play();document.getElementById("gate").style.display="none";'
                     '});</script></div></section>'),
    "offer-recap": ('<section class="offer-recap"><h2>Here Is What You Get</h2>'
                    '<p>This recap reminds you of the presentation, the workbook, the '
                    'implementation guide, and the private training call that come with '
                    'the complete package.</p></section>'),
    "final-cta": ('<section class="final-cta"><h2>Get Instant Access</h2>'
                  '<p>Click the button below to claim your copy while the doors are open '
                  'and the price is guaranteed today.</p>'
                  '<button>Get Instant Access Now</button></section>'),
    "brand-footer": ('<footer class="brand-footer"><p>Privacy Policy · Terms · '
                     'Copyright 2026 · All rights reserved.</p></footer>'),
}

_CANON_ORDER = ["hero-video", "gate-overlay", "offer-recap", "final-cta", "brand-footer"]


def _valid_vsl_html() -> str:
    return "<!doctype html><html><head><title>Watch the VSL</title></head><body>" + \
        "".join(_VALID_BLOCKS[k] for k in _CANON_ORDER) + "</body></html>"


def _vsl_without(blocks: List[str]) -> str:
    html = _valid_vsl_html()
    for k in blocks:
        html = html.replace(_VALID_BLOCKS[k], "")
    return html


def _vsl_with_static_gate() -> str:
    """Replace the real gate block with a static mock (inputs but no form/embed) INSIDE the
    body, so the prover must call it out as not-a-real-form (Skill 6/Skill 44 rule)."""
    html = _valid_vsl_html().replace(_VALID_BLOCKS["gate-overlay"], _STATIC_GATE)
    return html


def _vsl_reordered() -> str:
    order = ["gate-overlay", "hero-video", "offer-recap", "final-cta", "brand-footer"]
    return "<!doctype html><html><head><title>Watch the VSL</title></head><body>" + \
        "".join(_VALID_BLOCKS[k] for k in order) + "</body></html>"


def _valid_meta(gate_time: Any = 420) -> Dict[str, Any]:
    return {"duration_seconds": 600, "revelation_seconds": 400, "gate_time_seconds": gate_time}


def self_test() -> int:
    ok = True

    def check_pass(name: str, fails: List[Tuple[str, str]]) -> None:
        nonlocal ok
        good = not fails
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VALID {name:20s} -> exit "
              f"{EXIT_PASS if good else EXIT_AUTOFAIL}" + ("" if good else f" ({fails})"))

    def check_fail(name: str, fails: List[Tuple[str, str]], expect: str) -> None:
        nonlocal ok
        codes = [c for c, _ in fails]
        good = bool(fails) and expect in codes
        ok = ok and good
        print(f"  [{'PASS' if good else 'MISS'}] VIOLATION {name:22s} -> codes={codes} "
              f"(want {expect})")

    canon = _load_canonical()
    sections = _sections(canon)

    print("== self-test: VALID fixtures (must PASS) ==")
    check_pass("html-complete", _verify_html(_valid_vsl_html(), canon))
    check_pass("meta-in-band", _verify_meta(_valid_meta(420), html_present=True))
    check_pass("meta-defaulted", _verify_meta({"duration_seconds": 600, "revelation_seconds": 400},
                                              html_present=True))
    # clock-string form
    check_pass("meta-clock-string", _verify_meta({"gate_time": "6:00"}, html_present=True))

    print("== self-test: VIOLATION fixtures (must FAIL) ==")
    check_fail("missing-video", _verify_html(_vsl_without(["hero-video"]), canon), AF_VIDEO)
    check_fail("missing-gate-overlay", _verify_html(_vsl_without(["gate-overlay"]), canon),
               AF_GATE_FIELDS)
    check_fail("gate-static-mock", _verify_html(_vsl_with_static_gate(), canon),
               AF_GATE_NOT_REAL)
    check_fail("missing-recap", _verify_html(_vsl_without(["offer-recap"]), canon), AF_RECAP)
    check_fail("missing-cta", _verify_html(_vsl_without(["final-cta"]), canon), AF_CTA)
    check_fail("missing-footer", _verify_html(_vsl_without(["brand-footer"]), canon), AF_FOOTER)
    check_fail("order-swapped", _verify_html(_vsl_reordered(), canon), AF_ORDER)
    check_fail("gate-band-low", _verify_meta(_valid_meta(150), html_present=True), AF_GATE_BAND)
    check_fail("gate-band-high", _verify_meta(_valid_meta(490), html_present=True), AF_GATE_BAND)
    check_fail("gate-band-unknown", _verify_meta({}, html_present=True), AF_GATE_BAND)

    # --- ledger-mode fixtures ---
    _COPY = ("This is the offer recap section copy and it is long enough to clear every "
             "sacred word band without any artificial padding to satisfy the measured floor "
             "so that the prover sees real substance here.")

    def ledger_asset(variant: str, names: Optional[List[str]] = None) -> Dict[str, Any]:
        nm = names if names is not None else [s["id"] for s in sections]
        return {"stage": "vsl", "variant": variant, "type": "page",
                "asset_key": f"jane-doe__glow-method__vsl__page__v01{variant}",
                "sections": [{"order": i + 1, "name": n, "copy": _COPY}
                             for i, n in enumerate(nm)]}

    check_pass("ledger-both-variants", _verify_ledger({"assets": [ledger_asset("a"),
                                                                  ledger_asset("b")]}))
    check_fail("ledger-missing-b", _verify_ledger({"assets": [ledger_asset("a")]}), AF_COUNT)
    swapped = [s["id"] for s in sections]
    swapped[0], swapped[1] = swapped[1], swapped[0]
    check_fail("ledger-swapped", _verify_ledger({"assets": [ledger_asset("a", swapped)]}),
               AF_ORDER)
    check_fail("ledger-empty", _verify_ledger({"assets": []}), AF_EMPTY)

    print("== self-test:", "ALL ASSERTIONS PASSED ==" if ok else "FAILED ==")
    return 0 if ok else 1


# A static-mock gate: inputs present but no form semantics / no embed.
_STATIC_GATE = ('<section class="gate-overlay" id="gate" data-section="gate-overlay">'
                '<label>Email <input type="email" name="email" /></label>'
                '<label>First Name <input type="text" name="first_name" /></label>'
                '<label>Cell Phone <input type="tel" name="cell_phone" /></label>'
                '<button>Unlock</button></section>')


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed prover for the VSL page structure.")
    ap.add_argument("--html", help="path to a VSL page HTML fragment")
    ap.add_argument("--meta", help="path to VSL video/gate metadata JSON (vsl_spec.json)")
    ap.add_argument("--ledger", help="path to a copy_ledger.json (Skill 56 pattern)")
    ap.add_argument("--json", action="store_true", help="machine-readable JSON output")
    ap.add_argument("--self-test", dest="self_test", action="store_true",
                    help="run built-in VALID + VIOLATION fixtures and exit")
    args = ap.parse_args(argv)
    if args.self_test:
        return self_test()
    if args.html:
        if args.ledger:
            print("USAGE ERROR: pass --html OR --ledger, not both.")
            return EXIT_USAGE
        return prove_html_path(args.html, args.meta, as_json=args.json)
    if args.ledger:
        if args.meta:
            print("USAGE ERROR: --meta is only valid with --html.")
            return EXIT_USAGE
        p = Path(args.ledger)
        if not p.is_file():
            print("USAGE ERROR: ledger not found:", args.ledger)
            return EXIT_USAGE
        try:
            ledger = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"FAIL-CLOSED: cannot read/parse ledger: {exc}")
            return EXIT_USAGE
        try:
            _load_canonical()
        except (ValueError, OSError) as exc:
            print(f"FAIL-CLOSED: cannot load vsl_structure.json: {exc}")
            return EXIT_USAGE
        fails = _verify_ledger(ledger)
        _emit(str(p), fails, args.json)
        return EXIT_PASS if not fails else EXIT_AUTOFAIL
    if args.meta:
        p = Path(args.meta)
        if not p.is_file():
            print("USAGE ERROR: metadata not found:", args.meta)
            return EXIT_USAGE
        try:
            meta = json.loads(p.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            print(f"FAIL-CLOSED: cannot read/parse metadata: {exc}")
            return EXIT_USAGE
        fails = _verify_meta(meta, html_present=False)
        _emit(str(p), fails, args.json)
        return EXIT_PASS if not fails else EXIT_AUTOFAIL
    print("USAGE ERROR: pass --html <file> | --meta <file> | --ledger <file> (or --self-test).")
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())

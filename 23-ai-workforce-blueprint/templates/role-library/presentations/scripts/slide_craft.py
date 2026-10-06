#!/usr/bin/env python3
"""slide_craft.py — DETERMINISTIC enforcers for the craft rules that are ARITHMETIC.

The four craft rulebooks (SOP-SLIDE-01 One-Big-Idea, -02 Audience-Facing-Only,
-03 Hook-Doctrine, -04 Deck-Density-and-Pacing) declare 27 numbered triggers. Some are
counting; some are judgement. This module implements ONLY the counting ones and the
ruleset now says which is which, so the autofail total stops implying coverage it does
not have.

WHAT THIS MODULE DELIBERATELY DOES NOT DO: it writes no enforcer for a code whose
Detection column names a semantic decision (is this line phrased as speech, does this
caption narrate the photo, are these three values a trio), and none for a code whose
named input cannot exist (TEXT_ANCHOR is not a slides.schema.json property; the schema
is additionalProperties:false). Those rows are marked human_judged in the manifest and
HUMAN JUDGEMENT in the ruleset. An unmarked un-enforced code is the AF-NO-VISION-QC
defect, which is what U049 exists to delete.

WHAT IS ALREADY ENFORCED AND IS NOT DUPLICATED HERE:
  AF-HOOK, AF-HOOK-1, AF-HOOK-4, AF-HOOK-IMG-MISSING, AF-HOOK-OVERSTAMP  live in
    intelligence_engines_check.py (AF-HOOK-1 verified firing at 6 hook slides, silent
    at 4, by importing that module and calling check_copy).
  AF-HOOK-3  is a strict subset of AF-NO-HOOK-REFRAIN (<3 contains 0).
  AF-DEN-5   is AF-PRICE-BEFORE-PROMISE, whose price-token set already contains ANCHOR.
A second enforcer for any of those five rules double-fires on one defect.

EVERY THRESHOLD IS THE SOP's OWN NUMBER, CITED AT ITS DEFINITION. Nothing is invented
and nothing is tuned. Where the doctrine gives two numbers (SOP-SLIDE-04 prose says the
anchor targets 30-40%; its own trigger table says 25-45%) the TRIGGER TABLE wins, because
that is the row the ruleset publishes as machine-checkable — and the divergence is
recorded rather than silently resolved.

EVERY CHECK DEFERS AND NEVER RAISES. A raise inside run_preflight_gate kills the loop
at build_deck.py:7505 and the remaining entries never run.
"""

import difflib
import os
import sys
import json
import re
from pathlib import Path

# ── Thresholds, each with the line that defines it ───────────────────────────
# SOP-SLIDE-01 §2.3 "A slide carries at most THREE text blocks"; Section-5 line 167
# "count of text blocks > 3".
OBI_TEXT_BLOCK_MAX = 3

# SOP-SLIDE-01 §2.4 "Headline 9 words maximum (target 4 to 7)"; Section-5 line 168
# "exact word count". This is the WORD count the COPY_HEADLINE_CHAR_CEILING = 60
# character band (build_deck.py:350) is a proxy for; both stand, they measure
# different things.
OBI_HEADLINE_WORD_MAX = 9

# SOP-SLIDE-04 §2.1 "Minimum gap between any two price beats: 8 slides ... Computed
# against the FULL deck slide count"; Section-5 line 173.
DEN_PRICE_BEAT_MIN_GAP = 8

# SOP-SLIDE-04 §3 DEN-2 "Anchor slide position / total slides. Outside 0.25-0.45 =
# fail"; Section-5 line 174. §2.2's prose 30-40% is the TARGET, not the trigger.
DEN_ANCHOR_DEPTH_MIN = 0.25
DEN_ANCHOR_DEPTH_MAX = 0.45

# SOP-SLIDE-04 §2.7 "A 4-to-7-slide re-pitch block follows the FINAL price";
# Section-5 line 179.
DEN_REPITCH_MIN = 4
DEN_REPITCH_MAX = 7

# The refrain-similarity threshold is the repository's own, prompt_gate.py:190
# (OCR_MATCH_RATIO = 0.82, used with difflib.SequenceMatcher at :543-548). A copy
# occurrence that is >= this similar to the canonical hook but not char-exact is a
# MUTATION (SOP-SLIDE-03 §3 HOOK-5 "char-exact compare"); below it, it is different
# text and not this check's business.
HOOK_VARIANT_RATIO = 0.82

_WORD_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z'\-]*")
BRACKET_TOKEN_RE = re.compile(r"\[[^\]]*\]")

# SOP-SLIDE-02 §3 AUD-6 names these token substrings alongside the bracket regex.
PLACEHOLDER_TOKENS = ("owner to confirm", "insert", "tbd", "placeholder",
                      "client win", "endorsement", "real result", "client to supply")

# SOP-SLIDE-02 §2.4 and §3 AUD-4: the literal word plus the named announcements.
AUD_META_TOKENS = ("webinar", "this is not just", "one last proof",
                   "an intrigue gap", "hold onto this line", "hold on to this line")

# SOP-SLIDE-02 §3 AUD-5's own marker list, verbatim from the Detection column.
AUD_CREDENTIAL_TOKENS = ("licensed", "clinical", "years in", "certified",
                         "credential", "accredited")

# SOP-SLIDE-04 §3 DEN-4: the value-stack beat, in the ARC-marker vocabulary
# pitch_engines_check already parses (_arc_tags_in_order, :83-96).
DEN_STACK_TAGS = ("VALUE_STACK", "VALUESTACK", "STACK", "VALUE-STACK")
DEN_DROP_TAGS = ("DROP", "DROP1", "DROP2", "DROP3")

ENFORCE_ENV = "PRESENTATION_SLIDE_CRAFT_ENFORCE"
PROVENANCE_REL = "working/qc/slide_craft.json"
WAIVER_REL = "working/checkpoints/slide_craft_waivers.json"


# ── Helpers ─────────────────────────────────────────────────────────────────

def _slides_json(run_dir, slides_path=None):
    """Read slides.json from candidate paths and return parsed list or [].

    Duplicates build_deck._load_slide_copy_map's candidate order (:3222-3225)
    deliberately rather than importing it, to avoid a circular import."""
    candidates = []
    if slides_path is not None:
        candidates.append(Path(slides_path))
    candidates.append(run_dir / "working" / "copy" / "slides.json")
    candidates.append(run_dir / "slides.json")
    candidates.append(run_dir / "working" / "slides.json")
    for p in candidates:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(data, list):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            continue
    return []


def _slides(run_dir, slides_path=None):
    """{ordinal: [copy blocks]} for the deck that will actually be rendered, and the
    slide total. Returns {} when no slides.json can be read."""
    data = _slides_json(run_dir, slides_path)
    if not data:
        return {}
    out = {}
    for entry in data:
        if isinstance(entry, dict) and "slide" in entry:
            copy_val = entry.get("copy")
            if isinstance(copy_val, list):
                out[entry["slide"]] = [str(c) for c in copy_val]
            elif copy_val is not None:
                out[entry["slide"]] = [str(copy_val)]
            else:
                out[entry["slide"]] = [""]
    return out


def _intake(run_dir):
    """working/copy/intake.json as a dict, {} on absence or parse failure."""
    candidates = [
        run_dir / "working" / "copy" / "intake.json",
        run_dir / "copy" / "intake.json",
        run_dir / "intake.json",
    ]
    for p in candidates:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            continue
    return {}


def _price_ladder(run_dir):
    """working/copy/price_ladder.json, or None."""
    candidates = [
        run_dir / "working" / "copy" / "price_ladder.json",
        run_dir / "copy" / "price_ladder.json",
    ]
    for p in candidates:
        try:
            data = json.loads(Path(p).read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
            continue
    return None


def _arc_marker_offsets(run_dir):
    """{TAG: [character offsets]} from slides_copy.md's ARC markers."""
    candidates = [
        run_dir / "working" / "copy" / "slides_copy.md",
        run_dir / "slides_copy.md",
    ]
    text = None
    for p in candidates:
        try:
            text = Path(p).read_text(encoding="utf-8")
            if text:
                break
        except (FileNotFoundError, OSError):
            continue
    if not text:
        return {}
    tags = {}
    for m in re.finditer(r'(?:<!--\s*ARC:\s*([^>]+?)\s*-->|\[ARC:\s*([^\]]+?)\s*\])', text):
        raw = (m.group(1) or m.group(2) or "")
        toks = [t.strip().upper() for t in re.split(r'[\s,]+', raw) if t.strip()]
        for t in toks:
            tags.setdefault(t, []).append(m.start())
    return tags


def _write_provenance(run_dir, payload):
    """Write PROVENANCE_REL (best-effort, never raises). Merges with existing data
    so each check adds its own key rather than overwriting the previous one."""
    try:
        dest = run_dir / PROVENANCE_REL
        dest.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if dest.exists():
            try:
                existing = json.loads(dest.read_text(encoding="utf-8"))
                if not isinstance(existing, dict):
                    existing = {}
            except (json.JSONDecodeError, OSError):
                existing = {}
        existing.update(payload)
        dest.write_text(json.dumps(existing, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


# ── Waiver file reader (one rule / one run / named slides, per FIX 15) ───────

# The ten deterministic codes enforced by FIX 15 (DEFAULT RULING: enforce all ten,
# retire none). Map check function name -> the AF code it reports.
CHECK_RULE_CODES = {
    "check_obi_text_blocks": "AF-OBI-1",
    "check_obi_headline_words": "AF-OBI-2",
    "check_aud_meta_tokens": "AF-AUD-4",
    "check_aud_credentials": "AF-AUD-5",
    "check_aud_placeholder_render": "AF-AUD-6",
    "check_hook_verbatim": "AF-HOOK-5",
    "check_den_ladder_gaps": "AF-DEN-1",
    "check_den_anchor_depth": "AF-DEN-2",
    "check_den_stack_before_drop": "AF-DEN-4",
    "check_den_repitch_block": "AF-DEN-7",
}


def _load_waivers(run_dir):
    """Return {af_code: {"slides": set, "all_slides": bool}} from WAIVER_REL, or {} per
    invalid record. Waivers are scoped ONE RULE / ONE RUN / NAMED SLIDES:

    - The file lives inside the run dir, so its scope is exactly this run — there is no
      cross-run and no environment-wide waiver, and ENFORCE_ENV=0 is NOT honored as a
      production escape (see run_all_checks).
    - Each record: {"af_code": "AF-OBI-1", "slides": [3, 7], "approved_by": "...",
      "reason": "..."} — slides are named slide ordinals. "ALL" is accepted in the
      slides list ONLY for AF-DEN-4, whose ORDER-only finding has no slide attribution.
    - A record missing af_code, approved_by, reason, or slides is INVALID and ignored:
      a malformed waiver never silences a gate (fail-closed).

    Malformed JSON or a non-list document yields {} — same fail-closed direction."""
    p = run_dir / WAIVER_REL
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, list):
        return {}
    waivers = {}
    for rec in data:
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("af_code", "")).strip().upper()
        if code not in CHECK_RULE_CODES.values():
            continue
        if not str(rec.get("approved_by", "")).strip():
            continue
        if not str(rec.get("reason", "")).strip():
            continue
        slides = rec.get("slides")
        if not isinstance(slides, list) or not slides:
            continue
        ordinals = set()
        all_slides = False
        for s in slides:
            if s == "ALL" and code == "AF-DEN-4":
                all_slides = True
                continue
            try:
                n = int(s)
            except (TypeError, ValueError):
                continue
            if n > 0:
                ordinals.add(n)
        if not ordinals and not all_slides:
            continue
        entry = waivers.setdefault(code, {"slides": set(), "all_slides": False})
        entry["slides"].update(ordinals)
        entry["all_slides"] = entry["all_slides"] or all_slides
    return waivers


def _finding_slides(record):
    """Slide ordinals a provenance record attributes its findings to. {} / unknown
    shape -> empty set, which makes any waiver inapplicable (fail-closed): an
    unattributable finding can only be waived via the explicit AF-DEN-4 ALL path."""
    if not isinstance(record, dict):
        return set()
    offs = record.get("offenders")
    slides = set()
    if isinstance(offs, list):
        for o in offs:
            if isinstance(o, (list, tuple)) and o:
                first = o[0]
                # Per-slide rules lead with the ordinal; AUD-6 leads with a sidecar
                # filename "slide-NN.ocr.json"; DEN-1 leads with a beat slide and its
                # second element is the next beat slide.
                if isinstance(first, int):
                    slides.add(first)
                    if len(o) > 2 and isinstance(o[1], int):
                        slides.add(o[1])
                elif isinstance(first, str):
                    m = re.match(r"slide-(\d+)", first)
                    if m:
                        slides.add(int(m.group(1)))
            elif isinstance(o, int):
                slides.add(o)
    for key in ("anchor_slide", "final_slide"):
        v = record.get(key)
        if isinstance(v, int) and v > 0:
            slides.add(v)
    return slides


# ── Enforcer aggregator (called by build_deck preflight — FIX 15 wiring) ─────

def enforce_active():
    """FIX 15: enforcement is DEFAULT-ON and there is no global ENFORCE=0 production
    escape. ENFORCE_ENV is READ (the historic dead-env defect) and accepted values are
    '1'/'true'/'yes'/'on' (explicit ON, same behavior as the default) and anything else
    including '0' is REFUSED with a loud note — '0' does NOT disarm the gate; the only
    documented bypass is an owner-token waiver (WAIVER_REL) scoped to one rule, one run,
    named slides."""
    raw = (os.environ.get(ENFORCE_ENV) or "").strip().lower()
    if raw in ("", "1", "true", "yes", "on"):
        return True
    if raw == "0":
        try:
            print(f"{ENFORCE_ENV}=0 REFUSED: slide-craft enforcement has no global "
                  f"bypass (FIX 15). Waive one rule for named slides via "
                  f"{WAIVER_REL} instead.", file=sys.stderr)
        except Exception:
            pass
    return True


def run_all_checks(run_dir, slides_path=None):
    """Run all ten deterministic craft checks; return (all_pass, blocking_reasons).

    A check that returns "" DEFERS (pass — missing input is owned upstream). A
    non-empty return is a FAILED rule. Every check fires regardless of earlier
    failures — no early-exit — so one pass names every defect.

    Waivers: WAIVER_REL entries are applied ONLY when the waiver's named slides
    cover EVERY slide the provenance attributes to that rule's finding (or, for
    AF-DEN-4's unattributable ORDER finding only, the explicit "ALL"). A waived
    reason is reported as waived but does not block. Malformed or under-scoped
    waivers fail closed (the finding still blocks).

    all_pass=True only when no blocking reason survives. This is the call path
    build_deck.py's PREFLIGHT_REQUIRED gate uses; it cannot be skipped by an env
    flag (enforce_active() refuses ENFORCE=0)."""
    waivers = _load_waivers(run_dir)
    blocking = []
    waived = []
    for fn in _enforcers():
        reason = fn(run_dir, slides_path)
        if not reason:
            continue
        code = CHECK_RULE_CODES.get(fn.__name__, "?")
        prov = _read_provenance_entry(run_dir, fn.__name__)
        entry = waivers.get(code)
        if entry:
            offenders = _finding_slides(prov)
            if entry["all_slides"] and not offenders:
                waived.append(f"{code} (waived for the whole deck): {reason}")
                continue
            if offenders and offenders <= entry["slides"]:
                names = ", ".join(str(s) for s in sorted(offenders))
                waived.append(f"{code} (waived for slide(s) {names}): {reason}")
                continue
        blocking.append(reason)
    _write_provenance(run_dir, {"slide_craft_enforcement": {
        "blocking": len(blocking), "waived": len(waived),
        "waived_detail": waived, "reasons": blocking}})
    return (len(blocking) == 0), blocking


def _read_provenance_entry(run_dir, key):
    """Best-effort read of one provenance record written during this pass."""
    try:
        data = json.loads((run_dir / PROVENANCE_REL).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data.get(key) or {}
    except (FileNotFoundError, json.JSONDecodeError, OSError, ValueError):
        pass
    return {}


# ── Enforcers ────────────────────────────────────────────────────────────────

def check_obi_text_blocks(run_dir, slides_path=None):
    """AF-OBI-1 — no slide carries more than OBI_TEXT_BLOCK_MAX non-empty copy blocks."""
    sl = _slides(run_dir, slides_path)
    if not sl:
        _write_provenance(run_dir, {"check_obi_text_blocks": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    offenders = []
    for ordinal in sorted(sl):
        blocks = sl[ordinal]
        count = len([c for c in blocks if str(c).strip()])
        if count > OBI_TEXT_BLOCK_MAX:
            offenders.append((ordinal, count))
    if not offenders:
        _write_provenance(run_dir, {"check_obi_text_blocks": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s}: {c} blocks" for s, c in offenders)
    reason = (f"AF-OBI-1: {len(offenders)} slide(s) exceed the "
              f"{OBI_TEXT_BLOCK_MAX}-block ceiling ({detail})")
    _write_provenance(run_dir, {"check_obi_text_blocks": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "total_slides": len(sl), "reason": reason}})
    return reason


def check_obi_headline_words(run_dir, slides_path=None):
    """AF-OBI-2 — copy[0] carries at most OBI_HEADLINE_WORD_MAX words."""
    sl = _slides(run_dir, slides_path)
    if not sl:
        _write_provenance(run_dir, {"check_obi_headline_words": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    offenders = []
    for ordinal in sorted(sl):
        blocks = sl[ordinal]
        if not blocks or not isinstance(blocks[0], str) or not blocks[0].strip():
            continue
        words = _WORD_RE.findall(blocks[0])
        count = len(words)
        if count > OBI_HEADLINE_WORD_MAX:
            offenders.append((ordinal, count))
    if not offenders:
        _write_provenance(run_dir, {"check_obi_headline_words": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s}: {c} words" for s, c in offenders)
    reason = (f"AF-OBI-2: {len(offenders)} headline(s) exceed "
              f"{OBI_HEADLINE_WORD_MAX} words ({detail})")
    _write_provenance(run_dir, {"check_obi_headline_words": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "total_slides": len(sl), "reason": reason}})
    return reason


def _scanners_35():
    """FIX 35 — presentation_job.scanners (negation-aware keyword scanning), or
    None. Imported lazily so slide_craft keeps loading standalone; on failure the
    AF-AUD token scans fall back to the legacy substring scan (the gate keeps its
    pre-FIX-35 teeth rather than going blind)."""
    try:
        from presentation_job import scanners as _scanners_mod
        return _scanners_mod
    except Exception:
        try:
            import sys as _sys
            _pkg = str(Path(__file__).resolve().parent / "presentation_job")
            _parent = str(Path(__file__).resolve().parent)
            if _pkg not in _sys.path:
                _sys.path.insert(0, _pkg)
            if _parent not in _sys.path:
                _sys.path.insert(0, _parent)
            from presentation_job import scanners as _scanners_mod
            return _scanners_mod
        except Exception:
            return None


def _aud_token_hits_35(block, tokens):
    """FIX 35 — negation-aware token hits in ONE copy block.

    A token that sits within NEGATION_WINDOW_TOKENS tokens after a negator in the
    same sentence ("this is NOT a webinar", "she is NOT licensed") is a disclaimer,
    not the defect the AF-AUD rule names, so it is suppressed. A token outside a
    negated span still fires — the gate cannot get weaker than the old substring
    scan. Falls back to the legacy substring scan when the scanners module cannot
    be imported. Returns the list of tokens that survive."""
    surviving_tokens = [tok for tok, _off in _scanners_35().scan_negation_aware(
        str(block), tokens)] if _scanners_35() is not None else [
        tok for tok in tokens if tok.lower() in str(block).lower()]
    return surviving_tokens


def check_aud_meta_tokens(run_dir, slides_path=None):
    """AF-AUD-4 — no AUD_META_TOKENS substring appears in any copy block.
    FIX 35: the token scan is negation-aware (a prohibition of the technique is
    not the technique; see _aud_token_hits_35)."""
    sl = _slides(run_dir, slides_path)
    if not sl:
        _write_provenance(run_dir, {"check_aud_meta_tokens": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    findings = []
    for ordinal in sorted(sl):
        for i, block in enumerate(sl[ordinal]):
            for token in _aud_token_hits_35(block, AUD_META_TOKENS):
                findings.append((ordinal, i, token))
    if not findings:
        _write_provenance(run_dir, {"check_aud_meta_tokens": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s} copy[{i}]: '{t}'" for s, i, t in findings)
    reason = (f"AF-AUD-4: {len(findings)} meta-token occurrence(s) found "
              f"({detail})")
    _write_provenance(run_dir, {"check_aud_meta_tokens": {
        "deferred": False, "findings": len(findings),
        "offenders": findings, "total_slides": len(sl), "reason": reason}})
    return reason


def check_aud_credentials(run_dir, slides_path=None):
    """AF-AUD-5 — no AUD_CREDENTIAL_TOKENS in NON-HEADLINE blocks (copy[1:]).
    FIX 35: the token scan is negation-aware (a disclaimer such as 'not licensed'
    or 'never treat her advice as certified' is not a credential dump; see
    _aud_token_hits_35)."""
    sl = _slides(run_dir, slides_path)
    if not sl:
        _write_provenance(run_dir, {"check_aud_credentials": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    findings = []
    for ordinal in sorted(sl):
        blocks = sl[ordinal]
        for i in range(1, len(blocks)):
            for token in _aud_token_hits_35(blocks[i], AUD_CREDENTIAL_TOKENS):
                findings.append((ordinal, i, token))
    if not findings:
        _write_provenance(run_dir, {"check_aud_credentials": {
            "deferred": False, "findings": 0, "total_slides": len(sl)}})
        return ""
    detail = "; ".join(f"slide {s} copy[{i}]: '{t}'" for s, i, t in findings)
    reason = (f"AF-AUD-5: {len(findings)} credential-marker occurrence(s) "
              f"in body copy ({detail})")
    _write_provenance(run_dir, {"check_aud_credentials": {
        "deferred": False, "findings": len(findings),
        "offenders": findings, "total_slides": len(sl), "reason": reason}})
    return reason


def check_aud_placeholder_render(run_dir, slides_path=None):
    """AF-AUD-6 / AF-PLACEHOLDER — no placeholder on RENDERED slides."""
    renders_dir = run_dir / "renders"
    if not renders_dir.is_dir():
        _write_provenance(run_dir, {"check_aud_placeholder_render": {
            "deferred": True, "reason": "renders/ directory absent"}})
        return ""
    sidecars = sorted(renders_dir.glob("slide-*.ocr.json"))
    if not sidecars:
        _write_provenance(run_dir, {"check_aud_placeholder_render": {
            "deferred": True, "reason": "no .ocr.json sidecars in renders/"}})
        return ""
    findings = []
    any_checked = False
    for sc_path in sidecars:
        try:
            data = json.loads(sc_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            continue
        if not isinstance(data, dict) or not data.get("checked"):
            continue
        any_checked = True
        ocr_text = str(data.get("ocr_text", ""))
        for m in BRACKET_TOKEN_RE.finditer(ocr_text):
            findings.append((sc_path.name, "bracket", m.group()))
        lower = ocr_text.lower()
        for token in PLACEHOLDER_TOKENS:
            if token in lower:
                findings.append((sc_path.name, "token", token))
    if not any_checked:
        _write_provenance(run_dir, {"check_aud_placeholder_render": {
            "deferred": True,
            "reason": "no OCR sidecar with checked:true"}})
        return ""
    if not findings:
        _write_provenance(run_dir, {"check_aud_placeholder_render": {
            "deferred": False, "findings": 0, "sidecars_scanned": len(sidecars)}})
        return ""
    detail = "; ".join(f"{fn}: {kind} '{val}'" for fn, kind, val in findings)
    reason = (f"AF-AUD-6: {len(findings)} placeholder occurrence(s) "
              f"on rendered slides ({detail})")
    _write_provenance(run_dir, {"check_aud_placeholder_render": {
        "deferred": False, "findings": len(findings),
        "offenders": findings, "sidecars_scanned": len(sidecars), "reason": reason}})
    return reason


def check_hook_verbatim(run_dir, slides_path=None):
    """AF-HOOK-5 — every occurrence of the canonical hook in slide copy is char-exact."""
    intake = _intake(run_dir)
    hook = str(intake.get("hook", "")).strip()
    if not hook:
        _write_provenance(run_dir, {"check_hook_verbatim": {
            "deferred": True, "reason": "no canonical hook in intake.json"}})
        return ""
    sl = _slides(run_dir, slides_path)
    if not sl:
        _write_provenance(run_dir, {"check_hook_verbatim": {
            "deferred": True, "reason": "no slides.json readable"}})
        return ""
    findings = []
    hook_len = len(hook)
    for ordinal in sorted(sl):
        for i, block in enumerate(sl[ordinal]):
            text = str(block)
            # Char-exact match: clean
            if text.strip() == hook.strip():
                continue
            # Must be long enough for a window
            if len(text) < hook_len:
                continue
            best = 0.0
            best_window = ""
            for start in range(len(text) - hook_len + 1):
                window = text[start:start + hook_len]
                ratio = difflib.SequenceMatcher(None, hook, window).ratio()
                if ratio > best:
                    best = ratio
                    best_window = window
            if best >= HOOK_VARIANT_RATIO:
                findings.append((ordinal, i, best_window, best))
    if not findings:
        _write_provenance(run_dir, {"check_hook_verbatim": {
            "deferred": False, "findings": 0, "total_slides": len(sl),
            "hook": hook}})
        return ""
    detail_parts = []
    for s, i, window, ratio in findings:
        detail_parts.append(
            f"slide {s} copy[{i}]: '{window[:80]}' vs '{hook[:80]}' "
            f"(ratio {ratio:.3f})")
    detail = "; ".join(detail_parts)
    reason = f"AF-HOOK-5: {len(findings)} mutated hook occurrence(s) ({detail})"
    _write_provenance(run_dir, {"check_hook_verbatim": {
        "deferred": False, "findings": len(findings),
        "offenders": findings, "total_slides": len(sl), "hook": hook,
        "reason": reason}})
    return reason


def check_den_ladder_gaps(run_dir, slides_path=None):
    """AF-DEN-1 — adjacent price beats are at least DEN_PRICE_BEAT_MIN_GAP slides apart."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        _write_provenance(run_dir, {"check_den_ladder_gaps": {
            "deferred": True, "reason": "price_ladder.json absent"}})
        return ""
    rungs = ladder.get("rungs") or []
    drops = [r for r in rungs
             if str(r.get("kind", "")).upper() in ("DROP", "FINAL")
             or str(r.get("type", "")).upper() in ("DROP", "FINAL")]
    if not drops:
        drops = [r for r in rungs if r.get("target_slide") is not None]
    if len(drops) < 2:
        _write_provenance(run_dir, {"check_den_ladder_gaps": {
            "deferred": True, "reason": "fewer than 2 rungs with a target_slide"}})
        return ""
    drops = sorted(drops, key=lambda r: r.get("target_slide", 0))
    offenders = []
    for i in range(len(drops) - 1):
        a_slide = drops[i].get("target_slide", 0)
        b_slide = drops[i + 1].get("target_slide", 0)
        gap = b_slide - a_slide
        if gap < DEN_PRICE_BEAT_MIN_GAP:
            offenders.append((a_slide, b_slide, gap))
    if not offenders:
        sl = _slides(run_dir, slides_path)
        _write_provenance(run_dir, {"check_den_ladder_gaps": {
            "deferred": False, "findings": 0, "price_beats": len(drops),
            "total_slides": len(sl)}})
        return ""
    sl = _slides(run_dir, slides_path)
    detail = "; ".join(f"beat at {a} -> {b} gap={g}" for a, b, g in offenders)
    client_fixed = bool(_intake(run_dir).get("client_requested_slide_count"))
    clause = ""
    if client_fixed:
        count = _intake(run_dir)["client_requested_slide_count"]
        clause = (f" RE-SPACE the ladder inside the client's fixed "
                  f"{count}-slide count; do NOT add slides.")
    reason = (f"AF-DEN-1: {len(offenders)} price-beat gap(s) below "
              f"{DEN_PRICE_BEAT_MIN_GAP} slides ({detail}).{clause}")
    _write_provenance(run_dir, {"check_den_ladder_gaps": {
        "deferred": False, "findings": len(offenders),
        "offenders": offenders, "price_beats": len(drops),
        "total_slides": len(sl), "reason": reason}})
    return reason


def check_den_anchor_depth(run_dir, slides_path=None):
    """AF-DEN-2 — anchor depth within [DEN_ANCHOR_DEPTH_MIN, DEN_ANCHOR_DEPTH_MAX]."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        _write_provenance(run_dir, {"check_den_anchor_depth": {
            "deferred": True, "reason": "price_ladder.json absent"}})
        return ""
    rungs = ladder.get("rungs") or []
    anchor = None
    for r in rungs:
        k = str(r.get("kind", "")).upper()
        t = str(r.get("type", "")).upper()
        if "ANCHOR" in (k, t):
            anchor = r
            break
    if anchor is None:
        _write_provenance(run_dir, {"check_den_anchor_depth": {
            "deferred": True, "reason": "no ANCHOR rung in price_ladder.json"}})
        return ""
    anchor_slide = anchor.get("target_slide")
    if anchor_slide is None:
        _write_provenance(run_dir, {"check_den_anchor_depth": {
            "deferred": True, "reason": "ANCHOR rung has no target_slide"}})
        return ""
    sl = _slides(run_dir, slides_path)
    total = len(sl)
    if total == 0:
        _write_provenance(run_dir, {"check_den_anchor_depth": {
            "deferred": True, "reason": "deck total unknown"}})
        return ""
    depth = anchor_slide / total
    if depth < DEN_ANCHOR_DEPTH_MIN or depth > DEN_ANCHOR_DEPTH_MAX:
        pct = round(depth * 100)
        band = f"{int(DEN_ANCHOR_DEPTH_MIN * 100)}-{int(DEN_ANCHOR_DEPTH_MAX * 100)}%"
        reason = (f"AF-DEN-2: anchor at slide {anchor_slide}/{total} "
                  f"= {pct}%, outside {band} (divergence: 30-40% prose target vs "
                  f"25-45% trigger row; the trigger row is what this enforcer implements)")
        _write_provenance(run_dir, {"check_den_anchor_depth": {
            "deferred": False, "findings": 1,
            "anchor_slide": anchor_slide, "total_slides": total,
            "depth": depth, "reason": reason}})
        return reason
    _write_provenance(run_dir, {"check_den_anchor_depth": {
        "deferred": False, "findings": 0,
        "anchor_slide": anchor_slide, "total_slides": total, "depth": depth}})
    return ""


def check_den_stack_before_drop(run_dir, slides_path=None):
    """AF-DEN-4 — value-stack ARC beat appears BEFORE the first DROP beat (ORDER only)."""
    offsets = _arc_marker_offsets(run_dir)
    if not offsets:
        _write_provenance(run_dir, {"check_den_stack_before_drop": {
            "deferred": True, "reason": "no ARC markers in slides_copy.md"}})
        return ""
    stack_offs = []
    for tag in DEN_STACK_TAGS:
        stack_offs.extend(offsets.get(tag, []))
    drop_offs = []
    for tag in DEN_DROP_TAGS:
        drop_offs.extend(offsets.get(tag, []))
    if not drop_offs:
        _write_provenance(run_dir, {"check_den_stack_before_drop": {
            "deferred": True,
            "reason": "no DROP beat tagged in slides_copy.md (pitchless deck)"}})
        return ""
    if not stack_offs:
        reason = ("AF-DEN-4: no value-stack beat found before the first DROP "
                  "(ORDER ONLY — the check proves a value-stack tag precedes the "
                  "first DROP tag; it does NOT prove the stack is itemized or that "
                  "its total exceeds the anchor)")
        _write_provenance(run_dir, {"check_den_stack_before_drop": {
            "deferred": False, "findings": 1,
            "reason": reason, "stack_tags_found": [],
            "drop_tags_found": sorted(drop_offs)}})
        return reason
    if min(stack_offs) < min(drop_offs):
        _write_provenance(run_dir, {"check_den_stack_before_drop": {
            "deferred": False, "findings": 0,
            "stack_first_offset": min(stack_offs),
            "drop_first_offset": min(drop_offs)}})
        return ""
    reason = ("AF-DEN-4: the first DROP beat comes before the value-stack beat "
              "(ORDER ONLY — the check proves a value-stack tag precedes the "
              "first DROP tag; it does NOT prove the stack is itemized or that "
              "its total exceeds the anchor)")
    _write_provenance(run_dir, {"check_den_stack_before_drop": {
        "deferred": False, "findings": 1,
        "reason": reason, "stack_first_offset": min(stack_offs),
        "drop_first_offset": min(drop_offs)}})
    return reason


def check_den_repitch_block(run_dir, slides_path=None):
    """AF-DEN-7 — post-FINAL slide count within [DEN_REPITCH_MIN, DEN_REPITCH_MAX]."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        _write_provenance(run_dir, {"check_den_repitch_block": {
            "deferred": True, "reason": "price_ladder.json absent"}})
        return ""
    rungs = ladder.get("rungs") or []
    final = None
    for r in rungs:
        k = str(r.get("kind", "")).upper()
        t = str(r.get("type", "")).upper()
        if k == "FINAL" or t == "FINAL":
            final = r
            break
    if final is None:
        _write_provenance(run_dir, {"check_den_repitch_block": {
            "deferred": True, "reason": "no FINAL rung in price_ladder.json"}})
        return ""
    final_slide = final.get("target_slide")
    if final_slide is None:
        _write_provenance(run_dir, {"check_den_repitch_block": {
            "deferred": True, "reason": "FINAL rung has no target_slide"}})
        return ""
    sl = _slides(run_dir, slides_path)
    total = len(sl)
    if total == 0:
        _write_provenance(run_dir, {"check_den_repitch_block": {
            "deferred": True, "reason": "deck total unknown"}})
        return ""
    post = total - final_slide
    if post < DEN_REPITCH_MIN or post > DEN_REPITCH_MAX:
        reason = (f"AF-DEN-7: {post} post-FINAL slide(s), outside "
                  f"[{DEN_REPITCH_MIN}, {DEN_REPITCH_MAX}] (COUNT ONLY — the "
                  f"check proves 4-7 slides follow the FINAL price; it does NOT "
                  f"prove they recap the stack, restate the promises or reset the "
                  f"urgency)")
        _write_provenance(run_dir, {"check_den_repitch_block": {
            "deferred": False, "findings": 1,
            "post_final": post, "final_slide": final_slide,
            "total_slides": total, "reason": reason}})
        return reason
    _write_provenance(run_dir, {"check_den_repitch_block": {
        "deferred": False, "findings": 0,
        "post_final": post, "final_slide": final_slide, "total_slides": total}})
    return ""


# ── Ordered enforcer list (FIX 15 — defined here so every name resolves) ─────

def _enforcers():
    """Ordered list so the most actionable defects appear first."""
    return [
        check_obi_text_blocks,
        check_obi_headline_words,
        check_aud_meta_tokens,
        check_aud_credentials,
        check_aud_placeholder_render,
        check_hook_verbatim,
        check_den_ladder_gaps,
        check_den_anchor_depth,
        check_den_stack_before_drop,
        check_den_repitch_block,
    ]

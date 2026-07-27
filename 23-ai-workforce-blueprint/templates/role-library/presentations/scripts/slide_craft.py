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
import json
import os
import re
from pathlib import Path
from typing import Optional

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

_WORD_RE = re.compile(r"[0-9A-Za-z][0-9A-Za-z'’\-]*")
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


def _read_json(path: Path):
    """Parse-error-tolerant JSON read, mirroring build_deck._read_json."""
    try:
        return json.loads(path.read_text())
    except Exception as exc:  # noqa: BLE001
        return {"__parse_error__": str(exc)}


def _slides(run_dir: Path, slides_path: Optional[Path]) -> dict:
    """{ordinal: [copy blocks]} for the deck that will actually be rendered, and the
    slide total. Delegates to build_deck's own loaders via the wrapper, which passes
    them in; slide_craft never imports build_deck (one direction only, U047's rule).

    Duplicates _load_slide_copy_map's candidate order (:3222-3225) deliberately to
    avoid a circular import. Returns {} when no slides.json can be read — every caller
    then DEFERS."""
    candidates = []
    if slides_path is not None:
        candidates.append(slides_path)
    candidates += [run_dir / "working" / "copy" / "slides.json",
                   run_dir / "slides.json",
                   run_dir / "working" / "slides.json"]
    for p in candidates:
        if not p.exists():
            continue
        obj = _read_json(p)
        slides = obj if isinstance(obj, list) else (
            obj.get("slides") if isinstance(obj, dict) and "__parse_error__" not in obj else None)
        if isinstance(slides, list) and slides:
            out = {}
            for s in slides:
                if isinstance(s, dict) and isinstance(s.get("slide"), int):
                    out[s["slide"]] = s.get("copy")
            if out:
                return out
    return {}


def _intake(run_dir: Path) -> dict:
    """working/copy/intake.json as a dict, {} on absence or parse failure.
    Same candidate order build_deck._read_dark_optin uses (build_deck.py:5149)."""
    p = run_dir / "working" / "copy" / "intake.json"
    if not p.exists():
        return {}
    obj = _read_json(p)
    if not isinstance(obj, dict) or "__parse_error__" in obj:
        return {}
    return obj


def _price_ladder(run_dir: Path) -> Optional[dict]:
    """working/copy/price_ladder.json, or None. The key vocabulary is
    pitch_engines_check.load_run's (:409-418) and chk_cadence's (:126-133):
    rungs[] each carrying kind|type in {DROP, FINAL, ANCHOR, ...} and target_slide.
    None on absence -> every DEN check DEFERS. Measured: zero such files exist in the
    repository today, so on every deck that exists this returns None."""
    p = run_dir / "working" / "copy" / "price_ladder.json"
    if not p.exists():
        return None
    obj = _read_json(p)
    if not isinstance(obj, dict) or "__parse_error__" in obj:
        return None
    return obj


def _arc_marker_offsets(run_dir: Path) -> dict:
    """{TAG: [character offsets]} from slides_copy.md's <!-- ARC: ... --> / [ARC:...]
    markers. Byte-for-byte the same pattern pitch_engines_check._arc_tags_in_order
    (:83-96) uses, duplicated rather than imported so this module has no import-order
    dependency on that one.

    OFFSETS ARE NOT SLIDE NUMBERS. They give ORDER, monotonically and correctly, and
    they give NOTHING ELSE. Any check that needs adjacency (AF-DEN-3) or a slide gap
    (AF-DEN-6) is NOT implementable from them and is not implemented — see the
    human_judged rows. chk_cadence:135-138 says the same thing about its own use."""
    p = run_dir / "working" / "copy" / "slides_copy.md"
    if not p.exists():
        p = run_dir / "slides_copy.md"
    if not p.exists():
        return {}
    text = p.read_text()
    tags = {}
    for m in re.finditer(r'(?:<!--\s*ARC:\s*([^>]+?)\s*-->|\[ARC:\s*([^\]]+?)\s*\])',
                         text):
        raw = (m.group(1) or m.group(2) or "")
        toks = [t.strip().upper() for t in re.split(r'[\s,]+', raw) if t.strip()]
        for t in toks:
            tags.setdefault(t, []).append(m.start())
    return tags


def _write_provenance(run_dir: Path, payload: dict) -> None:
    """Write PROVENANCE_REL (best-effort, never raises). Records, per check: whether it
    ran or deferred and why, the inputs it found, the thresholds it applied and every
    finding. A deferred craft gate must be VISIBLE, not silent — that is the whole
    lesson of a defer that reads as a pass. Mirrors _record_ocr_readback
    (build_deck.py:1289-1297) and U047's slide_geometry.json provenance file."""
    try:
        out = run_dir / PROVENANCE_REL
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2))
    except Exception:  # noqa: BLE001
        pass


# ── Public checks ────────────────────────────────────────────────────────────

def check_obi_text_blocks(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-OBI-1 — no slide carries more than OBI_TEXT_BLOCK_MAX non-empty copy blocks.

    Counts len([c for c in copy if str(c).strip()]) per slide. This is a count of
    copy[] ITSELF, not of copy[3:] — build_deck's COPY_BULLET_MAX_COUNT = 3 bounds the
    bullets, this bounds the blocks, and a headline+subhead+kicker+1-bullet slide
    legitimately passes that band and fails this one.

    Deck-level report, deck-level single verdict: names every offending slide with its
    block count, then returns one message. Returns "" on pass or defer."""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    offenders = []
    for ordinal in sorted(slides):
        copy = slides[ordinal]
        if not isinstance(copy, list):
            continue
        blocks = [c for c in copy if isinstance(c, str) and c.strip()]
        if len(blocks) > OBI_TEXT_BLOCK_MAX:
            offenders.append((ordinal, len(blocks)))
    if not offenders:
        return ""
    parts = [f"slide {s}: {n} blocks (ceiling {OBI_TEXT_BLOCK_MAX})"
             for s, n in offenders]
    return f"AF-OBI-1: {len(offenders)} slide(s) carry more than {OBI_TEXT_BLOCK_MAX} non-empty text blocks — one idea per slide (SOP-SLIDE-01 §2.3). Offenders: {'; '.join(parts)}."


def check_obi_headline_words(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-OBI-2 — copy[0] carries at most OBI_HEADLINE_WORD_MAX words.

    Word count is _WORD_RE.findall on copy[0], which counts hyphenated and apostrophe
    forms as one word. Names the slide, the measured count and the ceiling in the
    message so a copywriter can act on it without re-counting. Returns "" on pass or
    defer; defers when copy[0] is absent or not a string (schema validation and
    AF-COPY-BAND own that)."""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    offenders = []
    for ordinal in sorted(slides):
        copy = slides[ordinal]
        if not isinstance(copy, list) or not copy:
            continue
        headline = copy[0]
        if not isinstance(headline, str) or not headline.strip():
            continue
        words = _WORD_RE.findall(headline)
        if len(words) > OBI_HEADLINE_WORD_MAX:
            offenders.append((ordinal, len(words)))
    if not offenders:
        return ""
    parts = [f"slide {s}: {n} words (ceiling {OBI_HEADLINE_WORD_MAX})"
             for s, n in offenders]
    return f"AF-OBI-2: {len(offenders)} headline(s) exceed {OBI_HEADLINE_WORD_MAX} words — the headline is a single tight idea (SOP-SLIDE-01 §2.4). Offenders: {'; '.join(parts)}."


def check_aud_meta_tokens(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-AUD-4 — no AUD_META_TOKENS substring appears in any copy block, matched
    case-insensitively on the raw block text.

    Section-5 line 164 specifies the method: "literal 'webinar' + format/technique-
    announcement match". This is that literal scan and nothing more; it does not attempt
    to recognise an unlisted meta line, and the ruleset row says so. Names the slide,
    the block index and the matched token. Returns "" on pass or defer."""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    offenders = []
    for ordinal in sorted(slides):
        copy = slides[ordinal]
        if not isinstance(copy, list):
            continue
        for bi, block in enumerate(copy):
            if not isinstance(block, str):
                continue
            lower = block.lower()
            for tok in AUD_META_TOKENS:
                if tok.lower() in lower:
                    offenders.append((ordinal, bi, tok))
                    break
    if not offenders:
        return ""
    parts = [f"slide {s} block {bi}: '{tok}'"
             for s, bi, tok in offenders[:10]]
    more = "" if len(offenders) <= 10 else f" (+{len(offenders) - 10} more)"
    return f"AF-AUD-4: {len(offenders)} copy block(s) contain a banned meta/technique-announcement token — never tell the audience what you are doing (SOP-SLIDE-02 §2.4). Offenders: {'; '.join(parts)}{more}."


def check_aud_credentials(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-AUD-5 — no AUD_CREDENTIAL_TOKENS substring appears in a NON-HEADLINE block.

    SOP-SLIDE-02 §3 AUD-5's Detection column scopes the trigger to a credential
    "rendered as body copy on the face", so copy[0] is exempt: a headline naming a
    credential is a design choice the doctrine does not ban, a body paragraph arguing
    one is. Scoping the check to copy[1:] is what keeps it from firing on legitimate
    quote-slide headlines. Returns "" on pass or defer."""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    offenders = []
    for ordinal in sorted(slides):
        copy = slides[ordinal]
        if not isinstance(copy, list) or len(copy) < 2:
            continue
        for bi in range(1, len(copy)):
            block = copy[bi]
            if not isinstance(block, str):
                continue
            lower = block.lower()
            for tok in AUD_CREDENTIAL_TOKENS:
                if tok.lower() in lower:
                    offenders.append((ordinal, bi, tok))
                    break
    if not offenders:
        return ""
    parts = [f"slide {s} block {bi}: '{tok}'"
             for s, bi, tok in offenders[:10]]
    more = "" if len(offenders) <= 10 else f" (+{len(offenders) - 10} more)"
    return f"AF-AUD-5: {len(offenders)} non-headline copy block(s) carry a credential/justification marker — the deck earns trust, it never argues for it (SOP-SLIDE-02 §2.5). Offenders: {'; '.join(parts)}{more}."


def check_aud_placeholder_render(run_dir: Path,
                                slides_path: Optional[Path] = None) -> str:
    """AF-AUD-6 / AF-PLACEHOLDER — no bracket token and no PLACEHOLDER_TOKENS substring
    appears in the OCR'd text of any RENDERED slide.

    Reads renders/slide-*.ocr.json (written by build_deck._record_ocr_readback,
    :1289-1297) and tests its "ocr_text" field with BRACKET_TOKEN_RE plus the token
    list. Section-5 line 166 gives the regex verbatim: `\\[[^\\]]*\\]` + token
    substrings on rendered text.

    RENDERED, not copy: SOP-SLIDE-02 §2.6 permits a [CLIENT TO SUPPLY] placeholder at
    the copy stage and bans it on a rendered face. Checking copy would fail work the
    doctrine allows.

    Defers when renders/ is absent, holds no .ocr.json sidecar, or every sidecar has
    checked:false — the OCR engine's availability is U027's gate, not this one's.
    Returns "" on pass or defer."""
    renders_dir = run_dir / "renders"
    if not renders_dir.exists():
        return ""
    ocr_files = sorted(renders_dir.glob("slide-*.ocr.json"))
    if not ocr_files:
        return ""
    has_any_checked = False
    offenders = []
    for fp in ocr_files:
        obj = _read_json(fp)
        if not isinstance(obj, dict) or "__parse_error__" in obj:
            continue
        if not obj.get("checked"):
            continue
        has_any_checked = True
        ocr_text = obj.get("ocr_text", "") or ""
        bracket_matches = BRACKET_TOKEN_RE.findall(ocr_text)
        token_matches = [tok for tok in PLACEHOLDER_TOKENS
                         if tok.lower() in ocr_text.lower()]
        if bracket_matches or token_matches:
            offenders.append((fp.stem, bracket_matches[:10], token_matches[:10]))
    if not has_any_checked:
        return ""
    if not offenders:
        return ""
    parts = [f"{stem}: brackets={brk} tokens={tok}"
             for stem, brk, tok in offenders[:10]]
    more = "" if len(offenders) <= 10 else f" (+{len(offenders) - 10} more)"
    return f"AF-AUD-6: {len(offenders)} rendered slide(s) carry a build/placeholder token on the delivered face — a [CLIENT TO SUPPLY] block must never ship (SOP-SLIDE-02 §2.6). Offenders: {'; '.join(parts)}{more}."


def check_hook_verbatim(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-HOOK-5 — every near-occurrence of the canonical hook in slide copy is
    CHAR-EXACT.

    The canonical hook is intake.json's "hook" key — the string
    intelligence_engines_check._load_intake_hook (:167-180) reads and the one
    pitch_engines_check.chk_speech_hook_count counts. SOP-SLIDE-03 §3/§5.4 name
    mission_prd.json instead; a whole-repository census found zero files of that name,
    so the code's file wins and the correction is recorded.

    For each copy block: if it contains the hook char-exact, clean. Else compute
    difflib.SequenceMatcher(None, hook, window).ratio() over the best-matching window;
    a ratio >= HOOK_VARIANT_RATIO with no char-exact hit is a MUTATION and fails,
    naming both strings. Below the ratio it is different text and is ignored.

    This is the gap AF-HOOK-1 cannot close: _check_hook_refrain_copy COUNTS char-exact
    occurrences, so a mutated hook simply is not counted — it makes the count go DOWN
    and can trip AF-NO-HOOK-REFRAIN, which reports the wrong defect. Returns "" on pass
    or defer; defers when intake.json declares no hook."""
    intake = _intake(run_dir)
    hook = (intake.get("hook") or "").strip()
    if not hook:
        return ""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    mutations = []
    for ordinal in sorted(slides):
        copy = slides[ordinal]
        if not isinstance(copy, list):
            continue
        for bi, block in enumerate(copy):
            if not isinstance(block, str):
                continue
            if hook in block:
                continue  # char-exact: clean
            # Test every window of len(hook) in block for similarity
            best = 0.0
            best_win = ""
            for i in range(max(0, len(block) - len(hook) + 1)):
                window = block[i:i + len(hook)]
                ratio = difflib.SequenceMatcher(None, hook, window).ratio()
                if ratio > best:
                    best = ratio
                    best_win = window
            if best >= HOOK_VARIANT_RATIO:
                mutations.append((ordinal, bi, best_win[:80]))
    if not mutations:
        return ""
    parts = [f"slide {s} block {bi}: rendered '{win}' vs canonical '{hook[:80]}'"
             for s, bi, win in mutations[:5]]
    more = "" if len(mutations) <= 5 else f" (+{len(mutations) - 5} more)"
    return f"AF-HOOK-5: {len(mutations)} near-variant(s) of the canonical hook in slide copy — the refrain must be char-exact everywhere it recurs (SOP-SLIDE-03 §2.4, ratio >= {HOOK_VARIANT_RATIO}). Offenders: {'; '.join(parts)}{more}."


def check_den_ladder_gaps(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-DEN-1 — adjacent price beats are at least DEN_PRICE_BEAT_MIN_GAP slides apart.

    Sorts price_ladder.json rungs by target_slide (chk_cadence's own selection logic,
    :126-133), then reports every adjacent pair whose gap is below the floor, naming
    both beats, both slide numbers and the gap.

    THE CLIENT'S COUNT WINS. When intake.json.client_requested_slide_count is set, the
    message says explicitly that the repair is to RE-SPACE the ladder inside the client's
    fixed length, never to lengthen the deck (SOP-SLIDE-04 §5.0; AF-SLIDE-COUNT-EXACT is
    the enforcer of the other half). The check still reports; it never asks for slides.

    Returns "" on pass or defer; defers when price_ladder.json is absent, has fewer than
    two rungs with a target_slide, or the deck total cannot be read."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        return ""
    rungs = ladder.get("rungs") or []
    # Select rungs with an integer target_slide (chk_cadence:126-133)
    price_beats = []
    for r in rungs:
        if not isinstance(r, dict):
            continue
        ts = r.get("target_slide")
        if isinstance(ts, int):
            kind = str(r.get("kind", r.get("type", "")))
            price_beats.append((ts, kind))
    if len(price_beats) < 2:
        return ""
    price_beats.sort(key=lambda x: x[0])
    offenders = []
    for i in range(len(price_beats) - 1):
        gap = price_beats[i + 1][0] - price_beats[i][0]
        if gap < DEN_PRICE_BEAT_MIN_GAP:
            offenders.append((price_beats[i], price_beats[i + 1], gap))
    if not offenders:
        return ""
    slides = _slides(run_dir, slides_path)
    total_slides = len(slides) if slides else None
    intake = _intake(run_dir)
    client_fixed = intake.get("client_requested_slide_count")
    client_note = ""
    if isinstance(client_fixed, (int, float)) and client_fixed > 0:
        client_note = (f" CLIENT HAS REQUESTED EXACTLY {int(client_fixed)} SLIDES "
                       f"(AF-SLIDE-COUNT-EXACT) — re-space the ladder inside the "
                       f"client's fixed length; do NOT lengthen the deck.")
    parts = [f"beats {a[1]}(s{a[0]}) -> {b[1]}(s{b[0]}): gap {gap} (floor {DEN_PRICE_BEAT_MIN_GAP})"
             for a, b, gap in offenders]
    info = f" (total {total_slides} slides)" if total_slides is not None else ""
    return f"AF-DEN-1: {len(offenders)} adjacent price-beat pair(s) below the {DEN_PRICE_BEAT_MIN_GAP}-slide minimum gap{info} — price beats must breathe (SOP-SLIDE-04 §2.1).{client_note} Offenders: {'; '.join(parts)}."


def check_den_anchor_depth(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-DEN-2 — the ANCHOR rung's depth is within
    [DEN_ANCHOR_DEPTH_MIN, DEN_ANCHOR_DEPTH_MAX] of the full deck.

    depth = anchor_target_slide / total_slides, total from the slides.json the renderer
    will render. Message quotes the measured percentage and the band. Returns "" on pass
    or defer; defers when no rung is kind/type ANCHOR or the total is unknown."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        return ""
    rungs = ladder.get("rungs") or []
    anchor = None
    for r in rungs:
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind", r.get("type", ""))).upper()
        ts = r.get("target_slide")
        if "ANCHOR" in kind and isinstance(ts, int):
            anchor = ts
            break
    if anchor is None:
        return ""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    total = len(slides)
    if total == 0:
        return ""
    depth = anchor / total
    band = f"{int(DEN_ANCHOR_DEPTH_MIN * 100)}-{int(DEN_ANCHOR_DEPTH_MAX * 100)}%"
    if DEN_ANCHOR_DEPTH_MIN <= depth <= DEN_ANCHOR_DEPTH_MAX:
        return ""
    return (f"AF-DEN-2: anchor at slide {anchor} of {total} = {depth:.0%} depth "
            f"— outside the {band} band (SOP-SLIDE-04 §3 DEN-2, trigger row "
            f"25-45%; §2.2 prose target 30-40% is the TARGET, not the trigger).")


def check_den_stack_before_drop(run_dir: Path,
                                slides_path: Optional[Path] = None) -> str:
    """AF-DEN-4 — a value-stack ARC beat appears BEFORE the first DROP beat.

    Order-only, which is exactly what _arc_marker_offsets can answer honestly:
    min(offsets of DEN_STACK_TAGS) < min(offsets of DEN_DROP_TAGS). Identical comparison
    shape to the live pitch_engines_check.chk_promise_before_price (:343-369).

    It does NOT check that the stack is itemized or that its total exceeds the anchor —
    SOP-SLIDE-04 §2.4 requires both and both are judgement. The ruleset row says the
    check covers ORDER ONLY. Returns "" on pass or defer; defers when no DROP beat is
    tagged (a pitchless deck) or slides_copy.md carries no ARC markers."""
    offsets = _arc_marker_offsets(run_dir)
    if not offsets:
        return ""
    stack_offs = []
    for tag in DEN_STACK_TAGS:
        stack_offs.extend(offsets.get(tag, []))
    drop_offs = []
    for tag in DEN_DROP_TAGS:
        drop_offs.extend(offsets.get(tag, []))
    if not drop_offs:
        return ""
    if not stack_offs:
        return (f"AF-DEN-4: no value-stack beat (VALUE_STACK/STACK) tagged before the "
                f"first DROP beat — the stack must precede the price ladder "
                f"(SOP-SLIDE-04 §2.4; ORDER ONLY — itemization and anchor-exceeding "
                f"total remain HUMAN JUDGEMENT).")
    if min(stack_offs) < min(drop_offs):
        return ""
    return (f"AF-DEN-4: the first DROP beat appears BEFORE the first value-stack beat "
            f"— the stack must precede the price ladder (SOP-SLIDE-04 §2.4; "
            f"ORDER ONLY — itemization and anchor-exceeding total remain "
            f"HUMAN JUDGEMENT).")


def check_den_repitch_block(run_dir: Path, slides_path: Optional[Path] = None) -> str:
    """AF-DEN-7 — the post-FINAL slide count is within [DEN_REPITCH_MIN,
    DEN_REPITCH_MAX].

    total_slides - final_rung.target_slide, from price_ladder.json and the rendered
    slides.json. Reports the measured count and the band.

    It counts SLIDES, not content: SOP-SLIDE-04 §2.7 also requires the block to "recap
    the stack, restate the promises, reset the urgency", which is judgement, and the
    ruleset row says the enforcer covers the COUNT only. Returns "" on pass or defer."""
    ladder = _price_ladder(run_dir)
    if ladder is None:
        return ""
    rungs = ladder.get("rungs") or []
    final = None
    for r in rungs:
        if not isinstance(r, dict):
            continue
        kind = str(r.get("kind", r.get("type", ""))).upper()
        ts = r.get("target_slide")
        if kind == "FINAL" and isinstance(ts, int):
            final = ts
            break
    if final is None:
        return ""
    slides = _slides(run_dir, slides_path)
    if not slides:
        return ""
    total = len(slides)
    if total == 0:
        return ""
    post = total - final
    band = f"{DEN_REPITCH_MIN}-{DEN_REPITCH_MAX}"
    if DEN_REPITCH_MIN <= post <= DEN_REPITCH_MAX:
        return ""
    return (f"AF-DEN-7: {post} post-FINAL slide(s) — outside the {band}-slide "
            f"re-pitch band (SOP-SLIDE-04 §2.7; total {total}, FINAL at slide {final}; "
            f"COUNT ONLY — content of the re-pitch block remains HUMAN JUDGEMENT).")

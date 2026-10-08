"""Text/product acceptance checks. Directive 17.8. Stdlib only.

Fail-closed: missing evidence never passes. UNAVAILABLE cannot become PASS.
Machine checks reject absent/short CTA holds, caption drift from approved
lines, and readability claims without an independent vision-model receipt.
OCR alone never proves readability or identity (17.8); makers never judge
their own output (17.6).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import protected_names  # noqa: E402  H7 caption gate

CTA_HOLD_MIN_SECONDS = 3.0
MOBILE_RENDITION_WIDTH_PX = 360

PASS = "PASS"
FAIL = "FAIL"
UNAVAILABLE = "UNAVAILABLE"

_NONWORD = re.compile(r"[^\w\s]", re.UNICODE)


def _norm_line(s):
    s = unicodedata.normalize("NFKC", s or "")
    s = _NONWORD.sub("", s.casefold())
    return " ".join(s.split())


def _apply_pronunciation(line, pmap):
    # Approved spelling substitutions may change spelling in generation
    # input, never meaning: map whole words on the approved side, then
    # compare against the rendered caption.
    if not pmap:
        return line
    return " ".join(pmap.get(w, w) for w in (line or "").split())


def check_cta_hold(hold_seconds):
    """Final CTA hold at least 3s. Missing measurement -> UNAVAILABLE."""
    if hold_seconds is None:
        return (UNAVAILABLE, "no CTA hold measurement; cannot pass without one")
    try:
        value = float(hold_seconds)
    except (TypeError, ValueError):
        return (FAIL, "CTA hold not a number: %r" % (hold_seconds,))
    if value < CTA_HOLD_MIN_SECONDS:
        return (FAIL, "CTA hold %.2fs below minimum %.1fs"
                % (value, CTA_HOLD_MIN_SECONDS))
    return (PASS, "CTA hold %.2fs meets minimum" % value)


def check_captions(caption_lines, approved_lines, pronunciation_map=None,
                   captions_enabled=True, protected=(),
                   text_source=protected_names.CAPTION_TEXT_SOURCE):
    """Caption correctness vs approved lines. Exact normalized match.

    H7: text must come from the approved lyric sheet (``text_source``), never
    speech-to-text; any word mismatch fails and a changed protected name
    (character/brand) is named in the detail."""
    if not captions_enabled:
        return (UNAVAILABLE, "captions disabled; nothing to check")
    if approved_lines is None:
        return (UNAVAILABLE, "no approved lines bound; cannot check captions")
    bad = protected_names.check_captions(
        caption_lines, approved_lines, protected, text_source)
    if bad:
        return (FAIL, "; ".join(bad))
    expected = [_norm_line(_apply_pronunciation(line, pronunciation_map))
                for line in approved_lines]
    actual = [_norm_line(line) for line in (caption_lines or [])]
    if len(actual) != len(expected):
        return (FAIL, "caption line count %d != approved %d"
                % (len(actual), len(expected)))
    for i, (got, want) in enumerate(zip(actual, expected)):
        if got != want:
            return (FAIL, "caption line %d differs from approved" % i)
    return (PASS, "%d caption lines match approved" % len(expected))


def check_mobile_readability(receipt, maker_identities=()):
    """360px mobile-readability hook. Validates a vision-model receipt.

    Never performs OCR and never claims OCR proves readability: an
    ocr-only receipt is rejected outright. Requires an independent
    reviewer, 360px rendition width, safe-area confirmation and a PASS
    verdict from the vision review.
    """
    if not receipt:
        return (UNAVAILABLE, "no mobile-readability receipt; vision review required")
    if receipt.get("method") == "ocr-only":
        return (FAIL, "OCR alone does not prove readability or identity")
    reviewer = (receipt.get("reviewer") or {}).get("identity", "")
    if not reviewer:
        return (FAIL, "receipt has no reviewer identity")
    if reviewer in (maker_identities or ()):
        return (FAIL, "maker cannot self-review readability")
    if receipt.get("rendition_width_px") != MOBILE_RENDITION_WIDTH_PX:
        return (FAIL, "rendition width must be %dpx mobile"
                % MOBILE_RENDITION_WIDTH_PX)
    if receipt.get("within_safe_areas") is not True:
        return (FAIL, "placement safe-area confirmation missing")
    if receipt.get("verdict") != PASS:
        return (FAIL, "vision reviewer verdict is not PASS")
    return (PASS, "independent vision review confirms 360px readability")


def check_exact_copy(rendered_text, approved_brief):
    """Exact required copy + product identity (product/offer/CTA verbatim)."""
    brief = approved_brief or {}
    missing = [k for k in ("product_name", "offer_text", "cta_text")
               if not brief.get(k)]
    if missing:
        return (UNAVAILABLE, "brief missing required copy: " + ",".join(missing))
    hay = rendered_text or ""
    for key in ("product_name", "offer_text", "cta_text"):
        if brief[key] not in hay:
            return (FAIL, "required %s absent from rendered text" % key)
    return (PASS, "required copy present verbatim")


def text_product_check(rendered_text, approved_brief, cta_hold_seconds,
                       readability_receipt, maker_identities=()):
    """Combined 17.8 text/product gate. Worst verdict wins; UNAVAILABLE
    never becomes PASS."""
    results = {
        "copy": check_exact_copy(rendered_text, approved_brief),
        "cta_hold": check_cta_hold(cta_hold_seconds),
        "readability": check_mobile_readability(readability_receipt,
                                                maker_identities),
    }
    verdicts = [v for v, _ in results.values()]
    if FAIL in verdicts:
        overall = FAIL
    elif UNAVAILABLE in verdicts:
        overall = UNAVAILABLE
    else:
        overall = PASS
    return (overall, results)

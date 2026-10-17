#!/usr/bin/env python3
"""Lint intended public copy/HTML for private production-label leakage.

1.0.3 enforcement additions (order C3):
- bracket placeholders  [EVENT_DATE]  -> FAIL; WARN only with --test-run
- data-section= / data-framework= attributes
- alt/title/aria-label values containing a private label or IMG-<digits>
- HTML comments containing NOTE / HANDOFF / NOT FOR PUBLICATION / INTERNAL
- private framework labels from references/private-label-list.txt matched
  case-insensitively as whole phrases in visible text, attribute values, and
  class names

S71-03 addition (Signature Launch change order, packet doc 07 section 3):
- --no-offer-pricing enforces the signature_launch_landing profile rule:
  no offer pricing on any public surface. Semantic and structural scan of
  visible copy, image alt text, title attributes, accessibility labels,
  page title, meta content and JSON-LD structured data for pricing signals
  (currency amounts, bare price figures in pricing context, per-period
  prices, installment amounts, discount amounts/percentages, price-anchor
  amounts, spelled-out prices). Legitimate numbers (dates, phone numbers,
  seat/session counts, non-price percentages, countdowns) are masked or
  suppressed, never flagged. Off by default so legacy profiles are
  unchanged; see GATE.md at the skill root.
"""
import argparse
import re
import sys
import unicodedata
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parent.parent
LABEL_FILE = SKILL_ROOT / "references" / "private-label-list.txt"

PATTERNS = [
    ("private section label", re.compile(r"^\s*(?:#+\s*)?SECTION\s+\d+[A-Z]?\s*[:.\-]", re.I | re.M)),
    ("private part label", re.compile(r"^\s*(?:#+\s*)?PART\s+\d+[A-Z]?\s*[:.\-]", re.I | re.M)),
    ("CTA production marker", re.compile(r"\bCTA\s+BUTTON\b", re.I)),
    ("image prompt marker", re.compile(r"\bIMAGE\s+PROMPT\b", re.I)),
    ("QC score marker", re.compile(r"\bQC\s+SCORE\b", re.I)),
    ("internal review marker", re.compile(r"\bINTERNAL\s+REVIEW\b", re.I)),
    ("private note marker", re.compile(r"\bPRIVATE\s+NOTE\b", re.I)),
    ("founder-letter part marker", re.compile(r"\bFOUNDER\s+LETTER\s+PART\b", re.I)),
    ("prompt ID marker", re.compile(r"\bPROMPT\s+ID\b", re.I)),
]
COMMENT_PATTERN = re.compile(
    r"<!--(?:(?!-->).)*(?:private|internal|prompt|qc score|section\s+\d)(?:(?!-->).)*-->", re.I | re.S
)

# C3 additions
BRACKET_PLACEHOLDER = re.compile(r"\[[A-Z0-9_ ]{3,}\]")
DATA_ATTRS = re.compile(r"\bdata-(?:section|framework)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
REF_ATTRS = re.compile(r"\b(?:alt|title|aria-label)\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
IMG_REF = re.compile(r"\bIMG-\d+", re.I)
NOTE_COMMENT = re.compile(
    r"<!--(?:(?!-->).)*(?:\bNOTE\b|\bHANDOFF\b|NOT\s+FOR\s+PUBLICATION|\bINTERNAL\b)(?:(?!-->).)*-->",
    re.I | re.S,
)
ATTR = re.compile(r"""\b([\w-]+)\s*=\s*("[^"]*"|'[^']*'|[^\s>]+)""")


def load_private_labels():
    labels = []
    if LABEL_FILE.exists():
        for raw in LABEL_FILE.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if line and not line.startswith("#"):
                labels.append(line)
    return labels


def strip_comments(text):
    return re.sub(r"<!--.*?-->", " ", text, flags=re.S)


def strip_tags(text):
    text = re.sub(r"<script\b.*?</script>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<style\b.*?</style>", " ", text, flags=re.I | re.S)
    return re.sub(r"<[^>]+>", " ", text)


def unquote(value):
    v = value.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def contains_whole_phrase(haystack, needle):
    pattern = r"(?<![A-Za-z0-9])" + re.escape(needle) + r"(?![A-Za-z0-9])"
    return re.search(pattern, haystack, re.I) is not None


def line_number(text, index):
    return text.count("\n", 0, index) + 1


# ---------------------------------------------------------------------------
# S71-03 no-offer-pricing gate (Signature Launch change order, packet doc 07
# section 3; acceptance unit A06, L1 layer). The named
# signature_launch_landing profile carries NO offer pricing on any public
# surface. The check is semantic and structural, never a dollar-sign-only
# test: pricing context, not the currency symbol, is what incriminates a
# number. Legitimate numbers (dates, phone numbers, seat/session counts,
# non-price percentages, deadline countdowns) are masked or suppressed.
# ---------------------------------------------------------------------------

_NUM = r"\d[\d,]*(?:\.\d{2})?"
_SYM_AMT = r"[$€£¥]\s?" + _NUM
_CODE_AMT = (r"(?:\b(?:USD|EUR|GBP|CAD|AUD)\s?" + _NUM
             + r"|\b" + _NUM + r"\s?(?:USD|EUR|GBP|CAD|AUD)\b)")
_AMT = r"(?:" + _SYM_AMT + r"|" + _CODE_AMT + r"|" + _NUM + r")"
_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|"
          r"October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|"
          r"Oct|Nov|Dec)")
_NUMWORD = (r"(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|"
            r"twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|"
            r"nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|"
            r"ninety|hundred|thousand)")

# Numbers that are never prices: phone numbers and calendar dates are
# blanked out of each segment before the signal scan (length-preserving,
# so offsets and line numbers stay true).
_PHONE_RE = re.compile(
    r"(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)\s*|\d{3}[\s.-])\d{3}[\s.-]\d{4}\b"
    r"|\b\d{3}[-.]\d{4}\b")
_DATE_RES = [
    re.compile(r"\b" + _MONTH + r"\s+\d{1,2}(?:st|nd|rd|th)?(?:\s*,\s*\d{4})?\b", re.I),
    re.compile(r"\b\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"(?:\s+\d{4})?\b", re.I),
    re.compile(r"\b\d{4}-\d{1,2}-\d{1,2}\b"),
    re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b"),
    re.compile(r"\b\d{1,2}-\d{1,2}-\d{4}\b"),
]

# A bare number directly followed by one of these unit nouns is a count, a
# duration or a rating, not a price ("only 48 hours", "a total of 500
# founders", "a satisfaction rate of 5 stars"; "the rate of 92%" is handled
# by the "%" rule in _suppressed_after). Ratings are denominated in stars,
# never in money, so a star figure suppresses exactly like a count.
_COUNT_NOUNS = {
    "sessions", "seats", "spots", "modules", "lessons", "pages", "steps",
    "days", "weeks", "months", "years", "hours", "minutes", "seconds",
    "people", "members", "students", "founders", "graduates", "clients",
    "attendees", "speakers", "stories", "businesses", "companies",
    "star", "stars",
}

# (priority, signal label, pattern); lower priority wins when spans overlap,
# so the most specific construction names the reason (an installment span
# that contains a currency amount reports "installment amount").
_PRICE_SIGNALS = [
    (0, "installment amount", re.compile(
        r"\b(?:\d+|" + _NUMWORD + r")\s+(?:easy\s+|monthly\s+|weekly\s+)?"
        r"(?:payments|installments|instalments)\s+of\s+(?:just\s+|only\s+)?"
        + _AMT, re.I)),
    (0, "installment amount", re.compile(
        r"\b(?:payments?|installments?|instalments?)\s+of\s+"
        r"(?:just\s+|only\s+)?" + _AMT, re.I)),
    (1, "per-period price", re.compile(
        _AMT + r"\s*(?:/\s*(?:mo|month|yr|year|week)\b"
        r"|\s+per\s+(?:month|mo|year|yr|week)\b"
        r"|\s+a\s+(?:month|year)\b)", re.I)),
    (2, "discount amount", re.compile(
        r"(?:" + _SYM_AMT + r"|" + _NUM + r"\s+dollars)\s+off\b", re.I)),
    (2, "discount amount", re.compile(
        r"\bsave\s+(?:up to\s+)?" + _SYM_AMT, re.I)),
    (2, "discount percentage", re.compile(
        r"\b\d{1,3}(?:\.\d+)?\s?(?:%|percent|per\s+cent)\s+off\b", re.I)),
    (3, "price anchor amount", re.compile(
        r"\b(?:worth|valued\s+at|compare\s+at|compared\s+at|retail\s+value|"
        r"list\s+price|regular\s+price|normally|regularly|originally|value)"
        r"\b[^\d$€£¥]{0,24}?" + _AMT, re.I)),
    (3, "price anchor amount", re.compile(
        _SYM_AMT + r"\s+(?:value|worth)\b", re.I)),
    (4, "currency amount", re.compile(_SYM_AMT + r"|" + _CODE_AMT, re.I)),
    (4, "currency amount", re.compile(
        r"\b" + _NUM + r"\s?(?:dollars|bucks)\b", re.I)),
    (5, "spelled-out price", re.compile(
        r"\b" + _NUMWORD + r"(?:[\s-]+" + _NUMWORD + r"){0,3}\s+"
        r"(?:dollars|bucks)\b", re.I)),
    (6, "bare price figure", re.compile(
        r"\b(?:price|cost|tuition|fee|investment|deposit|total|rate|payment)"
        r"\s*(?:is|of|:|=)?\s*[\"']?\s?" + _AMT, re.I)),
    (6, "bare price figure", re.compile(
        r"\b(?:only|just)\s+" + _AMT, re.I)),
    (6, "bare price figure", re.compile(
        r"\bpay\s+(?:just\s+|only\s+)?" + _AMT, re.I)),
    (6, "bare price figure", re.compile(
        r"[\"']?(?:price|amount|cost)[\"']?\s*:\s*[\"']?" + _AMT, re.I)),
]

_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_JSONLD_RE = re.compile(
    r"<script\b[^>]*\btype\s*=\s*[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.I | re.S)
_TITLE_EL_RE = re.compile(r"<title\b[^>]*>(.*?)</title>", re.I | re.S)
_META_TAG_RE = re.compile(r"<meta\b[^>]*>", re.I)
_CONTENT_ATTR_RE = re.compile(r"\bcontent\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.I)
_SCRIPT_BLOCK_RE = re.compile(r"<script\b.*?</script>", re.I | re.S)
_STYLE_BLOCK_RE = re.compile(r"<style\b.*?</style>", re.I | re.S)
_ANY_TAG_RE = re.compile(r"<[^>]+>")

_SURFACE_ATTRS = {
    "alt": "image alt text",
    "aria-label": "accessibility label",
    "aria-description": "accessibility label",
    "title": "title attribute",
}
# Signal classes whose bare (symbol-less) amounts can still be counts:
# they are suppressed when the number is followed by a count noun or "%".
_SUPPRESSIBLE = {"installment amount", "price anchor amount", "bare price figure"}
_CURRENCY_MARK = re.compile(r"[$€£¥]|\b(?:USD|EUR|GBP|CAD|AUD|dollars|bucks)\b", re.I)


def _blank(text):
    """Length- and newline-preserving blank (offsets stay true)."""
    return "".join("\n" if ch == "\n" else " " for ch in text)


def _mask_spans(text, patterns):
    chars = list(text)
    for pattern in patterns:
        for match in pattern.finditer(text):
            for i in range(match.start(), match.end()):
                if chars[i] != "\n":
                    chars[i] = " "
    return "".join(chars)


def _suppressed_after(segment, end):
    """True when the number ending at `end` is a count/duration/statistic:
    directly followed by "%", by the spelled-out "percent"/"per cent"
    (the same statistic in words, so typography alone never decides), or
    by a count unit noun. A spelled-out discount ("98 percent off") is
    still caught: suppression only applies to the bare-figure classes,
    and a suppressed candidate never occupies its span, so the
    discount-percentage signal claims the "N percent off" span."""
    rest = segment[end:end + 24].lstrip()
    if rest.startswith("%"):
        return True
    if re.match(r"(?:percent|per\s+cent)\b", rest, re.I):
        return True
    match = re.match(r"\+?\s*([A-Za-z]+)", rest)
    return bool(match and match.group(1).lower() in _COUNT_NOUNS)


def _price_hits(segment):
    """All non-overlapping pricing-signal hits in one masked segment, as
    (start, end, signal label, matched text), most specific class first."""
    candidates = []
    for priority, label, pattern in _PRICE_SIGNALS:
        for match in pattern.finditer(segment):
            candidates.append((match.start(), priority,
                                 -(match.end() - match.start()), match.end(),
                                 label, match.group(0)))
    candidates.sort()
    hits = []
    taken = []
    for start, _priority, _neglen, end, label, sample in candidates:
        if any(start < t_end and end > t_start for t_start, t_end in taken):
            continue
        if (label in _SUPPRESSIBLE and not _CURRENCY_MARK.search(sample)
                and _suppressed_after(segment, end)):
            continue
        taken.append((start, end))
        hits.append((start, end, label, sample))
    return hits


def scan_offer_pricing(text):
    """S71-03 gate over one file's text. Returns [(line, label, sample)]
    with labels of the form 'offer price in <surface>: <signal class>'."""
    findings = []
    working = _mask_spans(text, [_COMMENT_RE])
    segments = []  # (surface name, segment text, offset into text)
    for match in _JSONLD_RE.finditer(working):
        segments.append(("structured data (JSON-LD)", match.group(1), match.start(1)))
    for match in _TITLE_EL_RE.finditer(working):
        segments.append(("page title (structured content)", match.group(1),
                         match.start(1)))
    for match in _META_TAG_RE.finditer(working):
        content = _CONTENT_ATTR_RE.search(match.group(0))
        if content:
            raw = content.group(1)
            offset = match.start() + content.start(1) + (1 if raw[:1] in "\"'" else 0)
            segments.append(("meta content (structured content)", unquote(raw), offset))
    for match in ATTR.finditer(working):
        name = match.group(1).lower()
        if name in _SURFACE_ATTRS:
            raw = match.group(2)
            offset = match.start(2) + (1 if raw[:1] in "\"'" else 0)
            segments.append((_SURFACE_ATTRS[name], unquote(raw), offset))
    # Visible copy: scripts, styles and the title element are blanked (the
    # first two are not visible text; the title is a structured surface,
    # already captured above), then every remaining tag is blanked so only
    # rendered text remains. Markdown image alt text stays in the text and
    # is scanned as visible copy.
    visible = _mask_spans(working, [_SCRIPT_BLOCK_RE, _STYLE_BLOCK_RE, _TITLE_EL_RE])
    visible = _ANY_TAG_RE.sub(lambda m: _blank(m.group(0)), visible)
    segments.append(("visible copy", visible, 0))
    for surface, segment, offset in segments:
        masked = _mask_spans(segment, [_PHONE_RE] + _DATE_RES)
        for start, _end, signal, sample in _price_hits(masked):
            findings.append((line_number(text, offset + start),
                             f"offer price in {surface}: {signal}",
                             sample.strip()[:120]))
    findings.sort()
    return findings


def scan(text, private_labels, test_run=False, no_offer_pricing=False):
    """Return (errors, warnings). test_run downgrades bracket placeholders to WARN."""
    errors = []
    warnings = []

    def add(kind, line, label, sample, warn=False):
        entry = (line, label, sample)
        (warnings if warn else errors).append((kind, entry))

    nfc = unicodedata.normalize("NFC", text)

    for label, pattern in PATTERNS:
        for match in pattern.finditer(nfc):
            add("marker", line_number(nfc, match.start()), label, match.group(0).strip())

    for match in COMMENT_PATTERN.finditer(nfc):
        add("comment", line_number(nfc, match.start()), "private/internal HTML comment",
            match.group(0)[:120].replace("\n", " "))

    for match in NOTE_COMMENT.finditer(nfc):
        add("comment", line_number(nfc, match.start()), "note/handoff HTML comment",
            match.group(0)[:120].replace("\n", " "))

    for match in DATA_ATTRS.finditer(nfc):
        add("attribute", line_number(nfc, match.start()), "data-section/data-framework attribute",
            match.group(0)[:120])

    for match in REF_ATTRS.finditer(nfc):
        value = unicodedata.normalize("NFC", unquote(match.group(1)))
        if IMG_REF.search(value):
            add("attribute", line_number(nfc, match.start()), "IMG-<n> in alt/title/aria-label",
                match.group(0)[:120])
        else:
            for label in private_labels:
                if contains_whole_phrase(value, label):
                    add("attribute", line_number(nfc, match.start()),
                        f"private label in alt/title/aria-label: {label!r}", match.group(0)[:120])
                    break

    for match in BRACKET_PLACEHOLDER.finditer(nfc):
        add("placeholder", line_number(nfc, match.start()), "bracket placeholder",
            match.group(0), warn=test_run)

    # Private framework labels: whole phrases in visible text, attribute values,
    # and class names.
    visible = strip_tags(strip_comments(nfc))
    for match in ATTR.finditer(re.sub(r"<!--.*?-->", " ", nfc, flags=re.S)):
        name = match.group(1).lower()
        value = unquote(match.group(2))
        if name == "class":
            visible += " " + value

    for label in private_labels:
        for i, hay in enumerate((visible,)):
            idx = None
            for m in re.finditer(r"(?<![A-Za-z0-9])" + re.escape(label) + r"(?![A-Za-z0-9])", hay, re.I):
                idx = m.start()
                break
            if idx is not None:
                add("label", line_number(visible, idx), f"private framework label in public copy: {label!r}",
                    hay[max(0, idx - 40):idx + len(label) + 40].replace("\n", " ").strip())
                break

    if no_offer_pricing:
        for line, label, sample in scan_offer_pricing(nfc):
            add("price", line, label, sample)

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Lint intended public copy/HTML for definite BlackCEO production-label leakage.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--test-run", action="store_true",
                        help="Downgrade bracket placeholders from FAIL to WARN (test runs only).")
    parser.add_argument("--no-offer-pricing", action="store_true",
                        help="Enforce the signature_launch_landing profile rule (packet "
                             "doc 07 section 3): FAIL on any offer pricing on a public "
                             "surface. Off by default; legacy profiles are unchanged.")
    args = parser.parse_args()

    private_labels = load_private_labels()

    all_errors = []
    all_warnings = []
    for path in args.files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            print(f"FAIL: could not read {path}: {exc}")
            return 2
        errs, warns = scan(text, private_labels, test_run=args.test_run,
                           no_offer_pricing=args.no_offer_pricing)
        for kind, (line, label, sample) in errs:
            all_errors.append((path, kind, line, label, sample))
        for kind, (line, label, sample) in warns:
            all_warnings.append((path, kind, line, label, sample))

    for path, kind, line, label, sample in all_warnings:
        print(f"WARNING: {path}:{line}: {label}: {sample}")
    if all_errors:
        kinds = {kind for _path, kind, _line, _label, _sample in all_errors}
        if "price" in kinds:
            print("FAIL: offer pricing detected on a no-price public surface.")
        if kinds - {"price"}:
            print("FAIL: private production markers detected.")
        for path, kind, line, label, sample in all_errors:
            print(f"- {path}:{line}: {label}: {sample}")
        return 1
    print("PASS: no definite private production markers detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

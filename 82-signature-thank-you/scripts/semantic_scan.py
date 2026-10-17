"""Semantic pitch PRE-SCREEN for Skill 82 thank-you copy (S82-09).

This scanner is a conservative pre-screen for the A14 semantic review
defined in references/semantic-review-protocol.md. It is NOT the
semantic review itself: it flags candidate promotional phrases in
rendered HTML or plain copy text so an independent human/model
reviewer knows where to look. A clean scan never substitutes for the
recorded review verdict, and a flag is a prompt for review, not by
itself a verdict.

What it flags (case-insensitive, per line of visible text):

- urgency / scarcity language ("act now", "limited time",
  "last chance", "today only", "while supplies last", ...);
- "one more thing" constructions;
- "upgrade" / "don't miss" pitch verbs;
- other direct pitch markers ("buy now", "special offer",
  "get it before", ...);
- percentage-off claims ("50% off", "save 25%");
- price-pressure patterns ("only $19") — but ONLY outside the order
  summary section: an actual purchased amount inside the summary is
  required content in launch mode (A14), not a pitch. The scanner
  suppresses every pattern inside the rendered order-summary section
  (``<section class="ty82-order">``) as well as inside <style> blocks
  and HTML comments, neither of which is buyer-visible copy.

Usage:
    python3 scripts/semantic_scan.py FILE [FILE ...]
    python3 scripts/semantic_scan.py -          # read stdin

Exit 0 = no flags. Exit 1 = at least one flag (printed with its line
number, reason, and the offending excerpt). Exit 2 = usage/IO error.

Stdlib only. Deterministic.
"""

import re
import sys

# (reason, compiled pattern) — visible-copy pitch markers.
_PATTERNS = [
    ("urgency_scarcity", re.compile(
        r"\b(act now|hurry|limited[ -]time|last chance|today only|"
        r"while supplies last|offer ends|ends soon|expires soon|"
        r"before it(?:'s| is) gone|selling fast|only a few left|"
        r"countdown|time is running out|don'?t wait)\b", re.I)),
    ("one_more_thing", re.compile(r"\bone more thing\b", re.I)),
    ("pitch_verb", re.compile(r"\b(upgrade|don'?t miss|do not miss)\b",
                              re.I)),
    ("pitch_marker", re.compile(
        r"\b(buy now|special offer|exclusive offer|get it before|"
        r"price goes up|add to your order|complete your order with)\b",
        re.I)),
    ("percentage_off", re.compile(
        r"\b\d{1,3}\s*%\s*off\b|\bsave\s+\d{1,3}\s*%", re.I)),
]

# Price-pressure ("only $19") is judged separately because actual
# purchased amounts are legitimate inside the order summary.
_PRICE_PRESSURE = re.compile(r"\bonly\s+\$[\d,]+(?:\.\d{2})?", re.I)

_STYLE_RE = re.compile(r"<style\b[^>]*>.*?</style>", re.I | re.S)
_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_ORDER_SECTION_RE = re.compile(
    r"<section\b[^>]*class=\"[^\"]*ty82-order[^\"]*\"[^>]*>.*?</section>",
    re.I | re.S)


def _blank(match):
    """Replace a removed block with its newlines, keeping line numbers."""
    return "\n" * match.group(0).count("\n")


def visible_lines(text):
    """Buyer-visible text lines: no styles, comments, or tags."""
    text = _STYLE_RE.sub(_blank, text)
    text = _COMMENT_RE.sub(_blank, text)
    return [_TAG_RE.sub(" ", line) for line in text.splitlines()]


def scan_text(text):
    """Return findings: [{line, reason, excerpt}], in document order."""
    findings = []

    def _scan(segment_lines, first_line_no, in_summary):
        for offset, raw in enumerate(segment_lines):
            line = " ".join(raw.split())
            if not line:
                continue
            for reason, pattern in _PATTERNS:
                for match in pattern.finditer(line):
                    findings.append({
                        "line": first_line_no + offset,
                        "reason": reason,
                        "excerpt": line,
                        "match": match.group(0),
                    })
            if not in_summary:
                for match in _PRICE_PRESSURE.finditer(line):
                    findings.append({
                        "line": first_line_no + offset,
                        "reason": "price_pressure_outside_summary",
                        "excerpt": line,
                        "match": match.group(0),
                    })

    # Split the document at the order-summary section so amounts inside
    # it are never treated as price pressure, then scan both parts.
    summary = _ORDER_SECTION_RE.search(text)
    if summary is None:
        _scan(visible_lines(text), 1, in_summary=False)
    else:
        before = text[:summary.start()]
        inside = text[summary.start():summary.end()]
        after = text[summary.end():]
        _scan(visible_lines(before), 1, in_summary=False)
        inside_first = before.count("\n") + 1
        _scan(visible_lines(inside), inside_first, in_summary=True)
        after_first = inside_first + inside.count("\n")
        _scan(visible_lines(after), after_first, in_summary=False)

    findings.sort(key=lambda f: (f["line"], f["reason"]))
    return findings


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv == ["-h"] or argv == ["--help"]:
        print(__doc__.strip().splitlines()[0])
        print("usage: semantic_scan.py FILE [FILE ...]  ('-' reads stdin)")
        return 0 if argv else 2

    total = 0
    for path in argv:
        try:
            if path == "-":
                text = sys.stdin.read()
                label = "<stdin>"
            else:
                with open(path, encoding="utf-8") as fh:
                    text = fh.read()
                label = path
        except OSError as exc:
            print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
            return 2
        findings = scan_text(text)
        for finding in findings:
            print(f"FLAG {label}:{finding['line']}: "
                  f"[{finding['reason']}] matched "
                  f"{finding['match']!r} :: {finding['excerpt']}")
        total += len(findings)

    if total:
        print(f"FAIL: {total} semantic pitch flag(s) — pre-screen only; "
              "route to the independent semantic review "
              "(references/semantic-review-protocol.md).")
        return 1
    print("PASS: no semantic pitch flags (pre-screen only — this is "
          "NOT the semantic review; see "
          "references/semantic-review-protocol.md).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

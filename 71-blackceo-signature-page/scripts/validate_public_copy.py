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


def scan(text, private_labels, test_run=False):
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

    return errors, warnings


def main():
    parser = argparse.ArgumentParser(
        description="Lint intended public copy/HTML for definite BlackCEO production-label leakage.")
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--test-run", action="store_true",
                        help="Downgrade bracket placeholders from FAIL to WARN (test runs only).")
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
        errs, warns = scan(text, private_labels, test_run=args.test_run)
        for kind, (line, label, sample) in errs:
            all_errors.append((path, kind, line, label, sample))
        for kind, (line, label, sample) in warns:
            all_warnings.append((path, kind, line, label, sample))

    for path, kind, line, label, sample in all_warnings:
        print(f"WARNING: {path}:{line}: {label}: {sample}")
    if all_errors:
        print("FAIL: private production markers detected.")
        for path, kind, line, label, sample in all_errors:
            print(f"- {path}:{line}: {label}: {sample}")
        return 1
    print("PASS: no definite private production markers detected.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

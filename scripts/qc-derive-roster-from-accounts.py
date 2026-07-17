#!/usr/bin/env python3
"""
qc-derive-roster-from-accounts.py — derives a client-name roster STRUCTURALLY
from ~/clawd/accounts/accounts.md (or $OPENCLAW_ACCOUNTS_MD) at runtime, so
scripts/qc-assert-no-client-names.sh can run its authoritative, roster-based
check on an operator box that has never had a curated
~/.openclaw/client-roster.txt — which, as of this fix, is every operator box
including the primary one. Before this, "no curated roster file" silently
meant "the roster-specific check has never once run here either."

⛔ THIS SCRIPT NEVER PRINTS A DERIVED NAME. It prints exactly one summary
line to stderr (a COUNT) and writes candidate roster lines to STDOUT only,
which the caller consumes directly (process substitution) and never persists
to a file inside this repo. Never commit, log, or echo the output of this
script anywhere it could land in a tracked file, a CI log line beyond the
count, or a commit message.

WHY accounts.md AND NOT THE THREE SUMMARY TABLES IN THE SAME FILE:
  accounts.md also contains a "Quick reference table", a "Management Plan
  Designations" table, and a "Client emails" table. All three were checked
  structurally before this script was written and found to be STALE relative
  to the per-client detail sections (e.g. the Quick Reference table is
  missing several numbered rows that exist as full sections further down the
  file, and Management Plan Designations lists the same row number under two
  different category tables). The per-client detail sections themselves
  (the "### N. Name — ..." / "### CN. Name — ..." headers, and a couple of
  clients promoted to their own "## Name — ..." top-level heading) are the
  most current, single-entry-per-client source, each independently
  corroborated by that section's own "Owner" / "Owner / business" table row.
  This was verified against the live file before choosing this design; see
  the fix's PR description for the header-count cross-check.

DERIVATION (structural, not hand-keyed):
  1. "### <NUM>. <Name> — ..." and "### C<NUM>. <Name> — ..." headers
     (NUM = digits). The three "### <emoji> <Category> (...)" sub-headers
     inside "Management Plan Designations" do NOT match this shape (no
     "<number>. " prefix) and are correctly excluded.
  2. "## <Name> — ..." top-level headers that are NOT one of the known
     structural/category headings (an explicit denylist of section titles
     that are never a client identity — Credentials, Procedure, Client setup
     standards, How to use this file, Local — Mac mini, Client VPSes,
     Client VPS (Lyric's...), Contabo VPS clients, Management Plan
     Designations, Quick reference table, Client emails, Common commands,
     Related). A handful of clients get promoted to this level instead of a
     numbered ### subsection.
  3. "| Owner | <Name> |" / "| Owner / business | <Name> ... |" table rows
     — a redundant per-section cross-check of (1)/(2).
  Each raw candidate is trimmed to its leading Title-Case word run (stops at
  an em/en-dash, opening paren, backtick, or emoji/annotation), then run
  through the same "not all words are common English dictionary words"
  filter used by qc-heuristic-name-shapes.py, to drop anything that is not
  proper-noun-shaped (guards against a header whose shape slips past 1/2/3
  above but reads as ordinary prose).

FAILURE IS SIGNALED, NEVER SWALLOWED:
  Exit 0 with roster lines on stdout only when at least one candidate was
  derived. Exit 1 (nothing on stdout) if the source file is missing, empty,
  unreadable, or produced zero candidates — the caller (qc-assert-no-client-
  names.sh) treats that as "this source could not run" and must not report
  a PASS on that basis; see this script's own header for why.

Usage:
  python3 scripts/qc-derive-roster-from-accounts.py [--path /custom/accounts.md]
  Reads $OPENCLAW_ACCOUNTS_MD if --path is not given, else
  ~/clawd/accounts/accounts.md. Prints one roster line per derived candidate
  to stdout (for the caller to consume), and a single count line to stderr.
"""
import os
import re
import sys

# Every non-client "## ..." structural/category heading, verified against a
# live count of the file's own ## headers before this was written (15 total;
# these are the ones that are never a client identity). Any "## ..." header
# NOT starting with one of these prefixes is treated as a promoted per-client
# heading (a client is occasionally moved out of the numbered ### list into
# its own top-level section — e.g. two clients are promoted this way today).
DENYLIST_H2_PREFIXES = (
    "🔐 Credentials",
    "🆕 Procedure",
    "🌙 Client setup standards",
    "How to use this file",
    "Local — Mac mini",
    "Client VPSes",
    "Client VPS (Lyric's",
    "Contabo VPS clients",
    "Management Plan Designations",
    "Quick reference table",
    "📧 Client emails",
    "Common commands",
    "Related",
)

NUMBERED_H3_RE = re.compile(r'^###\s+(?:[A-Z]{1,2}\d+|\d+)\.\s+(.+)$')
H2_RE = re.compile(r'^##\s+(.+)$')
OWNER_ROW_RE = re.compile(
    r'^\|\s*\**Owner(?:\s*/\s*business)?\**\s*\|\s*(.+?)\s*\|'
)

# Stop the captured header/field text at the first shape that ends a name:
# em/en-dash, opening paren, backtick, pipe, or an emoji/warning glyph.
TRAIL_RE = re.compile(r'[—–(`|⚠️🆕🏢🖥️🧪🎙️🛟📞✉️].*$')
NAME_TOKEN_RE = re.compile(r"^[A-Z][a-zA-Z.'-]{1,20}$")

_DICT_CACHE = None


def _dict_words():
    global _DICT_CACHE
    if _DICT_CACHE is not None:
        return _DICT_CACHE
    words = set()
    try:
        with open("/usr/share/dict/words", errors="ignore") as fh:
            for line in fh:
                w = line.strip()
                if w:
                    words.add(w.lower())
    except OSError:
        pass
    _DICT_CACHE = words
    return words


def _clean(raw):
    text = TRAIL_RE.sub("", raw).strip()
    text = text.strip("*").strip()
    text = re.sub(r"\s{2,}", " ", text)
    return text


def _looks_like_candidate(name):
    words = name.split()
    if len(words) < 1 or len(words) > 4:
        return False
    for w in words:
        if not NAME_TOKEN_RE.match(w):
            return False
    dict_words = _dict_words()
    if len(words) == 1:
        # A single-token candidate (this roster legitimately has clients on
        # file by first name only) becomes a \bWord\b pattern in the gate —
        # same convention client-roster.example.txt documents for short
        # first names. That is much higher false-positive risk than a full
        # name, so require the word to NOT be an ordinary English word at
        # all (unlike the multi-word case below, precision here matters more
        # than recall).
        if dict_words and words[0].strip(".'-").lower() in dict_words:
            return False
        return True
    # Multi-word candidate: this source is already high-precision by
    # construction (every "### N. ..." header IS a client entry — verified
    # against the file's own header count before this was written), so unlike
    # the free-text heuristic scan in qc-heuristic-name-shapes.py, rejecting
    # "both words happen to also be common English words" here would only
    # drop real client names (a person can be named two ordinary words) for
    # no precision gain. No dictionary filter for the multi-word case.
    return True


def derive(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as fh:
            lines = fh.readlines()
    except OSError:
        return None  # source unreadable -> caller treats as "did not run"

    if not lines:
        return None

    candidates = set()

    for line in lines:
        m = NUMBERED_H3_RE.match(line)
        if m:
            name = _clean(m.group(1))
            if _looks_like_candidate(name):
                candidates.add(name)
            continue

        m = H2_RE.match(line)
        if m:
            raw_header = m.group(1).strip()
            if any(raw_header.startswith(p) for p in DENYLIST_H2_PREFIXES):
                continue
            name = _clean(raw_header)
            if _looks_like_candidate(name):
                candidates.add(name)
            continue

        m = OWNER_ROW_RE.match(line)
        if m:
            name = _clean(m.group(1))
            if _looks_like_candidate(name):
                candidates.add(name)
            continue

    return candidates


def main(argv):
    path = os.environ.get("OPENCLAW_ACCOUNTS_MD") or os.path.expanduser(
        "~/clawd/accounts/accounts.md"
    )
    args = argv[1:]
    i = 0
    while i < len(args):
        if args[i] == "--path" and i + 1 < len(args):
            path = args[i + 1]
            i += 2
        else:
            i += 1

    if not os.path.isfile(path):
        print(
            f"[qc-derive-roster-from-accounts] source not found at {path} "
            "(set OPENCLAW_ACCOUNTS_MD to override) — derivation DID NOT RUN.",
            file=sys.stderr,
        )
        return 1

    candidates = derive(path)
    if not candidates:
        print(
            f"[qc-derive-roster-from-accounts] source at {path} was read but "
            "produced ZERO usable candidates (empty, unreadable, or its "
            "structure has drifted from what this parser expects) — "
            "derivation DID NOT RUN a usable check.",
            file=sys.stderr,
        )
        return 1

    # Emit in the SAME two shapes client-roster.example.txt documents: full
    # (multi-word) names as literal patterns, single-word names \b-anchored
    # so a short token can't false-positive as a substring of another word.
    for name in sorted(candidates):
        if " " in name:
            print(name)
        else:
            print(f"\\b{name}\\b")

    print(
        f"[qc-derive-roster-from-accounts] derived {len(candidates)} "
        f"candidate roster entries from {path} (names withheld from this log "
        "by design).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

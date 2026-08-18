#!/usr/bin/env python3
"""
qc-expand-roster-name-forms.py — derives HIGHER-detection-power ERE patterns
from the roster patterns qc-assert-no-client-names.sh already loaded (either
a curated ~/.openclaw/client-roster.txt or the accounts.md-derived roster
from qc-derive-roster-from-accounts.py), so the gate can catch a client
identity referenced by less than its full "First Last" literal form.

WHY THIS EXISTS (CRITICAL-1, pre-878): a roster entry for a two-word name is
loaded as the literal string "First Last". `grep -E` only matches that when
BOTH words appear together, in that order, with a single space between them.
A real client's identity leaked into 4 tracked-file locations while the gate
reported PASS: 1 occurrence matched the full-name literal; the other 3 used
the client's FIRST NAME ALONE (prose, a pronoun-adjacent mention, and a
`<firstname>.zerohumanworkforce.com` hostname) and a
`bak-<firstname>-...` backup-filename suffix — none of which contain the
full "First Last" substring, so none matched. This script closes exactly
that gap.

⛔ NEVER PRINTS AN INPUT OR OUTPUT NAME/PATTERN TO STDERR OR ANY LOG. Reads
roster lines on stdin, writes ONLY new derived ERE patterns to stdout (for
the caller to fold into its scan alternation via process substitution), and
a single COUNT line to stderr — same withheld-content convention as
qc-derive-roster-from-accounts.py.

INPUT CONTRACT (stdin, one roster pattern per line — the same lines
qc-assert-no-client-names.sh already loaded into CLIENT_NAMES, from EITHER
source):
  - A bare multi-word literal, e.g. "First Last" (no leading backslash) —
    THIS is what gets expanded below.
  - An already-atomic pattern (starts with "\\b", or otherwise contains a
    regex metachar) — passed over untouched; it is single-token by
    construction and already matches every '.'/'-'/'/' -joined compound form
    directly via ordinary word-boundary behavior (proven: `\\bExample\\b`
    already matches inside "example.zerohumanworkforce.com" and
    "bak-example-..." because '.' and '-' are non-word characters), so there
    is nothing new to derive from it.

OUTPUT CONTRACT — TWO PRECISION TIERS, each line TAGGED so the caller can
route it to the matching grep pass (this repo's real BSD/macOS grep gets
measurably slower — not exponentially, but a case-insensitive multi-
alternative scan across this repo's ~7,000 tracked files runs in the
low tens of seconds rather than a couple, confirmed by direct timing before
this script was written — so this also keeps the case-insensitive
alternation from growing by more than it needs to):

  "CI:<pattern>" — case-INSENSITIVE-safe. Emitted for forms that carry their
  own corroborating structure, so an accidental collision with ordinary
  lowercase prose/code is negligible even without the dictionary-word
  filter below:
    1. COMPOUND forms — the full ordered word sequence joined with '-', '_',
       and '' (no separator), \\b-bounded as ONE token: "First-Last",
       "First_Last", "FirstLast". This is what catches a hostname/filename
       that FUSES the name without a plain space or a '.'/'-'-only join:
       `\\bFirst\\b` alone does NOT match inside "first_last" (word-boundary
       does not break on '_', a \\w character) or "firstlast" (no boundary
       in the middle at all) — proven against this repo's own grep before
       writing this script. TWO OR MORE proper-noun-shaped tokens fused
       together is itself the corroborating signal that this is a name, not
       prose, so this skips the dictionary filter even when one component
       (e.g. a first name like "Grace") is an ordinary English word alone.
    2. HOSTNAME-corroborated forms — \\bFirst\\.zerohumanworkforce\\.com\\b
       and \\bFirst\\.myvps\\b (the two "<client>.<domain>" conventions this
       repo's own tracked files already use — see the git history of the
       CRITICAL-1 fix this script closes). Catches the lowercase hostname
       leak form directly; scoped to these two specific domains rather than
       "any word followed by a dot" precisely because a bare `\\bWord\\.\\b`
       -style pattern would flag ordinary file-extension mentions
       ("word.py", "word.md") throughout the repo — measured and rejected
       for that reason before this design was finalized.
    3. BACKUP-FILENAME-corroborated forms — \\bbak[-_]First\\b and
       \\bFirst[-_]bak\\b (the "bak-<name>-..." convention this repo's own
       fix commits already use, e.g. "send-interview-link.sh.bak-<name>-
       ...").

  "CS:<pattern>" — case-SENSITIVE ONLY (exact Title-Case as derived). One
  \\bWord\\b per individual name component, but ONLY when that word does NOT
  also read as ordinary English (checked against /usr/share/dict/words,
  case-insensitive — the exact same filter qc-derive-roster-from-
  accounts.py already applies to single-word roster candidates) AND is at
  least MIN_STANDALONE_LEN characters. Measured on this repo's own tracked
  tree: the case-INSENSITIVE version of this exact check produced 100+
  false-positive file hits per noisy candidate (ordinary lowercase prose or
  code tokens that happen to not be in the dictionary file), and EVERY one
  of those hits vanished under an exact-case match — real client name
  mentions in prose are capitalized the same way the roster derived them, so
  case-sensitivity was free precision here with no measured recall cost on
  this repo. A component that fails the dictionary filter (e.g. "Grace")
  still gets full coverage via the full-name literal (already scanned) and
  via the CI compound/hostname/backup forms above, none of which depend on
  this filter passing.

MIN_STANDALONE_LEN=3: a 2-character standalone token is noise-level
ambiguous (matches constantly, catches nothing a longer form wouldn't also
catch) — same floor used elsewhere in this repo's name-shape heuristics.

Usage:
  printf '%s\\n' "${CLIENT_NAMES[@]}" | python3 scripts/qc-expand-roster-name-forms.py
"""
import re
import sys

MIN_STANDALONE_LEN = 3
NAME_TOKEN_RE = re.compile(r"^[A-Z][a-zA-Z'-]{1,20}$")
ATOMIC_PATTERN_MARKERS = ("\\b", "\\", "|", "(", ")", "[", "]", "*", "+", "?", "^", "$")

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


def _is_dictionary_word(word):
    dict_words = _dict_words()
    if not dict_words:
        # No dictionary available -> cannot clear a word as "ordinary
        # English" -> fail safe by treating it as non-dictionary (allow the
        # standalone form). Matches qc-derive-roster-from-accounts.py's own
        # fallback for the same missing-dictionary case.
        return False
    return word.strip("'-").lower() in dict_words


def expand_line(line):
    """Return a list of (tier, pattern) tuples for one roster line, tier is
    'CI' or 'CS'. Returns [] if the line is already atomic / not
    expandable."""
    line = line.strip()
    if not line:
        return []
    if any(marker in line for marker in ATOMIC_PATTERN_MARKERS):
        return []  # already an escaped/atomic single-token pattern
    words = line.split()
    if len(words) < 2:
        return []  # single bare word with no expansion to add
    if not all(NAME_TOKEN_RE.match(w) for w in words):
        return []  # not shaped like a plain name — do not guess at it

    out = []

    # 1. Compound forms (CI) — self-corroborating, no dictionary filter.
    for sep in ("-", "_", ""):
        compound = sep.join(words)
        out.append(("CI", r"\b" + re.escape(compound) + r"\b"))

    # 2. Hostname-corroborated forms (CI) — scoped to this repo's two real
    #    "<client>.<domain>" conventions, not a bare "word followed by a dot".
    for w in words:
        out.append(("CI", r"\b" + re.escape(w) + r"\.zerohumanworkforce\.com\b"))
        out.append(("CI", r"\b" + re.escape(w) + r"\.myvps\b"))

    # 3. Backup-filename-corroborated forms (CI) — the "bak-<name>-..." /
    #    "<name>-bak" convention this repo's own fix commits already use.
    for w in words:
        out.append(("CI", r"\bbak[-_]" + re.escape(w) + r"\b"))
        out.append(("CI", r"\b" + re.escape(w) + r"[-_]bak\b"))

    # 4. Standalone single-component forms (CS) — strict dictionary +
    #    length filter; case-sensitive only (see header for why).
    for w in words:
        if len(w) < MIN_STANDALONE_LEN:
            continue
        if _is_dictionary_word(w):
            continue
        out.append(("CS", r"\b" + re.escape(w) + r"\b"))

    return out


def main():
    derived = []
    for raw in sys.stdin:
        derived.extend(expand_line(raw))

    # De-dupe while preserving order (multiple roster lines can share a
    # component, e.g. two clients with the same first name).
    seen = set()
    unique = []
    for tier, pat in derived:
        key = (tier, pat)
        if key not in seen:
            seen.add(key)
            unique.append(key)

    for tier, pat in unique:
        print(f"{tier}:{pat}")

    ci_count = sum(1 for t, _ in unique if t == "CI")
    cs_count = sum(1 for t, _ in unique if t == "CS")
    print(
        f"[qc-expand-roster-name-forms] derived {len(unique)} additional "
        f"detection pattern(s) ({ci_count} case-insensitive-safe, "
        f"{cs_count} case-sensitive-only) from the loaded roster (forms "
        "withheld from this log by design).",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

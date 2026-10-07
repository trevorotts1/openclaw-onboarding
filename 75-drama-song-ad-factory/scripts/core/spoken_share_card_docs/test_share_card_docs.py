#!/usr/bin/env python3
"""D15 retarget tests: the choice card and the docs state 45 percent.

Proves the AF-SHARE-U2 acceptance points, stdlib only, zero network, zero
paid calls:

  1. the canonical numbers are 45 target / 55 ceiling / 40 floor, plus the
     short-opener and first-sung-within-10-seconds rules;
  2. the choice-card line states all of that;
  3. the docs wording states all of that AND carries the 5-minute reference
     note -- 57.0% spoken is over the new 55% limit, recipe still stands for
     everything else;
  4. the readers are fail-closed: planted retired-band text is named and
     refused, gutted wording is reported missing, clean wording passes (a
     check that cannot fail is not evidence);
  5. package hygiene: no media file, no absolute operator path, no network
     or provider code, no provider URL anywhere in this unit.

Mocked: sockets are replaced with a stub that raises, so any accidental
network use fails the suite instead of spending. Known-bad control: point
SPOKEN_SHARE_CARD_DOCS_PATH at a mutated copy of this package (receipts/
controls) and the same suite must FAIL.

Run: python3 core/spoken_share_card_docs/test_share_card_docs.py
"""
from __future__ import annotations

import os
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)                 # core/
sys.path.insert(0, CORE)

# Negative-control hook: point this at a mutated copy of the package and the
# same suite must fail. Used by the lane's controls, never in normal runs.
_OVERRIDE = os.environ.get("SPOKEN_SHARE_CARD_DOCS_PATH")
if _OVERRIDE:
    sys.path.insert(0, _OVERRIDE)

import spoken_share_card_docs as S            # noqa: E402  (package under test)
from spoken_share_card_docs import share_card_docs as M   # noqa: E402

# --- mocked environment: no live sockets, no spend -------------------------
_REAL_SOCKET = socket.socket

class _NoNetwork(_REAL_SOCKET):
    def connect(self, *a, **kw):
        raise AssertionError("network call during a mocked test")

    def connect_ex(self, *a, **kw):
        raise AssertionError("network call during a mocked test")

socket.socket = _NoNetwork                      # noqa: A001

FAILS = []

def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % str(detail)) if not cond else ""))
    if not cond:
        FAILS.append(name)


# --- 1. the numbers --------------------------------------------------------
def test_constants():
    check("target is 45 percent", M.SPOKEN_TARGET_PCT == 45,
          M.SPOKEN_TARGET_PCT)
    check("ceiling is 55 percent", M.SPOKEN_MAX_PCT == 55, M.SPOKEN_MAX_PCT)
    check("floor is 40 percent", M.SPOKEN_MIN_PCT == 40, M.SPOKEN_MIN_PCT)
    check("floor < target < ceiling",
          M.SPOKEN_MIN_PCT < M.SPOKEN_TARGET_PCT < M.SPOKEN_MAX_PCT)
    check("band is the new 40-55, not the retired one",
          (M.SPOKEN_MIN_PCT, M.SPOKEN_MAX_PCT) == (40, 55)
          and (M.SPOKEN_MIN_PCT, M.SPOKEN_MAX_PCT) != M.RETIRED_BAND_PCT)
    check("first sung line within about 10 seconds",
          M.FIRST_SUNG_WITHIN_SECONDS == 10, M.FIRST_SUNG_WITHIN_SECONDS)
    check("source cites Decision log 37 / plan 6.7",
          "Decision log 37" in M.SOURCE and "plan 6.7" in M.SOURCE, M.SOURCE)


# --- 2. the choice-card line ----------------------------------------------
def test_card_line_states_target():
    line = M.CARD_LINE
    check("card line is one line", "\n" not in line and line.strip() != "")
    check("card line is the Spoken: line",
          line.startswith(M.SPOKEN_LINE_PREFIX), line[:40])
    check("card line states 45 percent", "45%" in line, line)
    check("card line states the ceiling", "never above 55%" in line, line)
    check("card line states the floor", "never below 40%" in line, line)
    check("card line keeps the opener short", "short spoken opener" in line, line)
    check("card line carries the first-sung rule",
          "first sung line within about 10 seconds" in line, line)
    check("card block ships exactly the Spoken line",
          M.card_block() == [M.CARD_LINE], M.card_block())
    check("card line passes its own reader", M.check_card_text(line) == [],
          M.check_card_text(line))
    check("card label aligns to the plan 4.1 column (body starts at col 13)",
          line.index("%d%%" % M.SPOKEN_TARGET_PCT) == 13, repr(line[:20]))


# --- 3. the docs wording + the 5-minute reference note ---------------------
def test_docs_states_target():
    text = M.docs_statement()
    check("docs reader reports nothing missing", M.check_docs_text(text) == [],
          M.check_docs_text(text))
    check("docs state 45 percent", "target 45%" in text, text[:120])
    check("docs state never more than 55", "never more than 55%" in text)
    check("docs state never less than 40", "never less than 40%" in text)
    check("docs count rap as spoken", "rap counts as spoken" in text)
    check("docs keep the opener short", "opener stays short" in text)
    check("docs carry the first-sung-within-10s rule",
          "first sung line starts within about 10 seconds" in text)
    bare = M.check_docs_text(M.docs_statement(with_reference_note=False))
    check("docs without the reference note fail only on that note",
          len(bare) == 4 and all(
              ("reference" in r) or ("recipe" in r) or ("everything" in r)
              for r in bare), bare)


def test_reference_note_present():
    note = M.REFERENCE_NOTE
    check("reference note names the 5-minute reference ad",
          "5-minute" in note and "reference ad" in note, note[:80])
    check("reference note carries 57.0 percent", "57.0%" in note, note)
    check("reference note says it is over the new limit",
          "over the new 55% limit" in note, note)
    check("reference note keeps the recipe",
          "recipe still stands" in note, note)
    check("reference note scopes it to everything else",
          "everything else" in note, note)
    check("reference note is the docs paragraph",
          note in M.docs_statement())
    check("measure is the recorded 170.9 s of 300 s",
          M.REFERENCE_SPOKEN_SECONDS == 170.9
          and M.REFERENCE_LENGTH_SECONDS == 300.0,
          (M.REFERENCE_SPOKEN_SECONDS, M.REFERENCE_LENGTH_SECONDS))
    check("170.9/300 rounds to the recorded 57.0 percent",
          round(100.0 * M.REFERENCE_SPOKEN_SECONDS
                / M.REFERENCE_LENGTH_SECONDS, 1) == M.REFERENCE_SPOKEN_PCT)
    check("57 percent IS over the new 55 percent limit",
          M.reference_is_over_limit() is True)
    check("57 percent passed the retired band, which is why it stood",
          M.reference_within_retired_band() is True)
    check("new band and retired band differ",
          (M.SPOKEN_MIN_PCT, M.SPOKEN_MAX_PCT) != M.RETIRED_BAND_PCT)


# --- 4. fail-closed readers, with planted known-bad controls ---------------
_OLD_BAND = ("Spoken share target 40-70% of runtime (cap 70%), per-length "
             "60 / 55-60 / 55 / 50 percent.")

def test_negative_control_stale_text_is_refused():
    stale = M.find_stale(_OLD_BAND)
    check("planted retired band is detected", len(stale) >= 2, stale)
    card_reasons = M.check_card_text(_OLD_BAND)
    check("planted card text fails the card reader",
          len(card_reasons) >= 4, card_reasons)
    docs_reasons = M.check_docs_text(_OLD_BAND)
    check("planted docs text fails the docs reader",
          any("retired band" in r for r in docs_reasons)
          and any("45 percent" in r for r in docs_reasons), docs_reasons)


def test_negative_control_gutted_wording_is_reported():
    gutted = ("Spoken: 44% of the runtime (never above 60%, never below 30%)  "
              "/  long spoken opener  /  first sung line within about 30 seconds")
    reasons = M.check_card_text(gutted)
    check("wrong target reported", any("45 percent" in r for r in reasons),
          reasons)
    check("wrong ceiling reported", any("55 percent" in r for r in reasons),
          reasons)
    check("wrong floor reported", any("40 percent" in r for r in reasons),
          reasons)
    check("opener rule reported", any("opener" in r for r in reasons), reasons)
    check("first-sung rule reported",
          any("first sung" in r for r in reasons), reasons)


def test_positive_control_clean_text_passes():
    check("canonical card line is accepted",
          M.check_card_text(M.CARD_LINE) == [], M.check_card_text(M.CARD_LINE))
    check("canonical docs text is accepted",
          M.check_docs_text(M.docs_statement()) == [],
          M.check_docs_text(M.docs_statement()))
    check("clean prose is accepted",
          M.check_docs_text(
              "target 45% of runtime, never more than 55%, never less than "
              "40%. Rap counts as spoken. Opener stays short; first sung line "
              "starts within about 10 seconds. The 57.0% reference figure is "
              "over the new 55% limit; its recipe still stands for "
              "everything else.") == [])


def test_reader_type_guards():
    for fn in (M.check_card_text, M.check_docs_text, M.find_stale):
        try:
            fn(None)
        except TypeError:
            check("%s rejects non-text" % fn.__name__, True)
        else:
            check("%s rejects non-text" % fn.__name__, False)


# --- 5. package hygiene: no spend path, no media, no operator path ---------
# Needles are assembled at run time: a suite that greps for a banned string
# must never itself store that string (same trap the Velvet rename hit).
_HOME_PREFIX = "/" + "Users" + "/"
_URL_LIB = "import " + "urllib"
_REQUESTS = "import " + "requests"
_KIE = "api" + ".kie"
_SHIPPED_TOKENS = (_URL_LIB, _REQUESTS, "http.client",
                   "urlopen(", "import subprocess", _KIE,
                   "https" + "://", "http" + "://")
_SUITE_TOKENS = (_URL_LIB, _REQUESTS, "urlopen(", _KIE)
_MEDIA_EXT = (".mp4", ".mov", ".wav", ".mp3", ".png", ".jpg", ".jpeg",
              ".webp", ".srt", ".gif", ".avi", ".mkv", ".flac")

def _package_files():
    for name in sorted(os.listdir(HERE)):
        path = os.path.join(HERE, name)
        if os.path.isfile(path) and "__pycache__" not in path:
            yield path

def test_package_hygiene():
    files = list(_package_files())
    check("package has files", len(files) >= 4, [os.path.basename(f) for f in files])
    check("no media file in the unit",
          not [f for f in files if f.lower().endswith(_MEDIA_EXT)],
          [os.path.basename(f) for f in files if f.lower().endswith(_MEDIA_EXT)])
    bad_path, bad_token = [], []
    for path in files:
        with open(path, "r", encoding="utf-8") as handle:
            text = handle.read()
        if _HOME_PREFIX in text:
            bad_path.append(os.path.basename(path))
        if path.endswith(".py") and not os.path.basename(path).startswith("test_"):
            hits = [t for t in _SHIPPED_TOKENS if t in text]
            if hits:
                bad_token.append((os.path.basename(path), hits))
    check("no absolute operator path in the unit", not bad_path, bad_path)
    check("shipped module carries no network/provider/URL code",
          not bad_token, bad_token)
    with open(os.path.abspath(__file__), encoding="utf-8") as handle:
        suite_hits = [t for t in _SUITE_TOKENS if t in handle.read()]
    check("this suite itself never reaches the network", not suite_hits,
          suite_hits)
    check("unit makes no provider call: socket is mocked and never used",
          socket.socket is _NoNetwork)


def test_unit_docs_carry_no_retired_band_wording():
    """The unit's own docs must not advertise the band that was replaced."""
    for path in _package_files():
        if not path.endswith(".md"):
            continue
        with open(path, encoding="utf-8") as handle:
            text = handle.read()
        check("no retired band wording in %s" % os.path.basename(path),
              M.find_stale(text) == [], M.find_stale(text))


def test_build_root_found_without_a_hardcoded_path():
    root = M.build_root()
    check("build root resolves to the directory that owns core/",
          os.path.isdir(os.path.join(root, "core", "spoken_share_card_docs")),
          root)
    check("build root carries no operator home prefix in the module",
          _HOME_PREFIX not in open(
              os.path.join(HERE, "share_card_docs.py"), encoding="utf-8").read())


TESTS = (
    test_constants,
    test_card_line_states_target,
    test_docs_states_target,
    test_reference_note_present,
    test_negative_control_stale_text_is_refused,
    test_negative_control_gutted_wording_is_reported,
    test_positive_control_clean_text_passes,
    test_reader_type_guards,
    test_package_hygiene,
    test_unit_docs_carry_no_retired_band_wording,
    test_build_root_found_without_a_hardcoded_path,
)

def main():
    for test in TESTS:
        test()
    print("\n%d checks failed, %d tests run" % (len(FAILS), len(TESTS)))
    return 1 if FAILS else 0

if __name__ == "__main__":
    sys.exit(main())

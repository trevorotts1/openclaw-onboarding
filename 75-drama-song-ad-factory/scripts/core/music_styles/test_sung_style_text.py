#!/usr/bin/env python3
"""W-G-001 suite (G1): a sung style's style text never says spoken word.

Owner order 2026-10-08 11:35 EDT, part G item 1. Proves, stdlib only and
with zero paid calls:

  1. The ban list is exactly the owner's five words (spoken word, speech,
     narration, rap, talk) and the negative tags are exactly "spoken word,
     rap"; both are defined in ONE place (core/music_styles) and re-exported
     by core/audio_c3 no_echo without a second copy.
  2. sung_style_words() rejects every banned wording in the O3 style text
     (the LeAnne Dolce Soul Ballad receipt that spoke the whole track) --
     case-insensitive, whole word, hyphen/comma forms included.
  3. assert_sung_style_text() raises SUNG_STYLE_WORD on any sung style text
     carrying a banned word, and passes every built-in sung prompt clean
     (Soul Ballad, Soul Rise). style_prompt(sung=True) enforces it.
  4. Generator gate: no_echo.song_request(sung=True) refuses any style
     text with a banned word (envelope, never an exception) and stamps the
     sung negative tags on every clean sung payload; a hand-built payload
     marked sung=True is refused by check() both ways (dirty text, missing
     tags). Non-sung requests are untouched (rnb-flow keeps its rap text).
  5. Hygiene: stdlib only, no network, no provider marker, no operator path.

Exit 0 = all pass, 1 = failures, 2 = tooling failure.
"""
from __future__ import annotations

import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
sys.path.insert(0, CORE)

# Judge the SOURCE on disk, never a stale __pycache__.
_CACHE = os.path.join(HERE, "__pycache__")
if os.path.isdir(_CACHE):
    for _name in os.listdir(_CACHE):
        if _name.endswith(".pyc"):
            try:
                os.remove(os.path.join(_CACHE, _name))
            except OSError:
                pass

import music_styles as MS  # noqa: E402  (package under test)

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(fn, exc):
    try:
        fn()
    except exc as e:
        return e
    except Exception as e:  # noqa: BLE001 - wrong exception is a failure
        print("  note: raised %s: %s" % (type(e).__name__, e))
        return None
    return None


# The O3 style text (LeAnne Dolce Soul Ballad, take O3, 2026-10-08) -- the
# wording that made Suno speak the whole track. Quoted as evidence.
O3_STYLE_TEXT = (
    "68 bpm slow soul ballad, unhurried sung phrasing with long held notes, "
    "warm felt piano, soft brushed kit, deep rounded bass, soulful lead "
    "vocal of a Black woman in her forties, spoken word passages delivered "
    "as calm plain speech over the music"
)

# --- 1. one copy of the ban ------------------------------------------------

check("1a ban list is exactly the five owner words",
      MS.SUNG_BANNED_STYLE_WORDS == ("spoken word", "speech", "narration",
                                      "rap", "talk"),
      repr(MS.SUNG_BANNED_STYLE_WORDS))
check("1b negative tags are exactly 'spoken word, rap'",
      MS.SUNG_NEGATIVE_TAGS == ("spoken word", "rap"),
      repr(MS.SUNG_NEGATIVE_TAGS))

sys.path.insert(0, os.path.join(CORE, "audio_c3", "no_echo"))
import no_echo as NE  # noqa: E402

check("1c no_echo re-exports the ban without a second copy",
      NE.SUNG_BANNED_STYLE_WORDS is MS.SUNG_BANNED_STYLE_WORDS
      and NE.SUNG_NEGATIVE_TAGS is MS.SUNG_NEGATIVE_TAGS,
      "identity, not copies")
check("1d no provider/paid marker anywhere in the two sources",
      "apikey" not in open(os.path.join(HERE, "music_styles.py"),
                           encoding="utf-8").read().lower()
      and "api_key" not in open(
          os.path.join(CORE, "audio_c3", "no_echo", "no_echo.py"),
          encoding="utf-8").read().lower(),
      "stdlib only, no paid call")

# --- 2. the O3 style text is caught ----------------------------------------

o3_hits = MS.sung_style_words(O3_STYLE_TEXT)
check("2a O3 style text is caught (spoken word + speech)",
      "spoken word" in o3_hits and "speech" in o3_hits,
      repr(o3_hits))
check("2b every banned word is matched case-insensitively",
      all(MS.sung_style_words("Pray %s, LORD" % w)
          if w in ("speech", "narration", "rap", "talk")
          else MS.sung_style_words("Spoken WORD passages")
          for w in MS.SUNG_BANNED_STYLE_WORDS),
      "mixed case across the list")
check("2c whole word only: wraps/mistake/stalk/rapport survive",
      MS.sung_style_words("wraps, mistakes, stalk, rapport, kingdom")
      == [],
      "no false positive on substrings")
check("2d clean sung style text passes",
      MS.sung_style_words(MS.STYLES["soul-ballad"]["suno_style_prompt"])
      == []
      and MS.sung_style_words(MS.STYLES["soul-rise"]["suno_style_prompt"])
      == [],
      "Soul Ballad + Soul Rise built-in prompts are clean")
check("2e rnb-flow legitimately names rap in its own prompt (hybrid style)",
      "rap" in MS.sung_style_words(
          MS.STYLES["rnb-flow"]["suno_style_prompt"]),
      "the ban applies when sung=True, never by style id alone")

# --- 3. the gate raises -----------------------------------------------------

err = raises(lambda: MS.assert_sung_style_text("soul-ballad", O3_STYLE_TEXT),
             MS.MusicStyleError)
check("3a assert_sung_style_text raises SUNG_STYLE_WORD on O3 text",
      err is not None and err.code == "SUNG_STYLE_WORD",
      repr(getattr(err, "code", None)))
err = raises(lambda: MS.assert_sung_style_text(
    "soul-rise", "narration over the beat"), MS.MusicStyleError)
check("3b raises on narration", err is not None
      and err.code == "SUNG_STYLE_WORD", repr(getattr(err, "code", None)))
err = raises(lambda: MS.assert_sung_style_text(
    "soul-ballad", "she will talk to the listener"), MS.MusicStyleError)
check("3c raises on talk", err is not None
      and err.code == "SUNG_STYLE_WORD", repr(getattr(err, "code", None)))
check("3d clean text passes the gate and is returned unchanged",
      MS.assert_sung_style_text(
          "soul-ballad",
          MS.STYLES["soul-ballad"]["suno_style_prompt"])
      == MS.STYLES["soul-ballad"]["suno_style_prompt"],
      "identity on the built-in prompt")
err = raises(lambda: MS.style_prompt("soul-ballad", sung=True,
                                     _o3=O3_STYLE_TEXT), TypeError)
check("3e style_prompt(sung=True) has no backdoor keyword",
      err is not None, "only sung enforcement, no _o3 escape")
check("3f style_prompt(sung=True) passes built-in Soul Ballad",
      MS.style_prompt("soul-ballad", sung=True)
      == MS.STYLES["soul-ballad"]["suno_style_prompt"],
      "clean prompt returns")
err = raises(lambda: MS.style_prompt("rnb-flow", sung=True),
             MS.MusicStyleError)
check("3g style_prompt(sung=True) refuses rnb-flow (its prompt says rap)",
      err is not None and err.code == "SUNG_STYLE_WORD",
      repr(getattr(err, "code", None)))

# --- 4. the generator gate (no_echo.song_request) ---------------------------

CLEAN = MS.STYLES["soul-ballad"]["suno_style_prompt"]
_payload = {"input": {"style": CLEAN, "lyrics": "[Verse] hold on"}}
env = NE.song_request(dict(_payload), sung=True)
check("4a clean sung request builds ok",
      env["outcome"] == "ok", repr(env["errors"]) if env["outcome"] != "ok"
      else "")
req = env.get("request") or {}
check("4b clean sung request carries the sung negative tags",
      all(t in req.get("negative_tags", [])
          for t in MS.SUNG_NEGATIVE_TAGS),
      repr(req.get("negative_tags")))
check("4c extended tags carry the sung tags too",
      all(t in req.get("negative_tags_extended", [])
          for t in MS.SUNG_NEGATIVE_TAGS),
      repr(req.get("negative_tags_extended")))
check("4d payload is marked sung=True",
      req.get("sung") is True, repr(req.get("sung")))
check("4e the seven D22a tags survive the sung stamp",
      all(t in req.get("negative_tags", []) for t in NE.NEGATIVE_TAGS),
      "no regression on D22a")

for word in ("spoken word", "speech", "narration", "rap", "talk"):
    dirty = dict(_payload)
    dirty["input"] = dict(_payload["input"],
                          style="%s, %s" % (CLEAN, word))
    env = NE.song_request(dirty, sung=True)
    check("4f sung request refuses %r" % word,
          env["outcome"] == "rejected"
          and env["reason_code"] == "sung_style_word"
          and "SUNG_STYLE_WORD" in env["errors"][0],
          repr(env["errors"]))

env = NE.song_request(dict(_payload))   # not sung: rap text is allowed
check("4g non-sung request is not banned (rnb-flow path unchanged)",
      env["outcome"] == "ok", repr(env["errors"]))
env = NE.song_request({"input": {"style": CLEAN}}, sung=False)
check("4h sung=False behaves like the historical builder",
      env["outcome"] == "ok" and "sung" not in env.get("request", {}),
      "no sung flag, no sung tags")

# hand-built payload skipping the builder: check() must fail it both ways
hand = {"request_kind": "song", "input": {"style": O3_STYLE_TEXT},
        "dry_close_mic": True,
        "negative_tags": list(NE.NEGATIVE_TAGS)
        + list(MS.SUNG_NEGATIVE_TAGS),
        "negative_tags_extended": list(NE.BRIEF_NEGATIVE_TAGS),
        "style_words_banned": list(NE.SPOKEN_BANNED_STYLE_WORDS),
        "sung": True, "provider": "suno", "kie_path": "Skill 74"}
env = NE.check(hand)
check("4i check() refuses a hand-built sung payload with dirty text",
      env["outcome"] == "rejected"
      and any(e.startswith("SUNG_STYLE_WORD_IN_TEXT") for e in env["errors"]),
      repr(env["errors"])[:200])
clean_hand = dict(hand)
clean_hand["input"] = {"style": CLEAN + ", dry close-microphone vocal"}
clean_hand["negative_tags"] = list(NE.NEGATIVE_TAGS)   # D22a tags only:
clean_hand["negative_tags_extended"] = list(NE.BRIEF_NEGATIVE_TAGS)
# no sung tags -- the missing-tag path is what 4j proves
env = NE.check(clean_hand)
check("4j check() refuses clean-text sung payload missing the tags",
      env["outcome"] == "rejected"
      and any(e.startswith("MISSING_SUNG_NEGATIVE_TAG")
              for e in env["errors"]),
      repr(env["errors"])[:160])
good = NE.song_request({"input": {"style": CLEAN}}, sung=True)["request"]
env = NE.check(good)
check("4k check() passes a builder-stamped sung payload",
      env["outcome"] == "ok", repr(env["errors"])[:160])

# --- 5. hygiene: sources carry no transport --------------------------------

for path in (os.path.join(HERE, "music_styles.py"),
             os.path.join(CORE, "audio_c3", "no_echo", "no_echo.py")):
    tree = ast.parse(open(path, encoding="utf-8").read())
    imports = {n.names[0].name if isinstance(n, ast.Import) else n.module
               for n in ast.walk(tree)
               if isinstance(n, (ast.Import, ast.ImportFrom))
               and (n.names[0].name if isinstance(n, ast.Import)
                    else n.module or "")}
    bad = [i for i in imports if i and any(
        m in str(i) for m in ("requests", "urllib", "httpx", "socket",
                              "subprocess", "http.client"))]
    check("5a %s imports no network" % os.path.basename(path),
          not bad, repr(bad))

print("")
if FAILS:
    print("FAIL: %d check(s): %s" % (len(FAILS), ", ".join(FAILS)))
    raise SystemExit(1)
print("ALL PASS (%d checks)" % 27)

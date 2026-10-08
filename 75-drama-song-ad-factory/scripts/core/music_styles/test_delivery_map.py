#!/usr/bin/env python3
"""W-G-001 suite, AMENDED (G1): the delivery map is in, the negative-tag ban is out.

Owner order 2026-10-08 11:50 EDT, part G amended by the Opus audio review
(review item G6; TREVOR-ORDER-1150-partG-amend.md CORRECTION). Proves,
stdlib only and with zero paid calls:

  1. One copy: the delivery-map clauses and the two contradicting tag words
     live in core/music_styles and are re-exported by core/audio_c3 no_echo
     by identity, never a second copy. The reversed API (the 11:35
     spoken-word style-text ban, SUNG_BANNED_STYLE_WORDS, SUNG_NEGATIVE_TAGS)
     is gone from both modules.
  2. DELIVERY MAP IN: every default style prompt (Soul Ballad, R&B Flow,
     Soul Rise) ends with the delivery-map sentence naming SPEAKS and SINGS
     -- RAPS joins them for R&B Flow and for any sheet with rap blocks. The
     map is built from the sheet's own tags when a sheet is given, and
     style_prompt() still raises only on an unknown style id.
  3. THE BAN IS OUT: a style text carrying spoken-word wording is never
     refused (the O3 text passes), and a stamped payload never gains
     "spoken word" or "rap" as negative tags.
  4. THE ONE REFUSAL: a payload whose negative tags ban "spoken word" or
     "rap" while its lyric sheet carries spoken or rap blocks is refused by
     stamp() (envelope) and by check() -- with the whole-word controls that
     must NOT be refused beside it.
  5. Generator gate: song_request stamps the map on every style surface of
     a delivery-tagged sheet, check() passes its own output and refuses a
     hand-built payload missing the map, and a sheet that names no
     delivery stamps exactly as before.
  6. Hygiene: stdlib only, no network, no provider/paid marker.

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
COUNT = [0]


def check(name, cond, detail=""):
    COUNT[0] += 1
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
# wording the 11:35 order banned. The amendment keeps it legal.
O3_STYLE_TEXT = (
    "68 bpm slow soul ballad, unhurried sung phrasing with long held notes, "
    "warm felt piano, soft brushed kit, deep rounded bass, soulful lead "
    "vocal of a Black woman in her forties, spoken word passages delivered "
    "as calm plain speech over the music"
)

# A sheet shaped like the requests that actually sang: spoken block, sung
# block, and a rap block for the R&B Flow path.
SHEET = (
    "[Spoken - lead, plain natural speech over the music]\n"
    "Calm line over the music.\n"
    "[Sung - lead, long held notes]\n"
    "Who is holding me?\n"
    "[Rap - lead, confident metered flow]\n"
    "One check, one shot.\n"
)
SPOKEN_SUNG_SHEET = (
    "[Spoken - lead, plain natural speech over the music]\n"
    "Calm line.\n"
    "[Sung - lead, long held notes]\n"
    "Wake up happy sis.\n"
)
NO_DELIVERY_SHEET = "la la la"           # no [Tag] at all: G2 owns this
TRAP_SHEET = "[Trap beat - instrumental riff]\n"

sys.path.insert(0, os.path.join(CORE, "audio_c3", "no_echo"))
import no_echo as NE  # noqa: E402

# --- 1. one copy, and the reversed API is gone -----------------------------

check("1a the three delivery-map clauses are the map's single copy",
      len(MS.DELIVERY_MAP_CLAUSES) == 3
      and [c for _n, c in MS.DELIVERY_MAP_CLAUSES][0].startswith("SPEAKS")
      and "RAPS" in MS.DELIVERY_MAP_CLAUSES[1][1]
      and "SINGS" in MS.DELIVERY_MAP_CLAUSES[2][1],
      repr(MS.DELIVERY_MAP_CLAUSES))
check("1b verbs are derived from the clauses, not a second list",
      MS.DELIVERY_MAP_VERBS == {"spoken": "SPEAKS", "rap": "RAPS",
                                "sung": "SINGS"},
      repr(MS.DELIVERY_MAP_VERBS))
check("1c no_echo re-exports the contradicting tags without a second copy",
      NE.CONTRADICTING_NEGATIVE_TAGS is MS.CONTRADICTING_NEGATIVE_TAGS
      and MS.CONTRADICTING_NEGATIVE_TAGS == ("spoken word", "rap"),
      repr(getattr(NE, "CONTRADICTING_NEGATIVE_TAGS", None)))
check("1d the 11:35 ban API is gone from music_styles",
      not hasattr(MS, "SUNG_BANNED_STYLE_WORDS")
      and not hasattr(MS, "SUNG_NEGATIVE_TAGS")
      and not hasattr(MS, "sung_style_words")
      and not hasattr(MS, "assert_sung_style_text"),
      "reversed by owner order 1150")
check("1e the 11:35 ban API is gone from no_echo",
      not hasattr(NE, "SUNG_BANNED_STYLE_WORDS")
      and not hasattr(NE, "SUNG_NEGATIVE_TAGS"),
      "reversed by owner order 1150")
check("1f no SUNG_NEGATIVE_TAGS symbol survives in either source",
      all("SUNG_NEGATIVE_TAGS" not in open(
              os.path.join(CORE, "music_styles", name), encoding="utf-8"
          ).read()
          for name in ("music_styles.py", "__init__.py"))
      and "SUNG_NEGATIVE_TAGS" not in open(
          os.path.join(CORE, "audio_c3", "no_echo", "no_echo.py"),
          encoding="utf-8").read(),
      "grep of the two sources")
check("1g no provider/paid marker anywhere in the two sources",
      "apikey" not in open(os.path.join(HERE, "music_styles.py"),
                           encoding="utf-8").read().lower()
      and "api_key" not in open(
          os.path.join(CORE, "audio_c3", "no_echo", "no_echo.py"),
          encoding="utf-8").read().lower(),
      "stdlib only, no paid call")

# --- 2. the delivery map is IN every default style prompt -------------------

for sid in MS.style_ids():
    prompt = MS.style_prompt(sid)
    check("2a %s default prompt carries the delivery map" % sid,
          "The lead SPEAKS the lines tagged Spoken" in prompt
          and "SINGS the lines tagged Sung" in prompt
          and prompt.rstrip().endswith("."),
          prompt[-120:])
    check("2b %s prompt carries exactly one map sentence" % sid,
          prompt.count("The lead ") == 1,
          repr(prompt.count("The lead ")))
    check("2c %s prompt still starts from the D18 style text" % sid,
          prompt.startswith(MS.STYLES[sid]["suno_style_prompt"].rstrip(".,")),
          prompt[:60])

check("2d R&B Flow also names RAPS (its sheet carries rap blocks)",
      "RAPS the lines tagged Rap" in MS.style_prompt("rnb-flow"),
      MS.style_prompt("rnb-flow")[-160:])
check("2e Soul Ballad does not claim rap it has no blocks for",
      "RAPS" not in MS.style_prompt("soul-ballad"),
      MS.style_prompt("soul-ballad")[-160:])
check("2f style_prompt with a sheet maps FROM the sheet",
      "RAPS the lines tagged Rap" in MS.style_prompt(
          "soul-ballad", sheet_text=SHEET)
      and MS.style_prompt("soul-ballad", sheet_text=SHEET).count(
          "The lead ") == 1,
      MS.style_prompt("soul-ballad", sheet_text=SHEET)[-160:])
check("2g a sheet that names no delivery falls back to the style map",
      "SINGS the lines tagged Sung" in MS.style_prompt(
          "soul-ballad", sheet_text=NO_DELIVERY_SHEET),
      MS.style_prompt("soul-ballad", sheet_text=NO_DELIVERY_SHEET)[-120:])
check("2h style_prompt raises only on an unknown style id (V2B-AUDIO-U5)",
      raises(lambda: MS.style_prompt("polka"), MS.MusicStyleError) is not None
      and raises(lambda: MS.style_prompt("polka"),
                 MS.MusicStyleError).code == "UNKNOWN_STYLE",
      "historical contract kept")
check("2i the reversed order no longer refuses rnb-flow (it says rap)",
      "RAPS" in MS.style_prompt("rnb-flow", sung=True)
      and raises(lambda: MS.style_prompt("rnb-flow", sung=True),
                 MS.MusicStyleError) is None,
      "sung= is accepted and ignored: 11:35 ban reversed")
check("2j delivery_map() builds the sheet sentence verbatim",
      MS.delivery_map(SHEET) == "The lead %s."
      % ", ".join(clause for _n, clause in MS.DELIVERY_MAP_CLAUSES),
      MS.delivery_map(SHEET))
check("2k delivery_map() refuses a sheet that names no delivery",
      (raises(lambda: MS.delivery_map(NO_DELIVERY_SHEET),
              MS.MusicStyleError) or None) is not None
      and raises(lambda: MS.delivery_map(NO_DELIVERY_SHEET),
                 MS.MusicStyleError).code == "EMPTY_SHEET_DELIVERIES",
      "the G2 tag grammar owns that sheet")
check("2l sheet_deliveries classifies the three deliveries",
      MS.sheet_deliveries(SHEET) == {"spoken", "rap", "sung"}
      and MS.sheet_deliveries(SPOKEN_SUNG_SHEET) == {"spoken", "sung"}
      and MS.sheet_deliveries(NO_DELIVERY_SHEET) == set(),
      repr(MS.sheet_deliveries(SHEET)))
check("2m 'trap beat' is not read as a rap block (whole word)",
      "rap" not in MS.sheet_deliveries(TRAP_SHEET),
      repr(MS.sheet_deliveries(TRAP_SHEET)))
check("2n a tag naming no delivery counts as nothing",
      MS.sheet_deliveries("[Bridge] stripped back") == set(),
      repr(MS.sheet_deliveries("[Bridge] stripped back")))

# --- 3. the ban is OUT: spoken-word wording is never refused ----------------

check("3a the O3 spoken-word style text is not refused by any new gate",
      MS.assert_no_contradiction(NE.NEGATIVE_TAGS, SPOKEN_SUNG_SHEET)
      == list(NE.NEGATIVE_TAGS)
      and MS.missing_delivery_verbs(O3_STYLE_TEXT, {"spoken", "sung"})
      != [],   # no map in the bare O3 text -- the map is what must be added
      "the text itself carries no gate")
check("3b a mapped style text carrying spoken-word wording passes",
      MS.assert_delivery_map(
          "o3", O3_STYLE_TEXT + " " + MS.delivery_map(SPOKEN_SUNG_SHEET),
          SPOKEN_SUNG_SHEET) is not None,
      "map present, wording irrelevant")
check("3c stamped payload gains no 'spoken word, rap' negative tags",
      NE.song_request(
          {"input": {"style": MS.style_prompt("soul-ballad"),
                     "lyrics": SPOKEN_SUNG_SHEET}},
          sung=True)["request"]["negative_tags"] == list(NE.NEGATIVE_TAGS)
      and NE.song_request(
          {"input": {"style": MS.style_prompt("soul-ballad"),
                     "lyrics": SPOKEN_SUNG_SHEET}},
          sung=True)["request"]["negative_tags_extended"] == list(
              NE.BRIEF_NEGATIVE_TAGS),
      "the 11:35 tags are never injected")
check("3d D22a's own seven tags are never reported as a contradiction",
      raises(lambda: MS.assert_no_contradiction(
          list(NE.NEGATIVE_TAGS), SHEET), MS.MusicStyleError) is None,
      "control: the default tags ban no delivery")

# --- 4. the one refusal: tags that contradict the sheet ---------------------

def hand_payload(lyrics, neg_tags, style_text=None):
    """A complete hand-built song payload check() can judge.

    The style text carries the dry rule so the ONLY error a case can raise
    is the one the case is about.
    """
    return {
        "request_kind": "song",
        "provider": "suno",
        "kie_path": NE.KIE_PATH,
        "input": {
            "style": (style_text or MS.style_prompt("soul-ballad"))
            + ", " + NE.DRY_RULE,
            "lyrics": lyrics,
        },
        "dry_close_mic": True,
        "negative_tags": list(neg_tags),
        "negative_tags_extended": list(NE.BRIEF_NEGATIVE_TAGS),
        "style_words_banned": list(NE.SPOKEN_BANNED_STYLE_WORDS),
    }


def with_tag(tags, word):
    return list(tags) + [word]


env = NE.check(hand_payload(SPOKEN_SUNG_SHEET,
                            with_tag(NE.NEGATIVE_TAGS, "spoken word")))
check("4a check() refuses 'spoken word' beside [Spoken ...] blocks",
      env["outcome"] == "rejected"
      and env["reason_code"] == "negative-tag-contradiction"
      and any(e.startswith("NEGATIVE_TAG_CONTRADICTION")
              for e in env["errors"]),
      repr(env["errors"])[:200])

env = NE.check(hand_payload("[Rap - lead, confident metered flow]\n"
                            "One check, one shot.\n",
                            with_tag(NE.NEGATIVE_TAGS, "rap")))
check("4b check() refuses 'rap' beside [Rap ...] blocks",
      env["outcome"] == "rejected"
      and env["reason_code"] == "negative-tag-contradiction"
      and any(e.startswith("NEGATIVE_TAG_CONTRADICTION")
              for e in env["errors"]),
      repr(env["errors"])[:200])

env = NE.check(hand_payload(SPOKEN_SUNG_SHEET, NE.NEGATIVE_TAGS))
check("4c control: the same sheet with D22a tags only is accepted",
      env["outcome"] == "ok", repr(env["errors"])[:200])
check("4c2 the control payload carries no other defect either",
      env["outcome"] == "ok" and env["errors"] == [],
      repr(env["errors"])[:200])

env = NE.check(hand_payload("[Sung - lead, long held notes]\n"
                            "Wake up happy sis.\n",
                            with_tag(NE.NEGATIVE_TAGS, "spoken word")))
check("4d control: 'spoken word' beside a sheet with NO spoken block passes",
      env["outcome"] == "ok" and env["errors"] == [],
      repr(env["errors"])[:200])

env = NE.check(hand_payload(TRAP_SHEET,
                            with_tag(NE.NEGATIVE_TAGS, "rap")))
check("4e control: 'rap' beside a [Trap beat] block passes (whole word)",
      env["outcome"] == "ok" and env["errors"] == [],
      repr(env["errors"])[:200])

env = NE.song_request(
    {"input": {"style": "warm soul ballad", "lyrics": SPOKEN_SUNG_SHEET},
     "negative_tags": with_tag(NE.NEGATIVE_TAGS, "spoken word")})
check("4f song_request (envelope) refuses the contradicting payload",
      env["outcome"] == "rejected"
      # the envelope derives reason_code from the exception code, as it
      # already does for WRONG_PROVIDER -> wrong_provider
      and env["reason_code"] == "negative_tag_contradiction"
      and any(e.startswith("NEGATIVE_TAG_CONTRADICTION")
              for e in env["errors"])
      and env["request"] is None,
      repr(env["errors"])[:200])

env = NE.song_request(
    {"input": {"style": "warm soul ballad", "lyrics": SPOKEN_SUNG_SHEET},
     "negative_tags": with_tag(NE.NEGATIVE_TAGS, "spoken word")},
    sung=True)
check("4g the refusal holds with sung=True too",
      env["outcome"] == "rejected"
      and env["reason_code"] == "negative_tag_contradiction",
      repr(env["errors"])[:200])

# --- 5. generator gate: the map lands on the payload ------------------------

clean = {"input": {"style": MS.style_prompt("soul-ballad"),
                   "lyrics": SPOKEN_SUNG_SHEET}}
before = dict(clean["input"])
env = NE.song_request(dict(clean), sung=True)
check("5a a sung request on a delivery-tagged sheet builds ok",
      env["outcome"] == "ok", repr(env["errors"]))
req = env.get("request") or {}
style_out = req.get("input", {}).get("style", "")
check("5b the stamped style text ends with the map built from the sheet",
      "The lead SPEAKS the lines tagged Spoken" in style_out
      and "SINGS the lines tagged Sung" in style_out
      and style_out.count("The lead ") == 1,
      style_out[-160:])
check("5c the stamped payload carries no contradicting tags",
      all(t not in req.get("negative_tags", [])
          for t in ("spoken word", "rap"))
      and req.get("negative_tags") == list(NE.NEGATIVE_TAGS),
      repr(req.get("negative_tags")))
check("5d check() passes the payload this stamp just built",
      NE.check(req)["outcome"] == "ok", repr(NE.check(req)["errors"])[:200])
check("5e the caller's dict is never mutated",
      clean["input"] == before and "negative_tags" not in clean,
      repr(clean))
check("5f the payload is marked sung when sung=True",
      req.get("sung") is True, repr(req.get("sung")))

env = NE.song_request({"input": {"style": "warm soul ballad",
                                 "lyrics": SPOKEN_SUNG_SHEET}})
check("5g a non-sung song payload gets the map too (every song style text)",
      env["outcome"] == "ok"
      and "The lead " in env["request"]["input"]["style"]
      and NE.check(env["request"])["outcome"] == "ok",
      repr(env["errors"])[:200])

bare = hand_payload(
    SPOKEN_SUNG_SHEET, NE.NEGATIVE_TAGS,
    style_text="warm soul ballad")   # dry rule added, map still missing
env = NE.check(bare)
check("5h check() refuses a hand-built payload missing the map",
      env["outcome"] == "rejected"
      and env["reason_code"] == "delivery-map-missing"
      and any(e.startswith("MISSING_DELIVERY_MAP") for e in env["errors"])
      and not any(e.startswith("MISSING_DRY_RULE") for e in env["errors"]),
      repr(env["errors"])[:200])

env = NE.song_request({"input": {"style": "warm soul ballad",
                                 "lyrics": NO_DELIVERY_SHEET}})
check("5i a sheet that names no delivery stamps exactly as before",
      env["outcome"] == "ok"
      and env["request"]["input"]["style"]
      == NE._with_dry("warm soul ballad")
      and "The lead " not in env["request"]["input"]["style"],
      repr(env["request"]["input"]["style"]))

env = NE.check(NE.song_request({})["request"])
check("5j the empty payload still passes the historical checks",
      env["outcome"] == "ok", repr(env["errors"])[:200])

# --- 6. hygiene: sources carry no transport ---------------------------------

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
    check("6a %s imports no network" % os.path.basename(path),
          not bad, repr(bad))

TOTAL = COUNT[0]
print("")
if FAILS:
    print("FAIL: %d of %d check(s): %s" % (len(FAILS), TOTAL,
                                           ", ".join(FAILS)))
    raise SystemExit(1)
print("ALL PASS (%d checks)" % TOTAL)

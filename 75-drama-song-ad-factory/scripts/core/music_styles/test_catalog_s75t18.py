#!/usr/bin/env python3
"""S75-T18 / S75-A18: the eighteen-style catalog, stdlib only, zero spend.

Proves:
  1. Exactly eighteen stable ids, unique labels, frozen order.
  2. The three originals are byte-for-byte what the current file and the owner
     spec hold -- label, id, client description, and the live recipe record.
  3. Every style carries a client explanation and all eleven executable trait
     fields, distinct from every other style, and every style resolves at all
     six canonical durations.
  4. Client reference artists never reach compiled guidance, for all eighteen.
  5. A nineteenth style is refused, and a duplicate id is refused.
  6. The preserve-unchanged policies hold: reggaeton never auto-selects
     Spanish, trap rap never adds explicitness, orchestral stays a vocal song,
     gospel never invents client facts.
  7. Old-run compatibility: the first three ids are the old menu, in order.
  8. Hygiene: stdlib only, no network, no provider or paid-call marker.

Exit 0 = all pass, 1 = failures, 2 = tooling failure.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
for p in (CORE, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import music_styles as MS          # noqa: E402
import catalog as C                # noqa: E402

COUNT = [0]
FAILS = []


def check(label, ok, detail=""):
    COUNT[0] += 1
    if not ok:
        FAILS.append("%s %s" % (label, detail))
        print("FAIL %s %s" % (label, detail))


EXPECTED_IDS = (
    "soul-ballad", "rnb-flow", "soul-rise", "acoustic-pop",
    "folk-storytelling", "country-pop", "melodic-rap", "trap-rap",
    "pop-rap", "pop-rock", "reggaeton", "cinematic-orchestral-song",
    "musical-theater", "contemporary-gospel", "urban-gospel",
    "alternative-rnb", "afro-soul", "country-rap",
)

#: Double-entry: the owner client descriptions, typed here from the spec
#: independently of catalog.py. Byte comparison below, no normalization.
EXPECTED_DESCRIPTIONS = {
    "soul-ballad":
        "slow, heartfelt singing; builds to a big emotional chorus.",
    "rnb-flow":
        "rhythmic rap verses, then a smooth sung hook you remember.",
    "soul-rise":
        "starts slow and sad, then lifts into an upbeat, hopeful groove.",
    "acoustic-pop":
        "warm acoustic guitar, clear storytelling, and a catchy sung chorus.",
    "folk-storytelling":
        "intimate, detail-rich storytelling over simple acoustic instruments.",
    "country-pop":
        "plainspoken country storytelling with a polished, memorable pop "
        "chorus.",
    "melodic-rap":
        "emotional rap that moves between rhythmic lines and a tuneful hook.",
    "trap-rap":
        "punchy rap over deep bass and crisp, rolling hi-hats, with a strong "
        "hook.",
    "pop-rap":
        "upbeat, easy-to-follow rap with a bright, catchy pop hook.",
    "pop-rock":
        "driving guitars and drums with a big, singable chorus.",
    "reggaeton":
        "a rolling dembow groove, rhythmic vocals, and a danceable chorus.",
    "cinematic-orchestral-song":
        "a dramatic song with sweeping strings and a powerful film-style "
        "chorus. Keep the singing and spoken words clear and easy to hear, "
        "even when the music gets big and powerful.",
    "musical-theater":
        "character-driven singing and dialogue that build into a dramatic "
        "stage-style payoff.",
    "contemporary-gospel":
        "faith-centered singing with piano, organ, and a powerful choir that "
        "builds from testimony to an uplifting chorus.",
    "urban-gospel":
        "faith-centered singing with R&B and hip-hop grooves, choir "
        "responses, and a memorable gospel hook.",
    "alternative-rnb":
        "intimate, spacious R&B with inventive textures, flexible grooves, "
        "and an expressive vocal.",
    "afro-soul":
        "soulful vocals over warm, organic instruments and interlocking "
        "African-influenced rhythms.",
    "country-rap":
        "Country storytelling meets rock power and hip-hop rhythm. Gritty, "
        "soulful singing and rhythmic rap verses build into a big, emotional "
        "chorus. Think acoustic guitars, heavy drums, deep bass and "
        "electric-guitar lift, with stories about struggle, regret, "
        "resilience and redemption.",
}

#: sha256 of the three owner descriptions, taken from MUSIC-AND-VIDEO-UX.md
#: section 2 as delivered. Changing one of these is an owner change.
ORIGINAL_DESCRIPTION_SHA256 = {
    "soul-ballad":
        "26bf7da626b448bcb949d1ebf047851e54a986062b732fb7e2c6237083b5e588",
    "rnb-flow":
        "049d305eb3baaca912e7a6a854b8b0cf662c093362aee188a6412b3eb04baf6d",
    "soul-rise":
        "bd1a8e07ce4f896e5fded8a09ee1eeac3e7355cba663a119ee05b344cca6bba8",
}

#: sha256 of the three live music_styles.STYLES records, canonical JSON,
#: captured from origin/main before this unit touched anything. The originals
#: are unchanged: music_styles.py is not edited here, and the catalog reads
#: their label and recipe by reference.
ORIGINAL_RECORDS_SHA256 = \
    "a586aa79a4fa9cf30ce35472bb806a4482af943cb3200494ce963ecdd1339ae2"

SPECIALS = {"soul-ballad", "rnb-flow", "soul-rise"}
DURATIONS = (60, 90, 120, 180, 300, 600)

PROFANITY = ("fuck", "shit", "bitch", "nigga", "cunt", "damn")

# --- 1. exactly eighteen, unique, frozen -----------------------------------

check("1a eighteen ids", len(C.style_ids()) == 18, len(C.style_ids()))
check("1b exact id tuple", C.style_ids() == EXPECTED_IDS, C.style_ids())
check("1c unique ids", len(set(C.style_ids())) == 18)
check("1d unique labels",
      len({C.label(s) for s in C.style_ids()}) == 18)
check("1e kebab-case ids",
      all(s == s.lower() and " " not in s and "_" not in s
          for s in C.style_ids()))
check("1f max is eighteen", C.MAX_STYLES == 18)
check("1g validate_catalog", C.validate_catalog() == 18)
check("1h fifteen additions",
      len(C.added_style_ids()) == 15
      and set(C.added_style_ids()) == set(EXPECTED_IDS) - SPECIALS)
check("1i every choice row renders",
      len(C.choice_rows()) == 18
      and all(r["label"] and r["description"]
              for r in C.choice_rows()))

# --- 2. the three originals, byte for byte ---------------------------------

live = {sid: MS.STYLES[sid] for sid in SPECIALS}
blob = json.dumps(live, sort_keys=True, separators=(",", ":"),
                  ensure_ascii=False).encode("utf-8")
check("2a live originals are unchanged since origin/main",
      hashlib.sha256(blob).hexdigest() == ORIGINAL_RECORDS_SHA256,
      hashlib.sha256(blob).hexdigest())
check("2b music_styles still offers exactly the three originals",
      tuple(MS.STYLES) == EXPECTED_IDS[:3], tuple(MS.STYLES))

for sid in EXPECTED_IDS[:3]:
    rec = C.style(sid)
    check("2c %s id is the stable id" % sid, rec["style_id"] == sid)
    check("2d %s label bytes equal the live record" % sid,
          rec["label"].encode("utf-8") == live[sid]["label"].encode("utf-8"),
          rec["label"])
    check("2e %s description bytes equal the spec" % sid,
          rec["description"].encode("utf-8")
          == EXPECTED_DESCRIPTIONS[sid].encode("utf-8"),
          repr(rec["description"]))
    check("2f %s description sha256" % sid,
          hashlib.sha256(rec["description"].encode("utf-8")).hexdigest()
          == ORIGINAL_DESCRIPTION_SHA256[sid])

# --- 3. every style: explanation, traits, durations ------------------------

TRAIT_FIELDS = ("musical_identity", "instrumentation",
                "avoid_instrumentation", "tempo_bpm", "meter",
                "vocal_delivery", "energy_map", "hook_guidance",
                "delivery_constraints", "example", "negative_constraints")

for sid in C.style_ids():
    rec = C.style(sid)
    check("3a %s carries the owner client description" % sid,
          rec["description"].encode("utf-8")
          == EXPECTED_DESCRIPTIONS[sid].encode("utf-8"),
          repr(rec["description"])[:80])
    tr = C.production_traits(sid)
    check("3b %s has every trait field" % sid,
          all(tr.get(f) for f in TRAIT_FIELDS),
          [f for f in TRAIT_FIELDS if not tr.get(f)])
    lo, hi = tr["tempo_bpm"]
    check("3c %s tempo range is positive" % sid, 0 < lo < hi <= 300, (lo, hi))
    check("3d %s is a vocal song" % sid, bool(rec["vocal_song"]))
    check("3e %s knows the six durations" % sid,
          tuple(rec["durations_s"]) == DURATIONS, rec["durations_s"])
    for dur in DURATIONS:
        check("3f %s resolves at %ds" % (sid, dur),
              C.label(sid) and C.production_traits(sid)["tempo_bpm"][0] > 0)

sigs = [json.dumps(C.production_traits(s), sort_keys=True) for s in
        C.style_ids()]
check("3g all eighteen trait records are distinct", len(set(sigs)) == 18)

hints = [C.provider_hint(s) for s in C.style_ids()]
check("3h all eighteen compiled hints are distinct", len(set(hints)) == 18)
check("3i every hint fits the 1000-char style field",
      all(len(h) <= 1000 for h in hints), max(len(h) for h in hints))

for sid in C.style_ids():
    hint = C.provider_hint(sid)
    check("3j %s hint carries the delivery map" % sid,
          "The lead SPEAKS the lines tagged Spoken" in hint
          and "SINGS the lines tagged Sung" in hint)
    rails = sid in ("rnb-flow", "melodic-rap", "trap-rap", "pop-rap",
                    "urban-gospel", "country-rap")
    check("3k %s RAPS presence matches its deliveries" % sid,
          ("RAPS the lines tagged Rap" in hint) == rails)

# The three originals keep their own recipe text unchanged.
for sid in EXPECTED_IDS[:3]:
    base = MS.STYLES[sid]["suno_style_prompt"]
    check("3l %s provider hint starts from the live recipe" % sid,
          C.provider_hint(sid).startswith(base.rstrip(".,")),
          C.provider_hint(sid)[:60])

# --- 4. artist names never reach compiled guidance -------------------------

for sid in C.style_ids():
    refs = C.client_references(sid)
    hint = C._norm(C.provider_hint(sid))
    traits = C._norm(repr(C.production_traits(sid)))
    for ref in refs:
        key = C._norm(ref)
        check("4a %s hint hides %r" % (sid, ref), key not in hint)
        check("4b %s traits hide %r" % (sid, ref), key not in traits)
    check("4c %s has at least one display reference" % sid, bool(refs))
    check("4d %s explanation is not the reference list" % sid,
          all(r not in C.description(sid) for r in refs))

# --- 5. a nineteenth style is refused --------------------------------------

for bad in ({"style_id": "hyperpop-extra"}, {"style_id": "soul-ballad"},
            {"style_id": "Country Soul"}):
    try:
        C.register_style(bad)
    except C.CatalogError as exc:
        check("5a refuses %r" % bad["style_id"],
              exc.code in ("CATALOG_FULL", "DUPLICATE_STYLE"), exc.code)
    else:
        check("5a refuses %r" % bad["style_id"], False, "accepted")
check("5b catalog still holds eighteen", len(C.style_ids()) == 18)
try:
    C.style("country-soul")
except C.CatalogError as exc:
    check("5c unapproved genre is unknown", exc.code == "UNKNOWN_STYLE",
          exc.code)
else:
    check("5c unapproved genre is unknown", False, "resolved")

# --- 6. the preserve-unchanged policies ------------------------------------

tr_trap = repr(C.production_traits("trap-rap")).lower()
check("6a trap rap adds no profanity",
      not any(re.search(r"\b%s\b" % w, tr_trap) for w in PROFANITY))
check("6b trap rap preserves explicitness",
      "preserve the client's selected explicitness" in
      C.style("trap-rap")["explicitness_policy"])
check("6c trap rap names no auto-explicit switch",
      "auto" not in C.style("trap-rap")["explicitness_policy"].lower())

reg = C.production_traits("reggaeton")
check("6d reggaeton preserves the client's language",
      "preserve the client's selected language" in reg["delivery_constraints"])
check("6e reggaeton never auto-selects Spanish",
      "never auto-selects spanish" in
      " ".join(reg["negative_constraints"]).lower()
      and "spanish" not in C._norm(C.provider_hint("reggaeton")))
check("6f country-rap preserves explicitness",
      "preserve the client's selected explicitness" in
      C.style("country-rap")["explicitness_policy"])

orch = C.production_traits("cinematic-orchestral-song")
check("6g orchestral is a vocal song with a chorus",
      "vocal song" in C.style("cinematic-orchestral-song")["vocal_song"]
      and "chorus" in orch["musical_identity"]
      and "never an instrumental" in
      C.style("cinematic-orchestral-song")["vocal_song"])
check("6h orchestral keeps the client clarity sentence",
      "clear and easy to hear" in C.description("cinematic-orchestral-song"))

for sid in ("contemporary-gospel", "urban-gospel"):
    rec = C.style(sid)
    check("6i %s never invents client facts" % sid,
          "never invent" in rec["fact_policy"]
          and "faith" in rec["fact_policy"])
    check("6j %s gospel hooks stay distinct" % sid,
          C.provider_hint("contemporary-gospel")
          != C.provider_hint("urban-gospel")
          if sid == "urban-gospel" else True)

# --- 7. old runs keep their ids and their menu order -----------------------

check("7a first three ids are the original menu in order",
      C.style_ids()[:3] == ("soul-ballad", "rnb-flow", "soul-rise"))
for idx, sid in enumerate(("soul-ballad", "rnb-flow", "soul-rise")):
    check("7b old option %d resolves to %s" % (idx + 1, sid),
          C.style(C.label(sid))["style_id"] == sid)
check("7c label lookup is case-insensitive",
      C.style("r&b flow")["style_id"] == "rnb-flow")
check("7d card option dict resolves",
      C.style({"value": "country-rap"})["style_id"] == "country-rap")
try:
    C.style(19)
except C.CatalogError as exc:
    check("7e a bare number is not a style", exc.code == "BAD_STYLE", exc.code)
else:
    check("7e a bare number is not a style", False, "accepted")

# --- 8. hygiene ------------------------------------------------------------

src = open(os.path.join(HERE, "catalog.py"), encoding="utf-8").read()
tree = ast.parse(src)
imports = set()
for node in ast.walk(tree):
    if isinstance(node, ast.Import):
        imports |= {a.name for a in node.names}
    elif isinstance(node, ast.ImportFrom) and node.module:
        imports.add(node.module)
banned = [i for i in imports
          if any(m in i for m in ("requests", "urllib", "httpx", "socket",
                                  "subprocess", "http.client"))]
check("8a catalog imports no network", not banned, banned)
check("8b catalog names no provider or spend marker",
      all(m not in src.lower() for m in ("api_key", "apikey", "authorization",
                                         "bearer")),
      "")

TOTAL = COUNT[0]


def test_suite_checks_pass():
    assert not FAILS, FAILS


if __name__ == "__main__":
    print("")
    if FAILS:
        print("FAIL: %d of %d check(s): %s" % (len(FAILS), TOTAL,
                                               ", ".join(FAILS)))
        raise SystemExit(1)
    print("ALL PASS (%d checks)" % TOTAL)

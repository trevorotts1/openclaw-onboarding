"""test_brief_exemption_v2972.py — R2: the client's brief words are exempt.

v2.9.72 (unit DSF-R2): the first-person waiver now reads every field the
intake recorded as the CLIENT'S OWN ANSWER (offer, website, audience, action,
pain_or_transformation, claims, packet_lines, excerpt_lines, and the research
sub-avatar's three answers), and a line that CONTAINS a contiguous >=3-word
client run is the client's voice. Script-style stdlib test: run by file.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)
import lyric_writer as LW  # noqa: E402

LAYA = os.environ.get(
    "VTV_RUN",
    "/Users/blackceomacmini/scratch/laya-drama-diag/x/drama-song-runs/"
    "voyage-to-virtue")

checks, fails = [], []


def check(name, cond, detail=""):
    checks.append(name)
    if not cond:
        fails.append("%s: %s" % (name, detail))


def _laya():
    if not os.path.isdir(LAYA):
        return None
    try:
        with open(os.path.join(LAYA, "brief.json"), encoding="utf-8") as f:
            b = json.load(f)
        with open(os.path.join(LAYA, "creative", "lyrics.json"),
                  encoding="utf-8") as f:
            lyr = json.load(f)
        return b, lyr.get("lines")
    except (OSError, ValueError):
        return None

# --- 1. the source fields changed -------------------------------------------
brief = {
    "offer": "Voyage To Virtue: A Journey of Becoming",
    "website": "VoyageToVirtue.com/journeyofbecoming",
    "audience": ("Women 35-65 who have been the strong one for everyone else "
                 "for decades"),
    "action": "Click the book purchase link and buy your copy.",
    "sub_avatar": {
        "avatar": ("A woman 35 to 65 who has been the strong one for everyone "
                   "else for decades."),
        "emotional_wound": "Her own dreams went quiet.",
        "desired_transformation": "To stop being only the woman who gives.",
    },
}
runs = LW.client_word_runs(brief)
check("audience is a source",
      LW.client_verbatim(LW.exempt_tokens("the strong one for"), runs))
check("sub_avatar.avatar is a source",
      LW.client_verbatim(LW.exempt_tokens("strong one for everyone else"),
                         runs))
check("emotional_wound is a source",
      LW.client_verbatim(LW.exempt_tokens("own dreams went quiet"), runs))
check("desired_transformation is a source",
      LW.client_verbatim(LW.exempt_tokens("only the woman who gives"), runs))
check("action is a source",
      LW.client_verbatim(LW.exempt_tokens("click the book purchase link"),
                         runs))

# --- 2. the notes field is never a source ------------------------------------
nbrief = dict(brief)
nbrief["sub_avatar"] = dict(brief["sub_avatar"])
nbrief["sub_avatar"]["notes"] = ("Authored from the client's own audience "
                                 "statement; a model-written provenance remark "
                                 "with fresh wording in here.")
nruns = LW.client_word_runs(nbrief)
check("sub_avatar.notes is NOT a source",
      not LW.client_run_inside(LW.exempt_tokens("fresh wording in here"),
                               nruns))
check("notes-copied line still refuses",
      LW.validate_lyrics(
          [{"line_id": "v9",
            "text": "fresh wording in here now"}], nbrief
      )["reason_code"] == "line-not-first-person",
      "a line from the model-written notes field must refuse")

# --- 3. line CONTAINS a client run -> exempt --------------------------------
check("v2 line contains client run 'the strong one'",
      LW.client_run_inside(
          LW.exempt_tokens("what the strong one wants"), runs))
r = LW.validate_lyrics(
    [{"line_id": "v1", "text": "Nobody ever asks"},
     {"line_id": "v2", "text": "what the strong one wants"}], brief)
v2_first_person = [e.get("detail") for e in r.get("errors") or []
                   if e["error"] == "line-not-first-person"]
check("v2 passes with client run inside", "v2" not in v2_first_person,
      repr(v2_first_person))

# --- 4. a genuinely invented 3rd-person line still refuses -------------------
check("fully invented line refuses",
      LW.validate_lyrics(
          [{"line_id": "v3", "text": "Nobody ever asks"}], brief
      )["reason_code"] == "line-not-first-person")

# --- 5. abuse cases hold -----------------------------------------------------
# (a) model-persuasion wording with no client run
check('"You should buy this now" refuses (no client run >= 3)',
      LW.validate_lyrics(
          [{"line_id": "v4", "text": "You should buy this now"}], brief
      )["reason_code"] == "line-not-first-person")
# (b) two sentences still multi-idea
check('"I rise. I fall" still multi-idea',
      LW.validate_lyrics(
          [{"line_id": "v5", "text": "I rise. I fall"}], {}
      )["reason_code"] == "line-multi-idea")
# (c) a 2-word client fragment never exempts
check("2-word fragment refuses",
      LW.validate_lyrics(
          [{"line_id": "h1", "text": "strong one"}], brief
      )["reason_code"] == "line-not-first-person")
# (d) a stray 2-token client substring inside an invented line never exempts:
#     "her own family" — 'her own' is NOT 3 contiguous client tokens together
#     with an invented tail; runs must be contiguous.
thin = {"audience": "she held her own family up and carried every name"}
thin_runs = LW.client_word_runs(thin)
check("2 client tokens + invented tail refuse",
      not LW.client_run_inside(
          LW.exempt_tokens("her own dreams went silent in here"), thin_runs))
check("3 contiguous client tokens + invented tail exempt",
      LW.client_run_inside(
          LW.exempt_tokens("she held her own family up in silence"), thin_runs))
# (e) short lines under 3 tokens never exempt
check("1-token invented line refuses",
      LW.validate_lyrics(
          [{"line_id": "v6", "text": "Nobody"}], brief
      )["reason_code"] == "line-not-first-person")

# --- 6. CLIENT_RUN_MIN and apostrophe fold unchanged -------------------------
check("CLIENT_RUN_MIN stays 3", LW.CLIENT_RUN_MIN == 3,
      str(LW.CLIENT_RUN_MIN))
curly = dict(brief)
curly["audience"] = "she’s the strong one for everyone"
check("curly apostrophe fold still works",
      LW.client_run_inside(LW.exempt_tokens("the strong one for decades"),
                           LW.client_word_runs(curly)))

# --- 7. CTA exemption unchanged ----------------------------------------------
cta = LW.validate_lyrics(
    [{"line_id": "cta1", "text": "Tap to claim your kit today",
      "critical": True}],
    {"cta_text": "Tap to claim your kit"})
check("cta lines still pass", cta["outcome"] == "ok")

# --- 8. first-person lines unaffected -----------------------------------------
fp = LW.validate_lyrics(
    [{"line_id": "v7", "text": "I take my name"}], brief)
check("first-person lines still pass",
      fp["outcome"] == "ok" or "line-not-first-person" not in
      [e["error"] for e in fp["errors"]])

# --- 9. real-data proof --------------------------------------------------------
laya = _laya()
if laya is not None:
    b, lines = laya
    r = LW.validate_lyrics(lines, b)
    errs = r.get("errors") or []
    check("laya v2 exempt (real data)",
          all(e.get("detail") != "v2" for e in errs
              if e["error"] == "line-not-first-person"),
          repr([e for e in errs if e["error"] == "line-not-first-person"]))
    # The spec's alternative proof: name the remaining invented line.
    check("laya remaining refusal is exactly v1",
          all(e.get("detail") == "v1" for e in errs
              if e["error"] == "line-not-first-person"),
          repr(errs))
else:
    checks.append("laya real-data (skipped: VTV run dir not present)")
    print("NOTE: real-data fixture not present at %s; skipped" % LAYA)

print("test_brief_exemption_v2972: %s (%d checks, %d failures)"
      % ("PASS" if not fails else "FAIL", len(checks), len(fails)))
for f in fails:
    print(" -", f)
sys.exit(0 if not fails else 1)
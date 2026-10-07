#!/usr/bin/env python3
"""Sketch to Life is always All Suno -- mocked tests (D25, decision log 2026-10-07).

Proves the AF-STL-U1 acceptance points, stdlib only, zero network, zero paid
calls:

  1. Sketch to Life + Velvet Voiceover is **refused at intake** with a clear
     client-facing reason and a re-ask whose ``preselected`` payload is All
     Suno on the same look;
  2. Velvet Voiceover is **unselectable on the card** for Sketch to Life --
     disabled by default (listed, ``selectable`` False, unavailable note) and
     droppable with ``mode="hide"`` -- while **every other look keeps it**;
  3. All Suno stays the default and stays selectable on all five looks;
  4. the card writer ``apply_voice`` refuses the pair without mutating the
     caller's card, and writes the voice field alone when it is allowed;
  5. unknown look / unknown voice fail closed by name instead of guessing;
  6. package hygiene: no media file, no absolute operator path, no network or
     provider code, no provider URL, no Skill/KIE call in this unit.

Mocked: sockets are replaced with a stub that raises, so any accidental
network use fails the suite instead of spending. Known-bad control: point
STL_VOICE_GUARD_PATH at a mutated copy of the guard module (lane receipts/)
and the same suite must FAIL -- a check that cannot fail is not evidence.

Run: python3 core/choice_card/stl_voice_guard/test_stl_voice_guard.py
"""
from __future__ import annotations

import importlib.util
import os
import re
import socket
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(os.path.dirname(HERE))     # core/
sys.path.insert(0, CORE)

# Negative-control hook: point this at a mutated copy of the guard module and
# the same suite must fail. Used by the lane's controls, never in normal runs.
_OVERRIDE = os.environ.get("STL_VOICE_GUARD_PATH")
if _OVERRIDE:
    _spec = importlib.util.spec_from_file_location(
        "stl_voice_guard_under_test", _OVERRIDE)
    M = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(M)
else:
    import choice_card.stl_voice_guard as M      # noqa: E402  (unit under test)

# --- mocked environment: no live sockets, no spend -------------------------
_REAL_SOCKET = socket.socket


class _NoNetwork(_REAL_SOCKET):
    def connect(self, *a, **kw):
        raise AssertionError("network call during a mocked test")

    def connect_ex(self, *a, **kw):
        raise AssertionError("network call during a mocked test")


socket.socket = _NoNetwork                       # noqa: A001

# Plan 4.1's Voice line, transcribed verbatim from
# DRAMA_SONG_AD_FACTORY_V2_PLAN.md section 4.1 (the note is part of it).
import voice_velvet_echo.velvet_voiceover as _VV   # noqa: E402

_PLAN_41_LINE = (
    "Voice:       All Suno (default)  /  Velvet Voiceover "
    "(Google voiceover with the song underneath; not with Sketch to Life)"
)

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % str(detail)) if not cond else ""))
    if not cond:
        FAILS.append(name)


def raises(code, fn, *a, **kw):
    try:
        fn(*a, **kw)
    except M.StlGuardError as exc:
        return exc.code == code, "%s (wanted %s)" % (exc.code, code)
    except Exception as exc:                      # noqa: BLE001
        return False, "%s: %s" % (type(exc).__name__, exc)
    return False, "no error raised"


def sample_card():
    """The plan 4.1 card, before a voice choice."""
    return {
        "length": "60 seconds",
        "shape": "9:16 vertical",
        "style": "lifelike-3d",
        "music": "soul-ballad",
        "voice": "all_suno",
        "clips": None,
        "video_model": "MiniMax H3, 768P",
        "price": "$2.54",
    }


# --- 1. the constants ------------------------------------------------------
def test_constants():
    check("source cites Decision log 38",
          "Decision log 38" in M.SOURCE, M.SOURCE)
    check("source cites plan 6.12.1 and 4.1",
          "plan 6.12.1" in M.SOURCE and "4.1" in M.SOURCE, M.SOURCE)
    check("sketch to life is the guarded look id", M.STL_LOOK_ID == "sketch-to-life",
          M.STL_LOOK_ID)
    check("guarded look label is Sketch to Life",
          M.STL_LOOK_LABEL == "Sketch to Life", M.STL_LOOK_LABEL)
    check("the other four keeps are listed",
          len(M.STL_OTHER_LOOKS) == 4 and M.STL_LOOK_ID not in M.STL_OTHER_LOOKS,
          M.STL_OTHER_LOOKS)
    check("guard covers all five looks once",
          set(M.STL_OTHER_LOOKS) | {M.STL_LOOK_ID} ==
          {"lifelike-3d", "2d-hand-painted", "sketch-to-life",
           "canvas-to-life", "canvas-to-3d"}, M.STL_OTHER_LOOKS)
    check("all Suno id and Velvet id come from the sibling module",
          M.ALL_SUNO_ID == "all_suno" and M.VELVET_ID == "velvet_voiceover",
          (M.ALL_SUNO_ID, M.VELVET_ID))
    check("All Suno is the default voice (Decision 27)",
          M.DEFAULT_VOICE_ID == M.ALL_SUNO_ID, M.DEFAULT_VOICE_ID)
    check("disable is the default card mode", M.DEFAULT_MODE == "disable",
          M.DEFAULT_MODE)
    check("both card modes are offered",
          M.MODES == ("disable", "hide"), M.MODES)
    check("refusal code is stable", M.REASON_CODE == "stl-voice-velvet-not-offered",
          M.REASON_CODE)


# --- 2. the card: unselectable for Sketch to Life -------------------------
def test_card_disables_velvet_for_sketch_to_life():
    check("Sketch to Life offers only All Suno",
          M.selectable_voice_ids("Sketch to Life") == (M.ALL_SUNO_ID,),
          M.selectable_voice_ids("Sketch to Life"))
    opts = M.voice_options_for("sketch-to-life")
    check("the disabled card still lists both rows", len(opts) == 2, len(opts))
    velvet = [o for o in opts if o["id"] == M.VELVET_ID]
    check("Velvet Voiceover is present but unselectable",
          len(velvet) == 1 and velvet[0]["selectable"] is False, velvet)
    check("the disabled row says why it is unavailable",
          bool(velvet) and "unavailable with Sketch to Life" in velvet[0]["label"],
          velvet and velvet[0]["label"])
    check("the disabled row carries the client-facing reason",
          bool(velvet) and velvet[0]["unavailable_reason"] == M.CLIENT_REASON,
          velvet and velvet[0]["unavailable_reason"])
    all_suno = [o for o in opts if o["id"] == M.ALL_SUNO_ID]
    check("All Suno stays selectable and default on Sketch to Life",
          len(all_suno) == 1 and all_suno[0]["selectable"] is True
          and all_suno[0]["default"] is True, all_suno)

    line = M.voice_line("Sketch to Life")
    check("Voice line is one line", line.count("\n") == 0, line)
    check("Voice line body starts at column 13", line.index("All Suno") == 13,
          repr(line))
    check("Voice line offers All Suno", "All Suno (default)" in line, line)
    check("Voice line does not offer the selectable Velvet label",
          M.VELVET_LABEL not in line, line)
    check("Voice line marks Velvet unavailable",
          "unavailable with Sketch to Life" in line, line)

    line_hide = M.voice_line("sketch-to-life", mode="hide")
    check("hidden mode drops Velvet from the line",
          M.VELVET_DISABLED_LABEL not in line_hide and "Velvet" not in line_hide,
          line_hide)
    check("hidden mode keeps All Suno", "All Suno (default)" in line_hide,
          line_hide)
    check("hidden mode leaves one option",
          len(M.voice_options_for("sketch-to-life", "hide")) == 1,
          M.voice_options_for("sketch-to-life", "hide"))
    check("an unknown mode is refused by name",
          raises("MODE_UNKNOWN", M.voice_options_for, "sketch-to-life", "loud")[0])


def test_card_block_forces_all_suno():
    forced = M.card_voice_block("Sketch to Life", "velvet-voiceover")
    check("card block falls back to All Suno",
          forced["selected"] == M.ALL_SUNO_ID, forced["selected"])
    check("card block records that it forced the choice", forced["forced"] is True,
          forced["forced"])
    check("card block names what it rejected",
          forced["rejected"] == M.VELVET_ID, forced["rejected"])
    check("card block carries the client-facing reason",
          forced["reason"] == M.CLIENT_REASON, forced["reason"])
    check("card block selectable list is All Suno only",
          forced["selectable"] == [M.ALL_SUNO_ID], forced["selectable"])
    check("card block line is the disabled line",
          forced["line"] == M.voice_line("Sketch to Life"), forced["line"])

    ok = M.card_voice_block("Canvas to Life", "velvet_voiceover")
    check("other looks select Velvet without forcing",
          ok["selected"] == M.VELVET_ID and ok["forced"] is False
          and ok["rejected"] is None, ok)
    check("other looks list both voices as selectable",
          ok["selectable"] == [M.ALL_SUNO_ID, M.VELVET_ID], ok["selectable"])
    check("no-choice card block defaults to All Suno",
          M.card_voice_block(None, None)["selected"] == M.ALL_SUNO_ID,
          M.card_voice_block(None, None)["selected"])


# --- 3. every other look keeps the option ---------------------------------
def test_other_looks_keep_velvet():
    for lid in M.STL_OTHER_LOOKS:
        check("%s keeps Velvet selectable" % lid,
              M.VELVET_ID in M.selectable_voice_ids(lid),
              M.selectable_voice_ids(lid))
        opts = M.voice_options_for(lid)
        check("%s offers both voices" % lid,
              len(opts) == 2 and all(o["selectable"] for o in opts), opts)
        check("%s Voice line carries the plan 4.1 Velvet label" % lid,
              M.VELVET_LABEL in M.voice_line(lid), M.voice_line(lid))
        check("%s Voice line is byte-identical to plan 4.1's line" % lid,
              M.voice_line(lid) == _PLAN_41_LINE, M.voice_line(lid))
        # the plan 4.1 label extends the sibling's with the D25 note, so the
        # sibling's wording (minus its closing paren) must still be a prefix.
        check("%s Voice line still starts with the sibling wording" % lid,
              M.VELVET_LABEL.startswith(
                  _VV.voice_options()[1]["label"][:-1]),
              M.VELVET_LABEL)
        verdict = M.guard_intake(lid, "velvet_voiceover")
        check("%s accepts Velvet at intake" % lid,
              verdict["outcome"] == "ok" and verdict["questions"] == [], verdict)


def test_plan_41_line_is_rendered_verbatim():
    check("no-look Voice line matches plan 4.1 exactly",
          M.voice_line(None) == _PLAN_41_LINE, repr(M.voice_line(None)))
    check("the plan 4.1 line carries the D25 note",
          "not with Sketch to Life" in _PLAN_41_LINE, _PLAN_41_LINE)
    check("the sibling's pre-D25 label still resolves at intake",
          M.normalize_voice_choice(_VV.voice_options()[1]["label"]) == M.VELVET_ID,
          _VV.voice_options()[1]["label"])


def test_default_look_keeps_velvet():
    check("no choice means Lifelike 3D", M.resolve_look(None) == "lifelike-3d",
          M.resolve_look(None))
    check("the default look keeps Velvet Voiceover",
          M.velvet_offered_with(None) is True
          and M.VELVET_ID in M.selectable_voice_ids(None),
          M.selectable_voice_ids(None))
    check("the label spelling resolves like the id",
          M.resolve_look("Sketch to Life") == M.STL_LOOK_ID
          and M.resolve_look("sketch to life") == M.STL_LOOK_ID,
          M.resolve_look("Sketch to Life"))


# --- 4. intake refuses the pair and re-asks with All Suno -----------------
def test_intake_refuses_sketch_to_life_with_velvet():
    verdict = M.guard_intake("Sketch to Life", "velvet_voiceover")
    check("the pair is refused at intake", verdict["outcome"] == "refused",
          verdict["outcome"])
    check("the refusal carries the stable reason code",
          verdict["reason_code"] == M.REASON_CODE, verdict["reason_code"])
    msg = verdict["client_message"] or ""
    check("the reason is client-facing prose, not a code",
          len(msg) > 40 and not msg.isupper(), msg)
    check("the reason names Sketch to Life", "Sketch to Life" in msg, msg)
    check("the reason names All Suno", "All Suno" in msg, msg)
    check("the reason names Velvet Voiceover", "Velvet Voiceover" in msg, msg)
    check("the refusal re-asks", len(verdict["questions"]) == 1
          and bool(verdict["questions"][0]["question"]), verdict["questions"])
    # Read safely: a guard that forgets to re-ask must FAIL the check, not
    # abort the suite with an IndexError (a crash hides which rule broke).
    _q0 = verdict["questions"][0] if verdict["questions"] else {}
    pre = _q0.get("preselected")
    check("the re-ask pre-selects All Suno",
          pre == {"look": M.STL_LOOK_ID, "voice": M.ALL_SUNO_ID}, pre)
    check("the re-ask only offers All Suno",
          _q0.get("selectable") == [M.ALL_SUNO_ID],
          _q0.get("selectable"))
    check("the refusal itself reports All Suno as the choice",
          verdict["voice"] == M.ALL_SUNO_ID, verdict["voice"])
    check("the refusal names the rejected voice",
          verdict.get("rejected_voice") == M.VELVET_ID,
          verdict.get("rejected_voice"))
    check("the next action is the re-presented card",
          verdict["next_action"] == M.NEXT_ACTION_REFUSED, verdict["next_action"])
    check("the body-level preselected mirrors the question's",
          verdict["preselected"] == pre, verdict["preselected"])

    check("the same refusal fires on id spelling and on the plan label",
          M.guard_intake("sketch-to-life", "velvet-voiceover")["outcome"] == "refused"
          and M.guard_intake(
              "sketch to life",
              "Velvet Voiceover (Google voiceover with the song underneath; "
              "not with Sketch to Life)")["outcome"] == "refused")
    check("the retired slug is normalized then refused",
          M.guard_intake("sketch-to-life", "velvet_echo")["outcome"] == "refused",
          M.guard_intake("sketch-to-life", "velvet_echo"))
    check("is_forbidden names exactly the one pair",
          M.is_forbidden("sketch-to-life", "velvet_voiceover") is True
          and M.is_forbidden("sketch-to-life", "all_suno") is False
          and M.is_forbidden("canvas-to-life", "velvet_voiceover") is False)


def test_intake_accepts_the_allowed_pairs():
    ok = M.guard_intake("Sketch to Life", "All Suno")
    check("Sketch to Life + All Suno passes intake",
          ok["outcome"] == "ok" and ok["voice"] == M.ALL_SUNO_ID, ok)
    check("a passing verdict asks nothing", ok["questions"] == [],
          ok["questions"])
    check("no-choice voice is the All Suno default",
          M.guard_intake("sketch-to-life", None)["outcome"] == "ok",
          M.guard_intake("sketch-to-life", None))
    check("the card composer's hyphen slug is accepted",
          M.guard_intake("sketch-to-life", "all-suno")["outcome"] == "ok"
          and M.normalize_voice_choice("velvet-voiceover") == M.VELVET_ID,
          M.normalize_voice_choice("velvet-voiceover"))
    check("the guard alias behaves like the intake gate",
          M.guard("canvas-to-life", "velvet_voiceover")["outcome"] == "ok",
          M.guard("canvas-to-life", "velvet_voiceover"))


# --- 5. the card writer ----------------------------------------------------
def test_apply_voice_refuses_without_mutating():
    card = sample_card()
    before = dict(card)
    ok, detail = raises("stl-voice-velvet-not-offered", M.apply_voice, card,
                        "Sketch to Life", "velvet_voiceover")
    check("the writer refuses Sketch to Life + Velvet", ok, detail)
    check("the refused writer leaves the card untouched", card == before, card)

    # the look can also come off the card itself
    stl_card = sample_card()
    stl_card["style"] = "sketch-to-life"
    ok, detail = raises("stl-voice-velvet-not-offered", M.apply_voice, stl_card,
                        None, "Velvet Voiceover")
    check("the writer reads the look from the card", ok, detail)
    check("that refusal left the card alone",
          stl_card["voice"] == "all_suno", stl_card)

    ok, detail = raises("CARD_INVALID", M.apply_voice, "not a card", None, None)
    check("a non-dict card is refused", ok, detail)


def test_apply_voice_writes_only_the_voice_field():
    card = sample_card()
    keys_before = set(card)
    out = M.apply_voice(card, "sketch-to-life", "All Suno")
    check("the writer copies the card", out is not card)
    check("the writer touches nothing but the voice field",
          set(out) == keys_before
          and out["voice"] == M.ALL_SUNO_ID
          and all(out[k] == card[k] for k in card if k != M.VOICE_FIELD),
          {k: (card.get(k), out.get(k)) for k in keys_before
           if card.get(k) != out.get(k)})
    check("the writer left the caller's card alone",
          card["voice"] == "all_suno", card)

    velvet_card = M.apply_voice(sample_card(), "Canvas to Life", "velvet-voiceover")
    check("the writer takes Velvet on a look that offers it",
          velvet_card["voice"] == M.VELVET_ID, velvet_card["voice"])
    check("Velvet lands under the canonical card field name",
          M.VOICE_FIELD == "voice" and "voice" in velvet_card,
          M.VOICE_FIELD)


# --- 6. unknown choices fail closed ---------------------------------------
def test_unknown_choices_fail_closed():
    check("an unknown voice is refused by name",
          raises("VOICE_NOT_OFFERED", M.normalize_voice_choice, "telepathy")[0])
    check("a non-string voice is refused",
          raises("VOICE_NOT_OFFERED", M.normalize_voice_choice, 7)[0])
    check("an unknown look is refused by name",
          raises("LOOK_NOT_OFFERED", M.resolve_look, "neon-noir")[0])
    check("the intake gate refuses an unknown voice too",
          raises("VOICE_NOT_OFFERED", M.guard_intake, "sketch-to-life",
                 "telepathy")[0])
    check("the intake gate refuses an unknown look too",
          raises("LOOK_NOT_OFFERED", M.guard_intake, "neon-noir",
                 "all_suno")[0])
    check("the writer refuses an unknown look too",
          raises("LOOK_NOT_OFFERED", M.apply_voice, sample_card(),
                 "neon-noir", "all_suno")[0])


# --- 6b. the repo's real intake and the repo's real card --------------------
#: ``resolve_style`` only needs a non-empty action link, never a real one.
_REAL_LINK = "weekly-action-link"
#: The batch card spells the voice with hyphens; the intake uses the id.
_BATCH_VELVET = "velvet-voiceover"


def test_real_intake_and_card_refuse_the_pair():
    """Drives the sibling builders, not hand-made fixtures.

    The planner's initial questions are the look/voice intake and the batch
    module builds the choice card, so both must refuse the D25 pair on their
    own -- a guard nothing calls would prove nothing.
    """
    from smp.initial_questions import initial_questions as IQ
    from batch_mode import batch as BM

    # ---- intake -----------------------------------------------------------
    refusal = None
    try:
        IQ.resolve_style({"look": M.STL_LOOK_ID, "voice": M.VELVET_ID},
                         kie_active=True, weekly_action_link=_REAL_LINK)
    except IQ.InitialQuestionsError as exc:
        refusal = exc
    check("real intake refuses Sketch to Life + Velvet Voiceover",
          refusal is not None and refusal.code == M.REASON_CODE,
          getattr(refusal, "code", None))
    check("real intake refusal is the client-facing reason",
          refusal is not None and "All Suno" in str(refusal)
          and "Sketch to Life" in str(refusal),
          str(refusal)[:120] if refusal else None)
    reask = getattr(refusal, "reask", None) if refusal else None
    check("real intake refusal re-asks with All Suno pre-selected",
          bool(reask)
          and reask.get("outcome") == "refused"
          and reask.get("preselected") == {"look": M.STL_LOOK_ID,
                                           "voice": M.ALL_SUNO_ID},
          reask)

    for look in M.STL_OTHER_LOOKS:
        style = IQ.resolve_style({"look": look, "voice": M.VELVET_ID},
                                 kie_active=True, weekly_action_link=_REAL_LINK)
        check("real intake keeps Velvet Voiceover on %s" % look,
              M.guard_intake(style["look"], style["voice"])["outcome"] == "ok",
              style)
    stl_default = IQ.resolve_style({"look": M.STL_LOOK_ID,
                                    "voice": M.ALL_SUNO_ID},
                                   kie_active=True,
                                   weekly_action_link=_REAL_LINK)
    check("real intake still takes All Suno on Sketch to Life",
          M.guard_intake(stl_default["look"],
                         stl_default["voice"])["outcome"] == "ok",
          stl_default)

    # ---- the choice card --------------------------------------------------
    card_refusal = None
    try:
        BM.make_card({"style": M.STL_LOOK_ID, "voice": _BATCH_VELVET})
    except BM.BatchError as exc:
        card_refusal = exc
    check("real card builder refuses the pair",
          card_refusal is not None and card_refusal.code == M.REASON_CODE,
          getattr(card_refusal, "code", None))

    for look in M.STL_OTHER_LOOKS:
        card = BM.make_card({"style": look, "voice": _BATCH_VELVET})
        rendered = "\n".join(BM.card_lines(card))
        check("real card keeps Velvet Voiceover on %s" % look,
              M.guard_intake(card["style"], card["voice"])["outcome"] == "ok"
              and "Velvet Voiceover" in rendered,
              rendered)

    legacy = BM.make_card({"style": "canvas-to-life", "voice": _BATCH_VELVET})
    legacy["style"] = M.STL_LOOK_ID                 # written before D25
    legacy_lines = "\n".join(BM.card_lines(legacy))
    check("a card already holding the pair never prints Velvet Voiceover",
          "Velvet Voiceover" not in legacy_lines
          and "All Suno" in legacy_lines,
          legacy_lines)

    # ---- the row this unit renders ---------------------------------------
    row = [o for o in M.voice_options_for(M.STL_LOOK_ID)
           if o["id"] == M.VELVET_ID][0]
    check("this unit's card row disables Velvet for Sketch to Life",
          row["selectable"] is False and bool(row["unavailable_reason"]),
          row)
    check("mode='hide' drops it from the row entirely",
          [o["id"] for o in M.voice_options_for(M.STL_LOOK_ID, mode="hide")]
          == [M.ALL_SUNO_ID])
    check("the sibling's look-less field still lists both options",
          len(_VV.choice_card_voice_field(M.VELVET_ID)["options"]) == 2)


# --- 7. hygiene ------------------------------------------------------------
def _package_files():
    return sorted(os.path.join(HERE, n) for n in os.listdir(HERE)
                  if not n.startswith("__pycache__"))


_MEDIA = (".mp4", ".mov", ".mkv", ".avi", ".webm", ".wav", ".mp3", ".m4a",
          ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg")
_NETWORK_RE = re.compile(
    r"^\s*(import|from)\s+(requests|urllib|http|aiohttp|httpx|socket)\b", re.M)
_PROVIDER_RE = re.compile(r"(api\.kie|kie\.ai|/api/v1/|curl\s|pm2\s|subprocess)")
_URL_RE = re.compile(r"https?://")
_HOME_PREFIX = os.path.expanduser("~")


def test_package_hygiene():
    paths = _package_files()
    check("package has files", len(paths) >= 3, len(paths))
    media = [p for p in paths if p.lower().endswith(_MEDIA)]
    check("no media file in the unit", not media, media)
    texts = {}
    for path in paths:
        if path.endswith((".py", ".md")):
            with open(path, encoding="utf-8") as handle:
                texts[path] = handle.read()
    hits = [os.path.basename(p) for p, t in texts.items()
            if _HOME_PREFIX in t]
    check("no absolute operator path in the unit", not hits, hits)
    for name in ("stl_voice_guard.py", "__init__.py"):
        text = texts.get(os.path.join(HERE, name), "")
        check("%s never imports a network module" % name,
              not _NETWORK_RE.search(text), _NETWORK_RE.findall(text))
        check("%s carries no provider/KIE/pm2 call" % name,
              not _PROVIDER_RE.search(text), _PROVIDER_RE.findall(text))
        check("%s carries no URL" % name, not _URL_RE.search(text),
              _URL_RE.findall(text))
    suite = texts.get(os.path.join(HERE, os.path.basename(__file__)), "")
    # The suite names requests/urllib/httpx/aiohttp only inside the regex
    # literals above, so a bare substring scan would flag this file itself.
    # Match real import statements instead; ``import socket`` stays legal --
    # it is the mock, and its use is checked separately.
    self_import = re.compile(
        r"^\s*(?:import|from)\s+(?:requests|urllib|httpx|aiohttp)\b", re.M)
    _OPEN = "url" + "open"                       # spelled apart: this is it
    check("this suite itself never reaches the network",
          not self_import.search(suite)
          and not _URL_RE.search(suite)
          and _OPEN not in suite,
          self_import.findall(suite) + _URL_RE.findall(suite))
    check("unit makes no provider call: socket is mocked and never used",
          socket.socket is _NoNetwork)
    check("build root resolves to the directory that owns core/",
          bool(M.build_root())
          and os.path.isdir(os.path.join(M.build_root(), "core", "choice_card")),
          M.build_root())
    check("build root carries no operator home prefix in the module",
          _HOME_PREFIX not in texts.get(
              os.path.join(HERE, "stl_voice_guard.py"), "\0"))


def test_negative_control_the_guard_can_fail():
    """Known-bad controls: a guard that never refuses is not a guard."""
    check("control: the pair IS refused today",
          M.is_forbidden("sketch-to-life", "velvet_voiceover")
          and M.guard_intake("sketch-to-life", "velvet_voiceover")
          ["outcome"] == "refused")
    check("control: the same check does not refuse every pairing",
          not M.is_forbidden("canvas-to-life", "velvet_voiceover")
          and not M.is_forbidden("sketch-to-life", "all_suno"))
    check("control: the card reader reports the disabled row",
          [o for o in M.voice_options_for("sketch-to-life")
           if o["id"] == M.VELVET_ID][0]["selectable"] is False)
    check("control: a planted client reason is what the refusal carries",
          "All Suno" in M.CLIENT_REASON and "Sketch to Life" in M.CLIENT_REASON,
          M.CLIENT_REASON)


TESTS = (
    test_constants,
    test_card_disables_velvet_for_sketch_to_life,
    test_card_block_forces_all_suno,
    test_other_looks_keep_velvet,
    test_plan_41_line_is_rendered_verbatim,
    test_default_look_keeps_velvet,
    test_intake_refuses_sketch_to_life_with_velvet,
    test_intake_accepts_the_allowed_pairs,
    test_apply_voice_refuses_without_mutating,
    test_apply_voice_writes_only_the_voice_field,
    test_unknown_choices_fail_closed,
    test_real_intake_and_card_refuse_the_pair,
    test_package_hygiene,
    test_negative_control_the_guard_can_fail,
)


def main():
    for test in TESTS:
        test()
    print("\n%d checks failed, %d tests run" % (len(FAILS), len(TESTS)))
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())

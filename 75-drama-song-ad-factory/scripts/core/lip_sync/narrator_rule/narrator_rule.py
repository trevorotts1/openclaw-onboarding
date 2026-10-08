#!/usr/bin/env python3
"""Narrator lip-sync rule -- Decision 26 (Trevor, 2026-10-07) + plan 6.6.

The canonical rule (``core/voice_velvet_echo`` mirrors its token set from
here; this package is the one the lip-sync stage V2-08L screens against):

1. A narrator / off-screen voice may play as voice-over over ANY shot.
2. A lip-synced mouth may only ever move to that on-screen person's OWN
   isolated line -- never a narrator's voice, never another character's
   voice, never a mixed stem (the 2026-10-07 HIDE test lip-synced a CTA
   stem containing another voice onto a face).
3. A device speaking with no person on screen (phone voicemail shot) is a
   legal scene: the picture reads as the device talking. It passes QC as a
   voice-over shot and is never dispatched for mouth animation.
4. QC refuses every violation: a mouth moving to a narrator/foreign voice,
   a face whose voice is not the one playing, a missing or mixed stem.

Two gates, both fail-closed:

* ``screen_line`` / ``screen_selection`` -- planning gate. Screens the base
  stage's ``select_lines`` envelope against speaker + on-screen identity and
  extends it with the ``narrator_rule`` block: which flagged lines may be
  lip-synced, which play as voice-over, which scenes are violations.
* ``check_lipsync_attempt`` -- dispatch/QC gate. Verdict PASS/FAIL for an
  actual lip-sync attempt (mouth moved or not) including the stem check
  (exactly one isolated stem of the on-screen speaker; sung/music/narrator
  stems refused).

stdlib only, no network, no spend. Sibling ``qc_voice_match`` (D17) owns
the pitch bands and the on-screen speaker predicate -- this package imports
those, never re-implements them. The base stage V2-08L (``lip_sync``) is
imported when present for its QC-rule constants; when it is not in the
workspace yet, the mirrored v1 strings below are used and the screened
envelope always echoes the base envelope untouched, so the V2-W1-U5 suite
never sees a changed input.

ponytail: stems are mandatory at the dispatch gate, optional at the
planning gate (audio prep runs after shot planning). Add a strict
``require_stems`` pass to selection only if a stage starts dispatching
straight from the selection envelope.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(os.path.dirname(_HERE))      # .../core
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    # D17 predicate + device tokens live in exactly one place.
    from qc_voice_match import speaker_onscreen_ok          # noqa: F401
    from qc_voice_match.qc_voice_match import VOICE_SOURCE_TOKENS
except ImportError as exc:  # fail closed: never re-implement D17 here
    raise ImportError(
        "narrator_rule needs the sibling package qc_voice_match in %s"
        % (_CORE,)
    ) from exc

try:  # base stage V2-08L when present (lane or post-merge workspace)
    from lip_sync import RULE_FLAGGED as _BASE_RULE_FLAGGED
    from lip_sync import RULE_UNFLAGGED as _BASE_RULE_UNFLAGGED
    _BASE_AVAILABLE = True
except ImportError:
    # Mirrors core/lip_sync v1.0.0. Used only to name rules in overrides;
    # the base envelope itself is passed through untouched either way.
    _BASE_RULE_FLAGGED = "mouth_match_required"
    _BASE_RULE_UNFLAGGED = "no_accidental_mouth_movement"
    _BASE_AVAILABLE = False

TOOL_NAME = "narrator_rule"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.lip-sync-narrator/v1"
QC_SCHEMA_VERSION = "blackceo.lip-sync-narrator/qc/v1"
RULE_CITE = "Decision 26 / plan 6.6"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}

# Canonical narrator token set. core/voice_velvet_echo/velvet_voiceover.py
# carries the same eight tokens as its local copy; change both together.
NARRATOR_TOKENS = frozenset({
    "narrator", "narration", "voice-over", "voiceover", "off-screen",
    "offscreen", "host", "announcer",
})

# QC rule this package installs on flagged-but-voice-over lines.
RULE_VOICE_OVER = "voice_over_no_mouth_movement"
# Base stage constants, mirrored when the base package is absent.
RULE_FLAGGED = _BASE_RULE_FLAGGED
RULE_UNFLAGGED = _BASE_RULE_UNFLAGGED

# Reason codes (screening).
RC_LIPSYNC_OK = "LIPSYNC_OWN_LINE_OK"
RC_NARRATOR = "NARRATOR_VOICE_OVER_ONLY"
RC_DEVICE = "DEVICE_SCENE_VOICE_OVER"
RC_NO_PERSON = "NO_PERSON_ON_SCREEN"
RC_SPEAKER_UNKNOWN = "SPEAKER_UNKNOWN"
RC_ONSCREEN_UNKNOWN = "ONSCREEN_UNKNOWN"
RC_SCENE_UNKNOWN = "SCENE_UNKNOWN"
RC_SPEAKER_MISMATCH = "SPEAKER_MISMATCH"
RC_STEMS_REQUIRED = "STEMS_REQUIRED"
RC_STEM_MALFORMED = "STEM_MALFORMED"
RC_STEM_MISSING = "STEM_MISSING"
RC_MIXED_STEM = "MIXED_STEM"
RC_SUNG_STEM = "SUNG_STEM_PRESENT"
RC_MUSIC_STEM = "MUSIC_STEM_PRESENT"
RC_NARRATOR_STEM = "NARRATOR_STEM"
RC_OTHER_SPEAKER_STEM = "OTHER_SPEAKER_STEM"
RC_NOT_ISOLATED = "NOT_ISOLATED"
# Reason codes (dispatch/QC verdicts).
RC_MOUTH_REQUIRED = "MOUTH_MOVEMENT_REQUIRED"
RC_MOUTH_FORBIDDEN = "MOUTH_MOVEMENT_FORBIDDEN"

# Stem kinds that may never drive a mouth (plan 6.6 + Decision 27: the sung
# layer and the music bed are never a lip-sync input).
SUNG_STEM_KINDS = frozenset({"sung", "song", "sung_layer", "sung-under"})
MUSIC_STEM_KINDS = frozenset({"music_bed", "bed", "music"})
NARRATOR_STEM_KINDS = frozenset({
    "narrator", "narration", "voice-over", "voiceover", "off-screen",
    "offscreen", "host", "announcer",
})

EXIT_NEXT = {
    "ok": "Proceed to the next stage.",
    "parked": "Resolve the reason_code, then re-run; nothing was dispatched.",
    "rejected": "Fix the listed errors and re-run.",
    "waiting": "Repair the named lines, then re-run.",
    "error": "Fix the input shape and re-run.",
}


class NarratorRuleBlocked(Exception):
    """Raised by refuse_lipsync() when a lip-sync attempt was refused."""


def _res(outcome, reason_code, errors, **kw):
    env = {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "rule": RULE_CITE,
        "outcome": outcome,
        "reason_code": reason_code,
        "errors": list(errors),
        "next_action": EXIT_NEXT.get(outcome, EXIT_NEXT["error"]),
    }
    env.update(kw)
    return env


def _norm(value):
    if isinstance(value, str):
        v = value.strip().lower()
        return v or None
    return None


def is_narrator(speaker):
    """True when the voice is a narrator / off-screen voice (Decision 26)."""
    s = _norm(speaker)
    return s in NARRATOR_TOKENS


def is_voice_source(face):
    """True when the face on screen is a device, not a person (D17 set)."""
    f = _norm(face)
    return f in VOICE_SOURCE_TOKENS


def person_on_screen(face):
    """True only when a NAMED PERSON is visible (device/none -> False)."""
    f = _norm(face)
    return bool(f) and f not in VOICE_SOURCE_TOKENS and f not in NARRATOR_TOKENS


# ------------------------------------------------------------------ stems --

def check_stems(stems, speaker):
    """Validate the lip-sync audio input. Returns (ok, reason_code, errors).

    Exactly one stem, isolated, belonging to the on-screen speaker. The sung
    layer, the music bed and a narrator stem are refused (plan 6.6, the
    2026-10-07 HIDE test: a CTA stem carrying another voice was lip-synced
    onto a face).
    """
    spk = _norm(speaker)
    if stems is None:
        return False, RC_STEMS_REQUIRED, ["stem-input-missing"]
    if not isinstance(stems, (list, tuple)):
        return False, RC_STEM_MALFORMED, ["stems-not-a-list"]
    if not stems:
        return False, RC_STEM_MISSING, ["no-stems-given"]
    if len(stems) != 1:
        return False, RC_MIXED_STEM, ["exactly-one-stem:%d" % len(stems)]
    stem = stems[0]
    if not isinstance(stem, dict):
        return False, RC_STEM_MALFORMED, ["stem-not-an-object"]
    kind = _norm(stem.get("kind"))
    if kind in SUNG_STEM_KINDS:
        return False, RC_SUNG_STEM, ["sung-stem:%s" % kind]
    if kind in MUSIC_STEM_KINDS:
        return False, RC_MUSIC_STEM, ["music-stem:%s" % kind]
    if kind in NARRATOR_STEM_KINDS or _norm(stem.get("speaker_id")) in NARRATOR_TOKENS:
        return False, RC_NARRATOR_STEM, ["narrator-stem:%s" % kind]
    stem_spk = _norm(stem.get("speaker_id"))
    if spk and stem_spk and stem_spk != spk:
        return False, RC_OTHER_SPEAKER_STEM, [
            "stem:%s-on-screen:%s" % (stem_spk, spk)]
    if spk and not stem_spk:
        return False, RC_OTHER_SPEAKER_STEM, ["stem-has-no-speaker_id"]
    if stem.get("isolated") is not True:
        return False, RC_NOT_ISOLATED, ["stem-not-flagged-isolated"]
    return True, "STEM_OK", []


# ---------------------------------------------------------- screening gate --

def screen_line(record, stems_required=False):
    """Screen ONE line's scene against Decision 26 / plan 6.6.

    record: {"line_id", "speaker", "onscreen", optional "stems"}.
    Returns an envelope:

    * ``outcome`` ok    -- the scene is legal to SHOW (playback passes);
    * ``outcome`` refused -- the scene itself is a violation (fix the shot);
    * ``lipsync``  True -- a mouth may move here (person's own isolated line);
    * ``voice_over`` True -- the voice plays over the shot with no mouth
      moving (narrator, device, or no person on screen);
    * ``lipsync_reason`` names WHY lipsync is allowed/forbidden.
    """
    if not isinstance(record, dict):
        return _res("error", RC_SCENE_UNKNOWN, ["scene-not-an-object"],
                    line_id=None, lipsync=False, voice_over=False,
                    playback="refused", lipsync_reason=RC_SCENE_UNKNOWN)
    line_id = record.get("line_id")
    speaker = _norm(record.get("speaker"))
    onscreen = _norm(record.get("onscreen"))
    stems = record.get("stems")

    def base(outcome, rc, errors, lipsync, voice_over, playback, **kw):
        env = _res(outcome, rc, errors, line_id=line_id, speaker=speaker,
                   onscreen=onscreen, lipsync=lipsync, voice_over=voice_over,
                   playback=playback, lipsync_reason=rc, **kw)
        return env

    # Fail closed on missing identity: an absent field is never a pass.
    if not speaker:
        return base("refused", RC_SPEAKER_UNKNOWN, ["speaker-missing"],
                    False, False, "refused")
    if not onscreen:
        return base("refused", RC_ONSCREEN_UNKNOWN, ["onscreen-missing"],
                    False, False, "refused")

    # 1. Narrator: voice-over over ANY shot (person, device or empty frame),
    #    never a moving mouth -- Decision 26.
    if is_narrator(speaker):
        return base("ok", RC_NARRATOR, [], False, True, "ok", narrator=True)

    # 2. Device voice: legal only when the device (or no face) is the shot.
    if is_voice_source(speaker):
        if person_on_screen(onscreen):
            return base("refused", RC_SPEAKER_MISMATCH,
                        ["device-voice-on-person:%s" % onscreen],
                        False, False, "refused")
        return base("ok", RC_DEVICE, [], False, True, "ok", device_scene=True)

    # 3. Person speaking.
    if not person_on_screen(onscreen):
        # on_screen is a device: the voice's source is showing, no mouth here.
        if is_voice_source(onscreen):
            return base("ok", RC_NO_PERSON, [], False, True, "ok",
                        device_scene=True)
        return base("refused", RC_ONSCREEN_UNKNOWN, ["onscreen-not-a-person"],
                    False, False, "refused")
    if speaker != onscreen:
        return base("refused", RC_SPEAKER_MISMATCH,
                    ["on-screen:%s-speaker:%s" % (onscreen, speaker)],
                    False, False, "refused")

    # 4. The on-screen person's own line: eligible for lip sync, subject to
    #    the stem check (mandatory only at the dispatch gate). The scene is
    #    legal either way; only the AUDIO INPUT may be refused.
    if stems is None and not stems_required:
        return base("ok", RC_LIPSYNC_OK, [], True, False, "ok",
                    stems_verified=False)
    ok, rc, errs = check_stems(stems, speaker)
    if not ok:
        return base("refused", rc, errs, False, False, "ok",
                    stems_verified=False)
    return base("ok", RC_LIPSYNC_OK, [], True, False, "ok",
                stems_verified=True)


def screen_selection(selection, scenes):
    """Extend the base ``select_lines`` envelope with the narrator rule.

    ``selection`` is the base stage's envelope (passed through untouched --
    the V2-W1-U5 suite's input shape never changes). ``scenes`` maps
    line_id -> {"speaker", "onscreen", optional "stems"}.

    Envelope adds ``narrator_rule``::

        lipsync_line_ids    -- flagged lines a mouth MAY move to
        voice_over_line_ids -- flagged lines that play without a mouth
        violations          -- scenes that are illegal as shot (rejected)
        per_line            -- every screen_line() envelope

    outcome rejected on: unknown scene, playback violation, or a stem
    violation on a line whose scene would otherwise be lip-syncable.
    """
    if not isinstance(scenes, dict):
        return _res("error", "SCENES_INVALID", ["scenes-must-be-a-map"],
                    base_selection=selection)
    if isinstance(selection, dict) and selection.get("outcome") not in (None, "ok"):
        # Base rejected the selection on its own terms: pass it through
        # before any shape check (a rejection envelope has no "selected").
        return dict(selection)
    if not isinstance(selection, dict) or not isinstance(
            selection.get("selected"), list):
        return _res("error", "BASE_SELECTION_INVALID",
                    ["base-select_lines-envelope-required"],
                    base_selection=selection)

    per_line, lipsync_ids, voice_over_ids, violations, errors = {}, [], [], [], []
    for rec in selection["selected"]:
        lid = rec.get("line_id")
        scene = scenes.get(lid)
        if not isinstance(scene, dict):
            env = _res("rejected", RC_SCENE_UNKNOWN,
                       ["scene-missing:%s" % lid],
                       line_id=lid, lipsync=False, voice_over=False,
                       playback="refused", lipsync_reason=RC_SCENE_UNKNOWN)
            per_line[lid] = env
            errors.extend(env["errors"])
            violations.append({"line_id": lid, "reason_code": RC_SCENE_UNKNOWN,
                               "detail": "no scene record for a flagged line"})
            continue
        record = dict(scene)
        record.setdefault("line_id", lid)
        env = screen_line(record, stems_required=False)
        per_line[lid] = env
        if env["outcome"] == "refused":
            errors.extend("line-%s:%s" % (lid, e) for e in env["errors"])
            violations.append({"line_id": lid,
                               "reason_code": env["reason_code"],
                               "detail": "; ".join(env["errors"])})
            continue
        if env["lipsync"]:
            # Stems were optional here; if the scene carries them, verify now.
            if record.get("stems") is not None:
                sok, src, serrs = check_stems(record["stems"],
                                              record.get("speaker"))
                if not sok:
                    errors.extend("line-%s:%s" % (lid, e) for e in serrs)
                    violations.append({"line_id": lid, "reason_code": src,
                                       "detail": "; ".join(serrs)})
                    continue
            lipsync_ids.append(lid)
        else:
            voice_over_ids.append(lid)

    rule_block = {
        "schema_version": QC_SCHEMA_VERSION,
        "rule": RULE_CITE,
        "lipsync_line_ids": lipsync_ids,
        "voice_over_line_ids": voice_over_ids,
        "violations": violations,
        "per_line": per_line,
        "narrator_never_lipsynced": True,
        "device_scene_passes": True,
        "base_envelope_passed_through": True,
    }
    if errors:
        return _res("rejected", "SELECTION_HAS_VIOLATIONS", errors,
                    narrator_rule=rule_block, base_selection=selection,
                    lipsync_line_ids=lipsync_ids,
                    voice_over_line_ids=voice_over_ids)
    return _res("ok", "SELECTION_SCREENED", [],
                narrator_rule=rule_block, base_selection=selection,
                lipsync_line_ids=lipsync_ids,
                voice_over_line_ids=voice_over_ids)


def lipsync_selection(selection, screened):
    """Base-shaped ``{"selected": [...]}`` subset for the dispatch stage.

    Only the lines the narrator rule allows a mouth to move to; empty is
    legal (a voice-over-only ad matches directive 11.4's default).
    """
    if not isinstance(screened, dict) or screened.get("outcome") != "ok":
        return {"selected": []}
    allowed = set(screened.get("lipsync_line_ids") or [])
    recs = [r for r in selection.get("selected", [])
            if r.get("line_id") in allowed]
    return {"selected": recs}


# ---------------------------------------------------------- dispatch gate --

def check_lipsync_attempt(record, scene, flagged=True):
    """Verdict one actual lip-sync attempt. PASS or FAIL, fail-closed.

    record: {"line_id", "mouth_moved": bool, optional "stems"}.
    scene:  {"speaker", "onscreen", optional "stems"} (record.stems wins).

    FAIL when: an illegal scene, a mouth moving to a narrator/device/
    foreign voice, a missing or invalid stem, or -- on a flagged line the
    rule allows to move -- a mouth that did NOT move (plan 6.3's swap).
    """
    if not isinstance(record, dict) or not isinstance(scene, dict):
        return _qc(False, RC_SCENE_UNKNOWN,
                   ["attempt-and-scene-must-be-objects"],
                   line_id=(record or {}).get("line_id")
                   if isinstance(record, dict) else None)
    merged = dict(scene)
    merged.setdefault("line_id", record.get("line_id"))
    if record.get("stems") is not None:
        merged["stems"] = record["stems"]
    mouth_moved = bool(record.get("mouth_moved"))
    line_id = merged.get("line_id")

    env = screen_line(merged, stems_required=True)
    if env["outcome"] == "refused":
        return _qc(False, env["reason_code"], env["errors"],
                   line_id=line_id, playback=env["playback"],
                   mouth_moved=mouth_moved, scene=env)
    if mouth_moved and not env["lipsync"]:
        return _qc(False, RC_MOUTH_FORBIDDEN,
                   ["mouth-moved-to:%s" % env["lipsync_reason"]],
                   line_id=line_id, playback=env["playback"],
                   mouth_moved=True, voice_over=env["voice_over"],
                   scene=env)
    if not mouth_moved and env["lipsync"] and flagged:
        return _qc(False, RC_MOUTH_REQUIRED,
                   ["flagged-own-line-without-mouth-movement"],
                   line_id=line_id, playback=env["playback"],
                   mouth_moved=False, scene=env)
    return _qc(True, "LIPSYNC_ATTEMPT_OK", [],
               line_id=line_id, playback=env["playback"],
               mouth_moved=mouth_moved, voice_over=env.get("voice_over", False),
               scene=env)


def _qc(passed, reason_code, errors, **kw):
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "rule": RULE_CITE,
        "verdict": "PASS" if passed else "FAIL",
        "outcome": "ok" if passed else "rejected",
        "reason_code": reason_code,
        "errors": list(errors),
        "next_action": EXIT_NEXT["ok"] if passed else EXIT_NEXT["rejected"],
        **kw,
    }


def refuse_lipsync(qc_result):
    """Assembly hook: raise unless the attempt passed (qc_voice_match style)."""
    if not isinstance(qc_result, dict) or qc_result.get("verdict") != "PASS":
        code = (qc_result or {}).get("reason_code", "LIPSYNC_REFUSED")
        raise NarratorRuleBlocked(code)
    return True


# ------------------------------------------------------------- QC rules ----

def narrator_qc_rules(base_rules, scenes, flagged_ids=None):
    """Extend the base stage's QC rule map with the narrator rule.

    base_rules: ``line_id -> rule dict`` from ``lip_sync.qc_rules`` (or any
    map carrying ``mouth_movement``). scenes: as ``screen_selection``.

    * flagged line, rule allows the mouth -> base rule kept untouched;
    * flagged line, rule forbids the mouth (narrator / device / no person)
      -> overridden to ``voice_over_no_mouth_movement``, mouth forbidden,
      source Decision 26 -- the plan 6.3 "required" swap does NOT apply;
    * unflagged lines -> untouched (directive 17.4 keeps ruling).
    """
    if not isinstance(base_rules, dict):
        return _res("error", "BASE_RULES_INVALID",
                    ["rules-map-required"])
    flagged = set(flagged_ids) if flagged_ids is not None else set(base_rules)
    rules, overrides = {}, []
    for lid, rule in base_rules.items():
        scene = (scenes or {}).get(lid)
        if lid not in flagged or not isinstance(scene, dict):
            rules[lid] = rule
            continue
        env = screen_line(dict(scene, line_id=lid), stems_required=False)
        if env["outcome"] == "refused":
            # Illegal scene: keep the base rule AND force the mouth shut.
            rules[lid] = _override(rule, env["reason_code"])
            overrides.append({"line_id": lid, "from": env["reason_code"]})
            continue
        if env["lipsync"]:
            rules[lid] = rule          # plan 6.3 swap stands
            continue
        rules[lid] = _override(rule, env["lipsync_reason"])
        overrides.append({"line_id": lid, "from": env["lipsync_reason"]})
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "rule": RULE_CITE,
        "outcome": "ok",
        "reason_code": "QC_RULES_EXTENDED",
        "rules": rules,
        "overrides": overrides,
        "flagged": sorted(flagged),
        "base_flagged_rule": RULE_FLAGGED,
        "base_unflagged_rule": RULE_UNFLAGGED,
        "voice_over_rule": RULE_VOICE_OVER,
    }


def _override(rule, reason_code):
    """Copy a base rule record and shut the mouth (Decision 26)."""
    out = dict(rule) if isinstance(rule, dict) else {}
    out["flagged"] = out.get("flagged", True)
    out["check"] = out.get("check", "video")
    out["rule"] = RULE_VOICE_OVER
    out["mouth_movement"] = "forbidden"
    out["voice_over"] = True
    out["source"] = RULE_CITE
    out["voice_over_reason"] = reason_code
    return out


# ------------------------------------------------- selection extension -----

def _load_base():
    """The base V2-08L module when it is in the workspace, else None."""
    try:
        import lip_sync as base
    except ImportError:
        return None
    if not hasattr(base, "select_lines"):
        return None          # namespace placeholder, package not merged yet
    return base


def build_screened_plan(timing, flags, scenes, base=None):
    """Base ``select_lines`` -> narrator screen -> dispatch subset.

    ``base`` is a module-like object exposing ``select_lines(timing, flags)``
    (tests inject a mock; production resolves the real ``lip_sync``).
    Fail closed as BASE_LIPSYNC_UNAVAILABLE when neither is given and the
    base package is not in the workspace.
    """
    base = base if base is not None else _load_base()
    if base is None or not hasattr(base, "select_lines"):
        return _res("error", "BASE_LIPSYNC_UNAVAILABLE",
                    ["base core/lip_sync not importable in %s" % _CORE])
    selection = base.select_lines(timing, flags)
    if not isinstance(selection, dict) or selection.get("outcome") != "ok":
        return selection          # base rejected on its own terms, unchanged
    screened = screen_selection(selection, scenes)
    out = dict(screened)
    out["selection"] = selection
    out["lipsync_selection"] = lipsync_selection(selection, screened)
    if screened.get("outcome") == "ok":
        all_ids = sorted({r.get("line_id") for r in selection["selected"]})
        base_rules = {lid: {
            "line_id": lid, "flagged": True, "check": "video",
            "rule": RULE_FLAGGED, "mouth_movement": "required_matching_sung_words",
            "source": "plan 6.3 QC change",
        } for lid in all_ids}
        out["qc_rules"] = narrator_qc_rules(base_rules, scenes, all_ids)
    return out


def main(argv=None):
    """CLI: screen a selection envelope. Plan only, never dispatches."""
    import argparse
    ap = argparse.ArgumentParser(
        prog="narrator_rule.py",
        description="Decision 26 / plan 6.6: screen a base lip-sync "
                    "selection against the narrator rule. Plan only.")
    ap.add_argument("--selection", required=True,
                    help="base select_lines envelope JSON")
    ap.add_argument("--scenes", required=True,
                    help="line_id -> {speaker, onscreen, stems?} JSON map")
    ap.add_argument("--out", help="write envelope here instead of stdout")
    a = ap.parse_args(argv)
    try:
        selection = json.loads(open(a.selection, encoding="utf-8").read())
        scenes = json.loads(open(a.scenes, encoding="utf-8").read())
        if isinstance(scenes, dict) and isinstance(scenes.get("scenes"), dict):
            scenes = scenes["scenes"]
    except (OSError, ValueError) as exc:
        env = _res("error", "INPUT_UNREADABLE", [str(exc)])
    else:
        env = screen_selection(selection, scenes)
    text = json.dumps(env, indent=2, sort_keys=True)
    if a.out:
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        sys.stdout.write(text + "\n")
    return EXIT.get(env.get("outcome"), 1)


if __name__ == "__main__":
    sys.exit(main())

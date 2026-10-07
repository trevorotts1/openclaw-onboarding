#!/usr/bin/env python3
"""speaker_check.py: shot-list speaker-visibility QC (plan 6.6 + Decision 26).

Rule (plan 6.6, owner decision D17 picture check): the person visible on
screen while a line plays must be the line's speaker -- or the voice's
source (phone / laptop / speaker). Never show one character's face while
another character's voice plays (the 2026-10-07 hybrid test showed Chanel
on screen during the male HR voicemail). Narrator and off-screen voices
play as voice-over over ANY shot, but no visible mouth ever moves to them
(Decision 26, TREVOR 2026-10-07). A lip-synced mouth moves only to that
on-screen character's OWN isolated line: never a narrator's voice, never
another character's voice, never a mixed stem (the 2026-10-07 HIDE test
lip-synced a CTA stem carrying another voice onto Chanel's face).

Wiring into shot-planner QC (all of it inside this package):
  * ``shot_list_qc()`` -- THE shot-planner QC entry: runs
    ``shot_planner.bind_plan`` (14.2/14.3 structural QC) first, then the
    speaker-visibility rules, then emits the qc-schema record. One call.
  * ``to_qc_record()`` -- emits ``check="storyboard"`` for
    ``core/qc_gate.py`` (qc-schema 1.0.0), so a violation FAILS the
    storyboard gate: verdict FAIL -> gate FAIL (CHECK_FAIL).
  * every shot must carry the ``speaker-visibility`` marker in its
    14.2 ``qc_requirements`` ("QC also checks the picture", plan 6.6);
    a plan that never declares the picture check cannot pass QC.
  * ``refuse_before_video_spend()`` -- assembly/spend hook, raises
    SpeakerCheckBlocked on any violation (14.1: storyboard QC before spend).

Division of labour with siblings (never re-implemented here):
  * ``core/qc_voice_match`` scores per-line AUDIO (pitch band, one
    on-screen face via speaker_onscreen_ok);
  * ``core/lip_sync/narrator_rule`` screens one lip-sync attempt's stems
    at the V2-08L dispatch gate;
  * this package scores the whole SHOT LIST at plan time, per shot per
    line, against every voice visible in the window.

stdlib only, no network, no spend, fail-closed (an undeclared shot, a
missing speaker entry or a missing QC marker is a violation, never a pass).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE = os.path.dirname(os.path.dirname(_HERE))       # .../core
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

try:
    # Device/voice-source tokens live in exactly one place (D17).
    from qc_voice_match.qc_voice_match import VOICE_SOURCE_TOKENS
except ImportError as exc:                            # fail closed
    raise ImportError(
        "speaker_check needs the sibling package qc_voice_match in %s"
        % (_CORE,)
    ) from exc

try:
    # Narrator tokens + Decision 26 predicates live in exactly one place.
    from lip_sync.narrator_rule import NARRATOR_TOKENS, is_narrator, \
        is_voice_source
except ImportError as exc:                            # fail closed
    raise ImportError(
        "speaker_check needs the sibling package lip_sync.narrator_rule "
        "in %s" % (_CORE,)
    ) from exc

try:
    import shot_planner as _planner                   # structural QC (14.2/14.3)
except ImportError as exc:                            # fail closed
    raise ImportError(
        "speaker_check needs its own package shot_planner in %s"
        % (_CORE,)
    ) from exc

TOOL_NAME = "speaker_check"
TOOL_VERSION = "0.1.0"
SCHEMA_VERSION = "blackceo.shot-speaker-check/report/v1"
QC_SCHEMA_VERSION = "1.0.0"          # core/qc_gate.py COMPATIBLE
CHECK = "storyboard"                 # qc_gate check family for the shot list
CHECK_ID = "shot-speaker-visibility"
RULE_CITE = "plan 6.6 + Decision 26 (2026-10-07)"

# Every shot declares this picture check in its 14.2 qc_requirements.
QC_REQUIREMENT_MARKER = "speaker-visibility"

SPEAKER_TYPES = frozenset({"character", "narrator", "device"})
GENDERS = frozenset({"female", "male"})
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}


class SpeakerCheckError(Exception):
    """Structural problem in the envelope itself (fail closed, never pass)."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


class SpeakerCheckBlocked(Exception):
    """Raised by refuse_before_video_spend on any violation."""
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _norm(value):
    if isinstance(value, str):
        v = value.strip()
        return v or None
    return None


def classify_speaker(raw, registry=None):
    """Normalize one speaker_map value to {"type", "id", "gender"}.

    A plain string is looked up in the characters registry first (a
    declared character id always wins: the reference host is a CHARACTER
    even though "host" is also a narrator token), then classified through
    the shared token sets: narrator tokens -> narrator, device/
    voice-source tokens -> device, anything else -> character. A dict must
    state its type explicitly. Malformed input raises SpeakerCheckError
    (structural, fail closed).
    """
    if isinstance(raw, str):
        s = _norm(raw)
        if s is None:
            raise SpeakerCheckError("BAD_SPEAKER", "empty speaker value")
        if registry is not None and s in registry:
            return {"type": "character", "id": s, "gender": None}
        low = s.lower()
        if is_narrator(low):
            return {"type": "narrator", "id": low, "gender": None}
        if is_voice_source(low):
            return {"type": "device", "id": low, "gender": None}
        return {"type": "character", "id": s, "gender": None}
    if isinstance(raw, dict):
        t = _norm(raw.get("type"))
        sid = _norm(raw.get("id"))
        if t not in SPEAKER_TYPES or sid is None:
            raise SpeakerCheckError(
                "BAD_SPEAKER",
                "speaker needs type one of %s and a non-empty id"
                % (sorted(SPEAKER_TYPES),))
        g = _norm(raw.get("gender"))
        g = g.lower() if g else None
        if g is not None and g not in GENDERS:
            raise SpeakerCheckError(
                "BAD_SPEAKER", "speaker gender must be one of %s"
                % (sorted(GENDERS),))
        return {"type": t, "id": sid, "gender": g}
    raise SpeakerCheckError("BAD_SPEAKER",
                            "speaker must be a string or an object")


def _fail(code, shot_id=None, line_id=None, detail=""):
    f = {"code": code, "detail": detail}
    if shot_id is not None:
        f["shot_id"] = shot_id
    if line_id is not None:
        f["line_id"] = line_id
    return f


def check_shot_list(env):
    """Pure rule pass over one envelope. Returns (failures, counts).

    Rules, one per acceptance clause (plan 6.6 / Decision 26):
      MISSING_SPEAKER / UNKNOWN_SPEAKER      -- voice identity declared
      VISIBLE_NOT_SPEAKER                    -- wrong face on a character line
      PERSON_ON_DEVICE_LINE                  -- person shown during a device voice
      NARRATOR_LIP_SYNC / DEVICE_LIP_SYNC    -- mouth never moves to those voices
      LIP_SYNC_SPEAKER_NOT_VISIBLE           -- mouth target not on screen
      MIXED_LIP_SYNC_CLIP / CLIP_*           -- isolated single-line clip only
      NARRATOR_GENDER_* / HERO_*             -- narrator matches the hero (6.6)
      QC_REQUIREMENT_MISSING                 -- shot declares the picture check
      VISIBILITY_*                           -- visibility must be declared
    """
    if not isinstance(env, dict):
        raise SpeakerCheckError("BAD_INPUT", "envelope must be an object")
    if env.get("schema_version") != SCHEMA_VERSION:
        raise SpeakerCheckError("BAD_INPUT",
                                "schema_version must be %s" % SCHEMA_VERSION)
    run_id = _norm(env.get("run_id"))
    stage = _norm(env.get("stage"))
    if run_id is None or stage is None:
        raise SpeakerCheckError("BAD_INPUT", "run_id and stage are required")
    shots = env.get("shots")
    if not isinstance(shots, list) or not shots:
        raise SpeakerCheckError("BAD_INPUT", "shots must be a non-empty list")
    chars = env.get("characters")
    if not isinstance(chars, list) or not chars:
        raise SpeakerCheckError("BAD_INPUT",
                                "characters must be a non-empty list")
    registry = {}
    for c in chars:
        if not isinstance(c, dict) or _norm(c.get("id")) is None:
            raise SpeakerCheckError("BAD_INPUT",
                                    "each character needs a non-empty id")
        g = _norm(c.get("gender"))
        g = g.lower() if g else None
        if g is not None and g not in GENDERS:
            raise SpeakerCheckError("BAD_INPUT",
                                    "character gender must be one of %s"
                                    % (sorted(GENDERS),))
        registry[_norm(c["id"])] = g
    smap_raw = env.get("speaker_map")
    if not isinstance(smap_raw, dict) or not smap_raw:
        raise SpeakerCheckError("BAD_INPUT",
                                "speaker_map must be a non-empty object")
    speakers = {}
    for lid, raw in smap_raw.items():
        if _norm(lid) is None:
            raise SpeakerCheckError("BAD_INPUT", "speaker_map keys must be "
                                                "non-empty line ids")
        speakers[lid] = classify_speaker(raw, registry)

    failures = []

    # Narrator identity is checked once, against the hero (plan 6.6:
    # "A narrator's voice matches the hero's gender").
    hero_id = _norm(env.get("hero_id"))
    for lid in sorted(speakers, key=str):
        sp = speakers[lid]
        if sp["type"] != "narrator":
            continue
        if hero_id is None:
            failures.append(_fail(
                "HERO_UNDECLARED", line_id=lid,
                detail="narrator voice on %r but no hero_id; narrator must "
                       "match the hero's gender (%s)" % (lid, RULE_CITE)))
            continue
        if hero_id not in registry:
            failures.append(_fail(
                "HERO_UNDECLARED", line_id=lid,
                detail="hero %r not in characters registry" % hero_id))
            continue
        hero_g = registry[hero_id]
        if sp["gender"] is None:
            failures.append(_fail(
                "NARRATOR_GENDER_MISSING", line_id=lid,
                detail="narrator entry must declare gender (plan 6.6: "
                       "narrator matches hero %r)" % hero_id))
        elif hero_g is None:
            failures.append(_fail(
                "HERO_GENDER_MISSING", line_id=lid,
                detail="hero %r has no gender to match the narrator against"
                       % hero_id))
        elif sp["gender"] != hero_g:
            failures.append(_fail(
                "NARRATOR_GENDER_MISMATCH", line_id=lid,
                detail="narrator gender %s != hero %r gender %s (plan 6.6)"
                       % (sp["gender"], hero_id, hero_g)))

    lines_checked = 0
    for shot in shots:
        if not isinstance(shot, dict):
            raise SpeakerCheckError("BAD_INPUT", "each shot must be an object")
        sid = _norm(shot.get("shot_id")) or "?"
        lids = shot.get("lyric_line_ids")
        if not isinstance(lids, list) or not lids:
            raise SpeakerCheckError("BAD_INPUT",
                                    "shot %s needs non-empty lyric_line_ids"
                                    % sid)

        # 1. the shot itself declares the picture check (plan 6.6 QC).
        reqs = shot.get("qc_requirements")
        if not (isinstance(reqs, list) and any(
                QC_REQUIREMENT_MARKER in str(r).lower() for r in reqs)):
            failures.append(_fail(
                "QC_REQUIREMENT_MISSING", shot_id=sid,
                detail="qc_requirements must carry the %r marker; plan 6.6 "
                       "requires QC to check the picture on every shot"
                       % QC_REQUIREMENT_MARKER))

        # 2. visibility declaration (fail closed: undeclared != empty pass).
        vis = []
        if not isinstance(shot.get("visible_characters"), list):
            failures.append(_fail(
                "VISIBILITY_UNDECLARED", shot_id=sid,
                detail="shot must declare visible_characters (persons on "
                       "screen during the window)"))
        else:
            for v in shot["visible_characters"]:
                if _norm(v) is None:
                    failures.append(_fail(
                        "VISIBILITY_MALFORMED", shot_id=sid,
                        detail="visible_characters entries must be "
                               "non-empty strings"))
                    continue
                vid = _norm(v)
                if vid in registry:
                    if vid not in vis:
                        vis.append(vid)
                else:
                    failures.append(_fail(
                        "VISIBILITY_UNKNOWN_CHAR", shot_id=sid,
                        detail="visible character %r not in characters "
                               "registry" % vid))
        devices = []
        dev_raw = shot.get("visible_devices")
        if dev_raw is None:
            dev_raw = []
        if not isinstance(dev_raw, list):
            raise SpeakerCheckError("BAD_INPUT",
                                    "shot %s visible_devices must be a list"
                                    % sid)
        for d in dev_raw:
            d = _norm(d)
            if d:
                devices.append(d)

        # 3. every line's visible speaker vs the voice (the core rule).
        for lid in lids:
            lines_checked += 1
            sp = speakers.get(lid)
            if sp is None:
                failures.append(_fail(
                    "MISSING_SPEAKER", shot_id=sid, line_id=lid,
                    detail="no speaker_map entry for line %r" % lid))
                continue
            if sp["type"] == "character":
                if sp["id"] not in registry:
                    failures.append(_fail(
                        "UNKNOWN_SPEAKER", shot_id=sid, line_id=lid,
                        detail="speaker %r not in characters registry"
                               % sp["id"]))
                elif vis and sp["id"] not in vis:
                    failures.append(_fail(
                        "VISIBLE_NOT_SPEAKER", shot_id=sid, line_id=lid,
                        detail="on screen [%s] while %r speaks; the person "
                               "visible must be the speaker (%s)"
                               % (", ".join(vis), sp["id"], RULE_CITE)))
            elif sp["type"] == "device":
                if vis:
                    failures.append(_fail(
                        "PERSON_ON_DEVICE_LINE", shot_id=sid, line_id=lid,
                        detail="person(s) [%s] on screen during device voice "
                               "%r; a device line shows the voice source with "
                               "no person (plan 6.6 / Decision 26)"
                               % (", ".join(vis), sp["id"])))
            # narrator: voice-over over ANY shot is legal here; the mouth is
            # policed below (Decision 26).

        # 4. lip-sync declarations (Decision 26).
        ls_raw = shot.get("lip_sync_line_ids")
        if ls_raw is None:
            ls_raw = []
        if not isinstance(ls_raw, list):
            raise SpeakerCheckError("BAD_INPUT",
                                    "shot %s lip_sync_line_ids must be a "
                                    "list" % sid)
        ls_norm = []
        for lid in ls_raw:
            lid = _norm(lid)
            if lid is None:
                raise SpeakerCheckError("BAD_INPUT",
                                        "shot %s lip_sync_line_ids must be "
                                        "non-empty strings" % sid)
            if lid not in lids:
                failures.append(_fail(
                    "LIP_SYNC_UNKNOWN_LINE", shot_id=sid, line_id=lid,
                    detail="lip-synced line is not in this shot's "
                           "lyric_line_ids"))
                continue
            if lid not in ls_norm:
                ls_norm.append(lid)
            sp = speakers.get(lid)
            if sp is None:
                continue                        # MISSING_SPEAKER already filed
            if sp["type"] == "narrator":
                failures.append(_fail(
                    "NARRATOR_LIP_SYNC", shot_id=sid, line_id=lid,
                    detail="a mouth may never move to a narrator voice; "
                           "narrator plays voice-over only (%s)" % RULE_CITE))
            elif sp["type"] == "device":
                failures.append(_fail(
                    "DEVICE_LIP_SYNC", shot_id=sid, line_id=lid,
                    detail="a device voice is never lip-synced onto a face "
                           "(%s)" % RULE_CITE))
            elif sp["id"] not in vis:
                failures.append(_fail(
                    "LIP_SYNC_SPEAKER_NOT_VISIBLE", shot_id=sid, line_id=lid,
                    detail="lip-sync targets %r who is not on screen "
                           "(visible: %s); the mouth only moves to the "
                           "on-screen speaker's own line"
                           % (sp["id"], ", ".join(vis) or "no person")))

        # 5. lip-sync clips: one line, isolated, owned by the on-screen
        #    speaker. Declaring lip_sync_clips (even []) opts into coverage
        #    enforcement here; without the key, stems stay the dispatch
        #    gate's job (lip_sync/narrator_rule), ponytail noted in tests.
        clips = shot.get("lip_sync_clips")
        if clips is None:
            continue
        if not isinstance(clips, list):
            raise SpeakerCheckError("BAD_INPUT",
                                    "shot %s lip_sync_clips must be a list"
                                    % sid)
        covered = set()
        for clip in clips:
            if not isinstance(clip, dict):
                raise SpeakerCheckError("BAD_INPUT",
                                        "shot %s lip-sync clip must be an "
                                        "object" % sid)
            clines = clip.get("line_ids")
            if not (isinstance(clines, list) and len(clines) == 1
                    and _norm(clines[0]) is not None):
                failures.append(_fail(
                    "MIXED_LIP_SYNC_CLIP", shot_id=sid,
                    detail="lip-sync clip must isolate exactly one line, got "
                           "%r; a stem carrying another voice is refused "
                           "(2026-10-07 HIDE test)" % (clines,)))
                continue
            lid = _norm(clines[0])
            if lid not in ls_norm:
                failures.append(_fail(
                    "CLIP_LINE_NOT_LIP_SYNCED", shot_id=sid, line_id=lid,
                    detail="clip provided for a line this shot does not "
                           "lip-sync"))
                continue
            covered.add(lid)
            sp = speakers.get(lid)
            if sp is None or sp["type"] != "character":
                continue                        # narrator/device filed above
            clip_spk = _norm(clip.get("speaker"))
            if clip_spk is None:
                failures.append(_fail(
                    "CLIP_SPEAKER_MISSING", shot_id=sid, line_id=lid,
                    detail="lip-sync clip must name its speaker"))
            elif clip_spk != sp["id"]:
                failures.append(_fail(
                    "CLIP_SPEAKER_MISMATCH", shot_id=sid, line_id=lid,
                    detail="clip speaker %r != line speaker %r; the mouth "
                           "only moves to the on-screen speaker's own voice"
                           % (clip_spk, sp["id"])))
        for lid in ls_norm:
            if lid not in covered:
                failures.append(_fail(
                    "CLIP_MISSING", shot_id=sid, line_id=lid,
                    detail="lip-synced line has no isolated clip in "
                           "lip_sync_clips"))

    failures.sort(key=lambda f: (str(f.get("shot_id", "")),
                                 str(f.get("line_id", "")), f["code"]))
    return failures, {"shots_checked": len(shots),
                      "lines_checked": lines_checked}


def evaluate(env):
    """Full shot-list verdict. Structural problems raise SpeakerCheckError."""
    failures, counts = check_shot_list(env)
    codes = sorted({f["code"] for f in failures})
    return {
        "schema_version": SCHEMA_VERSION,
        "tool": TOOL_NAME,
        "tool_version": TOOL_VERSION,
        "command": "check",
        "run_id": _norm(env.get("run_id")),
        "stage": _norm(env.get("stage")),
        "outcome": "ok" if not failures else "rejected",
        "reason_code": "SPEAKER_VISIBILITY_OK" if not failures
                       else "+".join(codes),
        "next_action": "shot list may proceed to storyboard approval"
                       if not failures else
                       "repair the shot plan (visible speaker, device/"
                       "narrator/lip-sync rules, QC marker) and re-run "
                       "shot-list QC; storyboard approval stays blocked",
        "evidence": {
            "rule": RULE_CITE,
            "qc_requirement_marker": QC_REQUIREMENT_MARKER,
            "shots_checked": counts["shots_checked"],
            "lines_checked": counts["lines_checked"],
            "violations": len(failures),
            "failures": failures,
        },
    }


def to_qc_record(result, reviewer, check_id=None, checker_version=None):
    """qc-schema 1.0.0 verdict record (check=storyboard) for core/qc_gate.py.

    reviewer must carry identity/session/authority and must differ from the
    maker of the plan (qc_gate enforces independence; a PASS from the maker
    of the records is not evidence).
    """
    if not isinstance(result, dict) or result.get("outcome") \
            not in ("ok", "rejected"):
        raise SpeakerCheckError("BAD_INPUT",
                                "result must be an evaluate() result")
    run_id = _norm(result.get("run_id"))
    stage = _norm(result.get("stage"))
    if run_id is None or stage is None:
        raise SpeakerCheckError("BAD_INPUT", "result run_id/stage required")
    if not isinstance(reviewer, dict):
        raise SpeakerCheckError("BAD_INPUT", "reviewer must be an object")
    rev = {}
    for key in ("identity", "session", "authority"):
        v = _norm(reviewer.get(key))
        if v is None:
            raise SpeakerCheckError("BAD_INPUT",
                                    "reviewer.%s is required" % key)
        rev[key] = v
    failures = result["evidence"]["failures"]
    codes = sorted({f["code"] for f in failures})
    return {
        "schema_version": QC_SCHEMA_VERSION,
        "check_id": check_id or CHECK_ID,
        "run_id": run_id,
        "stage": stage,
        "check": CHECK,
        "verdict": "PASS" if result["outcome"] == "ok" else "FAIL",
        "evidence": {
            "summary": "speaker-visibility %s: %d shot(s), %d line(s), "
                       "%d violation(s)%s"
                       % (result["outcome"],
                          result["evidence"]["shots_checked"],
                          result["evidence"]["lines_checked"],
                          len(failures),
                          "" if not failures else
                          " [%s]" % ", ".join(codes)),
            "refs": [],
        },
        "reason_code": result["reason_code"],
        "checker_version": checker_version or TOOL_VERSION,
        "reviewer": rev,
    }


def shot_list_qc(env, timing=None, contracts=None, prompts=None,
                 reviewer=None):
    """Shot-planner QC entry: structural bind first, then speaker rules.

    timing given  -> shot_planner.bind_plan (14.2/14.3, raises PlanError on
                     an unbound line, bad window, missing contract, bad prompt)
    timing omitted -> speaker rules only (planner state recorded as skipped)
    Always returns {"planner", "result", "record"}; the record is what the
    storyboard gate consumes, and its verdict is FAIL whenever any line's
    visible speaker breaks the voice/device/narrator rules.
    """
    if not isinstance(env, dict):
        raise SpeakerCheckError("BAD_INPUT", "envelope must be an object")
    if timing is not None:
        shots = env.get("shots")
        if not isinstance(shots, list) or not shots:
            raise SpeakerCheckError("BAD_INPUT",
                                    "envelope needs shots before bind")
        _planner.bind_plan(shots, timing, contracts, prompts)
        planner_state = {"outcome": "bound", "reason_code": "plan-bound"}
    else:
        planner_state = {"outcome": "skipped", "reason_code": "no-timing"}
    result = evaluate(env)
    default_reviewer = {
        "identity": "speaker_check/%s" % TOOL_VERSION,
        "session": "shot-list-qc",
        "authority": RULE_CITE,
    }
    record = to_qc_record(result, reviewer or default_reviewer)
    return {"planner": planner_state, "result": result, "record": record}


def refuse_before_video_spend(result):
    """Spend hook (14.1): raise SpeakerCheckBlocked unless QC passed."""
    if not isinstance(result, dict) or result.get("outcome") != "ok":
        code = result.get("reason_code", "SPEAKER_VISIBILITY_FAIL") \
            if isinstance(result, dict) else "SPEAKER_VISIBILITY_FAIL"
        raise SpeakerCheckBlocked(code)
    return True


# ------------------------------------------------------------------ CLI ----

def main(argv=None):
    p = argparse.ArgumentParser(
        prog="speaker_check",
        description="shot-list speaker-visibility QC (plan 6.6 + Decision 26; "
                    "fail-closed, runs before storyboard approval)")
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("check", help="evaluate a shot-list envelope")
    a.add_argument("--env", required=True, help="envelope JSON path")
    a.add_argument("--timing", default="",
                   help="optional 12.4 timing map: runs bind_plan first")
    a.add_argument("--qc-record", default="",
                   help="also write the qc-schema storyboard verdict here")
    a.add_argument("--reviewer-identity", default="speaker_check/%s"
                   % TOOL_VERSION)
    a.add_argument("--reviewer-session", default="shot-list-qc")
    a.add_argument("--reviewer-authority", default=RULE_CITE)
    ns = p.parse_args(argv)
    try:
        with open(ns.env, encoding="utf-8") as f:
            env = json.load(f)
        timing = None
        if ns.timing:
            with open(ns.timing, encoding="utf-8") as f:
                timing = json.load(f)
        out = shot_list_qc(env, timing=timing, reviewer={
            "identity": ns.reviewer_identity,
            "session": ns.reviewer_session,
            "authority": ns.reviewer_authority,
        })
        if ns.qc_record:
            with open(ns.qc_record, "w", encoding="utf-8") as f:
                json.dump(out["record"], f, indent=2, sort_keys=True)
                f.write("\n")
        print(json.dumps(out["result"], indent=2, sort_keys=True))
        return EXIT["ok"] if out["result"]["outcome"] == "ok" \
            else EXIT["rejected"]
    except SpeakerCheckError as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                          "command": "check", "outcome": "error",
                          "reason_code": e.code,
                          "evidence": {"detail": str(e)}},
                         indent=2, sort_keys=True))
        return EXIT["error"]
    except _planner.PlanError as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                          "command": "check", "outcome": "error",
                          "reason_code": e.code,
                          "evidence": {"detail": str(e)}},
                         indent=2, sort_keys=True))
        return EXIT["error"]
    except (OSError, ValueError) as e:
        print(json.dumps({"schema_version": SCHEMA_VERSION,
                          "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                          "command": "check", "outcome": "error",
                          "reason_code": "IO_ERROR",
                          "evidence": {"detail": str(e)}},
                         indent=2, sort_keys=True))
        return EXIT["error"]


if __name__ == "__main__":
    sys.exit(main())

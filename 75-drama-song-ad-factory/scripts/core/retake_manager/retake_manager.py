#!/usr/bin/env python3
"""Retake manager: retake only the failed artifact and its real dependents.

Directive sections 24.5 (enforced handoffs, bounded work, targeted repair)
+ 18 rule 6 + 17.8 (acceptance profile repair caps + verdict values).
Stdlib only. No network, no secrets.

F1/F2 note (owner order 2026-10-08): for the Suno soundtrack, retakes are
WHOLE-TRACK only in F1 mode -- one full-track re-generation per failed take,
never a slice, a patch, or a spoken-take redo. ``core/audio_c3/soundtrack.py``
refuses anything else (``PARTIAL_SUNO_JOB``), and the dispatcher refuses such
a job at intake before any ledger row.

Contract:
- Every repair gets its own attempt ID and refers to the failed
  artifact/check. Retry limits persist across restarts: the caller passes the
  durable attempt history (a JSON list of prior retake records); nothing is
  kept in process memory.
- Retry bounds come from the acceptance profile (17.8): the profile may name
  a repair cap (nested under any key containing "repair" or "retry"); when
  the profile carries none, DEFAULT_REPAIR_CAP holds (marked
  profile_unspecified).
- Retake-only-failed-artifact: the plan lists exactly the failed artifact +
  its listed real dependents. Approved assets are never touched: dependents
  that name an artifact with an accepted (PASS) record are excluded with a
  reason; shots not in the dependent graph are never regenerated.
- Failed dependents fail with the retake only when their listed prerequisite
  is the failed artifact (chain retakes); a dependent on a passing artifact
  is untouched.
- Repair isolation: one bad shot never regenerates sibling shots. Shots list
  any number of artifact IDs; the plan emits entries ONLY for failed ones.
- Exit-per-artifact verdicts use the acceptance-profile vocabulary:
  FAIL / PASS / UNAVAILABLE. UNVERIFIED prerequisites park, never pass.

Exit codes (EXIT): ok 0 (plan with items or empty plan), error 1,
waiting 3, parked 4, rejected 5 (invalid input / cap exhausted).
Output: single JSON object on stdout.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path

# G4 call path: the band comes from core/target_engine (which reads the
# G10 numbers in core/spoken_share) -- never a second band in this file.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import target_engine  # noqa: E402

TOOL_NAME = "retake_manager"
TOOL_VERSION = "1.0.0"
EXIT = {"ok": 0, "error": 1, "waiting": 3, "parked": 4, "rejected": 5}

# ponytail: fixed ceiling until acceptance-profile.json names repair caps;
# upgrade path: read cap from the published versioned profile per run.
DEFAULT_REPAIR_CAP = 2

# F-CG-6 (S01 rule 6 owns the policy; this is the code): per-class retake caps.
# A defect class past its cap keeps the best take and flags RETAKE_OVER_BUDGET
# -- it is never retried. The profile may override any class in a
# ``retake_budgets`` map; the defaults below hold otherwise.
RETAKE_OVER_BUDGET = "RETAKE_OVER_BUDGET"
DEFAULT_CLASS_CAPS = {
    "faces": 1,
    "painted_letters": 1,
    "cuts": 2,
    "eyeball_faults": 1,
    "burned_text": 1,
}
_CLASS_ALIASES = {
    "face": "faces", "faces": "faces", "identity": "faces",
    "letters": "painted_letters", "painted_letters": "painted_letters",
    "painted-letters": "painted_letters", "text_letters": "painted_letters",
    "cut": "cuts", "cuts": "cuts", "edit": "cuts",
    "eyeball": "eyeball_faults", "eyeball_faults": "eyeball_faults",
    "eyeball-faults": "eyeball_faults",
    "burned_text": "burned_text", "burned-text": "burned_text",
    "burned_in_text": "burned_text", "text": "burned_text",
}

# Profile ships beside this package: core/ in the build tree, scripts/core/ in
# a skill install. Absolute operator-box paths cannot ship (QC static guard).
DEFAULT_PROFILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "acceptance-profile.json")

VERDICTS = ("FAIL", "PASS", "UNAVAILABLE")


def _reject(code, reason):
    """Owner order 2026-11-20: a rejection the client may see carries the
    four-part client explanation beside the code (loud_failure.explain_stop).
    Read-only; never changes the stop."""
    env = {"outcome": "rejected", "code": code, "reason": reason,
           "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import loud_failure  # noqa: E402
        env["client_explanation"] = loud_failure.explain_stop(
            code, None, {"reason_code": code, "detail": reason,
                         "next_action": ""})
    except Exception:  # noqa: BLE001 - the explanation never breaks a stop
        pass
    return env


def _stop(code, reason, outcome="rejected", extra=None, facts=None):
    """Non-ok retake envelope with the four-part client explanation beside
    the code. Read-only; never changes the stop."""
    env = {"outcome": outcome, "code": code, "reason": reason,
           "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    if extra:
        env.update(extra)
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        import loud_failure  # noqa: E402
        env["client_explanation"] = loud_failure.explain_stop(
            code, facts, dict(env, reason_code=code, detail=reason))
    except Exception:  # noqa: BLE001 - the explanation never breaks a stop
        pass
    return env


def load_profile(path):
    """(profile, repair_cap, cap_source, error): read acceptance profile."""
    if path is None:
        return {}, DEFAULT_REPAIR_CAP, "default", None
    p = Path(os.path.expanduser(str(path)))
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as exc:
        return None, None, None, (
            "acceptance profile not readable at %s (%s)"
            % (p, exc.strerror or exc))
    except ValueError as exc:
        return None, None, None, (
            "acceptance profile at %s is not valid JSON: %s" % (p, exc))
    if not isinstance(data, dict):
        return None, None, None, (
            "acceptance profile at %s is not a JSON object" % p)
    cap, source = _find_repair_cap(data)
    return data, cap, source, None


def _find_repair_cap(node):
    """(cap, source): repair cap from profile; None when the profile is silent."""
    if isinstance(node, dict):
        for key, value in node.items():
            lowered = str(key).lower()
            if ("repair" in lowered or "retry" in lowered) and (
                    "cap" in lowered or "max" in lowered or "limit" in lowered):
                if isinstance(value, int) and not isinstance(value, bool) \
                        and value >= 0:
                    return value, "profile"
        for value in node.values():
            found, source = _find_repair_cap(value)
            if found is not None:
                return found, source
    elif isinstance(node, list):
        for item in node:
            found, source = _find_repair_cap(item)
            if found is not None:
                return found, source
    return None, None


def _resolve_defect_class(value):
    """Map a defect-class name to its canonical key, or None when unknown."""
    if not isinstance(value, str) or not value.strip():
        return None
    return _CLASS_ALIASES.get(value.strip().lower().replace(" ", "_"))


def class_caps(profile=None):
    """Per-class retake caps (F-CG-6). Profile ``retake_budgets`` overrides a
    class; anything absent keeps its default. Unknown classes are ignored, so a
    typo never silently lowers a cap."""
    caps = dict(DEFAULT_CLASS_CAPS)
    budgets = profile.get("retake_budgets") if isinstance(profile, dict) else None
    if isinstance(budgets, dict):
        for key, value in budgets.items():
            cls = _resolve_defect_class(key)
            if cls is not None and isinstance(value, int) \
                    and not isinstance(value, bool) and value >= 0:
                caps[cls] = value
    return caps


# ---------------------------------------------------------------------------
# G-LIP-02: no motion-for-lip swap that kills scripted body beats.
LIP_SWAP_KILLS_BODY = "LIP_SWAP_KILLS_BODY_BEAT"


def check_lip_swap(swap, base):
    """Refuse a lip-swap take whose body-beat score drops below the base take
    it replaces (G-LIP-02).

    ``swap``/``base``: {"body_beat_score": number}. A take that buys a mouth by
    freezing the body is refused; the repair path is a two-track take (body
    motion preserved plus the face lip) or a reshoot briefed with both, never a
    frozen mouth-only swap. A swap that keeps or raises the score passes.
    """
    if not isinstance(swap, dict) or not isinstance(base, dict):
        return _reject("INVALID_REQUEST",
                       "lip_swap and base must be records with body_beat_score")
    cur = swap.get("body_beat_score")
    was = base.get("body_beat_score")
    if not (isinstance(cur, (int, float)) and not isinstance(cur, bool)
            and isinstance(was, (int, float)) and not isinstance(was, bool)):
        return _reject("INVALID_REQUEST",
                       "body_beat_score must be a number on both takes")
    if cur + 1e-9 < was:
        return {
            "outcome": "rejected", "code": LIP_SWAP_KILLS_BODY,
            "reason": ("lip-swap take keeps %.3f of the base take's %.3f body "
                       "beats; a frozen mouth-only swap loses the beat the "
                       "script asked for" % (cur, was)),
            "repair": [
                "two-track take: body motion preserved, face lip added",
                "reshoot briefed with the body beat and the lip together",
            ],
            "never": "frozen mouth-only swap",
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
            "recovery": "use the two-track take or a combined reshoot brief",
        }
    return {"pass": True, "reason_code": "LIP_SWAP_KEEPS_BODY",
            "swap": cur, "base": was}


# ---------------------------------------------------------------------------
# G-MOTION-02: ensemble shots enter the retake planner.
ENSEMBLE_MIN_CAST = 5           # "more than 4 cast members"
ENSEMBLE_CROWD_COMPLAINTS = frozenset({
    "crowd_motion", "crowd-motion", "unnatural_choir_movement",
    "unnatural-choir-movement", "choir_movement", "ensemble_motion",
    "ensemble-motion",
})


def plan_ensemble_rows(shots):
    """G-MOTION-02: a shot with more than 4 cast members and a crowd-motion
    complaint gets a retake row even when it is in neither the H3 nor the
    lip-sync retake list. The fix is direction-only on H3: one steady action
    such as a gentle sway plus one clap on beat, the floor singers held or
    removed. Returns the rows (empty when nothing qualifies)."""
    if not isinstance(shots, list):
        raise ValueError("ensemble_shots must be a list of shot records")
    rows = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        cast = shot.get("cast_count")
        complaint = str(shot.get("complaint")
                        or shot.get("motion_complaint") or "").strip().lower()
        if isinstance(cast, int) and not isinstance(cast, bool) \
                and cast >= ENSEMBLE_MIN_CAST \
                and complaint.replace(" ", "_") in ENSEMBLE_CROWD_COMPLAINTS:
            rows.append({
                "shot_id": shot.get("shot_id"),
                "kind": "ensemble_direction_only",
                "model": "minimax-h3/image-to-video",
                "direction": ("one steady action such as a gentle sway plus "
                              "one clap on beat; floor singers held or removed"),
                "reason": ("more than %d cast members with a crowd-motion "
                           "complaint" % (ENSEMBLE_MIN_CAST - 1)),
            })
    return rows


# ---------------------------------------------------------------------------
# N-31: "keep a usable take" is void after a change of look, bible or route.
KEEP_VOID_AFTER_CHANGE = "KEEP_VOID_AFTER_CHANGE"


def stale_takes(takes, current):
    """N-31: every take made under an older look, character bible or route is
    listed for remake; "keep a usable take" never applies to it.

    ``takes``: {artifact_id: {"look_version","bible_version","route_version"}}.
    ``current``: the run's current {"look_version","bible_version","route_version"}.
    Returns the list of stale artifact ids (empty when every take is current).
    """
    if not isinstance(takes, dict) or not isinstance(current, dict):
        return []
    keys = ("look_version", "bible_version", "route_version")
    stale = []
    for artifact_id, made in takes.items():
        if not isinstance(made, dict):
            stale.append(artifact_id)
            continue
        for key in keys:
            if key in current and made.get(key) != current.get(key):
                stale.append(artifact_id)
                break
    return stale


# ---------------------------------------------------------------------------
# N-44: fixes go back through the steps (3C.6).
FIX_NOT_FROM_REFERENCES = "FIX_NOT_FROM_REFERENCES"
STEP_2 = "step_2_keyframe_from_locked_references"


def plan_fix_start(artifact_id, made):
    """N-44: every replacement starts at step 2 from the locked references.

    ``made``: {"shot_id","run_id","look_version"} of the clip being replaced.
    Returns the repair plan; refuses to select another shot's, run's or
    version's clip as the source. The retake planner offers no other repair.
    """
    if not isinstance(made, dict) or not made.get("shot_id"):
        return {"outcome": "rejected", "code": FIX_NOT_FROM_REFERENCES,
                "reason": "replacement must name the shot it belongs to",
                "recovery": "start at step 2 from this shot's locked references",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    return {
        "outcome": "ok", "artifact_id": artifact_id,
        "start_at": STEP_2,
        "from": {"character_refs": "locked", "location_refs": "locked",
                 "look_lock": made.get("look_version")},
        "forbidden_sources": ["another shot's clip", "another run's clip",
                              "another look version's clip"],
        "then": ["step_3_story_clip", "step_4_lip_sync_if_lip"],
        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
    }


# ---------------------------------------------------------------------------
# N-122 (Bible Guard, part 3): escalation, never a person asked while a fix is
# still available.
RETAKE_ESCALATE = "RETAKE_ESCALATE"
BIBLE_RECHECK_REQUIRED = "BIBLE_RECHECK_REQUIRED"
ESCALATE_AFTER_TRIES = 2
BIBLE_RECHECK_AFTER_SHOTS = 3


def escalate(failures):
    """N-122 part 3: after the second try the shot escalates with both takes,
    and the same person or place failing in 3 or more shots stops shot-by-shot
    remaking -- the bible entry is rechecked and remade if it is the cause.

    ``failures``: [{"artifact_id","subject","subject_kind",
    "tries","takes":[...]}]. ``subject`` is the character id or place id.
    """
    escalations, per = [], {}
    for f in failures if isinstance(failures, list) else []:
        if not isinstance(f, dict):
            continue
        subject = f.get("subject")
        kind = f.get("subject_kind") or "person"
        if subject:
            per[(kind, subject)] = per.get((kind, subject), 0) + 1
        tries = f.get("tries")
        if isinstance(tries, int) and not isinstance(tries, bool) \
                and tries >= ESCALATE_AFTER_TRIES:
            escalations.append({
                "artifact_id": f.get("artifact_id"), "code": RETAKE_ESCALATE,
                "subject": subject, "subject_kind": kind,
                "both_takes": f.get("takes") or [],
                "reason": "still failing after %d tries; goes to the run owner "
                          "with both takes and the reference it failed against"
                          % tries,
            })
    bible = [{"subject": subject, "subject_kind": kind, "shots": shots,
              "code": BIBLE_RECHECK_REQUIRED,
              "reason": "failing in %d shots; recheck the bible entry against "
                        "its own master before remaking again" % shots}
             for (kind, subject), shots in per.items()
             if shots >= BIBLE_RECHECK_AFTER_SHOTS]
    return {"outcome": "ok", "escalate": escalations,
            "bible_recheck": bible,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION}


# ---------------------------------------------------------------------------
# N-04 / N-20: a new clip beats a patch, and a remake only makes the
# storyboard's own action bigger.
REMAKE_NOT_FROM_PICTURE = "REMAKE_NOT_FROM_PICTURE"
REMAKE_INVENTS_ACTION = "REMAKE_INVENTS_ACTION"


def check_remake(replacement):
    """N-04: the repair for a failed shot is a remake from the locked picture in
    the one remake blast -- never a patch (crop, zoom, freeze, hand-join).
    N-20: a remake may only make the storyboard's own action bigger; a new prop
    action is refused.

    ``replacement``: {"from": "locked_picture"|"patch"|..., "action":
    <storyboard action>, "new_action": <what the remake asks for>, plus
    optional "extra_prop_action": True}.
    """
    if not isinstance(replacement, dict):
        return _reject("INVALID_REQUEST", "replacement must be a record")
    frm = str(replacement.get("from") or "").strip().lower()
    if frm != "locked_picture":
        return {"outcome": "rejected", "code": REMAKE_NOT_FROM_PICTURE,
                "reason": ("the repair is a remake from the locked picture, "
                           "not a %r patch; a new clip beats a patch"
                           % (frm or "unknown")),
                "recovery": "remake the shot from its locked picture in the "
                            "one remake blast",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    if replacement.get("extra_prop_action") is True:
        return {"outcome": "rejected", "code": REMAKE_INVENTS_ACTION,
                "reason": ("a remake may only make the storyboard's own action "
                           "bigger; a new prop action is not a repair"),
                "recovery": "enlarge the storyboard action, add no new prop act",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    return {"outcome": "ok", "reason_code": "REMAKE_OK",
            "blast": "one_remake_blast", "from": frm,
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION}


def check_action_scope(storyboard_actions, remake_action_ids):
    """N-20: a remake only makes the storyboard's own action bigger.

    ``storyboard_actions``: the shot's own action ids; ``remake_action_ids``:
    the actions the remake asks for. Any remake action that is not one of the
    storyboard's own is a new invention and is refused.
    """
    own = {str(a) for a in (storyboard_actions or [])}
    asked = [str(a) for a in (remake_action_ids or [])]
    invented = [a for a in asked if a not in own]
    if invented:
        return {"outcome": "rejected", "code": REMAKE_INVENTS_ACTION,
                "reason": ("remake asks for action(s) %s the storyboard does "
                           "not carry; a remake enlarges the storyboard's own "
                           "action and invents nothing" % ", ".join(invented)),
                "invented": invented,
                "recovery": "drop the invented action or enlarge a storyboard "
                            "action instead",
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION}
    return {"outcome": "ok", "reason_code": "REMAKE_ACTION_IN_SCOPE",
            "tool": TOOL_NAME, "tool_version": TOOL_VERSION}


def _prior_attempts(history):
    """(counts, errors): per-artifact prior attempt counts from durable history."""
    counts = {}
    if history is None:
        return counts, []
    if not isinstance(history, list):
        return None, ["attempt_history must be a JSON list of retake records"]
    for index, record in enumerate(history):
        if not isinstance(record, dict):
            return None, ["attempt_history[%d] must be an object" % index]
        artifacts = record.get("artifacts")
        if artifacts is None and "artifact_id" in record:
            artifacts = [record["artifact_id"]]
        if not isinstance(artifacts, list) or not artifacts:
            return None, [
                "attempt_history[%d] must name artifacts (list) or "
                "artifact_id" % index]
        for artifact_id in artifacts:
            if not isinstance(artifact_id, str) or not artifact_id:
                return None, [
                    "attempt_history[%d] artifact IDs must be non-empty "
                    "strings" % index]
            counts[artifact_id] = counts.get(artifact_id, 0) + 1
    return counts, []


def plan(req, profile_path=None):
    """Plan one targeted retake. Returns the JSON envelope (see module doc)."""
    if not isinstance(req, dict):
        return _reject("INVALID_REQUEST", "request must be a JSON object")
    errors = []
    failed = req.get("failed_artifact_id")
    if not isinstance(failed, str) or not failed:
        errors.append("failed_artifact_id must be a non-empty string")
    check = req.get("check")
    if not isinstance(check, str) or not check:
        errors.append("check must name the failed artifact/check (non-empty)")
    shots = req.get("shots")
    if not isinstance(shots, list) or not shots:
        errors.append("shots must be a non-empty list of artifact IDs")
    elif any(not isinstance(s, str) or not s for s in shots):
        errors.append("shots must be non-empty strings")
    dependents = req.get("dependents", {})
    if not isinstance(dependents, dict):
        errors.append("dependents must be a map artifact_id -> [prereqs]")
    else:
        for key, prereqs in dependents.items():
            if not isinstance(prereqs, list) or any(
                    not isinstance(p, str) for p in prereqs):
                errors.append(
                    "dependents[%r] must be a list of artifact-ID strings"
                    % key)
    accepted = req.get("accepted", [])
    if not isinstance(accepted, list) or any(
            not isinstance(a, str) for a in accepted):
        errors.append("accepted must be a list of artifact-ID strings")
    states = req.get("artifact_states", {})
    if not isinstance(states, dict):
        errors.append("artifact_states must be a map artifact_id -> verdict")
    else:
        for key, verdict in states.items():
            if verdict not in VERDICTS:
                errors.append(
                    "artifact_states[%r] must be one of %s" % (key, VERDICTS))
    history = req.get("attempt_history")
    counts, history_errors = _prior_attempts(history)
    errors.extend(history_errors)
    reason = req.get("reason")
    if reason is not None and (not isinstance(reason, str) or not reason):
        errors.append("reason must be a non-empty string when present")
    gap = req.get("target_gap_pts")
    if gap is not None and (isinstance(gap, bool)
                            or not isinstance(gap, (int, float))):
        errors.append("target_gap_pts must be a number (percentage points)")
    if errors:
        return _reject("INVALID_REQUEST", "; ".join(errors))

    # G4 band gate: a measured target miss only warrants a retake past
    # FLAG_PTS. Within 5 points the take is accepted; 5-10 is accepted
    # with a flag in the receipt -- neither is redone (order 1240 item 3).
    if gap is not None:
        band = target_engine.band_for_gap(abs(float(gap)))
        if band != target_engine.BAND_REDO:
            # Round 2 finding 2: TARGET_IN_BAND carries the four-part message
            # beside the reason (the in-band take is kept, never redone).
            return _stop(
                "TARGET_IN_BAND",
                ("target gap %.4g points is %s (band: within %d "
                 "points accept, %d-%d accept with a flag, past %d "
                 "redo); no retake for an in-band take"
                 % (abs(float(gap)), band,
                    target_engine.ACCEPT_PTS,
                    target_engine.ACCEPT_PTS,
                    target_engine.FLAG_PTS,
                    target_engine.FLAG_PTS)),
                extra={"band": band},
                facts={"gap": abs(float(gap)), "band": band,
                       "accept": target_engine.ACCEPT_PTS,
                       "flag": target_engine.FLAG_PTS})

    prof_path = (profile_path or req.get("profile")
                 or os.environ.get("ACCEPTANCE_PROFILE_JSON")
                 or DEFAULT_PROFILE)
    profile, cap, cap_source, profile_error = load_profile(prof_path)
    if profile_error:
        # Round 2 finding 2: the missing profile is a client-facing stop, so
        # it carries the four-part message beside the reason.
        return _stop("PROFILE_UNAVAILABLE", profile_error,
                     outcome="error",
                     extra={"recovery": "publish the versioned "
                                        "acceptance-profile.json before "
                                        "generation (directive 17.8)"})
    if cap is None:
        cap, cap_source = DEFAULT_REPAIR_CAP, "default"
    profile_version = profile.get("profile_version", "unspecified")

    # G-LIP-02: a lip-swap take never buys a mouth by killing body beats.
    if req.get("lip_swap") is not None:
        verdict = check_lip_swap(req.get("lip_swap"),
                                 req.get("base_take") or {})
        if verdict.get("pass") is not True:
            return verdict

    # N-04 / N-20: a new clip beats a patch, and a remake invents no new action.
    if req.get("replacement") is not None:
        remake = check_remake(req.get("replacement"))
        if remake.get("outcome") != "ok":
            return remake
    if req.get("remake_action_ids") is not None:
        scope = check_action_scope(req.get("storyboard_actions") or [],
                                   req.get("remake_action_ids") or [])
        if scope.get("outcome") != "ok":
            return scope

    accepted_set = set(accepted)
    # N-31: a take made under an older look, bible or route is never "usable";
    # it is listed for remake even when it looks fine.
    stale = set(stale_takes(req.get("takes_by_version") or {},
                            req.get("current_versions") or {}))
    failed_states = {k for k, v in states.items() if v == "FAIL"}
    if failed not in shots:
        return _reject(
            "UNKNOWN_ARTIFACT",
            "failed_artifact_id %r is not in shots %r" % (failed, shots))
    if failed in accepted_set:
        return _reject(
            "ACCEPTED_ARTIFACT",
            "failed_artifact_id %r carries an accepted (PASS) record; "
            "retakes never regenerate approved assets" % failed)
    if states.get(failed) == "PASS":
        return _reject(
            "ACCEPTED_ARTIFACT",
            "failed_artifact_id %r has artifact_states PASS; do not "
            "regenerate approved assets" % failed)

    # Target set: failed artifact + real dependents whose prereqs include it
    # (transitively), minus anything accepted. Siblings are never included.
    blocked = []
    targets = [failed]
    queue = [failed]
    seen = {failed}
    while queue:
        current = queue.pop(0)
        for artifact_id, prereqs in dependents.items():
            if artifact_id in seen or current not in prereqs:
                continue
            if artifact_id in accepted_set or states.get(artifact_id) == "PASS":
                blocked.append({
                    "artifact_id": artifact_id,
                    "excluded": True,
                    "reason": "accepted (PASS) record exists; approved assets "
                              "are never regenerated",
                })
                continue
            seen.add(artifact_id)
            targets.append(artifact_id)
            queue.append(artifact_id)

    # Repair bounds: per-artifact attempt counts from durable history.
    # Lock 5: one lone drip (single target, cap 1 pass each) refuses
    # RETAKE_DRIP — remakes go back in ONE blast, never one by one.
    # Lock 1: identical-template retries past the cap raise
    # TEMPLATE_FAIL_LOCK with the prompt-change order.
    drip = req.get("drip") or (len(targets) == 1
                               and int(req.get("passes_used") or 1) > 1
                               and int(req.get("ready_count") or 1) > 1)
    if drip:
        import never_again as _na
        return {"outcome": "rejected", "code": _na.RETAKE_DRIP,
                "reason": "drip submit refused: %d ready jobs belong in one "
                          "blast up to the rate limit, never one by one"
                          % int(req.get("ready_count") or len(targets)),
                "targets": targets, "attempt_counts": dict(counts),
                "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                "recovery": "resubmit all ready jobs in ONE blast"}
    # Lock 8 (F-KLING-ROUTE, as revised by S-42/3C.1a): the lip-sync model
    # (omnihuman-2-0, the only one) rides ONLY lip_sync:true shots (talking or
    # singing). Caller passes shot lip_sync state as
    # req["lip_sync_by_artifact"] {id: bool} and the retake model as
    # req["retake_model"]; the locked lip-sync model
    # (kie_dispatch/model_lock.is_locked_lipsync) on a non-lip-sync shot
    # refuses ROUTE_CHANGED -- re-plan as an H3 remake.
    _lip_sync_map = req.get("lip_sync_by_artifact") or {}
    _retake_model = req.get("retake_model") or ""
    try:
        from kie_dispatch.model_lock import is_locked_lipsync as _is_lipsync
    except ImportError:
        try:
            from model_lock import is_locked_lipsync as _is_lipsync  # type: ignore
        except ImportError:
            _is_lipsync = None
    if _is_lipsync is not None and _is_lipsync(_retake_model):
        import never_again as _na
        for _a in targets:
            if not _lip_sync_map.get(_a, False):
                return {"outcome": "rejected", "code": _na.ROUTE_CHANGED,
                        "reason": ("the lip-sync model (omnihuman-2-0) is "
                                   "allowed ONLY on lip_sync:true shots "
                                   "(talking or singing); %r is not "
                                   "lip-sync -- re-plan as an H3 remake"
                                   % _a),
                        "targets": targets, "attempt_counts": dict(counts),
                        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                        "recovery": "re-plan %r as an H3 remake" % _a}
    # Lock 10 (F-MODEL-AUTH, Trevor order 2026-11-21): req["retake_model"]
    # must be in never_again.AUTHORIZED_DISPATCH_MODELS or every target
    # needs a Trevor written order binding that model + shot
    # (req["model_auth_order"]); else MODEL_UNAUTHORIZED before cap math.
    _auth_model = req.get("retake_model")
    if _auth_model:
        import never_again as _na
        _auth_hit = _na.check_model_authorized(_auth_model)
        _unbound = [a for a in targets if not _na.check_model_order(
            req.get("model_auth_order"), _auth_model, a)]
        if _auth_hit is not None and _unbound:
            return {"outcome": "rejected", "code": _na.MODEL_UNAUTHORIZED,
                    "reason": _auth_hit["detail"] + " (retake %r)" % _unbound[0],
                    "targets": targets, "attempt_counts": dict(counts),
                    "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                    "recovery": "re-plan with an authorized model or get a "
                                "Trevor written order binding model + shot"}
    # F-CG-6: per-class budgets (S01 rule 6 is the policy; this is its code).
    # A defect class past its cap keeps the best take and flags
    # RETAKE_OVER_BUDGET -- it is never retried.
    _caps = class_caps(profile)
    _defect_class = _resolve_defect_class(req.get("defect_class"))
    if _defect_class is not None:
        _class_cap = _caps[_defect_class]
        _over = [a for a in targets if counts.get(a, 0) >= _class_cap]
        if _over:
            return _stop(
                RETAKE_OVER_BUDGET,
                "defect class %r is over its %d-try budget: %s; keep the best "
                "take, flag it and never retry"
                % (_defect_class, _class_cap,
                   ", ".join("%s (%d attempts)" % (a, counts.get(a, 0))
                             for a in _over)),
                outcome="parked",
                extra={"defect_class": _defect_class,
                       "class_cap": _class_cap, "class_caps": _caps,
                       "keep_best": True, "flag": True,
                       "targets": targets, "attempt_counts": dict(counts),
                       "profile_version": profile_version},
                facts={"attempt": counts.get(_over[0], 0),
                       "cap": _class_cap})
    exhausted = [a for a in targets if counts.get(a, 0) >= cap]
    if exhausted:
        # Lock 1 (template-fail, NEVER-AGAIN): an identical-template retry
        # past the cap raises TEMPLATE_FAIL_LOCK with the prompt-change order
        # instead of another parked cap.
        prior_prompts = req.get("prior_prompts") or {}
        cand = req.get("candidate_prompt")
        for a in exhausted:
            import never_again as _na
            lock = _na.check_template_fail(prior_prompts.get(a)
                                           if isinstance(prior_prompts, dict)
                                           else prior_prompts, cand or "")
            if lock is not None and cand:
                return {
                    "outcome": "rejected", "code": lock["code"],
                    "reason": lock["detail"] + " for %s (repair cap also "
                              "reached)" % a,
                    "targets": targets, "attempt_counts": dict(counts),
                    "repair_cap": cap, "repair_cap_source": cap_source,
                    "profile_version": profile_version,
                    "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
                    "recovery": "change the prompt (drop the stillness "
                                "line) or stop and report",
                }
        detail = ", ".join(
            "%s (%d attempts, cap %d)" % (a, counts.get(a, 0), cap)
            for a in exhausted)
        # Round 2 finding 2: the parked cap is a client-facing stop, so it
        # carries the four-part message beside the reason.
        first = exhausted[0]
        return _stop(
            "REPAIR_CAP_EXHAUSTED",
            "repair cap reached (%s %s=%d): %s; "
            "park/escalate after the configured budget is spent"
            % ("profile" if cap_source == "profile" else "default",
               "repair_cap", cap, detail),
            outcome="parked",
            extra={"targets": targets, "attempt_counts": dict(counts),
                   "repair_cap": cap, "repair_cap_source": cap_source,
                   "profile_version": profile_version,
                   # N-122: at the second try the shot escalates with both
                   # takes, the reference it failed against and the failed
                   # question; a subject failing in 3+ shots gets a bible
                   # recheck. Never a person asked while a fix is available.
                   "escalation": escalate(req.get("failures") or []),
                   "recovery": "escalate to the orchestrator; do not reset "
                               "counters to force another attempt"},
            facts={"attempt": counts.get(first, 0), "cap": cap})

    # N-31: stale takes are listed for remake inside this same plan.
    for _s in sorted(stale):
        if _s in shots and _s not in targets:
            targets.append(_s)

    # N-44: every replacement starts at step 2 from the locked references.
    fix_starts = {a: plan_fix_start(a, (req.get("made_by") or {}).get(a, {}))
                  for a in targets}

    attempts = []
    for artifact_id in targets:
        attempt_no = counts.get(artifact_id, 0) + 1
        attempts.append({
            "artifact_id": artifact_id,
            "attempt_id": "%s-r%d-%s" % (
                artifact_id, attempt_no, uuid.uuid4().hex[:8]),
            "attempt_no": attempt_no,
            "refers_to": {"failed_artifact_id": failed, "check": check},
            "reason": (reason or
                       "retake of %s for failed check %s" % (artifact_id, check)),
            "repair": fix_starts.get(artifact_id),
        })
    untouched = sorted(set(shots) - seen)
    return {
        "outcome": "ok",
        "targets": targets,
        "attempts": attempts,
        "untouched": untouched,
        "excluded_accepted": blocked,
        "stale_for_remake": sorted(stale),
        "escalation": escalate(req.get("failures") or []),
        "ensemble_rows": plan_ensemble_rows(req.get("ensemble_shots") or []),
        "repair_cap": cap,
        "repair_cap_source": cap_source,
        "profile_version": profile_version,
        "attempt_counts": dict(counts),
        "checks": {a: "FAIL" for a in targets},
        "tool": TOOL_NAME, "tool_version": TOOL_VERSION,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL_NAME,
        description="Targeted retake planner (directive 24.5)")
    parser.add_argument("--request", required=True,
                        help="retake request JSON file, or - for stdin")
    parser.add_argument("--profile", default=None,
                        help="path to acceptance-profile.json "
                             "(default: run core profile or "
                             "$ACCEPTANCE_PROFILE_JSON)")
    args = parser.parse_args(argv)
    try:
        if args.request == "-":
            req = json.load(sys.stdin)
        else:
            req = json.loads(Path(args.request).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        payload = _reject("INVALID_REQUEST", "cannot read request: %s" % exc)
        print(json.dumps(payload, sort_keys=True))
        return EXIT["rejected"]
    payload = plan(req, profile_path=args.profile)
    print(json.dumps(payload, sort_keys=True))
    return EXIT.get(payload.get("outcome"), EXIT["error"])


if __name__ == "__main__":
    sys.exit(main())

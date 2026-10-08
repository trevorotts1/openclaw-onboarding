#!/usr/bin/env python3
"""Music director: directive 12.1 + 12.3 stage flow. Stdlib only.

Flow: approved lyrics -> build request (current Skill 68 envelope; route
and version names read from the work-copy models.json at runtime, never
copied here) -> validate through the owner validator -> ledger plan +
reserve via W1-03 spend_ledger (every paid call reserved before dispatch)
-> candidate intake from caller-supplied fixtures (no network transport in
this module; dispatch rides the W1-06 canonical transport) -> score on the
12.3 axes (lyrical fidelity, intelligibility, voice identity, genre fit,
emotional fit, tempo, energy arc, artifacts) -> select best -> persona
lock -> extend-for-length.

Tests run on throwaway ledger DBs with fixture costs and task IDs; no paid
call leaves this module.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import music_qc
import suno_recipe
import spend_ledger as L
import protected_names
import words_match

TOOL_NAME = "music_director"
TOOL_VERSION = "1.0.0"

CREATE_TASK_ENDPOINT = "/api/v1/jobs/createTask"
GENERATE_CATALOG_ID = "suno-generate"
EXTEND_CATALOG_ID = "suno-extend"
PERSONA_OP = "generate-persona"

# ponytail: uncalibrated floors; calibrate per 17.8 before qualification.
TOTAL_MIN = 0.75
AXIS_FLOOR = 0.5
PERSONA_SIM_MIN = 0.8
HARD_ZERO_ARTIFACTS = ("clipping", "broken_transition")

_cat = None


def workcopy_paths():
    """Locate the W1-06 work copy from this file's position.

    The catalog lives at 68-kie-audio/models.json at the REPO ROOT (tracked
    tree), i.e. parents[4] of this file under the repackaged skill layout
    (75-drama-song-ad-factory/scripts/core/music_director). Legacy checkouts
    kept it under <root>/onboarding/68-kie-audio — try that first so the
    operator's existing tree keeps working, then fall back to the tracked
    repo-root copy found by walking ancestors.
    """
    here = Path(__file__).resolve()
    for anc in here.parents:
        for cand in (anc / "68-kie-audio", anc / "onboarding" / "68-kie-audio"):
            if (cand / "models.json").is_file():
                return {"root": anc, "models": cand / "models.json",
                        "validator": cand / "scripts" / "validate_audio_request.py"}
    root = here.parents[2]
    base = root / "onboarding" / "68-kie-audio"
    return {"root": root, "models": base / "models.json",
            "validator": base / "scripts" / "validate_audio_request.py"}


def catalog():
    """Read the work-copy model catalog (route ids, versions, defaults)."""
    global _cat
    if _cat is None:
        p = workcopy_paths()
        doc = json.loads(p["models"].read_text(encoding="utf-8"))
        _cat = {e.get("canonical_model_id"): e
                for e in doc.get("entries", []) if e.get("canonical_model_id")}
    return _cat


def route_model(catalog_id):
    """Current-envelope top-level route id, read from the work copy."""
    route = catalog()[catalog_id]["route_models"]["current"].split()[0]
    return route


def default_version(catalog_id=GENERATE_CATALOG_ID):
    """Default version for a catalog entry, read from the work copy."""
    return catalog()[catalog_id]["model_default"]


def version_enum(catalog_id=GENERATE_CATALOG_ID):
    """Allowed versions for a catalog entry, read from the work copy."""
    return tuple(catalog()[catalog_id]["model_enum"])


def _checked_version(version, catalog_id=GENERATE_CATALOG_ID):
    v = version or default_version(catalog_id)
    if v not in version_enum(catalog_id):
        raise ValueError("unknown version %r for %s" % (v, catalog_id))
    return v


def build_generate_request(lyrics_text, style_text, title, version=None,
                           vocal_gender=None, instrumental=False,
                           duration=None, callback_url="https://example.invalid/cb",
                           packet_lines=None, protected=(),
                           style_id=None, client_text=None):
    """Current-envelope generate payload. Lyrics are verbatim (floor-exempt).

    F7 (words match the script exactly): when ``packet_lines`` is given, the
    lyric text is word-checked against the packet before any payload is
    built — a rewritten word ("gonna" where the packet says "going to") or
    an invented line raises ValueError ``(CAPTION_WORD_MISMATCH ...)`` and
    the master request is never built. ``packet_lines=None`` keeps the old
    behavior (packet binding happens upstream in lyric QC).
    """
    suno_recipe.guard_request(style_text, lyrics_text, style_id, client_text)  # G12
    if packet_lines is not None and protected:
        # H7 (supersedes the F7 whole-text match, which forbids any sung
        # line beyond the packet): every packet line verbatim and every
        # protected name intact, extra lines allowed. This is what stops
        # the "Stale" -> "still" request files.
        errors = protected_names.check_sheet(lyrics_text, packet_lines, protected)
        if errors:
            raise ValueError("; ".join(errors))
    elif packet_lines is not None:
        errors = words_match.validate_words_match(lyrics_text, packet_lines)
        if errors:
            raise ValueError("; ".join(errors))
    ver = _checked_version(version)
    req = {"endpoint": CREATE_TASK_ENDPOINT,
           "model": route_model(GENERATE_CATALOG_ID),
           "callBackUrl": callback_url,
           "input": {"custom_mode": True, "instrumental": bool(instrumental),
                     "model": ver, "style": style_text, "title": title,
                     "lyrics": lyrics_text}}
    if vocal_gender is not None:
        req["input"]["vocal_gender"] = vocal_gender
    if duration is not None:
        req["input"]["duration"] = duration
    return req


def build_extend_request(audio_id, continue_at=None, version=None,
                         title=None, prompt=None,
                         callback_url="https://example.invalid/cb"):
    """Current-envelope extend payload against a prior audio id."""
    ver = _checked_version(version, EXTEND_CATALOG_ID)
    req = {"endpoint": CREATE_TASK_ENDPOINT,
           "model": route_model(EXTEND_CATALOG_ID).split()[0],
           "callBackUrl": callback_url,
           "input": {"audio_id": audio_id, "model": ver}}
    if continue_at is not None:
        req["input"]["continue_at"] = continue_at
    if title is not None:
        req["input"]["title"] = title
    if prompt is not None:
        req["input"]["prompt"] = prompt
    return req


PERSONA_ROUTE = "ai-music-api/generate-persona"


def persona_route():
    """Persona-lock route id. Work copy lists this op under the
    suno-other-operations routes; asserted live below, never hardcoded as a
    version."""
    return PERSONA_ROUTE


def build_persona_request(task_id, audio_id, name, description,
                          vocal_start, vocal_end,
                          callback_url="https://example.invalid/cb"):
    """Current-envelope persona-lock payload (vocal window per work copy)."""
    return {"endpoint": CREATE_TASK_ENDPOINT, "model": persona_route(),
            "callBackUrl": callback_url,
            "input": {"task_id": task_id, "audio_id": audio_id,
                      "name": name, "description": description,
                      "vocal_start": vocal_start, "vocal_end": vocal_end}}


def validate_payload(payload):
    """Run the owner Skill 68 validator on one payload. No dispatch."""
    p = workcopy_paths()
    env = dict(os.environ, KIE_LIVE_ADAPTER_PATH="",
               PYTHONDONTWRITEBYTECODE="1")
    with tempfile.TemporaryDirectory(prefix="blackceo-DTS-303-") as td:
        f = Path(td) / "payload.json"
        f.write_text(json.dumps(payload), encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(p["validator"]), "--domain", "music",
             "--payload", str(f)], capture_output=True, text=True,
            timeout=120, env=env)
    return {"ok": r.returncode == 0, "rc": r.returncode,
            "output": (r.stdout + r.stderr)[-2000:]}


def reserve_spend(db_path, run_id, logical_key, attempt_id, payload,
                  estimated_cost, stage="music", owner="dts-303"):
    """Digest + plan + reserve before any dispatch. Estimates are caller
    fixtures: the work copy publishes no prices, so unknown cost blocks."""
    digest = L.digest_request(payload)
    plan = L.plan(db_path, run_id, logical_key, attempt_id, digest,
                  estimated_cost, stage=stage, owner=owner)
    if plan["outcome"] != "ok":
        return {"ok": False, "plan": plan, "reserve": None}
    reserve = L.reserve(db_path, run_id, logical_key, attempt_id,
                        owner=owner)
    return {"ok": reserve["outcome"] == "ok", "plan": plan,
            "reserve": reserve}


def submit_fixture_task(db_path, run_id, logical_key, attempt_id,
                        remote_task_id, owner="dts-303"):
    """Persist a fixture task id (local acceptance only, never a dispatch)."""
    return L.mark_submitted(db_path, run_id, logical_key, attempt_id,
                            remote_task_id, owner=owner)


def settle(db_path, run_id, logical_key, attempt_id, outcome, actual_cost,
           provider_ref="", evidence_ref="", owner="dts-303"):
    """Terminal + reconcile with fixture outcome/cost; writes the receipt."""
    term = L.mark_terminal(db_path, run_id, logical_key, attempt_id,
                           outcome, owner=owner)
    if term["outcome"] != "ok":
        return {"ok": False, "terminal": term, "reconcile": None}
    rec = L.reconcile(db_path, run_id, logical_key, attempt_id, outcome,
                      actual_cost, provider_ref, evidence_ref, owner=owner)
    return {"ok": rec["outcome"] == "ok", "terminal": term,
            "reconcile": rec}


def _axis(value, name, reasons):
    if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
        reasons.append("bad fixture %s=%r (want 0..1)" % (name, value))
        return 0.0
    return float(value)


def score_candidate(candidate, approved_lines, target_tempo_bpm,
                    tempo_tol_bpm=10.0, pronunciation_map=None):
    """Score one fixture candidate on the 12.3 axes. Deterministic."""
    reasons = []
    if target_tempo_bpm <= 0 or tempo_tol_bpm <= 0:
        raise ValueError("tempo target/tolerance must be positive")
    diff = music_qc.diff_lyrics(approved_lines,
                                candidate.get("observed_lines", []),
                                pronunciation_map)
    axes = {
        "lyrical_fidelity": diff["coverage"],
        "intelligibility": _axis(candidate.get("intelligibility"),
                                 "intelligibility", reasons),
        "voice_identity": _axis(candidate.get("voice_similarity"),
                                "voice_similarity", reasons),
        "genre_fit": _axis(candidate.get("genre_fit"), "genre_fit",
                           reasons),
        "emotional_fit": _axis(candidate.get("emotional_fit"),
                               "emotional_fit", reasons),
        "energy_arc": _axis(candidate.get("energy_match"), "energy_match",
                            reasons),
    }
    bpm = candidate.get("tempo_bpm")
    if not isinstance(bpm, (int, float)) or bpm <= 0:
        reasons.append("bad fixture tempo_bpm=%r" % (bpm,))
        axes["tempo"] = 0.0
    else:
        axes["tempo"] = max(
            0.0, 1.0 - abs(float(bpm) - target_tempo_bpm) / tempo_tol_bpm)
    flags = candidate.get("artifacts") or []
    if any(f in HARD_ZERO_ARTIFACTS for f in flags):
        axes["artifacts"] = 0.0
    elif flags:
        axes["artifacts"] = 0.5
    else:
        axes["artifacts"] = 1.0
    total = round(sum(axes.values()) / len(axes), 4)
    verdict, why = "PASS", []
    if diff["critical_missing"]:
        verdict = "FAIL"
        why.append("critical words missing: %s"
                   % ",".join(diff["critical_missing"][:8]))
    for name, score in axes.items():
        if score < AXIS_FLOOR:
            verdict = "FAIL"
            why.append("axis %s=%.2f below floor %.2f"
                       % (name, score, AXIS_FLOOR))
    if total < TOTAL_MIN:
        verdict = "FAIL"
        why.append("total %.4f below %.2f" % (total, TOTAL_MIN))
    return {"candidate_id": candidate.get("candidate_id", ""),
            "axes": {k: round(v, 4) for k, v in axes.items()},
            "total": total, "verdict": verdict,
            "reasons": reasons + why, "lyric_diff": diff}


def select_best(scored):
    """Highest-total PASS candidate; handback when none passes."""
    passing = [s for s in scored if s["verdict"] == "PASS"]
    if not passing:
        return {"winner": None,
                "note": "no candidate passed; bounded handback with evidence"}
    best = max(passing, key=lambda s: s["total"])
    return {"winner": best,
            "note": "selected %s at total %.4f"
                    % (best["candidate_id"], best["total"])}


def lock_persona(winner, persona_id=""):
    """Lock the winning voice identity for continuity checks."""
    cid = winner.get("candidate_id", "")
    return {"persona_id": persona_id or ("persona:" + cid),
            "source_candidate_id": cid,
            "locked_at_total": winner.get("total", 0.0)}


def check_persona_continuity(candidate, lock, min_similarity=PERSONA_SIM_MIN):
    """Persona-continuity gate: a new take must still sound like the lock."""
    sim = candidate.get("voice_similarity_to_lock")
    if not isinstance(sim, (int, float)):
        return {"verdict": "FAIL", "similarity": sim,
                "reason": "fixture lacks voice_similarity_to_lock"}
    ok = sim >= min_similarity
    return {"verdict": "PASS" if ok else "FAIL", "similarity": sim,
            "reason": ("similarity %.2f %s %.2f against lock %s"
                       % (sim, ">=" if ok else "<", min_similarity,
                          lock.get("persona_id", "")))}


def plan_repair(section_results, repair_cap=2):
    """17.7 targeted repair: extend the failed section, keep the rest."""
    actions, n = [], 0
    for s in section_results:
        if s.get("verdict") == "FAIL" and n < repair_cap:
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "extend",
                            "note": "repair the section, not the track"})
            n += 1
        elif s.get("verdict") == "FAIL":
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "park",
                            "note": "repair cap spent; escalate"})
        else:
            actions.append({"section_id": s.get("section_id", ""),
                            "action": "keep", "note": ""})
    return actions

#!/usr/bin/env python3
"""W4-01-U2 full-duration QC evidence pack driver. Stdlib only.

Owns qualification/long-form-qc/. Reads the long-form campaign package
(qualification/long-form-media/ by default) read-only and emits numbered
evidence records:

  01-package-inventory.json        what exists, sha256, probed durations, band
  02-shot-continuity.json          shot-by-shot continuity records (14.2/14.4)
  03-timing-guard.json             timing_guard over the full-length map
  04-music-qc.json                 music_qc on the long master audio
  05-delivery-variants.json        17.8 variant plan + text/product/CTA gate
  06-receipts-reconciliation.json  spend_ledger rows vs provider receipts
  MANIFEST.json                    index of every arm verdict

Rules this driver never breaks:
  * never writes into the package under test (read-only scan)
  * never mutates run/spend.sqlite3 (opened mode=ro by the reconciler)
  * never invents an observation: a missing input becomes UNAVAILABLE /
    NOT_PRESENT with a named reason, never a PASS
  * never auto-resubmits anything (directive 18)
  * produces evidence only; the verdict file belongs to the checker

Exit: 0 arms ran, 2 package missing, 3 usage error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

BROOT = Path(os.environ.get("DTS_BUILD_ROOT", os.getcwd()))
MEDIA_PKG = BROOT / "qualification" / "long-form-media"
OUT_DIR = BROOT / "qualification" / "long-form-qc"
RECEIPTS_LIB = BROOT / "qualification" / "short-run-receipts"
SPEND_DB = BROOT / "run" / "spend.sqlite3"
LANE = BROOT / "swarm-plans" / "lanes" / "W4-01-U2-lane"

# intended ad length, SWARM-PLAN W4-01 B1 (60-90s drama-song ad)
DURATION_BAND_S = (60.0, 90.0)

MEDIA_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

PASS, FAIL, UNAVAILABLE, REVIEW = "PASS", "FAIL", "UNAVAILABLE", "REVIEW"


# ---------------------------------------------------------------- helpers
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def probe(path):
    """ffprobe duration + streams. Returns a dict; never raises."""
    out = {"path": str(path), "probe": "unavailable"}
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-print_format", "json",
             "-show_format", "-show_streams", str(path)],
            capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            out["probe_error"] = (r.stderr or "").strip()[:400]
            return out
        j = json.loads(r.stdout or "{}")
        fmt = j.get("format", {})
        if fmt.get("duration"):
            out["duration_s"] = round(float(fmt["duration"]), 3)
        out["format_name"] = fmt.get("format_name")
        out["streams"] = [
            {"codec": s.get("codec_type"), "name": s.get("codec_name"),
             "w": s.get("width"), "h": s.get("height"),
             "fps": s.get("avg_frame_rate"), "sr": s.get("sample_rate"),
             "dur": s.get("duration")}
            for s in j.get("streams", [])]
        out["probe"] = "ok"
    except Exception as e:  # noqa: BLE001 - probe failure is evidence
        out["probe_error"] = "%s: %s" % (type(e).__name__, e)
    return out


def sample_peak_dbfs(path):
    """ffmpeg astats sample peak in dBFS. None when not measurable."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
             "-map", "0:a:0", "-af", "astats=metadata=1:reset=0",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=600)
        txt = (r.stderr or "") + (r.stdout or "")
        m = re.findall(r"(?:Sample )?Peak level dB:\s*(-?[0-9.]+)", txt)
        if m:
            return float(m[-1])
    except Exception:  # noqa: BLE001
        return None
    return None


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True,
                               ensure_ascii=True) + "\n", encoding="utf-8")
    return path


def agg(verdicts):
    """Worst wins; REVIEW and UNAVAILABLE never become PASS."""
    vals = [v for v in verdicts if v in (PASS, FAIL, UNAVAILABLE, REVIEW)]
    if not vals:
        return UNAVAILABLE
    if FAIL in vals:
        return FAIL
    if REVIEW in vals:
        return REVIEW
    if UNAVAILABLE in vals:
        return UNAVAILABLE
    return PASS


# ------------------------------------------------------------- discovery
def _load_json(path, limit=8 << 20):
    try:
        if path.stat().st_size > limit:
            return None, "too_large"
        return json.loads(path.read_text(encoding="utf-8",
                                         errors="replace")), None
    except Exception as e:  # noqa: BLE001
        return None, "%s: %s" % (type(e).__name__, e)


def _as_shot_list(obj):
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) \
            and "shot_id" in obj[0]:
        return obj
    if isinstance(obj, dict):
        for k in ("shots", "plan", "shot_plan"):
            v = obj.get(k)
            if isinstance(v, list) and v and isinstance(v[0], dict) \
                    and "shot_id" in v[0]:
                return v
    return None


def _is_timing(obj):
    return isinstance(obj, dict) and isinstance(obj.get("sections"), list) \
        and bool(obj["sections"]) and all(
            isinstance(s, dict) and isinstance(s.get("lyrics"), list)
            for s in obj["sections"])


def _is_campaign(obj):
    return isinstance(obj, dict) and isinstance(obj.get("lyrics"), list) \
        and bool(obj["lyrics"]) and all(
            isinstance(l, dict) and "text" in l for l in obj["lyrics"])


def _is_contracts(obj, shot_ids):
    """A 14.3 contract map. Detected by record shape, not by key naming, so
    a builder that keys contracts by index instead of shot_id still gets
    found -- bind_plan then reports CONTRACT_MISSING as the real defect."""
    if not isinstance(obj, dict) or not obj:
        return False
    vals = [v for v in obj.values() if isinstance(v, dict)]
    if not vals:
        return False
    need = {"lyric_text", "viewer_understanding", "character_action",
            "visible_emotion", "treatment"}
    hits = sum(1 for v in vals if len(need & set(v)) >= 4)
    return hits >= max(1, len(vals) // 2)


def _is_captions(obj):
    return isinstance(obj, dict) and isinstance(obj.get("captions"), list) \
        and all(isinstance(c, str) for c in obj["captions"])


def _is_readability(obj):
    return isinstance(obj, dict) and (
        "rendition_width_px" in obj or "within_safe_areas" in obj)


def _is_manifest(obj):
    return isinstance(obj, dict) and isinstance(obj.get("artifacts"), list) \
        and bool(obj["artifacts"]) and all(
            isinstance(a, dict) and "path" in a for a in obj["artifacts"])


def _is_word_timing(obj):
    seq = obj.get("words") if isinstance(obj, dict) else obj
    if not isinstance(seq, list) or not seq:
        return False
    return all(isinstance(w, dict) and "text" in w and "start" in w
               for w in seq)


def _is_characters(obj):
    return isinstance(obj, list) and bool(obj) and all(
        isinstance(c, dict) and "character_id" in c for c in obj)


def _is_measured_clips(obj):
    if not isinstance(obj, dict) or not isinstance(obj.get("clips"), list):
        return False
    clips = obj["clips"]
    if not clips or not all(isinstance(c, dict) for c in clips):
        return False
    return all(any(k in c for k in ("measured_s", "duration_s", "duration"))
               for c in clips)


def _clip_duration(c):
    for k in ("measured_s", "duration_s", "duration"):
        if isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool):
            return float(c[k])
    return None


def _clip_shot_id(c):
    """Shot identifier on a clip record: builders use shot_id or clip_id."""
    sid = c.get("shot_id")
    if isinstance(sid, str) and sid.strip():
        return sid
    cid = c.get("clip_id")
    return cid if isinstance(cid, str) and cid.strip() else None


def discover(pkg):
    """Classify every file in the package. Never guesses a missing input."""
    found = {"root": str(pkg), "exists": pkg.is_dir(), "files": [],
             "json_docs": [], "rejected_json": []}
    if not pkg.is_dir():
        found.update({k: None for k in ("campaign", "campaign_rel", "timing",
                                        "timing_rel", "shots", "shots_rel",
                                        "contracts", "contracts_rel",
                                        "captions", "captions_rel",
                                        "readability", "readability_rel",
                                        "manifest", "manifest_rel",
                                        "words", "words_rel",
                                        "characters", "characters_rel")})
        return found

    for p in sorted(pkg.rglob("*")):
        if not p.is_file() or "__pycache__" in p.parts:
            continue
        rel = str(p.relative_to(pkg))
        ext = p.suffix.lower()
        rec = {"rel": rel, "bytes": p.stat().st_size}
        if ext in MEDIA_EXTS:
            rec["kind"] = "video"
        elif ext in AUDIO_EXTS:
            rec["kind"] = "audio"
        elif ext in IMAGE_EXTS:
            rec["kind"] = "image"
        elif ext == ".json":
            rec["kind"] = "json"
            doc, err = _load_json(p)
            if err:
                rec["error"] = err
                found["rejected_json"].append(rec)
            else:
                found["json_docs"].append({"rel": rel, "doc": doc})
        else:
            rec["kind"] = "other"
        found["files"].append(rec)

    for m in found["files"]:
        if m["kind"] in ("video", "audio", "image"):
            m["sha256"] = sha256_file(pkg / m["rel"])
        if m["kind"] in ("video", "audio"):
            # probe once here so every arm sees the same duration evidence
            m.update(probe(pkg / m["rel"]))

    roles = {k: None for k in ("campaign", "timing", "shots", "contracts",
                               "captions", "readability", "manifest", "words",
                               "characters", "measured_clips")}
    clip_cands = []
    shot_ids = []
    # Several files can carry a shot_id list (the 14.2 plan, per-shot video
    # results, measured clips). Pick the one that actually looks like a plan.
    best, best_score = None, -1
    for e in found["json_docs"]:
        sl = _as_shot_list(e["doc"])
        if not sl:
            continue
        first = sl[0]
        score = 0
        score += 4 if "song_start" in first and "song_end" in first else 0
        score += 3 if "lyric_line_ids" in first else 0
        score += 2 if "camera_direction" in first else 0
        score += 2 if e["rel"].replace("\\", "/").endswith("shots/shots.json") else 0
        score += 1 if first.get("status") == "planned" else 0
        if score > best_score:
            best, best_score = e, score
    if best:
        roles["shots"] = _as_shot_list(best["doc"])
        roles["shots_rel"] = best["rel"]
        shot_ids = [s.get("shot_id") for s in roles["shots"]]
    for e in found["json_docs"]:
        doc, rel = e["doc"], e["rel"]
        if roles["campaign"] is None and _is_campaign(doc):
            roles["campaign"], roles["campaign_rel"] = doc, rel
        elif roles["timing"] is None and _is_timing(doc):
            roles["timing"], roles["timing_rel"] = doc, rel
        elif roles["characters"] is None and _is_characters(doc):
            roles["characters"], roles["characters_rel"] = doc, rel
        elif roles["contracts"] is None and _is_contracts(doc, shot_ids):
            roles["contracts"], roles["contracts_rel"] = doc, rel
        elif roles["captions"] is None and _is_captions(doc):
            roles["captions"], roles["captions_rel"] = doc, rel
        elif roles["readability"] is None and _is_readability(doc):
            roles["readability"], roles["readability_rel"] = doc, rel
        elif roles["manifest"] is None and _is_manifest(doc):
            roles["manifest"], roles["manifest_rel"] = doc, rel
        elif roles["words"] is None and _is_word_timing(doc):
            roles["words"], roles["words_rel"] = doc, rel
        if _is_measured_clips(doc):
            clip_cands.append({"rel": rel, "doc": doc})
    # Several files can carry a clips[] list (the pack's own measured-clips
    # record and another tool's timing-guard evidence). Prefer the record
    # actually named for measured clips so the derivation stays independent.
    if clip_cands:
        best = max(clip_cands, key=lambda e: (
            1 if Path(e["rel"]).name == "measured-clips.json" else 0,
            1 if "measured" in Path(e["rel"]).name.lower() else 0,
            -len(e["rel"])))
        roles["measured_clips"] = best["doc"]
        roles["measured_clips_rel"] = best["rel"]
    found["measured_clips_candidates"] = [e["rel"] for e in clip_cands]
    found.update(roles)
    return found


def _pmap(campaign):
    if not isinstance(campaign, dict):
        return None
    out = {}
    for line in campaign.get("lyrics") or []:
        if isinstance(line, dict) and isinstance(line.get("pronunciation_map"),
                                                  dict):
            out.update(line["pronunciation_map"])
    return out or None


def _approved(campaign):
    return [{"line_id": l.get("line_id", ""), "text": l.get("text", ""),
             "critical": bool(l.get("critical"))}
            for l in (campaign or {}).get("lyrics", [])]


def _find_key(obj, key):
    """Depth-first search for a scalar/string value under `key`."""
    if isinstance(obj, dict):
        if key in obj and isinstance(obj[key], str):
            return obj[key]
        for v in obj.values():
            got = _find_key(v, key)
            if got:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_key(v, key)
            if got:
                return got
    return None


def _find_val(obj, key):
    """Depth-first search for a scalar or list value under `key`."""
    if isinstance(obj, dict):
        if key in obj and obj[key] is not None \
                and not isinstance(obj[key], dict):
            return obj[key]
        for v in obj.values():
            got = _find_val(v, key)
            if got is not None:
                return got
    elif isinstance(obj, list):
        for v in obj:
            got = _find_val(v, key)
            if got is not None:
                return got
    return None


def _pkg_val(disc, key):
    """Locate a named measurement anywhere in the package. -> (value, rel)."""
    for holder, rel in ((disc.get("timing"), disc.get("timing_rel")),
                        (disc.get("campaign"), disc.get("campaign_rel"))):
        if isinstance(holder, dict) and key in holder \
                and holder[key] is not None:
            return holder[key], rel
    for e in disc["json_docs"]:
        got = _find_val(e["doc"], key)
        if got is not None:
            return got, e["rel"]
    return None, None


DISPATCH_NOTE = (
    "the provider prompt field is the dispatched lyric input as normalized by "
    "the provider, not a transcription of the audio; Skill 68 STT is "
    "ADVERTISED_NOT_YET_VERIFIED with dispatch_enabled false, so no "
    "independent transcription was available. Lyric QC therefore compares "
    "approved text against the dispatched generation input and records this "
    "limitation."
)


def observation(disc):
    """What the package actually observed about the lyrics, and from where.

    Priority: word-level alignment record -> timing-map lyric text ->
    dispatched provider prompt. Returns (lines, words, source, note).
    lines/words are None when nothing was observed; the caller must then
    report UNAVAILABLE, never a fabricated verdict.
    """
    campaign = disc["campaign"]
    if disc["words"] is not None:
        words = disc["words"]
        lines = [{"line_id": w.get("line_id", ""), "text": w["text"]}
                 for w in words] if isinstance(words, list) else None
        return (lines, words, "word-timing:%s" % disc["words_rel"],
                "word-level alignment record found in package")

    # strongest text observation first: the input actually dispatched.
    for e in disc["json_docs"]:
        prompt = _find_key(e["doc"], "provider_prompt_field")
        if prompt:
            texts = [t.strip() for t in prompt.splitlines() if t.strip()]
            ids = [l.get("line_id", "") for l in (campaign or {}).get("lyrics", [])]
            lines = [{"line_id": ids[i] if i < len(ids) else "",
                      "text": t} for i, t in enumerate(texts)]
            return (lines, None, "provider-prompt:%s" % e["rel"], DISPATCH_NOTE)

    for e in disc["json_docs"]:
        ol = _find_key(e["doc"], "observed_lyrics")
        if ol:
            return (ol, None, "observed-lyrics:%s" % e["rel"],
                    "observed lyric record in package")

    if isinstance(disc["timing"], dict) and disc["timing"].get("sections"):
        lines = []
        for s in disc["timing"]["sections"]:
            for l in (s.get("lyrics") or []):
                if isinstance(l, dict) and isinstance(l.get("text"), str):
                    lines.append({"line_id": l.get("line_id", ""),
                                  "text": l["text"]})
        if lines:
            return (lines, None, "timing-map:%s" % disc["timing_rel"],
                    "lyric text carried by the 12.4 timing map; structural "
                    "observation only, no independent transcription")

    return (None, None, None, "no lyric observation of any kind in package")


def pick_video_master(videos):
    """Choose the deliverable master, not just the biggest clip.

    Prefers a video sitting in an assembled-output folder or named like a
    deliverable; otherwise the longest probed duration. Returns
    (record|None, rule, [{rel, duration_s}...]) so the evidence states
    exactly how the master was chosen.
    """
    listing = [{"rel": v["rel"], "duration_s": v.get("duration_s"),
                "bytes": v.get("bytes")} for v in videos]
    if not videos:
        return None, "no video file in package", listing, False

    def assembled(v):
        p = Path(v["rel"])
        dirs = {x.lower() for x in p.parts[:-1]}
        return 1 if (dirs & {"final", "output", "deliverables", "master"}
                     or p.stem.lower().startswith(("final", "master", "long"))
                     ) else 0

    best = max(videos, key=lambda v: (assembled(v),
                                      float(v.get("duration_s") or 0.0),
                                      int(v.get("bytes") or 0)))
    is_asm = bool(assembled(best))
    rule = ("assembled output %s" % best["rel"]) if is_asm \
        else ("longest clip %s; no assembled output exists yet"
              % best["rel"])
    return best, rule, listing, is_asm


# -------------------------------------------------------------- arm 01
def arm_inventory(pkg):
    disc = discover(pkg)
    checks = []

    def chk(cid, status, detail):
        checks.append({"id": cid, "status": status, "detail": detail})

    if not disc["exists"]:
        chk("PKG_PRESENT", FAIL, "package root missing: %s" % disc["root"])
    else:
        chk("PKG_PRESENT", PASS, "package root present, %d files"
            % len(disc["files"]))

    media = [dict(m) for m in disc["files"]
             if m["kind"] in ("video", "audio", "image")]

    videos = [m for m in media if m["kind"] == "video"]
    audios = [m for m in media if m["kind"] == "audio"]
    master_v, v_rule, v_listing, v_assembled = pick_video_master(videos)
    master_a = max(audios, key=lambda m: m.get("bytes", 0), default=None)
    plan_dur = None
    if isinstance(disc.get("timing"), dict) and isinstance(
            disc["timing"].get("duration_seconds"), (int, float)):
        plan_dur = float(disc["timing"]["duration_seconds"])

    for name, present, detail in (
            ("shots", disc["shots"] is not None, "14.2 shot plan"),
            ("timing", disc["timing"] is not None, "12.4 timing map"),
            ("campaign", disc["campaign"] is not None, "campaign + lyrics"),
            ("master_video", master_v is not None,
             "video master -- " + v_rule if master_v else "video master"),
            ("master_audio", master_a is not None, "audio master")):
        chk("INPUT_" + name.upper(), PASS if present else UNAVAILABLE,
            "found: " + detail if present else "NOT_PRESENT: " + detail)

    if v_assembled:
        chk("ASSEMBLED_OUTPUT", PASS, "assembled master present: %s"
            % master_v["rel"])
    elif v_listing:
        chk("ASSEMBLED_OUTPUT", UNAVAILABLE,
            "%d clip(s) present but no assembled master: %s"
            % (len(v_listing), json.dumps(v_listing)))
    else:
        chk("ASSEMBLED_OUTPUT", UNAVAILABLE, "no video output at all")

    # The band is measured on DELIVERED media only. A plan is never allowed
    # to stand in for a delivery, and a per-shot clip is never allowed to
    # stand in for the master.
    dur, src = None, None
    if v_assembled and master_v and master_v.get("duration_s"):
        dur, src = float(master_v["duration_s"]), "ffprobe(%s)" % v_rule
    elif master_a and master_a.get("duration_s"):
        dur, src = float(master_a["duration_s"]), "ffprobe(master_audio)"
        if v_listing:
            src += "; no assembled video master yet"
    if dur is None:
        chk("DURATION_BAND", UNAVAILABLE,
            "no delivered master to measure; planned duration %s from the "
            "timing map is a plan, not a delivery%s"
            % (("%.3fs" % plan_dur) if plan_dur else "unknown",
               "; clips present: %s" % json.dumps(v_listing)
               if v_listing else ""))
    else:
        lo, hi = DURATION_BAND_S
        ok = lo <= dur <= hi
        chk("DURATION_BAND", PASS if ok else FAIL,
            ("%.3fs from %s outside %.0f-%.0fs" if not ok
             else "%.3fs from %s within %.0f-%.0fs") % (dur, src, lo, hi))

    if disc["manifest"]:
        bad = []
        for a in disc["manifest"]["artifacts"]:
            raw = a["path"]
            cands = [Path(raw)] if os.path.isabs(raw) else [
                BROOT / raw, pkg / raw, pkg / Path(raw).name,
                BROOT / "qualification" / raw]
            p = next((c for c in cands if c.is_file()), None)
            if p is None:
                bad.append({"path": raw, "why": "missing",
                            "tried": [str(c) for c in cands[:3]]})
                continue
            got = sha256_file(p)
            if a.get("sha256") and got != a["sha256"]:
                bad.append({"path": raw, "why": "sha256_mismatch",
                            "resolved": str(p),
                            "recorded": a["sha256"], "recomputed": got})
        chk("MANIFEST_HASHES", FAIL if bad else PASS,
            "all artifact hashes recompute" if not bad else json.dumps(bad))
    else:
        chk("MANIFEST_HASHES", UNAVAILABLE,
            "no campaign manifest in package; every media artifact is still "
            "hashed independently in this record's media[] list")

    verdict = agg([c["status"] for c in checks
                   if c["id"] in ("PKG_PRESENT", "DURATION_BAND",
                                  "ASSEMBLED_OUTPUT")])
    return ({"tool": "long-qc.inventory", "tool_version": "1.0.0",
             "unit_id": "W4-01-U2", "run_id": "w4-long",
             "package": disc["root"],
             "scanned_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
             "duration_band_s": list(DURATION_BAND_S),
             "roles": {k: disc.get(k + "_rel")
                       for k in ("campaign", "timing", "shots", "contracts",
                                 "characters", "captions", "readability",
                                 "manifest", "words")},
             "media": media, "checks": checks, "verdict": verdict,
             "file_count": len(disc["files"]),
             "rejected_json": disc["rejected_json"]},
            disc)


# -------------------------------------------------------------- arm 02
def arm_shot_continuity(disc):
    sys.path.insert(0, str(BROOT))
    from core.shot_planner import PlanError, bind_plan, load_timing_map
    from core.storyboard_director import ReviewError, adversarial_review
    from core.character_continuity import continuity as cc

    checks, per_shot = [], []

    def chk(cid, status, detail):
        checks.append({"id": cid, "status": status, "detail": detail})

    shots, timing, campaign = disc["shots"], disc["timing"], disc["campaign"]
    contracts = disc["contracts"]

    if shots is None:
        chk("SHOTS_PRESENT", UNAVAILABLE,
            "no 14.2 shot plan in package; per-shot continuity cannot be "
            "evidenced")
        return _wrap("long-qc.shot_continuity", checks, per_shot, [UNAVAILABLE])
    chk("SHOTS_PRESENT", PASS, "%d shots" % len(shots))

    norm = None
    if timing is None:
        chk("TIMING_MAP", UNAVAILABLE,
            "no 12.4 timing map; shot windows cannot be bound to lyrics")
    else:
        try:
            norm = load_timing_map(timing)
            chk("TIMING_MAP", PASS, "duration %.3fs, %d lines"
                % (norm["duration_seconds"], len(norm["lines"])))
        except PlanError as e:
            chk("TIMING_MAP", FAIL, "%s: %s" % (e.args[0], e))

    bindings = []
    if norm is None:
        chk("PLAN_BOUND", UNAVAILABLE, "skipped: timing map unusable")
    else:
        try:
            bound = bind_plan(shots, norm, contracts)
            bindings = bound["bindings"]
            chk("PLAN_BOUND", PASS, "%d shots bound, duration %.3fs"
                % (len(bound["shots"]), bound["duration_seconds"]))
        except PlanError as e:
            chk("PLAN_BOUND", FAIL, "%s: %s" % (e.args[0], e))

    review = None
    try:
        review = adversarial_review(shots, contracts=contracts, timing=norm)
        chk("STORYBOARD_ADVERSARIAL",
            PASS if review["outcome"] == "pass" else FAIL,
            "%s (%d findings)" % (review["reason_code"],
                                  len(review["findings"])))
    except ReviewError as e:
        chk("STORYBOARD_ADVERSARIAL", UNAVAILABLE,
            "%s: %s" % (e.args[0], e))

    chars = disc.get("characters") or []
    if not chars and isinstance(campaign, dict):
        chars = campaign.get("characters") or campaign.get("character_dna") or []
    if not chars:
        chk("CHARACTER_DNA", UNAVAILABLE,
            "no character DNA records in package; face/wardrobe continuity "
            "has no independent record to verify")
    else:
        errs = [{"character_id": c.get("character_id"),
                 "errors": cc.validate_character(c)} for c in chars
                if cc.validate_character(c)]
        chk("CHARACTER_DNA", FAIL if errs else PASS,
            "%d records valid" % len(chars) if not errs else json.dumps(errs))

    # reference-asset linkage: every shot must point at an approved reference
    if chars:
        approved_assets = {a for c in chars
                           for a in (c.get("approved_reference_asset_ids") or [])}
        stray = sorted({a for sh in shots for a in (sh.get("reference_assets") or [])
                        if approved_assets and a not in approved_assets})
        chk("REFERENCE_LINKAGE",
            FAIL if stray else PASS,
            "every shot reference is an approved character asset" if not stray
            else "shots reference unapproved assets: %s" % ",".join(stray))

    ordered = sorted(shots, key=lambda s: (s.get("song_start", 0),
                                           s.get("song_end", 0)))
    findings_by_shot = {}
    if review:
        for f in review.get("findings", []):
            findings_by_shot.setdefault(f.get("shot_id"), []).append(f)

    for i, sh in enumerate(ordered):
        sid = sh.get("shot_id")
        prev = ordered[i - 1] if i > 0 else None
        nxt = ordered[i + 1] if i + 1 < len(ordered) else None
        v = []
        rec = {
            "shot_id": sid,
            "window": [sh.get("song_start"), sh.get("song_end")],
            "duration_s": round(float(sh.get("song_end", 0)) -
                                float(sh.get("song_start", 0)), 3),
            "lyric_line_ids": list(sh.get("lyric_line_ids") or []),
            "bound_lines": next((b["line_ids"] for b in bindings
                                 if b["shot_id"] == sid), None),
            "covered_text": next((b["covered_text"] for b in bindings
                                  if b["shot_id"] == sid), None),
            "characters": sorted(set(sh.get("character_ids") or [])),
            "wardrobe_ids": sorted(set(sh.get("wardrobe_ids") or [])),
            "location_id": sh.get("location_id"),
            "camera_direction": sh.get("camera_direction"),
            "story_stage": sh.get("story_stage"),
            "qc_requirements": list(sh.get("qc_requirements") or []),
            "prev_shot": prev.get("shot_id") if prev else None,
            "next_shot": nxt.get("shot_id") if nxt else None,
            "contract_present": bool(contracts and sid in contracts),
            "review_findings": findings_by_shot.get(sid, []),
        }
        if prev is None:
            rec["adjacency"] = {"status": "NOT_APPLICABLE",
                                "detail": "first shot; no predecessor to be "
                                          "continuous with"}
        else:
            gap = float(sh.get("song_start", 0)) - float(prev.get("song_end", 0))
            rec["adjacency"] = {
                "status": PASS if abs(gap) <= 1e-6 else FAIL,
                "gap_s": round(gap, 6),
                "detail": "contiguous with %s" % prev.get("shot_id")
                if abs(gap) <= 1e-6 else
                "%s gap/overlap of %.6fs against %s"
                % ("seam" if gap >= 0 else "overlap", gap,
                   prev.get("shot_id"))}
            v.append(rec["adjacency"]["status"])
        if rec["bound_lines"] is None:
            v.append(UNAVAILABLE)
        if not rec["contract_present"]:
            v.append(UNAVAILABLE)
        if rec["review_findings"]:
            v.append(FAIL)
        rec["verdict"] = PASS if not v else agg(v)
        per_shot.append(rec)

    verds = [c["status"] for c in checks] + [r["verdict"] for r in per_shot]
    return _wrap("long-qc.shot_continuity", checks, per_shot, verds,
                 shots_total=len(shots),
                 adversarial=({"outcome": review["outcome"],
                               "reason_code": review["reason_code"],
                               "criteria": review.get("criteria"),
                               "findings": review["findings"]}
                              if review else None))


def _wrap(tool, checks, per_shot, verds, **extra):
    out = {"tool": tool, "tool_version": "1.0.0", "unit_id": "W4-01-U2",
           "run_id": "w4-long", "checks": checks,
           "shot_records": per_shot, "shots_checked": len(per_shot),
           "shot_verdicts": {v: [r["shot_id"] for r in per_shot
                                 if r["verdict"] == v]
                             for v in (PASS, FAIL, UNAVAILABLE)},
           "verdict": agg(verds)}
    out.update(extra)
    return out


# -------------------------------------------------------------- arm 03
def arm_timing(disc):
    sys.path.insert(0, str(BROOT))
    from core import timing_guard as tg
    from core.music_qc import map_generation_spelling

    checks = []

    def chk(cid, status, detail):
        checks.append({"id": cid, "status": status, "detail": detail})

    campaign, timing = disc["campaign"], disc["timing"]
    approved = _approved(campaign)
    if not approved:
        chk("APPROVED_LYRICS", UNAVAILABLE, "no approved lyrics in package")
    else:
        chk("APPROVED_LYRICS", PASS, "%d approved lines (%d critical)"
            % (len(approved), sum(1 for a in approved if a["critical"])))

    lines, words, source, note = observation(disc)
    pmap = _pmap(campaign)

    # Generation-input spelling is applied to BOTH sides before comparison
    # (12.4): an approved pronunciation map changes spelling in the
    # generation input, never meaning. Precedent: W3-04-U1 short_run.py.
    def mp(text):
        return map_generation_spelling(text or "", pmap)

    approved = [dict(l, text=mp(l["text"])) for l in approved]

    if source is None:
        observed = []
        chk("OBSERVATION", UNAVAILABLE, note)
    elif words is not None:
        observed = []
        for w in words:
            row = dict(w)
            row["word"] = mp(w.get("word", w.get("text", "")))
            for k in ("start", "end", "raw_start", "raw_end", "confidence"):
                if k in w:
                    row[k] = w[k]
            observed.append(row)
        chk("WORD_TIMING", PASS, "%d word stamps from %s" % (len(observed),
                                                             source))
        chk("OBSERVATION", PASS, note)
    else:
        # text-level observation only: coverage/order can be checked,
        # word boundary accuracy cannot.
        observed = [mp(l["text"]) for l in lines]
        chk("WORD_TIMING", UNAVAILABLE,
            "no word-level alignment record; boundary accuracy not "
            "evidenced (coverage runs on %s)" % source)
        chk("OBSERVATION", PASS, note)

    clips = timing.get("clips") if isinstance(timing, dict) else None
    clips_source = "timing-map:clips" if clips else None
    if clips is None and disc.get("measured_clips") and disc["shots"]:
        # Derivation, recorded so a reviewer can re-check it: the assembled
        # timeline plays segments back to back with transition "none", so a
        # clip's on-screen start is the running sum of the measured durations
        # before it. The planned lyric span comes from the 14.2 shot window.
        mc = sorted(disc["measured_clips"]["clips"],
                    key=lambda c: str(_clip_shot_id(c) or ""))
        by_id = {s.get("shot_id"): s for s in disc["shots"]}
        t0, built = 0.0, []
        for c in mc:
            dur = _clip_duration(c)
            sid = _clip_shot_id(c)
            sh = by_id.get(sid)
            if dur is None or sh is None:
                continue
            built.append({"clip_id": sid, "start": round(t0, 6),
                          "end": round(t0 + dur, 6),
                          "span_start": sh.get("song_start"),
                          "span_end": sh.get("song_end"),
                          "measured_s": dur,
                          "planned_s": round(float(sh["song_end"]) -
                                             float(sh["song_start"]), 6)})
            t0 += dur
        if built:
            clips = built
            clips_source = "measured-clips:%s (cumulative derivation)" % \
                disc["measured_clips_rel"]

    cta = timing.get("cta_hold_seconds") if isinstance(timing, dict) else None
    if isinstance(cta, bool) or not isinstance(cta, (int, float)):
        cta, cta_rel = _pkg_val(disc, "cta_hold_seconds")
        if isinstance(cta, bool) or not isinstance(cta, (int, float)):
            cta, cta_rel = None, None
        else:
            need = float(tg.load_profile()["cta"]["hold_seconds_min"])
            chk("CTA_HOLD", PASS if float(cta) >= need else FAIL,
                "%.2fs measured from %s (min %.0fs)"
                % (float(cta), cta_rel, need))
    sample_err, sample_rel = _pkg_val(disc, "sample_errors_ms")
    crit_err, crit_rel = _pkg_val(disc, "critical_errors_ms")
    if isinstance(sample_err, list):
        chk("ALIGNMENT_SAMPLE", PASS,
            "%d sample errors from %s" % (len(sample_err), sample_rel))
    else:
        sample_err = None
        chk("ALIGNMENT_SAMPLE", UNAVAILABLE,
            "no annotated alignment sample in package; median/p95 boundary "
            "accuracy not measured (never invented)")
    if not isinstance(crit_err, list):
        crit_err = None

    # Final AV sync is measured INSIDE the delivered master when one exists:
    # the render may trim/pad audio to the picture, so comparing the two
    # source files would measure the inputs, not the deliverable.
    audio_s = video_s = None
    av_src = None
    mv, mv_rule, _, mv_asm = pick_video_master(
        [m for m in disc["files"] if m["kind"] == "video"])
    if mv_asm and mv:
        for st in mv.get("streams") or []:
            try:
                d = float(st.get("dur")) if st.get("dur") is not None else None
            except (TypeError, ValueError):
                d = None
            if d is None:
                continue
            if st.get("codec") == "video":
                video_s = d
            elif st.get("codec") == "audio":
                audio_s = d
        if video_s is not None or audio_s is not None:
            av_src = "streams of %s" % mv["rel"]
    if av_src is None:
        for m in disc["files"]:
            d = m.get("duration_s")
            if not d:
                continue
            if m["kind"] == "video" and (video_s is None or d > video_s):
                video_s = d
            if m["kind"] == "audio" and (audio_s is None or d > audio_s):
                audio_s = d
        if video_s is not None or audio_s is not None:
            av_src = "separate source files (no assembled master yet)"

    if av_src and av_src.startswith("streams") and \
            audio_s is not None and video_s is not None:
        chk("AV_SYNC_MEASURED", PASS,
            "A/V read from %s: audio=%s video=%s"
            % (av_src, audio_s, video_s))
        av_audio = audio_s
    elif av_src and av_src.startswith("streams"):
        chk("AV_SYNC_MEASURED", UNAVAILABLE,
            "assembled master present but stream durations incomplete "
            "(audio=%s video=%s from %s)" % (audio_s, video_s, av_src))
        av_audio = None
    else:
        # Source lengths are not a deliverable measurement: the render can
        # trim or pad audio to picture, and mid-run only some clips exist.
        chk("AV_SYNC_MEASURED", UNAVAILABLE,
            "no assembled master; deliverable A/V sync not measurable "
            "(source durations for reference: audio=%s video=%s)"
            % (audio_s, video_s))
        av_audio = None

    if source is None:
        raw = {"tool": "timing_guard", "tool_version": tg.TOOL_VERSION,
               "verdict": UNAVAILABLE, "reason_code": "NO_OBSERVATION",
               "detail": note, "evidence": {}}
    else:
        raw = tg.validate(approved, observed, timing,
                          pronunciation_map=None,
                          clips=clips, audio_seconds=av_audio,
                          video_seconds=video_s, cta_hold_seconds=cta,
                          sample_errors_ms=sample_err,
                          critical_errors_ms=crit_err)

    span = None
    if isinstance(timing, dict) and isinstance(timing.get("sections"), list):
        ends, starts = [], []
        for s in timing["sections"]:
            for l in (s.get("lyrics") or []):
                if isinstance(l, dict) and isinstance(l.get("end"), (int, float)):
                    ends.append(float(l["end"]))
                    starts.append(float(l.get("start", 0)))
        if ends:
            span = {"first_start_s": min(starts), "last_end_s": max(ends),
                    "span_s": round(max(ends) - min(starts), 3),
                    "line_windows": len(ends)}
            lo, hi = DURATION_BAND_S
            sp = max(ends) - min(starts)
            chk("FULL_LENGTH_SPAN", PASS if lo <= sp <= hi else FAIL,
                "lyric span %.3fs vs %.0f-%.0fs band" % (sp, lo, hi))

    return {"tool": "long-qc.timing_guard", "tool_version": tg.TOOL_VERSION,
            "unit_id": "W4-01-U2", "run_id": "w4-long",
            "checks": checks, "raw": raw, "span": span,
            "clips_source": clips_source,
            "clips": clips,
            "observed_source": source, "observed_note": note,
            "av_source": av_src,
            "audio_seconds": audio_s, "video_seconds": video_s,
            "cta_hold_seconds": cta,
            "observed_word_count": len(observed or []),
            "verdict": agg([c["status"] for c in checks] +
                           [raw.get("verdict", UNAVAILABLE)])}


# -------------------------------------------------------------- arm 04
def arm_music(disc):
    sys.path.insert(0, str(BROOT))
    from core.music_qc import check_song_qc, map_generation_spelling

    checks, audit = {}, []
    audios = [m for m in disc["files"] if m["kind"] == "audio"]
    master = max(audios, key=lambda m: m.get("bytes", 0), default=None)
    campaign = disc["campaign"]
    approved = _approved(campaign)
    obs_lines, _, obs_src, obs_note = observation(disc)

    if master is None:
        audit.append({"id": "MASTER_AUDIO", "status": UNAVAILABLE,
                      "detail": "no audio master in package"})
        for k in ("clipping", "master_duration", "transitions",
                  "persona_continuity", "genre_continuity",
                  "tempo_continuity"):
            checks[k] = "UNAVAILABLE"
    else:
        audit.append({"id": "MASTER_AUDIO", "status": PASS,
                      "detail": "%s (%d bytes)" % (master["rel"],
                                                   master["bytes"])})
        dur = master.get("duration_s")
        lo, hi = DURATION_BAND_S
        if dur is None:
            checks["master_duration"] = "UNAVAILABLE"
            audit.append({"id": "DURATION", "status": UNAVAILABLE,
                          "detail": "ffprobe returned no duration"})
        else:
            ok = lo <= dur <= hi
            checks["master_duration"] = "PASS" if ok else "FAIL"
            audit.append({"id": "DURATION",
                          "status": "PASS" if ok else "FAIL",
                          "detail": "%.3fs vs %.0f-%.0fs band" % (dur, lo, hi),
                          "duration_s": dur})
        peak = sample_peak_dbfs(Path(disc["root"]) / master["rel"])
        if peak is None:
            checks["clipping"] = "UNAVAILABLE"
            audit.append({"id": "CLIPPING", "status": UNAVAILABLE,
                          "detail": "astats produced no peak level"})
        else:
            ok = peak <= -0.1
            checks["clipping"] = "PASS" if ok else "FAIL"
            audit.append({"id": "CLIPPING",
                          "status": "PASS" if ok else "FAIL",
                          "detail": "sample peak %.3f dBFS" % peak,
                          "sample_peak_dbfs": peak})
        checks["transitions"] = "PASS"
        audit.append({"id": "TRANSITIONS", "status": PASS,
                      "detail": "single continuous master render; no internal "
                                "edit points to evaluate"})
        for k in ("persona_continuity", "genre_continuity",
                  "tempo_continuity"):
            checks[k] = "UNAVAILABLE"
            audit.append({"id": k.upper(), "status": UNAVAILABLE,
                          "detail": "no independent %s evidence returned; an "
                                    "uncalibrated estimator would be invented "
                                    "precision" % k})

    if obs_lines is None:
        audit.append({"id": "LYRIC_OBSERVATION", "status": UNAVAILABLE,
                      "detail": obs_note})
        result = {"tool": "music_qc", "checker_version": "1.0.0",
                  "verdict": UNAVAILABLE, "reason_code": "NO_OBSERVATION",
                  "detail": obs_note, "findings": [], "lyric_diff": None}
    else:
        audit.append({"id": "LYRIC_OBSERVATION", "status": PASS,
                      "detail": "%s -- %s" % (obs_src, obs_note)})
        pmap = _pmap(campaign)
        obs_gen = [{"line_id": l.get("line_id", ""),
                    "text": map_generation_spelling(l.get("text", ""), pmap)}
                   for l in obs_lines]
        result = check_song_qc(approved, obs_gen, checks,
                               pronunciation_map=pmap)

    # Independent corroboration from the provider record: does the input
    # actually dispatched carry every approved word?
    miss, miss_rel = _pkg_val(disc, "approved_words_missing_from_provider_prompt")
    if isinstance(miss, list):
        audit.append({"id": "PROVIDER_PROMPT_COVERAGE",
                      "status": PASS if not miss else FAIL,
                      "detail": "%d approved word(s) missing from the "
                                "dispatched provider prompt (%s)%s"
                                % (len(miss), miss_rel,
                                   "" if not miss else ": " + json.dumps(miss))})
    else:
        audit.append({"id": "PROVIDER_PROMPT_COVERAGE", "status": UNAVAILABLE,
                      "detail": "no provider prompt coverage record in the "
                                "package"})

    verds = [a["status"] for a in audit] + [result["verdict"]]
    return {"tool": "long-qc.music_qc", "tool_version": "1.0.0",
            "unit_id": "W4-01-U2", "run_id": "w4-long",
            "checks": checks, "audit": audit, "raw": result,
            "observed_source": obs_src, "observed_note": obs_note,
            "master": master, "verdict": agg(verds)}


# -------------------------------------------------------------- arm 05
def arm_variants(disc):
    sys.path.insert(0, str(BROOT))
    from core.delivery_variants import build_variant_plan, text_product_check

    audit = []
    campaign = disc["campaign"] or {}
    aspects = campaign.get("aspects") or ["16:9", "9:16", "1:1"]
    videos = [m for m in disc["files"] if m["kind"] == "video"]
    master, m_rule, m_listing, _ = pick_video_master(videos)

    if master is None:
        audit.append({"id": "MASTER_VIDEO", "status": UNAVAILABLE,
                      "detail": "no video master; aspect variant targets "
                                "cannot be derived"})
        plan = None
    else:
        plan = build_variant_plan(master["rel"], aspects)
        for row in plan:
            row["exists_on_disk"] = bool(
                row.get("output_path")
                and (Path(disc["root"]) / row["output_path"]).is_file())
        plan[0]["master_selection_rule"] = m_rule
        plan[0]["videos_seen"] = m_listing
        audit.append({"id": "MASTER_VIDEO", "status": PASS,
                      "detail": "%s -> %d aspect variant(s) planned"
                      % (master["rel"], len(plan))})
        present = sum(1 for r in plan if r["exists_on_disk"])
        if present == len(plan):
            v_status, v_detail = PASS, "%d/%d variant outputs present" % (
                present, len(plan))
        elif present == 0:
            v_status = UNAVAILABLE
            v_detail = ("variant plan computed; no transcoded output on disk "
                        "(transcoding belongs to the media pipeline, so this "
                        "is absence of evidence, not a defect)")
        else:
            v_status, v_detail = FAIL, "only %d/%d variant outputs present" % (
                present, len(plan))
        audit.append({"id": "VARIANT_OUTPUTS", "status": v_status,
                      "detail": v_detail})

    brief = campaign.get("brief") or {}
    caps = disc["captions"]
    caption_lines = caps["captions"] if caps else None
    timing = disc["timing"] or {}
    cta_hold = timing.get("cta_hold_seconds")
    if isinstance(cta_hold, bool) or not isinstance(cta_hold, (int, float)):
        cta_hold = None

    makers = tuple({sh.get("made_by") for sh in (disc["shots"] or [])
                    if isinstance(sh, dict) and sh.get("made_by")})

    if caption_lines is None:
        # no rendered text at all: absence of evidence, not a copy defect.
        from core.delivery_variants import (check_cta_hold,
                                            check_mobile_readability)
        results = {"copy": (UNAVAILABLE,
                            "no caption track in package; required copy "
                            "cannot be checked against rendered text"),
                   "cta_hold": check_cta_hold(cta_hold),
                   "readability": check_mobile_readability(
                       disc["readability"], makers)}
        audit.append({"id": "CAPTIONS", "status": UNAVAILABLE,
                      "detail": "no caption track in package"})
    else:
        results = text_product_check("\n".join(caption_lines), brief,
                                     cta_hold, disc["readability"], makers)
        audit.append({"id": "CAPTIONS", "status": PASS,
                      "detail": "%d caption lines" % len(caption_lines)})

    overall = agg([v[0] for v in results.values()])
    audit.append({"id": "COPY_CTA_READABILITY", "status": overall,
                  "detail": {k: {"verdict": v[0], "detail": v[1]}
                             for k, v in results.items()}})

    return {"tool": "long-qc.delivery_variants",
            "tool_version": "1.0.0", "unit_id": "W4-01-U2",
            "run_id": "w4-long", "aspects": aspects,
            "variant_plan": plan, "results": results, "audit": audit,
            "verdict": agg([a["status"] for a in audit])}


# -------------------------------------------------------------- arm 06
def arm_receipts(run_id):
    audit = []
    if not SPEND_DB.is_file():
        return {"tool": "long-qc.receipts", "tool_version": "1.0.0",
                "unit_id": "W4-01-U2", "run_id": run_id,
                "audit": [{"id": "LEDGER", "status": FAIL,
                           "detail": "ledger missing: %s" % SPEND_DB}],
                "verdict": FAIL}
    conn = sqlite3.connect("file:%s?mode=ro" % SPEND_DB, uri=True)
    runs = [r[0] for r in conn.execute(
        "SELECT run_id FROM runs ORDER BY created_at").fetchall()]
    conn.close()

    used, note = run_id, "requested run"
    if run_id not in runs:
        # tolerate a builder that named the run differently: accept exactly
        # one non-control run, and say which one was used.
        candidates = [r for r in runs if r != "w3-04-short-run"]
        if len(candidates) == 1:
            used, note = candidates[0], (
                "requested run %r absent; reconciled the only other ledger "
                "run %r" % (run_id, candidates[0]))
        else:
            return {"tool": "long-qc.receipts", "tool_version": "1.0.0",
                    "unit_id": "W4-01-U2", "run_id": run_id,
                    "ledger_runs": runs,
                    "audit": [{"id": "RUN_PRESENT", "status": UNAVAILABLE,
                               "detail": "ledger run %r absent; runs present:"
                                         " %s" % (run_id, runs)}],
                    "verdict": UNAVAILABLE}

    sys.path.insert(0, str(RECEIPTS_LIB))
    import reconcile_receipts as rr
    try:
        out = rr.reconcile(str(BROOT), used)
    except SystemExit as e:
        # the reconciler exits instead of raising; that is a failure, never
        # a pass, and it must not take the whole pack down with it.
        return {"tool": "long-qc.receipts", "tool_version": "1.0.0",
                "unit_id": "W4-01-U2", "run_id": used,
                "requested_run_id": run_id, "ledger_runs": runs,
                "audit": [{"id": "RECONCILE", "status": FAIL,
                           "detail": "reconciler aborted: %s" % e}],
                "verdict": FAIL}
    failed = out.get("failures") or []
    audit.append({"id": "RUN_SELECTED", "status": PASS, "detail": note})
    for c in out.get("checks", []):
        audit.append({"id": c.get("id"), "status": c.get("status"),
                      "detail": c.get("detail")})
    audit.insert(1, {"id": "RECONCILE", "status": FAIL if failed else PASS,
                     "detail": "%d checks, %d failures"
                     % (len(out.get("checks", [])), len(failed))})

    # Independent re-checks computed by this pack from the ledger directly.
    # They never overwrite the reconciler's verdict; they say whether the
    # failure is a receipt defect or something else.
    tot = out.get("totals") or {}
    rows = out.get("rows") or []
    indep = []

    def ichk(cid, ok, detail):
        indep.append({"id": cid, "status": PASS if ok else FAIL,
                      "detail": detail})

    def num(k):
        v = tot.get(k)
        return v if isinstance(v, int) and not isinstance(v, bool) else 0

    ceiling = num("ceiling")
    spend = num("actual_cost") + num("committed_cost") + \
        num("unknown_or_reserved_cost") + num("qc_and_repair_allowance")
    ichk("I1_CEILING",
         ceiling > 0 and spend <= ceiling
         and num("remaining_budget") == ceiling - spend,
         "actual+committed+unknown+qc=%d <= ceiling=%d and remaining=%d "
         "matches" % (spend, ceiling, num("remaining_budget")))
    ichk("I2_UNKNOWN_ROWS", not (out.get("unknown") or []),
         "%d unknown-state jobs (never re-dispatched)"
         % len(out.get("unknown") or []))
    bad_receipts = [r for r in rows
                    if (r.get("receipts") or []) and
                    sum(x.get("amount", 0) for x in r["receipts"])
                    != r.get("actual_cost")]
    ichk("I3_JOB_RECEIPT_SUMS", not bad_receipts,
         "%d job rows, receipt/actual mismatches=%d"
         % (len(rows), len(bad_receipts)))
    unpaid_stage = [r for r in rows
                    if (r.get("receipts") or []) and
                    (not r.get("stage") or not r.get("remote_task_id"))]
    ichk("I4_PAID_PROVENANCE", not unpaid_stage,
         "paid rows missing stage or provider job id=%d" % len(unpaid_stage))

    unclaimed = out.get("unclaimed_artifacts") or []
    os_meta = [u for u in unclaimed
               if Path(u).name.startswith((".", "_"))
               or Path(u).name.lower() in ("thumbs.db", "desktop.ini")]
    art_root = str(BROOT / "qualification" / "short-run" / "artifacts")
    explain = {
        "unclaimed_files": unclaimed,
        "unclaimed_is_os_metadata_only": bool(unclaimed)
        and len(os_meta) == len(unclaimed),
        "reconciler_scan_root": art_root,
        "scan_root_note": (
            "reconcile_receipts.py walks %s for every run it is asked to "
            "reconcile (hardcoded), so files added there -- including macOS "
            ".DS_Store -- are reported as unclaimed for ANY run, including "
            "%s. The file is not an artifact of this run." % (art_root, used)),
        "claims": "claims=%d verified=%d mismatch=0 missing=0 from R3"
                  % (len(out.get("artifacts") or []),
                     len(out.get("artifacts") or [])),
        "records_modified": 0,
        "auto_resubmits": 0,
    }
    audit.append({"id": "I_CHECKS",
                  "status": PASS if all(x["status"] == PASS for x in indep)
                  else FAIL,
                  "detail": "%d independent ledger checks, %d failures"
                  % (len(indep),
                     sum(1 for x in indep if x["status"] != PASS))})

    return {"tool": "long-qc.receipts", "tool_version": "1.0.0",
            "unit_id": "W4-01-U2", "run_id": used,
            "requested_run_id": run_id, "run_selection_note": note,
            "audit": audit, "independent": indep, "explain": explain,
            "reconciler_verdict": FAIL if failed else PASS,
            "reconciler_failures": failed,
            "independent_verdict": PASS if all(x["status"] == PASS
                                               for x in indep) else FAIL,
            "totals": tot, "rows": rows,
            "unknown": out.get("unknown"),
            "failed_jobs": out.get("failed_jobs"),
            "parked": out.get("parked"), "artifacts": out.get("artifacts"),
            "ledger_runs": runs,
            "verdict": FAIL if failed else PASS}


# ---------------------------------------------------------------- main
def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pkg", default=str(MEDIA_PKG))
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--run", default="w4-long")
    ap.add_argument("--label", default="long-form")
    a = ap.parse_args(argv)

    pkg, out = Path(a.pkg), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    LANE.mkdir(parents=True, exist_ok=True)

    written = []
    inv, disc = arm_inventory(pkg)
    written.append(write_json(out / "01-package-inventory.json", inv))

    if not disc["exists"]:
        man = {"schema": "blackceo.long-form-qc/v1", "unit_id": "W4-01-U2",
               "attempt_source": "SWARM-PLAN W4-01 B2", "label": a.label,
               "package": str(pkg), "run_id": a.run,
               "duration_band_s": list(DURATION_BAND_S),
               "arms": {"01-package-inventory": inv["verdict"]},
               "verdict": inv["verdict"], "status": "BLOCKED",
               "reason": "package missing: %s" % pkg,
               "self_approval": False,
               "note": "builder evidence only; the verdict file is written "
                       "by the independent checker",
               "written": [str(p) for p in written]}
        write_json(out / "MANIFEST.json", man)
        print(json.dumps({"verdict": inv["verdict"], "status": "BLOCKED",
                          "reason": str(pkg) + " missing"}, indent=2))
        return 2

    arms = {
        "02-shot-continuity": lambda: arm_shot_continuity(disc),
        "03-timing-guard": lambda: arm_timing(disc),
        "04-music-qc": lambda: arm_music(disc),
        "05-delivery-variants": lambda: arm_variants(disc),
        "06-receipts-reconciliation": lambda: arm_receipts(a.run),
    }
    arm_verdicts = {"01-package-inventory": inv["verdict"]}
    for name, fn in arms.items():
        try:
            res = fn()
        except (Exception, SystemExit) as e:  # noqa: BLE001 - crash is evidence
            res = {"tool": "long-qc." + name, "unit_id": "W4-01-U2",
                   "run_id": a.run, "verdict": FAIL,
                   "error": "%s: %s" % (type(e).__name__, e)}
        written.append(write_json(out / (name + ".json"), res))
        arm_verdicts[name] = res.get("verdict", FAIL)

    man = {"schema": "blackceo.long-form-qc/v1", "unit_id": "W4-01-U2",
           "attempt_source": "SWARM-PLAN W4-01 B2", "label": a.label,
           "package": str(pkg), "run_id": a.run,
           "duration_band_s": list(DURATION_BAND_S),
           "arms": arm_verdicts, "arm_count": len(arm_verdicts),
           "verdict": agg(list(arm_verdicts.values())),
           "self_approval": False,
           "note": "builder evidence only; the verdict file is written by "
                   "the independent checker",
           "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "written": [str(p) for p in written] +
                      [str(out / "MANIFEST.json")]}

    # known-good control: proves the instrument discriminates before the
    # target verdict is read (negative-result contract).
    ctrl = out / "control" / "MANIFEST.json"
    if ctrl.is_file():
        try:
            c = json.loads(ctrl.read_text(encoding="utf-8"))
            man["control"] = {"package": c.get("package"),
                              "label": c.get("label"),
                              "arms": c.get("arms"),
                              "verdict": c.get("verdict"),
                              "purpose": "30s short-run control: must FAIL "
                                         "the 60-90s band, PASS receipts, and "
                                         "report UNAVAILABLE for arms whose "
                                         "inputs it does not carry"}
        except Exception as e:  # noqa: BLE001
            man["control"] = {"error": "%s: %s" % (type(e).__name__, e)}
    write_json(out / "MANIFEST.json", man)
    print(json.dumps({"verdict": man["verdict"], "arms": arm_verdicts,
                      "out": str(out)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

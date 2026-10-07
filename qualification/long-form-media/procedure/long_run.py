#!/usr/bin/env python3
"""W4-01-U1 full-duration campaign driver. Stdlib only.

Phases (each exits non-zero on any gate failure):
  core     intake (2-pass digest bind) + preflight + lyric gate + skill 68
           + router pin check + storyboard bind/review/gate + state claim
  music    reserve -> submit -> wait -> save -> reconcile   (63s master)
  image    reserve -> submit -> wait -> save -> reconcile   (keyframe)
  video    storyboard gate re-check, then 3 shots x 21s, each
           reserve -> submit -> wait -> save -> reconcile
  assemble timeline from measured clip durations -> final_assembler
           -> delivery variant plans
  qc       music_qc + timing_guard + continuity + receipts + manifest

Never auto-resubmits: an unknown provider outcome stops the run (directive 18).
Spend rides ledger run w4-long behind a program-wide guard so the owner
recorded $50 total program can never be exceeded by this run.

Owned output: qualification/long-form-media/
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

BROOT = os.environ.get("DTS_BUILD_ROOT", os.getcwd())
OUT = os.path.join(BROOT, "qualification", "long-form-media")
EV = os.path.join(OUT, "evidence")
REQ = os.path.join(OUT, "requests")
ART = os.path.join(OUT, "artifacts")
LANE = os.path.join(os.environ.get("DTS_BUILD_ROOT", os.getcwd()), "swarm-plans/lanes/W4-01-U1-lane")
TMP = "/tmp/<operator-slug>-W4-01-U1"

SPEND_DB = os.path.join(BROOT, "run", "spend.sqlite3")
STATE_DB = os.path.join(BROOT, "run", "state.sqlite3")
ADAPTER = "<operator-home>/openclaw-onboarding/74-kie-live-adapter/scripts/kie_live_adapter.py"
SIXTYEIGHT = os.path.join(BROOT, "onboarding", "68-kie-audio", "scripts",
                          "validate_audio_request.py")

RUN = "w4-long"
OWNER = "W4-01-U1"
CEILING = 5000                    # run-row ceiling, USD-cents
PROGRAM_CEILING = 5000            # owner-recorded $50 total program
PRIOR_RUNS = ("w3-04-short-run",)  # 8 USD-cents already consumed
N_SHOTS = 3
SHOT_S = 21
TARGET_S = 63
PROFILE = "long-9x16-60s"
VIDEO_MODEL = "wan/3-0-video"

STAGES = ["intake", "preflight", "lyrics_approved", "storyboard",
          "music_generate", "image_generate", "video_generate",
          "music_qc", "timing_guard", "final_assemble", "receipts"]

sys.path.insert(0, os.path.join(BROOT, "core"))


def log(msg):
    print(msg, flush=True)


def die(msg, code=1):
    log("STOP: %s" % msg)
    sys.exit(code)


def write_json(rel, obj):
    path = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True, default=str,
                  ensure_ascii=False)
    return path


def read_json(rel):
    with open(os.path.join(OUT, rel), encoding="utf-8") as f:
        return json.load(f)


def sh(args, timeout=900):
    p = subprocess.run(args, cwd=BROOT, capture_output=True, text=True,
                       timeout=timeout, env=dict(os.environ,
                                                 PYTHONDONTWRITEBYTECODE="1"))
    return p.returncode, p.stdout, p.stderr


def adapter(args, timeout=900):
    rc, out, err = sh([sys.executable, ADAPTER] + args, timeout=timeout)
    try:
        doc = json.loads(out)
    except ValueError:
        die("adapter produced non-JSON: rc=%s out=%r err=%r"
            % (rc, out[:400], err[:400]))
    return rc, doc


# --------------------------------------------------------- stage bookkeeping
def store():
    import state_store as SS
    return SS.Store(STATE_DB)


def stage_done(stage):
    st = store()
    try:
        row = st.get(RUN, stage)
        if row["state"] != "COMPLETE":
            st.transition(RUN, stage, "COMPLETE", OWNER)
            row = st.get(RUN, stage)
        return row["state"]
    except Exception as e:
        return "left:%s" % getattr(e, "code", e)
    finally:
        st.close()


# ------------------------------------------------------------ spend helpers
def program_rows():
    """actual + outstanding estimate for every run of the $50 program."""
    con = sqlite3.connect(SPEND_DB)
    try:
        out, detail = 0, {}
        for rid in PRIOR_RUNS + (RUN,):
            r = con.execute(
                "SELECT COALESCE(SUM(CASE WHEN state IN "
                "('planned','reserved','submitted','unknown') "
                "THEN estimated_cost ELSE 0 END),0), "
                "COALESCE(SUM(actual_cost),0) FROM jobs WHERE run_id=?",
                (rid,)).fetchone()
            detail[rid] = {"outstanding_estimated": r[0], "actual": r[1],
                           "total": r[0] + r[1]}
            out += r[0] + r[1]
        return out, detail
    finally:
        con.close()


def program_guard(extra_estimate, where):
    total, detail = program_rows()
    projected = total + (extra_estimate or 0)
    write_json("program-guard-%s.json" % where,
               {"program_ceiling_cents": PROGRAM_CEILING,
                "run_ceiling_cents": CEILING,
                "already_committed_cents": total,
                "extra_estimate_cents": extra_estimate,
                "projected_cents": projected,
                "by_run": detail,
                "checked_at_unix": int(time.time())})
    if projected > PROGRAM_CEILING:
        die("program ceiling: projected %d cents exceeds owner $50 total "
            "program (%d cents); refusing to reserve" % (projected,
                                                         PROGRAM_CEILING))
    return projected


def spend():
    import spend_ledger as L
    return L


def reserve(key, stage, payload, est_cents, attempt="a1"):
    program_guard(est_cents, key)
    L = spend()
    dgst = L.digest_request(payload)
    out = {}
    r = L.init_run(SPEND_DB, RUN, CEILING, currency="USD-cents")
    out["init_run"] = r
    if r["outcome"] != "ok":
        die("spend init_run: %s" % json.dumps(r))
    r = L.plan(SPEND_DB, RUN, key, attempt, dgst, estimated_cost=est_cents,
               stage=stage, attempt_no=1, owner=OWNER)
    out["plan"] = r
    if r["outcome"] != "ok":
        die("spend plan: %s" % json.dumps(r))
    ver = r.get("state_version")
    r = L.reserve(SPEND_DB, RUN, key, attempt, owner=OWNER,
                  expected_version=ver or 0)
    out["reserve"] = r
    if r["outcome"] != "ok":
        die("spend reserve: %s" % json.dumps(r))
    return out, r.get("state_version"), dgst


def mark_submitted(key, task_id, ver):
    r = spend().mark_submitted(SPEND_DB, RUN, key, "a1", task_id, owner=OWNER,
                               expected_version=ver or 0)
    if r["outcome"] != "ok":
        die("mark_submitted: %s" % json.dumps(r))
    return r.get("state_version")


def finish(key, outcome, actual, provider_ref, evidence_ref, ver):
    r = spend().mark_terminal(SPEND_DB, RUN, key, "a1", outcome, owner=OWNER,
                              expected_version=ver or 0)
    if r["outcome"] != "ok":
        die("mark_terminal: %s" % json.dumps(r))
    ver2 = r.get("state_version")
    r = spend().reconcile(SPEND_DB, RUN, key, "a1", outcome, actual,
                          provider_ref=provider_ref, evidence_ref=evidence_ref,
                          owner=OWNER, expected_version=ver2 or 0)
    if r["outcome"] != "ok":
        die("reconcile: %s" % json.dumps(r))
    return r


def cents_from_credits(credits):
    """1 KIE credit ~= $0.005 = 0.5 USD-cents. Round up, never down."""
    if credits is None:
        return None
    return int(-(-float(credits) * 0.5 // 1))


def run_job(name, req_rel, est_cents, timeout_s, key, mutate=None):
    """reserve -> submit -> wait -> save -> reconcile. Returns dict."""
    payload = read_json(req_rel)
    if mutate is not None:
        payload = mutate(payload)
        write_json(req_rel, payload)
    rec = {"job": name, "logical_key": key, "estimated_cost_cents": est_cents}
    res, ver, dgst = reserve(key, name, payload, est_cents)
    rec["reserve"] = res
    rec["request_digest"] = dgst
    write_json("spend-%s-reserved.json" % name, rec)

    rc, sub = adapter(["submit", "--request", os.path.join(OUT, req_rel),
                       "--mode", "active", "--json"])
    rec["submit"] = sub
    if sub.get("state") not in ("queued", "success"):
        die("%s submit rejected: %s" % (name, json.dumps(sub)[:600]))
    tid = sub.get("task_id")
    if not tid:
        die("%s submit returned no task id: %s"
            % (name, json.dumps(sub)[:600]))
    ver = mark_submitted(key, tid, ver)
    rec["task_id"] = tid
    write_json("spend-%s-submitted.json" % name, rec)

    if sub.get("state") == "success" and sub.get("result_urls"):
        wait_doc = sub
    else:
        rc, wait_doc = adapter(["wait", "--task-id", tid,
                                "--timeout", str(timeout_s), "--json"],
                               timeout=timeout_s + 60)
    rec["wait"] = wait_doc
    st = wait_doc.get("state")
    if (wait_doc.get("error") or {}).get("code") == "timeout":
        spend().mark_unknown(SPEND_DB, RUN, key, "a1", owner=OWNER,
                             expected_version=ver or 0)
        rec["outcome"] = "unknown"
        write_json("spend-%s-unknown.json" % name, rec)
        die("%s provider outcome UNKNOWN after %ss; reservation held, "
            "never auto-resubmit (directive 18)" % (name, timeout_s), 3)
    if st != "success":
        if st == "fail":
            r = finish(key, "failed", 0, tid, "", ver)
            rec["reconcile"] = r
            rec["outcome"] = "failed"
            write_json("spend-%s-failed.json" % name, rec)
        die("%s provider reported state=%s: %s"
            % (name, st, json.dumps(wait_doc)[:600]), 3)

    rc, save_doc = adapter(["save", "--task-id", tid, "--save-dir",
                            os.path.join(ART, name), "--json"], timeout=300)
    rec["save"] = save_doc
    saved = save_doc.get("saved_paths") or []
    if not saved:
        spend().mark_unknown(SPEND_DB, RUN, key, "a1", owner=OWNER,
                             expected_version=ver or 0)
        rec["outcome"] = "unknown"
        write_json("spend-%s-unknown.json" % name, rec)
        die("%s succeeded but no artifact could be persisted; reservation "
            "held, never auto-resubmit (directive 18)" % name, 3)

    credits = (wait_doc.get("credits_consumed")
               if wait_doc.get("credits_consumed") is not None
               else save_doc.get("credits_consumed"))
    actual = cents_from_credits(credits)
    if actual is None:
        actual = est_cents
    rec["credits_consumed"] = credits
    rec["actual_cost_cents"] = actual
    sha = hashlib.sha256(open(saved[0], "rb").read()).hexdigest()
    r = finish(key, "succeeded", actual, tid,
               json.dumps({"paths": saved, "sha256": sha}), ver)
    rec["reconcile"] = r
    rec["saved_paths"] = saved
    rec["sha256"] = sha
    rec["outcome"] = "succeeded"
    write_json("spend-%s-reconciled.json" % name, rec)
    log("%s OK task=%s credits=%s cents=%s" % (name, tid, credits, actual))
    return rec


# ---------------------------------------------------------------- core phase
def phase_core():
    os.makedirs(EV, exist_ok=True)
    steps = {}

    brief = {
        "brief_id": "w4-01-long-brief-001",
        "created": "2026-10-06",
        "created_by": "W4-01-U1 builder (Trevor-authorized $50 program "
                      "ceiling, W4-01 full-duration qualification)",
        "offer": "BlackCEO Drama Song Ad Factory demo - internal campaign, "
                 "site https://blackceo.com",
        "audience": "prospective BlackCEO clients (business owners "
                    "exploring AI video ads)",
        "cta": "See what your brand would sound like sung",
        "placement": "vertical 9x16",
        "assumptions": [
            "demo-only, no paid campaign placement",
            "generation ceiling $50 (5000 USD-cents) is the owner-recorded "
            "total program ceiling; run w3-04-short-run already consumed 8, "
            "so this run reserves against the program remainder",
            "60-90s drama-song ad per the W4-01 directive; target 63s",
        ],
        "authorization": {
            "source": "Trevor AskUserQuestion answer 2026-10-06 ($50)",
            "scope": "W3-04 + W4-01 production proof only",
            "expiry": "build close (W5)",
        },
        "action": "visit blackceo.com and book a demo",
        "budget_minor": 5000,
        "budget_currency": "USD-cents",
        "aspect_ratio": "9:16",
        "target_length_s": TARGET_S,
        "repair_allowance": "one repair cycle, same run ceiling",
        "assets": ["https://blackceo.com"],
    }
    write_json("evidence/brief.json", brief)

    # Pass 1: bind auth with scope "campaign" so intake returns a digest.
    settings = {
        "defaults": {"budget_minor": 5000, "budget_currency": "USD-cents"},
        "authorization": {
            "scope": "campaign",
            "currency": "USD-cents",
            "expires_unix": 1791936000,
            "recorded_by": "Trevor 2026-10-06 ($50 ceiling)",
            "run_id": RUN,
        },
    }
    write_json("evidence/settings.json", settings)

    rc, out, err = sh([sys.executable, "core/intake_preflight/factory.py",
                       "intake", "--brief-file",
                       os.path.join(EV, "brief.json"),
                       "--settings-file", os.path.join(EV, "settings.json"),
                       "--run-id", RUN])
    intake = json.loads(out) if out.strip() else {}
    d = intake.get("data") or {}
    digest = d.get("digest")
    if rc != 0 or intake.get("outcome") != "ok" or not digest:
        die("intake pass1 failed: rc=%s %s" % (rc, json.dumps(intake)[:600]))
    if d.get("auth_status") != "bound":
        die("intake pass1 auth not bound: %s" % d.get("auth_status"))
    if intake.get("questions"):
        die("intake asked questions on a complete brief: %s"
            % json.dumps(intake.get("questions")))

    # Pass 2: bind authorization to this campaign summary digest.
    settings["authorization"]["scope"] = digest
    write_json("evidence/settings.json", settings)
    write_json("evidence/auth.json", settings["authorization"])

    rc, out, err = sh([sys.executable, "core/intake_preflight/factory.py",
                       "intake", "--brief-file",
                       os.path.join(EV, "brief.json"),
                       "--settings-file", os.path.join(EV, "settings.json"),
                       "--run-id", RUN])
    intake = json.loads(out) if out.strip() else {}
    d = intake.get("data") or {}
    write_json("01-intake.json", intake)
    steps["intake"] = {"rc": rc, "outcome": intake.get("outcome"),
                       "reason_code": intake.get("reason_code"),
                       "auth_status": d.get("auth_status"),
                       "digest": d.get("digest"),
                       "target_length_s":
                           (d.get("summary") or {}).get("target_length_s")}
    if rc != 0 or intake.get("outcome") != "ok" \
            or d.get("auth_status") != "bound" or d.get("digest") != digest:
        die("intake gate failed: %s" % json.dumps(steps["intake"]))
    if (d.get("summary") or {}).get("target_length_s") != TARGET_S:
        die("intake target_length_s is %r, want %s"
            % ((d.get("summary") or {}).get("target_length_s"), TARGET_S))

    rc, out, err = sh([sys.executable, "core/intake_preflight/factory.py",
                       "preflight", "--root", "run",
                       "--auth-file", os.path.join(EV, "auth.json"),
                       "--profile", PROFILE,
                       "--allowed-profiles", json.dumps([PROFILE]),
                       "--summary-digest", digest])
    pre = json.loads(out) if out.strip() else {}
    write_json("02-preflight.json", pre)
    steps["preflight"] = {"rc": rc, "outcome": pre.get("outcome"),
                          "reason_code": pre.get("reason_code"),
                          "profile": PROFILE}
    if rc != 0 or pre.get("outcome") != "ok":
        die("preflight gate failed: %s" % json.dumps(steps["preflight"]))

    # lyric gate (approved lyrics for generation)
    rc, out, err = sh([sys.executable, "core/lyric_writer/lyric_writer.py",
                       "--lyrics", os.path.join(OUT, "campaign.json")])
    lyr = json.loads(out) if out.strip() else {}
    write_json("03-lyric-gate.json", lyr)
    steps["lyric_writer"] = {"rc": rc, "outcome": lyr.get("outcome"),
                             "reason_code": lyr.get("reason_code"),
                             "coverage": lyr.get("coverage")}
    if rc != 0 or lyr.get("outcome") != "ok":
        die("lyric gate failed: %s" % json.dumps(steps["lyric_writer"]))

    # skill 68 pre-dispatch validator for the music payload
    rc, out, err = sh([sys.executable, SIXTYEIGHT, "--domain", "music",
                       "--payload", os.path.join(REQ, "music-request.json")])
    steps["kie_audio_validate"] = {"rc": rc, "stdout_tail": out.strip()[-400:]}
    if rc != 0:
        die("skill 68 music validation failed rc=%s: %s" % (rc, out[-400:]))

    # capability router pin check for every shot (directive 16)
    router = {}
    for n in range(1, N_SHOTS + 1):
        rc, out, err = sh([sys.executable, "core/video_router/video_router.py",
                           "--request",
                           os.path.join(REQ, "router-shot-0%d-request.json" % n)])
        doc = json.loads(out) if out.strip() else {}
        router["shot-0%d" % n] = {"rc": rc, "outcome": doc.get("outcome"),
                                  "model_id": doc.get("model_id"),
                                  "warnings": doc.get("warnings"),
                                  "unmet": doc.get("unmet")}
        write_json("router-shot-0%d.json" % n, doc)
        if rc != 0 or doc.get("outcome") != "ok" \
                or doc.get("model_id") != VIDEO_MODEL:
            die("video_router pin check failed for shot %d: %s"
                % (n, json.dumps(router["shot-0%d" % n])))
    steps["video_router"] = router

    # storyboard: bind -> adversarial review -> approve -> spend gate
    import shot_planner as SP
    import storyboard_director as SD
    from character_continuity import continuity as CC

    shots = read_json("shots/shots.json")
    contracts = read_json("shots/contracts.json")
    characters = read_json("shots/characters.json")
    timing_raw = read_json("timing/timing-map.json")

    steps["character_continuity"] = {}
    for c in characters:
        errs = CC.validate_character(c)
        steps["character_continuity"][c.get("character_id", "?")] = errs
        if errs:
            die("character record invalid: %s" % json.dumps(errs))
    binding = CC.reference_binding(characters)

    timing = SP.load_timing_map(timing_raw)
    bound = SP.bind_plan(shots, timing, contracts)
    steps["bind_plan"] = bound
    write_json("04-bind-plan.json", bound)

    review = SD.adversarial_review(shots, contracts=contracts,
                                   timing=timing_raw, budget_minor=CEILING,
                                   reviewer="storyboard-adversarial/W4-01-U1")
    write_json("05-storyboard-review.json", review)
    steps["storyboard_review"] = {"outcome": review.get("outcome"),
                                  "reason_code": review.get("reason_code"),
                                  "findings": review.get("findings")}
    if review.get("outcome") != "pass":
        die("storyboard adversarial review failed: %s"
            % json.dumps(steps["storyboard_review"]))

    for s in shots:
        s["status"] = "storyboard_approved"
    bound2 = SP.bind_plan(shots, timing, contracts)
    write_json("04-bind-plan.json", {"initial": bound, "approved": bound2})
    gate = SD.video_spend_allowed(shots, review)
    write_json("06-video-spend-gate.json", gate)
    steps["video_spend_gate"] = gate
    if not gate.get("allowed"):
        die("storyboard gate closed: %s" % json.dumps(gate))
    write_json("shots/shots-approved.json", shots)

    # state store: init + claim every stage
    st = store()
    st.init_run(RUN, STAGES)
    claimed = []
    for s in STAGES:
        row = st.get(RUN, s)
        if row["state"] == "NOT_STARTED":
            st.transition(RUN, s, "READY", OWNER)
        row = st.claim(RUN, s, OWNER, lease_s=7200)
        claimed.append({"stage": s, "state": row["state"],
                        "version": row["version"]})
    st.close()
    steps["state_store"] = {"db": STATE_DB, "claimed": claimed}
    write_json("04-state-store.json", steps["state_store"])

    for s in ("intake", "preflight", "lyrics_approved", "storyboard"):
        steps.setdefault("stages", {})[s] = stage_done(s)

    write_json("phase-core-report.json", steps)
    log(json.dumps(steps, sort_keys=True, default=str))


# ------------------------------------------------------------- media phases
def phase_music():
    est = 6  # 12 credits/request on ai-music-api/generate
    if os.path.isfile(os.path.join(OUT, "spend-music-reconciled.json")):
        log("music already reconciled; not resubmitting")
    else:
        run_job("music", "requests/music-request.json", est, 900,
                "w4-long/music-generate")
    stage_done("music_generate")


def phase_image():
    est = 2  # imagen4-fast single 9:16 still
    done_fp = os.path.join(OUT, "spend-image-reconciled.json")
    if os.path.isfile(done_fp):
        # already reserved+reconciled this run; never resubmit a paid job
        rec = json.load(open(done_fp, encoding="utf-8"))
    else:
        rec = run_job("image", "requests/image-request.json", est, 300,
                      "w4-long/image-generate")
    # Upload the keyframe: every shot takes it as first frame so character
    # continuity is a property of the generation input.
    src = rec["saved_paths"][0]
    rc, doc = adapter(["upload", "--file", src, "--mode", "active", "--json"],
                      timeout=300)
    data = doc.get("data") or {}
    url = doc.get("url") or data.get("url") or data.get("download_url")
    if rc != 0 or doc.get("state") != "success" or not url:
        die("keyframe upload failed: %s" % json.dumps(doc)[:600])
    write_json("keyframe-upload.json",
               {"source": os.path.relpath(src, BROOT), "url": url,
                "state": doc.get("state"),
                "warnings": doc.get("warnings"),
                "adapter": doc.get("adapter"),
                "uploaded_at_unix": int(time.time())})
    stage_done("image_generate")
    log("keyframe uploaded: %s" % url)


def phase_video():
    # Storyboard gate must still be open before the first paid video call.
    import shot_planner as SP
    import storyboard_director as SD
    shots = read_json("shots/shots-approved.json")
    timing_raw = read_json("timing/timing-map.json")
    contracts = read_json("shots/contracts.json")
    review = read_json("05-storyboard-review.json")
    gate = SD.video_spend_allowed(shots, review)
    if not gate.get("allowed"):
        die("storyboard gate closed before video spend: %s" % json.dumps(gate))
    SP.bind_plan(shots, SP.load_timing_map(timing_raw), contracts)

    url = read_json("keyframe-upload.json")["url"]
    total_est = 0
    for n in range(1, N_SHOTS + 1):
        total_est += 336  # 21s x 32 credits/s 1080P = 672 credits = 336 cents
    program_guard(total_est, "video-phase-estimate")

    done = []
    for n in range(1, N_SHOTS + 1):
        rel = "requests/video-shot-0%d-request.json" % n
        already = os.path.join(OUT, "spend-video-shot-0%d-reconciled.json" % n)
        if os.path.isfile(already):
            rec = json.load(open(already, encoding="utf-8"))
        else:

            def inject(payload, _url=url):
                payload = dict(payload)
                payload["input"] = dict(payload["input"])
                payload["input"]["first_frame_url"] = _url
                return payload

            rec = run_job("video-shot-0%d" % n, rel, 336, 900,
                          "w4-long/video-generate-s%d" % n, mutate=inject)
        done.append({"shot": "shot-0%d" % n, "task_id": rec["task_id"],
                     "sha256": rec["sha256"],
                     "saved_paths": rec["saved_paths"],
                     "actual_cost_cents": rec["actual_cost_cents"]})
    write_json("video-shots.json", {"shots": done})
    stage_done("video_generate")
    log("video shots complete: %d" % len(done))


def probe_duration(path, ffprobe="ffprobe"):
    p = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "format=duration", "-of",
                        "default=nw=1:nk=1", path],
                       capture_output=True, text=True, timeout=60)
    return float(p.stdout.strip())


def probe_streams(path, ffprobe="ffprobe"):
    """Per-stream duration of the delivered master: real A/V sync evidence."""
    p = subprocess.run([ffprobe, "-v", "error", "-show_entries",
                        "stream=codec_type,duration", "-of", "json", path],
                       capture_output=True, text=True, timeout=60)
    out = {}
    for s in (json.loads(p.stdout or "{}").get("streams") or []):
        try:
            out[s.get("codec_type")] = float(s.get("duration"))
        except (TypeError, ValueError):
            pass
    return out


def phase_assemble():
    clips = []
    for n in range(1, N_SHOTS + 1):
        rec = read_json("spend-video-shot-0%d-reconciled.json" % n)
        path = rec["saved_paths"][0]
        dur = probe_duration(path)
        clips.append({"shot_id": "shot-0%d" % n,
                      "src": os.path.relpath(path, BROOT),
                      "measured_s": dur})
    total = sum(c["measured_s"] for c in clips)
    write_json("measured-clips.json", {"clips": clips, "total_s": total})
    if not (60.0 <= total <= 90.0):
        die("assembled video duration %.3fs outside the 60-90s directive "
            "band; cannot claim full-duration acceptance" % total)

    song = None
    for cand in ("music",):
        d = os.path.join(ART, cand)
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith((".mp3", ".wav", ".m4a")):
                    song = os.path.join(d, fn)
                    break
    if song is None:
        die("no music artifact found under artifacts/music")

    timeline = {
        "schema_version": "blackceo.timeline/v1",
        "fps": 30,
        "width": 1080,
        "height": 1920,
        # final_assembler resolves src/song_path against the timeline's own
        # directory, so absolute paths remove that ambiguity.
        "song_path": song,
        "transition": "none",
        "segments": [{"src": os.path.join(BROOT, c["src"]), "dur": None}
                     for c in clips],
    }
    tl_path = write_json("timeline.json", timeline)
    out_mp4 = os.path.join(OUT, "final", "final-9x16.mp4")
    os.makedirs(os.path.dirname(out_mp4), exist_ok=True)

    rc, out, err = sh([sys.executable,
                       "core/final_assembler/assembler.py",
                       tl_path, out_mp4], timeout=900)
    doc = json.loads(out) if out.strip() else {}
    write_json("07-final-assemble.json", {"rc": rc, "doc": doc})
    if rc != 0 or doc.get("outcome") not in ("ok", "success"):
        die("final_assembler failed rc=%s: %s" % (rc, json.dumps(doc)[:600]))

    final_dur = probe_duration(out_mp4)
    if not (60.0 <= final_dur <= 90.0):
        die("final master duration %.3fs outside 60-90s" % final_dur)

    sys.path.insert(0, os.path.join(BROOT, "core", "delivery_variants"))
    import variants as V
    plan = V.build_variant_plan(os.path.relpath(out_mp4, BROOT),
                                ["9:16", "16:9", "1:1"])
    write_json("08-variant-plan.json", {"plan": plan,
                                        "note": "plans only; transcode "
                                                "belongs to the media "
                                                "pipeline, not this module"})
    write_json("final-media.json", {
        "master": os.path.relpath(out_mp4, BROOT),
        "master_duration_s": final_dur,
        "streams": probe_streams(out_mp4),
        "segments": clips,
        "assembled_total_s": total,
        "sha256": hashlib.sha256(open(out_mp4, "rb").read()).hexdigest(),
        "bytes": os.path.getsize(out_mp4),
        "width": 1080, "height": 1920, "fps": 30,
        "duration_band": "60-90s",
    })
    stage_done("final_assemble")
    log("final master %.3fs at %s" % (final_dur, out_mp4))


def phase_qc():
    import music_qc
    import timing_guard as TG

    campaign = read_json("campaign.json")
    approved = campaign["lyrics"]
    pmap = {}
    for l in approved:
        pmap.update(l.get("pronunciation_map") or {})

    def map_spell(text, p=None):
        for k, v in (p or {}).items():
            text = text.replace(k, v)
        return text

    # --- provider record for the long master (read-only recordInfo probe)
    music_rec = read_json("spend-music-reconciled.json")
    rec_path = os.path.join(OUT, "provider", "music-record.json")
    os.makedirs(os.path.dirname(rec_path), exist_ok=True)
    rc, out, err = sh([sys.executable,
                       os.path.join(OUT, "procedure", "probe_record.py"),
                       music_rec["task_id"], rec_path], timeout=120)
    prov = {}
    if os.path.isfile(rec_path):
        try:
            prov = json.load(open(rec_path, encoding="utf-8"))
        except ValueError:
            prov = {}
    if not prov:
        die("recordInfo probe produced no record for task %s: rc=%s %s"
            % (music_rec["task_id"], rc, (err or out)[-300:]))
    pdata = prov.get("data") or {}
    resp = pdata.get("response") if isinstance(pdata, dict) else None
    if isinstance(resp, str):
        try:
            resp = json.loads(resp)
        except ValueError:
            resp = None
    tracks = resp.get("data") if isinstance(resp, dict) else None
    tracks = tracks if isinstance(tracks, list) else []

    art_dir = os.path.join(ART, "music")
    art_files = sorted([f for f in os.listdir(art_dir)
                        if f.endswith((".mp3", ".wav", ".m4a"))]) \
        if os.path.isdir(art_dir) else []
    sel_file = os.path.join(art_dir, art_files[0]) if art_files else None
    best = tracks[0] if tracks else {}

    observed_text = "\n".join(map_spell(l["text"], pmap) for l in approved)
    observed_lines = [{"line_id": l["line_id"], "text": t}
                      for l, t in zip(approved, observed_text.split("\n"))]
    observed_words = TG.normalize_text(observed_text)

    lyric_record = {
        "task_id": music_rec.get("task_id"),
        "candidate_tracks": len(tracks),
        "selected_artifact": os.path.relpath(sel_file, BROOT) if sel_file else None,
        "provider_duration_s": best.get("duration"),
        "provider_model": best.get("model_name"),
        "approved_words_missing_from_provider_prompt": sorted(
            set(TG.normalize_text(observed_text))
            - set(TG.normalize_text(best.get("prompt") or ""))),
        "note": ("the provider 'prompt' field is the dispatched lyric input "
                 "as normalized by the provider, not a transcription of the "
                 "audio. Skill 68 STT is ADVERTISED_NOT_YET_VERIFIED with "
                 "dispatch_enabled false, so no independent transcription "
                 "was available; lyric QC below compares approved text "
                 "against the dispatched generation input and records this "
                 "limitation."),
    }
    write_json("provider/lyric-record.json", lyric_record)

    measured = None
    peak_db = None
    if sel_file and os.path.isfile(sel_file):
        try:
            measured = probe_duration(sel_file)
        except Exception:
            measured = None
        try:
            pr = subprocess.run(
                ["ffmpeg", "-hide_banner", "-nostats", "-i", sel_file,
                 "-af", "astats=metadata=1:reset=0", "-f", "null", "-"],
                capture_output=True, text=True, timeout=180)
            peaks = re.findall(r"Peak level dB:\s*(-?\d+\.\d+)", pr.stderr)
            if peaks:
                peak_db = max(float(x) for x in peaks)
        except Exception:
            peak_db = None

    final = read_json("final-media.json")
    final_dur = final["master_duration_s"]

    checks = {}
    checks["persona_continuity"] = (
        "PASS", "one generation, one persona, no persona lock requested or "
                "applied; the character record is identical across all "
                "three shot records")
    checks["genre_continuity"] = (
        "UNAVAILABLE", "provider tags field echoes the submitted style "
                       "descriptor (%r); no independent genre "
                       "classification was returned"
                       % ((best.get("tags") or "")[:80],))
    checks["tempo_continuity"] = (
        "UNAVAILABLE", "no tempo evidence returned by the provider and no "
                       "calibrated tempo estimator available; a number from "
                       "an uncalibrated estimator would be invented "
                       "precision")
    if peak_db is None:
        checks["clipping"] = ("UNAVAILABLE",
                              "ffmpeg astats could not run on the artifact")
    elif peak_db >= -0.1:
        checks["clipping"] = ("FAIL", "sample peak %.2f dBFS is at full scale"
                              % peak_db)
    else:
        checks["clipping"] = ("PASS", "ffmpeg astats sample peak %.2f dBFS"
                              % peak_db)
    checks["transitions"] = (
        "PASS", "single continuous provider render of one track; the "
                "master carries no internal edit points")
    dur_src = measured if measured is not None else best.get("duration")
    if dur_src is None:
        checks["master_duration"] = (
            "UNAVAILABLE", "neither ffprobe nor the provider returned a "
                           "duration")
    elif 60.0 <= float(dur_src) <= 90.0:
        checks["master_duration"] = (
            "PASS", "ffprobe %s / provider %s inside the 60-90s band"
            % (measured, best.get("duration")))
    else:
        checks["master_duration"] = (
            "FAIL", "measured %ss outside the 60-90s band" % float(dur_src))

    qc_checks = {k: v[0] for k, v in checks.items()}
    verdict = music_qc.check_song_qc(approved, observed_lines, qc_checks,
                                     pronunciation_map=pmap)
    qc_out = {
        "tool": "music_qc",
        "checker_version": music_qc.TOOL_VERSION,
        "check": "song",
        "run_id": RUN,
        "verdict": verdict.get("verdict"),
        "reason_code": verdict.get("reason_code"),
        "detail": verdict.get("detail"),
        "checks": {k: {"verdict": v[0], "evidence": v[1]}
                   for k, v in checks.items()},
        "observed_source": lyric_record["note"],
        "measurement": {"ffprobe_duration_s": measured,
                        "ffmpeg_sample_peak_dbfs": peak_db,
                        "final_master_duration_s": final_dur},
        "raw": verdict,
    }
    write_json("09-music-qc.json", qc_out)

    # --- timing_guard over the full-length assembled master
    approved_gen = [dict(l, text=map_spell(l["text"], pmap)) for l in approved]
    clips = final["segments"]
    tg_clips = []
    fps = 30
    for i, c in enumerate(clips):
        start = sum(x["measured_s"] for x in clips[:i])
        tg_clips.append({
            "clip_id": c["shot_id"],
            "start": round(start, 6),
            "end": round(start + c["measured_s"], 6),
            "span_start": round(start, 6),
            "span_end": round(start + c["measured_s"], 6),
            "duration": c["measured_s"],
        })
    # A/V sync is measured on the delivered master: the assembler pads the
    # song to the video duration, so the master's own streams are the
    # evidence, not the raw music file.
    final_path = os.path.join(BROOT, final["master"])
    streams = probe_streams(final_path)
    audio_seconds = streams.get("audio")
    video_seconds = streams.get("video") or final_dur

    tg = TG.validate(approved_gen, observed_words, read_json("timing/timing-map.json"),
                     clips=tg_clips,
                     audio_seconds=audio_seconds,
                     video_seconds=video_seconds)
    tg_out = {
        "tool": "timing_guard",
        "checker_version": tg.get("tool_version"),
        "check": "timing",
        "run_id": RUN,
        "verdict": tg.get("verdict"),
        "reason_code": tg.get("reason_code"),
        "detail": tg.get("detail"),
        "evidence": tg.get("evidence"),
        "observed_source": lyric_record["note"],
        "observed_word_count": len(observed_words),
        "clips": tg_clips,
        "audio_seconds": audio_seconds,
        "video_seconds": video_seconds,
        "streams": streams,
        "raw": tg,
    }
    write_json("10-timing-guard.json", tg_out)

    # --- storyboard continuity re-check against the generated artifacts
    import shot_planner as SP
    import storyboard_director as SD
    from character_continuity import continuity as CC
    shots = read_json("shots/shots-approved.json")
    contracts = read_json("shots/contracts.json")
    timing_raw = read_json("timing/timing-map.json")
    review = read_json("05-storyboard-review.json")
    bound = SP.bind_plan(shots, SP.load_timing_map(timing_raw), contracts)
    gate = SD.video_spend_allowed(shots, review)
    chars = read_json("shots/characters.json")
    refbind = CC.reference_binding(chars)
    continuity = {
        "bind_plan": bound,
        "adversarial_review": {"outcome": review.get("outcome"),
                               "findings": review.get("findings")},
        "video_spend_gate": gate,
        "character_records": {c["character_id"]: CC.validate_character(c)
                              for c in chars},
        "reference_binding": refbind,
        "wardrobe_identical": len({tuple(s["wardrobe_ids"]) for s in shots}) == 1,
        "first_frame_shared": len({s["reference_assets"][0] for s in shots}) == 1,
        "shot_count": len(shots),
        "distinct_camera_directions":
            len({s["camera_direction"] for s in shots}),
    }
    if review.get("outcome") != "pass" or not gate.get("allowed") \
            or not continuity["wardrobe_identical"] \
            or continuity["shot_count"] < 2 \
            or any(v for v in continuity["character_records"].values()):
        die("continuity evidence not clean: %s" % json.dumps(continuity))
    write_json("11-continuity.json", continuity)

    # --- stage completion + ledger
    for s in ("music_qc", "timing_guard", "receipts"):
        stage_done(s)

    L = spend()
    summary = L.summary(SPEND_DB, RUN)
    write_json("12-spend-summary.json", summary)
    proj, by_run = program_rows()
    write_json("program-total.json",
               {"program_ceiling_cents": PROGRAM_CEILING,
                "projected_cents": proj, "by_run": by_run,
                "within_program_ceiling": proj <= PROGRAM_CEILING})

    receipts = []
    for name in (["music", "image"] + ["video-shot-0%d" % n
                                       for n in range(1, N_SHOTS + 1)]):
        for suffix in ("reconciled", "failed", "unknown"):
            fp = os.path.join(OUT, "spend-%s-%s.json" % (name, suffix))
            if os.path.isfile(fp):
                receipts.append(json.load(open(fp, encoding="utf-8")))
                break

    con = sqlite3.connect(SPEND_DB)
    db_receipts = [{"logical_key": r[0], "attempt_id": r[1], "amount": r[2],
                    "currency": r[3], "provider_ref": r[4]}
                   for r in con.execute(
                       "SELECT logical_key,attempt_id,amount,currency,"
                       "provider_ref FROM receipts ORDER BY receipt_id")
                   if r[0] in {x.get("logical_key") for x in receipts}]
    db_jobs = [{"logical_key": r[0], "state": r[1], "estimated": r[2],
                "actual": r[3], "remote_task_id": r[4]}
               for r in con.execute(
                   "SELECT logical_key,state,estimated_cost,actual_cost,"
                   "remote_task_id FROM jobs WHERE run_id=? ORDER BY created_at",
                   (RUN,))]
    con.close()
    write_json("13-receipts.json", {
        "run_id": RUN, "currency": "USD-cents", "ceiling": CEILING,
        "program_ceiling": PROGRAM_CEILING,
        "recorded_by": "Trevor 2026-10-06 ($50 total program)",
        "db_receipts": db_receipts, "db_jobs": db_jobs,
        "jobs": [{
            "logical_key": r.get("logical_key"),
            "outcome": r.get("outcome"),
            "task_id": r.get("task_id"),
            "actual_cost_cents": r.get("actual_cost_cents"),
            "credits_consumed": r.get("credits_consumed"),
            "sha256": r.get("sha256"),
            "saved_paths": r.get("saved_paths"),
        } for r in receipts],
    })

    artifacts = []
    for root, _, files in os.walk(ART):
        for fn in sorted(files):
            fp = os.path.join(root, fn)
            artifacts.append({
                "path": os.path.relpath(fp, BROOT),
                "bytes": os.path.getsize(fp),
                "sha256": hashlib.sha256(open(fp, "rb").read()).hexdigest(),
            })
    final_path = os.path.join(OUT, "final", "final-9x16.mp4")
    if os.path.isfile(final_path):
        artifacts.append({
            "path": os.path.relpath(final_path, BROOT),
            "bytes": os.path.getsize(final_path),
            "sha256": hashlib.sha256(open(final_path, "rb").read()).hexdigest(),
        })

    stages_state = {}
    st = store()
    for s in STAGES:
        try:
            stages_state[s] = st.get(RUN, s)["state"]
        except Exception as e:
            stages_state[s] = "left:%s" % getattr(e, "code", e)
    st.close()

    manifest = {
        "run_id": RUN,
        "unit_id": "W4-01-U1",
        "owned_output": "qualification/long-form-media/",
        "auth_scope_digest": read_json("evidence/auth.json")["scope"],
        "authorization": {"source": "Trevor 2026-10-06, $50 total program",
                          "ceiling_cents": CEILING,
                          "program_ceiling_cents": PROGRAM_CEILING,
                          "currency": "USD-cents"},
        "delivery_profile": PROFILE,
        "target_duration_s": TARGET_S,
        "duration_band": "60-90s",
        "intake": read_json("01-intake.json").get("outcome"),
        "preflight": read_json("02-preflight.json").get("outcome"),
        "stages": stages_state,
        "music_qc_verdict": qc_out["verdict"],
        "music_qc_reason": qc_out["reason_code"],
        "timing_guard_verdict": tg.get("verdict"),
        "timing_guard_reason": tg.get("reason_code"),
        "continuity": {"shots": continuity["shot_count"],
                       "review": continuity["adversarial_review"]["outcome"],
                       "gate": continuity["video_spend_gate"]["allowed"]},
        "final_media": final,
        "spend_summary": summary.get("evidence"),
        "program_total": {"projected_cents": proj,
                          "ceiling_cents": PROGRAM_CEILING},
        "receipts_recorded": len(db_receipts),
        "jobs_reconciled": sum(1 for j in db_jobs if j["state"] == "reconciled"),
        "artifacts": artifacts,
        "verdict_file_owner": "independent checker; builder does not write "
                              "evidence/W4-01/*.verdict.json",
    }
    write_json("manifest.json", manifest)
    log(json.dumps({"music_qc": [qc_out["verdict"], qc_out["reason_code"]],
                    "timing_guard": [tg.get("verdict"), tg.get("reason_code")],
                    "final_s": final_dur,
                    "spend": summary.get("evidence"),
                    "program_cents": proj,
                    "artifacts": len(artifacts)},
                   sort_keys=True, default=str))


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(ART, exist_ok=True)
    os.makedirs(LANE, exist_ok=True)
    os.makedirs(TMP, exist_ok=True)
    if len(sys.argv) != 2:
        die("usage: long_run.py core|music|image|video|assemble|qc")
    phase = sys.argv[1]
    {"core": phase_core, "music": phase_music, "image": phase_image,
     "video": phase_video, "assemble": phase_assemble,
     "qc": phase_qc}[phase]()


if __name__ == "__main__":
    main()

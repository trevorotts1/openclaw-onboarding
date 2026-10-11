#!/usr/bin/env python3
"""song_choices: SONG APPROVAL, three labelled songs and the pick gate (FU-SONG-APPROVAL).

Trevor 2026-10-09: add an audio approval gate like the storyboard one. When the
client answers Yes to the SONG APPROVAL card question:

  1. build_requests()    three Suno requests for the SAME lyric sheet, one per
                         arrangement variant (data table: variants.json), each
                         checked by song_dispatch.validate_request before spend;
  2. generate_choices()  the three run IN PARALLEL; each take is judged by
                         song_dispatch.judge_take (lyrics, hook, voice rules);
                         a version that fails is regenerated once, then reported;
  3. deliver_choices()   SONG-CHOICES/ in the delivery folder: "N - LABEL
                         (description).mp3" with the title tag set to the same
                         label (ffmpeg -c copy), plus README.txt;
  4. record_pick()       the client's 1, 2 or 3; the picked file becomes the song;
  5. refusal() /         NO picture timing, paid video, image or lip-sync job
     dispatch_refusal()  runs until the pick is recorded. A missing or damaged
                         pick blocks; nothing ever defaults.

State lives in <run>/song-choices/ (state.json, pick.json). No state file means
the client answered No: behaviour is exactly as before (one song, no wait).
stdlib only; generate/measure/save/runner are injected, so no network here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from song_dispatch import song_dispatch as _SD   # noqa: E402
import suno_recipe as _R                          # noqa: E402  (same form as song_dispatch: works with the package or the bare module on sys.path)
from song_choices import overlap as _OV            # noqa: E402  (WWFIX D2 item 3)

TOOL_NAME = "song_choices"
DIRNAME = "SONG-CHOICES"
BANNED_WORDS = ("choir", "reverb", "echo", "rap", "spoken", "speak", "acapella")
EXTRA_GENERATIONS = 2          # the card pays for 2 more songs than the single-song run
_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "variants.json")


class ChoiceError(ValueError):
    """A loud refusal: nothing was spent or delivered on the broken path."""


def variants_for(style_id):
    """The three variants for a music style (data table). Fails closed."""
    with open(_TABLE, encoding="utf-8") as f:
        rows = json.load(f).get(str(style_id))
    if not rows or len(rows) != 3:
        raise ChoiceError("no three-variant set for music style %r in variants.json" % (style_id,))
    for r in rows:
        low = r["clause"].lower()
        bad = [w for w in BANNED_WORDS if re.search(r"\b%s" % w, low)]
        if bad or len(r["clause"]) > 140:
            raise ChoiceError("variant %r clause breaks the style rules: %s" % (r["id"], bad or "too long"))
    return rows


def extra_cost_cents():
    """What the Yes answer adds to the song line: two more generations."""
    return EXTRA_GENERATIONS * _SD.GEN_COST_CENTS


def build_requests(style_id, sheet, client_text, title, length_s, vocal_gender="f", **kw):
    """[(variant, request)] x3: the style's own request plus the variant clause.
    Every request must pass song_dispatch.validate_request or none is sent."""
    pace_plan = kw.pop("pace_plan", None)   # never forwarded to suno_recipe
    out = []
    for v in variants_for(style_id):
        req = _R.build_request(style_id, sheet, client_text, title, length_s, vocal_gender, **kw)
        req = dict(req, style=req["style"].rstrip() + " " + v["clause"].rstrip(".") + ".")
        errs = _SD.validate_request(req, style_id, client_text, length_s)   # 1758: delivered_s required
        if errs:
            raise ChoiceError("variant %s request refused before spend: %s" % (v["id"], "; ".join(errs)))
        # The judge needs the style and the hook plan (FU-RNBFLOW-SONG song_contract,
        # FU-HOOK-PLACEMENT hook_placement): ride them on the request; run_takes
        # moves _hook_plan into the plan, generate_choices turns _style_id into style_id,
        # and neither reaches KIE.
        req = dict(req, _style_id=style_id)
        if kw.get("hook_plan") is not None:
            req["_hook_plan"] = kw["hook_plan"]
        # D1 / F2: the ordered pace change rides the request like the hook
        # plan; run_takes moves _pace_plan into the plan and it NEVER reaches KIE.
        if pace_plan is not None:
            req["_pace_plan"] = pace_plan
        out.append((v, req))
    return out


def _require_three(rows, key=lambda r: r):
    """The count-and-distinctness guard. Raises BEFORE any generation, so a
    malformed call spends nothing. Three versions must be THREE, and three
    DISTINCT arrangements -- never the same one three times."""
    if len(rows) != 3:
        raise ChoiceError("three versions are required; got %d" % len(rows))
    ids = [key(r) for r in rows]
    if len(set(ids)) != 3:
        raise ChoiceError("the three versions must be three DISTINCT arrangements; got %r" % (ids,))
    return rows


def one_variant(n, variant, request, plan, generate, measure, save, script_words, hook_text,
                spoken_range_pct=None, **kw):
    """THE single-variant worker path. Every caller (the umbrella three-up
    run and the per-unit `--variant`/`--unit-id` run) calls this ONE helper:
    there is no second worker path to drift. One generation per attempt; a
    FAIL is regenerated ONCE, then reported."""
    receipts, got, attempt = [], None, 0
    opts = dict(kw)
    opts.setdefault("style_id", request.get("_style_id"))
    req = {k: x for k, x in request.items() if k != "_style_id"}
    for attempt in (1, 2):
        r = _SD.run_takes(req, plan, lambda rq: generate(variant, rq), measure,
                          lambda t, rc: save(variant, t, rc), script_words, hook_text,
                          spoken_range_pct, cap_cents=_SD.GEN_COST_CENTS, **opts)
        receipts += r["receipts"]
        if r["verdict"] != "FAIL":
            got = r
            break
    return {"n": n, "variant": variant, "status": got["verdict"] if got else "FAILED",
            "take": got["delivered"] if got else None, "attempt": attempt,
            "attempts": attempt, "receipts": receipts}


def run_unit(requests, unit_id=None, variant_id=None, **kw):
    """Run exactly ONE variant -- the per-unit selector path. Dispatches ONE
    generation, never three, so an orchestrated run cannot fan out nine."""
    idx = _select_one(requests, unit_id, variant_id)
    v, rq = requests[idx]
    return [one_variant(idx + 1, v, rq, **kw)]


def _select_one(requests, unit_id, variant_id):
    rows = _require_three(requests, key=lambda r: r[0]["id"])
    if variant_id is not None:
        for i, (v, _) in enumerate(rows):
            if v["id"] == variant_id or v["label"] == variant_id:
                return i
        raise ChoiceError("%r is not one of the three variants %s"
                          % (variant_id, [v["id"] for v, _ in rows]))
    if unit_id is not None:
        want = str(unit_id).strip().upper()
        for i in range(3):
            if UNIT_IDS[i] == want:
                return i
        raise ChoiceError("%r is not one of %s" % (unit_id, list(UNIT_IDS)))
    raise ChoiceError("one worker must name --variant <variant_id> or --unit-id WW-00N")


def generate_choices(requests, plan, generate, measure, save, script_words, hook_text,
                     spoken_range_pct=None, **kw):
    """THE umbrella path: all three variants, ONE submission pass, THREE
    provider jobs, in THREE threads inside this ONE agent unit. Use only in
    non-workflow mode; the orchestrated mode runs three `run_unit`s instead,
    never this and them together. Returns [{n, variant, status, take,
    attempts, receipts}]."""
    _require_three(requests, key=lambda r: r[0]["id"])
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(one_variant, i, v, rq, plan, generate, measure, save,
                          script_words, hook_text, spoken_range_pct, **kw)
                for i, (v, rq) in enumerate(requests, 1)]
        return [f.result() for f in futs]


# ---- the three owned units (D2 item 4) ----------------------------------

UNIT_IDS = ("WW-001", "WW-002", "WW-003")
PROVIDER_SLOTS = 3       # a LANGUAGE-MODEL allocation, not a provider cap
RESERVE = 0


def unit_folder(run_dir, unit_id):
    """One owned folder per unit."""
    return os.path.join(run_dir, "lanes", "%s-lane" % str(unit_id).strip().upper())


def plan_units(run_dir, requests=None):
    """The three units WW-001..003, providerSlots 3, reserve 0, one owned
    folder each. This is what stops the planner rebuilding the WW-001
    monolith. ``media_concurrency`` (provider jobs that run at once) and
    ``builder_agent_units`` (agent lanes) are reported SEPARATELY; threads
    are never relabelled as visible agents."""
    ids = [v["id"] for v, _ in requests] if requests else [None, None, None]
    units = []
    for i, uid in enumerate(UNIT_IDS):
        units.append({"unit_id": uid, "index": i + 1, "variant_id": ids[i],
                      "owned_folder": unit_folder(run_dir, uid),
                      "provider_slots": PROVIDER_SLOTS, "reserve": RESERVE,
                      "owned_requests": 1})
    return {"units": units, "provider_slots": PROVIDER_SLOTS, "reserve": RESERVE,
            "builder_agent_units": len(units), "media_concurrency": len(units),
            "note": "providerSlots is the language-model allocation; the Suno "
                    "provider cap (20 per 10 s) is not binding at three jobs."}


# ---- the provider-overlap receipt (D2 item 3) ---------------------------
#
# ONE implementation: `song_choices/overlap.py`. Nothing here re-derives the
# rule, so the receipt and the gate can never drift.

OVERLAP_MIN_S = _OV.MIN_OVERLAP_S          # 1.000 s, the three INITIAL attempts

#: Name compatibility: the receipt row is the module's make_receipt.
receipt_row = _OV.make_receipt             # noqa: F401 - the receipt builder
request_sha256 = _OV.request_sha256        # noqa: F401 - the bound request hash


def check_overlap(receipts, min_s=OVERLAP_MIN_S):
    """The provider-overlap gate over the THREE INITIAL attempts.

    Delegates to ``song_choices.overlap.overlap_gate``: overlap_s =
    min(terminal_at) - max(submitted_at), PASS at >= 1.000 s, FAIL at 0.999 s or
    zero or negative, and UNAVAILABLE (never a pass) when the evidence is
    absent, naive or duplicated. A regenerated variant is excluded: it is not
    initial-overlap evidence. No automatic paid redo."""
    gate = _OV.overlap_gate(receipts, min_s)
    return {"verdict": gate["verdict"], "overlap_s": gate["overlap_s"],
            "min_s": min_s, "reason": gate["detail"],
            "paid_redo": gate["paid_redo"],
            "requires_owner_authority": gate["requires_owner_authority"]}


def receipt_for(run_dir, variant, request, attempt_id, task_id, submitted_at,
                terminal_at, initial=True):
    """Build and write ONE variant's overlap receipt under
    ``<run>/music/takes/<variant>/overlap-receipt.json``. Both times are aware
    UTC; a naive one is refused by the receipt module."""
    row = _OV.make_receipt(variant["id"], request, "song/%s" % variant["id"],
                           attempt_id, task_id, submitted_at, terminal_at,
                           initial=initial)
    p = os.path.join(run_dir, "music", "takes", variant["id"], "overlap-receipt.json")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(row, f, indent=2, sort_keys=True)
    return row


def overlap_from_run(run_dir):
    """Read the per-variant OVERLAP RECEIPTS under run/music/takes/ and gate on
    them. No receipts at all -> ``applicable: False`` (the gate governs the
    three-version run; a No run has nothing to check)."""
    base = os.path.join(run_dir, "music", "takes")
    rows = []
    if not os.path.isdir(base):
        return {"applicable": False, "verdict": "UNAVAILABLE", "overlap_s": None,
                "allowed": False}
    for name in sorted(os.listdir(base)):
        p = os.path.join(base, name, "overlap-receipt.json")
        if not os.path.isfile(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                rows.append(json.load(f))
        except (OSError, ValueError):
            continue
    if not rows:
        return {"applicable": False, "verdict": "UNAVAILABLE", "overlap_s": None,
                "allowed": False}
    gate = _OV.overlap_gate(rows)
    gate["applicable"] = True
    return gate


def _overlap_refusal(run_dir, action):
    chk = overlap_from_run(run_dir)
    if not chk.get("applicable"):
        return None
    if chk.get("allowed"):
        return None
    return _refuse("the three initial song attempts are %s (overlap %s s); %s is held. "
                   "NO PAID REDO is bought for a missing overlap -- new spend needs "
                   "explicit owner authority."
                   % (chk["verdict"], chk.get("overlap_s"), action),
                   code="SONG_OVERLAP_NOT_PROVEN")


# ---- WW-21: the acceptance boundary at the real delivery boundary ----------
#
# The total fail-closed aggregation/evidence-binding boundary lives ONCE, in
# song_dispatch (`accept_audio_results` / `acceptance_from_run`). Nothing is
# re-derived here, so the gate and the receipt can never drift. It is anchored
# to the SAME folder the production generator fills: the moment a variant has
# a produced take under <run>/music/takes/<variant>/, its acceptance record is
# required, and a take whose required gate set is not all PASS is never
# OFFERED, never PICKED and never PURCHASED.

def acceptance_from_run(run_dir):
    """The WW-21 boundary state for this run (delegates to song_dispatch)."""
    return _SD.acceptance_from_run(run_dir)


def _acceptance_refusal(run_dir, action):
    """None when the boundary is not applicable or has passed; else the
    refusal that holds the offer, the pick and every paid job."""
    return _SD.acceptance_refusal(run_dir, action)


def fan_in(results, run_dir, delivery_dir, **kw):
    """CHECK and DELIVER results that already exist. Never generates: the
    fan-in step must not dispatch anything."""
    return deliver_choices(results, delivery_dir, run_dir, **kw)


def _safe(s):
    return re.sub(r'[\\/:*?"<>|]', "-", s)


def _mmss(sec):
    sec = int(round(float(sec)))
    return "%d:%02d" % (sec // 60, sec % 60)


def _run_ffmpeg(argv):
    subprocess.run(argv, check=True, capture_output=True)


def deliver_choices(results, delivery_dir, run_dir, runner=_run_ffmpeg, target=None, send=None):
    """Write SONG-CHOICES/ and the offered list into state.json. Returns the
    client message. Zero good versions raises (fail closed). With a target the
    message and the files go to the client right away (send_choices). No target
    argument: the client's chat id the card recorded in the run is used. No
    target anywhere (CLI-only run): the message and file paths are printed."""
    hold = _overlap_refusal(run_dir, "delivery")
    if hold:
        raise ChoiceError(hold["detail"])
    # WW-21: OFFER is a delivery boundary. A take whose required gate set is
    # not all PASS -- or whose five results are missing, unbound or stale --
    # is never offered. Zero purchases on this path.
    ahold = _acceptance_refusal(run_dir, "the offer")
    if ahold:
        raise ChoiceError(ahold["detail"])
    _require_three(results, key=lambda r: r["variant"]["id"])
    good = [r for r in results if r["status"] != "FAILED" and r["take"]]
    if not good:
        raise ChoiceError("no song version passed the song checks; nothing to offer")
    folder = os.path.join(delivery_dir, DIRNAME)
    os.makedirs(folder, exist_ok=True)
    offered, lines = {}, []
    for r in good:
        v, take = r["variant"], r["take"]
        label = "%d - %s (%s)" % (r["n"], v["label"], v["description"])
        dst = os.path.join(folder, _safe(label) + ".mp3")
        runner(["ffmpeg", "-y", "-i", take["audio_path"], "-c", "copy",
                "-metadata", "title=" + label, dst])
        dur = _mmss(take.get("duration_s", 0))
        lines.append("%s - %s - %s" % (label.split(" (")[0], dur, v["description"]))
        offered[str(r["n"])] = {"label": label, "file": dst, "duration": dur, "take": take}
    with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    st = _state(run_dir) or {"required": True}
    st.update(required=True, offered=offered)
    _write(run_dir, "state.json", st)
    msg = client_message(offered, [r["n"] for r in results if r["status"] == "FAILED"])
    target = target or st.get("target")
    if target:
        send_choices(run_dir, target, send, msg)
    else:
        print(msg + "\n\nNO CLIENT TARGET RECORDED FOR THIS RUN - nothing was sent. Send these files to the client yourself, in order:")
        print("\n".join(offered[n]["file"] for n in sorted(offered, key=int)))
    return msg


def _run_send(argv):
    subprocess.run(argv, check=True, capture_output=True)


def send_choices(run_dir, target, send=None, message=None):
    """Client delivery: the intake card's own send path (intake_card.openclaw_send_argv,
    `openclaw message send`) with the offered files attached in order 1, 2, 3.
    send(argv) is the sink (default: run it). Returns the argv. Raises when
    nothing is offered or the send fails, so a lost message is never silent."""
    from choice_card.intake_card import intake_card as _IC   # noqa: PLC0415
    offered = (_state(run_dir) or {}).get("offered") or {}
    if not offered:
        raise ChoiceError("no song versions are offered yet; nothing to send")
    nums = sorted(offered, key=int)
    argv = _IC.openclaw_send_argv(target, message or client_message(offered), media=[offered[n]["file"] for n in nums])
    (send or _run_send)(argv)
    return argv


def client_message(offered, failed=()):
    nums = sorted(int(n) for n in offered)
    rows = ["%d. %s - %s" % (n, offered[str(n)]["label"].split(" - ", 1)[1], offered[str(n)]["duration"])
            for n in nums]
    pick = "%s or %d" % (", ".join(map(str, nums[:-1])), nums[-1]) if len(nums) > 1 else str(nums[0])
    msg = ["Your song is ready in %d versions. They are in the %s folder:" % (len(nums), DIRNAME), ""] + rows
    if failed:
        msg += ["", "Version %s did not pass my song checks after a second try, so I left it out."
                % ", ".join(map(str, failed))]
    return "\n".join(msg + ["", "Reply %s to pick your song. Nothing else is made until you pick." % pick])


# ---- state and the gate -------------------------------------------------

def _path(run_dir, name):
    return os.path.join(run_dir, "song-choices", name)


def _write(run_dir, name, data):
    os.makedirs(os.path.join(run_dir, "song-choices"), exist_ok=True)
    with open(_path(run_dir, name), "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True)


def _state(run_dir):
    p = _path(run_dir, "state.json")
    if not os.path.exists(p):
        return None
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def record_card_answer(run_dir, answers, target=None):
    """The intake card's SONG APPROVAL answer -> the run (Yes turns the gate on,
    No records No). Called when the recap is confirmed. A changed answer before
    the songs are made replaces the old one; once versions exist (resume) the
    recorded answer is kept untouched."""
    from choice_card.intake_card import intake_card as _IC   # noqa: PLC0415
    st = _state(run_dir)
    if st and st.get("offered"):
        return bool(st.get("required"))
    required = _IC.song_required(answers)
    init(run_dir, required, target or (st or {}).get("target"))
    return required


def init(run_dir, required, target=None):
    """Record the card answer (and the client's chat id). Call once when the card is approved."""
    st = {"required": bool(required), "offered": {}}
    if target:
        st["target"] = str(target)
    _write(run_dir, "state.json", st)


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def picked_song(run_dir):
    return os.path.join(run_dir, "music", "picked-song.mp3")


def record_pick(run_dir, reply):
    """The client's 1, 2 or 3. Anything not offered is refused; returns the label."""
    st = _state(run_dir)
    if not st or not st.get("required"):
        raise ChoiceError("this run did not ask for song choices")
    hold = _overlap_refusal(run_dir, "the pick")
    if hold:
        raise ChoiceError(hold["detail"])
    # WW-21: the PICK is a delivery boundary too.
    ahold = _acceptance_refusal(run_dir, "the pick")
    if ahold:
        raise ChoiceError(ahold["detail"])
    n = str(reply).strip()
    o = (st.get("offered") or {}).get(n)
    if not o or not os.path.isfile(o["file"]):
        raise ChoiceError("%r is not one of the offered songs %s" % (reply, sorted(st.get("offered") or {})))
    os.makedirs(os.path.join(run_dir, "music"), exist_ok=True)
    shutil.copyfile(o["file"], picked_song(run_dir))
    _write(run_dir, "pick.json", {"pick": int(n), "label": o["label"], "sha256": _sha(picked_song(run_dir)),
                                  "take": o.get("take")})
    return o["label"]


def refusal(run_dir):
    """None when work may go on; else the refusal. No state file = answered No.

    WW-21 first: a take whose required gate set is not all PASS holds EVERY
    later stage (picture timing, paid video, image, lip-sync) before the pick
    check is even consulted."""
    ahold = _acceptance_refusal(run_dir, "every later stage")
    if ahold:
        return ahold
    try:
        st = _state(run_dir)
    except (OSError, ValueError):
        return _refuse("the song-choices state is unreadable; fix it before anything is spent")
    if st is None or not st.get("required"):
        return None
    try:
        with open(_path(run_dir, "pick.json"), encoding="utf-8") as f:
            pick = json.load(f)
        ok = os.path.isfile(picked_song(run_dir)) and _sha(picked_song(run_dir)) == pick["sha256"]
    except (OSError, ValueError, KeyError):
        ok = False
    if not ok:
        return _refuse("the client has not picked a song yet (or the picked file is missing or changed)")
    return None


def _refuse(why, code="SONG_PICK_MISSING"):
    return {"reason_code": code, "detail": why,
            "next_action": "Send the client the three songs and wait for their pick (1, 2 or 3). "
                           "No picture timing, video, image or lip-sync job starts before it."}


def dispatch_refusal(is_music_job, run_dir):
    """kie_dispatch seam: the song stage itself may run; everything else waits."""
    return None if is_music_job else refusal(run_dir)


# ---- the CLI generate path ----------------------------------------------

def _load_request(path):
    """Read the music request and pull the pieces build_requests needs.
    A missing piece is a loud refusal BEFORE any spend."""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    inp = doc.get("input") if isinstance(doc.get("input"), dict) else {}
    sheet_text = doc.get("sheet_text") or inp.get("lyrics") or doc.get("lyrics")
    style_id = doc.get("style_id") or inp.get("style_id")
    if not sheet_text or not style_id:
        raise ChoiceError("the request file must carry style_id and the lyric sheet; "
                          "got style_id=%r, sheet=%s" % (style_id, bool(sheet_text)))
    return {"style_id": style_id, "sheet": _R.parse_lyrics(sheet_text) if hasattr(_R, "parse_lyrics")
            else [{"tag": "Sheet", "delivery": "sung", "lines": sheet_text.splitlines()}],
            "sheet_text": sheet_text,
            "client_text": doc.get("client_text", ""), "title": doc.get("title") or inp.get("title", ""),
            "length_s": doc.get("length_s") or inp.get("duration"),
            "vocal_gender": inp.get("vocal_gender", doc.get("vocal_gender", "f")),
            "hook_plan": doc.get("hook_plan") or doc.get("_hook_plan"),
            "pace_plan": doc.get("pace_plan") or doc.get("_pace_plan")}


def _envelope_path(run_dir, variant_id):
    return os.path.join(run_dir, "music", "takes", variant_id, "dispatch-envelope.json")


def _write_envelope(run_dir, variant_id, evidence):
    p = _envelope_path(run_dir, variant_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"variant_id": variant_id, "evidence": evidence}, f, indent=2, sort_keys=True)
    return p


def _real_generate(run_dir, ledger, run_id):
    """The default per-variant worker: ONE KIE dispatch per call, and the
    per-variant envelope carries the two aware-UTC stamps the overlap
    receipt binds (``evidence.accepted_submit_at`` / ``evidence.terminal_at``).
    Injected in tests, so no provider is ever called there."""
    def generate(variant, request):
        _c = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _c not in sys.path:
            sys.path.insert(0, _c)
        import kie_dispatch.kie_dispatch as _KD   # noqa: PLC0415
        save_dir = os.path.join(run_dir, "music", "takes", variant["id"])
        os.makedirs(save_dir, exist_ok=True)
        env = _KD.dispatch(model=request.get("model") or "ai-music-api/generate",
                           request=request, save_dir=save_dir, ledger_db=ledger,
                           run_id=run_id or (os.path.basename(run_dir) or "run"),
                           logical_key="song/%s" % variant["id"],
                           attempt_id="a1", estimated_cost=_SD.GEN_COST_CENTS,
                           prompt=request.get("input", {}).get("style", "")[:2000],
                           generation=True)
        ev = env.get("evidence", {}) if isinstance(env, dict) else {}
        _write_envelope(run_dir, variant["id"], ev)
        # D2 item 3: the overlap receipt, built from the PROVIDER lifecycle
        # stamps only. accepted_submit_at is stamped after a valid task-id
        # acknowledgment; terminal_at at the first terminal provider response.
        # No receipt when the provider never acknowledged or never terminated:
        # the gate then reports UNAVAILABLE, which is never a pass.
        if ev.get("accepted_submit_at") and ev.get("terminal_at"):
            receipt_for(run_dir, variant, request, "a1", ev.get("task_id"),
                        ev["accepted_submit_at"], ev["terminal_at"])
        takes = []
        if isinstance(env, dict) and env.get("outcome") == "ok":
            for p in ev.get("saved_paths", []) or []:
                takes.append({"audio_path": p})
        return takes
    return generate


def cmd_generate(a, generate=None, measure=None, save=None, plan=None):
    """`generate` -- the canonical three-version music runner.

    Orchestrated mode (``--variant``/``--unit-id``): ONE worker, ONE owned
    variant folder, ONE generation. Umbrella mode (neither flag, non-workflow
    run): all three once, three provider jobs in three threads inside this one
    agent unit. The fan-in only ever CHECKS and DELIVERS existing results.
    """
    run_dir = os.path.abspath(os.path.expanduser(a.run_dir))
    spec = _load_request(a.request)
    reqs = build_requests(spec["style_id"], spec["sheet"], spec["client_text"],
                          spec["title"], spec["length_s"], spec["vocal_gender"],
                          hook_plan=spec["hook_plan"], pace_plan=spec["pace_plan"])
    _require_three(reqs, key=lambda r: r[0]["id"])
    plan = plan or {"delivered_s": spec["length_s"], "style_id": spec["style_id"],
                    "sheet_text": spec["sheet_text"], "hook_plan": spec["hook_plan"],
                    "_pace_plan": spec["pace_plan"]}
    gen = generate or _real_generate(run_dir, a.ledger, a.run_id)
    kw = dict(plan=plan, generate=gen, measure=measure or (lambda t: {}),
              save=save or (lambda v, t, r: None), script_words=spec["client_text"],
              hook_text="")
    # WWFIXGAPS U1 (defect 3): ``dispatched`` is MEASURED from the run that
    # actually happened, never a literal. One provider job goes out per
    # attempt, and ``one_variant`` regenerates a FAIL once, so a variant that
    # had to retry is TWO dispatches -- an umbrella run that retries every
    # arrangement dispatches six, not the three the old literal claimed.
    if a.variant or a.unit_id:
        results = run_unit(reqs, unit_id=a.unit_id or None, variant_id=a.variant or None, **kw)
    else:
        results = generate_choices(reqs, **kw)
    dispatched = sum(int(r.get("attempts") or 0) for r in results)
    if a.variant or a.unit_id:
        out = {"mode": "orchestrated", "dispatched": dispatched, "results": results}
    else:
        out = {"mode": "umbrella", "dispatched": dispatched, "results": results,
               "media_concurrency": 3, "builder_agent_units": 1,
               "note": "3 provider jobs in 3 THREADS inside ONE agent unit; "
                       "threads are not visible agents"}
    out["units"] = plan_units(run_dir, reqs)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Song choices: init the card answer, record the pick, check the gate.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--run-dir", required=True)
    i.add_argument("--required", choices=("yes", "no"), required=True)
    p = sub.add_parser("pick")
    p.add_argument("--run-dir", required=True)
    p.add_argument("--reply", required=True)
    sd = sub.add_parser("send")
    sd.add_argument("--run-dir", required=True)
    sd.add_argument("--target", required=True)
    c = sub.add_parser("check")
    c.add_argument("--run-dir", required=True)
    g = sub.add_parser("generate", help="the canonical three-version music runner "
                                        "(umbrella three-up, or ONE unit in orchestrated mode)")
    g.add_argument("--run-dir", required=True)
    g.add_argument("--request", required=True, help="the music request JSON")
    g.add_argument("--ledger", default="", help="spend ledger sqlite path")
    g.add_argument("--run-id", default="")
    g.add_argument("--variant", default="", help="orchestrated mode: run ONE variant only")
    g.add_argument("--unit-id", default="", help="orchestrated mode: run ONE owned unit WW-00N")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "init":
            init(a.run_dir, a.required == "yes")
        elif a.cmd == "send":
            send_choices(a.run_dir, a.target)
        elif a.cmd == "pick":
            print("Picked: " + record_pick(a.run_dir, a.reply))
        elif a.cmd == "generate":
            out = cmd_generate(a)
            json.dump(out, sys.stdout, indent=2, sort_keys=True, default=str)
            sys.stdout.write("\n")
        else:
            r = refusal(a.run_dir)
            if r:
                print(json.dumps(r, indent=2))
                return 5
            print("ok")
    except ChoiceError as e:
        print("REFUSED: %s" % e, file=sys.stderr)
        return 5
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

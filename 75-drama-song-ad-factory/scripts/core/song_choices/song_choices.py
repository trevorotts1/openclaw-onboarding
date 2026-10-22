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
import time
from concurrent.futures import ThreadPoolExecutor

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from song_dispatch import song_dispatch as _SD   # noqa: E402
import suno_recipe as _R                          # noqa: E402  (same form as song_dispatch: works with the package or the bare module on sys.path)
from song_choices import overlap as _OV            # noqa: E402  (WWFIX D2 item 3)

TOOL_NAME = "song_choices"
DIRNAME = "SONG-CHOICES"
#: Failed takes are presented for listening only, never on the offer surface.
FOR_LISTENING = "FOR-LISTENING"
BANNED_WORDS = ("choir", "reverb", "echo", "rap", "spoken", "speak", "acapella")
#: WW-26: words no complete brief may carry whatever the style -- a sound the
#: style bans outright, or a delivery the style text already names once.
_BANNED_ALWAYS = ("choir", "reverb", "echo", "acapella")
_BANNED_SHARED = ("spoken", "speak")
#: WW-26: the ten directions a COMPLETE brief must carry. A brief missing any
#: one is an identifier, not a treatment, and is refused BEFORE spend.
#: The ORDER the brief is serialized in. ``arrangement`` is LAST so the
#: assembled style ends with the variant's own arrangement clause, exactly as
#: the base asserted, with the approved pace clause appended after it.
_BRIEF_FIELDS = ("groove", "palette", "energy", "vocals", "hook",
                 "scene_words", "problem_shift", "solution_shift", "ending",
                 "arrangement")
_DIRECTION_LABEL = {"groove": "groove", "palette": "palette",
                    "arrangement": "arrangement", "energy": "energy",
                    "vocals": "cast/vocals", "hook": "rap-vs-sung hook",
                    "scene_words": "immediate scene words",
                    "problem_shift": "problem shift",
                    "solution_shift": "solution shift", "ending": "short ending"}
#: WW-26: the shape a shared core plus a short suffix leaves in the FINAL
#: serialized styles -- a long identical prefix and only a short remainder.
#: A complete brief differs from its siblings from the first word.
SHARED_CORE_PREFIX_MIN = 120
SHARED_SUFFIX_MAX = 160
EXTRA_GENERATIONS = 2          # the card pays for 2 more songs than the single-song run
_TABLE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "variants.json")


class ChoiceError(ValueError):
    """A loud refusal: nothing was spent or delivered on the broken path."""


def _brief_refusals(variant):
    """WW-26: the ten-direction completeness of ONE variant brief. [] = complete.

    A brief that names its genre but carries no treatment is an identifier, not
    a brief; this is the check ``_require_three`` runs, so completeness is
    enforced before any generation, not only where the data is loaded."""
    brief = variant.get("brief") if isinstance(variant, dict) else None
    if not isinstance(brief, dict):
        return ["MISSING_BRIEF: variant %r carries no complete brief" % (variant.get("id"),)]
    out = []
    for f in _BRIEF_FIELDS:
        val = brief.get(f)
        if not isinstance(val, str) or len(val.strip()) < 8:
            out.append("MISSING_DIRECTION: variant %r brief lacks the %s direction"
                       % (variant.get("id"), _DIRECTION_LABEL[f]))
    return out

def _banned_words(style_id):
    """WW-26: the words a brief for THIS style may not carry. ``rap`` is refused
    only for a style that delivers none -- an R&B Flow brief is REQUIRED to name
    the rap-versus-sung hook, so the old blanket ban would forbid the direction."""
    _sr = getattr(_R, "suno_recipe", _R)
    try:
        sid = _sr._style_key(style_id)
        raps = sid in getattr(_sr, "RAP_STYLE_IDS", ()) or bool(
            _sr.music_block(sid).get("rap_allowed"))
    except Exception:   # noqa: BLE001  unknown style -> the stricter set
        raps = False
    words = list(_BANNED_ALWAYS) + list(_BANNED_SHARED)
    if not raps:
        words += ["rap", "rapping"]
    return tuple(words)

def variants_for(style_id):
    """WW-26: the three COMPLETE briefs for a music style (data table). Fails
    closed on a missing/duplicate set, an incomplete brief, a banned word, a
    genre substitution or a count that is not exactly ONE upbeat role."""
    with open(_TABLE, encoding="utf-8") as f:
        rows = json.load(f).get(str(style_id))
    if not rows or len(rows) != 3:
        raise ChoiceError("no three-variant set for music style %r in variants.json" % (style_id,))
    banned = _banned_words(style_id)
    for r in rows:
        for why in _brief_refusals(r):
            raise ChoiceError(why)
        if r.get("genre") != str(style_id):
            raise ChoiceError("variant %r substitutes genre %r for the chosen %r"
                              % (r.get("id"), r.get("genre"), style_id))
    for r in rows:
        text = " ".join(str(r["brief"][f]) for f in _BRIEF_FIELDS).lower()
        bad = [w for w in banned if re.search(r"\b%s" % w, text)]
        if bad:
            raise ChoiceError("variant %r brief breaks the style rules: %s" % (r["id"], bad))
        if len(r["brief"]["arrangement"]) > 140:
            raise ChoiceError("variant %r arrangement clause too long" % (r["id"],))
        # back-compat: the trailing clause is the brief's own arrangement sentence
        r["clause"] = r["brief"]["arrangement"]
    if sum(1 for r in rows if r.get("upbeat")) != 1:
        raise ChoiceError("exactly ONE variant must be the explicitly upbeat role for %r"
                          % (style_id,))
    return rows

def _brief_text(variant, vocal_gender):
    """One variant's authored brief CORE, in order, as the start of the provider
    style. The arrangement sentence is EXCLUDED here and passed back separately
    as the style's trailing clause, so the style ends with the variant's own
    arrangement exactly as the base asserted."""
    _sr = getattr(_R, "suno_recipe", _R)
    word = _sr.vocal_gender_word(vocal_gender)
    brief = variant["brief"]
    return " ".join(str(brief[f]).replace("{gender}", word).strip()
                    for f in _BRIEF_FIELDS if f != "arrangement")

def _common_prefix_len(strs):
    if not strs:
        return 0
    n = min(len(s) for s in strs)
    i = 0
    while i < n and all(s[i] == strs[0][i] for s in strs):
        i += 1
    return i

def _check_three_briefs(rows, vocal_gender="f"):
    """WW-26: the pre-spend gate on the EXACT serialized three variant payloads.

    Reads ``request["input"]["style"]`` after every transformation and refuses a
    missing cast/vocals/rap/shift/upbeat direction, a shared-core-plus-suffix
    shape, a genre substitution, a wrong upbeat count and a final over-cap text.
    The value the guard tests is printed at this real call site."""
    _sr = getattr(_R, "suno_recipe", _R)
    word = _sr.vocal_gender_word(vocal_gender)
    refusals, styles, genres, upbeats = [], [], [], 0
    for v, req in rows:
        style = ((req.get("input") or {}).get("style")) or ""
        styles.append(style)
        brief = v.get("brief") or {}
        print("  WW-26 serialized input.style [%s] len=%d chars" % (v.get("id"), len(style)))
        for f in _BRIEF_FIELDS:
            need = str(brief.get(f, "")).replace("{gender}", word)
            if not need or need not in style:
                refusals.append("MISSING_DIRECTION: variant %s style lacks the %s "
                                "direction (%r)" % (v.get("id"), _DIRECTION_LABEL[f], need))
        if len(style) > _sr.SUNO_STYLE_FIELD_MAX:
            refusals.append("STYLE_TOO_LONG: variant %s style is %d chars, limit %d"
                            % (v.get("id"), len(style), _sr.SUNO_STYLE_FIELD_MAX))
        genres.append(brief.get("genre") or v.get("genre"))
        if v.get("upbeat"):
            upbeats += 1
    if len(set(genres)) != 1 or any(g is None for g in genres):
        refusals.append("GENRE_SUBSTITUTION: the three variants name %r" % (genres,))
    if upbeats != 1:
        refusals.append("UPBEAT_DIRECTION: exactly one variant must be the upbeat role; got %d"
                        % upbeats)
    if styles and len(styles) == 3:
        lcp = _common_prefix_len(styles)
        shortest = min(len(s) for s in styles)
        print("  WW-26 three styles: common prefix %d chars, shortest %d chars"
              % (lcp, shortest))
        if lcp >= SHARED_CORE_PREFIX_MIN and (shortest - lcp) <= SHARED_SUFFIX_MAX:
            refusals.append("SHARED_CORE_PLUS_SUFFIX: the three variants share %d leading "
                            "chars and differ only by a suffix of %d chars"
                            % (lcp, shortest - lcp))
    if refusals:
        raise ChoiceError("three complete briefs refused before spend: %s" % "; ".join(refusals))
    return rows


def extra_cost_cents():
    """What the Yes answer adds to the song line: two more generations."""
    return EXTRA_GENERATIONS * _SD.GEN_COST_CENTS


def build_requests(style_id, sheet, client_text, title, length_s, vocal_gender="f", **kw):
    """[(variant, request)] x3: the style's own request plus the variant clause.
    Every request must pass song_dispatch.validate_request or none is sent.

    WW-07: the approved ``pace_plan`` is written into the FINAL provider
    ``input.style``, AFTER the ending and arrangement clauses: the
    lowest-point drop and the return ride the request as internal
    ``_pace_plan`` for the judge -- never to KIE. The arrangement clause is
    appended BEFORE the drop and return: assembling the pace clause inside
    ``build_request`` put it ahead of the variant clause, which is the WW-07
    defect this fixes."""
    pace_plan = kw.pop("pace_plan", None)   # WW-07: into the style, never into the payload
    # WW-07 / WW-26: each variant's style is its OWN complete brief, assembled
    # by suno_recipe.brief_style_text -- compliance trailer first, the variant's
    # whole brief next, the approved pace clause LAST, cap on the FINAL text.
    # pace_clause / SUNO_STYLE_FIELD_MAX live on the bare module, not the package
    # (same resolution music_director uses).
    _sr = getattr(_R, "suno_recipe", _R)
    out = []
    for v in variants_for(style_id):
        req = _R.build_request(style_id, sheet, client_text, title, length_s, vocal_gender, **kw)
        # WW-30: the style lands on the NESTED input.style -- the createTask
        # envelope carries directions inside ``input`` and nothing at the top
        # level except the route model and the callBackUrl.
        style = _sr.brief_style_text(style_id, _brief_text(v, vocal_gender),
                                     sheet, vocal_gender, pace_plan,
                                     tail_clause=v["brief"]["arrangement"])
        req = dict(req, input=dict(req["input"], style=style))
        # FU-HOOK-PLACEMENT: the hook plan must ride the request BEFORE the
        # pre-spend validation so the hook-count gate judges it with the same
        # plan the judge later sees (validate_request honors _hook_plan). It
        # never reaches KIE: run_takes moves it into the plan as metadata.
        if kw.get("hook_plan") is not None:
            req = dict(req, _hook_plan=kw["hook_plan"])
        errs = _SD.validate_request(req, style_id, client_text, length_s,   # 1758: delivered_s required
                                    pace_plan=pace_plan)
        if errs:
            raise ChoiceError("variant %s request refused before spend: %s" % (v["id"], "; ".join(errs)))
        # The judge needs the style (FU-RNBFLOW-SONG song_contract) and the hook
        # plan (FU-HOOK-PLACEMENT hook_placement): ride them on the request;
        # run_takes moves _hook_plan into the plan, generate_choices turns
        # _style_id into style_id, and neither reaches KIE.
        req = dict(req, _style_id=style_id)
        # D1 / F2: the ordered pace change rides the request like the hook
        # plan; run_takes moves _pace_plan into the plan and it NEVER reaches KIE.
        if pace_plan is not None:
            req["_pace_plan"] = pace_plan
        out.append((v, req))
    _check_three_briefs(out, vocal_gender)
    return out


def _variant_of(row):
    """The variant record a guard row exposes: a ``(variant, request)`` pair, a
    result dict carrying ``variant``, or None when the row carries neither."""
    if isinstance(row, (tuple, list)) and row:
        return row[0] if isinstance(row[0], dict) else None
    if isinstance(row, dict):
        v = row.get("variant")
        return v if isinstance(v, dict) else None
    return None

def _require_three(rows, key=lambda r: r):
    """The count, distinctness AND completeness guard. Raises BEFORE any
    generation, so a malformed call spends nothing. Three versions must be
    THREE; three DISTINCT arrangements; and -- WW-26 -- three COMPLETE
    treatments, not identifiers only: every brief must carry all ten
    directions and exactly ONE role must be the explicit upbeat option."""
    if len(rows) != 3:
        raise ChoiceError("three versions are required; got %d" % len(rows))
    ids = [key(r) for r in rows]
    if len(set(ids)) != 3:
        raise ChoiceError("the three versions must be three DISTINCT arrangements; got %r" % (ids,))
    variants = [_variant_of(r) for r in rows]
    if any(v is not None and "brief" in v for v in variants):
        for v in variants:
            if v is None or "brief" not in v:
                raise ChoiceError("the three versions must carry a COMPLETE brief each, "
                                  "not identifiers only")
            for why in _brief_refusals(v):
                raise ChoiceError(why)
        if sum(1 for v in variants if v.get("upbeat")) != 1:
            raise ChoiceError("exactly ONE of the three versions must be the explicit "
                              "upbeat role")
    return rows


def one_variant(n, variant, request, plan, generate, measure, save, script_words, hook_text,
                spoken_range_pct=None, **kw):
    """THE single-variant worker path. Every caller (the umbrella three-up
    run and the per-unit `--variant`/`--unit-id` run) calls this ONE helper:
    there is no second worker path to drift. ONE generation per attempt.

    SONG-FAILURE VERDICT BELONGS TO THE CLIENT (order 2026-10-21): a take the
    song judge FAILS is NEVER regenerated here. It is returned with the judge's
    named concerns so the client can listen and answer the one fork question
    (``failure_fork_message``); only the client's recorded answer authorizes a
    new paid round. There is no silent retry loop.

    WW-18: `run_takes` delivers only a take whose REQUIRED gate set all PASSed
    (its constituent receipt is current), so `status` is never a take that a
    required gate blocked; the receipt rides the result to the delivery gate."""
    opts = dict(kw)
    opts.setdefault("style_id", request.get("_style_id"))
    req = {k: x for k, x in request.items() if k != "_style_id"}
    heard = []

    def _save(t, rc):
        heard.append(dict(t))          # the paid take, kept for the client's listen
        return save(variant, t, rc)

    r = _SD.run_takes(req, plan, lambda rq: generate(variant, rq), measure,
                      _save, script_words, hook_text,
                      spoken_range_pct, cap_cents=_SD.GEN_COST_CENTS, **opts)
    got = None if r["verdict"] == "FAIL" else r
    return {"n": n, "variant": variant,
            "status": got["verdict"] if got else "FAILED",
            "take": got["delivered"] if got else None,
            # ``heard`` is LISTENING ONLY: a take the judge failed is presented
            # to the client, never offered for a pick (WW-18 stays).
            "heard": None if got else (heard[-1] if heard else None),
            "concerns": [] if got else failure_concerns(r),
            "receipt": got.get("receipt") if got else (r.get("receipt")),
            "attempt": 1, "attempts": 1, "receipts": r["receipts"]}


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


def _accepted(result):
    """WW-18: a result is offerable only when its take's REQUIRED gate set all
    PASSES (its constituent receipt is current). A take with a failed, flagged,
    unmeasured, unavailable or unknown REQUIRED gate (or no receipt) is never
    offered."""
    rec = (result or {}).get("receipt")
    if rec is None:
        return (False, "no constituent receipt") if result.get("receipts") else \
            (False, "no take receipt recorded")
    return _SD.constituent_ok(rec)

# ---- WW-25: the copy-first archive (the shipping writer, no second module) --
#
# The EXISTING shipping publish step is ``deliver_choices`` below: it
# ffmpeg-copies the approved takes into ``<delivery>/SONG-CHOICES/`` and
# rewrites README.txt and state.json. On a re-run that folder is REPLACED, so
# the approved take files must be preserved by COPY -- never by deleting the
# originals and never by overwriting an earlier archive to make the re-run
# succeed. NO pre-existing archive helper exists in skill 75 (resolved from
# disk: zero ``archive`` symbols under 75-drama-song-ad-factory/scripts/, and
# no such module anywhere in this repo's git history for skill 75), so the
# copy-first archive lives HERE, on the existing shipping writer -- never in a
# new parallel module. The historical defective
# qualification/.../WW-011-lane/build_restart2.py ``archive_replaced()``
# (os.remove on an existing archive then shutil.move) is EVIDENCE of the
# defect, never the shipping destination.

ARCHIVE_DIRNAME = "archive"

def _sha256_file(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()

def _noncolliding_dir(base):
    """A directory path that does NOT exist yet. An earlier archive is NEVER
    overwritten: a name collision bumps '-2', '-3', ... until the name is
    free."""
    if not os.path.exists(base):
        return base
    i = 2
    while os.path.exists("%s-%d" % (base, i)):
        i += 1
    return "%s-%d" % (base, i)

def archive_before_publish(run_dir, items, stamp="published", copier=None):
    """WW-25 copy-first archive. COPY every source into a NEW noncolliding
    archive folder and verify each copy's sha256 EQUALS its source BEFORE any
    replacement output is published. Never deletes or moves a source; never
    writes into an existing archive. Any copy fault or hash mismatch raises
    ChoiceError with BOTH sides preserved: the sources are untouched and the
    fresh archive folder is left exactly as written, never rolled back by a
    delete. ``items`` is [{"name", "source"}]; returns the receipt."""
    copier = copier or shutil.copy2
    root = os.path.join(run_dir, "song-choices", ARCHIVE_DIRNAME)
    os.makedirs(root, exist_ok=True)
    dest = _noncolliding_dir(os.path.join(root, stamp))
    os.makedirs(dest, exist_ok=False)      # noncolliding: a fresh folder only
    receipt = {"dir": dest, "stamp": stamp, "files": [], "complete": False}
    for it in items:
        name, src = it["name"], it["source"]
        if not os.path.isfile(src):
            raise ChoiceError("WW-25 archive: source missing for %s: %s "
                              "(nothing was published)" % (name, src))
        target = os.path.join(dest, name)
        try:
            copier(src, target)
        except Exception as exc:            # noqa: BLE001 - any copy fault refuses before publish
            raise ChoiceError("WW-25 archive: copy failed for %s (%r); both sides "
                              "preserved, nothing was published" % (name, exc))
        got, want = _sha256_file(target), _sha256_file(src)
        if got != want:
            raise ChoiceError("WW-25 archive: copied hash mismatch for %s (copy %s != "
                              "source %s); both sides preserved, nothing was published"
                              % (name, got, want))
        receipt["files"].append({"name": name, "sha256": got})
    receipt["complete"] = True
    with open(os.path.join(dest, "archive-receipt.json"), "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, sort_keys=True)
    return receipt


def deliver_choices(results, delivery_dir, run_dir, runner=_run_ffmpeg, target=None, send=None):
    """Write SONG-CHOICES/ and the offered list into state.json. Returns the
    client message. With a target the message and the files go to the client
    right away (send_choices). No target argument: the client's chat id the
    card recorded in the run is used. No target anywhere (CLI-only run): the
    message and file paths are printed.

    WW-18: a take whose REQUIRED gate set is not all PASS is NOT offered, so a
    failed or unmeasured required gate can never be PICKED; its paid file is
    still presented for LISTENING because the song-failure verdict belongs to
    the client (order 2026-10-21). Nothing regenerates and nothing loops here:
    every take that failed is delivered with the judge's named concerns and the
    ONE fork question. Only a production that produced no take at all raises.

    WW-21: OFFER is a delivery boundary. A take whose required gate set is not
    all PASS -- or whose five results are missing, unbound or stale -- is never
    offered. Zero purchases on this path.
    """
    hold = _overlap_refusal(run_dir, "delivery")
    if hold:
        raise ChoiceError(hold["detail"])
    _require_three(results, key=lambda r: r["variant"]["id"])
    good = [r for r in results
            if r.get("take") and r.get("status") != "FAILED" and _accepted(r)[0]]
    # LISTENING ONLY: a take the JUDGE failed (status FAILED with its named
    # concerns). A take blocked by WW-21's acceptance binding is NOT presented
    # here -- that refusal path is unchanged.
    heard = [r for r in results
             if r not in good and str(r.get("status") or "").upper() == "FAILED"
             and (r.get("take") or r.get("heard"))]
    if not good and not heard:
        raise ChoiceError("no song version passed every required song gate; nothing to offer")
    if good:
        ahold = _acceptance_refusal(run_dir, "the offer")
        if ahold:
            raise ChoiceError(ahold["detail"])
    folder = os.path.join(delivery_dir, DIRNAME)
    # WW-25: COPY-FIRST archive BEFORE any replacement output is published. Every
    # approved take file is copied into a NEW noncolliding archive and each copy
    # is hash-verified against its source; a copy fault or mismatch raises here,
    # so NOTHING is published (not even the folder), the originals are untouched
    # and a prior archive is never overwritten. This call is the guard the WW-25
    # fixtures prove reachable from the production delivery path.
    plan = [(_safe("%d - %s (%s)" % (r["n"], r["variant"]["label"],
                                     r["variant"]["description"])) + ".mp3",
             (r.get("take") or r.get("heard"))["audio_path"], r) for r in good]
    plan += [(_safe("%d - %s (%s) - NOT PASSED"
                    % (r["n"], r["variant"]["label"], r["variant"]["description"]))
              + ".mp3", (r.get("take") or r.get("heard"))["audio_path"], r)
             for r in heard]
    archive_before_publish(run_dir, [{"name": n, "source": s} for n, s, _ in plan])
    os.makedirs(folder, exist_ok=True)
    listen_dir = os.path.join(folder, FOR_LISTENING)
    offered, lines, concerns, presented = {}, [], {}, []
    for name, _src, r in plan:
        v, take = r["variant"], (r.get("take") or r.get("heard"))
        label = "%d - %s (%s)" % (r["n"], v["label"], v["description"])
        # A failed take is presented for LISTENING under its own folder, so the
        # offer surface (WW-21/WW-18) carries accepted takes only.
        dst = os.path.join(folder if r in good else listen_dir, name)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        runner(["ffmpeg", "-y", "-i", take["audio_path"], "-c", "copy",
                "-metadata", "title=" + label, dst])
        presented.append(dst)
        dur = _mmss(take.get("duration_s", 0))
        if r in good:
            lines.append("%s - %s - %s" % (label.split(" (")[0], dur, v["description"]))
            offered[str(r["n"])] = {"label": label, "file": dst, "duration": dur,
                                    "take": take, "receipt": r.get("receipt")}
        else:
            # Presented to LISTEN to, never offered for a pick (WW-18).
            why = r.get("concerns") or failure_concerns(r)
            concerns[str(r["n"])] = why
            lines.append("%s - %s - %s - NOT PASSED: %s"
                         % (label.split(" (")[0], dur, v["description"],
                            "; ".join(why) if why else "did not pass the song checks"))
    with open(os.path.join(folder, "README.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    st = _state(run_dir) or {"required": True}
    st.update(required=True, offered=offered,
              failure_fork=bool(heard), concerns=concerns)
    _write(run_dir, "state.json", st)
    # Method Step 14 (inert until the run carries control/method.json): the
    # message RECOMMENDS the strongest compliant version with a concrete reason.
    # `recommend` ranks only the versions `good` above offers, so it can never
    # name one the client was not sent.
    rec = recommend(results) if method_run(run_dir) and offered else None
    st["presented"] = presented
    _write(run_dir, "state.json", st)
    failed_nums = sorted(int(r["n"]) for r in heard)
    if not offered:
        # Every take failed: the client hears them and answers the ONE fork.
        msg = failure_fork_message(results)
    else:
        msg = client_message(offered, failed_nums, recommend=rec, concerns=concerns)
    target = target or st.get("target")
    if target:
        send_choices(run_dir, target, send, msg)
    else:
        print(msg + "\n\nNO CLIENT TARGET RECORDED FOR THIS RUN - nothing was sent. Send these files to the client yourself, in order:")
        print("\n".join(st["presented"]))
    return msg


def _run_send(argv):
    subprocess.run(argv, check=True, capture_output=True)


def send_choices(run_dir, target, send=None, message=None):
    """Client delivery: the intake card's own send path (intake_card.openclaw_send_argv,
    `openclaw message send`) with the files attached in order. send(argv) is the
    sink (default: run it). Returns the argv. Raises when nothing was presented
    or the send fails, so a lost message is never silent.

    A failed production still sends: the takes the judge failed are presented
    for LISTENING (never offered for a pick) so the client can answer the fork.
    """
    from choice_card.intake_card import intake_card as _IC   # noqa: PLC0415
    st = _state(run_dir) or {}
    offered = st.get("offered") or {}
    media = [f for f in (st.get("presented") or []) if os.path.isfile(f)]
    if not media:
        media = [offered[n]["file"] for n in sorted(offered, key=int)]
    if not media:
        raise ChoiceError("no song versions are ready yet; nothing to send")
    argv = _IC.openclaw_send_argv(target, message or client_message(offered), media=media)
    (send or _run_send)(argv)
    return argv


# ---- Step 14: the message RECOMMENDS the strongest compliant version ------
#
# The method (Step 14; METHOD-INTEGRATION F9) asks for a recommendation of the
# strongest COMPLIANT candidate with a concrete explanation, "rather than making
# the owner evaluate an unfiltered pile of options". The client still picks --
# nothing here auto-picks, and the pick gate is untouched.

#: The gates that carry the method's music turns (ERM Drop first vocal, and the
#: two pace seams once U2's ``erm_drop``/``hero_shift`` anchors land). Names are
#: looked up in the take's own gate set, so a gate the judge does not emit simply
#: costs a candidate nothing -- no gate is invented here.
ERM_HERO_GATES = ("pace_change", "erm_drop", "hero_shift", "first_sung")
#: The earned-hook gates (Step 12): the third tiebreak.
HOOK_GATES = ("hook", "hook_placement")
#: Inert-until-wired (BUILD-PLAN): this runs only on a run that carries it.
METHOD_RECORD = os.path.join("control", "method.json")


def _verdicts(result):
    """``{gate name: verdict}`` from ONE result's constituent receipt, or ``{}``
    when it carries no gate results at all."""
    rec = (result or {}).get("receipt")
    gates = rec.get("gates") if isinstance(rec, dict) else None
    if not isinstance(gates, dict):
        return {}
    return {k: (v.get("verdict") if isinstance(v, dict) else v) for k, v in gates.items()}


def _passes(verdicts, names=()):
    """How many of ``names`` (default: every gate present) are PASS."""
    keys = names or tuple(verdicts)
    return sum(1 for k in keys if str(verdicts.get(k) or "").strip().upper() == "PASS")


def recommend(results):
    """The version to RECOMMEND, with the concrete reason Step 14 asks for.

    Ranking: the most PASS gates; then the measured ERM/Hero-Shift gates; then
    the earned hook; then the lowest version number, so the same run always
    recommends the same version. Only a version DELIVERY itself would offer is
    ever considered (the same acceptance test), so the recommendation can never
    name a version that is not in the client's hands.

    Returns ``{"n": <version number>, "reason": "<one plain line>"}``, or ``None``
    when no result carries gate results -- a run with no gate results says
    nothing extra."""
    ranked = []
    for r in results or []:
        if not isinstance(r, dict) or r.get("status") == "FAILED" or not r.get("take"):
            continue
        if not _accepted(r)[0]:                     # never recommend an unoffered take
            continue
        v = _verdicts(r)
        if not v:
            continue
        score = (_passes(v), _passes(v, ERM_HERO_GATES), _passes(v, HOOK_GATES))
        ranked.append((score, -int(r.get("n") or 0), r, v))
    if not ranked:
        return None
    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    _score, _neg_n, r, v = ranked[0]
    bits = ["it passed %d of %d song checks" % (_score[0], len(v))]
    if _score[1]:
        bits.append("the ERM / Hero Shift turn gates pass")
    if _score[2]:
        bits.append("the hook lands")
    return {"n": int(r["n"]), "reason": ", ".join(bits)}


def method_run(run_dir):
    """True when the run carries ``control/method.json`` (the intake card writes
    it at recap confirmation). Inert-until-wired: a run without that record gets
    today's message, byte for byte."""
    return os.path.isfile(os.path.join(run_dir or "", METHOD_RECORD))


# ---- the client's song-failure fork (order 2026-10-21) --------------------
#
# SONG-FAILURE VERDICT BELONGS TO THE CLIENT. When the song judge fails a
# take, nothing regenerates and nothing loops: the take keeps the judge's
# NAMED concerns, every take is presented for listening, and the client
# answers ONE question. That answer is authoritative and recorded in the run
# state (song-choices/fork-decision.json, appended, never clobbered). Only a
# recorded answer authorizes a new paid round; the pick/constituent gates are
# untouched, so nothing advances on a FAIL by itself.

FAILURE_FORK = ("Want me to redo all of them, keep one of these three, "
                "or generate three new options?")
FORK_ANSWERS = ("redo_all", "keep_one", "new_three")
_FORK_ALIASES = (
    ("redo all of them", "redo_all"), ("redo all", "redo_all"),
    ("redo", "redo_all"), ("redo them", "redo_all"),
    ("keep one of these three", "keep_one"), ("keep one", "keep_one"),
    ("generate three new options", "new_three"), ("three new options", "new_three"),
    ("new three", "new_three"),
)
FORK_FILE = "fork-decision.json"


def parse_fork_answer(reply):
    """The client's answer folded onto the three branches, or None (never
    guessed -- a pick number goes through record_pick, not here)."""
    t = re.sub(r"[^a-z0-9 ]+", " ", str(reply or "").lower()).strip()
    t = re.sub(r"\s+", " ", t)
    for phrase, answer in _FORK_ALIASES:
        if t == phrase or t.startswith(phrase):
            return answer
    return None


def failure_concerns(result):
    """The song judge's NAMED concerns for a take that did not pass, as plain
    lines. Empty when every gate passed."""
    r = result if isinstance(result, dict) else {}
    judged = r.get("receipt") if isinstance(r.get("receipt"), dict) else None
    if not judged or "gates" not in judged:
        recs = [x for x in (r.get("receipts") or []) if isinstance(x, dict)]
        judged = recs[-1] if recs else {}
    out = []
    for name in sorted(judged.get("gates") or {}):
        g = (judged.get("gates") or {})[name]
        v = (g or {}).get("verdict") if isinstance(g, dict) else g
        if str(v or "").strip().upper() == "PASS":
            continue
        detail = ((g or {}).get("detail") if isinstance(g, dict) else "") or ""
        out.append("%s: %s%s" % (name, str(v or "").strip().upper() or "UNKNOWN",
                                 (" - " + str(detail)) if detail else ""))
    return out


def failure_fork_message(results):
    """The one client message when any take failed the judge: the concerns in
    plain words, the client's freedom to say a take is fine, and the ONE
    question. No jargon, no second question."""
    failed = [r for r in results or [] if str(r.get("status") or "").upper() == "FAILED"]
    msg = ["I listened through your song options and checked them carefully.", ""]
    for r in failed:
        concerns = r.get("concerns") or failure_concerns(r)
        msg.append("Version %d needs work: %s."
                   % (r.get("n"), "; ".join(concerns) if concerns else "it did not pass my check"))
    if len(failed) < len(results or []):
        passed = [r for r in results or [] if r not in failed]
        msg += ["", "Version %s came through cleanly, and you can still pick one of those."
                % ", ".join(str(r.get("n")) for r in passed)]
    msg += ["", "These are my notes, not the final word: you may listen and decide one of "
                "them is exactly what you want.", FAILURE_FORK]
    return "\n".join(msg)


def record_fork_decision(run_dir, reply, who=None, channel="card", at=None):
    """Record the client's answer. Authoritative: nothing overrides it and no
    new paid round runs before it exists. An answer outside the three branches
    is refused, never guessed."""
    ans = parse_fork_answer(reply)
    if ans is None:
        raise ChoiceError("%r is not one of the three answers; ask again: %s"
                          % (reply, FAILURE_FORK))
    rec = {"answer": ans, "reply": str(reply), "who": who, "channel": channel,
           "at": at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    doc = {}
    p = _path(run_dir, FORK_FILE)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                doc = json.load(f) or {}
        except (OSError, ValueError):
            doc = {}                     # unreadable: a fresh doc, never a guess
    log = doc.get("decisions") if isinstance(doc.get("decisions"), list) else []
    _write(run_dir, FORK_FILE, dict(doc, decisions=log + [rec]))
    return rec


def fork_decision(run_dir):
    """The latest recorded client answer, or None when the client has not
    answered yet."""
    try:
        with open(_path(run_dir, FORK_FILE), encoding="utf-8") as f:
            doc = json.load(f) or {}
    except (OSError, ValueError):
        return None
    log = doc.get("decisions") or []
    return log[-1] if log and isinstance(log[-1], dict) else None


def client_message(offered, failed=(), recommend=None, concerns=None):
    nums = sorted(int(n) for n in offered)
    rows = ["%d. %s - %s" % (n, offered[str(n)]["label"].split(" - ", 1)[1], offered[str(n)]["duration"])
            for n in nums]
    pick = "%s or %d" % (", ".join(map(str, nums[:-1])), nums[-1]) if len(nums) > 1 else str(nums[0])
    msg = ["Your song is ready in %d versions. They are in the %s folder:" % (len(nums), DIRNAME), ""] + rows
    if failed:
        msg += ["", "Version %s did not pass all of my song checks, so I have not offered it for "
                    "your pick." % ", ".join(map(str, failed))]
        for n in sorted(failed):
            why = (concerns or {}).get(str(n)) or []
            if why:
                msg.append("Version %d: %s." % (n, "; ".join(why)))
        msg += ["", "You can still keep one of them if it sounds right to you.", FAILURE_FORK]
        return "\n".join(msg)
    if isinstance(recommend, dict) and recommend.get("n") is not None:
        msg += ["", "I recommend version %d because %s."
                % (int(recommend["n"]), recommend.get("reason") or "it passed every song check")]
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


def answer_provenance(answer, target=None, channel="card"):
    """WW-09 item 3: who answered (the client, a delegated assistant under
    recorded authority, or unknown), on which channel, and at what time. The
    intake card IS the client's own channel, so a card answer with the client's
    chat id is the client's; an answer that names another channel with no author
    is UNKNOWN (unspecified), never a client decision."""
    a = answer if isinstance(answer, dict) else {}
    author = a.get("who") or a.get("author") or a.get("by") or (str(target) if target else None)
    ch = a.get("channel") or channel
    unknown = not author and a.get("channel") is not None and a.get("channel") != "card"
    return {"who": author, "channel": ch, "at": a.get("at") or a.get("when"),
            "unknown": bool(unknown)}


def classify_song_answer(answers, target=None):
    """WW-09: (required, provenance, reason).

    An EXPLICIT client answer is honoured: Yes = three labelled versions, No =
    one song, exactly as recorded. A MISSING answer (no song row), a CORRUPT one
    (n not 1 or 2) or an AUTHOR-LESS delegated one is NEVER silently turned into
    No: it is treated as UNSPECIFIED and routed to the recommended Yes, and the
    refusal to guess is recorded with the answer."""
    rows = [a for a in (answers or []) if isinstance(a, dict)]
    rec = next((a for a in rows if a.get("id") == "song"), None)
    if rec is None:
        return True, {"channel": "card", "unknown": True}, \
            ("no song answer recorded: treated as unspecified and routed to the "
             "recommended Yes (three labelled versions)")
    prov = answer_provenance(rec, target)
    n = rec.get("n")
    if n not in (1, 2) or prov["unknown"]:
        return True, prov, \
            ("the song answer (n=%r, author=%r) is corrupt or has no recorded "
             "author: treated as unspecified and routed to the recommended Yes"
             % (n, prov["who"]))
    return n == 1, prov, ""


def record_card_answer(run_dir, answers, target=None):
    """The intake card's SONG APPROVAL answer -> the run (Yes turns the gate on,
    No records No). Called when the recap is confirmed. A changed answer before
    the songs are made replaces the old one; once versions exist (resume) the
    recorded answer is kept untouched.

    WW-09: a missing, corrupt or author-less answer is never read as No (it
    routes to the recommended Yes and records the refusal to guess); the
    channel, the author and the timestamp, when recorded, are stored with the
    answer so nobody can answer for the client unnoticed."""
    st = _state(run_dir)
    if st and st.get("offered"):
        return bool(st.get("required"))
    required, prov, guess_reason = classify_song_answer(answers, target)
    if guess_reason:
        prov = dict(prov, refused_to_guess=guess_reason)
    init(run_dir, required, target or (st or {}).get("target"), provenance=prov)
    return required


def init(run_dir, required, target=None, provenance=None):
    """Record the card answer (and the client's chat id). Call once when the card is approved."""
    st = {"required": bool(required), "offered": {}}
    if target:
        st["target"] = str(target)
    if provenance is not None:
        st["provenance"] = provenance
    _write(run_dir, "state.json", st)


def _sha(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def picked_song(run_dir):
    return os.path.join(run_dir, "music", "picked-song.mp3")


def record_pick(run_dir, reply):
    """The client's 1, 2 or 3. Anything not offered is refused; returns the label.

    WW-18: a file may be picked only when its take's REQUIRED gate set all
    PASSED (its constituent receipt is current); an offered file whose take did
    not pass every required gate is refused here and at delivery."""
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
    ok, why = _SD.constituent_ok(o.get("receipt"))
    if not ok:
        raise ChoiceError("song %s is not offerable: %s" % (reply, why))
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


def _refuse_constituent(why):
    return {"reason_code": "SONG_CONSTITUENT_EVIDENCE_MISSING", "detail": why,
            "next_action": "Re-record the take's constituent-evidence receipt (every required "
                           "gate PASS) before any picture, image or video spend."}


def constituent_hold(run_dir):
    """WW-08 item 3: every OFFERED song must carry a current constituent-evidence
    receipt (its required gates all PASS). A missing or blocked receipt closes
    the gate at every later purchase and at delivery. None = nothing to hold."""
    try:
        st = _state(run_dir)
    except (OSError, ValueError):
        return _refuse_constituent("the song-choices state is unreadable")
    if not st or not st.get("required"):
        return None
    bad = []
    for n, o in (st.get("offered") or {}).items():
        ok, why = _SD.constituent_ok((o or {}).get("receipt"))
        if not ok:
            bad.append("%s: %s" % (n, why))
    return _refuse_constituent("; ".join(bad)) if bad else None


def dispatch_refusal(is_music_job, run_dir):
    """kie_dispatch seam: the song stage itself may run; everything else waits
    until the pick is in AND every offered song's constituent receipt is
    current (WW-08 item 3)."""
    if is_music_job:
        return None
    return refusal(run_dir) or constituent_hold(run_dir)


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


def _hook_text(spec):
    """WW-09 item 5: the hook text the hook gate measures -- the sung lines the
    sheet itself repeats (suno_recipe's own rule). Non-empty for a shipped sheet
    and never a silent empty default."""
    sung = [s for s in (spec.get("sheet") or [])
            if s.get("delivery") == "sung" and s.get("lines")
            and not str(s.get("tag", "")).lower().startswith("vocalise")]
    counts = {}
    for s in sung:
        key = " ".join(str(x) for x in s["lines"])
        counts[key] = counts.get(key, 0) + 1
    if not counts:
        return ""
    best = max(counts, key=counts.get)
    return best if counts[best] >= 2 else ""


def _envelope_path(run_dir, variant_id):
    return os.path.join(run_dir, "music", "takes", variant_id, "dispatch-envelope.json")

def _write_envelope(run_dir, variant_id, evidence):
    p = _envelope_path(run_dir, variant_id)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"variant_id": variant_id, "evidence": evidence}, f, indent=2, sort_keys=True)
    return p


def _card_receipt(run_dir):
    """The run's recorded four-pick card receipt, read from the run folder.

    ``kie_dispatch.card_gate_refusal`` refuses EVERY paid job that carries no
    ``card_receipt`` (F15: no paid job starts on an unanswered card), and the
    music path never attached one -- so every dispatch, the word-timing
    sub-calls included, refused CARD_UNANSWERED although the client had
    answered and the receipt was on disk.

    Read in this order, each shape taken only when it really carries the
    answers: ``control/card-receipt-block.json`` (the stamped block),
    ``control/card-receipt.json`` when it holds an ``answers`` dict (the
    per-question record), ``control/run-state.json["card_receipt"]``. Nothing
    found returns None: the gate then refuses exactly as before. A receipt is
    never fabricated.
    """
    def _ok(block):
        return isinstance(block, dict) and isinstance(block.get("answers"), dict)

    p = os.path.join(run_dir, "control", "card-receipt-block.json")
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = None
    if _ok(doc):
        return doc

    p = os.path.join(run_dir, "control", "card-receipt.json")
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = None
    if _ok(doc):
        return doc

    p = os.path.join(run_dir, "control", "run-state.json")
    try:
        with open(p, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        doc = None
    block = doc.get("card_receipt") if isinstance(doc, dict) else None
    return block if _ok(block) else None


def _sheet_lyric_words(spec):
    """The approved sheet's LYRIC LINES only -- what the script_words gate asks.

    ``script_words`` is a REQUIRED_TAKE_GATE: it checks the TAKE sang the
    approved lyrics. It was handed ``spec["client_text"]``, the source
    research document, so every take was asked to sing a sales page. The
    sheet's bracket headers are directions to Suno (``[Verse 1 (sung):
    melodic, rhymed, slow long held notes]``), never lyrics, so they are
    excluded here too -- ``song_dispatch._script_lyric_words`` only drops
    brackets from text it is given, and this hands it text that never had
    them. Falling back to ``sheet_text`` keeps a sheet that failed to parse
    no worse off than before. ``client_text`` stays the hook-vocabulary
    source and nothing else (``build_requests``).
    """
    lines = []
    for sec in spec.get("sheet") or []:
        if not isinstance(sec, dict):
            continue
        for line in sec.get("lines") or []:
            if str(line).strip():
                lines.append(str(line))
    if lines:
        return " ".join(lines)
    return spec.get("sheet_text") or ""


def _next_attempt_id(ledger_db, run_id, logical_key):
    """Mint the next attempt id from the spend ledger.

    spend_ledger.plan() refuses a duplicate (logical_key, attempt_id) on
    purpose, but the shipped generate path used a literal "a1" for every
    dispatch, so a retry after a failed paid take was refused
    DUPLICATE_ATTEMPT and the retry path was structurally dead.
    """
    try:
        import sqlite3
        con = sqlite3.connect(ledger_db)
        rows = con.execute(
            "SELECT attempt_id FROM jobs WHERE logical_key=? AND run_id=?",
            (logical_key, run_id)).fetchall()
        con.close()
        import re as _re
        nums = [int(m.group(1)) for (aid,) in rows
                if (m := _re.match(r"a(\d+)$", str(aid or "")))]
        n = (max(nums) + 1) if nums else 1
    except Exception:
        n = 1
    return "a%d" % max(n, 1)


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
        # F15: the run's recorded card receipt rides the request. Without it
        # every paid job -- each song and each word-timing sub-call -- was
        # refused CARD_UNANSWERED even though the client had answered. A
        # request that already carries its own receipt is left alone.
        payload = dict(request)
        if not isinstance(payload.get("card_receipt"), dict):
            receipt = _card_receipt(run_dir)
            if receipt is not None:
                payload["card_receipt"] = receipt
        att_id = _next_attempt_id(ledger, run_id or (os.path.basename(run_dir) or "run"),
                                  "song/%s" % variant["id"])
        env = _KD.dispatch(model=payload.get("model") or "ai-music-api/generate",
                           request=payload, save_dir=save_dir, ledger_db=ledger,
                           run_id=run_id or (os.path.basename(run_dir) or "run"),
                           logical_key="song/%s" % variant["id"],
                           attempt_id=att_id, estimated_cost=_SD.GEN_COST_CENTS,
                           prompt=payload.get("input", {}).get("style", "")[:2000])
        ev = env.get("evidence", {}) if isinstance(env, dict) else {}
        _write_envelope(run_dir, variant["id"], ev)
        # D2 item 3: the overlap receipt, built from the PROVIDER lifecycle
        # stamps only. accepted_submit_at is stamped after a valid task-id
        # acknowledgment; terminal_at at the first terminal provider response.
        # No receipt when the provider never acknowledged or never terminated:
        # the gate then reports UNAVAILABLE, which is never a pass.
        if ev.get("accepted_submit_at") and ev.get("terminal_at"):
            receipt_for(run_dir, variant, request, att_id, ev.get("task_id"),
                        ev["accepted_submit_at"], ev["terminal_at"])
        # Provenance for lyric_timing (reads take["task_id"] / take["audio_id"]).
        # The envelope carries the generation task id only; the per-track Suno
        # audio id is not surfaced, so audio_id stays ABSENT -- never filled
        # with the task id. A dispatcher-synthesized "sync-" id is not a
        # provider id and is not recorded.
        task_id = ev.get("task_id")
        prov = ({"task_id": task_id} if isinstance(task_id, str) and task_id
                and not task_id.startswith("sync-") else {})
        takes = []
        if isinstance(env, dict) and env.get("outcome") == "ok":
            for p in ev.get("saved_paths", []) or []:
                takes.append(dict(prov, audio_path=p))
        return takes
    return generate


def cmd_generate(a, generate=None, measure=None, save=None, plan=None):
    """`generate` -- the canonical three-version music runner.

    Orchestrated mode (``--variant``/``--unit-id``): ONE worker, ONE owned
    variant folder, ONE generation. Umbrella mode (neither flag, non-workflow
    run): all three once, three provider jobs in three threads inside this one
    agent unit. The fan-in only ever CHECKS and DELIVERS existing results.

    WW-09 item 5: a production run REFUSES an empty ``measure``/``save``
    transport or an empty hook text rather than substituting a silent no-op --
    a take judged on no measurements, or a hook gate that never ran, is the
    defect this unit fixes.
    """
    run_dir = os.path.abspath(os.path.expanduser(a.run_dir))
    spec = _load_request(a.request)
    for _label, _fn in (("measure", measure), ("save", save)):
        if _fn is None:
            raise ChoiceError("REFUSED: the production run needs a real %s transport, "
                              "not an empty default no-op" % _label)
    hook_text = _hook_text(spec)
    if not str(hook_text).strip():
        raise ChoiceError("REFUSED: the run has no hook text (the sheet repeats no "
                          "sung hook); the hook gate cannot be skipped")
    reqs = build_requests(spec["style_id"], spec["sheet"], spec["client_text"],
                          spec["title"], spec["length_s"], spec["vocal_gender"],
                          hook_plan=spec["hook_plan"], pace_plan=spec["pace_plan"])
    _require_three(reqs, key=lambda r: r[0]["id"])
    plan = plan or {"delivered_s": spec["length_s"], "style_id": spec["style_id"],
                    "sheet_text": spec["sheet_text"], "hook_plan": spec["hook_plan"],
                    "_pace_plan": spec["pace_plan"]}
    gen = generate or _real_generate(run_dir, a.ledger, a.run_id)
    kw = dict(plan=plan, generate=gen, measure=measure, save=save,
              script_words=_sheet_lyric_words(spec), hook_text=hook_text)
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
    fk = sub.add_parser("fork", help="record the client's answer to the song-failure fork")
    fk.add_argument("--run-dir", required=True)
    fk.add_argument("--reply", required=True)
    fk.add_argument("--who", default="")
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
            try:
                print("Picked: " + record_pick(a.run_dir, a.reply))
            except ChoiceError:
                # SONG-FAILURE VERDICT BELONGS TO THE CLIENT (order 2026-10-21):
                # the client answered the fork in words, not a number. Record
                # that answer and re-raise only when it is none of the three.
                if parse_fork_answer(a.reply) is None:
                    raise
                rec = record_fork_decision(a.run_dir, a.reply)
                print("Fork recorded: " + rec["answer"])
        elif a.cmd == "fork":
            rec = record_fork_decision(a.run_dir, a.reply, who=a.who or None)
            print("Fork recorded: " + rec["answer"])
        elif a.cmd == "generate":
            # The CLI is the command the stage runbook hands agents, so it
            # supplies the REAL transports itself: measurements off the take's
            # own audio (song_transports.make_measure, which runs the one
            # word-timing step) and every paid take kept on disk
            # (make_save). ``cmd_generate`` still refuses a programmatic
            # ``measure``/``save`` of None -- that guard is untouched; it was
            # never meant to describe the shipped runner.
            import song_transports as _ST        # noqa: PLC0415
            _run_dir = os.path.abspath(os.path.expanduser(a.run_dir))
            _spec = _load_request(a.request)
            # The word-timing step is wired here too: hook, hook_placement and
            # song_contract cannot be measured without it, and the step carries
            # the SAME run receipt this file attaches, so its own paid sub-call
            # clears the same card gate.
            _timings = _ST.make_timings(
                _run_dir, ledger=a.ledger or os.path.join(_run_dir, "spend.sqlite3"),
                run_id=a.run_id)
            out = cmd_generate(
                a,
                measure=_ST.make_measure(pace_plan=_spec.get("pace_plan"),
                                         timings=_timings),
                save=_ST.make_save(_run_dir))
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

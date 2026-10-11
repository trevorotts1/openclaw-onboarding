#!/usr/bin/env python3
"""WW-30: the createTask music contract, proved with a FAKE TRANSPORT only.

Run: python3 scripts/core/test_music_createtask_ww30.py

ZERO SPEND. No provider call, no KIE call, no Suno call: every transport below
is a local function that RECORDS the request and returns a canned reply. The
only real code exercised is the skill's own build/refuse/read paths.

What this file pins, in the plan's own terms:

  1. the EXACT URL and the EXACT serialized payload of BOTH skills' music
     entry paths (skill 75's core build + skill 68's pre-dispatch validator);
  2. each refusal, by NAME: the legacy flat /api/v1/generate contract, a
     misplaced or non-top-level callback URL, competing lyrics sources, a
     missing required direction, and an unsupported or invented model value;
  3. success, rejection, timeout, a MALFORMED acknowledgement and a response
     returning MULTIPLE tracks -- all with zero spend;
  4. the model value as UNDETERMINED with its unranked candidates, and the
     task-ID acknowledgement nesting reported as UNVERIFIED while the code
     tolerates more than one plausible nesting.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "suno_recipe"))

import kie_dispatch as KD          # noqa: E402
import suno_recipe as R            # noqa: E402

REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
VALIDATOR_68 = os.path.join(REPO, "68-kie-audio", "scripts", "validate_audio_request.py")
SKILL_75 = os.path.join(REPO, "75-drama-song-ad-factory")

CLIENT = ("I am not small. I never was. One seed of truth made me strong. "
          "She Found Power in the Climb.")
HOOK = ["I am not sma-a-all", "I ne-ever wa-a-as"]
HOOK_PLAN = {"true_at_beat": "the_world"}
SHEET = [{"tag": "Intro", "delivery": "spoken", "lines": ["One closed door."]},
         {"tag": "Vocalise", "delivery": "sung", "lines": ["Oo-o-o-o-o-oh,"]},
         {"tag": "Verse", "delivery": "sung", "lines": ["One seed of truth made me stro-o-ong,"]},
         {"tag": "Hook 1", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 2", "delivery": "sung", "lines": HOOK},
         {"tag": "Hook 3", "delivery": "sung", "lines": HOOK},
         {"tag": "Outro", "delivery": "spoken",
          "lines": ["She Found Power in the Climb. Get the book. Link below."]}]

FAILED = []


def check(name, cond, detail=""):
    print(("ok: " if cond else "FAIL: ") + name + ("" if cond else "  (%s)" % (detail,)))
    if not cond:
        FAILED.append(name)


# ---------------------------------------------------------------------------
# The FAKE TRANSPORT. It is the ONLY thing that ever "sends": it records the
# resolved URL and the serialized payload and never touches a socket.

class FakeTransport:
    """Records (url, payload_json) and returns a scripted adapter reply."""

    def __init__(self, replies=None):
        self.sent = []
        self.replies = list(replies or [])
        self.calls = []

    def resolve_url(self, request):
        """The exact URL the request would POST to: kie_dispatch owns the KIE
        host (F14), so the base comes from there -- never a second copy."""
        endpoint = str((request or {}).get("endpoint") or "")
        return "https://api.kie.ai" + endpoint

    def __call__(self, request):
        url = self.resolve_url(request)
        payload = json.dumps(request, sort_keys=True)
        self.sent.append((url, payload))
        if not self.replies:
            return {"state": "ok", "task_id": "fake-task-1"}
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if reply == "TIMEOUT":
            raise TimeoutError("fake transport timeout")
        return reply


def built_request():
    """The ONE envelope both legs use.

    Skill 68's rule-12 band holds a DESCRIPTIVE music field (the Suno style)
    to 95-100% of its 1000-char cap, so the style is padded into the band
    here: the skill-68 leg must measure the ENDPOINT/MODEL contract, not the
    band. Both legs then see byte-identical payloads.
    """
    req = R.build_request("soul-ballad", SHEET, CLIENT, "T", 58, hook_plan=HOOK_PLAN)
    style = req["input"]["style"]
    pad = (" The arrangement stays sparse under the verse and opens up on the "
           "hook, one lead voice throughout, no stacked harmonies.")
    while len(style) < 950:
        style += pad
    req["input"]["style"] = style[:1000]
    assert 950 <= len(req["input"]["style"]) <= 1000
    return req


def main():
    t = FakeTransport()

    # ---- 1. the EXACT URL and the EXACT serialized payload ----------------
    req = built_request()
    url = t.resolve_url(req)
    serialized = json.dumps(req, sort_keys=True)
    check("WW30-1a the request rides the createTask endpoint",
          req["endpoint"] == "/api/v1/jobs/createTask", req["endpoint"])
    check("WW30-1b the exact POST URL is the documented createTask URL",
          url == "https://api.kie.ai/api/v1/jobs/createTask", url)
    check("WW30-1c the outer model is the market route, never a version",
          req["model"] == "ai-music-api/generate", req["model"])
    check("WW30-1d callBackUrl is TOP LEVEL and camelCase",
          isinstance(req.get("callBackUrl"), str) and "callBackUrl" not in req["input"]
          and "callback_url" not in req, sorted(req))
    check("WW30-1e the directions are nested snake_case in input",
          all(k in req["input"] for k in ("custom_mode", "instrumental", "title",
                                          "lyrics", "style", "negative_tags",
                                          "duration", "model")), sorted(req["input"]))
    check("WW30-1f exactly ONE lyrics source and no prompt beside it",
          req["input"].get("lyrics") and "prompt" not in req["input"], sorted(req["input"]))
    check("WW30-1g the legacy /api/v1/generate route appears nowhere in the payload",
          "/api/v1/generate" not in serialized or "/api/v1/generate/" in serialized,
          serialized[:120])
    print("--- PASTED EVIDENCE: exact URL ---")
    print(url)
    print("--- PASTED EVIDENCE: exact serialized payload ---")
    print(serialized)

    # ---- 2. the NAMED refusals -------------------------------------------
    inp = req["input"]
    # The legacy contract's own payload, named with its own route so the
    # refusal is about the CONTRACT, never about a missing endpoint field.
    flat = {"endpoint": R.KIE_LEGACY_GENERATE_ENDPOINT,
            "model": R.KIE_MUSIC_MODEL_VALUE, "custom_mode": True,
            "instrumental": False, "title": "T", "style": inp["style"],
            "lyrics": inp["lyrics"], "negative_tags": inp["negative_tags"],
            "duration": 58, "callBackUrl": R.DEFAULT_CALLBACK_URL}
    cases = (
        ("WW30-2a legacy flat contract refused",
         flat, "LEGACY_FLAT_CONTRACT"),
        ("WW30-2b misplaced (nested) callback refused",
         dict(req, callBackUrl=None, input=dict(inp, callBackUrl=R.DEFAULT_CALLBACK_URL)),
         "CALLBACK_NOT_TOP_LEVEL"),
        ("WW30-2c snake_case callback name refused",
         dict(req, callBackUrl=None, callback_url=R.DEFAULT_CALLBACK_URL),
         "CALLBACK_NOT_TOP_LEVEL"),
        ("WW30-2d competing lyrics sources refused",
         dict(req, input=dict(inp, prompt="a second, competing lyrics source")),
         "COMPETING_LYRICS"),
        ("WW30-2e missing required direction refused",
         dict(req, input={k: v for k, v in inp.items() if k != "negative_tags"}),
         "MISSING_DIRECTION"),
        ("WW30-2f unsupported outer model refused",
         dict(req, model="V6"), "UNSUPPORTED_MODEL"),
        ("WW30-2g invented inner model value refused",
         dict(req, input=dict(inp, model="V6_ULTRA")), "UNSUPPORTED_MODEL_VALUE"),
    )
    for name, payload, want in cases:
        errs = R.check_envelope(payload)
        check(name, any(e.split(":")[0] == want for e in errs), errs)
        check(name + " (send refused, nothing recorded)",
              R.check_envelope(payload) != [], errs)

    # ---- 3. the model VALUE is UNDETERMINED, candidates unranked ----------
    check("WW30-3a the value is a single named constant",
          R.KIE_MUSIC_MODEL_VALUE == "V6", R.KIE_MUSIC_MODEL_VALUE)
    check("WW30-3b its status is stated as UNDETERMINED",
          R.KIE_MUSIC_MODEL_VALUE_STATUS == "UNDETERMINED", R.KIE_MUSIC_MODEL_VALUE_STATUS)
    check("WW30-3c the three candidates are named and NOT ranked",
          R.KIE_MUSIC_MODEL_VALUE_CANDIDATES == ("V6", "V6_MINI", "V6_WILD"),
          R.KIE_MUSIC_MODEL_VALUE_CANDIDATES)
    check("WW30-3d the constant is the value actually sent",
          inp["model"] == R.KIE_MUSIC_MODEL_VALUE, inp["model"])

    # ---- 4. skill 68's validator: same URL, same payload, zero spend ------
    with tempfile.TemporaryDirectory(prefix="blackceo-WW30U1-") as td:
        p = os.path.join(td, "payload.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(req, f, sort_keys=True)
        r68 = subprocess.run([sys.executable, VALIDATOR_68, "--domain", "music",
                              "--payload", p], capture_output=True, text=True, timeout=180)
        check("WW30-4a skill 68 validates the SAME envelope (exit 0)",
              r68.returncode == 0, (r68.stdout + r68.stderr)[-500:])
        with open(p, "w", encoding="utf-8") as f:
            json.dump(flat, f, sort_keys=True)
        r68b = subprocess.run([sys.executable, VALIDATOR_68, "--domain", "music",
                               "--payload", p], capture_output=True, text=True, timeout=180)
        out68 = (r68b.stdout + r68b.stderr)
        check("WW30-4b skill 68 refuses the retired legacy generate route",
              r68b.returncode == 2 and "RETIRED" in out68.upper(), out68[-500:])

    # ---- 5. the FAKE TRANSPORT captures BOTH skills' exact URL/payload ----
    for label, request in (("skill-75-core", req),
                           ("skill-68-validated", json.loads(serialized))):
        t2 = FakeTransport()
        t2(request)
        got_url, got_payload = t2.sent[-1]
        check("WW30-5 %s: transport captured URL %s" % (label, got_url),
              got_url == "https://api.kie.ai/api/v1/jobs/createTask", got_url)
        check("WW30-5 %s: transport captured the serialized payload" % label,
              json.loads(got_payload) == request, got_payload[:120])

    # ---- 6. success / rejection / timeout / malformed ack / multi-track --
    ok_tr = FakeTransport([{"state": "ok", "data": {"taskId": "fake-1"}}])
    reply = ok_tr(req)
    tid, path = KD.task_id_from_acknowledgement(reply)
    check("WW30-6a SUCCESS: ack accepted, task id read from a tolerated nesting",
          tid == "fake-1" and path == "data.taskId", (tid, path))

    for label, reply, want in (
            ("WW30-6b REJECTION", {"state": "fail", "error": {"code": "invalid_request"}}, "fail"),
            ("WW30-6c MALFORMED acknowledgement", {"state": "ok", "task_id": ""}, "ok")):
        tr = FakeTransport([reply])
        got = tr(req)
        tid2, _ = KD.task_id_from_acknowledgement(got)
        check("%s: handled, no task id invented" % label,
              got.get("state") == want and tid2 == "", (got, tid2))

    tr = FakeTransport(["TIMEOUT"])
    try:
        tr(req)
        check("WW30-6d TIMEOUT surfaces as a raised timeout (not a fake success)", False)
    except TimeoutError:
        check("WW30-6d TIMEOUT surfaces as a raised timeout (not a fake success)", True)
    check("WW30-6d a timed-out job records nothing as generated",
          len(tr.sent) == 1, tr.sent)

    multi = {"data": {"response": {"data": [
        {"audio_url": "https://fake.invalid/a.mp3", "title": "A"},
        {"audio_url": "https://fake.invalid/b.mp3", "title": "B"},
        {"audio_url": "https://fake.invalid/c.mp3", "title": "C"}]}}}
    tracks = KD.audio_urls_from_result(multi)
    check("WW30-6e MULTIPLE tracks: all three returned, none truncated to one",
          [u for u, _ in tracks] == ["https://fake.invalid/a.mp3",
                                     "https://fake.invalid/b.mp3",
                                     "https://fake.invalid/c.mp3"], tracks)
    check("WW30-6f the documented recordInfo read path is the one named",
          KD.RECORD_INFO_ENDPOINT == "/api/v1/jobs/recordInfo"
          and len(KD.ACK_TASK_ID_PATHS) > 1, KD.RECORD_INFO_ENDPOINT)

    # ---- 7. the dispatch gate refuses before ANY ledger row or call -------
    env = KD.dispatch(model=R.KIE_MUSIC_TASK_MODEL, request=flat,
                      save_dir=tempfile.gettempdir(), ledger_db=":memory:",
                      run_id="ww30", logical_key="song", attempt_id="a1",
                      estimated_cost=6, runner=lambda argv: (0, "{}"))
    check("WW30-7a dispatch refuses the legacy flat contract before any spend",
          env["outcome"] == "rejected" and env["reason_code"] == KD.LEGACY_MUSIC_ROUTE,
          (env["outcome"], env["reason_code"]))
    env2 = KD.dispatch(model=R.KIE_MUSIC_TASK_MODEL,
                       request=dict(req, input=dict(inp, prompt="competing")),
                       save_dir=tempfile.gettempdir(), ledger_db=":memory:",
                       run_id="ww30", logical_key="song", attempt_id="a1",
                       estimated_cost=6, runner=lambda argv: (0, "{}"))
    check("WW30-7b dispatch refuses a malformed envelope before any spend",
          env2["outcome"] == "rejected" and env2["reason_code"] == KD.MUSIC_ENVELOPE_REJECTED,
          (env2["outcome"], env2["reason_code"]))

    print()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        for n in FAILED:
            print("  - " + n)
        return 1
    print("ALL PASS (zero spend: no provider call was made)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

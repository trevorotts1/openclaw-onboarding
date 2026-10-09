#!/usr/bin/env python3
"""FU-U7: video and avatar prompt caps, fail closed, enforced AT DISPATCH.

Proves (plan E.1, file 17):
  1. an H3 prompt of 7,001 chars is refused at dispatch (PROMPT_OVER_CAP,
     cap 7,000, status VERIFIED) before the ledger and before Skill 74;
  2. a Kling 2.5 Turbo prompt of 2,501 is refused PROMPT_OVER_CAP (2,500) and
     a negative_prompt of 2,501 is refused too - file 17's 2,500 each;
  3. a kling/ai-avatar-standard prompt of 2,501 is refused PROMPT_OVER_CAP
     (2,500, UNVERIFIED override) BEFORE the picture gate can mask it;
  4. a Kling 3.0 Omni prompt of 3,073 is refused (3,072) and a Hailuo prompt
     of 2,001 is refused (2,000 - H3 itself keeps the catalog's 7,000);
  5. at the cap and under it the job still runs: H3 7,000 and a 200-char
     prompt both dispatch (the 67 house floor of 5000 is NEVER applied - the
     brief's house band sits above Kling's hard cap and must not pad);
  6. the ok receipt carries the measured cap and its status (prompt_caps);
  7. the refusal names field, chars, cap, source and status and truncates
     nothing (chars stay 7,001 - the payload is never trimmed to pass);
  8. nothing is reserved and nothing is sent on a refusal (no ledger row,
     zero Skill 74 calls).

Zero paid calls: Skill 74 is a fake runner, the ledger DBs are throwaway temp
files. Run: HOME=$(mktemp -d) python3 core/kie_dispatch/test_prompt_cap_u7.py
(exit 0 = pass, 1 = failures). On the base tree (no dispatch-side cap check)
this suite FAILS: the over-cap jobs reach submit and the wrong refusal wins.
"""
import importlib
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))          # core/

import kie_dispatch.model_lock as ML   # noqa: E402
import prompt_limits as PL             # noqa: E402
import spend_ledger as L               # noqa: E402

MODULE = importlib.import_module("kie_dispatch.kie_dispatch")

FAILS = []


def _forbid_make_runner(*_a, **_k):
    """Zero paid calls: no test may ever spawn the real Skill 74."""
    raise AssertionError("real Skill 74 runner disabled in tests")


MODULE.make_runner = _forbid_make_runner


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name,
                        (" (%s)" % detail) if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


class Fake74:
    def __init__(self, script):
        self.script = script
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        if sub not in self.script:
            raise AssertionError("unexpected Skill 74 call: %r" % sub)
        res = self.script[sub]
        if isinstance(res, Exception):
            raise res
        return res

    def order(self):
        return [c[1] for c in self.calls]


HEALTH_ACTIVE = (0, {"adapter_mode": "active", "state": "success"})
PREFLIGHT_OK = (0, {"state": "validated", "data": {"ok": True}})
BUDGET_OK = (0, {"state": "success",
                 "data": {"status": "OK", "exit_code": 0, "max": 20000}})
BASE_SCRIPT = {
    "health": HEALTH_ACTIVE,
    "preflight": PREFLIGHT_OK,
    "prompt-budget": BUDGET_OK,
    "submit": (0, {"state": "queued", "task_id": "t-u7",
                   "raw_family": "market"}),
    "wait": (0, {"state": "success", "task_id": "t-u7", "raw_family": "market",
                 "credits_consumed": 16}),
    "save": (0, {"state": "success", "task_id": "t-u7",
                 "saved_paths": ["/tmp/u7.mp4"], "credits_consumed": 16}),
}

STAMPED_CARD = {"answers": {"video_style": "Lifelike 3D",
                            "audio_style": "Soul Ballad",
                            "length": 60,
                            "video_model": "MiniMax H3 768P"},
                "who": "FU-U7 prompt-cap test",
                "at": "2026-10-09T09:00:00Z"}


def disp(label, model, input_body, lock=None):
    """One dispatch against a fake Skill 74. request['model'] stays 'm' (an
    image id by cue) so the F6 storyboard gate does not mask the cap gate."""
    tmp = tempfile.mkdtemp(prefix="pu7-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-u7", 10000)
    state_db = os.path.join(tmp, "state.db")
    if lock:
        ML.lock_run_model(state_db, "run-u7", lock)
    fake = Fake74(BASE_SCRIPT)
    req = {"model": "m", "input": dict(input_body), "card_receipt": STAMPED_CARD}
    env = MODULE.dispatch(
        model=model, request=req, save_dir=tmp, ledger_db=db,
        run_id="run-u7", logical_key=label, attempt_id="att-1",
        estimated_cost=100, prompt=input_body.get("prompt", ""),
        adapter_path=os.path.abspath(__file__), runner=fake,
        state_store=state_db)
    return env, fake, db, tmp


def ledger_rows(db, logical_key):
    conn = sqlite3.connect(db)
    try:
        return conn.execute("SELECT COUNT(*) FROM jobs WHERE logical_key=?",
                            (logical_key,)).fetchone()[0]
    finally:
        conn.close()


def refused(label, model, input_body, cap, status, lock=None):
    env, fake, db, _ = disp(label, model, input_body)
    check("%s: refused PROMPT_OVER_CAP (%r)" % (label, env.get("reason_code")),
          env["outcome"] == "rejected"
          and env["reason_code"] == "PROMPT_OVER_CAP", str(env))
    ev = env.get("evidence") or {}
    check("%s: refusal names field/chars/cap/source/status" % label,
          ev.get("field") and ev.get("chars") and ev.get("cap") == cap
          and ev.get("cap_source") and ev.get("cap_status") == status
          and ev.get("generated") is False, str(ev))
    check("%s: payload was NOT truncated (chars %s kept)"
          % (label, ev.get("chars")),
          ev.get("chars") == len(input_body.get(ev.get("field"), "")), str(ev))
    check("%s: nothing sent to Skill 74" % label, fake.calls == [],
          str(fake.calls))
    check("%s: nothing reserved in the ledger" % label,
          ledger_rows(db, label) == 0, str(ledger_rows(db, label)))
    return ev


# ---- 1. MiniMax H3: 7,001 refused, 7,000 runs ------------------------------
def test_h3_cap():
    ev = refused("h3-over", "minimax-h3/text-to-video",
                 {"prompt": "x" * 7001}, 7000, "VERIFIED")
    check("h3: cap 7,000 is the catalog number",
          "7000" in (ev.get("cap_source") or "") or ev.get("cap") == 7000, str(ev))

    env, fake, _, _ = disp("h3-at", "minimax-h3/text-to-video",
                           {"prompt": "x" * 7000},
                           lock=ML.DEFAULT_VIDEO_MODEL)
    check("h3: prompt of exactly 7,000 still dispatches",
          env["outcome"] == "ok", str(env))
    caps = (env.get("evidence") or {}).get("prompt_caps") or []
    row = next((r for r in caps if r["field"] == "prompt"), None)
    check("h3: ok receipt shows cap 7,000, status VERIFIED",
          row and row["cap"] == 7000 and row["status"] == "VERIFIED"
          and row["chars"] == 7000, str(caps))

    env, _, _, _ = disp("h3-short", "minimax-h3/text-to-video",
                        {"prompt": "p" * 200},
                        lock=ML.DEFAULT_VIDEO_MODEL)
    check("h3: a 200-char prompt is NOT padded to the 67 house floor 5000",
          env["outcome"] == "ok", str(env))


# ---- 2. Kling 2.5 Turbo: prompt and negative_prompt 2,500 each -------------
def test_kling25_caps():
    refused("k25-over", "kling/v2-5-turbo-image-to-video-pro",
            {"prompt": "x" * 2501}, 2500, "VERIFIED")
    refused("k25-neg", "kling/v2-5-turbo-image-to-video-pro",
            {"prompt": "x" * 100, "negative_prompt": "n" * 2501},
            2500, "VERIFIED")
    # at the cap the cap gate lets it through (F14 then owns this off-menu id)
    env, fake, _, _ = disp("k25-at", "kling/v2-5-turbo-image-to-video-pro",
                           {"prompt": "x" * 2500,
                            "negative_prompt": "n" * 2500})
    check("k25: 2,500/2,500 passes the cap gate",
          env["reason_code"] != "PROMPT_OVER_CAP", str(env))


# ---- 3. Avatar: 2,501 refused before the picture gate can mask it ----------
def test_avatar_cap():
    refused("avatar-over", "kling/ai-avatar-standard",
            {"prompt": "sings one line, steady camera" + "x" * 2501},
            2500, "UNVERIFIED")
    check("avatar: cap refused is PROMPT_OVER_CAP, never the picture gate",
          PL.video_caps("kling/ai-avatar-standard")["prompt"] == 2500
          and PL.video_caps("kling/ai-avatar-standard")["status"] == "UNVERIFIED")


# ---- 4. Kling 3.0 Omni 3,072 and Hailuo 2,000 ------------------------------
def test_kling30_and_hailuo_caps():
    refused("k30-over", "kling-3.0-omni/image-to-video",
            {"prompt": "x" * 3073}, 3072, "VERIFIED")
    refused("hailuo-over", "hailuo/02-text-to-video-standard",
            {"prompt": "x" * 2001}, 2000, "VERIFIED")
    check("h3: Hailuo cap did NOT leak onto H3 (7,000, not 2,000)",
          PL.video_caps("minimax-h3/text-to-video")["prompt"] == 7000)


# ---- 5. The table itself ---------------------------------------------------
def test_table():
    check("k26: kling-2.6 i2v override at 2,500",
          PL.video_caps("kling-2.6/image-to-video")["prompt"] == 2500)
    neg = PL.video_caps("kling/v2-5-turbo-text-to-video-pro")["negative_prompt"]
    check("k25: negative_prompt cap 2,500 on the T2V member too", neg == 2500)
    check("hailuo: no negative field invented",
          PL.video_caps("hailuo/02-image-to-video-pro")["negative_prompt"] is None)


TESTS = [test_h3_cap, test_kling25_caps, test_avatar_cap,
         test_kling30_and_hailuo_caps, test_table]


def main():
    for t in TESTS:
        try:
            t()
        except Exception as e:                              # noqa: BLE001
            check("%s raised" % t.__name__, False,
                  "%s: %s" % (type(e).__name__, e))
    print("\n%d checks failed" % len(FAILS))
    if FAILS:
        for f in FAILS:
            print("  FAILED: %s" % f)
        return 1
    print("all %d prompt-cap tests passed" % len(TESTS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

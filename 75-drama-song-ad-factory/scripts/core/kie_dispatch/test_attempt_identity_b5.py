#!/usr/bin/env python3
"""BATCH-5 redesign #6: the ledger mints the attempt identity, not the caller.

W02-U2 policy: identities are minted inside the allocation transaction and
callers must use the id it returns ("a1", "a1-retry", "a1-2" are all forbidden
string suffixes). The shipped song generate path hard-coded attempt_id="a1",
so a retry after a failed paid take was refused DUPLICATE_ATTEMPT and the
retry path was structurally dead.

Pinned here:
  * a ledger call with an EMPTY attempt_id mints one and reports it, with
    evidence.identity_minted_by_ledger = True;
  * after a failed paid attempt the next empty-id call mints a NEW identity
    (the retry exists) and the id is not a string suffix of the old one;
  * dispatch() carries the minted id back on its envelope and records the job
    under exactly that id;
  * control: a caller-supplied id is still used verbatim and reusing one is
    still refused DUPLICATE_ATTEMPT -- nothing was loosened.

stdlib only, zero paid calls: the Skill 74 runner is a stub.

Run from the skill root: python3 scripts/core/kie_dispatch/test_attempt_identity_b5.py
"""
import importlib
import os
import sqlite3
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
CORE = os.path.dirname(HERE)
if CORE not in sys.path:
    sys.path.insert(0, CORE)

D = importlib.import_module("kie_dispatch.kie_dispatch")
L = importlib.import_module("spend_ledger")

FAILS = []


def _forbid(*_a, **_k):
    raise AssertionError("real Skill 74 runner disabled in tests")


D.make_runner = _forbid


def check(name, got, want):
    if got == want:
        print("ok %s" % name)
    else:
        print("FAIL %s: got %r want %r" % (name, got, want))
        FAILS.append(name)


class Fake74:
    def __init__(self):
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        sub = argv[1] if len(argv) > 1 else ""
        return {
            "health": (0, {"adapter_mode": "active", "state": "success"}),
            "preflight": (0, {"state": "validated", "data": {"ok": True}}),
            "prompt-budget": (0, {"state": "success",
                                  "data": {"status": "OK", "exit_code": 0,
                                           "max": 20000}}),
            "submit": (0, {"state": "success",
                           "data": {"task_id": "task-1"}}),
        }.get(sub, (1, {}))


CARD = {"answers": {"video_style": "Lifelike 3D", "audio_style": "Soul Ballad",
                    "length": 60, "video_model": "MiniMax H3 768P"},
        "who": "b5 identity test", "at": "2026-10-08T09:00:00Z"}

REQ = {"model": "m",
       "input": {"prompt": "Photorealistic still frame, warm light." * 6},
       "card_receipt": CARD}


def test_ledger_mints():
    tmp = tempfile.mkdtemp(prefix="b5-attempt-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-b5", 10000)
    digest = L.digest_request({"k": 1})

    p1 = L.plan(db, "run-b5", "song/v1", "", digest, 100)
    check("1: an empty attempt_id is accepted", p1["outcome"], "ok")
    a1 = p1["attempt_id"]
    check("2: the ledger says it minted the identity",
          p1["evidence"]["identity_minted_by_ledger"], True)
    check("3: attempt_no 1 is derived, not claimed",
          p1["evidence"]["attempt_no"], 1)

    check("4: reserve takes the minted id",
          L.reserve(db, "run-b5", "song/v1", a1)["outcome"], "ok")
    check("5: mark_submitted takes the minted id",
          L.mark_submitted(db, "run-b5", "song/v1", a1,
                           "remote-1")["outcome"], "ok")
    check("6: the take really failed",
          L.mark_terminal(db, "run-b5", "song/v1", a1,
                          "failed")["outcome"], "ok")

    p2 = L.plan(db, "run-b5", "song/v1", "", digest, 100)
    a2 = p2.get("attempt_id") or ""
    check("7: the retry is not refused as a duplicate",
          p2["outcome"], "ok")
    check("8: the retry gets a NEW identity", a2 != a1, True)
    check("9: the new id is not a suffix/superstring of the old",
          a1 in a2 or a2 in a1, False)
    check("10: the retry is attempt 2", p2["evidence"]["attempt_no"], 2)


def test_dispatch_carries_it():
    tmp = tempfile.mkdtemp(prefix="b5-attempt-")
    db = os.path.join(tmp, "spend.db")
    L.init_run(db, "run-b5", 10000)
    env = D.dispatch(model="gpt-image-2-5-sunburst-text-to-image",
                     request=REQ, save_dir=os.path.join(tmp, "out"),
                     ledger_db=db, run_id="run-b5", logical_key="song/v1",
                     attempt_id="", estimated_cost=100, prompt="q" * 200,
                     adapter_path=os.path.abspath(__file__), runner=Fake74())
    aid = env.get("attempt_id") or ""
    check("11: dispatch returns the committed identity", bool(aid), True)
    rows = sqlite3.connect(db).execute(
        "SELECT attempt_id FROM jobs WHERE logical_key='song/v1'").fetchall()
    check("12: the job row is that identity", [r[0] for r in rows], [aid])

    # control: an explicit id is honoured verbatim, and reuse is still refused
    e3 = D.dispatch(model="gpt-image-2-5-sunburst-text-to-image",
                    request=REQ, save_dir=os.path.join(tmp, "out2"),
                    ledger_db=db, run_id="run-b5", logical_key="song/v2",
                    attempt_id="explicit-1", estimated_cost=100,
                    prompt="q" * 200,
                    adapter_path=os.path.abspath(__file__), runner=Fake74())
    check("13: an explicit id is used verbatim",
          e3.get("attempt_id"), "explicit-1")
    e4 = D.dispatch(model="gpt-image-2-5-sunburst-text-to-image",
                    request=REQ, save_dir=os.path.join(tmp, "out3"),
                    ledger_db=db, run_id="run-b5", logical_key="song/v2",
                    attempt_id="explicit-1", estimated_cost=100,
                    prompt="q" * 200,
                    adapter_path=os.path.abspath(__file__), runner=Fake74())
    check("14: reusing an id is still refused (policy untouched)",
          e4.get("reason_code"), "DUPLICATE_ATTEMPT")


def test_no_string_suffix_minter():
    """The disposition forbids a locally-minted attempt identity. #2414 shipped
    `_next_attempt_id` (a ledger read + MAX()+1 suffix); it must not exist."""
    SC = importlib.import_module("song_choices.song_choices")
    check("15: no _next_attempt_id minter survives in song_choices",
          hasattr(SC, "_next_attempt_id"), False)
    src = open(os.path.join(CORE, "song_choices", "song_choices.py"),
               encoding="utf-8").read()
    check("16: the generate path asks the ledger to mint",
          'attempt_id="",' in src, True)


def main():
    for fn in (test_ledger_mints, test_dispatch_carries_it,
               test_no_string_suffix_minter):
        try:
            fn()
        except Exception as e:                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            FAILS.append("%s raised %s: %s" % (fn.__name__, type(e).__name__, e))
    print()
    if FAILS:
        print("%d FAILED: %s" % (len(FAILS), ", ".join(FAILS)))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

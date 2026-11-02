#!/usr/bin/env python3
"""ST11A regression: no false sent=True on a studio script run.

Defect: with control/studio-order.json present and no --target, the script
gate marked the run sent with zero Studio publication calls -- chat/text
delivery alone counted as Studio-sent.

Pin, driven exactly like the E05 repro (factory._script_gate with a stubbed
studio seam): (a) when the studio publish is refused, sent stays False and
nothing is recorded as delivered; (b) when the publish succeeds, sent is
True and control/studio-script-receipt.json exists.

Run: python3 tests/test_script_gate_false_sent.py
"""
import json
import os
import sys
from types import SimpleNamespace

CORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts", "core")
IP = os.path.join(CORE, "intake_preflight")
SA_DIR = os.path.join(CORE, "script_approval")
for p in (IP, SA_DIR, CORE):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_stage_purpose as T  # noqa: E402
from script_approval import script_approval as SA  # noqa: E402
import factory as F  # noqa: E402


def drive(publish_result):
    """A studio-ordered run through the real gate with a counting studio stub."""
    pubs = []

    def fake_publish(*a, **k):
        pubs.append((a, k))
        return publish_result

    F._studio_publish = fake_publish
    run = T.run_dir(T.story())
    with open(os.path.join(run, "control", "studio-order.json"), "w", encoding="utf-8") as f:
        json.dump({"order_id": "ord-1"}, f)
    r = F._script_gate(run, SimpleNamespace(target="", reply=None), None)
    return r, SA.record_for(run), pubs, run


def test_refused_studio_publish_keeps_sent_false_and_delivers_nothing():
    r, rec, pubs, run = drive(None)
    assert r["outcome"] == "error", r
    assert len(pubs) == 1, pubs                       # the gate attempted the Studio publish
    assert rec is not None and rec.get("sent") is False, rec
    assert r.get("delivered", []) == [] and r.get("messages", []) == [], r
    assert not os.path.exists(os.path.join(run, "control", "studio-script-receipt.json"))


def test_successful_studio_publish_marks_sent_and_writes_receipt():
    r, rec, pubs, run = drive({"receipt": "r1", "approval": "script"})
    assert r["outcome"] == "waiting", r
    assert len(pubs) == 1, pubs
    assert rec is not None and rec.get("sent") is True, rec
    assert len(r["delivered"]) == 1 and "THE SONG LYRICS" in r["delivered"][0], r
    receipt = os.path.join(run, "control", "studio-script-receipt.json")
    assert os.path.exists(receipt), receipt
    assert json.load(open(receipt, encoding="utf-8")).get("approval") == "script"


if __name__ == "__main__":
    test_refused_studio_publish_keeps_sent_false_and_delivers_nothing()
    print("PASS test_refused_studio_publish_keeps_sent_false_and_delivers_nothing")
    test_successful_studio_publish_marks_sent_and_writes_receipt()
    print("PASS test_successful_studio_publish_marks_sent_and_writes_receipt")
    print("ALL PASS")

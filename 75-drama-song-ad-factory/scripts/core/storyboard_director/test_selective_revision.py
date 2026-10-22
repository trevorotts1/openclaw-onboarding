#!/usr/bin/env python3
"""S75-W06-U2: storyboard presentation + selective revisions.

Proves (Skill 75 section 5.1 item 8):
  * every shot card carries line, action, emotional purpose, timing and
    character, shots presented in song order with their stills;
  * large plans present NUMBERED contact sheets and NUMBERED card pages
    (ordered part numbers), every shot in order, nothing dropped;
  * approve-all and named-shot revision round trips work in-chat (through
    factory.py storyboard --reply, the real reply path);
  * selective revision invalidates ONLY the affected shots and their
    descendants — unaffected shots keep their approval records;
  * the shared artifact schema (contracts/artifact-schema.json) records for
    the storyboard artifacts validate structurally, with scoped stale flags.
    Named contract consumers of that shared schema: S75-W05 (story_coverage
    measurement records) and S75-W03 (channel_send / intake_card typed
    envelope + delivery outbox).

Run: python3 scripts/core/storyboard_director/test_selective_revision.py
(stdlib, no spend)
"""
import json
import os
import re
import sys
import tempfile

CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if CORE not in sys.path:
    sys.path.insert(0, CORE)

import storyboard_director.approval_package as AP      # noqa: E402
import storyboard_director.approval_runner as AR       # noqa: E402
import state_store as SS                              # noqa: E402
from batch_mode import batch as BATCH                 # noqa: E402

sys.path.insert(0, os.path.join(CORE, "intake_preflight"))
import factory as FACTORY                             # noqa: E402

FAILS = []


def check(name, cond, detail=""):
    print("%s: %s%s" % ("ok" if cond else "FAIL", name, "" if cond else " (%s)" % (detail,)))
    if not cond:
        FAILS.append(name)


def shot(i, chars=("mia",), continuity=None):
    return {"shot_id": "s%d" % i, "song_start": (i - 1) * 8.0,
            "song_end": (i - 1) * 8.0 + 8.0,
            "lyric_line_ids": ["l%d" % i], "story_stage": "frozen",
            "visual_objective": "show beat %d" % i,
            "character_ids": list(chars), "wardrobe_ids": ["w1"],
            "location_id": "kitchen", "product_visibility": "none",
            "camera_direction": "close-up %d" % (i % 4),
            "reference_assets": [], "image_model_capability_request": {},
            "video_model_capability_request": {},
            "continuity_constraints": list(continuity or []),
            "negative_constraints": [], "cost_estimate": 10,
            "qc_requirements": ["speaker-visibility"], "status": "planned"}


def contract(i, change_from_prior=""):
    return {"lyric_text": "line %d" % i,
            "viewer_understanding": "she is stuck %d" % i,
            "character_action": "sitting at table %d" % i,
            "visible_emotion": "stuck",
            "change_from_prior": change_from_prior}


def make_run(n=4, dep=True, choice="yes"):
    """n shots; when dep, s3 declares change_from_prior (edge s3 -> s2) and
    nothing else couples the shots."""
    run = os.path.join(tempfile.mkdtemp(prefix="sbsel-"), "run1")
    sb = os.path.join(run, "storyboard")
    os.makedirs(sb)
    os.makedirs(os.path.join(run, "control"))
    shots, contracts, stills = [], {}, {}
    for i in range(1, n + 1):
        shots.append(shot(i))
        contracts["s%d" % i] = contract(
            i, change_from_prior="she shifts her weight" if (dep and i == 3) else "")
        stills["s%d" % i] = os.path.join(sb, "s%d.png" % i)
        open(stills["s%d" % i], "wb").write(b"png-%d" % i)
    json.dump({"shots": shots}, open(os.path.join(sb, "shot-list.json"), "w"))
    json.dump(contracts, open(os.path.join(sb, "contracts.json"), "w"))
    json.dump(stills, open(os.path.join(sb, "stills.json"), "w"))
    if choice:
        json.dump({"storyboard_approval": choice},
                  open(os.path.join(run, "control", "card-receipt.json"), "w"))
    with SS.Store(os.path.join(run, "control", "state.sqlite3")) as st:
        st.init_run("run1", [s for s, _ in BATCH.STAGES])
    return run


class World:
    def __init__(self):
        self.events = []

    def send(self, message, images):
        self.events.append(("message", message))
        for n, img in images:
            self.events.append(("image", n, img))


def test_per_shot_fields_in_order():
    run = make_run(4)
    shots = json.load(open(os.path.join(run, "storyboard", "shot-list.json")))["shots"]
    contracts = json.load(open(os.path.join(run, "storyboard", "contracts.json")))
    stills = json.load(open(os.path.join(run, "storyboard", "stills.json")))
    pkg = AP.build(shots, contracts, stills)
    check("shots presented in song order",
          [e["shot_id"] for e in pkg["items"]] == ["s1", "s2", "s3", "s4"], pkg["items"])
    for e in pkg["items"]:
        for key in ("line", "action", "emotional_purpose", "timing", "character"):
            check("%s carries %s" % (e["shot_id"], key), bool(e.get(key)), e)
        text = AP.card_text(e)
        for label in ("Line:", "Emotional purpose:", "Action:", "Character:",
                      "Timing:"):
            check("%s card shows %s" % (e["shot_id"], label), label in text, text)
        check("%s card shows its still" % e["shot_id"], e["still"] in text, text)
    check("characters come from the plan's character_ids",
          pkg["items"][0]["character"] == "mia", pkg["items"][0])


def test_numbered_contact_sheets_and_pages_for_large_plans():
    run = make_run(12, dep=False)
    shots = json.load(open(os.path.join(run, "storyboard", "shot-list.json")))["shots"]
    contracts = json.load(open(os.path.join(run, "storyboard", "contracts.json")))
    stills = json.load(open(os.path.join(run, "storyboard", "stills.json")))
    pkg = AP.build(shots, contracts, stills)
    check("12-shot plan is large", pkg["large"], pkg["large"])
    sheets = pkg["sheets"]
    check("contact sheets numbered k/m",
          all(s["n"] == i and s["of"] == len(sheets) for i, s in enumerate(sheets, 1))
          and len(sheets) >= 2, sheets)
    flat = [img for s in sheets for img in s["images"]]
    check("sheets carry every still, in order",
          flat == [(e["n"], e["still"]) for e in pkg["items"]], flat)
    for s in sheets:
        check("sheet %d caption names its shot range" % s["n"],
              s["caption"].startswith("Contact sheet %d/%d - shots %d-%d"
                                      % (s["n"], s["of"], s["first"], s["last"])),
              s["caption"])
    pages = pkg["pages"]
    check("card pages numbered k/m with ordered part numbers",
          all(p["n"] == i and p["of"] == len(pages) for i, p in enumerate(pages, 1))
          and len(pages) >= 2, pages)
    seen = []
    for p in pages:
        check("page %d header names its shot range" % p["n"],
              p["text"].startswith("Storyboard cards %d/%d (shots %d-%d)"
                                   % (p["n"], p["of"], p["first"], p["last"])),
              p["text"][:80])
        seen += [e["shot_id"] for e in pkg["items"]
                 if p["first"] <= e["n"] <= p["last"]]
    check("pages cover every shot in order", seen == [e["shot_id"] for e in pkg["items"]], seen)
    check("only the last page carries the reply footer",
          AP.FOOTER in pages[-1]["text"] and all(AP.FOOTER not in p["text"] for p in pages[:-1]))
    check("every page inside the channel cap",
          all(len(p["text"]) <= AP.PAGE_LIMIT + 200 for p in pages),
          [len(p["text"]) for p in pages])
    # small plans stay the plain one-message presentation
    small = AP.build(shots[:3], contracts, stills)
    check("small plan is not paginated", not small["large"] and len(small["sheets"]) == 1
          and len(small["pages"]) == 1, (small["large"], len(small["sheets"])))


def test_selective_revision_scoped_invalidation():
    run = make_run(4, dep=True)
    w = World()
    AR.run(run, w.send)                       # present
    r = AR.run(run, w.send, reply="approve all")   # approve-all wording, not just GO
    check("approve-all wording approves", r["action"] == "approved" and AR.gate_open(run), r)
    st = json.load(open(os.path.join(run, "storyboard", "approval.json")))
    check("per-shot approvals recorded",
          all(v["status"] == "approved" for v in st["shots"].values()), st["shots"])
    # named revision after approval: only s2 + its descendant s3 lose approval
    def make_still(sid, card):
        p = os.path.join(run, "storyboard", sid + ".v2.png")
        open(p, "wb").write(b"png2-%s" % sid.encode())
        return p
    n = len(w.events)
    r = AR.run(run, w.send, reply="shot 2: change standing at the sink",
               make_still=make_still)
    sent = w.events[n:]
    check("named-shot revision re-sends that shot only",
          r["action"] == "revised" and r["shot_ids"] == ["s2"]
          and [e[0] for e in sent] == ["message", "image"] and sent[1][1] == 2,
          (r, sent))
    check("revision message carries the new card",
          "standing at the sink" in sent[0][1], sent[0][1])
    st = json.load(open(os.path.join(run, "storyboard", "approval.json")))
    check("revised shot + descendant invalidated only",
          st["shots"]["s2"]["status"] == "invalidated"
          and st["shots"]["s3"]["status"] == "invalidated"
          and st["shots"]["s1"]["status"] == "approved"
          and st["shots"]["s4"]["status"] == "approved",
          {k: v["status"] for k, v in st["shots"].items()})
    inv = st["invalidations"][-1]
    check("invalidation record scopes shots + descendants + kept",
          inv["shots"] == ["s2"] and inv["descendants"] == ["s3"]
          and inv["kept"] == ["s1", "s4"], inv)
    check("gate closed while affected shots are unapproved", not AR.gate_open(run))
    # re-approve: everything current again, gate open
    r = AR.run(run, w.send, reply="looks good")
    check("ordinary wording re-approves", r["action"] == "approved" and AR.gate_open(run), r)
    q = json.load(open(os.path.join(run, "control", "continuation-queue.json")))
    check("continuation enqueued once (replay-safe)", len(q) == 1
          and q[0]["event"] == "storyboard-approved" and q[0]["stage"] == "video-generation", q)
    # replay: acknowledge, no duplicate work
    r = AR.run(run, w.send, reply="approve all")
    check("replayed approval acknowledges without work",
          r["action"] == "approved" and len(w.events) == n + 2
          and len(json.load(open(os.path.join(run, "control",
                                              "continuation-queue.json")))) == 1, r)


def test_revision_without_dependencies_touches_one_shot():
    run = make_run(4, dep=False)
    w = World()
    AR.run(run, w.send)
    AR.run(run, w.send, reply="GO")
    def make_still(sid, card):
        p = os.path.join(run, "storyboard", sid + ".v2.png")
        open(p, "wb").write(b"png2")
        return p
    r = AR.run(run, w.send, reply="shot s2: change standing at the sink",
               make_still=make_still)
    check("revision by shot id works", r["action"] == "revised" and r["shot_ids"] == ["s2"], r)
    st = json.load(open(os.path.join(run, "storyboard", "approval.json")))
    check("no declared dependency: exactly one shot invalidated",
          st["shots"]["s2"]["status"] == "invalidated"
          and all(st["shots"][s]["status"] == "approved" for s in ("s1", "s3", "s4")),
          {k: v["status"] for k, v in st["shots"].items()})
    check("kept listed", r["kept"] == ["s1", "s3", "s4"], r)


def test_multi_shot_revision():
    run = make_run(4, dep=False)
    w = World()
    AR.run(run, w.send)
    def make_still(sid, card):
        p = os.path.join(run, "storyboard", sid + ".v2.png")
        open(p, "wb").write(b"png2")
        return p
    r = AR.run(run, w.send, reply="shots 2 and 4: change standing at the sink",
               make_still=make_still)
    check("two named shots revised in one reply",
          r["action"] == "revised" and r["shot_ids"] == ["s2", "s4"]
          and r["kept"] == ["s1", "s3"], r)
    n_ord = [e[1] for e in w.events if e[0] == "image"]
    check("both shots re-sent with their ordinals", n_ord[-2:] == [2, 4], w.events)


def test_in_chat_round_trip_via_factory():
    """The real conversation path: factory.py storyboard --reply ..."""
    run = make_run(4, dep=True)

    class A:
        pass

    def cmd(reply=None):
        a = A()
        a.run_dir, a.target, a.reply = run, "", reply
        return FACTORY.cmd_storyboard(a)
    env = cmd()
    check("in-chat present hands the cards back (no target)",
          env["outcome"] == "waiting" and env["data"]["messages"], env)
    env = cmd("shot 2: change standing at the sink")
    check("in-chat revision asks for the redone still",
          env["data"]["action"] == "regenerate_still"
          and env["data"]["shot_id"] == "s2", env["data"])
    open(os.path.join(run, "storyboard", "redo", "s2.png"), "wb").write(b"new-png")
    env = cmd()
    check("in-chat revision completes on the next call",
          env["data"]["action"] == "revised" and env["data"]["shot_ids"] == ["s2"], env["data"])
    check("in-chat invalidation scoped",
          env["data"]["invalidated"] == ["s2", "s3"]
          and env["data"]["kept"] == ["s1", "s4"], env["data"])
    env = cmd("GO")
    check("in-chat GO approves and says the pipeline continues",
          env["outcome"] == "ok" and env["reason_code"] == "approved"
          and env["data"]["continuation"]["stage"] == "video-generation", env)


def test_artifact_schema_contract():
    """Shared artifact schema conformance; named consumers S75-W05 + S75-W03."""
    schema_path = os.path.join(CORE, "contracts", "artifact-schema.json")
    schema = json.load(open(schema_path))
    run = make_run(3, dep=False)
    shots = json.load(open(os.path.join(run, "storyboard", "shot-list.json")))["shots"]
    contracts = json.load(open(os.path.join(run, "storyboard", "contracts.json")))
    stills = json.load(open(os.path.join(run, "storyboard", "stills.json")))
    recs = AP.artifact_records("run1", shots, contracts, stills, stale=["s2"])
    props, required = schema["properties"], schema["required"]
    for rec in recs:
        for key in required:
            check("%s has %s" % (rec["artifact_id"], key), key in rec, rec)
        for key, val in rec.items():
            check("%s.%s is in the shared schema" % (rec["artifact_id"], key),
                  key in props, (key, sorted(props)))
        check("%s kind in schema enum" % rec["artifact_id"],
              rec["kind"] in props["kind"]["enum"], rec["kind"])
        check("%s stage in schema enum" % rec["artifact_id"],
              rec["stage"] in props["stage"]["enum"], rec["stage"])
        check("%s sha256 well formed" % rec["artifact_id"],
              re.fullmatch(props["sha256"]["pattern"], rec["sha256"]) is not None,
              rec["sha256"])
        check("%s artifact_id well formed" % rec["artifact_id"],
              re.fullmatch(props["artifact_id"]["pattern"], rec["artifact_id"]) is not None,
              rec["artifact_id"])
    still_recs = [r for r in recs if r["kind"] == "image"]
    check("one image record per still", len(still_recs) == 3, still_recs)
    check("stale flag scoped to the affected shot",
          {r["artifact_id"]: r["stale"] for r in still_recs}
          == {"storyboard.still.s1": False, "storyboard.still.s2": True,
              "storyboard.still.s3": False},
          {r["artifact_id"]: r["stale"] for r in still_recs})
    # contract-surface guard: the consumers read these names
    doc = open(os.path.join(os.path.dirname(__file__), "approval_package.py")).read()
    check("shared-schema consumers named in the module",
          "S75-W05" in doc and "S75-W03" in doc
          and "artifact-schema.json" in doc, "consumer names")


if __name__ == "__main__":
    test_per_shot_fields_in_order()
    test_numbered_contact_sheets_and_pages_for_large_plans()
    test_selective_revision_scoped_invalidation()
    test_revision_without_dependencies_touches_one_shot()
    test_multi_shot_revision()
    test_in_chat_round_trip_via_factory()
    test_artifact_schema_contract()
    print("FAIL (%d): %s" % (len(FAILS), ", ".join(FAILS)) if FAILS else "ALL PASS")
    sys.exit(1 if FAILS else 0)

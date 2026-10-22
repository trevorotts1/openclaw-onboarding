#!/usr/bin/env python3
"""W03-U1: typed artifact envelope + durable delivery outbox.

Checks, on the contract from Skill_75_Universal_Repair_Spec_v1.1 sections
5.3/5.4 (findings D06/D07):

  (a) returning JSON / writing a local file establishes PREPARED, never sent;
  (b) each text chunk and attachment has its own deterministic identity and
      receipt; a crash resends only the missing pieces;
  (c) long lyrics/scripts split at semantic boundaries with ordered part
      numbers; channel limits observed with numbered contact sheets and
      paginated cards;
  (d) uncertain deliveries resolve through the channel's idempotency/readback
      -- never a false exactly-once claim;
  (e) repair re-sends the same bytes: no paid media is spent;
  (f) origin migration handles recognized legacy schemas idempotently and
      NEVER guesses (no global Telegram target);
  (g) no-target and no-receipt cases stay prepared/queued/uncertain/
      action-required until the channel proves otherwise.

Run: python3 core/choice_card/intake_card/test_delivery_outbox_w03.py
"""
import json
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(HERE)))
from choice_card.intake_card import delivery_outbox as DO  # noqa: E402
from choice_card.intake_card import intake_card as IC  # noqa: E402

ORIGIN = {"channel": "telegram", "account_id": "bot-1", "conversation_id": "777",
          "thread_id": "", "tenant_id": "t-1"}


def _run():
    return tempfile.mkdtemp()


def _envelope(text="hello", attachments=(), revision=1):
    return DO.build_envelope("run-1", "t-1", "art-1", "script", revision,
                             ORIGIN, text=text, attachments=attachments)


def test_states_are_the_contract_vocabulary():
    for s in ("prepared", "queued", "sending", "sent", "retryable_failure",
              "action_required", "uncertain"):
        assert s in DO.DELIVERY_STATES, s


def test_returned_json_or_written_file_is_prepared_never_sent():
    env = _envelope()
    assert env["delivery"]["state"] == "prepared"           # built -> prepared
    run = _run()
    path = os.path.join(run, "envelope.json")
    DO._write_json(path, env)
    back = json.load(open(path))
    assert back["delivery"]["state"] == "prepared"          # written -> still prepared
    assert back["delivery"]["message_ids"] == []
    assert env["sha256"] and env["delivery"]["idempotency_key"]


def test_deterministic_piece_identity_per_chunk_and_attachment():
    run = _run()
    env = _envelope(text="part body", attachments=[
        {"path": os.path.join(HERE, "ai_models.json"), "mime_type": "application/json"}])
    out = DO.Outbox(run)
    first = out.enqueue(env)
    second = DO.Outbox(run).enqueue(env)                    # crash + retry
    assert [p["piece_id"] for p in first] == [p["piece_id"] for p in second]
    ids = [p["piece_id"] for p in first]
    assert len(ids) == len(set(ids)) == 2                   # text chunk + attachment
    assert all(p["idempotency_key"] == p["piece_id"] for p in first)
    assert all(p["payload_sha256"] for p in first)


def test_semantic_split_ordered_part_numbers():
    lyrics = "\n\n".join("verse %d\n%s" % (i, "la " * 40) for i in range(4))
    parts = DO.split_semantic(lyrics, 200)
    assert len(parts) > 1, len(parts)
    assert [p["part_no"] for p in parts] == list(range(1, len(parts) + 1))
    assert all(p["part_count"] == len(parts) for p in parts)
    assert all(len(p["text"]) <= 200 for p in parts)        # channel limit observed
    joined = "\n\n".join(p["text"] for p in parts)
    assert joined == lyrics                                 # nothing lost or reordered
    # a paragraph is never split when it fits: semantic boundary first
    para = DO.split_semantic("one two three", 200)
    assert len(para) == 1 and para[0]["text"] == "one two three"


def test_long_text_respects_the_real_channel_limit():
    text = "\n\n".join("line %d %s" % (i, "x" * 50) for i in range(300))
    parts = DO.split_semantic(text, DO.channel_limit("telegram", "text_chars"))
    assert all(len(p["text"]) <= 4096 for p in parts), max(len(p["text"]) for p in parts)


def test_numbered_contact_sheets_and_paginated_cards():
    shots = ["s%d.png" % i for i in range(24)]
    sheets = DO.contact_sheets(shots, 10)
    assert [s["label"] for s in sheets] == \
        ["Contact sheet 1/3", "Contact sheet 2/3", "Contact sheet 3/3"], sheets
    flat = [i for s in sheets for i in s["items"]]
    assert flat == shots                                    # order preserved
    pages = DO.paginate(list(range(12)), 5)
    assert [p["label"] for p in pages] == ["Page 1/3", "Page 2/3", "Page 3/3"], pages
    assert [i for p in pages for i in p["items"]] == list(range(12))


def test_partial_crash_resends_only_missing_pieces():
    run = _run()
    env = _envelope(text="\n\n".join("v%d %s" % (i, "x" * 1500) for i in range(3)))
    out = DO.Outbox(run)
    pieces = out.enqueue(env)
    assert len(pieces) == 3, [p["payload"]["part_no"] for p in pieces]
    ids = [p["piece_id"] for p in pieces]
    # crash story: piece 1 acknowledged, piece 2 lost mid-send ("sending"),
    # piece 3 dispatched without a receipt ("uncertain")
    out.mark(ids[0], DO.SENT, receipt={"message_id": "m-1"})
    out.mark(ids[1], DO.SENDING)
    out.mark(ids[2], DO.UNCERTAIN)
    # restart: a fresh Outbox reads the durable ledger and resends ONLY missing
    seen = []

    def sender(p):
        seen.append((p["piece_id"], p["payload_sha256"]))
        return {"message_id": "m-new", "piece": p["piece_id"]}

    res = DO.Outbox(run).resume(sender)
    assert [s[0] for s in seen] == [ids[1], ids[2]], seen   # piece 1 NOT resent
    assert sorted(res["sent"]) == sorted([ids[1], ids[2]]), res
    assert DO.Outbox(run).get(ids[0])["receipt"] == {"message_id": "m-1"}
    # the resent payloads are byte-identical: no paid media is spent on repair
    orig = {p["piece_id"]: p["payload_sha256"] for p in pieces}
    assert all(orig[pid] == sha for pid, sha in seen), seen


def test_no_receipt_never_marked_sent():
    run = _run()
    out = DO.Outbox(run)
    (p,) = out.enqueue(_envelope())
    res = out.resume(lambda piece: None)                    # channel acked nothing
    assert res["uncertain"] == [p["piece_id"]] and not res["sent"], res
    assert out.get(p["piece_id"])["state"] == DO.UNCERTAIN
    assert out.get(p["piece_id"])["receipt"] is None
    try:
        out.mark(p["piece_id"], DO.SENT)                    # no receipt -> refused
    except DO.OutboxError:
        pass
    else:
        raise AssertionError("a piece was claimed sent without a channel receipt")


def test_uncertain_resolved_by_idempotency_readback_not_exactly_once_claims():
    run = _run()
    out = DO.Outbox(run)
    ids = [p["piece_id"] for p in out.enqueue(
        _envelope(text="\n\n".join("v%d %s" % (i, "x" * 1500) for i in range(3))))]
    out.resume(lambda piece: None)                          # all three uncertain
    # the channel readback proves one landed, proves one never landed, and
    # cannot prove the third -- each outcome stays distinct and honest
    r1 = out.resolve_uncertain(ids[0], lambda k: {"message_id": "m-found"})
    r2 = out.resolve_uncertain(ids[1], lambda k: DO.NOT_FOUND)
    r3 = out.resolve_uncertain(ids[2], lambda k: None)
    assert r1["state"] == DO.SENT and r1["receipt"] == {"message_id": "m-found"}
    assert r2["state"] == DO.RETRYABLE_FAILURE               # resend is safe
    assert r3["state"] == DO.UNCERTAIN                       # never falsely resolved


def test_no_target_case_stays_action_required_until_repaired():
    run = _run()
    out = DO.Outbox(run)
    env = DO.build_envelope("run-1", "t-1", "art-2", "lyrics", 1,
                            {"channel": "telegram", "conversation_id": ""},
                            text="verse")
    (p,) = out.enqueue(env)
    out.mark(p["piece_id"], DO.ACTION_REQUIRED,
             error="no destination recorded for this run")
    res = out.resume(lambda piece: {"message_id": "m"})
    assert res["sent"] == [] and p["piece_id"] in res["skipped"], res
    rec = DO.save_origin(run, dict(ORIGIN, conversation_id="888"))
    moved = out.redestinate(rec)
    assert [m["piece_id"] for m in moved] != [p["piece_id"]]  # identity follows dest
    assert moved[0]["payload_sha256"] == p["payload_sha256"]  # same bytes
    res2 = DO.Outbox(run).resume(lambda piece: {"message_id": "m-2"})
    assert len(res2["sent"]) == 1, res2


def test_origin_migration_recognized_schema_idempotent():
    run = _run()
    os.makedirs(os.path.join(run, "song-choices"))
    with open(os.path.join(run, "song-choices", "state.json"), "w", encoding="utf-8") as f:
        json.dump({"required": True, "offered": {},
                   "target": "777",
                   "provenance": {"channel": "telegram", "who": "client"}}, f)
    m1 = DO.migrate_legacy_destinations(run)
    assert m1["origin"]["channel"] == "telegram" and \
        m1["origin"]["conversation_id"] == "777", m1
    assert m1["migrated"] and not m1["unresolved"], m1
    m2 = DO.migrate_legacy_destinations(run)                # idempotent
    assert m2["origin"] == m1["origin"] and m2["migrated"] == [], m2
    assert DO.load_origin(run) == m1["origin"]


def test_origin_migration_never_guesses_a_telegram_target():
    """A bare chat id with no channel marker is NOT migrated: no guessed
    global Telegram target, ever."""
    run = _run()
    os.makedirs(os.path.join(run, "song-choices"))
    with open(os.path.join(run, "song-choices", "state.json"), "w", encoding="utf-8") as f:
        json.dump({"required": True, "offered": {}, "target": "888"}, f)
    m = DO.migrate_legacy_destinations(run)
    assert m["origin"] is None, m
    assert DO.load_origin(run) is None
    assert m["unresolved"] and "no channel" in m["unresolved"][0]["reason"], m
    flat = json.dumps(m)
    assert "telegram" not in flat.lower(), flat              # NOTHING assumed telegram


def test_origin_save_is_once_only_and_conflict_is_loud():
    run = _run()
    DO.save_origin(run, ORIGIN)
    DO.save_origin(run, ORIGIN)                             # idempotent same record
    try:
        DO.save_origin(run, dict(ORIGIN, conversation_id = "other"))
    except DO.OriginConflict:
        pass
    else:
        raise AssertionError("a conflicting origin record was accepted")
    assert DO.load_origin(run)["conversation_id"] == "777"  # original preserved


def test_channel_command_builder_resolves_channel_as_data():
    argv = IC.channel_send_argv("app", "conv-1", "hi")
    assert argv[:6] == ["openclaw", "message", "send", "--channel", "app", "--target"]
    t = IC.channel_send_argv("telegram", "777", "hi", media=["/tmp/a.png"],
                             account="bot-1", thread_id="t-9")
    assert t[4] == "telegram" and "--account" in t and "--thread-id" in t
    try:
        IC.channel_send_argv("", "x", "hi")
    except ValueError:
        pass
    else:
        raise AssertionError("the builder guessed a channel when none was resolved")


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                fails += 1
                print("FAIL", name, repr(e))
    print("ALL PASS" if not fails else "%d FAILED" % fails)
    sys.exit(1 if fails else 0)

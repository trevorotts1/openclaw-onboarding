#!/usr/bin/env python3
"""test_gate_engine_assembly_status.py -- the U9/U13 status-passthrough + order-
confirmation contract on gate_engine.py (the ENGINE side of the CC assembly cockpit).

Hermetic: a REAL local ledger (anthology_state.py, --state-dir temp; MIRROR-ONLY, no
Airtable, no network) is seeded through the actual gate walk, then gate_engine.py is
driven as a subprocess exactly the way the session-gated board route shells it. No
model call is ever made (the finale WRITE is the S9 runner's job, decoupled from the
decide call; confirm_order only PERSISTS the order + sets request.confirm_order, which
this test observes directly). Proves:

  1. cmd_status for an ASSEMBLY subject additionally emits assembly_state + readiness +
     ordering under the EXACT keys the CC cockpit parser reads (assembly-cockpit-
     logic.ts parseAssemblyStatus/parseReadiness/parseOrdering).
  2. cmd_status for a PARTICIPANT subject is UNCHANGED (no assembly keys leak).
  3. confirm_order PERSISTS the producer's adjusted order through the sole writer AND
     sets the S9 runner's request.confirm_order (so U9's Grand Finale write fires next
     runner pass); adjust_order persists WITHOUT the finale flag.
  4. confirm_order preserves the both-door rule + exit-code map (0 recorded / 2 guard
     refusal / 3 gate-not-open): non-producer, token door, participant subject, a
     non-permutation order, and a wrong assembly-state window each refuse as contracted.

Run: python3 -m pytest 59-anthology-engine/tests/test_gate_engine_assembly_status.py -q
"""
import json
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE = SCRIPTS / "anthology_state.py"
GATE = SCRIPTS / "gate_engine.py"
PY = sys.executable or "python3"

AID = "ANTHtest0001"
PID = "prodTEST"
P1 = "cT1::" + AID
P2 = "cT2::" + AID
TITLES = {P1: "First Light", P2: "Last Call"}
SHAS = {P1: "shaT1v1", P2: "shaT2v1"}
NAMES = {P1: ("Ada", "Vaughn"), P2: ("Ben", "Reyes")}


# --------------------------------------------------------------------------- #
# subprocess drivers
# --------------------------------------------------------------------------- #
def _run(argv):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except ValueError:
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def state(state_dir, *args):
    rc, parsed, err = _run([PY, str(STATE), args[0], "--state-dir", str(state_dir),
                            "--json", *args[1:]])
    assert rc == 0, "anthology_state %s failed rc=%d :: %s" % (args[0], rc, err)
    return parsed


def gate(state_dir, *args, expect_rc=None):
    rc, parsed, err = _run([PY, str(GATE), args[0], "--state-dir", str(state_dir),
                            "--json", *args[1:]])
    if expect_rc is not None:
        assert rc == expect_rc, ("gate_engine %s expected rc=%s got %s :: %s\n%s"
                                 % (args[0], expect_rc, rc, err, parsed))
    return rc, parsed


def _walk_to_approved(state_dir, pk, title, sha, first, last):
    """Walk a participant through the real gate machine to stage_cursor 'approved'
    with a FROZEN chapter artifact (the two conditions S9 readiness requires)."""
    contact = pk.split("::", 1)[0]
    state(state_dir, "upsert-participant", "--contact-id", contact,
          "--anthology-id", AID, "--first-name", first, "--last-name", last)
    for frm_to in ("s1_avatar", "s1_gate"):
        state(state_dir, "advance-stage", "--participant-key", pk, "--to", frm_to)
    state(state_dir, "record-approval", "--gate", "s1_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
    state(state_dir, "record-approval", "--gate", "s2_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
    state(state_dir, "record-approval", "--gate", "s3_selection",
          "--participant-key", pk, "--decision", "approve", "--title", title)
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
    state(state_dir, "record-approval", "--gate", "s4_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "record-approval", "--gate", "s4_participant",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "record-artifact", "--participant-key", pk, "--type", "chapter",
          "--sha256", sha, "--model-used", "glm-5.2")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s5_gate")
    state(state_dir, "record-approval", "--gate", "s5_participant",
          "--participant-key", pk, "--decision", "approve")
    for nxt in ("s8_deliver", "s9_wait_assembly", "approved"):
        state(state_dir, "advance-stage", "--participant-key", pk, "--to", nxt)


def _seed_ready(state_dir):
    """Seed a real ledger to the ARMED/ready_confirmed ordering window."""
    state(state_dir, "bootstrap")
    state(state_dir, "upsert-producer", "--producer-id", PID,
          "--producer-email", "owner@example.test", "--display-name", "Owner")
    state(state_dir, "upsert-anthology", "--anthology-id", AID,
          "--producer-id", PID, "--name", "The Test Collection", "--min-chapters", "2")
    for pk in (P1, P2):
        _walk_to_approved(state_dir, pk, TITLES[pk], SHAS[pk], *NAMES[pk])
    # fire the s9_ready trigger (own-producer + typed name) -> ready_confirmed
    state(state_dir, "record-approval", "--gate", "s9_ready", "--anthology-id", AID,
          "--producer-id", PID, "--confirm-name", "The Test Collection")


# --------------------------------------------------------------------------- #
# 1 + 2: cmd_status passthrough (assembly enriched; participant unchanged)
# --------------------------------------------------------------------------- #
def test_status_assembly_emits_state_readiness_and_actions(tmp_path):
    _seed_ready(tmp_path)
    rc, out = gate(tmp_path, "status", "--subject-key", AID, expect_rc=0)
    assert out["ok"] is True and out["kind"] == "anthology"
    # assembly_state surfaced (CC reads r.assembly_state)
    assert out["assembly_state"] == "ready_confirmed"
    # readiness summary under the keys parseReadiness consumes
    r = out["readiness"]
    assert r["frozen_chapter_count"] == 2 and r["active_members"] == 2
    assert r["ready"] is True and r["min_chapters"] == 2
    assert r["below_min_chapters"] is False and isinstance(r["blocking"], list)
    # in the ordering window the board order actions are advertised
    assert out["actions"] == ["adjust_order", "confirm_order"]
    assert out["doors"] == ["board"] and out["actor"] == "producer"
    # no order proposed yet -> ordering absent (honest 'pending')
    assert "ordering" not in out


def test_status_participant_subject_is_unchanged(tmp_path):
    _seed_ready(tmp_path)
    rc, out = gate(tmp_path, "status", "--subject-key", P1, expect_rc=0)
    assert out["ok"] is True and out["kind"] == "participant"
    # a participant subject NEVER carries the assembly passthrough keys
    for leaked in ("assembly_state", "readiness", "ordering"):
        assert leaked not in out, "participant status leaked %r" % leaked


# --------------------------------------------------------------------------- #
# 3: confirm_order persists the order AND flags the finale; adjust_order does not
# --------------------------------------------------------------------------- #
def test_confirm_order_persists_and_triggers_finale(tmp_path):
    _seed_ready(tmp_path)
    run_dir = tmp_path / "run"
    order = json.dumps([P1, P2])
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", AID, "--producer-id", PID, "--order", order,
                   "--opener", P1, "--closer", P2, "--run-dir", str(run_dir),
                   expect_rc=0)
    # recorded + persisted through the sole writer
    assert out["ok"] is True and out["committed"] is True
    assert out["decision"] == "confirm_order" and out["door"] == "dashboard"
    assert out["assembly_state"] == "adjusted" and out["order_len"] == 2
    # the finale flag is set for the S9 runner
    assert out["confirm_order"]["flagged"] is True
    req = json.loads((run_dir / "request.json").read_text(encoding="utf-8"))
    assert req["confirm_order"] is True
    assert req["order"] == [P1, P2] and req["opener"] == P1 and req["closer"] == P2
    assert req["producer_id"] == PID
    # the order is durably persisted in the ledger (chapter_order + assembly_state)
    anth = state(tmp_path, "get-anthology", "--anthology-id", AID)
    assert anth["assembly_state"] == "adjusted"
    assert json.loads(anth["chapter_order"]) == [P1, P2]
    # and cmd_status now surfaces the ordering view (ledger fallback: titles from the
    # locked titles, contributor from first+last, empty per-slot rationale)
    rc, st = gate(tmp_path, "status", "--subject-key", AID, "--run-dir", str(run_dir),
                  expect_rc=0)
    ordering = st["ordering"]
    assert ordering["order"] == [P1, P2]
    slots = ordering["slots"]
    assert [s["position"] for s in slots] == [1, 2]
    assert slots[0]["participant_key"] == P1
    assert slots[0]["chapter_title"] == "First Light"
    assert slots[0]["contributor_name"] == "Ada Vaughn"


def test_adjust_order_persists_without_finale_flag(tmp_path):
    _seed_ready(tmp_path)
    run_dir = tmp_path / "run_adjust"
    order = json.dumps([P2, P1])
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "adjust_order",
                   "--subject-key", AID, "--producer-id", PID, "--order", order,
                   "--run-dir", str(run_dir), expect_rc=0)
    assert out["committed"] is True and out["decision"] == "adjust_order"
    # adjust_order does NOT arm the finale: no confirm_order block, no request.json
    assert "confirm_order" not in out
    assert not (run_dir / "request.json").exists()
    anth = state(tmp_path, "get-anthology", "--anthology-id", AID)
    assert json.loads(anth["chapter_order"]) == [P2, P1]


# --------------------------------------------------------------------------- #
# 3b: a persisted cockpit view (order_proposal.json) is PREFERRED (carries rationale)
# --------------------------------------------------------------------------- #
def test_status_prefers_persisted_cockpit_view(tmp_path):
    _seed_ready(tmp_path)
    # arm an order first so we are in the window
    gate(tmp_path, "decide", "--door", "board", "--action", "adjust_order",
         "--subject-key", AID, "--producer-id", PID, "--order", json.dumps([P1, P2]),
         "--run-dir", str(tmp_path / "r"), expect_rc=0)
    run_dir = tmp_path / "cockpit"
    (run_dir / "working").mkdir(parents=True)
    view = {
        "order": [P1, P2],
        "slots": [
            {"position": 1, "participant_key": P1, "chapter_title": "First Light",
             "contributor_name": "Ada Vaughn", "word_count": 3000, "tone": "warm",
             "rationale": "a strong opener"},
            {"position": 2, "participant_key": P2, "chapter_title": "Last Call",
             "contributor_name": "Ben Reyes", "word_count": 2100, "tone": "wry",
             "rationale": "a resonant close"},
        ],
        "overall_rationale": "opener/closer with a wry middle",
    }
    (run_dir / "working" / "order_proposal.json").write_text(
        json.dumps(view), encoding="utf-8")
    rc, st = gate(tmp_path, "status", "--subject-key", AID, "--run-dir", str(run_dir),
                  expect_rc=0)
    ordering = st["ordering"]
    # the persisted view (with ae-01 rationale + word_count/tone) is used verbatim
    assert ordering["overall_rationale"] == "opener/closer with a wry middle"
    assert ordering["slots"][0]["rationale"] == "a strong opener"
    assert ordering["slots"][0]["word_count"] == 3000
    assert ordering["slots"][1]["tone"] == "wry"


# --------------------------------------------------------------------------- #
# 4: both-door rule + exit-code map (0/2/3) on confirm_order refusals
# --------------------------------------------------------------------------- #
def test_confirm_order_refuses_non_producer(tmp_path):
    _seed_ready(tmp_path)
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", AID, "--producer-id", "intruder",
                   "--order", json.dumps([P1, P2]), "--run-dir", str(tmp_path / "x"),
                   expect_rc=2)
    assert out["reason"] == "not_owning_producer" and out["committed"] is False


def test_confirm_order_refuses_token_door(tmp_path):
    _seed_ready(tmp_path)
    rc, out = gate(tmp_path, "decide", "--door", "token", "--action", "confirm_order",
                   "--subject-key", AID, "--producer-id", PID,
                   "--order", json.dumps([P1, P2]), expect_rc=2)
    assert out["reason"] == "door_not_allowed_for_gate"


def test_confirm_order_refuses_participant_subject(tmp_path):
    _seed_ready(tmp_path)
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", P1, "--producer-id", PID,
                   "--order", json.dumps([P1, P2]), expect_rc=2)
    assert out["reason"] == "not_an_assembly_subject"


def test_confirm_order_refuses_non_permutation(tmp_path):
    _seed_ready(tmp_path)
    # drop P2 -> not a permutation of the staged, approved, frozen set (writer exit 5)
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", AID, "--producer-id", PID,
                   "--order", json.dumps([P1]), "--run-dir", str(tmp_path / "x"),
                   expect_rc=2)
    assert out["reason"] == "order_not_a_permutation" and out["committed"] is False


def test_confirm_order_refuses_wrong_state_window(tmp_path):
    # a fresh, not-ready anthology (no arm) -> gate not open (exit 3)
    state(tmp_path, "bootstrap")
    state(tmp_path, "upsert-producer", "--producer-id", PID,
          "--producer-email", "o@example.test", "--display-name", "Owner")
    state(tmp_path, "upsert-anthology", "--anthology-id", "ANTHnr", "--producer-id",
          PID, "--name", "Not Ready", "--min-chapters", "2")
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", "ANTHnr", "--producer-id", PID,
                   "--order", json.dumps(["x::ANTHnr"]), expect_rc=3)
    assert out["reason"] == "gate_not_open" and out["assembly_state"] == "not_ready"


def test_confirm_order_opener_closer_consistency(tmp_path):
    _seed_ready(tmp_path)
    # opener that is not order[0] -> refuse (exit 2), nothing persisted
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "confirm_order",
                   "--subject-key", AID, "--producer-id", PID,
                   "--order", json.dumps([P1, P2]), "--opener", P2, expect_rc=2)
    assert out["reason"] == "opener_not_first"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))

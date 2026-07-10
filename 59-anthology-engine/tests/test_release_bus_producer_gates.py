#!/usr/bin/env python3
"""test_release_bus_producer_gates.py -- the chapter/rewrite/cover producer RELEASE
gates are now LIVE in gate_engine.py's release bus (promoted from wired-ahead).

Proves, both PURE and END-TO-END, that a committed BOARD-door producer approve at the
s5 (chapter), s6 (rewrite) and s7 (cover) producer gates fires the corresponding §3
release slug -- anthology-release-chapter / -rewrite / -cover -- exactly the way the
s1/s2/s4 avatar/tone/outline gates do today, and that hold / exclude never fire it.

  PURE: release_slug_for(GATE_BY_CURSOR[cursor], "approve", "board", committed=True)
        returns the slug; every non-approve / non-board / uncommitted decision -> None.

  END-TO-END (hermetic): a REAL local ledger (anthology_state.py, --state-dir temp;
  MIRROR-ONLY -- Airtable env stripped, no network) is walked through the actual gate
  machine to the producer-review cursor, then gate_engine.py is driven as a subprocess
  exactly the way the board route shells it. A board approve COMMITS through the sole
  writer and the decide payload carries release_tag.slug; the pipeline cursor is left
  UNCHANGED (these gates are RELEASE-ONLY -- they own no cursor edge); a board hold or
  exclude commits WITHOUT any release_tag. No model call, no live Convert and Flow, no
  credential value (the tag STAMP is fail-soft and simply reports its status; the proof
  is that the bus DECIDED to fire the correct slug). Python 3 stdlib only.

Run: python3 -m pytest 59-anthology-engine/tests/test_release_bus_producer_gates.py -q
 or: python3 59-anthology-engine/tests/test_release_bus_producer_gates.py
"""
import json
import os
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE = SCRIPTS / "anthology_state.py"
GATE = SCRIPTS / "gate_engine.py"
PY = sys.executable or "python3"

AID = "ANTHrelbus01"
PID = "prodREL"

# (producer-review cursor, gate id, §3 release slug)
GATES = (
    ("s5_chapter", "s5_producer", "anthology-release-chapter"),
    ("s6_rewrite", "s6_producer", "anthology-release-rewrite"),
    ("s7_cover",   "s7_producer", "anthology-release-cover"),
)


def _clean_env():
    """Strip every Airtable/base lever so the sole writer runs MIRROR-ONLY (no network)
    and force the state dir to be the flag-supplied one only."""
    env = dict(os.environ)
    for k in ("ANTHOLOGY_STATE_BASE_ID", "AIRTABLE_API_KEY", "AIRTABLE_TOKEN",
              "AIRTABLE_PAT", "ANTHOLOGY_STATE_AIRTABLE_KEY", "ANTHOLOGY_STATE_DIR"):
        env.pop(k, None)
    return env


def _run(argv):
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=90,
                          env=_clean_env())
    parsed = None
    out = (proc.stdout or "").strip()
    if out:
        try:
            parsed = json.loads(out)
        except ValueError:
            parsed = None
    return proc.returncode, parsed, (proc.stderr or "").strip()


def state(state_dir, *args, expect_ok=True):
    rc, parsed, err = _run([PY, str(STATE), args[0], "--state-dir", str(state_dir),
                            "--json", *args[1:]])
    if expect_ok:
        assert rc == 0, "anthology_state %s failed rc=%d :: %s" % (args[0], rc, err)
    return rc, parsed


def gate(state_dir, *args, expect_rc=None):
    rc, parsed, err = _run([PY, str(GATE), args[0], "--state-dir", str(state_dir),
                            "--json", *args[1:]])
    if expect_rc is not None:
        assert rc == expect_rc, ("gate_engine %s expected rc=%s got %s :: %s\n%s"
                                 % (args[0], expect_rc, rc, err, parsed))
    return rc, parsed


def _seed(state_dir):
    state(state_dir, "bootstrap")
    state(state_dir, "upsert-producer", "--producer-id", PID,
          "--producer-email", "owner@example.test", "--display-name", "Owner")
    state(state_dir, "upsert-anthology", "--anthology-id", AID,
          "--producer-id", PID, "--name", "The Release Bus Collection", "--min-chapters", "2")


def _walk_to(state_dir, contact, target):
    """Walk a FRESH participant `contact::AID` through the real gate machine to the
    producer-review cursor `target` (s5_chapter, s6_rewrite, or s7_cover). Returns the
    participant_key. Uses only the pre-existing (unchanged) gate edges."""
    pk = "%s::%s" % (contact, AID)
    state(state_dir, "upsert-participant", "--contact-id", contact,
          "--anthology-id", AID, "--first-name", "Coauthor")
    for nxt in ("s1_avatar", "s1_gate"):
        state(state_dir, "advance-stage", "--participant-key", pk, "--to", nxt)
    state(state_dir, "record-approval", "--gate", "s1_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
    state(state_dir, "record-approval", "--gate", "s2_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
    state(state_dir, "record-approval", "--gate", "s3_selection",
          "--participant-key", pk, "--decision", "approve", "--title", "Rise")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
    state(state_dir, "record-approval", "--gate", "s4_producer",
          "--participant-key", pk, "--decision", "approve")
    state(state_dir, "record-approval", "--gate", "s4_participant",
          "--participant-key", pk, "--decision", "approve")
    # cursor is now s5_chapter (the chapter producer-review cursor)
    if target == "s5_chapter":
        return pk
    # a chapter artifact is required for the s5_participant freeze/rewrite decisions
    state(state_dir, "record-artifact", "--participant-key", pk, "--type", "chapter",
          "--sha256", "sha_%s" % contact, "--model-used", "glm-5.2")
    state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s5_gate")
    if target == "s6_rewrite":
        state(state_dir, "record-approval", "--gate", "s5_participant",
              "--participant-key", pk, "--decision", "request_rewrite", "--notes", "tighten")
        return pk           # cursor -> s6_rewrite
    if target == "s7_cover":
        state(state_dir, "record-approval", "--gate", "s5_participant",
              "--participant-key", pk, "--decision", "approve")
        return pk           # cursor -> s7_cover
    raise AssertionError("unknown target cursor %r" % target)


def _cursor(state_dir, pk):
    _rc, p = state(state_dir, "get-participant", "--participant-key", pk)
    return p["stage_cursor"]


# --------------------------------------------------------------------------- #
# PURE: the release-bus decision, imported directly (no ledger, no network).
# --------------------------------------------------------------------------- #
def test_release_slug_for_pure_decisions():
    sys.path.insert(0, str(SCRIPTS))
    import gate_engine as ge  # noqa: E402
    for cursor, gid, slug in GATES:
        g = ge.GATE_BY_CURSOR[cursor]
        assert g.gate_id == gid and g.door_kind == "producer", (cursor, g)
        assert ge.GATE_RELEASE_SLUG[gid] == slug
        # fires ONLY on a committed board-door producer approve
        assert ge.release_slug_for(g, "approve", "board", True) == slug
        # never on any other action, the token door, or an uncommitted decision
        for action, door, committed in (
                ("hold", "board", True), ("exclude", "board", True),
                ("escalate", "board", True), ("approve", "token", True),
                ("approve", "board", False)):
            assert ge.release_slug_for(g, action, door, committed) is None, \
                (cursor, action, door, committed)


# --------------------------------------------------------------------------- #
# END-TO-END: a committed BOARD approve fires the tag; the cursor is unchanged.
# --------------------------------------------------------------------------- #
def _assert_release_fires(tmp_path, cursor, gate_id, slug):
    _seed(tmp_path)
    pk = _walk_to(tmp_path, "cFIRE", cursor)
    assert _cursor(tmp_path, pk) == cursor, "walk did not land on %s" % cursor
    # the board sees a producer gate open here
    rc, st = gate(tmp_path, "status", "--subject-key", pk, expect_rc=0)
    assert st["open_gate"] == gate_id and st["actor"] == "producer"
    assert st["doors"] == ["board"]
    # a committed board approve fires the §3 slug through the release bus
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", "approve",
                   "--subject-key", pk, expect_rc=0)
    assert out["committed"] is True and out["decision"] == "approve"
    assert out["gate"] == gate_id
    assert isinstance(out.get("release_tag"), dict), "the release bus did not fire"
    assert out["release_tag"]["slug"] == slug, out["release_tag"]
    # RELEASE-ONLY: the producer approve owns no cursor edge -- the pipeline stays put
    assert _cursor(tmp_path, pk) == cursor, "a release-only approve must not move the cursor"


def test_s5_chapter_producer_approve_fires_release(tmp_path):
    _assert_release_fires(tmp_path, "s5_chapter", "s5_producer", "anthology-release-chapter")


def test_s6_rewrite_producer_approve_fires_release(tmp_path):
    _assert_release_fires(tmp_path, "s6_rewrite", "s6_producer", "anthology-release-rewrite")


def test_s7_cover_producer_approve_fires_release(tmp_path):
    _assert_release_fires(tmp_path, "s7_cover", "s7_producer", "anthology-release-cover")


# --------------------------------------------------------------------------- #
# END-TO-END negative: hold and exclude commit but NEVER fire the release tag.
# --------------------------------------------------------------------------- #
def _assert_no_release(tmp_path, cursor, action, extra):
    _seed(tmp_path)
    pk = _walk_to(tmp_path, "cNO", cursor)
    rc, out = gate(tmp_path, "decide", "--door", "board", "--action", action,
                   "--subject-key", pk, *extra, expect_rc=0)
    assert "release_tag" not in out, "%s must NOT fire a release tag: %s" % (action, out)


def test_s5_chapter_hold_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s5_chapter", "hold", ["--reason", "credit_out"])


def test_s5_chapter_exclude_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s5_chapter", "exclude", [])


def test_s6_rewrite_hold_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s6_rewrite", "hold", ["--reason", "callback_lost"])


def test_s6_rewrite_exclude_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s6_rewrite", "exclude", [])


def test_s7_cover_hold_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s7_cover", "hold", ["--reason", "strike_out"])


def test_s7_cover_exclude_does_not_release(tmp_path):
    _assert_no_release(tmp_path, "s7_cover", "exclude", [])


# --------------------------------------------------------------------------- #
# The token door never releases (participant credential) even at a producer gate.
# --------------------------------------------------------------------------- #
def test_token_door_refused_at_producer_gate(tmp_path):
    _seed(tmp_path)
    pk = _walk_to(tmp_path, "cTOK", "s7_cover")
    # A producer/release gate is board-door only, and the token door needs the scoped
    # secret this hermetic box never sets: either way the decision is REFUSED (never 0)
    # and NOTHING releases (the release bus only fires on a committed BOARD approve).
    rc, out = gate(tmp_path, "decide", "--door", "token", "--action", "approve",
                   "--subject-key", pk, "--token", "v1.bogus.bogus")
    assert rc in (2, 3), "token door at a producer gate must be refused, got rc=%s" % rc
    assert out is None or "release_tag" not in out


# --------------------------------------------------------------------------- #
# The three original LIVE gates are untouched (regression guard).
# --------------------------------------------------------------------------- #
def test_original_live_gates_unchanged():
    sys.path.insert(0, str(SCRIPTS))
    import gate_engine as ge  # noqa: E402
    assert ge.release_slug_for(ge.GATE_BY_CURSOR["s1_gate"], "approve", "board", True) \
        == "anthology-release-avatar"
    assert ge.release_slug_for(ge.GATE_BY_CURSOR["s2_gate"], "approve", "board", True) \
        == "anthology-release-tone"
    assert ge.release_slug_for(ge.GATE_BY_CURSOR["s4_gate_producer"], "approve", "board", True) \
        == "anthology-release-outline"
    # participant gates still never release
    assert ge.release_slug_for(ge.GATE_BY_CURSOR["s5_gate"], "approve_as_is", "board", True) is None
    assert ge.release_slug_for(ge.GATE_BY_CURSOR["s3_gate"], "select", "board", True) is None


def _run_all():
    import tempfile
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            if "tmp_path" in fn.__code__.co_varnames[:fn.__code__.co_argcount]:
                with tempfile.TemporaryDirectory() as td:
                    fn(Path(td))
            else:
                fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_release_bus_producer_gates: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

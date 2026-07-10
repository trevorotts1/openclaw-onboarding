#!/usr/bin/env python3
"""test_s9_assembly_runner_confirm_order.py -- closes the S9 RUNNER test gap.

The existing S9 suite (test_s9_assembly_transitions_finale.py) exercises only the
LOGIC functions (write_transitions / write_finale / compile_manuscript / the two
provers) in isolation. It never drives scripts/stage_s9_assembly.py's runner
ORCHESTRATION, so a runner-level regression -- the confirm_order pass
UNCONDITIONALLY re-curating the order (assembly-set-order --state proposed), an
ILLEGAL adjusted->proposed transition that raised before the Grand Finale +
inter-chapter transitions were ever written -- slipped straight through a green
battery. These tests drive the REAL runner (_invoke_wiring) against a REAL seeded
ledger, mocking ONLY the LLM writers (the model_router boundary), and prove the
final edition emits through the producer's confirm_order action.

Hermetic: a REAL local ledger (anthology_state.py under a temp ANTHOLOGY_STATE_DIR;
MIRROR-ONLY, no Airtable, no network), the REAL confirm_order board action
(gate_engine.py), the REAL S9 orchestration + state machine + deterministic
compile + sha byte-identity re-proof. The ONLY test double is the model router
(stage_s9_assembly_logic._default_router) -- every ae-01..ae-06 model call. Frozen
chapter bodies are written where the runner's chapter_source reads them
(state/runs/s5/<safe>/working/chapter.md) and torn down afterwards.

NOTE (separate, pre-existing, out-of-scope defect observed while writing this
test): the runner's assembly Gate B call shells qc-tier1-anthology.py with
--anthology-id/--manuscript, args that script's argparse does not accept, so Gate
B (which runs AFTER compile) exits 2 and the runner's overall return code is
non-zero. That is unrelated to the confirm_order/curate defect under test and is
NOT asserted here; these tests assert the DURABLE orchestration evidence the
confirm_order bug corrupts -- the persisted ledger state and the compiled
manuscript bytes -- both of which are established at/by compile, before Gate B.

Run: python3 -m pytest 59-anthology-engine/tests/test_s9_assembly_runner_confirm_order.py -q
 or: python3 59-anthology-engine/tests/test_s9_assembly_runner_confirm_order.py
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS = SKILL_DIR / "scripts"
STATE = SCRIPTS / "anthology_state.py"
GATE = SCRIPTS / "gate_engine.py"
PY = sys.executable or "python3"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import stage_s9_assembly_logic as logic          # noqa: E402
import stage_s9_assembly as runner               # noqa: E402

AID = "ANTHrunner01"
PID = "prodRUNNER"
NAME = "The Test Collection"
K1, K2, K3 = "cR1::" + AID, "cR2::" + AID, "cR3::" + AID
KEYS = [K1, K2, K3]                              # ledger-sorted (frozen) order
TITLES = {K1: "Rise", K2: "Fall Forward", K3: "Begin Again"}
NAMES = {K1: ("Ada", "Vaughn"), K2: ("Ben", "Reyes"), K3: ("Cyd", "Okafor")}
BODIES = {k: ("# %s\n\nThis is the frozen body of %s.\nA second line for %s.\n"
              % (TITLES[k], k, k)).encode("utf-8") for k in KEYS}
SHAS = {k: hashlib.sha256(BODIES[k]).hexdigest() for k in KEYS}
# The producer's CONFIRMED order is a DELIBERATELY non-sorted permutation so the
# manuscript order proves the confirmed order is used, not a re-derived/sorted one.
CONFIRMED = [K3, K1, K2]


# --------------------------------------------------------------------------- #
# ledger seeding (the REAL gate walk -- the two conditions S9 readiness needs:
# stage_cursor 'approved' + a FROZEN chapter artifact)
# --------------------------------------------------------------------------- #
def _state(state_dir, *args):
    argv = [PY, str(STATE), args[0], "--state-dir", str(state_dir), "--json", *args[1:]]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, "anthology_state %s rc=%d :: %s" % (args[0], p.returncode, p.stderr)
    return json.loads(p.stdout) if (p.stdout or "").strip() else {}


def _walk_to_approved(state_dir, pk):
    contact = pk.split("::", 1)[0]
    first, last = NAMES[pk]
    _state(state_dir, "upsert-participant", "--contact-id", contact,
           "--anthology-id", AID, "--first-name", first, "--last-name", last)
    for to in ("s1_avatar", "s1_gate"):
        _state(state_dir, "advance-stage", "--participant-key", pk, "--to", to)
    _state(state_dir, "record-approval", "--gate", "s1_producer", "--participant-key", pk, "--decision", "approve")
    _state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s2_gate")
    _state(state_dir, "record-approval", "--gate", "s2_producer", "--participant-key", pk, "--decision", "approve")
    _state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s3_gate")
    _state(state_dir, "record-approval", "--gate", "s3_selection", "--participant-key", pk,
           "--decision", "approve", "--title", TITLES[pk])
    _state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s4_gate_producer")
    _state(state_dir, "record-approval", "--gate", "s4_producer", "--participant-key", pk, "--decision", "approve")
    _state(state_dir, "record-approval", "--gate", "s4_participant", "--participant-key", pk, "--decision", "approve")
    _state(state_dir, "record-artifact", "--participant-key", pk, "--type", "chapter",
           "--sha256", SHAS[pk], "--model-used", "glm-5.2")
    _state(state_dir, "advance-stage", "--participant-key", pk, "--to", "s5_gate")
    _state(state_dir, "record-approval", "--gate", "s5_participant", "--participant-key", pk, "--decision", "approve")
    for to in ("s8_deliver", "s9_wait_assembly", "approved"):
        _state(state_dir, "advance-stage", "--participant-key", pk, "--to", to)


def _seed_ready(state_dir):
    """Seed a real ledger to the ARMED/ready_confirmed ordering window."""
    _state(state_dir, "bootstrap")
    _state(state_dir, "upsert-producer", "--producer-id", PID,
           "--producer-email", "owner@example.test", "--display-name", "Owner")
    _state(state_dir, "upsert-anthology", "--anthology-id", AID,
           "--producer-id", PID, "--name", NAME, "--min-chapters", "2")
    for pk in KEYS:
        _walk_to_approved(state_dir, pk)
    _state(state_dir, "record-approval", "--gate", "s9_ready", "--anthology-id", AID,
           "--producer-id", PID, "--confirm-name", NAME)


def _safe(pk):
    return "".join(c if (c.isalnum() or c in "-_.") else "_" for c in pk)


def _write_frozen_bodies():
    """Drop each frozen chapter body where the runner's chapter_source reads it
    (SKILL_DIR/state/runs/s5/<safe>/working/chapter.md). Returns the dirs to remove."""
    made = []
    for pk in KEYS:
        d = SKILL_DIR / "state" / "runs" / "s5" / _safe(pk)
        (d / "working").mkdir(parents=True, exist_ok=True)
        (d / "working" / "chapter.md").write_bytes(BODIES[pk])
        made.append(d)
    return made


def _anth(state_dir):
    return _state(state_dir, "get-anthology", "--anthology-id", AID)


# --------------------------------------------------------------------------- #
# the SOLE test double: the model router (every ae-01..ae-06 LLM call). It also
# RECORDS the steps it was asked for, so a test can prove the runner did/did not
# call a given writer.
# --------------------------------------------------------------------------- #
def _bridge_body(next_title, target=210):
    words = ("We pause at the seam between two finished voices. The chapter that follows is "
             "titled %s and it carries the theme onward with fresh conviction and open hands."
             % next_title).split()
    while len(words) < target:
        words += "The reader turns the page with intention and a steady open heart.".split()
    return " ".join(words[:target]) + "."


def _finale_body(order):
    lines = ["This collection gathered every voice into one arc of resilience and hope."]
    for k in order:
        lines.append("In %s, the reader meets a turning point that echoes the whole theme."
                     % TITLES[k])
    lines += ["", "## Where Do You Go From Here", "",
              "1. Begin the practice today, in one small way.",
              "2. Share your story with a single person who needs it.",
              "3. Return to these pages whenever the road turns."]
    return "\n".join(lines)


def _make_router(order, seen):
    """A fake router for ae-01..ae-06. `order` is the running order this pass will
    ask transitions/finale about (seam k names order[k]); `seen` collects the steps."""
    def _router(tier, messages, context, run_dir=None, model_map_path=None):
        step = context["step"]
        seen.append(step)
        if step == "s9_order_curation":
            proposal = {"order": list(order),
                        "position_rationale": [{"position": i + 1, "participant_key": k,
                                                "reason": "slot %d" % (i + 1)}
                                               for i, k in enumerate(order)],
                        "overall_rationale": "a curated arc"}
            return {"text": json.dumps(proposal), "model_used": "glm-x", "tier": tier,
                    "provider": "p", "usage": {}}
        if step == "s9_bios":
            bios = [{"participant_key": k, "bio_markdown": "Bio of %s %s." % NAMES[k]} for k in KEYS]
            return {"text": json.dumps({"bios": bios}), "model_used": "glm-x", "tier": tier,
                    "provider": "p", "usage": {}}
        if step.startswith("s9_transition_"):
            seam = int(step.rsplit("_", 1)[1])          # seam k names order[k]
            return {"text": "<!-- TRANSITION -->\n%s\n<!-- END TRANSITION -->"
                            % _bridge_body(TITLES[order[seam]]),
                    "model_used": "glm-x", "tier": tier, "provider": "p", "usage": {}}
        if step == "s9_grand_finale":
            return {"text": json.dumps({"finale_title": "The Bridge We Built Together",
                                        "finale_markdown": _finale_body(order)}),
                    "model_used": "glm-x", "tier": tier, "provider": "p", "usage": {}}
        raise AssertionError("unexpected router step %r (test provides no producer_inputs, "
                             "so intro/matter must not be requested)" % step)
    return _router


def _drive(state_dir, run_dir, router):
    """Drive the REAL runner orchestration with ONLY the LLM router mocked. Returns
    the runner's classified exit code (not asserted on -- see the module note re Gate B)."""
    prev_env = os.environ.get("ANTHOLOGY_STATE_DIR")
    prev_router = logic._default_router
    os.environ["ANTHOLOGY_STATE_DIR"] = str(state_dir)
    logic._default_router = router
    try:
        return runner._invoke_wiring(AID, str(run_dir))
    finally:
        logic._default_router = prev_router
        if prev_env is None:
            os.environ.pop("ANTHOLOGY_STATE_DIR", None)
        else:
            os.environ["ANTHOLOGY_STATE_DIR"] = prev_env


class _Sandbox:
    """A temp ledger + run dir + on-disk frozen bodies, all torn down on exit."""
    def __enter__(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="s9runner_"))
        self.state_dir = self.tmp / "state"
        self.run_dir = self.tmp / "run"
        (self.run_dir / "working").mkdir(parents=True)
        self.body_dirs = _write_frozen_bodies()
        return self

    def __exit__(self, *exc):
        for d in self.body_dirs:
            shutil.rmtree(d, ignore_errors=True)
        # best-effort: leave no empty state/runs/s5 scaffolding behind (rmdir only
        # succeeds while a directory is empty, so this never removes a dir in use).
        for leftover in (SKILL_DIR / "state" / "runs" / "s5",
                         SKILL_DIR / "state" / "runs", SKILL_DIR / "state"):
            try:
                leftover.rmdir()
            except OSError:
                break
        shutil.rmtree(self.tmp, ignore_errors=True)
        return False


# --------------------------------------------------------------------------- #
# POSITIVE: the confirm_order pass emits the FINAL edition through the runner.
# --------------------------------------------------------------------------- #
def test_runner_confirm_order_emits_final_edition_in_confirmed_order():
    with _Sandbox() as sb:
        _seed_ready(sb.state_dir)
        # the arm pass left the typed-name confirmation in request.json; the board
        # confirm_order preserves it and adds confirm_order + the confirmed order.
        (sb.run_dir / "request.json").write_text(
            json.dumps({"producer_id": PID, "confirm_name": NAME}), encoding="utf-8")
        # the REAL board "Confirm the finalized set & order" action: persists the order
        # through the sole writer (assembly_state -> adjusted) and flags the runner.
        p = subprocess.run(
            [PY, str(GATE), "decide", "--state-dir", str(sb.state_dir), "--json",
             "--door", "board", "--action", "confirm_order", "--subject-key", AID,
             "--producer-id", PID, "--order", json.dumps(CONFIRMED),
             "--opener", CONFIRMED[0], "--closer", CONFIRMED[-1],
             "--run-dir", str(sb.run_dir)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, "confirm_order rc=%d :: %s" % (p.returncode, p.stderr)
        assert _anth(sb.state_dir)["assembly_state"] == "adjusted"

        seen = []
        _drive(sb.state_dir, sb.run_dir, _make_router(CONFIRMED, seen))

        # (1) DIRECT proof the defect is gone: the confirm_order pass did NOT re-curate.
        assert "s9_order_curation" not in seen, \
            "confirm_order pass re-curated the order (the regressed behaviour)"
        # it DID drive the final-edition writers (ae-05 per seam, ae-06 finale, ae-03 bios).
        assert seen.count("s9_grand_finale") == 1
        assert sorted(s for s in seen if s.startswith("s9_transition_")) == \
            ["s9_transition_1", "s9_transition_2"]
        assert "s9_bios" in seen

        # (2) the ledger assembly_state advanced along the LEGAL adjusted->compiled edge.
        assert _anth(sb.state_dir)["assembly_state"] == "compiled"

        # (3) the compiled manuscript carries EXACTLY N-1 transitions + ONE titled finale.
        ms_path = sb.run_dir / "working" / "manuscript.md"
        assert ms_path.is_file(), "the runner did not compile a manuscript"
        ms = ms_path.read_text(encoding="utf-8")
        assert len(logic.extract_transition_blocks(ms)) == len(KEYS) - 1 == 2
        finale = logic.extract_finale_block(ms)
        assert finale is not None and logic._first_heading_title(finale) == \
            "The Bridge We Built Together"

        # (4) both provers pass over the REAL compiled bytes, in the CONFIRMED order.
        rep_t = logic.prove_transitions(ms, CONFIRMED, TITLES, frozen_bodies=BODIES)
        assert rep_t["ok"], rep_t["issues"]
        assert rep_t["seams"][0]["next_title"] == TITLES[CONFIRMED[1]]
        assert rep_t["seams"][1]["next_title"] == TITLES[CONFIRMED[2]]
        rep_f = logic.prove_finale(ms, TITLES, order=CONFIRMED)
        assert rep_f["ok"], rep_f["issues"]

        # (5) chapter bodies appear in the producer's CONFIRMED (non-sorted) order.
        offsets = [ms.find("frozen body of %s" % k) for k in CONFIRMED]
        assert all(o >= 0 for o in offsets), "a frozen body is missing from the manuscript"
        assert offsets == sorted(offsets), \
            "manuscript order does not match the producer's confirmed order"

        # (6) every frozen chapter body is byte-identical in the compiled manuscript.
        for k in KEYS:
            assert BODIES[k].decode("utf-8") in ms, "frozen chapter %s not byte-identical" % k
        assert rep_t["frozen_unchanged"] is True


def test_runner_confirm_order_uses_ledger_chapter_order_when_request_order_absent():
    """The fallback branch: if request.json omits the order, the runner uses the
    ledger's confirmed chapter_order (persisted in the 'adjusted' state). Still no
    re-curate, still the final edition."""
    with _Sandbox() as sb:
        _seed_ready(sb.state_dir)
        (sb.run_dir / "request.json").write_text(
            json.dumps({"producer_id": PID, "confirm_name": NAME}), encoding="utf-8")
        p = subprocess.run(
            [PY, str(GATE), "decide", "--state-dir", str(sb.state_dir), "--json",
             "--door", "board", "--action", "confirm_order", "--subject-key", AID,
             "--producer-id", PID, "--order", json.dumps(CONFIRMED),
             "--opener", CONFIRMED[0], "--closer", CONFIRMED[-1],
             "--run-dir", str(sb.run_dir)], capture_output=True, text=True, timeout=60)
        assert p.returncode == 0, p.stderr
        # strip request['order'] so the runner must fall back to the ledger chapter_order.
        req = json.loads((sb.run_dir / "request.json").read_text(encoding="utf-8"))
        req.pop("order", None)
        assert req.get("confirm_order") is True
        (sb.run_dir / "request.json").write_text(json.dumps(req), encoding="utf-8")

        seen = []
        _drive(sb.state_dir, sb.run_dir, _make_router(CONFIRMED, seen))

        assert "s9_order_curation" not in seen
        assert _anth(sb.state_dir)["assembly_state"] == "compiled"
        ms = (sb.run_dir / "working" / "manuscript.md").read_text(encoding="utf-8")
        # the ledger's chapter_order (== CONFIRMED) drove the compiled order.
        offsets = [ms.find("frozen body of %s" % k) for k in CONFIRMED]
        assert offsets == sorted(offsets) and all(o >= 0 for o in offsets)
        assert logic.extract_finale_block(ms) is not None


# --------------------------------------------------------------------------- #
# NEGATIVE: an arm pass (NO confirm_order) curates but does NOT emit the finale.
# --------------------------------------------------------------------------- #
def test_runner_arm_pass_without_confirm_does_not_emit_finale():
    with _Sandbox() as sb:
        _seed_ready(sb.state_dir)                    # ready_confirmed; no confirm_order
        # an arm-shaped request.json: producer_id + typed name, but NO confirm_order.
        (sb.run_dir / "request.json").write_text(
            json.dumps({"producer_id": PID, "confirm_name": NAME}), encoding="utf-8")
        assert _anth(sb.state_dir)["assembly_state"] == "ready_confirmed"

        seen = []
        # the arm pass DOES curate, so the router will be asked for the order (sorted set).
        _drive(sb.state_dir, sb.run_dir, _make_router(KEYS, seen))

        # curation happened; the final-edition writers were NOT invoked.
        assert "s9_order_curation" in seen, "the arm pass must still curate a working order"
        assert not any(s.startswith("s9_transition_") for s in seen), \
            "an unconfirmed pass must not write inter-chapter transitions"
        assert "s9_grand_finale" not in seen, \
            "an unconfirmed pass must not write the Grand Finale"

        # whatever the pass compiled carries NO finale and NO transitions.
        ms_path = sb.run_dir / "working" / "manuscript.md"
        if ms_path.is_file():
            ms = ms_path.read_text(encoding="utf-8")
            assert logic.extract_finale_block(ms) is None, "finale leaked into an unconfirmed edition"
            assert logic.extract_transition_blocks(ms) == [], \
                "transitions leaked into an unconfirmed edition"


# --------------------------------------------------------------------------- #
# standalone runner (the gate battery runs both `python3 <file>` and pytest)
# --------------------------------------------------------------------------- #
def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print("  [PASS] %s" % fn.__name__)
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print("  [FAIL] %s -- %s" % (fn.__name__, exc))
    print("test_s9_assembly_runner_confirm_order: %s (%d/%d)"
          % ("ALL PASSED" if not failed else "FAILURES", len(fns) - failed, len(fns)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(_run_all())

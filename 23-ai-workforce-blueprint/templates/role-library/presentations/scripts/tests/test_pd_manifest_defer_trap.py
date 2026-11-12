"""PD-038 -- a declined sales/checkout or VSL branch must not strand the run.

The manifest fix: `P-U-SALES-BUILD`, `P-U-CHECKOUT-BUILD` and
`P-U-FORM-CHECKOUT` carry `defers_unless: intake.want_sales_checkout == "yes"`
and `P-U-VSL-BUILD` carries `intake.want_vsl_page == "yes"` (the copy phases
they consume already carried it). Without the predicate the build phase is an
ACTIVE phase with no gate of its own consuming a file whose only producer is
DEFERRED; `presentation_job.execution_plan.build_edge_records` marks an edge
optional by the CONSUMER's `defers_unless`, so that edge is REQUIRED and
`Engine._check_predecessor_success` withholds the consumer with
"deferred, but phase ... requires it through a non-optional edge" -- forever.

Proven here on a scratch manifest shaped like the real upsell branch, in the
style of tests/test_pres002_ready_gate.py:

  1. declined -> the run ends successfully and the build phase is DEFERRED
     (the branch declines as a whole; nothing waits on a missing artifact).
  2. the CONTROL: the same shape with the build phase's predicate removed does
     NOT end successfully -- the build phase is withheld on the non-optional
     edge. This is what makes test 1 able to fail.

No model, network, notification, upload or paid call is made: the executors are
real `python3 -c` scripts that write a file, and the verifier/gate/close seams
are stubbed (a scratch manifest has no registered verifier and must never mint
an attestation).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK  # noqa: E402
import phase_verifiers  # noqa: E402

SALES_GATE = 'intake.want_sales_checkout == "yes"'


def _cmd_that_writes(target: str) -> str:
    d = json.dumps(target)
    body = (f"import pathlib;"
            f"p=pathlib.Path({d});p.parent.mkdir(parents=True,exist_ok=True);"
            f"p.write_text('done')")
    return f"python3 -c {json.dumps(body)}"


def _engine(tmp_path: Path, phases: list) -> Engine:
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    mp = tmp_path / "PIPELINE-MANIFEST.json"
    mp.write_text(json.dumps({
        "manifest_version": 25,
        "phases": [{"id": pid, "order": order, "owning_role": "test",
                    "produces_artifact": [art],
                    **({"consumes": cons} if cons else {}),
                    **({"defers_unless": du} if du else {}),
                    "executor": {"kind": "script", "cmd": cmd}}
                    for (pid, order, art, cons, cmd, du) in phases],
    }), encoding="utf-8")
    manifest = Manifest(mp)
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": str(mp), "manifest_version": 25,
        "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    return Engine(rd, manifest, store, state, dry_run=False)


@pytest.fixture(autouse=True)
def _stub_boundaries(monkeypatch):
    """Scratch phase ids have no registered verifier; the engine fails closed on
    that. These tests prove SCHEDULING and every artifact is a real file the
    executor wrote, so a pass-through substance check is the honest stand-in.
    close() is stubbed to its success terminal: the scheduling subject never
    touches gate logic and no attestation is minted."""
    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))
    import presentation_job.phases as phases_mod
    monkeypatch.setattr(
        phases_mod.Gates, "evaluate_all",
        lambda self: {k: {"state": "pass", "reason": "test stub"} for k in
                      phases_mod.ALL_GATE_KEYS})

    def _stub_close(self):
        with self._state_lock:
            self.state["terminal"] = "DONE"
            self.store.save(self.state)
        return EXIT_OK
    monkeypatch.setattr(phases_mod.Engine, "close", _stub_close)
    monkeypatch.setenv("PRESENTATION_DAG_ADMISSION", "1")
    monkeypatch.setenv("PRESENTATION_WAVE_EXECUTION", "1")
    yield


def _declined_intake(tmp_path: Path) -> None:
    """The real intake shape the driver writes: pre_presentation_capture.*."""
    copy_dir = tmp_path / "run" / "working" / "copy"
    copy_dir.mkdir(parents=True, exist_ok=True)
    (copy_dir / "intake.json").write_text(json.dumps({
        "presentation_type": "from_scratch",
        "pre_presentation_capture": {"WANT_SALES_CHECKOUT": "no"},
        "waivers": [{"rule": "sales_checkout",
                     "client_request_quote": "no sales page this time"}],
    }))


def _branch(build_gate: str | None) -> list:
    """Copy phase + build phase, the real branch's artifact names.

    INDY is an unrelated sibling that must complete regardless.
    """
    return [
        ("INDY", 1, "working/i.txt", [], _cmd_that_writes("working/i.txt"), None),
        ("P-U-SALES-COPY", 3.6, "working/upsell/copy/sales.fragment.md", [],
         _cmd_that_writes("working/upsell/copy/sales.fragment.md"), SALES_GATE),
        ("P-U-SALES-BUILD", 8.75, "working/sales-checkout/html/sales.html",
         ["working/upsell/copy/sales.fragment.md"],
         _cmd_that_writes("working/sales-checkout/html/sales.html"), build_gate),
    ]


def test_declined_sales_branch_defers_the_build_and_the_run_succeeds(tmp_path):
    """A2: the fixed shape -- the gated build phase defers with its producer."""
    _declined_intake(tmp_path)
    eng = _engine(tmp_path, _branch(SALES_GATE))
    rc = eng.run()
    assert rc == EXIT_OK, eng.state.get("blocked") or eng.state.get("terminal")
    assert eng._phase_state("INDY").get("status") == "done", \
        "an unrelated sibling must complete regardless of the declined branch"
    assert eng._phase_state("P-U-SALES-COPY").get("status") == "deferred"
    ps_build = eng._phase_state("P-U-SALES-BUILD")
    assert ps_build.get("status") == "deferred", \
        f"the gated build phase must defer with its branch, got {ps_build.get('status')}"
    assert not ps_build.get("waiting_dependency"), \
        f"a deferred phase must not wait on a declined producer: {ps_build.get('waiting_dependency')}"
    run_dir = tmp_path / "run"
    assert not (run_dir / "working" / "upsell" / "copy" / "sales.fragment.md").exists()
    assert not (run_dir / "working" / "sales-checkout" / "html" / "sales.html").exists()


def test_ungated_build_phase_is_stranded_on_the_non_optional_edge(tmp_path):
    """A3 (the control): without the predicate the same run cannot succeed.

    This is the PD-038 defect itself: a deferred producer can never satisfy a
    REQUIRED edge, so the build phase is withheld -- which is why test A2's
    success depends on the manifest carrying `defers_unless` on the build.
    """
    _declined_intake(tmp_path)
    eng = _engine(tmp_path, _branch(None))
    rc = eng.run()
    ps_build = eng._phase_state("P-U-SALES-BUILD")
    waiting = ps_build.get("waiting_dependency") or []
    assert rc != EXIT_OK, \
        "a build phase with no defers_unless consuming a declined producer cannot succeed"
    assert eng._phase_state("P-U-SALES-COPY").get("status") == "deferred"
    assert eng._phase_state("INDY").get("status") == "done", \
        "the declined branch must not stop unrelated work"
    assert any(w.get("blocked_by") == "P-U-SALES-COPY"
               and "non-optional" in (w.get("reason") or "") for w in waiting), \
        f"the deferred producer must be named on a non-optional edge: {waiting}"
    assert ps_build.get("status") != "done"
    assert not (tmp_path / "run" / "working" / "sales-checkout" / "html" / "sales.html").exists()

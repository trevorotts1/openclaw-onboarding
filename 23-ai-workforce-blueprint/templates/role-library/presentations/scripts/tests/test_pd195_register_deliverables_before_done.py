"""PD-TEST-195 -- a phase's work is REGISTERED before its card is closed 'done'.

THE DEFECT, MEASURED LIVE on pres-operator-1d269693:

    [cc_board/presentations] patch_phase P-STYLE-PREVIEW->done non-OK (HTTP 403):
      {'error': 'Forbidden: cannot mark a task done with no completion evidence.',
       'hint': 'Cannot record this task as done: no completion evidence. No deliverable
                of any kind is registered against this task. ... Register it with POST
                /api/tasks/<id>/deliverables -- {"deliverable_type":"file","title":"<name>",
                "path":"<absolute path>"} for a produced file ...'}

The phase had genuinely produced its artifacts -- nine style samples and a manifest
on disk -- and the engine had verified them, so `child_report(..., "done", ...)`
PATCHed the child card to `done` without ever telling the board WHAT was produced.
The board refused, and the result was a board that DISAGREES WITH THE RUN: the
card showed the phase not-done while the engine held it done with artifacts on
disk. That is the opposite of an accurate Kanban, and it was SILENT -- patch_phase
is fail-soft, so nothing stopped and nothing failed.

The client already had the capability (`cc_board.register_deliverable`, FIX-12);
the phase-completion path simply never called it. It also could not have
registered a local artifact correctly, because it hard-coded
`deliverable_type="url"` while the schema's enum is file|url|artifact|image and a
produced FILE must be registered as `file` with an absolute path.

These tests pin: the artifacts go in BEFORE the transition, as `file` type, and
the whole thing stays fail-soft -- a board that cannot be told is never a reason
to hold the deck.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

import cc_board  # noqa: E402
from presentation_job import board as board_module  # noqa: E402


class _Reporter:
    def __init__(self):
        self.events = []

    def event(self, kind, message, **extra):
        self.events.append({"kind": kind, "message": message})


def _mirror(tmp_path, fake_cc, *, child="child-1", artifacts=()):
    run_dir = tmp_path / "run"
    (run_dir / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    for rel in artifacts:
        f = run_dir / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x")
    state = {"board": {"task_id": "parent-1"}, "job_id": "pj_test",
             "intake": {"deck_slug": run_dir.name}}
    rep = _Reporter()
    # NOTE: child_report resolves its client at CALL time through
    # _get_cc_board(), so the patch must outlive construction. Assign the module
    # global directly (no context manager) and let each test own its own fake.
    board_module._cc_board = fake_cc
    bm = board_module.BoardMirror(run_dir, state, mock.MagicMock(), rep)
    bm._resolve_child_task_id = lambda phase_id: child
    return bm, rep, run_dir


def _fake_cc():
    cc = mock.MagicMock()
    # child_report reads the real frozenset; a MagicMock attribute would fail the
    # `status not in cc.CC_TASK_STATUSES` membership test in a confusing way.
    cc.CC_TASK_STATUSES = cc_board.CC_TASK_STATUSES
    cc.register_deliverable.return_value = True
    cc.patch_phase.return_value = True
    return cc


def test_artifacts_are_registered_BEFORE_the_done_transition(tmp_path):
    """THE REGRESSION. Ordering is the whole point -- evidence, then the close."""
    cc = _fake_cc()
    bm, _, run_dir = _mirror(tmp_path, cc,
                             artifacts=["working/prompts/slide-01.txt",
                                        "working/prompts/slide-02.txt"])
    order = []
    cc.register_deliverable.side_effect = lambda *a, **k: order.append("register") or True
    cc.patch_phase.side_effect = lambda *a, **k: order.append("patch") or True

    bm.child_report("P4-PROMPT", "t", "d", "done", "note",
                    deliverables=["working/prompts/slide-01.txt",
                                  "working/prompts/slide-02.txt"])

    assert order == ["register", "register", "patch"], (
        "the phase's work must be registered BEFORE the card is closed done; "
        f"observed order {order}")
    assert cc.register_deliverable.call_count == 2
    assert cc.patch_phase.call_count == 1


def test_a_local_artifact_is_registered_as_an_absolute_FILE(tmp_path):
    """A produced file is `deliverable_type='file'` with an ABSOLUTE path.

    The previous hard-coded `url` could not satisfy the board's requirement for a
    produced file, however many times it was called.
    """
    cc = _fake_cc()
    bm, _, run_dir = _mirror(tmp_path, cc, artifacts=["working/prompts/slide-01.txt"])
    bm.child_report("P4-PROMPT", "t", "d", "done", "n",
                    deliverables=["working/prompts/slide-01.txt"])
    assert cc.register_deliverable.call_count == 1
    args, kwargs = cc.register_deliverable.call_args
    registered_path = args[1]
    assert kwargs.get("deliverable_type") == "file", kwargs
    assert Path(registered_path).is_absolute(), registered_path
    assert Path(registered_path).exists(), registered_path


def test_a_non_done_transition_registers_nothing(tmp_path):
    """Only the close carries evidence; a blocked/progress report must not."""
    for status in ("blocked", "in_progress"):
        cc = _fake_cc()
        bm, _, _ = _mirror(tmp_path / status, cc, artifacts=["working/a.txt"])
        bm.child_report("P4-PROMPT", "t", "d", status, "n",
                        deliverables=["working/a.txt"])
        assert cc.register_deliverable.call_count == 0, status
        assert cc.patch_phase.call_count == 1, status


def test_a_missing_artifact_is_skipped_and_reported_but_never_blocks(tmp_path):
    """We do not claim evidence we do not have -- and we still close the card."""
    cc = _fake_cc()
    bm, rep, _ = _mirror(tmp_path, cc, artifacts=["working/real.txt"])
    bm.child_report("P4-PROMPT", "t", "d", "done", "n",
                    deliverables=["working/real.txt", "working/GONE.txt"])
    assert cc.register_deliverable.call_count == 1, "the ghost must not be registered"
    assert cc.patch_phase.call_count == 1, "a missing artifact must not hold the deck"
    assert any(e["kind"] == "board.deliverable_missing" for e in rep.events), rep.events


def test_a_registration_FAILURE_never_blocks_the_transition(tmp_path):
    """FAIL-SOFT: a board that cannot be told is not a reason to hold the deck."""
    cc = _fake_cc()
    cc.register_deliverable.return_value = False
    bm, rep, _ = _mirror(tmp_path, cc, artifacts=["working/a.txt"])
    bm.child_report("P4-PROMPT", "t", "d", "done", "n", deliverables=["working/a.txt"])
    assert cc.patch_phase.call_count == 1
    assert any(e["kind"] == "board.deliverable_unregistered" for e in rep.events)

    # ...and a RAISING client is caught too.
    cc2 = _fake_cc()
    cc2.register_deliverable.side_effect = ConnectionRefusedError("down")
    bm2, rep2, _ = _mirror(tmp_path / "raise", cc2, artifacts=["working/a.txt"])
    bm2.child_report("P4-PROMPT", "t", "d", "done", "n", deliverables=["working/a.txt"])
    assert cc2.patch_phase.call_count == 1
    assert any(e["kind"] == "board.deliverable_error" for e in rep2.events)


def test_no_deliverables_argument_keeps_the_old_behaviour(tmp_path):
    """Back-compat: every existing caller passes no deliverables."""
    cc = _fake_cc()
    bm, _, _ = _mirror(tmp_path, cc)
    bm.child_report("P4-PROMPT", "t", "d", "done", "n")
    assert cc.register_deliverable.call_count == 0
    assert cc.patch_phase.call_count == 1


def test_register_deliverable_sends_the_TYPE_it_was_given():
    """The client can now express a produced FILE, not just a URL."""
    seen = {}

    def _fake_request(method, url, payload, cfg):
        seen["url"] = url
        seen["payload"] = payload
        return (200, {})

    cfg = {"base_url": "http://board.test", "token": "t", "secret": "s"}
    with mock.patch.object(cc_board, "board_config", return_value=cfg), \
         mock.patch.object(cc_board, "_request", _fake_request):
        assert cc_board.register_deliverable("task-1", "/abs/path/deck.pptx",
                                             meta={"title": "deck.pptx"},
                                             env={}, deliverable_type="file") is True
        assert seen["payload"]["deliverable_type"] == "file", seen["payload"]
        assert seen["payload"]["path"] == "/abs/path/deck.pptx"
        assert seen["payload"]["title"] == "deck.pptx"
        # the default stays 'url' for every pre-existing caller
        cc_board.register_deliverable("task-1", "https://x/y", env={})
        assert seen["payload"]["deliverable_type"] == "url", seen["payload"]
        # an unknown type degrades to 'url' rather than 400-ing the board
        cc_board.register_deliverable("task-1", "https://x/y", env={},
                                      deliverable_type="banana")
        assert seen["payload"]["deliverable_type"] == "url", seen["payload"]


def test_a_RE_RUN_does_not_re_POST_already_registered_artifacts(tmp_path):
    """THE DEFECT THE REVIEW FOUND: the CC route is NOT idempotent.

    `command-center .../deliverables/route.ts` mints a fresh `crypto.randomUUID()`
    and does a plain INSERT -- no ON CONFLICT, no unique index -- then broadcasts
    an SSE event. So re-registering the same artifact creates a DUPLICATE row.
    The engine re-runs and re-admits phases by design, so the client must dedupe.
    """
    cc = _fake_cc()
    bm, _, _ = _mirror(tmp_path, cc, artifacts=["working/prompts/slide-01.txt"])
    for _ in range(3):  # a run, then two re-admissions
        bm.child_report("P4-PROMPT", "t", "d", "done", "n",
                        deliverables=["working/prompts/slide-01.txt"])
    assert cc.patch_phase.call_count == 3, "every transition must still happen"
    assert cc.register_deliverable.call_count == 1, (
        "the artifact was re-POSTed on a later transition, which the CC route "
        "turns into a duplicate deliverable row -- observed "
        f"{cc.register_deliverable.call_count} POSTs for one file")


def test_the_dedupe_survives_a_RESUME(tmp_path):
    """The registry lives ON DISK, so a fresh BoardMirror still skips.

    This is the case that actually produces duplicates: the duplicate comes from
    a LATER process re-running the phase, not from two calls in one process.
    """
    cc = _fake_cc()
    bm1, _, run_dir = _mirror(tmp_path, cc, artifacts=["working/a.txt"])
    bm1.child_report("P4-PROMPT", "t", "d", "done", "n", deliverables=["working/a.txt"])
    assert cc.register_deliverable.call_count == 1
    assert (run_dir / "working" / "checkpoints"
            / "cc-board-deliverables.json").exists(), "no on-disk registry"

    # a NEW mirror over the SAME run dir == a resumed engine
    cc2 = _fake_cc()
    state = {"board": {"task_id": "parent-1"}, "job_id": "pj_test",
             "intake": {"deck_slug": run_dir.name}}
    board_module._cc_board = cc2
    bm2 = board_module.BoardMirror(run_dir, state, mock.MagicMock(), _Reporter())
    bm2._resolve_child_task_id = lambda phase_id: "child-1"
    bm2.child_report("P4-PROMPT", "t", "d", "done", "n", deliverables=["working/a.txt"])
    assert cc2.patch_phase.call_count == 1, "the transition must still happen"
    assert cc2.register_deliverable.call_count == 0, (
        "a RESUMED run re-registered an artifact already on the card")


def test_distinct_artifacts_are_each_registered_once(tmp_path):
    """Dedupe must key on the PATH, not collapse everything to one registration."""
    cc = _fake_cc()
    bm, _, _ = _mirror(tmp_path, cc,
                       artifacts=["working/a.txt", "working/b.txt", "working/c.txt"])
    bm.child_report("P4-PROMPT", "t", "d", "done", "n",
                    deliverables=["working/a.txt", "working/b.txt", "working/c.txt"])
    assert cc.register_deliverable.call_count == 3
    bm.child_report("P4-PROMPT", "t", "d", "done", "n",
                    deliverables=["working/a.txt", "working/b.txt", "working/c.txt"])
    assert cc.register_deliverable.call_count == 3, "second pass must add nothing"

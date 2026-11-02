#!/usr/bin/env python3
"""Regression suite for dossier F14 (event run identity).

Run: python3 test_factory_event_run_identity_f14.py   (plain asserts, no framework)

Covers the F14 acceptance rows:
  1. a renamed run folder still resolves the run the store recorded
  2. a folder name that matches a DIFFERENT run never retargets it
  3. an unresolved / empty identity refuses, and is never invented
  4. an explicit id the store does not know is refused
  5. replaying an event keeps the same run identity (one attempt, no split)
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(HERE))

import factory as F  # noqa: E402
import state_store as ss  # noqa: E402

PASS = []


def ok(name):
    PASS.append(name)
    print("PASS  %s" % name)


def make_run(root, name, run_id, states):
    d = Path(root) / name
    (d / "control").mkdir(parents=True)
    st = ss.Store(d / "control" / "state.sqlite3")
    st.init_run(run_id, list(states))
    for stage, state in states.items():
        if state == "READY":
            st.transition(run_id, stage, "READY", "fixture")
    st.close()
    return d


def queue_ids(d):
    p = Path(d) / "control" / "continuation-queue.json"
    return [a.get("run_id") for a in json.loads(p.read_text())]


def test_renamed_folder_resolves_original_run():
    root = tempfile.mkdtemp(prefix="f14-rename-")
    try:
        a = make_run(root, "seed", "orig-run-123", {"research": "READY"})
        moved = Path(root) / "client-renamed-folder"
        shutil.copytree(a, moved)
        act = F.continuation_enqueue(str(moved), "restart")
        assert act["run_id"] == "orig-run-123", act
        assert act["next_stage"] == "research", act
        assert queue_ids(moved) == ["orig-run-123"], queue_ids(moved)
        ok("renamed folder resolves the original run")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_folder_name_matching_another_run_does_not_retarget():
    root = tempfile.mkdtemp(prefix="f14-collide-")
    try:
        a = make_run(root, "seed-a", "orig-run-123", {"research": "READY"})
        collided = Path(root) / "other-run-456"
        shutil.copytree(a, collided)
        st = ss.Store(collided / "control" / "state.sqlite3")
        st.init_run("other-run-456", ["research", "creative-strategy"])
        st.transition("other-run-456", "research", "READY", "fixture")
        st.close()
        try:
            F.continuation_enqueue(str(collided), "restart")
            raise AssertionError("ambiguous store targeted a run")
        except ValueError as exc:
            assert "run-id-ambiguous" in str(exc), exc
        assert not (collided / "control" / "continuation-queue.json").exists()
        ok("folder matching another run never retargets")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unresolved_identity_refuses():
    root = tempfile.mkdtemp(prefix="f14-empty-")
    try:
        d = Path(root) / "folder-name-is-not-an-id"
        (d / "control").mkdir(parents=True)
        try:
            F.continuation_enqueue(str(d), "restart")
            raise AssertionError("an empty store still invented a run id")
        except ValueError as exc:
            assert "run-id-empty" in str(exc), exc
        assert not (d / "control" / "continuation-queue.json").exists()
        ok("unresolved identity refuses")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_unknown_explicit_id_is_refused():
    root = tempfile.mkdtemp(prefix="f14-unknown-")
    try:
        a = make_run(root, "seed", "orig-run-123", {"research": "READY"})
        try:
            F.continuation_enqueue(str(a), "restart", run_id="some-other-run")
            raise AssertionError("an unknown explicit id was accepted")
        except ValueError as exc:
            assert "run-id-unknown" in str(exc), exc
        ok("unknown explicit id refused")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_replay_keeps_one_identity():
    root = tempfile.mkdtemp(prefix="f14-replay-")
    try:
        a = make_run(root, "seed", "orig-run-123", {"research": "READY"})
        first = F.continuation_enqueue(str(a), "restart")
        again = F.continuation_enqueue(str(a), "restart")
        assert first["run_id"] == again["run_id"] == "orig-run-123"
        ids = queue_ids(a)
        assert ids == ["orig-run-123", "orig-run-123"], ids
        ok("replay keeps one run identity")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_single_store_id_is_authoritative():
    root = tempfile.mkdtemp(prefix="f14-single-")
    try:
        a = make_run(root, "seed", "orig-run-123", {"research": "READY"})
        assert F.resolved_run_id(str(a)) == ("orig-run-123", None)
        assert F.resolved_run_id(str(a), "orig-run-123") == ("orig-run-123", None)
        ok("the store's single id is authoritative")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main():
    test_renamed_folder_resolves_original_run()
    test_folder_name_matching_another_run_does_not_retarget()
    test_unresolved_identity_refuses()
    test_unknown_explicit_id_is_refused()
    test_replay_keeps_one_identity()
    test_single_store_id_is_authoritative()
    print("\nALL %d CHECKS PASSED" % len(PASS))
    return 0


if __name__ == "__main__":
    sys.exit(main())

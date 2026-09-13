"""Regression for multi-output agent publication (PD-TEST-013).

The dispatcher receives one model response.  A list-valued ``produces_artifact``
must therefore be an explicit envelope, never a silent write to only its first
path.  This test stubs the transport and exercises the real dispatch path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job import dispatcher as d  # noqa: E402


class Phase:
    id = "P-U-SALES-COPY"
    owning_role = "writer"
    workers = 1
    budget_minutes = 5
    executor_kind = "agent"

    @staticmethod
    def resolve_artifact_patterns(_run_dir):
        return ["working/upsell/copy/sales.fragment.md",
                "working/upsell/copy/copy_ledger.json"]


def _dept(tmp_path: Path) -> Path:
    dept = tmp_path / "dept"
    role = dept / "writer"
    role.mkdir(parents=True)
    (role / "how-to.md").write_text("Write the requested page copy.")
    return dept


def _verify(_phase_id: str, run_dir: Path):
    fragment = run_dir / "working/upsell/copy/sales.fragment.md"
    ledger = run_dir / "working/upsell/copy/copy_ledger.json"
    if not fragment.is_file() or not ledger.is_file():
        return False, ["both declared artifacts are required"]
    try:
        parsed = json.loads(ledger.read_text())
    except json.JSONDecodeError:
        return False, ["ledger must be JSON"]
    return isinstance(parsed, dict), []


def test_multi_artifact_dispatch_publishes_every_declared_sibling(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "working/work-orders").mkdir(parents=True)
    monkeypatch.setattr(d, "_verify", _verify)
    monkeypatch.setattr(
        d, "dispatch_complete",
        lambda *args, **kwargs: (json.dumps({"artifacts": {
            "working/upsell/copy/sales.fragment.md": "# Sales\nReal deck-specific copy.",
            "working/upsell/copy/copy_ledger.json": json.dumps({"version": 1, "entries": []}),
        }}), {"request_id": "stub"}, {"provider": "stub", "model": "stub-1"}),
    )
    order = {"phase": "P-U-SALES-COPY", "owning_role": "writer",
             "produces_artifact": Phase.resolve_artifact_patterns(run)}
    result = d.dispatch_one(run, "P-U-SALES-COPY", order, dept_root=_dept(tmp_path),
                            phase_obj=Phase(), worker_id="test")
    assert result.status == "ok", result.reasons
    assert (run / "working/upsell/copy/sales.fragment.md").read_text().startswith("# Sales")
    assert json.loads((run / "working/upsell/copy/copy_ledger.json").read_text())["version"] == 1


def test_multi_artifact_dispatch_refuses_missing_sibling_without_writing(tmp_path, monkeypatch):
    run = tmp_path / "run"
    (run / "working/work-orders").mkdir(parents=True)
    monkeypatch.setattr(d, "_verify", _verify)
    monkeypatch.setattr(
        d, "dispatch_complete",
        lambda *args, **kwargs: (json.dumps({"artifacts": {
            "working/upsell/copy/sales.fragment.md": "# Sales\nOnly one file.",
        }}), {"request_id": "stub"}, {"provider": "stub", "model": "stub-1"}),
    )
    order = {"phase": "P-U-SALES-COPY", "owning_role": "writer",
             "produces_artifact": Phase.resolve_artifact_patterns(run)}
    result = d.dispatch_one(run, "P-U-SALES-COPY", order, dept_root=_dept(tmp_path),
                            phase_obj=Phase(), worker_id="test")
    assert result.status == "exhausted"
    assert not (run / "working/upsell/copy/sales.fragment.md").exists()
    assert not (run / "working/upsell/copy/copy_ledger.json").exists()


def test_concrete_targets_reject_escape_absolute_duplicate_and_symlink_escape(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (run / "linked").symlink_to(outside, target_is_directory=True)

    assert d._concrete_target_paths(["../outside/escape.md"], run) is None
    assert d._concrete_target_paths([str(outside / "absolute.md")], run) is None
    assert d._concrete_target_paths(["copy/a.md", "./copy/a.md"], run) is None
    assert d._concrete_target_paths(["linked/escape.md"], run) is None


def test_group_publication_rolls_back_when_second_replace_fails(tmp_path, monkeypatch):
    first = tmp_path / "first.md"
    second = tmp_path / "second.json"
    first.write_text("old first")
    second.write_text("old second")
    first_tmp = tmp_path / "first.partial"
    second_tmp = tmp_path / "second.partial"
    first_tmp.write_text("new first")
    second_tmp.write_text("new second")

    real_replace = d.os.replace
    calls = {"count": 0}

    def fail_second(source, destination):
        calls["count"] += 1
        if calls["count"] == 2:
            raise OSError("injected second sibling failure")
        return real_replace(source, destination)

    monkeypatch.setattr(d.os, "replace", fail_second)
    error = d._publish_artifact_group({first: first_tmp, second: second_tmp})

    assert error and "publication failed" in error
    assert first.read_text() == "old first"
    assert second.read_text() == "old second"
    assert not first_tmp.exists()
    assert not second_tmp.exists()
    assert not list(tmp_path.glob("*.publish-backup-*"))

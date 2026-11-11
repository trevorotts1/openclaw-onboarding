"""S44-33: the schedule emit_launch_schedule.py writes is the one the launch QC (WF-9) accepts.

The emitter reads the plan reader's document; the QC compares against the workflow the launch compiler
actually built. This test compiles a real automation-build document with compile_launch_builds, exports it
the way `caf workflows export` would, and runs qc-built-workflow.sh's WF-9 against the emitted schedule.

Mock-only: a stub `caf` supplies the export. Run:
    python3 -m pytest 44-convert-and-flow-operator/tools/engine/tests/test_launch_schedule_matches_compiler.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parents[1]
SKILL = ENGINE.parents[1]
sys.path.insert(0, str(ENGINE))

from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402

LAUNCH_C = SKILL / "automation-templates" / "launch-c"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# Ruling INT-T-2: the surviving emitter is WP-06b's, which reads the compiled graph. The documents come from the
# engine's own ready-to-build synthetic launch (the reader now blocks WP-07's hand-made plan: lifecycle, eligibility,
# sender and guards are required). Assertions are unchanged: accepted for the compiled workflow, refused for a
# duration wait where a date was compiled.
emitter = _load("emit_launch_schedule_06b", LAUNCH_C / "emit_launch_schedule.py")
_l07 = _load("sched_match_l07", ENGINE / "tests" / "test_workflow_builder_l07.py")


class helpers:  # noqa: N801 - the name the assertions below already use
    @staticmethod
    def compile_unit(unit, *_ignored):
        return None, _l07.synthetic_document()


def _wf9(tmp_path, document, schedule, unit):
    """WF-9 status from qc-built-workflow.sh for the workflow the compiler built from `document`."""
    campaign = wb.compile_launch_builds(document, require_ready=True)
    workflow = next(v for v in campaign.values() if v["source_unit"] == unit)
    export = {"id": "WFTEST001", "name": "ZHC-test", "status": "draft", "allowMultiple": False, "active": False,
              "workflowData": {"templates": workflow["templates"]}}
    tree = tmp_path / "tree"
    skill = tree / "44-convert-and-flow-operator"
    skill.mkdir(parents=True)
    shutil.copy2(SKILL / "qc-built-workflow.sh", skill / "qc-built-workflow.sh")
    (skill / "tools").symlink_to(SKILL / "tools")
    (skill / "automation-templates").symlink_to(SKILL / "automation-templates")
    (tmp_path / "bin").mkdir()
    caf = tmp_path / "bin" / "caf"
    caf.write_text('#!/usr/bin/env bash\nwhile [ $# -gt 0 ]; do [ "$1" = "--out" ] && { cp "$QC_TEST_EXPORT" "$2"; exit 0; }; shift; done\nexit 1\n')
    caf.chmod(0o755)
    (tmp_path / "export.json").write_text(json.dumps(export))
    (tmp_path / "schedule.json").write_text(json.dumps(schedule))
    (tmp_path / "deps.json").write_text("{}")
    env = {"PATH": str(tmp_path / "bin") + os.pathsep + os.environ["PATH"], "HOME": str(tmp_path / "home"),
           "OPENCLAW_PLATFORM": "mac", "QC_TEST_EXPORT": str(tmp_path / "export.json")}
    result = subprocess.run(
        ["bash", str(skill / "qc-built-workflow.sh"), "WFTEST001", "--deps", str(tmp_path / "deps.json"), "--json",
         "--launch", "--launch-schedule", str(tmp_path / "schedule.json")],
        env=env, capture_output=True, text=True, timeout=60, check=False)
    text = result.stdout
    items = json.loads(text[text.index("{"):text.rindex("}") + 1])["items"]
    return items["WF-9"]


@pytest.mark.parametrize("kind", ["auto_pre_launch"])  # the other synthetic unit compiles no waits; the emitter refuses it (NO-WAITS)
def test_emitted_schedule_is_accepted_by_wf9_for_the_compiled_workflow(tmp_path, kind):
    _tmp, document = helpers.compile_unit(kind)
    waits = emitter.emit(document, kind)["waits"]
    item = _wf9(tmp_path, document, {"waits": waits}, kind)
    assert item["status"] == "PASS", item


def test_a_duration_wait_where_a_date_was_compiled_fails_wf9(tmp_path):
    _tmp, document = helpers.compile_unit("auto_pre_launch")
    wrong = {"waits": [{"kind": "delay", "value": 1, "unit": "days"}] * 3}
    assert _wf9(tmp_path, document, wrong, "auto_pre_launch")["status"] == "FAIL"

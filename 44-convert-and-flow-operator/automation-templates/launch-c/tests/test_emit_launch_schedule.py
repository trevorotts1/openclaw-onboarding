"""Issue 33: the WF-9 launch-schedule file has a producer.

Fail-before: nothing produced the {"waits": [...]} file `qc-built-workflow.sh --launch-schedule`
compares, and the reader's schedule.nodes is a different shape, so WF-9 could not pass on a launch
build. Pass-after: emit_launch_schedule.py converts one unit and the REAL WF-9 comparator (extracted
from qc-built-workflow.sh) passes it against the compiled graph and fails a mismatch.

Run: python3 -m pytest 44-convert-and-flow-operator/automation-templates/launch-c/tests/test_emit_launch_schedule.py -q
"""
import copy
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
LAUNCH_C = HERE.parent
SKILL = LAUNCH_C.parents[1]
ENGINE = SKILL / "tools" / "engine"
QC = SKILL / "qc-built-workflow.sh"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


emit = _load("emit_launch_schedule", LAUNCH_C / "emit_launch_schedule.py")
sys.path.insert(0, str(ENGINE))
_l07 = _load("emit_sched_l07", ENGINE / "tests" / "test_workflow_builder_l07.py")
from cli_anything.gohighlevel.utils import workflow_builder as wb  # noqa: E402


def _comparator():
    """The WF-9 python exactly as qc-built-workflow.sh runs it."""
    text = QC.read_text(encoding="utf-8")
    return re.search(r"<<'WF9PY' 2>/dev/null \|\| echo[^\n]*\n(.*?)\nWF9PY\n", text, re.S).group(1)


def _wf9(tmp_path, document, unit, schedule):
    """Run the real WF-9 comparison of `schedule` against the unit's compiled graph."""
    campaign = wb.compile_launch_builds(document)
    steps = next(v for v in campaign.values() if v["source_unit"] == unit)["templates"]
    export = tmp_path / "export.json"
    export.write_text(json.dumps({"workflowData": {"templates": steps}}))
    sched = tmp_path / "schedule.json"
    sched.write_text(json.dumps(schedule))
    done = subprocess.run([sys.executable, "-I", "-", str(export), str(sched)],
                          input=_comparator(), capture_output=True, text=True)
    return done.stdout.strip()


@pytest.fixture(scope="module")
def document():
    return _l07.synthetic_document()


def test_emits_the_shape_wf9_reads_and_wf9_passes_it(tmp_path, document):
    out = tmp_path / "schedule.json"
    rc = emit.main(["--automation-build", _write(tmp_path, document), "--unit", "auto_pre_launch",
                    "--out", str(out)])
    assert rc == 0
    schedule = json.loads(out.read_text())
    assert set(schedule) == {"waits"} and schedule["waits"]
    kinds = {w["kind"] for w in schedule["waits"]}
    assert kinds <= {"until_date", "delay"} and "until_date" in kinds  # pre-launch is date-anchored
    for w in schedule["waits"]:
        if w["kind"] == "until_date":
            assert re.search(r"[+-]\d\d:\d\d$|Z$", w["until"])
        else:
            assert w["unit"] in ("minutes", "hours", "days") and isinstance(w["value"], int)
    assert _wf9(tmp_path, document, "auto_pre_launch", schedule).startswith("PASS|")


def test_a_mismatched_schedule_fails_wf9_so_the_gate_is_real(tmp_path, document):
    schedule = emit.emit(document, "auto_pre_launch")
    wrong = copy.deepcopy(schedule)
    first_date = next(w for w in wrong["waits"] if w["kind"] == "until_date")
    first_date.clear()
    first_date.update({"kind": "delay", "value": 2, "unit": "days"})  # a date built as a duration
    assert _wf9(tmp_path, document, "auto_pre_launch", wrong).startswith("FAIL|")
    assert _wf9(tmp_path, document, "auto_pre_launch", {"waits": []}).startswith("FAIL|")


def test_the_reader_schedule_nodes_are_not_the_wf9_shape(document):
    build = next(b for b in document["builds"] if b["id"] == "auto_pre_launch")
    assert "waits" not in build["schedule"] and build["schedule"]["nodes"]


def test_unknown_unit_blocked_unit_and_ambiguous_workflow_refuse(tmp_path, document):
    assert emit.main(["--automation-build", _write(tmp_path, document), "--unit", "nope",
                      "--out", str(tmp_path / "o.json")]) == 2
    blocked = copy.deepcopy(document)
    next(b for b in blocked["builds"] if b["id"] == "auto_pre_launch").update(
        state="blocked", blocked_by=["email_count:email_pre_launch"])
    assert emit.main(["--automation-build", _write(tmp_path, blocked, "b.json"),
                      "--unit", "auto_pre_launch", "--out", str(tmp_path / "o2.json")]) == 4
    assert not (tmp_path / "o2.json").exists()
    with pytest.raises(emit.EmitError) as err:
        emit.emit(document, "auto_pre_launch", workflow_key="not_a_key")
    assert "WORKFLOW-UNKNOWN" in str(err.value)


def test_a_unit_that_compiles_no_wait_step_refuses_with_no_waits(tmp_path, document):
    # auto_post_sale compiles to a workflow with no wait step: WF-9 refuses an empty schedule,
    # so the emitter must refuse (exit 2) instead of writing {"waits": []}.
    with pytest.raises(emit.EmitError) as err:
        emit.emit(document, "auto_post_sale")
    assert "NO-WAITS" in str(err.value) and err.value.exit_code == 2
    out = tmp_path / "o.json"
    assert emit.main(["--automation-build", _write(tmp_path, document), "--unit", "auto_post_sale",
                      "--out", str(out)]) == 2
    assert not out.exists()


def test_a_blank_wait_date_is_a_wait_with_no_resolved_date_not_a_malformed_one():
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry({"id": "w", "type": "wait", "attributes": {"untilDate": "   "}}, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value) and "has no resolved date" in str(err.value)


def test_an_unresolved_wait_refuses_instead_of_guessing():
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry({"id": "w", "type": "wait", "attributes": {"type": "until_date",
                                                                    "untilDate": None}}, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value)
    with pytest.raises(emit.EmitError):
        emit._wait_entry({"id": "w", "type": "wait", "attributes": {
            "startAfter": {"type": "weeks", "value": 1}}}, "wf")


def _write(tmp_path, document, name="automation-builds.json"):
    path = tmp_path / name
    path.write_text(json.dumps(document))
    return str(path)


# ---- one test per enforcement line of the emitter ------------------------------------------------

@pytest.mark.parametrize("value", [-1, 1.5, True, "abc"])
def test_a_delay_value_that_is_not_a_non_negative_whole_number_refuses(value):
    # One case per clause of the guard: -1 (value < 0), 1.5 and "abc" (isinstance int), True (bool).
    step = {"id": "w", "type": "wait", "attributes": {"startAfter": {"type": "hours", "value": value}}}
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry(step, "wf")
    assert "WAIT-UNSUPPORTED" in str(err.value)
    assert err.value.exit_code == 2
    step["attributes"]["startAfter"]["value"] = 0
    assert emit._wait_entry(step, "wf") == {"kind": "delay", "value": 0, "unit": "hours"}


def test_a_wait_date_with_no_utc_offset_refuses(tmp_path):
    attrs = {"untilDate": "2026-11-26T09:00:00"}  # a valid ISO date, but no zone: the instant is a guess
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry({"id": "w", "type": "wait", "attributes": attrs}, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value) and "no UTC offset" in str(err.value)
    assert err.value.exit_code == 2
    assert emit._wait_entry({"id": "w", "type": "wait", "attributes": {
        "untilDate": "2026-11-26T09:00:00-05:00"}}, "wf") == {
            "kind": "until_date", "until": "2026-11-26T09:00:00-05:00"}


def test_a_wait_date_that_is_not_iso_8601_refuses_with_exit_2_not_a_value_error():
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry({"id": "w", "type": "wait", "attributes": {"untilDate": "next tuesday"}}, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value) and "not ISO-8601" in str(err.value)
    assert err.value.exit_code == 2


def test_a_unit_that_is_not_ready_is_refused_as_blocked_before_any_other_check(tmp_path, document):
    # A not-ready build that also carries no workflows: only compile_launch_builds(require_ready=True)
    # names it BUILD-BLOCKED; with require_ready off the same unit is reported as NO-BUILDABLE-WORKFLOW.
    draft = copy.deepcopy(document)
    next(b for b in draft["builds"] if b["id"] == "auto_pre_launch").update(
        state="draft", blocked_by=[], workflows=[])
    out = tmp_path / "o.json"
    assert emit.main(["--automation-build", _write(tmp_path, draft), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 4
    assert not out.exists()
    with pytest.raises(emit.EmitError) as err:
        emit.emit(draft, "auto_pre_launch")
    assert "UNIT-BLOCKED: BUILD-BLOCKED" in str(err.value) and err.value.exit_code == 4


def test_a_unit_that_compiles_to_several_workflows_needs_a_workflow_key(tmp_path, document):
    several = copy.deepcopy(document)
    build = next(b for b in several["builds"] if b["id"] == "auto_pre_launch")
    second = copy.deepcopy(build["workflows"][0])
    second.update(key="second", name="second")
    build["workflows"].append(second)
    with pytest.raises(emit.EmitError) as err:
        emit.emit(several, "auto_pre_launch")
    assert "WORKFLOW-AMBIGUOUS" in str(err.value) and "compiles to 2 workflows" in str(err.value)
    out = tmp_path / "o.json"
    assert emit.main(["--automation-build", _write(tmp_path, several), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 2
    assert not out.exists()
    # naming the workflow resolves it: the refusal is about ambiguity, not about the document
    assert emit.emit(several, "auto_pre_launch", workflow_key="auto_pre_launch__email_pre_launch")["waits"]


def test_an_automation_build_that_cannot_be_read_exits_3_and_writes_nothing(tmp_path):
    out = tmp_path / "o.json"
    assert emit.main(["--automation-build", str(tmp_path / "no-such.json"), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 3
    junk = tmp_path / "junk.json"
    junk.write_text("not json")
    assert emit.main(["--automation-build", str(junk), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 3
    assert not out.exists()


def test_a_schedule_that_cannot_be_written_exits_3(tmp_path, document):
    out = tmp_path / "no-such-dir" / "o.json"
    assert emit.main(["--automation-build", _write(tmp_path, document), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 3
    assert not out.exists()


# ---- sweep round 1: unit names, delay units, input shapes, the command line -----------------------

@pytest.mark.parametrize("given,unit", [("minute", "minutes"), ("minutes", "minutes"), ("hour", "hours"),
                                        ("hours", "hours"), ("day", "days"), ("days", "days"),
                                        ("Hours", "hours")])
def test_every_wf9_delay_unit_is_spelled_the_way_wf9_reads_it(given, unit):
    step = {"id": "w", "type": "wait", "attributes": {"startAfter": {"type": given, "value": 3}}}
    assert emit._wait_entry(step, "wf") == {"kind": "delay", "value": 3, "unit": unit}


@pytest.mark.parametrize("start", [{"value": 3}, {"type": "hours"}, {}, "3 hours", None])
def test_a_start_after_without_both_a_type_and_a_value_is_an_unresolved_wait(start):
    step = {"id": "w", "type": "wait", "attributes": {"startAfter": start}}
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry(step, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value) and err.value.exit_code == 2


@pytest.mark.parametrize("step", [{"id": "w", "type": "wait"}, {"id": "w", "type": "wait", "attributes": None},
                                  {"id": "w", "type": "wait", "attributes": ["x"]}])
def test_a_wait_without_an_attributes_object_is_an_unresolved_wait_not_a_crash(step):
    with pytest.raises(emit.EmitError) as err:
        emit._wait_entry(step, "wf")
    assert "WAIT-UNRESOLVED" in str(err.value) and err.value.exit_code == 2


def test_an_unknown_unit_is_named_with_the_units_the_document_has(tmp_path, document):
    with pytest.raises(emit.EmitError) as err:
        emit.emit(document, "auto_nothing")
    assert "UNIT-UNKNOWN" in str(err.value) and "have: auto_post_sale, auto_pre_launch" in str(err.value)
    assert err.value.exit_code == 2
    assert emit.emit(document, "auto_pre_launch")["waits"]


def test_an_unknown_workflow_key_is_refused_with_the_keys_the_unit_has(document):
    with pytest.raises(emit.EmitError) as err:
        emit.emit(document, "auto_pre_launch", workflow_key="nope")
    assert "WORKFLOW-UNKNOWN" in str(err.value) and "auto_pre_launch__email_pre_launch" in str(err.value)
    assert err.value.exit_code == 2


def test_compiling_leaves_the_import_path_as_it_found_it(document):
    before = list(sys.path)
    emit.emit(document, "auto_pre_launch")
    assert sys.path == before


def test_an_engine_that_cannot_be_imported_is_an_io_refusal(tmp_path, document, monkeypatch):
    monkeypatch.setitem(sys.modules, "cli_anything.gohighlevel.utils.workflow_builder", None)
    with pytest.raises(emit.EmitError) as err:
        emit.emit(document, "auto_pre_launch")
    assert "ENGINE-MISSING" in str(err.value) and err.value.exit_code == 3
    out = tmp_path / "o.json"
    assert emit.main(["--automation-build", _write(tmp_path, document), "--unit", "auto_pre_launch",
                      "--out", str(out)]) == 3
    assert not out.exists()


@pytest.mark.parametrize("body", [[], None, 3])
def test_a_document_that_is_json_but_not_an_object_is_a_named_refusal_not_a_traceback(tmp_path, body):
    with pytest.raises(emit.EmitError) as err:
        emit.emit(body, "auto_pre_launch")
    assert "DOCUMENT-INVALID" in str(err.value) and err.value.exit_code == 2
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(body))
    rc, err_text = _cli("--automation-build", path, "--unit", "auto_pre_launch", "--out", tmp_path / "o.json")
    assert rc == 2 and "emit-launch-schedule: DOCUMENT-INVALID" in err_text
    assert "Traceback" not in err_text and not (tmp_path / "o.json").exists()


def test_a_document_whose_builds_is_null_names_the_unit_as_unknown_not_a_traceback(tmp_path):
    path = tmp_path / "doc.json"
    path.write_text(json.dumps({"builds": None}))
    rc, err_text = _cli("--automation-build", path, "--unit", "auto_pre_launch", "--out", tmp_path / "o.json")
    assert rc == 2 and "UNIT-UNKNOWN" in err_text and "Traceback" not in err_text


class _Campaign(dict):
    refusals = ()


def _fake_compile(monkeypatch, templates):
    campaign = _Campaign(wf={"source_unit": "u", "templates": templates})
    monkeypatch.setattr(emit, "_compile", lambda document: campaign)
    return {"builds": [{"id": "u"}]}


def test_a_compiled_workflow_with_null_templates_is_no_waits_not_a_traceback(monkeypatch):
    doc = _fake_compile(monkeypatch, None)
    with pytest.raises(emit.EmitError) as err:
        emit.emit(doc, "u")
    assert "NO-WAITS" in str(err.value) and err.value.exit_code == 2


def test_compiled_steps_that_are_not_objects_or_not_waits_are_skipped_not_a_traceback(monkeypatch):
    wait = {"id": "w", "type": "wait", "attributes": {"startAfter": {"type": "hours", "value": 2}}}
    doc = _fake_compile(monkeypatch, ["bare string", None, {"id": "e", "type": "email"},
                                      {"id": "t"}, wait])
    assert emit.emit(doc, "u") == {"waits": [{"kind": "delay", "value": 2, "unit": "hours"}]}
    doc = _fake_compile(monkeypatch, ["bare string", {"id": "e", "type": "email"}])
    with pytest.raises(emit.EmitError) as err:
        emit.emit(doc, "u")
    assert "NO-WAITS" in str(err.value)


def _cli(*args):
    done = subprocess.run([sys.executable, str(LAUNCH_C / "emit_launch_schedule.py"), *map(str, args)],
                          capture_output=True, text=True)
    return done.returncode, done.stderr


def test_the_command_line_needs_all_three_arguments_and_exits_with_the_documented_codes(tmp_path, document):
    build = _write(tmp_path, document)
    out = tmp_path / "o.json"
    full = ["--automation-build", build, "--unit", "auto_pre_launch", "--out", out]
    for drop in range(0, 6, 2):  # each required option left out in turn
        rc, err = _cli(*(full[:drop] + full[drop + 2:]))
        assert rc == 2 and "required" in err, (drop, err)
    assert not out.exists()
    rc, err = _cli("--automation-build", tmp_path / "absent.json", "--unit", "x", "--out", out)
    assert rc == 3 and "emit-launch-schedule: cannot read" in err
    rc, err = _cli("--automation-build", build, "--unit", "auto_nothing", "--out", out)
    assert rc == 2 and "emit-launch-schedule: UNIT-UNKNOWN" in err
    rc, err = _cli("--automation-build", build, "--unit", "auto_pre_launch",
                   "--out", tmp_path / "no-such-dir" / "o.json")
    assert rc == 3 and "emit-launch-schedule: IO:" in err
    assert _cli(*full) == (0, "")
    assert json.loads(out.read_text())["waits"]


# ---- cases ported from WP-07's emitter tests (ruling INT-T-2), re-baselined to this emitter's exact output ----
# WP-07's emitter re-derived the gating rules from the reader's schedule nodes; this one reads the compiled graph, so
# the gating rules themselves (absolute and dated and not suppressed, only emails, only this workflow) are the
# compiler's and are pinned in tools/engine/tests/test_launch_step_compiler.py. What is pinned here is what the
# emitter must do with the compiled result.

def _wait_step(i, **start_or_until):
    attrs = {"type": "time"}
    attrs.update(start_or_until)
    return {"id": "w%d" % i, "type": "wait", "name": "Wait", "attributes": attrs}


def _email_step(i):
    return {"id": "e%d" % i, "type": "email", "name": "Email", "attributes": {}}


def test_ported_absolute_and_relative_waits_pass_through_in_order_one_for_one(monkeypatch):
    # an absolute (dated) send is gated by a wait-until-date, a suppressed send keeps its duration wait
    steps = [_email_step(0), _wait_step(0, untilDate="2026-11-03T08:00:00-05:00"), _email_step(1),
             _wait_step(1, startAfter={"type": "hours", "value": 3, "when": "after"}), _email_step(2)]
    doc = _fake_compile(monkeypatch, steps)
    assert emit.emit(doc, "u") == {"waits": [{"kind": "until_date", "until": "2026-11-03T08:00:00-05:00"},
                                             {"kind": "delay", "value": 3, "unit": "hours"}]}


def test_ported_relative_phase_keeps_the_templates_own_delays(monkeypatch):
    steps = [_email_step(0), _wait_step(0, startAfter={"type": "days", "value": 1, "when": "after"}),
             _email_step(1), _wait_step(1, startAfter={"type": "hours", "value": 2, "when": "after"}), _email_step(2)]
    doc = _fake_compile(monkeypatch, steps)
    assert emit.emit(doc, "u")["waits"] == [{"kind": "delay", "value": 1, "unit": "days"},
                                            {"kind": "delay", "value": 2, "unit": "hours"}]


def test_ported_trailing_duration_waits_after_the_last_email_are_emitted(monkeypatch):
    steps = [_email_step(0), _wait_step(0, startAfter={"type": "days", "value": 1, "when": "after"}), _email_step(1),
             _wait_step(1, startAfter={"type": "days", "value": 3, "when": "after"})]
    doc = _fake_compile(monkeypatch, steps)
    assert emit.emit(doc, "u")["waits"] == [{"kind": "delay", "value": 1, "unit": "days"},
                                            {"kind": "delay", "value": 3, "unit": "days"}]


def test_ported_waits_survive_steps_that_are_not_emails_and_junk_steps_are_skipped(monkeypatch):
    steps = ["junk", None, {"type": "add_contact_tag", "id": "t", "attributes": {"tags": []}}, _wait_step(0, startAfter={
        "type": "minutes", "value": 5, "when": "after"}), {"type": "sms", "id": "s", "attributes": {}}]
    doc = _fake_compile(monkeypatch, steps)
    assert emit.emit(doc, "u")["waits"] == [{"kind": "delay", "value": 5, "unit": "minutes"}]


def test_ported_a_z_date_is_accepted_and_written_trimmed(monkeypatch):
    doc = _fake_compile(monkeypatch, [_wait_step(0, untilDate=" 2026-12-01T09:00:00Z ")])
    assert emit.emit(doc, "u")["waits"] == [{"kind": "until_date", "until": "2026-12-01T09:00:00Z"}]


def test_ported_the_real_pre_launch_unit_emits_one_until_date_per_dated_wait_step(tmp_path, document):
    campaign = emit._compile(document)
    steps = next(v for v in campaign.values() if v["source_unit"] == "auto_pre_launch")["templates"]
    dated = [s for s in steps if s.get("type") == "wait" and s["attributes"].get("untilDate")]
    waits = emit.emit(document, "auto_pre_launch")["waits"]
    assert dated and [w["kind"] for w in waits].count("until_date") == len(dated)
    assert len(waits) == len([s for s in steps if s.get("type") == "wait"])


def test_ported_the_schedule_file_is_indented_by_two_ends_with_a_newline_and_prints_no_summary(tmp_path, document, capsys):
    out = tmp_path / "schedule.json"
    rc = emit.main(["--automation-build", _write(tmp_path, document), "--unit", "auto_pre_launch", "--out", str(out)])
    text = out.read_text(encoding="utf-8")
    assert rc == 0 and text == json.dumps(json.loads(text), indent=2) + "\n"
    assert capsys.readouterr().out == ""  # unlike WP-07's emitter this one prints no summary line on success

#!/usr/bin/env python3
"""FIX 11 -- ULTRA IS REACHABLE FROM THE HOSTED INTERVIEW APP, END TO END.

test_fix11_client_run_mode_path.py pins the AGENT-DRIVEN path: bank ->
deck-intake-driver.py -> presentation-intake-poll.sh -> the run-mode door. The
hosted interview app (presentations/intake/interview-app) is a THIRD intake
path -- a Cloudflare-hosted questionnaire whose answers are replayed onto the
box by bridge/intake_writer.py -- and it had NO run-mode handling anywhere.

Measured on pristine main with python3 whole-file scans (control: the literal
"intake", non-empty in each): bridge/intake_writer.py 525 lines, pages/
questions.json 15 questions, pages/index.html, payload/
build_questions_payload.py, bridge/intake_bridge.py and worker/src/*.js all
returned ZERO for run_mode / RUN_MODE / ultra / economy. So the app never asked,
and the ledger the writer produced carried no RUN_MODE key for read_run_mode()'s
first candidate. A hosted client's deck built STANDARD whatever they wanted,
and every surface reported success.

(What pristine main DID do, so this file does not overclaim: an INJECTED
run_mode answer -- one no client could produce, because nothing asked -- fell
through write_ledger's generic answer loop into entries["run_mode"] RAW.
Unnormalised, unvalidated, and copied into deck_brief too; "quick" and "turbo"
landed there unrefused. The canonical RUN_MODE key was never written.)

This file is the ACCEPTANCE proof for the hosted path. It does not hand-write a
ledger: it drives the REAL intake_writer, then runs the REAL poller over the
run dir that writer produced, and asserts what the dispatched process resolves.
The unit-level contract (vocabulary, refusals, record shape, bank parity) lives
next to the module it governs, in interview-app/test/test_intake_writer_run_mode.py.

NEVER ULTRA BY DEFAULT. The undeclared case asserts standard, and asserts that
NOTHING was passed to get there -- it is the launcher's own default answering,
not a guess made anywhere on this path.

Unit-level: no network, no spend, no deck, no render. Nothing here touches
presentation-canonical-entry.sh or tests/test_fix36_intake_depth.py, which own
the other direction of the two-axis guard.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from presentation_job import model_router  # noqa: E402

POLLER = SCRIPTS / "presentation-intake-poll.sh"
APP = SCRIPTS.parent / "intake" / "interview-app"
WRITER = APP / "bridge" / "intake_writer.py"

pytestmark = pytest.mark.skipif(
    not WRITER.is_file(), reason=f"hosted interview app writer not present at {WRITER}")


def _writer():
    if str(APP / "bridge") not in sys.path:
        sys.path.insert(0, str(APP / "bridge"))
    import intake_writer  # noqa: PLC0415
    return intake_writer


#: A complete hosted submission. presentation_type is mandatory: without it the
#: writer fails closed on the deck-type axis and never reaches the run mode.
_ANSWERS = {
    "presentation_type": "from_scratch",
    "offer_name": "The Momentum Method",
    "named_methodology": "The Three-Move Pipeline",
    "transformation_promise": "stuck -> closing",
    "time_to_result": "8 weeks",
    "audience": "women entrepreneurs, 35-55",
    "cta_action": "book a call",
    "tone": "Inspirational",
    "final_price": "$497",
    "speech_speed_preference": "default",
    "want_sales_checkout": "yes",
    "want_vsl_page": "no",
}

_ENGINE_STUB = '''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["SIM_RECORD_DIR"], "engine.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv,
                         "mode_env": os.environ.get("PRESENTATION_MODE")}) + "\\n")
if "--new" in sys.argv:
    rd = sys.argv[sys.argv.index("--run-dir") + 1]
    with open(os.path.join(rd, "state.json"), "w") as fh:
        json.dump({"terminal": "", "phase": "P0"}, fh)
'''

_LAUNCHER_STUB = '''#!/usr/bin/env python3
import json, os, sys
with open(os.path.join(os.environ["SIM_RECORD_DIR"], "launcher.jsonl"), "a") as fh:
    fh.write(json.dumps({"argv": sys.argv,
                         "mode_env": os.environ.get("PRESENTATION_MODE")}) + "\\n")
'''

_RESOLVE_STUB = '''#!/usr/bin/env python3
import json, sys
with open(sys.argv[sys.argv.index("--out") + 1], "w") as fh:
    json.dump({"presentation_type": "from_scratch"}, fh)
'''


def _hosted_run_dir(runs_root: Path, declared):
    """Build a run dir the way a real hosted submission does: through the app's
    OWN writer. No fixture ledger -- if the writer stops persisting the mode,
    these tests fail, which is the entire point."""
    iw = _writer()
    answers = dict(_ANSWERS)
    if declared is not None:
        answers["run_mode"] = declared
    run_dir = runs_root / "pres-hosted-0001"
    run_dir.mkdir(parents=True, exist_ok=True)
    intake = iw.assemble_intake({"answers": answers}, run_id="pres-hosted-0001")
    iw.write_intake_file(run_dir, intake)
    iw.write_ledger(run_dir, intake)
    return run_dir


def _poller_rig(tmp_path, declared, parked):
    """test_fix11_client_run_mode_path.py's rig, fed by the hosted writer.

    model_router is the REAL one, so the poller validates whatever the writer
    persisted against the same authority active_mode() uses."""
    scripts = tmp_path / "rig"
    (scripts / "presentation_job").mkdir(parents=True)
    for name in ("__init__.py", "model_router.py", "launch_plan.py"):
        shutil.copy2(SCRIPTS / "presentation_job" / name,
                     scripts / "presentation_job" / name)
    (scripts / "presentation_job" / "launcher.py").write_text(_LAUNCHER_STUB)
    (scripts / "presentation_job" / "resolve_intake.py").write_text(_RESOLVE_STUB)
    (scripts / "presentation_job.py").write_text(_ENGINE_STUB)
    shutil.copy2(POLLER, scripts / POLLER.name)

    runs = tmp_path / "runs"
    run_dir = _hosted_run_dir(runs, declared)
    if parked:
        (run_dir / "state.json").write_text(
            json.dumps({"terminal": "", "engine_pid": ""}), encoding="utf-8")

    records = tmp_path / "records"
    records.mkdir()
    env = dict(os.environ)
    env["HOME"] = str(tmp_path / "home")
    (tmp_path / "home" / "Library" / "Logs" / "openclaw").mkdir(parents=True)
    env["PRESENTATION_RUNS_DIR"] = str(runs)
    env["SIM_RECORD_DIR"] = str(records)
    env.pop("PRESENTATION_MODE", None)
    proc = subprocess.run(["bash", str(scripts / POLLER.name)],
                          env=env, capture_output=True, text=True, timeout=300)
    got = {}
    for f in records.glob("*.jsonl"):
        got[f.stem] = [json.loads(line) for line in
                       f.read_text().splitlines() if line.strip()]
    return proc, got, run_dir


def _resolved(row):
    """What model_router.active_mode() answers for what this process got."""
    argv = row["argv"]
    explicit = (argv[argv.index("--mode") + 1] if "--mode" in argv else None)
    saved = os.environ.pop(model_router.MODE_ENV, None)
    if row.get("mode_env"):
        os.environ[model_router.MODE_ENV] = row["mode_env"]
    try:
        return model_router.active_mode(explicit, strict=False)
    finally:
        os.environ.pop(model_router.MODE_ENV, None)
        if saved is not None:
            os.environ[model_router.MODE_ENV] = saved


# ---------------------------------------------------------------------------
# 1. THE LEDGER THE HOSTED WRITER PRODUCES IS THE ONE THE POLLER READS
# ---------------------------------------------------------------------------
def test_the_hosted_writer_uses_the_drivers_ledger_key(tmp_path):
    """No second convention. The key, its spelling and its casing are
    deck-intake-driver._RUN_MODE_SUBFIELD's, which is what read_run_mode()'s
    first candidate looks for."""
    run_dir = _hosted_run_dir(tmp_path / "runs", "ultra")
    entries = json.loads(
        (run_dir / "working" / "interview" / "intake_ledger.json")
        .read_text(encoding="utf-8"))["entries"]
    assert entries["RUN_MODE"]["value"] == "ultra"
    assert entries["run_mode"]["value"] == "ultra"

    src = POLLER.read_text(encoding="utf-8")
    assert '("RUN_MODE", "run_mode")' in src, "the poller's candidate keys moved"


def test_the_hosted_vocabulary_is_the_routers(tmp_path):
    iw = _writer()
    assert tuple(iw.RUN_MODES) == tuple(model_router.MODES)
    assert iw.DEFAULT_RUN_MODE == model_router.DEFAULT_MODE == "standard"


# ---------------------------------------------------------------------------
# 2. END TO END -- a hosted client declaring ultra gets an ultra run
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("parked,process", [(False, "engine"), (True, "launcher")])
def test_declared_ultra_reaches_the_dispatched_process(tmp_path, parked, process):
    proc, got, _ = _poller_rig(tmp_path, "ultra", parked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = got.get(process) or []
    assert rows, f"{process} was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert _resolved(row) == "ultra", row


@pytest.mark.parametrize("declared,expected",
                         [("ultra", "ultra"), ("ULTRA", "ultra"),
                          ("Economy", "economy"), ("standard", "standard")])
def test_every_declaration_survives_the_whole_hosted_path(tmp_path, declared,
                                                          expected):
    """Case-insensitive in, normalised lowercase out -- all the way from the
    app's answer map to what the engine process resolves."""
    proc, got, _ = _poller_rig(tmp_path, declared, parked=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rows = got.get("engine") or []
    assert rows, f"engine was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert _resolved(row) == expected, row


@pytest.mark.parametrize("parked,process", [(False, "engine"), (True, "launcher")])
def test_undeclared_stays_standard_and_passes_nothing(tmp_path, parked, process):
    """Never ultra by default -- and NOTHING is handed over to get to standard,
    so it is the launcher's own default answering, not a guess made here."""
    proc, got, run_dir = _poller_rig(tmp_path, None, parked)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    entries = json.loads(
        (run_dir / "working" / "interview" / "intake_ledger.json")
        .read_text(encoding="utf-8"))["entries"]
    assert "RUN_MODE" not in entries, sorted(entries)
    rows = got.get(process) or []
    assert rows, f"{process} was never dispatched: {got} / {proc.stdout}"
    for row in rows:
        assert "--mode" not in row["argv"], row
        assert row.get("mode_env") is None, row
        assert _resolved(row) == "standard", row


def test_the_new_branch_records_the_hosted_declaration_with_its_provenance(
        tmp_path):
    """The --new branch does not go through the launcher, so the sidecar is the
    only after-the-fact answer to "which mode was this deck built in?"."""
    proc, _, run_dir = _poller_rig(tmp_path, "ultra", parked=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    rec_path = run_dir / ".mode-plan.json"
    assert rec_path.is_file(), f"no .mode-plan.json: {proc.stdout[-1500:]}"
    rec = json.loads(rec_path.read_text(encoding="utf-8"))
    assert rec["mode"] == "ultra"
    assert rec["declared"] is True
    assert rec["mode_source"] == "intake-slot", rec["mode_source"]


# ---------------------------------------------------------------------------
# 3. THE REFUSALS ARE REAL -- and they happen BEFORE anything is written
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("word", ["quick", "QUICK", "in-depth", "in_depth"])
def test_interview_depth_vocabulary_never_becomes_a_run_dir(tmp_path, word):
    """The mirror image of test_fix36_intake_depth's guard, on the third path:
    that one refuses the run-mode words on --intake-depth; the hosted writer
    refuses the interview-depth words in the run-mode slot, naming BOTH axes.
    Fail-closed, so no run dir exists at all for the poller to find."""
    iw = _writer()
    runs = tmp_path / "runs"
    with pytest.raises(iw.RunModeVocabularyError) as exc:
        _hosted_run_dir(runs, word)
    msg = str(exc.value)
    assert "ultra|standard|economy" in msg
    assert "quick|in-depth" in msg
    assert "never interchangeable" in msg
    assert not (runs / "pres-hosted-0001" / "working" / "interview"
                / "intake_ledger.json").exists()


def test_garbage_is_refused_never_coerced(tmp_path):
    iw = _writer()
    runs = tmp_path / "runs"
    with pytest.raises(iw.RunModeVocabularyError) as exc:
        _hosted_run_dir(runs, "banana")
    assert "banana" in str(exc.value)
    assert "run_mode" in str(exc.value)
    assert not (runs / "pres-hosted-0001" / "working").exists()


def test_a_run_mode_is_never_deck_content(tmp_path):
    """The bank's run_mode subfield: "a run mode is an execution axis, not deck
    content, so it stays out of working/copy/intake.json's deck_brief"."""
    run_dir = _hosted_run_dir(tmp_path / "runs", "ultra")
    intake = json.loads((run_dir / "working" / "copy" / "intake.json")
                        .read_text(encoding="utf-8"))
    assert "RUN_MODE" not in (intake.get("deck_brief") or {})
    assert "run_mode" not in (intake.get("deck_brief") or {})
    assert intake["pre_presentation_capture"]["RUN_MODE"] == "ultra"

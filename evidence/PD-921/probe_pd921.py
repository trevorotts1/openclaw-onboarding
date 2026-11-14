#!/usr/bin/env python3
"""PD-921 proof probe.

Loads ONE phase_verifiers.py (path from PV_FILE) inside the real scripts dir,
then prints a deterministic transcript for three states:

  UNBOUND  _rf109 is None (the binding could not be loaded)
  BOUND    the real presentation_job.runfacts binding (bound run)
  DOOR     Engine._check_intake_provenance with the runfacts import sabotaged

Run against HEAD bytes and against the working-tree bytes; the BOUND sections
must be byte-identical (that is "bound run unchanged"), and the UNBOUND section
must differ (None/pass -> named refusal).
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

PV_FILE = os.environ["PV_FILE"]
SCRIPTS = Path(os.environ["SCRIPTS_DIR"]).resolve()
RUN_ROOT = Path(os.environ["RUN_ROOT"])

sys.path.insert(0, str(SCRIPTS))

spec = importlib.util.spec_from_file_location("phase_verifiers_probe", PV_FILE)
pv = importlib.util.module_from_spec(spec)
sys.modules["phase_verifiers_probe"] = pv
spec.loader.exec_module(pv)


def emit(label: str, value) -> None:
    print(f"{label}={value!r}")


def make_run() -> Path:
    run = RUN_ROOT / "run-1" / ("r%d" % (len(list(RUN_ROOT.glob("run-1/r*"))) if (RUN_ROOT / "run-1").exists() else 0))
    (run / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (run / "working" / "checkpoints").mkdir(parents=True, exist_ok=True)
    (run / "working" / "copy" / "intake.json").write_text('{"client": "C"}')
    man = run / "pinned" / "PIPELINE-MANIFEST.json"
    man.parent.mkdir(parents=True, exist_ok=True)
    man.write_text(json.dumps({"phases": [
        {"id": "P0A-INTAKE", "order": 0.1,
         "produces_artifact": ["working/copy/intake.json"], "consumes": []},
        {"id": "P4-COPY", "order": 4.0,
         "produces_artifact": ["working/copy/slide_copy.json"],
         "consumes": ["working/copy/intake.json"]},
    ]}))
    (run / "state.json").write_text(json.dumps({
        "job_id": run.name, "schema_version": 1, "phases": []}, indent=2))
    return run


# --------------------------------------------------------------------------
# UNBOUND — the binding could not be loaded
# --------------------------------------------------------------------------
run_unbound = make_run()
real_rf = pv._rf109
pv._rf109 = None
unbound_funnel_refusal = pv._intake_provenance_refusal("P4-COPY", run_unbound)
print("== UNBOUND ==")
for pid in ("P4-COPY", "P0A-INTAKE", "P-CONVERTER"):
    emit(f"unbound.refusal[{pid}]", pv._intake_provenance_refusal(pid, run_unbound))
for pid in ("P4-COPY", "P0A-INTAKE"):
    ok, reasons = pv.verify(pid, run_unbound)
    emit(f"unbound.verify[{pid}]", (ok, reasons))

# --------------------------------------------------------------------------
# BOUND — a successfully bound run behaves exactly as before
# --------------------------------------------------------------------------
pv._rf109 = real_rf
assert pv._rf109 is not None, "bound probe requires the real runfacts binding"
print("== BOUND ==")
run_bound = make_run()
for pid in ("P4-COPY", "P0A-INTAKE", "P-CONVERTER"):
    emit(f"bound.refusal[{pid}]", pv._intake_provenance_refusal(pid, run_bound))
for pid in ("P4-COPY", "P0A-INTAKE"):
    ok, reasons = pv.verify(pid, run_bound)
    emit(f"bound.verify[{pid}]", (ok, reasons))

# --------------------------------------------------------------------------
# DOOR — the engine door refuses the same state with its own line
# --------------------------------------------------------------------------
print("== DOOR ==")
from presentation_job.phases import Engine, _INTAKE_ARTIFACT  # noqa: E402
from presentation_job.state import StateStore  # noqa: E402
from presentation_job.manifest import Manifest  # noqa: E402

run_door = make_run()
man = Manifest(run_door / "pinned" / "PIPELINE-MANIFEST.json")
store = StateStore(run_door)
eng = Engine(run_door, man, store, store.load())
phase = man.phase_or_none("P4-COPY") or man.phases[1]

# Hiding the module from sys.modules is the only sabotage that covers BOTH the
# relative `from . import runfacts` and the bare `import runfacts` fallback.
# The package attribute must go too: `from . import x` resolves the parent's
# attribute FIRST when it exists, so sys.modules alone is a silent no-op.
import presentation_job  # noqa: E402

saved_mods = {}
for key in ("presentation_job.runfacts", "runfacts"):
    if key in sys.modules:
        saved_mods[key] = sys.modules[key]
        sys.modules[key] = None
saved_attr = getattr(presentation_job, "runfacts", None)
try:
    if saved_attr is not None:
        delattr(presentation_job, "runfacts")
    rc = eng._check_intake_provenance(phase)
finally:
    if saved_attr is not None:
        presentation_job.runfacts = saved_attr
    for key in ("presentation_job.runfacts", "runfacts"):
        if key in saved_mods:
            sys.modules[key] = saved_mods[key]
        else:
            sys.modules.pop(key, None)

door_reason = (store.load().get("blocked") or {}).get("reason")
emit("door.rc", rc)
emit("door.reason", door_reason)

funnel_unbound = unbound_funnel_refusal
print(f"agreement.funnel_refusal={funnel_unbound!r}")
if door_reason is None:
    print("agreement.startswith_door_reason=False  [door produced no reason]")
elif funnel_unbound is None:
    print("agreement.startswith_door_reason=False  [funnel returned None = pass]")
else:
    # The funnel's refusal must carry the door's exact line as its prefix.
    print(f"agreement.startswith_door_reason={funnel_unbound.startswith(door_reason)}")
print(f"agreement.both_name_AF={('AF-INTAKE-PROVENANCE' in (door_reason or '')) and ('AF-INTAKE-PROVENANCE' in (funnel_unbound or ''))}")
print(f"agreement.door_blocks={bool(door_reason)}")
print(f"agreement.funnel_refuses={funnel_unbound is not None}")

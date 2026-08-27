"""L-11 regression (Ticket 7, presentation department fix campaign, 2026-08-27):
P9.6-WEBINAR-VIDEO's executor.cmd must call build_webinar_video.py DIRECTLY,
never re-enter presentation-canonical-entry.sh.

THE DEFECT THIS FILE PROVES FIXED:

Every other "kind": "script" phase in PIPELINE-MANIFEST.json invokes its own
builder directly (e.g. P9.2-GHL-UPLOAD -> "python3 scripts/ghl_media_push.py
--run-dir {run_dir}"). P9.6-WEBINAR-VIDEO was instead wired to
"bash scripts/presentation-canonical-entry.sh --resume --run-dir {run_dir}" --
the TOP-LEVEL pipeline launcher, not its own builder (build_webinar_video.py).

That launcher's own dispatch (after its gates pass) execs a FRESH
`python3 presentation_job.py --run --run-dir {run_dir}` (presentation-
canonical-entry.sh's "Step 3: Run the engine" block). But the Engine that is
in the middle of DISPATCHING P9.6 is, by construction, still inside
`with RunLock(run_dir):` for the full duration of its own engine.run() call
(presentation_job/__main__.py:582) -- subprocess.run() blocks synchronously,
so that lock is never released while the child is executing. RunLock is a
non-blocking exclusive flock (presentation_job/state.py's RunLock.__enter__):
a second acquisition on the same run dir raises BlockingIOError and dies
immediately with EXIT_LOCK_HELD (state.py:148-168) -- dispatcher.py's own
module docstring independently documents this exact hazard ("a second process
attempting [RunLock] while the Engine is alive dies immediately with
EXIT_LOCK_HELD"). So the OLD executor.cmd could never succeed: every
dispatch of P9.6 relaunches an engine that is guaranteed to collide with its
own parent's still-held lock, retries HEAL_CAP_TRANSIENT (3) times identically,
then blocks the run at P9.6-WEBINAR-VIDEO every time.

The fix calls build_webinar_video.py directly, matching every sibling script
phase. This is safe: OC_DECK_ENTRY_NONCE is minted ONCE by the ORIGINAL
top-level canonical-entry.sh invocation and inherited by the whole descendant
process tree (engine -> this phase's subprocess -- no `env=` override
anywhere in that chain: phases.py's _run_script_phase / heal.py's
rung2_regenerate|rung3_alt_route, and process_reaper.run_with_cleanup's `env`
parameter defaults to None, meaning full inheritance), so
build_webinar_video.py's own _verify_entry_nonce() still passes exactly as it
does today for every already-direct script phase, and a genuinely hand-rolled
direct invocation still fails closed (AF-CANONICAL-RENDER-BYPASS) exactly as
before -- nothing about the nonce door itself changed.

UPDATE (same branch, follow-up): P8.25-WORKBOOK carried the IDENTICAL pre-fix
defect (same "bash scripts/presentation-canonical-entry.sh --resume --run-dir
{run_dir}" executor.cmd, same RunLock self-collision) -- it was flagged
out-of-scope for the original L-11 ticket (which named P9.6 only) and left
unfixed with a tripwire test. The team lead confirmed it is in campaign scope
(it blocks the workbook deliverable the same deterministic way P9.6 blocked
video) and asked for the identical mirror fix on this branch: P8.25-WORKBOOK's
executor.cmd now calls workbook_builder.py directly too. Verified before
wiring it: workbook_builder.py's own CLI contract (--run-dir required, or
--selftest) and its own _verify_entry_nonce() (workbook_builder.py:1262-1271)
are a near-exact structural mirror of build_webinar_video.py's -- same env
read, same --no-upload smoke-test exemption, same AF-CANONICAL-RENDER-BYPASS
fail-closed message -- so the identical env-inheritance safety argument
applies. Zero phases in the manifest now point at presentation-canonical-
entry.sh as a per-phase executor.

Flat file inside tests/, manages its own import path -- matching every
sibling in this directory (test_f16_agent_phase_wait_race.py, test_gates.py,
etc.).
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
from presentation_job.state import StateStore  # noqa: E402


def _canonical_manifest() -> Path:
    """Same resolution order as every sibling test file's own copy."""
    deployed = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
    if deployed.is_file():
        return deployed
    cur = SCRIPTS
    for _ in range(12):
        cand = cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if cand.is_file():
            return cand
        if cur.parent == cur:
            break
        cur = cur.parent
    raise FileNotFoundError("PIPELINE-MANIFEST.json not found")


def _manifest() -> Manifest:
    return Manifest(_canonical_manifest())


# ---------------------------------------------------------------------------
# 1. STATIC: P9.6's executor.cmd must never again point at the top-level
#    launcher -- that shape is exactly the regression this test exists to
#    catch, regardless of how it might be reworded (bash vs sh, absolute vs
#    relative path, extra flags).
# ---------------------------------------------------------------------------
def test_p96_webinar_executor_does_not_reenter_canonical_entry():
    phase = _manifest().phase("P9.6-WEBINAR-VIDEO")
    assert phase.executor_kind == "script"
    assert "presentation-canonical-entry.sh" not in (phase.executor_cmd or ""), (
        "P9.6-WEBINAR-VIDEO's executor must not re-invoke the top-level launcher -- "
        "doing so relaunches a full engine (`python3 presentation_job.py --run`) "
        "while the dispatching Engine still holds RunLock on the same run dir, "
        "which always dies with EXIT_LOCK_HELD. See this file's module docstring."
    )


def test_p96_webinar_executor_calls_build_webinar_video_directly():
    phase = _manifest().phase("P9.6-WEBINAR-VIDEO")
    assert phase.executor_cmd == "python3 scripts/build_webinar_video.py --run-dir {run_dir}", (
        f"unexpected executor.cmd for P9.6-WEBINAR-VIDEO: {phase.executor_cmd!r} -- "
        "expected a direct call to its own builder, matching every sibling "
        "script-kind phase in this manifest (e.g. P9.2-GHL-UPLOAD)"
    )


# ---------------------------------------------------------------------------
# 2. DYNAMIC: the Engine's own argv-builder must resolve that cmd to a direct
#    python3 invocation of build_webinar_video.py under the real scripts dir
#    -- proving what actually gets exec'd, not just what the manifest string
#    says.
# ---------------------------------------------------------------------------
def test_engine_resolves_p96_argv_to_direct_script_invocation(tmp_path):
    manifest = _manifest()
    phase = manifest.phase("P9.6-WEBINAR-VIDEO")
    rd = tmp_path / "run"
    rd.mkdir()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "manifest_path": str(manifest.path), "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256, "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "events": [], "sent": {}, "heartbeat": {},
    }
    eng = Engine(rd, manifest, store, state, dry_run=True)

    argv = eng._build_executor_argv(phase.executor_cmd, phase.id)

    assert argv[0] == "python3"
    assert Path(argv[1]).name == "build_webinar_video.py", (
        f"expected build_webinar_video.py as the resolved script, got argv={argv!r}")
    assert "presentation-canonical-entry.sh" not in " ".join(argv)
    assert "--run-dir" in argv and str(rd) in argv


# ---------------------------------------------------------------------------
# 3. P8.25-WORKBOOK mirror fix (same branch, follow-up): the identical twin
#    defect, now fixed the identical way. Mirrors tests 1+2 above exactly --
#    formerly a tripwire documenting this as unfixed; now a positive proof.
# ---------------------------------------------------------------------------
def test_p825_workbook_executor_does_not_reenter_canonical_entry():
    phase = _manifest().phase("P8.25-WORKBOOK")
    assert phase.executor_kind == "script"
    assert "presentation-canonical-entry.sh" not in (phase.executor_cmd or ""), (
        "P8.25-WORKBOOK's executor must not re-invoke the top-level launcher -- "
        "the same RunLock self-collision fixed for P9.6-WEBINAR-VIDEO applies "
        "identically here. See this file's module docstring."
    )


def test_p825_workbook_executor_calls_workbook_builder_directly():
    phase = _manifest().phase("P8.25-WORKBOOK")
    assert phase.executor_cmd == "python3 scripts/workbook_builder.py --run-dir {run_dir}", (
        f"unexpected executor.cmd for P8.25-WORKBOOK: {phase.executor_cmd!r} -- "
        "expected a direct call to its own builder, matching every sibling "
        "script-kind phase in this manifest"
    )


def test_engine_resolves_p825_argv_to_direct_script_invocation(tmp_path):
    manifest = _manifest()
    phase = manifest.phase("P8.25-WORKBOOK")
    rd = tmp_path / "run"
    rd.mkdir()
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "manifest_path": str(manifest.path), "manifest_version": manifest.version,
        "manifest_sha256": manifest.sha256, "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "events": [], "sent": {}, "heartbeat": {},
    }
    eng = Engine(rd, manifest, store, state, dry_run=True)

    argv = eng._build_executor_argv(phase.executor_cmd, phase.id)

    assert argv[0] == "python3"
    assert Path(argv[1]).name == "workbook_builder.py", (
        f"expected workbook_builder.py as the resolved script, got argv={argv!r}")
    assert "presentation-canonical-entry.sh" not in " ".join(argv)
    assert "--run-dir" in argv and str(rd) in argv


# ---------------------------------------------------------------------------
# 4. Repo-wide guard: no phase's executor.cmd may re-enter the top-level
#    launcher, full stop -- catches a THIRD phase being wired this way in
#    the future, not just P9.6/P8.25 by name.
# ---------------------------------------------------------------------------
def test_no_manifest_phase_reenters_canonical_entry():
    offenders = [p.id for p in _manifest().phases
                 if "presentation-canonical-entry.sh" in (p.executor_cmd or "")]
    assert not offenders, (
        f"phase(s) {offenders} re-invoke presentation-canonical-entry.sh as a "
        "per-phase executor -- this always self-collides on RunLock (see this "
        "file's module docstring). Every script-kind phase must call its own "
        "builder directly."
    )

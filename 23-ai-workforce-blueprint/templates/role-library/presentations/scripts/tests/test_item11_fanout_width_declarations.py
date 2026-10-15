#!/usr/bin/env python3
"""test_item11_fanout_width_declarations.py -- FIX-PLAN Item 11 (B23):
fanout widths are declared, and an undeclared width is LOUD, not silent.

THE TRAP (Reader E finding F6, FIX-PLAN Item 11). `Phase.workers` defaults
to 1 when the manifest omits the key, and eight of the nine fanout phases in
the shipped manifest omitted it. On P4-PROMPT's own pool path that default
is a hard serial cap (dispatcher branches on `phase.workers <= 1` into the
literal serial loop); everywhere else the undeclared state was invisible:
nothing at manifest load, nothing in the run record, nothing in sync_check
said "this phase has no declared width". A serial pocket inside a parallel
pipeline, with no signal.

THE FIX (manifest v71).
  1. Every fanout phase in the shipped manifest declares `workers`. The
     declared value is the phase's OWN fanout batch_width, the width the
     phase already declares for its batches (the P4-PROMPT precedent:
     workers 12 == batch_width 12). A declared width is a per-phase ceiling
     inside fanout.resolve_effective_workers: measured capacity and the
     unit count still bind below it, so no machine-specific number is
     burned into the manifest.
  2. P9-SPEECH declares an explicit `workers: 1`: a stated decision, not an
     omission. Its manifest executor is a SCRIPT (the speech harness), the
     generic unit path never executes for it, and the preflight refuses its
     fanout declaration; the document is produced by one harness invocation.
  3. The fallback stays 1 for any manifest that has not declared yet (no
     run changes behavior), but it is LOUD: Manifest.load prints a WARN
     line naming the phase, sync_check reports it as a W2 advisory, and
     cmd_new stamps the warnings into the run record (state.json
     fanout_width_warnings). (Item 16 later promoted the sync_check W2
     advisory to a drift failure; see the update note below.)

WHAT THESE TESTS PROVE, AND HOW THEY FAIL ON PRISTINE ea22ed88:
  1. the shipped manifest declares workers on every fanout phase, at the
     phase's own batch_width (P9-SPEECH: explicit 1) -- pristine declares
     only P4-PROMPT, and Manifest has no fanout_width_warnings at all.
  2. a synthetic fanout phase with no workers key (or a null one) loads
     WITHOUT refusal, falls back to workers == 1, and is named in
     Manifest.fanout_width_warnings and on stderr by Manifest.load --
     pristine has neither attribute nor warning.
  3. a fanout phase declaring workers: 1 on purpose does NOT warn (a stated
     serial decision is not an omission).
  4. sync_check flags the same condition as W2 by name (as built by
     Item 11: warn_checks, advisory; as promoted by Item 16: run_checks,
     drift) -- pristine warn_checks has no W2 class.
  5. a declared width resolves at dispatch: resolve_effective_workers
     returns the declared width when units and capacity allow, the unit
     count when fewer units exist, and the capacity when capacity binds
     below the declaration (the declaration is a ceiling, not a promise).
  6. cmd_new's run record carries fanout_width_warnings: naming the phase
     for a manifest copy with one declaration removed, empty for the
     shipped manifest.

NO NETWORK, NO MODEL SPEND. The cmd_new test runs the real creation path
against a scratch copy of the shipped manifest (version and phase count
intact, so the manifest-currency gate passes) in a tmp run dir.

ITEM 16 UPDATE (the promotion this suite's section 4 now asserts): W2 moved
from sync_check.warn_checks (advisory warnings list, never an exit code) to
sync_check.run_checks (drift list, class render_path): an undeclared fanout
width now fails the drift gate, and phases.py refuses it at plan time
(Engine._refuse_undeclared_fanout_widths, pinned in test_f6_fanout_width.py
section 7). Points 2 and 6 above are unchanged: Manifest.load still does
not refuse, and the run record still carries the warnings; the refusal
lives at the gate and at plan time.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

CLUSTER_MANIFEST = (
    SCRIPTS.parent.parent.parent.parent.parent
    / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
)

# The nine fanout phases of the shipped manifest and their declared widths
# (Item 11: workers == the phase's own fanout batch_width, except P9-SPEECH,
# deliberately serial at an explicit 1).
EXPECTED_WIDTHS = {
    "P4-COPY": 5,
    "P-U-DESIGN-SALES": 3,
    "P-U-DESIGN-CHECKOUT": 3,
    "P-U-DESIGN-VSL": 3,
    "P4-PROMPT": 12,
    "P-PROMPT-QC": 12,
    "P-STYLE-SPEC": 3,
    "P-IMAGE-QC": 12,
    "P9-SPEECH": 1,
}


def _canonical() -> Path:
    if CLUSTER_MANIFEST.is_file():
        return CLUSTER_MANIFEST
    pytest.skip("PIPELINE-MANIFEST.json not found from this checkout root")


def _write_manifest(tmp_path: Path, phases: list) -> Path:
    data = {"manifest_version": 1, "phases": phases, "autofails": [], "roles": []}
    path = tmp_path / "PIPELINE-MANIFEST.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _base_phase(**overrides) -> dict:
    phase = {
        "id": "P-TEST",
        "order": 1.0,
        "owning_role": "test-role",
        "produces_artifact": "working/x.txt",
        "executor": {"kind": "agent"},
        "verifier": "phase_verifiers.verify",
    }
    phase.update(overrides)
    return phase


# ---------------------------------------------------------------------------
# 1 + 2 (shipped side). The drift gate over the canonical manifest: every
# fanout phase declares workers, at its own batch_width.
# ---------------------------------------------------------------------------
def test_canonical_manifest_every_fanout_phase_declares_workers():
    from presentation_job.manifest import Manifest
    m = Manifest(_canonical())
    fanout_phases = [p for p in m.phases if p.fanout is not None]
    assert {p.id for p in fanout_phases} == set(EXPECTED_WIDTHS), (
        "the fanout phase set changed; update EXPECTED_WIDTHS with per-phase "
        "verdicts, do not let a fanout phase ship undeclared")
    undeclared = [p.id for p in fanout_phases if not p.workers_declared]
    assert undeclared == [], (
        f"fanout phases declaring no workers: {undeclared}. Item 11: declare "
        f"the width (the phase's own fanout batch_width), or declare an "
        f"explicit workers: 1 with a recorded deliberate-serial verdict")
    assert m.fanout_width_warnings == [], m.fanout_width_warnings


def test_canonical_declared_widths_match_the_phase_own_batch_width():
    from presentation_job.manifest import Manifest
    m = Manifest(_canonical())
    for pid, expected in EXPECTED_WIDTHS.items():
        phase = m.phase(pid)
        assert phase.workers == expected, (
            f"{pid}: declared workers {phase.workers} != expected {expected}")
        if pid == "P9-SPEECH":
            continue  # deliberate serial: explicit 1, batch_width stays 12
        assert phase.workers == phase.fanout["batch_width"], (
            f"{pid}: workers {phase.workers} is not the phase's own fanout "
            f"batch_width {phase.fanout['batch_width']}; the declaration rule "
            f"is the phase's own declared batch width, never an invented "
            f"machine-specific number")


# ---------------------------------------------------------------------------
# 2 + 3 (synthetic side). Undeclared is loud and non-fatal; declared serial
# is silent.
# ---------------------------------------------------------------------------
def test_undeclared_fanout_warns_by_name_and_falls_back_to_one(tmp_path, capsys):
    from presentation_job.manifest import Manifest
    path = _write_manifest(tmp_path, [
        _base_phase(id="P-FAN", fanout={"by": "slide", "batch_width": 4}),
        _base_phase(id="P-PLAIN", order=2.0, produces_artifact="working/y.txt"),
    ])
    m = Manifest.load(path)  # must NOT raise: the fallback stays usable
    fan = m.phase("P-FAN")
    assert fan.workers == 1, "the effective fallback stays 1"
    assert fan.workers_declared is False
    assert len(m.fanout_width_warnings) == 1, m.fanout_width_warnings
    assert "P-FAN" in m.fanout_width_warnings[0]
    err = capsys.readouterr().err
    assert "WARN:" in err and "P-FAN" in err, (
        f"Manifest.load printed no load-time warning naming the phase: {err!r}")
    assert "P-PLAIN" not in err


def test_null_workers_counts_as_undeclared(tmp_path, capsys):
    from presentation_job.manifest import Manifest
    path = _write_manifest(tmp_path, [
        _base_phase(id="P-FAN", workers=None,
                    fanout={"by": "slide", "batch_width": 4}),
    ])
    m = Manifest.load(path)
    assert m.phase("P-FAN").workers == 1
    assert [w for w in m.fanout_width_warnings if "P-FAN" in w], (
        "a null workers key is an omission (the parser treats it as absent), "
        "so it must warn like one")


def test_declared_serial_workers_one_does_not_warn(tmp_path, capsys):
    from presentation_job.manifest import Manifest
    path = _write_manifest(tmp_path, [
        _base_phase(id="P-SERIAL", workers=1,
                    fanout={"by": "slide", "batch_width": 12}),
    ])
    m = Manifest.load(path)
    assert m.phase("P-SERIAL").workers == 1
    assert m.phase("P-SERIAL").workers_declared is True
    assert m.fanout_width_warnings == [], (
        "an explicit workers: 1 is a stated serial decision (the P9-SPEECH "
        "shape), not an omission; it must not warn")
    assert "P-SERIAL" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 4. sync_check W2: the repo's own manifest checks flag it by name.
#    ITEM 16 UPDATE: W2 was promoted from warn_checks (advisory) to
#    run_checks (drift) by FIX-PLAN Item 16, so this section reads the
#    drift list now, and also pins that the advisory list no longer
#    carries W2.
# ---------------------------------------------------------------------------
def _sync_check_w2_drift(raw):
    """W2 entries in sync_check's DRIFT list for a raw manifest dict.

    run_checks needs the build-deck parse and the role/SOP scan that
    main() assembles; the empty ruleset-code set only quiets the ruleset
    cross-checks, which this suite does not judge."""
    import sync_check
    bd = sync_check.parse_build_deck()
    role_stems, sop_files = sync_check.scan_roles_and_sops()
    drift = sync_check.run_checks(raw, bd, set(), role_stems, sop_files)
    return [d for d in drift if d["check"] == "W2"]


def test_sync_check_w2_flags_undeclared_fanout_by_name():
    import sync_check
    raw = json.loads(_canonical().read_text(encoding="utf-8"))
    clean = _sync_check_w2_drift(raw)
    assert clean == [], (
        f"the shipped manifest must carry no W2 drift: {clean}")
    assert [w for w in sync_check.warn_checks(raw, set())
            if w["check"] == "W2"] == [], (
        "W2 left the advisory warnings list in FIX-PLAN Item 16")
    broken = copy.deepcopy(raw)
    for ph in broken["phases"]:
        if ph["id"] == "P4-COPY":
            del ph["workers"]
    flagged = [d["item"] for d in _sync_check_w2_drift(broken)]
    assert flagged == ["P4-COPY"], flagged


# ---------------------------------------------------------------------------
# 5. Declared widths resolve at dispatch width.
# ---------------------------------------------------------------------------
def test_declared_widths_resolve_at_dispatch_width():
    from presentation_job.fanout import resolve_effective_workers
    from presentation_job.manifest import Manifest
    m = Manifest(_canonical())
    for pid, declared in EXPECTED_WIDTHS.items():
        phase = m.phase(pid)
        assert phase.workers == declared
        # Ample units, no capacity term: the declared width is the width.
        assert resolve_effective_workers(
            phase.workers, unit_count=50) == declared, pid
        # Fewer units than the declaration: the unit count binds.
        assert resolve_effective_workers(
            phase.workers, unit_count=2) == min(declared, 2), pid
        # Capacity binds BELOW the declaration: the declaration is a
        # per-phase ceiling the measured capacity still caps, never a
        # machine promise burned into the manifest.
        assert resolve_effective_workers(
            phase.workers, unit_count=50, capacity_available=4) == min(declared, 4), pid


# ---------------------------------------------------------------------------
# 6. The run record carries the note.
# ---------------------------------------------------------------------------
def _cmd_new(tmp_path: Path, manifest_path: Path, run_name: str):
    from presentation_job.__main__ import cmd_new
    intake = tmp_path / f"intake-{run_name}.json"
    intake.write_text(json.dumps(
        {"presentation_type": "from_scratch",
         "requester": {"chat_id": "item11-test"}}), encoding="utf-8")
    run_dir = tmp_path / run_name
    args = SimpleNamespace(run_dir=run_dir, intake=intake,
                           manifest=str(manifest_path))
    rc = cmd_new(args, SCRIPTS)
    assert rc == 0
    return json.loads((run_dir / "state.json").read_text(encoding="utf-8"))


def test_run_record_carries_fanout_width_warnings(tmp_path):
    raw = json.loads(_canonical().read_text(encoding="utf-8"))
    for ph in raw["phases"]:
        if ph["id"] == "P-IMAGE-QC":
            del ph["workers"]
    scratch = tmp_path / "PIPELINE-MANIFEST.json"
    scratch.write_text(json.dumps(raw), encoding="utf-8")

    state = _cmd_new(tmp_path, scratch, "run-undeclared")
    warnings = state.get("fanout_width_warnings")
    assert warnings is not None, (
        "state.json carries no fanout_width_warnings key: the run record "
        "does not note the undeclared width")
    assert len(warnings) == 1 and "P-IMAGE-QC" in warnings[0], warnings

    clean = _cmd_new(tmp_path, _canonical(), "run-declared")
    assert clean["fanout_width_warnings"] == [], clean["fanout_width_warnings"]

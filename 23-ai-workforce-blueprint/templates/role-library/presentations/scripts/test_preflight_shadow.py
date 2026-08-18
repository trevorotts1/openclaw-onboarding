#!/usr/bin/env python3
"""test_preflight_shadow.py — proves presentation_job/preflight_shadow.py, the
trust-boundary "wrap" instrumentation on build_deck.run_preflight()'s
PREFLIGHT_REQUIRED dispatch loop (see CONTROL/TRUST-BOUNDARY-BUILD-SPEC.md §7.2).

Reuses the REAL fixture-building helper (`make_workdir`) and the REAL
front-door nonce helper (`_arm_entry_nonce`) already in test_preflight.py —
this file authors no fixture of its own; every run dir here is the same
upstream-artifact set the existing preflight test suite already builds and
the existing preflight gates already validate. What this file adds is calling
the REAL build_deck.run_preflight() directly (in-process, deterministic) and
inspecting the REAL shadow ledger it writes as a side effect.

Three cases:

  CASE A — LEGITIMATE run is unaffected.
    make_workdir(with_artifacts=True) (the existing "preflight passes" fixture)
    run through the REAL run_preflight() with the wrap active. Asserts:
      - no SystemExit / no refusal (matches the pre-existing, unwrapped
        behavior — CASE 2 of test_preflight.py already proves this fixture
        passes; this asserts the wrap doesn't change that).
      - stdout is BYTE-IDENTICAL to the same call with the wrap stubbed to a
        pure no-op — direct proof the wrap changes nothing observable to a
        caller who isn't looking at the new ledger.
      - the shadow ledger has exactly len(PREFLIGHT_REQUIRED) lines, all
        legacy_result=PASS, zero toctou_divergence.

  CASE B — TAMPERED run is DETECTED and RECORDED, but still proceeds.
    Same fixture, but the REAL _chk_intake function (PREFLIGHT_REQUIRED[0],
    "working/copy/intake.json") is wrapped — for this test only, restored in
    a `finally` — so that when the dispatch loop calls it, it first appends a
    harmless field to intake.json (simulating a concurrent/racing writer
    mutating the SAME file between admission-time seal and this gate's own
    read) and THEN calls the unmodified real _chk_intake on the now-changed
    file. The real gate's own pass/fail logic never changes — only the bytes
    on disk change, mid-loop, after the wrap's up-front seal already ran.
    Asserts:
      - run_preflight() still does NOT exit 3 (report-only: a divergence
        never blocks) — proves item 3 of the task ("show a run that WOULD
        fail the new validation still completing").
      - the ledger line for that gate has toctou_divergence=true AND
        legacy_result=PASS — the exact "would-have-blocked" shape — and
        names the specific fact (gate_label) and its source (resolved_path).
      - a TRUST-BOUNDARY-PREFLIGHT-WOULD-BLOCK line was printed to stderr
        naming the same gate and path.
      - repeating CASE B with PRES_TRUST_BOUNDARY_ENFORCE=1 set STILL does
        not block — surface A has no enforcing() branch in Phase 1 at all
        (spec §7.2's explicit design), so flipping the flag must not change
        the outcome even though it does get recorded into the ledger line's
        enforcing_flag_set field.

  CASE C — a broken shadow module can never break a legitimate run.
    Same clean fixture, but preflight_shadow.open_run is monkeypatched to
    raise. Asserts run_preflight() still passes (does not exit 3, does not
    propagate the exception) — proves the module's own "never raises across
    the wrapped call site" contract at the one point it matters most: total
    failure of the shadow module itself.

Run:  python3 test_preflight_shadow.py
Exit: 0 = all assertions passed; 1 = a case failed.
"""
import contextlib
import io
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import build_deck  # noqa: E402
from presentation_job import preflight_shadow  # noqa: E402
from test_preflight import make_workdir  # noqa: E402 — REUSE the real fixture, author none here

LEDGER_REL = Path("working") / "checkpoints" / "preflight-shadow.jsonl"


def _read_ledger(root: Path):
    p = root / LEDGER_REL
    if not p.is_file():
        return []
    lines = [ln for ln in p.read_text().splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines]


def _run_preflight_captured(root: Path):
    """Call the REAL build_deck.run_preflight() in-process. Returns
    (exited_3, stdout_text, stderr_text)."""
    out, err = io.StringIO(), io.StringIO()
    exited_3 = False
    slides_path = root / "slides.json"
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            build_deck.run_preflight(root, slides_path=slides_path)
        except SystemExit as e:
            exited_3 = (e.code == 3)
    return exited_3, out.getvalue(), err.getvalue()


def case_a_legitimate_unaffected():
    fails = []
    root = make_workdir(with_artifacts=True)

    exited_3, out_wrapped, err_wrapped = _run_preflight_captured(root)
    if exited_3:
        fails.append("CASE A: legitimate run wrongly refused (exit 3) with wrap active")

    ledger = _read_ledger(root)
    if len(ledger) != len(build_deck.PREFLIGHT_REQUIRED):
        fails.append(f"CASE A: ledger has {len(ledger)} lines, expected "
                     f"{len(build_deck.PREFLIGHT_REQUIRED)} (one per PREFLIGHT_REQUIRED entry)")
    bad_pass = [e["gate_label"] for e in ledger if e.get("legacy_result") != "PASS"]
    if bad_pass:
        fails.append(f"CASE A: expected every gate to PASS on the clean fixture, "
                      f"these did not: {bad_pass}")
    diverged = [e["gate_label"] for e in ledger if e.get("toctou_divergence")]
    if diverged:
        fails.append(f"CASE A: unexpected TOCTOU divergence on an untouched clean "
                      f"fixture: {diverged}")

    # Byte-identical stdout proof: SAME fixture, SAME run_dir, wrap stubbed to
    # a pure no-op the second time (open_run returns None -> record()/
    # close_run() are no-ops by their own contract). Re-running run_preflight()
    # against the same already-validated run dir is read-only/idempotent for
    # every _chk_* gate, so any stdout difference can only come from the wrap
    # itself. (Using the SAME root, not a second make_workdir() call, so the
    # comparison isn't confounded by the tempdir path printed in the banner
    # line, which differs across two independent make_workdir() calls.)
    _real_open_run = preflight_shadow.open_run
    preflight_shadow.open_run = lambda *a, **k: None
    try:
        exited_3_stub, out_stub, _ = _run_preflight_captured(root)
    finally:
        preflight_shadow.open_run = _real_open_run
    if exited_3_stub:
        fails.append("CASE A: control run (wrap stubbed) unexpectedly refused")
    if out_stub != out_wrapped:
        fails.append("CASE A: stdout differs between wrap-active and wrap-stubbed runs "
                      "-- the wrap is changing observable legacy behavior")

    print(f"CASE A (legitimate unaffected) -> "
          f"{'PASS' if not fails else 'FAIL'}  (ledger entries={len(ledger)})")
    return fails


def _intake_entry_index():
    for i, entry in enumerate(build_deck.PREFLIGHT_REQUIRED):
        if entry[0] == "working/copy/intake.json":
            return i
    raise AssertionError("could not find the intake.json PREFLIGHT_REQUIRED entry")


def _run_case_b(enforce: bool):
    fails = []
    root = make_workdir(with_artifacts=True)
    idx = _intake_entry_index()
    rel, label, phase, real_check = build_deck.PREFLIGHT_REQUIRED[idx]

    def _tamper_then_check(path):
        # Simulate a concurrent/racing writer: mutate the SAME file the wrap
        # already sealed at admission, with a change the real gate's own
        # logic ignores (an added key), so the REAL gate's pass/fail verdict
        # is untouched -- only the bytes on disk change, mid-loop.
        try:
            p = Path(path)
            obj = json.loads(p.read_text())
            obj["_simulated_concurrent_write"] = "race-injected-by-test"
            p.write_text(json.dumps(obj))
        except Exception:
            pass
        return real_check(path)  # unmodified real gate logic decides pass/fail

    build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, _tamper_then_check)
    env_backup = os.environ.get("PRES_TRUST_BOUNDARY_ENFORCE")
    try:
        if enforce:
            os.environ["PRES_TRUST_BOUNDARY_ENFORCE"] = "1"
        else:
            os.environ.pop("PRES_TRUST_BOUNDARY_ENFORCE", None)
        exited_3, out, err = _run_preflight_captured(root)
    finally:
        build_deck.PREFLIGHT_REQUIRED[idx] = (rel, label, phase, real_check)
        if env_backup is None:
            os.environ.pop("PRES_TRUST_BOUNDARY_ENFORCE", None)
        else:
            os.environ["PRES_TRUST_BOUNDARY_ENFORCE"] = env_backup

    tag = f"enforce={enforce}"
    if exited_3:
        fails.append(f"CASE B ({tag}): tampered run wrongly BLOCKED (exit 3) -- "
                      f"report-only surface A must never block")

    ledger = _read_ledger(root)
    matches = [e for e in ledger if e.get("gate_label") == label]
    if len(matches) != 1:
        fails.append(f"CASE B ({tag}): expected exactly one ledger line for "
                      f"{label!r}, found {len(matches)}")
    else:
        e = matches[0]
        if not e.get("toctou_divergence"):
            fails.append(f"CASE B ({tag}): tamper was NOT detected "
                          f"(toctou_divergence=false) -- {e}")
        if e.get("legacy_result") != "PASS":
            fails.append(f"CASE B ({tag}): expected the legacy gate to still PASS "
                          f"(its own logic ignores the injected field) -- got "
                          f"{e.get('legacy_result')}")
        if e.get("resolved_path") is None or "intake.json" not in e["resolved_path"]:
            fails.append(f"CASE B ({tag}): record does not name WHERE the fact came "
                          f"from -- resolved_path={e.get('resolved_path')!r}")
        if e.get("gate_label") != label:
            fails.append(f"CASE B ({tag}): record does not name the SPECIFIC gate")
        if e.get("enforcing_flag_set") != enforce:
            fails.append(f"CASE B ({tag}): ledger's enforcing_flag_set={e.get('enforcing_flag_set')} "
                          f"does not match the env this run actually had ({enforce})")
        if e.get("hash_at_seal") == e.get("hash_at_check"):
            fails.append(f"CASE B ({tag}): hash_at_seal should differ from "
                          f"hash_at_check after the injected mid-loop write")

    if "TRUST-BOUNDARY-PREFLIGHT-WOULD-BLOCK" not in err:
        fails.append(f"CASE B ({tag}): expected a WOULD-BLOCK line on stderr, none found")
    elif label not in err:
        fails.append(f"CASE B ({tag}): WOULD-BLOCK line did not name the gate label")

    print(f"CASE B (tampered detected, {tag}) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def case_c_shadow_module_failure_never_blocks():
    fails = []
    root = make_workdir(with_artifacts=True)
    _real_open_run = preflight_shadow.open_run

    def _boom(*a, **k):
        raise RuntimeError("simulated total failure of the shadow module")

    preflight_shadow.open_run = _boom
    try:
        exited_3, out, err = _run_preflight_captured(root)
    finally:
        preflight_shadow.open_run = _real_open_run

    if exited_3:
        fails.append("CASE C: a raising shadow module caused the run to be refused")
    if "PREFLIGHT PASSED" not in out:
        fails.append("CASE C: a raising shadow module suppressed the normal PASS banner "
                      "(the exception propagated somewhere it shouldn't have)")

    print(f"CASE C (shadow-module-failure-is-safe) -> {'PASS' if not fails else 'FAIL'}")
    return fails


def main() -> int:
    all_fails = []
    all_fails += case_a_legitimate_unaffected()
    all_fails += _run_case_b(enforce=False)
    all_fails += _run_case_b(enforce=True)
    all_fails += case_c_shadow_module_failure_never_blocks()

    print()
    if all_fails:
        print(f"FAIL ({len(all_fails)} failure(s)):")
        for f in all_fails:
            print(f"  - {f}")
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

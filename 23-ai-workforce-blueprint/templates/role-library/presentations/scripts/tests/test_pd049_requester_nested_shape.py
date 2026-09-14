#!/usr/bin/env python3
"""test_pd049_requester_nested_shape.py -- PD-TEST-049 pin.

THE FAULT (live, first-ever real engine execution, 2026-09-14)
--------------------------------------------------------------
The real operator-delegated run
`pres-operator-1d269693-ff54-4b1f-b45a-61dc7d8ca4d4` sealed a
working/copy/intake.json that DID carry a requester -- but only in the FLAT
shape:

    "requester_chat_id": "5252140759",
    "requester_channel": "telegram",

and the engine died on its first instruction with

    FATAL: no requester.chat_id in intake. A presentations job with no
    requester cannot report progress or completion to anyone, and must not
    start (fix F1).

because presentation_job/__main__.py:266 reads the NESTED
`intake.get("requester") or {}` and :278-281 requires its `chat_id`.

WHY THE FLAT SHAPE WAS NOT ENOUGH -- the two dispatch paths differ
------------------------------------------------------------------
  * SHELL path: presentation-canonical-entry.sh:1188 / presentation-intake-
    poll.sh:1270 run presentation_job/resolve_intake.py first and hand the
    engine `working/checkpoints/.engine-intake.json` -- resolve_intake.py's
    OWN output, which builds the nested object (resolve_intake.py:498-504)
    out of the flat pair (resolve_intake.py:477-480).
  * LAUNCHER path (operator-delegated bridge): intake_bridge.
    drive_operator_contract() -> `deck-intake-driver.py --complete` ->
    launcher.dispatch_new(). The launcher NEVER runs resolve_intake.py: it
    passes the driver's own working/copy/intake.json STRAIGHT to the engine as
    --intake (launcher.py:1763-1771, contract stated at launcher.py:1760-1761
    and dispatch_new's docstring launcher.py:1884-1885).

deck-intake-driver.py is the SOLE writer of that file (its own comment;
intake_bridge.py:1108-1110). Its FIX F19 stamp wrote only the FLAT pair, so
the launcher path produced an intake the engine's own F1 gate was always
going to reject. Every prior "successful" engine run on this box had a
hand-authored/acceptance intake.json that already carried the nested object,
which is why the gap survived until the first REAL run.

WHAT THIS FILE PROVES, MECHANICALLY
------------------------------------
  1. REGRESSION: an intake completed through the REAL, unmodified
     deck-intake-driver.py CLI, then consumed the way the LAUNCHER consumes
     it (the file itself as --intake), satisfies F1 and creates the job.
     This is RED before the fix and GREEN after.
  2. The nested object the driver emits is byte-for-byte the product's own
     canonical shape -- {"chat_id", "client_name", "channel"} -- the object
     resolve_intake.py:498-500 builds and real runs' state.json carries.
  3. An intake that ALREADY carried a flat requester (the no-clobber path
     _resolve_requester_from_env() early-returns on) still gets the nested
     mirror from that pre-existing value -- otherwise such a run keeps dying
     at F1 forever.
  4. The FLAT pair is still written/never clobbered, and still feeds the
     shell path: the REAL resolve_intake.py still resolves from it. No
     existing consumer is broken by the added nested object.
  5. Both SIGNATURE finalize paths (--sig-record and the turn-gated
     --sig-answer finalize) stamp both shapes too.
  6. F1 IS NOT WEAKENED: a genuinely requester-less run (no chat-surface env
     var, no OPERATOR_*_CHAT_ID env var, no reachable openclaw.json) still
     gets NOTHING fabricated -- no flat value, no nested object -- and the
     engine still refuses it loudly, writing no state.json.

Unit + subprocess level, no kie.ai spend, no renderer, no network, and it
never touches this box's real run dirs or its real ~/.openclaw/openclaw.json
(every subprocess gets an isolated HOME and every requester key is scrubbed).
Flat file inside tests/, manages its own import path -- matching every
sibling in this directory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
DRIVER_PATH = SCRIPTS / "deck-intake-driver.py"
RESOLVE_INTAKE_PATH = SCRIPTS / "presentation_job" / "resolve_intake.py"
ENGINE_ENTRY = SCRIPTS / "presentation_job.py"

sys.path.insert(0, str(SCRIPTS))

# Deployed tree first (scripts/../sops/PIPELINE-MANIFEST.json); repo walk-up
# fallback -- mirrors test_f19_requester_stamp.py's own resolution exactly.
_DEPLOYED_MANIFEST = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
if _DEPLOYED_MANIFEST.is_file():
    MANIFEST = _DEPLOYED_MANIFEST
else:
    _cur = HERE
    MANIFEST = None
    for _ in range(12):
        _cand = _cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if _cand.is_file():
            MANIFEST = _cand
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent

pytestmark = pytest.mark.skipif(
    MANIFEST is None,
    reason="PIPELINE-MANIFEST.json not found (deployed sops/ or universal-sops walk-up)")

# Every env key either tier of the requester resolution can consult -- ALL of
# these must be scrubbed, or a value leaking in from this box's real shell
# would produce a false pass.
_ALL_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
    "PRESENTATION_REQUESTER_CHANNEL",
    "PRESENTER_CHAT_ID",
    "PRESENTER_CHANNEL",
    "OPERATOR_ESCALATION_CHAT_ID",
    "OPERATOR_HELP_CHAT_ID",
    "OPERATOR_TELEGRAM_CHAT_ID",
)


# ---------------------------------------------------------------------------
# fixture plumbing
# ---------------------------------------------------------------------------
def _isolated_env(tmp_path: Path, overrides: dict | None = None,
                  config_vars: dict | None = None) -> dict:
    """A subprocess env ISOLATED from this box's real operator config: every
    requester-resolution key scrubbed, HOME repointed at a fresh tmp dir (so
    operator_requester.py's config tier -- ~/.openclaw/openclaw.json --
    resolves to nothing real). `config_vars` writes a synthetic openclaw.json
    under that fake HOME, so the sanctioned operator fallback can be exercised
    deterministically without ever touching the real config or a real id."""
    env = dict(os.environ)
    for key in _ALL_REQUESTER_ENV_KEYS:
        env.pop(key, None)
    fake_home = tmp_path / "fakehome"
    fake_home.mkdir(exist_ok=True)
    env["HOME"] = str(fake_home)
    if config_vars:
        cfg_dir = fake_home / ".openclaw"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        (cfg_dir / "openclaw.json").write_text(
            json.dumps({"env": {"vars": config_vars}}), encoding="utf-8")
    if overrides:
        env.update(overrides)
    return env


def _run_driver(run_dir: Path, env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DRIVER_PATH), "--run-dir", str(run_dir), *args],
        capture_output=True, text=True, env=env,
    )


def _drive_standard_intake(run_dir: Path, env: dict) -> subprocess.CompletedProcess:
    r = _run_driver(run_dir, env, "--answer", "presentation_type", "from_scratch")
    assert r.returncode == 0, f"--answer failed: {r.stdout}\n{r.stderr}"
    return _run_driver(run_dir, env, "--complete")


def _intake_copy_path(run_dir: Path) -> Path:
    return run_dir / "working" / "copy" / "intake.json"


def _read_intake_copy(run_dir: Path) -> dict:
    path = _intake_copy_path(run_dir)
    assert path.is_file(), f"driver did not write {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_engine_new(run_dir: Path, env: dict, intake_path: Path) -> subprocess.CompletedProcess:
    """Exactly the launcher's invocation (launcher.py:1745-1771): the engine
    entry, `--new`, `--run-dir`, and the intake FILE the launcher would pass.
    No resolve_intake.py in the loop -- that is the whole point."""
    return subprocess.run(
        [sys.executable, str(ENGINE_ENTRY), "--new", "--run-dir", str(run_dir),
         "--intake", str(intake_path), "--manifest", str(MANIFEST)],
        capture_output=True, text=True, env=env,
    )


def _run_resolve_intake(run_dir: Path, env: dict, out_path: Path) -> subprocess.CompletedProcess:
    ledger_path = run_dir / "working" / "interview" / "intake_ledger.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(RESOLVE_INTAKE_PATH), "--ledger", str(ledger_path),
         "--out", str(out_path), "--source", "test-pd049"],
        capture_output=True, text=True, env=env,
    )


# ---------------------------------------------------------------------------
# 1 + 2 -- THE REGRESSION: the launcher's own consumption of the driver's file
# ---------------------------------------------------------------------------
class TestLauncherPathGetsANestedRequester:
    def test_driver_intake_file_alone_satisfies_the_engine_f1_gate(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-PD049-0001"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"

        intake_copy = _intake_copy_path(run_dir)
        assert intake_copy.is_file()
        # The file the launcher passes is the REAL driver output -- not a
        # hand-built object that already carries the nested shape.
        pre = _read_intake_copy(run_dir)
        assert pre.get("requester_chat_id") == "TESTOP-PD049-0001"

        r = _run_engine_new(run_dir, env, intake_copy)
        assert r.returncode == 0, (
            "the launcher hands the engine the driver's own working/copy/"
            "intake.json (launcher.py:1763-1771) -- it must satisfy F1 on its "
            f"own, without resolve_intake.py. rc={r.returncode}\n"
            f"stdout={r.stdout}\nstderr={r.stderr}")
        assert "no requester.chat_id in intake" not in (r.stdout + r.stderr), (
            "F1 must not fire: the file DID carry a requester (flat) and the "
            "producer must also emit the nested shape the engine reads")
        state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
        assert state["requester"]["chat_id"] == "TESTOP-PD049-0001"

    def test_nested_object_is_the_products_canonical_shape(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-PD049-0002"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester") == {
            "chat_id": "TESTOP-PD049-0002",
            "client_name": "operator",
            "channel": "telegram",
        }, ("the emitted nested object must be resolve_intake.py:498-500's "
            "canonical shape, not an ad-hoc one")

    def test_env_tier_requester_is_also_nested(self, tmp_path):
        """A real chat-surface requester (dispatcher-exported env var) gets the
        SAME nested mirror -- not just the operator fallback."""
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            overrides={"PRESENTATION_REQUESTER_CHAT_ID": "REAL-CLIENT-7777"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "REAL-CLIENT-7777"
        assert intake.get("requester", {}).get("chat_id") == "REAL-CLIENT-7777"
        r = _run_engine_new(run_dir, env, _intake_copy_path(run_dir))
        assert r.returncode == 0, f"F1 not satisfied: {r.stdout}\n{r.stderr}"


# ---------------------------------------------------------------------------
# 3 -- the no-clobber path: a pre-existing FLAT requester must still be
# mirrored (this is the branch _resolve_requester_from_env() early-returns on)
# ---------------------------------------------------------------------------
class TestPreExistingFlatRequesterIsMirrored:
    def test_upstream_stamped_flat_requester_gets_the_nested_mirror(self, tmp_path):
        run_dir = tmp_path / "run"
        copy_dir = run_dir / "working" / "copy"
        copy_dir.mkdir(parents=True)
        copy_dir.joinpath("intake.json").write_text(
            json.dumps({"requester_chat_id": "UPSTREAM-1234",
                        "requester_channel": "telegram"}), encoding="utf-8")
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "SHOULD-NOT-WIN"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"

        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "UPSTREAM-1234", (
            "an upstream stamp must never be clobbered")
        assert intake.get("requester", {}).get("chat_id") == "UPSTREAM-1234", (
            "the nested mirror must be derived from the value ALREADY on disk "
            "-- the fallback must not have to resolve anything for this")
        assert intake.get("requester", {}).get("channel") == "telegram"

        r = _run_engine_new(run_dir, env, _intake_copy_path(run_dir))
        assert r.returncode == 0, (
            "an upstream-stamped flat-requester intake must also satisfy F1 "
            f"when the launcher passes it straight through: {r.stdout}\n{r.stderr}")

    def test_pre_existing_nested_requester_is_never_rewritten(self, tmp_path):
        run_dir = tmp_path / "run"
        copy_dir = run_dir / "working" / "copy"
        copy_dir.mkdir(parents=True)
        canonical = {"chat_id": "ALREADY-NESTED-1", "client_name": "operator",
                     "channel": "telegram"}
        copy_dir.joinpath("intake.json").write_text(
            json.dumps({"requester": canonical,
                        "requester_chat_id": "ALREADY-NESTED-1",
                        "requester_channel": "telegram"}), encoding="utf-8")
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "SHOULD-NOT-WIN"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester") == canonical


# ---------------------------------------------------------------------------
# 4 -- no existing consumer is broken: the FLAT pair is still written, is
# still authoritative, and still feeds the shell path's resolve_intake.py.
# ---------------------------------------------------------------------------
class TestFlatShapeStillServesTheShellPath:
    def test_flat_pair_still_resolves_through_the_real_resolve_intake(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-PD049-0004"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"

        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-PD049-0004"
        assert intake.get("requester_channel") == "telegram"

        out_path = run_dir / "working" / "checkpoints" / ".engine-intake.json"
        r = _run_resolve_intake(run_dir, env, out_path)
        assert r.returncode == 0, (
            f"resolve_intake.py reads the FLAT pair from working/copy/intake.json "
            f"(resolve_intake.py:477-480); the added nested object must not "
            f"disturb it: {r.stdout}\n{r.stderr}")
        engine_intake = json.loads(out_path.read_text(encoding="utf-8"))
        assert engine_intake["requester"]["chat_id"] == "TESTOP-PD049-0004"


# ---------------------------------------------------------------------------
# 5 -- the two SIGNATURE finalize paths carry the nested shape too.
# ---------------------------------------------------------------------------
class TestSignatureFinalizePathsAlsoNest:
    def test_sig_record_stamps_both_shapes(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-PD049-SIGREC"})
        record_file = tmp_path / "sp-record.json"
        record_file.write_text(json.dumps({
            "signature_frame": "authority_teardown",
            "mode": "quick",
        }), encoding="utf-8")
        r = _run_driver(run_dir, env, "--signature", "--sig-record", str(record_file))
        assert r.returncode == 0, f"--signature --sig-record failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-PD049-SIGREC"
        assert intake.get("requester", {}).get("chat_id") == "TESTOP-PD049-SIGREC"

    def test_sig_finalize_stamps_both_shapes(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path,
                            config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-PD049-SIGFIN"})
        r = _run_driver(run_dir, env, "--signature", "--sig-answer", "sp_mode", "QUICK")
        assert r.returncode == 0, f"--sig-answer sp_mode failed: {r.stdout}\n{r.stderr}"
        r = _run_driver(run_dir, env, "--signature", "--sig-answer",
                        "signature_frame", "vault")
        assert r.returncode == 0, f"--sig-answer signature_frame failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-PD049-SIGFIN"
        assert intake.get("requester", {}).get("chat_id") == "TESTOP-PD049-SIGFIN"


# ---------------------------------------------------------------------------
# 6 -- F1 IS NOT WEAKENED. A genuinely requester-less run must still refuse,
# with nothing fabricated in EITHER shape.
# ---------------------------------------------------------------------------
class TestF1GateIsNotWeakened:
    def test_no_source_anywhere_leaves_both_shapes_absent(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path)  # no overrides, no config_vars
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert not intake.get("requester_chat_id"), (
            "a genuinely requester-less run must NOT have a flat chat_id invented")
        assert not (intake.get("requester") or {}).get("chat_id"), (
            "a genuinely requester-less run must NOT have a nested requester "
            "invented -- the mirror only ever moves a value that really exists")

    def test_engine_still_refuses_the_requester_less_real_intake(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path)
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0
        intake_copy = _intake_copy_path(run_dir)
        assert intake_copy.is_file()
        r = _run_engine_new(run_dir, env, intake_copy)
        assert r.returncode != 0, (
            "F1 must still refuse this run: no requester exists anywhere")
        assert "no requester.chat_id in intake" in (r.stdout + r.stderr)
        assert not (run_dir / "state.json").exists(), (
            "a refused run must not have created a job state")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

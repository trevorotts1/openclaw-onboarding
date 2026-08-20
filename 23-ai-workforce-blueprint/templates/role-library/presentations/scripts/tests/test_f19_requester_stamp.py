#!/usr/bin/env python3
"""test_f19_requester_stamp.py -- FIX F19 pin.

THE FAULT (orchestrator-verified, see the F19 unit brief)
-----------------------------------------------------------
Across every real run dir on this box, only one carried a requester.chat_id
-- and only because a human hand-stamped it after the fact. deck-intake-
driver.py's --complete already carried _resolve_requester_from_env(), which
forwards a chat-surface requester when a dispatcher exported one of
PRESENTATION_REQUESTER_CHAT_ID / ROUTE_PRES_REQUESTER_CHAT_ID /
MC_ROUTE_REQUESTER_CHAT_ID -- but had NOTHING to fall back to when none of
those were set, which is exactly the shape of every real CLI-driven run on
this box (a genuinely operator-initiated deck). resolve_intake.py correctly
raises MissingRequester in that case (fix F04) and presentation_job.py --new
correctly hard-fails at its own F1 gate ("no requester.chat_id in intake ...
must not start") -- both of those are RIGHT and must stay untouched. What was
missing is a legitimate SOURCE to stamp at creation, so a deck could ever
clear that gate without a human editing JSON by hand.

THIS FILE PROVES, MECHANICALLY, END TO END
--------------------------------------------
  1. An intake completed through the REAL, unmodified deck-intake-driver.py
     CLI (--answer / --complete) -- with no chat-surface env var set, but
     the sanctioned OPERATOR fallback configured -- yields working/copy/
     intake.json carrying a usable requester_chat_id (both the env tier and
     the ~/.openclaw/openclaw.json config tier of operator_requester.py).
  2. That ledger then resolves through the REAL resolve_intake.py into an
     engine intake whose requester.chat_id is non-empty -- the exact shape
     presentation_job.py --new's F1 gate requires.
  3. presentation_job.py --new, run for real (not mocked) against that
     engine intake and a real PIPELINE-MANIFEST.json, creates the job --
     it does NOT die with "no requester.chat_id in intake" (F1 satisfied).
  4. A run with genuinely NO requester source anywhere (no chat-surface env
     var, no OPERATOR_*_CHAT_ID env var, no reachable openclaw.json) still
     fails LOUDLY at resolve_intake.py (exit 4, AF-REQUESTER-MISSING,
     writes nothing) -- the gate this fix must never weaken.
  5. The chat-surface requester (a real client order) always wins over the
     operator fallback when both are present -- priority order regression.
  6. An intake that already carries a requester_chat_id is never clobbered.
  7. The two SIGNATURE-mode finalize paths this fix also had to patch
     (--signature --record's inline finalize, and _sig_record() -- the path
     "tooling that already ran the turn-gate through another surface" uses)
     now stamp the requester too, closing the same gap in the second/third
     intake-finalization code path inside the one driver.
  8. operator_requester.resolve_operator_chat_id() itself: env tier beats
     config tier, the tiered alias precedence is honored, and it returns
     ("", "") -- never a fabricated id -- when nothing is configured.

Unit + subprocess-level, no kie.ai spend, no renderer, no network, never
touches the live box's real run dirs or its real ~/.openclaw/openclaw.json
(every subprocess gets an isolated HOME so the config tier is exercised only
against a synthetic fixture file). Flat file inside tests/, manages its own
import path -- matching every sibling in this directory.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PRES_DEPT = SCRIPTS.parent
DRIVER_PATH = SCRIPTS / "deck-intake-driver.py"
RESOLVE_INTAKE_PATH = SCRIPTS / "presentation_job" / "resolve_intake.py"
ENGINE_ENTRY = SCRIPTS / "presentation_job.py"
OPERATOR_REQUESTER_PATH = SCRIPTS / "operator_requester.py"

sys.path.insert(0, str(SCRIPTS))

from presentation_job import resolve_intake as ri  # noqa: E402
import operator_requester as opreq  # noqa: E402

# Deployed tree first (scripts/../sops/PIPELINE-MANIFEST.json); repo walk-up
# fallback (universal-sops/presentation-slide-craft/) -- mirrors
# test_fix23_door_reliability.py's own manifest resolution exactly.
_DEPLOYED_MANIFEST = SCRIPTS.parent / "sops" / "PIPELINE-MANIFEST.json"
if _DEPLOYED_MANIFEST.is_file():
    MANIFEST = _DEPLOYED_MANIFEST
else:
    _cur = HERE
    _m = None
    for _ in range(12):
        _cand = _cur / "universal-sops" / "presentation-slide-craft" / "PIPELINE-MANIFEST.json"
        if _cand.is_file():
            _m = _cand
            break
        if _cur.parent == _cur:
            break
        _cur = _cur.parent
    MANIFEST = _m

pytestmark = pytest.mark.skipif(
    MANIFEST is None, reason="PIPELINE-MANIFEST.json not found (deployed sops/ or universal-sops walk-up)"
)

# Every env key either tier of the requester resolution can consult -- ALL of
# these must be scrubbed from a test's env before it asserts a negative, or a
# value leaking in from this box's real shell would produce a false pass.
_ALL_REQUESTER_ENV_KEYS = (
    "PRESENTATION_REQUESTER_CHAT_ID",
    "ROUTE_PRES_REQUESTER_CHAT_ID",
    "MC_ROUTE_REQUESTER_CHAT_ID",
    "PRESENTATION_REQUESTER_CHANNEL",
    "OPERATOR_ESCALATION_CHAT_ID",
    "OPERATOR_HELP_CHAT_ID",
    "OPERATOR_TELEGRAM_CHAT_ID",
)


# ---------------------------------------------------------------------------
# fixture plumbing
# ---------------------------------------------------------------------------
def _isolated_env(tmp_path: Path, overrides: dict | None = None,
                  config_vars: dict | None = None) -> dict:
    """Build a subprocess env that is ISOLATED from this box's real operator
    config: every requester-resolution key is scrubbed, then HOME is
    repointed at a fresh empty tmp dir (so operator_requester.py's config
    tier -- ~/.openclaw/openclaw.json -- resolves to nothing real). When
    `config_vars` is given, a synthetic openclaw.json carrying exactly those
    env.vars is written under the fake HOME, so the config tier can be
    exercised deterministically without ever touching the real config file
    or a real chat id."""
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


def _read_intake_copy(run_dir: Path) -> dict:
    path = run_dir / "working" / "copy" / "intake.json"
    assert path.is_file(), f"driver did not write {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def _run_resolve_intake(run_dir: Path, env: dict, out_path: Path) -> subprocess.CompletedProcess:
    ledger_path = run_dir / "working" / "interview" / "intake_ledger.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    return subprocess.run(
        [sys.executable, str(RESOLVE_INTAKE_PATH), "--ledger", str(ledger_path),
         "--out", str(out_path), "--source", "test-f19"],
        capture_output=True, text=True, env=env,
    )


def _run_engine_new(run_dir: Path, env: dict, intake_path: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENGINE_ENTRY), "--new", "--run-dir", str(run_dir),
         "--intake", str(intake_path), "--manifest", str(MANIFEST)],
        capture_output=True, text=True, env=env,
    )


# ---------------------------------------------------------------------------
# 1 + 2 + 3 -- the mandated end-to-end chain, POSITIVE (operator fallback,
# env tier of operator_requester.py)
# ---------------------------------------------------------------------------
class TestEndToEndChainOperatorFallbackEnvTier:
    def test_driver_complete_stamps_requester_from_operator_env(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, overrides={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-ENV-0001"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-ENV-0001"
        assert intake.get("requester_channel") == "telegram"

    def test_resolve_intake_then_satisfies_engine_f1_gate(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, overrides={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-ENV-0002"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"

        out_path = run_dir / "working" / "checkpoints" / ".engine-intake.json"
        r = _run_resolve_intake(run_dir, env, out_path)
        assert r.returncode == 0, f"resolve_intake failed: {r.stdout}\n{r.stderr}"
        engine_intake = json.loads(out_path.read_text(encoding="utf-8"))
        assert engine_intake.get("requester", {}).get("chat_id") == "TESTOP-ENV-0002"

        r = _run_engine_new(run_dir, env, out_path)
        assert r.returncode == 0, (
            f"presentation_job.py --new should satisfy F1 and create the job, "
            f"got rc={r.returncode}\nstdout={r.stdout}\nstderr={r.stderr}")
        assert "no requester.chat_id" not in (r.stdout + r.stderr), (
            "F1 gate message must not appear -- the requester DID resolve")
        state_path = run_dir / "state.json"
        assert state_path.is_file()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state.get("requester", {}).get("chat_id") == "TESTOP-ENV-0002"


# ---------------------------------------------------------------------------
# operator fallback, CONFIG tier (~/.openclaw/openclaw.json env.vars)
# ---------------------------------------------------------------------------
class TestOperatorFallbackConfigTier:
    def test_driver_complete_stamps_requester_from_operator_config_file(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-CFG-0001"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-CFG-0001"
        assert intake.get("requester_channel") == "telegram"

    def test_config_chain_also_satisfies_f1(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, config_vars={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-CFG-0002"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0

        out_path = run_dir / "working" / "checkpoints" / ".engine-intake.json"
        r = _run_resolve_intake(run_dir, env, out_path)
        assert r.returncode == 0, f"resolve_intake failed: {r.stdout}\n{r.stderr}"

        r = _run_engine_new(run_dir, env, out_path)
        assert r.returncode == 0, f"F1 gate not satisfied: {r.stdout}\n{r.stderr}"


# ---------------------------------------------------------------------------
# 4 -- the mandated NEGATIVE: no legitimate source anywhere -> loud failure,
# gate intact, nothing silently started.
# ---------------------------------------------------------------------------
class TestNoLegitimateSourceStillFailsLoudly:
    def test_driver_complete_leaves_requester_unstamped(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path)  # no overrides, no config_vars
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert not intake.get("requester_chat_id"), (
            "a genuinely requester-less run must NOT have a chat_id invented")

    def test_resolve_intake_hard_fails_af_requester_missing(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path)
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0

        out_path = run_dir / "working" / "checkpoints" / ".engine-intake.json"
        r = _run_resolve_intake(run_dir, env, out_path)
        assert r.returncode == 4, (
            f"expected exit 4 (AF-REQUESTER-MISSING), got {r.returncode}: {r.stdout}{r.stderr}")
        assert "AF-REQUESTER-MISSING" in r.stderr
        assert not out_path.exists(), (
            "resolve_intake must write NOTHING when it cannot resolve a requester "
            "-- a partial/empty artifact handed to the engine is exactly FAULT-04")

    def test_engine_new_also_hard_fails_when_handed_a_chat_idless_intake(self, tmp_path):
        """Belt-and-suspenders: even if some OTHER caller bypassed
        resolve_intake.py entirely and handed presentation_job.py --new an
        intake with no requester, F1 must still fire. This fix must never
        weaken that gate -- it only ever adds a legitimate way to clear it."""
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path)
        bare_intake = tmp_path / "bare-intake.json"
        bare_intake.write_text(json.dumps({"presentation_type": "from_scratch"}), encoding="utf-8")
        r = _run_engine_new(run_dir, env, bare_intake)
        assert r.returncode != 0
        assert "no requester.chat_id in intake" in (r.stdout + r.stderr)
        assert not (run_dir / "state.json").exists()


# ---------------------------------------------------------------------------
# 5 -- priority: a real chat-surface requester always wins over the operator
# fallback when both are present.
# ---------------------------------------------------------------------------
class TestChatSurfaceWinsOverOperatorFallback:
    def test_dispatcher_env_wins_over_operator_env(self, tmp_path):
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, overrides={
            "PRESENTATION_REQUESTER_CHAT_ID": "REAL-CLIENT-9999",
            "OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-SHOULD-NOT-WIN",
        })
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "REAL-CLIENT-9999"


# ---------------------------------------------------------------------------
# 6 -- no-clobber: an intake that already carries a requester keeps it.
# ---------------------------------------------------------------------------
class TestNoClobber:
    def test_existing_requester_chat_id_is_not_overwritten(self, tmp_path):
        run_dir = tmp_path / "run"
        copy_dir = run_dir / "working" / "copy"
        copy_dir.mkdir(parents=True)
        (copy_dir / "intake.json").write_text(
            json.dumps({"requester_chat_id": "PRE-EXISTING-1234",
                       "requester_channel": "telegram"}), encoding="utf-8")
        env = _isolated_env(tmp_path, overrides={"OPERATOR_TELEGRAM_CHAT_ID": "SHOULD-NOT-APPEAR"})
        r = _drive_standard_intake(run_dir, env)
        assert r.returncode == 0, f"--complete failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "PRE-EXISTING-1234"


# ---------------------------------------------------------------------------
# 7 -- the two SIGNATURE-mode finalize paths this fix also had to patch.
# ---------------------------------------------------------------------------
class TestSignatureModeFinalizePaths:
    def test_sig_record_stamps_requester(self, tmp_path):
        """_sig_record() -- 'tooling that already ran the turn-gate through
        another surface' (the mini-app bridge's own completion path)."""
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, overrides={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-SIGREC-0001"})
        record_file = tmp_path / "sp-record.json"
        record_file.write_text(json.dumps({
            "signature_frame": "authority_teardown",
            "mode": "quick",
        }), encoding="utf-8")
        r = _run_driver(run_dir, env, "--signature", "--sig-record", str(record_file))
        assert r.returncode == 0, f"--signature --sig-record failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-SIGREC-0001"
        assert intake.get("deck_type") == "signature_presentation"

    def test_sig_finalize_via_full_turngate_stamps_requester(self, tmp_path):
        """_sig_finalize() -- the OTHER signature completion path: the real
        turn-gated QUICK/IN-DEPTH -> [8 Questions] -> frame -> finalize flow
        driven one answer at a time (--sig-answer), never a hand-authored
        record. QUICK mode skips the 8 Questions, so two turns are enough to
        reach _sig_finalize."""
        run_dir = tmp_path / "run"
        env = _isolated_env(tmp_path, overrides={"OPERATOR_TELEGRAM_CHAT_ID": "TESTOP-SIGFIN-0001"})
        r = _run_driver(run_dir, env, "--signature", "--sig-answer", "sp_mode", "QUICK")
        assert r.returncode == 0, f"--sig-answer sp_mode failed: {r.stdout}\n{r.stderr}"
        r = _run_driver(run_dir, env, "--signature", "--sig-answer", "signature_frame", "vault")
        assert r.returncode == 0, f"--sig-answer signature_frame failed: {r.stdout}\n{r.stderr}"
        intake = _read_intake_copy(run_dir)
        assert intake.get("requester_chat_id") == "TESTOP-SIGFIN-0001"
        assert intake.get("deck_type") == "signature_presentation"


# ---------------------------------------------------------------------------
# 8 -- operator_requester.py in isolation (unit-level, no subprocess).
# ---------------------------------------------------------------------------
class TestOperatorRequesterModule:
    def test_env_tier_beats_config_tier(self, tmp_path):
        cfg = tmp_path / "openclaw.json"
        cfg.write_text(json.dumps({"env": {"vars": {"OPERATOR_TELEGRAM_CHAT_ID": "FROM-CONFIG"}}}))
        chat_id, channel = opreq.resolve_operator_chat_id(
            config_path=cfg, env={"OPERATOR_TELEGRAM_CHAT_ID": "FROM-ENV"})
        assert chat_id == "FROM-ENV"
        assert channel == "telegram"

    def test_falls_back_to_config_tier_when_env_empty(self, tmp_path):
        cfg = tmp_path / "openclaw.json"
        cfg.write_text(json.dumps({"env": {"vars": {"OPERATOR_TELEGRAM_CHAT_ID": "FROM-CONFIG"}}}))
        chat_id, channel = opreq.resolve_operator_chat_id(config_path=cfg, env={})
        assert chat_id == "FROM-CONFIG"
        assert channel == "telegram"

    def test_tiered_alias_precedence(self):
        env = {
            "OPERATOR_HELP_CHAT_ID": "HELP-TIER",
            "OPERATOR_TELEGRAM_CHAT_ID": "TELEGRAM-TIER",
        }
        chat_id, _ = opreq.resolve_operator_chat_id(config_path=Path("/nonexistent"), env=env)
        assert chat_id == "HELP-TIER", "OPERATOR_HELP_CHAT_ID must outrank OPERATOR_TELEGRAM_CHAT_ID"

    def test_returns_empty_never_fabricates(self, tmp_path):
        missing_cfg = tmp_path / "does-not-exist.json"
        chat_id, channel = opreq.resolve_operator_chat_id(config_path=missing_cfg, env={})
        assert (chat_id, channel) == ("", "")

    def test_corrupt_config_file_degrades_to_empty_not_a_crash(self, tmp_path):
        cfg = tmp_path / "openclaw.json"
        cfg.write_text("{ not valid json")
        chat_id, channel = opreq.resolve_operator_chat_id(config_path=cfg, env={})
        assert (chat_id, channel) == ("", "")


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))

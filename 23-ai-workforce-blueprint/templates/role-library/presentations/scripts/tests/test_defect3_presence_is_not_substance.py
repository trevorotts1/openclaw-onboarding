"""DEFECT 3 -- Engine._run_agent_phase's poll loop must not complete a phase on
FILE PRESENCE ALONE when the substance verifier says the artifact is invalid.

THE DEFECT

v22.0.63 (commit 30b97d865) added the presence/no-mtime-growth TIEBREAKER: when
a phase's declared artifacts are all present but nothing is newer than this
dispatch's baseline, the state is ambiguous -- a stale partial from an earlier
blocked attempt (keep waiting) or a complete artifact inherited across an engine
restart (accept) -- so it asked phase_verifiers.verify() and assigned the answer:

    ok = v_ok

FIX 21 (commit 4019cf9b0) replaced that single line with a sidecar-pending
override and never restored it:

    if self._sidecar_pending(phase.id):
        ok = False

From that commit until this one, `v_ok` was computed and NEVER READ. With no
sidecar row pending, presence alone returned EXIT_OK -- an empty, truncated or
malformed artifact satisfied the wait loop exactly as a complete one did. FIX
21's own comment still asserts the contract it had just dropped ("the verifier
is only ever a TIEBREAKER when NO sidecar row is pending"), and the loop's
budget-timeout message ("exists but failed substance verification") was
unreachable, because nothing could carry a verifier FAIL out of the branch.

WHAT THESE TESTS PIN

The two states must be DISTINGUISHABLE: present-and-valid completes the phase;
present-and-INVALID keeps waiting on the identical cadence and then blocks
honestly. Both cases drive the SAME fixture through the SAME code path and
differ only in what the verifier returns -- so a regression that stops reading
v_ok makes case 2 look exactly like case 1 and fails here.

These tests deliberately write EVERY artifact P4-PROMPT declares (the
slide-*.txt glob AND working/prompts/infographic-prompt.txt). Its sibling file
tests/test_f16_agent_phase_wait_race.py writes only the slide files, so
_artifacts_present() is False there and the tiebreaker branch is never reached
at all -- which is why those tests neither caught this defect nor change
behaviour when it is fixed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SCRIPTS))

from presentation_job.manifest import Manifest  # noqa: E402
from presentation_job.phases import Engine  # noqa: E402
from presentation_job.state import StateStore, EXIT_OK, EXIT_GATE_BLOCKED  # noqa: E402
import phase_verifiers  # noqa: E402


# ---------------------------------------------------------------------------
# Fixture -- same manifest resolution + FakeClock idiom as
# tests/test_f16_agent_phase_wait_race.py.
# ---------------------------------------------------------------------------
def _canonical_manifest() -> Path:
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


def _engine(tmp_path) -> Engine:
    rd = tmp_path / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "intake.json").write_text(json.dumps(
        {"deck_type": "webinar", "creation_mode": "from_scratch"}))
    manifest = Manifest(_canonical_manifest())
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": "t", "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00", "manifest_path": str(manifest.path),
        "manifest_version": manifest.version, "manifest_sha256": manifest.sha256,
        "presentation_type": "from_scratch", "requester": {"chat_id": "tc"},
        "phases": [], "gates": {}, "waivers": [], "events": [], "sent": {},
        "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    return Engine(rd, manifest, store, state, dry_run=False)


class FakeClock:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start
        self.sleep_calls = 0

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleep_calls += 1
        self.now += seconds


def _install_clock(monkeypatch) -> FakeClock:
    clock = FakeClock()
    monkeypatch.setattr("time.time", clock.time)
    monkeypatch.setattr("time.sleep", clock.sleep)
    return clock


def _write_all_p4_artifacts(rd: Path, mtime: float) -> None:
    """Write EVERY artifact P4-PROMPT declares, all stale (older than the
    dispatch baseline) so the mtime-growth fast path can never fire and the
    presence/no-growth tiebreaker is the branch under test."""
    pdir = rd / "working" / "prompts"
    pdir.mkdir(parents=True, exist_ok=True)
    for p in (pdir / "slide-01.txt", pdir / "infographic-prompt.txt"):
        p.write_text("x" * 9500)
        os.utime(p, (mtime, mtime))


def _p4(eng: Engine):
    return eng.manifest.phase("P4-PROMPT")


# ---------------------------------------------------------------------------
# 1. PRESENT + VALID -> the phase completes (the v22.0.63 false-block fix,
#    still intact). This is the control: it proves the fixture genuinely
#    reaches the tiebreaker branch and that a PASS is accepted there.
# ---------------------------------------------------------------------------
def test_present_and_verifier_passes_completes_the_phase(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    phase = _p4(eng)
    clock = _install_clock(monkeypatch)
    _write_all_p4_artifacts(Path(eng.run_dir), clock.now - 400)

    monkeypatch.setattr(phase_verifiers, "verify", lambda *a, **k: (True, []))

    rc = eng._run_agent_phase(phase)

    assert rc == EXIT_OK, "a present, verify-PASSING artifact must satisfy the phase"
    assert clock.sleep_calls == 0, (
        "a PASS is the accept path -- it must not burn budget")


# ---------------------------------------------------------------------------
# 2. PRESENT + INVALID -> the loop must NOT exit on presence. THE DEFECT.
#    Same fixture, same branch, only the verifier's answer differs.
# ---------------------------------------------------------------------------
def test_present_but_verifier_fails_must_not_complete_on_presence(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    phase = _p4(eng)
    clock = _install_clock(monkeypatch)
    _write_all_p4_artifacts(Path(eng.run_dir), clock.now - 400)

    monkeypatch.setattr(
        phase_verifiers, "verify",
        lambda *a, **k: (False, ["AF-PROMPT-FLOOR: slide-25 missing"]))

    rc = eng._run_agent_phase(phase)

    assert rc != EXIT_OK, (
        "DEFECT 3: the poll loop completed the phase on FILE PRESENCE alone "
        "while its own substance verifier said the artifact is invalid -- "
        "v_ok was computed and never read")
    assert clock.sleep_calls > 0, (
        "a verifier FAIL must keep the identical wait cadence, not exit "
        "immediately")


# ---------------------------------------------------------------------------
# 3. The honest timeout message. Before this fix nothing could carry a verifier
#    FAIL out of the branch, so this reason string was unreachable.
# ---------------------------------------------------------------------------
def test_timeout_reason_names_substance_not_produced_nothing(tmp_path, monkeypatch):
    eng = _engine(tmp_path)
    phase = _p4(eng)
    clock = _install_clock(monkeypatch)
    _write_all_p4_artifacts(Path(eng.run_dir), clock.now - 400)

    monkeypatch.setattr(
        phase_verifiers, "verify",
        lambda *a, **k: (False, ["AF-PROMPT-FLOOR: slide-25 missing"]))

    eng._run_agent_phase(phase)

    blob = json.dumps(eng.state)
    assert "exists but failed substance verification" in blob, (
        "a present-but-invalid artifact must time out with the honest "
        "exists-but-failed reason, never the 'produced nothing' proxy")
    assert "AF-PROMPT-FLOOR: slide-25 missing" in blob, (
        "the real verifier's notes must reach the operator-facing reason")


# ---------------------------------------------------------------------------
# 4. Gate integrity: a truly absent artifact still blocks with 'produced
#    nothing' and never consults the verifier. Proves this fix changed WHEN
#    the tiebreaker is honoured, not WHETHER the loop can time out.
# ---------------------------------------------------------------------------
def test_absent_artifact_still_blocks_without_consulting_the_verifier(tmp_path,
                                                                      monkeypatch):
    eng = _engine(tmp_path)
    phase = _p4(eng)
    clock = _install_clock(monkeypatch)
    calls = []
    monkeypatch.setattr(phase_verifiers, "verify",
                        lambda *a, **k: calls.append(a) or (True, []))

    rc = eng._run_agent_phase(phase)

    assert rc != EXIT_OK
    assert not calls, "no artifact on disk -> the substance verifier must not run"
    assert clock.sleep_calls > 0
    assert "produced nothing" in json.dumps(eng.state)

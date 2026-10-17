"""S06-05 — persistence roots, crash/restart harness, client isolation.

Covers the S06-05 root fixes and their repair-in-place fallbacks:
  * ghl_run_state.default_state_root() — durable root via the ONE
    sanctioned primitive, env override first, legacy root last; a run
    started before the move stays resumable from the legacy root
    (SK6002 repair-in-place, never a silent move).
  * ghl_builder.ledger_root() — the per-page ledger off ephemeral /tmp;
    legacy /tmp records still read, writes merge against them so the
    never-rewind guard compares against pre-move state.
  * ghl_vps_mount_proof path set — the five persistence paths in ONE
    per-box receipt; pre-only honesty per path; the single-path receipt
    home is unchanged.
  * Crash/restart harness — run state resumes after a root move; PARK
    state persists across processes while leases expire by TTL.
  * Two-client isolation — per-location breaker files and session names;
    the box-level PARK marker is shared BY DESIGN (recorded, not fixed).
  * Gap-14 isolation guard — fixture writes under full overrides never
    land in the REAL durable roots (the 2026-07-07 incident: hermetic
    tests parked the operator's real box).

Hermetic: tmp dirs and injected seams only. NO network, NO live GHL.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_TOOLS_DIR = _TESTS_DIR.parent / "tools"
for _p in (str(_TOOLS_DIR), str(_TESTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import agent_browser_orphan_audit as audit  # noqa: E402
import ghl_builder as gb  # noqa: E402
import ghl_run_state as rs  # noqa: E402
import ghl_vps_mount_proof as mp  # noqa: E402
import ghl_vps_provision_check as vpc  # noqa: E402

SPECS = [rs.PhaseSpec("survey", "Survey"), rs.PhaseSpec("build", "Build"),
         rs.PhaseSpec("publish", "Publish")]


def mounts_ext4():
    return [("/dev/vda1", "/", "ext4", "rw,relatime")]


# ── A. run-state root resolution + legacy fallback ──────────────────────────

def test_state_root_prefers_durable_root(tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_RUN_STATE_ROOT", raising=False)
    monkeypatch.setattr(rs, "_durable_root", lambda: str(tmp_path / "durable"))
    assert rs.default_state_root() == str(tmp_path / "durable" / "skill6-runs")


def test_state_root_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("GHL_RUN_STATE_ROOT", str(tmp_path / "explicit"))
    monkeypatch.setattr(rs, "_durable_root", lambda: str(tmp_path / "durable"))
    assert rs.default_state_root() == str(tmp_path / "explicit")


def test_state_root_falls_back_to_legacy(tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_RUN_STATE_ROOT", raising=False)
    monkeypatch.setattr(rs, "_durable_root", lambda: "")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert rs.default_state_root() == str(
        tmp_path / ".openclaw" / "skill6-runs")
    assert rs.default_state_root() == rs.legacy_state_root()


def test_run_started_before_move_resumes_from_legacy(tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_RUN_STATE_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    legacy = rs.legacy_state_root()
    st = rs.RunState.start("fixture-builder", SPECS,
                           run_id="run-legacy-1", state_root=legacy)
    st.mark_done("survey")
    del st
    # The box is onboarded AFTER the run started: the durable root moves.
    durable = tmp_path / "durable"
    monkeypatch.setattr(rs, "_durable_root", lambda: str(durable))
    assert rs.default_state_root() == str(durable / "skill6-runs")
    loaded = rs.RunState.load("run-legacy-1", "fixture-builder", specs=SPECS)
    # Repair-in-place: found at legacy, flagged, still WRITES to legacy.
    assert loaded.doc.get("state_root_legacy_fallback") is True
    assert loaded.state_root == legacy
    assert loaded.is_done("survey")
    assert loaded.doc["attempts"] == 2
    assert not (durable / "skill6-runs" / "run-legacy-1.json").exists()
    assert Path(loaded.path).exists()


def test_new_run_starts_at_the_new_root(tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_RUN_STATE_ROOT", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    durable = tmp_path / "durable"
    monkeypatch.setattr(rs, "_durable_root", lambda: str(durable))
    st = rs.RunState.start("fixture-builder", SPECS, run_id="run-new-1")
    assert st.state_root == str(durable / "skill6-runs")
    assert Path(st.path).exists()


# ── B. ledger root resolution + legacy merge ────────────────────────────────

def test_ledger_root_prefers_durable_root(tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_LEDGER_ROOT", raising=False)
    monkeypatch.setattr(gb, "_durable_root_for_ledger",
                        lambda: str(tmp_path / "durable"))
    assert gb.ledger_root() == str(tmp_path / "durable" / "skill6-ledgers")
    assert gb.ledger_root_is_ephemeral() is False


def test_ledger_root_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("GHL_LEDGER_ROOT", str(tmp_path / "explicit"))
    monkeypatch.setattr(gb, "_durable_root_for_ledger",
                        lambda: str(tmp_path / "durable"))
    assert gb.ledger_root() == str(tmp_path / "explicit")


def test_ledger_root_tmp_fallback_is_labelled_ephemeral(monkeypatch):
    monkeypatch.delenv("GHL_LEDGER_ROOT", raising=False)
    monkeypatch.setattr(gb, "_durable_root_for_ledger", lambda: "")
    assert gb.ledger_root() == "/tmp"
    assert gb.ledger_root_is_ephemeral() is True
    assert gb.ledger_root_is_ephemeral({"GHL_LEDGER_ROOT": "/tmp/x"}) is True
    assert gb.ledger_root_is_ephemeral({"GHL_LEDGER_ROOT": "/data/x"}) is False


def test_ledger_write_read_round_trip_and_resume(tmp_path, monkeypatch):
    monkeypatch.setenv("GHL_LEDGER_ROOT", str(tmp_path / "ledgers"))
    monkeypatch.setattr(gb, "_LEGACY_LEDGER_BASE", str(tmp_path / "no-legacy"))
    path = gb.ledger_write("run-1", "Funnel A", "Step One", "created")
    assert path.startswith(str(tmp_path / "ledgers"))
    assert gb.ledger_read("run-1", "Funnel A", "Step One")["state"] == "created"
    gb.ledger_write("run-1", "Funnel A", "Step One", "previewed")
    plan = gb.resume_point("run-1", {
        "funnel_name": "Funnel A",
        "pages": [{"name": "Step One", "path": "/p", "mode": "create"}],
    })
    assert plan[0]["current_state"] == "previewed"
    assert plan[0]["resume_at"] == "published"
    assert plan[0]["skip_create"] is True


def test_ledger_never_rewinds_across_the_root_move(tmp_path, monkeypatch):
    legacy_base = tmp_path / "legacy-tmp"
    monkeypatch.setattr(gb, "_LEGACY_LEDGER_BASE", str(legacy_base))
    # A pre-move record lives ONLY at the legacy location, at "previewed".
    legacy_path = Path(gb._legacy_ledger_path("run-2", "Funnel", "Step"))
    legacy_path.parent.mkdir(parents=True)
    legacy_path.write_text(json.dumps(
        {"funnel": "Funnel", "step": "Step", "state": "previewed",
         "updated_at": 1}), encoding="utf-8")
    monkeypatch.setenv("GHL_LEDGER_ROOT", str(tmp_path / "ledgers"))
    # The legacy record still reads (repair-in-place read fallback).
    assert gb.ledger_read("run-2", "Funnel", "Step")["state"] == "previewed"
    # A post-move write of an EARLIER state must not rewind the page: the
    # merge base is the legacy record, and the write lands at the new root.
    new_path = gb.ledger_write("run-2", "Funnel", "Step", "page-saved")
    assert new_path.startswith(str(tmp_path / "ledgers"))
    assert gb.ledger_read("run-2", "Funnel", "Step")["state"] == "previewed"
    plan = gb.resume_point("run-2", {
        "funnel_name": "Funnel",
        "pages": [{"name": "Step", "path": "/p", "mode": "create"}],
    })
    assert plan[0]["resume_at"] == "published"


# ── C. mount-proof path set ─────────────────────────────────────────────────

def _pathset(tmp_path):
    base = tmp_path / "box"
    paths = {}
    for key in mp.PATHSET_KEYS:
        p = base / key
        p.mkdir(parents=True)
        paths[key] = str(p)
    paths["evidence_base"] = ""  # unresolvable on this fixture box
    return paths


def test_pathset_round_trip_all_survive(tmp_path):
    paths = _pathset(tmp_path)
    pre = mp.pathset_pre(paths, "run-ps-1", mounts_reader=mounts_ext4,
                         platform="linux")
    assert set(pre) == {k for k, v in paths.items() if v}
    post = mp.pathset_post(paths, "run-ps-1")
    receipt = mp.build_pathset_receipt(paths, pre, post, run_id="run-ps-1",
                                       box_label="fixture-box")
    assert receipt["schema"] == "skill6-vps-mount-pathset/1"
    for key, row in receipt["paths"].items():
        if not paths[key]:
            assert row["survived_recreate"] is None
            assert row["live_leg_status"].startswith("SKIPPED")
        else:
            assert row["survived_recreate"] is True, row
            assert row["live_leg_status"] == "complete"


def test_pathset_pre_only_honesty(tmp_path):
    paths = _pathset(tmp_path)
    pre = mp.pathset_pre(paths, "run-ps-2", mounts_reader=mounts_ext4,
                         platform="linux")
    receipt = mp.build_pathset_receipt(paths, pre, None, run_id="run-ps-2")
    for key, row in receipt["paths"].items():
        assert row["survived_recreate"] is None
        if paths[key]:
            assert row["live_leg_status"].startswith("PRE-ONLY"), row


def test_pathset_one_wiped_path_reports_not_survived(tmp_path):
    paths = _pathset(tmp_path)
    pre = mp.pathset_pre(paths, "run-ps-3", mounts_reader=mounts_ext4,
                         platform="linux")
    wiped = paths["run_state_root"]
    shutil.rmtree(wiped)
    Path(wiped).mkdir(parents=True)  # recreated EMPTY, as a container layer would be
    post = mp.pathset_post(paths, "run-ps-3")
    receipt = mp.build_pathset_receipt(paths, pre, post, run_id="run-ps-3")
    assert receipt["paths"]["run_state_root"]["survived_recreate"] is False
    assert receipt["paths"]["secrets_dir"]["survived_recreate"] is True


def test_pathset_receipt_homes_and_single_path_unchanged(tmp_path):
    ev = str(tmp_path / "evidence")
    receipt = mp.build_pathset_receipt(_pathset(tmp_path), {}, None,
                                       run_id="run-ps-4")
    written = mp.write_pathset_receipt(ev, receipt)
    assert written == os.path.join(ev, "routing",
                                   "vps-mount-pathset-receipt.json")
    assert mp.read_pathset_receipt(ev)["run_id"] == "run-ps-4"
    # The single-path receipt home is untouched by the path-set addition.
    assert mp.receipt_path(ev) == os.path.join(
        ev, "routing", "vps-mount-receipt.json")
    assert mp.read_pathset_receipt(str(tmp_path / "empty")) is None


def test_default_pathset_shape():
    paths = mp.default_pathset(durable_root="/data/.openclaw", home="/home/node",
                               evidence_base="/ev", secrets_dir="/sec")
    assert paths["agent_browser_state"] == "/home/node/.agent-browser"
    assert paths["evidence_base"] == "/ev"
    assert paths["run_state_root"] == "/data/.openclaw/skill6-runs"
    assert paths["playwright_data_dir"] == (
        "/data/.openclaw/playwright-data/ghl-install-pages")
    assert paths["secrets_dir"] == "/sec"
    unresolved = mp.default_pathset(durable_root="", home="/home/node")
    assert unresolved["run_state_root"] == ""
    assert unresolved["playwright_data_dir"] == ""


# ── D. crash/restart harness ────────────────────────────────────────────────

def test_run_state_crash_resume_skips_completed_mutating_phases(
        tmp_path, monkeypatch):
    monkeypatch.delenv("GHL_RUN_STATE_ROOT", raising=False)
    durable = tmp_path / "durable"
    monkeypatch.setattr(rs, "_durable_root", lambda: str(durable))
    st = rs.RunState.start("fixture-builder", SPECS, run_id="run-crash-1")
    st.mark_done("survey")
    st.mark_running("build")
    del st  # the crash: process dies mid-"build"
    loaded = rs.RunState.load("run-crash-1", "fixture-builder", specs=SPECS)
    assert loaded.should_skip("survey") is True
    assert loaded.is_done("build") is False
    assert loaded.first_incomplete_mutating_phase() == "build"
    assert loaded.resume_phase() == "build"


def _bash_env(tmp_path, **extra):
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(tmp_path / "home"),
        "TMPDIR": str(tmp_path / "tmpdir"),
        "BM_DURABLE_ROOT_OVERRIDE": str(tmp_path / "durable"),
    }
    env.update(extra)
    return env


def _bash(script, env):
    return subprocess.run(["/bin/bash", "-c", script], capture_output=True,
                          text=True, env=env, timeout=120)


def test_park_persists_across_processes_while_leases_expire(tmp_path):
    loc = "s06-05-park-loc"
    env = _bash_env(tmp_path, GHL_LOCATION_ID=loc, AB_BREAKER_MAX="2",
                    AB_MAX_OPENS_PER_HOUR="99")
    sh = str(_TOOLS_DIR / "browser_manager.sh")
    # Process 1: two opens, then the check trips the breaker and parks.
    p1 = _bash(
        f'source "{sh}" >/dev/null 2>&1; '
        "_bm_breaker_record_open; _bm_breaker_record_open; "
        "( bm_breaker_check ) >/dev/null 2>&1; echo rc=$?",
        env)
    assert "rc=75" in p1.stdout, p1.stdout + p1.stderr
    park = tmp_path / "durable" / "workspace" / ".park"
    assert (park / f"agent-browser-{loc}.count").exists()
    assert (park / f"agent-browser-{loc}.BLOCKED").exists()
    assert (park / "workforce-build.parked").exists()
    # Process 2 (a "restart"): no opens recorded here, yet the durable
    # PARK marker still refuses — PARK state persists across processes.
    p2 = _bash(
        f'source "{sh}" >/dev/null 2>&1; '
        "( bm_breaker_check ) >/dev/null 2>&1; echo rc=$?",
        env)
    assert "rc=75" in p2.stdout, p2.stdout + p2.stderr
    # Leases, by contrast, are TTL state: live inside the TTL, gone after
    # it — they do NOT persist like the PARK marker does.
    lease_dir = tmp_path / "tmpdir" / "agent-browser" / "leases"
    lease_dir.mkdir(parents=True, exist_ok=True)
    session = f"ghl-skill6-{loc}"
    (lease_dir / f"{session}.lease").write_text(json.dumps(
        {"started_epoch": 1_000_000, "ttl_sec": 60}), encoding="utf-8")
    assert session in audit._live_session_names_from_leases(
        str(lease_dir), now=1_000_030)
    assert session not in audit._live_session_names_from_leases(
        str(lease_dir), now=1_000_600)


# ── E. two-client isolation on one box view ─────────────────────────────────

def test_two_locations_breaker_files_and_session_names(tmp_path):
    sh = str(_TOOLS_DIR / "browser_manager.sh")
    park = tmp_path / "durable" / "workspace" / ".park"

    def run_loc(loc, script_extra=""):
        env = _bash_env(tmp_path, GHL_LOCATION_ID=loc, AB_BREAKER_MAX="2",
                        AB_MAX_OPENS_PER_HOUR="99")
        return _bash(
            f'source "{sh}" >/dev/null 2>&1; '
            f'echo "session=$(bm_session_name)"; {script_extra}',
            env)

    # Location A trips its breaker on the shared box view.
    pa = run_loc("loc-a",
                 "_bm_breaker_record_open; _bm_breaker_record_open; "
                 "( bm_breaker_check ) >/dev/null 2>&1; echo rc=$?")
    assert "session=ghl-skill6-loc-a" in pa.stdout
    assert "rc=75" in pa.stdout
    assert (park / "agent-browser-loc-a.count").exists()
    assert (park / "agent-browser-loc-a.BLOCKED").exists()
    # A's activity wrote NOTHING under B's per-location names.
    assert not (park / "agent-browser-loc-b.count").exists()
    assert not (park / "agent-browser-loc-b.BLOCKED").exists()
    # Location B on the SAME box view refuses too — via the box-level
    # PARK marker a trip writes BY DESIGN (recorded in ENV-MATRIX.md; the
    # per-location files stay isolated, the box park is shared on purpose).
    pb = run_loc("loc-b", "( bm_breaker_check ) >/dev/null 2>&1; echo rc=$?")
    assert "session=ghl-skill6-loc-b" in pb.stdout
    assert "rc=75" in pb.stdout
    assert not (park / "agent-browser-loc-b.count").exists()
    assert not (park / "agent-browser-loc-b.BLOCKED").exists()
    # Location B on its OWN box view (fresh roots) is unaffected by A.
    env_b = _bash_env(tmp_path / "box-b", GHL_LOCATION_ID="loc-b",
                      AB_BREAKER_MAX="2", AB_MAX_OPENS_PER_HOUR="99")
    (tmp_path / "box-b").mkdir(parents=True, exist_ok=True)
    pb2 = _bash(
        f'source "{sh}" >/dev/null 2>&1; '
        "( bm_breaker_check ) >/dev/null 2>&1; echo rc=$?",
        env_b)
    assert "rc=0" in pb2.stdout, pb2.stdout + pb2.stderr


# ── F. gap-14 isolation guard ───────────────────────────────────────────────

def test_gap14_fixture_writes_never_touch_real_durable_roots(
        tmp_path, monkeypatch):
    token = "s06-05-gap14"
    real_home = Path(os.path.expanduser("~"))  # BEFORE the HOME override
    real_roots = [
        real_home / ".openclaw" / "skill6-provisioning",
        real_home / ".openclaw" / "skill6-runs",
        real_home / ".openclaw" / "skill6-ledgers",
        real_home / ".openclaw" / "workspace" / ".park",
    ]

    def leaked():
        hits = []
        for root in real_roots:
            if root.exists():
                for p in root.rglob("*"):
                    if token in p.name:
                        hits.append(str(p))
        return hits

    assert leaked() == []
    # Aim EVERY override at tmp (the gap-14 discipline), then exercise
    # every S06-05 writer: verifier receipts, the ledger, run state.
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GHL_LEDGER_ROOT", str(tmp_path / "ledgers"))
    monkeypatch.setenv("GHL_RUN_STATE_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("BM_DURABLE_ROOT_OVERRIDE", str(tmp_path / "durable"))
    monkeypatch.setattr(rs, "_durable_root", lambda: str(tmp_path / "durable"))
    paths = {k: str(tmp_path / "paths" / k) for k in mp.PATHSET_KEYS}
    for p in paths.values():
        Path(p).mkdir(parents=True, exist_ok=True)
    receipt = vpc.verify_provisioning(
        client=f"{token}-client", env={}, paths=paths, stores=[],
        service_uid=os.getuid(), service_gid=os.getegid(),
        mounts_reader=mounts_ext4, platform="linux",
        box={"durable_root": str(tmp_path / "durable"), "is_vps": True,
             "supervisor": "pm2-or-systemd", "platform": "linux"})
    vpc.write_receipts(receipt)
    gb.ledger_write(f"{token}-run", "Funnel", "Step", "created")
    rs.RunState.start("fixture-builder", SPECS, run_id=f"{token}-run")
    # Sanity: the fixture state really landed — under tmp.
    assert (tmp_path / "durable" / "skill6-provisioning"
            / f"{token}-client" / "provisioning-receipt.json").exists()
    assert (tmp_path / "ledgers" / f"{token}-run").exists()
    assert (tmp_path / "runs" / f"{token}-run.json").exists()
    # And NOTHING leaked into the operator's real durable roots.
    assert leaked() == []

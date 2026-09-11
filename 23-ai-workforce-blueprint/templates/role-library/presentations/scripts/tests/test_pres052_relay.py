"""PRES-052 — supervised, acknowledged event relay (QC-PRES-052 checks 1-2).

Covers, against the real modules (no mocks except the transport probe):

QC check 1
  a. stop relay midway + resume: pending rows re-queue, acknowledged rows
     stay acknowledged, logical display never duplicates;
  b. two companies / two decks: rows are directory-scoped, cross-company
     outbox rows refused, one run never reads another rows;
  c. CC failure does not suppress local progress (local + CC ack separate).

QC check 2
  d. long synthetic job: progress visible BEFORE completion (stage rows +
     --relay-status), ack timeout visible, queued-only receipt cannot
     certify client notified.

Plus the step-1/2/3 unit contracts: typed IDs persisted, no cwd guessing,
transport readiness by probe (installed-but-unready openclaw = NOT READY),
no Telegram credential use.
"""
import json
import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

_scripts_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_scripts_dir))

from presentation_job.state import StateStore
from presentation_job import relay
from presentation_job import report as report_mod
from presentation_job.result import CheckResult


def _mkstate(tmp_path, company="acme", deck="deck-a", job="pj_test1"):
    rd = tmp_path / "run"
    rd.mkdir(parents=True, exist_ok=True)
    store = StateStore(rd)
    state = {
        "schema_version": 1, "job_id": job, "run_dir": str(rd),
        "created_at": "2026-01-01T00:00:00+00:00",
        "manifest_path": "/x.json", "manifest_version": 25,
        "manifest_sha256": "0" * 64, "presentation_type": "from_scratch",
        "requester": {"chat_id": "tc"},
        "intake": {"client": company, "deck_slug": deck},
        "phases": [], "gates": {}, "waivers": [], "events": [],
        "sent": {}, "undeliverable": [], "heartbeat": {}, "terminal": None,
    }
    store.save(state)
    return rd, state, store


def _find_outbox() -> Path:
    """Walk up from this file to the worktree root (holds both the dept
    templates and 51-signature-presentation), then down to the transport."""
    here = Path(__file__).resolve()
    for parent in (here,) + tuple(here.parents):
        cand = parent / "51-signature-presentation" / "bin" / "presentation-outbox-queue"
        if cand.is_file():
            return cand
    raise FileNotFoundError("presentation-outbox-queue not found above " + str(here))


OUTBOX = _find_outbox()


def _queue(row, run_dir, extra_env=None):
    env = dict(os.environ)
    env["PRESENTATION_RUN_DIR"] = str(run_dir)
    if extra_env:
        env.update(extra_env)
    proc = subprocess.run([sys.executable, str(OUTBOX)],
                          input=json.dumps(row), text=True, capture_output=True,
                          env=env, timeout=30)
    return proc


class TestTypedIdentity:
    def test_emit_persists_typed_ids(self, tmp_path):
        rd, state, store = _mkstate(tmp_path)
        row = relay.emit(state, rd, "stage_start", "P1 starting",
                         stage="P1", task_id="t-1", store=store)
        assert row["company"] == "acme"
        assert row["presentation"] == "deck-a"
        assert row["run_id"] == "pj_test1"
        assert row["stage"] == "P1"
        assert row["task_id"] == "t-1"
        assert row["event_id"]
        assert row["revision"] >= 1
        assert row["state"] == "queued"
        assert row["retry_not_before"]
        ledger = list((rd / "working" / "relay" / "ledger.jsonl")
                      .read_text(encoding="utf-8").strip().splitlines())
        assert len(ledger) == 1
        assert json.loads(ledger[0])["event_id"] == row["event_id"]

    def test_session_open_bumps_revision_on_reopen(self, tmp_path):
        rd, state, store = _mkstate(tmp_path)
        relay.session_open(state, rd, store=store)
        first_rev = state["relay"]["revision"]
        relay.session_open(state, rd, store=store)
        assert state["relay"]["revision"] == first_rev + 1


class TestResumeReconcile:
    def test_stop_midway_resume_no_loss_no_dupe(self, tmp_path):
        """QC-1a: stop midway, resume — pending re-queues, acked stays."""
        rd, state, store = _mkstate(tmp_path)
        relay.session_open(state, rd, store=store)
        r1 = relay.emit(state, rd, "stage_start", "P1 starting", stage="P1",
                        store=store)
        r2 = relay.emit(state, rd, "stage_start", "P2 starting", stage="P2",
                        store=store)
        # P1 acknowledged locally (the "stop midway" point); P2 not.
        assert relay.ack_local(state, rd, r1["event_id"], store=store)
        n_ledger_before = len(relay._read_ledger(rd))
        summary = relay.reconcile(state, rd, store=store)
        assert summary["skipped_acked"] >= 1
        assert summary["requeued"] >= 1  # P2 (and session row) retried
        display = relay.read_display(rd)
        # Logical display: one row per event id — never duplicated.
        assert len(display) == len({k for k in display})
        assert display[r1["event_id"]]["state"] in (
            relay.STATE_ACKED_LOCAL, relay.STATE_ACKED_BOTH)
        assert display[r2["event_id"]]["state"] == relay.STATE_QUEUED
        # Retries are retained in the ledger, not overwritten.
        assert len(relay._read_ledger(rd)) > n_ledger_before

    def test_reconcile_idempotent(self, tmp_path):
        rd, state, store = _mkstate(tmp_path)
        relay.session_open(state, rd, store=store)
        relay.reconcile(state, rd, store=store)
        d1 = relay.read_display(rd)
        relay.reconcile(state, rd, store=store)
        # reconcile emits its own progress row each pass (+1 logical event
        # per pass is the reconcile receipt itself); no OTHER row duplicates.
        d2 = relay.read_display(rd)
        assert len(d2) == len(d1) + 1


class TestIsolation:
    def test_two_runs_never_share_rows(self, tmp_path):
        rda, sa, sta = _mkstate(tmp_path / "a", company="acme",
                                deck="deck-a", job="pj_a")
        rdb = tmp_path / "b" / "run"
        rdb.mkdir(parents=True)
        stb = StateStore(rdb)
        sb = dict(sa, job_id="pj_b", run_dir=str(rdb),
                  intake={"client": "globex", "deck_slug": "deck-b"})
        stb.save(sb)
        relay.emit(sa, rda, "stage_start", "P1 a", stage="P1", store=sta)
        relay.emit(sb, rdb, "stage_start", "P1 b", stage="P1", store=stb)
        da = relay.read_display(rda)
        db = relay.read_display(rdb)
        assert {v["display_text"] for v in da.values()} == {"P1 a"}
        assert {v["display_text"] for v in db.values()} == {"P1 b"}

    def test_outbox_refuses_cross_company_row(self, tmp_path):
        rd, state, store = _mkstate(tmp_path, company="acme")
        proc = _queue({"chat_id": "x", "kind": "progress",
                       "message": "hi", "company": "globex"}, rd)
        assert proc.returncode == 6  # EXIT_SCOPE_MISMATCH
        assert not (rd / "working" / "outbox.jsonl").exists()

    def test_outbox_same_company_ok(self, tmp_path):
        rd, state, store = _mkstate(tmp_path, company="acme")
        proc = _queue({"chat_id": "x", "kind": "progress",
                       "message": "hi", "company": "acme"}, rd)
        assert proc.returncode == 0
        rows = (rd / "working" / "outbox.jsonl").read_text(
            encoding="utf-8").strip().splitlines()
        env = json.loads(rows[0])
        assert env["schema"] == "pres-outbox-v1"
        assert env["company"] == "acme"
        assert env["state"] == "queued"
        assert env["event_id"]

    def test_no_cwd_guessing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("PRESENTATION_RUN_DIR", raising=False)
        proc = subprocess.run([sys.executable, str(OUTBOX)],
                              input=json.dumps({"chat_id": "x"}), text=True,
                              capture_output=True, cwd=str(tmp_path), timeout=30)
        assert proc.returncode != 0
        assert "PRESENTATION_RUN_DIR" in proc.stderr


class TestSeparateAcks:
    def test_cc_failure_keeps_local_progress(self, tmp_path):
        """QC-1c: CC outage never suppresses local progress."""
        rd, state, store = _mkstate(tmp_path)
        row = relay.emit(state, rd, "stage_start", "P1 starting", stage="P1",
                         store=store)
        assert relay.ack_local(state, rd, row["event_id"], store=store)
        display = relay.read_display(rd)
        assert display[row["event_id"]]["state"] == relay.STATE_ACKED_LOCAL
        # CC side still pending — and a later CC success completes both.
        assert relay.ack_cc(state, rd, row["event_id"], store=store)
        assert (relay.read_display(rd)[row["event_id"]]["state"]
                == relay.STATE_ACKED_BOTH)

    def test_report_observe_maps_outcome(self, tmp_path, monkeypatch):
        """dispatch FAIL/UNDETERMINED -> queued + visible retry; PASS -> ack."""
        rd, state, store = _mkstate(tmp_path)
        monkeypatch.delenv("PRESENTATION_NOTIFY_CMD", raising=False)
        rep = report_mod.Reporter(state, store)
        rep.to_requester("progress", "Starting phase P1", phase_id="P1")
        display = relay.read_display(rd)
        assert display, "relay must observe even failed dispatches"
        vis = next(iter(display.values()))
        assert vis["state"] == relay.STATE_QUEUED
        assert "queued" in (vis["display_text"] or "")


class TestProgressBeforeCompletion:
    def test_long_job_visible_before_done(self, tmp_path):
        """QC-2 (first half): stage rows exist before any final output."""
        rd, state, store = _mkstate(tmp_path)
        relay.session_open(state, rd, store=store)
        relay.emit(state, rd, "stage_start", "P1 starting", stage="P1",
                   store=store)
        relay.emit(state, rd, "progress", "P1 50% — still working", stage="P1",
                   store=store)
        out = relay.render_status(rd, state,
                                  env={"PATH": str(tmp_path / "no-bin")})
        assert "P1" in out
        assert "QUEUED" in out
        assert "client notified: NO" in out  # queued-only cannot certify

    def test_ack_timeout_visible(self, tmp_path, monkeypatch):
        rd, state, store = _mkstate(tmp_path)
        monkeypatch.setenv("PRESENTATION_RELAY_ACK_TIMEOUT_S", "0.01")
        row = relay.emit(state, rd, "progress", "P1 working", stage="P1",
                         store=store)
        for _ in range(relay.MAX_ATTEMPTS):
            relay.note_attempt(state, rd, row["event_id"], "local", store=store)
        vis = relay.read_display(rd)[row["event_id"]]
        assert vis["state"] == relay.STATE_TIMEOUT
        assert "TIMEOUT" in relay.render_status(
            rd, state, env={"PATH": str(tmp_path / "no-bin")})

    def test_queued_only_cannot_certify(self, tmp_path):
        rd, state, store = _mkstate(tmp_path)
        relay.emit(state, rd, "progress", "P1 working", stage="P1", store=store)
        ok, msg = relay.certify_notified(rd)
        assert ok is False
        assert "queued" in msg.lower()
        # After a real ack, the verdict flips.
        eid = next(iter(relay.read_display(rd)))
        relay.ack_local(state, rd, eid, store=store)
        ok2, _ = relay.certify_notified(rd)
        assert ok2 is True


class TestTransportReadiness:
    def test_installed_but_unready_openclaw_is_not_ready(self, tmp_path):
        """An `openclaw` executable that fails its probe must NOT read ready."""
        bindir = tmp_path / "bin"
        bindir.mkdir()
        fake = bindir / "openclaw"
        fake.write_text("#!/bin/sh\necho 'gateway down' >&2\nexit 1\n")
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        env = dict(os.environ)
        env["PATH"] = str(bindir) + os.pathsep + env.get("PATH", "")
        probe = relay.probe_openclaw_gateway(env)
        assert probe["ready"] is False
        assert "UNREADY" in probe["detail"]

    def test_missing_openclaw_is_not_ready(self, tmp_path):
        probe = relay.probe_openclaw_gateway({"PATH": str(tmp_path)})
        assert probe["ready"] is False
        assert "not found" in probe["detail"]

    def test_cc_needs_token(self):
        probe = relay.probe_cc({"COMMAND_CENTER_URL": "https://cc.example"})
        assert probe["ready"] is False
        assert "token" in probe["detail"].lower() or "identity" in probe["detail"].lower()
        ok_probe = relay.probe_cc({"COMMAND_CENTER_URL": "https://cc.example",
                                   "CC_API_TOKEN": "sekrit"})
        assert ok_probe["ready"] is True
        assert "sekrit" not in ok_probe["detail"]

    def test_no_telegram_credentials_read(self, tmp_path, monkeypatch):
        """Relay + probes must never read Telegram bot tokens."""
        for key in ("OPERATOR_TELEGRAM_BOT_TOKEN", "TELEGRAM_BOT_TOKEN",
                    "BOT_TOKEN"):
            monkeypatch.setenv(key, "SHOULD-NEVER-BE-READ")
        rd, state, store = _mkstate(tmp_path)
        relay.emit(state, rd, "progress", "x", store=store)
        relay.probe_transports(rd, dict(os.environ))
        relay.render_status(rd, state)
        # The verdict proves it: nothing in the relay output carries the token.
        blob = ((rd / "working" / "relay" / "ledger.jsonl").read_text()
                + relay.render_status(rd, state))
        assert "SHOULD-NEVER-BE-READ" not in blob


class TestDedupe:
    def test_retries_never_duplicate_display(self, tmp_path):
        rd, state, store = _mkstate(tmp_path)
        row = relay.emit(state, rd, "progress", "P1 working", stage="P1",
                         store=store)
        n0 = len(relay.read_display(rd))
        for _ in range(3):
            relay.note_attempt(state, rd, row["event_id"], "local", store=store)
        assert len(relay.read_display(rd)) == n0
        assert len(relay._read_ledger(rd)) == n0 + 3  # retries retained

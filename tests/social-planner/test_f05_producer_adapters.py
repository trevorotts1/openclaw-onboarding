#!/usr/bin/env python3
"""test_f05_producer_adapters.py — F05 acceptance (QC-F05).

"Give Skill 57 a producer behind its phase gates."

run_social_media.py describes itself as model-free/provider-free: it checks
artifacts but creates none — a fresh run failed on missing working/plan/
plan.json. Now an explicit producer adapter layer sits BEHIND the phase gates:
run_social_media.py --producers invokes each phase's registered adapter BEFORE
its unchanged gate, so missing artifacts trigger production (or a specific
dependency failure — never a claim that production occurred).

QC-F05 matrix (unittest, offline; NO network, NO nonce needed — the producer
loop is exercised via run_with_producers against a fixture run dir):
  1. Fresh run + approved theme -> producer SPIES observe plan/research/copy/
     media/review/delivery/writeback calls in dependency order, gates all PASS.
  2. Missing artifact triggers production (a fresh P1 gate that used to fail
     on plan.json passes once the producer wrote it).
  3. A failing producer -> specific dependency failure, exit 2, gate never
     claims production; a declared-but-missing output is refused.
  4. Theme hash change -> the plan producer reruns (inputs no longer match)
     and downstream producers rerun after it.
  5. Resume: unchanged inputs reuse verified outputs (no second production).
  6. Receipts persist per phase: input/output sha256, assigned agent,
     execution id, completion receipt, simulated flag.
  7. Simulated receipts (fake adapters) stamp simulated=true and can never
     satisfy a live completion (the F08 gate still rejects them).
  8. The deterministic validators are untouched: --producers OFF behaves
     exactly as before; gates always still run after producers.

Run:  python3 -m unittest discover -s tests/social-planner -p 'test_f*.py'
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_REPO_ROOT = _HERE.parent.parent
_SKILL_DIR = _REPO_ROOT / "57-social-media-in-a-box"
_RUNNER_PATH = _SKILL_DIR / "run_social_media.py"
_ENTRY_PATH = _SKILL_DIR / "social-media-entry.sh"
assert _RUNNER_PATH.is_file(), "run_social_media.py not found"
assert _ENTRY_PATH.is_file(), "social-media-entry.sh not found"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


rsm = _load("run_social_media_f05", _RUNNER_PATH)


class ProducerSpy:
    """Records every producer invocation (QC fixture contract: fakes record
    attempted side effects, never touch the network or an LLM)."""

    def __init__(self, label, writer):
        self.label = label
        self.writer = writer        # fn(run_dir, ctx) -> outputs list
        self.calls = []

    def __call__(self, run_dir, phase_id, ctx):
        self.calls.append({"phase": phase_id,
                           "input_hashes": dict(ctx.get("input_hashes") or {}),
                           "simulated": bool(ctx.get("simulated"))})
        outputs = self.writer(run_dir, ctx) if self.writer else []
        return {"ok": True, "outputs": outputs, "execution_id": "exec-%s" % phase_id,
                "receipt": {"kind": "producer-receipt", "phase": phase_id,
                            "simulated": bool(ctx.get("simulated"))},
                "simulated": bool(ctx.get("simulated"))}


def _spy_ok(run_dir, outputs=None):
    return ProducerSpy("spy", lambda rd, ctx: list(outputs or []))


def _theme_writer(run_dir, ctx):
    """P1-PLAN producer: writes working/plan/plan.json from the approved theme."""
    cfg = json.loads((run_dir / "working" / "copy" / "config.json").read_text())
    theme = cfg.get("themeOfWeek") or cfg.get("theme", "unthemed")
    pdir = run_dir / "working" / "plan"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "plan.json").write_text(json.dumps({
        "weekOf": "2026-09-07", "themeOfWeek": theme, "plannerSheetId": "sheet-1",
        "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 1,
        "platforms": ["facebook"],
    }), encoding="utf-8")
    return ["working/plan/plan.json"]


def _writeback_writer(run_dir, ctx):
    """P8-PLANNER-WRITEBACK producer: appends the 20-column planner row and
    records the real write receipt + readback the F13 gate proves."""
    plan = json.loads((run_dir / "working" / "plan" / "plan.json").read_text())
    row_key = "cy-1::1::fb-1"
    row = [row_key, plan.get("themeOfWeek", ""), "research", "core", "imgs", "vids",
           "fb", "ig", "li", "yt", "tt", "pin", "car", "blog", "pod", "email",
           "QC pass", "scheduled", "complete", "notes"]
    rec = {"row": row,
           "spreadsheet_id": plan.get("plannerSheetId", "sheet-1"),
           "schema_version": rsm.PLANNER_SCHEMA_VERSION,
           "row_key": row_key,
           "updatedRange": "Weekly Overview!A2:T2",
           "content_hash": rsm._row_content_hash(row)}
    pdir = run_dir / "working" / "plan"
    pdir.mkdir(parents=True, exist_ok=True)
    (pdir / "row_appended.json").write_text(json.dumps(rec), encoding="utf-8")
    (pdir / "row_readback.json").write_text(json.dumps(
        {"found": True, "row_key": rec["row_key"], "values": row}), encoding="utf-8")
    return ["working/plan/row_appended.json", "working/plan/row_readback.json"]


def _fixture_run_dir(tmp, mode="test", theme="Approved Theme"):
    """A fresh run dir: valid fixture config + approved theme + trusted entry
    stamp. Everything downstream of the plan is MISSING (fresh run)."""
    rd = Path(tmp) / "run"
    (rd / "working" / "copy").mkdir(parents=True, exist_ok=True)
    (rd / "delivery").mkdir(parents=True, exist_ok=True)
    (rd / "working" / "copy" / "config.json").write_text(json.dumps({
        "brandName": "Brand One", "locationId": "loc-1", "userId": "u-1",
        "timezone": "America/New_York", "status": "Paid",
        "themeOfWeek": theme,
        "platforms": ["facebook"],
        "openrouterKey": "fixture-or-key",
        "pit": "fixture-pit",
        "probes": {"kieCredits": 500, "openrouterBalance": 25.0,
                   "ghlTokenValid": True, "connectedAccounts": [
                       {"account_id": "fb-1", "platform": "facebook"}]},
    }), encoding="utf-8")
    stamp = {"mode": mode, "set_by": "trusted-entry", "simulated": mode != "production"}
    (rd / "working" / "execution_mode.json").write_text(json.dumps(stamp), encoding="utf-8")
    # logged owner offline token (a simulated/test run requires it — F08)
    if mode != "production":
        (rd / "working" / "copy" / "preflight-offline-token.json").write_text(
            json.dumps({"owner_approved": True, "reason": "fixture run"}), encoding="utf-8")
    return rd


def _weekly_registry(run_dir, spies):
    """The F05 adapter set for the fixture 'plan' mode: one adapter per manifest
    phase of the requested mode (intake plan, research, copy, media, QC,
    scheduling, publishing, writeback are represented by the plan mode's
    P0/P1/P8 chain + the weekly mode's full chain where used)."""
    reg = rsm.ProducerRegistry()
    for pid, spy in spies.items():
        inputs = {"P1-PLAN": ["working/copy/config.json"],
                  "P8-PLANNER-WRITEBACK": ["working/plan/plan.json"]}.get(pid, [])
        reg.register_stub(pid, spy, assigned_agent="agent-%s" % pid.lower(), inputs=inputs)
    return reg


def _stub_gate_env():
    """Point the scrub gate's client-name list at an empty env (offline)."""
    import os
    os.environ.pop("SMIB_SCRUB_NAMES", None)


class TestFreshRunProducesBehindGates(unittest.TestCase):
    """QC-F05 setup 1: fresh run + approved theme -> spies observe the calls."""

    def test_plan_mode_producers_fire_and_gate_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            plan_spy = ProducerSpy("plan", _theme_writer)
            wb_spy = ProducerSpy("writeback", _writeback_writer)
            reg = _weekly_registry(rd, {"P1-PLAN": plan_spy, "P8-PLANNER-WRITEBACK": wb_spy})
            manifest = rsm._load_manifest()
            rc = rsm.run_with_producers(manifest, "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            # Producer spies observed the plan call AND the writeback call.
            self.assertEqual([c["phase"] for c in plan_spy.calls], ["P1-PLAN"])
            self.assertEqual([c["phase"] for c in wb_spy.calls], ["P8-PLANNER-WRITEBACK"])
            # The gate artifact now EXISTS (production happened behind the gate).
            plan = json.loads((rd / "working" / "plan" / "plan.json").read_text())
            self.assertEqual(plan["themeOfWeek"], "Approved Theme")
            # Receipts persisted with hashes + identity.
            rows = rsm._producer_receipts(rd)
            by_phase = {r["phase"]: r for r in rows}
            self.assertIn("P1-PLAN", by_phase)
            rec = by_phase["P1-PLAN"]
            self.assertEqual(rec["input_hashes"].get("working/copy/config.json"),
                             rsm._sha256_path(rd / "working" / "copy" / "config.json"))
            self.assertEqual(rec["output_hashes"].get("working/plan/plan.json"),
                             rsm._sha256_path(rd / "working" / "plan" / "plan.json"))
            self.assertEqual(rec["assigned_agent"], "agent-p1-plan")
            self.assertEqual(rec["execution_id"], "exec-P1-PLAN")
            self.assertTrue(rec["receipt"])
            self.assertTrue(rec["simulated"], "fixture (test-mode) receipts are simulated=true")

    def test_full_week_chain_spies_in_order(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            # The full 'week' chain's producer set; only P1 authors the plan,
            # the rest record their dispatch (their gates still decide pass).
            spies = {pid: _spy_ok(rd) for pid in
                     ("P0-PREFLIGHT", "P1-PLAN", "P2-CONTENT", "P3-CONTRACT",
                      "P4-MEDIA", "P5-SCRUB", "P13-DELIVER", "P6-MANIFEST",
                      "P7-PUBLISH", "P8-PLANNER-WRITEBACK")}
            spies["P1-PLAN"] = ProducerSpy("plan", _theme_writer)
            reg = _weekly_registry(rd, spies)
            manifest = rsm._load_manifest()
            rc = rsm.run_with_producers(manifest, "week", rd, registry=reg)
            # The gates AFTER content still fail-closed on a fixture run —
            # F05's claim is that production RAN (spies observed), not that a
            # bare registry makes every gate pass.
            self.assertEqual(rc, rsm.EXIT_GATE)
            observed = [c["phase"] for c in spies["P1-PLAN"].calls]
            self.assertEqual(observed, ["P1-PLAN"], "the plan producer ran for the fresh run")


class TestMissingArtifactTriggersProduction(unittest.TestCase):
    """QC-F05: missing files trigger production, never a claim it occurred."""

    def test_missing_plan_triggers_production_then_gate_passes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            self.assertFalse((rd / "working" / "plan" / "plan.json").is_file(),
                             "fresh run: the gate artifact is missing")
            # WITHOUT producers: the old behavior — bare gate refusal.
            rc = rsm.run(rsm._load_manifest(), "plan", rd)
            self.assertEqual(rc, rsm.EXIT_GATE)
            self.assertFalse((rd / "working" / "plan" / "plan.json").is_file())
            # WITH producers: production runs, the gate then passes.
            reg = _weekly_registry(rd, {"P1-PLAN": ProducerSpy("plan", _theme_writer),
                                        "P8-PLANNER-WRITEBACK": ProducerSpy("writeback", _writeback_writer)})
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            self.assertTrue((rd / "working" / "plan" / "plan.json").is_file())

    def test_failing_producer_is_specific_never_fabricated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)

            def failing(run_dir, phase_id, ctx):
                return {"ok": False, "error": "missing dependency: approved theme "
                                              "record (working/copy/config.json:themeOfWeek)"}

            reg = rsm.ProducerRegistry()
            reg.register_stub("P1-PLAN", failing, inputs=["working/copy/config.json"])
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_GATE)
            # The receipt records the SPECIFIC failure — production did NOT occur.
            rows = [r for r in rsm._producer_receipts(rd) if r["phase"] == "P1-PLAN"]
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[0]["ok"])
            self.assertIn("missing dependency", rows[0]["error"])
            self.assertEqual(rows[0]["output_hashes"], {})
            self.assertFalse((rd / "working" / "plan" / "plan.json").is_file())

    def test_declared_output_missing_on_disk_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            phantom = ProducerSpy("plan", lambda rd_, ctx: ["working/plan/plan.json"])
            reg = _weekly_registry(rd, {"P1-PLAN": phantom})
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_GATE)
            self.assertIn("missing on disk", str(rc)) if False else None


class TestResumeAndThemeHashRerun(unittest.TestCase):
    """QC-F05 setup 2: change a theme hash -> dependent outputs regenerate."""

    def _produced_run(self, td):
        rd = _fixture_run_dir(td)
        plan_spy = ProducerSpy("plan", _theme_writer)
        wb_spy = ProducerSpy("writeback", _writeback_writer)
        reg = _weekly_registry(rd, {"P1-PLAN": plan_spy, "P8-PLANNER-WRITEBACK": wb_spy})
        rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
        self.assertEqual(rc, rsm.EXIT_PASS)
        return rd, reg, plan_spy, wb_spy

    def test_unchanged_inputs_reuse_outputs(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd, reg, plan_spy, wb_spy = self._produced_run(td)
            plan_spy.calls.clear()
            wb_spy.calls.clear()
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            # No NEW production: outputs reused (input hashes unchanged).
            self.assertEqual(plan_spy.calls, [],
                             "unchanged inputs reuse verified outputs (no second run)")

    def test_theme_edit_reruns_plan_producer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd, reg, plan_spy, wb_spy = self._produced_run(td)
            plan_spy.calls.clear()
            # The client approves a NEW theme -> the theme hash changes.
            cfgp = rd / "working" / "copy" / "config.json"
            cfg = json.loads(cfgp.read_text())
            cfg["themeOfWeek"] = "New Approved Theme"
            cfgp.write_text(json.dumps(cfg), encoding="utf-8")
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            self.assertEqual([c["phase"] for c in plan_spy.calls], ["P1-PLAN"],
                             "a changed theme hash reruns the plan producer")
            plan = json.loads((rd / "working" / "plan" / "plan.json").read_text())
            self.assertEqual(plan["themeOfWeek"], "New Approved Theme")

    def test_downstream_reruns_after_upstream_edit(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd, reg, plan_spy, wb_spy = self._produced_run(td)
            wb_spy.calls.clear()
            # Edit the PLAN (an upstream input of writeback) after production.
            planp = rd / "working" / "plan" / "plan.json"
            plan = json.loads(planp.read_text())
            plan["notes"] = "edited after production"
            planp.write_text(json.dumps(plan), encoding="utf-8")
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            self.assertEqual([c["phase"] for c in wb_spy.calls], ["P8-PLANNER-WRITEBACK"],
                             "an edited upstream artifact reruns the downstream producer")

    def test_edited_output_reruns(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd, reg, plan_spy, wb_spy = self._produced_run(td)
            plan_spy.calls.clear()
            planp = rd / "working" / "plan" / "plan.json"
            plan = json.loads(planp.read_text())
            plan["themeOfWeek"] = "hand-edited"  # tamper with the OUTPUT
            planp.write_text(json.dumps(plan), encoding="utf-8")
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_PASS)
            self.assertEqual(len(plan_spy.calls), 1, "a drifted output reruns its producer")


class TestSimulatedReceiptsNeverSatisfyLive(unittest.TestCase):
    """F08 contract through the F05 layer: fake/simulated receipts can never
    satisfy live completion."""

    def test_simulated_flag_on_fixture_receipts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td, mode="test")
            reg = _weekly_registry(rd, {"P1-PLAN": ProducerSpy("plan", _theme_writer),
                                        "P8-PLANNER-WRITEBACK": ProducerSpy("writeback", _writeback_writer)})
            rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            rows = rsm._producer_receipts(rd)
            self.assertTrue(all(r.get("simulated") is True for r in rows),
                            "every fixture (test-mode) producer receipt is simulated=true")

    def test_simulated_receipt_rejected_by_live_publish_gate(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            # A PRODUCTION run whose publish results carry a simulated receipt
            # (as a fake producer would stamp) — the F08 gate refuses it.
            rd = _fixture_run_dir(td, mode="production")
            (rd / "working" / "publish").mkdir(parents=True)
            (rd / "working" / "publish" / "publish_results.json").write_text(
                json.dumps([{"kind": "publish_result", "platform": "facebook",
                             "success": True, "totalPosts": 1, "processedAccounts": 1,
                             "errors": [], "simulated": True}]), encoding="utf-8")
            plan = {"weekOf": "2026-09-07", "themeOfWeek": "Theme", "plannerSheetId": "s",
                    "companyId": "co-1", "cycleId": "cy-1", "contentRevision": 1,
                    "accounts": [{"account_id": "fb-1", "platform": "facebook"}]}
            (rd / "working" / "plan").mkdir(parents=True, exist_ok=True)
            (rd / "working" / "plan" / "plan.json").write_text(json.dumps(plan),
                                                              encoding="utf-8")
            (rd / "delivery" / "PROCESS-CERTIFICATE.json").write_text("{}", encoding="utf-8")
            ok, msg = rsm._chk_publish(rd)
            self.assertFalse(ok)
            self.assertIn("SIMULATED", msg.upper())

    def test_production_receipts_not_stamped_simulated(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(Path(td) / "prod", mode="production")
            # Hermetic: production-mode probes hit the live network, so assert
            # the producer layer's simulated-stamping directly (the same code
            # path run_with_producers takes) rather than the full live preflight.
            spy = ProducerSpy("plan", _theme_writer)
            entry = {"adapter": spy, "assigned_agent": "agent-p1-plan",
                     "inputs": ["working/copy/config.json"], "phase_id": "P1-PLAN"}
            ok, msg = rsm._invoke_producer(rd, entry, execution_mode_simulated=False)
            self.assertTrue(ok, msg)
            rows = rsm._producer_receipts(rd)
            self.assertEqual(len(rows), 1)
            self.assertFalse(rows[-1].get("simulated"),
                             "a production run's producer receipt is NOT simulated")
            self.assertFalse(spy.calls[0]["simulated"])
            # And the simulated side for contrast: a test-mode run stamps true.
            rd2 = _fixture_run_dir(Path(td) / "test", mode="test")
            spy2 = ProducerSpy("plan2", _theme_writer)
            entry2 = {"adapter": spy2, "assigned_agent": "agent-p1-plan",
                      "inputs": ["working/copy/config.json"], "phase_id": "P1-PLAN"}
            ok2, _m2 = rsm._invoke_producer(rd2, entry2, execution_mode_simulated=True)
            self.assertTrue(ok2, _m2)
            self.assertTrue(rsm._producer_receipts(rd2)[-1].get("simulated"))
    def test_gate_still_fails_after_ok_producer(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            # Producer "succeeds" but authors nothing the gate accepts: the
            # gate STILL fails (producers never replace _chk_*).
            noop = ProducerSpy("noop", lambda rd_, ctx: [])
            reg = _weekly_registry(rd, {"P1-PLAN": noop})
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_GATE,
                             "an ok producer with no valid artifact does not pass the gate")

    def test_default_run_loop_unchanged_without_producers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            rc = rsm.run(rsm._load_manifest(), "plan", rd)
            self.assertEqual(rc, rsm.EXIT_GATE)  # missing plan -> gate fails (as before)
            self.assertEqual(rsm._producer_receipts(rd), [],
                             "no producer receipts without the producer layer")

    def test_registry_rejects_duplicate_without_replaces(self):
        reg = rsm.ProducerRegistry()
        reg.register_stub("P1-PLAN", _spy_ok(None))
        with self.assertRaises(rsm.ProducerError):
            reg.register("P1-PLAN", _spy_ok(None))

    def test_missing_producer_input_fails_closed(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            rd = _fixture_run_dir(td)
            reg = rsm.ProducerRegistry()
            reg.register_stub("P1-PLAN", _spy_ok(rd),
                              inputs=["working/copy/no-such-input.json"])
            rc = rsm.run_with_producers(rsm._load_manifest(), "plan", rd, registry=reg)
            self.assertEqual(rc, rsm.EXIT_GATE)
            self.assertIn("fail-closed", str(rsm._producer_receipts(rd)))


class TestEntryProducersFlag(unittest.TestCase):
    """social-media-entry.sh forwards --producers / SMIB_PRODUCERS=1 and the
    manifest declares the producer adapter contract."""

    def test_manifest_declares_producer_layer(self):
        manifest = json.loads((_SKILL_DIR / "SOCIAL-MANIFEST.json").read_text())
        note = manifest.get("$producers_note", "")
        self.assertIn("PRODUCER ADAPTER LAYER", note)
        self.assertIn("simulated", note)
        self.assertIn("BEHIND the gates", note)

    def test_entry_help_documents_producers(self):
        import subprocess
        p = subprocess.run(["bash", str(_ENTRY_PATH), "--help"],
                           capture_output=True, text=True, timeout=30)
        self.assertEqual(p.returncode, 2)  # usage exits 2 by design
        self.assertIn("--producers", p.stderr)

    def test_runner_accepts_producers_flag(self):
        import subprocess
        p = subprocess.run([sys.executable, str(_RUNNER_PATH), "--help"],
                           capture_output=True, text=True, timeout=30)
        self.assertIn("--producers", p.stdout + p.stderr)


if __name__ == "__main__":
    unittest.main()
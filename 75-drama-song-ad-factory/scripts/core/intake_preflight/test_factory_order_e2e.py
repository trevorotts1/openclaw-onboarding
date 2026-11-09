"""C01 end-to-end order prover: the published `factory.py next` path must hand
out the twelve canonical stages in order, one at a time, and a planted skip
must be refused by name. Offline: synthetic local fixtures, no provider call.
"""
from contextlib import redirect_stdout, redirect_stderr
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

CORE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(CORE))
from intake_preflight import factory
import production_process
import state_store
from batch_mode import batch as batch_mod
import final_recap
import spend_ledger
from test_production_process import confirmed_run, approve_script, approve_storyboard


def cli(*argv):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        code = factory.main(list(argv))
    return code, json.loads(out.getvalue())


def complete(run, stage, registry):
    for rel in registry[stage].get("required_artifacts", []):
        p = run / rel
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({"fixture": stage}), encoding="utf-8")
    with state_store.Store(run / "control" / "state.sqlite3") as s:
        if s.get(run.name, stage)["state"] != "READY":
            s.transition(run.name, stage, "READY", "fixture-worker")
        s.claim(run.name, stage, "fixture-worker")
        s.transition(run.name, stage, "COMPLETE", "fixture-worker")


def elect_song(run):
    song = run / "music" / "picked-song.mp3"
    song.parent.mkdir(parents=True, exist_ok=True)
    song.write_bytes(b"synthetic local picked song")
    pick = run / "song-choices" / "pick.json"
    pick.parent.mkdir(parents=True, exist_ok=True)
    pick.write_text(json.dumps({"pick": 1, "label": "fixture",
                                "sha256": hashlib.sha256(song.read_bytes()).hexdigest()}),
                    encoding="utf-8")


def recap_and_go(run, rid, work):
    ledger = run / "spend.sqlite3"
    if not ledger.exists():
        spend_ledger.init_run(str(ledger), rid, ceiling=50000, currency="USD")
    _, env = cli("final-recap", "--run-dir", str(run))
    go = work / "go.json"
    go.write_text(json.dumps({"schema": final_recap.GO_SCHEMA, "decision": "GO",
                              "operator": "offline-owner-fixture",
                              "at_utc": "2026-11-01T00:00:00Z",
                              "recap_digest": env["data"]["recap"]["recap_digest"]}),
                  encoding="utf-8")
    cli("production-go", "--run-dir", str(run), "--go", str(go))


class OrderEndToEnd(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="factory-order-e2e-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.graph, self.registry = production_process._graph()

    def test_three_order_sources_agree(self):
        canonical = list(factory.CANONICAL_STAGES)
        self.assertEqual(canonical, list(self.graph))
        self.assertEqual(canonical, [sid for sid, _ in batch_mod.STAGES])

    def test_next_walks_all_twelve_stages_in_order(self):
        run = self.work / "run"
        rid = confirmed_run(run)
        seen = []
        for stage in factory.CANONICAL_STAGES:
            if stage == "music":
                approve_script(run)
            if stage == "video-generation":
                approve_storyboard(run)
                recap_and_go(run, rid, self.work)
            _, env = cli("next", "--run-dir", str(run))
            data = env["data"]
            self.assertEqual(data.get("stage"), stage, "after %s" % seen)
            self.assertTrue(data.get("production_admitted"), stage)
            seen.append(data["stage"])
            complete(run, stage, self.registry)
            if stage == "music":
                elect_song(run)
        self.assertEqual(seen, list(factory.CANONICAL_STAGES))
        self.assertEqual(len(seen), len(set(seen)))

    def test_planted_skip_refused_by_name(self):
        run = self.work / "planted"
        confirmed_run(run)
        complete(run, "research", self.registry)
        code, env = cli("preflight", "--run-dir", str(run),
                        "--stage", "music", "--mode", "production")
        self.assertEqual(code, 2)
        self.assertEqual(env.get("reason_code"), "PRODUCTION_PREDECESSOR_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()

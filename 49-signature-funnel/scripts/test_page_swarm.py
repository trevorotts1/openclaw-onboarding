#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_page_swarm.py - pages built side by side (the landing lane too), limiter and spend
cap respected, one failure never stops the rest. Fake pages and a fake limiter only: no provider,
no paid call, no network. Run: python3 test_page_swarm.py (from scripts/).
"""
import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import dispatch_launch as dl  # noqa: E402
import page_set as ps  # noqa: E402
import page_swarm as sw  # noqa: E402
from test_page_set import approved_launch, route_launch, EXTRAS  # noqa: E402

CLIENT, WORKER = "client-1", "worker-9"
STUB_INPUTS = {"design_style": "B", "brand_file": "/x/brand.json", "brand_owner": "Acme", "image_cap": 10 ** 6,
               "image_provider": "stub", "allow_paid": False}


def paid_inputs(cap):
    return dict(STUB_INPUTS, image_provider="kie", image_cap=cap, test_only=True)


class CountingLimiter:
    """Stands in for Skill 71's TokenBucket: counts the starts it is asked to pace."""

    def __init__(self):
        self.tokens = 0
        self.lock = threading.Lock()

    def consume(self):
        with self.lock:
            self.tokens += 1


def fake_executor(log=None, sleep=0.0, fail=(), transient_once=(), seen=None):
    """A consumer that answers every request with a valid L0 result, optionally slowly or badly."""
    simulated = dl._simulated_executor("test")
    tried = set()

    def run(req, lane=None):
        key = lane or req["page_role"]
        if log is not None:
            log.append(("start", key, time.monotonic()))
        if seen is not None:
            seen.append(key)
        time.sleep(sleep(key) if callable(sleep) else sleep)
        if key in fail:
            raise dl.DispatchError(f"{key}: the consumer said no")
        if key in transient_once and key not in tried:
            tried.add(key)
            raise sw.LaneTransient("timed out")
        out = simulated(req, lane)
        if log is not None:
            log.append(("end", key, time.monotonic()))
        return out
    return run


def go(mode="multiple_options", executor=None, parallel=1, inputs=None, limiter=None, extras=(),
       landing_pages=("landing", "sales"), out=None):
    launch, approval = approved_launch(mode)
    return dl.dispatch(launch, approval, client_identity_ref=CLIENT, worker_identity_ref=WORKER,
                       out_dir=out, executor=executor, parallel=parallel, image_inputs=inputs,
                       landing_pages=list(landing_pages), extra_pages=tuple(extras), limiter=limiter)


class WhatAFullFunnelDispatches(unittest.TestCase):
    def test_the_multiple_options_full_funnel_page_list_and_lane_plan(self):
        m = go()
        pages = [p["page_key"] for p in m["page_set"]["pages"]]
        self.assertEqual(pages, ["landing", "sales", "product_selection", "checkout", "upsell_1", "upsell_2",
                                 "downsell_1", "thank_you"])
        plan = m["page_set"]["lane_plan"]
        self.assertEqual(len(plan["parallel"]), 7, "landing and the six other lanes")
        self.assertEqual(len(m["requests"]), 7, "the route graph still has 7 nodes: no node was added")

    def test_folded_levels_dispatches_every_page_but_the_selection_page(self):
        m = go("folded_levels")
        pages = [p["page_key"] for p in m["page_set"]["pages"]]
        self.assertNotIn("product_selection", pages)
        self.assertEqual(pages, ["landing", "sales", "checkout", "upsell_1", "upsell_2", "downsell_1", "thank_you"])
        self.assertEqual(len(m["requests"]), 6)

    def test_what_the_client_did_not_choose_is_listed_as_to_confirm(self):
        launch, approval = approved_launch()
        m = dl.dispatch(launch, approval, client_identity_ref=CLIENT, worker_identity_ref=WORKER)
        self.assertEqual(m["page_set"]["to_confirm"], ["landing_pages"])
        self.assertEqual(go()["page_set"]["to_confirm"], [])


class ParallelLanes(unittest.TestCase):
    def test_pages_run_side_by_side_so_wall_time_beats_the_sum(self):
        started = time.monotonic()
        m = go(executor=fake_executor(sleep=0.25), parallel=6)
        wall = time.monotonic() - started
        self.assertEqual(len(m["results"]), 7)
        # all seven lanes at once (0.25), far below the 7 x 0.25 sequential sum, with no landing-first wait
        self.assertLess(wall, 0.9, wall)

    def test_results_come_back_in_page_order_whatever_order_they_finish(self):
        # later pages finish first
        delay = {"landing": 0.05, "product_selection": 0.30, "checkout": 0.25, "upsell_1": 0.2,
                 "downsell_1": 0.1, "upsell_2": 0.05, "thank_you": 0.0}
        m = go(executor=fake_executor(sleep=lambda k: delay[k]), parallel=6)
        order = [r["page_id"].rsplit("-", 1)[1].lower() for r in m["results"]]
        self.assertEqual(order, ["landing", "product_selection", "checkout", "upsell_1", "downsell_1",
                                 "upsell_2", "thank_you"])
        self.assertEqual(m["swarm"]["lanes"], ["landing", "product_selection", "checkout", "upsell_1",
                                               "downsell_1", "upsell_2", "thank_you"])

    def test_parallel_one_is_the_sequential_fallback_with_identical_results(self):
        a = go(executor=fake_executor(), parallel=1)
        b = go(executor=fake_executor(), parallel=6)
        self.assertEqual(a["results"], b["results"])
        self.assertEqual(a["swarm"]["statuses"], b["swarm"]["statuses"])
        self.assertEqual(a["swarm"]["workers"], 1)

    def test_the_worker_count_defaults_to_the_runner_profile(self):
        for profile, workers in (("fleet-mac", 6), ("fleet-hostinger", 8), ("fleet-contabo", 4)):
            self.assertEqual(sw.default_workers(profile_name=profile), workers, profile)

    def test_no_lane_runs_twice_and_every_lane_runs_once(self):
        seen = []
        go(executor=fake_executor(seen=seen), parallel=6, extras=("downsell_2",))
        self.assertEqual(sorted(seen), sorted(set(seen)))
        self.assertEqual(len(seen), 8)


class OneFailureNeverStopsTheRest(unittest.TestCase):
    def test_a_failed_page_is_named_and_every_other_page_is_still_built(self):
        out = Path(tempfile.mkdtemp())
        seen = []
        with self.assertRaises(dl.DispatchError) as cm:
            go(executor=fake_executor(fail=("upsell_1",), seen=seen), parallel=6, out=out)
        self.assertIn("upsell_1 failed", str(cm.exception))
        self.assertEqual(len(seen), 7, "all seven pages were attempted")
        written = sorted(p.name for p in out.glob("result-*.json"))
        self.assertEqual(written, sorted(f"result-{r}.json" for r in (
            "landing", "product_selection", "checkout", "downsell_1", "upsell_2", "thank_you")))
        manifest = json.loads((out / "dispatch-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["swarm"]["statuses"]["upsell_1"], "failed")

    def test_a_transient_failure_is_retried_once_and_a_second_failure_is_final(self):
        m = go(executor=fake_executor(transient_once=("checkout",)), parallel=6)
        self.assertEqual(m["swarm"]["attempts"]["checkout"], 2)
        self.assertEqual(m["swarm"]["attempts"]["thank_you"], 1)

        def always(req, lane=None):
            raise sw.LaneTransient("down")
        out = sw.run_swarm([{"lane": "a", "image_estimate": 1}], lambda lane: always(None), workers=1)
        self.assertEqual((out[0]["status"], out[0]["attempts"]), ("failed", 2))


class LimiterAndSpendCap(unittest.TestCase):
    def test_the_free_stub_takes_no_tokens_and_has_no_cap(self):
        limiter = CountingLimiter()
        m = go(executor=fake_executor(), parallel=6, inputs=dict(STUB_INPUTS, image_cap=0), limiter=limiter)
        self.assertEqual(limiter.tokens, 0)
        self.assertEqual(set(m["swarm"]["statuses"].values()), {"ok"})
        self.assertFalse(m["swarm"]["spend"]["enforced"])

    def test_every_paid_image_start_takes_a_token_and_a_retry_takes_them_again(self):
        limiter = CountingLimiter()
        m = go(executor=fake_executor(transient_once=("checkout",)), parallel=6, inputs=paid_inputs(10 ** 6),
               limiter=limiter)
        plan = m["page_set"]["lane_plan"]
        estimate = {l["lane"]: l["image_estimate"] for l in plan["parallel"]}
        self.assertEqual(limiter.tokens, sum(estimate.values()) + estimate["checkout"])

    def test_no_new_paid_image_work_starts_past_the_cap(self):
        limiter, seen = CountingLimiter(), []
        # landing = 108 images (15-section landing + 12-section sales), then pages in order:
        # product_selection 20, checkout 20 fit under 150; upsell_1 (32) would pass it and is skipped
        out = Path(tempfile.mkdtemp())
        with self.assertRaises(dl.DispatchError):  # skipped pages fail the dispatch by name (next test)
            go(executor=fake_executor(seen=seen), parallel=6, inputs=paid_inputs(150), limiter=limiter, out=out)
        m = json.loads((out / "dispatch-manifest.json").read_text(encoding="utf-8"))
        statuses = m["swarm"]["statuses"]
        self.assertEqual([k for k, v in statuses.items() if v == "ok"], ["landing", "product_selection", "checkout"])
        self.assertEqual(statuses["upsell_1"], "skipped_cap")
        self.assertEqual(sorted(seen), ["checkout", "landing", "product_selection"], "skipped pages never started")
        self.assertEqual(limiter.tokens, 108 + 20 + 20)
        self.assertLessEqual(m["swarm"]["spend"]["reserved_images"], 150)

    def test_a_page_skipped_for_the_cap_fails_the_dispatch_by_name_not_silently(self):
        with self.assertRaises(dl.DispatchError) as cm:
            go(executor=fake_executor(), inputs=paid_inputs(150), limiter=CountingLimiter())
        self.assertIn("upsell_1 skipped_cap", str(cm.exception))
        self.assertIn("image cap 150", str(cm.exception))

    def test_the_ledger_is_written_to_disk(self):
        out = Path(tempfile.mkdtemp())
        go(executor=fake_executor(), inputs=paid_inputs(10 ** 6), limiter=CountingLimiter(), out=out)
        ledger = json.loads((out / sw.LEDGER_NAME).read_text(encoding="utf-8"))
        self.assertEqual(ledger["provider"], "kie")
        self.assertEqual(len(ledger["entries"]), 7)

    def test_the_real_kie_limiter_paces_twenty_starts_per_ten_seconds(self):
        sys.path.insert(0, str(sw.SKILL71_ROOT / "scripts"))
        import swarm_runner
        clock = swarm_runner.FakeClock()
        bucket = sw.kie_limiter(path=Path(tempfile.mkdtemp()) / "kie.json", clock=clock)
        start = clock.now()
        for _ in range(20):
            bucket.consume()
        self.assertEqual(clock.now(), start, "the first twenty starts are immediate")
        bucket.consume()
        self.assertGreaterEqual(clock.now() - start, 10.0, "the twenty-first waits for the window")


class VisualBibleAndExtraPages(unittest.TestCase):
    def test_the_landing_lane_runs_beside_the_other_pages_not_before_them(self):
        meet = threading.Barrier(2, timeout=20)  # landing and checkout must be running at the same time

        def run(req, lane=None):
            if (lane or req["page_role"]) in ("landing", "checkout"):
                meet.wait()
            return dl._simulated_executor("t")(req, lane)
        m = go(executor=run, parallel=4, inputs=STUB_INPUTS)
        self.assertEqual(set(m["swarm"]["statuses"].values()), {"ok"})

    def test_the_visual_bible_is_the_record_of_the_landing_run_written_when_the_swarm_ends(self):
        out = Path(tempfile.mkdtemp())
        go(executor=fake_executor(), parallel=4, inputs=STUB_INPUTS, out=out)
        bible = json.loads((out / sw.BIBLE_NAME).read_text(encoding="utf-8"))
        self.assertEqual((bible["design_style"], bible["landing_status"]), ("B", "ok"))
        inputs = json.loads((out / sw.INPUTS_NAME).read_text(encoding="utf-8"))
        self.assertNotIn("visual_bible_ref", inputs, "no lane's input depends on the bible")

    def test_the_second_downsell_rides_on_the_downsell_request_with_its_own_files(self):
        out = Path(tempfile.mkdtemp())
        m = go(executor=fake_executor(), parallel=4, extras=("downsell_2",), out=out)
        self.assertEqual(len(m["results"]), 7, "the route's results are unchanged")
        d2 = m["page_results"]["downsell_2"]
        d1 = next(r for r in m["results"] if r["page_id"].endswith("DOWNSELL_1"))
        self.assertEqual(d2["request_id"], d1["request_id"])
        self.assertTrue((out / "page-result-downsell_2.json").is_file())
        self.assertFalse((out / "result-downsell_2.json").exists(), "never collected as a route result")


class CommandLine(unittest.TestCase):
    """The real command line, with fake consumer programs standing in for the owning skills."""

    def run_cli(self, *extra, sleep=0.0, mode="folded_levels", extra_adapters=()):
        td = Path(tempfile.mkdtemp())
        launch, approval = approved_launch(mode)
        (td / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
        (td / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
        consumer = td / "consumer.py"
        consumer.write_text(
            "import json,sys,time\n"
            f"time.sleep({sleep})\n"
            "req=json.load(open(sys.argv[1]))\n"
            "res={'schema_version':'1.0','tenant_id':req['tenant_id'],'location_id':req['location_id'],"
            "'launch_id':req['launch_id'],'revision':req['revision'],'request_id':req['request_id'],"
            "'input_hash':req['input_hash'],'page_id':req['page_id'],'status':'authored','artifacts':[],"
            "'author_session':'cli-test','reviewer_session':None,'independent_review':False,"
            "'proof_class':'L0','blockers':[],'native_bindings_ref':None,'test_only':req['test_only']}\n"
            "json.dump(res,open(sys.argv[2],'w'))\n", encoding="utf-8")
        cfg = {"adapters": {r: {"command": [sys.executable, str(consumer), "{request}", "{result}"]}
                            for r in (*dl.PAGE_ROLES, *extra_adapters)}}
        (td / "adapters.json").write_text(json.dumps(cfg), encoding="utf-8")
        inputs = td / "image_inputs.json"
        inputs.write_text(json.dumps({"design_style": "A", "brand_file": "/x/b.json", "brand_owner": "Acme",
                                      "image_cap": 100, "image_provider": "stub"}), encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(HERE / "dispatch_launch.py"), "--launch", str(td / "launch.json"),
             "--approval", str(td / "approval.json"), "--client", CLIENT, "--worker", WORKER,
             "--out", str(td / "out"), "--adapters", str(td / "adapters.json"),
             "--image-inputs", str(inputs), "--landing-pages", "landing,sales", *extra],
            capture_output=True, text=True)
        return proc, td / "out"

    def test_parallel_cli_runs_every_page_and_reports_the_plan(self):
        started = time.monotonic()
        proc, out = self.run_cli("--parallel", "6", sleep=0.4)
        wall = time.monotonic() - started
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["results"], 6)
        self.assertEqual(summary["pages"], ["landing", "sales", "checkout", "upsell_1", "upsell_2", "downsell_1",
                                            "thank_you"])
        self.assertLess(wall, 6 * 0.4, "six consumers ran side by side")
        manifest = json.loads((out / "dispatch-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["swarm"]["workers"], 6)
        self.assertTrue((out / sw.BIBLE_NAME).is_file())

    def test_parallel_one_gives_the_same_results(self):
        _, out6 = self.run_cli("--parallel", "6")
        _, out1 = self.run_cli("--parallel", "1")
        m6 = json.loads((out6 / "dispatch-manifest.json").read_text(encoding="utf-8"))
        m1 = json.loads((out1 / "dispatch-manifest.json").read_text(encoding="utf-8"))
        self.assertEqual([r["page_id"] for r in m6["results"]], [r["page_id"] for r in m1["results"]])

    def test_the_second_downsell_runs_as_its_own_lane_and_never_collides_with_downsell_1(self):
        proc, out = self.run_cli("--parallel", "4", "--extra-page", "downsell_2", mode="multiple_options",
                                 extra_adapters=("downsell_2",))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["pages"][-2:], ["downsell_2", "thank_you"])
        self.assertTrue((out / "page-result-downsell_2.json").is_file())
        self.assertTrue((out / "page-request-downsell_2.json").is_file())
        self.assertEqual(len(list(out.glob("result-*.json"))), 7, "the route's results are untouched")

    def test_an_adapter_key_that_is_no_page_is_still_refused(self):
        with self.assertRaises(dl.DispatchError):
            dl.executor_from_config({"adapters": {"downsell_3": {"command": ["true"]}}}, Path("."))
        dl.executor_from_config({"adapters": {"downsell_2": {"command": ["true"]}}}, Path("."))

    def test_a_bad_image_inputs_file_is_refused_before_anything_runs(self):
        proc, out = self.run_cli("--parallel", "2", "--image-inputs", "/nonexistent/image_inputs.json")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("image inputs", proc.stdout)


if __name__ == "__main__":
    unittest.main()

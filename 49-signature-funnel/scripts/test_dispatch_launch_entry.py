#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_dispatch_launch_entry.py - the canonical entry must EXECUTE when the
approved adapter configuration rides in launch-request.json (finding 9), and a
lone-directory install must still EMIT without Skill 71 (finding 12).

Real subprocesses, temp dirs, stub/fake consumers only: no network, no paid
provider, no Skill 71 execution. Run from scripts/: python3 test_dispatch_launch_entry.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

# Launch events spool to the home directory when no Command Center is configured;
# a test run must never write there.
_SPOOL = tempfile.mkdtemp(prefix="launch-events-spool-")
os.environ["LAUNCH_EVENTS_SPOOL"] = _SPOOL
os.environ.pop("LAUNCH_EVENTS_URL", None)

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
CLIENT, WORKER = "client-1", "worker-9"
sys.path.insert(0, str(HERE))
import compile_launch_route as clr  # noqa: E402
import front_door as fd  # noqa: E402
import dispatch_launch as dl  # noqa: E402
import page_set as pset  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402
from test_page_set import LAUNCH_EXAMPLE, approved_launch  # noqa: E402

# A stand-in consumer that echoes the request exactly (valid L0 page-result).
CONSUMER = """\
import json, sys
req = json.load(open(sys.argv[1]))
res = {'schema_version': '1.0', 'tenant_id': req['tenant_id'],
       'location_id': req['location_id'], 'launch_id': req['launch_id'],
       'revision': req['revision'], 'request_id': req['request_id'],
       'input_hash': req['input_hash'], 'page_id': req['page_id'],
       'status': 'authored', 'artifacts': [], 'author_session': 'entry-test',
       'reviewer_session': None, 'independent_review': False,
       'proof_class': 'L0', 'blockers': [], 'native_bindings_ref': None,
       'test_only': req['test_only']}
json.dump(res, open(sys.argv[2], 'w'))
"""


def make_run_dir(td: Path, *, adapters: bool, parallel="auto") -> Path:
    """A launch run dir exactly as the documented launch mode expects it."""
    launch, approval = approved_launch()
    rd = td / "run"
    rd.mkdir()
    (rd / "launch.json").write_text(json.dumps(launch), encoding="utf-8")
    (rd / "approval.json").write_text(json.dumps(approval), encoding="utf-8")
    consumer = td / "consumer.py"
    consumer.write_text(CONSUMER, encoding="utf-8")
    request = {"mode": "signature_launch", "client_identity_ref": CLIENT,
               "worker_identity_ref": WORKER, "parallel": parallel}
    if adapters:
        request["adapters"] = {
            role: {"command": [sys.executable, str(consumer),
                               "{request}", "{result}"]}
            for role in dl.PAGE_ROLES}
    (rd / "launch-request.json").write_text(json.dumps(request), encoding="utf-8")
    return rd


def lone_install(td: Path) -> Path:
    """Skill 49 copied alone into a skills root with the shared approval verifier: no
    71-blackceo-signature-page sibling."""
    dst = td / "skills" / "49-signature-funnel"
    dst.mkdir(parents=True)
    for name in ("signature-funnel-entry.sh", "SKILL.md", "skill-version.txt"):
        shutil.copy2(SKILL / name, dst / name)
    shutil.copytree(SKILL / "structure", dst / "structure")
    shutil.copytree(
        SKILL / "scripts", dst / "scripts",
        ignore=shutil.ignore_patterns("__pycache__", "fixtures", "vendor",
                                      "working", "test_*.py"))
    su = td / "skills" / "shared-utils" / "signature_launch_contract"
    su.mkdir(parents=True)
    shutil.copy2(SKILL.parent / "shared-utils" / "signature_launch_contract" / "approval_record.py",
                 su / "approval_record.py")
    return dst


def run(cmd) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def pinned_copy(td: Path) -> Path:
    """The whole skill copied beside Skill 71 with its own freshly minted pin.

    These tests are about what the entry DOES with an approved adapter table, not
    about the enforcement-core pin (CI re-mints SF-PROVER-PIN.sha256
    after any pinned file changes; the pin itself is proven in test_front_door). A copy
    with its own pin keeps them true on every branch."""
    root = td / "skills"
    dst = root / "49-signature-funnel"
    shutil.copytree(SKILL, dst, ignore=shutil.ignore_patterns("__pycache__", "working"))
    (root / "71-blackceo-signature-page").symlink_to(
        SKILL.parent / "71-blackceo-signature-page", target_is_directory=True)
    # the pin set also covers the Skill 83 launcher tree and the shared launch packages beside Skill 49
    # the front door also needs the department map (Skill 49's own routing row) beside the skill
    for sibling in ("83-black-friday-launcher", "shared-utils", "23-ai-workforce-blueprint"):
        (root / sibling).symlink_to(SKILL.parent / sibling, target_is_directory=True)
    # the fixture's own mint, through the only legal path (CI); the repository pin is untouched
    fd.mint_pin_ci(dst, env={"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
                             "GITHUB_REPOSITORY": "local/test", "GITHUB_RUN_ID": "0"})
    return dst


class TheEntryExecutesApprovedAdapters(unittest.TestCase):
    def test_entry_launch_mode_executes_instead_of_only_emitting(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            rd = make_run_dir(tdp, adapters=True)
            p = run(["bash", str(pinned_copy(tdp) / "signature-funnel-entry.sh"),
                     "--mode", "signature_launch", "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertEqual(p.returncode, 0, out)
            manifest = json.loads(
                (rd / "dispatch" / "dispatch-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"], "executed", out)
            self.assertEqual(len(manifest["results"]), len(dl.PAGE_ROLES), out)
            # every result came from the consumer that ran, never a fabrication
            self.assertTrue(
                all(r["author_session"] == "entry-test" for r in manifest["results"]), out)


class TheEntryRefusesFabricatedResults(unittest.TestCase):
    def test_simulate_executor_is_never_forwardable(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            rd = make_run_dir(tdp, adapters=True)
            p = run(["bash", str(SKILL / "signature-funnel-entry.sh"),
                     "--mode", "signature_launch", "--run-dir", str(rd),
                     "--simulate-executor"])
            out = p.stdout + p.stderr
            self.assertNotEqual(p.returncode, 0, out)
            self.assertIn("unknown arg", out)


class BadAdapterConfigFailsClosed(unittest.TestCase):
    """A malformed adapters table is a named violation, never a traceback."""
    def _run_with(self, mutate):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            rd = make_run_dir(tdp, adapters=True)
            req = json.loads((rd / "launch-request.json").read_text(encoding="utf-8"))
            mutate(req)
            (rd / "launch-request.json").write_text(json.dumps(req), encoding="utf-8")
            p = run(["bash", str(pinned_copy(tdp) / "signature-funnel-entry.sh"),
                     "--mode", "signature_launch", "--run-dir", str(rd)])
            return p.stdout + p.stderr, p.returncode

    def test_an_adapter_entry_that_is_not_an_object_fails_closed(self):
        out, rc = self._run_with(lambda req: req["adapters"].update(landing="consumer.py"))
        self.assertEqual(rc, dl.EXIT_VIOLATION, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("adapter landing", out)

    def test_adapters_that_are_not_an_object_at_all_fail_closed(self):
        out, rc = self._run_with(lambda req: req.update(adapters="not-an-object"))
        self.assertEqual(rc, dl.EXIT_VIOLATION, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("adapters", out)

    def test_a_command_that_is_not_a_list_of_strings_fails_closed(self):
        out, rc = self._run_with(
            lambda req: req["adapters"]["landing"].update(command="consumer.py {request}"))
        self.assertEqual(rc, dl.EXIT_VIOLATION, out)
        self.assertNotIn("Traceback", out)
        self.assertIn("adapter landing command", out)


def _adapters(td: Path, *roles, author="entry-test"):
    consumer = td / f"consumer-{author}.py"
    consumer.write_text(CONSUMER.replace("entry-test", author), encoding="utf-8")
    return {r: {"command": [sys.executable, str(consumer), "{request}", "{result}"]}
            for r in roles}


def _dispatch(td: Path, adapters, pair=None, **kw):
    launch, approval = pair or approved_launch()
    out = td / "dispatch"
    return dl.dispatch(launch, approval, client_identity_ref=CLIENT,
                       worker_identity_ref=WORKER, out_dir=out,
                       executor=dl.executor_from_config({"adapters": adapters}, out),
                       **kw), out


class AnExtraLaneNeverBorrowsItsParentsAdapter(unittest.TestCase):
    """DTY-12: downsell_2 rides on downsell_1's request; with no entry of its own it
    used to run the downsell_1 command and rebuild D1 under the Downsell 2 name."""
    def test_downsell_2_without_its_own_entry_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(dl.DispatchError) as ctx:
                _dispatch(Path(td), _adapters(Path(td), *dl.PAGE_ROLES),
                          extra_pages=("downsell_2",))
            self.assertIn("downsell_2", str(ctx.exception))
            self.assertIn("no consumer adapter", str(ctx.exception))

    def test_downsell_2_with_its_own_entry_runs_it_and_leaves_d1_alone(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            adapters = _adapters(tdp, *dl.PAGE_ROLES)
            adapters.update(_adapters(tdp, "downsell_2", author="d2-only"))
            manifest, out = _dispatch(tdp, adapters, extra_pages=("downsell_2",))
            self.assertEqual(manifest["page_results"]["downsell_2"]["author_session"], "d2-only")
            d1 = json.loads((out / "result-downsell_1.json").read_text(encoding="utf-8"))
            self.assertEqual(d1["author_session"], "entry-test")
            self.assertTrue((out / "page-result-downsell_2.json").is_file())


class ASimulatedRunIsLabelledAndTestOnly(unittest.TestCase):
    """ENF-26: --simulate-executor fabricates results, so the manifest says so."""
    def test_cli_manifest_says_simulated(self):
        with tempfile.TemporaryDirectory() as td:
            rd = make_run_dir(Path(td), adapters=False, parallel=1)
            p = run([sys.executable, str(HERE / "dispatch_launch.py"),
                     "--run-dir", str(rd), "--simulate-executor"])
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            manifest = json.loads(
                (rd / "dispatch" / "dispatch-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"], "simulated")

    def test_refused_when_the_launch_is_not_test_only(self):
        launch, approval = approved_launch()
        launch["test_only"] = False
        with self.assertRaises(dl.DispatchError) as ctx:
            dl.dispatch(launch, approval, client_identity_ref=CLIENT,
                        worker_identity_ref=WORKER,
                        executor=dl._simulated_executor("x"))
        self.assertIn("simulate-executor", str(ctx.exception))


class ARefusalPrintedToStdoutStillShowsItsCause(unittest.TestCase):
    """DTY-28: a lane that exits non-zero with empty stderr used to read 'exited 2:'."""
    def test_stdout_stands_in_for_an_empty_stderr(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            refuser = tdp / "refuser.py"
            refuser.write_text("import sys\n"
                               "print('cannot read /x/thank-you-result.json')\n"
                               "sys.exit(2)\n", encoding="utf-8")
            adapters = _adapters(tdp, *dl.PAGE_ROLES)
            adapters["thank_you"] = {"command": [sys.executable, str(refuser)]}
            with self.assertRaises(dl.DispatchError) as ctx:
                _dispatch(tdp, adapters)
            self.assertIn("exited 2: cannot read /x/thank-you-result.json",
                          str(ctx.exception))


class AnImageCapBelowThePlanIsRefusedBeforeAnythingStarts(unittest.TestCase):
    """F8: a launch whose pages need more images than the client's cap used to run every page on the
    stub (reserved 204 of a 200 cap, enforced false) and only skip a page on the paid provider."""
    def dispatch_with_cap(self, cap):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            rd = make_run_dir(tdp, adapters=False, parallel=1)
            inputs = tdp / "image-inputs.json"
            inputs.write_text(json.dumps({"design_style": "B", "brand_file": "/x/brand.json", "brand_owner": "Acme",
                                          "image_cap": cap, "image_provider": "stub", "test_only": True}), encoding="utf-8")
            p = run([sys.executable, str(HERE / "dispatch_launch.py"), "--run-dir", str(rd),
                     "--simulate-executor", "--image-inputs", str(inputs)])
            return p, rd

    def need(self):
        launch, _approval = approved_launch()
        return pset.offered_image_ceilings(pset.build_page_set(launch))["total"]

    def test_a_cap_one_image_short_refuses_and_starts_nothing(self):
        p, rd = self.dispatch_with_cap(self.need() - 1)
        self.assertEqual(p.returncode, dl.EXIT_VIOLATION, p.stdout + p.stderr)
        self.assertIn("smaller than this launch needs", p.stdout)
        self.assertIn("Nothing was started", p.stdout)
        self.assertFalse(list((rd / "dispatch").glob("result-*.json")))

    def test_a_cap_that_covers_the_pages_runs_every_page(self):
        p, rd = self.dispatch_with_cap(self.need())
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)


class TheLibraryPathRefusesACapBelowThePlanToo(unittest.TestCase):
    """F8 on the launcher path: the Black Friday launcher calls dl.dispatch() as a library with no
    strict_cap, so the refusal must be dispatch()'s default, as a DispatchError (the launcher names it)."""
    def need(self):
        launch, _approval = approved_launch()
        return pset.offered_image_ceilings(pset.build_page_set(launch))["total"]

    def library_run(self, cap, **kw):
        started = []
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            inner = dl._simulated_executor("library-cap-test")

            def executor(request, *rest):
                started.append(request["page_role"])
                return inner(request, *rest)
            executor.simulated = True
            launch, approval = approved_launch()
            try:
                manifest = dl.dispatch(launch, approval, client_identity_ref=CLIENT, worker_identity_ref=WORKER,
                                       out_dir=tdp / "dispatch", executor=executor,
                                       image_inputs={"image_provider": "stub", "image_cap": cap}, **kw)
            except dl.DispatchError as exc:
                return None, exc, started
            return manifest, None, started

    def test_a_cap_one_image_short_is_a_dispatch_error_and_nothing_starts(self):
        manifest, exc, started = self.library_run(self.need() - 1)
        self.assertIsNone(manifest)
        self.assertIsNotNone(exc, "the library default must refuse, not run every lane")
        self.assertIn("Nothing was started", str(exc))
        self.assertEqual(started, [])

    def test_a_cap_that_covers_the_pages_runs_every_page(self):
        manifest, exc, started = self.library_run(self.need())
        self.assertIsNone(exc)
        self.assertTrue(started)
        self.assertTrue(manifest["swarm"]["cap_preview"]["fits"])

    def test_no_image_inputs_means_no_cap_to_check(self):
        launch, approval = approved_launch()
        dl.dispatch(launch, approval, client_identity_ref=CLIENT, worker_identity_ref=WORKER)


class ALongRefusalKeepsItsTail(unittest.TestCase):
    """F4: wrappers print progress first and the refusal last; the head-only cut hid the cause."""
    def test_the_last_line_of_a_long_stderr_reaches_the_error(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            refuser = tdp / "refuser.py"
            refuser.write_text("import sys\n"
                               "for i in range(60):\n"
                               "    print('progress line %d: building the page set' % i, file=sys.stderr)\n"
                               "print('FAIL-CLOSED: launch profile signature_launch pads the page set',\n"
                               "      file=sys.stderr)\n"
                               "sys.exit(2)\n", encoding="utf-8")
            adapters = _adapters(tdp, *dl.PAGE_ROLES)
            adapters["thank_you"] = {"command": [sys.executable, str(refuser)]}
            with self.assertRaises(dl.DispatchError) as ctx:
                _dispatch(tdp, adapters)
            self.assertIn("pads the page set", str(ctx.exception))
            self.assertLess(len(str(ctx.exception)), 2500)  # bounded, not the whole log


def _flip(node, value):
    """Set every nested test_only (the offers carry it too) to value."""
    if isinstance(node, dict):
        for k in node:
            if k == "test_only":
                node[k] = value
            else:
                _flip(node[k], value)
    elif isinstance(node, list):
        for item in node:
            _flip(item, value)


def live_launch():
    """An approved launch that is NOT test_only, plus its plan approval record (as Command Center holds it)."""
    launch = deepcopy(LAUNCH_EXAMPLE)
    _flip(launch, False)
    launch["journey_mode"], launch["bump_enabled"] = "multiple_options", True
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = f"route-graph:{launch['launch_id']}:rev{launch['revision']}"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    launch["status"], launch["plan_approval_ref"] = "approved", "APPR-LIVE-1"
    approval = dict(approved_launch()[1], approval_id="APPR-LIVE-1", plan_hash=vlp.plan_document_hash(launch))
    return launch, approval


def command_center_holds(testcase, *records):
    """A live (not test_only) approval is fetched from Command Center and a dict never stands in for it, so the
    fetch is the one seam faked here: it answers with exactly these records and nothing else."""
    held = {r["approval_id"]: r for r in records}
    real = vlp._approval_verifier

    def verifier():
        mod = real()

        def fetch(approval_id, env):
            if approval_id not in held:
                mod._refuse("APPROVAL-NOT-FROM-AUTHORITY", "Command Center has no such approval record")
            return dict(held[approval_id])
        mod._fetch = fetch
        return mod
    patcher = mock.patch.object(vlp, "_approval_verifier", verifier)
    patcher.start()
    testcase.addCleanup(patcher.stop)


class APaidKieRunNeedsItsBudgetApproval(unittest.TestCase):
    """IMG-03: a paid (kie) execution that is not test_only needs a
    paid_asset_budget approval, whatever the write target is."""
    INPUTS = {"image_provider": "kie", "image_cap": 100000}

    def test_refused_without_and_accepted_with_the_approval(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            adapters = _adapters(tdp, *dl.PAGE_ROLES)
            pair = live_launch()
            budget = dict(pair[1], approval_id="APPR-PAID-1", kind="paid_asset_budget",
                          scope=["paid_asset_budget"], cap={"cap_minor": 8_000_000, "currency": "USD"})
            command_center_holds(self, pair[1], budget)
            with self.assertRaises(dl.DispatchError) as ctx:
                _dispatch(tdp, adapters, pair, image_inputs=self.INPUTS)
            self.assertIn("paid_asset_budget", str(ctx.exception))
            uncapped = {k: v for k, v in budget.items() if k != "cap"}
            command_center_holds(self, pair[1], uncapped)
            with self.assertRaises(dl.DispatchError) as ctx:  # a budget with no cap is no budget
                _dispatch(tdp, adapters, pair, image_inputs=self.INPUTS, scoped_approvals=[uncapped])
            self.assertIn("spend cap", str(ctx.exception))
            command_center_holds(self, pair[1], budget)
            manifest, _ = _dispatch(tdp, adapters, pair, image_inputs=self.INPUTS,
                                    scoped_approvals=[budget])
            self.assertEqual(manifest["execution"], "executed")
            self.assertEqual(len(manifest["results"]), len(dl.PAGE_ROLES))

    def test_a_test_only_kie_launch_needs_no_budget_approval(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = _dispatch(Path(td), _adapters(Path(td), *dl.PAGE_ROLES),
                                    image_inputs=self.INPUTS)
            self.assertEqual(manifest["execution"], "executed")

    def test_the_free_stub_provider_needs_no_budget_approval(self):
        with tempfile.TemporaryDirectory() as td:
            manifest, _ = _dispatch(
                Path(td), _adapters(Path(td), *dl.PAGE_ROLES),
                image_inputs={"image_provider": "stub", "image_cap": 100000})
            self.assertEqual(manifest["execution"], "executed")


class LaunchEventsAreEmittedAndNeverBlock(unittest.TestCase):
    class Fake:
        def __init__(self, boom=False):
            self.calls, self.boom = [], boom

        def emit(self, skill, launch_id, event):
            self.calls.append((skill, launch_id, event))
            if self.boom:
                raise RuntimeError("Command Center is down")

    def _run(self, fake, *, with_out_dir=True, bad_lane=None):
        real = dl._load_launch_events
        dl._load_launch_events = lambda: fake
        self.addCleanup(setattr, dl, "_load_launch_events", real)
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            adapters = _adapters(tdp, *dl.PAGE_ROLES)
            if bad_lane:
                bad = tdp / "bad.py"
                bad.write_text("import sys\nsys.exit(2)\n", encoding="utf-8")
                adapters[bad_lane] = {"command": [sys.executable, str(bad)]}
            if with_out_dir:
                return _dispatch(tdp, adapters)[0]
            launch, approval = approved_launch()
            return dl.dispatch(launch, approval, client_identity_ref=CLIENT,
                               worker_identity_ref=WORKER,
                               executor=dl._simulated_executor("x"))

    def test_events_go_out_as_skill_49_in_contract_order(self):
        fake = self.Fake()
        self._run(fake)
        self.assertEqual({c[0] for c in fake.calls}, {49})
        self.assertEqual(len({c[1] for c in fake.calls}), 1)
        evs = [c[2] for c in fake.calls]
        self.assertEqual(evs[0], {"event_type": "run_initialized"})
        closed = evs[1:-1]
        self.assertEqual([e["event_type"] for e in closed], ["item_closed"] * len(dl.PAGE_ROLES))
        self.assertEqual({e["item"] for e in closed}, set(dl.PAGE_ROLES))
        self.assertEqual({e["stage"] for e in closed}, {"dispatch"})
        self.assertEqual(evs[-1], "dispatch")

    def test_a_failed_lane_is_blocked_and_the_error_is_unchanged(self):
        fake = self.Fake()
        with self.assertRaises(dl.DispatchError) as ctx:
            self._run(fake, bad_lane="thank_you")
        self.assertIn("thank_you", str(ctx.exception))
        evs = [c[2] for c in fake.calls]
        blocked = [e for e in evs if isinstance(e, dict) and e["event_type"] == "item_blocked"]
        self.assertEqual([e["item"] for e in blocked], ["thank_you"])
        self.assertEqual(evs[-1]["event_type"], "stage_blocked")
        self.assertEqual(evs[-1]["stage"], "dispatch")
        self.assertNotIn("dispatch", evs)

    def test_an_emitter_that_raises_or_is_missing_never_fails_the_launch(self):
        self.assertEqual(self._run(self.Fake(boom=True))["execution"], "executed")
        self.assertEqual(self._run(None)["execution"], "executed")

    def test_without_an_out_dir_nothing_is_emitted(self):
        fake = self.Fake()
        self._run(fake, with_out_dir=False)
        self.assertEqual(fake.calls, [])


class ALoneInstallStillEmits(unittest.TestCase):
    def test_emission_only_needs_no_skill_71_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            skill = lone_install(tdp)
            rd = make_run_dir(tdp, adapters=False)
            p = run([sys.executable, str(skill / "scripts" / "dispatch_launch.py"),
                     "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertNotIn("ModuleNotFoundError", out)
            self.assertEqual(p.returncode, 0, out)
            manifest = json.loads(
                (rd / "dispatch" / "dispatch-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["execution"], "emitted_not_executed", out)

    def test_the_emitter_is_found_by_walking_up_from_the_install(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            skill = lone_install(tdp)
            sink = tdp / "events.jsonl"
            stub = skill.parent / "shared-utils" / "signature_launch" / "launch_events.py"
            stub.parent.mkdir(parents=True)
            stub.write_text(
                "import json, os\n"
                "def emit(skill, launch_id, event):\n"
                "    with open(os.environ['STUB_EVENTS'], 'a') as f:\n"
                "        f.write(json.dumps([skill, launch_id, event]) + '\\n')\n",
                encoding="utf-8")
            rd = make_run_dir(tdp, adapters=False)
            p = subprocess.run(
                [sys.executable, str(skill / "scripts" / "dispatch_launch.py"),
                 "--run-dir", str(rd)],
                capture_output=True, text=True, env=dict(os.environ, STUB_EVENTS=str(sink)))
            self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
            lines = [json.loads(x) for x in sink.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(lines[0][0], 49)
            self.assertEqual(lines[0][2], {"event_type": "run_initialized"})

    def test_execution_preflight_names_the_missing_sibling(self):
        with tempfile.TemporaryDirectory() as td:
            tdp = Path(td)
            skill = lone_install(tdp)
            rd = make_run_dir(tdp, adapters=True)
            p = run([sys.executable, str(skill / "scripts" / "dispatch_launch.py"),
                     "--run-dir", str(rd)])
            out = p.stdout + p.stderr
            self.assertEqual(p.returncode, dl.EXIT_VIOLATION, out)
            self.assertIn("71-blackceo-signature-page", out)
            self.assertIn("swarm_runner.py", out)


SHA = "a" * 64
# A consumer whose result claims a finished, independently reviewed page.
REVIEWED_CONSUMER = CONSUMER.replace("'status': 'authored', 'artifacts': []", "'status': 'locally_verified', 'artifacts': [{'path': 'a.png', 'sha256': '" + SHA + "'}]"
    ).replace("'reviewer_session': None, 'independent_review': False,\n       'proof_class': 'L0'", "'reviewer_session': 'rev-1', 'independent_review': True,\n       'proof_class': 'L2'")


class ClientDeliveryNeedsAnIndependentReview(unittest.TestCase):
    """Issue 30 / M2: the executor validates at scope client_delivery unless the request is a local rehearsal
    (test_only AND local_only), so an unreviewed result can no longer pass a launch that is going to a client."""

    def run_lane(self, td, consumer_src, *, test_only, target, review=None, ledger=None,
                 extra=(), lane=None, review_name="review-checkout.json", ledger_text=None):
        consumer = td / "consumer.py"
        consumer.write_text(consumer_src, encoding="utf-8")
        launch, _approval = approved_launch()
        req = next(r for r in dl.build_requests(launch, clr.compile_route(launch), copy_profile="standard",
                                                allowed_write_target=target) if r["page_role"] == "checkout")
        req["test_only"] = test_only
        (td / "request-checkout.json").write_text(json.dumps(req), encoding="utf-8")  # dispatch stages it first
        cfg = {"adapters": {lane or "checkout": {"command": [sys.executable, str(consumer), "{request}", "{result}",
                                                              *extra]}}}
        if review is not None:
            (td / review_name).write_text(review if isinstance(review, str) else json.dumps(review), encoding="utf-8")
        if ledger is not None:
            (td / 'dispatch-session-registry.json').write_text(
                ledger if isinstance(ledger, str) else json.dumps(ledger), encoding="utf-8")
        return dl.executor_from_config(cfg, td)(req, lane)

    def review(self, **over):
        rec = {"schema": "signature-launch-review-record/v1", "reviewer_session": "rev-1", "reviewer_model": "m",
               "verdict": "PASS", "request_id": None, "reviewed_artifacts": [{"path": "a.png", "sha256": SHA}]}
        rec.update(over)
        return rec

    LEDGER = {"sessions": [{"session_id": "rev-1", "model": "m"}]}

    def test_the_review_placeholder_in_an_adapter_command_names_the_staged_record(self):
        # a consumer that records the {review} argument it was handed
        spy = CONSUMER + "open(sys.argv[2] + '.review-arg', 'w').write(sys.argv[3])\n"
        for lane, name in ((None, "review-checkout.json"), ("downsell_2", "review-downsell_2.json")):
            with self.subTest(lane=lane), tempfile.TemporaryDirectory() as td:
                td = Path(td)
                self.run_lane(td, spy, test_only=True, target="local_only", extra=("{review}",), lane=lane)
                seen = list(td.glob("*.review-arg"))
                self.assertEqual(len(seen), 1)
                self.assertEqual(seen[0].read_text(encoding="utf-8"), str(td / name))

    def test_a_local_rehearsal_needs_no_review(self):
        with tempfile.TemporaryDirectory() as td:
            res = self.run_lane(Path(td), CONSUMER, test_only=True, target="local_only")
            self.assertFalse(res["independent_review"])

    def test_an_unreviewed_result_is_refused_for_a_client_delivery(self):
        for test_only, target in ((False, "local_only"), (True, "approved_test_location")):
            with self.subTest(test_only=test_only, target=target), tempfile.TemporaryDirectory() as td:
                with self.assertRaises(dl.DispatchError) as ctx:
                    self.run_lane(Path(td), CONSUMER, test_only=test_only, target=target)
                self.assertIn("client_delivery needs an independent review record", str(ctx.exception))

    def test_a_valid_review_record_passes_a_client_delivery(self):
        with tempfile.TemporaryDirectory() as td:
            req_id = None
            launch, _ = approved_launch()
            req_id = next(r for r in dl.build_requests(launch, clr.compile_route(launch), copy_profile="standard",
                                                       allowed_write_target="local_only")
                          if r["page_role"] == "checkout")["request_id"]
            res = self.run_lane(Path(td), REVIEWED_CONSUMER, test_only=False, target="local_only",
                                review=self.review(request_id=req_id), ledger=self.LEDGER)
            self.assertTrue(res["independent_review"])
            self.assertEqual(res["reviewer_session"], "rev-1")

    def test_a_review_claim_with_a_failed_verdict_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(dl.DispatchError) as ctx:
                self.run_lane(Path(td), REVIEWED_CONSUMER, test_only=False, target="local_only",
                              review=self.review(verdict="FAIL"), ledger=self.LEDGER)
            self.assertIn("no recognised successful verdict", str(ctx.exception))

    def test_a_lane_reads_its_own_review_record_not_its_parents(self):
        with tempfile.TemporaryDirectory() as td:
            launch, _ = approved_launch()
            req_id = next(r for r in dl.build_requests(launch, clr.compile_route(launch), copy_profile="standard",
                                                       allowed_write_target="local_only")
                          if r["page_role"] == "checkout")["request_id"]
            kw = dict(test_only=False, target="local_only", lane="downsell_2", ledger=self.LEDGER)
            res = self.run_lane(Path(td), REVIEWED_CONSUMER, review=self.review(request_id=req_id),
                                review_name="review-downsell_2.json", **kw)
            self.assertTrue(res["independent_review"])
        with tempfile.TemporaryDirectory() as td:  # a record under the parent's name does not count for the lane
            with self.assertRaises(dl.DispatchError):
                self.run_lane(Path(td), REVIEWED_CONSUMER, review=self.review(request_id=req_id),
                              review_name="review-checkout.json", **kw)

    def test_an_unparseable_review_or_ledger_file_is_a_refusal_not_a_crash(self):
        launch, _ = approved_launch()
        req_id = next(r for r in dl.build_requests(launch, clr.compile_route(launch), copy_profile="standard",
                                                   allowed_write_target="local_only")
                      if r["page_role"] == "checkout")["request_id"]
        for label, review, ledger in (("review", "{not json", self.LEDGER),
                                      ("ledger", self.review(request_id=req_id), "{not json")):
            with self.subTest(bad=label), tempfile.TemporaryDirectory() as td:
                with self.assertRaises(dl.DispatchError):
                    self.run_lane(Path(td), REVIEWED_CONSUMER, test_only=False, target="local_only",
                                  review=review, ledger=ledger)

    def test_a_review_claim_with_no_record_on_disk_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(dl.DispatchError) as ctx:
                self.run_lane(Path(td), REVIEWED_CONSUMER, test_only=False, target="local_only")
            self.assertIn("without a review record", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)

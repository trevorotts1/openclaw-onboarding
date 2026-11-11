"""Skill 83 adapter configuration (U-structure-01): what build_dispatch_config binds, and what it refuses.

STR-03  the product_selection result lists the order page designs, so `assemble` accepts a multiple_options launch
IMG-05  --allow-paid reaches the order page (Skill 78) exactly when the approved image plan allows paid
UPS-16  only the launch extras in the route graph need inputs and get an adapter entry; downsell_2 only when routed
ENF-08  an adapter command that is not a pinned wrapper is refused ('adapter not in allow-list')
DTY-01  the thank_you entry is the design-only chain: 71 shared service, run_page_role_stages, translator --design-only

Free and offline. The order page's image stage is stood in for by a tiny script that writes the files Skill 71's stub
provider writes (Skill 71's own prompt budget needs a measured design system a unit test cannot invent); the plan
builder, the page-result emitter and the new attach step are the real ones, wired by the real command.
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
SKILL_ROOT = HERE.parent
sys.path[:0] = [str(SKILL_ROOT), str(SKILL_ROOT / "routes"), str(HERE)]

import adapters  # noqa: E402
import substrate  # noqa: E402
sys.path.insert(0, str(SKILL_ROOT / "fixtures"))
from test_only_readback import TEST_ONLY_CHECKOUT_READBACK  # noqa: E402
from launcher_core import intake, launch_bridge, package, route  # noqa: E402
from test_lane83_dispatch import ELEVATION_PAGES, consumer_config, payload, run_dispatch  # noqa: E402

CONSUMER = HERE / "lane83_fake_consumer.py"
LABELS = substrate.source("71-blackceo-signature-page/scripts/deliverable_labels.py")
EXTRAS = {"u1_only": {"upsell_1": True, "downsell_1": False, "upsell_2": False},
          "u1_d1": {"upsell_1": True, "downsell_1": True, "upsell_2": False},
          "all": {"upsell_1": True, "downsell_1": True, "upsell_2": True}}


def segments(script: str) -> list:
    """The `&&` steps of a bash -c script, each as its own argv."""
    lexer = shlex.shlex(script, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    steps, current = [], []
    for token in lexer:
        if token == "&&":
            steps.append(current)
            current = []
        else:
            current.append(token)
    return steps + [current]


def step(config: dict, role: str, wrapper: str) -> list:
    return next(s for s in segments(config["adapters"][role]["command"][2]) if wrapper in " ".join(s))


def stamped_checkout(directory: Path):
    """A checkout request and a manuscript carrying its source stamp, as Skill 79's emitter leaves them."""
    request = Path(directory) / "checkout-request.json"
    request.write_text('{"main_offer_id": "TEST-ONLY"}', encoding="utf-8")
    manuscript = Path(directory) / "checkout.md"
    manuscript.write_text("<!-- source_request_sha256: %s -->\n\nx\n"
                          % hashlib.sha256(request.read_bytes()).hexdigest(), encoding="utf-8")
    return manuscript, request


class Inputs:
    """Real files in a temp folder: a launch record, a bridge config and per-role sidecars."""

    def __init__(self, test: unittest.TestCase, extras: str = "all", roles=None):
        tmp = tempfile.TemporaryDirectory()
        test.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        (self.root / "work").mkdir()

        def write(name: str, doc=None) -> Path:
            path = self.root / name
            path.write_text(json.dumps({} if doc is None else doc), encoding="utf-8")
            return path

        launch = write("launch.json", {"tenant_id": "t", "location_id": "l", "launch_id": "L", "revision": 1,
                                       "journey_mode": "multiple_options", "extras": EXTRAS[extras],
                                       "test_only": True})
        roles = roles if roles is not None else [r for r in ("upsell_1", "upsell_2", "downsell_1")
                                                 if EXTRAS[extras][r]]
        self.kwargs = {
            "work_dir": self.root / "work", "launch_record": launch, "bridge_config": write("bridge.json"),
            "author_session": "session-test", "image_inputs": write("image-inputs.json"),
            "copy": {r: write(f"copy-{r}.json") for r in roles},
            "journey": {r: write(f"journey-{r}.json") for r in roles},
            "enrichment": {r: write(f"enrichment-{r}.json") for r in roles},
        }
        self.write = write

    def build(self, **over) -> dict:
        return adapters.build_dispatch_config(**{**self.kwargs, **over})


class PaidFlagTests(unittest.TestCase):
    """IMG-05: --allow-paid reaches the order page exactly when the image plan allows paid."""

    def test_the_order_page_command_carries_allow_paid_only_on_a_paid_launch(self):
        inputs = Inputs(self)
        free = step(inputs.build(), "product_selection", "run_image_stages.py")
        self.assertNotIn("--allow-paid", free)
        paid_config = inputs.build(allow_paid=True)
        paid = step(paid_config, "product_selection", "run_image_stages.py")
        self.assertIn("--allow-paid", paid)
        # the same decision every other paid lane already follows
        self.assertIn("--allow-paid", paid_config["adapters"]["upsell_1"]["command"])
        pipeline = step(paid_config, "thank_you", "shared_page_service.py")
        self.assertIn("--allow-paid", shlex.split(pipeline[pipeline.index("--pipeline-command") + 1]))

    def test_the_image_plans_answer_is_the_only_answer(self):
        inputs = Inputs(self)
        plan = {"allow_paid": True}
        self.assertIn("--allow-paid", step(inputs.build(allow_paid=True, image_plan=plan), "product_selection",
                                           "run_image_stages.py"))
        with self.assertRaises(adapters.AdapterError):  # paid asked for, plan says free: nothing is built
            inputs.build(allow_paid=True, image_plan={"allow_paid": False})
        with self.assertRaises(adapters.AdapterError):  # plan says paid, caller says free
            inputs.build(allow_paid=False, image_plan={"allow_paid": True})


class DesignStageTests(unittest.TestCase):
    """Issue 72: dispatch runs the upsell wrapper at the design stage, where eligibility is a design marker."""

    def test_dispatch_runs_both_upsell_wrappers_at_the_design_stage(self):
        config = Inputs(self, "all").build()
        for role in ("upsell_1", "upsell_2"):
            command = config["adapters"][role]["command"]
            at = command.index("--stage")
            self.assertEqual(command[at + 1], "design", role)
            self.assertEqual(command.count("--stage"), 1, role)
        for role in ("downsell_1",):
            self.assertNotIn("--stage", config["adapters"][role]["command"])


class RoutedRolesTests(unittest.TestCase):
    """UPS-16: inputs and entries only for the roles the launch routes."""

    def test_a_u1_only_launch_builds_without_u2_or_d1_inputs(self):
        config = Inputs(self, "u1_only").build()
        self.assertEqual(set(config["adapters"]), {"landing", "product_selection", "thank_you", "upsell_1"})

    def test_u1_and_d1_without_u2(self):
        config = Inputs(self, "u1_d1").build()
        self.assertEqual(set(config["adapters"]) - {"landing", "product_selection", "thank_you"},
                         {"upsell_1", "downsell_1"})

    def test_a_routed_role_still_needs_its_own_inputs(self):
        inputs = Inputs(self, "u1_d1", roles=["upsell_1"])  # D1 is routed but nothing was supplied for it
        with self.assertRaises(adapters.AdapterError) as ctx:
            inputs.build()
        self.assertIn("downsell_1", str(ctx.exception))

    def test_downsell_2_is_built_only_when_asked_for_and_routed(self):
        inputs = Inputs(self, "u1_d1")
        self.assertNotIn("downsell_2", inputs.build()["adapters"])
        inputs.kwargs["copy"]["downsell_2"] = inputs.write("copy-downsell_2.json")
        command = inputs.build(extra_pages=("downsell_2",))["adapters"]["downsell_2"]["command"]
        self.assertEqual(command[command.index("--role-instance") + 1], "downsell_2")
        # CARRIED 116: a design page that draws its own images, in its own folder, never downsell_1's
        self.assertIn("--skill71-root", command)
        run_dir = command[command.index("--images-run-dir") + 1]
        self.assertTrue(run_dir.endswith("downsell_2-images"), run_dir)
        self.assertNotIn("downsell_1-images", run_dir)
        self.assertEqual(command[command.index("--author-session") + 1], "session-test")
        self.assertNotIn("--allow-paid", command)
        self.assertIn("--allow-paid", inputs.build(allow_paid=True, extra_pages=("downsell_2",))
                      ["adapters"]["downsell_2"]["command"])
        no_d1 = Inputs(self, "u1_only")
        no_d1.kwargs["copy"]["downsell_2"] = no_d1.write("copy-downsell_2.json")
        with self.assertRaises(adapters.AdapterError):  # D1 is not routed, so there is nothing for D2 to ride on
            no_d1.build(extra_pages=("downsell_2",))
        with self.assertRaises(adapters.AdapterError):
            inputs.build(extra_pages=("downsell_3",))
        del inputs.kwargs["copy"]["downsell_2"]
        with self.assertRaises(adapters.AdapterError):  # asked for, but no copy supplied
            inputs.build(extra_pages=("downsell_2",))


class UpsellTwoCopyTests(unittest.TestCase):
    """CARRIED 140: U2 copy is checked against the U1 copy the launch supplied."""

    def test_upsell_2_carries_the_u1_copy_path(self):
        inputs = Inputs(self)
        config = inputs.build()
        command = config["adapters"]["upsell_2"]["command"]
        self.assertEqual(command[command.index("--u1-copy") + 1], str(inputs.kwargs["copy"]["upsell_1"]))
        self.assertNotIn("--u1-copy", config["adapters"]["upsell_1"]["command"])

    def test_a_u1_less_launch_has_no_upsell_2_entry(self):
        self.assertNotIn("upsell_2", Inputs(self, "u1_d1").build()["adapters"])


class ThankYouTests(unittest.TestCase):
    """DTY-01: the launch-time thank_you page is a design deliverable."""

    def test_the_entry_chains_the_image_service_the_stages_and_the_design_only_translator(self):
        config = Inputs(self).build()
        steps = segments(config["adapters"]["thank_you"]["command"][2])
        self.assertEqual([Path(s[1]).name for s in steps],
                         ["adapters.py", "adapters.py", "shared_page_service.py", "translate_thank_you_result.py"])
        # first the run composes the design prose itself, then checks it: a hand-typed one never reaches an image
        self.assertEqual([steps[0][2], steps[1][2]], ["compose-design-prose", "check-design-prose"])
        steps = steps[2:]
        service = steps[0]
        self.assertEqual(service[service.index("--page-version") + 1], "thank-you")
        pipeline = shlex.split(service[service.index("--pipeline-command") + 1])
        self.assertEqual(Path(pipeline[1]).name, "run_page_role_stages.py")
        self.assertIn("--design-only", steps[1])
        self.assertEqual(steps[1][steps[1].index("--images-run-dir") + 1], pipeline[2])  # the translator reads what the stages drew
        self.assertEqual(steps[1][steps[1].index("--author-session") + 1], "session-test")

    def test_the_thank_you_pipeline_passes_skill_82s_no_pitch_scanner(self):
        """AF-71-THANK-YOU-PITCH: the runner is told to scan the manuscript with Skill 82's own script."""
        service = step(Inputs(self).build(), "thank_you", "shared_page_service.py")  # the chain now heads with compose and check
        pipeline = shlex.split(service[service.index("--pipeline-command") + 1])
        self.assertIn("--no-pitch-scan", pipeline)
        scanner = Path(pipeline[pipeline.index("--no-pitch-scan") + 1])
        self.assertEqual(scanner, substrate.source("82-signature-thank-you/scripts/semantic_scan.py"))
        self.assertTrue(scanner.is_file())


def adapters_thank_you_script(test: unittest.TestCase) -> str:
    return Inputs(test).build()["adapters"]["thank_you"]["command"][2]


class CheckoutCopyDispatchTests(unittest.TestCase):
    """Issue 12: the order form's copy reaches the checkout lane only as Skill 79's stamped output, and the
    refusal is made by build_dispatch_config itself (these go THROUGH the builder, not the helper)."""

    def design(self, inputs, manuscript, request):
        brand = inputs.write("checkout-brand.md")
        return {"manuscript": manuscript, "brand_file": brand, "brand_owner": "o", "image_cap": 1,
                **({"checkout_request": request} if request is not None else {})}

    def test_a_stamped_manuscript_for_its_own_request_is_dispatched(self):
        inputs = Inputs(self)
        manuscript, request = stamped_checkout(inputs.root)
        command = inputs.build(checkout_design=self.design(inputs, manuscript, request))["adapters"]["checkout"]["command"]
        self.assertEqual(command[command.index("--checkout-request") + 1], str(request))  # the wrapper re-checks the stamp

    def test_an_unstamped_manuscript_is_refused_by_the_builder(self):
        inputs = Inputs(self)
        _, request = stamped_checkout(inputs.root)
        staged = inputs.root / "staged.md"
        staged.write_text("## Section 1: Offer\n\nHand-written.\n", encoding="utf-8")
        with self.assertRaises(adapters.AdapterError) as ctx:
            inputs.build(checkout_design=self.design(inputs, staged, request))
        self.assertIn("never staged by hand", str(ctx.exception))

    def test_a_manuscript_stamped_for_another_request_is_refused_by_the_builder(self):
        inputs = Inputs(self)
        manuscript, request = stamped_checkout(inputs.root)
        request.write_text('{"main_offer_id": "SOMETHING-ELSE"}', encoding="utf-8")  # the request moved on
        with self.assertRaises(adapters.AdapterError) as ctx:
            inputs.build(checkout_design=self.design(inputs, manuscript, request))
        self.assertIn("never staged by hand", str(ctx.exception))

    def test_a_manuscript_with_two_stamps_is_refused_by_the_builder(self):
        inputs = Inputs(self)
        manuscript, request = stamped_checkout(inputs.root)
        manuscript.write_text(manuscript.read_text(encoding="utf-8") + manuscript.read_text(encoding="utf-8"),
                              encoding="utf-8")
        with self.assertRaises(adapters.AdapterError):
            inputs.build(checkout_design=self.design(inputs, manuscript, request))

    def test_an_emitter_that_exits_clean_without_writing_the_copy_is_refused(self):
        inputs = Inputs(self)
        out = inputs.root / "never-written.md"
        done = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
        with mock.patch.object(adapters.subprocess, "run", return_value=done):
            with self.assertRaises(adapters.AdapterError):
                adapters.emit_checkout_manuscript(request=inputs.root / "r.json", launch=inputs.root / "launch.json",
                                                  terms=inputs.root / "t.json", out=out)

    def test_a_launcher_without_the_skill_79_emitter_refuses_by_name(self):
        inputs = Inputs(self)
        with mock.patch.object(adapters.substrate, "source", return_value=inputs.root / "absent.py"):
            with self.assertRaises(adapters.AdapterError) as ctx:
                adapters.emit_checkout_manuscript(request=inputs.root / "r.json", launch=inputs.root / "launch.json",
                                                  terms=inputs.root / "t.json", out=inputs.root / "o.md")
        self.assertIn("not installed", str(ctx.exception))

    def test_no_checkout_request_is_refused_by_the_builder(self):
        inputs = Inputs(self)
        manuscript, _ = stamped_checkout(inputs.root)
        for missing in (None, ""):
            with self.assertRaises(adapters.AdapterError) as ctx:
                inputs.build(checkout_design=self.design(inputs, manuscript, missing))
            self.assertIn("checkout_request", str(ctx.exception))


class AllowListTests(unittest.TestCase):
    """ENF-08: a supplied adapter config is held to the pinned wrappers."""

    def test_what_the_builder_emits_passes_its_own_allow_list(self):
        inputs = Inputs(self)
        checkout = inputs.write("checkout.md")
        manuscript, request = stamped_checkout(inputs.root)
        config = inputs.build(checkout_design={"manuscript": manuscript, "checkout_request": request,
                                               "brand_file": checkout, "brand_owner": "o", "image_cap": 1})
        adapters.validate_adapter_config(config)
        self.assertIn("checkout", config["adapters"])
        command = config["adapters"]["checkout"]["command"]
        self.assertEqual(command[command.index("--checkout-request") + 1], str(request))

    def refused(self, command, **kw):
        with self.assertRaises(adapters.AdapterNotAllowed) as ctx:
            adapters.validate_adapter_config({"adapters": {"landing": {"command": command, "timeout_s": 5}}}, **kw)
        self.assertIn("adapter not in allow-list", str(ctx.exception))

    def test_python_dash_c_is_refused(self):
        self.refused(["python3", "-c", "print('a page')"])

    def test_an_unpinned_script_is_refused_even_with_a_pinned_name(self):
        self.refused([sys.executable, "/tmp/landing_bridge.py", "--request", "{request}"])
        with tempfile.TemporaryDirectory() as tmp:  # the right name in the wrong place
            copy = Path(tmp) / "landing_bridge.py"
            copy.write_text("print('fake')\n", encoding="utf-8")
            self.refused([sys.executable, str(copy)])

    def test_a_shell_cannot_carry_anything_unpinned(self):
        pinned = str(substrate.source("49-signature-funnel/scripts/landing_bridge.py"))
        ok = f"{shlex.quote(sys.executable)} {shlex.quote(pinned)} --request \"{{request}}\""
        adapters.validate_adapter_config({"adapters": {"landing": {"command": ["bash", "-c", ok], "timeout_s": 5}}})
        for bad in (ok + " && curl example.invalid", ok + "; rm -rf x", ok + " | tee y", ok + "\ncurl x",
                    ok + " $(id)", "curl example.invalid", ok + " > a > b"):
            self.refused(["bash", "-c", bad])
        self.refused(["bash", "-lc", ok])

    def test_a_pipeline_command_must_be_a_pinned_stage_runner(self):
        inputs = Inputs(self)
        config = inputs.build()
        script = config["adapters"]["thank_you"]["command"][2]
        service = step(config, "thank_you", "shared_page_service.py")
        inner = service[service.index("--pipeline-command") + 1]
        evil = script.replace(shlex.quote(inner), shlex.quote(f"{sys.executable} -c 'print(1)'"))
        self.assertNotEqual(evil, script)
        with self.assertRaises(adapters.AdapterNotAllowed):
            adapters.validate_adapter_config({"adapters": {"thank_you": {"command": ["bash", "-c", evil]}}})

    def test_the_no_pitch_flag_may_name_only_skill_82s_scanner(self):
        """A stand-in scanner that always passes would void AF-71-THANK-YOU-PITCH, so it is refused by name."""
        script = adapters_thank_you_script(self)
        service = next(s for s in segments(script) if "shared_page_service.py" in " ".join(s))  # not steps[0]: compose and check head the chain
        inner = service[service.index("--pipeline-command") + 1]
        pipeline = shlex.split(inner)
        adapters.validate_adapter_config({"adapters": {"thank_you": {"command": ["bash", "-c", script]}}})
        pipeline[pipeline.index("--no-pitch-scan") + 1] = "/tmp/always_pass.py"
        evil = script.replace(shlex.quote(inner), shlex.quote(shlex.join(pipeline)))
        self.assertNotEqual(evil, script)
        with self.assertRaises(adapters.AdapterNotAllowed) as ctx:
            adapters.validate_adapter_config({"adapters": {"thank_you": {"command": ["bash", "-c", evil]}}})
        self.assertIn("--no-pitch-scan", str(ctx.exception))

    def test_the_fake_design_consumer_passes_only_for_a_test_only_launch(self):
        command = [sys.executable, str(CONSUMER), "{request}", "{result}", str(LABELS)]
        self.refused(command)
        self.refused(command, test_only=False)
        adapters.validate_adapter_config({"adapters": {"landing": {"command": command}}}, test_only=True)

    def test_a_role_outside_the_page_roles_and_placeholders_are_refused(self):
        with self.assertRaises(adapters.AdapterNotAllowed):
            adapters.validate_adapter_config({"adapters": {"payments": {"command": ["x"]}}})
        with self.assertRaises(adapters.PlaceholderRefused):
            adapters.validate_adapter_config({"adapters": {"landing": {"command": [
                sys.executable, "/path/to/49-signature-funnel/scripts/landing_bridge.py"]}}})
        with self.assertRaises(adapters.AdapterError):
            adapters.validate_adapter_config({"adapters": {}})


class FakeConsumerTests(unittest.TestCase):
    def run_consumer(self, test_only):
        with tempfile.TemporaryDirectory() as tmp:
            request = Path(tmp) / "request.json"
            request.write_text(json.dumps({"page_role": "upsell_1", "tenant_id": "t", "location_id": "l",
                                           "launch_id": "L", "revision": 1, "request_id": "r", "input_hash": "h",
                                           "page_id": "p", "test_only": test_only}), encoding="utf-8")
            result = Path(tmp) / "result.json"
            proc = subprocess.run([sys.executable, str(CONSUMER), str(request), str(result), str(LABELS)],
                                  capture_output=True, text=True)
            return proc, (json.loads(result.read_text()) if result.exists() else None)

    def test_it_refuses_a_request_that_is_not_test_only(self):
        for flag in (False, None):
            proc, result = self.run_consumer(flag)
            self.assertEqual(proc.returncode, 3, proc.stderr)
            self.assertIn("test_only", proc.stderr)
            self.assertIsNone(result)

    def test_it_still_answers_a_test_only_request(self):
        proc, result = self.run_consumer(True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(result["artifacts"])


# the order page's copy form fixes how many section images each deliverable needs (Skill 49 page_types.json)
SECTIONS = substrate.load("49-signature-funnel/scripts/page_set.py", "adapters_config_page_set",
                          "49-signature-funnel/scripts").section_counts("product_selection")[0]
STAND_IN = """
import json, sys
from pathlib import Path
argv = sys.argv[2:]
run = Path(argv[argv.index("--run-dir") + 1])
for n in range(1, __SECTIONS__ + 1):
    for rel in (f"desktop-wireframe/section-{n}.png", f"mobile-tablet/section-{n}.png",
                f"visual-mockup/desktop/part-{n}.png", f"visual-mockup/mobile/part-{n}.png"):
        (run / rel).parent.mkdir(parents=True, exist_ok=True)
        (run / rel).write_bytes(b"stub png " + rel.encode())
(run / "visual-mockup" / "stage-executor-record.json").write_text(json.dumps({"provider": "stub"}))
(run.parent / "image-stage-argv.json").write_text(json.dumps(argv))
"""


_SPOOL = {}


def setUpModule():
    # Building a package appends launch events to ~/.openclaw/data/signature-launch/events-spool when no ingest
    # URL is set. Send them to a temp folder, so nothing in this module (or in a child launcher it starts,
    # which inherits the variable) writes into the real home folder.
    _SPOOL["dir"] = tempfile.TemporaryDirectory()
    _SPOOL["env"] = mock.patch.dict(os.environ, {"LAUNCH_EVENTS_SPOOL": _SPOOL["dir"].name})
    _SPOOL["env"].start()


def tearDownModule():
    _SPOOL["env"].stop()
    _SPOOL["dir"].cleanup()


class SelectionAssemblyTests(unittest.TestCase):
    """STR-03 and the IMG-05 paid dry run, end to end: dispatch the multiple_options fixture, then assemble."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.out = self.root / "run"
        self.brand = self.root / "brand.json"
        self.brand.write_text("{}", encoding="utf-8")
        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        (bin_dir / "stand_in_images.py").write_text(STAND_IN.replace("__SECTIONS__", str(SECTIONS)), encoding="utf-8")
        # an interpreter named python3 that runs the stand-in for Skill 78's image stage and python for the rest
        self.python = bin_dir / "python3"
        self.python.write_text('#!/bin/sh\nfor a in "$@"; do case "$a" in *run_image_stages.py) exec "%s" "%s" "$@";; esac; done\n'
                               'exec "%s" "$@"\n' % (sys.executable, bin_dir / "stand_in_images.py", sys.executable))
        self.python.chmod(0o755)

    def dispatch(self, doc, paid=False):
        files = self.root / "inputs"
        files.mkdir(exist_ok=True)

        def f(name, text="{}"):
            path = files / name
            path.write_text(text, encoding="utf-8")
            return str(path)
        roles = ("upsell_1", "upsell_2", "downsell_1")
        # the bridge refuses a config with no landing section; it fills landing.image_inputs from the approved plan
        adapter_inputs = {"bridge_config": f("bridge.json", '{"landing": {}}'), "author_session": "sess",
                          "copy": {r: f(f"copy-{r}.json") for r in roles},
                          "journey": {r: f(f"journey-{r}.json") for r in roles},
                          "enrichment": {r: f(f"enrichment-{r}.json") for r in roles}}
        real_build = adapters.build_dispatch_config
        built = {}

        def build(**kw):
            if paid:  # a paid image plan, kept free here: the provider in the inputs file stays stub
                kw["allow_paid"] = True
                kw["image_plan"] = {**kw["image_plan"], "allow_paid": True}
            built["config"] = real_build(python=str(self.python), **kw)
            return built["config"]

        real = substrate.dispatch()
        fake_pages = consumer_config()

        def executor(config, work_dir, landing_pages=None):  # every page but the order page answers from the fake
            mixed = {"adapters": {**fake_pages["adapters"], "product_selection": config["adapters"]["product_selection"]}}
            return real.executor_from_config(mixed, work_dir, landing_pages=landing_pages)

        class Spy:
            vlp, clr, pset, DispatchError = real.vlp, real.clr, real.pset, real.DispatchError
            swarm, dispatch = real.swarm, staticmethod(real.dispatch)
            executor_from_config = staticmethod(executor)

        with mock.patch.object(launch_bridge.substrate, "dispatch", return_value=Spy), \
                mock.patch.object(adapters, "build_dispatch_config", build):
            report = run_dispatch(doc, self.out, adapters_config=None, adapter_inputs=adapter_inputs)
        return report, built["config"]

    def assemble(self, doc, pieces):
        normalized = intake.validate(doc)
        return package.assemble(self.out / "package", normalized, route.compile_route(normalized), pieces,
                                source_root=self.out, checkout_readback=TEST_ONLY_CHECKOUT_READBACK)

    def pieces(self, report):
        return {r: json.loads((self.out / "pieces" / f"{r}.json").read_text()) for r in report["pages"]}

    def test_the_selection_page_lists_its_order_page_designs_and_assemble_accepts_it(self):
        doc = payload("elevation", brand_file=str(self.brand))
        report, config = self.dispatch(doc)
        self.assertEqual(report["pages"], ELEVATION_PAGES)
        pieces = self.pieces(report)
        selection = pieces["product_selection"]
        images = self.out / "dispatch" / "order-page-images"
        listed = {Path(a["path"]).relative_to(images).as_posix() for a in selection["artifacts"]}
        want = {"visual-mockup/stage-executor-record.json"}
        for n in range(1, SECTIONS + 1):
            want |= {f"desktop-wireframe/section-{n}.png", f"mobile-tablet/section-{n}.png",
                     f"visual-mockup/desktop/part-{n}.png", f"visual-mockup/mobile/part-{n}.png"}
        self.assertEqual(listed, want)
        # WP-08b: Skill 78's emitter defaults to "authored"; "locally_verified" needs a review record, and this
        # dispatch step has none (no independent review exists yet), so the honest status is "authored".
        self.assertEqual(selection["status"], "authored")
        self.assertEqual(selection["blockers"], [])
        built = self.assemble(doc, pieces)
        piece = next(p for p in built["manifest"]["pieces"] if p["role"] == "product_selection")
        self.assertEqual(len(piece["artifacts"]), 4 * SECTIONS + 1)
        argv = json.loads((self.out / "dispatch" / "image-stage-argv.json").read_text())
        self.assertNotIn("--allow-paid", argv)  # a practice run is free

    def test_without_the_attached_designs_assemble_refuses_the_page(self):
        """The control: the result Skill 78's emitter writes on its own carries no artifacts and is refused."""
        doc = payload("elevation", brand_file=str(self.brand))
        report, _ = self.dispatch(doc)
        pieces = self.pieces(report)
        pieces["product_selection"]["artifacts"] = []
        with self.assertRaises(package.PackageError) as ctx:
            self.assemble(doc, pieces)
        self.assertIn("at least one artifact is required", str(ctx.exception))

    def test_a_paid_dry_run_hands_the_order_page_allow_paid_and_completes_every_lane(self):
        doc = payload("elevation", brand_file=str(self.brand))
        report, config = self.dispatch(doc, paid=True)
        self.assertEqual(report["pages"], ELEVATION_PAGES)  # every lane finished
        self.assertIn("--allow-paid", step(config, "product_selection", "run_image_stages.py"))
        argv = json.loads((self.out / "dispatch" / "image-stage-argv.json").read_text())
        self.assertIn("--allow-paid", argv)  # the order page's image stage really received it
        self.assertTrue(self.assemble(doc, self.pieces(report))["manifest"])


class AttachDesignArtifactsTests(unittest.TestCase):
    def result(self, root: Path) -> Path:
        path = root / "result.json"
        path.write_text(json.dumps({"status": "locally_verified", "blockers": [], "artifacts": []}), encoding="utf-8")
        return path

    def test_a_run_that_drew_nothing_is_refused_not_passed_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "images").mkdir()
            with self.assertRaises(adapters.AdapterError):
                adapters.attach_design_artifacts(self.result(root), root / "images")
            proc = subprocess.run([sys.executable, str(Path(adapters.__file__)), "attach-design-artifacts",
                                   "--result", str(self.result(root)), "--run-dir", str(root / "images")],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 3)
            self.assertIn("FAIL-CLOSED", proc.stderr)

    def test_the_status_follows_the_image_stage(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images = root / "images"
            (images / "desktop-wireframe").mkdir(parents=True)
            (images / "desktop-wireframe" / "section-1.png").write_bytes(b"png")  # the other three stages left nothing
            result = adapters.attach_design_artifacts(self.result(root), images)
            self.assertEqual(len(result["artifacts"]), 1)
            self.assertEqual(result["status"], "blocked")
            self.assertTrue(any("mobile_wireframe_sections" in b for b in result["blockers"]), result["blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

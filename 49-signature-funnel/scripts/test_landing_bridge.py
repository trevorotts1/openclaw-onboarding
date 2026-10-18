#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fixture tests for the S49-08 landing bridge wrapper.

Fixture launch: the packet fixture launch (TEST-TENANT / TEST-LOCATION
/ TEST-LAUNCH, packet/reference/launch-example.json and
route-graph-example.json), made approvable the way S49's own dispatch
self-test makes a plan approvable: status approved, a real compiled
route_graph_hash, brand_hash = SHA-256 of a staged brand file, and a
launch_plan_build approval recorded NOW and bound to the plan document
hash. The REAL dispatch_launch.dispatch first runs the whole plan
through its fail-closed gates (record validation, plan-approval gate,
route re-compilation and hash binding) and emits the plan's requests;
the compiled graph for this journey carries landing + checkout +
thank_you nodes, and the test asserts exactly that set, then executes
ONLY the landing request through the bridge, using the adapter
command template from the config fragment with the same
{request}/{result}/{work_dir} substitution
dispatch_launch.executor_from_config performs (that executor itself
is covered by dispatch_launch.py's own self-test). The bridge's
result is then validated by the REAL
collect_launch_receipts.validate_result, the same function the
executor applies before accepting a consumer result.

The consumer is the FAKE Skill 71 tree (tests/make_fake_skill71.py):
the real launch_context.py, write_intake.py, page_result.py and
write_page_result.py copied verbatim from main, with stage_gate.py
stubbed (the 14-stage production gate is an agent-driven process; see
BUILD-REPORT.md for exactly where real execution stops).

What is proven:
  1. End to end through real dispatch: request written by dispatch,
     bridge stages the run (page-request.json byte-identical to the
     dispatch request), the real Skill 71 import validates and maps
     the context into intake.json, the real emitter writes
     page-result.json in the run, the bridge validates it with S49's
     receipt rules and places it at the dispatch {result} path, and
     dispatch accepts it into the manifest.
  2. The emitted result validates against the page-result 1.0 schema
     AND passes collect_launch_receipts.validate_result AND rolls up
     in collect_launch_receipts.collect.
  3. Fail-closed: a bridge config missing page_version, brand_owner,
     or image_cap (each) aborts with the value named, exit 2, and no
     consumer process runs (no intake.json, no staged request).
  4. Fail-closed: a configured brand file whose bytes do not hash to
     the request's brand_hash aborts before anything is staged.
  5. Schema fallback: with S49's receipts module not importable, the
     bridge still validates the emitted result against the vendored
     page-result schema (S49_SCRIPTS_DIR pointed at an empty dir).
  6. Skill 71's own shipped test for the real validation half
     (tests/test_launch_profile.py from main) passes against the
     fetched real tree, with no network use.
  7. Exit contract: a no-args (usage-error) invocation exits 3 and
     stages nothing, distinct from the exit-2 fail-closed refusals
     above. The bridge's ArgumentParser subclass replaces argparse's
     stock usage exit code (2), which made the two indistinguishable.
  8. brand_ref traversal (independent review D1, blocking): a
     brand_ref that is absolute or contains ".." is refused by name
     at exit 2 with nothing staged anywhere, in the three shapes the
     review probed; and _stage_file itself refuses any target that
     resolves outside the run directory (defence in depth).
  9. Receipts fallback (independent review D2): with the receipts
     module unimportable, the fallback is ANNOUNCED (stderr warning
     plus "receipt_validation": "vendored_schema_fallback" in the
     bridge summary, never silent), and the fallback enforces the
     independent-review cross-check (independent_review=true requires
     a named reviewer_session different from author_session) exactly
     as collect_launch_receipts.validate_result does.
 10. Dual-accept (PP-Y2 adoption map section 1.1): a 1.1 request
     carrying its prompt_policy_id citation passes the bridge end to
     end and the citation lands in the run's intake launch block;
     a 1.1 request without the citation, a 1.0 request carrying it,
     an unknown schema_version, and a launch record that disagrees
     with the request on the citation each refuse by name at exit 2
     before anything is staged.

Run: python3 tests/test_landing_bridge.py [-v]
"""

import contextlib
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BRIDGE_DIR = HERE
BRIDGE = BRIDGE_DIR / "landing_bridge.py"
REPO_ROOT = HERE.parents[1]  # scripts -> 49-signature-funnel -> repo root
FIXTURES = HERE / "fixtures"
S49_SCRIPTS = HERE
SKILL71_MAIN = REPO_ROOT / "71-blackceo-signature-page"
PY = sys.executable

sys.path.insert(0, str(S49_SCRIPTS))
import compile_launch_route as clr  # noqa: E402
import validate_launch_plan as vlp  # noqa: E402
import dispatch_launch as dispatch_mod  # noqa: E402
import collect_launch_receipts as receipts_mod  # noqa: E402

try:
    import jsonschema as _jsonschema
except ImportError:  # the schema assertions degrade to S49's own rules
    _jsonschema = None


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def dump(doc) -> bytes:
    return (json.dumps(doc, indent=2) + "\n").encode("utf-8")


BRAND_DOC = {
    "brand_id": "test-only-brand",
    "brand_name": "TEST ONLY Brand",
    "colors": {"primary": "#123456", "accent": "#C9A227"},
    "test_only": True,
}
BRAND_RAW = dump(BRAND_DOC)
BRAND_SHA = sha256(BRAND_RAW)


def fixture_launch() -> (dict, dict):
    """The packet fixture launch, made approvable for dispatch."""
    launch = json.loads((FIXTURES / "launch-example.json")
                        .read_text(encoding="utf-8"))
    launch["journey_mode"] = "single_simple"
    launch["offers"] = [o for o in launch["offers"]
                        if o["offer_id"] in ("MAIN-A", "BUMP")]
    launch["extras"] = {"upsell_1": False, "downsell_1": False,
                        "upsell_2": False}
    launch["brand_ref"] = "brand.json"
    launch["brand_hash"] = BRAND_SHA
    graph = clr.compile_route(launch)
    launch["route_graph_ref"] = "route-graph.json"
    launch["route_graph_hash"] = clr.graph_hash(graph)
    launch["status"] = "approved"
    launch["plan_approval_ref"] = "APPR-FIXTURE-1"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    approval = {
        "schema_version": "1.0", "approval_id": "APPR-FIXTURE-1",
        "subject_type": "launch_plan_build",
        "subject_hash": vlp.plan_document_hash(launch),
        "owner_identity_ref": "client-fixture",
        "source_message_ref": "fixture-msg-1", "recorded_at": now,
        "scope": ["launch_plan_build"], "revoked": False,
        "verification_class":
            "recorded_consent_not_cryptographically_sealed",
    }
    return launch, approval


class LandingBridgeCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s49-landing-bridge-"))
        self.addCleanup(lambda: shutil.rmtree(self.td,
                                              ignore_errors=True))
        # Fake Skill 71 tree (real consumer files, stubbed gate).
        self.fake = self.td / "skill71"
        proc = subprocess.run(
            [PY, str(HERE / "make_fake_skill71.py"), str(self.fake)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        # Fixture inputs.
        self.launch, self.approval = fixture_launch()
        self.launch_path = self.td / "launch.json"
        self.launch_path.write_bytes(dump(self.launch))
        self.brand_path = self.td / "brand-src.json"
        self.brand_path.write_bytes(BRAND_RAW)
        self.run_dir = self.td / "run"
        self.bridge_config_path = self.td / "bridge-config.json"

    def write_bridge_config(self, drop: str = None,
                            **overrides) -> dict:
        landing = {
            "run_dir": str(self.run_dir),
            "page_version": "standard",
            "brand_owner": "Fixture Brand Owner",
            "image_cap": 12,
            "launch_record": str(self.launch_path),
            "brand_file": str(self.brand_path),
        }
        landing.update(overrides)
        if drop:
            landing.pop(drop, None)
        cfg = {"skill71": {"root": str(self.fake), "python": PY},
               "landing": landing}
        self.bridge_config_path.write_text(
            json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        return cfg

    def adapter_command(self) -> list:
        """The landing adapter command template, in the exact shape of
        the launch-adapters fragment (and of executor_from_config's
        config)."""
        return [PY, str(BRIDGE),
                "--request", "{request}",
                "--result", "{result}",
                "--work-dir", "{work_dir}",
                "--bridge-config", str(self.bridge_config_path)]

    def emit_dispatch(self) -> (dict, Path):
        """S49's REAL dispatch over the fixture plan, emission only:
        the full fail-closed gate chain runs (record validation,
        plan-approval gate, route re-compilation + hash binding) and
        the requests + compiled route graph land in the out dir."""
        out = self.td / "dispatch"
        manifest = dispatch_mod.dispatch(
            self.launch, self.approval,
            client_identity_ref="client-fixture",
            worker_identity_ref="worker-fixture",
            copy_profile="standard", allowed_write_target="local_only",
            out_dir=out)
        return manifest, out

    def run_landing_adapter(self, out: Path,
                            env_extra: dict = None) -> dict:
        """Execute the landing request exactly the way
        executor_from_config.run does: substitute the three tokens in
        the configured command, run it, require exit 0 and a result
        file, then apply collect_launch_receipts.validate_result (the
        same acceptance the executor applies)."""
        import os
        req_path = out / "request-landing.json"
        res_path = out / "result-landing.json"
        cmd = [part.replace("{request}", str(req_path))
                    .replace("{result}", str(res_path))
                    .replace("{work_dir}", str(out))
               for part in self.adapter_command()]
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              env=env, timeout=600)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(res_path.is_file())
        result = json.loads(res_path.read_text(encoding="utf-8"))
        request = json.loads(req_path.read_text(encoding="utf-8"))
        fails = receipts_mod.validate_result(result, request)
        self.assertEqual(fails, [])
        return result

    def run_bridge_directly(self, request_path: Path, run_dir: Path,
                            env_extra: dict = None,
                            bridge_path: Path = None):
        result_path = self.td / "direct-result.json"
        env = dict(os.environ)
        if env_extra:
            env.update(env_extra)
        proc = subprocess.run(
            [PY, str(bridge_path or BRIDGE), "--request",
             str(request_path),
             "--result", str(result_path), "--work-dir", str(self.td),
             "--bridge-config", str(self.bridge_config_path)],
            capture_output=True, text=True, env=env)
        return proc, result_path

    def make_request(self) -> Path:
        # The landing request from S49's real request builder, run
        # against the fixture launch's compiled graph (the plan's
        # other roles are irrelevant to these direct bridge calls).
        graph = clr.compile_route(self.launch)
        reqs = dispatch_mod.build_requests(
            self.launch, graph, copy_profile="standard",
            allowed_write_target="local_only")
        landing = [r for r in reqs if r["page_role"] == "landing"]
        self.assertEqual(len(landing), 1)
        req_path = self.td / "request-landing.json"
        req_path.write_bytes(dump(landing[0]))
        graph_path = self.td / "route-graph.json"
        graph_path.write_bytes(clr.serialize_graph(graph))
        return req_path


class TestEndToEnd(LandingBridgeCase):
    def test_dispatch_runs_bridge_into_real_skill71_consumer(self):
        self.write_bridge_config()
        manifest, out = self.emit_dispatch()
        self.assertEqual(manifest["execution"], "emitted_not_executed")
        roles = sorted(r["page_role"] for r in manifest["requests"])
        self.assertEqual(roles, ["checkout", "landing", "thank_you"])
        result = self.run_landing_adapter(out)

        # The run was staged byte-identically.
        staged_request = (self.run_dir / "page-request.json").read_bytes()
        dispatch_request = (out / "request-landing.json").read_bytes()
        self.assertEqual(staged_request, dispatch_request)
        self.assertEqual((self.run_dir / "launch.json").read_bytes(),
                         self.launch_path.read_bytes())
        graph_raw = (self.run_dir / "route-graph.json").read_bytes()
        self.assertEqual(sha256(graph_raw),
                         self.launch["route_graph_hash"])
        self.assertEqual((self.run_dir / "brand.json").read_bytes(),
                         BRAND_RAW)

        # The real Skill 71 import consumed the staged context.
        intake = json.loads((self.run_dir / "intake.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(intake["launch_profile"],
                         "signature_launch_landing")
        self.assertEqual(intake["page_version"], "standard")
        self.assertEqual(intake["brand_owner"], "Fixture Brand Owner")
        self.assertEqual(intake["image_cap"], 12)
        self.assertEqual(intake["image_engine"], "agnes")
        self.assertIs(intake["test_run"], True)
        block = intake["launch"]
        self.assertEqual(block["brand_hash_check"], "matched")
        landing_req = next(r for r in manifest["requests"]
                           if r["page_role"] == "landing")
        self.assertEqual(block["next_page_id"],
                         next(r for r in manifest["requests"]
                              if r["page_role"] ==
                              block["next_role"])["page_id"])
        self.assertEqual(block["route_graph_placed"], True)
        self.assertEqual(block["page_id"], landing_req["page_id"])
        popup = json.loads((self.run_dir / "launch" / "popup-config.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(popup["component"], "interest-popup")

        # The real emitter produced the result in the run; the bridge
        # placed those exact bytes at the dispatch result path.
        emitted = (self.run_dir / "page-result.json").read_bytes()
        placed = (out / "result-landing.json").read_bytes()
        self.assertEqual(placed, emitted)
        placed_result = json.loads(placed)
        self.assertEqual(placed_result, result)
        self.assertEqual(result["status"], "authored")
        self.assertEqual(result["proof_class"], "L0")
        self.assertTrue(any("not closed" in b
                            for b in result["blockers"]))
        handoff = json.loads((self.run_dir / "page-handoff.json")
                             .read_text(encoding="utf-8"))
        self.assertEqual(handoff["routing"]["authorized"], False)

    def test_result_validates_by_schema_receipts_and_rollup(self):
        self.write_bridge_config()
        manifest, out = self.emit_dispatch()
        result = self.run_landing_adapter(out)
        request = json.loads((out / "request-landing.json")
                             .read_text(encoding="utf-8"))
        if _jsonschema is not None:
            schema = json.loads(
                (BRIDGE_DIR / "vendor" / "page-result.schema.json")
                .read_text(encoding="utf-8"))
            _jsonschema.validate(result, schema)  # raises on violation
        fails = receipts_mod.validate_result(result, request)
        self.assertEqual(fails, [])
        checkpoint = receipts_mod.collect(manifest, [result],
                                          {request["request_id"]:
                                           request})
        self.assertEqual(checkpoint["roles_reported"], ["landing"])
        self.assertEqual(checkpoint["missing_roles"],
                         ["checkout", "thank_you"])
        self.assertEqual(checkpoint["problems"], [])
        self.assertEqual(checkpoint["aggregate_status"], "in_progress")


class TestFailClosed(LandingBridgeCase):
    def assert_refused_before_staging(self, drop, needle):
        self.write_bridge_config(drop=drop)
        req_path = self.make_request()
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)
        self.assertFalse(result_path.exists())
        self.assertFalse((self.run_dir / "intake.json").exists())
        self.assertFalse((self.run_dir / "page-request.json").exists())

    def test_missing_page_version_fails_closed(self):
        self.assert_refused_before_staging("page_version", "page_version")

    def test_missing_brand_owner_fails_closed(self):
        self.assert_refused_before_staging("brand_owner", "brand_owner")

    def test_missing_image_cap_fails_closed(self):
        self.assert_refused_before_staging("image_cap", "image_cap")

    def test_brand_bytes_mismatch_fails_closed(self):
        bad_brand = self.td / "brand-bad.json"
        bad_brand.write_bytes(dump({"brand_id": "someone-else"}))
        self.write_bridge_config(brand_file=str(bad_brand))
        req_path = self.make_request()
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("brand_hash", proc.stdout)
        self.assertFalse(result_path.exists())
        self.assertFalse(self.run_dir.exists())

    def test_stale_route_graph_fails_closed(self):
        self.write_bridge_config()
        req_path = self.make_request()
        (self.td / "route-graph.json").write_bytes(
            dump({"schema_version": "1.0", "nodes": [], "edges": []}))
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("route_graph_hash", proc.stdout)
        self.assertFalse(result_path.exists())


class TestPromptPolicyDualAccept(LandingBridgeCase):
    """PP-Y2 adoption map section 1.1: the bridge dual-accepts the 1.0
    shape and the 1.1 citation shape under the pair rule, and refuses
    every pair violation for its actual defect before staging. The
    1.1 request below is the shape dispatch_launch.build_requests
    emits once a role flips ready with a policy on the record: the
    real builder runs on the citation-carrying fixture record and
    the emitted landing request is then stamped exactly as that
    builder stamps it (schema_version 1.1, the record's
    prompt_policy_id verbatim). The registry of record is staged
    beside the fake Skill 71 tree in the repo's own layout, because
    the real launch_context verifies the citation against it."""

    POLICY = "kie-rule-12-band"

    def stage_registry_beside_fake(self):
        dest = (self.td / "shared-utils" / "signature_launch"
                / "domain")
        dest.mkdir(parents=True)
        shutil.copyfile(
            REPO_ROOT / "shared-utils" / "signature_launch" / "domain"
            / "prompt-policy-registry.json",
            dest / "prompt-policy-registry.json")

    def citation_record(self):
        self.launch["schema_version"] = "1.1"
        self.launch["prompt_policy_id"] = self.POLICY
        self.launch_path.write_bytes(dump(self.launch))

    def request_11(self) -> Path:
        self.citation_record()
        req_path = self.make_request()
        doc = json.loads(req_path.read_text(encoding="utf-8"))
        doc["schema_version"] = "1.1"
        doc["prompt_policy_id"] = self.POLICY
        req_path.write_bytes(dump(doc))
        return req_path

    def mutate_request(self, req_path: Path, **changes) -> Path:
        doc = json.loads(req_path.read_text(encoding="utf-8"))
        doc.update(changes)
        req_path.write_bytes(dump(doc))
        return req_path

    def test_valid_11_request_passes_the_bridge(self):
        self.write_bridge_config()
        self.stage_registry_beside_fake()
        req_path = self.request_11()
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(result_path.exists())
        result = json.loads(result_path.read_text(encoding="utf-8"))
        request = json.loads(req_path.read_text(encoding="utf-8"))
        self.assertEqual(receipts_mod.validate_result(result, request),
                         [])
        intake = json.loads((self.run_dir / "intake.json")
                            .read_text(encoding="utf-8"))
        block = intake["launch"]
        self.assertEqual(block["schema_version"], "1.1")
        self.assertEqual(block["prompt_policy_id"], self.POLICY)
        staged = json.loads((self.run_dir / "page-request.json")
                            .read_text(encoding="utf-8"))
        self.assertEqual(staged["schema_version"], "1.1")
        self.assertEqual(staged["prompt_policy_id"], self.POLICY)

    def assert_refused_before_staging(self, proc, result_path, needle):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn(needle, proc.stdout)
        self.assertFalse(result_path.exists())
        self.assertFalse(self.run_dir.exists())

    def test_11_without_citation_is_refused_by_name(self):
        self.write_bridge_config()
        req_path = self.mutate_request(self.make_request(),
                                       schema_version="1.1")
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assert_refused_before_staging(proc, result_path,
                                           "prompt_policy_id")

    def test_10_with_citation_is_refused_by_name(self):
        self.write_bridge_config()
        req_path = self.mutate_request(self.make_request(),
                                       prompt_policy_id=self.POLICY)
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assert_refused_before_staging(proc, result_path,
                                           "prompt_policy_id")

    def test_unknown_schema_version_is_refused_by_name(self):
        self.write_bridge_config()
        req_path = self.mutate_request(self.make_request(),
                                       schema_version="2.0")
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assert_refused_before_staging(proc, result_path,
                                           "schema_version")

    def test_record_citation_mismatch_is_refused_by_name(self):
        self.write_bridge_config()
        req_path = self.request_11()
        record = json.loads(self.launch_path.read_text(encoding="utf-8"))
        record.pop("prompt_policy_id")
        self.launch_path.write_bytes(dump(record))
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assert_refused_before_staging(proc, result_path,
                                           "prompt_policy_id")


class TestSchemaFallback(LandingBridgeCase):
    def test_bridge_validates_via_vendored_schema_without_receipts(self):
        self.write_bridge_config()
        empty = self.td / "empty-scripts"
        empty.mkdir()
        _manifest, out = self.emit_dispatch()
        result = self.run_landing_adapter(
            out, env_extra={"S49_SCRIPTS_DIR": str(empty)})
        self.assertEqual(result["status"], "authored")


def load_bridge_module(bridge_path=None):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "landing_bridge_under_test", bridge_path or BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestBrandRefTraversal(LandingBridgeCase):
    """Independent review D1 (BLOCKING): brand_ref gets the same
    run-relative guard route_graph_ref has. The three shapes below
    are the review's three probes: before the cure each exited 0 and
    staged the brand bytes outside the run directory. The fixture
    launch is mutated only in brand_ref, with the launch record file
    and the request built from it, so every cross-check (brand_hash,
    record/request agreement) still passes and the guard is the only
    thing that can refuse."""

    def make_request_with_brand_ref(self, brand_ref: str) -> Path:
        self.launch["brand_ref"] = brand_ref
        self.launch_path.write_bytes(dump(self.launch))
        self.write_bridge_config()
        return self.make_request()

    def assert_brand_ref_refused(self, brand_ref, escape_target):
        req_path = self.make_request_with_brand_ref(brand_ref)
        proc, result_path = self.run_bridge_directly(req_path,
                                                     self.run_dir)
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        self.assertIn("brand_ref", proc.stdout)
        self.assertFalse(result_path.exists())
        self.assertFalse(Path(escape_target).exists())
        self.assertFalse(self.run_dir.exists())

    def test_brand_ref_parent_escape_refused(self):
        self.assert_brand_ref_refused("../escape.json",
                                      self.td / "escape.json")

    def test_brand_ref_absolute_refused(self):
        target = self.td / "escape-abs.json"
        self.assert_brand_ref_refused(str(target), target)

    def test_brand_ref_nested_escape_refused(self):
        self.assert_brand_ref_refused("sub/../../escape2.json",
                                      self.td / "escape2.json")


class TestStageFileContainment(unittest.TestCase):
    """Defence in depth behind the check_request guard (review D1):
    _stage_file itself refuses any target that resolves outside the
    resolved run directory, and still stages ordinary refs."""

    def setUp(self):
        self.mod = load_bridge_module()
        self.td = Path(tempfile.mkdtemp(prefix="s49-stage-file-"))
        self.addCleanup(lambda: shutil.rmtree(self.td,
                                              ignore_errors=True))
        self.run_dir = self.td / "run"
        self.run_dir.mkdir()

    def test_stage_file_refuses_parent_escape(self):
        with self.assertRaises(self.mod.BridgeError) as cm:
            self.mod._stage_file(self.run_dir, "../escape.json", b"x",
                                 "brand file")
        self.assertIn("brand file", str(cm.exception))
        self.assertFalse((self.td / "escape.json").exists())

    def test_stage_file_refuses_absolute_path(self):
        target = self.td / "escape-abs.json"
        with self.assertRaises(self.mod.BridgeError):
            self.mod._stage_file(self.run_dir, str(target), b"x",
                                 "brand file")
        self.assertFalse(target.exists())

    def test_stage_file_stages_inside_run_dir(self):
        self.mod._stage_file(self.run_dir, "sub/brand.json", b"{}",
                             "brand file")
        self.assertEqual(
            (self.run_dir / "sub" / "brand.json").read_bytes(), b"{}")


class TestReceiptsFallbackRules(LandingBridgeCase):
    """Independent review D2: the vendored-schema fallback is
    announced (never silent) and enforces the independent-review
    cross-check that collect_launch_receipts.validate_result carries
    and the fallback used to drop."""

    def empty_scripts_dir(self) -> Path:
        empty = self.td / "empty-scripts-fallback"
        empty.mkdir(exist_ok=True)
        return empty

    def isolated_bridge(self) -> Path:
        # Harness anchor (assembly cure, coordinator-authorized
        # under S49-DEC-S4908-01): the two tests in this class force
        # the vendored-schema fallback by making
        # collect_launch_receipts.py undiscoverable. In the staging
        # topology (the bridge outside any 49-signature-funnel/
        # scripts ancestor) pointing S49_SCRIPTS_DIR at an empty
        # directory did exactly that. In the shipped layout the
        # bridge sits inside 49-signature-funnel/scripts/, so its
        # ancestor walk always finds the real receipts module beside
        # it and the fallback can never be forced in place. The
        # fallback exists for out-of-tree execution, so these tests
        # run a copy of the bridge placed in an isolated directory
        # with no 49-signature-funnel/scripts ancestor, with the
        # shipped vendor schemas beside it exactly as the staging
        # layout had them. The copy is taken from the shipped
        # in-repo file at runtime, so it is byte-identical by
        # construction; every assertion in the two tests is
        # unchanged.
        iso = self.td / "isolated-bridge"
        (iso / "vendor").mkdir(parents=True, exist_ok=True)
        target = iso / "landing_bridge.py"
        shutil.copyfile(BRIDGE, target)
        for name in ("page-result.schema.json",
                     "page-request.schema.json"):
            shutil.copyfile(BRIDGE_DIR / "vendor" / name,
                            iso / "vendor" / name)
        return target

    def test_fallback_announced_in_summary_and_stderr(self):
        self.write_bridge_config()
        req_path = self.make_request()
        proc, result_path = self.run_bridge_directly(
            req_path, self.run_dir,
            env_extra={"S49_SCRIPTS_DIR": str(self.empty_scripts_dir())},
            bridge_path=self.isolated_bridge())
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(result_path.exists())
        # The downgrade is announced on stderr...
        self.assertIn("WARNING", proc.stderr)
        self.assertIn("schema fallback", proc.stderr)
        # ...and named in the bridge summary itself.
        summary = json.loads(proc.stdout)
        self.assertEqual(summary["receipt_validation"],
                         "vendored_schema_fallback")

    def test_fallback_enforces_independent_review_rule(self):
        self.write_bridge_config()
        _manifest, out = self.emit_dispatch()
        result = self.run_landing_adapter(out)
        request = json.loads((out / "request-landing.json")
                             .read_text(encoding="utf-8"))
        self.assertTrue(result["author_session"])
        mod = load_bridge_module(self.isolated_bridge())
        env = {"S49_SCRIPTS_DIR": str(self.empty_scripts_dir())}
        # reviewer == author under a claimed independent review.
        bad = dict(result)
        bad["independent_review"] = True
        bad["reviewer_session"] = bad["author_session"]
        bad_path = self.td / "bad-result.json"
        bad_path.write_bytes(dump(bad))
        # no reviewer at all under a claimed independent review.
        bad2 = dict(result)
        bad2["independent_review"] = True
        bad2["reviewer_session"] = None
        bad2_path = self.td / "bad2-result.json"
        bad2_path.write_bytes(dump(bad2))
        with mock.patch.dict(os.environ, env):
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                with self.assertRaises(mod.BridgeError) as cm:
                    mod.validate_emitted_result(bad_path, request)
            self.assertIn("independent_review", str(cm.exception))
            self.assertIn("reviewer == author", str(cm.exception))
            self.assertIn("WARNING", err.getvalue())
            with self.assertRaises(mod.BridgeError) as cm2:
                mod.validate_emitted_result(bad2_path, request)
            self.assertIn("no reviewer session", str(cm2.exception))
            # The unmutated, genuinely emitted result still validates
            # under the fallback, and reports the fallback mode.
            good_path = self.td / "good-result.json"
            good_path.write_bytes(dump(result))
            err2 = io.StringIO()
            with contextlib.redirect_stderr(err2):
                parsed, mode = mod.validate_emitted_result(good_path,
                                                           request)
            self.assertEqual(mode, "vendored_schema_fallback")
            self.assertEqual(parsed["request_id"],
                             request["request_id"])
            self.assertIn("WARNING", err2.getvalue())


class TestExitContract(unittest.TestCase):
    """The documented exit contract, pinned at the CLI: 0 = result
    placed, 2 = fail-closed refusal, 3 = usage error. The refusal half
    is pinned by TestFailClosed (every case asserts exit 2); this case
    pins the usage half. Before the cure, a no-args invocation exited
    2 (argparse's stock usage code), so a caller distinguishing the
    codes would have misread a usage error as a refusal."""

    def test_no_args_exits_3_and_stages_nothing(self):
        td = Path(tempfile.mkdtemp(prefix="s49-landing-bridge-usage-"))
        self.addCleanup(lambda: shutil.rmtree(td, ignore_errors=True))
        proc = subprocess.run([PY, str(BRIDGE)], cwd=str(td),
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 3, proc.stdout + proc.stderr)
        self.assertIn("the following arguments are required",
                      proc.stderr)
        self.assertEqual(list(td.iterdir()), [])


class TestRealEntrypointValidation(unittest.TestCase):
    def test_skill71_shipped_launch_profile_tests_pass(self):
        if not (SKILL71_MAIN / "scripts" / "stage_gate.py").is_file():
            self.skipTest("fetched stage_gate.py is absent; the real "
                          "entrypoint test needs the full scripts tree")
        proc = subprocess.run(
            [PY, "-m", "unittest", "test_launch_profile", "-v"],
            cwd=str(SKILL71_MAIN / "tests"),
            capture_output=True, text=True, timeout=900)
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-6:])
        self.assertEqual(proc.returncode, 0, tail)
        self.assertIn("OK", proc.stderr + proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)

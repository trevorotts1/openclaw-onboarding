#!/usr/bin/env python3
"""S71-02: the signature_launch_landing launch profile and the
write_intake.py launch-context import.

Covers: a valid page-request 1.0 importing and mapping field by field;
every schema-violation class refusing by name with nothing written; the
profile-on versus profile-off deltas (popup config emission, design
assets record, the stage gate's no-offer-pricing engagement); consent
statements carried verbatim; and a legacy run's intake staying
byte-identical to the baseline writer's output.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
PY = sys.executable

sys.path.insert(0, str(SCRIPTS))
import launch_context  # noqa: E402
import stage_gate  # noqa: E402

IDENT = {"tenant_id": "tenant-acme", "location_id": "loc-123",
         "launch_id": "launch-2026-bf", "revision": 3}

LEGACY_GOLDEN = (
    '{\n'
    '  "page_version": "standard",\n'
    '  "brand_owner": "BlackCEO",\n'
    '  "brand_file": "assets/brand/blackceo-brand.json",\n'
    '  "creative_direction": null,\n'
    '  "image_cap": 40,\n'
    '  "image_engine": "kie",\n'
    '  "test_run": false,\n'
    '  "copy_version": "standard"\n'
    '}\n'
)


def graph_doc(journey_edge_to="page-select-1"):
    return {
        "schema_version": "1.0", **IDENT,
        "nodes": [
            {"page_id": "page-landing-1", "role": "landing"},
            {"page_id": "page-select-1", "role": "product_selection"},
            {"page_id": "page-thanks-1", "role": "thank_you"},
        ],
        "edges": [
            {"from": "page-landing-1", "event": "interest_submitted",
             "to": journey_edge_to, "guard": "verified_native_contact_submit"},
            {"from": "page-select-1", "event": "selection_validated",
             "to": "page-thanks-1", "guard": "selection_complete"},
        ],
        "pending_failed_payment_behavior":
            "retain_current_purchase_state_until_resolved_or_explicit_decline",
        "test_only": True,
    }


def dump(doc):
    return (json.dumps(doc, indent=2) + "\n").encode("utf-8")


def request_doc(graph_hash, **overrides):
    doc = {
        "schema_version": "1.0", **IDENT,
        "request_id": "req-001", "page_id": "page-landing-1",
        "page_role": "landing", "assigned_skill": 71,
        "approval_ref": "approval://plan-9", "input_hash": "in-hash-1",
        "brand_ref": "brand:acme", "brand_hash": "brand-hash-1",
        "route_graph_ref": "route-graph.json", "route_graph_hash": graph_hash,
        "offer_refs": ["offer-main"], "copy_profile": "standard",
        "allowed_write_target": "local_only", "test_only": True,
    }
    doc.update(overrides)
    return doc


def launch_doc(graph_hash, **overrides):
    offer = {
        "offer_id": "offer-main", "slot": "main", "display_name": "Main Offer",
        "deliverables": ["the thing"], "exclusions": [], "entitlement_ids": [],
        "requires": [], "excludes": [], "native_product_id": None,
        "prices": [{"price_choice_id": "pc-1", "currency": "USD",
                    "amount_minor": 4900, "billing_type": "one_time",
                    "native_price_id": None, "schedule": [],
                    "approval_status": "approved"}],
        "source_kind": "owner", "source_ref": "owner-brief", "test_only": True,
    }
    doc = {
        "schema_version": "1.0", **IDENT,
        "journey_mode": "multiple_options", "status": "approved",
        "brand_ref": "brand:acme", "brand_hash": "brand-hash-1",
        "route_graph_ref": "route-graph.json", "route_graph_hash": graph_hash,
        "plan_approval_ref": "approval://plan-9", "offers": [offer],
        "extras": {"upsell_1": False, "downsell_1": False, "upsell_2": False},
        "bump_enabled": False, "image_provider": "agnes",
        "source_refs": ["owner-brief"], "test_only": True,
    }
    doc.update(overrides)
    return doc


CONSENT = [
    {"id": "email", "text": "Email statement text, verbatim.", "required": True},
    {"id": "sms", "text": "SMS statement text, verbatim.", "required": True},
]


class LaunchImportCase(unittest.TestCase):
    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-02-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))
        self.graph_bytes = dump(graph_doc())
        self.ghash = hashlib.sha256(self.graph_bytes).hexdigest()
        self.graph_path = self.write("graph.json", self.graph_bytes)
        self.request_path = self.write("request.json", dump(request_doc(self.ghash)))
        self.launch_path = self.write("launch.json", dump(launch_doc(self.ghash)))
        self.consent_path = self.write("consent.json", dump(CONSENT))
        self.run_dir = self.td / "run"
        self.run_dir.mkdir()

    def write(self, name, raw):
        p = self.td / name
        p.write_bytes(raw if isinstance(raw, bytes) else raw.encode("utf-8"))
        return p

    def intake_cmd(self, *extra):
        return [PY, str(SCRIPTS / "write_intake.py"), str(self.run_dir),
                "--page-version", "standard", "--brand-owner", "Acme Owner",
                "--image-cap", "40", *extra]

    def run_intake(self, *extra):
        return subprocess.run(self.intake_cmd(*extra),
                              capture_output=True, text=True)

    def full_import(self):
        return self.run_intake(
            "--launch-context", str(self.request_path),
            "--launch-record", str(self.launch_path),
            "--route-graph", str(self.graph_path),
            "--consent-statements", str(self.consent_path))

    def run_files(self):
        return sorted(str(p.relative_to(self.run_dir))
                      for p in self.run_dir.rglob("*") if p.is_file())

    def read_intake(self):
        return json.loads((self.run_dir / "intake.json").read_text(encoding="utf-8"))

    def tokens_component_present(self):
        # Production's own probe (launch_context.emit_design_tokens):
        # the S71-07 tokens component as a sibling of the skill root.
        # Whether the import emits launch/design-tokens.css and what it
        # records depends on this tree state, so the expectations below
        # name the state and assert its full behavior, either way.
        return launch_context.tokens_component_path(ROOT).is_file()

    def expected_files(self, absent_files):
        files = list(absent_files)
        if self.tokens_component_present():
            files.append("launch/design-tokens.css")
        return sorted(files)

    def assert_design_tokens_record(self, block):
        record = block["design_assets"]["design_tokens_css"]
        css_path = self.run_dir / "launch" / "design-tokens.css"
        if self.tokens_component_present():
            self.assertEqual(record["status"], "emitted")
            self.assertEqual(record["path"], "launch/design-tokens.css")
            self.assertIsInstance(record["missing_tokens"], list)
            css = css_path.read_text(encoding="utf-8")
            self.assertTrue(css.startswith(":root"), css[:80])
            self.assertIn("--sl-", css)
        else:
            self.assertEqual(record["status"], "component_not_in_tree")
            self.assertIsNone(record["path"])
            self.assertFalse(css_path.exists())


class TestValidImport(LaunchImportCase):
    def test_full_import_maps_field_by_field(self):
        proc = self.full_import()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        intake = self.read_intake()
        # Legacy keys intact.
        self.assertEqual(intake["page_version"], "standard")
        self.assertEqual(intake["brand_owner"], "Acme Owner")
        self.assertEqual(intake["image_cap"], 40)
        # Mapped from the launch context.
        self.assertEqual(intake["image_engine"], "agnes")       # launch image_provider
        self.assertEqual(intake["copy_version"], "standard")    # request copy_profile
        self.assertIs(intake["test_run"], True)                 # request test_only
        self.assertEqual(intake["launch_profile"], "signature_launch_landing")
        block = intake["launch"]
        for key, want in (
                ("request_id", "req-001"), ("input_hash", "in-hash-1"),
                ("tenant_id", "tenant-acme"), ("location_id", "loc-123"),
                ("launch_id", "launch-2026-bf"), ("revision", 3),
                ("page_id", "page-landing-1"), ("page_role", "landing"),
                ("assigned_skill", 71), ("approval_ref", "approval://plan-9"),
                ("brand_ref", "brand:acme"), ("brand_hash", "brand-hash-1"),
                ("brand_hash_check", "not_a_file_ref"),
                ("route_graph_ref", "route-graph.json"),
                ("route_graph_hash", self.ghash), ("route_graph_placed", True),
                ("copy_profile", "standard"), ("copy_profile_mapped", True),
                ("allowed_write_target", "local_only"), ("test_only", True),
                ("journey_mode", "multiple_options"),
                ("image_provider", "agnes"),
                ("plan_approval_ref", "approval://plan-9"),
                ("next_role", "product_selection"),
                ("next_page_id", "page-select-1"),
                ("page_request_ref", "page-request.json"),
                ("launch_record_ref", "launch.json"),
                ("popup_config_ref", "launch/popup-config.json"),
                ("consent_source", "launch_context_import")):
            self.assertEqual(block[key], want, key)
        self.assertEqual(block["offer_refs"], ["offer-main"])
        # Placed artifacts are the validated documents, verbatim.
        self.assertEqual((self.run_dir / "page-request.json").read_bytes(),
                         self.request_path.read_bytes())
        self.assertEqual((self.run_dir / "launch.json").read_bytes(),
                         self.launch_path.read_bytes())
        self.assertEqual((self.run_dir / "route-graph.json").read_bytes(),
                         self.graph_bytes)
        self.assertEqual(self.run_files(), self.expected_files(
            ["intake.json", "launch.json", "launch/popup-config.json",
             "page-request.json", "route-graph.json"]))
        self.assert_design_tokens_record(block)

    def test_popup_config_carries_consent_verbatim(self):
        proc = self.full_import()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        popup = json.loads((self.run_dir / "launch" / "popup-config.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(popup["component"], "interest-popup")
        self.assertEqual(popup["component_version"], "1.0.0")
        self.assertEqual(popup["fields"],
                         ["first_name", "last_name", "email", "phone"])
        self.assertEqual(popup["native_field_map"],
                         {f: f for f in popup["fields"]})
        self.assertEqual(popup["consent_statements"], CONSENT)
        self.assertEqual(popup["consent_source"], "launch_context_import")
        self.assertEqual(popup["events"], ["sl:interest-capture"])

    def test_request_only_import(self):
        proc = self.run_intake("--launch-context", str(self.request_path))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        intake = self.read_intake()
        block = intake["launch"]
        self.assertIsNone(block["launch_record_ref"])
        self.assertIsNone(block["journey_mode"])
        self.assertIsNone(block["image_provider"])
        self.assertIsNone(block["next_role"])
        self.assertIs(block["route_graph_placed"], False)
        self.assertIsNone(block["consent_source"])
        self.assertEqual(intake["image_engine"], "kie")  # CLI default stands
        popup = json.loads((self.run_dir / "launch" / "popup-config.json")
                           .read_text(encoding="utf-8"))
        self.assertEqual(popup["consent_statements"], [])
        self.assertIsNone(popup["consent_source"])
        self.assertEqual(self.run_files(), self.expected_files(
            ["intake.json", "launch/popup-config.json", "page-request.json"]))
        self.assert_design_tokens_record(block)

    def test_free_entry_next_role(self):
        graph = graph_doc(journey_edge_to="page-thanks-1")
        raw = dump(graph)
        gh = hashlib.sha256(raw).hexdigest()
        gp = self.write("graph-fe.json", raw)
        rp = self.write("request-fe.json", dump(request_doc(gh)))
        lp = self.write("launch-fe.json",
                        dump(launch_doc(gh, journey_mode="free_entry")))
        proc = self.run_intake("--launch-context", str(rp),
                               "--launch-record", str(lp),
                               "--route-graph", str(gp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        block = self.read_intake()["launch"]
        self.assertEqual(block["next_role"], "free_entry")
        self.assertEqual(block["next_page_id"], "page-thanks-1")

    def test_free_entry_refused_for_other_journeys(self):
        graph = graph_doc(journey_edge_to="page-thanks-1")
        raw = dump(graph)
        gh = hashlib.sha256(raw).hexdigest()
        gp = self.write("graph-fe2.json", raw)
        rp = self.write("request-fe2.json", dump(request_doc(gh)))
        lp = self.write("launch-fe2.json", dump(launch_doc(gh)))
        proc = self.run_intake("--launch-context", str(rp),
                               "--launch-record", str(lp),
                               "--route-graph", str(gp))
        self.assertEqual(proc.returncode, 2)
        self.assertIn("free_entry", proc.stdout)
        self.assertEqual(self.run_files(), [])

    def test_brand_hash_matched_and_refused(self):
        brand = ROOT / "assets" / "brand" / "blackceo-brand.json"
        good = hashlib.sha256(brand.read_bytes()).hexdigest()
        rp = self.write("request-brand.json", dump(request_doc(
            self.ghash, brand_ref="assets/brand/blackceo-brand.json",
            brand_hash=good)))
        proc = self.run_intake("--launch-context", str(rp))
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.read_intake()["launch"]["brand_hash_check"],
                         "matched")
        bad = self.write("request-brand-bad.json", dump(request_doc(
            self.ghash, brand_ref="assets/brand/blackceo-brand.json",
            brand_hash="0" * 64)))
        run2 = self.td / "run2"
        run2.mkdir()
        proc = subprocess.run(
            [PY, str(SCRIPTS / "write_intake.py"), str(run2),
             "--page-version", "standard", "--brand-owner", "Acme",
             "--image-cap", "1", "--launch-context", str(bad)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("brand_hash", proc.stdout)
        self.assertEqual(list(run2.rglob("*")), [])


class TestRefusals(LaunchImportCase):
    def assert_refused(self, proc, *needles):
        self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
        for needle in needles:
            self.assertIn(needle, proc.stdout)
        self.assertEqual(self.run_files(), [])

    def request_variant(self, name, **overrides):
        doc = request_doc(self.ghash)
        for key, value in overrides.items():
            if value is ...:
                doc.pop(key, None)
            else:
                doc[key] = value
        return self.write(name, dump(doc))

    def test_missing_required_field(self):
        rp = self.request_variant("r1.json", approval_ref=...)
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "missing required field 'approval_ref'")

    def test_additional_property(self):
        rp = self.request_variant("r2.json", surprise=1)
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "additional property 'surprise'")

    def test_bad_enum(self):
        rp = self.request_variant("r3.json", allowed_write_target="anywhere")
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "allowed_write_target", "not one of")

    def test_wrong_schema_version(self):
        rp = self.request_variant("r4.json", schema_version="2.0")
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "schema_version", "must be '1.0'")

    def test_revision_wrong_type_and_too_small(self):
        rp = self.request_variant("r5.json", revision="3")
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "revision", "integer")
        rp = self.request_variant("r6.json", revision=0)
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "revision", "minimum")

    def test_role_and_skill(self):
        rp = self.request_variant("r7.json", page_role="checkout")
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "page_role is 'checkout'")
        rp = self.request_variant("r8.json", assigned_skill=63)
        self.assert_refused(self.run_intake("--launch-context", str(rp)),
                            "assigned_skill is 63")

    def test_launch_identity_mismatch(self):
        lp = self.write("launch-bad.json",
                        dump(launch_doc(self.ghash, launch_id="other-launch")))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "launch_id")

    def test_launch_not_approved(self):
        lp = self.write("launch-coll.json",
                        dump(launch_doc(self.ghash, status="collecting",
                                        plan_approval_ref=None)))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "status is 'collecting'")

    def test_launch_extras_rule(self):
        bad_extras = {"upsell_1": False, "downsell_1": True, "upsell_2": False}
        lp = self.write("launch-extras.json",
                        dump(launch_doc(self.ghash, extras=bad_extras)))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "extras.downsell_1")

    def test_launch_approved_without_plan_approval_ref(self):
        lp = self.write("launch-noref.json",
                        dump(launch_doc(self.ghash, plan_approval_ref=None)))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "plan_approval_ref")

    def test_launch_test_only_mismatch(self):
        lp = self.write("launch-test.json",
                        dump(launch_doc(self.ghash, test_only=False)))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "test_only")

    def test_other_explicit_provider_refused(self):
        lp = self.write("launch-other.json",
                        dump(launch_doc(self.ghash,
                                        image_provider="other_explicit")))
        self.assert_refused(
            self.run_intake("--launch-context", str(self.request_path),
                            "--launch-record", str(lp)),
            "other_explicit")

    def test_route_graph_hash_mismatch(self):
        rp = self.request_variant("r9.json", route_graph_hash="f" * 64)
        proc = self.run_intake("--launch-context", str(rp),
                               "--route-graph", str(self.graph_path))
        self.assert_refused(proc, "route_graph_hash", "stale routing")

    def test_route_graph_too_few_nodes(self):
        graph = graph_doc()
        graph["nodes"] = graph["nodes"][:2]
        raw = dump(graph)
        gh = hashlib.sha256(raw).hexdigest()
        gp = self.write("graph-small.json", raw)
        rp = self.write("request-small.json", dump(request_doc(gh)))
        self.assert_refused(
            self.run_intake("--launch-context", str(rp),
                            "--route-graph", str(gp)),
            "minItems")

    def test_copy_version_conflict(self):
        proc = self.run_intake("--launch-context", str(self.request_path),
                               "--copy-version", "long-form")
        self.assert_refused(proc, "copy_profile")

    def test_consent_duplicate_id(self):
        dup = self.write("consent-dup.json", dump(CONSENT + [CONSENT[0]]))
        proc = self.run_intake("--launch-context", str(self.request_path),
                               "--consent-statements", str(dup))
        self.assert_refused(proc, "duplicate consent statement id")

    def test_consent_bad_shape(self):
        bad = self.write("consent-bad.json",
                         dump([{"id": "x", "text": "t", "required": "yes"}]))
        proc = self.run_intake("--launch-context", str(self.request_path),
                               "--consent-statements", str(bad))
        self.assert_refused(proc, "'required' must be a boolean")

    def test_orphan_import_input(self):
        proc = self.run_intake("--route-graph", str(self.graph_path))
        self.assert_refused(proc, "--launch-context")


class TestDesignTokens(unittest.TestCase):
    """The tokens component bridge: absent pre-assembly (recorded, never
    substituted) and present (its output emitted verbatim)."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-02-tokens-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))
        self.skill_root = self.td / "skill"
        (self.skill_root / "references").mkdir(parents=True)
        for name in ("page-request.schema.json", "launch.schema.json",
                     "route-graph.schema.json"):
            (self.skill_root / "references" / name).write_bytes(
                (ROOT / "references" / name).read_bytes())

    def test_component_absent_records_not_in_tree(self):
        css, record = launch_context.emit_design_tokens(self.skill_root, None)
        self.assertIsNone(css)
        self.assertEqual(record["status"], "component_not_in_tree")
        self.assertIsNone(record["path"])

    def test_component_present_emits_its_css(self):
        comp_dir = (self.td / "shared-utils" / "signature_launch" / "design"
                    / "tokens")
        comp_dir.mkdir(parents=True)
        (comp_dir / "tokens.py").write_text(
            'def resolve_tokens(brand):\n'
            '    return {"brand_id": brand.get("brand_id"), '
            '"token_version": "1.0.0", "missing": ["colors.accent"]}\n'
            'def tokens_to_css(resolution):\n'
            '    return ":root { --sl-test: 1; }\\n"\n',
            encoding="utf-8")
        brand = self.td / "brand.json"
        brand.write_text(json.dumps({"brand_id": "acme"}), encoding="utf-8")
        css, record = launch_context.emit_design_tokens(self.skill_root, brand)
        self.assertEqual(css, ":root { --sl-test: 1; }\n")
        self.assertEqual(record["status"], "emitted")
        self.assertEqual(record["path"], "launch/design-tokens.css")
        self.assertEqual(record["missing_tokens"], ["colors.accent"])
        self.assertEqual(record["brand_id"], "acme")


class TestProfileGateWiring(unittest.TestCase):
    """stage_gate engages S71-03's gate under the profile, fails closed
    naming it while the flag is absent from the tree, and never touches
    non-profile runs. The flag's presence is a TREE state, so the
    missing-gate and gate-engaged tests pin stage_gate.SKILL_ROOT at
    fake roots that construct each state explicitly (the supported-case
    pattern below): each asserts the same behavior whether the ambient
    tree carries S71-03's flag or not."""

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="s71-02-gate-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.td, ignore_errors=True))
        self.run_dir = self.td / "run"
        (self.run_dir / "copy").mkdir(parents=True)
        (self.run_dir / "copy" / "public-copy.md").write_text(
            "# Heading\n\nSome public copy.\n", encoding="utf-8")
        self.cmd = ("scripts/validate_public_copy.py "
                    f"{self.run_dir}/copy/public-copy.md")

    def write_intake(self, profile):
        intake = {"image_engine": "kie", "copy_version": "standard",
                  "test_run": True}
        if profile:
            intake["launch_profile"] = "signature_launch_landing"
            intake["launch"] = {"launch_id": "launch-2026-bf", "revision": 3}
        (self.run_dir / "intake.json").write_text(
            json.dumps(intake, indent=2) + "\n", encoding="utf-8")

    def pin_skill_root(self, validator_text):
        """Point stage_gate at a fake skill root whose on-disk
        validate_public_copy.py carries exactly validator_text, so the
        gate state under test is constructed, not ambient. Restored on
        test cleanup."""
        fake_root = self.td / "fake-skill"
        (fake_root / "scripts").mkdir(parents=True, exist_ok=True)
        (fake_root / "scripts" / "validate_public_copy.py").write_text(
            validator_text, encoding="utf-8")
        original = stage_gate.SKILL_ROOT
        stage_gate.SKILL_ROOT = fake_root
        self.addCleanup(setattr, stage_gate, "SKILL_ROOT", original)
        return fake_root

    def test_profile_off_command_unchanged(self):
        self.write_intake(profile=False)
        cmd, line = stage_gate.apply_launch_profile(self.cmd, self.run_dir)
        self.assertEqual(cmd, self.cmd)
        self.assertIsNone(line)

    def test_profile_on_fails_closed_naming_the_gate(self):
        self.write_intake(profile=True)
        self.pin_skill_root("# validator build without the launch gate\n")
        cmd, line = stage_gate.apply_launch_profile(self.cmd, self.run_dir)
        self.assertEqual(cmd, self.cmd)
        self.assertIsNotNone(line)
        self.assertIn("S71-03", line)
        self.assertIn("--no-offer-pricing", line)

    def test_profile_on_appends_flag_when_supported(self):
        self.write_intake(profile=True)
        fake_root = self.td / "skill"
        (fake_root / "scripts").mkdir(parents=True)
        (fake_root / "scripts" / "validate_public_copy.py").write_text(
            "# supports --no-offer-pricing\n", encoding="utf-8")
        original = stage_gate.SKILL_ROOT
        stage_gate.SKILL_ROOT = fake_root
        try:
            cmd, line = stage_gate.apply_launch_profile(self.cmd, self.run_dir)
        finally:
            stage_gate.SKILL_ROOT = original
        self.assertIsNone(line)
        self.assertTrue(cmd.endswith(" --no-offer-pricing"))

    def test_copy_stage_close_path_reports_missing_gate(self):
        self.write_intake(profile=True)
        self.pin_skill_root("# validator build without the launch gate\n")
        failures = stage_gate.run_validators(self.run_dir, "copy", None)
        self.assertTrue(any("S71-03" in f for f in failures), failures)
        self.assertTrue(any("--no-offer-pricing" in f for f in failures),
                        failures)

    def test_copy_stage_close_path_engages_gate_when_supported(self):
        self.write_intake(profile=True)
        self.pin_skill_root("# supports --no-offer-pricing\n")
        failures = stage_gate.run_validators(self.run_dir, "copy", None)
        self.assertFalse(
            any("no-offer-pricing gate (S71-03)" in f for f in failures),
            failures)

    def test_report_names_the_profile(self):
        self.write_intake(profile=True)
        warns = stage_gate.collect_warnings(self.run_dir, {"stages": {}})
        self.assertTrue(
            any("launch profile active: signature_launch_landing" in w
                and "launch-2026-bf" in w for w in warns), warns)


class TestLegacyUnchanged(LaunchImportCase):
    def test_legacy_intake_byte_identical(self):
        proc = self.run_intake("--copy-version", "standard")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        raw = (self.run_dir / "intake.json").read_bytes()
        # brand_owner differs from the golden run, so compare structure
        # against the golden bytes with the owner substituted.
        expected = LEGACY_GOLDEN.replace('"BlackCEO"', '"Acme Owner"')
        self.assertEqual(raw.decode("utf-8"), expected)
        self.assertEqual(self.run_files(), ["intake.json"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

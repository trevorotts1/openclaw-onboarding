#!/usr/bin/env python3
"""Findings 13, 14, 15 and 21: one page role and one sequence rule across the builder,
the executor and the page-type runner.

Pins that the upsell request stamps the role the runner verified (never landing), that
every page type refuses another page type's copy form in both the builder and the
executor, that the builder accepts the same 5A/5B/5C expansion the executor accepts,
that a page type whose spec forbids offer buttons may carry its utility buttons, and
that the runner never prints DONE for a preflight and prints runnable next commands.
"""
import contextlib
import importlib.util
import io
import json
import shlex
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from brand_fixture import give_blackceo_colors  # noqa: E402

ROOT = HERE.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = HERE / "fixtures" / "copy_examples"
SKILL80 = ROOT.parent / "80-signature-upsell"
COPY_1 = SKILL80 / "components/80-signature-upsell/fixtures/copy-upsell1-public.valid.json"
COPY_2 = SKILL80 / "components/80-signature-upsell/fixtures/copy-upsell2-public.valid.json"
BUNDLE_1 = SKILL80 / "examples/upsell-result-bundle-upsell1.example.json"
BUNDLE_2 = SKILL80 / "examples/upsell-result-bundle-upsell2-from-downsell1.example.json"
STUB = "STUB-NO-MODEL"
UPSELL_IDS = [str(i) for i in range(1, 9)]
EXPANDED_LONG_FORM = ["1", "2", "2A", "3", "3A", "4", "4A", "5A", "5B", "5C",
                      "6", "7", "8", "9", "10", "11", "12"]
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


exe = load("stage_executor")
builder = load("build_production_request")
runner = load("run_page_type")
forms = load("copy_forms")
page_role = load("page_role")
wspec = load("wireframe_spec")

needs_skill80 = unittest.skipUnless(COPY_1.is_file() and BUNDLE_1.is_file(),
                                    "Skill 80 is not installed beside Skill 71")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def upsell_sections(copy_path=COPY_1, bundle_path=BUNDLE_1):
    return builder.sections_from_copy_json(read(copy_path), read(bundle_path),
                                           read(exe.SPEC_DIR / "upsell-v6.json"), {})


def expanded_long_form():
    """The Long-Form manuscript with its Section 5 written as 5A/5B/5C: 17 sections, the
    optional expansion the copy spec allows (containment.child_sections)."""
    text = (FIXTURES / "long-form-path-b.md").read_text(encoding="utf-8")
    text = text.replace("## Section 5: The Big Bold Why\n", "")
    for child in ("5A", "5B", "5C"):
        text = text.replace(f"### {child}:", f"## Section {child}:")
    return text


class RunCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.run = Path(self.tmp.name)
        give_blackceo_colors(self.run)
        self.addCleanup(self.tmp.cleanup)


@needs_skill80
class VerifiedRoleTests(RunCase):
    """Finding 13: the upsell request carries the role the runner verified."""

    def test_the_verified_role_is_stamped_in_request_and_metadata(self):
        for role, copy_path, bundle_path in (("upsell_1", COPY_1, BUNDLE_1),
                                             ("upsell_2", COPY_2, BUNDLE_2)):
            request = builder.build("visual-mockup", "upsell", "", {}, {}, [], STUB, "", self.run,
                                    role, sections=upsell_sections(copy_path, bundle_path))
            self.assertEqual(request["page_role"], role)
            self.assertEqual(request["metadata"]["page_role"], role)
            self.assertEqual(request["copy_version"], "upsell")

    def test_a_role_the_upsell_form_does_not_serve_is_refused_not_stamped_landing(self):
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "upsell", "", {}, {}, [], STUB, "", self.run,
                          "landing", sections=upsell_sections())
        self.assertIn("is not one of ['upsell_1', 'upsell_2']", str(ctx.exception))


class RoleFormGuardTests(RunCase):
    """Finding 14: role and form must agree, read from copy_forms.form_for_role (plural too)."""

    def test_every_page_type_role_refuses_another_types_form(self):
        for role, version in (("upsell_1", "standard"), ("upsell_2", "long-form"),
                              ("product_selection", "standard"), ("landing", "upsell")):
            with self.assertRaises(exe.ExecutorError, msg=f"{role} + {version}") as ctx:
                exe.check_section_count(self.run, {"page_role": role, "copy_version": version,
                                                   "sections": [{"section_id": "1"}]}, paid=True)
            self.assertIn("disagree", str(ctx.exception))

    def test_each_roles_own_form_is_still_accepted(self):
        for role, version, ids in (("upsell_1", "upsell", UPSELL_IDS),
                                   ("upsell_2", "upsell", UPSELL_IDS),
                                   ("product_selection", "product-selection", ["1", "2", "3", "4", "5"]),
                                   ("thank_you", "thank-you", ["1", "2", "3", "4", "5"])):
            got = exe.check_section_count(self.run, {
                "page_role": role, "copy_version": version,
                "sections": [{"section_id": i} for i in ids]}, paid=True)
            self.assertEqual(got[:2], (version, ids), role)

    def test_the_builder_refuses_a_copy_version_that_belongs_to_another_role(self):
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "standard", "", {}, {}, [], STUB, "", self.run,
                          "upsell_1", sections=upsell_sections())
        self.assertIn("does not fit page role 'upsell_1'", str(ctx.exception))

    def test_a_role_with_its_own_spec_takes_only_a_landing_form(self):
        # the executor's role-spec rule (check_section_count) refuses every page type's own form
        # for a role like checkout; the builder refuses it up front the same way, not late
        for version in ("upsell", "product-selection", "thank-you"):
            with self.assertRaises(builder.BuildError, msg=version) as ctx:
                builder.build("visual-mockup", version, "", {}, {}, [], STUB, "", self.run, "checkout")
            self.assertIn("does not fit page role 'checkout'", str(ctx.exception))

    def test_a_passed_role_the_form_does_not_serve_is_refused_not_overridden(self):
        text = (FIXTURES / "thank-you-path-b.md").read_text(encoding="utf-8")
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "thank-you", text, {}, {}, [], STUB, "", self.run, "banana")
        self.assertIn("does not serve the thank-you form", str(ctx.exception))

    def test_a_registered_role_is_checked_from_its_own_role_even_unpaid(self):
        # finding 14: no declared copy_version must not mean "skip the check" for a page type
        got = exe.check_section_count(self.run, {"page_role": "upsell_1",
                                                 "sections": [{"section_id": i} for i in UPSELL_IDS]})
        self.assertEqual(got[:2], ("upsell", UPSELL_IDS))
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, {"page_role": "upsell_1",
                                               "sections": [{"section_id": str(i)} for i in range(1, 13)]})
        self.assertIn("8 canonical sections", str(ctx.exception))

    def test_a_landing_version_in_the_intake_still_disagrees_with_a_page_type_role(self):
        (self.run / "intake.json").write_text(json.dumps({"copy_version": "standard"}))
        with self.assertRaises(exe.ExecutorError) as ctx:
            exe.check_section_count(self.run, {"page_role": "upsell_1",
                                               "sections": [{"section_id": i} for i in UPSELL_IDS]})
        self.assertIn("disagree", str(ctx.exception))


class SharedSequenceTests(RunCase):
    """Finding 14: one allowed-sequence resolver, read by builder and executor."""

    def test_the_builder_and_executor_allow_the_same_sequences(self):
        spec = forms.load_spec("long-form")
        self.assertEqual(page_role.allowed_sequences(spec), exe.allowed_section_sequences(spec))
        self.assertEqual(exe.allowed_section_sequences(spec)[1], EXPANDED_LONG_FORM)

    def test_the_builder_accepts_the_expanded_long_form_the_executor_accepts(self):
        spec = forms.load_spec("long-form")
        sections = builder.sections_from_manuscript(expanded_long_form(), spec, {})
        self.assertEqual([s["section_id"] for s in sections], EXPANDED_LONG_FORM)
        self.assertEqual(sections[7]["section_name"], "Recognition and reason")
        request = builder.build("visual-mockup", "long-form", expanded_long_form(), {}, {}, [],
                                STUB, "", self.run)
        self.assertEqual(request["metadata"]["canonical_ids"], EXPANDED_LONG_FORM)
        self.assertEqual(exe.check_section_count(
            self.run, {"copy_version": "long-form", "sections": request["sections"]}, paid=True)[1],
            EXPANDED_LONG_FORM)


class UtilityButtonTests(RunCase):
    """Finding 15: a page type whose spec forbids offer buttons keeps its utility buttons."""

    def test_thank_you_keeps_support_and_manage_purchase_side_by_side(self):
        text = (FIXTURES / "thank-you-path-b.md").read_text(encoding="utf-8")
        text = text.replace("**[CTA BUTTON: Contact support]**",
                            "**[CTA BUTTON: Contact support]**\n\n"
                            "**[CTA BUTTON: Manage my purchase]**")
        request = builder.build("visual-mockup", "thank-you", text, {}, {}, [], STUB, "", self.run,
                                "thank_you")
        section = next(s for s in request["sections"] if s["section_id"] == "5")
        self.assertEqual(section["cta_labels"], ["Contact support", "Manage my purchase"])
        self.assertIsNone(section["cta"])

    def test_a_landing_page_still_carries_one_button_per_section(self):
        text = (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8")
        text = text.replace("## Section 2:", "[CTA BUTTON: One]\n[CTA BUTTON: Two]\n\n## Section 2:", 1)
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "standard", text, {}, {}, [], STUB, "", self.run)
        self.assertIn("one button per section", str(ctx.exception))

    def test_a_button_in_a_landing_section_the_spec_forbids_is_refused(self):
        # the landing specs declare cta.standalone "forbidden" for 6, 7, 8, 9, 11 and 12; the
        # builder refuses there instead of letting the copy validator be the first to notice
        text = (FIXTURES / "standard-path-b.md").read_text(encoding="utf-8")
        text = text.replace("## Section 6:", "## Section 6:\n\n[CTA BUTTON: Buy now]\n", 1)
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "standard", text, {}, {}, [], STUB, "", self.run)
        self.assertIn("section 6", str(ctx.exception))
        self.assertIn("forbids a button", str(ctx.exception))

    def test_thank_you_keeps_every_access_button_in_the_access_section(self):
        # finding 15's own reproduction: several purchased-item access buttons in section 3
        text = (FIXTURES / "thank-you-path-b.md").read_text(encoding="utf-8")
        text = text.replace("## Section 3: Access\n",
                            "## Section 3: Access\n\n**[CTA BUTTON: Download the workbook]**\n\n"
                            "**[CTA BUTTON: Watch the lessons]**\n", 1)
        request = builder.build("visual-mockup", "thank-you", text, {}, {}, [], STUB, "", self.run,
                                "thank_you")
        section = next(s for s in request["sections"] if s["section_id"] == "3")
        self.assertEqual(section["cta_labels"],
                         ["Download the workbook", "Watch the lessons",
                          "Access: Own Your Week live owner lab"])
        self.assertIsNone(section["cta"])
        self.assertEqual(section.get("cta_layout"), "utility")
        self.assertEqual(section.get("cta_note"),
                         "One access, download or schedule button per card; the manuscript shows "
                         "one card as the pattern.")
        block = wspec.prompt_block("desktop-wireframe", section, 3, 5, 1440, request)
        self.assertIn("one access, download or schedule button per card", block)
        self.assertNotIn("package card", block)

    def test_the_utility_treatment_reaches_the_copy_contract_and_the_wireframe(self):
        # finding 15's second half: separate labels AND treatments, never the package-card rule
        text = (FIXTURES / "thank-you-path-b.md").read_text(encoding="utf-8")
        text = text.replace("**[CTA BUTTON: Contact support]**",
                            "**[CTA BUTTON: Contact support]**\n\n"
                            "**[CTA BUTTON: Manage my purchase]**")
        request = builder.build("desktop-wireframe", "thank-you", text, {}, {}, [], STUB, "", self.run,
                                "thank_you")
        section = next(s for s in request["sections"] if s["section_id"] == "5")
        self.assertEqual(section.get("cta_layout"), "utility")
        self.assertIn("manage-purchase action is a secondary outlined button",
                      section.get("cta_note", ""))
        contract = exe.copy_contract(section)
        self.assertIn("utility actions on this page", contract)
        self.assertIn("manage-purchase action is a secondary outlined button", contract)
        self.assertNotIn("package card", contract)
        block = wspec.prompt_block("desktop-wireframe", section, 5, 5, 1440, request)
        self.assertIn("utility actions only on this page", block)
        self.assertIn("manage-purchase action is a secondary outlined button", block)
        self.assertNotIn("package card", block)
        self.assertNotIn("inside its card", block)

    def test_a_package_section_needs_its_declared_minimum_of_buttons(self):
        # the product-selection spec declares cta.min = 2: one package is refused, never rendered
        # as a per-card row that silently drops its label
        text = (FIXTURES / "product-selection-path-b.md").read_text(encoding="utf-8")
        one = (text.split("### Package: TEST ONLY Professional")[0] + "## Section 4:"
               + text.split("## Section 4:", 1)[1])
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "product-selection", one, {}, {}, [], STUB, "", self.run)
        self.assertIn("at least 2 package buttons", str(ctx.exception))

    def test_a_button_where_the_spec_forbids_one_is_refused(self):
        text = (FIXTURES / "thank-you-path-b.md").read_text(encoding="utf-8")
        text = text.replace("## Section 2: Order summary\n",
                            "## Section 2: Order summary\n\n**[CTA BUTTON: Buy the bonus]**\n", 1)
        with self.assertRaises(builder.BuildError) as ctx:
            builder.build("visual-mockup", "thank-you", text, {}, {}, [], STUB, "", self.run,
                          "thank_you")
        self.assertIn("section 2", str(ctx.exception))
        self.assertIn("forbids a button", str(ctx.exception))


@needs_skill80
class RunnerOutputTests(unittest.TestCase):
    """Finding 21: a preflight is a preview, and every printed next command runs as printed."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run = Path(self.tmp.name) / "run dir"  # a space in the path: the printed command must survive it
        self.run.mkdir()
        self.request = Path(self.tmp.name) / "page-request.json"
        self.request.write_text(json.dumps({"page_role": "upsell_1"}), encoding="utf-8")
        self.bundle = Path(self.tmp.name) / "bundle.json"
        self.bundle.write_text(json.dumps({"page_plan": {"instance": "upsell_1"}}), encoding="utf-8")
        self.original_run = runner.run
        self.addCleanup(setattr, runner, "run", self.original_run)
        runner.run = lambda argv: 0  # no subprocess and no provider: only the printed advice is checked

    def output(self, *extra, rc=0):
        argv = ["--copy-version", "upsell", "--copy-json", COPY_1, "--bundle", self.bundle,
                "--request", self.request, "--launch-record", self.request,
                "--route-graph", self.request, "--brand-file", self.request,
                "--brand-owner", "x", "--image-cap", 1, "--run-dir", self.run, *extra]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(runner.main([str(x) for x in argv]), rc)
        return out.getvalue()

    def test_a_request_and_bundle_that_disagree_are_refused_before_any_build(self):
        # finding 13: the runner's verified role is the request's AND the bundle's; a mismatch
        # must stop before a single builder or executor call, never fall through to landing
        self.bundle.write_text(json.dumps({"page_plan": {"instance": "upsell_2"}}))
        seen = []
        runner.run = lambda argv: seen.append(argv) or 0
        text = self.output(rc=1)
        self.assertIn("REFUSED", text)
        self.assertEqual(seen, [])

    def test_preflight_prints_preview_and_two_separate_runnable_commands(self):
        text = self.output("--preflight")
        self.assertIn("PREVIEW upsell_1", text)
        self.assertNotIn("DONE", text)
        self.assertNotIn("design-board, final-mockups", text)
        lines = {l.split(",", 1)[0]: l for l in text.splitlines() if l.startswith("NEXT ")}
        self.assertEqual(set(lines), {"NEXT 1", "NEXT 2"})
        # every command must paste and run as printed: shell-split back to one argv per command
        board = shlex.split(lines["NEXT 1"].rsplit(": ", 1)[1])
        self.assertEqual(board, [sys.executable, str(SCRIPTS / "stage_executor.py"),
                                 str(self.run.resolve()), "--stages", "design-board",
                                 "--request", "production-request-visual-mockup.json"])
        build, execute = (shlex.split(part) for part in lines["NEXT 2"].rsplit(": ", 1)[1].split(" && "))
        self.assertEqual(build[:2], [sys.executable, str(SCRIPTS / "build_production_request.py")])
        self.assertIn(["--stage", "final-mockups"], [build[i:i + 2] for i in range(len(build) - 1)])
        self.assertIn(["--out", str(self.run.resolve() / "production-request-final-mockups.json")],
                      [build[i:i + 2] for i in range(len(build) - 1)])
        self.assertEqual(execute, [sys.executable, str(SCRIPTS / "stage_executor.py"),
                                   str(self.run.resolve()), "--stages", "final-mockups",
                                   "--request", "production-request-final-mockups.json"])

    def test_a_real_run_prints_done(self):
        text = self.output("--provider", "kie")
        self.assertIn("DONE upsell_1", text)
        self.assertNotIn("PREVIEW", text)

    def test_a_stub_run_is_a_preview_not_a_completion(self):
        # finding 21: DONE was printed for stub output too, which is placeholder PNGs
        text = self.output()
        self.assertIn("PREVIEW upsell_1", text)
        self.assertIn("placeholder", text)
        self.assertNotIn("DONE", text)
        self.assertIn("nothing is complete yet", text)

    def test_the_verified_role_is_forwarded_to_every_builder_and_executor_call(self):
        # finding 13: the runner's verified role must reach the builder, never the landing default
        seen = []
        runner.run = lambda argv: seen.append([str(a) for a in argv]) or 0
        self.output()
        builds = [a for a in seen if a[0].endswith("build_production_request.py")]
        runs = [a for a in seen if a[0].endswith("stage_executor.py")]
        self.assertEqual(len(builds), len(runner.STAGES))
        self.assertEqual(len(runs), len(runner.STAGES))
        for argv, stage in zip(builds, runner.STAGES):
            pairs = [argv[i:i + 2] for i in range(len(argv) - 1)]
            self.assertIn(["--page-role", "upsell_1"], pairs)
            self.assertIn(["--copy-version", "upsell"], pairs)
            self.assertIn(["--stage", stage], pairs)
        for argv, stage in zip(runs, runner.STAGES):
            self.assertEqual(argv[1], str(self.run.resolve()))
            self.assertIn(["--stages", stage], [argv[i:i + 2] for i in range(len(argv) - 1)])
            self.assertIn(["--request", f"production-request-{stage}.json"],
                          [argv[i:i + 2] for i in range(len(argv) - 1)])


if __name__ == "__main__":
    unittest.main()

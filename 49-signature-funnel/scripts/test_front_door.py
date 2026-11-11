#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""test_front_door.py - one front door for Skill 49 dispatch (83 included); the pin is CI-minted and covers every
decision file (ENF-02, ENF-14, ENF-15).

Every tamper runs on a throwaway COPY of the trees with its own freshly minted pin, so nothing here edits the
repository. Real subprocesses (the shell entry, `cli dispatch`), no network. Run:
    python3 -m pytest 49-signature-funnel/scripts/test_front_door.py -q
"""
import ast
import contextlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent
REPO = SKILL.parent
sys.path.insert(0, str(HERE))
import front_door as fd  # noqa: E402

PIN_REL = "scripts/SF-PROVER-PIN.sha256"
SKIP = shutil.ignore_patterns("__pycache__", "examples", "working", "fixtures", "tests")


def _top_files_only(directory, names):
    return [n for n in names if (Path(directory) / n).is_dir()]


class Trees(unittest.TestCase):
    """A copy of 49 + 83 + the shared contract/launch trees, pinned, shared by the tests below."""

    @classmethod
    def setUpClass(cls):
        cls._td = tempfile.TemporaryDirectory()
        root = Path(cls._td.name)
        cls.t49, cls.t83 = root / "49-signature-funnel", root / "83-black-friday-launcher"
        cls.t71 = root / "71-blackceo-signature-page"
        shutil.copytree(SKILL, cls.t49, ignore=SKIP)
        shutil.copytree(REPO / "83-black-friday-launcher", cls.t83, ignore=SKIP)
        shutil.copytree(REPO / "71-blackceo-signature-page", cls.t71, ignore=SKIP)
        for name in ("signature_launch", "signature_launch_contract"):
            shutil.copytree(REPO / "shared-utils" / name, root / "shared-utils" / name, ignore=_top_files_only)
        # 83's `cli dispatch` runs its dependency preflight (every sibling skill tree, client_intake, the registry
        # map) BEFORE the front door, so the fixture links the real siblings in; the pinned trees stay the copies.
        for src in REPO.iterdir():
            if src.is_dir() and (src.name[:1].isdigit() or (src / "SKILL.md").is_file()) and not (root / src.name).exists():
                (root / src.name).symlink_to(src, target_is_directory=True)
        for src in (REPO / "shared-utils").iterdir():
            if src.is_dir() and not (root / "shared-utils" / src.name).exists():
                (root / "shared-utils" / src.name).symlink_to(src, target_is_directory=True)
        # the fixture's own mint, through the only legal path; the repo pin is untouched
        fd.mint_pin_ci(cls.t49, env={"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
                                     "GITHUB_REPOSITORY": "local/test", "GITHUB_RUN_ID": "0"})
        cls.pin_path = cls.t49 / PIN_REL
        cls.env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        cls.key = root.parent / (root.name + "-operator.key")  # outside the copied checkout
        cls.key.write_text("operator-held-pin-key-0123456789abcdef\n")
        cls.key.chmod(0o600)

    @classmethod
    def tearDownClass(cls):
        cls._td.cleanup()
        cls.key.unlink(missing_ok=True)

    @contextlib.contextmanager
    def tampered(self, path, extra=b"\n"):
        """Change one byte (append a newline) of a copied file, restore it afterwards."""
        original = path.read_bytes()
        path.write_bytes(original + extra)
        try:
            yield path
        finally:
            path.write_bytes(original)

    def shell(self, *args, **env):
        return subprocess.run(["bash", str(self.t49 / "signature-funnel-entry.sh"), *args], text=True,
                              capture_output=True, env=dict(self.env, SF_PIN_AUTHORITY_KEY_FILE=str(self.key), **env))

    def run_dir(self, td):
        rd = Path(td) / "run"
        rd.mkdir()
        for name in ("launch.json", "approval.json", "launch-request.json"):
            (rd / name).write_text("{}", encoding="utf-8")
        return rd

    def cli_dispatch(self, td):
        intake = json.loads((REPO / "83-black-friday-launcher/fixtures/elevation/intake.json").read_text())
        # the copied 83 tree has no fixtures/, so the intake names the real answers file by absolute path
        intake["answers_file"] = str(REPO / "83-black-friday-launcher/fixtures/elevation/answers.json")
        intake["image_plan"] = {"brand_file": str(Path(td) / "brand.json"), "brand_owner": "TEST-ONLY Client"}
        files = {"intake.json": intake, "approval.json": {}}
        for name, doc in files.items():
            (Path(td) / name).write_text(json.dumps(doc), encoding="utf-8")
        # 83 reads the entitlement back from GHL before it reaches the front door; the launcher's own offline
        # TEST-ONLY transport stands in for that read (imported after the copied launcher_core is cached).
        boot = ("import sys; sys.path.insert(0, '.'); import launcher_core.cli as c; "
                f"sys.path.insert(0, {str(REPO / '83-black-friday-launcher/fixtures')!r}); "
                "import test_only_readback as r; r.install(); raise SystemExit(c.main(sys.argv[1:]))")
        return subprocess.run(
            [sys.executable, "-c", boot, "dispatch", "--intake", str(Path(td) / "intake.json"),
             "--out", str(Path(td) / "out"), "--approval", str(Path(td) / "approval.json"),
             "--client", "a", "--worker", "a"],
            cwd=self.t83, text=True, capture_output=True, env=self.env)


class TamperedPinnedFileStopsBothDoors(Trees):
    """ENF-02: row 1 and row 5. One byte of validate_launch_plan.py aborts the shell entry AND 83 dispatch."""

    def test_pristine_files_clear_both_doors(self):
        with tempfile.TemporaryDirectory() as td:
            p = self.shell("--mode", "signature_launch", "--run-dir", str(self.run_dir(td)))
            self.assertIn("front door cleared", p.stdout + p.stderr)  # the dispatcher then refuses the empty {} files
            self.assertNotIn("HASH-PIN", p.stdout + p.stderr)
            c = self.cli_dispatch(td)
            self.assertNotIn("HASH-PIN", c.stdout + c.stderr)

    def test_one_byte_of_validate_launch_plan_aborts_the_shell_entry(self):
        with self.tampered(self.t49 / "scripts/validate_launch_plan.py"), tempfile.TemporaryDirectory() as td:
            p = self.shell("--mode", "signature_launch", "--run-dir", str(self.run_dir(td)))
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("HASH-PIN", p.stderr)
            self.assertNotIn("front door cleared", p.stdout)

    def test_one_byte_of_validate_launch_plan_aborts_cli_dispatch(self):
        with self.tampered(self.t49 / "scripts/validate_launch_plan.py"), tempfile.TemporaryDirectory() as td:
            c = self.cli_dispatch(td)
            self.assertNotEqual(c.returncode, 0)
            self.assertIn("HASH-PIN", c.stderr)
            self.assertFalse((Path(td) / "out" / "dispatch").exists(), "nothing may be dispatched")

    def test_83_substrate_gate_aborts_before_any_skill_49_module_loads(self):
        code = ("import sys; sys.path.insert(0, 'routes'); import substrate; substrate.dispatch()")
        for tamper in (True, False):
            with contextlib.ExitStack() as stack:
                if tamper:
                    stack.enter_context(self.tampered(self.t49 / "scripts/validate_launch_plan.py"))
                p = subprocess.run([sys.executable, "-c", code], cwd=self.t83, text=True, capture_output=True,
                                   env=self.env)
            self.assertEqual(p.returncode == 0, not tamper, p.stdout + p.stderr)
            self.assertEqual("HASH-PIN" in p.stderr, tamper, p.stderr)

    def test_the_gate_is_not_catchable_by_a_broad_except(self):
        self.assertTrue(issubclass(fd.FrontDoorError, SystemExit))
        self.assertFalse(issubclass(fd.FrontDoorError, Exception))


class EveryDecisionFileIsPinned(Trees):
    """ENF-15: rows 3 and 7."""

    def names(self):
        return {n for n, _ in fd.pin_files(self.t49)}

    def test_the_generated_list_names_the_decision_files(self):
        names = self.names()
        for want in ("49/structure/page_types.json", "49/scripts/collect_launch_receipts.py",
                     "49/scripts/launch_intake.py", "49/scripts/page_set.py", "49/scripts/landing_bridge.py",
                     "49/scripts/validate_launch_plan.py", "49/FUNNEL-MANIFEST.json", "49/role_wrappers.py",
                     "49/signature-funnel-entry.sh",
                     "shared/contract/validate_launch_plan.py", "83/routes/substrate.py"):
            self.assertIn(want, names)
        for wrapper in (self.t49 / "scripts").glob("*_wrapper.py"):
            if wrapper.name.startswith("test_"):
                continue
            self.assertIn(f"49/scripts/{wrapper.name}", names)
        for f in (self.t83 / "launcher_core").iterdir():
            if f.suffix in (".py", ".json"):
                self.assertIn(f"83/launcher_core/{f.name}", names)
        self.assertFalse([n for n in names if Path(n).name.startswith("test_")], "tests are not pinned")

    def test_every_module_the_dispatch_chain_imports_is_pinned(self):
        names, seen, todo = self.names(), set(), ["dispatch_launch"]
        while todo:
            mod = todo.pop()
            if mod in seen or not (self.t49 / "scripts" / f"{mod}.py").is_file():
                continue
            seen.add(mod)
            self.assertIn(f"49/scripts/{mod}.py", names)
            for node in ast.walk(ast.parse((self.t49 / "scripts" / f"{mod}.py").read_text(encoding="utf-8"))):
                if isinstance(node, ast.Import):
                    todo += [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    todo.append(node.module.split(".")[0])
        self.assertGreater(len(seen), 5)

    def test_editing_page_types_or_landing_bridge_trips_hash_pin(self):
        for rel in ("structure/page_types.json", "scripts/landing_bridge.py", "scripts/launch_intake.py",
                    "scripts/checkout_wrapper.py"):
            with self.tampered(self.t49 / rel):
                with self.assertRaises(fd.FrontDoorError) as cm:
                    fd.check(skill_dir=self.t49)
                self.assertEqual(cm.exception.gate, "HASH-PIN", rel)
        with self.tampered(self.t83 / "launcher_core/intake.py"), self.assertRaises(fd.FrontDoorError):
            fd.check(skill_dir=self.t49)
        fd.check(skill_dir=self.t49)  # restored: clear again

    def test_the_shell_floor_must_stay_inside_the_generated_list(self):
        fd.step_hashpin(self.t49, must_cover=["scripts/prove_sf_cert.py", "structure/funnel_structure.json"])
        with self.assertRaises(fd.FrontDoorError) as cm:
            fd.step_hashpin(self.t49, must_cover=["scripts/not_in_the_list.py"])
        self.assertIn("no longer covers", str(cm.exception))

    def test_a_new_unpinned_file_trips_the_pin(self):
        extra = self.t49 / "scripts" / "new_wrapper.py"
        extra.write_text("X = 1\n")
        try:
            with self.assertRaises(fd.FrontDoorError):
                fd.step_hashpin(self.t49)
        finally:
            extra.unlink()

    def test_bypass_scan_covers_the_skill_tree_not_just_the_run_dir(self):
        self.assertEqual(fd.scan_tree(self.t49), [])
        for rel, extra, why in (
                ("scripts/checkout_wrapper.py", b"\nimport requests\n", "network import"),
                ("scripts/upsell_wrapper.py", b"\nimport urllib.request\n", "network import"),
                ("scripts/downsell_wrapper.py", b"\nx = __import__('socket')\n", "dynamic import"),
                ("structure/page_types.json", b'\n "h": "backend.leadconnectorhq.com"\n', "GHL host in data"),
                ("scripts/selection_wrapper.py", b"\nimport subprocess\nsubprocess.run('curl -s x', shell=True)\n",
                 "curl")):
            with self.tampered(self.t49 / rel, extra):
                self.assertTrue(fd.scan_tree(self.t49), why)
                with self.assertRaises(fd.FrontDoorError):
                    fd.step_bypass_scan(None, self.t49)
        with self.tampered(self.t83 / "launcher_core/checkout.py", b"\nimport smtplib\n"):
            self.assertTrue(fd.scan_tree(self.t49), "83 tree is scanned too")
        # the approved adapters inside the tree stay allowed (explicit, pinned list)
        self.assertEqual(fd.NET_ALLOWED, {"49/scripts/agnes_orchestrator.py", "49/scripts/mc_board.py",
                                          "shared/contract/approval_record.py", "shared/launch/launch_events.py"})

    def test_a_loopback_server_is_refused_outside_the_tests_folder(self):
        # Issue 38 fixture: the loopback Command Center stand-in (http.server) lives in 49-signature-funnel/tests/,
        # a folder the scan skips and the pin does not list (like examples/ and working/). The same import
        # anywhere else in the tree is still a BYPASS-SCAN hit, and the stand-in has not drifted back next to
        # the product scripts.
        fake = SKILL / "tests" / "fake_command_center.py"
        self.assertTrue(fake.is_file())
        self.assertFalse((SKILL / "scripts" / "fake_command_center.py").exists())
        self.assertFalse((SKILL / "scripts" / "fixtures" / "fake_command_center.py").exists())
        self.assertIn("http.server", fake.read_text(encoding="utf-8"))
        self.assertEqual(fd.scan_tree(SKILL), [])
        self.assertEqual(fd.scan_tree(self.t49), [])
        for rel in ("scripts/fake_command_center.py", "scripts/loopback_helper.py", "adapters/loopback_helper.py"):
            path = self.t49 / rel
            path.write_text("from http.server import ThreadingHTTPServer\n")
            try:
                hits = fd.scan_tree(self.t49)
                self.assertTrue(any(rel in h and "network module" in h for h in hits), (rel, hits))
                with self.assertRaises(fd.FrontDoorError):
                    fd.step_bypass_scan(None, self.t49)
            finally:
                path.unlink()
        self.assertEqual(fd.scan_tree(self.t49), [])


class Skill71PageBuildTreeIsPinned(Trees):
    """FIX-16 Branch A: the Skill 71 page-build tree is inside the composition, so one digest certifies the
    code that actually builds the pages. The pin covers scripts and the reference JSON those scripts read;
    Skill 71's own test files are not pinned, and a missing tree fails closed."""

    def names(self):
        return {n for n, _ in fd.pin_files(self.t49)}

    def test_every_skill71_script_and_reference_json_is_named(self):
        names = self.names()
        for want in ("71/scripts/swarm_runner.py", "71/scripts/shared_page_service.py",
                     "71/scripts/build_production_request.py", "71/scripts/page_role.py",
                     "71/scripts/copy_forms.py", "71/references/launch.schema.json",
                     "71/references/page-kinds.json", "71/references/copy-specs/roles/checkout.json"):
            self.assertIn(want, names)
        for f in (self.t71 / "scripts").glob("*.py"):
            if not fd._is_test(f.name):
                self.assertIn(f"71/scripts/{f.name}", names)
        for sub in ("references", "references/copy-specs", "references/copy-specs/roles",
                    "references/style-traits"):
            for f in (self.t71 / sub).glob("*.json"):
                self.assertIn(f"71/{sub}/{f.name}", names, sub)

    def test_a_new_or_edited_skill71_file_trips_hash_pin_both_ways(self):
        # both directions: an edit to an existing pinned file, and a brand-new file the generated list picks up
        for rel in ("scripts/swarm_runner.py", "scripts/shared_page_service.py", "references/launch.schema.json"):
            with self.tampered(self.t71 / rel):
                with self.assertRaises(fd.FrontDoorError) as cm:
                    fd.check(skill_dir=self.t49)
                self.assertEqual(cm.exception.gate, "HASH-PIN", rel)
        extra = self.t71 / "scripts" / "new_page_stage.py"
        extra.write_text("X = 1\n")
        try:
            with self.assertRaises(fd.FrontDoorError) as cm:
                fd.step_hashpin(self.t49)
            self.assertEqual(cm.exception.gate, "HASH-PIN")
        finally:
            extra.unlink()
        fd.check(skill_dir=self.t49)  # restored: clear again

    def test_skill71_test_files_are_not_pinned(self):
        before = fd.compute_pin(self.t49)
        extra = self.t71 / "scripts" / "test_not_pinned.py"
        extra.write_text("X = 1\n")
        try:
            self.assertEqual(fd.compute_pin(self.t49), before)
            self.assertNotIn("71/scripts/test_not_pinned.py", self.names())
        finally:
            extra.unlink()

    def test_a_missing_skill71_tree_fails_closed(self):
        moved = self.t71.with_name(self.t71.name + ".moved")
        self.t71.rename(moved)
        try:
            with self.assertRaises(fd.FrontDoorError) as cm:
                fd.pin_files(self.t49)
            self.assertEqual(cm.exception.gate, "HASH-PIN")
            self.assertIn("pinned tree missing: 71", cm.exception.detail)
        finally:
            moved.rename(self.t71)

    def test_skill71_is_pinned_but_not_string_scanned(self):
        # boundary: Skill 71's builders legitimately import urllib.request (browser bootstrap, run events),
        # so the string/AST scan does not cover that tree. The file is still protected by the pin above.
        self.assertEqual(fd.scan_tree(self.t49), [])
        with self.tampered(self.t71 / "scripts/stage_gate.py", b"\nimport requests\n"):
            self.assertEqual(fd.scan_tree(self.t49), [])
            with self.assertRaises(fd.FrontDoorError):
                fd.step_hashpin(self.t49)
        fd.check(skill_dir=self.t49)

class PinIsMintedOnlyByTheAuthority(Trees):
    """ENF-14: rows 2, 4 and 6."""

    def write_pin(self, *args):
        return self.shell("--write-pin", *args)

    def record(self, **over):
        rec = fd.sign_rotation("operator", self.t49, str(self.key))
        rec.update(over)
        path = Path(tempfile.mkdtemp(dir=self.key.parent)) / "record.json"
        path.write_text(json.dumps(rec), encoding="utf-8")
        return path

    def test_write_pin_without_a_record_exits_non_zero_and_leaves_the_pin(self):
        before = self.pin_path.read_bytes()
        with self.tampered(self.t49 / "scripts/page_set.py"):
            p = self.write_pin()
            self.assertNotEqual(p.returncode, 0)
            self.assertIn("PIN-ROTATION", p.stderr)
        self.assertEqual(self.pin_path.read_bytes(), before)

    def test_a_bad_record_is_refused_and_the_pin_is_untouched(self):
        before = self.pin_path.read_bytes()
        with self.tampered(self.t49 / "scripts/page_set.py"):
            good = self.record()
            forged = json.loads(good.read_text())
            forged["signature"] = "0" * 64
            wrong_pin = self.record(pin="f" * 64)  # signature no longer matches either
            bad_kind = self.record(kind="approval")
            expired = self.record(expires_at="2020-01-01T00:00:00+00:00")
            for label, rec in (("forged signature", None), ("other pin", wrong_pin), ("wrong kind", bad_kind),
                               ("expired", expired)):
                if rec is None:
                    rec = good.parent / "forged.json"
                    rec.write_text(json.dumps(forged), encoding="utf-8")
                p = self.write_pin("--rotation-record", str(rec))
                self.assertNotEqual(p.returncode, 0, label)
            self.key.chmod(0o644)  # a world-readable key is no authority
            try:
                self.assertNotEqual(self.write_pin("--rotation-record", str(good)).returncode, 0)
            finally:
                self.key.chmod(0o600)
        self.assertEqual(self.pin_path.read_bytes(), before)

    def test_a_record_for_an_earlier_tree_does_not_cover_a_later_edit(self):
        before = self.pin_path.read_bytes()
        good = self.record()  # signed for the pristine digest
        with self.tampered(self.t49 / "scripts/page_set.py"):
            self.assertNotEqual(self.write_pin("--rotation-record", str(good)).returncode, 0)
        self.assertEqual(self.pin_path.read_bytes(), before)

    def test_a_signed_pin_rotation_record_for_this_tree_re_mints(self):
        before = self.pin_path.read_bytes()
        try:
            with self.tampered(self.t49 / "scripts/page_set.py"):
                p = self.write_pin("--rotation-record", str(self.record()))
                self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
                self.assertEqual(self.pin_path.read_text().strip(), fd.compute_pin(self.t49))
        finally:
            self.pin_path.write_bytes(before)

    def test_the_key_must_live_outside_the_checkout(self):
        inside = self.t49 / "operator.key"
        inside.write_text("operator-held-pin-key-0123456789abcdef\n")
        inside.chmod(0o600)
        try:
            with self.assertRaises(fd.FrontDoorError):
                fd.sign_rotation("operator", self.t49, str(inside))
        finally:
            inside.unlink()

    def test_the_ci_mint_refuses_outside_the_workflow(self):
        with self.assertRaises(fd.FrontDoorError):
            fd.mint_pin_ci(self.t49, env={})
        with self.assertRaises(fd.FrontDoorError):
            fd.mint_pin_ci(self.t49, env={"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "pull_request",
                                          "GITHUB_REPOSITORY": "o/r", "GITHUB_RUN_ID": "1"})
        env = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push", "GITHUB_REPOSITORY": "o/r",
               "GITHUB_RUN_ID": "1"}
        before = self.pin_path.read_bytes()
        try:
            with self.tampered(self.t49 / "scripts/page_set.py"):
                self.assertEqual(fd.mint_pin_ci(self.t49, env=env), fd.compute_pin(self.t49))
        finally:
            self.pin_path.write_bytes(before)

    def test_the_workflow_is_the_only_minting_path_and_verifies_prs(self):
        import yaml  # PyYAML ships on the CI runners and the operator Mac
        wf_dir = REPO / ".github" / "workflows"
        doc = yaml.safe_load((wf_dir / "sf-prover-pin-authority.yml").read_text(encoding="utf-8"))
        triggers = doc.get("on", doc.get(True))
        self.assertIn("pull_request", triggers)
        self.assertTrue(any(p.startswith("49-signature-funnel") for p in triggers["pull_request"]["paths"]))
        self.assertTrue(any(p.startswith("83-black-friday-launcher") for p in triggers["pull_request"]["paths"]))
        self.assertIn("tags", triggers["push"])  # the pin is re-checked against the tagged tree
        verify, mint = doc["jobs"]["verify"], doc["jobs"]["mint"]
        verify_text = json.dumps(verify)
        self.assertIn("front_door.py", verify_text)
        self.assertIn("hashpin", verify_text)
        self.assertIn("trusted/", verify_text)  # the base branch judges the PR, not the PR itself
        self.assertNotIn("mint-pin", verify_text)
        # the guard keys on commits, never on the human who opened the PR (that deadlocked the bootstrap PR)
        self.assertNotIn("github.actor", verify_text)
        self.assertNotIn("PR_ACTOR", verify_text)
        self.assertNotIn("[skip ci]", json.dumps(mint))
        self.assertIn("workflow_dispatch", mint["if"])
        recompute = next(s["run"] for s in verify["steps"] if s.get("name", "").startswith("Recompute the pin"))
        bootstrap, _, later = recompute.partition("fi\n")  # the bootstrap branch ends at the first fi
        self.assertIn("bypass-scan", bootstrap)
        self.assertNotIn("hashpin", bootstrap)
        self.assertIn("hashpin", later)
        self.assertIn('"$verifier"', later)  # the trusted verifier
        self.assertEqual(verify["permissions"] if "permissions" in verify else doc["permissions"],
                         {"contents": "read"})
        self.assertEqual(mint["permissions"], {"contents": "write"})
        self.assertIn("mint-pin --ci", json.dumps(mint))
        self.assertNotIn("pull_request", mint["if"])
        for other in wf_dir.glob("*.yml"):
            if other.name != "sf-prover-pin-authority.yml":
                text = other.read_text(encoding="utf-8")
                self.assertNotIn("mint-pin", text, other.name)
                self.assertNotIn("SF-PROVER-PIN", text, other.name)

    def test_the_pin_guard_accepts_only_bot_minted_pin_commits(self):
        import yaml
        doc = yaml.safe_load((REPO / ".github/workflows/sf-prover-pin-authority.yml").read_text(encoding="utf-8"))
        script = next(s["run"] for s in doc["jobs"]["verify"]["steps"] if s.get("name") == "Refuse a hand-edited pin file")
        pin, bot = "49-signature-funnel/scripts/SF-PROVER-PIN.sha256", "41898282+github-actions[bot]@users.noreply.github.com"

        def git(tree, *a, who=("Human", "human@example.com")):
            env = dict(os.environ, GIT_AUTHOR_NAME=who[0], GIT_AUTHOR_EMAIL=who[1],
                       GIT_COMMITTER_NAME=who[0], GIT_COMMITTER_EMAIL=who[1])
            return subprocess.run(["git", "-C", str(tree), *a], check=True, text=True, capture_output=True,
                                  env=env).stdout.strip()

        def commit(tree, files, who):
            for rel, text in files.items():
                (tree / rel).write_text(text)
            git(tree, "add", "-A")
            git(tree, "commit", "-q", "-m", "c", who=who)
            return git(tree, "rev-parse", "HEAD")

        human, robot = ("Human", "human@example.com"), ("github-actions[bot]", bot)
        cases = {}  # label -> (expected rc == 0, head sha)
        with tempfile.TemporaryDirectory() as td:
            tree = Path(td) / "tree"
            (tree / "49-signature-funnel/scripts").mkdir(parents=True)
            git(tree, "init", "-q")
            git(tree, "config", "user.name", "x")
            git(tree, "config", "user.email", "x@example.com")
            (tree / pin).write_text("base\n")
            (tree / "other.txt").write_text("base\n")
            git(tree, "add", "-A")
            git(tree, "commit", "-q", "-m", "base")
            base = git(tree, "rev-parse", "HEAD")

            def head_for(label, steps):
                git(tree, "checkout", "-q", "-B", label, base)
                for files, who in steps:
                    sha = commit(tree, files, who)
                cases[label] = sha

            head_for("human", [({pin: "human\n"}, human)])
            head_for("bot_only", [({pin: "bot\n"}, robot)])
            head_for("bot_plus_other", [({pin: "bot\n", "other.txt": "x\n"}, robot)])
            head_for("revert", [({pin: "human\n"}, human), ({pin: "base\n"}, human)])
            for label, ok in (("human", False), ("bot_only", True), ("bot_plus_other", False), ("revert", True)):
                p = subprocess.run(["bash", "-c", script], cwd=td, text=True, capture_output=True,
                                   env=dict(os.environ, BASE_SHA=base, HEAD_SHA=cases[label]))
                self.assertEqual(p.returncode == 0, ok, f"{label}: {p.stdout}{p.stderr}")

    def test_the_shell_entry_has_no_pin_writer_of_its_own(self):
        text = (SKILL / "signature-funnel-entry.sh").read_text(encoding="utf-8")
        self.assertNotIn("compute_pin", text)
        self.assertNotIn("> \"$PIN_FILE\"", text)
        self.assertIn("front_door.py", text)


class TheRepositoryPinMatchesTheTree(unittest.TestCase):
    """The CI recompute, run locally: the committed pin must equal the tree (rows 5 and 6, pristine side)."""

    def test_committed_pin_matches_this_tree_and_the_gates_clear(self):
        pin = fd.check(skill_dir=SKILL)
        self.assertEqual(pin, (SKILL / PIN_REL).read_text().strip())


if __name__ == "__main__":
    unittest.main(verbosity=2)

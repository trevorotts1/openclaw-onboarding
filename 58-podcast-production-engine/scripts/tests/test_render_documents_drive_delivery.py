#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: Step 12 Google Drive delivery
# -----------------------------------------------------------------------------
# Stdlib unittest only, fully offline. The Drive transport is injected, so no
# socket is ever opened and no credential value is read from a real key file.
#
# What these tests hold down (ISSUE-15):
#   1. Credentials ABSENT  -> the plan stays intent-only, exactly one skip line
#      naming Skill 14 reaches stderr, and the exit code is unchanged (0).
#   2. Credentials PRESENT -> every drive.upload_convert and drive.set_permission
#      intent is PERFORMED, stamped performed:true, and the resulting file ids
#      and links are recorded in the plan under links.* and delivery.documents
#      so Steps 16 and 17 (GHL completion) can reference real documents.
#   3. Drive API ERROR     -> the episode continues, the error is recorded on the
#      plan, and the exit code is unchanged (0).
#
# Plus the standing safety rules: the gws binary is never invoked (a bare headless
# gws call self-wipes the default credential store), no secret value is ever
# written into the plan or printed, and the full Drive scope is the one requested
# because domain-wide delegation rejects the narrow drive.file scope.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_render_documents_drive_delivery.py
# =============================================================================
"""Deterministic offline tests for Step 12 Google Drive delivery."""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

_HERE = Path(__file__).resolve()
_SCRIPT = _HERE.parent.parent / "render_documents.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("render_documents", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


RD = _load_module()

# A syntactically valid service-account shape. The private key is a placeholder
# that is never signed with, because the transport is injected in every test.
FAKE_SA = {
    "type": "service_account",
    "client_email": "podcast-delivery@example-project.iam.gserviceaccount.com",
    "private_key": "-----BEGIN PRIVATE KEY-----\nplaceholder\n-----END PRIVATE KEY-----\n",
}

MANIFEST = {
    "title": "The Quiet Compounding Of Small Habits",
    "client": "Example Show",
    "mode": "personal",
    "style": "narrative",
    "thesis": "Small repeated actions outperform bursts of intensity.",
    "runtime_minutes": 24,
    "word_count": 3400,
    "speech_script": (
        "Welcome back to the show.\n"
        "Today we look at what happens when you keep a promise to yourself "
        "for ninety days straight.\n"
        "The result is rarely dramatic on any single day.\n"
    ),
}

# Every env name either delivery tier consults, cleared per test so a developer box
# with real credentials cannot change an outcome.
_GOOGLE_ENVS = (
    RD.SA_KEY_ENVS + RD.IMPERSONATE_ENVS + (RD.DRIVE_ROOT_FOLDER_ENV,)
    + RD.NOTION_TOKEN_ENVS + RD.NOTION_PARENT_ENVS
    + (RD.NOTION_AGENCY_TOKEN_ENV, RD.NOTION_AGENCY_PARENT_ENV, RD.NOTION_VERSION_ENV)
)



def DRIVE(plan):
    """The Google Drive tier's own record inside the delivery chain."""
    return plan["delivery"]["tiers"]["google_drive"]


def NOTION(plan):
    """The Notion tier's own record inside the delivery chain."""
    return plan["delivery"]["tiers"]["notion"]


class FakeTransport:
    """Records every Drive call. Optionally fails one of them."""

    def __init__(self, fail_on=None, fail_message="drive is unhappy",
                 inherited_permission=False):
        self.uploads = []
        self.permissions = []
        self.fail_on = fail_on
        self.fail_message = fail_message
        self.inherited_permission = inherited_permission
        self._seq = 0

    def upload_convert(self, source, name, mime_import, mime_target,
                       parent_folder_id=None):
        if self.fail_on == "upload":
            raise RD.DriveDeliveryError(self.fail_message)
        self._seq += 1
        file_id = "file-%d" % self._seq
        self.uploads.append({
            "source": source, "name": name, "mime_import": mime_import,
            "mime_target": mime_target, "parent_folder_id": parent_folder_id,
            "id": file_id,
        })
        return {"id": file_id,
                "link": "https://docs.google.com/document/d/%s/edit" % file_id}

    def set_permission(self, file_id, role, type_):
        if self.fail_on == "permission":
            raise RD.DriveDeliveryError(self.fail_message)
        self.permissions.append({"file_id": file_id, "role": role, "type": type_})
        if self.inherited_permission:
            return {"permission_id": None, "inherited": True}
        return {"permission_id": "perm-%s" % file_id, "inherited": False}


class DriveDeliveryTestBase(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in _GOOGLE_ENVS}
        for key in _GOOGLE_ENVS:
            os.environ.pop(key, None)
        self._saved_factory = RD._make_transport
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.manifest_path = self.tmp / "manifest.json"
        self.manifest_path.write_text(json.dumps(MANIFEST), encoding="utf-8")
        self.out_dir = self.tmp / "out"

    def tearDown(self):
        RD._make_transport = self._saved_factory
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _install_fake_sa(self):
        """Point the Skill 14 key env at a valid service-account shape."""
        key_path = self.tmp / "gcp-service-account.json"
        key_path.write_text(json.dumps(FAKE_SA), encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)
        os.environ["GCP_IMPERSONATE_USER"] = "shows@example.com"
        return key_path

    def _render(self, extra_args=()):
        """Run the render subcommand. Returns (exit_code, plan, stderr_text)."""
        argv = ["render", "--manifest", str(self.manifest_path),
                "--out-dir", str(self.out_dir), "--force-destination", "google"]
        argv.extend(extra_args)
        err = io.StringIO()
        out = io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            code = RD.main(argv)
        plan_files = sorted(self.out_dir.glob("*-documents-plan.json"))
        self.assertEqual(len(plan_files), 1, "exactly one plan file is written")
        plan = json.loads(plan_files[0].read_text(encoding="utf-8"))
        return code, plan, err.getvalue()


class CredentialsAbsentTest(DriveDeliveryTestBase):
    """Case 1: no Skill 14 credentials -> intents only, one skip line, exit 0."""

    def setUp(self):
        super().setUp()
        # Point the key env at a path that does not exist so the Skill 14 default
        # location on a developer box cannot accidentally resolve.
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.tmp / "absent.json")

    def test_plan_stays_intent_only(self):
        code, plan, stderr = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "skipped")
        self.assertFalse(DRIVE(plan)["performed"])
        self.assertFalse(DRIVE(plan)["attempted"])
        self.assertEqual(DRIVE(plan)["documents"], {})
        self.assertNotIn("links", plan)
        for action in plan["actions"]:
            self.assertNotIn("performed", action,
                             "no intent is stamped performed without credentials")
            self.assertNotIn("file_id", action)

    def test_exactly_one_skip_line_naming_both_prerequisites(self):
        # Tier 3: with neither tier configured the operator gets ONE line that
        # names both prerequisites, not one line per tier.
        _, plan, stderr = self._render()
        matches = [ln for ln in stderr.splitlines() if "delivery skipped" in ln]
        self.assertEqual(len(matches), 1, "exactly one skip line, got %r" % matches)
        self.assertIn("14-google-workspace-integration/INSTALL.md", matches[0])
        self.assertIn("Google Workspace (Skill 14", matches[0])
        self.assertIn("Notion", matches[0])
        self.assertIn("NOTION_API_TOKEN", matches[0])
        self.assertEqual(plan["delivery"]["log"], [RD.BOTH_TIERS_SKIP_LINE])

    def test_chain_summary_reports_no_channel(self):
        _, plan, _ = self._render()
        summary = plan["delivery"]
        self.assertIsNone(summary["channel"])
        self.assertFalse(summary["performed"])
        self.assertEqual(summary["status"], "skipped")
        self.assertEqual(summary["documents"], {})
        self.assertEqual(summary["errors"], [])
        self.assertEqual(NOTION(plan)["status"], "skipped")

    def test_missing_impersonated_user_alone_is_not_configured(self):
        self._install_fake_sa()
        os.environ.pop("GCP_IMPERSONATE_USER", None)
        code, plan, stderr = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "skipped")
        self.assertIn("impersonated", DRIVE(plan)["reason"])
        self.assertEqual(DRIVE(plan)["credentials"]["impersonated_user"],
                         "NOT SET")

    def test_malformed_key_file_is_not_configured(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(bad)
        os.environ["GCP_IMPERSONATE_USER"] = "shows@example.com"
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "skipped")
        self.assertIn("not valid JSON", DRIVE(plan)["reason"])

    def test_deliverables_still_render_without_credentials(self):
        code, _, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(len(list(self.out_dir.glob("*-episode-package.html"))), 1)
        self.assertEqual(len(list(self.out_dir.glob("*-speech-script.txt"))), 1)


class CredentialsPresentTest(DriveDeliveryTestBase):
    """Case 2: credentials resolve -> upload performed, ids recorded, shares set."""

    def setUp(self):
        super().setUp()
        self._install_fake_sa()
        self.transport = FakeTransport()
        RD._make_transport = lambda creds: self.transport

    def test_both_documents_uploaded_and_converted(self):
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.transport.uploads), 2)
        targets = {u["mime_target"] for u in self.transport.uploads}
        self.assertEqual(targets, {"application/vnd.google-apps.document"},
                         "both documents are converted to Google Docs")
        imports = sorted(u["mime_import"] for u in self.transport.uploads)
        self.assertEqual(imports, ["text/html", "text/plain"])
        for upload in self.transport.uploads:
            self.assertTrue(Path(upload["source"]).is_file(),
                            "the upload source is a file that was actually rendered")

    def test_permission_set_on_both_documents(self):
        _, plan, _ = self._render()
        self.assertEqual(len(self.transport.permissions), 2)
        for perm in self.transport.permissions:
            self.assertEqual(perm["role"], "writer")
            self.assertEqual(perm["type"], "anyone")
        shared = {p["file_id"] for p in self.transport.permissions}
        uploaded = {u["id"] for u in self.transport.uploads}
        self.assertEqual(shared, uploaded,
                         "every uploaded document is the one that gets shared")

    def test_intents_stamped_performed_with_ids(self):
        _, plan, _ = self._render()
        uploads = [a for a in plan["actions"] if a["action"] == "drive.upload_convert"]
        perms = [a for a in plan["actions"] if a["action"] == "drive.set_permission"]
        self.assertEqual(len(uploads), 2)
        self.assertEqual(len(perms), 2)
        for action in uploads:
            self.assertTrue(action["performed"])
            self.assertTrue(action["file_id"])
            self.assertTrue(action["link"].startswith("https://"))
        for action in perms:
            self.assertTrue(action["performed"])
            self.assertTrue(action["permission_id"])
            self.assertFalse(action["inherited_permission"])

    def test_links_recorded_for_steps_16_and_17(self):
        _, plan, _ = self._render()
        self.assertIn("links", plan)
        self.assertIn("package_doc", plan["links"])
        self.assertIn("speech_doc", plan["links"])
        for value in plan["links"].values():
            self.assertTrue(value.startswith("https://"))
        documents = DRIVE(plan)["documents"]
        self.assertEqual(sorted(documents), ["package_doc", "speech_doc"])
        for record in documents.values():
            self.assertTrue(record["file_id"])
            self.assertTrue(record["link"].startswith("https://"))

    def test_delivery_status_and_exit_code(self):
        code, plan, stderr = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "performed")
        self.assertTrue(DRIVE(plan)["performed"])
        self.assertTrue(DRIVE(plan)["attempted"])
        self.assertEqual(DRIVE(plan)["errors"], [])
        self.assertIn("drive delivery performed", stderr)
        summary = plan["delivery"]
        self.assertEqual(summary["channel"], "google_drive")
        self.assertTrue(summary["performed"])
        self.assertEqual(summary["status"], "performed")
        self.assertNotIn("notion", summary["tiers"],
                         "Notion is never consulted once Drive delivered")

    def test_root_folder_env_is_honored(self):
        os.environ[RD.DRIVE_ROOT_FOLDER_ENV] = "folder-abc123"
        _, plan, _ = self._render()
        for upload in self.transport.uploads:
            self.assertEqual(upload["parent_folder_id"], "folder-abc123")
        self.assertEqual(DRIVE(plan)["credentials"]["root_folder"],
                         "SET (%s)" % RD.DRIVE_ROOT_FOLDER_ENV)

    def test_no_root_folder_means_no_parent(self):
        _, plan, _ = self._render()
        for upload in self.transport.uploads:
            self.assertIsNone(upload["parent_folder_id"])
        self.assertEqual(DRIVE(plan)["credentials"]["root_folder"], "NOT SET")

    def test_no_deliver_flag_keeps_intent_only(self):
        code, plan, _ = self._render(extra_args=["--no-deliver"])
        self.assertEqual(code, 0)
        self.assertEqual(self.transport.uploads, [])
        self.assertEqual(self.transport.permissions, [])
        self.assertEqual(plan["delivery"]["status"], "disabled")
        self.assertEqual(plan["delivery"]["tiers"], {},
                         "no tier is even consulted under --no-deliver")

    def test_inherited_permission_is_not_an_error(self):
        self.transport.inherited_permission = True
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "performed")
        self.assertEqual(DRIVE(plan)["errors"], [])
        perms = [a for a in plan["actions"] if a["action"] == "drive.set_permission"]
        for action in perms:
            self.assertTrue(action["performed"])
            self.assertTrue(action["inherited_permission"])


class DriveErrorTest(DriveDeliveryTestBase):
    """Case 3: a Drive API error -> episode continues, error recorded, exit 0."""

    def setUp(self):
        super().setUp()
        self._install_fake_sa()

    def test_upload_failure_does_not_fail_the_episode(self):
        transport = FakeTransport(fail_on="upload",
                                  fail_message="Drive upload returned HTTP 503")
        RD._make_transport = lambda creds: transport
        code, plan, stderr = self._render()
        self.assertEqual(code, 0, "a Drive error never changes the exit code")
        self.assertEqual(DRIVE(plan)["status"], "error")
        self.assertFalse(DRIVE(plan)["performed"])
        self.assertTrue(DRIVE(plan)["errors"])
        self.assertIn("HTTP 503", " ".join(DRIVE(plan)["errors"]))
        self.assertIn("drive delivery failed", stderr)
        self.assertEqual(plan["delivery"]["status"], "error")
        self.assertIsNone(plan["delivery"]["channel"])

    def test_upload_failure_leaves_the_local_deliverables_intact(self):
        transport = FakeTransport(fail_on="upload")
        RD._make_transport = lambda creds: transport
        self._render()
        self.assertEqual(len(list(self.out_dir.glob("*-episode-package.html"))), 1)
        self.assertEqual(len(list(self.out_dir.glob("*-speech-script.txt"))), 1)

    def test_permission_failure_keeps_the_uploaded_ids(self):
        transport = FakeTransport(fail_on="permission",
                                  fail_message="Drive permission returned HTTP 403")
        RD._make_transport = lambda creds: transport
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "partial")
        self.assertTrue(DRIVE(plan)["performed"],
                        "the documents that did upload are still recorded")
        self.assertEqual(sorted(DRIVE(plan)["documents"]),
                         ["package_doc", "speech_doc"])
        self.assertEqual(len(DRIVE(plan)["errors"]), 2)
        perms = [a for a in plan["actions"] if a["action"] == "drive.set_permission"]
        for action in perms:
            self.assertFalse(action["performed"])
            self.assertIn("HTTP 403", action["error"])

    def test_transport_construction_failure_is_recorded(self):
        def boom(creds):
            raise RD.DriveDeliveryError("openssl CLI is not available")
        RD._make_transport = boom
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(DRIVE(plan)["status"], "error")
        self.assertIn("transport unavailable", " ".join(DRIVE(plan)["errors"]))

    def test_error_text_is_one_line_and_bounded(self):
        transport = FakeTransport(fail_on="upload",
                                  fail_message="line one\nline two " + ("x" * 500))
        RD._make_transport = lambda creds: transport
        _, plan, _ = self._render()
        for err in DRIVE(plan)["errors"]:
            self.assertNotIn("\n", err)
            self.assertLessEqual(len(err), 240)


class CredentialResolutionTest(DriveDeliveryTestBase):
    """The Skill 14 contract itself: names, precedence, and secrecy."""

    def test_only_skill_14_env_names_are_consulted(self):
        self.assertEqual(RD.SA_KEY_ENVS,
                         ("GOOGLE_APPLICATION_CREDENTIALS",
                          "GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"))
        self.assertEqual(RD.IMPERSONATE_ENVS,
                         ("GCP_IMPERSONATE_USER", "GWS_ACCOUNT"))
        self.assertEqual(RD.SA_DEFAULT_PATH, "~/clawd/secrets/gcp-service-account.json")

    def test_workspace_cli_credentials_file_also_resolves(self):
        key_path = self.tmp / "sa.json"
        key_path.write_text(json.dumps(FAKE_SA), encoding="utf-8")
        os.environ["GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE"] = str(key_path)
        os.environ["GWS_ACCOUNT"] = "shows@example.com"
        creds = RD.resolve_drive_credentials()
        self.assertTrue(creds["resolved"])
        self.assertEqual(creds["service_account_key"],
                         "SET (GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE)")
        self.assertEqual(creds["impersonated_user"], "SET (GWS_ACCOUNT)")

    def test_full_drive_scope_is_requested(self):
        # Domain-wide delegation rejects drive.file and drive.readonly for this
        # grant with unauthorized_client; only the full Drive scope works.
        self.assertEqual(RD.DRIVE_SCOPE, "https://www.googleapis.com/auth/drive")

    def test_public_report_carries_no_secret(self):
        self._install_fake_sa()
        creds = RD.resolve_drive_credentials()
        self.assertTrue(creds["resolved"])
        public = RD.public_credential_report(creds)
        self.assertNotIn("_sa", public)
        self.assertNotIn("_subject", public)
        blob = json.dumps(public)
        self.assertNotIn("BEGIN PRIVATE KEY", blob)
        self.assertNotIn("shows@example.com", blob)
        self.assertNotIn(FAKE_SA["client_email"], blob)

    def test_plan_file_carries_no_secret(self):
        self._install_fake_sa()
        RD._make_transport = lambda creds: FakeTransport()
        _, plan, stderr = self._render()
        blob = json.dumps(plan)
        self.assertNotIn("BEGIN PRIVATE KEY", blob)
        self.assertNotIn("shows@example.com", blob)
        self.assertNotIn(FAKE_SA["client_email"], blob)
        self.assertNotIn("shows@example.com", stderr)


class GwsBinaryIsNeverInvokedTest(unittest.TestCase):
    """A bare headless gws call self-wipes the default credential store.

    The delivery path therefore speaks Drive REST directly and must not shell out
    to gws anywhere. Detection may still look for gws on PATH, which reads nothing
    and runs nothing.
    """

    @staticmethod
    def _argv_lists(tree):
        """Every list/tuple literal of plain strings passed as a call argument."""
        import ast
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for arg in list(node.args) + [kw.value for kw in node.keywords]:
                if not isinstance(arg, (ast.List, ast.Tuple)):
                    continue
                items = [e.value for e in arg.elts
                         if isinstance(e, ast.Constant) and isinstance(e.value, str)]
                if items:
                    yield items

    def test_no_call_executes_the_gws_binary(self):
        import ast
        tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
        for items in self._argv_lists(tree):
            self.assertNotEqual(
                Path(items[0]).name, "gws",
                "render_documents.py must never execute the gws binary: %r" % items)

    def test_the_only_gws_literal_is_the_path_lookup(self):
        import ast
        tree = ast.parse(_SCRIPT.read_text(encoding="utf-8"))
        gws_calls = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for arg in node.args:
                if isinstance(arg, ast.Constant) and arg.value == "gws":
                    gws_calls.append(ast.unparse(node.func))
        self.assertEqual(gws_calls, ["shutil.which"],
                         "the bare string gws may only reach shutil.which, which "
                         "runs nothing; got %r" % gws_calls)


class NoEmDashTest(unittest.TestCase):
    """House rule: zero em dash characters anywhere in the shipped source.

    The character is built from its codepoint so this file does not itself
    contain the literal it forbids.
    """

    EM_DASH = chr(0x2014)

    def test_source_has_no_em_dash(self):
        self.assertNotIn(self.EM_DASH, _SCRIPT.read_text(encoding="utf-8"))

    def test_test_file_has_no_em_dash(self):
        self.assertNotIn(self.EM_DASH, _HERE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

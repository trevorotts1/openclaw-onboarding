#!/usr/bin/env python3
# =============================================================================
# SKILL 58 - PODCAST PRODUCTION ENGINE :: Step 12 Notion fallback (tier 2)
# -----------------------------------------------------------------------------
# Stdlib unittest only, fully offline. The Notion HTTP layer is injected, so no
# socket is ever opened and no real workspace is touched.
#
# The delivery chain Step 12 runs:
#   Tier 1  Google Drive through the client's Skill 14 credentials
#   Tier 2  the client's OWN Notion workspace, when Drive is absent or failed
#   Tier 3  intent-only plus ONE log line naming both prerequisites
#
# What these tests hold down:
#   1. Neither tier configured  -> intent-only, one log line naming BOTH.
#   2. Drive absent, Notion present -> an episode page is created with the
#      properties block and the rendered blocks, and the chain records its url.
#   3. Drive present -> Drive wins and the Notion transport is never constructed.
#   4. A Notion API error -> the episode continues, the error is recorded, and
#      the exit code is unchanged.
#
# Plus the repo's standing Notion rules, taken from
# 37-zhc-closeout/scripts/ensure-notion-parent-page.sh and
# 38-conversational-ai-system/references/notion-client-doc-standard.md:
# the client's own token and an EXPLICIT client-owned parent page are both
# required, the agency token and agency parent are refused, re-running an episode
# updates its page instead of duplicating it, block appends are chunked at the
# API's 100-children limit, and the published audio is LINKED because the Notion
# API cannot upload a file.
# Run:  python3 -m unittest 58-podcast-production-engine/scripts/tests/test_render_documents_notion_fallback.py
# =============================================================================
"""Deterministic offline tests for the Step 12 Notion fallback."""

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
    spec = importlib.util.spec_from_file_location("render_documents_notion", str(_SCRIPT))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


RD = _load_module()

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
    "description": "What ninety days of one kept promise actually looks like.",
    "podbean_url": "https://example-podbean.test/episodes/quiet-compounding",
    "research": {
        "key_takeaways": ["Consistency beats intensity", "Track the streak, not the mood"],
        "power_statements": ["The streak is the strategy"],
        "case_studies": [
            {"title": "The ninety day ledger",
             "summary": "One founder logged a single action daily for a quarter.",
             "source": "https://example-research.test/ledger"},
        ],
        "findings": ["Daily logging raised follow through"],
        "sources": ["https://example-research.test/ledger"],
    },
    "speech_script": (
        "Welcome back to the show.\n"
        "Today we look at what happens when you keep a promise to yourself "
        "for ninety days straight.\n"
        "The result is rarely dramatic on any single day.\n"
    ),
}

_ALL_ENVS = (
    RD.SA_KEY_ENVS + RD.IMPERSONATE_ENVS + (RD.DRIVE_ROOT_FOLDER_ENV,)
    + RD.NOTION_TOKEN_ENVS + RD.NOTION_PARENT_ENVS
    + (RD.NOTION_AGENCY_TOKEN_ENV, RD.NOTION_AGENCY_PARENT_ENV, RD.NOTION_VERSION_ENV)
)


class FakeNotion:
    """Records every Notion call. Optionally fails one of them.

    Models the parts of the API the delivery path uses: a direct-children listing
    keyed by parent, page creation, block appends, and block deletes.
    """

    def __init__(self, fail_on=None, fail_message="notion is unhappy",
                 existing=None):
        self.calls = []
        self.fail_on = fail_on
        self.fail_message = fail_message
        # {parent_id: {title: page_id}}
        self.children = dict(existing or {})
        self.blocks = {}
        self.deleted = []
        self._seq = 0

    def _maybe_fail(self, name):
        if self.fail_on == name:
            raise RD.NotionDeliveryError(self.fail_message)

    def find_child_page(self, parent_id, title):
        self.calls.append(("find", parent_id, title))
        self._maybe_fail("find")
        return self.children.get(parent_id, {}).get(title)

    def create_page(self, parent_id, title, blocks):
        self.calls.append(("create", parent_id, title, len(blocks)))
        self._maybe_fail("create")
        self._seq += 1
        page_id = "page-%d" % self._seq
        self.children.setdefault(parent_id, {})[title] = page_id
        self.blocks[page_id] = list(blocks)
        return {"id": page_id, "url": "https://www.notion.so/%s" % page_id}

    def append_blocks(self, page_id, blocks):
        self.calls.append(("append", page_id, len(blocks)))
        self._maybe_fail("append")
        self.blocks.setdefault(page_id, []).extend(blocks)

    def clear_children(self, page_id):
        self.calls.append(("clear", page_id))
        self._maybe_fail("clear")
        self.deleted.append(page_id)
        self.blocks[page_id] = []

    def update_page(self, page_id, blocks):
        self.calls.append(("update", page_id, len(blocks)))
        self._maybe_fail("update")
        self.clear_children(page_id)
        self.append_blocks(page_id, blocks)
        return {"id": page_id, "url": "https://www.notion.so/%s" % page_id}


class ChainTestBase(unittest.TestCase):
    def setUp(self):
        self._saved_env = {k: os.environ.get(k) for k in _ALL_ENVS}
        for key in _ALL_ENVS:
            os.environ.pop(key, None)
        # A path that does not exist, so a developer box's real Skill 14 default
        # key location can never resolve tier 1 by accident.
        self._saved_drive_factory = RD._make_transport
        self._saved_notion_factory = RD._make_notion_transport
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(self.tmp / "absent.json")
        self.manifest_path = self.tmp / "manifest.json"
        self.manifest_path.write_text(json.dumps(MANIFEST), encoding="utf-8")
        self.out_dir = self.tmp / "out"

    def tearDown(self):
        RD._make_transport = self._saved_drive_factory
        RD._make_notion_transport = self._saved_notion_factory
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._tmp.cleanup()

    def _enable_notion(self, token="client-test-token", parent="client-parent"):
        os.environ["NOTION_API_TOKEN"] = token
        os.environ["NOTION_PODCAST_PARENT"] = parent

    def _enable_drive(self):
        key_path = self.tmp / "gcp-service-account.json"
        key_path.write_text(json.dumps(FAKE_SA), encoding="utf-8")
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(key_path)
        os.environ["GCP_IMPERSONATE_USER"] = "shows@example.com"

    def _render(self, extra_args=()):
        argv = ["render", "--manifest", str(self.manifest_path),
                "--out-dir", str(self.out_dir), "--force-destination", "google"]
        argv.extend(extra_args)
        err, out = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(out):
            code = RD.main(argv)
        plan_files = sorted(self.out_dir.glob("*-documents-plan.json"))
        self.assertEqual(len(plan_files), 1)
        return code, json.loads(plan_files[0].read_text(encoding="utf-8")), err.getvalue()


class NeitherTierConfiguredTest(ChainTestBase):
    """Case 1: no Drive and no Notion -> intent-only, one line naming both."""

    def test_intent_only_and_one_combined_log_line(self):
        code, plan, stderr = self._render()
        self.assertEqual(code, 0)
        summary = plan["delivery"]
        self.assertEqual(summary["status"], "skipped")
        self.assertIsNone(summary["channel"])
        self.assertEqual(summary["documents"], {})
        self.assertEqual(summary["log"], [RD.BOTH_TIERS_SKIP_LINE])
        lines = [ln for ln in stderr.splitlines() if "delivery skipped" in ln]
        self.assertEqual(len(lines), 1, "one line, not one per tier: %r" % lines)
        self.assertIn("Skill 14", lines[0])
        self.assertIn("NOTION_API_TOKEN", lines[0])
        for action in plan["actions"]:
            self.assertNotIn("performed", action)

    def test_deliverables_still_render(self):
        self._render()
        self.assertEqual(len(list(self.out_dir.glob("*-episode-package.html"))), 1)
        self.assertEqual(len(list(self.out_dir.glob("*-speech-script.txt"))), 1)


class NotionFallbackTest(ChainTestBase):
    """Case 2: Drive absent, Notion present -> the page is written."""

    def setUp(self):
        super().setUp()
        self._enable_notion()
        self.notion = FakeNotion()
        RD._make_notion_transport = lambda creds: self.notion

    def test_episode_page_created_under_a_podcast_episodes_parent(self):
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        creates = [c for c in self.notion.calls if c[0] == "create"]
        self.assertEqual(len(creates), 2, "the episodes parent, then the episode")
        self.assertEqual(creates[0][1], "client-parent")
        self.assertEqual(creates[0][2], RD.NOTION_EPISODES_PAGE_TITLE)
        self.assertEqual(creates[1][2], MANIFEST["title"])
        self.assertEqual(RD.NOTION_EPISODES_PAGE_TITLE, "Podcast Episodes")

    def test_chain_records_the_url_and_channel(self):
        _, plan, stderr = self._render()
        summary = plan["delivery"]
        self.assertEqual(summary["channel"], "notion")
        self.assertTrue(summary["performed"])
        self.assertEqual(summary["status"], "performed")
        page = summary["documents"]["episode_page"]
        self.assertTrue(page["page_id"])
        self.assertTrue(page["url"].startswith("https://www.notion.so/"))
        self.assertEqual(plan["links"]["episode_page"], page["url"])
        self.assertIn("notion delivery performed", stderr)

    def test_intent_marked_performed_with_channel_notion(self):
        # Force the Notion-shaped plan so the notion.create_page intents exist.
        _, plan, _ = self._render(extra_args=[])
        # The forced destination is google, so stamp-through is proven on the
        # notion-destination plan instead.
        argv_plan = self._render_notion_destination()
        notion_actions = [a for a in argv_plan["actions"]
                          if a["action"] == "notion.create_page"]
        self.assertTrue(notion_actions)
        for action in notion_actions:
            self.assertTrue(action["performed"])
            self.assertEqual(action["channel"], "notion")
            self.assertTrue(action["page_id"])
            self.assertTrue(action["url"].startswith("https://www.notion.so/"))

    def _render_notion_destination(self):
        out = self.tmp / "out-notion"
        argv = ["render", "--manifest", str(self.manifest_path),
                "--out-dir", str(out), "--force-destination", "notion"]
        err, sout = io.StringIO(), io.StringIO()
        with redirect_stderr(err), redirect_stdout(sout):
            code = RD.main(argv)
        self.assertEqual(code, 0)
        plan_files = sorted(out.glob("*-documents-plan.json"))
        return json.loads(plan_files[0].read_text(encoding="utf-8"))

    def test_properties_block_carries_title_date_style_and_audio_link(self):
        self._render()
        page_id = self.notion.children["page-1"][MANIFEST["title"]]
        blocks = self.notion.blocks[page_id]
        text = json.dumps(blocks)
        self.assertIn("Episode properties", text)
        self.assertIn(MANIFEST["title"], text)
        self.assertIn(MANIFEST["style"], text)
        # The date is today's UTC date in ISO form.
        from datetime import datetime, timezone
        self.assertIn(datetime.now(timezone.utc).strftime("%Y-%m-%d"), text)
        # The Notion API cannot upload a file, so the audio is a LINK.
        self.assertIn(MANIFEST["podbean_url"], text)
        links = [b for b in blocks
                 if any(r.get("text", {}).get("link") for r in b[b["type"]]["rich_text"])]
        self.assertTrue(links, "the published audio is carried as a link")

    def test_blocks_carry_headings_bullets_and_the_speech_script(self):
        self._render()
        page_id = self.notion.children["page-1"][MANIFEST["title"]]
        kinds = {b["type"] for b in self.notion.blocks[page_id]}
        self.assertIn("heading_2", kinds)
        self.assertIn("bulleted_list_item", kinds)
        self.assertIn("paragraph", kinds)
        text = json.dumps(self.notion.blocks[page_id])
        self.assertIn("Speech Script", text)
        self.assertIn("Welcome back to the show.", text)
        self.assertIn("Key takeaways", text)

    def test_rerun_updates_the_same_page_and_never_duplicates(self):
        self._render()
        first_creates = len([c for c in self.notion.calls if c[0] == "create"])
        self.notion.calls.clear()
        # A second Step 12 run for the same episode.
        import shutil
        shutil.rmtree(self.out_dir)
        self._render()
        creates = [c for c in self.notion.calls if c[0] == "create"]
        updates = [c for c in self.notion.calls if c[0] == "update"]
        self.assertEqual(creates, [], "no page is created a second time")
        self.assertEqual(len(updates), 1, "the existing episode page is updated")
        self.assertEqual(first_creates, 2)
        titles = self.notion.children["page-1"]
        self.assertEqual(len(titles), 1, "exactly one page per episode title")

    def test_drive_skip_line_precedes_the_notion_attempt(self):
        _, plan, stderr = self._render()
        self.assertIn(RD.SKIP_LINE, plan["delivery"]["log"][0])
        self.assertEqual(RD.DRIVE_TIER_ORDER, ("google_drive", "notion"))


class DriveWinsTest(ChainTestBase):
    """Case 3: Drive configured -> Drive delivers and Notion is never called."""

    def setUp(self):
        super().setUp()
        self._enable_drive()
        self._enable_notion()
        self.notion_built = []

        def _never(creds):
            self.notion_built.append(creds)
            raise AssertionError("the Notion tier must not be reached")

        RD._make_notion_transport = _never

        class Drive:
            def __init__(self):
                self.n = 0

            def upload_convert(self, source, name, mime_import, mime_target,
                               parent_folder_id=None):
                self.n += 1
                return {"id": "f%d" % self.n,
                        "link": "https://docs.google.com/document/d/f%d/edit" % self.n}

            def set_permission(self, file_id, role, type_):
                return {"permission_id": "p-%s" % file_id, "inherited": False}

        RD._make_transport = lambda creds: Drive()

    def test_drive_delivers_and_notion_is_not_constructed(self):
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertEqual(plan["delivery"]["channel"], "google_drive")
        self.assertEqual(self.notion_built, [],
                         "the Notion transport is never even built")
        self.assertNotIn("notion", plan["delivery"]["tiers"])
        self.assertIn("package_doc", plan["links"])


class NotionErrorTest(ChainTestBase):
    """Case 4: a Notion API error -> episode continues, error recorded, exit 0."""

    def setUp(self):
        super().setUp()
        self._enable_notion()

    def _with(self, notion):
        RD._make_notion_transport = lambda creds: notion

    def test_create_failure_does_not_fail_the_episode(self):
        notion = FakeNotion(fail_on="create",
                            fail_message="Notion /v1/pages returned HTTP 502")
        self._with(notion)
        code, plan, stderr = self._render()
        self.assertEqual(code, 0, "a Notion error never changes the exit code")
        summary = plan["delivery"]
        self.assertEqual(summary["status"], "error")
        self.assertIsNone(summary["channel"])
        self.assertIn("HTTP 502", " ".join(summary["errors"]))
        self.assertEqual(summary["tiers"]["notion"]["status"], "error")

    def test_local_deliverables_survive_a_notion_error(self):
        self._with(FakeNotion(fail_on="create"))
        self._render()
        self.assertEqual(len(list(self.out_dir.glob("*-episode-package.html"))), 1)
        self.assertEqual(len(list(self.out_dir.glob("*-speech-script.txt"))), 1)

    def test_transport_construction_failure_is_recorded(self):
        def boom(creds):
            raise RD.NotionDeliveryError("integration token rejected")
        RD._make_notion_transport = boom
        code, plan, _ = self._render()
        self.assertEqual(code, 0)
        self.assertIn("transport unavailable",
                      " ".join(plan["delivery"]["tiers"]["notion"]["errors"]))

    def test_error_text_is_one_line_and_bounded(self):
        self._with(FakeNotion(fail_on="create",
                              fail_message="line one\nline two " + ("x" * 500)))
        _, plan, _ = self._render()
        for err in plan["delivery"]["errors"]:
            self.assertNotIn("\n", err)
            self.assertLessEqual(len(err), 240)


class NotionCredentialRulesTest(ChainTestBase):
    """The repo's standing client-ownership rules for Notion."""

    def test_env_names_match_the_repo_convention(self):
        self.assertEqual(RD.NOTION_TOKEN_ENVS[0], "NOTION_API_TOKEN")
        self.assertIn("NOTION_PARENT_PAGE_ID", RD.NOTION_PARENT_ENVS)
        self.assertEqual(RD.NOTION_AGENCY_TOKEN_ENV, "ZHC_AGENCY_NOTION_TOKEN")
        self.assertEqual(RD.NOTION_AGENCY_PARENT_ENV,
                         "ZHC_AGENCY_NOTION_PARENT_PAGE_ID")
        self.assertEqual(RD.NOTION_DEFAULT_VERSION, "2022-06-28")

    def test_token_without_an_explicit_parent_is_not_configured(self):
        os.environ["NOTION_API_TOKEN"] = "client-test-token"
        creds = RD.resolve_notion_credentials()
        self.assertFalse(creds["resolved"])
        self.assertIn("parent page", creds["reason"])

    def test_agency_token_is_refused(self):
        os.environ["NOTION_API_TOKEN"] = "agency-test-token"
        os.environ["NOTION_PODCAST_PARENT"] = "client-parent"
        os.environ[RD.NOTION_AGENCY_TOKEN_ENV] = "agency-test-token"
        creds = RD.resolve_notion_credentials()
        self.assertFalse(creds["resolved"])
        self.assertEqual(creds["token"], "REFUSED (agency token)")
        self.assertIn("agency", creds["reason"])

    def test_agency_parent_is_refused_even_with_dashes(self):
        os.environ["NOTION_API_TOKEN"] = "client-test-token"
        os.environ["NOTION_PODCAST_PARENT"] = "aaaa-bbbb-cccc"
        os.environ[RD.NOTION_AGENCY_PARENT_ENV] = "aaaabbbbcccc"
        creds = RD.resolve_notion_credentials()
        self.assertFalse(creds["resolved"])
        self.assertEqual(creds["parent_page"], "REFUSED (agency parent)")

    def test_public_report_carries_no_token_or_parent_value(self):
        self._enable_notion(token="super-secret-token", parent="private-parent")
        creds = RD.resolve_notion_credentials()
        self.assertTrue(creds["resolved"])
        blob = json.dumps(RD.public_credential_report(creds))
        self.assertNotIn("super-secret-token", blob)
        self.assertNotIn("private-parent", blob)

    def test_plan_and_logs_carry_no_token(self):
        self._enable_notion(token="super-secret-token", parent="private-parent")
        RD._make_notion_transport = lambda creds: FakeNotion()
        _, plan, stderr = self._render()
        blob = json.dumps(plan)
        self.assertNotIn("super-secret-token", blob)
        self.assertNotIn("super-secret-token", stderr)


class MarkdownToNotionBlocksTest(unittest.TestCase):
    """The markdown to Notion block converter, on its own."""

    def test_headings_bullets_and_paragraphs(self):
        blocks = RD.markdown_to_notion_blocks(
            "# One\n## Two\n### Three\n- a bullet\n* another\nplain text\n")
        kinds = [b["type"] for b in blocks]
        self.assertEqual(kinds, ["heading_1", "heading_2", "heading_3",
                                 "bulleted_list_item", "bulleted_list_item",
                                 "paragraph"])

    def test_blank_lines_produce_no_blocks(self):
        self.assertEqual(RD.markdown_to_notion_blocks("\n\n   \n"), [])

    def test_links_become_notion_links(self):
        blocks = RD.markdown_to_notion_blocks(
            "See [the ledger](https://example.test/x) for detail.")
        runs = blocks[0]["paragraph"]["rich_text"]
        linked = [r for r in runs if r["text"].get("link")]
        self.assertEqual(len(linked), 1)
        self.assertEqual(linked[0]["text"]["link"]["url"], "https://example.test/x")
        self.assertEqual(linked[0]["text"]["content"], "the ledger")
        self.assertEqual("".join(r["text"]["content"] for r in runs),
                         "See the ledger for detail.")

    def test_long_text_is_split_into_runs_never_truncated(self):
        body = "y" * 5000
        blocks = RD.markdown_to_notion_blocks(body)
        self.assertEqual(len(blocks), 1)
        runs = blocks[0]["paragraph"]["rich_text"]
        self.assertGreater(len(runs), 1)
        for run in runs:
            self.assertLessEqual(len(run["text"]["content"]), RD.NOTION_MAX_RICH_TEXT)
        self.assertEqual("".join(r["text"]["content"] for r in runs), body)

    def test_block_limit_constant_matches_the_api(self):
        self.assertEqual(RD.NOTION_MAX_BLOCKS_PER_REQUEST, 100)


class BlockChunkingTest(ChainTestBase):
    """Appends are chunked at the API's 100-children-per-request limit."""

    def setUp(self):
        super().setUp()
        self._enable_notion()

    def test_large_page_is_created_then_appended_in_hundreds(self):
        calls = []

        class Recorder(RD.NotionTransport):
            def __init__(self, creds):
                self._token = "t"
                self._version = RD.NOTION_DEFAULT_VERSION

            def _call(self, method, path, body=None, expect=(200,)):
                calls.append((method, path.split("?")[0],
                              len((body or {}).get("children", []))))
                if method == "GET":
                    return {"results": [], "has_more": False}
                if method == "POST" and path == "/v1/pages":
                    return {"id": "page-x", "url": "https://www.notion.so/page-x"}
                return {}

        RD._make_notion_transport = lambda creds: Recorder(creds)
        # 250 blocks forces one create (100) plus two appends (100 + 50).
        transport = Recorder({})
        blocks = RD.markdown_to_notion_blocks("\n".join("line %d" % i for i in range(250)))
        self.assertEqual(len(blocks), 250)
        transport.create_page("parent", "Big", blocks)
        sizes = [c[2] for c in calls if c[0] in ("POST", "PATCH") and c[2]]
        self.assertEqual(sizes, [100, 100, 50])
        self.assertTrue(all(s <= RD.NOTION_MAX_BLOCKS_PER_REQUEST for s in sizes))


class NoEmDashTest(unittest.TestCase):
    """House rule: zero em dash characters in the shipped source."""

    EM_DASH = chr(0x2014)

    def test_source_has_no_em_dash(self):
        self.assertNotIn(self.EM_DASH, _SCRIPT.read_text(encoding="utf-8"))

    def test_test_file_has_no_em_dash(self):
        self.assertNotIn(self.EM_DASH, _HERE.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()

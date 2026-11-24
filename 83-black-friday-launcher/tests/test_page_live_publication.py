"""SWB-094: a page the owner ordered PUBLISHED is sealed as published, only through the owner's approval.

The draft law (test_external_page_install.py) is unchanged: a row with published false still has to be an unpublished
draft, and a row with published true is refused unless its own sealed files hold the owner's live-publication
approval record and a read-back that shows the live version served on its public URL. Every acceptance here has
negative twins on the same instrument: the same assemble, with the one thing that makes the row valid taken away.
"""

from __future__ import annotations

import copy
import hashlib
import json
import shutil
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher_core import checks  # noqa: E402
import test_external_page_install as base  # noqa: E402

APPROVAL_REF = "trevor-live-publish-TEST"
PUBLIC = "https://example.test/black-friday-2026-upsell-1"


def approval(location: str, **over) -> dict:
    doc = {"approval_ref": APPROVAL_REF, "allowed_write_target": "approved_live_publication", "test_only": False,
           "revoked": False, "location_id": location, "page_ids": ["P1", "P2"], "funnel_id": "F1",
           "owner_words": ["finish ALL THE WORK NOW"], "provenance": "operator_written_under_direct_owner_order"}
    doc.update(over)
    return doc


def live_readback(location: str, page_over=None, public_over=None, **top_over) -> dict:
    top = {"pageType": "live", "versionId": base.VERSION, "blob_sha256": base.CONTENT}
    top.update(top_over)
    public = {"url": PUBLIC, "http_status": 200, "sha256": "a" * 64}
    public.update(public_over or {})
    page = {"page_id": "P1", "http_status": 200, "funnelId": "F1", "stepId": "S1", "locationId": location,
            "deleted": False, "top_version": top, "public": public}
    page.update(page_over or {})
    return {"kind": "rest_readback", "unit": "SWB-094", "read_at": "2026-11-24T06:45:07Z",
            "method": "read-only HTTP GET only", "location_id": location, "pages": {base.UNIT: page}}


def live_delivery(run_dir: Path, plan_sha: str, location: str, *, approval_doc=None, back=None, receipt=None,
                  drop=(), extra_approval=False, **facts) -> dict:
    arts = [{**base._write(run_dir, "installs/W30/RECEIPT-upsell_1.json", receipt or base.install_receipt(location)),
             "role": "install_receipt"},
            {**base._write(run_dir, "approvals/live-publish.json", approval_doc or approval(location)),
             "role": "live_publication_approval"},
            {**base._write(run_dir, "readbacks/readback-SWB-094.json", back or live_readback(location)),
             "role": "independent_readback"}]
    if extra_approval:
        arts.append({**base._write(run_dir, "approvals/live-publish-2.json", approval(location)),
                     "role": "live_publication_approval"})
    arts = [a for a in arts if a["role"] not in drop]
    page_install = {"page_id": "P1", "funnel_id": "F1", "step_id": "S1", "location_id": location,
                    "draft_version_id": base.VERSION, "content_sha256": base.CONTENT, "preview_http_status": 200,
                    "published": True, "live_publication_approval_ref": APPROVAL_REF, "public_url": PUBLIC,
                    "public_http_status": 200, "installed_by": "SWB-029", "read_by": "SWB-094"}
    page_install.update(facts)
    return {"state": "complete", "artifacts": arts,
            "lane_validation": {"lane": "Skill 80 install via Skill 06 rail; published by the owner's order; "
                                        "read back by SWB-094", "contract": base.PAGE_CONTRACT, "state": "passed"},
            "request": {"plan_sha256": plan_sha, "request_id": "SWB-029", "input_hash": base.CONTENT},
            "page_install": page_install}


class PageLivePublicationTests(base.ExternalPageInstallTests):
    for _name in dir(base.ExternalPageInstallTests):  # the draft tests are not re-run here
        if _name.startswith("test_"):
            locals()[_name] = None
    del _name

    def with_live(self, **kwargs) -> dict:
        shutil.rmtree(self.run_dir / "lanes" / base.UNIT, ignore_errors=True)
        deliveries = copy.deepcopy(self.deliveries)
        deliveries[base.UNIT] = live_delivery(self.run_dir, self.plan_sha, self.location, **kwargs)
        return deliveries

    # ---- acceptance -------------------------------------------------------------------------------
    def test_a_published_page_with_the_owners_approval_and_a_live_read_back_is_sealed_as_published(self):
        out = self.assemble(self.with_live())
        row = {r["unit_id"]: r for r in out["receipt"]["units"]}[base.UNIT]
        self.assertEqual(row["status"], "published_delivered")
        self.assertEqual(row["proof"], {"authored": True, "draft_installed": True, "tested": False,
                                        "live_verified": True})
        self.assertIs(row["page_install"]["published"], True)
        self.assertEqual(row["page_install"]["live_publication_approval_ref"], APPROVAL_REF)
        self.assertEqual(out["receipt"]["live_effects"], "published_pages:1")
        self.assertEqual(checks.check_package(Path(out["manifest_path"]), self.run_dir), [])

    def test_the_draft_law_is_unchanged_and_a_draft_is_still_labelled_a_draft(self):
        out = self.assemble(self.with_page())
        row = {r["unit_id"]: r for r in out["receipt"]["units"]}[base.UNIT]
        self.assertEqual(row["status"], "draft_delivered")

    # ---- negative twins: the same row with one proof taken away ----------------------------------
    def test_published_true_without_the_approval_record_is_refused(self):
        self.assertIn("not exactly one", self.refused(self.with_live(drop=("live_publication_approval",))))
        self.assertIn("not exactly one", self.refused(self.with_live(extra_approval=True)))
        self.assertIn("live_publication_approval_ref is missing",
                      self.refused(self.with_live(live_publication_approval_ref="")))

    def test_published_true_on_a_draft_shaped_row_is_refused(self):
        deliveries = self.with_page(published=True)  # a draft row that just says published
        self.assertIn("live_publication_approval_ref is missing", self.refused(deliveries))

    def test_an_approval_that_does_not_cover_this_page_is_refused(self):
        loc = self.location
        for name, doc in (("revoked", approval(loc, revoked=True)),
                          ("a test record", approval(loc, test_only=True)),
                          ("another write target", approval(loc, allowed_write_target="workflows_build")),
                          ("another location", approval(loc, location_id="OTHERLOCATION")),
                          ("another page", approval(loc, page_ids=["P9"])),
                          ("another funnel", approval(loc, funnel_id="F9")),
                          ("another ref", approval(loc, approval_ref="trevor-live-publish-OTHER")),
                          ("no owner words", approval(loc, owner_words=[]))):
            with self.subTest(name=name):
                self.assertIn("does not cover this page", self.refused(self.with_live(approval_doc=doc)))

    def test_an_approval_edited_after_it_was_recorded_is_refused(self):
        deliveries = self.with_live()
        path = self.run_dir / "approvals/live-publish.json"
        doc = json.loads(path.read_text())
        doc["page_ids"].append("P-extra")
        path.write_text(json.dumps(doc), encoding="utf-8")
        # the package stages the artifact and refuses bytes that are not the recorded ones
        self.assertIn("does not match its hash", self.refused(deliveries, code="AF-LAUNCH-PKG-HASH"))

    def test_a_read_back_that_does_not_show_this_page_live_is_refused(self):
        loc = self.location
        for name, back in (("a draft top version", live_readback(loc, pageType="draft")),
                           ("another version", live_readback(loc, versionId="00000000-0000-0000-0000-000000000000")),
                           ("another content", live_readback(loc, blob_sha256="0" * 64)),
                           ("a page not served", live_readback(loc, public_over={"http_status": 404})),
                           ("another public url", live_readback(loc, public_over={"url": "https://example.test/x"})),
                           ("a deleted page", live_readback(loc, page_over={"deleted": True})),
                           ("another location", live_readback(loc, page_over={"locationId": "OTHERLOCATION"})),
                           ("another page", live_readback(loc, page_over={"page_id": "P9"})),
                           ("not read by GET", dict(live_readback(loc), method="an edit"))):
            with self.subTest(name=name):
                self.assertIn("does not show this page live", self.refused(self.with_live(back=back)))

    def test_the_read_back_must_be_independent_and_present(self):
        self.assertIn("independent", self.refused(self.with_live(read_by="SWB-029")))
        self.assertIn("not exactly one", self.refused(self.with_live(drop=("independent_readback",))))

    def test_the_public_url_and_status_are_required_facts(self):
        self.assertIn("public_url", self.refused(self.with_live(public_url="http://example.test/x")))
        self.assertIn("public_http_status", self.refused(self.with_live(public_http_status=404)))

    def test_an_installer_receipt_that_does_not_name_the_page_is_refused(self):
        deliveries = self.with_live(receipt=base.install_receipt(self.location, page_id="P9"))
        self.assertIn("names page", self.refused(deliveries))

    def test_check_refuses_a_sealed_published_row_whose_approval_was_edited_after_assembly(self):
        out = self.assemble(self.with_live())
        sealed = [p for p in self.run_dir.rglob("live-publish.json") if "lanes" in p.parts]
        self.assertTrue(sealed)
        doc = json.loads(sealed[0].read_text())
        doc["revoked"] = True
        sealed[0].write_text(json.dumps(doc), encoding="utf-8")
        fails = checks.check_package(Path(out["manifest_path"]), self.run_dir)
        self.assertTrue(fails, "a package whose sealed approval was edited must fail the check")


if __name__ == "__main__":
    unittest.main()

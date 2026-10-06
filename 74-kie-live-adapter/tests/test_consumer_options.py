"""Options the consuming skills need on the shared transport (Skills 25, 37, 58, 59): a download User-Agent,
a result-host allowlist, and saving a direct (sync endpoint) result. Fake transport, no network."""
import json
import os
import tempfile
import unittest

from fakes import K, KEY, MODEL, make, slurp, std_routes
from test_adapter_contract import info

UA = "Mozilla/5.0 test-agent"
PNG = b"\x89PNG\r\n\x1a\nXXXX"


def done(url="https://tempfile.aiquickdraw.com/a.png"):
    return info("success", response={"resultUrls": [url]})


class Options(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def test_user_agent_goes_to_the_result_host_only_never_the_key(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        a.dl_headers = {"User-Agent": UA}
        r = a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertEqual(r["state"], "success")
        dl = [x for x in tr.calls if "aiquickdraw" in x["url"]][0]
        self.assertEqual(dl["headers"], {"User-Agent": UA})
        api = [x for x in tr.calls if "recordInfo" in x["url"]][0]
        self.assertNotIn("User-Agent", api["headers"])
        self.assertEqual(slurp(r["saved_paths"][0], "rb"), PNG)

    def test_default_download_sends_a_product_agent_not_urllibs_and_no_key(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        a.cmd_save("T1", os.path.join(self.tmp, "o"))
        h = [x for x in tr.calls if "aiquickdraw" in x["url"]][0]["headers"]
        self.assertEqual(h, {"User-Agent": K.DOWNLOAD_UA})
        self.assertNotIn("urllib", h["User-Agent"].lower())

    def test_allow_host_skips_others_and_fails_when_none_match(self):
        two = info("success", response={"resultUrls": ["https://static.aiquickdraw.com/a.png", "https://evil.example/b.png"]})
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [two]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        a.dl_hosts = ("aiquickdraw.com",)
        r = a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertEqual(len(r["saved_paths"]), 1)
        self.assertEqual(tr.n("GET", "evil.example"), 0)
        self.assertTrue(any("skipped" in w for w in r["warnings"]))
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done("https://evil.example/x.png")]]])
        a.dl_hosts = ("aiquickdraw.com",)
        r = a.cmd_save("T1", os.path.join(self.tmp, "o2"))
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "host_not_allowed"))
        self.assertEqual(tr.n("GET", "evil.example"), 0)

    def test_allow_host_is_not_a_suffix_trick(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done("https://notaiquickdraw.com/x.png")]]])
        a.dl_hosts = ("aiquickdraw.com",)
        self.assertEqual(a.cmd_save("T1", os.path.join(self.tmp, "o"))["error"]["code"], "host_not_allowed")

    def test_cli_flags_set_options(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        import io
        out = io.StringIO()
        rc = K.main(["save", "--task-id", "T1", "--save-dir", os.path.join(self.tmp, "o"), "--json",
                     "--user-agent", UA, "--allow-host", "aiquickdraw.com"], adapter=a, out=out)
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out.getvalue())["state"], "success")
        self.assertEqual([x for x in tr.calls if "aiquickdraw" in x["url"]][0]["headers"], {"User-Agent": UA})

    def test_refreshed_link_must_be_on_the_allow_list(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(403, b"")]],
                                   ["POST", "download-url", [(200, {"code": 200, "data": "https://evil.example/f.png"})]]])
        a.dl_hosts = ("aiquickdraw.com",)
        r = a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "host_not_allowed"))
        self.assertEqual(tr.n("GET", "evil.example"), 0)

    def test_redirect_off_the_list_or_to_http_is_refused(self):
        import urllib.request
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        a.dl_hosts = ("aiquickdraw.com",)
        a.cmd_save("T1", os.path.join(self.tmp, "o"))
        guard = [x for x in tr.calls if "aiquickdraw" in x["url"]][0]["guard"]
        self.assertTrue(guard("https://static.aiquickdraw.com/b.png"))
        self.assertFalse(guard("https:///x"))
        for bad in ("https://evil.example/b.png", "http://static.aiquickdraw.com/b.png"):
            self.assertFalse(guard(bad), bad)
            h = K._GuardRedirect(guard)
            req = urllib.request.Request("https://tempfile.aiquickdraw.com/a.png")
            with self.assertRaises(urllib.error.HTTPError):
                h.redirect_request(req, None, 302, "Found", {}, bad)
        ok = K._GuardRedirect(guard).redirect_request(
            urllib.request.Request("https://tempfile.aiquickdraw.com/a.png"), None, 302, "Found", {},
            "https://static.aiquickdraw.com/b.png")
        self.assertEqual(ok.full_url, "https://static.aiquickdraw.com/b.png")

    def test_no_allow_list_means_no_guard(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done()]], ["GET", "aiquickdraw.com", [(200, PNG)]]])
        a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertIsNone([x for x in tr.calls if "aiquickdraw" in x["url"]][0]["guard"])

    def test_blank_allow_host_values_are_ignored_and_never_lift_the_list(self):
        import io
        for flags, expect in ((["--allow-host", " ", "--allow-host", "aiquickdraw.com"], 0),
                              (["--allow-host", "", "--allow-host", "  "], 1)):
            a, tr, c = make(self.tmp, [["GET", "recordInfo", [done("https://evil.example/x.png")]]])
            out = io.StringIO()
            K.main(["save", "--task-id", "T1", "--save-dir", os.path.join(self.tmp, "o"), "--json"] + flags,
                   adapter=a, out=out)
            self.assertEqual(tr.n("GET", "evil.example"), 0, flags)
            self.assertEqual(json.loads(out.getvalue())["error"]["code"], "host_not_allowed")

    def test_url_with_no_hostname_is_refused(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [done("https:///x.png")]]])
        r = a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "bad_url"))


SYNC_SCHEMA = {"code": 200, "data": {"model": "runway-x", "openapi": {"paths": {"/api/v1/runway/generate": {"post": {
    "requestBody": {"content": {"application/json": {"schema": {
        "type": "object", "required": ["prompt"], "properties": {"prompt": {"type": "string"}}}}}}}}}}}}


class SyncResult(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def test_run_saves_a_direct_result_from_the_declared_path(self):
        routes = [["GET", "/schema", [(200, SYNC_SCHEMA)]],
                  ["POST", "/api/v1/runway/generate", [(200, {"code": 200, "data": {"resultUrls": ["https://cdn.example/v.mp4"]}})]],
                  ["GET", "cdn.example", [(200, b"VIDEO")]]]
        a, tr, c = make(self.tmp, routes)
        r = a.cmd_run({"model": "runway-x", "input": {"prompt": "p"}}, os.path.join(self.tmp, "o"))
        self.assertEqual((r["state"], r["raw_family"]), ("success", "sync"))
        self.assertEqual(slurp(r["saved_paths"][0], "rb"), b"VIDEO")
        self.assertEqual(tr.n("POST", "createTask"), 0)

    def test_sync_result_nested_under_response(self):
        routes = [["GET", "/schema", [(200, SYNC_SCHEMA)]],
                  ["POST", "/api/v1/runway/generate", [(200, {"code": 200, "data": {"response": {"resultUrls": ["https://cdn.example/v.mp4"]}}})]],
                  ["GET", "cdn.example", [(200, b"VIDEO")]]]
        a, tr, c = make(self.tmp, routes)
        r = a.cmd_run({"model": "runway-x", "input": {"prompt": "p"}}, os.path.join(self.tmp, "o"))
        self.assertEqual(len(r["saved_paths"]), 1)

    def test_sync_without_a_link_is_returned_unchanged(self):
        routes = [["GET", "/schema", [(200, SYNC_SCHEMA)]],
                  ["POST", "/api/v1/runway/generate", [(200, {"code": 200, "data": {"taskId": "R9"}})]]]
        a, tr, c = make(self.tmp, routes)
        r = a.cmd_run({"model": "runway-x", "input": {"prompt": "p"}}, os.path.join(self.tmp, "o"))
        self.assertEqual((r["state"], r["saved_paths"], r["data"]["response"]), ("success", [], {"taskId": "R9"}))


if __name__ == "__main__":
    unittest.main()

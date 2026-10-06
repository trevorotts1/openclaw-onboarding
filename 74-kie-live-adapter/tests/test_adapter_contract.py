import json
import os
import tempfile
import unittest

from fakes import K, KEY, MODEL, fx, make, slurp, std_routes


def info(state, **kw):
    d = {"taskId": "T1", "model": MODEL, "state": state}
    d.update(kw)
    return (200, {"code": 200, "data": d})


class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)


class Catalog(Base):
    def test_discover_filters_locally_and_caches(self):
        a, tr, c = make(self.tmp, std_routes())
        r = a.cmd_discover("image")
        self.assertEqual([m["model"] for m in r["data"]["models"]],
                         [MODEL, "flux-kontext/edit"])
        self.assertEqual(r["data"]["total"], 4)
        self.assertEqual(a.cmd_discover("audio")["data"]["matched"], 1)
        self.assertEqual(a.cmd_discover("video", provider="kling")["data"]["matched"], 1)
        self.assertEqual(a.cmd_discover("any", query="suno")["data"]["matched"], 1)
        self.assertEqual(tr.n("GET", "/api/v1/models"), 1, "one unfiltered fetch, cached")
        self.assertNotIn("?", tr.calls[0]["url"])

    def test_spacing_between_discovery_calls(self):
        a, tr, c = make(self.tmp, std_routes())
        a.cmd_discover("image")
        a.cmd_schema(MODEL)
        self.assertTrue(any(s >= 1.0 for s in c.slept), c.slept)
        gaps = [c.slept[-1]]
        self.assertGreaterEqual(gaps[0], 1.0)

    def test_catalog_ttl_expires(self):
        a, tr, c = make(self.tmp, std_routes())
        a.cmd_discover("image")
        c.t += 6 * 3600 + 1
        a.cmd_discover("image")
        self.assertEqual(tr.n("GET", "/api/v1/models"), 2)


class Http(Base):
    def test_bearer_only(self):
        a, tr, c = make(self.tmp, std_routes())
        a.cmd_credits()
        h = tr.calls[0]["headers"]
        self.assertEqual(h["Authorization"], "Bearer " + KEY)
        self.assertFalse([k for k in h if k.lower() == "apikey"])

    def test_body_code_over_http_200(self):
        for code in (401, 402, 404, 422, 433, 455):
            a, tr, c = make(self.tmp, [["GET", "chat/credit", [(200, {"code": code, "msg": "boom"})]]])
            r = a.cmd_credits()
            self.assertEqual((r["state"], r["error"]["code"]), ("fail", code))
            self.assertEqual(tr.n("GET", "chat/credit"), 1, "401/402/etc are never retried")

    def test_429_retried_then_gives_up(self):
        a, tr, c = make(self.tmp, [["GET", "chat/credit", [(200, {"code": 429, "msg": "slow"})]]])
        r = a.cmd_credits()
        self.assertEqual(r["error"]["code"], 429)
        self.assertEqual(tr.n("GET", "chat/credit"), 3)

    def test_429_then_ok(self):
        a, tr, c = make(self.tmp, [["GET", "chat/credit", [(200, {"code": 429, "msg": "x"}),
                                                          (200, {"code": 200, "data": 5})]]])
        self.assertEqual(a.cmd_credits()["data"]["credits"], 5)

    def test_no_key(self):
        a, tr, c = make(self.tmp, std_routes(), extra_env={"KIE_API_KEY": ""})
        a.key = ""
        self.assertEqual(a.cmd_credits()["error"]["code"], "no_key")
        self.assertEqual(tr.calls, [])

    def test_key_never_in_error_text(self):
        a, tr, c = make(self.tmp, [["GET", "chat/credit", [(200, {"code": 500, "msg": "bad " + KEY})]]])
        self.assertNotIn(KEY, json.dumps(a.cmd_credits()))


class Schema(Base):
    def test_ref_percent_and_trailing_space(self):
        doc = fx("schema_image.json")["data"]["openapi"]
        self.assertEqual(K.deref(doc, "#/components/schemas/Input%20")["required"], ["prompt"])
        with self.assertRaises(K.KieError):
            K.deref(doc, "#/components/schemas/Input")  # no trimming
        path, method, body = K.pick_submit(doc)
        self.assertEqual(path, K.JOB_PATH)
        self.assertIn("prompt", body["properties"]["input"]["properties"])

    def test_validate_required_enum_type(self):
        a, tr, c = make(self.tmp, std_routes())
        ok = a.cmd_validate(MODEL, {"prompt": "hi", "resolution": "1K"})
        self.assertEqual(ok["state"], "validated")
        for bad in ({}, {"prompt": "x", "resolution": "9K"}, {"prompt": 5}, {"prompt": "x", "seed": -1},
                    {"prompt": "x" * 101}):
            r = a.cmd_validate(MODEL, bad)
            self.assertEqual((r["state"], r["error"]["code"]), ("fail", "validation_failed"), bad)

    def test_oneof(self):
        a, tr, c = make(self.tmp, [["GET", "/schema", [(200, fx("schema_oneof.json"))]]])
        self.assertEqual(a.cmd_validate("m/x", {"task_id": "a"})["state"], "validated")
        self.assertEqual(a.cmd_validate("m/x", {"image_url": "u", "prompt": "p"})["state"], "validated")
        self.assertEqual(a.cmd_validate("m/x", {"prompt": "p"})["state"], "fail")
        mixed = a.cmd_validate("m/x", {"task_id": "a", "prompt": "p"})
        self.assertEqual(mixed["state"], "fail")
        self.assertIn("mixes", mixed["error"]["msg"])

    def test_schema_url_slash_not_encoded(self):
        a, tr, c = make(self.tmp, [["GET", "/schema", [(200, fx("schema_oneof.json"))]]])
        a.cmd_schema("wan/v2-2-t2v")
        self.assertTrue(tr.calls[0]["url"].endswith("/api/v1/models/wan/v2-2-t2v/schema"))

    def test_openapi_null(self):
        a, tr, c = make(self.tmp, [["GET", "/schema", [(200, fx("schema_null.json"))]]])
        r = a.cmd_schema("x/y")
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "schema_not_synced"))
        self.assertIn("schema not synced", r["error"]["msg"])

    def test_drift_receipt(self):
        a, tr, c = make(self.tmp, std_routes())
        a.cmd_schema(MODEL)
        c.t += 25 * 3600
        tr.add("GET", "/schema", [(200, {"code": 200, "data": {"model": MODEL, "openapi": {
            "paths": {K.JOB_PATH: {"post": {"requestBody": {"content": {"application/json": {"schema": {"type": "object"}}}}}}}}}})])
        r = a.cmd_schema(MODEL)
        self.assertIn("schema changed since last receipt", r["warnings"])
        rd = os.path.join(self.tmp, "cache", "receipts")
        lines = "".join(slurp(os.path.join(rd, f)) for f in sorted(os.listdir(rd)))
        self.assertIn('"drift": true', lines)
        self.assertNotIn(KEY, lines)


class Submit(Base):
    def test_pinned_model_passed_through(self):
        a, tr, c = make(self.tmp, [["GET", "/schema", [(200, fx("schema_oneof.json"))]],
                                   ["POST", K.JOB_PATH, [(200, {"code": 200, "data": {"taskId": "T9"}})]]])
        r = a.cmd_submit({"model": "Weird/Pinned-Model_X", "input": {"task_id": "a"}, "callBackUrl": "https://cb.example/x"})
        self.assertEqual((r["state"], r["task_id"], r["model_id"]), ("queued", "T9", "Weird/Pinned-Model_X"))
        body = json.loads(next(x for x in tr.calls if x["method"] == "POST")["body"])
        self.assertEqual(body, {"model": "Weird/Pinned-Model_X", "input": {"task_id": "a"}, "callBackUrl": "https://cb.example/x"})

    def test_validation_blocks_dispatch(self):
        a, tr, c = make(self.tmp, std_routes())
        r = a.cmd_submit({"model": MODEL, "input": {}})
        self.assertEqual(r["state"], "fail")
        self.assertEqual(tr.n("POST", "createTask"), 0)

    def test_sync_path_uses_declared_path(self):
        a, tr, c = make(self.tmp, [["GET", "/schema", [(200, fx("schema_sync.json"))]],
                                   ["POST", "/claude/v1/messages", [(200, {"code": 200, "data": {"content": "hi"}})]]])
        r = a.cmd_submit({"model": "claude-x", "input": {"messages": [{"role": "user"}]}})
        self.assertEqual((r["state"], r["raw_family"]), ("success", "sync"))
        self.assertEqual(tr.n("POST", "/claude/v1/messages"), 1)
        self.assertEqual(tr.n("POST", "createTask"), 0)

    def test_network_error_not_retried(self):
        a, tr, c = make(self.tmp, std_routes())
        orig = tr.request

        def boom(method, url, *x, **k):
            if method == "POST":
                tr.calls.append({"method": method, "url": url})
                raise K.KieError("network", "down")
            return orig(method, url, *x, **k)
        tr.request = boom
        r = a.cmd_submit({"model": MODEL, "input": {"prompt": "x"}})
        self.assertEqual(r["state"], "fail")
        self.assertEqual(tr.n("POST", "createTask"), 1)


class Wait(Base):
    def test_state_machine_and_results(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [
            info("waiting"), info("queuing"), info("generating"),
            info("success", creditsConsumed=3.0, response={"resultUrls": ["https://x/a.png"]})]]])
        r = a.cmd_wait("T1", 300)
        self.assertEqual((r["state"], r["result_urls"], r["credits_consumed"]), ("success", ["https://x/a.png"], 3.0))
        self.assertEqual(tr.n("GET", "recordInfo"), 4)
        self.assertEqual(c.slept[0], 3.0)
        self.assertGreater(c.slept[2], c.slept[0], "backs off")

    def test_resultjson_string_fallback(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("success", resultJson='{"resultUrls":["https://x/b.png"]}')]]])
        self.assertEqual(a.cmd_wait("T1")["result_urls"], ["https://x/b.png"])

    def test_suno_shapes(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("success", response={"data": [
            {"audio_url": "https://x/1.mp3", "title": "t"}, {"audio_url": "https://x/2.mp3"}]})]]])
        self.assertEqual(a.cmd_wait("T1")["result_urls"], ["https://x/1.mp3", "https://x/2.mp3"])
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("success", response={"resultObject": {"lyricsData": [{"text": "la"}]}})]]])
        r = a.cmd_wait("T1")
        self.assertEqual(r["result_urls"], [])
        self.assertEqual(r["data"]["result_object"]["lyricsData"][0]["text"], "la")
        self.assertEqual(r["warnings"], [])

    def test_fail_state(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("fail", failCode="500", failMsg="nope")]]])
        r = a.cmd_wait("T1")
        self.assertEqual((r["state"], r["error"]), ("fail", {"code": "500", "msg": "nope"}))

    def test_deadline(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("generating")]]])
        r = a.cmd_wait("T1", timeout=20)
        self.assertEqual((r["state"], r["error"]["code"], r["task_id"]), ("running", "timeout", "T1"))
        self.assertLessEqual(c.t - 1_000_000.0, 20)

    def test_nonzero_code_stops(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [(200, {"code": 404, "msg": "gone"})]]])
        self.assertEqual(a.cmd_wait("T1")["error"]["code"], 404)
        self.assertEqual(tr.n("GET", "recordInfo"), 1)


class Save(Base):
    def test_refresh_on_expired(self):
        d = os.path.join(self.tmp, "out")
        a, tr, c = make(self.tmp, [
            ["GET", "recordInfo", [info("success", response={"resultUrls": ["https://tf.example/old/x.png"]})]],
            ["GET", "https://tf.example/old/", [(403, b"expired")]],
            ["GET", "https://fresh.example/", [(200, b"\x89PNGdata")]],
            ["POST", "/common/download-url", [(200, {"code": 200, "data": "https://fresh.example/new.png"})]]])
        r = a.cmd_save("T1", d)
        self.assertEqual(r["state"], "success")
        self.assertEqual(slurp(r["saved_paths"][0], "rb"), b"\x89PNGdata")
        self.assertEqual(tr.n("POST", "/common/download-url"), 1)
        for call in tr.calls:  # the API key is never sent to result hosts
            if "example" in call["url"]:
                self.assertNotIn("Authorization", call["headers"])

    def test_refresh_only_once(self):
        a, tr, c = make(self.tmp, [
            ["GET", "recordInfo", [info("success", response={"resultUrls": ["https://tf.example/o.png"]})]],
            ["GET", "https://tf.example/", [(404, b"")]],
            ["GET", "https://fresh.example/", [(404, b"")]],
            ["POST", "/common/download-url", [(200, {"code": 200, "data": "https://fresh.example/n.png"})]]])
        r = a.cmd_save("T1", os.path.join(self.tmp, "o"))
        self.assertEqual((r["state"], r["error"]["code"]), ("fail", "download_failed"))
        self.assertEqual(tr.n("POST", "/common/download-url"), 1)

    def test_http_url_refused(self):
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [info("success", response={"resultUrls": ["http://x/o.png"]})]]])
        self.assertEqual(a.cmd_save("T1", self.tmp)["error"]["code"], "bad_url")


class Upload(Base):
    def _file(self, name, size):
        p = os.path.join(self.tmp, name)
        with open(p, "wb") as f:
            f.write(b"\0" * size)
        return p

    def ok(self):
        return {"success": True, "code": 200, "data": {"downloadUrl": "https://tempfile.example/x.png", "fileName": "x.png"}}

    def test_small_uses_base64(self):
        a, tr, c = make(self.tmp, [["POST", "/api/file-", [(200, self.ok())]]])
        r = a.cmd_upload(file=self._file("a.png", 100), upload_path="/images/up/")
        self.assertEqual(r["data"]["upload_method"], "base64")
        self.assertTrue(tr.calls[0]["url"].endswith("/api/file-base64-upload"))
        self.assertIn("kieai.redpandaai.co", tr.calls[0]["url"])
        b = json.loads(tr.calls[0]["body"])
        self.assertEqual(b["uploadPath"], "images/up")
        self.assertTrue(b["base64Data"].startswith("data:image/png;base64,"))
        self.assertTrue(any("expiresAt" in w for w in r["warnings"]))

    def test_large_uses_stream_multipart(self):
        a, tr, c = make(self.tmp, [["POST", "/api/file-", [(200, self.ok())]]])
        r = a.cmd_upload(file=self._file("big.png", K.B64_LIMIT + 1))
        self.assertEqual(r["data"]["upload_method"], "stream")
        self.assertTrue(tr.calls[0]["url"].endswith("/api/file-stream-upload"))
        self.assertTrue(tr.calls[0]["headers"]["Content-Type"].startswith("multipart/form-data; boundary="))

    def test_url_rehost(self):
        a, tr, c = make(self.tmp, [["POST", "/api/file-", [(200, self.ok())]]])
        r = a.cmd_upload(url="https://example.com/p.jpg")
        self.assertEqual(r["data"]["upload_method"], "url")
        self.assertEqual(json.loads(tr.calls[0]["body"])["fileUrl"], "https://example.com/p.jpg")

    def test_rejects_bad_files(self):
        a, tr, c = make(self.tmp, [["POST", "/api/file-", [(200, self.ok())]]])
        for kw in ({"file": self.tmp}, {"file": os.path.join(self.tmp, "nope.png")},
                   {"file": self._file("e.png", 0)}, {"file": self._file("x.exe", 5)}):
            self.assertEqual(a.cmd_upload(**kw)["error"]["code"], "bad_file", kw)
        self.assertEqual(tr.calls, [])

    def test_symlink_resolved(self):
        real = self._file("r.png", 10)
        ln = os.path.join(self.tmp, "ln.png")
        os.symlink(real, ln)
        a, tr, c = make(self.tmp, [["POST", "/api/file-", [(200, self.ok())]]])
        self.assertEqual(a.cmd_upload(file=ln)["state"], "success")


class Health(Base):
    def test_health_and_credits(self):
        a, tr, c = make(self.tmp, std_routes())
        h = a.cmd_health()
        self.assertEqual((h["state"], h["data"]["key"], h["data"]["credits"]), ("success", "SET", 2450))
        self.assertEqual(set(h) >= {"provider", "adapter", "adapter_mode", "backend", "model_id", "capability",
                                    "schema_source", "schema_fetched_at", "task_id", "state", "result_urls",
                                    "saved_paths", "credits_consumed", "warnings", "fallback_used", "raw_family", "error"}, True)
        self.assertEqual((h["provider"], h["adapter"], h["backend"]), ("kie", "74-kie-live-adapter", "native-live"))

    def test_resolver_used_when_env_empty(self):
        a = K.Adapter(env={"HOME": self.tmp}, resolver=lambda s: "from-resolver" if s == "kie" else None)
        self.assertEqual(a.key, "from-resolver")
        self.assertEqual(K.Adapter(env={"HOME": self.tmp}).key, "")  # injected env never reaches the real resolver
        self.assertEqual(K.Adapter(env={"HOME": self.tmp, "KIE_API_KEY": "envwins"}, resolver=lambda s: "r").key, "envwins")


if __name__ == "__main__":
    unittest.main()

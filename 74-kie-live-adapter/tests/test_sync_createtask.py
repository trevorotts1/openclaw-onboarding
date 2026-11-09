"""createTask models that answer SYNCHRONOUSLY (Skill 74 half of bug 4).

ai-music-api/timeStamped-lyrics answers createTask with the finished payload in
`data` (alignedWords) and no taskId. Before this change the adapter called that
`bad_response`, so those models could not be dispatched at all, and the save step
re-queried a local "sync-<hex>" id KIE never had and wrote zero files.

Covers: sync submit returns success with data.response + sync; a URL-less save
writes <save_dir>/<task>_0.json and never re-queries the task; the CLI
`save --info <file>` path; and that a createTask answer with genuinely NOTHING in
it still fails bad_response (the failure code is not weakened into success).
Fake transport, no network, no paid call, no key needed.
"""
import io
import json
import os
import tempfile
import unittest

from fakes import K, KEY, MODEL, fx, make, slurp

OK_INPUT = {"prompt": "a lighthouse at dusk", "resolution": "1K"}

# The shape observed live on ai-music-api/timeStamped-lyrics: the createTask body
# carries the finished payload under data.data (alignedWords, startS/endS) and no
# taskId. This is what the box-local reference diff keys on (data.data).
ALIGNED = {"alignedWords": [{"word": "nobody", "startS": 0.0, "endS": 0.41},
                            {"word": "asks", "startS": 0.41, "endS": 0.66}]}
SYNC_RESPONSE = {"data": dict(ALIGNED, duration=88.0)}
SYNC_DATA = {"code": 200, "msg": "success", "data": SYNC_RESPONSE}

def routes(answer):
    """std_routes() with the createTask answer replaced (schema routes stay first)."""
    return [
        ["GET", "/api/v1/models/gpt-image-2-5-sunburst-text-to-image/schema", [(200, fx("schema_image.json"))]],
        ["GET", "/api/v1/models", [(200, fx("catalog.json"))]],
        ["GET", "/api/v1/chat/credit", [(200, {"code": 200, "msg": "success", "data": 2450})]],
        ["GET", "recordInfo", [(200, {"code": 200, "data": {"taskId": "T1", "state": "success"}})]],
        ["POST", "/api/v1/jobs/createTask", [(200, answer)]],
    ]

class Base(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def save_dir(self, name="out"):
        return os.path.join(self.tmp, name)

class SyncSubmit(Base):
    def test_sync_answer_is_success_not_bad_response(self):
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        r = a.cmd_submit({"model": MODEL, "input": OK_INPUT})
        self.assertEqual(r["state"], "success", r["error"])
        self.assertIsNone(r["task_id"], "there is no job to poll")
        self.assertTrue(r["data"]["sync"])
        self.assertEqual(r["data"]["response"], SYNC_RESPONSE)
        self.assertEqual(r["raw_family"], "market", "it is still the createTask path")
        self.assertEqual(tr.n("GET", "recordInfo"), 0, "never polls a job that does not exist")
        self.assertTrue(any("sync response on createTask" in w for w in r["warnings"]), r["warnings"])

    def test_an_empty_createTask_answer_still_fails_bad_response(self):
        for answer in ({"code": 200, "data": {}},        # nothing at all
                       {"code": 200},                    # no data key
                       {"code": 200, "data": None},      # explicit null
                       {"code": 200, "data": {"taskId": ""}}):  # blank id, no payload
            a, tr, c = make(self.tmp, routes(answer))
            r = a.cmd_submit({"model": MODEL, "input": OK_INPUT})
            self.assertEqual(r["state"], "fail", answer)
            self.assertEqual(r["error"]["code"], "bad_response", answer)
            self.assertIn("createTask returned no taskId", r["error"]["msg"], answer)
            self.assertEqual(r["saved_paths"], [], answer)

class UrlLessSave(Base):
    def _envelope(self, a):
        return a.cmd_submit({"model": MODEL, "input": OK_INPUT})

    def test_url_less_sync_save_writes_task_0_json(self):
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        env = self._envelope(a)
        r = a.cmd_save("sync-abc123", self.save_dir(), info=env)
        self.assertEqual(r["state"], "success", r["error"])
        want = os.path.join(self.save_dir(), "sync-abc123_0.json")
        self.assertEqual(r["saved_paths"], [want])
        self.assertEqual(json.loads(slurp(want)), SYNC_RESPONSE)
        self.assertTrue(any("no file URL" in w for w in r["warnings"]), r["warnings"])
        self.assertEqual(tr.n("GET", "recordInfo"), 0, "a local sync id is never re-queried")

    def test_save_dir_is_created_and_id_is_sanitised(self):
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        deep = os.path.join(self.tmp, "a", "b", "c")
        r = a.cmd_save("sync/../weird id", deep, info=self._envelope(a))
        self.assertEqual(r["state"], "success", r["error"])
        self.assertEqual(r["saved_paths"], [os.path.join(deep, "syncweirdid_0.json")])
        self.assertTrue(os.path.isfile(r["saved_paths"][0]))

    def test_allow_host_is_not_consulted_and_never_blocks_a_url_less_save(self):
        # keep the allow-list intact: it governs downloaded URLs, of which there are none here.
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        a.dl_hosts = ("aiquickdraw.com",)
        r = a.cmd_save("sync-abc123", self.save_dir(), info=self._envelope(a))
        self.assertEqual(r["state"], "success", r["error"])
        self.assertEqual(len(r["saved_paths"]), 1)
        self.assertEqual([x for x in tr.calls if x["method"] == "GET" and "recordInfo" in x["url"]], [])

    def test_a_market_task_without_a_sync_payload_is_untouched(self):
        # info from a QUEUED market task: no data.response, so no document is invented.
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        env = a.result(state="success", task_id="T1", data={})
        r = a.cmd_save("T1", self.save_dir(), info=env)
        self.assertEqual((r["state"], r["saved_paths"]), ("success", []))

class CliSaveInfo(Base):
    def test_cli_save_info_persists_the_submit_envelope(self):
        a, tr, c = make(self.tmp, routes(SYNC_DATA))
        env = a.cmd_submit({"model": MODEL, "input": OK_INPUT})
        info = os.path.join(self.tmp, "sync-info.json")
        with open(info, "w", encoding="utf-8") as f:
            json.dump(env, f, sort_keys=True)
        out = io.StringIO()
        rc = K.main(["save", "--task-id", "sync-deadbeef", "--save-dir", self.save_dir(),
                     "--json", "--info", info], adapter=a, out=out)
        self.assertEqual(rc, 0, out.getvalue())
        r = json.loads(out.getvalue())
        self.assertEqual(r["state"], "success", r["error"])
        self.assertEqual(r["saved_paths"], [os.path.join(self.save_dir(), "sync-deadbeef_0.json")])
        self.assertEqual(json.loads(slurp(r["saved_paths"][0])), SYNC_RESPONSE)
        self.assertEqual(tr.n("GET", "recordInfo"), 0)

    def test_cli_save_without_info_still_re_queries_the_task(self):
        # the old contract is unchanged: no --info means "look the task up".
        a, tr, c = make(self.tmp, [["GET", "recordInfo", [(404, {"code": 404, "msg": "no such task"})]]]
                        + routes(SYNC_DATA))
        out = io.StringIO()
        rc = K.main(["save", "--task-id", "T1", "--save-dir", self.save_dir(), "--json"],
                    adapter=a, out=out)
        self.assertEqual(rc, 1)
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], 404)
        self.assertEqual(tr.n("GET", "recordInfo"), 1)

    def test_cli_output_never_carries_the_key(self):
        loud = {"code": 500, "msg": "upstream said " + KEY}
        a, tr, c = make(self.tmp, routes(loud))
        out = io.StringIO()
        K.main(["submit", "--request", self._req()], adapter=a, out=out)
        self.assertNotIn(KEY, out.getvalue())
        self.assertIn("[REDACTED]", out.getvalue())
        self.assertEqual(json.loads(out.getvalue())["error"]["code"], 500)

    def _req(self):
        p = os.path.join(self.tmp, "req.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"model": MODEL, "input": OK_INPUT}, f)
        return p

if __name__ == "__main__":
    unittest.main()

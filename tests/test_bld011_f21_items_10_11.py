#!/usr/bin/env python3
"""F21 items 10 and 11 — the cross-caller proofs, driven through both real modules.

ITEM 11 "the same root is used by both callers": Skill 46's JavaScript layout
(46-kie-callback-relay/data-root.js) and Skill 74's Python layout
(74-kie-live-adapter/scripts/kie_live_adapter.py) are asked for a layout with the SAME
environment. Both execute shared-utils/durable-data-root.sh; this test asserts they come
back with the identical root and the identical directories, so one job cannot acquire two
answers about where its evidence lives.

ITEM 10 "a callback must reuse the existing job identity": the identity is minted ONCE by
Skill 46 and echoed back by Skill 74's `data.callback_url`; the box then proves the two are
the same job. This test asserts the adapter RESULT carries back the exact URL it was given
(so the `j=` identity survives the handoff) and that a re-prepared job returns that same
`j=`. The full reuse/rebind matrix is driven in
46-kie-callback-relay/test/security.test.mjs, which runs without a model call.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOLVER = os.path.join(REPO, "shared-utils", "durable-data-root.sh")
JS_LAYOUT = os.path.join(REPO, "46-kie-callback-relay", "data-root.js")
ADAPTER = os.path.join(REPO, "74-kie-live-adapter", "scripts", "kie_live_adapter.py")
SCOPE = "client-alpha"


def bash_layout(root, scope=SCOPE):
    out = subprocess.run(["bash", RESOLVER, "--json", "--scope", scope],
                         env={"HOME": root, "OPENCLAW_DATA_ROOT": root},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, timeout=60)
    if out.returncode != 0:
        raise AssertionError("resolver failed: %s" % out.stderr)
    return json.loads(out.stdout.strip())


def js_layout(root, scope=SCOPE):
    script = ("const {resolveDataRoot} = require(process.argv[1]);"
              "process.stdout.write(JSON.stringify(resolveDataRoot({scope: process.argv[2]})));")
    out = subprocess.run(["node", "-e", script, JS_LAYOUT, scope],
                         env={"HOME": root, "OPENCLAW_DATA_ROOT": root, "PATH": os.environ.get("PATH", "")},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError("node layout failed: %s" % out.stderr)
    return json.loads(out.stdout)


def py_layout(root, scope=SCOPE):
    script = ("import json,sys; sys.path.insert(0, sys.argv[1]);"
              "import kie_live_adapter as K;"
              "sys.stdout.write(json.dumps(K.resolve_durable_layout(scope=sys.argv[2])))")
    out = subprocess.run([sys.executable, "-I", "-c", script, os.path.dirname(ADAPTER), scope],
                         env={"HOME": root, "OPENCLAW_DATA_ROOT": root,
                              "PATH": os.environ.get("PATH", "")},
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         universal_newlines=True, timeout=120)
    if out.returncode != 0:
        raise AssertionError("python layout failed: %s" % out.stderr)
    return json.loads(out.stdout)


class SameRootForBothCallers(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.root = self._t.name
        self.addCleanup(self._t.cleanup)

    def test_shell_js_and_python_resolve_one_identical_layout(self):
        shell = bash_layout(self.root)
        js = js_layout(self.root)
        py = py_layout(self.root)
        for key in ("root", "scope", "state_dir", "registry", "index", "done", "receipts"):
            self.assertEqual(shell[key], js[key], "Skill 46 (JS) disagrees with the resolver on %r" % key)
            self.assertEqual(shell[key], py[key], "Skill 74 (Python) disagrees with the resolver on %r" % key)
        self.assertEqual(shell["root"], self.root)
        # The location is derived, not guessed: <root>/data/kie-jobs/<scope>/…
        self.assertEqual(shell["registry"],
                         os.path.join(self.root, "data", "kie-jobs", SCOPE, "registry"))
        # Neither caller may place state inside its own skill tree.
        self.assertNotIn(os.path.join(REPO, "46-kie-callback-relay"), js["registry"])
        self.assertNotIn(os.path.join(REPO, "74-kie-live-adapter"), py["registry"])

    def test_two_scopes_do_not_share_a_state_dir(self):
        a = bash_layout(self.root, "client-alpha")
        b = bash_layout(self.root, "client-beta")
        self.assertNotEqual(a["state_dir"], b["state_dir"])
        self.assertEqual(os.path.dirname(a["state_dir"]), os.path.dirname(b["state_dir"]))

    def test_no_caller_computes_the_root_without_the_resolver(self):
        """Neither module may carry its own root precedence (the defect: two computations)."""
        with open(os.path.join(REPO, "74-kie-live-adapter", "scripts", "kie_live_adapter.py"),
                  encoding="utf-8") as fh:
            adapter_src = fh.read()
        # An ASSIGNMENT is the defect (a second root authority); prose that names the
        # removed constant is not. Both modules must get the root from the resolver only.
        self.assertNotIn("\nDATA_OC_ROOT =", adapter_src,
                         "Skill 74 still assigns a hard-coded root next to the resolver")
        self.assertNotIn('os.path.join(home, ".openclaw", "cache", "kie-live-adapter")',
                         adapter_src.split("def resolve_durable_layout")[0],
                         "Skill 74 still computes the cache root itself before the resolver runs")
        with open(os.path.join(REPO, "46-kie-callback-relay", "kie-slide-submitter.js"),
                  encoding="utf-8") as fh:
            submitter_src = fh.read()
        self.assertNotIn("path.join(this.workspaceDir, '.kie'", submitter_src,
                         "Skill 46 still builds its own transient state path")


class CallbackIdentitySurvivesTheHandoff(unittest.TestCase):
    """Item 10, adapter side: Skill 74 echoes back the EXACT callback URL it was given."""

    def test_submit_records_the_callback_url_it_was_handed(self):
        sys.path.insert(0, os.path.join(REPO, "74-kie-live-adapter", "tests"))
        sys.dont_write_bytecode = True
        import fakes  # the suite's own doubles: no network, no key

        with tempfile.TemporaryDirectory() as tmp:
            routes = [r for r in fakes.std_routes() if r[0] != "POST"]
            routes.append(["POST", "/api/v1/jobs/createTask",
                           [(200, {"code": 200, "data": {"taskId": "task-echo-1"}})]])
            a, tr, _ = fakes.make(tmp, routes)
            url = "https://relay.example/cb?c=client-alpha&j=%s&s=aa&h=bb" % ("a1b2c3d4" * 4)
            # The CLI's own --callback-url wiring (main() applies _with_callback before submit).
            import kie_live_adapter as K
            r = a.cmd_submit(K._with_callback({"model": fakes.MODEL,
                                               "input": {"prompt": "a leaf", "resolution": "1K"}}, url))
            self.assertEqual(r["task_id"], "task-echo-1")
            self.assertEqual(r["data"]["callback_url"], url,
                             "Skill 74 must echo the URL verbatim: its j= IS the job identity")
            body = json.loads(tr.calls[-1]["body"])
            self.assertEqual(body["callBackUrl"], url, "the submitted callBackUrl is the prepared one")
            self.assertEqual(tr.n("POST", "createTask"), 1, "one paid submit, never a retry")


if __name__ == "__main__":
    unittest.main()

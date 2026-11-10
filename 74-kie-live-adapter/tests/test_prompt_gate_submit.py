#!/usr/bin/env python3
"""A3 — the prompt band is enforced INSIDE the Kie submit path, before the HTTP call.

Proof for SCOPE-LEDGER PRMPT-001 #1, #8, #9:
  (a) a 25,000-char prompt is REFUSED with zero createTask calls; and
  (b) a 19,500-char prompt PASSES and is submitted exactly once.

The vendor schema publishes maxLength 32000; the owner cap for gpt-image-2-6 is 20000 and
governs (Trevor 2026-11-08). Both runs therefore go through the real submit path
(`_dispatch` -> `_prompt_gate` -> `POST /api/v1/jobs/createTask`) with the gate ON.

Offline: fake transport, no key, no network, no spend. stdlib only.
Run: (cd tests && HOME="$(mktemp -d)" python3 -m unittest test_prompt_gate_submit -v)
"""
import copy
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)                                   # fakes
from fakes import K, MODEL, fx, make, std_routes  # noqa: E402

VENDOR_MAX = 32000
OWNER_CAP = 20000


def vendor_routes():
    """The standard routes, with the vendor OpenAPI publishing the 32,000 maxLength."""
    doc = copy.deepcopy(fx("schema_image.json"))
    doc["data"]["openapi"]["components"]["schemas"]["Input "]["properties"]["prompt"][
        "maxLength"] = VENDOR_MAX
    routes = std_routes()
    routes[0] = ["GET", "/api/v1/models/" + MODEL + "/schema", [(200, doc)]]
    return routes


class SubmitGate(unittest.TestCase):
    def setUp(self):
        self._t = tempfile.TemporaryDirectory()
        self.tmp = self._t.name
        self.addCleanup(self._t.cleanup)

    def adapter(self):
        # KIE_PROMPT_POLICY_TEST_OFF=0 turns the real gate ON (the shared fixture defaults it off
        # for hermetic transport tests, which use placeholder prompts).
        a, tr, _ = make(self.tmp, vendor_routes(),
                        extra_env={"KIE_PROMPT_POLICY_TEST_OFF": "0"})
        return a, tr

    def test_owner_cap_outranks_the_vendor_figure(self):
        a, _ = self.adapter()
        d = a.cmd_prompt_budget(MODEL)["data"]
        self.assertEqual(d["max"], OWNER_CAP)
        self.assertTrue(str(d["limit_source"]).startswith("owner-ruling"), d["limit_source"])

    def test_a_25000_char_prompt_is_refused_with_zero_submit_calls(self):
        a, tr = self.adapter()
        r = a.cmd_submit({"model": MODEL, "input": {"prompt": "x" * 25000}})
        self.assertEqual(r["state"], "fail", r)
        self.assertEqual((r.get("error") or {}).get("code"), "prompt_above_max", r.get("error"))
        self.assertEqual((r.get("data") or {}).get("prompt_policy", {}).get("ok"), False)
        # THE PROOF: the refusal happened before any paid HTTP call.
        self.assertEqual(tr.n("POST", K.JOB_PATH), 0)
        self.assertFalse(any("createTask" in c["url"] for c in tr.calls))

    def test_b_19500_char_prompt_passes_and_is_submitted_once(self):
        a, tr = self.adapter()
        r = a.cmd_submit({"model": MODEL, "input": {"prompt": "x" * 19500}})
        self.assertEqual(r["state"], "queued", r)
        self.assertTrue(r["data"]["prompt_policy"]["ok"])
        self.assertEqual(tr.n("POST", K.JOB_PATH), 1)


if __name__ == "__main__":
    unittest.main()

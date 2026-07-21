#!/usr/bin/env python3
"""Regression suite for the publish workflow's success response (T0-21).

The success branch of `IF — Episode Created Successfully` fanned out to three
SIBLING nodes in parallel: the Gmail notification, `Respond — Publish Success`,
and `Idempotency — Mark Completed`. The response node had no dependency on the
completion write's outcome, and the completion node carried
`onError: continueRegularOutput`.

So the synchronous webhook returned an OK response asserting a durable successful
publish while the completion row could silently fail to update — leaving the
caller told the publish succeeded and the idempotency record that prevents a
DUPLICATE publish nonexistent.

The fix chains the response BEHIND the completion write and removes the
continue-on-error setting, so the response cannot be produced unless the durable
row landed. These tests pin that ordering as a graph property, read with a real
JSON parser rather than a text search.

NOTE — this file is only half of the fix. A workflow in the repository that is
never imported changes nothing on the running automation host; the paired FLEET
ACTION is to redeploy this workflow. This suite proves the file is right, never
that the host is running it.

Run:
    python3 tests/unit/podbean-publish-workflow-response-ordering.test.py
    or: pytest tests/unit/podbean-publish-workflow-response-ordering.test.py
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

_HERE = Path(__file__).parent
_REPO_ROOT = _HERE.parent.parent
_WF = (_REPO_ROOT / "58-podcast-production-engine" / "config" / "n8n"
       / "podbean-publish.workflow.json")
assert _WF.is_file(), f"workflow not found at {_WF}"

WF = json.loads(_WF.read_text(encoding="utf-8"))

GATE = "IF — Episode Created Successfully"
COMPLETION = "Idempotency — Mark Completed"
RESPONSE = "Respond — Publish Success"
NOTIFY = "Gmail — Success Notification"

CONNECTIONS = WF["connections"]
NODES = {n["name"]: n for n in WF["nodes"]}


def _targets(node_name: str, branch: int = 0):
    main = CONNECTIONS.get(node_name, {}).get("main", [])
    if len(main) <= branch:
        return []
    return [c["node"] for c in main[branch]]


def _reachable(start: str, limit: int = 200):
    seen, stack = set(), [start]
    while stack and len(seen) < limit:
        cur = stack.pop()
        for branch in CONNECTIONS.get(cur, {}).get("main", []):
            for c in branch:
                if c["node"] not in seen:
                    seen.add(c["node"])
                    stack.append(c["node"])
    return seen


class TestWorkflowIsWellFormed(unittest.TestCase):
    def test_the_named_nodes_all_exist(self):
        for name in (GATE, COMPLETION, RESPONSE, NOTIFY):
            with self.subTest(node=name):
                self.assertIn(name, NODES, f"{name} is not in the workflow")

    def test_every_connection_target_names_a_real_node(self):
        missing = sorted(
            {c["node"]
             for conns in CONNECTIONS.values()
             for branch in conns.get("main", [])
             for c in branch
             if c["node"] not in NODES}
        )
        self.assertEqual(missing, [], f"connections point at nodes that do not exist: {missing}")


class TestSuccessResponseIsDownstreamOfTheCompletionWrite(unittest.TestCase):
    def test_the_gate_does_not_answer_the_caller_directly(self):
        self.assertNotIn(
            RESPONSE, _targets(GATE, 0),
            "the success gate still answers the webhook in parallel with the "
            "completion write — the caller can be told the publish succeeded "
            "while the idempotency row never landed",
        )

    def test_the_gate_still_drives_the_completion_write(self):
        self.assertIn(COMPLETION, _targets(GATE, 0))

    def test_the_response_hangs_off_the_completion_write(self):
        self.assertIn(
            RESPONSE, _targets(COMPLETION, 0),
            "the success response is not chained behind the completion write",
        )

    def test_the_response_is_reachable_from_the_gate_only_through_the_write(self):
        without_completion = {
            k: v for k, v in CONNECTIONS.items() if k != COMPLETION
        }
        saved = CONNECTIONS.copy()
        try:
            CONNECTIONS.clear()
            CONNECTIONS.update(without_completion)
            self.assertNotIn(
                RESPONSE, _reachable(GATE),
                "the success response is still reachable without the completion write",
            )
        finally:
            CONNECTIONS.clear()
            CONNECTIONS.update(saved)

    def test_the_notification_is_unchanged(self):
        """The Gmail notification may stay a sibling — it is not a durability claim."""
        self.assertIn(NOTIFY, _targets(GATE, 0))


class TestTheCompletionWriteCannotBeSkipped(unittest.TestCase):
    def test_the_completion_write_has_no_continue_on_error(self):
        node = NODES[COMPLETION]
        self.assertNotIn(
            "onError", node,
            f"{COMPLETION} still carries an onError setting "
            f"({node.get('onError')!r}); a failed durable write would flow on to "
            f"the success response",
        )
        self.assertNotIn("continueOnFail", node)

    def test_the_failure_branch_is_untouched(self):
        """The fix must not quietly change what happens when the publish fails."""
        failure_targets = _targets(GATE, 1)
        self.assertIn("Respond — Publish Failure", failure_targets)
        self.assertIn("Idempotency — Mark Failed", failure_targets)


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""QC-F02 — anyone-with-the-link edit sharing is preserved in the export.

The live Sheet Creator (INyGjT8jQ6JjrZSh) intentionally grants Drive permission
type=anyone, role=writer. The repo export must carry the same node/parameters
and must not introduce any access-restriction migration. Docs must document the
contract, not flag it as a defect.
"""
import json
import os
import unittest

BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
EXPORT = os.path.join(
    BASE, "35-social-media-planner", "config", "n8n",
    "social-planner-sheet-create.json")
README = os.path.join(
    BASE, "35-social-media-planner", "config", "n8n", "README.md")
INSTALL = os.path.join(BASE, "35-social-media-planner", "INSTALL.md")

LIVE_SHARE_NODE = "Set Anyone Can Edit"


def load_export():
    with open(EXPORT) as f:
        return json.load(f)


class TestF02SharingPreserved(unittest.TestCase):
    def test_share_node_present_with_anyone_writer(self):
        export = load_export()
        nodes = [n for n in export["nodes"] if n["name"] == LIVE_SHARE_NODE]
        self.assertEqual(len(nodes), 1, "share node must exist exactly once")
        node = nodes[0]
        self.assertEqual(node["type"], "n8n-nodes-base.googleDrive")
        self.assertEqual(node["parameters"]["operation"], "share")
        perms = node["parameters"]["permissionsUi"]["permissionsValues"]
        self.assertEqual(perms["role"], "writer")
        self.assertEqual(perms["type"], "anyone")

    def test_share_node_wired_in_provisioning_chain(self):
        # Formatting is durably checkpointed before sharing; only after sharing
        # succeeds is the file marked ready. The sharing repair branch stays wired.
        export = load_export()
        connections = export["connections"]
        targets = [link["node"] for branch in connections["Sharing Ready?"]["main"] for link in branch]
        self.assertIn(LIVE_SHARE_NODE, targets)
        self.assertEqual(connections[LIVE_SHARE_NODE]["main"][0][0]["node"], "Tag Provisioning Key")
        # Reachability: every path from the share node eventually reaches
        # 'Respond: Created' without passing through the error branch.
        reachable = set()
        frontier = [LIVE_SHARE_NODE]
        while frontier:
            current = frontier.pop()
            if current in reachable:
                continue
            reachable.add(current)
            out = connections.get(current)
            if out is None:
                continue
            branches = out["main"] if isinstance(out, dict) else out
            for branch in branches:
                for link in branch:
                    frontier.append(link["node"])
        self.assertIn("Respond: Created", reachable,
                      "the share node must still precede the created response (F02)")

    def test_response_reports_anyone_link_sharing(self):
        export = load_export()
        raw = json.dumps(export)
        self.assertIn("anyone with the link can edit", raw)

    def test_no_restriction_migration(self):
        export = load_export()
        nodes = [n for n in export["nodes"]
                 if n["type"] == "n8n-nodes-base.googleDrive"]
        for node in nodes:
            params = json.dumps(node["parameters"])
            for banned in ('"role": "reader"', '"role": "commenter"',
                           '"role":"reader"', '"role":"commenter"'):
                self.assertNotIn(banned, params)
            share_nodes = node["parameters"].get("permissionsUi")
            if share_nodes:
                perms = share_nodes["permissionsValues"]
                self.assertIn(perms["role"], ("writer", "organizer", "fileOrganizer"))
                self.assertEqual(perms["type"], "anyone")

    def test_readme_documents_sharing_contract_as_intentional(self):
        with open(README) as f:
            text = f.read().lower()
        self.assertIn("anyone", text)
        self.assertIn("intentional", text)
        self.assertIn("never", text)
        self.assertIn("named-user-only", text)

    def test_install_documents_provisioning_sharing_verification(self):
        with open(INSTALL) as f:
            text = f.read().lower()
        self.assertIn("type=anyone", text)
        self.assertIn("role=writer", text)
        self.assertIn("4d-bis", text)
        self.assertIn("named-user-only", text)

    def test_placeholder_note_gone(self):
        with open(EXPORT) as f:
            raw = f.read()
        self.assertNotIn("_PLACEHOLDER_NOTE", raw)
        self.assertNotIn("RECONSTRUCTED", raw)


if __name__ == "__main__":
    unittest.main()
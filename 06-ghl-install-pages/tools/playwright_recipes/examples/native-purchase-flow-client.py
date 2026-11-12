#!/usr/bin/env python3
"""Host a native buyer-flow manifest using an already authenticated Playwright Page.

Usage from a signed-in host process:
    import runpy
    run = runpy.run_path("native-purchase-flow-client.py")["run"]
    receipt = run(page, 'flow.json', 'probes.json', '/durable/run-001')
The manifest must contain the actual approved Skill 49 graph, independently read
back page/step mappings, and the staged inputs described in native-purchase-flow-README.md. This
client never publishes or performs a payment. Its return is editor evidence,
not a buyer-journey PASS.
"""
from pathlib import Path
import json
import sys

RECIPES = Path(__file__).resolve().parents[1]
TOOLS = RECIPES.parent
for path in (str(TOOLS), str(RECIPES)):
    if path not in sys.path:
        sys.path.insert(0, path)
from playwright_recipes.host import run_recipe


def run(page, manifest_path, probes_path, evidence_root):
    manifest_path = Path(manifest_path).resolve()
    inputs = json.loads(manifest_path.read_text(encoding='utf-8'))
    probes = json.loads(Path(probes_path).read_text(encoding='utf-8'))
    return run_recipe('checkout.purchase_flow', inputs, probes, Path(evidence_root),
                      input_dir=manifest_path.parent, page=page)

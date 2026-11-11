"""Test helper: the Skill 45 receipt that image-inventory-prompts cannot close without (fix spec M4).

In a real run scripts/build_production_request.py writes private/receipts/design-intelligence.json
as it builds each stage's request. The fixtures here stage a run by hand, so they write the same
receipt through the same module, against the real design library, before the prompts stage closes.
"""
import importlib.util
from pathlib import Path

_PATH = Path(__file__).resolve().parents[2] / "shared-utils" / "signature_launch" / "design_intelligence.py"


def module():
    spec = importlib.util.spec_from_file_location("signature_launch_design_intelligence", _PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def put(run, card_id=None, root=None):
    """Write <run>/private/receipts/design-intelligence.json for the run and return its path."""
    return module().write_receipt(Path(run), card_id, root=root)

"""Re-export shim (no logic): order_components now lives at 06-ghl-install-pages/tools/order_components.py.

Old path kept so nothing that imports or runs it breaks. Run the self-check at
the real location. ponytail: the impl is loaded under its own module name, so
classes here are the impl's classes only when callers import via this shim.
"""
import importlib.util
import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[2] / "06-ghl-install-pages/tools/order_components.py"
_NAME = "_impl_order_components"
_mod = sys.modules.get(_NAME)
if _mod is None:
    _spec = importlib.util.spec_from_file_location(_NAME, _IMPL)
    _mod = importlib.util.module_from_spec(_spec)
    sys.modules[_NAME] = _mod
    _spec.loader.exec_module(_mod)
globals().update({k: v for k, v in vars(_mod).items() if not k.startswith("__")})

if __name__ == "__main__":
    raise SystemExit(_mod._self_check())

"""S44-13 commerce rule: a launch is not 'ready' while a sellable native id is null.

Check-rule contract (see ``check_rules/__init__.py``): ``violations(manifest, root,
skill_root)`` returns one string per violation; an empty list passes.

The launch plan carries a ``commerce_units`` list. Owners (DECISIONS.md, S44-13):
Skill 44 creates the product and price (``shared-utils/ghl/products_prices.py``,
read-back verified) and records the native ids here; Skill 06 places the order form,
bump and one-click upsell/downsell; the payment-provider connection is a documented
operator manual gate. Unit shape::

    {"id": "main_offer", "kind": "product", "native_product_id": "...", "native_price_id": "..."}
    {"id": "stripe",     "kind": "payment_provider", "operator_confirmed": true}

Kinds that sell something (product, order_form, order_bump, upsell, downsell) need both
native ids. A null, empty or placeholder id is not a binding.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

SELLING_KINDS = ("product", "order_form", "order_bump", "upsell", "downsell")
PROVIDER_KIND = "payment_provider"
NATIVE_ID_FIELDS = ("native_product_id", "native_price_id")
CHECKOUT_PAGE_KINDS = ("order", "checkout", "upsell", "downsell")
_PLACEHOLDERS = ("", "null", "none", "tbd", "todo", "placeholder", "xxx", "n/a")


def _real_id(value: Any) -> bool:
    return isinstance(value, str) and value.strip().lower() not in _PLACEHOLDERS


def unit_violations(units: Any) -> List[str]:
    """Violations of a ``commerce_units`` value, independent of where it was loaded from."""
    if not isinstance(units, list) or not units:
        return ["AF-LAUNCH-COMMERCE-MISSING: the launch plan carries no commerce unit "
                "(product, price, order form, bump, upsell/downsell, payment provider)"]
    fails: List[str] = []
    for index, unit in enumerate(units):
        if not isinstance(unit, dict):
            fails.append(f"AF-LAUNCH-COMMERCE-SHAPE: commerce_units[{index}] must be an object")
            continue
        label = unit.get("id") or f"commerce_units[{index}]"
        kind = unit.get("kind")
        if kind in SELLING_KINDS:
            for field in NATIVE_ID_FIELDS:
                if not _real_id(unit.get(field)):
                    fails.append(f"AF-LAUNCH-COMMERCE-NATIVE-ID: commerce unit {label!r} ({kind}) "
                                 f"has no {field}; the launch is not ready while a native id is null")
        elif kind == PROVIDER_KIND:
            if unit.get("operator_confirmed") is not True:
                fails.append(f"AF-LAUNCH-COMMERCE-PROVIDER: payment provider {label!r} is not "
                             "confirmed connected by the operator (manual gate)")
        else:
            fails.append(f"AF-LAUNCH-COMMERCE-KIND: commerce unit {label!r} has unknown kind {kind!r}")
    return fails


def _load_plan(manifest: Dict[str, Any], root: Path) -> Dict[str, Any] | None:
    path = ((manifest.get("launch_plan") or {}).get("plan") or {}).get("path")
    if not path:
        return None
    try:
        plan = json.loads((Path(root) / str(path)).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None  # an unreadable plan is already named by AF-LAUNCH-PKG-PLAN-MISSING
    return plan if isinstance(plan, dict) else None


def violations(manifest: Dict[str, Any], root: Path, skill_root: Path) -> List[str]:
    plan = _load_plan(manifest, root)
    if plan is None:
        return []  # a page-only package predates the shared launch plan
    if "commerce_units" not in plan:
        pages = [p for p in plan.get("pages") or [] if isinstance(p, dict)]
        sells = any(p.get("kind") in CHECKOUT_PAGE_KINDS for p in pages)
        # ponytail: a test_only (offline) package is not claimed sellable, so it may omit
        # the commerce list; a client delivery (test_only false) that sells may not.
        if not sells or manifest.get("test_only") is not False:
            return []
    return unit_violations(plan.get("commerce_units"))

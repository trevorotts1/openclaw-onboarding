"""Load the real funnel/page skill modules by their real file paths.

The skill folders are not importable package names (leading digits, hyphens),
so the launcher binds them with importlib from the exact tree. No substrate
module is copied, forked or reimplemented; every import below is a real entry
point named in the received contracts.

References below are written with the skill SLUG and resolved by
``launcher_core.constants.resolve_ref``, which accepts ``<number>-<slug>`` and
``<slug>`` alike, so the same code runs in the onboarding repository and in a
999 package that renames the trees.
"""
from __future__ import annotations

import importlib.util
import sys
from contextlib import contextmanager
from pathlib import Path

ROUTES_DIR = Path(__file__).resolve().parent
SKILL_DIR = ROUTES_DIR.parent
REPO_ROOT = SKILL_DIR.parent

if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from launcher_core.constants import resolve_ref  # noqa: E402


def source(rel_path: str) -> Path:
    """Resolve a repository-relative path, refusing escape and placeholders.

    The first segment names a skill by either convention; an unresolvable skill
    slug raises SkillResolutionError naming the slug, never a FileNotFoundError.
    """
    if rel_path.startswith("/") or ".." in Path(rel_path).parts:
        raise ValueError(f"substrate path must be repository-relative: {rel_path!r}")
    return resolve_ref(rel_path, REPO_ROOT)


@contextmanager
def _sibling_imports(directory: Path | None):
    if directory is None:
        yield
        return
    sys.path.insert(0, str(directory))
    try:
        yield
    finally:
        try:
            sys.path.remove(str(directory))
        except ValueError:
            pass


_cache: dict[tuple[str, str], object] = {}


def load(rel_path: str, module_name: str, sibling_dir: str | None = None):
    """Load a real module from its file path, with optional sibling imports."""
    key = (rel_path, module_name)
    if key in _cache:
        return _cache[key]
    path = source(rel_path)
    sibling = source(sibling_dir) if sibling_dir else None
    with _sibling_imports(sibling):
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ModuleNotFoundError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    _cache[key] = module
    return module


def compiler():
    return load(
        "49-signature-funnel/scripts/compile_launch_route.py",
        "launcher_compile_launch_route",
    )


def dispatch():
    return load(
        "49-signature-funnel/scripts/dispatch_launch.py",
        "launcher_dispatch_launch",
        sibling_dir="49-signature-funnel/scripts",
    )


def landing_bridge():
    return load(
        "49-signature-funnel/scripts/landing_bridge.py",
        "launcher_landing_bridge",
    )


def upsell_wrapper():
    return load(
        "49-signature-funnel/scripts/upsell_wrapper.py",
        "launcher_upsell_wrapper",
    )


def downsell_wrapper():
    return load(
        "49-signature-funnel/scripts/downsell_wrapper.py",
        "launcher_downsell_wrapper",
    )


def thank_you_translator():
    return load(
        "49-signature-funnel/scripts/translate_thank_you_result.py",
        "launcher_translate_thank_you_result",
    )


def s71_launch_context():
    return load(
        "71-blackceo-signature-page/scripts/launch_context.py",
        "launcher_s71_launch_context",
    )


def s71_page_result():
    return load(
        "71-blackceo-signature-page/scripts/page_result.py",
        "launcher_s71_page_result",
    )


def s78_build_selection_plan():
    return load(
        "78-signature-product-selection/scripts/build_selection_plan.py",
        "launcher_s78_build_selection_plan",
    )


def s78_emit_page_result():
    return load(
        "78-signature-product-selection/scripts/emit_page_result.py",
        "launcher_s78_emit_page_result",
    )


def s79_validate_checkout():
    """Skill 79's cross-field checkout validator (the native order-form contract)."""
    return load(
        "79-signature-order-form/scripts/validate_checkout.py",
        "launcher_s79_validate_checkout",
    )


def s80_produce():
    return load(
        "80-signature-upsell/components/adapters/produce.py",
        "launcher_s80_produce",
        sibling_dir="80-signature-upsell/components/adapters",
    )


def s80_routing_state():
    return load(
        "80-signature-upsell/components/adapters/routing_state.py",
        "launcher_s80_routing_state",
    )


def s81_validate_request():
    return load(
        "81-signature-downsell/validators/validate_request.py",
        "launcher_s81_validate_request",
    )


def s81_validate_downsell():
    return load(
        "81-signature-downsell/validators/validate_downsell.py",
        "launcher_s81_validate_downsell",
    )


def s82_run_manifest():
    return load(
        "82-signature-thank-you/scripts/run_manifest.py",
        "launcher_s82_run_manifest",
        sibling_dir="82-signature-thank-you/scripts",
    )


def s82_thank_you_resolver():
    return load(
        "82-signature-thank-you/scripts/thank_you_resolver.py",
        "launcher_s82_thank_you_resolver",
    )

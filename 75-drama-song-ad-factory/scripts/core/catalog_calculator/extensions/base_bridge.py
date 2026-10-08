"""base_bridge — locate and load the Skill 75 catalog calculator.

BO-PKG2-U1 *extends* the price calculator built by unit V2-W0-U2
(``scripts/core/catalog_calculator/catalog_calculator.py``). It never
replaces that module and never re-implements its arithmetic: this file only
finds the module on disk, imports it, and reports plainly when it cannot.

Plan 4.2 / choice-card-spec section 4: a live rate that cannot be read makes
the card say "Price unavailable" and stops paid work. A calculator that cannot
be loaded is the same condition, so every entry point in this package fails
closed through here instead of falling back to a number of its own.

Search order: an explicit path, the ``BO_PKG2_U1_CALCULATOR`` environment
variable, then the calculator shipped in this skill (first candidate, from
this package's own directory and its ancestors), then the legacy
``tests/catalog-calculator/`` lane layout of the same checkout.

No operator paths (manual 02 B4): a card never depends on another machine's
home directory.

Stdlib only. No network.
"""
import importlib.util
import os

CALCULATOR_REL = os.path.join("scripts", "core", "catalog_calculator",
                              "catalog_calculator.py")
# The legacy lane layout, kept only for a checkout that predates W2-C-U1.
LEGACY_CALCULATOR_REL = os.path.join("tests", "catalog-calculator",
                                     "catalog_calculator.py")
ENV_VAR = "BO_PKG2_U1_CALCULATOR"

# The surface this extension calls. Anything less is not the calculator.
REQUIRED_ATTRS = ("price_card", "price_line", "credits_to_usd", "usd_label",
                  "shot_count", "UNIT_NAME")


def candidate_paths(explicit=None, module_dir=None):
    """Ordered absolute candidates. Existence only; never opens them."""
    out = []

    def add(path):
        path = os.path.abspath(path)
        if path not in out:
            out.append(path)

    if explicit:
        add(explicit)
    env = os.environ.get(ENV_VAR)
    if env:
        add(env)
    here = os.path.abspath(module_dir or os.path.dirname(os.path.abspath(__file__)))
    # FIRST candidate: the calculator shipped inside this skill. Walk from
    # this package's directory and its ancestors: the shipped copy sits one
    # directory above extensions/ in the repo and installed layouts.
    root = os.path.dirname(here)  # extensions' parent: the calculator's home
    for _ in range(5):  # catalog_calculator -> core -> 75 -> repo root
        add(os.path.join(root, "catalog_calculator.py"))
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    # Legacy: unit V2-W0-U2's lane layout (tests/catalog-calculator/) inside
    # this same checkout. No operator paths (manual 02 B4): a card never
    # depends on another machine's home directory.
    root = here
    for _ in range(5):
        add(os.path.join(root, LEGACY_CALCULATOR_REL))
        parent = os.path.dirname(root)
        if parent == root:
            break
        root = parent
    return out


def find_calculator(explicit=None, module_dir=None):
    """First existing candidate path, else None. Existence only, no import."""
    for path in candidate_paths(explicit, module_dir):
        if os.path.isfile(path):
            return path
    return None


def load_calculator(path):
    """Import the calculator from an absolute path; check its surface."""
    name = "bo_pkg2_u1_base_catalog_calculator"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise ImportError("cannot build import spec for %s" % path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    missing = [attr for attr in REQUIRED_ATTRS if not hasattr(module, attr)]
    if missing:
        raise ImportError("%s is missing %s" % (path, ", ".join(missing)))
    return module

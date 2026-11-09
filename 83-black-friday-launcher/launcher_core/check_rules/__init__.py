"""The check_rules seam: drop a module in this folder and check_package runs it.

A rule module defines one function::

    def violations(manifest: dict, root: pathlib.Path, skill_root: pathlib.Path) -> list[str]

It returns one plain string per violation (an empty list passes). ``check_package`` loads
every ``*.py`` file here (files starting with ``_`` are skipped) and fails on every string a
rule returns. The seam fails closed: a module with no ``violations`` function, one that
raises, or one that returns something other than a list of strings is itself a violation,
so a broken rule can never read as a pass.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Dict, List, Optional

CODE = "AF-LAUNCH-CHECK-RULE"
RULES_DIR = Path(__file__).resolve().parent


def rule_files(rules_dir: Optional[Path] = None) -> List[Path]:
    """Every rule module in the folder, in a stable order."""
    folder = Path(rules_dir) if rules_dir else RULES_DIR
    return sorted(p for p in folder.glob("*.py") if not p.name.startswith("_"))


def run(manifest: Dict[str, Any], root: Path, skill_root: Path,
        rules_dir: Optional[Path] = None) -> List[str]:
    """Run every rule module and return all violations they name."""
    fails: List[str] = []
    for path in rule_files(rules_dir):
        name = path.stem
        try:
            spec = importlib.util.spec_from_file_location(f"{__name__}.{name}", path)
            if spec is None or spec.loader is None:
                raise ImportError("no loader for the rule file")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            rule = getattr(module, "violations", None)
            if not callable(rule):
                fails.append(f"{CODE}: {name} defines no violations(manifest, root, skill_root)")
                continue
            got = rule(manifest, root, skill_root)
        except Exception as exc:  # a rule that cannot run is a failure, never a skip
            fails.append(f"{CODE}: {name} could not run ({type(exc).__name__}: {exc})")
            continue
        if not isinstance(got, (list, tuple)) or not all(isinstance(v, str) for v in got):
            fails.append(f"{CODE}: {name} must return a list of violation strings")
            continue
        fails.extend(got)
    return fails

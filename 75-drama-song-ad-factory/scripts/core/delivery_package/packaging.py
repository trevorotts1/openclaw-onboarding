"""DEL-13: the packaging entry point -- one run in, one delivery folder out.

package_run(run_dir, out_dir) is THE packaging call. It asks each of the 12
package items for its produced files (contract.ITEMS_BY_KEY[...].producers,
first module that exports produce_delivery(run_dir, item)), copies them into
out_dir under the canonical numbered names, then verifies the folder against
the contract. A component that has not landed yet is not guessed at: the call
raises COMPONENT_MISSING naming the DEL unit, the item and every candidate
module tried, and writes nothing.

Fail closed end to end:
  COMPONENT_MISSING -- a package item has no producer in this branch;
  COMPONENT_FAILED  -- a producer raised;
  PACKAGE_INCOMPLETE-- files were written but the folder does not verify.

Producers are injectable (producers={key: fn}) so the packaging path itself is
unit-testable before the sibling DEL units land. Stdlib only, no network.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from delivery_package.contract import (  # noqa: E402
    PACKAGE_ITEMS, ITEMS_BY_KEY, copy_item_sources, verify_folder)

TOOL_NAME = "delivery_package"
TOOL_VERSION = "1.0.0"
PRODUCE_ENTRY = "produce_delivery"     # produce_delivery(run_dir, item) -> [Path]


class PackageError(Exception):
    """A packaging call refused. code carries the machine reason."""

    def __init__(self, code, message, items=()):
        super().__init__("%s: %s" % (code, message))
        self.code = code
        self.message = message
        self.items = tuple(items)


def resolve_producer(item):
    """Find the component that produces one package item.

    Returns (callable, note) or (None, why). Tries item.producers in order;
    a module that exists but exports no produce_delivery is reported as
    "present, not wired" so the evidence says which unit still owes the call.
    """
    tried = []
    for dotted in item.producers:
        tried.append(dotted)
        try:
            module = importlib.import_module(dotted)
        except Exception as exc:                      # noqa: BLE001
            last_error = "%s: %s" % (dotted, exc.__class__.__name__)
            continue
        fn = getattr(module, PRODUCE_ENTRY, None)
        if callable(fn):
            return fn, "wired via %s" % dotted
        last_error = "%s: no %s()" % (dotted, PRODUCE_ENTRY)
    why = "%s component not landed (tried: %s)%s" % (
        item.unit, ", ".join(tried),
        "; last: %s" % last_error if tried else "")
    return None, why


def package_run(run_dir, out_dir, producers=None):
    """Package one fixture/production run into its delivery folder.

    run_dir  -- the run whose components produced the package items.
    out_dir  -- the delivery folder to write (created).
    producers-- optional {item key: fn}; when given, discovery is skipped so
                the packaging path can be exercised on its own.

    Returns {"folder", "items", "files", "contract_version"}. Raises
    PackageError before writing anything when a component is missing or
    fails; raises PACKAGE_INCOMPLETE when the written folder does not verify.
    """
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    if not run_dir.is_dir():
        raise PackageError("BAD_INPUT", "run folder missing: %s" % run_dir)

    plan, problems = {}, []
    for item in PACKAGE_ITEMS:
        if producers is not None:
            fn = producers.get(item.key)
            note = "injected" if fn is not None else \
                "%s component not injected" % item.unit
        else:
            fn, note = resolve_producer(item)
        if fn is None:
            problems.append("%s %s: %s" % (item.unit, item.label, note))
        else:
            plan[item] = (fn, note)
    if problems:
        missing = [item.key for item in PACKAGE_ITEMS if item not in plan]
        raise PackageError(
            "COMPONENT_MISSING",
            "packaging cannot run, %d of %d package item(s) unproduced -- %s"
            % (len(problems), len(PACKAGE_ITEMS), " | ".join(problems)),
            items=missing)

    out_dir.mkdir(parents=True, exist_ok=True)
    collected, failed = {}, []
    for item, (fn, note) in plan.items():
        try:
            sources = fn(run_dir, item)
        except Exception as exc:                      # noqa: BLE001
            failed.append("%s %s: producer raised %s: %s"
                          % (item.unit, item.label,
                             exc.__class__.__name__, exc))
            continue
        if not isinstance(sources, (list, tuple)):
            failed.append("%s %s: %s must return a list of paths"
                          % (item.unit, item.label, PRODUCE_ENTRY))
            continue
        collected[item] = list(sources)
    if failed:
        raise PackageError("COMPONENT_FAILED",
                           "%d producer(s) failed -- %s"
                           % (len(failed), " | ".join(failed)),
                           items=[k for k, v in plan.items()
                                  if any(f.startswith("%s %s" % (k.unit, k.label))
                                         for f in failed)])

    written = []
    for item in PACKAGE_ITEMS:
        try:
            written.extend(copy_item_sources(item, collected[item], out_dir))
        except ValueError as exc:
            raise PackageError("COMPONENT_FAILED", str(exc),
                               items=(item.key,)) from exc

    report = verify_folder(out_dir)
    if not report["ok"]:
        raise PackageError(
            "PACKAGE_INCOMPLETE",
            "folder does not verify -- " + "; ".join(
                "%s: %s (%s)" % (p["item"], p["file"], p["problem"])
                for p in report["problems"]),
            items=tuple(report["missing"]))
    return {"folder": str(out_dir),
            "items": [item.key for item in PACKAGE_ITEMS],
            "files": [str(p) for p in written],
            "contract_version": report["contract_version"]}


__all__ = ["PackageError", "package_run", "resolve_producer",
           "ITEMS_BY_KEY", "PACKAGE_ITEMS", "TOOL_NAME", "TOOL_VERSION"]

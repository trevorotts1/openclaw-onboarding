"""DEL-13: the packaging entry point -- one run in, one delivery folder out.

package_run(run_dir, out_dir) is THE packaging call. It first reads the run's
OWN recorded obligations (``run_inputs.delivery_context``: intake admission,
the client's saved length and ``control/method.json``), then asks each item
the run owes for its produced files (contract.ITEMS_BY_KEY[...].producers,
first module that exports produce_delivery(run_dir, item)), copies them into
out_dir under the exact names that item carries, and verifies the folder
against the same resolved items. A 60/90/120 second ad owes no clip files; a
campaign owes item 6 as trailers plus item 13, the ad clips, from the ONE
render pass. A component that has not landed is not guessed at: the call
raises COMPONENT_MISSING naming the DEL unit, the item and every candidate
module tried, and writes nothing.

Fail closed end to end:
  RUN_CONTEXT_UNVERIFIED -- the run cannot prove its own obligations;
  RUN_CONTEXT_MISMATCH   -- a caller-supplied reading disagrees with the run;
  COMPONENT_MISSING      -- a package item has no producer in this branch;
  COMPONENT_FAILED       -- a producer raised or left a promised file out;
  RUN_CONTEXT_CHANGED    -- the saved length/purpose moved during packaging;
  PACKAGE_INCOMPLETE     -- the folder does not verify against those items.

Producers are injectable (producers={key: fn}) so the packaging path itself is
unit-testable before the sibling DEL units land. Injection never skips the
run-context check. Stdlib only, no network.
"""
from __future__ import annotations

import importlib
import shutil
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from delivery_package.contract import (  # noqa: E402
    PACKAGE_ITEMS, ITEMS_BY_KEY, copy_item_sources, verify_folder)

TOOL_NAME = "delivery_package"
TOOL_VERSION = "1.1.0"
PRODUCE_ENTRY = "produce_delivery"     # produce_delivery(run_dir, item) -> [Path]

#: the only names that travel beside a separate approved export: the merged
#: client receipt and README. QC data, cost reports and provenance receipts
#: stay in the run.
_EXPORT_EXTRAS = ("delivery-receipt.json", "README.md")


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


def package_run(run_dir, out_dir, producers=None, *, run_id=None,
                context=None):
    """Package one run into its delivery folder, by that run's OWN obligations.

    run_dir  -- the run whose components produced the package items.
    out_dir  -- the delivery folder to write (created).
    producers-- optional {item key: fn}; when given, discovery is skipped so
                the packaging path can be exercised on its own. It never skips
                the run-context check: a run whose intake, purpose record or
                saved length cannot be read is refused before anything is
                written.
    run_id   -- the run id the caller means (an unknown one is refused).
    context  -- a caller's earlier ``run_inputs.delivery_context`` reading. It
                is only an assertion: it must match the run's freshly resolved
                obligations exactly or the call refuses (RUN_CONTEXT_MISMATCH)
                before any producer runs. Requirements and items always come
                from the fresh resolution, never from this mapping.

    Returns {"folder", "items", "files", "contract_version", "authority",
    "chosen_length_s", "purpose", "campaign", "not_applicable"}. Raises
    PackageError before copying anything into the client folder when the run
    context is unverifiable, a component is missing or fails, or the saved
    obligations changed while the producers ran; raises PACKAGE_INCOMPLETE
    when the written folder does not verify against those obligations.
    """
    run_dir = Path(run_dir)
    out_dir = Path(out_dir)
    if not run_dir.is_dir():
        raise PackageError("BAD_INPUT", "run folder missing: %s" % run_dir)
    ctx = _resolve_context(run_dir, run_id=run_id)
    if context is not None:
        _require_supplied_context(context, actual=ctx)
    items = ctx["items"]
    clips_owed = any(item.key == "clips" for item in items)

    plan, problems = {}, []
    for item in items:
        if item.key == "ad_clips" and clips_owed:
            plan[item] = (None, "staged from the clip render")
            continue
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
        missing = [item.key for item in items if item not in plan]
        raise PackageError(
            "COMPONENT_MISSING",
            "packaging cannot run, %d of %d owed item(s) unproduced -- %s"
            % (len(problems), len(items), " | ".join(problems)),
            items=missing)

    collected, failed = {}, []
    for item, (fn, note) in plan.items():
        if fn is None:                        # campaign ads: one render pass
            continue
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
    if any(item.key == "ad_clips" for item in items):
        ad_item = next(item for item in items if item.key == "ad_clips")
        collected[ad_item] = _campaign_ad_sources(ad_item, collected, items)

    _recheck_context(run_dir, run_id=run_id, ctx=ctx)

    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for item in items:
        try:
            written.extend(copy_item_sources(item, collected[item], out_dir))
        except ValueError as exc:
            raise PackageError("COMPONENT_FAILED", str(exc),
                               items=(item.key,)) from exc
    written.extend(_copy_export_extras(run_dir, out_dir))

    report = verify_folder(out_dir, campaign_run=ctx["campaign"],
                           chosen_length_s=ctx["chosen_length_s"])
    if not report["ok"]:
        raise PackageError(
            "PACKAGE_INCOMPLETE",
            "folder does not verify -- " + "; ".join(
                "%s: %s (%s)" % (p["item"], p["file"], p["problem"])
                for p in report["problems"]),
            items=tuple(report["missing"]))
    return {"folder": str(out_dir),
            "items": [item.key for item in items],
            "files": [str(p) for p in written],
            "contract_version": report["contract_version"],
            "authority": report["authority"],
            "chosen_length_s": ctx["chosen_length_s"],
            "purpose": ctx["purpose"],
            "campaign": ctx["campaign"],
            "not_applicable": list(report["not_applicable"])}


def _resolve_context(run_dir, *, run_id):
    """The run's recorded obligations, freshly read -- never supplied."""
    from delivery_package import run_inputs          # noqa: PLC0415
    try:
        return run_inputs.delivery_context(run_dir, run_id=run_id)
    except run_inputs.RunInputError as exc:
        raise PackageError("RUN_CONTEXT_UNVERIFIED", str(exc)) from exc


def _context_identity(ctx):
    """Everything that decides which files a run owes, nothing less."""
    return (ctx.get("run_id"), ctx.get("purpose"), bool(ctx.get("campaign")),
            bool(ctx.get("method_run")), ctx.get("chosen_length_s"),
            tuple(ctx.get("items") or ()),
            tuple(ctx.get("not_applicable") or ()))


def _require_supplied_context(given, *, actual):
    """A supplied reading may assert the run's obligations, never set them."""
    if not isinstance(given, dict):
        raise PackageError(
            "RUN_CONTEXT_MISMATCH",
            "supplied context is not a run_inputs.delivery_context mapping",
            items=())
    before, fresh = _context_identity(given), _context_identity(actual)
    if before != fresh:
        names = ("run_id", "purpose", "campaign", "method_run",
                 "chosen_length_s", "items", "not_applicable")
        differ = [name for name, a, b in zip(names, before, fresh) if a != b]
        raise PackageError(
            "RUN_CONTEXT_MISMATCH",
            "the supplied context disagrees with the run's freshly resolved "
            "obligations (%s differ); requirements are always taken from the "
            "run" % ", ".join(differ), items=())


def _recheck_context(run_dir, *, run_id, ctx):
    """The run's complete obligation identity must survive the producers."""
    after = _resolve_context(run_dir, run_id=run_id)
    if _context_identity(after) != _context_identity(ctx):
        raise PackageError(
            "RUN_CONTEXT_CHANGED",
            "the run's resolved obligations changed while packaging ran; "
            "nothing was copied into the client folder and the produced "
            "sources are left in place",
            items=())


def _campaign_ad_sources(ad_item, collected, items):
    """Item 13's files: the ad clips the clip pass already rendered, never a re-render."""
    from delivery_package import run_inputs          # noqa: PLC0415
    clips = next((item for item in items if item.key == "clips"), None)
    sources = collected.get(clips) if clips is not None else None
    if not sources:
        raise PackageError("COMPONENT_FAILED",
                           "%s has no clip render to stage the ad clips from"
                           % ad_item.key, items=(ad_item.key,))
    try:
        return run_inputs.stage(ad_item, Path(sources[0]).parent)
    except run_inputs.RunInputError as exc:
        raise PackageError("COMPONENT_FAILED", str(exc),
                           items=(ad_item.key,)) from exc


def _copy_export_extras(run_dir, out_dir):
    """Carry the merged receipt and README to a separate approved export.

    The producers merged them in the run's own delivery folder; a second
    folder must not lose them. Only these two names travel -- QC data, cost
    reports and provenance receipts stay in the run.
    """
    from delivery_package import run_inputs          # noqa: PLC0415
    source = run_inputs.delivery_dir(run_dir)
    if source.resolve() == out_dir.resolve():
        return []
    written = []
    for name in _EXPORT_EXTRAS:
        src = source / name
        if src.is_file():
            dest = out_dir / name
            shutil.copy2(src, dest)
            written.append(dest)
    return written


__all__ = ["PackageError", "package_run", "resolve_producer",
           "ITEMS_BY_KEY", "PACKAGE_ITEMS", "TOOL_NAME", "TOOL_VERSION"]

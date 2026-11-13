#!/usr/bin/env python3
"""DEL-13 / S75-055: the packaging command -- one run in, one folder out.

    python3 -m delivery_package package --run-dir <run> [--out <run>/delivery]

Prints ONE JSON object on standard output and nothing else::

    {"ok": bool, "items": [...numbered items...], "missing": [...],
     "problems": [...]}

``--out`` defaults to the run's own delivery folder (``<run>/delivery``).
Exit 0 only when ``contract.verify_folder`` says the folder is ok; every
refusal exits 1 with its code in ``problems``.

Before a producer runs, the run's four packaging inputs are checked by
``run_inputs.require_packaging_inputs``: a missing one is refused BY STAGE
("the music stage writes it ..."), never by a bare path -- the finding this
command fixes is that no stage wrote them and the old path named no owner.

Stdlib only, no network, no provider call.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_CORE = Path(__file__).resolve().parents[1]
if str(_CORE) not in sys.path:
    sys.path.insert(0, str(_CORE))

from delivery_package import contract, packaging, run_inputs  # noqa: E402

EXIT_OK = 0
EXIT_REFUSED = 1


def _envelope(ok, items=(), missing=(), problems=()):
    return {"ok": bool(ok), "items": list(items), "missing": list(missing),
            "problems": list(problems)}


def _item_rows(report):
    """The numbered items the folder was verified against, in slot order."""
    known = {item.key: item for item in
             contract.PACKAGE_ITEMS + contract.OPTIONAL_ITEMS}
    present = set(report["present"])
    rows = []
    for key in list(report["present"]) + list(report["missing"]):
        item = known.get(key)
        if item is None:
            continue
        rows.append({"number": item.number, "key": key, "unit": item.unit,
                     "label": item.label, "files": list(item.files),
                     "present": key in present})
    rows.sort(key=lambda row: row["number"])
    return rows


def _emit(envelope, code):
    print(json.dumps(envelope, sort_keys=True))
    return code


def package(args):
    """Run the packaging call and emit its envelope; returns the exit code."""
    run_dir = Path(args.run_dir).expanduser()
    out_dir = (Path(args.out).expanduser() if args.out
               else run_dir / run_inputs.DELIVERY_NAME)
    try:
        run_inputs.require_packaging_inputs(run_dir)
    except run_inputs.PackagingInputMissing as exc:
        return _emit(_envelope(False, missing=list(exc.missing),
                               problems=[str(exc)]), EXIT_REFUSED)
    except run_inputs.RunInputError as exc:
        return _emit(_envelope(False, problems=[str(exc)]), EXIT_REFUSED)
    try:
        result = packaging.package_run(run_dir, out_dir)
    except packaging.PackageError as exc:
        return _emit(_envelope(False, missing=list(exc.items),
                               problems=["%s: %s" % (exc.code, exc.message)]),
                     EXIT_REFUSED)
    report = contract.verify_folder(out_dir,
                                    campaign_run=result["campaign"],
                                    chosen_length_s=result["chosen_length_s"])
    problems = ["%s %s: %s" % (problem["item"] or "-", problem["file"],
                               problem["problem"])
                for problem in report["problems"]]
    return _emit(_envelope(bool(report["ok"]), items=_item_rows(report),
                           missing=report["missing"], problems=problems),
                 EXIT_OK if report["ok"] else EXIT_REFUSED)


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="python3 -m delivery_package",
        description="Package one run's delivery folder and verify it.")
    sub = ap.add_subparsers(dest="command", required=True)
    pack = sub.add_parser("package", help="package one run's delivery folder")
    pack.add_argument("--run-dir", required=True, help="the run folder")
    pack.add_argument("--out", default=None,
                      help="delivery folder (default: <run>/delivery)")
    args = ap.parse_args(argv)
    if args.command == "package":
        return package(args)
    return EXIT_REFUSED


if __name__ == "__main__":
    sys.exit(main())

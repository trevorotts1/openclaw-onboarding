#!/usr/bin/env python3
"""Write <run_dir>/page-result.json and <run_dir>/page-handoff.json
(Signature Launch S71-05; builder: scripts/page_result.py).

This is the standalone form of the emission the stage gate's report
pass performs automatically for any run that carries a
page-request.json (doc 02 section 6). The result conforms to
references/page-result.schema.json and is validated against that file
before it is written; an invalid result is refused, never written.

Exit codes: 0 written; 1 the run carries no page-request.json (not a
Signature Launch run, nothing written); 2 the result cannot be built
validly (the failure lines are printed), which includes a
page-request.json that is present but corrupt: a corrupt request is
an error state, never a silent skip.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import page_result


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Write the Signature Launch page-result.json and "
                    "page-handoff.json for a Skill 71 run.")
    p.add_argument("run_dir", type=Path)
    a = p.parse_args(argv)
    run_dir = a.run_dir.resolve()
    if not run_dir.is_dir():
        print(f"FAIL: run_dir does not exist: {run_dir}")
        return 2
    try:
        result_path, handoff_path, authorized = \
            page_result.build_and_write(run_dir)
    except page_result.NotLaunchRun:
        print(f"SKIP: {run_dir} carries no page-request.json; not a "
              f"Signature Launch run, nothing written")
        return 1
    except page_result.PageResultError as exc:
        print("FAIL")
        for line in exc.lines:
            print(f"- {line}")
        return 2
    print(f"wrote {result_path}")
    print(f"wrote {handoff_path}")
    print(f"routing authorized: {'yes' if authorized else 'no'} "
          f"(see page-handoff.json routing.basis)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
